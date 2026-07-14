# CRM migration (from a connected CRM) — design + confidence model

**Status (2026-07-13):** built + locally tested for **Attio**, then **merged into `skills/crm-import/`**
as a second *source* (a connected CRM alongside a file). One skill, one zip, one write path. Live-read
on claude.ai is Rian's to test. This is the "switch off your old CRM" on-ramp — the highest-friction
moment for a new user, and the one where a live migration is most persuasive.

> **Note:** an earlier draft of this doc described `crm-migration` as a standalone skill built alongside
> `crm-import`. That was the deliberate first step (de-risk the deployed CSV path); we then merged it in.
> Where this doc says "separate skill," read "second source inside `crm-import`."

## What it is
Migrate a user off **Attio** into this CRM **live through the Attio connector** — no export file
needed. It is the enrichment/import loop with one new **source**: a *connected CRM* instead of Gmail
or a CSV. Pipeline: **discover → pull → map → build → approve → write**.

It deliberately **reuses the back half of `crm-import`**: `build_from_attio.py` emits the *same*
`plan` + `digest` shape as `build_import.py`, so the approval preview and the server-side write
(`bulk_import`) are reused unchanged. The only genuinely new code is the front half — pulling Attio
and mapping its schema. The renderer is now a **single, source-aware `render_preview.py`** (it reads
`digest.source_kind` to swap file/rows/import copy for Attio/records/migrate); the two builders route
by **STEP 0** in `SKILL.md` (a file present → CSV path; migrate/Attio → Attio path; ambiguous → ask).

```
Attio connector ──(page list-records)──▶ people/companies/deals.json
                                              │
                          build_from_attio.py │  (flatten · parse · dedupe · link · normalise)
                                              ▼
                                          plan.json ──▶ render_preview.py ──▶ preview (approve)
                                              │                                         │
                                              └────────────── bulk_import ◀─────────────┘
```

## Build order: separate first, then merged (both intentional)
`crm-import` is **deployed and demo-relevant**, so we did NOT refactor its tested `build_import.py`.
Step 1 built the Attio engine as a standalone `crm-migration` skill (copying the pure helpers) to
prove it with zero risk to the CSV path. Step 2 **merged it into `crm-import`**: moved
`build_from_attio.py` in as a **second engine** (still not refactored into `build_import.py` — the
CSV path stays byte-for-byte, guarded by a golden regression test), and **unified the two renderers**
into one source-aware `render_preview.py`. Remaining duplication is the normalisers/dedupe/`assemble`
copied between the two builders (co-located now, `⚠️ DUPLICATION NOTE` headers); a later clock-free
pass can factor those into a shared module. Routing between sources lives in `SKILL.md` STEP 0.

## The core question: "can we ever be *confident* fuzzy-matching arbitrary stages/objects?"
No — and the goal isn't to try. The target is **never be *silently* wrong**: every guess visible and
correctable before a single write. But "show everything for approval" is a cop-out if we make the
human approve hundreds of coin-flips, so we get genuinely confident where it counts by tiering:

1. **Structure first (deterministic where it matters).** Won / lost / open is the classification that
   drives pipeline value — and it's the one we can nearly nail from the *source's own structure*, not
   name-guessing. Attio deal stages are a `status` attribute with an **`order`** and titles (probed
   live); the model uses order + wording to place won/lost. *(HubSpot exposes `stage.metadata.isClosed`
   + `probability`; Salesforce exposes `IsWon`/`IsClosed` — structural, per-CRM, to use when we add
   those. Verify at build time, don't trust these from memory.)*
2. **Semantics second (low-stakes).** Open-stage granularity (discovery vs proposal vs verbal) all
   buckets as open pipeline — the model maps by *meaning* (an LLM reading "Demo scheduled" → discovery
   is understanding, not Levenshtein), and the few that matter get corrected.
3. **Human last.** The approval preview's stage-translation chips (`Won 🎉 → won`) are the confidence
   surface; the user adjudicates only the genuinely ambiguous.

### The rule that makes it safe: never destroy the source label
Whatever a stage maps to, the **original Attio title is always kept** as `deal.attr.imported_stage`
(even when mapped). Nothing is lost, the user can re-segment later, and it kills the "your migration
mangled my data" fear. This is enrichment's "reconciliation output" guardrail applied to migration:
tell the user exactly what we mapped, what we demoted to a note, and what we skipped.

## The decision we made: do NOT expand our model to mirror source CRMs
Adding stages/objects to absorb each source's taxonomy trades away the whole thesis (a *small,
opinionated* pipeline). Attio has "Demo scheduled"/"Onboarding"/"Live"; the next person has
"Nurture"/"Trial"/"QBR"; Salesforce ships 20. **The mapping layer exists precisely so we don't have to
grow the schema.** Two consequences:
- **"Live"/"Onboarding" aren't missing deal stages — they're a lifecycle confusion we get right.** In
  our model a live customer is `deal = won` **+** `org lifecycle = client`; Attio conflates the two
  into one status, we separate them. So "Attio has stages we don't" is usually "those are lifecycle,"
  and mapping fixes it. *(Auto-setting org lifecycle from a won/post-sale deal stage — the richer
  version — is **parked**; v1 maps the deal only. See "Parked.")*
- **Objects are a hard, loud boundary.** Only the three spine objects (people / companies / deals) +
  standard fields migrate. Custom attributes become notes (via `mapping.fields`) or are **reported**
  in `digest.skipped_columns`; custom *objects* are not imported. Trust comes from the reconciliation
  summary, not from coverage.

## What the live probe of the "Track" workspace taught us
- **The connector already flattens values** — `name: "Forte Healthcare"`, `value: "€12,000.00"`,
  `stage: "Disqualified"`, `company: {record_id}`. No raw typed-array envelope to parse. Associations
  come back as clean `{record_id}` references → links are **exact (by id), not fuzzy**.
- **Real edge cases baked into the fixtures/tests:** a CEO with **no email at all** (so dedupe must
  fall back to Attio's stable `record_id`, never name — else two emailless people merge); money
  pre-formatted with a currency **symbol** (`€`/`£`/`$` → ISO); a **custom** deal pipeline
  (`Lead → In Progress → Demo scheduled → Won 🎉 → Onboarding scheduled → Live → Lost → Disqualified`);
  workspace currency **EUR**, not our USD default.

## Local test suite (`skills/crm-import/test/`)
`python3 test/run_tests.py` — **no connection needed.** Exercises **both** engines: **60 checks**
across four scenarios. Attio (over fixtures shaped like the real connector output, probed from Track):
emailless no-false-merge, `€/£/$/ISO` currency detection + amount parsing, stage mapping (seeded +
model alias), never-guess on an unmapped stage, original-label preservation, `record_id` link
resolution, dropped cross-pull links, unmapped-attribute reconciliation, and source-aware render copy.
CSV: a **golden regression** (the committed `sample-contacts.csv` + `sample-mapping.json` must still
reproduce `sample-plan.json` exactly — so a shared-config/vocab change can't silently break the
deployed CSV path) plus fact checks. Run it after any change to either builder, the config, or the
renderer. Fixtures: `test/fixtures/{people,companies,deals,mapping}.json`.

## Demo safety
The intermediate is the *same* write-plan as CSV import, so if the live read wobbles (auth, rate
limit, unexpected shape), the fallback is "export Attio → CSV → `crm-import`" — the same
approval → `bulk_import` path completes the migration. Never dead on stage.

## Parked / next
- ✅ **Merged into `crm-import`** as a second source (done — one renderer, golden-guarded CSV path).
- **Factor the shared helpers** (normalisers/dedupe/`assemble`) out of the two builders into one module.
- **Lifecycle from deal stage** — a won/post-sale deal also sets the org's lifecycle to `client`.
  Truer to our model; more logic + more to test. Not for the demo.
- **HubSpot** next (its connector is also live on claude.ai) — same shape, plus `isClosed`/`probability`
  structural won/lost. **Salesforce** has *no* claude.ai connector visible → CSV-export fallback or a
  real integration; lowest priority (its users can already use `crm-import`).
- **Volume**: `list-records` caps at 50/call; very large workspaces mean many pages. Materialising to
  files keeps context flat, but watch total pull time; consider a cap + "migrate the rest?" prompt.
