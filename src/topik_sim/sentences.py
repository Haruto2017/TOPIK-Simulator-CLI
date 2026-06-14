from __future__ import annotations

import json
import random
import unicodedata
from pathlib import Path
from typing import Any

SENTENCES_SCHEMA_VERSION = "topik-sim.sentences.v1"
# Bundled, tracked content. One file per topic lives here (greetings.json,
# travel.json, ...), so a topic can be expanded in isolation by one agent —
# the same per-genre pattern as content/facts/.
DEFAULT_SENTENCES_PATH = Path("content") / "sentences"


def load_sentences(path: str | Path = DEFAULT_SENTENCES_PATH) -> list[dict[str, Any]]:
    """Load translation sentences from a directory of per-topic files (sorted,
    then concatenated) or from a single JSON file. Returns [] on any problem."""
    sentences_path = Path(path)
    if sentences_path.is_dir():
        sentences: list[dict[str, Any]] = []
        for topic_file in sorted(sentences_path.glob("*.json")):
            sentences.extend(_load_file(topic_file))
        return sentences
    return _load_file(sentences_path)


def _load_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("sentences")
    else:
        items = None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("english") and item.get("korean")]


def topics(sentences: list[dict[str, Any]]) -> list[str]:
    return sorted({str(item.get("topic", "")) for item in sentences if item.get("topic")})


def filter_sentences(sentences: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Filter by topic (exact wins), else substring of topic/english/id."""
    wanted = query.strip().lower()
    if not wanted:
        return list(sentences)
    exact = [item for item in sentences if str(item.get("topic", "")).lower() == wanted]
    if exact:
        return exact
    return [
        item
        for item in sentences
        if wanted in f"{item.get('topic', '')} {item.get('english', '')} {item.get('id', '')}".lower()
    ]


def accepted_answers(sentence: dict[str, Any]) -> list[str]:
    accepted = sentence.get("accepted")
    if isinstance(accepted, list) and accepted:
        return [str(answer) for answer in accepted]
    return [str(sentence.get("korean", ""))]


def normalize_answer(text: str) -> str:
    """NFC-normalize and collapse whitespace so spacing/composition quirks
    do not cause false misses; trailing sentence punctuation is ignored."""
    collapsed = " ".join(unicodedata.normalize("NFC", text).split())
    return collapsed.strip().rstrip(".?!").strip()


def is_correct(sentence: dict[str, Any], typed: str) -> bool:
    target = normalize_answer(typed)
    return any(normalize_answer(answer) == target for answer in accepted_answers(sentence))


def build_drill(
    sentences: list[dict[str, Any]],
    topic: str | None = None,
    count: int = 10,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    pool = filter_sentences(sentences, topic) if topic else list(sentences)
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool[: max(1, count)]
