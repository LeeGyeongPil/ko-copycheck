"""Tunable settings. Defaults are documented in the README option table."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """All knobs of a comparison run.

    ``dice`` default comes from ``scripts/calibrate.py`` (hand-written calibration
    corpus); it is a starting point, not a verdict. Tune it with ``--dice``.
    """

    k: int = 8  # characters per k-gram
    w: int = 4  # winnowing window (guarantee threshold = w + k - 1 characters)
    min_match: int = 20  # shortest verbatim match (normalized characters) that counts
    dice: float = 0.30  # sentence bigram Dice threshold for the paraphrase layer
    min_sentence: int = 10  # shortest sentence (normalized characters) for the paraphrase layer
    group_ratio: float = 0.5  # k-grams shared by this share of documents are "common"...
    group_min_docs: int = 3  # ...but only when at least this many documents share them
    covered_skip: float = 0.8  # skip paraphrase pairs whose sentence is already this covered by verbatim
    max_postings: int = 200  # ignore k-grams occurring more often than this in the index
    timeout: float = 60.0  # seconds per file for extraction

    def validate(self) -> None:
        """Raise ``ValueError`` with a fix hint for settings that cannot work."""
        if self.k < 3:
            raise ValueError(f"k must be >= 3 (got {self.k}); try --k 8")
        if self.w < 1:
            raise ValueError(f"w must be >= 1 (got {self.w}); try --w 4")
        if self.min_match < self.w + self.k - 1:
            raise ValueError(
                f"min_match ({self.min_match}) must be >= w + k - 1 ({self.w + self.k - 1}); "
                "shorter matches are not guaranteed to be found. Try --min-match 20"
            )
        if not 0.0 < self.dice <= 1.0:
            raise ValueError(f"dice must be in (0, 1] (got {self.dice}); try --dice {type(self).dice}")
        if not 0.0 < self.group_ratio <= 1.0:
            raise ValueError(f"group_ratio must be in (0, 1] (got {self.group_ratio})")
        if self.min_sentence < 2:
            raise ValueError(f"min_sentence must be >= 2 (got {self.min_sentence})")
        if self.timeout <= 0:
            raise ValueError(f"timeout must be > 0 seconds (got {self.timeout})")
