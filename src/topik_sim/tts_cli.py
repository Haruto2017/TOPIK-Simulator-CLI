from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from .config import config_value, load_config
from .tts import TTSConfig, build_provider, play_audio, synthesize_many


def main(argv: list[str] | None = None) -> int:
    configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nTTS stopped.")
        return 130


def configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="topik-tts", description="TOPIK Korean TTS CLI")
    subparsers = parser.add_subparsers(required=True)

    speak = subparsers.add_parser("speak", help="Generate Korean TTS audio for direct text.")
    speak.add_argument("text", nargs="+", help="Text to synthesize.")
    add_tts_arguments(speak)
    speak.add_argument("--save", action="store_true", help="Keep the generated WAV in --tts-output-dir instead of using temporary playback.")
    speak.set_defaults(handler=handle_speak)

    speakers = subparsers.add_parser("list-speakers", help="List voices exposed by the selected TTS provider.")
    add_tts_arguments(speakers)
    speakers.set_defaults(handler=handle_list_speakers)

    play = subparsers.add_parser("play", help="Play an existing WAV file.")
    play.add_argument("audio", help="Path to a WAV file.")
    play.set_defaults(handler=handle_play)

    return parser


def handle_speak(args: argparse.Namespace) -> int:
    text = " ".join(args.text)
    try:
        if args.save:
            paths = synthesize_many([text], build_tts_config(args))
        else:
            with tempfile.TemporaryDirectory(prefix="topik-tts-") as temp_dir:
                config = replace(build_tts_config(args), output_dir=Path(temp_dir), playback=True, force=True)
                synthesize_many([text], config)
                paths = []
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for path in paths:
        print(path)
    return 0


def handle_list_speakers(args: argparse.Namespace) -> int:
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


def handle_play(args: argparse.Namespace) -> int:
    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"Audio file not found: {audio_path}", file=sys.stderr)
        return 1
    play_audio(audio_path)
    return 0


def add_tts_arguments(parser: argparse.ArgumentParser, config: dict | None = None) -> None:
    config = config if config is not None else load_config()
    tts = lambda key, default: config_value(config, "tts", key, default)  # noqa: E731
    parser.add_argument("--tts-provider", default=tts("provider", "supertonic"), choices=["supertonic", "melo", "xtts-v2"], help="Local TTS provider.")
    parser.add_argument("--tts-language", default=tts("language", "KR"), help="TTS language code. Use KR for Korean.")
    parser.add_argument("--tts-device", default=tts("device", "cuda:0"), help="TTS device, such as cuda:0 or cpu.")
    parser.add_argument("--tts-output-dir", default=tts("output_dir", "data/audio_cache"), help="Directory for generated WAV files.")
    parser.add_argument("--tts-speed", type=float, default=tts("speed", 1.0), help="Speech speed multiplier.")
    parser.add_argument("--tts-volume", type=float, default=tts("volume", 1.0), help="Audio gain multiplier applied at playback.")
    parser.add_argument("--tts-play", action="store_true", help="Play generated audio immediately.")
    parser.add_argument("--tts-force", action="store_true", help="Regenerate audio even when cached.")
    parser.add_argument("--tts-speaker-id", default=tts("voice", None), help="Provider speaker name or numeric speaker id when supported.")
    parser.add_argument("--tts-speaker-wav", help="Reference WAV file for XTTS-v2.")
    parser.add_argument("--tts-onnx-provider", default=tts("onnx_provider", "dml"), choices=["dml", "cpu", "default"], help="Supertonic ONNX backend.")
    parser.add_argument("--tts-steps", type=int, default=tts("steps", 10), help="Supertonic synthesis steps.")
    parser.add_argument("--tts-python", default=tts("python", None), help="Python executable for subprocess-based TTS providers.")


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


if __name__ == "__main__":
    raise SystemExit(main())
