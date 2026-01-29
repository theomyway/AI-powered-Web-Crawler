"""
Scheduler endpoints for automated crawl operations.

Prefers URLs stored in scheduler config (AppSettings -> key: "scheduler_config" -> "target_urls").
If target_urls is present and non-empty, scheduler will queue only those canonical URLs
(found or created as ad-hoc CrawlSource rows). Otherwise falls back to enabled sources.
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

DAY_NAME_TO_WEEKDAY = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

DEFAULT_SCHEDULE = {
    "days": ["Monday", "Thursday"],
    "hour": 6,
    "minute": 0,
    "timezone": "UTC",
    "enabled": True,
    "last_run": None,
    "target_urls": [],
}


class SchedulerConfig(BaseModel):
    scheduled_days: list[str]
    scheduled_time_utc: str
    next_scheduled_run: datetime | None
    last_scheduled_run: datetime | None
    enabled: bool = True
    target_urls: list[str] = Field(default_factory=list)


class SchedulerConfigUpdate(BaseModel):
    days: list[str] = Field(..., description="Days to run scans", min_length=1)
    hour: int = Field(..., ge=0, le=23, description="Hour to run (0-23)")
    minute: int = Field(0, ge=0, le=59, description="Minute to run (0-59)")
    enabled: bool = Field(True, description="Whether scheduler is enabled")
    target_urls: list[str] = Field(default_factory=list, description="Optional explicit list of URLs to scan")


class ScheduledScanResponse(BaseModel):
    success: bool
    message: str
    urls_to_scan: list[str]
    total_sources: int


async def get_schedule_config(db: AsyncSession) -> dict:
    result = await db.execute(select(AppSettings).where(AppSettings.key == "scheduler_config"))
    setting = result.scalar_one_or_none()
    if setting:
        return {**DEFAULT_SCHEDULE, **(setting.value or {})}
    return DEFAULT_SCHEDULE


def canonicalize_url(raw: str) -> str | None:
    """Canonicalize URL: require http(s), drop query/fragment, strip www., lowercase host, remove trailing slash."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        parsed = urlparse(raw)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""
    canon = f"{parsed.scheme}://{host}{path}".rstrip("/")
    return canon.lower()


def get_next_scheduled_run(days: list[str], hour: int, minute: int) -> datetime:
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
    config = await get_schedule_config(db)
    days = config.get("days", ["Monday", "Thursday"])
    hour = config.get("hour", 6)
    minute = config.get("minute", 0)
    enabled = config.get("enabled", True)
    last_run = config.get("last_run")
    target_urls = config.get("target_urls", [])
    return SchedulerConfig(
        scheduled_days=days,
        scheduled_time_utc=f"{hour:02d}:{minute:02d} UTC",
        next_scheduled_run=get_next_scheduled_run(days, hour, minute) if enabled else None,
        last_scheduled_run=datetime.fromisoformat(last_run) if last_run else None,
        enabled=enabled,
        target_urls=target_urls,
    )


@router.put("/config", response_model=SchedulerConfig)
async def update_scheduler_config(db: DB, config_update: SchedulerConfigUpdate) -> SchedulerConfig:
    for day in config_update.days:
        if day not in DAY_NAME_TO_WEEKDAY:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid day: {day}")
    result = await db.execute(select(AppSettings).where(AppSettings.key == "scheduler_config"))
    setting = result.scalar_one_or_none()
    new_value = {
        "days": config_update.days,
        "hour": config_update.hour,
        "minute": config_update.minute,
        "timezone": "UTC",
        "enabled": config_update.enabled,
        "last_run": setting.value.get("last_run") if setting and setting.value else None,
        "target_urls": config_update.target_urls or [],
    }
    if setting:
        setting.value = new_value
    else:
        setting = AppSettings(key="scheduler_config", value=new_value)
        db.add(setting)
    await db.commit()
    return SchedulerConfig(
        scheduled_days=config_update.days,
        scheduled_time_utc=f"{config_update.hour:02d}:{config_update.minute:02d} UTC",
        next_scheduled_run=get_next_scheduled_run(config_update.days, config_update.hour, config_update.minute) if config_update.enabled else None,
        last_scheduled_run=datetime.fromisoformat(new_value["last_run"]) if new_value["last_run"] else None,
        enabled=config_update.enabled,
        target_urls=new_value["target_urls"],
    )


@router.post("/trigger-scan", response_model=ScheduledScanResponse)
async def trigger_scheduled_scan(
    db: DB,
    background_tasks: BackgroundTasks,
    x_scheduler_key: str = Header(None, alias="X-Scheduler-Key"),
) -> ScheduledScanResponse:
    settings = get_settings()
    expected_key = getattr(settings, "internal_api_key", None)
    if not x_scheduler_key or x_scheduler_key != expected_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing scheduler key")

    config = await get_schedule_config(db)
    if not config.get("enabled", True):
        return ScheduledScanResponse(success=True, message="Scheduler disabled", urls_to_scan=[], total_sources=0)

    raw_targets = config.get("target_urls") or []
    urls: list[str] = []
    sources: list[CrawlSource] = []
    source_ids: list[str] = []

    if raw_targets:
        # canonicalize and dedupe targets
        seen = set()
        for r in raw_targets:
            c = canonicalize_url(r)
            if not c:
                logger.warning("Skipping invalid/non-http target URL", url=r)
                continue
            if c in seen:
                continue
            seen.add(c)
            urls.append(c)

        # find or create CrawlSource rows for these urls so UI shows processing
        for c_url in urls:
            result = await db.execute(select(CrawlSource).where(CrawlSource.base_url == c_url))
            src = result.scalar_one_or_none()
            if not src:
                alt = c_url + "/"
                result = await db.execute(select(CrawlSource).where(CrawlSource.base_url == alt))
                src = result.scalar_one_or_none()
            if not src:
                from app.models.crawl_source import SourceType  # local import to avoid circulars
                parsed = urlparse(c_url)
                domain = parsed.netloc or "unknown"
                src = CrawlSource(
                    name=f"Ad-hoc: {domain}",
                    source_type=SourceType.GOVERNMENT_PORTAL,
                    state_code="US",
                    base_url=c_url,
                    config={"selectors": {}, "pagination": {"type": "none"}},
                    is_enabled=True,
                    notes="Auto-created ad-hoc source for scheduled run",
                    processing_status=ProcessingStatus.PENDING,
                    last_crawl_started_at=datetime.utcnow(),
                    progress_percent=0,
                )
                db.add(src)
                await db.flush()
            sources.append(src)
            source_ids.append(str(src.id))
    else:
        # No target_urls configured - don't scan anything
        # (Previously fell back to all enabled sources, but that's not desired behavior)
        return ScheduledScanResponse(
            success=True,
            message="No target URLs configured for scheduled scan",
            urls_to_scan=[],
            total_sources=0
        )

    if not urls:
        return ScheduledScanResponse(success=True, message="No valid HTTP(S) URLs to scan", urls_to_scan=[], total_sources=0)

    # mark matching sources as processing so frontend detects session
    crawl_session_id = str(uuid4())
    for src in sources:
        base = src.base_url or ""
        c_base = canonicalize_url(base)
        if not c_base:
            continue
        if any(c_base == u or c_base.startswith(u) or u.startswith(c_base) for u in urls):
            src.processing_status = ProcessingStatus.PROCESSING
            src.last_crawl_started_at = datetime.utcnow()
            src.progress_percent = 0
            src.progress_message = "Scheduled scan starting..."
            if str(src.id) not in source_ids:
                source_ids.append(str(src.id))

    # update last_run
    cfg_res = await db.execute(select(AppSettings).where(AppSettings.key == "scheduler_config"))
    cfg_setting = cfg_res.scalar_one_or_none()
    if cfg_setting:
        cfg_setting.value = {**(cfg_setting.value or {}), "last_run": datetime.utcnow().isoformat()}

    await db.commit()

    # enqueue same as scan-urls
    servicebus = get_servicebus_service()
    settings_local = get_settings()
    if servicebus.is_configured:
        await servicebus.send_batch_crawl_requests(
            urls=urls,
            source_ids=source_ids,
            crawl_session_id=crawl_session_id,
            categories=[],
            backend_url=str(getattr(settings_local, "backend_url", "")),
        )
    else:
        async def call_azure_function():
            azure_function_url = getattr(settings_local, "azure_function_url", None)
            if not azure_function_url:
                logger.warning("AZURE_FUNCTION_URL not configured, cannot trigger scheduled scan")
                return
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    request_url = azure_function_url.rstrip("/")
                    if request_url.endswith("/api/crawl"):
                        request_url = request_url[:-len("/api/crawl")]
                    await client.post(
                        request_url,
                        json={
                            "urls": urls,
                            "categories": [],
                            "crawl_session_id": crawl_session_id,
                            "source_ids": source_ids,
                            "backend_url": str(getattr(settings_local, "backend_url", "")),
                        },
                        headers={"Content-Type": "application/json"},
                    )
            except Exception as e:
                logger.error("Failed to trigger Azure Function for scheduled scan", error=str(e))
        background_tasks.add_task(call_azure_function)

    return ScheduledScanResponse(success=True, message=f"Scheduled scan initiated for {len(urls)} URLs", urls_to_scan=urls, total_sources=len(sources))
