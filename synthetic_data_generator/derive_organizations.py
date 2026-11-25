"""Deterministically derive ORGANIZATION evidence tables from the frozen dataset.

Why this is a derivation and not a generator step
-------------------------------------------------
``synthetic_data_generator`` is nominally seeded (``DEFAULT_SEED = 42``) but the
committed evidence CSVs are **not** reproducible from it: regenerating reorders
``travel_movements.csv`` and ``vehicle_records.csv``. Every downstream artifact
(entity resolution, knowledge graph, GraphSAGE) is keyed to the committed CSVs,
so re-running the generator would invalidate all of them.

This module therefore *reads the frozen evidence* and emits two new tables.
It uses no RNG and makes no network/file-creation decisions that depend on
iteration order, so repeated runs produce byte-identical output, and the
existing CSVs are left untouched.

Derivation sources (all observable, none latent ground truth)
------------------------------------------------------------
organizations.csv
    * persons.csv      occupation + address city  -> employer establishments
    * cases.csv        agency                     -> investigating agency
    * evidence.csv     chain_of_custody           -> forensic laboratory / evidence store
org_affiliations.csv
    * PERSON  --AFFILIATED_WITH-->  ORGANIZATION   (persons.csv occupation + city)
    * CASE    --INVESTIGATED_BY-->  ORGANIZATION   (cases.csv agency)
    * EVIDENCE--PROCESSED_BY-->     ORGANIZATION   (evidence.csv chain_of_custody)

Usage (from ``synthetic_data_generator/``):
    python derive_organizations.py
"""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

BASE_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = BASE_DIR / "output" / "evidence_dataset"

ORGANIZATIONS_FILE = "organizations.csv"
AFFILIATIONS_FILE = "org_affiliations.csv"

ORG_FIELDS = [
    "org_id",
    "name",
    "org_type",
    "sector",
    "registered_office_city",
    "registration_no",
    "case_id",
]
AFFILIATION_FIELDS = [
    "affiliation_id",
    "org_id",
    "entity_id",
    "entity_type",
    "relation",
    "since_date",
    "source_table",
    "source_record_id",
    "case_id",
]

# Occupations that imply an establishment the person is observed to run or work in.
# Deliberately excludes self-employed trades and "Unemployed": an occupation is not
# by itself evidence of a shared organisation.
OCCUPATION_TO_ORG: Dict[str, Tuple[str, str, str]] = {
    # occupation -> (org_type, sector, name suffix)
    "Agency Proprietor": ("PLACEMENT_AGENCY", "Employment Placement", "Placement Services"),
    "Placement Agent": ("PLACEMENT_AGENCY", "Employment Placement", "Placement Services"),
    "Labour Contractor": ("LABOUR_SUPPLY_FIRM", "Labour Contracting", "Labour Supply Company"),
    "Travel Agent": ("TRAVEL_AGENCY", "Travel & Ticketing", "Travel & Ticketing Agency"),
    "Tour Operator": ("TRAVEL_AGENCY", "Travel & Ticketing", "Travel & Ticketing Agency"),
    "Bus Ticket Clerk": ("TRAVEL_AGENCY", "Travel & Ticketing", "Travel & Ticketing Agency"),
    "Hotel Manager": ("LODGING_ESTABLISHMENT", "Hospitality", "Guest House"),
    "Driver": ("TRANSPORT_OPERATOR", "Road Transport", "Road Transport Operator"),
    "Auto Driver": ("TRANSPORT_OPERATOR", "Road Transport", "Road Transport Operator"),
    "NGO Volunteer": ("NONPROFIT_ORGANISATION", "Social Welfare", "Welfare Trust"),
}

ORG_TYPE_ABBR = {
    "PLACEMENT_AGENCY": "PLC",
    "LABOUR_SUPPLY_FIRM": "LBR",
    "TRAVEL_AGENCY": "TRV",
    "LODGING_ESTABLISHMENT": "LDG",
    "TRANSPORT_OPERATOR": "TRN",
    "NONPROFIT_ORGANISATION": "NGO",
    "LAW_ENFORCEMENT_AGENCY": "LEA",
    "FORENSIC_LABORATORY": "FSL",
    "EVIDENCE_STORE": "EVD",
}

AGENCY_NAMES = {
    "Anti-Human Trafficking Unit (AHTU)": "Anti-Human Trafficking Unit",
    "State Crime Investigation Department (CID)": "State Crime Investigation Department",
    "Special Task Force (STF)": "Special Task Force",
    "Metro Central Police Division": "Metro Central Police Division",
}


# --------------------------------------------------------------------------- helpers
def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", (value or "").strip()).strip("_").upper()


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with open(path, mode="r", encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _city_from_address(address: str) -> str:
    """Addresses are stored as 'house, street, City'; the city is the last component."""
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    return parts[-1] if parts else ""


def _registration_no(org_id: str) -> str:
    """Deterministic synthetic registration reference (no real identifiers)."""
    digest = hashlib.sha256(org_id.encode("utf-8")).hexdigest().upper()
    return f"REG-{digest[:4]}-{int(digest[4:12], 16) % 100000:05d}"


def _org_id(org_type: str, key: str) -> str:
    return f"ORG_{ORG_TYPE_ABBR.get(org_type, 'GEN')}_{_slug(key)}"


def _earliest(values: Iterable[str]) -> str:
    present = [v for v in values if v]
    return min(present) if present else ""


# --------------------------------------------------------------------------- derive
def derive(evidence_dir: Path = EVIDENCE_DIR) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (organizations, affiliations) derived from the frozen evidence tables."""
    evidence_dir = Path(evidence_dir)
    persons = _read_csv(evidence_dir / "persons.csv")
    cases = _read_csv(evidence_dir / "cases.csv")
    evidence = _read_csv(evidence_dir / "evidence.csv")

    case_reported = {row.get("case_id", ""): row.get("reported_date", "") for row in cases}

    organizations: Dict[str, Dict[str, Any]] = {}
    affiliations: List[Dict[str, Any]] = []

    def register_org(
        org_id: str,
        name: str,
        org_type: str,
        sector: str,
        city: str,
        case_id: str,
    ) -> None:
        existing = organizations.get(org_id)
        if existing is None:
            organizations[org_id] = {
                "org_id": org_id,
                "name": name,
                "org_type": org_type,
                "sector": sector,
                "registered_office_city": city,
                "registration_no": _registration_no(org_id),
                "case_id": case_id,
            }
            return
        # An organisation observed across several cases keeps the first case by
        # sorted order (deterministic) and accumulates the rest via affiliations.
        if case_id and case_id < existing["case_id"]:
            existing["case_id"] = case_id

    def add_affiliation(
        org_id: str,
        entity_id: str,
        entity_type: str,
        relation: str,
        since_date: str,
        source_table: str,
        source_record_id: str,
        case_id: str,
    ) -> None:
        affiliations.append(
            {
                "org_id": org_id,
                "entity_id": entity_id,
                "entity_type": entity_type,
                "relation": relation,
                "since_date": since_date,
                "source_table": source_table,
                "source_record_id": source_record_id,
                "case_id": case_id,
            }
        )

    # 1. Employer establishments observed through persons' occupations
    for row in sorted(persons, key=lambda r: r.get("person_id", "")):
        occupation = (row.get("occupation") or "").strip()
        mapping = OCCUPATION_TO_ORG.get(occupation)
        if not mapping:
            continue
        org_type, sector, suffix = mapping
        city = _city_from_address(row.get("address", ""))
        if not city:
            continue
        org_id = _org_id(org_type, city)
        register_org(
            org_id=org_id,
            name=f"{city} {suffix}",
            org_type=org_type,
            sector=sector,
            city=city,
            case_id=row.get("case_id", ""),
        )
        case_id = row.get("case_id", "")
        add_affiliation(
            org_id=org_id,
            entity_id=row.get("person_id", ""),
            entity_type="PERSON",
            relation="AFFILIATED_WITH",
            since_date=case_reported.get(case_id, ""),
            source_table="persons.csv",
            source_record_id=row.get("person_id", ""),
            case_id=case_id,
        )

    # 2. Investigating agencies observed on case dossiers
    for row in sorted(cases, key=lambda r: r.get("case_id", "")):
        agency = (row.get("agency") or "").strip()
        if not agency:
            continue
        case_id = row.get("case_id", "")
        org_id = _org_id("LAW_ENFORCEMENT_AGENCY", agency)
        register_org(
            org_id=org_id,
            name=AGENCY_NAMES.get(agency, agency),
            org_type="LAW_ENFORCEMENT_AGENCY",
            sector="Law Enforcement",
            city="",
            case_id=case_id,
        )
        add_affiliation(
            org_id=org_id,
            entity_id=case_id,
            entity_type="CASE",
            relation="INVESTIGATED_BY",
            since_date=row.get("reported_date", ""),
            source_table="cases.csv",
            source_record_id=case_id,
            case_id=case_id,
        )

    # 3. Custodial / forensic organisations observed in the chain of custody
    for row in sorted(evidence, key=lambda r: r.get("evidence_id", "")):
        chain = (row.get("chain_of_custody") or "").strip()
        if not chain:
            continue
        case_id = row.get("case_id", "")
        evidence_id = row.get("evidence_id", "")
        custodians = [part.strip() for part in chain.split("->") if part.strip()]

        for custodian in custodians:
            lowered = custodian.lower()
            if "forensic" in lowered:
                org_type, sector, name = (
                    "FORENSIC_LABORATORY",
                    "Forensic Science",
                    "Forensic Science Laboratory",
                )
            elif "malkhana" in lowered:
                org_type, sector, name = (
                    "EVIDENCE_STORE",
                    "Evidence Custody",
                    "District Malkhana Evidence Store",
                )
            else:
                continue

            org_id = _org_id(org_type, name)
            register_org(
                org_id=org_id,
                name=name,
                org_type=org_type,
                sector=sector,
                city="",
                case_id=case_id,
            )
            add_affiliation(
                org_id=org_id,
                entity_id=evidence_id,
                entity_type="EVIDENCE",
                relation="PROCESSED_BY",
                since_date=(row.get("timestamp", "") or "").split(" ")[0],
                source_table="evidence.csv",
                source_record_id=evidence_id,
                case_id=case_id,
            )

    # Deterministic output ordering (affiliations de-duplicated on their key fields)
    seen = set()
    unique_affiliations: List[Dict[str, Any]] = []
    for aff in sorted(
        affiliations,
        key=lambda a: (a["org_id"], a["entity_type"], a["entity_id"], a["relation"]),
    ):
        key = (aff["org_id"], aff["entity_id"], aff["relation"])
        if key in seen:
            continue
        seen.add(key)
        unique_affiliations.append(aff)

    for idx, aff in enumerate(unique_affiliations, start=1):
        aff["affiliation_id"] = f"AFF_{idx:05d}"

    orgs = [organizations[oid] for oid in sorted(organizations)]
    return orgs, unique_affiliations


def write_tables(
    organizations: List[Dict[str, Any]],
    affiliations: List[Dict[str, Any]],
    evidence_dir: Path = EVIDENCE_DIR,
) -> Tuple[Path, Path]:
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    orgs_path = evidence_dir / ORGANIZATIONS_FILE
    with open(orgs_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ORG_FIELDS)
        writer.writeheader()
        for row in organizations:
            writer.writerow({k: row.get(k, "") for k in ORG_FIELDS})

    affs_path = evidence_dir / AFFILIATIONS_FILE
    with open(affs_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AFFILIATION_FIELDS)
        writer.writeheader()
        for row in affiliations:
            writer.writerow({k: row.get(k, "") for k in AFFILIATION_FIELDS})

    return orgs_path, affs_path


def main() -> int:
    organizations, affiliations = derive()
    orgs_path, affs_path = write_tables(organizations, affiliations)

    by_type: Dict[str, int] = {}
    for org in organizations:
        by_type[org["org_type"]] = by_type.get(org["org_type"], 0) + 1
    by_relation: Dict[str, int] = {}
    for aff in affiliations:
        by_relation[aff["relation"]] = by_relation.get(aff["relation"], 0) + 1

    print("=== Derived organization evidence ===")
    print(f"[+] {orgs_path.name}: {len(organizations)} organizations")
    for org_type, count in sorted(by_type.items()):
        print(f"      {org_type}: {count}")
    print(f"[+] {affs_path.name}: {len(affiliations)} affiliations")
    for relation, count in sorted(by_relation.items()):
        print(f"      {relation}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
