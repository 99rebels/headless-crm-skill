# Meeting prep — build context for the skill (not yet built)

**Status (2026-07-14):** Design captured, **not built.** This is context for a future instance to build
a **meeting-prep skill** on claude.ai, plus the dependencies/gaps to check first. Kept light on
purpose — the schema and enrichment loop may change before this gets built, so treat specifics as
"true as of now," not a spec.

**Reference mockup:** [mockups/meeting-prep.html](mockups/meeting-prep.html) — the exact layout and
tone. Sits beside [mockups/deep-view-company.html](mockups/deep-view-company.html); same "Ledger"
identity.

## What it is (one line)
The **deep view, re-ordered for the 25 minutes before a call**: time-boxed and action-first. History
moves to the back; *this meeting* moves to the front. It answers "what do I say / ask / bring," not
"what happened." Same data, different altitude — so it should be a **mode of the same skill family as
the deep view**, not a separate object.

## The one new input: the calendar event (read live, never stored)
Everything else reuses the notes substrate; the only new thing is the **upcoming Google Calendar
event**, read **client-side at prep time** (the loop already uses Google Calendar as a source). From
the event: title, start→end (**= the "30 min" duration, computed, not stored**), and the **attendee
list**. Attendees are matched to `person` records **by email**. A future meeting's details are never
persisted — we read them when we build the prep.

## What each part of the mockup comes from
- **Header (title / time / 30 min / Meet)** — the live calendar event.
- **"Who's in the room"** — calendar attendees → `person` records (email match), with role chips and a
  one-line "how to work with them."
- **"Where you left off"** — the most recent `meeting`/`email` `interaction.summary`. Stored.
- **"What to cover" talking points** — **generated at prep time**, NOT stored. The model synthesizes
  them from `deal.summary` (living summary) + the recent timeline + deal facts + the attendee list.
  This is the key point: talking points are prose/judgment (the model writes them), not facts to
  warehouse. No "open questions" field is needed or wanted.
- **"Bring with you"** — the user's open items (today: read from the living-summary prose; see
  commitments note).
- **"At a glance"** — `deal` fields (amount, stage, `expected_close_date`).

## Dependencies / issues to check BEFORE building
1. **Attendee `interaction_link`s (the main one).** Two things lean on the loop having linked people to
   past interactions:
   - *"Who's in the room"* richness beyond a bare name — resolving an attendee to a real `person` with
     role + recency.
   - *"First time you're meeting Marcus"* — derived from the **absence** of a prior `meeting`-type
     `interaction_link` for that person.
   `interaction_link` exists (0003), but **confirm the enrichment loop actually populates attendee
   links on ingest.** If it doesn't yet, that's a small loop change. **Fallback if not:** match
   attendee emails to `person` records directly (still gives names + roles), and drop the "first time
   meeting" derivation until links are populated.
2. **Role chips (champion / blocker).** The room cards want a role. Per
   [source-attribution.md](source-attribution.md) §3, roles may live in living-summary prose (v1) or as
   typed `association.relationship_type`. Either is readable; just know which one is the source when
   building.
3. **Living-summary richness = talking-point quality.** Talking points are only as sharp as the summary
   and timeline feeding them. Thin summary → generic prep. Not a blocker, a quality dependency — and
   the same confident-fiction risk the summary discipline (provenance + digest approval) manages.
4. **Trigger / discovery.** How the user invokes it ("prep me for my 2pm", "brief me on my next Nimbus
   meeting"): the skill finds the event, resolves the org/deal from the attendees, assembles. Worth a
   discovery-test pass like the other skills.

## The nice property
Unlike the deep view (which wants an org living-summary and, maybe, structured commitments), **meeting
prep needs no new schema** — it runs on the existing notes substrate + the live calendar read. The one
thing to *verify* is the attendee-link plumbing above; everything else is read + synthesize.

## Related
- [source-attribution.md](source-attribution.md) — the deep view build brief + the source-drill model
  this reuses.
- [commitments-ledger.md](commitments-ledger.md) — the "structured open items" question that also
  affects the "Bring with you" list here.
