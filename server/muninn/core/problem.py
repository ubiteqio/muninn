"""Errors as Problem Details (RFC 9457).

Every error the API returns has the media type ``application/problem+json`` and the same shape, so
the generated TypeScript client can handle failures in one place.
"""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"

#: Problem types are stable URNs; ``about:blank`` means "nothing beyond the status code".
PROBLEM_TYPE_PREFIX = "urn:muninn:problem:"


def problem_type(slug: str) -> str:
    return f"{PROBLEM_TYPE_PREFIX}{slug}"


class ProblemDetail(BaseModel):
    """The response body of every failed request."""

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class ProblemError(Exception):
    """Raise this instead of ``HTTPException`` to control the problem type."""

    def __init__(
        self,
        *,
        status: int,
        title: str,
        type: str = "about:blank",
        detail: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(title)
        self.status = status
        self.title = title
        self.type = type
        self.detail = detail
        self.extra = extra or {}


def _with_extra(problem: ProblemDetail, extra: Mapping[str, Any]) -> ProblemDetail:
    """Attach extension members. RFC 9457 allows any additional field on a problem."""
    for key, value in extra.items():
        setattr(problem, key, value)
    return problem


def _response(request: Request, problem: ProblemDetail) -> JSONResponse:
    problem.instance = str(request.url.path)
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def _handle_problem(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProblemError)  # noqa: S101 - handler is registered for this type only
    problem = _with_extra(
        ProblemDetail(type=exc.type, title=exc.title, status=exc.status, detail=exc.detail),
        exc.extra,
    )
    return _response(request, problem)


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    detail = exc.detail if isinstance(exc.detail, str) else None
    return _response(
        request,
        ProblemDetail(title=_title_for(exc.status_code), status=exc.status_code, detail=detail),
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return _response(
        request,
        _with_extra(
            ProblemDetail(
                type=problem_type("validation-failed"),
                title="Request validation failed",
                status=422,
            ),
            {"errors": errors},
        ),
    )


def _title_for(status: int) -> str:
    from http import HTTPStatus

    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProblemError, _handle_problem)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
