"""
Phase 7A: Unified Evidence Parsers & Normalizers.
Provides standardized parsing and normalization across all supported evidence modalities:
- CDR (Call Detail Records)
- TRANSACTION (Banking, UPI, Wire Transfers)
- TRAVEL (Movements, Flights, Trains, Tolls)
- VEHICLE (Sightings, ANPR, Registrations)
- DEVICE (IP, MAC, IMEI, Wi-Fi connections)
- CHAT (Messaging, Threads)
- PERSONS (Rosters, Suspects, Identity records)
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional, Tuple
from app.parsers.cdr import normalize_phone, normalize_timestamp
from app.services.ocr import extract_text_for_upload


PARSER_VERSION = "2.0.0"


def _rows_from_bytes(file_bytes: bytes, file_extension: str, source_file_name: str) -> tuple[List[Tuple[int, Dict[str, Any]]], str]:
    """Convert CSV, XLSX, JSON, or PDF/image bytes into (row_number, raw_dict) tuples and extraction_method."""
    ext = (file_extension or ".csv").lower()
    if ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
        row_iter = ws.iter_rows(values_only=True)
        headers = [str(c).strip() if c is not None else "" for c in next(row_iter, ())]
        out: List[Tuple[int, Dict[str, Any]]] = []
        for idx, vals in enumerate(row_iter, start=2):
            row_dict = {headers[i]: ("" if v is None else str(v)) for i, v in enumerate(vals) if i < len(headers) and headers[i]}
            out.append((idx, row_dict))
        wb.close()
        return out, "openpyxl_xlsx"

    if ext == ".json":
        payload = json.loads(file_bytes.decode("utf-8", errors="replace"))
        items = payload.get("records", payload) if isinstance(payload, dict) else payload
        if isinstance(items, list):
            return [(idx, {str(k): str(v) if v is not None else "" for k, v in item.items()}) for idx, item in enumerate(items, start=1) if isinstance(item, dict)], "json_structured"
        return [(1, {"text": json.dumps(payload, ensure_ascii=False)})], "json_document"

    if ext in {".pdf", ".png", ".jpg", ".jpeg"}:
        extracted = extract_text_for_upload(source_file_name, file_bytes) or ""
        method = "pypdf_ocr" if ext == ".pdf" else "tesseract_ocr"
        return [(1, {"extracted_text": extracted, "filename": source_file_name})], method

    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [(idx, dict(row)) for idx, row in enumerate(reader, start=2)], "csv_dict_reader"


def parse_unified_evidence_csv(
    file_bytes: bytes,
    modality: str,
    case_id: str,
    evidence_id: str,
    source_file_name: str,
    sha256_hash: str,
    file_extension: str = ".csv",
) -> Dict[str, Any]:
    """
    Parses and normalizes evidence records across CSV, XLSX, JSON, PDF, and image formats.
    """
    try:
        indexed_rows, extraction_method = _rows_from_bytes(file_bytes, file_extension, source_file_name)
    except Exception as e:
        return {
            "total_rows": 0,
            "valid_rows": 0,
            "invalid_rows": 1,
            "extraction_method": "error",
            "parser_version": PARSER_VERSION,
            "records": [],
            "errors": [{"source_row_number": 0, "raw_record": {}, "parse_error": f"Decode/read error: {e}"}],
        }

    records: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, raw in indexed_rows:
        try:
            normalized = _normalize_row_by_modality(raw, modality, case_id)
            normalized["source_evidence_id"] = evidence_id
            normalized["source_row_number"] = idx
            normalized["extraction_method"] = extraction_method
            normalized["parser_version"] = PARSER_VERSION
            records.append({
                "source_row_number": idx,
                "raw_record": raw,
                "normalized_record": normalized,
                "extraction_method": extraction_method,
                "parser_version": PARSER_VERSION,
            })
        except Exception as e:
            errors.append({
                "source_row_number": idx,
                "raw_record": raw,
                "parse_error": str(e),
                "extraction_method": extraction_method,
                "parser_version": PARSER_VERSION,
            })

    return {
        "total_rows": len(records) + len(errors),
        "valid_rows": len(records),
        "invalid_rows": len(errors),
        "extraction_method": extraction_method,
        "parser_version": PARSER_VERSION,
        "records": records,
        "errors": errors,
    }


def _normalize_row_by_modality(raw: Dict[str, str], modality: str, case_id: str) -> Dict[str, Any]:
    """
    Dispatches normalization based on evidence modality.
    """
    # Lowercase lookup dictionary
    lowered = {k.strip().lower(): v.strip() for k, v in raw.items() if k}

    def get_field(*candidates: str, default: str = "") -> str:
        for c in candidates:
            if c.lower() in lowered and lowered[c.lower()]:
                return lowered[c.lower()]
        return default

    if modality == "CDR":
        caller = get_field("calling_number", "caller", "calling", "src_phone", "phone_from")
        callee = get_field("called_number", "callee", "called", "dst_phone", "phone_to")
        time_raw = get_field("start_time", "timestamp", "call_time", "datetime")
        duration = get_field("duration_seconds", "duration", default="0")
        tower = get_field("tower_id", "cell_tower", "tower", "cell_id")

        if not caller or not callee:
            raise ValueError("Missing caller or callee phone number")

        norm_caller = normalize_phone(caller) or caller
        norm_callee = normalize_phone(callee) or callee
        norm_time, raw_time = normalize_timestamp(time_raw)

        return {
            "calling_number": norm_caller,
            "called_number": norm_callee,
            "start_time_utc": norm_time or raw_time,
            "raw_start_time": raw_time,
            "duration_seconds": int(float(duration)) if duration.replace(".", "", 1).isdigit() else 0,
            "tower_id": tower.upper() if tower else "",
            "case_id": case_id,
        }

    elif modality == "TRANSACTION":
        sender = get_field("sender_account", "sender_identifier", "from_account", "sender", "sender_id")
        receiver = get_field("receiver_account", "receiver_identifier", "to_account", "receiver", "receiver_id")
        amount = get_field("amount", "txn_amount", "transaction_amount", "value", default="0.0")
        time_raw = get_field("timestamp", "txn_date", "date", "created_at")
        txn_type = get_field("transaction_type", "type", "channel", default="BANK_TRANSFER")
        currency = get_field("currency", default="INR")

        if not sender or not receiver:
            raise ValueError("Missing sender or receiver account")

        norm_time, raw_time = normalize_timestamp(time_raw)

        return {
            "sender_identifier": sender.upper(),
            "receiver_identifier": receiver.upper(),
            "amount": float(amount) if amount.replace(".", "", 1).isdigit() else 0.0,
            "currency": currency.upper(),
            "timestamp_utc": norm_time or raw_time,
            "raw_timestamp": raw_time,
            "transaction_type": txn_type.upper(),
            "case_id": case_id,
        }

    elif modality == "TRAVEL":
        person = get_field("person_id", "traveler", "name", "passenger")
        origin = get_field("origin", "from_city", "departure_city", "source_location")
        dest = get_field("destination", "to_city", "arrival_city", "target_location")
        time_raw = get_field("departure_time", "timestamp", "travel_date", "date")
        mode = get_field("transport_mode", "mode", "carrier_type", default="TRANSIT")

        if not person or not origin or not dest:
            raise ValueError("Missing required travel movement fields (person, origin, destination)")

        norm_time, raw_time = normalize_timestamp(time_raw)

        return {
            "person_id": person.upper(),
            "origin": origin.strip().title(),
            "destination": dest.strip().title(),
            "departure_time_utc": norm_time or raw_time,
            "transport_mode": mode.upper(),
            "case_id": case_id,
        }

    elif modality == "VEHICLE":
        veh = get_field("vehicle_number", "registration", "vehicle_id", "plate_number")
        loc = get_field("sighting_location", "location", "checkpoint", "camera_location")
        owner = get_field("owner_person_id", "owner_id", "owner", default="")
        time_raw = get_field("timestamp", "sighting_timestamp", "date")

        if not veh:
            raise ValueError("Missing vehicle registration number")

        norm_time, raw_time = normalize_timestamp(time_raw)

        return {
            "vehicle_number": veh.upper().replace(" ", ""),
            "sighting_location": loc.strip().title() if loc else "UNKNOWN",
            "owner_person_id": owner.upper() if owner else "",
            "timestamp_utc": norm_time or raw_time,
            "case_id": case_id,
        }

    elif modality == "DEVICE":
        dev = get_field("device_id", "mac_address", "imei")
        ip = get_field("ip_address", "ip", default="")
        person = get_field("person_id", "user_id", default="")
        time_raw = get_field("timestamp", "log_time", "connected_at")

        if not dev and not ip:
            raise ValueError("Missing device identifier or IP address")

        norm_time, raw_time = normalize_timestamp(time_raw)

        return {
            "device_id": dev.upper() if dev else ip,
            "ip_address": ip,
            "person_id": person.upper() if person else "",
            "timestamp_utc": norm_time or raw_time,
            "case_id": case_id,
        }

    elif modality == "CHAT":
        sender = get_field("sender_id", "sender", "author")
        recipient = get_field("recipient_id", "recipient", "receiver")
        msg = get_field("message_text", "text", "content", "message", default="")
        platform = get_field("platform", "channel", default="MESSAGING")
        time_raw = get_field("timestamp", "date", "sent_at")

        if not sender or not recipient:
            raise ValueError("Missing chat sender or recipient")

        norm_time, raw_time = normalize_timestamp(time_raw)

        return {
            "sender_id": sender.upper(),
            "recipient_id": recipient.upper(),
            "platform": platform.upper(),
            "message_text": msg,
            "timestamp_utc": norm_time or raw_time,
            "case_id": case_id,
        }

    elif modality == "PERSONS":
        pid = get_field("person_id", "suspect_id", "individual_id")
        name = get_field("raw_name", "name", "full_name", "person_name")
        phone = get_field("phone_id", "phone", "phone_number", default="")
        device = get_field("device_id", "device", default="")

        if not pid or not name:
            raise ValueError("Missing person_id or person name")

        return {
            "person_id": pid.upper(),
            "raw_name": name.strip(),
            "phone_id": phone,
            "device_id": device,
            "case_id": case_id,
        }

    # Fallback generic normalization
    return {k: v.strip() for k, v in raw.items()}
