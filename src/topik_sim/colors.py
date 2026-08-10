from __future__ import annotations

"""Korean color practice — see a color, name it in Korean.

Colors are a beginner topic with a grammar sting in the tail. Three things
have to be learned together:

- The **noun** form, almost always ending in 색: 빨간색, 파란색, 노란색. Some
  colors also have a bare native noun (빨강, 파랑, 노랑, 초록, 검정, 하양).
- The **modifier** form used before a noun: 빨간 사과, 하얀 눈. For the five
  native colors this comes from a ㅎ-irregular adjective (빨갛다 → 빨간,
  하얗다 → 하얀), the same irregular class the conjugation engine handles.
- The **Sino-Korean** synonyms (녹색, 백색, 흑색, 적색, 청색, 황색), which show
  up in signs, sets, and compounds rather than everyday speech.

Every drill answer here is Hangul; items carry ``no_latin`` so the frontends
can reject an English answer with a hint instead of a plain "wrong".
"""

import random

from .hangul import decompose_syllable


def topic_particle(word: str) -> str:
    """은 after a final consonant, 는 after a vowel — 당근은, 바나나는."""
    parts = decompose_syllable(word.strip()[-1:]) if word.strip() else None
    if parts is None:
        return "는"
    return "은" if parts[2] else "는"


# ko: the noun form taught first · accept: every form counted correct for it
# adjective/modifier: the ㅎ-irregular pair, when the color has one
# hex: the swatch shown to the learner · dark: swatch needs light text
_COLORS: list[dict] = [
    {"ko": "빨간색", "en": "red", "hex": "#E03131", "accept": ["빨강", "빨간색", "붉은색"],
     "adjective": "빨갛다", "modifier": "빨간", "sino": "적색"},
    {"ko": "주황색", "en": "orange", "hex": "#F76707", "accept": ["주황", "주황색"]},
    {"ko": "노란색", "en": "yellow", "hex": "#F2C037", "accept": ["노랑", "노란색"],
     "adjective": "노랗다", "modifier": "노란", "sino": "황색"},
    {"ko": "초록색", "en": "green", "hex": "#2F9E44", "accept": ["초록", "초록색", "녹색"],
     "sino": "녹색"},
    {"ko": "파란색", "en": "blue", "hex": "#1971C2", "accept": ["파랑", "파란색"],
     "adjective": "파랗다", "modifier": "파란", "sino": "청색"},
    {"ko": "남색", "en": "navy blue", "hex": "#364FC7", "accept": ["남색"]},
    {"ko": "보라색", "en": "purple", "hex": "#7048E8", "accept": ["보라", "보라색"]},
    {"ko": "분홍색", "en": "pink", "hex": "#E64980", "accept": ["분홍", "분홍색", "핑크색"]},
    {"ko": "갈색", "en": "brown", "hex": "#A9722D", "accept": ["갈색"]},
    {"ko": "검은색", "en": "black", "hex": "#212529", "accept": ["검정", "검은색", "까만색", "검정색"],
     "adjective": "까맣다", "modifier": "까만", "sino": "흑색", "dark": True},
    {"ko": "흰색", "en": "white", "hex": "#F1F3F5", "accept": ["하양", "흰색", "하얀색"],
     "adjective": "하얗다", "modifier": "하얀", "sino": "백색"},
    {"ko": "회색", "en": "gray", "hex": "#868E96", "accept": ["회색"]},
    {"ko": "하늘색", "en": "sky blue", "hex": "#4DABF7", "accept": ["하늘색"]},
    {"ko": "연두색", "en": "yellow-green", "hex": "#94D82D", "accept": ["연두", "연두색"]},
    {"ko": "금색", "en": "gold", "hex": "#C9A227", "accept": ["금색", "황금색"]},
    {"ko": "은색", "en": "silver", "hex": "#ADB5BD", "accept": ["은색"]},
]

# Nouns whose color is fixed enough to be quizzed — everyday, not poetic.
_OBJECTS: list[tuple[str, str, str]] = [
    ("바나나", "a banana", "노란색"),
    ("하늘", "the sky", "하늘색"),
    ("눈", "snow", "흰색"),
    ("바다", "the sea", "파란색"),
    ("나뭇잎", "a leaf", "초록색"),
    ("토마토", "a tomato", "빨간색"),
    ("귤", "a tangerine", "주황색"),
    ("커피", "coffee", "갈색"),
    ("우유", "milk", "흰색"),
    ("포도", "grapes", "보라색"),
    ("당근", "a carrot", "주황색"),
    ("밤하늘", "the night sky", "검은색"),
]

# Things a modifier form naturally attaches to, for the 빨간 사과 drill.
_MODIFIED_NOUNS: list[tuple[str, str]] = [
    ("사과", "apple"), ("가방", "bag"), ("모자", "hat"), ("우산", "umbrella"),
    ("치마", "skirt"), ("자동차", "car"), ("꽃", "flower"), ("신발", "shoes"),
]

_SHADES: list[tuple[str, str]] = [("연한", "light"), ("진한", "dark")]

COLOR_LIST = [dict(color) for color in _COLORS]


def color_by_name(name: str) -> dict | None:
    """The color entry whose noun form (or any accepted form) matches."""
    wanted = name.strip()
    for color in _COLORS:
        if wanted == color["ko"] or wanted in color["accept"]:
            return dict(color)
    return None


def _swatch_fields(color: dict) -> dict:
    return {"swatch": color["hex"], "swatch_dark": bool(color.get("dark"))}


# --------------------------------------------------------------- generators

def _gen_swatch(rng: random.Random) -> dict:
    """The core ask: a color is shown, name it in Korean."""
    color = rng.choice(_COLORS)
    return {
        "show": "What color is this?",
        "answer": color["ko"],
        "accept": list(color["accept"]),
        "speech": color["ko"],
        "meaning": color["en"],
        # The swatch carries the whole question; a frontend that cannot show
        # color must fall back to naming it (see the shell's _present_typing).
        "swatch_only": True,
        **_swatch_fields(color),
    }


def _gen_word(rng: random.Random) -> dict:
    """English gloss → Korean color noun (works with no color display at all)."""
    color = rng.choice(_COLORS)
    return {
        "show": f"Color:  {color['en']}",
        "answer": color["ko"],
        "accept": list(color["accept"]),
        "speech": color["ko"],
        **_swatch_fields(color),
    }


def _gen_modifier(rng: random.Random) -> dict:
    """빨간 사과 — the ㅎ-irregular modifier form before a noun."""
    color = rng.choice([c for c in _COLORS if c.get("modifier")])
    noun, gloss = rng.choice(_MODIFIED_NOUNS)
    answer = f"{color['modifier']} {noun}"
    accept = [answer, answer.replace(" ", "")]
    return {
        "show": f"Say it before a noun:  {color['en']} {gloss}  ({color['adjective']} + {noun})",
        "answer": answer,
        "accept": accept,
        "speech": answer,
        "meaning": f"{color['adjective']} is a ㅎ-irregular adjective: the ㅎ drops before -ㄴ.",
        **_swatch_fields(color),
    }


def _gen_shade(rng: random.Random) -> dict:
    """연한/진한 + color — the everyday way to say light or dark."""
    color = rng.choice([c for c in _COLORS if c["ko"] not in {"흰색", "검은색"}])
    prefix, gloss = rng.choice(_SHADES)
    answer = f"{prefix} {color['ko']}"
    accept = [answer, answer.replace(" ", "")]
    for alt in color["accept"]:
        accept.append(f"{prefix} {alt}")
    return {
        "show": f"Shade:  {gloss} {color['en']}",
        "answer": answer,
        "accept": accept,
        "speech": answer,
        "meaning": "연한 = light/pale · 진한 = dark/deep",
        **_swatch_fields(color),
    }


def _gen_object(rng: random.Random) -> dict:
    """What color is a banana? — color words attached to real things."""
    noun, gloss, answer = rng.choice(_OBJECTS)
    color = color_by_name(answer) or {}
    accept = list(color.get("accept", [answer]))
    item = {
        "show": f"{noun}{topic_particle(noun)} 무슨 색이에요?   ({gloss})",
        "answer": answer,
        "accept": accept,
        "speech": answer,
        "meaning": f"무슨 색이에요? asks 'what color is it?' — answer with a 색 noun.",
    }
    return item  # deliberately no swatch: the learner supplies the color


def _gen_sino(rng: random.Random) -> dict:
    """Sino-Korean color words — signs, sets, and compounds."""
    color = rng.choice([c for c in _COLORS if c.get("sino")])
    return {
        "show": f"Sino-Korean word for {color['en']}  (한자어)",
        "answer": color["sino"],
        "accept": [color["sino"]],
        "speech": color["sino"],
        "meaning": f"Everyday form: {color['ko']}",
        **_swatch_fields(color),
    }


# Insertion order is the round-robin order used by the mixed drill.
_GENERATORS = {
    "swatch": _gen_swatch,
    "word": _gen_word,
    "modifier": _gen_modifier,
    "shade": _gen_shade,
    "object": _gen_object,
    "sino": _gen_sino,
}

COLOR_CATEGORIES = list(_GENERATORS)

USAGE_GUIDE = [
    ("Naming a color by itself", "빨간색이에요", "The 색 noun is the safe default."),
    ("Before a noun", "빨간 가방", "Modifier form — no 색, no 이에요."),
    ("Asking", "무슨 색이에요?", "What color is it?"),
    ("Light / dark", "연한 파란색 · 진한 파란색", "연한 = pale, 진한 = deep."),
    ("Formal / compound", "녹색 · 백색 · 흑색", "Sino-Korean, used in signs and sets."),
]


def cheat_sheet() -> dict:
    """Colors as a reference table, built from the same data the drill grades
    with — so the sheet can never disagree with the grader."""
    return {
        "colors": [
            {
                "ko": color["ko"],
                "en": color["en"],
                "hex": color["hex"],
                "dark": bool(color.get("dark")),
                "also": [form for form in color["accept"] if form != color["ko"]],
                "adjective": color.get("adjective", ""),
                "modifier": color.get("modifier", ""),
                "sino": color.get("sino", ""),
            }
            for color in _COLORS
        ],
        "irregulars": [
            {"adjective": color["adjective"], "modifier": color["modifier"], "en": color["en"]}
            for color in _COLORS if color.get("adjective")
        ],
        "usage": [{"context": c, "example": e, "note": n} for c, e, n in USAGE_GUIDE],
    }


def build_color_items(
    seed: int | None = None,
    count: int = 10,
    category: str | None = None,
) -> list[dict]:
    """Drill items whose answers are Korean color words.

    With no category (or "mix"), categories are rotated so naming, modifying,
    shading, and the Sino-Korean set all appear. Items carry ``no_latin`` so a
    frontend can ask for Hangul instead of marking an English answer wrong.
    """
    count = max(1, count)
    rng = random.Random(seed)
    if category in (None, "mix"):
        order = [COLOR_CATEGORIES[i % len(COLOR_CATEGORIES)] for i in range(count)]
    elif category in _GENERATORS:
        order = [category] * count
    else:
        raise ValueError(f"unknown color category: {category}")

    items: list[dict] = []
    for key in order:
        item = _GENERATORS[key](rng)
        item["kind"] = "color"
        item["no_latin"] = True
        items.append(item)
    return items
