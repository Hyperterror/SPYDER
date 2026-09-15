"""
Helper script to inspect generated examples for reporting and verification.
"""

import json
import csv
from pathlib import Path

base = Path(__file__).resolve().parent / "output"

with open(base / "ground_truth/ground_truth.json", encoding="utf-8") as f:
    gt = json.load(f)

# Load evidence persons for cross-checking
with open(base / "evidence_dataset/persons.csv", encoding="utf-8") as f:
    persons = list(csv.DictReader(f))

# Load evidence cdrs, transactions, vehicles
with open(base / "evidence_dataset/cdr.csv", encoding="utf-8") as f:
    cdrs = list(csv.DictReader(f))

with open(base / "evidence_dataset/financial_transactions.csv", encoding="utf-8") as f:
    txns = list(csv.DictReader(f))

with open(base / "evidence_dataset/vehicle_records.csv", encoding="utf-8") as f:
    vehicles = list(csv.DictReader(f))

with open(base / "evidence_dataset/social_media.csv", encoding="utf-8") as f:
    social = list(csv.DictReader(f))

print("="*60)
print("1. LATENT ENTITY CROSS-CASE MANIFESTATIONS (3-5 EXAMPLES)")
print("="*60)
cross_ents = [e for e in gt["entities"] if len(e["case_memberships"]) > 1]
for idx, e in enumerate(cross_ents[:4], 1):
    gid = e["global_id"]
    obs = gt["observational_mapping"][gid]
    # find phones, bank accounts, vehicles for this entity
    p_nums = [p["phone_number"] for p in gt["phones"] if p["primary_owner_global_id"] == gid]
    accs = [a["account_id"] for a in gt["bank_accounts"] if a["owner_global_id"] == gid]
    socs = [s["username"] for s in gt["social_accounts"] if s["owner_global_id"] == gid]
    
    print(f"\n[Example {idx}] Latent Entity: {gid}")
    print(f"  * True Identity: {e['true_name']} | Canonical Role: {e['true_role']}")
    print(f"  * Network Syndicate: {e['network_cluster']}")
    print(f"  * Observable Shared Signals: Phone={p_nums[:1]}, Accounts={accs[:1]}, Social={socs[:1]}")
    print(f"  * Manifestations in Evidence Dossiers:")
    for cid, inst in obs["case_instances"].items():
        obs_p = [p for p in persons if p["person_id"] == inst["observational_person_id"]][0]
        print(f"    - Case {cid}: Observational Person ID = '{inst['observational_person_id']}'")
        print(f"      Recorded Name = '{obs_p['name']}', Alias = '{obs_p['alias']}', Recorded Role = '{obs_p['role']}'")

print("\n" + "="*60)
print("2. GENUINE CROSS-CASE RELATIONSHIPS (3-5 EXAMPLES)")
print("="*60)
links = [l for l in gt["case_links"] if l["is_linked"]]
for idx, l in enumerate(links[:4], 1):
    ca, cb = l["case_a"], l["case_b"]
    print(f"\n[Case Link {idx}] {ca} <---> {cb}")
    print(f"  * Syndicate: {l['syndicate_cluster']}")
    print(f"  * Shared Latent Entities Count: {l['shared_global_entities_count']}")
    print(f"  * Shared Latent Entities: {l['shared_global_entities']}")
    # Show observable overlaps between ca and cb in evidence (e.g. shared phones in CDR, shared accounts in TXN)
    ca_callers = {r["caller"] for r in cdrs if r["case_id"] == ca}
    cb_callers = {r["caller"] for r in cdrs if r["case_id"] == cb}
    shared_callers = ca_callers.intersection(cb_callers)
    print(f"  * Observable Cross-Case Phone Numbers in CDR: {len(shared_callers)} recurring numbers (e.g. {list(shared_callers)[:2]})")

print("\n" + "="*60)
print("3. HARD NEGATIVES (SIMILAR SURFACE FORMS, DIFFERENT ENTITIES)")
print("="*60)
hn_groups = {}
for hn in gt["hard_negatives"]:
    hn_groups.setdefault(hn["hard_negative_group"], []).append(hn)

for idx, (grp, members) in enumerate(hn_groups.items(), 1):
    print(f"\n[Hard Negative Pair {idx}] Group: {grp}")
    for m in members:
        print(f"  * Global ID: {m['global_id']}")
        print(f"    Name: '{m['true_name']}' | Alias: '{m['canonical_alias']}'")
        print(f"    Role: {m['true_role']} | Cluster: {m['network_cluster']} | Cases: {m['case_memberships']}")
