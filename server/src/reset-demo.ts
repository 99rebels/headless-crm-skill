// reset-demo.ts — wipe ALL records in a workspace (people, orgs, deals, associations), leaving the
// workspace row itself. Pair with `npm run seed` to restore the curated demo "before" state — the
// `reset-demo` npm script chains both. Use when a test run (e.g. a CSV import) polluted the demo
// workspace and you want a clean, known-good state before a rehearsal/demo.
//
//   npm run reset-demo                 # wipe + reseed "Dev Workspace"
//   npm run reset-demo:wipe -- "WS"    # wipe only, a named workspace
//
// Scoped by workspace_id — it cannot touch another tenant's data. Deletes associations first
// (they reference the other records), then deals/people/organizations.

import { getDb, initDb } from "./core/db.js";
import { getOrCreateWorkspaceByName } from "./core/workspace.js";

initDb(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

async function main() {
  const wsName = process.argv[2] ?? "Dev Workspace";
  const ws = await getOrCreateWorkspaceByName(wsName);
  console.log(`\n⚠️  wiping ALL records in workspace "${ws.name}" (${ws.id})`);

  for (const table of ["association", "deal", "person", "organization"] as const) {
    const { error, count } = await getDb()
      .from(table)
      .delete({ count: "exact" })
      .eq("workspace_id", ws.id);
    if (error) throw new Error(`${table}: ${error.message}`);
    console.log(`  − ${table}: deleted ${count ?? 0}`);
  }

  console.log(`\n✅ workspace "${ws.name}" wiped clean.\n`);
}

main().catch((err) => {
  console.error("\n💥 reset failed:", err.message);
  process.exit(1);
});
