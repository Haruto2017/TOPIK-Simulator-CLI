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


class Level2EndingTests(unittest.TestCase):
    """Golden battery for the level-2 endings, hand-verified across the verb
    classes. Rows are (word, form_key, gloss, expected)."""

    def check(self, rows):
        from topik_sim.conjugation import conjugate
        for word, form_key, en, expected in rows:
            self.assertEqual(conjugate(word, form_key, en), expected,
                             f"{word} [{form_key}] ({en!r})")

    def test_banmal_is_the_aeo_stem(self):
        self.check([
            ("가다", "banmal", "", "가"), ("먹다", "banmal", "", "먹어"),
            ("춥다", "banmal", "", "추워"), ("하다", "banmal", "", "해"),
            ("듣다", "banmal", "", "들어"), ("살다", "banmal", "", "살아"),
            ("마시다", "banmal", "", "마셔"), ("좋다", "banmal", "", "좋아"),
            ("모르다", "banmal", "", "몰라"), ("공부하다", "banmal", "", "공부해"),
        ])

    def test_quote_statement_action_vs_descriptive(self):
        self.check([
            # action: plain-present quote (는/ㄴ다고)
            ("먹다", "quote_statement", "", "먹는다고 해요"),
            ("가다", "quote_statement", "", "간다고 해요"),
            ("살다", "quote_statement", "", "산다고 해요"),      # ㄹ-drop + ㄴ
            ("하다", "quote_statement", "", "한다고 해요"),
            ("마시다", "quote_statement", "", "마신다고 해요"),
            ("듣다", "quote_statement", "", "듣는다고 해요"),    # bare stem before 는
            ("공부하다", "quote_statement", "", "공부한다고 해요"),
            ("팔다", "quote_statement", "to sell", "판다고 해요"),
            # descriptive and 있다/없다: dictionary-stem quote (다고)
            ("좋다", "quote_statement", "to be good", "좋다고 해요"),
            ("춥다", "quote_statement", "to be cold", "춥다고 해요"),
            ("있다", "quote_statement", "", "있다고 해요"),
            ("맛있다", "quote_statement", "", "맛있다고 해요"),
        ])

    def test_quote_question_attaches_with_l_drop(self):
        self.check([
            ("먹다", "quote_question", "", "먹냐고 해요"),
            ("가다", "quote_question", "", "가냐고 해요"),
            ("살다", "quote_question", "", "사냐고 해요"),       # ㄹ-drop
            ("듣다", "quote_question", "", "듣냐고 해요"),
            ("하다", "quote_question", "", "하냐고 해요"),
            ("좋다", "quote_question", "to be good", "좋냐고 해요"),
            ("춥다", "quote_question", "to be cold", "춥냐고 해요"),
        ])

    def test_quote_command_action_only(self):
        self.check([
            ("먹다", "quote_command", "", "먹으라고 해요"),
            ("가다", "quote_command", "", "가라고 해요"),
            ("살다", "quote_command", "", "살라고 해요"),        # ㄹ kept
            ("듣다", "quote_command", "", "들으라고 해요"),      # ㄷ-irregular 으 stem
            ("하다", "quote_command", "", "하라고 해요"),
            ("마시다", "quote_command", "", "마시라고 해요"),
            ("좋다", "quote_command", "to be good", None),      # descriptive
            ("춥다", "quote_command", "to be cold", None),
        ])

    def test_quote_suggest_action_only(self):
        self.check([
            ("먹다", "quote_suggest", "", "먹자고 해요"),
            ("가다", "quote_suggest", "", "가자고 해요"),
            ("살다", "quote_suggest", "", "살자고 해요"),
            ("듣다", "quote_suggest", "", "듣자고 해요"),
            ("좋다", "quote_suggest", "to be good", None),
        ])

    def test_quote_request_uses_aeo_stem(self):
        self.check([
            ("사다", "quote_request", "", "사 달라고 해요"),
            ("듣다", "quote_request", "", "들어 달라고 해요"),
            ("먹다", "quote_request", "", "먹어 달라고 해요"),
            ("하다", "quote_request", "", "해 달라고 해요"),
            ("가르치다", "quote_request", "to teach", "가르쳐 달라고 해요"),
            ("좋다", "quote_request", "to be good", None),
        ])

    def test_ryeomyeon_uses_eu_stem(self):
        self.check([
            ("먹다", "ryeomyeon", "", "먹으려면"),
            ("가다", "ryeomyeon", "", "가려면"),
            ("살다", "ryeomyeon", "", "살려면"),                # ㄹ kept
            ("듣다", "ryeomyeon", "", "들으려면"),
            ("마시다", "ryeomyeon", "", "마시려면"),
            ("모르다", "ryeomyeon", "to not know", "모르려면"),
        ])

    def test_eulkka_hada_adds_l(self):
        self.check([
            ("먹다", "eulkka_hada", "", "먹을까 해요"),
            ("가다", "eulkka_hada", "", "갈까 해요"),
            ("살다", "eulkka_hada", "", "살까 해요"),
            ("듣다", "eulkka_hada", "", "들을까 해요"),
            ("춥다", "eulkka_hada", "to be cold", None),        # intention: action only
        ])

    def test_nayo_action_only_with_l_drop(self):
        self.check([
            ("먹다", "nayo", "", "먹나요?"),
            ("가다", "nayo", "", "가나요?"),
            ("살다", "nayo", "", "사나요?"),
            ("듣다", "nayo", "", "듣나요?"),
            ("좋다", "nayo", "to be good", None),               # takes -(으)ㄴ가요
        ])

    def test_eotdaga_uses_past_stem(self):
        self.check([
            ("가다", "eotdaga", "", "갔다가"),
            ("먹다", "eotdaga", "", "먹었다가"),
            ("듣다", "eotdaga", "", "들었다가"),
            ("춥다", "eotdaga", "", "추웠다가"),
            ("하다", "eotdaga", "", "했다가"),
        ])

    def test_boida_descriptive_only(self):
        self.check([
            ("좋다", "boida", "to be good", "좋아 보여요"),
            ("맵다", "boida", "to be spicy", "매워 보여요"),
            ("춥다", "boida", "to be cold", "추워 보여요"),
            ("예쁘다", "boida", "to be pretty", "예뻐 보여요"),
            ("먹다", "boida", "", None),                        # action verb
        ])

    def test_gajigo_jimalgo_deogunyo(self):
        self.check([
            ("먹다", "gajigo", "", "먹어 가지고"),
            ("듣다", "gajigo", "", "들어 가지고"),
            ("춥다", "gajigo", "", "추워 가지고"),
            ("먹다", "jimalgo", "", "먹지 말고"),
            ("가다", "jimalgo", "", "가지 말고"),
            ("살다", "jimalgo", "", "살지 말고"),               # bare stem, ㄹ kept
            ("좋다", "jimalgo", "to be good", None),            # prohibition: action only
            ("좋다", "deogunyo", "to be good", "좋더군요"),
            ("먹다", "deogunyo", "", "먹더군요"),
            ("살다", "deogunyo", "", "살더군요"),
            ("춥다", "deogunyo", "", "춥더군요"),
        ])

    def test_deon_and_eot_deon(self):
        self.check([
            ("먹다", "deon", "", "먹던"), ("가다", "deon", "", "가던"),
            ("살다", "deon", "", "살던"), ("듣다", "deon", "", "듣던"),
            ("좋다", "deon", "", "좋던"),
            ("가다", "eot_deon", "", "갔던"), ("먹다", "eot_deon", "", "먹었던"),
            ("듣다", "eot_deon", "", "들었던"), ("춥다", "eot_deon", "", "추웠던"),
            ("살다", "eot_deon", "", "살았던"),
        ])

    def test_eulji_moreu_and_neunji_and_neun_daero(self):
        self.check([
            ("가다", "eulji_moreu", "", "갈지 모르겠어요"),
            ("먹다", "eulji_moreu", "", "먹을지 모르겠어요"),
            ("살다", "eulji_moreu", "", "살지 모르겠어요"),
            ("듣다", "eulji_moreu", "", "들을지 모르겠어요"),
            ("춥다", "eulji_moreu", "", "추울지 모르겠어요"),
            ("먹다", "neunji", "", "먹는지 알아요"),
            ("살다", "neunji", "", "사는지 알아요"),             # ㄹ-drop
            ("가다", "neunji", "", "가는지 알아요"),
            ("듣다", "neunji", "", "듣는지 알아요"),
            ("좋다", "neunji", "to be good", None),             # takes -(으)ㄴ지
            ("먹다", "neun_daero", "", "먹는 대로"),
            ("살다", "neun_daero", "", "사는 대로"),             # ㄹ-drop
            ("듣다", "neun_daero", "", "듣는 대로"),
            ("춥다", "neun_daero", "to be cold", None),
        ])


class VerbKindGatingTests(unittest.TestCase):
    def test_unresolvable_kind_returns_none(self):
        from topik_sim.conjugation import conjugate
        # 팔다 is in no override set: with no gloss, every gated ending declines.
        for key in ("quote_statement", "quote_command", "quote_suggest",
                    "quote_request", "nayo", "neunji", "neun_daero",
                    "ryeomyeon", "eulkka_hada", "jimalgo", "boida"):
            self.assertIsNone(conjugate("팔다", key), key)
        # A gloss resolves it.
        self.assertEqual(conjugate("팔다", "quote_statement", "to sell"), "판다고 해요")
        self.assertEqual(conjugate("팔다", "nayo", "to sell"), "파나요?")

    def test_passive_to_be_gloss_is_not_treated_as_descriptive(self):
        from topik_sim.conjugation import conjugate
        # "to be born" is a passive action verb; the gloss cannot settle the
        # kind, so gated endings decline rather than produce 태어나다고.
        self.assertIsNone(conjugate("태어나다", "quote_statement", "to be born"))
        self.assertIsNone(conjugate("팔리다", "quote_statement", "to be sold"))

    def test_ungated_endings_ignore_the_gloss(self):
        from topik_sim.conjugation import conjugate
        self.assertEqual(conjugate("먹다", "past", "to eat"), "먹었어요")
        self.assertEqual(conjugate("먹다", "past"), "먹었어요")

    def test_copulas_and_non_verbs_conjugate_to_nothing(self):
        from topik_sim.conjugation import conjugate
        for word in ("이다", "아니다", "우산"):
            for key in ("banmal", "quote_statement", "quote_question", "deon",
                        "deogunyo", "eotdaga", "eulji_moreu"):
                self.assertIsNone(conjugate(word, key), f"{word} [{key}]")


class Level2MatchingTests(unittest.TestCase):
    def match(self, pattern):
        spec = match_ending(pattern)
        return spec["key"] if spec else None

    def test_new_patterns_resolve(self):
        self.assertEqual(self.match("반말 -아/어"), "banmal")
        self.assertEqual(self.match("-(느)ㄴ다고 하다"), "quote_statement")
        self.assertEqual(self.match("-다고 하다"), "quote_statement")
        self.assertEqual(self.match("-냐고 하다"), "quote_question")
        self.assertEqual(self.match("-(으)라고 하다"), "quote_command")
        self.assertEqual(self.match("-자고 하다"), "quote_suggest")
        self.assertEqual(self.match("-아/어 달라고 하다"), "quote_request")
        self.assertEqual(self.match("-(으)려면"), "ryeomyeon")
        self.assertEqual(self.match("-(으)ㄹ까 하다"), "eulkka_hada")
        self.assertEqual(self.match("-나요?"), "nayo")
        self.assertEqual(self.match("-았/었다가"), "eotdaga")
        self.assertEqual(self.match("-아/어 보이다"), "boida")
        self.assertEqual(self.match("-아/어 가지고"), "gajigo")
        self.assertEqual(self.match("-지 말고"), "jimalgo")
        self.assertEqual(self.match("-더군요"), "deogunyo")
        self.assertEqual(self.match("-았/었던"), "eot_deon")
        self.assertEqual(self.match("-던"), "deon")
        self.assertEqual(self.match("-(으)ㄹ지 모르겠다"), "eulji_moreu")
        # Documented collapse: a bare -(으)ㄹ지 lesson drills the full
        # -(으)ㄹ지 모르겠어요 form, which fits either lesson.
        self.assertEqual(self.match("-(으)ㄹ지"), "eulji_moreu")
        self.assertEqual(self.match("-는지 알다/모르다"), "neunji")
        self.assertEqual(self.match("-는 대로"), "neun_daero")

    def test_precedence_and_non_collisions(self):
        # Old patterns keep their old endings.
        self.assertEqual(self.match("-(으)면"), "if")
        self.assertEqual(self.match("-지만"), "but")
        self.assertEqual(self.match("-지 않다"), "not")
        self.assertEqual(self.match("-았/었어요"), "past")
        self.assertEqual(self.match("-아/어요"), "aeo")
        # Noun quotation is not a verb ending.
        self.assertIsNone(self.match("N(이)라고 하다"))
        # Bare -(으)ㄹ까요? is a different (unsupported) ending, not ㄹ까 하다.
        self.assertIsNone(self.match("-(으)ㄹ까요?"))
        # Still-unsupported patterns match nothing.
        self.assertIsNone(self.match("주시겠습니까"))
        self.assertIsNone(self.match("N에서"))


class Level2DrillMenuTests(unittest.TestCase):
    def test_menu_contains_new_forms_and_all_endings_are_matchable(self):
        from topik_sim.conjugation import DRILL_FORMS, ENDINGS
        keys = [spec["key"] for spec in DRILL_FORMS]
        for key in ("banmal", "quote_statement", "quote_question", "quote_command",
                    "quote_suggest", "quote_request", "ryeomyeon", "eulkka_hada", "boida"):
            self.assertIn(key, keys)
        self.assertLessEqual(len(DRILL_FORMS), 22)
        # Every new ending is in ENDINGS with match keys for homework/curriculum.
        by_key = {spec["key"]: spec for spec in ENDINGS}
        for key in ("nayo", "eotdaga", "gajigo", "jimalgo", "deogunyo",
                    "deon", "eot_deon", "eulji_moreu", "neunji", "neun_daero"):
            self.assertTrue(by_key[key]["match"], key)

    def test_form_callables_still_accept_a_single_argument(self):
        from topik_sim.conjugation import ENDINGS
        for spec in ENDINGS:
            spec["form"]("먹다")  # must not raise


if __name__ == "__main__":
    unittest.main()
