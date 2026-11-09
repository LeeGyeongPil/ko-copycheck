"""AC-8: static HTML without external resources, CSV with BOM and fixed columns."""
import json
import re
from pathlib import Path

from helpers import load_example
from ko_copycheck import compare
from ko_copycheck.report import CSV_COLUMNS, write_csv, write_json, write_report
from ko_copycheck.score import Failure


def _report():
    texts, prompt = load_example()
    return compare(texts, [prompt], failures=[Failure("broken.pdf", "timeout: no result after 60s (worker killed)")])


def test_static_html_no_external(tmp_path):
    report = _report()
    index = write_report(report, tmp_path)
    pages = [index, *sorted((tmp_path / "pairs").glob("*.html"))]
    assert len(pages) >= 3
    joined = ""
    for page in pages:
        text = page.read_text(encoding="utf-8")
        joined += text
        assert not re.search(r'(?:src|href)\s*=\s*"\s*(?:https?:)?//', text)
        assert "http://" not in text and "https://" not in text
    assert '<script type="application/json"' in index.read_text(encoding="utf-8")
    assert '<mark class="v"' in joined and '<mark class="p"' in joined and '<mark class="g"' in joined
    data = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', index.read_text(encoding="utf-8"), re.S)
    assert json.loads(data.group(1))["stats"]["documents"] == 4
    assert "추출 실패" in index.read_text(encoding="utf-8")


def test_html_escapes_document_text(tmp_path):
    report = compare({"a.txt": "<script>alert(1)</script> " * 6, "b.txt": "<script>alert(1)</script> " * 6})
    write_report(report, tmp_path)
    page = (tmp_path / "pairs" / "0001.html").read_text(encoding="utf-8")
    assert "<script>alert" not in page


def test_csv_json_schema(tmp_path):
    report = _report()
    csv_path, json_path = tmp_path / "pairs.csv", tmp_path / "pairs.json"
    write_csv(report, csv_path)
    write_json(report, json_path)
    raw = csv_path.read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf"
    header = raw[3:].decode("utf-8").splitlines()[0]
    assert header.split(",") == ["left", "right", "verbatim_lr", "verbatim_rl", "para_sentences", "score_lr", "score_rl"] == CSV_COLUMNS
    assert len(raw.decode("utf-8-sig").splitlines()) == 1 + 6
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert len(data["pairs"]) == 6 and data["failures"][0]["name"] == "broken.pdf"
    assert data["pairs"][0]["verbatim_spans_left"]
