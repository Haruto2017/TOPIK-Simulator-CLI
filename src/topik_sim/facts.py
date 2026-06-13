from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FACTS_SCHEMA_VERSION = "topik-sim.facts.v1"
# Bundled, tracked content (not the gitignored library) — ships with the tool.
# One file per genre lives in this directory, so a genre can be edited in
# isolation (see docs/CONTENT_CONTRACT.md). A single .json file also works.
DEFAULT_FACTS_PATH = Path("content") / "facts"


def load_facts(path: str | Path = DEFAULT_FACTS_PATH) -> list[dict[str, Any]]:
    """Load Korea facts from a directory of per-genre files (sorted, then
    concatenated) or from a single JSON file. Returns [] on any problem so a
    missing or malformed source degrades gracefully rather than breaking."""
    facts_path = Path(path)
    if facts_path.is_dir():
        facts: list[dict[str, Any]] = []
        for genre_file in sorted(facts_path.glob("*.json")):
            facts.extend(_load_file(genre_file))
        return facts
    return _load_file(facts_path)


def _load_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        facts = data
    elif isinstance(data, dict):
        facts = data.get("facts")
    else:
        facts = None
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
