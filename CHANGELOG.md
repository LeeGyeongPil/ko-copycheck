# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
