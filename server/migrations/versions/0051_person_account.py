"""The account a person signs in with

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-07

An admin links a person to the account of whoever they are, so that person hears when somebody
comments on or reacts to a photo of them. One account is one person: the column is unique, and
an account that is deleted leaves the person unlinked rather than gone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("persons", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_persons_user_id_users"),
        "persons",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(op.f("uq_persons_user_id"), "persons", ["user_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_persons_user_id"), "persons", type_="unique")
    op.drop_constraint(op.f("fk_persons_user_id_users"), "persons", type_="foreignkey")
    op.drop_column("persons", "user_id")
