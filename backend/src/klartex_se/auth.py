"""API-token verification for mutating endpoints.

`API_TOKEN` env-var gates all write endpoints:

- `POST /render`
- `POST /page-templates`
- `DELETE /page-templates/<name>`

Read-only endpoints (`GET /health`, `/templates`, `/blocks`, `/page-templates`,
`/page-templates/<name>`) stay public — metadata-discovery is harmless.

This is a stopgap until per-user auth lands (Clerk integration on the
frontend + JWT-validering här). When that arrives, this dependency is
replaced or supplemented by a session/JWT check.
"""

import os
import secrets

from fastapi import Header, HTTPException, status


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency. 401 if missing/wrong; 503 if token not configured."""
    expected = os.environ.get("API_TOKEN")
    if not expected:
        # Server isn't configured for write operations at all.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_TOKEN not configured on this instance",
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
