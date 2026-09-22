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

# stat speaks differently on Linux and macOS; both are used to run Muninn.
owner_of() {
    stat -c '%u %g' "$1" 2>/dev/null || stat -f '%u %g' "$1"
}

mode_of() {
    stat -c '%A' "$1" 2>/dev/null || stat -f '%Sp' "$1"
}

absolute() {
    case "$1" in
        /*) printf '%s' "$1" ;;
        *) printf '%s' "$SCRIPT_DIR/$1" ;;
    esac
}

# Can a container read the library? Asked the only way that really answers it: by reading it,
# as the user Muninn would be. A NAS share belongs to one user and one group and lets nobody
# else in - not even through that group, on some systems.
readable_as() {
    # readable_as <uid> <gid> <path>
    docker run --rm --user "$1:$2" -v "$(absolute "$3"):/library:ro" \
        alpine sh -c 'ls /library >/dev/null 2>&1' >/dev/null 2>&1
}

setting() {
    # setting <name> <default>: what the configuration says, or the default.
    value=$(grep "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d "'\"")
    [ -n "$value" ] && printf '%s' "$value" || printf '%s' "$2"
}

if [ -f "$ENV_FILE" ]; then
    echo "Configuration $ENV_FILE already exists, keeping it."

    # It may predate the day Muninn learned about NAS permissions, so check it can read.
    library_path=$(setting MUNINN_LIBRARY_HOST_PATH ../data/library)
    run_uid=$(setting MUNINN_UID 1000)
    run_gid=$(setting MUNINN_GID 1000)
    if [ -d "$(absolute "$library_path")" ] && ! readable_as "$run_uid" "$run_gid" "$library_path"; then
        library_uid=$(owner_of "$(absolute "$library_path")" | cut -d' ' -f1)
        library_gid=$(owner_of "$(absolute "$library_path")" | cut -d' ' -f2)
        echo
        echo "Warning: as $run_uid:$run_gid, Muninn cannot read $library_path."
        echo "The folder belongs to $library_uid:$library_gid. Put this into $ENV_FILE and start again:"
        echo "  MUNINN_UID=$library_uid"
        echo "  MUNINN_GID=$library_gid"
        echo "  and: chown -R $library_uid:$library_gid $(setting MUNINN_DERIVED_HOST_PATH ../data/derived)"
        echo
    fi
else
    echo "Setting up Muninn. Press Enter to accept the value in brackets."
    echo

    library_path=$(ask "Path to the NAS library (read-only)" "../data/library")
    derived_path=$(ask "Path for thumbnails and previews" "../data/derived")
    api_port=$(ask "Port for the API on this machine" "8000")

    # Who Muninn runs as. Where the library is open to everybody, the user in the image is
    # enough. Where it is not, Muninn takes the library's own user, or it cannot read a thing.
    run_uid=1000
    run_gid=1000
    if [ -d "$library_path" ] && ! readable_as 1000 1000 "$library_path"; then
        library_uid=$(owner_of "$library_path" | cut -d' ' -f1)
        library_gid=$(owner_of "$library_path" | cut -d' ' -f2)
        echo
        echo "Muninn cannot read $library_path as its own user ($(mode_of "$library_path"))."
        if readable_as "$library_uid" "$library_gid" "$library_path"; then
            echo "As $library_uid:$library_gid, the folder's own user, it can."
            answer=$(ask "Run Muninn as $library_uid:$library_gid? (yes/no)" "yes")
            case "$answer" in
                y* | Y* | j* | J*)
                    run_uid=$library_uid
                    run_gid=$library_gid
                    ;;
            esac
        else
            echo "Its owner $library_uid:$library_gid cannot read it either. Give the folder or"
            echo "the share read access for the user Muninn should run as, then start again."
            exit 1
        fi
    fi

    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"

    # Fill in the generated secrets and the answers. A temporary file keeps this atomic.
    tmp=$(mktemp)
    sed \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret 24)|" \
        -e "s|^MUNINN_JWT_SECRET=.*|MUNINN_JWT_SECRET=$(secret 48)|" \
        -e "s|^MUNINN_API_PORT=.*|MUNINN_API_PORT=${api_port}|" \
        -e "s|^MUNINN_LIBRARY_HOST_PATH=.*|MUNINN_LIBRARY_HOST_PATH=${library_path}|" \
        -e "s|^MUNINN_DERIVED_HOST_PATH=.*|MUNINN_DERIVED_HOST_PATH=${derived_path}|" \
        -e "s|^# *MUNINN_UID=.*|MUNINN_UID=${run_uid}|" \
        -e "s|^# *MUNINN_GID=.*|MUNINN_GID=${run_gid}|" \
        "$ENV_FILE" > "$tmp"
    mv "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"

    # The previews are the one place Muninn writes, so the folder has to belong to the user it
    # runs as. Docker would otherwise create it as root and every preview would fail.
    mkdir -p "$derived_path"
    if [ "$(owner_of "$derived_path")" != "$run_uid $run_gid" ] \
        && ! chown -R "$run_uid:$run_gid" "$derived_path" 2>/dev/null; then
        echo
        echo "Note: $derived_path does not belong to $run_uid:$run_gid, and this account may not"
        echo "change that. Muninn cannot write previews until it does:"
        echo "  sudo chown -R $run_uid:$run_gid $derived_path"
    fi

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
