// inspect.ts — read-only snapshot of a workspace's CRM state. Use it to check what the
// enrichment loop actually wrote. Resolves the association graph into readable lines.
//
//   npm run inspect                # inspects "Dev Workspace" (what Claude.ai connects to)
//   npm run inspect -- "Some WS"   # a named workspace instead
//
// Writes nothing. Safe to run anytime.

import { getDb, initDb } from "./core/db.js";
import { getOrCreateWorkspaceByName } from "./core/workspace.js";

initDb(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

const money = (a: number | null, c: string) =>
  a == null ? "" : ` · ${c} ${a.toLocaleString()}`;

async function main() {
  const wsName = process.argv[2] ?? "Dev Workspace";
  const ws = await getOrCreateWorkspaceByName(wsName);
  const db = getDb();

  const [people, orgs, deals, assocs] = await Promise.all([
    db.from("person").select().eq("workspace_id", ws.id).is("archived_at", null).order("created_at"),
    db.from("organization").select().eq("workspace_id", ws.id).is("archived_at", null).order("created_at"),
    db.from("deal").select().eq("workspace_id", ws.id).is("archived_at", null).order("created_at"),
    db.from("association").select().eq("workspace_id", ws.id),
  ]);
  for (const r of [people, orgs, deals, assocs]) if (r.error) throw new Error(r.error.message);

  // id -> label maps for resolving associations
  const label = new Map<string, string>();
  for (const p of people.data!) label.set(p.id, `${p.name ?? "(no name)"}`);
  for (const o of orgs.data!) label.set(o.id, `${o.name ?? "(no name)"}`);
  for (const d of deals.data!) label.set(d.id, `${d.name ?? "(no name)"}`);
  const resolve = (id: string) => label.get(id) ?? `${id.slice(0, 8)}…`;

  console.log(`\n═══ CRM snapshot · workspace "${ws.name}" ═══\n`);

  console.log(`ORGANISATIONS (${orgs.data!.length})`);
  for (const o of orgs.data!) {
    const attrs = Object.keys(o.attributes ?? {}).length ? `  {${Object.entries(o.attributes).map(([k, v]) => `${k}: ${v}`).join(", ")}}` : "";
    console.log(`  • ${o.name ?? "(no name)"} — ${o.primary_domain ?? o.domains?.[0] ?? "no domain"}${attrs}`);
  }

  console.log(`\nCONTACTS (${people.data!.length})`);
  for (const p of people.data!) {
    const attrs = Object.keys(p.attributes ?? {}).length ? `  {${Object.entries(p.attributes).map(([k, v]) => `${k}: ${v}`).join(", ")}}` : "";
    console.log(`  • ${p.name ?? "(no name)"} — ${p.title ?? "?"} · ${p.primary_email ?? "no email"} · ${p.lifecycle_stage ?? "?"}${attrs}`);
  }

  console.log(`\nDEALS (${deals.data!.length})`);
  for (const d of deals.data!) {
    console.log(`  • ${d.name ?? "(no name)"} — ${d.stage ?? "?"}/${d.status}${money(d.amount, d.currency)}${d.expected_close_date ? ` · close ${d.expected_close_date}` : ""}`);
  }

  console.log(`\nLINKS (${assocs.data!.length})`);
  for (const a of assocs.data!) {
    console.log(`  • ${resolve(a.from_id)} —${a.relationship_type}→ ${resolve(a.to_id)}`);
  }

  console.log(`\n── totals: ${orgs.data!.length} orgs · ${people.data!.length} contacts · ${deals.data!.length} deals · ${assocs.data!.length} links ──\n`);
}

main().catch((err) => {
  console.error("\n💥 inspect failed:", err.message);
  process.exit(1);
});
