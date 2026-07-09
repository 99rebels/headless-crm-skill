# START HERE — onboarding for a fresh instance

You're picking up an in-progress project. This gets you 0→1: what it is, where we are, and
what's next. Read it fully, then the referenced docs, before acting.

---

## 1. Read these, in order
1. **[docs/concept.md](docs/concept.md)** — what we're building and why: the product, the user, the bet, the (honest) edge, the simple architecture.
2. **[docs/roadmap.md](docs/roadmap.md)** — the build plan, phases, **current status**, key decisions, and open research questions.
3. **[docs/data-model.md](docs/data-model.md)** — the schema and the design rationale (the real source of truth for the schema is `server/db/migrations/0001_init.sql`).
4. **[docs/validation.md](docs/validation.md)** — the market-validation plan (running in parallel; Rian is doing the conversations).
5. **[docs/lessons-v1.md](docs/lessons-v1.md)** — the idea we tried first and killed, the traps not to re-walk, and the competitor scan. Don't re-discover this.

## 2. One-paragraph what-and-why
We're building a **simple, AI-native CRM that lives inside Claude.ai**, for **solo/small "fractional" operators** (independent consultants, fractional execs, agencies, indie founders) who run a relationship pipeline, live in Claude, and find Salesforce/HubSpot heavy and admin-heavy. It has its **own small Postgres database** (we own the substrate), **maintains itself** by reading the user's comms *client-side* and proposing clean updates for approval, and renders views **on demand** via skills instead of a fixed UI. Per-seat subscription. Indie scale: ~100 customers to validate.

## 3. The most important thing to internalise
**This is a pivot.** The first idea ("SKAAS" — serving CRM *skills* over MCP that drive the customer's *own existing* CRM) was killed (thin value, half-competing with the CRM vendors, no moat, broken monetisation — see `lessons-v1.md`). **Now we own the CRM and the database.** If anything you read implies we're a "skills provider that never touches customer data" or "drives the customer's HubSpot," it's stale v1. Key architecture decision: the **self-maintenance loop runs client-side in the user's Claude** (using Claude's scheduled tasks + the user's own comms connectors) — we **never ingest raw comms**, only approved CRM updates. That keeps our compliance surface to ordinary CRM records.

## 4. Where we are now (2026-07-09)
Two parallel tracks:
- **Validation** (Rian, non-code): running conversations with fractional operators. See `docs/validation.md`. The retention question — *"why did you quit your last CRM?"* — matters most.
- **Build** (`server/`): **Phase 0 done, Phase 1 skeleton proven locally.**
  - **Supabase + TypeScript.** Schema (`server/db/migrations/0001_init.sql`) is live in Rian's Supabase.
  - Headless **core** (`server/src/core/` — db, workspace, person) + thin **MCP adapter** (`server/src/mcp/`) for the `contact` object are **built and verified**: `npm run smoke` (core→DB) and `npm run mcp-smoke` (MCP client→tools→core→DB, incl. read-before-write dedup) both pass, and the tools work in the MCP Inspector.
  - Architecture is **headless-core-first**: all logic in `core/` (interface-agnostic); MCP is a thin adapter; a REST API / web UI can be added later as more adapters without a rewrite. See `server/README.md`.

## 5. What to do next
1. **The immediate build milestone: make it reachable from Claude.ai.** Deploy the server publicly + add the OAuth handshake (mandatory on Claude.ai — a v1 finding), then connect it in Claude.ai and operate a contact by talking to Claude. That completes the walking skeleton end-to-end. *Account-gated (hosting is Rian's); you build and guide.*
2. **Only after that full path works, widen** (Phase 3): copy the proven `person` pattern to organizations, deals, interactions, tasks.
3. **The make-or-break remains Phase 2:** the client-side **self-maintenance loop** (comms → dedupe → propose → approve). Hardest tech and the whole differentiator. Build on the dedup seed in `server/src/core/person.ts`.

## 6. How the server works (quick orientation)
- `cd server && npm install`, then `.env` (copy `.env.example`) holds `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (gitignored; never commit).
- `npm run smoke` — verify core CRUD against Supabase. `npm run mcp-smoke` — verify the MCP path. `npm run mcp` — run the stdio server (what the Inspector / a local client connects to).
- Until auth lands, the server uses the service-role key and the **core enforces `workspace_id` scoping** on every query; a "Dev Workspace" is auto-created for local use.

## 7. Working norms Rian expects
- Founder/decision-maker (don@corethings.io), solo. Wants a **partner + builder** and **honest pushback, not cheerleading.** Challenge weak reasoning; mark bets as bets. (This whole direction exists because that pushback killed a weak idea and found a better one.)
- **Indie scale is the frame.** ~100 customers is a win. Don't drift toward the funded outbound/GTM lane — the calm system-of-record niche is the point.
- **Verify current APIs/markets, don't trust training data.** **Feasibility ≠ desirability** — validate pull, don't mistake a working demo for traction.
- **Verify your work by running it** (the smoke tests exist for this). Keep the schema/scope small; resist clutter.
- Account-gated steps (hosting, connectors, real data) are **Rian's to run**; you can't see his Claude.ai session — he's your eyes on-surface.
