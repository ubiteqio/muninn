"""Command line helpers that run inside the server container.

docker compose -f deploy/docker-compose.yml exec api python -m muninn.cli create-admin
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from muninn.core.config import get_settings
from muninn.core.db import create_engine, create_session_factory
from muninn.core.security import hash_password, password_problem
from muninn.faces import people
from muninn.media import service as media_service
from muninn.models.user import User, UserRole, UserStatus


async def _create_admin(username: str, display_name: str, email: str | None, password: str) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            existing = await session.scalar(select(User).where(User.username == username))
            if existing is not None:
                print(f"error: an account named {username} already exists", file=sys.stderr)
                return 1

            session.add(
                User(
                    username=username,
                    email=email,
                    display_name=display_name,
                    password_hash=hash_password(password),
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                    # The first admin chooses the password here, so nothing needs replacing.
                    must_change_password=False,
                )
            )
            await session.commit()
    finally:
        await engine.dispose()

    print(f"admin {username} created")
    return 0


def _read_password(from_stdin: bool) -> str | None:
    if from_stdin:
        password = sys.stdin.readline().strip()
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("error: the passwords do not match", file=sys.stderr)
            return None

    problem = password_problem(password)
    if problem is not None:
        print(f"error: {problem.lower().rstrip('.')}", file=sys.stderr)
        return None
    return password


async def _clean_derived(dry_run: bool, allow_empty: bool) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            orphans = await media_service.remove_orphans(
                session, settings.derived_path, dry_run=dry_run, allow_empty=allow_empty
            )
    finally:
        await engine.dispose()

    if not orphans:
        print("Nothing to clean: every folder under the derived path belongs to a medium.")
        return 0

    for media_id in orphans:
        print(f"{'would remove' if dry_run else 'removed'} {media_id}")
    print(f"{len(orphans)} folder(s) {'would be removed' if dry_run else 'removed'}.")
    return 0


async def _regroup_faces() -> int:
    """Groups made under an older rule are not repaired by themselves; this builds them again."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            grouped = await people.regroup(session)
    finally:
        await engine.dispose()

    print(f"{grouped} face(s) are in a group now.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="muninn", description="Muninn maintenance commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin = subparsers.add_parser("create-admin", help="create the first admin account")
    create_admin.add_argument("--username", required=True, help="what the admin logs in with")
    create_admin.add_argument("--name", required=True, help="display name")
    create_admin.add_argument("--email", help="optional, kept as an attribute")
    create_admin.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin instead of asking for it",
    )

    clean_derived = subparsers.add_parser(
        "clean-derived", help="remove previews that belong to no medium any more"
    )
    clean_derived.add_argument(
        "--dry-run", action="store_true", help="only say what would be removed"
    )
    clean_derived.add_argument(
        "--even-when-empty",
        action="store_true",
        help="sweep although no media are known at all, which is normally refused",
    )

    subparsers.add_parser(
        "regroup-faces",
        help="build the groups of unnamed faces again, under the rule as it stands now",
    )

    args = parser.parse_args(argv)

    if args.command == "create-admin":
        password = _read_password(args.password_stdin)
        if password is None:
            return 1
        return asyncio.run(_create_admin(args.username, args.name, args.email, password))

    if args.command == "clean-derived":
        return asyncio.run(_clean_derived(args.dry_run, args.even_when_empty))

    if args.command == "regroup-faces":
        return asyncio.run(_regroup_faces())

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
