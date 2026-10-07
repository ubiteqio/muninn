"""The bell on the lock screen: what goes out as a push, when, in which words, and only once."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.device import Device
from muninn.models.notification import NotificationKind, NotificationSettings, PushEvent
from muninn.models.user import User, UserStatus
from muninn.notify import push
from muninn.notify import service as notify
from muninn.notify.apns import Answer, Outcome, Push
from tests.helpers import create_user
from tests.test_social import a_picture

DE = Path(__file__).resolve().parents[2] / "app" / "src" / "i18n" / "locales" / "de.json"
#: A quarter past ten in the morning in Berlin, outside the default quiet hours.
MORNING = datetime(2026, 10, 7, 8, 15, tzinfo=UTC)


class FakeApple:
    """Takes pushes as Apple would, and answers what the test says."""

    def __init__(self, answer: Outcome = Outcome.SENT) -> None:
        self.answer = answer
        self.pushes: list[Push] = []

    async def send(self, push: Push) -> Answer:
        self.pushes.append(push)
        return Answer(self.answer)


async def an_account(
    session_factory: async_sessionmaker[AsyncSession],
    username: str,
    name: str,
    *,
    phone: str | None = None,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    user = await create_user(session_factory, username=username, display_name=name, status=status)
    if phone:
        async with session_factory() as session:
            session.add(Device(user_id=user.id, platform="ios", token=phone))
            await session.commit()
    return user


async def deliver(session: AsyncSession, apple: FakeApple, *users: User, at: datetime) -> int:
    return await push.deliver(
        session, apple, [user.id for user in users], now=at, zone="Europe/Berlin"
    )


def _app_text(value: str) -> str:
    """The app's {{count, number}} and {{who}} as the server spells them."""
    return re.sub(r"\{\{(\w+)(?:, \w+)?\}\}", r"{\1}", value)


def test_the_push_says_it_in_the_bells_own_words() -> None:
    texts = json.loads(DE.read_text(encoding="utf-8"))
    kind = texts["notify"]["kind"]
    for name, (one, several) in push.KIND_TEXT.items():
        assert (one, several) == (_app_text(kind[f"{name}_one"]), _app_text(kind[f"{name}_other"]))
    assert (
        _app_text(kind["new_media_one"]),
        _app_text(kind["new_media_other"]),
    ) == push.NEW_MEDIA
    assert _app_text(kind["stage_failed"]) == push.STAGE_FAILED
    assert texts["admin"]["jobs"]["failedStage"] == push.STAGES
    assert _app_text(texts["notify"]["two"]) == push.TWO
    assert (
        _app_text(texts["notify"]["more_one"]),
        _app_text(texts["notify"]["more_other"]),
    ) == push.MORE
    # Every kind of entry has its switch in the push settings.
    assert set(push.EVENT_OF) == {kind.value for kind in NotificationKind}


async def test_a_new_entry_goes_out_once_and_again_when_it_grows(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await an_account(session_factory, "anna", "Anna", phone="phone-anna")
    boris = await an_account(session_factory, "boris", "Boris")
    carla = await an_account(session_factory, "carla", "Carla")
    medium = await a_picture(session)
    about = notify.About(media_id=medium.id)
    apple = FakeApple()

    await notify.notify(
        session, [anna.id], NotificationKind.PICTURED_COMMENT, about, actor_id=boris.id, now=MORNING
    )
    await session.commit()
    assert await deliver(session, apple, anna, at=MORNING) == 1
    (first,) = apple.pushes
    assert first.token == "phone-anna"
    assert first.body == "Boris hat ein Foto von dir kommentiert"
    assert first.badge == 1
    assert first.data["media_id"] == str(medium.id)

    # Asked again, nothing new: nothing goes out.
    assert await deliver(session, apple, anna, at=MORNING) == 0

    # Carla joins the same entry: it goes out again, under the same id, so it replaces the first.
    later = MORNING.replace(minute=20)
    await notify.notify(
        session, [anna.id], NotificationKind.PICTURED_COMMENT, about, actor_id=carla.id, now=later
    )
    await session.commit()
    assert await deliver(session, apple, anna, at=later) == 1
    second = apple.pushes[-1]
    assert second.body == "Carla und Boris haben ein Foto von dir kommentiert"
    assert second.collapse_id == first.collapse_id
    assert second.badge == 1


async def test_switched_off_quiet_or_without_a_phone_nothing_goes_out_and_nothing_piles_up(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await an_account(session_factory, "anna", "Anna", phone="phone-anna")
    boris = await an_account(session_factory, "boris", "Boris")
    lena = await an_account(session_factory, "lena", "Lena")
    medium = await a_picture(session)
    about = notify.About(media_id=medium.id)
    apple = FakeApple()
    # Anna does not want comments on photos of her as a push.
    session.add(NotificationSettings(user_id=anna.id, push={PushEvent.PICTURED.value: False}))
    await session.commit()

    await notify.notify(
        session, [anna.id, lena.id], NotificationKind.PICTURED_LIKE, about, actor_id=boris.id
    )
    await session.commit()
    assert await deliver(session, apple, anna, lena, at=MORNING) == 0

    # At night: the default quiet hours, 22:00 to 07:00 where the family lives.
    night = datetime(2026, 10, 7, 21, 30, tzinfo=UTC)
    await notify.notify(session, [anna.id], NotificationKind.REPLY, about, actor_id=boris.id)
    await session.commit()
    assert await deliver(session, apple, anna, at=night) == 0

    # The morning after brings none of it: it was handled when it came.
    assert await deliver(session, apple, anna, lena, at=MORNING.replace(day=8)) == 0
    assert apple.pushes == []


async def test_a_dead_phone_is_forgotten_and_a_passing_failure_tried_again(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await an_account(session_factory, "anna", "Anna", phone="phone-anna")
    boris = await an_account(session_factory, "boris", "Boris")
    medium = await a_picture(session)
    about = notify.About(media_id=medium.id)
    await notify.notify(session, [anna.id], NotificationKind.MENTION, about, actor_id=boris.id)
    await session.commit()

    # Apple is away: the entry waits for the next try.
    assert await deliver(session, FakeApple(Outcome.FAILED), anna, at=MORNING) == 0
    apple = FakeApple()
    assert await deliver(session, apple, anna, at=MORNING) == 1
    assert apple.pushes[0].body == "Boris hat dich erwähnt"

    # The app was removed: Apple says so, and the phone is forgotten.
    await notify.notify(session, [anna.id], NotificationKind.REPLY, about, actor_id=boris.id)
    await session.commit()
    await deliver(session, FakeApple(Outcome.GONE), anna, at=MORNING)
    assert list(await session.scalars(select(Device))) == []


async def test_a_disabled_account_hears_nothing(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    opa = await an_account(
        session_factory, "opa", "Opa", phone="phone-opa", status=UserStatus.DISABLED
    )
    boris = await an_account(session_factory, "boris", "Boris")
    medium = await a_picture(session)
    await notify.notify(
        session,
        [opa.id],
        NotificationKind.REPLY,
        notify.About(media_id=medium.id),
        actor_id=boris.id,
    )
    await session.commit()
    apple = FakeApple()

    assert await deliver(session, apple, opa, at=MORNING) == 0
    assert apple.pushes == []


@pytest.mark.parametrize(
    ("names", "count", "said"),
    [
        (["Anna"], 1, "Anna"),
        (["Boris", "Anna"], 2, "Boris und Anna"),
        (["Carla", "Boris", "Anna"], 3, "Carla und 2 weitere"),
        (["Anna"], 2, "Anna und 1 weitere Person"),
    ],
)
def test_the_people_are_named_as_the_bell_names_them(
    names: list[str], count: int, said: str
) -> None:
    assert push.people(names, count) == said
