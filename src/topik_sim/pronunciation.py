from __future__ import annotations

"""Korean sound-change rules — why words sound different from how they're spelled.

The single fastest thing a learner can do for listening is learn the handful of
phonological rules that make written Korean and spoken Korean diverge (연음,
경음화, 비음화, 유음화, 격음화, 구개음화, ㅎ-weakening). Once you know them,
native speech stops sounding "slurred".

To stay correct, examples are curated rather than computed (Korean phonology has
enough conditions that an engine would risk teaching a wrong reading). Each rule
carries worked spelled→spoken pairs; the drill shows the spelling and asks for
the pronunciation (the phonetic Hangul), which the TTS then speaks so the ear
and the rule line up.
"""

import random
from typing import Any

# Each rule: id, Korean + English name, one-line explanation, and (written,
# spoken, gloss) examples. "spoken" is the phonetic Hangul respelling.
RULES: list[dict[str, Any]] = [
    {
        "id": "yeoneum",
        "name": "연음 — linking (liaison)",
        "explain": "A final consonant (받침) slides onto the next syllable when it begins with a vowel (ㅇ).",
        "examples": [
            ("한국어", "한구거", "Korean language"),
            ("음악", "으막", "music"),
            ("옷을", "오슬", "clothes (obj.)"),
            ("책이", "채기", "book (subj.)"),
            ("밥을", "바블", "rice/meal (obj.)"),
        ],
    },
    {
        "id": "gyeongeum",
        "name": "경음화 — tensing",
        "explain": "ㄱ/ㄷ/ㅂ/ㅅ/ㅈ become tense (ㄲ/ㄸ/ㅃ/ㅆ/ㅉ) after a ㄱ/ㄷ/ㅂ stop.",
        "examples": [
            ("학교", "학꾜", "school"),
            ("식당", "식땅", "restaurant"),
            ("숙제", "숙쩨", "homework"),
            ("입구", "입꾸", "entrance"),
            ("책상", "책쌍", "desk"),
        ],
    },
    {
        "id": "bieum",
        "name": "비음화 — nasalization",
        "explain": "A ㄱ/ㄷ/ㅂ stop becomes a nasal (ㅇ/ㄴ/ㅁ) before a ㄴ or ㅁ.",
        "examples": [
            ("한국말", "한궁말", "Korean language"),
            ("감사합니다", "감사함니다", "thank you"),
            ("먹는", "멍는", "eating (mod.)"),
            ("입니다", "임니다", "is/am/are (formal)"),
            ("몇 명", "면 명", "how many people"),
        ],
    },
    {
        "id": "yueum",
        "name": "유음화 — ㄴ↔ㄹ blending",
        "explain": "ㄴ next to ㄹ turns into ㄹ, so the pair sounds like a doubled ㄹㄹ.",
        "examples": [
            ("신라", "실라", "Silla (dynasty)"),
            ("연락", "열락", "contact"),
            ("한류", "할류", "the Korean wave"),
            ("실내", "실래", "indoors"),
        ],
    },
    {
        "id": "gyeokeum",
        "name": "격음화 — aspiration",
        "explain": "ㅎ merges with a neighbouring ㄱ/ㄷ/ㅂ/ㅈ into an aspirated ㅋ/ㅌ/ㅍ/ㅊ.",
        "examples": [
            ("축하", "추카", "congratulations"),
            ("좋다", "조타", "to be good"),
            ("많다", "만타", "to be many"),
            ("입학", "이팍", "entering school"),
        ],
    },
    {
        "id": "gugae",
        "name": "구개음화 — palatalization",
        "explain": "A final ㄷ/ㅌ before 이/히 shifts to ㅈ/ㅊ.",
        "examples": [
            ("같이", "가치", "together"),
            ("굳이", "구지", "obstinately"),
            ("해돋이", "해도지", "sunrise"),
        ],
    },
    {
        "id": "hiat",
        "name": "ㅎ weakening",
        "explain": "ㅎ softens or drops between voiced sounds, so it is barely heard.",
        "examples": [
            ("좋아요", "조아요", "it's good"),
            ("많이", "마니", "a lot"),
            ("싫어요", "시러요", "I don't like it"),
            ("넣어요", "너어요", "put it in"),
        ],
    },
]

_BY_ID = {rule["id"]: rule for rule in RULES}


def rules() -> list[dict[str, Any]]:
    return RULES


def guide() -> dict[str, Any]:
    """The whole reference as data for any frontend."""
    return {
        "intro": (
            "Korean is written morphophonemically — the spelling shows the parts of a word, "
            "not always its sound. These seven rules cover almost every gap between what you "
            "read and what you hear. Learn them and native speech gets much clearer."
        ),
        "rules": [{
            "id": r["id"], "name": r["name"], "explain": r["explain"],
            "examples": [{"written": w, "spoken": s, "gloss": g} for w, s, g in r["examples"]],
        } for r in RULES],
    }


def build_pronunciation_items(seed: int | None = None, count: int = 10,
                              rule_id: str | None = None) -> list[dict[str, Any]]:
    """Drill items: show the spelling, type how it is actually pronounced.

    The answer is the phonetic Hangul; ``speech`` is the same, so the TTS reads
    the *sound* and the learner's answer, rule name, and audio all agree.
    """
    chosen = [_BY_ID[rule_id]] if rule_id in _BY_ID else RULES
    pool: list[dict[str, Any]] = []
    for rule in chosen:
        for written, spoken, gloss in rule["examples"]:
            pool.append({"written": written, "spoken": spoken, "gloss": gloss, "rule": rule["name"]})
    random.Random(seed).shuffle(pool)
    items: list[dict[str, Any]] = []
    for ex in pool[: max(1, count)]:
        items.append({
            "show": f"How is it pronounced?  {ex['written']}  ({ex['gloss']})",
            "accept": [ex["spoken"]],
            "answer": ex["spoken"],
            "speech": ex["spoken"],
            "meaning": f"{ex['written']} → [{ex['spoken']}]  ·  {ex['rule']}",
            "kind": "pronunciation",
        })
    return items
