"""
Case Generator: Produces cases.csv representing official FIR / investigation case records.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from config import AGENCIES, PRIORITIES, STATUSES

class CaseGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_cases(self, ground_truth: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generates evidence records for cases.csv
        Fields:
        case_id, case_type, reported_date, incident_date, origin_location, destination_location, status, agency, priority
        """
        raw_cases = ground_truth["cases"]
        evidence_cases = []

        base_time = datetime(2025, 1, 10, 9, 30)

        for idx, c in enumerate(raw_cases):
            c_id = c["case_id"]
            c_type = c["crime_type"]
            locs = c["locations"]

            # Incident date slightly precedes reported date
            days_offset = idx * 28 + self.rng.randint(2, 10)
            incident_dt = base_time + timedelta(days=days_offset)
            reported_dt = incident_dt + timedelta(days=self.rng.randint(1, 14), hours=self.rng.randint(2, 8))

            origin = locs[0]
            dest = locs[-1] if len(locs) > 1 else locs[0]

            agency = self.rng.choice(AGENCIES)
            priority = "Critical" if c["network_cluster"] == "NETWORK_ALPHA" else self.rng.choice(PRIORITIES)
            status = self.rng.choice(STATUSES)

            evidence_cases.append({
                "case_id": c_id,
                "case_type": c_type,
                "reported_date": reported_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "incident_date": incident_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "origin_location": origin,
                "destination_location": dest,
                "status": status,
                "agency": agency,
                "priority": priority,
            })

        return evidence_cases
