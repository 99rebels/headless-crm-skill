export const meta = {
  name: 'enrichment-eval',
  description: 'Stress-test the enrichment extract+reconcile skill across models on adversarial scenarios',
  phases: [
    { title: 'Run', detail: '6 scenarios × 3 models produce proposals' },
    { title: 'Judge', detail: 'Opus scores each run against its rubric' },
  ],
}

// The real skill's extract+reconcile+guardrail rules (condensed, faithful to SKILL.md) — this is
// what we are actually testing: do models FOLLOWING these rules behave correctly?
const SKILL_RULES = `You keep a CRM current from incoming email and calendar. For the given CRM state and incoming items, propose changes. Rules:
- Extract only concrete, STATED facts that map to the CRM (person: name/title/phone/emails/lifecycle_stage/last_interaction_at/attributes; organization: name/domain; deal: name/stage/status/amount/close_date; associations: works_at, decision_maker). Never infer or guess.
- Read before write: check the CRM state first. If a person's email or an org's domain already exists, it is an UPDATE, not a new record. Dedupe people by email, and when emails differ dedupe by strong name+context match. Dedupe orgs by domain (Acme / Acme Corporation / acme.com are the same org).
- NEVER silently overwrite: filling an EMPTY field or adding a new attribute is a normal update; changing an existing NON-EMPTY value to a different value is a CONFLICT — surface it as a conflict, do not overwrite. Exception: last_interaction_at moving to a MORE-RECENT date is an enrichment, not a conflict.
- Deal dates & stage are precise: expected_close_date is when the deal will CLOSE / be decided, NOT a project start or kickoff date — never write a start date ("start Sept 1", "kick off next month") into close_date. status "won" means the deal is ACTUALLY closed/signed; a verbal yes, board approval, or "budget approved" is the "verbal" stage with status still "open", never "won". Never mark a deal won/lost on a verbal or speculative signal. Only create a deal for a concrete opportunity (a project/engagement/amount discussed), not a vague mention.
- Worthiness: not every sender is a relationship. Skip newsletters, receipts, automated/no-reply, notifications, and cold/unsolicited sales pitches. Add someone only for a real business relationship (client/prospect/partner/investor). List what you skip and why.
- Confidence: direct participants (email From/To/Cc; meeting attendees) are high; someone only MENTIONED in a body is low ("mentioned only").
- Do not add the user themselves, or internal colleagues (same email domain as the user).
- Never treat quoted or forwarded HISTORY as new facts unless it is the actual new content of the message.
- Cross-source: the same person from an email AND a calendar event is ONE proposal, not two.
- Never merge two DIFFERENT people who happen to share a name.
Output strictly as the proposals JSON. In "skipped", list items you deliberately did not act on, with the reason.`

const PROPOSALS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    new_contacts: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, email: { type: 'string' }, title: { type: 'string' },
      lifecycle_stage: { type: 'string' }, org: { type: 'string' }, source: { type: 'string' },
      confidence: { type: 'string' }, reason: { type: 'string' } }, required: ['name'] } },
    new_organizations: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, domain: { type: 'string' }, source: { type: 'string' }, reason: { type: 'string' } }, required: ['name'] } },
    new_deals: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, stage: { type: 'string' }, amount: { type: 'number' }, org: { type: 'string' }, reason: { type: 'string' } }, required: ['name'] } },
    updates: { type: 'array', items: { type: 'object', properties: {
      record: { type: 'string' }, change: { type: 'string' }, source: { type: 'string' }, reason: { type: 'string' } }, required: ['record', 'change'] } },
    deal_updates: { type: 'array', items: { type: 'object', properties: {
      deal: { type: 'string' }, change: { type: 'string' }, reason: { type: 'string' } }, required: ['deal', 'change'] } },
    conflicts: { type: 'array', items: { type: 'object', properties: {
      record: { type: 'string' }, field: { type: 'string' }, current: { type: 'string' }, proposed: { type: 'string' }, reason: { type: 'string' } }, required: ['record', 'field'] } },
    skipped: { type: 'array', items: { type: 'object', properties: {
      item: { type: 'string' }, reason: { type: 'string' } }, required: ['item'] } },
  },
  required: ['new_contacts', 'new_organizations', 'new_deals', 'updates', 'deal_updates', 'conflicts', 'skipped'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    checks: { type: 'array', items: { type: 'object', additionalProperties: false, properties: {
      dimension: { type: 'string' },
      expectation: { type: 'string' },
      outcome: { type: 'string' },
      pass: { type: 'boolean' },
      severity: { type: 'string', enum: ['critical', 'minor'] },
      note: { type: 'string' },
    }, required: ['dimension', 'pass', 'severity'] } },
    quality: { type: 'string', enum: ['correct', 'minor_issues', 'wrong'],
      description: 'correct = all right; minor_issues = only minor slips, no critical failures (a NEAR MISS); wrong = one or more critical failures' },
    score: { type: 'number', description: '0-100, weight critical failures heavily' },
    critical_failures: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['checks', 'quality', 'score', 'critical_failures', 'summary'],
}

const MODELS = ['haiku', 'sonnet', 'opus']

const SCENARIOS = [
  {
    id: 'S1-combo',
    title: 'Intro + alias-dedup + title conflict',
    stresses: ['net-new multi-entity', 'conflict-not-overwrite', 'name-based alias dedup', 'start-date vs close-date'],
    self: 'you@rioconsulting.com (domain rioconsulting.com)',
    crm_state: `CONTACTS:
- David Okafor · david@meridianhealth.com · title: Founder · lifecycle: prospect
- Sarah Mills · sarah@northwind.co · title: COO · lifecycle: client
ORGANISATIONS:
- Meridian Health · meridianhealth.com
- Northwind Logistics · northwind.co
DEALS:
- "Meridian — fractional COO engagement" · stage: proposal · status: open · amount: 30000`,
    inputs: `EMAIL 1 — from: Jordan Blake <jordan@blakeadvisory.com>, to: you@rioconsulting.com, cc: priya@caldergroup.com
Subject: intro — Priya @ Calder needs ops help
Body: Meet Priya Nair, CEO of Calder & Co (caldergroup.com). They're scaling and need fractional ops support — you're the right fit. Priya, take it from here. — Jordan Blake, Blake Advisory

EMAIL 2 — from: David Okafor <david@meridianhealth.com>, to: you
Subject: Re: proposal
Body: The board approved the engagement at the $30k we discussed. Let's start Sept 1. — David Okafor, CEO, Meridian Health

EMAIL 3 — from: Sarah Mills <sarah.mills@gmail.com>, to: you
Subject: doc from my personal email
Body: Reaching you from my personal address since I'm out of office — attaching the signed doc. — Sarah (Northwind)`,
    rubric: `- CREATE contact Priya Nair (priya@caldergroup.com, CEO, lifecycle lead), high confidence (Cc'd), linked works_at Calder & Co.
- CREATE org Calder & Co (caldergroup.com).
- CREATE a new early-stage deal for Calder.
- CONFLICT on David Okafor title: Founder -> CEO. Must be FLAGGED as a conflict, NOT silently overwritten (a plain title update = failure).
- UPDATE Meridian deal: stage proposal -> verbal. "start Sept 1" is a START date and must NOT be recorded as expected_close_date.
- EMAIL 3 is from sarah.mills@gmail.com signed "Sarah (Northwind)" — the SAME Sarah Mills already in the CRM. Correct: recognise as existing Sarah and add the alias email (enrichment) or flag as likely-same. MUST NOT create a duplicate Sarah Mills contact.
CRITICAL: silently overwriting David's title; duplicate Sarah; missing the conflict; recording Sept 1 as close date.`,
  },
  {
    id: 'S2-noise',
    title: 'Noise gauntlet (one real email in the junk)',
    stresses: ['worthiness filter', 'automated-sender skip', 'cold-pitch judgment', 'find the signal'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS: (none relevant)
ORGANISATIONS: (none relevant)
DEALS: (none)`,
    inputs: `EMAIL 1 — from: The Hustle <newsletter@thehustle.co> — Subject: 5 startups to watch this week — Body: [marketing newsletter].
EMAIL 2 — from: Stripe <receipts@stripe.com> — Subject: Your receipt from Acme SaaS #1234 — Body: [automated payment receipt].
EMAIL 3 — from: Calendly <no-reply@calendly.com> — Subject: New event scheduled — Body: Do not reply.
EMAIL 4 — from: Kyle Brenner <kyle@growthagency.io> — Subject: Quick question about your SEO — Body: Hi, I'm Kyle from Growth Agency. We help consultancies 3x their inbound. Free to chat this week? — Kyle Brenner, Growth Agency, growthagency.io  [UNSOLICITED cold sales pitch]
EMAIL 5 — from: LinkedIn <notifications@linkedin.com> — Subject: You have 3 new connection requests — Body: [automated].
EMAIL 6 — from: Marta Ruiz <marta@velafoods.com>, to: you — Subject: Re: ops review scope — Body: Thanks for the call yesterday — the scope looks right. Let's kick off next month. — Marta Ruiz, Head of Ops, Vela Foods`,
    rubric: `- CREATE contact Marta Ruiz (marta@velafoods.com, Head of Ops, active relationship) + CREATE org Vela Foods (velafoods.com).
- SKIP emails 1,2,3,5 (newsletter, receipt, automated calendar, automated LinkedIn) — must NOT create contacts/orgs from them.
- EMAIL 4 (Kyle, cold unsolicited pitch): correct behaviour is SKIP — a cold vendor pitch is not a relationship. Adding Kyle as a contact = a failure (the discriminating case; weaker models over-add here).
CRITICAL: adding ANY automated/newsletter/notification sender; missing Marta. Adding Kyle = notable but less severe than adding automated senders.`,
  },
  {
    id: 'S3-restraint',
    title: 'Restraint / inference traps',
    stresses: ['never-guess', 'no speculative deal close', 'internal-colleague exclusion'],
    self: 'you@rioconsulting.com (domain rioconsulting.com)',
    crm_state: `CONTACTS:
- Sarah Mills · sarah@northwind.co · COO · client
ORGANISATIONS:
- Northwind Logistics · northwind.co
- Acme Inc · acme.com
DEALS:
- "Acme — retainer" · stage: proposal · status: open · amount: 24000`,
    inputs: `EMAIL 1 — from: Tom Reyes <tom@northwind.co>, to: you — Subject: Re: Q3 — Body: I'm taking over the finance side from Sarah going forward. — Tom Reyes, CFO, Northwind Logistics
EMAIL 2 — from: Rob Deane <rob@acme.com>, to: you — Subject: thoughts — Body: Honestly we should probably wrap things up with the retainer soon, but let's discuss next quarter. — Rob
EMAIL 3 — from: Nina Patel <nina@brightco.com>, to: you, cc: sam@rioconsulting.com — Subject: kickoff — Body: Looping in your colleague Sam. Let's get started. — Nina, Brightco`,
    rubric: `- CREATE contact Tom Reyes (tom@northwind.co, CFO, links to existing Northwind).
- EMAIL 1 says Tom takes over "from Sarah" — MUST NOT remove, archive, downgrade, or unlink Sarah. Sarah stays unchanged (at most a flagged question, never an automatic change).
- EMAIL 2 "should probably wrap things up... discuss next quarter" is SPECULATIVE — MUST NOT mark the Acme deal lost/won/closed or change its stage. (Adding Rob Deane as a contact is fine.)
- EMAIL 3: sam@rioconsulting.com is the SAME domain as the user — an internal colleague. MUST NOT add Sam. Nina Patel (brightco.com) SHOULD be added.
CRITICAL: removing/altering Sarah; changing the Acme deal status/stage on speculation; adding internal colleague Sam.`,
  },
  {
    id: 'S4-ambiguity',
    title: 'Ambiguity (same name, mentioned-only, org aliases)',
    stresses: ['do-not-merge distinct people', 'mentioned-only confidence', 'org dedup by domain not name'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS:
- John Smith · john@acme.com · title: Head of Sales · lifecycle: client
ORGANISATIONS:
- Acme Inc · acme.com
DEALS: (none)`,
    inputs: `EMAIL 1 — from: John Smith <john.smith@brightwave.io>, to: you — Subject: intro from the conference — Body: Great meeting you at SaaStr — I lead ops at Brightwave. Let's stay in touch. — John Smith, Brightwave (brightwave.io)
EMAIL 2 — from: an existing contact, to: you — Subject: fyi — Body: I had a great chat with Elena Fisher from Northstar last week, you two should connect.
EMAIL 3 — from: John Smith <john@acme.com>, to: you — Subject: renewal — Body: Re our renewal — note it's Acme Corporation on the paperwork, and our site is acme.com. — John, Acme`,
    rubric: `- EMAIL 1: John Smith at Brightwave (john.smith@brightwave.io) is a DIFFERENT person from the existing John Smith at Acme (john@acme.com). MUST create a NEW distinct contact (John Smith, Brightwave) + CREATE org Brightwave. MUST NOT merge with or update the existing Acme John Smith.
- EMAIL 2: Elena Fisher (Northstar) is only MENTIONED (not a correspondent). If proposed, must be LOW confidence / "mentioned only"; must NOT be high confidence. Skipping her is also acceptable.
- EMAIL 3: "Acme Corporation" / "acme.com" refer to the EXISTING Acme Inc. MUST NOT create a duplicate Acme org.
CRITICAL: merging the two John Smiths; duplicate Acme org; Elena marked high-confidence.`,
  },
  {
    id: 'S5-crosssource',
    title: 'Cross-source dedup + calendar + last_interaction_at',
    stresses: ['email+calendar = one proposal', 'calendar attendee extraction', 'last_interaction enrichment not conflict', 'org dedup by domain'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS:
- David Okafor · david@meridianhealth.com · CEO · prospect · last_interaction_at: 2026-06-20
ORGANISATIONS:
- Meridian Health · meridianhealth.com
DEALS: (none)`,
    inputs: `EMAIL — from: David Okafor <david@meridianhealth.com>, to: you — Subject: next steps — Body: Good to progress this. — David
CALENDAR EVENT 1 (past, 2026-07-10) — Title: Meridian sync — Attendees: david@meridianhealth.com, carla@meridianhealth.com (Carla Nunes), you@rioconsulting.com
CALENDAR EVENT 2 (upcoming, 2026-07-15) — Title: Intro — Brightpath ops — Attendees: marcus@brightpathpartners.com (Marcus Webb), you@rioconsulting.com`,
    rubric: `- David Okafor appears in BOTH the email and calendar event 1 — must be ONE proposal, not duplicated. Update his last_interaction_at to 2026-07-10 — an ENRICHMENT (more recent), NOT a conflict.
- CREATE contact Carla Nunes (carla@meridianhealth.com) from event 1, linked works_at existing Meridian Health (dedupe org by domain — do NOT create a new Meridian org). Source calendar, high confidence.
- CREATE contact Marcus Webb (marcus@brightpathpartners.com) + CREATE org Brightpath Partners (brightpathpartners.com) from event 2.
CRITICAL: duplicate David; duplicate Meridian org; adding the user (you@rioconsulting.com); last_interaction_at flagged as a conflict.`,
  },
  {
    id: 'S6-messy',
    title: 'Messy extraction (forward, quoted history, signature-only)',
    stresses: ['extract from forwarded content', 'ignore quoted history', 'extract from signature block'],
    self: 'you@rioconsulting.com',
    crm_state: `CONTACTS: (none relevant)
ORGANISATIONS: (none)
DEALS: (none)`,
    inputs: `EMAIL 1 (a FORWARD) — from: a colleague, to: you — Subject: Fwd: partnership — Body:
Thought you'd want this.
---------- Forwarded message ----------
From: Nadia Okonkwo <nadia@lumen.health>
I'm the VP Product at Lumen Health. Keen to explore a partnership. My cell is +1 415-555-0102.

EMAIL 2 (a REPLY with quoted history) — from: Priya Nair <priya@caldergroup.com>, to: you — Subject: Re: scope — Body:
Sounds good, let's lock it in for Q3.

On Mon you wrote:
> Here's the revised scope. Note the old figure of $12,000 from the Bravo project is not relevant.
> Bravo Corp (bravo.co) was last year's engagement.

EMAIL 3 (signature-only) — from: reggie@tidecove.com, to: you — Subject: thanks! — Body:
Thanks!
Reggie Vance | Founder, Tidecove | reggie@tidecove.com | +1 212-555-0110`,
    rubric: `- EMAIL 1: extract Nadia Okonkwo (VP Product, Lumen Health, lumen.health, phone +1 415-555-0102) from the FORWARDED content. CREATE contact + org Lumen Health. (The forwarding colleague need not be added.)
- EMAIL 2: the only NEW fact is "lock it in for Q3" (a note/update on the Priya/Calder relationship). The quoted history — $12,000, "Bravo project", Bravo Corp (bravo.co) — is OLD context and must NOT be extracted. MUST NOT create a Bravo Corp org or a $12,000 deal.
- EMAIL 3: body is terse but the SIGNATURE has Reggie Vance, Founder, Tidecove, reggie@tidecove.com, phone. Extract Reggie + org Tidecove (tidecove.com).
CRITICAL: extracting Bravo Corp / the $12,000 old figure as new; missing Nadia (forward) or Reggie (signature).`,
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

Produce the proposals JSON now. Include everything you would propose; in "skipped", list items you deliberately did not act on and why.`
}

function judgePrompt(s, proposals) {
  return `You are a strict evaluator of a CRM enrichment run. Score the model's proposals against the rubric of correct behaviour.

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

For each rubric point produce a check (dimension, expectation, outcome, pass, severity, note). severity=critical for a wrong write / silent overwrite / duplicate record / added noise/automated sender / merged distinct people / lost data / extracted stale quoted history; severity=minor for suboptimal labels, confidence, wording, or a debatable add (e.g. the cold-pitch contact).
Set quality: "correct" = everything right; "minor_issues" = only minor slips, NO critical failures (a near miss); "wrong" = one or more critical failures.
score 0-100, weighting critical failures heavily (any critical failure should put it below 60). List critical_failures as short strings. One-line summary.`
}

// ---- optional filters (args: {scenarios:[ids], models:[names]}) for targeted re-runs ----
// args can arrive as an object or a JSON string — normalise both.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const wantScenarios = A.scenarios ? SCENARIOS.filter((s) => A.scenarios.includes(s.id)) : SCENARIOS
const wantModels = A.models ? MODELS.filter((m) => A.models.includes(m)) : MODELS

// ---- run: each (scenario, model) → proposals → Opus judge ----
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

// ---- synthesize ----
const flat = results.filter(Boolean)
const byScenario = {}
for (const r of flat) {
  byScenario[r.scenario] = byScenario[r.scenario] || {}
  byScenario[r.scenario][r.model] = r
}
const summ = (r) => (r && r.verdict ? { score: r.verdict.score, quality: r.verdict.quality, critical: r.verdict.critical_failures, summary: r.verdict.summary } : null)

const scenarioReport = wantScenarios.map((s) => {
  const h = byScenario[s.id]?.haiku, so = byScenario[s.id]?.sonnet, op = byScenario[s.id]?.opus
  const hv = h?.verdict, sov = so?.verdict
  let confidence46
  if (!sov || (sov.critical_failures && sov.critical_failures.length))
    confidence46 = 'SKILL-BUG — Sonnet 5 itself failed; fix the skill, not a model tier'
  else if (hv && (hv.quality === 'correct' || hv.quality === 'minor_issues'))
    confidence46 = 'HIGH — Haiku 4.5 already handles it (4.6 is stronger), no spot-check needed'
  else
    confidence46 = 'SPOT-CHECK 4.6 — Haiku 4.5 got it wrong but Sonnet 5 is fine; 4.6 sits in the gap'
  return {
    id: s.id, title: s.title, stresses: s.stresses,
    haiku: summ(h), sonnet: summ(so), opus: summ(op),
    confidence46,
  }
})

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
