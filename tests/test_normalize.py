"""AC-6 (normalization part): NFD Hangul equals NFC, offsets map back."""
import unicodedata

from helpers import find_pair, load_example
from ko_copycheck import compare
from ko_copycheck.normalize import normalize, to_display_span


def test_nfd_equals_nfc():
    texts, _ = load_example()
    nfc = texts["a_original.txt"]
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc
    report = compare({"nfc.txt": nfc, "nfd.txt": nfd})
    pair = find_pair(report, "nfc.txt", "nfd.txt")
    assert pair.verbatim_lr == 1.0 and pair.verbatim_rl == 1.0


def test_offsets_point_at_source_characters():
    n = normalize("열섬, 현상! ABC 123")
    assert n.text == "열섬현상abc123"
    start, end = to_display_span(n.offsets, 0, 4)
    assert n.display[start:end] == "열섬, 현상"


def test_punctuation_and_case_ignored():
    assert normalize("Hello,   WORLD!").text == "helloworld"
