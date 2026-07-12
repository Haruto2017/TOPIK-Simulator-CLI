from __future__ import annotations

"""Auto-generated homework for course lessons.

Courses teach a bounded set of vocabulary and grammar, then jump straight to
exam questions. Homework closes that gap the way a textbook does: each lesson
gets a short assignment that validates exactly the knowledge it introduced,
generated from the lesson itself — no separate content authoring.

Four exercise kinds are generated per lesson:

- ``recall``  — the English gloss is shown, the Korean word is typed.
- ``meaning`` — a Korean word is shown, its gloss is picked from options.
- ``pattern`` — a grammar explanation is shown, its pattern is picked.
- ``cloze``   — a grammar example with one word blanked out is completed.

Item dicts plug straight into the shell's typed-drill lifecycle (``show``,
``accept``, ``answer``, ``speech``), extended with ``options`` for the
multiple-choice kinds and ``meaning`` for the after-answer teaching line.
Generation is deterministic per lesson, so re-running the homework repeats
the same assignment.

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
from .hangul import decompose_syllable

HOMEWORK_FILE = "homework_progress.json"

_PUNCT = ".,!?…\"'()[]{}:;-—~"


def _is_hangul_word(word: str) -> bool:
    return bool(word) and all(decompose_syllable(char) is not None for char in word)


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


def _cloze(example: str, vocab_words: list[str], rng: random.Random) -> tuple[str, str] | None:
    """Blank one word in the example: a lesson vocabulary word when one occurs
    (particles attach directly, so substring replacement is safe), otherwise
    the longest pure-Hangul token."""
    hits = sorted((w for w in vocab_words if w and w in example), key=len, reverse=True)
    if hits:
        word = rng.choice(hits[: min(3, len(hits))])
        return example.replace(word, "____", 1), word
    tokens = [token.strip(_PUNCT) for token in example.split()]
    tokens = [t for t in tokens if len(t) >= 2 and _is_hangul_word(t)]
    if not tokens:
        return None
    word = max(tokens, key=len)
    return example.replace(word, "____", 1), word


def build_homework(
    course: dict[str, Any],
    pack: ExamPack | None = None,
    seed: int | None = None,
    max_recall: int = 6,
    max_meaning: int = 4,
) -> list[dict[str, Any]]:
    """The assignment for one course lesson, deterministic per lesson."""
    rng = random.Random(f"{course.get('id', '')}:{seed}")
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

    # --- grammar in context: fill the blank in the example sentence
    vocab_words = [entry["ko"] for entry in vocab]
    for point in grammar:
        if not point["example"]:
            continue
        blanked = _cloze(point["example"], vocab_words, rng)
        if blanked is None:
            continue
        sentence, word = blanked
        items.append({
            "kind": "cloze",
            "show": f"Fill the blank ({point['pattern']}):  {sentence}",
            "accept": [word],
            "answer": word,
            "speech": point["example"],
            "meaning": point["example"],
        })

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
