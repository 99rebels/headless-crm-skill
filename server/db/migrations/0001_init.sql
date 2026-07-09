-- 0001_init.sql — initial CRM schema
-- Mirrors data-model.md (Phase 0). Apply in Supabase: SQL Editor → paste → Run,
-- or via the Supabase CLI. Safe to read top-to-bottom; nothing here is destructive.
--
-- Design: typed spine columns for what we query/sort/filter + a flexible `attributes`
-- (jsonb) tail the AI fills, + a generic `association` table (the relationship graph).
-- We deliberately do NOT go full key-value (EAV) — real columns stay real columns.

-- gen_random_uuid() is built into Postgres 13+ (Supabase has it). No extension needed.

-- ── helper: auto-maintain updated_at ────────────────────────────────────────────
create or replace function set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- ── workspace (the tenant) ──────────────────────────────────────────────────────
create table workspace (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  settings    jsonb not null default '{}',   -- per-workspace config (pipeline stages, lifecycle values, display terms) — no schema change to evolve
  created_at  timestamptz not null default now()
);

-- ── person ──────────────────────────────────────────────────────────────────────
create table person (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references workspace(id) on delete cascade,
  name                text,
  primary_email       text,
  emails              text[] not null default '{}',  -- ALL known emails/aliases — load-bearing for dedup in the self-maintenance loop
  phone               text,
  title               text,
  lifecycle_stage     text,                          -- lead/prospect/client/past — values configurable in workspace.settings (replaces a legacy "Lead" object)
  last_interaction_at timestamptz,
  owner_id            uuid,                           -- FK to a future members table (auth workstream); unconstrained for now
  attributes          jsonb not null default '{}',   -- ★ AI-managed flexible facts
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  archived_at         timestamptz
);
create index person_workspace_idx      on person (workspace_id);
create index person_emails_idx         on person using gin (emails);       -- fast "does any known email match?"
create index person_last_interaction   on person (workspace_id, last_interaction_at desc);
create trigger person_set_updated_at before update on person for each row execute function set_updated_at();

-- ── organization ─────────────────────────────────────────────────────────────────
create table organization (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references workspace(id) on delete cascade,
  name                text,
  primary_domain      text,
  domains             text[] not null default '{}',  -- all known domains — for matching people→orgs and dedup
  last_interaction_at timestamptz,
  owner_id            uuid,
  attributes          jsonb not null default '{}',   -- ★
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  archived_at         timestamptz
);
create index organization_workspace_idx on organization (workspace_id);
create index organization_domains_idx    on organization using gin (domains);
create trigger organization_set_updated_at before update on organization for each row execute function set_updated_at();

-- ── deal (the pipeline) ───────────────────────────────────────────────────────────
create table deal (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references workspace(id) on delete cascade,
  name                text,
  stage               text,                          -- references a stage in workspace.settings.pipeline; app-validated (kept flexible on purpose)
  status              text not null default 'open' check (status in ('open','won','lost')),
  amount              numeric,
  currency            text not null default 'USD',
  expected_close_date date,
  owner_id            uuid,
  attributes          jsonb not null default '{}',   -- ★
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  archived_at         timestamptz
);
create index deal_workspace_idx on deal (workspace_id);
create index deal_status_idx    on deal (workspace_id, status);
create trigger deal_set_updated_at before update on deal for each row execute function set_updated_at();

-- ── interaction (the timeline backbone) ───────────────────────────────────────────
create table interaction (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspace(id) on delete cascade,
  type          text not null check (type in ('email','meeting','call','note')),
  occurred_at   timestamptz not null default now(),
  direction     text check (direction in ('inbound','outbound','internal')),
  subject       text,
  summary       text,                                -- ★ AI-generated — always stored
  body          text,                                -- full content ONLY for user-authored notes; ingested comms store summary-only (compliance: we don't hold raw comms)
  source        text,                                -- gmail / gcal / manual / …
  external_id   text,                                -- idempotency/dedup key from the source system
  owner_id      uuid,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index interaction_workspace_idx on interaction (workspace_id);
create index interaction_occurred_idx  on interaction (workspace_id, occurred_at desc);
-- re-running the self-maintenance loop must never duplicate the same source item:
create unique index interaction_source_dedup
  on interaction (workspace_id, source, external_id)
  where external_id is not null;
create trigger interaction_set_updated_at before update on interaction for each row execute function set_updated_at();

-- ── task (follow-ups) ─────────────────────────────────────────────────────────────
create table task (
  id                          uuid primary key default gen_random_uuid(),
  workspace_id                uuid not null references workspace(id) on delete cascade,
  title                       text not null,
  description                 text,
  due_at                      timestamptz,
  status                      text not null default 'open' check (status in ('open','done')),
  assignee_id                 uuid,
  created_from_interaction_id uuid references interaction(id) on delete set null,  -- provenance hook
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);
create index task_workspace_idx on task (workspace_id);
create index task_open_due_idx  on task (workspace_id, status, due_at);
create trigger task_set_updated_at before update on task for each row execute function set_updated_at();

-- ── association (the relationship graph — links any record to any record) ─────────
create table association (
  id                uuid primary key default gen_random_uuid(),
  workspace_id      uuid not null references workspace(id) on delete cascade,
  from_type         text not null,                   -- person / organization / deal / interaction / task
  from_id           uuid not null,
  to_type           text not null,
  to_id             uuid not null,
  relationship_type text not null,                   -- works_at / advises / decision_maker / champion / introduced / participated_in / …  (add freely)
  attributes        jsonb not null default '{}',     -- optional link detail (since, role notes)
  created_at        timestamptz not null default now()
);
create index association_workspace_idx on association (workspace_id);
create index association_from_idx      on association (from_type, from_id);
create index association_to_idx        on association (to_type, to_id);
create unique index association_unique
  on association (workspace_id, from_type, from_id, to_type, to_id, relationship_type);

-- ── row-level security ────────────────────────────────────────────────────────────
-- Enable RLS everywhere now (Supabase best practice). Real per-user/per-member policies
-- come with the auth workstream. Until then, the MCP server connects with the service-role
-- key (which bypasses RLS) and the CORE layer enforces workspace_id scoping on every query.
alter table workspace    enable row level security;
alter table person       enable row level security;
alter table organization enable row level security;
alter table deal         enable row level security;
alter table interaction  enable row level security;
alter table task         enable row level security;
alter table association  enable row level security;
