"""What comes as push, and when nothing does."""

from datetime import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.notification import PushEvent
from muninn.models.user import UserRole
from muninn.notify import service
from tests.test_comments import person

pytestmark = pytest.mark.usefixtures("api_client")


async def test_everybody_starts_with_the_concepts_defaults(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await person(api_client, session_factory, "anna", "Anna")

    settings = (await api_client.get("/me/notification-settings", headers=anna)).json()

    assert settings == {
        "push": {
            "reply": True,
            "mention": True,
            "comment_like": True,
            "comment": True,
            "activity": False,
            "new_media": True,
        },
        "quiet_enabled": True,
        "quiet_start": "22:00:00",
        "quiet_end": "07:00:00",
    }


async def test_a_choice_is_kept_and_what_was_left_out_stays(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await person(api_client, session_factory, "anna", "Anna")

    saved = await api_client.put(
        "/me/notification-settings",
        json={
            "push": {"new_media": False, "admin_alerts": False},
            "quiet_enabled": True,
            "quiet_start": "23:30",
            "quiet_end": "06:15",
        },
        headers=anna,
    )
    again = (await api_client.get("/me/notification-settings", headers=anna)).json()

    assert saved.status_code == 200
    assert again["push"]["new_media"] is False
    assert again["push"]["reply"] is True
    assert (again["quiet_start"], again["quiet_end"]) == ("23:30:00", "06:15:00")
    # Not an admin: admin alerts are neither shown nor taken.
    assert "admin_alerts" not in again["push"]


async def test_admins_have_admin_alerts(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    chef = await person(api_client, session_factory, "chef", "Chef", UserRole.ADMIN)

    settings = (await api_client.get("/me/notification-settings", headers=chef)).json()

    assert settings["push"]["admin_alerts"] is True


@pytest.mark.parametrize(
    ("start", "end", "moment", "quiet"),
    [
        (time(22), time(7), time(23, 30), True),
        (time(22), time(7), time(3), True),
        (time(22), time(7), time(7), False),
        (time(22), time(7), time(12), False),
        (time(13), time(15), time(14), True),
        (time(13), time(15), time(16), False),
    ],
)
def test_quiet_hours_may_run_past_midnight(
    start: time, end: time, moment: time, quiet: bool
) -> None:
    prefs = service.Preferences(
        push=dict.fromkeys(PushEvent, True), quiet_enabled=True, quiet_start=start, quiet_end=end
    )
    assert service.is_quiet(prefs, moment) is quiet
