from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from .content import ExamPack


def build_deck(pack: ExamPack, seed: int | None = None) -> list[dict[str, str]]:
    """Vocabulary flashcards from every explanation in the pack, deduplicated."""
    seen: set[tuple[str, str]] = set()
    deck: list[dict[str, str]] = []
    for question in pack.questions():
        explanation = question.get("explanation", {})
        for entry in explanation.get("vocabulary", []):
            ko = str(entry.get("ko", "")).strip()
            en = str(entry.get("en", "")).strip()
            if not ko or not en or (ko, en) in seen:
                continue
            seen.add((ko, en))
            deck.append({"ko": ko, "en": en, "note": str(entry.get("note", "") or "")})
    random.Random(seed).shuffle(deck)
    return deck


def library_deck(library_dir: str | Path) -> list[dict[str, str]]:
    """Vocabulary cards from every imported pack, deduplicated by (ko, en)."""
    from .library import list_packs, load_pack_ref

    try:
        entries = list_packs(library_dir)
    except (OSError, ValueError, KeyError):
        return []
    seen: set[tuple[str, str]] = set()
    deck: list[dict[str, str]] = []
    for entry in entries:
        try:
            pack = load_pack_ref(f"{entry['pack_id']}@{entry['pack_version']}", library_dir)
        except (OSError, ValueError, KeyError):
            continue
        for card in build_deck(pack, seed=0):
            key = (card["ko"], card["en"])
            if key in seen:
                continue
            seen.add(key)
            deck.append(card)
    return deck


def build_recall_items(
    pack: ExamPack | None = None,
    library_dir: str | Path | None = None,
    seed: int | None = None,
    count: int = 10,
) -> list[dict[str, Any]]:
    """English-to-Korean production drills: show the gloss, type the Korean.

    Cards sharing one English gloss are merged so any of their Korean words
    counts as correct (synonyms across packs would otherwise be unfair).
    """
    if pack is not None:
        deck = build_deck(pack, seed=seed)
    elif library_dir is not None:
        deck = library_deck(library_dir)
    else:
        deck = []

    by_gloss: dict[str, dict[str, Any]] = {}
    for card in deck:
        gloss_key = card["en"].strip().lower()
        item = by_gloss.get(gloss_key)
        if item is None:
            by_gloss[gloss_key] = {
                "show": card["en"],
                "accept": [card["ko"]],
                "answer": card["ko"],
                "speech": card["ko"],
            }
        elif card["ko"] not in item["accept"]:
            item["accept"].append(card["ko"])
    items = list(by_gloss.values())
    random.Random(seed).shuffle(items)
    return items[: max(1, count)]
