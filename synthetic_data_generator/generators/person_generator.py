"""
Person Generator: Generates persons.csv and victims.csv evidence files.
Uses case-scoped observational identifiers (e.g. CASE_001_PER_01) to strictly prevent
leaking latent global entity IDs while allowing downstream Entity Resolution.

Strictly protects against Role Leakage: Evidence roles are purely observational
police procedural designations (e.g. 'Suspect', 'Person of Interest', 'Witness / Associate')
and occupations are standard observable trades, NEVER canonical ground truth roles
(e.g., recruiter, coordinator, transporter, financier, mastermind).
"""

import random
from typing import Dict, List, Any, Tuple

# Observational procedural roles documented in police case diaries / FIRs
OBSERVATIONAL_POLICE_ROLES = [
    "Suspect",
    "Accused (Named in FIR)",
    "Person of Interest",
    "Witness / Associate",
    "Contact Under Scrutiny",
    "Informant / Caller",
    "Acquaintance",
]

OBSERVATIONAL_OCCUPATIONS = [
    "Travel Agency Staff", "Commercial Driver", "Shop Assistant", "Self-Employed",
    "Office Clerk", "Tea Stall Owner", "Property Broker", "Bus Ticket Clerk",
    "Automobile Mechanic", "Unemployed", "Warehouse Staff", "Hotel Desk Attendant"
]

class PersonGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_persons_and_victims(self, ground_truth: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Produces records for persons.csv and victims.csv
        """
        entities = ground_truth["entities"]
        victims = ground_truth["victims"]
        obs_mapping = ground_truth["observational_mapping"]
        phones = ground_truth["phones"]
        devices = ground_truth["devices"]

        # Build lookup for primary phone and device per entity
        ent_phone_map = {}
        for p in phones:
            owner_id = p["primary_owner_global_id"]
            if owner_id not in ent_phone_map:
                ent_phone_map[owner_id] = p["phone_id"]

        ent_device_map = {}
        for d in devices:
            owner_id = d["primary_owner_global_id"]
            if owner_id not in ent_device_map:
                ent_device_map[owner_id] = d["device_id"]

        evidence_persons = []

        # Generate persons.csv records
        for ent in entities:
            g_id = ent["global_id"]
            mapping_info = obs_mapping[g_id]
            p_phone = ent_phone_map.get(g_id, "PH_UNVERIFIED")
            p_device = ent_device_map.get(g_id, "DEV_UNVERIFIED")

            for c_id, instance_data in mapping_info["case_instances"].items():
                obs_person_id = instance_data["observational_person_id"]
                vis_name = instance_data["visible_name"]
                vis_alias = instance_data["visible_alias"]

                # Assign purely procedural/investigative role
                if ent["true_role"] in ["coordinator", "recruiter", "financier", "transporter"]:
                    case_role = self.rng.choice(["Suspect", "Accused (Named in FIR)", "Person of Interest"])
                elif ent["true_role"] in ["local_associate", "document_facilitator"]:
                    case_role = self.rng.choice(["Contact Under Scrutiny", "Person of Interest", "Suspect"])
                else:
                    case_role = self.rng.choice(["Witness / Associate", "Acquaintance", "Informant / Caller"])

                # Observed occupation (strictly benign real-world trade)
                occ = ent.get("occupation", self.rng.choice(OBSERVATIONAL_OCCUPATIONS))
                # Sanitize occupation to ensure no canonical roles leaked
                if any(w in occ.lower() for w in ["coordinator", "recruiter", "transporter", "financier", "facilitator", "mastermind"]):
                    occ = "Small Business Owner"
                addr = ent["address"]

                evidence_persons.append({
                    "person_id": obs_person_id,
                    "name": vis_name,
                    "alias": vis_alias,
                    "age_group": ent["age_group"],
                    "role": case_role,
                    "phone_id": p_phone,
                    "device_id": p_device,
                    "address": addr,
                    "occupation": occ,
                    "case_id": c_id,
                })

        # Generate victims.csv records
        evidence_victims = []
        for v in victims:
            v_gid = v["global_victim_id"]
            v_map = obs_mapping[v_gid]
            obs_vic_id = v_map["observational_victim_id"]
            c_id = v["case_id"]

            evidence_victims.append({
                "victim_id": obs_vic_id,
                "case_id": c_id,
                "age_group": v["age_group"],
                "reported_location": v["reported_location"],
                "last_known_location": v["last_known_location"],
                "recruitment_channel": v["recruitment_channel"],
                "status": v["status"],
                "sensitive_flag": True,
            })

        evidence_persons.sort(key=lambda x: (x["case_id"], x["person_id"]))
        evidence_victims.sort(key=lambda x: (x["case_id"], x["victim_id"]))

        return evidence_persons, evidence_victims
