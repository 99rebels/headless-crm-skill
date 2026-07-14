#!/usr/bin/env python3
"""
build_import.py — turn a CSV + an approved column mapping into a deterministic WRITE PLAN
(what to create) plus a DIGEST (what to show for approval). Stdlib-only.

This is the script-heavy half of the import skill: the model decides the *mapping* (which column
is the email, which is the company); this script mechanically applies it to every row — parsing,
normalising, DEDUPING people/orgs/deals, wiring up the works-at / primary-contact / account links,
and normalising lifecycle/stage values against the workspace vocab. The model never hand-builds the
per-row records, so a 2,000-row file is as reliable as a 5-row one.

The output's `plan` block is the exact set of MCP create/link calls to make once approved; each
record carries a stable local `key` so `links` can reference records before they have real ids.
The `digest` block is what render_preview.py renders for human approval.

Usage:
    python3 build_import.py <file.csv> <mapping.json> [config.json] > plan.json

mapping.json:
{
  "columns": {
    "Full Name": "person.name",
    "Email":     "person.email",
    "Title":     "person.title",
    "Company":   "organization.name",
    "Website":   "organization.domain",
    "Status":    "person.lifecycle_stage",
    "Deal":      "deal.name",
    "Value":     "deal.amount",
    "Stage":     "deal.stage",
    "Notes":     "person.attr.notes",
    "Owner":     "ignore"
  },
  "options": { "default_lifecycle": "lead", "create_deals": true, "default_currency": "USD" },
  "aliases": {
    "lifecycle":  { "evangelist": "client", "sales qualified lead": "prospect" },
    "deal_stage": { "negotiation/review": "verbal", "value proposition": "proposal" }
  }
}

`aliases` is OPTIONAL and model-supplied: for the lifecycle/deal-stage columns, the model maps the
file's ACTUAL values (from the samples it saw) onto the workspace vocab. It's merged OVER config.json's
seed aliases (model wins), so normalisation adapts to any vendor's labels with no static per-vendor
table. Unmapped values are kept as a note and the vocab field left blank (never guessed).

Recognised target fields:
  person.name | person.first_name | person.last_name | person.email | person.emails |
  person.phone | person.title | person.lifecycle_stage
    (first_name + last_name are joined into the person's name when there's no single name column)
  organization.name | organization.domain
  deal.name | deal.stage | deal.status | deal.amount | deal.currency | deal.expected_close_date
  <entity>.attr.<key>   (person.attr.* | organization.attr.* | deal.attr.*)
  ignore
"""

import csv
import io
import json
import os
import re
import sys

DISPLAY_CAP = 20  # per-section item cap in the digest; full set still goes in `plan`


# ── value normalisers ─────────────────────────────────────────────────────────────────
def norm_email(v: str) -> tuple[str, list[str]]:
    """Return (primary, [extras]) from a cell that may list several emails."""
    parts = [p.strip().lower() for p in re.split(r"[;,/]", v) if p.strip()]
    parts = [p for p in parts if "@" in p]
    return (parts[0], parts[1:]) if parts else ("", [])


def norm_domain(v: str) -> str:
    v = v.strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    v = v.split("/")[0].split("?")[0]
    return v


def norm_amount(v: str):
    cleaned = re.sub(r"[^0-9.\-]", "", v.replace(",", ""))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else None
    except ValueError:
        return None


def norm_vocab(v: str, allowed: list[str], aliases: dict) -> tuple[str, bool]:
    """Map a raw label to a vocab term. Returns (term_or_raw, matched?)."""
    key = v.strip().lower()
    if key in aliases:
        key = aliases[key].lower()
    if key in [a.lower() for a in allowed]:
        return key, True
    return v.strip(), False


def initials_of(name: str) -> str:
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    return ("".join(w[0] for w in words[:2])).upper() if words else "?"


# Human labels for the "how I read your columns" card (internal field key → what the user sees).
FIELD_LABELS = {
    "person.name": "Contact name", "person.first_name": "Contact name", "person.last_name": "Contact name",
    "person.email": "Email", "person.emails": "Email", "person.phone": "Phone", "person.title": "Title",
    "person.lifecycle_stage": "Lifecycle",
    "organization.name": "Organisation", "organization.domain": "Domain",
    "deal.name": "Deal", "deal.stage": "Deal stage", "deal.status": "Deal status",
    "deal.amount": "Amount", "deal.currency": "Currency", "deal.expected_close_date": "Expected close",
}
FIELD_ORDER = ["Contact name", "Email", "Title", "Phone", "Lifecycle", "Organisation", "Domain",
               "Deal", "Amount", "Deal stage", "Deal status", "Currency", "Expected close", "Note"]
CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "AUD": "A$", "CAD": "C$", "NZD": "NZ$"}


def field_label(target: str) -> str:
    if target in FIELD_LABELS:
        return FIELD_LABELS[target]
    if ".attr." in target:
        return "Note"
    return target


def fmt_money(currency: str, amount: float) -> str:
    sym = CURRENCY_SYMBOLS.get((currency or "USD").upper())
    return f"{sym}{amount:,.0f}" if sym else f"{(currency or 'USD')} {amount:,.0f}"


# ── the build ─────────────────────────────────────────────────────────────────────────
def build(csv_path: str, mapping: dict, config: dict) -> dict:
    cols = mapping.get("columns", {})
    opts = mapping.get("options", {})
    create_deals = opts.get("create_deals", True)
    default_lifecycle = opts.get("default_lifecycle")
    default_currency = opts.get("default_currency", config.get("default_currency", "USD"))

    vocab = config.get("vocab", {})
    life_ok = vocab.get("lifecycle_stages", [])
    stage_ok = vocab.get("deal_stages", [])

    # Value aliases (export label → workspace vocab). config.json is a SEED for common cases; the
    # model adds per-file aliases in mapping.aliases (from the actual sample values it saw), and
    # those WIN on conflict — so normalisation adapts to any vendor's vocabulary, no static
    # per-vendor tables to maintain.
    def merge_aliases(kind: str) -> dict:
        base = {k.lower(): v for k, v in config.get("aliases", {}).get(kind, {}).items()}
        over = {k.lower(): v for k, v in mapping.get("aliases", {}).get(kind, {}).items()}
        return {**base, **over}

    life_alias = merge_aliases("lifecycle")
    stage_alias = merge_aliases("deal_stage")

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    try:
        delimiter = csv.Sniffer().sniff(raw[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    dict_reader = csv.DictReader(io.StringIO(raw), delimiter=delimiter)
    csv_headers = dict_reader.fieldnames or []
    rows = list(dict_reader)

    # Deduped stores keyed by a natural key; values accumulate across rows.
    people: dict = {}
    orgs: dict = {}
    deals: dict = {}
    links: set = set()
    notes: set = set()
    translations: dict = {}  # raw label (lower) → (raw, vocab term); for the "translated" chips
    rows_reviewed = 0

    # a column is "left out" if it's mapped to ignore OR the mapping omits it entirely — check
    # against the real CSV header so a forgotten column is surfaced, not silently dropped.
    unmapped = [h for h in csv_headers if cols.get(h) in (None, "", "ignore")]

    def put_attr(bag: dict, target: str, val: str):
        # target like "person.attr.notes"
        key = target.split(".attr.", 1)[1]
        bag.setdefault("attributes", {})[key] = val

    for row in rows:
        if not any((v or "").strip() for v in row.values()):
            continue
        rows_reviewed += 1
        p: dict = {}
        o: dict = {}
        d: dict = {}

        for col, target in cols.items():
            if not target or target == "ignore":
                continue
            val = (row.get(col) or "").strip()
            if not val:
                continue
            if target == "person.name":
                p["name"] = val
            elif target == "person.first_name":
                p["_first"] = val
            elif target == "person.last_name":
                p["_last"] = val
            elif target == "person.email":
                pri, extra = norm_email(val)
                if pri:
                    p["email"] = pri
                    p.setdefault("emails", []).extend(extra)
            elif target == "person.emails":
                pri, extra = norm_email(val)
                p.setdefault("emails", []).extend(([pri] if pri else []) + extra)
            elif target == "person.phone":
                p["phone"] = val
            elif target == "person.title":
                p["title"] = val
            elif target == "person.lifecycle_stage":
                term, ok = norm_vocab(val, life_ok, life_alias)
                if ok:
                    p["lifecycle_stage"] = term
                    if val.strip().lower() != term.lower():
                        translations.setdefault(val.strip().lower(), (val.strip(), term))
                else:
                    put_attr(p, "person.attr.imported_status", val)
                    notes.add(f"Lifecycle value “{val}” isn’t in your vocab — kept as a note, stage left blank.")
            elif target == "organization.name":
                o["name"] = val
            elif target == "organization.domain":
                o["domain"] = norm_domain(val)
            elif target == "deal.name":
                d["name"] = val
            elif target == "deal.stage":
                term, ok = norm_vocab(val, stage_ok, stage_alias)
                if ok:
                    d["stage"] = term
                    if val.strip().lower() != term.lower():
                        translations.setdefault(val.strip().lower(), (val.strip(), term))
                else:
                    put_attr(d, "deal.attr.imported_stage", val)
                    notes.add(f"Deal stage “{val}” isn’t in your vocab — kept as a note, stage left blank.")
            elif target == "deal.status":
                s = val.strip().lower()
                d["status"] = s if s in ("open", "won", "lost") else "open"
            elif target == "deal.amount":
                amt = norm_amount(val)
                if amt is not None:
                    d["amount"] = amt
            elif target == "deal.currency":
                d["currency"] = val.strip().upper()[:3]
            elif target == "deal.expected_close_date":
                d["expected_close_date"] = val
            elif target.startswith("person.attr."):
                put_attr(p, target, val)
            elif target.startswith("organization.attr."):
                put_attr(o, target, val)
            elif target.startswith("deal.attr."):
                put_attr(d, target, val)

        # join separate first/last name columns into a single name (only if no full-name column)
        first, last = p.pop("_first", None), p.pop("_last", None)
        if not p.get("name"):
            joined = " ".join(x for x in [first, last] if x)
            if joined:
                p["name"] = joined

        # infer an org domain from the person's email if the org has none (light, flagged)
        if o.get("name") and not o.get("domain") and p.get("email") and "@" in p["email"]:
            dom = p["email"].split("@", 1)[1]
            if dom not in config.get("public_email_domains", []):
                o["domain"] = dom

        # a won/lost STAGE means the deal is actually closed — keep status in lockstep (the core
        # stamps closed_at from status, and the dashboard's open-pipeline value filters on status).
        if create_deals and d.get("stage") in ("won", "lost") and not d.get("status"):
            d["status"] = d["stage"]

        p_key = merge_person(people, p, default_lifecycle)
        o_key = merge_org(orgs, o)
        d_key = merge_deal(deals, d, default_currency) if create_deals else None

        if p_key and o_key:
            links.add((p_key, o_key, "works_at"))
        if p_key and d_key:
            links.add((p_key, d_key, "primary_contact"))
        if d_key and o_key:
            links.add((d_key, o_key, "account"))

    # "How I read your columns" — group source columns by the CRM field they fill; left-out
    # columns (ignore/omitted) are shown struck-through in the card, not as a warning.
    groups: dict = {}
    for col, target in cols.items():
        if not target or target == "ignore":
            continue
        groups.setdefault(field_label(target), []).append(col)
    mapping_rows = [
        {"sources": groups[lbl], "field": lbl}
        for lbl in sorted(groups, key=lambda l: FIELD_ORDER.index(l) if l in FIELD_ORDER else len(FIELD_ORDER))
    ]
    value_aliases = [{"from": raw, "to": term} for (raw, term) in translations.values()]

    return assemble(people, orgs, deals, links, notes, rows_reviewed,
                    mapping_rows, unmapped, value_aliases, default_currency,
                    os.path.basename(csv_path))


# ── dedupe/merge helpers (natural keys) ─────────────────────────────────────────────────
def _merge_scalar(dst: dict, src: dict, fields: list[str]):
    for fld in fields:
        if src.get(fld) and not dst.get(fld):
            dst[fld] = src[fld]


def _merge_list(dst: dict, src: dict, fld: str):
    if src.get(fld):
        merged = dict.fromkeys((dst.get(fld) or []) + src[fld])  # order-preserving unique
        dst[fld] = [x for x in merged if x]


def _merge_attrs(dst: dict, src: dict):
    if src.get("attributes"):
        bag = dst.setdefault("attributes", {})
        for k, v in src["attributes"].items():
            bag.setdefault(k, v)  # first non-empty wins; a later dup row can't clobber


def merge_person(store: dict, p: dict, default_lifecycle) -> str | None:
    if not (p.get("name") or p.get("email")):
        return None
    key = ("email:" + p["email"]) if p.get("email") else ("name:" + p["name"].strip().lower())
    if key not in store:
        rec = {"key": f"c{len(store)}"}
        if default_lifecycle and not p.get("lifecycle_stage"):
            rec["lifecycle_stage"] = default_lifecycle
        store[key] = rec
    dst = store[key]
    _merge_scalar(dst, p, ["name", "email", "phone", "title", "lifecycle_stage"])
    _merge_list(dst, p, "emails")
    _merge_attrs(dst, p)
    # drop the primary out of the emails alias list if it slipped in
    if dst.get("emails") and dst.get("email"):
        dst["emails"] = [e for e in dst["emails"] if e != dst["email"]] or None
        if dst["emails"] is None:
            del dst["emails"]
    return dst["key"]


def merge_org(store: dict, o: dict) -> str | None:
    if not (o.get("name") or o.get("domain")):
        return None
    key = ("dom:" + o["domain"]) if o.get("domain") else ("name:" + o["name"].strip().lower())
    if key not in store:
        store[key] = {"key": f"o{len(store)}"}
    dst = store[key]
    _merge_scalar(dst, o, ["name", "domain"])
    _merge_attrs(dst, o)
    return dst["key"]


def merge_deal(store: dict, d: dict, default_currency: str) -> str | None:
    if not (d.get("name") or d.get("amount")):
        return None
    key = ("name:" + d["name"].strip().lower()) if d.get("name") else f"row:{len(store)}"
    if key not in store:
        store[key] = {"key": f"d{len(store)}"}
    dst = store[key]
    # merge BEFORE defaulting, so an explicit status/currency isn't blocked by a pre-set default
    _merge_scalar(dst, d, ["name", "stage", "status", "expected_close_date", "currency"])
    if d.get("amount") is not None and dst.get("amount") is None:
        dst["amount"] = d["amount"]
    _merge_attrs(dst, d)
    dst.setdefault("currency", default_currency)
    dst.setdefault("status", "open")
    return dst["key"]


# ── assemble plan + digest ──────────────────────────────────────────────────────────────
def assemble(people, orgs, deals, links, notes, rows_reviewed,
             mapping_rows, skipped_columns, value_aliases, default_currency, source_file) -> dict:
    contacts = list(people.values())
    organizations = list(orgs.values())
    deal_list = list(deals.values())
    link_list = [{"from": a, "to": b, "relationship_type": r} for (a, b, r) in sorted(links)]

    def contact_row(c):
        return {
            "name": c.get("name") or c.get("email") or "—",
            "initials": initials_of(c.get("name") or c.get("email") or "?"),
            "title": c.get("title") or "",
            "email": c.get("email") or "",
            "lifecycle": (c.get("lifecycle_stage") or "").capitalize(),
        }

    def org_row(o):
        nm = o.get("name") or o.get("domain") or "—"
        return {"name": nm, "initial": (nm.strip()[:1].upper() if nm.strip() else "?"), "domain": o.get("domain") or ""}

    def deal_row(d):
        amt = d.get("amount")
        status = d.get("status", "open")
        stage = (d.get("stage") or "").capitalize()
        return {
            "name": d.get("name") or "(unnamed deal)",
            "amount_display": fmt_money(d.get("currency", default_currency), amt) if amt is not None else "",
            "stage": stage or (status.capitalize() if status in ("won", "lost") else "Unstaged"),
            "status": status,
        }

    deals_sorted = sorted(deal_list, key=lambda d: (d.get("amount") is None, -(d.get("amount") or 0)))
    open_total = sum(d.get("amount") or 0 for d in deal_list if d.get("status") == "open")
    won_total = sum(d.get("amount") or 0 for d in deal_list if d.get("status") == "won")
    people_with_deal = len({a for (a, b, r) in links if r == "primary_contact"})

    digest = {
        "rows_reviewed": rows_reviewed,
        "source_file": source_file,
        "counts": {"contacts": len(contacts), "organizations": len(organizations),
                   "deals": len(deal_list), "links": len(link_list)},
        "mapping": mapping_rows,
        "skipped_columns": skipped_columns,
        "value_aliases": value_aliases,
        "contacts": [contact_row(c) for c in contacts[:DISPLAY_CAP]],
        "organizations": [org_row(o) for o in organizations[:DISPLAY_CAP]],
        "deals": [deal_row(d) for d in deals_sorted[:DISPLAY_CAP]],
        "aggregates": {
            "open_total": open_total, "won_total": won_total,
            "open_display": fmt_money(default_currency, open_total),
            "won_display": fmt_money(default_currency, won_total),
            "people_with_deal": people_with_deal,
        },
        "notes": sorted(notes),
    }
    return {
        "rows_reviewed": rows_reviewed,
        "plan": {
            "contacts": contacts,
            "organizations": organizations,
            "deals": deal_list,
            "links": link_list,
        },
        "digest": digest,
    }


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("usage: build_import.py <file.csv> <mapping.json> [config.json]")
    csv_path, mapping_path = sys.argv[1], sys.argv[2]
    mapping = json.loads(open(mapping_path, encoding="utf-8").read())
    config = json.loads(open(sys.argv[3], encoding="utf-8").read()) if len(sys.argv) > 3 else {}
    print(json.dumps(build(csv_path, mapping, config), indent=2))


if __name__ == "__main__":
    main()
