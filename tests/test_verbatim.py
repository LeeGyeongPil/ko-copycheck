"""AC-3: prompt masking by character span, group-common pieces excluded."""
import random

from helpers import find_pair, rand_text
from ko_copycheck import Config, compare


def test_prompt_edge_masked():
    rng = random.Random(7)
    prompt = rand_text(rng, 40)
    edge_before, edge_after = rand_text(rng, 3), rand_text(rng, 3)
    # Both documents quote the prompt AND share 3 characters on each side of it, so the
    # k-grams straddling the prompt edge are identical: a 46 character raw match.
    docs = {
        n: rand_text(rng, 60) + edge_before + prompt + edge_after + rand_text(rng, 60)
        for n in ("a.txt", "b.txt")
    }
    cfg = Config(dice=0.95)
    unmasked = find_pair(compare(docs, [], cfg), "a.txt", "b.txt")
    assert unmasked.verbatim_lr > 0  # without the prompt the quote looks like copying
    masked = find_pair(compare(docs, [prompt], cfg), "a.txt", "b.txt")
    assert masked.verbatim_lr == 0.0 and masked.verbatim_rl == 0.0
    assert masked.score_lr == 0.0 and masked.score_rl == 0.0


def test_group_common_excluded():
    rng = random.Random(11)
    shared = rand_text(rng, 30)
    docs = {}
    for i in range(5):
        body = rand_text(rng, 100)
        if i < 3:  # 3 of 5 documents share the 30 character piece
            at = rng.randint(10, 80)
            body = body[:at] + shared + body[at:]
        docs[f"d{i}.txt"] = body
    cfg = Config(dice=0.95)
    report = compare(docs, [], cfg)
    for a, b in (("d0.txt", "d1.txt"), ("d0.txt", "d2.txt"), ("d1.txt", "d2.txt")):
        assert find_pair(report, a, b).verbatim_lr == 0.0
    # control: with only two documents the same piece is a real match
    two = find_pair(compare({k: docs[k] for k in ("d0.txt", "d1.txt")}, [], cfg), "d0.txt", "d1.txt")
    assert two.verbatim_lr > 0.1


def test_two_student_copy_is_not_common():
    rng = random.Random(3)
    piece = rand_text(rng, 40)
    docs = {f"d{i}.txt": rand_text(rng, 100) for i in range(6)}
    docs["d0.txt"] += piece
    docs["d1.txt"] += piece
    report = compare(docs, [], Config(dice=0.95))
    assert find_pair(report, "d0.txt", "d1.txt").verbatim_lr > 0.2
