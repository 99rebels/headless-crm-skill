# Artifact → Claude interactivity — can our skills become a *real* interactive UI?

**Status:** research note. Written 2026-07-12. **⛔ VERDICT (2026-07-12, spike run): the core
premise below is WRONG — artifacts CANNOT call our MCP tools. Do not build write-back-from-artifact.**

> **What the spike found.** `spikes/artifact-mcp-probe.html` run on claude.ai returned
> **`window.claude` entirely undefined**. Corroborated by Anthropic's own issue tracker
> ([anthropics/claude-code#16848](https://github.com/anthropics/claude-code/issues/16848),
> **closed as "not planned"**): the `mcp_servers` parameter is *intentionally* stripped from
> artifact API calls. So **all write-back paths are closed today**: (1) no `window.claude.mcp`
> bridge; (2) `window.claude.complete()` is a tool-less sub-agent that does NOT inherit MCP
> connections; (3) the artifact CSP blocks a direct `fetch` to our own Worker; (4) there's no API
> for an artifact to inject a message into the conversation. It's a deliberate platform constraint,
> not a bug and not "coming soon."
>
> **Implication.** "Skills as the UI" = **rendering works** (dashboards/digests/previews — proven),
> **write-back does not**. Writes must go through the *conversation* (user says "import" →
> conversation-Claude calls the tool), which is the supported pattern and already works. The CSV
> "Import all" button, the digest-as-a-form, and any in-artifact write are **not feasible now.**
> Re-probe only if Anthropic reverses the not-planned decision. The optimistic "Bridge 2" section
> below is retained for history — it was based on secondary sources and is now disproven.
**Why this doc exists:** our whole product bet is "skills as the UI" — skills render HTML/JS
views inside Claude.ai instead of us shipping a separate app. This note captures what we
learned about how far that can go: can a rendered artifact send data *back* to Claude (or
straight to our CRM) so the UI is genuinely interactive, not just a read-only render?

If you're a fresh instance: read `START-HERE.md` first for the product context. The short
version — we own a small CRM (Postgres + a `core/` behind an MCP server, live on Claude.ai as
the `headless-crm` connector). Skills render two views today: the **pipeline dashboard**
(`skills/crm-dashboard/`) and the enrichment **approval digest** (`skills/crm-enrichment/`).
Both are self-contained HTML+JS artifacts. Until now we assumed they were **presentation-only**:
the artifact sandbox has no network, so every CRM *write* had to go back through the
conversation (the user types "yes, accept those", and conversation-Claude calls the MCP tools).

---

## The question

Two concrete things we wanted:

1. **Deal "deep view" button.** In the dashboard, click into a deal and press a button that
   produces a rich deep-view UI for that deal/company (a view we haven't built yet) — i.e. the
   artifact triggers the creation of more UI, instead of the user going back to chat and asking.
2. **Digest as a form.** In the approval digest, replace "I accept this and this but not X"
   (freeform prose the model has to parse) with real checkboxes/toggles. Hit **Submit** and the
   selected changes get written to the CRM.

Underlying both: **can artifact JavaScript communicate back to Claude / our backend?**

---

## What we found

There are **two** bridges from artifact JS back toward Claude. This matters — our earlier notes
only knew about the first one and treated it as a dead end for CRM work.

### Bridge 1 — `window.claude.complete(prompt)`
- Spawns a **tool-less sub-agent** and returns **text**.
- **No MCP, no CRM, no tools.** It's a pure text-in / text-out LLM call.
- Useful for: generating prose or HTML *from data already present in the page*. It cannot fetch
  or write CRM data on its own.
- This is the API our `START-HERE.md` / `roadmap.md` referenced (the "deep view via
  `window.claude.complete`" idea) and correctly flagged as limited.

### Bridge 2 — MCP-from-artifact (the new, important one)
- Reported to have shipped **~late 2025**. Artifact JS can call **connected MCP servers
  directly — read *and* write** — proxied through Claude.ai using the **signed-in user's own
  credentials** (an `mcp` namespace on `window.claude`).
- This means the dashboard artifact can call our **`headless-crm`** tools itself
  (`find_deals`, `get_deal`, `update_deal`, `update_contact`, …) without routing through the
  conversation.
- **Plan-gated:** requires **Pro / Max / Team / Enterprise**. Free-plan users don't get it.
- First-use **consent prompt** before an artifact may call a connector.

> Net: the old caveat "`window.claude.complete()` has no CRM access unless MCP-from-artifact
> works" is resolved — **MCP-from-artifact works.** That's what unlocks both use cases.

**Confidence / provenance.** The *existence* of MCP-in-artifacts (read+write to connected
tools like Gmail/Calendar/Slack/Asana, plan-gated) is confirmed by Anthropic's own support
docs. The **exact JS call signature** (`window.claude.mcp.*`) came from **secondary sources**,
not a canonical Anthropic API reference we could find. Treat the API shape as *probable, not
confirmed* until a hands-on spike (below).

Sources consulted 2026-07-12:
- Claude Help Center — *What are artifacts?* https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them
- Suprmind — *Claude Features 2026* https://suprmind.ai/hub/claude/features/
- Albato — *What Are Claude Artifacts (2026)* https://albato.com/blog/publications/how-to-use-claude-artifacts-guide

---

## How this maps onto the two ideas

### Digest as a form → CRM write — the clean win
- Render each proposed change as a checkbox/toggle; **Submit** calls the relevant MCP write
  tool(s) directly via Bridge 2. No more parsing freeform approval prose.
- **Architecturally sound:** the enrichment loop's guardrails + reconciliation already ran when
  the **digest was generated** — the digest *is* the vetted diff. "Submit the checked items" is
  just executing an already-approved diff, so we're not skipping any judgement by writing from
  the artifact.
- Highest value, lowest risk. Build this first if the spike is green.

### Deal "deep view" button — possible, but reframe it
- **There is no documented API for an artifact to spawn a new *artifact card* in the
  conversation.** Don't design around "artifact creates a sibling artifact."
- Instead: the dashboard artifact is itself an **MCP client**. The button calls a tool
  (`get_deal` + associations today, or a future `get_account_deepview` aggregation in `core`)
  and **renders the deep view inside the same artifact** (a drawer/route/modal). That feels like
  a real app and is fully self-contained.
- This rewards the discipline we already committed to (see `docs/summary-tool.md`): **facts are
  computed once, server-side in `core`.** The deep view becomes another `core/summary.ts`-style
  aggregation the artifact simply calls and renders.

---

## Caveats / risks to keep in mind
1. **Plan-gated.** Interactive writes need a paid plan tier. A free-plan solo operator wouldn't
   get them — that's a **business-model input**, not just a technical detail. The read-only
   render still works everywhere; only the interactivity is gated.
2. **API surface unconfirmed.** The exact `window.claude.mcp` call shape needs hands-on
   confirmation. Don't ship anything depending on it until verified.
3. **Keep all writes going through our MCP tools.** `core` enforces workspace scoping +
   validation. The good news: artifact JS *can only call the tools we expose* — it can't bypass
   `core`. Design rule: **no business logic in artifact JS**; it renders and it calls tools.
4. **Consent + trust.** Users approve connector access on first use. Fine, but it's a moment in
   the UX to account for.

---

## Next step — the spike is BUILT, pending a run: `spikes/artifact-mcp-probe.html`
A throwaway probe artifact now exists at [`spikes/artifact-mcp-probe.html`](../spikes/artifact-mcp-probe.html).
It has three buttons — **Detect** (dumps `window.claude`'s real shape), **Read** (`find_deals`),
**Write** (`bulk_import` upserting one disposable `spike-test@example.com` contact) — each logging to
an on-page console. Because we don't know the exact call signature, it introspects `window.claude`
*and* tries a list of candidate signatures, reporting which one works.

It answers all three unknowns: (a) real call signature, (b) is our `headless-crm` connector reachable
from the sandbox, (c) consent-prompt behavior. **Deliberately it ends by calling `bulk_import`** — the
exact tool the CSV "Import all" button will use — so a green run is the button's known-good dress
rehearsal, not just an abstract test.

**How to run (Rian, account-gated):** open claude.ai on a Pro/Max/Team/Enterprise plan with the
`headless-crm` connector on, paste the file, say "render this exactly as an HTML artifact", click the
buttons top-to-bottom, copy the log back. An automated/CLI instance can *write* the probe but cannot
*run* it (sandbox + connector auth are account-gated).

**If green → first real feature: the CSV "Import all" button.** `bulk_import` is one call and the plan
is already embedded in the import preview, so the button is a ~20-line port of the probe's Write step
into `skills/crm-import/scripts/render_preview.py`. Keep the chat fallback ("or reply `import`") for
free-plan users. Then the digest-as-a-form, then the in-artifact deep view.

## Related
- `docs/summary-tool.md` — "compute facts once in `core`" (the pattern the deep view should follow)
- `skills/crm-dashboard/`, `skills/crm-enrichment/` — the two views this would upgrade
- `START-HERE.md` — product context and current build state
