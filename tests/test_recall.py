import tempfile
import unittest
from pathlib import Path

from topik_sim.content import ExamPack, load_pack
from topik_sim.flashcards import build_recall_items, library_deck
from topik_sim.library import import_pack
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import IDLE, TYPING, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


def _pack_with_vocab(vocab_lists):
    questions = []
    for index, vocabulary in enumerate(vocab_lists, start=1):
        questions.append(
            {
                "question_id": f"q-{index:03d}",
                "order": index,
                "skill": "reading",
                "prompt": "x",
                "answer": {"type": "short_answer", "accepted_answers": ["x"]},
                "explanation": {"summary": "s", "vocabulary": vocabulary},
            }
        )
    data = {
        "schema_version": "topik-sim.content.v1",
        "pack_id": "recall-test",
        "pack_version": "0.0.1",
        "title": "Recall Test",
        "topik_level": "TOPIK_I",
        "language_pair": "ko-en",
        "source_type": "original",
        "sections": [{"section_id": "s", "title": "S", "questions": questions}],
    }
    return ExamPack(path=Path("recall-test.json"), data=data)


class RecallItemTests(unittest.TestCase):
    def test_items_show_english_and_accept_korean(self):
        pack = load_pack(SAMPLE_PACK)
        items = build_recall_items(pack=pack, seed=0, count=10)
        self.assertEqual(len(items), 6)
        by_gloss = {item["show"]: item for item in items}
        self.assertIn("weather", by_gloss)
        self.assertEqual(by_gloss["weather"]["accept"], ["날씨"])
        self.assertEqual(build_recall_items(pack=pack, seed=0, count=10), items)
        self.assertEqual(len(build_recall_items(pack=pack, seed=0, count=3)), 3)

    def test_same_gloss_merges_synonyms(self):
        pack = _pack_with_vocab(
            [
                [{"ko": "도서관", "en": "library"}],
                [{"ko": "서재", "en": "Library"}],
            ]
        )
        items = build_recall_items(pack=pack, seed=0, count=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(set(items[0]["accept"]), {"도서관", "서재"})

    def test_library_wide_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library_dir = Path(temp_dir) / "library"
            import_pack(SAMPLE_PACK, library_dir)
            self.assertEqual(len(library_deck(library_dir)), 6)
            items = build_recall_items(library_dir=library_dir, seed=0, count=4)
            self.assertEqual(len(items), 4)
        self.assertEqual(build_recall_items(), [])


class RecallShellTests(unittest.TestCase):
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

    def test_recall_flow_grades_typed_korean(self):
        shell, output = self.make_shell()
        shell.handle_line(f"/recall {SAMPLE_PACK} 3")
        self.assertEqual(shell.state, TYPING)
        text = "\n".join(output)
        self.assertIn("Vocab recall", text)
        self.assertIn("3 item(s)", text)
        # The prompt is the English gloss, not Korean.
        shown = shell._typing_items[0]["show"]
        self.assertFalse(any("가" <= ch <= "힣" for ch in shown))

        shell.handle_line(shell._typing_items[0]["accept"][0])   # correct
        shell.handle_line("아니요")                                # wrong on purpose
        miss_answer = shell._typing_items[1]["answer"]
        shell.handle_line(shell._typing_items[2]["accept"][0])   # correct
        text = "\n".join(output)
        self.assertIn("✓", text)
        self.assertIn(f"✗ {miss_answer}", text)
        self.assertIn("Keys:", text)
        self.assertIn("Recalled 2/3 correctly.", text)
        self.assertEqual(shell.state, IDLE)

    def test_recall_without_pack_uses_library(self):
        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, output = self.make_shell()
        shell.handle_line("/recall")
        text = "\n".join(output)
        self.assertIn("every imported pack", text)
        self.assertIn("6 item(s)", text)
        shell.handle_line("/pause")
        self.assertIn("Vocab recall stopped after", "\n".join(output))

    def test_recall_with_empty_library_reports_gently(self):
        shell, output = self.make_shell()
        shell.handle_line("/recall")
        self.assertIn("No vocabulary found", "\n".join(output))
        self.assertEqual(shell.state, IDLE)


if __name__ == "__main__":
    unittest.main()
