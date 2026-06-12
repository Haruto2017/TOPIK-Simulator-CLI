from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from .content import ExamPack


def collect_grammar_entries(pack: ExamPack) -> list[dict[str, str]]:
    """Unique grammar patterns taught by a pack, first explanation wins."""
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for question in pack.questions():
        for item in question.get("explanation", {}).get("grammar", []):
            pattern = str(item.get("pattern", "")).strip()
            explanation = str(item.get("explanation", "")).strip()
            if not pattern or not explanation or pattern in seen:
                continue
            seen.add(pattern)
            entries.append(
                {
                    "pattern": pattern,
                    "explanation": explanation,
                    "example": str(item.get("example", "") or "").strip(),
                }
            )
    return entries


def library_grammar_entries(library_dir: str | Path) -> list[dict[str, str]]:
    from .library import list_packs, load_pack_ref

    try:
        packs = list_packs(library_dir)
    except (OSError, ValueError, KeyError):
        return []
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for entry in packs:
        try:
            pack = load_pack_ref(f"{entry['pack_id']}@{entry['pack_version']}", library_dir)
        except (OSError, ValueError, KeyError):
            continue
        for item in collect_grammar_entries(pack):
            if item["pattern"] in seen:
                continue
            seen.add(item["pattern"])
            entries.append(item)
    return entries


def build_grammar_cards(
    pack: ExamPack | None = None,
    library_dir: str | Path | None = None,
    seed: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Cards for the shared flashcard flow: front = pattern, back = teaching."""
    if pack is not None:
        entries = collect_grammar_entries(pack)
    elif library_dir is not None:
        entries = library_grammar_entries(library_dir)
    else:
        entries = []
    cards = [
        {
            "front": entry["pattern"],
            "back": entry["explanation"],
            "example": entry["example"],
            "speech": entry["example"],
            "keys": "",
        }
        for entry in entries
    ]
    random.Random(seed).shuffle(cards)
    if limit is not None:
        cards = cards[:limit]
    return cards
