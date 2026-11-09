"""AC-5 and AC-10 smoke tests for the scripts (full-size bench runs outside pytest)."""
import calibrate
import bench

from ko_copycheck import Config


def test_calibration_matches_default(capsys):
    assert calibrate.main() == 0
    out = capsys.readouterr().out
    assert f"recommended dice: {Config().dice:.2f}" in out
    assert "unrelated pairs over threshold: 0" in out


def test_bench_candidates_stay_small():
    from ko_copycheck import compare

    docs = bench.make_corpus(60, 1500)
    report = compare(docs)
    assert report.stats["candidate_pairs"] < 0.10 * report.stats["all_pairs"]
