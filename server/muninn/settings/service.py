"""Reading and changing the settings an admin may edit at runtime.

Only this module touches the settings table. Huginn reads the sizes from here before deriving a
thumbnail or a preview, and the scanner reads the ignore list before walking a folder.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.models.settings import (
    DEFAULT_DELETION_COUNT,
    DEFAULT_DELETION_SHARE_PERCENT,
    DEFAULT_FULL_SYNC_HOUR,
    DEFAULT_IGNORED_NAMES,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_MISSING_GRACE_DAYS,
    DEFAULT_PREVIEW_SIZE,
    DEFAULT_QUICK_SYNC_SECONDS,
    DEFAULT_STABILITY_SECONDS,
    DEFAULT_THUMBNAIL_SIZE,
    DEFAULT_VIDEO_HEIGHT,
    SETTINGS_ID,
    AppSettings,
)


def _defaults() -> AppSettings:
    return AppSettings(
        id=SETTINGS_ID,
        thumbnail_size=DEFAULT_THUMBNAIL_SIZE,
        preview_size=DEFAULT_PREVIEW_SIZE,
        image_quality=DEFAULT_IMAGE_QUALITY,
        video_height=DEFAULT_VIDEO_HEIGHT,
        ignored_names=list(DEFAULT_IGNORED_NAMES),
        quick_sync_seconds=DEFAULT_QUICK_SYNC_SECONDS,
        full_sync_hour=DEFAULT_FULL_SYNC_HOUR,
        stability_seconds=DEFAULT_STABILITY_SECONDS,
        missing_grace_days=DEFAULT_MISSING_GRACE_DAYS,
        deletion_share_percent=DEFAULT_DELETION_SHARE_PERCENT,
        deletion_count=DEFAULT_DELETION_COUNT,
        nas_agent_enabled=False,
        faces_enabled=True,
    )


async def get_settings(session: AsyncSession) -> AppSettings:
    """The settings row. The migration creates it; a missing row falls back to the defaults.

    Without the fallback a database restored from a partial backup would answer 500 on every
    request that needs a size, which is a worse answer than the value the migration would have
    written anyway.
    """
    settings = await session.get(AppSettings, SETTINGS_ID)
    if settings is not None:
        return settings

    session.add(_defaults())
    try:
        await session.commit()
    except IntegrityError:
        # Another request got there first; its row is the one that counts.
        await session.rollback()
        settings = await session.get(AppSettings, SETTINGS_ID)
        if settings is None:
            raise
        return settings

    return await get_settings(session)


async def update_settings(session: AsyncSession, **changes: object) -> AppSettings:
    """Replace every setting at once; the endpoint is a PUT and sends all of them."""
    settings = await get_settings(session)
    for field, value in changes.items():
        setattr(settings, field, value)
    await session.commit()
    await session.refresh(settings)
    return settings
