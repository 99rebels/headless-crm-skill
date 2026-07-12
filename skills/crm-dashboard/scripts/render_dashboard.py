#!/usr/bin/env python3
"""
render_dashboard.py — render a CRM dashboard from a state JSON into self-contained HTML.

The "script-heavy" half of the dashboard skill: the model gathers CRM state via the read tools and
shapes it into the JSON below (including its judgment about what needs attention); this script renders
it deterministically in the "Ledger" identity (shared with the enrichment digest). The page is a
single self-contained HTML file with inline CSS + JS — it renders in Claude's sandboxed artifact view,
is theme-aware (light/dark, plus an in-page toggle), and is interactive:

  • four tabs (Focus / Pipeline / People / Momentum), CSS-driven
  • a "needs you now" action brief (the model's prioritised follow-ups)
  • a clickable "Open deals" tile and clickable deals/people that open a detail drawer
  • live search across deals + people, a "gone quiet" filter, and an interactive pipeline chart

Interactivity is presentation-only: the artifact is a sealed sandbox (no network). Actions that change
the CRM happen back in the Claude conversation via the MCP tools — the drawer's footer says so.

Usage:
    python3 render_dashboard.py state.json out.html
    cat state.json | python3 render_dashboard.py - out.html

Input contract (most fields optional; sensible fallbacks are derived):
{
  "workspace": "Fractional Ops — Rian",
  "weekday": "Saturday",                     # optional, shown above the date
  "generated_label": "11 Jul 2026",
  "currency": "USD",                         # default USD
  "brief": "You have ... worth a nudge.",    # optional plain sentence; else derived from stats (with highlights)
  "stats": { "open_pipeline_value": 30000, "weighted_forecast": 24000,
             "open_deals": 2, "relationships": 5, "needs_attention": 3 },

  "focus": [                                 # the "needs you now" list, in priority order
    { "ref": "meridian",                     # id of a deal/person to open in the drawer
      "name": "David Okafor", "type": "opportunity" | "follow" | "cool",
      "tag": "Opportunity",                  # optional; defaults from type
      "meta": "$30,000",                     # optional right-hand note
      "why": "The board approved the budget…",
      "action": "Send the engagement paperwork" } ],

  "stages": [                                # pipeline columns IN ORDER
    { "name": "discovery",
      "deals": [ Deal ] } ],

  "people": [ Person ],                      # relationship roster (recency)
  "won":    [ { "name": "Northwind — Q3 ops retainer", "amount": 18000 } ],
  "momentum": {                              # optional; Momentum tab
    "won_quarter": 18000, "won_deals": 1,
    "series": { "4":[…], "8":[…], "13":[…] },  # illustrative $k trend by range (optional)
    "labels": { "4":["20 Jun","11 Jul"], "8":[…], "13":[…] } }
}

Deal = {
  "id": "meridian", "name": "Meridian — fractional COO engagement",
  "amount": 30000,            # null → shown as "value TBD"
  "org": "Meridian Health", "people": ["David Okafor"],   # or [{"name","role"}]
  "stage": "Verbal",          # display label (also the board column)
  "weighted_pct": 80,         # for the weighted-forecast fact
  "status": "Open",
  "close_label": "start 1 Sep 2026",         # optional footer line on the card
  "date_label": "Start date", "date_value": "1 Sep 2026",  # optional drawer fact
  "note": "Board approved the budget — a verbal yes…",     # optional drawer note
  "search": "…"               # optional override of the search string
}
Person = {
  "id": "david", "name": "David Okafor",
  "role": "CEO", "org": "Meridian Health", "kind": "prospect",
  "days": 2,                  # days since last contact; null → "new / no contact yet"
  "last_label": "No meeting yet",   # optional override of the recency label
  "email": "david@meridianhealth.com",
  "deals": [ ["Meridian — COO engagement", "verbal · $30,000"] ],   # optional drawer links
  "note": "Verbal yes on the record…",       # optional drawer note
  "search": "…"
}
"""

import html
import json
import sys

CURRENCY = {"USD": "$", "GBP": "£", "EUR": "€"}
TAGS = {"opportunity": "Opportunity", "follow": "Follow up", "cool": "Going quiet"}
TYPE_CLASS = {"opportunity": "t-opp", "follow": "t-follow", "cool": "t-cool"}
DEFAULT_SERIES = {"4": [26, 28, 29, 30], "8": [22, 23, 21, 26, 27, 28, 29, 30],
                  "13": [15, 17, 16, 18, 19, 21, 22, 24, 25, 26, 28, 29, 30]}
DEFAULT_LABELS = {"4": ["20 Jun", "today"], "8": ["8 wks ago", "today"], "13": ["13 wks ago", "today"]}


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def money(amount, currency: str) -> str:
    if amount is None:
        return "—"
    sym = CURRENCY.get(currency, "")
    n = f"{amount:,.0f}"
    return f"{sym}{n}" if sym else f"{n} {currency}"


def person_names(people) -> list:
    """Accept ["Name"] or [{"name","role"}] and return plain names."""
    out = []
    for p in people or []:
        out.append(p["name"] if isinstance(p, dict) else p)
    return out


# ---------- drawer data (built into JS objects the front-end consumes) ----------

def deal_record(d: dict, currency: str) -> dict:
    amt = d.get("amount")
    facts = [["Stage", d.get("stage", "—")], ["Amount", money(amt, currency), "mono"]]
    if d.get("date_value"):
        facts.append([d.get("date_label", "Date"), d["date_value"], "mono"])
    facts.append(["Status", d.get("status", "Open")])
    links = [[n, "decision maker", "→"] for n in person_names(d.get("people"))]
    return {"kind": f"Deal · {d.get('stage', 'Open')}", "title": d.get("name", ""),
            "sub": d.get("org", ""), "facts": facts, "links": links, "note": d.get("note", "")}


def person_record(p: dict) -> dict:
    days = p.get("days")
    last = p.get("last_label") or ("No recent contact" if days is None else f"{days} day{'s' if days != 1 else ''} ago")
    facts = [["Company", p.get("org", "—")], ["Last contact", last, "mono"]]
    if p.get("email"):
        facts.append(["Email", p["email"]])
    if p.get("role_extra"):
        facts.append(["Role", p["role_extra"]])
    links = [[dn[0], dn[1], "→"] for dn in (p.get("deals") or [])]
    sub = " · ".join(x for x in [p.get("role"), p.get("org")] if x)
    kind = (p.get("kind") or "contact").capitalize()
    return {"kind": f"Person · {kind}", "title": p.get("name", ""), "sub": sub,
            "facts": facts, "links": links, "note": p.get("note", "")}


# ---------- server-rendered HTML sections ----------

def render_brief(data: dict, currency: str) -> str:
    if data.get("brief"):
        return esc(data["brief"])
    s = data.get("stats", {})
    val = money(s.get("open_pipeline_value"), currency)
    nd = s.get("open_deals", 0)
    nf = len(data.get("focus") or [])
    out = f"You have <span class='hl'>{esc(val)}</span> in open pipeline across {nd} open deal{'s' if nd != 1 else ''}"
    if nf:
        out += f", and <span class='warnhl'>{nf} thing{'s' if nf != 1 else ''}</span> that need your attention."
    else:
        out += "."
    return out


def render_actions(focus: list) -> str:
    rows = ""
    for f in focus or []:
        t = f.get("type", "follow")
        cls = TYPE_CLASS.get(t, "t-follow")
        tag = f.get("tag") or TAGS.get(t, "Follow up")
        meta = f"<span class='a-meta'>{esc(f['meta'])}</span>" if f.get("meta") else ""
        search = esc(f.get("search") or f.get("name", "")).lower()
        rows += (
            f"<button class='action {cls} rowlink' data-rec='{esc(f.get('ref',''))}' data-search='{search}'>"
            f"<div class='a-head'><div class='a-namewrap'><span class='a-name'>{esc(f.get('name',''))}</span>"
            f"<span class='a-tag'>{esc(tag)}</span></div>{meta}</div>"
            f"<div class='a-why'>{esc(f.get('why',''))}</div>"
            f"<div class='a-do'>{esc(f.get('action',''))}</div>"
            "</button>"
        )
    return rows or "<p class='sec-note'>Nothing needs you right now. ✓</p>"


def render_won_strip(won: list, currency: str) -> str:
    if not won:
        return ""
    chips = "".join(
        f"<span class='won-chip'>{esc(w.get('name',''))} <b>{esc(money(w.get('amount'), currency))}</b></span>"
        for w in won
    )
    return f"<div class='won-strip'><span class='won-lead'>Recently won</span>{chips}</div>"


def render_tiles(data: dict, currency: str) -> str:
    s = data.get("stats", {})
    unstaged = s.get("unstaged_deals", 0)
    open_sub = f"{unstaged} unstaged — tap to triage" if unstaged else "tap to list them"
    cells = (
        f"<div class='tile'><div class='tile-label'>Open pipeline</div>"
        f"<div class='figure'>{esc(money(s.get('open_pipeline_value'), currency))}</div>"
        f"<div class='tile-sub'>value of open deals</div></div>"
        f"<button class='tile tilelink' data-list='open'><div class='tile-label'>Open deals</div>"
        f"<div class='figure'>{s.get('open_deals', 0)}</div><div class='tile-sub'>{esc(open_sub)}</div></button>"
        f"<div class='tile'><div class='tile-label'>Relationships</div>"
        f"<div class='figure'>{s.get('relationships', 0)}</div>"
        f"<div class='tile-sub'>people you're tracking</div></div>"
    )
    return cells


def render_stagebars(stages: list, data: dict, currency: str) -> str:
    rows = []
    computed = []
    maxval = 0
    for st in stages:
        deals = st.get("deals") or []
        subtotal = sum(d.get("amount") or 0 for d in deals)
        unpriced = any(d.get("amount") is None for d in deals)
        computed.append((st.get("name", ""), len(deals), subtotal, unpriced))
        maxval = max(maxval, subtotal)
    for name, count, subtotal, unpriced in computed:
        if count == 0:
            fill = "<div class='sb-fill empty' style='width:100%'></div>"
            val = f"—<span class='cnt'>0 deals</span>"
        elif subtotal == 0 and unpriced:
            fill = "<div class='sb-fill pending' style='width:22%'></div>"
            val = f"value TBD<span class='cnt'>{count} deal{'s' if count != 1 else ''}</span>"
        else:
            w = round(subtotal / maxval * 100) if maxval else 100
            fill = f"<div class='sb-fill' style='width:{w}%'></div>"
            val = f"{esc(money(subtotal, currency))}<span class='cnt'>{count} deal{'s' if count != 1 else ''}</span>"
        rows.append(
            f"<div class='sb-row'><div class='sb-name'>{esc(name)}</div>"
            f"<div class='sb-track'>{fill}</div><div class='sb-val'>{val}</div></div>"
        )
    return "".join(rows)


def render_board(stages: list, currency: str) -> str:
    cols = ""
    for st in stages:
        deals = st.get("deals") or []
        subtotal = sum(d.get("amount") or 0 for d in deals)
        priced = any(d.get("amount") is not None for d in deals)
        sub = money(subtotal, currency) if priced else ("value TBD" if deals else "—")
        cards = ""
        for d in deals:
            names = person_names(d.get("people"))
            who = " · ".join(esc(n) for n in names)
            org = f"<span class='org'>{esc(d['org'])}</span>" if d.get("org") else ""
            sep = " · " if org and who else ""
            foot = (f"<div class='deal-foot'><span class='deal-close'>{esc(d['close_label'])}</span></div>"
                    if d.get("close_label") else "")
            search = esc(d.get("search") or " ".join([d.get("name") or "", d.get("org") or ""] + names)).lower()
            cards += (
                f"<button class='deal rowlink' data-rec='{esc(d.get('id',''))}' data-search='{search}'>"
                f"<div class='deal-top'><h3 class='deal-name'>{esc(d.get('name',''))}</h3>"
                f"<span class='deal-amount'>{esc(money(d.get('amount'), currency))}</span></div>"
                f"<div class='deal-meta'>{org}{sep}{who}</div>{foot}</button>"
            )
        if not cards:
            cards = "<p class='stage-empty'>Nothing here yet</p>"
        cols += (
            f"<div class='col' data-stage='{esc(st.get('name',''))}'>"
            f"<div class='col-head'><span class='col-name'>{esc(st.get('name',''))}</span>"
            f"<span class='col-count'>{len(deals)}</span><span class='col-sub'>{esc(sub)}</span></div>"
            f"<div class='col-body'>{cards}</div></div>"
        )
    return cols


def render_people(people: list) -> str:
    rows = ""
    for p in people or []:
        days = p.get("days")
        if days is None:
            cls, fill, when, quiet = "new-r", 100, "—", True  # short token in the row; drawer says "no contact logged"
        else:
            cls = "fresh" if days < 7 else ("warm" if days <= 21 else "stale")
            fill = max(8, min(96, 100 - days * 3))
            when = p.get("last_label") or f"{days} day{'s' if days != 1 else ''}"
            quiet = days > 21
        org_line = " · ".join(x for x in [p.get("org"), p.get("kind")] if x)
        search = esc(p.get("search") or " ".join(x for x in [p.get("name"), p.get("org"), p.get("kind")] if x)).lower()
        rows += (
            f"<div class='rec-row {cls} rowlink' data-rec='{esc(p.get('id',''))}' data-quiet='{1 if quiet else 0}' data-search='{search}'>"
            f"<div><div class='rec-name'>{esc(p.get('name',''))}</div><div class='rec-org'>{esc(org_line)}</div></div>"
            f"<div class='rec-track'><div class='rec-fill' style='width:{fill}%'></div></div>"
            f"<div class='rec-when'>{esc(when)}</div></div>"
        )
    return rows


def render_momentum(data: dict, currency: str) -> str:
    m = data.get("momentum") or {}
    won = data.get("won") or []
    wq = m.get("won_quarter")
    wd = m.get("won_deals")
    big = money(wq, currency) if wq is not None else money(sum(w.get("amount") or 0 for w in won), currency)
    deals_lbl = f"<small>{wd} deal{'s' if wd != 1 else ''}</small>" if wd is not None else ""
    chips = "".join(
        f"<span class='won-chip'>{esc(w.get('name',''))} <b>{esc(money(w.get('amount'), currency))}</b></span>"
        for w in won
    )
    return (f"<div class='card'><h4>Won this quarter</h4><div class='big'>{esc(big)} {deals_lbl}</div>"
            f"<div class='won-row'>{chips}</div></div>")


def render(data: dict) -> str:
    currency = data.get("currency", "USD")
    stages = data.get("stages") or []
    people = data.get("people") or []
    focus = data.get("focus") or []
    s = data.get("stats", {})

    # drawer data
    rec = {}
    for st in stages:
        for d in st.get("deals") or []:
            if d.get("id"):
                rec[d["id"]] = deal_record(d, currency)
    for p in people:
        if p.get("id"):
            rec[p["id"]] = person_record(p)

    open_deals = [d for st in stages for d in (st.get("deals") or [])]
    lists = {"open": {
        "kind": "Pipeline", "title": "Open deals",
        "sub": f"{money(s.get('open_pipeline_value'), currency)} open"
               + (f" · {money(s.get('weighted_forecast'), currency)} weighted" if s.get("weighted_forecast") is not None else ""),
        "rows": [{"id": d.get("id", ""), "name": d.get("name", ""),
                  "meta": " · ".join(x for x in [d.get("stage"), d.get("org")] if x),
                  "amt": money(d.get("amount"), currency)} for d in open_deals],
    }}

    m = data.get("momentum") or {}
    series = m.get("series") or DEFAULT_SERIES
    labels = m.get("labels") or DEFAULT_LABELS

    weekday = f"{esc(data['weekday'])}<br>" if data.get("weekday") else ""
    mast_date = f"{weekday}{esc(data.get('generated_label',''))}"

    repl = {
        "{{TITLE}}": esc(f"Dashboard — {data.get('workspace', 'Your CRM')}"),
        "{{WORKSPACE}}": esc(data.get("workspace", "Your CRM")),
        "{{MAST_DATE}}": mast_date,
        "{{TAB_FOCUS_N}}": str(len(focus)),
        "{{TAB_PIPE_N}}": str(s.get("open_deals", len(open_deals))),
        "{{TAB_PPL_N}}": str(s.get("relationships", len(people))),
        "{{BRIEF}}": render_brief(data, currency),
        "{{ACTIONS}}": render_actions(focus),
        "{{WON_STRIP}}": render_won_strip(data.get("won") or [], currency),
        "{{TILES}}": render_tiles(data, currency),
        "{{STAGEBARS}}": render_stagebars(stages, data, currency),
        "{{BOARD}}": render_board(stages, currency),
        "{{PEOPLE_ROWS}}": render_people(people),
        "{{MOMENTUM}}": render_momentum(data, currency),
        "{{REC_JSON}}": json.dumps(rec, ensure_ascii=False),
        "{{LISTS_JSON}}": json.dumps(lists, ensure_ascii=False),
        "{{SERIES_JSON}}": json.dumps(series, ensure_ascii=False),
        "{{LABELS_JSON}}": json.dumps(labels, ensure_ascii=False),
    }
    out = TEMPLATE
    for k, v in repl.items():
        out = out.replace(k, v)
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
  :root{
    --bg:#f3f0e8; --surface:#fffdf7; --raise:#fbf8f1; --ink:#221f18; --muted:#77705f; --faint:#9a927f;
    --line:#e7e0d1; --line-strong:#d8cfba; --accent:#216b57; --accent-ink:#164d3d; --accent-soft:#e3efe9;
    --warn:#8f6412; --warn-ink:#6f4e0e; --warn-soft:#f4ecd7; --warn-line:#e6d3a6;
    --cool:#3f6f86; --cool-ink:#2c5266; --cool-soft:#e4eef3; --good:#216b57; --bad:#9d4a3b;
    --shadow:0 1px 2px rgba(60,48,24,.05), 0 4px 14px rgba(60,48,24,.05); --shadow-lg:0 8px 40px rgba(40,32,16,.18);
    --serif:"Iowan Old Style",Palatino,"Palatino Linotype",Georgia,serif;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:"SF Mono",ui-monospace,Menlo,Consolas,"Liberation Mono",monospace;
  }
  @media (prefers-color-scheme: dark){ :root{
    --bg:#14120d; --surface:#1d1a13; --raise:#221e16; --ink:#ece6d8; --muted:#9c9280; --faint:#766e5e;
    --line:#2b2619; --line-strong:#3a3324; --accent:#4fae90; --accent-ink:#c6e9de; --accent-soft:#1a3129;
    --warn:#d6a34d; --warn-ink:#e8c485; --warn-soft:#2a2413; --warn-line:#403413;
    --cool:#7fb0c9; --cool-ink:#a7cede; --cool-soft:#17272f; --good:#4fae90; --bad:#cf7462;
    --shadow:0 1px 2px rgba(0,0,0,.34), 0 4px 14px rgba(0,0,0,.30); --shadow-lg:0 10px 44px rgba(0,0,0,.55);
  }}
  :root[data-theme="light"]{
    --bg:#f3f0e8; --surface:#fffdf7; --raise:#fbf8f1; --ink:#221f18; --muted:#77705f; --faint:#9a927f;
    --line:#e7e0d1; --line-strong:#d8cfba; --accent:#216b57; --accent-ink:#164d3d; --accent-soft:#e3efe9;
    --warn:#8f6412; --warn-ink:#6f4e0e; --warn-soft:#f4ecd7; --warn-line:#e6d3a6;
    --cool:#3f6f86; --cool-ink:#2c5266; --cool-soft:#e4eef3; --good:#216b57; --bad:#9d4a3b;
    --shadow:0 1px 2px rgba(60,48,24,.05), 0 4px 14px rgba(60,48,24,.05); --shadow-lg:0 8px 40px rgba(40,32,16,.18);
  }
  :root[data-theme="dark"]{
    --bg:#14120d; --surface:#1d1a13; --raise:#221e16; --ink:#ece6d8; --muted:#9c9280; --faint:#766e5e;
    --line:#2b2619; --line-strong:#3a3324; --accent:#4fae90; --accent-ink:#c6e9de; --accent-soft:#1a3129;
    --warn:#d6a34d; --warn-ink:#e8c485; --warn-soft:#2a2413; --warn-line:#403413;
    --cool:#7fb0c9; --cool-ink:#a7cede; --cool-soft:#17272f; --good:#4fae90; --bad:#cf7462;
    --shadow:0 1px 2px rgba(0,0,0,.34), 0 4px 14px rgba(0,0,0,.30); --shadow-lg:0 10px 44px rgba(0,0,0,.55);
  }

  *{ box-sizing:border-box; }
  body{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 var(--sans); -webkit-font-smoothing:antialiased; }
  .wrap{ max-width:900px; margin:0 auto; padding:32px 22px 64px; }
  .kicker{ font:600 11px/1 var(--sans); letter-spacing:.14em; text-transform:uppercase; color:var(--accent); }

  .topbar{ display:flex; justify-content:flex-end; margin-bottom:10px; }
  .themebar{ display:inline-flex; background:var(--raise); border:1px solid var(--line); border-radius:999px; padding:3px; gap:2px; }
  .themebar button{ font:600 11px/1 var(--sans); color:var(--muted); background:none; border:none; border-radius:999px; padding:6px 11px; cursor:pointer; display:inline-flex; align-items:center; gap:5px; }
  .themebar button[aria-pressed="true"]{ color:var(--accent-ink); background:var(--surface); box-shadow:var(--shadow); }
  .themebar button:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }

  .masthead{ display:flex; justify-content:space-between; align-items:flex-end; gap:24px;
    padding-bottom:18px; border-bottom:1px solid var(--line-strong); }
  .mast-title{ font-family:var(--serif); font-weight:600; font-size:29px; line-height:1.04; margin:8px 0 0; letter-spacing:-.01em; }
  .mast-date{ font:12.5px/1.35 var(--mono); color:var(--muted); text-align:right; }

  .toolbar{ margin-top:20px; }
  .search{ position:relative; }
  .search input{ width:100%; font:14px/1 var(--sans); color:var(--ink); background:var(--surface);
    border:1px solid var(--line-strong); border-radius:10px; padding:11px 34px 11px 36px; outline:none; }
  .search input:focus{ border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }
  .search input::placeholder{ color:var(--faint); }
  .search::before{ content:"\2315"; position:absolute; left:12px; top:50%; transform:translateY(-50%); color:var(--faint); font-size:17px; }
  .search-clear{ position:absolute; right:8px; top:50%; transform:translateY(-50%); border:none; background:none;
    color:var(--faint); cursor:pointer; font-size:15px; padding:4px; display:none; }
  .search.has-val .search-clear{ display:block; }

  .tabswitch{ position:absolute; opacity:0; pointer-events:none; }
  .tabs{ display:flex; justify-content:center; gap:4px; margin:18px 0 26px; border-bottom:1px solid var(--line); flex-wrap:wrap; }
  .tabs label{ font:600 13px/1 var(--sans); color:var(--muted); padding:11px 15px; border-bottom:2px solid transparent;
    cursor:pointer; margin-bottom:-1px; display:inline-flex; align-items:center; gap:7px; border-radius:8px 8px 0 0;
    transition:color .15s, border-color .15s, background .15s; }
  .tabs label:hover{ color:var(--ink); background:var(--raise); }
  .tabs label .tcount{ font:600 11px/1 var(--mono); color:var(--muted); background:var(--line); border-radius:999px; padding:2px 7px; }
  #t-focus:checked ~ .tabs label[for="t-focus"], #t-pipe:checked ~ .tabs label[for="t-pipe"], #t-ppl:checked ~ .tabs label[for="t-ppl"], #t-mom:checked ~ .tabs label[for="t-mom"]{ color:var(--accent-ink); border-bottom-color:var(--accent); }
  #t-focus:checked ~ .tabs label[for="t-focus"] .tcount, #t-pipe:checked ~ .tabs label[for="t-pipe"] .tcount, #t-ppl:checked ~ .tabs label[for="t-ppl"] .tcount{ color:var(--accent-ink); background:var(--accent-soft); }
  .tabswitch:focus-visible + .tabs label{ outline:2px solid var(--accent); outline-offset:2px; }
  .panel{ display:none; }
  #t-focus:checked ~ .panels .panel-focus, #t-pipe:checked ~ .panels .panel-pipe, #t-ppl:checked ~ .panels .panel-ppl, #t-mom:checked ~ .panels .panel-mom{ display:block; animation:fade .2s ease; }
  @keyframes fade{ from{ opacity:0; transform:translateY(4px);} to{ opacity:1; transform:none;} }

  .sec-title{ font:600 10.5px/1 var(--sans); letter-spacing:.14em; text-transform:uppercase; color:var(--accent);
    margin:0 0 14px; display:flex; justify-content:space-between; align-items:center; }
  .sec-title.mt{ margin-top:32px; }
  .sec-note{ font-size:12px; color:var(--faint); font-style:italic; margin:-9px 0 14px; }

  .brief{ font-family:var(--serif); font-size:20px; line-height:1.45; margin:0 0 26px; color:var(--ink); text-wrap:balance; }
  .brief .hl{ color:var(--accent-ink); font-weight:600; } .brief .warnhl{ color:var(--warn); font-weight:600; }

  .actions{ display:flex; flex-direction:column; gap:11px; }
  .action{ display:block; width:100%; text-align:left; font:inherit; color:inherit; cursor:pointer;
    background:var(--surface); border:1px solid var(--line); border-left:3px solid var(--type-color);
    border-radius:12px; padding:14px 16px; box-shadow:var(--shadow); transition:transform .12s ease, border-color .12s ease; }
  .action:hover{ transform:translateY(-1px); }
  .action:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
  .action.t-opp{ --type-color:var(--accent); } .action.t-follow{ --type-color:var(--cool); } .action.t-cool{ --type-color:var(--warn); }
  .a-head{ display:flex; align-items:baseline; gap:10px; justify-content:space-between; }
  .a-namewrap{ display:flex; align-items:baseline; gap:9px; flex-wrap:wrap; }
  .a-name{ font-family:var(--serif); font-size:16.5px; font-weight:600; }
  .a-tag{ font:600 10px/1 var(--sans); text-transform:uppercase; letter-spacing:.06em; padding:3px 8px; border-radius:999px; white-space:nowrap; }
  .t-opp .a-tag{ color:var(--accent-ink); background:var(--accent-soft); }
  .t-follow .a-tag{ color:var(--cool-ink); background:var(--cool-soft); }
  .t-cool .a-tag{ color:var(--warn-ink); background:var(--warn-soft); }
  .a-meta{ font:12.5px/1 var(--mono); color:var(--muted); white-space:nowrap; font-variant-numeric:tabular-nums; }
  .a-why{ font:13px/1.45 var(--sans); color:var(--muted); margin-top:5px; }
  .a-do{ font:600 13.5px/1.4 var(--sans); color:var(--accent-ink); margin-top:9px; display:inline-flex; align-items:center; gap:8px; }
  .a-do::before{ content:"\2192"; color:var(--type-color); font-weight:700; }

  .won-strip{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:12px; padding:14px 16px;
    background:var(--raise); border:1px solid var(--line); border-radius:12px; }
  .won-lead{ font:600 10.5px/1 var(--sans); letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }
  .won-chip{ font:12.5px/1 var(--sans); color:var(--ink); background:var(--accent-soft); border:1px solid var(--accent-soft);
    border-radius:999px; padding:6px 12px; }
  .won-chip b{ font-family:var(--mono); color:var(--accent-ink); font-weight:600; font-variant-numeric:tabular-nums; }

  .tiles{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
  .tile{ background:var(--surface); border:1px solid var(--line); border-radius:13px; padding:15px 16px; box-shadow:var(--shadow); }
  .tile-label{ font:600 11px/1 var(--sans); letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
  .figure{ font-family:var(--serif); font-size:28px; font-weight:600; margin-top:9px; font-variant-numeric:tabular-nums; letter-spacing:-.01em; line-height:1; }
  .tile-sub{ font:11.5px/1.3 var(--sans); color:var(--faint); margin-top:6px; }
  .tilelink{ cursor:pointer; text-align:left; font:inherit; color:inherit; width:100%; display:block; position:relative; transition:transform .12s ease, border-color .12s ease; }
  .tilelink:hover{ transform:translateY(-1px); border-color:var(--accent); }
  .tilelink:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
  .tilelink::after{ content:"\203A"; position:absolute; top:11px; right:14px; color:var(--faint); font-size:17px; line-height:1; }

  .stagebars{ background:var(--surface); border:1px solid var(--line); border-radius:13px; box-shadow:var(--shadow); padding:18px 20px; }
  .sb-row{ display:grid; grid-template-columns:96px 1fr 132px; align-items:center; gap:16px; padding:9px 0; }
  .sb-row + .sb-row{ border-top:1px solid var(--line); }
  .sb-name{ font:600 11px/1.2 var(--sans); letter-spacing:.05em; text-transform:uppercase; color:var(--ink); }
  .sb-track{ height:22px; background:var(--bg); border-radius:6px; overflow:hidden; }
  .sb-fill{ height:100%; background:var(--accent); border-radius:6px; min-width:3px; }
  .sb-fill.empty{ background:repeating-linear-gradient(45deg,var(--line) 0 6px,transparent 6px 12px); }
  .sb-fill.pending{ background:var(--accent-soft); border:1px solid var(--accent); }
  .sb-val{ text-align:right; font:13px/1 var(--mono); color:var(--accent-ink); font-variant-numeric:tabular-nums; }
  .sb-val .cnt{ display:block; font:11px/1.4 var(--sans); color:var(--muted); }
  .forecast{ display:flex; justify-content:space-between; align-items:baseline; margin-top:14px; padding-top:14px; border-top:1px solid var(--line-strong); }
  .forecast .fc-label{ font:600 11px/1 var(--sans); letter-spacing:.05em; text-transform:uppercase; color:var(--muted); }
  .forecast .fc-val{ font-family:var(--mono); font-size:16px; color:var(--ink); font-weight:600; font-variant-numeric:tabular-nums; }

  .board{ display:grid; grid-auto-flow:column; grid-auto-columns:minmax(240px,1fr); gap:14px; overflow-x:auto; padding-bottom:6px; }
  .col-head{ display:flex; align-items:baseline; gap:8px; padding:0 2px 10px; border-bottom:2px solid var(--accent); margin-bottom:12px; }
  .col-name{ font:650 12px/1 var(--sans); letter-spacing:.05em; text-transform:uppercase; color:var(--ink); }
  .col-count{ font:600 11px/1 var(--mono); color:var(--accent-ink); background:var(--accent-soft); border-radius:999px; padding:2px 8px; }
  .col-sub{ margin-left:auto; font:12px/1 var(--mono); color:var(--muted); font-variant-numeric:tabular-nums; }
  .col-body{ display:flex; flex-direction:column; gap:10px; min-height:20px; }
  .deal{ background:var(--surface); border:1px solid var(--line); border-radius:11px; padding:13px 14px; box-shadow:var(--shadow);
    cursor:pointer; transition:transform .12s ease, border-color .12s ease; text-align:left; width:100%; font:inherit; color:inherit; display:block; }
  .deal:hover{ transform:translateY(-1px); border-color:var(--accent); }
  .deal:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
  .deal-top{ display:flex; justify-content:space-between; align-items:baseline; gap:10px; }
  .deal-name{ font-family:var(--serif); font-size:15.5px; font-weight:600; margin:0; line-height:1.2; text-wrap:balance; }
  .deal-amount{ font:13px/1 var(--mono); color:var(--accent-ink); font-variant-numeric:tabular-nums; white-space:nowrap; }
  .deal-meta{ font:12.5px/1.4 var(--sans); color:var(--muted); margin-top:6px; }
  .deal-meta .org{ color:var(--ink); font-weight:500; }
  .deal-foot{ margin-top:9px; padding-top:8px; border-top:1px dashed var(--line); }
  .deal-close{ font:11.5px/1 var(--mono); color:var(--muted); font-variant-numeric:tabular-nums; }
  .stage-empty{ font:12.5px/1 var(--sans); color:var(--faint); font-style:italic; padding:6px 2px; }

  .rec{ background:var(--surface); border:1px solid var(--line); border-radius:13px; box-shadow:var(--shadow); padding:6px 18px; }
  .rowlink{ cursor:pointer; }
  .rec-row{ display:grid; grid-template-columns:1fr 150px 96px; align-items:center; gap:14px; padding:13px 10px; border-top:1px solid var(--line); margin:0 -10px; border-radius:8px; transition:background .12s ease; }
  .rec-row:hover{ background:var(--raise); }
  .rec-row:first-child{ border-top:none; }
  .rec-row:focus-visible{ outline:2px solid var(--accent); outline-offset:-2px; }
  .rec-name{ font-family:var(--serif); font-size:15px; font-weight:600; }
  .rec-org{ font:12px/1.3 var(--sans); color:var(--muted); margin-top:1px; }
  .rec-track{ height:8px; border-radius:999px; background:var(--bg); overflow:hidden; }
  .rec-fill{ height:100%; border-radius:999px; }
  .rec-when{ text-align:right; font:12px/1 var(--mono); font-variant-numeric:tabular-nums; }
  .fresh .rec-fill{ background:var(--accent); } .fresh .rec-when{ color:var(--accent-ink); }
  .warm .rec-fill{ background:var(--cool); } .warm .rec-when{ color:var(--cool-ink); }
  .stale .rec-fill{ background:var(--warn); } .stale .rec-when{ color:var(--warn); }
  .new-r .rec-fill{ background:repeating-linear-gradient(45deg,var(--line-strong) 0 5px,transparent 5px 10px); } .new-r .rec-when{ color:var(--faint); }
  .rec-legend{ display:flex; gap:16px; flex-wrap:wrap; margin:12px 0 4px; font-size:11.5px; color:var(--muted); }
  .rec-legend span{ display:inline-flex; align-items:center; gap:6px; }
  .dot{ width:9px; height:9px; border-radius:999px; display:inline-block; }
  .filterbtn{ font:600 10px/1 var(--sans); letter-spacing:.04em; text-transform:uppercase; color:var(--muted);
    background:none; border:1px solid var(--line-strong); border-radius:999px; padding:5px 11px; cursor:pointer; }
  .filterbtn[aria-pressed="true"]{ color:var(--warn-ink); background:var(--warn-soft); border-color:var(--warn-line); }

  .empty-msg{ padding:24px 8px; text-align:center; color:var(--faint); font-size:13px; font-style:italic; display:none; }

  .mom-grid{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }
  .card{ background:var(--surface); border:1px solid var(--line); border-radius:13px; box-shadow:var(--shadow); padding:18px 20px; }
  .card h4{ margin:0 0 3px; font:600 11px/1 var(--sans); letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
  .card .big{ font-family:var(--serif); font-size:32px; font-weight:600; font-variant-numeric:tabular-nums; letter-spacing:-.01em; margin-top:6px; }
  .card .big small{ font:12px/1 var(--sans); color:var(--muted); font-weight:400; letter-spacing:0; }
  .chart-head{ display:flex; justify-content:space-between; align-items:center; gap:10px; }
  .rangebtns{ display:flex; gap:4px; }
  .rangebtns button{ font:600 10px/1 var(--mono); color:var(--muted); background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:5px 8px; cursor:pointer; }
  .rangebtns button[aria-pressed="true"]{ color:var(--accent-ink); background:var(--accent-soft); border-color:var(--accent); }
  .chart-holder{ position:relative; }
  .chart{ width:100%; height:auto; display:block; margin-top:8px; overflow:visible; }
  .chart .grid{ stroke:var(--line); stroke-width:1; }
  .chart .area{ fill:var(--accent); opacity:.12; }
  .chart .line{ fill:none; stroke:var(--accent); stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
  .chart .dot{ fill:var(--surface); stroke:var(--accent); stroke-width:2; }
  .chart .hl{ fill:var(--accent); }
  .chart .vline{ stroke:var(--line-strong); stroke-width:1; stroke-dasharray:3 3; }
  .tip{ position:absolute; pointer-events:none; background:var(--ink); color:var(--bg); font:600 11px/1.3 var(--mono);
    padding:6px 9px; border-radius:7px; transform:translate(-50%,-120%); white-space:nowrap; opacity:0; transition:opacity .12s; box-shadow:var(--shadow); }
  .tip.on{ opacity:1; }
  .caxis{ display:flex; justify-content:space-between; font:10px var(--mono); color:var(--faint); margin-top:4px; }
  .won-row{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }

  .scrim{ position:fixed; inset:0; background:rgba(20,16,8,.4); opacity:0; pointer-events:none; transition:opacity .2s ease; z-index:40; }
  .scrim.on{ opacity:1; pointer-events:auto; }
  .drawer{ position:fixed; top:0; right:0; height:100%; width:min(400px,92vw); background:var(--surface);
    border-left:1px solid var(--line-strong); box-shadow:var(--shadow-lg); z-index:50; transform:translateX(100%);
    transition:transform .24s cubic-bezier(.4,0,.2,1); overflow-y:auto; padding:24px 24px 40px; }
  .drawer.on{ transform:none; }
  .dr-close{ position:absolute; top:16px; right:16px; border:none; background:var(--raise); color:var(--muted);
    width:32px; height:32px; border-radius:8px; cursor:pointer; font-size:16px; line-height:1; }
  .dr-close:hover{ color:var(--ink); }
  .dr-kind{ font:600 10.5px/1 var(--sans); letter-spacing:.1em; text-transform:uppercase; color:var(--accent); }
  .dr-title{ font-family:var(--serif); font-size:23px; font-weight:600; margin:8px 0 2px; letter-spacing:-.01em; }
  .dr-subtitle{ font:13px/1.4 var(--sans); color:var(--muted); }
  .dr-facts{ margin:20px 0 0; }
  .dr-fact{ display:flex; justify-content:space-between; gap:16px; padding:11px 0; border-top:1px solid var(--line); }
  .dr-fact:first-child{ border-top:none; }
  .dr-fact dt{ font:12px/1.4 var(--sans); color:var(--muted); }
  .dr-fact dd{ margin:0; font:13px/1.4 var(--sans); color:var(--ink); text-align:right; font-weight:500; }
  .dr-fact dd.mono{ font-family:var(--mono); font-variant-numeric:tabular-nums; }
  .dr-sec{ font:600 10px/1 var(--sans); letter-spacing:.1em; text-transform:uppercase; color:var(--muted); margin:22px 0 10px; }
  .dr-link{ display:flex; align-items:center; gap:8px; padding:10px 12px; background:var(--raise); border:1px solid var(--line); border-radius:10px; margin-bottom:8px; font-size:13px; }
  .dr-link b{ font-weight:600; } .dr-link .r{ margin-left:auto; font:11px/1 var(--mono); color:var(--muted); }
  .dr-note{ font:12.5px/1.5 var(--sans); color:var(--ink); background:var(--accent-soft); border-radius:10px; padding:12px 14px; margin-top:18px; }
  .dr-hint{ font:11.5px/1.45 var(--sans); color:var(--faint); text-align:center; margin-top:20px; font-style:italic; }
  .dr-back{ font:600 12px/1 var(--sans); color:var(--accent); background:none; border:none; cursor:pointer; padding:4px 0; margin-bottom:6px; display:inline-flex; align-items:center; gap:5px; }
  .dr-back:hover{ color:var(--accent-ink); }
  #drList{ margin-top:18px; }
  .dr-listrow{ display:flex; align-items:center; gap:10px; width:100%; text-align:left; font:inherit; color:inherit;
    background:var(--raise); border:1px solid var(--line); border-radius:10px; padding:12px 13px; margin-bottom:8px; cursor:pointer;
    transition:border-color .12s ease, transform .12s ease; }
  .dr-listrow:hover{ border-color:var(--accent); transform:translateY(-1px); }
  .dr-listrow:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
  .dl-main{ display:flex; flex-direction:column; gap:2px; min-width:0; }
  .dl-name{ font-family:var(--serif); font-weight:600; font-size:14px; }
  .dl-meta{ font:11.5px/1.3 var(--sans); color:var(--muted); }
  .dl-amt{ margin-left:auto; font:12.5px/1 var(--mono); color:var(--accent-ink); font-variant-numeric:tabular-nums; white-space:nowrap; }

  @media (max-width:640px){
    .tiles{ grid-template-columns:1fr 1fr; } .masthead{ flex-direction:column; align-items:flex-start; } .mast-date{ text-align:left; }
    .sb-row{ grid-template-columns:80px 1fr 96px; gap:10px; } .rec-row{ grid-template-columns:1fr 90px 66px; gap:10px; }
  }
  @media (prefers-reduced-motion:reduce){ *{ transition:none !important; animation:none !important; } }
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
  <header class="masthead">
    <div><span class="kicker">Dashboard</span><h1 class="mast-title">{{WORKSPACE}}</h1></div>
    <div class="mast-date">{{MAST_DATE}}</div>
  </header>

  <div class="toolbar">
    <div class="search" id="searchBox">
      <input id="q" type="search" placeholder="Search deals &amp; people&hellip;" autocomplete="off" aria-label="Search deals and people">
      <button class="search-clear" id="qClear" aria-label="Clear search">&#10005;</button>
    </div>
  </div>

  <input class="tabswitch" type="radio" name="tab" id="t-focus" checked>
  <input class="tabswitch" type="radio" name="tab" id="t-pipe">
  <input class="tabswitch" type="radio" name="tab" id="t-ppl">
  <input class="tabswitch" type="radio" name="tab" id="t-mom">
  <nav class="tabs" role="tablist">
    <label for="t-focus">Focus <span class="tcount">{{TAB_FOCUS_N}}</span></label>
    <label for="t-pipe">Pipeline <span class="tcount">{{TAB_PIPE_N}}</span></label>
    <label for="t-ppl">People <span class="tcount">{{TAB_PPL_N}}</span></label>
    <label for="t-mom">Momentum</label>
  </nav>

  <div class="panels">
    <section class="panel panel-focus">
      <p class="brief">{{BRIEF}}</p>
      <h2 class="sec-title">Needs you now</h2>
      <div class="actions">{{ACTIONS}}</div>
      {{WON_STRIP}}
    </section>

    <section class="panel panel-pipe">
      <div class="tiles">{{TILES}}</div>
      <h2 class="sec-title mt">Pipeline by stage</h2>
      <div class="stagebars">{{STAGEBARS}}</div>
      <h2 class="sec-title mt">Open deals</h2>
      <div class="board" id="board">{{BOARD}}</div>
      <p class="empty-msg" id="emptyPipe">No deals match &ldquo;<span class="qecho"></span>&rdquo;.</p>
    </section>

    <section class="panel panel-ppl">
      <h2 class="sec-title">Last contact <button class="filterbtn" id="filterQuiet" aria-pressed="false">Only gone quiet</button></h2>
      <p class="sec-note">Recency by last-interaction date. Fresh &rarr; cooling &rarr; gone quiet.</p>
      <div class="rec" id="recList">{{PEOPLE_ROWS}}</div>
      <div class="rec-legend">
        <span><i class="dot" style="background:var(--accent)"></i> Fresh &lt; 7 days</span>
        <span><i class="dot" style="background:var(--cool)"></i> Cooling 1&ndash;3 wks</span>
        <span><i class="dot" style="background:var(--warn)"></i> Gone quiet &gt; 3 wks</span>
        <span><i class="dot" style="background:var(--line-strong)"></i> No contact yet</span>
      </div>
      <p class="empty-msg" id="emptyPpl">No one matches &ldquo;<span class="qecho"></span>&rdquo;.</p>
    </section>

    <section class="panel panel-mom">
      <p class="sec-note" style="margin-top:0">The trend line is illustrative until there's enough history; won totals are your real closed deals.</p>
      <div class="mom-grid">
        {{MOMENTUM}}
        <div class="card">
          <div class="chart-head"><h4>Open pipeline</h4>
            <div class="rangebtns"><button data-range="4">4w</button><button data-range="8" aria-pressed="true">8w</button><button data-range="13">13w</button></div>
          </div>
          <div class="chart-holder" id="chartHolder">
            <svg class="chart" id="chart" viewBox="0 0 320 120" preserveAspectRatio="none" role="img" aria-label="Open pipeline value over time">
              <line class="grid" x1="0" y1="30" x2="320" y2="30"></line>
              <line class="grid" x1="0" y1="70" x2="320" y2="70"></line>
              <line class="grid" x1="0" y1="110" x2="320" y2="110"></line>
              <path class="area" id="cArea"></path>
              <path class="line" id="cLine"></path>
              <line class="vline" id="cVline" x1="0" y1="0" x2="0" y2="120" style="opacity:0"></line>
              <circle class="dot" id="cEnd" r="3.5"></circle>
              <circle class="hl" id="cHl" r="3.5" style="opacity:0"></circle>
            </svg>
            <div class="tip" id="tip"></div>
          </div>
          <div class="caxis"><span id="axL"></span><span id="axR"></span></div>
        </div>
      </div>
    </section>
  </div>
</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" role="dialog" aria-modal="true" aria-labelledby="drTitle">
  <button class="dr-close" id="drClose" aria-label="Close">&#10005;</button>
  <button class="dr-back" id="drBack" style="display:none">&larr; Back</button>
  <div class="dr-kind" id="drKind"></div>
  <h2 class="dr-title" id="drTitle"></h2>
  <div class="dr-subtitle" id="drSub"></div>
  <div id="drList"></div>
  <dl class="dr-facts" id="drFacts"></dl>
  <div id="drLinks"></div>
  <div class="dr-note" id="drNote"></div>
  <p class="dr-hint" id="drHint">To act on this &mdash; log a note, move the stage, draft the follow-up &mdash; just ask Claude in the chat.</p>
</aside>

<script>
(function(){
  "use strict";

  (function(){
    var root=document.documentElement;
    var tbtns=Array.prototype.slice.call(document.querySelectorAll(".themebar button"));
    function media(){ return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
    function apply(t){ root.setAttribute("data-theme",t);
      tbtns.forEach(function(b){ b.setAttribute("aria-pressed", b.getAttribute("data-set")===t ? "true":"false"); }); }
    apply(root.getAttribute("data-theme") || media());
    tbtns.forEach(function(b){ b.addEventListener("click",function(){ apply(b.getAttribute("data-set")); }); });
  })();

  var REC = {{REC_JSON}};
  var LISTS = {{LISTS_JSON}};
  var SERIES = {{SERIES_JSON}};
  var LABELS = {{LABELS_JSON}};

  var $=function(s,r){return (r||document).querySelector(s);};
  var $$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));};

  var drawer=$("#drawer"), scrim=$("#scrim"), lastFocus=null;
  function fact(f){ return "<div class='dr-fact'><dt>"+f[0]+"</dt><dd class='"+(f[2]||"")+"'>"+f[1]+"</dd></div>"; }
  function link(l){ return "<div class='dr-link'><b>"+l[0]+"</b><span class='r'>"+l[1]+"</span><span>"+(l[2]||"")+"</span></div>"; }
  function recordMode(isRecord){
    ["#drFacts","#drLinks","#drNote","#drHint"].forEach(function(s){ $(s).style.display=isRecord?"":"none"; });
    $("#drList").style.display=isRecord?"none":"";
  }
  function ensureOpen(){ if(!drawer.classList.contains("on")){ lastFocus=document.activeElement; }
    drawer.classList.add("on"); scrim.classList.add("on"); $("#drClose").focus(); }
  function openRec(id, backKey){ var r=REC[id]; if(!r) return;
    ensureOpen(); recordMode(true);
    var back=$("#drBack");
    if(backKey && LISTS[backKey]){ back.style.display=""; back.textContent="← "+LISTS[backKey].title; back.onclick=function(){ openList(backKey); }; }
    else back.style.display="none";
    $("#drKind").textContent=r.kind; $("#drTitle").textContent=r.title; $("#drSub").textContent=r.sub;
    $("#drFacts").innerHTML=(r.facts||[]).map(fact).join("");
    $("#drLinks").innerHTML=(r.links&&r.links.length?"<div class='dr-sec'>Linked</div>"+r.links.map(link).join(""):"");
    $("#drNote").textContent=r.note||"";
  }
  function openList(key){ var L=LISTS[key]; if(!L) return;
    ensureOpen(); recordMode(false);
    $("#drBack").style.display="none";
    $("#drKind").textContent=L.kind; $("#drTitle").textContent=L.title; $("#drSub").textContent=L.sub;
    $("#drList").innerHTML=(L.rows||[]).map(function(r){
      return "<button class='dr-listrow' data-rec='"+r.id+"'><span class='dl-main'><span class='dl-name'>"+r.name+"</span><span class='dl-meta'>"+r.meta+"</span></span><span class='dl-amt'>"+r.amt+"</span></button>";
    }).join("");
    $$("#drList .dr-listrow").forEach(function(b){ b.addEventListener("click",function(){ openRec(b.getAttribute("data-rec"), key); }); });
  }
  function closeRec(){ drawer.classList.remove("on"); scrim.classList.remove("on"); if(lastFocus) lastFocus.focus(); }
  $$(".rowlink").forEach(function(el){
    if(el.tagName!=="BUTTON"){ el.setAttribute("tabindex","0"); el.setAttribute("role","button"); }
    el.addEventListener("click",function(){ openRec(el.getAttribute("data-rec")); });
    el.addEventListener("keydown",function(e){ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); openRec(el.getAttribute("data-rec")); }});
  });
  $$("[data-list]").forEach(function(el){ el.addEventListener("click",function(){ openList(el.getAttribute("data-list")); }); });
  $("#drClose").addEventListener("click",closeRec); scrim.addEventListener("click",closeRec);
  document.addEventListener("keydown",function(e){ if(e.key==="Escape") closeRec(); });

  var q=$("#q"), sb=$("#searchBox");
  function applySearch(){
    var term=q.value.trim().toLowerCase();
    sb.classList.toggle("has-val",!!term);
    $$(".qecho").forEach(function(n){ n.textContent=q.value; });
    [["pipe","emptyPipe"],["ppl","emptyPpl"]].forEach(function(p){
      var rows=$$(".panel-"+p[0]+" [data-search]"), shown=0;
      rows.forEach(function(r){ var hit=!term||r.getAttribute("data-search").indexOf(term)>-1;
        r.style.display=hit?"":"none"; if(hit) shown++; });
      $("#"+p[1]).style.display=(term&&shown===0)?"block":"none";
    });
    $$("#board .col").forEach(function(col){
      var vis=$$(".deal",col).filter(function(d){return d.style.display!=="none";}).length;
      $(".col-count",col).textContent=vis;
    });
  }
  q.addEventListener("input",applySearch);
  $("#qClear").addEventListener("click",function(){ q.value=""; applySearch(); q.focus(); });

  var fq=$("#filterQuiet");
  fq.addEventListener("click",function(){
    var on=fq.getAttribute("aria-pressed")!=="true"; fq.setAttribute("aria-pressed",on?"true":"false");
    $$("#recList .rec-row").forEach(function(r){ r.style.display=(!on||r.getAttribute("data-quiet")==="1")?"":"none"; });
  });

  var W=320,H=120,PAD=6, pts=[];
  function buildChart(range){
    var s=SERIES[range]; if(!s||!s.length) return;
    var max=Math.max.apply(null,s), min=Math.min.apply(null,s), span=(max-min)||1;
    pts=s.map(function(v,i){ var x=(i/(s.length-1))*W; var y=H-PAD-((v-min)/span)*(H-2*PAD); return {x:x,y:y,v:v}; });
    var d=pts.map(function(p,i){ return (i?"L":"M")+p.x.toFixed(1)+","+p.y.toFixed(1); }).join(" ");
    $("#cLine").setAttribute("d",d); $("#cArea").setAttribute("d",d+" L"+W+","+H+" L0,"+H+" Z");
    var last=pts[pts.length-1]; $("#cEnd").setAttribute("cx",last.x); $("#cEnd").setAttribute("cy",last.y);
    var lab=LABELS[range]||["",""];
    $("#axL").textContent=lab[0]; $("#axR").textContent=lab[1]+" · $"+s[s.length-1]+"k";
  }
  $$(".rangebtns button").forEach(function(b){
    b.addEventListener("click",function(){
      $$(".rangebtns button").forEach(function(x){ x.setAttribute("aria-pressed","false"); });
      b.setAttribute("aria-pressed","true"); buildChart(b.getAttribute("data-range"));
    });
  });
  var holder=$("#chartHolder"), svg=$("#chart"), tip=$("#tip"), hl=$("#cHl"), vline=$("#cVline");
  function moveTip(clientX){
    if(!pts.length) return;
    var box=svg.getBoundingClientRect(); var rel=(clientX-box.left)/box.width; rel=Math.max(0,Math.min(1,rel));
    var idx=Math.round(rel*(pts.length-1)), p=pts[idx];
    var px=(p.x/W)*box.width, py=(p.y/H)*box.height;
    hl.style.opacity=1; hl.setAttribute("cx",p.x); hl.setAttribute("cy",p.y);
    vline.style.opacity=.7; vline.setAttribute("x1",p.x); vline.setAttribute("x2",p.x);
    tip.classList.add("on"); tip.style.left=px+"px"; tip.style.top=py+"px"; tip.textContent="$"+p.v+"k";
  }
  holder.addEventListener("mousemove",function(e){ moveTip(e.clientX); });
  holder.addEventListener("mouseleave",function(){ tip.classList.remove("on"); hl.style.opacity=0; vline.style.opacity=0; });
  holder.addEventListener("touchmove",function(e){ if(e.touches[0]) moveTip(e.touches[0].clientX); },{passive:true});
  buildChart("8");
})();
</script>
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
