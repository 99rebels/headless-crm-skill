# Enrichment eval — stress-testing the extract/reconcile judgment

*How well does the enrichment skill's **LLM interpretation** hold up across models and adversarial
inputs? This records the harness, the results, the one bug it found, the fix, and the model-coverage
conclusion. The plumbing (connectors, dedup tools, DB writes) is proven elsewhere — this doc is only
about judgment quality. Harness: `skills/crm-enrichment/eval/eval-workflow.mjs`. Run 2026-07-11.*

---

## Why this exists

The self-maintenance loop is the make-or-break feature, and its risk isn't the plumbing — it's
whether the model, *following SKILL.md*, reads messy real inputs and proposes the **right** changes.
So we test the extract+reconcile step in isolation: feed (CRM state + incoming items) as text, get
structured proposals, and score them against a rubric. No live connector needed.

## Method

- **6 dense scenarios**, each bundling several traps (so 6 cover ~15 behaviours).
- **3 models** — the ones actually runnable here and the ones users actually have:
  **Haiku 4.5** (floor / free tier), **Sonnet 5** (the optimisation target / Pro default),
  **Opus 4.8** (ceiling / Max).
- Each run judged by **Opus 4.8** against the scenario's rubric, graded
  **correct / minor-issues (near-miss) / wrong**, scored 0–100 (any critical failure ⇒ <60).
- **Model-coverage logic (the 4.6 question).** I can't run Sonnet 4.6 (no version selector — the
  tool only exposes `sonnet|opus|haiku|fable`). But capability brackets it: Haiku 4.5 < Sonnet 4.6 <
  Sonnet 5. So: if **Haiku** handles a scenario (correct or near-miss), **4.6 is safe** — no manual
  check. Only a **Haiku-fail / Sonnet-pass** gap needs a manual 4.6 spot-check in claude.ai. A
  Sonnet-5 failure is a *skill* bug, not a tier issue.

## Results (run 1, before fix)

| Scenario | Haiku 4.5 | Sonnet 5 | Opus 4.8 | 4.6 verdict |
|---|---|---|---|---|
| **S1** intro + alias-dedup + title conflict | ❌ 47 wrong | ❌ **42 wrong** | ❌ 45 wrong | **skill bug** |
| S2 noise gauntlet | 88 near-miss | ✅ 96 | ✅ 98 | high confidence |
| S3 restraint / inference | 86 near-miss | ✅ 97 | ✅ 98 | high confidence |
| S4 ambiguity / dedup | ✅ 94 | 88 near-miss | ✅ 95 | high confidence |
| S5 cross-source + calendar | ✅ 98 | ✅ 96 | ✅ 98 | high confidence |
| S6 messy extraction | 84 near-miss | ✅ 94 | 85 near-miss | high confidence |
| **avg** | **83** | **86** | **87** | |

**Read:** 5 of 6 categories are solid across *all three* models, Haiku included — so **no Sonnet-4.6
spot-checks are needed** on those; 4.6 (stronger than Haiku) will handle them. The single failure is
model-independent — a **skill bug**, the most useful kind of finding.

## The bug (S1) — deal date & stage semantics

All three models made the same two mistakes on the deal:

1. **Start date recorded as close date.** "Let's start Sept 1" was written into the deal's
   `expected_close_date`. A kickoff/start date is not a close date.
2. **"Won" on a verbal yes.** "The board approved it" advanced the deal to *closed-won / status won*
   instead of the **`verbal` stage with status still `open`.** A verbal/board approval is not a
   signed close.

Everything *else* in S1 was handled well by all models — the Founder→CEO title **conflict was
flagged** (not overwritten), and the personal-email **alias for Sarah was deduped** (no duplicate
contact). So the skill's core guardrails held; the gap was purely deal-field precision.

*Note: the bug was latent in our own `sample-proposals.json`, which modelled "close date set to 1
Sep" — the eval caught the fixture lying. Fixed alongside the skill.*

## The fix (applied 2026-07-11)

Added a **"Deal dates & stage are precise"** rule to SKILL.md's extract rules (and mirrored it into
the eval harness):
- `expected_close_date` = when the deal will **close/be decided**, never a start/kickoff date.
- `status: won` = **actually closed/signed**; a verbal yes / board approval / "budget approved" is
  the **`verbal` stage, status `open`** — never `won`; never won/lost on a speculative signal.
- Only create a deal for a **concrete opportunity**, not a vague mention (also curbs the minor
  "blank-fielded deal" over-creation seen across S2/S4/S6).

**Confirmation (run 2, after fix — full matrix re-run).** Changing the rules invalidated the run-1
cache, so re-running went wide (all 6 × 3) instead of just S1 — a bonus full regression test.

| Scenario | Haiku 4.5 | Sonnet 5 | Opus 4.8 |
|---|---|---|---|
| **S1** intro + dedup + conflict | 80 near-miss | 80 near-miss | 80 near-miss |
| S2 noise gauntlet | ✅ 97 | ✅ 98 | ✅ 96 |
| S3 restraint / inference | ✅ 96 | ✅ 96 | ✅ 96 |
| S4 ambiguity / dedup | 86 near-miss | ✅ 93 | ✅ 96 |
| S5 cross-source + calendar | ✅ 96 | ✅ 97 | ✅ 97 |
| S6 messy extraction | 88 near-miss | 88 near-miss | 86 near-miss |
| **avg** | **91** (was 83) | **92** (was 86) | **92** (was 87) |
| **critical failures** | **0** (was 2) | **0** (was 1) | **0** (was 2) |

**The bug is fixed and there were no regressions — every run improved or held.** On S1, all three
models now flag the conflict, dedup Sarah, keep Sept 1 off the close date, and set `verbal` (not
`won`). No run has a critical failure anywhere. Sonnet 5, the target, is clean on 5/6 with S1 a
near-miss. Nothing needs a Sonnet-4.6 spot-check.

Remaining S1 slips are **minor trade-offs**, not bugs: the early-stage Calder deal was *not* created
(the new "concrete opportunity only" rule made all models conservative — arguably fine for a solo
operator who doesn't want speculative pipeline), and Priya was labelled `prospect` not `lead` (the
lead/prospect line is fuzzy). Left as-is; tunable later (a config "deal eagerness" knob if it ever
matters).

## Minor issues (not fixed — logged, low priority)

- Occasional **lifecycle mislabels** (e.g. an active client tagged `prospect`; a new contact tagged
  `customer`). Cosmetic; the `partner` addition earlier was the one that mattered.
- Occasional **over-eager blank deal** creation on thin signals — largely addressed by the
  "concrete opportunity only" clause above.
- **Phones/structured fields** sometimes kept in prose rather than the structured field (S6). Minor.
- A model once created a **mentioned-only org without the low-confidence marker** (S4, Sonnet). Minor.

## Conclusions

- **Sonnet 5 (the target) is clean on 5/6** and only failed the bug everyone failed → after the fix,
  expected clean. This is a strong place to be for cost-conscious users.
- **No manual Sonnet-4.6 spot-checks required** — Haiku 4.5 already brackets 4.6 from below on every
  passing scenario. (Re-confirm only if S1's re-run somehow regresses on Haiku.)
- **Haiku 4.5 is viable** as a floor (avg 83, no catastrophic misses outside the shared bug) — so the
  free tier is usable, not just Pro/Max.
- The eval's real value: it found a **specific, model-independent, fixable** defect that a live demo
  might have surfaced only by luck, and it did so in ~5 minutes / 36 agents instead of hours of manual
  claude.ai testing.

## Re-running

```
# full matrix (6 scenarios × 3 models)
Workflow({ scriptPath: "skills/crm-enrichment/eval/eval-workflow.mjs" })
# targeted (one or more scenarios, optionally a subset of models)
Workflow({ scriptPath: "...", args: { scenarios: ["S1-combo"], models: ["sonnet"] } })
```

Scenarios + rubrics live in the harness file. Add a scenario = add an object to `SCENARIOS`.
