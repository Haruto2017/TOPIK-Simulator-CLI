from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class QuestionTypeSpec:
    """One answer format the simulator can validate and grade.

    New test formats register a spec instead of editing the validator or
    grader. ``validate`` receives ``(answer, question, path)`` and returns
    contract errors. ``grade`` receives ``(question, normalized_response)``
    and returns correctness.
    """

    name: str
    validate: Callable[[dict[str, Any], dict[str, Any], str], list[str]]
    grade: Callable[[dict[str, Any], str], bool]


_REGISTRY: dict[str, QuestionTypeSpec] = {}


def register_question_type(spec: QuestionTypeSpec, replace: bool = False) -> None:
    if spec.name in _REGISTRY and not replace:
        raise ValueError(f"Question type {spec.name!r} is already registered.")
    _REGISTRY[spec.name] = spec


def get_question_type(name: str) -> QuestionTypeSpec:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unsupported answer type {name!r}. Registered types: {sorted(_REGISTRY)}."
        ) from None


def supported_answer_types() -> set[str]:
    return set(_REGISTRY)


def _validate_single_choice(answer: dict[str, Any], question: dict[str, Any], path: str) -> list[str]:
    options = question.get("options")
    if not isinstance(options, list) or not options:
        return [f"{path}.options must be a non-empty array for single_choice."]
    option_ids = {
        str(option.get("id"))
        for option in options
        if isinstance(option, dict) and option.get("id") is not None
    }
    if answer.get("correct_option_id") not in option_ids:
        return [f"{path}.answer.correct_option_id must match an option id."]
    return []


def _grade_single_choice(question: dict[str, Any], response: str) -> bool:
    return response.upper() == str(question["answer"]["correct_option_id"]).upper()


def _validate_short_answer(answer: dict[str, Any], question: dict[str, Any], path: str) -> list[str]:
    accepted = answer.get("accepted_answers")
    if not isinstance(accepted, list) or not accepted:
        return [f"{path}.answer.accepted_answers must be a non-empty array for short_answer."]
    return []


def _grade_short_answer(question: dict[str, Any], response: str) -> bool:
    accepted = [str(value or "").strip() for value in question["answer"]["accepted_answers"]]
    return response in accepted


register_question_type(
    QuestionTypeSpec(name="single_choice", validate=_validate_single_choice, grade=_grade_single_choice)
)
register_question_type(
    QuestionTypeSpec(name="short_answer", validate=_validate_short_answer, grade=_grade_short_answer)
)
