"""Contracts for logging in, refreshing and changing the own password."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from muninn.api.schemas.users import Password, Username, UserProfile

#: Browsers get the refresh token in an httpOnly cookie, the native app in the body.
ClientKind = Literal["web", "native"]


class LoginRequest(BaseModel):
    username: Username
    password: str
    client: ClientKind = "web"


class RefreshRequest(BaseModel):
    """Native clients send the token; browsers send nothing and rely on the cookie."""

    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - a scheme name, not a secret
    expires_at: datetime
    #: Only filled for native clients.
    refresh_token: str | None = None
    user: UserProfile


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: Password
    #: Decides where the new refresh token goes, exactly as on login.
    client: ClientKind = "web"
