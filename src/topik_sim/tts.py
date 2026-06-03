from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


DEFAULT_TTS_PROVIDER = "melo"
DEFAULT_TTS_LANGUAGE = "KR"
DEFAULT_TTS_DEVICE = "cuda:0"
DEFAULT_AUDIO_DIR = Path("data") / "audio_cache"


class TTSProvider(Protocol):
    def synthesize_to_file(self, text: str, output_path: Path, config: "TTSConfig") -> None:
        ...


@dataclass(frozen=True)
class TTSConfig:
    provider: str = DEFAULT_TTS_PROVIDER
    language: str = DEFAULT_TTS_LANGUAGE
    device: str = DEFAULT_TTS_DEVICE
    output_dir: Path = DEFAULT_AUDIO_DIR
    speed: float = 1.0
    playback: bool = False
    force: bool = False
    speaker_wav: Path | None = None


def synthesize_many(texts: list[str], config: TTSConfig) -> list[Path]:
    output_paths: list[Path] = []
    provider: TTSProvider | None = None
    config.output_dir.mkdir(parents=True, exist_ok=True)

    for text in [item.strip() for item in texts if item.strip()]:
        output_path = config.output_dir / stable_audio_name(text, provider=config.provider, language=config.language)
        output_paths.append(output_path)
        if output_path.exists() and not config.force:
            continue
        if provider is None:
            provider = build_provider(config.provider)
        provider.synthesize_to_file(text, output_path, config)

    if config.playback:
        for output_path in output_paths:
            play_audio(output_path)

    return output_paths


def build_provider(provider_name: str) -> TTSProvider:
    normalized = provider_name.lower()
    if normalized == "melo":
        return MeloTTSProvider()
    if normalized == "xtts-v2":
        return XTTSV2Provider()
    raise ValueError(f"Unknown TTS provider {provider_name!r}. Supported providers: melo, xtts-v2.")


def collect_question_speech_texts(
    question: dict[str, Any],
    include_passage: bool = True,
    include_prompt: bool = True,
    include_options: bool = False,
    include_explanation: bool = False,
) -> list[str]:
    texts: list[str] = []
    if include_passage:
        value = str(question.get("passage", "")).strip()
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


def stable_audio_name(text: str, provider: str, language: str) -> str:
    digest = hashlib.sha256(f"{provider}|{language}|{text}".encode("utf-8")).hexdigest()[:24]
    return f"{provider}-{language}-{digest}.wav"


def looks_korean(text: str) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in text)


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def play_audio(path: Path) -> None:
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
        speaker_id = speaker_ids.get(config.language) or speaker_ids.get("KR")
        if speaker_id is None:
            raise RuntimeError(f"MeloTTS model does not expose a speaker for {config.language!r}.")
        model.tts_to_file(text, speaker_id, str(output_path), speed=config.speed)

    def _load_model(self, config: TTSConfig) -> Any:
        if self._model is not None:
            return self._model
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
