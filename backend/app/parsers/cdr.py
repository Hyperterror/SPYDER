"""
CDR CSV Parser
Normalises Call Detail Records from variable provider CSV formats
using a configurable column mapping.
"""
from __future__ import annotations
import io
import re
from datetime import timezone
from typing import Optional
import pandas as pd
import phonenumbers
from dateutil import parser as dateparser


DEFAULT_MAPPING = {
    "calling_number": "calling_number",
    "called_number": "called_number",
    "start_time": "start_time",
    "duration_seconds": "duration_seconds",
    "call_type": "call_type",
    "imei": "imei",
    "imsi": "imsi",
    "tower_id": "tower_id",
}


def normalize_phone(value: str, default_country: str = "IN") -> Optional[str]:
    """Return E.164 formatted phone or None if unparseable."""
    if not value or str(value).strip() in ("", "nan", "None"):
        return None
    try:
        parsed = phonenumbers.parse(str(value).strip(), default_country)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    return None


def normalize_timestamp(value, source_timezone: str = "Asia/Kolkata") -> tuple[Optional[str], str]:
    """
    Returns (utc_iso_string, raw_string).
    Converts to UTC while keeping the original raw value.
    """
    raw = str(value).strip() if value is not None else ""
    try:
        dt = dateparser.parse(raw)
        if dt.tzinfo is None:
            import pytz
            tz = pytz.timezone(source_timezone)
            dt = tz.localize(dt)
        utc = dt.astimezone(timezone.utc)
        return utc.isoformat(), raw
    except Exception:
        return None, raw


def parse_cdr_csv(
    file_bytes: bytes,
    column_mapping: dict,
    case_id: str,
    evidence_id: str,
    source_file_name: str,
    sha256_hash: str,
) -> dict:
    """
    Parse CDR CSV bytes using the given column mapping.

    Returns:
        {
            total_rows: int,
            valid_rows: int,
            invalid_rows: int,
            records: list[dict],   # VALID normalized records
            errors: list[dict],    # INVALID row details
        }
    """
    mapping = {**DEFAULT_MAPPING, **column_mapping}

    try:
        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    except Exception as e:
        return {"total_rows": 0, "valid_rows": 0, "invalid_rows": 0, "records": [], "errors": [],
                "parse_error": str(e)}

    total_rows = len(df)
    records = []
    errors = []

    for idx, row in df.iterrows():
        row_number = int(idx) + 2  # 1-indexed, +1 for header
        raw_record = row.to_dict()

        def get_col(field: str) -> Optional[str]:
            col = mapping.get(field)
            return row.get(col, "").strip() if col and col in row else ""

        calling_raw = get_col("calling_number")
        called_raw = get_col("called_number")
        start_time_raw = get_col("start_time")

        calling_norm = normalize_phone(calling_raw)
        called_norm = normalize_phone(called_raw)
        start_utc, start_raw = normalize_timestamp(start_time_raw)

        # Validation
        missing = []
        if not calling_norm:
            missing.append("calling_number")
        if not called_norm:
            missing.append("called_number")
        if not start_utc:
            missing.append("start_time")

        if missing:
            errors.append({
                "source_row_number": row_number,
                "raw_record": raw_record,
                "parse_status": "INVALID",
                "parse_error": f"Missing or invalid required fields: {', '.join(missing)}",
            })
            continue

        # Parse optional fields
        duration = None
        dur_raw = get_col("duration_seconds")
        if dur_raw:
            try:
                duration = int(float(dur_raw))
            except Exception:
                pass

        imei_val = get_col("imei") or None
        tower_val = get_col("tower_id") or None
        call_type = get_col("call_type") or "VOICE"

        normalized = {
            "calling_number": calling_norm,
            "called_number": called_norm,
            "start_time_utc": start_utc,
            "raw_start_time": start_raw,
            "duration_seconds": duration,
            "call_type": call_type.upper() if call_type else "VOICE",
            "imei": imei_val,
            "imsi": get_col("imsi") or None,
            "tower_id": tower_val,
        }

        records.append({
            "source_row_number": row_number,
            "raw_record": raw_record,
            "normalized_record": normalized,
            "parse_status": "VALID",
        })

    return {
        "total_rows": total_rows,
        "valid_rows": len(records),
        "invalid_rows": len(errors),
        "records": records,
        "errors": errors,
    }
