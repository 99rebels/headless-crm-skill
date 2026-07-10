# START HERE — onboarding for a fresh instance

You're picking up an in-progress project. This gets you 0→1: what it is, where we are, and
what's next. Read it fully, then the referenced docs, before acting.

---

## 1. Read these, in order
1. **[docs/concept.md](docs/concept.md)** — what we're building and why: the product, the user, the bet, the (honest) edge, the simple architecture.
2. **[docs/roadmap.md](docs/roadmap.md)** — the build plan, phases, **current status**, key decisions, and open research questions.
3. **[docs/data-model.md](docs/data-model.md)** — the schema and the design rationale (the real source of truth for the schema is `server/db/migrations/0001_init.sql`).
4. **[docs/enrichment-loop.md](docs/enrichment-loop.md)** — the self-maintenance loop (Phase 2, the make-or-break): architecture + rationale behind `skills/crm-enrichment/`. Built, not yet live-tested on real email.
5. **[docs/validation.md](docs/validation.md)** — the market-validation plan (running in parallel; Rian is doing the conversations).
6. **[docs/lessons-v1.md](docs/lessons-v1.md)** — the idea we tried first and killed, the traps not to re-walk, and the competitor scan. Don't re-discover this.

## 2. One-paragraph what-and-why
We're building a **simple, AI-native CRM that lives inside Claude.ai**, for **solo/small "fractional" operators** (independent consultants, fractional execs, agencies, indie founders) who run a relationship pipeline, live in Claude, and find Salesforce/HubSpot heavy and admin-heavy. It has its **own small Postgres database** (we own the substrate), **maintains itself** by reading the user's comms *client-side* and proposing clean updates for approval, and renders views **on demand** via skills instead of a fixed UI. Per-seat subscription. Indie scale: ~100 customers to validate.

## 3. The most important thing to internalise
**This is a pivot.** The first idea ("SKAAS" — serving CRM *skills* over MCP that drive the customer's *own existing* CRM) was killed (thin value, half-competing with the CRM vendors, no moat, broken monetisation — see `lessons-v1.md`). **Now we own the CRM and the database.** If anything you read implies we're a "skills provider that never touches customer data" or "drives the customer's HubSpot," it's stale v1. Key architecture decision: the **self-maintenance loop runs client-side in the user's Claude** (using Claude's scheduled tasks + the user's own comms connectors) — we **never ingest raw comms**, only approved CRM updates. That keeps our compliance surface to ordinary CRM records.

## 4. Where we are now (end of 2026-07-09)
**⏰ Deadline:** Rian demos an MVP to someone **Monday 2026-07-13**; wants it ready **Sunday eve**. See §5.

Two parallel tracks:
- **Validation** (Rian, non-code): running conversations with fractional operators. See `docs/validation.md`. The retention question — *"why did you quit your last CRM?"* — matters most.
- **Build** (`server/`): **Phase 1 COMPLETE — the CRM is LIVE and operable from Claude.ai.**
  - **Supabase + TypeScript.** Schema (`server/db/migrations/0001_init.sql`) live in Rian's Supabase.
  - **Headless-core-first architecture:** all logic in `server/src/core/` (interface-agnostic — db, workspace, person), exposed through **two thin adapters** over the *same* core: a local **stdio** MCP (`src/mcp/`) and a deployed **Cloudflare Worker** (`src/worker/index.ts`). Tools are shared via `registerCrmTools`.
  - **Deployed & working end-to-end:** the Worker (`headless-crm-mcp`, OAuth-wrapped, reusing Spike A's auto-approve flow) is live on Cloudflare, connected in Claude.ai, and **verified by creating a contact by talking to Claude.ai** → row written to Supabase. The deploy+OAuth milestone is done.
  - Verified locally too: `npm run smoke` (core→DB) and `npm run mcp-smoke` (MCP client→tools→core→DB, incl. read-before-write dedup) both pass; tools also work in the MCP Inspector.
  - **Only the `contact` object has tools so far.** Core CRUD exists for person + workspace; organizations/deals/etc. are schema-only, no tools yet.

## 5. What to do next
Toward the Monday MVP demo, in order:
1. **Widen tools to the demo-necessary set: `organizations` + `deals` + `associations`, plus the read tools the dashboard needs.** Copy the proven `person` pattern (core module → `registerCrmTools`). This makes it a functioning relationship CRM. **Cap it there** — don't build exhaustive CRUD (tasks, every delete/list variant) that won't appear in the demo. Redeploy with `npm run deploy`.
2. **On-demand auto-enrichment (the make-or-break + the wow).** A skill/flow that takes a set of emails → extracts contacts/companies/deal signals → dedupes against the CRM via read-before-write → writes updates. Client-side, on-demand (no cron needed for the demo). Start this *early* — it's the risk. Build on the dedup seed in `server/src/core/person.ts`. For a reliable demo, feed it a **prepared set of realistic emails**, not a live messy inbox.
3. **The dashboard/pipeline view skill** — reuse the skills-as-UI approach proven in v1 (a skill renders a self-contained HTML view of live CRM data).
4. **Polish:** seed a realistic demo scenario, rehearse the flow, record a fallback video (live AI demos misfire). Be honest in the meeting about what's real vs. prototype.

*Small hardening worth doing before the demo:* the Worker resolves the workspace in `init()` (during connection) — make it lazy (resolve on first tool call) so a DB hiccup can't break the connection.

*(Deferred, not for the demo: cron/scheduling, real auth/multi-tenancy, compliance gate, the other objects. See `docs/roadmap.md`.)*

## 6. How the server works (quick orientation)
- `cd server && npm install`. `.env` (copy `.env.example`) holds `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (gitignored; never commit).
- **Local/dev:** `npm run smoke` (core→DB) · `npm run mcp-smoke` (MCP path) · `npm run mcp` (stdio server for the Inspector / a local client).
- **Deploy to Claude.ai:** `npm run deploy` (Cloudflare Worker). Secrets set once via `npx wrangler secret put SUPABASE_URL` / `…SERVICE_ROLE_KEY`. `npm run cf-build` does a dry-run bundle without deploying. Live at `headless-crm-mcp.rianoleary.workers.dev/mcp`; connect it in Claude.ai as a custom connector (no OAuth creds to enter — auto-approve). The OAuth flow reuses `@cloudflare/workers-oauth-provider`; the KV + Cloudflare account already exist.
- The core is env-agnostic: each adapter calls `initDb(url, key)` at startup (stdio from `process.env`, Worker from the Worker env). Until auth lands, it uses the service-role key and the **core enforces `workspace_id` scoping**; a "Dev Workspace" is auto-resolved.
- **To add an object's tools:** write `core/<object>.ts` (mirror `person.ts`), add tool registrations to `src/mcp/build.ts`'s `registerCrmTools`, `npm run typecheck` + smoke, then `npm run deploy`.

## 7. Working norms Rian expects
- Founder/decision-maker (don@corethings.io), solo. Wants a **partner + builder** and **honest pushback, not cheerleading.** Challenge weak reasoning; mark bets as bets. (This whole direction exists because that pushback killed a weak idea and found a better one.)
- **Indie scale is the frame.** ~100 customers is a win. Don't drift toward the funded outbound/GTM lane — the calm system-of-record niche is the point.
- **Verify current APIs/markets, don't trust training data.** **Feasibility ≠ desirability** — validate pull, don't mistake a working demo for traction.
- **Verify your work by running it** (the smoke tests exist for this). Keep the schema/scope small; resist clutter.
- Account-gated steps (hosting, connectors, real data) are **Rian's to run**; you can't see his Claude.ai session — he's your eyes on-surface.
