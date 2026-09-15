"""
Vehicle Generator: Generates vehicle_records.csv.
Captures vehicle sighting logs, FASTag/toll readings, and ANPR checkpoint records.
Vehicle registrations serve as key recurring observable signals across cases.
Correctly scopes vehicle sightings to owner/driver case memberships, plus legitimate
interstate commercial transport corridors.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from config import TARGET_CONFIG

TOLL_LOCATIONS = [
    "NH-19 Dankuni Toll Plaza (Kolkata Outskirts)",
    "NH-27 Ghoshpukur Toll Plaza (Siliguri)",
    "NH-44 Murthal Toll Plaza (Delhi-Haryana Border)",
    "Badarpur Border Toll Plaza (Delhi-Faridabad)",
    "KMP Expressway Toll Plaza (Gurugram)",
    "NH-33 Bundu Checkpoint (Ranchi Highway)",
    "Yamuna Expressway Jewar Toll Plaza (Agra-Noida)",
    "Shahjahanpur Toll Plaza (Rajasthan Border)"
]

class VehicleGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_vehicle_records(self, ground_truth: Dict[str, Any], evidence_persons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Produces records for vehicle_records.csv
        """
        latent_vehicles = ground_truth["vehicles"]
        entities = ground_truth["entities"]
        cases = ground_truth["cases"]
        obs_mapping = ground_truth["observational_mapping"]
        total_records = TARGET_CONFIG["num_vehicle_records"]

        ent_cases_map = {e["global_id"]: e["case_memberships"] for e in entities}
        case_list = [c["case_id"] for c in cases]

        # Map person global IDs to case-scoped observational IDs
        persons_by_case = {}
        for p in evidence_persons:
            persons_by_case.setdefault(p["case_id"], []).append(p["person_id"])

        records = []
        base_time = datetime(2025, 2, 12, 4, 0, 0)

        for r_idx in range(1, total_records + 1):
            veh = self.rng.choice(latent_vehicles)
            owner_gid = veh["owner_global_id"]
            driver_gid = veh["driver_global_id"]

            owner_cases = ent_cases_map.get(owner_gid, [case_list[0]])
            driver_cases = ent_cases_map.get(driver_gid, [case_list[0]])
            valid_cases = list(set(owner_cases + driver_cases))

            # Sighting occurs primarily within active cases of owner/driver
            # (with small chance for commercial bus to be captured on corridor toll)
            if "Bus" in veh["vehicle_type"] and self.rng.random() < 0.15:
                c_id = self.rng.choice(case_list)
            else:
                c_id = self.rng.choice(valid_cases)

            owner_map = obs_mapping.get(owner_gid, {}).get("case_instances", {}).get(c_id)
            driver_map = obs_mapping.get(driver_gid, {}).get("case_instances", {}).get(c_id)

            candidate_case_persons = persons_by_case.get(c_id, [])
            default_p = candidate_case_persons[0] if candidate_case_persons else f"{c_id}_PER_01"

            owner_id = owner_map["observational_person_id"] if owner_map else default_p
            driver_id = driver_map["observational_person_id"] if driver_map else default_p

            time_offset = timedelta(
                days=self.rng.randint(0, 180),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59)
            )
            obs_dt = base_time + time_offset
            location = self.rng.choice(TOLL_LOCATIONS)

            records.append({
                "vehicle_id": veh["vehicle_id"],
                "registration_no": veh["registration_no"],
                "vehicle_type": veh["vehicle_type"],
                "owner_id": owner_id,
                "driver_id": driver_id,
                "timestamp": obs_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "location": location,
                "case_id": c_id,
            })

        records.sort(key=lambda x: x["timestamp"])
        return records
