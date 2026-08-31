"""Alembic migrations, against a real Postgres.

Not SQLite. The schema this database will carry is Postgres-only —
parla's `PROVIDER_SQL`, `pg_advisory_xact_lock` around the login-code
cooldown, `uuid` primary keys — so a migration suite that passes against
another dialect proves nothing about the one production runs.

The suite skips itself unless `DATABASE_URL` points at a reachable
database, because it is destructive: every test starts from an empty
`public` schema. CI gives it a throwaway service container; locally it
wants a scratch database, never the one holding real rows.

`alembic current` is asserted here because it is exactly the deploy's
preflight: the new image resolves the running database's revision while
the old stack still serves, so a rollback across a migration fails before
production is taken down.
"""

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.environ.get("DATABASE_URL", "")


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


def alembic(*args: str) -> str:
    """Run the alembic CLI from backend/ and return its stdout.

    A subprocess rather than alembic's Python API: this is the command the
    Dockerfile, the deploy and the smoke test all run, so the test covers
    the same entrypoint they do — including that `alembic.ini` and
    `migrations/` are found from the working directory alone.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"
    return result.stdout


def revisions(output: str) -> list[str]:
    """The revision ids in `alembic current` / `alembic heads` output.

    Each line is `<id> (head)` or just `<id>`; an empty output means base
    — no revision applied, or none defined.
    """
    return sorted(line.split()[0] for line in output.splitlines() if line.strip())


@pytest.fixture
def empty_database():
    """Start from a database with nothing in it; leave it at head."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    yield
    alembic("upgrade", "head")


def test_upgrade_head_on_a_fresh_database(empty_database):
    """A brand-new install reaches head in one go."""
    alembic("upgrade", "head")
    assert revisions(alembic("current")) == revisions(alembic("heads"))


def test_downgrade_and_upgrade_again(empty_database):
    """Every revision defines a working way back down, and back up."""
    alembic("upgrade", "head")
    alembic("downgrade", "base")
    assert revisions(alembic("current")) == []
    alembic("upgrade", "head")
    assert revisions(alembic("current")) == revisions(alembic("heads"))


def test_current_resolves_before_the_first_migration(empty_database):
    """The deploy preflight answers against a database with no history."""
    assert revisions(alembic("current")) == []


def test_single_head():
    """One linear history — a branch would make `upgrade head` ambiguous."""
    assert len(revisions(alembic("heads"))) <= 1
