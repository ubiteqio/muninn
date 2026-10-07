"""The phones that hear of the bell

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-07

Every app installation that allowed notifications leaves the token its push service gave it, and
every entry of the bell remembers when it last went out as a push. An entry that grows - "Anna
und 2 weitere" - goes out again and replaces the push before it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name=op.f("fk_devices_user_id_users")),
            nullable=False,
        ),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("token", name=op.f("uq_devices_token")),
    )
    op.create_index(op.f("ix_devices_user_id"), "devices", ["user_id"])
    op.add_column("notifications", sa.Column("pushed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("notifications", "pushed_at")
    op.drop_index(op.f("ix_devices_user_id"), table_name="devices")
    op.drop_table("devices")
