// core/types.ts — the domain contract.
// This is the "headless CRM" vocabulary. It knows nothing about MCP or HTTP —
// the MCP adapter (and, later, a REST API or web UI) all speak in these types.
// Mirrors db/migrations/0001_init.sql.

export type UUID = string;

/** Flexible AI-managed facts. The typed fields above are the spine; this is the tail. */
export type Attributes = Record<string, unknown>;

export type DealStatus = "open" | "won" | "lost";
// The unified timeline entry's kind: human/comms touchpoints + system change-events (notes-design §3).
export type InteractionType =
  | "email"
  | "meeting"
  | "call"
  | "note"
  | "stage_change"
  | "relationship_change";
export type InteractionDirection = "inbound" | "outbound" | "internal";
/** The record kinds a timeline entry can link to (a subset of EntityType). */
export type TimelineRecordType = "person" | "organization" | "deal";
export type TaskStatus = "open" | "done";

/** Any record that can participate in the association graph. */
export type EntityType =
  | "person"
  | "organization"
  | "deal"
  | "interaction"
  | "task";

export interface Workspace {
  id: UUID;
  name: string;
  settings: Attributes;
  created_at: string;
}

export interface Person {
  id: UUID;
  workspace_id: UUID;
  name: string | null;
  primary_email: string | null;
  emails: string[];
  phone: string | null;
  title: string | null;
  lifecycle_stage: string | null; // values configured per-workspace
  last_interaction_at: string | null;
  summary: string | null; // living relationship summary — self-maintained by the enrichment loop
  summary_updated_at: string | null;
  summary_provenance: Attributes; // which timeline entries / comms it was built from (§7)
  owner_id: UUID | null;
  attributes: Attributes;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface Organization {
  id: UUID;
  workspace_id: UUID;
  name: string | null;
  primary_domain: string | null;
  domains: string[];
  description: string | null; // stable identity: who they are / what they do
  last_interaction_at: string | null;
  owner_id: UUID | null;
  attributes: Attributes;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface Deal {
  id: UUID;
  workspace_id: UUID;
  name: string | null;
  stage: string | null; // validated against workspace.settings.pipeline in the core layer
  status: DealStatus;
  amount: number | null;
  currency: string;
  expected_close_date: string | null;
  closed_at: string | null; // stamped when status flips to won/lost (source of truth for "recently won")
  summary: string | null; // living deal summary — self-maintained by the enrichment loop
  summary_updated_at: string | null;
  summary_provenance: Attributes; // which timeline entries / comms it was built from (§7)
  owner_id: UUID | null;
  attributes: Attributes;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

/** A unified timeline entry: a free note OR a logged touchpoint OR a system change-event,
 *  distinguished by `type`. Table name stays `interaction`; the vocabulary is "timeline". */
export interface Interaction {
  id: UUID;
  workspace_id: UUID;
  type: InteractionType;
  occurred_at: string;
  direction: InteractionDirection | null;
  subject: string | null;
  summary: string | null; // always stored
  body: string | null; // notes only; ingested comms stay summary-only (compliance)
  source: string | null; // the MECHANISM: manual / enrichment / migration / granola (§6.4)
  external_id: string | null; // dedup/idempotency
  owner_id: UUID | null; // the AUTHOR it's attributed to (§6.4 — forward-compat for teams)
  created_at: string;
  updated_at: string;
}

/** A many-to-many link from a timeline entry to a record it concerns. One entry → any number of
 *  people/deals/orgs (notes-design §1, the flexible model). Purpose-built, kept out of `association`
 *  so graph traversals and timeline reads never have to filter each other out. */
export interface InteractionLink {
  id: UUID;
  workspace_id: UUID;
  interaction_id: UUID;
  record_type: TimelineRecordType;
  record_id: UUID;
  role: string | null; // participant | subject | organizer | … (optional)
  created_at: string;
}

/** A timeline entry with its resolved record links attached — what the read tools return. */
export interface TimelineEntry extends Interaction {
  links: InteractionLink[];
}

export interface Task {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string | null;
  due_at: string | null;
  status: TaskStatus;
  assignee_id: UUID | null;
  created_from_interaction_id: UUID | null; // provenance hook
  created_at: string;
  updated_at: string;
}

export interface Association {
  id: UUID;
  workspace_id: UUID;
  from_type: EntityType;
  from_id: UUID;
  to_type: EntityType;
  to_id: UUID;
  relationship_type: string; // works_at / advises / decision_maker / … (open set)
  attributes: Attributes;
  created_at: string;
}
