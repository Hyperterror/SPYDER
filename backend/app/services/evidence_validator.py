"""
Phase 7A: Evidence Validation Service.
Enforces rigorous validation on uploaded files:
- File size bounds (non-empty, <= 100MB)
- File extension whitelist (.csv, .xlsx, .json)
- Path traversal and character sanitization
- Binary / executable magic-byte inspection (prevents disguised executables)
- Structured schema inspection and header matching for evidence modalities
"""

import csv
import io
import os
import re
from typing import List, Optional, Set, Tuple


ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".json"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
MIN_FILE_SIZE = 1  # Disallow empty 0-byte uploads

# Known dangerous executable magic bytes
DISALLOWED_MAGIC_PREFIXES = [
    b"MZ",           # Windows PE executable
    b"\x7fELF",      # Linux ELF executable
    b"\xfe\xed\xfa", # Mach-O binary
    b"\xce\xfa\xed", # Mach-O binary
    b"%PDF",         # PDF header masquerading as CSV
    b"#!/bin/",      # Shell script
    b"#!/usr/",      # Shell script
]


class EvidenceValidationError(ValueError):
    """Raised when evidence fails validation checks."""
    pass


def sanitize_filename(filename: str) -> str:
    """
    Sanitizes filename, preventing directory traversal and stripping dangerous characters.
    """
    if not filename or not filename.strip():
        return "evidence_upload"

    # Reject path traversal tokens in original input
    if ".." in filename or "/" in filename or "\\" in filename:
        raise EvidenceValidationError("Path traversal characters are not permitted in filenames.")

    basename = os.path.basename(filename).strip()
    # Remove null bytes or control characters
    basename = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", basename)

    # Clean characters: keep alphanumeric, dashes, dots, underscores
    sanitized = re.sub(r"[^\w\s\-\.]", "", basename).strip().replace(" ", "_")
    if not sanitized:
        return "evidence_upload"
    return sanitized


def validate_file_security(
    filename: str,
    file_bytes: bytes,
    max_size: int = MAX_FILE_SIZE,
) -> str:
    """
    Validates file extension, size, path safety, and magic bytes.
    Returns sanitized filename.
    """
    if len(file_bytes) < MIN_FILE_SIZE:
        raise EvidenceValidationError("Uploaded evidence file is empty (0 bytes).")

    if len(file_bytes) > max_size:
        raise EvidenceValidationError(f"File exceeds maximum allowed size of {max_size // (1024 * 1024)} MB.")

    sanitized = sanitize_filename(filename)
    ext = os.path.splitext(sanitized)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise EvidenceValidationError(f"Unsupported file extension '{ext}'. Allowed extensions: {sorted(ALLOWED_EXTENSIONS)}.")

    # Check dangerous executable magic bytes
    for prefix in DISALLOWED_MAGIC_PREFIXES:
        if file_bytes.startswith(prefix):
            raise EvidenceValidationError("Uploaded file contains binary or executable headers and cannot be accepted.")

    # ZIP handling: generic ZIPs disallowed for CSV/JSON; valid OpenXML spreadsheets permitted for XLSX
    if file_bytes.startswith(b"PK\x03\x04"):
        if ext != ".xlsx":
            raise EvidenceValidationError("ZIP archive headers detected. Generic archives are not allowed.")
        # Validate XLSX OpenXML container integrity
        try:
            import zipfile
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                namelist = zf.namelist()
                has_content_types = "[Content_Types].xml" in namelist
                has_workbook = any(n.startswith("xl/") for n in namelist)
                if not (has_content_types and has_workbook):
                    raise EvidenceValidationError("File has .xlsx extension but lacks valid OpenXML spreadsheet structure.")
                for name in namelist:
                    lower = name.lower()
                    if any(lower.endswith(bad) for bad in [".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".bin"]):
                        raise EvidenceValidationError("XLSX package contains prohibited executable or script components.")
        except zipfile.BadZipFile:
            raise EvidenceValidationError("Corrupted or invalid XLSX archive.")
    elif ext == ".xlsx":
        raise EvidenceValidationError("XLSX file must be a valid OpenXML container starting with ZIP magic bytes.")

    # For CSV files, check that it's readable text without binary null bytes
    if ext == ".csv":
        sample = file_bytes[:2048]
        if b"\x00" in sample:
            raise EvidenceValidationError("File appears to be binary data, not a valid CSV text document.")
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            try:
                sample.decode("latin-1")
            except Exception:
                raise EvidenceValidationError("CSV file is not valid UTF-8 or text format.")

    return sanitized


# Schema header signatures
SCHEMA_SIGNATURES = {
    "CDR": {
        "caller_indicators": {"calling_number", "caller", "calling", "phone_from", "src_phone"},
        "callee_indicators": {"called_number", "callee", "called", "phone_to", "dst_phone", "receiver"},
        "time_indicators": {"start_time", "timestamp", "call_time", "datetime", "call_start"},
    },
    "TRANSACTION": {
        "sender_indicators": {"sender_account", "sender_identifier", "from_account", "sender", "sender_id"},
        "receiver_indicators": {"receiver_account", "receiver_identifier", "to_account", "receiver", "receiver_id"},
        "amount_indicators": {"amount", "txn_amount", "transaction_amount", "value"},
    },
    "TRAVEL": {
        "person_indicators": {"person_id", "traveler", "name", "passenger"},
        "origin_indicators": {"origin", "from_city", "departure_city", "source_location"},
        "destination_indicators": {"destination", "to_city", "arrival_city", "target_location"},
    },
    "VEHICLE": {
        "vehicle_indicators": {"vehicle_number", "registration", "vehicle_id", "plate_number"},
        "sighting_indicators": {"sighting_location", "location", "checkpoint", "camera_location"},
    },
    "DEVICE": {
        "device_indicators": {"device_id", "mac_address", "imei", "ip_address"},
        "time_indicators": {"timestamp", "log_time", "connected_at", "seen_at"},
    },
    "CHAT": {
        "sender_indicators": {"sender_id", "sender", "author"},
        "recipient_indicators": {"recipient_id", "recipient", "receiver"},
        "message_indicators": {"message_text", "text", "content", "message", "platform"},
    },
    "PERSONS": {
        "id_indicators": {"person_id", "suspect_id", "individual_id"},
        "name_indicators": {"raw_name", "name", "full_name", "person_name"},
    },
}


def inspect_and_classify_schema(file_bytes: bytes) -> Tuple[str, List[str]]:
    """
    Inspects CSV headers to classify evidence modality and verify required columns.
    Returns (modality, headers).
    Raises EvidenceValidationError if schema is unrecognized or malformed.
    """
    try:
        text = file_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        raise EvidenceValidationError(f"Cannot decode CSV text: {e}")

    stream = io.StringIO(text)
    reader = csv.reader(stream)
    try:
        headers = next(reader, None)
    except Exception as e:
        raise EvidenceValidationError(f"Cannot parse CSV header row: {e}")

    if not headers or all(not h.strip() for h in headers):
        raise EvidenceValidationError("CSV file does not contain a valid header row.")

    normalized_headers = [h.strip().lower() for h in headers if h.strip()]
    header_set = set(normalized_headers)

    # Check against known schema signatures
    # 1. CDR
    sig = SCHEMA_SIGNATURES["CDR"]
    if (header_set & sig["caller_indicators"]) and (header_set & sig["callee_indicators"]):
        return "CDR", normalized_headers

    # 2. TRANSACTION
    sig = SCHEMA_SIGNATURES["TRANSACTION"]
    if (header_set & sig["sender_indicators"]) and (header_set & sig["receiver_indicators"]) and (header_set & sig["amount_indicators"]):
        return "TRANSACTION", normalized_headers

    # 3. TRAVEL
    sig = SCHEMA_SIGNATURES["TRAVEL"]
    if (header_set & sig["person_indicators"]) and (header_set & sig["origin_indicators"]) and (header_set & sig["destination_indicators"]):
        return "TRAVEL", normalized_headers

    # 4. VEHICLE
    sig = SCHEMA_SIGNATURES["VEHICLE"]
    if (header_set & sig["vehicle_indicators"]) and (header_set & sig["sighting_indicators"] or "timestamp" in header_set):
        return "VEHICLE", normalized_headers

    # 5. DEVICE
    sig = SCHEMA_SIGNATURES["DEVICE"]
    if (header_set & sig["device_indicators"]) and (header_set & sig["time_indicators"] or "wifi_ssid" in header_set):
        return "DEVICE", normalized_headers

    # 6. CHAT
    sig = SCHEMA_SIGNATURES["CHAT"]
    if (header_set & sig["sender_indicators"]) and (header_set & sig["recipient_indicators"]) and (header_set & sig["message_indicators"]):
        return "CHAT", normalized_headers

    # 7. PERSONS
    sig = SCHEMA_SIGNATURES["PERSONS"]
    if (header_set & sig["id_indicators"]) and (header_set & sig["name_indicators"]):
        return "PERSONS", normalized_headers

    # If not recognized
    raise EvidenceValidationError(
        f"Unsupported or unrecognized evidence schema. Found columns: {headers[:10]}. "
        f"Expected schema matching one of: {list(SCHEMA_SIGNATURES.keys())}."
    )
