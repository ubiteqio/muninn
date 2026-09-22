#!/bin/sh
# Bring the database up to date before starting. Only the API does this; worker and scheduler
# start with MUNINN_RUN_MIGRATIONS=0 so that they cannot race the API on a fresh deployment.
set -eu

if [ "${MUNINN_RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "muninn: applying database migrations"
    alembic upgrade head
fi

exec "$@"
