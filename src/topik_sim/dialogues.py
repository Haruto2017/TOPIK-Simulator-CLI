from __future__ import annotations

"""Situational dialogues — communicative, produce-your-line practice.

The exams and drills train recognition and isolated forms; research is clear
that the missing piece in self-study is *production in context* — choosing the
right line for a real situation. A dialogue plays out turn by turn: the partner's
lines are given, and on the learner's turns they produce the Korean for a stated
intent (accepted-answer tolerant, whitespace/punctuation-insensitive, with the
model revealed either way — the /compose grading model, applied to a scene).

Content lives in the editable ``content/dialogues/`` directory.
"""

import json
import unicodedata
from pathlib import Path
from typing import Any

DEFAULT_DIALOGUES_PATH = Path("content") / "dialogues"


def load_dialogues(path: str | Path = DEFAULT_DIALOGUES_PATH) -> list[dict[str, Any]]:
    directory = Path(path)
    if not directory.is_dir():
        return []
    dialogues: list[dict[str, Any]] = []
    for file in sorted(directory.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for dialogue in data.get("dialogues", []) if isinstance(data, dict) else []:
            if _valid(dialogue):
                dialogues.append(dialogue)
    return dialogues


def _valid(dialogue: Any) -> bool:
    if not isinstance(dialogue, dict) or not dialogue.get("id") or not dialogue.get("turns"):
        return False
    return any(is_learner_turn(turn) for turn in dialogue["turns"])


def is_learner_turn(turn: dict[str, Any]) -> bool:
    """A turn the learner produces: it states an English intent and carries a
    model Korean line plus accepted variants (or an explicit ``learner`` flag).
    Partner turns give Korean + a translation but no accepted list."""
    return (bool(turn.get("ko")) and bool(turn.get("en"))
            and ("accepted" in turn or turn.get("learner") is True))


def find_dialogue(dialogue_id: str, path: str | Path = DEFAULT_DIALOGUES_PATH) -> dict[str, Any] | None:
    return next((d for d in load_dialogues(path) if str(d.get("id")) == dialogue_id), None)


def accepted_answers(turn: dict[str, Any]) -> list[str]:
    accepted = turn.get("accepted")
    if isinstance(accepted, list) and accepted:
        return [str(a) for a in accepted]
    return [str(turn.get("ko", ""))]


def normalize(text: str) -> str:
    collapsed = " ".join(unicodedata.normalize("NFC", text).split())
    return collapsed.strip().rstrip(".?!~").strip()


def is_correct(turn: dict[str, Any], typed: str) -> bool:
    target = normalize(typed)
    return any(normalize(a) == target for a in accepted_answers(turn))


def summarize(path: str | Path = DEFAULT_DIALOGUES_PATH) -> list[dict[str, Any]]:
    """Listing metadata for pickers: id, titles, situation, level, turn counts."""
    out = []
    for dialogue in load_dialogues(path):
        learner_turns = sum(1 for t in dialogue["turns"] if is_learner_turn(t))
        out.append({
            "id": dialogue["id"],
            "title": dialogue.get("title", dialogue["id"]),
            "title_ko": dialogue.get("title_ko", ""),
            "situation": dialogue.get("situation", ""),
            "level": dialogue.get("level"),
            "turns": len(dialogue["turns"]),
            "your_lines": learner_turns,
        })
    return out
