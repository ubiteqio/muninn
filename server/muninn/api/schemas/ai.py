"""Contract for the AI profiles: which machine answers for which interface."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field

from muninn.models.ai import DEFAULT_CONCURRENCY, DEFAULT_TIMEOUT_SECONDS, AiKind, AiProfile


class AiProfileView(BaseModel):
    """A profile as the admin area shows it. The key itself never leaves the server."""

    id: uuid.UUID
    kind: AiKind
    name: str
    base_url: str
    model: str
    concurrency: int
    timeout_seconds: int
    #: True when this is the profile in use for its interface.
    is_active: bool
    #: Whether a key is stored. What it is stays here.
    has_api_key: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, profile: AiProfile) -> Self:
        return cls(
            id=profile.id,
            kind=profile.kind,
            name=profile.name,
            base_url=profile.base_url,
            model=profile.model,
            concurrency=profile.concurrency,
            timeout_seconds=profile.timeout_seconds,
            is_active=profile.is_active is True,
            has_api_key=bool(profile.api_key),
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )


class AiProfileCreate(BaseModel):
    kind: AiKind
    name: Annotated[str, Field(min_length=1, max_length=120)]
    #: Up to and including /v1, e.g. http://gpu.zuhause:8000/v1
    base_url: Annotated[str, Field(min_length=1, max_length=500)]
    model: Annotated[str, Field(min_length=1, max_length=200)]
    api_key: Annotated[str, Field(max_length=500)] = ""
    concurrency: Annotated[int, Field(ge=1, le=32)] = DEFAULT_CONCURRENCY
    timeout_seconds: Annotated[int, Field(ge=5, le=1800)] = DEFAULT_TIMEOUT_SECONDS


class AiProfileUpdate(BaseModel):
    """Everything optional: what is not sent stays as it is, the key above all."""

    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    base_url: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    model: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    api_key: Annotated[str | None, Field(max_length=500)] = None
    concurrency: Annotated[int | None, Field(ge=1, le=32)] = None
    timeout_seconds: Annotated[int | None, Field(ge=5, le=1800)] = None


class AiCheckView(BaseModel):
    """What came of asking the machine whether it is there."""

    ok: bool
    detail: str
    milliseconds: int
    dimensions: int | None = None
