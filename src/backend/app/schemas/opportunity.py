"""
Schemas for Opportunity API.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.opportunity import OpportunityCategory, OpportunityStatus


class ContactInfo(BaseModel):
    """Contact information schema."""
    
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    department: str | None = None


class OpportunityBase(BaseModel):
    """Base schema for Opportunity."""
    
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    source_url: HttpUrl
    source_opportunity_id: str | None = None
    state_code: str = Field(min_length=2, max_length=2)
    county: str | None = None
    city: str | None = None
    categories: list[str] = Field(default_factory=list)
    published_date: datetime | None = None
    submission_deadline: datetime | None = None
    estimated_value: Decimal | None = None
    value_currency: str = "USD"
    requires_prequalification: bool = False
    prequalification_deadline: datetime | None = None
    is_discretionary: bool = False
    contact_info: ContactInfo | None = None
    eligibility_requirements: str | None = None
    certifications_required: list[str] = Field(default_factory=list)


class OpportunityCreate(OpportunityBase):
    """Schema for creating a new Opportunity."""
    
    source_id: UUID


class OpportunityUpdate(BaseModel):
    """Schema for updating an Opportunity (partial update)."""
    
    model_config = ConfigDict(extra="forbid")
    
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: OpportunityStatus | None = None
    categories: list[str] | None = None
    relevance_score: Decimal | None = Field(default=None, ge=0, le=1)
    submission_deadline: datetime | None = None
    estimated_value: Decimal | None = None
    requires_prequalification: bool | None = None
    prequalification_deadline: datetime | None = None
    is_discretionary: bool | None = None
    contact_info: ContactInfo | None = None
    eligibility_requirements: str | None = None
    certifications_required: list[str] | None = None
    internal_notes: str | None = None


class DocumentResponse(BaseModel):
    """Schema for Document in opportunity response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    document_type: str
    source_url: str
    storage_path: str | None
    file_extension: str | None
    file_size_bytes: int | None
    processing_status: str
    ai_summary: str | None


class PrequalificationResponse(BaseModel):
    """Schema for PrequalificationRequirement in opportunity response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    requirement_type: str
    name: str
    description: str | None
    deadline: datetime | None
    registration_url: str | None
    portal_name: str | None
    is_mandatory: bool
    is_completed: bool


class OpportunityResponse(OpportunityBase):
    """Schema for Opportunity API response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    source_id: UUID
    summary: str | None
    relevance_score: Decimal | None
    status: OpportunityStatus
    ai_analysis: dict[str, Any] | None
    internal_notes: str | None
    created_at: datetime
    updated_at: datetime
    documents: list[DocumentResponse] = Field(default_factory=list)
    prequalification_requirements: list[PrequalificationResponse] = Field(default_factory=list)


class OpportunityListItem(BaseModel):
    """Lightweight schema for opportunity list view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source_id: UUID
    source_url: str
    state_code: str
    county: str | None
    category: str | None = None  # Primary category (first from categories array)
    categories: list[str]
    status: OpportunityStatus
    submission_deadline: datetime | None
    estimated_value: Decimal | None
    requires_prequalification: bool
    is_discretionary: bool
    relevance_score: Decimal | None
    published_date: datetime | None = None
    document_count: int = 0
    created_at: datetime


class OpportunityListResponse(BaseModel):
    """Paginated list of opportunities."""
    
    items: list[OpportunityListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class OpportunityFilters(BaseModel):
    """Filters for opportunity list endpoint."""
    
    status: list[OpportunityStatus] | None = None
    categories: list[str] | None = None
    state_codes: list[str] | None = None
    county: str | None = None
    requires_prequalification: bool | None = None
    is_discretionary: bool | None = None
    min_relevance_score: Decimal | None = Field(default=None, ge=0, le=1)
    deadline_after: datetime | None = None
    deadline_before: datetime | None = None
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    search: str | None = Field(default=None, max_length=200)
    source_id: UUID | None = None

