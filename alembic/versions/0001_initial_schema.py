"""Initial tenant, build, event, artifact and domain schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "domain_verifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=120), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("token", sa.String(length=160), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("owner_id", "hostname", name="uq_owner_hostname"),
    )
    op.create_index("ix_domain_verifications_owner_id", "domain_verifications", ["owner_id"])
    op.create_index("ix_domain_verifications_hostname", "domain_verifications", ["hostname"])

    op.create_table(
        "builds",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("app_name", sa.String(length=50), nullable=False),
        sa.Column("package_id", sa.String(length=180), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=False),
        sa.Column("formats_json", sa.Text(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_owner_idempotency"),
    )
    op.create_index("ix_builds_owner_id", "builds", ["owner_id"])
    op.create_index("ix_builds_status", "builds", ["status"])

    op.create_table(
        "build_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("build_id", sa.String(length=36), sa.ForeignKey("builds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=12), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_build_events_build_id", "build_events", ["build_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("build_id", sa.String(length=36), sa.ForeignKey("builds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_build_id", "artifacts", ["build_id"])


def downgrade():
    op.drop_index("ix_artifacts_build_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_build_events_build_id", table_name="build_events")
    op.drop_table("build_events")
    op.drop_index("ix_builds_status", table_name="builds")
    op.drop_index("ix_builds_owner_id", table_name="builds")
    op.drop_table("builds")
    op.drop_index("ix_domain_verifications_hostname", table_name="domain_verifications")
    op.drop_index("ix_domain_verifications_owner_id", table_name="domain_verifications")
    op.drop_table("domain_verifications")
