"""Log in with a username instead of an e-mail address

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-20

The e-mail address stays on the account as an attribute for later, but it is no longer what
people log in with, and no longer required: Muninn sends no mail, so nobody should need an address
to take part. Existing accounts get a username from the local part of their address.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Derives a username from the address, numbering duplicates so the unique index can be added.
BACKFILL = sa.text(
    """
    UPDATE users SET username = derived.candidate
    FROM (
        SELECT id,
               CASE WHEN rank = 1 THEN base ELSE base || rank::text END AS candidate
        FROM (
            SELECT id,
                   split_part(email, '@', 1) AS base,
                   row_number() OVER (
                       PARTITION BY lower(split_part(email, '@', 1))
                       ORDER BY created_at, id
                   ) AS rank
            FROM users
        ) ranked
    ) derived
    WHERE users.id = derived.id
    """
)


def upgrade() -> None:
    op.add_column("users", sa.Column("username", postgresql.CITEXT(), nullable=True))
    op.execute(BACKFILL)
    op.alter_column("users", "username", nullable=False)
    op.create_unique_constraint(op.f("uq_users_username"), "users", ["username"])

    # An address is now optional.
    op.alter_column("users", "email", nullable=True)


def downgrade() -> None:
    # Accounts without an address cannot exist in the old schema; they would have to log in with
    # something, so give them one derived from the username rather than deleting them.
    op.execute(sa.text("UPDATE users SET email = username || '@invalid' WHERE email IS NULL"))
    op.alter_column("users", "email", nullable=False)
    op.drop_constraint(op.f("uq_users_username"), "users", type_="unique")
    op.drop_column("users", "username")
