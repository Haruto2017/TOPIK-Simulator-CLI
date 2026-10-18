from __future__ import annotations

"""Curriculum wordlists — vocabulary beyond what exam packs teach.

Packs teach words in context; wordlists carry the rest of a beginner
curriculum (``content/vocabulary/*.json``), each word keyed to the study-path
unit that introduces its domain. The loader is forgiving: files or entries
that do not match the schema are skipped, never fatal.
"""

import json
from pathlib import Path
from typing import Any, Iterable

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
    seen: set[str] = set()
    words: list[dict[str, str]] = []
    for _, data in _wordlist_files(path):
        for word in _entries(data):
            if word["ko"] in seen:
                continue
            seen.add(word["ko"])
            words.append(word)
    return words


def _wordlist_files(path: str | Path | Iterable[str | Path]) -> list[tuple[Path, dict[str, Any]]]:
    """Every valid wordlist file under the directories, in precedence order."""
    if isinstance(path, (str, Path)):
        directories = [Path(path)]
    else:
        directories = [Path(entry) for entry in path]
    found: list[tuple[Path, dict[str, Any]]] = []
    for file in (f for d in directories if d.is_dir() for f in sorted(d.glob("*.json"))):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("schema_version") == WORDLIST_SCHEMA_VERSION \
                and isinstance(data.get("words"), list):
            found.append((file, data))
    return found


def _entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A file's valid entries, normalized (first of a repeated ``ko`` wins)."""
    seen: set[str] = set()
    words: list[dict[str, Any]] = []
    for entry in data.get("words", []):
        if not isinstance(entry, dict):
            continue
        ko = str(entry.get("ko", "") or "").strip()
        en = str(entry.get("en", "") or "").strip()
        if not ko or not en or ko in seen:
            continue
        seen.add(ko)
        packs = entry.get("packs")
        word: dict[str, Any] = {
            "ko": ko,
            "en": en,
            "unit": str(entry.get("unit", "") or "").strip(),
            "note": str(entry.get("note", "") or "").strip(),
            # Provenance for mined lists: which packs actually use the word,
            # so vocabulary practice can be scoped to one exam.
            "packs": [str(p) for p in packs] if isinstance(packs, list) else [],
        }
        for lang in ("zh", "ja"):  # inline meanings (see lexicon.py)
            if str(entry.get(lang, "") or "").strip():
                word[lang] = str(entry[lang]).strip()
        words.append(word)
    return words


def list_word_sets(path: str | Path | Iterable[str | Path] = DEFAULT_WORDLIST_DIR) -> list[dict[str, Any]]:
    """Named word sets: wordlist files that declare ``"set": {"id", "title"}``.

    A set keeps every one of its words together — including words another
    list already defines — so a personal collection (words picked up from
    Korean media, say) is practisable as one unit, while its new words also
    join the shared pool (and so the part-of-speech sets).
    """
    sets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for file, data in _wordlist_files(path):
        meta = data.get("set")
        if not isinstance(meta, dict) or not str(meta.get("id", "")).strip():
            continue
        set_id = str(meta["id"]).strip()
        if set_id in seen:
            continue
        seen.add(set_id)
        sets.append({"id": set_id, "title": str(meta.get("title", "") or set_id).strip(),
                     "description": str(meta.get("description", "") or "").strip(),
                     "count": len(_entries(data)), "file": str(file)})
    return sets


def words_for_set(set_id: str, path: str | Path | Iterable[str | Path] = DEFAULT_WORDLIST_DIR) -> list[dict[str, Any]]:
    """Every word of one named set, in the set's own order and glosses."""
    wanted = str(set_id).strip()
    for _, data in _wordlist_files(path):
        meta = data.get("set")
        if isinstance(meta, dict) and str(meta.get("id", "")).strip() == wanted:
            return _entries(data)
    return []


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


def words_for_class(word_class_id: str, path: str | Path | Iterable[str | Path] = DEFAULT_WORDLIST_DIR) -> list[dict[str, str]]:
    """Every wordlist entry of one part of speech (noun/verb/adjective/adverb).

    The class is inferred from the entry itself — see ``pos.word_class`` — so
    no list needs a hand-tagged field.
    """
    from .pos import words_in_class

    return words_in_class(load_wordlists(path), word_class_id)


def wordlist_glosses(path: str | Path = DEFAULT_WORDLIST_DIR) -> dict[str, str]:
    """Korean word → gloss for every wordlist entry (note after an em dash)."""
    glosses: dict[str, str] = {}
    for entry in load_wordlists(path):
        gloss = entry["en"]
        if entry["note"]:
            gloss = f"{gloss} — {entry['note']}"
        glosses[entry["ko"]] = gloss
    return glosses
