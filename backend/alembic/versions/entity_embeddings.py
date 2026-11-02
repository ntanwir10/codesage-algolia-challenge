"""semantic search: each definition's vector and the model that made it

Revision ID: entity_embeddings
Revises: commit_sha
Create Date: 2026-11-02
"""
import sqlalchemy as sa

from alembic import op

revision = "entity_embeddings"
down_revision = "commit_sha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("code_entities") as batch:
        batch.add_column(sa.Column("embedding", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("embedding_model", sa.String(200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("code_entities") as batch:
        batch.drop_column("embedding_model")
        batch.drop_column("embedding")
