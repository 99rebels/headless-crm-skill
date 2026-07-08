# SKAAS — Concept, Strategy & Architecture

*Standalone 0-to-1 onboarding doc. Read this end to end before touching anything. It explains **what we're building and why** — the enduring idea, not the current task list. The companion doc `skaas-spikes.md` covers what we're testing right now.*

*Tone note: this is written to be honest, not to sell. Settled decisions are marked as such. Live bets and unvalidated assumptions are marked as such. Do not mistake one for the other.*

---

## 1. The concept in one paragraph

Sales teams own a CRM and hate maintaining it — the data-entry tax means records go stale, and stale records make forecasts and follow-ups worthless ("good data in, good data out" is the whole game). SKAAS is a set of **agent skills that turn a CRM into a headless, self-populating backend the user operates from inside the AI they already use every day (Claude.ai)** — not from the CRM's own UI, and not from yet another SaaS app. The user connects their comms (email, calendar, calls) and their CRM; on a schedule, an agent gathers ground truth, proposes clean, deduped updates, the user approves them, and they get written back. The CRM stops being the place you go and becomes a database Claude reads from and writes to. **Delivery is skills served over MCP, not a SaaS app** — hence "SKAAS," skills-as-a-service.

## 2. The problem we're attacking

The pain is real, expensive, and well-documented:
- Reps spend hours per week on manual CRM entry — pure overhead that doesn't sell anything.
- A large share of CRM data is inaccurate or stale as a result.
- When deal stages aren't current, "the forecast is fiction" — managers can't trust their own pipeline.
- Managers fight a losing battle getting reps to actually update records.

This is the "shit in, shit out" problem: a CRM is only as valuable as the data in it, and the act of getting good data in is exactly the work everyone avoids. Solving *data capture without the human doing data entry* is the prize.

## 3. Our two differentiators

Others attack this problem (see §8). Our shape is different in two specific ways:

1. **Headless / bring-your-own-agent.** The product lives in the customer's *existing* agent surface (Claude.ai). No new app to learn, no new chatbot to log into. The CRM becomes headless — operated from the agent, not its own UI.
2. **Delivery as skills, not SaaS ("SKAAS").** The capability is served as skills over an MCP connection — a frictionless expansion of a tool the customer already uses, not a separate product with its own login and UI.

## 4. The core bet (read this twice)

We are **building where the puck is going, not for today's TAM.** Stated plainly so it can be judged:

> Every popular CRM will become AI-native and auto-populate itself. We cannot stop that and we are not trying to. Instead we bet that a growing segment of users will want to **live in their agent (Claude), treat the CRM as a writable backend, and never open the CRM's clunky UI** — and that serving those users as skills-over-MCP is a better wedge than competing on capture mechanics.

This is a **deliberately small, forward-leaning TAM**, and we accept that. The plan is to build it, maintain it as APIs drift, and let it sit until the segment grows into it. We are not chasing the mass-market sales rep yet (see §5).

## 5. Who we target — the two-circle Venn (strategy + TAM rationale)

The beachhead is the **intersection** of two groups. Neither alone; the overlap.

**Circle 1 — customers who already have a framework that can schedule crons.**
Claude routines / scheduled agents, third parties like Track, or their own runtime. This matters because the product's real value is the *continuous, ambient* gather-and-propose loop, and a continuous loop needs something firing on a schedule. By **selecting for customers who bring their own cron runtime, we offload the hosting of that loop to them** — we don't have to host it ourselves yet. Small group today, expected to grow as scheduling becomes seamless.

**Circle 2 — customers who don't want their CRM to be the center of their data.**
People who find the CRM UI clunky, already live in Claude, and would rather access and update their CRM from the agent — often via a CRM MCP they've *already* connected. For them the CRM is a system of record, not a home.

**Why the intersection, and why we accept the small TAM:**
- These are early-adopter, agent-native operators. They forgive rough edges and are reachable.
- Circle 1 removes our hardest near-term infra dependency (hosting the loop) by construction.
- Circle 2 is the psychographic the whole product is designed around.
- We are explicitly **not** optimizing for the largest number of CRM-hating reps today, because most of them aren't in an agent surface at all, and the ones who are can't yet run crons easily. Both constraints are expected to relax over time. We build ahead of that.

## 6. Surface decision (settled): Claude.ai

**We build and promote for Claude.ai, and leave it there for now.**
- Claude.ai supports end-user **custom connectors via remote MCP** on Free/Pro/Max/Team/Enterprise (Free is capped at one connector; on Team/Enterprise an Owner adds the connector, then members enable it). Setup is a name + URL, optionally OAuth — low friction. ([setup](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp), [build](https://support.claude.com/en/articles/11503834-build-custom-connectors-via-remote-mcp-servers))
- **Design implication:** Claude reaches our MCP server *from Anthropic's cloud*, so the server must be **publicly hosted and reachable**. We run infra from day one, even for read-only. There is no purely-local, no-server version of this.
- We are not spreading to ChatGPT/Slack/etc. yet. Those are later expansions that cost architectural purity (on Slack, "skills the user connects" becomes "a hosted app," and the headless framing weakens).

## 7. Architecture (settled)

### The critical insight — and the two choices that fall out of it
A skill's text can be (a) copied by a user asking the model to echo it, and (b) executed unreliably by whatever model the customer runs. Two responses, and we have deliberately chosen where we land on each:

1. **Copyability → we ACCEPT it.** Skill text is public. The moat is not the text (see §8, §11). We do not contort the architecture to hide prompts.
2. **Data liability → we REFUSE it.** We do **not** route customer CRM/comms data through our servers. We are a **skills-and-logic *provider*, not a data *processor*.** Execution runs client-side, in the customer's own agent/runtime, against the customer's own CRM and comms connectors. Data stays between the customer and their systems; we never see it.

So the architecture splits cleanly by *what touches data*:

> **Our server serves and governs skills. The customer's agent executes them against the customer's own data. The two never mix.**

```
Customer's agent (Claude.ai)
   │   connects, side by side:
   │
   ├──► OUR MCP server ── skills + governance ONLY, never customer data:
   │       • Skill library (served on demand; model discovers + pulls a skill)
   │       • Versioning / updates (the SaaS value)
   │       • Per-customer access / entitlements / revocation
   │       • Usage metering / billing
   │       • The integration-maintenance treadmill (skills tracked to API drift)
   │
   └──► the customer's OWN connectors ── this is where data lives:
           • their CRM MCP (e.g. HubSpot)  ← reads + writes happen here
           • their comms (email / calendar / calls)

Execution happens IN the customer's agent: a loaded skill's logic runs there,
calls the customer's own connectors, uses the customer's own model for fuzzy
judgment, and proposes writes for approval. None of it transits our server.
```

**Why refuse the data path.** The moment CRM data (names, emails, deal values) transits our servers, we become a data processor under GDPR/CCPA — DPAs, breach liability, sub-processor disclosures, security reviews, SOC 2 pressure. For a small/early team that is a heavy, sales-slowing burden. Protecting prompts (which leak anyway and were never the moat) is not worth taking that on. This is a conscious trade — see §10 for what we give up (the data-network-effect moat).

### What runs where
- **Server-side (never sees customer data):** serve skills, version/update, per-customer access control, metering, the maintenance treadmill. That's it.
- **Client-side (in the customer's agent/runtime — all the data-touching work):** reading the CRM/comms, dedup scoring + field mapping, the fuzzy "same entity?" judgment (on the *customer's* model), the auto-write guardrails, and presentation.
- **The deterministic guardrails ship *inside the skills* and run client-side.** Rules like "never auto-merge two records that each have an open deal," "never auto-merge across different email domains without a hard matching signal," or "never auto-write a stage regression without a flag" protect the *customer's own* data integrity — and the customer has no incentive to bypass their own safety — so client-side execution is fine. Yes, they're copyable; that's acceptable (they're safety rules, not a moat).

### The fuzzy judgment runs on the customer's model
The genuinely ambiguous work — "are these the same entity?" (`john@acme.com` vs `jsmith@acmecorp.io`), extracting meaning from messy comms, drafting proposed updates — runs on the **customer's own model**, in their runtime, not one we host. Rationale, now reinforced by the data-processor decision:
- Keeps the gather loop **self-contained in the customer's runtime** (§5, Circle 1) — no dependency on our endpoint.
- Avoids **inference COGS** across every customer's gather cycle.
- **Rides the rising floor** of general model quality.
- **Keeps us out of the data path** — the comms/records never reach a model we operate.

**Safety nuance that still holds:** human-in-the-loop only catches a model that is *unsure* (it flags). It does **not** catch a model that is *confidently wrong* and auto-writes a bad merge. So we don't trust the model's self-reported confidence — the deterministic guardrails above decide what is even *eligible* to auto-write vs. flag. Those guardrails are authored by us and shipped in the skill; they just execute client-side.

*Reversibility:* if per-customer consistency ever becomes a real problem, an **opt-in** hosted-inference option is a later possibility for consenting customers — but it is not a v1 commitment, and the default stays data-light.

### Clarification 2 — read first, then write
- **Read-only** (query the CRM + present it beautifully in Claude) ships first: no write-trust barrier, no dedup risk, no cron dependency. It's the on-ramp — it earns the trust and generates the real, messy data needed to make write good.
- **Write** (gather → dedupe → propose → approve → write back) is the real value and comes second. Ambient write is what makes this "an AI-native CRM in Claude" rather than "a nice CRM viewer."

## 8. Competitive picture & where our edge is — and isn't

**The CRM vendors themselves are the real competitor** — more than the standalone tools:
- **Attio** — the most AI-native CRM, building auto-population natively. (This is why it is *not* our first target.)
- **HubSpot** — **Breeze** auto-populates contact properties from email, has an AI Meeting Notetaker that captures/transcribes calls, auto-fills records, and "Smart Deal Progression" that suggests deal updates on an approve-first model (the same UX we intended); standard enrichment is now free. HubSpot also ships its **own remote CRM MCP server (GA April 2026)**. ([HubSpot AI](https://www.hubspot.com/products/artificial-intelligence), [auto-populate](https://knowledge.hubspot.com/connected-email/automatically-populate-contact-properties-with-hubspot-ai), [HubSpot MCP](https://developers.hubspot.com/ai-tools/mcp))

Standalone competitors:
- **Coffee.ai** — an AI agent that auto-populates Salesforce/HubSpot from email/calendar/calls. It works, but it **traps the user in Coffee's own app** and does not serve Attio.
- **Carly** — event-driven CRM updates, but a general Zapier-style automation SaaS with its own UI.

**Not our edge:**
- **The capture mechanism** (extracting structured data from comms) — commoditizing fast; table stakes, not a differentiator.
- **Raw CRM access from Claude** — the vendors ship their own MCP servers now; we can't win by providing a pipe they also provide for free.

**What actually is our edge (weaker than "moat," on purpose):**
- **(a) The judgment layer, as authored + maintained logic** — dedup / entity-resolution / mapping / approval-guardrail logic that's reliably better than a CRM's bolt-on, with ambiguous cases *flagged, not guessed*. Note: this ships as skills and runs client-side, so its value is **authorship quality + staying current**, not secrecy. Any single snapshot is copyable; the ongoing quality and maintenance are not. (We deliberately forgo the data-network-effect version of this edge — see §10 — because we never see customer data.)
- **(b) Cross-source and (later) cross-CRM neutrality — strengthened by being data-light.** A single vendor structurally can't match this: its AI only sees its own connected data and is incentivized to lock you in, never to unify across sources/CRMs or help you switch. We can be the neutral layer above any source and any CRM — and because we never capture the data, we're a *safer* neutral party than a vendor whose business is owning it.
- **(c) The in-agent experience** — making the CRM genuinely nicer to use from Claude than from its own fixed UI.
- **(d) The integration-maintenance treadmill** — CRM APIs drift; we absorb that ongoing work so the customer doesn't. "Moat by tedium" — unglamorous but it's why people buy integration products instead of building them. **With the data-light stance, this + distribution + the relationship carry most of the weight.**

**Honest caveat:** none of (a)–(d) is a true structural moat. They're advantages of *focus, quality, neutrality, and maintenance*. A funded competitor could copy a snapshot of the skills; they cannot copy the treadmill, the distribution, or the relationship without doing the ongoing work. We win by owning a niche they don't prioritize and moving faster — a distribution-and-focus bet, which is legitimate early-stage strategy as long as we don't pretend the architecture alone protects us.

## 9. First CRM (decision): HubSpot

Chosen *under the §4–5 thesis* (not under a "find a CRM that hasn't solved this" thesis, which HubSpot would fail):
- It fits Circle 2 by construction: a HubSpot user who has connected HubSpot's own MCP to Claude is *already* "accessing their CRM from the agent." Their existing MCP is **plumbing we build on top of**, not competition to route around.
- Large install base → more of the target psychographic exists within it.
- API is workable for a per-customer model: OAuth 2.1 + PKCE, ~100–110 requests / 10s per installing account, OAuth apps up to ~1M calls/day, marketplace distribution. ([API limits](https://developers.hubspot.com/docs/developer-tooling/platform/usage-guidelines))
- **Alternative consciously set aside:** *Pipedrive* was the cleaner, uncontested wedge (sales-rep-native, simpler API, not AI-forward, likely no official MCP pre-empting us). We chose HubSpot because, under this thesis, HubSpot's native AI + own MCP are *enablers* of the target behavior rather than blockers, and the target psychographic is larger. Revisit Pipedrive if HubSpot's native effort crowds us out faster than expected.

## 10. Key risks & live assumptions (record these; do not treat as solved)

1. **The DIY paradox.** Our beachhead segment (agent-native, cron-capable) is precisely the segment most able to wire a CRM MCP to a Claude routine themselves. *Live bet:* we assume scheduling crons becomes seamless and non-technical over time, so the "we save you the wiring" value erodes and our value must live in the **quality of the authored judgment logic + the maintenance treadmill + distribution**, not the orchestration. Founder's position: this is *true today but won't be a major problem long-term.* **Logged as an assumption we lean on, not a proven fact.** If it's wrong, the product must be worth paying for purely on judgment quality and maintenance.
2. **The core psychographic is unvalidated.** Everything rests on "people who have a CRM, live in Claude, and would rather not open the CRM" being real and growing — not a projection of how we'd like to work. Cheap to test: find 3–5 real people who say this today, before building much.
3. **Near-term overlap with HubSpot's own push into Claude.** A vendor will build the Claude-native experience for its own CRM. Expect v1 to feel like it's racing HubSpot's native effort; our real separation (cross-CRM/cross-source neutrality) only appears once we're multi-CRM.
4. **We host infra regardless — but it's a skills server, not a data pipeline.** "No SaaS" means "no separate UI the user logs into," *not* "no server." We run a publicly hosted MCP server that serves and governs skills (Claude.ai connects to it from Anthropic's cloud, so it must be public; Spike A confirmed it also requires OAuth). But it carries skills, access, and metering — **never customer CRM/comms data**, which stays in the customer's own runtime and connectors.
5. **Data-light by choice — the conscious trade.** By never processing customer data we shed almost all data-processor liability (GDPR/CCPA, DPAs, breach exposure, security reviews) — a real sales and risk win. What we give up: (a) the **data-network-effect moat** — we can't accumulate cross-customer correction data or enrichment, so that "compounding data asset" edge is off the table unless we later add opt-in, consented processing; and (b) some **execution-quality control** — running on the customer's own model/runtime means reliability varies per customer. Both are accepted deliberately; the moat rests on treadmill + distribution + relationship + neutrality instead.

## 11. Guardrails & product principles (enduring)

- **Never silent-write ambiguous data.** Anything uncertain gets flagged for human approval, not guessed. The intended UX is a morning approval digest.
- **Read before write.** Always check for an existing record before creating one.
- **Treat skill text as public.** No secrets, no proprietary logic in any skill markdown — assume it will be echoed.
- **Auto-write eligibility is gated by deterministic guardrails, not by the model's self-reported confidence.** The customer's model does the linguistic judgment; deterministic rules we author (shipped in the skill, run client-side) decide what is even allowed to auto-write vs. flag (see §7).
- **We are a skills-and-logic provider, not a data processor.** Customer CRM/comms data never transits our servers; execution runs in the customer's own agent/runtime against their own connectors. (See §7 and the §10 trade.)
- **The defensible value lives in what a snapshot can't copy:** the integration-maintenance treadmill (skills kept current as APIs drift); distribution / presence in the surface the customer already uses; the accountable, data-light vendor relationship (access control, versioning, support); and cross-source / cross-CRM neutrality. **Not** the skill text (public), **not** hidden server-side logic (there is none that touches data), **not** accumulated customer data (we never hold it). Design as if every skill is public — because it is.
