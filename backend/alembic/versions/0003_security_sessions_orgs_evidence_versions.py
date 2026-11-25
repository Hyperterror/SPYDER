"""Add organizations, user_sessions, evidence versioning, audit sequence/checkpoint, and catch-up tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    is_pg = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)
    json_type = postgresql.JSONB() if is_pg else sa.Text()

    # 1. Organizations
    if not _has_table(inspector, "organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("code", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_organizations_code", "organizations", ["code"], unique=True)

    # 2. User sessions (refresh token rotation & revocation)
    if not _has_table(inspector, "user_sessions"):
        op.create_table(
            "user_sessions",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("user_id", uuid_type, nullable=False),
            sa.Column("refresh_token_jti", sa.String(64), nullable=False),
            sa.Column("token_family_id", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revocation_reason", sa.String(), nullable=True),
            sa.Column("replaced_by_jti", sa.String(64), nullable=True),
            sa.Column("ip_address", sa.String(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
        op.create_index("ix_user_sessions_refresh_token_jti", "user_sessions", ["refresh_token_jti"], unique=True)
        op.create_index("ix_user_sessions_token_family_id", "user_sessions", ["token_family_id"])

    # 3. Catch-up: evidence_processing_jobs
    if not _has_table(inspector, "evidence_processing_jobs"):
        op.create_table(
            "evidence_processing_jobs",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("evidence_id", uuid_type, nullable=False),
            sa.Column("case_id", uuid_type, nullable=False),
            sa.Column("job_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("pipeline_version", sa.String(), nullable=False),
            sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("result_summary", json_type, nullable=True),
            sa.Column("initiated_by", uuid_type, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"]),
            sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
            sa.ForeignKeyConstraint(["initiated_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    # 4. Column additions
    if not _has_column(inspector, "users", "organization_id"):
        op.add_column("users", sa.Column("organization_id", uuid_type, nullable=True))
        op.create_index("ix_users_organization_id", "users", ["organization_id"])

    if not _has_column(inspector, "cases", "organization_id"):
        op.add_column("cases", sa.Column("organization_id", uuid_type, nullable=True))
        op.create_index("ix_cases_organization_id", "cases", ["organization_id"])
    if not _has_column(inspector, "cases", "external_case_ref"):
        op.add_column("cases", sa.Column("external_case_ref", sa.String(), nullable=True))
        op.create_index("ix_cases_external_case_ref", "cases", ["external_case_ref"], unique=True)

    if not _has_column(inspector, "evidence_items", "processing_status"):
        op.add_column("evidence_items", sa.Column("processing_status", sa.String(), nullable=False, server_default="UPLOADED"))
    if not _has_column(inspector, "evidence_items", "version_number"):
        op.add_column("evidence_items", sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"))
    if not _has_column(inspector, "evidence_items", "supersedes_evidence_id"):
        op.add_column("evidence_items", sa.Column("supersedes_evidence_id", uuid_type, nullable=True))
    if not _has_column(inspector, "evidence_items", "lifecycle_status"):
        op.add_column("evidence_items", sa.Column("lifecycle_status", sa.String(), nullable=False, server_default="ACTIVE"))
    if not _has_column(inspector, "evidence_items", "withdrawn_reason"):
        op.add_column("evidence_items", sa.Column("withdrawn_reason", sa.Text(), nullable=True))
    if not _has_column(inspector, "evidence_items", "withdrawn_by"):
        op.add_column("evidence_items", sa.Column("withdrawn_by", uuid_type, nullable=True))
    if not _has_column(inspector, "evidence_items", "withdrawn_at"):
        op.add_column("evidence_items", sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column(inspector, "evidence_items", "acquisition_metadata"):
        op.add_column("evidence_items", sa.Column("acquisition_metadata", json_type, nullable=True))

    if not _has_column(inspector, "audit_events", "sequence_number"):
        op.add_column("audit_events", sa.Column("sequence_number", sa.Integer(), nullable=True))
    if not _has_column(inspector, "audit_events", "checkpoint_signature"):
        op.add_column("audit_events", sa.Column("checkpoint_signature", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_events", "checkpoint_signature")
    op.drop_column("audit_events", "sequence_number")
    for col in (
        "acquisition_metadata", "withdrawn_at", "withdrawn_by", "withdrawn_reason",
        "lifecycle_status", "supersedes_evidence_id", "version_number",
    ):
        op.drop_column("evidence_items", col)
    op.drop_index("ix_cases_external_case_ref", table_name="cases")
    op.drop_column("cases", "external_case_ref")
    op.drop_index("ix_cases_organization_id", table_name="cases")
    op.drop_column("cases", "organization_id")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_column("users", "organization_id")
    op.drop_table("user_sessions")
    op.drop_index("ix_organizations_code", table_name="organizations")
    op.drop_table("organizations")
