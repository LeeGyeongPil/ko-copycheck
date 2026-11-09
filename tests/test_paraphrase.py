"""AC-4: Dice layer and the prefix filter."""
import random

from helpers import find_pair, load_example, rand_text
from ko_copycheck import Config, compare
from ko_copycheck.paraphrase import Sentence, bigram_set, matches_bruteforce, matches_prefix, split_sentences


def _mutate(rng: random.Random, s: str, rate: float) -> str:
    return "".join(rand_text(rng, 1) if rng.random() < rate else ch for ch in s)


def test_prefix_filter_equals_bruteforce():
    rng = random.Random(5)
    base = [rand_text(rng, rng.randint(10, 40)) for _ in range(40)]
    sents = []
    for doc in range(8):
        for s in base:
            if rng.random() < 0.5:  # each document reuses some sentences with random edits
                sents.append(Sentence(doc, (0, len(s)), bigram_set(_mutate(rng, s, rng.choice([0.0, 0.1, 0.25, 0.5])))))
        for _ in range(5):
            sents.append(Sentence(doc, (0, 20), bigram_set(rand_text(rng, rng.randint(10, 40)))))
    for t in (0.2, 0.3, 0.5, 0.7, 0.9):
        expected = matches_bruteforce(sents, t)
        got, compared = matches_prefix(sents, t)
        assert got == expected, f"t={t}"
        if t >= 0.5:
            assert expected  # the test must actually exercise matches
    assert compared < len(sents) * (len(sents) - 1) // 2


def test_example_paraphrase_detected():
    texts, prompt = load_example()
    report = compare(texts, [prompt])
    assert find_pair(report, "a_original.txt", "c_paraphrase.txt").para_sentences >= 2
    for other in ("a_original.txt", "c_paraphrase.txt"):
        d = find_pair(report, other, "d_unrelated.txt")
        assert d.para_sentences == 0 and d.score_lr == 0.0 and d.score_rl == 0.0


def test_sentence_splitting_merges_short_fragments():
    text = "첫 문장은 충분히 길게 쓰여 있다. 짧은\n줄은 다음 줄과 합쳐진다 그래서 하나가 된다.\n끝."
    spans = split_sentences(text, 10)
    pieces = [text[s:e] for s, e in spans]
    assert pieces[0].startswith("첫 문장")
    assert any("짧은\n줄은" in p for p in pieces)
    assert all(not p.strip() == "끝." for p in pieces)
