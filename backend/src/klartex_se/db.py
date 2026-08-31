"""Database engine and session factory.

`DATABASE_URL` is the single source for where the database lives; dev,
CI and production each point it at their own. The bare `postgresql://`
scheme is rewritten to `postgresql+psycopg://` because this backend
ships psycopg3, while SQLAlchemy's bare scheme still resolves to
psycopg2.

The engine is built on first use rather than at import time. `/api/health`
is a liveness probe — it answers that this process is up, not that the
database is reachable — so importing the app must never depend on a
database being configured or running. A caller that actually needs a
session gets the failure, and only then.
"""

import os
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def sqlalchemy_url() -> str:
    """The configured URL, in the dialect form SQLAlchemy needs.

    Raises `RuntimeError` when `DATABASE_URL` is unset, so a missing
    configuration surfaces where a session is requested rather than as an
    obscure connection error later.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set — the backend needs a database for "
            "accounts and connections. See infra/.env.example."
        )
    return normalize_url(url)


def normalize_url(url: str) -> str:
    """Rewrite `postgresql://` to the psycopg3 dialect SQLAlchemy needs."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine() -> Engine:
    """The process-wide engine, created on first use."""
    global _engine
    if _engine is None:
        # pool_pre_ping because the database restarts independently of this
        # process — a deploy migrates with the backend stopped, and pooled
        # connections from before it must not be handed out afterwards.
        _engine = create_engine(sqlalchemy_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """The process-wide session factory, created on first use."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that commits or rolls back."""
    with get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def reset_engine() -> None:
    """Drop the cached engine and factory.

    Tests point `DATABASE_URL` at different databases within one process;
    without this they would keep talking to the first one.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
