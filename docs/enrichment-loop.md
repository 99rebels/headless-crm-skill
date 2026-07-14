# The enrichment loop (self-maintenance) — architecture & rationale

*The **why** behind `skills/crm-enrichment/`. The skill's `SKILL.md` is the operational how (what the
model does at runtime); this doc is the design rationale a new **builder** needs. Read `concept.md`
§5/§8 and `roadmap.md` §2/§5 (Phase 2) for where this sits. Status at bottom.*

> **Update 2026-07-14 — the loop now maintains the context layer (phase 2).** Beyond field updates, the
> loop now (a) logs each processed email/meeting as a **timeline entry** (AI summary only, never raw
> body; `source`+`external_id` make re-runs idempotent) and (b) maintains a **living summary** per
> person/deal. Recency is now *derived* from contact-type timeline entries (it no longer hand-sets
> `last_interaction_at`). So where this doc says meeting/interaction records are "deferred," read
> "built" — see the digest's new "Logged to your timeline" + "Living summaries" sections, and
> [`notes-design.md`](notes-design.md).

---

## What it is and why it matters

This is the **self-maintenance loop** — the product's differentiator, retention bet, and hardest
tech, all one thing. A relationship CRM dies from the **upkeep chore**; this loop is what removes it.
It reads the user's email, figures out who's who, and proposes clean updates for one-tap approval, so
the CRM stays accurate without manual data entry. If this isn't *good enough*, users still feel the
chore and churn — so quality here is the whole ballgame (`concept.md` §8.2–8.3).

## The one architectural decision that shapes everything: it runs client-side

The loop runs **in the user's own Claude**, using **their own connectors** (Gmail, Google Calendar).
Raw email/event content is read there and **never reaches our server** — only the *approved,
structured* CRM updates do. This is the single biggest liability-reducing decision in the product: it
keeps our compliance surface to ordinary CRM records, not raw comms (`roadmap.md` §1). **Never** route
raw email/event content through the CRM server. That's why the loop is a *skill* (client-side), not a
server job.

## Sources feed one shared core

The second load-bearing decision: **sources are pluggable; the core is shared.** Each source (Gmail,
Calendar, later Slack/Granola) is a thin *reader* that emits candidate facts. They all flow into one
source-agnostic **core** — reconcile → digest → approve → write.

```
SOURCES (readers, source-specific)          CORE (shared, source-agnostic)
  Gmail:    scope → classify → read → extract  ┐
  Calendar: scope → extract attendees/dates    ┼─►  reconcile (dedupe ACROSS sources)
  (Slack…)                                     ┘        → render digest → approve → write
```

Why one skill with internal source-split, **not** separate skills per source: (a) Claude skills can't
share code across bundles — separate skills would duplicate the renderer + reconcile logic; (b)
**cross-source dedup needs a single reconcile pass** — the same person from an email *and* a calendar
invite must collapse to one proposal, which is impossible if sources run as isolated skills; (c) one
calm approval digest is the product's UX, not two. Adding a source = adding a reader module in
`SKILL.md`; the core is untouched.

- **Token discipline (Gmail):** filter on *cheap* metadata (from/subject/snippet) first; only fetch
  full bodies for survivors. We do **not** gate on "already in the CRM" — discovering *new*
  people/companies is half the value; the CRM lookup only *classifies* create-vs-update and supplies
  the existing record as context.
- **Calendar's contribution:** attendees → new contacts/orgs (deduped by email/domain), and a past
  meeting refreshes when you last spoke to someone, which powers the dashboard's "who haven't I talked
  to in a while." *(Updated 2026-07-14: this now flows through a logged **timeline entry** — the
  meeting is recorded and recency is **derived** from it — rather than only stamping
  `last_interaction_at`. Full interaction/meeting-note records are no longer deferred; they're the
  context layer, built in phase 2.)* Recency stays a special case of the overwrite guardrail: a
  **more-recent date is an enrichment, never a conflict** (monotonic).
- **Script-heavy split:** the LLM does only what's genuinely fuzzy — reading prose/events and
  extracting facts. Filtering, existence checks, reconciliation, and rendering are mechanical and live
  in code. Cheaper *and* more reliable (`roadmap.md` §2.6). `render_digest.py` is the clearest example:
  deterministic, identical every run; each proposal carries a `source` so the digest badges it 📧/📅.
- **Idempotency:** Gmail uses a `crm-processed` label as a watermark. Calendar has no label, and
  doesn't need one — contacts/orgs dedupe on re-run, and `last_interaction_at` only moves forward.

## The guardrails (executed, not prose)

Safety comes from rules that *run*, not from the model's self-reported confidence (`concept.md` §9).

1. **Never silently overwrite.** Adding a record or filling an *empty* field / new attribute →
   propose freely. Changing an **existing, non-empty** value → a **conflict**, surfaced in the
   digest's "Needs your call" section for a human decision. A confidently-wrong overwrite is the one
   thing that breaks the trust the product depends on.
2. **Read before write.** Existence-checked in the loop (②) *and* re-checked server-side by the tools
   (`create_*` return `already_exists`). Belt and suspenders.
3. **Worthiness + confidence.** Not every new address is a lead (skip vendors/receipts). Direct
   correspondents (From/To/Cc) are high-confidence; people only *mentioned* in a body are flagged
   "mentioned only." Everything is a proposal; the user is the final filter.
4. **Approval-first.** Write nothing before the user approves.

## The UI, and its one hard constraint

The digest is **skills-as-UI** (the one piece of v1 that carried over): a skill renders a
self-contained HTML view on demand. **Constraint:** an artifact in Claude.ai **cannot call our tools
back** (sandbox CSP). So the model is: **display in HTML, decide in chat.** The digest is for
*reviewing* (changes grouped by *type* — not by source — each with a 📧/📅 source badge and evidence
in a `<details>` "AI overview" dropdown: a one-line reason + the italic source quote); approval
happens *conversationally*; then the skill executes the writes. Don't design buttons that try to write
directly — they can't. (Grouping by change-type keeps related changes together; the per-item badge
carries provenance without fragmenting the view.)

Two UI surfaces, kept separate: this **approval digest** (part of enrichment) vs. the **pipeline
dashboard** (a separate view skill). Same technique, different job.

## Config — the only tuning surface (deliberately small)

`config.example.json`: `self` (identity — never CRM yourself; **mandatory**), `scope` (Gmail lookback
+ `crm-processed` watermark label; calendar look-back/ahead windows), `ignore` (senders/domains to
never add — grows when the user rejects an add), `vocab` (valid lifecycle/deal stages, incl.
`partner`). The shape is open JSON so we add fields later without migration; resist growing it until
the core loop is proven.

## Files

- `skills/crm-enrichment/SKILL.md` — runtime orchestration (the how)
- `skills/crm-enrichment/config.example.json` — the four knobs
- `skills/crm-enrichment/scripts/render_digest.py` — deterministic HTML digest renderer
- `skills/crm-enrichment/scripts/sample-proposals.json` + `sample-digest.html` — preview/test fixture
- `skills/crm-enrichment/demo-fixture-emails.md` — the staged demo inbox
- `server/src/seed-demo.ts` (`npm run seed`) — the demo "before" CRM state (idempotent)

## Status (2026-07-10)

- **Gmail source: live-tested and passing.** A real run on a *noisy* inbox extracted correctly,
  deduped (no duplicate orgs), fired the guardrails (title conflict flagged; a "did she leave?"
  inference correctly *not* acted on), and the worthiness filter held — security + Calendly noise were
  seen and declined, zero junk written. This is the first real evidence the differentiator works.
  (Feasibility ≠ desirability — proves the mechanism is good, not that customers want it.)
- **Calendar source: built, not yet live-tested.** Reader + `last_interaction_at` + cross-source
  dedup are written and the renderer/badges are verified locally; the live Google Calendar run is the
  next validation.
- **Locally verified throughout:** digest renderer (full/empty/sparse, source badges), seed script
  (idempotent, 2/2/2/4), the tool write-path (via `mcp-smoke`). Delivery = bundled skill zip.
