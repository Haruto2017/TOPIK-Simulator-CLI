from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content import ExamPack
from .grading import grade_answers


ATTEMPT_SCHEMA_VERSION = "topik-sim.attempt.v1"
DEFAULT_ATTEMPT_DIR = Path("data") / "attempts"


def create_attempt(pack: ExamPack, section_id: str | None = None, limit: int | None = None) -> dict[str, Any]:
    questions = pack.questions(section_id=section_id)
    if limit is not None:
        questions = questions[:limit]
    question_ids = [question["question_id"] for question in questions]
    now = utc_now()
    return {
        "schema_version": ATTEMPT_SCHEMA_VERSION,
        "attempt_id": str(uuid.uuid4()),
        "pack_id": pack.pack_id,
        "pack_version": str(pack.data["pack_version"]),
        "section_id": section_id,
        "status": "in_progress",
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
        "question_ids": question_ids,
        "answers": [],
        "result": None,
    }


def answer_question(attempt: dict[str, Any], pack: ExamPack, response: str) -> dict[str, Any]:
    if attempt["status"] == "completed":
        raise ValueError("Cannot answer a completed attempt.")

    answered_ids = {answer["question_id"] for answer in attempt["answers"]}
    next_question_id = None
    for question_id in attempt["question_ids"]:
        if question_id not in answered_ids:
            next_question_id = question_id
            break
    if next_question_id is None:
        raise ValueError("Attempt already has answers for every question.")

    question = find_question(pack, next_question_id)
    attempt = clone_attempt(attempt)
    attempt["answers"].append(
        {
            "question_id": question["question_id"],
            "response": response,
            "answered_at": utc_now(),
        }
    )
    attempt["updated_at"] = utc_now()
    return attempt


def complete_attempt(attempt: dict[str, Any], pack: ExamPack) -> dict[str, Any]:
    attempt = clone_attempt(attempt)
    responses = {answer["question_id"]: answer["response"] for answer in attempt["answers"]}
    result = grade_answers(subset_pack_data(pack, attempt["question_ids"]), responses)
    attempt["result"] = result
    attempt["status"] = "completed"
    attempt["completed_at"] = utc_now()
    attempt["updated_at"] = attempt["completed_at"]
    return attempt


def save_attempt(attempt: dict[str, Any], path: str | Path) -> Path:
    attempt_path = Path(path)
    attempt_path.parent.mkdir(parents=True, exist_ok=True)
    with attempt_path.open("w", encoding="utf-8") as handle:
        json.dump(attempt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return attempt_path


def save_attempt_to_dir(attempt: dict[str, Any], attempt_dir: str | Path = DEFAULT_ATTEMPT_DIR) -> Path:
    return save_attempt(attempt, Path(attempt_dir) / f"{attempt['attempt_id']}.json")


def load_attempt(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_question(pack: ExamPack, question_id: str) -> dict[str, Any]:
    for question in pack.questions():
        if question["question_id"] == question_id:
            return question
    raise ValueError(f"Question {question_id!r} is not in pack {pack.pack_id}.")


def subset_pack_data(pack: ExamPack, question_ids: list[str]) -> dict[str, Any]:
    question_id_set = set(question_ids)
    data = dict(pack.data)
    sections = []
    for section in pack.sections:
        section_copy = dict(section)
        section_copy["questions"] = [question for question in section["questions"] if question["question_id"] in question_id_set]
        if section_copy["questions"]:
            sections.append(section_copy)
    data["sections"] = sections
    return data


def clone_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(attempt, ensure_ascii=False))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

