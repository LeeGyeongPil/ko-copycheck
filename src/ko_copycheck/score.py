"""Result data classes and the score definition.

score(left <- right) = characters of left covered by (verbatim spans U paraphrase
sentence spans against right) / (normalized length of left - prompt-masked characters).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .normalize import Normalized
from .verbatim import Span, covered, merge_spans


@dataclass
class Doc:
    """A compared document."""

    name: str
    norm: Normalized
    mask: list[Span]  # prompt-masked spans, normalized coordinates
    sentences: list[Span]  # sentence spans, normalized coordinates (>= min_sentence chars)

    @property
    def scored_length(self) -> int:
        """Characters that can count toward a score (prompt text excluded)."""
        return max(0, len(self.norm.text) - covered(self.mask))


@dataclass
class ParaMatch:
    """One matched sentence pair of the paraphrase layer (normalized coordinates)."""

    left: Span
    right: Span
    dice: float


@dataclass
class PairResult:
    """Comparison result of two documents. ``*_lr`` means left explained by right."""

    left: str
    right: str
    verbatim_lr: float = 0.0
    verbatim_rl: float = 0.0
    para_sentences: int = 0
    score_lr: float = 0.0
    score_rl: float = 0.0
    verbatim_left: list[Span] = field(default_factory=list)
    verbatim_right: list[Span] = field(default_factory=list)
    para: list[ParaMatch] = field(default_factory=list)

    @property
    def rank_key(self) -> float:
        """Sort key: the larger of the two directional scores."""
        return max(self.score_lr, self.score_rl)


@dataclass
class Failure:
    """A file that could not be read."""

    name: str
    reason: str


@dataclass
class Report:
    """Everything a comparison run produced."""

    docs: dict[str, Doc]
    pairs: list[PairResult]
    failures: list[Failure]
    config: Config
    stats: dict[str, Any]
    prompts: list[str] = field(default_factory=list)


def ratio(spans: list[Span], doc: Doc) -> float:
    """Covered share of a document's scoreable text."""
    if doc.scored_length == 0:
        return 0.0
    return min(1.0, covered(spans) / doc.scored_length)


def finalize(left: Doc, right: Doc, vl: list[Span], vr: list[Span], para: list[ParaMatch]) -> PairResult:
    """Build a :class:`PairResult` from the two layers."""
    pl = [m.left for m in para]
    pr = [m.right for m in para]
    return PairResult(
        left=left.name,
        right=right.name,
        verbatim_lr=ratio(vl, left),
        verbatim_rl=ratio(vr, right),
        para_sentences=len(para),
        score_lr=ratio(merge_spans(vl + pl), left),
        score_rl=ratio(merge_spans(vr + pr), right),
        verbatim_left=vl,
        verbatim_right=vr,
        para=para,
    )
