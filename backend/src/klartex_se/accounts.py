"""Self-serve accounts: email, a six-digit code, and a session cookie.

Anyone with a working mailbox can sign in — there is no allowlist, because
the point of accounts here is that a caller obtains API access without
anyone handing it over. Signing in for the first time creates the user and
a one-person org for them.

Sign-in is a code and nothing else. A magic link would drag in the mail
scanner problem (a `GET` that must not spend the sign-in) without buying
anything: the code is typed into the same page that asked for it, so a
client keeps no state between the two halves.

Three properties hold the flow together:

- **Enumeration safety.** `request-code` answers the same for an address
  that has an account, one that does not, and one still inside its
  cooldown. Verification answers the same for a wrong, spent, expired and
  exhausted code.
- **Nothing replayable is stored.** The code is kept as an HMAC keyed with
  `LOGIN_CODE_SECRET`, which never reaches the database; the session token
  as a plain sha256.
- **Races cannot double-spend.** One guarded `UPDATE` consumes a code, and
  the request path serialises per address on a `pg_advisory_xact_lock`, so
  two concurrent requests cannot leave two live codes behind.

`LOGIN_CODE_SECRET` is required: the process refuses to start without it.
A per-process fallback would look like it worked while silently breaking
every outstanding code at a restart, and every code minted by one worker
for the next.
"""

import hashlib
import hmac
import os
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session as DbSession

from klartex_se.db import get_db
from klartex_se.models import LoginToken, Org, Session, User

router = APIRouter(tags=["auth"])

SESSION_COOKIE = "klartex_session"
SESSION_TTL_DAYS = 30
LOGIN_CODE_TTL_MINUTES = 15
LOGIN_REQUEST_COOLDOWN_SECONDS = 60
LOGIN_CODE_MAX_ATTEMPTS = 5

# Auth answers carry credentials and account state; no cache, anywhere, may
# hold on to them.
NO_STORE = {"Cache-Control": "no-store"}

# The one answer `request-code` gives: registered, unknown and cooled-down
# addresses are indistinguishable from the outside.
GENERIC_REQUEST_ANSWER = {
    "message": "If the address can receive mail, a sign-in code is on its way."
}
# Wrong, spent, expired and exhausted codes answer with this and nothing else.
INVALID_CODE_MESSAGE = "Invalid or expired code."

_DEFAULT_PORTS = {"http": 80, "https": 443}


def base_url() -> str:
    """The public origin this instance is served from."""
    return os.environ.get("BASE_URL", "https://app.klartex.se")


def admin_emails() -> set[str]:
    """The addresses treated as administrators.

    Server configuration rather than a column, so no database write can
    promote an account.
    """
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def is_admin(email: str) -> bool:
    return email.strip().lower() in admin_emails()


def _require_login_code_secret() -> str:
    """The HMAC key for sign-in codes, or `RuntimeError`."""
    secret = os.environ.get("LOGIN_CODE_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "LOGIN_CODE_SECRET is not set. Sign-in codes are stored as an "
            "HMAC keyed with it, and a per-process fallback would break "
            "every outstanding code at a restart and across workers. "
            "Generate one with `openssl rand -base64 32`; see "
            "infra/.env.example."
        )
    return secret


# Checked at import so a misconfigured instance fails at startup rather than
# at the first sign-in attempt.
_require_login_code_secret()


def _hash(token: str) -> str:
    """Digest of a bearer credential — the only form that is stored."""
    return hashlib.sha256(token.encode()).hexdigest()


def _code_hash(code: str) -> str:
    """Keyed digest of a sign-in code.

    Six digits is a space a thief walks through in microseconds against a
    plain digest, so the stored value is keyed with a secret that lives
    only in the environment.
    """
    return hmac.new(
        _require_login_code_secret().encode(), code.encode(), hashlib.sha256
    ).hexdigest()


def _origin_parts(value: str) -> tuple[str, str | None, int | None] | None:
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    port = parts.port or _DEFAULT_PORTS.get(parts.scheme)
    return (parts.scheme, parts.hostname, port)


def check_origin(request: Request) -> None:
    """Reject a cross-origin write.

    A missing `Origin` passes, so curl, agents and tests keep working; a
    present one must match `BASE_URL` on scheme, host and port, which
    rejects `null` and malformed values too.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    if _origin_parts(origin) != _origin_parts(base_url()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin request rejected.",
            headers=NO_STORE,
        )


def _purge_expired(db: DbSession, now: datetime) -> None:
    """Drop rows that can no longer authenticate anything.

    `request-code` is unauthenticated, so without this the tables grow for
    as long as anyone cares to poke it.
    """
    db.execute(delete(LoginToken).where(LoginToken.expires_at < now))
    db.execute(delete(Session).where(Session.expires_at < now))


def _send_code_email(to: str, code: str) -> None:
    """Mail a sign-in code over SMTP."""
    host = os.environ.get("SMTP_HOST", "")
    if not host:
        raise RuntimeError(
            "SMTP_HOST is not set, so sign-in codes cannot be delivered. "
            "See infra/.env.example."
        )
    message = EmailMessage()
    message["From"] = os.environ.get("SMTP_FROM", "kontakt@klartex.se")
    message["To"] = to
    message["Subject"] = "Din inloggningskod till klartex.se"
    # The code sits alone on its line so iOS offers it above the keyboard.
    message.set_content(
        "Din engångskod för att logga in på klartex.se:\n\n"
        f"{code}\n\n"
        f"Koden gäller i {LOGIN_CODE_TTL_MINUTES} minuter och kan bara "
        "användas en gång. Ignorera det här mejlet om du inte begärde den."
    )
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if os.environ.get("SMTP_TLS", "true").lower() == "true":
            smtp.starttls()
        user = os.environ.get("SMTP_USER", "")
        if user:
            smtp.login(user, os.environ.get("SMTP_PASSWORD", ""))
        smtp.send_message(message)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=base_url().startswith("https"),
    )


def _create_session(db: DbSession, email: str, now: datetime) -> str:
    """Mint a session token, creating the user and its org on first sign-in.

    The caller commits: consuming the code and inserting the session belong
    to one transaction, so a failed insert gives the code back instead of
    burning it.
    """
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        # The org is named after the address it was created for; nothing
        # renames it yet, and multi-user orgs are a later decision.
        org = Org(name=email)
        db.add(org)
        db.flush()
        user = User(email=email, org_id=org.id)
        db.add(user)
        db.flush()
    token = secrets.token_urlsafe(32)
    db.add(
        Session(
            user_id=user.id,
            token_hash=_hash(token),
            expires_at=now + timedelta(days=SESSION_TTL_DAYS),
        )
    )
    return token


def _session_user(db: DbSession, request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = db.scalar(select(Session).where(Session.token_hash == _hash(token)))
    if session is None or session.expires_at < datetime.now(UTC):
        return None
    return db.get(User, session.user_id)


def current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    """The signed-in user, or 401.

    Cookie sessions only. A machine's bearer token is a parla principal
    with scopes, not a user, and the two are kept apart deliberately: a
    user satisfies every scope check implicitly, so folding a machine into
    this dependency would hand it whatever a person may do.
    """
    user = _session_user(db, request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in.",
            headers=NO_STORE,
        )
    return user


class CodeRequest(BaseModel):
    email: EmailStr


class GenericMessage(BaseModel):
    message: str


@router.post("/auth/request-code", response_model=GenericMessage)
def request_code(
    body: CodeRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> dict:
    """Mail a fresh sign-in code to the address, at most once a minute."""
    check_origin(request)
    response.headers.update(NO_STORE)
    email = body.email.lower()
    now = datetime.now(UTC)

    _purge_expired(db, now)

    # Hold the address for the rest of this transaction so the cooldown
    # check, the invalidation and the insert below cannot interleave with a
    # concurrent request for the same address and leave two live codes. The
    # lock lives only in the running transaction, unlike a unique index,
    # which would outlast a rollback to an image that does not expect it and
    # block sign-in for the address until repaired by hand.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:email))"), {"email": email})

    recent = db.scalar(
        select(LoginToken)
        .where(LoginToken.email == email)
        .where(
            LoginToken.created_at
            > now - timedelta(seconds=LOGIN_REQUEST_COOLDOWN_SECONDS)
        )
    )
    if recent is not None:
        db.commit()
        return GENERIC_REQUEST_ANSWER

    code = f"{secrets.randbelow(10**6):06d}"
    # Latest request wins: the previous code is spent before the new one
    # exists, so exactly one is live per address.
    db.execute(
        update(LoginToken)
        .where(LoginToken.email == email)
        .where(LoginToken.used.is_(False))
        .values(used=True)
        .execution_options(synchronize_session=False)
    )
    db.add(
        LoginToken(
            email=email,
            code_hash=_code_hash(code),
            expires_at=now + timedelta(minutes=LOGIN_CODE_TTL_MINUTES),
        )
    )
    db.commit()

    _send_code_email(email, code)
    return GENERIC_REQUEST_ANSWER


class CodeSubmission(BaseModel):
    email: EmailStr
    code: str = Field(min_length=1, max_length=20)


class SignedIn(BaseModel):
    status: Literal["signed-in"]


@router.post("/auth/code", response_model=SignedIn)
def sign_in_with_code(
    body: CodeSubmission,
    request: Request,
    db: DbSession = Depends(get_db),
) -> Response:
    """Spend a code and sign this browser in.

    Only the typed address and code are needed, so the client that asked
    for the mail can finish here holding no state of its own.
    """
    check_origin(request)
    now = datetime.now(UTC)
    email = body.email.lower()
    code = "".join(ch for ch in body.code if ch.isdigit())

    # One guarded statement consumes the row, so two concurrent submissions
    # of the same code cannot both win.
    consumed = db.execute(
        update(LoginToken)
        .where(LoginToken.email == email)
        .where(LoginToken.used.is_(False))
        .where(LoginToken.expires_at >= now)
        .where(LoginToken.code_hash == _code_hash(code))
        .where(LoginToken.code_attempts < LOGIN_CODE_MAX_ATTEMPTS)
        .values(used=True)
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        db.rollback()
        # A miss costs an attempt; the code dies after
        # LOGIN_CODE_MAX_ATTEMPTS of them, which is what bounds guessing
        # one out of a million within the fifteen-minute window.
        db.execute(
            update(LoginToken)
            .where(LoginToken.email == email)
            .where(LoginToken.used.is_(False))
            .where(LoginToken.expires_at >= now)
            .where(LoginToken.code_attempts < LOGIN_CODE_MAX_ATTEMPTS)
            .values(code_attempts=LoginToken.code_attempts + 1)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_CODE_MESSAGE,
            headers=NO_STORE,
        )

    token = _create_session(db, email, now)
    _purge_expired(db, now)
    db.commit()

    signed_in = JSONResponse(content={"status": "signed-in"}, headers=NO_STORE)
    _set_session_cookie(signed_in, token)
    return signed_in


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> dict:
    """Drop this browser's session. Answers the same whether or not one existed."""
    check_origin(request)
    response.headers.update(NO_STORE)
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(Session).where(Session.token_hash == _hash(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "signed-out"}


@router.get("/me")
def me(response: Response, user: User = Depends(current_user)) -> dict:
    """Who the caller is signed in as."""
    response.headers.update(NO_STORE)
    return {
        "email": user.email,
        "org_id": str(user.org_id),
        "admin": is_admin(user.email),
    }
