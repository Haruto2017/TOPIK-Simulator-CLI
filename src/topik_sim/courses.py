from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content import ExamPack

COURSE_SCHEMA_VERSION = "topik-sim.course.v1"
DEFAULT_COURSES_PATH = Path("content") / "courses"
DEFAULT_MAX_VOCAB = 12
DEFAULT_MAX_GRAMMAR = 3


def load_course_doc(pack_id: str, courses_dir: str | Path = DEFAULT_COURSES_PATH) -> dict[str, Any]:
    path = Path(courses_dir) / f"{pack_id}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def courses_for(pack_id: str, courses_dir: str | Path = DEFAULT_COURSES_PATH) -> list[dict[str, Any]]:
    """The ordered, runnable courses defined for a pack (empty if none)."""
    courses = load_course_doc(pack_id, courses_dir).get("courses")
    if not isinstance(courses, list):
        return []
    valid = [c for c in courses if isinstance(c, dict) and c.get("id") and c.get("question_ids")]
    return sorted(valid, key=lambda c: int(c.get("order", 0)))


def packs_with_courses(pack_ids: list[str], courses_dir: str | Path = DEFAULT_COURSES_PATH) -> set[str]:
    return {pid for pid in pack_ids if courses_for(pid, courses_dir)}


def course_questions(course: dict[str, Any], pack: ExamPack) -> list[dict[str, Any]]:
    questions = []
    for qid in course.get("question_ids", []):
        try:
            questions.append(pack.question(qid))
        except (ValueError, KeyError):
            pass
    return questions


def validate_course_doc(doc: dict[str, Any], pack: ExamPack) -> list[str]:
    """Contract checks for a pack's course file: question ids exist and partition
    the pack, new-item counts stay within limits, and orders are contiguous."""
    errors: list[str] = []
    courses = doc.get("courses")
    if not isinstance(courses, list) or not courses:
        return ["course doc has no courses."]
    limits = doc.get("limits") or {}
    max_vocab = int(limits.get("max_new_vocab", DEFAULT_MAX_VOCAB))
    max_grammar = int(limits.get("max_new_grammar", DEFAULT_MAX_GRAMMAR))

    all_qids = {q["question_id"] for q in pack.questions()}
    seen_q: dict[str, str] = {}
    introduced_vocab: set[str] = set()
    introduced_grammar: set[str] = set()
    orders: list[int] = []

    for course in sorted(courses, key=lambda c: int(c.get("order", 0))):
        cid = str(course.get("id", "?"))
        orders.append(int(course.get("order", 0)))
        vocab = course.get("new_vocabulary") or []
        grammar = course.get("new_grammar") or []
        if len(vocab) > max_vocab:
            errors.append(f"{cid}: {len(vocab)} new vocabulary exceeds limit {max_vocab}.")
        if len(grammar) > max_grammar:
            errors.append(f"{cid}: {len(grammar)} new grammar exceeds limit {max_grammar}.")
        for item in vocab:
            key = str(item.get("ko", "")).strip()
            if key and key in introduced_vocab:
                errors.append(f"{cid}: vocabulary {key!r} was already introduced earlier.")
            introduced_vocab.add(key)
        for item in grammar:
            key = str(item.get("pattern", "")).strip()
            if key and key in introduced_grammar:
                errors.append(f"{cid}: grammar {key!r} was already introduced earlier.")
            introduced_grammar.add(key)
        for qid in course.get("question_ids", []):
            if qid not in all_qids:
                errors.append(f"{cid}: question {qid!r} is not in the pack.")
            elif qid in seen_q:
                errors.append(f"{cid}: question {qid!r} is also in course {seen_q[qid]}.")
            else:
                seen_q[qid] = cid

    uncovered = sorted(all_qids - set(seen_q))
    if uncovered:
        errors.append(f"questions not covered by any course: {uncovered[:8]}{' …' if len(uncovered) > 8 else ''}")
    if sorted(orders) != list(range(1, len(orders) + 1)):
        errors.append(f"course orders must be contiguous 1..{len(orders)}, got {sorted(orders)}.")
    return errors


# --- learner progress ------------------------------------------------------

def progress_path(attempt_dir: str | Path) -> Path:
    return Path(attempt_dir) / "course_progress.json"


def load_progress(attempt_dir: str | Path) -> dict[str, Any]:
    path = progress_path(attempt_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def is_done(progress: dict[str, Any], pack_id: str, course_id: str) -> bool:
    return course_id in (progress.get(pack_id) or {})


def mark_done(attempt_dir: str | Path, pack_id: str, course_id: str) -> None:
    path = progress_path(attempt_dir)
    data = load_progress(attempt_dir)
    data.setdefault(pack_id, {})[course_id] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
