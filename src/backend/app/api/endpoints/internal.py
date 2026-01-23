"""
Internal API endpoints for service-to-service communication.

These endpoints use API key authentication instead of Azure AD,
allowing the Azure Function to call back to the backend for
progress/status updates without needing OAuth tokens.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_internal_api_key, InternalServiceUser
from app.core.exceptions import EntityNotFoundException
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.crawl_source import CrawlSource, ProcessingStatus
from app.schemas.crawl_source import (
    CrawlSourceResponse,
    ProcessingStatusUpdate,
    ProgressUpdate,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
)


@router.patch("/sources/{source_id}/status", response_model=CrawlSourceResponse)
async def internal_update_source_status(
    source_id: UUID,
    data: ProcessingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _service: InternalServiceUser = Depends(verify_internal_api_key),
) -> CrawlSourceResponse:
    """
    Update the processing status of a crawl source (internal API).

    This endpoint is called by the Azure Function to report crawl completion.
    Uses API key authentication for service-to-service communication.
    """
    result = await db.execute(
        select(CrawlSource).where(CrawlSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise EntityNotFoundException("CrawlSource", str(source_id))

    # Update processing status
    source.processing_status = data.processing_status

    # Handle different status transitions
    if data.processing_status == ProcessingStatus.PROCESSING:
        if not source.last_crawl_started_at:
            source.last_crawl_started_at = datetime.utcnow()
    elif data.processing_status == ProcessingStatus.FAILED:
        source.last_crawl_completed_at = datetime.utcnow()
        source.processing_error_message = data.processing_error_message
        source.last_error_message = data.processing_error_message
        source.progress_percent = 0
        source.progress_message = None
        source.current_processing_url = None
    elif data.processing_status == ProcessingStatus.SUCCESS:
        source.last_crawl_completed_at = datetime.utcnow()
        source.last_success_at = datetime.utcnow()
        source.processing_error_message = None
        source.progress_percent = 0
        source.progress_message = None
        source.current_processing_url = None

    if data.opportunities_found is not None:
        source.total_opportunities_found = (
            source.total_opportunities_found + data.opportunities_found
        )

    await db.flush()
    await db.refresh(source)

    logger.info(
        "Source status updated via internal API",
        source_id=str(source_id),
        processing_status=data.processing_status.value,
    )

    return CrawlSourceResponse.model_validate(source)


@router.patch("/sources/{source_id}/progress", response_model=CrawlSourceResponse)
async def internal_update_source_progress(
    source_id: UUID,
    data: ProgressUpdate,
    db: AsyncSession = Depends(get_db),
    _service: InternalServiceUser = Depends(verify_internal_api_key),
) -> CrawlSourceResponse:
    """
    Update the real-time progress of a crawl source (internal API).

    This endpoint is called by the Azure Function during crawl processing
    to report granular progress updates. Uses API key authentication.
    """
    result = await db.execute(
        select(CrawlSource).where(CrawlSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise EntityNotFoundException("CrawlSource", str(source_id))

    source.progress_percent = data.progress_percent
    if data.progress_message is not None:
        source.progress_message = data.progress_message
    if data.current_processing_url is not None:
        source.current_processing_url = data.current_processing_url

    await db.flush()
    await db.refresh(source)

    logger.debug(
        "Source progress updated via internal API",
        source_id=str(source_id),
        progress_percent=data.progress_percent,
    )

    return CrawlSourceResponse.model_validate(source)

