// core/workspace.ts — minimal workspace ops.
// Full workspace/member management belongs to the auth workstream; for now this is
// just enough to bootstrap a tenant so the rest of the core has something to scope to.

import { getDb, orThrow } from "./db.js";
import type { UUID, Workspace } from "./types.js";

export async function createWorkspace(name: string): Promise<Workspace> {
  return orThrow(
    await getDb().from("workspace").insert({ name }).select().single(),
  );
}

export async function getWorkspace(id: UUID): Promise<Workspace | null> {
  const { data, error } = await getDb().from("workspace").select().eq("id", id).maybeSingle();
  if (error) throw new Error(error.message);
  return data;
}

/** Dev/skeleton convenience: reuse a workspace by name, or create it. Real multi-tenant
 *  workspace resolution comes with the auth workstream. */
export async function getOrCreateWorkspaceByName(name: string): Promise<Workspace> {
  const { data, error } = await getDb()
    .from("workspace")
    .select()
    .eq("name", name)
    .limit(1)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data ?? (await createWorkspace(name));
}
