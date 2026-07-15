# Seed a living summary at import — build brief (Attio migration)

**Status (2026-07-15):** Design captured, **not built.** Context for a future instance to build, same
as the other flag docs. Concerns the Attio migration (`build_from_attio.py`) + the summary layer
(`core/note.ts` / the enrichment loop). Kept light where the schema/loop may still move; the decision
is firm. CSV is out of scope for now (Attio is the demo priority).

**Related mockups/docs:** [source-attribution.md](source-attribution.md) (deep view + notes model),
[mockups/deep-view-company.html](mockups/deep-view-company.html) (the "Where things stand" brief band
this fills), [notes-design.md](notes-design.md) §7 (summary discipline).

## The gap
The Attio migration already brings **notes across** as **timeline entries** (full body preserved) —
good, and visible in the import preview's Notes tab. What it does **not** do is create the **living
summary** (`deal.summary` / `person.summary`) — the single synthesized "where things stand" field the
deep view shows as its hero band.

Key distinction (this is the thing that's easy to conflate):
- **Attio note = a timeline entry.** A deal can have several; they're append-only history, the *source
  material*.
- **Living summary = one derived field** per record, synthesized *from* the timeline. Not one of the
  notes — a roll-up of them.

So after a migration, a deal shows its notes in the timeline but an **empty "Where things stand"
band** until a summary exists.

## Why the enrichment loop doesn't fill it on its own
How the loop is actually run (corrected — it is **not** comm-triggered, and can't be fired from
activity inside Claude):
- It runs as a **Claude native scheduled task** that fires the skill **client-side** — we host no
  cron/runtime (`roadmap.md` line 15). That automation is currently **deferred**; today it runs
  **on-demand** (the user invokes the skill in conversation). `roadmap.md` line 84.
- Whenever it runs, it reads a **lookback window of recent Gmail/Calendar** and only proposes summaries
  for records touched by **new activity in that window**.

Consequence: a just-migrated record whose only content is **old imported notes** (no recent comm) is
**not in the loop's window**, so it never gets a summary from a normal loop run. The migrated CRM looks
like a pile of untouched notes rather than something alive — bad for a demo, and bad for first-run
trust.

## The decision: seed the living summary at import
For each migrated **deal / person that has imported notes** (or other meaningful state), synthesize an
**opening living summary** from those notes, so the deep view's brief band is populated the moment the
migration lands. The enrichment loop then refines it later as normal (regenerate-not-blind-edit, §7).

This makes the user's intuition literally true out of the box: *their Attio notes flow into the living
summaries* — as the **source** the seed is built from (not by promoting a note verbatim).

## Design considerations (for whoever builds it)
- **Only seed where there's material.** A record with no notes / no state gets **no** summary — never
  invent one. (Same "don't guess" discipline as the rest of the import.)
- **It's a model step.** The import is otherwise deterministic/script-heavy; summarising notes is
  judgment, so it's the model's job. Scope it narrowly: summarise *from the imported notes* (+ deal
  stage/amount/close date already in the plan), don't infer beyond them. Follow the loop's summary
  style (lead with a standalone one-line headline — see the enrichment SKILL.md summary rules).
- **Provenance.** Set `summary_provenance` to the imported timeline entry ids the seed was built from
  (§7 keep-it-true discipline) — so the later loop knows what it was based on.
- **Approval.** Surface seeded summaries for approval like every other write — either in the **import
  preview** (a Summaries view alongside the Notes tab) or via the enrichment digest's existing
  "Living summaries" section (which already renders summary items, now with the before→after diff).
- **Compliance:** fine — the seed is derived from **user-authored** notes we already store in full;
  no new raw-data exposure.

## Two ways to build it (pick deliberately)
- **(a) In the migration flow.** After the plan is built, a model pass reads each record's imported
  notes → drafts a seed summary → include it in the plan/preview for approval → `bulk_import` writes
  `deal.summary` / `person.summary` + `summary_provenance`. Simplest to ship; keeps it one flow.
- **(b) A post-import "summarise migrated records" pass.** A non-comm-triggered entry point that runs
  the loop's *summary* logic once over the freshly-migrated set (reads their timelines, proposes
  summaries). Cleaner reuse of the enrichment summary logic; keeps the import deterministic. Needs a
  "summarise these records from their existing timeline" mode the loop doesn't have today.

Lean recommendation: **(b)** if the summary logic is cleanly callable (best reuse, keeps the import
script-only); **(a)** if you need it fastest for the demo. Either way the write target is the same
(`deal.summary` / `person.summary` + provenance), and it goes through approval.

## The nice property
No schema change needed — `deal.summary` / `person.summary` / `summary_provenance` already exist
(0003). This is a **generation + approval** step, not a new table.
