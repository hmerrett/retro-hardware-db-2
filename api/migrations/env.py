"""Alembic environment. Reuses the app's engine + metadata so migrations and the
running app always agree on the schema, and reads the URL from DATABASE_URL."""
from logging.config import fileConfig

from alembic import context

from app.db import Base, engine
# Import models so their tables register on Base.metadata for autogenerate.
from app import models
_ = models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=str(engine.url), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
