from __future__ import annotations

from typing import Any

from .question_types import get_question_type


def grade_question(question: dict[str, Any], response: str | None) -> dict[str, Any]:
    answer = question["answer"]
    points = int(question.get("points", 1))
    normalized_response = normalize_answer(response)
    correct = get_question_type(answer["type"]).grade(question, normalized_response)

    return {
        "question_id": question["question_id"],
        "correct": correct,
        "points_awarded": points if correct else 0,
        "max_points": points,
        "response": response or "",
        "feedback": build_feedback(question, correct),
    }


def grade_answers(pack_data: dict[str, Any], responses: dict[str, str]) -> dict[str, Any]:
    results = []
    for question in iter_questions(pack_data):
        results.append(grade_question(question, responses.get(question["question_id"])))

    score = sum(result["points_awarded"] for result in results)
    max_score = sum(result["max_points"] for result in results)
    return {
        "pack_id": pack_data["pack_id"],
        "score": score,
        "max_score": max_score,
        "results": results,
    }


def build_feedback(question: dict[str, Any], correct: bool) -> dict[str, Any]:
    explanation = question.get("explanation", {})
    prefix = "Correct." if correct else "Review this item."
    return {
        "summary": f"{prefix} {explanation.get('summary', '')}".strip(),
        "teaching_points": explanation.get("teaching_points", []),
        "vocabulary": explanation.get("vocabulary", []),
        "grammar": explanation.get("grammar", []),
        "common_mistakes": explanation.get("common_mistakes", []),
    }


def iter_questions(pack_data: dict[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for section in pack_data["sections"]:
        questions.extend(section["questions"])
    return sorted(questions, key=lambda item: int(item.get("order", 0)))


def normalize_answer(value: Any) -> str:
    return str(value or "").strip()

