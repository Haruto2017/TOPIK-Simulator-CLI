from __future__ import annotations

import random
import unicodedata
from pathlib import Path
from typing import Any

from .content import ExamPack
from .flashcards import build_deck
from .hangul import compose_syllable, decompose_syllable


# Alphabet mechanics, not exam content: the drill teaches where keys are.
CONSONANT_POOL = ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
VOWEL_POOL = ["ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ", "ㅣ", "ㅐ", "ㅔ", "ㅛ", "ㅕ", "ㅑ", "ㅠ"]
SIMPLE_TAILS = ["", "", "ㄱ", "ㄴ", "ㄹ", "ㅁ", "ㅂ", "ㅇ"]


def normalize_typed(text: str) -> str:
    """NFC-normalize, collapse internal whitespace, and drop trailing sentence
    punctuation, so typing a word or sentence is not failed by a missing
    period or an extra space."""
    collapsed = " ".join(unicodedata.normalize("NFC", text).split())
    return collapsed.strip().rstrip(".?!").strip()


def _has_hangul(text: str) -> bool:
    return any("가" <= char <= "힣" for char in text)


def _pack_sentence_level_cap(pack: ExamPack | None) -> int | None:
    """Highest ``/compose`` lesson ``level`` to admit when scoping sentences to
    a pack's TOPIK band. ``None`` means no cap (admit every level).

    A TOPIK I pack caps at level 2, dropping the level-3 TOPIK II expression
    patterns so the sentence difficulty matches the pack. TOPIK II (and an
    unrecognized or missing band) admits everything.
    """
    if pack is None:
        return None
    band = str(pack.data.get("topik_level", "")).strip().upper()
    if "II" in band or band in {"2", "TOPIK2", "TOPIK_2"}:
        return None
    if "I" in band or band in {"1", "TOPIK1", "TOPIK_1"}:
        return 2
    return None


def _lesson_level(lesson: dict[str, Any]) -> int | None:
    try:
        return int(lesson.get("level"))
    except (TypeError, ValueError):
        return None


def _random_syllable(rng: random.Random) -> str:
    return compose_syllable(rng.choice(CONSONANT_POOL), rng.choice(VOWEL_POOL), rng.choice(SIMPLE_TAILS))


def _is_pure_hangul(word: str) -> bool:
    return bool(word) and all(decompose_syllable(char) is not None for char in word)


def library_vocabulary(library_dir: str | Path) -> list[str]:
    """Every vocabulary word taught by any imported pack, deduplicated."""
    from .library import list_packs, load_pack_ref

    try:
        entries = list_packs(library_dir)
    except (OSError, ValueError, KeyError):
        return []
    words: list[str] = []
    for entry in entries:
        try:
            pack = load_pack_ref(f"{entry['pack_id']}@{entry['pack_version']}", library_dir)
        except (OSError, ValueError, KeyError):
            continue
        words.extend(card["ko"] for card in build_deck(pack, seed=0))
    return [word for word in dict.fromkeys(words) if _is_pure_hangul(word)]


def build_typing_items(
    seed: int | None = None,
    pack: ExamPack | None = None,
    count: int = 12,
    library_dir: str | Path | None = None,
) -> list[str]:
    """Drill items ramping jamo → syllables → words.

    The word stage uses real vocabulary: from the given pack, or from every
    imported pack when only a library is given. Random two-syllable
    combinations are the last resort when no vocabulary exists.
    """
    count = max(3, count)
    rng = random.Random(seed)
    jamo_count = max(1, count // 3)
    syllable_count = max(1, count // 3)
    word_count = max(0, count - jamo_count - syllable_count)

    items: list[str] = []
    pool = CONSONANT_POOL + VOWEL_POOL
    items.extend(rng.sample(pool, min(jamo_count, len(pool))))
    for _ in range(syllable_count):
        items.append(_random_syllable(rng))

    words: list[str] = []
    if pack is not None:
        words = [card["ko"] for card in build_deck(pack, seed=seed) if _is_pure_hangul(card["ko"])]
    elif library_dir is not None:
        vocabulary = library_vocabulary(library_dir)
        if vocabulary:
            words = rng.sample(vocabulary, min(word_count, len(vocabulary)))
    while len(words) < word_count:
        words.append(_random_syllable(rng) + _random_syllable(rng))
    items.extend(words[:word_count])
    return items


def build_advanced_typing_items(
    pack: ExamPack | None = None,
    library_dir: str | Path | None = None,
    compose_path: str | Path | None = None,
    count: int = 12,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Advanced typing: only meaningful Korean words and full sentences (no
    jamo/syllable warm-up). Each item carries its English `meaning`, shown
    after the learner types it.

    Words come from pack/library vocabulary; sentences from the compose
    lessons. You type the Korean shown; matching is whitespace/punctuation
    tolerant via ``normalize_typed``.

    Naming a pack scopes the content to that pack: words to its vocabulary, and
    sentences to its TOPIK level band (a TOPIK I pack drops the level-3 TOPIK II
    expression patterns). With no pack, words span every imported pack and
    sentences span every level.
    """
    from .flashcards import build_deck, library_deck

    items: list[dict[str, Any]] = []

    if pack is not None:
        deck = build_deck(pack, seed=seed)
    elif library_dir is not None:
        deck = library_deck(library_dir)
    else:
        deck = []
    for card in deck:
        ko = str(card.get("ko", "")).strip()
        en = str(card.get("en", "")).strip()
        if ko and en and _has_hangul(ko):
            items.append({"show": ko, "accept": [ko], "answer": ko, "meaning": en, "speech": ko, "kind": "word"})

    if compose_path is not None:
        from .compose import lesson_sentences, load_lessons

        level_cap = _pack_sentence_level_cap(pack)
        for lesson in load_lessons(compose_path):
            if level_cap is not None:
                level = _lesson_level(lesson)
                if level is not None and level > level_cap:
                    continue
            for sentence in lesson_sentences(lesson):
                ko = str(sentence.get("korean", "")).strip()
                en = str(sentence.get("english", "")).strip()
                if ko and en:
                    items.append({"show": ko, "accept": [ko], "answer": ko, "meaning": en, "speech": ko, "kind": "sentence"})

    rng = random.Random(seed)
    rng.shuffle(items)
    return items[: max(1, count)]
