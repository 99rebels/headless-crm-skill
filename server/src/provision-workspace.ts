// provision-workspace.ts — stand up a new (empty) tenant workspace and seed its settings/vocab.
// Used to give a design partner their own isolated instance ("Path A"), paired with a per-tenant
// Worker deployment (wrangler.advisor.jsonc) whose WORKSPACE_NAME matches the name used here.
//
//   npm run provision -- "Advisor Workspace"                 # create/reuse + default vocab
//   npm run provision -- "Advisor Workspace" self@acme.com   # also set self.emails (dashboard
//                                                            # excludes the operator's own record)
//
// Idempotent: re-running reuses the workspace by name and re-applies settings (shallow-merged).
// The summary tool falls back to sane defaults for any unset key, so the placeholder self.emails
// can be filled later once you have the advisor's real address(es).

import { initDb } from "./core/db.js";
import { getOrCreateWorkspaceByName, updateWorkspaceSettings } from "./core/workspace.js";

initDb(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

// Default CRM vocabulary — mirrors the skills' config.json and summary.ts DEFAULTS. Adjust per
// tenant later if they use different stage names (it's data in workspace.settings, not code).
const DEFAULT_SETTINGS = {
  pipeline: ["discovery", "proposal", "verbal", "won", "lost"],
  lifecycle_stages: ["lead", "prospect", "client", "partner", "past"],
  default_currency: "USD",
  self: { emails: [] as string[], domains: [] as string[] },
};

async function main() {
  const name = process.argv[2];
  if (!name) {
    console.error('usage: npm run provision -- "<Workspace Name>" [selfEmail ...]');
    process.exit(1);
  }
  const selfEmails = process.argv.slice(3).map((e) => e.toLowerCase());

  const ws = await getOrCreateWorkspaceByName(name);
  console.log(`\n→ workspace "${ws.name}" (${ws.id})`);

  const settings = {
    ...DEFAULT_SETTINGS,
    self: { ...DEFAULT_SETTINGS.self, emails: selfEmails },
  };
  await updateWorkspaceSettings(ws.id, settings);

  console.log(`  ✓ settings applied:`);
  console.log(`    pipeline stages : ${settings.pipeline.join(" → ")}`);
  console.log(`    lifecycle       : ${settings.lifecycle_stages.join(", ")}`);
  console.log(`    currency        : ${settings.default_currency}`);
  console.log(
    `    self.emails     : ${selfEmails.length ? selfEmails.join(", ") : "(none yet — pass the advisor's address to exclude his own record from the roster)"}`,
  );
  console.log(`\n✅ provisioned. Next: set WORKSPACE_NAME="${ws.name}" in wrangler.advisor.jsonc, then deploy it.\n`);
}

main().catch((err) => {
  console.error("\n💥 provision failed:", err.message);
  process.exit(1);
});
