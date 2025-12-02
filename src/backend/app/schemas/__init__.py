"""
Pydantic schemas for API request/response validation.
"""

from app.schemas.common import (
    BaseSchema,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    IDResponse,
    PaginatedResponse,
    PaginationParams,
    StatsResponse,
    SuccessResponse,
    TimestampMixin,
)
from app.schemas.crawl_source import (
    CrawlSourceConfig,
    CrawlSourceCreate,
    CrawlSourceResponse,
    CrawlSourceUpdate,
    PaginationConfig,
    SelectorConfig,
)
from app.schemas.opportunity import (
    ContactInfo,
    DocumentResponse,
    OpportunityCreate,
    OpportunityFilters,
    OpportunityListItem,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
    PrequalificationResponse,
)

__all__ = [
    # Common
    "BaseSchema",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "IDResponse",
    "PaginatedResponse",
    "PaginationParams",
    "StatsResponse",
    "SuccessResponse",
    "TimestampMixin",
    # Crawl Source
    "CrawlSourceConfig",
    "CrawlSourceCreate",
    "CrawlSourceResponse",
    "CrawlSourceUpdate",
    "PaginationConfig",
    "SelectorConfig",
    # Opportunity
    "ContactInfo",
    "DocumentResponse",
    "OpportunityCreate",
    "OpportunityFilters",
    "OpportunityListItem",
    "OpportunityListResponse",
    "OpportunityResponse",
    "OpportunityUpdate",
    "PrequalificationResponse",
]

from app.schemas.crawl_source import (
    CrawlSourceCreate,
    CrawlSourceUpdate,
    CrawlSourceResponse,
    CrawlSourceConfig,
    SelectorConfig,
    PaginationConfig,
)
from app.schemas.opportunity import (
    OpportunityCreate,
    OpportunityUpdate,
    OpportunityResponse,
    OpportunityListResponse,
    OpportunityFilters,
)
from app.schemas.common import (
    PaginationParams,
    PaginatedResponse,
    HealthResponse,
    ErrorResponse,
)

__all__ = [
    # Crawl Source
    "CrawlSourceCreate",
    "CrawlSourceUpdate",
    "CrawlSourceResponse",
    "CrawlSourceConfig",
    "SelectorConfig",
    "PaginationConfig",
    # Opportunity
    "OpportunityCreate",
    "OpportunityUpdate",
    "OpportunityResponse",
    "OpportunityListResponse",
    "OpportunityFilters",
    # Common
    "PaginationParams",
    "PaginatedResponse",
    "HealthResponse",
    "ErrorResponse",
]

