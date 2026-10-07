"""What goes to Apple for one push, and what Muninn makes of Apple's answer."""

import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from muninn.notify.apns import ApnsClient, Outcome, Push

TOKEN = "f0" * 32


def a_key() -> tuple[str, ec.EllipticCurvePublicKey]:
    """A key like the .p8 from the Apple Developer account, made for the test."""
    private = ec.generate_private_key(ec.SECP256R1())
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return pem, private.public_key()


def a_push() -> Push:
    return Push(
        token=TOKEN,
        body="Anna hat ein Foto von dir kommentiert",
        badge=3,
        collapse_id="notification-1",
        data={"media_id": "m1", "album_id": "a1"},
    )


async def test_a_push_is_signed_addressed_and_shaped_as_apple_wants() -> None:
    pem, public = a_key()
    seen: list[httpx.Request] = []

    def apple(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    client = ApnsClient(
        key=pem,
        key_id="KEY1234567",
        team_id="78F76BMEG8",
        topic="io.ubiteq.apps.muninn",
        transport=httpx.MockTransport(apple),
    )

    answer = await client.send(a_push())

    assert answer.outcome is Outcome.SENT
    (request,) = seen
    assert str(request.url) == f"https://api.push.apple.com/3/device/{TOKEN}"
    assert request.headers["apns-topic"] == "io.ubiteq.apps.muninn"
    assert request.headers["apns-push-type"] == "alert"
    assert request.headers["apns-collapse-id"] == "notification-1"
    token = request.headers["authorization"].removeprefix("bearer ")
    assert jwt.get_unverified_header(token) == {"alg": "ES256", "kid": "KEY1234567", "typ": "JWT"}
    assert jwt.decode(token, public, algorithms=["ES256"])["iss"] == "78F76BMEG8"
    assert json.loads(request.content) == {
        "aps": {
            "alert": {"body": "Anna hat ein Foto von dir kommentiert"},
            "badge": 3,
            "sound": "default",
        },
        "media_id": "m1",
        "album_id": "a1",
    }
    await client.close()


@pytest.mark.parametrize(
    ("status", "reason", "outcome"),
    [
        (410, "Unregistered", Outcome.GONE),
        (400, "BadDeviceToken", Outcome.GONE),
        (403, "InvalidProviderToken", Outcome.FAILED),
        (503, None, Outcome.FAILED),
    ],
)
async def test_apples_answer_says_whether_the_phone_is_gone(
    status: int, reason: str | None, outcome: Outcome
) -> None:
    pem, _ = a_key()

    def apple(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"reason": reason} if reason else None)

    client = ApnsClient(
        key=pem,
        key_id="KEY1234567",
        team_id="78F76BMEG8",
        topic="io.ubiteq.apps.muninn",
        transport=httpx.MockTransport(apple),
    )

    answer = await client.send(a_push())

    assert answer.outcome is outcome
    assert answer.reason == reason
    await client.close()


async def test_the_signed_token_is_kept_between_pushes() -> None:
    pem, _ = a_key()
    tokens: list[str] = []

    def apple(request: httpx.Request) -> httpx.Response:
        tokens.append(request.headers["authorization"])
        return httpx.Response(200)

    client = ApnsClient(
        key=pem,
        key_id="KEY1234567",
        team_id="78F76BMEG8",
        topic="io.ubiteq.apps.muninn",
        transport=httpx.MockTransport(apple),
    )
    await client.send(a_push())
    await client.send(a_push())

    # Apple turns away a provider that makes a new token for every push.
    assert tokens[0] == tokens[1]
    await client.close()
