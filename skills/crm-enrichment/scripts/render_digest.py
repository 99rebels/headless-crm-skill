#!/usr/bin/env python3
"""
render_digest.py — turn a proposed-changes JSON into a self-contained HTML approval digest.

This is the "script-heavy" half of the enrichment skill: the LLM decides WHAT to propose;
this script deterministically renders it (the "Ledger" identity, shared with the dashboard skill),
so the digest looks identical every run and the model never hand-writes HTML. Evidence — the email/
calendar line that justifies each change — sits in a native <details> dropdown: clean by default,
one click to audit. No external assets; it renders inside Claude's sandboxed artifact view.

Usage:
    python3 render_digest.py proposals.json out.html
    cat proposals.json | python3 render_digest.py - out.html

Input contract (all sections optional; empty/missing sections are skipped):
{
  "emails_reviewed": 4,
  "events_reviewed": 3,
  "new_contacts":      [ Item ],   # rendered under "New contacts"  (avatar: person)
  "new_organizations": [ Item ],   # rendered under "New records"   (avatar: org)
  "new_deals":         [ Item ],   # rendered under "New records"   (avatar: deal)
  "deal_updates":      [ Item ],   # rendered under "Updates"       (avatar: deal)
  "updates":           [ Item ],   # rendered under "Updates"       (avatar: person)
  "timeline":          [ Item ],   # rendered under "Logged to your timeline" — touchpoints (email/meeting)
  "summaries":         [ Item ],   # rendered under "Living summaries" — refreshed relationship/deal state
  "conflicts":         [ Conflict ]# rendered under "Needs your call" — existing value would change
}

The living summary (a person's/deal's current-state prose) goes in each `summaries` item's `subtitle`.
A timeline touchpoint uses `title` = what happened (e.g. "Meeting — Nimbus kickoff"), `subtitle` =
who/when, `avatar` = person|deal. These are the loop's new main job (see docs/notes-design.md).

Item = {
  "title":      "Priya Nair",                        # required — the headline
  "subtitle":   "CEO · priya@caldergroup.com",       # optional — one grey line under the title
  "detail":     "→ works at Calder & Co (new)",      # optional — a mono line (links/associations)
  "source":     "email" | "calendar",               # optional — small source badge
  "confidence": "high" | "low",                      # optional — "low" shows a 'mentioned only' badge
  "initials":   "PN",                                # optional — override the monogram (else derived)
  "avatar":     "person" | "org" | "deal",           # optional — override the monogram shape
  "chip":       { "text": "Lead", "kind": "kind" },  # optional — right chip; kind = "kind" | "stage"
  "evidence":   Evidence                             # optional — the <details> dropdown
}
Conflict = {
  "title": "David Okafor", "field": "title",
  "current": "Founder", "proposed": "CEO",
  "source": "email" | "calendar",                    # optional — badge
  "initials": "DO",                                  # optional
  "evidence": Evidence
}
Evidence = {
  "reason":  "One-sentence AI overview: why this change is being proposed.",  # shown first
  "snippet": "the exact email/calendar line that supports it",                # shown italic, as a quote
  "from": "...", "subject": "...", "date": "..."                              # attribution under the quote
}
"""

import html
import json
import re
import sys

# Render groups: (heading, optional hint, [(section_key, default_avatar), ...])
GROUPS = [
    ("New contacts", None, [("new_contacts", "person")]),
    ("New records", None, [("new_organizations", "org"), ("new_deals", "deal")]),
    ("Updates", "to records you already have", [("deal_updates", "deal"), ("updates", "person")]),
    ("Logged to your timeline", "new touchpoints — these set last-contact recency", [("timeline", "person")]),
    ("Living summaries", "refreshed from the latest activity", [("summaries", "person")]),
]
CONFLICT_KEY = "conflicts"


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def initials(name: str, avatar: str) -> str:
    """People get two letters (PN); orgs/deals get one, from the leading word before an em dash."""
    base = re.split(r"[—–\-]", name)[0].strip() or name
    words = [w for w in re.split(r"\s+", base) if w and w[0].isalnum()]
    if not words:
        return esc(name[:2].upper())
    if avatar == "person":
        return esc(("".join(w[0] for w in words[:2])).upper())
    return esc(words[0][:1].upper())


def render_badges(item: dict) -> str:
    out = ""
    src = item.get("source")
    if src in ("email", "calendar"):
        out += f"<span class='badge badge-src'>{esc(src)}</span>"
    if item.get("confidence") == "low":
        out += (
            "<span class='badge badge-low' title='Only mentioned, not a direct correspondent'>"
            "mentioned only</span>"
        )
    return out


def render_avatar(item: dict, avatar: str) -> str:
    mono = item.get("initials") or initials(item.get("title", ""), avatar)
    return f"<span class='ava ava-{avatar}'>{esc(mono)}</span>"


def render_chip(item: dict) -> str:
    chip = item.get("chip")
    if not chip or not chip.get("text"):
        return ""
    kind = chip.get("kind", "kind")
    kind = kind if kind in ("kind", "stage") else "kind"
    return f"<span class='chip chip-{kind}'>{esc(chip['text'])}</span>"


def render_evidence(ev: dict) -> str:
    if not ev:
        return ""
    reason = f"<div class='ev-reason'>{esc(ev['reason'])}</div>" if ev.get("reason") else ""
    snippet = f"<blockquote class='ev-snippet'>{esc(ev['snippet'])}</blockquote>" if ev.get("snippet") else ""
    attr_bits = [esc(ev[k]) for k in ("from", "subject", "date") if ev.get(k)]
    attr = f"<div class='ev-attr'>— {' · '.join(attr_bits)}</div>" if attr_bits else ""
    return (
        "<details class='ev'><summary>Why this?</summary>"
        f"{reason}{snippet}{attr}"
        "</details>"
    )


def render_item(item: dict, avatar: str) -> str:
    subtitle = f"<div class='sub'>{esc(item['subtitle'])}</div>" if item.get("subtitle") else ""
    detail = f"<div class='detail'>{esc(item['detail'])}</div>" if item.get("detail") else ""
    return (
        "<li class='item'>"
        f"{render_avatar(item, avatar)}"
        "<div class='item-main'>"
        f"<div class='title'>{esc(item.get('title', ''))} {render_badges(item)}</div>"
        f"{subtitle}{detail}{render_evidence(item.get('evidence'))}"
        "</div>"
        f"{render_chip(item)}"
        "</li>"
    )


def render_conflict(c: dict) -> str:
    change = (
        f"<span class='cur'>{esc(c.get('current'))}</span>"
        "<span class='arrow'>→</span>"
        f"<span class='prop'>{esc(c.get('proposed'))}</span>"
    )
    return (
        "<li class='item'>"
        f"{render_avatar(c, 'person')}"
        "<div class='item-main'>"
        f"<div class='title'>{esc(c.get('title', ''))} <span class='field'>· {esc(c.get('field',''))}</span> {render_badges(c)}</div>"
        f"<div class='change'>{change}</div>"
        f"{render_evidence(c.get('evidence'))}"
        "</div>"
        "</li>"
    )


def render_group(heading: str, hint, parts, data: dict) -> str:
    rows = ""
    count = 0
    for key, avatar in parts:
        for item in data.get(key, []) or []:
            rows += render_item(item, item.get("avatar", avatar))
            count += 1
    if not count:
        return ""
    hint_html = f"<span class='hint'>{esc(hint)}</span>" if hint else ""
    return (
        "<section class='section'>"
        f"<h2>{esc(heading)} <span class='count'>{count}</span> {hint_html}</h2>"
        f"<ul>{rows}</ul>"
        "</section>"
    )


def render_conflicts(items: list) -> str:
    if not items:
        return ""
    rows = "".join(render_conflict(c) for c in items)
    return (
        "<section class='section conflicts'>"
        f"<h2>Needs your call <span class='count'>{len(items)}</span> "
        "<span class='hint'>existing value would change</span></h2>"
        f"<ul>{rows}</ul>"
        "</section>"
    )


def render(data: dict) -> str:
    n_people = len(data.get("new_contacts", []) or [])
    n_records = len(data.get("new_organizations", []) or []) + len(data.get("new_deals", []) or [])
    n_updates = len(data.get("deal_updates", []) or []) + len(data.get("updates", []) or [])
    n_timeline = len(data.get("timeline", []) or [])
    n_summaries = len(data.get("summaries", []) or [])
    n_review = len(data.get(CONFLICT_KEY, []) or [])
    total = n_people + n_records + n_updates + n_timeline + n_summaries + n_review

    pills = []
    if n_people:
        pills.append(f"<span class='pill'><b>{n_people}</b> new {'people' if n_people != 1 else 'person'}</span>")
    if n_records:
        pills.append(f"<span class='pill'><b>{n_records}</b> new record{'s' if n_records != 1 else ''}</span>")
    if n_updates:
        pills.append(f"<span class='pill'><b>{n_updates}</b> update{'s' if n_updates != 1 else ''}</span>")
    if n_timeline:
        pills.append(f"<span class='pill'><b>{n_timeline}</b> logged</span>")
    if n_summaries:
        pills.append(f"<span class='pill'><b>{n_summaries}</b> summar{'ies' if n_summaries != 1 else 'y'}</span>")
    if n_review:
        pills.append(f"<span class='pill pill-warn'><b>{n_review}</b> to review</span>")
    tally = "".join(pills)

    reviewed = []
    if data.get("emails_reviewed") is not None:
        e = data["emails_reviewed"]
        reviewed.append(f"{e} email{'s' if e != 1 else ''}")
    if data.get("events_reviewed") is not None:
        v = data["events_reviewed"]
        reviewed.append(f"{v} calendar event{'s' if v != 1 else ''}")
    subline = (
        f"Read from {' and '.join(reviewed)} over the last few days."
        if reviewed else "Read from your recent email and calendar."
    )

    body = "".join(render_group(h, hint, parts, data) for h, hint, parts in GROUPS)
    body += render_conflicts(data.get(CONFLICT_KEY, []) or [])

    if total == 0:
        body = ("<section class='section'><ul><li class='item'><div class='item-main'>"
                "<div class='sub'>Nothing to update — your CRM already matches your recent email and calendar. ✓</div>"
                "</div></li></ul></section>")
        approve = ""
    else:
        approve = (
            "<div class='approve'><div class='lead'>Ready when you are.</div>"
            f"<div class='how'>Reply <span class='say'>approve</span> to save all {total} — or tell me which to skip "
            "(e.g. <span class='say'>approve all but the title change</span>). Anything flagged "
            "<b>Needs your call</b> won’t be touched unless you say so.</div></div>"
        )

    return (
        TEMPLATE
        .replace("{{SUBLINE}}", esc(subline))
        .replace("{{TALLY}}", tally)
        .replace("{{BODY}}", body)
        .replace("{{APPROVE}}", approve)
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proposed CRM updates</title>
<style>
  :root{
    --bg:#f3f0e8; --surface:#fffdf7; --raise:#fbf8f1; --ink:#221f18; --muted:#77705f; --faint:#9a927f;
    --line:#e7e0d1; --line-strong:#d8cfba; --accent:#216b57; --accent-ink:#164d3d; --accent-soft:#e3efe9;
    --warn:#8f6412; --warn-ink:#6f4e0e; --warn-soft:#f4ecd7; --warn-line:#e6d3a6;
    --good:#216b57; --bad:#9d4a3b;
    --shadow:0 1px 2px rgba(60,48,24,.05), 0 4px 14px rgba(60,48,24,.05);
    --serif:"Iowan Old Style",Palatino,"Palatino Linotype",Georgia,serif;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:"SF Mono",ui-monospace,Menlo,Consolas,"Liberation Mono",monospace;
  }
  @media (prefers-color-scheme: dark){ :root{
    --bg:#14120d; --surface:#1d1a13; --raise:#221e16; --ink:#ece6d8; --muted:#9c9280; --faint:#766e5e;
    --line:#2b2619; --line-strong:#3a3324; --accent:#4fae90; --accent-ink:#c6e9de; --accent-soft:#1a3129;
    --warn:#d6a34d; --warn-ink:#e8c485; --warn-soft:#2a2413; --warn-line:#403413; --good:#4fae90; --bad:#cf7462;
    --shadow:0 1px 2px rgba(0,0,0,.34), 0 4px 14px rgba(0,0,0,.30);
  }}
  :root[data-theme="light"]{
    --bg:#f3f0e8; --surface:#fffdf7; --raise:#fbf8f1; --ink:#221f18; --muted:#77705f; --faint:#9a927f;
    --line:#e7e0d1; --line-strong:#d8cfba; --accent:#216b57; --accent-ink:#164d3d; --accent-soft:#e3efe9;
    --warn:#8f6412; --warn-ink:#6f4e0e; --warn-soft:#f4ecd7; --warn-line:#e6d3a6; --good:#216b57; --bad:#9d4a3b;
    --shadow:0 1px 2px rgba(60,48,24,.05), 0 4px 14px rgba(60,48,24,.05);
  }
  :root[data-theme="dark"]{
    --bg:#14120d; --surface:#1d1a13; --raise:#221e16; --ink:#ece6d8; --muted:#9c9280; --faint:#766e5e;
    --line:#2b2619; --line-strong:#3a3324; --accent:#4fae90; --accent-ink:#c6e9de; --accent-soft:#1a3129;
    --warn:#d6a34d; --warn-ink:#e8c485; --warn-soft:#2a2413; --warn-line:#403413; --good:#4fae90; --bad:#cf7462;
    --shadow:0 1px 2px rgba(0,0,0,.34), 0 4px 14px rgba(0,0,0,.30);
  }

  *{ box-sizing:border-box; }
  body{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 var(--sans); -webkit-font-smoothing:antialiased; }
  .wrap{ max-width:640px; margin:0 auto; padding:32px 20px 40px; }
  .kicker{ font:600 11px/1 var(--sans); letter-spacing:.14em; text-transform:uppercase; color:var(--accent); }

  .topbar{ display:flex; justify-content:flex-end; margin-bottom:10px; }
  .themebar{ display:inline-flex; background:var(--raise); border:1px solid var(--line); border-radius:999px; padding:3px; gap:2px; }
  .themebar button{ font:600 11px/1 var(--sans); color:var(--muted); background:none; border:none; border-radius:999px; padding:6px 11px; cursor:pointer; }
  .themebar button[aria-pressed="true"]{ color:var(--accent-ink); background:var(--surface); box-shadow:var(--shadow); }
  .themebar button:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }

  header{ padding-bottom:20px; border-bottom:1px solid var(--line-strong); margin-bottom:22px; }
  header h1{ font-family:var(--serif); font-weight:600; font-size:27px; line-height:1.06; margin:8px 0 0; letter-spacing:-.01em; }
  .subline{ font-size:13px; color:var(--muted); margin-top:6px; }
  .tally{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }
  .pill{ font:12px/1 var(--sans); color:var(--muted); background:var(--surface); border:1px solid var(--line); border-radius:999px; padding:8px 12px; }
  .pill b{ font-family:var(--mono); color:var(--ink); font-weight:700; margin-right:4px; }
  .pill-warn{ background:var(--warn-soft); border-color:var(--warn-line); color:var(--warn-ink); }
  .pill-warn b{ color:var(--warn-ink); }
  .reassure{ display:inline-flex; align-items:center; gap:7px; margin-top:14px; font:600 12px/1 var(--sans);
    color:var(--accent-ink); background:var(--accent-soft); border-radius:999px; padding:7px 13px; }
  .reassure::before{ content:""; width:7px; height:7px; border-radius:999px; background:var(--accent); }

  .section{ background:var(--surface); border:1px solid var(--line); border-radius:13px; box-shadow:var(--shadow);
    padding:4px 18px 6px; margin-bottom:13px; }
  .section > h2{ display:flex; align-items:center; gap:9px; margin:15px 0 3px; font:600 10.5px/1 var(--sans);
    letter-spacing:.12em; text-transform:uppercase; color:var(--accent); }
  .section > h2 .count{ font:600 11px/1 var(--mono); color:var(--accent-ink); background:var(--accent-soft); border-radius:999px; padding:2px 8px; }
  .section > h2 .hint{ margin-left:auto; font:400 11px/1 var(--sans); letter-spacing:0; text-transform:none; color:var(--faint); font-style:italic; }

  ul{ list-style:none; margin:0; padding:0; }
  .item{ display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:13px; align-items:start;
    padding:14px 0; border-top:1px solid var(--line); }
  .item:first-child{ border-top:none; }

  .ava{ width:36px; height:36px; flex:none; display:grid; place-items:center; font-family:var(--serif); font-weight:600; font-size:13.5px; margin-top:1px; }
  .ava-person{ border-radius:999px; background:var(--accent-soft); color:var(--accent-ink); }
  .ava-org{ border-radius:9px; background:var(--raise); color:var(--ink); border:1px solid var(--line-strong); }
  .ava-deal{ border-radius:999px; background:transparent; color:var(--accent-ink); border:1.5px solid var(--accent); font-size:12px; }

  .item-main{ min-width:0; }
  .title{ font-family:var(--serif); font-weight:600; font-size:15.5px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; line-height:1.25; }
  .badge{ font:600 10px/1.4 var(--sans); padding:2px 8px; border-radius:999px; letter-spacing:.03em; }
  .badge-src{ color:var(--muted); background:var(--raise); border:1px solid var(--line); font-weight:500; }
  .badge-low{ color:var(--warn-ink); background:var(--warn-soft); border:1px solid var(--warn-line); }
  .sub{ font:13px/1.45 var(--sans); color:var(--muted); margin-top:3px; }
  .detail{ font:12.5px/1.45 var(--mono); color:var(--accent-ink); margin-top:4px; }

  .chip{ font:600 11px/1.3 var(--sans); border-radius:999px; padding:5px 11px; white-space:nowrap; margin-top:2px; }
  .chip-kind{ color:var(--muted); background:var(--raise); border:1px solid var(--line-strong); }
  .chip-stage{ color:var(--accent-ink); background:var(--accent-soft); }

  details.ev{ margin-top:10px; grid-column:2 / -1; }
  details.ev summary{ cursor:pointer; color:var(--accent); font:600 12px/1 var(--sans); list-style:none;
    display:inline-flex; align-items:center; gap:6px; user-select:none; padding:2px 0; }
  details.ev summary::-webkit-details-marker{ display:none; }
  details.ev summary::before{ content:"\\25B8"; font-size:10px; transition:transform .15s ease; }
  details.ev[open] summary::before{ transform:rotate(90deg); }
  .ev-reason{ color:var(--ink); font-size:13px; line-height:1.5; margin:9px 0 0; }
  .ev-snippet{ margin:9px 0 0; padding:9px 13px; border-left:3px solid var(--line-strong); background:var(--raise);
    border-radius:0 8px 8px 0; color:var(--muted); font-size:12.5px; font-style:italic; line-height:1.5; }
  .ev-attr{ color:var(--faint); font:11.5px/1.4 var(--mono); margin-top:8px; }

  .section.conflicts{ background:var(--warn-soft); border-color:var(--warn-line); border-left:4px solid var(--warn); }
  .section.conflicts > h2{ color:var(--warn-ink); }
  .section.conflicts > h2 .count{ color:var(--warn-ink); background:var(--warn-line); }
  .section.conflicts .item{ border-top-color:var(--warn-line); }
  .section.conflicts .ava-person{ background:var(--warn-soft); color:var(--warn-ink); border:1.5px solid var(--warn-line); }
  .field{ color:var(--muted); font-weight:400; font-size:13px; }
  .change{ margin-top:7px; font:16px/1.2 var(--serif); display:flex; align-items:center; gap:2px; flex-wrap:wrap; }
  .cur{ text-decoration:line-through; color:var(--muted); }
  .arrow{ margin:0 10px; color:var(--warn-ink); }
  .prop{ color:var(--good); font-weight:700; }
  .conflicts details.ev summary{ color:var(--warn-ink); }
  .conflicts .ev-snippet{ border-left-color:var(--warn-line); }

  .approve{ margin-top:20px; padding:16px 18px; background:var(--surface); border:1px solid var(--line-strong);
    border-radius:13px; box-shadow:var(--shadow); }
  .approve .lead{ font-family:var(--serif); font-size:16px; font-weight:600; }
  .approve .how{ font:13px/1.5 var(--sans); color:var(--muted); margin-top:5px; }
  .approve .say{ font-family:var(--mono); font-size:12.5px; color:var(--ink); background:var(--raise); border:1px solid var(--line); border-radius:8px; padding:3px 8px; }

  @media (max-width:460px){ .item{ grid-template-columns:auto minmax(0,1fr); } .chip{ grid-column:2; justify-self:start; } }
  @media (prefers-reduced-motion:reduce){ *{ transition:none !important; } }
</style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="themebar" role="group" aria-label="Colour theme">
        <button type="button" data-set="light">&#9728; Light</button>
        <button type="button" data-set="dark">&#9790; Dark</button>
      </div>
    </div>
    <header>
      <span class="kicker">Enrichment</span>
      <h1>Proposed updates to your CRM</h1>
      <div class="subline">{{SUBLINE}}</div>
      <div class="tally">{{TALLY}}</div>
      <span class="reassure">Nothing is saved until you approve</span>
    </header>
    {{BODY}}
    {{APPROVE}}
  </div>
  <script>
  (function(){
    var root=document.documentElement;
    var btns=Array.prototype.slice.call(document.querySelectorAll(".themebar button"));
    function media(){ return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
    function apply(t){ root.setAttribute("data-theme",t);
      btns.forEach(function(b){ b.setAttribute("aria-pressed", b.getAttribute("data-set")===t ? "true":"false"); }); }
    apply(root.getAttribute("data-theme") || media());
    btns.forEach(function(b){ b.addEventListener("click",function(){ apply(b.getAttribute("data-set")); }); });
  })();
  </script>
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
