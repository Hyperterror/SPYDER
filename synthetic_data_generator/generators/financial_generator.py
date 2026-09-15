"""
Financial Generator: Generates financial_transactions.csv.
Models fund routing (advances, operational transit logistics, mule accounts, UPI/IMPS).
Properly scopes transactions to cases where sender/receiver are active, while modeling:
- True cross-case financial links (financier/coordinator moving funds across syndicate cases)
- Case-local merchant/personal transactions
- Legitimate shared utility/transit portal account
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from config import TARGET_CONFIG

TXN_PURPOSES = [
    "ADVANCE_LODGING", "TRAVEL_EXPENSE", "PLACEMENT_REG_FEE",
    "TICKETING_REIMBURSE", "LOGISTICS_SETTLEMENT", "COMMISSION_SPLIT",
    "OFFICE_RENT_PAYMENT", "MONTHLY_MAINTENANCE"
]

# Legitimate common utility/transit portal account (coincidental overlap across independent cases)
SHARED_UTILITY_ACCOUNT = "ACC_SBI_IRCTC_099"

class FinancialGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_financial_transactions(self, ground_truth: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Produces records for financial_transactions.csv
        """
        accounts = ground_truth["bank_accounts"]
        entities = ground_truth["entities"]
        cases = ground_truth["cases"]
        relationships = ground_truth["relationships"]
        total_txns = TARGET_CONFIG["num_financial_transactions"]

        ent_cases_map = {e["global_id"]: e["case_memberships"] for e in entities}
        case_list = [c["case_id"] for c in cases]

        # Map owner global ID to account IDs
        owner_to_accs = {}
        acc_to_cases = {}
        for acc in accounts:
            owner_id = acc["owner_global_id"]
            owner_to_accs.setdefault(owner_id, []).append(acc["account_id"])
            acc_to_cases[acc["account_id"]] = ent_cases_map.get(owner_id, ["CASE_001"])

        all_acc_ids = [a["account_id"] for a in accounts]

        # Financial edges from ground truth (e.g. Financier -> Recruiter / Transporter)
        fin_edges = [r for r in relationships if r["type"] in ["AUTHORIZES_FUNDS", "DISBURSES_PAYMENT"]]

        txns = []
        base_time = datetime(2025, 2, 1, 10, 0, 0)

        for t_idx in range(1, total_txns + 1):
            if fin_edges and self.rng.random() < 0.60:
                edge = self.rng.choice(fin_edges)
                s_accs = owner_to_accs.get(edge["source"], all_acc_ids)
                r_accs = owner_to_accs.get(edge["target"], all_acc_ids)
                sender = self.rng.choice(s_accs)
                receiver = self.rng.choice(r_accs)
                amount = self.rng.choice([15000, 25000, 30000, 45000, 50000, 75000, 120000])
                t_type = self.rng.choice(["IMPS Transfer", "NEFT Settlement", "UPI P2P"])
                
                # Assign to common case if exists, else one active case
                s_cases = set(ent_cases_map.get(edge["source"], []))
                t_cases = set(ent_cases_map.get(edge["target"], []))
                common_cases = list(s_cases.intersection(t_cases))
                if common_cases:
                    c_id = self.rng.choice(common_cases)
                else:
                    all_c = list(s_cases.union(t_cases))
                    c_id = self.rng.choice(all_c) if all_c else case_list[0]
            elif self.rng.random() < 0.05:
                # Payment to shared utility / IRCTC rail ticketing portal
                sender = self.rng.choice(all_acc_ids)
                receiver = SHARED_UTILITY_ACCOUNT
                amount = self.rng.choice([1200, 2450, 3100, 4800])
                t_type = "UPI P2P"
                c_id = self.rng.choice(acc_to_cases.get(sender, case_list))
            else:
                # Case-local background transaction
                c_id = self.rng.choice(case_list)
                case_accs = [acc_id for acc_id, c_ids in acc_to_cases.items() if c_id in c_ids]
                if len(case_accs) >= 2:
                    sender, receiver = self.rng.sample(case_accs, 2)
                else:
                    sender = self.rng.choice(all_acc_ids)
                    receiver = self.rng.choice(all_acc_ids)
                amount = self.rng.choice([1500, 3200, 5000, 8000, 10000, 18000, 22000])
                t_type = self.rng.choice(["UPI P2P", "ATM Cash Withdrawal", "IMPS Transfer"])

            purpose = self.rng.choice(TXN_PURPOSES)
            ref_id = f"UTR{self.rng.randint(100000000000, 999999999999)}/{purpose}"

            time_offset = timedelta(
                days=self.rng.randint(0, 180),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59),
                seconds=self.rng.randint(0, 59)
            )
            txn_dt = base_time + time_offset

            txns.append({
                "transaction_id": f"TXN_{t_idx:05d}",
                "timestamp": txn_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "sender_account": sender,
                "receiver_account": receiver,
                "amount": amount,
                "transaction_type": t_type,
                "reference": ref_id,
                "case_id": c_id,
            })

        txns.sort(key=lambda x: x["timestamp"])
        return txns
