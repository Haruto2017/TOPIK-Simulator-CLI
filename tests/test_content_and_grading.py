import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from topik_sim.content import load_pack, validate_pack_file
from topik_sim.grading import grade_answers
from topik_sim.library import import_pack, list_packs, load_pack_ref, validate_library
from topik_sim.attempts import (
    answer_question,
    attempt_progress,
    complete_attempt,
    create_attempt,
    load_attempt,
    remaining_question_ids,
    save_attempt,
)
from topik_sim.cli import main


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


class ContentAndGradingTests(unittest.TestCase):
    def test_sample_pack_is_valid(self):
        self.assertEqual(validate_pack_file(SAMPLE_PACK), [])

    def test_batch_grading_scores_answers(self):
        pack = load_pack(SAMPLE_PACK)
        result = grade_answers(pack.data, {"r-001": "B", "r-002": "C"})
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["max_score"], 2)
        self.assertTrue(result["results"][0]["correct"])
        self.assertFalse(result["results"][1]["correct"])

    def test_duplicate_question_ids_are_rejected(self):
        data = json.loads(SAMPLE_PACK.read_text(encoding="utf-8"))
        data["sections"][0]["questions"][1]["question_id"] = "r-001"
        temp_path = ROOT / "examples" / "content" / "_invalid_duplicate.json"
        try:
            temp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            errors = validate_pack_file(temp_path)
            self.assertTrue(any("duplicated" in error for error in errors))
        finally:
            temp_path.unlink(missing_ok=True)

    def test_pack_import_creates_versioned_library_manifest(self):
        library_dir = ROOT / "data" / "test_library"
        _remove_tree(library_dir)
        try:
            imported = import_pack(SAMPLE_PACK, library_dir)
            self.assertEqual(imported["pack_id"], "topik-i-mini-pack")
            self.assertEqual(imported["pack_version"], "0.1.0")
            self.assertTrue(Path(imported["path"]).exists())

            packs = list_packs(library_dir)
            self.assertEqual(len(packs), 1)
            self.assertEqual(packs[0]["checksum_sha256"], imported["checksum_sha256"])
            self.assertEqual(validate_library(library_dir), [])
        finally:
            _remove_tree(library_dir)

    def test_library_loads_pack_by_id_and_version(self):
        library_dir = ROOT / "data" / "test_library"
        _remove_tree(library_dir)
        try:
            import_pack(SAMPLE_PACK, library_dir)
            latest = load_pack_ref("topik-i-mini-pack", library_dir)
            pinned = load_pack_ref("topik-i-mini-pack@0.1.0", library_dir)
            self.assertEqual(latest.pack_id, "topik-i-mini-pack")
            self.assertEqual(pinned.data["pack_version"], "0.1.0")
        finally:
            _remove_tree(library_dir)

    def test_attempt_can_be_answered_completed_and_reloaded(self):
        pack = load_pack(SAMPLE_PACK)
        attempt = create_attempt(pack)
        self.assertEqual(attempt_progress(attempt), (0, 2))
        attempt = answer_question(attempt, pack, "B")
        self.assertEqual(attempt_progress(attempt), (1, 2))
        self.assertEqual(remaining_question_ids(attempt), ["r-002"])
        attempt = answer_question(attempt, pack, "C")
        completed = complete_attempt(attempt, pack)

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"]["score"], 1)
        self.assertEqual(completed["result"]["max_score"], 2)

        attempt_path = ROOT / "data" / "test_attempts" / "attempt.json"
        attempt_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            save_attempt(completed, attempt_path)
            reloaded = load_attempt(attempt_path)
            self.assertEqual(reloaded["attempt_id"], completed["attempt_id"])
            self.assertEqual(reloaded["answers"][0]["question_id"], "r-001")
        finally:
            attempt_path.unlink(missing_ok=True)
            _remove_tree(attempt_path.parent)

    def test_resume_attempt_continues_from_next_unanswered_question(self):
        library_dir = ROOT / "data" / "test_resume_library"
        attempt_dir = ROOT / "data" / "test_resume_attempts"
        _remove_tree(library_dir)
        _remove_tree(attempt_dir)
        try:
            import_pack(SAMPLE_PACK, library_dir)
            pack = load_pack(SAMPLE_PACK)
            attempt = answer_question(create_attempt(pack), pack, "B")
            attempt_dir.mkdir(parents=True, exist_ok=True)
            attempt_path = attempt_dir / "partial.json"
            save_attempt(attempt, attempt_path)

            output = StringIO()
            with patch("builtins.input", return_value="C"), redirect_stdout(output):
                exit_code = main(["resume-attempt", str(attempt_path), "--library", str(library_dir)])

            self.assertEqual(exit_code, 0)
            self.assertIn("Progress: 1/2 answered", output.getvalue())
            reloaded = load_attempt(attempt_path)
            self.assertEqual(reloaded["status"], "completed")
            self.assertEqual(attempt_progress(reloaded), (2, 2))
            self.assertEqual([answer["question_id"] for answer in reloaded["answers"]], ["r-001", "r-002"])
        finally:
            _remove_tree(library_dir)
            _remove_tree(attempt_dir)

    def test_list_attempts_shows_recent_progress(self):
        attempt_dir = ROOT / "data" / "test_list_attempts"
        _remove_tree(attempt_dir)
        try:
            pack = load_pack(SAMPLE_PACK)
            attempt = answer_question(create_attempt(pack), pack, "B")
            attempt["updated_at"] = "2026-06-03T10:00:00+00:00"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            save_attempt(attempt, attempt_dir / "partial.json")

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["list-attempts", "--attempt-dir", str(attempt_dir)])

            self.assertEqual(exit_code, 0)
            self.assertIn("Recent attempts:", output.getvalue())
            self.assertIn("1/2 answered", output.getvalue())
            self.assertIn("topik-i-mini-pack@0.1.0", output.getvalue())
        finally:
            _remove_tree(attempt_dir)

    def test_resume_attempt_without_path_prompts_from_recent_attempts(self):
        library_dir = ROOT / "data" / "test_resume_picker_library"
        attempt_dir = ROOT / "data" / "test_resume_picker_attempts"
        _remove_tree(library_dir)
        _remove_tree(attempt_dir)
        try:
            import_pack(SAMPLE_PACK, library_dir)
            pack = load_pack(SAMPLE_PACK)
            attempt = answer_question(create_attempt(pack), pack, "B")
            attempt["updated_at"] = "2026-06-03T10:00:00+00:00"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            attempt_path = attempt_dir / "partial.json"
            save_attempt(attempt, attempt_path)

            output = StringIO()
            with patch("builtins.input", side_effect=["1", "C"]), redirect_stdout(output):
                exit_code = main(
                    [
                        "resume-attempt",
                        "--attempt-dir",
                        str(attempt_dir),
                        "--library",
                        str(library_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Recent attempts:", output.getvalue())
            self.assertIn("Progress: 1/2 answered", output.getvalue())
            reloaded = load_attempt(attempt_path)
            self.assertEqual(reloaded["status"], "completed")
            self.assertEqual(attempt_progress(reloaded), (2, 2))
        finally:
            _remove_tree(library_dir)
            _remove_tree(attempt_dir)


if __name__ == "__main__":
    unittest.main()
