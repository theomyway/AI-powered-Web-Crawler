"""
Application configuration management.

Loads settings from environment variables via .env file.
Supports multiple environments (development, staging, production).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All sensitive values should be stored in .env file (not committed to git).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI-Powered Web Crawler"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = Field(default=False, description="Enable debug mode")

    # API Configuration
    api_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="CORS allowed origins (comma-separated)"
    )

    @property
    def cors_origins(self) -> list[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    # Database - Azure Cosmos DB for PostgreSQL
    database_url: PostgresDsn = Field(
        ...,
        description="PostgreSQL connection string for Cosmos DB"
    )
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout: int = Field(default=30, ge=5, le=120)
    database_echo: bool = Field(default=False, description="Echo SQL queries")
    
    # Azure Service Bus
    servicebus_connection_string: str | None = Field(
        default=None,
        description="Azure Service Bus connection string"
    )
    servicebus_queue_name: str = "opportunity-processing"
    
    # Azure OpenAI
    azure_openai_endpoint: str | None = Field(
        default=None,
        description="Azure OpenAI endpoint URL (e.g., https://your-resource.openai.azure.com/)"
    )
    azure_openai_api_key: str | None = Field(
        default=None,
        description="Azure OpenAI API key"
    )
    azure_openai_deployment: str = Field(
        default="gpt-4o",
        description="Azure OpenAI deployment name for GPT-4o"
    )
    azure_openai_api_version: str = "2024-08-01-preview"

    # Azure Document Intelligence (Form Recognizer)
    azure_doc_intelligence_endpoint: str | None = Field(
        default=None,
        description="Azure Document Intelligence endpoint URL"
    )
    azure_doc_intelligence_key: str | None = Field(
        default=None,
        description="Azure Document Intelligence API key"
    )

    # Azure Functions
    azure_function_url: str | None = Field(
        default=None,
        description="Azure Function App URL (e.g., https://your-app.azurewebsites.net)"
    )
    azure_function_key: str | None = Field(
        default=None,
        description="Azure Function host key for authentication"
    )

    # Crawler Proxy (for geo-restricted sites)
    crawler_proxy_url: str | None = Field(
        default=None,
        description="HTTP/HTTPS proxy URL for crawling (e.g., http://proxy:8080)"
    )

    # Redis Cache
    redis_url: RedisDsn | None = Field(
        default=None,
        description="Redis connection URL"
    )
    redis_ttl_seconds: int = Field(default=3600, description="Default cache TTL")
    
    # SharePoint Integration
    sharepoint_site_url: str | None = Field(
        default=None,
        description="SharePoint site URL for document storage"
    )
    sharepoint_client_id: str | None = None
    sharepoint_client_secret: str | None = None
    sharepoint_tenant_id: str | None = None
    
    # Crawler Settings
    crawler_default_delay: float = Field(
        default=2.0,
        ge=0.5,
        description="Default delay between requests (seconds)"
    )
    crawler_max_concurrent: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent crawl requests"
    )
    crawler_timeout: int = Field(
        default=30,
        ge=10,
        le=120,
        description="Request timeout in seconds"
    )
    crawler_user_agent: str = Field(
        default="MazikUSA-OpportunityBot/1.0 (+https://mazikusa.com/bot)",
        description="User agent for crawling"
    )
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    
    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL uses asyncpg driver."""
        if v and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    Returns:
        Settings: Application settings instance
    """
    return Settings()

