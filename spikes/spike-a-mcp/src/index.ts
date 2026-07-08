import OAuthProvider from "@cloudflare/workers-oauth-provider";
import { McpAgent } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SKILLS } from "./skills";

// Spike A: a thin MCP server that serves the SKAAS skill library on demand.
// Two tools only:
//   - list_skills : returns the CATALOG (id, name, description) — NOT the instructions.
//   - get_skill   : returns the full instructions for one skill id.
// The model should: call list_skills -> pick the right one -> call get_skill -> follow it.
//
// Wrapped in OAuth because Claude.ai's custom-connector flow requires an OAuth
// handshake (it cannot connect to a truly authless server). For this spike the
// authorize step AUTO-APPROVES — there are no real user accounts yet. That's fine
// for a throwaway with non-sensitive data; do NOT ship this as-is.

export class SkaasMCP extends McpAgent {
  server = new McpServer({
    name: "skaas-skill-library",
    version: "0.1.0",
  });

  async init() {
    this.server.tool(
      "list_skills",
      "List the SKAAS skills available to load. Call this FIRST — before answering from your own knowledge — whenever the user asks about their CRM, sales pipeline, deals, contacts, follow-up emails after calls/meetings, or cleaning up / auditing CRM data. Returns each skill's id, name, and description (not its instructions). Read the descriptions, pick the best match, then call get_skill with that id.",
      {},
      async () => ({
        content: [
          {
            type: "text",
            text: JSON.stringify(
              SKILLS.map(({ id, name, description }) => ({ id, name, description })),
              null,
              2
            ),
          },
        ],
      })
    );

    this.server.tool(
      "get_skill",
      "Load the full instructions for one SKAAS skill by id. You must obtain the id from list_skills first — do not guess ids. After calling, follow the returned instructions exactly to complete the user's task.",
      { id: z.string().describe("A skill id returned by a preceding list_skills call. Do not invent ids; call list_skills to discover valid ones.") },
      async ({ id }) => {
        const skill = SKILLS.find((s) => s.id === id);
        if (!skill) {
          return {
            isError: true,
            content: [
              {
                type: "text",
                text: `No skill with id "${id}". Call list_skills to see valid ids.`,
              },
            ],
          };
        }
        return { content: [{ type: "text", text: skill.instructions }] };
      }
    );
  }
}

// Handles everything that isn't the OAuth-protected /mcp API route:
//   - GET /authorize : auto-approve the OAuth request and redirect back with a code.
//   - GET /          : friendly info page.
// The provider itself serves /token, /register, and the /.well-known metadata.
const defaultHandler = {
  async fetch(request: Request, env: any): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/authorize") {
      const oauthReqInfo = await env.OAUTH_PROVIDER.parseAuthRequest(request);
      const { redirectTo } = await env.OAUTH_PROVIDER.completeAuthorization({
        request: oauthReqInfo,
        userId: "spike-user",
        scope: oauthReqInfo.scope ?? [],
        metadata: {},
        props: { autoApproved: true },
      });
      return Response.redirect(redirectTo, 302);
    }

    if (url.pathname === "/") {
      return new Response(
        "SKAAS Spike A MCP server (OAuth-wrapped). Add the /mcp endpoint as a custom connector in Claude.ai.",
        { status: 200, headers: { "content-type": "text/plain" } }
      );
    }

    return new Response("Not found", { status: 404 });
  },
};

export default new OAuthProvider({
  apiRoute: "/mcp",
  apiHandler: SkaasMCP.serve("/mcp") as any,
  defaultHandler: defaultHandler as any,
  authorizeEndpoint: "/authorize",
  tokenEndpoint: "/token",
  clientRegistrationEndpoint: "/register",
});
