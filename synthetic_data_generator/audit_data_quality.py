"""
Identifier Overlap and Data Quality Audit Script
"""

import csv
import json
from pathlib import Path
from collections import defaultdict

base = Path(__file__).resolve().parent / "output"
evidence_dir = base / "evidence_dataset"
gt_dir = base / "ground_truth"

with open(gt_dir / "ground_truth.json", encoding="utf-8") as f:
    gt = json.load(f)

# 1. Role Leakage Check
print("="*65)
print("1. ROLE LEAKAGE AUDIT")
print("="*65)
CANONICAL_ROLES = [
    "coordinator", "recruiter", "transporter", "financier",
    "document_facilitator", "local_associate", "victim", "legitimate_contact",
    "mastermind", "syndicate head", "hawala operator"
]

role_leaks = []
with open(evidence_dir / "persons.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        r_val = row["role"].lower()
        o_val = row["occupation"].lower()
        for c_role in CANONICAL_ROLES:
            if c_role == r_val or c_role in r_val.split("/"):
                role_leaks.append((row["person_id"], "role", row["role"]))
            if c_role in o_val:
                role_leaks.append((row["person_id"], "occupation", row["occupation"]))

if role_leaks:
    print(f"FAILED: Found {len(role_leaks)} role leaks!")
    for leak in role_leaks[:5]:
        print(f"  Leak in {leak[0]} ({leak[1]}): {leak[2]}")
else:
    print("PASSED: Zero canonical true roles leaked in persons.csv.")

# Sample observed roles and occupations
with open(evidence_dir / "persons.csv", encoding="utf-8") as f:
    p_rows = list(csv.DictReader(f))
    observed_roles = sorted(list({r["role"] for r in p_rows}))
    observed_occs = sorted(list({r["occupation"] for r in p_rows}))
    print(f"Unique Observed Roles ({len(observed_roles)}): {observed_roles}")
    print(f"Sample Observed Occupations: {observed_occs[:6]}")

# 2. Identifier Overlap Audit
print("\n" + "="*65)
print("2. IDENTIFIER OVERLAP AUDIT BY TYPE")
print("="*65)

def get_case_sets(csv_path, id_col, case_col="case_id"):
    case_map = defaultdict(set)
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            val = row[id_col].strip()
            cid = row[case_col].strip()
            if val:
                case_map[cid].add(val)
    return case_map

phone_cases_cdr = defaultdict(set)
with open(evidence_dir / "cdr.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cid = row["case_id"]
        phone_cases_cdr[cid].add(row["caller"])
        phone_cases_cdr[cid].add(row["receiver"])

imei_cases = get_case_sets(evidence_dir / "device_logs.csv", "imei")
dev_cases = get_case_sets(evidence_dir / "device_logs.csv", "device_id")
ip_cases = get_case_sets(evidence_dir / "device_logs.csv", "ip_address")
veh_cases = get_case_sets(evidence_dir / "vehicle_records.csv", "registration_no")
bank_cases = defaultdict(set)
with open(evidence_dir / "financial_transactions.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cid = row["case_id"]
        bank_cases[cid].add(row["sender_account"])
        bank_cases[cid].add(row["receiver_account"])
soc_cases = get_case_sets(evidence_dir / "social_media.csv", "username")

def analyze_overlap(name, case_map):
    all_cases = sorted(list(case_map.keys()))
    pairwise_overlaps = []
    # Count how many identifiers appear in >= 2 cases
    id_freq = defaultdict(set)
    for cid, ids in case_map.items():
        for i in ids:
            id_freq[i].add(cid)
    
    cross_ids = {i: cids for i, cids in id_freq.items() if len(cids) > 1}
    print(f"Identifier Type: {name}")
    print(f"  Total unique values: {len(id_freq)}")
    print(f"  Values appearing across >= 2 cases: {len(cross_ids)} ({len(cross_ids)/max(1, len(id_freq)):.1%})")
    
    # Check CASE_001 vs CASE_003 (Network Alpha) and CASE_001 vs CASE_004 (Independent)
    c1_c3 = len(case_map.get("CASE_001", set()).intersection(case_map.get("CASE_003", set())))
    c1_c7 = len(case_map.get("CASE_001", set()).intersection(case_map.get("CASE_007", set())))
    c1_c4 = len(case_map.get("CASE_001", set()).intersection(case_map.get("CASE_004", set())))
    print(f"  Overlap CASE_001 <-> CASE_003 (Alpha Syndicate): {c1_c3}")
    print(f"  Overlap CASE_001 <-> CASE_007 (Alpha Syndicate): {c1_c7}")
    print(f"  Overlap CASE_001 <-> CASE_004 (Independent Pair): {c1_c4}")
    return cross_ids

print("")
analyze_overlap("Phone Numbers (in CDR)", phone_cases_cdr)
print("")
analyze_overlap("Device IMEIs", imei_cases)
print("")
analyze_overlap("Device IDs", dev_cases)
print("")
analyze_overlap("Vehicle Registrations", veh_cases)
print("")
analyze_overlap("Bank Accounts", bank_cases)
print("")
analyze_overlap("IP Addresses (Network Infrastructure)", ip_cases)

print("\n" + "="*65)
print("3. DEVICE LOGS AUDIT")
print("="*65)
with open(evidence_dir / "device_logs.csv", encoding="utf-8") as f:
    dev_rows = list(csv.DictReader(f))
print(f"Total device log records: {len(dev_rows)}")
print("Sample device log record:")
for k, v in list(dev_rows[0].items()):
    print(f"  {k}: {v}")
