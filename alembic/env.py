"""Alembic env — reads Postgres URL from SPIDERFOOT_DATABASE_URL."""
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    from logging.config import fileConfig
    fileConfig(config.config_file_name)

DATABASE_URL = os.environ.get("SPIDERFOOT_DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError(
        "SPIDERFOOT_DATABASE_URL is not set — Alembic requires it"
    )
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = None  # raw-SQL migrations; no SQLAlchemy model autogenerate


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
