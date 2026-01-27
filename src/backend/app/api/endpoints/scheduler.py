"""
Scheduler endpoints for automated crawl operations.

Provides endpoints for:
1. Triggering scheduled scans (called by Azure Logic App)
2. Getting/updating scheduler configuration
"""

from datetime import datetime, timedelta
from typing import Annotated
from uuid import uuid4
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import structlog

from app.db.session import get_db
from app.core.config import get_settings
from app.models import CrawlSource, AppSettings
from app.models.crawl_source import ProcessingStatus
from app.services.servicebus import get_servicebus_service

logger = structlog.get_logger()

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

DB = Annotated[AsyncSession, Depends(get_db)]

# Day name to weekday mapping
DAY_NAME_TO_WEEKDAY = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}
WEEKDAY_TO_DAY_NAME = {v: k for k, v in DAY_NAME_TO_WEEKDAY.items()}

# Default schedule configuration
DEFAULT_SCHEDULE = {
    "days": ["Monday", "Thursday"],
    "hour": 6,
    "minute": 0,
    "timezone": "UTC",
    "enabled": True,
    "last_run": None,
}


class SchedulerConfig(BaseModel):
    """Scheduler configuration response."""

    scheduled_days: list[str]
    scheduled_time_utc: str
    next_scheduled_run: datetime | None
    last_scheduled_run: datetime | None
    enabled: bool = True


class SchedulerConfigUpdate(BaseModel):
    """Update scheduler configuration."""

    days: list[str] = Field(..., description="Days to run scans", min_length=1)
    hour: int = Field(..., ge=0, le=23, description="Hour to run (0-23)")
    minute: int = Field(0, ge=0, le=59, description="Minute to run (0-59)")
    enabled: bool = Field(True, description="Whether scheduler is enabled")


class ScheduledScanResponse(BaseModel):
    """Response for scheduled scan trigger."""

    success: bool
    message: str
    urls_to_scan: list[str]
    total_sources: int


async def get_schedule_config(db: AsyncSession) -> dict:
    """Get schedule configuration from database."""
    result = await db.execute(select(AppSettings).where(AppSettings.key == "scheduler_config"))
    setting = result.scalar_one_or_none()
    if setting:
        return {**DEFAULT_SCHEDULE, **(setting.value or {})}
    return DEFAULT_SCHEDULE


def get_next_scheduled_run(days: list[str], hour: int, minute: int) -> datetime:
    """Calculate the next scheduled run time."""
    now = datetime.utcnow()
    weekdays = [DAY_NAME_TO_WEEKDAY.get(d, 0) for d in days if d in DAY_NAME_TO_WEEKDAY]

    if not weekdays:
        return now + timedelta(days=7)

    days_until_next = []
    for target_day in weekdays:
        days_ahead = target_day - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0:
            scheduled_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now >= scheduled_today:
                days_ahead = 7
        days_until_next.append(days_ahead)

    min_days = min(days_until_next)
    next_run = now + timedelta(days=min_days)
    next_run = next_run.replace(hour=hour, minute=minute, second=0, microsecond=0)

    return next_run


@router.get("/config", response_model=SchedulerConfig)
async def get_scheduler_config(db: DB) -> SchedulerConfig:
    """
    Get scheduler configuration and next run time.

    This endpoint is public (no auth required) for dashboard display.
    """
    config = await get_schedule_config(db)
    days = config.get("days", ["Monday", "Thursday"])
    hour = config.get("hour", 6)
    minute = config.get("minute", 0)
    enabled = config.get("enabled", True)
    last_run = config.get("last_run")

    return SchedulerConfig(
        scheduled_days=days,
        scheduled_time_utc=f"{hour:02d}:{minute:02d} UTC",
        next_scheduled_run=get_next_scheduled_run(days, hour, minute) if enabled else None,
        last_scheduled_run=datetime.fromisoformat(last_run) if last_run else None,
        enabled=enabled,
    )


@router.put("/config", response_model=SchedulerConfig)
async def update_scheduler_config(
    db: DB,
    config_update: SchedulerConfigUpdate,
) -> SchedulerConfig:
    """
    Update scheduler configuration.

    Note: This updates the backend schedule settings. The Azure Logic App
    recurrence is set separately but will check if scanning is enabled.
    """
    # Validate day names
    for day in config_update.days:
        if day not in DAY_NAME_TO_WEEKDAY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid day: {day}. Must be one of: {list(DAY_NAME_TO_WEEKDAY.keys())}",
            )

    # Get or create setting
    result = await db.execute(select(AppSettings).where(AppSettings.key == "scheduler_config"))
    setting = result.scalar_one_or_none()

    new_value = {
        "days": config_update.days,
        "hour": config_update.hour,
        "minute": config_update.minute,
        "timezone": "UTC",
        "enabled": config_update.enabled,
        "last_run": setting.value.get("last_run") if setting else None,
    }

    if setting:
        setting.value = new_value
    else:
        setting = AppSettings(key="scheduler_config", value=new_value)
        db.add(setting)

    await db.commit()
    logger.info(f"Scheduler config updated: {new_value}")

    return SchedulerConfig(
        scheduled_days=config_update.days,
        scheduled_time_utc=f"{config_update.hour:02d}:{config_update.minute:02d} UTC",
        next_scheduled_run=(
            get_next_scheduled_run(config_update.days, config_update.hour, config_update.minute)
            if config_update.enabled
            else None
        ),
        last_scheduled_run=(
            datetime.fromisoformat(new_value["last_run"]) if new_value["last_run"] else None
        ),
        enabled=config_update.enabled,
    )


@router.post("/trigger-scan", response_model=ScheduledScanResponse)
async def trigger_scheduled_scan(
    db: DB,
    background_tasks: BackgroundTasks,
    x_scheduler_key: str = Header(None, alias="X-Scheduler-Key"),
) -> ScheduledScanResponse:
    """
    Trigger a scheduled scan for all enabled sources.

    This endpoint is called by Azure Logic App on schedule.
    Requires X-Scheduler-Key header for authentication.
    """
    settings = get_settings()

    # Validate scheduler key (use internal_api_key - lowercase)
    expected_key = getattr(settings, "internal_api_key", None)
    if not x_scheduler_key or x_scheduler_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing scheduler key",
        )

    # Check if scheduler is enabled in config
    config = await get_schedule_config(db)
    if not config.get("enabled", True):
        logger.info("Scheduled scan skipped - scheduler is disabled")
        return ScheduledScanResponse(
            success=True,
            message="Scheduler is disabled",
            urls_to_scan=[],
            total_sources=0,
        )

    logger.info("Scheduled scan triggered by Azure Logic App")

    # Get all enabled sources
    result = await db.execute(select(CrawlSource).where(CrawlSource.is_enabled.is_(True)))
    sources = result.scalars().all()

    if not sources:
        return ScheduledScanResponse(
            success=True,
            message="No enabled sources to scan",
            urls_to_scan=[],
            total_sources=0,
        )

    # Collect, normalize and deduplicate URLs from sources
    raw_urls = [s.base_url or "" for s in sources]
    normalized = []
    for u in raw_urls:
        u = (u or "").strip()
        if not u:
            continue
        parsed = urlparse(u)
        # Only allow http/https
        if parsed.scheme not in ("http", "https"):
            logger.warning("Skipping non-http(s) URL from sources", url=u)
            continue
        # Normalize: scheme + netloc + path + query (lowercase host, strip trailing slashes)
        norm = parsed.geturl().rstrip("/").lower()
        normalized.append(norm)

    # Deduplicate preserving order
    seen = set()
    urls = []
    for u in normalized:
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)

    if not urls:
        return ScheduledScanResponse(
            success=True,
            message="No valid HTTP(S) URLs to scan from enabled sources",
            urls_to_scan=[],
            total_sources=len(sources),
        )

    logger.info(
        f"Scheduled scan: will process {len(urls)} unique url(s) from {len(sources)} enabled sources"
    )

    # Mark sources as processing and set last_crawl_started_at so front-end will detect them
    crawl_session_id = str(uuid4())
    source_ids = []
    for source in sources:
        if source.base_url:
            # Only mark sources that match one of the normalized urls (match by prefix)
            parsed = urlparse(source.base_url or "")
            if parsed.scheme not in ("http", "https"):
                continue
            norm = (parsed.geturl().rstrip("/")).lower()
            if any(norm == u or u.startswith(norm) for u in urls):
                source.processing_status = ProcessingStatus.PROCESSING
                source.last_crawl_started_at = datetime.utcnow()
                source.progress_percent = 0
                source.progress_message = "Scheduled scan starting..."
                source_ids.append(str(source.id))

    # Update last run time in config
    config_result = await db.execute(
        select(AppSettings).where(AppSettings.key == "scheduler_config")
    )
    config_setting = config_result.scalar_one_or_none()
    if config_setting:
        config_setting.value = {
            **(config_setting.value or {}),
            "last_run": datetime.utcnow().isoformat(),
        }

    # Commit the source status updates and last_run
    await db.commit()

    # Enqueue via Service Bus (same path used by scan-urls). This keeps behavior consistent
    servicebus = get_servicebus_service()
    if servicebus.is_configured:
        logger.info(
            "Enqueueing scheduled URLs via Service Bus",
            count=len(urls),
            session_id=crawl_session_id,
        )
        success_count, fail_count = await servicebus.send_batch_crawl_requests(
            urls=urls,
            source_ids=source_ids,
            crawl_session_id=crawl_session_id,
            categories=[],
            backend_url=str(getattr(settings, "backend_url", "")),
        )
        if fail_count > 0:
            logger.warning(
                "Some scheduled messages failed to enqueue", fail_count=fail_count, total=len(urls)
            )
    else:
        # Fall back to calling the Azure Function (if configured)
        async def call_azure_function():
            azure_function_url = getattr(settings, "azure_function_url", None)
            if not azure_function_url:
                logger.warning("AZURE_FUNCTION_URL not configured, cannot trigger scheduled scan")
                return
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        azure_function_url,
                        json={
                            "urls": urls,
                            "categories": [],  # Scan all categories
                            "crawl_session_id": crawl_session_id,
                            "source_ids": source_ids,
                            "backend_url": str(getattr(settings, "backend_url", "")),
                        },
                        headers={"Content-Type": "application/json"},
                    )
                    logger.info(
                        "Azure Function triggered for scheduled scan",
                        status_code=response.status_code,
                    )
            except Exception as e:
                logger.error("Failed to trigger Azure Function for scheduled scan", error=str(e))

        background_tasks.add_task(call_azure_function)

    return ScheduledScanResponse(
        success=True,
        message=f"Scheduled scan initiated for {len(urls)} URLs",
        urls_to_scan=urls,
        total_sources=len(sources),
    )
