"""Layer 2: paraphrase detection with sentence character-bigram Dice similarity."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass

from .normalize import normalize_text

Span = tuple[int, int]

_TERMINAL = re.compile(r"(?<=[.!?。])\s+|\n+")
_ENDS = (".", "!", "?", "。")


def split_sentences(display: str, min_chars: int) -> list[Span]:
    """Split text into sentence spans (indexes into ``display``).

    Boundaries are ``. ? ! 。`` followed by whitespace, and line breaks. A fragment that
    is too short and does not end with terminal punctuation (for example a wrapped PDF
    line) is joined to the next one. Sentences shorter than ``min_chars`` normalized
    characters are dropped.
    """
    pieces: list[Span] = []
    pos = 0
    for m in _TERMINAL.finditer(display):
        pieces.append((pos, m.start()))
        pos = m.end()
    pieces.append((pos, len(display)))

    out: list[Span] = []
    start: int | None = None
    for s, e in pieces:
        if e <= s or not display[s:e].strip():
            continue
        if start is None:
            start = s
        text = display[start:e].strip()
        if text.endswith(_ENDS) or len(normalize_text(text)) >= min_chars:
            if len(normalize_text(text)) >= min_chars:
                out.append((start, e))
            start = None
    if start is not None and len(normalize_text(display[start:])) >= min_chars:
        out.append((start, len(display)))
    return out


def bigram_set(norm_sentence: str) -> frozenset[str]:
    """Set of character bigrams of an already normalized sentence."""
    return frozenset(norm_sentence[i : i + 2] for i in range(len(norm_sentence) - 1))


def dice(a: frozenset[str], b: frozenset[str]) -> float:
    """Dice coefficient of two sets."""
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


@dataclass(frozen=True)
class Sentence:
    """One sentence of one document."""

    doc: int
    span: Span  # normalized-text coordinates
    bigrams: frozenset[str]


_EPS = 1e-9


def matches_bruteforce(sents: list[Sentence], t: float) -> set[tuple[int, int]]:
    """All sentence index pairs ``(i, j)``, ``i < j``, from different documents with Dice >= t."""
    out: set[tuple[int, int]] = set()
    for i in range(len(sents)):
        for j in range(i + 1, len(sents)):
            if sents[i].doc != sents[j].doc and dice(sents[i].bigrams, sents[j].bigrams) >= t - _EPS:
                out.add((i, j))
    return out


def matches_prefix(sents: list[Sentence], t: float) -> tuple[set[tuple[int, int]], int]:
    """Same result as :func:`matches_bruteforce`, found with a rare-bigram prefix filter.

    Dice >= t forces two sentences to share a minimum number of bigrams. If each
    sentence's bigrams are sorted rarest first, any pair that reaches that overlap must
    share a bigram among the first few (the "prefix"), so only sentences sharing a rare
    prefix bigram are ever compared. Returns ``(pairs, candidates_compared)``.
    """
    df: dict[str, int] = defaultdict(int)
    for s in sents:
        for g in s.bigrams:
            df[g] += 1
    order = sorted(range(len(sents)), key=lambda i: len(sents[i].bigrams))  # shorter first
    index: dict[str, list[int]] = defaultdict(list)
    found: set[tuple[int, int]] = set()
    compared = 0
    for y in order:
        grams = sorted(sents[y].bigrams, key=lambda g: (df[g], g))
        n = len(grams)
        if n == 0:
            continue
        # Earlier sentences are not longer than y, so Dice >= t needs an overlap of at
        # least t*n/(2-t) (probe side) and, for the shorter one, at least t*|x| (index side).
        need_probe = max(1, math.ceil(t * n / (2 - t) - _EPS))
        cands: set[int] = set()
        for g in grams[: n - need_probe + 1]:
            for x in index.get(g, ()):
                if sents[x].doc != sents[y].doc:
                    cands.add(x)
        for x in cands:
            compared += 1
            if dice(sents[x].bigrams, sents[y].bigrams) >= t - _EPS:
                found.add((min(x, y), max(x, y)))
        need_index = max(1, math.ceil(t * n - _EPS))
        for g in grams[: n - need_index + 1]:
            index[g].append(y)
    return found, compared
