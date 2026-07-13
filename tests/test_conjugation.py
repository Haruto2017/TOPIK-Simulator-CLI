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

    def test_match_ending_finds_supported_patterns_only(self):
        self.assertIsNotNone(match_ending("-습니다"))
        self.assertIsNotNone(match_ending("V-ㅂ니다/습니다"))
        self.assertIsNotNone(match_ending("V-고 싶다"))
        self.assertIsNotNone(match_ending("-지 않다"))
        self.assertIsNone(match_ending("N이에요/예요?"))
        self.assertIsNone(match_ending("N에서"))
        self.assertIsNone(match_ending("-(으)세요"))  # irregular-sensitive: unsupported
        self.assertIsNone(match_ending("주시겠습니까"))  # 습니까 is not 습니다

    def test_is_conjugatable_requires_dictionary_form_and_verb_gloss(self):
        self.assertTrue(is_conjugatable("먹다", "to eat"))
        self.assertTrue(is_conjugatable("좋다", "to be good"))
        self.assertFalse(is_conjugatable("우산", "umbrella"))
        self.assertFalse(is_conjugatable("바다", "sea"))  # ends in 다 but not a verb gloss


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
            first = build_conjugation_items(library_dir=library, seed=0, count=5)
            second = build_conjugation_items(library_dir=library, seed=0, count=5)
            self.assertEqual(first, second)
            for item in first:
                self.assertEqual(item["kind"], "conjugation")
                self.assertEqual(item["accept"], [item["answer"]])
                # every produced answer is exactly what the conjugator returns
                verb = item["show"].split(":", 1)[1].strip().split(" ")[0]
                self.assertEqual(informal_polite(verb), item["answer"])


if __name__ == "__main__":
    unittest.main()
