"""
Schemas for CrawlSource configuration and API.

These schemas define the structure for configuration-driven crawling,
enabling dynamic source management without code changes.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.crawl_source import SourceStatus, SourceType


class SelectorConfig(BaseModel):
    """
    CSS/XPath selectors for extracting data from pages.
    
    Supports both CSS selectors and XPath expressions.
    """
    
    # List page selectors
    opportunity_list: str = Field(
        description="Selector for opportunity items on list page"
    )
    next_page: str | None = Field(
        default=None,
        description="Selector for next page button/link"
    )
    
    # Detail extraction
    title: str = Field(description="Selector for opportunity title")
    description: str | None = Field(default=None, description="Selector for description")
    deadline: str | None = Field(default=None, description="Selector for submission deadline")
    published_date: str | None = Field(default=None, description="Selector for published date")
    department: str | None = Field(default=None, description="Selector for department/agency")
    opportunity_id: str | None = Field(default=None, description="Selector for opportunity ID")
    estimated_value: str | None = Field(default=None, description="Selector for contract value")
    contact_info: str | None = Field(default=None, description="Selector for contact information")
    documents: str | None = Field(default=None, description="Selector for document links")
    
    # Optional custom selectors (stored as dict for flexibility)
    custom: dict[str, str] = Field(
        default_factory=dict,
        description="Additional custom selectors"
    )


class PaginationConfig(BaseModel):
    """Configuration for handling pagination on source sites."""
    
    type: str = Field(
        default="link",
        description="Pagination type: link, ajax, scroll, api"
    )
    max_pages: int = Field(default=10, ge=1, le=100, description="Maximum pages to crawl")
    page_param: str | None = Field(default=None, description="URL parameter for page number")
    items_per_page: int | None = Field(default=None, description="Items per page if known")
    wait_after_page: float = Field(default=1.0, ge=0, description="Seconds to wait after loading page")


class CrawlSourceConfig(BaseModel):
    """
    Complete crawler configuration for a source.
    
    This is stored in the `config` JSONB column of CrawlSource.
    """
    
    # Selectors
    selectors: SelectorConfig
    
    # Pagination
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    
    # Keywords for filtering opportunities
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords to filter relevant opportunities"
    )
    exclude_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords to exclude opportunities"
    )
    
    # Rendering
    requires_javascript: bool = Field(
        default=False,
        description="Whether page requires JavaScript rendering"
    )
    wait_for_selector: str | None = Field(
        default=None,
        description="Selector to wait for before scraping (JS pages)"
    )
    wait_timeout: int = Field(default=30, description="Timeout for waiting in seconds")
    
    # Date parsing
    date_format: str = Field(
        default="%m/%d/%Y",
        description="Date format used on the source site"
    )
    timezone: str = Field(default="America/Los_Angeles", description="Source timezone")
    
    # Request headers
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Custom headers for requests"
    )
    
    # Cookies
    cookies: dict[str, str] = Field(
        default_factory=dict,
        description="Cookies to send with requests"
    )


class CrawlSourceBase(BaseModel):
    """Base schema for CrawlSource."""
    
    name: str = Field(min_length=1, max_length=255)
    source_type: SourceType
    state_code: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    county: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    base_url: HttpUrl
    search_url: HttpUrl | None = None
    config: CrawlSourceConfig
    schedule_cron: str | None = Field(default=None, max_length=50)
    crawl_delay: float = Field(default=2.0, ge=0.5, le=30.0)
    is_enabled: bool = True
    priority: int = Field(default=5, ge=1, le=10)
    notes: str | None = None
    
    @field_validator("state_code")
    @classmethod
    def uppercase_state_code(cls, v: str) -> str:
        return v.upper()


class CrawlSourceCreate(CrawlSourceBase):
    """Schema for creating a new CrawlSource."""
    pass


class CrawlSourceUpdate(BaseModel):
    """Schema for updating a CrawlSource (partial update)."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source_type: SourceType | None = None
    status: SourceStatus | None = None
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    county: str | None = None
    region: str | None = None
    base_url: HttpUrl | None = None
    search_url: HttpUrl | None = None
    config: CrawlSourceConfig | None = None
    schedule_cron: str | None = None
    crawl_delay: float | None = Field(default=None, ge=0.5, le=30.0)
    is_enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = None


class CrawlSourceResponse(CrawlSourceBase):
    """Schema for CrawlSource API response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    status: SourceStatus
    requires_auth: bool
    last_crawl_at: datetime | None
    last_success_at: datetime | None
    last_error_message: str | None
    total_opportunities_found: int
    created_at: datetime
    updated_at: datetime

