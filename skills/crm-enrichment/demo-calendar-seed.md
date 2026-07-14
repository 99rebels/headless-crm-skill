# Calendar seed — populate Google Calendar for the enrichment test

Paste this whole file into a Claude.ai chat that has the **Google Calendar** connector enabled. It
creates four events on your calendar, purpose-built to exercise the enrichment loop's **calendar
source** + the new **notes/context layer** (timeline entries, many-to-many linking, living summaries,
recency, and the "skip junk" filter).

**Before you run it:** the dates below are given **relative to today** so the events always land inside
the loop's windows (it scans the **past 14 days** and **next 7 days** — not just 24 hours). Attendee
addresses use **fake demo domains** (they match the seeded CRM, or are made-up) — Google may try to send
invites and get bounces; that's harmless, ignore it. (If your connector supports it, create them with
"don't send invitations".)

---

**Claude, please create these four Google Calendar events on my primary calendar. Work out each real
date from "today" using the relative offsets given, keep the times as listed, add the listed people as
attendees, and put the description text in each event's description/notes. Don't send email invitations
if you can avoid it. After creating them, list back the four events with the actual dates you used.**

### Event 1 — "Meridian sync"  *(PAST)*
- **When:** **3 days ago**, 10:00–10:30
- **Attendees:** david@meridianhealth.com
- **Description:** Reviewed the fractional COO proposal with David. He confirmed the Meridian **board approved the $30k engagement** and everyone's on board; we're aiming to **start Sept 1**. Next step: David sends the signed order form by Friday.

### Event 2 — "Northwind ops review"  *(PAST)*
- **When:** **5 days ago**, 14:00–14:45
- **Attendees:** sarah@northwind.co, tom@northwind.co
- **Description:** Quarterly ops review with Northwind. **Tom Reyes is the new CFO**, taking over the finance side from Sarah. Walked through the Q3 retainer scope; both happy with direction.

### Event 3 — "Intro — Brightpath ops"  *(UPCOMING)*
- **When:** **2 days from now**, 15:00–15:30
- **Attendees:** marcus@brightpathpartners.example
- **Description:** Intro call — Brightpath Partners is exploring **fractional ops support**. Marcus Webb, Head of Ops, wants to scope a possible engagement.

### Event 4 — "Dentist"  *(PAST, no external attendees)*
- **When:** **4 days ago**, 09:00–10:00
- **Attendees:** (none — just me)
- **Description:** Personal appointment.

---

## What each event is testing (so you know what "correct" looks like after you run enrichment)

| Event | Should produce |
|---|---|
| **1 · Meridian sync** | A **meeting** timeline entry linked to **David + the Meridian deal**; David's recency refreshed to Jul 11; a **living-summary** refresh on the Meridian deal (verbal, $30k, Sept 1 **start**, next = order form). Deal stage → **verbal**, NOT won. Sept 1 must **not** become a close date. |
| **2 · Northwind ops review** | **ONE** meeting entry linked to **both** Sarah *and* Tom (many-to-many); **Tom Reyes created** as a new contact and linked to the **existing** Northwind org (no duplicate org); recency refreshed for both. |
| **3 · Intro — Brightpath** | **Marcus Webb** + **Brightpath Partners** added ahead of the meeting (upcoming event). A weak/absent deal is fine — don't force one from a vague intro. |
| **4 · Dentist** | **Nothing** — no external attendee, so the loop should skip it entirely (no contact, no timeline entry). |

After the events exist, run the enrichment test from `demo-calendar-test.md` (or just tell Claude:
*"update my CRM from my calendar"*), review the digest, approve, and check the results above.
