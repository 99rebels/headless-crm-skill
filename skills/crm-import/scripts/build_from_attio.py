#!/usr/bin/env python3
"""
build_from_attio.py — turn records pulled from a connected Attio workspace into a deterministic
WRITE PLAN (what to create) plus a DIGEST (what to show for approval). Stdlib-only.

This is the script-heavy half of the Attio migration. The MODEL's only real judgment is the
**stage mapping** (Attio pipelines are named anything — "Demo scheduled", "Live", "Won 🎉"); this
script mechanically does everything else: flattening Attio's values, parsing money/emails/domains,
DEDUPING (by email/domain, falling back to Attio's stable record_id — never by name, so two
different emailless "CEO" records can't be wrongly merged), resolving Attio's record_id references
into works-at / primary-contact / account LINKS, and normalising stages against the workspace vocab.

It emits the SAME `plan` + `digest` shape build_import.py does, so the SAME preview
(render_preview.py) and the SAME server-side write (the bulk_import MCP tool) are reused unchanged.

  ⚠️ DUPLICATION NOTE: the normalisers / dedupe / assemble here are deliberately COPIED from
  build_import.py — kept as a second engine (not refactored into build_import) so the deployed,
  tested CSV path stays byte-for-byte. The one renderer (render_preview.py) is shared. A later,
  clock-free pass can factor these helpers into a shared module. See docs/crm-migration.md.

Design principles (see docs/crm-migration.md):
  • Structure first, names second, human last. Won/lost is the classification that matters; the
    model proposes stage_aliases informed by Attio's stage ORDER + win-ish titles, and the human
    approves in the preview. Open-stage granularity is low-stakes (it all buckets as open pipeline).
  • Never destroy the source label. Whatever a stage maps to, the original Attio title is ALSO kept
    as `deal.attr.imported_stage` — nothing is lost, the user can re-segment later.
  • Never guess. A stage with no vocab home is kept as a note and the field left blank (flagged).
  • Don't expand our model to mirror Attio. Only the three spine objects + standard fields import;
    anything unmapped is reported (reconciliation), not silently dropped.

Usage:
    python3 build_from_attio.py --people people.json --companies companies.json \
        --deals deals.json --mapping mapping.json [--config config.json] > plan.json

Each of people/companies/deals.json is a JSON array of records as the Attio MCP connector returns
them: { "record_id": "...", "attributes": { <slug>: <flattened value>, ... } }. Any file may be
omitted (e.g. a contacts-only migration).

mapping.json (model-supplied — most of it is OPTIONAL; defaults cover the standard Attio schema):
{
  "stage_aliases":     { "won 🎉": "won", "live": "won", "onboarding scheduled": "won",
                         "demo scheduled": "discovery", "in progress": "discovery",
                         "lead": "discovery", "lost": "lost", "disqualified": "lost" },
  "lifecycle_aliases": { "customer": "client" },
  "fields": { "people": { "linkedin": "person.attr.linkedin" },
              "companies": { "categories": "organization.attr.industry" } },
  "options": { "default_currency": "EUR", "default_lifecycle": null }
}
`stage_aliases` is the important one and is the model's job. `fields` only ADDS to / overrides the
built-in defaults (below) — you never re-declare the standard slugs.
"""

import argparse
import json
import re
import sys

DISPLAY_CAP = 20  # per-section item cap in the digest; full set still goes in `plan`

# Attio system/derived slugs we silently ignore (never reported as "dropped data").
SYSTEM_SLUGS = {
    "record_id", "created_at", "created_by", "updated_at", "updated_by", "owner",
    "avatar_url", "logo_url", "associated_deals", "team",
}

# Built-in field map for Attio's STANDARD object slugs → our target fields. The model's mapping.fields
# is merged OVER this (model wins), so custom attributes can be pulled into notes without re-declaring
# the standard ones. "link.*" targets are resolved from Attio record-reference values.
DEFAULT_FIELDS = {
    "people": {
        "name": "person.name",
        "email_addresses": "person.email",
        "job_title": "person.title",
        "phone_numbers": "person.phone",
        "company": "link.works_at",
    },
    "companies": {
        "name": "organization.name",
        "domains": "organization.domain",
    },
    "deals": {
        "name": "deal.name",
        "value": "deal.amount",
        "stage": "deal.stage",
        "associated_company": "link.account",
        "associated_people": "link.primary_contact",
    },
}


# ── value normalisers (copied from build_import.py) ─────────────────────────────────────
def norm_domain(v: str) -> str:
    v = str(v).strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    return v.split("/")[0].split("?")[0]


CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "AUD": "A$", "CAD": "C$", "NZD": "NZ$"}
# symbol → ISO, longest-symbol first so "A$"/"C$"/"NZ$" beat a bare "$"
_SYMBOL_TO_ISO = sorted(
    ((sym, iso) for iso, sym in CURRENCY_SYMBOLS.items()),
    key=lambda kv: -len(kv[0]),
)


def detect_currency(v: str, default: str) -> str:
    """Attio returns money pre-formatted, e.g. '€12,000.00' / 'US$1,000'. Read the currency off it."""
    s = str(v).strip()
    m = re.match(r"^([A-Z]{3})[\s0-9]", s)  # explicit ISO prefix, e.g. "EUR 1,000"
    if m:
        return m.group(1)
    for sym, iso in _SYMBOL_TO_ISO:
        if sym in s:
            return iso
    return (default or "USD").upper()


def norm_amount(v) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", str(v).replace(",", ""))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else None
    except ValueError:
        return None


def norm_vocab(v: str, allowed: list, aliases: dict) -> tuple[str, bool]:
    """Map a raw label to a vocab term. Returns (term_or_raw, matched?)."""
    key = str(v).strip().lower()
    if key in aliases:
        key = str(aliases[key]).lower()
    if key in [a.lower() for a in allowed]:
        return key, True
    return str(v).strip(), False


def initials_of(name: str) -> str:
    words = [w for w in re.split(r"\s+", str(name).strip()) if w]
    return ("".join(w[0] for w in words[:2])).upper() if words else "?"


def fmt_money(currency: str, amount: float) -> str:
    sym = CURRENCY_SYMBOLS.get((currency or "USD").upper())
    return f"{sym}{amount:,.0f}" if sym else f"{(currency or 'USD')} {amount:,.0f}"


# ── flattening Attio's connector shapes into simple scalars/lists ───────────────────────
def _as_list(v) -> list:
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def _first_str(v) -> str:
    for item in _as_list(v):
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):  # e.g. email objects; be defensive
            for k in ("email_address", "phone_number", "value"):
                if item.get(k):
                    return str(item[k]).strip()
    return ""


def _ref_ids(v) -> list:
    """Attio record-reference value(s) → list of referenced record_ids."""
    out = []
    for item in _as_list(v):
        if isinstance(item, dict) and item.get("record_id"):
            out.append(item["record_id"])
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _iso(v) -> str:
    """Pull an ISO timestamp out of an Attio value (a plain string, or an interaction object)."""
    for item in _as_list(v):
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            for k in ("interacted_at", "last_interacted_at", "timestamp", "value"):
                if item.get(k):
                    return str(item[k]).strip()
    return ""


# Attio note parent-object names → the id_map bucket they resolve against.
_PARENT_MAP = {
    "people": "people", "person": "people",
    "companies": "companies", "company": "companies",
    "deals": "deals", "deal": "deals",
}


# ── the build ───────────────────────────────────────────────────────────────────────────
FIELD_LABELS = {
    "person.name": "Contact name", "person.email": "Email", "person.emails": "Email",
    "person.phone": "Phone", "person.title": "Title", "person.lifecycle_stage": "Lifecycle",
    "person.last_interaction_at": "Last contacted",
    "organization.name": "Organisation", "organization.domain": "Domain",
    "organization.last_interaction_at": "Last contacted",
    "deal.name": "Deal", "deal.stage": "Deal stage", "deal.amount": "Amount",
    "deal.currency": "Currency",
    "link.works_at": "Company (link)", "link.account": "Company (link)",
    "link.primary_contact": "Contact (link)",
}
FIELD_ORDER = ["Contact name", "Email", "Title", "Phone", "Lifecycle", "Last contacted",
               "Organisation", "Domain", "Company (link)", "Contact (link)", "Deal", "Amount",
               "Deal stage", "Currency", "Note"]


def field_label(target: str) -> str:
    if target in FIELD_LABELS:
        return FIELD_LABELS[target]
    if ".attr." in target:
        return "Note"
    return target


def _put_attr(bag: dict, target: str, val):
    bag.setdefault("attributes", {})[target.split(".attr.", 1)[1]] = val


def build(people_recs, company_recs, deal_recs, mapping, config, note_recs=None) -> dict:
    opts = mapping.get("options", {})
    default_currency = opts.get("default_currency", config.get("default_currency", "USD"))
    default_lifecycle = opts.get("default_lifecycle")

    vocab = config.get("vocab", {})
    life_ok = vocab.get("lifecycle_stages", [])
    stage_ok = vocab.get("deal_stages", [])

    def merged_aliases(kind_cfg, kind_map):
        base = {k.lower(): v for k, v in config.get("aliases", {}).get(kind_cfg, {}).items()}
        over = {k.lower(): v for k, v in mapping.get(kind_map, {}).items()}
        return {**base, **over}

    stage_alias = merged_aliases("deal_stage", "stage_aliases")
    life_alias = merged_aliases("lifecycle", "lifecycle_aliases")

    def fields_for(obj):
        m = dict(DEFAULT_FIELDS.get(obj, {}))
        m.update(mapping.get("fields", {}).get(obj, {}))
        return m

    # stores keyed by natural key; id_map: attio record_id → local key (for link resolution)
    people, orgs, deals = {}, {}, {}
    id_map = {"people": {}, "companies": {}, "deals": {}}
    links = set()
    notes = set()
    translations = {}          # raw stage title (lower) → (raw, vocab term) for the "translated" chips
    used_fields = {}           # field label → set of source slugs that filled it (mapping card)
    unmapped_slugs = set()     # non-system slugs seen in data but not mapped (reconciliation)
    pending_ref = []           # (from_key, ref_attio_ids, relationship, target_type) resolved after ingest
    emailless = 0

    def note_field(target, slug):
        used_fields.setdefault(field_label(target), set()).add(slug)

    # ---- people ----
    fmap = fields_for("people")
    for rec in people_recs or []:
        rid = rec.get("record_id")
        attrs = rec.get("attributes", {}) or {}
        p, ref_org = {}, None
        for slug, val in attrs.items():
            if val in (None, "", []):
                continue
            target = fmap.get(slug)
            if not target:
                if slug not in SYSTEM_SLUGS:
                    unmapped_slugs.add(f"people.{slug}")
                continue
            if target == "person.name":
                p["name"] = _first_str(val) or (str(val).strip() if isinstance(val, str) else "")
            elif target == "person.email":
                emails = [e.strip().lower() for e in _as_list(val)
                          if isinstance(e, str) and "@" in e]
                if emails:
                    p["email"] = emails[0]
                    if len(emails) > 1:
                        p["emails"] = emails[1:]
            elif target == "person.phone":
                p["phone"] = _first_str(val)
            elif target == "person.title":
                p["title"] = _first_str(val) or (str(val).strip() if isinstance(val, str) else "")
            elif target == "person.lifecycle_stage":
                term, ok = norm_vocab(_first_str(val) or str(val), life_ok, life_alias)
                if ok:
                    p["lifecycle_stage"] = term
                    if str(val).strip().lower() != term.lower():
                        translations.setdefault(str(val).strip().lower(), (str(val).strip(), term))
                else:
                    _put_attr(p, "person.attr.imported_status", str(val).strip())
                    notes.add(f"Lifecycle value “{str(val).strip()}” isn’t in your vocab — kept as a note.")
            elif target == "link.works_at":
                ids = _ref_ids(val)
                ref_org = ids[0] if ids else None
            elif target == "person.last_interaction_at":
                iso = _iso(val)  # Attio "last contacted" → carry-in recency (no timeline to derive from yet)
                if iso:
                    p["last_interaction_at"] = iso
            elif target.startswith("person.attr."):
                _put_attr(p, target, val if isinstance(val, str) else _first_str(val) or json.dumps(val))
            note_field(target, slug)
        if not (p.get("name") or p.get("email")):
            continue
        if not p.get("email"):
            emailless += 1
        key = _merge(people, p, natural_key(p, "email", rid), "c")
        id_map["people"][rid] = key
        if ref_org:
            pending_ref.append((key, [ref_org], "works_at", "companies"))
        if default_lifecycle and not p.get("lifecycle_stage"):
            people[key].setdefault("lifecycle_stage", default_lifecycle)

    # ---- companies ----
    fmap = fields_for("companies")
    for rec in company_recs or []:
        rid = rec.get("record_id")
        attrs = rec.get("attributes", {}) or {}
        o = {}
        for slug, val in attrs.items():
            if val in (None, "", []):
                continue
            target = fmap.get(slug)
            if not target:
                if slug not in SYSTEM_SLUGS:
                    unmapped_slugs.add(f"companies.{slug}")
                continue
            if target == "organization.name":
                o["name"] = _first_str(val) or (str(val).strip() if isinstance(val, str) else "")
            elif target == "organization.domain":
                dom = _first_str(val)
                if dom:
                    o["domain"] = norm_domain(dom)
            elif target == "organization.last_interaction_at":
                iso = _iso(val)
                if iso:
                    o["last_interaction_at"] = iso
            elif target.startswith("organization.attr."):
                _put_attr(o, target, val if isinstance(val, str) else _first_str(val) or json.dumps(val))
            note_field(target, slug)
        if not (o.get("name") or o.get("domain")):
            continue
        key = _merge(orgs, o, natural_key(o, "domain", rid), "o")
        id_map["companies"][rid] = key

    # ---- deals ----
    fmap = fields_for("deals")
    for rec in deal_recs or []:
        rid = rec.get("record_id")
        attrs = rec.get("attributes", {}) or {}
        d, ref_company, ref_people = {}, None, []
        for slug, val in attrs.items():
            if val in (None, "", []):
                continue
            target = fmap.get(slug)
            if not target:
                if slug not in SYSTEM_SLUGS:
                    unmapped_slugs.add(f"deals.{slug}")
                continue
            if target == "deal.name":
                d["name"] = _first_str(val) or (str(val).strip() if isinstance(val, str) else "")
            elif target == "deal.amount":
                amt = norm_amount(val)
                if amt is not None:
                    d["amount"] = amt
                    d.setdefault("currency", detect_currency(val, default_currency))
            elif target == "deal.stage":
                raw = _first_str(val) or str(val).strip()
                # Always preserve the original Attio stage label — never destroy it.
                if raw:
                    _put_attr(d, "deal.attr.imported_stage", raw)
                term, ok = norm_vocab(raw, stage_ok, stage_alias)
                if ok:
                    d["stage"] = term
                    if raw.lower() != term.lower():
                        translations.setdefault(raw.lower(), (raw, term))
                elif raw:
                    notes.add(f"Deal stage “{raw}” isn’t in your vocab — kept as a note, stage left blank.")
            elif target == "link.account":
                ids = _ref_ids(val)
                ref_company = ids[0] if ids else None
            elif target == "link.primary_contact":
                ref_people = _ref_ids(val)
            elif target.startswith("deal.attr."):
                _put_attr(d, target, val if isinstance(val, str) else _first_str(val) or json.dumps(val))
            note_field(target, slug)
        if not (d.get("name") or d.get("amount") is not None):
            continue
        # a won/lost STAGE means the deal is actually closed — keep status in lockstep (the core
        # stamps closed_at from status; the dashboard's open-pipeline value filters on status).
        if d.get("stage") in ("won", "lost"):
            d["status"] = d["stage"]
        else:
            d.setdefault("status", "open")
        d.setdefault("currency", default_currency)
        key = _merge(deals, d, f"rid:{rid}", "d")  # deals: always dedupe by record_id, never name
        id_map["deals"][rid] = key
        if ref_company:
            pending_ref.append((key, [ref_company], "account", "companies"))
        for pid in ref_people:
            pending_ref.append((pid, [key], "primary_contact_rev", "self"))  # person→deal, resolved below
        # also account link company↔ (handled via account above)

    # ---- resolve links from Attio references ----
    dropped_links = 0
    for from_key, ref_ids, rel, target_type in pending_ref:
        if rel == "works_at":
            ok = [id_map["companies"].get(r) for r in ref_ids]
            for org_key in filter(None, ok):
                links.add((from_key, org_key, "works_at"))
            dropped_links += sum(1 for r in ref_ids if not id_map["companies"].get(r))
        elif rel == "account":
            ok = [id_map["companies"].get(r) for r in ref_ids]
            for org_key in filter(None, ok):
                links.add((from_key, org_key, "account"))
            dropped_links += sum(1 for r in ref_ids if not id_map["companies"].get(r))
        elif rel == "primary_contact_rev":
            # from_key is an Attio person record_id here; ref_ids holds the deal's local key
            person_key = id_map["people"].get(from_key)
            if person_key:
                for deal_key in ref_ids:
                    links.add((person_key, deal_key, "primary_contact"))
            else:
                dropped_links += 1

    # ---- notes → timeline entries (fold Attio notes into the unified timeline) ----
    # Each note attaches to the record it was written on, resolved Attio record_id → local key.
    # source=migration + external_id=note_id makes a re-run idempotent (bulk_import skips dupes).
    timeline_entries = []
    notes_dropped = 0
    for rec in note_recs or []:
        parent_obj = _PARENT_MAP.get(str(rec.get("parent_object", "")).strip().lower())
        parent_rid = rec.get("parent_record_id") or rec.get("record_id")
        key = id_map.get(parent_obj, {}).get(parent_rid) if parent_obj else None
        content = str(rec.get("content") or rec.get("body") or rec.get("plaintext") or "").strip()
        title = str(rec.get("title") or "").strip()
        if not key or not (content or title):
            notes_dropped += 1
            continue
        entry = {"type": "note", "source": "migration", "links": [{"key": key}]}
        ext = rec.get("note_id") or rec.get("id")
        if ext:
            entry["external_id"] = str(ext)
        if title:
            entry["subject"] = title
        if content:
            entry["body"] = content  # migration notes are user-authored → full text is fine to store
        if rec.get("created_at"):
            entry["occurred_at"] = str(rec["created_at"])
        timeline_entries.append(entry)
    if notes_dropped:
        notes.add(f"{notes_dropped} note(s) couldn’t be attached — their parent record wasn’t in this "
                  "pull. Re-run pulling all objects to capture them.")

    # ---- derive a lifecycle for people who have none (Attio has no lifecycle field) ----
    # Roster/relationships in the dashboard only count contacts WITH a lifecycle (core/summary.ts),
    # so without this a whole migrated book of people is invisible. Derive it from deal activity:
    # a person tied to a WON deal → client, an OPEN deal → prospect, else → lead (or the default).
    # "Tied to" = directly (primary_contact) OR via their company (works_at → a deal on that org).
    derived = _derive_lifecycles(people, deals, links, default_lifecycle)
    if derived:
        notes.add(f"Assigned a lifecycle to {derived} contact(s) from their deal activity "
                  "(won → client, open → prospect, otherwise lead) — Attio has no lifecycle field. "
                  "Adjust any that look off before approving.")

    if emailless:
        notes.add(f"{emailless} {'person' if emailless == 1 else 'people'} had no email address — "
                  "deduped by Attio identity, not email (so none were wrongly merged).")
    if dropped_links:
        notes.add(f"{dropped_links} link(s) pointed at a record outside this pull — skipped. "
                  "Re-run pulling all objects to capture them.")

    mapping_rows = [
        {"sources": sorted(used_fields[lbl]), "field": lbl}
        for lbl in sorted(used_fields, key=lambda l: FIELD_ORDER.index(l) if l in FIELD_ORDER else len(FIELD_ORDER))
    ]
    value_aliases = [{"from": raw, "to": term} for (raw, term) in translations.values()]
    skipped = sorted(unmapped_slugs)

    src_ws = mapping.get("options", {}).get("source_label", "Attio")
    return assemble(people, orgs, deals, links, notes, len(people) + len(orgs) + len(deals),
                    mapping_rows, skipped, value_aliases, default_currency, src_ws, timeline_entries)


# ── dedupe/merge (keyed; Attio has stable ids so we never fall back to name) ─────────────
def natural_key(rec: dict, id_field: str, rid: str) -> str:
    if rec.get(id_field):
        return f"{id_field}:{str(rec[id_field]).strip().lower()}"
    return f"rid:{rid}"  # stable Attio id — never merge two distinct records by name


def _merge(store: dict, rec: dict, key: str, prefix: str) -> str:
    if key not in store:
        store[key] = {"key": f"{prefix}{len(store)}"}
    dst = store[key]
    for fld, val in rec.items():
        if fld == "attributes":
            bag = dst.setdefault("attributes", {})
            for k, v in val.items():
                bag.setdefault(k, v)  # first-wins; a later dup can't clobber a real value
        elif fld == "emails":
            merged = dict.fromkeys((dst.get("emails") or []) + val)
            dst["emails"] = [e for e in merged if e]
        elif val not in (None, "") and not dst.get(fld):
            dst[fld] = val
    if dst.get("emails") and dst.get("email"):
        dst["emails"] = [e for e in dst["emails"] if e != dst["email"]] or None
        if dst["emails"] is None:
            del dst["emails"]
    return dst["key"]


# ── derive lifecycle from deal activity (fills the gap Attio leaves) ────────────────────
_STATUS_RANK = {"won": 3, "open": 2, "lost": 1}
_STATUS_LIFECYCLE = {"won": "client", "open": "prospect"}  # lost/none fall through to the default


def _better(a: str, b: str) -> str:
    return a if _STATUS_RANK.get(a, 0) >= _STATUS_RANK.get(b, 0) else b


def _derive_lifecycles(people: dict, deals: dict, links, default_lifecycle) -> int:
    """Set lifecycle_stage on people who lack one, from the best status among the deals they're
    tied to — directly (primary_contact) or through their company (works_at → a deal's account).
    Only fills a blank; never overrides an explicit lifecycle. Returns how many were set."""
    status_of = {d["key"]: d.get("status", "open") for d in deals.values()}
    org_best: dict = {}       # org_key  → best deal status on that org (via account links)
    person_direct: dict = {}  # person_key → best status among deals they're the contact on
    works_at: dict = {}       # person_key → set(org_key)
    for (a, b, rel) in links:
        if rel == "account" and a in status_of:              # a=deal_key, b=org_key
            org_best[b] = _better(org_best.get(b, ""), status_of[a])
        elif rel == "primary_contact" and b in status_of:    # a=person_key, b=deal_key
            person_direct[a] = _better(person_direct.get(a, ""), status_of[b])
        elif rel == "works_at":                              # a=person_key, b=org_key
            works_at.setdefault(a, set()).add(b)

    fallback = default_lifecycle or "lead"
    n = 0
    for p in people.values():
        if p.get("lifecycle_stage"):
            continue
        best = person_direct.get(p["key"], "")
        for org_key in works_at.get(p["key"], ()):
            best = _better(best, org_best.get(org_key, ""))
        p["lifecycle_stage"] = _STATUS_LIFECYCLE.get(best, fallback)
        n += 1
    return n


# ── assemble plan + digest (shape matches build_import.py so render_preview.py works) ──
def assemble(people, orgs, deals, links, notes, records_reviewed,
             mapping_rows, skipped, value_aliases, default_currency, source_label,
             timeline_entries=None) -> dict:
    timeline_entries = timeline_entries or []
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
        "rows_reviewed": records_reviewed,
        "source_kind": "attio",
        "source_file": source_label,
        "counts": {"contacts": len(contacts), "organizations": len(organizations),
                   "deals": len(deal_list), "links": len(link_list),
                   "timeline_entries": len(timeline_entries)},
        "mapping": mapping_rows,
        "skipped_columns": skipped,
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
    plan = {"contacts": contacts, "organizations": organizations,
            "deals": deal_list, "links": link_list}
    if timeline_entries:
        plan["timeline_entries"] = timeline_entries
    return {
        "rows_reviewed": records_reviewed,
        "plan": plan,
        "digest": digest,
    }


def _load(path):
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # accept either a bare array or {"records": [...]} / {"data": [...]}
    if isinstance(data, dict):
        data = data.get("records") or data.get("data") or []
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a CRM write-plan from pulled Attio records.")
    ap.add_argument("--people")
    ap.add_argument("--companies")
    ap.add_argument("--deals")
    ap.add_argument("--notes", help="Attio notes (list-notes + get-note-body) → timeline entries")
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--config")
    args = ap.parse_args()

    mapping = json.load(open(args.mapping, encoding="utf-8"))
    config = json.load(open(args.config, encoding="utf-8")) if args.config else {}
    plan = build(_load(args.people), _load(args.companies), _load(args.deals), mapping, config,
                 _load(args.notes))
    print(json.dumps(plan, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
