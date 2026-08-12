from __future__ import annotations

"""Mine an exam pack's vocabulary — mechanically, without reading it.

A pack's Korean text is data, not prose to be understood: this module reduces
it to a deduplicated list of lemmas by string surgery alone (particle
stripping, plural stripping, and dictionary-form recovery from inflected
endings), then resolves each lemma against glosses the project already owns —
pack teaching notes, curriculum wordlists, and every form the conjugation
engine can generate from a known dictionary form.

What comes out is two lists: lemmas already glossed, and *bare* lemmas that
still need one. The second list carries no sentences, no questions, and no
context — so a vocabulary list can be built for copyrighted material without
that material being read or reproduced anywhere.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

HANGUL = re.compile(r"[가-힣]+")

# Case particles and suffixes, longest first so 에서부터 beats 에.
PARTICLES = (
    "에서부터", "으로부터", "이라고", "에게서", "한테서", "께서는", "에서는",
    "으로는", "에게는", "한테는", "이라도", "이나마", "라고", "밖에", "처럼",
    "마다", "부터", "까지", "에게", "한테", "에서", "으로", "이나", "보다",
    "하고", "이랑", "께서", "조차", "마저", "만큼",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "와",
    "과", "나", "께", "랑",
)

# Endings that mark a word as verbal beyond reasonable doubt: seeing one lets
# us rebuild a dictionary form (stem + 다) instead of keeping a bare surface.
STRONG_TAILS = (
    "겠습니다", "았습니다", "었습니다", "였습니다", "습니다",
    "으십시오", "십시오", "았습니까", "었습니까", "습니까",
    "았어요", "었어요", "였어요", "으세요", "세요",
    "아요", "어요", "지요", "네요", "군요", "을까요", "ㄹ까요", "십니다",
)

# 하다-verb endings contract the 하 away (공부합니다, 공부해요), so the stem must
# be rebuilt as stem + 하다 — never stem + 다, which invents a word.
HADA_TAILS = (
    "했습니다", "하겠습니다", "합니다", "합니까", "했어요", "하세요", "하십시오",
    "해요", "해서", "했다", "하고", "하는", "한다", "해", "하다",
)

# Noun + copula: the vocabulary item is the noun, not a verb.
COPULA_TAILS = ("이었습니다", "였습니다", "입니다", "이에요", "예요", "이었다", "이다", "입니까")

# Past stems contract onto the stem (가 + 았 → 갔); undo that where the rule is
# unambiguous so 갔다 is recorded as 가다.
_PAST_UNDO = {
    "갔": "가", "왔": "오", "봤": "보", "췄": "추", "줬": "주", "됐": "되",
    "했": "하", "썼": "쓰", "샀": "사", "탔": "타", "났": "나", "잤": "자",
    "섰": "서", "켰": "키", "폈": "피", "쳤": "치", "냈": "내", "뒀": "두",
    "배웠": "배우", "마셨": "마시", "기다렸": "기다리", "다녔": "다니",
}

# Fragments and function words that are grammar, not vocabulary worth listing.
SKIP = frozenset(
    "그 저 이 것 수 때 등 및 안 못 좀 잘 더 또 다 왜 뭐 누구 어디 언제 거 게 걸 데 채 뿐 만큼"
    " 씨 님 분 개 명 살 시 분 원 번 층 권 대 마리 잔 병 그루 송이 벌 켤레"
    " 와 과 라 아 어 은 는 이 가 을 를 의 에 도 만 로 나 야 요 죠 네 군 지".split()
)


def _strip_particles(token: str) -> set[str]:
    """The token plus every plausible particle/plural-stripped form."""
    seen = {token}
    frontier = [token]
    while frontier:
        current = frontier.pop()
        if current.endswith("들") and len(current) > 2:
            base = current[:-1]
            if base not in seen:
                seen.add(base)
                frontier.append(base)
        for particle in PARTICLES:
            if current.endswith(particle) and len(current) > len(particle):
                base = current[: -len(particle)]
                if base and base not in seen:
                    seen.add(base)
                    frontier.append(base)
    return seen


def _modifier_stems(token: str) -> list[str]:
    """Dictionary-form candidates for a ㄴ/ㄹ modifier form.

    할 → 하다, 본 → 보다, 특별한 → 특별하다. A ㄹ-irregular verb drops its ㄹ
    before the ending (만들다 → 만든), so the ㄹ is offered back as well.
    """
    from .hangul import compose_syllable, decompose_syllable

    if not token:
        return []
    parts = decompose_syllable(token[-1])
    if parts is None:
        return []
    lead, vowel, tail = parts
    if tail not in ("ㄴ", "ㄹ"):
        return []
    stem = token[:-1] + compose_syllable(lead, vowel, "")
    candidates = [stem + "다"]
    if tail == "ㄴ":  # ㄹ-irregular: 만들다 → 만든
        candidates.append(token[:-1] + compose_syllable(lead, vowel, "ㄹ") + "다")
    return candidates


def _hada_lemma(token: str) -> str | None:
    """공부합니다 → 공부하다. Returns None when no 하다 ending matches."""
    for tail in HADA_TAILS:
        if token.endswith(tail) and len(token) > len(tail):
            return token[: -len(tail)] + "하다"
    return None


def _copula_lemma(token: str) -> str | None:
    """학생입니다 → 학생: the vocabulary item is the noun, not the copula."""
    for tail in COPULA_TAILS:
        if token.endswith(tail) and len(token) > len(tail) + 1:
            return token[: -len(tail)]
    return None


def _verb_candidates(token: str) -> set[str]:
    """Dictionary-form guesses (…다) for a possibly inflected token."""
    out: set[str] = set()
    hada = _hada_lemma(token)
    if hada:
        out.add(hada)
    copula = _copula_lemma(token)
    if copula:
        out.add(copula)
    for tail in STRONG_TAILS:
        if token.endswith(tail) and len(token) > len(tail):
            out.add(_undo_past(token[: -len(tail)]) + "다")
    for tail in ("아서", "어서", "여서", "으면", "면", "지만", "는데", "은데",
                 "으니까", "니까", "고", "며", "게", "지", "기", "던", "은", "는", "을"):
        if token.endswith(tail) and len(token) > len(tail) + 1:
            out.add(_undo_past(token[: -len(tail)]) + "다")
    if not token.endswith("다"):
        out.add(token + "다")
    else:
        out.add(_undo_past(token[:-1]) + "다")
    return {form for form in out if len(form) > 1}


def _undo_past(stem: str) -> str:
    """Undo a contracted past stem where the mapping is unambiguous."""
    for contracted, plain in sorted(_PAST_UNDO.items(), key=lambda kv: -len(kv[0])):
        if stem.endswith(contracted):
            return stem[: -len(contracted)] + plain
    for marker in ("았", "었", "였"):
        if stem.endswith(marker) and len(stem) > 1:
            return stem[: -len(marker)]
    return stem


def inflection_index(glosses: dict[str, str]) -> dict[str, str]:
    """Every form the conjugation engine can build → its dictionary form.

    This is what lets 갔습니다 in an exam resolve to a 가다 we already gloss,
    with no morphological analyzer and no guessing.
    """
    from .conjugation import ENDINGS, conjugate

    index: dict[str, str] = {}
    for word in glosses:
        if not word.endswith("다"):
            continue
        for spec in ENDINGS:
            try:
                form = conjugate(word, spec["key"], glosses.get(word, ""))
            except Exception:  # a form this word cannot take
                continue
            if form:
                index.setdefault(str(form).replace(" ", ""), word)
    return index


def pack_text_fragments(pack: dict[str, Any]) -> Iterable[str]:
    """Every learner-facing Korean string in a pack, as opaque text."""
    for section in pack.get("sections", []) or []:
        for question in section.get("questions", []) or []:
            yield str(question.get("prompt", "") or "")
            yield str(question.get("passage", "") or "")
            for option in question.get("options", []) or []:
                yield str(option.get("text", "") or "")


def resolve_token(token: str, glosses: dict[str, str], inflected: dict[str, str]) -> tuple[str, bool]:
    """(lemma, already_glossed) for one whitespace-delimited Korean token."""
    stripped = _strip_particles(token)
    for candidate in sorted(stripped, key=len, reverse=True):
        if candidate in glosses:
            return candidate, True
        if candidate in inflected:
            return inflected[candidate], True
    # A modifier or connective ending (같은, 있는, 먹고) leaves a bare stem, so
    # try it as a dictionary form — but only as a *lookup*, never as an
    # invention: an unknown stem stays a stem rather than becoming a fake verb.
    for candidate in sorted(stripped - {token}, key=len, reverse=True):
        if candidate + "다" in glosses:
            return candidate + "다", True
        if candidate + "다" in inflected:
            return inflected[candidate + "다"], True
    for candidate in _modifier_stems(token):
        if candidate in glosses:
            return candidate, True
        if candidate in inflected:
            return inflected[candidate], True
    for candidate in _verb_candidates(token):
        if candidate in glosses:
            return candidate, True
        if candidate in inflected:
            return inflected[candidate], True
    # Unknown: still normalize a clearly verbal token to its dictionary form.
    hada = _hada_lemma(token)
    if hada:
        return hada, False
    copula = _copula_lemma(token)
    if copula:
        return copula, False
    for tail in STRONG_TAILS:
        if token.endswith(tail) and len(token) > len(tail):
            return _undo_past(token[: -len(tail)]) + "다", False
    return min(_strip_particles(token), key=len), False


def mine_pack(
    pack: dict[str, Any],
    glosses: dict[str, str],
    inflected: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Lemma inventory for one pack, split into glossed and needs-gloss."""
    if inflected is None:
        inflected = inflection_index(glosses)
    counts: Counter[str] = Counter()
    status: dict[str, bool] = {}
    for fragment in pack_text_fragments(pack):
        for token in HANGUL.findall(fragment):
            if token in SKIP:
                continue
            lemma, glossed = resolve_token(token, glosses, inflected)
            # Single-syllable nouns (책, 집, 물, 밥) are real vocabulary; only
            # the SKIP set of particles and bound forms is filtered out.
            if not lemma or lemma in SKIP:
                continue
            counts[lemma] += 1
            status[lemma] = status.get(lemma, False) or glossed
    return {
        "pack_id": pack.get("pack_id", ""),
        "known": sorted((l for l in counts if status[l]), key=lambda l: -counts[l]),
        "needs_gloss": sorted((l for l in counts if not status[l]), key=lambda l: -counts[l]),
        "counts": dict(counts),
    }


def mine_packs(
    pack_paths: Iterable[str | Path],
    glosses: dict[str, str],
) -> dict[str, Any]:
    """Merge several packs into one lemma inventory with per-pack provenance."""
    inflected = inflection_index(glosses)
    counts: Counter[str] = Counter()
    status: dict[str, bool] = {}
    sources: dict[str, set[str]] = defaultdict(set)
    for path in pack_paths:
        pack = json.loads(Path(path).read_text(encoding="utf-8"))
        result = mine_pack(pack, glosses, inflected)
        pack_id = result["pack_id"] or Path(path).stem
        for lemma, n in result["counts"].items():
            counts[lemma] += n
            sources[lemma].add(pack_id)
        for lemma in result["known"]:
            status[lemma] = True
        for lemma in result["needs_gloss"]:
            status.setdefault(lemma, False)
    return {
        "lemmas": [
            {
                "ko": lemma,
                "count": counts[lemma],
                "packs": sorted(sources[lemma]),
                "glossed": status.get(lemma, False),
            }
            for lemma in sorted(counts, key=lambda l: (-counts[l], l))
        ],
        "total": len(counts),
        "glossed": sum(1 for l in counts if status.get(l)),
        "needs_gloss": sum(1 for l in counts if not status.get(l)),
    }
