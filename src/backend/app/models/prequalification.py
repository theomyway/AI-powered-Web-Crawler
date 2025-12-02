"""
PrequalificationRequirement model - Tracks prequalification/registration requirements.

Stores detailed information about vendor registration and prequalification
requirements detected by the AI for each opportunity.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity


class PrequalificationRequirement(Base, TimestampMixin):
    """
    Prequalification or registration requirement for an opportunity.
    
    AI-detected requirements for vendor registration, certifications,
    or other prerequisites needed to submit a bid.
    """
    
    __tablename__ = "prequalification_requirements"
    
    # Opportunity Reference
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Requirement Type
    requirement_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type: vendor_registration, certification, insurance, bond, etc.",
    )
    
    # Description
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Deadline
    deadline: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Deadline for completing this requirement",
    )
    
    # Registration Portal
    registration_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="URL to registration portal",
    )
    portal_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Name of registration system (e.g., SAM.gov, State portal)",
    )
    
    # Status
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Has MazikUSA completed this requirement?",
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    # Additional Details
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        comment="Additional requirement details",
    )
    
    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # AI Confidence
    ai_confidence: Mapped[float | None] = mapped_column(
        nullable=True,
        comment="AI confidence in this detection (0.0-1.0)",
    )
    
    # Relationships
    opportunity: Mapped["Opportunity"] = relationship(
        "Opportunity",
        back_populates="prequalification_requirements",
    )
    
    @property
    def days_until_deadline(self) -> int | None:
        """Calculate days remaining until deadline."""
        if self.deadline:
            delta = self.deadline - datetime.utcnow()
            return delta.days
        return None
    
    @property
    def is_urgent(self) -> bool:
        """Check if deadline is within 7 days."""
        days = self.days_until_deadline
        return days is not None and days <= 7
    
    def __repr__(self) -> str:
        return f"<PrequalificationRequirement(id={self.id}, type='{self.requirement_type}', name='{self.name}')>"

