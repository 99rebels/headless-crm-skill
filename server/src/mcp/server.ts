// mcp/server.ts — the stdio entry point. Run:  npm run mcp
// Resolves a dev workspace and serves the CRM tools over stdio (what a local MCP client,
// e.g. the MCP Inspector or Claude Desktop, connects to). Public hosting + OAuth for
// Claude.ai come later.

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { getOrCreateWorkspaceByName } from "../core/workspace.js";
import { buildServer } from "./build.js";

async function main() {
  const ws = await getOrCreateWorkspaceByName("Dev Workspace");
  const server = buildServer(ws.id);
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Log to stderr — stdout is the MCP protocol channel and must not be polluted.
  console.error(`CRM MCP server running · workspace "${ws.name}" (${ws.id})`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
