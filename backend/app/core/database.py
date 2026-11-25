from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# SQLite doesn't support pool_size/max_overflow — detect and configure accordingly
_url = settings.DATABASE_URL
_is_sqlite = _url.startswith("sqlite")

if _is_sqlite:
    engine = create_engine(
        _url,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        _url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# Columns added after the initial schema. ``Base.metadata.create_all`` only
# creates missing tables, so an existing local SQLite dev database would
# otherwise fail on these columns until Alembic is run.
_LATE_COLUMNS = {
    "evidence_items": {
        "processing_status": "VARCHAR NOT NULL DEFAULT 'UPLOADED'",
        "extracted_text": "TEXT",
    },
}


def ensure_late_columns(bind) -> list[str]:
    """Adds any post-initial-schema columns that a pre-existing database lacks.

    Best-effort and idempotent: returns the list of columns it added, and never
    raises — a failure here must not stop application startup.
    """
    from sqlalchemy import inspect, text

    added: list[str] = []
    try:
        inspector = inspect(bind)
        existing_tables = set(inspector.get_table_names())
        for table, columns in _LATE_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for column, sql_type in columns.items():
                if column in present:
                    continue
                with bind.begin() as conn:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {sql_type}'))
                added.append(f"{table}.{column}")
    except Exception as exc:  # pragma: no cover - startup resilience
        print(f"[WARN] Could not apply late schema columns: {exc}")
    return added


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
