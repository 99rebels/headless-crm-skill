# Source attribution + the deep view — build brief

**Status (2026-07-13, updated):** The notes/context layer this doc originally "flagged for" is now
**BUILT** (phase 2 — migration `0003`, `core/note.ts`, timeline + living summaries wired into the
enrichment loop and the Attio migration; see [notes-design.md](notes-design.md) and the build-state
memory). So this doc is no longer a heads-up for that build — it is now the **build brief for the
deep (per-record) view** that sits on top of it, plus the source-drill-down decision (which still
holds) and the handful of gaps left to decide. A fresh instance should be able to build the deep view
from this doc + the mockup. **Not being built this session** — Rian is deciding scope; this captures
the shared understanding so it can be picked up cold.

**Reference mockup:** [mockups/deep-view-company.html](mockups/deep-view-company.html) — open it and
expand any timeline entry's **"Summary & source"** to see the exact experience. This is the committed
reference for the deep view + the source drill-down.

---

## 1. The decision (unchanged) — proof = AI summary + link out, never raw data
When a timeline entry comes from an ingested comm (Gmail email, Granola meeting), the user can **see
where it came from**: enough header context to trust it, the **AI summary** of what happened, and a
**link back to the original in their own tool** (`external_id`). We do **not** store the raw body.
Confirmed with Rian (2026-07-13): **"proof" = the AI summary + the link out** — that is sufficient and
on-model; we are not storing a raw quote/excerpt.

Two options considered and **rejected** (don't re-open without a deliberate, consented reason):
- **Storing raw email/meeting bodies** — inverts the client-side-only compliance model (the pivot's
  core edge: we never hold raw comms). Its one real payoff is cross-comms retrieval/search, which
  semantic search over *summaries* gives us more cheaply (see §8) without the liability.
- **Storing a short "approved excerpt"/quote** — dropped. The AI summary + metadata + link is enough,
  and a stored quote nudges the raw-content boundary.

## 2. What's already stored (phase 2 — the substrate the deep view reads)
Everything the source card needs already exists. Schema of record: `server/db/migrations/0003_notes_timeline.sql`;
core: `server/src/core/note.ts`; MCP tools in `server/src/mcp/build.ts`.
- **`interaction`** (the unified timeline entry): `id`, `type`
  (`email`/`meeting`/`call`/`note`/`stage_change`/`relationship_change`), `occurred_at`, `direction`
  (`inbound`/`outbound`/`internal`), `subject`, **`summary`** (the AI gist — always stored),
  `body` (user-authored notes ONLY — ingested comms stay summary-only), **`source`**
  (`gmail`/`gcal`/`granola`/`migration`/`manual`), **`external_id`** (the back-pointer for "view
  original"), `owner_id` (author — team forward-compat).
- **`interaction_link`** (many-to-many): one entry ↔ any number of people/deals/orgs, each with an
  optional `role`. This is how the source card renders "who was on it" for attendees/recipients who
  are CRM records.
- **`person.summary` / `deal.summary`** (+ `summary_updated_at`, `summary_provenance`): the living
  summaries, enrichment-maintained, regenerate-not-blind-edit, provenance = the timeline entry ids
  they were built from.
- **`organization.description`**: stable identity ("who they are / what they do"). NOTE: orgs do **not**
  yet have a *living* summary — that's the decided add in §4.
- **Recency is derived**: `core/note.ts:getLatestContactMap` gives, per record, the date of its most
  recent contact-type entry (email/meeting/call); `core/summary.ts` maxes that with the stored
  `last_interaction_at` (the migrated-recency carry-in). So "last spoke 3 days ago" is computed, not
  typed.

## 3. Building the deep view — what's real vs. derived vs. missing
Audited against `mockups/deep-view-company.html`. **~80% renders from stored data today.**

**Backed by stored data ✅**
- Company identity: name, domain, `description` prose, the Industry/Stage/Team/Funding chips
  (`organization.attributes`).
- People: names, titles, emails; "last spoke X days" (derived recency).
- The deal: name, stage, amount, decision date (`expected_close_date`), start date
  (`attributes.target_start` — already read by `summary.ts`).
- The deal's living summary (the `deal-summary` paragraph is literally `deal.summary`).
- The **whole timeline**: each entry's type icon, title (`subject`), date, AI `summary`, `source`
  badge, `direction`, and its record links.
- The **"Summary & source" drill-down**: AI summary + subject + direction + the "View original in
  Gmail/Granola" link (`external_id`) + the honest footer. This is the source-attribution MVP, and it
  is real.

**Derived at render time — computable from what's stored 🔁**
- "Warm · active deal" temperature (from deal status + recency).
- "12 days in stage" (from the latest `stage_change` entry's `occurred_at` — requires the loop to log
  stage moves as `stage_change` entries; else fall back to `deal.updated_at`).
- "Champion / blocker" role chips: the `association` table already supports typed `relationship_type`
  strings (`champion`, `decision_maker`, …) — the enrichment loop just has to set them. (Per
  notes-design §6.3 roles may live in summary prose for v1; associations are the typed home when we
  want chips.)
- People / deal counts.

**Not stored yet — the gaps (see §4–§5) ⚠️**
1. Company-level **living summary** (the "Where things stand" brief band). → §4 (decided: add it).
2. Structured **"My open items / Waiting on them"** commitments. → §5a (undecided — Rian revisiting).
3. Non-record participants, meeting duration, "referred by" edges. → §5b/§5c (deferred).

## 4. Company living summary — DECISION: add it (Rian likes this)
Add a **living summary to `organization`**, symmetric with person/deal:
`organization.summary` + `summary_updated_at` + `summary_provenance` (a new migration; mirror the
person/deal columns from `0003`). This powers the deep view's hero "Where things stand" brief band.

Keep it distinct from `description`:
- **`description`** = *stable identity* — what the company is ("seed-stage dev-tools startup, CI/CD for
  mobile"). Rarely changes.
- **`summary`** (new) = *living account state* — where the relationship stands now.

How it's maintained (the important nuance Rian raised): it is **mostly a roll-up of the people and deal
summaries** for that account — but it also carries **company-only facts that change and aren't tied to
a single deal or person**: a funding round, a reorg / new CEO, "went quiet across *all* our contacts,"
an expansion into a new market, an M&A event. So the org summary = (roll-up of its deals + people) +
(account-level dynamics). Same discipline as the others: enrichment regenerates it with provenance
(citing the deal/person summaries + timeline entries it drew from), material changes go through the
approval digest.

**Interim, before this ships:** the deep view can **compose the brief band at render time from the
active deal's summary** — for a solo operator a single-deal company's "where things stand" *is* the
deal's state, so this is a free stopgap that needs no schema change. Add the real column when a company
narrative independent of one deal starts to matter (multi-deal accounts, or the company-only facts
above).

## 5. The remaining gaps

### 5a. Structured commitments — "My open items / Waiting on them" (UNDECIDED — Rian revisiting)
The mockup shows two tidy columns: the user's open items and what they're waiting on from the other
side, each with a due date / "the deciding step" tag. We do **not** store these as structured data
today — they currently live *inside* the living summary prose. Rendering the structured boxes is
exactly the deferred **[commitments-ledger.md](commitments-ledger.md)** capability.
- **Status:** Rian wants to **come back to this** — decide whether v1 gets structured commitments or
  keeps them as prose inside the summary.
- **What it would take if adopted:** a small structured store for commitments (owner = mine/theirs,
  text, optional due date, status open/done, linked to the deal/person) — either its own table or a
  typed shape inside `deal.attributes` / the summary provenance; plus an enrichment extraction target
  (the loop already reads the comms that state commitments) surfaced in the digest for approval. Pairs
  naturally with the notes loop ("capture a bit more structure at enrichment time so a read is cheap
  later"). Keep the vocab tiny; resist a task-manager.
- **Recommendation:** prose-in-summary for v1; promote to structured only if the boxes prove they earn
  the schema. Don't block the deep view on it — render from summary prose meanwhile.

### 5b. Non-record participants + meeting duration (deferred)
The source card shows things like meeting duration ("42 min") and attendees who aren't CRM records
("me", an external cc). We store attendees/recipients who **are** records (via `interaction_link`), and
`direction` reconstructs the From/To sense; the rest isn't stored. Recommendation (unchanged): **defer**
— ship with subject/title + record-linked participants, and add a small nullable `interaction.participants`
(jsonb) for non-record names + a `duration`/detail field **only if** their absence actually proves
annoying. Leanest start; refactor later.

### 5c. "Referred by" edges (deferred → the referral graph)
The intro entry shows "referred by Dana Rios." That's a person↔person edge — the **§8b referral graph**
in [notes-design.md](notes-design.md). Storage already exists (the polymorphic `association` table with
a free `relationship_type` + jsonb provenance that can cite the timeline entry `id`). Deferred to the
notes fast-follow; the deep view can omit it now and light it up when the edge extraction lands.

## 6. The tool to build alongside the deep view — `get_record_detail`
The deep view needs the **whole record composed in ONE deterministic call**, for the same reason
`get_pipeline_summary` exists: compute facts + joins once, server-side, so every model renders an
identical view and the skill only does presentation (see [summary-tool.md](summary-tool.md) — the
"arithmetic/lookups live in `core`; the model writes prose" principle). Today a deep view would have to
stitch `get_organization` + `find_associations` + `find_timeline_entries` + `find_deals` +
`find_contacts` — multiple calls, inconsistent across models.

**Proposed tool** (build in `core/` like `summary.ts`, e.g. `core/detail.ts` → `getRecordDetail`):
- **Input:** `record_type` (`person`|`organization`|`deal`), `record_id`.
- **Output (composed, presentation-ready):**
  - the record's own fields + `description` (org) + living `summary` (+ `summary_updated_at`),
  - **derived recency** (`getLatestContactMap` max stored) and a **temperature** (warm/cooling/quiet
    from status + recency) — computed here, not by the model,
  - **related people** (via associations) with roles + per-person recency,
  - **related deals** with stage/amount/close-date + days-in-stage (from `stage_change` entries) +
    each deal's living summary,
  - the **timeline** for the record (its own + its related records' entries, merged, newest-first),
    each entry already shaped for the source card: `type`, `subject`, `summary`, `direction`,
    `source`, `external_id` (→ the "view original" URL), and the linked records,
  - for an org: the composed **brief band** (from `organization.summary` once §4 ships; until then,
    composed from the active deal's summary).
- **Consequences:** new tool → **tool count changes** → update `mcp-smoke`'s assertion, then
  `npm run deploy` + re-upload the deep-view skill (same deploy-before-skill ordering lesson as
  `bulk_import`/`get_pipeline_summary`). Keep it read-only; all writes stay conversational.

Build order when picked up: (1) `core/detail.ts` + smoke coverage; (2) register the tool; (3) the
deep-view skill (`render_*` in the shared "Ledger" identity — mirror the mockup); (4) deploy + upload.
The company living summary (§4) can land in the same pass or just before.

## 7. The "view original" link — one thing to verify on-surface
The source card links out to Gmail/Granola (built from `external_id`). A **user-clicked** hyperlink out
of an artifact *should* work even though the sandbox blocks *programmatic* fetches — but it's unverified.
If outbound navigation is blocked, the fallback is conversational ("ask Claude to pull it up"), which
still fits the model. Worth a quick real-surface test when the deep view goes live.

## 8. Semantic search — parked (future, explicitly not now)
Storing AI summaries is also the substrate for **semantic search** (a headline Attio capability —
`semantic-search-emails/notes/call-recordings`). Rian: **hold off for now**, add later. When we do, it's
**additive, not a storage change**: a `vector` embedding column (Supabase has **pgvector**) on
`interaction` (and ideally person/deal summaries + `organization.description`), an embed-on-write step
in the loop, and a `semantic_search` tool. It's fully **on-model** — we embed the *summary we already
store*, never raw comms — so it preserves the compliance edge (Attio searches raw content; we search
summaries: lower fidelity, lower liability). Two honest caveats for later: (a) embeddings need an
external provider (Anthropic has no first-party embeddings API — points to **Voyage AI**; alternatives
OpenAI/Cohere/open models — *verify current options + pricing at build time*), which means our
summaries egress to that provider; (b) a cheap interim is Postgres **full-text search** over the
summaries (keyword, zero external dependency) before committing to vectors.

## Related
- [notes-design.md](notes-design.md) — the notes/context layer (built): timeline, living summaries,
  the §8b referral graph.
- [commitments-ledger.md](commitments-ledger.md) — §5a's structured-commitments capability.
- [summary-tool.md](summary-tool.md) — the `get_pipeline_summary` pattern `get_record_detail` mirrors.
- [mockups/deep-view-company.html](mockups/deep-view-company.html) — the committed deep-view reference.
