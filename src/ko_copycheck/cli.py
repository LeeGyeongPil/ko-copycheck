"""Command line interface: scan, pair, extract."""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

from . import __version__
from .config import Config
from .engine import compare
from .extract import SUPPORTED, Limits, SandboxedExtractor
from .report import write_csv, write_json, write_report
from .report.html import pair_page
from .normalize import normalize_text
from .score import Failure, Report

EXIT_OK, EXIT_ERROR = 0, 2


def _add_tuning(p: argparse.ArgumentParser) -> None:
    d = Config()
    p.add_argument("--prompt", action="append", default=[], metavar="FILE",
                   help="assignment text every submission may quote (repeatable); matching parts are ignored")
    p.add_argument("--k", type=int, default=d.k, help=f"k-gram length in characters (default {d.k})")
    p.add_argument("--w", type=int, default=d.w, help=f"winnowing window (default {d.w})")
    p.add_argument("--min-match", type=int, default=d.min_match, help=f"shortest verbatim match in characters (default {d.min_match})")
    p.add_argument("--dice", type=float, default=d.dice, help=f"paraphrase Dice threshold (default {d.dice})")
    p.add_argument("--min-sentence", type=int, default=d.min_sentence, help=f"shortest sentence for paraphrase layer (default {d.min_sentence})")
    p.add_argument("--group-ratio", type=float, default=d.group_ratio, help=f"share of documents that makes a passage common (default {d.group_ratio})")
    p.add_argument("--timeout", type=float, default=d.timeout, help=f"seconds allowed per file extraction (default {d.timeout:g})")


def _config(a: argparse.Namespace) -> Config:
    return Config(k=a.k, w=a.w, min_match=a.min_match, dice=a.dice, min_sentence=a.min_sentence,
                  group_ratio=a.group_ratio, timeout=a.timeout)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ko-copycheck",
        description="Offline plagiarism checker for Korean prose submissions. Compares files with each other only; nothing is uploaded.",
    )
    ap.add_argument("--version", action="version", version=f"ko-copycheck {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="compare every pair of files in a folder")
    scan.add_argument("folder", type=Path)
    scan.add_argument("--out", type=Path, default=Path("report"), help="output folder (default ./report)")
    scan.add_argument("--recursive", action="store_true", help="also read sub-folders")
    scan.add_argument("--top", type=int, default=300, help="write side-by-side pages for at most this many pairs (default 300)")
    _add_tuning(scan)

    pair = sub.add_parser("pair", help="compare two files and write one side-by-side HTML page")
    pair.add_argument("left", type=Path)
    pair.add_argument("right", type=Path)
    pair.add_argument("--out", type=Path, default=Path("pair.html"), help="output HTML file (default ./pair.html)")
    _add_tuning(pair)

    ex = sub.add_parser("extract", help="print the text extracted from one file (check how it is read)")
    ex.add_argument("file", type=Path)
    ex.add_argument("--timeout", type=float, default=Config().timeout, help="seconds allowed (default 60)")
    return ap


def _say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _collect(folder: Path, recursive: bool, exclude: set[Path]) -> tuple[list[Path], int]:
    """Return (files to compare, number of files skipped for an unsupported extension).

    ``.hwp`` is kept so the extractor reports it as a FAILED row with its usual hint
    instead of dropping it silently. Hidden and ``~$`` temporary files are never counted.
    """
    it = folder.rglob("*") if recursive else folder.glob("*")
    files = [p for p in it if p.is_file() and not p.name.startswith((".", "~$")) and p.resolve() not in exclude]
    keep = [p for p in files if p.suffix.lower() in SUPPORTED or p.suffix.lower() == ".hwp"]
    return sorted(keep), len(files) - len(keep)


def _extract_all(paths: list[Path], names: list[str], timeout: float, min_chars: int = 0) -> tuple[dict[str, str], list[Failure]]:
    texts: dict[str, str] = {}
    failures: list[Failure] = []
    with SandboxedExtractor(timeout=timeout) as ex:
        for i, (path, name) in enumerate(zip(paths, names), 1):
            res = ex.extract(path)
            if res.ok and res.text is not None and len(normalize_text(res.text)) < min_chars:
                failures.append(Failure(name, f"no_text: fewer than {min_chars} readable characters (empty file?)"))
            elif res.ok and res.text is not None:
                texts[name] = res.text
            else:
                failures.append(Failure(name, res.error or "unknown"))
            _say(f"extract {i}/{len(paths)}  failed {len(failures)}")
    return texts, failures


def _read_prompts(paths: list[str], timeout: float) -> list[str] | None:
    files = [Path(p) for p in paths]
    for f in files:
        if not f.is_file():
            _say(f"error: prompt file not found: {f}")
            return None
    if not files:
        return []
    texts, failures = _extract_all(files, [f.name for f in files], timeout)
    if failures:
        _say(f"error: cannot read prompt {failures[0].name}: {failures[0].reason}")
        return None
    return list(texts.values())


def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s: str, n: int) -> str:
    return s + " " * max(0, n - _width(s))


def print_top(report: Report, n: int = 10) -> None:
    """Terminal ranking of the most similar pairs."""
    rows = [p for p in report.pairs if p.rank_key > 0][:n]
    if not rows:
        print("no overlapping pairs found")
        return
    label = [f"{p.left} ~ {p.right}" for p in rows]
    wid = max(_width(x) for x in label)
    print(f"{_pad('pair', wid)}  verbatim L<-R / R<-L   paraphrase  total L<-R / R<-L")
    for text, p in zip(label, rows):
        print(f"{_pad(text, wid)}  {p.verbatim_lr * 100:5.1f}% / {p.verbatim_rl * 100:5.1f}%      "
              f"{p.para_sentences:6d}      {p.score_lr * 100:5.1f}% / {p.score_rl * 100:5.1f}%")


def cmd_scan(a: argparse.Namespace) -> int:
    cfg = _config(a)
    cfg.validate()
    if not a.folder.is_dir():
        _say(f"error: not a folder: {a.folder}. Pass the folder that holds the submissions.")
        return EXIT_ERROR
    prompts = _read_prompts(a.prompt, cfg.timeout)
    if prompts is None:
        return EXIT_ERROR
    exclude = {Path(p).resolve() for p in a.prompt}
    paths, skipped = _collect(a.folder, a.recursive, exclude)
    if skipped:
        _say(f"skipped {skipped} files with unsupported extensions (supported: {', '.join(SUPPORTED)})")
    names = [p.relative_to(a.folder).as_posix() for p in paths]
    if len(paths) < 2:
        _say(f"error: need at least 2 files ({', '.join(SUPPORTED)}) in {a.folder}, found {len(paths)}. Try --recursive.")
        return EXIT_ERROR
    texts, failures = _extract_all(paths, names, cfg.timeout, cfg.k)
    if len(texts) < 2:
        _say("error: fewer than 2 files could be read; see the failure reasons above (run 'extract' on one file).")
        for f in failures:
            _say(f"  {f.name}: {f.reason}")
        return EXIT_ERROR
    report = compare(texts, prompts, cfg, failures)
    a.out.mkdir(parents=True, exist_ok=True)
    write_csv(report, a.out / "pairs.csv")
    write_json(report, a.out / "pairs.json")
    index = write_report(report, a.out, top=a.top)
    print_top(report)
    for f in failures:
        print(f"FAILED {f.name}: {f.reason}")
    s = report.stats
    print(f"\n{s['documents']} documents, {s['candidate_pairs']} candidate pairs of {s['all_pairs']}, {s['elapsed_seconds']}s")
    print(f"report: {index}")
    return EXIT_OK


def cmd_pair(a: argparse.Namespace) -> int:
    cfg = _config(a)
    cfg.validate()
    for f in (a.left, a.right):
        if not f.is_file():
            _say(f"error: file not found: {f}")
            return EXIT_ERROR
    prompts = _read_prompts(a.prompt, cfg.timeout)
    if prompts is None:
        return EXIT_ERROR
    left_name, right_name = a.left.name, a.right.name
    if left_name == right_name:
        left_name, right_name = str(a.left), str(a.right)
    texts, failures = _extract_all([a.left, a.right], [left_name, right_name], cfg.timeout, cfg.k)
    if failures:
        for f in failures:
            _say(f"error: cannot read {f.name}: {f.reason}")
        return EXIT_ERROR
    report = compare(texts, prompts, cfg)
    result = report.pairs[0]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(pair_page(report, result), encoding="utf-8")
    print(f"{result.left} ~ {result.right}: verbatim {result.verbatim_lr * 100:.1f}% / {result.verbatim_rl * 100:.1f}%, "
          f"paraphrase sentences {result.para_sentences}")
    print(f"page: {a.out}")
    return EXIT_OK


def cmd_extract(a: argparse.Namespace) -> int:
    if not a.file.is_file():
        _say(f"error: file not found: {a.file}")
        return EXIT_ERROR
    with SandboxedExtractor(timeout=a.timeout, limits=Limits()) as ex:
        res = ex.extract(a.file)
    if not res.ok or res.text is None:
        _say(f"error: {res.error}")
        return EXIT_ERROR
    sys.stdout.write(res.text if res.text.endswith("\n") else res.text + "\n")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            return cmd_scan(args)
        if args.command == "pair":
            return cmd_pair(args)
        return cmd_extract(args)
    except ValueError as exc:
        _say(f"error: {exc}")
        return EXIT_ERROR
    except KeyboardInterrupt:
        _say("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
