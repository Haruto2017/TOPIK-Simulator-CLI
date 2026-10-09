import json
import re
import tempfile
import unittest
from pathlib import Path

from topik_sim.lexicon import LEXICON_SCHEMA_VERSION, Lexicon, lexicon_dirs_for, load_lexicon, meaning_line
from topik_sim.tts import TTSConfig
from topik_sim.wordlists import WORDLIST_SCHEMA_VERSION, load_wordlists

ROOT = Path(__file__).resolve().parents[1]


def write_lexicon(directory: Path, name: str, entries: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps({"schema_version": LEXICON_SCHEMA_VERSION, "entries": entries},
                                             ensure_ascii=False), encoding="utf-8")


class LexiconTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.library = self.root / "library"
        write_lexicon(self.root / "lexicon", "a.json", {"학교": {"zh": "学校", "ja": "学校"},
                                                         "쓰다": {"zh": "写", "ja": "書く"}})
        write_lexicon(self.root / "private" / "lexicon", "b.json", {"학교": {"zh": "WRONG", "ja": "WRONG"},
                                                                     "시험": {"zh": "考试", "ja": "試験"}})

    def tearDown(self):
        self._temp.cleanup()

    def test_tracked_lexicon_wins_and_private_fills_in(self):
        entries = load_lexicon(lexicon_dirs_for(self.library))
        self.assertEqual(entries["학교"], {"zh": "学校", "ja": "学校"})
        self.assertEqual(entries["시험"]["ja"], "試験")

    def test_inline_values_override_the_lexicon(self):
        lexicon = Lexicon(self.library)
        self.assertEqual(lexicon.get("쓰다", {"zh": "使用"}), {"zh": "使用", "ja": "書く"})
        self.assertEqual(lexicon.get("없는말"), {})
        cards = lexicon.attach([{"ko": "학교", "en": "school"}, {"ko": "없는말", "en": "x"}])
        self.assertEqual((cards[0]["zh"], cards[0]["ja"]), ("学校", "学校"))
        self.assertNotIn("zh", cards[1])

    def test_only_recall_prompts_are_decorated(self):
        items = Lexicon(self.library).decorate_items([
            {"show": "Type the Korean:  school", "answer": "학교", "accept": ["학교"]},
            {"show": "Type it again:  학교", "answer": "학교", "accept": ["학교"]},
            {"show": "Type the Korean:  exam", "answer": "모르는말", "accept": ["모르는말", "시험"]},
        ])
        self.assertEqual(items[0]["meanings"], {"zh": "学校", "ja": "学校"})
        self.assertNotIn("meanings", items[1])          # copy-typing: the answer is on screen
        self.assertEqual(items[2]["meanings"]["zh"], "考试")  # falls back to an accepted synonym
        self.assertEqual(meaning_line({"zh": "学校", "ja": "学校"}), "中文 学校  ·  日本語 学校")
        self.assertEqual(meaning_line(None), "")

    def test_shell_recall_and_cards_show_meanings(self):
        from topik_sim.ui.shell import Shell
        from topik_sim.ui import ansi

        vocab = self.root / "vocabulary"
        vocab.mkdir()
        (vocab / "w.json").write_text(json.dumps({"schema_version": WORDLIST_SCHEMA_VERSION, "words": [
            {"ko": "학교", "en": "school", "unit": "u1"}]}, ensure_ascii=False), encoding="utf-8")
        ansi.set_color_enabled(False)
        try:
            out = []
            shell = Shell(library_dir=self.library, attempt_dir=self.root / "attempts",
                          tts_config=TTSConfig(output_dir=self.root / "audio"), output=out.append)
            shell.audio_enabled = False
            shell.handle_line("/recall unit:u1 1")
            self.assertTrue(any("中文 学校" in line and "日本語 学校" in line for line in out), out[-4:])
            shell.handle_line("/pause")
            out.clear()
            shell.handle_line("/flashcards unit:u1")
            shell.handle_line("")  # flip
            self.assertTrue(any("日本語 学校" in line for line in out), out[-4:])
        finally:
            ansi.set_color_enabled(None)

    def test_web_deck_and_recall_items_carry_meanings(self):
        from topik_sim.web.app import WebApp

        vocab = self.root / "vocabulary"
        vocab.mkdir(exist_ok=True)
        (vocab / "w.json").write_text(json.dumps({"schema_version": WORDLIST_SCHEMA_VERSION, "words": [
            {"ko": "학교", "en": "school", "unit": "u1"}]}, ensure_ascii=False), encoding="utf-8")
        app = WebApp(library_dir=self.library, attempt_dir=self.root / "attempts",
                     tts_config=TTSConfig(output_dir=self.root / "audio"), audio_enabled=False, seed=0)
        status, deck = app.handle("GET", "/api/deck/flashcards", query={"unit": "u1"})
        self.assertEqual(status, 200)
        self.assertEqual((deck["cards"][0]["zh"], deck["cards"][0]["ja"]), ("学校", "学校"))
        status, view = app.handle("POST", "/api/drill/start", body={"mode": "recall", "unit": "u1", "count": 1})
        self.assertEqual(status, 200)
        self.assertEqual(view["item"]["meanings"], {"zh": "学校", "ja": "学校"})


class BundledCoverageTests(unittest.TestCase):
    """Every word the bundled content can put on a card has 中文 and 日本語.

    New vocabulary must ship with both: add the word to content/lexicon/ (or
    give the wordlist / explanation entry inline ``zh`` and ``ja``).
    """

    def test_every_bundled_word_has_mandarin_and_japanese(self):
        lexicon = Lexicon(ROOT / "content" / "library")
        words = {}
        for entry in load_wordlists([ROOT / "content" / "vocabulary"]):
            words[entry["ko"]] = entry
        for file in sorted((ROOT / "content" / "source").glob("*.json")):
            pack = json.loads(file.read_text(encoding="utf-8"))
            for section in pack.get("sections", []):
                for question in section.get("questions", []):
                    for item in (question.get("explanation") or {}).get("vocabulary", []) or []:
                        if str(item.get("ko", "")).strip():
                            words.setdefault(str(item["ko"]).strip(), item)
        self.assertGreater(len(words), 1500)
        missing = [ko for ko, entry in words.items() if set(lexicon.get(ko, entry)) != {"zh", "ja"}]
        self.assertEqual(missing, [], f"{len(missing)} words lack zh/ja, e.g. {missing[:10]}")
        hangul = [ko for ko in words if re.search(r"[가-힣]", "".join(lexicon.get(ko, words[ko]).values()))]
        self.assertEqual(hangul, [])


if __name__ == "__main__":
    unittest.main()
