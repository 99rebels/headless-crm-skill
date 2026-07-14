---
name: crm-dashboard
description: >-
  Show the current CRM pipeline and the relationships that need a nudge, as a clean read-only view
  rendered on demand. Use when the user asks to see their pipeline or a CRM dashboard, "what's in my
  pipeline", "how's my pipeline looking", "show me my deals / deal board", "who do I need to follow
  up with / who's gone quiet / who should I chase", or wants a pipeline or relationship overview.
  Read-only — it shows current state and changes nothing. This does NOT read email or add data — to
  update the CRM from email/calendar, use the crm-enrichment skill instead.
---

# CRM pipeline dashboard

Renders a calm, at-a-glance view of the CRM **on demand** — the open pipeline (deals by stage) plus
the relationships that need a nudge — as a self-contained HTML artifact. It is the read-only
counterpart to the enrichment digest: enrichment keeps the data *current*, this shows the data. It
runs **client-side**, reads the CRM via the MCP read tools, and never writes.

**Script-heavy + facts-from-the-tool:** the **facts** come from one deterministic MCP call
(`get_pipeline_summary`); `scripts/render_dashboard.py` renders them (identical every run, no
hand-authored HTML). The model's *only* judgement is the **Focus** list — and even that is anchored
by the tool's computed `signals`, not derived from scratch. This is deliberate: the summary tool
exists so every model shows **identical facts** (pipeline value, counts, stage buckets, recency),
instead of each re-deriving them and disagreeing.

The rendered page has **four tabs** (Focus / Pipeline / People / Momentum), an in-page light/dark
toggle, live search, and clickable deals/people that open a detail drawer. All of that is
**presentation-only** — the artifact is a sandbox with no network. Anything that *changes* the CRM
happens back in the chat via the MCP tools; the drawer says so.

## Steps

### 1 — Get the facts (ONE call)
Call **`get_pipeline_summary`**. It returns the whole factual half of the dashboard, computed
server-side: `stats` (open_pipeline_value, open_deals, relationships, unstaged_deals, mixed_currency),
`stages` (deals bucketed by stage **including an "Unstaged" bucket**), `people` (roster with real
`days`-since-contact, null ⇒ no contact), `won`, and `signals` (attention flags per record id). Each
deal/person also carries a **`summary_line`** — a one-line "where things stand" headline trimmed from
its living summary — which the renderer shows in the **click-to-drill drawer** (the *full* living
summary isn't here; it's read on demand via `get_deal`/`get_contact` or the deep view). Do **not**
re-compute any of these from `find_deals`/`find_contacts` — that's what used to make different models
show different numbers.

### 2 — Add the Focus list (the only judgement) and render
Pass the tool's output straight through, and add two things:
- `focus`: the ranked "needs you now" list, built **from `signals`** (don't invent). Map each signal
  to a card: `awaiting_close` → `type:"opportunity"` ("verbal yes — send the paperwork");
  `new_no_interaction` → `type:"follow"` ("warm lead, book a call"); `is_unstaged` →
  `type:"follow"`, `tag:"Unstaged"` ("give it a stage"); `quiet_days` → `type:"cool"` ("check in").
  Each card: `ref` (the record id from the tool), `name`, `type`, optional `meta`/`tag`, a one-line
  `why`, and a concrete `action`. Rank most-urgent first; keep it ~5 max, calm.
- `weekday` + `generated_label` (today's date, for the masthead).

Then `python3 scripts/render_dashboard.py <state.json> dashboard.html` and show it (interactive
artifact; theme-aware). The full input contract is documented at the top of the script.
`momentum` is optional (illustrative trend chart — say so until a workspace has real history).

### 3 — Offer next steps
Offer to act on a Focus item (draft the follow-up, move a stage, stage the unstaged deal) — but
that's a separate MCP write step; the dashboard itself only displays.

## Notes
- **Read-only render.** The dashboard makes no `create_*`/`update_*` calls; regenerate on demand.
- Honesty: null `last_interaction_at` shows "no contact logged" and fires **no** nudge — never invent
  recency. Unstaged/mixed-currency/orphan-stage cases are handled by the tool, not guessed.
- Vocabulary (stages, order, lifecycle, self-emails, currency) lives in `workspace.settings` — a
  config change, never a code change.
- Empty pipeline / no focus render gracefully ("Nothing here" / "Nothing needs you right now").
- Keep the design identity intact — it's shared with the enrichment digest (the "Ledger" look).
