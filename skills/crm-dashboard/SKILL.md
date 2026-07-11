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

**Script-heavy:** the model gathers and shapes the state; `scripts/render_dashboard.py` renders it
deterministically (identical every run, no hand-authored HTML). The model's only judgement is
deriving the "needs a nudge" list.

## Steps

### 1 — Gather (CRM read tools only; no writes)
- `find_deals` — open deals (and, if available, recently won). Note each deal's stage/status/amount.
- `find_organizations`, `find_contacts` — for names, lifecycle, and `last_interaction_at`.
- `find_associations` on each open deal — to attach its org and people (so cards read as
  relationships, not rows).

### 2 — Build the state JSON
Assemble the object documented at the top of `scripts/render_dashboard.py`:
- `stats`: `open_pipeline_value` (sum of open deal amounts), `open_deals`, `relationships`
  (active contacts), `needs_attention` (length of the nudge list).
- `stages`: the **open** pipeline stages **in order** (from `workspace.settings.pipeline` /
  config `vocab.deal_stages`, excluding `won`/`lost`), each with its deals (name, amount, org,
  people, close_date).
- `attention`: the nudge list (see rules below).
- `won`: recently-won deals (optional) — shown as quiet chips.

### 3 — Derive "needs a nudge" (the judgement — keep it short and calm, ~5 max)
A relationship earns a nudge when:
- a deal is in the **latest open stage** (e.g. `verbal`) awaiting an obvious next action
  ("verbal yes — send the paperwork");
- an active contact (client/prospect) has **gone quiet** — `last_interaction_at` older than ~30
  days, or never recorded;
- a **new** contact (recently added lead/prospect) has **no meeting/interaction yet**
  ("warm intro, no meeting booked").
Each nudge: `title` (person), `kind` (their lifecycle), `reason` (the specific next action, in the
user's words), `detail` (the org or deal it's about). Rank most-urgent first. This strip is the
fractional-operator's real pain — dropped relationships — so keep it *actionable and few*, never a
long chore list.

### 4 — Render and show
`python3 scripts/render_dashboard.py <state.json> dashboard.html`, then show `dashboard.html` (it
renders as an artifact; theme-aware, light/dark). Offer to act on a nudge (e.g. draft the follow-up)
— but that's a separate step; the dashboard itself only displays.

## Notes
- **Read-only.** No `create_*` / `update_*` calls. Regenerate on demand for a fresh view.
- Empty pipeline / no nudges render gracefully ("Nothing here" / "You're on top of everyone").
- Stage order and lifecycle vocabulary come from the workspace/config, not hard-coded.
