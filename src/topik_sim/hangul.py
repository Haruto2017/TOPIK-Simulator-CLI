from __future__ import annotations

"""Hangul ↔ 두벌식 (Dubeolsik) keyboard mapping.

Decomposes syllables into jamo by Unicode arithmetic and maps each jamo to
its QWERTY key. Uppercase letters in keystroke output mean Shift+key.
"""

SYLLABLE_BASE = 0xAC00
SYLLABLE_LAST = 0xD7A3

LEADS = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
VOWELS = ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ", "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"]
TAILS = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]

KEY_MAP = {
    "ㄱ": "r", "ㄲ": "R", "ㄴ": "s", "ㄷ": "e", "ㄸ": "E", "ㄹ": "f", "ㅁ": "a",
    "ㅂ": "q", "ㅃ": "Q", "ㅅ": "t", "ㅆ": "T", "ㅇ": "d", "ㅈ": "w", "ㅉ": "W",
    "ㅊ": "c", "ㅋ": "z", "ㅌ": "x", "ㅍ": "v", "ㅎ": "g",
    "ㅏ": "k", "ㅐ": "o", "ㅑ": "i", "ㅒ": "O", "ㅓ": "j", "ㅔ": "p", "ㅕ": "u",
    "ㅖ": "P", "ㅗ": "h", "ㅘ": "hk", "ㅙ": "ho", "ㅚ": "hl", "ㅛ": "y", "ㅜ": "n",
    "ㅝ": "nj", "ㅞ": "np", "ㅟ": "nl", "ㅠ": "b", "ㅡ": "m", "ㅢ": "ml", "ㅣ": "l",
    "ㄳ": "rt", "ㄵ": "sw", "ㄶ": "sg", "ㄺ": "fr", "ㄻ": "fa", "ㄼ": "fq",
    "ㄽ": "ft", "ㄾ": "fx", "ㄿ": "fv", "ㅀ": "fg", "ㅄ": "qt",
}

# (key, jamo, shifted-jamo) per column; None marks the left/right hand split.
LAYOUT_ROWS = [
    [("Q", "ㅂ", "ㅃ"), ("W", "ㅈ", "ㅉ"), ("E", "ㄷ", "ㄸ"), ("R", "ㄱ", "ㄲ"), ("T", "ㅅ", "ㅆ"), None,
     ("Y", "ㅛ", None), ("U", "ㅕ", None), ("I", "ㅑ", None), ("O", "ㅐ", "ㅒ"), ("P", "ㅔ", "ㅖ")],
    [("A", "ㅁ", None), ("S", "ㄴ", None), ("D", "ㅇ", None), ("F", "ㄹ", None), ("G", "ㅎ", None), None,
     ("H", "ㅗ", None), ("J", "ㅓ", None), ("K", "ㅏ", None), ("L", "ㅣ", None)],
    [("Z", "ㅋ", None), ("X", "ㅌ", None), ("C", "ㅊ", None), ("V", "ㅍ", None), None,
     ("B", "ㅠ", None), ("N", "ㅜ", None), ("M", "ㅡ", None)],
]


def decompose_syllable(char: str) -> tuple[str, str, str] | None:
    """Return (lead, vowel, tail) jamo for a precomposed syllable, else None."""
    code = ord(char)
    if not SYLLABLE_BASE <= code <= SYLLABLE_LAST:
        return None
    code -= SYLLABLE_BASE
    return LEADS[code // 588], VOWELS[(code % 588) // 28], TAILS[code % 28]


def compose_syllable(lead: str, vowel: str, tail: str = "") -> str:
    return chr(SYLLABLE_BASE + LEADS.index(lead) * 588 + VOWELS.index(vowel) * 28 + TAILS.index(tail))


def char_keystrokes(char: str) -> str | None:
    """Keystrokes for one character, or None for non-Hangul input."""
    parts = decompose_syllable(char)
    if parts is not None:
        lead, vowel, tail = parts
        return KEY_MAP[lead] + KEY_MAP[vowel] + (KEY_MAP[tail] if tail else "")
    return KEY_MAP.get(char)


def keystrokes(text: str, separator: str = "·") -> str:
    """Keystroke sequence for a sentence; syllables separated for readability.

    날씨 → skf·Tl. Non-Hangul characters pass through unchanged.
    """
    result = ""
    previous_was_keys = False
    for char in text:
        keys = char_keystrokes(char)
        if keys is None:
            result += char
            previous_was_keys = False
        else:
            if previous_was_keys:
                result += separator
            result += keys
            previous_was_keys = True
    return result


def uses_shift(keys: str) -> bool:
    return any(char.isalpha() and char.isupper() for char in keys)


def keystroke_hint(text: str) -> str:
    """Learner-facing hint line for one text."""
    keys = keystrokes(text)
    suffix = "  (uppercase = Shift)" if uses_shift(keys) else ""
    return f"Keys: {keys}{suffix}"
