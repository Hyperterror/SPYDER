"""
Communication Generator: Generates cdr.csv and chat_logs.csv.
Reflects latent communication edges between phone numbers of syndicate members.
Properly scopes case calls to that case's entities and case-local background numbers,
ensuring realistic and informative cross-case identifier overlap rather than overwhelming noise.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from config import TARGET_CONFIG

TOWERS = [
    "TWR-DL-ANANDVIHAR-01", "TWR-DL-KASHMEREGATE-04", "TWR-DL-MAHIPALPUR-09",
    "TWR-WB-HOWRAH-02", "TWR-WB-SEALDAH-05", "TWR-WB-SILIGURI-11", "TWR-WB-MALDA-03",
    "TWR-JH-RANCHI-08", "TWR-JH-DHANBAD-14", "TWR-HR-GURUGRAM-07", "TWR-HR-PANIPAT-12",
    "TWR-UP-AGRA-06", "TWR-UP-KANPUR-15", "TWR-RJ-JAIPUR-10", "TWR-BR-PATNA-13"
]

CHAT_TEMPLATES = [
    ("Send the photo and Aadhaar copy of the candidate immediately.", "English"),
    ("Tickets confirmed for 3 persons on 12302 train coach S3.", "English"),
    ("Advance 25000 transfer kar diya hai account me check karo.", "Hinglish"),
    ("Vehicle will reach highway toll plaza by 04:30 AM.", "English"),
    ("Ladki ko reception desk par handover karna hai, phone switch off rakho.", "Hinglish"),
    ("New placement registration slip ready. Tell family everything is legal.", "English"),
    ("Mule account details shared on Telegram. Route the payment through UPI.", "English"),
    ("Driver reached destination border post. Awaiting clearance.", "English"),
    ("Do not call on this regular SIM. Call only via encrypted app.", "English"),
    ("Keep the safehouse room locked from outside until further instructions.", "English"),
    ("Interview scheduled in Delhi tomorrow morning. Ensure travel is on time.", "English"),
    ("Gadi Anand Vihar station ke bahar khadi hai, jaldi aao.", "Hinglish"),
    ("Family is asking for location update. Give standard company excuse.", "English"),
    ("Cash delivered to Kolkata agent. Token number verified.", "English"),
    ("Change SIM card tonight after crossing state border.", "English"),
]

BACKGROUND_MESSAGES = [
    ("Will reach home in 10 minutes.", "English"),
    ("Payment received for tea stall delivery.", "English"),
    ("Call you back after lunch.", "English"),
    ("Send grocery list on WhatsApp.", "English"),
    ("Bhai recharge kar dena 299 wala.", "Hinglish"),
    ("Meeting postponed to tomorrow 3 PM.", "English"),
]

# Common transit helpline numbers (legitimate coincidental cross-case overlap)
COINCIDENTAL_HOTLINES = ["+911123010000", "+911800112233"]

class CommunicationGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_communications(self, ground_truth: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Produces records for cdr.csv and chat_logs.csv
        """
        phones = ground_truth["phones"]
        entities = ground_truth["entities"]
        relationships = ground_truth["relationships"]
        cases = ground_truth["cases"]

        ent_to_phones = {}
        for p in phones:
            owner = p["primary_owner_global_id"]
            ent_to_phones.setdefault(owner, []).append(p["phone_number"])
            for co_user in p.get("co_users", []):
                ent_to_phones.setdefault(co_user, []).append(p["phone_number"])

        ent_cases_map = {e["global_id"]: e["case_memberships"] for e in entities}

        # Build case-scoped communication pairs:
        # Calls are attributed to cases where BOTH entities operate (if shared)
        # or to ONE specific case where either caller or receiver is investigated.
        comm_pairs_by_case = {c["case_id"]: [] for c in cases}
        for rel in relationships:
            s_cases = set(ent_cases_map.get(rel["source"], []))
            t_cases = set(ent_cases_map.get(rel["target"], []))
            common_cases = list(s_cases.intersection(t_cases))
            
            src_phones = ent_to_phones.get(rel["source"], [])
            tgt_phones = ent_to_phones.get(rel["target"], [])
            
            if src_phones and tgt_phones:
                p1 = self.rng.choice(src_phones)
                p2 = self.rng.choice(tgt_phones)
                if common_cases:
                    for cid in common_cases:
                        if cid in comm_pairs_by_case:
                            comm_pairs_by_case[cid].append((p1, p2))
                else:
                    # Interstate link: assign to the specific primary case
                    all_c = list(s_cases.union(t_cases))
                    if all_c:
                        cid = self.rng.choice(all_c)
                        if cid in comm_pairs_by_case:
                            comm_pairs_by_case[cid].append((p1, p2))

        # Generate dedicated local background numbers for each case (isolated to that case)
        local_numbers_by_case = {}
        for c in cases:
            cid = c["case_id"]
            local_nums = [
                f"+91{self.rng.choice(['70', '72', '80', '85'])}{self.rng.randint(10000000, 99999999)}"
                for _ in range(12)
            ]
            local_numbers_by_case[cid] = local_nums

        # Map entity phones per case
        case_entity_phones = {c["case_id"]: [] for c in cases}
        for ent in entities:
            e_phones = ent_to_phones.get(ent["global_id"], [])
            for cid in ent["case_memberships"]:
                if cid in case_entity_phones:
                    case_entity_phones[cid].extend(e_phones)

        # 1. Generate CDR Records (~2,000)
        total_cdrs = TARGET_CONFIG["num_cdrs"]
        cdr_records = []
        base_time = datetime(2025, 2, 1, 8, 0, 0)
        case_list = [c["case_id"] for c in cases]

        for i in range(1, total_cdrs + 1):
            c_id = self.rng.choice(case_list)
            pairs = comm_pairs_by_case.get(c_id, [])
            c_phones = case_entity_phones.get(c_id, [])
            loc_nums = local_numbers_by_case[c_id]

            dice = self.rng.random()
            if pairs and dice < 0.60:
                # Direct syndicate operational communication within this case
                p1, p2 = self.rng.choice(pairs)
                caller, receiver = (p1, p2) if self.rng.random() < 0.5 else (p2, p1)
            elif dice < 0.95 and c_phones:
                # Local background call (entity calling local taxi/vendor/shop in this case)
                p1 = self.rng.choice(c_phones)
                p2 = self.rng.choice(loc_nums)
                caller, receiver = (p1, p2) if self.rng.random() < 0.5 else (p2, p1)
            else:
                # Coincidental inquiry hotline call
                p1 = self.rng.choice(c_phones) if c_phones else self.rng.choice(loc_nums)
                caller, receiver = (p1, self.rng.choice(COINCIDENTAL_HOTLINES))

            time_offset = timedelta(
                days=self.rng.randint(0, 180),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59),
                seconds=self.rng.randint(0, 59)
            )
            call_dt = base_time + time_offset
            call_type = self.rng.choice(["Voice Outgoing", "Voice Incoming", "SMS Outgoing", "Missed Call"])
            duration = 0 if call_type in ["SMS Outgoing", "Missed Call"] else self.rng.randint(15, 840)
            tower = self.rng.choice(TOWERS)

            cdr_records.append({
                "cdr_id": f"CDR_{i:05d}",
                "timestamp": call_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "caller": caller,
                "receiver": receiver,
                "duration_sec": duration,
                "call_type": call_type,
                "cell_tower": tower,
                "case_id": c_id,
            })

        # 2. Generate Chat Logs (~1,000)
        total_chats = TARGET_CONFIG["num_chats"]
        chat_records = []
        chat_base_time = datetime(2025, 2, 5, 10, 0, 0)

        for j in range(1, total_chats + 1):
            c_id = self.rng.choice(case_list)
            pairs = comm_pairs_by_case.get(c_id, [])
            c_phones = case_entity_phones.get(c_id, [])
            loc_nums = local_numbers_by_case[c_id]

            if pairs and self.rng.random() < 0.70:
                p1, p2 = self.rng.choice(pairs)
                sender, receiver = (p1, p2) if self.rng.random() < 0.5 else (p2, p1)
                text, lang = self.rng.choice(CHAT_TEMPLATES)
            else:
                p1 = self.rng.choice(c_phones) if c_phones else self.rng.choice(loc_nums)
                p2 = self.rng.choice(loc_nums)
                sender, receiver = (p1, p2) if self.rng.random() < 0.5 else (p2, p1)
                text, lang = self.rng.choice(BACKGROUND_MESSAGES)

            time_offset = timedelta(
                days=self.rng.randint(0, 180),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59),
                seconds=self.rng.randint(0, 59)
            )
            chat_dt = chat_base_time + time_offset
            platform = self.rng.choice(["WhatsApp", "Telegram", "Signal", "SMS"])

            chat_records.append({
                "message_id": f"MSG_{j:05d}",
                "timestamp": chat_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "sender": sender,
                "receiver": receiver,
                "message_text": text,
                "platform": platform,
                "language": lang,
                "case_id": c_id,
            })

        cdr_records.sort(key=lambda x: x["timestamp"])
        chat_records.sort(key=lambda x: x["timestamp"])

        return cdr_records, chat_records
