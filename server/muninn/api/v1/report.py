"""Überblick: the library at a glance, the same for everybody (/overview)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.report import (
    Content,
    Duplicates,
    People,
    PersonShare,
    Places,
    ReportView,
    Share,
    Social,
    Step,
    Totals,
    TownShare,
    YearCount,
)
from muninn.core.config import Settings
from muninn.core.deps import ActiveUser, get_session, get_settings_from_state
from muninn.core.signing import sign_media
from muninn.report import service

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("", summary="The library at a glance")
async def read_report(
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> ReportView:
    """Counts and shares over everything the albums show - no single media. Everybody sees the
    same, the pipeline and the housekeeping included."""
    report = await service.build(session)

    def crop(face_id: object) -> str | None:
        if face_id is None:
            return None
        token = sign_media(face_id, "face", secret=settings.jwt_secret)  # type: ignore[arg-type]
        return f"/api/v1/faces/{face_id}/crop?token={token}"

    return ReportView(
        totals=Totals.model_validate(report.totals),
        years=[YearCount.model_validate(row) for row in report.years],
        pipeline=[Step.model_validate(row) for row in report.pipeline],
        content=Content.model_validate(report.content),
        tags=[Share(name=row["tag"], count=row["count"]) for row in report.tags],
        scenes=[Share.model_validate(row) for row in report.scenes],
        times_of_day=[Share.model_validate(row) for row in report.times_of_day],
        people=People.model_validate(report.people),
        persons=[
            PersonShare(
                id=row["id"], name=row["name"], media=row["media"], crop=crop(row["cover_id"])
            )
            for row in report.persons
        ],
        places=Places.model_validate(report.places),
        countries=[Share.model_validate(row) for row in report.countries],
        towns=[TownShare.model_validate(row) for row in report.towns],
        date_sources=[Share.model_validate(row) for row in report.date_sources],
        cameras=[Share.model_validate(row) for row in report.cameras],
        duplicates=Duplicates.model_validate(report.duplicates),
        social=Social.model_validate(report.social),
    )
