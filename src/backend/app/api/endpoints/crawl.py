"""
Crawl operation endpoints.

Provides endpoints for triggering crawls, monitoring progress,
and viewing crawl history.

Supports both:
1. Source-based crawling (using pre-configured CrawlSource)
2. URL-based crawling (direct URL input from RFP Scanner UI)
"""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.core.config import get_settings
from app.core.exceptions import EntityNotFoundException, ValidationException
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.crawl_session import CrawlSession, CrawlSessionStatus
from app.models.crawl_source import CrawlSource, ProcessingStatus, SourceStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.schemas.common import PaginatedResponse, SuccessResponse

logger = get_logger(__name__)
router = APIRouter()
settings = get_settings()

DB = Annotated[AsyncSession, Depends(get_db)]


# Response schemas for crawl operations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
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


class UrlCrawlRequest(BaseModel):
    """Request schema for URL-based crawl."""

    urls: list[str] = Field(..., min_length=1, max_length=10, description="URLs to crawl")
    categories: list[str] = Field(default=[], description="Target categories to filter")


class ExtractedOpportunity(BaseModel):
    """Extracted opportunity from crawl."""

    document_id: str
    event_name: str
    document_url: str | None = None
    event_start_date: str | None = None
    response_due_date: str | None = None
    last_updated: str | None = None
    is_relevant: bool
    predicted_category: str
    classification_confidence: float
    classification_reason: str


class UrlCrawlResult(BaseModel):
    """Result of crawling a URL."""

    url: str
    success: bool
    total_found: int = 0
    relevant_count: int = 0
    opportunities: list[ExtractedOpportunity] = []
    error: str | None = None
    crawl_duration: float | None = None


class UrlCrawlResponse(BaseModel):
    """Response for URL-based crawl."""

    success: bool
    crawl_session_id: str
    results: list[UrlCrawlResult] = []
    total_relevant: int = 0
    saved_to_db: int = 0
    message: str | None = None
    error: str | None = None


@router.post("/scan-urls", response_model=UrlCrawlResponse)
async def scan_urls(
    db: DB,
    request: UrlCrawlRequest,
    background_tasks: BackgroundTasks,
) -> UrlCrawlResponse:
    """
    Scan URLs for RFP opportunities.

    This endpoint:
    1. Fetches HTML from provided URLs using Playwright
    2. Uses Azure OpenAI GPT-4o to extract and classify RFPs
    3. Saves relevant opportunities to the database

    If Azure Function is configured, it calls the Function.
    Otherwise, it runs the crawl locally.
    """
    crawl_session_id = str(uuid4())
    logger.info(
        "URL scan requested",
        session_id=crawl_session_id,
        urls=request.urls,
        categories=request.categories,
    )

    # Find or create CrawlSource for each URL and set processing status
    source_ids = []
    for url in request.urls:
        # Try to find existing source by base_url (exact match)
        result = await db.execute(
            select(CrawlSource).where(CrawlSource.base_url == url)
        )
        source = result.scalar_one_or_none()

        # If no exact match, try with/without trailing slash
        if not source:
            alt_url = url.rstrip('/') if url.endswith('/') else url + '/'
            result = await db.execute(
                select(CrawlSource).where(CrawlSource.base_url == alt_url)
            )
            source = result.scalar_one_or_none()

        if source:
            # Update processing status to 'processing'
            source.processing_status = ProcessingStatus.PROCESSING
            source.last_crawl_started_at = datetime.utcnow()
            source.processing_error_message = None
            source_ids.append(str(source.id))
            logger.info(f"Found existing source for URL: {url}, source_id: {source.id}")
        else:
            # Auto-create a simple source for ad-hoc URLs to enable status tracking
            from urllib.parse import urlparse
            from app.models.crawl_source import SourceType

            parsed = urlparse(url)
            domain = parsed.netloc or 'unknown'

            # Create a minimal source configuration
            new_source = CrawlSource(
                name=f"Ad-hoc: {domain}",
                source_type=SourceType.GOVERNMENT_PORTAL,
                state_code="XX",  # Unknown state for ad-hoc sources
                base_url=url,
                config={
                    "selectors": {},
                    "pagination": {"type": "link", "max_pages": 1}
                },
                is_enabled=True,
                processing_status=ProcessingStatus.PROCESSING,
                last_crawl_started_at=datetime.utcnow(),
            )
            db.add(new_source)
            await db.flush()  # Get the ID
            source_ids.append(str(new_source.id))
            logger.info(f"Created new ad-hoc source for URL: {url}, source_id: {new_source.id}")

    # Commit the processing status immediately so it's visible to frontend
    await db.commit()

    # Try Azure Function first
    function_url = settings.azure_function_url

    if function_url:
        # Normalize URL - remove trailing /api/crawl if present to avoid duplication
        function_url = function_url.rstrip('/')
        if function_url.endswith('/api/crawl'):
            function_url = function_url[:-len('/api/crawl')]

        # Define synchronous wrapper for background task
        # (FastAPI BackgroundTasks requires sync function for async work)
        def call_azure_function_sync():
            import asyncio

            async def _call():
                try:
                    async with httpx.AsyncClient(timeout=600.0) as client:
                        # Build request URL with function key if available
                        request_url = f"{function_url}/api/crawl"
                        if settings.azure_function_key:
                            request_url += f"?code={settings.azure_function_key}"

                        response = await client.post(
                            request_url,
                            json={
                                "urls": request.urls,
                                "crawl_session_id": crawl_session_id,
                                "categories": request.categories,
                                "source_ids": source_ids,
                                "backend_url": str(settings.backend_url),
                            }
                        )
                        logger.info(f"Azure Function responded with status: {response.status_code}")
                except Exception as e:
                    logger.error(f"Azure Function call failed: {e}")

            # Run the async function in a new event loop
            asyncio.run(_call())

        # Use FastAPI's BackgroundTasks for proper lifecycle management
        background_tasks.add_task(call_azure_function_sync)

        # Return immediately - Azure Function will update status via callback
        return UrlCrawlResponse(
            success=True,
            crawl_session_id=crawl_session_id,
            results=[],
            total_relevant=0,
            saved_to_db=0,
            message="Scan started. Processing in background - check back for results."
        )

    # No Azure Function configured - fall back to local crawler
    try:
        from app.services.local_crawler import LocalCrawlerService

        crawler = LocalCrawlerService()
        result = await crawler.crawl_urls(request.urls, request.categories)

        # Convert results to dict format for saving
        results_as_dicts = result.results

        # Save to database
        saved_count = await _save_opportunities_to_db(db, results_as_dicts, crawl_session_id)

        # Update sources to success
        await _update_sources_status(db, source_ids, ProcessingStatus.SUCCESS)

        # Convert to response format
        url_results = [
            UrlCrawlResult(
                url=r.get("url", ""),
                success=r.get("success", False),
                total_found=r.get("total_found", 0),
                relevant_count=r.get("relevant_count", 0),
                opportunities=[
                    ExtractedOpportunity(**opp) for opp in r.get("opportunities", [])
                ],
                error=r.get("error"),
                crawl_duration=r.get("crawl_duration"),
            )
            for r in results_as_dicts
        ]

        return UrlCrawlResponse(
            success=True,
            crawl_session_id=crawl_session_id,
            results=url_results,
            total_relevant=result.total_relevant,
            saved_to_db=saved_count,
            message="Crawl completed successfully"
        )

    except ImportError as e:
        logger.warning(f"Local crawler import failed: {e}")
        await _update_sources_status(db, source_ids, ProcessingStatus.FAILED, "Crawler services not configured")
        return UrlCrawlResponse(
            success=False,
            crawl_session_id=crawl_session_id,
            error="Crawler services not configured. Please set up Azure Functions or local services.",
            message="Configuration required"
        )
    except Exception as e:
        logger.exception("URL scan failed", error=str(e))
        await _update_sources_status(db, source_ids, ProcessingStatus.FAILED, str(e))
        return UrlCrawlResponse(
            success=False,
            crawl_session_id=crawl_session_id,
            error=str(e),
            message="Crawl failed"
        )


async def _update_sources_status(
    db: AsyncSession,
    source_ids: list[str | None],
    status: ProcessingStatus,
    error_message: str | None = None,
) -> None:
    """Update processing status for sources."""
    from uuid import UUID

    for source_id in source_ids:
        if source_id is None:
            continue
        try:
            result = await db.execute(
                select(CrawlSource).where(CrawlSource.id == UUID(source_id))
            )
            source = result.scalar_one_or_none()
            if source:
                source.processing_status = status
                source.last_crawl_completed_at = datetime.utcnow()
                if error_message:
                    source.processing_error_message = error_message
        except Exception as e:
            logger.warning(f"Failed to update source status: {e}")

    await db.commit()


async def _save_opportunities_to_db(
    db: AsyncSession,
    results: list[dict],
    crawl_session_id: str,
) -> int:
    """Save extracted opportunities to the database using UPSERT logic.

    Uses source_opportunity_id as the unique key for deduplication.
    Existing opportunities are updated with new data, new ones are inserted.
    """
    saved_count = 0

    for result in results:
        if not result.get("success"):
            continue

        for opp in result.get("opportunities", []):
            if not opp.get("is_relevant"):
                continue

            doc_id = opp.get("document_id")
            if not doc_id:
                logger.warning("Skipping opportunity without document_id")
                continue

            try:
                # Check if opportunity already exists
                existing_result = await db.execute(
                    select(Opportunity).where(
                        Opportunity.source_opportunity_id == doc_id
                    )
                )
                existing_opp = existing_result.scalar_one_or_none()

                ai_analysis = {
                    "stage1_category": opp.get("predicted_category"),
                    "classification_reason": opp.get("classification_reason"),
                    "crawl_session_id": crawl_session_id,
                }

                # Use document_url (RFP-specific URL) if available, otherwise fall back to base URL
                rfp_url = opp.get("document_url") or result.get("url")
                base_url = result.get("url", "")

                if existing_opp:
                    # Update existing opportunity
                    existing_opp.title = opp.get("event_name", "Unknown")
                    existing_opp.source_url = rfp_url
                    existing_opp.categories = [opp.get("predicted_category", "other")]
                    existing_opp.relevance_score = opp.get("classification_confidence")
                    existing_opp.submission_deadline = _parse_date(opp.get("response_due_date"))
                    existing_opp.ai_analysis = ai_analysis
                    logger.info(f"Updated existing opportunity: {doc_id}")
                else:
                    # Create new opportunity - need a source_id
                    # Get or create an ad-hoc source for this URL
                    source = await _get_or_create_adhoc_source(db, base_url)

                    new_opp = Opportunity(
                        source_id=source.id,
                        source_opportunity_id=doc_id,
                        title=opp.get("event_name", "Unknown"),
                        source_url=rfp_url,
                        state_code="US",
                        status=OpportunityStatus.NEW,
                        categories=[opp.get("predicted_category", "other")],
                        relevance_score=opp.get("classification_confidence"),
                        submission_deadline=_parse_date(opp.get("response_due_date")),
                        ai_analysis=ai_analysis,
                    )
                    db.add(new_opp)
                    saved_count += 1
                    logger.info(f"Inserted new opportunity: {doc_id}")

            except Exception as e:
                logger.warning(f"Failed to save opportunity {doc_id}: {e}")
                continue

    if saved_count > 0:
        await db.commit()

    return saved_count


async def _get_or_create_adhoc_source(db: AsyncSession, url: str) -> CrawlSource:
    """Get or create an ad-hoc crawl source for URL-based scanning."""
    from urllib.parse import urlparse
    from app.models.crawl_source import SourceType

    parsed = urlparse(url)
    domain = parsed.netloc or "unknown"
    source_name = f"Ad-hoc: {domain}"

    # Check if source already exists
    result = await db.execute(
        select(CrawlSource).where(CrawlSource.name == source_name)
    )
    source = result.scalar_one_or_none()

    if source:
        return source

    # Create new source
    new_source = CrawlSource(
        name=source_name,
        source_type=SourceType.GOVERNMENT_PORTAL,
        state_code="US",
        base_url=f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else url,
        config={"selectors": {}, "pagination": {"type": "none"}},
        is_enabled=True,
        notes="Auto-created source for ad-hoc URL scanning",
    )
    db.add(new_source)
    await db.flush()

    return new_source


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse date string to datetime."""
    if not date_str:
        return None

    # Try common formats
    formats = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


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

