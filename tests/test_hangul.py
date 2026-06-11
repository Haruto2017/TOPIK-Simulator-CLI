import tempfile
import unittest
from pathlib import Path

from topik_sim.content import load_pack
from topik_sim.hangul import (
    compose_syllable,
    decompose_syllable,
    keystroke_hint,
    keystrokes,
    uses_shift,
)
from topik_sim.typing_drill import build_typing_items, normalize_typed
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.render import keyboard_chart
from topik_sim.ui.shell import IDLE, TYPING, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class HangulTests(unittest.TestCase):
    def test_decompose_and_compose_round_trip(self):
        self.assertEqual(decompose_syllable("한"), ("ㅎ", "ㅏ", "ㄴ"))
        self.assertEqual(decompose_syllable("가"), ("ㄱ", "ㅏ", ""))
        self.assertIsNone(decompose_syllable("a"))
        self.assertEqual(compose_syllable("ㅎ", "ㅏ", "ㄴ"), "한")

    def test_keystrokes_match_dubeolsik(self):
        # The famous one: 안녕하세요 typed on QWERTY is dkssudgktpdy.
        self.assertEqual(keystrokes("안녕하세요").replace("·", ""), "dkssudgktpdy")
        self.assertEqual(keystrokes("날씨"), "skf·Tl")
        self.assertEqual(keystrokes("의"), "dml")        # compound vowel ㅢ = m+l
        self.assertEqual(keystrokes("과"), "rhk")        # compound vowel ㅘ = h+k
        self.assertEqual(keystrokes("닭"), "ekfr")       # compound tail ㄺ = f+r
        self.assertEqual(keystrokes("ㄲ"), "R")          # bare jamo, shifted

    def test_non_hangul_passes_through(self):
        self.assertEqual(keystrokes("abc 123!"), "abc 123!")
        self.assertEqual(keystrokes("날씨 좋다."), "skf·Tl whg·ek.")

    def test_shift_legend_only_when_needed(self):
        self.assertTrue(uses_shift(keystrokes("씨")))
        self.assertFalse(uses_shift(keystrokes("하나")))
        self.assertIn("(uppercase = Shift)", keystroke_hint("씨"))
        self.assertNotIn("Shift", keystroke_hint("하나"))

    def test_keyboard_chart_lists_layout(self):
        ansi.set_color_enabled(False)
        try:
            chart = keyboard_chart()
        finally:
            ansi.set_color_enabled(None)
        self.assertIn("ㅂ", chart)
        self.assertIn("Q", chart)
        self.assertIn("ㅏ", chart)
        self.assertIn("Shift", chart)


class TypingDrillTests(unittest.TestCase):
    def test_items_are_deterministic_and_ramp(self):
        first = build_typing_items(seed=0, count=12)
        second = build_typing_items(seed=0, count=12)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 12)
        # Early items are single jamo, later items are full syllables/words.
        self.assertEqual(len(first[0]), 1)
        self.assertGreaterEqual(len(first[-1]), 2)

    def test_pack_vocabulary_feeds_word_stage(self):
        pack = load_pack(SAMPLE_PACK)
        items = build_typing_items(seed=0, pack=pack, count=12)
        vocab = {"오늘", "날씨", "좋다", "도서관", "책", "읽다"}
        self.assertTrue(vocab & set(items))

    def test_normalize_typed_handles_nfd_input(self):
        composed = "한"
        decomposed = "한"  # NFD jamo sequence
        self.assertEqual(normalize_typed(decomposed), composed)


class TypingShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self, **kwargs):
        output = []
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
            flashcard_seed=0,
            **kwargs,
        )
        return shell, output

    def test_typing_trainer_grades_and_reveals_keys_on_miss(self):
        shell, output = self.make_shell()
        shell.handle_line("/typing 3")
        self.assertEqual(shell.state, TYPING)
        items = list(shell._typing_items)

        shell.handle_line(items[0])          # correct
        shell.handle_line("틀림")             # wrong on purpose
        shell.handle_line(items[2])          # correct
        text = "\n".join(output)
        self.assertIn("✓", text)
        self.assertIn(f"✗ {items[1]}", text)
        self.assertIn("Keys:", text)
        self.assertIn("Typed 2/3 correctly.", text)
        self.assertIn("Practice again:", text)
        self.assertEqual(shell.state, IDLE)

    def test_typing_pause_stops_early(self):
        shell, output = self.make_shell()
        shell.handle_line("/typing 4")
        shell.handle_line("/pause")
        self.assertIn("stopped after 0/4", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_keyboard_command_chart_and_toggle(self):
        shell, output = self.make_shell()
        shell.handle_line("/keyboard")
        self.assertIn("두벌식", "\n".join(output))
        self.assertFalse(shell.keyboard_hints)

        shell.handle_line("/keyboard on")
        self.assertTrue(shell.keyboard_hints)
        shell.handle_line("/keyboard off")
        self.assertFalse(shell.keyboard_hints)

    def test_keyboard_mode_adds_hints_to_flashcards(self):
        shell, output = self.make_shell(keyboard_hints=True)
        shell.handle_line(f"/flashcards {SAMPLE_PACK}")
        shell.handle_line("")  # flip first card
        text = "\n".join(output)
        self.assertIn("Keys:", text)

    def test_keyboard_mode_adds_hints_to_dictation_feedback(self):
        from topik_sim.dictation import feedback_lines

        plain = feedback_lines("날씨", "날시")
        hinted = feedback_lines("날씨", "날시", keyboard_hints=True)
        self.assertFalse(any("Keys:" in line for line in plain))
        self.assertTrue(any("Keys: skf·Tl" in line for line in hinted))


if __name__ == "__main__":
    unittest.main()
