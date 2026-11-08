"""one job per repository: API processes racing to queue the same repository can't both win

Revision ID: unique_jobs
Revises: jobs
Create Date: 2026-11-07
"""
import sqlalchemy as sa

from alembic import op

revision = "unique_jobs"
down_revision = "jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Before this index, two processes could each queue the same repository; keep the first job,
    # the one workers claim first (they claim in id order)
    op.execute(sa.text("DELETE FROM jobs WHERE id NOT IN (SELECT MIN(id) FROM jobs GROUP BY repository_id)"))
    op.drop_index("ix_jobs_repository_id", table_name="jobs")
    op.create_index("ix_jobs_repository_id", "jobs", ["repository_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_jobs_repository_id", table_name="jobs")
    op.create_index("ix_jobs_repository_id", "jobs", ["repository_id"])
