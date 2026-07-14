---
name: crm-enrichment
description: >-
  Update the CRM from the user's email and calendar. Reads recent Gmail + Google Calendar, extracts
  new contacts, companies, deal signals, and who they've met, dedupes against the CRM, and proposes
  changes for approval — nothing is written until approved. Use when the user wants to catch up /
  update / sync / enrich their CRM from email or calendar, log recent emails or meetings, add new
  people they've been talking to, process their inbox into the CRM, tidy or maintain their CRM, or
  asks "what's new for my CRM" / "anyone new to add". This is the WRITE/ingest side — to only VIEW
  the pipeline without changing anything, use the crm-dashboard skill instead.
---

# CRM enrichment — the self-maintenance loop

Keeps the CRM accurate **without manual data entry**. Runs **client-side** in the user's own Claude,
using their **own connectors** (Gmail, Google Calendar): raw email/event content is read here and
**never leaves for our server** — only the **approved** structured updates are written, via the CRM's
MCP tools. That client-side boundary is a deliberate compliance decision; never send raw email/event
content to the CRM server.

**Architecture — sources feed one shared core.** Each *source* (Gmail, Calendar, and later Slack
etc.) is a thin reader that produces candidate facts. Those candidates flow into a single,
source-agnostic **core** — reconcile → digest → approve → write. This means one deduped review across
all sources, not one per source. Add a source = add a reader; the core is untouched.

**Do the deterministic work in code, reserve the model for judgment.** Filtering, existence-checks,
and rendering are mechanical; only *reading prose/events and extracting facts* and *judging whether
something is a real relationship* need the model. Cheaper and more reliable.

**Prime guardrail — never silently overwrite.** Adding a record, or filling an *empty* field / new
attribute, is low-friction (propose it). Changing an **existing, non-empty** value to something
different is a **conflict**: never write it silently — surface it in the digest's "Needs your call"
section. A confidently-wrong overwrite is the one thing that breaks trust. (Exception: see
`last_interaction_at` below — a more-recent date is an enrichment, not a conflict.)

## Before you start

1. Read `config.json` (fall back to `config.example.json`): `self` (the user's own emails/domains —
   never CRM yourself), `scope` (Gmail lookback + the `crm-processed` watermark label; calendar
   look-back/ahead windows), `ignore` (senders/domains to never add), `vocab` (valid lifecycle/deal
   stages).
2. Confirm the CRM MCP tools are connected (e.g. `find_contacts`). Then use whichever **sources** are
   available — Gmail and/or Google Calendar. If a source's connector is missing, skip that source and
   say so; don't guess.

---

# SOURCES — gather candidate facts (run each available source)

## Source A — Gmail

### A1. Scope (cheap, deterministic: pick emails; don't read bodies yet)
Search Gmail: `newer_than:{scope.lookback} -label:{scope.exclude_label} {scope.gmail_query_extra}`.
From **metadata only** (from / subject / snippet), drop: `self.emails`/`self.domains`, `ignore`
senders/domains, and obvious automated mail (no-reply, receipts, newsletters). Token discipline: only
survivors get their bodies read.

### A2. Classify vs the CRM (cheap DB reads, no tokens)
For each survivor: `find_contacts(email)` / `find_organizations(domain)` → tag KNOWN (update) or NEW
(add). This does **not** exclude unknown senders — discovering new people is half the value; it just
sets create-vs-update and supplies the existing record as context. **Also load existing DEALS** — call
`find_deals` and check the deals already linked to any matched contact/org (`find_associations`) — so a
deal mentioned in a comm can be matched to one that already exists (see the deal read-before-write rule
in C1). Deals have no email/domain key, so this lookup is the only thing standing between "advance the
stage" and "create a duplicate deal."

### A3. Read + extract
`get_thread` on survivors only. Extract concrete, stated facts from the body (see EXTRACT rules
below). Tag each candidate `source: "email"`, with evidence (reason + snippet + from/subject/date).

## Source B — Google Calendar

### B1. Scope
List events in the window: past `{scope.calendar_lookback}` (meetings that happened → who you met)
and next `{scope.calendar_lookahead}` (upcoming meetings → who you're about to meet). Drop events with
no external attendees, and drop the user themselves (`self`).

### B2. Extract from events
For each relevant event, extract from **attendees + title/description**:
- **People:** attendee name + email → contact (dedupe by email as in A2). An attendee on a real
  meeting is a direct participant → **high confidence**.
- **Organisations:** attendee email **domains** → org (dedupe by domain).
- **Recency via a timeline entry:** for a **past** meeting, log a `timeline` touchpoint
  (`type: "meeting"`, `occurred_at` = the event date, linked to the attendees + any deal). Recency
  is now **derived** from contact-type timeline entries, so logging the meeting is what powers "who
  haven't I talked to in a while" — you don't separately set `last_interaction_at` (leave that for a
  migrated carry-in). See "the context layer" below.
- Deal signals from a calendar are usually weak; only extract one if the title/description is explicit
  (e.g. "Acme renewal — contract review"). When unsure, don't.
Tag each candidate `source: "calendar"`, with evidence (reason + the event title/time as the snippet).

*Idempotency:* calendar has no `crm-processed` label. Re-running is safe anyway — contacts/orgs
dedupe (A2), and `last_interaction_at` only ever moves to a more-recent date (older/equal = no-op).

---

# EXTRACT rules (shared by all sources — the model's job)

Extract only **concrete, stated facts** that map to the CRM. Never infer or guess. The editable
surface (propose across all of it — don't restrict to one field):
- **person:** name, title, phone, emails, `lifecycle_stage` (from `vocab`), `last_interaction_at`,
  plus free **`attributes`** (e.g. `preferred_name`, "based in Berlin").
- **organization:** name, domain(s), plus `attributes`.
- **deal:** name, `stage`/`status` (from `vocab`), amount, currency, expected close date, plus
  `attributes`.
- **associations:** who `works_at` which org, who is `decision_maker` / `champion` on which deal.
- **timeline entry** (the context layer — the loop's new main job): each processed **email/meeting**
  becomes one timeline touchpoint — `type` (`email`/`meeting`/`call`), `occurred_at`, a short `subject`,
  an AI **`summary`** (what happened / what was said / what's next), and the people + deal(s) + org(s)
  it involves. This is the record's history *and* what drives recency.
- **living summary** (per person and per deal): the current relationship/deal state in a sentence or
  two — where it stands, open items/commitments, key dates, sentiment. Rebuilt from the timeline +
  this comm when something material changed; not every run. **Lead with a standalone one-line headline
  sentence** — a self-contained "where things stand" gist that reads well on its own (the dashboard
  shows *only this first sentence* in its drawer, trimmed by code, so it must make sense without the
  rest). Then add the supporting detail in the following sentence(s). e.g. *"Verbal at $30k; board
  approved, awaiting the signed order form. Targeting a Sept 1 start; David sends paperwork by Friday."*

### The context layer — two hard rules
1. **Compliance: a timeline entry from an ingested comm stores the AI `summary` ONLY — never the raw
   `body`.** (The `body` field is for user-authored notes.) Same boundary as everything else: we hold
   the gist, not the raw email/event. Write the summary as *your own paraphrase of the outcome* —
   don't carry over sentences, quotes, or filler phrases (e.g. "everyone's aligned", "sounds good")
   verbatim from the message; capture what changed and what's next, not the wording. For idempotency, tag each entry `source: "gmail"` (emails) or
   `source: "gcal"` (calendar) with `external_id` = the Gmail thread id / Calendar event id — re-running
   the loop then never double-logs (the write dedupes on source+external_id).
2. **Summaries regenerate, they don't blind-edit.** Rebuild the living summary from the timeline (cite
   the entries/comms it's built from as its provenance); a *material* change surfaces in the digest for
   approval like any other write. Recency and the summary are context the model *maintains*, not
   authoritative numbers it invents.

Judgment rules:
- **Worthiness:** not every new address is a lead. Vendors, receipts, automated notifications, and
  one-off support reps are not relationships — skip them. Add someone only for a real business
  relationship (client / prospect / partner / investor).
- **Confidence:** direct participants (email From/To/Cc; meeting attendees) are high confidence;
  someone only *mentioned* in a body ("I met Jane at Acme") is low ("mentioned only") — still
  proposable, but flagged.
- **Evidence, always:** a one-sentence `reason` (brief AI overview — read first), the exact `snippet`
  that supports it (email line, or event title/time), and from/subject/date. The reason is your
  interpretation; the snippet is the raw proof.
- **Deal dates & stage are precise (the model's most common mistake — get this right):**
  - `expected_close_date` is when the deal is expected to **close / be decided** — NOT a project
    start or kickoff date. A stated start date ("start Sept 1", "kick off next month") must **never**
    be written to `expected_close_date`; leave it empty unless an actual close/decision date is given.
  - `status: won` means the deal is **actually closed** (signed / agreed to proceed contractually). A
    verbal yes, board approval, or "budget approved" is the **`verbal` stage with status still
    `open`** — never `won`. Never mark a deal `won`/`lost` on a verbal or speculative signal; advance
    the *stage*, keep *status* `open` until it truly closes.
  - Only create a deal when there's a **concrete opportunity** (a project, engagement, or amount
    discussed). Don't invent a blank-fielded deal from a vague mention.

---

# CORE — reconcile, review, write (once, across ALL sources)

### C1. Reconcile into proposals (deterministic)
Merge candidates from every source into one set. **Dedupe across sources** — the same person from an
email *and* a calendar invite is ONE proposal (keep the richest fields; note both sources if helpful).
Sort each change into:
- `new_contacts`, `new_organizations`, `new_deals` — no CRM match.
- `updates` — enrichments to existing records: a fact for an **empty** field, a **new** attribute, or
  a more-recent `last_interaction_at`.
- `deal_updates` — stage / status / amount moves on an existing deal.
- `timeline` — the touchpoints to log (one per processed email/meeting), each linked to the people /
  deal(s) / org(s) it involves.
- `summaries` — living-summary refreshes on people/deals whose state materially changed (put the new
  summary prose in the item's `subtitle`). Also include the record's **current stored summary** as
  `previous`, so the digest shows a before→after diff of exactly what the rewrite changed. **If the
  record has no summary yet (a first summary), omit `previous`** — there's nothing to replace, and it
  renders as plain new text.
- `conflicts` — a stated value **differs from an existing, non-empty** value (never `last_interaction_at`).

**Read-before-write for DEALS (deals have no natural key — match, don't duplicate).** Before you put
anything in `new_deals`, check the existing deals loaded in A2 — especially those on the matched
organisation/contact. If a deal with the **same or clearly-equivalent name on the same org** already
exists, it is **NOT new** — file it as a `deal_update` (e.g. stage `proposal → verbal`, an amount move),
**never a second copy**. A duplicate deal silently doubles that pipeline's value — a trust-breaking
invisible error. Only use `new_deals` when no existing deal plausibly matches. (Same discipline as the
email/domain dedup for people/orgs; deals just need name+org judgement instead of a key.)

Build the JSON in the shape at the top of `scripts/render_digest.py`: per item `title` / `subtitle` /
`detail` / **`source`** (`"email"` | `"calendar"`) / `confidence` / `evidence` (= `reason` + `snippet`
+ from/subject/date), plus an optional **`chip`** (`{text, kind:"kind"|"stage"}` — e.g. a contact's
`Lead`, a deal's `Discovery`, or a move `proposal → verbal`). `conflicts` also carry `field` /
`current` / `proposed`. Include `emails_reviewed` / `events_reviewed`. The renderer derives the
monogram avatars, the header tally, and the grouping (contacts → "New contacts"; orgs+deals → "New
records"; enrichments+deal moves → "Updates"; `timeline` → "Logged to your timeline"; `summaries` →
"Living summaries"; conflicts → "Needs your call"), so you don't format any of that — just sort items
into the right section key.

### C2. Render the digest and ask for approval
Run `python3 scripts/render_digest.py <proposals.json> digest.html` and show it (each item carries an
`email`/`calendar` source badge; the reasoning + source quote sit in the "Why this?" dropdowns; the
one conflict is quarantined in an amber "Needs your call" card). Then approve **in the conversation** —
the HTML is for reviewing, chat is for deciding (an artifact can't call tools back). Accept "approve
all", "skip #2", etc. **Write nothing before approval.**

### C3. Write approved changes (via the CRM MCP tools)
Approved items only, in this order so links resolve: `create_organization` → `create_contact` →
`create_deal` → `link_records` (idempotent) → `update_*` for enrichments, `last_interaction_at`, and
resolved conflicts. Then the **context layer**: `create_timeline_entry` for each approved touchpoint
(pass `person_ids` / `deal_ids` / `organization_ids`, `summary` [the gist, **not** the raw body],
`source`, `external_id`), and `update_contact` / `update_deal` with the new `summary` +
`summary_provenance` for each approved living-summary refresh. The tools re-check dedup server-side as a
backstop (contacts by email, orgs by domain, timeline entries by source+external_id).

### C4. Close the loop
Apply `scope.exclude_label` (`crm-processed`) to the handled **Gmail** threads (create the label first
if needed). If the user rejected an "add", offer to append that sender to `ignore`. Give a one-line
summary of what was written and skipped.

## What NOT to do
- Don't write anything before approval. Don't silently overwrite non-empty values (except a
  more-recent `last_interaction_at`).
- Don't read full email bodies that failed the cheap filters (waste of tokens).
- Don't invent facts to fill fields — an empty field is fine; a wrong one is not.
- Don't add the user themselves, automated senders, or `ignore`-listed contacts.
- Don't send raw email/event content to the CRM server — only structured, approved updates.
