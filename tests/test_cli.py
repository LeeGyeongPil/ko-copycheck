"""AC-9 and scan behaviour through the real command line entry point."""
import shutil

from fixtures.make_fixtures import make_docx, make_hwpx
from helpers import EXAMPLE
from ko_copycheck.cli import main

S1 = "도시 열섬 현상은 도심의 기온이 주변보다 높게 나타나는 현상이다."


def test_pair_and_extract(tmp_path, capsys):
    hwpx = make_hwpx(tmp_path / "file.hwpx", [[S1]])
    docx = make_docx(tmp_path / "other.docx", [S1])
    out = tmp_path / "x.html"
    assert main(["pair", str(hwpx), str(docx), "--out", str(out)]) == 0
    assert out.is_file() and '<mark class="v"' in out.read_text(encoding="utf-8")
    capsys.readouterr()
    assert main(["extract", str(hwpx)]) == 0
    assert S1 in capsys.readouterr().out


def test_scan_example_and_failure_row(tmp_path, capsys):
    folder = tmp_path / "subs"
    shutil.copytree(EXAMPLE, folder)
    (folder / "broken.docx").write_bytes(b"not a zip")
    out = tmp_path / "report"
    assert main(["scan", str(folder), "--prompt", str(folder / "prompt.txt"), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "a_original.txt ~ b_copy.txt" in text and "FAILED broken.docx" in text
    assert (out / "index.html").is_file() and (out / "pairs.csv").is_file()
    assert "추출 실패" in (out / "index.html").read_text(encoding="utf-8")


def test_scan_needs_two_files(tmp_path, capsys):
    (tmp_path / "only.txt").write_text(S1, encoding="utf-8")
    assert main(["scan", str(tmp_path), "--out", str(tmp_path / "r")]) == 2
    assert "at least 2 files" in capsys.readouterr().err


def test_bad_option_has_fix_hint(tmp_path, capsys):
    (tmp_path / "a.txt").write_text(S1, encoding="utf-8")
    (tmp_path / "b.txt").write_text(S1, encoding="utf-8")
    assert main(["scan", str(tmp_path), "--dice", "2", "--out", str(tmp_path / "r")]) == 2
    assert "try --dice" in capsys.readouterr().err


def test_empty_file_is_reported_as_failure(tmp_path, capsys):
    (tmp_path / "a.txt").write_text(S1 * 3, encoding="utf-8")
    (tmp_path / "b.txt").write_text(S1 * 3, encoding="utf-8")
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    assert main(["scan", str(tmp_path), "--out", str(tmp_path / "r")]) == 0
    assert "no_text" in (tmp_path / "r" / "pairs.json").read_text(encoding="utf-8")


def test_dice_hint_matches_default_and_exit_codes(tmp_path, capsys):
    assert main(["pair", "a", "b", "--dice", "2"]) == 2
    assert "try --dice 0.3" in capsys.readouterr().err
    assert main(["extract", str(tmp_path / "missing.txt")]) == 2


def _hwp_folder(tmp_path):
    folder = tmp_path / "subs"
    shutil.copytree(EXAMPLE, folder)
    (folder / "c_student.hwp").write_bytes(b"\xd0\xcf\x11\xe0fake")
    return folder


def test_scan_reports_hwp_as_failed_row(tmp_path, capsys):
    folder = _hwp_folder(tmp_path)
    out = tmp_path / "report"
    assert main(["scan", str(folder), "--prompt", str(folder / "prompt.txt"), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "FAILED c_student.hwp" in text and "save as .hwpx or .pdf" in text
    import json
    failures = json.loads((out / "pairs.json").read_text(encoding="utf-8"))["failures"]
    assert any("c_student.hwp" in json.dumps(f, ensure_ascii=False) for f in failures)
    assert "c_student.hwp" in (out / "index.html").read_text(encoding="utf-8")


def test_scan_ignores_hidden_and_temp_hwp(tmp_path, capsys):
    folder = _hwp_folder(tmp_path)
    (folder / "c_student.hwp").unlink()
    (folder / "~$c.hwp").write_bytes(b"x")
    (folder / ".c.hwp").write_bytes(b"x")
    assert main(["scan", str(folder), "--prompt", str(folder / "prompt.txt"), "--out", str(tmp_path / "r")]) == 0
    cap = capsys.readouterr()
    assert "FAILED" not in cap.out and "skipped" not in cap.err


def test_scan_notes_skipped_unsupported_files(tmp_path, capsys):
    folder = _hwp_folder(tmp_path)
    (folder / "notes.xyz").write_bytes(b"x")
    assert main(["scan", str(folder), "--prompt", str(folder / "prompt.txt"), "--out", str(tmp_path / "r")]) == 0
    cap = capsys.readouterr()
    assert "skipped 1 files with unsupported extensions (supported: .txt, .docx, .hwpx, .pdf)" in cap.err
    assert "FAILED notes.xyz" not in cap.out


def _five_docs(tmp_path):
    folder = tmp_path / "subs"
    shutil.copytree(EXAMPLE, folder)
    shutil.copy(folder / "b_copy.txt", folder / "b_copy2.txt")  # 3 of 5 share the passage -> common
    return folder


def test_scan_reports_common_excluded(tmp_path, capsys):
    folder = _five_docs(tmp_path)
    out = tmp_path / "r"
    assert main(["scan", str(folder), "--prompt", str(folder / "prompt.txt"), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "common passages excluded:" in text and "--group-ratio" in text
    import json
    stats = json.loads((out / "pairs.json").read_text(encoding="utf-8"))["stats"]
    assert stats["common_fingerprints"] > 0 and stats["common_threshold_docs"] == 3
    assert "공통 구절로 제외" in (out / "index.html").read_text(encoding="utf-8")


def test_scan_four_docs_has_no_common_line(tmp_path, capsys):
    folder = tmp_path / "subs"
    shutil.copytree(EXAMPLE, folder)
    out = tmp_path / "r"
    assert main(["scan", str(folder), "--prompt", str(folder / "prompt.txt"), "--out", str(out)]) == 0
    assert "common passages excluded" not in capsys.readouterr().out
    import json
    stats = json.loads((out / "pairs.json").read_text(encoding="utf-8"))["stats"]
    assert stats["common_fingerprints"] == 0
    assert "공통 구절로 제외" not in (out / "index.html").read_text(encoding="utf-8")
