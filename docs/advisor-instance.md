# Giving the advisor his own instance ("Path A" isolation)

**Goal:** the advisor (our design partner) gets his **own isolated CRM instance** — his data never
mixes with our dev data — while our dev Worker + connector keep working untouched.

**Status:** code scaffolded with placeholders (2026-07-12). The remaining steps are **account-gated
(Rian's to run)** and need the advisor's details, which we don't have yet.

---

## The idea (why this shape)
For **one trusted design partner**, the requirement is **isolation, not authentication**. Building
real login/OAuth/multi-tenancy now would be solving a problem we don't have (we have exactly one
known user). So:

- **Same code, deployed a second time**, pinned to a different **workspace** by a single env var
  (`WORKSPACE_NAME`). The dev Worker → `"Dev Workspace"`; the advisor Worker → his workspace.
- A **tenant is a `workspace` row**, not a new table or a new database. His data is the rows tagged
  with his `workspace_id`, in the *same tables* as everyone else — which is exactly the product's
  future multi-tenant shape (one DB, RLS per workspace). **Not** a database-per-customer (that
  doesn't scale and diverges from the RLS model).
- He **never gets DB credentials** — the *Worker* holds them; he only gets the `/mcp` URL. You own
  the Supabase project(s) and the service-role key.
- Each of you is on a **different claude.ai account**, so there's no connector conflict.

### Dev vs. prod: put his real data in a PROD project (decided 2026-07-12)
His data must **not** live in the **dev** Supabase project — that's the one `npm run seed` / `smoke`
run against, so one stray reseed could pollute or erase his contacts. So:

- **dev** Supabase project (the current one) = our sandbox: Dev Workspace + test data, safe to wipe.
- **prod** Supabase project (NEW) = the first *real customer DB*: the advisor's workspace today, more
  customer workspaces later — still **one shared multi-tenant DB**, isolated per workspace.
- The advisor Worker's secrets point at **prod**; `npm run provision:prod` runs against **prod**.

**Honest caveats (fine for a design partner, NOT for real customers):**
1. The `/mcp` URL is an **unguessable capability** — there is no login. Anyone with the URL reaches
   that workspace.
2. Within the prod project, workspaces share one Postgres with **app-level scoping only** (the
   service-role key bypasses RLS). Low risk at one tenant, but real RLS + auth is the deferred
   multi-tenant workstream.

This is deliberately a **shim**, not the product tenancy model. But nothing is wasted: the prod
project *is* the future customer DB, and the per-tenant `workspace.settings` we write here is exactly
what the real product keys off later. A Worker-per-tenant doesn't scale past a handful — when
customer #2 arrives, build the real path (a `tenants`/`api_keys` table + token→workspace resolution
+ RLS), all inside that same prod project.

## What's already built
- `server/src/worker/index.ts` reads `env.WORKSPACE_NAME ?? "Dev Workspace"` — the one functional change.
- `server/wrangler.advisor.jsonc` — a second deployment config with `<<PLACEHOLDER>>`s.
- `server/src/provision-workspace.ts` — creates the workspace + seeds its vocab/settings.
  `npm run provision` targets **dev** (`.env`); `npm run provision:prod` targets **prod** (`.env.prod`).
- `core/updateWorkspaceSettings()` — writes `workspace.settings` (also the seed of the real product).

## The runbook (Rian, when you have the advisor's info)
Fill in his **workspace name** (e.g. `"Jane Advisory"`) and, ideally, **his email(s)** (so the
dashboard excludes his own record from the roster).

```bash
cd server

# 0. ONE-TIME: create the PROD Supabase project (your first real customer DB).
#    a. New project in the Supabase dashboard (e.g. "headless-crm-prod").
#    b. Run both migrations on it via the SQL editor, in order:
#         db/migrations/0001_init.sql   then   db/migrations/0002_deal_closed_at.sql
#    c. Save its API creds into server/.env.prod (see .env.example — same two keys as .env):
#         SUPABASE_URL=...          # the PROD project
#         SUPABASE_SERVICE_ROLE_KEY=...

# 1. Provision his workspace + settings IN PROD (idempotent). Pass his email(s) if you have them.
npm run provision:prod -- "Jane Advisory" jane@janeadvisory.com

# 2. Edit wrangler.advisor.jsonc — fill the three <<PLACEHOLDER>>s:
#    • name           → e.g. "headless-crm-mcp-advisor"  (becomes his URL subdomain)
#    • vars.WORKSPACE_NAME → EXACTLY "Jane Advisory"      (must match step 1)
#    • kv_namespaces id → create one and paste it:
npx wrangler kv namespace create OAUTH_KV --config wrangler.advisor.jsonc

# 3. Set the PROD Supabase secrets on THIS Worker (per-Worker; point at PROD, not dev):
npx wrangler secret put SUPABASE_URL --config wrangler.advisor.jsonc            # paste PROD url
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY --config wrangler.advisor.jsonc  # paste PROD key

# 4. Deploy his Worker:
npm run deploy:advisor      # = wrangler deploy --config wrangler.advisor.jsonc
```

Then, **on the advisor's claude.ai account** (his to click; give him the URL + zips):
5. Add a **custom connector** pointing at `https://<his-worker>.<subdomain>.workers.dev/mcp`.
6. Upload the three skill zips (Customize → Skills → Create skill → Upload):
   `crm-dashboard.zip`, `crm-enrichment.zip`, `crm-import.zip`.
7. Fill his CRM: run the **crm-import** skill on his contact export (or the enrichment loop on his
   Gmail/Calendar). Then "show me my pipeline" (crm-dashboard) should render **his** data only.

## Verifying isolation
- Our dev connector still shows the dev/demo data (Northwind, Meridian, etc.).
- His connector shows only what step 7 put in. If they ever show the same records, `WORKSPACE_NAME`
  in `wrangler.advisor.jsonc` doesn't match the `provision` name — fix and redeploy.

## Related
- `docs/roadmap.md` — the deferred real auth/multi-tenancy workstream this is a shim for.
- `docs/data-model.md` — `workspace.settings` (what `provision` writes).
- `skills/crm-import/` — the fastest way to fill his fresh workspace.
