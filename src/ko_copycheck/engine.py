"""Public entry point: compare a set of texts against each other."""
from __future__ import annotations

import time
from collections import defaultdict
from itertools import combinations
from typing import Mapping, Sequence

from .config import Config
from .index import candidate_hits, document_frequency
from .normalize import from_display_span, normalize
from .paraphrase import Sentence, bigram_set, matches_prefix, split_sentences
from .score import Doc, Failure, PairResult, ParaMatch, Report, finalize
from .verbatim import Span, covered, merge_spans, pair_spans, prompt_mask
from .winnow import kgram_hashes, winnow


def _overlap_share(span: Span, others: list[Span]) -> float:
    """Share of ``span`` covered by the (merged, sorted) ``others``."""
    s, e = span
    if e <= s:
        return 0.0
    hit = sum(max(0, min(e, oe) - max(s, os)) for os, oe in others)
    return hit / (e - s)


def compare(
    texts: Mapping[str, str],
    prompts: Sequence[str] = (),
    config: Config | None = None,
    failures: Sequence[Failure] = (),
) -> Report:
    """Compare every pair of ``texts`` (name -> text) and return a :class:`Report`.

    ``prompts`` are the assignment texts every submission may quote; matching parts are
    masked and never count. No network is used.
    """
    cfg = config or Config()
    cfg.validate()
    t0 = time.perf_counter()
    names = sorted(texts)
    norms = [normalize(texts[n]) for n in names]
    prompt_norms = [normalize(p).text for p in prompts]
    prompt_norms = [p for p in prompt_norms if len(p) >= cfg.k]

    hash_lists = [kgram_hashes(n.text, cfg.k) for n in norms]
    fps = [winnow(h, cfg.w) for h in hash_lists]
    prompt_fps = [winnow(kgram_hashes(p, cfg.k), cfg.w) for p in prompt_norms]
    df = document_frequency(hash_lists)
    del hash_lists

    docs: list[Doc] = []
    for name, norm, doc_fps in zip(names, norms, fps):
        mask = prompt_mask(norm.text, doc_fps, prompt_norms, prompt_fps, cfg.k)
        sent_spans = [
            from_display_span(norm.offsets, s, e) for s, e in split_sentences(norm.display, cfg.min_sentence)
        ]
        docs.append(Doc(name, norm, mask, sent_spans))

    # Layer 1: verbatim matches only for pairs that share a (non-common) fingerprint.
    hits = candidate_hits(fps, df, cfg)
    verbatim: dict[tuple[int, int], tuple[list[Span], list[Span]]] = {}
    for (i, j), pair_hits in hits.items():
        sa, sb = pair_spans(norms[i].text, norms[j].text, pair_hits, docs[i].mask, docs[j].mask, cfg)
        if sa:
            verbatim[(i, j)] = (sa, sb)

    # Layer 2: sentence Dice over all documents with the rare-bigram prefix filter.
    sents: list[Sentence] = []
    for di, doc in enumerate(docs):
        for span in doc.sentences:
            if _overlap_share(span, doc.mask) >= 0.5:  # mostly prompt text
                continue
            grams = bigram_set(doc.norm.text[span[0] : span[1]])
            if grams:
                sents.append(Sentence(di, span, grams))
    sent_pairs, compared = matches_prefix(sents, cfg.dice)
    para_by_pair: dict[tuple[int, int], list[tuple[float, Span, Span]]] = defaultdict(list)
    for a, b in sent_pairs:
        sa, sb = sents[a], sents[b]
        if sa.doc > sb.doc:
            sa, sb = sb, sa
        d = 2 * len(sa.bigrams & sb.bigrams) / (len(sa.bigrams) + len(sb.bigrams))
        para_by_pair[(sa.doc, sb.doc)].append((d, sa.span, sb.span))

    results: dict[tuple[int, int], PairResult] = {}
    for (i, j), cand in para_by_pair.items():
        vl, vr = verbatim.get((i, j), ([], []))
        matches = _one_to_one(cand, vl, vr, cfg.covered_skip)
        results[(i, j)] = finalize(docs[i], docs[j], vl, vr, matches)
    for (i, j), (vl, vr) in verbatim.items():
        if (i, j) not in results:
            results[(i, j)] = finalize(docs[i], docs[j], vl, vr, [])
    pairs = [results.get(p) or PairResult(docs[p[0]].name, docs[p[1]].name) for p in combinations(range(len(docs)), 2)]
    pairs.sort(key=lambda p: (-p.rank_key, -(p.score_lr + p.score_rl), p.left, p.right))

    n = len(docs)
    stats = {
        "documents": n,
        "all_pairs": n * (n - 1) // 2,
        "candidate_pairs": len(results),  # pairs that reached either layer (= rows with a score)
        "verbatim_pairs": len(verbatim),
        "sentences": len(sents),
        "sentence_candidates_compared": compared,
        "elapsed_seconds": round(time.perf_counter() - t0, 3),
    }
    return Report({d.name: d for d in docs}, pairs, list(failures), cfg, stats, list(prompts))


def _one_to_one(
    cand: list[tuple[float, Span, Span]], vl: list[Span], vr: list[Span], skip: float
) -> list[ParaMatch]:
    """Greedy one-to-one sentence matching, best Dice first.

    Pairs whose sentence is already mostly explained by a verbatim match are skipped:
    that text is reported by layer 1.
    """
    ml, mr = merge_spans(vl), merge_spans(vr)
    used_l: set[Span] = set()
    used_r: set[Span] = set()
    out: list[ParaMatch] = []
    for d, sl, sr in sorted(cand, key=lambda c: (-c[0], c[1], c[2])):
        if sl in used_l or sr in used_r:
            continue
        if _overlap_share(sl, ml) >= skip or _overlap_share(sr, mr) >= skip:
            continue
        used_l.add(sl)
        used_r.add(sr)
        out.append(ParaMatch(sl, sr, round(d, 4)))
    out.sort(key=lambda m: m.left)
    return out
