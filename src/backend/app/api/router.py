"""
Main API router that aggregates all endpoint routers.
"""

from fastapi import APIRouter

from app.api.endpoints import sources, opportunities, crawl, dashboard

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    sources.router,
    prefix="/sources",
    tags=["Crawl Sources"],
)

api_router.include_router(
    opportunities.router,
    prefix="/opportunities",
    tags=["Opportunities"],
)

api_router.include_router(
    crawl.router,
    prefix="/crawl",
    tags=["Crawl Operations"],
)

api_router.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["Dashboard"],
)

