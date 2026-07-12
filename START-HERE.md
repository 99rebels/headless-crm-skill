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
6b. **[docs/summary-tool.md](docs/summary-tool.md)** — how the dashboard's `get_pipeline_summary` tool works, why (the consistency fix), its limits, and a **post-demo redesign** parking note. Read before extending the tool or building a 2nd view.
7. **[docs/validation.md](docs/validation.md)** — the market-validation plan (Rian runs the conversations).
8. **[docs/lessons-v1.md](docs/lessons-v1.md)** — the idea we tried first and killed. Don't re-walk the traps.

## 2. One-paragraph what-and-why
We're building a **simple, AI-native CRM that lives inside Claude.ai**, for **solo/small "fractional" operators** (independent consultants, fractional execs, agencies, indie founders) who run a relationship pipeline, live in Claude, and find Salesforce/HubSpot heavy and admin-heavy. It has its **own small Postgres database** (we own the substrate), **maintains itself** by reading the user's comms *client-side* and proposing clean updates for approval, and renders views **on demand** via skills instead of a fixed UI. Per-seat subscription. Indie scale: ~100 customers to validate.

## 3. The most important thing to internalise
**This is a pivot.** The first idea ("SKAAS" — serving CRM *skills* over MCP that drive the customer's *own existing* CRM) was killed (thin value, half-competing with the CRM vendors, no moat, broken monetisation — see `lessons-v1.md`). **Now we own the CRM and the database.** If anything you read implies we're a "skills provider that never touches customer data" or "drives the customer's HubSpot," it's stale v1. Key decision: the **self-maintenance loop runs client-side in the user's Claude** (their own Gmail/Calendar connectors) — we **never ingest raw comms**, only approved CRM updates. That keeps our compliance surface to ordinary CRM records.

## 4. Where we are now (2026-07-12)
**⏰ Deadline:** Rian demos an MVP **Monday 2026-07-13** to an advisor — a solo operator who *tried and failed to build this himself*, and whom we want to build for. Two tracks:
- **Validation** (Rian, non-code): conversations with fractional operators. The retention question — *"why did you quit your last CRM?"* — matters most.
- **Build:** **all three demo pillars are built, the risky one is proven, and this session hardened the dashboard + gave both view-skills a real visual identity.**

**① The CRM — live on Claude.ai.** Full relationship model — **contacts + organizations + deals + associations**, **16 MCP tools**. Headless **core** (`server/src/core/`, interface-agnostic) behind two thin adapters over the *same* core: a local **stdio** MCP and a deployed **Cloudflare Worker** (OAuth auto-approve). Supabase Postgres. Verified locally (`npm run smoke`, `npm run mcp-smoke` — both green) and end-to-end on Claude.ai. Workspace resolves lazily (a DB blip can't break the connection). *One migration since init: `0002_deal_closed_at.sql` (applied).*
  - **NEW — `get_pipeline_summary` (the consistency fix).** The dashboard's *facts* (pipeline value, counts, deals bucketed by stage incl. an "Unstaged" bucket, the roster with real recency, recently-won, and attention `signals`) are now computed **once, server-side in `core/summary.ts`** — so every model shows identical numbers. Born from finding the *same* prompt returned three different dashboards across Haiku/Sonnet/Opus (a calculation + a label + a judgement all diverged). Principle now settled: **if it's arithmetic or a lookup, `core` does it; the model only writes prose.** Vocabulary (stages/order, lifecycle, `self.emails`, `default_currency`) lives in **`workspace.settings`** — data, not code.

**② Self-maintenance enrichment — built + PROVEN** (`skills/crm-enrichment/`, the make-or-break). One skill, two client-side sources (**Gmail + Google Calendar**) feeding a shared core: scope → classify vs CRM → extract → reconcile → **approval digest (HTML)** → approve in chat → write via MCP tools. Guardrails are *executed rules*. Status:
  - **Live-tested on a real, noisy Gmail** and **stress-tested** (`docs/enrichment-eval.md`): 6 adversarial scenarios × Haiku 4.5 / Sonnet 5 / Opus 4.8. One model-independent bug found + fixed; re-run = **zero critical failures** (91/92/92). **Discovery passed on all models.**
  - *This session:* fixed a latent gap — `last_interaction_at` was not writable through the core/tools, so the loop could never actually refresh recency; now settable via `update_contact`/`update_organization`.
  - **Granola as a 3rd source: evaluated + parked.** It has an official MCP + a public REST API; it's the *smallest* integration to add because the loop is multi-source by design. Not for the demo. Treat it as *a source we read*, never a platform we depend on (it's VC-funded and drifting toward CRM — sherlock risk).

**③ Views — redesigned this session, one identity ("Ledger").** Both the **dashboard** (`skills/crm-dashboard/`) and the **enrichment digest** now share a warm-paper / pine-green calm-ledger design (full light/dark + an in-page theme toggle), built as **~20 CSS tokens** so a future "pick your look" customisation at bundle-time is nearly free.
  - **Dashboard** is now **interactive** (presentation-only — the artifact sandbox has no network): four tabs (**Focus / Pipeline / People / Momentum**), a click-to-drill **detail drawer**, live search, a clickable "Open deals" tile, and a hand-built SVG trend chart. It **lands on Focus** — the ranked "needs you now" brief (the thesis made visible: the CRM surfaces the work). All *writes* still happen in the conversation via MCP; the drawer says so.
  - **Digest** stays deliberately plain (a decision surface): monogram avatars, state chips, a header tally, and the one conflict quarantined in amber. Previews: `skills/*/sample-*.html`. Design explorations live only as artifacts (not committed).

**Delivery:** both skills ship as **bundled zips** (`skills/*.zip`, gitignored — regenerate by zipping the folder; **rebuilt this session**). Uploaded via claude.ai → Customize → Skills → Create skill → Upload.

## 5. What's left
The build is demo-complete; remaining work is **Rian's account-gated steps + rehearsal**.
1. **Deploy + re-upload (ordering matters).** The new dashboard skill calls `get_pipeline_summary`, which only exists after a deploy. So: migration `0002` is applied ✅ → `cd server && npm run deploy` → **re-upload both rebuilt zips** on claude.ai. Uploading the dashboard zip *before* deploying would call a tool that isn't live yet.
2. **Live tests on the demo account** (`99rebels.info@gmail.com`): re-run "show me my pipeline" across the three models — **facts should now be identical** (only the Focus wording varies), with the enriched recency showing. Plus the calendar enrichment live-test. (Gmail enrichment + discovery already passed.)
3. **Demo prep:** the story is *enrich from email/calendar → approve digest → dashboard reflects it → nudge list*. The demo workspace already has enriched recency (David 2d / Sarah 3d / Tom 9d / Jordan 31d-quiet / Priya new) and a genuine **unstaged** Acme deal that showcases the tool's edge-case handling. Rehearse; record a fallback video. Be honest about real vs. prototype. *(Note: rename the demo workspace from "Dev Workspace" to something real.)*
4. **Being considered (not committed):** a per-account **"deep view"** skill, launchable by a **button inside the artifact** via `window.claude.complete()` (verified real; caveat: that call has no MCP/CRM access unless we embed the data or MCP-from-artifact works — worth a spike). And a fuller pipeline board (Proposal stage is empty).

*(Deferred, not for the demo — see roadmap: cron/scheduling, real auth & multi-tenancy, the compliance gate, tasks/interactions objects, and the standalone HTTP API. The core is already adapter-agnostic, so that API is a clean future add.)*

## 6. How it works (orientation)

**Server** (`cd server && npm install`; `.env` from `.env.example` holds `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`, gitignored):
- `npm run smoke` (core→DB) · `npm run mcp-smoke` (MCP client→tools→core→DB) · `npm run seed` (demo before-state, idempotent) · `npm run inspect` (read-only snapshot of a workspace) · `npm run mcp` (stdio server for the Inspector).
- **Deploy:** `npm run deploy` (Cloudflare Worker; `npm run cf-build` = dry-run). Live at `headless-crm-mcp.rianoleary.workers.dev/mcp`; connected in Claude.ai as a custom connector (auto-approve, no creds).
- **Architecture:** all logic in `core/` (env-agnostic; each adapter calls `initDb(url,key)`). The core enforces `workspace_id` scoping (service-role key bypasses RLS for now; a "Dev Workspace" auto-resolves). **Adapters are thin** — no business logic leaks into MCP/HTTP, which is what keeps a future REST API a clean drop-in. **Aggregation/derived views also live in `core`** (`core/summary.ts` → `get_pipeline_summary`) — the pattern for "compute facts once so all callers agree."
- **To add an object's tools:** write `core/<object>.ts` (mirror `person.ts`), register in `src/mcp/build.ts`'s `registerCrmTools`, `npm run typecheck` + smoke (both `smoke` and `mcp-smoke` — the latter asserts the tool count), then `npm run deploy`.

**Skills** (`skills/`, delivered as zips, **script-heavy** — deterministic work in Python, model only for judgment). Both view-skills render self-contained HTML artifacts in the shared **"Ledger"** identity (the design system = the CSS token block at the top of each `render_*.py`; keep the two in sync). Interactivity is presentation-only — the artifact sandbox has no network, so CRM writes always go back through the conversation/MCP.
- `crm-enrichment/` — `SKILL.md` (the loop) · `config.json` (self/scope/ignore/vocab) · `scripts/render_digest.py` (the approval digest) · `eval/eval-workflow.mjs` (repeatable stress-test) · `demo-*.md` · `sample-*` (previews).
- `crm-dashboard/` — `SKILL.md` (step 1 = call `get_pipeline_summary`; the model only adds the `focus` list) · `scripts/render_dashboard.py` · `sample-state.json` (the tool's output + a Focus list) · `sample-dashboard.html` (preview).
- Rebuild a zip: `cd skills && zip -rq crm-dashboard.zip crm-dashboard -x '*.DS_Store' -x '*/__pycache__/*'` (same for `crm-enrichment`).

## 7. Working norms Rian expects
- Founder/decision-maker (don@corethings.io), solo, **unfamiliar with CRMs/this architecture** — so *teach* and *recommend*, don't just execute. Wants a **partner + builder** and **honest pushback, not cheerleading.** Mark bets as bets. (This whole direction exists because that pushback killed a weak idea.)
- **Indie scale is the frame.** ~100 customers is a win. Don't drift toward the funded outbound/GTM lane — the calm system-of-record niche is the point.
- **Verify current APIs/markets/model facts, don't trust training data.** **Feasibility ≠ desirability** — a working demo isn't traction.
- **Verify your work by running it** (smoke tests, the eval, `inspect`). Keep the schema/scope small; resist clutter.
- Account-gated steps (hosting, connectors, real data, claude.ai) are **Rian's to run** — he's your eyes on-surface. Commit + push when he asks; the repo is on GitHub (`99rebels/headless-crm-skill`).
