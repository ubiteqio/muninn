#!/usr/bin/env bash
#
# One face per person in a video.
#
# A video is looked at every few seconds, so the same person is found again and again and ends
# up with several faces on one medium. This removes the extra ones: every person keeps the face
# somebody assigned by hand, or else the clearest look, and a guess about somebody who is on the
# video for certain already is dropped with them. Photos are never touched - two faces of one
# person in a photo are two different people.
#
# It works through the containers that are already running, so it needs no new image and no
# deployment. Without --apply it only says what it would remove.
#
#   ./deploy/collapse-video-faces.sh           # count what would go
#   ./deploy/collapse-video-faces.sh --apply   # remove it
#
# The faces that go take their vectors with them, because both live in the same row, and their
# square pictures under /data/derived are deleted as well.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose -f "$here/docker-compose.yml")
apply=""
if [ "${1:-}" = "--apply" ]; then
    apply=1
elif [ -n "${1:-}" ]; then
    echo "usage: $(basename "$0") [--apply]" >&2
    exit 2
fi

# The faces that are one sighting too many: every person beyond the first on a video, ordered so
# that a hand-assigned face wins, then the biggest and surest look. Plus every guess about
# somebody who already has a face on that same video.
extra="
WITH ranked AS (
    SELECT id, media_id,
           row_number() OVER (
               PARTITION BY media_id, person_id
               ORDER BY (assigned_by = 'user') DESC, pixels * score DESC, id
           ) AS place
      FROM faces
     WHERE second IS NOT NULL AND person_id IS NOT NULL
),
extra AS (
    SELECT id, media_id FROM ranked WHERE place > 1
    UNION
    SELECT guess.id, guess.media_id
      FROM faces guess
      JOIN faces sure
        ON sure.media_id = guess.media_id
       AND sure.person_id = guess.suggested_person_id
     WHERE guess.second IS NOT NULL
       AND guess.person_id IS NULL
       AND guess.suggested_person_id IS NOT NULL
)"

# Where the square picture of a face lies, relative to /data/derived: the same layout the server
# writes, <first two of the medium>/<the medium>/face-<first sixteen of the face>.webp
crop="substr(replace(media_id::text, '-', ''), 1, 2) || '/'
   || replace(media_id::text, '-', '') || '/face-'
   || substr(replace(id::text, '-', ''), 1, 16) || '.webp'"

sql() {
    "${compose[@]}" exec -T postgres sh -c \
        'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"' _ "$1"
}

if [ -z "$apply" ]; then
    echo "Videos with a person more than once, and what would go:"
    sql "$extra
         SELECT count(*) || ' faces on ' || count(DISTINCT media_id) || ' videos'
           FROM extra;"
    echo
    echo "Nothing was changed. Run with --apply to remove them."
    exit 0
fi

echo "Removing the extra faces…"
crops="$(sql "$extra
              DELETE FROM faces WHERE id IN (SELECT id FROM extra)
              RETURNING $crop;")"

if [ -z "$crops" ]; then
    echo "Nothing to do: every person already has one face per video."
    exit 0
fi

echo "$crops" | wc -l | tr -d ' ' | xargs printf '%s faces removed.\n'

# The square pictures, inside a container that has /data/derived mounted. A picture that stays
# behind is harmless - nothing points at it any more - so a refusal here is a warning, not a
# failure.
if printf '%s\n' "$crops" \
    | "${compose[@]}" exec -T api sh -c 'cd /data/derived && xargs -r rm -f' 2>/dev/null; then
    echo "Their square pictures are gone too."
else
    echo "Warning: the square pictures could not be deleted (permissions on /data/derived)." >&2
    echo "         They are orphans now and harmless; nothing reads them any more." >&2
fi
