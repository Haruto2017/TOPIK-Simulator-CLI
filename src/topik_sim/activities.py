from __future__ import annotations

from typing import Any

from .attempts import create_attempt
from .content import ExamPack


def missed_question_ids(attempt: dict[str, Any]) -> list[str]:
    """Auto-gradable misses; essays pending manual review are not drillable."""
    result = attempt.get("result") or {}
    return [
        item["question_id"]
        for item in result.get("results", [])
        if not item.get("correct") and not item.get("needs_review")
    ]


def create_drill_attempt(pack: ExamPack, source_attempt: dict[str, Any]) -> dict[str, Any]:
    """Build a new attempt covering only the questions missed in a completed attempt."""
    if source_attempt.get("status") != "completed":
        raise ValueError("Drill needs a completed attempt. Resume and finish it first.")
    missed = missed_question_ids(source_attempt)
    if not missed:
        raise ValueError("Nothing to drill: every question in that attempt was answered correctly.")
    attempt = create_attempt(pack, question_ids=missed, activity="drill")
    attempt["source_attempt_id"] = source_attempt.get("attempt_id")
    return attempt
