from __future__ import annotations

"""Learn to *read* Hangul — the from-zero on-ramp.

The simulator's first flashcard is Korean text, so a true beginner needs a
way to sound out syllable blocks before anything else makes sense. This is
alphabet mechanics, not exam content: jamo, their sounds, and how blocks
compose. Romanization appears only here, labeled as training wheels.

Consumed by the shell's /hangul command and the web UI's "Read Hangul" page.
"""

from typing import Any

from .hangul import compose_syllable

# (jamo, name, sound) — the 14 basic consonants in dictionary order.
BASIC_CONSONANTS = [
    ("ㄱ", "기역 giyeok", "g (k at the end of a syllable)"),
    ("ㄴ", "니은 nieun", "n"),
    ("ㄷ", "디귿 digeut", "d (t at the end)"),
    ("ㄹ", "리을 rieul", "r between vowels, l elsewhere"),
    ("ㅁ", "미음 mieum", "m"),
    ("ㅂ", "비읍 bieup", "b (p at the end)"),
    ("ㅅ", "시옷 siot", "s (sh before i/y)"),
    ("ㅇ", "이응 ieung", "silent at the start · ng at the end"),
    ("ㅈ", "지읒 jieut", "j"),
    ("ㅊ", "치읓 chieut", "ch"),
    ("ㅋ", "키읔 kieuk", "k (strong puff of air)"),
    ("ㅌ", "티읕 tieut", "t (strong puff)"),
    ("ㅍ", "피읖 pieup", "p (strong puff)"),
    ("ㅎ", "히읗 hieut", "h"),
]

# The five tense (doubled) consonants.
TENSE_CONSONANTS = [
    ("ㄲ", "쌍기역", "kk — tight, no puff of air"),
    ("ㄸ", "쌍디귿", "tt"),
    ("ㅃ", "쌍비읍", "pp"),
    ("ㅆ", "쌍시옷", "ss"),
    ("ㅉ", "쌍지읒", "jj"),
]

BASIC_VOWELS = [
    ("ㅏ", "a, as in father"),
    ("ㅑ", "ya"),
    ("ㅓ", "eo — 'uh', open o"),
    ("ㅕ", "yeo"),
    ("ㅗ", "o, as in go"),
    ("ㅛ", "yo"),
    ("ㅜ", "u, as in moon"),
    ("ㅠ", "yu"),
    ("ㅡ", "eu — 'uh' with flat lips"),
    ("ㅣ", "i, as in ski"),
]

COMPOUND_VOWELS = [
    ("ㅐ", "ae — as in bed"),
    ("ㅔ", "e — nearly the same as ㅐ today"),
    ("ㅒ", "yae"),
    ("ㅖ", "ye"),
    ("ㅘ", "wa"),
    ("ㅝ", "wo"),
    ("ㅙ", "wae"),
    ("ㅞ", "we"),
    ("ㅚ", "oe/we"),
    ("ㅟ", "wi"),
    ("ㅢ", "ui"),
]

# Worked examples for sounding out blocks, from single syllable to a phrase.
WALKTHROUGHS = [
    {"word": "한", "parts": "ㅎ h + ㅏ a + ㄴ n", "reading": "han",
     "note": "lead consonant + vowel + final consonant, stacked into one square block"},
    {"word": "국", "parts": "ㄱ g + ㅜ u + ㄱ k", "reading": "guk",
     "note": "the same jamo can start and end a block — 한국 = han-guk, Korea"},
    {"word": "학생", "parts": "ㅎ+ㅏ+ㄱ · ㅅ+ㅐ+ㅇ", "reading": "hak-saeng",
     "note": "student — read blocks left to right, one syllable each"},
    {"word": "안녕하세요", "parts": "안 an · 녕 nyeong · 하 ha · 세 se · 요 yo", "reading": "annyeonghaseyo",
     "note": "hello — five blocks, five syllables; ㅇ is silent at a block's start"},
]

HOW_BLOCKS_WORK = (
    "Hangul is an alphabet, not thousands of characters: 24 basic letters (jamo)"
    " that stack into square syllable blocks. Every block = a lead consonant +"
    " a vowel, plus an optional final consonant (받침 batchim). Vertical vowels"
    " (ㅏ ㅓ ㅣ …) sit to the right of the lead; horizontal ones (ㅗ ㅜ ㅡ) sit"
    " below it. Read blocks left to right, one spoken syllable each."
)

BATCHIM_NOTE = (
    "받침 (batchim) — a consonant closing the block's bottom. Finals soften:"
    " ㄱ/ㅋ/ㄲ all end like k, ㄷ/ㅅ/ㅈ/ㅊ/ㅌ/ㅎ like t, ㅂ/ㅍ like p. When the"
    " next block starts with silent ㅇ, the batchim carries over: 있어요 sounds"
    " like 이써요 (i-sseo-yo)."
)

ROMANIZATION_NOTE = (
    "Romanization here is training wheels — use it to check yourself, then let"
    " it go. Korean spelling tells you the pronunciation; English letters only"
    " approximate it."
)


def syllable_grid(consonants: list[str] | None = None, vowels: list[str] | None = None) -> list[list[str]]:
    """A small consonant × vowel composition table (reading practice)."""
    consonants = consonants or ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅎ"]
    vowels = vowels or ["ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ", "ㅣ"]
    return [[compose_syllable(lead, vowel) for vowel in vowels] for lead in consonants]


def guide() -> dict[str, Any]:
    """The whole primer as data, for any frontend to render."""
    return {
        "how_blocks_work": HOW_BLOCKS_WORK,
        "consonants": [{"jamo": j, "name": n, "sound": s} for j, n, s in BASIC_CONSONANTS],
        "tense_consonants": [{"jamo": j, "name": n, "sound": s} for j, n, s in TENSE_CONSONANTS],
        "vowels": [{"jamo": j, "sound": s} for j, s in BASIC_VOWELS],
        "compound_vowels": [{"jamo": j, "sound": s} for j, s in COMPOUND_VOWELS],
        "batchim": BATCHIM_NOTE,
        "romanization": ROMANIZATION_NOTE,
        "walkthroughs": list(WALKTHROUGHS),
        "syllable_grid": {
            "vowels": ["ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ", "ㅣ"],
            "rows": syllable_grid(),
        },
    }
