"""The database module's configuration edges — no database needed.

Two properties matter before any table exists: `DATABASE_URL` reaches
SQLAlchemy in the psycopg3 dialect the backend actually ships, and the
app stays importable and live when no database is configured at all.
"""

import pytest
from fastapi.testclient import TestClient

from klartex_se import db
from klartex_se.main import app

client = TestClient(app)


def test_normalize_url_rewrites_the_bare_scheme():
    """SQLAlchemy's bare `postgresql://` means psycopg2, which is not shipped."""
    assert (
        db.normalize_url("postgresql://u:p@host:5432/klartex")
        == "postgresql+psycopg://u:p@host:5432/klartex"
    )


def test_normalize_url_leaves_an_explicit_dialect_alone():
    url = "postgresql+psycopg://u:p@host:5432/klartex"
    assert db.normalize_url(url) == url


def test_normalize_url_rewrites_only_the_scheme():
    """A password or database name containing the scheme is not a scheme."""
    url = "postgresql://u:postgresql://@host/db"
    assert url.count("postgresql+psycopg://") == 0
    assert db.normalize_url(url).count("postgresql+psycopg://") == 1


def test_sqlalchemy_url_without_configuration(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        db.sqlalchemy_url()


def test_health_answers_without_a_database(monkeypatch):
    """`/api/health` is liveness, not readiness.

    Docker restarts an unhealthy container, so a probe that failed while
    the database was down would take the whole backend with it.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.reset_engine()
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
