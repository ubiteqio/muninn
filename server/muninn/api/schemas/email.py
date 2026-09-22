"""E-mail addresses as Muninn uses them.

The address is a login name, nothing else: Muninn never sends mail. So the syntax is checked, but
the domains of a home network are allowed, which the library rejects by default: ``.local`` and
``.home.arpa`` for mDNS and internal networks, ``.test`` and ``localhost`` for trying things out.
``.invalid`` and ``.onion`` stay rejected, they are never a real login name. Deliverability is
deliberately not checked, there is nothing to deliver.
"""

from typing import Annotated

import email_validator
from pydantic import AfterValidator, WithJsonSchema

MAX_EMAIL_LENGTH = 254

#: Removing entries from this list is how the library intends this to be configured.
ALLOWED_SPECIAL_USE_DOMAINS = frozenset({"arpa", "local", "localhost", "test"})
email_validator.SPECIAL_USE_DOMAIN_NAMES = [
    domain
    for domain in email_validator.SPECIAL_USE_DOMAIN_NAMES
    if domain not in ALLOWED_SPECIAL_USE_DOMAINS
]


def _validate(value: str) -> str:
    try:
        result = email_validator.validate_email(value, check_deliverability=False)
    except email_validator.EmailNotValidError as error:
        raise ValueError(str(error)) from error
    return result.normalized


Email = Annotated[
    str,
    AfterValidator(_validate),
    WithJsonSchema({"type": "string", "format": "email", "maxLength": MAX_EMAIL_LENGTH}),
]
