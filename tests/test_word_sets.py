import json
import tempfile
import unittest
from pathlib import Path

from topik_sim.flashcards import wordlist_deck
from topik_sim.pos import word_class
from topik_sim.tts import TTSConfig
from topik_sim.wordlists import WORDLIST_SCHEMA_VERSION, list_word_sets, load_wordlists, words_for_set


def write(directory: Path, name: str, words, word_set=None):
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": WORDLIST_SCHEMA_VERSION, "words": words}
    if word_set:
        payload["set"] = word_set
    (directory / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class WordSetTests(unittest.TestCase):
    """A personal collection is one practisable set, and its words join the shared pool."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.library = self.root / "library"
        write(self.root / "vocabulary", "level1.json", [{"ko": "외롭다", "en": "to be lonely", "unit": "u1"}])
        write(self.root / "private" / "vocabulary", "media.json", [
            {"ko": "외롭다", "en": "to feel lonely (no one around)", "zh": "孤独", "ja": "寂しい"},
            {"ko": "탐내다", "en": "to covet", "zh": "贪图；眼馋", "ja": "欲しがる"},
            {"ko": "야무지게", "en": "smartly, firmly"},
            {"ko": "조차", "en": "even (particle)"},
            {"ko": "아무 말도 없이", "en": "without a word"},
            {"ko": "탐내다", "en": "duplicate in the same file is ignored"},
        ], word_set={"id": "media", "title": "Words from Korean media"})
        self.dirs = [self.root / "vocabulary", self.root / "private" / "vocabulary"]

    def tearDown(self):
        self._temp.cleanup()

    def test_set_keeps_all_its_words_and_new_words_join_the_pool(self):
        self.assertEqual([(s["id"], s["count"]) for s in list_word_sets(self.dirs)], [("media", 5)])
        in_set = words_for_set("media", self.dirs)
        self.assertEqual([w["ko"] for w in in_set], ["외롭다", "탐내다", "야무지게", "조차", "아무 말도 없이"])
        self.assertEqual(in_set[0]["en"], "to feel lonely (no one around)")  # the set's own gloss
        pool = {w["ko"]: w for w in load_wordlists(self.dirs)}
        self.assertEqual(pool["외롭다"]["en"], "to be lonely")               # bundled gloss wins in the pool
        self.assertIn("탐내다", pool)                                        # new word joins the pool
        verbs = {c["ko"] for c in wordlist_deck(self.library, word_class="verb")}
        self.assertIn("탐내다", verbs)
        deck = wordlist_deck(self.library, word_set="media")
        self.assertEqual(deck[1]["zh"], "贪图；眼馋")                         # inline meanings flow through

    def test_particles_and_non_verb_phrases_are_in_no_class(self):
        self.assertEqual(word_class("조차", "even (particle)"), "other")
        self.assertEqual(word_class("든지", "whether … or"), "other")
        self.assertEqual(word_class("아무 말도 없이", "without a word"), "other")
        self.assertEqual(word_class("비가 그치다", "to stop raining"), "verb")
        self.assertEqual(word_class("인기가 많다", "to be popular"), "adjective")
        self.assertEqual(word_class("야무지게", "smartly, firmly"), "adverb")

    def test_shell_lists_and_drills_a_set(self):
        from topik_sim.ui import ansi
        from topik_sim.ui.shell import Shell

        ansi.set_color_enabled(False)
        try:
            out = []
            shell = Shell(library_dir=self.library, attempt_dir=self.root / "attempts",
                          tts_config=TTSConfig(output_dir=self.root / "audio"), output=out.append)
            shell.audio_enabled = False
            shell.handle_line("/sets")
            self.assertTrue(any("set:media" in line and "5 words" in line for line in out), out)
            out.clear()
            shell.handle_line("/recall set:media 3")
            self.assertTrue(any("Vocab recall: Words from Korean media" in line for line in out), out)
            shell.handle_line("/pause")
            out.clear()
            shell.handle_line("/flashcards set:nope")
            self.assertTrue(any("No word set" in line for line in out) and any("set:media" in line for line in out))
            out.clear()
            shell.handle_line("/flashcards set:media")
            self.assertTrue(any("Flashcards: Words from Korean media" in line for line in out), out)
        finally:
            ansi.set_color_enabled(None)

    def test_web_sets_endpoint_and_scopes(self):
        from topik_sim.web.app import WebApp

        app = WebApp(library_dir=self.library, attempt_dir=self.root / "attempts",
                     tts_config=TTSConfig(output_dir=self.root / "audio"), audio_enabled=False, seed=0)
        status, payload = app.handle("GET", "/api/vocab/sets")
        self.assertEqual((status, payload["sets"][0]["id"], payload["sets"][0]["count"]), (200, "media", 5))
        self.assertNotIn("file", payload["sets"][0])
        status, deck = app.handle("GET", "/api/deck/flashcards", query={"set": "media"})
        self.assertEqual((status, deck["title"], len(deck["cards"])), (200, "Words from Korean media", 5))
        status, view = app.handle("POST", "/api/drill/start", body={"mode": "recall", "set": "media", "count": 5})
        self.assertEqual(status, 200)
        self.assertEqual(len(app._activities[view["id"]]["items"]), 5)
        meanings = {item["answer"]: item.get("meanings") for item in app._activities[view["id"]]["items"]}
        self.assertEqual(meanings["탐내다"], {"zh": "贪图；眼馋", "ja": "欲しがる"})  # inline meanings reach recall
        status, review = app.handle("POST", "/api/drill/start", body={"mode": "vocab", "set": "media"})
        self.assertEqual(status, 200)
        self.assertTrue(any(i.get("meanings") for i in app._activities[review["id"]]["items"]))
        self.assertEqual(app.handle("GET", "/api/deck/flashcards", query={"set": "nope"})[0], 400)


if __name__ == "__main__":
    unittest.main()
