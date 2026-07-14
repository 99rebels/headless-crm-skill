// core/summary.ts — the pipeline dashboard summary: ONE deterministic computation of the
// factual half of the dashboard (stats, stage buckets, roster, recently-won, and attention
// "signals"), so every model that renders the dashboard gets identical facts. The model's only
// remaining job is the Focus prose — anchored by the signals below, not derived from scratch.
//
// Everything here is a RULE decided once (see docs / SKILL.md), not a per-call judgement:
//   • unstaged open deals  → their own "Unstaged" bucket, still counted in totals
//   • a stage not in the workspace vocabulary → its own bucket, flagged (never silently dropped)
//   • relationships        → contacts WITH a lifecycle stage, minus the operator's own record
//   • recency              → real last_interaction_at only; null ⇒ "no contact logged", no nudge
//   • mixed currencies     → sum only the workspace currency; flag any deal that differs
//   • recently won         → status=won with closed_at within RECENTLY_WON_DAYS
//
// Vocabulary (open stages + order, lifecycle values, self emails, default currency) is read from
// workspace.settings — DATA, not code — so adding a stage is a settings change, never a code one.

import { getDb, orThrow } from "./db.js";
import { getLatestContactMap } from "./note.js";
import type { Deal, Organization, Person, UUID } from "./types.js";

const RECENTLY_WON_DAYS = 90;
const QUIET_AFTER_DAYS = 30;

// Fallbacks used only when workspace.settings hasn't been configured yet.
const DEFAULTS = {
  open_stages: ["discovery", "proposal", "verbal"],
  lifecycle_stages: ["lead", "prospect", "client", "partner", "past"],
  self_emails: [] as string[],
  default_currency: "USD",
};

const CURRENCY_SYMBOL: Record<string, string> = { USD: "$", GBP: "£", EUR: "€" };

interface Settings {
  openStages: string[];
  selfEmails: Set<string>;
  currency: string;
}

interface DealView {
  id: UUID;
  name: string;
  amount: number | null;
  currency: string;
  org: string | null;
  people: string[];
  stage: string; // display label ("Verbal", "Unstaged")
  status: string;
  note?: string;
  summary?: string; // the living deal summary — current state, maintained by enrichment
  close_label?: string;
  date_label?: string;
  date_value?: string;
}

interface PersonView {
  id: UUID;
  name: string;
  role: string | null;
  org: string | null;
  kind: string | null;
  days: number | null; // days since last contact; null ⇒ never
  last_label: string;
  email: string | null;
  deals: [string, string][];
  note?: string;
  summary?: string; // the living relationship summary — maintained by enrichment
}

function money(amount: number | null, currency: string): string {
  if (amount === null || amount === undefined) return "—";
  const sym = CURRENCY_SYMBOL[currency] ?? "";
  const n = Math.round(amount).toLocaleString("en-US");
  return sym ? `${sym}${n}` : `${n} ${currency}`;
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.floor((Date.now() - then) / 86_400_000));
}

/** Effective recency = the more recent of the derived timeline date and the stored carry-in column.
 *  Timeline wins once a contact-type entry exists; migrated/seeded records with no timeline still show
 *  their stored last_interaction_at (notes-design: the imported-recency carry-in). Either may be null. */
function mostRecent(a: string | null, b: string | null | undefined): string | null {
  if (!a) return b ?? null;
  if (!b) return a;
  return a > b ? a : b;
}

function readSettings(raw: Record<string, unknown> | null | undefined): Settings {
  const s = raw ?? {};
  const pipeline = (s as { pipeline?: unknown }).pipeline;
  const openStages = Array.isArray(pipeline)
    ? (pipeline as string[])
    : Array.isArray((pipeline as { open_stages?: unknown })?.open_stages)
      ? ((pipeline as { open_stages: string[] }).open_stages)
      : DEFAULTS.open_stages;
  const self = (s as { self?: { emails?: unknown } }).self;
  const selfEmails = new Set(
    (Array.isArray(self?.emails) ? (self!.emails as string[]) : DEFAULTS.self_emails).map((e) =>
      e.toLowerCase(),
    ),
  );
  const currency =
    typeof (s as { default_currency?: unknown }).default_currency === "string"
      ? ((s as { default_currency: string }).default_currency)
      : DEFAULTS.default_currency;
  return { openStages, selfEmails, currency };
}

export interface PipelineSummary {
  workspace: string;
  currency: string;
  stats: {
    open_pipeline_value: number;
    open_deals: number;
    relationships: number;
    unstaged_deals: number;
    mixed_currency: boolean;
  };
  stages: { name: string; label: string; deals: DealView[] }[];
  people: PersonView[];
  won: { id: UUID; name: string; amount: number | null; currency: string }[];
  signals: Record<string, Record<string, unknown>>;
  notes: string[];
}

/** Compute the whole dashboard state for a workspace in one pass. Deterministic: same DB → same output
 *  (modulo real time, which only affects recency days). The dashboard skill renders this + a Focus list. */
export async function getPipelineSummary(workspaceId: UUID): Promise<PipelineSummary> {
  const db = getDb();
  const [wsRes, dealsRes, peopleRes, orgsRes, assocRes, contactMap] = await Promise.all([
    db.from("workspace").select("name,settings").eq("id", workspaceId).maybeSingle(),
    db.from("deal").select("*").eq("workspace_id", workspaceId).is("archived_at", null),
    db.from("person").select("*").eq("workspace_id", workspaceId).is("archived_at", null),
    db.from("organization").select("*").eq("workspace_id", workspaceId).is("archived_at", null),
    db.from("association").select("*").eq("workspace_id", workspaceId),
    // per-record recency derived from the timeline (contact-type entries) — maxed with the stored column
    getLatestContactMap(workspaceId),
  ]);
  if (wsRes.error) throw new Error(wsRes.error.message);
  const deals = orThrow(dealsRes) as Deal[];
  const people = orThrow(peopleRes) as Person[];
  const orgs = orThrow(orgsRes) as Organization[];
  const assocs = orThrow(assocRes) as {
    from_type: string; from_id: string; to_type: string; to_id: string; relationship_type: string;
  }[];

  const settings = readSettings(wsRes.data?.settings as Record<string, unknown> | undefined);
  const notes: string[] = [];

  const orgById = new Map(orgs.map((o) => [o.id, o]));
  const personById = new Map(people.map((p) => [p.id, p]));

  // ── resolve the relationship graph once (deal↔people, deal↔org, person↔org) ─────────
  const dealPeople = new Map<string, string[]>();
  const dealOrg = new Map<string, string>();
  const personOrg = new Map<string, string>();
  for (const a of assocs) {
    const ends = [
      { t: a.from_type, id: a.from_id },
      { t: a.to_type, id: a.to_id },
    ];
    const deal = ends.find((e) => e.t === "deal");
    const person = ends.find((e) => e.t === "person");
    const org = ends.find((e) => e.t === "organization");
    if (deal && person) {
      const p = personById.get(person.id);
      if (p?.name) dealPeople.set(deal.id, [...(dealPeople.get(deal.id) ?? []), p.name]);
    }
    if (deal && org) {
      const o = orgById.get(org.id);
      if (o?.name) dealOrg.set(deal.id, o.name);
    }
    if (person && org && !deal) {
      const o = orgById.get(org.id);
      if (o?.name) personOrg.set(person.id, o.name);
    }
  }

  // ── deals: split open vs won, bucket the open ones by stage ─────────────────────────
  const openDeals = deals.filter((d) => d.status === "open");
  const wonDeals = deals.filter((d) => d.status === "won");

  const dealView = (d: Deal): DealView => {
    const closeLabel = d.expected_close_date
      ? `close ${d.expected_close_date}`
      : typeof d.attributes?.target_start === "string"
        ? `start ${d.attributes.target_start as string}`
        : undefined;
    const view: DealView = {
      id: d.id,
      name: d.name ?? "(unnamed deal)",
      amount: d.amount,
      currency: d.currency,
      org: dealOrg.get(d.id) ?? null,
      people: dealPeople.get(d.id) ?? [],
      stage: d.stage ? titleCase(d.stage) : "Unstaged",
      status: titleCase(d.status),
      note: typeof d.attributes?.note === "string" ? (d.attributes.note as string) : undefined,
      summary: d.summary ?? undefined,
    };
    if (closeLabel) view.close_label = closeLabel;
    if (d.expected_close_date) {
      view.date_label = "Close date";
      view.date_value = d.expected_close_date;
    } else if (typeof d.attributes?.target_start === "string") {
      view.date_label = "Start date";
      view.date_value = d.attributes.target_start as string;
    }
    return view;
  };

  // buckets in canonical order: configured open stages, then Unstaged, then any orphan stage
  const buckets = new Map<string, DealView[]>();
  const order: string[] = [...settings.openStages];
  for (const st of settings.openStages) buckets.set(st, []);
  const UNSTAGED = "unstaged";
  for (const d of openDeals) {
    const key = d.stage ?? UNSTAGED;
    if (!buckets.has(key)) {
      // unstaged, or a stage not in the workspace vocabulary → its own bucket, flagged
      buckets.set(key, []);
      order.push(key);
      if (key !== UNSTAGED) notes.push(`Deal "${d.name}" has stage "${d.stage}" which isn't in the pipeline vocabulary.`);
    }
    buckets.get(key)!.push(dealView(d));
  }
  // ensure Unstaged sorts right after the real stages if present
  if (buckets.has(UNSTAGED) && !settings.openStages.includes(UNSTAGED)) {
    const i = order.indexOf(UNSTAGED);
    if (i > -1) order.splice(i, 1);
    order.splice(settings.openStages.length, 0, UNSTAGED);
  }
  const stages = order.map((name) => ({
    name,
    label: name === UNSTAGED ? "Unstaged" : titleCase(name),
    deals: buckets.get(name) ?? [],
  }));

  // ── stats (sum only the workspace currency; flag anything different) ─────────────────
  let openValue = 0;
  let mixed = false;
  for (const d of openDeals) {
    if (d.amount === null) continue;
    if (d.currency === settings.currency) openValue += d.amount;
    else mixed = true;
  }
  if (mixed) notes.push(`Some open deals are in a currency other than ${settings.currency}; they're excluded from the pipeline total.`);
  const unstagedCount = openDeals.filter((d) => !d.stage).length;

  // ── people roster: classified contacts, minus the operator's own record ─────────────
  const isSelf = (p: Person) =>
    [p.primary_email, ...(p.emails ?? [])]
      .filter(Boolean)
      .some((e) => settings.selfEmails.has((e as string).toLowerCase()));
  const roster = people.filter((p) => p.lifecycle_stage && !isSelf(p));

  const dealNameById = new Map(deals.map((d) => [d.id, d]));
  const personDeals = new Map<string, [string, string][]>();
  for (const a of assocs) {
    const ends = [{ t: a.from_type, id: a.from_id }, { t: a.to_type, id: a.to_id }];
    const deal = ends.find((e) => e.t === "deal");
    const person = ends.find((e) => e.t === "person");
    if (deal && person) {
      const d = dealNameById.get(deal.id);
      if (d) {
        const meta = `${d.stage ? d.stage : "unstaged"}${d.amount !== null ? ` · ${money(d.amount, d.currency)}` : ""}`;
        personDeals.set(person.id, [...(personDeals.get(person.id) ?? []), [d.name ?? "(deal)", meta]]);
      }
    }
  }

  const peopleView: PersonView[] = roster.map((p) => {
    const days = daysSince(mostRecent(contactMap.get(p.id) ?? null, p.last_interaction_at));
    return {
      id: p.id,
      name: p.name ?? "(unnamed)",
      role: p.title,
      org: personOrg.get(p.id) ?? null,
      kind: p.lifecycle_stage,
      days,
      last_label: days === null ? "no contact logged" : `${days} day${days === 1 ? "" : "s"}`,
      email: p.primary_email,
      deals: personDeals.get(p.id) ?? [],
      note: typeof p.attributes?.note === "string" ? (p.attributes.note as string) : undefined,
      summary: p.summary ?? undefined,
    };
  });

  // ── recently won ────────────────────────────────────────────────────────────────────
  const wonRecent = wonDeals
    .filter((d) => {
      const days = daysSince(d.closed_at);
      return days === null || days <= RECENTLY_WON_DAYS; // include undated wins rather than hide them
    })
    .map((d) => ({ id: d.id, name: d.name ?? "(deal)", amount: d.amount, currency: d.currency }));

  // ── signals: deterministic anchors for the model's Focus list ───────────────────────
  const lastOpenStage = settings.openStages[settings.openStages.length - 1];
  const signals: Record<string, Record<string, unknown>> = {};
  for (const d of openDeals) {
    if (!d.stage) signals[d.id] = { ...(signals[d.id] ?? {}), is_unstaged: true };
    else if (d.stage === lastOpenStage) signals[d.id] = { ...(signals[d.id] ?? {}), awaiting_close: true };
  }
  for (const p of roster) {
    const days = daysSince(mostRecent(contactMap.get(p.id) ?? null, p.last_interaction_at));
    if (days === null && (p.lifecycle_stage === "lead" || p.lifecycle_stage === "prospect")) {
      signals[p.id] = { ...(signals[p.id] ?? {}), new_no_interaction: true };
    } else if (days !== null && days > QUIET_AFTER_DAYS) {
      signals[p.id] = { ...(signals[p.id] ?? {}), quiet_days: days };
    }
  }

  return {
    workspace: (wsRes.data?.name as string) ?? "Your CRM",
    currency: settings.currency,
    stats: {
      open_pipeline_value: openValue,
      open_deals: openDeals.length,
      relationships: roster.length,
      unstaged_deals: unstagedCount,
      mixed_currency: mixed,
    },
    stages,
    people: peopleView,
    won: wonRecent,
    signals,
    notes,
  };
}
