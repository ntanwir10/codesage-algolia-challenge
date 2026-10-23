"""baseline: the schema Base.metadata.create_all() produced before migrations

Revision ID: baseline
Revises:
Create Date: 2026-10-23
"""
import sqlalchemy as sa

from alembic import op

revision = "baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("branch", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("framework", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=True),
        sa.Column("total_lines", sa.Integer(), nullable=True),
        sa.Column("processed_files", sa.Integer(), nullable=True),
        sa.Column("repo_metadata", sa.JSON(), nullable=True),
        sa.Column("security_score", sa.Integer(), nullable=True),
        sa.Column("vulnerability_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repositories_id", "repositories", ["id"])
    op.create_index("ix_repositories_framework", "repositories", ["framework"])
    op.create_index("ix_repositories_name", "repositories", ["name"])
    op.create_index("ix_repositories_status", "repositories", ["status"])
    op.create_index("ix_repositories_language", "repositories", ["language"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_collaborative", sa.Boolean(), nullable=True),
        sa.Column("room_id", sa.String(length=255), nullable=True),
        sa.Column("is_websocket_connected", sa.Boolean(), nullable=True),
        sa.Column("websocket_id", sa.String(length=255), nullable=True),
        sa.Column("active_repository_id", sa.Integer(), nullable=True),
        sa.Column("active_file_path", sa.String(length=1000), nullable=True),
        sa.Column("session_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "last_activity",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_session_id", "sessions", ["session_id"], unique=True)
    op.create_index("ix_sessions_room_id", "sessions", ["room_id"])
    op.create_index("ix_sessions_id", "sessions", ["id"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "code_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("line_count", sa.Integer(), nullable=True),
        sa.Column("is_analyzed", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_files_language", "code_files", ["language"])
    op.create_index("ix_code_files_file_path", "code_files", ["file_path"])
    op.create_index("ix_code_files_file_name", "code_files", ["file_name"])
    op.create_index("ix_code_files_id", "code_files", ["id"])
    op.create_index("ix_code_files_repository_id", "code_files", ["repository_id"])

    op.create_table(
        "search_indexes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("algolia_object_id", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search_metadata", sa.JSON(), nullable=True),
        sa.Column("is_indexed", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_indexes_algolia_object_id",
        "search_indexes",
        ["algolia_object_id"],
        unique=True,
    )
    op.create_index("ix_search_indexes_entity_name", "search_indexes", ["entity_name"])
    op.create_index("ix_search_indexes_entity_type", "search_indexes", ["entity_type"])
    op.create_index("ix_search_indexes_id", "search_indexes", ["id"])
    op.create_index(
        "ix_search_indexes_repository_id", "search_indexes", ["repository_id"]
    )

    op.create_table(
        "code_entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=500), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("start_column", sa.Integer(), nullable=True),
        sa.Column("end_column", sa.Integer(), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("complexity_score", sa.Integer(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=True),
        sa.Column("is_async", sa.Boolean(), nullable=True),
        sa.Column("entity_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["code_files.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_entities_file_id", "code_entities", ["file_id"])
    op.create_index("ix_code_entities_entity_name", "code_entities", ["entity_name"])
    op.create_index("ix_code_entities_entity_type", "code_entities", ["entity_type"])
    op.create_index("ix_code_entities_id", "code_entities", ["id"])
    op.create_index(
        "ix_code_entities_repository_id", "code_entities", ["repository_id"]
    )
    op.create_index("ix_code_entities_full_name", "code_entities", ["full_name"])


def downgrade() -> None:
    for table in (
        "code_entities",
        "search_indexes",
        "code_files",
        "sessions",
        "repositories",
    ):
        op.drop_table(table)
