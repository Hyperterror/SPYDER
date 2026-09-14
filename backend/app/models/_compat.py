"""
Portable column type helpers.
Uses native PostgreSQL types when connected to Postgres,
falls back to plain String/Text for SQLite (local dev/testing).
"""
import os
from sqlalchemy import String, Text
from sqlalchemy import types as sa_types

_url = os.environ.get("DATABASE_URL", "sqlite:///./spyder_local.db")
_IS_PG = _url.startswith("postgresql")

if _IS_PG:
    from sqlalchemy.dialects.postgresql import UUID as _UUID, JSONB as _JSONB

    class UUIDType(sa_types.TypeDecorator):
        impl = _UUID(as_uuid=True)
        cache_ok = True

    class JSONBType(sa_types.TypeDecorator):
        impl = _JSONB
        cache_ok = True

else:
    import uuid
    import json

    class UUIDType(sa_types.TypeDecorator):  # type: ignore[no-redef]
        """Stores UUID as VARCHAR(36) in SQLite."""
        impl = String(36)
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            return str(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            return uuid.UUID(str(value))

    class JSONBType(sa_types.TypeDecorator):  # type: ignore[no-redef]
        """Stores JSON as TEXT in SQLite."""
        impl = Text
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            return json.dumps(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, (dict, list)):
                return value
            return json.loads(value)
