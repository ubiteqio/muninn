"""Personen: naming groups of faces, answering suggestions, looking after persons (/people),
and the faces of one medium (/media/{id}/faces, /faces/{id})."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.albums.service import cursor_value
from muninn.api.schemas.media import MediaView
from muninn.api.schemas.pagination import Page, decode_cursor, encode_cursor
from muninn.api.schemas.people import (
    AlikeFace,
    AlikeFaces,
    ConfirmManyRequest,
    DecidedMany,
    DecideManyRequest,
    FacePage,
    FaceView,
    ForgottenFaces,
    GroupPage,
    GroupView,
    MediaFaceView,
    MergeRequest,
    NameRequest,
    PeopleOverview,
    PersonBrief,
    PersonCard,
    PersonUpdate,
    SuggestionPage,
    SuggestionView,
)
from muninn.api.schemas.search import decode_offset, encode_offset
from muninn.core.config import Settings
from muninn.core.deps import (
    ActiveUser,
    AdminUser,
    OptionalUser,
    get_session,
    get_settings_from_state,
)
from muninn.core.problem import ProblemError, problem_type
from muninn.core.signing import verify_media
from muninn.faces import listing, people
from muninn.faces import service as faces_service
from muninn.faces.service import crop_name
from muninn.huginn.dispatch import queue_face_reassessment, queue_face_sorting
from muninn.media.service import relative_of
from muninn.models.face import Face, Person

router = APIRouter(tags=["people"])
admin_router = APIRouter(prefix="/admin/faces", tags=["admin: faces"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]

GROUPS_PAGE = 24


def _problem(code: int, slug: str, title: str, detail: str | None = None) -> ProblemError:
    return ProblemError(status=code, type=problem_type(slug), title=title, detail=detail)


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return decode_offset(cursor)
    except ValueError as error:
        raise _problem(400, "invalid-cursor", "Invalid cursor") from error


def _person_view(summary: listing.PersonSummary, secret: str) -> PersonCard:
    return PersonCard(
        id=summary.person.id,
        name=summary.person.name,
        hidden=summary.person.hidden,
        faces=summary.faces,
        media=summary.media,
        cover=FaceView.of(summary.cover.face, secret=secret) if summary.cover else None,
    )


def _group_page(found: list[listing.Group], more: bool, offset: int, secret: str) -> GroupPage:
    return GroupPage(
        items=[
            GroupView(
                cluster=group.cluster,
                size=group.size,
                faces=[FaceView.of(shown.face, secret=secret) for shown in group.faces],
            )
            for group in found
        ],
        next_cursor=encode_offset(offset + len(found)) if more else None,
    )


async def _person(session: AsyncSession, person_id: uuid.UUID) -> Person:
    person = await session.get(Person, person_id)
    if person is None:
        raise _problem(404, "person-not-found", "Person not found")
    return person


@router.get("/people", summary="Persons, unnamed groups and how many suggestions wait")
async def read_people(
    user: ActiveUser, session: SessionDep, settings: SettingsDep, hidden: bool = False
) -> PeopleOverview:
    if not await faces_service.enabled(session):
        return PeopleOverview(enabled=False, persons=[], groups=GroupPage(items=[]), suggestions=0)
    found, more = await listing.groups(session, offset=0, limit=GROUPS_PAGE)
    return PeopleOverview(
        persons=[
            _person_view(summary, settings.jwt_secret)
            for summary in await listing.persons(session, hidden=hidden)
        ],
        groups=_group_page(found, more, 0, settings.jwt_secret),
        suggestions=(await people.counts(session)).suggestions,
    )


@router.get("/people/groups", summary="Unnamed groups, the largest first")
async def read_groups(
    user: ActiveUser, session: SessionDep, settings: SettingsDep, cursor: str | None = None
) -> GroupPage:
    offset = _offset(cursor)
    found, more = await listing.groups(session, offset=offset, limit=GROUPS_PAGE)
    return _group_page(found, more, offset, settings.jwt_secret)


@router.get("/people/groups/{cluster}", summary="Every face of an unnamed group")
async def read_group(
    cluster: int, user: ActiveUser, session: SessionDep, settings: SettingsDep
) -> list[FaceView]:
    return [
        FaceView.of(shown.face, secret=settings.jwt_secret)
        for shown in await listing.group_faces(session, cluster)
    ]


@router.post("/people/groups/{cluster}/name", summary="Say who an unnamed group is")
async def name_group(
    cluster: int, payload: NameRequest, user: ActiveUser, session: SessionDep
) -> PersonBrief:
    """A name already given joins the group to that person."""
    try:
        person = await people.name_group(session, cluster, payload.name, user)
    except people.PersonError as error:
        raise _problem(422, "cannot-name", "Cannot name this group", str(error)) from error
    await queue_face_reassessment()
    return PersonBrief.of(person)


@router.get("/people/suggestions", summary="Is this Lena? - surest first")
async def read_suggestions(
    user: ActiveUser, session: SessionDep, settings: SettingsDep, cursor: str | None = None
) -> SuggestionPage:
    offset = _offset(cursor)
    found, more = await listing.suggestions(session, offset=offset, limit=GROUPS_PAGE)
    return SuggestionPage(
        items=[
            SuggestionView(
                face=FaceView.of(item.shown.face, secret=settings.jwt_secret),
                person=PersonBrief.of(item.person),
            )
            for item in found
        ],
        next_cursor=encode_offset(offset + len(found)) if more else None,
    )


@router.get("/people/{person_id}", summary="One person")
async def read_person(
    person_id: uuid.UUID, user: ActiveUser, session: SessionDep, settings: SettingsDep
) -> PersonCard:
    person = await _person(session, person_id)
    summary = next(
        (
            item
            for item in await listing.persons(session, hidden=person.hidden)
            if item.person.id == person.id
        ),
        listing.PersonSummary(person=person, faces=0, media=0, cover=None),
    )
    return _person_view(summary, settings.jwt_secret)


@router.patch("/people/{person_id}", summary="Rename a person, or hide or show them")
async def update_person(
    person_id: uuid.UUID,
    payload: PersonUpdate,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
) -> PersonCard:
    person = await _person(session, person_id)
    try:
        if payload.name is not None:
            await people.rename(session, person, payload.name)
        if payload.hidden is not None:
            await people.hide(session, person, payload.hidden)
    except people.PersonError as error:
        raise _problem(409, "name-taken", "Name taken", str(error)) from error
    return await read_person(person_id, user, session, settings)


@router.post("/people/{person_id}/merge", summary="Make two persons one")
async def merge_person(
    person_id: uuid.UUID,
    payload: MergeRequest,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
) -> PersonCard:
    """Every face of this person goes to the other, and this one is gone."""
    source = await _person(session, person_id)
    target = await _person(session, payload.into)
    await people.merge(session, source, target)
    await queue_face_reassessment()
    return await read_person(target.id, user, session, settings)


@router.get("/people/{person_id}/faces", summary="A person's faces, newest photo first")
async def read_person_faces(
    person_id: uuid.UUID,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    only: Annotated[
        listing.FaceFilter | None,
        Query(description="auto: given by Muninn; twice: the person twice in one photo"),
    ] = None,
) -> FacePage:
    await _person(session, person_id)
    offset = _offset(cursor)
    found, more = await listing.faces_of(session, person_id, offset=offset, limit=limit, only=only)
    return FacePage(
        items=[FaceView.of(shown.face, secret=settings.jwt_secret) for shown in found],
        next_cursor=encode_offset(offset + len(found)) if more else None,
    )


@router.get("/people/{person_id}/media", summary="The photos and videos a person is in")
async def read_person_media(
    person_id: uuid.UUID,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> Page[MediaView]:
    await _person(session, person_id)
    try:
        position = decode_cursor(cursor) if cursor else None
    except ValueError as error:
        raise _problem(400, "invalid-cursor", "Invalid cursor") from error
    found, more = await listing.media_of(session, person_id, cursor=position, limit=limit)
    return Page[MediaView](
        items=[
            MediaView.of(item, library_path=str(settings.library_path), secret=settings.jwt_secret)
            for item in found
        ],
        next_cursor=encode_cursor(cursor_value(found[-1]), found[-1].id)
        if more and found
        else None,
    )


async def _face(session: AsyncSession, face_id: uuid.UUID) -> Face:
    face = await session.get(Face, face_id)
    if face is None:
        raise _problem(404, "face-not-found", "Face not found")
    return face


@router.post(
    "/faces/alike",
    summary="Answer several open questions about one person the same way",
)
async def decide_alike_faces(
    payload: DecideManyRequest, user: ActiveUser, session: SessionDep
) -> DecidedMany:
    """Yes or no for a whole list at once, as the modal after a decision offers it.

    Faces that are no longer an open question about this person are skipped: the list somebody
    answered may have moved on between seeing it and sending it back.
    """
    person = await _person(session, payload.person_id)
    answered = await people.decide_many(session, payload.face_ids, person, confirm=payload.confirm)
    if payload.confirm and answered:
        await queue_face_reassessment()
    return DecidedMany(answered=answered)


@router.post("/faces/confirm", summary="Stand by what Muninn decided for several faces")
async def confirm_many_faces(
    payload: ConfirmManyRequest, user: ActiveUser, session: SessionDep, settings: SettingsDep
) -> DecidedMany:
    """A page of the faces Muninn assigned itself, confirmed in one go.

    What Muninn decided by itself vouches for nobody - one wrong guess would otherwise teach
    the rest - so a person may have thousands of faces and still be recognised poorly. Going
    through them a page at a time, taking the wrong ones out with the cross and standing by
    the rest, is worth more than answering a hundred questions.

    Only the faces Muninn gave, and each keeps its own person. Anything else is skipped.
    """
    media_ids = {
        face.media_id
        for face in [await session.get(Face, face_id) for face_id in payload.face_ids]
        if face is not None
    }
    confirmed = await people.confirm_many(session, payload.face_ids)
    if confirmed:
        for media_id in media_ids:
            await _one_face_each(session, settings, media_id)
        await queue_face_reassessment()
    return DecidedMany(answered=confirmed)


@router.post(
    "/faces/{face_id}/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Yes: the suggestion, or the person Muninn gave, is right",
)
async def confirm_face(
    face_id: uuid.UUID, user: ActiveUser, session: SessionDep, settings: SettingsDep
) -> Response:
    face = await _face(session, face_id)
    # A suggestion answered with yes, or a person Muninn gave confirmed: either way the face
    # now vouches for its person when new faces are sorted.
    person_id = face.suggested_person_id or (face.person_id if face.assigned_by == "auto" else None)
    if person_id is None:
        raise _problem(409, "no-suggestion", "Nothing suggested for this face")
    await people.assign(session, face_id, await _person(session, person_id))
    await _one_face_each(session, settings, face.media_id)
    await queue_face_reassessment()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/faces/{face_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="No, not this person",
)
async def reject_face(face_id: uuid.UUID, user: ActiveUser, session: SessionDep) -> Response:
    """The suggestion goes - or, for a face that has a person, the face leaves them."""
    await _face(session, face_id)
    await people.reject(session, face_id)
    queue_face_sorting(face_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/faces/{face_id}/alike",
    summary="Open questions about the same person that look like this face",
)
async def read_alike_faces(
    face_id: uuid.UUID,
    person: uuid.UUID,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
) -> AlikeFaces:
    """Asked right after a yes or a no, to offer the same answer for what looks the same.

    Everything within the widest distance Muninn would ever offer comes back, each with how
    alike it is, so the app can let somebody draw the line themselves without asking again.
    """
    await _face(session, face_id)
    found = await people.alike_suggestions(session, face_id, person)
    return AlikeFaces(
        person_id=person,
        items=[
            AlikeFace(face=FaceView.of(face, secret=settings.jwt_secret), similarity=similarity)
            for face, similarity in found
        ],
    )


async def _one_face_each(session: SessionDep, settings: Settings, media_id: uuid.UUID) -> None:
    """The medium has this person for certain now, so the other looks at them are answered.

    A second sighting of somebody already named adds nothing to the medium, and a question
    about somebody who is on it for certain has its answer. Both go, with their squares - this
    is how one child came to be confirmed five times on one photograph.
    """
    await faces_service.collapse_media_faces(session, media_id, settings.derived_path)


@router.post("/faces/{face_id}/name", summary="Say who this face is")
async def name_face(
    face_id: uuid.UUID,
    payload: NameRequest,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
) -> PersonBrief:
    face = await _face(session, face_id)
    try:
        person = await people.person_named(session, payload.name, user)
    except people.PersonError as error:
        raise _problem(422, "cannot-name", "Cannot name this face", str(error)) from error
    await people.assign(session, face_id, person)
    await _one_face_each(session, settings, face.media_id)
    await queue_face_reassessment()
    return PersonBrief.of(person)


@router.get("/media/{media_id}/faces", summary="The faces in a medium, and who they are")
async def read_media_faces(
    media_id: uuid.UUID, user: ActiveUser, session: SessionDep, settings: SettingsDep
) -> list[MediaFaceView]:
    if not await faces_service.enabled(session):
        return []
    found = await listing.faces_in(session, media_id)
    suggested_ids = {face.suggested_person_id for face, _ in found if face.suggested_person_id}
    suggested = {
        person.id: person
        for person in [await session.get(Person, person_id) for person_id in suggested_ids]
        if person is not None
    }
    return [
        MediaFaceView(
            face=FaceView.of(face, secret=settings.jwt_secret),
            person=PersonBrief.of(person) if person and not person.hidden else None,
            suggested=(
                PersonBrief.of(suggested[face.suggested_person_id])
                if face.suggested_person_id in suggested and person is None
                else None
            ),
        )
        for face, person in found
        # A hidden person is somebody nobody wants to see named: their face is left out.
        if person is None or not person.hidden
    ]


@router.get("/faces/{face_id}/crop", summary="The square picture of a face")
async def read_face_crop(
    face_id: uuid.UUID,
    user: OptionalUser,
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str | None, Query()] = None,
) -> FileResponse:
    signed = token is not None and verify_media(token, face_id, "face", secret=settings.jwt_secret)
    if not signed and user is None:
        raise _problem(401, "not-authenticated", "Not authenticated")
    face = await _face(session, face_id)
    path = settings.derived_path / relative_of(face.media_id, crop_name(face.id))
    # As with every picture: the connection goes back before the file is sent.
    await session.close()
    if not path.exists():
        raise _problem(404, "crop-not-ready", "Not ready")
    return FileResponse(
        path, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"}
    )


@admin_router.delete("", summary="Delete every face and every person")
async def forget_faces(
    admin: AdminUser, session: SessionDep, settings: SettingsDep
) -> ForgottenFaces:
    """Biometric data, all of it: faces, their vectors and pictures, and the persons named.

    Switched on again, faces are looked for anew; the names are not coming back.
    """
    faces, persons = await faces_service.forget_all(session, settings.derived_path)
    return ForgottenFaces(faces=faces, persons=persons)
