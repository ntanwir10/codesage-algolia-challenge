"""a table of indexing jobs, for workers in other processes (INDEX_WORKERS=external)

Revision ID: jobs
Revises: entity_embeddings
Create Date: 2026-11-02
"""
import sqlalchemy as sa

from alembic import op

revision = "jobs"
down_revision = "entity_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("force_reprocess", sa.Boolean(), nullable=False),
        sa.Column("incremental", sa.Boolean(), nullable=False),
        sa.Column("claimed_by", sa.String(200), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_repository_id", "jobs", ["repository_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_repository_id", table_name="jobs")
    op.drop_table("jobs")
