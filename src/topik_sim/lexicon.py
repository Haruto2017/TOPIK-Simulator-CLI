"""Mandarin and Japanese meanings for Korean vocabulary.

English glosses are often too loose to pin a Korean word down (쓰다: write?
use? wear?). The lexicon pairs each headword with its Mandarin (Simplified)
and Japanese equivalents, and every vocabulary surface — flashcards, recall,
spaced review, homework recall, the misses drill — shows them under the
English.

Files live in ``content/lexicon/`` (tracked) and ``content/private/lexicon/``
(personal, for words that only come from private material), beside the
library like the wordlists::

    {"schema_version": "topik-sim.lexicon.v1",
     "entries": {"학교": {"zh": "学校", "ja": "学校"}, ...}}

A wordlist entry or a pack's explanation vocabulary may also carry ``zh``/``ja``
inline; inline values win over the lexicon. Every bundled word is required to
have both (``tests/test_lexicon.py``), so new vocabulary must ship with them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

LEXICON_SCHEMA_VERSION = "topik-sim.lexicon.v1"
LANGUAGES: tuple[tuple[str, str], ...] = (("zh", "中文"), ("ja", "日本語"))
_RECALL_PREFIX = "Type the Korean:"

_cache: dict[tuple[str, ...], tuple[tuple[float, ...], dict[str, dict[str, str]]]] = {}


def lexicon_dirs_for(library_dir: str | Path | None) -> tuple[Path, ...]:
    """Lexicon directories beside a library (tracked first, then private)."""
    root = Path(library_dir).parent if library_dir is not None else Path("content")
    return (root / "lexicon", root / "private" / "lexicon")


def load_lexicon(directories: Iterable[str | Path]) -> dict[str, dict[str, str]]:
    """Korean headword → {"zh", "ja"}; the first file to define a word wins."""
    files = [file for directory in map(Path, directories) if directory.is_dir()
             for file in sorted(directory.glob("*.json"))]
    key = tuple(str(f) for f in files)
    stamp = tuple(f.stat().st_mtime for f in files)
    cached = _cache.get(key)
    if cached and cached[0] == stamp:
        return cached[1]
    merged: dict[str, dict[str, str]] = {}
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("schema_version") != LEXICON_SCHEMA_VERSION:
            continue
        for ko, entry in (data.get("entries") or {}).items():
            if not isinstance(entry, dict) or ko in merged:
                continue
            meanings = {lang: str(entry.get(lang, "") or "").strip() for lang, _ in LANGUAGES}
            if any(meanings.values()):
                merged[str(ko).strip()] = meanings
    _cache[key] = (stamp, merged)
    return merged


class Lexicon:
    """Meaning lookup for one library (lexicons beside it)."""

    def __init__(self, library_dir: str | Path | None = None) -> None:
        self.entries = load_lexicon(lexicon_dirs_for(library_dir))

    def get(self, ko: str, inline: dict[str, Any] | None = None) -> dict[str, str]:
        """{"zh", "ja"} for a word — inline values first, then the lexicon."""
        found = dict(self.entries.get(str(ko).strip(), {}))
        for lang, _ in LANGUAGES:
            value = str((inline or {}).get(lang, "") or "").strip()
            if value:
                found[lang] = value
        return {lang: found[lang] for lang, _ in LANGUAGES if found.get(lang)}

    def attach(self, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Give vocabulary cards (``ko`` + ``en``) their ``zh``/``ja`` in place."""
        for card in cards:
            card.update(self.get(card.get("ko", ""), card))
        return cards

    def decorate_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add ``meanings`` to vocabulary-recall items ("Type the Korean: …" prompts
        and English→Korean recall items, which carry ``srs_en``).

        Covers every producer of recall prompts (recall, spaced review,
        homework recall, the misses drill) at the one place a session starts.
        """
        for item in items:
            recall = str(item.get("show", "")).startswith(_RECALL_PREFIX) or "srs_en" in item
            if item.get("meanings") or not recall:
                continue
            for ko in [item.get("answer"), *item.get("accept", [])]:
                meanings = self.get(str(ko or ""))
                if meanings:
                    item["meanings"] = meanings
                    break
        return items


def meaning_line(meanings: dict[str, str] | None) -> str:
    """``中文 学校 · 日本語 学校`` (empty when nothing is known)."""
    parts = [f"{label} {meanings[lang]}" for lang, label in LANGUAGES if (meanings or {}).get(lang)]
    return "  ·  ".join(parts)
