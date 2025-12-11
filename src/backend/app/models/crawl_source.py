"""
CrawlSource model - Configuration-driven source definitions.

This is the core model for dynamic source management. Each source
represents a crawlable endpoint (government portal, press release feed, etc.)
with its configuration stored in the database rather than hardcoded.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, Integer, String, Text, Float
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.crawl_session import CrawlSession
    from app.models.opportunity import Opportunity


class SourceType(str, enum.Enum):
    """Type of crawl source."""

    GOVERNMENT_PORTAL = "government_portal"
    PRESS_RELEASE = "press_release"
    CORPORATE_WEBSITE = "corporate_website"
    RSS_FEED = "rss_feed"
    API = "api"


class SourceStatus(str, enum.Enum):
    """Operational status of a crawl source."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class ProcessingStatus(str, enum.Enum):
    """Processing status for real-time crawl tracking."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class CrawlSource(Base, TimestampMixin):
    """
    Configuration for a crawlable data source.
    
    This model enables dynamic source management - new states, counties,
    or data sources can be added via database entries without code changes.
    
    Attributes:
        name: Human-readable source name (e.g., "California eProcure")
        source_type: Type of source (government_portal, press_release, etc.)
        state_code: Two-letter US state code (e.g., "CA", "TX")
        county: County name if applicable
        base_url: Base URL of the source
        config: JSON configuration for crawler (selectors, pagination, etc.)
        schedule_cron: Cron expression for scheduled crawls
        is_enabled: Whether this source should be crawled
    """
    
    __tablename__ = "crawl_sources"
    
    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(
            SourceType,
            name="sourcetype",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[SourceStatus] = mapped_column(
        Enum(
            SourceStatus,
            name="sourcestatus",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=SourceStatus.ACTIVE,
        nullable=False,
    )
    
    # Location
    state_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    county: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Source URLs
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    search_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Crawler Configuration (stored as JSONB for flexibility)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Crawler configuration: selectors, pagination, keywords, etc.",
    )
    
    # Authentication (if required)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    auth_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Authentication configuration (credentials stored in Key Vault)",
    )
    
    # Scheduling
    schedule_cron: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Cron expression for scheduled crawls (e.g., '0 6 * * *')",
    )
    crawl_delay: Mapped[float] = mapped_column(
        Float,
        default=2.0,
        comment="Delay between requests in seconds",
    )
    
    # Operational
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    priority: Mapped[int] = mapped_column(
        Integer,
        default=5,
        comment="Crawl priority (1=highest, 10=lowest)",
    )
    
    # Statistics
    last_crawl_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_opportunities_found: Mapped[int] = mapped_column(Integer, default=0)

    # Real-time processing status tracking
    processing_status: Mapped[ProcessingStatus | None] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processingstatusenum",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ProcessingStatus.PENDING,
        nullable=True,
        index=True,
    )
    last_crawl_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_crawl_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    processing_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Real-time progress tracking
    progress_percent: Mapped[int | None] = mapped_column(
        Integer,
        default=0,
        nullable=True,
        comment="Current crawl progress percentage (0-100)",
    )
    current_processing_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="URL currently being processed",
    )
    progress_message: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Human-readable progress message",
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    crawl_sessions: Mapped[list["CrawlSession"]] = relationship(
        "CrawlSession",
        back_populates="source",
        lazy="dynamic",
    )
    opportunities: Mapped[list["Opportunity"]] = relationship(
        "Opportunity",
        back_populates="source",
        lazy="dynamic",
    )
    
    def __repr__(self) -> str:
        return f"<CrawlSource(id={self.id}, name='{self.name}', state='{self.state_code}')>"

