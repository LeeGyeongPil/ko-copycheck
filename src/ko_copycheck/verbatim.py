"""Layer 1: verbatim matches. Extend shared fingerprints to character-level spans."""
from __future__ import annotations

from .config import Config
from .winnow import Fingerprints

Span = tuple[int, int]


def merge_spans(spans: list[Span]) -> list[Span]:
    """Sort and merge overlapping or touching spans."""
    out: list[list[int]] = []
    for s, e in sorted(spans):
        if e <= s:
            continue
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def covered(spans: list[Span]) -> int:
    """Number of characters covered by the union of ``spans``."""
    return sum(e - s for s, e in merge_spans(spans))


def subtract(span: Span, masks: list[Span]) -> list[Span]:
    """Remove ``masks`` (merged, sorted) from ``span``; return the remaining pieces."""
    s, e = span
    pieces: list[Span] = []
    cur = s
    for ms, me in masks:
        if me <= cur:
            continue
        if ms >= e:
            break
        if ms > cur:
            pieces.append((cur, ms))
        cur = max(cur, me)
    if cur < e:
        pieces.append((cur, e))
    return pieces


def extend_match(a: str, b: str, i: int, j: int, k: int) -> tuple[int, int, int, int] | None:
    """Grow the exact match ``a[i:i+k] == b[j:j+k]`` to its maximal extent.

    Returns ``(a_start, a_end, b_start, b_end)`` or ``None`` when the k-grams differ
    (a hash collision, which a string comparison filters out).
    """
    if a[i : i + k] != b[j : j + k] or len(a) < i + k or len(b) < j + k:
        return None
    s1, s2 = i, j
    while s1 > 0 and s2 > 0 and a[s1 - 1] == b[s2 - 1]:
        s1 -= 1
        s2 -= 1
    e1, e2 = i + k, j + k
    while e1 < len(a) and e2 < len(b) and a[e1] == b[e2]:
        e1 += 1
        e2 += 1
    return (s1, e1, s2, e2)


def prompt_mask(doc: str, doc_fps: Fingerprints, prompts: list[str], prompt_fps: list[Fingerprints], k: int) -> list[Span]:
    """Character spans of ``doc`` that repeat the assignment prompt.

    Masking whole character spans (instead of dropping the prompt's fingerprint hashes)
    also removes the k-grams that straddle the edge of the quoted prompt, which would
    otherwise create small fake matches between unrelated documents.
    """
    spans: list[Span] = []
    for prompt, pfps in zip(prompts, prompt_fps):
        where: dict[int, list[int]] = {}
        for h, pos in pfps:
            where.setdefault(h, []).append(pos)
        done: dict[int, int] = {}  # diagonal -> end already explained
        for h, pos in doc_fps:
            for ppos in where.get(h, ()):
                diag = pos - ppos
                if done.get(diag, -1) > pos:
                    continue
                m = extend_match(prompt, doc, ppos, pos, k)
                if m:
                    spans.append((m[2], m[3]))
                    done[diag] = m[3]
    return merge_spans(spans)


def pair_spans(
    a: str,
    b: str,
    hits: list[tuple[int, int]],
    mask_a: list[Span],
    mask_b: list[Span],
    cfg: Config,
) -> tuple[list[Span], list[Span]]:
    """Verbatim spans for one document pair, as ``(spans_in_a, spans_in_b)``.

    Each shared fingerprint is extended into a maximal match; prompt-masked characters
    of either document are cut out; remaining pieces shorter than ``min_match`` are
    dropped.
    """
    spans_a: list[Span] = []
    spans_b: list[Span] = []
    done: dict[int, int] = {}  # diagonal -> end (in a) already explained
    for pa, pb in sorted(hits):
        diag = pa - pb
        if done.get(diag, -1) > pa:
            continue
        m = extend_match(a, b, pa, pb, cfg.k)
        if not m:
            continue
        s1, e1, s2, e2 = m
        done[diag] = e1
        delta = s2 - s1  # same length on both sides: shift between coordinate systems
        shifted_b = [(ms - delta, me - delta) for ms, me in mask_b]
        masks = merge_spans(mask_a + shifted_b)
        for ps, pe in subtract((s1, e1), masks):
            if pe - ps >= cfg.min_match:
                spans_a.append((ps, pe))
                spans_b.append((ps + delta, pe + delta))
    return merge_spans(spans_a), merge_spans(spans_b)
