// smoke.ts — proves the spine end-to-end against your real Supabase.
// Run:  npm install  &&  npm run smoke
// It creates a throwaway workspace + contact, exercises read/update/dedup, prints results,
// then cleans up after itself (deletes the workspace, which cascades to the person).

import { db } from "./core/db.js";
import { createWorkspace } from "./core/workspace.js";
import {
  createPerson,
  getPerson,
  findPeople,
  findPeopleByEmail,
  updatePerson,
} from "./core/person.js";

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

    console.log("\n📇 Final record:");
    console.log(JSON.stringify(updated, null, 2));
  } finally {
    // clean up — deleting the workspace cascades to the person
    await db.from("workspace").delete().eq("id", ws.id);
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
