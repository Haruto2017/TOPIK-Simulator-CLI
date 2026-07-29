import json
import tempfile
import unittest
from pathlib import Path

from topik_sim.curriculum import load_curriculum
from topik_sim.flashcards import gloss_map
from topik_sim.library import import_pack
from topik_sim.lookup import search_library
from topik_sim.wordlists import WORDLIST_SCHEMA_VERSION, load_wordlists, wordlist_glosses

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"
BUNDLED_WORDLISTS = ROOT / "content" / "vocabulary"
BUNDLED_CURRICULUM = ROOT / "content" / "curriculum"


def write_wordlist(directory: Path, name: str, words, schema=WORDLIST_SCHEMA_VERSION):
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": schema, "words": words}
    (directory / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.vocab_dir = Path(self._temp.name) / "vocabulary"

    def tearDown(self):
        self._temp.cleanup()

    def test_dedupes_by_ko_and_skips_invalid_entries(self):
        write_wordlist(self.vocab_dir, "a.json", [
            {"ko": "코끼리", "en": "elephant", "unit": "greetings"},
            {"ko": "코끼리", "en": "a different gloss", "unit": "greetings"},  # dup ko
            {"ko": "", "en": "no korean", "unit": "greetings"},  # invalid
            {"ko": "기린", "en": "", "unit": "greetings"},  # invalid
            "not-a-dict",  # invalid
            {"ko": "호랑이", "en": "tiger", "unit": "greetings", "note": "genuinely helpful"},
        ])
        words = load_wordlists(self.vocab_dir)
        self.assertEqual([w["ko"] for w in words], ["코끼리", "호랑이"])
        self.assertEqual(words[0]["en"], "elephant")  # first entry wins

    def test_wrong_schema_and_missing_dir_load_nothing(self):
        write_wordlist(self.vocab_dir, "bad.json", [{"ko": "말", "en": "horse", "unit": "u"}],
                       schema="something-else")
        self.assertEqual(load_wordlists(self.vocab_dir), [])
        self.assertEqual(load_wordlists(self.vocab_dir / "missing"), [])

    def test_glosses_append_note_after_em_dash(self):
        write_wordlist(self.vocab_dir, "a.json", [
            {"ko": "코끼리", "en": "elephant", "unit": "greetings"},
            {"ko": "마리", "en": "counter for animals", "unit": "food", "note": "두 마리"},
        ])
        glosses = wordlist_glosses(self.vocab_dir)
        self.assertEqual(glosses["코끼리"], "elephant")
        self.assertEqual(glosses["마리"], "counter for animals — 두 마리")


class GlossMapMergeTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.library = root / "library"
        import_pack(SAMPLE_PACK, self.library)
        # Wordlists live beside the library, mirroring content/{library,vocabulary}.
        write_wordlist(root / "vocabulary", "level1.json", [
            {"ko": "날씨", "en": "climate (wordlist gloss that must lose)", "unit": "weather"},
            {"ko": "코끼리", "en": "elephant", "unit": "greetings"},
        ])

    def tearDown(self):
        self._temp.cleanup()

    def test_pack_glosses_win_and_wordlist_fills_the_rest(self):
        glosses = gloss_map(library_dir=self.library)
        self.assertIn("weather", glosses["날씨"])  # taught by the mini pack
        self.assertNotIn("climate", glosses["날씨"])  # wordlist loses the conflict
        self.assertEqual(glosses["코끼리"], "elephant")  # wordlist fills the gap

    def test_pack_scoped_gloss_map_ignores_wordlists(self):
        from topik_sim.library import load_pack_ref

        pack = load_pack_ref("topik-i-mini-pack@0.1.0", self.library)
        glosses = gloss_map(pack=pack)
        self.assertNotIn("코끼리", glosses)


class LookupWordlistTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.library = root / "library"
        import_pack(SAMPLE_PACK, self.library)
        write_wordlist(root / "vocabulary", "level1.json", [
            {"ko": "코끼리", "en": "elephant", "unit": "greetings"},
        ])

    def tearDown(self):
        self._temp.cleanup()

    def test_lookup_finds_wordlist_word_with_unit_attribution(self):
        result = search_library("코끼리", self.library)
        self.assertEqual(result["vocabulary"][0]["ko"], "코끼리")
        self.assertEqual(result["vocabulary"][0]["pack_id"], "wordlist:greetings")
        # Pack-taught vocabulary still resolves to its pack.
        by_english = search_library("weather", self.library)
        self.assertEqual(by_english["vocabulary"][0]["pack_id"], "topik-i-mini-pack")


class BundledWordlistTests(unittest.TestCase):
    def test_bundled_wordlists_are_large_unique_and_unit_keyed(self):
        words = load_wordlists(BUNDLED_WORDLISTS)
        self.assertGreaterEqual(len(words), 900)

        # Unique ko across all bundled files, checked against the raw JSON so
        # the loader's dedupe cannot mask an authoring mistake.
        raw_ko = []
        for file in sorted(BUNDLED_WORDLISTS.glob("*.json")):
            data = json.loads(file.read_text(encoding="utf-8"))
            raw_ko.extend(str(entry["ko"]) for entry in data["words"])
        self.assertEqual(len(raw_ko), len(set(raw_ko)), "duplicate ko across bundled wordlists")
        self.assertEqual(len(raw_ko), len(words))

        unit_ids = {unit["id"] for unit in load_curriculum(BUNDLED_CURRICULUM)}
        self.assertTrue(unit_ids)
        for word in words:
            self.assertIn(word["unit"], unit_ids,
                          f"{word['ko']} names unknown curriculum unit {word['unit']!r}")


if __name__ == "__main__":
    unittest.main()
