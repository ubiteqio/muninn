"""The foundation migration, run against Muninn's own PostgreSQL image.

These tests drop and recreate the whole schema, so they work on a database of their own: pooled
connections cache the OIDs of the enum types, and a recreated type would break every other test.
"""

import os
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

REQUIRED_EXTENSIONS = {"citext", "ltree", "pg_trgm", "postgis", "vector"}
EXPECTED_TABLES = {
    "users",
    "refresh_tokens",
    "settings",
    "publications",
    "albums",
    "media",
    "media_files",
    "pending_files",
    "change_log",
    "ai_profiles",
    "image_embeddings",
    "caption_embeddings",
    "media_analyses",
    "video_frames",
    "media_transcripts",
    "likes",
    "favorites",
    "comments",
    "comment_mentions",
    "notifications",
    "notification_settings",
    "places",
    "duplicate_groups",
    "duplicate_members",
    "memories",
    "memory_media",
    "persons",
    "faces",
    "face_rejections",
}

MIGRATION_DATABASE = "muninn_migrations"


@pytest.fixture(scope="module")
def migration_database_url(sync_database_url: str) -> Iterator[str]:
    """A second, empty database in the same container."""
    admin_engine = sa.create_engine(sync_database_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(sa.text(f"DROP DATABASE IF EXISTS {MIGRATION_DATABASE}"))
        connection.execute(sa.text(f"CREATE DATABASE {MIGRATION_DATABASE}"))

    url = sa.engine.make_url(sync_database_url).set(database=MIGRATION_DATABASE)
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(sa.text(f"DROP DATABASE IF EXISTS {MIGRATION_DATABASE}"))
        admin_engine.dispose()


@pytest.fixture(scope="module")
def alembic_config(migration_database_url: str, database_url: str) -> Iterator[Config]:
    from muninn.core.config import get_settings

    os.environ["MUNINN_DATABASE_URL"] = migration_database_url.replace("+psycopg", "+asyncpg")
    get_settings.cache_clear()
    try:
        yield Config("alembic.ini")
    finally:
        # Hand the shared database back to the other tests.
        os.environ["MUNINN_DATABASE_URL"] = database_url
        get_settings.cache_clear()


def test_upgrade_creates_extensions_and_tables(
    alembic_config: Config, migration_database_url: str
) -> None:
    command.upgrade(alembic_config, "head")

    engine = sa.create_engine(migration_database_url)
    with engine.connect() as connection:
        extensions = {
            row[0] for row in connection.execute(sa.text("SELECT extname FROM pg_extension"))
        }
        tables = set(sa.inspect(engine).get_table_names())
        version = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()

    assert extensions >= REQUIRED_EXTENSIONS
    assert tables >= EXPECTED_TABLES
    assert version == "0034"


def test_username_is_case_insensitive_and_unique(
    alembic_config: Config, migration_database_url: str
) -> None:
    command.upgrade(alembic_config, "head")

    engine = sa.create_engine(migration_database_url)
    insert = sa.text(
        "INSERT INTO users (id, username, display_name, password_hash, role, status,"
        " must_change_password) VALUES (gen_random_uuid(), :username, 'Test', 'hash', 'user',"
        " 'active', true)"
    )
    with engine.begin() as connection:
        connection.execute(insert, {"username": "Anna"})

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(insert, {"username": "anna"})

    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM users"))
    engine.dispose()


def test_downgrade_removes_the_tables(alembic_config: Config, migration_database_url: str) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    engine = sa.create_engine(migration_database_url)
    tables = set(sa.inspect(engine).get_table_names())
    engine.dispose()

    assert not EXPECTED_TABLES & tables


def test_existing_accounts_keep_working_with_a_derived_username(
    alembic_config: Config, migration_database_url: str
) -> None:
    """Upgrading an installation that predates usernames must not lock anybody out."""
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "0001")

    engine = sa.create_engine(migration_database_url)
    insert = sa.text(
        "INSERT INTO users (id, email, display_name, password_hash, role, status,"
        " must_change_password, created_at) VALUES (gen_random_uuid(), :email, :name, 'hash',"
        " 'user', 'active', false, :created)"
    )
    with engine.begin() as connection:
        connection.execute(
            insert, {"email": "anna@example.org", "name": "Anna", "created": "2026-01-01"}
        )
        # Same local part, different domain: the derived names would collide.
        connection.execute(
            insert, {"email": "anna@anderswo.de", "name": "Anna B", "created": "2026-01-02"}
        )

    command.upgrade(alembic_config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            sa.text("SELECT email, username FROM users ORDER BY created_at")
        ).all()
    engine.dispose()

    assert [row.username for row in rows] == ["anna", "anna2"]
    assert [row.email for row in rows] == ["anna@example.org", "anna@anderswo.de"]


def test_the_settings_row_is_created_once_and_stays_alone(
    alembic_config: Config, migration_database_url: str
) -> None:
    """Huginn reads sizes from this row, so an installation has to come up with exactly one."""
    command.upgrade(alembic_config, "head")

    engine = sa.create_engine(migration_database_url)
    with engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT id, thumbnail_size, preview_size, ignored_names FROM settings")
        ).one()

    assert row.id == 1
    assert (row.thumbnail_size, row.preview_size) == (400, 2048)
    assert "@eaDir" in row.ignored_names

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO settings (id, thumbnail_size, preview_size, image_quality,"
                " video_height, ignored_names) VALUES (2, 400, 2048, 82, 720, ARRAY[]::text[])"
            )
        )
    engine.dispose()
