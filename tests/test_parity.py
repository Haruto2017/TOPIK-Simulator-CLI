import tempfile
import unittest
from pathlib import Path

from topik_sim.library import import_pack, latest_packs
from topik_sim.practice_log import build_misses_items, record_practice
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import IDLE, TYPING, Shell
from topik_sim.web.app import WebApp

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class StubPrefetcher:
    def warm(self, *args, **kwargs):
        return None

    def close(self):
        return None


class MissesParityTests(unittest.TestCase):
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
            audio_enabled=False,
            flashcard_seed=0,
        )
        return shell, output

    def test_shared_builder_asks_vocabulary_from_its_gloss(self):
        record_practice(self.temp_dir / "attempts", "recall", "Vocab recall", 0, 2,
                        missed=["날씨", "삼백사십칠"])
        items = build_misses_items(self.temp_dir / "attempts", self.temp_dir / "library")
        shows = {item["answer"]: item["show"] for item in items}
        self.assertIn("weather", shows["날씨"])          # known vocab → production
        self.assertIn("Type it again", shows["삼백사십칠"])  # unknown → retype

    def test_shell_misses_drills_and_logs(self):
        record_practice(self.temp_dir / "attempts", "recall", "Vocab recall", 0, 1, missed=["날씨"])
        shell, output = self.make_shell()
        shell.handle_line("/misses")
        self.assertEqual(shell.state, TYPING)
        self.assertIn("weather", "\n".join(output))
        shell.handle_line("날씨")
        self.assertEqual(shell.state, IDLE)
        self.assertIn("Cleared 1/1", "\n".join(output))

    def test_shell_misses_without_history_explains(self):
        shell, output = self.make_shell()
        shell.handle_line("/misses")
        self.assertIn("No missed items recorded yet", "\n".join(output))
        self.assertEqual(shell.state, IDLE)


class WebParityTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def make_app(self, with_pack=True, **kwargs):
        if with_pack:
            import_pack(SAMPLE_PACK, self.temp_dir / "library")
        kwargs.setdefault("audio_enabled", False)
        return WebApp(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            seed=0, **kwargs,
        )

    def test_advanced_typing_reaches_the_web(self):
        app = self.make_app()
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "typing", "advanced": True, "count": 4})
        self.assertEqual(status, 200)
        self.assertEqual(view["label"], "Advanced typing")
        # Every advanced item is a real word or sentence with a meaning reveal.
        activity = view["id"]
        status, result = app.handle("POST", f"/api/activity/{activity}/answer",
                                    body={"value": view["item"]["show"]})
        self.assertTrue(result["correct"])
        self.assertTrue(result.get("meaning"))

    def test_visible_answer_audio_is_not_treated_as_a_spoiler(self):
        def synth(text, config):
            path = self.temp_dir / "fake.wav"
            path.write_bytes(b"RIFFfake")
            return path

        app = self.make_app(audio_enabled=True, synthesizer=synth)
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "typing", "pack": "topik-i-mini-pack", "count": 4})
        self.assertTrue(view["item"]["audio"])  # copy-typing: the answer is on screen

    def test_setup_endpoint_imports_the_bundled_packs(self):
        app = self.make_app(with_pack=False)
        self.assertEqual(app.handle("GET", "/api/packs")[1]["packs"], [])
        status, result = app.handle("POST", "/api/setup")
        self.assertEqual(status, 200)
        self.assertGreater(len(result["imported"]), 0)
        self.assertEqual(result["failed"], [])
        self.assertEqual(len(latest_packs(self.temp_dir / "library")), len(result["imported"]))
        # Idempotent, exactly like the CLI setup command.
        status, again = app.handle("POST", "/api/setup")
        self.assertEqual(again["imported"], [])
        self.assertGreater(len(again["skipped"]), 0)


if __name__ == "__main__":
    unittest.main()
