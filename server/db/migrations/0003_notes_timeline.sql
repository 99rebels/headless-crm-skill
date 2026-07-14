-- 0003_notes_timeline.sql — the notes / context layer (design: docs/notes-design.md).
-- Apply in Supabase: SQL Editor → paste → Run. Additive + nullable throughout, so existing rows
-- and the deployed Worker keep working untouched until the new code paths are wired in.
--
-- What this adds (all reusing what exists — see notes-design.md §6/§9b):
--   1. `interaction` becomes the unified TIMELINE entry — widen its `type` to carry system events.
--   2. `interaction_link` — a many-to-many join so ONE entry links to any number of people/deals/orgs
--      (a real meeting: 3 attendees + 2 deals + 1 org). This is the flexible model decided with Rian.
--   3. `description` on organization — stable identity ("who they are / what they do").
--   4. living-summary columns on deal + person — the self-maintained current-state prose (§9b: option
--      a, a column on the record; history lives in the timeline via entry ids in summary_provenance).
-- Nothing is dropped. `last_interaction_at` stays as the imported-recency carry-in (§migration story);
-- recency is now max(latest contact-type timeline entry, that column) — derived in core/summary.ts.

-- ── 1. widen the timeline entry's type vocabulary ─────────────────────────────────
-- Adds the system change-events (§3): how the deal evolved, who joined/dropped off. The constraint
-- was created inline in 0001 with the default name interaction_type_check.
alter table interaction drop constraint if exists interaction_type_check;
alter table interaction add constraint interaction_type_check
  check (type in ('email','meeting','call','note','stage_change','relationship_change'));

-- ── 2. interaction_link — the many-to-many timeline↔record join ───────────────────
-- Polymorphic like `association` (no single FK target for record_id), but PURPOSE-BUILT for timeline
-- participation so graph-edge queries and timeline reads never have to filter each other out.
-- `role` (participant/subject/organizer/…) is a free, optional string for future richness.
create table interaction_link (
  id              uuid primary key default gen_random_uuid(),
  workspace_id    uuid not null references workspace(id) on delete cascade,
  interaction_id  uuid not null references interaction(id) on delete cascade,
  record_type     text not null check (record_type in ('person','organization','deal')),
  record_id       uuid not null,
  role            text,                                 -- participant | subject | organizer | … (optional)
  created_at      timestamptz not null default now()
);
create index interaction_link_workspace_idx   on interaction_link (workspace_id);
create index interaction_link_record_idx      on interaction_link (record_type, record_id); -- "this record's timeline" (the hot read)
create index interaction_link_interaction_idx on interaction_link (interaction_id);          -- "this entry's participants"
-- an entry links to a given record at most once (re-linking is idempotent):
create unique index interaction_link_unique
  on interaction_link (interaction_id, record_type, record_id);

-- ── 3. organization.description — the identity/context field ──────────────────────
alter table organization add column description text;

-- ── 4. living-summary columns on deal + person ───────────────────────────────────
-- summary        = the current, self-maintained state prose (the differentiator)
-- summary_updated_at = when the loop last rebuilt it
-- summary_provenance = which timeline entry ids / comms it was built from (§7 keep-it-true discipline)
alter table deal
  add column summary text,
  add column summary_updated_at timestamptz,
  add column summary_provenance jsonb not null default '{}';
alter table person
  add column summary text,
  add column summary_updated_at timestamptz,
  add column summary_provenance jsonb not null default '{}';

-- ── row-level security (same posture as every other table: on now, policies with auth) ───
alter table interaction_link enable row level security;
