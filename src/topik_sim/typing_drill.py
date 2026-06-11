from __future__ import annotations

import random
import unicodedata

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


def build_typing_items(
    seed: int | None = None,
    pack: ExamPack | None = None,
    count: int = 12,
) -> list[str]:
    """Drill items ramping jamo → syllables → words.

    Words come from the pack's vocabulary when one is given; without a pack
    the word stage uses random two-syllable combinations (typing practice,
    not vocabulary).
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
    while len(words) < word_count:
        words.append(_random_syllable(rng) + _random_syllable(rng))
    items.extend(words[:word_count])
    return items
