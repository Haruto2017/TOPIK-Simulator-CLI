"""Inline markup inside question text.

Real exam items point at part of a sentence — 밑줄 친 부분 ("the underlined
part"). Packs mark that span with ``<u>…</u>`` in a prompt, passage, or
option. It is the only markup: everything else is plain text. Each surface
decides how to show it (an underline on the web and in colour terminals,
``_x_`` in plain text) and strips it wherever text is spoken or tokenized.
"""
from __future__ import annotations

import re

_UNDERLINE = re.compile(r"<u>(.*?)</u>", re.S)
_TAG = re.compile(r"</?u>")


def strip_markup(text: str) -> str:
    """The text without any ``<u>``/``</u>`` tags."""
    return _TAG.sub("", str(text or ""))


def underline_spans(text: str) -> list[tuple[str, bool]]:
    """Split text into ``(chunk, underlined)`` runs, in order."""
    text = str(text or "")
    spans: list[tuple[str, bool]] = []
    position = 0
    for match in _UNDERLINE.finditer(text):
        if match.start() > position:
            spans.append((text[position:match.start()], False))
        spans.append((match.group(1), True))
        position = match.end()
    if position < len(text):
        spans.append((text[position:], False))
    return spans


def plain_underline(text: str) -> str:
    """Underlined spans as ``_x_`` for surfaces without real underline."""
    return "".join(f"_{chunk}_" if underlined else chunk for chunk, underlined in underline_spans(text))


def markup_errors(text: str) -> list[str]:
    """Problems with the markup in one field (unbalanced or nested tags)."""
    depth = 0
    for match in _TAG.finditer(str(text or "")):
        if match.group(0) == "<u>":
            depth += 1
            if depth > 1:
                return ["nested <u> tags"]
        else:
            depth -= 1
            if depth < 0:
                return ["</u> without a matching <u>"]
    return ["<u> without a matching </u>"] if depth else []
