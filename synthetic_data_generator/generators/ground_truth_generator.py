"""
Ground Truth Generator: Generates the hidden latent criminal network, entities,
syndicates, true relationships, cross-case links, and hard negatives.
"""

import random
from typing import Dict, List, Any, Tuple
from config import NETWORK_CLUSTERS, ROLES, TARGET_CONFIG

# Curated synthetic Indian names (explicitly fictional)
FIRST_NAMES_MALE = [
    "Aarav", "Kabir", "Mohit", "Sunil", "Rakesh", "Deepak", "Vikram", "Manoj",
    "Sanjay", "Anil", "Pankaj", "Rajesh", "Amit", "Santosh", "Dinesh", "Mukesh",
    "Ashok", "Gopal", "Kamal", "Vinod", "Harish", "Tarun", "Subhash", "Mahesh"
]
FIRST_NAMES_FEMALE = [
    "Pooja", "Sunita", "Anita", "Kavita", "Rekha", "Meena", "Geeta", "Babita",
    "Mamta", "Suman", "Seema", "Neelam", "Renu", "Shobha", "Sarita", "Usha"
]
LAST_NAMES = [
    "Sharma", "Verma", "Kumar", "Yadav", "Singh", "Ghosh", "Mandal", "Das",
    "Gupta", "Mishra", "Patel", "Thakur", "Prasad", "Saha", "Biswas", "Roy",
    "Choudhury", "Poddar", "Mahato", "Khatun", "Soren", "Murmu", "Tiwari"
]

ALIASES_POOL = [
    "Bhaiya", "Chhotu", "Ustad", "Doctor", "Vicky", "Rocky", "Raju", "Sethji",
    "Captain", "Pandit", "Mama", "Tiger", "Munna", "Guru", "Kaka", "Babu",
    "Sonu", "Master", "Shooter", "Netaji", "Pradhan", "Didi", "Madam", "Agent"
]

OCCUPATIONS = [
    "Travel Agent", "Placement Agent", "Tour Operator", "Labor Contractor",
    "Property Broker", "Transporter", "Hotel Manager", "Tea Stall Owner",
    "Security Guard", "Auto Driver", "Cloth Merchant", "Mobile Repair Shop Owner",
    "Unemployed", "NGO Volunteer", "Factory Supervisor", "Driver"
]

ADDRESS_AREAS = [
    "Station Road", "Gandhi Nagar", "Subhash Chowk", "Bazaar Road", "Industrial Area Phase 1",
    "Railway Colony", "Near Bus Terminus", "Transport Nagar", "Civil Lines", "New Basti"
]

class GroundTruthGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_ground_truth(self) -> Dict[str, Any]:
        """
        Creates the complete latent criminal network, global entities,
        cross-case memberships, and true relationship graphs.
        """
        cases = self._init_cases()
        entities = self._generate_latent_entities(cases)
        victims = self._generate_latent_victims(cases)
        phones = self._generate_latent_phones(entities)
        devices = self._generate_latent_devices(entities, phones)
        vehicles = self._generate_latent_vehicles(entities)
        bank_accounts = self._generate_latent_bank_accounts(entities)
        social_accounts = self._generate_latent_social_accounts(entities, phones)
        
        # Build relational graph edges and case links
        relationships = self._generate_latent_relationships(
            entities, victims, phones, devices, vehicles, bank_accounts
        )
        case_links = self._generate_latent_case_links(cases, entities)
        true_roles = self._build_true_roles(entities, victims)

        # Build mapping of global entity -> observational representations in evidence
        observational_mapping = self._build_observational_mapping(entities, victims)

        ground_truth = {
            "networks": NETWORK_CLUSTERS,
            "cases": cases,
            "entities": entities,
            "victims": victims,
            "phones": phones,
            "devices": devices,
            "vehicles": vehicles,
            "bank_accounts": bank_accounts,
            "social_accounts": social_accounts,
            "relationships": relationships,
            "case_links": case_links,
            "true_roles": true_roles,
            "observational_mapping": observational_mapping,
            "hard_negatives": self._extract_hard_negative_registry(entities),
        }
        return ground_truth

    def _init_cases(self) -> List[Dict[str, Any]]:
        case_list = []
        for net_key, net_data in NETWORK_CLUSTERS.items():
            for c_id in net_data["cases"]:
                case_list.append({
                    "case_id": c_id,
                    "network_cluster": net_key,
                    "crime_type": net_data["crime_type"],
                    "locations": net_data["focus_locations"]
                })
        case_list.sort(key=lambda x: x["case_id"])
        return case_list

    def _generate_latent_entities(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        total_target = TARGET_CONFIG["num_global_entities"]
        entities = []
        
        # 1. Syndicate Alpha entities (Trafficking Syndicate: 4 cases)
        alpha_cases = NETWORK_CLUSTERS["NETWORK_ALPHA"]["cases"]
        # 2. Syndicate Beta entities (Placement Agency Racket: 3 cases)
        beta_cases = NETWORK_CLUSTERS["NETWORK_BETA"]["cases"]
        # 3. Independent cases (3 isolated cases)
        indep_cases = NETWORK_CLUSTERS["INDEPENDENT"]["cases"]

        ent_idx = 1

        # We designate specific entities for Cross-Case recurrence in Alpha (11 entities):
        alpha_cross_entities = [
            ("coordinator", alpha_cases),                                      # spans all 4
            ("financier", [alpha_cases[0], alpha_cases[2], alpha_cases[3]]),   # spans 3
            ("financier", [alpha_cases[1], alpha_cases[2]]),                   # spans 2
            ("transporter", [alpha_cases[0], alpha_cases[1], alpha_cases[2]]), # spans 3
            ("transporter", [alpha_cases[0], alpha_cases[3]]),                 # spans 2
            ("transporter", [alpha_cases[1], alpha_cases[3]]),                 # spans 2
            ("recruiter", [alpha_cases[0], alpha_cases[1], alpha_cases[3]]),   # spans 3
            ("recruiter", [alpha_cases[0], alpha_cases[2]]),                   # spans 2
            ("recruiter", [alpha_cases[1], alpha_cases[2]]),                   # spans 2
            ("document_facilitator", [alpha_cases[1], alpha_cases[3]]),        # spans 2
            ("local_associate", [alpha_cases[0], alpha_cases[2]]),             # spans 2
        ]

        # Beta cross-case entities (8 entities):
        beta_cross_entities = [
            ("coordinator", beta_cases),                                       # spans all 3
            ("recruiter", [beta_cases[0], beta_cases[1]]),                     # spans 2
            ("recruiter", [beta_cases[1], beta_cases[2]]),                     # spans 2
            ("financier", [beta_cases[0], beta_cases[2]]),                     # spans 2
            ("financier", [beta_cases[1], beta_cases[2]]),                     # spans 2
            ("transporter", [beta_cases[0], beta_cases[1]]),                   # spans 2
            ("transporter", [beta_cases[0], beta_cases[2]]),                   # spans 2
            ("local_associate", [beta_cases[1], beta_cases[2]]),               # spans 2
        ]

        # Allocate syndicate entities
        for role, member_cases in alpha_cross_entities:
            ent = self._create_entity(ent_idx, "NETWORK_ALPHA", role, member_cases)
            entities.append(ent)
            ent_idx += 1

        for role, member_cases in beta_cross_entities:
            ent = self._create_entity(ent_idx, "NETWORK_BETA", role, member_cases)
            entities.append(ent)
            ent_idx += 1

        # Allocate single-case syndicate associates
        for c_id in alpha_cases:
            # Add 2-3 local associates / recruiters / legitimate contacts
            for r in ["recruiter", "local_associate", "legitimate_contact"]:
                ent = self._create_entity(ent_idx, "NETWORK_ALPHA", r, [c_id])
                entities.append(ent)
                ent_idx += 1

        for c_id in beta_cases:
            for r in ["recruiter", "local_associate", "legitimate_contact"]:
                ent = self._create_entity(ent_idx, "NETWORK_BETA", r, [c_id])
                entities.append(ent)
                ent_idx += 1

        # Allocate independent case entities
        for c_id in indep_cases:
            # Independent cases get 5-6 localized entities
            for r in ["coordinator", "recruiter", "transporter", "local_associate", "legitimate_contact", "legitimate_contact"]:
                ent = self._create_entity(ent_idx, "INDEPENDENT", r, [c_id])
                entities.append(ent)
                ent_idx += 1

        # Fill remaining up to total_target with legitimate contacts & associates
        while ent_idx <= total_target:
            cluster = self.rng.choice(["NETWORK_ALPHA", "NETWORK_BETA", "INDEPENDENT"])
            c_id = self.rng.choice(NETWORK_CLUSTERS[cluster]["cases"])
            role = self.rng.choice(["legitimate_contact", "local_associate", "transporter"])
            ent = self._create_entity(ent_idx, cluster, role, [c_id])
            entities.append(ent)
            ent_idx += 1

        # INJECT HARD NEGATIVES:
        # Pair 1: Ramesh Chand (Recruiter in Alpha) vs Ramesh Chand (Tea Vendor / Legitimate contact in Independent CASE_004)
        alpha_ent = [e for e in entities if e["network_cluster"] == "NETWORK_ALPHA" and e["true_role"] == "recruiter"][0]
        alpha_ent["true_name"] = "Ramesh Chand"
        alpha_ent["canonical_alias"] = "Ramu"
        alpha_ent["is_hard_negative"] = True
        alpha_ent["hard_negative_group"] = "HN_GROUP_RAMESH"

        indep_ent = [e for e in entities if e["network_cluster"] == "INDEPENDENT" and e["true_role"] == "legitimate_contact"][0]
        indep_ent["true_name"] = "Ramesh Chand"
        indep_ent["canonical_alias"] = "Ramu Kaka"
        indep_ent["occupation"] = "Tea Stall Owner"
        indep_ent["is_hard_negative"] = True
        indep_ent["hard_negative_group"] = "HN_GROUP_RAMESH"

        # Pair 2: Vicky Alias (Vikramaditya Rao in Beta) vs Vicky Alias (Vikram Rathore in Independent CASE_006)
        beta_coord = [e for e in entities if e["network_cluster"] == "NETWORK_BETA" and e["true_role"] == "coordinator"][0]
        beta_coord["true_name"] = "Vikramaditya Rao"
        beta_coord["canonical_alias"] = "Vicky"
        beta_coord["is_hard_negative"] = True
        beta_coord["hard_negative_group"] = "HN_GROUP_VICKY"

        indep_ent2 = [e for e in entities if e["network_cluster"] == "INDEPENDENT" and e["case_memberships"] == ["CASE_006"]][0]
        indep_ent2["true_name"] = "Vikram Rathore"
        indep_ent2["canonical_alias"] = "Vicky"
        indep_ent2["occupation"] = "Auto Driver"
        indep_ent2["is_hard_negative"] = True
        indep_ent2["hard_negative_group"] = "HN_GROUP_VICKY"

        # Pair 3: Sunil Verma (Alpha transporter) vs Sunil K. Verma (Beta legitimate transport clerk)
        alpha_trans = [e for e in entities if e["network_cluster"] == "NETWORK_ALPHA" and e["true_role"] == "transporter"][0]
        alpha_trans["true_name"] = "Sunil Verma"
        alpha_trans["canonical_alias"] = "Ustad"
        alpha_trans["is_hard_negative"] = True
        alpha_trans["hard_negative_group"] = "HN_GROUP_SUNIL"

        beta_legit = [e for e in entities if e["network_cluster"] == "NETWORK_BETA" and e["true_role"] == "legitimate_contact"][0]
        beta_legit["true_name"] = "Sunil K. Verma"
        beta_legit["canonical_alias"] = "Vermaji"
        beta_legit["occupation"] = "Bus Ticket Clerk"
        beta_legit["is_hard_negative"] = True
        beta_legit["hard_negative_group"] = "HN_GROUP_SUNIL"

        return entities

    def _create_entity(self, idx: int, cluster: str, role: str, case_memberships: List[str]) -> Dict[str, Any]:
        is_female = (role == "victim") or (self.rng.random() < 0.25)
        fname = self.rng.choice(FIRST_NAMES_FEMALE if is_female else FIRST_NAMES_MALE)
        lname = self.rng.choice(LAST_NAMES)
        true_name = f"{fname} {lname}"
        alias = self.rng.choice(ALIASES_POOL) if self.rng.random() < 0.70 else None
        
        loc_pool = NETWORK_CLUSTERS[cluster]["focus_locations"]
        base_city = self.rng.choice(loc_pool)
        address = f"{self.rng.randint(12, 450)}, {self.rng.choice(ADDRESS_AREAS)}, {base_city}"
        
        age_group = self.rng.choice(["18-25", "26-35", "36-50", "50+"])
        occupation = self.rng.choice(OCCUPATIONS) if role != "coordinator" else "Agency Proprietor"

        return {
            "global_id": f"GLOBAL_ENT_{idx:03d}",
            "true_name": true_name,
            "canonical_alias": alias,
            "age_group": age_group,
            "true_role": role,
            "network_cluster": cluster,
            "case_memberships": case_memberships,
            "base_city": base_city,
            "address": address,
            "occupation": occupation,
            "is_hard_negative": False,
            "hard_negative_group": None,
        }

    def _generate_latent_victims(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        victims = []
        vic_count = TARGET_CONFIG["num_victims"]
        for v_idx in range(1, vic_count + 1):
            c_entry = self.rng.choice(cases)
            c_id = c_entry["case_id"]
            cluster = c_entry["network_cluster"]
            locs = c_entry["locations"]

            reported_loc = locs[0]
            last_loc = locs[-1] if len(locs) > 1 else locs[0]

            recruitment_channel = self.rng.choice([
                "Social Media Job Advertisement",
                "Placement Agency Lure",
                "Acquaintance Referral",
                "Marriage Proposal Fraud",
                "Hospitality Trainee Offer",
            ])
            status = self.rng.choice(["Rescued", "Missing", "Identified in Transit", "Under Protective Shelter"])

            victims.append({
                "global_victim_id": f"GLOBAL_VIC_{v_idx:03d}",
                "case_id": c_id,
                "network_cluster": cluster,
                "age_group": self.rng.choice(["Minor (14-17)", "Young Adult (18-22)", "Adult (23-30)"]),
                "reported_location": reported_loc,
                "last_known_location": last_loc,
                "recruitment_channel": recruitment_channel,
                "status": status,
                "sensitive_flag": True,
            })
        return victims

    def _generate_latent_phones(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        phones = []
        ph_idx = 1
        # Primary phone for each entity
        for ent in entities:
            num_phones = 2 if ent["true_role"] in ["coordinator", "recruiter", "financier"] else 1
            for _ in range(num_phones):
                msisdn = f"+91{self.rng.choice(['98', '97', '99', '94', '88'])}{self.rng.randint(10000000, 99999999)}"
                phones.append({
                    "phone_id": f"PH_{ph_idx:03d}",
                    "phone_number": msisdn,
                    "primary_owner_global_id": ent["global_id"],
                    "service_provider": self.rng.choice(["Airtel", "Jio", "Vodafone-Idea", "BSNL"]),
                    "sim_type": "Prepaid Burner" if ent["true_role"] in ["recruiter", "transporter"] else "Regular Postpaid",
                    "is_shared": False,
                    "co_users": []
                })
                ph_idx += 1

        # Create coincidental / shared identifier:
        # A burner phone shared between a coordinator and transporter in Network Alpha
        alpha_transporters = [e for e in entities if e["network_cluster"] == "NETWORK_ALPHA" and e["true_role"] == "transporter"]
        alpha_coordinators = [e for e in entities if e["network_cluster"] == "NETWORK_ALPHA" and e["true_role"] == "coordinator"]
        if alpha_transporters and alpha_coordinators:
            shared_ph = phones[0]
            shared_ph["is_shared"] = True
            shared_ph["co_users"] = [alpha_transporters[0]["global_id"]]

        # Fill up to target
        while len(phones) < TARGET_CONFIG["num_phones"]:
            msisdn = f"+91{self.rng.choice(['98', '97', '99', '94', '88'])}{self.rng.randint(10000000, 99999999)}"
            phones.append({
                "phone_id": f"PH_{ph_idx:03d}",
                "phone_number": msisdn,
                "primary_owner_global_id": self.rng.choice(entities)["global_id"],
                "service_provider": self.rng.choice(["Airtel", "Jio", "Vodafone-Idea", "BSNL"]),
                "sim_type": "Prepaid Burner",
                "is_shared": False,
                "co_users": []
            })
            ph_idx += 1

        return phones

    def _generate_latent_devices(self, entities: List[Dict[str, Any]], phones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        devices = []
        dev_idx = 1
        for p_idx, phone in enumerate(phones[:TARGET_CONFIG["num_devices"]]):
            imei = f"86{self.rng.randint(1000000000000, 9999999999999)}"
            device_model = self.rng.choice(["Samsung Galaxy A14", "Redmi Note 12", "Realme C55", "Vivo Y20", "Nokia 105", "OnePlus Nord"])
            devices.append({
                "device_id": f"DEV_{dev_idx:03d}",
                "imei": imei,
                "device_model": device_model,
                "linked_phone_id": phone["phone_id"],
                "primary_owner_global_id": phone["primary_owner_global_id"],
                "is_shared": (dev_idx == 10), # e.g. One transit cyber cafe / shop shared device
            })
            dev_idx += 1
        return devices

    def _generate_latent_vehicles(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        vehicles = []
        transporters = [e for e in entities if e["true_role"] in ["transporter", "local_associate", "coordinator"]]
        veh_count = TARGET_CONFIG["num_vehicles"]
        
        state_codes = ["DL", "WB", "JH", "UP", "HR", "RJ", "BR"]
        
        for v_idx in range(1, veh_count + 1):
            owner = self.rng.choice(transporters) if transporters else self.rng.choice(entities)
            driver = owner if self.rng.random() < 0.6 else self.rng.choice(entities)
            st = self.rng.choice(state_codes)
            reg_no = f"{st}-{self.rng.randint(1, 99):02d}-{self.rng.choice(['AB', 'AX', 'CA', 'DL', 'TR'])}-{self.rng.randint(1000, 9999)}"
            v_type = self.rng.choice(["White Bolero SUV", "Maruti Ertiga MPV", "Force Traveller Van", "Tata Sumo", "Private Sleeper Bus", "Auto Rickshaw"])
            
            vehicles.append({
                "vehicle_id": f"VEH_{v_idx:03d}",
                "registration_no": reg_no,
                "vehicle_type": v_type,
                "owner_global_id": owner["global_id"],
                "driver_global_id": driver["global_id"],
                "network_cluster": owner["network_cluster"],
            })
        return vehicles

    def _generate_latent_bank_accounts(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        accounts = []
        banks = ["SBI", "HDFC", "ICICI", "PNB", "Bank of Baroda", "Axis Bank", "Canara Bank", "Paytm Payments Bank"]
        acc_idx = 1
        for ent in entities:
            # Financiers and coordinators have 2-3 accounts (including mule accounts)
            num_acc = 3 if ent["true_role"] in ["financier", "coordinator"] else 1
            for _ in range(num_acc):
                bank = self.rng.choice(banks)
                acc_num = f"{self.rng.randint(1000000000, 9999999999)}"
                acc_id = f"ACC_{bank[:3].upper()}_{acc_num[-4:]}_{acc_idx:03d}"
                accounts.append({
                    "account_id": acc_id,
                    "account_number": acc_num,
                    "bank_name": bank,
                    "owner_global_id": ent["global_id"],
                    "is_mule": (ent["true_role"] == "financier" and self.rng.random() < 0.5),
                    "network_cluster": ent["network_cluster"],
                })
                acc_idx += 1
                if len(accounts) >= TARGET_CONFIG["num_bank_accounts"]:
                    break
            if len(accounts) >= TARGET_CONFIG["num_bank_accounts"]:
                break
        return accounts

    def _generate_latent_social_accounts(self, entities: List[Dict[str, Any]], phones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        social_accounts = []
        platforms = ["Facebook", "Instagram", "WhatsApp", "Telegram", "LinkedIn"]
        phone_map = {p["primary_owner_global_id"]: p["phone_number"] for p in phones}
        
        soc_idx = 1
        # Give initial accounts to entities
        for ent in entities:
            if len(social_accounts) >= TARGET_CONFIG["num_social_accounts"]:
                break
            num_soc = 2 if ent["true_role"] in ["recruiter", "coordinator"] else 1
            for _ in range(num_soc):
                plat = self.rng.choice(platforms)
                base_tag = ent["canonical_alias"] or ent["true_name"].split()[0]
                base_clean = "".join([c for c in base_tag.lower() if c.isalnum()])
                user_handle = f"@{base_clean}_{self.rng.randint(10, 999)}"
                email_domain = self.rng.choice(["gmail.com", "outlook.com", "yahoo.com", "fastmail.com"])
                email = f"{base_clean}{self.rng.randint(100, 999)}@{email_domain}"
                
                social_accounts.append({
                    "account_id": f"SOC_{soc_idx:03d}",
                    "username": user_handle,
                    "platform": plat,
                    "linked_phone": phone_map.get(ent["global_id"], None),
                    "linked_email": email,
                    "owner_global_id": ent["global_id"],
                    "location": ent["base_city"],
                    "network_cluster": ent["network_cluster"],
                })
                soc_idx += 1
                if len(social_accounts) >= TARGET_CONFIG["num_social_accounts"]:
                    break

        # If any slots remain, allocate secondary accounts to active recruiters/coordinators
        while len(social_accounts) < TARGET_CONFIG["num_social_accounts"]:
            ent = self.rng.choice(entities)
            plat = self.rng.choice(platforms)
            base_tag = ent["canonical_alias"] or ent["true_name"].split()[0]
            base_clean = "".join([c for c in base_tag.lower() if c.isalnum()])
            user_handle = f"@{base_clean}_{self.rng.randint(1000, 9999)}"
            email_domain = self.rng.choice(["gmail.com", "outlook.com", "yahoo.com"])
            email = f"{base_clean}{self.rng.randint(1000, 9999)}@{email_domain}"
            social_accounts.append({
                "account_id": f"SOC_{soc_idx:03d}",
                "username": user_handle,
                "platform": plat,
                "linked_phone": phone_map.get(ent["global_id"], None),
                "linked_email": email,
                "owner_global_id": ent["global_id"],
                "location": ent["base_city"],
                "network_cluster": ent["network_cluster"],
            })
            soc_idx += 1
        return social_accounts

    def _generate_latent_relationships(
        self, entities: List[Dict[str, Any]], victims: List[Dict[str, Any]],
        phones: List[Dict[str, Any]], devices: List[Dict[str, Any]],
        vehicles: List[Dict[str, Any]], bank_accounts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        relationships = []
        
        # 1. Operational hierarchy relationships within clusters
        ent_by_cluster = {}
        for e in entities:
            ent_by_cluster.setdefault(e["network_cluster"], []).append(e)

        for cluster_key, group in ent_by_cluster.items():
            coords = [e for e in group if e["true_role"] == "coordinator"]
            recs = [e for e in group if e["true_role"] == "recruiter"]
            trans = [e for e in group if e["true_role"] == "transporter"]
            fins = [e for e in group if e["true_role"] == "financier"]
            docs = [e for e in group if e["true_role"] == "document_facilitator"]

            # Coordinator -> Recruiter
            for c in coords:
                for r in recs:
                    relationships.append({
                        "source": c["global_id"],
                        "target": r["global_id"],
                        "type": "COORDINATES_WITH",
                        "weight": 0.9,
                        "cluster": cluster_key
                    })
                for t in trans:
                    relationships.append({
                        "source": c["global_id"],
                        "target": t["global_id"],
                        "type": "DIRECTS_TRANSPORT",
                        "weight": 0.85,
                        "cluster": cluster_key
                    })
                for f in fins:
                    relationships.append({
                        "source": c["global_id"],
                        "target": f["global_id"],
                        "type": "AUTHORIZES_FUNDS",
                        "weight": 0.95,
                        "cluster": cluster_key
                    })
            
            # Recruiter -> Transporter
            for r in recs:
                for t in trans:
                    if self.rng.random() < 0.6:
                        relationships.append({
                            "source": r["global_id"],
                            "target": t["global_id"],
                            "type": "HANDS_OVER_TRANSIT",
                            "weight": 0.8,
                            "cluster": cluster_key
                        })
            
            # Financier -> Recruiter / Transporter (advance payments)
            for f in fins:
                for recipient in recs + trans:
                    relationships.append({
                        "source": f["global_id"],
                        "target": recipient["global_id"],
                        "type": "DISBURSES_PAYMENT",
                        "weight": 0.75,
                        "cluster": cluster_key
                    })

        # 2. Recruiter -> Victim relationships
        for v in victims:
            cluster = v["network_cluster"]
            matching_recs = [e for e in ent_by_cluster.get(cluster, []) if e["true_role"] == "recruiter"]
            if matching_recs:
                rec = self.rng.choice(matching_recs)
                relationships.append({
                    "source": rec["global_id"],
                    "target": v["global_victim_id"],
                    "type": "RECRUITS_OR_LURES",
                    "weight": 1.0,
                    "cluster": cluster
                })

        return relationships

    def _generate_latent_case_links(self, cases: List[Dict[str, Any]], entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Builds the ground-truth case-to-case link matrix.
        Two cases are genuinely linked if they belong to the same syndicate and share entities.
        Independent cases have 0 links to the syndicates.
        """
        case_links = []
        case_ids = [c["case_id"] for c in cases]

        for i in range(len(case_ids)):
            for j in range(i + 1, len(case_ids)):
                c1, c2 = case_ids[i], case_ids[j]
                
                # Find shared global entities between c1 and c2
                shared_ents = [
                    e["global_id"] for e in entities
                    if c1 in e["case_memberships"] and c2 in e["case_memberships"]
                ]

                c1_cluster = next(c["network_cluster"] for c in cases if c["case_id"] == c1)
                c2_cluster = next(c["network_cluster"] for c in cases if c["case_id"] == c2)

                is_genuine_link = (c1_cluster == c2_cluster) and (c1_cluster != "INDEPENDENT") and (len(shared_ents) > 0)

                if is_genuine_link:
                    case_links.append({
                        "case_a": c1,
                        "case_b": c2,
                        "is_linked": True,
                        "syndicate_cluster": c1_cluster,
                        "shared_global_entities_count": len(shared_ents),
                        "shared_global_entities": shared_ents,
                        "relationship_description": f"Syndicate co-membership in {c1_cluster}"
                    })
                else:
                    # Unrelated case pair
                    case_links.append({
                        "case_a": c1,
                        "case_b": c2,
                        "is_linked": False,
                        "syndicate_cluster": None,
                        "shared_global_entities_count": 0,
                        "shared_global_entities": [],
                        "relationship_description": "Unrelated independent operations"
                    })

        return case_links

    def _build_true_roles(self, entities: List[Dict[str, Any]], victims: List[Dict[str, Any]]) -> Dict[str, str]:
        roles_map = {}
        for e in entities:
            roles_map[e["global_id"]] = e["true_role"]
        for v in victims:
            roles_map[v["global_victim_id"]] = "victim"
        return roles_map

    def _build_observational_mapping(self, entities: List[Dict[str, Any]], victims: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Builds the hidden mapping from global entity ID -> observational case-scoped IDs.
        Crucial for ground-truth evaluation later.
        """
        mapping = {}
        case_person_counters = {}

        for e in entities:
            g_id = e["global_id"]
            mapping[g_id] = {
                "global_id": g_id,
                "true_name": e["true_name"],
                "true_role": e["true_role"],
                "network_cluster": e["network_cluster"],
                "case_instances": {}
            }

            for c_id in e["case_memberships"]:
                case_person_counters[c_id] = case_person_counters.get(c_id, 0) + 1
                seq = case_person_counters[c_id]
                obs_id = f"{c_id}_PER_{seq:02d}"

                # Generate noisy name variations for each appearance
                name_variant = self._generate_noisy_name(e["true_name"], e["canonical_alias"])
                alias_obs = e["canonical_alias"] if self.rng.random() < 0.75 else ""

                mapping[g_id]["case_instances"][c_id] = {
                    "observational_person_id": obs_id,
                    "visible_name": name_variant,
                    "visible_alias": alias_obs,
                    "case_id": c_id
                }

        # Victim observational mapping
        case_vic_counters = {}
        for v in victims:
            v_gid = v["global_victim_id"]
            c_id = v["case_id"]
            case_vic_counters[c_id] = case_vic_counters.get(c_id, 0) + 1
            seq = case_vic_counters[c_id]
            obs_vic_id = f"{c_id}_VIC_{seq:02d}"

            mapping[v_gid] = {
                "global_victim_id": v_gid,
                "case_id": c_id,
                "observational_victim_id": obs_vic_id,
            }

        return mapping

    def _generate_noisy_name(self, true_name: str, alias: str) -> str:
        parts = true_name.split()
        if len(parts) < 2:
            return true_name
        first, last = parts[0], parts[1]
        
        style = self.rng.choice(["full", "initial", "concat", "mononym", "spelling_variant"])
        if style == "full":
            return true_name
        elif style == "initial":
            return f"{first[0]}. {last}"
        elif style == "concat":
            return f"{first}{last}"
        elif style == "mononym":
            return first
        else: # minor phonetic variant
            vowels = {"a": "aa", "ee": "i", "i": "ee", "u": "oo", "o": "aw"}
            for v, repl in vowels.items():
                if v in first:
                    return f"{first.replace(v, repl, 1)} {last}"
            return true_name

    def _extract_hard_negative_registry(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hn_list = []
        for e in entities:
            if e.get("is_hard_negative"):
                hn_list.append({
                    "global_id": e["global_id"],
                    "true_name": e["true_name"],
                    "canonical_alias": e["canonical_alias"],
                    "true_role": e["true_role"],
                    "network_cluster": e["network_cluster"],
                    "case_memberships": e["case_memberships"],
                    "hard_negative_group": e["hard_negative_group"]
                })
        return hn_list
