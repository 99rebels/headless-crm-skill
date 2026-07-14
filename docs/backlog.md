# Deferred plans & follow-ups — the checklist

**What this is (2026-07-13):** a single, honest inventory of everything we **speced or flagged but
haven't built** — the "I said I'd come back to this" items scattered across the docs. For each: a
one-line description, **where the plan lives**, **what we have today**, and **what the plan adds**. This
is the concrete checklist; [`roadmap.md`](roadmap.md) §5b is the *themed strategy* behind it. Nothing
here is a commitment to build — it's so a fresh instance (or future you) can see the whole board without
re-reading fifteen docs.

**Legend:** ⬜ not started · 🟡 partially there · 🤔 undecided (needs a call) · ✅ done since the source
doc was written (listed so nobody re-plans it) · ⛔ decided NOT to build (listed so nobody resurrects it).

---

## A · Views & reads

**⬜ Per-account "deep view" skill** — a rich single-record page (company/person/deal): identity, people
with roles, the deal, the living summary as a hero "brief band", and the full timeline with per-entry
"Summary & source" drill-downs.
- *Lives in:* [`source-attribution.md`](source-attribution.md) (full build brief), mockup
  `mockups/deep-view-company.html`, [`roadmap.md`](roadmap.md) §5b theme C.
- *Have:* all the underlying data (timeline, summaries, sources, links, derived recency); ~80% renders today.
- *Adds:* the read-only view skill itself + the composed data tool below.

**⬜ `get_record_detail` tool** — one deterministic MCP call that composes a record's whole view (fields +
description + living summary + related people/deals + merged timeline + derived recency/temperature), so
every model renders the deep view identically.
- *Lives in:* [`source-attribution.md`](source-attribution.md) §6.
- *Have:* the pieces via separate calls (`get_organization` + `find_associations` + `find_timeline_entries` + `find_deals`); the `get_pipeline_summary` pattern to mirror.
- *Adds:* the single composed call (a `core/detail.ts`), so the deep view isn't stitched per-model.

**🤔 Company-level living summary** — a living `summary` on `organization` (symmetric with person/deal):
the current *account state*, rolled up from its people/deals plus company-only facts (funding, reorg,
went-quiet-everywhere).
- *Lives in:* [`source-attribution.md`](source-attribution.md) §4. **Rian likes this.**
- *Have:* `organization.description` (stable identity only); living summaries on person + deal.
- *Adds:* a migration (3 columns) + enrichment maintaining it. Free interim: compose from the deal summary at render time.

**🤔 Structured commitments + the commitments ledger** — capture "my open items / waiting on them" as
*structured data* (owner, text, due, status) at enrichment time, unlocking a cross-record ledger ("what
did I promise, what am I waiting on?").
- *Lives in:* [`commitments-ledger.md`](commitments-ledger.md), [`source-attribution.md`](source-attribution.md) §5a. **Rian revisiting whether v1 gets it.**
- *Have:* commitments live as prose inside the living summary.
- *Adds:* a structured store + extraction; makes the ledger a trivial deterministic read instead of prose-parsing.

**⬜ On-demand custom reports (NL → rendered view)** — "show me X" produces a rendered view on the fly,
the leapfrog over Attio's fixed report builder.
- *Lives in:* [`roadmap.md`](roadmap.md) §5b theme C (recommended sequence item 3).
- *Have:* one hard-coded aggregate (`get_pipeline_summary`); the skills-as-UI render pattern.
- *Adds:* a general "ask for any view" capability — depends on the query-layer question below.

**⬜ `get_pipeline_summary` redesign → a shared aggregation/query layer** — generalise the bespoke
single-view tool into composable `core` helpers when the 2nd view (the deep view) lands.
- *Lives in:* [`summary-tool.md`](summary-tool.md) §6–§7 (the open question: per-view tools vs. a thin general query layer).
- *Have:* one working-but-"primitive" view tool; recency now derives from the timeline (✅ that sub-item is done).
- *Adds:* shared join/money/recency/bucket helpers so new views + a future REST API compose instead of copy-paste. Also flagged: richer/configurable signal rules.

## B · Notes / context-layer follow-ons

**⬜ Referral / connections graph** — person↔person referral/intro edges ("where did my pipeline come
from", "top referrers", "who can warm-intro me to X"). MVP = referral provenance only.
- *Lives in:* [`notes-design.md`](notes-design.md) §8b, [`roadmap.md`](roadmap.md) §5b.
- *Have:* the storage (generic `association` table, arbitrary edge types + jsonb provenance), the enrichment loop as the population engine, and the banked forward-compat (stable `id` on every timeline entry).
- *Adds:* a small edge vocab + loop extraction (human-approved) + multi-hop reads + a network view.

**⬜ Non-record participants + meeting duration on timeline entries** — store external attendees not in
the CRM ("me", a cc'd guest) and meeting length for the source card.
- *Lives in:* [`source-attribution.md`](source-attribution.md) §5b.
- *Have:* record-linked participants (`interaction_link`) + `direction`.
- *Adds:* a nullable `interaction.participants` (jsonb) + a duration/detail field — *only if their absence proves annoying.*

**⬜ Files / attachments** — attach the actual proposal/contract PDF to a deal.
- *Lives in:* [`notes-design.md`](notes-design.md) §5, [`data-model.md`](data-model.md) "Deferred".
- *Have:* nothing (headless has no blob storage; the note *references* a file, doesn't hold it).
- *Adds:* blob storage + an attachment model. Phase 3+.

**⬜ Threaded collaboration comments** — colleagues @-ing each other on a deal.
- *Lives in:* [`notes-design.md`](notes-design.md) §5.
- *Have:* multi-author timeline entries partially cover it (`owner_id` on every entry).
- *Adds:* a comment/thread model. Teams-era; defer.

## C · Getting data in (migration sources)

**⬜ HubSpot migration source** — migrate live from HubSpot, same as Attio.
- *Lives in:* [`roadmap.md`](roadmap.md) §5b theme D, [`crm-migration.md`](crm-migration.md) "Parked/next".
- *Have:* the whole back half is source-agnostic (`bulk_import` + one renderer); HubSpot's connector is live on claude.ai; it exposes structural won/lost (`stage.metadata.isClosed` + `probability`).
- *Adds:* a `build_from_hubspot.py` front half + STEP-0 routing.

**⬜ Salesforce migration** — lowest priority (no visible claude.ai connector → CSV-export fallback works today).
- *Lives in:* [`crm-migration.md`](crm-migration.md) "Parked/next".
- *Have:* Salesforce users can already use the CSV path; SF exposes `IsWon`/`IsClosed` structurally.
- *Adds:* a real integration (or lean on CSV).

**⬜ Large-workspace pull cap + "migrate the rest?" prompt** — `list-records` caps at 50/call; huge
workspaces mean many pages + long pull time.
- *Lives in:* [`crm-migration.md`](crm-migration.md) "Parked/next", [`roadmap.md`](roadmap.md) §5b theme D.
- *Have:* paging to files keeps context flat; no cap/guard.
- *Adds:* a page cap + a resumable "migrate the rest" prompt.

**⬜ Granola / Slack as enrichment sources** — meeting notes (Granola) and Slack as additional readers.
- *Lives in:* [`enrichment-loop.md`](enrichment-loop.md), [`roadmap.md`](roadmap.md) §5b theme B (Granola parked).
- *Have:* the loop is multi-source by design (Gmail + Calendar today); Granola has an official MCP + REST API — the *smallest* add.
- *Adds:* a thin reader per source. Treat Granola as a *source we read*, never a platform we depend on.

**⬜ Factor the two migration builders' shared helpers into one module** — the normalisers/dedupe/
`assemble` are deliberately duplicated between `build_import.py` and `build_from_attio.py`.
- *Lives in:* [`crm-migration.md`](crm-migration.md), [`roadmap.md`](roadmap.md) §5b theme E.
- *Have:* two engines, co-located, `⚠️ DUPLICATION NOTE` headers, a CSV golden test guarding drift.
- *Adds:* one shared helper module — a clock-free refactor once the shape settles.

## D · Enrichment depth

**⬜ Scheduled-task automation** — the loop fires on Claude's native scheduled task, not just on-demand.
- *Lives in:* [`roadmap.md`](roadmap.md) §1 (decided: use Claude's native scheduling) + Phase 2 note (deferred).
- *Have:* on-demand loop works; scheduling is a settled *decision*, not built.
- *Adds:* wiring the loop to a recurring task (no server-side cron — Claude fires it client-side).

**⬜ Richer extraction** — more of the editable surface pulled from comms as the loop matures.
- *Lives in:* [`roadmap.md`](roadmap.md) §5b theme B.
- *Have:* contacts/orgs/deals/associations/timeline/summaries extraction today.
- *Adds:* incremental depth (e.g. commitments if §A adopts it, referral edges per §B).

**🟡 Calendar source live-test** — the calendar reader is built but was flagged "not yet live-tested."
- *Lives in:* [`enrichment-loop.md`](enrichment-loop.md) (line ~116).
- *Have:* built + unit-covered; Gmail path is live-tested. (Timeline-based recency is now the mechanism — re-confirm on a real calendar.)
- *Adds:* an on-surface test pass (a testing task, not a build).

## E · Platform / foundation

**⬜ Real auth & multi-tenancy (Phase 4)** — replace the Path-A Worker-per-tenant shim with a
`tenants`/`api_keys` table + token→workspace resolution + Postgres RLS.
- *Lives in:* [`roadmap.md`](roadmap.md) Phase 4 + R3, [`advisor-instance.md`](advisor-instance.md).
- *Have:* a single shared multi-tenant DB, workspace-scoped in `core`; per-tenant `workspace.settings`; a Worker-per-tenant shim (doesn't scale past a handful).
- *Adds:* real per-user auth + RLS policies. Gate before real scale.

**⬜ Compliance gate (Phase 4)** — minimum-viable GDPR/CCPA posture for holding CRM personal data (DPA,
residency, retention/deletion, sub-processors).
- *Lives in:* [`roadmap.md`](roadmap.md) Phase 4 + R4.
- *Have:* the big liability-reducer already in place (client-side loop → we never hold raw comms).
- *Adds:* the formal posture — a gate *before the first paying customer*.

**⬜ Skills-over-MCP delivery** — serve skills centrally over our MCP (for versioning/auto-update) instead of bundled zips.
- *Lives in:* [`roadmap.md`](roadmap.md) §1 + §4 R1.
- *Have:* bundled skill zips (discovery passed on all models); central updatability is a *convenience*, not the moat.
- *Adds:* central updates — **gated on a research spike** (MCP-served skills may compete with native Skills). Fallback (zips) is acceptable.

**⬜ Facts / provenance table** — which interaction taught us each attribute, with confidence.
- *Lives in:* [`data-model.md`](data-model.md) "Deferred", [`summary-tool.md`](summary-tool.md) §4 (no how-we-know).
- *Have:* hooks in place (`interaction` first-class, `created_from_interaction_id`); the living summary carries `summary_provenance`.
- *Adds:* per-attribute provenance/confidence — deeper than the summary-level provenance we have.

**⬜ User-created custom objects / fields** — let a workspace add its own object types.
- *Lives in:* [`data-model.md`](data-model.md) "Deferred".
- *Have:* the flexible `attributes` jsonb tail on every record.
- *Adds:* first-class custom objects — only when a real cross-user pattern emerges (even Attio defaults to People + Companies). Tension with our lean-core thesis.

**⬜ "Pick your look" theme customization** — bundle-time swap of the Ledger design tokens per customer.
- *Lives in:* [`roadmap.md`](roadmap.md) §1 (Ledger design system).
- *Have:* all three renderers built on ~20 shared CSS tokens — the swap is "nearly free."
- *Adds:* the actual customization mechanism at bundle time.

**⬜ In-artifact "deep view" via `window.claude.complete()`** — a read-only deep view rendered *inside*
the dashboard artifact from embedded data (no tools, no write-back).
- *Lives in:* [`artifact-interactivity.md`](artifact-interactivity.md), [`roadmap.md`](roadmap.md) §1.
- *Have:* verdict that artifact JS *cannot* call our MCP tools (write-back is a dead-end); `complete()` (tool-less) is *unconfirmed*.
- *Adds:* an embedded read-only view — low priority, needs a spike to confirm the API even works.

## F · ✅ Done since a doc called it "deferred" (don't re-plan)

- **Notes as a first-class object + enrichment-maintained** (roadmap §5b themes A/B) — built (phase 2).
- **Full interaction/meeting-note timeline records** (enrichment-loop.md line ~53 called deferred) — built (the timeline).
- **Recency derived from the timeline** (summary-tool.md §6 "smaller win") — built (`getLatestContactMap` max carry-in).
- **Living summaries on person + deal** with provenance — built.
- **Attio "last contacted" carry-in + Attio notes → timeline** — built (phase 2 import).
- **Stable `id` on every timeline entry** (the referral-graph forward-compat bet) — banked.
- **Attio→CRM migration, lifecycle-from-deal derivation** — built earlier.

## G · ⛔ Decided NOT to build (don't resurrect without a reason)

- **Tasks / a checkbox to-do object** — deliberately skipped; pulls toward the admin-heavy CRM feel the thesis rejects. ([`roadmap.md`](roadmap.md) §5b, [`notes-design.md`](notes-design.md) §5.)
- **Storing raw email/meeting bodies** — inverts the client-side compliance edge; we store the AI summary + link only. ([`source-attribution.md`](source-attribution.md) §1, [`data-model.md`](data-model.md).)
- **Storing an "approved excerpt"/quote** — dropped; summary + metadata + link is enough. ([`source-attribution.md`](source-attribution.md) §1.)
- **Expanding our schema to mirror source CRMs' stages/objects** — the mapping layer exists so we *don't* grow the schema. ([`crm-migration.md`](crm-migration.md).)
- **Artifact → CRM write-back (one-click in-artifact button)** — platform dead-end (Anthropic issue closed *not planned*). ([`artifact-interactivity.md`](artifact-interactivity.md).)
- **Server-side cron/runtime for the loop** — scheduling is Claude's native task, client-side. ([`roadmap.md`](roadmap.md) §1.)

---

*Keep this current: when an item ships, move it to §F; when a new "come back to this" flag gets written
into a doc, add it here. This file is the index; the linked docs hold the real design.*
