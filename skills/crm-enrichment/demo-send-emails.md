# Hand-to-Claude: send the demo fixture emails

Paste everything in the box below into a **Claude chat that has the 99rebels.info@gmail.com Gmail
connector enabled**. It tells Claude to send the four demo emails to that same address (email
yourself), so they land in the inbox the enrichment loop reads.

> **Note:** the sender/recipient are the same account on purpose (matches the demo config, which
> `ignore`s that address rather than treating it as `self`). If Claude's Gmail tool can only create
> drafts, let it — then open Gmail and hit send on each. Run the CRM seed first (`npm run seed`).

---

```
Please send the following FOUR emails, each as a separate message, TO: 99rebels.info@gmail.com.
Use the exact subject and body given for each — keep the signatures, they matter. If you can only
create drafts, create all four and tell me.

────────────────────────────────────────────────────────
EMAIL 1
Subject: intro — Priya @ Calder is looking for ops help
Body:
Hi — quick intro before I connect you two properly.

I want you to meet Priya Nair, CEO of Calder & Co (caldergroup.com). They're scaling fast and need
fractional ops support, and I told her you're exactly the right person. Priya's on priya@caldergroup.com
— I'll let you take it from here.

Jordan
Jordan Blake · Blake Advisory
────────────────────────────────────────────────────────
EMAIL 2
Subject: Re: Q3 numbers
Body:
Hi,

Adding myself to this thread — I'm the new CFO at Northwind, taking over the finance side from Sarah.
I'll be your point of contact on budgets and renewals going forward.

Best,
Tom Reyes
CFO, Northwind Logistics
tom@northwind.co
────────────────────────────────────────────────────────
EMAIL 3
Subject: Re: proposal
Body:
Hi,

Good news — the board approved the engagement at the $30k we discussed. Let's aim to start Sept 1.
Send the paperwork whenever you're ready.

Best,
David Okafor
CEO, Meridian Health
david@meridianhealth.com
────────────────────────────────────────────────────────
EMAIL 4
Subject: Your event with a new invitee has been scheduled
Body:
A new event has been scheduled.

Event: 30 Minute Meeting
Invitee: (pending)

Do not reply to this email — replies are not monitored.
Calendly
────────────────────────────────────────────────────────
```

---

## What each email is for (so you can sanity-check the run afterwards)
1. **Priya / Calder** → net-new contact + org + a discovery deal. (Introduced, named with email — she'll
   likely show as a proposed new contact; because she's only in the body, not a direct correspondent,
   she may carry a "mentioned only" flag. That's correct behaviour.)
2. **Tom Reyes** → new contact at Northwind (existing client → org deduped by domain, Tom linked).
3. **David Okafor** → Meridian deal update (proposal → verbal, ~Sep 1) **and** a Founder→CEO conflict
   flagged in "Needs your call" — not silently overwritten.
4. **Calendly** → should be **skipped**: it's an automated notification, not a relationship. Shows the
   CRM stays clean.
