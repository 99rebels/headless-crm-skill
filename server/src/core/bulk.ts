// core/bulk.ts — one-shot bulk import: create + dedupe + link a whole plan in a single call.
// Exists so the CSV-import skill doesn't have to make one MCP tool call per record (which blows
// the model's per-turn tool limit). The plan mirrors build_import.py's output: each record carries
// a stable local `key` (c0/o0/d0…) and links reference those keys, so the graph resolves
// server-side before any real ids exist.
//
// SET-BASED on purpose. Each object type takes at most ONE dedup fetch + ONE bulk insert, and all
// links are one upsert — so the whole import is ~6 Cloudflare subrequests regardless of size. (A
// per-record loop was ~2 subrequests each and hit the Worker's 50-subrequest free-tier cap at ~24
// records.) Order is fixed (orgs → contacts → deals → links) so link targets exist when links run.
// Dedupe matches the single-record create tools: orgs by domain, contacts by email — a match is
// REUSED (its id feeds the key map), never duplicated. Deals have no natural key, so always create.
//
// Note on scale: the dedup fetch passes all emails/domains in one `overlaps` query. For very large
// imports (thousands) that array could get unwieldy; chunking the fetch is a future add, not needed
// at solo-operator sizes.

import { createPeople, findPeopleByEmail } from "./person.js";
import { createOrganizations, findOrganizationsByDomain } from "./organization.js";
import { createDeals } from "./deal.js";
import { linkMany, type LinkInput } from "./association.js";
import { createTimelineEntries, type CreateTimelineEntryInput } from "./note.js";
import type { Attributes, DealStatus, EntityType, InteractionType, TimelineRecordType, UUID } from "./types.js";

export interface BulkContact {
  key: string;
  name?: string; email?: string; emails?: string[]; phone?: string; title?: string;
  lifecycle_stage?: string; last_interaction_at?: string; attributes?: Attributes;
}
export interface BulkOrganization {
  key: string; name?: string; domain?: string; domains?: string[];
  description?: string; last_interaction_at?: string; attributes?: Attributes;
}
export interface BulkDeal {
  key: string; name?: string; stage?: string; status?: DealStatus; amount?: number;
  currency?: string; expected_close_date?: string; attributes?: Attributes;
}
export interface BulkLink { from: string; to: string; relationship_type: string; }
/** A timeline entry in a plan — its links reference LOCAL record keys (c0 / o0 / d0), resolved here. */
export interface BulkTimelineEntry {
  type: InteractionType;
  occurred_at?: string; subject?: string; summary?: string; body?: string;
  source?: string; external_id?: string;
  links?: { key: string; role?: string }[];
}

export interface BulkImportPlan {
  contacts?: BulkContact[];
  organizations?: BulkOrganization[];
  deals?: BulkDeal[];
  links?: BulkLink[];
  timeline_entries?: BulkTimelineEntry[];
}

// Local-key prefix → entity type (build_import.py emits c*/o*/d*).
const KEY_TYPE: Record<string, EntityType> = { c: "person", o: "organization", d: "deal" };
// same prefix → the timeline's record-type subset (person/organization/deal)
const KEY_RECORD_TYPE: Record<string, TimelineRecordType> = {
  c: "person", o: "organization", d: "deal",
};

export interface BulkImportResult {
  created: { contacts: number; organizations: number; deals: number; links: number; timeline_entries: number };
  reused: { contacts: number; organizations: number };
  skipped: { timeline_entries: number };
  errors: string[];
}

const lower = (s: string) => s.trim().toLowerCase();

export async function bulkImport(workspaceId: UUID, plan: BulkImportPlan): Promise<BulkImportResult> {
  const idMap: Record<string, UUID> = {};
  const created = { contacts: 0, organizations: 0, deals: 0, links: 0, timeline_entries: 0 };
  const reused = { contacts: 0, organizations: 0 };
  const skipped = { timeline_entries: 0 };
  const errors: string[] = [];

  // 1) ORGANIZATIONS — one dedup fetch (by all domains) + one bulk insert of the new ones
  const orgs = plan.organizations ?? [];
  if (orgs.length) {
    const allDomains = orgs.flatMap((o) => [...(o.domains ?? []), ...(o.domain ? [o.domain] : [])]);
    const existing = allDomains.length ? await findOrganizationsByDomain(workspaceId, allDomains) : [];
    const domainToId = new Map<string, UUID>();
    for (const e of existing) {
      for (const d of [...(e.domains ?? []), ...(e.primary_domain ? [e.primary_domain] : [])]) {
        domainToId.set(lower(d), e.id);
      }
    }
    const toCreate: BulkOrganization[] = [];
    const toCreateKeys: string[] = [];
    for (const o of orgs) {
      const domains = [...(o.domains ?? []), ...(o.domain ? [o.domain] : [])].map(lower);
      const hitId = domains.map((d) => domainToId.get(d)).find(Boolean);
      if (hitId) {
        idMap[o.key] = hitId;
        reused.organizations++;
      } else {
        toCreateKeys.push(o.key);
        toCreate.push(o);
      }
    }
    const createdOrgs = await createOrganizations(
      workspaceId,
      toCreate.map((o) => ({
        name: o.name, primary_domain: o.domain, domains: o.domains,
        description: o.description, last_interaction_at: o.last_interaction_at, attributes: o.attributes,
      })),
    );
    createdOrgs.forEach((org, i) => (idMap[toCreateKeys[i]] = org.id));
    created.organizations = createdOrgs.length;
  }

  // 2) CONTACTS — one dedup fetch (by all emails) + one bulk insert of the new ones
  const contacts = plan.contacts ?? [];
  if (contacts.length) {
    const allEmails = contacts.flatMap((c) => [...(c.emails ?? []), ...(c.email ? [c.email] : [])]);
    const existing = allEmails.length ? await findPeopleByEmail(workspaceId, allEmails) : [];
    const emailToId = new Map<string, UUID>();
    for (const e of existing) for (const em of e.emails ?? []) emailToId.set(lower(em), e.id);

    const toCreate: BulkContact[] = [];
    const toCreateKeys: string[] = [];
    for (const c of contacts) {
      const emails = [...(c.emails ?? []), ...(c.email ? [c.email] : [])].map(lower);
      const hitId = emails.map((em) => emailToId.get(em)).find(Boolean);
      if (hitId) {
        idMap[c.key] = hitId;
        reused.contacts++;
      } else {
        toCreateKeys.push(c.key);
        toCreate.push(c);
      }
    }
    const createdPeople = await createPeople(
      workspaceId,
      toCreate.map((c) => ({
        name: c.name, primary_email: c.email, emails: c.emails, phone: c.phone,
        title: c.title, lifecycle_stage: c.lifecycle_stage,
        last_interaction_at: c.last_interaction_at, attributes: c.attributes,
      })),
    );
    createdPeople.forEach((p, i) => (idMap[toCreateKeys[i]] = p.id));
    created.contacts = createdPeople.length;
  }

  // 3) DEALS — one bulk insert (no natural dedup key)
  const deals = plan.deals ?? [];
  if (deals.length) {
    const createdDeals = await createDeals(
      workspaceId,
      deals.map((d) => ({
        name: d.name, stage: d.stage, status: d.status, amount: d.amount,
        currency: d.currency, expected_close_date: d.expected_close_date, attributes: d.attributes,
      })),
    );
    createdDeals.forEach((deal, i) => (idMap[deals[i].key] = deal.id));
    created.deals = createdDeals.length;
  }

  // 4) LINKS — resolve local keys → ids (type from key prefix), then ONE bulk upsert
  const linkInputs: LinkInput[] = [];
  for (const l of plan.links ?? []) {
    const fromId = idMap[l.from];
    const toId = idMap[l.to];
    const fromType = KEY_TYPE[l.from[0]];
    const toType = KEY_TYPE[l.to[0]];
    if (!fromId || !toId || !fromType || !toType) {
      errors.push(`link ${l.from}→${l.to}: unresolved key (record failed to create or was skipped)`);
      continue;
    }
    linkInputs.push({ from_type: fromType, from_id: fromId, to_type: toType, to_id: toId, relationship_type: l.relationship_type });
  }
  const createdLinks = await linkMany(workspaceId, linkInputs);
  created.links = createdLinks.length;

  // 5) TIMELINE ENTRIES — resolve each entry's local-key links → real ids, then ONE batch insert
  //    (folds a migration's notes into the timeline; idempotent on source+external_id).
  const entryInputs: CreateTimelineEntryInput[] = [];
  for (const e of plan.timeline_entries ?? []) {
    const links: { record_type: TimelineRecordType; record_id: UUID; role?: string }[] = [];
    for (const l of e.links ?? []) {
      const id = idMap[l.key];
      const recordType = KEY_RECORD_TYPE[l.key[0]];
      if (!id || !recordType) {
        errors.push(`timeline entry link ${l.key}: unresolved key (record failed to create or was skipped)`);
        continue;
      }
      links.push({ record_type: recordType, record_id: id, role: l.role });
    }
    entryInputs.push({
      type: e.type, occurred_at: e.occurred_at, subject: e.subject, summary: e.summary,
      body: e.body, source: e.source, external_id: e.external_id, links,
    });
  }
  const timelineResult = await createTimelineEntries(workspaceId, entryInputs);
  created.timeline_entries = timelineResult.created;
  skipped.timeline_entries = timelineResult.skipped;

  return { created, reused, skipped, errors };
}
