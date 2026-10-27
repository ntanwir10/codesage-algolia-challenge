"""record the commit each index was built from

Revision ID: commit_sha
Revises: drop_unused_columns
Create Date: 2026-10-27
"""
import sqlalchemy as sa

from alembic import op

revision = "commit_sha"
down_revision = "drop_unused_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(sa.Column("commit_sha", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("commit_sha")
