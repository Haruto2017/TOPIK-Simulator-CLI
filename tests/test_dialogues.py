import tempfile
import unittest
from pathlib import Path

from topik_sim.dialogues import (
    accepted_answers,
    is_correct,
    is_learner_turn,
    load_dialogues,
    summarize,
)
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import DIALOGUE_PICK, DIALOGUE_TYPE, IDLE, Shell
from topik_sim.web.app import WebApp

ROOT = Path(__file__).resolve().parents[1]
DIALOGUES = ROOT / "content" / "dialogues"


class DialogueContentTests(unittest.TestCase):
    def test_bundled_dialogues_are_valid(self):
        dialogues = load_dialogues(DIALOGUES)
        self.assertGreaterEqual(len(dialogues), 5)
        for d in dialogues:
            learner = [t for t in d["turns"] if is_learner_turn(t)]
            self.assertTrue(learner, d["id"])
            for turn in learner:
                # every learner turn states an intent, a model line, and variants
                self.assertTrue(turn["en"] and turn["ko"])
                self.assertIn(turn["ko"], accepted_answers(turn))
            # partner turns give Korean + translation but are not learner turns
            partner = [t for t in d["turns"] if not is_learner_turn(t)]
            self.assertTrue(partner, d["id"])

    def test_grading_is_variant_and_punctuation_tolerant(self):
        turn = {"en": "x", "ko": "두 명이에요.", "accepted": ["두 명이에요.", "두 명입니다."]}
        self.assertTrue(is_correct(turn, "두 명이에요"))      # missing period
        self.assertTrue(is_correct(turn, "  두  명입니다. "))  # variant + spacing
        self.assertFalse(is_correct(turn, "세 명이에요"))

    def test_summary_counts_learner_lines(self):
        by_id = {s["id"]: s for s in summarize(DIALOGUES)}
        self.assertIn("restaurant", by_id)
        self.assertGreaterEqual(by_id["restaurant"]["your_lines"], 3)


class StubPrefetcher:
    def warm(self, *a, **k):
        return None

    def close(self):
        return None


class DialogueShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)

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
            dialogues_path=DIALOGUES,
        )
        return shell, output

    def test_run_a_dialogue_and_record_practice(self):
        from topik_sim.practice_log import load_practice_log

        shell, output = self.make_shell()
        shell.handle_line("/dialogue restaurant")
        self.assertEqual(shell.state, DIALOGUE_TYPE)  # partner line auto-played, now our turn
        while shell.state in {DIALOGUE_TYPE, "dialogue_grade"}:
            turn = shell._dialogue["turns"][shell._dialogue_index]
            shell.handle_line(turn["ko"])  # answer each learner line correctly
        self.assertEqual(shell.state, IDLE)
        text = "\n".join(output)
        self.assertIn("Conversation complete", text)
        self.assertIn("3/3", text)
        runs = load_practice_log(self.temp_dir / "attempts")["runs"]
        self.assertEqual(runs[-1]["mode"], "dialogue")
        self.assertEqual(runs[-1]["total"], 3)

    def test_picker_and_unknown_id(self):
        shell, output = self.make_shell()
        shell.handle_line("/dialogue")
        self.assertEqual(shell.state, DIALOGUE_PICK)
        shell.handle_line("2")
        self.assertEqual(shell.state, DIALOGUE_TYPE)
        shell.handle_line("/pause")
        self.assertEqual(shell.state, IDLE)
        output.clear()
        shell.handle_line("/dialogue nope")
        self.assertIn("No conversation", "\n".join(output))

    def test_wrong_line_reveals_model_and_self_grades(self):
        shell, output = self.make_shell()
        shell.handle_line("/dialogue self-intro")
        output.clear()
        shell.handle_line("전혀 아님")
        text = "\n".join(output)
        self.assertIn("Model:", text)
        self.assertEqual(shell.state, "dialogue_grade")
        shell.handle_line("n")  # self-rate wrong → advances
        self.assertNotEqual(shell.state, "dialogue_grade")


class DialogueWebTests(unittest.TestCase):
    def test_dialogues_endpoint_returns_full_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = WebApp(library_dir=Path(tmp) / "library", attempt_dir=Path(tmp) / "attempts",
                         tts_config=TTSConfig(output_dir=Path(tmp) / "audio"), audio_enabled=False)
            status, payload = app.handle("GET", "/api/dialogues")
            self.assertEqual(status, 200)
            self.assertGreaterEqual(len(payload["dialogues"]), 5)
            self.assertIn("turns", payload["dialogues"][0])


if __name__ == "__main__":
    unittest.main()
