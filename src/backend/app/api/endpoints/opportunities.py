"""
Opportunity management endpoints.

Provides CRUD operations for managing identified procurement opportunities
with filtering, search, and status tracking.
"""

from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import EntityNotFoundException
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.opportunity import Opportunity, OpportunityStatus
from app.schemas.opportunity import (
    OpportunityFilters,
    OpportunityListItem,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
)

logger = get_logger(__name__)
router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    db: DB,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: list[OpportunityStatus] | None = Query(default=None),
    categories: list[str] | None = Query(default=None),
    state_codes: list[str] | None = Query(default=None),
    requires_prequalification: bool | None = None,
    is_discretionary: bool | None = None,
    deadline_after: datetime | None = None,
    deadline_before: datetime | None = None,
    search: str | None = Query(default=None, max_length=200),
    source_id: UUID | None = None,
    sort_by: str = Query(default="created_at", regex="^(created_at|deadline|relevance|title)$"),
    sort_order: str = Query(default="desc", regex="^(asc|desc)$"),
) -> OpportunityListResponse:
    """
    List opportunities with comprehensive filtering.
    
    Supports filtering by status, category, state, prequalification,
    deadlines, and full-text search.
    """
    # Build base query
    query = select(Opportunity).where(Opportunity.deleted_at.is_(None))
    count_query = select(func.count(Opportunity.id)).where(Opportunity.deleted_at.is_(None))
    
    # Apply filters
    if status:
        query = query.where(Opportunity.status.in_(status))
        count_query = count_query.where(Opportunity.status.in_(status))
    
    if categories:
        # PostgreSQL array overlap operator
        query = query.where(Opportunity.categories.overlap(categories))
        count_query = count_query.where(Opportunity.categories.overlap(categories))
    
    if state_codes:
        upper_codes = [s.upper() for s in state_codes]
        query = query.where(Opportunity.state_code.in_(upper_codes))
        count_query = count_query.where(Opportunity.state_code.in_(upper_codes))
    
    if requires_prequalification is not None:
        query = query.where(Opportunity.requires_prequalification == requires_prequalification)
        count_query = count_query.where(Opportunity.requires_prequalification == requires_prequalification)
    
    if is_discretionary is not None:
        query = query.where(Opportunity.is_discretionary == is_discretionary)
        count_query = count_query.where(Opportunity.is_discretionary == is_discretionary)
    
    if deadline_after:
        query = query.where(Opportunity.submission_deadline >= deadline_after)
        count_query = count_query.where(Opportunity.submission_deadline >= deadline_after)
    
    if deadline_before:
        query = query.where(Opportunity.submission_deadline <= deadline_before)
        count_query = count_query.where(Opportunity.submission_deadline <= deadline_before)
    
    if source_id:
        query = query.where(Opportunity.source_id == source_id)
        count_query = count_query.where(Opportunity.source_id == source_id)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Opportunity.title.ilike(search_pattern),
                Opportunity.description.ilike(search_pattern),
            )
        )
        count_query = count_query.where(
            or_(
                Opportunity.title.ilike(search_pattern),
                Opportunity.description.ilike(search_pattern),
            )
        )
    
    # Get total
    total = await db.scalar(count_query) or 0
    
    # Apply sorting
    sort_column = getattr(Opportunity, sort_by if sort_by != "deadline" else "submission_deadline")
    if sort_order == "desc":
        query = query.order_by(sort_column.desc().nulls_last())
    else:
        query = query.order_by(sort_column.asc().nulls_last())
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    opportunities = result.scalars().all()

    # Build response with document count and primary category
    items = []
    for opp in opportunities:
        # Get primary category (first from categories array)
        primary_category = opp.categories[0] if opp.categories else None

        item = OpportunityListItem(
            id=opp.id,
            title=opp.title,
            source_id=opp.source_id,
            source_url=opp.source_url,
            state_code=opp.state_code,
            county=opp.county,
            category=primary_category,
            categories=opp.categories or [],
            status=opp.status,
            submission_deadline=opp.submission_deadline,
            estimated_value=opp.estimated_value,
            requires_prequalification=opp.requires_prequalification,
            is_discretionary=opp.is_discretionary,
            relevance_score=opp.relevance_score,
            published_date=opp.published_date,
            document_count=0,  # Will be populated via relationship count
            created_at=opp.created_at,
        )
        items.append(item)
    
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    return OpportunityListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(db: DB, opportunity_id: UUID) -> OpportunityResponse:
    """Get detailed information about a specific opportunity."""
    result = await db.execute(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id, Opportunity.deleted_at.is_(None))
        .options(
            selectinload(Opportunity.documents),
            selectinload(Opportunity.prequalification_requirements),
        )
    )
    opportunity = result.scalar_one_or_none()
    
    if not opportunity:
        raise EntityNotFoundException("Opportunity", str(opportunity_id))
    
    return OpportunityResponse.model_validate(opportunity)


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    db: DB,
    opportunity_id: UUID,
    data: OpportunityUpdate,
) -> OpportunityResponse:
    """Update opportunity details (status, notes, etc.)."""
    result = await db.execute(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id, Opportunity.deleted_at.is_(None))
        .options(
            selectinload(Opportunity.documents),
            selectinload(Opportunity.prequalification_requirements),
        )
    )
    opportunity = result.scalar_one_or_none()
    
    if not opportunity:
        raise EntityNotFoundException("Opportunity", str(opportunity_id))
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "contact_info" and value:
            setattr(opportunity, field, value.model_dump())
        else:
            setattr(opportunity, field, value)
    
    await db.flush()
    await db.refresh(opportunity)
    
    logger.info("Opportunity updated", opportunity_id=str(opportunity_id), fields=list(update_data.keys()))
    
    return OpportunityResponse.model_validate(opportunity)

