from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


DEFAULT_TTS_PROVIDER = "supertonic"
DEFAULT_TTS_LANGUAGE = "KR"
DEFAULT_TTS_DEVICE = "cuda:0"
DEFAULT_AUDIO_DIR = Path("data") / "audio_cache"
DEFAULT_MODEL_CACHE_DIR = Path("data") / "model_cache"
DEFAULT_SUPERTONIC_VOICE = "F1"
DEFAULT_SUPERTONIC_ONNX_PROVIDER = "dml"
DEFAULT_SUPERTONIC_STEPS = 10
DEFAULT_ANKI_TTS_PYTHON = Path("H:/software/anki/.tts-venv/Scripts/python.exe")
DEFAULT_ANKI_HF_CACHE = Path("H:/software/anki/.hf-cache")
DEFAULT_ANKI_SUPERTONIC_CACHE = Path("H:/software/anki/.supertonic-cache")


class TTSProvider(Protocol):
    def synthesize_to_file(self, text: str, output_path: Path, config: "TTSConfig") -> None:
        ...

    def list_speakers(self, config: "TTSConfig") -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class TTSConfig:
    provider: str = DEFAULT_TTS_PROVIDER
    language: str = DEFAULT_TTS_LANGUAGE
    device: str = DEFAULT_TTS_DEVICE
    output_dir: Path = DEFAULT_AUDIO_DIR
    speed: float = 1.0
    volume: float = 1.0
    playback: bool = False
    force: bool = False
    speaker_id: str | None = None
    speaker_wav: Path | None = None
    onnx_provider: str = DEFAULT_SUPERTONIC_ONNX_PROVIDER
    steps: int = DEFAULT_SUPERTONIC_STEPS
    tts_python: Path | None = None


def synthesize_many(texts: list[str], config: TTSConfig) -> list[Path]:
    configure_utf8_output()
    output_paths: list[Path] = []
    provider: TTSProvider | None = None
    config.output_dir.mkdir(parents=True, exist_ok=True)

    for text in [item.strip() for item in texts if item.strip()]:
        output_path = config.output_dir / stable_audio_name(
            text,
            provider=config.provider,
            language=config.language,
            speed=config.speed,
            speaker_id=config.speaker_id,
            speaker_wav=config.speaker_wav,
            steps=config.steps,
        )
        output_paths.append(output_path)
        if output_path.exists() and not config.force:
            touch_cache_entry(output_path)
            continue
        if not config.force and restore_cached_audio(output_path):
            continue
        if provider is None:
            provider = build_provider(config.provider)
        synthesize_atomic(provider, text, output_path, config)

    if config.playback:
        for output_path in output_paths:
            play_audio(output_path, volume=config.volume)

    return output_paths


def synthesize_atomic(provider: TTSProvider, text: str, output_path: Path, config: TTSConfig) -> None:
    """Write through a temp file so concurrent prefetch and foreground synthesis never clash."""
    token = f"{os.getpid()}-{threading.get_ident()}"
    temp_path = output_path.with_name(f"{output_path.stem}.{token}.tmp.wav")
    try:
        provider.synthesize_to_file(text, temp_path, config)
        os.replace(temp_path, output_path)
    finally:
        temp_path.unlink(missing_ok=True)


def touch_cache_entry(path: Path) -> None:
    """Mark a cache hit so prune can evict least-recently-used audio first."""
    try:
        os.utime(path, None)
    except OSError:
        pass


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def restore_cached_audio(wav_path: Path) -> bool:
    """Re-expand an opus-compressed cache entry back to WAV. See docs/AUDIO_DESIGN.md."""
    opus_path = wav_path.with_suffix(".opus")
    if not opus_path.exists():
        return False
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        return False
    result = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(opus_path), str(wav_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not wav_path.exists():
        wav_path.unlink(missing_ok=True)
        return False
    opus_path.unlink(missing_ok=True)
    return True


def build_provider(provider_name: str) -> TTSProvider:
    normalized = provider_name.lower()
    if normalized == "melo":
        return MeloTTSProvider()
    if normalized == "xtts-v2":
        return XTTSV2Provider()
    if normalized == "supertonic":
        return SupertonicProvider()
    raise ValueError(f"Unknown TTS provider {provider_name!r}. Supported providers: melo, xtts-v2, supertonic.")


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def collect_question_speech_texts(
    question: dict[str, Any],
    include_passage: bool = True,
    include_prompt: bool = True,
    include_options: bool = False,
    include_explanation: bool = False,
) -> list[str]:
    texts: list[str] = []
    if include_passage:
        value = transcript_text(question) or str(question.get("passage", "")).strip()
        if value:
            texts.append(value)

    if include_prompt and looks_korean(str(question.get("prompt", ""))):
        texts.append(str(question["prompt"]))

    if include_options:
        for option in question.get("options", []):
            text = str(option.get("text", "")).strip()
            if looks_korean(text):
                texts.append(text)

    if include_explanation:
        explanation = question.get("explanation", {})
        for item in explanation.get("vocabulary", []):
            if item.get("ko"):
                texts.append(str(item["ko"]))
        for item in explanation.get("grammar", []):
            if item.get("example"):
                texts.append(str(item["example"]))

    return dedupe(texts)


def stable_audio_name(
    text: str,
    provider: str,
    language: str,
    speed: float = 1.0,
    speaker_id: str | None = None,
    speaker_wav: Path | None = None,
    steps: int = DEFAULT_SUPERTONIC_STEPS,
) -> str:
    speaker_key = speaker_id or (str(speaker_wav) if speaker_wav else "default")
    # Volume is applied at playback, so one cached waveform serves every gain
    # setting. The literal volume=1.000 keeps names of previously cached files valid.
    key = f"{provider}|{language}|speed={speed:.3f}|volume=1.000|speaker={speaker_key}|steps={steps}|{text}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return f"{provider}-{language}-{digest}.wav"


def adjust_wav_volume(path: Path, volume: float) -> None:
    if volume <= 0:
        raise ValueError("Volume must be greater than 0.")
    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())

    if params.sampwidth != 2:
        return

    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()

    for index, sample in enumerate(samples):
        samples[index] = max(-32768, min(32767, int(sample * volume)))

    if sys.byteorder != "little":
        samples.byteswap()

    with wave.open(str(path), "wb") as target:
        target.setparams(params)
        target.writeframes(samples.tobytes())


def looks_korean(text: str) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in text)


def transcript_text(question: dict[str, Any]) -> str:
    passage = str(question.get("passage", "")).strip()
    if passage.lower().startswith("transcript:"):
        return passage.split(":", 1)[1].strip()
    return passage


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def is_listening_question(question: dict[str, Any]) -> bool:
    return str(question.get("skill", "")).lower() == "listening" or bool(question.get("audio_ref"))


def play_audio(path: Path, volume: float = 1.0) -> None:
    if volume != 1.0:
        temp_path = Path(tempfile.gettempdir()) / f"topik-play-{os.getpid()}-{path.name}"
        try:
            shutil.copy2(path, temp_path)
            adjust_wav_volume(temp_path, volume)
            _play_audio_file(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return
    _play_audio_file(path)


def _play_audio_file(path: Path) -> None:
    if sys.platform.startswith("win"):
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(New-Object Media.SoundPlayer '{path}').PlaySync();",
            ],
            check=False,
        )
        return
    if sys.platform == "darwin":
        subprocess.run(["afplay", str(path)], check=False)
        return
    subprocess.run(["aplay", str(path)], check=False)


class MeloTTSProvider:
    def __init__(self) -> None:
        self._model: Any | None = None

    def synthesize_to_file(self, text: str, output_path: Path, config: TTSConfig) -> None:
        model = self._load_model(config)
        speaker_ids = model.hps.data.spk2id
        speaker_id = resolve_speaker_id(speaker_ids, config)
        if speaker_id is None:
            raise RuntimeError(f"MeloTTS model does not expose a speaker for {config.language!r}.")
        model.tts_to_file(text, speaker_id, str(output_path), speed=config.speed)

    def list_speakers(self, config: TTSConfig) -> dict[str, Any]:
        model = self._load_model(config)
        return hparams_to_dict(model.hps.data.spk2id)

    def _load_model(self, config: TTSConfig) -> Any:
        if self._model is not None:
            return self._model
        configure_model_cache()
        configure_mecab_dictionary()
        try:
            from melo.api import TTS
        except ImportError as exc:
            raise RuntimeError(
                "MeloTTS is not installed. Install optional TTS dependencies from docs/TTS_SETUP.md."
            ) from exc
        self._model = TTS(language=config.language, device=config.device)
        return self._model


class XTTSV2Provider:
    def __init__(self) -> None:
        self._model: Any | None = None

    def synthesize_to_file(self, text: str, output_path: Path, config: TTSConfig) -> None:
        if config.speaker_wav is None:
            raise RuntimeError("XTTS-v2 requires --tts-speaker-wav with a reference voice file.")
        model = self._load_model(config)
        model.tts_to_file(
            text=text,
            file_path=str(output_path),
            speaker_wav=str(config.speaker_wav),
            language="ko",
        )

    def list_speakers(self, config: TTSConfig) -> dict[str, Any]:
        return {"speaker_wav": str(config.speaker_wav) if config.speaker_wav else "required"}

    def _load_model(self, config: TTSConfig) -> Any:
        if self._model is not None:
            return self._model
        try:
            from TTS.api import TTS
        except ImportError as exc:
            raise RuntimeError("Coqui TTS is not installed. Install optional TTS dependencies from docs/TTS_SETUP.md.") from exc
        use_gpu = config.device.startswith("cuda")
        self._model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=use_gpu)
        return self._model


def supertonic_helper_path() -> Path:
    """The subprocess helper that runs Supertonic synthesis (see tools/)."""
    return Path(__file__).resolve().parents[2] / "tools" / "supertonic_synth.py"


class SupertonicProvider:
    def synthesize_to_file(self, text: str, output_path: Path, config: TTSConfig) -> None:
        python_path = resolve_supertonic_python(config)
        helper_path = supertonic_helper_path()
        if not helper_path.exists():
            raise RuntimeError(f"Supertonic helper is missing: {helper_path}")

        command = [
            str(python_path),
            str(helper_path),
            "--output",
            str(output_path),
            "--voice",
            config.speaker_id or DEFAULT_SUPERTONIC_VOICE,
            "--provider",
            config.onnx_provider,
            "--speed",
            str(config.speed),
            "--steps",
            str(config.steps),
            "--lang",
            supertonic_language(config.language),
            "--hf-home",
            str(resolve_supertonic_hf_home()),
            "--cache-dir",
            str(resolve_supertonic_cache_dir()),
        ]
        result = subprocess.run(
            command,
            input=text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Supertonic synthesis failed: {details}")

    def list_speakers(self, config: TTSConfig) -> dict[str, Any]:
        return {
            "F1": "female preset 1",
            "F2": "female preset 2",
            "M1": "male preset 1",
        }


def configure_mecab_dictionary() -> Path | None:
    try:
        import unidic_lite
    except ImportError:
        return Path(os.environ["MECABRC"]) if os.environ.get("MECABRC") else None
    mecabrc = Path(unidic_lite.__file__).resolve().parent / "dicdir" / "mecabrc"
    if mecabrc.exists():
        dicdir = mecabrc.parent
        try:
            import unidic

            unidic.DICDIR = str(dicdir)
        except ImportError:
            pass
        os.environ["MECABRC"] = str(mecabrc)
        return mecabrc
    return Path(os.environ["MECABRC"]) if os.environ.get("MECABRC") else None


def configure_model_cache(cache_dir: str | Path = DEFAULT_MODEL_CACHE_DIR) -> Path:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    hf_home = cache_path / "huggingface"
    hf_home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home / "transformers"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_path))
    nltk_data = cache_path / "nltk_data"
    nltk_data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("NLTK_DATA", str(nltk_data))
    try:
        import nltk.data

        nltk_path = str(nltk_data)
        if nltk_path not in nltk.data.path:
            nltk.data.path.insert(0, nltk_path)
    except ImportError:
        pass
    return cache_path


def resolve_supertonic_python(config: TTSConfig) -> Path:
    candidates = [
        config.tts_python,
        Path(os.environ["TOPIK_SUPERTONIC_PYTHON"]) if os.environ.get("TOPIK_SUPERTONIC_PYTHON") else None,
        DEFAULT_ANKI_TTS_PYTHON,
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise RuntimeError(
        "Supertonic Python runtime was not found. Set TOPIK_SUPERTONIC_PYTHON or pass --tts-python."
    )


def resolve_supertonic_hf_home() -> Path:
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"])
    if DEFAULT_ANKI_HF_CACHE.exists():
        return DEFAULT_ANKI_HF_CACHE
    return DEFAULT_MODEL_CACHE_DIR / "huggingface"


def resolve_supertonic_cache_dir() -> Path:
    if os.environ.get("SUPERTONIC_CACHE_DIR"):
        return Path(os.environ["SUPERTONIC_CACHE_DIR"])
    if DEFAULT_ANKI_SUPERTONIC_CACHE.exists():
        return DEFAULT_ANKI_SUPERTONIC_CACHE
    return DEFAULT_MODEL_CACHE_DIR / "supertonic"


def supertonic_language(language: str) -> str:
    normalized = language.lower()
    if normalized in {"kr", "ko", "kor", "korean"}:
        return "ko"
    return normalized


def resolve_speaker_id(speaker_ids: Any, config: TTSConfig) -> Any | None:
    if config.speaker_id is not None:
        if config.speaker_id.isdigit():
            return int(config.speaker_id)
        return lookup_speaker_id(speaker_ids, config.speaker_id)
    return lookup_speaker_id(speaker_ids, config.language) or lookup_speaker_id(speaker_ids, "KR")


def lookup_speaker_id(speaker_ids: Any, language: str) -> Any | None:
    if hasattr(speaker_ids, "get"):
        return speaker_ids.get(language)
    try:
        return speaker_ids[language]
    except (KeyError, TypeError):
        return getattr(speaker_ids, language, None)


def hparams_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        return dict(value.items())
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}
