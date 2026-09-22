"""Mímir's storage: vectors are kept per model, and the missing ones can be named."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.media import Media, MediaStatus
from muninn.search import service
from muninn.search.service import VectorError, VectorKind
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")


async def media_with_previews(session: AsyncSession, count: int) -> list[Media]:
    album = await an_album(session, "Fotos")
    media = []
    for index in range(count):
        medium = await a_medium(session, album, taken_at=JULY, name=f"IMG_{index}.jpg")
        medium.thumbnail_path = f"ab/{medium.id.hex}/thumb.webp"
        media.append(medium)
    await session.commit()
    return media


async def test_a_vector_is_kept_and_the_medium_no_longer_missing(session: AsyncSession) -> None:
    first, second = await media_with_previews(session, 2)

    await service.store(
        session, VectorKind.IMAGE, media_id=first.id, model="siglip2", version=1, vector=[0.5] * 8
    )
    await session.commit()

    missing = await service.media_without(session, VectorKind.IMAGE, model="siglip2", version=1)
    assert missing == [second.id]
    assert await service.count_without(session, VectorKind.IMAGE, model="siglip2", version=1) == 1


async def test_storing_it_again_replaces_rather_than_adds(session: AsyncSession) -> None:
    (medium,) = await media_with_previews(session, 1)

    for value in (0.1, 0.9):
        await service.store(
            session,
            VectorKind.IMAGE,
            media_id=medium.id,
            model="siglip2",
            version=1,
            vector=[value] * 8,
        )
        await session.commit()

    rows = await session.execute(text("SELECT count(*) FROM image_embeddings"))
    assert rows.scalar() == 1


async def test_each_model_keeps_its_own_vectors(session: AsyncSession) -> None:
    """A new model fills in beside the old one; the old one stays until it takes over."""
    (medium,) = await media_with_previews(session, 1)

    await service.store(
        session, VectorKind.IMAGE, media_id=medium.id, model="siglip2", version=1, vector=[0.5] * 8
    )
    await session.commit()

    assert await service.media_without(session, VectorKind.IMAGE, model="siglip3", version=1) == [
        medium.id
    ]


async def test_a_newer_stage_asks_for_the_vector_again(session: AsyncSession) -> None:
    (medium,) = await media_with_previews(session, 1)
    await service.store(
        session, VectorKind.IMAGE, media_id=medium.id, model="siglip2", version=1, vector=[0.5] * 8
    )
    await session.commit()

    assert await service.media_without(session, VectorKind.IMAGE, model="siglip2", version=2) == [
        medium.id
    ]


async def test_only_what_can_be_looked_at_is_missing(session: AsyncSession) -> None:
    """No thumbnail yet, or the file is gone: nothing to give the picture model."""
    without_preview, gone = await media_with_previews(session, 2)
    without_preview.thumbnail_path = None
    gone.status = MediaStatus.MISSING
    await session.commit()

    assert await service.media_without(session, VectorKind.IMAGE, model="siglip2", version=1) == []


async def test_the_first_vector_of_a_model_brings_its_index(session: AsyncSession) -> None:
    """Without it every search reads every vector; with it, HNSW by cosine."""
    (medium,) = await media_with_previews(session, 1)

    await service.store(
        session, VectorKind.IMAGE, media_id=medium.id, model="siglip2", version=1, vector=[0.5] * 8
    )
    await session.commit()

    definition = await session.scalar(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
        {"name": service.index_name(VectorKind.IMAGE, "siglip2", 8)},
    )
    assert definition is not None
    assert "hnsw" in definition
    assert "halfvec_cosine_ops" in definition
    assert "'siglip2'" in definition
    assert "dimensions = 8" in definition


async def test_a_model_name_with_a_quote_does_not_break_the_index(session: AsyncSession) -> None:
    """Model names come from the admin area; an index statement takes no parameters."""
    (medium,) = await media_with_previews(session, 1)

    await service.store(
        session, VectorKind.IMAGE, media_id=medium.id, model="o'reilly", version=1, vector=[0.5] * 8
    )
    await session.commit()

    assert await service.media_without(session, VectorKind.IMAGE, model="o'reilly", version=1) == []


async def test_an_empty_vector_is_refused(session: AsyncSession) -> None:
    (medium,) = await media_with_previews(session, 1)

    with pytest.raises(VectorError):
        await service.store(
            session, VectorKind.IMAGE, media_id=medium.id, model="siglip2", version=1, vector=[]
        )


async def test_a_removed_medium_takes_its_vectors_along(session: AsyncSession) -> None:
    (medium,) = await media_with_previews(session, 1)
    await service.store(
        session, VectorKind.CAPTION, media_id=medium.id, model="bge-m3", version=1, vector=[0.5] * 8
    )
    await session.commit()

    await session.delete(medium)
    await session.commit()

    rows = await session.execute(text("SELECT count(*) FROM caption_embeddings"))
    assert rows.scalar() == 0


async def test_the_first_vectors_of_a_model_may_arrive_at_once(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Two workers, one new model: both used to create the index and deadlocked each other."""
    media = await media_with_previews(session, 6)

    async def store_one(medium: Media) -> None:
        async with session_factory() as own:
            await service.store(
                own,
                VectorKind.IMAGE,
                media_id=medium.id,
                model="parallel-model",
                version=1,
                vector=[0.5] * 8,
            )
            # Hold the transaction open a moment, the way a worker does before it commits.
            await asyncio.sleep(0.05)
            await own.commit()

    await asyncio.gather(*(store_one(medium) for medium in media))

    rows = await session.execute(text("SELECT count(*) FROM image_embeddings"))
    assert rows.scalar() == 6


async def test_a_model_that_changes_its_length_keeps_working(session: AsyncSession) -> None:
    """Swapped behind the same name, a model may answer with vectors of another length."""
    first, second = await media_with_previews(session, 2)

    await service.store(
        session, VectorKind.IMAGE, media_id=first.id, model="swapped", version=1, vector=[0.5] * 8
    )
    await session.commit()
    await service.store(
        session, VectorKind.IMAGE, media_id=second.id, model="swapped", version=1, vector=[0.5] * 4
    )
    await session.commit()

    rows = await session.execute(text("SELECT count(*) FROM image_embeddings"))
    assert rows.scalar() == 2
