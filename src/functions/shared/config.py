"""
Configuration for Azure Functions.
"""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # Database
    database_url: str

    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    azure_openai_api_version: str

    # Azure Document Intelligence
    azure_doc_intelligence_endpoint: str | None
    azure_doc_intelligence_key: str | None

    # Crawler Settings - Core
    crawler_proxy_url: str | None
    crawler_proxy_username: str | None
    crawler_proxy_password: str | None
    crawler_timeout: int
    crawler_navigation_timeout: int
    crawler_user_agent: str

    # Crawler Settings - Retry & Resilience
    crawler_max_retries: int
    crawler_retry_min_wait: int
    crawler_retry_max_wait: int

    # Crawler Settings - Stealth Mode
    crawler_stealth_mode: bool
    crawler_random_delay_min: float
    crawler_random_delay_max: float

    # Crawler Settings - Viewport
    crawler_viewport_width: int
    crawler_viewport_height: int


@lru_cache
def get_settings() -> Settings:
    """Get application settings from environment variables."""
    return Settings(
        # Database
        database_url=os.environ.get("DATABASE_URL", ""),

        # Azure OpenAI
        azure_openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
        azure_openai_api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),
        azure_openai_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        azure_openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),

        # Azure Document Intelligence
        azure_doc_intelligence_endpoint=os.environ.get("AZURE_DOC_INTELLIGENCE_ENDPOINT"),
        azure_doc_intelligence_key=os.environ.get("AZURE_DOC_INTELLIGENCE_KEY"),

        # Crawler - Core
        crawler_proxy_url=os.environ.get("CRAWLER_PROXY_URL") or None,
        crawler_proxy_username=os.environ.get("CRAWLER_PROXY_USERNAME") or None,
        crawler_proxy_password=os.environ.get("CRAWLER_PROXY_PASSWORD") or None,
        crawler_timeout=int(os.environ.get("CRAWLER_TIMEOUT", "90")),
        crawler_navigation_timeout=int(os.environ.get("CRAWLER_NAVIGATION_TIMEOUT", "120")),
        crawler_user_agent=os.environ.get("CRAWLER_USER_AGENT", ""),  # Empty = use stealth rotation

        # Crawler - Retry & Resilience
        crawler_max_retries=int(os.environ.get("CRAWLER_MAX_RETRIES", "3")),
        crawler_retry_min_wait=int(os.environ.get("CRAWLER_RETRY_MIN_WAIT", "5")),
        crawler_retry_max_wait=int(os.environ.get("CRAWLER_RETRY_MAX_WAIT", "60")),

        # Crawler - Stealth Mode
        crawler_stealth_mode=os.environ.get("CRAWLER_STEALTH_MODE", "true").lower() == "true",
        crawler_random_delay_min=float(os.environ.get("CRAWLER_RANDOM_DELAY_MIN", "1.0")),
        crawler_random_delay_max=float(os.environ.get("CRAWLER_RANDOM_DELAY_MAX", "3.0")),

        # Crawler - Viewport
        crawler_viewport_width=int(os.environ.get("CRAWLER_VIEWPORT_WIDTH", "1920")),
        crawler_viewport_height=int(os.environ.get("CRAWLER_VIEWPORT_HEIGHT", "1080")),
    )

