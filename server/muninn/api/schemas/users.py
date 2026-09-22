"""Contracts for accounts: the own profile and admin user management."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from muninn.api.schemas.email import Email
from muninn.core.security import MIN_PASSWORD_LENGTH, password_problem
from muninn.models.user import UserRole, UserStatus

#: A username is what people type to log in: letters, digits and . _ - in between.
USERNAME_PATTERN = r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]{1,30})[a-zA-Z0-9]$"

Username = Annotated[str, Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)]


def _check_password(value: str) -> str:
    problem = password_problem(value)
    if problem is not None:
        raise ValueError(problem)
    return value


#: At least MIN_PASSWORD_LENGTH characters, with at least one letter and one digit among them.
#: Other characters are welcome, just not required.
Password = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=200),
    AfterValidator(_check_password),
]
DisplayName = Annotated[str, Field(min_length=1, max_length=120)]


class UserProfile(BaseModel):
    """A user as everybody may see themselves and as admins see everybody."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    #: Kept for later; Muninn sends no mail, so an account does not need one.
    email: Email | None
    display_name: str
    role: UserRole
    status: UserStatus
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None


class ProfileUpdate(BaseModel):
    """What a user may change about themselves. The password has its own endpoint."""

    display_name: DisplayName


class UserCreate(BaseModel):
    username: Username
    display_name: DisplayName
    email: Email | None = None
    role: UserRole = UserRole.USER


class UserCreated(BaseModel):
    """The only moment the starting password is readable. It is never stored in clear text."""

    user: UserProfile
    starting_password: str


class UserUpdate(BaseModel):
    """What an admin may change about an account. A field left out stays as it is; an empty
    e-mail address takes it away."""

    display_name: DisplayName | None = None
    username: Username | None = None
    email: Email | Literal[""] | None = None
    role: UserRole | None = None
    status: UserStatus | None = None


class PasswordReset(BaseModel):
    starting_password: str
