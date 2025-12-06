"""
Data models for RFP extraction and classification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OpportunityCategory(str, Enum):
    """Target technology categories for classification."""
    DYNAMICS = "dynamics"           # Microsoft Dynamics 365/CRM
    AI = "ai"                       # Artificial Intelligence / ML
    IOT = "iot"                     # Internet of Things
    ERP = "erp"                     # Enterprise Resource Planning
    STAFF_AUGMENTATION = "staff_augmentation"  # IT Staffing
    CLOUD = "cloud"                 # Cloud services
    CYBERSECURITY = "cybersecurity" # Security services
    DATA_ANALYTICS = "data_analytics"  # BI/Analytics
    OTHER = "other"                 # Other technology
    NOT_RELEVANT = "not_relevant"   # Not in our target categories


@dataclass
class ExtractedRFP:
    """RFP data extracted from HTML page (Stage 1) and enriched in Stage 2."""
    document_id: str
    event_name: str
    document_url: str | None
    event_start_date: str | None
    response_due_date: str | None
    last_updated: str | None

    # Classification from Stage 1 (updated in Stage 2)
    is_relevant: bool = False
    predicted_category: OpportunityCategory = OpportunityCategory.NOT_RELEVANT
    classification_confidence: float = 0.0
    classification_reason: str = ""

    # Stage 2 enrichment fields
    requires_prequalification: bool = False
    prequalification_deadline: str | None = None
    prequalification_details: list[dict[str, Any]] = field(default_factory=list)
    eligibility_requirements: str | None = None
    certifications_required: list[str] = field(default_factory=list)
    estimated_value: float | None = None
    is_discretionary: bool = False
    contact_info: dict[str, str] | None = None
    scope_of_work: str | None = None


@dataclass
class DeepAnalysisResult:
    """Deep analysis result from Stage 2."""
    # Confirmed classification
    confirmed_category: OpportunityCategory
    category_confidence: float
    
    # Extracted details
    summary: str
    scope_of_work: str | None
    estimated_value: float | None
    
    # Pre-qualification
    requires_prequalification: bool
    prequalification_details: list[dict[str, Any]] = field(default_factory=list)
    
    # Eligibility
    eligibility_requirements: str | None = None
    certifications_required: list[str] = field(default_factory=list)
    
    # Discretionary
    is_discretionary: bool = False
    discretionary_reason: str | None = None
    
    # Contact
    contact_info: dict[str, str] | None = None
    
    # Deadlines
    submission_deadline: datetime | None = None
    prequalification_deadline: datetime | None = None
    
    # Raw AI response
    raw_analysis: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrawlResult:
    """Result of crawling a page (Stage 1)."""
    url: str
    success: bool
    html_content: str | None = None
    extracted_rfps: list[ExtractedRFP] = field(default_factory=list)
    relevant_count: int = 0
    total_count: int = 0
    error_message: str | None = None
    error_type: str | None = None  # Type of error (timeout, geo_blocked, bot_detected, etc.)
    crawl_duration_seconds: float = 0.0


@dataclass
class DocumentProcessingMessage:
    """Message sent to document processing queue."""
    crawl_session_id: str
    rfp: dict[str, Any]  # Serialized ExtractedRFP
    source_url: str
    state_code: str = "TN"  # Default to Tennessee for now

