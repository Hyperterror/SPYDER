"""
Financial Transaction CSV Parser.
Normalises bank/UPI transaction records from variable CSV formats.
"""
from __future__ import annotations
import io
import re
from typing import Optional
import pandas as pd
from dateutil import parser as dateparser
from datetime import timezone

DEFAULT_MAPPING = {
    "sender": "sender",
    "receiver": "receiver",
    "timestamp": "timestamp",
    "amount": "amount",
    "currency": "currency",
    "transaction_id": "transaction_id",
    "transaction_type": "transaction_type",
}


def normalize_account(value: str) -> Optional[str]:
    """Normalize bank account or UPI ID to lowercase stripped form."""
    if not value or str(value).strip() in ("", "nan", "None"):
        return None
    v = str(value).strip().lower()
    return v if v else None


def normalize_amount(value) -> Optional[float]:
    """Strip currency symbols and parse to float."""
    if value is None or str(value).strip() in ("", "nan", "None"):
        return None
    cleaned = re.sub(r"[^\d.]", "", str(value).strip())
    try:
        return round(float(cleaned), 2)
    except Exception:
        return None


def normalize_timestamp(value, source_timezone: str = "Asia/Kolkata") -> tuple[Optional[str], str]:
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


def parse_transaction_csv(
    file_bytes: bytes,
    column_mapping: dict,
    case_id: str,
    evidence_id: str,
    source_file_name: str,
    sha256_hash: str,
) -> dict:
    """
    Parse financial transaction CSV bytes using the given column mapping.

    Returns dict with total_rows, valid_rows, invalid_rows, records, errors.
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
        row_number = int(idx) + 2
        raw_record = row.to_dict()

        def get_col(field: str) -> Optional[str]:
            col = mapping.get(field)
            return row.get(col, "").strip() if col and col in row else ""

        sender_raw = get_col("sender")
        receiver_raw = get_col("receiver")
        timestamp_raw = get_col("timestamp")
        amount_raw = get_col("amount")

        sender_norm = normalize_account(sender_raw)
        receiver_norm = normalize_account(receiver_raw)
        timestamp_utc, raw_ts = normalize_timestamp(timestamp_raw)
        amount = normalize_amount(amount_raw)

        # Validation
        missing = []
        if not sender_norm:
            missing.append("sender")
        if not receiver_norm:
            missing.append("receiver")
        if not timestamp_utc:
            missing.append("timestamp")
        if amount is None:
            missing.append("amount")

        if missing:
            errors.append({
                "source_row_number": row_number,
                "raw_record": raw_record,
                "parse_status": "INVALID",
                "parse_error": f"Missing or invalid required fields: {', '.join(missing)}",
            })
            continue

        currency = get_col("currency") or "INR"
        txn_id = get_col("transaction_id") or None
        txn_type = get_col("transaction_type") or "UPI"

        normalized = {
            "sender_identifier": sender_norm,
            "receiver_identifier": receiver_norm,
            "timestamp_utc": timestamp_utc,
            "raw_timestamp": raw_ts,
            "amount": amount,
            "currency": currency.upper() if currency else "INR",
            "transaction_id": txn_id,
            "transaction_type": txn_type.upper() if txn_type else "UPI",
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
