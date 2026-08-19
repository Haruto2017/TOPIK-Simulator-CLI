from __future__ import annotations

"""The staged study path — a textbook-style scope and sequence.

``content/curriculum/*.json`` stages the whole journey the way a classroom
textbook does: levels of units, each naming its communicative tasks, grammar
scope, and vocabulary domains, so a learner always knows what to learn at
which stage. Units carry no lesson text of their own; instead this module
*resolves* each unit against the content the simulator already has —

- **compose structures** whose match keys occur in the unit's grammar,
- **course lessons** whose taught grammar overlaps the unit's grammar,
- **dialogues** and **drills** the unit names explicitly,
- **conjugation forms** the unit's grammar implies,

— and computes the unit's progress from the same files the rest of the tool
writes (course progress, homework scores, the practice log).
"""

import json
import unicodedata
from pathlib import Path
from typing import Any

DEFAULT_CURRICULUM_PATH = Path("content") / "curriculum"
CURRICULUM_SCHEMA_VERSION = "topik-sim.curriculum.v1"


def _despace(text: str) -> str:
    return "".join(unicodedata.normalize("NFC", str(text)).split())


def load_curriculum(path: str | Path = DEFAULT_CURRICULUM_PATH) -> list[dict[str, Any]]:
    """All units from every curriculum file, ordered by (level, order)."""
    directory = Path(path)
    if not directory.is_dir():
        return []
    units: list[dict[str, Any]] = []
    for file in sorted(directory.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for unit in data.get("units", []) if isinstance(data, dict) else []:
            if isinstance(unit, dict) and unit.get("id") and unit.get("title"):
                units.append(unit)
    units.sort(key=lambda u: (int(u.get("level", 0)), int(u.get("order", 0))))
    return units


def _unit_grammar_haystack(unit: dict[str, Any]) -> str:
    return " ".join(_despace(g) for g in unit.get("grammar", []))


def _match_compose(unit: dict[str, Any], corpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    haystack = _unit_grammar_haystack(unit)
    if not haystack:
        return []
    matched = []
    for lesson in corpus:
        keys = [_despace(k) for k in lesson.get("match", []) if str(k).strip()]
        if not keys:
            keys = [_despace(str(lesson.get("pattern", "")))]
        # Single-character keys only match inside an explicit grammar item.
        if any(key and len(key) >= 2 and key in haystack for key in keys):
            matched.append({"id": lesson.get("id"), "pattern": lesson.get("pattern")})
    return matched


def _match_courses(unit: dict[str, Any], course_index: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Course lessons whose taught grammar overlaps the unit's grammar scope."""
    unit_keys = [_despace(g) for g in unit.get("grammar", []) if str(g).strip()]
    if not unit_keys:
        return []
    matched = []
    for entry in course_index:
        overlap = 0
        for pattern in entry["patterns"]:
            despaced = _despace(pattern)
            if any(key in despaced or despaced in key for key in unit_keys):
                overlap += 1
        if overlap:
            matched.append({**{k: entry[k] for k in ("pack_id", "course_id", "title", "order")},
                            "overlap": overlap})
    matched.sort(key=lambda m: -m["overlap"])
    return matched[:3]


def _course_index(library_dir: str | Path, courses_path: str | Path) -> list[dict[str, Any]]:
    from .courses import courses_for
    from .library import latest_packs

    index: list[dict[str, Any]] = []
    try:
        packs = latest_packs(library_dir)
    except (OSError, ValueError, KeyError):
        packs = []
    for pack in packs:
        for course in courses_for(str(pack.get("pack_id")), courses_path):
            index.append({
                "pack_id": str(pack.get("pack_id")),
                "course_id": str(course.get("id")),
                "title": course.get("title", ""),
                "order": course.get("order"),
                "patterns": [g.get("pattern", "") for g in course.get("new_grammar", [])],
            })
    return index


def _conjugation_forms(unit: dict[str, Any]) -> list[dict[str, str]]:
    from .conjugation import match_ending

    forms = []
    seen = set()
    for grammar in unit.get("grammar", []):
        spec = match_ending(str(grammar))
        if spec and spec["key"] not in seen:
            seen.add(spec["key"])
            forms.append({"form": spec["key"], "display": spec["display"]})
    return forms


def resolve_units(
    units: list[dict[str, Any]],
    library_dir: str | Path,
    courses_path: str | Path,
    compose_path: str | Path,
    dialogues_path: str | Path,
) -> list[dict[str, Any]]:
    from .compose import load_lessons
    from .dialogues import load_dialogues

    corpus = load_lessons(compose_path)
    course_index = _course_index(library_dir, courses_path)
    dialogue_ids = {str(d.get("id")) for d in load_dialogues(dialogues_path)}

    from .wordlists import words_for_unit, wordlist_dirs_for

    wordlist_dirs = wordlist_dirs_for(library_dir)
    resolved = []
    for unit in units:
        words = words_for_unit(str(unit.get("id", "")), wordlist_dirs)
        resolved.append({
            **unit,
            "compose_structures": _match_compose(unit, corpus),
            "courses": _match_courses(unit, course_index),
            "dialogues": [d for d in unit.get("dialogues", []) if d in dialogue_ids],
            "conjugation": _conjugation_forms(unit),
            # The stage's new words, the way a textbook prints them along the
            # bottom of its pages — and the deck its drills are scoped to.
            "vocabulary": [{"ko": w["ko"], "en": w["en"], "note": w.get("note", "")} for w in words],
        })
    return resolved


def unit_status(unit: dict[str, Any], attempt_dir: str | Path) -> dict[str, Any]:
    """Progress from the tool's own trackers. The backbone is courses +
    homework; drill/dialogue practice counts as activity, not completion."""
    from .courses import is_done, load_progress
    from .homework import homework_entry, load_homework_progress
    from .practice_log import load_practice_log

    course_progress = load_progress(attempt_dir)
    hw_progress = load_homework_progress(attempt_dir)
    lessons = unit.get("courses", [])
    lessons_done = sum(1 for c in lessons if is_done(course_progress, c["pack_id"], c["course_id"]))
    homework_done = sum(1 for c in lessons
                        if homework_entry(hw_progress, c["pack_id"], c["course_id"]) is not None)

    log_modes = {run.get("mode") for run in load_practice_log(attempt_dir).get("runs", [])}
    wanted_modes = {d.get("mode") for d in unit.get("drills", [])} | (
        {"dialogue"} if unit.get("dialogues") else set())
    practiced = bool(log_modes & wanted_modes)

    if lessons:
        if lessons_done == len(lessons) and homework_done == len(lessons):
            state = "done"
        elif lessons_done or homework_done or practiced:
            state = "started"
        else:
            state = "new"
    else:
        state = "practiced" if practiced else "new"
    return {
        "state": state,
        "lessons_done": lessons_done,
        "lessons_total": len(lessons),
        "homework_done": homework_done,
        "practiced": practiced,
    }
