# The pipeline-summary tool & the consistency problem — reference + redesign parking lot

*Written 2026-07-12 to capture the design of `get_pipeline_summary` and, honestly, its rough edges — so we can revisit it deliberately **after the demo**. Rian's read: the tool is **needed and good, but feels a little primitive**, and may hinder us later without a redesign. This doc is the "come back to this" note. Source of truth for behaviour: `server/src/core/summary.ts`.*

---

## 1. Why it exists — the problem it solves

The same prompt ("show me my pipeline") run on **Haiku 4.5 / Sonnet 5 / Opus 4.8** produced **three different dashboards**: different pipeline totals, three different weighted forecasts ($24k / $33.6k / $36k), and a stage-less deal (Acme) bucketed under three different made-up names ("other" / "unassigned" / "unstaged"). Only the *facts they could read straight off* (there are 3 open deals, worth $54k) agreed.

Diagnosis: we were asking the **model** to do three different things and conflating them —
1. **arithmetic** (sum the pipeline, weight the forecast),
2. **labelling/bucketing** (what stage is a stage-less deal in?),
3. **judgement** (what needs the user's attention?).

The first two are *facts* — they must be identical every time. The third is genuinely model work. Mixing them meant every model improvised all three.

**The fix / the principle now settled:** *if it's arithmetic or a lookup, `core` computes it once; the model only writes prose.* `get_pipeline_summary` is that "compute the facts once" step.

## 2. How it works

One function (`core/summary.ts`, `getPipelineSummary(workspaceId)`), exposed as one MCP tool. Per call it:

1. **Reads the rulebook** from `workspace.settings` — stage names + order, lifecycle values, `default_currency`, and `self.emails` (the operator's own addresses). *Vocabulary is data, not code.*
2. **Batch-reads** all deals, people, orgs, and association links for the workspace.
3. **Joins** the association graph once — attaches each deal's people/org and each person's org/deals (the step models used to do inconsistently).
4. **Buckets** deals by stage in canonical order, with a dedicated **"Unstaged"** bucket for `stage = null`, and an auto-flagged bucket for any stage not in the vocabulary.
5. **Computes stats** with fixed rules: `open_pipeline_value` (sums only the workspace currency; flags mixed), `open_deals`, `relationships` (= contacts with a lifecycle stage, minus self), `unstaged_deals`.
6. **Builds the roster** with real recency (`last_interaction_at` → days; null → "no contact logged", never invented) and recently-won (via `deal.closed_at`, last 90 days).
7. **Emits `signals`** — deterministic attention flags per record id: `is_unstaged`, `awaiting_close`, `quiet_days: N`, `new_no_interaction`.
8. **Returns** the whole factual half of the dashboard as JSON.

The model then does exactly one creative thing: turn `signals` into the ranked human **Focus** list. Same DB in → same facts out, every model.

## 3. Coupling: does it auto-update when the CRM changes?

The most important practical property. Three levels:

| You add… | Auto-updates? | Why |
|---|---|---|
| A new **value** (stage `negotiation`, lifecycle `churned`) | ✅ **Yes, free** | Vocabulary comes from `workspace.settings`; a new stage just becomes a bucket. Unknown stages auto-get a flagged bucket. |
| A new **field** (a `priority` column, a new attribute) | ❌ **Manual** | The tool reads all columns (`select *`) but only *surfaces* the ones it shapes into the output. New field is invisible until added to `summary.ts`. |
| A whole new **object** (tasks, interactions) | ❌ **Manual** | The tool only knows deals/people/orgs/associations. |

So **new values are free; new fields and objects require a small edit in one file.** That's inherent to a *curated view* (a dashboard is opinionated about what it shows) — but it is real coupling, and it's the seed of Rian's "primitive / will hinder us" concern.

## 4. Known limitations (the redesign backlog)

1. **It's one hard-coded view.** Answers "the pipeline dashboard" only. The account "deep view" will need its *own* aggregation → risk of copy-pasted join/format logic across N summary tools.
2. **Schema coupling** (§3) — new fields/objects need manual tool edits. Curated, not automatic.
3. **Full-scan, in-memory aggregation.** Reads every workspace record and computes in JS. Fine at solo scale (tens–hundreds); a ceiling at tens of thousands. *(Note: this niche is unlikely to ever hit that — indie scale is the point.)*
4. **Recency reads a cached column** (`last_interaction_at`) rather than deriving from the `interaction` timeline — can drift.
5. **Signals are fixed heuristics.** e.g. "verbal = last open stage = awaiting close." A new *kind* of attention is a code change.
6. **Single-currency assumption** — mixed currency is flagged, not converted (no FX).
7. **No provenance/confidence** — reports facts, not how-we-know (deferred facts table).

## 5. Is it needed? (verdict)

**Yes — for aggregate/derived views.** The inconsistency it fixes is damaging to the retention thesis (a system of record showing different numbers per model isn't trustworthy). The only alternatives are to *coach the model to compute consistently* (watched that fail across 3 models) or *compute in code* — determinism belongs in code. It's also cheaper/faster (one call vs many model reads) and the natural home for business rules. **Not** needed for simple single-record reads — the plain CRUD tools are fine there. It earns its place because the dashboard is an aggregate.

## 6. Ways to improve / redesign (for after the demo)

Ranked by current preference:

1. **Generalise when the 2nd view lands (recommended).** When we build the account deep-view, extract the shared bits (the association-graph walk, money/recency/bucket helpers) into a small **aggregation/query layer** in `core`, so views compose from shared pieces instead of copy-paste. Don't abstract now — one view doesn't justify it; let the *second* view reveal the right shape.
2. **Consider DB-side aggregation** (Postgres views / a Supabase RPC). *Pro:* airtight, scales, reusable by a future REST API. *Con:* business logic in SQL is harder to test/version than TypeScript, and some rules (self-email match, signal heuristics) are awkward in SQL. Revisit only if scale ever demands it (unlikely at indie scale).
3. **Cache / materialise** the summary (compute on write, store a snapshot). Overkill now; recompute-on-read is instant at this scale.

Concrete smaller wins worth doing regardless: **derive recency from the `interaction` timeline** (more accurate than the cached column), and **make the signal rules richer/configurable** as we learn what "needs attention" really means for these users.

**A genuinely different framing to consider (but I currently reject):** bake the whole view (or strong render instructions) into the tool's *output* so there's no separate render step. I'd keep the current separation — tool = facts, `render_*.py` = presentation, model = Focus prose — because that separation of concerns is clean and testable. But it's the kind of question a redesign should re-open deliberately.

## 7. The open question to answer at redesign time

> Is a per-view "summary tool" the right long-term primitive, or do we want a **thin general query/aggregation layer** in `core` (composable helpers + a few view functions) that new views and a future REST API all build on — so adding an object/field/view is small and predictable rather than a bespoke tool each time?

Rian's instinct (tool is good but primitive) points at the second. Decide it **after the demo**, informed by building the *second* view (the account deep-view), not in the abstract. Related: [`roadmap.md`](roadmap.md) §1 (the "facts in core" settled decision), [`data-model.md`](data-model.md) (schema + `workspace.settings`).
