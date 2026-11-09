"""CSV (Excel-friendly UTF-8 BOM) and JSON exports."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..normalize import to_display_span
from ..score import Report

CSV_COLUMNS = ["left", "right", "verbatim_lr", "verbatim_rl", "para_sentences", "score_lr", "score_rl"]


def write_csv(report: Report, path: Path) -> None:
    """One row per document pair, ratios between 0 and 1. ``utf-8-sig`` adds the BOM Excel needs."""
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for p in report.pairs:
            w.writerow([
                p.left, p.right, f"{p.verbatim_lr:.4f}", f"{p.verbatim_rl:.4f}",
                p.para_sentences, f"{p.score_lr:.4f}", f"{p.score_rl:.4f}",
            ])


def write_json(report: Report, path: Path) -> None:
    """Full result including matched spans (indexes into each document's NFKC text)."""
    cfg = report.config
    data = {
        "config": {"k": cfg.k, "w": cfg.w, "min_match": cfg.min_match, "dice": cfg.dice,
                   "min_sentence": cfg.min_sentence, "group_ratio": cfg.group_ratio},
        "stats": report.stats,
        "failures": [{"name": f.name, "reason": f.reason} for f in report.failures],
        "pairs": [],
    }
    for p in report.pairs:
        left, right = report.docs[p.left], report.docs[p.right]
        data["pairs"].append({
            **{c: getattr(p, c) for c in CSV_COLUMNS},
            "verbatim_spans_left": [to_display_span(left.norm.offsets, s, e) for s, e in p.verbatim_left],
            "verbatim_spans_right": [to_display_span(right.norm.offsets, s, e) for s, e in p.verbatim_right],
            "paraphrase": [
                {"dice": m.dice, "left": to_display_span(left.norm.offsets, *m.left),
                 "right": to_display_span(right.norm.offsets, *m.right)}
                for m in p.para
            ],
        })
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
