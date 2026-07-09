# Validation plan — prove pull before building

*The most important work right now is NOT code. It's finding out whether the niche is real and whether self-maintenance actually solves their pain. This is cheap, and it's the thing that killed us last time by being skipped. Do this before writing the product.*

---

## The two questions everything hinges on

1. **Demand:** Would a solo/fractional operator pay for a simple CRM that lives in Claude and fills itself in? (Concept §8.1)
2. **Retention / the real killer:** *Why did they abandon their last CRM or spreadsheet?* If the answer isn't some version of "keeping it updated was a chore," then self-maintenance isn't the unlock and the thesis wobbles. (Concept §8.2)

Q2 matters more than Q1. People are polite in interviews and will say "sure, sounds useful" (cheap yes). The story of *what they already quit and why* is real, unsolicited evidence. Chase that.

## Who to talk to

Independent consultants, fractional CxOs (CFO/CMO/COO), boutique agency owners, solo founders — anyone running a **relationship pipeline** who already uses Claude. Aim for ~10–15 real conversations before drawing conclusions; ~5 saying the same specific thing unprompted is a strong signal.

## How to reach them cold — and the stealth question

**On "I don't want to make the idea too known":** at this stage that instinct is mostly a trap, and here's the honest reasoning — the graveyard is full of *secret products nobody wanted*, not of great products copied before launch. Your edge will be execution, niche focus, and being native-in-Claude first; none of that leaks in a conversation. The funded players already have the general idea. **Obscurity protects a weak position; it doesn't protect a good one.** The good news: the *best* validation method is also the *quietest* one — you don't need to broadcast to learn.

So resolve the tension this way: **validate through 1:1 conversations and listening, not public announcements.** Talking to 15 people privately doesn't "make it known" in any meaningful way. Posting "launching my CRM, sign up!" to a big subreddit is *more* exposure for *worse* signal. Both goals point the same direction.

Channels, best-first for this niche:

1. **Listen before you ask (cheapest, fully stealth, do this first).** Mine existing complaints where the pain is *unsolicited*: search Reddit / X / forums for phrases like "hate my CRM," "CRM too complicated," "spreadsheet for clients," "gave up on HubSpot," "CRM for consultants." Unsolicited pain beats solicited opinion every time. Costs nothing, reveals nothing, and tells you if the pain is real and how people phrase it (their words become your copy).
2. **LinkedIn — the best *targeted* channel for this niche.** Fractional execs and consultants live there and are findable by title ("fractional CFO," "independent consultant," "founder"). Send a genuine, short research ask ("I'm researching how independent consultants keep track of clients and pipeline — 15 min, no pitch?"). High-quality targets, and 1:1 = zero broadcast.
3. **Niche communities.** Fractional-exec and consultant Slack/Discord groups (e.g. fractional-work communities), indie-hacker circles (for the solo-founder slice). Warm-ish, targeted, low-exposure. Read the room's rules; contribute before asking.
4. **Reddit — good for *listening* and *soft* 1:1, weak for broadcast.** Relevant subs: r/consulting, r/fractional, r/freelance, r/agency, r/smallbusiness, r/Entrepreneur (and r/SaaS / r/indiehackers for *peers*, not customers). Use it to find complaint threads and DM helpfully, or ask a genuine research question ("how do you track clients/pipeline, and what do you hate about it?"). Direct "buy my thing" posts get removed/downvoted and expose the idea for little signal — avoid.
5. **Cold email / DM.** Independent consultants are easy to find; a short genuine research ask converts fine at small numbers.

**Skip for now:** build-in-public on X, "coming soon" landing pages, Product Hunt, anything broadcast-shaped. That's the opposite of your stealth preference *and* premature — you have nothing to validate against yet.

## How to run the conversation (so you get truth, not politeness)

- **Frame it as research, not a pitch.** "I'm trying to understand a problem," not "I built a thing, would you buy it." You want their reality, not their reaction to your idea. (This also keeps the idea quiet.)
- **Ask about the past, not the future.** "Walk me through how you track clients today." "What did you use before? Why'd you stop?" Past behaviour is evidence; future intentions are hopes.
- **Shut up and let them talk.** The upkeep-chore story should come out *unprompted*. If you have to lead them to it, that's a weak signal.
- **Only near the end, test the wedge:** "if something quietly kept that up to date for you, inside Claude, what would that be worth?" Watch for genuine pull vs. polite interest.

## What a pass / fail looks like

- **Pass:** a clear majority describe the upkeep-chore as *the* reason they quit past tools, and several show real (not polite) interest in a self-maintaining, in-Claude CRM — ideally "when can I try it?" energy.
- **Weak/fail:** they're basically fine with their spreadsheet, or their pain is something *else* (finding leads, sending outreach — that's the outbound lane we're deliberately not in), or interest is uniformly lukewarm. If so, the thesis needs to change *before* any build — that's a cheap, valuable no.

## Only after this: the build

**Note (2026-07-09):** the plumbing is now further along than this section assumed — the schema + core + MCP adapter for contacts are built and proven (see `roadmap.md` Phase 1). The differentiator — the **self-maintenance loop** on real comms — is still the unproven, make-or-break part, building on the read-before-write dedup seed in `server/src/core/person.ts`. Prove self-maintenance quality *first* when you get there — it's the retention bet the whole product rests on. Validation conversations still gate how hard we push.
