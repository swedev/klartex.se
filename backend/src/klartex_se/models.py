"""SQLAlchemy models for accounts: orgs, users, sign-in codes and sessions.

The schema is owned by alembic — `migrations/versions/0001_accounts.py`
writes the DDL by hand — and these classes mirror it so the application
layer has typed rows to work with. `tests/test_migrations.py` asserts that
the two still agree against a migrated database.

Nothing a caller could present as a credential is stored in the clear: a
sign-in code is kept as an HMAC keyed with `LOGIN_CODE_SECRET`, which lives
only in the environment, and a session token as a plain sha256. A leaked
table therefore yields digests, not working credentials.

Times are `timestamptz`, so every value carries its zone and comparisons
against `now()` mean the same thing in the database and in Python.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for the account tables."""


def _uuid_pk() -> Mapped[uuid.UUID]:
    """A uuid primary key the database fills in."""
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Org(Base):
    """An organisation — the unit a paired machine belongs to.

    First sign-in creates a one-person org for the new user, because
    `parla_machine.org_id` needs a real foreign-key target. Membership of
    several users in one org is not modelled yet; the schema does not
    stand in its way.
    """

    __tablename__ = "org"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class User(Base):
    """A person who can sign in.

    `email` is stored lowercased by the route layer, and the unique index
    over `lower(email)` holds that invariant in the database — so one
    address is one account however it was typed.

    Admin status is not a column: it is derived from the `ADMIN_EMAILS`
    environment variable, so the set of admins is server configuration
    that no database write can change.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("users_email_lower_idx", func.lower(text("email")), unique=True),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("org.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = _created_at()


class LoginToken(Base):
    """One outstanding sign-in code for an address.

    `email` is deliberately not a foreign key. `request-code` answers
    identically whether or not the address has an account, and a
    constraint violation would leak, through the error, exactly what those
    identical answers hide.

    At most one row per address is live at a time; the request route
    enforces that by serialising on the address rather than through a
    constraint here, so a rollback to an image that does not expect the
    constraint cannot leave sign-in broken for an address.
    """

    __tablename__ = "login_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text)
    # HMAC-sha256 of the six-digit code, keyed with LOGIN_CODE_SECRET.
    code_hash: Mapped[str] = mapped_column(Text)
    code_attempts: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), default=0
    )
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False
    )


class Session(Base):
    """A signed-in browser.

    The cookie carries the token; only its sha256 is stored, so the table
    identifies sessions without being able to impersonate them.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
