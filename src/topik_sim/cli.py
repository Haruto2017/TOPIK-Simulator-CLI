from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .attempts import (
    answer_question,
    attempt_progress,
    complete_attempt,
    create_attempt,
    find_question,
    load_attempt,
    remaining_question_ids,
    save_attempt,
    save_attempt_to_dir,
)
from .activities import create_drill_attempt
from .audio_cache import cache_stats, prune_cache, warm_pack
from .config import config_value, load_config
from .content import ContentValidationError, load_pack, validate_pack_file
from .facts import DEFAULT_FACTS_PATH
from .grading import grade_answers, grade_question
from .library import (
    DEFAULT_LIBRARY_DIR,
    import_pack,
    list_packs,
    load_pack_ref,
    set_pack_hidden,
    validate_library,
)
from .question_types import response_format_hint
from .tts import (
    DEFAULT_AUDIO_DIR,
    TTSConfig,
    build_provider,
    collect_question_speech_texts,
    is_listening_question,
    play_audio,
    synthesize_many,
)
from .tts_cli import add_tts_arguments, build_tts_config


REPLAY_COMMANDS = {"/replay", "/r", "replay"}
DEFAULT_RECENT_ATTEMPT_LIMIT = 10


def main(argv: list[str] | None = None) -> int:
    configure_output()
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["shell"]
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except ContentValidationError as exc:
        print("Content pack is invalid:", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSimulation stopped.")
        return 130


def configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    # Piped stdin (scripted sessions) should accept UTF-8 and ignore a BOM;
    # interactive consoles keep their own working encoding.
    try:
        if hasattr(sys.stdin, "reconfigure") and not sys.stdin.isatty():
            sys.stdin.reconfigure(encoding="utf-8-sig", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def build_parser() -> argparse.ArgumentParser:
    config = load_config()
    library_default = str(config_value(config, "paths", "library", DEFAULT_LIBRARY_DIR))
    attempts_default = str(config_value(config, "paths", "attempts", "data/attempts"))
    audio_default = str(config_value(config, "tts", "output_dir", DEFAULT_AUDIO_DIR))

    parser = argparse.ArgumentParser(prog="topik-sim", description="TOPIK simulation CLI")
    parser.add_argument("--version", action="version", version=f"topik-sim {__version__}")
    subparsers = parser.add_subparsers(required=True)

    setup = subparsers.add_parser("setup", help="Import the bundled exam packs into the library (idempotent).")
    setup.add_argument("--library", default=library_default, help="Content library directory.")
    setup.add_argument("--source-dir", default=str(Path("content") / "source"), help="Directory of bundled pack JSON files.")
    setup.set_defaults(handler=handle_setup)

    doctor = subparsers.add_parser("doctor", help="Diagnose the environment: Python, TTS, ffmpeg, config, library, data dir.")
    doctor.add_argument("--library", default=library_default, help="Content library directory.")
    doctor.add_argument("--data-dir", default="data", help="Writable data directory to probe.")
    doctor.set_defaults(handler=handle_doctor)

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
    simulate.add_argument("--show-teaching", action="store_true", help="Compatibility flag; feedback is always shown.")
    simulate.set_defaults(handler=handle_simulate)

    take = subparsers.add_parser("take", help="Take a test and save the attempt.")
    take.add_argument("pack_ref", help="Pack file path, pack_id, or pack_id@pack_version.")
    take.add_argument("--library", default=library_default, help="Content library directory.")
    take.add_argument("--attempt-dir", default=attempts_default, help="Directory for saved attempts.")
    take.add_argument("--section", help="Only run one section_id.")
    take.add_argument("--limit", type=int, help="Limit the number of questions.")
    take.add_argument("--show-teaching", action="store_true", help="Compatibility flag; feedback is always shown.")
    take.add_argument("--show-transcript", action="store_true", help="Show listening transcripts while taking a test.")
    add_tts_arguments(take)
    take.add_argument("--speak-question", action="store_true", help="Generate Korean audio for each question while taking a test.")
    take.add_argument("--speak-teaching", action="store_true", help="Generate Korean audio for vocabulary and example sentences in teaching notes.")
    take.add_argument("--no-listening-audio", action="store_true", help="Do not automatically play audio for listening questions.")
    take.set_defaults(handler=handle_take)

    shell_parser = subparsers.add_parser("shell", help="Interactive shell with slash commands (default with no arguments).")
    shell_parser.add_argument("--library", default=library_default, help="Content library directory.")
    shell_parser.add_argument("--attempt-dir", default=attempts_default, help="Directory for saved attempts.")
    shell_parser.add_argument("--show-transcript", action="store_true", help="Show listening transcripts while taking a test.")
    add_tts_arguments(shell_parser)
    shell_parser.set_defaults(handler=handle_shell)

    drill = subparsers.add_parser("drill", help="Re-practice the questions missed in a completed attempt.")
    drill.add_argument("attempt", help="Path to a completed attempt JSON file.")
    drill.add_argument("--library", default=library_default, help="Content library directory.")
    drill.add_argument("--attempt-dir", default=attempts_default, help="Directory for saved attempts.")
    drill.add_argument("--show-transcript", action="store_true", help="Show listening transcripts while drilling.")
    add_tts_arguments(drill)
    drill.set_defaults(handler=handle_drill)

    review_parser = subparsers.add_parser("review", help="Spaced-repetition review of previously missed questions.")
    review_parser.add_argument("pack_ref", nargs="?", help="Pack id to review. Omit to list due counts per pack.")
    review_parser.add_argument("--library", default=library_default, help="Content library directory.")
    review_parser.add_argument("--attempt-dir", default=attempts_default, help="Directory for saved attempts.")
    review_parser.add_argument("--limit", type=int, default=20, help="Maximum review items per session.")
    review_parser.add_argument("--show-transcript", action="store_true", help="Show listening transcripts while reviewing.")
    add_tts_arguments(review_parser)
    review_parser.set_defaults(handler=handle_review)

    review_writing = subparsers.add_parser("review-writing", help="Score essay answers in a completed attempt against their rubric.")
    review_writing.add_argument("attempt", help="Path to a completed attempt JSON file.")
    review_writing.add_argument("--library", default=library_default, help="Content library directory.")
    review_writing.set_defaults(handler=handle_review_writing)

    review = subparsers.add_parser("review-attempt", help="Review a saved attempt JSON file.")
    review.add_argument("attempt")
    review.set_defaults(handler=handle_review_attempt)

    list_attempts = subparsers.add_parser("list-attempts", help="List recent saved attempts.")
    list_attempts.add_argument("--attempt-dir", default=attempts_default, help="Directory for saved attempts.")
    list_attempts.add_argument("--limit", type=int, default=DEFAULT_RECENT_ATTEMPT_LIMIT, help="Maximum attempts to show.")
    list_attempts.set_defaults(handler=handle_list_attempts)

    resume = subparsers.add_parser("resume-attempt", help="Continue a saved in-progress attempt.")
    resume.add_argument("attempt", nargs="?", help="Path to an attempt JSON file. Omit to choose from recent attempts.")
    resume.add_argument("--attempt-dir", default=attempts_default, help="Directory to scan when no attempt path is given.")
    resume.add_argument("--recent", type=int, default=DEFAULT_RECENT_ATTEMPT_LIMIT, help="Maximum recent attempts to show when choosing.")
    resume.add_argument("--library", default=library_default, help="Content library directory.")
    resume.add_argument("--show-transcript", action="store_true", help="Show listening transcripts before answering too.")
    add_tts_arguments(resume)
    resume.add_argument("--speak-question", action="store_true", help="Generate Korean audio for each question while taking a test.")
    resume.add_argument("--speak-teaching", action="store_true", help="Generate Korean audio for vocabulary and example sentences in teaching notes.")
    resume.add_argument("--no-listening-audio", action="store_true", help="Do not automatically play audio for listening questions.")
    resume.set_defaults(handler=handle_resume_attempt)

    grade = subparsers.add_parser("grade", help="Grade an answer JSON file.")
    grade.add_argument("pack")
    grade.add_argument("answers")
    grade.set_defaults(handler=handle_grade)

    import_content = subparsers.add_parser("import-pack", help="Import a content pack into the versioned library.")
    import_content.add_argument("pack")
    import_content.add_argument("--library", default=library_default, help="Content library directory.")
    import_content.add_argument("--replace", action="store_true", help="Replace an existing pack with the same id and version.")
    import_content.set_defaults(handler=handle_import_pack)

    list_content = subparsers.add_parser("list-packs", help="List packs in the content library, grouped by level.")
    list_content.add_argument("--library", default=library_default, help="Content library directory.")
    list_content.add_argument("--all", action="store_true", help="Include hidden packs (marked [hidden]).")
    list_content.set_defaults(handler=handle_list_packs)

    hide_pack = subparsers.add_parser("hide-pack", help="Hide a pack from pickers and practice pools (still loadable by ref).")
    hide_pack.add_argument("pack_id", help="Pack id; every imported version is hidden.")
    hide_pack.add_argument("--library", default=library_default, help="Content library directory.")
    hide_pack.set_defaults(handler=handle_hide_pack)

    show_pack = subparsers.add_parser("show-pack", help="Unhide a previously hidden pack.")
    show_pack.add_argument("pack_id", help="Pack id; every imported version is unhidden.")
    show_pack.add_argument("--library", default=library_default, help="Content library directory.")
    show_pack.set_defaults(handler=handle_show_pack)

    validate_library_parser = subparsers.add_parser("validate-library", help="Validate the content library manifest and pack files.")
    validate_library_parser.add_argument("--library", default=library_default, help="Content library directory.")
    validate_library_parser.set_defaults(handler=handle_validate_library)

    report = subparsers.add_parser("report", help="Write a Markdown study report for a completed attempt.")
    report.add_argument("attempt", help="Path to a completed attempt JSON file.")
    report.add_argument("--library", default=library_default, help="Content library directory.")
    report.add_argument("--output", help="Write to this file instead of stdout.")
    report.set_defaults(handler=handle_report)

    stats_parser = subparsers.add_parser("stats", help="Show per-skill accuracy and trends across completed attempts.")
    stats_parser.add_argument("--attempt-dir", default=attempts_default, help="Directory for saved attempts.")
    stats_parser.add_argument("--library", default=library_default, help="Content library directory.")
    stats_parser.set_defaults(handler=handle_stats)

    facts_parser = subparsers.add_parser("facts", help="Show an interesting fact about Korea with Korean and learning notes.")
    facts_parser.add_argument("category", nargs="?", help="Filter to a category (see --list).")
    facts_parser.add_argument("--list", action="store_true", help="List the available fact categories.")
    facts_parser.add_argument("--facts-file", default=str(DEFAULT_FACTS_PATH), help="Facts JSON data file.")
    facts_parser.set_defaults(handler=handle_facts)

    audio = subparsers.add_parser("audio", help="Manage the generated audio cache.")
    audio_sub = audio.add_subparsers(required=True)

    audio_stats = audio_sub.add_parser("stats", help="Show audio cache size and file count.")
    audio_stats.add_argument("--audio-dir", default=audio_default, help="Audio cache directory.")
    audio_stats.set_defaults(handler=handle_audio_stats)

    audio_prune = audio_sub.add_parser("prune", help="Delete least-recently-used cached audio.")
    audio_prune.add_argument("--audio-dir", default=audio_default, help="Audio cache directory.")
    audio_prune.add_argument("--max-mb", type=float, help="Keep the cache under this many megabytes.")
    audio_prune.add_argument("--older-than-days", type=float, help="Remove audio unused for this many days.")
    audio_prune.add_argument("--dry-run", action="store_true", help="Report what would be removed without deleting.")
    audio_prune.set_defaults(handler=handle_audio_prune)

    audio_warm = audio_sub.add_parser("warm", help="Pre-generate audio for a pack so playback never waits.")
    audio_warm.add_argument("pack_ref", help="Pack file path, pack_id, or pack_id@pack_version.")
    audio_warm.add_argument("--library", default=library_default, help="Content library directory.")
    audio_warm.add_argument("--all-questions", action="store_true", help="Warm every question passage, not just listening.")
    audio_warm.add_argument("--teaching", action="store_true", help="Also warm vocabulary and grammar example audio.")
    audio_warm.add_argument("--voices", help="Comma-separated voice presets to warm for A/B comparison, e.g. F1,M1.")
    add_tts_arguments(audio_warm)
    audio_warm.set_defaults(handler=handle_audio_warm)

    audio_compress = audio_sub.add_parser("compress", help="Transcode cold cache WAVs to Opus via ffmpeg.")
    audio_compress.add_argument("--audio-dir", default=audio_default, help="Audio cache directory.")
    audio_compress.add_argument("--older-than-days", type=float, help="Only compress audio unused for this many days.")
    audio_compress.add_argument("--bitrate", default="24k", help="Opus bitrate (24k suits speech).")
    audio_compress.set_defaults(handler=handle_audio_compress)

    audio_bundle = audio_sub.add_parser("bundle", help="Export a pack's warmed audio plus manifest as a zip.")
    audio_bundle.add_argument("pack_ref", help="Pack file path, pack_id, or pack_id@pack_version.")
    audio_bundle.add_argument("--library", default=library_default, help="Content library directory.")
    audio_bundle.add_argument("--output", help="Zip path. Defaults to exports/<pack_id>-<version>-audio.zip.")
    audio_bundle.add_argument("--all-questions", action="store_true", help="Bundle every question passage, not just listening.")
    audio_bundle.add_argument("--teaching", action="store_true", help="Also bundle vocabulary and grammar example audio.")
    add_tts_arguments(audio_bundle)
    audio_bundle.set_defaults(handler=handle_audio_bundle)

    speak = subparsers.add_parser("speak", help="Generate Korean TTS audio for direct text.")
    speak.add_argument("text", nargs="+", help="Text to synthesize.")
    add_tts_arguments(speak)
    speak.set_defaults(handler=handle_speak)

    list_speakers = subparsers.add_parser("list-tts-speakers", help="List voices exposed by the selected TTS provider.")
    add_tts_arguments(list_speakers)
    list_speakers.set_defaults(handler=handle_list_tts_speakers)

    return parser


def handle_setup(args: argparse.Namespace) -> int:
    from .workspace import format_setup_summary, setup_workspace

    result = setup_workspace(args.library, source_dir=args.source_dir)
    for line in format_setup_summary(result):
        print(line)
    counts = result["counts"]
    if counts["total"] == 0:
        return 0
    if counts["failed"] == counts["total"]:
        return 1
    print("Start studying: python -m topik_sim (press Enter for the menu).")
    return 0


def handle_doctor(args: argparse.Namespace) -> int:
    from .doctor import format_checks, has_failure, run_checks

    checks = run_checks(library_dir=args.library, data_dir=args.data_dir)
    for line in format_checks(checks):
        print(line)
    return 1 if has_failure(checks) else 0


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
    questions = pack.questions()
    print(f"{pack.title} ({pack.pack_id})")
    print(f"Level: {pack.data['topik_level']}")
    print(f"Source: {pack.data['source_type']}")
    for section in pack.sections:
        question_count = len(section["questions"])
        limit = section.get("time_limit_minutes")
        limit_note = f", {limit} min" if limit else ""
        print(f"- {section['section_id']}: {question_count} question(s){limit_note}")

    print(f"Questions: {len(questions)}, total points: {sum(int(q.get('points', 1)) for q in questions)}")
    print(f"Skills: {format_counter(count_by(questions, 'skill'))}")
    print(f"Answer types: {format_counter(count_by(questions, ('answer', 'type')))}")
    difficulties = count_by(questions, "difficulty", missing="unrated")
    if set(difficulties) != {"unrated"}:
        print(f"Difficulty: {format_counter(difficulties)}")
    return 0


def count_by(questions: list[dict[str, Any]], key: str | tuple[str, str], missing: str = "unknown") -> dict[str, int]:
    counts: dict[str, int] = {}
    for question in questions:
        if isinstance(key, tuple):
            value = (question.get(key[0]) or {}).get(key[1])
        else:
            value = question.get(key)
        label = str(value) if value is not None else missing
        counts[label] = counts.get(label, 0) + 1
    return counts


def format_counter(counts: dict[str, int]) -> str:
    return ", ".join(f"{label} ({count})" for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])))


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
        print_feedback(result["feedback"])
        prompt_after_answer([])

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
    tts_config = build_tts_config(args)

    attempt = run_attempt_questions(
        attempt=attempt,
        pack=pack,
        questions=questions,
        save_path=attempt_path,
        tts_config=tts_config,
        show_transcript=args.show_transcript,
        speak_question_audio=args.speak_question,
        speak_teaching=args.speak_teaching,
        no_listening_audio=args.no_listening_audio,
        tts_play=args.tts_play,
        start_index=1,
    )

    attempt = complete_attempt(attempt, pack)
    save_attempt(attempt, attempt_path)
    record_review_queue(attempt, args.attempt_dir)
    print_attempt_summary(attempt)
    return 0


def handle_resume_attempt(args: argparse.Namespace) -> int:
    attempt_path = Path(args.attempt) if args.attempt else choose_recent_attempt(args.attempt_dir, args.recent)
    if attempt_path is None:
        return 1
    attempt = load_attempt(attempt_path)
    pack = resolve_pack(f"{attempt['pack_id']}@{attempt['pack_version']}", args.library)
    validate_attempt_questions(attempt, pack)
    answered_count, total_count = attempt_progress(attempt)

    print(f"{pack.title}")
    print(f"Attempt: {attempt['attempt_id']}")
    print(f"Progress: {answered_count}/{total_count} answered")
    print(f"Saving to: {attempt_path}\n")

    if attempt.get("status") == "completed":
        print("This attempt is already completed.")
        print_attempt_summary(attempt)
        return 0

    question_ids = remaining_question_ids(attempt)
    if not question_ids:
        attempt = complete_attempt(attempt, pack)
        save_attempt(attempt, attempt_path)
        print_attempt_summary(attempt)
        return 0

    questions = [find_question(pack, question_id) for question_id in question_ids]
    tts_config = build_tts_config(args)
    attempt = run_attempt_questions(
        attempt=attempt,
        pack=pack,
        questions=questions,
        save_path=attempt_path,
        tts_config=tts_config,
        show_transcript=args.show_transcript,
        speak_question_audio=args.speak_question,
        speak_teaching=args.speak_teaching,
        no_listening_audio=args.no_listening_audio,
        tts_play=args.tts_play,
        start_index=answered_count + 1,
    )

    attempt = complete_attempt(attempt, pack)
    save_attempt(attempt, attempt_path)
    # The queue lives next to the attempt being resumed, which may not be in --attempt-dir.
    record_review_queue(attempt, attempt_path.parent)
    print_attempt_summary(attempt)
    return 0


def handle_shell(args: argparse.Namespace) -> int:
    from .ui.shell import run_shell

    config = load_config()
    return run_shell(
        library_dir=args.library,
        attempt_dir=args.attempt_dir,
        tts_config=build_tts_config(args),
        show_transcript=args.show_transcript or bool(config_value(config, "shell", "show_transcript", False)),
        audio_enabled=bool(config_value(config, "shell", "audio", True)),
        keyboard_hints=bool(config_value(config, "shell", "keyboard_hints", False)),
        keyboard_pinned=bool(config_value(config, "shell", "keyboard_pinned", False)),
    )


def handle_drill(args: argparse.Namespace) -> int:
    source = load_attempt(args.attempt)
    pack = resolve_pack(f"{source['pack_id']}@{source['pack_version']}", args.library)
    attempt = create_drill_attempt(pack, source)
    attempt_path = save_attempt_to_dir(attempt, args.attempt_dir)
    questions = [find_question(pack, question_id) for question_id in attempt["question_ids"]]

    print(f"Drill: {pack.title}")
    print(f"Attempt: {attempt['attempt_id']}")
    print(f"{len(questions)} missed question(s)")
    print(f"Saving to: {attempt_path}\n")

    tts_config = build_tts_config(args)
    attempt = run_attempt_questions(
        attempt=attempt,
        pack=pack,
        questions=questions,
        save_path=attempt_path,
        tts_config=tts_config,
        show_transcript=args.show_transcript,
        speak_question_audio=False,
        speak_teaching=False,
        no_listening_audio=False,
        tts_play=args.tts_play,
        start_index=1,
    )

    attempt = complete_attempt(attempt, pack)
    save_attempt(attempt, attempt_path)
    record_review_queue(attempt, args.attempt_dir)
    print_attempt_summary(attempt)
    return 0


def handle_review(args: argparse.Namespace) -> int:
    from . import srs

    queue = srs.load_queue(srs.queue_path_for(args.attempt_dir))
    if not args.pack_ref:
        counts = srs.due_counts_by_pack(queue)
        if not counts:
            print("Nothing is due for review.")
            return 0
        for pack_id, count in sorted(counts.items()):
            print(f"{pack_id}: {count} due")
        print("Run: python -m topik_sim review <pack_id>")
        return 0

    pack = resolve_pack(args.pack_ref, args.library)
    try:
        attempt = srs.create_review_attempt(pack, queue, limit=args.limit)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    attempt_path = save_attempt_to_dir(attempt, args.attempt_dir)
    questions = [find_question(pack, question_id) for question_id in attempt["question_ids"]]

    print(f"Review: {pack.title}")
    print(f"Attempt: {attempt['attempt_id']}")
    print(f"{len(questions)} item(s) due")
    print(f"Saving to: {attempt_path}\n")

    tts_config = build_tts_config(args)
    attempt = run_attempt_questions(
        attempt=attempt,
        pack=pack,
        questions=questions,
        save_path=attempt_path,
        tts_config=tts_config,
        show_transcript=args.show_transcript,
        speak_question_audio=False,
        speak_teaching=False,
        no_listening_audio=False,
        tts_play=args.tts_play,
        start_index=1,
    )

    attempt = complete_attempt(attempt, pack)
    save_attempt(attempt, attempt_path)
    record_review_queue(attempt, args.attempt_dir)
    print_attempt_summary(attempt)
    return 0


def handle_review_writing(args: argparse.Namespace) -> int:
    from .stats import resolve_attempt_pack

    attempt_path = Path(args.attempt)
    attempt = load_attempt(attempt_path)
    if attempt.get("status") != "completed":
        print("review-writing needs a completed attempt. Resume and finish it first.", file=sys.stderr)
        return 1
    pack = resolve_attempt_pack(attempt, args.library)
    if pack is None:
        print("The attempt's pack could not be loaded from the library or its source path.", file=sys.stderr)
        return 1

    result = attempt.get("result") or {}
    pending = [item for item in result.get("results", []) if item.get("needs_review")]
    if not pending:
        print("Nothing is awaiting manual review in this attempt.")
        return 0

    for item in pending:
        question = find_question(pack, item["question_id"])
        print(f"\n{question['question_id']}: {question.get('prompt', '')}")
        passage = str(question.get("passage", "")).strip()
        if passage:
            print(passage)
        print(f"Learner answer: {item.get('response') or '(blank)'}")
        criteria = question["answer"]["rubric"]["criteria"]
        scores: dict[str, int] = {}
        for criterion in criteria:
            name = str(criterion["name"])
            max_points = int(criterion["max_points"])
            scores[name] = prompt_for_score(name, max_points)
        awarded = min(sum(scores.values()), int(item.get("max_points", 0)))
        item["manual_scores"] = scores
        item["points_awarded"] = awarded
        # Correct means at least half marks; full rigor would demand a perfect essay every time.
        item["correct"] = awarded * 2 >= int(item.get("max_points", 0))
        item["needs_review"] = False
        item["feedback"]["summary"] = f"Scored {awarded}/{item.get('max_points', 0)} by manual review."
        print(f"Recorded {awarded}/{item.get('max_points', 0)}.")

    result["score"] = sum(int(entry.get("points_awarded", 0)) for entry in result.get("results", []))
    attempt["result"] = result
    attempt["updated_at"] = utc_now_iso()
    save_attempt(attempt, attempt_path)
    print(f"\nUpdated score: {result['score']}/{result.get('max_score', 0)}")
    print(f"Saved to: {attempt_path}")
    return 0


def prompt_for_score(name: str, max_points: int) -> int:
    while True:
        value = input(f"  {name} (0-{max_points}): ").strip()
        if value.isdigit() and 0 <= int(value) <= max_points:
            return int(value)
        print(f"  Enter a whole number from 0 to {max_points}.")


def utc_now_iso() -> str:
    from datetime import timezone

    return datetime.now(timezone.utc).isoformat()


def record_review_queue(attempt: dict[str, Any], attempt_dir: str | Path) -> None:
    from . import srs

    queue_path = srs.queue_path_for(attempt_dir)
    queue = srs.load_queue(queue_path)
    if srs.record_attempt(queue, attempt):
        srs.save_queue(queue, queue_path)


def handle_list_attempts(args: argparse.Namespace) -> int:
    entries = recent_attempt_entries(args.attempt_dir, args.limit)
    if not entries:
        print(f"No saved attempts found in {args.attempt_dir}.")
        return 0
    print_recent_attempts(entries)
    return 0


def run_attempt_questions(
    attempt: dict[str, Any],
    pack: Any,
    questions: list[dict[str, Any]],
    save_path: Path,
    tts_config: TTSConfig,
    show_transcript: bool,
    speak_question_audio: bool,
    speak_teaching: bool,
    no_listening_audio: bool,
    tts_play: bool,
    start_index: int,
) -> dict[str, Any]:
    for offset, question in enumerate(questions):
        index = start_index + offset
        listening_audio = is_listening_question(question) and not no_listening_audio
        question_audio_paths: list[Path] = []
        if speak_question_audio or listening_audio:
            question_audio_paths = speak_question(
                question,
                tts_config,
                include_explanation=False,
                playback=listening_audio or tts_play,
            )
        print_question(index, question, show_transcript=show_transcript)
        question_started = time.monotonic()
        response = prompt_for_answer(question_audio_paths, volume=tts_config.volume)
        duration = time.monotonic() - question_started
        attempt = answer_question(attempt, pack, response, duration_seconds=duration)
        save_attempt(attempt, save_path)
        result = grade_question(question, response)
        print("Correct.\n" if result["correct"] else "Not quite.\n")
        print_post_answer_transcript(question, was_shown_before_answer=show_transcript)
        print_feedback(result["feedback"])
        if speak_teaching:
            speak_question(question, tts_config, include_explanation=True, playback=tts_play)
        prompt_after_answer(question_audio_paths, volume=tts_config.volume)
    return attempt


def validate_attempt_questions(attempt: dict[str, Any], pack: Any) -> None:
    for question_id in attempt.get("question_ids", []):
        find_question(pack, question_id)


def recent_attempt_entries(attempt_dir: str | Path, limit: int = DEFAULT_RECENT_ATTEMPT_LIMIT) -> list[tuple[Path, dict[str, Any]]]:
    if limit <= 0:
        raise ValueError("--limit/--recent must be greater than 0.")
    directory = Path(attempt_dir)
    if not directory.exists():
        return []

    entries: list[tuple[Path, dict[str, Any]]] = []
    for path in directory.glob("*.json"):
        try:
            attempt = load_attempt(path)
        except (OSError, json.JSONDecodeError):
            continue
        entries.append((path, attempt))

    entries.sort(key=attempt_sort_key, reverse=True)
    return entries[:limit]


def attempt_sort_key(entry: tuple[Path, dict[str, Any]]) -> tuple[str, float]:
    path, attempt = entry
    timestamp = str(attempt.get("updated_at") or attempt.get("completed_at") or attempt.get("started_at") or "")
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return timestamp, mtime


def choose_recent_attempt(attempt_dir: str | Path, limit: int) -> Path | None:
    entries = recent_attempt_entries(attempt_dir, limit)
    if not entries:
        print(f"No saved attempts found in {attempt_dir}.")
        return None

    print_recent_attempts(entries)
    while True:
        value = input("Choose attempt number (or blank to cancel): ").strip()
        if not value:
            print("Resume cancelled.")
            return None
        if not value.isdigit():
            print("Enter a number from the list.")
            continue
        index = int(value)
        if 1 <= index <= len(entries):
            return entries[index - 1][0]
        print("Enter a number from the list.")


def print_recent_attempts(entries: list[tuple[Path, dict[str, Any]]]) -> None:
    print("Recent attempts:")
    for index, (path, attempt) in enumerate(entries, start=1):
        print(format_attempt_entry(index, path, attempt))


def format_attempt_entry(index: int, path: Path, attempt: dict[str, Any]) -> str:
    answered_count, total_count = attempt_progress(attempt)
    pack_ref = f"{attempt.get('pack_id', 'unknown')}@{attempt.get('pack_version', 'unknown')}"
    status = str(attempt.get("status", "unknown"))
    updated = str(attempt.get("updated_at") or attempt.get("completed_at") or attempt.get("started_at") or "unknown")
    attempt_id = str(attempt.get("attempt_id", path.stem))
    return f"{index}. {status} | {answered_count}/{total_count} answered | {pack_ref} | updated {updated} | {attempt_id} | {path}"


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
    packs = list_packs(args.library, include_hidden=args.all)
    if not packs:
        print("No packs imported.")
        return 0
    by_level: dict[str, list[dict[str, Any]]] = {}
    for pack in packs:
        by_level.setdefault(str(pack.get("topik_level", "OTHER")), []).append(pack)
    for level in sorted(by_level):
        print(f"{level}:")
        for pack in by_level[level]:
            difficulty = f" · {pack['difficulty']}" if pack.get("difficulty") else ""
            hidden = " [hidden]" if pack.get("hidden") else ""
            print(
                f"  {pack['pack_id']}@{pack['pack_version']} - {pack['title']}"
                f"{difficulty} ({pack['question_count']} question(s)){hidden}"
            )
    if not args.all:
        hidden_count = len(list_packs(args.library, include_hidden=True)) - len(packs)
        if hidden_count:
            print(f"({hidden_count} hidden pack version(s) — list-packs --all shows them)")
    return 0


def handle_hide_pack(args: argparse.Namespace) -> int:
    changed = set_pack_hidden(args.pack_id, True, args.library)
    print(f"Hidden {changed} version(s) of {args.pack_id}. show-pack restores it.")
    return 0


def handle_show_pack(args: argparse.Namespace) -> int:
    changed = set_pack_hidden(args.pack_id, False, args.library)
    print(f"Unhidden {changed} version(s) of {args.pack_id}.")
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


def handle_report(args: argparse.Namespace) -> int:
    from .report import build_report
    from .stats import resolve_attempt_pack

    attempt = load_attempt(args.attempt)
    if attempt.get("status") != "completed":
        print("Reports need a completed attempt. Resume and finish it first.", file=sys.stderr)
        return 1
    pack = resolve_attempt_pack(attempt, args.library)
    if pack is None:
        print("The attempt's pack could not be loaded from the library or its source path.", file=sys.stderr)
        return 1
    markdown = build_report(attempt, pack)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        print(output_path)
    else:
        print(markdown)
    return 0


def handle_stats(args: argparse.Namespace) -> int:
    from .stats import collect_stats, format_stats

    for line in format_stats(collect_stats(args.attempt_dir, args.library)):
        print(line)
    return 0


def handle_facts(args: argparse.Namespace) -> int:
    import random

    from .facts import categories, filter_facts, load_facts
    from .ui import render

    facts = load_facts(args.facts_file)
    if not facts:
        print(f"No facts are available (looked for {args.facts_file}).", file=sys.stderr)
        return 1
    if args.list:
        for category in categories(facts):
            print(f"{category} ({len(filter_facts(facts, category))})")
        return 0
    pool = filter_facts(facts, args.category) if args.category else facts
    if not pool:
        print(f"No facts match {args.category!r}. Use --list to see categories.", file=sys.stderr)
        return 1
    print(render.fact_card(random.choice(pool)))
    return 0


def handle_audio_stats(args: argparse.Namespace) -> int:
    stats = cache_stats(args.audio_dir)
    print(f"Audio cache: {stats.directory}")
    print(f"Files: {stats.file_count} ({stats.wav_count} wav, {stats.opus_count} opus)")
    print(f"Size: {stats.total_bytes / (1024 * 1024):.1f} MB")
    if stats.oldest_mtime is not None:
        oldest = datetime.fromtimestamp(stats.oldest_mtime).isoformat(timespec="seconds")
        print(f"Least recently used: {oldest}")
    return 0


def handle_audio_prune(args: argparse.Namespace) -> int:
    if args.max_mb is None and args.older_than_days is None:
        print("Pass --max-mb and/or --older-than-days.", file=sys.stderr)
        return 1
    result = prune_cache(
        args.audio_dir,
        max_bytes=int(args.max_mb * 1024 * 1024) if args.max_mb is not None else None,
        older_than_days=args.older_than_days,
        dry_run=args.dry_run,
    )
    label = "Would remove" if args.dry_run else "Removed"
    print(f"{label} {len(result.removed)} file(s) ({result.bytes_removed / (1024 * 1024):.1f} MB).")
    return 0


def handle_audio_warm(args: argparse.Namespace) -> int:
    from dataclasses import replace

    pack = resolve_pack(args.pack_ref, args.library)
    base_config = build_tts_config(args)
    voices = [voice.strip() for voice in args.voices.split(",") if voice.strip()] if args.voices else [None]

    def progress(index: int, total: int, text: str) -> None:
        snippet = text if len(text) <= 42 else f"{text[:39]}..."
        print(f"[{index}/{total}] {snippet}")

    for voice in voices:
        config = base_config if voice is None else replace(base_config, speaker_id=voice)
        if voice is not None:
            print(f"Voice {voice}:")
        try:
            generated, cached = warm_pack(
                pack,
                config,
                include_all_questions=args.all_questions,
                include_teaching=args.teaching,
                progress=progress,
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Generated {generated} file(s), reused {cached} cached file(s).")
    return 0


def handle_audio_compress(args: argparse.Namespace) -> int:
    from .audio_cache import compress_cache

    try:
        result = compress_cache(args.audio_dir, older_than_days=args.older_than_days, bitrate=args.bitrate)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    saved_mb = result.bytes_saved / (1024 * 1024)
    print(f"Compressed {result.compressed} file(s), saved {saved_mb:.1f} MB, skipped {result.skipped} recent file(s).")
    return 0


def handle_audio_bundle(args: argparse.Namespace) -> int:
    from .audio_cache import bundle_pack

    pack = resolve_pack(args.pack_ref, args.library)
    config = build_tts_config(args)
    output = args.output or str(Path("exports") / f"{pack.pack_id}-{pack.data['pack_version']}-audio.zip")
    try:
        zip_path = bundle_pack(
            pack,
            config,
            output,
            include_all_questions=args.all_questions,
            include_teaching=args.teaching,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(zip_path)
    return 0


def handle_speak(args: argparse.Namespace) -> int:
    config = build_tts_config(args)
    text = " ".join(args.text)
    try:
        paths = synthesize_many([text], config)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for path in paths:
        print(path)
    return 0


def handle_list_tts_speakers(args: argparse.Namespace) -> int:
    config = build_tts_config(args)
    try:
        speakers = build_provider(config.provider).list_speakers(config)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not speakers:
        print("No named speakers exposed by this provider.")
        return 0
    for speaker_name, speaker_id in speakers.items():
        print(f"{speaker_name}: {speaker_id}")
    return 0


def resolve_pack(pack_ref: str, library_dir: str | Path) -> Any:
    pack_path = Path(pack_ref)
    if pack_path.exists():
        return load_pack(pack_path)
    return load_pack_ref(pack_ref, library_dir)


def load_answer_file(path: str | Path) -> dict[str, str]:
    # utf-8-sig also reads plain UTF-8; PowerShell's Out-File adds a BOM.
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data: Any = json.load(handle)

    if isinstance(data, dict) and isinstance(data.get("answers"), list):
        return {str(item["question_id"]): str(item.get("response", "")) for item in data["answers"]}
    if isinstance(data, dict):
        return {str(key): str(value) for key, value in data.items()}
    raise ValueError("Answer file must be an object or contain an answers array.")


def speak_question(question: dict[str, Any], config: TTSConfig, include_explanation: bool, playback: bool) -> list[Path]:
    config = TTSConfig(
        provider=config.provider,
        language=config.language,
        device=config.device,
        output_dir=config.output_dir,
        speed=config.speed,
        volume=config.volume,
        playback=playback,
        force=config.force,
        speaker_id=config.speaker_id,
        speaker_wav=config.speaker_wav,
        onnx_provider=config.onnx_provider,
        steps=config.steps,
        tts_python=config.tts_python,
    )
    texts = collect_question_speech_texts(
        question,
        include_passage=not include_explanation,
        include_prompt=False,
        include_explanation=include_explanation,
    )
    if not texts:
        return []
    try:
        paths = synthesize_many(texts, config)
    except RuntimeError as exc:
        print(f"TTS unavailable: {exc}", file=sys.stderr)
        return []
    for path in paths:
        print(f"Audio: {path}")
    return paths


def prompt_for_answer(audio_paths: list[Path], volume: float = 1.0) -> str:
    while True:
        response = input("Your answer (or /replay): ")
        if not is_replay_request(response):
            return response
        replay_audio_paths(audio_paths, volume=volume)


def prompt_after_answer(audio_paths: list[Path], volume: float = 1.0) -> None:
    while True:
        response = input("Press Enter for next question, or /replay: ").strip()
        if not response:
            return
        if is_replay_request(response):
            replay_audio_paths(audio_paths, volume=volume)
            continue
        print("Press Enter to continue, or type /replay.")


def replay_audio_paths(audio_paths: list[Path], volume: float = 1.0) -> None:
    if not audio_paths:
        print("No question audio is available to replay.")
        return
    for path in audio_paths:
        play_audio(path, volume=volume)


def is_replay_request(value: str) -> bool:
    return value.strip().lower() in REPLAY_COMMANDS


def print_question(index: int, question: dict[str, Any], show_transcript: bool = True) -> None:
    print(f"Question {index}: {question['question_id']}")
    passage = question_display_passage(question, show_transcript=show_transcript)
    if passage:
        print(passage)
    if question.get("audio_ref") and not is_transcript_only_audio(question):
        print(f"Audio reference: {question['audio_ref']}")
    print(question["prompt"])
    for option in question.get("options", []):
        print(f"  {option['id']}. {option['text']}")
    hint = response_format_hint(question)
    if hint:
        print(f"({hint})")


def print_post_answer_transcript(question: dict[str, Any], was_shown_before_answer: bool) -> None:
    if was_shown_before_answer or not is_listening_question(question):
        return
    passage = question_display_passage(question, show_transcript=True)
    if passage:
        if not passage.lower().startswith("transcript:"):
            print("Transcript:")
        print(passage)
        print()


def question_display_passage(question: dict[str, Any], show_transcript: bool) -> str | None:
    passage = str(question.get("passage", "")).strip()
    if not passage:
        return None
    if is_listening_question(question) and not show_transcript:
        return None
    return passage


def is_transcript_only_audio(question: dict[str, Any]) -> bool:
    return str(question.get("audio_ref", "")).startswith("transcript-only:")


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
    answered_count, total_count = attempt_progress(attempt)
    print(f"Final score: {score}/{max_score}")
    print(f"Status: {attempt['status']}")
    print(f"Progress: {answered_count}/{total_count} answered")
    elapsed = float(attempt.get("elapsed_seconds") or 0.0)
    if elapsed and answered_count:
        minutes, seconds = divmod(int(elapsed), 60)
        print(f"Time: {minutes:02d}:{seconds:02d} ({elapsed / answered_count:.0f}s/question)")
    print(f"Attempt ID: {attempt['attempt_id']}")


if __name__ == "__main__":
    raise SystemExit(main())
