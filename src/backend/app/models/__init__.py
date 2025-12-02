"""
SQLAlchemy ORM models for the AI-Powered Web Crawler.

Models are designed for configuration-driven crawling with support for
dynamic source management and multi-state/county deployment.
"""

from app.models.crawl_source import CrawlSource, SourceType, SourceStatus
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityCategory
from app.models.crawl_session import CrawlSession, CrawlSessionStatus
from app.models.document import Document, DocumentType, ProcessingStatus
from app.models.prequalification import PrequalificationRequirement

__all__ = [
    # Crawl Source
    "CrawlSource",
    "SourceType",
    "SourceStatus",
    # Opportunity
    "Opportunity",
    "OpportunityStatus",
    "OpportunityCategory",
    # Crawl Session
    "CrawlSession",
    "CrawlSessionStatus",
    # Document
    "Document",
    "DocumentType",
    "ProcessingStatus",
    # Prequalification
    "PrequalificationRequirement",
]

