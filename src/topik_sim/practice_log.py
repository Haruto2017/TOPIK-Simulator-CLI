from __future__ import annotations

"""Practice run log: the record a teacher would keep of daily work.

Exams already persist as attempts, but practice runs (typing, recall,
numbers, dictation, homework) used to vanish when they ended. This log
captures every run — mode, score, and which items were missed — in
``practice_log.json`` next to the attempt files, shared by the shell and
the web UI.

Two consumers:

- Progress views show recent runs, so practice work counts as progress.
- ``weak_items`` aggregates the missed items across recent runs into the
  learner's personal weak list, which the "drill your misses" mode turns
  back into practice. Items stop surfacing once runs stop missing them.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRACTICE_FILE = "practice_log.json"
MAX_RUNS = 200          # the file stays small; old runs age out
MAX_MISSED_PER_RUN = 30
RECENT_RUNS_FOR_WEAKNESS = 50


def practice_log_path(attempt_dir: str | Path) -> Path:
    return Path(attempt_dir) / PRACTICE_FILE


def load_practice_log(attempt_dir: str | Path) -> dict[str, Any]:
    path = practice_log_path(attempt_dir)
    if not path.exists():
        return {"runs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"runs": []}
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        return {"runs": []}
    return data


def record_practice(
    attempt_dir: str | Path,
    mode: str,
    label: str,
    hits: int,
    total: int,
    missed: list[str] | None = None,
    pack_id: str | None = None,
) -> dict[str, Any]:
    """Append one finished (or stopped-early) run; returns the stored entry."""
    run = {
        "mode": mode,
        "label": label,
        "hits": int(hits),
        "total": int(total),
        "missed": list(dict.fromkeys(missed or []))[:MAX_MISSED_PER_RUN],
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if pack_id:
        run["pack_id"] = pack_id
    log = load_practice_log(attempt_dir)
    log["runs"] = (log["runs"] + [run])[-MAX_RUNS:]
    path = practice_log_path(attempt_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(log, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return run


def weak_items(log: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    """Most-missed items over the recent runs, most frequent first.

    Only misses count — an item disappears from this list once the learner
    keeps getting it right, because new runs stop contributing it.
    """
    counts: dict[str, dict[str, Any]] = {}
    for run in log.get("runs", [])[-RECENT_RUNS_FOR_WEAKNESS:]:
        for item in run.get("missed", []):
            item = str(item).strip()
            if not item:
                continue
            entry = counts.setdefault(item, {"item": item, "count": 0, "last": ""})
            entry["count"] += 1
            entry["last"] = max(entry["last"], str(run.get("at", "")))
    ranked = sorted(counts.values(), key=lambda e: e["last"], reverse=True)
    ranked.sort(key=lambda e: e["count"], reverse=True)  # stable: recent breaks ties
    return ranked[:limit]


def practice_summary(log: dict[str, Any]) -> dict[str, Any]:
    """Small rollup for status displays: run count, items answered, accuracy."""
    runs = log.get("runs", [])
    hits = sum(int(run.get("hits", 0)) for run in runs)
    total = sum(int(run.get("total", 0)) for run in runs)
    return {
        "runs": len(runs),
        "hits": hits,
        "total": total,
        "accuracy": (hits / total) if total else None,
    }
