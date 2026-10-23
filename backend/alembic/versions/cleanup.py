"""cleanup: drop unused tables, dedupe repository URLs, make url unique

Revision ID: cleanup
Revises: baseline
Create Date: 2026-10-23
"""
import sqlalchemy as sa

from alembic import op

revision = "cleanup"
down_revision = "baseline"
branch_labels = None
depends_on = None

_DUPLICATES = (
    "SELECT id FROM repositories WHERE url IS NOT NULL AND id NOT IN "
    "(SELECT MAX(id) FROM repositories WHERE url IS NOT NULL GROUP BY url) "
    "AND url IN (SELECT url FROM repositories WHERE url IS NOT NULL "
    "GROUP BY url HAVING COUNT(*) > 1)"
)


def upgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("search_indexes")

    # Keep the newest (highest id) repository per URL; remove children first.
    op.execute(f"DELETE FROM code_entities WHERE repository_id IN ({_DUPLICATES})")
    op.execute(f"DELETE FROM code_files WHERE repository_id IN ({_DUPLICATES})")
    op.execute(f"DELETE FROM repositories WHERE id IN ({_DUPLICATES})")

    with op.batch_alter_table("repositories") as batch:
        batch.create_unique_constraint("uq_repositories_url", ["url"])


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_constraint("uq_repositories_url", type_="unique")

    # Tables are restored empty; deleted duplicate repositories are not recoverable.
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
