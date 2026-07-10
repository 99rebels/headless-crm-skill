// smoke.ts — proves the spine end-to-end against your real Supabase.
// Run:  npm install  &&  npm run smoke
// It creates a throwaway workspace + contact, exercises read/update/dedup, prints results,
// then cleans up after itself (deletes the workspace, which cascades to the person).

import { getDb, initDb } from "./core/db.js";
import { createWorkspace } from "./core/workspace.js";

initDb(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);
import {
  createPerson,
  getPerson,
  findPeople,
  findPeopleByEmail,
  updatePerson,
} from "./core/person.js";
import {
  createOrganization,
  findOrganizationsByDomain,
} from "./core/organization.js";
import { createDeal, findDeals, updateDeal } from "./core/deal.js";
import { findAssociationsFor, link } from "./core/association.js";

function ok(label: string, cond: boolean) {
  console.log(`${cond ? "✅" : "❌"} ${label}`);
  if (!cond) process.exitCode = 1;
}

async function main() {
  console.log("→ connecting to Supabase and exercising the core…\n");

  const ws = await createWorkspace("Smoke Test Workspace");
  ok("created workspace", !!ws.id);

  try {
    const kate = await createPerson(ws.id, {
      name: "Kate Chen",
      primary_email: "Kate@Acme.com", // mixed case on purpose — should normalise
      title: "VP Finance",
      lifecycle_stage: "prospect",
      attributes: { preferred_name: "Kate", decision_style: "cautious, loops in CFO" },
    });
    ok("created person", !!kate.id);
    ok("email normalised to lowercase", kate.primary_email === "kate@acme.com");
    ok("primary email present in emails[]", kate.emails.includes("kate@acme.com"));
    ok("attributes stored", (kate.attributes as any).preferred_name === "Kate");

    const fetched = await getPerson(ws.id, kate.id);
    ok("read person back", fetched?.id === kate.id);

    const byEmail = await findPeopleByEmail(ws.id, ["KATE@acme.com"]);
    ok("dedup lookup finds by any-case email", byEmail.some((p) => p.id === kate.id));

    const updated = await updatePerson(ws.id, kate.id, { lifecycle_stage: "client" });
    ok("update person", updated.lifecycle_stage === "client");
    ok("updated_at advanced by trigger", updated.updated_at !== kate.updated_at);

    const list = await findPeople(ws.id);
    ok("list people", list.length === 1 && list[0].id === kate.id);

    // ── organization + dedup ──────────────────────────────────────────────────────
    const acme = await createOrganization(ws.id, {
      name: "Acme Inc",
      primary_domain: "https://www.Acme.com/about", // dirty on purpose — should normalise to acme.com
      attributes: { industry: "fintech" },
    });
    ok("created organization", !!acme.id);
    ok("domain normalised (protocol/www/path stripped)", acme.primary_domain === "acme.com");
    const orgDupe = await findOrganizationsByDomain(ws.id, ["ACME.com"]);
    ok("org dedup finds by any-case domain", orgDupe.some((o) => o.id === acme.id));

    // ── deal + pipeline filter ────────────────────────────────────────────────────
    const deal = await createDeal(ws.id, {
      name: "Acme — annual retainer",
      stage: "proposal",
      amount: 24000,
    });
    ok("created deal (defaults applied)", deal.status === "open" && deal.currency === "USD");
    const won = await updateDeal(ws.id, deal.id, { status: "won" });
    ok("update deal → won", won.status === "won");
    const openDeals = await findDeals(ws.id, { status: "open" });
    ok("status filter excludes the won deal", openDeals.every((d) => d.id !== deal.id));

    // ── associations (the graph) ──────────────────────────────────────────────────
    await link(ws.id, {
      from_type: "person",
      from_id: kate.id,
      to_type: "organization",
      to_id: acme.id,
      relationship_type: "works_at",
    });
    await link(ws.id, {
      from_type: "person",
      from_id: kate.id,
      to_type: "deal",
      to_id: deal.id,
      relationship_type: "decision_maker",
    });
    // re-link the same pair — must NOT duplicate (idempotent upsert)
    await link(ws.id, {
      from_type: "person",
      from_id: kate.id,
      to_type: "organization",
      to_id: acme.id,
      relationship_type: "works_at",
    });
    const kateLinks = await findAssociationsFor(ws.id, "person", kate.id);
    ok("kate has exactly 2 links (idempotent re-link didn't duplicate)", kateLinks.length === 2);
    const dealLinks = await findAssociationsFor(ws.id, "deal", deal.id);
    ok("traversal finds the link from the deal's side too", dealLinks.length === 1);

    console.log("\n📇 Final record:");
    console.log(JSON.stringify(updated, null, 2));
  } finally {
    // clean up — deleting the workspace cascades to the person
    await getDb().from("workspace").delete().eq("id", ws.id);
    console.log("\n🧹 cleaned up throwaway workspace");
  }

  console.log(
    process.exitCode === 1
      ? "\n❌ Smoke test had failures — see above."
      : "\n✅ Spine works: connection, schema, and core CRUD all good.",
  );
}

main().catch((err) => {
  console.error("\n💥 Smoke test threw:", err.message);
  process.exit(1);
});
