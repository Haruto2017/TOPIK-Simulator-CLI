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


if __name__ == "__main__":
    unittest.main()
