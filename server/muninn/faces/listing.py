"""What the Personen screen shows: persons, groups of unnamed faces, suggestions, and the photos
of one person. Faces of media that are gone from the NAS or hidden as copies are left out."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from muninn.albums.service import SORT_KEY
from muninn.models.face import Face, Person
from muninn.models.media import Media, shown

#: How many faces a group shows of itself.
GROUP_FACES = 6


def _visible_faces() -> Select[tuple[Face, Media]]:
    return select(Face, Media).join(Media, Media.id == Face.media_id).where(shown())


@dataclass(frozen=True, slots=True)
class FaceShown:
    face: Face
    media: Media


@dataclass(frozen=True, slots=True)
class PersonSummary:
    person: Person
    faces: int
    media: int
    cover: FaceShown | None


async def _clearest(session: AsyncSession, condition: object) -> dict[object, FaceShown]:
    """Per person or group, its clearest face: the largest and surest."""
    rows = await session.execute(
        _visible_faces()
        .where(condition)  # type: ignore[arg-type]
        .order_by((Face.pixels * Face.score).desc())
        .options(selectinload(Media.files))
    )
    best: dict[object, FaceShown] = {}
    for face, media in rows.tuples():
        key = face.person_id if face.person_id is not None else face.cluster
        best.setdefault(key, FaceShown(face=face, media=media))
    return best


async def persons(session: AsyncSession, *, hidden: bool = False) -> list[PersonSummary]:
    """Everybody named, the one with the most photos first."""
    counts = await session.execute(
        select(
            Person,
            func.count(Face.id),
            func.count(func.distinct(Face.media_id)),
        )
        .outerjoin(
            Face,
            and_(
                Face.person_id == Person.id,
                Face.media_id.in_(select(Media.id).where(shown())),
            ),
        )
        .where(Person.hidden.is_(hidden))
        .group_by(Person.id)
        .order_by(func.count(func.distinct(Face.media_id)).desc(), Person.name)
    )
    rows = counts.tuples().all()
    covers = await _clearest(session, Face.person_id.in_([row[0].id for row in rows]))
    return [
        PersonSummary(person=person, faces=faces, media=media, cover=covers.get(person.id))
        for person, faces, media in rows
    ]


@dataclass(frozen=True, slots=True)
class Group:
    cluster: int
    size: int
    faces: list[FaceShown]


async def groups(session: AsyncSession, *, offset: int, limit: int) -> tuple[list[Group], bool]:
    """Unnamed groups of at least two faces, the largest first."""
    size = func.count(Face.id)
    rows = (
        (
            await session.execute(
                select(Face.cluster, size)
                .join(Media, Media.id == Face.media_id)
                .where(shown(), Face.person_id.is_(None), Face.cluster.is_not(None))
                .group_by(Face.cluster)
                .having(size >= 2)
                .order_by(size.desc(), Face.cluster)
                .offset(offset)
                .limit(limit + 1)
            )
        )
        .tuples()
        .all()
    )
    page = rows[:limit]
    clusters = [cluster for cluster, _ in page if cluster is not None]
    faces = await session.execute(
        _visible_faces()
        .where(Face.cluster.in_(clusters), Face.person_id.is_(None))
        .order_by(Face.cluster, (Face.pixels * Face.score).desc())
        .options(selectinload(Media.files))
    )
    by_cluster: dict[int, list[FaceShown]] = {}
    for face, media in faces.tuples():
        if face.cluster is None:
            continue
        shown_faces = by_cluster.setdefault(face.cluster, [])
        if len(shown_faces) < GROUP_FACES:
            shown_faces.append(FaceShown(face=face, media=media))
    return (
        [
            Group(cluster=cluster, size=count, faces=by_cluster.get(cluster, []))
            for cluster, count in page
            if cluster is not None
        ],
        len(rows) > limit,
    )


async def group_faces(session: AsyncSession, cluster: int) -> list[FaceShown]:
    rows = await session.execute(
        _visible_faces()
        .where(Face.cluster == cluster, Face.person_id.is_(None))
        .order_by((Face.pixels * Face.score).desc())
        .options(selectinload(Media.files))
    )
    return [FaceShown(face=face, media=media) for face, media in rows.tuples()]


@dataclass(frozen=True, slots=True)
class Suggestion:
    shown: FaceShown
    person: Person


async def suggestions(
    session: AsyncSession, *, offset: int, limit: int
) -> tuple[list[Suggestion], bool]:
    """ "Ist das Lena?" - the surest first: the face nearest to the person it is suggested for.

    A face without a distance - suggested before the distance was kept - comes last; among equals
    the newest face goes first.
    """
    rows = (
        (
            await session.execute(
                select(Face, Media, Person)
                .join(Media, Media.id == Face.media_id)
                .join(Person, Person.id == Face.suggested_person_id)
                .where(shown(), Face.person_id.is_(None), Person.hidden.is_(False))
                .order_by(
                    Face.suggested_distance.asc().nulls_last(), Face.created_at.desc(), Face.id
                )
                .offset(offset)
                .limit(limit + 1)
                .options(selectinload(Media.files))
            )
        )
        .tuples()
        .all()
    )
    return (
        [
            Suggestion(shown=FaceShown(face=face, media=media), person=person)
            for face, media, person in rows[:limit]
        ],
        len(rows) > limit,
    )


class FaceFilter(StrEnum):
    """Which of a person's faces to look through when checking them."""

    #: Given by Muninn, not confirmed by anybody.
    AUTO = "auto"
    #: In a photo where the person has another face as well: one of them is somebody else.
    TWICE = "twice"


async def faces_of(
    session: AsyncSession,
    person_id: uuid.UUID,
    *,
    offset: int,
    limit: int,
    only: FaceFilter | None = None,
) -> tuple[list[FaceShown], bool]:
    """A person's faces, newest photo first: to look through, and to take wrong ones out."""
    query = _visible_faces().where(Face.person_id == person_id)
    if only is FaceFilter.AUTO:
        query = query.where(Face.assigned_by == "auto")
    elif only is FaceFilter.TWICE:
        other = aliased(Face)
        query = query.where(
            Face.second.is_(None),
            select(other.id)
            .where(
                other.media_id == Face.media_id,
                other.person_id == person_id,
                other.id != Face.id,
            )
            .exists(),
        )
    rows = (
        (
            await session.execute(
                query.order_by(SORT_KEY.desc(), Media.id, Face.id)
                .offset(offset)
                .limit(limit + 1)
                .options(selectinload(Media.files))
            )
        )
        .tuples()
        .all()
    )
    return [FaceShown(face=face, media=media) for face, media in rows[:limit]], len(rows) > limit


async def media_of(
    session: AsyncSession,
    person_id: uuid.UUID,
    *,
    cursor: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> tuple[list[Media], bool]:
    """The photos a person is in, newest first."""
    query = (
        select(Media)
        .where(shown(), Media.id.in_(select(Face.media_id).where(Face.person_id == person_id)))
        .options(selectinload(Media.files))
    )
    if cursor is not None:
        taken_at, media_id = cursor
        order = SORT_KEY
        query = query.where((order < taken_at) | ((order == taken_at) & (Media.id < media_id)))
    rows = list(
        await session.scalars(query.order_by(SORT_KEY.desc(), Media.id.desc()).limit(limit + 1))
    )
    return rows[:limit], len(rows) > limit


async def faces_in(session: AsyncSession, media_id: uuid.UUID) -> list[tuple[Face, Person | None]]:
    """The faces of one medium with their persons, left to right."""
    rows = await session.execute(
        select(Face, Person)
        .outerjoin(Person, Person.id == Face.person_id)
        .where(Face.media_id == media_id)
        .order_by(Face.second.nulls_first(), Face.box_left)
    )
    return list(rows.tuples())
