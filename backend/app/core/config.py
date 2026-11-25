from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


_INSECURE_JWT_DEFAULTS = {
    "",
    "CHANGE_ME_to_a_long_random_secret_key",
    "CHANGE_ME_to_a_long_random_secret_key_at_least_32_chars",
    "secret",
    "dev_secret",
}

_INSECURE_SERVICE_PASSWORDS = {
    "spyder_secret",
    "spyder_secret_change_me",
    "spyder_neo4j",
    "spyder_neo4j_change_me",
    "spyder_minio_secret",
    "spyder_minio_secret_change_me",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App & Environment
    APP_NAME: str = "SPYDER-DETECT API"
    APP_VERSION: str = "1.1.0"
    ENVIRONMENT: str = "development"  # development | testing | production
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://spyder:spyder_secret@localhost:5432/spyder"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "spyder_neo4j"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "spyder_minio"
    MINIO_SECRET_KEY: str = "spyder_minio_secret"
    MINIO_SECURE: bool = False
    MINIO_BUCKET: str = "evidence"

    # Celery / Redis (Milestone 2+)
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_ALWAYS_EAGER: bool = True

    # Auth / JWT & Session Cookies
    JWT_SECRET_KEY: str = "CHANGE_ME_to_a_long_random_secret_key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    ALLOW_BODY_REFRESH: bool = True
    REQUIRE_SESSION_ID_IN_JWT: bool = False

    # Audit & Upload Integrity
    AUDIT_SIGNING_KEY: str = ""
    MAX_UPLOAD_BYTES: int = 100 * 1024 * 1024  # 100 MB

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "testing"


def validate_security_configuration(cfg: Settings) -> None:
    """Enforce strict secret and environment validation in production."""
    if not cfg.is_production:
        return

    errors: list[str] = []
    if cfg.DEBUG:
        errors.append("DEBUG must be False in production.")
    if cfg.JWT_SECRET_KEY in _INSECURE_JWT_DEFAULTS or len(cfg.JWT_SECRET_KEY) < 32:
        errors.append("JWT_SECRET_KEY must be a non-default secret of at least 32 characters in production.")
    if any(pw in cfg.DATABASE_URL for pw in _INSECURE_SERVICE_PASSWORDS):
        errors.append("DATABASE_URL uses a default development password in production.")
    if cfg.NEO4J_PASSWORD in _INSECURE_SERVICE_PASSWORDS or len(cfg.NEO4J_PASSWORD) < 12:
        errors.append("NEO4J_PASSWORD must not use default credentials in production.")
    if cfg.MINIO_SECRET_KEY in _INSECURE_SERVICE_PASSWORDS or len(cfg.MINIO_SECRET_KEY) < 12:
        errors.append("MINIO_SECRET_KEY must not use default credentials in production.")
    if not cfg.COOKIE_SECURE:
        errors.append("COOKIE_SECURE must be True in production.")
    if "*" in cfg.cors_origins_list:
        errors.append("CORS_ORIGINS must not contain wildcard '*' in production.")

    if errors:
        raise RuntimeError("Production security configuration check failed: " + " | ".join(errors))


settings = Settings()
