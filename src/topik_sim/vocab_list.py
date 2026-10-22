"""Printable vocabulary lists.

Any vocabulary scope the practice modes understand — a named word set, a
study-path stage, a part of speech, or one pack — can be listed whole, in its
own order, with each word's English, Mandarin and Japanese meanings and note.
The shell prints it (``/wordlist``) and can save a print-ready HTML page; the
web UI renders the same listing on a page with a Print button.
"""
from __future__ import annotations

import html
from datetime import date
from pathlib import Path
from typing import Any


def vocab_listing(
    library_dir: str | Path,
    pack: Any = None,
    unit: str | None = None,
    word_class: str | None = None,
    word_set: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``{"title", "scope", "words": [{ko, en, zh, ja, note, pos}]}`` for one scope.

    Exactly one of ``pack`` (an ExamPack), ``unit``, ``word_class`` or
    ``word_set`` (a ``list_word_sets`` entry) selects the words. Pack lists
    keep the order the pack teaches them, then any mined words for it.
    """
    from .flashcards import build_deck, wordlist_deck
    from .lexicon import Lexicon
    from .pos import CLASS_LABELS, word_class as classify

    if word_set:
        cards = wordlist_deck(library_dir, word_set=word_set["id"])
        title, scope = word_set["title"], f"set:{word_set['id']}"
    elif word_class:
        cards = wordlist_deck(library_dir, word_class=word_class)
        title, scope = CLASS_LABELS[word_class], f"pos:{word_class}"
    elif unit:
        cards = wordlist_deck(library_dir, unit=unit)
        title, scope = _unit_title(unit), f"unit:{unit}"
    elif pack is not None:
        cards = build_deck(pack, shuffle=False)
        taught = {card["ko"] for card in cards}
        cards += [card for card in wordlist_deck(library_dir, pack.pack_id) if card["ko"] not in taught]
        title, scope = pack.title, pack.pack_id
    else:
        raise ValueError("Choose a word set, study-path stage, part of speech, or pack.")
    Lexicon(library_dir).attach(cards)
    words = [{
        "ko": card["ko"], "en": card["en"], "zh": card.get("zh", ""), "ja": card.get("ja", ""),
        "note": card.get("note", ""), "pos": classify(card["ko"], card["en"]),
    } for card in cards]
    return {"title": title, "scope": scope, "words": words}


def _unit_title(unit_id: str) -> str:
    try:
        from .curriculum import load_curriculum

        for unit in load_curriculum():
            if unit.get("id") == unit_id:
                return f"{unit.get('order', '')}. {unit.get('title', unit_id)}".strip(". ")
    except Exception:  # the list still prints with the bare id
        pass
    return unit_id


def render_text(listing: dict[str, Any], style=lambda text, *codes: text) -> list[str]:
    """Terminal lines: numbered Korean + English, meanings and note beneath."""
    from .lexicon import meaning_line

    words = listing["words"]
    lines = [style(f"{listing['title']} — {len(words)} words", "1")]
    width = max((len(w["ko"]) for w in words), default=0) * 2 + 2   # Hangul is double-width
    for index, word in enumerate(words, 1):
        pad = " " * max(1, width - len(word["ko"]) * 2)
        lines.append(f"{index:>4}. {style(word['ko'], '36')}{pad}{word['en']}")
        extra = meaning_line({"zh": word["zh"], "ja": word["ja"]})
        if word["note"]:
            extra = f"{extra}  ·  {word['note']}" if extra else word["note"]
        if extra:
            lines.append(" " * 6 + style(extra, "2"))
    return lines


def render_html(listing: dict[str, Any]) -> str:
    """A standalone, print-ready HTML page (A4, two-line rows, page-break safe)."""
    from .pos import CLASS_LABELS

    esc = html.escape
    rows = []
    for index, word in enumerate(listing["words"], 1):
        pos = CLASS_LABELS.get(word["pos"], "").split(" · ")[-1]
        note = f"<div class=note>{esc(word['note'])}</div>" if word["note"] else ""
        rows.append(
            "<tr>"
            f"<td class=n>{index}</td><td class=ko>{esc(word['ko'])}<div class=pos>{esc(pos)}</div></td>"
            f"<td>{esc(word['en'])}{note}</td>"
            f"<td lang=zh-Hans>{esc(word['zh'])}</td><td lang=ja>{esc(word['ja'])}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{esc(listing['title'])} — word list</title>
<style>
  @page {{ size: A4; margin: 14mm 12mm; }}
  body {{ font: 11pt/1.35 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", "PingFang SC", "Hiragino Sans", sans-serif; color: #111; margin: 24px; }}
  h1 {{ font-size: 16pt; margin: 0 0 2px; }} .meta {{ color: #666; font-size: 9pt; margin-bottom: 10px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; font-size: 9pt; color: #555; border-bottom: 1.5px solid #333; padding: 4px 6px; }}
  td {{ border-bottom: 0.5px solid #ccc; padding: 5px 6px; vertical-align: top; }}
  tr {{ break-inside: avoid; }} thead {{ display: table-header-group; }}
  .n {{ color: #999; width: 2.2em; text-align: right; font-size: 9pt; }}
  .ko {{ font-size: 13pt; font-weight: 600; white-space: nowrap; }}
  .pos, .note {{ color: #777; font-size: 8.5pt; font-weight: 400; }}
</style></head><body>
<h1>{esc(listing['title'])}</h1>
<div class="meta">{len(listing['words'])} words · {esc(listing['scope'])} · printed {date.today().isoformat()} · TOPIK Simulator</div>
<table><thead><tr><th></th><th>한국어</th><th>English</th><th>中文</th><th>日本語</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>
</body></html>
"""
