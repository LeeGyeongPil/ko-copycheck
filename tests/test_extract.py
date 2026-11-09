"""AC-6 (formats) and AC-7 (timeout kill, size limits)."""
import time

import pytest

from fixtures.make_fixtures import make_docx, make_hwpx, make_pdf, make_zip_bomb
from ko_copycheck.extract import ExtractError, Limits, SandboxedExtractor, extract_file

S1 = "도시 열섬 현상은 도심의 기온이 높게 나타나는 현상이다."
S2 = "아스팔트는 낮 동안 열을 흡수했다가 밤에 방출한다."


def test_formats_roundtrip(tmp_path):
    (tmp_path / "utf8.txt").write_text(S1, encoding="utf-8")
    (tmp_path / "cp949.txt").write_bytes(S1.encode("cp949"))
    make_docx(tmp_path / "x.docx", [S1, S2])
    # spine lists section1 first: reading order must follow the spine, not file names
    make_hwpx(tmp_path / "x.hwpx", [[S1], [S2]], spine_order=[1, 0])
    make_pdf(tmp_path / "x.pdf", "Urban heat island effect is a measured fact")
    with SandboxedExtractor(timeout=30) as ex:
        assert S1 in ex.extract(tmp_path / "utf8.txt").text
        assert S1 in ex.extract(tmp_path / "cp949.txt").text
        docx = ex.extract(tmp_path / "x.docx").text
        assert S1 in docx and S2 in docx
        hwpx = ex.extract(tmp_path / "x.hwpx").text
        assert hwpx.index(S2) < hwpx.index(S1)
        assert "heat island" in ex.extract(tmp_path / "x.pdf").text


def test_hwpx_without_spine_uses_section_numbers(tmp_path):
    path = make_hwpx(tmp_path / "y.hwpx", [[S1], [S2]])
    import zipfile

    with zipfile.ZipFile(path) as zf:
        members = {n: zf.read(n) for n in zf.namelist() if n != "Contents/content.hpf"}
    with zipfile.ZipFile(path, "w") as zf:
        for n, data in members.items():
            zf.writestr(n, data)
    text = extract_file(str(path))
    assert text.index(S1) < text.index(S2)


def test_unsupported_and_corrupt(tmp_path):
    (tmp_path / "a.hwp").write_bytes(b"x")
    with pytest.raises(ExtractError) as e:
        extract_file(str(tmp_path / "a.hwp"))
    assert e.value.code == "unsupported" and ".hwpx" in str(e.value)
    (tmp_path / "bad.docx").write_bytes(b"not a zip")
    with pytest.raises(ExtractError) as e:
        extract_file(str(tmp_path / "bad.docx"))
    assert e.value.code == "corrupt"


def test_timeout_kills_and_continues(tmp_path):
    (tmp_path / "hang.txt").write_text("x")
    (tmp_path / "ok.txt").write_text(S1, encoding="utf-8")
    start = time.monotonic()
    with SandboxedExtractor(timeout=1, handler="slow_handler:handler") as ex:
        first = ex.extract(tmp_path / "hang.txt")
        second = ex.extract(tmp_path / "ok.txt")
        killed = list(ex.retired_exitcodes)
    elapsed = time.monotonic() - start
    assert not first.ok and first.error.startswith("timeout")
    assert second.ok and second.text == S1
    assert killed and killed[0] < 0  # the stuck worker was killed by a signal
    assert elapsed < 5


def test_size_limits(tmp_path):
    bomb = make_zip_bomb(tmp_path / "bomb.docx", 5 * 1024 * 1024)
    assert bomb.stat().st_size < 100_000  # small on disk, 5 MB when unpacked
    limits = Limits(max_unzipped_bytes=1024 * 1024)
    with pytest.raises(ExtractError) as e:
        extract_file(str(bomb), limits)
    assert e.value.code == "too_large"
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * 2048)
    with SandboxedExtractor(timeout=30, limits=Limits(max_file_bytes=1024, max_unzipped_bytes=1024 * 1024)) as ex:
        assert ex.extract(big).error.startswith("too_large")
        res = ex.extract(bomb)
        assert res.error.startswith("too_large")
        (tmp_path / "ok.txt").write_text(S1, encoding="utf-8")
        assert ex.extract(tmp_path / "ok.txt").ok  # worker keeps going after a rejected file


def test_worker_recycled_after_n_files(tmp_path):
    (tmp_path / "ok.txt").write_text(S1, encoding="utf-8")
    with SandboxedExtractor(timeout=30, recycle_after=2) as ex:
        for _ in range(3):
            assert ex.extract(tmp_path / "ok.txt").ok
        assert len(ex.retired_exitcodes) == 1  # first worker retired after 2 files


def test_invalid_timeout():
    with pytest.raises(ValueError, match="timeout"):
        SandboxedExtractor(timeout=0)
