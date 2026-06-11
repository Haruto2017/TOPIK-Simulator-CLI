import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from topik_sim.attempts import answer_question, complete_attempt, create_attempt, save_attempt_to_dir
from topik_sim.cli import main
from topik_sim.content import load_pack
from topik_sim.report import build_report, describe_correct_answer


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"
FORMATS_PACK = ROOT / "examples" / "content" / "topik_i_formats_pack.json"


class ReportTests(unittest.TestCase):
    def test_report_lists_misses_vocabulary_and_grammar(self):
        pack = load_pack(SAMPLE_PACK)
        attempt = create_attempt(pack)
        attempt = answer_question(attempt, pack, "B", duration_seconds=5.0)
        attempt = answer_question(attempt, pack, "C", duration_seconds=10.0)
        attempt = complete_attempt(attempt, pack)

        markdown = build_report(attempt, pack)
        self.assertIn("# Study Report — TOPIK I Mini Pack", markdown)
        self.assertIn("**1/2**", markdown)
        self.assertIn("### r-002", markdown)
        self.assertNotIn("### r-001", markdown)
        self.assertIn("Correct answer: A. library", markdown)
        self.assertIn("| 도서관 | library |", markdown)
        self.assertIn("**N에서**", markdown)
        self.assertIn("Time: 00:15", markdown)

    def test_perfect_score_report_celebrates(self):
        pack = load_pack(SAMPLE_PACK)
        attempt = create_attempt(pack)
        attempt = answer_question(attempt, pack, "B")
        attempt = answer_question(attempt, pack, "A")
        attempt = complete_attempt(attempt, pack)
        markdown = build_report(attempt, pack)
        self.assertIn("Perfect score", markdown)
        self.assertNotIn("Missed questions", markdown)

    def test_describe_correct_answer_per_type(self):
        pack = load_pack(FORMATS_PACK)
        questions = {question["question_id"]: question for question in pack.questions()}
        self.assertIn("A. 밥을 먹습니다.", describe_correct_answer(questions["f-001"]))
        self.assertEqual(describe_correct_answer(questions["f-002"]), "B → C → A")
        self.assertEqual(describe_correct_answer(questions["f-003"]), "에 / 에서")
        self.assertEqual(describe_correct_answer(questions["f-004"]), "A. Thank you.")

    def test_report_cli_writes_output_file(self):
        pack = load_pack(SAMPLE_PACK)
        attempt = create_attempt(pack)
        attempt = answer_question(attempt, pack, "B")
        attempt = answer_question(attempt, pack, "C")
        attempt = complete_attempt(attempt, pack)
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_path = save_attempt_to_dir(attempt, temp_dir)
            output_path = Path(temp_dir) / "report.md"
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["report", str(attempt_path), "--output", str(output_path)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            self.assertIn("Study Report", output_path.read_text(encoding="utf-8"))

    def test_report_cli_rejects_in_progress_attempts(self):
        pack = load_pack(SAMPLE_PACK)
        attempt = create_attempt(pack)
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_path = save_attempt_to_dir(attempt, temp_dir)
            stderr = StringIO()
            with redirect_stdout(StringIO()), patch("sys.stderr", stderr):
                exit_code = main(["report", str(attempt_path)])
            self.assertEqual(exit_code, 1)
            self.assertIn("completed attempt", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
