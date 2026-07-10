---
name: crm-enrichment
description: >-
  Keep the CRM current from Gmail. Reads recent emails, extracts new contacts,
  organisations, and deal signals, dedupes them against the CRM, then proposes
  approved updates as a visual digest — nothing is written until the user approves.
  Use when the user wants to update / sync / enrich / "catch up" their CRM from
  email, asks "what's new in my inbox for the CRM", or runs their periodic review.
---

# CRM enrichment — the self-maintenance loop

This skill keeps the CRM accurate **without the user doing data entry**. It runs **client-side**
in the user's own Claude, using their **own Gmail connector**: raw email is read here and never
leaves for our server — only the **approved** structured updates are written, via the CRM's MCP
tools. That client-side boundary is a deliberate compliance decision; do not send raw email bodies
to the CRM server.

**Core principle — do the deterministic work in code, reserve the model for judgment.** Filtering,
existence-checks, and rendering are mechanical; only *reading prose and extracting facts* and
*judging whether something is a real relationship* need the model. This is cheaper and more
reliable.

**The prime guardrail — never silently overwrite.** Adding a new record, or filling an *empty*
field / new attribute, is low-friction (propose it). Changing an **existing, non-empty** value to
something different is a **conflict**: never write it silently — surface it in the digest's "Needs
your call" section for a human decision. A confidently-wrong overwrite is the one thing that breaks
trust in this product.

## Before you start

1. Read `config.json` (fall back to `config.example.json`). It defines `self` (the user's own
   emails/domains), `scope` (lookback window + the `crm-processed` watermark label), `ignore`
   (senders/domains to never add), and `vocab` (valid lifecycle/deal stages).
2. Confirm the CRM MCP tools are connected (e.g. `find_contacts`) and the Gmail connector is
   available. If either is missing, tell the user and stop — don't guess.

## The loop

### 1 — Scope (cheap, deterministic: pick the emails; don't read bodies yet)
- Search Gmail with a query built from config, e.g.:
  `newer_than:{scope.lookback} -label:{scope.exclude_label} {scope.gmail_query_extra}`
- From the returned **metadata only** (from / subject / snippet — not full bodies), drop:
  - anything from `self.emails` / `self.domains`,
  - senders matching `ignore.senders` or `ignore.domains`,
  - obvious automated mail (no-reply, receipts, newsletters).
- **Token discipline:** you now have a short candidate list. Only fetch full bodies (next step)
  for these survivors — never full-read the whole inbox.

### 2 — Classify against the CRM (cheap DB reads, no model tokens)
For each candidate, look up whether its people/org already exist:
- `find_contacts(email: <sender>)` and `find_organizations(domain: <sender domain>)`.
- Tag each candidate **KNOWN** (exists → an *update* candidate) or **NEW** (an *add* candidate).
- This does **not** exclude unknown senders — discovering new people/companies is half the value.
  It only decides create-vs-update and gives you the existing record as context for step 4.

### 3 — Read the survivors (this is where body tokens are spent)
Fetch full threads (`get_thread`) only for the candidates that passed. Read the content.

### 4 — Extract facts (the model's job — fit them to what the CRM can hold)
From each email, extract only **concrete, stated facts** that map to the CRM. Never infer or guess.
The editable surface (propose across all of it — don't restrict to one field):
- **person:** name, title, phone, emails, `lifecycle_stage` (from `vocab`), plus free
  **`attributes`** (e.g. `preferred_name`, "based in Berlin", "prefers Slack") — the attributes
  layer is how you add facts the schema has no column for.
- **organization:** name, domain(s), plus `attributes` (industry, size, renewal month…).
- **deal:** name, `stage`/`status` (from `vocab`), amount, currency, expected close date,
  plus `attributes`.
- **associations:** who `works_at` which org, who is `decision_maker` / `champion` on which deal.

Judgment rules:
- **Worthiness:** not every new address is a lead. Vendors, receipts, one-off support reps are
  not relationships — skip them. Add someone only if the email shows a real business relationship
  (client / prospect / partner / investor).
- **Confidence:** someone in From/To/Cc is a **direct correspondent** (high confidence). Someone
  only *named in the body* ("I met Jane at Acme") is **mentioned only** (low confidence) — still
  proposable, but mark it so.
- **Every proposal carries its evidence:** a one-sentence **`reason`** (a brief AI overview of why
  you're proposing this — the user reads this first), the exact **`snippet`** from the email that
  supports it (shown as an italic quote), and the sender / subject / date. The reason is your
  interpretation; the snippet is the raw proof. Together they make one-tap approval safe.

### 5 — Reconcile into proposals (deterministic)
Turn the extracted facts + the KNOWN/NEW tags into a proposals object, sorting each change into:
- `new_contacts`, `new_organizations`, `new_deals` — records with no CRM match.
- `updates` — enrichments to existing records: a fact for an **empty** field, or a **new**
  attribute key.
- `deal_updates` — stage / status / amount moves on an existing deal.
- `conflicts` — a stated value **differs from an existing, non-empty** CRM value. (Prime guardrail.)

Build the JSON in the shape documented at the top of `scripts/render_digest.py`
(`title` / `subtitle` / `detail` / `confidence` / `evidence` per item, where `evidence` =
`reason` + `snippet` + from/subject/date; `conflicts` carry `field` / `current` / `proposed`).
Include `emails_reviewed`.

### 6 — Render the digest and ask for approval
- Run: `python3 scripts/render_digest.py <proposals.json> digest.html` and show `digest.html`
  to the user (it renders as an artifact; evidence is in the collapsible "Why this" dropdowns).
- Then ask for approval **in the conversation** — the HTML is for reviewing, chat is for deciding
  (an artifact can't call tools back). Accept "approve all", "skip #2", "yes but fix David's
  title", etc. **Write nothing before the user approves.**

### 7 — Write approved changes (via the CRM MCP tools)
Only for approved items, in this order so links resolve:
1. `create_organization` (dedupes by domain server-side; returns existing if present),
2. `create_contact` (dedupes by email server-side),
3. `create_deal`,
4. `link_records` for associations (idempotent),
5. `update_contact` / `update_organization` / `update_deal` for approved enrichments &
   resolved conflicts.
Rely on the tools' built-in read-before-write as a backstop, but you have already deduped in
step 2 — the tools returning `already_exists` should be the rare case, not the plan.

### 8 — Close the loop
- Apply the `scope.exclude_label` (`crm-processed`) to the handled Gmail threads (create the label
  first if needed) so the next run won't re-surface them.
- If the user **rejected** an "add", offer to append that sender to `ignore` so it never nags again.
- Give a one-line summary of what was written (and what was skipped).

## What NOT to do
- Don't write anything before approval. Don't silently overwrite non-empty values.
- Don't read full bodies of emails that failed the cheap filters (waste of tokens).
- Don't invent facts to fill fields — an empty field is fine; a wrong one is not.
- Don't add the user themselves, automated senders, or `ignore`-listed contacts.
- Don't send raw email content to the CRM server — only structured, approved updates.
