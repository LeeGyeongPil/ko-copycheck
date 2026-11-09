"""Extractor stand-in for tests: hangs on files named hang*, reads everything else as text."""
import time
from pathlib import Path


def handler(path, limits):
    if Path(path).name.startswith("hang"):
        time.sleep(3600)
    return Path(path).read_text(encoding="utf-8")
