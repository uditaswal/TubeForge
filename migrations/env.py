"""Alembic environment configured from TubeForge settings."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from tubeforge.core.config import load_settings
from tubeforge.db.models import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    """Allow tests and operators to pass an explicit transient database URL."""
    return context.get_x_argument(as_dictionary=True).get(
        "database_url", load_settings().database.url
    )


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
