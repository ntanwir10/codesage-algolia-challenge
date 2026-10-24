"""drop columns nothing reads or writes

Revision ID: drop_unused_columns
Revises: cleanup
Create Date: 2026-10-23
"""
import sqlalchemy as sa

from alembic import op

revision = "drop_unused_columns"
down_revision = "cleanup"
branch_labels = None
depends_on = None

_ENTITY_COLUMNS = (
    "full_name",
    "start_column",
    "end_column",
    "complexity_score",
    "is_public",
    "is_async",
)
_FILE_COLUMNS = ("file_name", "is_analyzed", "size_bytes")
_REPOSITORY_COLUMNS = ("repo_metadata", "security_score", "vulnerability_count")


def upgrade() -> None:
    # Indexes on dropped columns go first; batch mode rebuilds the table
    # and would otherwise try to recreate them.
    op.drop_index("ix_code_entities_full_name", table_name="code_entities")
    op.drop_index("ix_code_files_file_name", table_name="code_files")

    with op.batch_alter_table("code_entities") as batch:
        for column in _ENTITY_COLUMNS:
            batch.drop_column(column)
    with op.batch_alter_table("code_files") as batch:
        for column in _FILE_COLUMNS:
            batch.drop_column(column)
    with op.batch_alter_table("repositories") as batch:
        for column in _REPOSITORY_COLUMNS:
            batch.drop_column(column)


def downgrade() -> None:
    # Columns come back nullable and empty; the dropped values are not recoverable.
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(sa.Column("repo_metadata", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("security_score", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("vulnerability_count", sa.Integer(), nullable=True))

    with op.batch_alter_table("code_files") as batch:
        batch.add_column(sa.Column("file_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("is_analyzed", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.create_index("ix_code_files_file_name", "code_files", ["file_name"])

    with op.batch_alter_table("code_entities") as batch:
        batch.add_column(sa.Column("full_name", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("start_column", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("end_column", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("complexity_score", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("is_public", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("is_async", sa.Boolean(), nullable=True))
    op.create_index("ix_code_entities_full_name", "code_entities", ["full_name"])
