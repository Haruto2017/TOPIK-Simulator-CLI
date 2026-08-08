from __future__ import annotations

"""Local media files referenced by pack questions.

A question's ``audio_ref`` or ``image_ref`` may carry a ``file:`` prefix
followed by a path to a real recording or picture — used by past-paper packs
whose official audio and figures live outside the pack JSON. Relative paths
resolve against ``content/private/`` first (where personal, never-committed
materials live) and then the working directory; absolute paths are used as
given. A reference whose file is missing resolves to ``None`` so every
caller can fall back to TTS or text.
"""

from pathlib import Path
from typing import Any

FILE_PREFIX = "file:"

MEDIA_BASE_DIRS: tuple[Path, ...] = (Path("content/private"), Path("."))

_SUFFIX_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def resolve_media_ref(ref: Any, base_dirs: tuple[Path, ...] = MEDIA_BASE_DIRS) -> Path | None:
    text = str(ref or "")
    if not text.startswith(FILE_PREFIX):
        return None
    raw = Path(text[len(FILE_PREFIX):].strip())
    if not str(raw):
        return None
    if raw.is_absolute():
        return raw if raw.is_file() else None
    for base in base_dirs:
        candidate = base / raw
        if candidate.is_file():
            return candidate
    return None


def question_audio_file(question: dict[str, Any]) -> Path | None:
    return resolve_media_ref(question.get("audio_ref"))


def question_image_file(question: dict[str, Any]) -> Path | None:
    return resolve_media_ref(question.get("image_ref"))


def media_mime_type(path: Path) -> str:
    return _SUFFIX_MIME.get(path.suffix.lower(), "application/octet-stream")
