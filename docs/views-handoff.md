# Read-view suite — build handoff & index

**Status (2026-07-15):** Design + mockups done this session; **build not started.** This is the single
entry point for a fresh instance to build the **read views** that sit on top of the notes/context
layer (which is already built — migration `0003`, `core/note.ts`, timeline + living summaries). Read
this first, then the per-view docs it links. Everything referenced here is committed.

Sibling context you already have: [notes-design.md](notes-design.md) (the model), the build-state
memory, [artifact-interactivity.md](artifact-interactivity.md) (the write constraint below).

---

## 1. The architecture decision — read before building anything

**One skill family. The deep view is the base primitive; the others reuse it.**

- **Deep view (company-rooted) = the anchor/primitive.** One scrollable canvas (NOT tabs): brief band
  (living summary + freshness/provenance) → identity → people (with role chips) → deal cards (open
  items, staleness, folded per-deal timeline) → full timeline (collapsible, source-attributed,
  drill-into-note). Every component is *born here* and reused by the others.
- **Meeting prep = a MODE of the deep view, not a separate object.** Same data, re-ordered and
  time-boxed for a calendar event (walk-in brief → who's in the room → where you left off → generated
  talking points). Same skill family. See [meeting-prep.md](meeting-prep.md).
- **Person view = a sibling that reuses the primitive, person-rooted.** Adds the two person-only
  sections a company page can't have: *how to work with them* and the *connections/referral graph*
  (§5 below). See the mockup + §5.
- **Commitments ledger = deferred, and NOT part of this skill.** It's cross-record (an aggregate over
  every record, closer to the dashboard than to a single-record view) and needs a structured field.
  See [commitments-ledger.md](commitments-ledger.md).

**Two hard constraints that shape every view:**
1. **Artifacts render, never write** ([artifact-interactivity.md](artifact-interactivity.md)). Every
   "action" a view implies (log a note, move a stage, draft a follow-up, approve a summary) routes
   back into the **conversation**. Design views to *invite* those chat actions; never build an editor.
2. **No fetch in the sandbox.** Progressive disclosure is done with embedded `<details>` (drill
   without fetch) — everything ships folded, the user unfolds it. Don't design anything that needs a
   network call on click.

---

## 2. The mockups — the visual spec (build to these)

Self-contained HTML, "Ledger" identity (the ~20-token CSS block shared with the dashboard/digest),
light/dark + toggle. Open them in a browser:

| View | Mockup | Notes |
|---|---|---|
| **Deep view** (company) | [mockups/deep-view-company.html](mockups/deep-view-company.html) | The primitive. Expand a timeline entry's **"Summary & source"** to see the source-attribution drill-down. |
| **Meeting prep** | [mockups/meeting-prep.html](mockups/meeting-prep.html) | The deep view re-ordered for a calendar event. |
| **Person view** | [mockups/person-view.html](mockups/person-view.html) | Person-rooted; the referral graph is the centerpiece. |

---

## 3. The per-view build docs (context + what's real vs missing)

- **[source-attribution.md](source-attribution.md)** — the **deep-view build brief**: audits the mockup
  field-by-field (what renders from stored data today ✅, what's derived 🔁, what's missing ⚠️), plus
  the source-drill model ("proof" = AI summary + link out, never raw data). **~80% renders from stored
  data today.** Start here for the deep view.
- **[meeting-prep.md](meeting-prep.md)** — meeting-prep as a mode: the one new input (live calendar
  event), talking points generated at read-time (not stored), and the one dependency to verify
  (attendee `interaction_link`s).
- **[import-seed-summary.md](import-seed-summary.md)** — seed a living summary at import from migrated
  Attio notes, so a just-migrated deep view isn't empty until the loop next runs. Also corrects how the
  loop is triggered (Claude scheduled task / on-demand — **not** comm-triggered).
- **[commitments-ledger.md](commitments-ledger.md)** — the deferred cross-record view + the structured-
  commitments flag.

---

## 4. Already built this session — do NOT rebuild

- **Digest: living-summary before→after diff.** Rewrites now render a word-level diff so an approver
  sees exactly what changed (`render_digest.py` + the SKILL.md wiring for `previous`). Falls back to
  plain for a first summary.
- **Import: Notes tab.** The Attio migration preview now shows migrated notes against the record they
  land on (`build_from_attio.py` surfaces them in the digest; `render_preview.py` renders a conditional
  Notes tab). 78/78 import checks pass.

---

## 5. The person view's connections / referral graph — what it takes to build

The centerpiece of the person view, and the part that is **NOT renderable from today's data** — it needs
a real build. Grounded in [notes-design.md](notes-design.md) §8b.

**Already have (the storage):** the `association` table is polymorphic (any record ↔ any record), takes
a **free `relationship_type` string** (no migration to add `referred_by` / `introduced_by`), has an
`attributes` jsonb for edge detail (provenance, "since"), and from/to traversal indexes. The
*population mechanism* — the enrichment loop — also exists.

**Genuinely new work (in rough order):**
1. **A small edge vocab** — `referred_by` / `introduced_by` / `worked_with` (4–6; resist an edge zoo).
2. **Extraction (the hard part + the accuracy risk).** The enrichment loop detects "Sarah introduced me
   to Priya" in a note/comm → proposes a directional edge → **human approves in the digest** (mandatory
   — this is a judgment call that can be wrong). The edge's provenance points at the timeline entry it
   came from (that's why timeline entries have stable ids). Notes largely populate the graph as a
   byproduct.
3. **Traversal reads.** `find_associations` is one hop; the view needs directional reads — "who referred
   this person in," "who they've introduced," and aggregates like "top referrers / where did my pipeline
   come from."
4. **The view section** — render as **directional inline lists** (↘ came to you through / ↗ intros they
   made), NOT a node diagram (matches the mockup + the Attio research: relationships as inline linked
   lists). Each edge shows the person, their company, the outcome (lead / pending), and cites its
   provenance.

**MVP = referral/intro provenance only.** Directional, high-value, actionable ("top referrers", "who can
warm-intro me to X"), and usually *explicitly stated* in a note — so it's the easiest to extract
accurately. A full acquaintance graph + multi-hop traversal + viz is a later, larger pass.

---

## 6. Two "reach" concepts the person view shows — don't conflate them

1. **Direct multi-company involvement** — one person linked to several companies/deals at once (works at
   A, advises B, decision-maker on a C deal). **Renders from `association` today, no new build** — the
   person view just lists everywhere they're linked. (Sarah in the mockup only works at Nimbus, so this
   isn't visible on her; it lights up for anyone with links across accounts.)
2. **Referral reach** — who they *introduced you to* at other companies. This is the **§5 referral
   graph** and needs the extraction build.

Same view, two different data sources: #1 is existing associations; #2 is the new graph.

---

## 7. Known dependencies / test notes (from this session)

- **Person view depends on a rich living summary** (the brief band + "how to work with them"). It's only
  as sharp as what the loop maintains — thin summary → generic view. Acceptable; test it live.
- **Meeting prep** leans on the loop populating **attendee `interaction_link`s** (for "who's in the
  room" + "first time meeting X"). Verify that's populated; fallback in [meeting-prep.md](meeting-prep.md).
- **Deep view source drill-down** links out to Gmail/Granola via `external_id` — verify a user-clicked
  link actually opens out of the artifact sandbox on-surface.

## 8. Suggested build order
1. **Deep view** (the primitive) — from [source-attribution.md](source-attribution.md); ~80% renders now.
2. **Meeting prep** (a mode of it) — from [meeting-prep.md](meeting-prep.md); no new schema.
3. **Import seed-summary** — from [import-seed-summary.md](import-seed-summary.md); makes migrated deep
   views non-empty.
4. **Person view** (sibling) — how-to-work + deals + timeline render on existing data; the **referral
   graph (§5) is the one real build** and can be a fast-follow.
