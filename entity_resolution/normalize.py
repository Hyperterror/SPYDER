"""
Normalization and String Similarity Utilities for Entity Resolution.
Provides deterministic, standard preprocessing functions while preserving both raw and normalized values.
"""

import re
from typing import Dict, Any, List, Set

# Honorifics to strip for canonical name normalization
HONORIFICS = {"mr", "mrs", "ms", "dr", "shri", "smt", "prof", "capt", "insp", "si"}

def normalize_name(raw_name: str) -> Dict[str, Any]:
    """
    Normalizes a person's name while retaining structural components.
    Example: ' A. Gupta ' -> {'raw': ' A. Gupta ', 'clean': 'a gupta', 'tokens': ['a', 'gupta'], 'initials': 'ag'}
    """
    if not raw_name:
        return {"raw": "", "clean": "", "tokens": [], "initials": ""}
    
    raw = raw_name.strip()
    # Remove punctuation except whitespace
    cleaned = re.sub(r"[^\w\s]", " ", raw).lower()
    tokens = [t for t in cleaned.split() if t not in HONORIFICS]
    
    clean_str = " ".join(tokens)
    initials = "".join([t[0] for t in tokens if t])
    
    return {
        "raw": raw,
        "clean": clean_str,
        "tokens": tokens,
        "initials": initials,
    }

def normalize_alias(raw_alias: str) -> Dict[str, Any]:
    """Normalizes an alias / nickname."""
    if not raw_alias:
        return {"raw": "", "clean": "", "tokens": []}
    raw = raw_alias.strip()
    cleaned = re.sub(r"[^\w\s]", " ", raw).lower()
    tokens = cleaned.split()
    return {
        "raw": raw,
        "clean": " ".join(tokens),
        "tokens": tokens
    }

def normalize_phone(raw_phone: str) -> Dict[str, Any]:
    """
    Normalizes phone numbers to standardized E.164 and 10-digit formats.
    Example: '+91 98765-43210' -> {'raw': '+91 98765-43210', 'digits': '919876543210', 'last10': '9876543210'}
    """
    if not raw_phone:
        return {"raw": "", "digits": "", "last10": "", "is_valid": False}
    raw = raw_phone.strip()
    digits = re.sub(r"\D", "", raw)
    last10 = digits[-10:] if len(digits) >= 10 else digits
    return {
        "raw": raw,
        "digits": digits,
        "last10": last10,
        "is_valid": len(last10) == 10
    }

def normalize_email(raw_email: str) -> Dict[str, Any]:
    """Normalizes email addresses."""
    if not raw_email:
        return {"raw": "", "clean": "", "username": "", "domain": ""}
    raw = raw_email.strip().lower()
    parts = raw.split("@")
    username = parts[0] if len(parts) > 0 else ""
    domain = parts[1] if len(parts) > 1 else ""
    return {
        "raw": raw_email.strip(),
        "clean": raw,
        "username": username,
        "domain": domain
    }

def normalize_imei(raw_imei: str) -> Dict[str, Any]:
    """Normalizes 15-digit mobile device IMEI."""
    if not raw_imei:
        return {"raw": "", "clean": "", "is_valid": False}
    digits = re.sub(r"\D", "", str(raw_imei).strip())
    return {
        "raw": str(raw_imei).strip(),
        "clean": digits,
        "is_valid": len(digits) == 15
    }

def normalize_device_id(raw_device: str) -> Dict[str, Any]:
    """Normalizes observational device ID."""
    raw = str(raw_device).strip().upper() if raw_device else ""
    return {
        "raw": str(raw_device).strip() if raw_device else "",
        "clean": raw
    }

def normalize_vehicle_reg(raw_reg: str) -> Dict[str, Any]:
    """
    Normalizes vehicle registration numbers.
    Example: 'DL-01-AB-1234' -> {'raw': 'DL-01-AB-1234', 'clean': 'DL01AB1234', 'state': 'DL'}
    """
    if not raw_reg:
        return {"raw": "", "clean": "", "state": ""}
    raw = raw_reg.strip().upper()
    clean = re.sub(r"[^A-Z0-9]", "", raw)
    state = clean[:2] if len(clean) >= 2 else ""
    return {
        "raw": raw,
        "clean": clean,
        "state": state
    }

def normalize_account_id(raw_acc: str) -> Dict[str, Any]:
    """Normalizes bank account identifier string."""
    if not raw_acc:
        return {"raw": "", "clean": ""}
    raw = raw_acc.strip().upper()
    return {
        "raw": raw_acc.strip(),
        "clean": raw
    }

def normalize_ip(raw_ip: str) -> Dict[str, Any]:
    """Normalizes IPv4 address string."""
    if not raw_ip:
        return {"raw": "", "clean": "", "is_valid": False}
    raw = raw_ip.strip()
    parts = raw.split(".")
    is_valid = len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
    return {
        "raw": raw,
        "clean": raw,
        "is_valid": is_valid
    }

# ============================================================================
# String Similarity Metrics
# ============================================================================

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculates Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
    if len(s1) == 0:
        return len(s2)
    if len(s2) == 0:
        return len(s1)

    v0 = list(range(len(s2) + 1))
    v1 = [0] * (len(s2) + 1)

    for i in range(len(s1)):
        v1[0] = i + 1
        for j in range(len(s2)):
            cost = 0 if s1[i] == s2[j] else 1
            v1[j + 1] = min(v1[j] + 1, v0[j + 1] + 1, v0[j] + cost)
        v0 = list(v1)

    return v1[len(s2)]

def levenshtein_similarity(s1: str, s2: str) -> float:
    """Calculates normalized Levenshtein similarity in range [0.0, 1.0]."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(s1, s2)
    return max(0.0, 1.0 - dist / max_len)

def jaro_similarity(s1: str, s2: str) -> float:
    """Calculates Jaro distance similarity."""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    return (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3.0

def jaro_winkler_similarity(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """Calculates Jaro-Winkler similarity."""
    jaro_sim = jaro_similarity(s1, s2)
    if jaro_sim < 0.7:
        return jaro_sim
    # Common prefix length up to 4 characters
    prefix_len = 0
    for i in range(min(len(s1), len(s2), 4)):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break
    return jaro_sim + prefix_len * prefix_weight * (1.0 - jaro_sim)

def token_jaccard_similarity(tokens1: List[str], tokens2: List[str]) -> float:
    """Calculates Jaccard similarity between two token lists."""
    set1, set2 = set(tokens1), set(tokens2)
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    return len(set1.intersection(set2)) / len(set1.union(set2))
