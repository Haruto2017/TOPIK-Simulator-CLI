from __future__ import annotations

"""Curriculum wordlists — vocabulary beyond what exam packs teach.

Packs teach words in context; wordlists carry the rest of a beginner
curriculum (``content/vocabulary/*.json``), each word keyed to the study-path
unit that introduces its domain. The loader is forgiving: files or entries
that do not match the schema are skipped, never fatal.
"""

import json
from pathlib import Path

WORDLIST_SCHEMA_VERSION = "topik-sim.vocabulary.v1"
DEFAULT_WORDLIST_DIR = Path("content") / "vocabulary"


def wordlist_dir_for(library_dir: str | Path) -> Path:
    """The wordlist directory that sits beside a content library.

    The bundled layout keeps ``vocabulary/`` next to ``library/`` under
    ``content/``; deriving the path from the library keeps temp-dir libraries
    (tests, scratch workspaces) hermetic — they simply have no wordlists.
    """
    return Path(library_dir).parent / "vocabulary"


def load_wordlists(path: str | Path = DEFAULT_WORDLIST_DIR) -> list[dict[str, str]]:
    """Every valid wordlist entry, deduplicated by Korean headword.

    Entries missing ``ko`` or ``en`` are skipped; the first file (sorted by
    name) wins on duplicate ``ko``.
    """
    directory = Path(path)
    if not directory.is_dir():
        return []
    seen: set[str] = set()
    words: list[dict[str, str]] = []
    for file in sorted(directory.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("schema_version") != WORDLIST_SCHEMA_VERSION:
            continue
        entries = data.get("words")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ko = str(entry.get("ko", "") or "").strip()
            en = str(entry.get("en", "") or "").strip()
            if not ko or not en or ko in seen:
                continue
            seen.add(ko)
            words.append({
                "ko": ko,
                "en": en,
                "unit": str(entry.get("unit", "") or "").strip(),
                "note": str(entry.get("note", "") or "").strip(),
            })
    return words


def wordlist_glosses(path: str | Path = DEFAULT_WORDLIST_DIR) -> dict[str, str]:
    """Korean word → gloss for every wordlist entry (note after an em dash)."""
    glosses: dict[str, str] = {}
    for entry in load_wordlists(path):
        gloss = entry["en"]
        if entry["note"]:
            gloss = f"{gloss} — {entry['note']}"
        glosses[entry["ko"]] = gloss
    return glosses
