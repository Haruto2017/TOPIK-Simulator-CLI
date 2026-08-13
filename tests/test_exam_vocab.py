import json
import tempfile
import unittest
from pathlib import Path

from topik_sim.exam_vocab import (
    inflection_index,
    mine_pack,
    mine_packs,
    pack_text_fragments,
    resolve_token,
)
from topik_sim.wordlists import (
    WORDLIST_SCHEMA_VERSION,
    load_wordlists,
    wordlist_dirs_for,
    wordlist_glosses,
)


def sample_pack():
    return {
        "pack_id": "sample",
        "sections": [
            {
                "section_id": "reading",
                "questions": [
                    {
                        "question_id": "r-001",
                        "prompt": "알맞은 것을 고르십시오.",
                        "passage": "저는 도서관에서 책을 읽었습니다.",
                        "options": [{"id": "1", "text": "친구들과 공부합니다"}],
                    }
                ],
            }
        ],
    }


class TokenNormalizationTests(unittest.TestCase):
    """The extractor never reads meaning — it must still land on real lemmas."""

    def resolve(self, token):
        return resolve_token(token, {}, {})[0]

    def test_particles_are_stripped(self):
        self.assertEqual(self.resolve("책을"), "책")
        self.assertEqual(self.resolve("도서관에서"), "도서관")
        self.assertEqual(self.resolve("친구들과"), "친구")

    def test_hada_verbs_keep_their_hada(self):
        """공부합니다 → 공부하다, never the invented 공부다."""
        for token in ("공부합니다", "공부해요", "공부했습니다", "공부하고"):
            self.assertEqual(self.resolve(token), "공부하다", token)

    def test_copula_reduces_to_the_noun(self):
        self.assertEqual(self.resolve("학생입니다"), "학생")
        self.assertEqual(self.resolve("선생님이에요"), "선생님")

    def test_contracted_past_stems_are_undone(self):
        self.assertEqual(self.resolve("갔습니다"), "가다")
        self.assertEqual(self.resolve("왔어요"), "오다")

    def test_plain_inflections_become_dictionary_forms(self):
        self.assertEqual(self.resolve("좋습니다"), "좋다")
        self.assertEqual(self.resolve("읽었습니다"), "읽다")


class ModifierFormTests(unittest.TestCase):
    """ㄴ/ㄹ modifier forms resolve only against verbs we already know."""

    def test_modifier_resolves_to_a_known_verb(self):
        glosses = {"하다": "to do", "보다": "to see", "만들다": "to make",
                   "특별하다": "to be special"}
        for token, expected in (("할", "하다"), ("본", "보다"),
                                ("만든", "만들다"), ("특별한", "특별하다")):
            lemma, known = resolve_token(token, glosses, {})
            self.assertEqual(lemma, expected, token)
            self.assertTrue(known)

    def test_unknown_modifier_stem_is_not_invented_as_a_verb(self):
        """An unknown 한 must not silently become a fabricated 하다 entry."""
        lemma, known = resolve_token("한", {}, {})
        self.assertFalse(known)
        self.assertNotEqual(lemma, "하다")


class InflectionIndexTests(unittest.TestCase):
    def test_known_verb_resolves_through_generated_forms(self):
        glosses = {"가다": "to go"}
        index = inflection_index(glosses)
        self.assertIn("갑니다", index)
        lemma, known = resolve_token("갑니다", glosses, index)
        self.assertEqual(lemma, "가다")
        self.assertTrue(known)

    def test_unknown_word_is_reported_as_needing_a_gloss(self):
        lemma, known = resolve_token("바다", {}, {})
        self.assertEqual(lemma, "바다")
        self.assertFalse(known)


class MinePackTests(unittest.TestCase):
    def test_fragments_cover_prompt_passage_and_options(self):
        text = " ".join(pack_text_fragments(sample_pack()))
        self.assertIn("고르십시오", text)
        self.assertIn("도서관", text)
        self.assertIn("공부합니다", text)

    def test_mining_splits_known_from_needs_gloss(self):
        result = mine_pack(sample_pack(), {"책": "book", "읽다": "to read"})
        self.assertIn("책", result["known"])
        self.assertIn("읽다", result["known"])
        self.assertIn("도서관", result["needs_gloss"])
        self.assertNotIn("책", result["needs_gloss"])

    def test_mining_records_counts_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            path.write_text(json.dumps(sample_pack(), ensure_ascii=False), encoding="utf-8")
            merged = mine_packs([path], {"책": "book"})
        lemmas = {entry["ko"]: entry for entry in merged["lemmas"]}
        self.assertEqual(lemmas["책"]["packs"], ["sample"])
        self.assertTrue(lemmas["책"]["glossed"])
        self.assertFalse(lemmas["도서관"]["glossed"])
        self.assertEqual(merged["total"], merged["glossed"] + merged["needs_gloss"])

    def test_no_exam_text_leaks_into_the_lemma_list(self):
        """The output must be words only — never a sentence from the pack."""
        merged = mine_packs([], {})
        self.assertEqual(merged["lemmas"], [])
        result = mine_pack(sample_pack(), {})
        for lemma in result["known"] + result["needs_gloss"]:
            self.assertNotIn(" ", lemma)


class PrivateWordlistTests(unittest.TestCase):
    """A private vocabulary dir fills gaps without overriding curated glosses."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.library = root / "library"
        self.library.mkdir()
        (root / "vocabulary").mkdir()
        (root / "private" / "vocabulary").mkdir(parents=True)
        self.bundled = root / "vocabulary" / "core.json"
        self.private = root / "private" / "vocabulary" / "past-papers.json"
        self.bundled.write_text(json.dumps({
            "schema_version": WORDLIST_SCHEMA_VERSION,
            "words": [{"ko": "학교", "en": "school", "unit": "school"}],
        }, ensure_ascii=False), encoding="utf-8")
        self.private.write_text(json.dumps({
            "schema_version": WORDLIST_SCHEMA_VERSION,
            "words": [
                {"ko": "학교", "en": "WRONG", "unit": "past-papers"},
                {"ko": "윗글", "en": "the passage above", "unit": "past-papers"},
            ],
        }, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self._temp.cleanup()

    def test_dirs_are_ordered_bundled_then_private(self):
        dirs = wordlist_dirs_for(self.library)
        self.assertEqual(dirs[0].name, "vocabulary")
        self.assertEqual(dirs[1].parent.name, "private")

    def test_private_entries_load_but_do_not_override(self):
        glosses = wordlist_glosses(wordlist_dirs_for(self.library))
        self.assertEqual(glosses["학교"], "school")        # curated wins
        self.assertEqual(glosses["윗글"], "the passage above")  # private fills the gap

    def test_single_directory_still_accepted(self):
        words = load_wordlists(self.bundled.parent)
        self.assertEqual([w["ko"] for w in words], ["학교"])

    def test_missing_private_dir_is_not_fatal(self):
        import shutil

        shutil.rmtree(self.private.parent)
        self.assertEqual(len(load_wordlists(wordlist_dirs_for(self.library))), 1)



class PackScopedVocabularyTests(unittest.TestCase):
    """A pack that teaches no words is still practisable from its mined list."""

    def setUp(self):
        from topik_sim.library import import_pack

        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.library = root / "library"
        (root / "private" / "vocabulary").mkdir(parents=True)
        (root / "private" / "vocabulary" / "mined.json").write_text(json.dumps({
            "schema_version": WORDLIST_SCHEMA_VERSION,
            "words": [
                {"ko": "사진관", "en": "photo studio", "packs": ["silent-pack"]},
                {"ko": "모래", "en": "sand", "packs": ["silent-pack", "other-pack"]},
                {"ko": "무관", "en": "unrelated word", "packs": ["other-pack"]},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        pack_path = root / "silent.json"
        pack_path.write_text(json.dumps({
            "schema_version": "topik-sim.content.v1",
            "pack_id": "silent-pack", "pack_version": "1.0.0",
            "title": "Silent Pack", "topik_level": "TOPIK_I",
            "language_pair": "ko-ko", "source_type": "user_provided",
            "sections": [{
                "section_id": "reading", "title": "읽기",
                "questions": [{
                    "question_id": "r-001", "order": 1, "skill": "reading",
                    "prompt": "고르십시오.", "options": [{"id": "1", "text": "가"}, {"id": "2", "text": "나"}],
                    "answer": {"type": "single_choice", "correct_option_id": "1"},
                    "explanation": {"summary": "No vocabulary is taught here."},
                }],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        import_pack(pack_path, self.library)
        self.pack = __import__("topik_sim.library", fromlist=["load_pack_ref"]).load_pack_ref(
            "silent-pack@1.0.0", self.library)

    def tearDown(self):
        self._temp.cleanup()

    def test_pack_teaches_nothing_on_its_own(self):
        from topik_sim.flashcards import build_deck

        self.assertEqual(build_deck(self.pack, seed=0), [])

    def test_mined_words_are_scoped_to_their_pack(self):
        from topik_sim.flashcards import wordlist_deck

        mine = {c["ko"] for c in wordlist_deck(self.library, "silent-pack")}
        self.assertEqual(mine, {"사진관", "모래"})
        self.assertNotIn("무관", mine)

    def test_recall_falls_back_to_the_mined_list(self):
        from topik_sim.flashcards import build_recall_items

        items = build_recall_items(pack=self.pack, library_dir=self.library, seed=0, count=5)
        self.assertTrue(items)
        self.assertTrue({i["answer"] for i in items} <= {"사진관", "모래"})

    def test_library_deck_includes_wordlist_words(self):
        from topik_sim.flashcards import library_deck

        self.assertIn("무관", {c["ko"] for c in library_deck(self.library)})

if __name__ == "__main__":
    unittest.main()
