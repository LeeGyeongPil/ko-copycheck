"""Inverted index over fingerprints: candidate document pairs and common-piece filter."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import combinations

from .config import Config

Fingerprints = list[tuple[int, int]]  # (hash, position)


def group_threshold(n_docs: int, cfg: Config) -> int:
    """Number of documents from which a k-gram counts as group-common.

    Needs both a share of the class (``group_ratio``) and an absolute minimum
    (``group_min_docs``), so a copied passage shared by exactly two students is never
    mistaken for common material.
    """
    return max(cfg.group_min_docs, math.ceil(cfg.group_ratio * n_docs))


def document_frequency(hash_lists: list[list[int]]) -> Counter[int]:
    """In how many documents does each k-gram hash occur (any position, not only fingerprints)."""
    df: Counter[int] = Counter()
    for hashes in hash_lists:
        df.update(set(hashes))
    return df


def candidate_hits(
    fps: list[Fingerprints], df: Counter[int], cfg: Config
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Shared fingerprints per document pair ``(i, j)`` with ``i < j``.

    Returns ``{(i, j): [(pos_i, pos_j), ...]}``. Hashes that are group-common are not
    used to create candidates. Documents without a shared fingerprint never pair up,
    which is what keeps hundreds of documents tractable.
    """
    threshold = group_threshold(len(fps), cfg)
    postings: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for doc, picks in enumerate(fps):
        for h, pos in picks:
            postings[h].append((doc, pos))
    hits: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for h, occ in postings.items():
        if len(occ) < 2 or df[h] >= threshold or len(occ) > cfg.max_postings:
            continue
        for (d1, p1), (d2, p2) in combinations(occ, 2):
            if d1 == d2:
                continue
            if d1 < d2:
                hits[(d1, d2)].append((p1, p2))
            else:
                hits[(d2, d1)].append((p2, p1))
    return hits


def common_excluded(
    fps: list[Fingerprints], df: Counter[int], cfg: Config, ignore: frozenset[int] | set[int] = frozenset()
) -> tuple[int, int]:
    """Count what the group-common filter skips: ``(fingerprints, documents)``.

    A fingerprint hash is counted when it is a fingerprint in at least two documents but its
    document frequency reaches :func:`group_threshold`, i.e. ``candidate_hits`` ignores it.
    Hashes dropped only because of ``max_postings`` are not counted, and neither are hashes in
    ``ignore`` (the engine passes the k-grams of the assignment prompt, which every document
    shares by design and which are handled by the prompt mask). Read-only: scores and
    candidates do not depend on this function.
    """
    threshold = group_threshold(len(fps), cfg)
    owners: dict[int, set[int]] = defaultdict(set)
    for doc, picks in enumerate(fps):
        for h, _pos in picks:
            owners[h].add(doc)
    common = {h for h, docs in owners.items() if len(docs) >= 2 and df[h] >= threshold and h not in ignore}
    touched = {doc for h in common for doc in owners[h]}
    return len(common), len(touched)
