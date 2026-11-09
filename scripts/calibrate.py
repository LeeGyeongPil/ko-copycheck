"""Derive the default Dice threshold from the hand-written calibration corpus.

Corpus: tests/fixtures/calib/<topic>/{original,paraphrase,unrelated}.txt. For each topic,
every sentence of ``original`` is compared with every sentence of ``paraphrase`` (same
content, reworded) and of ``unrelated`` (same topic, different content). The recommended
threshold is the smallest 0.05 step that keeps a margin of 0.15 above the highest
unrelated Dice.

Usage: uv run python scripts/calibrate.py
"""
from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

from ko_copycheck.config import Config
from ko_copycheck.normalize import normalize
from ko_copycheck.paraphrase import bigram_set, dice, split_sentences

ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "calib"
MARGIN = 0.15  # wide on purpose: with many students the unrelated tail is longer than in this small corpus


def sentence_sets(path: Path, min_chars: int) -> list[frozenset[str]]:
    norm = normalize(path.read_text(encoding="utf-8"))
    sets = []
    for s, e in split_sentences(norm.display, min_chars):
        sets.append(bigram_set(normalize(norm.display[s:e]).text))
    return sets


def best_per_sentence(src: list[frozenset[str]], other: list[frozenset[str]]) -> list[float]:
    """Highest Dice of each ``src`` sentence against any ``other`` sentence."""
    return [max(dice(a, b) for b in other) for a in src]


def main() -> int:
    cfg = Config()
    topics = sorted(p for p in ROOT.iterdir() if p.is_dir())
    if not topics:
        print(f"error: no calibration topics under {ROOT}", file=sys.stderr)
        return 2
    rows = []
    all_unrelated: list[float] = []
    all_para: list[float] = []
    unrelated_pairs: list[float] = []
    for topic in topics:
        o = sentence_sets(topic / "original.txt", cfg.min_sentence)
        p = sentence_sets(topic / "paraphrase.txt", cfg.min_sentence)
        u = sentence_sets(topic / "unrelated.txt", cfg.min_sentence)
        para_best = best_per_sentence(o, p)
        # unrelated side: original and paraphrase sentences against the unrelated text
        unrel_best = best_per_sentence(o, u) + best_per_sentence(p, u)
        unrelated_pairs += [dice(a, b) for a in o + p for b in u]
        rows.append((topic.name, len(o), para_best, unrel_best))
        all_para += para_best
        all_unrelated += unrel_best

    print(f"{'topic':<12}{'sentences':>10}  {'paraphrase best-Dice (min / median / max)':<44}{'unrelated max':>14}")
    for name, n, para, unrel in rows:
        stats = f"{min(para):.2f} / {statistics.median(para):.2f} / {max(para):.2f}"
        print(f"{name:<12}{n:>10}  {stats:<44}{max(unrel):>14.2f}")
    top_unrelated = max(all_unrelated)
    rec = math.ceil((top_unrelated + MARGIN) * 20 - 1e-9) / 20
    caught = sum(1 for x in all_para if x >= rec)
    print()
    print(f"highest unrelated Dice: {top_unrelated:.2f}")
    print(f"paraphrased sentences at or above the threshold: {caught}/{len(all_para)}")
    print(f"recommended dice: {rec:.2f}")
    over = sum(1 for x in unrelated_pairs if x >= rec)
    print(f"unrelated pairs over threshold: {over}")
    print(f"Config default: {cfg.dice:.2f} ({'matches' if abs(cfg.dice - rec) < 1e-9 else 'DIFFERS from'} the recommendation)")
    print("note: a small corpus gives a starting point, not a guarantee; tune with --dice")
    return 0 if abs(cfg.dice - rec) < 1e-9 and over == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
