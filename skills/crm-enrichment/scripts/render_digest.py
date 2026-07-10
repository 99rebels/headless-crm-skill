#!/usr/bin/env python3
"""
render_digest.py — turn a proposed-changes JSON into a self-contained HTML approval digest.

This is the "script-heavy" half of the enrichment skill: the LLM decides WHAT to propose;
this script deterministically renders it, so the digest looks identical every run and the model
never hand-writes HTML. Evidence (the email snippet that justifies each change) sits in a native
<details> dropdown — clean by default, one click to see the source. No JS, no external assets:
it renders inside Claude's sandboxed artifact view.

Usage:
    python3 render_digest.py proposals.json out.html
    cat proposals.json | python3 render_digest.py - out.html

Input contract (all sections optional; empty/missing sections are skipped):
{
  "emails_reviewed": 4,
  "new_contacts":      [ Item ],
  "new_organizations": [ Item ],
  "new_deals":         [ Item ],
  "updates":           [ Item ],   # enrichments to existing records (add to empty / new attribute)
  "deal_updates":      [ Item ],   # stage/amount/status moves on existing deals
  "conflicts":         [ Conflict ]# existing non-empty value would change — needs a human call
}

Item = {
  "title":      "Priya Nair",                      # required — the headline
  "subtitle":   "CEO · priya@caldergroup.com",     # optional — one grey line under the title
  "detail":     "→ works_at Calder & Co (existing)",# optional — a second grey line (e.g. links)
  "source":     "email" | "calendar",             # optional — which source surfaced this (badge)
  "confidence": "high" | "low",                    # optional — "low" shows a 'mentioned only' badge
  "evidence":   Evidence                           # optional — the <details> dropdown
}
Conflict = {
  "title": "David Okafor", "field": "title",
  "current": "Founder", "proposed": "CEO",
  "source": "email" | "calendar",                 # optional — badge
  "evidence": Evidence
}
Evidence = {
  "reason":  "One-sentence AI overview: why this change is being proposed.",  # shown first, prominent
  "snippet": "the exact email line that supports it",                          # shown italic, as the quote
  "from": "...", "subject": "...", "date": "..."                              # attribution under the quote
}
"""

import html
import json
import sys


# Section key -> (emoji, heading). Order here is the render order.
SECTIONS = [
    ("new_contacts", "🆕", "New contacts"),
    ("new_organizations", "🏢", "New organisations"),
    ("new_deals", "💼", "New deals"),
    ("deal_updates", "📈", "Deal updates"),
    ("updates", "✨", "Enrichments to existing records"),
]


SOURCE_LABELS = {"email": "📧 email", "calendar": "📅 calendar"}


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def render_badges(item: dict) -> str:
    """Small chips after a title: which source surfaced it, and (for people) a confidence flag."""
    out = ""
    src = item.get("source")
    if src in SOURCE_LABELS:
        out += f"<span class='badge badge-source'>{SOURCE_LABELS[src]}</span>"
    if item.get("confidence") == "low":
        out += (
            "<span class='badge badge-low' title='Only mentioned, not a direct correspondent'>"
            "mentioned only</span>"
        )
    return out


def render_evidence(ev: dict) -> str:
    """The collapsible 'AI overview' dropdown: a brief reason first, then the quoted email line
    (italic) that supports it, then a small attribution."""
    if not ev:
        return ""
    reason = f"<div class='ev-reason'>{esc(ev['reason'])}</div>" if ev.get("reason") else ""
    snippet = f"<blockquote class='ev-snippet'>{esc(ev['snippet'])}</blockquote>" if ev.get("snippet") else ""
    attr_bits = [esc(ev[k]) for k in ("from", "subject", "date") if ev.get(k)]
    attr = f"<div class='ev-attr'>— {' · '.join(attr_bits)}</div>" if attr_bits else ""
    return (
        "<details class='ev'>"
        "<summary>AI overview</summary>"
        f"{reason}{snippet}{attr}"
        "</details>"
    )


def render_item(item: dict) -> str:
    subtitle = f"<div class='sub'>{esc(item['subtitle'])}</div>" if item.get("subtitle") else ""
    detail = f"<div class='sub detail'>{esc(item['detail'])}</div>" if item.get("detail") else ""
    return (
        "<li class='item'>"
        f"<div class='title'>{esc(item.get('title', ''))}{render_badges(item)}</div>"
        f"{subtitle}{detail}"
        f"{render_evidence(item.get('evidence'))}"
        "</li>"
    )


def render_conflict(c: dict) -> str:
    change = (
        f"<span class='cur'>{esc(c.get('current'))}</span>"
        f"<span class='arrow'>→</span>"
        f"<span class='prop'>{esc(c.get('proposed'))}</span>"
    )
    return (
        "<li class='item conflict'>"
        f"<div class='title'>{esc(c.get('title', ''))} · <span class='field'>{esc(c.get('field',''))}</span>{render_badges(c)}</div>"
        f"<div class='change'>{change}</div>"
        f"{render_evidence(c.get('evidence'))}"
        "</li>"
    )


def render_section(emoji: str, heading: str, items: list, conflict: bool = False) -> str:
    if not items:
        return ""
    rows = "".join(render_conflict(i) if conflict else render_item(i) for i in items)
    cls = "section conflicts" if conflict else "section"
    return (
        f"<section class='{cls}'>"
        f"<h2>{emoji} {esc(heading)} <span class='count'>{len(items)}</span></h2>"
        f"<ul>{rows}</ul>"
        "</section>"
    )


def render(data: dict) -> str:
    total = sum(len(data.get(k, [])) for k, _, _ in SECTIONS) + len(data.get("conflicts", []))
    sub = f"{total} proposed change{'s' if total != 1 else ''}"
    reviewed = []
    if data.get("emails_reviewed") is not None:
        e = data["emails_reviewed"]
        reviewed.append(f"{e} email{'s' if e != 1 else ''}")
    if data.get("events_reviewed") is not None:
        v = data["events_reviewed"]
        reviewed.append(f"{v} calendar event{'s' if v != 1 else ''}")
    if reviewed:
        sub += " · " + " + ".join(reviewed) + " reviewed"

    body = "".join(render_section(e, h, data.get(k, [])) for k, e, h in SECTIONS)
    body += render_section("⚠️", "Needs your call", data.get("conflicts", []), conflict=True)

    if total == 0:
        body = "<section class='section empty'><p>Nothing to update — your CRM already matches these emails. ✅</p></section>"

    return TEMPLATE.replace("{{SUBTITLE}}", esc(sub)).replace("{{BODY}}", body)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proposed CRM updates</title>
<style>
  :root {
    --bg:#f7f8fa; --card:#ffffff; --ink:#1a1c20; --muted:#6b7280; --line:#e5e7eb;
    --accent:#2563eb; --amber-bg:#fff7ed; --amber-line:#fdba74; --amber-ink:#9a3412;
    --prop:#166534;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#0f1115; --card:#171a21; --ink:#e8eaed; --muted:#9aa1ab; --line:#262b35;
      --accent:#60a5fa; --amber-bg:#2a1c0f; --amber-line:#7c4a1e; --amber-ink:#fdba74;
      --prop:#4ade80;
    }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  .wrap { max-width:680px; margin:0 auto; padding:28px 20px 48px; }
  header h1 { margin:0 0 4px; font-size:20px; font-weight:650; letter-spacing:-0.01em; }
  header .subtitle { color:var(--muted); font-size:13.5px; margin-bottom:20px; }
  .section { background:var(--card); border:1px solid var(--line); border-radius:12px;
    padding:14px 16px; margin-bottom:14px; }
  .section h2 { margin:0 0 10px; font-size:13px; font-weight:600; text-transform:uppercase;
    letter-spacing:0.04em; color:var(--muted); display:flex; align-items:center; gap:8px; }
  .count { margin-left:auto; background:var(--line); color:var(--ink); border-radius:999px;
    padding:1px 9px; font-size:12px; font-weight:600; letter-spacing:0; text-transform:none; }
  ul { list-style:none; margin:0; padding:0; }
  .item { padding:10px 0; border-top:1px solid var(--line); }
  .item:first-child { border-top:none; padding-top:2px; }
  .title { font-weight:560; }
  .sub { color:var(--muted); font-size:13.5px; margin-top:1px; }
  .sub.detail { color:var(--accent); }
  .badge { font-size:11px; font-weight:600; padding:1px 7px; border-radius:999px; margin-left:8px;
    vertical-align:middle; }
  .badge-low { background:var(--amber-bg); color:var(--amber-ink); border:1px solid var(--amber-line); }
  .badge-source { background:var(--bg); color:var(--muted); border:1px solid var(--line); font-weight:500; }
  details.ev { margin-top:7px; }
  details.ev summary { cursor:pointer; color:var(--accent); font-size:12.5px; list-style:none;
    display:inline-flex; align-items:center; gap:5px; user-select:none; }
  details.ev summary::-webkit-details-marker { display:none; }
  details.ev summary::before { content:"▸"; font-size:10px; transition:transform .15s; }
  details.ev[open] summary::before { transform:rotate(90deg); }
  .ev-reason { color:var(--ink); font-size:13px; margin:8px 0; }
  .ev-snippet { margin:8px 0 0; padding:8px 12px; border-left:3px solid var(--line);
    background:var(--bg); border-radius:0 6px 6px 0; color:var(--muted); font-size:13px;
    font-style:italic; }
  .ev-attr { color:var(--muted); font-size:11.5px; margin-top:6px; }
  .conflicts { background:var(--amber-bg); border-color:var(--amber-line); }
  .conflicts h2 { color:var(--amber-ink); }
  .item.conflict .change { margin-top:3px; font-size:14px; }
  .cur { text-decoration:line-through; color:var(--muted); }
  .arrow { margin:0 8px; color:var(--muted); }
  .prop { color:var(--prop); font-weight:600; }
  .field { color:var(--muted); font-weight:400; }
  .empty p { text-align:center; color:var(--muted); margin:8px 0; }
  footer { color:var(--muted); font-size:12px; text-align:center; margin-top:18px; }
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Proposed CRM updates</h1>
      <div class="subtitle">{{SUBTITLE}}</div>
    </header>
    {{BODY}}
    <footer>Nothing is saved until you approve. Reply to approve all, or say which to skip.</footer>
  </div>
</body>
</html>"""


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("usage: render_digest.py <proposals.json|-> <out.html>")
    src, out = sys.argv[1], sys.argv[2]
    raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    data = json.loads(raw)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(data))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
