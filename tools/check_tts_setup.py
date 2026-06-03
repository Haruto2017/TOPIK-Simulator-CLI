from __future__ import annotations

import argparse
import sys
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from topik_sim.tts import TTSConfig, configure_mecab_dictionary, configure_model_cache, synthesize_many


def main() -> int:
    parser = argparse.ArgumentParser(description="Check optional local TTS setup.")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--synthesize", action="store_true", help="Generate a Korean sample WAV.")
    args = parser.parse_args()

    print(f"Python: {platform.python_version()} ({sys.executable})")
    check_python_runtime()
    cache_dir = configure_model_cache(ROOT / "data" / "model_cache")
    print(f"Model cache: {cache_dir}")
    check_torch(args.device)
    check_melotts()

    if args.synthesize:
        config = TTSConfig(device=args.device, output_dir=ROOT / "data" / "audio_cache", force=True)
        paths = synthesize_many(["안녕하세요. 오늘은 날씨가 좋습니다."], config)
        for path in paths:
            print(f"Generated: {path}")
    else:
        print("Run with --synthesize to generate a sample WAV.")
    return 0


def check_python_runtime() -> None:
    executable = str(Path(sys.executable)).lower()
    if "msys64" in executable or "mingw" in executable:
        print("Warning: MSYS/MINGW Python may not support official Windows PyTorch CUDA wheels.")


def check_torch(device: str) -> None:
    try:
        import torch
    except ImportError:
        print("PyTorch is not installed.")
        return

    print(f"PyTorch: {torch.__version__}")
    if device.startswith("cuda"):
        print(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"CUDA device: {torch.cuda.get_device_name(0)}")


def check_melotts() -> None:
    try:
        mecabrc = configure_mecab_dictionary()
        if mecabrc:
            print(f"MeCab dictionary: {mecabrc}")
        from melo.api import TTS  # noqa: F401
    except ImportError:
        print("MeloTTS is not installed.")
        return
    print("MeloTTS import: OK")


if __name__ == "__main__":
    raise SystemExit(main())
