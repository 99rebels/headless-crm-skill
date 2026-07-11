# START HERE — onboarding for a fresh instance

You're picking up an in-progress project. This gets you 0→1: what it is, where we are, and
what's next. Read it fully, then the referenced docs, before acting.

---

## 1. Read these, in order
1. **[docs/concept.md](docs/concept.md)** — what we're building and why: the product, the user, the bet, the (honest) edge.
2. **[docs/roadmap.md](docs/roadmap.md)** — the build plan, phases, decisions, open questions.
3. **[docs/data-model.md](docs/data-model.md)** — the schema + rationale (source of truth: `server/db/migrations/0001_init.sql`).
4. **[docs/enrichment-loop.md](docs/enrichment-loop.md)** — the self-maintenance loop, the make-or-break feature: architecture + rationale behind `skills/crm-enrichment/`. **Built, live-tested, stress-tested.**
5. **[docs/enrichment-eval.md](docs/enrichment-eval.md)** — how we stress-tested the loop's judgment across models, the one bug it found, and the fix. Includes the repeatable harness.
6. **[docs/discovery-test.md](docs/discovery-test.md)** — the claude.ai protocol for testing whether Claude finds+invokes the right skill (roadmap R1). **Passed on all models.**
7. **[docs/validation.md](docs/validation.md)** — the market-validation plan (Rian runs the conversations).
8. **[docs/lessons-v1.md](docs/lessons-v1.md)** — the idea we tried first and killed. Don't re-walk the traps.

## 2. One-paragraph what-and-why
We're building a **simple, AI-native CRM that lives inside Claude.ai**, for **solo/small "fractional" operators** (independent consultants, fractional execs, agencies, indie founders) who run a relationship pipeline, live in Claude, and find Salesforce/HubSpot heavy and admin-heavy. It has its **own small Postgres database** (we own the substrate), **maintains itself** by reading the user's comms *client-side* and proposing clean updates for approval, and renders views **on demand** via skills instead of a fixed UI. Per-seat subscription. Indie scale: ~100 customers to validate.

## 3. The most important thing to internalise
**This is a pivot.** The first idea ("SKAAS" — serving CRM *skills* over MCP that drive the customer's *own existing* CRM) was killed (thin value, half-competing with the CRM vendors, no moat, broken monetisation — see `lessons-v1.md`). **Now we own the CRM and the database.** If anything you read implies we're a "skills provider that never touches customer data" or "drives the customer's HubSpot," it's stale v1. Key decision: the **self-maintenance loop runs client-side in the user's Claude** (their own Gmail/Calendar connectors) — we **never ingest raw comms**, only approved CRM updates. That keeps our compliance surface to ordinary CRM records.

## 4. Where we are now (2026-07-11)
**⏰ Deadline:** Rian demos an MVP **Monday 2026-07-13** to an advisor — a solo operator who *tried and failed to build this himself*, and whom we want to build for. Wants it ready Sunday eve. Two tracks:
- **Validation** (Rian, non-code): conversations with fractional operators. The retention question — *"why did you quit your last CRM?"* — matters most.
- **Build:** **all three demo pillars are built, and the risky one is proven.**

**① The CRM — live on Claude.ai.** Full relationship model — **contacts + organizations + deals + associations**, **15 MCP tools**. Headless **core** (`server/src/core/`, interface-agnostic) behind two thin adapters over the *same* core: a local **stdio** MCP and a deployed **Cloudflare Worker** (OAuth auto-approve). Supabase Postgres. Verified locally (`npm run smoke`, `npm run mcp-smoke`) and end-to-end on Claude.ai. Workspace resolves lazily (a DB blip can't break the connection).

**② Self-maintenance enrichment — built + PROVEN** (`skills/crm-enrichment/`, the make-or-break). One skill, two client-side sources (**Gmail + Google Calendar**) feeding a shared core: scope (cheap filters) → classify vs CRM → extract → reconcile → **approval digest (HTML)** → approve in chat → write via MCP tools. Guardrails are *executed rules* (never silent-overwrite; worthiness/noise filter; confidence). Status:
  - **Live-tested on a real, noisy Gmail** — extracted correctly, deduped, guardrails fired, the noise filter held (security/Calendly junk declined; zero junk written).
  - **Stress-tested** (`docs/enrichment-eval.md`): 6 adversarial scenarios × Haiku 4.5 / Sonnet 5 / Opus 4.8, Opus-judged. Found one *model-independent* bug (start-date→close-date; verbal→won), **fixed it**; re-run = **zero critical failures**, avgs 91/92/92.
  - **Discovery tested on claude.ai — passed on all models.**

**③ Pipeline dashboard — built** (`skills/crm-dashboard/`). A read-only, on-demand view: pipeline (deals by stage, with linked org/people) + a **"needs a nudge"** strip (the fractional-operator's real pain — dropped relationships). "Harbor" calm-ledger design. Previews in `sample-dashboard.html`.

**Delivery:** both skills ship as **bundled zips** (`skills/*.zip`, gitignored — regenerate by zipping the folder). Uploaded via claude.ai → Customize → Skills → Create skill → Upload. Central skill-updates aren't available for solo users on that path (accepted; see R1 in the roadmap).

## 5. What's left
The build is essentially demo-complete. Remaining work is **Rian's account-gated steps + polish** — you can't see his claude.ai session, so he's your eyes on-surface.
1. **Rian re-uploads the two current zips** and runs the **calendar live-test** + **dashboard live-test** on the demo account (`99rebels.info@gmail.com`). (Gmail enrichment + discovery already passed live.)
2. **Demo prep:** `cd server && npm run seed` writes the "before" state; then the story is *enrich from email/calendar → approve digest → dashboard reflects it → nudge list*. Rehearse the run-of-show; record a fallback video (live AI demos misfire). Be honest about real vs. prototype.
3. **Optional next:** a demo run-of-show doc; more skill polish.

*(Deferred, not for the demo — see roadmap: cron/scheduling, real auth & multi-tenancy, the compliance gate, tasks/interactions objects, and the standalone HTTP API. The core is already adapter-agnostic, so that API is a clean future add, not a rewrite.)*

## 6. How it works (orientation)

**Server** (`cd server && npm install`; `.env` from `.env.example` holds `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`, gitignored):
- `npm run smoke` (core→DB) · `npm run mcp-smoke` (MCP client→tools→core→DB) · `npm run seed` (demo before-state, idempotent) · `npm run inspect` (read-only snapshot of a workspace) · `npm run mcp` (stdio server for the Inspector).
- **Deploy:** `npm run deploy` (Cloudflare Worker; `npm run cf-build` = dry-run). Live at `headless-crm-mcp.rianoleary.workers.dev/mcp`; connected in Claude.ai as a custom connector (auto-approve, no creds).
- **Architecture:** all logic in `core/` (env-agnostic; each adapter calls `initDb(url,key)`). The core enforces `workspace_id` scoping (service-role key bypasses RLS for now; a "Dev Workspace" auto-resolves). **Adapters are thin** — no business logic leaks into MCP/HTTP, which is what keeps a future REST API a clean drop-in.
- **To add an object's tools:** write `core/<object>.ts` (mirror `person.ts`), register in `src/mcp/build.ts`'s `registerCrmTools`, `npm run typecheck` + smoke, then `npm run deploy`.

**Skills** (`skills/`, delivered as zips, **script-heavy** — deterministic work in Python, model only for judgment):
- `crm-enrichment/` — `SKILL.md` (the loop) · `config.json` (self/scope/ignore/vocab) · `scripts/render_digest.py` (the approval digest) · `eval/eval-workflow.mjs` (repeatable stress-test) · `demo-*.md` (demo fixtures/send doc) · `sample-*` (previews).
- `crm-dashboard/` — `SKILL.md` · `scripts/render_dashboard.py` · `sample-*` (preview).
- Rebuild a zip: `cd skills && zip -r crm-enrichment.zip crm-enrichment` (exclude dev files if you want a lean package; the demo docs/samples/eval are dev-only).

## 7. Working norms Rian expects
- Founder/decision-maker (don@corethings.io), solo, **unfamiliar with CRMs/this architecture** — so *teach* and *recommend*, don't just execute. Wants a **partner + builder** and **honest pushback, not cheerleading.** Mark bets as bets. (This whole direction exists because that pushback killed a weak idea.)
- **Indie scale is the frame.** ~100 customers is a win. Don't drift toward the funded outbound/GTM lane — the calm system-of-record niche is the point.
- **Verify current APIs/markets/model facts, don't trust training data.** **Feasibility ≠ desirability** — a working demo isn't traction.
- **Verify your work by running it** (smoke tests, the eval, `inspect`). Keep the schema/scope small; resist clutter.
- Account-gated steps (hosting, connectors, real data, claude.ai) are **Rian's to run** — he's your eyes on-surface. Commit + push when he asks; the repo is on GitHub (`99rebels/headless-crm-skill`).
