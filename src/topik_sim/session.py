from __future__ import annotations

from pathlib import Path
from typing import Any

from .attempts import (
    answer_question,
    attempt_progress,
    complete_attempt,
    create_attempt,
    find_question,
    load_attempt,
    remaining_question_ids,
    save_attempt,
    save_attempt_to_dir,
)
from .content import ExamPack
from .grading import grade_question


class ExamSession:
    """State machine for one attempt, independent of any frontend.

    The plain CLI, the interactive shell, and future UIs all drive the same
    present/submit/advance/finalize cycle. The attempt file is saved after
    every answer, so abandoning a session never loses progress.
    """

    def __init__(self, pack: ExamPack, attempt: dict[str, Any], attempt_path: Path) -> None:
        self.pack = pack
        self.attempt = attempt
        self.attempt_path = Path(attempt_path)

    @classmethod
    def start(
        cls,
        pack: ExamPack,
        attempt_dir: str | Path,
        section_id: str | None = None,
        limit: int | None = None,
        question_ids: list[str] | None = None,
        activity: str = "exam",
    ) -> "ExamSession":
        attempt = create_attempt(
            pack,
            section_id=section_id,
            limit=limit,
            question_ids=question_ids,
            activity=activity,
        )
        if not attempt["question_ids"]:
            raise ValueError("No questions matched this request.")
        attempt_path = save_attempt_to_dir(attempt, attempt_dir)
        return cls(pack, attempt, attempt_path)

    @classmethod
    def resume(cls, attempt_path: str | Path, pack: ExamPack) -> "ExamSession":
        attempt = load_attempt(attempt_path)
        for question_id in attempt.get("question_ids", []):
            find_question(pack, question_id)
        return cls(pack, attempt, Path(attempt_path))

    @property
    def is_completed(self) -> bool:
        return self.attempt.get("status") == "completed"

    @property
    def activity(self) -> str:
        return str(self.attempt.get("activity", "exam"))

    def progress(self) -> tuple[int, int]:
        return attempt_progress(self.attempt)

    def question_number(self) -> int:
        answered, _ = self.progress()
        return answered + 1

    def current_question(self) -> dict[str, Any] | None:
        remaining = remaining_question_ids(self.attempt)
        if not remaining:
            return None
        return find_question(self.pack, remaining[0])

    def next_question(self) -> dict[str, Any] | None:
        """The question after the current one; used to prefetch its audio."""
        remaining = remaining_question_ids(self.attempt)
        if len(remaining) < 2:
            return None
        return find_question(self.pack, remaining[1])

    def has_remaining(self) -> bool:
        return bool(remaining_question_ids(self.attempt))

    def submit(self, response: str) -> dict[str, Any]:
        question = self.current_question()
        if question is None:
            raise ValueError("No question is awaiting an answer.")
        self.attempt = answer_question(self.attempt, self.pack, response)
        save_attempt(self.attempt, self.attempt_path)
        return grade_question(question, response)

    def running_score(self) -> tuple[int, int]:
        """Points earned and points available over the questions answered so far."""
        earned = 0
        available = 0
        for answer in self.attempt.get("answers", []):
            question = find_question(self.pack, answer["question_id"])
            result = grade_question(question, answer.get("response", ""))
            earned += result["points_awarded"]
            available += result["max_points"]
        return earned, available

    def finalize(self) -> dict[str, Any]:
        self.attempt = complete_attempt(self.attempt, self.pack)
        save_attempt(self.attempt, self.attempt_path)
        return self.attempt
