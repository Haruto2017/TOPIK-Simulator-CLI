from __future__ import annotations

"""Look something up — the student's 'what was that word again?'.

Searches every imported pack's taught vocabulary and grammar patterns by
substring (Korean or English), attributing each hit to its pack. This is the
digest-and-revisit tool: lessons introduce items once, and this finds them
again weeks later without replaying the lesson.
"""

from pathlib import Path
from typing import Any

from .library import DEFAULT_LIBRARY_DIR, latest_packs, load_pack_ref


def search_library(
    query: str,
    library_dir: str | Path = DEFAULT_LIBRARY_DIR,
    limit: int = 12,
) -> dict[str, list[dict[str, Any]]]:
    """Vocabulary and grammar entries matching the query, with their sources."""
    from .flashcards import build_deck
    from .grammar import collect_grammar_entries

    wanted = query.strip().casefold()
    result: dict[str, list[dict[str, Any]]] = {"vocabulary": [], "grammar": []}
    if not wanted:
        return result
    try:
        entries = latest_packs(library_dir)
    except (OSError, ValueError, KeyError):
        return result

    seen_vocab: set[tuple[str, str]] = set()
    seen_grammar: set[str] = set()
    for entry in entries:
        try:
            pack = load_pack_ref(f"{entry['pack_id']}@{entry['pack_version']}", library_dir)
        except (OSError, ValueError, KeyError):
            continue
        if len(result["vocabulary"]) < limit:
            for card in build_deck(pack, seed=0):
                haystack = f"{card['ko']} {card['en']} {card.get('note', '')}".casefold()
                key = (card["ko"], card["en"])
                if wanted in haystack and key not in seen_vocab:
                    seen_vocab.add(key)
                    result["vocabulary"].append({**card, "pack_id": pack.pack_id})
                    if len(result["vocabulary"]) >= limit:
                        break
        if len(result["grammar"]) < limit:
            for point in collect_grammar_entries(pack):
                haystack = f"{point['pattern']} {point['explanation']} {point['example']}".casefold()
                if wanted in haystack and point["pattern"] not in seen_grammar:
                    seen_grammar.add(point["pattern"])
                    result["grammar"].append({**point, "pack_id": pack.pack_id})
                    if len(result["grammar"]) >= limit:
                        break
    return result
