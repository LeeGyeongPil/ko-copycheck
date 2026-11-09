"""Scale check on a synthetic corpus: how many document pairs need a precise comparison?

Generates N documents of M characters from a skewed syllable distribution (a few very
common syllables, a long tail, like real text), plants some copied passages, runs the full
comparison, and prints the number of candidate pairs the inverted index produced.

Usage: uv run python scripts/bench.py --docs 300 --chars 3000
Exit code 0 when candidate pairs < 10% of all pairs and the run is within --limit seconds.
"""
from __future__ import annotations

import argparse
import random
import sys
import time

from ko_copycheck import compare

SYLLABLES = [chr(c) for c in range(0xAC00, 0xAC00 + 11172, 19)][:600]
WEIGHTS = [1.0 / (rank + 1) ** 0.7 for rank in range(len(SYLLABLES))]


def make_corpus(n_docs: int, n_chars: int, seed: int = 1) -> dict[str, str]:
    rng = random.Random(seed)
    docs: dict[str, str] = {}
    for i in range(n_docs):
        chars: list[str] = []
        while len(chars) < n_chars:
            sentence = "".join(rng.choices(SYLLABLES, WEIGHTS, k=rng.randint(15, 45)))
            chars.extend(sentence + ". ")
        docs[f"doc{i:04d}.txt"] = "".join(chars)[:n_chars]
    names = sorted(docs)
    for i in range(0, min(n_docs // 3, 60), 2):  # plant copied passages in 30 pairs
        src, dst = docs[names[i]], names[i + 1]
        piece = src[200:200 + n_chars // 5]
        docs[dst] = docs[dst][:300] + piece + docs[dst][300 + len(piece):]
    return docs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--docs", type=int, default=300)
    ap.add_argument("--chars", type=int, default=3000)
    ap.add_argument("--limit", type=float, default=120.0, help="seconds allowed")
    a = ap.parse_args()
    if a.docs < 2 or a.chars < 100:
        print("error: need --docs >= 2 and --chars >= 100", file=sys.stderr)
        return 2
    docs = make_corpus(a.docs, a.chars)
    t0 = time.perf_counter()
    report = compare(docs)
    elapsed = time.perf_counter() - t0
    s = report.stats
    found = sum(1 for p in report.pairs if p.verbatim_lr > 0)
    print(f"documents: {s['documents']} x {a.chars} chars")
    print(f"all pairs: {s['all_pairs']}")
    print(f"candidate pairs: {s['candidate_pairs']} ({s['candidate_pairs'] / s['all_pairs'] * 100:.2f}% of all pairs)")
    print(f"sentences: {s['sentences']}, sentence comparisons after prefix filter: {s['sentence_candidates_compared']}")
    print(f"planted copies found: {found}")
    print(f"elapsed: {elapsed:.1f}s")
    ok = s["candidate_pairs"] < 0.10 * s["all_pairs"] and elapsed <= a.limit
    print("result:", "ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
