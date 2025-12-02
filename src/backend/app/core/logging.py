"""
Structured logging configuration using structlog.

Provides consistent JSON logging for production and human-readable
console output for development.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from app.core.config import get_settings


def setup_logging() -> None:
    """
    Configure structured logging for the application.
    
    Uses JSON format in production for log aggregation compatibility,
    and colored console output in development for readability.
    """
    settings = get_settings()
    
    # Determine processors based on environment
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    
    if settings.log_format == "json":
        # Production: JSON output
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Console output with colors
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Also configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__ of the calling module)
        **initial_context: Initial context values to bind to the logger
        
    Returns:
        BoundLogger: Configured structured logger
        
    Example:
        >>> logger = get_logger(__name__, request_id="abc123")
        >>> logger.info("Processing request", user_id=42)
    """
    logger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


class LoggerMixin:
    """
    Mixin class that provides a logger property to any class.
    
    Example:
        >>> class MyService(LoggerMixin):
        ...     def do_work(self):
        ...         self.logger.info("Working...")
    """
    
    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        """Get logger bound with class name."""
        return get_logger(self.__class__.__name__)

