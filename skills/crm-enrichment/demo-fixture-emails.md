# Demo fixture emails — the inbox that drives the enrichment loop

Four emails to place in the **dedicated demo Gmail account**. Together they exercise every
capability once. Each puts the entity details in the **body / signature**, not just the From header
— so you can send them from any account you control and the loop still extracts correctly (real
signatures carry this info anyway). Sending from the "real" addresses is nicer if easy, but not
required.

## Staging options (pick one)
- **Easiest:** from any Gmail you control, send each email TO the demo account. The loop extracts
  people/companies from the bodies + signatures, so the From address doesn't need to match.
- **Most realistic:** create free throwaway accounts (or +aliases) for the senders and send from
  those. Only worth it if quick.

Run the seed first (`cd server && npm run seed`) so the "before" state exists, then send these.

---

## 1. Intro → net-new person + org + deal  *(tests: net-new discovery, association)*
**From:** Jordan Blake · **To:** you · **Cc:** priya@caldergroup.com
**Subject:** intro — Priya @ Calder is looking for ops help

> Hi both — quick intro.
>
> Priya, meet [you] — the fractional COO I mentioned. [You], meet **Priya Nair, CEO of Calder & Co**
> (caldergroup.com). They're scaling fast and need fractional ops support, and I said you're exactly
> the right person.
>
> I'll let you two take it from here.
>
> Jordan

*Expected: new contact **Priya Nair** (CEO, priya@caldergroup.com, lead), new org **Calder & Co**
(caldergroup.com), new discovery deal, Priya linked as decision_maker. Priya is Cc'd (high
confidence).*

---

## 2. New person at an existing client  *(tests: domain dedup + works_at existing org)*
**From:** Tom Reyes · **To:** you
**Subject:** Re: Q3 numbers

> Hi [you],
>
> Adding myself to this thread — I'm the new **CFO at Northwind**, taking the finance side over from
> Sarah. I'll be your point of contact on budgets and renewals going forward.
>
> Best,
> Tom Reyes
> CFO, Northwind Logistics
> tom@northwind.co

*Expected: new contact **Tom Reyes** (CFO), org **Northwind** deduped by domain (already exists →
no duplicate), Tom linked works_at Northwind.*

---

## 3. Deal signal + a changed detail  *(tests: deal update + the never-silent-overwrite guardrail)*
**From:** David Okafor · **To:** you
**Subject:** Re: proposal

> Hi [you],
>
> Good news — the board approved the engagement at the **$30k** we discussed. Let's aim to **start
> Sept 1**. Send the paperwork whenever you're ready.
>
> Best,
> David Okafor
> **CEO**, Meridian Health
> david@meridianhealth.com

*Expected: **deal update** on Meridian (proposal → verbal, close date ~Sep 1). And because David is
seeded as "Founder" but signs off "CEO", a **conflict** in "Needs your call" — NOT a silent
overwrite.*

---

## 4. Noise → should be ignored  *(tests: the filter / no junk in the CRM)*
**From:** no-reply@calendly.com  ·  **To:** you
**Subject:** Your event with a new invitee has been scheduled

> A new event has been scheduled.
> Event: 30 Minute Meeting
> Do not reply to this email.

*Expected: **skipped** — automated sender, no relationship. Demonstrates the CRM stays clean. (Still
counts toward "emails reviewed".)*

---

## The story this tells on screen
"4 emails reviewed → 6 proposed changes": 2 new contacts, 1 new org, 1 new deal, 1 deal update,
1 conflict flagged for you — and the Calendly noise silently ignored. Approve, and the pipeline
dashboard (next skill) reflects it.
