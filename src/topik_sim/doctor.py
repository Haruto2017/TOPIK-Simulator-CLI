"""Environment self-diagnosis: `topik-sim doctor`.

Each check returns ``(status, label, detail)`` where status is PASS, WARN, or
FAIL. WARN means the simulator still works with a degraded feature (no rich
prompt, no audio); FAIL means something needs fixing before studying. Every
check is safe on a machine with none of the optional pieces installed —
nothing here synthesizes audio, downloads models, or needs a GPU.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

from .config import config_path, load_config
from .library import DEFAULT_LIBRARY_DIR, list_packs, validate_library
from .tts import TTSConfig, resolve_supertonic_python, supertonic_helper_path


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

DEFAULT_DATA_DIR = Path("data")
MIN_PYTHON = (3, 9)

Check = tuple[str, str, str]


def check_python(version_info: tuple[int, ...] | None = None) -> Check:
    info = version_info if version_info is not None else tuple(sys.version_info[:3])
    running = ".".join(str(part) for part in info[:3])
    if info[:2] >= MIN_PYTHON:
        return (PASS, "Python", running)
    wanted = ".".join(str(part) for part in MIN_PYTHON)
    return (FAIL, "Python", f"{running} — topik-sim needs Python {wanted} or newer")


def check_prompt_toolkit() -> Check:
    if importlib.util.find_spec("prompt_toolkit") is not None:
        return (PASS, "prompt_toolkit", "installed — rich prompt with completion")
    return (WARN, "prompt_toolkit", "not installed — plain prompt fallback (pip install prompt_toolkit)")


def check_tts_runtime() -> Check:
    soundless = "exams run soundless, transcripts are shown instead"
    try:
        python_path = resolve_supertonic_python(TTSConfig())
    except RuntimeError as exc:
        return (WARN, "TTS runtime", f"{exc} — {soundless}")
    helper = supertonic_helper_path()
    if not helper.exists():
        return (WARN, "TTS runtime", f"helper missing: {helper} — {soundless}")
    return (PASS, "TTS runtime", f"{python_path} + {helper.name}")


def check_ffmpeg() -> Check:
    found = shutil.which("ffmpeg")
    if found:
        return (PASS, "ffmpeg", found)
    return (WARN, "ffmpeg", "not on PATH — audio compress/restore unavailable")


def check_config() -> Check:
    path = config_path()
    if not path.exists():
        return (PASS, "Config", "no config file — built-in defaults")
    try:
        load_config(path)
    except ValueError as exc:
        return (FAIL, "Config", str(exc))
    return (PASS, "Config", f"{path} parsed")


def check_library(library_dir: str | Path = DEFAULT_LIBRARY_DIR) -> Check:
    try:
        errors = validate_library(library_dir)
    except (OSError, ValueError, KeyError) as exc:
        return (FAIL, "Library", f"could not read {library_dir}: {exc}")
    if errors:
        shown = "; ".join(errors[:3])
        more = f" (+{len(errors) - 3} more)" if len(errors) > 3 else ""
        return (FAIL, "Library", f"{shown}{more} — see: topik-sim validate-library")
    packs = list_packs(library_dir)
    if not packs:
        return (WARN, "Library", "valid but empty — run: topik-sim setup")
    return (PASS, "Library", f"{len(packs)} pack(s) imported")


def check_data_dir(data_dir: str | Path = DEFAULT_DATA_DIR) -> Check:
    directory = Path(data_dir)
    probe = directory / f".doctor-write-probe-{os.getpid()}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return (FAIL, "Data directory", f"{directory} is not writable: {exc}")
    return (PASS, "Data directory", f"{directory} is writable")


def run_checks(
    library_dir: str | Path = DEFAULT_LIBRARY_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> list[Check]:
    return [
        check_python(),
        check_prompt_toolkit(),
        check_tts_runtime(),
        check_ffmpeg(),
        check_config(),
        check_library(library_dir),
        check_data_dir(data_dir),
    ]


def format_checks(checks: list[Check]) -> list[str]:
    """One aligned line per check, then a summary line."""
    label_width = max(len(label) for _, label, _ in checks)
    lines = [f"{status}  {label.ljust(label_width)}  {detail}" for status, label, detail in checks]
    passed = sum(1 for status, _, _ in checks if status == PASS)
    warned = sum(1 for status, _, _ in checks if status == WARN)
    failed = sum(1 for status, _, _ in checks if status == FAIL)
    lines.append("")
    lines.append(f"{passed} passed, {warned} warning(s), {failed} failure(s).")
    return lines


def has_failure(checks: list[Check]) -> bool:
    return any(status == FAIL for status, _, _ in checks)
