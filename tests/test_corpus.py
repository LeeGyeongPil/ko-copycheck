"""AC-2: ranking on the example folder."""
from helpers import find_pair, load_example
from ko_copycheck import compare


def test_example_ranking():
    texts, prompt = load_example()
    report = compare(texts, [prompt])
    top = report.pairs[0]
    assert {top.left, top.right} == {"a_original.txt", "b_copy.txt"}
    assert top.verbatim_lr >= 0.6 and top.verbatim_rl >= 0.6
    for p in report.pairs:
        if "d_unrelated.txt" in (p.left, p.right):
            assert p.verbatim_lr == 0.0 and p.verbatim_rl == 0.0 and p.para_sentences == 0
    # the paraphrase has no verbatim overlap but is still ranked above unrelated pairs
    ac = find_pair(report, "a_original.txt", "c_paraphrase.txt")
    assert ac.verbatim_lr == 0.0 and ac.score_lr > 0.1
