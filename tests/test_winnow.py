"""AC-1: winnowing definition, guarantee threshold, stable hashing."""
import random
import subprocess
import sys

from helpers import rand_text
from ko_copycheck.winnow import fingerprints, kgram_hashes, stable_hash, winnow


def test_window_minimum_rightmost_no_duplicates():
    # windows of 3: [3,1,1] -> idx2, [1,1,2] -> idx2 (already recorded), [1,2,1] -> idx4
    assert winnow([3, 1, 1, 2, 1], 3) == [(1, 2), (1, 4)]


def test_short_input_is_one_window():
    assert winnow([9, 4], 4) == [(4, 1)]
    assert winnow([], 4) == []


def test_guarantee_threshold():
    k, w = 8, 4
    for seed in range(500):
        rng = random.Random(seed)
        common = rand_text(rng, rng.randint(w + k - 1, 45))  # at least 11 characters
        a = rand_text(rng, rng.randint(0, 40)) + common + rand_text(rng, rng.randint(0, 40))
        b = rand_text(rng, rng.randint(0, 40)) + common + rand_text(rng, rng.randint(0, 40))
        shared = {h for h, _ in fingerprints(a, k, w)} & {h for h, _ in fingerprints(b, k, w)}
        assert shared, f"seed {seed}: common piece of {len(common)} chars left no common fingerprint"


def test_stable_hash_across_processes():
    grams = ["도시열섬현상", "abc가나다", "열섬 현상"]
    code = "import sys; from ko_copycheck.winnow import stable_hash; print([stable_hash(g) for g in sys.argv[1:]])"
    outputs = set()
    for hashseed in ("1", "2"):
        res = subprocess.run(
            [sys.executable, "-c", code, *grams], capture_output=True, text=True, env={"PYTHONHASHSEED": hashseed, "PATH": ""}, check=True
        )
        outputs.add(res.stdout.strip())
    assert outputs == {str([stable_hash(g) for g in grams])}


def test_kgram_hashes_count():
    assert len(kgram_hashes("abcdefghij", 8)) == 3
    assert kgram_hashes("abc", 8) == []
