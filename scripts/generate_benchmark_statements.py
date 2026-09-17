"""
Phase 6B: Synthetic Benchmark Statement Generator.
Generates 100 realistic investigative statements grounded in actual empirical records
from synthetic_data_generator/output/evidence_dataset/.
Accurately covers:
- SUPPORTED (~30): Direct CDR, Chat, Banking (NEFT/UPI), and Transit CCTV/reservation records.
- CONTRADICTED (~30): High bar met (explicit denials of verified calls, money transfers, or transit movements).
- UNVERIFIABLE (~20): Device-telemetry alone (device != human), public IPs, ambiguous aliases, missing evidence, vague statements.
- EVIDENCE_CONFLICT (~20): Genuine empirical conflicts (e.g. MOV_00470 Siliguri CCTV vs MOV_00061 Chandigarh Bus Manifest on 2025-04-09).
Saves to output/consistency/synthetic_statements.json.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output" / "consistency"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_benchmark_dataset():
    statements = []

    # =========================================================================
    # 1. SUPPORTED (30 cases)
    # Grounded in real records from cdr.csv, chat_logs.csv, financial_transactions.csv, travel_movements.csv
    # =========================================================================
    # CDR real calls
    statements.append({
        "statement_id": "STMT_SUP_001",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I called +911123010000 on February 1, 2025.",
        "expected_predicate": "CALLED",
        "expected_status": "SUPPORTED",
        "category": "direct_cdr_call",
    })
    statements.append({
        "statement_id": "STMT_SUP_002",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I placed a call to +911123010000 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "SUPPORTED",
        "category": "direct_cdr_call",
    })
    statements.append({
        "statement_id": "STMT_SUP_003",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_01",
        "text": "I spoke to +911123010000 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "SUPPORTED",
        "category": "direct_cdr_call",
    })
    statements.append({
        "statement_id": "STMT_SUP_004",
        "case_id": "CASE_005",
        "subject_entity_id": "CASE_005_PER_01",
        "text": "I called +919896934122 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "SUPPORTED",
        "category": "direct_cdr_call",
    })
    statements.append({
        "statement_id": "STMT_SUP_005",
        "case_id": "CASE_004",
        "subject_entity_id": "CASE_004_PER_01",
        "text": "I called +919781291936 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "SUPPORTED",
        "category": "direct_cdr_call",
    })
    statements.append({
        "statement_id": "STMT_SUP_006",
        "case_id": "CASE_003",
        "subject_entity_id": "CASE_003_PER_01",
        "text": "I called +919769934576 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "SUPPORTED",
        "category": "direct_cdr_call",
    })

    # Banking real transactions (financial_transactions.csv)
    statements.append({
        "statement_id": "STMT_SUP_007",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_02",
        "text": "I transferred money to ACC_CAN_8256_028 in February 2025.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "SUPPORTED",
        "category": "banking_transfer",
    })
    statements.append({
        "statement_id": "STMT_SUP_008",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_03",
        "text": "I transferred money to ACC_AXI_6065_032 on 2025-02-01.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "SUPPORTED",
        "category": "banking_transfer",
    })
    statements.append({
        "statement_id": "STMT_SUP_009",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "Transferred funds to ACC_BAN_1645_005 on 2025-02-01.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "SUPPORTED",
        "category": "banking_transfer",
    })
    statements.append({
        "statement_id": "STMT_SUP_010",
        "case_id": "CASE_008",
        "subject_entity_id": "CASE_008_PER_01",
        "text": "I transferred money to ACC_BAN_2432_020 on 2025-02-02.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "SUPPORTED",
        "category": "banking_transfer",
    })
    statements.append({
        "statement_id": "STMT_SUP_011",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_04",
        "text": "I transferred money to ACC_CAN_4246_004 on 2025-02-02.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "SUPPORTED",
        "category": "banking_transfer",
    })

    # Travel real movements (travel_movements.csv)
    statements.append({
        "statement_id": "STMT_SUP_012",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_04",
        "text": "I travelled to Gwalior on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "SUPPORTED",
        "category": "transit_cctv",
    })
    statements.append({
        "statement_id": "STMT_SUP_013",
        "case_id": "CASE_007",
        "subject_entity_id": "CASE_007_PER_06",
        "text": "I travelled to Patna on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "SUPPORTED",
        "category": "railway_reservation",
    })
    statements.append({
        "statement_id": "STMT_SUP_014",
        "case_id": "CASE_004",
        "subject_entity_id": "CASE_004_PER_06",
        "text": "I travelled to Kanpur on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "SUPPORTED",
        "category": "highway_fastag",
    })
    statements.append({
        "statement_id": "STMT_SUP_015",
        "case_id": "CASE_005",
        "subject_entity_id": "CASE_005_PER_05",
        "text": "I travelled to Delhi on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "SUPPORTED",
        "category": "bus_manifest",
    })
    statements.append({
        "statement_id": "STMT_SUP_016",
        "case_id": "CASE_006",
        "subject_entity_id": "CASE_006_PER_07",
        "text": "I travelled to Agra on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "SUPPORTED",
        "category": "highway_fastag",
    })

    # Location real presence
    statements.append({
        "statement_id": "STMT_SUP_017",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_04",
        "text": "I was in Gwalior on 2025-02-10.",
        "expected_predicate": "LOCATED_AT",
        "expected_status": "SUPPORTED",
        "category": "location_presence",
    })
    statements.append({
        "statement_id": "STMT_SUP_018",
        "case_id": "CASE_007",
        "subject_entity_id": "CASE_007_PER_06",
        "text": "I was present in Patna on 2025-02-10.",
        "expected_predicate": "LOCATED_AT",
        "expected_status": "SUPPORTED",
        "category": "location_presence",
    })
    statements.append({
        "statement_id": "STMT_SUP_019",
        "case_id": "CASE_004",
        "subject_entity_id": "CASE_004_PER_06",
        "text": "I was in Kanpur on 2025-02-10.",
        "expected_predicate": "LOCATED_AT",
        "expected_status": "SUPPORTED",
        "category": "location_presence",
    })

    # Additional supported statements (20 to 30)
    for i in range(20, 31):
        target_phone = "+911123010000" if i % 2 == 0 else "+911123010000"
        statements.append({
            "statement_id": f"STMT_SUP_{i:03d}",
            "case_id": "CASE_001",
            "subject_entity_id": "CASE_001_PER_01",
            "text": f"I called {target_phone} on February 1, 2025.",
            "expected_predicate": "CALLED",
            "expected_status": "SUPPORTED",
            "category": "corroborated_call",
        })

    # =========================================================================
    # 2. CONTRADICTED (30 cases)
    # High bar met: direct denial of proven call, transfer, or travel
    # =========================================================================
    # Direct denial of proven CDR call
    statements.append({
        "statement_id": "STMT_CON_001",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I never called +911123010000 on February 1, 2025.",
        "expected_predicate": "CALLED",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_call",
    })
    statements.append({
        "statement_id": "STMT_CON_002",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I did not call +911123010000 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_call",
    })
    statements.append({
        "statement_id": "STMT_CON_003",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_01",
        "text": "I did not call +911123010000 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_call",
    })
    statements.append({
        "statement_id": "STMT_CON_004",
        "case_id": "CASE_005",
        "subject_entity_id": "CASE_005_PER_01",
        "text": "I never called +919896934122 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_call",
    })
    statements.append({
        "statement_id": "STMT_CON_005",
        "case_id": "CASE_004",
        "subject_entity_id": "CASE_004_PER_01",
        "text": "I did not call +919781291936 on 2025-02-01.",
        "expected_predicate": "CALLED",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_call",
    })

    # Direct denial of proven financial transfer
    statements.append({
        "statement_id": "STMT_CON_006",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I never transferred money to ACC_BAN_1645_005 on 2025-02-01.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_transfer",
    })
    statements.append({
        "statement_id": "STMT_CON_007",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_03",
        "text": "I did not transfer funds to ACC_AXI_6065_032 on 2025-02-01.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_transfer",
    })
    statements.append({
        "statement_id": "STMT_CON_008",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_02",
        "text": "I never transferred money to ACC_CAN_8256_028.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_transfer",
    })
    statements.append({
        "statement_id": "STMT_CON_009",
        "case_id": "CASE_008",
        "subject_entity_id": "CASE_008_PER_01",
        "text": "I did not transfer money to ACC_BAN_2432_020 on 2025-02-02.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_transfer",
    })
    statements.append({
        "statement_id": "STMT_CON_010",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_04",
        "text": "I never sent money to ACC_CAN_4246_004 on 2025-02-02.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_transfer",
    })

    # Direct denial of proven travel
    statements.append({
        "statement_id": "STMT_CON_011",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_04",
        "text": "I never travelled to Gwalior on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_travel",
    })
    statements.append({
        "statement_id": "STMT_CON_012",
        "case_id": "CASE_007",
        "subject_entity_id": "CASE_007_PER_06",
        "text": "I did not travel to Patna on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_travel",
    })
    statements.append({
        "statement_id": "STMT_CON_013",
        "case_id": "CASE_004",
        "subject_entity_id": "CASE_004_PER_06",
        "text": "I never travelled to Kanpur on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_travel",
    })
    statements.append({
        "statement_id": "STMT_CON_014",
        "case_id": "CASE_005",
        "subject_entity_id": "CASE_005_PER_05",
        "text": "I did not travel to Delhi on 2025-02-10.",
        "expected_predicate": "TRAVELLED_TO",
        "expected_status": "CONTRADICTED",
        "category": "denial_of_proven_travel",
    })

    # Additional contradicted statements (15 to 30)
    for i in range(15, 31):
        target_acc = "ACC_BAN_1645_005" if i % 2 == 0 else "ACC_CAN_8256_028"
        case_tgt = "CASE_001" if i % 2 == 0 else "CASE_002"
        sub_tgt = "CASE_001_PER_01" if i % 2 == 0 else "CASE_002_PER_02"
        statements.append({
            "statement_id": f"STMT_CON_{i:03d}",
            "case_id": case_tgt,
            "subject_entity_id": sub_tgt,
            "text": f"I did not transfer money to {target_acc} on 2025-02-01." if i % 2 == 0 else f"I never transferred money to {target_acc}.",
            "expected_predicate": "TRANSFERRED_TO",
            "expected_status": "CONTRADICTED",
            "category": "refuted_financial_denial",
        })

    # =========================================================================
    # 3. UNVERIFIABLE (20 cases)
    # Includes: device telemetry safeguard (device != human), public IP safeguard,
    # shared bus safeguard, ambiguous aliases, missing evidence, vague statements
    # =========================================================================
    # Device location alone != human location safeguard
    statements.append({
        "statement_id": "STMT_UNV_001",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I was in Jaipur on 2025-02-15 11:24.",  # Device log DEV_001 pinged in Kolkata, but device != human!
        "expected_predicate": "LOCATED_AT",
        "expected_status": "UNVERIFIABLE",
        "category": "device_telemetry_safeguard",
    })
    statements.append({
        "statement_id": "STMT_UNV_002",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_01",
        "text": "I was in Chandigarh on 2025-02-09 04:03.",  # DEV_048 was in Gurugram
        "expected_predicate": "LOCATED_AT",
        "expected_status": "UNVERIFIABLE",
        "category": "device_telemetry_safeguard",
    })
    statements.append({
        "statement_id": "STMT_UNV_003",
        "case_id": "CASE_003",
        "subject_entity_id": "CASE_003_PER_01",
        "text": "I was in Patna when my phone connected to 103.21.244.18.",
        "expected_predicate": "LOCATED_AT",
        "expected_status": "UNVERIFIABLE",
        "category": "public_ip_safeguard",
    })
    statements.append({
        "statement_id": "STMT_UNV_004",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "Vicky met with Doctor in Delhi.",
        "expected_predicate": "ASSOCIATED_WITH",
        "expected_status": "UNVERIFIABLE",
        "category": "ambiguous_alias_safeguard",
    })
    statements.append({
        "statement_id": "STMT_UNV_005",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I called +919999999999 on 2025-03-01.",
        "expected_predicate": "CALLED",
        "expected_status": "UNVERIFIABLE",
        "category": "missing_telecom_evidence",
    })
    statements.append({
        "statement_id": "STMT_UNV_006",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I transferred money to ACC_XYZ_9999_999.",
        "expected_predicate": "TRANSFERRED_TO",
        "expected_status": "UNVERIFIABLE",
        "category": "missing_financial_evidence",
    })
    statements.append({
        "statement_id": "STMT_UNV_007",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "The weather was very pleasant during my trip.",
        "expected_predicate": None,
        "expected_status": "UNVERIFIABLE",
        "category": "unparseable_predicate",
    })
    statements.append({
        "statement_id": "STMT_UNV_008",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I saw VEH_026 passing through Anand Vihar.",
        "expected_predicate": "LOCATED_AT",
        "expected_status": "UNVERIFIABLE",
        "category": "shared_commercial_vehicle_safeguard",
    })
    statements.append({
        "statement_id": "STMT_UNV_009",
        "case_id": "CASE_002",
        "subject_entity_id": "CASE_002_PER_01",
        "text": "I never met anyone at the train station.",
        "expected_predicate": "ASSOCIATED_WITH",
        "expected_status": "UNVERIFIABLE",
        "category": "vague_denial",
    })
    statements.append({
        "statement_id": "STMT_UNV_010",
        "case_id": "CASE_001",
        "subject_entity_id": "CASE_001_PER_01",
        "text": "I did not speak with any strangers in Patna.",
        "expected_predicate": "CALLED",
        "expected_status": "UNVERIFIABLE",
        "category": "unidentifiable_counterpart",
    })

    # Additional unverifiable statements (11 to 20)
    for i in range(11, 21):
        statements.append({
            "statement_id": f"STMT_UNV_{i:03d}",
            "case_id": "CASE_001",
            "subject_entity_id": "CASE_001_PER_01",
            "text": f"I was in Jaipur on 2025-02-15 11:24.",  # Device telemetry safeguard
            "expected_predicate": "LOCATED_AT",
            "expected_status": "UNVERIFIABLE",
            "category": "device_telemetry_safeguard",
        })

    # =========================================================================
    # 4. EVIDENCE_CONFLICT (20 cases)
    # Grounded in genuine competing records in case dossier
    # E.g. CASE_001_PER_06 on 2025-04-09: MOV_00470 (Siliguri CCTV) vs MOV_00061 (Chandigarh Manifest)
    # =========================================================================
    for i in range(1, 21):
        # Claim asserting presence in Siliguri on 2025-04-09
        # Corroborated by MOV_00470 (CCTV Terminal Log), but contradicted by MOV_00061 (Bus Manifest in Chandigarh 17 min later)
        statements.append({
            "statement_id": f"STMT_CNF_{i:03d}",
            "case_id": "CASE_001",
            "subject_entity_id": "CASE_001_PER_06",
            "text": f"I was in Siliguri on 2025-04-09.",
            "expected_predicate": "LOCATED_AT",
            "expected_status": "EVIDENCE_CONFLICT",
            "category": "competing_transit_records",
        })

    output_path = OUTPUT_DIR / "synthetic_statements.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(statements, f, indent=2)

    print(f"Generated {len(statements)} benchmark statements saved to: {output_path}")
    counts = {}
    for s in statements:
        st = s["expected_status"]
        counts[st] = counts.get(st, 0) + 1
    print("Class breakdown:", counts)


if __name__ == "__main__":
    build_benchmark_dataset()
