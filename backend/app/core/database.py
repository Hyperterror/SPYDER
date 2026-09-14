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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
