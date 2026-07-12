import tempfile
import unittest
from pathlib import Path

from topik_sim.library import import_pack
from topik_sim.practice_log import (
    load_practice_log,
    practice_summary,
    record_practice,
    weak_items,
)
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import TYPING, Shell
from topik_sim.web.app import WebApp

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class PracticeLogModuleTests(unittest.TestCase):
    def test_record_and_weak_aggregation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_practice(temp_dir, "recall", "Vocab recall", 2, 4, missed=["오늘", "날씨"])
            record_practice(temp_dir, "typing", "Typing practice", 3, 4, missed=["오늘"])
            log = load_practice_log(temp_dir)
            self.assertEqual(len(log["runs"]), 2)
            weak = weak_items(log)
            self.assertEqual(weak[0]["item"], "오늘")
            self.assertEqual(weak[0]["count"], 2)
            self.assertEqual({w["item"] for w in weak}, {"오늘", "날씨"})
            summary = practice_summary(log)
            self.assertEqual((summary["runs"], summary["hits"], summary["total"]), (2, 5, 8))

    def test_runs_are_capped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for index in range(210):
                record_practice(temp_dir, "numbers", "Number practice", 1, 1)
            self.assertEqual(len(load_practice_log(temp_dir)["runs"]), 200)

    def test_missing_or_corrupt_file_yields_empty_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(load_practice_log(temp_dir), {"runs": []})
            (Path(temp_dir) / "practice_log.json").write_text("not json", encoding="utf-8")
            self.assertEqual(load_practice_log(temp_dir), {"runs": []})


class StubPrefetcher:
    def warm(self, *args, **kwargs):
        return None

    def close(self):
        return None


class ShellRecordingTests(unittest.TestCase):
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
            flashcard_seed=0,
        )
        return shell, output

    def test_typing_run_lands_in_the_log_with_misses(self):
        shell, output = self.make_shell()
        shell.handle_line("/typing 3")
        first_wrong = False
        while shell.state == TYPING:
            item = shell._typing_items[shell._typing_index]
            if not first_wrong:
                shell.handle_line("오답임")
                first_wrong = True
            else:
                shell.handle_line(item["accept"][0])
        log = load_practice_log(self.temp_dir / "attempts")
        self.assertEqual(len(log["runs"]), 1)
        run = log["runs"][0]
        self.assertEqual(run["mode"], "typing")
        self.assertEqual((run["hits"], run["total"]), (2, 3))
        self.assertEqual(len(run["missed"]), 1)

    def test_early_stop_still_records_completed_items(self):
        shell, output = self.make_shell()
        shell.handle_line("/numbers 5")
        item = shell._typing_items[0]
        shell.handle_line(item["accept"][0])
        shell.handle_line("/pause")
        run = load_practice_log(self.temp_dir / "attempts")["runs"][0]
        self.assertEqual(run["mode"], "numbers")
        self.assertEqual(run["total"], 1)

    def test_stats_shows_practice_block_and_weak_items(self):
        shell, output = self.make_shell()
        record_practice(self.temp_dir / "attempts", "recall", "Vocab recall", 1, 3,
                        missed=["도서관", "날씨"])
        output.clear()
        shell.handle_line("/stats")
        text = "\n".join(output)
        self.assertIn("Practice", text)
        self.assertIn("1 run(s)", text)
        self.assertIn("도서관", text)


class WebRecordingTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        import_pack(SAMPLE_PACK, self.temp_dir / "library")

    def tearDown(self):
        self._temp.cleanup()

    def make_app(self):
        return WebApp(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            audio_enabled=False,
            seed=0,
        )

    def test_finished_drill_is_logged_and_feeds_misses_mode(self):
        app = self.make_app()
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "recall", "pack": "topik-i-mini-pack", "count": 3})
        activity = view["id"]
        while True:
            status, result = app.handle("POST", f"/api/activity/{activity}/answer",
                                        body={"value": "일부러틀림"})
            if result.get("finished"):
                break
        status, log = app.handle("GET", "/api/practice/log")
        self.assertEqual(status, 200)
        self.assertEqual(log["summary"]["runs"], 1)
        self.assertTrue(log["weak"])

        # The weak list turns back into a drill; vocabulary shows its gloss.
        status, drill = app.handle("POST", "/api/drill/start", body={"mode": "misses"})
        self.assertEqual(status, 200)
        self.assertEqual(drill["label"], "Weak items")
        self.assertIn("Type the Korean:", drill["item"]["show"])

    def test_misses_mode_without_history_is_a_400(self):
        app = self.make_app()
        status, payload = app.handle("POST", "/api/drill/start", body={"mode": "misses"})
        self.assertEqual(status, 400)

    def test_paused_drill_records_partial_run(self):
        app = self.make_app()
        status, view = app.handle("POST", "/api/drill/start", body={"mode": "numbers", "count": 4})
        activity = view["id"]
        item_total = view["progress"][1]
        app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "삼"})
        status, paused = app.handle("POST", f"/api/activity/{activity}/pause")
        self.assertTrue(paused["recorded"])
        status, log = app.handle("GET", "/api/practice/log")
        self.assertEqual(log["runs"][0]["total"], 1)
        self.assertEqual(item_total, 4)

    def test_state_includes_practice_summary(self):
        app = self.make_app()
        status, payload = app.handle("GET", "/api/state")
        self.assertIn("practice", payload)
        self.assertEqual(payload["practice"]["summary"]["runs"], 0)


if __name__ == "__main__":
    unittest.main()
