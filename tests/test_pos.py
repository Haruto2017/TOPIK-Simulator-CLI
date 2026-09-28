import json
import tempfile
import unittest
from pathlib import Path

from topik_sim.flashcards import wordlist_deck
from topik_sim.pos import CLASS_LABELS, WORD_CLASSES, class_counts, normalize_class, word_class, words_in_class
from topik_sim.tts import TTSConfig
from topik_sim.ui.shell import Shell
from topik_sim.wordlists import WORDLIST_SCHEMA_VERSION, words_for_class

WORDS = [
    {"ko": "학교", "en": "school", "unit": "u1"},
    {"ko": "고양이", "en": "cat", "unit": "u1"},
    {"ko": "가게", "en": "store, shop", "unit": "u1"},
    {"ko": "캐나다", "en": "Canada", "unit": "u1"},
    {"ko": "필요", "en": "need, necessity", "unit": "u1"},
    {"ko": "가다", "en": "to go", "unit": "u1"},
    {"ko": "공부하다", "en": "to study", "unit": "u1"},
    {"ko": "열리다", "en": "to be opened", "unit": "u1"},
    {"ko": "크다", "en": "to be big", "unit": "u1"},
    {"ko": "맛있다", "en": "to be delicious", "unit": "u1"},
    {"ko": "아니다", "en": "to not be", "unit": "u1"},
    {"ko": "아주", "en": "very", "unit": "u1"},
    {"ko": "열심히", "en": "hard, diligently", "unit": "u1"},
    {"ko": "쉽게", "en": "easily", "unit": "u1"},
    {"ko": "이렇게", "en": "like this, in this way", "unit": "u1"},
    {"ko": "그리고", "en": "and", "unit": "u1"},
    {"ko": "안녕히 가세요", "en": "goodbye", "unit": "u1"},
    {"ko": "글쎄요", "en": "well..., I'm not sure", "unit": "u1"},
]


class WordClassTests(unittest.TestCase):
    """The class comes from the entry's shape and gloss — no hand tagging."""

    def classes(self):
        return {w["ko"]: word_class(w["ko"], w["en"]) for w in WORDS}

    def test_nouns_are_the_default_bucket(self):
        c = self.classes()
        for ko in ("학교", "고양이", "가게", "캐나다", "필요"):
            self.assertEqual(c[ko], "noun", ko)      # -이/-게/-다/-요 shapes alone prove nothing

    def test_verbs_and_adjectives_split_on_the_gloss(self):
        c = self.classes()
        self.assertEqual([c["가다"], c["공부하다"], c["열리다"]], ["verb"] * 3)   # passive stays a verb
        self.assertEqual([c["크다"], c["맛있다"], c["아니다"]], ["adjective"] * 3)

    def test_adverbs_by_list_and_by_shape(self):
        c = self.classes()
        for ko in ("아주", "열심히", "쉽게", "이렇게", "그리고"):
            self.assertEqual(c[ko], "adverb", ko)

    def test_set_phrases_fall_in_no_bucket(self):
        c = self.classes()
        self.assertEqual([c["안녕히 가세요"], c["글쎄요"]], ["other", "other"])

    def test_aliases_and_counts(self):
        self.assertEqual([normalize_class(v) for v in ("adj", "V", "Nouns", "부사", "colour")],
                         ["adjective", "verb", "noun", "adverb", None])
        self.assertEqual(class_counts(WORDS), {"noun": 5, "verb": 3, "adjective": 3, "adverb": 5})
        self.assertEqual({w["ko"] for w in words_in_class(WORDS, "adj")}, {"크다", "맛있다", "아니다"})
        self.assertEqual(words_in_class(WORDS, "nope"), [])
        self.assertEqual(tuple(CLASS_LABELS), WORD_CLASSES)


class WordClassScopeTests(unittest.TestCase):
    """Decks, recall, flashcards and review can all be scoped to one class."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        vocab = self.root / "vocabulary"
        vocab.mkdir()
        (vocab / "words.json").write_text(json.dumps(
            {"schema_version": WORDLIST_SCHEMA_VERSION, "words": WORDS}, ensure_ascii=False), encoding="utf-8")
        self.library = self.root / "library"

    def tearDown(self):
        self._temp.cleanup()

    def make_shell(self):
        output = []
        shell = Shell(library_dir=self.library, attempt_dir=self.root / "attempts",
                      tts_config=TTSConfig(output_dir=self.root / "audio"), output=output.append)
        shell.audio_enabled = False
        return shell, output

    def test_words_for_class_and_deck(self):
        self.assertEqual({w["ko"] for w in words_for_class("verb", self.root / "vocabulary")},
                         {"가다", "공부하다", "열리다"})
        deck = wordlist_deck(self.library, word_class="adverb")
        self.assertEqual({c["ko"] for c in deck}, {"아주", "열심히", "쉽게", "이렇게", "그리고"})
        self.assertEqual(wordlist_deck(self.library, unit="u1", word_class="noun")[0]["ko"], "학교")  # class wins

    def test_shell_recall_and_flashcards_take_pos(self):
        shell, output = self.make_shell()
        shell.handle_line("/recall pos:adj 3")
        self.assertTrue(any("Vocab recall: Adjectives" in line for line in output), output[-5:])
        shell.handle_line("/pause")
        shell, output = self.make_shell()
        shell.handle_line("/flashcards pos:verbs")
        self.assertTrue(any("Flashcards: Verbs" in line for line in output), output[-5:])

    def test_shell_rejects_unknown_class_with_a_menu(self):
        shell, output = self.make_shell()
        shell.handle_line("/recall pos:colour")
        text = "\n".join(output)
        self.assertIn("Unknown part of speech", text)
        self.assertIn("pos:adverb", text)
        self.assertIn("5 words", text)


if __name__ == "__main__":
    unittest.main()
