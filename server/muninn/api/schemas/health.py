"""Contracts for the container health endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness: the process is up. Checks nothing else on purpose."""

    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    """Readiness: every dependency the API needs to serve requests answered."""

    status: Literal["ready", "unready"]
    database: bool
    redis: bool
