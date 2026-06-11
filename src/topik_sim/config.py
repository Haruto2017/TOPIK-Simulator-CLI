from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# JSON instead of TOML keeps the core stdlib-only on Python 3.10 (no tomllib).
DEFAULT_CONFIG_FILENAME = "topik.config.json"
ENV_CONFIG_PATH = "TOPIK_CONFIG"


def config_path() -> Path:
    env = os.environ.get(ENV_CONFIG_PATH)
    if env:
        return Path(env)
    return Path(DEFAULT_CONFIG_FILENAME)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load workspace defaults. A missing file means built-in defaults."""
    config_file = Path(path) if path is not None else config_path()
    if not config_file.exists():
        return {}
    try:
        with config_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read config {config_file}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a JSON object: {config_file}")
    return data


def config_value(config: dict[str, Any], section: str, key: str, default: Any) -> Any:
    section_data = config.get(section)
    if isinstance(section_data, dict) and key in section_data:
        return section_data[key]
    return default
