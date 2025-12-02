"""
Dashboard endpoints.

Provides aggregated statistics and metrics for the dashboard UI.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.crawl_session import CrawlSession, CrawlSessionStatus
from app.models.crawl_source import CrawlSource
from app.models.opportunity import Opportunity, OpportunityStatus

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


class DashboardStats(BaseModel):
    """Dashboard statistics response."""
    
    # Opportunity counts
    total_opportunities: int
    new_this_week: int
    new_this_month: int
    active_opportunities: int
    
    # By status
    by_status: dict[str, int]
    
    # By category
    by_category: dict[str, int]
    
    # By state
    by_state: dict[str, int]
    
    # Special flags
    requiring_prequalification: int
    discretionary: int
    
    # Deadlines
    deadlines_this_week: int
    deadlines_next_week: int
    expired: int
    
    # Performance
    average_relevance_score: float | None
    
    # Sources
    total_sources: int
    active_sources: int


class RecentActivity(BaseModel):
    """Recent activity item."""
    
    type: str  # opportunity_found, crawl_completed, etc.
    title: str
    description: str
    timestamp: datetime
    metadata: dict[str, Any] = {}


class UpcomingDeadline(BaseModel):
    """Upcoming deadline item."""
    
    opportunity_id: str
    title: str
    deadline: datetime
    days_remaining: int
    state_code: str
    requires_prequalification: bool


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: DB) -> DashboardStats:
    """
    Get aggregated dashboard statistics.
    
    Returns counts and breakdowns of opportunities by various dimensions.
    """
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    week_ahead = now + timedelta(days=7)
    two_weeks_ahead = now + timedelta(days=14)
    
    # Base query for non-deleted opportunities
    base_filter = Opportunity.deleted_at.is_(None)
    
    # Total opportunities
    total = await db.scalar(
        select(func.count(Opportunity.id)).where(base_filter)
    ) or 0
    
    # New this week
    new_this_week = await db.scalar(
        select(func.count(Opportunity.id)).where(
            base_filter,
            Opportunity.created_at >= week_ago,
        )
    ) or 0
    
    # New this month
    new_this_month = await db.scalar(
        select(func.count(Opportunity.id)).where(
            base_filter,
            Opportunity.created_at >= month_ago,
        )
    ) or 0
    
    # Active (not expired/archived)
    active_statuses = [
        OpportunityStatus.NEW,
        OpportunityStatus.REVIEWING,
        OpportunityStatus.QUALIFIED,
        OpportunityStatus.APPLIED,
    ]
    active = await db.scalar(
        select(func.count(Opportunity.id)).where(
            base_filter,
            Opportunity.status.in_(active_statuses),
        )
    ) or 0
    
    # By status
    status_result = await db.execute(
        select(
            Opportunity.status,
            func.count(Opportunity.id),
        )
        .where(base_filter)
        .group_by(Opportunity.status)
    )
    by_status = {row[0].value: row[1] for row in status_result.all()}
    
    # By category (using unnest for array column)
    category_result = await db.execute(
        select(
            func.unnest(Opportunity.categories).label("category"),
            func.count(Opportunity.id),
        )
        .where(base_filter)
        .group_by("category")
    )
    by_category = {row[0]: row[1] for row in category_result.all()}
    
    # By state
    state_result = await db.execute(
        select(
            Opportunity.state_code,
            func.count(Opportunity.id),
        )
        .where(base_filter)
        .group_by(Opportunity.state_code)
    )
    by_state = {row[0]: row[1] for row in state_result.all()}
    
    # Requiring prequalification
    prequal = await db.scalar(
        select(func.count(Opportunity.id)).where(
            base_filter,
            Opportunity.requires_prequalification.is_(True),
        )
    ) or 0
    
    # Discretionary
    discretionary = await db.scalar(
        select(func.count(Opportunity.id)).where(
            base_filter,
            Opportunity.is_discretionary.is_(True),
        )
    ) or 0
    
    # Deadlines this week
    deadlines_this_week = await db.scalar(
        select(func.count(Opportunity.id)).where(
            base_filter,
            Opportunity.submission_deadline >= now,
            Opportunity.submission_deadline <= week_ahead,
        )
    ) or 0
    
    # Deadlines next week
    deadlines_next_week = await db.scalar(
        select(func.count(Opportunity.id)).where(
            base_filter,
            Opportunity.submission_deadline > week_ahead,
            Opportunity.submission_deadline <= two_weeks_ahead,
        )
    ) or 0
    
    # Expired
    expired = await db.scalar(
        select(func.count(Opportunity.id)).where(
            base_filter,
            Opportunity.submission_deadline < now,
            Opportunity.status != OpportunityStatus.EXPIRED,
        )
    ) or 0
    
    # Average relevance score
    avg_score = await db.scalar(
        select(func.avg(Opportunity.relevance_score)).where(
            base_filter,
            Opportunity.relevance_score.isnot(None),
        )
    )
    
    # Source counts
    total_sources = await db.scalar(select(func.count(CrawlSource.id))) or 0
    active_sources = await db.scalar(
        select(func.count(CrawlSource.id)).where(CrawlSource.is_enabled.is_(True))
    ) or 0
    
    return DashboardStats(
        total_opportunities=total,
        new_this_week=new_this_week,
        new_this_month=new_this_month,
        active_opportunities=active,
        by_status=by_status,
        by_category=by_category,
        by_state=by_state,
        requiring_prequalification=prequal,
        discretionary=discretionary,
        deadlines_this_week=deadlines_this_week,
        deadlines_next_week=deadlines_next_week,
        expired=expired,
        average_relevance_score=float(avg_score) if avg_score else None,
        total_sources=total_sources,
        active_sources=active_sources,
    )

