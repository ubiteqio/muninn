"""What a stage tried and could not do

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-23

A medium the pipeline cannot handle came back every minute: the stage gave up, wrote nothing
down, and the clock handed it out again because it still counted as outstanding. Two damaged
videos were enough to keep a worker busy for a day.

Failed attempts are counted here, and after a few of them the clock leaves that medium alone
until somebody asks for it again.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE media_attempts (
            media_id uuid NOT NULL REFERENCES media(id) ON DELETE CASCADE,
            stage varchar(24) NOT NULL,
            attempts smallint NOT NULL DEFAULT 1,
            last_error text,
            last_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (media_id, stage)
        )
        """
    )
    # Every stage asks the same question when it hands out work: which media has it given up on.
    op.execute("CREATE INDEX ix_media_attempts_stage ON media_attempts (stage, attempts)")


def downgrade() -> None:
    op.execute("DROP TABLE media_attempts")
