"""Shared test helpers: deterministic random Korean-looking text, example loader."""
from __future__ import annotations

import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "heat-island"

SYLLABLES = [chr(c) for c in range(0xAC00, 0xAC00 + 11172, 37)][:300]


def rand_text(rng: random.Random, n: int) -> str:
    """``n`` random Hangul syllables (collisions between texts are astronomically unlikely)."""
    return "".join(rng.choice(SYLLABLES) for _ in range(n))


def load_example() -> tuple[dict[str, str], str]:
    texts = {p.name: p.read_text(encoding="utf-8") for p in sorted(EXAMPLE.glob("[a-d]_*.txt"))}
    return texts, (EXAMPLE / "prompt.txt").read_text(encoding="utf-8")


def find_pair(report, a: str, b: str):
    for p in report.pairs:
        if {p.left, p.right} == {a, b}:
            return p
    raise AssertionError(f"pair {a} ~ {b} not found")
