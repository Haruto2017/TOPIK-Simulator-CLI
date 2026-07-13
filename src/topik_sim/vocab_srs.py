from __future__ import annotations

"""Spaced repetition for vocabulary — the schedule a flashcard app runs on.

The exam review queue (``srs.py``) only schedules *missed exam questions*. This
schedules *words*: every vocabulary item the library teaches is introduced a
few new per session and then resurfaced on a Leitner schedule, so a word is
seen many times at growing intervals — the spacing the research calls for
(~8–12 encounters to form a word, ~20–30 spaced reviews to keep it).

State persists in ``vocab_review.json`` beside the attempts. A review item is
recall-style (see the English, produce the Korean); a correct answer promotes
the card a box and pushes its next due date out, a miss sends it back to box 1.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "topik-sim.vocab-srs.v1"
VOCAB_FILE = "vocab_review.json"
MAX_BOX = 5
# Days a card waits after reaching each box (box 1 = just missed / brand new).
BOX_INTERVALS_DAYS = {1: 1, 2: 3, 3: 7, 4: 16, 5: 35}
NEW_PER_SESSION = 8


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def vocab_path(attempt_dir: str | Path) -> Path:
    return Path(attempt_dir) / VOCAB_FILE


def load_deck(attempt_dir: str | Path) -> dict[str, Any]:
    path = vocab_path(attempt_dir)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "cards": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "cards": {}}
    if not isinstance(data, dict) or not isinstance(data.get("cards"), dict):
        return {"schema_version": SCHEMA_VERSION, "cards": {}}
    return data


def save_deck(deck: dict[str, Any], attempt_dir: str | Path) -> Path:
    path = vocab_path(attempt_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(deck, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def _due_at(card: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(card.get("due")))
    except (ValueError, TypeError):
        return None


def due_cards(deck: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or utc_now()
    due = [c for c in deck.get("cards", {}).values()
           if (_due_at(c) is not None and _due_at(c) <= now)]
    due.sort(key=lambda c: str(c.get("due")))
    return due


def due_count(deck: dict[str, Any], now: datetime | None = None) -> int:
    return len(due_cards(deck, now))


def record(deck: dict[str, Any], ko: str, en: str, correct: bool,
           now: datetime | None = None) -> dict[str, Any]:
    """Leitner update: correct promotes a box (later due), a miss resets to box 1."""
    now = now or utc_now()
    cards = deck.setdefault("cards", {})
    card = cards.get(ko) or {"ko": ko, "en": en, "box": 1, "reps": 0, "lapses": 0}
    if en and not card.get("en"):
        card["en"] = en
    card["reps"] = int(card.get("reps", 0)) + 1
    if correct:
        card["box"] = min(MAX_BOX, int(card.get("box", 1)) + 1)
        card["last_result"] = True
    else:
        card["box"] = 1
        card["lapses"] = int(card.get("lapses", 0)) + 1
        card["last_result"] = False
    card["due"] = (now + timedelta(days=BOX_INTERVALS_DAYS[card["box"]])).isoformat()
    cards[ko] = card
    return card


def build_session(
    deck: dict[str, Any],
    glosses: dict[str, str],
    now: datetime | None = None,
    count: int = 15,
    new_limit: int = NEW_PER_SESSION,
) -> list[dict[str, Any]]:
    """The cards to study now: everything due, then a few never-seen words.

    ``glosses`` is the library's Korean→English map; new words are drawn from
    it in order, so a session is deterministic for a given deck and library.
    """
    now = now or utc_now()
    count = max(1, count)
    cards = deck.get("cards", {})
    session: list[dict[str, Any]] = []
    for card in due_cards(deck, now):
        gloss = glosses.get(card["ko"]) or card.get("en", "")
        session.append({"ko": card["ko"], "en": gloss, "box": card.get("box", 1), "new": False})
        if len(session) >= count:
            return session
    introduced = 0
    for ko, en in glosses.items():
        if introduced >= new_limit or len(session) >= count:
            break
        if ko not in cards:
            session.append({"ko": ko, "en": en, "box": 0, "new": True})
            introduced += 1
    return session


def summary(deck: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    cards = deck.get("cards", {})
    return {
        "learning": len(cards),
        "due": due_count(deck, now),
        "mastered": sum(1 for c in cards.values() if int(c.get("box", 0)) >= MAX_BOX),
    }
