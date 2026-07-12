// core/organization.ts — organization CRUD. Part of the headless core: no MCP/HTTP awareness.
// Every function is scoped by workspace_id (our tenant boundary until RLS policies land).
//
// Mirrors person.ts. The read-before-write helper here is `findOrganizationsByDomain`
// (domain is to orgs what email is to people): the dedup seed for the self-maintenance loop —
// "does a company with this domain already exist?"

import { getDb, orThrow } from "./db.js";
import type { Attributes, Organization, UUID } from "./types.js";

export interface CreateOrganizationInput {
  name?: string;
  primary_domain?: string;
  domains?: string[];
  last_interaction_at?: string; // ISO timestamp — refreshed by the enrichment loop
  owner_id?: UUID;
  attributes?: Attributes;
}

export type UpdateOrganizationInput = Partial<CreateOrganizationInput>;

/** Normalise domains: lowercase, strip protocol/leading www, de-dupe, ensure primary is included. */
function normaliseDomain(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/^www\./, "")
    .replace(/\/.*$/, ""); // drop any path
}

function normaliseDomains(input: CreateOrganizationInput): { primary_domain?: string; domains: string[] } {
  const set = new Set<string>();
  for (const d of input.domains ?? []) if (d) set.add(normaliseDomain(d));
  const primary = input.primary_domain ? normaliseDomain(input.primary_domain) : undefined;
  if (primary) set.add(primary);
  return { primary_domain: primary, domains: [...set] };
}

export async function createOrganization(
  workspaceId: UUID,
  input: CreateOrganizationInput,
): Promise<Organization> {
  const { primary_domain, domains } = normaliseDomains(input);
  return orThrow(
    await getDb()
      .from("organization")
      .insert({
        workspace_id: workspaceId,
        name: input.name ?? null,
        primary_domain: primary_domain ?? null,
        domains,
        last_interaction_at: input.last_interaction_at ?? null,
        owner_id: input.owner_id ?? null,
        attributes: input.attributes ?? {},
      })
      .select()
      .single(),
  );
}

/** Batch create: ONE insert for many organizations (same normalisation as createOrganization).
 *  Used by bulk import to stay within the Worker's per-invocation subrequest budget. Returns rows
 *  in input order; empty in → no DB call. */
export async function createOrganizations(
  workspaceId: UUID,
  inputs: CreateOrganizationInput[],
): Promise<Organization[]> {
  if (inputs.length === 0) return [];
  const rows = inputs.map((input) => {
    const { primary_domain, domains } = normaliseDomains(input);
    return {
      workspace_id: workspaceId,
      name: input.name ?? null,
      primary_domain: primary_domain ?? null,
      domains,
      last_interaction_at: input.last_interaction_at ?? null,
      owner_id: input.owner_id ?? null,
      attributes: input.attributes ?? {},
    };
  });
  return orThrow(await getDb().from("organization").insert(rows).select());
}

export async function getOrganization(workspaceId: UUID, id: UUID): Promise<Organization | null> {
  const { data, error } = await getDb()
    .from("organization")
    .select()
    .eq("workspace_id", workspaceId)
    .eq("id", id)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data;
}

/** List orgs in a workspace, most-recently-interacted first. Excludes archived. */
export async function findOrganizations(
  workspaceId: UUID,
  opts: { limit?: number } = {},
): Promise<Organization[]> {
  return orThrow(
    await getDb()
      .from("organization")
      .select()
      .eq("workspace_id", workspaceId)
      .is("archived_at", null)
      .order("last_interaction_at", { ascending: false, nullsFirst: false })
      .limit(opts.limit ?? 50),
  );
}

/** Read-before-write dedup seed: find any org whose known domains overlap the given ones. */
export async function findOrganizationsByDomain(
  workspaceId: UUID,
  domains: string[],
): Promise<Organization[]> {
  const needles = domains.map(normaliseDomain).filter(Boolean);
  if (needles.length === 0) return [];
  return orThrow(
    await getDb()
      .from("organization")
      .select()
      .eq("workspace_id", workspaceId)
      .overlaps("domains", needles),
  );
}

export async function updateOrganization(
  workspaceId: UUID,
  id: UUID,
  input: UpdateOrganizationInput,
): Promise<Organization> {
  const patch: Record<string, unknown> = {};
  if (input.name !== undefined) patch.name = input.name;
  if (input.last_interaction_at !== undefined) patch.last_interaction_at = input.last_interaction_at;
  if (input.owner_id !== undefined) patch.owner_id = input.owner_id;
  if (input.attributes !== undefined) patch.attributes = input.attributes;
  if (input.domains !== undefined || input.primary_domain !== undefined) {
    const { primary_domain, domains } = normaliseDomains(input);
    patch.primary_domain = primary_domain ?? null;
    patch.domains = domains;
  }

  return orThrow(
    await getDb()
      .from("organization")
      .update(patch)
      .eq("workspace_id", workspaceId)
      .eq("id", id)
      .select()
      .single(),
  );
}
