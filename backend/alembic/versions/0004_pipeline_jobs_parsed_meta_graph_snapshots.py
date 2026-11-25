"""Add graph_snapshots table and pipeline job/parsed record provenance columns.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26 00:10:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
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

    if not _has_table(inspector, "graph_snapshots"):
        op.create_table(
            "graph_snapshots",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("version_tag", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("edge_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("artifact_dir", sa.String(), nullable=True),
            sa.Column("manifest", json_type, nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_by", uuid_type, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_graph_snapshots_version_number", "graph_snapshots", ["version_number"], unique=True)
        op.create_index("ix_graph_snapshots_version_tag", "graph_snapshots", ["version_tag"], unique=True)

    job_cols = [
        ("stage", sa.Column("stage", sa.String(), nullable=False, server_default="QUEUED")),
        ("retry_count", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")),
        ("max_retries", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3")),
        ("celery_task_id", sa.Column("celery_task_id", sa.String(), nullable=True)),
        ("idempotency_key", sa.Column("idempotency_key", sa.String(128), nullable=True)),
        ("cancelled_at", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)),
        ("cancelled_by", sa.Column("cancelled_by", uuid_type, nullable=True)),
    ]
    for name, col in job_cols:
        if not _has_column(inspector, "evidence_processing_jobs", name):
            op.add_column("evidence_processing_jobs", col)

    pr_cols = [
        ("evidence_version", sa.Column("evidence_version", sa.Integer(), nullable=False, server_default="1")),
        ("extraction_method", sa.Column("extraction_method", sa.String(), nullable=True)),
        ("parser_version", sa.Column("parser_version", sa.String(), nullable=True)),
        ("extracted_at", sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True)),
        ("extraction_confidence", sa.Column("extraction_confidence", sa.String(), nullable=True)),
    ]
    for name, col in pr_cols:
        if not _has_column(inspector, "parsed_records", name):
            op.add_column("parsed_records", col)


def downgrade() -> None:
    for col in ("extraction_confidence", "extracted_at", "parser_version", "extraction_method", "evidence_version"):
        op.drop_column("parsed_records", col)
    for col in ("cancelled_by", "cancelled_at", "idempotency_key", "celery_task_id", "max_retries", "retry_count", "stage"):
        op.drop_column("evidence_processing_jobs", col)
    op.drop_table("graph_snapshots")
