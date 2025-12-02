"""
Crawl operation endpoints.

Provides endpoints for triggering crawls, monitoring progress,
and viewing crawl history.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ValidationException
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.crawl_session import CrawlSession, CrawlSessionStatus
from app.models.crawl_source import CrawlSource, SourceStatus
from app.schemas.common import PaginatedResponse, SuccessResponse

logger = get_logger(__name__)
router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


# Response schemas for crawl operations
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Any


class CrawlSessionResponse(BaseModel):
    """Response schema for crawl session."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    source_id: UUID
    status: CrawlSessionStatus
    started_at: datetime | None
    completed_at: datetime | None
    pages_crawled: int
    opportunities_found: int
    opportunities_new: int
    opportunities_updated: int
    documents_downloaded: int
    errors_count: int
    last_error_message: str | None
    triggered_by: str
    progress: dict[str, Any]
    created_at: datetime


class CrawlTriggerResponse(BaseModel):
    """Response for crawl trigger request."""
    
    session_id: UUID
    source_id: UUID
    source_name: str
    status: str
    message: str


@router.post("/trigger/{source_id}", response_model=CrawlTriggerResponse)
async def trigger_crawl(
    db: DB,
    source_id: UUID,
    background_tasks: BackgroundTasks,
) -> CrawlTriggerResponse:
    """
    Trigger a crawl for a specific source.
    
    Creates a new crawl session and starts the crawl in the background.
    """
    # Get source
    result = await db.execute(
        select(CrawlSource).where(CrawlSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise EntityNotFoundException("CrawlSource", str(source_id))
    
    if not source.is_enabled:
        raise ValidationException(
            message="Cannot trigger crawl for disabled source",
            field_errors={"source_id": ["Source is disabled"]},
        )
    
    if source.status == SourceStatus.MAINTENANCE:
        raise ValidationException(
            message="Source is under maintenance",
            field_errors={"source_id": ["Source is in maintenance mode"]},
        )
    
    # Check for existing running session
    running_session = await db.execute(
        select(CrawlSession).where(
            CrawlSession.source_id == source_id,
            CrawlSession.status == CrawlSessionStatus.RUNNING,
        )
    )
    if running_session.scalar_one_or_none():
        raise ValidationException(
            message="A crawl is already running for this source",
            field_errors={"source_id": ["Active crawl session exists"]},
        )
    
    # Create new session
    session = CrawlSession(
        source_id=source_id,
        status=CrawlSessionStatus.PENDING,
        triggered_by="api",
        config_snapshot=source.config,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    
    logger.info(
        "Crawl triggered",
        session_id=str(session.id),
        source_id=str(source_id),
        source_name=source.name,
    )
    
    # TODO: Add background task to start actual crawl
    # background_tasks.add_task(execute_crawl, session.id)
    
    return CrawlTriggerResponse(
        session_id=session.id,
        source_id=source_id,
        source_name=source.name,
        status="pending",
        message=f"Crawl session created for '{source.name}'. Processing will begin shortly.",
    )


@router.get("/sessions", response_model=PaginatedResponse[CrawlSessionResponse])
async def list_crawl_sessions(
    db: DB,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source_id: UUID | None = None,
    status: CrawlSessionStatus | None = None,
) -> PaginatedResponse[CrawlSessionResponse]:
    """List crawl sessions with optional filtering."""
    query = select(CrawlSession)
    count_query = select(func.count(CrawlSession.id))
    
    if source_id:
        query = query.where(CrawlSession.source_id == source_id)
        count_query = count_query.where(CrawlSession.source_id == source_id)
    
    if status:
        query = query.where(CrawlSession.status == status)
        count_query = count_query.where(CrawlSession.status == status)
    
    total = await db.scalar(count_query) or 0
    
    offset = (page - 1) * page_size
    query = query.order_by(CrawlSession.created_at.desc())
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    sessions = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[CrawlSessionResponse.model_validate(s) for s in sessions],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sessions/{session_id}", response_model=CrawlSessionResponse)
async def get_crawl_session(db: DB, session_id: UUID) -> CrawlSessionResponse:
    """Get details of a specific crawl session."""
    result = await db.execute(
        select(CrawlSession).where(CrawlSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise EntityNotFoundException("CrawlSession", str(session_id))
    
    return CrawlSessionResponse.model_validate(session)


@router.post("/sessions/{session_id}/cancel", response_model=SuccessResponse)
async def cancel_crawl_session(db: DB, session_id: UUID) -> SuccessResponse:
    """Cancel a running crawl session."""
    result = await db.execute(
        select(CrawlSession).where(CrawlSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise EntityNotFoundException("CrawlSession", str(session_id))
    
    if session.status not in (CrawlSessionStatus.PENDING, CrawlSessionStatus.RUNNING):
        raise ValidationException(
            message="Cannot cancel session that is not running",
            field_errors={"session_id": [f"Session status is {session.status.value}"]},
        )
    
    session.status = CrawlSessionStatus.CANCELLED
    session.completed_at = datetime.utcnow()
    await db.flush()
    
    logger.info("Crawl session cancelled", session_id=str(session_id))
    
    return SuccessResponse(message="Crawl session cancelled successfully")

