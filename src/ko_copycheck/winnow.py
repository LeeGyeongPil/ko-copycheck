"""Stable k-gram hashing and winnowing (Schleimer, Wilkerson, Aiken 2003)."""
from __future__ import annotations

import hashlib

Fingerprints = list[tuple[int, int]]  # (hash, position)


def stable_hash(gram: str) -> int:
    """64-bit hash that is identical across processes and Python versions.

    The built-in ``hash()`` is randomized per process, which would make any cached or
    parallel fingerprint useless.
    """
    return int.from_bytes(hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest(), "big")


def kgram_hashes(text: str, k: int) -> list[int]:
    """Hash of every k-character window of ``text`` (empty if shorter than ``k``)."""
    return [stable_hash(text[i : i + k]) for i in range(len(text) - k + 1)]


def winnow(hashes: list[int], w: int) -> list[tuple[int, int]]:
    """Select fingerprints ``(hash, position)`` from ``hashes``.

    In every window of ``w`` consecutive hashes pick the minimum; on ties pick the
    rightmost; record a position only once. Any text shared by two documents that is at
    least ``w + k - 1`` characters long contains a full window of identical hashes, so
    both documents select the same fingerprint there.
    """
    n = len(hashes)
    if n == 0:
        return []
    if n < w:  # shorter than one window: treat everything as one window
        w = n
    picks: list[tuple[int, int]] = []
    last = -1
    for start in range(n - w + 1):
        window = hashes[start : start + w]
        low = min(window)
        pos = start + (w - 1 - window[::-1].index(low))  # rightmost minimum
        if pos != last:
            picks.append((low, pos))
            last = pos
    return picks


def fingerprints(text: str, k: int, w: int) -> list[tuple[int, int]]:
    """Convenience: winnowed fingerprints of a normalized text."""
    return winnow(kgram_hashes(text, k), w)
