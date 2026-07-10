// core/deal.ts — deal (pipeline) CRUD. Part of the headless core: no MCP/HTTP awareness.
// Every function is scoped by workspace_id (our tenant boundary until RLS policies land).
//
// Unlike person/organization, a deal has no natural dedup key (no email/domain), so there is
// no read-before-write helper here. A deal links to its org(s) and people via the association
// table, not fixed FKs (see core/association.ts) — keeping the relationship graph consistent.

import { getDb, orThrow } from "./db.js";
import type { Attributes, Deal, DealStatus, UUID } from "./types.js";

export interface CreateDealInput {
  name?: string;
  stage?: string;
  status?: DealStatus;
  amount?: number;
  currency?: string;
  expected_close_date?: string; // ISO date (YYYY-MM-DD)
  owner_id?: UUID;
  attributes?: Attributes;
}

export type UpdateDealInput = Partial<CreateDealInput>;

export async function createDeal(workspaceId: UUID, input: CreateDealInput): Promise<Deal> {
  return orThrow(
    await getDb()
      .from("deal")
      .insert({
        workspace_id: workspaceId,
        name: input.name ?? null,
        stage: input.stage ?? null,
        status: input.status ?? "open",
        amount: input.amount ?? null,
        currency: input.currency ?? "USD",
        expected_close_date: input.expected_close_date ?? null,
        owner_id: input.owner_id ?? null,
        attributes: input.attributes ?? {},
      })
      .select()
      .single(),
  );
}

export async function getDeal(workspaceId: UUID, id: UUID): Promise<Deal | null> {
  const { data, error } = await getDb()
    .from("deal")
    .select()
    .eq("workspace_id", workspaceId)
    .eq("id", id)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data;
}

/** List deals in a workspace, optionally filtered by status. Excludes archived.
 *  Newest-created first — the pipeline dashboard groups these by stage/status itself. */
export async function findDeals(
  workspaceId: UUID,
  opts: { status?: DealStatus; limit?: number } = {},
): Promise<Deal[]> {
  let q = getDb()
    .from("deal")
    .select()
    .eq("workspace_id", workspaceId)
    .is("archived_at", null);
  if (opts.status) q = q.eq("status", opts.status);
  return orThrow(
    await q.order("created_at", { ascending: false }).limit(opts.limit ?? 50),
  );
}

export async function updateDeal(
  workspaceId: UUID,
  id: UUID,
  input: UpdateDealInput,
): Promise<Deal> {
  const patch: Record<string, unknown> = {};
  if (input.name !== undefined) patch.name = input.name;
  if (input.stage !== undefined) patch.stage = input.stage;
  if (input.status !== undefined) patch.status = input.status;
  if (input.amount !== undefined) patch.amount = input.amount;
  if (input.currency !== undefined) patch.currency = input.currency;
  if (input.expected_close_date !== undefined) patch.expected_close_date = input.expected_close_date;
  if (input.owner_id !== undefined) patch.owner_id = input.owner_id;
  if (input.attributes !== undefined) patch.attributes = input.attributes;

  return orThrow(
    await getDb()
      .from("deal")
      .update(patch)
      .eq("workspace_id", workspaceId)
      .eq("id", id)
      .select()
      .single(),
  );
}
