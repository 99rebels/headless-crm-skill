// mcp/build.ts — the MCP adapter. THIN: every tool just calls the core and formats the
// result. No business logic lives here (that's core/). Scoped to one workspace for now.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import type { UUID } from "../core/types.js";
import {
  createPerson,
  findPeople,
  findPeopleByEmail,
  getPerson,
  updatePerson,
} from "../core/person.js";
import {
  createOrganization,
  findOrganizations,
  findOrganizationsByDomain,
  getOrganization,
  updateOrganization,
} from "../core/organization.js";
import { createDeal, findDeals, getDeal, updateDeal } from "../core/deal.js";
import { findAssociationsFor, link, unlink } from "../core/association.js";
import { getPipelineSummary } from "../core/summary.js";
import { bulkImport } from "../core/bulk.js";
import {
  createTimelineEntry,
  findTimelineEntries,
  getTimelineEntry,
  updateTimelineEntry,
  type TimelineLinkInput,
} from "../core/note.js";

/** The record kinds that can participate in the association graph. */
const ENTITY_TYPES = ["person", "organization", "deal", "interaction", "task"] as const;

const text = (obj: unknown) => ({
  content: [
    {
      type: "text" as const,
      text: typeof obj === "string" ? obj : JSON.stringify(obj, null, 2),
    },
  ],
});
const errorText = (msg: string) => ({ ...text(msg), isError: true as const });

/** A workspace id, or a (possibly async) resolver for it. The stdio adapter passes a concrete
 *  id; the Worker passes a resolver so the workspace DB lookup happens lazily on first tool use,
 *  not at connection time — a DB hiccup during the handshake then can't break the MCP connection. */
export type WorkspaceRef = UUID | (() => UUID | Promise<UUID>);

/** Register the CRM tools onto any McpServer, scoped to one workspace. Shared by the
 *  stdio adapter (buildServer, below) and the Cloudflare Worker adapter. */
export function registerCrmTools(server: McpServer, workspace: WorkspaceRef): void {
  // Normalise to a memoised resolver: resolve the workspace at most once per session, then
  // reuse. With a concrete id this is a no-op; with a resolver it defers the DB call to the
  // first tool that actually runs (lazy init — keeps a DB blip from failing the connection).
  let cached: UUID | undefined;
  const getWorkspaceId = async (): Promise<UUID> => {
    if (cached === undefined) {
      cached = typeof workspace === "function" ? await workspace() : workspace;
    }
    return cached;
  };

  // ── contacts (people) ────────────────────────────────────────────────────────────
  server.registerTool(
    "create_contact",
    {
      title: "Create contact",
      description:
        "Create a new contact (person). Checks for an existing contact with the same email FIRST (read-before-write) and returns that instead of creating a duplicate.",
      inputSchema: {
        name: z.string().optional(),
        email: z.string().optional().describe("primary email"),
        emails: z.array(z.string()).optional().describe("additional known emails/aliases"),
        phone: z.string().optional(),
        title: z.string().optional(),
        lifecycle_stage: z.string().optional().describe("lead | prospect | client | past"),
        attributes: z
          .record(z.string(), z.unknown())
          .optional()
          .describe("flexible extra facts, e.g. { preferred_name: 'Kate' }"),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const allEmails = [...(args.emails ?? []), ...(args.email ? [args.email] : [])];
        if (allEmails.length) {
          const existing = await findPeopleByEmail(workspaceId, allEmails);
          if (existing.length) {
            return text({
              status: "already_exists",
              message:
                "A contact with this email already exists — returning it instead of creating a duplicate.",
              contact: existing[0],
            });
          }
        }
        const person = await createPerson(workspaceId, {
          name: args.name,
          primary_email: args.email,
          emails: args.emails,
          phone: args.phone,
          title: args.title,
          lifecycle_stage: args.lifecycle_stage,
          attributes: args.attributes,
        });
        return text({ status: "created", contact: person });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "find_contacts",
    {
      title: "Find contacts",
      description: "List recent contacts, or look up contacts by email (any case).",
      inputSchema: {
        email: z.string().optional().describe("if given, find contacts whose known emails match"),
        limit: z.number().int().positive().optional(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const results = args.email
          ? await findPeopleByEmail(workspaceId, [args.email])
          : await findPeople(workspaceId, { limit: args.limit });
        return text({ count: results.length, contacts: results });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "get_contact",
    {
      title: "Get contact",
      description: "Fetch a single contact by id.",
      inputSchema: { id: z.string().describe("contact id") },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const person = await getPerson(workspaceId, args.id);
        return person ? text(person) : errorText("No contact with that id.");
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "update_contact",
    {
      title: "Update contact",
      description: "Update fields on an existing contact.",
      inputSchema: {
        id: z.string(),
        name: z.string().optional(),
        email: z.string().optional(),
        emails: z.array(z.string()).optional(),
        phone: z.string().optional(),
        title: z.string().optional(),
        lifecycle_stage: z.string().optional(),
        last_interaction_at: z
          .string()
          .optional()
          .describe("ISO timestamp of the most recent contact — refresh this after an email/meeting"),
        summary: z
          .string()
          .optional()
          .describe("the living relationship summary — current state, open items, sentiment"),
        summary_provenance: z
          .record(z.string(), z.unknown())
          .optional()
          .describe("which timeline entry ids / comms this summary was built from"),
        attributes: z.record(z.string(), z.unknown()).optional(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const { id, email, ...rest } = args;
        const person = await updatePerson(workspaceId, id, { ...rest, primary_email: email });
        return text({ status: "updated", contact: person });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  // ── organizations ───────────────────────────────────────────────────────────────
  server.registerTool(
    "create_organization",
    {
      title: "Create organization",
      description:
        "Create a new organization (company). Checks for an existing org with the same domain FIRST (read-before-write) and returns that instead of creating a duplicate.",
      inputSchema: {
        name: z.string().optional(),
        domain: z.string().optional().describe("primary domain, e.g. acme.com"),
        domains: z.array(z.string()).optional().describe("additional known domains"),
        description: z
          .string()
          .optional()
          .describe("who they are / what they do — the stable identity line"),
        attributes: z
          .record(z.string(), z.unknown())
          .optional()
          .describe("flexible extra facts, e.g. { industry: 'fintech', size: '50-100' }"),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const allDomains = [...(args.domains ?? []), ...(args.domain ? [args.domain] : [])];
        if (allDomains.length) {
          const existing = await findOrganizationsByDomain(workspaceId, allDomains);
          if (existing.length) {
            return text({
              status: "already_exists",
              message:
                "An organization with this domain already exists — returning it instead of creating a duplicate.",
              organization: existing[0],
            });
          }
        }
        const org = await createOrganization(workspaceId, {
          name: args.name,
          primary_domain: args.domain,
          domains: args.domains,
          description: args.description,
          attributes: args.attributes,
        });
        return text({ status: "created", organization: org });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "find_organizations",
    {
      title: "Find organizations",
      description: "List recent organizations, or look up organizations by domain (any case).",
      inputSchema: {
        domain: z.string().optional().describe("if given, find orgs whose known domains match"),
        limit: z.number().int().positive().optional(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const results = args.domain
          ? await findOrganizationsByDomain(workspaceId, [args.domain])
          : await findOrganizations(workspaceId, { limit: args.limit });
        return text({ count: results.length, organizations: results });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "get_organization",
    {
      title: "Get organization",
      description: "Fetch a single organization by id.",
      inputSchema: { id: z.string().describe("organization id") },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const org = await getOrganization(workspaceId, args.id);
        return org ? text(org) : errorText("No organization with that id.");
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "update_organization",
    {
      title: "Update organization",
      description: "Update fields on an existing organization.",
      inputSchema: {
        id: z.string(),
        name: z.string().optional(),
        domain: z.string().optional(),
        domains: z.array(z.string()).optional(),
        description: z.string().optional().describe("who they are / what they do"),
        last_interaction_at: z.string().optional().describe("ISO timestamp of the most recent contact"),
        attributes: z.record(z.string(), z.unknown()).optional(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const { id, domain, ...rest } = args;
        const org = await updateOrganization(workspaceId, id, { ...rest, primary_domain: domain });
        return text({ status: "updated", organization: org });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  // ── deals (the pipeline) ─────────────────────────────────────────────────────────
  server.registerTool(
    "create_deal",
    {
      title: "Create deal",
      description:
        "Create a new deal in the pipeline. Link it to its people/organization with link_records (e.g. relationship_type 'decision_maker').",
      inputSchema: {
        name: z.string().optional(),
        stage: z.string().optional().describe("pipeline stage, e.g. 'discovery' | 'proposal'"),
        status: z.enum(["open", "won", "lost"]).optional().describe("defaults to open"),
        amount: z.number().optional(),
        currency: z.string().optional().describe("defaults to USD"),
        expected_close_date: z.string().optional().describe("ISO date, YYYY-MM-DD"),
        attributes: z.record(z.string(), z.unknown()).optional(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const deal = await createDeal(workspaceId, args);
        return text({ status: "created", deal });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "find_deals",
    {
      title: "Find deals",
      description: "List deals, optionally filtered by status (open | won | lost).",
      inputSchema: {
        status: z.enum(["open", "won", "lost"]).optional(),
        limit: z.number().int().positive().optional(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const results = await findDeals(workspaceId, args);
        return text({ count: results.length, deals: results });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "get_deal",
    {
      title: "Get deal",
      description: "Fetch a single deal by id.",
      inputSchema: { id: z.string().describe("deal id") },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const deal = await getDeal(workspaceId, args.id);
        return deal ? text(deal) : errorText("No deal with that id.");
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "update_deal",
    {
      title: "Update deal",
      description: "Update fields on an existing deal (e.g. advance the stage, mark won/lost).",
      inputSchema: {
        id: z.string(),
        name: z.string().optional(),
        stage: z.string().optional(),
        status: z.enum(["open", "won", "lost"]).optional(),
        amount: z.number().optional(),
        currency: z.string().optional(),
        expected_close_date: z.string().optional(),
        summary: z
          .string()
          .optional()
          .describe("the living deal summary — where it stands, next steps, blockers, key dates"),
        summary_provenance: z
          .record(z.string(), z.unknown())
          .optional()
          .describe("which timeline entry ids / comms this summary was built from"),
        attributes: z.record(z.string(), z.unknown()).optional(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const { id, ...rest } = args;
        const deal = await updateDeal(workspaceId, id, rest);
        return text({ status: "updated", deal });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  // ── dashboard summary (deterministic aggregation for the pipeline view) ────────────
  server.registerTool(
    "get_pipeline_summary",
    {
      title: "Get pipeline summary",
      description:
        "Compute the whole pipeline dashboard in one call: open pipeline value, open/unstaged deal counts, relationship count, deals bucketed by stage (with an 'Unstaged' bucket for stage-less deals), the people roster with real last-contact recency, recently-won deals, and attention 'signals'. All facts, labels, and joins are computed server-side so every render is identical — the caller only adds the human 'Focus' list from the signals. Prefer this over stitching together find_deals/find_contacts/find_associations for the dashboard.",
      inputSchema: {},
    },
    async () => {
      try {
        const workspaceId = await getWorkspaceId();
        return text(await getPipelineSummary(workspaceId));
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  // ── bulk import (create + dedupe + link a whole plan in ONE call) ──────────────────
  const bulkAttrs = z.record(z.string(), z.unknown()).optional();
  server.registerTool(
    "bulk_import",
    {
      title: "Bulk import",
      description:
        "Create and link many records in ONE call — the write step for the CSV-import / migration skill. Takes a `plan` of contacts, organizations, deals, links, and optional timeline_entries (each record has a local `key` like 'c0'/'o0'/'d0'; links and timeline-entry links reference those keys). Creates in the right order (orgs → contacts → deals → links → timeline), dedupes orgs by domain and contacts by email (reusing matches, never duplicating), folds notes into the timeline (idempotent on source+external_id), and resolves the keys to real ids server-side. Writes are set-based (a few DB ops total, not one per record), so pass the WHOLE plan in a single call — do NOT pre-split it into batches, and do NOT loop create_/link_ per record (that hits the per-turn tool limit). Returns created/reused/skipped counts and any per-record errors.",
      inputSchema: {
        plan: z.object({
          contacts: z
            .array(
              z.object({
                key: z.string().describe("stable local id, e.g. 'c0'"),
                name: z.string().optional(),
                email: z.string().optional(),
                emails: z.array(z.string()).optional(),
                phone: z.string().optional(),
                title: z.string().optional(),
                lifecycle_stage: z.string().optional(),
                last_interaction_at: z
                  .string()
                  .optional()
                  .describe("ISO — carry-in recency from a migrated source's 'last contacted'"),
                attributes: bulkAttrs,
              }),
            )
            .optional(),
          organizations: z
            .array(
              z.object({
                key: z.string().describe("stable local id, e.g. 'o0'"),
                name: z.string().optional(),
                domain: z.string().optional(),
                domains: z.array(z.string()).optional(),
                description: z.string().optional(),
                last_interaction_at: z.string().optional().describe("ISO — carry-in recency"),
                attributes: bulkAttrs,
              }),
            )
            .optional(),
          deals: z
            .array(
              z.object({
                key: z.string().describe("stable local id, e.g. 'd0'"),
                name: z.string().optional(),
                stage: z.string().optional(),
                status: z.enum(["open", "won", "lost"]).optional(),
                amount: z.number().optional(),
                currency: z.string().optional(),
                expected_close_date: z.string().optional(),
                attributes: bulkAttrs,
              }),
            )
            .optional(),
          links: z
            .array(
              z.object({
                from: z.string().describe("local key of the from-record"),
                to: z.string().describe("local key of the to-record"),
                relationship_type: z.string().describe("e.g. works_at | primary_contact | account"),
              }),
            )
            .optional(),
          timeline_entries: z
            .array(
              z.object({
                type: z.enum(["email", "meeting", "call", "note", "stage_change", "relationship_change"]),
                occurred_at: z.string().optional().describe("ISO — e.g. the note's created date"),
                subject: z.string().optional(),
                summary: z.string().optional(),
                body: z.string().optional().describe("full text (migration notes are user-authored)"),
                source: z.string().optional().describe("e.g. migration | granola"),
                external_id: z.string().optional().describe("source's id — makes re-runs idempotent"),
                links: z
                  .array(
                    z.object({
                      key: z.string().describe("local key of the record this entry concerns, e.g. 'c0'"),
                      role: z.string().optional(),
                    }),
                  )
                  .optional(),
              }),
            )
            .optional()
            .describe("notes/touchpoints to fold into the timeline (e.g. a migration's notes)"),
        }),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const result = await bulkImport(workspaceId, args.plan);
        return text({ status: "imported", ...result });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  // ── timeline (the notes / context layer) ──────────────────────────────────────────
  // One unified entry (note | touchpoint | system event) linking to any number of people/deals/orgs.
  const TIMELINE_TYPES = ["email", "meeting", "call", "note", "stage_change", "relationship_change"] as const;
  const linkIdArrays = {
    person_ids: z.array(z.string()).optional().describe("contact ids this entry concerns"),
    deal_ids: z.array(z.string()).optional().describe("deal ids this entry concerns"),
    organization_ids: z.array(z.string()).optional().describe("organization ids this entry concerns"),
  };
  const toLinks = (a: {
    person_ids?: string[];
    deal_ids?: string[];
    organization_ids?: string[];
  }): TimelineLinkInput[] => [
    ...(a.person_ids ?? []).map((id) => ({ record_type: "person" as const, record_id: id })),
    ...(a.deal_ids ?? []).map((id) => ({ record_type: "deal" as const, record_id: id })),
    ...(a.organization_ids ?? []).map((id) => ({ record_type: "organization" as const, record_id: id })),
  ];

  server.registerTool(
    "create_timeline_entry",
    {
      title: "Create timeline entry",
      description:
        "Log a timeline entry — a note, a touchpoint (email/meeting/call), or a system change-event (stage_change/relationship_change) — and link it to any number of people, deals, and organizations at once (a real meeting: several attendees across several deals). Contact-type entries (email/meeting/call) drive each linked record's last-contact recency automatically. Pass an external_id + source to make re-runs idempotent (an existing entry with that key is returned, not duplicated).",
      inputSchema: {
        type: z.enum(TIMELINE_TYPES),
        occurred_at: z.string().optional().describe("ISO timestamp — defaults to now"),
        direction: z.enum(["inbound", "outbound", "internal"]).optional(),
        subject: z.string().optional(),
        summary: z.string().optional().describe("what happened — always safe to store"),
        body: z.string().optional().describe("full text for user-authored notes only (not ingested comms)"),
        source: z.string().optional().describe("mechanism: manual | enrichment | migration | granola"),
        external_id: z.string().optional().describe("source's id — dedup/idempotency key"),
        ...linkIdArrays,
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const { person_ids, deal_ids, organization_ids, ...entry } = args;
        const { entry: created, deduped } = await createTimelineEntry(workspaceId, {
          ...entry,
          links: toLinks({ person_ids, deal_ids, organization_ids }),
        });
        return text({ status: deduped ? "already_exists" : "created", entry: created });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "find_timeline_entries",
    {
      title: "Find timeline entries",
      description:
        "Read a record's timeline (newest first) by passing record_type + record_id, or the whole workspace's recent timeline with neither. Each entry includes its record links.",
      inputSchema: {
        record_type: z.enum(["person", "organization", "deal"]).optional(),
        record_id: z.string().optional(),
        limit: z.number().int().positive().optional(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const entries = await findTimelineEntries(workspaceId, args);
        return text({ count: entries.length, entries });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "update_timeline_entry",
    {
      title: "Update timeline entry",
      description:
        "Edit an existing timeline entry (e.g. correct a summary or occurred_at). If any of person_ids/deal_ids/organization_ids is provided, the entry's links are REPLACED with exactly those (pass empty arrays to clear); omit all three to leave links unchanged.",
      inputSchema: {
        id: z.string(),
        type: z.enum(TIMELINE_TYPES).optional(),
        occurred_at: z.string().optional(),
        direction: z.enum(["inbound", "outbound", "internal"]).optional(),
        subject: z.string().optional(),
        summary: z.string().optional(),
        body: z.string().optional(),
        ...linkIdArrays,
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const { id, person_ids, deal_ids, organization_ids, ...rest } = args;
        const relinking =
          person_ids !== undefined || deal_ids !== undefined || organization_ids !== undefined;
        const existing = await getTimelineEntry(workspaceId, id);
        if (!existing) return errorText("No timeline entry with that id.");
        const entry = await updateTimelineEntry(workspaceId, id, {
          ...rest,
          ...(relinking ? { links: toLinks({ person_ids, deal_ids, organization_ids }) } : {}),
        });
        return text({ status: "updated", entry });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  // ── associations (the relationship graph) ─────────────────────────────────────────
  server.registerTool(
    "link_records",
    {
      title: "Link records",
      description:
        "Create a relationship between two records (person/organization/deal/interaction/task), e.g. a person works_at an organization, or is a decision_maker on a deal. Idempotent — re-linking the same pair won't duplicate.",
      inputSchema: {
        from_type: z.enum(ENTITY_TYPES),
        from_id: z.string(),
        to_type: z.enum(ENTITY_TYPES),
        to_id: z.string(),
        relationship_type: z
          .string()
          .describe("e.g. works_at | decision_maker | champion | participated_in"),
        attributes: z
          .record(z.string(), z.unknown())
          .optional()
          .describe("optional link detail, e.g. { since: '2024', role: 'CFO' }"),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const association = await link(workspaceId, args);
        return text({ status: "linked", association });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "find_associations",
    {
      title: "Find associations",
      description:
        "Find every relationship touching a record, in either direction — used to gather everything linked to a contact, org, or deal.",
      inputSchema: {
        entity_type: z.enum(ENTITY_TYPES),
        entity_id: z.string(),
      },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        const results = await findAssociationsFor(workspaceId, args.entity_type, args.entity_id);
        return text({ count: results.length, associations: results });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  server.registerTool(
    "unlink_records",
    {
      title: "Unlink records",
      description: "Remove a relationship by its association id (e.g. to correct a wrong link).",
      inputSchema: { id: z.string().describe("association id") },
    },
    async (args) => {
      try {
        const workspaceId = await getWorkspaceId();
        await unlink(workspaceId, args.id);
        return text({ status: "unlinked", id: args.id });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );
}

export function buildServer(workspace: WorkspaceRef): McpServer {
  const server = new McpServer({ name: "crm", version: "0.1.0" });
  registerCrmTools(server, workspace);
  return server;
}
