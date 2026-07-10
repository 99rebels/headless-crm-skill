// seed-demo.ts — populate the demo's "before" CRM state, so the enrichment loop has something
// to dedupe against and update. Idempotent: read-before-write means re-running never duplicates.
//
//   npm run seed                 # seeds the "Dev Workspace" (what Claude.ai connects to)
//   npm run seed -- "Some WS"    # seeds a named workspace instead
//
// The state is deliberately partial — it's the BEFORE. The fixture emails (see the enrichment
// skill) then drive it to the AFTER: David is "Founder" here so the loop finds the Founder→CEO
// conflict; Northwind exists so a new person there dedupes by domain; Calder/Priya/Tom are absent
// so they surface as net-new.

import { initDb } from "./core/db.js";
import { getOrCreateWorkspaceByName } from "./core/workspace.js";
import {
  createOrganization,
  findOrganizationsByDomain,
} from "./core/organization.js";
import { createPerson, findPeopleByEmail } from "./core/person.js";
import { createDeal, findDeals } from "./core/deal.js";
import { link } from "./core/association.js";
import type { CreateDealInput } from "./core/deal.js";
import type { CreateOrganizationInput } from "./core/organization.js";
import type { CreatePersonInput } from "./core/person.js";
import type { Deal, Organization, Person, UUID } from "./core/types.js";

initDb(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

/** Idempotent org: reuse by domain if present, else create. */
async function ensureOrg(ws: UUID, input: CreateOrganizationInput): Promise<Organization> {
  const domains = [...(input.domains ?? []), ...(input.primary_domain ? [input.primary_domain] : [])];
  const existing = await findOrganizationsByDomain(ws, domains);
  if (existing.length) {
    console.log(`  = org exists: ${existing[0].name}`);
    return existing[0];
  }
  const org = await createOrganization(ws, input);
  console.log(`  + org created: ${org.name}`);
  return org;
}

/** Idempotent person: reuse by email if present, else create. */
async function ensurePerson(ws: UUID, input: CreatePersonInput): Promise<Person> {
  const emails = [...(input.emails ?? []), ...(input.primary_email ? [input.primary_email] : [])];
  const existing = await findPeopleByEmail(ws, emails);
  if (existing.length) {
    console.log(`  = person exists: ${existing[0].name}`);
    return existing[0];
  }
  const person = await createPerson(ws, input);
  console.log(`  + person created: ${person.name}`);
  return person;
}

/** Idempotent deal: deals have no natural key, so match by exact name within the workspace. */
async function ensureDeal(ws: UUID, input: CreateDealInput): Promise<Deal> {
  const all = await findDeals(ws, { limit: 200 });
  const existing = all.find((d) => d.name === input.name);
  if (existing) {
    console.log(`  = deal exists: ${existing.name}`);
    return existing;
  }
  const deal = await createDeal(ws, input);
  console.log(`  + deal created: ${deal.name}`);
  return deal;
}

async function main() {
  const wsName = process.argv[2] ?? "Dev Workspace";
  const ws = await getOrCreateWorkspaceByName(wsName);
  console.log(`\n→ seeding demo "before" state into workspace "${ws.name}" (${ws.id})\n`);

  // ── Northwind Logistics — an existing CLIENT ────────────────────────────────────
  const northwind = await ensureOrg(ws.id, {
    name: "Northwind Logistics",
    primary_domain: "northwind.co",
    attributes: { industry: "logistics", size: "50-100" },
  });
  const sarah = await ensurePerson(ws.id, {
    name: "Sarah Mills",
    primary_email: "sarah@northwind.co",
    title: "COO",
    lifecycle_stage: "client",
    attributes: { preferred_name: "Sarah" },
  });
  const northwindDeal = await ensureDeal(ws.id, {
    name: "Northwind — Q3 ops retainer",
    stage: "won",
    status: "won",
    amount: 18000,
  });
  await link(ws.id, { from_type: "person", from_id: sarah.id, to_type: "organization", to_id: northwind.id, relationship_type: "works_at" });
  await link(ws.id, { from_type: "person", from_id: sarah.id, to_type: "deal", to_id: northwindDeal.id, relationship_type: "decision_maker" });

  // ── Meridian Health — a PROSPECT (David is "Founder" ON PURPOSE → conflict bait) ──
  const meridian = await ensureOrg(ws.id, {
    name: "Meridian Health",
    primary_domain: "meridianhealth.com",
    attributes: { industry: "healthcare" },
  });
  const david = await ensurePerson(ws.id, {
    name: "David Okafor",
    primary_email: "david@meridianhealth.com",
    title: "Founder", // fixture email signs off "CEO" → the loop should flag this, not silently overwrite
    lifecycle_stage: "prospect",
  });
  const meridianDeal = await ensureDeal(ws.id, {
    name: "Meridian — fractional COO engagement",
    stage: "proposal",
    status: "open",
    amount: 30000,
    expected_close_date: null as unknown as string | undefined,
  });
  await link(ws.id, { from_type: "person", from_id: david.id, to_type: "organization", to_id: meridian.id, relationship_type: "works_at" });
  await link(ws.id, { from_type: "person", from_id: david.id, to_type: "deal", to_id: meridianDeal.id, relationship_type: "decision_maker" });

  console.log(`\n✅ seeded. Before-state summary:`);
  console.log(`   • 2 orgs: Northwind Logistics (client), Meridian Health (prospect)`);
  console.log(`   • 2 people: Sarah Mills (COO), David Okafor (Founder ← intentional)`);
  console.log(`   • 2 deals: Northwind retainer (won), Meridian engagement (proposal)`);
  console.log(`\n   NOT seeded (net-new for the loop to discover): Calder & Co, Priya Nair, Tom Reyes.\n`);
}

main().catch((err) => {
  console.error("\n💥 seed failed:", err.message);
  process.exit(1);
});
