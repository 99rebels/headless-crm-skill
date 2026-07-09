# The Product — Concept, Strategy & Architecture

*Standalone 0→1 doc. What we're building and why. Written to be honest, not to sell: settled calls are marked settled, bets are marked bets. If this contradicts anything in the old `skaas-*` docs, this wins — those described a different, abandoned idea (see `lessons-v1.md`).*

---

## 1. The concept in one paragraph

Most people who need to track relationships and a light sales pipeline **hate CRMs** — Salesforce and HubSpot are overkill, confusing, and demand constant manual data entry that nobody does, so the data rots. We're building a **simple, AI-native CRM that lives inside Claude.ai** for **solo and small "fractional" operators** (independent consultants, fractional execs, small agencies, indie founders). You operate it by talking to Claude — no separate app to open, no forms to fill. It has its **own small database** (we own the substrate), and its defining feature is that **it maintains itself**: it reads your email/calendar, figures out who's who, and proposes clean updates for a one-tap approval. Skills generate the views (a pipeline dashboard, an account brief) **on demand**, rendered in-agent, instead of a fixed UI you navigate.

## 2. The problem

- Existing CRMs are built for sales *teams* and priced/architected accordingly; for a solo operator they're heavy, expensive, and mostly empty because keeping them current is a chore.
- The chore is the whole problem. Relationship/personal CRMs (Dex, Monica, spreadsheets) don't die from lack of features — they die because **manual upkeep is tedious and people abandon it.** Retention, not acquisition, is the category killer.
- So the prize is a CRM that **stays accurate without the human doing data entry**, and that you reach from where you already work (Claude), not one more app to check.

## 3. Why now (the bet, stated plainly)

> CRM history is a story of **distribution shifts, not feature innovation** — mainframe → Siebel on-prem → Salesforce SaaS. Each wave was the same core features on a new surface, and each opened the category to people the old surface excluded. We bet the **next surface is the AI agent**: a growing group will run their system-of-record *from inside Claude* rather than a GUI, and a CRM built **native to that surface** (not ported to it) can ride that shift — while the thing that finally kills the upkeep-chore (AI self-maintenance) makes the calm, no-admin CRM actually stick for the first time.

Marked as a **bet**, not a fact. It rests on two unproven assumptions (see §8).

## 4. Who we target (settled: the beachhead)

**Solo / small fractional operators** — independent consultants, fractional CxOs, boutique agencies, indie founders — who:
- run a **relationship pipeline** (clients, prospects, partners, investors), not a high-volume outbound machine;
- already **live in Claude** day-to-day;
- find Salesforce/HubSpot absurd for their size and mostly limp along on a spreadsheet or their inbox;
- feel the pain as **lost time on admin** (for a consultant, unbilled admin = lost billable hours).

We are **not** chasing sales teams or the outbound/GTM-orchestration lane (that's where the funded competitors are — see `lessons-v1.md` §competitors). We want the calm system-of-record niche they walk past because it can't justify a venture return. At our scale (see §6) that's a feature.

## 5. What makes it different (and where the edge is / isn't)

1. **It maintains itself.** Auto-capture from comms → entity resolution → proposed updates for approval. This is the differentiator *and* the hardest technical bet — they're the same thing (§8).
2. **It lives in Claude, UI generated on demand.** No fixed app; skills render exactly the view the task needs. Incumbents are anchored to their GUIs and can't easily match "no app at all" without cannibalising themselves — a real, if temporary, edge.
3. **Opinionated for one niche.** A horizontal platform can't nail one segment's workflow the way a focused product can.

**Honest on the edge:** none of these is a permanent structural moat. Big incumbents are already going headless/agentic (Salesforce Headless 360). Our advantages are **focus, speed, niche relationship, and being native-in-Claude first** — legitimate for a solo, but they are *lead-time* advantages, not walls. We win by owning a niche nobody funded will prioritise and moving faster.

## 6. Scale & business model (settled shape, numbers are bets)

- **Indie / bootstrapper scale, by design.** ~100 paying customers to *validate*; roughly 3–5× that (~$10k MRR) to *sustain* one person full-time. Small TAM is acceptable — we're not raising, we're building a focused micro-SaaS.
- **Monetise like a CRM, not like an MCP tool: per-seat subscription.** This matters — charging per-tool-call over MCP is a broken model (agents loop and re-query; metering sub-cent calls is a nightmare; free MCP servers have burned five-figures/month on infra). Because we **own the product and the data**, we charge a normal monthly subscription for the CRM. Owning the substrate is what makes it monetisable.
- Likely shape: a low monthly price for solo, a small per-seat price for tiny teams. Exact pricing is unresolved and not urgent — validate demand first.

## 7. Architecture (intentionally simple)

The whole point is that this is **small**. A relationship CRM is a handful of tables, not a platform.

```
Claude.ai (the surface the user operates from)
   │  connects to:
   ▼
OUR MCP server  ──►  OUR database (Postgres)
   • CRUD tools over a small data model:
       people · organisations · interactions · follow-ups/deals
   • skills that render views on demand (pipeline brief, account view)
   • the self-maintenance loop: read comms → resolve entities → propose writes → approve → write
```

- **We own the database.** Unlike the abandoned v1, customer data lives in *our* store. That brings back switching-cost/lock-in (a real moat ingredient) but also makes us a **data processor** — GDPR/CCPA, security, backups, uptime for someone's system of record. That responsibility is unavoidable in this model; walk in eyes-open.
- **Keep the schema tiny.** Resist becoming a general CRM platform. The value is the self-maintenance + the in-Claude experience, *not* schema breadth.
- **Deliberately NOT built on Twenty** (the open-source AGPL CRM). Great validation that the category is real, but rejected as a base: AGPL drag, a heavyweight stack we don't need, and Twenty is itself building the AI-native layer (sherlock risk). See `lessons-v1.md`.
- **Self-maintenance guardrails must be *executed* checks, not prose.** A guardrail the model merely "reads" is only as reliable as the model obeying it; make it run verification and show reconciliation. This is load-bearing for retention (a confidently-wrong auto-update erodes the trust the whole product depends on).

## 8. Key risks & live assumptions (do not treat as solved)

1. **The core psychographic is unvalidated.** "Solo operators who live in Claude and would rather run their CRM there than in an app, and will pay for it" — must be shown real, not assumed. Cheapest and most important thing to test. See `validation.md`.
2. **Retention is the real risk, not acquisition.** The category dies from the upkeep-chore. Everything rests on self-maintenance being *good enough* to break that. If it's only 80% good, users still feel the chore and churn like every relationship CRM before them. Validate the *reason people quit their last CRM*, not just whether they'd try ours.
3. **Self-maintenance is the hardest tech and the whole differentiator at once.** Entity resolution + safe auto-writes on messy comms, with confidently-wrong merges blocked by deterministic rules. Unproven at quality.
4. **Lead-time moat only.** Incumbents are moving headless/agentic; our separation is focus + speed + niche, and it's a window, not a wall.
5. **We're now a data processor.** Owning the substrate brings liability and security obligations we previously designed *around*. Real cost, accepted deliberately.

## 9. Guardrails & principles (enduring)

- **Never silent-write ambiguous data.** Uncertain → flagged for one-tap approval, never guessed. The intended UX is a light approval digest.
- **Read before write.** Always check for an existing record before creating one.
- **Guardrails are executed verification, not emphatic prose.** Safety comes from rules that run, not the model's self-reported confidence.
- **Keep it simple and niche.** Every temptation to generalise the schema or chase the outbound market is a temptation to become the thing we're differentiating against.
- **Own the relationship and the data responsibly.** The defensible value is focus, the in-Claude experience, self-maintenance quality, and trust — not secrecy.
