import unittest

from topik_sim.conjugation import attach, formal_polite, is_conjugatable, match_ending


class FormalPoliteTests(unittest.TestCase):
    def test_consonant_stems_take_seumnida(self):
        self.assertEqual(formal_polite("읽다"), "읽습니다")
        self.assertEqual(formal_polite("좋다"), "좋습니다")
        self.assertEqual(formal_polite("있다"), "있습니다")
        self.assertEqual(formal_polite("듣다"), "듣습니다")  # ㄷ-irregular untouched here
        self.assertEqual(formal_polite("돕다"), "돕습니다")  # ㅂ-irregular untouched here

    def test_vowel_stems_take_b_batchim(self):
        self.assertEqual(formal_polite("가다"), "갑니다")
        self.assertEqual(formal_polite("만나다"), "만납니다")
        self.assertEqual(formal_polite("마시다"), "마십니다")

    def test_rieul_stems_drop_the_rieul(self):
        self.assertEqual(formal_polite("살다"), "삽니다")
        self.assertEqual(formal_polite("알다"), "압니다")
        self.assertEqual(formal_polite("만들다"), "만듭니다")

    def test_non_verbs_return_none(self):
        self.assertIsNone(formal_polite("우산"))
        self.assertIsNone(formal_polite("다"))
        self.assertIsNone(formal_polite("study다"))  # non-Hangul stem


class AttachAndMatchingTests(unittest.TestCase):
    def test_concatenative_endings(self):
        self.assertEqual(attach("먹다", "고 싶어요"), "먹고 싶어요")
        self.assertEqual(attach("읽다", "지 않아요"), "읽지 않아요")
        self.assertIsNone(attach("우산", "고 싶어요"))

    def test_match_ending_finds_supported_patterns(self):
        self.assertEqual(match_ending("-습니다")["key"], "seumnida")
        self.assertEqual(match_ending("V-고 싶다")["key"], "want")
        self.assertEqual(match_ending("-지 않다")["key"], "not")
        self.assertEqual(match_ending("-았/었어요")["key"], "past")
        self.assertEqual(match_ending("-(으)ㄹ 거예요")["key"], "future")
        self.assertEqual(match_ending("-(으)세요")["key"], "honorific")
        self.assertEqual(match_ending("-(으)면")["key"], "if")
        # Noun patterns and non-final forms still match nothing.
        self.assertIsNone(match_ending("N이에요/예요?"))
        self.assertIsNone(match_ending("N에서"))
        self.assertIsNone(match_ending("주시겠습니까"))  # 습니까 is not 습니다

    def test_is_conjugatable_requires_dictionary_form_and_verb_gloss(self):
        self.assertTrue(is_conjugatable("먹다", "to eat"))
        self.assertTrue(is_conjugatable("좋다", "to be good"))
        self.assertFalse(is_conjugatable("우산", "umbrella"))
        self.assertFalse(is_conjugatable("바다", "sea"))  # ends in 다 but not a verb gloss


class BroadEndingTests(unittest.TestCase):
    """The class engine across tense, connectives, and modality — one hand-
    verified value per (verb class, ending), spanning every irregular class."""

    def check(self, rows):
        from topik_sim.conjugation import conjugate
        for word, form_key, expected in rows:
            self.assertEqual(conjugate(word, form_key), expected, f"{word} [{form_key}]")

    def test_past_tense_all_classes(self):
        self.check([
            ("먹다", "past", "먹었어요"), ("가다", "past", "갔어요"), ("하다", "past", "했어요"),
            ("살다", "past", "살았어요"), ("듣다", "past", "들었어요"), ("춥다", "past", "추웠어요"),
            ("짓다", "past", "지었어요"), ("쓰다", "past", "썼어요"), ("모르다", "past", "몰랐어요"),
            ("그렇다", "past", "그랬어요"), ("마시다", "past", "마셨어요"),
            ("먹다", "past_formal", "먹었습니다"), ("가다", "past_formal", "갔습니다"),
        ])

    def test_future_and_can_add_l_with_irregulars(self):
        self.check([
            ("먹다", "future", "먹을 거예요"), ("가다", "future", "갈 거예요"),
            ("살다", "future", "살 거예요"), ("만들다", "future", "만들 거예요"),
            ("듣다", "future", "들을 거예요"), ("춥다", "future", "추울 거예요"),
            ("짓다", "future", "지을 거예요"), ("쓰다", "future", "쓸 거예요"),
            ("먹다", "can", "먹을 수 있어요"), ("듣다", "can", "들을 수 있어요"),
        ])

    def test_eu_family_and_rieul_drop(self):
        self.check([
            ("먹다", "if", "먹으면"), ("가다", "if", "가면"), ("살다", "if", "살면"),
            ("듣다", "if", "들으면"), ("춥다", "if", "추우면"), ("짓다", "if", "지으면"),
            ("그렇다", "if", "그러면"), ("쓰다", "if", "쓰면"),
            ("살다", "because", "사니까"), ("살다", "honorific", "사세요"),
            ("만들다", "honorific", "만드세요"), ("먹다", "honorific", "먹으세요"),
            ("듣다", "honorific", "들으세요"), ("춥다", "honorific", "추우세요"),
        ])

    def test_connectives_and_modals(self):
        self.check([
            ("먹다", "so", "먹어서"), ("가다", "so", "가서"), ("하다", "so", "해서"),
            ("먹다", "must", "먹어야 해요"), ("가다", "must", "가야 해요"),
            ("먹다", "want", "먹고 싶어요"), ("먹다", "not", "먹지 않아요"),
            ("먹다", "progressive", "먹고 있어요"), ("먹다", "but", "먹지만"),
            ("듣다", "want", "듣고 싶어요"),  # bare stem: no ㄷ→ㄹ before 고
        ])

    def test_never_guesses_an_irregular_stem(self):
        from topik_sim.conjugation import conjugate, DRILL_FORMS

        # Copulas conjugate to nothing at all.
        for spec in DRILL_FORMS:
            self.assertIsNone(conjugate("이다", spec["key"]), spec["key"])

        # An unlisted ㅅ/르 irregular: every form built on the 아/어 or 으 stem
        # is declined (never a wrong 긋어요/구르어요) — the engine only offers
        # forms that need no irregular knowledge (formal polite, bare-stem
        # concatenatives), and those are correct.
        stem_dependent = {"aeo", "past", "past_formal", "future", "can",
                          "if", "because", "so", "must", "honorific"}
        for word in ("긋다", "구르다"):
            for key in stem_dependent:
                self.assertIsNone(conjugate(word, key), f"{word} [{key}]")
        self.assertEqual(conjugate("긋다", "seumnida"), "긋습니다")   # safe, correct
        self.assertEqual(conjugate("긋다", "want"), "긋고 싶어요")   # safe, correct


class InformalPoliteTests(unittest.TestCase):
    def check(self, cases):
        from topik_sim.conjugation import informal_polite
        for word, expected in cases.items():
            self.assertEqual(informal_polite(word), expected, word)

    def test_regular_consonant_harmony(self):
        self.check({"먹다": "먹어요", "읽다": "읽어요", "앉다": "앉아요",
                    "살다": "살아요", "놀다": "놀아요", "있다": "있어요",
                    "없다": "없어요", "많다": "많아요"})

    def test_hada_and_vowel_contractions(self):
        self.check({"공부하다": "공부해요", "하다": "해요",
                    "가다": "가요", "오다": "와요", "보다": "봐요", "주다": "줘요",
                    "배우다": "배워요", "마시다": "마셔요", "기다리다": "기다려요",
                    "서다": "서요", "보내다": "보내요", "되다": "돼요",
                    "만나다": "만나요", "쉬다": "쉬어요"})

    def test_b_irregular_and_regular(self):
        self.check({"춥다": "추워요", "덥다": "더워요", "돕다": "도와요",
                    "어렵다": "어려워요", "입다": "입어요", "잡다": "잡아요"})

    def test_d_irregular_and_regular(self):
        self.check({"듣다": "들어요", "걷다": "걸어요", "묻다": "물어요",
                    "닫다": "닫아요", "받다": "받아요", "믿다": "믿어요"})

    def test_s_irregular_and_regular(self):
        self.check({"짓다": "지어요", "낫다": "나아요", "붓다": "부어요",
                    "웃다": "웃어요", "씻다": "씻어요", "벗다": "벗어요"})

    def test_eu_and_reu_irregular(self):
        self.check({"쓰다": "써요", "크다": "커요", "바쁘다": "바빠요",
                    "아프다": "아파요", "예쁘다": "예뻐요",
                    "모르다": "몰라요", "부르다": "불러요", "빠르다": "빨라요",
                    "따르다": "따라요"})  # 으-irregular 르-ending, not ㄹㄹ

    def test_h_irregular_and_regular(self):
        self.check({"그렇다": "그래요", "빨갛다": "빨개요", "어떻다": "어때요",
                    "좋다": "좋아요", "놓다": "놓아요", "넣다": "넣어요"})

    def test_unknown_risky_verbs_and_copulas_return_none(self):
        from topik_sim.conjugation import informal_polite
        for word in ("긋다", "뜯다", "구르다", "이다", "아니다", "우산"):
            self.assertIsNone(informal_polite(word), word)


class ConjugationDrillTests(unittest.TestCase):
    def test_build_items_are_safe_and_deterministic(self):
        import tempfile
        from pathlib import Path
        from topik_sim.conjugation import build_conjugation_items, informal_polite
        from topik_sim.library import import_pack

        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "library"
            import_pack(SAMPLE_PACK := Path(__file__).resolve().parents[1] / "examples" / "content" / "topik_i_mini_pack.json", library)
            # A focused session: every answer is exactly that form's output.
            first = build_conjugation_items(library_dir=library, seed=0, count=5, form_key="aeo")
            second = build_conjugation_items(library_dir=library, seed=0, count=5, form_key="aeo")
            self.assertEqual(first, second)
            for item in first:
                self.assertEqual(item["kind"], "conjugation")
                self.assertEqual(item["accept"], [item["answer"]])
                verb = item["show"].split(":", 1)[1].strip().split(" ")[0]
                self.assertEqual(informal_polite(verb), item["answer"])

    def test_mix_interleaves_endings_and_stays_correct(self):
        import tempfile
        from pathlib import Path

        from topik_sim.conjugation import DRILL_FORMS, build_conjugation_items
        from topik_sim.library import import_pack

        pack_file = Path(__file__).resolve().parents[1] / "examples" / "content" / "topik_i_mini_pack.json"
        displays = {d["display"]: d for d in DRILL_FORMS}
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "library"
            import_pack(pack_file, library)
            items = build_conjugation_items(library_dir=library, seed=0, count=6, form_key="mix")
            for item in items:
                ending = item["show"].split("Conjugate to ", 1)[1].split(":", 1)[0]
                verb = item["show"].split(":", 1)[1].strip().split(" ")[0]
                self.assertIn(ending, displays)
                # the ending named in the prompt really produces the answer
                self.assertEqual(displays[ending]["form"](verb), item["answer"])
            # reproducible under a seed
            self.assertEqual(
                items, build_conjugation_items(library_dir=library, seed=0, count=6, form_key="mix"))


if __name__ == "__main__":
    unittest.main()
