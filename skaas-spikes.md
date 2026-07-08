# SKAAS — De-Risking Spikes & Current Plan

*Standalone companion to `skaas-concept.md`. That doc explains **what we're building and why** (the settled idea, strategy, and architecture); this one covers **what we're proving right now**. Read the concept doc first — this assumes it.*

*Where we are: the strategy is settled enough to stop pressure-testing and start proving. We are **not building a product yet.** We are running a small number of throwaway experiments to confirm the load-bearing technical pieces are possible before committing to a v1 scope.*

---

## 1. How to run these spikes

- **Throwaway is fine — optimize for answering the question, not for reuse.** These are de-risking experiments, not v1 code.
- **Prefer the smallest thing that answers the question.** Each spike has one clear question and a success criterion.
- **Verify current APIs, don't assume them.** HubSpot's API, Claude.ai's connector/skill behavior, and the MCP spec all move — check current docs rather than trusting memory or training data.
- **Note blockers and move on.** If a spike surfaces a blocker in something that's out of scope (§4), log it and keep going.

## 2. The spikes

Priority order reflects the strategy: prove the architectural spine first, then the first shippable wedge, then the real value, then the runtime.

### Spike A — skill-library-over-MCP on Claude.ai *(the architectural spine; do first)*
**Question:** From a clean Claude.ai session, loading only one bootstrap connector, can the model discover, pull, and act on the right skill from our library on demand — without the skill files ever living on the customer's disk?
**Build:** A minimal MCP server exposing (a) a way to list/search available skills and (b) a way to fetch a chosen skill's instructions into context. Plus the one bootstrap file/connector a customer loads that tells the model how to use it.
**Success:** From a clean session, loading only the bootstrap, the model lists available skills, selects the correct one, pulls its instructions, and acts on them — with the skill text never on the customer's disk.
**Sub-questions to note:** How does the model *choose* the right skill (naming, descriptions, a router tool)? What must the bootstrap minimally contain? How would per-customer access/revocation work later? Does Claude.ai's connector behavior differ from Claude Code in any way that matters here? *(CRM-agnostic — can be prototyped without a HubSpot sandbox.)*

**RESULT (tested 2026-07-08 on Claude.ai web) — PASSED, with a discovery/routing caveat.**
Built a throwaway Cloudflare Worker MCP server (`spikes/spike-a-mcp/`) exposing `list_skills` + `get_skill` over three sample skills. Verified end-to-end: the model discovers, pulls, and executes a skill from the server on Claude.ai; skill text never touches the customer's disk. Findings:
- **Authless does NOT work on Claude.ai.** The connector flow requires an OAuth handshake (Dynamic Client Registration); a truly no-auth server fails to register. We wrapped the server in Cloudflare's OAuth provider with an auto-approve flow (spike-only, no real accounts) to get past it. OAuth is therefore mandatory on this surface — it's on the real roadmap anyway.
- **Discovery is a decision, not a guarantee (the caveat).** Lazy delivery means individual skills are invisible until the model *chooses* to call `list_skills`. The real reliability lever is the always-in-context `list_skills` **tool description** (must signal *when* to call it) plus the bootstrap file — not the individual skill descriptions, which aren't seen until after discovery.
- **Routing traps:** an example id in the `get_skill` schema let the model shortcut past discovery. Fixed by removing example ids and hardening the meta-tool descriptions.
- **Mitigations chosen:** harden meta-tool descriptions (done) + bootstrap instruction; **server-side routing** (one tool takes user intent, server returns the right skill) is the at-scale answer, deferred until the library is large enough to need it.
- **Open:** measure cold vs. bootstrap discovery rate over repeated runs before over-engineering.

### Spike B — read + present, HubSpot *(the first shippable wedge)*
**Question:** Can we read a customer's HubSpot data (via API and/or their MCP) and render views in Claude that are *clearly better* than opening HubSpot?
**Build:** Pull real records (people, companies, deals) and generate a brief/dashboard as HTML or markdown inside the agent.
**Success:** A generated view a user would genuinely prefer to the CRM UI. If it isn't clearly better, the read wedge isn't a wedge — say so.
**Sub-questions to note:** What's the quality of HubSpot's read API/MCP for this? Where does presentation add real value vs. just re-skinning?

### Spike C — gather → dedupe → propose → write, HubSpot *(the real value; only after A and B look good)*
**Question:** Can a served skill (running client-side, driving the customer's own CRM connector) read from a source, resolve whether the person/company already exists, and create/update the correct records without duplicates or bad mapping — with deterministic scoring + auto-write guardrails shipped in the skill, the fuzzy linguistic judgment on the customer's own model, ambiguous cases flagged not guessed, and no customer data touching our server?
**Build:** A script (plain code first, then refactored toward the MCP-tool shape) that pulls a few sample items from a source → resolves whether the entity already exists in HubSpot → creates or updates the right records → logs what it did. Run it repeatedly to confirm a second run *updates* rather than *duplicates*.
**Success:** Running it twice over overlapping data produces clean, deduped records with correct field mapping — not duplicates or garbage. Entity resolution works on the easy cases; ambiguous cases are flagged, not guessed. **The primary metric is the auto-write-vs-flag ratio** — if most updates need manual approval, we've converted a data-entry tax into an approval tax and the value collapses. "No duplicates" is necessary but not sufficient.
**Sub-questions to note:** How good is HubSpot's API for read-before-write dedup lookups? Rate limits in practice? Where does entity resolution break (same name / different company; email-alias mismatch)? What's the right confidence threshold for auto-write vs. flag?
**Architecture note (data-light — see concept-doc §7):** this runs **client-side**. The served skill drives the customer's *own* CRM connector to read/write, uses the customer's *own* model for fuzzy judgment, and the deterministic dedup scoring + auto-write guardrails are authored by us but ship *inside the skill* and execute in the customer's runtime — **no customer data transits our server.** What we're proving is that this client-side split still produces a clean, deduped result. **Specifically test the "confidently wrong" failure mode:** feed a case a weak model would auto-merge incorrectly, and confirm the *deterministic* guardrail (in the skill) blocks it even when the model is sure — safety must come from the rules, not the model's self-reported confidence.

### Spike D — the loop in a customer's own cron runtime
**Question:** Can the gather-and-propose loop run end-to-end from a customer-side scheduler (a Claude routine / Track), even manually triggered first?
**Success:** A scheduled trigger fires the skill (pulled from our library), which drives the customer's own connectors to gather + propose writes into an approval surface in-agent. *(Note findings on customer-runtime viability vs. eventually needing our own hosting — don't solve hosting here.)*

## 3. What "ship" means

Ship read-only (Spikes A + B) **narrow, to design partners** — to earn trust, real usage, and the messy real data needed to make write good. Reserve the loud "AI-native CRM in Claude" launch for when write (Spike C) works well. **Do not hold all shipping until write is perfect** — read-only is the on-ramp that makes write possible, and "write works well" is a bar you can chase forever.

## 4. Environment / what's needed to start

- A **HubSpot workspace with representative test data** (people, companies, deals) to read/write against safely. *Confirm this exists or create a sandbox first.*
- HubSpot **OAuth app** credentials (OAuth 2.1 + PKCE).
- A **comms source** for Spike C — email or a call-notes export (e.g. Granola). Start with whichever is fastest; stub the other.
- A **publicly hostable environment** for the MCP server (required by Claude.ai's cloud-side connection to it).
- Language/stack is open; Python is a sensible default for the tool logic and MCP server.

## 5. Explicitly out of scope for now

Pricing, packaging, watermarking/anti-piracy, multi-CRM support, hosting the cron loop ourselves, OAuth productionization, multi-tenant security, mass-market (non-Claude.ai) surfaces, and UI polish. These are real and captured elsewhere — do **not** let them expand the spikes. If a spike surfaces a blocker in one of these, note it and move on.

## 6. Open questions to resolve through the spikes (not before)

- Skill discovery/routing mechanism behind one bootstrap MCP connector (Spike A).
- Whether the read/present experience is *clearly* better than HubSpot's UI (Spike B).
- Real-world HubSpot read-before-write dedup quality, and where entity resolution breaks (Spike C).
- The confidence threshold for auto-write vs. flag-for-approval, and the resulting auto-write ratio (Spike C).
- The clean boundary between thin in-context instructions and server-side tools (Spike C).
- Whether the loop is viable on a customer's own cron framework vs. eventually needing our hosting (Spike D — note findings, don't solve).
- Validation of the core psychographic: do 3–5 real "CRM-in-Claude, not CRM-as-home" users exist today? (Not a coding spike, but the cheapest and most important thing to check before building much.)

---

**Bottom line:** Answer, with small throwaway experiments, whether (A) a skill-library-over-MCP works on Claude.ai, (B) read+present clearly beats the HubSpot UI, (C) clean deduped writes with an acceptable auto-write ratio are achievable behind thin skills, and (D) the loop runs on a customer's own cron runtime. Prove or break these before anyone builds a v1.
