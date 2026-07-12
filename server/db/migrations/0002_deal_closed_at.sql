-- 0002_deal_closed_at.sql — add deal.closed_at so "recently won" can be scoped by a real date.
-- Apply in Supabase (SQL Editor → paste → Run) BEFORE deploying the get_pipeline_summary tool.
-- Safe + additive: one nullable column + a best-effort backfill of existing closed deals.

alter table deal add column if not exists closed_at timestamptz;

-- Backfill: closed deals get their last-updated time as an approximate close date.
-- (updated_at is imprecise, but it's the best signal we have for pre-existing rows; new
--  closes are stamped precisely by the core when status flips to won/lost.)
update deal
   set closed_at = updated_at
 where status in ('won', 'lost')
   and closed_at is null;

create index if not exists deal_closed_at_idx on deal (workspace_id, closed_at desc);
