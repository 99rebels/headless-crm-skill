# Data Model (Phase 0) — draft to react to

*The core schema. Read `roadmap.md` for where this sits. This is a **draft for review**, not frozen. Philosophy: a lean **typed spine** (real columns for what we query/sort/filter) + a flexible **`attributes` (JSONB) layer** the AI fills (add fields with no migration) + a generic **association table** (the relationship graph). Decisions locked 2026-07-09: flex fields (no user-created custom objects yet), build the full association table.*

---

## Design principles (the guardrails)

1. **Typed spine, flexible tail.** Columns for what we query/sort/filter/validate; `attributes` JSONB for the variable rest. **Never** go full key-value (the EAV anti-pattern — kills query speed, integrity, cleanliness).
2. **Evolvable by construction.** Add a field → drop it in `attributes`, no migration. Add a relationship kind → new `type` string. Add an object later → it plugs into the generic association table with no restructuring. Promote a hot `attributes` key to a real column when it earns it.
3. **Interactions are the source of truth; structure is derived from them.** (Full provenance/"facts" table deferred to Phase 2 with the self-maintenance loop.)
4. **Multi-tenant from row one.** Every row carries `workspace_id`; isolate with row-level security.

## Conventions

- `id uuid` primary key everywhere; `workspace_id uuid` on every table (the tenant).
- `created_at`, `updated_at timestamptz`; `archived_at timestamptz` nullable (soft-delete — CRMs rarely hard-delete).
- `owner_id` = the workspace member who owns the record (for team seats). Users/auth is a related but separate workstream (Phase 1/4); `owner_id` is a nullable FK placeholder for now.
- `attributes jsonb` default `'{}'` on the core entities.

---

## Tables

### workspace  *(the tenant)*
| column | type | notes |
|---|---|---|
| id | uuid | |
| name | text | |
| settings | jsonb | per-workspace config with no schema change — e.g. pipeline stages, displayed term for "deal", defaults |
| created_at | timestamptz | |

### person
| column | type | notes |
|---|---|---|
| id | uuid | |
| workspace_id | uuid | |
| name | text | full name (can split to first/last later if we need salutations/sorting) |
| primary_email | text | for display / quick lookup |
| emails | text[] | ALL known emails/aliases — load-bearing for dedup in the self-maintenance loop (john@acme.com vs jsmith@…) |
| phone | text | |
| title | text | |
| lifecycle_stage | text | `lead` / `prospect` / `client` / `past` — configurable in `workspace.settings`. Replaces the legacy separate "Lead" object (HubSpot/Attio do this too); people filter by it constantly, so it earns a spine column |
| last_interaction_at | timestamptz | denormalised so "who haven't I talked to in a while" is a cheap query |
| owner_id | uuid | |
| **attributes** | jsonb | ★ AI-managed facts: `{preferred_name, decision_style, budget_reset, …}` |
| created_at / updated_at / archived_at | timestamptz | |

### organization
| column | type | notes |
|---|---|---|
| id | uuid | |
| workspace_id | uuid | |
| name | text | |
| primary_domain | text | |
| domains | text[] | all known domains — for matching people→orgs and dedup |
| last_interaction_at | timestamptz | |
| owner_id | uuid | |
| **attributes** | jsonb | ★ e.g. `{industry, size, renewal_month, …}` |
| created_at / updated_at / archived_at | timestamptz | |

### deal  *(the pipeline)*
| column | type | notes |
|---|---|---|
| id | uuid | |
| workspace_id | uuid | |
| name | text | |
| stage | text | references a stage in `workspace.settings.pipeline`; default stages documented, not over-modelled |
| status | text | `open` / `won` / `lost` |
| amount | numeric | |
| currency | text | default `USD` |
| expected_close_date | date | |
| owner_id | uuid | |
| **attributes** | jsonb | ★ |
| created_at / updated_at / archived_at | timestamptz | |

*Deals link to their org(s) and people via the **association** table (e.g. `decision_maker`, `champion`), not fixed FKs — keeps the graph consistent. (Option we could add later: a convenience `primary_organization_id` for the common single-account case.)*

### interaction  *(the timeline backbone)*
| column | type | notes |
|---|---|---|
| id | uuid | |
| workspace_id | uuid | |
| type | text | `email` / `meeting` / `call` / `note` |
| occurred_at | timestamptz | |
| direction | text | `inbound` / `outbound` / `internal` (nullable) |
| subject | text | |
| summary | text | ★ AI-generated summary — **always stored** |
| body | text | **see the compliance note below — deliberately NOT always stored** |
| source | text | `gmail` / `gcal` / `manual` / … |
| external_id | text | idempotency/dedup key so re-running the loop never duplicates the same email/event |
| owner_id | uuid | |
| created_at / updated_at | timestamptz | |

*Participants and links (interaction↔person, ↔org, ↔deal) live in the **association** table.*

### task  *(follow-ups)*
| column | type | notes |
|---|---|---|
| id | uuid | |
| workspace_id | uuid | |
| title | text | |
| description | text | |
| due_at | timestamptz | |
| status | text | `open` / `done` |
| assignee_id | uuid | |
| created_from_interaction_id | uuid | provenance hook: "this follow-up came from that email" (nullable) |
| created_at / updated_at | timestamptz | |

*Task's "about" link (to a person/deal/org) via the **association** table.*

### association  *(the relationship graph — links any record to any record)*
| column | type | notes |
|---|---|---|
| id | uuid | |
| workspace_id | uuid | |
| from_type | text | `person` / `organization` / `deal` / `interaction` / `task` |
| from_id | uuid | |
| to_type | text | |
| to_id | uuid | |
| relationship_type | text | `works_at`, `advises`, `decision_maker`, `champion`, `introduced`, `participated_in`, `subsidiary_of`, … (add freely) |
| attributes | jsonb | optional link detail (e.g. `since`, role notes) |
| created_at | timestamptz | |

*Indexes on `(from_type, from_id)` and `(to_type, to_id)` for traversal; unique on `(workspace_id, from_type, from_id, to_type, to_id, relationship_type)` to prevent duplicate links.*

---

## One design decision this surfaces (needs your call)

**Do we store the raw `body` of ingested comms, or only the AI `summary` + metadata?**

This ties directly to the client-side-loop / "we never hold raw comms" compliance win:
- **Ingested comms (email/calendar):** the loop reads the raw content *in the user's Claude*, extracts a `summary` + structured facts, and writes those to us. To honour "we don't hold raw comms," we'd store **summary + metadata only, not the full `body`.**
- **User-authored notes** (they type a meeting note into the CRM): that content *is* CRM data they want kept — store `body` fully.

So `body` would be populated for `type = note`, and left empty (summary-only) for ingested `email`/`meeting`. That keeps our compliance surface small while still storing what users actually want. **Flagging because it's a real trade — richer records vs smaller data-liability. My lean: summary-only for ingested comms.**

## Deferred past Phase 0 (don't build yet)

- **Provenance/`facts` table** (which interaction taught us each attribute, with confidence) — comes with the self-maintenance loop in Phase 2. Hooks are in place (`interaction` first-class, `created_from_interaction_id`).
- **User-created custom objects** — flex fields for now; we curate new first-class objects only when a real cross-user pattern emerges. (Attio offers these; even it defaults to just People + Companies, so lean-core is the validated starting point.)
- **Files / attachments** (e.g. attach a proposal PDF to a deal) — standard in Salesforce/HubSpot, genuinely useful later, but needs blob storage. Phase 3+.

*Validated against Salesforce / HubSpot / Attio object models (2026-07): our objects cover the universal CRM spine; omitted objects (Tickets, Campaigns, Products/Quotes/Orders) are deliberate — not relevant to solo/fractional operators.*
- **Formal pipeline/stage tables** — start with `stage` text + `workspace.settings`; formalise only if needed.
- **Users/auth/billing** — separate workstream.
