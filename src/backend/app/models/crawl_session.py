"""
CrawlSession model - Tracks individual crawl executions.

Provides detailed logging and metrics for each crawl run,
enabling monitoring and debugging of the crawling process.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.crawl_source import CrawlSource


class CrawlSessionStatus(str, enum.Enum):
    """Status of a crawl session."""
    
    PENDING = "pending"         # Scheduled but not started
    RUNNING = "running"         # Currently executing
    COMPLETED = "completed"     # Finished successfully
    FAILED = "failed"           # Finished with errors
    CANCELLED = "cancelled"     # Manually cancelled
    PARTIAL = "partial"         # Completed with some errors


class CrawlSession(Base, TimestampMixin):
    """
    Record of a single crawl execution.
    
    Tracks progress, metrics, and errors for each crawl run.
    Used for monitoring, debugging, and analytics.
    """
    
    __tablename__ = "crawl_sessions"
    
    # Source Reference
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Status
    status: Mapped[CrawlSessionStatus] = mapped_column(
        Enum(
            CrawlSessionStatus,
            name="crawlsessionstatus",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=CrawlSessionStatus.PENDING,
        index=True,
    )
    
    # Timing
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    # Metrics
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    opportunities_found: Mapped[int] = mapped_column(Integer, default=0)
    opportunities_new: Mapped[int] = mapped_column(
        Integer, 
        default=0,
        comment="New opportunities (not duplicates)",
    )
    opportunities_updated: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Existing opportunities with updates",
    )
    documents_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    
    # Error Tracking
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        comment="List of error details",
    )
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Trigger Information
    triggered_by: Mapped[str] = mapped_column(
        String(50),
        default="manual",
        comment="How crawl was triggered: manual, scheduled, api",
    )
    
    # Configuration Snapshot
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot of source config at crawl time",
    )
    
    # Progress Tracking
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        comment="Real-time progress data",
    )
    
    # Relationships
    source: Mapped["CrawlSource"] = relationship(
        "CrawlSource",
        back_populates="crawl_sessions",
    )
    
    @property
    def duration_seconds(self) -> float | None:
        """Calculate crawl duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def success_rate(self) -> float | None:
        """Calculate success rate (pages without errors)."""
        if self.pages_crawled > 0:
            return 1.0 - (self.errors_count / self.pages_crawled)
        return None
    
    def add_error(self, error_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        """Add an error to the session."""
        error_entry = {
            "type": error_type,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        }
        if not self.errors:
            self.errors = []
        self.errors.append(error_entry)
        self.errors_count += 1
        self.last_error_message = message
    
    def __repr__(self) -> str:
        return f"<CrawlSession(id={self.id}, source_id={self.source_id}, status='{self.status.value}')>"

