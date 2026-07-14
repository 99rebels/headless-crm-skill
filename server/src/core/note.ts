// core/note.ts — the notes / context layer's timeline. Part of the headless core: no MCP/HTTP
// awareness. Every function is scoped by workspace_id (our tenant boundary until RLS policies land).
//
// The "timeline" is the `interaction` table (a unified entry: note | touchpoint | system event),
// plus `interaction_link` — a many-to-many join so ONE entry links to any number of people/deals/
// orgs (a real meeting: several attendees across several deals). See docs/notes-design.md.
//
// Two responsibilities live here:
//   • timeline CRUD (create/read/update entries + their links), and
//   • the recency derivation the dashboard reads — `getLatestContactMap` gives, per record, the date
//     of its most recent CONTACT-type entry (email/meeting/call). core/summary.ts combines that with
//     the stored last_interaction_at (the imported-recency carry-in) via max().

import { getDb, orThrow } from "./db.js";
import type {
  Interaction,
  InteractionDirection,
  InteractionLink,
  InteractionType,
  TimelineEntry,
  TimelineRecordType,
  UUID,
} from "./types.js";

/** Entry kinds that count as "we actually made contact" → they drive recency. A personal note or a
 *  system change-event (stage/relationship) is NOT contact, so it never bumps last-interaction. */
export const CONTACT_TYPES: InteractionType[] = ["email", "meeting", "call"];

export interface TimelineLinkInput {
  record_type: TimelineRecordType;
  record_id: UUID;
  role?: string;
}

export interface CreateTimelineEntryInput {
  type: InteractionType;
  occurred_at?: string; // ISO; omitted → DB default now()
  direction?: InteractionDirection;
  subject?: string;
  summary?: string;
  body?: string;
  source?: string; // mechanism: manual / enrichment / migration / granola
  external_id?: string; // idempotency key from the source system
  owner_id?: UUID; // author
  links?: TimelineLinkInput[];
}

export type UpdateTimelineEntryInput = Partial<
  Omit<CreateTimelineEntryInput, "links">
> & {
  /** If provided, REPLACES the entry's links wholesale (pass [] to clear). Omit to leave them as-is. */
  links?: TimelineLinkInput[];
};

/** Insert the link rows for an entry (deduped within the batch by the unique key). Empty in → no-op. */
async function insertLinks(
  workspaceId: UUID,
  interactionId: UUID,
  links: TimelineLinkInput[],
): Promise<InteractionLink[]> {
  if (links.length === 0) return [];
  const seen = new Set<string>();
  const rows: Record<string, unknown>[] = [];
  for (const l of links) {
    const key = `${l.record_type}:${l.record_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({
      workspace_id: workspaceId,
      interaction_id: interactionId,
      record_type: l.record_type,
      record_id: l.record_id,
      role: l.role ?? null,
    });
  }
  if (rows.length === 0) return [];
  return orThrow(
    await getDb()
      .from("interaction_link")
      .upsert(rows, { onConflict: "interaction_id,record_type,record_id" })
      .select(),
  );
}

async function linksFor(workspaceId: UUID, interactionIds: UUID[]): Promise<InteractionLink[]> {
  if (interactionIds.length === 0) return [];
  return orThrow(
    await getDb()
      .from("interaction_link")
      .select()
      .eq("workspace_id", workspaceId)
      .in("interaction_id", interactionIds),
  );
}

/** Create a timeline entry + its record links. If a (source, external_id) is given and an entry
 *  already exists for it, that existing entry is returned instead of creating a duplicate — this is
 *  what makes the enrichment loop safe to re-run (mirrors the read-before-write dedup on contacts). */
export async function createTimelineEntry(
  workspaceId: UUID,
  input: CreateTimelineEntryInput,
): Promise<{ entry: TimelineEntry; deduped: boolean }> {
  if (input.external_id && input.source) {
    const { data: existing, error } = await getDb()
      .from("interaction")
      .select()
      .eq("workspace_id", workspaceId)
      .eq("source", input.source)
      .eq("external_id", input.external_id)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (existing) {
      const links = await linksFor(workspaceId, [existing.id]);
      return { entry: { ...(existing as Interaction), links }, deduped: true };
    }
  }

  const row: Record<string, unknown> = {
    workspace_id: workspaceId,
    type: input.type,
    direction: input.direction ?? null,
    subject: input.subject ?? null,
    summary: input.summary ?? null,
    body: input.body ?? null,
    source: input.source ?? null,
    external_id: input.external_id ?? null,
    owner_id: input.owner_id ?? null,
  };
  if (input.occurred_at !== undefined) row.occurred_at = input.occurred_at; // else DB default now()

  const entry = orThrow(
    await getDb().from("interaction").insert(row).select().single(),
  ) as Interaction;
  const links = await insertLinks(workspaceId, entry.id, input.links ?? []);
  return { entry: { ...entry, links }, deduped: false };
}

/** Batch create timeline entries + their links in a handful of DB ops (not one round-trip per entry).
 *  Used by bulk_import to fold a migration's notes into the timeline. Entries carrying a (source,
 *  external_id) that already exists are SKIPPED (idempotent re-run) — the same read-before-write
 *  discipline as bulk contact/org dedup. Returns how many new entries were created. */
export async function createTimelineEntries(
  workspaceId: UUID,
  inputs: CreateTimelineEntryInput[],
): Promise<{ created: number; skipped: number }> {
  if (inputs.length === 0) return { created: 0, skipped: 0 };

  // 1) dedup: drop any entry whose (source, external_id) already exists in this workspace
  const keyed = inputs.filter((e) => e.external_id && e.source);
  const existing = new Set<string>();
  if (keyed.length) {
    const rows = orThrow(
      await getDb()
        .from("interaction")
        .select("source,external_id")
        .eq("workspace_id", workspaceId)
        .in("external_id", [...new Set(keyed.map((e) => e.external_id!))]),
    ) as { source: string | null; external_id: string | null }[];
    for (const r of rows) if (r.external_id) existing.add(`${r.source ?? ""}::${r.external_id}`);
  }
  const fresh = inputs.filter(
    (e) => !(e.external_id && e.source && existing.has(`${e.source}::${e.external_id}`)),
  );
  const skipped = inputs.length - fresh.length;
  if (fresh.length === 0) return { created: 0, skipped };

  // 2) one bulk insert of the entries (rows come back in input order)
  const rows = fresh.map((e) => {
    const row: Record<string, unknown> = {
      workspace_id: workspaceId,
      type: e.type,
      direction: e.direction ?? null,
      subject: e.subject ?? null,
      summary: e.summary ?? null,
      body: e.body ?? null,
      source: e.source ?? null,
      external_id: e.external_id ?? null,
      owner_id: e.owner_id ?? null,
    };
    if (e.occurred_at !== undefined) row.occurred_at = e.occurred_at;
    return row;
  });
  const inserted = orThrow(
    await getDb().from("interaction").insert(rows).select(),
  ) as Interaction[];

  // 3) one bulk insert of all their links
  const linkRows: Record<string, unknown>[] = [];
  const seen = new Set<string>();
  inserted.forEach((entry, i) => {
    for (const l of fresh[i].links ?? []) {
      const k = `${entry.id}:${l.record_type}:${l.record_id}`;
      if (seen.has(k)) continue;
      seen.add(k);
      linkRows.push({
        workspace_id: workspaceId,
        interaction_id: entry.id,
        record_type: l.record_type,
        record_id: l.record_id,
        role: l.role ?? null,
      });
    }
  });
  if (linkRows.length) {
    orThrow(
      await getDb()
        .from("interaction_link")
        .upsert(linkRows, { onConflict: "interaction_id,record_type,record_id" })
        .select("id"),
    );
  }
  return { created: inserted.length, skipped };
}

export async function getTimelineEntry(
  workspaceId: UUID,
  id: UUID,
): Promise<TimelineEntry | null> {
  const { data, error } = await getDb()
    .from("interaction")
    .select()
    .eq("workspace_id", workspaceId)
    .eq("id", id)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const links = await linksFor(workspaceId, [id]);
  return { ...(data as Interaction), links };
}

/** A record's timeline, newest first — or the whole workspace's recent timeline if no record given.
 *  The `(record_type, record_id)` index makes the per-record read a cheap lookup. */
export async function findTimelineEntries(
  workspaceId: UUID,
  opts: { record_type?: TimelineRecordType; record_id?: UUID; limit?: number } = {},
): Promise<TimelineEntry[]> {
  const limit = opts.limit ?? 50;
  let interactionIds: UUID[] | null = null;

  if (opts.record_type && opts.record_id) {
    const links = orThrow(
      await getDb()
        .from("interaction_link")
        .select("interaction_id")
        .eq("workspace_id", workspaceId)
        .eq("record_type", opts.record_type)
        .eq("record_id", opts.record_id),
    ) as { interaction_id: UUID }[];
    interactionIds = [...new Set(links.map((l) => l.interaction_id))];
    if (interactionIds.length === 0) return [];
  }

  let q = getDb().from("interaction").select().eq("workspace_id", workspaceId);
  if (interactionIds) q = q.in("id", interactionIds);
  const entries = orThrow(
    await q.order("occurred_at", { ascending: false }).limit(limit),
  ) as Interaction[];

  const links = await linksFor(workspaceId, entries.map((e) => e.id));
  const byInteraction = new Map<UUID, InteractionLink[]>();
  for (const l of links) {
    byInteraction.set(l.interaction_id, [...(byInteraction.get(l.interaction_id) ?? []), l]);
  }
  return entries.map((e) => ({ ...e, links: byInteraction.get(e.id) ?? [] }));
}

export async function updateTimelineEntry(
  workspaceId: UUID,
  id: UUID,
  input: UpdateTimelineEntryInput,
): Promise<TimelineEntry> {
  const patch: Record<string, unknown> = {};
  if (input.type !== undefined) patch.type = input.type;
  if (input.occurred_at !== undefined) patch.occurred_at = input.occurred_at;
  if (input.direction !== undefined) patch.direction = input.direction;
  if (input.subject !== undefined) patch.subject = input.subject;
  if (input.summary !== undefined) patch.summary = input.summary;
  if (input.body !== undefined) patch.body = input.body;
  if (input.source !== undefined) patch.source = input.source;
  if (input.owner_id !== undefined) patch.owner_id = input.owner_id;

  // Supabase rejects an empty update patch; only issue the UPDATE if there's something to change.
  const entry = Object.keys(patch).length
    ? (orThrow(
        await getDb()
          .from("interaction")
          .update(patch)
          .eq("workspace_id", workspaceId)
          .eq("id", id)
          .select()
          .single(),
      ) as Interaction)
    : await (async () => {
        const e = await getTimelineEntry(workspaceId, id);
        if (!e) throw new Error("No timeline entry with that id.");
        return e as Interaction;
      })();

  // Links: replace wholesale only when the caller passed an explicit array.
  if (input.links !== undefined) {
    const del = await getDb()
      .from("interaction_link")
      .delete()
      .eq("workspace_id", workspaceId)
      .eq("interaction_id", id);
    if (del.error) throw new Error(del.error.message);
    await insertLinks(workspaceId, id, input.links);
  }

  const links = await linksFor(workspaceId, [id]);
  return { ...entry, links };
}

/** Per-record recency from the timeline: record_id → ISO date of its most recent CONTACT-type entry.
 *  core/summary.ts maxes this against the stored last_interaction_at (imported-recency carry-in), so a
 *  freshly-migrated contact with no timeline still shows its carried-in date. Computed in memory (the
 *  summary path already loads whole-workspace sets) — fine at solo-operator scale. */
export async function getLatestContactMap(workspaceId: UUID): Promise<Map<UUID, string>> {
  const db = getDb();
  const [intsRes, linksRes] = await Promise.all([
    db
      .from("interaction")
      .select("id,occurred_at")
      .eq("workspace_id", workspaceId)
      .in("type", CONTACT_TYPES),
    db.from("interaction_link").select("interaction_id,record_id").eq("workspace_id", workspaceId),
  ]);
  const ints = orThrow(intsRes) as { id: UUID; occurred_at: string }[];
  const links = orThrow(linksRes) as { interaction_id: UUID; record_id: UUID }[];

  const occurredById = new Map(ints.map((i) => [i.id, i.occurred_at]));
  const latest = new Map<UUID, string>();
  for (const l of links) {
    const occurred = occurredById.get(l.interaction_id);
    if (!occurred) continue; // link points at a non-contact entry
    const cur = latest.get(l.record_id);
    if (!cur || occurred > cur) latest.set(l.record_id, occurred);
  }
  return latest;
}
