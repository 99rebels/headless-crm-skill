# crm-server

Headless AI-native CRM: a clean **core** of business logic with thin **adapters** over it.
See `../concept.md`, `../roadmap.md`, `../data-model.md` for the why/what.

## Architecture (headless-first)

```
Supabase / Postgres  ──►  CORE (business logic, interface-agnostic)  ──►  adapters
                                                                          ├─ mcp/  (built now — the product)
                                                                          ├─ api/  (later — when a 2nd consumer needs it)
                                                                          └─ web/  (later)
```

The **core** knows nothing about MCP or HTTP. All validation, association integrity, and
(later) guardrails live there, so every interface shares one implementation. There are
**two adapters over the same core today**: a local **stdio** MCP and a deployed
**Cloudflare Worker** (what Claude.ai connects to). Tools are registered once in
`src/mcp/build.ts` (`registerCrmTools`) and reused by both.

## Layout

```
db/migrations/      SQL migrations (apply in Supabase)
wrangler.jsonc      Cloudflare Worker config (the deployed adapter)
src/
  core/             the headless CRM: types + logic. No MCP/HTTP awareness.
    types.ts        the domain contract (mirrors the schema)
    db.ts           initDb(url,key) / getDb() — env-agnostic so it runs on Node AND Workers
    person.ts, workspace.ts
  mcp/
    build.ts        registerCrmTools(server, workspaceId) — the tools, shared by both adapters
    server.ts       local stdio entry (Inspector / local clients)
  worker/
    index.ts        Cloudflare Worker: OAuth shell + McpAgent, for Claude.ai
  smoke.ts, mcp-smoke.ts   verification scripts
```

## Setup (local)

1. Supabase project exists; schema applied (`db/migrations/0001_init.sql` in the SQL Editor).
2. Copy `.env.example` → `.env`, fill from Supabase (below).
3. `npm install`. Verify: `npm run smoke` and `npm run mcp-smoke` (both should pass).

## Deploy (Claude.ai)

```
npm run deploy                              # deploy the Worker to Cloudflare
npx wrangler secret put SUPABASE_URL        # set once (paste value)
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
npm run cf-build                            # dry-run bundle (no deploy) to validate a build
```
Live at `headless-crm-mcp.rianoleary.workers.dev/mcp` — add as a custom connector in
Claude.ai (no OAuth creds to enter; auto-approve). OAuth via `@cloudflare/workers-oauth-provider`.

## Environment (never commit real values)

| var | where to find it in Supabase | notes |
|-----|------------------------------|-------|
| `SUPABASE_URL` | Project Settings → API → Project URL | |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → service_role key | **secret** — server-only, bypasses RLS. Never ship to a client. |

Until the auth workstream lands, the server uses the service-role key and the **core layer
enforces `workspace_id` scoping on every query** (RLS policies come later).

## Status

**Phase 1 complete — live on Claude.ai.** Schema ✔; `contact` tools ✔ (create/find/get/update
with read-before-write dedup); deployed Worker verified end-to-end (contact created by talking
to Claude.ai). **Next:** add `organizations` + `deals` + `associations` tools (mirror `person.ts`
→ `registerCrmTools`), then on-demand enrichment + a dashboard skill. See `../START-HERE.md` §5.
