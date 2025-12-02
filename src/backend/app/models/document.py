"""
Document model - Tracks documents attached to opportunities.

Manages document metadata and processing status for PDFs, attachments,
and other files associated with procurement opportunities.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity


class DocumentType(str, enum.Enum):
    """Type of document."""
    
    RFP = "rfp"                     # Request for Proposal
    RFQ = "rfq"                     # Request for Quote
    RFI = "rfi"                     # Request for Information
    ADDENDUM = "addendum"           # Addendum/Amendment
    ATTACHMENT = "attachment"        # General attachment
    FORM = "form"                   # Required form
    SPECIFICATION = "specification"  # Technical specifications
    DRAWING = "drawing"             # Technical drawings
    CONTRACT = "contract"           # Sample/draft contract
    OTHER = "other"


class ProcessingStatus(str, enum.Enum):
    """Document processing status."""
    
    PENDING = "pending"             # Awaiting processing
    DOWNLOADING = "downloading"     # Currently downloading
    DOWNLOADED = "downloaded"       # Download complete
    PROCESSING = "processing"       # AI processing in progress
    PROCESSED = "processed"         # Processing complete
    FAILED = "failed"               # Processing failed
    SKIPPED = "skipped"             # Skipped (too large, unsupported, etc.)


class Document(Base, TimestampMixin):
    """
    Document attached to an opportunity.
    
    Tracks the document lifecycle from discovery through AI processing,
    with storage in SharePoint.
    """
    
    __tablename__ = "documents"
    
    # Opportunity Reference
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Document Information
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(
            DocumentType,
            name="documenttype",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=DocumentType.OTHER,
    )
    
    # Source URL
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    
    # Storage (SharePoint)
    storage_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Path in SharePoint",
    )
    sharepoint_item_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="SharePoint item ID",
    )
    
    # File Properties
    file_extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash for deduplication",
    )
    
    # Processing
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processingstatus",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ProcessingStatus.PENDING,
        index=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Extracted Content
    extracted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Text extracted from document",
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # AI Analysis
    ai_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI-generated document summary",
    )
    ai_analysis: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full AI analysis results",
    )
    
    # Document Metadata
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        comment="Additional document metadata",
    )
    
    # Flags
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Is this the main RFP document?",
    )
    
    # Relationships
    opportunity: Mapped["Opportunity"] = relationship(
        "Opportunity",
        back_populates="documents",
    )
    
    @property
    def file_size_mb(self) -> float | None:
        """Get file size in megabytes."""
        if self.file_size_bytes:
            return self.file_size_bytes / (1024 * 1024)
        return None
    
    def __repr__(self) -> str:
        return f"<Document(id={self.id}, name='{self.name}', status='{self.processing_status.value}')>"

