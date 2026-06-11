from __future__ import annotations

from typing import Any

from .content import ExamPack


def describe_correct_answer(question: dict[str, Any]) -> str:
    answer = question.get("answer", {})
    answer_type = str(answer.get("type", ""))
    options = {str(option.get("id")): str(option.get("text", "")) for option in question.get("options", [])}
    if answer_type == "single_choice":
        option_id = str(answer.get("correct_option_id", "?"))
        return f"{option_id}. {options.get(option_id, '')}".strip()
    if answer_type == "short_answer":
        return " / ".join(str(value) for value in answer.get("accepted_answers", []))
    if answer_type == "multiple_select":
        ids = [str(value) for value in answer.get("correct_option_ids", [])]
        return ", ".join(f"{value}. {options.get(value, '')}".strip() for value in ids)
    if answer_type == "ordering":
        return " → ".join(str(value) for value in answer.get("correct_order", []))
    if answer_type == "cloze":
        firsts = [str((blank.get("accepted_answers") or ["?"])[0]) for blank in answer.get("blanks", [])]
        return " / ".join(firsts)
    return "(see explanation)"


def build_report(attempt: dict[str, Any], pack: ExamPack) -> str:
    result = attempt.get("result") or {}
    results = result.get("results", [])
    questions = {question["question_id"]: question for question in pack.questions()}
    missed = [item for item in results if not item.get("correct")]

    lines: list[str] = []
    lines.append(f"# Study Report — {pack.title}")
    lines.append("")
    completed = str(attempt.get("completed_at") or "")[:16].replace("T", " ")
    score = result.get("score", 0)
    max_score = result.get("max_score", 0)
    percent = f" ({100.0 * score / max_score:.0f}%)" if max_score else ""
    lines.append(f"- Attempt: `{attempt.get('attempt_id', '?')}` ({attempt.get('activity', 'exam')})")
    lines.append(f"- Completed: {completed or 'unknown'}")
    lines.append(f"- Score: **{score}/{max_score}**{percent}")
    elapsed = float(attempt.get("elapsed_seconds") or 0.0)
    if elapsed and results:
        minutes, seconds = divmod(int(elapsed), 60)
        lines.append(f"- Time: {minutes:02d}:{seconds:02d} ({elapsed / len(results):.0f}s/question)")
    lines.append("")

    if not missed:
        lines.append("Perfect score — nothing to review. 잘했어요!")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"## Missed questions ({len(missed)})")
    lines.append("")
    vocabulary: list[tuple[str, str, str]] = []
    grammar: list[tuple[str, str]] = []
    mistakes: list[str] = []
    for item in missed:
        question = questions.get(item["question_id"])
        if question is None:
            continue
        explanation = question.get("explanation", {})
        lines.append(f"### {item['question_id']}")
        passage = str(question.get("passage", "")).strip()
        if passage:
            lines.append(f"> {passage}")
        lines.append(f"- Prompt: {question.get('prompt', '')}")
        lines.append(f"- Your answer: {item.get('response') or '(blank)'}")
        lines.append(f"- Correct answer: {describe_correct_answer(question)}")
        summary = str(explanation.get("summary", "")).strip()
        if summary:
            lines.append(f"- Why: {summary}")
        for point in explanation.get("teaching_points", []):
            lines.append(f"  - {point}")
        lines.append("")
        for entry in explanation.get("vocabulary", []):
            vocabulary.append((str(entry.get("ko", "")), str(entry.get("en", "")), str(entry.get("note", "") or "")))
        for entry in explanation.get("grammar", []):
            grammar.append((str(entry.get("pattern", "")), str(entry.get("explanation", ""))))
        mistakes.extend(str(text) for text in explanation.get("common_mistakes", []))

    if vocabulary:
        lines.append("## Vocabulary to review")
        lines.append("")
        lines.append("| Korean | English | Note |")
        lines.append("| --- | --- | --- |")
        for ko, en, note in dict.fromkeys(vocabulary):
            lines.append(f"| {ko} | {en} | {note} |")
        lines.append("")

    if grammar:
        lines.append("## Grammar to review")
        lines.append("")
        for pattern, explanation_text in dict.fromkeys(grammar):
            lines.append(f"- **{pattern}** — {explanation_text}")
        lines.append("")

    if mistakes:
        lines.append("## Watch out for")
        lines.append("")
        for text in dict.fromkeys(mistakes):
            lines.append(f"- {text}")
        lines.append("")

    return "\n".join(lines)
