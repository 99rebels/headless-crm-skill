# Lessons from v1 (the abandoned idea) — read so we don't repeat it

*We spent the first stretch of this project on a different idea and killed it on 2026-07-09. It's captured here so the specific traps don't get re-walked. (The v1 throwaway code and demo artifact have been removed to declutter; they remain in git history if ever needed.)*

---

## What v1 was

"**SKAAS**" — skills-as-a-service. We would author CRM skills (dedup, pipeline briefs, hygiene, follow-ups) and **serve them over MCP** to the customer's Claude. The skills would run **client-side** and drive the customer's *own existing* CRM connector (HubSpot) and comms. We would be a *skills-and-logic provider, never a data processor* — customer data would never touch our servers. The moat was supposed to be a "maintenance treadmill" (keeping skills current as APIs drift) + distribution + neutrality.

## Why we killed it

The founder lost conviction, and the concept doc's own honest caveats, stacked up, made the case:
1. **No real value / half-competing.** We'd be rebuilding what the CRM vendors now ship natively (HubSpot Breeze auto-populates and does approve-first deal progression — our exact planned UX; Attio is AI-native). We were a thin layer *on top of* a platform we were also *half-competing with*. Bad seat.
2. **No moat.** The concept doc admitted it: *"none of (a)–(d) is a true structural moat."* We'd also **deliberately given up** the one compounding asset (data network effects) by refusing the data path — so nothing accumulated.
3. **The beachhead could DIY it.** Our target (agent-native, cron-capable) was precisely the segment most able to wire a CRM MCP to Claude themselves.
4. **Monetisation was structurally broken.** Charging for skills/tools over MCP is a mess: per-call pricing rewards agent inefficiency (agents loop/re-query, 10–100× infra load), MCP defines no metering/payment primitives, and free MCP servers have burned $50–75k/month. There was no clean way to charge.
5. **Green spikes created false confidence.** Spikes A & B "passed" — but they only proved **feasibility** (we *can* serve skills and render a nice dashboard), never **desirability** (anyone *needs* it). We kept deferring the one cheap test that mattered (talk to real users).

## The traps to never repeat

- **Don't build a thin layer on a platform you also compete with.** If the platform can ship your feature natively, you have no position. Own the substrate or own a workflow they won't.
- **Feasibility ≠ desirability.** A working demo proves the machine runs, not that the market wants it. **Validate pull before building the mechanism.** (This is now doubly important because the new build is bigger.)
- **Pick a monetisable shape up front.** "How do we charge, and is that model sane?" is a first-order question, not a later detail. Per-call-over-MCP failed this; per-seat-subscription-on-our-own-product passes it.
- **Marks-as-bets discipline is only useful if you act on it.** We correctly labelled the psychographic "unvalidated" — then didn't validate it for weeks. Label *and* test.
- **Watch for false momentum from tooling wins.** Deploys, connectors, and pretty artifacts feel like progress; they aren't traction.

## What actually carried forward (worth keeping)

- **Skills-as-UI works.** We proved a skill can drive a connector and render a genuinely good, self-contained HTML dashboard in-agent, better than the CRM's own view (demonstrated with a real generated dashboard, since removed). The new product reuses this: **skills generate views on demand.** This is the one piece of v1 that survives intact.
- **Discovery is a model decision.** Serving things over MCP, the model must *choose* to invoke them; reliability rests on always-in-context tool descriptions + a bootstrap, not on lazily-loaded item descriptions. Relevant if we ever expose skills/tools the model must pick among.
- **Guardrails must be executed, not prose.** A rule the model only reads is only as safe as the model obeying it. Carried into the new product as a core principle (self-maintenance safety depends on it).

## The competitive landscape we found (2026-07) — still relevant to the new idea

The AI-native CRM space is **real, funded, and crowded** — which validates demand but means "nobody's doing this" is false:
- **Cluster / getcluster.ai** (a16z speedrun) — literally "the headless CRM for Claude & Codex." Started pure-headless, then **added a UI back** and **tilted to GTM/outbound orchestration** (50+ lead sources, LinkedIn/email sending, hundreds of prospecting subagents). Tells us where the *money* pulls (outbound) and that pure no-UI wasn't enough alone.
- **Day.ai** — ex-HubSpot founder, $20M Series A (Sequoia). AI-native "CRMx," its own SaaS app. Outbound/GTM lean.
- **Twenty** — open-source (AGPL), Postgres, native MCP, "designed for AI." $43M funded; **HubSpot's founder is an angel.** The category's strongest validation — and why we chose *not* to build on it (AGPL + heavyweight + they're building the AI layer themselves = sherlock risk).
- **Salesforce Headless 360** — the incumbent going headless: 60+ MCP tools, browser "optional." Proof that "incumbents can't follow" is *false* — it's a lead-time window, not a wall.
- **Breakcold / Common Room** — sales/buyer-intelligence tools going headless/MCP.

**The seam we're aiming at:** everyone funded is chasing **outbound/GTM** (premium, easy to justify "50 more deals"). The **calm system-of-record for solo/fractional operators who hate CRM admin** is the lane they walk past. Smaller, lower-WTP — which is exactly why it's uncontested and fine for a solo needing ~100 customers.
