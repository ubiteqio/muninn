"""The contract of the Personen screen and of the faces in a medium."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from muninn.core.signing import sign_media
from muninn.models.face import Face, Person


class DecideManyRequest(BaseModel):
    """The same yes or no for several open questions about one person."""

    person_id: UUID
    face_ids: list[UUID] = Field(max_length=200)
    #: True for yes, false for no.
    confirm: bool


class DecidedMany(BaseModel):
    answered: int


class BoxView(BaseModel):
    """Fractions of the picture's width and height."""

    left: float
    top: float
    right: float
    bottom: float


class FaceView(BaseModel):
    id: UUID
    media_id: UUID
    box: BoxView
    #: For a video, the second the face was seen at.
    second: float | None
    #: A signed address of the square picture of the face.
    crop: str
    person_id: UUID | None
    #: "user" or "auto"; null without a person.
    assigned_by: str | None
    suggested_person_id: UUID | None
    #: How alike the suggested person's nearest face is, from 0 to 1. From 0.5 on a face is
    #: assigned without asking.
    suggested_similarity: float | None = None

    @classmethod
    def of(cls, face: Face, *, secret: str) -> Self:
        token = sign_media(face.id, "face", secret=secret)
        return cls(
            id=face.id,
            media_id=face.media_id,
            box=BoxView(
                left=face.box_left, top=face.box_top, right=face.box_right, bottom=face.box_bottom
            ),
            second=face.second,
            crop=f"/api/v1/faces/{face.id}/crop?token={token}",
            person_id=face.person_id,
            assigned_by=face.assigned_by,
            suggested_person_id=face.suggested_person_id,
            suggested_similarity=(
                round(1 - face.suggested_distance, 3)
                if face.suggested_distance is not None
                else None
            ),
        )


class PersonBrief(BaseModel):
    id: UUID
    name: str

    @classmethod
    def of(cls, person: Person) -> Self:
        return cls(id=person.id, name=person.name)


class PersonCard(BaseModel):
    id: UUID
    name: str
    hidden: bool
    #: How many of their faces, and in how many photos and videos.
    faces: int
    media: int
    cover: FaceView | None


class GroupView(BaseModel):
    """Unnamed faces that look like one person."""

    cluster: int
    size: int
    #: The clearest few.
    faces: list[FaceView]


class GroupPage(BaseModel):
    items: list[GroupView]
    next_cursor: str | None = None


class SuggestionView(BaseModel):
    """ "Ist das Lena?" """

    face: FaceView
    person: PersonBrief


class SuggestionPage(BaseModel):
    items: list[SuggestionView]
    next_cursor: str | None = None


class FacePage(BaseModel):
    items: list[FaceView]
    next_cursor: str | None = None


class PeopleOverview(BaseModel):
    #: Off when the admin switched faces off: nothing is shown then.
    enabled: bool = True
    persons: list[PersonCard]
    groups: GroupPage
    #: How many suggestions wait for a yes or no.
    suggestions: int


class NameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PersonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    hidden: bool | None = None


class MergeRequest(BaseModel):
    """The person the other one becomes."""

    into: UUID


class AlikeFace(BaseModel):
    """An open question that looks like the one just answered."""

    face: FaceView
    #: How alike this face is to the one just answered, from 0 to 1.
    similarity: float


class AlikeFaces(BaseModel):
    """What can be answered along with a face, most alike first."""

    person_id: UUID
    items: list[AlikeFace]


class MediaFaceView(BaseModel):
    """A face in the viewer: where it is, and who it is or might be."""

    face: FaceView
    person: PersonBrief | None
    suggested: PersonBrief | None


class ForgottenFaces(BaseModel):
    """What "delete all face data" deleted."""

    faces: int
    persons: int
