# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.3] - 2026-11-12

### Added
- `scan` summary (console, `index.html`, `pairs.json` stats) now shows how much was excluded as group-common: `common_fingerprints`, `common_documents`, `common_threshold_docs`. Passages from the `--prompt` task text are masked separately and not counted. Scores and candidates are unchanged; the console line appears only when something was excluded.

## [0.1.2] - 2026-11-10

### Fixed
- `scan` now reports binary `.hwp` files as `FAILED` rows (same hint as `extract`) instead of silently dropping them; they also appear in `pairs.json` and `index.html`.

### Added
- `scan` prints one stderr line with the number of files skipped for other unsupported extensions.

## [0.1.1]

### Changed
- README "compare with other tools" table replaced by a short "when to use" section.

## [0.1.0]

### Added
- `scan`, `pair` and `extract` commands.
- Verbatim layer: 8-character k-gram winnowing (w=4), inverted index, character-level match extension.
- Prompt masking by character span and exclusion of passages shared by many documents.
- Paraphrase layer: sentence character-bigram Dice with a rare-bigram prefix filter; default threshold calibrated by `scripts/calibrate.py`.
- Text extraction for txt (UTF-8/CP949), docx, hwpx and pdf in a killable worker process with time and size limits.
- Static HTML report (opens from disk), CSV (UTF-8 BOM) and JSON output.
- `scripts/bench.py` scale check.
