---
name: crm-import
description: >-
  Bring an existing contact/deal list into the CRM from either a FILE or a CONNECTED CRM, cleanly and
  with approval. Two sources, one destination: (1) a CSV / spreadsheet / other-CRM export the user
  attaches, or (2) a live connected CRM — currently Attio — read straight through its connector.
  Proposes how each column / field and each deal STAGE maps onto this CRM's fields and vocabulary,
  dedupes and links people to companies and deals, and shows an approval preview — nothing is written
  until approved. Use when the user wants to import / upload / bring in / migrate / move / switch /
  transfer their contacts, a spreadsheet, an Excel or CSV export, or their existing CRM (Attio,
  HubSpot, Salesforce, Pipedrive, a Mailchimp export, etc.) to get started quickly. This is a bulk
  WRITE path — for updating from live email/calendar use crm-enrichment; to only VIEW the pipeline
  use crm-dashboard.
---

# CRM import — bring an existing list in, cleanly

Gets a new user from **zero to a populated CRM in one pass**. Same discipline as the enrichment loop,
just a different **source** — and this skill handles **two**:

- **A file** — a CSV / spreadsheet / other-CRM export the user attaches.
- **A connected CRM** — currently **Attio**, read live through its connector (no export needed).

Both run the same shape — **profile/discover → map → build → approve → write** — and both converge on
the same approval preview and the same one-call server-side write (`bulk_import`). So a 2,000-row
file and a 2,000-record Attio migration are equally reliable.

**Do the deterministic work in code, reserve the model for judgment.** Parsing, deduping, linking,
and rendering are mechanical (the scripts). The *one* judgment call is the **mapping** — which column
is the email / which Attio stage is a "won" deal. That's yours; everything else is a script.

**Never write before approval.** Records are *proposed* into the CRM and shown as a preview; the user
approves in the conversation before anything is created. Existing records with the same email or
domain are **reused, not duplicated** (`bulk_import` enforces this server-side too).

## Before you start
1. Confirm this CRM's tools are connected (e.g. `find_contacts`). If not, stop and say so.
2. Read `config.json` (fall back to `config.example.json`): `vocab` (valid lifecycle/deal stages),
   `aliases` (source labels → your vocab), `column_hints` (hints for the mapping step).

---

# STEP 0 — Which source? (route before you do anything else)
- **A file is attached, or the user points to a CSV / spreadsheet / export** → **PATH A**. A present
  file is the strongest signal — take it.
- **The user asks to migrate / move / switch from Attio** (or names Attio), **or** there's no file and
  they want to bring in their existing CRM → **PATH B**. (Requires the **Attio** connector; confirm it
  with Attio `whoami` and, if it's missing, tell them to add the Attio connector in their Claude
  connector settings.)
- **Ambiguous** (e.g. "import my contacts" with no file and no CRM named) → ask ONE question: *"Do you
  have a file to upload, or is your data in a connected CRM like Attio?"* Then route.

Other source CRMs (HubSpot, Salesforce, Pipedrive, …): if the user has an **export file**, use PATH A
(it's vendor-agnostic). Live connectors beyond Attio aren't wired yet — offer the file route.

---

# ── PATH A · a file (CSV / spreadsheet export) ──

## A1 — Profile the file (deterministic, cheap)
Save the attached file locally (e.g. `import.csv`) and run `python3 scripts/inspect_csv.py import.csv`.
It returns the delimiter, row count, and per-column **fill rate** + **sample values** — enough to map
columns **without reading every row into the context**. Don't dump the whole CSV into the conversation.

## A2 — Propose the column mapping (the model's job)
From the profile, decide what each column maps to. Recognised targets:
- **person:** `person.name` (single full-name col) OR `person.first_name` + `person.last_name` ·
  `person.email` · `person.emails` (extras) · `person.phone` · `person.title` · `person.lifecycle_stage`
- **organization:** `organization.name` · `organization.domain`
- **deal:** `deal.name` · `deal.stage` · `deal.status` · `deal.amount` · `deal.currency` ·
  `deal.expected_close_date`
- **keep as a note:** `person.attr.<key>` / `organization.attr.<key>` / `deal.attr.<key>` (e.g. a
  "LinkedIn" column → `person.attr.linkedin`) — nothing is lost, it just isn't a spine field
- **`ignore`** for columns you're not importing (internal ids, owner, source, …)

Rules: use `column_hints` + samples; **don't guess** an ambiguous column (leave it `ignore` and say
so, or ask). A single "Name" column → `person.name`; separate "First/Last" → the two name fields
(joined automatically). Only set `options.create_deals = true` if the file has deal/value columns.
Set `options.default_lifecycle` only if the user wants every contact to start at one stage.

**Also map the VALUES, not just the columns** (this is what makes it vendor-agnostic). For the
lifecycle and deal-stage columns, look at the *actual sample values* and map any that aren't already
workspace vocab into `mapping.aliases`. `config.json.aliases` seeds the common cases
(`Customer`→`client`, `Closed Won`→`won`); **you** handle whatever this file contains (a HubSpot
`Evangelist`, a Salesforce `Negotiation/Review` / `Value Proposition`):
```json
"aliases": { "lifecycle": { "evangelist": "client" }, "deal_stage": { "value proposition": "proposal" } }
```
Map to a **valid vocab term only**; if a value has no good home, **leave it out** (it's kept as a note,
field blank — never guessed). Don't map `won`/`lost` onto an *open* stage or vice-versa.

Write `mapping.json` (shape at the top of `scripts/build_import.py`). **Show the mapping in plain
language and let the user correct it before building.**

## A3 — Build the write-plan
Run `python3 scripts/build_import.py import.csv mapping.json config.json > plan.json`. **Then run the
self-check in the shared BUILD step below.** → continue to **BOTH**.

---

# ── PATH B · a connected Attio ──

## B1 — Discover the Attio schema (cheap, structural — no records yet)
Call Attio `whoami` and `list-attribute-definitions` for **people**, **companies**, **deals**. The
one thing to capture: the **deal-stage** attribute's status options **with their `order` and titles**
(type `status`) — you'll use order + wording to place won/lost, not blind string-matching. Note the
deal `value` attribute's currency. Don't pull records yet. *(Only the three spine objects migrate —
see "What NOT to do".)*

## B2 — Pull the records into local files (keep them OUT of the conversation)
For each of `people`, `companies`, `deals`, page Attio `list-records` (`limit: 50`, then `offset` 50,
100, … until a short/empty page or `has_more` false) and **write the arrays to `people.json`,
`companies.json`, `deals.json`** (records as returned: `{record_id, attributes:{…}}`). **Do NOT paste
records into the chat** — a real workspace floods the context (the whole reason we write to files, then
let the script read them). Keep only the counts; tell the user ("321 people, 88 companies, 140 deals").

## B3 — Propose the mapping (the model's job: the STAGES)
Standard fields map automatically (`build_from_attio.py` has built-in defaults for Attio's standard
slugs). **Your job is `mapping.json`, mainly the deal-stage alias map** — map each Attio stage **title**
to a `deal_stages` term (`discovery/proposal/verbal/won/lost`) using the **`order` + wording** from B1:
- **Won/lost is what matters** (it drives pipeline value). End-of-pipeline success stages → `won`;
  explicit `Lost`/`Disqualified`/`Dead` → `lost`. **Post-sale states (`Live`, `Onboarding`, `Active`,
  `Customer`) mean the deal closed → `won`** — the ongoing customer relationship is *lifecycle*, tracked
  separately, not a deal stage.
- **Open-stage granularity is low-stakes** — map by meaning (`Lead`/`In Progress`/`Demo scheduled`→
  `discovery`; `Proposal`/`Quote`→`proposal`; `Negotiation`/`Contract`→`verbal`).
- **Never invent a stage the vocab lacks** — leave it out (the build keeps the original label as a note,
  field blank).
```json
{
  "stage_aliases": { "won 🎉": "won", "live": "won", "demo scheduled": "discovery", "disqualified": "lost" },
  "fields":  { "companies": { "company_stage": "organization.attr.funding_stage" } },
  "options": { "default_currency": "EUR", "source_label": "Attio · <Workspace>" }
}
```
`config.json` seeds the common cases (your `stage_aliases` win). Use `fields` only to pull a *custom*
attribute in as a note; standard slugs are already handled. Set `options.default_currency` to the
workspace currency (seen on the deal `value` in B1). **Show the stage map in plain language and let the
user correct it before building** — this is the "did the stages map right?" trust moment.

## B3b — Bring the context layer too (notes + last-contacted) — recommended
The migration should carry a record's **history and recency**, not just its fields — otherwise a
migrated contact reads as "no contact ever", which erodes trust.
- **Notes → timeline.** Page Attio `list-notes` for people/companies/deals, then `get-note-body` for
  each, and write an array to `notes.json`: `{note_id, parent_object, parent_record_id, title,
  content, created_at}`. `build_from_attio.py --notes` folds each into a timeline entry attached to
  its record (`source: migration`, idempotent on `note_id`, so re-running never duplicates). Notes
  whose parent isn't in the pull are dropped with a reconciliation note. Keep note bodies OUT of the
  chat — write to the file, let the script read it.
- **Last-contacted → recency.** If Attio exposes a "last interaction / last contacted" attribute
  (from B1's definitions), map its slug in `mapping.json` to `person.last_interaction_at` /
  `organization.last_interaction_at`, e.g. `"fields": { "people": { "last_interaction":
  "person.last_interaction_at" } }`. It's carried in as recency (there's no timeline history to derive
  it from yet), and any freshly-logged email/meeting later supersedes it automatically.

## B4 — Build the write-plan
Run (drop `--notes` if you didn't pull any):
```
python3 scripts/build_from_attio.py --people people.json --companies companies.json \
    --deals deals.json --notes notes.json --mapping mapping.json --config config.json > plan.json
```
The plan may now include a `timeline_entries` array — the write step (`bulk_import`) handles it in the
same single call. **Then run the self-check in the shared BUILD step below.** → continue to **BOTH**.

---

# ── BOTH · build self-check → preview → approve → write → close ──

## BUILD self-check (REQUIRED, both paths)
Read `digest.notes`. If a note says a lifecycle/deal-stage value "isn't in your vocab", you **missed
mapping it** — that value fell through to a blank field. Add it to `mapping.aliases` (PATH A) /
`mapping.stage_aliases` (PATH B) and **rebuild**. Repeat until the only notes left are genuinely
unmappable values, emailless-people counts, or dropped cross-pull links. Don't present blank
stages/lifecycles when a one-line alias would map them — this is the most common failure.
(`digest.skipped_columns` lists columns/attributes not imported — expected for custom fields.)

## Render the preview and get approval (REQUIRED)
**You MUST render and display the HTML preview before asking for approval — do not skip it and do not
substitute a text summary.** The visual preview IS the approval surface.
1. Run `python3 scripts/render_preview.py plan.json preview.html` (one renderer for both sources; it
   reads `digest.source_kind` and shows the right copy — "how I read your columns" for a file, "how I
   mapped your Attio fields" for Attio).
2. **Display `preview.html`** (present it so it renders): summary tiles, the mapping card (the thing to
   check — column/stage translations), tab-switched People / Companies / Deals tables, and any amber notes.
3. Get approval **in the conversation** (the artifact can't call tools back). Accept "import"/"migrate",
   "skip the deals", "don't set everyone to lead", mapping corrections, etc. **Write nothing before approval.**

*Re-import / non-empty workspace:* if the workspace may already have data, pull existing records once
(`find_contacts`, `find_organizations`) and note which rows already exist. On a first import into an
empty workspace, skip this — `bulk_import` dedupes anyway.

## Write the approved plan (ONE call)
Call **`bulk_import`** once with the whole `plan` object (`{ contacts, organizations, deals, links }`).
It creates everything server-side in order (orgs → contacts → deals → links), dedupes orgs by domain
and contacts by email (reusing matches), resolves the local `key`s, and links — in a **single call**.

**Do NOT loop `create_contact` / `create_deal` / `link_records` per record** — on a real-size file or
workspace that's dozens-to-hundreds of calls and blows the per-turn tool limit. `bulk_import` is the
whole write.
- **Honor skips** by editing the plan *before* the call (e.g. "skip the deals" → drop `plan.deals` and
  any `plan.links` referencing a `d…` key).
- **Merged duplicates:** if the user chose to merge a flagged possible-duplicate into an existing record,
  drop that contact from `plan.contacts` and `update_contact` the existing record instead (separate call).
- Check the returned `errors` array is empty.

## Close the loop
One-line summary: how many contacts / companies / deals were created (and reused). Offer the next step —
"want me to run the dashboard?" (crm-dashboard) or "keep this current from your email going forward?"
(crm-enrichment).

## What NOT to do
- Don't write anything before approval, and don't skip the HTML preview — no approving blind.
- **Don't loop per-record `create_`/`link_` calls — use `bulk_import`.**
- Don't present blank stages/lifecycles when an alias would map them — run the BUILD self-check.
- **PATH A:** don't read the whole CSV into the conversation (`inspect_csv.py` profiles it); don't invent
  deals from a contact-only file; don't guess an ambiguous column.
- **PATH B:** don't paste pulled Attio records into the chat (page them to files); don't fabricate
  associations (links come only from Attio's own `record_id` references).
- **Never guess a stage the vocab doesn't define** — a value with no home is kept as a note, not written.
- **Don't expand this CRM's model to mirror a source.** Only people / companies / deals + standard fields
  import; custom objects/attributes are **reported** (notes or skipped-list), never bolted on as new
  types. Legibility, not coverage, is the trust.

## Fallback (demo safety, PATH B)
If the live Attio read is flaky (auth, rate limit, an unexpected shape), the user can export Attio to
CSV and run **PATH A** — it lands on the *same* approval → `bulk_import` path, so the migration still
completes.

## Local test suite
`python3 test/run_tests.py` — no connection needed. Exercises **both** engines: the Attio migration
(`build_from_attio.py`) over fixtures shaped like the real connector output, **and** a CSV golden
regression (the committed sample must still reproduce `sample-plan.json` exactly) so a shared-config
change can't silently break the deployed CSV path. Run it after any change to either builder, the
config, or the renderer.
