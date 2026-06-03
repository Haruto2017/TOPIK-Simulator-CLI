from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .attempts import complete_attempt, create_attempt, load_attempt, save_attempt_to_dir, answer_question
from .content import ContentValidationError, load_pack, validate_pack_file
from .grading import grade_answers, grade_question
from .library import DEFAULT_LIBRARY_DIR, import_pack, list_packs, load_pack_ref, validate_library


def main(argv: list[str] | None = None) -> int:
    configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except ContentValidationError as exc:
        print("Content pack is invalid:", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSimulation stopped.")
        return 130


def configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="topik-sim", description="TOPIK simulation CLI")
    subparsers = parser.add_subparsers(required=True)

    validate = subparsers.add_parser("validate-content", help="Validate a content pack JSON file.")
    validate.add_argument("pack")
    validate.set_defaults(handler=handle_validate_content)

    inspect = subparsers.add_parser("inspect-content", help="Inspect pack metadata and question counts.")
    inspect.add_argument("pack")
    inspect.set_defaults(handler=handle_inspect_content)

    simulate = subparsers.add_parser("simulate", help="Run an interactive TOPIK simulation.")
    simulate.add_argument("pack")
    simulate.add_argument("--section", help="Only run one section_id.")
    simulate.add_argument("--limit", type=int, help="Limit the number of questions.")
    simulate.add_argument("--show-teaching", action="store_true", help="Show teaching notes for correct answers too.")
    simulate.set_defaults(handler=handle_simulate)

    take = subparsers.add_parser("take", help="Take a test and save the attempt.")
    take.add_argument("pack_ref", help="Pack file path, pack_id, or pack_id@pack_version.")
    take.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
    take.add_argument("--attempt-dir", default="data/attempts", help="Directory for saved attempts.")
    take.add_argument("--section", help="Only run one section_id.")
    take.add_argument("--limit", type=int, help="Limit the number of questions.")
    take.add_argument("--show-teaching", action="store_true", help="Show teaching notes for correct answers too.")
    take.set_defaults(handler=handle_take)

    review = subparsers.add_parser("review-attempt", help="Review a saved attempt JSON file.")
    review.add_argument("attempt")
    review.set_defaults(handler=handle_review_attempt)

    grade = subparsers.add_parser("grade", help="Grade an answer JSON file.")
    grade.add_argument("pack")
    grade.add_argument("answers")
    grade.set_defaults(handler=handle_grade)

    import_content = subparsers.add_parser("import-pack", help="Import a content pack into the versioned library.")
    import_content.add_argument("pack")
    import_content.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
    import_content.add_argument("--replace", action="store_true", help="Replace an existing pack with the same id and version.")
    import_content.set_defaults(handler=handle_import_pack)

    list_content = subparsers.add_parser("list-packs", help="List packs in the content library.")
    list_content.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
    list_content.set_defaults(handler=handle_list_packs)

    validate_library_parser = subparsers.add_parser("validate-library", help="Validate the content library manifest and pack files.")
    validate_library_parser.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
    validate_library_parser.set_defaults(handler=handle_validate_library)

    return parser


def handle_validate_content(args: argparse.Namespace) -> int:
    errors = validate_pack_file(args.pack)
    if errors:
        print("Content pack is invalid:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Content pack is valid.")
    return 0


def handle_inspect_content(args: argparse.Namespace) -> int:
    pack = load_pack(args.pack)
    print(f"{pack.title} ({pack.pack_id})")
    print(f"Level: {pack.data['topik_level']}")
    print(f"Source: {pack.data['source_type']}")
    for section in pack.sections:
        question_count = len(section["questions"])
        print(f"- {section['section_id']}: {question_count} question(s)")
    return 0


def handle_simulate(args: argparse.Namespace) -> int:
    pack = load_pack(args.pack)
    questions = pack.questions(section_id=args.section)
    if args.limit is not None:
        questions = questions[: args.limit]

    if not questions:
        print("No questions matched this request.")
        return 1

    print(f"{pack.title}")
    print(f"{len(questions)} question(s)\n")

    results = []
    for index, question in enumerate(questions, start=1):
        print_question(index, question)
        response = input("Your answer: ")
        result = grade_question(question, response)
        results.append(result)
        print("Correct.\n" if result["correct"] else "Not quite.\n")
        if args.show_teaching or not result["correct"]:
            print_feedback(result["feedback"])

    score = sum(result["points_awarded"] for result in results)
    max_score = sum(result["max_points"] for result in results)
    print(f"Final score: {score}/{max_score}")
    return 0


def handle_take(args: argparse.Namespace) -> int:
    pack = resolve_pack(args.pack_ref, args.library)
    questions = pack.questions(section_id=args.section)
    if args.limit is not None:
        questions = questions[: args.limit]
    if not questions:
        print("No questions matched this request.")
        return 1

    attempt = create_attempt(pack, section_id=args.section, limit=args.limit)
    attempt_path = save_attempt_to_dir(attempt, args.attempt_dir)

    print(f"{pack.title}")
    print(f"Attempt: {attempt['attempt_id']}")
    print(f"{len(questions)} question(s)")
    print(f"Saving to: {attempt_path}\n")

    for index, question in enumerate(questions, start=1):
        print_question(index, question)
        response = input("Your answer: ")
        attempt = answer_question(attempt, pack, response)
        result = grade_question(question, response)
        print("Correct.\n" if result["correct"] else "Not quite.\n")
        if args.show_teaching or not result["correct"]:
            print_feedback(result["feedback"])
        save_attempt_to_dir(attempt, args.attempt_dir)

    attempt = complete_attempt(attempt, pack)
    save_attempt_to_dir(attempt, args.attempt_dir)
    print_attempt_summary(attempt)
    return 0


def handle_review_attempt(args: argparse.Namespace) -> int:
    attempt = load_attempt(args.attempt)
    print_attempt_summary(attempt)
    for result in (attempt.get("result") or {}).get("results", []):
        status = "correct" if result["correct"] else "missed"
        print(f"- {result['question_id']}: {status}, {result['points_awarded']}/{result['max_points']}")
        print(f"  {result['feedback']['summary']}")
    return 0


def handle_grade(args: argparse.Namespace) -> int:
    pack = load_pack(args.pack)
    responses = load_answer_file(args.answers)
    result = grade_answers(pack.data, responses)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def handle_import_pack(args: argparse.Namespace) -> int:
    try:
        entry = import_pack(args.pack, args.library, replace=args.replace)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Imported {entry['pack_id']}@{entry['pack_version']}")
    print(f"Questions: {entry['question_count']}")
    print(f"Checksum: {entry['checksum_sha256']}")
    return 0


def handle_list_packs(args: argparse.Namespace) -> int:
    packs = list_packs(args.library)
    if not packs:
        print("No packs imported.")
        return 0
    for pack in packs:
        print(f"{pack['pack_id']}@{pack['pack_version']} - {pack['title']} ({pack['question_count']} question(s))")
    return 0


def handle_validate_library(args: argparse.Namespace) -> int:
    errors = validate_library(args.library)
    if errors:
        print("Content library is invalid:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Content library is valid.")
    return 0


def resolve_pack(pack_ref: str, library_dir: str | Path) -> Any:
    pack_path = Path(pack_ref)
    if pack_path.exists():
        return load_pack(pack_path)
    return load_pack_ref(pack_ref, library_dir)


def load_answer_file(path: str | Path) -> dict[str, str]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data: Any = json.load(handle)

    if isinstance(data, dict) and isinstance(data.get("answers"), list):
        return {str(item["question_id"]): str(item.get("response", "")) for item in data["answers"]}
    if isinstance(data, dict):
        return {str(key): str(value) for key, value in data.items()}
    raise ValueError("Answer file must be an object or contain an answers array.")


def print_question(index: int, question: dict[str, Any]) -> None:
    print(f"Question {index}: {question['question_id']}")
    if question.get("passage"):
        print(question["passage"])
    if question.get("audio_ref"):
        print(f"Audio reference: {question['audio_ref']}")
    print(question["prompt"])
    for option in question.get("options", []):
        print(f"  {option['id']}. {option['text']}")


def print_feedback(feedback: dict[str, Any]) -> None:
    print(feedback["summary"])
    for point in feedback.get("teaching_points", []):
        print(f"- {point}")
    for item in feedback.get("vocabulary", []):
        note = f" ({item['note']})" if item.get("note") else ""
        print(f"- {item['ko']}: {item['en']}{note}")
    for item in feedback.get("grammar", []):
        print(f"- {item['pattern']}: {item['explanation']}")
    for mistake in feedback.get("common_mistakes", []):
        print(f"- Common mistake: {mistake}")
    print()


def print_attempt_summary(attempt: dict[str, Any]) -> None:
    result = attempt.get("result") or {}
    score = result.get("score", 0)
    max_score = result.get("max_score", 0)
    print(f"Final score: {score}/{max_score}")
    print(f"Status: {attempt['status']}")
    print(f"Attempt ID: {attempt['attempt_id']}")


if __name__ == "__main__":
    raise SystemExit(main())
