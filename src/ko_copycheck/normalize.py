"""Text normalization that keeps a map back to the text shown in reports."""
from __future__ import annotations

import bisect
import unicodedata
from dataclasses import dataclass

Span = tuple[int, int]


@dataclass(frozen=True)
class Normalized:
    """A normalized document.

    ``display`` is the NFKC form of the input (what reports show). ``text`` keeps only
    letters and digits, case-folded. ``offsets[i]`` is the index in ``display`` of the
    character that produced ``text[i]``.
    """

    display: str
    text: str
    offsets: list[int]


def normalize(raw: str) -> Normalized:
    """NFKC, casefold, keep letters and digits only.

    NFKC also composes decomposed (NFD) Hangul from macOS file systems, so the same
    sentence typed or saved on different systems compares equal.
    """
    display = unicodedata.normalize("NFKC", raw)
    chars: list[str] = []
    offsets: list[int] = []
    for i, ch in enumerate(display):
        if unicodedata.category(ch)[0] in "LN":
            for c in ch.casefold():  # casefold can expand one char into several
                chars.append(c)
                offsets.append(i)
    return Normalized(display, "".join(chars), offsets)


def normalize_text(raw: str) -> str:
    """Normalized text only (no offsets)."""
    return normalize(raw).text


def to_display_span(offsets: list[int], start: int, end: int) -> Span:
    """Map a normalized ``[start, end)`` span to a ``display`` span."""
    if end <= start:
        return (0, 0)
    return (offsets[start], offsets[end - 1] + 1)


def from_display_span(offsets: list[int], start: int, end: int) -> Span:
    """Map a ``display`` span to the normalized span of characters inside it."""
    return (bisect.bisect_left(offsets, start), bisect.bisect_left(offsets, end))
