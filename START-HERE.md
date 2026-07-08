# START HERE — SKAAS onboarding for a fresh instance

You're picking up an in-progress project. This doc gets you 0→1: what to read, where we
are, and what to do next. Read it fully, then read the referenced files before acting.

---

## 1. Read these, in order
1. **[skaas-concept.md](skaas-concept.md)** — the enduring idea, strategy, and architecture.
   *What the product is, who it's for, why, and how it's built. Settled decisions vs. live bets are marked.*
2. **[skaas-spikes.md](skaas-spikes.md)** — the de-risking test plan (Spikes A–D) and the logged result of Spike A.
3. **[spikes/spike-a-mcp/](spikes/spike-a-mcp/)** — the working MCP server we built and deployed (see §4 below).

That's genuinely enough to understand everything. The rest of this doc is orientation.

## 2. One-paragraph what-and-why
SKAAS turns a CRM into a headless, self-populating backend the user operates from **inside Claude.ai**
(not the CRM's UI, not a new SaaS app). Skills are served over **MCP**. The target user lives in their
agent and wants the CRM as a writable backend, not a home. First CRM: **HubSpot**. See the concept doc for
the full strategy — do **not** relitigate it; know which parts are bets (concept-doc §10).

## 3. The single most important architectural decision (recent — internalize it)
**We are a skills-and-logic PROVIDER, not a data PROCESSOR.** Customer CRM/comms data **never transits our
servers**. Our server only serves + governs skills (library, versioning, access, metering, maintenance).
**All data-touching execution runs client-side** in the customer's own agent/runtime, against the
customer's **own** connectors (their HubSpot MCP, their email, etc.), using the customer's **own** model for
fuzzy judgment. Deterministic guardrails are authored by us but ship *inside the skills* and run client-side.
Corollary: **skill text is public** — the moat is the maintenance treadmill + distribution + relationship +
neutrality, never secrecy or hoarded data. This is concept-doc §7/§8/§10/§11. If anything you read elsewhere
implies our server processes customer data, it's stale — this decision wins.

## 4. Where we are now
- **Spike A: PASSED** (2026-07-08, tested on Claude.ai web). We proved skills can be served from behind an MCP
  connector and discovered/pulled/executed by the model on demand, with the text never on the customer's disk.
- **What's live:** a throwaway Cloudflare Worker MCP server at `spikes/spike-a-mcp/`, deployed at
  `https://skaas-spike-a.rianoleary.workers.dev` (endpoint `/mcp`). It exposes `list_skills` + `get_skill`
  over 3 sample skills (`src/skills.ts`) and is wrapped in OAuth (auto-approve, **spike-only, no real
  accounts** — do not ship as-is). Redeploy with `npm run deploy` from that folder (Cloudflare account is
  `rianoleary`; an `OAUTH_KV` namespace already exists and is bound).
- **Two Spike-A findings that matter:** (1) **authless does NOT work on Claude.ai** — an OAuth handshake is
  mandatory; (2) **discovery is a model *decision*** — reliability rests on the always-visible `list_skills`
  tool description + a bootstrap file (`spikes/spike-a-mcp/bootstrap.md`), not the individual skill
  descriptions. Meta-tool descriptions were hardened and the example-id routing trap removed; these need a
  redeploy to re-test.

## 5. What to test next — Spike B (read + present), reframed data-light
Spike B is the first shippable wedge **and** it validates the load-bearing assumption the data-light pivot
introduced. It answers two things at once:
1. **Can a served skill orchestrate the customer's *separate* connector?** Everything in Spike A was a
   self-contained skill. Now a skill served from *our* MCP must reliably drive the customer's *own* CRM
   connector ("use your HubSpot connector to pull open deals, then present them"). It's all tools in one
   context, so it *should* work — but it's the crux of the client-side model and isn't proven yet.
2. **Is the generated view *clearly better* than opening the CRM?** If a generated HTML/markdown brief isn't
   obviously nicer than the CRM's own UI, the read wedge isn't a wedge — say so.

### Suggested plan
- **Fast, zero-setup first cut (recommended to start):** if your session has *any* CRM connector available
  (e.g. Attio), prototype a "pipeline brief / account view" skill against its real data to feel out
  presentation quality *now*, before investing in HubSpot setup. Attio isn't the target — this is purely a
  CRM-agnostic mechanism/quality test. Confirm with Rian before pulling his real CRM data.
- **Real target (needs Rian):** stand up a **HubSpot developer/test account with sample data** and connect
  **HubSpot's MCP to Claude.ai**. Then test the genuine wedge: served skill + real HubSpot connector, on
  Claude.ai web.
- **In parallel (highest-value, non-coding):** the biggest *unvalidated* risk is whether the target
  psychographic exists (concept-doc §10.2). Use the Spike B artifact as a demo to put in front of 3–5 real
  "CRM-in-Claude, not CRM-as-home" people. This de-risks the whole bet more than more code does.

Then Spikes C (dedup + write; primary metric = **auto-write-vs-flag ratio**) and D (loop on the customer's own
cron runtime) follow — see the spikes doc. Don't jump to write before B ships narrow.

## 6. Working norms Rian expects
- He's the founder/decision-maker (don@corethings.io); treats the instance as **partner + builder** and wants
  **honest pushback, not cheerleading**. Challenge weak reasoning; mark bets as bets.
- **Verify current APIs, don't trust training data** — HubSpot, Claude.ai connectors, and MCP all move.
- Spikes are **throwaway** — optimize for answering the question, not reuse.
- Account-gated steps (Cloudflare login/deploy, Claude.ai connector, HubSpot setup) are **Rian's to run**;
  you build and guide. You cannot see his Claude.ai web session — he's your eyes for on-surface tests.
