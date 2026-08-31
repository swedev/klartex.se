"""Alembic runtime config.

The URL comes from `klartex_se.db`, so alembic and the app always reach
the same database from the same `DATABASE_URL` — no per-environment
alembic profiles, and the psycopg3 dialect rewrite happens in one place.

Autogenerate is not used: every revision is written by hand, so
`target_metadata` stays None.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from klartex_se.db import sqlalchemy_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: emit SQL to stdout."""
    context.configure(
        url=sqlalchemy_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        {"sqlalchemy.url": sqlalchemy_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
