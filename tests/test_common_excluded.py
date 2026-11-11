"""Common-passage counting: read-only, scores unchanged."""
from collections import Counter

from helpers import find_pair, load_example
from ko_copycheck import index
from ko_copycheck.config import Config
from ko_copycheck.engine import compare


def _with_copy():
    texts, prompt = load_example()
    five = dict(texts)
    five["b_copy2.txt"] = texts["b_copy.txt"]
    return texts, five, prompt


def test_four_docs_nothing_excluded_and_verbatim_kept():
    texts, _, prompt = _with_copy()
    r = compare(texts, [prompt], Config(), [])
    assert r.stats["common_fingerprints"] == 0 and r.stats["common_documents"] == 0
    assert round(find_pair(r, "a_original.txt", "b_copy.txt").verbatim_lr, 3) == 0.668


def test_five_docs_counts_and_threshold():
    _, five, prompt = _with_copy()
    r = compare(five, [prompt], Config(), [])
    assert r.stats["common_fingerprints"] > 0
    assert r.stats["common_documents"] >= 3 and r.stats["common_threshold_docs"] == 3
    assert find_pair(r, "a_original.txt", "b_copy.txt").verbatim_lr == 0.0


def test_scores_identical_without_new_keys(monkeypatch):
    """Neutralising the counter must not change any score, order or old stat."""
    _, five, prompt = _with_copy()
    with_new = compare(five, [prompt], Config(), [])
    monkeypatch.setattr("ko_copycheck.engine.common_excluded", lambda *a: (0, 0))
    without = compare(five, [prompt], Config(), [])
    key = lambda r: [(p.left, p.right, p.verbatim_lr, p.verbatim_rl, p.para_sentences, p.score_lr, p.score_rl) for p in r.pairs]
    assert key(with_new) == key(without)
    for k in ("documents", "all_pairs", "candidate_pairs", "verbatim_pairs", "sentences", "sentence_candidates_compared"):
        assert with_new.stats[k] == without.stats[k]
    assert with_new.stats["common_fingerprints"] > 0 and without.stats["common_fingerprints"] == 0


def test_helper_ignores_unshared_and_single_doc_hashes():
    cfg = Config()
    fps = [[(1, 0), (2, 1)], [(1, 0), (3, 1)], [(1, 0)]]
    df = Counter({1: 3, 2: 1, 3: 1})
    assert index.common_excluded(fps, df, cfg) == (1, 3)
    assert index.common_excluded([[(2, 0)], [(3, 0)]], Counter({2: 1, 3: 1}), cfg) == (0, 0)
