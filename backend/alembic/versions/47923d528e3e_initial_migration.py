"""Initial migration

Revision ID: 47923d528e3e
Revises:
Create Date: 2025-07-19 14:06:14.539365

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "47923d528e3e"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create repositories table
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("branch", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("framework", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False),
        sa.Column("processed_files", sa.Integer(), nullable=False),
        sa.Column("total_lines", sa.Integer(), nullable=False),
        sa.Column("security_score", sa.Float(), nullable=True),
        sa.Column("vulnerability_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_repositories_id"), "repositories", ["id"], unique=False)
    op.create_index(
        op.f("ix_repositories_language"), "repositories", ["language"], unique=False
    )
    op.create_index(
        op.f("ix_repositories_name"), "repositories", ["name"], unique=False
    )
    op.create_index(
        op.f("ix_repositories_status"), "repositories", ["status"], unique=False
    )
    op.create_index(op.f("ix_repositories_url"), "repositories", ["url"], unique=True)

    # Create code_files table
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
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_code_files_file_name"), "code_files", ["file_name"], unique=False
    )
    op.create_index(
        op.f("ix_code_files_file_path"), "code_files", ["file_path"], unique=False
    )
    op.create_index(op.f("ix_code_files_id"), "code_files", ["id"], unique=False)
    op.create_index(
        op.f("ix_code_files_language"), "code_files", ["language"], unique=False
    )
    op.create_index(
        op.f("ix_code_files_repository_id"),
        "code_files",
        ["repository_id"],
        unique=False,
    )

    # Create code_entities table
    op.create_table(
        "code_entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_file_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("complexity_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["code_file_id"],
            ["code_files.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_code_entities_entity_type"),
        "code_entities",
        ["entity_type"],
        unique=False,
    )
    op.create_index(op.f("ix_code_entities_id"), "code_entities", ["id"], unique=False)
    op.create_index(
        op.f("ix_code_entities_name"), "code_entities", ["name"], unique=False
    )

    # Create search_indexes table
    op.create_table(
        "search_indexes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("algolia_object_id", sa.String(length=255), nullable=False),
        sa.Column("index_name", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.String(length=50), nullable=True),
        sa.Column("entity_name", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("file_path", sa.String(length=1000), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("security_score", sa.Float(), nullable=True),
        sa.Column("complexity_score", sa.Float(), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=True),
        sa.Column("is_indexed", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_search_indexes_algolia_object_id"),
        "search_indexes",
        ["algolia_object_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_search_indexes_entity_type"),
        "search_indexes",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_indexes_id"), "search_indexes", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_search_indexes_repository_id"),
        "search_indexes",
        ["repository_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f("ix_search_indexes_repository_id"), table_name="search_indexes")
    op.drop_index(op.f("ix_search_indexes_id"), table_name="search_indexes")
    op.drop_index(op.f("ix_search_indexes_entity_type"), table_name="search_indexes")
    op.drop_index(
        op.f("ix_search_indexes_algolia_object_id"), table_name="search_indexes"
    )
    op.drop_table("search_indexes")

    op.drop_index(op.f("ix_code_entities_name"), table_name="code_entities")
    op.drop_index(op.f("ix_code_entities_id"), table_name="code_entities")
    op.drop_index(op.f("ix_code_entities_entity_type"), table_name="code_entities")
    op.drop_table("code_entities")

    op.drop_index(op.f("ix_code_files_repository_id"), table_name="code_files")
    op.drop_index(op.f("ix_code_files_language"), table_name="code_files")
    op.drop_index(op.f("ix_code_files_id"), table_name="code_files")
    op.drop_index(op.f("ix_code_files_file_path"), table_name="code_files")
    op.drop_index(op.f("ix_code_files_file_name"), table_name="code_files")
    op.drop_table("code_files")

    op.drop_index(op.f("ix_repositories_url"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_status"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_name"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_language"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_id"), table_name="repositories")
    op.drop_table("repositories")
