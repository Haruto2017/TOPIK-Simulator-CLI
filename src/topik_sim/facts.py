from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FACTS_SCHEMA_VERSION = "topik-sim.facts.v1"
# Bundled, tracked content (not the gitignored library) — ships with the tool.
DEFAULT_FACTS_PATH = Path("content") / "korea_facts.json"


def load_facts(path: str | Path = DEFAULT_FACTS_PATH) -> list[dict[str, Any]]:
    """Load the Korea facts data file. Returns [] on any problem so a missing
    or malformed file degrades gracefully rather than breaking the shell."""
    facts_path = Path(path)
    if not facts_path.exists():
        return []
    try:
        data = json.loads(facts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    facts = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(facts, list):
        return []
    return [fact for fact in facts if isinstance(fact, dict)]


def categories(facts: list[dict[str, Any]]) -> list[str]:
    return sorted({str(fact.get("category", "")) for fact in facts if fact.get("category")})


def filter_facts(facts: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Filter by category. An exact category match wins; otherwise match the
    query as a substring of category, title, or tags."""
    wanted = query.strip().lower()
    if not wanted:
        return list(facts)
    exact = [fact for fact in facts if str(fact.get("category", "")).lower() == wanted]
    if exact:
        return exact
    matched: list[dict[str, Any]] = []
    for fact in facts:
        haystack = " ".join(
            [str(fact.get("category", "")), str(fact.get("title", "")), " ".join(fact.get("tags", []) or [])]
        ).lower()
        if wanted in haystack:
            matched.append(fact)
    return matched
