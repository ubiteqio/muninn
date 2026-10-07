"""The bell on the lock screen: what is new for somebody goes out to their phones as a push.

Every unread entry that never went out, or grew since it last did, is pushed once - unless the
person switched that kind of news off, or it falls into their quiet hours. Either way it counts
as handled, so the morning does not bring the night's news in a heap. Running this twice sends
nothing twice.

The words are the bell's, in German. The app is not running when a push arrives, so the server
says them; tests/test_push.py holds them against the app's de.json, so the two never drift apart.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.models.notification import Notification, NotificationKind, PushEvent
from muninn.models.user import User, UserStatus
from muninn.notify import devices
from muninn.notify import service as notify
from muninn.notify.apns import Answer, Outcome, Push


class Sender(Protocol):
    """Whoever carries a push to the phone: Apple's service, or a stand-in in the tests."""

    async def send(self, push: Push) -> Answer: ...


#: Which switch in the push settings each kind of entry listens to.
EVENT_OF: dict[str, PushEvent] = {
    NotificationKind.REPLY: PushEvent.REPLY,
    NotificationKind.MENTION: PushEvent.MENTION,
    NotificationKind.COMMENT_LIKE: PushEvent.COMMENT_LIKE,
    NotificationKind.COMMENT: PushEvent.COMMENT,
    NotificationKind.PICTURED_COMMENT: PushEvent.PICTURED,
    NotificationKind.PICTURED_LIKE: PushEvent.PICTURED,
    NotificationKind.NEW_MEDIA: PushEvent.NEW_MEDIA,
    NotificationKind.STAGE_FAILED: PushEvent.ADMIN_ALERTS,
}

#: notify.kind in the app's de.json: the first for one person, the second for several.
KIND_TEXT: dict[str, tuple[str, str]] = {
    NotificationKind.REPLY: (
        "{who} hat auf deinen Kommentar geantwortet",
        "{who} haben auf deinen Kommentar geantwortet",
    ),
    NotificationKind.MENTION: ("{who} hat dich erwähnt", "{who} haben dich erwähnt"),
    NotificationKind.COMMENT_LIKE: ("{who} gefällt dein Kommentar", "{who} gefällt dein Kommentar"),
    NotificationKind.COMMENT: ("{who} hat kommentiert", "{who} haben kommentiert"),
    NotificationKind.PICTURED_COMMENT: (
        "{who} hat ein Foto von dir kommentiert",
        "{who} haben ein Foto von dir kommentiert",
    ),
    NotificationKind.PICTURED_LIKE: (
        "{who} gefällt ein Foto von dir",
        "{who} gefällt ein Foto von dir",
    ),
}
#: notify.two, notify.more_one and notify.more_other.
TWO = "{first} und {second}"
MORE = ("{first} und 1 weitere Person", "{first} und {count} weitere")
#: notify.kind.new_media_one and _other.
NEW_MEDIA = ("1 neues Medium in {album}", "{count} neue Medien in {album}")
#: notify.kind.stage_failed, and admin.jobs.failedStage for the step.
STAGE_FAILED = "{stage} – nach drei Versuchen aufgegeben"  # noqa: RUF001 - the app's own dash
STAGES = {
    "metadata": "Metadaten nicht gelesen",
    "derive": "Vorschau nicht erzeugt",
    "image_vector": "Bildvektor nicht berechnet",
    "transcription": "Video nicht abgehört",
    "analysis": "Nicht beschrieben",
    "caption_vector": "Textvektor nicht berechnet",
    "faces": "Gesichter nicht gesucht",
    "derive_video": "Video nicht umgewandelt",
    "analysis_video": "Video nicht beschrieben",
    "image_vector_video": "Bildvektor des Videos nicht berechnet",
    "read": "Ordner nicht gelesen",
}


def people(names: Sequence[str], count: int) -> str:
    """Who did it, the way the bell says it: "Anna", "Boris und Anna", "Anna und 2 weitere"."""
    if not names:
        return ""
    others = max(count, len(names)) - 1
    if others == 0:
        return names[0]
    if others == 1 and len(names) > 1:
        return TWO.format(first=names[0], second=names[1])
    return MORE[0 if others == 1 else 1].format(first=names[0], count=others)


def text(entry: notify.Entry) -> str:
    """The words of one bell entry."""
    row = entry.notification
    if row.kind == NotificationKind.NEW_MEDIA:
        album = entry.album.display_title if entry.album else ""
        return NEW_MEDIA[0 if row.count == 1 else 1].format(count=row.count, album=album)
    if row.kind == NotificationKind.STAGE_FAILED:
        return STAGE_FAILED.format(stage=STAGES.get(row.stage or "", row.stage or ""))
    one, several = KIND_TEXT[row.kind]
    who = people(entry.actors, row.count)
    return (one if max(len(entry.actors), 1) == 1 else several).format(who=who)


async def deliver(
    session: AsyncSession,
    client: Sender,
    user_ids: Sequence[uuid.UUID],
    *,
    now: datetime | None = None,
    zone: str = "UTC",
) -> int:
    """Push what is new for these people. Returns how many pushes went out."""
    now = now or datetime.now(UTC)
    sent = 0
    for user_id in dict.fromkeys(user_ids):
        user = await session.get(User, user_id)
        if user is None or user.status is not UserStatus.ACTIVE:
            continue
        phones = await devices.of_user(session, user.id)
        waiting = list(
            await session.scalars(
                select(Notification)
                .where(
                    Notification.user_id == user.id,
                    Notification.read_at.is_(None),
                    or_(
                        Notification.pushed_at.is_(None),
                        Notification.pushed_at < Notification.updated_at,
                    ),
                )
                .order_by(Notification.updated_at)
            )
        )
        if not waiting:
            continue
        prefs = await notify.preferences(session, user)
        quiet = notify.is_quiet(prefs, now.astimezone(ZoneInfo(zone)).time())
        wanted = [
            row
            for row in waiting
            if not quiet and prefs.push.get(EVENT_OF.get(row.kind, PushEvent.ACTIVITY), False)
        ]
        badge = await notify.unread_count(session, user)
        gone: list[str] = []
        failed = False
        for entry in await notify.entries_of(session, wanted) if phones else []:
            push_data = {
                "notification_id": str(entry.notification.id),
                **({"media_id": str(entry.media.id)} if entry.media else {}),
                **({"album_id": str(entry.album.id)} if entry.album else {}),
            }
            for phone in phones:
                if phone.token in gone:
                    continue
                answer = await client.send(
                    Push(
                        token=phone.token,
                        body=text(entry),
                        badge=badge,
                        collapse_id=str(entry.notification.id),
                        data=push_data,
                    )
                )
                if answer.outcome is Outcome.SENT:
                    sent += 1
                elif answer.outcome is Outcome.GONE:
                    gone.append(phone.token)
                else:
                    failed = True
        # Pushed, switched off, quiet or without a phone: handled either way. Only a passing
        # failure leaves it for the next try.
        if not failed:
            for row in waiting:
                row.pushed_at = now
        await session.commit()
        await devices.gone(session, gone)
    return sent
