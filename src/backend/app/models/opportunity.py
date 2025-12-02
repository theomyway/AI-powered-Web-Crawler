"""
Opportunity model - Core entity for procurement opportunities.

Stores identified opportunities from government portals and press releases
with AI-powered classification and prequalification detection.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.crawl_source import CrawlSource
    from app.models.document import Document
    from app.models.prequalification import PrequalificationRequirement


class OpportunityStatus(str, enum.Enum):
    """Lifecycle status of an opportunity."""

    NEW = "new"                     # Just discovered
    REVIEWING = "reviewing"         # Under review
    QUALIFIED = "qualified"         # Meets criteria, worth pursuing
    NOT_RELEVANT = "not_relevant"   # Doesn't meet criteria
    APPLIED = "applied"             # Application submitted
    WON = "won"                     # Contract awarded
    LOST = "lost"                   # Not selected
    EXPIRED = "expired"             # Deadline passed
    ARCHIVED = "archived"           # Manually archived


class OpportunityCategory(str, enum.Enum):
    """Technology category classification."""
    
    DYNAMICS = "dynamics"           # Microsoft Dynamics 365/CRM
    AI = "ai"                       # Artificial Intelligence / ML
    IOT = "iot"                     # Internet of Things
    ERP = "erp"                     # Enterprise Resource Planning
    STAFF_AUGMENTATION = "staff_augmentation"  # IT Staffing
    CLOUD = "cloud"                 # Cloud services
    CYBERSECURITY = "cybersecurity" # Security services
    DATA_ANALYTICS = "data_analytics"  # BI/Analytics
    OTHER = "other"                 # Other technology


class Opportunity(Base, TimestampMixin, SoftDeleteMixin):
    """
    A procurement opportunity identified by the crawler.
    
    Contains all information about the opportunity including AI-generated
    classifications, prequalification requirements, and tracking status.
    """
    
    __tablename__ = "opportunities"
    
    # Source Reference
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_opportunity_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Original opportunity ID from source system",
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    
    # Basic Information
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI-generated summary",
    )
    
    # Location
    state_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    county: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Classification (AI-generated)
    categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)),
        default=list,
        comment="AI-classified technology categories",
    )
    relevance_score: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
        comment="AI relevance score 0.00-1.00",
    )
    
    # Dates
    published_date: Mapped[datetime | None] = mapped_column(nullable=True)
    submission_deadline: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    
    # Value
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    value_currency: Mapped[str] = mapped_column(String(3), default="USD")
    
    # Prequalification
    requires_prequalification: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    prequalification_deadline: Mapped[datetime | None] = mapped_column(nullable=True)
    
    # Discretionary Flag
    is_discretionary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Small/discretionary purchase with simplified process",
    )
    
    # Contact Information
    contact_info: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Contact name, email, phone",
    )
    
    # Eligibility
    eligibility_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    certifications_required: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)),
        default=list,
    )
    
    # Tracking
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(
            OpportunityStatus,
            name="opportunitystatus",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=OpportunityStatus.NEW,
        index=True,
    )
    
    # Metadata
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Original scraped data for debugging",
    )
    ai_analysis: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full AI analysis results",
    )
    
    # Notes
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    source: Mapped["CrawlSource"] = relationship(
        "CrawlSource",
        back_populates="opportunities",
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    prequalification_requirements: Mapped[list["PrequalificationRequirement"]] = relationship(
        "PrequalificationRequirement",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Opportunity(id={self.id}, title='{self.title[:50]}...', state='{self.state_code}')>"

