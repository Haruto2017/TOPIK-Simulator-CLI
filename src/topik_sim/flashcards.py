from __future__ import annotations

import random
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
