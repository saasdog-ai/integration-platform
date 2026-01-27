from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from alembic import context

# Import your models and settings
from app.core.config import get_settings
from app.infrastructure.db.models import Base

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate support
target_metadata = Base.metadata

# Get database URL from settings
settings = get_settings()


def get_url() -> str:
    """Get database URL, converting async to sync for Alembic."""
    url = settings.database_url
    # Alembic needs sync driver - remove asyncpg
    return url.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with sync engine."""
    url = get_url()

    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
