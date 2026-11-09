"""Static HTML report: opens from disk (file://), data embedded, no external resources."""
from __future__ import annotations

import html
import json
from pathlib import Path

from ..normalize import to_display_span
from ..score import Doc, PairResult, Report
from ..verbatim import Span, merge_spans

DISCLAIMER = "이 점수는 표절 판정이 아니라, 사람이 확인할 순서를 정해 주는 보조 지표입니다."

CSS = """
body{font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;margin:1.5rem auto;max-width:1100px;padding:0 1rem;color:#222}
h1{font-size:1.4rem} .note{background:#fff8e1;border:1px solid #f0d98c;padding:.5rem .8rem;border-radius:6px}
table{border-collapse:collapse;width:100%;margin:1rem 0} th,td{border-bottom:1px solid #ddd;padding:.35rem .5rem;text-align:left;font-size:.92rem}
th{cursor:pointer;background:#f5f5f5} td.n{text-align:right;font-variant-numeric:tabular-nums}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:1rem} .doc{white-space:pre-wrap;line-height:1.7;border:1px solid #ddd;border-radius:6px;padding:.8rem;font-size:.95rem}
mark.v{background:#ff9d9d} mark.p{background:#ffe08a} mark.g{background:#e8e8e8;color:#777;text-decoration:line-through}
.legend mark{padding:0 .4rem;margin-right:.6rem} .fail td{color:#a33} a{color:#1a56c4}
"""

SORT_JS = """
document.querySelectorAll('th[data-k]').forEach(function(th){th.addEventListener('click',function(){
var tb=th.closest('table').tBodies[0],k=th.dataset.k,rows=Array.prototype.slice.call(tb.rows);
var dir=th.dataset.dir==='desc'?1:-1;th.dataset.dir=dir===1?'asc':'desc';
rows.sort(function(a,b){var x=a.dataset[k],y=b.dataset[k],nx=parseFloat(x),ny=parseFloat(y);
var c=(isNaN(nx)||isNaN(ny))?x.localeCompare(y):nx-ny;return c*dir;});
rows.forEach(function(r){tb.appendChild(r);});});});
"""


def _json_block(data: object, element_id: str) -> str:
    """Embed JSON safely inside a <script> element (no ``</script>`` break-out)."""
    text = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    return f'<script type="application/json" id="{element_id}">{text}</script>'


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def display_spans(doc: Doc, spans: list[Span]) -> list[Span]:
    """Normalized spans -> spans in the displayed text."""
    return merge_spans([to_display_span(doc.norm.offsets, s, e) for s, e in spans])


def render_text(text: str, layers: dict[str, list[Span]], titles: dict[Span, str] | None = None) -> str:
    """Escape ``text`` and wrap marked regions in ``<mark class=v|p|g>``.

    ``layers`` maps a class to display spans; where layers overlap, ``v`` beats ``p``
    beats ``g``. ``titles`` adds tooltips to paraphrase spans.
    """
    points = {0, len(text)}
    for spans in layers.values():
        for s, e in spans:
            points.update((max(0, s), min(len(text), e)))
    cuts = sorted(points)
    out: list[str] = []
    for a, b in zip(cuts, cuts[1:]):
        if b <= a:
            continue
        cls = next(
            (c for c in ("v", "p", "g") if any(s <= a and b <= e for s, e in layers.get(c, []))),
            None,
        )
        piece = html.escape(text[a:b])
        if cls is None:
            out.append(piece)
            continue
        title = ""
        if cls == "p" and titles:
            hit = next((t for (s, e), t in titles.items() if s <= a and b <= e), "")
            title = f' title="{html.escape(hit)}"' if hit else ""
        out.append(f'<mark class="{cls}"{title}>{piece}</mark>')
    return "".join(out)


def _pair_view(report: Report, pair: PairResult) -> dict[str, object]:
    left, right = report.docs[pair.left], report.docs[pair.right]
    sides = {}
    for key, doc, verb, other in (
        ("left", left, pair.verbatim_left, [m.left for m in pair.para]),
        ("right", right, pair.verbatim_right, [m.right for m in pair.para]),
    ):
        layers = {
            "v": display_spans(doc, verb),
            "p": display_spans(doc, other),
            "g": display_spans(doc, doc.mask),
        }
        titles = {}
        for m in pair.para:
            span = m.left if key == "left" else m.right
            titles[to_display_span(doc.norm.offsets, *span)] = f"Dice {m.dice:.2f}"
        sides[key] = (doc, layers, titles)
    return sides  # type: ignore[return-value]


def pair_page(report: Report, pair: PairResult, back_href: str | None = None) -> str:
    """One side-by-side page for a document pair."""
    sides = _pair_view(report, pair)
    parts = [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
        f"<title>{html.escape(pair.left)} ~ {html.escape(pair.right)}</title>",
        f"<style>{CSS}</style></head><body>",
        f"<h1>{html.escape(pair.left)} ~ {html.escape(pair.right)}</h1>",
        f'<p class="note">{DISCLAIMER}</p>',
        "<p>"
        f"축자 일치 {html.escape(pair.left)}: <b>{_pct(pair.verbatim_lr)}</b> / {html.escape(pair.right)}: <b>{_pct(pair.verbatim_rl)}</b>"
        f" · 바꿔쓴 문장 <b>{pair.para_sentences}</b>"
        f" · 종합 {_pct(pair.score_lr)} / {_pct(pair.score_rl)}</p>",
        '<p class="legend"><mark class="v">축자 일치</mark><mark class="p">바꿔 쓴 문장(Dice)</mark>'
        '<mark class="g">과제 지문(제외)</mark></p>',
        '<div class="cols">',
    ]
    for key in ("left", "right"):
        doc, layers, titles = sides[key]  # type: ignore[misc]
        parts.append(f'<div><h3>{html.escape(doc.name)}</h3><div class="doc">{render_text(doc.norm.display, layers, titles)}</div></div>')
    parts.append("</div>")
    if pair.para:
        left, right = report.docs[pair.left], report.docs[pair.right]
        parts.append("<h3>바꿔 쓴 문장 쌍</h3><table><thead><tr><th>Dice</th><th>왼쪽</th><th>오른쪽</th></tr></thead><tbody>")
        for m in sorted(pair.para, key=lambda m: -m.dice):
            ls = to_display_span(left.norm.offsets, *m.left)
            rs = to_display_span(right.norm.offsets, *m.right)
            parts.append(
                f'<tr><td class="n">{m.dice:.2f}</td><td>{html.escape(left.norm.display[ls[0]:ls[1]])}</td>'
                f"<td>{html.escape(right.norm.display[rs[0]:rs[1]])}</td></tr>"
            )
        parts.append("</tbody></table>")
    if back_href:
        parts.append(f'<p><a href="{html.escape(back_href)}">순위표로 돌아가기</a></p>')
    data = {
        "left": pair.left,
        "right": pair.right,
        "verbatim_lr": round(pair.verbatim_lr, 4),
        "verbatim_rl": round(pair.verbatim_rl, 4),
        "para_sentences": pair.para_sentences,
        "score_lr": round(pair.score_lr, 4),
        "score_rl": round(pair.score_rl, 4),
        "dice": [m.dice for m in pair.para],
    }
    parts.append(_json_block(data, "pair-data"))
    parts.append("</body></html>")
    return "\n".join(parts)


def index_page(report: Report, shown: list[tuple[PairResult, str]]) -> str:
    """Ranking table. ``shown`` is ``[(pair, relative_link), ...]`` in rank order."""
    cfg = report.config
    rows = []
    for rank, (p, link) in enumerate(shown, 1):
        rows.append(
            f'<tr data-rank="{rank}" data-left="{html.escape(p.left)}" data-right="{html.escape(p.right)}" '
            f'data-vlr="{p.verbatim_lr:.4f}" data-vrl="{p.verbatim_rl:.4f}" data-para="{p.para_sentences}" '
            f'data-max="{p.rank_key:.4f}"><td class="n">{rank}</td>'
            f'<td><a href="{html.escape(link)}">{html.escape(p.left)}</a></td><td>{html.escape(p.right)}</td>'
            f'<td class="n">{_pct(p.verbatim_lr)}</td><td class="n">{_pct(p.verbatim_rl)}</td>'
            f'<td class="n">{p.para_sentences}</td><td class="n">{_pct(p.score_lr)}</td><td class="n">{_pct(p.score_rl)}</td></tr>'
        )
    fails = "".join(
        f"<tr class='fail'><td>{html.escape(f.name)}</td><td>추출 실패: {html.escape(f.reason)}</td></tr>"
        for f in report.failures
    )
    s = report.stats
    data = {
        "stats": s,
        "config": {
            "k": cfg.k, "w": cfg.w, "min_match": cfg.min_match, "dice": cfg.dice,
            "min_sentence": cfg.min_sentence, "group_ratio": cfg.group_ratio,
        },
        "pairs": [
            {"left": p.left, "right": p.right, "verbatim_lr": round(p.verbatim_lr, 4),
             "verbatim_rl": round(p.verbatim_rl, 4), "para_sentences": p.para_sentences,
             "score_lr": round(p.score_lr, 4), "score_rl": round(p.score_rl, 4)}
            for p, _ in shown
        ],
        "failures": [{"name": f.name, "reason": f.reason} for f in report.failures],
    }
    body = [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>ko-copycheck 보고서</title>',
        f"<style>{CSS}</style></head><body><h1>ko-copycheck 보고서</h1>",
        f'<p class="note">{DISCLAIMER} 파일은 어디로도 전송되지 않았습니다.</p>',
        f"<p>문서 {s['documents']}편 · 전체 쌍 {s['all_pairs']} · 후보 쌍 {s['candidate_pairs']} · "
        f"설정 k={cfg.k}, w={cfg.w}, 최소 일치 {cfg.min_match}자, Dice ≥ {cfg.dice:g} · 머리글을 눌러 정렬</p>",
        "<table><thead><tr>"
        '<th data-k="rank">#</th><th data-k="left">왼쪽</th><th data-k="right">오른쪽</th>'
        '<th data-k="vlr">축자 L←R</th><th data-k="vrl">축자 R←L</th><th data-k="para">바꿔쓴 문장</th>'
        '<th data-k="max">종합 L←R</th><th>종합 R←L</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>",
    ]
    if not rows:
        body.append("<p>겹치는 쌍이 없습니다.</p>")
    if fails:
        body.append(f"<h2>추출 실패</h2><table><tbody>{fails}</tbody></table>")
    body.append(_json_block(data, "report-data"))
    body.append(f"<script>{SORT_JS}</script></body></html>")
    return "\n".join(body)


def write_report(report: Report, out_dir: Path, top: int = 300) -> Path:
    """Write ``index.html`` and ``pairs/NNNN.html`` for pairs with a non-zero score."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs_dir = out_dir / "pairs"
    pairs_dir.mkdir(exist_ok=True)
    shown: list[tuple[PairResult, str]] = []
    for p in report.pairs:
        if p.rank_key <= 0 or len(shown) >= top:
            continue
        name = f"{len(shown) + 1:04d}.html"
        (pairs_dir / name).write_text(pair_page(report, p, "../index.html"), encoding="utf-8")
        shown.append((p, f"pairs/{name}"))
    index = out_dir / "index.html"
    index.write_text(index_page(report, shown), encoding="utf-8")
    return index
