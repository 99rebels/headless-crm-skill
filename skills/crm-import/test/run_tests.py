#!/usr/bin/env python3
"""
run_tests.py — local test suite for the crm-import skill, BOTH sources, no network needed:

  • Attio migration engine (build_from_attio.py) over fixtures shaped like the real Attio connector
    output (probed from a live workspace) — emailless dedupe, currency parsing, stage mapping +
    never-guess, label preservation, reference-link resolution, dropped cross-pull links, and
    unmapped-attribute reconciliation.
  • CSV import engine (build_import.py) — a GOLDEN regression (the committed sample-contacts.csv +
    sample-mapping.json must still reproduce sample-plan.json exactly) plus a few fact checks, so a
    change to the shared config/vocab can't silently break the deployed CSV path.

    python3 test/run_tests.py         # from the skills/crm-import dir

Exit code is non-zero if any check fails, so it can gate a commit / CI.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import build_from_attio as B   # noqa: E402
import build_import as BI       # noqa: E402
import render_preview as R      # noqa: E402

FIX = os.path.join(HERE, "fixtures")
CONFIG = json.load(open(os.path.join(SKILL, "config.json"), encoding="utf-8"))


def _render(plan_obj) -> str:
    """Render a built plan through the unified renderer (source_kind drives the copy)."""
    return R.render(plan_obj)


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


# ── tiny assertion harness ──────────────────────────────────────────────────────────────
_fails = []
_passes = 0


def check(name, cond, detail=""):
    global _passes
    if cond:
        _passes += 1
    else:
        _fails.append((name, detail))
        print(f"  ✗ {name}" + (f"  — {detail}" if detail else ""))


def by_key(records):
    return {r["key"]: r for r in records}


def find(records, **kw):
    for r in records:
        if all(r.get(k) == v for k, v in kw.items()):
            return r
    return None


# ── the main scenario ─────────────────────────────────────────────────────────────────
def scenario_full():
    print("Scenario: [Attio] full Track-shaped pull (people + companies + deals)")
    config = CONFIG
    mapping = load("mapping.json")
    out = B.build(load("people.json"), load("companies.json"), load("deals.json"), mapping, config)

    plan, digest = out["plan"], out["digest"]
    contacts, orgs, deals = plan["contacts"], plan["organizations"], plan["deals"]
    links = plan["links"]
    ckey = by_key(contacts)
    okey = by_key(orgs)
    dkey = by_key(deals)

    # id → local key, rebuilt from the same natural keys the build uses (for link assertions)
    def cfind(name, email=None):
        return find(contacts, email=email) if email else next((c for c in contacts if c.get("name") == name), None)

    # --- counts / no-false-merge ---
    check("4 people (two distinct emailless 'Dan Hobbs' NOT merged)", len(contacts) == 4,
          f"got {len(contacts)}")
    dans = [c for c in contacts if c.get("name") == "Dan Hobbs"]
    check("both Dan Hobbs kept as separate records", len(dans) == 2, f"got {len(dans)}")
    check("3 companies", len(orgs) == 3, f"got {len(orgs)}")
    check("6 deals", len(deals) == 6, f"got {len(deals)}")

    # --- emails ---
    sara = cfind("Sara Lin")
    check("Sara primary email is work address", sara and sara.get("email") == "sara@nimbus.io",
          str(sara))
    check("Sara's 2nd email kept as alias", sara and sara.get("emails") == ["sara.lin@gmail.com"],
          str(sara and sara.get("emails")))

    # --- unmapped-attribute reconciliation ---
    skipped = digest["skipped_columns"]
    check("unmapped custom people attr reported (linkedin)", "people.linkedin" in skipped, str(skipped))
    check("unmapped custom company attr reported (company_stage)", "companies.company_stage" in skipped,
          str(skipped))
    check("model-overridden attr NOT reported as skipped (categories)",
          "companies.categories" not in skipped, str(skipped))
    check("system slugs never reported (created_at/owner/record_id)",
          not any(s.endswith((".created_at", ".owner", ".record_id", ".created_by")) for s in skipped),
          str(skipped))

    # --- field override actually imported the attr ---
    nimbus = find(orgs, name="Nimbus")
    check("categories imported as a note via override (industry=E-commerce)",
          nimbus and nimbus.get("attributes", {}).get("industry") == "E-commerce", str(nimbus))

    # --- deals: stage mapping, status lockstep, currency, label preservation ---
    d_forte = find(deals, name="Forte Healthcare")
    check("Disqualified → lost (seeded alias)", d_forte and d_forte.get("stage") == "lost", str(d_forte))
    check("lost stage sets status=lost", d_forte and d_forte.get("status") == "lost", str(d_forte))
    check("€ amount parsed to number", d_forte and d_forte.get("amount") == 12000.0, str(d_forte))
    check("€ currency detected as EUR", d_forte and d_forte.get("currency") == "EUR", str(d_forte))
    check("original stage label preserved even when mapped",
          d_forte and d_forte.get("attributes", {}).get("imported_stage") == "Disqualified", str(d_forte))

    d_nimbus = find(deals, name="Nimbus rollout")
    check("Won 🎉 → won (model alias beats config)", d_nimbus and d_nimbus.get("stage") == "won", str(d_nimbus))
    check("won stage sets status=won", d_nimbus and d_nimbus.get("status") == "won", str(d_nimbus))
    check("imported_stage keeps the emoji label", d_nimbus and
          d_nimbus.get("attributes", {}).get("imported_stage") == "Won 🎉", str(d_nimbus))

    d_axe = find(deals, name="Axe pilot")
    check("Demo scheduled → discovery (seeded)", d_axe and d_axe.get("stage") == "discovery", str(d_axe))
    check("open stage keeps status=open", d_axe and d_axe.get("status") == "open", str(d_axe))
    check("$ detected as USD despite EUR default", d_axe and d_axe.get("currency") == "USD", str(d_axe))

    d_live = find(deals, name="Nimbus expansion")
    check("Live → won (seeded alias)", d_live and d_live.get("stage") == "won", str(d_live))

    d_myst = find(deals, name="Unknown-stage deal")
    check("unmapped stage 'Pilot' leaves stage blank (never guessed)",
          d_myst and d_myst.get("stage") is None, str(d_myst))
    check("unmapped stage still preserved as imported_stage",
          d_myst and d_myst.get("attributes", {}).get("imported_stage") == "Pilot", str(d_myst))
    check("£ detected as GBP", d_myst and d_myst.get("currency") == "GBP", str(d_myst))
    check("unmapped-stage note present",
          any("Pilot" in n and "vocab" in n for n in digest["notes"]), str(digest["notes"]))

    d_ghost = find(deals, name="Ghost-link deal")
    check("Lead → discovery (seeded)", d_ghost and d_ghost.get("stage") == "discovery", str(d_ghost))

    # --- links resolved from Attio record_id references ---
    def has_link(from_name_or_deal, to_name, rel, side="c"):
        # resolve names → local keys
        return any(l["relationship_type"] == rel for l in links)  # coarse; refined below

    axe_key = find(orgs, name="Axe")["key"]
    forte_key = find(orgs, name="Forte Healthcare")["key"]
    nimbus_key = find(orgs, name="Nimbus")["key"]
    james_key = cfind("Sara Lin") and None  # placeholder
    james = next(c for c in contacts if c.get("name") == "James McElroy")
    sara_key = sara["key"]

    linkset = {(l["from"], l["to"], l["relationship_type"]) for l in links}
    check("James works_at Axe", (james["key"], axe_key, "works_at") in linkset, str(linkset))
    check("Sara works_at Nimbus", (sara_key, nimbus_key, "works_at") in linkset)
    # both Dans link to their (different) companies
    dan_axe = next(c for c in dans if (c["key"], axe_key, "works_at") in linkset)
    dan_forte = next(c for c in dans if (c["key"], forte_key, "works_at") in linkset)
    check("Dan #1 works_at Axe", dan_axe is not None)
    check("Dan #2 works_at Forte", dan_forte is not None)

    check("deal→account link: Nimbus rollout → Nimbus",
          (d_nimbus["key"], nimbus_key, "account") in linkset, str(linkset))
    check("deal→primary_contact link: Nimbus rollout → Sara",
          (sara_key, d_nimbus["key"], "primary_contact") in linkset, str(linkset))

    # --- dropped cross-pull link (deal_ghost's company not in the pull) ---
    check("ghost deal's account link dropped (company outside pull)",
          (d_ghost["key"], "__any__", "account") not in linkset and
          not any(l["from"] == d_ghost["key"] and l["relationship_type"] == "account" for l in links),
          "ghost account link should not resolve")
    check("dropped-link note present", any("outside this pull" in n for n in digest["notes"]),
          str(digest["notes"]))

    # --- emailless note ---
    check("emailless note present (2 people)",
          any("no email" in n and "2 people" in n for n in digest["notes"]), str(digest["notes"]))

    # --- aggregates ---
    agg = digest["aggregates"]
    check("open pipeline total = 3000+800+1000 = 4800", agg["open_total"] == 4800, str(agg))
    check("won total = 5000+20000 = 25000", agg["won_total"] == 25000, str(agg))

    # --- value-alias chips (translations that fired) ---
    va = {(a["from"], a["to"]) for a in digest["value_aliases"]}
    check("value alias chip: Won 🎉 → won", ("Won 🎉", "won") in va, str(va))
    check("value alias chip: Disqualified → lost", ("Disqualified", "lost") in va, str(va))
    check("no alias chip for unmapped 'Pilot'", not any(f == "Pilot" for f, _ in va), str(va))

    # --- unified renderer picks Attio copy from source_kind ---
    htmlout = _render(out)
    check("[Attio] preview renders with migration copy",
          "Ready to bring your Attio" in htmlout and "How I mapped your Attio fields" in htmlout,
          "Attio copy missing")
    check("[Attio] digest carries source_kind=attio", digest.get("source_kind") == "attio",
          str(digest.get("source_kind")))

    # --- lifecycle derived from deal activity (fills Attio's missing lifecycle) ---
    james = next(c for c in contacts if c.get("name") == "James McElroy")
    check("derive: Sara (Nimbus, won deals) → client", sara.get("lifecycle_stage") == "client",
          str(sara.get("lifecycle_stage")))
    check("derive: James (Axe, open deal) → prospect", james.get("lifecycle_stage") == "prospect",
          str(james.get("lifecycle_stage")))
    check("derive: Dan @Axe (open deal via company) → prospect",
          dan_axe.get("lifecycle_stage") == "prospect", str(dan_axe.get("lifecycle_stage")))
    check("derive: Dan @Forte (only a lost deal) → lead (fallback)",
          dan_forte.get("lifecycle_stage") == "lead", str(dan_forte.get("lifecycle_stage")))
    check("derive: every migrated contact now has a lifecycle (roster-visible)",
          all(c.get("lifecycle_stage") for c in contacts), "some contacts still blank")
    check("derive: a note explains the assignment",
          any("Assigned a lifecycle" in n for n in digest["notes"]), str(digest["notes"]))


def scenario_notes_timeline():
    print("Scenario: [Attio] notes → timeline entries + last-contacted carry-in")
    config = CONFIG
    mapping = load("mapping.json")
    out = B.build(load("people.json"), load("companies.json"), load("deals.json"), mapping, config,
                  load("notes.json"))
    plan, digest = out["plan"], out["digest"]
    entries = plan.get("timeline_entries", [])

    # 3 of the 5 notes attach (orphan-parent + empty-content are dropped)
    check("3 notes folded into the timeline (orphan + empty dropped)", len(entries) == 3,
          f"got {len(entries)}")
    check("digest counts the timeline entries", digest["counts"].get("timeline_entries") == 3,
          str(digest["counts"]))
    check("every entry is type=note, source=migration",
          all(e["type"] == "note" and e["source"] == "migration" for e in entries), str(entries))
    check("every entry carries an external_id (idempotent re-run)",
          all(e.get("external_id") for e in entries), str(entries))
    check("every entry links to exactly one record", all(len(e.get("links", [])) == 1 for e in entries),
          str(entries))

    by_ext = {e["external_id"]: e for e in entries}
    sara = next(c for c in plan["contacts"] if c.get("name") == "Sara Lin")
    nimbus = find(plan["organizations"], name="Nimbus")
    d_nimbus = find(plan["deals"], name="Nimbus rollout")
    check("note on a person resolves to that contact's local key",
          by_ext["note_sara"]["links"][0]["key"] == sara["key"], str(by_ext.get("note_sara")))
    check("note on a company resolves to that org's local key",
          by_ext["note_nimbus_co"]["links"][0]["key"] == nimbus["key"], str(by_ext.get("note_nimbus_co")))
    check("note on a deal resolves to that deal's local key",
          by_ext["note_nimbus_deal"]["links"][0]["key"] == d_nimbus["key"], str(by_ext.get("note_nimbus_deal")))
    check("note body + title + occurred_at carried through",
          by_ext["note_sara"].get("body", "").startswith("Sara is the economic") and
          by_ext["note_sara"].get("subject") == "Intro call" and
          by_ext["note_sara"].get("occurred_at") == "2026-05-10T09:00:00Z", str(by_ext.get("note_sara")))
    check("orphan-parent note produces a reconciliation note",
          any("couldn’t be attached" in n for n in digest["notes"]), str(digest["notes"]))

    # last-contacted carry-in: an Attio interaction field mapped to last_interaction_at
    li_map = {"fields": {"people": {"last_interaction": "person.last_interaction_at"}}, "options": {}}
    li_people = [{"record_id": "per_x", "attributes": {
        "name": "Zoe Vale", "email_addresses": ["zoe@vale.io"],
        "last_interaction": {"interacted_at": "2026-06-20T00:00:00Z"}}}]
    li_out = B.build(li_people, None, None, li_map, config)
    zoe = li_out["plan"]["contacts"][0]
    check("Attio last-contacted carried into last_interaction_at (recency carry-in)",
          zoe.get("last_interaction_at") == "2026-06-20T00:00:00Z", str(zoe))

    # notes-free build must NOT add a timeline_entries key (keeps the no-notes plan shape stable)
    plain = B.build(load("people.json"), load("companies.json"), load("deals.json"), mapping, config)
    check("a notes-free build omits timeline_entries from the plan",
          "timeline_entries" not in plain["plan"], str(list(plain["plan"].keys())))


def scenario_contacts_only():
    print("Scenario: [Attio] contacts-only pull (companies/deals omitted)")
    out = B.build(load("people.json"), None, None, {"options": {}}, CONFIG)
    plan = out["plan"]
    check("contacts-only: 4 people", len(plan["contacts"]) == 4, str(len(plan["contacts"])))
    check("contacts-only: 0 companies", len(plan["organizations"]) == 0)
    check("contacts-only: 0 deals", len(plan["deals"]) == 0)
    # works_at refs point at companies that weren't pulled → all dropped, but no crash
    check("contacts-only: works_at links all dropped (no companies pulled)",
          all(l["relationship_type"] != "works_at" for l in plan["links"]), str(plan["links"]))


def scenario_csv_golden():
    print("Scenario: [CSV] golden regression (deployed path must not drift)")
    csv_path = os.path.join(SKILL, "sample-contacts.csv")
    mapping = json.load(open(os.path.join(SKILL, "sample-mapping.json"), encoding="utf-8"))
    golden = json.load(open(os.path.join(SKILL, "sample-plan.json"), encoding="utf-8"))
    out = BI.build(csv_path, mapping, CONFIG)
    check("committed sample-contacts.csv still reproduces sample-plan.json exactly",
          out == golden, "CSV output drifted from the committed golden — inspect the diff")

    # a few explicit facts (independent of the golden, so a regenerated golden still gets checked)
    plan, digest = out["plan"], out["digest"]
    check("[CSV] some contacts built", len(plan["contacts"]) > 0, str(len(plan["contacts"])))
    won = [d for d in plan["deals"] if d.get("status") == "won"]
    check("[CSV] a 'Closed Won' deal is won+closed (status lockstep)",
          any(d.get("stage") == "won" and d.get("status") == "won" for d in won), str(won))
    check("[CSV] Negotiation → verbal, stays open",
          any(d.get("stage") == "verbal" and d.get("status") == "open" for d in plan["deals"]),
          str(plan["deals"]))
    check("[CSV] preview renders via the unified renderer with CSV copy",
          "Ready to import" in _render(out), "CSV copy missing")


def scenario_units():
    print("Scenario: pure-function units")
    check("detect_currency €", B.detect_currency("€12,000.00", "USD") == "EUR")
    check("detect_currency £", B.detect_currency("£800", "USD") == "GBP")
    check("detect_currency A$ beats $", B.detect_currency("A$1,000", "USD") == "AUD")
    check("detect_currency ISO prefix", B.detect_currency("EUR 1,000", "USD") == "EUR")
    check("detect_currency falls back to default", B.detect_currency("1000", "GBP") == "GBP")
    check("norm_amount strips symbols/commas", B.norm_amount("€12,000.00") == 12000.0)
    check("norm_domain strips scheme/www", B.norm_domain("https://www.Acme.com/x") == "acme.com")


def main():
    for scn in (scenario_full, scenario_notes_timeline, scenario_contacts_only,
                scenario_csv_golden, scenario_units):
        scn()
    print()
    total = _passes + len(_fails)
    if _fails:
        print(f"FAILED — {_passes}/{total} checks passed, {len(_fails)} failed.")
        sys.exit(1)
    print(f"OK — all {total} checks passed.")


if __name__ == "__main__":
    main()
