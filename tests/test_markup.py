import unittest

from topik_sim.content import validate_pack_data
from topik_sim.markup import markup_errors, plain_underline, strip_markup, underline_spans
from topik_sim.tts import collect_speech_segments
from topik_sim.ui import ansi
from topik_sim.ui.render import question_card


def pack_with(question):
    return {
        "schema_version": "topik-sim.content.v1", "pack_id": "m", "pack_version": "1.0.0", "title": "m",
        "topik_level": "TOPIK_II", "language_pair": "ko-ko", "source_type": "original",
        "sections": [{"section_id": "reading", "title": "읽기", "questions": [question]}],
    }


def question(**overrides):
    base = {
        "question_id": "r-001", "order": 1, "skill": "reading",
        "prompt": "밑줄 친 부분과 의미가 가장 비슷한 것을 고르십시오.",
        "passage": "시험이 시작되자 교실은 <u>숨소리가 들릴 만큼</u> 조용해졌다.",
        "options": [{"id": "1", "text": "들리다가"}, {"id": "2", "text": "들릴 정도로"}],
        "answer": {"type": "single_choice", "correct_option_id": "2"},
        "explanation": {"summary": "만큼 ≈ 정도로."},
    }
    base.update(overrides)
    return base


class MarkupTests(unittest.TestCase):
    def test_spans_strip_and_plain(self):
        text = "교실은 <u>숨소리가 들릴 만큼</u> 조용해졌다."
        self.assertEqual(underline_spans(text),
                         [("교실은 ", False), ("숨소리가 들릴 만큼", True), (" 조용해졌다.", False)])
        self.assertEqual(strip_markup(text), "교실은 숨소리가 들릴 만큼 조용해졌다.")
        self.assertEqual(plain_underline(text), "교실은 _숨소리가 들릴 만큼_ 조용해졌다.")
        self.assertEqual(underline_spans("no markup"), [("no markup", False)])

    def test_unbalanced_tags_are_contract_errors(self):
        self.assertEqual(markup_errors("<u>a</u> <u>b</u>"), [])
        self.assertTrue(markup_errors("<u>a"))
        self.assertTrue(markup_errors("a</u>"))
        self.assertTrue(markup_errors("<u><u>a</u></u>"))
        self.assertEqual(validate_pack_data(pack_with(question())), [])
        errors = validate_pack_data(pack_with(question(passage="교실은 <u>숨소리가 조용해졌다.")))
        self.assertTrue(any("passage" in e and "<u>" in e for e in errors), errors)

    def test_shell_card_underlines_and_speech_strips(self):
        ansi.set_color_enabled(False)
        try:
            card = question_card(1, 1, question(), show_transcript=True)
        finally:
            ansi.set_color_enabled(None)
        self.assertIn("_숨소리가 들릴 만큼_", card)
        self.assertNotIn("<u>", card)
        ansi.set_color_enabled(True)
        try:
            self.assertIn("\x1b[4m숨소리가 들릴 만큼\x1b[24m", question_card(1, 1, question(), show_transcript=True))
        finally:
            ansi.set_color_enabled(None)
        spoken = " ".join(s["text"] for s in collect_speech_segments(question(), include_options=True))
        self.assertNotIn("<u>", spoken)
        self.assertIn("숨소리가 들릴 만큼", spoken)


if __name__ == "__main__":
    unittest.main()
