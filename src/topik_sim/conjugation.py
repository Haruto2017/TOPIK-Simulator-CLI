from __future__ import annotations

"""Deterministic Korean conjugation for homework drills.

Only endings with rock-solid, exception-free rules are supported — a learning
tool must never teach a wrong form. The formal polite -습니다/-ㅂ니다 (with the
ㄹ-drop) is fully regular; the concatenative endings attach straight to the
stem with no sound change. Everything irregular-sensitive (-아/어요 vowel
harmony, ㄷ/ㅂ/르 irregulars with -(으)세요, …) is deliberately left out:
``match_ending`` simply returns None and no drill item is generated.
"""

import unicodedata
from typing import Any, Callable

from .hangul import compose_syllable, decompose_syllable


def _stem(word: str) -> str | None:
    """The verb/adjective stem: dictionary form minus 다."""
    word = word.strip()
    if len(word) < 2 or not word.endswith("다"):
        return None
    stem = word[:-1]
    if any(decompose_syllable(char) is None for char in stem):
        return None
    return stem


def formal_polite(word: str) -> str | None:
    """-습니다 / -ㅂ니다: 읽다 → 읽습니다, 가다 → 갑니다, 살다 → 삽니다.

    Consonant stems take 습니다; vowel stems take ㅂ as the final consonant
    plus 니다; ㄹ-final stems drop the ㄹ and do the same. This rule has no
    other irregulars (ㄷ/ㅂ/르 stems keep their dictionary shape here).
    """
    stem = _stem(word)
    if stem is None:
        return None
    lead, vowel, tail = decompose_syllable(stem[-1])
    if tail == "":
        return stem[:-1] + compose_syllable(lead, vowel, "ㅂ") + "니다"
    if tail == "ㄹ":
        return stem[:-1] + compose_syllable(lead, vowel, "ㅂ") + "니다"
    return stem + "습니다"


def attach(word: str, suffix: str) -> str | None:
    """Endings that join the stem unchanged: 읽다 + 고 싶어요 → 읽고 싶어요."""
    stem = _stem(word)
    if stem is None:
        return None
    return stem + suffix


def _despace(text: str) -> str:
    return "".join(unicodedata.normalize("NFC", text).split())


# Each supported ending: the despaced keys that identify it inside a lesson's
# grammar pattern, a display name for the drill prompt, and the form builder.
SUPPORTED_ENDINGS: list[dict[str, Any]] = [
    {
        "keys": ["습니다", "ㅂ니다"],
        "display": "-습니다/-ㅂ니다 (formal polite)",
        "form": formal_polite,
    },
    {
        "keys": ["고싶"],
        "display": "-고 싶어요 (want to)",
        "form": lambda word: attach(word, "고 싶어요"),
    },
    {
        "keys": ["지않"],
        "display": "-지 않아요 (does not)",
        "form": lambda word: attach(word, "지 않아요"),
    },
    {
        "keys": ["지만"],
        "display": "-지만 (but)",
        "form": lambda word: attach(word, "지만"),
    },
]


def match_ending(pattern: str) -> dict[str, Any] | None:
    """The supported ending taught by this grammar pattern, if any.

    The keys are specific despaced substrings of the pattern text itself, so
    noun patterns (N이에요, N에서 …) can never match.
    """
    haystack = _despace(pattern)
    for spec in SUPPORTED_ENDINGS:
        if any(key in haystack for key in spec["keys"]):
            return spec
    return None


def is_conjugatable(ko: str, en: str) -> bool:
    """Lesson vocabulary that can safely feed a conjugation drill: a Hangul
    dictionary form (…다) glossed as a verb/adjective ("to …")."""
    return _stem(ko) is not None and en.strip().lower().startswith("to ")


Form = Callable[[str], "str | None"]
