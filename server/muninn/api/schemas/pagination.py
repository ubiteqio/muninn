"""Cursor pagination. Page numbers get slow on large tables, so Muninn never uses them."""

import base64
import binascii
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    #: Pass as ``cursor`` to fetch the next page; null means this was the last one.
    next_cursor: str | None = None
    #: Pass as ``before`` to fetch the page in front of this one; null means this was the first.
    prev_cursor: str | None = None


def encode_cursor(sort_value: datetime, identifier: UUID) -> str:
    raw = f"{sort_value.isoformat()}|{identifier}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Raise ValueError for anything we did not hand out."""
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        sort_value, identifier = raw.split("|", 1)
        return datetime.fromisoformat(sort_value), UUID(identifier)
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise ValueError("malformed cursor") from error
