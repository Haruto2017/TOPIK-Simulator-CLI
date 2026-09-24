from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from .content import ExamPack
from .tts import dedupe, is_listening_question, split_speaker_turns, transcript_text


def collect_dictation_turns(pack: ExamPack, limit: int | None = None) -> list[dict]:
    """Listening transcripts as speaker turns — one sentence per turn, speaker
    tags removed (a learner types what is *said*, never "남자:"), each carrying
    the role that should voice it."""
    turns: list[dict] = []
    seen: set[str] = set()
    for question in pack.questions():
        if not is_listening_question(question):
            continue
        for turn in split_speaker_turns(transcript_text(question)):
            if turn["text"] in seen:
                continue
            seen.add(turn["text"])
            turns.append(turn)
    if limit is not None:
        turns = turns[:limit]
    return turns


def collect_dictation_texts(pack: ExamPack, limit: int | None = None) -> list[str]:
    """The dictation sentences only (see collect_dictation_turns)."""
    return [turn["text"] for turn in collect_dictation_turns(pack, limit=limit)]


def normalize(text: str) -> str:
    return " ".join(text.split())


def accuracy(expected: str, typed: str) -> float:
    return SequenceMatcher(None, normalize(expected), normalize(typed)).ratio()


def feedback_lines(expected: str, typed: str, keyboard_hints: bool = False) -> list[str]:
    if normalize(expected) == normalize(typed):
        return ["Perfect! 100%"]
    lines = [f"Accuracy: {accuracy(expected, typed) * 100:.0f}%"]
    lines.append(f"Expected:  {expected}")
    lines.append(f"You typed: {typed if typed.strip() else '(nothing)'}")
    expected_words = normalize(expected).split()
    typed_words = normalize(typed).split()
    # Match on punctuation-stripped words so a missing period is not a missed word.
    strip_punctuation = lambda word: word.strip(".,!?;:·…\"'")  # noqa: E731
    matcher = SequenceMatcher(
        None,
        [strip_punctuation(word) for word in expected_words],
        [strip_punctuation(word) for word in typed_words],
    )
    missing: list[str] = []
    extra: list[str] = []
    for tag, e_start, e_end, t_start, t_end in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            missing.extend(expected_words[e_start:e_end])
        if tag in {"insert", "replace"}:
            extra.extend(typed_words[t_start:t_end])
    if missing:
        lines.append(f"Missing or wrong: {' '.join(missing)}")
    if extra:
        lines.append(f"Not in the sentence: {' '.join(extra)}")
    if keyboard_hints:
        from .hangul import keystroke_hint

        lines.append(keystroke_hint(expected))
    return lines
