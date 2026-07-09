// core/types.ts — the domain contract.
// This is the "headless CRM" vocabulary. It knows nothing about MCP or HTTP —
// the MCP adapter (and, later, a REST API or web UI) all speak in these types.
// Mirrors db/migrations/0001_init.sql.

export type UUID = string;

/** Flexible AI-managed facts. The typed fields above are the spine; this is the tail. */
export type Attributes = Record<string, unknown>;

export type DealStatus = "open" | "won" | "lost";
export type InteractionType = "email" | "meeting" | "call" | "note";
export type InteractionDirection = "inbound" | "outbound" | "internal";
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
  owner_id: UUID | null;
  attributes: Attributes;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface Interaction {
  id: UUID;
  workspace_id: UUID;
  type: InteractionType;
  occurred_at: string;
  direction: InteractionDirection | null;
  subject: string | null;
  summary: string | null; // always stored
  body: string | null; // notes only; ingested comms stay summary-only (compliance)
  source: string | null;
  external_id: string | null; // dedup/idempotency
  owner_id: UUID | null;
  created_at: string;
  updated_at: string;
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
