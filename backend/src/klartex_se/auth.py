"""API-token verification and request tiers.

The API_TOKEN env-var gates writes on /api/page-templates and the extended
render surface (the `latex` block, which passes raw LaTeX to the compiler).
Discovery endpoints and anonymous rendering of every other block are open.

Two dependencies sit on top of the same verification:

- `require_api_token` — a missing or wrong token is a 401. Used by writes.
- `render_tier` — no Authorization header means `Tier.ANONYMOUS`; a
  presented token is verified and yields `Tier.TOKEN`. A presented but
  wrong token is a 401, never a silent downgrade to anonymous.

This is a stopgap: one shared token in the environment. Accounts and
self-serve tokens are issue #19; per-tier quotas are #23.
"""

import os
import secrets
from enum import StrEnum

from fastapi import Header, HTTPException, status

# How a caller obtains a token. Repeated verbatim in llms.txt and
# index.html; one line to change when self-serve tokens land (#19).
TOKEN_HOWTO = (
    "Access is granted on request until self-serve accounts launch — "
    "email kontakt@klartex.se."
)


class Tier(StrEnum):
    """Access level of a request."""

    ANONYMOUS = "anonymous"
    TOKEN = "token"


def _verify(authorization: str | None) -> None:
    """Raise unless `authorization` carries the configured API token.

    503 when the instance has no token configured, 401 when the header is
    missing, malformed, or carries the wrong token.
    """
    expected = os.environ.get("API_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "type": "token_not_configured",
                "message": (
                    "This instance has no API token configured, so "
                    "token-authenticated requests cannot be served."
                ),
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "type": "token_required",
                "message": f"Missing 'Authorization: Bearer <token>'. {TOKEN_HOWTO}",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization.removeprefix("Bearer ").strip()
    # Constant-time compare to dodge timing attacks. Bytes rather than str,
    # so a non-ASCII token cannot raise TypeError.
    if not secrets.compare_digest(presented.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "type": "invalid_token",
                "message": f"The presented API token is not valid. {TOKEN_HOWTO}",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency for endpoints that always need a token."""
    _verify(authorization)


def render_tier(authorization: str | None = Header(default=None)) -> Tier:
    """FastAPI dependency resolving the caller's tier."""
    if authorization is None:
        return Tier.ANONYMOUS
    _verify(authorization)
    return Tier.TOKEN
