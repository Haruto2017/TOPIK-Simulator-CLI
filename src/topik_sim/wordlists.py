from __future__ import annotations

"""Curriculum wordlists — vocabulary beyond what exam packs teach.

Packs teach words in context; wordlists carry the rest of a beginner
curriculum (``content/vocabulary/*.json``), each word keyed to the study-path
unit that introduces its domain. The loader is forgiving: files or entries
that do not match the schema are skipped, never fatal.
"""

import json
from pathlib import Path
from typing import Iterable

WORDLIST_SCHEMA_VERSION = "topik-sim.vocabulary.v1"
DEFAULT_WORDLIST_DIR = Path("content") / "vocabulary"


def wordlist_dir_for(library_dir: str | Path) -> Path:
    """The wordlist directory that sits beside a content library.

    The bundled layout keeps ``vocabulary/`` next to ``library/`` under
    ``content/``; deriving the path from the library keeps temp-dir libraries
    (tests, scratch workspaces) hermetic — they simply have no wordlists.
    """
    return Path(library_dir).parent / "vocabulary"


def wordlist_dirs_for(library_dir: str | Path) -> tuple[Path, ...]:
    """Every wordlist directory beside a library, in precedence order.

    ``content/private/vocabulary/`` is read after the bundled one so personal,
    never-committed lists (e.g. vocabulary mined from past-paper packs) fill in
    words the curriculum does not teach, without overriding a curated gloss.
    """
    root = Path(library_dir).parent
    return (root / "vocabulary", root / "private" / "vocabulary")


def load_wordlists(
    path: str | Path | Iterable[str | Path] = DEFAULT_WORDLIST_DIR,
) -> list[dict[str, str]]:
    """Every valid wordlist entry, deduplicated by Korean headword.

    Accepts one directory or several; entries missing ``ko`` or ``en`` are
    skipped, and the first file (directories in order, then files sorted by
    name) wins on duplicate ``ko``.
    """
    if isinstance(path, (str, Path)):
        directories = [Path(path)]
    else:
        directories = [Path(entry) for entry in path]
    seen: set[str] = set()
    words: list[dict[str, str]] = []
    files = [file for directory in directories if directory.is_dir()
             for file in sorted(directory.glob("*.json"))]
    for file in files:
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
            packs = entry.get("packs")
            words.append({
                "ko": ko,
                "en": en,
                "unit": str(entry.get("unit", "") or "").strip(),
                "note": str(entry.get("note", "") or "").strip(),
                # Provenance for mined lists: which packs actually use the word,
                # so vocabulary practice can be scoped to one exam.
                "packs": [str(p) for p in packs] if isinstance(packs, list) else [],
            })
    return words


def words_for_pack(pack_id: str, path: str | Path | Iterable[str | Path] = DEFAULT_WORDLIST_DIR) -> list[dict[str, str]]:
    """Wordlist entries recorded as appearing in a given pack."""
    wanted = str(pack_id).strip()
    if not wanted:
        return []
    return [word for word in load_wordlists(path) if wanted in word.get("packs", [])]


def words_for_unit(unit_id: str, path: str | Path | Iterable[str | Path] = DEFAULT_WORDLIST_DIR) -> list[dict[str, str]]:
    """The vocabulary a study-path unit introduces, in wordlist order.

    Units key their words by ``unit``, which is what puts a stage's new words
    on its page — the way a textbook prints them along the bottom.
    """
    wanted = str(unit_id).strip()
    if not wanted:
        return []
    return [word for word in load_wordlists(path) if word.get("unit") == wanted]


def wordlist_glosses(path: str | Path = DEFAULT_WORDLIST_DIR) -> dict[str, str]:
    """Korean word → gloss for every wordlist entry (note after an em dash)."""
    glosses: dict[str, str] = {}
    for entry in load_wordlists(path):
        gloss = entry["en"]
        if entry["note"]:
            gloss = f"{gloss} — {entry['note']}"
        glosses[entry["ko"]] = gloss
    return glosses
