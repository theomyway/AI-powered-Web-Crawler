"""
Alembic migration environment configuration.

Uses synchronous psycopg2 for migrations against Azure Cosmos DB PostgreSQL.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Add src/backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.db.base import Base

# Import all models to ensure they're registered with Base
from app.models import (
    CrawlSource,
    Opportunity,
    CrawlSession,
    Document,
    PrequalificationRequirement,
)

# Alembic Config object
config = context.config

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from settings, converted for sync driver."""
    settings = get_settings()
    url = str(settings.database_url)
    # Convert async driver to sync for Alembic
    if "+asyncpg" in url:
        url = url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://")
    return url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates SQL without connecting to database.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    url = get_url()

    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

