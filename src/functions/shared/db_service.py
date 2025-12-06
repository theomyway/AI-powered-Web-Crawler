"""
Database service for Azure Functions.

Provides synchronous database access for saving opportunities directly from the Azure Function.
Uses psycopg2 (synchronous) because asyncpg requires an async context manager which complicates
the Azure Functions flow.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor

from shared.config import get_settings
from shared.models import ExtractedRFP

logger = logging.getLogger(__name__)


def get_db_connection():
    """
    Create a synchronous database connection for Azure Cosmos DB PostgreSQL.
    
    Returns:
        psycopg2 connection object
    """
    settings = get_settings()
    db_url = settings.database_url
    
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set")
    
    # Parse the connection string
    # Convert from asyncpg format to psycopg2 format if needed
    if "postgresql+asyncpg://" in db_url:
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    
    # Remove sslmode from URL and add as parameter
    db_url = db_url.replace("?sslmode=require", "")
    
    logger.info("Connecting to database...")
    conn = psycopg2.connect(db_url, sslmode="require")
    logger.info("Database connection established")
    return conn


def get_or_create_adhoc_source(conn, url: str) -> uuid.UUID:
    """
    Get or create an ad-hoc crawl source for URL-based scanning.
    
    Args:
        conn: Database connection
        url: The URL being scanned
        
    Returns:
        UUID of the crawl source
    """
    parsed = urlparse(url)
    domain = parsed.netloc or "unknown"
    source_name = f"Ad-hoc: {domain}"
    base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else url
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Check if source already exists
        cur.execute(
            """
            SELECT id FROM crawl_sources 
            WHERE name = %s AND source_type = 'government_portal'
            """,
            (source_name,)
        )
        result = cur.fetchone()
        
        if result:
            return uuid.UUID(str(result['id']))
        
        # Create new source
        source_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO crawl_sources 
            (id, name, source_type, status, state_code, base_url, config, is_enabled, notes, created_at, updated_at)
            VALUES (%s, %s, 'government_portal', 'active', 'US', %s, %s, true, %s, %s, %s)
            RETURNING id
            """,
            (
                str(source_id),
                source_name,
                base_url,
                '{"selectors": {"opportunity_list": ".opportunity-card"}, "pagination": {"type": "none"}}',
                "Auto-created source for ad-hoc URL scanning",
                datetime.utcnow(),
                datetime.utcnow(),
            )
        )
        conn.commit()
        logger.info(f"Created new ad-hoc source: {source_name} ({source_id})")
        return source_id


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime object."""
    if not date_str:
        return None
    
    # Try common date formats
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def save_opportunities_to_db(results: list[dict], crawl_session_id: str) -> int:
    """
    Save extracted opportunities directly to the database.
    
    Args:
        results: List of URL processing results containing opportunities
        crawl_session_id: The crawl session identifier
        
    Returns:
        Number of opportunities successfully saved
    """
    saved_count = 0
    source_cache: dict[str, uuid.UUID] = {}
    
    try:
        conn = get_db_connection()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return 0
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for result in results:
                if not result.get("success"):
                    continue
                    
                url = result.get("url", "")
                opportunities = result.get("opportunities", [])
                
                for opp in opportunities:
                    # Only save relevant opportunities
                    if not opp.get("is_relevant"):
                        continue
                    
                    try:
                        doc_id = opp.get("document_id")
                        
                        # Check for duplicates
                        if doc_id:
                            cur.execute(
                                "SELECT id FROM opportunities WHERE source_opportunity_id = %s",
                                (doc_id,)
                            )
                            if cur.fetchone():
                                logger.info(f"Skipping duplicate: {doc_id}")
                                continue
                        
                        # Get or create source
                        domain = urlparse(url).netloc or "unknown"
                        if domain not in source_cache:
                            source_cache[domain] = get_or_create_adhoc_source(conn, url)
                        source_id = source_cache[domain]

                        # Prepare AI analysis JSON (includes Stage 2 details)
                        ai_analysis = {
                            "classification": {
                                "category": opp.get("predicted_category", "other"),
                                "confidence": opp.get("classification_confidence"),
                                "reason": opp.get("classification_reason"),
                            },
                            "extraction": {
                                "document_id": doc_id,
                                "event_name": opp.get("event_name"),
                                "document_url": opp.get("document_url"),
                            },
                            "stage2": {
                                "scope_of_work": opp.get("scope_of_work"),
                                "prequalification_details": opp.get("prequalification_details", []),
                            },
                            "crawl_session_id": crawl_session_id,
                        }

                        # Prepare contact info as JSON if present
                        contact_info = opp.get("contact_info")
                        contact_info_json = psycopg2.extras.Json(contact_info) if contact_info else None

                        # Prepare certifications as array
                        certifications = opp.get("certifications_required", [])
                        if not isinstance(certifications, list):
                            certifications = []

                        # Insert opportunity with all Stage 2 enrichment data
                        opp_id = uuid.uuid4()
                        cur.execute(
                            """
                            INSERT INTO opportunities (
                                id, source_id, source_opportunity_id, source_url, title,
                                state_code, status, categories, relevance_score,
                                submission_deadline, published_date, ai_analysis,
                                requires_prequalification, prequalification_deadline,
                                is_discretionary, estimated_value, eligibility_requirements,
                                certifications_required, contact_info,
                                created_at, updated_at
                            ) VALUES (
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s,
                                %s, %s,
                                %s, %s, %s,
                                %s, %s,
                                %s, %s
                            )
                            """,
                            (
                                str(opp_id),
                                str(source_id),
                                doc_id,
                                url,
                                opp.get("event_name", "Unknown Opportunity"),
                                "US",  # Default state code for ad-hoc scans
                                "new",  # OpportunityStatus.NEW
                                [opp.get("predicted_category", "other")],
                                opp.get("classification_confidence"),
                                parse_date(opp.get("response_due_date")),
                                parse_date(opp.get("event_start_date")),
                                psycopg2.extras.Json(ai_analysis),
                                opp.get("requires_prequalification", False),
                                parse_date(opp.get("prequalification_deadline")),
                                opp.get("is_discretionary", False),
                                opp.get("estimated_value"),
                                opp.get("eligibility_requirements"),
                                certifications,
                                contact_info_json,
                                datetime.utcnow(),
                                datetime.utcnow(),
                            )
                        )
                        saved_count += 1
                        logger.info(f"Saved opportunity: {doc_id} - {opp.get('event_name', 'Unknown')[:50]}")

                    except Exception as e:
                        logger.error(f"Failed to save opportunity {opp.get('document_id')}: {e}")
                        conn.rollback()
                        continue

            # Commit all successful inserts
            if saved_count > 0:
                conn.commit()
                logger.info(f"Successfully committed {saved_count} opportunities to database")

    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        conn.rollback()
    finally:
        conn.close()
        logger.info("Database connection closed")

    return saved_count

