# Skill discovery test (run on claude.ai)

*Does Claude **find and invoke the right skill** from a natural request — unprompted — across the
models people actually use? This is the one thing the automated eval could NOT cover (that eval fed
the skill rules to the model directly; it tested judgment, not discovery). Discovery is
surface-specific — it lives in claude.ai's skill-selection, so it can only be tested there. This is
roadmap **R1**.*

---

## Why a fresh chat per test

Once a skill is invoked, its content sits in the conversation context and biases every later turn —
so a second test in the same chat is no longer a *cold* discovery test. **Each test = a new chat.**
And since the model is chosen per-chat, testing across models means separate chats anyway.

**You're testing invocation, not the full run** (the run is already proven). So each test is ~30s:
new chat → send the phrase → read *only the first response* → did the right skill fire? → record →
move on. No need to complete the enrichment/dashboard flow.

**What "it fired" looks like:** Claude announces/uses the skill, or immediately starts the skill's
behaviour (for enrichment: reading Gmail/Calendar and offering a digest; for dashboard: gathering
deals and rendering the pipeline view) — instead of improvising a generic answer or asking what you
mean.

## Setup (once)

- Both skills installed on the test account (`crm-enrichment.zip`, `crm-dashboard.zip`), code
  execution on, CRM + Gmail + Calendar connectors on.
- Models to cover: **Haiku 4.5**, **Sonnet 4.6**, **Sonnet 5** (what users have; Opus optional as a
  ceiling). Pick the model in each new chat before sending the phrase.

## The phrases

**Enrichment (should fire crm-enrichment):**
- E1. "Catch my CRM up from my recent emails."
- E2. "Any new people I should add from my inbox this week?"
- E3. "Log my recent meetings to the CRM."
- E4. "Keep my CRM up to date." *(vaguer — a harder discovery test)*

**Dashboard (should fire crm-dashboard):**
- D1. "Show me my pipeline."
- D2. "Who do I need to follow up with?"
- D3. "How's my pipeline looking?"

**Collision checks (the right one must fire, the other must NOT):**
- C1. "What's going on with my deals?" → expect **dashboard**, not enrichment.
- C2. "Update my CRM from my calendar." → expect **enrichment**, not dashboard.

## Record it

For each phrase × model, note: **right skill fired?** (Y/N) · **first try?** (Y/N) · **wrong skill
fired?** (Y/N) · short note.

| Phrase | Haiku 4.5 | Sonnet 4.6 | Sonnet 5 |
|---|---|---|---|
| E1 catch up from emails | | | |
| E2 new people from inbox | | | |
| E3 log meetings | | | |
| E4 keep CRM up to date | | | |
| D1 show pipeline | | | |
| D2 who to follow up | | | |
| D3 how's pipeline looking | | | |
| C1 what's up with deals → dashboard | | | |
| C2 update from calendar → enrichment | | | |

**Minimal pass (fast, ~9 chats):** E1, D1, C1 across the 3 models. If those are clean, you're
probably fine. Run the full grid only if the minimal pass shows any flakiness.

## Pass / fail

- **Pass:** the primary phrases (E1, D1) fire the right skill **first try on all three models**, and
  the collision checks never fire the wrong skill.
- **Weak:** works on Sonnet 5 but flaky on Haiku/4.6, or needs a second nudge, or the wrong skill
  sometimes fires. Note *which phrasing on which model* — that's the fix target.

## If discovery is weak — the fixes (in order)

1. **Tune the `description`** toward the phrasings that missed (the description is *the* lever for
   selection). Cheapest fix; re-zip and re-test.
2. **Sharpen the disambiguation** line in each description if the *wrong* skill fires (the two
   already cross-reference each other — strengthen it).
3. **R1 fallback — bake the behaviour into the MCP tool output.** If the cheaper models still won't
   reliably discover the skill, have the CRM tool's *result* carry the presentation/next-step
   instructions, so the skill "rides along" with the tool call and there's no separate object to
   discover. This dissolves the discovery problem at the cost of central updatability.

## Note

We have **one** real end-to-end data point already: the first live Gmail run discovered + invoked the
enrichment skill and drove the tools correctly — on claude.ai's default model. This protocol extends
that single success into coverage across the cheaper models, where discovery is most likely to wobble.
