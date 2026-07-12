// core/association.ts — the relationship graph. Part of the headless core: no MCP/HTTP awareness.
// Every function is scoped by workspace_id (our tenant boundary until RLS policies land).
//
// A single generic table links any record to any record (person↔org, person↔deal, deal↔org,
// interaction↔anything, …) via a `relationship_type` string. This is what lets the schema stay
// tiny while the graph stays rich: new relationship kinds are just new strings, no migration.

import { getDb, orThrow } from "./db.js";
import type { Association, Attributes, EntityType, UUID } from "./types.js";

export interface LinkInput {
  from_type: EntityType;
  from_id: UUID;
  to_type: EntityType;
  to_id: UUID;
  relationship_type: string; // works_at / decision_maker / champion / participated_in / …
  attributes?: Attributes;
}

/** Create a link between two records. Idempotent: the DB's unique index on
 *  (workspace, from, to, relationship_type) means re-linking the same pair updates the
 *  link's attributes instead of creating a duplicate. */
export async function link(workspaceId: UUID, input: LinkInput): Promise<Association> {
  return orThrow(
    await getDb()
      .from("association")
      .upsert(
        {
          workspace_id: workspaceId,
          from_type: input.from_type,
          from_id: input.from_id,
          to_type: input.to_type,
          to_id: input.to_id,
          relationship_type: input.relationship_type,
          attributes: input.attributes ?? {},
        },
        { onConflict: "workspace_id,from_type,from_id,to_type,to_id,relationship_type" },
      )
      .select()
      .single(),
  );
}

/** Batch link: ONE upsert for many associations (same idempotent onConflict as link). Used by bulk
 *  import to stay within the Worker's per-invocation subrequest budget. Dedups within the batch by
 *  the conflict key first — Postgres rejects two rows hitting the same conflict target in one
 *  statement. Returns the upserted rows; empty in → no DB call. */
export async function linkMany(workspaceId: UUID, inputs: LinkInput[]): Promise<Association[]> {
  if (inputs.length === 0) return [];
  const seen = new Set<string>();
  const rows: Record<string, unknown>[] = [];
  for (const i of inputs) {
    const key = `${i.from_type}:${i.from_id}>${i.to_type}:${i.to_id}:${i.relationship_type}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({
      workspace_id: workspaceId,
      from_type: i.from_type,
      from_id: i.from_id,
      to_type: i.to_type,
      to_id: i.to_id,
      relationship_type: i.relationship_type,
      attributes: i.attributes ?? {},
    });
  }
  return orThrow(
    await getDb()
      .from("association")
      .upsert(rows, {
        onConflict: "workspace_id,from_type,from_id,to_type,to_id,relationship_type",
      })
      .select(),
  );
}

/** Find every association touching a record, in EITHER direction (it may be the `from` or the
 *  `to` side). This is the traversal an account/deal view uses to gather "everything linked
 *  to this record." */
export async function findAssociationsFor(
  workspaceId: UUID,
  entityType: EntityType,
  entityId: UUID,
): Promise<Association[]> {
  return orThrow(
    await getDb()
      .from("association")
      .select()
      .eq("workspace_id", workspaceId)
      .or(
        `and(from_type.eq.${entityType},from_id.eq.${entityId}),` +
          `and(to_type.eq.${entityType},to_id.eq.${entityId})`,
      ),
  );
}

/** Remove a link by id. */
export async function unlink(workspaceId: UUID, id: UUID): Promise<void> {
  const { error } = await getDb()
    .from("association")
    .delete()
    .eq("workspace_id", workspaceId)
    .eq("id", id);
  if (error) throw new Error(error.message);
}
