from __future__ import annotations

"""Auto-generated homework for course lessons.

Courses teach a bounded set of vocabulary and grammar, then jump straight to
exam questions. Homework closes that gap the way a textbook does: each lesson
gets a short assignment that validates exactly the knowledge it introduced,
generated from the lesson itself — no separate content authoring.

Six exercise kinds are generated per lesson:

- ``recall``      — the English gloss is shown, the Korean word is typed.
- ``meaning``     — a Korean word is shown, its gloss is picked from options.
- ``pattern``     — a grammar explanation is shown, its pattern is picked.
- ``cloze``       — a grammar example with its verb blanked out; the learner
  conjugates the given dictionary form to fill it (only when the example
  contains a conjugated lesson verb, so the answer is always a transformation).
- ``compose``     — a full English sentence is written in Korean, pulled from
  the compose corpus for the lesson's own patterns (usage as real sentences).
- ``conjugation`` — lesson verbs are conjugated with the ending the lesson
  taught, only for endings whose rules are exception-free (see conjugation.py).

Item dicts plug straight into the shell's typed-drill lifecycle (``show``,
``accept``, ``answer``, ``speech``), extended with ``options`` for the
multiple-choice kinds and ``meaning`` for the after-answer teaching line.
With no seed each run re-rolls a fresh cut of the lesson's pool; an explicit
seed reproduces an assignment exactly (tests).

Results persist in ``homework_progress.json`` next to the course progress
file: last and best score per lesson, so course lists can show what has been
validated and what still needs work.
"""

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content import ExamPack

HOMEWORK_FILE = "homework_progress.json"


def _lesson_vocab(course: dict[str, Any]) -> list[dict[str, str]]:
    vocab = []
    for entry in course.get("new_vocabulary") or []:
        ko = str(entry.get("ko", "")).strip()
        en = str(entry.get("en", "")).strip()
        if ko and en:
            vocab.append({"ko": ko, "en": en})
    return vocab


def _lesson_grammar(course: dict[str, Any]) -> list[dict[str, str]]:
    grammar = []
    for entry in course.get("new_grammar") or []:
        pattern = str(entry.get("pattern", "")).strip()
        if pattern:
            grammar.append({
                "pattern": pattern,
                "explanation": str(entry.get("explanation", "")).strip(),
                "example": str(entry.get("example", "")).strip(),
            })
    return grammar


def _pack_glosses(pack: ExamPack | None) -> list[str]:
    if pack is None:
        return []
    from .flashcards import build_deck

    return [card["en"] for card in build_deck(pack, seed=0)]


def _pack_patterns(pack: ExamPack | None) -> list[str]:
    if pack is None:
        return []
    from .grammar import collect_grammar_entries

    return [entry["pattern"] for entry in collect_grammar_entries(pack)]


def _choice_item(show: str, options: list[str], answer: str, rng: random.Random) -> dict[str, Any]:
    """A numbered-options item: the option number or its full text both count."""
    options = list(dict.fromkeys(options))
    rng.shuffle(options)
    number = options.index(answer) + 1
    return {
        "show": show + "\n" + "\n".join(f"  {i}. {opt}" for i, opt in enumerate(options, 1)),
        "options": options,
        "accept": [str(number), answer],
        "answer": answer,
        "reveal": f"{number}. {answer}",
    }


def _conjugation_cloze(
    point: dict[str, str],
    vocab: list[dict[str, str]],
    used: set[str],
    rng: random.Random,
) -> dict[str, Any] | None:
    """Blank a conjugated verb in the grammar example; the learner conjugates
    the given dictionary form to fill it.

    A meaningful cloze requires a transformation: we look for a lesson verb
    whose conjugation — in the ending this pattern teaches, or the everyday
    polite levels — actually appears in the example, blank that form, and hand
    back the dictionary form plus the target ending. If nothing traces back to
    a lesson verb, there is no cloze for this point (we never blank a random
    word to be copied).
    """
    from .conjugation import DRILL_FORMS, is_conjugatable, match_ending

    example = point.get("example", "")
    if not example:
        return None
    verbs = [(v["ko"], v["en"]) for v in vocab if is_conjugatable(v["ko"], v["en"])]
    if not verbs:
        return None

    # Prefer the ending this grammar point teaches, then the common polite
    # levels; each candidate is (short label, form builder).
    candidates: list[tuple[str, Any]] = []
    spec = match_ending(point.get("pattern", ""))
    if spec is not None:
        candidates.append((spec["display"].split(" (")[0], spec["form"]))
    candidates.extend((form["display"].split(" (")[0], form["form"]) for form in DRILL_FORMS)

    rng.shuffle(verbs)
    # Prefer a verb not already blanked in another point this session.
    for ko, en in sorted(verbs, key=lambda pair: pair[0] in used):
        for short, form in candidates:
            conjugated = form(ko)
            if conjugated and conjugated in example:
                used.add(ko)
                # Blank *every* occurrence so a repeated form (e.g. a Q and its
                # echoed answer) never leaves the answer visible in the sentence.
                blanked = example.replace(conjugated, "____")
                return {
                    "kind": "cloze",
                    "show": f"Fill the blank — conjugate {ko} ({en}) to {short}:  " + blanked,
                    "accept": [conjugated],
                    "answer": conjugated,
                    "speech": example,
                    "miss_key": conjugated,
                    "meaning": f"{ko} → {conjugated}  ·  {example}",
                }
    return None


def _compose_items(
    grammar: list[dict[str, str]],
    compose_path: Any,
    rng: random.Random,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Full-sentence writing for the lesson's own patterns.

    The compose corpus tags each structure with despaced ``match`` keys; a
    corpus lesson applies when one of its keys occurs in a grammar point's
    pattern or example. One sentence per matched structure, accepted variants
    included, graded like /compose (whitespace/trailing-punctuation tolerant).
    """
    from .compose import _despace, accepted_answers, lesson_sentences, load_lessons

    corpus = load_lessons(compose_path)
    items: list[dict[str, Any]] = []
    used_structures: set[str] = set()
    # Rotate which grammar points get the budget: with more matchable
    # structures than `limit`, a fixed order would starve the same pattern
    # forever. The structure per point stays the deterministic best match;
    # only the allocation (and the sentence within a structure) varies.
    points = list(grammar)
    rng.shuffle(points)
    for point in points:
        if len(items) >= limit:
            break
        pattern_hay = _despace(point["pattern"])
        example_hay = _despace(point["example"])
        # One sentence per grammar point: the corpus structure whose longest
        # key matches wins (so V-고 싶다 picks -고 싶다, not the bare -고).
        # Single-character keys (particles like 도) are too greedy for the
        # example text — they must occur in the pattern itself.
        best = None
        best_score = (0, 0)
        for lesson in corpus:
            structure_id = str(lesson.get("id", ""))
            if structure_id in used_structures or not lesson_sentences(lesson):
                continue
            keys = [_despace(k) for k in lesson.get("match", []) if str(k).strip()]
            if not keys:
                keys = [_despace(str(lesson.get("pattern", "")))]
            matched = [key for key in keys
                       if key and (key in pattern_hay or (len(key) >= 2 and key in example_hay))]
            if not matched:
                continue
            # Tiebreak on the structure's own pattern being contained in the
            # taught pattern: V-고 싶다 must pick -고 싶다, not the bare -고.
            structure_pattern = _despace(str(lesson.get("pattern", "")))
            containment = len(structure_pattern) if structure_pattern and structure_pattern in pattern_hay else 0
            score = (max(map(len, matched)), containment)
            if score > best_score:
                best = lesson
                best_score = score
        if best is None:
            continue
        used_structures.add(str(best.get("id", "")))
        sentence = rng.choice(lesson_sentences(best))
        items.append({
            "kind": "compose",
            "show": f"Write it in Korean ({best.get('pattern', '')}):  {sentence['english']}",
            "accept": accepted_answers(sentence),
            "answer": str(sentence.get("korean", "")),
            "speech": str(sentence.get("korean", "")),
            "miss_key": str(sentence.get("korean", "")),
            "meaning": f"{best.get('pattern', '')} — {best.get('meaning', '')}",
        })
    return items


def _conjugation_items(
    grammar: list[dict[str, str]],
    vocab: list[dict[str, str]],
    rng: random.Random,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Conjugate the lesson's own verbs with the ending the lesson taught.

    Generated only when a grammar pattern matches a supported, exception-free
    ending AND the lesson vocabulary contains conjugatable dictionary forms —
    the "if applicable" rule.
    """
    from .conjugation import is_conjugatable, match_ending

    verbs = [entry for entry in vocab if is_conjugatable(entry["ko"], entry["en"])]
    if not verbs:
        return []
    items: list[dict[str, Any]] = []
    for point in grammar:
        spec = match_ending(point["pattern"])
        if spec is None:
            continue
        chosen = rng.sample(verbs, min(2, len(verbs)))
        for entry in chosen:
            if len(items) >= limit:
                return items
            # The gloss lets kind-gated endings (quotes, -나요, …) resolve
            # action vs. descriptive; unresolvable words yield None and skip.
            answer = spec["form"](entry["ko"], entry.get("en", ""))
            if not answer:
                continue
            items.append({
                "kind": "conjugation",
                "show": f"Conjugate with {spec['display']}:  {entry['ko']} → ?",
                "accept": [answer],
                "answer": answer,
                "speech": answer,
                "meaning": f"{entry['ko']} ({entry['en']}) → {answer}",
            })
    return items


def build_homework(
    course: dict[str, Any],
    pack: ExamPack | None = None,
    seed: int | None = None,
    max_recall: int = 6,
    max_meaning: int = 4,
    compose_path: Any = None,
) -> list[dict[str, Any]]:
    """A fresh assignment for one course lesson, drawn from what it taught.

    With no seed (the normal case) each run re-rolls: a different fair cut of
    the lesson's own vocabulary and grammar, so re-doing homework validates the
    lesson rather than one memorized set. Passing an explicit ``seed`` makes it
    reproducible (tests, and any "give me that exact assignment again" caller).
    """
    rng = random.Random(f"{course.get('id', '')}:{seed}") if seed is not None else random.Random()
    vocab = _lesson_vocab(course)
    grammar = _lesson_grammar(course)
    items: list[dict[str, Any]] = []

    # --- vocabulary production: type the Korean for the gloss
    recall_vocab = rng.sample(vocab, min(max_recall, len(vocab)))
    for entry in recall_vocab:
        items.append({
            "kind": "recall",
            "show": f"Type the Korean:  {entry['en']}",
            "accept": [entry["ko"]],
            "answer": entry["ko"],
            "speech": entry["ko"],
            "meaning": f"{entry['ko']} — {entry['en']}",
        })

    # --- vocabulary recognition: pick the gloss for the Korean word
    remaining = [entry for entry in vocab if entry not in recall_vocab] or vocab
    gloss_pool = [entry["en"] for entry in vocab] + _pack_glosses(pack)
    for entry in rng.sample(remaining, min(max_meaning, len(remaining))):
        distractors = [g for g in dict.fromkeys(gloss_pool) if g != entry["en"]]
        options = [entry["en"]] + rng.sample(distractors, min(3, len(distractors)))
        if len(options) < 2:
            continue
        item = _choice_item(f"Which meaning matches:  {entry['ko']}", options, entry["en"], rng)
        # A miss should resurface the Korean word, not its English gloss.
        item.update({"kind": "meaning", "speech": entry["ko"], "miss_key": entry["ko"],
                     "meaning": f"{entry['ko']} — {entry['en']}"})
        items.append(item)

    # --- grammar: match the pattern to what it does
    pattern_pool = [g["pattern"] for g in grammar] + _pack_patterns(pack)
    for point in grammar:
        if not point["explanation"]:
            continue
        distractors = [p for p in dict.fromkeys(pattern_pool) if p != point["pattern"]]
        options = [point["pattern"]] + rng.sample(distractors, min(3, len(distractors)))
        if len(options) < 2:
            continue
        item = _choice_item(f"Which pattern does this?  {point['explanation']}", options, point["pattern"], rng)
        item.update({"kind": "pattern", "speech": point["example"] or point["pattern"],
                     "meaning": point["example"]})
        items.append(item)

    # --- grammar in context: conjugate the verb that fills the example's blank
    blanked_verbs: set[str] = set()
    for point in grammar:
        cloze = _conjugation_cloze(point, vocab, blanked_verbs, rng)
        if cloze is not None:
            items.append(cloze)

    # --- conjugation: apply the lesson's ending to the lesson's own verbs
    items.extend(_conjugation_items(grammar, vocab, rng))

    # --- production: write full sentences with the lesson's patterns
    if compose_path is None:
        from .compose import DEFAULT_COMPOSE_PATH

        compose_path = DEFAULT_COMPOSE_PATH
    items.extend(_compose_items(grammar, compose_path, rng))

    return items


# --- learner progress -------------------------------------------------------

def homework_path(attempt_dir: str | Path) -> Path:
    return Path(attempt_dir) / HOMEWORK_FILE


def load_homework_progress(attempt_dir: str | Path) -> dict[str, Any]:
    path = homework_path(attempt_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def homework_entry(progress: dict[str, Any], pack_id: str, course_id: str) -> dict[str, Any] | None:
    entry = (progress.get(pack_id) or {}).get(course_id)
    return entry if isinstance(entry, dict) else None


def record_homework(
    attempt_dir: str | Path, pack_id: str, course_id: str, correct: int, total: int
) -> dict[str, Any]:
    """Store one completed run; best score only ever improves."""
    progress = load_homework_progress(attempt_dir)
    entry = homework_entry(progress, pack_id, course_id) or {}
    best = entry.get("best_correct", -1)
    entry.update({
        "correct": correct,
        "total": total,
        "runs": int(entry.get("runs", 0)) + 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    if correct > best:
        entry["best_correct"] = correct
        entry["best_total"] = total
    progress.setdefault(pack_id, {})[course_id] = entry
    path = homework_path(attempt_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(progress, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return entry
