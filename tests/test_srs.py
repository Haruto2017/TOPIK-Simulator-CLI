import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from topik_sim import srs
from topik_sim.attempts import answer_question, complete_attempt, create_attempt
from topik_sim.content import load_pack
from topik_sim.library import import_pack
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import IDLE, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"
NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _completed(pack, responses):
    attempt = create_attempt(pack)
    for response in responses:
        attempt = answer_question(attempt, pack, response)
    return complete_attempt(attempt, pack)


class SrsQueueTests(unittest.TestCase):
    def setUp(self):
        self.pack = load_pack(SAMPLE_PACK)

    def test_misses_enter_box_one_and_are_due_immediately(self):
        queue = srs.load_queue("missing/queue.json")
        changes = srs.record_attempt(queue, _completed(self.pack, ["B", "C"]), now=NOW)
        self.assertEqual(changes, 1)
        due = srs.due_items(queue, now=NOW)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["question_id"], "r-002")
        self.assertEqual(due[0]["box"], 1)
        self.assertEqual(due[0]["lapses"], 1)

    def test_correct_answers_promote_and_schedule_later(self):
        queue = srs.load_queue("missing/queue.json")
        srs.record_attempt(queue, _completed(self.pack, ["B", "C"]), now=NOW)
        srs.record_attempt(queue, _completed(self.pack, ["B", "A"]), now=NOW)
        entry = queue["items"]["topik-i-mini-pack|r-002"]
        self.assertEqual(entry["box"], 2)
        self.assertTrue(entry["last_result"])
        self.assertEqual(srs.due_items(queue, now=NOW), [])
        later = NOW + timedelta(days=3)
        self.assertEqual(len(srs.due_items(queue, now=later)), 1)

    def test_wrong_again_demotes_to_box_one(self):
        queue = srs.load_queue("missing/queue.json")
        srs.record_attempt(queue, _completed(self.pack, ["B", "C"]), now=NOW)
        srs.record_attempt(queue, _completed(self.pack, ["B", "A"]), now=NOW)
        srs.record_attempt(queue, _completed(self.pack, ["B", "C"]), now=NOW)
        entry = queue["items"]["topik-i-mini-pack|r-002"]
        self.assertEqual(entry["box"], 1)
        self.assertEqual(entry["lapses"], 2)

    def test_top_box_success_retires_item(self):
        queue = srs.load_queue("missing/queue.json")
        srs.record_attempt(queue, _completed(self.pack, ["B", "C"]), now=NOW)
        for _ in range(srs.MAX_BOX):
            srs.record_attempt(queue, _completed(self.pack, ["B", "A"]), now=NOW)
        self.assertNotIn("topik-i-mini-pack|r-002", queue["items"])

    def test_create_review_attempt_uses_due_items(self):
        queue = srs.load_queue("missing/queue.json")
        srs.record_attempt(queue, _completed(self.pack, ["C", "C"]), now=NOW)
        attempt = srs.create_review_attempt(self.pack, queue, now=NOW)
        self.assertEqual(attempt["activity"], "review")
        self.assertEqual(set(attempt["question_ids"]), {"r-001", "r-002"})
        with self.assertRaisesRegex(ValueError, "No review items"):
            srs.create_review_attempt(self.pack, {"items": {}}, now=NOW)

    def test_queue_round_trips_to_disk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = srs.queue_path_for(temp_dir)
            queue = srs.load_queue(path)
            srs.record_attempt(queue, _completed(self.pack, ["B", "C"]), now=NOW)
            srs.save_queue(queue, path)
            reloaded = srs.load_queue(path)
            self.assertIn("topik-i-mini-pack|r-002", reloaded["items"])


class SrsShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        import_pack(SAMPLE_PACK, self.temp_dir / "library")

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self):
        output = []
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
        )
        return shell, output

    def test_finished_attempt_feeds_review_queue_and_review_runs(self):
        shell, output = self.make_shell()
        for line in ["/take topik-i-mini-pack", "B", "", "C", ""]:
            shell.handle_line(line)
        text = "\n".join(output)
        self.assertIn("Review queue: 1 item(s) due · /review", text)
        self.assertTrue(srs.queue_path_for(self.temp_dir / "attempts").exists())

        output.clear()
        for line in ["/review", "A", ""]:
            shell.handle_line(line)
        text = "\n".join(output)
        self.assertIn("Review: TOPIK I Mini Pack", text)
        self.assertIn("1 item(s) due", text)
        self.assertIn("r-002", text)
        self.assertIn("Score: 1/1", text)
        self.assertEqual(shell.state, IDLE)

        output.clear()
        shell.handle_line("/review")
        self.assertIn("Nothing is due for review.", "\n".join(output))


if __name__ == "__main__":
    unittest.main()
