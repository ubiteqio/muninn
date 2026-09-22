"""The contract of likes and favourites."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from muninn.models.social import Reaction
from muninn.models.user import User, UserRole
from muninn.social.comments import MAX_BODY, Author, CommentNode
from muninn.social.service import Summary, Target, TargetKind


class ReactionCount(BaseModel):
    reaction: Reaction
    count: int


class LikerView(BaseModel):
    name: str
    reaction: Reaction


class LikeRequest(BaseModel):
    """Which reaction; a heart when nothing is said."""

    reaction: Reaction = Reaction.HEART


class SocialView(BaseModel):
    """What goes beside the heart and the star of a medium or an album."""

    likes: int
    #: Whether the person asking liked it.
    liked: bool
    #: Up to three names: the person asking first when they liked it, then the most recent.
    likers: list[str]
    #: Whether it is in the asking person's Walhall.
    favorite: bool
    #: How many comments there are to read.
    comments: int = 0
    #: The asking person's own reaction, if they reacted.
    reaction: Reaction | None = None
    #: How often each reaction was given, the most frequent first.
    reactions: list[ReactionCount] = []
    #: The same people as likers, each with their reaction.
    people: list[LikerView] = []

    @classmethod
    def of(cls, summary: Summary) -> Self:
        return cls(
            likes=summary.likes,
            liked=summary.liked,
            likers=summary.likers,
            favorite=summary.favorite,
            comments=summary.comments,
            reaction=Reaction(summary.reaction) if summary.reaction else None,
            reactions=[
                ReactionCount(reaction=Reaction(reaction), count=count)
                for reaction, count in summary.reactions
            ],
            people=[
                LikerView(name=name, reaction=Reaction(reaction))
                for name, reaction in zip(summary.likers, summary.liker_reactions, strict=True)
            ],
        )


class FavoriteTarget(BaseModel):
    """A medium or an album - exactly one of them."""

    media_id: UUID | None = None
    album_id: UUID | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.media_id is None) == (self.album_id is None):
            raise ValueError("Name either a medium or an album.")
        return self

    def target(self) -> Target:
        if self.media_id is not None:
            return Target(TargetKind.MEDIA, self.media_id)
        assert self.album_id is not None  # noqa: S101 - the validator made sure
        return Target(TargetKind.ALBUM, self.album_id)


class PersonView(BaseModel):
    """Somebody, as a comment names them."""

    id: UUID
    display_name: str
    username: str

    @classmethod
    def of(cls, author: Author) -> Self:
        return cls(id=author.id, display_name=author.display_name, username=author.username)


class CommentView(BaseModel):
    id: UUID
    author: PersonView
    #: Empty once deleted; the place stays for the answers.
    body: str
    created_at: datetime
    edited_at: datetime | None
    deleted: bool
    likes: int
    liked: bool
    #: What the asking person may do with it.
    can_edit: bool
    can_delete: bool
    #: The answers, oldest first. Answers have none of their own.
    replies: list["CommentView"] = []

    @classmethod
    def of(cls, node: CommentNode, viewer: User) -> Self:
        comment = node.comment
        deleted = comment.deleted_at is not None
        own = comment.user_id == viewer.id
        return cls(
            id=comment.id,
            author=PersonView.of(node.author),
            body=comment.body,
            created_at=comment.created_at,
            edited_at=comment.edited_at,
            deleted=deleted,
            likes=node.likes,
            liked=node.liked,
            can_edit=own and not deleted,
            can_delete=not deleted and (own or viewer.role is UserRole.ADMIN),
            replies=[cls.of(reply, viewer) for reply in node.replies],
        )


class CommentList(BaseModel):
    """Every comment of a medium or album, answers under what they answer."""

    items: list[CommentView]
    #: How many there are to read, answers included - the number beside the speech bubble.
    count: int


class NewComment(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)
    #: The comment this one answers.
    parent_id: UUID | None = None


class CommentEdit(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)


class CommentLikes(BaseModel):
    likes: int
    liked: bool
