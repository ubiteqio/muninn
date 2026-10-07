"""Apple's push service: how a bell entry reaches an iPhone that is not looking.

Muninn only ever calls out to Apple here, so a server that is reachable at home alone still
reaches a phone anywhere. Apple wants HTTP/2 and a short-lived token signed with the key from the
Apple Developer account; the token is made anew every 50 minutes, as Apple asks.
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx
import jwt

PRODUCTION = "https://api.push.apple.com"
SANDBOX = "https://api.sandbox.push.apple.com"

#: Apple refuses a token older than an hour, and one made more often than every 20 minutes.
TOKEN_LIFETIME_SECONDS = 50 * 60

#: Apple's answers that mean the app on that phone is gone or no longer wants pushes.
GONE_REASONS = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}


class Outcome(StrEnum):
    SENT = "sent"
    #: The token is dead: forget the device.
    GONE = "gone"
    #: Anything else - Apple away, a key it refuses. Try again with the next push.
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Push:
    token: str
    body: str
    #: Unread entries, shown on the app's icon.
    badge: int
    #: A push with the same id replaces the one before: a bundle that grew is one push, not two.
    collapse_id: str
    #: Handed to the app when it is tapped, to open the right place.
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Answer:
    outcome: Outcome
    #: Apple's reason, when it gave one.
    reason: str | None = None


class ApnsClient:
    """Sends pushes to Apple. One per worker process: the connection and the token are kept."""

    def __init__(
        self,
        *,
        key: str,
        key_id: str,
        team_id: str,
        topic: str,
        sandbox: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key = key
        self._key_id = key_id
        self._team_id = team_id
        self._topic = topic
        self._http = httpx.AsyncClient(
            base_url=SANDBOX if sandbox else PRODUCTION,
            http2=transport is None,
            transport=transport,
            timeout=10.0,
        )
        self._token: str | None = None
        self._token_made = 0.0

    @classmethod
    def from_files(
        cls, *, key_file: Path, key_id: str, team_id: str, topic: str, sandbox: bool
    ) -> "ApnsClient":
        return cls(
            key=key_file.read_text(),
            key_id=key_id,
            team_id=team_id,
            topic=topic,
            sandbox=sandbox,
        )

    def _bearer(self) -> str:
        now = time.time()
        if self._token is None or now - self._token_made > TOKEN_LIFETIME_SECONDS:
            self._token = jwt.encode(
                {"iss": self._team_id, "iat": int(now)},
                self._key,
                algorithm="ES256",
                headers={"kid": self._key_id},
            )
            self._token_made = now
        return self._token

    async def send(self, push: Push) -> Answer:
        payload: dict[str, Any] = {
            "aps": {"alert": {"body": push.body}, "badge": push.badge, "sound": "default"},
            **push.data,
        }
        try:
            response = await self._http.post(
                f"/3/device/{push.token}",
                json=payload,
                headers={
                    "authorization": f"bearer {self._bearer()}",
                    "apns-topic": self._topic,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                    "apns-collapse-id": push.collapse_id[:64],
                },
            )
        except httpx.HTTPError:
            return Answer(Outcome.FAILED, "unreachable")
        if response.status_code == httpx.codes.OK:
            return Answer(Outcome.SENT)
        reason = _reason(response)
        if response.status_code == httpx.codes.GONE or reason in GONE_REASONS:
            return Answer(Outcome.GONE, reason)
        return Answer(Outcome.FAILED, reason)

    async def close(self) -> None:
        await self._http.aclose()


def _reason(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    reason = body.get("reason") if isinstance(body, dict) else None
    return reason if isinstance(reason, str) else None
