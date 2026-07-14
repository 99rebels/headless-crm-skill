# Commitments ledger — a deferred view + one schema flag for the notes build

**Status (2026-07-13):** Parked from the UI/view work. This is a note **for the notes-schema
session** to consider while the schema is still on paper — not a build request, and deliberately
light on mechanics because the schema may have moved since this was written. It captures *what the
view would be* and *why it's worth a small forward-compat bet now*, and leaves the *how* to whoever
owns the schema.

## What the view would be
A **commitments ledger**: a single cross-record read that answers *"what did I promise, and what am
I waiting on?"* across every relationship at once — mine (owed to others) vs. theirs (owed to me),
with the record each item belongs to. It's the fractional operator's daily driver: not a view of one
deal, but a sweep of the open loops across the whole pipeline.

It is **not** part of the deep view. The deep view shows open items for *one* record; the ledger is
the *cross-record* roll-up of those same items. Different shape — an aggregate over many records
(closer in nature to the dashboard than to a single record page).

## Why it's deferred
Doing it *well* means the ledger must read commitments **as data**, not by re-parsing the living
summary's prose at render time. Prose-parsing on each read would be non-deterministic and could miss
or invent items — the same "same prompt, three different answers across models" problem that
`get_pipeline_summary` was created to fix. The settled principle applies: **if it's a fact we
aggregate, `core` holds it as data; the model only writes prose.** So a good ledger wants commitments
to exist as **structured, first-class items**, captured at enrichment time — not reconstructed later.

## The forward-compat flag (the actual ask)
While deciding where/how the living summary and its "open items" are stored, **consider capturing
commitments as structured items from the start**, rather than only as free text inside the summary.
The living summary is already slated to carry commitments/open items — this is just about *whether
they're queryable data or prose*.

Deliberately not prescribing the field/shape here — that's the schema session's call, and the schema
may already have changed. The point is only the *decision*, framed like the other cheap-now bets
already banked into the notes design (stable `id`, `owner_id`): capturing this structure **now, while
the schema is on paper, is close to free; retrofitting it later is a migration plus re-enrichment
across every record.**

## The benefit
- Unlocks the commitments ledger as a **trivial, deterministic read** later — no render-time parsing,
  consistent across models (facts-in-`core` compliant).
- It's a genuinely differentiating view: **no legacy CRM keeps commitments current**, because none
  captures them without manual entry — our enrichment loop can. Strong "works *for* me, not the
  reverse" story for the solo operator.
- Costs the solo user nothing today (the enrichment loop populates it on the existing approval path);
  pays off the moment we want the cross-record view or team handoffs ("here's what's open with this
  account").

## Scope note
No UI work is blocked on this. The deep view + meeting-prep views are being built now and show open
items per-record without it. This flag only affects whether the *cross-record ledger* is cheap or
expensive when we choose to build it.
