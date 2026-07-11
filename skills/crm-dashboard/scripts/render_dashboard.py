#!/usr/bin/env python3
"""
render_dashboard.py — render a CRM pipeline dashboard from a state JSON into self-contained HTML.

The "script-heavy" half of the dashboard skill: the model gathers CRM state via the read tools and
shapes it into the JSON below; this script renders it deterministically (identical every run, no
hand-authored HTML). Self-contained (no JS beyond none, no external assets) so it renders in Claude's
sandboxed artifact view, and theme-aware (light/dark).

Usage:
    python3 render_dashboard.py state.json out.html
    cat state.json | python3 render_dashboard.py - out.html

Input contract:
{
  "workspace": "Acme Consulting",
  "generated_label": "11 Jul 2026",
  "currency": "USD",                         # default USD
  "stats": { "open_pipeline_value": 54000, "open_deals": 2, "relationships": 7, "needs_attention": 3 },
  "stages": [                                # open pipeline stages, IN ORDER
    { "name": "discovery",
      "deals": [ { "name": "...", "amount": 12000, "currency": "USD",
                   "org": "Calder & Co", "people": ["Priya Nair"], "close_date": "2026-09-01" } ] }
  ],
  "attention": [                            # relationships to nudge (the follow-up strip)
    { "title": "David Okafor", "kind": "prospect",
      "reason": "No contact logged yet", "detail": "Meridian — fractional COO engagement" }
  ],
  "won": [ { "name": "...", "amount": 18000, "currency": "USD", "org": "Northwind Logistics" } ]  # optional
}
"""

import html
import json
import sys

CURRENCY = {"USD": "$", "GBP": "£", "EUR": "€"}


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def money(amount, currency: str) -> str:
    if amount is None:
        return "—"
    sym = CURRENCY.get(currency, "")
    n = f"{amount:,.0f}"
    return f"{sym}{n}" if sym else f"{n} {currency}"


def kicker(text: str) -> str:
    return f"<span class='kicker'>{esc(text)}</span>"


def render_stats(stats: dict, currency: str) -> str:
    attention = stats.get("needs_attention", 0)
    tiles = [
        ("Open pipeline", money(stats.get("open_pipeline_value"), currency), "figure serif", False),
        ("Open deals", str(stats.get("open_deals", 0)), "figure serif", False),
        ("Relationships", str(stats.get("relationships", 0)), "figure serif", False),
        ("Needs a nudge", str(attention), "figure serif", attention and attention > 0),
    ]
    cells = ""
    for label, value, cls, warn in tiles:
        wc = " tile-warn" if warn else ""
        cells += (
            f"<div class='tile{wc}'>"
            f"<div class='tile-label'>{esc(label)}</div>"
            f"<div class='{cls}'>{esc(value)}</div>"
            "</div>"
        )
    return f"<section class='tiles'>{cells}</section>"


def render_deal(deal: dict, currency: str) -> str:
    people = deal.get("people") or []
    who = " · ".join(esc(p) for p in people)
    org = f"<span class='deal-org'>{esc(deal['org'])}</span>" if deal.get("org") else ""
    sep = " · " if org and who else ""
    meta = f"{org}{sep}<span class='deal-people'>{who}</span>" if (org or who) else ""
    close = (
        f"<span class='deal-close'>close {esc(deal['close_date'])}</span>"
        if deal.get("close_date") else ""
    )
    return (
        "<article class='deal'>"
        f"<div class='deal-top'><h3 class='deal-name'>{esc(deal.get('name','(unnamed deal)'))}</h3>"
        f"<span class='deal-amount'>{money(deal.get('amount'), deal.get('currency', currency))}</span></div>"
        f"<div class='deal-meta'>{meta}</div>"
        f"{('<div class=' + chr(39) + 'deal-foot' + chr(39) + '>' + close + '</div>') if close else ''}"
        "</article>"
    )


def render_stage(stage: dict, currency: str) -> str:
    deals = stage.get("deals") or []
    subtotal = sum(d.get("amount") or 0 for d in deals)
    cards = "".join(render_deal(d, currency) for d in deals) or "<p class='stage-empty'>Nothing here</p>"
    return (
        "<div class='col'>"
        "<div class='col-head'>"
        f"<span class='col-name'>{esc(stage.get('name',''))}</span>"
        f"<span class='col-count'>{len(deals)}</span>"
        f"<span class='col-subtotal'>{money(subtotal, currency)}</span>"
        "</div>"
        f"<div class='col-body'>{cards}</div>"
        "</div>"
    )


def render_attention(items: list) -> str:
    if not items:
        return (
            "<section class='attention'>"
            + kicker("Needs a nudge")
            + "<p class='attention-clear'>You're on top of everyone. Nothing's gone quiet. ✓</p>"
            "</section>"
        )
    rows = ""
    for it in items:
        detail = f"<div class='att-detail'>{esc(it['detail'])}</div>" if it.get("detail") else ""
        kind = f"<span class='att-kind'>{esc(it['kind'])}</span>" if it.get("kind") else ""
        rows += (
            "<li class='att-row'>"
            f"<div class='att-main'><div class='att-nameline'><span class='att-name'>{esc(it.get('title',''))}</span>{kind}</div>{detail}</div>"
            f"<div class='att-reason'>{esc(it.get('reason',''))}</div>"
            "</li>"
        )
    return (
        "<section class='attention'>"
        + kicker("Needs a nudge")
        + f"<ul class='att-list'>{rows}</ul>"
        "</section>"
    )


def render_won(won: list, currency: str) -> str:
    if not won:
        return ""
    chips = ""
    for w in won:
        chips += (
            "<span class='won-chip'>"
            f"{esc(w.get('name',''))} <span class='won-amt'>{money(w.get('amount'), w.get('currency', currency))}</span>"
            "</span>"
        )
    return f"<section class='won'>{kicker('Recently won')}<div class='won-row'>{chips}</div></section>"


def render(data: dict) -> str:
    currency = data.get("currency", "USD")
    stages = data.get("stages") or []
    summary = data.get("stats", {})
    n_deals = summary.get("open_deals", sum(len(s.get("deals") or []) for s in stages))
    val = money(summary.get("open_pipeline_value"), currency)
    n_att = summary.get("needs_attention", len(data.get("attention") or []))
    line = f"{val} across {n_deals} open deal{'s' if n_deals != 1 else ''}"
    if n_att:
        line += f" · {n_att} relationship{'s' if n_att != 1 else ''} to nudge"

    board = "".join(render_stage(s, currency) for s in stages) or "<p class='stage-empty'>No open deals.</p>"

    body = (
        "<header class='masthead'>"
        "<div class='mast-left'>"
        + kicker("Pipeline")
        + f"<h1 class='mast-title'>{esc(data.get('workspace','Your CRM'))}</h1>"
        "</div>"
        f"<div class='mast-right'><div class='mast-date'>{esc(data.get('generated_label',''))}</div>"
        f"<div class='mast-summary'>{esc(line)}</div></div>"
        "</header>"
        + render_stats(summary, currency)
        + "<section class='board-wrap'>" + kicker("Open pipeline")
        + f"<div class='board'>{board}</div></section>"
        + render_attention(data.get("attention") or [])
        + render_won(data.get("won") or [], currency)
    )
    return TEMPLATE.replace("{{BODY}}", body)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pipeline</title>
<style>
  /* ---- Harbor: a calm ledger palette. One accent (teal), semantic state kept separate. ---- */
  :root {
    --bg:#f4f6f4; --surface:#ffffff; --ink:#1a231e; --muted:#657069;
    --line:#e4e8e4; --line-strong:#d3d9d3;
    --accent:#12756a; --accent-ink:#0c5049; --accent-soft:#e3efec;
    --warn:#9a6a16; --warn-soft:#f5ecd9; --bad:#9d4a3b;
    --shadow:0 1px 2px rgba(20,40,35,.05), 0 3px 12px rgba(20,40,35,.05);
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#0e1311; --surface:#151c19; --ink:#e7ece8; --muted:#8a958e;
      --line:#232b27; --line-strong:#313a35;
      --accent:#3fb0a0; --accent-ink:#c3e8e0; --accent-soft:#16302b;
      --warn:#d6a34d; --warn-soft:#2a2413; --bad:#cf7462;
      --shadow:0 1px 2px rgba(0,0,0,.32), 0 3px 12px rgba(0,0,0,.28);
    }
  }
  :root[data-theme="light"] {
    --bg:#f4f6f4; --surface:#ffffff; --ink:#1a231e; --muted:#657069;
    --line:#e4e8e4; --line-strong:#d3d9d3;
    --accent:#12756a; --accent-ink:#0c5049; --accent-soft:#e3efec;
    --warn:#9a6a16; --warn-soft:#f5ecd9; --bad:#9d4a3b;
    --shadow:0 1px 2px rgba(20,40,35,.05), 0 3px 12px rgba(20,40,35,.05);
  }
  :root[data-theme="dark"] {
    --bg:#0e1311; --surface:#151c19; --ink:#e7ece8; --muted:#8a958e;
    --line:#232b27; --line-strong:#313a35;
    --accent:#3fb0a0; --accent-ink:#c3e8e0; --accent-soft:#16302b;
    --warn:#d6a34d; --warn-soft:#2a2413; --bad:#cf7462;
    --shadow:0 1px 2px rgba(0,0,0,.32), 0 3px 12px rgba(0,0,0,.28);
  }

  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans);
    font-size:15px; line-height:1.5; -webkit-font-smoothing:antialiased; }
  .wrap { max-width:940px; margin:0 auto; padding:34px 24px 56px; }

  .kicker { display:block; font-size:11px; font-weight:600; letter-spacing:.14em;
    text-transform:uppercase; color:var(--accent); margin-bottom:10px; }

  /* masthead */
  .masthead { display:flex; justify-content:space-between; align-items:flex-end; gap:24px;
    padding-bottom:20px; border-bottom:1px solid var(--line-strong); margin-bottom:26px; }
  .mast-left .kicker { margin-bottom:6px; }
  .mast-title { font-family:var(--serif); font-weight:600; font-size:30px; line-height:1.05;
    margin:0; letter-spacing:-.01em; text-wrap:balance; }
  .mast-right { text-align:right; }
  .mast-date { font-size:12.5px; color:var(--muted); }
  .mast-summary { font-size:13.5px; color:var(--ink); margin-top:3px; }

  /* stat tiles */
  .tiles { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:32px; }
  .tile { background:var(--surface); border:1px solid var(--line); border-radius:12px;
    padding:16px 18px; box-shadow:var(--shadow); }
  .tile-label { font-size:11.5px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
  .figure { font-family:var(--serif); font-size:30px; font-weight:600; margin-top:8px;
    font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
  .tile-warn { border-color:var(--warn); background:var(--warn-soft); }
  .tile-warn .figure { color:var(--warn); }

  /* pipeline board */
  .board-wrap { margin-bottom:32px; }
  .board { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(240px,1fr); gap:14px;
    overflow-x:auto; padding-bottom:6px; }
  .col { background:transparent; }
  .col-head { display:flex; align-items:baseline; gap:8px; padding:0 2px 10px;
    border-bottom:2px solid var(--accent); margin-bottom:12px; }
  .col-name { font-size:12.5px; font-weight:650; letter-spacing:.06em; text-transform:uppercase;
    color:var(--ink); }
  .col-count { font-size:11px; font-weight:600; color:var(--accent-ink); background:var(--accent-soft);
    border-radius:999px; padding:1px 8px; }
  .col-subtotal { margin-left:auto; font-family:var(--mono); font-size:12px; color:var(--muted);
    font-variant-numeric:tabular-nums; }
  .col-body { display:flex; flex-direction:column; gap:10px; }

  .deal { background:var(--surface); border:1px solid var(--line); border-radius:11px;
    padding:13px 14px; box-shadow:var(--shadow); transition:transform .12s ease, border-color .12s ease; }
  .deal:hover { transform:translateY(-1px); border-color:var(--line-strong); }
  .deal-top { display:flex; justify-content:space-between; align-items:baseline; gap:10px; }
  .deal-name { font-family:var(--serif); font-size:16px; font-weight:600; margin:0; line-height:1.2;
    text-wrap:balance; }
  .deal-amount { font-family:var(--mono); font-size:13.5px; color:var(--accent-ink);
    font-variant-numeric:tabular-nums; white-space:nowrap; }
  .deal-meta { font-size:12.5px; color:var(--muted); margin-top:6px; }
  .deal-org { color:var(--ink); font-weight:500; }
  .deal-foot { margin-top:8px; padding-top:8px; border-top:1px dashed var(--line); }
  .deal-close { font-size:11.5px; color:var(--muted); font-variant-numeric:tabular-nums; }
  .stage-empty { font-size:12.5px; color:var(--muted); font-style:italic; padding:6px 2px; }

  /* needs a nudge */
  .attention { background:var(--surface); border:1px solid var(--line); border-left:3px solid var(--warn);
    border-radius:12px; padding:18px 20px; box-shadow:var(--shadow); margin-bottom:24px; }
  .att-list { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; }
  .att-row { display:flex; justify-content:space-between; align-items:center; gap:16px;
    padding:12px 0; border-top:1px solid var(--line); }
  .att-row:first-child { border-top:none; padding-top:2px; }
  .att-main { display:flex; flex-direction:column; gap:2px; }
  .att-nameline { display:flex; align-items:baseline; gap:9px; }
  .att-name { font-family:var(--serif); font-size:16px; font-weight:600; }
  .att-kind { font-size:10.5px; font-weight:600; letter-spacing:.05em; text-transform:uppercase;
    color:var(--muted); border:1px solid var(--line-strong); border-radius:999px; padding:1px 8px; }
  .att-detail { font-size:12px; color:var(--muted); }
  .att-reason { font-size:12.5px; color:var(--warn); text-align:right; white-space:nowrap; }
  .attention-clear { margin:0; font-size:13.5px; color:var(--muted); }

  /* recently won */
  .won { margin-top:6px; }
  .won-row { display:flex; flex-wrap:wrap; gap:8px; }
  .won-chip { font-size:12.5px; color:var(--ink); background:var(--accent-soft);
    border:1px solid var(--accent-soft); border-radius:999px; padding:4px 11px; }
  .won-amt { font-family:var(--mono); color:var(--accent-ink); font-variant-numeric:tabular-nums; }

  @media (max-width:640px) {
    .tiles { grid-template-columns:repeat(2,1fr); }
    .masthead { flex-direction:column; align-items:flex-start; }
    .mast-right { text-align:left; }
  }
  @media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
</style>
</head>
<body>
  <main class="wrap">
    {{BODY}}
  </main>
</body>
</html>"""


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("usage: render_dashboard.py <state.json|-> <out.html>")
    src, out = sys.argv[1], sys.argv[2]
    raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(json.loads(raw)))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
