"""The machines Muninn asks

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-21

One profile per interface - describing, picture vectors, word vectors - with the address, the
model and how hard Muninn may push. No model name and no address belongs in the code; this is
where they live instead.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    ai_kind = postgresql.ENUM(
        "analyzer", "image_embedder", "text_embedder", name="ai_kind", create_type=False
    )
    ai_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ai_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", ai_kind, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("concurrency", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="120"),
        # Null means "spare". Only true collides, because NULLs never equal each other - which
        # is exactly the rule "one machine in use per interface".
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("kind", "is_active", name="uq_ai_profiles_one_active"),
    )


def downgrade() -> None:
    op.drop_table("ai_profiles")
    postgresql.ENUM(name="ai_kind").drop(op.get_bind(), checkfirst=True)
