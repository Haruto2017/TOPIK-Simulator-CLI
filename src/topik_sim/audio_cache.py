from __future__ import annotations

import json
import subprocess
import time
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from .content import ExamPack
from .tts import (
    TTSConfig,
    collect_question_speech_texts,
    dedupe,
    ffmpeg_path,
    is_listening_question,
    stable_audio_name,
    synthesize_many,
)


@dataclass(frozen=True)
class CacheStats:
    directory: Path
    file_count: int
    total_bytes: int
    oldest_mtime: float | None
    newest_mtime: float | None
    wav_count: int = 0
    opus_count: int = 0


def cache_wav_files(directory: str | Path) -> list[Path]:
    cache_dir = Path(directory)
    if not cache_dir.exists():
        return []
    return sorted(path for path in cache_dir.glob("*.wav") if path.is_file())


def cache_audio_files(directory: str | Path) -> list[Path]:
    cache_dir = Path(directory)
    if not cache_dir.exists():
        return []
    files = [path for path in cache_dir.glob("*.wav") if path.is_file()]
    files += [path for path in cache_dir.glob("*.opus") if path.is_file()]
    return sorted(files)


def cache_stats(directory: str | Path) -> CacheStats:
    files = cache_audio_files(directory)
    mtimes = [path.stat().st_mtime for path in files]
    return CacheStats(
        directory=Path(directory),
        file_count=len(files),
        total_bytes=sum(path.stat().st_size for path in files),
        oldest_mtime=min(mtimes) if mtimes else None,
        newest_mtime=max(mtimes) if mtimes else None,
        wav_count=sum(1 for path in files if path.suffix == ".wav"),
        opus_count=sum(1 for path in files if path.suffix == ".opus"),
    )


@dataclass(frozen=True)
class PruneResult:
    removed: list[Path]
    bytes_removed: int


def prune_cache(
    directory: str | Path,
    max_bytes: int | None = None,
    older_than_days: float | None = None,
    dry_run: bool = False,
    now: float | None = None,
) -> PruneResult:
    """Remove least-recently-used cache audio until the constraints are met.

    Cache hits refresh mtime, so mtime order is LRU order.
    """
    if max_bytes is None and older_than_days is None:
        raise ValueError("Pass max_bytes and/or older_than_days to prune.")

    current_time = time.time() if now is None else now
    files = sorted(cache_audio_files(directory), key=lambda path: path.stat().st_mtime)
    removed: list[Path] = []
    bytes_removed = 0

    if older_than_days is not None:
        cutoff = current_time - older_than_days * 86400
        for path in list(files):
            if path.stat().st_mtime < cutoff:
                bytes_removed += path.stat().st_size
                removed.append(path)
                files.remove(path)

    if max_bytes is not None:
        remaining_bytes = sum(path.stat().st_size for path in files)
        for path in list(files):
            if remaining_bytes <= max_bytes:
                break
            size = path.stat().st_size
            remaining_bytes -= size
            bytes_removed += size
            removed.append(path)
            files.remove(path)

    if not dry_run:
        for path in removed:
            path.unlink(missing_ok=True)
    return PruneResult(removed=removed, bytes_removed=bytes_removed)


@dataclass(frozen=True)
class CompressResult:
    compressed: int
    bytes_saved: int
    skipped: int


def compress_cache(
    directory: str | Path,
    older_than_days: float | None = None,
    bitrate: str = "24k",
    now: float | None = None,
) -> CompressResult:
    """Transcode cold cache WAVs to Opus (~10x smaller); playback restores them on demand."""
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        raise RuntimeError("ffmpeg was not found on PATH. Install ffmpeg to compress the audio cache.")

    current_time = time.time() if now is None else now
    cutoff = None if older_than_days is None else current_time - older_than_days * 86400
    compressed = 0
    bytes_saved = 0
    skipped = 0
    for wav in cache_wav_files(directory):
        if cutoff is not None and wav.stat().st_mtime >= cutoff:
            skipped += 1
            continue
        opus = wav.with_suffix(".opus")
        result = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus", "-b:a", bitrate, str(opus)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not opus.exists():
            opus.unlink(missing_ok=True)
            details = (result.stderr or "").strip()
            raise RuntimeError(f"ffmpeg failed on {wav.name}: {details}")
        bytes_saved += wav.stat().st_size - opus.stat().st_size
        wav.unlink()
        compressed += 1
    return CompressResult(compressed=compressed, bytes_saved=bytes_saved, skipped=skipped)


def bundle_pack(
    pack: ExamPack,
    config: TTSConfig,
    output_zip: str | Path,
    include_all_questions: bool = False,
    include_teaching: bool = False,
    progress: Callable[[int, int, str], Any] | None = None,
) -> Path:
    """Warm a pack's audio and export it as one zip with a text→file manifest."""
    texts = pack_speech_texts(
        pack,
        include_all_questions=include_all_questions,
        include_teaching=include_teaching,
    )
    if not texts:
        raise ValueError("This pack has no speakable text to bundle.")
    warm_pack(
        pack,
        config,
        include_all_questions=include_all_questions,
        include_teaching=include_teaching,
        progress=progress,
    )

    manifest: dict[str, Any] = {
        "pack_id": pack.pack_id,
        "pack_version": str(pack.data["pack_version"]),
        "provider": config.provider,
        "language": config.language,
        "voice": config.speaker_id or "default",
        "speed": config.speed,
        "items": [],
    }
    zip_path = Path(output_zip)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for text in texts:
            file_name = stable_audio_name(
                text,
                provider=config.provider,
                language=config.language,
                speed=config.speed,
                speaker_id=config.speaker_id,
                speaker_wav=config.speaker_wav,
                steps=config.steps,
            )
            archive.write(config.output_dir / file_name, arcname=file_name)
            manifest["items"].append({"text": text, "file": file_name})
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return zip_path


def pack_speech_texts(
    pack: ExamPack,
    include_all_questions: bool = False,
    include_teaching: bool = False,
) -> list[str]:
    """Collect every text a pack can speak, listening questions first."""
    texts: list[str] = []
    for question in pack.questions():
        if include_all_questions or is_listening_question(question):
            texts.extend(
                collect_question_speech_texts(question, include_prompt=False)
            )
        if include_teaching:
            texts.extend(
                collect_question_speech_texts(
                    question,
                    include_passage=False,
                    include_prompt=False,
                    include_explanation=True,
                )
            )
    return dedupe(texts)


def warm_pack(
    pack: ExamPack,
    config: TTSConfig,
    include_all_questions: bool = False,
    include_teaching: bool = False,
    progress: Callable[[int, int, str], Any] | None = None,
) -> tuple[int, int]:
    """Pre-generate pack audio so test taking never waits on synthesis.

    Returns (generated, cached) counts.
    """
    texts = pack_speech_texts(
        pack,
        include_all_questions=include_all_questions,
        include_teaching=include_teaching,
    )
    config = replace(config, playback=False)
    generated = 0
    cached = 0
    for index, text in enumerate(texts, start=1):
        target = config.output_dir / stable_audio_name(
            text,
            provider=config.provider,
            language=config.language,
            speed=config.speed,
            speaker_id=config.speaker_id,
            speaker_wav=config.speaker_wav,
            steps=config.steps,
        )
        already_cached = target.exists() and not config.force
        if progress:
            progress(index, len(texts), text)
        synthesize_many([text], config)
        if already_cached:
            cached += 1
        else:
            generated += 1
    return generated, cached
