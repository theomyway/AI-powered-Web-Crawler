"""
Main API router that aggregates all endpoint routers.
"""

from fastapi import APIRouter

from app.api.endpoints import sources, opportunities, crawl, dashboard, auth, internal

api_router = APIRouter()

# Include authentication router (no authentication required for these endpoints)
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)

# Include internal router (API key authentication for service-to-service)
api_router.include_router(
    internal.router,
    tags=["Internal"],
)

# Include all endpoint routers (authentication required)
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

