from __future__ import annotations

import random
import unicodedata
from pathlib import Path

from .content import ExamPack
from .flashcards import build_deck
from .hangul import compose_syllable, decompose_syllable


# Alphabet mechanics, not exam content: the drill teaches where keys are.
CONSONANT_POOL = ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
VOWEL_POOL = ["ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ", "ㅣ", "ㅐ", "ㅔ", "ㅛ", "ㅕ", "ㅑ", "ㅠ"]
SIMPLE_TAILS = ["", "", "ㄱ", "ㄴ", "ㄹ", "ㅁ", "ㅂ", "ㅇ"]


def normalize_typed(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip())


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
