from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .attempts import load_attempt
from .content import ExamPack, load_pack
from .library import DEFAULT_LIBRARY_DIR, load_pack_ref


def load_completed_attempts(attempt_dir: str | Path) -> list[dict[str, Any]]:
    directory = Path(attempt_dir)
    if not directory.exists():
        return []
    attempts = []
    for path in directory.glob("*.json"):
        try:
            attempt = load_attempt(path)
        except (OSError, json.JSONDecodeError):
            continue
        if attempt.get("status") == "completed" and attempt.get("result"):
            attempts.append(attempt)
    attempts.sort(key=lambda item: str(item.get("completed_at") or ""))
    return attempts


def resolve_attempt_pack(attempt: dict[str, Any], library_dir: str | Path) -> ExamPack | None:
    try:
        return load_pack_ref(f"{attempt['pack_id']}@{attempt['pack_version']}", library_dir)
    except (KeyError, ValueError, OSError):
        pass
    pack_path = attempt.get("pack_path")
    if pack_path and Path(pack_path).exists():
        try:
            return load_pack(pack_path)
        except (ValueError, OSError):
            return None
    return None


def collect_stats(
    attempt_dir: str | Path,
    library_dir: str | Path = DEFAULT_LIBRARY_DIR,
    trend_limit: int = 10,
) -> dict[str, Any]:
    attempts = load_completed_attempts(attempt_dir)
    skills: dict[str, dict[str, float]] = {}
    packs: dict[str, dict[str, Any]] = {}
    trend: list[dict[str, Any]] = []
    skipped = 0
    pack_cache: dict[str, ExamPack | None] = {}

    for attempt in attempts:
        ref = f"{attempt.get('pack_id', '?')}@{attempt.get('pack_version', '?')}"
        if ref not in pack_cache:
            pack_cache[ref] = resolve_attempt_pack(attempt, library_dir)
        pack = pack_cache[ref]
        if pack is None:
            skipped += 1
            continue

        question_skills = {
            question["question_id"]: str(question.get("skill", "unknown"))
            for question in pack.questions()
        }
        durations = {
            answer["question_id"]: answer.get("duration_seconds")
            for answer in attempt.get("answers", [])
        }
        result = attempt["result"]
        for item in result.get("results", []):
            skill = question_skills.get(item["question_id"], "unknown")
            entry = skills.setdefault(skill, {"correct": 0, "total": 0, "seconds": 0.0, "timed": 0})
            entry["total"] += 1
            if item.get("correct"):
                entry["correct"] += 1
            duration = durations.get(item["question_id"])
            if isinstance(duration, (int, float)):
                entry["seconds"] += float(duration)
                entry["timed"] += 1

        score = int(result.get("score", 0))
        max_score = int(result.get("max_score", 0))
        pack_entry = packs.setdefault(ref, {"attempts": 0, "best": (0, 0), "last": (0, 0)})
        pack_entry["attempts"] += 1
        pack_entry["last"] = (score, max_score)
        best_score, best_max = pack_entry["best"]
        if best_max == 0 or (max_score and score / max_score > (best_score / best_max if best_max else 0)):
            pack_entry["best"] = (score, max_score)
        trend.append(
            {
                "completed_at": str(attempt.get("completed_at") or ""),
                "pack_ref": ref,
                "activity": str(attempt.get("activity", "exam")),
                "score": score,
                "max_score": max_score,
            }
        )

    return {
        "attempt_count": len(attempts) - skipped,
        "skills": skills,
        "packs": packs,
        "trend": trend[-trend_limit:],
        "skipped": skipped,
    }


def format_stats(stats: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if stats["attempt_count"] == 0:
        lines.append("No completed attempts yet. Finish a test with take or the shell first.")
        if stats["skipped"]:
            lines.append(f"({stats['skipped']} attempt(s) skipped: their packs could not be loaded.)")
        return lines

    lines.append(f"Completed attempts: {stats['attempt_count']}")
    if stats["skipped"]:
        lines.append(f"Skipped (pack unavailable): {stats['skipped']}")

    lines.append("Skill accuracy:")
    for skill, entry in sorted(stats["skills"].items(), key=lambda item: item[0]):
        total = int(entry["total"])
        correct = int(entry["correct"])
        percent = 100.0 * correct / total if total else 0.0
        pace = ""
        if entry["timed"]:
            pace = f" · avg {entry['seconds'] / entry['timed']:.0f}s/question"
        lines.append(f"  {skill}: {percent:.0f}% ({correct}/{total}){pace}")

    lines.append("Recent attempts:")
    for item in reversed(stats["trend"]):
        when = item["completed_at"][:16].replace("T", " ") or "unknown time"
        lines.append(f"  {when} · {item['pack_ref']} · {item['score']}/{item['max_score']} · {item['activity']}")

    lines.append("Packs:")
    for ref, entry in sorted(stats["packs"].items()):
        best = f"{entry['best'][0]}/{entry['best'][1]}"
        last = f"{entry['last'][0]}/{entry['last'][1]}"
        lines.append(f"  {ref}: {entry['attempts']} attempt(s) · best {best} · last {last}")
    return lines
