"""
Phase 6B: Claim Normalizer.
Resolves and standardizes extracted entities, aliases, phone numbers, bank accounts,
geographical locations, dates/times, and negation indicators into canonical formats.
Strictly avoids auto-confirming ambiguous or uncertain identities.
"""

import csv
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.intelligence.config import REPO_ROOT
from app.intelligence.claim_models import ClaimPredicate

# Evidence dataset path
EVIDENCE_DIR = REPO_ROOT / "synthetic_data_generator" / "output" / "evidence_dataset"
PERSONS_CSV = EVIDENCE_DIR / "persons.csv"
NODES_CSV = REPO_ROOT / "output" / "graph_analysis" / "nodes.csv"


class ClaimNormalizer:
    """
    Normalizes entities, aliases, communication handles, locations, and time intervals.
    """

    _instance: Optional["ClaimNormalizer"] = None

    def __init__(self, persons_path: Path = PERSONS_CSV, nodes_path: Path = NODES_CSV):
        self.persons_path = Path(persons_path)
        self.nodes_path = Path(nodes_path)

        # Lookup tables: (name_or_alias_lower, case_id) -> list of person_ids
        self._name_to_persons: Dict[Tuple[str, Optional[str]], List[str]] = {}
        self._global_name_to_persons: Dict[str, List[str]] = {}
        self._person_to_details: Dict[str, dict] = {}
        self._phone_to_persons: Dict[str, List[str]] = {}
        self._device_to_persons: Dict[str, List[str]] = {}

        self._load_indexes()

    @classmethod
    def get_instance(cls) -> "ClaimNormalizer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_indexes(self) -> None:
        """Indexes known persons, names, aliases, phones, and devices from observable files."""
        if not self.persons_path.exists():
            return

        with open(self.persons_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row["person_id"]
                name = row.get("name", "").strip()
                alias = row.get("alias", "").strip()
                cid = row.get("case_id", "").strip()
                ph = row.get("phone_id", "").strip()
                dev = row.get("device_id", "").strip()

                self._person_to_details[pid] = row

                # Index name
                if name:
                    n_clean = name.lower()
                    self._name_to_persons.setdefault((n_clean, cid), []).append(pid)
                    self._global_name_to_persons.setdefault(n_clean, []).append(pid)

                # Index alias
                if alias and alias.lower() != "nan":
                    a_clean = alias.lower()
                    self._name_to_persons.setdefault((a_clean, cid), []).append(pid)
                    self._global_name_to_persons.setdefault(a_clean, []).append(pid)

                # Index phone ID & device ID
                if ph:
                    self._phone_to_persons.setdefault(ph, []).append(pid)
                if dev:
                    self._device_to_persons.setdefault(dev, []).append(pid)

    def normalize_person_entity(
        self,
        raw_mention: str,
        case_id: Optional[str] = None,
    ) -> Tuple[Optional[str], float, bool]:
        """
        Resolves an entity mention (name, alias, or ID) to a canonical person_id.
        Returns: (person_id, confidence, is_ambiguous)
        """
        mention = raw_mention.strip()
        if not mention:
            return None, 0.0, False

        # Direct person ID match (e.g. CASE_001_PER_01 or PROV_RES_ENT_001)
        if mention.startswith("CASE_") and "_PER_" in mention:
            return mention, 1.0, False
        if mention.startswith("PROV_RES_ENT_"):
            return mention, 0.95, False

        mention_lower = mention.lower()

        # Case-scoped lookup first
        if case_id:
            case_matches = self._name_to_persons.get((mention_lower, case_id), [])
            if len(case_matches) == 1:
                return case_matches[0], 0.95, False
            elif len(case_matches) > 1:
                return case_matches[0], 0.70, True  # Ambiguous within case

        # Global lookup across all cases
        global_matches = self._global_name_to_persons.get(mention_lower, [])
        if len(global_matches) == 1:
            return global_matches[0], 0.85, False
        elif len(global_matches) > 1:
            # Check if any belongs to the requested case
            if case_id:
                for pid in global_matches:
                    if self._person_to_details.get(pid, {}).get("case_id") == case_id:
                        return pid, 0.85, True
            return global_matches[0], 0.60, True  # Ambiguous across multiple cases

        # Partial token match (e.g., "Aarav" matches "Aarav Gupta")
        partial_matches = []
        for (name, cid), pids in self._name_to_persons.items():
            if case_id and cid != case_id:
                continue
            if mention_lower in name.split():
                partial_matches.extend(pids)

        if len(partial_matches) == 1:
            return partial_matches[0], 0.75, True
        elif len(partial_matches) > 1:
            return partial_matches[0], 0.50, True

        return None, 0.0, False

    def normalize_phone_number(self, raw_phone: str) -> Optional[str]:
        """Normalizes phone numbers to standard international format (e.g. +919416927215)."""
        clean = re.sub(r"[^\d+]", "", raw_phone)
        if clean.startswith("+91") and len(clean) == 13:
            return clean
        if clean.startswith("91") and len(clean) == 12:
            return f"+{clean}"
        if len(clean) == 10 and clean.isdigit():
            return f"+91{clean}"
        return clean if clean else None

    def normalize_bank_account(self, raw_account: str) -> Optional[str]:
        """Normalizes bank account identifiers to standard ACC_... format."""
        clean = raw_account.strip().upper()
        if re.match(r"^ACC_[A-Z]{3}_\d{4}_\d{3}$", clean):
            return clean
        if clean.startswith("ACC_"):
            return clean
        return None

    def normalize_location(self, raw_location: str) -> Optional[str]:
        """Standardizes geographical cities and transit points to canonical labels."""
        loc = raw_location.strip()
        loc_lower = loc.lower()

        CANONICAL_LOCATIONS = {
            "delhi": "Delhi",
            "new delhi": "New Delhi",
            "delhi ncr": "Delhi NCR",
            "anand vihar": "Anand Vihar",
            "kashmere gate": "Kashmere Gate",
            "kolkata": "Kolkata",
            "howrah": "Howrah",
            "sealdah": "Sealdah",
            "patna": "Patna",
            "ranchi": "Ranchi",
            "dhanbad": "Dhanbad",
            "jaipur": "Jaipur",
            "agra": "Agra",
            "kanpur": "Kanpur",
            "bhopal": "Bhopal",
            "gwalior": "Gwalior",
            "murshidabad": "Murshidabad",
            "malda": "Malda",
            "siliguri": "Siliguri",
            "gurugram": "Gurugram",
            "panipat": "Panipat",
        }

        for k in sorted(CANONICAL_LOCATIONS.keys(), key=len, reverse=True):
            if k in loc_lower:
                return CANONICAL_LOCATIONS[k]

        return loc.title() if loc else None

    def parse_time_window(
        self,
        raw_text: str,
        reference_year: int = 2025,
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Extracts temporal start and end window (ISO 8601 strings) from text.
        Tolerance is automatically adapted based on specified granularity (exact hour vs whole day).
        Returns: (time_start, time_end, confidence)
        """
        # 1. Look for ISO date YYYY-MM-DD
        date_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", raw_text)
        found_date = None
        if date_match:
            try:
                y, m, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                found_date = datetime(y, m, d)
            except ValueError:
                pass

        # 2. Look for word date e.g. "10 Feb 2025" or "February 10, 2025"
        if not found_date:
            word_date = re.search(
                r"\b(\d{1,2})?\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*(\d{1,2})?,?\s*(\d{4})?\b",
                raw_text,
                re.IGNORECASE,
            )
            if word_date:
                try:
                    d_str = word_date.group(1) or word_date.group(3) or "1"
                    m_str = word_date.group(2)[:3].title()
                    y_str = word_date.group(4) or str(reference_year)
                    found_date = datetime.strptime(f"{d_str} {m_str} {y_str}", "%d %b %Y")
                except ValueError:
                    pass

        if not found_date:
            return None, None, 0.0

        # 3. Look for time e.g. "20:00", "8 PM", "8:30 AM", "04:30" (must have colon or meridiem)
        time_match = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b|\b(\d{1,2})\s*(am|pm)\b", raw_text, re.IGNORECASE)
        found_hour = None
        found_min = 0

        if time_match:
            if time_match.group(1) is not None:  # HH:MM format
                h = int(time_match.group(1))
                m = int(time_match.group(2))
                meridiem = time_match.group(3).lower() if time_match.group(3) else None
                if meridiem:
                    if meridiem == "pm" and h < 12:
                        h += 12
                    elif meridiem == "am" and h == 12:
                        h = 0
                found_hour = h
                found_min = m
            elif time_match.group(4) is not None:  # H AM/PM format
                h = int(time_match.group(4))
                meridiem = time_match.group(5).lower()
                if meridiem == "pm" and h < 12:
                    h += 12
                elif meridiem == "am" and h == 12:
                    h = 0
                found_hour = h
                found_min = 0

        if found_hour is not None:
            # Precise time window: +/- 2 hours tolerance
            center = found_date.replace(hour=found_hour, minute=found_min, second=0)
            t_start = (center - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            t_end = (center + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            return t_start, t_end, 0.90
        else:
            # Entire day window (00:00:00 to 23:59:59)
            t_start = found_date.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
            t_end = found_date.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
            return t_start, t_end, 0.75
