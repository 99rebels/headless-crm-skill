---
name: crm-import
description: >-
  Import contacts, companies, and deals into the CRM from a CSV or spreadsheet export. Reads the
  file, proposes how each column maps to CRM fields, dedupes and links people to their companies
  and deals, and shows an approval preview — nothing is written until approved. Use when the user
  wants to import / upload / bring in / migrate / bulk-add contacts, a spreadsheet, an Excel or
  CSV export, or their existing list from another CRM (HubSpot, Salesforce, Pipedrive, a
  Mailchimp/newsletter export, etc.) to get started quickly. This is a bulk WRITE path — for
  updating from live email/calendar use crm-enrichment; to only VIEW the pipeline use crm-dashboard.
---

# CRM import — bring an existing list in, cleanly

Gets a new user from **zero to a populated CRM in one pass**, from a file they already have (a CRM
export, a spreadsheet of contacts, a deal list). Same discipline as the enrichment loop, one new
**source**: a CSV file instead of Gmail/Calendar. The pipeline is identical — **profile → map →
build → approve → write** — so a 2,000-row file is as reliable as a 5-row one.

**Do the deterministic work in code, reserve the model for judgment.** Parsing, deduping, linking,
and rendering are mechanical (the scripts). The *one* judgment call is the **column mapping** — which
column is the email, which is the company, which is a deal stage. That's yours; everything else is a
script.

**Never write before approval.** The file is *proposed* into the CRM and shown as a preview; the
user approves in the conversation before anything is created. Existing records with the same email
or domain are **reused, not duplicated** (the create tools enforce this server-side too).

## Before you start
1. Confirm the CRM MCP tools are connected (e.g. `find_contacts`). If not, stop and say so.
2. Read `config.json` (fall back to `config.example.json`): `vocab` (valid lifecycle/deal stages),
   `aliases` (export labels → your vocab), `column_hints` (hints for the mapping step).
3. Get the file. The user attaches a CSV (or exports their spreadsheet/other CRM to CSV). Save it
   locally so the scripts can read it (e.g. `import.csv`).

---

# STEP 1 — Profile the file (deterministic, cheap)
Run `python3 scripts/inspect_csv.py import.csv`. This returns the delimiter, row count, and for each
column its **fill rate** and a few **sample values** — enough to map columns **without reading every
row into the context**. Don't dump the whole CSV into the conversation.

# STEP 2 — Propose the column mapping (the model's job)
From the profile, decide what each column maps to. Recognised targets:
- **person:** `person.name` (a single full-name column) OR `person.first_name` + `person.last_name`
  (separate columns — joined into the name automatically) · `person.email` · `person.emails` (extra
  addresses) · `person.phone` · `person.title` · `person.lifecycle_stage`
- **organization:** `organization.name` · `organization.domain`
- **deal:** `deal.name` · `deal.stage` · `deal.status` · `deal.amount` · `deal.currency` ·
  `deal.expected_close_date`
- **keep as a note:** `person.attr.<key>` / `organization.attr.<key>` / `deal.attr.<key>` (e.g. a
  "Notes" or "LinkedIn" column → `person.attr.notes`) — nothing is lost, it just isn't a spine field
- **`ignore`** for columns you're not importing (internal ids, owner, source, etc.)

Rules:
- Use `column_hints` and the sample values to judge; **don't guess** on an ambiguous column — leave
  it `ignore` and mention it, or ask.
- A single "Name"/"Full Name" column → `person.name`. Separate "First Name"/"Last Name" columns →
  `person.first_name` and `person.last_name` (the build joins them into the name).
- Only set `options.create_deals = true` if the file actually has deal/opportunity/value columns.
  A pure contact list has no deals — don't invent them.
- Set `options.default_lifecycle` only if the user wants every imported contact to start at one stage
  (e.g. `lead`); otherwise leave it off.

**Also map the VALUES, not just the columns (this is what makes it vendor-agnostic).** For the
lifecycle and deal-stage columns, look at the *actual sample values* from the profile and map any that
aren't already workspace vocab onto it — put them in `mapping.aliases`. The vocab lives in
`config.json` (`vocab.lifecycle_stages`, `vocab.deal_stages`); `config.json.aliases` seeds the common
cases (`Customer`→`client`, `Closed Won`→`won`), but **you** handle whatever this file actually
contains — a HubSpot `Evangelist`, a Salesforce `Negotiation/Review` or `Value Proposition`, etc.:
```json
"aliases": {
  "lifecycle":  { "evangelist": "client", "sales qualified lead": "prospect" },
  "deal_stage": { "negotiation/review": "verbal", "value proposition": "proposal" }
}
```
Rules: map to a **valid vocab term only**; keys are the file's raw values (case-insensitive). If a
value genuinely has no good vocab home, **leave it out** — the build keeps it as a note and leaves the
field blank (never guess a stage). Don't map `won`/`lost` onto an *open* stage or vice-versa: a
"Contract Sent" / "Verbal yes" is `verbal` with the deal still **open**, not `won`.

Write the mapping to `mapping.json` (shape documented at the top of `scripts/build_import.py`).
**Show the user the mapping in plain language and let them correct it before building** — this is the
"match it up as well as possible" moment. A quick table (column → CRM field, with the ones you're
skipping called out) is ideal.

# STEP 3 — Build the write-plan (deterministic)
Run `python3 scripts/build_import.py import.csv mapping.json config.json > plan.json`. This applies
the mapping to every row and produces:
- `plan` — the exact records to create (`contacts`, `organizations`, `deals`) each with a local
  `key`, plus `links` (works_at / primary_contact / account) referencing those keys. **Deduped**
  (people by email, orgs by domain, deals by name) and **stage-normalised** against your vocab.
- `digest` — the display data for the preview, including `counts` and any **mapping `notes`**
  (unmapped columns, values that didn't match the vocab).

**REQUIRED self-check — read `digest.notes` before continuing.** If any note says a lifecycle or
deal-stage value "isn't in your vocab", you **missed mapping it in Step 2** — that value fell through
to a blank field. Go back, add it to `mapping.aliases`, and **rebuild**. Repeat until the only notes
left are genuinely unmappable values or ignored columns. Do NOT present a plan full of blank
stages/lifecycles when a one-line alias would have mapped them — that's the most common failure and
it's exactly what this check prevents. (A HubSpot `Evangelist`, a Salesforce `Negotiation/Review` /
`Value Proposition` / `Contract Sent` all have obvious vocab homes — map them.)

# STEP 4 — Render the preview and get approval
**You MUST render and display the HTML preview before asking for approval — do not skip it and do not
substitute a text summary.** The visual preview IS the approval surface; approving from a text list
means the user is approving blind.
1. Run `python3 scripts/render_import.py plan.json import-preview.html`.
2. **Display the generated `import-preview.html` file to the user** (present the file so it renders).
   It shows summary tiles, a "how I read your columns" mapping card (columns → CRM fields, plus the
   value translations like `Customer → client`), and tab-switched tables of the People / Companies /
   Deals to be created (capped with a "+N more"). It's driven entirely by `plan.json` — no hand-editing.
3. Then get approval **in the conversation** (the artifact can't call tools back). Accept "import",
   "import but skip the deals", "don't set everyone to lead", etc. **Write nothing before approval.**

*Re-import / not-a-fresh-workspace:* if the workspace may already have data, pull existing records
once (`find_contacts`, `find_organizations`) and note in the preview which rows already exist. On a
first import into an empty workspace, skip this — the create tools dedupe anyway.

# STEP 5 — Write the approved plan (ONE call)
Call **`bulk_import`** once, passing the whole `plan` object from `plan.json`
(`{ contacts, organizations, deals, links }`). It creates everything server-side in the right order
(orgs → contacts → deals → links), dedupes orgs by domain and contacts by email (reusing matches, not
duplicating), resolves the local `key`s to real ids, and links — all in a **single tool call**.

**Do NOT loop `create_contact` / `create_deal` / `link_records` per record.** On a real-size file
that's dozens-to-hundreds of calls and will hit the per-turn tool limit mid-import. `bulk_import` is
the whole write.

- **Honor skips** by editing the plan *before* the call: if the user said "skip the deals", drop
  `plan.deals` and any `plan.links` whose `from`/`to` is a `d…` key.
- **Merged duplicates:** if the user chose to merge a flagged possible-duplicate into an existing
  record (e.g. "add David's new email to his existing record"), drop that contact from `plan.contacts`
  and instead `update_contact` the existing record (add the alias email) — as a separate call.
- `bulk_import` returns `created`/`reused` counts and a per-record `errors` array — check it's empty.

# STEP 6 — Close the loop
Give a one-line summary: how many contacts / companies / deals were created (and how many were reused
as existing). Offer the natural next step — "want me to run the dashboard?" (crm-dashboard) or "keep
this current from your email going forward?" (crm-enrichment).

## What NOT to do
- Don't write anything before approval, and don't skip the HTML preview (Step 4) — no approving blind.
- **Don't loop per-record `create_`/`link_` calls — use `bulk_import` (Step 5).** Per-record writes
  hit the per-turn tool limit on real files.
- Don't present a plan with blank stages/lifecycles when an alias would map them — run the Step 3
  self-check and add `mapping.aliases`.
- Don't read the whole CSV into the conversation — `inspect_csv.py` profiles it cheaply; the scripts
  handle the full file.
- Don't invent deals from a contact-only file. Never guess a stage the vocab doesn't define — a value
  with no vocab home is kept as a note, not written to the spine field.
- Don't guess an ambiguous column — leave it `ignore` and say so, or ask.
- Don't duplicate: rely on email/domain dedupe (in the plan and server-side).
