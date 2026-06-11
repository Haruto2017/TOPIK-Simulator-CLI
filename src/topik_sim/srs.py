from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .attempts import create_attempt, find_question
from .content import ExamPack


SRS_SCHEMA_VERSION = "topik-sim.review.v1"
QUEUE_FILENAME = "review_queue.json"
MAX_BOX = 5
# After a correct answer an item moves up one box and waits this many days.
BOX_INTERVALS_DAYS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 15}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def queue_path_for(attempt_dir: str | Path) -> Path:
    return Path(attempt_dir) / QUEUE_FILENAME


def load_queue(path: str | Path) -> dict[str, Any]:
    queue_file = Path(path)
    if not queue_file.exists():
        return {"schema_version": SRS_SCHEMA_VERSION, "items": {}}
    try:
        with queue_file.open("r", encoding="utf-8") as handle:
            queue = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SRS_SCHEMA_VERSION, "items": {}}
    queue.setdefault("items", {})
    return queue


def save_queue(queue: dict[str, Any], path: str | Path) -> Path:
    queue_file = Path(path)
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    with queue_file.open("w", encoding="utf-8") as handle:
        json.dump(queue, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return queue_file


def record_attempt(queue: dict[str, Any], attempt: dict[str, Any], now: datetime | None = None) -> int:
    """Update the Leitner queue from a completed attempt.

    Misses (re)enter box 1 and are due immediately. Correct answers promote
    queued items one box; a correct answer at the top box retires the item.
    Questions answered correctly that were never missed stay out of the queue.
    """
    result = attempt.get("result") or {}
    if attempt.get("status") != "completed" or not result:
        return 0
    current_time = now or utc_now()
    items = queue.setdefault("items", {})
    pack_id = str(attempt.get("pack_id", ""))
    changes = 0

    for item_result in result.get("results", []):
        question_id = str(item_result["question_id"])
        key = f"{pack_id}|{question_id}"
        existing = items.get(key)
        if not item_result.get("correct"):
            entry = existing or {"pack_id": pack_id, "question_id": question_id, "reps": 0, "lapses": 0}
            entry["box"] = 1
            entry["due"] = current_time.isoformat()
            entry["last_result"] = False
            entry["reps"] = int(entry.get("reps", 0)) + 1
            entry["lapses"] = int(entry.get("lapses", 0)) + 1
            items[key] = entry
            changes += 1
        elif existing is not None:
            box = int(existing.get("box", 1)) + 1
            existing["reps"] = int(existing.get("reps", 0)) + 1
            existing["last_result"] = True
            if box > MAX_BOX:
                del items[key]
            else:
                existing["box"] = box
                existing["due"] = (current_time + timedelta(days=BOX_INTERVALS_DAYS[box])).isoformat()
            changes += 1
    return changes


def due_items(queue: dict[str, Any], pack_id: str | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
    current_time = now or utc_now()
    due: list[dict[str, Any]] = []
    for entry in queue.get("items", {}).values():
        if pack_id and entry.get("pack_id") != pack_id:
            continue
        try:
            due_at = datetime.fromisoformat(str(entry.get("due")))
        except ValueError:
            continue
        if due_at <= current_time:
            due.append(entry)
    due.sort(key=lambda entry: str(entry.get("due")))
    return due


def due_counts_by_pack(queue: dict[str, Any], now: datetime | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in due_items(queue, now=now):
        pack_id = str(entry.get("pack_id", "?"))
        counts[pack_id] = counts.get(pack_id, 0) + 1
    return counts


def create_review_attempt(
    pack: ExamPack,
    queue: dict[str, Any],
    limit: int | None = 20,
    now: datetime | None = None,
) -> dict[str, Any]:
    question_ids: list[str] = []
    for entry in due_items(queue, pack_id=pack.pack_id, now=now):
        question_id = str(entry["question_id"])
        try:
            find_question(pack, question_id)
        except ValueError:
            continue
        question_ids.append(question_id)
        if limit is not None and len(question_ids) >= limit:
            break
    if not question_ids:
        raise ValueError(f"No review items are due for {pack.pack_id}.")
    return create_attempt(pack, question_ids=question_ids, activity="review")
