"""
Custom exception classes for the application.

Provides structured error handling with consistent error codes
and HTTP status mappings.
"""

from typing import Any


class AppException(Exception):
    """
    Base exception for all application errors.
    
    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code for client handling
        status_code: HTTP status code to return
        details: Additional error context
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "APP_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API response."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }


# Database Exceptions
class DatabaseException(AppException):
    """Base exception for database-related errors."""
    
    def __init__(
        self,
        message: str = "Database operation failed",
        error_code: str = "DB_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code, 500, details)


class EntityNotFoundException(AppException):
    """Raised when a requested entity is not found."""
    
    def __init__(
        self,
        entity_type: str,
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        message = f"{entity_type} not found"
        if entity_id:
            message = f"{entity_type} with id '{entity_id}' not found"
        super().__init__(message, "ENTITY_NOT_FOUND", 404, details)


class DuplicateEntityException(AppException):
    """Raised when attempting to create a duplicate entity."""
    
    def __init__(
        self,
        entity_type: str,
        field: str,
        value: str,
    ) -> None:
        message = f"{entity_type} with {field}='{value}' already exists"
        super().__init__(message, "DUPLICATE_ENTITY", 409, {"field": field, "value": value})


# Validation Exceptions
class ValidationException(AppException):
    """Raised when input validation fails."""
    
    def __init__(
        self,
        message: str = "Validation failed",
        field_errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message, "VALIDATION_ERROR", 422, {"field_errors": field_errors or {}})


# Crawler Exceptions
class CrawlerException(AppException):
    """Base exception for crawler-related errors."""
    
    def __init__(
        self,
        message: str = "Crawler operation failed",
        error_code: str = "CRAWLER_ERROR",
        source_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        _details = details or {}
        if source_id:
            _details["source_id"] = source_id
        super().__init__(message, error_code, 500, _details)


class CrawlerConfigException(CrawlerException):
    """Raised when crawler configuration is invalid."""
    
    def __init__(self, message: str, source_id: str | None = None) -> None:
        super().__init__(message, "CRAWLER_CONFIG_ERROR", source_id)


class CrawlerConnectionException(CrawlerException):
    """Raised when crawler cannot connect to target."""
    
    def __init__(self, url: str, source_id: str | None = None) -> None:
        super().__init__(
            f"Failed to connect to {url}",
            "CRAWLER_CONNECTION_ERROR",
            source_id,
            {"url": url},
        )


# External Service Exceptions
class ExternalServiceException(AppException):
    """Raised when an external service call fails."""
    
    def __init__(
        self,
        service_name: str,
        message: str = "External service call failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            f"{service_name}: {message}",
            "EXTERNAL_SERVICE_ERROR",
            503,
            {"service": service_name, **(details or {})},
        )


class AIServiceException(ExternalServiceException):
    """Raised when Azure OpenAI service fails."""
    
    def __init__(self, message: str = "AI classification failed") -> None:
        super().__init__("AzureOpenAI", message)


class SharePointException(ExternalServiceException):
    """Raised when SharePoint operations fail."""
    
    def __init__(self, message: str = "SharePoint operation failed") -> None:
        super().__init__("SharePoint", message)

