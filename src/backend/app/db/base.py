"""
SQLAlchemy declarative base and common model utilities.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    
    Provides common attributes and table naming conventions.
    """
    
    # Use UUID as primary key for all models
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name from class name (snake_case)."""
        name = cls.__name__
        # Convert CamelCase to snake_case
        result = [name[0].lower()]
        for char in name[1:]:
            if char.isupper():
                result.append("_")
                result.append(char.lower())
            else:
                result.append(char)
        return "".join(result)


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at timestamps.
    """
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Mixin that adds soft delete capability.
    """
    
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    
    @property
    def is_deleted(self) -> bool:
        """Check if record is soft-deleted."""
        return self.deleted_at is not None


def model_to_dict(model: Base, exclude: set[str] | None = None) -> dict[str, Any]:
    """
    Convert SQLAlchemy model to dictionary.
    
    Args:
        model: SQLAlchemy model instance
        exclude: Set of column names to exclude
        
    Returns:
        Dictionary representation of the model
    """
    exclude = exclude or set()
    result = {}
    
    for column in model.__table__.columns:
        if column.name not in exclude:
            value = getattr(model, column.name)
            # Handle UUID serialization
            if isinstance(value, uuid.UUID):
                value = str(value)
            # Handle datetime serialization
            elif isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
    
    return result

