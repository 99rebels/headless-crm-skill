export const meta = {
  name: 'enrichment-notes-eval',
  description: 'Stress-test the NOTES/CONTEXT-LAYER behaviour of the enrichment loop across models',
  phases: [
    { title: 'Run', detail: 'notes scenarios × {sonnet,opus} produce proposals incl. timeline + summaries' },
    { title: 'Judge', detail: 'Opus scores each run against its rubric' },
  ],
}

// The enrichment rules + the NEW context-layer rules (faithful to SKILL.md after phase 2). What we're
// testing: given a comm, do models ALSO produce a correct timeline entry + living summary, respecting
// the compliance boundary — not just the field updates the base eval already covers.
const SKILL_RULES = `You keep a CRM current from incoming email and calendar. For the given CRM state and incoming items, propose changes. Base rules:
- Extract only concrete STATED facts. Read before write (dedupe people by email, orgs by domain: Acme / acme.com are one org). Never silently overwrite a non-empty value — surface it as a conflict.
- DEALS have no key: match a deal named in a comm to an EXISTING deal by name + org; if one exists, propose a stage/amount UPDATE (deal_updates), NEVER a second copy. A duplicate deal doubles pipeline value — a trust-breaking error.
- Deal precision: a start/kickoff date is NOT expected_close_date; a verbal yes / board approval / "budget approved" is the "verbal" stage with status STILL open, never "won".
- Worthiness: skip newsletters, receipts, automated/no-reply, notifications, cold/unsolicited pitches. Do not add the user themselves or internal colleagues (same domain).

THE CONTEXT LAYER (your new main job — in ADDITION to the above):
- TIMELINE: log each processed real email/meeting as ONE timeline entry — type (email|meeting|call), a short subject, and an AI "summary" of what happened / what's next. Link it to the people, deal(s), and organisation(s) it involves (a single meeting can link to MANY people and MANY deals at once — do NOT split it into one entry per person).
- COMPLIANCE (hard rule): the timeline entry stores your AI SUMMARY only — a paraphrased gist. NEVER copy the raw email/event body verbatim into the summary, and never populate a "body" for an ingested comm (body is only for notes the user types themselves). Set source ("gmail" for email, "gcal" for calendar) and external_id (the thread/event id) so a re-run never double-logs.
- RECENCY comes from the logged contact-type entry — do NOT separately hand-set last_interaction_at for a meeting you've logged.
- LIVING SUMMARY: when a person's or deal's state MATERIALLY changed, propose a refreshed living summary — the current state in a sentence or two (where it stands, open items, next step, blocker, key dates). LEAD with a standalone one-line headline sentence that reads well on its own (the dashboard shows only that first sentence, trimmed by code), then add detail. REGENERATE it to reflect the new reality (integrate old + new); do not blindly append or discard prior context. Cite provenance (which comm/entry it's built from). No living-summary churn for trivial/no-change items.
- Do NOT create timeline entries or summaries for items you SKIP (junk/automated/cold).
Output strictly as the proposals JSON.`

const PROPOSALS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    new_contacts: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, email: { type: 'string' }, org: { type: 'string' }, reason: { type: 'string' } }, required: ['name'] } },
    new_organizations: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, domain: { type: 'string' } }, required: ['name'] } },
    deal_updates: { type: 'array', items: { type: 'object', properties: {
      deal: { type: 'string' }, change: { type: 'string' }, reason: { type: 'string' } }, required: ['deal', 'change'] } },
    conflicts: { type: 'array', items: { type: 'object', properties: {
      record: { type: 'string' }, field: { type: 'string' }, current: { type: 'string' }, proposed: { type: 'string' } }, required: ['record', 'field'] } },
    timeline: { type: 'array', description: 'one entry per logged touchpoint', items: { type: 'object', additionalProperties: false, properties: {
      type: { type: 'string', description: 'email | meeting | call' },
      subject: { type: 'string' },
      summary: { type: 'string', description: 'AI gist — NOT the raw body' },
      source: { type: 'string', description: 'gmail | gcal' },
      external_id: { type: 'string' },
      occurred_at: { type: 'string' },
      people: { type: 'array', items: { type: 'string' } },
      deals: { type: 'array', items: { type: 'string' } },
      organizations: { type: 'array', items: { type: 'string' } },
    }, required: ['type', 'summary', 'people'] } },
    summaries: { type: 'array', description: 'living-summary refreshes on materially-changed records', items: { type: 'object', additionalProperties: false, properties: {
      record: { type: 'string' }, record_type: { type: 'string', description: 'person | deal' },
      summary: { type: 'string' }, provenance: { type: 'string', description: 'which comm/entry it was built from' },
    }, required: ['record', 'summary'] } },
    skipped: { type: 'array', items: { type: 'object', properties: {
      item: { type: 'string' }, reason: { type: 'string' } }, required: ['item'] } },
  },
  required: ['new_contacts', 'new_organizations', 'deal_updates', 'conflicts', 'timeline', 'summaries', 'skipped'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    checks: { type: 'array', items: { type: 'object', additionalProperties: false, properties: {
      dimension: { type: 'string' }, expectation: { type: 'string' }, outcome: { type: 'string' },
      pass: { type: 'boolean' }, severity: { type: 'string', enum: ['critical', 'minor'] }, note: { type: 'string' },
    }, required: ['dimension', 'pass', 'severity'] } },
    quality: { type: 'string', enum: ['correct', 'minor_issues', 'wrong'] },
    score: { type: 'number', description: '0-100, weight critical failures heavily' },
    critical_failures: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['checks', 'quality', 'score', 'critical_failures', 'summary'],
}

// Haiku dropped (2026-07-14, Rian): too problematic/inconsistent for this product. Sonnet + Opus only.
const MODELS = ['sonnet', 'opus']

const SCENARIOS = [
  {
    id: 'N1-progress',
    title: 'Deal-progressing email → timeline + living summary + compliance',
    stresses: ['one timeline entry per email', 'compliance: gist not raw body', 'living summary refresh', 'verbal-not-won', 'start-date not close-date'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS: David Okafor · david@meridianhealth.com · CEO · prospect
ORGANISATIONS: Meridian Health · meridianhealth.com
DEALS: "Meridian — fractional COO engagement" · stage: proposal · status: open · amount: 30000`,
    inputs: `EMAIL (gmail thread id: THREAD-MER-1) — from: David Okafor <david@meridianhealth.com>, to: you
Subject: Re: proposal
Body: The board approved the engagement at the $30k we discussed — everyone's aligned. Let's plan to start Sept 1. Next step on my side: I'll send the signed order form by Friday. — David Okafor, CEO, Meridian Health`,
    rubric: `- TIMELINE: exactly ONE entry, type=email, source=gmail, external_id=THREAD-MER-1, linked to David Okafor (people) AND the Meridian deal (deals). Its summary is a GIST (board approved $30k, moving to verbal, Sept 1 start, next: order form Friday).
- COMPLIANCE (critical): the summary must NOT copy the raw body verbatim; the phrase "everyone's aligned" (raw filler) should NOT be reproduced word-for-word; no raw "body" field populated for this ingested email.
- LIVING SUMMARY: a refreshed summary on the Meridian DEAL reflecting: verbal, $30k, ~Sept 1 start, next = signed order form; provenance cites this email.
- DEAL UPDATE: stage proposal -> verbal (NOT won — it's a verbal/approval signal). "Sept 1" is a START date and must NOT be recorded as close date.
CRITICAL: storing the raw body / copying it verbatim; marking the deal won; Sept 1 as close date; NO timeline entry, or a timeline entry not linked to the deal.`,
  },
  {
    id: 'N2-multiparty',
    title: 'Multi-attendee meeting across two deals → ONE many-to-many entry',
    stresses: ['single entry links many people + many deals', 'no split-per-person', 'org dedup by domain', 'recency for all attendees not a conflict'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS: Sarah Chen · sarah@nimbus.io · Founder · client
ORGANISATIONS: Nimbus · nimbus.io
DEALS:
- "Nimbus rollout" · stage: proposal · status: open · amount: 45000
- "Nimbus expansion" · stage: discovery · status: open · amount: 20000`,
    inputs: `CALENDAR EVENT (gcal event id: EVT-NIM-Q3, past, 2026-07-12) — Title: Nimbus quarterly — rollout + expansion
Attendees: sarah@nimbus.io (Sarah Chen), marcus@nimbus.io (Marcus Lee, CTO), dana@nimbus.io (Dana Poe, Ops), you@rioconsulting.com
Notes in the invite: reviewed the rollout proposal and scoped the expansion.`,
    rubric: `- TIMELINE: exactly ONE meeting entry (NOT one per attendee), type=meeting, source=gcal, external_id=EVT-NIM-Q3, linked to ALL THREE people (Sarah Chen, Marcus Lee, Dana Poe) AND BOTH deals (Nimbus rollout + Nimbus expansion) AND the Nimbus org.
- NEW CONTACTS: Marcus Lee + Dana Poe (both @nimbus.io) — linked to the EXISTING Nimbus org (dedupe by domain; do NOT create a new Nimbus org).
- RECENCY: all three attendees' last-contact is driven by this logged meeting; must NOT be raised as a conflict, and you should NOT separately hand-set last_interaction_at.
- Must NOT add the user (you@rioconsulting.com).
CRITICAL: splitting into multiple timeline entries; a timeline entry missing any attendee or either deal in its links; duplicate Nimbus org; adding the user.`,
  },
  {
    id: 'N3-noise',
    title: 'Noise gauntlet → log ONLY the real touchpoint',
    stresses: ['no timeline entry for junk', 'worthiness applies to logging too'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS: (none relevant)
ORGANISATIONS: (none)
DEALS: (none)`,
    inputs: `EMAIL 1 — from: The Hustle <newsletter@thehustle.co> — Subject: 5 startups to watch — [newsletter].
EMAIL 2 — from: Stripe <receipts@stripe.com> — Subject: Your receipt #1234 — [automated receipt].
EMAIL 3 — from: Kyle Brenner <kyle@growthagency.io> — Subject: Quick SEO question — Body: Hi, I'm Kyle from Growth Agency, we 3x inbound for consultancies. Free to chat? [UNSOLICITED cold pitch].
EMAIL 4 (gmail thread id: THREAD-VELA-9) — from: Marta Ruiz <marta@velafoods.com>, to: you — Subject: Re: ops review scope — Body: Thanks for the call yesterday — the scope looks right, let's kick off next month. — Marta Ruiz, Head of Ops, Vela Foods`,
    rubric: `- TIMELINE: exactly ONE entry — for Marta's email (type=email, source=gmail, external_id=THREAD-VELA-9, linked to Marta Ruiz + Vela Foods). NO timeline entries for emails 1, 2, or 3.
- NEW: contact Marta Ruiz + org Vela Foods (velafoods.com). SKIP the newsletter, receipt, and Kyle's cold pitch.
CRITICAL: creating a timeline entry (or contact) for ANY of the newsletter/receipt/cold-pitch senders; missing Marta's entry.`,
  },
  {
    id: 'N5-dealdedup',
    title: 'Existing deal advances → UPDATE, not a duplicate (regression for the live bug)',
    stresses: ['deal read-before-write', 'match by name+org', 'no duplicate deal', 'timeline links the EXISTING deal'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS: David Okafor · david@meridianhealth.com · Founder · prospect
ORGANISATIONS: Meridian Health · meridianhealth.com
DEALS: "Meridian — fractional COO engagement" · stage: proposal · status: open · amount: 30000  (already exists, linked to David Okafor)`,
    inputs: `CALENDAR EVENT (gcal event id: EVT-MER-1, past, 2026-07-11) — Title: Meridian sync — Attendees: david@meridianhealth.com, you@rioconsulting.com
Description: Reviewed the fractional COO proposal. The board approved the $30k engagement; aiming to start Sept 1. David will send the signed order form by Friday.`,
    rubric: `- The "Meridian — fractional COO engagement" deal ALREADY EXISTS. This must be a DEAL UPDATE (stage proposal -> verbal, status stays open), NOT a new deal. Creating a SECOND "Meridian — fractional COO engagement" (in new_deals) is the critical failure this scenario exists to catch.
- TIMELINE: one meeting entry (source=gcal, external_id=EVT-MER-1) linked to David AND the EXISTING Meridian deal.
- Sept 1 is a START date, not a close date. Verbal, not won.
- David already exists — do NOT re-create him.
CRITICAL: a duplicate Meridian deal in new_deals; marking it won; Sept 1 as close date; re-creating David.`,
  },
  {
    id: 'N4-regenerate',
    title: 'Living summary REGENERATES (integrate, not append/discard) + provenance',
    stresses: ['regenerate-not-blind-edit', 'integrate prior + new state', 'provenance', 'compliance'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS: Priya Nair · priya@caldergroup.com · CEO · prospect
ORGANISATIONS: Calder & Co · caldergroup.com
DEALS: "Calder — fractional ops" · stage: verbal · status: open · amount: 45000
  EXISTING living summary on this deal: "In verbal at $45k. Priya is the decision-maker and is reviewing the SOW; awaiting her sign-off."`,
    inputs: `EMAIL (gmail thread id: THREAD-CAL-7) — from: Priya Nair <priya@caldergroup.com>, to: you
Subject: Re: SOW
Body: We're good on the price. The only change I need: make it a 3-month initial term so my co-founder will sign off. Can you send the revised SOW by next week? — Priya`,
    rubric: `- LIVING SUMMARY on the Calder deal: REGENERATED to reflect the new reality AND keep the still-true prior context — e.g. "Verbal at $45k; price agreed; the blocker was co-founder sign-off, addressed by moving to a 3-month initial term; next: send the revised SOW by next week." It must INTEGRATE (not blindly append a line, and not discard that Priya is the decision-maker); provenance cites this email.
- TIMELINE: one email entry (source=gmail, external_id=THREAD-CAL-7) linked to Priya + the Calder deal, summary a gist.
- COMPLIANCE: gist only, no raw body stored.
CRITICAL: a summary that loses the prior context entirely, OR that just tacks on a raw line without integrating; missing provenance; storing the raw body; no timeline entry.`,
  },
]

function runPrompt(s) {
  return `${SKILL_RULES}

## You (the operator)
${s.self}

## Current CRM state (what a lookup returns)
${s.crm_state}

## Incoming items to process
${s.inputs}

Produce the proposals JSON now — including the timeline entries and any living-summary refreshes. In "skipped", list items you deliberately did not act on and why.`
}

function judgePrompt(s, proposals) {
  return `You are a strict evaluator of a CRM enrichment run, focused on the NOTES/CONTEXT LAYER. Score the model's proposals against the rubric.

## Scenario: ${s.title}
## Operator: ${s.self}
## CRM state
${s.crm_state}
## Incoming items
${s.inputs}
## Rubric (correct behaviour)
${s.rubric}

## The model's proposals
${JSON.stringify(proposals, null, 2)}

For each rubric point produce a check (dimension, expectation, outcome, pass, severity, note). severity=critical for: storing/verbatim-copying a raw comm body, a missing or wrongly-linked timeline entry, splitting a meeting into multiple entries, logging a skipped junk sender, a living summary that discards prior context or only blindly appends, a duplicate org, or adding the user. severity=minor for suboptimal wording/labels/subject.
Set quality: "correct" = all right; "minor_issues" = only minor slips, NO critical failures; "wrong" = one or more critical failures.
score 0-100, weight critical failures heavily (any critical failure puts it below 60). List critical_failures as short strings. One-line summary.`
}

const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const wantScenarios = A.scenarios ? SCENARIOS.filter((s) => A.scenarios.includes(s.id)) : SCENARIOS
const wantModels = A.models ? MODELS.filter((m) => A.models.includes(m)) : MODELS

const pairs = []
for (const s of wantScenarios) for (const m of wantModels) pairs.push({ scenario: s, model: m })

const results = await pipeline(
  pairs,
  (pair) =>
    agent(runPrompt(pair.scenario), {
      label: `run ${pair.scenario.id}·${pair.model}`,
      phase: 'Run',
      model: pair.model,
      schema: PROPOSALS_SCHEMA,
    }).then((proposals) => ({ pair, proposals })),
  (prev, pair) => {
    if (!prev || !prev.proposals) return { scenario: pair.scenario.id, model: pair.model, verdict: null }
    return agent(judgePrompt(pair.scenario, prev.proposals), {
      label: `judge ${pair.scenario.id}·${pair.model}`,
      phase: 'Judge',
      model: 'opus',
      schema: VERDICT_SCHEMA,
    }).then((verdict) => ({ scenario: pair.scenario.id, model: pair.model, verdict, proposals: prev.proposals }))
  },
)

const flat = results.filter(Boolean)
const byScenario = {}
for (const r of flat) {
  byScenario[r.scenario] = byScenario[r.scenario] || {}
  byScenario[r.scenario][r.model] = r
}
const summ = (r) => (r && r.verdict ? { score: r.verdict.score, quality: r.verdict.quality, critical: r.verdict.critical_failures, summary: r.verdict.summary } : null)

const scenarioReport = wantScenarios.map((s) => ({
  id: s.id, title: s.title, stresses: s.stresses,
  haiku: summ(byScenario[s.id]?.haiku), sonnet: summ(byScenario[s.id]?.sonnet), opus: summ(byScenario[s.id]?.opus),
}))

const byModel = {}
for (const m of MODELS) {
  const vs = flat.filter((r) => r.model === m).map((r) => r.verdict).filter(Boolean)
  byModel[m] = {
    n: vs.length,
    avg: Math.round(vs.reduce((a, v) => a + (v.score || 0), 0) / (vs.length || 1)),
    correct: vs.filter((v) => v.quality === 'correct').length,
    minor: vs.filter((v) => v.quality === 'minor_issues').length,
    wrong: vs.filter((v) => v.quality === 'wrong').length,
    critical_failures: vs.reduce((a, v) => a + ((v.critical_failures && v.critical_failures.length) || 0), 0),
  }
}

log(`done: ${flat.length} runs. haiku ${byModel.haiku?.avg} · sonnet ${byModel.sonnet?.avg} · opus ${byModel.opus?.avg}`)
return { byModel, scenarioReport, raw: flat }
