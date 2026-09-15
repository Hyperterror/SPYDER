"""
Dataset Generation CLI Orchestrator:
Executes the Ground-Truth-First synthesis and exports fragmented observational evidence CSVs
alongside isolated hidden ground-truth JSON files.
"""

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DEFAULT_SEED, EVIDENCE_DIR, GROUND_TRUTH_DIR, NETWORK_CLUSTERS
from generators.ground_truth_generator import GroundTruthGenerator
from generators.case_generator import CaseGenerator
from generators.person_generator import PersonGenerator
from generators.communication_generator import CommunicationGenerator
from generators.movement_generator import MovementGenerator
from generators.vehicle_generator import VehicleGenerator
from generators.device_generator import DeviceGenerator
from generators.financial_generator import FinancialGenerator
from generators.social_generator import SocialGenerator
from generators.evidence_generator import EvidenceGenerator

def export_csv(file_path: Path, records: List[Dict[str, Any]], fieldnames: List[str]):
    """Exports a list of dictionaries to CSV with standard header."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r)

def export_json(file_path: Path, data: Any):
    """Exports structured data to formatted JSON."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, mode="w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def run_pipeline(seed: int = DEFAULT_SEED, evidence_dir: Path = EVIDENCE_DIR, ground_truth_dir: Path = GROUND_TRUTH_DIR):
    rng = random.Random(seed)

    # 1. Latent Ground Truth Generation
    gt_gen = GroundTruthGenerator(rng)
    ground_truth = gt_gen.generate_ground_truth()

    # 2. Evidence Generators
    case_gen = CaseGenerator(rng)
    person_gen = PersonGenerator(rng)
    comm_gen = CommunicationGenerator(rng)
    mov_gen = MovementGenerator(rng)
    veh_gen = VehicleGenerator(rng)
    dev_gen = DeviceGenerator(rng)
    fin_gen = FinancialGenerator(rng)
    soc_gen = SocialGenerator(rng)
    ev_gen = EvidenceGenerator(rng)

    # Generate records
    cases_records = case_gen.generate_cases(ground_truth)
    persons_records, victims_records = person_gen.generate_persons_and_victims(ground_truth)
    cdr_records, chat_records = comm_gen.generate_communications(ground_truth)
    movement_records = mov_gen.generate_movements(ground_truth, persons_records)
    vehicle_records = veh_gen.generate_vehicle_records(ground_truth, persons_records)
    device_records = dev_gen.generate_device_logs(ground_truth)
    financial_records = fin_gen.generate_financial_transactions(ground_truth)
    social_records = soc_gen.generate_social_media(ground_truth)
    evidence_records = ev_gen.generate_evidence_metadata(ground_truth)

    # 3. Export Evidence CSVs
    export_csv(evidence_dir / "cases.csv", cases_records, [
        "case_id", "case_type", "reported_date", "incident_date",
        "origin_location", "destination_location", "status", "agency", "priority"
    ])
    export_csv(evidence_dir / "persons.csv", persons_records, [
        "person_id", "name", "alias", "age_group", "role",
        "phone_id", "device_id", "address", "occupation", "case_id"
    ])
    export_csv(evidence_dir / "victims.csv", victims_records, [
        "victim_id", "case_id", "age_group", "reported_location",
        "last_known_location", "recruitment_channel", "status", "sensitive_flag"
    ])
    export_csv(evidence_dir / "cdr.csv", cdr_records, [
        "cdr_id", "timestamp", "caller", "receiver",
        "duration_sec", "call_type", "cell_tower", "case_id"
    ])
    export_csv(evidence_dir / "chat_logs.csv", chat_records, [
        "message_id", "timestamp", "sender", "receiver",
        "message_text", "platform", "language", "case_id"
    ])
    export_csv(evidence_dir / "travel_movements.csv", movement_records, [
        "movement_id", "person_id", "vehicle_id", "timestamp",
        "source", "destination", "transport_mode", "evidence_source", "case_id"
    ])
    export_csv(evidence_dir / "vehicle_records.csv", vehicle_records, [
        "vehicle_id", "registration_no", "vehicle_type", "owner_id",
        "driver_id", "timestamp", "location", "case_id"
    ])
    export_csv(evidence_dir / "device_logs.csv", device_records, [
        "device_id", "imei", "phone_id", "ip_address",
        "timestamp", "location", "case_id"
    ])
    export_csv(evidence_dir / "financial_transactions.csv", financial_records, [
        "transaction_id", "timestamp", "sender_account", "receiver_account",
        "amount", "transaction_type", "reference", "case_id"
    ])
    export_csv(evidence_dir / "social_media.csv", social_records, [
        "account_id", "username", "platform", "linked_phone",
        "linked_email", "created_date", "location", "case_id"
    ])
    export_csv(evidence_dir / "evidence.csv", evidence_records, [
        "evidence_id", "case_id", "evidence_type", "source_file",
        "timestamp", "sha256_hash", "extraction_method", "reliability", "chain_of_custody"
    ])

    # 4. Export Ground Truth Files (Strictly Isolated)
    export_json(ground_truth_dir / "ground_truth.json", ground_truth)
    export_json(ground_truth_dir / "true_entities.json", ground_truth["entities"])
    export_json(ground_truth_dir / "true_relationships.json", ground_truth["relationships"])
    export_json(ground_truth_dir / "true_case_links.json", ground_truth["case_links"])
    export_json(ground_truth_dir / "true_roles.json", ground_truth["true_roles"])

    # 5. Compute Key Statistics
    cross_case_entities = [e for e in ground_truth["entities"] if len(e["case_memberships"]) > 1]
    num_cross_case = len(cross_case_entities)
    pct_cross_case = (num_cross_case / len(ground_truth["entities"])) * 100

    # Strict isolation check: Verify no "GLOBAL_" string in any evidence CSV
    for csv_file in evidence_dir.glob("*.csv"):
        with open(csv_file, "r", encoding="utf-8") as f:
            content = f.read()
            if "GLOBAL_ENT" in content or "GLOBAL_VIC" in content:
                raise ValueError(f"CRITICAL ISOLATION BREACH: Latent global entity ID leaked into {csv_file.name}!")

    print("\n" + "="*50)
    print("Dataset generated successfully")
    print("="*50)
    print(f"Cases: {len(cases_records)}")
    print(f"Persons: {len(persons_records)}")
    print(f"Victims: {len(victims_records)}")
    print(f"CDRs: {len(cdr_records):,}")
    print(f"Chats: {len(chat_records):,}")
    print(f"Movements: {len(movement_records):,}")
    print(f"Vehicles: {len(vehicle_records):,}")
    print(f"Transactions: {len(financial_records):,}")
    print(f"Social accounts: {len(social_records):,}")
    print(f"Evidence records: {len(evidence_records):,}")
    print("")
    print(f"Cross-case entities: {num_cross_case} ({pct_cross_case:.1f}% of latent entities)")
    print(f"Criminal networks: 2 active syndicates (Network Alpha & Network Beta)")
    print(f"Independent cases: {len(NETWORK_CLUSTERS['INDEPENDENT']['cases'])}")
    print("="*50 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synthetic Criminal Network Data Generator (SIH26189)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for deterministic generation")
    parser.add_argument("--evidence-dir", type=str, default=str(EVIDENCE_DIR), help="Output directory for evidence CSVs")
    parser.add_argument("--ground-truth-dir", type=str, default=str(GROUND_TRUTH_DIR), help="Output directory for ground truth JSONs")
    args = parser.parse_args()

    run_pipeline(
        seed=args.seed,
        evidence_dir=Path(args.evidence_dir),
        ground_truth_dir=Path(args.ground_truth_dir)
    )
