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
sets create-vs-update and supplies the existing record as context.

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
- **`last_interaction_at`:** for a **past** meeting, the person's last-interaction date is (at least)
  the event date. Propose setting/refreshing it. This is the calendar's signature contribution — it
  powers "who haven't I talked to in a while."
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
- `conflicts` — a stated value **differs from an existing, non-empty** value (never `last_interaction_at`).

Build the JSON in the shape at the top of `scripts/render_digest.py`: per item `title` / `subtitle` /
`detail` / **`source`** (`"email"` | `"calendar"`) / `confidence` / `evidence` (= `reason` + `snippet`
+ from/subject/date); `conflicts` also carry `field` / `current` / `proposed`. Include `emails_reviewed`.

### C2. Render the digest and ask for approval
Run `python3 scripts/render_digest.py <proposals.json> digest.html` and show it (each item shows a
📧/📅 source badge; evidence is in the "AI overview" dropdowns). Then approve **in the conversation** —
the HTML is for reviewing, chat is for deciding (an artifact can't call tools back). Accept "approve
all", "skip #2", etc. **Write nothing before approval.**

### C3. Write approved changes (via the CRM MCP tools)
Approved items only, in this order so links resolve: `create_organization` → `create_contact` →
`create_deal` → `link_records` (idempotent) → `update_*` for enrichments, `last_interaction_at`, and
resolved conflicts. The tools re-check dedup server-side as a backstop.

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
