// core/person.ts — person CRUD. Part of the headless core: no MCP/HTTP awareness.
// Every function is scoped by workspace_id (our tenant boundary until RLS policies land).
//
// Note the read-before-write helper `findPeopleByEmail` — it's the seed of the
// self-maintenance loop's dedup: "does a contact with this email already exist?"

import { getDb, orThrow } from "./db.js";
import type { Attributes, Person, UUID } from "./types.js";

export interface CreatePersonInput {
  name?: string;
  primary_email?: string;
  emails?: string[];
  phone?: string;
  title?: string;
  lifecycle_stage?: string;
  last_interaction_at?: string; // ISO timestamp — the enrichment loop refreshes this after a comm
  owner_id?: UUID;
  attributes?: Attributes;
}

export type UpdatePersonInput = Partial<CreatePersonInput>;

/** Normalise emails: lowercase, de-dupe, and ensure primary_email is included in emails[]. */
function normaliseEmails(input: CreatePersonInput): { primary_email?: string; emails: string[] } {
  const set = new Set<string>();
  for (const e of input.emails ?? []) if (e) set.add(e.trim().toLowerCase());
  const primary = input.primary_email?.trim().toLowerCase();
  if (primary) set.add(primary);
  return { primary_email: primary, emails: [...set] };
}

export async function createPerson(
  workspaceId: UUID,
  input: CreatePersonInput,
): Promise<Person> {
  const { primary_email, emails } = normaliseEmails(input);
  return orThrow(
    await getDb()
      .from("person")
      .insert({
        workspace_id: workspaceId,
        name: input.name ?? null,
        primary_email: primary_email ?? null,
        emails,
        phone: input.phone ?? null,
        title: input.title ?? null,
        lifecycle_stage: input.lifecycle_stage ?? null,
        last_interaction_at: input.last_interaction_at ?? null,
        owner_id: input.owner_id ?? null,
        attributes: input.attributes ?? {},
      })
      .select()
      .single(),
  );
}

export async function getPerson(workspaceId: UUID, id: UUID): Promise<Person | null> {
  const { data, error } = await getDb()
    .from("person")
    .select()
    .eq("workspace_id", workspaceId)
    .eq("id", id)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data;
}

/** List people in a workspace, most-recently-interacted first. Excludes archived. */
export async function findPeople(
  workspaceId: UUID,
  opts: { limit?: number } = {},
): Promise<Person[]> {
  return orThrow(
    await getDb()
      .from("person")
      .select()
      .eq("workspace_id", workspaceId)
      .is("archived_at", null)
      .order("last_interaction_at", { ascending: false, nullsFirst: false })
      .limit(opts.limit ?? 50),
  );
}

/** Read-before-write dedup seed: find anyone whose known emails overlap the given ones. */
export async function findPeopleByEmail(
  workspaceId: UUID,
  emails: string[],
): Promise<Person[]> {
  const needles = emails.map((e) => e.trim().toLowerCase()).filter(Boolean);
  if (needles.length === 0) return [];
  return orThrow(
    await getDb()
      .from("person")
      .select()
      .eq("workspace_id", workspaceId)
      .overlaps("emails", needles),
  );
}

export async function updatePerson(
  workspaceId: UUID,
  id: UUID,
  input: UpdatePersonInput,
): Promise<Person> {
  const patch: Record<string, unknown> = {};
  if (input.name !== undefined) patch.name = input.name;
  if (input.phone !== undefined) patch.phone = input.phone;
  if (input.title !== undefined) patch.title = input.title;
  if (input.lifecycle_stage !== undefined) patch.lifecycle_stage = input.lifecycle_stage;
  if (input.last_interaction_at !== undefined) patch.last_interaction_at = input.last_interaction_at;
  if (input.owner_id !== undefined) patch.owner_id = input.owner_id;
  if (input.attributes !== undefined) patch.attributes = input.attributes;
  if (input.emails !== undefined || input.primary_email !== undefined) {
    const { primary_email, emails } = normaliseEmails(input);
    patch.primary_email = primary_email ?? null;
    patch.emails = emails;
  }

  return orThrow(
    await getDb()
      .from("person")
      .update(patch)
      .eq("workspace_id", workspaceId)
      .eq("id", id)
      .select()
      .single(),
  );
}
