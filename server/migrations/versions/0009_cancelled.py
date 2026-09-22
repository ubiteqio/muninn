"""A read can be stopped

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-20

An admin can stop a running read. It stops between folders, so what it already read is kept -
which is a different outcome from "failed" and says so.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Adding a value to an enum cannot happen inside a transaction that then uses it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE scan_status ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single value from an enum, and rewriting the type would mean
    # rewriting every column that uses it. The value simply stays unused.
    pass
