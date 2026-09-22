"""Contract for the settings an admin may change at runtime."""

from datetime import datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

#: Bounds, not opinions: below these the derivative is useless, above them it costs space without
#: anybody seeing the difference on a screen.
ThumbnailSize = Annotated[int, Field(ge=100, le=1000)]
PreviewSize = Annotated[int, Field(ge=800, le=8000)]
ImageQuality = Annotated[int, Field(ge=50, le=100)]
VideoHeight = Annotated[int, Field(ge=360, le=2160)]

#: How the library is kept in step with the NAS.
QuickSyncSeconds = Annotated[int, Field(ge=60, le=3600)]
FullSyncHour = Annotated[int, Field(ge=0, le=23)]
StabilitySeconds = Annotated[int, Field(ge=5, le=600)]
#: 0 removes a missing medium at once; beyond a year it is not a grace period any more.
MissingGraceDays = Annotated[int, Field(ge=0, le=365)]

#: The safety net can be adjusted, never switched off.
#: 0 switches the pause off.
DeletionSharePercent = Annotated[int, Field(ge=0, le=50)]
DeletionCount = Annotated[int, Field(ge=0, le=100_000)]


def _check_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("An ignored name cannot be empty.")
    if "/" in name or "\\" in name:
        raise ValueError("An ignored name is a single folder or file name, not a path.")
    return name


IgnoredName = Annotated[str, Field(max_length=100), AfterValidator(_check_name)]


class SettingsView(BaseModel):
    """What the admin area shows and what Huginn reads before deriving."""

    model_config = ConfigDict(from_attributes=True)

    thumbnail_size: int
    preview_size: int
    image_quality: int
    video_height: int
    ignored_names: list[str]

    quick_sync_seconds: int
    full_sync_hour: int
    stability_seconds: int
    missing_grace_days: int
    deletion_share_percent: int
    deletion_count: int
    nas_agent_enabled: bool
    faces_enabled: bool

    updated_at: datetime


class SettingsUpdate(BaseModel):
    """Every setting at once: the endpoint replaces the row rather than patching it."""

    thumbnail_size: ThumbnailSize
    preview_size: PreviewSize
    image_quality: ImageQuality
    video_height: VideoHeight
    ignored_names: Annotated[list[IgnoredName], Field(max_length=200)]

    quick_sync_seconds: QuickSyncSeconds
    full_sync_hour: FullSyncHour
    stability_seconds: StabilitySeconds
    missing_grace_days: MissingGraceDays
    deletion_share_percent: DeletionSharePercent
    deletion_count: DeletionCount
    nas_agent_enabled: bool = False
    faces_enabled: bool = True

    @model_validator(mode="after")
    def _preview_is_larger(self) -> Self:
        if self.preview_size <= self.thumbnail_size:
            raise ValueError("The preview has to be larger than the thumbnail.")
        return self

    @model_validator(mode="after")
    def _names_are_unique(self) -> Self:
        seen: set[str] = set()
        unique: list[str] = []
        for name in self.ignored_names:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                unique.append(name)
        self.ignored_names = unique
        return self
