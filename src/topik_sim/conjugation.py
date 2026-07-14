from __future__ import annotations

"""Korean conjugation engine — textbook-broad, and never a guessed form.

A textbook does not memorize every conjugated word; it *classifies* a verb and
applies the rules for that class. This module does the same:

1. ``_classify`` sorts a dictionary form into one class — HADA, VOWEL, RIEUL
   (ㄹ-final), REGULAR (a consonant final that is never irregular), or one of
   the five irregular classes B/D/S/H (ㅂ/ㄷ/ㅅ/ㅎ), REU (르), EU (으). The
   ambiguous finals ㄷ/ㅂ/ㅅ/ㅎ and the bare ㅡ vowel cannot be told apart by
   spelling, so those verbs must appear in ``CLASS_OVERRIDES``; anything
   ambiguous and unlisted classifies as None and is simply skipped.

2. Two "magic stems" are built per class — the 아/어 stem (해요체) and the 으
   stem — and from them ~16 endings across tense, politeness, connectives, and
   modality are assembled mechanically. Every ending returns None whenever the
   stem cannot be formed, so no wrong form is ever produced.

The public surface (``formal_polite``, ``informal_polite``, ``attach``,
``conjugate``, ``build_conjugation_items``, ``match_ending``,
``SUPPORTED_ENDINGS``, ``DRILL_FORMS``, ``is_conjugatable``) is unchanged.
"""

import random
import unicodedata
from pathlib import Path
from typing import Any, Callable

from .content import ExamPack
from .hangul import compose_syllable, decompose_syllable

BRIGHT_VOWELS = {"ㅏ", "ㅗ"}
RISKY_FINALS = {"ㄷ", "ㅂ", "ㅅ", "ㅎ"}
COPULAS = {"이다", "아니다"}

# Conjugation classes.
HADA, VOWEL, RIEUL, REGULAR = "hada", "vowel", "rieul", "regular"
B, D, S, H, REU, EU = "b", "d", "s", "h", "reu", "eu"

# Verbs whose class cannot be read off the spelling (ambiguous ㄷ/ㅂ/ㅅ/ㅎ finals
# and the bare ㅡ vowel). Regular risky-final verbs are listed as REGULAR so the
# classifier knows they are safe; everything else here names its irregular class.
CLASS_OVERRIDES: dict[str, str] = {
    # ㅂ irregular
    **{w: B for w in ("춥다", "덥다", "쉽다", "어렵다", "무겁다", "가볍다", "맵다",
                       "뜨겁다", "차갑다", "아름답다", "반갑다", "고맙다", "즐겁다",
                       "귀엽다", "눕다", "굽다", "돕다", "곱다")},
    # ㅂ regular
    **{w: REGULAR for w in ("입다", "잡다", "좁다", "씹다", "넓다")},
    # ㄷ irregular
    **{w: D for w in ("듣다", "걷다", "묻다", "싣다", "깨닫다")},
    # ㄷ regular
    **{w: REGULAR for w in ("닫다", "받다", "믿다", "얻다")},
    # ㅅ irregular
    **{w: S for w in ("짓다", "낫다", "붓다", "젓다")},
    # ㅅ regular
    **{w: REGULAR for w in ("웃다", "씻다", "벗다")},
    # ㅎ irregular
    **{w: H for w in ("그렇다", "어떻다", "이렇다", "저렇다", "빨갛다", "파랗다",
                      "노랗다", "까맣다", "하얗다")},
    # ㅎ regular
    **{w: REGULAR for w in ("좋다", "놓다", "넣다", "낳다", "닿다")},
    # 으 irregular (bare ㅡ, incl. 르-ending 으-irregulars 따르다/치르다/들르다)
    **{w: EU for w in ("쓰다", "크다", "끄다", "뜨다", "바쁘다", "아프다", "고프다",
                       "슬프다", "예쁘다", "기쁘다", "나쁘다", "모으다", "담그다",
                       "따르다", "치르다", "들르다")},
    # 르 irregular
    **{w: REU for w in ("모르다", "다르다", "빠르다", "부르다", "고르다", "자르다",
                        "흐르다", "오르다", "기르다", "누르다", "서두르다")},
}


def _stem(word: str) -> str | None:
    """The verb/adjective stem: dictionary form minus 다."""
    word = word.strip()
    if len(word) < 2 or not word.endswith("다"):
        return None
    stem = word[:-1]
    if any(decompose_syllable(char) is None for char in stem):
        return None
    return stem


def _harmony(vowel: str) -> str:
    return "ㅏ" if vowel in BRIGHT_VOWELS else "ㅓ"


def _classify(word: str) -> str | None:
    if word in COPULAS:
        return None
    stem = _stem(word)
    if stem is None:
        return None
    if word in CLASS_OVERRIDES:
        return CLASS_OVERRIDES[word]
    if stem.endswith("하"):
        return HADA
    _, vowel, tail = decompose_syllable(stem[-1])
    if tail == "":
        if vowel == "ㅡ":       # 으/르 irregular — needs an override
            return None
        return VOWEL
    if tail == "ㄹ":
        return RIEUL
    if tail in RISKY_FINALS:    # ambiguous, and no override — do not guess
        return None
    return REGULAR


# Vowel-ending stem vowel + harmony vowel → contracted vowel.
_CONTRACTIONS = {
    ("ㅏ", "ㅏ"): "ㅏ", ("ㅗ", "ㅏ"): "ㅘ", ("ㅓ", "ㅓ"): "ㅓ", ("ㅜ", "ㅓ"): "ㅝ",
    ("ㅣ", "ㅓ"): "ㅕ", ("ㅐ", "ㅓ"): "ㅐ", ("ㅔ", "ㅓ"): "ㅔ", ("ㅚ", "ㅓ"): "ㅙ",
    ("ㅕ", "ㅓ"): "ㅕ",
}
_APPEND_VOWELS = {"ㅟ", "ㅢ"}


def _aeo_stem(word: str) -> str | None:
    """The 아/어 stem — the 해요체 form without 요 (가→가, 먹→먹어, 춥→추워)."""
    cls = _classify(word)
    if cls is None:
        return None
    stem = _stem(word)
    lead, vowel, tail = decompose_syllable(stem[-1])
    harmony = _harmony(vowel)
    if cls == HADA:
        return stem[:-1] + "해"
    if cls == VOWEL:
        if vowel == "ㅡ":
            return None
        combined = _CONTRACTIONS.get((vowel, harmony))
        if combined is not None:
            return stem[:-1] + compose_syllable(lead, combined)
        if vowel in _APPEND_VOWELS:
            return stem + compose_syllable("ㅇ", harmony)
        return None
    if cls in (REGULAR, RIEUL):
        return stem + compose_syllable("ㅇ", harmony)
    if cls == B:
        base = stem[:-1] + compose_syllable(lead, vowel)
        return base + ("와" if word in ("돕다", "곱다") else "워")
    if cls == D:
        return stem[:-1] + compose_syllable(lead, vowel, "ㄹ") + compose_syllable("ㅇ", harmony)
    if cls == S:
        return stem[:-1] + compose_syllable(lead, vowel) + compose_syllable("ㅇ", harmony)
    if cls == H:
        new_vowel = "ㅒ" if vowel == "ㅑ" else "ㅐ"
        return stem[:-1] + compose_syllable(lead, new_vowel)
    if cls == REU:
        prev_lead, prev_vowel, _ = decompose_syllable(stem[-2])
        return (stem[:-2] + compose_syllable(prev_lead, prev_vowel, "ㄹ")
                + compose_syllable("ㄹ", _harmony(prev_vowel)))
    if cls == EU:
        prev_vowel = decompose_syllable(stem[-2])[1] if len(stem) >= 2 else "ㅓ"
        return stem[:-1] + compose_syllable(lead, _harmony(prev_vowel))
    return None


def _eu_stem(word: str, drop_l: bool = False) -> str | None:
    """The 으 stem: consonant stems add 으, vowel/ㄹ/ㅡ stems do not, and each
    irregular class rewrites its final. ``drop_l`` removes a ㄹ-final's ㄹ, for
    endings that begin with ㄴ/ㅂ/ㅅ (사세요, 사니까)."""
    cls = _classify(word)
    if cls is None:
        return None
    stem = _stem(word)
    lead, vowel, tail = decompose_syllable(stem[-1])
    if cls in (HADA, VOWEL, REU, EU):
        return stem
    if cls == RIEUL:
        return stem[:-1] + compose_syllable(lead, vowel) if drop_l else stem
    if cls == REGULAR:
        return stem + compose_syllable("ㅇ", "ㅡ")
    if cls == B:
        return stem[:-1] + compose_syllable(lead, vowel) + "우"
    if cls == D:
        return stem[:-1] + compose_syllable(lead, vowel, "ㄹ") + compose_syllable("ㅇ", "ㅡ")
    if cls == S:
        return stem[:-1] + compose_syllable(lead, vowel) + compose_syllable("ㅇ", "ㅡ")
    if cls == H:
        return stem[:-1] + compose_syllable(lead, vowel)
    return None


def _past_stem(word: str) -> str | None:
    """The 았/었 stem: the 아/어 stem with ㅆ closing its last syllable."""
    aeo = _aeo_stem(word)
    if aeo is None:
        return None
    lead, vowel, tail = decompose_syllable(aeo[-1])
    if tail:
        return None
    return aeo[:-1] + compose_syllable(lead, vowel, "ㅆ")


def _add_l(stem: str | None) -> str | None:
    """Add the (으)ㄹ future/relative ㄹ to a 으 stem (먹으→먹을, 가→갈, 살→살)."""
    if not stem:
        return None
    lead, vowel, tail = decompose_syllable(stem[-1])
    if tail == "":
        return stem[:-1] + compose_syllable(lead, vowel, "ㄹ")
    if tail == "ㄹ":
        return stem
    return stem + "을"


def _cat(stem: str | None, suffix: str) -> str | None:
    return stem + suffix if stem else None


def formal_polite(word: str) -> str | None:
    """-습니다 / -ㅂ니다 (formal polite present)."""
    if word in COPULAS:
        return None
    stem = _stem(word)
    if stem is None:
        return None
    lead, vowel, tail = decompose_syllable(stem[-1])
    if tail in ("", "ㄹ"):
        return stem[:-1] + compose_syllable(lead, vowel, "ㅂ") + "니다"
    return stem + "습니다"


def informal_polite(word: str) -> str | None:
    """-아/어요 (해요체 present)."""
    return _cat(_aeo_stem(word), "요")


def attach(word: str, suffix: str) -> str | None:
    """Endings that join the bare stem unchanged (읽다 + 고 → 읽고)."""
    if word in COPULAS:
        return None
    return _cat(_stem(word), suffix)


def _despace(text: str) -> str:
    return "".join(unicodedata.normalize("NFC", text).split())


# The ending catalogue. Each entry drives both the standalone /conjugate drill
# (all of them) and homework's grammar-pattern matching (those with match keys).
# ``match`` keys are distinctive despaced substrings; order below is the
# match precedence, so specific endings win over general ones.
ENDINGS: list[dict[str, Any]] = [
    {"key": "past", "display": "-았/었어요 (past)", "match": ["았어요", "었어요", "았/어요", "았/었어"],
     "form": lambda w: _cat(_past_stem(w), "어요")},
    {"key": "past_formal", "display": "-았/었습니다 (past formal)", "match": ["았습니다", "었습니다"],
     "form": lambda w: _cat(_past_stem(w), "습니다")},
    {"key": "seumnida", "display": "-습니다/-ㅂ니다 (formal polite)", "match": ["습니다", "ㅂ니다"],
     "form": formal_polite},
    {"key": "future", "display": "-(으)ㄹ 거예요 (will / intend to)", "match": ["ㄹ거예요", "ㄹ거에요", "(으)ㄹ거"],
     "form": lambda w: _cat(_add_l(_eu_stem(w)), " 거예요")},
    {"key": "can", "display": "-(으)ㄹ 수 있어요 (can)", "match": ["ㄹ수있", "ㄹ수없"],
     "form": lambda w: _cat(_add_l(_eu_stem(w)), " 수 있어요")},
    {"key": "honorific", "display": "-(으)세요 (honorific / please)", "match": ["(으)세요", "으세요"],
     "form": lambda w: _cat(_eu_stem(w, drop_l=True), "세요")},
    {"key": "if", "display": "-(으)면 (if / when)", "match": ["(으)면", "으면"],
     "form": lambda w: _cat(_eu_stem(w), "면")},
    {"key": "because", "display": "-(으)니까 (because)", "match": ["(으)니까", "으니까"],
     "form": lambda w: _cat(_eu_stem(w, drop_l=True), "니까")},
    {"key": "so", "display": "-아서/어서 (so / and then)", "match": ["아서", "어서", "아/어서"],
     "form": lambda w: _cat(_aeo_stem(w), "서")},
    {"key": "must", "display": "-아야/어야 해요 (must)", "match": ["아야", "어야", "아/어야"],
     "form": lambda w: _cat(_aeo_stem(w), "야 해요")},
    {"key": "want", "display": "-고 싶어요 (want to)", "match": ["고싶"],
     "form": lambda w: attach(w, "고 싶어요")},
    {"key": "progressive", "display": "-고 있어요 (be ...-ing)", "match": ["고있"],
     "form": lambda w: attach(w, "고 있어요")},
    {"key": "not", "display": "-지 않아요 (does not)", "match": ["지않"],
     "form": lambda w: attach(w, "지 않아요")},
    {"key": "but", "display": "-지만 (but)", "match": ["지만"],
     "form": lambda w: attach(w, "지만")},
    {"key": "and", "display": "-고 (and)", "match": [],
     "form": lambda w: attach(w, "고")},
    {"key": "aeo", "display": "-아/어요 (informal polite)", "match": ["아/어요", "아요/어요", "어요/아요", "해요체"],
     "form": informal_polite},
]

_BY_KEY = {spec["key"]: spec for spec in ENDINGS}

# Endings matched from a lesson's grammar pattern (those with match keys),
# in precedence order.
SUPPORTED_ENDINGS: list[dict[str, Any]] = [spec for spec in ENDINGS if spec["match"]]


def match_ending(pattern: str) -> dict[str, Any] | None:
    """The supported ending taught by this grammar pattern, if any."""
    haystack = _despace(pattern)
    for spec in SUPPORTED_ENDINGS:
        if any(key in haystack for key in spec["match"]):
            return spec
    return None


def is_conjugatable(ko: str, en: str) -> bool:
    """Vocabulary that can safely feed a conjugation drill: a Hangul dictionary
    form (…다) glossed as a verb/adjective ("to …"), and not a copula."""
    return ko not in COPULAS and _stem(ko) is not None and en.strip().lower().startswith("to ")


def conjugate(word: str, form_key: str) -> str | None:
    spec = _BY_KEY.get(form_key)
    return spec["form"](word) if spec else None


# Speech-level / ending menu offered by the standalone /conjugate drill, in a
# teaching-friendly order.
DRILL_FORMS: list[dict[str, Any]] = [
    _BY_KEY[key] for key in (
        "aeo", "seumnida", "past", "past_formal", "future",
        "not", "want", "can", "if", "because", "so", "must", "honorific",
    )
]


MIX_KEY = "mix"


def build_conjugation_items(
    pack: ExamPack | None = None,
    library_dir: str | Path | None = None,
    seed: int | None = None,
    count: int = 10,
    form_key: str = MIX_KEY,
) -> list[dict[str, Any]]:
    """Drill items: show a dictionary form, type its conjugation.

    ``form_key`` is one of the DRILL_FORMS keys, or ``"mix"`` (the default) to
    interleave — each verb gets a random ending it can safely take, which is
    more effective study than blocking on one form. The prompt always names the
    target ending, so a mixed session is never ambiguous. Only verbs the engine
    can resolve are included; with no seed each session re-rolls.
    """
    from .flashcards import build_deck, library_deck

    mixed = form_key == MIX_KEY
    fixed = None if mixed else _BY_KEY.get(form_key, _BY_KEY["aeo"])
    rng = random.Random(seed)
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
        if mixed:
            options = [spec for spec in DRILL_FORMS if spec["form"](ko)]
            if not options:
                continue
            spec = rng.choice(options)
        else:
            spec = fixed
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
    rng.shuffle(items)
    return items[: max(1, count)]


Form = Callable[[str], "str | None"]
