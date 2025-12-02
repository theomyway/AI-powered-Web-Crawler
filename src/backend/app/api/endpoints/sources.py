"""
Crawl Source management endpoints.

Provides CRUD operations for managing crawl sources (government portals,
press release feeds, etc.) through configuration-driven approach.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEntityException, EntityNotFoundException
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.crawl_source import CrawlSource, SourceStatus, SourceType
from app.schemas.crawl_source import (
    CrawlSourceCreate,
    CrawlSourceResponse,
    CrawlSourceUpdate,
)
from app.schemas.common import PaginatedResponse, SuccessResponse

logger = get_logger(__name__)
router = APIRouter()

# Type alias for database dependency
DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=PaginatedResponse[CrawlSourceResponse])
async def list_sources(
    db: DB,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source_type: SourceType | None = None,
    state_code: str | None = None,
    status: SourceStatus | None = None,
    is_enabled: bool | None = None,
) -> PaginatedResponse[CrawlSourceResponse]:
    """
    List all crawl sources with optional filtering.
    
    Supports filtering by source type, state, status, and enabled flag.
    """
    # Build query
    query = select(CrawlSource)
    count_query = select(func.count(CrawlSource.id))
    
    # Apply filters
    if source_type:
        query = query.where(CrawlSource.source_type == source_type)
        count_query = count_query.where(CrawlSource.source_type == source_type)
    if state_code:
        query = query.where(CrawlSource.state_code == state_code.upper())
        count_query = count_query.where(CrawlSource.state_code == state_code.upper())
    if status:
        query = query.where(CrawlSource.status == status)
        count_query = count_query.where(CrawlSource.status == status)
    if is_enabled is not None:
        query = query.where(CrawlSource.is_enabled == is_enabled)
        count_query = count_query.where(CrawlSource.is_enabled == is_enabled)
    
    # Get total count
    total = await db.scalar(count_query) or 0
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(CrawlSource.priority, CrawlSource.name)
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    sources = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[CrawlSourceResponse.model_validate(s) for s in sources],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{source_id}", response_model=CrawlSourceResponse)
async def get_source(db: DB, source_id: UUID) -> CrawlSourceResponse:
    """Get a specific crawl source by ID."""
    result = await db.execute(
        select(CrawlSource).where(CrawlSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise EntityNotFoundException("CrawlSource", str(source_id))
    
    return CrawlSourceResponse.model_validate(source)


@router.post("", response_model=CrawlSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(db: DB, data: CrawlSourceCreate) -> CrawlSourceResponse:
    """
    Create a new crawl source.
    
    The source configuration defines how the crawler will extract
    opportunities from the target website.
    """
    # Check for duplicate name + state combination
    existing = await db.execute(
        select(CrawlSource).where(
            CrawlSource.name == data.name,
            CrawlSource.state_code == data.state_code,
        )
    )
    if existing.scalar_one_or_none():
        raise DuplicateEntityException("CrawlSource", "name+state", f"{data.name} ({data.state_code})")
    
    source = CrawlSource(
        name=data.name,
        source_type=data.source_type,
        state_code=data.state_code,
        county=data.county,
        region=data.region,
        base_url=str(data.base_url),
        search_url=str(data.search_url) if data.search_url else None,
        config=data.config.model_dump(),
        schedule_cron=data.schedule_cron,
        crawl_delay=data.crawl_delay,
        is_enabled=data.is_enabled,
        priority=data.priority,
        notes=data.notes,
    )
    
    db.add(source)
    await db.flush()
    await db.refresh(source)
    
    logger.info("Crawl source created", source_id=str(source.id), name=source.name)
    
    return CrawlSourceResponse.model_validate(source)


@router.patch("/{source_id}", response_model=CrawlSourceResponse)
async def update_source(db: DB, source_id: UUID, data: CrawlSourceUpdate) -> CrawlSourceResponse:
    """Update an existing crawl source."""
    result = await db.execute(
        select(CrawlSource).where(CrawlSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise EntityNotFoundException("CrawlSource", str(source_id))
    
    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "config" and value:
            setattr(source, field, value.model_dump())
        elif field in ("base_url", "search_url") and value:
            setattr(source, field, str(value))
        else:
            setattr(source, field, value)
    
    await db.flush()
    await db.refresh(source)
    
    logger.info("Crawl source updated", source_id=str(source_id))
    
    return CrawlSourceResponse.model_validate(source)


@router.delete("/{source_id}", response_model=SuccessResponse)
async def delete_source(db: DB, source_id: UUID) -> SuccessResponse:
    """Delete a crawl source."""
    result = await db.execute(
        select(CrawlSource).where(CrawlSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise EntityNotFoundException("CrawlSource", str(source_id))
    
    await db.delete(source)
    logger.info("Crawl source deleted", source_id=str(source_id))
    
    return SuccessResponse(message=f"Source '{source.name}' deleted successfully")

