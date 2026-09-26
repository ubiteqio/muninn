"""SQLAlchemy models. Importing this package registers every table on ``Base.metadata``."""

from muninn.models.album import Album
from muninn.models.analysis import MediaAnalysis, MediaTranscript, VideoFrame
from muninn.models.attempt import GIVE_UP_AFTER, MediaAttempt
from muninn.models.base import Base
from muninn.models.change_log import ChangeKind, ChangeLogEntry, SyncTrigger
from muninn.models.duplicate import DuplicateGroup, DuplicateMember
from muninn.models.face import Face, FaceRejection, Person
from muninn.models.media import (
    DateSource,
    Media,
    MediaFile,
    MediaFileRole,
    MediaKind,
    MediaStatus,
)
from muninn.models.memory import Memory, MemoryMedium
from muninn.models.notification import (
    Notification,
    NotificationKind,
    NotificationSettings,
)
from muninn.models.pending_file import PendingFile
from muninn.models.place import Place
from muninn.models.publication import Publication, ScanStatus
from muninn.models.refresh_token import RefreshToken
from muninn.models.settings import AppSettings
from muninn.models.smart import SMART_VERSION, SmartChapter, SmartChapterMedium
from muninn.models.social import Comment, CommentMention, Favorite, Like
from muninn.models.user import User, UserRole, UserStatus
from muninn.models.withdrawn import WithdrawnMedium

__all__ = [
    "GIVE_UP_AFTER",
    "SMART_VERSION",
    "Album",
    "AppSettings",
    "Base",
    "ChangeKind",
    "ChangeLogEntry",
    "Comment",
    "CommentMention",
    "DateSource",
    "DuplicateGroup",
    "DuplicateMember",
    "Face",
    "FaceRejection",
    "Favorite",
    "Like",
    "Media",
    "MediaAnalysis",
    "MediaAttempt",
    "MediaFile",
    "MediaFileRole",
    "MediaKind",
    "MediaStatus",
    "MediaTranscript",
    "Memory",
    "MemoryMedium",
    "Notification",
    "NotificationKind",
    "NotificationSettings",
    "PendingFile",
    "Person",
    "Place",
    "Publication",
    "RefreshToken",
    "ScanStatus",
    "SmartChapter",
    "SmartChapterMedium",
    "SyncTrigger",
    "User",
    "UserRole",
    "UserStatus",
    "VideoFrame",
    "WithdrawnMedium",
]
