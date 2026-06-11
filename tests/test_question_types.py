import json
import unittest
from pathlib import Path

from topik_sim.content import validate_pack_data
from topik_sim.grading import grade_question
from topik_sim.question_types import (
    QuestionTypeSpec,
    get_question_type,
    register_question_type,
    supported_answer_types,
    _REGISTRY,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"
FORMATS_PACK = ROOT / "examples" / "content" / "topik_i_formats_pack.json"


def _pack_with_question(question):
    return {
        "schema_version": "topik-sim.content.v1",
        "pack_id": "test-pack",
        "pack_version": "0.0.1",
        "title": "Test Pack",
        "topik_level": "TOPIK_I",
        "language_pair": "ko-en",
        "source_type": "original",
        "sections": [
            {"section_id": "s1", "title": "Section", "questions": [question]}
        ],
    }


def _question(answer):
    return {
        "question_id": "q-001",
        "order": 1,
        "skill": "reading",
        "prompt": "Prompt",
        "answer": answer,
        "explanation": {"summary": "Because."},
    }


class QuestionTypeRegistryTests(unittest.TestCase):
    def test_builtin_types_are_registered(self):
        self.assertIn("single_choice", supported_answer_types())
        self.assertIn("short_answer", supported_answer_types())

    def test_unknown_type_raises_with_known_types_listed(self):
        with self.assertRaisesRegex(ValueError, "single_choice"):
            get_question_type("essay")

    def test_duplicate_registration_requires_replace(self):
        spec = get_question_type("single_choice")
        with self.assertRaisesRegex(ValueError, "already registered"):
            register_question_type(spec)
        register_question_type(spec, replace=True)

    def test_unsupported_answer_type_fails_validation(self):
        pack = _pack_with_question(_question({"type": "essay"}))
        errors = validate_pack_data(pack)
        self.assertTrue(any("answer.type" in error for error in errors))

    def test_custom_type_extends_validation_and_grading(self):
        spec = QuestionTypeSpec(
            name="exact_match",
            validate=lambda answer, question, path: (
                [] if answer.get("expected") else [f"{path}.answer.expected is required."]
            ),
            grade=lambda question, response: response == str(question["answer"]["expected"]),
        )
        register_question_type(spec)
        try:
            pack = _pack_with_question(_question({"type": "exact_match", "expected": "B"}))
            self.assertEqual(validate_pack_data(pack), [])

            question = _question({"type": "exact_match", "expected": "B"})
            self.assertTrue(grade_question(question, "B")["correct"])
            self.assertFalse(grade_question(question, "A")["correct"])

            bad_pack = _pack_with_question(_question({"type": "exact_match"}))
            errors = validate_pack_data(bad_pack)
            self.assertTrue(any("expected is required" in error for error in errors))
        finally:
            _REGISTRY.pop("exact_match", None)

    def test_sample_pack_still_validates_through_registry(self):
        data = json.loads(SAMPLE_PACK.read_text(encoding="utf-8"))
        self.assertEqual(validate_pack_data(data), [])


class NewFormatTests(unittest.TestCase):
    OPTIONS = [
        {"id": "A", "text": "one"},
        {"id": "B", "text": "two"},
        {"id": "C", "text": "three"},
    ]

    def test_formats_showcase_pack_validates(self):
        data = json.loads(FORMATS_PACK.read_text(encoding="utf-8"))
        self.assertEqual(validate_pack_data(data), [])

    def test_multiple_select_grades_order_insensitively(self):
        question = _question({"type": "multiple_select", "correct_option_ids": ["A", "C"]})
        question["options"] = self.OPTIONS
        self.assertTrue(grade_question(question, "C, a")["correct"])
        self.assertTrue(grade_question(question, "A C")["correct"])
        self.assertFalse(grade_question(question, "A")["correct"])
        self.assertFalse(grade_question(question, "A,B,C")["correct"])
        self.assertFalse(grade_question(question, "")["correct"])

    def test_multiple_select_validation_rejects_unknown_ids(self):
        question = _question({"type": "multiple_select", "correct_option_ids": ["A", "Z"]})
        question["options"] = self.OPTIONS
        errors = validate_pack_data(_pack_with_question(question))
        self.assertTrue(any("unknown option ids" in error for error in errors))

    def test_ordering_grades_exact_sequence(self):
        question = _question({"type": "ordering", "correct_order": ["B", "C", "A"]})
        question["options"] = self.OPTIONS
        self.assertTrue(grade_question(question, "b,c,a")["correct"])
        self.assertTrue(grade_question(question, "B C A")["correct"])
        self.assertFalse(grade_question(question, "A,B,C")["correct"])
        self.assertFalse(grade_question(question, "B,C")["correct"])

    def test_ordering_validation_rejects_repeats(self):
        question = _question({"type": "ordering", "correct_order": ["A", "A", "B"]})
        question["options"] = self.OPTIONS
        errors = validate_pack_data(_pack_with_question(question))
        self.assertTrue(any("repeat" in error for error in errors))

    def test_cloze_grades_each_blank(self):
        question = _question(
            {
                "type": "cloze",
                "blanks": [
                    {"accepted_answers": ["에"]},
                    {"accepted_answers": ["에서", "서"]},
                ],
            }
        )
        self.assertTrue(grade_question(question, "에 / 에서")["correct"])
        self.assertTrue(grade_question(question, "에/서")["correct"])
        self.assertFalse(grade_question(question, "에서 / 에")["correct"])
        self.assertFalse(grade_question(question, "에")["correct"])

    def test_cloze_validation_requires_blanks(self):
        question = _question({"type": "cloze", "blanks": []})
        errors = validate_pack_data(_pack_with_question(question))
        self.assertTrue(any("blanks" in error for error in errors))

    def test_response_format_hints_exist_for_new_types(self):
        from topik_sim.question_types import response_format_hint

        question = _question({"type": "ordering", "correct_order": ["A", "B"]})
        self.assertIn("order", response_format_hint(question))
        self.assertIsNone(response_format_hint(_question({"type": "single_choice", "correct_option_id": "A"})))


if __name__ == "__main__":
    unittest.main()
