import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from topik_sim import srs
from topik_sim.activities import missed_question_ids
from topik_sim.attempts import answer_question, complete_attempt, create_attempt, load_attempt, save_attempt_to_dir
from topik_sim.cli import main
from topik_sim.content import load_pack, validate_pack_data
from topik_sim.grading import grade_question


ROOT = Path(__file__).resolve().parents[1]
FORMATS_PACK = ROOT / "examples" / "content" / "topik_i_formats_pack.json"


def _essay_question(points=4, criteria=None):
    return {
        "question_id": "w-001",
        "order": 1,
        "skill": "writing",
        "prompt": "Write about your weekend.",
        "answer": {
            "type": "essay",
            "rubric": {
                "criteria": criteria
                if criteria is not None
                else [
                    {"name": "content", "max_points": 2},
                    {"name": "grammar", "max_points": 2},
                ]
            },
        },
        "points": points,
        "explanation": {"summary": "Two complete sentences."},
    }


def _pack_with(question):
    return {
        "schema_version": "topik-sim.content.v1",
        "pack_id": "essay-pack",
        "pack_version": "0.0.1",
        "title": "Essay Pack",
        "topik_level": "TOPIK_I",
        "language_pair": "ko-en",
        "source_type": "original",
        "sections": [{"section_id": "writing", "title": "Writing", "questions": [question]}],
    }


class EssayTypeTests(unittest.TestCase):
    def test_essay_validation_requires_rubric_and_matching_points(self):
        self.assertEqual(validate_pack_data(_pack_with(_essay_question())), [])

        errors = validate_pack_data(_pack_with(_essay_question(criteria=[])))
        self.assertTrue(any("rubric.criteria" in error for error in errors))

        errors = validate_pack_data(_pack_with(_essay_question(points=5)))
        self.assertTrue(any("rubric total" in error for error in errors))

        bad_criterion = [{"name": "content", "max_points": 0}]
        errors = validate_pack_data(_pack_with(_essay_question(points=0, criteria=bad_criterion)))
        self.assertTrue(any("max_points" in error for error in errors))

    def test_essay_grades_as_pending_manual_review(self):
        result = grade_question(_essay_question(), "주말에 친구를 만났습니다.")
        self.assertFalse(result["correct"])
        self.assertEqual(result["points_awarded"], 0)
        self.assertEqual(result["max_points"], 4)
        self.assertTrue(result["needs_review"])
        self.assertIn("manual review", result["feedback"]["summary"])

    def test_essays_are_excluded_from_drill_and_srs(self):
        pack_data = _pack_with(_essay_question())
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_path = Path(temp_dir) / "pack.json"
            pack_path.write_text(json.dumps(pack_data, ensure_ascii=False), encoding="utf-8")
            pack = load_pack(pack_path)
            attempt = answer_question(create_attempt(pack), pack, "글입니다.")
            attempt = complete_attempt(attempt, pack)
            self.assertEqual(missed_question_ids(attempt), [])
            queue = srs.load_queue(Path(temp_dir) / "queue.json")
            self.assertEqual(srs.record_attempt(queue, attempt), 0)

    def test_review_writing_records_rubric_scores(self):
        pack = load_pack(FORMATS_PACK)
        attempt = create_attempt(pack, question_ids=["f-005"])
        attempt = answer_question(attempt, pack, "주말에 친구를 만났습니다. 같이 영화를 봤습니다.")
        attempt = complete_attempt(attempt, pack)
        self.assertEqual(attempt["result"]["score"], 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_path = save_attempt_to_dir(attempt, temp_dir)
            output = StringIO()
            with patch("builtins.input", side_effect=["2", "1"]), redirect_stdout(output):
                exit_code = main(["review-writing", str(attempt_path)])
            self.assertEqual(exit_code, 0)
            self.assertIn("Updated score: 3/4", output.getvalue())

            reloaded = load_attempt(attempt_path)
            item = reloaded["result"]["results"][0]
            self.assertEqual(item["manual_scores"], {"content": 2, "grammar": 1})
            self.assertEqual(item["points_awarded"], 3)
            self.assertTrue(item["correct"])
            self.assertFalse(item["needs_review"])
            self.assertIn("Scored 3/4", item["feedback"]["summary"])

    def test_review_writing_low_score_counts_as_incorrect(self):
        pack = load_pack(FORMATS_PACK)
        attempt = create_attempt(pack, question_ids=["f-005"])
        attempt = answer_question(attempt, pack, "짧음")
        attempt = complete_attempt(attempt, pack)
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_path = save_attempt_to_dir(attempt, temp_dir)
            with patch("builtins.input", side_effect=["1", "0"]), redirect_stdout(StringIO()):
                main(["review-writing", str(attempt_path)])
            reloaded = load_attempt(attempt_path)
            item = reloaded["result"]["results"][0]
            self.assertEqual(item["points_awarded"], 1)
            self.assertFalse(item["correct"])

    def test_review_writing_with_nothing_pending(self):
        pack = load_pack(FORMATS_PACK)
        attempt = create_attempt(pack, question_ids=["f-004"])
        attempt = answer_question(attempt, pack, "A")
        attempt = complete_attempt(attempt, pack)
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_path = save_attempt_to_dir(attempt, temp_dir)
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["review-writing", str(attempt_path)])
            self.assertEqual(exit_code, 0)
            self.assertIn("Nothing is awaiting manual review", output.getvalue())


if __name__ == "__main__":
    unittest.main()
