from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from .content import ExamPack
from .tts import (
    TTSConfig,
    collect_question_speech_texts,
    dedupe,
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


def cache_wav_files(directory: str | Path) -> list[Path]:
    cache_dir = Path(directory)
    if not cache_dir.exists():
        return []
    return sorted(path for path in cache_dir.glob("*.wav") if path.is_file())


def cache_stats(directory: str | Path) -> CacheStats:
    files = cache_wav_files(directory)
    mtimes = [path.stat().st_mtime for path in files]
    return CacheStats(
        directory=Path(directory),
        file_count=len(files),
        total_bytes=sum(path.stat().st_size for path in files),
        oldest_mtime=min(mtimes) if mtimes else None,
        newest_mtime=max(mtimes) if mtimes else None,
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
    files = sorted(cache_wav_files(directory), key=lambda path: path.stat().st_mtime)
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
