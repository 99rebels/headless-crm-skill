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

const text = (obj: unknown) => ({
  content: [
    {
      type: "text" as const,
      text: typeof obj === "string" ? obj : JSON.stringify(obj, null, 2),
    },
  ],
});
const errorText = (msg: string) => ({ ...text(msg), isError: true as const });

export function buildServer(workspaceId: UUID): McpServer {
  const server = new McpServer({ name: "crm", version: "0.1.0" });

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
          .record(z.unknown())
          .optional()
          .describe("flexible extra facts, e.g. { preferred_name: 'Kate' }"),
      },
    },
    async (args) => {
      try {
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
        attributes: z.record(z.unknown()).optional(),
      },
    },
    async (args) => {
      try {
        const { id, email, ...rest } = args;
        const person = await updatePerson(workspaceId, id, { ...rest, primary_email: email });
        return text({ status: "updated", contact: person });
      } catch (e) {
        return errorText((e as Error).message);
      }
    },
  );

  return server;
}
