"""
Device Generator: Generates device_logs.csv.
Models forensic digital device traces (IMEI, associated Phone, IP addresses, cellular locations).
Properly scopes device traces to owner case memberships, while modeling:
- True cross-case device overlaps (entities operating across multiple cases)
- Shared noisy infrastructure (public lodge / cyber cafe shared IPs)
- Coincidental shared devices (cyber kiosk shared terminal)
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from config import TARGET_CONFIG

DEVICE_LOCATIONS = [
    "Delhi NCR - Mahipalpur Transit Lodge",
    "Delhi NCR - Anand Vihar ISBT",
    "Kolkata - Sealdah Railway Environs",
    "Kolkata - Howrah Station South Gate",
    "Siliguri - Junction Bus Stand",
    "Ranchi - Overbridge Commercial Complex",
    "Patna - Fraser Road cyber kiosk",
    "Gurugram - Cyber City Sector 29",
    "Panipat - GT Road Transit Inn",
    "Jaipur - Sindhi Camp Bus Terminal"
]

# Legitimate shared infrastructure IPs (Wi-Fi routers at transit lodges, cyber cafes, rail hotspots)
# A shared IP alone must NOT imply individual identity!
SHARED_INFRASTRUCTURE_IPS = [
    "103.21.244.18",    # Mahipalpur Transit Lodge Public Wi-Fi
    "49.205.12.87",     # Cyber Kiosk Shared Broadband
    "117.247.88.102",   # Railway Station Public Wi-Fi Hotspot
]

class DeviceGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_device_logs(self, ground_truth: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Produces records for device_logs.csv
        """
        latent_devices = ground_truth["devices"]
        entities = ground_truth["entities"]
        cases = ground_truth["cases"]
        total_logs = TARGET_CONFIG["num_device_logs"]

        ent_cases_map = {e["global_id"]: e["case_memberships"] for e in entities}
        case_list = [c["case_id"] for c in cases]

        # Map devices to their owners' cases
        dev_cases = {}
        for dev in latent_devices:
            owner_gid = dev["primary_owner_global_id"]
            owner_cases = ent_cases_map.get(owner_gid, ["CASE_001"])
            dev_cases[dev["device_id"]] = owner_cases

        logs = []
        base_time = datetime(2025, 2, 8, 9, 0, 0)

        for log_idx in range(1, total_logs + 1):
            dev = self.rng.choice(latent_devices)
            dev_id = dev["device_id"]
            owner_cases = dev_cases.get(dev_id, ["CASE_001"])

            if dev.get("is_shared", False):
                # Shared cyber kiosk device: can be used by persons across any case
                c_id = self.rng.choice(case_list)
            else:
                # Personal device: logs in the owner's case(s)
                c_id = self.rng.choice(owner_cases)

            # Assign IP: shared infrastructure vs private dynamic IP
            if self.rng.random() < 0.35:
                ip_addr = self.rng.choice(SHARED_INFRASTRUCTURE_IPS)
            else:
                ip_addr = f"{self.rng.randint(49, 182)}.{self.rng.randint(10, 250)}.{self.rng.randint(1, 254)}.{self.rng.randint(1, 254)}"

            time_offset = timedelta(
                days=self.rng.randint(0, 180),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59)
            )
            log_dt = base_time + time_offset
            location = self.rng.choice(DEVICE_LOCATIONS)

            logs.append({
                "device_id": dev_id,
                "imei": dev["imei"],
                "phone_id": dev["linked_phone_id"],
                "ip_address": ip_addr,
                "timestamp": log_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "location": location,
                "case_id": c_id,
            })

        logs.sort(key=lambda x: x["timestamp"])
        return logs
