import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.attempts import answer_question, create_attempt, pack_time_limit_minutes
from topik_sim.content import load_pack
from topik_sim.session import ExamSession
from topik_sim.ui.render import format_clock, summary_panel
from topik_sim.ui import ansi


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class TimingTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)

    def tearDown(self):
        ansi.set_color_enabled(None)

    def test_attempt_records_time_limit_from_sections(self):
        pack = load_pack(SAMPLE_PACK)
        self.assertEqual(pack_time_limit_minutes(pack), 5)
        attempt = create_attempt(pack)
        self.assertEqual(attempt["time_limit_minutes"], 5)
        self.assertEqual(attempt["elapsed_seconds"], 0)
        # Partial selections do not pretend to be a timed exam.
        limited = create_attempt(pack, limit=1)
        self.assertIsNone(limited["time_limit_minutes"])
        drill = create_attempt(pack, question_ids=["r-001"], activity="drill")
        self.assertIsNone(drill["time_limit_minutes"])

    def test_answer_question_accumulates_duration(self):
        pack = load_pack(SAMPLE_PACK)
        attempt = create_attempt(pack)
        attempt = answer_question(attempt, pack, "B", duration_seconds=3.21)
        attempt = answer_question(attempt, pack, "A", duration_seconds=4.5)
        self.assertEqual(attempt["answers"][0]["duration_seconds"], 3.2)
        self.assertEqual(attempt["elapsed_seconds"], 7.7)

    def test_session_measures_question_duration(self):
        pack = load_pack(SAMPLE_PACK)
        with tempfile.TemporaryDirectory() as temp_dir:
            session = ExamSession.start(pack, temp_dir)
            with patch("topik_sim.session.time.monotonic", side_effect=[100.0, 103.5, 103.5]):
                session.mark_presented()
                session.submit("B")
            self.assertEqual(session.attempt["answers"][0]["duration_seconds"], 3.5)
            self.assertEqual(session.attempt["elapsed_seconds"], 3.5)

    def test_session_remaining_seconds_counts_down(self):
        pack = load_pack(SAMPLE_PACK)
        with tempfile.TemporaryDirectory() as temp_dir:
            session = ExamSession.start(pack, temp_dir)
            with patch("topik_sim.session.time.monotonic", side_effect=[100.0, 130.0]):
                session.mark_presented()
                remaining = session.remaining_seconds()
            self.assertEqual(remaining, 5 * 60 - 30)

    def test_format_clock_and_summary_show_pace(self):
        self.assertEqual(format_clock(0), "00:00")
        self.assertEqual(format_clock(75), "01:15")
        attempt = {
            "attempt_id": "x",
            "activity": "exam",
            "question_ids": ["a", "b"],
            "answers": [{"question_id": "a"}, {"question_id": "b"}],
            "elapsed_seconds": 90,
            "time_limit_minutes": 5,
            "result": {"score": 1, "max_score": 2},
        }
        panel = summary_panel(attempt)
        self.assertIn("Time: 01:30 · 45s/question · limit 05:00", panel)


if __name__ == "__main__":
    unittest.main()
