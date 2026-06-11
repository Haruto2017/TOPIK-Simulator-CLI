from __future__ import annotations

import re
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
    # Manual types (essays) cannot be auto-graded: responses score 0 with
    # needs_review=True until `review-writing` records rubric scores.
    manual: bool = False


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


def split_option_ids(response: str) -> list[str]:
    """Parse learner input like "A,C", "a c", or "B/D" into option ids."""
    return [token.upper() for token in re.split(r"[,;/\s]+", response) if token]


def _option_ids(question: dict[str, Any]) -> set[str]:
    return {
        str(option.get("id"))
        for option in question.get("options", [])
        if isinstance(option, dict) and option.get("id") is not None
    }


def _validate_multiple_select(answer: dict[str, Any], question: dict[str, Any], path: str) -> list[str]:
    options = question.get("options")
    if not isinstance(options, list) or not options:
        return [f"{path}.options must be a non-empty array for multiple_select."]
    correct = answer.get("correct_option_ids")
    if not isinstance(correct, list) or not correct:
        return [f"{path}.answer.correct_option_ids must be a non-empty array for multiple_select."]
    known = _option_ids(question)
    missing = [str(item) for item in correct if str(item) not in known]
    if missing:
        return [f"{path}.answer.correct_option_ids contains unknown option ids: {missing}."]
    return []


def _grade_multiple_select(question: dict[str, Any], response: str) -> bool:
    correct = {str(item).upper() for item in question["answer"]["correct_option_ids"]}
    return set(split_option_ids(response)) == correct


def _validate_ordering(answer: dict[str, Any], question: dict[str, Any], path: str) -> list[str]:
    options = question.get("options")
    if not isinstance(options, list) or len(options) < 2:
        return [f"{path}.options must contain at least two entries for ordering."]
    correct = answer.get("correct_order")
    if not isinstance(correct, list) or len(correct) < 2:
        return [f"{path}.answer.correct_order must be an array of at least two option ids."]
    known = _option_ids(question)
    missing = [str(item) for item in correct if str(item) not in known]
    if missing:
        return [f"{path}.answer.correct_order contains unknown option ids: {missing}."]
    if len(set(correct)) != len(correct):
        return [f"{path}.answer.correct_order must not repeat option ids."]
    return []


def _grade_ordering(question: dict[str, Any], response: str) -> bool:
    correct = [str(item).upper() for item in question["answer"]["correct_order"]]
    return split_option_ids(response) == correct


def _validate_cloze(answer: dict[str, Any], question: dict[str, Any], path: str) -> list[str]:
    blanks = answer.get("blanks")
    if not isinstance(blanks, list) or not blanks:
        return [f"{path}.answer.blanks must be a non-empty array for cloze."]
    errors: list[str] = []
    for index, blank in enumerate(blanks):
        accepted = blank.get("accepted_answers") if isinstance(blank, dict) else None
        if not isinstance(accepted, list) or not accepted:
            errors.append(f"{path}.answer.blanks[{index}].accepted_answers must be a non-empty array.")
    return errors


def _grade_cloze(question: dict[str, Any], response: str) -> bool:
    blanks = question["answer"]["blanks"]
    parts = [part.strip() for part in re.split(r"[/;|]", response)]
    parts = [part for part in parts if part]
    if len(parts) != len(blanks):
        return False
    for part, blank in zip(parts, blanks):
        accepted = {str(value or "").strip() for value in blank["accepted_answers"]}
        if part not in accepted:
            return False
    return True


register_question_type(
    QuestionTypeSpec(name="single_choice", validate=_validate_single_choice, grade=_grade_single_choice)
)
register_question_type(
    QuestionTypeSpec(name="short_answer", validate=_validate_short_answer, grade=_grade_short_answer)
)
register_question_type(
    QuestionTypeSpec(name="multiple_select", validate=_validate_multiple_select, grade=_grade_multiple_select)
)
register_question_type(
    QuestionTypeSpec(name="ordering", validate=_validate_ordering, grade=_grade_ordering)
)
register_question_type(
    QuestionTypeSpec(name="cloze", validate=_validate_cloze, grade=_grade_cloze)
)


def _validate_essay(answer: dict[str, Any], question: dict[str, Any], path: str) -> list[str]:
    rubric = answer.get("rubric")
    criteria = rubric.get("criteria") if isinstance(rubric, dict) else None
    if not isinstance(criteria, list) or not criteria:
        return [f"{path}.answer.rubric.criteria must be a non-empty array for essay."]
    errors: list[str] = []
    total = 0
    for index, criterion in enumerate(criteria):
        criterion_path = f"{path}.answer.rubric.criteria[{index}]"
        if not isinstance(criterion, dict) or not str(criterion.get("name", "")).strip():
            errors.append(f"{criterion_path}.name is required.")
            continue
        max_points = criterion.get("max_points")
        if not isinstance(max_points, int) or max_points <= 0:
            errors.append(f"{criterion_path}.max_points must be a positive integer.")
            continue
        total += max_points
    points = question.get("points")
    if not errors and points is not None and int(points) != total:
        errors.append(f"{path}.points ({points}) must equal the rubric total ({total}).")
    return errors


def _grade_essay(question: dict[str, Any], response: str) -> bool:
    return False


register_question_type(
    QuestionTypeSpec(name="essay", validate=_validate_essay, grade=_grade_essay, manual=True)
)


RESPONSE_FORMAT_HINTS = {
    "multiple_select": "Select all that apply, e.g. A,C",
    "ordering": "Answer with the order, e.g. C,A,B",
    "cloze": "Fill the blank(s); separate multiple blanks with /",
    "essay": "Write freely; scored later with review-writing",
}


def response_format_hint(question: dict[str, Any]) -> str | None:
    answer = question.get("answer")
    if not isinstance(answer, dict):
        return None
    return RESPONSE_FORMAT_HINTS.get(str(answer.get("type")))
