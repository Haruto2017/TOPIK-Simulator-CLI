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


def wordlist_deck(
    library_dir: str | Path,
    pack_id: str | None = None,
    unit: str | None = None,
) -> list[dict[str, str]]:
    """Vocabulary cards from the curriculum and private wordlists.

    With ``pack_id`` the deck narrows to words that pack actually uses — which
    is how a mined list (e.g. a past paper's vocabulary) becomes practisable
    even though the pack itself teaches no words in its explanations. With
    ``unit`` it narrows to one study-path stage's words instead.
    """
    from .wordlists import load_wordlists, words_for_pack, words_for_unit, wordlist_dirs_for

    directories = wordlist_dirs_for(library_dir)
    if unit:
        entries = words_for_unit(unit, directories)
    elif pack_id:
        entries = words_for_pack(pack_id, directories)
    else:
        entries = load_wordlists(directories)
    return [
        {"ko": entry["ko"], "en": entry["en"], "note": entry.get("note", "")}
        for entry in entries
    ]


def library_deck(library_dir: str | Path) -> list[dict[str, str]]:
    """Vocabulary cards from every imported pack plus the wordlists.

    Deduplicated by (ko, en); pack-taught cards come first so a curated card
    wins over a wordlist entry for the same word.
    """
    from .library import list_packs, load_pack_ref

    seen: set[tuple[str, str]] = set()
    taught: set[str] = set()
    deck: list[dict[str, str]] = []
    try:
        entries = list_packs(library_dir)
    except (OSError, ValueError, KeyError):
        entries = []
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
            taught.add(card["ko"])
            deck.append(card)
    for card in wordlist_deck(library_dir):
        if card["ko"] in taught:  # a pack already teaches this word
            continue
        key = (card["ko"], card["en"])
        if key in seen:
            continue
        seen.add(key)
        deck.append(card)
    return deck


def gloss_map(pack: ExamPack | None = None, library_dir: str | Path | None = None) -> dict[str, str]:
    """Korean word → its gloss(es), for revealing meanings after an answer.

    Duplicate glosses across packs merge with ``/``; a card note is appended
    after an em dash. The library-wide map also folds in curriculum wordlists
    (the ``vocabulary/`` directory beside the library): pack-taught glosses
    win on conflict, wordlist entries fill in the rest.
    """
    if pack is not None:
        cards = build_deck(pack, seed=0)
    elif library_dir is not None:
        cards = library_deck(library_dir)
    else:
        cards = []
    meanings: dict[str, list[str]] = {}
    for card in cards:
        ko = str(card.get("ko", "")).strip()
        gloss = str(card.get("en", "")).strip()
        if not ko or not gloss:
            continue
        note = str(card.get("note", "") or "").strip()
        if note:
            gloss = f"{gloss} — {note}"
        glosses = meanings.setdefault(ko, [])
        if gloss not in glosses:
            glosses.append(gloss)
    result = {ko: " / ".join(glosses) for ko, glosses in meanings.items()}
    if pack is None and library_dir is not None:
        from .wordlists import wordlist_dirs_for, wordlist_glosses

        for ko, gloss in wordlist_glosses(wordlist_dirs_for(library_dir)).items():
            result.setdefault(ko, gloss)
    return result


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
        if library_dir is not None:
            # Packs that teach no vocabulary in their notes (past papers, say)
            # still have a mined wordlist; scope it to this pack.
            taught = {card["ko"] for card in deck}
            deck = deck + [card for card in wordlist_deck(library_dir, pack.pack_id)
                           if card["ko"] not in taught]
            random.Random(seed).shuffle(deck)
    elif library_dir is not None:
        deck = library_deck(library_dir)
    else:
        deck = []

    return recall_items_from_cards(deck, seed=seed, count=count)


def recall_items_from_cards(
    cards: list[dict[str, str]],
    seed: int | None = None,
    count: int = 10,
) -> list[dict[str, Any]]:
    """Turn vocabulary cards into English→Korean production items.

    Cards sharing one English gloss are merged so any of their Korean words
    counts as correct (synonyms would otherwise be graded unfairly).
    """
    by_gloss: dict[str, dict[str, Any]] = {}
    for card in cards:
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
