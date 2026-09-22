"""The profiles: which machine answers for which interface, and whether it is there.

Only this module touches the profile table. Everything else asks it for the profile that is in
use and gets a client back, never an address.
"""

import uuid
from collections.abc import Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai.base import Analyzer, Check, Embedder
from muninn.ai.openai_compatible import (
    OpenAiAnalyzer,
    OpenAiEmbedder,
    OpenAiFaceDetector,
    OpenAiTranscriber,
    probe_chat_model,
)
from muninn.models.ai import (
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT_SECONDS,
    AiKind,
    AiProfile,
)


class ProfileNotFoundError(Exception):
    pass


async def list_profiles(session: AsyncSession) -> list[AiProfile]:
    """All profiles, the one in use first, then by name."""
    rows = await session.scalars(
        select(AiProfile).order_by(AiProfile.kind, AiProfile.is_active.desc(), AiProfile.name)
    )
    return list(rows)


async def get_profile(session: AsyncSession, profile_id: uuid.UUID) -> AiProfile:
    profile = await session.get(AiProfile, profile_id)
    if profile is None:
        raise ProfileNotFoundError
    return profile


async def active_profile(session: AsyncSession, kind: AiKind) -> AiProfile | None:
    """The profile in use for this interface, or nothing when none was set up yet."""
    found: AiProfile | None = await session.scalar(
        select(AiProfile).where(AiProfile.kind == kind, AiProfile.is_active.is_(True))
    )
    return found


async def create_profile(
    session: AsyncSession,
    *,
    kind: AiKind,
    name: str,
    base_url: str,
    model: str,
    api_key: str = "",
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> AiProfile:
    """Add a profile. The first one of its kind is the one in use; later ones are spares."""
    profile = AiProfile(
        kind=kind,
        name=name,
        base_url=base_url,
        model=model,
        api_key=api_key,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
        is_active=True if await active_profile(session, kind) is None else None,
    )

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def update_profile(session: AsyncSession, profile: AiProfile, **changes: object) -> AiProfile:
    """Change a profile. A key that was not sent stays as it is; nobody retypes a secret."""
    for field, value in changes.items():
        if value is not None:
            setattr(profile, field, value)

    await session.commit()
    await session.refresh(profile)
    return profile


async def activate(session: AsyncSession, profile: AiProfile) -> AiProfile:
    """Put this profile in use and make the others of its kind spares."""
    others = await session.scalars(
        select(AiProfile).where(AiProfile.kind == profile.kind, AiProfile.id != profile.id)
    )
    for other in others:
        other.is_active = None
    # First the others step aside, then this one steps in. Both in one transaction, but not in
    # one statement: the database allows one machine in use per interface and checks that per
    # statement, so writing them the other way round collides with itself.
    await session.flush()

    profile.is_active = True
    await session.commit()
    await session.refresh(profile)
    return profile


async def delete_profile(session: AsyncSession, profile: AiProfile) -> None:
    """Remove a profile. Taking away the one in use leaves that interface without a machine."""
    await session.delete(profile)
    await session.commit()


def embedder_for(
    profile: AiProfile,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: int | None = None,
) -> Embedder:
    """The client for an embedding profile. Nothing outside gets to see the address.

    ``timeout_seconds`` overrides the profile's for a caller that cannot wait as long as the
    pipeline can - somebody in front of a search field.
    """
    return OpenAiEmbedder(
        base_url=profile.base_url,
        model=profile.model,
        api_key=profile.api_key,
        timeout_seconds=timeout_seconds or profile.timeout_seconds,
        client=client,
    )


def analyzer_for(profile: AiProfile, *, client: httpx.AsyncClient | None = None) -> Analyzer:
    """The client for a describing profile."""
    return OpenAiAnalyzer(
        base_url=profile.base_url,
        model=profile.model,
        api_key=profile.api_key,
        timeout_seconds=profile.timeout_seconds,
        client=client,
    )


def transcriber_for(
    profile: AiProfile,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: int | None = None,
) -> OpenAiTranscriber:
    """The client for a speech profile."""
    return OpenAiTranscriber(
        base_url=profile.base_url,
        model=profile.model,
        api_key=profile.api_key,
        timeout_seconds=timeout_seconds or profile.timeout_seconds,
        client=client,
    )


def face_detector_for(
    profile: AiProfile,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: int | None = None,
) -> OpenAiFaceDetector:
    """The client for a face profile."""
    return OpenAiFaceDetector(
        base_url=profile.base_url,
        model=profile.model,
        api_key=profile.api_key,
        timeout_seconds=timeout_seconds or profile.timeout_seconds,
        client=client,
    )


async def check_profile(
    profile: AiProfile,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: int | None = None,
) -> Check:
    """Ask the machine one small question, the way this interface would ask it.

    ``timeout_seconds`` overrides the profile's for a caller that only wants to know whether
    the machine is there, not wait for it the way the pipeline does.
    """
    if profile.kind is AiKind.ANALYZER:
        return await probe_chat_model(
            base_url=profile.base_url,
            model=profile.model,
            api_key=profile.api_key,
            timeout_seconds=timeout_seconds or profile.timeout_seconds,
            client=client,
        )

    if profile.kind is AiKind.TRANSCRIBER:
        return await transcriber_for(
            profile, client=client, timeout_seconds=timeout_seconds
        ).check()

    if profile.kind is AiKind.FACE_DETECTOR:
        return await face_detector_for(
            profile, client=client, timeout_seconds=timeout_seconds
        ).check()

    return await embedder_for(profile, client=client, timeout_seconds=timeout_seconds).check()


def kinds() -> Sequence[AiKind]:
    return tuple(AiKind)
