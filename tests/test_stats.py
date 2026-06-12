import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from topik_sim.attempts import answer_question, complete_attempt, create_attempt, save_attempt_to_dir
from topik_sim.cli import main
from topik_sim.content import load_pack
from topik_sim.library import import_pack
from topik_sim.stats import collect_stats, format_stats


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


def _completed_attempt(pack, responses, durations=None, activity="exam"):
    question_ids = None if activity == "exam" else [qid for qid, _ in responses]
    attempt = create_attempt(pack, question_ids=question_ids, activity=activity)
    for index, (question_id, response) in enumerate(responses):
        duration = durations[index] if durations else None
        attempt = answer_question(attempt, pack, response, duration_seconds=duration)
    return complete_attempt(attempt, pack)


class StatsTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.library_dir = self.temp_dir / "library"
        self.attempt_dir = self.temp_dir / "attempts"
        import_pack(SAMPLE_PACK, self.library_dir)
        self.pack = load_pack(SAMPLE_PACK)

    def tearDown(self):
        self._temp.cleanup()

    def test_collect_stats_aggregates_skills_and_packs(self):
        first = _completed_attempt(self.pack, [("r-001", "B"), ("r-002", "C")], durations=[5.0, 7.0])
        second = _completed_attempt(self.pack, [("r-001", "B"), ("r-002", "A")], durations=[4.0, 6.0])
        first["completed_at"] = "2026-06-01T10:00:00+00:00"
        second["completed_at"] = "2026-06-02T10:00:00+00:00"
        save_attempt_to_dir(first, self.attempt_dir)
        save_attempt_to_dir(second, self.attempt_dir)

        stats = collect_stats(self.attempt_dir, self.library_dir)
        self.assertEqual(stats["attempt_count"], 2)
        reading = stats["skills"]["reading"]
        self.assertEqual(reading["total"], 4)
        self.assertEqual(reading["correct"], 3)
        self.assertAlmostEqual(reading["seconds"], 22.0)

        pack_entry = stats["packs"]["topik-i-mini-pack"]
        self.assertEqual(pack_entry["attempts"], 2)
        self.assertEqual(pack_entry["best"], (2, 2))
        self.assertEqual(pack_entry["last"], (2, 2))
        self.assertEqual(len(stats["trend"]), 2)

    def test_format_stats_renders_accuracy_and_trend(self):
        attempt = _completed_attempt(self.pack, [("r-001", "B"), ("r-002", "C")], durations=[5.0, 7.0])
        save_attempt_to_dir(attempt, self.attempt_dir)
        lines = format_stats(collect_stats(self.attempt_dir, self.library_dir))
        text = "\n".join(lines)
        self.assertIn("Completed attempts: 1", text)
        self.assertIn("reading: 50% (1/2) · avg 6s/question", text)
        self.assertIn("topik-i-mini-pack: 1 attempt(s) · best 1/2 · last 1/2", text)

    def test_stats_cli_reports_empty_state(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["stats", "--attempt-dir", str(self.attempt_dir), "--library", str(self.library_dir)])
        self.assertEqual(exit_code, 0)
        self.assertIn("No completed attempts yet", output.getvalue())


if __name__ == "__main__":
    unittest.main()
