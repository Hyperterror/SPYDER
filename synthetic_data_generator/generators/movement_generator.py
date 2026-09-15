"""
Movement Generator: Generates travel_movements.csv.
Models the transit routes of persons (using case-scoped person IDs) across origin,
transit hubs, and destination exploitation locations.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from config import TARGET_CONFIG

EVIDENCE_SOURCES = [
    "Highway Toll RFID / FASTag Log",
    "Railway Reservation Chart",
    "Interstate Border Checkpoint ANPR",
    "Bus Terminal Manifest",
    "Hotel Guest Register Scan",
    "CCTV Transit Terminal Log"
]

ROUTE_CORRIDORS = [
    ("Murshidabad", "Kolkata", "Interstate Train"),
    ("Kolkata", "New Delhi", "Interstate Train"),
    ("Siliguri", "Patna", "Sleeper Bus"),
    ("Ranchi", "Anand Vihar (Delhi)", "Private SUV"),
    ("Patna", "Gurugram", "Private SUV"),
    ("Chandigarh", "Panipat", "Interstate Bus"),
    ("Jaipur", "Delhi NCR", "Private SUV"),
    ("Agra", "Kanpur", "Interstate Bus"),
    ("Bhopal", "Gwalior", "Interstate Train"),
]

class MovementGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_movements(self, ground_truth: Dict[str, Any], evidence_persons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Produces records for travel_movements.csv
        """
        vehicles = ground_truth["vehicles"]
        cases = ground_truth["cases"]
        total_movements = TARGET_CONFIG["num_movements"]

        # Map persons by case_id for foreign-key consistency
        persons_by_case = {}
        for p in evidence_persons:
            persons_by_case.setdefault(p["case_id"], []).append(p["person_id"])

        veh_ids = [v["vehicle_id"] for v in vehicles]
        movements = []
        base_time = datetime(2025, 2, 10, 6, 0, 0)

        for m_idx in range(1, total_movements + 1):
            c_entry = self.rng.choice(cases)
            c_id = c_entry["case_id"]
            
            # Select an observational person associated with this case
            candidate_persons = persons_by_case.get(c_id, [])
            person_id = self.rng.choice(candidate_persons) if candidate_persons else f"{c_id}_PER_01"

            src, dest, default_mode = self.rng.choice(ROUTE_CORRIDORS)
            transport_mode = default_mode if self.rng.random() < 0.75 else self.rng.choice(["Private SUV", "Sleeper Bus", "Interstate Train"])
            
            # Vehicle ID only associated when transport mode is vehicle-based
            if "SUV" in transport_mode or "Bus" in transport_mode:
                vehicle_id = self.rng.choice(veh_ids)
            else:
                vehicle_id = ""

            ev_source = self.rng.choice(EVIDENCE_SOURCES)

            time_offset = timedelta(
                days=self.rng.randint(0, 180),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59)
            )
            move_dt = base_time + time_offset

            movements.append({
                "movement_id": f"MOV_{m_idx:05d}",
                "person_id": person_id,
                "vehicle_id": vehicle_id,
                "timestamp": move_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "source": src,
                "destination": dest,
                "transport_mode": transport_mode,
                "evidence_source": ev_source,
                "case_id": c_id,
            })

        movements.sort(key=lambda x: x["timestamp"])
        return movements
