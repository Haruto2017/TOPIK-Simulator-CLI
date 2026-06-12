from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from .question_types import get_question_type, supported_answer_types


SCHEMA_VERSION = "topik-sim.content.v1"
SUPPORTED_LEVELS = {"TOPIK_I", "TOPIK_II"}
SUPPORTED_SOURCE_TYPES = {"original", "licensed", "public_domain", "user_provided"}


class ContentValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class ExamPack:
    path: Path
    data: dict[str, Any]

    @property
    def pack_id(self) -> str:
        return str(self.data["pack_id"])

    @property
    def title(self) -> str:
        return str(self.data["title"])

    @property
    def sections(self) -> list[dict[str, Any]]:
        return list(self.data["sections"])

    # cached_property writes straight into __dict__, so it works on a frozen
    # dataclass; pack data is immutable after load.
    @cached_property
    def _questions_sorted(self) -> list[dict[str, Any]]:
        questions = [question for section in self.sections for question in section["questions"]]
        return sorted(questions, key=lambda item: int(item.get("order", 0)))

    @cached_property
    def _questions_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(question["question_id"]): question for question in self._questions_sorted}

    def questions(self, section_id: str | None = None) -> list[dict[str, Any]]:
        if section_id is None:
            return list(self._questions_sorted)
        questions: list[dict[str, Any]] = []
        for section in self.sections:
            if section["section_id"] != section_id:
                continue
            questions.extend(section["questions"])
        return sorted(questions, key=lambda item: int(item.get("order", 0)))

    def question(self, question_id: str) -> dict[str, Any]:
        try:
            return self._questions_by_id[str(question_id)]
        except KeyError:
            raise ValueError(f"Question {question_id!r} is not in pack {self.pack_id}.") from None


def load_pack(path: str | Path) -> ExamPack:
    pack_path = Path(path)
    with pack_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    errors = validate_pack_data(data)
    if errors:
        raise ContentValidationError(errors)
    return ExamPack(path=pack_path, data=data)


def validate_pack_file(path: str | Path) -> list[str]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]
    except OSError as exc:
        return [f"Could not read file: {exc}"]

    return validate_pack_data(data)


def validate_pack_data(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Pack root must be a JSON object."]

    _require_fields(data, ["schema_version", "pack_id", "pack_version", "title", "topik_level", "language_pair", "source_type", "sections"], "pack", errors)

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"pack.schema_version must be {SCHEMA_VERSION!r}.")
    if data.get("topik_level") not in SUPPORTED_LEVELS:
        errors.append("pack.topik_level must be TOPIK_I or TOPIK_II.")
    if data.get("source_type") not in SUPPORTED_SOURCE_TYPES:
        errors.append("pack.source_type must be original, licensed, public_domain, or user_provided.")
    if not str(data.get("pack_version", "")).strip():
        errors.append("pack.pack_version is required.")
    if not isinstance(data.get("sections"), list) or not data.get("sections"):
        errors.append("pack.sections must be a non-empty array.")
        return errors

    seen_question_ids: set[str] = set()
    for section_index, section in enumerate(data["sections"]):
        section_path = f"sections[{section_index}]"
        if not isinstance(section, dict):
            errors.append(f"{section_path} must be an object.")
            continue

        _require_fields(section, ["section_id", "title", "questions"], section_path, errors)
        if not isinstance(section.get("questions"), list) or not section.get("questions"):
            errors.append(f"{section_path}.questions must be a non-empty array.")
            continue

        for question_index, question in enumerate(section["questions"]):
            question_path = f"{section_path}.questions[{question_index}]"
            _validate_question(question, question_path, seen_question_ids, errors)

    return errors


def _validate_question(question: Any, path: str, seen_question_ids: set[str], errors: list[str]) -> None:
    if not isinstance(question, dict):
        errors.append(f"{path} must be an object.")
        return

    _require_fields(question, ["question_id", "order", "skill", "prompt", "answer", "explanation"], path, errors)

    question_id = question.get("question_id")
    if isinstance(question_id, str):
        if question_id in seen_question_ids:
            errors.append(f"{path}.question_id {question_id!r} is duplicated.")
        seen_question_ids.add(question_id)

    answer = question.get("answer")
    if not isinstance(answer, dict):
        errors.append(f"{path}.answer must be an object.")
        return

    answer_type = answer.get("type")
    if answer_type not in supported_answer_types():
        errors.append(f"{path}.answer.type must be one of {sorted(supported_answer_types())}.")
        return

    errors.extend(get_question_type(answer_type).validate(answer, question, path))

    explanation = question.get("explanation")
    if not isinstance(explanation, dict):
        errors.append(f"{path}.explanation must be an object.")
    elif not str(explanation.get("summary", "")).strip():
        errors.append(f"{path}.explanation.summary is required.")


def _require_fields(data: dict[str, Any], fields: list[str], path: str, errors: list[str]) -> None:
    for field in fields:
        if field not in data:
            errors.append(f"{path}.{field} is required.")
