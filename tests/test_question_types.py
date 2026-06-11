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


if __name__ == "__main__":
    unittest.main()
