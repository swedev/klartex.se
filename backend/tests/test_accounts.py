"""Sign-in: email, a six-digit code, a session cookie.

Against a real Postgres, like the migration suite and for the same reason:
the flow leans on `pg_advisory_xact_lock`, a guarded `UPDATE … RETURNING`
rowcount and a functional unique index, none of which another dialect
would exercise honestly. The suite skips itself when `DATABASE_URL` points
at nothing reachable, and it truncates the account tables between tests —
point it at a scratch database, never one holding real rows.

The properties under test are the ones an attacker probes: that the
answers do not say whether an address has an account, that a code cannot
be spent twice or guessed indefinitely, and that nothing replayable is
written down.
"""

import os
import ssl
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from klartex_se import accounts, db
from klartex_se.main import app
from klartex_se.models import LoginToken, Org, Session, User

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.environ.get("DATABASE_URL", "")

EMAIL = "anna@example.com"


def _reachable() -> bool:
    if not DATABASE_URL:
        return False
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


pytestmark = pytest.mark.skipif(
    not _reachable(), reason="no database reachable at DATABASE_URL"
)


@pytest.fixture(scope="module", autouse=True)
def schema():
    """Bring the database to head once for the module."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"


@pytest.fixture(autouse=True)
def empty_tables(schema):
    """Every test starts with no accounts, codes or sessions."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE sessions, login_tokens, users, org CASCADE")
    db.reset_engine()


@pytest.fixture
def mailbox(monkeypatch):
    """Capture what would have been mailed, as (address, code) pairs."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        accounts, "_send_code_email", lambda to, code: sent.append((to, code))
    )
    return sent


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session():
    """A database session for asserting on rows directly."""
    with db.get_session_factory()() as db_session:
        yield db_session


def request_code(client, email: str = EMAIL):
    return client.post("/api/auth/request-code", json={"email": email})


def sign_in(client, mailbox, email: str = EMAIL) -> str:
    """Run the whole flow and return the code that was used."""
    assert request_code(client, email).status_code == 200
    _, code = mailbox[-1]
    assert (
        client.post("/api/auth/code", json={"email": email, "code": code}).status_code
        == 200
    )
    return code


def expire_codes(email: str = EMAIL) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "UPDATE login_tokens SET expires_at = now() - interval '1 minute' "
            "WHERE email = %s",
            (email,),
        )


# --- requesting a code -------------------------------------------------------


def test_request_code_mails_six_digits(client, mailbox):
    assert request_code(client).status_code == 200
    assert len(mailbox) == 1
    to, code = mailbox[0]
    assert to == EMAIL
    assert len(code) == 6 and code.isdigit()


def test_only_the_digest_of_the_code_is_stored(client, mailbox, session):
    request_code(client)
    _, code = mailbox[0]
    row = session.scalar(select(LoginToken))
    assert row.code_hash != code
    assert row.code_hash == accounts._code_hash(code)
    # And the plaintext is nowhere else in the row either.
    assert code not in str(row.__dict__)


def test_a_second_request_inside_the_cooldown_sends_nothing(client, mailbox):
    first = request_code(client)
    second = request_code(client)
    assert len(mailbox) == 1
    # Indistinguishable from the outside: the cooldown is not an oracle for
    # "this address just asked".
    assert (first.status_code, first.json()) == (second.status_code, second.json())


def test_an_unknown_address_answers_like_a_known_one(client, mailbox):
    known = request_code(client)
    sign_in(client, mailbox)
    stranger = request_code(client, "nobody@example.com")
    assert (known.status_code, known.json()) == (
        stranger.status_code,
        stranger.json(),
    )


def test_a_new_code_spends_the_previous_one(client, mailbox, session, monkeypatch):
    request_code(client)
    _, first_code = mailbox[0]
    monkeypatch.setattr(accounts, "LOGIN_REQUEST_COOLDOWN_SECONDS", 0)
    request_code(client)
    assert len(mailbox) == 2

    # Exactly one live code per address; the older one is spent.
    live = session.scalars(select(LoginToken).where(LoginToken.used.is_(False))).all()
    assert len(live) == 1
    assert (
        client.post(
            "/api/auth/code", json={"email": EMAIL, "code": first_code}
        ).status_code
        == 400
    )


def test_auth_answers_are_not_cacheable(client, mailbox):
    assert request_code(client).headers["cache-control"] == "no-store"
    _, code = mailbox[0]
    signed_in = client.post("/api/auth/code", json={"email": EMAIL, "code": code})
    assert signed_in.headers["cache-control"] == "no-store"
    assert client.get("/api/me").headers["cache-control"] == "no-store"


# --- spending a code ---------------------------------------------------------


def test_sign_in_creates_the_user_and_a_one_person_org(client, mailbox, session):
    sign_in(client, mailbox)
    user = session.scalar(select(User))
    assert user.email == EMAIL
    org = session.get(Org, user.org_id)
    assert org is not None
    assert session.scalars(select(User)).all() == [user]


def test_me_reports_the_signed_in_user(client, mailbox, session):
    sign_in(client, mailbox)
    body = client.get("/api/me").json()
    user = session.scalar(select(User))
    assert body == {"email": EMAIL, "org_id": str(user.org_id), "admin": False}


def test_a_code_can_only_be_spent_once(client, mailbox):
    code = sign_in(client, mailbox)
    again = client.post("/api/auth/code", json={"email": EMAIL, "code": code})
    assert again.status_code == 400


def test_wrong_spent_and_expired_codes_answer_identically(client, mailbox):
    request_code(client)
    _, code = mailbox[0]
    wrong = client.post("/api/auth/code", json={"email": EMAIL, "code": "000000"})

    expire_codes()
    expired = client.post("/api/auth/code", json={"email": EMAIL, "code": code})

    unknown = client.post(
        "/api/auth/code", json={"email": "nobody@example.com", "code": "123456"}
    )

    answers = {(r.status_code, r.text) for r in (wrong, expired, unknown)}
    assert len(answers) == 1
    assert wrong.status_code == 400


def test_a_code_dies_after_five_wrong_attempts(client, mailbox):
    request_code(client)
    _, code = mailbox[0]
    wrong = "".join("1" if ch != "1" else "2" for ch in code)
    for _ in range(accounts.LOGIN_CODE_MAX_ATTEMPTS):
        assert (
            client.post(
                "/api/auth/code", json={"email": EMAIL, "code": wrong}
            ).status_code
            == 400
        )
    # The right code no longer works: guessing one in a million is bounded
    # by the attempt count, not by the fifteen-minute window.
    assert (
        client.post("/api/auth/code", json={"email": EMAIL, "code": code}).status_code
        == 400
    )


def test_an_expired_code_does_not_sign_anyone_in(client, mailbox, session):
    request_code(client)
    _, code = mailbox[0]
    expire_codes()
    assert (
        client.post("/api/auth/code", json={"email": EMAIL, "code": code}).status_code
        == 400
    )
    assert session.scalars(select(User)).all() == []


def test_signing_in_again_reuses_the_user_and_org(
    client, mailbox, session, monkeypatch
):
    sign_in(client, mailbox)
    user = session.scalar(select(User))
    monkeypatch.setattr(accounts, "LOGIN_REQUEST_COOLDOWN_SECONDS", 0)
    sign_in(client, mailbox)
    session.expire_all()
    users = session.scalars(select(User)).all()
    assert [u.id for u in users] == [user.id]
    assert len(session.scalars(select(Org)).all()) == 1


def test_address_case_does_not_create_a_second_account(client, mailbox, session):
    sign_in(client, mailbox, "Anna@Example.COM")
    user = session.scalar(select(User))
    assert user.email == "anna@example.com"
    assert client.get("/api/me").json()["email"] == "anna@example.com"


# --- sessions ----------------------------------------------------------------


def test_me_without_a_session_is_401(client):
    assert client.get("/api/me").status_code == 401


def test_logout_drops_the_session(client, mailbox, session):
    sign_in(client, mailbox)
    assert client.post("/api/auth/logout").status_code == 200
    assert session.scalars(select(Session)).all() == []
    assert client.get("/api/me").status_code == 401


def test_logout_without_a_session_answers_the_same(client):
    assert client.post("/api/auth/logout").status_code == 200


def test_only_the_digest_of_the_session_token_is_stored(client, mailbox, session):
    sign_in(client, mailbox)
    cookie = client.cookies[accounts.SESSION_COOKIE]
    row = session.scalar(select(Session))
    assert row.token_hash == accounts._hash(cookie)
    assert cookie not in row.token_hash


def test_the_session_cookie_is_httponly_and_lax(client, mailbox):
    request_code(client)
    _, code = mailbox[0]
    header = client.post("/api/auth/code", json={"email": EMAIL, "code": code}).headers[
        "set-cookie"
    ]
    assert "HttpOnly" in header
    assert "SameSite=lax" in header


def test_the_session_cookie_is_secure_on_an_https_instance(
    client, mailbox, monkeypatch
):
    monkeypatch.setenv("BASE_URL", "https://app.klartex.se")
    request_code(client)
    _, code = mailbox[0]
    header = client.post("/api/auth/code", json={"email": EMAIL, "code": code}).headers[
        "set-cookie"
    ]
    assert "Secure" in header


def test_an_expired_session_does_not_authenticate(client, mailbox):
    sign_in(client, mailbox)
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("UPDATE sessions SET expires_at = now() - interval '1 day'")
    assert client.get("/api/me").status_code == 401


# --- housekeeping and configuration ------------------------------------------


def test_expired_rows_are_swept_by_the_public_endpoint(client, mailbox, session):
    sign_in(client, mailbox)
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("UPDATE sessions SET expires_at = now() - interval '1 day'")
        conn.execute("UPDATE login_tokens SET expires_at = now() - interval '1 day'")

    request_code(client, "someone-else@example.com")

    session.expire_all()
    assert session.scalars(select(Session)).all() == []
    remaining = session.scalars(select(LoginToken)).all()
    assert [row.email for row in remaining] == ["someone-else@example.com"]


def test_a_cross_origin_write_is_rejected(client):
    rejected = client.post(
        "/api/auth/request-code",
        json={"email": EMAIL},
        headers={"Origin": "https://evil.example"},
    )
    assert rejected.status_code == 403


def test_a_same_origin_write_passes(client, mailbox):
    assert (
        client.post(
            "/api/auth/request-code",
            json={"email": EMAIL},
            headers={"Origin": "http://testserver"},
        ).status_code
        == 200
    )


def test_a_malformed_origin_is_rejected_rather_than_crashing(client):
    """A port is parsed on access, and an unguarded parse would be a 500.

    The contract for a bad Origin is the same 403 a mismatched one gets;
    answering 500 instead would turn every cookie-write endpoint into a
    crash for anyone who sends a junk header.
    """
    rejected = client.post(
        "/api/auth/request-code",
        json={"email": EMAIL},
        headers={"Origin": "http://x:abc"},
    )
    assert rejected.status_code == 403


def test_the_sign_in_mail_verifies_the_smtp_server(monkeypatch):
    """STARTTLS without an explicit context verifies nothing.

    The context `starttls()` falls back to sets CERT_NONE and skips the
    hostname check, so anyone in the path could impersonate the SMTP
    server and read the credentials and every code that crosses it.
    """
    contexts = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context=None):
            contexts.append(context)

        def login(self, user, password):
            pass

        def send_message(self, message):
            pass

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_TLS", "true")
    monkeypatch.setattr(accounts.smtplib, "SMTP", FakeSMTP)

    accounts._send_code_email(EMAIL, "123456")

    assert len(contexts) == 1
    assert contexts[0].check_hostname is True
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED


def test_a_missing_origin_passes(client, mailbox):
    """curl and agents send none, and they are first-class callers here."""
    assert "origin" not in {k.lower() for k in request_code(client).request.headers}
    assert len(mailbox) == 1


def test_a_malformed_email_is_refused(client, mailbox):
    refused = client.post("/api/auth/request-code", json={"email": "nope"})
    assert refused.status_code == 422
    assert mailbox == []


def test_login_code_secret_is_required(monkeypatch):
    """No per-process fallback: it would break codes across restarts."""
    monkeypatch.delenv("LOGIN_CODE_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="LOGIN_CODE_SECRET"):
        accounts._require_login_code_secret()


def test_admin_status_comes_from_the_environment(monkeypatch, client, mailbox):
    monkeypatch.setenv("ADMIN_EMAILS", f" Other@example.com, {EMAIL.upper()} ")
    assert accounts.is_admin(EMAIL)
    assert not accounts.is_admin("stranger@example.com")
    sign_in(client, mailbox)
    assert client.get("/api/me").json()["admin"] is True


def test_no_admins_are_configured_by_default(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    assert accounts.admin_emails() == set()
    assert not accounts.is_admin(EMAIL)


def test_a_code_minted_under_another_secret_does_not_verify(
    client, mailbox, monkeypatch
):
    """The HMAC key is what makes a leaked table worthless."""
    request_code(client)
    _, code = mailbox[0]
    monkeypatch.setenv("LOGIN_CODE_SECRET", "a-different-secret")
    assert (
        client.post("/api/auth/code", json={"email": EMAIL, "code": code}).status_code
        == 400
    )


def test_the_code_expires_within_the_configured_window(client, mailbox, session):
    request_code(client)
    row = session.scalar(select(LoginToken))
    window = row.expires_at - datetime.now(UTC)
    assert timedelta(minutes=accounts.LOGIN_CODE_TTL_MINUTES) - window < timedelta(
        minutes=1
    )
