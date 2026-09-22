"""One way of putting a Python enum into PostgreSQL."""

from enum import StrEnum

from sqlalchemy import Enum


def pg_enum(enum_type: type[StrEnum], name: str) -> Enum:
    """Store the enum values, not the Python member names."""
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda members: [member.value for member in members],
    )
