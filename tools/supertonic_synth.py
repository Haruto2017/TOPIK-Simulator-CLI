from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize one Korean WAV with Supertonic.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--voice", default="F1")
    parser.add_argument("--provider", choices=["dml", "cpu", "default"], default="dml")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--lang", default="ko")
    parser.add_argument("--hf-home")
    parser.add_argument("--cache-dir")
    args = parser.parse_args()

    text = sys.stdin.buffer.read().decode("utf-8", errors="strict").strip()
    if not text:
        print("No text received on stdin.", file=sys.stderr)
        return 1

    if args.hf_home:
        os.environ.setdefault("HF_HOME", args.hf_home)
    if args.cache_dir:
        os.environ.setdefault("SUPERTONIC_CACHE_DIR", args.cache_dir)

    try:
        from supertonic import TTS
        configure_provider(args.provider)
    except ImportError:
        print("Supertonic is not installed in this Python runtime.", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tts = TTS(auto_download=True)
    style = tts.get_voice_style(voice_name=args.voice)
    wav, _duration = tts.synthesize(
        text=text,
        lang=args.lang,
        voice_style=style,
        total_steps=args.steps,
        speed=args.speed,
    )
    tts.save_audio(wav, str(output_path))
    return 0


def configure_provider(provider: str) -> None:
    if provider == "default":
        return
    providers = ["CPUExecutionProvider"] if provider == "cpu" else ["DmlExecutionProvider", "CPUExecutionProvider"]
    import supertonic.config as config
    import supertonic.loader as loader

    config.DEFAULT_ONNX_PROVIDERS = providers
    loader.DEFAULT_ONNX_PROVIDERS = providers


if __name__ == "__main__":
    raise SystemExit(main())
