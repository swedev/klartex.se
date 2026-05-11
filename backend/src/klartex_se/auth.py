"""Admin-token verification for mutating endpoints.

ADMIN_TOKEN env-var gates POST/DELETE on /page-templates. Public endpoints
(GET, /render) are not affected.

This is a stopgap until real auth + orgs land (fas 5). When that happens,
this dependency is replaced by a session/JWT check.
"""

import os
import secrets

from fastapi import Header, HTTPException, status


def require_admin(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency. 401 if missing/wrong; 503 if token not configured."""
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        # Server isn't configured for admin operations at all.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin endpoints not configured on this instance",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization.removeprefix("Bearer ").strip()
    # constant-time compare to dodge timing attacks
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
