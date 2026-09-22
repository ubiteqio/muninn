#!/usr/bin/env bash
# One gate for the whole repository: tests, linter and type check for server and app.
#
#   ./check.sh          everything, server, app and the embedding service, in parallel
#   ./check.sh server   server only
#   ./check.sh app      app only
#   ./check.sh embed    the embedding service only
#   ./check.sh fast     skip the tests that need the PostgreSQL container
#
# Exits non-zero as soon as any part failed, and prints which one.

set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${1:-all}"
log_dir="$(mktemp -d)"
trap 'rm -rf "$log_dir"' EXIT

run_server() {
    cd "$root/server" || return 1
    # Bash 3.2 ships with macOS and treats an empty array as unbound under `set -u`,
    # so the fast case runs its own command instead of expanding one.
    if [ "$target" = "fast" ]; then
        uv run pytest -q -m "not database" || return 1
    else
        uv run pytest -q || return 1
    fi
    uv run ruff check . || return 1
    uv run ruff format --check . || return 1
    uv run mypy . || return 1
}

run_embed() {
    cd "$root/embed" || return 1
    uv run pytest -q || return 1
    uv run ruff check . || return 1
    uv run ruff format --check . || return 1
    uv run mypy . || return 1
}

run_app() {
    cd "$root/app" || return 1
    pnpm test || return 1
    pnpm lint || return 1
    pnpm typecheck || return 1
}

declare -a names=()
declare -a pids=()

start() {
    local name="$1"
    "run_$name" >"$log_dir/$name.log" 2>&1 &
    names+=("$name")
    pids+=($!)
}

case "$target" in
    server) start server ;;
    app) start app ;;
    embed) start embed ;;
    all | fast) start server; start app; start embed ;;
    *) echo "unknown target: $target (use all, server, app, embed or fast)" >&2; exit 2 ;;
esac

failed=()
for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then
        failed+=("${names[$i]}")
    fi
done

for name in "${names[@]}"; do
    echo "===== $name ====="
    cat "$log_dir/$name.log"
done

if [ ${#failed[@]} -gt 0 ]; then
    echo
    echo "FAILED: ${failed[*]}"
    exit 1
fi

echo
echo "All checks passed (${names[*]})."
