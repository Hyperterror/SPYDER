"""
Structured JSON Logging with Sensitive-Data Redaction & Request Correlation (Milestone 6).
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.=]+", re.IGNORECASE)
_SECRET_KV_RE = re.compile(
    r"((?:password|secret|token|jwt|api_key|authorization|cookie)\s*[=:]\s*)([^\s,;\"'}]+)",
    re.IGNORECASE,
)


def redact_sensitive_text(text: str) -> str:
    masked = _BEARER_RE.sub(r"\1[REDACTED]", text)
    masked = _SECRET_KV_RE.sub(r"\1[REDACTED]", masked)
    return masked


def redact_mapping(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(tok in kl for tok in ("password", "secret", "token", "authorization", "cookie", "raw_record")):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_mapping(v)
        return out
    if isinstance(obj, list):
        return [redact_mapping(i) for i in obj]
    if isinstance(obj, str):
        return redact_sensitive_text(obj)
    return obj


class JsonLogFormatter(logging.Formatter):
    """Formats log records as single-line redacted JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_ctx.get("-"),
            "message": redact_sensitive_text(record.getMessage()),
        }
        extra_meta = getattr(record, "extra_meta", None)
        if isinstance(extra_meta, dict):
            payload["meta"] = redact_mapping(extra_meta)
        if record.exc_info:
            payload["exception"] = redact_sensitive_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_structured_logging(level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger("spyder")
    root.setLevel(level)
    if not any(isinstance(h.formatter, JsonLogFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        root.handlers = [handler]
    root.propagate = False
    return root
