# Notes / context layer — design & scope (pre-schema)

> **✅ BUILT (2026-07-14).** The foundation this doc specs is done: migration `0003` (unified timeline
> via the `interaction` table + `interaction_link` M2M; living `summary` on person/deal; `description`
> on org), `core/note.ts`, three timeline MCP tools, timeline-derived recency, and the enrichment loop
> + Attio migration writing to it. Two decisions changed during the build (both Rian's calls): the
> timeline **reuses the existing `interaction` table** (not a new `timeline` table), and record links
> are a **many-to-many `interaction_link`** (not fixed FK columns). This doc is now **rationale +
> history**; for what's still open see [`backlog.md`](backlog.md) (org living summary, referral graph
> §8b, commitments) and [`source-attribution.md`](source-attribution.md) (the deep view).

**Status (2026-07-13, pre-build):** scope + shape **locked** (§6 decisions confirmed with Rian). Schema (tables +
MCP tool surface + summary-derivation mechanics) is the **next** step, in its own pass. This doc is the
"what and why + future + refactor/regression plan" so we build deliberately and don't regress the
deployed paths. See `product-strategy-attio-benchmark` (memory) for the strategic frame this serves.

## 1. Why notes matter — they're the context layer, not a feature
Notes are the **current, self-maintained context** the entire intelligent CRM reads from. Today the
dashboard is smart about *numbers* (pipeline value, stages via `get_pipeline_summary`); notes make it
smart about **relationships** — which is the actual job. Everything intelligent is just *reading rich,
current context*:

```
  dashboard Focus list · smart nudges ("who's quiet") · drafting follow-ups
  "answer any question" reports · meeting prep ("brief me") · team handoffs
        └────────────── all just READ ──────────────►  living notes + timeline
                                                        (kept current by enrichment)
```

Differentiator: **no legacy CRM keeps this current** (a human can't), but our client-side enrichment
loop can. This is where "connections other CRMs can't do" lives — once every relationship carries
current context, the LLM can spot cross-relationship patterns ("these three deals all stalled after
pricing").

## 2. The principle — sort context by how fast it changes
Different context has a different *nature*, and its nature dictates its shape. This is the discipline
that keeps us rich-but-not-clunky (the mindset: **rich in context/connections, disciplined in
schema/vocabulary** — the LLM absorbs *interface* complexity, NOT *semantic* complexity, and in a
headless CRM mis-filed data is *invisible* until it yields a wrong answer, so schema discipline matters
MORE, not less):

| Kind of context | Example (Nimbus deal / Sarah Chen) | Changes | Home |
|---|---|---|---|
| **Stable facts** | Sarah, Founder, sarah@nimbus-labs.com | ~never | **attributes** (exists) |
| **Identity / description** | "Nimbus — seed-stage dev-tools startup, ~12 people, CI/CD for mobile" | occasionally | **description** field |
| **Living relationship state** | "In proposal $45k; decision by March; blocker is co-founder budget sign-off; warm, referred us once; last spoke 3d ago" | constantly | **living note/summary** |
| **History / timeline** | "Feb 22 intro · Mar 1 proposal sent · Mar 5 asked re pricing · Mar 5 stage→Verbal" | append-only | **timeline** |

## 3. The model (capability level)
Two new layers + one field, **reusing** what exists:
- **`description`** — a field on **organisations** (identity: who they are / what they do), and
  optionally a person bio. Static-ish; not the living part.
- **Living note / summary** — per **deal** and **person**: current state, next/open items,
  commitments, key dates, sentiment/health. **Self-maintained by the enrichment loop.** This is the
  differentiator.
- **Timeline** — append-only entries per deal / person / org. Entry kinds:
  - human notes; **meeting summaries** (Granola & co. as a *source*);
  - **system-generated change events** — deal stage/amount/owner changes ("how the deal evolved");
  - **relationship-change events** — who joined / dropped off / was replaced.
  - Drives `last_interaction_at` (recency derived in `core` from latest `occurred_at`, not hand-set).
- **Reuse:** **attributes** stay for *stable facts only*; **associations** stay for *current links*
  (relationship *roles* live in note prose for now — see §6).

The relationship between the two layers: **the living summary is *derived from* the timeline** (+ the
user's comms). Timeline = source of truth + audit trail; summary = always-current read.

## 4. Customer-wants coverage map
Validated against a customer's-eye list (Rian, 2026-07-13):

| Want | Layer | Status |
|---|---|---|
| Deal details / where it stands | living note (deal) | ✅ |
| What was said last meeting (Granola) | timeline `meeting`, source=granola | ✅ |
| What needs discussing next | living note (next/open) | ✅ |
| Last contact w/ a person | timeline → `last_interaction_at` | ✅ |
| How the deal evolved | timeline, system change-events | ✅ |
| Who connected / dropped off / replaced | timeline, relationship-change events | ✅ |
| Deal health / temperature | living note or `core` (derived) | ✅ |
| Commitments (mine / theirs) | living note (open items) | ✅ |
| Key dates (renewal, decision) | living note (context) | ✅ |
| How to work with them (prefs) | person description / living note | ✅ |
| Why we won/lost | timeline entry + living note | ✅ |

## 5. Out of scope / deferred (named honestly, not omitted)
- **Files / attachments** (the actual proposal/contract PDF) — headless has **no blob storage**. The
  note *references* ("proposal sent"), it doesn't *hold* the file. A separate future capability.
- **Threaded collaboration comments** (colleagues @-ing on a deal) — teams-era; multi-author timeline
  entries partially cover it. Defer.
- **Person↔person referral graph** — NOT out of reach (see §8b); it's **downstream of notes**, not
  excluded. The graph *storage already exists* (the generic `association` table). Deferred to a
  fast-follow, not v1.
- **Tasks** — deliberately skipped (admin-heavy checkbox feel the thesis rejects — decided earlier).

## 6. Decisions (locked 2026-07-13)
1. **Timeline object shape → ONE unified object (Rian: confirmed).** A single "timeline entry" that is
   a free note OR a logged touchpoint (call/meeting/email), distinguished by `type` + optional
   `occurred_at`. NOT two separate note/interaction objects. Embodies "rich content, disciplined
   schema" — a meeting is just an entry with `type=meeting`.
2. **Living summary in v1 (Rian: yes).** The loop maintains a rolling per-record summary from day one,
   not just an append-only timeline. Carries the discipline in §7.
3. **Relationship roles → note prose in v1** (champion / blocker / economic-buyer); promote to a typed
   role on the association only if it proves load-bearing. (Recommended; adopt unless Rian objects.)
4. **Every timeline entry + note carries `author` (`owner_id`) AND `source`** (Rian, 2026-07-13).
   `source` = the *mechanism* (manual / enrichment / migration / granola); `author` = the *person* it's
   attributed to. Solo: they collapse, no visible effect — this is **forward-compat for teams** (who
   logged it / whose relationship / who changed the deal / "my vs team activity" / handoffs), stamped
   with the operator now, real per-user identity when Phase-4 auth lands. ~one nullable column, invisible
   to the solo user. Same cheap-insurance logic as `owner_id` on records.

Net: the model = **one `description` field (orgs) + one unified timeline object + one living summary**,
reusing attributes (stable facts) and associations (current links). Timeline entries + notes carry
`author` + `source`, and a **stable `id`** (so a future graph edge can cite its provenance — §8b).

## 7. Discipline — what keeps rich context from rotting
A living summary the LLM silently rewrites is exactly the "rich" that can become confident fiction
(the headless invisible-error risk). So it ships with its keep-it-true mechanism, same as every other
write path:
- **Provenance:** the summary records which timeline entries / comms it's built from.
- **Regenerate, don't blind-edit:** rebuilt from source, not mutated in place.
- **Human-in-the-loop:** material changes surface through the **enrichment digest** for approval, like
  all other writes. (Consistent with facts-in-`core` + executed guardrails: recency is *derived*, the
  model writes prose, not authoritative numbers.)

## 8. What it grows into (nothing built now is thrown away)
`you + the migration write the first notes` → `enrichment takes over maintaining the living summary`
→ `dashboard / reports / drafting / meeting-prep all read them` → `for teams, the shared brain`.
Same objects, growing capability. Ties to the teams lens: notes carry `author` (`owner_id`) from day
one, so they're team-ready.

## 8b. Downstream: the connections / referral graph (fast-follow, NOT v1)
Verified 2026-07-13: the **storage already exists**. `association` (0001_init.sql:128) links *any*
record to *any* record with a **free-string `relationship_type`** ("add freely — no migration", the
comment literally lists `champion` / `introduced`) and an `attributes` jsonb for edge detail
(provenance, "since"). So a person↔person referral graph is far closer than "out of scope" implied.

- **Already have:** the graph table (polymorphic, any-to-any), arbitrary edge types, edge provenance
  (jsonb), traversal indexes (from/to), AND the *population mechanism* — the enrichment loop (a new
  extraction target, not a new engine).
- **Genuinely new work:** a small opinionated edge vocab (`referred_by` / `introduced_by` /
  `worked_with` — 4–6, resist an edge zoo); **extraction** (loop detects "Ken intro'd me to Oscar" →
  proposes edge → human approves — the hard part + the accuracy risk, so human-in-the-loop is
  mandatory); multi-hop **traversal reads** (find_associations is one hop); a **network view**.
- **Why downstream of notes:** a referral is almost always *stated in a note/comm first*, so the edge's
  provenance points at a timeline entry — the graph largely populates itself as a byproduct of the
  notes loop. **MVP = referral/intro provenance only** (directional, high-value, actionable — "where did
  my pipeline come from", "top referrers", "who can warm-intro me to X" — and usually explicitly stated,
  so easiest to extract accurately). Full acquaintance graph + traversal + viz = a later, larger pass.
- **Cheap forward-compat to bank NOW (in the notes schema):** give every timeline entry a **stable `id`**
  so a future edge can cite it as its source ("introduced, per this meeting note") with no retrofit.
  (Same pattern as `owner_id` for teams.) This is the only graph-related thing to build into notes v1.

## 9. Refactor surface + regression plan (Rian flagged this)
Adding the notes layer touches several already-working, some **deployed**, paths. Sequence to protect
them; add coverage before/with each change.

**Surface (likely):**
- **Schema/migrations:** new `notes`/timeline table(s) + a `description` column on organisations (and
  maybe a person bio). New migration file(s) after `0002`.
- **Core:** a `core/note.ts` (mirror `person.ts`); wire `core/summary.ts` to derive
  `last_interaction_at`/recency from the timeline and surface the living summary.
- **MCP tools:** create/find/update notes + read a record's timeline/summary → **tool count changes**
  (`mcp-smoke` asserts the count) → `npm run deploy` + re-upload skills.
- **Enrichment loop:** write timeline entries + maintain the living summary (its new main job).
- **Migration skill (`crm-import`):** fold Attio notes into timeline entries (closes the migration
  gap — Rian's 14 Attio notes). Attio has `list-notes`/`get-note-body`.
- **Dashboard skill:** surface the living summary + recency.

**Regression (must stay green):**
- `crm-import/test/run_tests.py` (**66 checks**, incl. the **CSV golden** — must not drift).
- `server` `npm run smoke` + `npm run mcp-smoke` (tool count).
- `crm-enrichment/eval` (the stress-test harness).
- Dashboard + digest + import previews render.
- Add a **notes/timeline test suite** alongside these.

## 9b. The one open schema fork to decide FIRST (before writing tables)
**Where does the living summary live?** Three candidates — pick deliberately, it shapes everything:
- **(a) a column on `contact`/`deal`** (e.g. `summary text` + `summary_updated_at` + `summary_provenance jsonb`).
  Simplest to read (it's right on the record; the dashboard/summary tool already loads these rows). Con:
  one summary per record, no history of the summary itself.
- **(b) a special timeline entry** (`type=summary`, latest-wins). Unifies with the timeline; keeps summary
  history for free. Con: "current summary" becomes a query (latest of type), slightly more work to read.
- **(c) its own `summary` table** (one row per record). Cleanest separation. Con: another object/table.

Recommendation to pit against the alternatives next session: **(a)** for v1 — the summary is a *read-optimised
current-state field*, and `core/summary.ts` already loads the record rows, so the dashboard gets it for free;
the timeline (with provenance ids) already provides the history, so (a)'s "no summary history" con is covered.
Revisit if we need to diff summaries over time.

## 10. Next — start in a FRESH session
The design is fully captured (this doc = the spec; roadmap §5b; the `notes-design` memory). The build is
large, touches deployed paths, and needs regression — so **start it in a fresh session with a clean
context window**, using this doc as the brief.

**Suggested build order (each step green before the next; the codebase recipe is START-HERE §6 "to add
an object's tools"):**
1. **Decide §9b** (where the living summary lives) + write the **schema on paper** → get Rian's sign-off.
2. **Migration `0003`** — the unified `timeline` table (stable `id`, `author`/`owner_id`, `source`,
   `type`, `occurred_at`, `body`, record links) + the `description` column on `organization` (+ the
   summary storage per §9b). *(Next migration number after `0002_deal_closed_at.sql`.)*
3. **`core/note.ts`** — mirror `core/person.ts`; create/list/update timeline entries + read a record's
   timeline; the summary read/write. Then wire **`core/summary.ts`** to derive `last_interaction_at`
   from the latest `occurred_at` and surface the living summary.
4. **MCP tools** — register in `src/mcp/build.ts` `registerCrmTools` → **tool count changes**, so update
   `mcp-smoke` (it asserts the count). `npm run typecheck` + `smoke` + `mcp-smoke`.
5. **Enrichment loop** — write timeline entries + maintain the living summary (its new main job), with
   provenance + digest approval (§7).
6. **`crm-import` migration** — fold Attio notes (`list-notes`/`get-note-body`) into timeline entries;
   keep the **66-check suite + CSV golden** green (add notes coverage).
7. **Dashboard skill** — surface the living summary + recency.
8. **`npm run deploy`** + re-upload the affected skill zips (same ordering lesson as `bulk_import`/
   `get_pipeline_summary`: tool must be deployed before the skill that calls it).

Bank the one graph forward-compat throughout: stable `id` on timeline entries (§8b).
