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

    def test_library_vocabulary_feeds_word_stage_without_pack(self):
        from topik_sim.library import import_pack
        from topik_sim.typing_drill import library_vocabulary

        with tempfile.TemporaryDirectory() as temp_dir:
            library_dir = Path(temp_dir) / "library"
            import_pack(SAMPLE_PACK, library_dir)

            words = library_vocabulary(library_dir)
            vocab = {"오늘", "날씨", "좋다", "도서관", "책", "읽다"}
            self.assertEqual(set(words), vocab)

            items = build_typing_items(seed=0, count=12, library_dir=library_dir)
            self.assertTrue(vocab & set(items))
            first = build_typing_items(seed=0, count=12, library_dir=library_dir)
            self.assertEqual(items, first)

    def test_empty_library_falls_back_to_syllables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            items = build_typing_items(seed=0, count=9, library_dir=Path(temp_dir) / "nope")
            self.assertEqual(len(items), 9)  # no crash, random-syllable words instead

    def test_normalize_typed_handles_nfd_input(self):
        composed = "한"
        decomposed = "한"  # NFD jamo sequence
        self.assertEqual(normalize_typed(decomposed), composed)


class AdvancedTypingTests(unittest.TestCase):
    def test_normalize_typed_is_tolerant_of_spacing_and_punctuation(self):
        self.assertEqual(normalize_typed("  안녕하세요. "), "안녕하세요")
        self.assertEqual(normalize_typed("저는  학교에   가요"), "저는 학교에 가요")

    def test_advanced_items_are_words_and_sentences_with_meaning(self):
        import json

        from topik_sim.typing_drill import build_advanced_typing_items

        pack = load_pack(SAMPLE_PACK)
        with tempfile.TemporaryDirectory() as d:
            compose = Path(d) / "c.json"
            compose.write_text(json.dumps({"schema_version": "topik-sim.compose.v1", "lessons": [
                {"id": "l1", "pattern": "-go",
                 "sentences": [{"english": "I want to go.", "korean": "가고 싶어요.", "accepted": ["가고 싶어요."]}]}
            ]}, ensure_ascii=False), encoding="utf-8")
            items = build_advanced_typing_items(pack=pack, compose_path=compose, count=20, seed=0)

        self.assertEqual({i["kind"] for i in items}, {"word", "sentence"})  # no jamo/syllables
        self.assertTrue(all(i["meaning"] for i in items))
        sentence = next(i for i in items if i["kind"] == "sentence")
        self.assertEqual(sentence["show"], "가고 싶어요.")
        self.assertEqual(sentence["meaning"], "I want to go.")
        self.assertTrue(next(i for i in items if i["kind"] == "word")["meaning"])


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
        answers = [item["answer"] for item in shell._typing_items]

        shell.handle_line(answers[0])        # correct
        shell.handle_line("틀림")             # wrong on purpose
        shell.handle_line(answers[2])        # correct
        text = "\n".join(output)
        self.assertIn("✓", text)
        self.assertIn(f"✗ {answers[1]}", text)
        self.assertIn("Keys:", text)
        self.assertIn("Typed 2/3 correctly.", text)
        self.assertIn("Practice again:", text)
        self.assertEqual(shell.state, IDLE)

    def test_typing_without_pack_uses_library_words(self):
        from topik_sim.library import import_pack

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, output = self.make_shell()
        shell.handle_line("/typing 12")
        vocab = {"오늘", "날씨", "좋다", "도서관", "책", "읽다"}
        self.assertTrue(vocab & {item["answer"] for item in shell._typing_items})
        shell.handle_line("/pause")

    def test_typing_reveals_meaning_for_pack_words(self):
        from topik_sim.library import import_pack

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, output = self.make_shell()
        shell.handle_line("/typing 12")
        glosses = {
            "책": "book", "좋다": "to be good", "날씨": "weather",
            "오늘": "today", "도서관": "library", "읽다": "to read",
        }
        # Answer every item; only real pack words carry a meaning, and it matches
        # the pack gloss. Invented jamo/syllables have no meaning attached.
        seen_meaning = False
        while shell.state == TYPING:
            item = shell._typing_items[shell._typing_index]
            self.assertEqual("meaning" in item, item["answer"] in glosses)
            if "meaning" in item:
                self.assertEqual(item["meaning"], glosses[item["answer"]])
                seen_meaning = True
            shell.handle_line(item["answer"])
        self.assertTrue(seen_meaning)
        self.assertIn("today", "\n".join(output))

    def test_typing_pause_stops_early(self):
        shell, output = self.make_shell()
        shell.handle_line("/typing 4")
        shell.handle_line("/pause")
        self.assertIn("stopped after 0/4", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_advanced_typing_drills_meaningful_items_and_shows_meaning(self):
        import json

        from topik_sim.library import import_pack

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        compose = self.temp_dir / "compose"
        compose.mkdir()
        (compose / "c.json").write_text(json.dumps({"schema_version": "topik-sim.compose.v1", "lessons": [
            {"id": "l1", "pattern": "-go",
             "sentences": [{"english": "I want to go.", "korean": "가고 싶어요.", "accepted": ["가고 싶어요."]}]}
        ]}, ensure_ascii=False), encoding="utf-8")
        shell, output = self.make_shell()
        shell.compose_path = compose

        shell.handle_line("/typing advanced 20")
        self.assertEqual(shell.state, TYPING)
        self.assertTrue(shell._typing_items)
        self.assertTrue(all(item.get("meaning") for item in shell._typing_items))

        # Type the sentence WITHOUT its trailing period — still correct — and the meaning is shown.
        sentence = next(i for i in shell._typing_items if i.get("kind") == "sentence")
        order = [i["answer"] for i in shell._typing_items]
        # answer items up to and including the sentence
        seen_meaning = False
        for answer in order:
            before = len(output)
            typed = answer.rstrip(".") if answer == sentence["answer"] else answer
            shell.handle_line(typed)
            chunk = "\n".join(output[before:])
            if answer == sentence["answer"]:
                self.assertIn("✓", chunk)
                self.assertIn("I want to go.", chunk)
                seen_meaning = True
                break
        self.assertTrue(seen_meaning)

    def test_advanced_typing_without_content_reports(self):
        shell, output = self.make_shell()
        shell.compose_path = self.temp_dir / "no-compose"
        shell.handle_line("/typing advanced")
        self.assertIn("No words or sentences available", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_keyboard_command_chart_and_toggle(self):
        shell, output = self.make_shell()
        shell.handle_line("/keyboard")
        self.assertIn("두벌식", "\n".join(output))
        self.assertFalse(shell.keyboard_hints)

        shell.handle_line("/keyboard on")
        self.assertTrue(shell.keyboard_hints)
        self.assertTrue(shell.keyboard_pinned)
        shell.handle_line("/keyboard off")
        self.assertFalse(shell.keyboard_hints)
        self.assertFalse(shell.keyboard_pinned)

    def test_pinned_keyboard_hovers_in_status_toolbar(self):
        shell, _ = self.make_shell()
        self.assertNotIn("\n", shell.status_line())

        shell.handle_line("/keyboard pin")
        self.assertTrue(shell.keyboard_pinned)
        self.assertFalse(shell.keyboard_hints)  # pin alone does not enable hints
        toolbar = shell.status_line()
        lines = toolbar.split("\n")
        self.assertGreaterEqual(len(lines), 4)
        self.assertIn("ㅂq", toolbar)
        self.assertIn("⇧", toolbar)
        self.assertIn("idle", lines[-1])  # status line stays at the bottom

        shell.handle_line("/keyboard unpin")
        self.assertNotIn("\n", shell.status_line())

    def test_pinned_toolbar_carries_no_ansi_codes(self):
        from topik_sim.ui.render import keyboard_toolbar

        ansi.set_color_enabled(True)
        try:
            self.assertNotIn("\x1b", keyboard_toolbar())
        finally:
            ansi.set_color_enabled(False)

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
