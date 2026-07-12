# Roadmap — what we're building, in what order

*The working build plan. Read `concept.md` for the why and `validation.md` for the parallel market work. This is the how + the sequence. Status (2026-07-12): all three demo pillars built; the make-or-break loop live- and stress-tested; skill discovery passed on claude.ai. The two view-skills now share a real visual identity ("Ledger"), and the dashboard's facts are computed by a server-side tool (`get_pipeline_summary`) so they're identical across models. Remaining before the demo = Rian's account-gated deploy + live tests + rehearsal. Validation running in parallel.*

---

## 1. Settled decisions (don't relitigate without a reason)

- **We own the CRM + a small Postgres database.** Not a layer on someone else's CRM (that was v1 — see `lessons-v1.md`).
- **The self-maintenance loop runs CLIENT-SIDE, in the user's own Claude.** We never ingest the user's raw email/calendar. The loop uses the user's *own* comms connectors, and only the resulting **proposed CRM updates** reach our server. This is the single biggest liability-reducing decision in the product.
- **Scheduling = Claude's native scheduled tasks.** The user's scheduled task fires the loop client-side. We do not host a cron/runtime. (Closes the old "where does the loop run" question.)
- **Skills are core to the product** (they're the UX — views generated on demand), not optional.
- **Preferred skill delivery: over our MCP** (for central versioning/updates) — but this is **gated on a research spike** (§4), because MCP-served skills may compete with local/native Claude Skills. Fallback if it's unreliable: bundle skills as files. (Central updatability is now a *convenience*, not the moat, so the fallback is acceptable.)
- **Monetisation: per-seat subscription** on our own product (not per-call-over-MCP, which is broken — see `lessons-v1.md`).
- **Scale: indie.** ~100 customers to validate, ~$10k MRR to sustain. Keep the schema and scope small.
- **Facts are computed in `core`, not by the model (2026-07-12).** A read-heavy view (the dashboard) gets its numbers/buckets/joins from ONE deterministic MCP tool (`get_pipeline_summary`), so every model shows identical facts; the model only adds the *judgement* layer (the ranked "Focus" list, anchored to the tool's `signals`). Triggered by finding the same prompt returned three different dashboards. Rule of thumb: if it's arithmetic or a lookup, the server does it; the model only writes prose. **Vocabulary lives in `workspace.settings`** (data, not code). **The tool is deliberately parked for a post-demo redesign** — it works but is a bespoke single view; see [`summary-tool.md`](summary-tool.md) for how it works, its limits, and the open question (per-view tools vs. a general query layer).
- **The two view-skills share one design system ("Ledger").** Warm-paper/pine-green calm-ledger identity, full light/dark, ~20 CSS tokens — so a future "pick your look" customisation at bundle-time is nearly free. The dashboard is interactive (tabs, drill-down drawer, search, chart) but presentation-only; all writes stay in the conversation via MCP.

## 2. What we're building — component map

**The spine (commodity — build clean, don't gold-plate)**
1. **Data model** — people · organisations · interactions · follow-ups/deals. Small, durable, get-it-right-once (expensive to change with live data).
2. **Persistence + infra** — Postgres + hosting; **multi-tenant isolation model** is an early decision (lean: row-level security to start, revisit).
3. **Service/API layer** — CRUD + query + validation + auth. Thin; its shape is driven by what the MCP/skills need, not designed in a vacuum.
4. **MCP server** — CRUD tools over the API + (pending §4) the skill library. **OAuth mandatory** (Spike A: authless fails on Claude.ai). Keep tools context-window-light (Cluster's complaint: "CRM MCPs torch your context window").

**The moat (risky + valuable — de-risk EARLY, not last)**
5. **Self-maintenance loop (client-side)** — runs in the user's Claude on a scheduled task: reads their comms via their own connectors → resolves entities / dedupes → proposes writes → user approves → writes to our MCP. Guardrails are **executed verification, not prose**. This is the differentiator, the retention bet, and the hardest tech — all one thing.
6. **Skills layer** — view-rendering skills (pipeline brief, account view — reuse the skills-as-UI approach proven in v1) + the self-maintenance workflow skill. **Principle: script-heavy.** Do deterministic work (filter, count, dedupe-match, format) in code; reserve LLM interpretation for the genuinely fuzzy part (entity-resolution judgment, summarising prose). Cheaper *and* more reliable — same logic as executed guardrails, and it controls token/context cost.

**The obligations (unavoidable now we own the data — but reduced by the client-side loop)**
7. **Auth & identity** — user accounts, the OAuth handshake for the MCP connection.
8. **Security & multi-tenant isolation** — encryption at rest, secrets, tenant separation.
9. **Compliance / data governance** — GDPR/CCPA for **CRM records** (personal data, but NOT raw comms — the client-side loop keeps comms out of our systems). DPA, privacy policy, data residency, retention/deletion. Full compliance is a gate *before the first paying customer*, but data-residency/encryption/tenancy choices are shaped now.

*(Note: the old workstream "comms connectors" is largely GONE — the client-side loop uses the user's own connectors. Nice simplification.)*

## 3. The architecture, in one picture

```
User's Claude.ai
  ├─ their OWN comms connectors (email/calendar)         ← raw comms stay here, never reach us
  ├─ a scheduled task  ──fires──►  our self-maintenance SKILL (runs client-side):
  │                                  read comms → resolve/dedupe → propose updates → approve
  │                                                 │
  └─ OUR MCP connector  ◄───────────────────────────┘ writes approved updates only
         • CRUD tools over OUR Postgres (people/orgs/interactions/deals)
         • skill library (pending §4 research) — view + workflow skills
                 │
                 ▼
         OUR server: Postgres (CRM records only) + skill serving/versioning
```

## 4. Open research questions (resolve via testing, not assertion)

**R1 — Skill discovery & priority. [RESOLVED FOR THE DEMO — 2026-07-11]**
Delivery = **bundled skill zips** (the accepted fallback). Discovery was tested on claude.ai across models (`docs/discovery-test.md`) and **passed on all of them** — Claude reliably finds and invokes the right skill (crm-enrichment vs crm-dashboard) from a natural request, no collisions. The description field + explicit cross-referencing disambiguation was the lever. Still open *longer-term:* central updatability for solo users (bundled zips don't auto-update) and the "bake behaviour into tool output" alternative if discovery ever wobbles at scale. Original open questions kept below for history:
- Does co-locating CRM tools + skill library on one connector aid discovery or add noise?
- Is an MCP **Prompt** (or Resource) a better skill-delivery primitive than the `get_skill` **tool** approach used in Spike A?
- Can the loop *reliably* invoke OUR skill under a scheduled task, not a local one or an improvisation?
- **Design alternative to test:** bake presentation/behavior instructions into the MCP tool's *output* (skill rides along with the tool result) — no separately-discovered skill object to compete. May dissolve the problem.
- **Fallback if unreliable:** ship skills as bundled files (lose central updates, keep reliability).

**R2 — MCP context-window weight.** How many/how granular can CRUD tools be before they bloat the context (Cluster's warning)? Informs tool design.

**R3 — Multi-tenant isolation model.** Row-level security vs schema-per-tenant vs db-per-tenant for our scale + compliance. Decide before Phase 3.

**R4 — Compliance specifics.** Minimum viable GDPR/CCPA posture for holding CRM personal data as a solo operator: DPA template, data residency (EU users?), retention/deletion, sub-processor list. Understand now, implement before first paying customer.

## 5. Phased plan (priority order)

> **⏰ MVP demo sprint (Fri–Sun, for a Mon 2026-07-13 demo).** Near-term ordering differs from the long-term phases below: (1) widen tools to the *demo-necessary* set — organizations + deals + associations + dashboard reads (not exhaustive CRUD); (2) on-demand auto-enrichment (start early — it's the risk + the wow); (3) the dashboard/pipeline view skill; (4) polish + rehearse + fallback recording. See `START-HERE.md` §5 for the detailed steps.


- **Phase 0 — ✅ DONE:** data model designed + validated against Salesforce/HubSpot/Attio (`data-model.md`); tenancy = row-level security to start (R3); R1 downgraded (skills-over-MCP is a convenience, file-bundle fallback is fine).
- **Phase 1 — ✅ DONE (live on Claude.ai):** schema live in Supabase; headless **core** + **two adapters** (local stdio + deployed Cloudflare **Worker**, OAuth-wrapped). Now the **full relationship model** — contacts + organizations + deals + associations, **16 MCP tools** (added `get_pipeline_summary`, the deterministic dashboard aggregator). Workspace resolves lazily (a DB blip can't break the connection). Verified locally (`smoke` + `mcp-smoke`) + end-to-end on Claude.ai. *(One migration since init: `0002_deal_closed_at.sql`.)*
- **Phase 2 — ✅ DONE + PROVEN (the make-or-break):** the client-side self-maintenance loop (`skills/crm-enrichment/`) over **Gmail + Google Calendar**. **Live-tested on a real noisy inbox** and **stress-tested** across Haiku 4.5 / Sonnet 5 / Opus 4.8 (`docs/enrichment-eval.md`) — one model-independent bug found + fixed; re-run = zero critical failures. Scheduled-task automation deferred (on-demand is enough for the demo). *(Also fixed a latent gap: `last_interaction_at` is now writable via core + `update_contact`/`update_organization`, so the loop can actually refresh recency.)* **Granola as a 3rd source is evaluated + parked** (it has an official MCP + REST API; smallest of the integrations because the loop is multi-source by design — see the START-HERE notes).
- **Phase 3 — mostly done:** the **pipeline dashboard** (`skills/crm-dashboard/`, now tool-driven + interactive) and the **approval digest** are built and share the Ledger identity. Still deferred: a **per-account "deep view"** skill (design discussed; a button in the artifact could launch it via `window.claude.complete` — being evaluated), and the *other* objects' tools (interactions, tasks).
- **Phase 4 — productionize (deferred):** multi-tenant hardening, real auth, security, compliance gate — before the first paying customer with real data.

## 6. Deliberately deferred (don't let these expand early phases)

Pricing specifics, billing infra, marketing site, SSO/enterprise features, multi-CRM anything, a web UI beyond generated views, scale/perf hardening. Real, but later.
