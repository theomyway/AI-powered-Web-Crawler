"""
Application settings model for persistent configuration.

Stores settings like scheduler configuration that can be updated from the frontend.
"""

from sqlalchemy import String, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AppSettings(Base, TimestampMixin):
    """
    Persistent application settings stored in database.
    
    Uses a key-value pattern with JSON value for flexibility.
    
    Attributes:
        key: Unique setting key (e.g., "scheduler_config")
        value: JSON value for the setting
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<AppSettings(key='{self.key}')>"

