from __future__ import annotations

import shutil
from typing import Any

from ..question_types import response_format_hint
from ..tts import is_listening_question
from . import ansi
from .commands import Command


def _width() -> int:
    return max(44, min(78, shutil.get_terminal_size((80, 24)).columns - 2))


def banner() -> str:
    width = _width()
    inner = width - 4
    rows = [
        "TOPIK Simulator",
        "/take <pack> start a test   /say <text> pronounce a sentence",
        "/help all commands          slash input is never your answer",
    ]
    lines = ["╭" + "─" * (width - 2) + "╮"]
    for index, row in enumerate(rows):
        padded = row.ljust(inner)[:inner]
        if index == 0:
            padded = ansi.style(padded, ansi.BOLD, ansi.CYAN)
        lines.append("│ " + padded + " │")
    lines.append("╰" + "─" * (width - 2) + "╯")
    return "\n".join(lines)


def rule(label: str = "") -> str:
    width = _width()
    if not label:
        return ansi.style("─" * width, ansi.GREY)
    body = f"── {label} "
    return ansi.style(body + "─" * max(0, width - len(body)), ansi.GREY)


def question_card(number: int, total: int, question: dict[str, Any], show_transcript: bool) -> str:
    lines = [rule(f"Question {number}/{total} · {question.get('question_id', '?')} · {question.get('skill', '?')}")]

    listening = is_listening_question(question)
    passage = str(question.get("passage", "")).strip()
    if listening and not show_transcript:
        lines.append(ansi.style("[listening] audio plays automatically · /replay to repeat · /transcript to peek", ansi.DIM))
    elif passage:
        lines.append(passage)

    audio_ref = str(question.get("audio_ref", ""))
    if audio_ref and not audio_ref.startswith("transcript-only:"):
        lines.append(ansi.style(f"Audio reference: {audio_ref}", ansi.DIM))

    lines.append(ansi.style(str(question.get("prompt", "")), ansi.BOLD))
    for option in question.get("options", []):
        lines.append(f"  {ansi.style(str(option.get('id', '?')), ansi.CYAN)}. {option.get('text', '')}")
    hint = response_format_hint(question)
    if hint:
        lines.append(ansi.style(f"({hint})", ansi.DIM))
    return "\n".join(lines)


def transcript_block(question: dict[str, Any]) -> str:
    passage = str(question.get("passage", "")).strip()
    if not passage:
        return "This question has no transcript."
    if passage.lower().startswith("transcript:"):
        return passage
    return f"Transcript: {passage}"


def feedback_block(result: dict[str, Any], question: dict[str, Any], transcript_was_shown: bool) -> str:
    lines = []
    if result["correct"]:
        lines.append(ansi.style("✓ Correct.", ansi.BOLD, ansi.GREEN))
    else:
        lines.append(ansi.style("✗ Not quite.", ansi.BOLD, ansi.RED))

    if is_listening_question(question) and not transcript_was_shown:
        lines.append(transcript_block(question))

    feedback = result.get("feedback", {})
    summary = str(feedback.get("summary", "")).strip()
    if summary:
        lines.append(summary)
    for point in feedback.get("teaching_points", []):
        lines.append(f"  • {point}")
    for item in feedback.get("vocabulary", []):
        note = f" ({item['note']})" if item.get("note") else ""
        lines.append(f"  • {item['ko']}: {item['en']}{note}")
    for item in feedback.get("grammar", []):
        lines.append(f"  • {item['pattern']}: {item['explanation']}")
    for mistake in feedback.get("common_mistakes", []):
        lines.append(f"  • Common mistake: {mistake}")
    return "\n".join(lines)


def continue_hint() -> str:
    return ansi.style("Enter → next · /replay hear again · /transcript · /pause save & leave", ansi.GREY)


def keyboard_chart() -> str:
    from ..hangul import LAYOUT_ROWS

    lines = [rule("두벌식 keyboard · left hand consonants, right hand vowels")]
    for row in LAYOUT_ROWS:
        keys_line = ""
        jamo_line = ""
        shift_line = ""
        has_shift = False
        for cell in row:
            if cell is None:
                keys_line += " │ "
                jamo_line += " │ "
                shift_line += " │ "
                continue
            key, jamo, shifted = cell
            keys_line += f" {ansi.style(key, ansi.BOLD, ansi.CYAN)}  "
            jamo_line += f" {jamo} "
            if shifted:
                shift_line += f" {shifted} "
                has_shift = True
            else:
                shift_line += "    "
        lines.append(keys_line)
        lines.append(jamo_line)
        if has_shift:
            lines.append(ansi.style(shift_line, ansi.DIM) + ansi.style("  ← Shift", ansi.DIM))
    lines.append(ansi.style("Compound vowels are sequences: ㅘ = ㅗ+ㅏ (hk) · ㅢ = ㅡ+ㅣ (ml)", ansi.GREY))
    return "\n".join(lines)


def keyboard_toolbar() -> str:
    """Compact 두벌식 chart for the bottom toolbar: plain text, no ANSI,
    because prompt_toolkit styles the toolbar itself."""
    from ..hangul import LAYOUT_ROWS

    lines = []
    shifted_jamo: list[str] = []
    for row in LAYOUT_ROWS:
        cells = []
        for cell in row:
            if cell is None:
                cells.append("│")
                continue
            key, jamo, shifted = cell
            cells.append(f"{jamo}{key.lower()}")
            if shifted:
                shifted_jamo.append(shifted)
        lines.append(" ".join(cells))
    lines[-1] += f"   ⇧ {''.join(shifted_jamo)}"
    return "\n".join(lines)


def format_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def summary_panel(attempt: dict[str, Any]) -> str:
    result = attempt.get("result") or {}
    answered = len(attempt.get("answers", []))
    total = len(attempt.get("question_ids", []))
    score = result.get("score", 0)
    max_score = result.get("max_score", 0)
    lines = [
        rule("Result"),
        f"Score: {ansi.style(f'{score}/{max_score}', ansi.BOLD, ansi.CYAN)}",
        f"Progress: {answered}/{total} answered",
        f"Activity: {attempt.get('activity', 'exam')}",
    ]
    elapsed = float(attempt.get("elapsed_seconds") or 0.0)
    if elapsed and answered:
        pace = f"Time: {format_clock(elapsed)} · {elapsed / answered:.0f}s/question"
        limit = attempt.get("time_limit_minutes")
        if limit:
            pace += f" · limit {format_clock(float(limit) * 60)}"
        lines.append(pace)
    lines.append(f"Attempt: {attempt.get('attempt_id', '?')}")
    return "\n".join(lines)


def help_table(commands: list[Command]) -> str:
    usage_width = max(len(command.usage) for command in commands)
    lines = [rule("Commands")]
    for command in commands:
        aliases = f" (also {', '.join('/' + alias for alias in command.aliases)})" if command.aliases else ""
        lines.append(f"  {ansi.style(command.usage.ljust(usage_width), ansi.CYAN)}  {command.description}{aliases}")
    lines.append("")
    lines.append(ansi.style("/help <command> explains its arguments with examples, e.g. /help typing.", ansi.BOLD))
    lines.append("Anything not starting with / is treated as your answer to the current question.")
    return "\n".join(lines)


def command_help(command: Command) -> str:
    lines = [rule(f"/{command.name}")]
    lines.append(f"Usage: {ansi.style(command.usage, ansi.CYAN)}")
    if command.aliases:
        lines.append(f"Aliases: {', '.join('/' + alias for alias in command.aliases)}")
    lines.append(command.description)
    if command.details:
        lines.append("")
        lines.extend(ansi.style(line, ansi.GREY) if line.startswith("Example") else line for line in command.details.splitlines())
    return "\n".join(lines)
