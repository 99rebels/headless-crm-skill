# The enrichment loop (self-maintenance) — architecture & rationale

*The **why** behind `skills/crm-enrichment/`. The skill's `SKILL.md` is the operational how (what the
model does at runtime); this doc is the design rationale a new **builder** needs. Read `concept.md`
§5/§8 and `roadmap.md` §2/§5 (Phase 2) for where this sits. Status at bottom.*

---

## What it is and why it matters

This is the **self-maintenance loop** — the product's differentiator, retention bet, and hardest
tech, all one thing. A relationship CRM dies from the **upkeep chore**; this loop is what removes it.
It reads the user's email, figures out who's who, and proposes clean updates for one-tap approval, so
the CRM stays accurate without manual data entry. If this isn't *good enough*, users still feel the
chore and churn — so quality here is the whole ballgame (`concept.md` §8.2–8.3).

## The one architectural decision that shapes everything: it runs client-side

The loop runs **in the user's own Claude**, using **their own Gmail connector**. Raw email is read
there and **never reaches our server** — only the *approved, structured* CRM updates do. This is the
single biggest liability-reducing decision in the product: it keeps our compliance surface to
ordinary CRM records, not raw comms (`roadmap.md` §1). **Never** route raw email content through the
CRM server. That's why the loop is a *skill* (client-side) and not a server job.

## The pipeline, and why each stage is shaped the way it is

```
① SCOPE      Gmail query (time window + -label:crm-processed)   cheap metadata only
② CLASSIFY   find_contacts / find_organizations                 DB reads, no tokens → KNOWN vs NEW
③ READ       get_thread on survivors only                       the only place body-tokens are spent
④ EXTRACT    LLM → facts fitting the CRM schema                 the ONLY fuzzy step
⑤ RECONCILE  diff into new / updates / deal_updates / conflicts deterministic
⑥ APPROVE    render digest (HTML) → user approves in chat       nothing written yet
⑦ WRITE      create/update/link via MCP tools                   approved items only
⑧ CLOSE      label handled threads; offer to grow the ignore-list
```

- **Token discipline (②③):** we filter on *cheap* Gmail metadata first and only fetch full bodies for
  survivors. We do **not** gate on "already in the CRM" — discovering *new* people/companies is half
  the value, so unknown senders must still be read; the CRM lookup only *classifies* create-vs-update
  and supplies the existing record as context.
- **Script-heavy split (④ vs the rest):** the LLM does only what's genuinely fuzzy — reading prose
  and extracting facts. Filtering, existence checks, reconciliation, and rendering are mechanical and
  live in code. Cheaper *and* more reliable (`roadmap.md` §2.6). The digest renderer
  (`render_digest.py`) is the clearest example: deterministic, identical every run.

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
*reviewing* (grouped changes, evidence in `<details>` dropdowns — an "AI overview" reason + the
italic email quote); approval happens *conversationally*; then the skill executes the writes. Don't
design buttons that try to write directly — they can't.

Two UI surfaces, kept separate: this **approval digest** (part of enrichment) vs. the **pipeline
dashboard** (a separate view skill). Same technique, different job.

## Config — the only tuning surface (deliberately small)

`config.example.json`: `self` (identity — never CRM yourself; **mandatory**), `scope` (lookback +
the `crm-processed` watermark label), `ignore` (senders/domains to never add — grows when the user
rejects an add), `vocab` (valid lifecycle/deal stages). The shape is open JSON so we add fields
later without migration; resist growing it until the core loop is proven.

## Files

- `skills/crm-enrichment/SKILL.md` — runtime orchestration (the how)
- `skills/crm-enrichment/config.example.json` — the four knobs
- `skills/crm-enrichment/scripts/render_digest.py` — deterministic HTML digest renderer
- `skills/crm-enrichment/scripts/sample-proposals.json` + `sample-digest.html` — preview/test fixture
- `skills/crm-enrichment/demo-fixture-emails.md` — the staged demo inbox
- `server/src/seed-demo.ts` (`npm run seed`) — the demo "before" CRM state (idempotent)

## Status (2026-07-10)

- **Built and locally verified:** digest renderer (full/empty/sparse cases), seed script (idempotent,
  2/2/2/4), the tool write-path (via `mcp-smoke`). Delivery = bundled skill files.
- **NOT yet proven — the open risk:** extraction quality on *real* email (stage ④). Everything around
  the model is proven; the model reading real inboxes and producing correct proposals can only be
  validated in a live Claude.ai run (Gmail connector on the dedicated demo account). That live test is
  the immediate next step and the thing to be honest about — feasibility of the scaffolding ≠ quality
  of the extraction.
