# Roadmap — what we're building, in what order

*The working build plan. Read `concept.md` for the why and `validation.md` for the parallel market work. This is the how + the sequence. Status: pre-build, validation running in parallel. Updated 2026-07-09.*

---

## 1. Settled decisions (don't relitigate without a reason)

- **We own the CRM + a small Postgres database.** Not a layer on someone else's CRM (that was v1 — see `lessons-v1.md`).
- **The self-maintenance loop runs CLIENT-SIDE, in the user's own Claude.** We never ingest the user's raw email/calendar. The loop uses the user's *own* comms connectors, and only the resulting **proposed CRM updates** reach our server. This is the single biggest liability-reducing decision in the product.
- **Scheduling = Claude's native scheduled tasks.** The user's scheduled task fires the loop client-side. We do not host a cron/runtime. (Closes the old "where does the loop run" question.)
- **Skills are core to the product** (they're the UX — views generated on demand), not optional.
- **Preferred skill delivery: over our MCP** (for central versioning/updates) — but this is **gated on a research spike** (§4), because MCP-served skills may compete with local/native Claude Skills. Fallback if it's unreliable: bundle skills as files. (Central updatability is now a *convenience*, not the moat, so the fallback is acceptable.)
- **Monetisation: per-seat subscription** on our own product (not per-call-over-MCP, which is broken — see `lessons-v1.md`).
- **Scale: indie.** ~100 customers to validate, ~$10k MRR to sustain. Keep the schema and scope small.

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

**R1 — Skill discovery & priority: MCP-served skills vs local/native Claude Skills. [HIGHEST — gates the skill-delivery decision]**
When both a relevant local Skill and a relevant MCP-served skill exist, which does Claude invoke? Is there source-priority, or pure relevance? Sub-questions:
- Does co-locating CRM tools + skill library on one connector aid discovery or add noise?
- Is an MCP **Prompt** (or Resource) a better skill-delivery primitive than the `get_skill` **tool** approach used in Spike A?
- Can the loop *reliably* invoke OUR skill under a scheduled task, not a local one or an improvisation?
- **Design alternative to test:** bake presentation/behavior instructions into the MCP tool's *output* (skill rides along with the tool result) — no separately-discovered skill object to compete. May dissolve the problem.
- **Fallback if unreliable:** ship skills as bundled files (lose central updates, keep reliability).

**R2 — MCP context-window weight.** How many/how granular can CRUD tools be before they bloat the context (Cluster's warning)? Informs tool design.

**R3 — Multi-tenant isolation model.** Row-level security vs schema-per-tenant vs db-per-tenant for our scale + compliance. Decide before Phase 3.

**R4 — Compliance specifics.** Minimum viable GDPR/CCPA posture for holding CRM personal data as a solo operator: DPA template, data residency (EU users?), retention/deletion, sub-processor list. Understand now, implement before first paying customer.

## 5. Phased plan (priority order)

- **Phase 0 — ✅ DONE:** data model designed + validated against Salesforce/HubSpot/Attio (`data-model.md`); tenancy = row-level security to start (R3); R1 downgraded (skills-over-MCP is a convenience, file-bundle fallback is fine).
- **Phase 1 — 🟡 IN PROGRESS (skeleton proven locally):** schema live in Supabase; the headless **core** (`server/src/core/`) + thin **MCP adapter** (`server/src/mcp/`) for the `contact` object are **built and verified** — `npm run smoke` (core→DB) and `npm run mcp-smoke` (client→tools→core→DB, incl. read-before-write dedup) both pass, and the tools work in the MCP Inspector. **Remaining:** deploy the server publicly + add the OAuth handshake so it's reachable from **Claude.ai**, then operate a contact by talking to Claude. *Only after that full path works do we widen (Phase 3).*
- **Phase 2 — self-maintenance spike (EARLY):** prove entity-resolution + safe-write quality on real comms for one flow, client-side, on a scheduled task. The make-or-break. Build on the read-before-write dedup seed already in `server/src/core/person.ts` (against our own DB). If this can't be made reliable, the product is dead — learn it here, cheaply.
- **Phase 3 — widen:** full data-model CRUD (organizations, deals, interactions, tasks — copy the proven `person` pattern), the view-rendering skills, the approval UX/digest.
- **Phase 4 — productionize:** multi-tenant hardening, security, compliance gate — before the first paying customer with real data.

## 6. Deliberately deferred (don't let these expand early phases)

Pricing specifics, billing infra, marketing site, SSO/enterprise features, multi-CRM anything, a web UI beyond generated views, scale/perf hardening. Real, but later.
