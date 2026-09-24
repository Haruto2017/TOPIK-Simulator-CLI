from __future__ import annotations

"""Synthesize one WAV with Qwen3-TTS through mlx-audio (Apple Silicon).

Runs inside the .venv-qwen3 environment (see setup-tts-qwen3.sh); the
simulator's own stdlib-only process invokes it as a subprocess, exactly like
tools/supertonic_synth.py. Text arrives on stdin, the WAV lands at --output.

Qwen3-TTS declares its own languages and voices, so both are validated
against the loaded model rather than hard-coded here. The model does not
implement a speed control yet; --speed other than 1.0 is applied with ffmpeg's
atempo filter when ffmpeg is available, otherwise normal speed is kept and a
note goes to stderr (never a failure — slow replay must not break playback).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

DEFAULT_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
DEFAULT_VOICE = "sohee"
SILENCE_RMS = 0.01     # 1% of full scale counts as silence
KEEP_PAD_SECONDS = 0.12


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize one WAV with Qwen3-TTS (mlx-audio).")
    parser.add_argument("--output", help="destination WAV path")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--lang", default="korean", help="language code as the model names it (korean, english, …)")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--model", default=os.environ.get("TOPIK_QWEN3_MODEL", DEFAULT_MODEL))
    parser.add_argument("--hf-home")
    parser.add_argument("--keep-silence", action="store_true", help="do not trim leading/trailing silence")
    parser.add_argument("--check", action="store_true", help="only verify the engine imports; exit 0 when ready")
    args = parser.parse_args()

    if args.hf_home:
        os.environ.setdefault("HF_HOME", args.hf_home)

    try:
        from mlx_audio.tts.utils import load_model
        import numpy as np
    except ImportError as exc:
        print(f"Qwen3-TTS runtime is not installed in this Python ({exc}). Run setup-tts-qwen3.sh.", file=sys.stderr)
        return 1
    if args.check:
        print("qwen3 ok")
        return 0
    if not args.output:
        print("--output is required.", file=sys.stderr)
        return 2

    text = sys.stdin.buffer.read().decode("utf-8", errors="strict").strip()
    if not text:
        print("No text received on stdin.", file=sys.stderr)
        return 1

    model = load_model(args.model)
    voices = [v.lower() for v in (model.get_supported_speakers() or [])]
    voice = args.voice.lower()
    if voices and voice not in voices:
        print(f"Voice {args.voice!r} is not a Qwen3-TTS voice ({', '.join(voices)}); using {DEFAULT_VOICE}.",
              file=sys.stderr)
        voice = DEFAULT_VOICE if DEFAULT_VOICE in voices else voices[0]
    languages = [l.lower() for l in (model.get_supported_languages() or [])]
    lang = args.lang.lower()
    if languages and lang not in languages:
        print(f"Language {args.lang!r} is not declared by the model; using auto.", file=sys.stderr)
        lang = "auto"

    chunks = []
    sample_rate = 24000
    for result in model.generate(text, voice=voice, lang_code=lang):
        chunks.append(np.asarray(result.audio, dtype=np.float32).reshape(-1))
        sample_rate = int(getattr(result, "sample_rate", sample_rate))
    if not chunks:
        print("The model produced no audio.", file=sys.stderr)
        return 1
    audio = np.concatenate(chunks)
    if not args.keep_silence:
        audio = trim_silence(audio, sample_rate, np)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if abs(args.speed - 1.0) > 1e-3:
        write_with_speed(audio, sample_rate, args.speed, output_path, np)
    else:
        write_wav(audio, sample_rate, output_path, np)
    return 0


def trim_silence(audio, sample_rate: int, np):
    """Cut the model's ~1 s of leading/trailing silence, keeping a short pad."""
    win = max(1, sample_rate // 50)
    n = len(audio)
    if n < win * 2:
        return audio
    frames = n // win
    rms = np.sqrt(np.mean(audio[: frames * win].reshape(frames, win) ** 2, axis=1))
    loud = np.flatnonzero(rms > SILENCE_RMS)
    if loud.size == 0:
        return audio
    pad = int(KEEP_PAD_SECONDS * sample_rate)
    start = max(0, int(loud[0]) * win - pad)
    end = min(n, (int(loud[-1]) + 1) * win + pad)
    return audio[start:end]


def write_wav(audio, sample_rate: int, path: Path, np) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def write_with_speed(audio, sample_rate: int, speed: float, path: Path, np) -> None:
    """Tempo change via ffmpeg atempo (pitch-preserving); falls back to normal speed."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print(f"ffmpeg not found; speed {speed} ignored (normal speed written).", file=sys.stderr)
        write_wav(audio, sample_rate, path, np)
        return
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "normal.wav"
        write_wav(audio, sample_rate, source, np)
        tempo = min(max(speed, 0.5), 2.0)  # atempo's single-pass range
        result = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(source), "-filter:a", f"atempo={tempo}", str(path)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0 or not path.exists():
            print(f"ffmpeg atempo failed ({result.stderr.strip()}); normal speed written.", file=sys.stderr)
            write_wav(audio, sample_rate, path, np)


if __name__ == "__main__":
    raise SystemExit(main())
