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
(later) guardrails live there, so every interface shares one implementation. Adding a REST
API or web UI later is a thin adapter, not a rewrite. This is why we build the core first
and put MCP over it — without prematurely building a full public API.

## Layout

```
db/migrations/      SQL migrations (apply in Supabase)
src/
  core/             the headless CRM: types + logic. No MCP/HTTP awareness.
    types.ts        the domain contract (mirrors the schema)
  mcp/              the MCP adapter (thin — calls core). server.ts = entry point
```

## Setup

1. Create a Supabase project (done by Rian).
2. Apply `db/migrations/0001_init.sql` — Supabase dashboard → SQL Editor → paste → Run.
3. Copy `.env.example` → `.env` and fill in the values from Supabase (see below).
4. `npm install`, then `npm run dev`.

## Environment (never commit real values)

| var | where to find it in Supabase | notes |
|-----|------------------------------|-------|
| `SUPABASE_URL` | Project Settings → API → Project URL | |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → service_role key | **secret** — server-only, bypasses RLS. Never ship to a client. |

Until the auth workstream lands, the server uses the service-role key and the **core layer
enforces `workspace_id` scoping on every query** (RLS policies come later).

## Status

Phase 1 (walking skeleton) in progress: schema ✔. Next: core CRUD for one object →
one MCP tool → operate it in Claude, pointed at the live Supabase.
