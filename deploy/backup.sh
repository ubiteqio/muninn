#!/usr/bin/env bash
#
# Backs the database up into one archive.
#
# The database is the only thing in Muninn that cannot be made again: the originals lie on the
# NAS untouched and the previews are computed from them, but albums, people, faces, comments,
# likes and settings live here alone.
#
# The dump is taken with the stack stopped. A dump shares the server with whoever else is
# querying it, and one crashing backend takes every connection with it - which is how a backup
# ends up as a torso that still looks like a file. With --hot the services stay up.
#
#   ./deploy/backup.sh                 # stop the stack, dump, pack, start again
#   ./deploy/backup.sh --hot           # leave the stack running
#   ./deploy/backup.sh --keep 14       # how many archives to keep (default 7)
#   ./deploy/backup.sh --out /volume2/backups
#
# It writes backups/muninn-<date>.tar.gz and says plainly whether the dump is whole. The archive
# carries three things: the dump, a note of when and by which server version it was taken, and
# the definitions of the vector indexes, which are worth having when one has to be built again.
# It packs rather than compresses - pg_dump already compresses, and the vectors leave gzip
# nothing to find: 117 MB either way, measured.

set -uo pipefail

KEEP=7
OUT=""
HOT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --hot) HOT=1; shift ;;
    --keep) KEEP=${2:-7}; shift 2 ;;
    --out) OUT=${2:-}; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

cd "$(dirname "$0")/.." || exit 1
[ -f deploy/docker-compose.yml ] || {
  echo "Run this from the Muninn folder." >&2
  exit 1
}

COMPOSE=(docker compose -f deploy/docker-compose.yml)
STAMP=$(date +%F-%H%M)
DIR=${OUT:-backups}
WORK="$DIR/.muninn-$STAMP"
ARCHIVE="$DIR/muninn-$STAMP.tar.gz"

mkdir -p "$WORK" || exit 1
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Everything the stack holds except the database - asked of compose, so a service added later
# is stopped as well.
APPS=()
while IFS= read -r service; do
  [ -n "$service" ] && APPS+=("$service")
done < <("${COMPOSE[@]}" config --services 2>/dev/null | grep -vx "postgres")

if [ "$HOT" -eq 0 ] && [ "${#APPS[@]}" -gt 0 ]; then
  echo "==> Stopping the stack"
  "${COMPOSE[@]}" stop "${APPS[@]}" </dev/null >/dev/null 2>&1
fi

start_again() {
  if [ "$HOT" -eq 0 ] && [ "${#APPS[@]}" -gt 0 ]; then
    echo "==> Starting the stack again"
    "${COMPOSE[@]}" up -d </dev/null >/dev/null 2>&1
  fi
}

echo "==> Dumping the database"
if ! "${COMPOSE[@]}" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$WORK/muninn.dump"; then
  echo "The dump broke off - $ARCHIVE was not written." >&2
  echo "See docs/updating.md, \"When the dump breaks off\"." >&2
  start_again
  exit 1
fi

# A dump that broke off still looks like a file, so the table count is what proves it whole.
# pg_restore reads the archive from its standard input when no file is named; handed a path
# such as /dev/stdin it seeks, finds nothing, and says the dump is empty.
TABLES=$("${COMPOSE[@]}" exec -T postgres pg_restore -l < "$WORK/muninn.dump" 2>/dev/null \
  | grep -c "TABLE DATA")
if [ "${TABLES:-0}" -lt 5 ]; then
  echo "The dump holds only ${TABLES:-0} tables - not to be trusted." >&2
  start_again
  exit 1
fi

# What the database is made of, beside the data: the version it was written by, and the vector
# indexes, whose definitions are worth having when one of them has to be built again.
{
  echo "taken:     $(date -Iseconds)"
  echo "host:      $(hostname)"
  echo "tables:    $TABLES"
  printf 'server:    '
  printf '%s\n' "SELECT version();" | "${COMPOSE[@]}" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' 2>/dev/null | head -1
} > "$WORK/manifest.txt"

printf '%s\n' "SELECT pg_get_indexdef(i.indexrelid) || ';'
               FROM pg_index i
               JOIN pg_class c ON c.oid = i.indexrelid
               JOIN pg_am am ON am.oid = c.relam
               WHERE am.amname IN ('hnsw', 'ivfflat')
               ORDER BY c.relname;" \
  | "${COMPOSE[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' \
  > "$WORK/vector-indexes.sql" 2>/dev/null

echo "==> Packing"
if ! tar -czf "$ARCHIVE" -C "$WORK" muninn.dump manifest.txt vector-indexes.sql; then
  echo "Packing failed." >&2
  start_again
  exit 1
fi

start_again

# Only whole archives are counted, so a failed run never pushes a good one out of the window.
if [ "$KEEP" -gt 0 ]; then
  ls -1t "$DIR"/muninn-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    echo "    removing $old"
    rm -f "$old"
  done
fi

echo
echo "Backup: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1)), $TABLES tables"
echo "Restore it with:"
echo "  tar -xzf $ARCHIVE -C /tmp"
echo "  docker compose -f deploy/docker-compose.yml exec -T postgres \\"
echo "    sh -c 'pg_restore --clean --if-exists -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"' < /tmp/muninn.dump"
