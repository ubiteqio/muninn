"""One face, and one question, per person on a photograph too

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-24

0039 did this for videos, where the same people come round frame after frame. A photograph can
say it twice as well - a collage, a picture of a picture, a mirror - and one of them carried
five faces of one child and four of another, every one confirmed by hand, because confirming
one question left the others standing and they had to be answered one after another.

The medium says who is in it. How often a face of them was found in it is not something anyone
is shown or can act on, so one face per person is kept here as well: what somebody assigned by
hand, else the clearest look. A guess at somebody the medium already has for certain goes, and
of the guesses that are left one per person keeps its question.

The square pictures of the faces that go stay on disk - a few kilobytes each that nothing
points at any more.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: A guess at somebody the medium already has for certain: answered, so it goes.
_ANSWERED = """
    DELETE FROM faces f
     WHERE f.person_id IS NULL
       AND f.suggested_person_id IS NOT NULL
       AND EXISTS (SELECT 1 FROM faces o
                    WHERE o.media_id = f.media_id
                      AND o.person_id = f.suggested_person_id)
"""

#: Of the questions left, one per medium and person: the nearest guess, clearest among equals.
_ASKED_AGAIN = """
    DELETE FROM faces f
     USING (SELECT id, row_number() OVER (
                     PARTITION BY media_id, suggested_person_id
                     ORDER BY suggested_distance, pixels * score DESC, id) AS rank
              FROM faces
             WHERE person_id IS NULL
               AND suggested_person_id IS NOT NULL) d
     WHERE d.id = f.id AND d.rank > 1
"""

#: The repeated sightings of somebody already named on the medium.
_SEEN_AGAIN = """
    DELETE FROM faces f
     USING (SELECT id, row_number() OVER (
                     PARTITION BY media_id, person_id
                     ORDER BY (assigned_by = 'user') DESC, pixels * score DESC, id) AS rank
              FROM faces
             WHERE person_id IS NOT NULL) d
     WHERE d.id = f.id AND d.rank > 1
"""


def upgrade() -> None:
    for statement in (_ANSWERED, _ASKED_AGAIN, _SEEN_AGAIN):
        op.execute(statement)


def downgrade() -> None:
    """What was collapsed cannot be unfolded: the sightings are gone."""
