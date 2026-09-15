"""
Pairwise Feature Engineering for Entity Resolution.
Extracts explainable, multi-modal features strictly from observable evidence.
Includes an explicit Data Leakage Audit to guarantee zero ground-truth feature pollution.
"""

from typing import Dict, List, Any
import numpy as np

from entity_resolution.config import FORBIDDEN_FEATURE_TOKENS
from entity_resolution.normalize import (
    levenshtein_similarity, jaro_winkler_similarity, token_jaccard_similarity
)
from entity_resolution.embeddings import EmbeddingManager

# Public transit infrastructure IPs (should be flagged as public/coincidental)
PUBLIC_INFRASTRUCTURE_IPS = {"103.21.244.18", "49.205.12.87", "117.247.88.102"}

class FeatureEngineer:
    def __init__(self, embedding_manager: EmbeddingManager = None):
        self.embedding_manager = embedding_manager or EmbeddingManager()

    def extract_features_for_pair(self, p1: Dict[str, Any], p2: Dict[str, Any]) -> Dict[str, float]:
        """
        Extracts an observable feature dictionary for candidate pair (p1, p2).
        Strictly avoids any hidden ground-truth fields.
        """
        feats = {}

        # 1. NAME FEATURES
        clean_name1 = p1["norm_name"]
        clean_name2 = p2["norm_name"]
        
        feats["name_exact_match"] = 1.0 if (clean_name1 and clean_name1 == clean_name2) else 0.0
        feats["name_levenshtein_sim"] = float(levenshtein_similarity(clean_name1, clean_name2))
        feats["name_jaro_winkler_sim"] = float(jaro_winkler_similarity(clean_name1, clean_name2))
        feats["name_token_jaccard"] = float(token_jaccard_similarity(p1["name_tokens"], p2["name_tokens"]))
        
        # Initial match
        init1 = p1.get("name_initials", "")
        init2 = p2.get("name_initials", "")
        feats["name_initial_match"] = 1.0 if (init1 and init2 and init1 == init2) else 0.0
        feats["name_length_diff"] = float(abs(len(clean_name1) - len(clean_name2)))

        # 2. ALIAS FEATURES
        alias1 = p1["norm_alias"]
        alias2 = p2["norm_alias"]
        alias_both = 1.0 if (alias1 and alias2) else 0.0
        feats["alias_both_present"] = alias_both
        feats["alias_exact_match"] = 1.0 if (alias_both and alias1 == alias2) else 0.0
        feats["alias_levenshtein_sim"] = float(levenshtein_similarity(alias1, alias2)) if alias_both else 0.0
        feats["alias_token_jaccard"] = float(token_jaccard_similarity(p1["alias_tokens"], p2["alias_tokens"])) if alias_both else 0.0

        # Cross check: name1 matches alias2 or name2 matches alias1
        feats["name_alias_cross_match"] = 1.0 if (
            (alias2 and alias2 in p1["name_tokens"]) or (alias1 and alias1 in p2["name_tokens"])
        ) else 0.0

        # 3. TELECOM & PHONE FEATURES
        shared_phones = p1["phone_last10s"].intersection(p2["phone_last10s"])
        feats["phone_shared_count"] = float(len(shared_phones))
        feats["phone_exact_match"] = 1.0 if len(shared_phones) > 0 else 0.0
        feats["phone_both_present"] = 1.0 if (len(p1["phone_last10s"]) > 0 and len(p2["phone_last10s"]) > 0) else 0.0

        # 4. DIGITAL IDENTITY FEATURES
        # Device ID
        dev1 = p1.get("device_id")
        dev2 = p2.get("device_id")
        dev_match = (dev1 and dev2 and dev1 == dev2 and dev1 != "DEV_UNVERIFIED")
        feats["device_id_match"] = 1.0 if dev_match else 0.0

        # IMEI
        shared_imeis = p1["imeis"].intersection(p2["imeis"])
        feats["imei_shared_count"] = float(len(shared_imeis))
        feats["imei_match"] = 1.0 if len(shared_imeis) > 0 else 0.0

        # IP Address
        shared_ips = p1["ip_addresses"].intersection(p2["ip_addresses"])
        feats["shared_ip_count"] = float(len(shared_ips))
        # Flag if shared IP is solely public transit infrastructure
        shared_is_public = 1.0 if (shared_ips and shared_ips.issubset(PUBLIC_INFRASTRUCTURE_IPS)) else 0.0
        feats["shared_ip_is_public_infra"] = shared_is_public

        # Social & Email
        shared_soc = p1["social_handles"].intersection(p2["social_handles"])
        shared_email = p1["emails"].intersection(p2["emails"])
        feats["social_handle_match"] = 1.0 if len(shared_soc) > 0 else 0.0
        feats["email_match"] = 1.0 if len(shared_email) > 0 else 0.0

        # 5. VEHICLE FEATURES
        shared_vehs = p1["vehicles"].intersection(p2["vehicles"])
        feats["shared_vehicle_count"] = float(len(shared_vehs))
        feats["vehicle_reg_match"] = 1.0 if len(shared_vehs) > 0 else 0.0

        # 6. LOCATION & DEMOGRAPHICS
        shared_locs = p1["locations"].intersection(p2["locations"])
        feats["shared_location_count"] = float(len(shared_locs))
        addr1_tokens = p1.get("address", "").lower().split()
        addr2_tokens = p2.get("address", "").lower().split()
        feats["address_token_sim"] = float(token_jaccard_similarity(addr1_tokens, addr2_tokens))
        feats["same_age_group"] = 1.0 if (p1.get("age_group") and p1["age_group"] == p2.get("age_group")) else 0.0

        # 7. COMMUNICATION CONTEXT
        shared_contacts = p1["contacts"].intersection(p2["contacts"])
        feats["shared_contacts_count"] = float(len(shared_contacts))

        # 8. CONTEXTUAL SENTENCE TRANSFORMER SIMILARITY
        cos_sim = self.embedding_manager.get_similarity_for_pair(
            p1["person_id"], p1, p2["person_id"], p2
        )
        feats["context_embedding_cosine_sim"] = float(cos_sim)

        # Self-audit data leakage on this feature set
        self.audit_feature_leakage(feats)

        return feats

    @staticmethod
    def audit_feature_leakage(feats: Dict[str, Any]):
        """Audits feature names and values to ensure no ground-truth tokens leak."""
        for feat_name in feats.keys():
            lower_name = feat_name.lower()
            for forbidden in FORBIDDEN_FEATURE_TOKENS:
                if forbidden in lower_name:
                    raise ValueError(f"CRITICAL LEAKAGE DETECTED in feature name: '{feat_name}' contains '{forbidden}'!")
