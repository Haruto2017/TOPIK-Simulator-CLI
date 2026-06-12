import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.content import load_pack
from topik_sim.grammar import build_grammar_cards, collect_grammar_entries, library_grammar_entries
from topik_sim.library import import_pack
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import FLASH_BACK, FLASH_FRONT, IDLE, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class GrammarDeckTests(unittest.TestCase):
    def test_collect_grammar_entries_dedupes_patterns(self):
        pack = load_pack(SAMPLE_PACK)
        entries = collect_grammar_entries(pack)
        self.assertEqual([entry["pattern"] for entry in entries], ["-습니다", "N에서"])
        self.assertEqual(entries[0]["example"], "날씨가 좋습니다.")
        self.assertIn("location", entries[1]["explanation"])

    def test_library_wide_cards_and_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library_dir = Path(temp_dir) / "library"
            import_pack(SAMPLE_PACK, library_dir)
            entries = library_grammar_entries(library_dir)
            self.assertEqual(len(entries), 2)

            cards = build_grammar_cards(library_dir=library_dir, seed=0)
            self.assertEqual(len(cards), 2)
            self.assertEqual({card["front"] for card in cards}, {"-습니다", "N에서"})
            limited = build_grammar_cards(library_dir=library_dir, seed=0, limit=1)
            self.assertEqual(len(limited), 1)
            self.assertEqual(build_grammar_cards(library_dir=library_dir, seed=0), cards)

    def test_empty_sources_give_no_cards(self):
        self.assertEqual(build_grammar_cards(), [])
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(build_grammar_cards(library_dir=Path(temp_dir) / "nope"), [])


class GrammarShellTests(unittest.TestCase):
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
            flashcard_seed=0,
        )
        return shell, output

    def test_grammar_cards_flip_to_explanation_and_example(self):
        shell, output = self.make_shell()
        shell.handle_line(f"/grammar {SAMPLE_PACK}")
        text = "\n".join(output)
        self.assertIn("Grammar practice", text)
        self.assertIn("2 card(s)", text)
        self.assertEqual(shell.state, FLASH_FRONT)

        output.clear()
        shell.handle_line("")  # flip
        text = "\n".join(output)
        self.assertEqual(shell.state, FLASH_BACK)
        self.assertIn("예: ", text)
        self.assertTrue("Formal polite" in text or "location" in text)

        shell.handle_line("y")
        shell.handle_line("")
        output.clear()
        shell.handle_line("n")
        text = "\n".join(output)
        self.assertIn("Knew 1/2.", text)
        self.assertIn("Review again:", text)
        self.assertEqual(shell.state, IDLE)

    def test_grammar_without_pack_uses_library(self):
        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, output = self.make_shell()
        shell.handle_line("/grammar")
        text = "\n".join(output)
        self.assertIn("every imported pack", text)
        self.assertIn("2 card(s)", text)
        shell.handle_line("/pause")
        self.assertIn("Grammar practice stopped after", "\n".join(output))

    def test_grammar_with_empty_library_reports_gently(self):
        shell, output = self.make_shell()
        shell.handle_line("/grammar")
        self.assertIn("No grammar notes found", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_say_speaks_the_example_sentence(self):
        shell, output = self.make_shell()
        calls = []

        def fake_synthesize(texts, config):
            calls.append(list(texts))
            return []

        with patch("topik_sim.ui.shell.synthesize_many", side_effect=fake_synthesize):
            shell.handle_line(f"/grammar {SAMPLE_PACK}")
            shell.handle_line("/say")
        self.assertEqual(len(calls), 1)
        self.assertIn(calls[0][0], {"날씨가 좋습니다.", "도서관에서 책을 읽습니다."})


if __name__ == "__main__":
    unittest.main()
