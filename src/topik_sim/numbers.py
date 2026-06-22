from __future__ import annotations

"""Korean number system practice.

Korean uses two number systems and the learner has to know which one a given
context wants:

- Sino-Korean (일 이 삼 …) for dates, money, minutes, phone numbers, floor and
  room numbers, and arithmetic.
- Native Korean (하나 둘 셋 …) for counting objects, age, and the hour, almost
  always paired with a counter (개, 명, 살, 시 …). Before a counter the first four
  numbers and 스물 take short forms: 한, 두, 세, 네, 스무.

This module renders integers into either system and assembles the mixed-system
phrases (time, dates) that trip learners up, then builds drill items whose
answers are always Hangul — never Arabic digits.
"""

import random

from .hangul import decompose_syllable

# ----------------------------------------------------------------- Sino-Korean

_SINO_DIGITS = ["영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_SINO_PLACES = ["", "십", "백", "천"]
_SINO_GROUPS = ["", "만", "억", "조"]


def _read_group(value: int) -> str:
    """Read a 1–9999 chunk: 1 is dropped before 십/백/천 (105 → 백오, not 일백…)."""
    parts = []
    for power in (3, 2, 1, 0):
        digit = (value // (10 ** power)) % 10
        if digit == 0:
            continue
        if digit == 1 and power >= 1:
            parts.append(_SINO_PLACES[power])
        else:
            parts.append(_SINO_DIGITS[digit] + _SINO_PLACES[power])
    return "".join(parts)


def sino_korean(n: int) -> str:
    """Sino-Korean reading of a non-negative integer (만 is read bare: 10000 → 만)."""
    if n < 0:
        raise ValueError("sino_korean expects a non-negative integer")
    if n == 0:
        return "영"
    chunks: list[int] = []
    while n > 0:
        chunks.append(n % 10000)
        n //= 10000
    out = []
    for index in range(len(chunks) - 1, -1, -1):
        value = chunks[index]
        if value == 0:
            continue
        group = _SINO_GROUPS[index]
        if group == "만" and value == 1:
            out.append("만")
        else:
            out.append(_read_group(value) + group)
    return "".join(out)


# --------------------------------------------------------------- Native Korean

_NATIVE_ONES = ["", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉"]
_NATIVE_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]
_COUNTER_FORMS = {"하나": "한", "둘": "두", "셋": "세", "넷": "네"}


def native_korean(n: int) -> str:
    """Native Korean reading, 1–99 (the range native numbers cover)."""
    if not 1 <= n <= 99:
        raise ValueError("native Korean numbers run 1–99; use Sino-Korean above 99")
    return _NATIVE_TENS[n // 10] + _NATIVE_ONES[n % 10]


def native_counter(n: int) -> str:
    """Native number in the short form used before a counter (한 개, 스무 살)."""
    word = native_korean(n)
    for full, short in _COUNTER_FORMS.items():
        if word.endswith(full):
            return word[: -len(full)] + short
    if word == "스물":
        return "스무"
    return word


# ------------------------------------------------------------- mixed-system phrases

_MONTHS = [
    "", "일월", "이월", "삼월", "사월", "오월", "유월",
    "칠월", "팔월", "구월", "시월", "십일월", "십이월",
]  # 6월 → 유월, 10월 → 시월 are irregular.

_DIGIT_NAMES = {"0": "공", "1": "일", "2": "이", "3": "삼", "4": "사",
                "5": "오", "6": "육", "7": "칠", "8": "팔", "9": "구"}

_MATH_OPS = {
    "+": ("더하기", lambda a, b: a + b),
    "-": ("빼기", lambda a, b: a - b),
    "×": ("곱하기", lambda a, b: a * b),
    "÷": ("나누기", lambda a, b: a // b),
}


def date_korean(year: int, month: int, day: int) -> str:
    """Sino-Korean date: 2024-06-15 → 이천이십사년 유월 십오일."""
    return f"{sino_korean(year)}년 {_MONTHS[month]} {sino_korean(day)}일"


def time_korean(hour: int, minute: int) -> str:
    """Native hour + Sino minute: 3:15 → 세 시 십오 분 (3:00 → 세 시)."""
    phrase = f"{native_counter(hour)} 시"
    if minute:
        phrase += f" {sino_korean(minute)} 분"
    return phrase


def money_korean(won: int) -> str:
    """Sino-Korean amount: 5300 → 오천삼백 원."""
    return f"{sino_korean(won)} 원"


def phone_korean(digits: str) -> str:
    """Read a phone number digit by digit (0 → 공), grouping by the dashes."""
    return " ".join(
        "".join(_DIGIT_NAMES[ch] for ch in group)
        for group in digits.split("-")
    )


def ordinal_korean(n: int) -> str:
    """Native ordinal: 1st → 첫 번째, 3rd → 세 번째."""
    if n == 1:
        return "첫 번째"
    return f"{native_counter(n)} 번째"


def _has_batchim(word: str) -> bool:
    parts = decompose_syllable(word[-1]) if word else None
    return bool(parts and parts[2])


def math_korean(a: int, symbol: str, b: int) -> str:
    """Read a full equation: 7 - 2 = 5 → 칠 빼기 이는 오."""
    word, fn = _MATH_OPS[symbol]
    result = fn(a, b)
    marker = "은" if _has_batchim(sino_korean(b)) else "는"
    return f"{sino_korean(a)} {word} {sino_korean(b)}{marker} {sino_korean(result)}"


# ----------------------------------------------------------------- drill builder

# (counter, English gloss) — every one takes native numbers in counter form.
_COUNTERS = [
    ("개", "things"), ("명", "people"), ("마리", "animals"), ("권", "books"),
    ("장", "sheets"), ("잔", "cups"), ("병", "bottles"), ("살", "years old"),
    ("대", "cars/machines"), ("그릇", "bowls"), ("번", "times"),
]


def _english_ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _gen_sino(rng: random.Random) -> tuple[str, str, list[str]]:
    n = rng.randint(10, 99999)
    answer = sino_korean(n)
    return f"Sino-Korean number:  {n:,}", answer, [answer]


def _gen_native(rng: random.Random) -> tuple[str, str, list[str]]:
    n = rng.randint(1, 99)
    answer = native_korean(n)
    return f"Native-Korean number:  {n}", answer, [answer]


def _gen_count(rng: random.Random) -> tuple[str, str, list[str]]:
    n = rng.randint(1, 99)
    counter, gloss = rng.choice(_COUNTERS)
    answer = f"{native_counter(n)} {counter}"
    return f"Count:  {n} {counter}  ({gloss})", answer, [answer]


def _gen_money(rng: random.Random) -> tuple[str, str, list[str]]:
    won = rng.randint(1, 9999) * 100
    answer = money_korean(won)
    return f"Money:  ₩{won:,}", answer, [answer]


def _gen_date(rng: random.Random) -> tuple[str, str, list[str]]:
    year, month, day = rng.randint(1980, 2030), rng.randint(1, 12), rng.randint(1, 28)
    answer = date_korean(year, month, day)
    return f"Date:  {year}-{month:02d}-{day:02d}", answer, [answer]


def _gen_time(rng: random.Random) -> tuple[str, str, list[str]]:
    hour = rng.randint(1, 12)
    minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 40, 45, 50, 55])
    answer = time_korean(hour, minute)
    accept = [answer]
    if minute == 30:  # 3:30 is just as often "세 시 반".
        accept.append(f"{native_counter(hour)} 시 반")
    return f"Time:  {hour}:{minute:02d}", answer, accept


def _gen_math(rng: random.Random) -> tuple[str, str, list[str]]:
    symbol = rng.choice(["+", "-", "×", "÷"])
    if symbol == "+":
        a, b = rng.randint(1, 20), rng.randint(1, 20)
    elif symbol == "-":
        a = rng.randint(1, 20)
        b = rng.randint(0, a)
    elif symbol == "×":
        a, b = rng.randint(1, 9), rng.randint(1, 9)
    else:  # ÷ — build it from an exact quotient.
        b, quotient = rng.randint(1, 9), rng.randint(1, 9)
        a = b * quotient
    answer = math_korean(a, symbol, b)
    accept = [answer]
    if answer.endswith("영"):  # 5 - 5 = 0 reads 영, but 공 is also heard.
        accept.append(answer[:-1] + "공")
    return f"Solve:  {a} {symbol} {b} = ?", answer, accept


def _gen_phone(rng: random.Random) -> tuple[str, str, list[str]]:
    middle = "".join(str(rng.randint(0, 9)) for _ in range(4))
    last = "".join(str(rng.randint(0, 9)) for _ in range(4))
    number = f"010-{middle}-{last}"
    answer = phone_korean(number)
    return f"Phone number:  {number}", answer, [answer]


def _gen_ordinal(rng: random.Random) -> tuple[str, str, list[str]]:
    n = rng.randint(1, 30)
    answer = ordinal_korean(n)
    return f"Ordinal:  {_english_ordinal(n)}", answer, [answer]


# Insertion order is the round-robin order used by the mixed drill.
_GENERATORS = {
    "sino": _gen_sino,
    "native": _gen_native,
    "count": _gen_count,
    "money": _gen_money,
    "date": _gen_date,
    "time": _gen_time,
    "math": _gen_math,
    "phone": _gen_phone,
    "ordinal": _gen_ordinal,
}

NUMBER_CATEGORIES = list(_GENERATORS)


def build_number_items(
    seed: int | None = None,
    count: int = 10,
    category: str | None = None,
) -> list[dict]:
    """Drill items whose answers are Hangul number phrases.

    With no category (or "mix"), categories are rotated so every system and
    context appears. Each item carries ``no_digits`` so the shell can insist on
    Korean letters in the answer.
    """
    count = max(1, count)
    rng = random.Random(seed)
    if category in (None, "mix"):
        order = [NUMBER_CATEGORIES[i % len(NUMBER_CATEGORIES)] for i in range(count)]
    elif category in _GENERATORS:
        order = [category] * count
    else:
        raise ValueError(f"unknown number category: {category}")

    items: list[dict] = []
    for key in order:
        show, answer, accept = _GENERATORS[key](rng)
        items.append({
            "show": show,
            "accept": accept,
            "answer": answer,
            "speech": answer,
            "no_digits": True,
        })
    return items
