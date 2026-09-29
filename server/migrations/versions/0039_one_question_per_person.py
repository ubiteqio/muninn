"""One face, and one question, per person on a video

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-24

A frame every few seconds sees the same people again and again. One face per person was kept
where somebody was named, but where nobody was certain yet every look asked its own question:
seven frames that all resembled Olivia asked seven times whether Olivia is in the video. Which
frame she was seen in leads nowhere - nothing shows the second or jumps to it - so the answer
to one is the answer to all of them.

New videos are collapsed as they are looked at. The ones already in the library are collapsed
here: per video and person the nearest guess keeps its question, and a guess at somebody who
is on the video for certain goes, because that question has its answer already.

The square pictures of the faces that go are left on disk. They are a few kilobytes each and
nothing points at them any more; the alternative is a migration that deletes files.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: A guess at somebody the video already has for certain: answered, so it goes.
_ANSWERED = """
    DELETE FROM faces f
     WHERE f.second IS NOT NULL
       AND f.person_id IS NULL
       AND f.suggested_person_id IS NOT NULL
       AND EXISTS (SELECT 1 FROM faces o
                    WHERE o.media_id = f.media_id
                      AND o.person_id = f.suggested_person_id)
"""

#: Of the questions left, one per video and person: the nearest guess, clearest among equals.
_ASKED_AGAIN = """
    DELETE FROM faces f
     USING (SELECT id, row_number() OVER (
                     PARTITION BY media_id, suggested_person_id
                     ORDER BY suggested_distance, pixels * score DESC, id) AS rank
              FROM faces
             WHERE second IS NOT NULL
               AND person_id IS NULL
               AND suggested_person_id IS NOT NULL) d
     WHERE d.id = f.id AND d.rank > 1
"""

#: The repeated sightings of somebody already named on the video. The rule always meant to keep
#: these to one; it only ever ran for videos looked at since it was written.
_SEEN_AGAIN = """
    DELETE FROM faces f
     USING (SELECT id, row_number() OVER (
                     PARTITION BY media_id, person_id
                     ORDER BY (assigned_by = 'user') DESC, pixels * score DESC, id) AS rank
              FROM faces
             WHERE second IS NOT NULL AND person_id IS NOT NULL) d
     WHERE d.id = f.id AND d.rank > 1
"""


def upgrade() -> None:
    for statement in (_ANSWERED, _ASKED_AGAIN, _SEEN_AGAIN):
        op.execute(statement)


def downgrade() -> None:
    """What was collapsed cannot be unfolded: the sightings are gone."""
