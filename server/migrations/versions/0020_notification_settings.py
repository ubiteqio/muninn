"""Notification settings

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-21

Per person: which events also come as a push notification, and the quiet hours without any.
In the app every event appears regardless; this only decides about push. An account without a
row has the defaults of the concept.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "push", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("quiet_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("quiet_start", sa.Time(), nullable=False, server_default="22:00"),
        sa.Column("quiet_end", sa.Time(), nullable=False, server_default="07:00"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
