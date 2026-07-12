// mcp-smoke.ts — proves the MCP path end-to-end: a real MCP Client calls the tools,
// which hit the core, which hits your Supabase. Uses an in-memory transport (no network,
// no browser). Run:  npm run mcp-smoke
// Self-cleaning: deletes the throwaway workspace afterwards.

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { getDb, initDb } from "./core/db.js";
import { createWorkspace } from "./core/workspace.js";
import { buildServer } from "./mcp/build.js";

initDb(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

function ok(label: string, cond: boolean) {
  console.log(`${cond ? "✅" : "❌"} ${label}`);
  if (!cond) process.exitCode = 1;
}

/** Tool results come back as text content; parse the JSON payload we put there. */
function payload(res: any): any {
  const t = res?.content?.[0]?.text;
  return typeof t === "string" ? JSON.parse(t) : undefined;
}

async function main() {
  console.log("→ driving the CRM MCP tools through a real MCP client…\n");

  const ws = await createWorkspace("MCP Smoke Workspace");
  const server = buildServer(ws.id);

  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  const client = new Client({ name: "smoke-client", version: "0.1.0" });
  await client.connect(clientTransport);

  try {
    const tools = (await client.listTools()).tools.map((t) => t.name).sort();
    const expectedTools = [
      "create_contact", "find_contacts", "get_contact", "update_contact",
      "create_organization", "find_organizations", "get_organization", "update_organization",
      "create_deal", "find_deals", "get_deal", "update_deal",
      "link_records", "find_associations", "unlink_records",
      "get_pipeline_summary", "bulk_import",
    ];
    ok(
      `lists ${expectedTools.length} tools (${tools.join(", ")})`,
      tools.length === expectedTools.length && expectedTools.every((n) => tools.includes(n)),
    );

    const created = payload(
      await client.callTool({
        name: "create_contact",
        arguments: {
          name: "Kate Chen",
          email: "Kate@Acme.com",
          title: "VP Finance",
          lifecycle_stage: "prospect",
          attributes: { preferred_name: "Kate" },
        },
      }),
    );
    ok("create_contact → created", created?.status === "created");
    const id = created?.contact?.id;
    ok("returned a contact id", !!id);
    ok("email normalised via core", created?.contact?.primary_email === "kate@acme.com");

    // read-before-write: same email again should NOT duplicate
    const dupe = payload(
      await client.callTool({
        name: "create_contact",
        arguments: { name: "Katherine Chen", email: "kate@acme.com" },
      }),
    );
    ok("create_contact (same email) → already_exists (no duplicate)", dupe?.status === "already_exists");
    ok("dedup returned the original contact", dupe?.contact?.id === id);

    const found = payload(
      await client.callTool({ name: "find_contacts", arguments: { email: "KATE@ACME.COM" } }),
    );
    ok("find_contacts by any-case email → 1 hit", found?.count === 1 && found?.contacts?.[0]?.id === id);

    const updated = payload(
      await client.callTool({
        name: "update_contact",
        arguments: { id, lifecycle_stage: "client" },
      }),
    );
    ok("update_contact → client", updated?.contact?.lifecycle_stage === "client");

    const fetched = payload(await client.callTool({ name: "get_contact", arguments: { id } }));
    ok("get_contact returns the updated record", fetched?.id === id && fetched?.lifecycle_stage === "client");

    // ── organization (+ read-before-write dedup via MCP) ───────────────────────────
    const org = payload(
      await client.callTool({
        name: "create_organization",
        arguments: { name: "Acme Inc", domain: "https://www.Acme.com" },
      }),
    );
    ok("create_organization → created", org?.status === "created");
    const orgId = org?.organization?.id;
    ok("org domain normalised via core", org?.organization?.primary_domain === "acme.com");
    const orgDupe = payload(
      await client.callTool({
        name: "create_organization",
        arguments: { name: "ACME", domain: "acme.com" },
      }),
    );
    ok("create_organization (same domain) → already_exists", orgDupe?.status === "already_exists");

    // ── deal (+ pipeline status filter via MCP) ────────────────────────────────────
    const deal = payload(
      await client.callTool({
        name: "create_deal",
        arguments: { name: "Acme — annual retainer", stage: "proposal", amount: 24000 },
      }),
    );
    ok("create_deal → created (defaults applied)", deal?.deal?.status === "open" && deal?.deal?.currency === "USD");
    const dealId = deal?.deal?.id;
    const openDeals = payload(await client.callTool({ name: "find_deals", arguments: { status: "open" } }));
    ok("find_deals(open) returns the open deal", openDeals?.deals?.some((d: any) => d.id === dealId));

    // ── associations (link + traverse via MCP) ─────────────────────────────────────
    const linked = payload(
      await client.callTool({
        name: "link_records",
        arguments: {
          from_type: "person", from_id: id,
          to_type: "deal", to_id: dealId,
          relationship_type: "decision_maker",
        },
      }),
    );
    ok("link_records → linked", linked?.status === "linked");
    await client.callTool({
      name: "link_records",
      arguments: {
        from_type: "person", from_id: id,
        to_type: "organization", to_id: orgId,
        relationship_type: "works_at",
      },
    });
    const assoc = payload(
      await client.callTool({
        name: "find_associations",
        arguments: { entity_type: "person", entity_id: id },
      }),
    );
    ok("find_associations gathers both of the contact's links", assoc?.count === 2);

    // ── bulk_import (one-shot, SET-BASED create + dedupe + link) ───────────────────
    // Multiple NEW records of each type so the batch inserts + key→id order-mapping are exercised
    // (not just a single-row insert). c2/o2 are existing → must dedupe, not duplicate.
    const bulk = payload(
      await client.callTool({
        name: "bulk_import",
        arguments: {
          plan: {
            organizations: [
              { key: "o0", name: "Zephyr Inc", domain: "zephyr.test" },
              { key: "o1", name: "Bramble Co", domain: "bramble.test" },
              { key: "o2", name: "Acme (dupe)", domain: "acme.com" }, // existing → reuse
            ],
            contacts: [
              { key: "c0", name: "Rae Lin", email: "rae@zephyr.test", lifecycle_stage: "prospect" },
              { key: "c1", name: "Bo Vance", email: "bo@bramble.test", lifecycle_stage: "lead" },
              { key: "c2", name: "Kate Dup", email: "kate@acme.com" }, // existing → reuse
            ],
            deals: [
              { key: "d0", name: "Zephyr rollout", stage: "won", status: "won", amount: 1000 },
              { key: "d1", name: "Bramble pilot", stage: "proposal", amount: 500 },
            ],
            links: [
              { from: "c0", to: "o0", relationship_type: "works_at" },
              { from: "c1", to: "o1", relationship_type: "works_at" }, // 2nd-new-of-each: catches order bugs
              { from: "c1", to: "d1", relationship_type: "primary_contact" },
            ],
          },
        },
      }),
    );
    ok(
      "bulk_import created 2 new orgs + 2 new contacts + 2 deals (multi-row batch inserts)",
      bulk?.created?.organizations === 2 && bulk?.created?.contacts === 2 && bulk?.created?.deals === 2,
    );
    ok(
      "bulk_import reused existing org + contact by dedup (no duplicates)",
      bulk?.reused?.organizations === 1 && bulk?.reused?.contacts === 1,
    );
    ok(
      "bulk_import resolved all 3 links via local keys",
      bulk?.created?.links === 3 && (bulk?.errors?.length ?? 0) === 0,
    );
    // Prove the 2ND new contact's keys mapped to the RIGHT rows (order-correct after batch insert).
    const bo = payload(await client.callTool({ name: "find_contacts", arguments: { email: "bo@bramble.test" } }));
    const boAssoc = payload(
      await client.callTool({ name: "find_associations", arguments: { entity_type: "person", entity_id: bo?.contacts?.[0]?.id } }),
    );
    ok(
      "bulk_import mapped 2nd-new-record keys correctly (c1 linked to o1 + d1)",
      boAssoc?.count === 2 &&
        boAssoc?.associations?.some((a: any) => a.relationship_type === "works_at") &&
        boAssoc?.associations?.some((a: any) => a.relationship_type === "primary_contact"),
    );

    console.log("\n📇 Final contact via MCP:");
    console.log(JSON.stringify(fetched, null, 2));
  } finally {
    await client.close();
    await getDb().from("workspace").delete().eq("id", ws.id);
    console.log("\n🧹 cleaned up throwaway workspace");
  }

  console.log(
    process.exitCode === 1
      ? "\n❌ MCP smoke had failures — see above."
      : "\n✅ MCP path works: client → tools → core → Supabase, incl. read-before-write dedup.",
  );
}

main().catch((err) => {
  console.error("\n💥 MCP smoke threw:", err.message);
  process.exit(1);
});
