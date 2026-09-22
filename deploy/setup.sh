#!/bin/sh
# Set Muninn up: create the configuration, generate the secrets, start the package and create the
# first admin. Safe to run again; an existing .env is kept as it is.
#
#   ./deploy/setup.sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE="$SCRIPT_DIR/.env"
COMPOSE="docker compose -f $SCRIPT_DIR/docker-compose.yml"

secret() {
    openssl rand -base64 "$1" | tr -d '\n'
}

ask() {
    # ask <question> <default>
    printf '%s [%s]: ' "$1" "$2" >&2
    read -r answer
    [ -n "$answer" ] && printf '%s' "$answer" || printf '%s' "$2"
}

if [ -f "$ENV_FILE" ]; then
    echo "Configuration $ENV_FILE already exists, keeping it."
else
    echo "Setting up Muninn. Press Enter to accept the value in brackets."
    echo

    library_path=$(ask "Path to the NAS library (read-only)" "../data/library")
    derived_path=$(ask "Path for thumbnails and previews" "../data/derived")
    api_port=$(ask "Port for the API on this machine" "8000")

    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"

    # Fill in the generated secrets and the answers. A temporary file keeps this atomic.
    tmp=$(mktemp)
    sed \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret 24)|" \
        -e "s|^MUNINN_JWT_SECRET=.*|MUNINN_JWT_SECRET=$(secret 48)|" \
        -e "s|^MUNINN_API_PORT=.*|MUNINN_API_PORT=${api_port}|" \
        -e "s|^MUNINN_LIBRARY_HOST_PATH=.*|MUNINN_LIBRARY_HOST_PATH=${library_path}|" \
        -e "s|^MUNINN_DERIVED_HOST_PATH=.*|MUNINN_DERIVED_HOST_PATH=${derived_path}|" \
        "$ENV_FILE" > "$tmp"
    mv "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"

    echo
    echo "Wrote $ENV_FILE."
fi

echo "Starting the containers. The first run builds the images and takes a while."
$COMPOSE up -d --build

echo "Waiting for the API to be ready."
attempt=0
until $COMPOSE exec -T api python -c "
import urllib.request
urllib.request.urlopen('http://127.0.0.1:8000/ready')
" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -gt 60 ]; then
        echo "The API did not become ready. Check: $COMPOSE logs api" >&2
        exit 1
    fi
    sleep 2
done

if $COMPOSE exec -T api python -c "
import asyncio, sys
from sqlalchemy import func, select
from muninn.core.config import get_settings
from muninn.core.db import create_engine, create_session_factory
from muninn.models.user import User

async def main() -> None:
    engine = create_engine(get_settings().database_url)
    try:
        async with create_session_factory(engine)() as session:
            count = await session.scalar(select(func.count()).select_from(User))
    finally:
        await engine.dispose()
    sys.exit(0 if count else 1)

asyncio.run(main())
" >/dev/null 2>&1; then
    echo "An account already exists, skipping the admin setup."
else
    echo
    echo "Creating the first admin."
    admin_username=$(ask "Username" "admin")
    admin_name=$(ask "Display name" "Admin")
    $COMPOSE exec api python -m muninn.cli create-admin \
        --username "$admin_username" --name "$admin_name"
fi

web_port=$(grep '^MUNINN_WEB_PORT=' "$ENV_FILE" | cut -d= -f2)
web_port=${web_port:-9090}

echo
echo "Muninn is running."
echo "  In the house: http://$(hostname):$web_port"
echo "  On this machine: http://127.0.0.1:$web_port"
echo "  API description: http://127.0.0.1:$(grep '^MUNINN_API_PORT=' "$ENV_FILE" | cut -d= -f2)/api/v1/docs"
