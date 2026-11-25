"""Add Milestone 3 intelligence persistence tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26 00:20:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    is_pg = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)
    json_type = postgresql.JSONB() if is_pg else sa.Text()

    if "identity_hypotheses" not in existing:
        op.create_table(
            "identity_hypotheses",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("hypothesis_key", sa.String(64), nullable=False),
            sa.Column("person_a_ref", sa.String(), nullable=False),
            sa.Column("person_b_ref", sa.String(), nullable=False),
            sa.Column("person_a_name", sa.String(), nullable=True),
            sa.Column("person_b_name", sa.String(), nullable=True),
            sa.Column("case_a_id", uuid_type, nullable=True),
            sa.Column("case_b_id", uuid_type, nullable=True),
            sa.Column("case_a_ref", sa.String(), nullable=False),
            sa.Column("case_b_ref", sa.String(), nullable=False),
            sa.Column("match_probability", sa.Float(), nullable=False),
            sa.Column("confidence_tier", sa.String(), nullable=False),
            sa.Column("model_version", sa.String(), nullable=False),
            sa.Column("feature_explanation", json_type, nullable=False),
            sa.Column("supporting_evidence", json_type, nullable=False),
            sa.Column("conflicting_evidence", json_type, nullable=False),
            sa.Column("blocking_reasons", json_type, nullable=False),
            sa.Column("profile_a_snapshot", json_type, nullable=False),
            sa.Column("profile_b_snapshot", json_type, nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("reviewed_by", uuid_type, nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_rationale", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_identity_hypotheses_key", "identity_hypotheses", ["hypothesis_key"], unique=True)

    if "identity_hypothesis_decisions" not in existing:
        op.create_table(
            "identity_hypothesis_decisions",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("hypothesis_id", uuid_type, nullable=False),
            sa.Column("previous_status", sa.String(), nullable=True),
            sa.Column("new_status", sa.String(), nullable=False),
            sa.Column("reviewer_id", uuid_type, nullable=True),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["hypothesis_id"], ["identity_hypotheses.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "intelligence_leads" not in existing:
        op.create_table(
            "intelligence_leads",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("lead_code", sa.String(64), nullable=False),
            sa.Column("source_entity", sa.String(), nullable=False),
            sa.Column("target_entity", sa.String(), nullable=False),
            sa.Column("source_case_ids", json_type, nullable=False),
            sa.Column("target_case_ids", json_type, nullable=False),
            sa.Column("is_cross_case", sa.Boolean(), nullable=False),
            sa.Column("candidate_relationship_type", sa.String(), nullable=False),
            sa.Column("model_version", sa.String(), nullable=False),
            sa.Column("graph_snapshot_version", sa.String(), nullable=True),
            sa.Column("prediction_score", sa.Float(), nullable=False),
            sa.Column("priority_tier", sa.String(), nullable=False),
            sa.Column("evidence_strength", sa.String(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("supporting_modalities", json_type, nullable=False),
            sa.Column("common_intermediates", json_type, nullable=False),
            sa.Column("caveats", json_type, nullable=False),
            sa.Column("supporting_records", json_type, nullable=False),
            sa.Column("conflicting_records", json_type, nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("reviewed_by", uuid_type, nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_rationale", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_intelligence_leads_lead_code", "intelligence_leads", ["lead_code"], unique=True)

    if "lead_decisions" not in existing:
        op.create_table(
            "lead_decisions",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("lead_id", uuid_type, nullable=False),
            sa.Column("previous_status", sa.String(), nullable=True),
            sa.Column("new_status", sa.String(), nullable=False),
            sa.Column("reviewer_id", uuid_type, nullable=True),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["lead_id"], ["intelligence_leads.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "consistency_analyses" not in existing:
        op.create_table(
            "consistency_analyses",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("result_id", sa.String(128), nullable=False),
            sa.Column("case_id", uuid_type, nullable=True),
            sa.Column("case_ref", sa.String(), nullable=False),
            sa.Column("subject_entity_id", sa.String(), nullable=False),
            sa.Column("statement_text", sa.Text(), nullable=False),
            sa.Column("source_document_id", sa.String(), nullable=True),
            sa.Column("original_claim", json_type, nullable=False),
            sa.Column("current_claim", json_type, nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("confidence_breakdown", json_type, nullable=False),
            sa.Column("matched_evidence", json_type, nullable=False),
            sa.Column("conflicting_evidence", json_type, nullable=False),
            sa.Column("caveats", json_type, nullable=False),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("recommended_action", sa.Text(), nullable=False),
            sa.Column("reviewer_comment", sa.Text(), nullable=True),
            sa.Column("reviewed_by", uuid_type, nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_consistency_analyses_result_id", "consistency_analyses", ["result_id"], unique=True)

    if "model_artifact_registry" not in existing:
        op.create_table(
            "model_artifact_registry",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("model_name", sa.String(), nullable=False),
            sa.Column("version", sa.String(), nullable=False),
            sa.Column("feature_schema_version", sa.String(), nullable=False),
            sa.Column("artifact_uri", sa.String(), nullable=False),
            sa.Column("training_snapshot_id", sa.String(), nullable=True),
            sa.Column("evaluation_report", json_type, nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("model_artifact_registry")
    op.drop_table("consistency_analyses")
    op.drop_table("lead_decisions")
    op.drop_table("intelligence_leads")
    op.drop_table("identity_hypothesis_decisions")
    op.drop_table("identity_hypotheses")
