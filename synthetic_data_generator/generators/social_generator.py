"""
Social Generator: Generates social_media.csv.
Models online recruiting profiles, sham placement accounts, and linked contacts.
Usernames, linked phones, and emails serve as observable cross-case signals.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any

class SocialGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_social_media(self, ground_truth: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Produces records for social_media.csv
        """
        latent_social = ground_truth["social_accounts"]
        cases = ground_truth["cases"]
        ent_cases_map = {e["global_id"]: e["case_memberships"] for e in ground_truth["entities"]}

        records = []
        base_create_dt = datetime(2023, 6, 1)

        for soc in latent_social:
            owner_gid = soc["owner_global_id"]
            associated_cases = ent_cases_map.get(owner_gid, [self.rng.choice(cases)["case_id"]])
            # Assign to primary associated case or random
            c_id = self.rng.choice(associated_cases)

            created_dt = base_create_dt + timedelta(days=self.rng.randint(0, 500))

            records.append({
                "account_id": soc["account_id"],
                "username": soc["username"],
                "platform": soc["platform"],
                "linked_phone": soc["linked_phone"] or "",
                "linked_email": soc["linked_email"],
                "created_date": created_dt.strftime("%Y-%m-%d"),
                "location": soc["location"],
                "case_id": c_id,
            })

        records.sort(key=lambda x: x["account_id"])
        return records
