"""ko-copycheck: offline plagiarism checker for Korean prose.

Public API: :func:`compare`, :class:`Config`, :class:`Report`. Everything else is
internal and may change.
"""
from .engine import compare
from .config import Config
from .score import Report

__version__ = "0.1.0"
__all__ = ["compare", "Config", "Report", "__version__"]
