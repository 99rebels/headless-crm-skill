#!/usr/bin/env python3
"""
render_preview.py — render a write-plan as a self-contained HTML approval preview, in the shared
"Ledger" identity. ONE renderer for BOTH sources of the import skill: a CSV/spreadsheet file
(build_import.py) and a connected Attio workspace (build_from_attio.py). Purpose-built for a BULK
review (not the per-item scrutiny the enrichment digest is for): summary tiles, a "how I read your
columns / how I mapped your Attio fields" card (the thing you're really approving), then tab-switched
compact tables — People / Companies / Deals.

The only thing that differs between the two sources is the user-facing COPY (file/rows/import vs
Attio/records/migrate); the layout, tables, and CSS are identical. The renderer picks the copy from
`digest.source_kind` ("csv" default, or "attio"), so build_import.py needs no change.

Takes the builder's output (the whole object, or just its `digest` block). Approval happens in the
conversation, not here (an artifact can't call the CRM tools back).

Usage:
    python3 render_preview.py plan.json out.html
    cat plan.json | python3 render_preview.py - out.html
"""

import html
import json
import sys

VALUE_ALIAS_CAP = 8  # translated-label chips shown before "+N more"

# Source-specific copy. Everything else (layout/CSS/tables) is identical across sources.
COPY = {
    "csv": {
        "kicker": "Import preview",
        "h1": "Ready to import into your CRM",
        "read_verb": "Read", "unit": "row", "source_prep": "from",
        "map_h2": "How I read your columns",
        "map_left": "Column in your file",
        "norm_label": "I also translated the labels in your file to your CRM&rsquo;s own terms:",
        "tabs_aria": "Records to import",
        "more_verb": "imported",
        "empty_where": "this file",
        "approve_verb": "import",
        "reused_line": "Existing people or companies with the same email or domain are reused, never duplicated.",
    },
    "attio": {
        "kicker": "Migration preview",
        "h1": "Ready to bring your Attio into this CRM",
        "read_verb": "Pulled", "unit": "record", "source_prep": "from",
        "map_h2": "How I mapped your Attio fields",
        "map_left": "Field in Attio",
        "norm_label": "I also translated your Attio stage names to your CRM&rsquo;s own terms:",
        "tabs_aria": "Records to migrate",
        "more_verb": "migrated",
        "empty_where": "this pull",
        "approve_verb": "migrate",
        "reused_line": "Existing people or companies with the same email or domain are reused, never duplicated.",
    },
}
C = COPY["csv"]  # active copy; render() sets this from digest.source_kind


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


# ── pieces ─────────────────────────────────────────────────────────────────────────────
def render_stats(counts: dict) -> str:
    tiles = [
        ("contacts", "People", ""),
        ("organizations", "Companies", ""),
        ("deals", "Deals", ""),
        ("links", "Links", "people · companies · deals"),
    ]
    out = ""
    for key, label, sub in tiles:
        dim = " dim" if key == "links" else ""
        small = f"<small>{esc(sub)}</small>" if sub else ""
        out += (
            f"<div class='stat{dim}'><div class='n'>{counts.get(key, 0)}</div>"
            f"<div class='l'>{esc(label)}{small}</div></div>"
        )
    return out


def render_mapping(mapping: list, skipped: list, aliases: list) -> str:
    rows = ""
    for m in mapping:
        src = esc(" + ".join(m.get("sources", []))).replace(" ", "&nbsp;")
        rows += (
            f"<div class='map'><span class='src'>{src}</span>"
            f"<span class='to'>&rarr;</span><span class='fld'>{esc(m.get('field'))}</span></div>"
        )
    for col in skipped:
        rows += (
            f"<div class='map skip'><span class='src'>{esc(col).replace(' ', '&nbsp;')}</span>"
            "<span class='to'>&rarr;</span><span class='fld'>left out</span></div>"
        )

    norm = ""
    if aliases:
        chips = ""
        for a in aliases[:VALUE_ALIAS_CAP]:
            chips += (
                f"<span class='nchip'>{esc(a['from']).replace(' ', '&nbsp;')} "
                f"<span class='na'>&rarr;</span> <b>{esc(a['to'])}</b></span>"
            )
        more = len(aliases) - VALUE_ALIAS_CAP
        if more > 0:
            chips += f"<span class='nmore'>+{more} more</span>"
        norm = (
            f"<div class='norm'><span class='nlabel'>{C['norm_label']}</span>"
            f"<div class='nchips'>{chips}</div></div>"
        )

    return (
        "<section class='card'>"
        f"<h2>{esc(C['map_h2'])} <span class='hint'>correct me before you approve</span></h2>"
        f"<div class='maphdr'><span>{esc(C['map_left'])}</span><span class='to'>&rarr;</span>"
        "<span>Field in your CRM</span></div>"
        f"<div class='maps'>{rows}</div>{norm}"
        "</section>"
    )


def render_tabs(counts: dict) -> str:
    def tab(panel, label, n, sel):
        s = "true" if sel else "false"
        return (
            f"<button class='tab' role='tab' aria-selected='{s}' data-panel='{panel}'>"
            f"{esc(label)} <span class='c'>{n}</span></button>"
        )
    return (
        f"<div class='tabs' role='tablist' aria-label='{esc(C['tabs_aria'])}'>"
        + tab("people", "People", counts.get("contacts", 0), True)
        + tab("companies", "Companies", counts.get("organizations", 0), False)
        + tab("deals", "Deals", counts.get("deals", 0), False)
        + "</div>"
    )


def _more_row(shown: int, total: int, cols: int) -> str:
    extra = total - shown
    if extra <= 0:
        return ""
    return f"<tr class='more'><td colspan='{cols}'>+{extra} more will be {C['more_verb']}</td></tr>"


def render_people(digest: dict) -> str:
    counts = digest.get("counts", {})
    people = digest.get("contacts", []) or []
    body = ""
    for c in people:
        chip = f"<span class='chip life'>{esc(c['lifecycle'])}</span>" if c.get("lifecycle") else ""
        body += (
            "<tr>"
            f"<td><div class='who'><span class='ava'>{esc(c.get('initials'))}</span>"
            f"<span class='nm'>{esc(c.get('name'))}</span></div></td>"
            f"<td class='role'>{esc(c.get('title'))}</td>"
            f"<td class='mail'>{esc(c.get('email'))}</td>"
            f"<td>{chip}</td></tr>"
        )
    body += _more_row(len(people), counts.get("contacts", len(people)), 4)
    pwd = digest.get("aggregates", {}).get("people_with_deal", 0)
    foot_r = f"<span>{pwd} linked to a deal</span>" if pwd else "<span></span>"
    foot = (
        f"<div class='tblfoot'><span><b>{counts.get('contacts', 0)}</b> people</span>{foot_r}</div>"
    )
    if not people:
        body = f"<tr><td colspan='4' class='empty'>No people in {C['empty_where']}.</td></tr>"
        foot = ""
    return (
        "<div class='panel on' id='people' role='tabpanel'><div class='tblwrap'><table>"
        "<thead><tr><th>Name</th><th>Title</th><th>Email</th><th>Lifecycle</th></tr></thead>"
        f"<tbody>{body}</tbody></table>{foot}</div></div>"
    )


def render_companies(digest: dict) -> str:
    counts = digest.get("counts", {})
    orgs = digest.get("organizations", []) or []
    body = ""
    for o in orgs:
        dom = f"<span class='dom'>{esc(o.get('domain'))}</span>" if o.get("domain") else "<span class='role'>&mdash;</span>"
        body += (
            "<tr>"
            f"<td><div class='who'><span class='mono-ava'>{esc(o.get('initial'))}</span>"
            f"<span class='nm'>{esc(o.get('name'))}</span></div></td>"
            f"<td>{dom}</td></tr>"
        )
    body += _more_row(len(orgs), counts.get("organizations", len(orgs)), 2)
    foot = f"<div class='tblfoot'><span><b>{counts.get('organizations', 0)}</b> companies</span></div>"
    if not orgs:
        body = f"<tr><td colspan='2' class='empty'>No companies in {C['empty_where']}.</td></tr>"
        foot = ""
    return (
        "<div class='panel' id='companies' role='tabpanel'><div class='tblwrap'><table>"
        "<thead><tr><th>Company</th><th>Domain</th></tr></thead>"
        f"<tbody>{body}</tbody></table>{foot}</div></div>"
    )


def render_deals(digest: dict) -> str:
    counts = digest.get("counts", {})
    deals = digest.get("deals", []) or []
    agg = digest.get("aggregates", {})
    body = ""
    for d in deals:
        status = d.get("status", "open")
        cls = status if status in ("won", "lost") else "open"
        amt = f"<td class='num amt'>{esc(d.get('amount_display'))}</td>" if d.get("amount_display") else "<td class='num role'>&mdash;</td>"
        body += (
            "<tr>"
            f"<td class='nm'>{esc(d.get('name'))}</td>"
            f"{amt}"
            f"<td><span class='chip st {cls}'>{esc(d.get('stage'))}</span></td></tr>"
        )
    body += _more_row(len(deals), counts.get("deals", len(deals)), 3)
    foot = (
        f"<div class='tblfoot'><span><b>{esc(agg.get('open_display', ''))}</b> open pipeline"
        f" · <b>{esc(agg.get('won_display', ''))}</b> won</span>"
        f"<span>{counts.get('deals', 0)} deals</span></div>"
    )
    if not deals:
        body = f"<tr><td colspan='3' class='empty'>No deals in {C['empty_where']}.</td></tr>"
        foot = ""
    return (
        "<div class='panel' id='deals' role='tabpanel'><div class='tblwrap'><table>"
        "<thead><tr><th>Deal</th><th class='num'>Amount</th><th>Stage</th></tr></thead>"
        f"<tbody>{body}</tbody></table>{foot}</div></div>"
    )


def render_note(notes: list) -> str:
    if not notes:
        return ""
    items = "".join(f"<li>{esc(n)}</li>" for n in notes)
    return (
        "<div class='note'><span class='ic'>!</span><div class='t'>"
        "<b>A few values need your eye</b> — kept as notes, the field left blank so nothing is guessed:"
        f"<ul>{items}</ul></div></div>"
    )


def render(data: dict) -> str:
    global C
    if "digest" in data:
        data = data["digest"]
    C = COPY.get(data.get("source_kind", "csv"), COPY["csv"])
    counts = data.get("counts", {})
    total = counts.get("contacts", 0) + counts.get("organizations", 0) + counts.get("deals", 0)
    all_created = total + counts.get("links", 0)

    rows = data.get("rows_reviewed")
    src = data.get("source_file")
    src_html = f" {C['source_prep']} <span class='file'>{esc(src)}</span>" if src else ""
    unit = C["unit"]
    subline = (
        f"{C['read_verb']} <b>{rows} {unit}{'' if rows == 1 else 's'}</b>{src_html} — nothing is saved until you approve."
        if rows is not None else
        f"{C['read_verb']} your {'file' if C is COPY['csv'] else 'records'}{src_html} — nothing is saved until you approve."
    )

    if total == 0:
        body = (
            f"<div class='note'><span class='ic'>!</span><div class='t'>Nothing to {C['approve_verb']} — no "
            "records mapped to a person, company, or deal. Check the mapping and try again.</div></div>"
        )
        approve = ""
    else:
        body = (
            f"<div class='stats'>{render_stats(counts)}</div>"
            + render_mapping(data.get("mapping", []), data.get("skipped_columns", []), data.get("value_aliases", []))
            + render_tabs(counts)
            + render_people(data) + render_companies(data) + render_deals(data)
            + render_note(data.get("notes", []) or [])
        )
        approve = (
            "<div class='approve'><div class='lead'><span class='dot'></span>Nothing is saved until you approve</div>"
            f"<div class='how'>Reply <span class='say'>{C['approve_verb']}</span> to create all {all_created} records — "
            "or tell me what to change (e.g. <span class='say'>skip the deals</span>, or fix the mapping above). "
            f"{C['reused_line']}</div></div>"
        )

    return (TEMPLATE
            .replace("{{TITLE}}", esc(C["kicker"]))
            .replace("{{KICKER}}", esc(C["kicker"]))
            .replace("{{H1}}", esc(C["h1"]))
            .replace("{{SUBLINE}}", subline).replace("{{BODY}}", body).replace("{{APPROVE}}", approve))


TEMPLATE = """<!doctype html>
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
    --clay:#9d4a3b; --clay-soft:#f0e2dc;
    --shadow:0 1px 2px rgba(60,48,24,.05), 0 4px 16px rgba(60,48,24,.06);
    --serif:"Iowan Old Style",Palatino,"Palatino Linotype",Georgia,serif;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:"SF Mono",ui-monospace,Menlo,Consolas,"Liberation Mono",monospace;
  }
  @media (prefers-color-scheme: dark){ :root{
    --bg:#14120d; --surface:#1d1a13; --raise:#242016; --ink:#ece6d8; --muted:#9c9280; --faint:#766e5e;
    --line:#2b2619; --line-strong:#3a3324; --accent:#4fae90; --accent-ink:#c6e9de; --accent-soft:#183028;
    --warn:#d6a34d; --warn-ink:#e8c485; --warn-soft:#2a2413; --warn-line:#403413;
    --clay:#cf7462; --clay-soft:#331f19;
    --shadow:0 1px 2px rgba(0,0,0,.34), 0 6px 18px rgba(0,0,0,.34);
  }}
  :root[data-theme="light"]{
    --bg:#f3f0e8; --surface:#fffdf7; --raise:#fbf8f1; --ink:#221f18; --muted:#77705f; --faint:#9a927f;
    --line:#e7e0d1; --line-strong:#d8cfba; --accent:#216b57; --accent-ink:#164d3d; --accent-soft:#e3efe9;
    --warn:#8f6412; --warn-ink:#6f4e0e; --warn-soft:#f4ecd7; --warn-line:#e6d3a6;
    --clay:#9d4a3b; --clay-soft:#f0e2dc;
    --shadow:0 1px 2px rgba(60,48,24,.05), 0 4px 16px rgba(60,48,24,.06);
  }
  :root[data-theme="dark"]{
    --bg:#14120d; --surface:#1d1a13; --raise:#242016; --ink:#ece6d8; --muted:#9c9280; --faint:#766e5e;
    --line:#2b2619; --line-strong:#3a3324; --accent:#4fae90; --accent-ink:#c6e9de; --accent-soft:#183028;
    --warn:#d6a34d; --warn-ink:#e8c485; --warn-soft:#2a2413; --warn-line:#403413;
    --clay:#cf7462; --clay-soft:#331f19;
    --shadow:0 1px 2px rgba(0,0,0,.34), 0 6px 18px rgba(0,0,0,.34);
  }

  *{ box-sizing:border-box; }
  body{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 var(--sans); -webkit-font-smoothing:antialiased; }
  .wrap{ max-width:720px; margin:0 auto; padding:30px 20px 44px; }

  .topbar{ display:flex; justify-content:flex-end; margin-bottom:12px; }
  .themebar{ display:inline-flex; background:var(--raise); border:1px solid var(--line); border-radius:999px; padding:3px; gap:2px; }
  .themebar button{ font:600 11px/1 var(--sans); color:var(--muted); background:none; border:none; border-radius:999px; padding:6px 11px; cursor:pointer; }
  .themebar button[aria-pressed="true"]{ color:var(--accent-ink); background:var(--surface); box-shadow:var(--shadow); }
  .themebar button:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }

  header{ margin-bottom:22px; }
  .kicker{ font:600 11px/1 var(--sans); letter-spacing:.16em; text-transform:uppercase; color:var(--accent); }
  h1{ font-family:var(--serif); font-weight:600; font-size:29px; line-height:1.05; margin:9px 0 0; letter-spacing:-.01em; text-wrap:balance; }
  .subline{ font-size:13.5px; color:var(--muted); margin-top:8px; }
  .subline b{ color:var(--ink); font-weight:600; }
  .subline .file{ font-family:var(--mono); font-size:12.5px; color:var(--accent-ink); background:var(--accent-soft); border-radius:6px; padding:2px 7px; }

  .stats{ display:grid; grid-template-columns:repeat(4,1fr); gap:11px; margin:20px 0 14px; }
  .stat{ background:var(--surface); border:1px solid var(--line); border-radius:13px; box-shadow:var(--shadow); padding:15px 16px; position:relative; overflow:hidden; }
  .stat::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--accent); opacity:.85; }
  .stat.dim::before{ background:var(--line-strong); }
  .stat .n{ font-family:var(--serif); font-weight:600; font-size:30px; line-height:1; font-variant-numeric:tabular-nums; letter-spacing:-.02em; }
  .stat .l{ font:600 10.5px/1.3 var(--sans); letter-spacing:.09em; text-transform:uppercase; color:var(--muted); margin-top:8px; }
  .stat .l small{ display:block; font-weight:400; letter-spacing:0; text-transform:none; font-size:11px; color:var(--faint); margin-top:2px; }

  .card{ background:var(--surface); border:1px solid var(--line); border-radius:14px; box-shadow:var(--shadow); padding:16px 18px 18px; margin-bottom:14px; }
  .card > h2{ display:flex; align-items:center; gap:9px; margin:2px 0 14px; font:600 10.5px/1 var(--sans); letter-spacing:.12em; text-transform:uppercase; color:var(--accent); }
  .card > h2 .hint{ margin-left:auto; font:400 11px/1 var(--sans); letter-spacing:0; text-transform:none; color:var(--faint); font-style:italic; }
  .maphdr{ display:flex; align-items:center; gap:9px; margin:-4px 0 12px; font:600 10px/1 var(--sans); letter-spacing:.09em; text-transform:uppercase; color:var(--faint); }
  .maphdr .to{ color:var(--accent); font-weight:700; font-size:12px; }
  .maps{ display:grid; grid-template-columns:1fr 1fr; gap:2px 26px; }
  .map{ display:flex; align-items:baseline; gap:9px; padding:6px 0; border-top:1px solid var(--line); }
  .maps .map:nth-child(1), .maps .map:nth-child(2){ border-top:none; }
  .map .src{ font-family:var(--mono); font-size:12px; color:var(--ink); flex:0 0 auto; max-width:47%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .map .to{ color:var(--accent); font-weight:700; flex:0 0 auto; }
  .map .fld{ font-family:var(--serif); font-size:14px; color:var(--ink); }
  .map.skip .src{ color:var(--faint); text-decoration:line-through; }
  .map.skip .fld{ color:var(--faint); font-style:italic; font-family:var(--sans); font-size:12.5px; }
  .norm{ margin-top:14px; padding-top:13px; border-top:1px solid var(--line); }
  .norm .nlabel{ display:block; font:400 12.5px/1.4 var(--sans); color:var(--muted); margin-bottom:10px; }
  .nchips{ display:flex; flex-wrap:wrap; gap:7px; align-items:center; }
  .nchip{ font:500 11.5px/1 var(--mono); color:var(--muted); background:var(--raise); border:1px solid var(--line); border-radius:7px; padding:5px 9px; white-space:nowrap; }
  .nchip .na{ color:var(--accent); font-weight:700; margin:0 4px; }
  .nchip b{ color:var(--accent-ink); font-weight:700; }
  .nmore{ font:500 11.5px/1 var(--sans); color:var(--faint); font-style:italic; }

  .tabs{ display:inline-flex; background:var(--raise); border:1px solid var(--line); border-radius:11px; padding:4px; gap:3px; margin-bottom:12px; }
  .tab{ display:inline-flex; align-items:center; gap:7px; font:600 13px/1 var(--sans); color:var(--muted); background:none; border:none; border-radius:8px; padding:9px 14px; cursor:pointer; }
  .tab .c{ font:600 11px/1 var(--mono); font-variant-numeric:tabular-nums; color:var(--muted); background:var(--surface); border:1px solid var(--line); border-radius:999px; padding:2px 7px; }
  .tab[aria-selected="true"]{ color:var(--accent-ink); background:var(--surface); box-shadow:var(--shadow); }
  .tab[aria-selected="true"] .c{ color:#fff; background:var(--accent); border-color:transparent; }
  .tab:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }

  .panel{ display:none; }
  .panel.on{ display:block; animation:fade .18s ease; }
  @keyframes fade{ from{ opacity:0; transform:translateY(3px); } to{ opacity:1; transform:none; } }

  .tblwrap{ background:var(--surface); border:1px solid var(--line); border-radius:14px; box-shadow:var(--shadow); overflow:hidden; }
  table{ width:100%; border-collapse:collapse; }
  thead th{ font:600 10px/1 var(--sans); letter-spacing:.1em; text-transform:uppercase; color:var(--faint); text-align:left; padding:13px 16px 11px; background:var(--raise); border-bottom:1px solid var(--line); }
  th.num, td.num{ text-align:right; }
  tbody td{ padding:11px 16px; border-top:1px solid var(--line); vertical-align:middle; font-size:14px; }
  tbody tr:first-child td{ border-top:none; }
  tbody tr:hover td{ background:var(--raise); }
  td.empty{ color:var(--faint); font-style:italic; text-align:center; padding:22px 16px; }
  tr.more td{ color:var(--faint); font-style:italic; font-size:13px; text-align:center; background:var(--raise); }
  .nm{ font-family:var(--serif); font-weight:600; font-size:14.5px; color:var(--ink); }
  .role{ color:var(--muted); font-size:13px; }
  .mail{ font-family:var(--mono); font-size:12px; color:var(--muted); }
  .dom{ font-family:var(--mono); font-size:12.5px; color:var(--accent-ink); }
  .amt{ font-family:var(--mono); font-size:13.5px; font-variant-numeric:tabular-nums; color:var(--ink); font-weight:600; }

  .who{ display:flex; align-items:center; gap:11px; }
  .ava{ width:32px; height:32px; flex:none; display:grid; place-items:center; border-radius:999px; font-family:var(--serif); font-weight:600; font-size:12px; background:var(--accent-soft); color:var(--accent-ink); }
  .mono-ava{ width:30px; height:30px; border-radius:8px; background:var(--raise); border:1px solid var(--line-strong); color:var(--ink); display:grid; place-items:center; font-family:var(--serif); font-weight:600; font-size:12px; }

  .chip{ font:600 11px/1.3 var(--sans); border-radius:999px; padding:4px 11px; white-space:nowrap; display:inline-block; }
  .life{ color:var(--muted); background:var(--raise); border:1px solid var(--line-strong); }
  .st.open{ color:var(--accent-ink); background:var(--accent-soft); }
  .st.won{ color:#fff; background:var(--accent); }
  .st.lost{ color:var(--clay); background:var(--clay-soft); border:1px solid var(--clay); }

  .tblfoot{ display:flex; justify-content:space-between; align-items:center; gap:10px; padding:11px 16px; border-top:1px solid var(--line); background:var(--raise); font:12px/1.4 var(--sans); color:var(--muted); }
  .tblfoot b{ font-family:var(--mono); color:var(--ink); font-variant-numeric:tabular-nums; }

  .note{ margin-top:14px; background:var(--warn-soft); border:1px solid var(--warn-line); border-left:4px solid var(--warn); border-radius:12px; padding:13px 16px; display:flex; gap:11px; align-items:flex-start; }
  .note .ic{ color:var(--warn); font-weight:700; }
  .note .t{ font-size:13px; color:var(--warn-ink); line-height:1.5; }
  .note .t b{ font-weight:700; }
  .note .t ul{ margin:7px 0 0; padding-left:18px; }
  .note .t li{ margin:2px 0; }

  .approve{ margin-top:16px; padding:17px 19px; background:var(--surface); border:1px solid var(--line-strong); border-radius:14px; box-shadow:var(--shadow); }
  .approve .lead{ font-family:var(--serif); font-size:16.5px; font-weight:600; display:flex; align-items:center; gap:9px; }
  .approve .dot{ width:8px; height:8px; border-radius:999px; background:var(--accent); flex:none; }
  .approve .how{ font:13.5px/1.55 var(--sans); color:var(--muted); margin-top:7px; }
  .approve .say{ font-family:var(--mono); font-size:12.5px; color:var(--ink); background:var(--raise); border:1px solid var(--line); border-radius:7px; padding:3px 8px; }

  @media (max-width:560px){
    .stats{ grid-template-columns:repeat(2,1fr); }
    .maps{ grid-template-columns:1fr; }
    .maps .map:nth-child(2){ border-top:1px solid var(--line); }
    .mail{ display:none; }
  }
  @media (prefers-reduced-motion:reduce){ *{ animation:none !important; transition:none !important; } }
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
      <span class="kicker">{{KICKER}}</span>
      <h1>{{H1}}</h1>
      <div class="subline">{{SUBLINE}}</div>
    </header>
    {{BODY}}
    {{APPROVE}}
  </div>
  <script>
  (function(){
    var root=document.documentElement;
    var tb=[].slice.call(document.querySelectorAll(".themebar button"));
    function media(){ return matchMedia("(prefers-color-scheme: dark)").matches ? "dark":"light"; }
    function theme(t){ root.setAttribute("data-theme",t);
      tb.forEach(function(b){ b.setAttribute("aria-pressed", b.getAttribute("data-set")===t?"true":"false"); }); }
    theme(root.getAttribute("data-theme")||media());
    tb.forEach(function(b){ b.addEventListener("click",function(){ theme(b.getAttribute("data-set")); }); });
    var tabs=[].slice.call(document.querySelectorAll(".tab"));
    var panels=[].slice.call(document.querySelectorAll(".panel"));
    tabs.forEach(function(t){ t.addEventListener("click",function(){
      tabs.forEach(function(x){ x.setAttribute("aria-selected", x===t?"true":"false"); });
      panels.forEach(function(p){ p.classList.toggle("on", p.id===t.getAttribute("data-panel")); });
    }); });
  })();
  </script>
</body>
</html>"""


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("usage: render_preview.py <plan.json|-> <out.html>")
    src, out = sys.argv[1], sys.argv[2]
    raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(json.loads(raw)))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
