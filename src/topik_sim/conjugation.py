from __future__ import annotations

"""Deterministic Korean conjugation for practice drills.

A learning tool must never teach a wrong form, so every conjugation here is
either produced by an exception-free rule or read from a curated table — never
guessed. Two speech levels are covered:

- **Formal polite** ``-습니다/-ㅂ니다`` — fully regular (consonant/vowel stems
  plus the ㄹ-drop), no verb-class exceptions.
- **Informal polite** ``-아/어요`` (해요체) — the everyday speech level, and the
  hard one: vowel harmony, vowel contractions, and five irregular verb classes
  (ㅂ, ㄷ, ㅅ, 르, 으, ㅎ). The regular algorithm runs only on the *provably*
  safe cases (하다, vowel stems, and consonant stems whose final can never be
  irregular); anything ending in ㄷ/ㅂ/ㅅ/ㅎ or the ㅡ vowel is resolved from
  ``KNOWN_AEO`` or skipped. So a verb the table does not know and the algorithm
  cannot prove is simply left out of the drill (``conjugate`` returns None).

Also the concatenative endings (``-고 싶어요`` etc.) that attach to the bare
stem with no sound change.
"""

import random
import unicodedata
from pathlib import Path
from typing import Any, Callable

from .content import ExamPack
from .hangul import compose_syllable, decompose_syllable

BRIGHT_VOWELS = {"ㅏ", "ㅗ"}          # take 아; everything else takes 어
RISKY_FINALS = {"ㄷ", "ㅂ", "ㅅ", "ㅎ"}  # can be regular OR irregular — table only
COPULAS = {"이다", "아니다"}          # 이에요/예요 — not drilled as plain verbs

# Vowel-ending stem vowel + harmony vowel → the contracted vowel (가 + 아 → 가).
_CONTRACTIONS = {
    ("ㅏ", "ㅏ"): "ㅏ",  # 가 → 가요
    ("ㅗ", "ㅏ"): "ㅘ",  # 오 → 와요, 보 → 봐요
    ("ㅓ", "ㅓ"): "ㅓ",  # 서 → 서요, 건너 → 건너요
    ("ㅜ", "ㅓ"): "ㅝ",  # 주 → 줘요, 배우 → 배워요
    ("ㅣ", "ㅓ"): "ㅕ",  # 마시 → 마셔요, 기다리 → 기다려요
    ("ㅐ", "ㅓ"): "ㅐ",  # 보내 → 보내요
    ("ㅔ", "ㅓ"): "ㅔ",  # 세 → 세요
    ("ㅚ", "ㅓ"): "ㅙ",  # 되 → 돼요
    ("ㅕ", "ㅓ"): "ㅕ",  # 켜 → 켜요
}
_APPEND_VOWELS = {"ㅟ", "ㅢ"}  # 쉬 → 쉬어요, 뛰 → 뛰어요 (no contraction)


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
    plus 니다; ㄹ-final stems drop the ㄹ and do the same. No verb-class
    exceptions apply to this ending.
    """
    if word in COPULAS:
        return None
    stem = _stem(word)
    if stem is None:
        return None
    lead, vowel, tail = decompose_syllable(stem[-1])
    if tail in ("", "ㄹ"):
        return stem[:-1] + compose_syllable(lead, vowel, "ㅂ") + "니다"
    return stem + "습니다"


# Curated -아/어요 forms: every verb whose final is ㄷ/ㅂ/ㅅ/ㅎ (ambiguous —
# regular vs. irregular cannot be told from spelling) or whose stem vowel is ㅡ
# (으/르 irregulars), plus the ㅎ-irregular adjectives and 되다/뵈다. Regular
# risky-final verbs are listed too, because the algorithm refuses to guess them.
KNOWN_AEO = {
    # ㅂ irregular (ㅂ → 우 + 어 → 워)
    "춥다": "추워요", "덥다": "더워요", "쉽다": "쉬워요", "어렵다": "어려워요",
    "무겁다": "무거워요", "가볍다": "가벼워요", "맵다": "매워요", "뜨겁다": "뜨거워요",
    "차갑다": "차가워요", "아름답다": "아름다워요", "반갑다": "반가워요", "고맙다": "고마워요",
    "즐겁다": "즐거워요", "귀엽다": "귀여워요", "눕다": "누워요", "굽다": "구워요",
    "돕다": "도와요", "곱다": "고와요",  # ㅂ → 오 (only these two)
    # ㅂ regular
    "입다": "입어요", "잡다": "잡아요", "좁다": "좁아요", "씹다": "씹어요",
    # ㄷ irregular (ㄷ → ㄹ)
    "듣다": "들어요", "걷다": "걸어요", "묻다": "물어요", "싣다": "실어요",
    # ㄷ regular
    "닫다": "닫아요", "받다": "받아요", "믿다": "믿어요", "얻다": "얻어요",
    # ㅅ irregular (ㅅ drops, vowels stay uncontracted)
    "짓다": "지어요", "낫다": "나아요", "붓다": "부어요", "젓다": "저어요",
    # ㅅ regular
    "웃다": "웃어요", "씻다": "씻어요", "벗다": "벗어요",
    # ㅎ irregular (adjectives): stem ㅎ drops, vowel → ㅐ (ㅑ → ㅒ)
    "그렇다": "그래요", "어떻다": "어때요", "이렇다": "이래요", "저렇다": "저래요",
    "빨갛다": "빨개요", "파랗다": "파래요", "노랗다": "노래요", "까맣다": "까매요",
    "하얗다": "하얘요",
    # ㅎ regular
    "좋다": "좋아요", "놓다": "놓아요", "넣다": "넣어요", "낳다": "낳아요", "닿다": "닿아요",
    # 으 irregular (ㅡ drops; harmony from the syllable before)
    "쓰다": "써요", "크다": "커요", "끄다": "꺼요", "뜨다": "떠요",
    "바쁘다": "바빠요", "아프다": "아파요", "고프다": "고파요", "슬프다": "슬퍼요",
    "예쁘다": "예뻐요", "기쁘다": "기뻐요", "나쁘다": "나빠요",
    "모으다": "모아요", "담그다": "담가요",
    "따르다": "따라요", "치르다": "치러요", "들르다": "들러요",  # 르-ending but 으-irregular
    # 르 irregular (ㄹㄹ)
    "모르다": "몰라요", "다르다": "달라요", "빠르다": "빨라요", "부르다": "불러요",
    "고르다": "골라요", "자르다": "잘라요", "흐르다": "흘러요", "오르다": "올라요",
    "기르다": "길러요", "누르다": "눌러요", "서두르다": "서둘러요",
    # special vowel contractions worth pinning
    "되다": "돼요", "뵈다": "봬요",
}


def informal_polite(word: str) -> str | None:
    """-아/어요 (해요체). Returns None for any verb it cannot resolve safely."""
    if word in COPULAS:
        return None
    stem = _stem(word)
    if stem is None:
        return None
    if stem.endswith("하"):          # 하다 → 해요 (invariant)
        return stem[:-1] + "해요"
    if word in KNOWN_AEO:            # irregulars & risky-final regulars
        return KNOWN_AEO[word]
    lead, vowel, tail = decompose_syllable(stem[-1])
    harmony = "ㅏ" if vowel in BRIGHT_VOWELS else "ㅓ"
    if tail == "":                  # vowel-ending stem
        if vowel == "ㅡ":           # 으/르 irregular — must be in the table
            return None
        combined = _CONTRACTIONS.get((vowel, harmony))
        if combined is not None:
            return stem[:-1] + compose_syllable(lead, combined) + "요"
        if vowel in _APPEND_VOWELS:
            return stem + compose_syllable("ㅇ", harmony) + "요"
        return None                 # an uncommon vowel we will not guess
    if tail in RISKY_FINALS:        # ㄷ/ㅂ/ㅅ/ㅎ not in the table — skip
        return None
    return stem + compose_syllable("ㅇ", harmony) + "요"


def attach(word: str, suffix: str) -> str | None:
    """Endings that join the stem unchanged: 읽다 + 고 싶어요 → 읽고 싶어요."""
    if word in COPULAS:
        return None
    stem = _stem(word)
    if stem is None:
        return None
    return stem + suffix


def _despace(text: str) -> str:
    return "".join(unicodedata.normalize("NFC", text).split())


# Each supported ending: the despaced keys that identify it inside a lesson's
# grammar pattern, a display name for the drill prompt, and the form builder.
# Order matters — match_ending returns the first hit, so specific endings
# precede the catch-all -아/어요.
SUPPORTED_ENDINGS: list[dict[str, Any]] = [
    {"keys": ["습니다", "ㅂ니다"], "display": "-습니다/-ㅂ니다 (formal polite)", "form": formal_polite},
    {"keys": ["고싶"], "display": "-고 싶어요 (want to)", "form": lambda w: attach(w, "고 싶어요")},
    {"keys": ["지않"], "display": "-지 않아요 (does not)", "form": lambda w: attach(w, "지 않아요")},
    {"keys": ["지만"], "display": "-지만 (but)", "form": lambda w: attach(w, "지만")},
    {"keys": ["아/어요", "아요/어요", "어요/아요", "해요체"], "display": "-아/어요 (informal polite)", "form": informal_polite},
]


def match_ending(pattern: str) -> dict[str, Any] | None:
    """The supported ending taught by this grammar pattern, if any.

    Keys are specific despaced substrings of the pattern text, so noun
    patterns (N이에요, N에서 …) and example sentences that merely happen to end
    in -어요 never match — the -아/어요 key requires the 아/어 alternation.
    """
    haystack = _despace(pattern)
    for spec in SUPPORTED_ENDINGS:
        if any(key in haystack for key in spec["keys"]):
            return spec
    return None


def is_conjugatable(ko: str, en: str) -> bool:
    """Lesson/pack vocabulary that can safely feed a conjugation drill: a
    Hangul dictionary form (…다) glossed as a verb/adjective ("to …"), and not
    the copulas."""
    return ko not in COPULAS and _stem(ko) is not None and en.strip().lower().startswith("to ")


# Speech levels a standalone /conjugate drill can target.
DRILL_FORMS: list[dict[str, Any]] = [
    {"key": "aeo", "display": "-아/어요 (informal polite)", "form": informal_polite},
    {"key": "seumnida", "display": "-습니다/-ㅂ니다 (formal polite)", "form": formal_polite},
]


def conjugate(word: str, form_key: str) -> str | None:
    spec = next((f for f in DRILL_FORMS if f["key"] == form_key), None)
    return spec["form"](word) if spec else None


def build_conjugation_items(
    pack: ExamPack | None = None,
    library_dir: str | Path | None = None,
    seed: int | None = None,
    count: int = 10,
    form_key: str = "aeo",
) -> list[dict[str, Any]]:
    """Drill items: show a dictionary form, type its conjugation.

    Verbs come from the pack (or the whole library); only those the conjugator
    can resolve safely are included, so the drill never asks for a form the
    tool is unsure of.
    """
    from .flashcards import build_deck, library_deck

    spec = next((f for f in DRILL_FORMS if f["key"] == form_key), DRILL_FORMS[0])
    if pack is not None:
        deck = build_deck(pack, seed=0)
    elif library_dir is not None:
        deck = library_deck(library_dir)
    else:
        deck = []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in deck:
        ko = str(card.get("ko", "")).strip()
        en = str(card.get("en", "")).strip()
        if ko in seen or not is_conjugatable(ko, en):
            continue
        answer = spec["form"](ko)
        if not answer:
            continue
        seen.add(ko)
        items.append({
            "show": f"Conjugate to {spec['display']}:  {ko}  ({en}) → ?",
            "accept": [answer],
            "answer": answer,
            "speech": answer,
            "meaning": f"{ko} ({en}) → {answer}",
            "kind": "conjugation",
        })
    random.Random(seed).shuffle(items)
    return items[: max(1, count)]


Form = Callable[[str], "str | None"]
