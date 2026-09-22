"""Password hashing, access tokens and refresh token secrets."""

import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from muninn.models.user import UserRole

#: Set to "1" to hash with the lowest cost Argon2 allows. Only the test suite may do this: it
#: hashes hundreds of passwords and cares that hashing round-trips, not that it is expensive.
CHEAP_HASHING_ENV = "MUNINN_PASSWORD_HASHING_IS_CHEAP"


@cache
def _get_hasher() -> PasswordHasher:
    """Argon2id with the library defaults, which follow the current OWASP recommendation.

    Built on first use rather than on import, so the test suite can choose the cheap parameters
    without having to win a race against import order.
    """
    if os.environ.get(CHEAP_HASHING_ENV) == "1":
        return PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    return PasswordHasher()


_ALGORITHM = "HS256"
_ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - a claim value, not a secret

#: Characters for generated starting passwords: no look-alikes, so they can be read out loud.
_PASSWORD_LETTERS = "abcdefghijkmnopqrstuvwxyz"  # noqa: S105 - an alphabet
_PASSWORD_DIGITS = "23456789"  # noqa: S105 - an alphabet
_PASSWORD_ALPHABET = _PASSWORD_LETTERS + _PASSWORD_DIGITS

#: The rule a password has to meet. Letters and digits are both required.
MIN_PASSWORD_LENGTH = 8


def password_problem(password: str) -> str | None:
    """Return why this password is not allowed, or None if it is."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"The password needs at least {MIN_PASSWORD_LENGTH} characters."
    if not any(character.isalpha() for character in password):
        return "The password needs at least one letter."
    if not any(character.isdigit() for character in password):
        return "The password needs at least one digit."
    return None


def hash_password(password: str) -> str:
    return _get_hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _get_hasher().verify(password_hash, password)
    except Argon2Error:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True once the stored hash uses weaker parameters than the current defaults."""
    return _get_hasher().check_needs_rehash(password_hash)


def generate_password(groups: int = 3, group_size: int = 4) -> str:
    """A starting password an admin can read out over the phone, about 60 bits of entropy.

    Drawn again until it meets the same rule people have to meet: a generated password that the
    server itself would reject would be a confusing thing to hand somebody.
    """
    while True:
        parts = [
            "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(group_size))
            for _ in range(groups)
        ]
        candidate = "-".join(parts)
        if password_problem(candidate) is None:
            return candidate


def generate_refresh_token() -> str:
    """The refresh token itself. Only its hash reaches the database."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 is enough here: the token is long and random, not a guessable password."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    role: UserRole
    expires_at: datetime


class InvalidAccessTokenError(Exception):
    """The token is missing, malformed, expired or not signed by us."""


def create_access_token(
    *, user_id: uuid.UUID, role: UserRole, secret: str, ttl: timedelta
) -> tuple[str, datetime]:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + ttl
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "typ": _ACCESS_TOKEN_TYPE,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM), expires_at


def decode_access_token(token: str, *, secret: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM], options={"require": ["exp"]})
    except jwt.PyJWTError as error:
        raise InvalidAccessTokenError(str(error)) from error

    if payload.get("typ") != _ACCESS_TOKEN_TYPE:
        raise InvalidAccessTokenError("not an access token")

    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            role=UserRole(payload["role"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (KeyError, ValueError) as error:
        raise InvalidAccessTokenError("malformed claims") from error
