"""Application settings, read from the environment (see deploy/.env.example)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting is prefixed with MUNINN_ in the environment."""

    model_config = SettingsConfigDict(
        env_prefix="MUNINN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"

    #: Paths inside the container. The host side of both is set in deploy/.env.
    library_path: Path = Path("/library")
    derived_path: Path = Path("/data/derived")
    #: The places from GeoNames, prepared when the image is built (muninn.places.gazetteer).
    places_file: Path = Path("/opt/muninn/places.tsv.gz")

    #: Signs access tokens. Changing it invalidates every access token at once.
    jwt_secret: str
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    #: Browsers keep the refresh token in a cookie; set to False only for local HTTP testing.
    refresh_cookie_secure: bool = True

    #: Origins that may call the API from somewhere else.
    #:
    #: The web app is served from the same origin as the API and needs none of this. A phone is
    #: different: the app is loaded from inside itself, so every request it makes is a request
    #: from another origin, and the browser in it asks permission first. These are the origins
    #: Capacitor gives the app on iOS and Android. Comma-separated in the environment.
    # NoDecode: the environment spells the list comma-separated, not as JSON; the validator below
    # splits it. Without it the settings refuse to start on the very form the template shows.
    cors_origins: Annotated[list[str], NoDecode] = [
        "capacitor://localhost",
        "ionic://localhost",
        "http://localhost",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """An environment variable is one line; a list of origins is comma-separated in it."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    #: Failed logins allowed per IP address within the window.
    login_attempts_per_window: int = 10
    login_attempt_window_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    """Settings are read once per process."""
    return Settings()  # type: ignore[call-arg]
