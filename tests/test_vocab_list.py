import json
import tempfile
import unittest
from pathlib import Path

from topik_sim.tts import TTSConfig
from topik_sim.vocab_list import render_html, render_text, vocab_listing
from topik_sim.wordlists import WORDLIST_SCHEMA_VERSION, list_word_sets, wordlist_dirs_for


class VocabListTests(unittest.TestCase):
    """Any vocabulary scope can be listed whole and printed."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.library = self.root / "library"
        vocab = self.root / "vocabulary"
        vocab.mkdir()
        (vocab / "w.json").write_text(json.dumps({
            "schema_version": WORDLIST_SCHEMA_VERSION,
            "set": {"id": "media", "title": "Words from <media>"},
            "words": [
                {"ko": "탐내다", "en": "to covet", "zh": "贪图", "ja": "欲しがる", "unit": "u1"},
                {"ko": "가끔", "en": "sometimes", "zh": "偶尔", "ja": "時々", "note": "frequency", "unit": "u1"},
            ]}, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self._temp.cleanup()

    def test_listing_keeps_order_meanings_and_class(self):
        word_set = list_word_sets(wordlist_dirs_for(self.library))[0]
        listing = vocab_listing(self.library, word_set=word_set)
        self.assertEqual(listing["scope"], "set:media")
        self.assertEqual([w["ko"] for w in listing["words"]], ["탐내다", "가끔"])
        self.assertEqual((listing["words"][0]["zh"], listing["words"][1]["pos"]), ("贪图", "adverb"))
        self.assertEqual([w["ko"] for w in vocab_listing(self.library, word_class="adverb")["words"]], ["가끔"])
        self.assertEqual(len(vocab_listing(self.library, unit="u1")["words"]), 2)
        with self.assertRaises(ValueError):
            vocab_listing(self.library)

    def test_renderers(self):
        listing = vocab_listing(self.library, word_set=list_word_sets(wordlist_dirs_for(self.library))[0])
        text = "\n".join(render_text(listing))
        self.assertIn("1. 탐내다", text)
        self.assertIn("中文 偶尔", text)
        self.assertIn("frequency", text)
        page = render_html(listing)
        self.assertIn("Words from &lt;media&gt;", page)        # escaped
        self.assertIn("<td lang=ja>時々</td>", page)
        self.assertIn("@page", page)

    def test_shell_prints_and_saves(self):
        from topik_sim.ui import ansi
        from topik_sim.ui.shell import Shell

        ansi.set_color_enabled(False)
        try:
            out = []
            shell = Shell(library_dir=self.library, attempt_dir=self.root / "data" / "attempts",
                          tts_config=TTSConfig(output_dir=self.root / "audio"), output=out.append)
            shell.handle_line("/wordlist set:media save")
            self.assertTrue(any("2 words" in line for line in out), out)
            saved = self.root / "data" / "exports" / "wordlist-set-media.html"
            self.assertTrue(saved.is_file())
            self.assertIn("欲しがる", saved.read_text(encoding="utf-8"))
            out.clear()
            shell.handle_line("/wordlist pos:adverb")
            self.assertTrue(any("가끔" in line for line in out), out)
        finally:
            ansi.set_color_enabled(None)

    def test_web_endpoint(self):
        from topik_sim.web.app import WebApp

        app = WebApp(library_dir=self.library, attempt_dir=self.root / "attempts",
                     tts_config=TTSConfig(output_dir=self.root / "audio"), audio_enabled=False, seed=0)
        status, listing = app.handle("GET", "/api/vocab/list", query={"set": "media"})
        self.assertEqual((status, len(listing["words"])), (200, 2))
        self.assertEqual(app.handle("GET", "/api/vocab/list", query={"unit": "u1"})[1]["words"][1]["ja"], "時々")
        self.assertEqual(app.handle("GET", "/api/vocab/list")[0], 400)
        self.assertEqual(app.handle("GET", "/api/vocab/list", query={"unit": "nope"})[0], 400)


if __name__ == "__main__":
    unittest.main()
