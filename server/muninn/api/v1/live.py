"""The live channel (WS /ws): events as they happen, without asking again and again."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.core.config import Settings
from muninn.core.deps import get_redis, get_session, get_settings_from_state
from muninn.core.security import InvalidAccessTokenError, decode_access_token
from muninn.models.user import User, UserRole, UserStatus
from muninn.notify import events

router = APIRouter(tags=["live"])

#: Closing codes. 1008 is "policy violation", which is what a socket without a good token is.
UNAUTHENTICATED = 1008

#: The token travels as a WebSocket subprotocol, because a browser cannot set headers on a
#: socket and a token in the address would end up in every proxy log.
TOKEN_PROTOCOL = "bearer"  # noqa: S105 - a protocol name, not a secret

#: Topics only an admin may hear. The engine room says which files are on the NAS.
ADMIN_ONLY = {"jobs"}


@router.websocket("/ws")
async def live(
    websocket: WebSocket,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Every event the installation produces, for as long as the page is open."""
    user = await _user_behind(websocket, session, settings)
    if user is None:
        await websocket.close(code=UNAUTHENTICATED)
        return

    is_admin = user.role is UserRole.ADMIN
    # The socket stays open for as long as the page does. Its database connection must not: it
    # would sit in the pool, idle in its transaction, and a few open tabs would starve the API.
    await session.close()
    await websocket.accept(subprotocol=TOKEN_PROTOCOL)

    # One task watches the socket: without reading from it, a page that goes away is only
    # noticed the next time something happens to be sent, which may be never.
    watching = asyncio.create_task(_until_gone(websocket))
    try:
        async for event in events.listen(redis):
            if watching.done():
                break
            if event.get("topic") in ADMIN_ONLY and not is_admin:
                continue
            recipients = event.pop("recipients", None)
            # Meant for some people only: the others never hear of it, not even that it exists.
            if recipients is not None and str(user.id) not in recipients:
                continue
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        watching.cancel()


async def _until_gone(websocket: WebSocket) -> None:
    """Waits for the page to close the socket. Anything it sends is ignored."""
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return


async def _user_behind(
    websocket: WebSocket, session: AsyncSession, settings: Settings
) -> User | None:
    """The user whose token the socket carries, or None for anybody else."""
    offered = websocket.headers.get("sec-websocket-protocol", "")
    parts = [part.strip() for part in offered.split(",") if part.strip()]
    if len(parts) != 2 or parts[0] != TOKEN_PROTOCOL:
        return None

    try:
        claims = decode_access_token(parts[1], secret=settings.jwt_secret)
    except InvalidAccessTokenError:
        return None

    user = await session.get(User, claims.user_id)
    if user is None or user.status is not UserStatus.ACTIVE or user.must_change_password:
        return None
    return user
