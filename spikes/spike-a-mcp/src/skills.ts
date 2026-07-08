// The SKAAS "skill library" — lives on the server, never on the customer's disk.
// For Spike A the instructions are self-contained and demonstrable WITHOUT a CRM.
// Each skill embeds a distinctive marker line so that, when the model runs it, we can
// unambiguously confirm the behavior came from server-delivered text it could not have
// guessed — proving the skill flowed: server -> tool result -> model context -> behavior.

export interface Skill {
  id: string;
  name: string;
  description: string;
  instructions: string;
}

export const SKILLS: Skill[] = [
  {
    id: "pipeline-brief",
    name: "Pipeline Brief",
    description:
      "Turn a list of sales deals into a clean, grouped pipeline summary. Use when the user asks to summarize, review, or get a brief on their pipeline or deals.",
    instructions: [
      "# Skill: Pipeline Brief",
      "",
      "When executing this skill you MUST:",
      "1. Begin your reply with the exact line: `🎯 SKAAS PIPELINE BRIEF (skill v1)`",
      "2. If the user has not provided any deals, ask them to paste a few (name, stage, amount). Do not invent data.",
      "3. Render the deals as a markdown table with columns: Deal | Stage | Amount | Next step.",
      "4. Group rows by Stage, ordered: Discovery → Proposal → Negotiation → Closed.",
      "5. End with a **Totals** line: count of deals and summed amount per stage.",
      "6. Flag any deal missing a Next step with ⚠️ rather than guessing one.",
    ].join("\n"),
  },
  {
    id: "follow-up-draft",
    name: "Follow-up Draft",
    description:
      "Draft a follow-up email after a sales call from rough notes. Use when the user wants to write a follow-up, recap, or thank-you email after a meeting or call.",
    instructions: [
      "# Skill: Follow-up Draft",
      "",
      "When executing this skill you MUST:",
      "1. Begin your reply with the exact line: `✉️ SKAAS FOLLOW-UP DRAFT (skill v1)`",
      "2. Ask for the call notes if none were given. Do not fabricate commitments.",
      "3. Produce an email with: a one-line subject, a warm opener referencing something specific from the call, a short bulleted recap of what was discussed, clearly-owned next steps (who does what by when), and a light close.",
      "4. Keep it under 150 words.",
      "5. After the draft, list any 'open items to confirm' where the notes were ambiguous — flag, don't assume.",
    ].join("\n"),
  },
  {
    id: "crm-hygiene",
    name: "CRM Hygiene Check",
    description:
      "Scan CRM records for staleness, missing fields, and likely duplicates, and propose fixes for approval. Use when the user wants to clean up, audit, or check the health of their CRM data.",
    instructions: [
      "# Skill: CRM Hygiene Check",
      "",
      "When executing this skill you MUST:",
      "1. Begin your reply with the exact line: `🧹 SKAAS CRM HYGIENE CHECK (skill v1)`",
      "2. For each record provided, report: missing required fields, last-touched staleness, and any record that looks like a duplicate of another.",
      "3. Propose a specific fix for each issue, but NEVER present a fix as already applied — this skill only proposes, a human approves.",
      "4. Sort findings by severity: likely-duplicate first, then stale, then missing-field.",
      "5. End with a one-line summary: 'N issues found, 0 changes made — awaiting approval.'",
    ].join("\n"),
  },
];
