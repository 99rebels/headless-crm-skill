// worker/index.ts — the Cloudflare Worker adapter: the SAME core, exposed to Claude.ai
// over a remote, OAuth-wrapped MCP endpoint. Reuses Spike A's proven OAuth setup
// (auto-approve — spike/demo only, no real accounts yet; do NOT ship as-is).
//
// The CRM tools come from registerCrmTools (shared with the local stdio adapter); the only
// worker-specific bits are: getting Supabase creds from the Worker env, and the OAuth shell.

import OAuthProvider from "@cloudflare/workers-oauth-provider";
import { McpAgent } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { initDb } from "../core/db.js";
import { getOrCreateWorkspaceByName } from "../core/workspace.js";
import { registerCrmTools } from "../mcp/build.js";

interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  // Which workspace this deployment is bound to. Absent on the dev Worker (→ "Dev Workspace").
  // A per-tenant deployment (e.g. wrangler.advisor.jsonc) sets this to that tenant's workspace
  // name — the lightweight isolation used before the real multi-tenant auth workstream lands.
  WORKSPACE_NAME?: string;
  OAUTH_PROVIDER: any;
}

export class CrmMCP extends McpAgent {
  server = new McpServer({ name: "headless-crm", version: "0.1.0" });

  async init() {
    const env = this.env as Env;
    initDb(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);
    // Register tools with a LAZY workspace resolver — do NOT hit the DB here. This keeps the
    // MCP handshake from depending on a Supabase round-trip at connection time (a DB blip then
    // can't fail the connection); the workspace is resolved+memoised on the first tool call.
    // The workspace name is pinned per-deployment via WORKSPACE_NAME (dev Worker → "Dev
    // Workspace"; a per-tenant Worker → that tenant's workspace). Real multi-tenant resolution
    // from the connection identity comes with the auth workstream.
    const workspaceName = env.WORKSPACE_NAME ?? "Dev Workspace";
    registerCrmTools(this.server, () =>
      getOrCreateWorkspaceByName(workspaceName).then((ws) => ws.id),
    );
  }
}

// Everything that isn't the OAuth-protected /mcp route. /authorize auto-approves (demo only).
const defaultHandler = {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/authorize") {
      const oauthReqInfo = await env.OAUTH_PROVIDER.parseAuthRequest(request);
      const { redirectTo } = await env.OAUTH_PROVIDER.completeAuthorization({
        request: oauthReqInfo,
        userId: "demo-user",
        scope: oauthReqInfo.scope ?? [],
        metadata: {},
        props: { autoApproved: true },
      });
      return Response.redirect(redirectTo, 302);
    }

    if (url.pathname === "/") {
      return new Response(
        "Headless CRM MCP server (OAuth-wrapped). Add the /mcp endpoint as a custom connector in Claude.ai.",
        { status: 200, headers: { "content-type": "text/plain" } },
      );
    }

    return new Response("Not found", { status: 404 });
  },
};

export default new OAuthProvider({
  apiRoute: "/mcp",
  apiHandler: CrmMCP.serve("/mcp") as any,
  defaultHandler: defaultHandler as any,
  authorizeEndpoint: "/authorize",
  tokenEndpoint: "/token",
  clientRegistrationEndpoint: "/register",
});
