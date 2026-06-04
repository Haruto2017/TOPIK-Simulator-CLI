from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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
from .content import ContentValidationError, load_pack, validate_pack_file
from .grading import grade_answers, grade_question
from .library import DEFAULT_LIBRARY_DIR, import_pack, list_packs, load_pack_ref, validate_library
from .tts import TTSConfig, build_provider, collect_question_speech_texts, play_audio, synthesize_many


REPLAY_COMMANDS = {"/replay", "/r", "replay"}
DEFAULT_RECENT_ATTEMPT_LIMIT = 10


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
    simulate.add_argument("--show-teaching", action="store_true", help="Compatibility flag; feedback is always shown.")
    simulate.set_defaults(handler=handle_simulate)

    take = subparsers.add_parser("take", help="Take a test and save the attempt.")
    take.add_argument("pack_ref", help="Pack file path, pack_id, or pack_id@pack_version.")
    take.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
    take.add_argument("--attempt-dir", default="data/attempts", help="Directory for saved attempts.")
    take.add_argument("--section", help="Only run one section_id.")
    take.add_argument("--limit", type=int, help="Limit the number of questions.")
    take.add_argument("--show-teaching", action="store_true", help="Compatibility flag; feedback is always shown.")
    take.add_argument("--show-transcript", action="store_true", help="Show listening transcripts while taking a test.")
    add_tts_arguments(take)
    take.add_argument("--speak-question", action="store_true", help="Generate Korean audio for each question while taking a test.")
    take.add_argument("--speak-teaching", action="store_true", help="Generate Korean audio for vocabulary and example sentences in teaching notes.")
    take.add_argument("--no-listening-audio", action="store_true", help="Do not automatically play audio for listening questions.")
    take.set_defaults(handler=handle_take)

    review = subparsers.add_parser("review-attempt", help="Review a saved attempt JSON file.")
    review.add_argument("attempt")
    review.set_defaults(handler=handle_review_attempt)

    list_attempts = subparsers.add_parser("list-attempts", help="List recent saved attempts.")
    list_attempts.add_argument("--attempt-dir", default="data/attempts", help="Directory for saved attempts.")
    list_attempts.add_argument("--limit", type=int, default=DEFAULT_RECENT_ATTEMPT_LIMIT, help="Maximum attempts to show.")
    list_attempts.set_defaults(handler=handle_list_attempts)

    resume = subparsers.add_parser("resume-attempt", help="Continue a saved in-progress attempt.")
    resume.add_argument("attempt", nargs="?", help="Path to an attempt JSON file. Omit to choose from recent attempts.")
    resume.add_argument("--attempt-dir", default="data/attempts", help="Directory to scan when no attempt path is given.")
    resume.add_argument("--recent", type=int, default=DEFAULT_RECENT_ATTEMPT_LIMIT, help="Maximum recent attempts to show when choosing.")
    resume.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
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
    import_content.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
    import_content.add_argument("--replace", action="store_true", help="Replace an existing pack with the same id and version.")
    import_content.set_defaults(handler=handle_import_pack)

    list_content = subparsers.add_parser("list-packs", help="List packs in the content library.")
    list_content.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
    list_content.set_defaults(handler=handle_list_packs)

    validate_library_parser = subparsers.add_parser("validate-library", help="Validate the content library manifest and pack files.")
    validate_library_parser.add_argument("--library", default=str(DEFAULT_LIBRARY_DIR), help="Content library directory.")
    validate_library_parser.set_defaults(handler=handle_validate_library)

    speak = subparsers.add_parser("speak", help="Generate Korean TTS audio for direct text.")
    speak.add_argument("text", nargs="+", help="Text to synthesize.")
    add_tts_arguments(speak)
    speak.set_defaults(handler=handle_speak)

    list_speakers = subparsers.add_parser("list-tts-speakers", help="List voices exposed by the selected TTS provider.")
    add_tts_arguments(list_speakers)
    list_speakers.set_defaults(handler=handle_list_tts_speakers)

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
    print_attempt_summary(attempt)
    return 0


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
        response = prompt_for_answer(question_audio_paths)
        attempt = answer_question(attempt, pack, response)
        save_attempt(attempt, save_path)
        result = grade_question(question, response)
        print("Correct.\n" if result["correct"] else "Not quite.\n")
        print_post_answer_transcript(question, was_shown_before_answer=show_transcript)
        print_feedback(result["feedback"])
        if speak_teaching:
            speak_question(question, tts_config, include_explanation=True, playback=tts_play)
        prompt_after_answer(question_audio_paths)
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
    with Path(path).open("r", encoding="utf-8") as handle:
        data: Any = json.load(handle)

    if isinstance(data, dict) and isinstance(data.get("answers"), list):
        return {str(item["question_id"]): str(item.get("response", "")) for item in data["answers"]}
    if isinstance(data, dict):
        return {str(key): str(value) for key, value in data.items()}
    raise ValueError("Answer file must be an object or contain an answers array.")


def add_tts_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tts-provider", default="supertonic", choices=["supertonic", "melo", "xtts-v2"], help="Local TTS provider.")
    parser.add_argument("--tts-language", default="KR", help="TTS language code. Use KR for Korean.")
    parser.add_argument("--tts-device", default="cuda:0", help="TTS device, such as cuda:0 or cpu.")
    parser.add_argument("--tts-output-dir", default="data/audio_cache", help="Directory for generated WAV files.")
    parser.add_argument("--tts-speed", type=float, default=1.0, help="Speech speed multiplier.")
    parser.add_argument("--tts-volume", type=float, default=1.0, help="Audio gain multiplier for generated WAV files.")
    parser.add_argument("--tts-play", action="store_true", help="Play generated audio immediately.")
    parser.add_argument("--tts-force", action="store_true", help="Regenerate audio even when cached.")
    parser.add_argument("--tts-speaker-id", help="Provider speaker name or numeric speaker id when supported.")
    parser.add_argument("--tts-speaker-wav", help="Reference WAV file for XTTS-v2.")
    parser.add_argument("--tts-onnx-provider", default="dml", choices=["dml", "cpu", "default"], help="Supertonic ONNX backend.")
    parser.add_argument("--tts-steps", type=int, default=10, help="Supertonic synthesis steps.")
    parser.add_argument("--tts-python", help="Python executable for subprocess-based TTS providers.")


def build_tts_config(args: argparse.Namespace) -> TTSConfig:
    if args.tts_volume <= 0:
        raise ValueError("--tts-volume must be greater than 0.")
    if args.tts_steps <= 0:
        raise ValueError("--tts-steps must be greater than 0.")
    return TTSConfig(
        provider=args.tts_provider,
        language=args.tts_language,
        device=args.tts_device,
        output_dir=Path(args.tts_output_dir),
        speed=args.tts_speed,
        volume=args.tts_volume,
        playback=args.tts_play,
        force=args.tts_force,
        speaker_id=args.tts_speaker_id,
        speaker_wav=Path(args.tts_speaker_wav) if args.tts_speaker_wav else None,
        onnx_provider=args.tts_onnx_provider,
        steps=args.tts_steps,
        tts_python=Path(args.tts_python) if args.tts_python else None,
    )


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


def prompt_for_answer(audio_paths: list[Path]) -> str:
    while True:
        response = input("Your answer (or /replay): ")
        if not is_replay_request(response):
            return response
        replay_audio_paths(audio_paths)


def prompt_after_answer(audio_paths: list[Path]) -> None:
    while True:
        response = input("Press Enter for next question, or /replay: ").strip()
        if not response:
            return
        if is_replay_request(response):
            replay_audio_paths(audio_paths)
            continue
        print("Press Enter to continue, or type /replay.")


def replay_audio_paths(audio_paths: list[Path]) -> None:
    if not audio_paths:
        print("No question audio is available to replay.")
        return
    for path in audio_paths:
        play_audio(path)


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


def is_listening_question(question: dict[str, Any]) -> bool:
    return str(question.get("skill", "")).lower() == "listening" or bool(question.get("audio_ref"))


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
    print(f"Attempt ID: {attempt['attempt_id']}")


if __name__ == "__main__":
    raise SystemExit(main())
