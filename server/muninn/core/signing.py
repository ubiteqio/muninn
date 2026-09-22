"""Signed media URLs.

Pictures and videos are loaded with a signature in the address rather than with a session: the
browser may then cache them, and the native app needs no cookies. A signature says nothing more
than "this medium, this variant, until then".

The address has to stay the same for a while, or the cache is useless: every list the app asks
for again would bring new addresses, and the browser would load every thumbnail anew. So the
expiry is not "an hour from now" but the end of the next full hour: all addresses made within
one hour are identical, and each stays good for one to two hours.
"""

import hashlib
import hmac
import time
import uuid

#: How long a signed address stays valid.
DEFAULT_TTL_SECONDS = 3600

_SEPARATOR = "."


def sign_media(
    media_id: uuid.UUID,
    variant: str,
    *,
    secret: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: int | None = None,
) -> str:
    """A token for one medium and one variant, the same for everybody asking within one period."""
    current = now if now is not None else int(time.time())
    expires_at = (current // ttl_seconds + 2) * ttl_seconds
    return f"{expires_at}{_SEPARATOR}{_digest(media_id, variant, expires_at, secret)}"


def verify_media(
    token: str,
    media_id: uuid.UUID,
    variant: str,
    *,
    secret: str,
    now: int | None = None,
) -> bool:
    """Whether this token was made by us, for this medium and variant, and is still valid."""
    expires_raw, _, signature = token.partition(_SEPARATOR)
    if not signature:
        return False

    try:
        expires_at = int(expires_raw)
    except ValueError:
        return False

    if expires_at < (now if now is not None else int(time.time())):
        return False

    return hmac.compare_digest(signature, _digest(media_id, variant, expires_at, secret))


def _digest(media_id: uuid.UUID, variant: str, expires_at: int, secret: str) -> str:
    message = f"{media_id}:{variant}:{expires_at}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
