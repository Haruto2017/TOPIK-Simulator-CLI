from __future__ import annotations

import json
import random
import unicodedata
from pathlib import Path
from typing import Any

from .library import DEFAULT_LIBRARY_DIR, latest_packs, load_pack_ref

COMPOSE_SCHEMA_VERSION = "topik-sim.compose.v1"
# Bundled, tracked content. One file per lesson set lives here; each "lesson"
# teaches one grammar structure and drills several sentences that use it.
DEFAULT_COMPOSE_PATH = Path("content") / "compose"


def load_lessons(path: str | Path = DEFAULT_COMPOSE_PATH) -> list[dict[str, Any]]:
    """Load grammar-structure lessons from a directory of files (sorted, then
    concatenated) or a single JSON file. Returns [] on any problem."""
    compose_path = Path(path)
    if compose_path.is_dir():
        lessons: list[dict[str, Any]] = []
        for lesson_file in sorted(compose_path.glob("*.json")):
            lessons.extend(_load_file(lesson_file))
        return lessons
    return _load_file(compose_path)


def _load_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        lessons = data
    elif isinstance(data, dict):
        lessons = data.get("lessons")
    else:
        lessons = None
    if not isinstance(lessons, list):
        return []
    return [lesson for lesson in lessons if _valid_lesson(lesson)]


def _valid_lesson(lesson: Any) -> bool:
    if not isinstance(lesson, dict) or not str(lesson.get("pattern", "")).strip():
        return False
    sentences = lesson.get("sentences")
    return isinstance(sentences, list) and any(
        isinstance(s, dict) and s.get("english") and s.get("korean") for s in sentences
    )


def lesson_sentences(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        s for s in lesson.get("sentences", []) if isinstance(s, dict) and s.get("english") and s.get("korean")
    ]


def filter_lessons(lessons: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    wanted = query.strip().lower()
    if not wanted:
        return list(lessons)
    return [
        lesson
        for lesson in lessons
        if wanted in f"{lesson.get('id', '')} {lesson.get('pattern', '')} {lesson.get('meaning', '')}".lower()
    ]


# --- sentence grading -------------------------------------------------------

def accepted_answers(sentence: dict[str, Any]) -> list[str]:
    accepted = sentence.get("accepted")
    if isinstance(accepted, list) and accepted:
        return [str(answer) for answer in accepted]
    return [str(sentence.get("korean", ""))]


def normalize_answer(text: str) -> str:
    collapsed = " ".join(unicodedata.normalize("NFC", text).split())
    return collapsed.strip().rstrip(".?!").strip()


def is_correct(sentence: dict[str, Any], typed: str) -> bool:
    target = normalize_answer(typed)
    return any(normalize_answer(answer) == target for answer in accepted_answers(sentence))


def drill_order(lesson: dict[str, Any], seed: int | None = None) -> list[dict[str, Any]]:
    sentences = lesson_sentences(lesson)
    random.Random(seed).shuffle(sentences)
    return sentences


# --- grounding in the learner's packs --------------------------------------

def collect_pack_grammar(library_dir: str | Path = DEFAULT_LIBRARY_DIR) -> list[dict[str, str]]:
    """Every grammar note taught across the imported packs: pattern, example,
    and the pack title. This is the 'knowledge inside the packs' a lesson is
    grounded in."""
    grammar: list[dict[str, str]] = []
    try:
        entries = latest_packs(library_dir)
    except (OSError, ValueError, KeyError):
        return grammar
    for entry in entries:
        try:
            pack = load_pack_ref(f"{entry['pack_id']}@{entry['pack_version']}", library_dir)
        except (OSError, ValueError, KeyError):
            continue
        title = str(pack.title)
        for question in pack.questions():
            for item in question.get("explanation", {}).get("grammar", []):
                grammar.append(
                    {
                        "pattern": str(item.get("pattern", "")),
                        "example": str(item.get("example", "") or ""),
                        "pack": title,
                    }
                )
    return grammar


def _despace(text: str) -> str:
    return "".join(unicodedata.normalize("NFC", text).split())


def lesson_pack_evidence(lesson: dict[str, Any], grammar: list[dict[str, str]]) -> dict[str, Any]:
    """How the lesson's structure shows up in the learner's packs: a count, the
    pack titles, and an authentic example sentence to display up front."""
    keys = [_despace(k) for k in lesson.get("match", []) if str(k).strip()]
    if not keys:
        keys = [_despace(str(lesson.get("pattern", "")))]
    count = 0
    packs: list[str] = []
    example = ""
    for note in grammar:
        haystack = _despace(note["pattern"]) + " " + _despace(note["example"])
        if any(key and key in haystack for key in keys):
            count += 1
            if note["pack"] not in packs:
                packs.append(note["pack"])
            if not example and note["example"]:
                example = note["example"]
    return {"count": count, "packs": packs, "example": example}
