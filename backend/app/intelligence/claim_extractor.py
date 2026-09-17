"""
Phase 6B: Claim Extractor.
Deterministic, rule- and regex-based extraction of factual assertions from statement text.
Transforms unstructured witness, suspect, or informant statements into normalized
StructuredClaim models. Operates strictly without LLMs, external APIs, or probabilistic drift.
"""

import hashlib
import re
from typing import List, Optional, Tuple

from app.intelligence.claim_models import ClaimPredicate, StructuredClaim
from app.intelligence.claim_normalizer import ClaimNormalizer


# Negation detection patterns
NEGATION_PATTERNS = [
    r"\bdid\s+not\b",
    r"\bdidn'?t\b",
    r"\bnever\b",
    r"\bno\s+contact\b",
    r"\bhaven'?t\b",
    r"\bhave\s+not\b",
    r"\bwas\s+not\b",
    r"\bwasn'?t\b",
    r"\bnot\s+at\b",
    r"\bnot\s+in\b",
    r"\bnot\s+present\b",
    r"\bdo\s+not\b",
    r"\bdon'?t\b",
    r"\bdenies\b",
    r"\bdenied\b",
]

# Predicate trigger patterns
CALLED_PATTERNS = [
    r"\bcalled\b",
    r"\bcall\b",
    r"\bphoned\b",
    r"\bphone\b",
    r"\bplaced\s+a\s+call\s+to\b",
    r"\bplace\s+a\s+call\b",
    r"\bspoke\s+to\b",
    r"\bspoke\s+with\b",
    r"\bspeak\s+to\b",
    r"\bspeak\s+with\b",
    r"\btalked\s+to\b",
    r"\btalk\s+to\b",
    r"\btelephoned\b",
    r"\btelephone\b",
    r"\bphone\s+contact\b",
]

CONTACTED_PATTERNS = [
    r"\bmessaged\b",
    r"\bmessage\b",
    r"\btexted\b",
    r"\btext\b",
    r"\bcontacted\b",
    r"\bcontact\b",
    r"\bchatted\s+with\b",
    r"\bchat\s+with\b",
    r"\bsent\s+(?:a\s+)?message\s+to\b",
    r"\bsend\s+(?:a\s+)?message\s+to\b",
    r"\bcommunicated\s+with\b",
    r"\bcommunicate\s+with\b",
    r"\bwhatsapp(?:ed)?\b",
    r"\btelegram\b",
]

TRANSFERRED_PATTERNS = [
    r"\btransferred\b",
    r"\btransfer\b",
    r"\bsent\s+(?:money|funds|rs\.?|inr|\d+)\b",
    r"\bsend\s+(?:money|funds|rs\.?|inr|\d+)\b",
    r"\bpaid\b",
    r"\bpay\b",
    r"\bdeposited\b",
    r"\bdeposit\b",
    r"\bremitted\b",
    r"\bremit\b",
    r"\btransaction\b",
]

TRAVELLED_PATTERNS = [
    r"\btravelled\s+to\b",
    r"\btraveled\s+to\b",
    r"\btravel\s+to\b",
    r"\bwent\s+to\b",
    r"\bgo\s+to\b",
    r"\bboarded\b",
    r"\bboard\b",
    r"\btook\s+(?:a\s+)?(?:train|bus|flight|cab|taxi|vehicle)\s+to\b",
    r"\btake\s+(?:a\s+)?(?:train|bus|flight|cab|taxi|vehicle)\s+to\b",
    r"\bjourneyed\s+to\b",
    r"\bjourney\s+to\b",
    r"\barrived\s+in\b",
    r"\barrived\s+at\b",
    r"\barrive\s+in\b",
    r"\barrive\s+at\b",
]

LOCATED_PATTERNS = [
    r"\bwas\s+in\b",
    r"\bwas\s+at\b",
    r"\bbe\s+in\b",
    r"\bbe\s+at\b",
    r"\bstayed\s+in\b",
    r"\bstayed\s+at\b",
    r"\bstay\s+in\b",
    r"\bstay\s+at\b",
    r"\bpresent\s+in\b",
    r"\bpresent\s+at\b",
    r"\bresided\s+in\b",
    r"\breside\s+in\b",
    r"\blived\s+in\b",
    r"\blive\s+in\b",
    r"\blocation\b",
]

ASSOCIATED_PATTERNS = [
    r"\bknows\b",
    r"\bknow\b",
    r"\bknew\b",
    r"\bassociated\s+with\b",
    r"\bassociate\s+with\b",
    r"\bmet\s+with\b",
    r"\bmeet\s+with\b",
    r"\bmet\b",
    r"\bmeet\b",
    r"\bpartner\s+of\b",
    r"\baffiliated\s+with\b",
    r"\bfriend\s+of\b",
]


class ClaimExtractor:
    """
    Extracts structured relational assertions from investigative statement texts.
    """

    def __init__(self, normalizer: Optional[ClaimNormalizer] = None):
        self.normalizer = normalizer or ClaimNormalizer.get_instance()

    def extract_claims(
        self,
        statement_text: str,
        case_id: str,
        subject_entity_id: Optional[str] = None,
        source_document_id: str = "Unavailable",
    ) -> List[StructuredClaim]:
        """
        Parses statement text into individual sentences and extracts structured claims.
        """
        claims: List[StructuredClaim] = []
        if not statement_text or not statement_text.strip():
            return claims

        # Split into sentences safely without breaking IP addresses or decimals
        raw_parts = re.split(r"\.\s+(?=[A-Z])|[\n;]+", statement_text)
        sentences = [
            s.strip(" .\t\r\n")
            for s in raw_parts
            if len(s.strip(" .\t\r\n")) > 5
        ]

        if not sentences and statement_text.strip():
            sentences = [statement_text.strip(" .\t\r\n")]

        for sent_idx, sentence in enumerate(sentences):
            extracted = self._extract_single_sentence(
                sentence=sentence,
                case_id=case_id,
                default_subject=subject_entity_id,
                source_document_id=source_document_id,
                index=sent_idx,
            )
            if extracted:
                claims.append(extracted)

        return claims

    def _extract_single_sentence(
        self,
        sentence: str,
        case_id: str,
        default_subject: Optional[str],
        source_document_id: str,
        index: int,
    ) -> Optional[StructuredClaim]:
        """Extracts a StructuredClaim from a single sentence or clause."""
        sent_lower = sentence.lower()

        # 1. Detect Negation
        is_negated = any(re.search(pat, sent_lower) for pat in NEGATION_PATTERNS)

        # 2. Detect Predicate
        predicate = None
        if any(re.search(pat, sent_lower) for pat in CALLED_PATTERNS):
            predicate = ClaimPredicate.CALLED
        elif any(re.search(pat, sent_lower) for pat in CONTACTED_PATTERNS):
            predicate = ClaimPredicate.CONTACTED
        elif any(re.search(pat, sent_lower) for pat in TRANSFERRED_PATTERNS):
            predicate = ClaimPredicate.TRANSFERRED_TO
        elif any(re.search(pat, sent_lower) for pat in TRAVELLED_PATTERNS):
            predicate = ClaimPredicate.TRAVELLED_TO
        elif any(re.search(pat, sent_lower) for pat in LOCATED_PATTERNS):
            predicate = ClaimPredicate.LOCATED_AT
        elif any(re.search(pat, sent_lower) for pat in ASSOCIATED_PATTERNS):
            predicate = ClaimPredicate.ASSOCIATED_WITH

        # 3. Resolve Subject Entity
        subject_id = default_subject
        subj_conf = 1.0 if default_subject else 0.5

        # Check if an explicit subject is stated at start of sentence, e.g. "Aarav Gupta stated..." or "CASE_001_PER_01 says..."
        first_token_match = re.match(r"^([A-Za-z0-9_]+(?:\s+[A-Za-z0-9_]+)?)\s+(?:stated|said|claimed|says|claims|confessed|denies)", sentence)
        if first_token_match:
            candidate_sub = first_token_match.group(1)
            pid, conf, _ = self.normalizer.normalize_person_entity(candidate_sub, case_id)
            if pid:
                subject_id = pid
                subj_conf = conf

        # If still no subject, check for pronouns "I", "We" -> default to provided default_subject or placeholder
        if not subject_id:
            if default_subject:
                subject_id = default_subject
            else:
                subject_id = f"{case_id}_PER_UNKNOWN"
                subj_conf = 0.40

        # 4. Resolve Object Entity / Phone / Account / Location
        object_id = None
        location_id = None
        obj_conf = 1.0

        # Check for phone number
        phone_match = re.search(r"(\+?91[\d\s-]{10,12}|\b\d{10}\b)", sentence)
        if phone_match:
            norm_phone = self.normalizer.normalize_phone_number(phone_match.group(1))
            if norm_phone:
                object_id = norm_phone

        # Check for bank account
        account_match = re.search(r"\b(ACC_[A-Za-z0-9_]+)\b", sentence, re.IGNORECASE)
        if account_match:
            norm_acc = self.normalizer.normalize_bank_account(account_match.group(1))
            if norm_acc:
                object_id = norm_acc

        # Check for target person if predicate involves a person and not yet found
        if not object_id and predicate in (ClaimPredicate.CALLED, ClaimPredicate.CONTACTED, ClaimPredicate.TRANSFERRED_TO, ClaimPredicate.ASSOCIATED_WITH):
            # Scan for words matching known person names or aliases
            words = [w.strip(" ,.;:\"'") for w in sentence.split()]
            for i in range(len(words)):
                candidate = words[i]
                if i + 1 < len(words):
                    candidate_pair = f"{words[i]} {words[i+1]}"
                    pid, conf, _ = self.normalizer.normalize_person_entity(candidate_pair, case_id)
                    if pid and pid != subject_id:
                        object_id = pid
                        obj_conf = conf
                        break
                pid, conf, _ = self.normalizer.normalize_person_entity(candidate, case_id)
                if pid and pid != subject_id:
                    object_id = pid
                    obj_conf = conf
                    break

        # Check for location
        location_id = self.normalizer.normalize_location(sentence)
        # If predicate is TRAVELLED_TO or LOCATED_AT, but no canonical location found, try extracting destination
        if not location_id and predicate in (ClaimPredicate.TRAVELLED_TO, ClaimPredicate.LOCATED_AT):
            loc_match = re.search(r"\b(?:to|in|at)\s+([A-Z][a-zA-Z\s]+)", sentence)
            if loc_match:
                candidate_loc = loc_match.group(1).strip().split()[0]
                location_id = self.normalizer.normalize_location(candidate_loc) or candidate_loc

        # 5. Extract Temporal Window
        time_start, time_end, time_conf = self.normalizer.parse_time_window(sentence)

        # 6. Compute Extraction and Entity Confidence
        extraction_conf = 0.50
        if predicate is not None:
            extraction_conf += 0.30
        if time_start is not None:
            extraction_conf += 0.10
        if object_id is not None or location_id is not None:
            extraction_conf += 0.10
        extraction_conf = min(1.0, extraction_conf)

        entity_match_conf = min(subj_conf, obj_conf) if object_id else subj_conf

        # Deterministic Claim ID
        raw_hash = hashlib.sha256(f"{case_id}_{subject_id}_{predicate}_{object_id}_{location_id}_{time_start}_{is_negated}_{sentence}".encode("utf-8")).hexdigest()[:12]
        claim_id = f"CLM_{case_id}_{raw_hash}"

        return StructuredClaim(
            claim_id=claim_id,
            case_id=case_id,
            source_document_id=source_document_id,
            subject_entity_id=subject_id,
            predicate=predicate,
            object_entity_id=object_id,
            time_start=time_start,
            time_end=time_end,
            location_id=location_id,
            negated=is_negated,
            raw_text=sentence,
            extraction_method="RULE_BASED",
            claim_extraction_confidence=round(extraction_conf, 3),
            entity_match_confidence=round(entity_match_conf, 3),
        )
