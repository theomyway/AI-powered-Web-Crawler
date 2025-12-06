"""
Azure Function: RFP Crawler (Unified)

Single HTTP-triggered function that handles the complete crawling flow:
1. Accept URLs from the frontend
2. Fetch HTML content using Playwright (async)
3. Extract and classify RFPs using Azure OpenAI GPT-4o
4. Return all results to the caller

Features:
- Comprehensive step-by-step logging with timestamps and metrics
- Intelligent HTML parsing to extract just RFP table content
- Token limit management with automatic chunking
- Full page scrolling to trigger lazy-loaded content

This consolidates the previous separate functions into one async flow.
"""

import json
import logging
import time
import azure.functions as func
from dataclasses import asdict
from datetime import datetime

from shared.config import get_settings
from shared.page_crawler import PageCrawlerService
from shared.ai_classifier import AIClassifierService
from shared.document_processor import DocumentProcessorService
from shared.models import OpportunityCategory, ExtractedRFP
from shared.db_service import save_opportunities_to_db

logger = logging.getLogger(__name__)


def log_step(step_num: int, step_name: str, status: str,
             duration: float = None, metrics: dict = None):
    """Log a processing step with standardized format."""
    timestamp = datetime.utcnow().isoformat()
    log_msg = f"[Step {step_num}] {step_name}: {status}"
    if duration is not None:
        log_msg += f" (duration: {duration:.2f}s)"
    if metrics:
        metrics_str = ", ".join(f"{k}={v}" for k, v in metrics.items())
        log_msg += f" | {metrics_str}"
    logger.info(f"{timestamp} - {log_msg}")


async def process_single_url(
    url: str,
    crawler: PageCrawlerService,
    classifier: AIClassifierService,
    doc_processor: DocumentProcessorService,
    state_code: str = "TN",
    enable_stage2: bool = True
) -> dict:
    """Process a single URL: fetch HTML, extract, classify, and optionally deep-analyze RFPs."""
    log_step(0, "URL Processing", "started", metrics={"url": url[:80] + "..." if len(url) > 80 else url})
    url_start_time = time.time()

    # Step 1-5: Fetch HTML content (async) - detailed logging in PageCrawlerService
    crawl_result = await crawler.fetch_page(url)

    if not crawl_result.success:
        log_step(0, "URL Processing", "failed",
                duration=time.time() - url_start_time,
                metrics={"error": crawl_result.error_message[:50]})
        return {
            "url": url,
            "success": False,
            "error": crawl_result.error_message,
            "total_found": 0,
            "relevant_count": 0,
            "opportunities": [],
            "crawl_duration": time.time() - url_start_time
        }

    log_step(6, "HTML Fetched", "success",
            metrics={"html_chars": len(crawl_result.html_content)})

    # Step 6-10: Extract and classify RFPs using GPT-4o (Stage 1)
    try:
        extracted_rfps = classifier.extract_and_classify_page(
            crawl_result.html_content,
            url
        )
    except Exception as e:
        logger.error(f"Classification failed for {url}: {e}")
        return {
            "url": url,
            "success": False,
            "error": f"AI classification failed: {str(e)}",
            "total_found": 0,
            "relevant_count": 0,
            "opportunities": [],
            "crawl_duration": time.time() - url_start_time
        }

    # === STAGE 2: Deep Analysis for Relevant Opportunities ===
    if enable_stage2:
        relevant_rfps = [rfp for rfp in extracted_rfps if rfp.is_relevant]

        if relevant_rfps:
            logger.info("\n" + "=" * 70)
            logger.info("=== STEP 3: STAGE 2 - DOCUMENT INTELLIGENCE & DEEP ANALYSIS ===")
            logger.info("=" * 70)
            logger.info(f"Processing {len(relevant_rfps)} relevant opportunities with Document Intelligence")

            for i, rfp in enumerate(relevant_rfps, 1):
                if not rfp.document_url:
                    logger.info(f"  [{i}] {rfp.document_id}: No document URL, skipping Stage 2")
                    continue

                logger.info(f"\n  [{i}] Processing: {rfp.document_id} - {rfp.event_name[:50]}...")
                logger.info(f"      Document URL: {rfp.document_url[:60]}...")

                try:
                    # Download PDF
                    stage2_start = time.time()
                    doc_bytes, download_error = await crawler.download_document(rfp.document_url)

                    if download_error:
                        logger.warning(f"      Download failed: {download_error}")
                        continue

                    logger.info(f"      Downloaded: {len(doc_bytes):,} bytes")

                    # Extract text using Document Intelligence (first 4 pages)
                    extracted_text, extract_error = doc_processor.extract_text_from_bytes(doc_bytes)

                    if extract_error:
                        logger.warning(f"      Text extraction failed: {extract_error}")
                        continue

                    logger.info(f"      Extracted: {len(extracted_text):,} characters from PDF")

                    # Deep analysis with GPT-4o (Stage 2)
                    deep_result = classifier.deep_analyze_document(extracted_text, rfp)

                    # Update RFP with Stage 2 results - Classification
                    old_category = rfp.predicted_category.value
                    old_confidence = rfp.classification_confidence

                    rfp.predicted_category = deep_result.confirmed_category
                    rfp.classification_confidence = deep_result.category_confidence
                    rfp.classification_reason = deep_result.summary

                    # Update RFP with Stage 2 results - Prequalification & Details
                    rfp.requires_prequalification = deep_result.requires_prequalification
                    rfp.prequalification_details = deep_result.prequalification_details
                    rfp.eligibility_requirements = deep_result.eligibility_requirements
                    rfp.certifications_required = deep_result.certifications_required
                    rfp.estimated_value = deep_result.estimated_value
                    rfp.is_discretionary = deep_result.is_discretionary
                    rfp.contact_info = deep_result.contact_info
                    rfp.scope_of_work = deep_result.scope_of_work

                    # Extract prequalification deadline if available
                    if deep_result.prequalification_deadline:
                        rfp.prequalification_deadline = str(deep_result.prequalification_deadline)

                    # Check if classification changed
                    if old_category != deep_result.confirmed_category.value:
                        logger.info(f"      ⚡ Category CHANGED: {old_category} → {deep_result.confirmed_category.value}")
                    else:
                        logger.info(f"      ✓ Category CONFIRMED: {deep_result.confirmed_category.value}")

                    logger.info(f"      Confidence: {old_confidence:.2f} → {deep_result.category_confidence:.2f}")
                    logger.info(f"      Prequalification Required: {deep_result.requires_prequalification}")
                    if deep_result.requires_prequalification:
                        logger.info(f"      Prequal Deadline: {deep_result.prequalification_deadline}")
                        logger.info(f"      Prequal Details: {len(deep_result.prequalification_details)} requirements")
                    logger.info(f"      Summary: {deep_result.summary[:100]}...")
                    logger.info(f"      Stage 2 Duration: {time.time() - stage2_start:.2f}s")

                except Exception as e:
                    logger.error(f"      Stage 2 error for {rfp.document_id}: {e}")
                    continue

            logger.info("\n" + "=" * 70)

    # Convert to dict for JSON response
    opportunities_dict = []
    for rfp in extracted_rfps:
        opp = asdict(rfp)
        # Convert enum to string value
        opp["predicted_category"] = rfp.predicted_category.value
        opportunities_dict.append(opp)

    relevant_count = sum(1 for rfp in extracted_rfps if rfp.is_relevant)
    total_duration = time.time() - url_start_time

    # === ENHANCED LOGGING: FINAL STRUCTURED OUTPUT ===
    logger.info("\n" + "=" * 70)
    logger.info("=== STEP 4: FINAL STRUCTURED OUTPUT ===")
    logger.info("=" * 70)
    logger.info(f"URL: {url}")
    logger.info(f"Processing Duration: {total_duration:.2f}s")
    logger.info(f"\n--- SUMMARY ---")
    logger.info(f"Total Opportunities Found: {len(extracted_rfps)}")
    logger.info(f"Relevant Opportunities: {relevant_count}")
    logger.info(f"Not Relevant: {len(extracted_rfps) - relevant_count}")

    # Category breakdown
    category_counts = {}
    for rfp in extracted_rfps:
        cat = rfp.predicted_category.value
        category_counts[cat] = category_counts.get(cat, 0) + 1

    logger.info(f"\n--- CATEGORY BREAKDOWN ---")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {cat}: {count}")

    # List relevant opportunities
    relevant_rfps = [rfp for rfp in extracted_rfps if rfp.is_relevant]
    if relevant_rfps:
        logger.info(f"\n--- RELEVANT OPPORTUNITIES DETAILS ---")
        for i, rfp in enumerate(relevant_rfps, 1):
            logger.info(f"\n  [{i}] {rfp.document_id}")
            logger.info(f"      Name: {rfp.event_name}")
            logger.info(f"      Category: {rfp.predicted_category.value}")
            logger.info(f"      Confidence: {rfp.classification_confidence:.2f}")
            logger.info(f"      Due Date: {rfp.response_due_date}")
            if rfp.document_url:
                logger.info(f"      Document: {rfp.document_url[:70]}...")

    logger.info("\n" + "=" * 70)
    logger.info("=== FINAL JSON RESPONSE PREVIEW ===")
    logger.info("=" * 70)
    # Show truncated JSON preview
    result_preview = {
        "url": url[:60] + "..." if len(url) > 60 else url,
        "success": True,
        "total_found": len(extracted_rfps),
        "relevant_count": relevant_count,
        "opportunities_preview": [
            {"id": o["document_id"], "name": o["event_name"][:40], "relevant": o["is_relevant"]}
            for o in opportunities_dict[:5]
        ]
    }
    logger.info(json.dumps(result_preview, indent=2))
    logger.info("=" * 70 + "\n")

    log_step(11, "URL Processing", "completed", duration=total_duration,
            metrics={
                "total_found": len(extracted_rfps),
                "relevant": relevant_count,
                "not_relevant": len(extracted_rfps) - relevant_count
            })

    return {
        "url": url,
        "success": True,
        "total_found": len(extracted_rfps),
        "relevant_count": relevant_count,
        "opportunities": opportunities_dict,
        "crawl_duration": total_duration
    }


async def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger for unified RFP crawling and classification.

    Request body:
    {
        "urls": ["https://..."],
        "crawl_session_id": "uuid",
        "categories": ["dynamics", "ai", "erp"],
        "state_code": "TN"
    }

    Response:
    {
        "success": true,
        "crawl_session_id": "...",
        "results": [...],
        "total_relevant": 3,
        "processing_time": 12.5,
        "metrics": {...}
    }
    """
    start_time = time.time()

    logger.info("=" * 80)
    logger.info("RFP CRAWLER FUNCTION TRIGGERED")
    logger.info("=" * 80)

    try:
        # Parse request
        req_body = req.get_json()
        urls = req_body.get("urls", [])
        crawl_session_id = req_body.get("crawl_session_id", str(datetime.utcnow().timestamp()))
        state_code = req_body.get("state_code", "TN")

        if not urls:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "No URLs provided"}),
                status_code=400,
                mimetype="application/json"
            )

        # Check if Stage 2 (Document Intelligence) is enabled
        enable_stage2 = req_body.get("enable_stage2", True)  # Default to enabled

        log_step(0, "Request Received", "processing", metrics={
            "urls_count": len(urls),
            "session_id": crawl_session_id,
            "state_code": state_code,
            "stage2_enabled": enable_stage2
        })

        # Initialize services
        crawler = PageCrawlerService()
        classifier = AIClassifierService()
        doc_processor = DocumentProcessorService(page_limit=4)  # First 4 pages for classification

        results = []
        total_relevant = 0
        total_found = 0

        for i, url in enumerate(urls, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing URL {i}/{len(urls)}")
            logger.info(f"{'='*60}")

            url_result = await process_single_url(
                url, crawler, classifier, doc_processor,
                state_code, enable_stage2
            )
            results.append(url_result)
            total_relevant += url_result.get("relevant_count", 0)
            total_found += url_result.get("total_found", 0)

        processing_time = time.time() - start_time

        # === STEP 5: SAVE OPPORTUNITIES TO DATABASE ===
        logger.info("\n" + "=" * 80)
        logger.info("=== STEP 5: SAVING OPPORTUNITIES TO DATABASE ===")
        logger.info("=" * 80)

        saved_count = 0
        db_error = None
        try:
            saved_count = save_opportunities_to_db(results, crawl_session_id)
            logger.info(f"Successfully saved {saved_count} opportunities to database")
        except Exception as e:
            db_error = str(e)
            logger.error(f"Database save failed: {e}", exc_info=True)

        # Final summary
        logger.info("\n" + "=" * 80)
        logger.info("CRAWL SESSION COMPLETE")
        logger.info("=" * 80)
        log_step(12, "Session Complete", "success", duration=processing_time, metrics={
            "urls_processed": len(urls),
            "total_opportunities": total_found,
            "relevant_opportunities": total_relevant,
            "saved_to_db": saved_count,
            "not_relevant": total_found - total_relevant
        })

        # Return summary response (without full opportunity data to reduce payload)
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "crawl_session_id": crawl_session_id,
                "total_found": total_found,
                "total_relevant": total_relevant,
                "saved_to_db": saved_count,
                "db_error": db_error,
                "processing_time": processing_time,
                "metrics": {
                    "urls_processed": len(urls),
                    "total_opportunities_found": total_found,
                    "relevant_opportunities": total_relevant,
                    "saved_to_database": saved_count,
                    "not_relevant": total_found - total_relevant
                }
            }),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": f"Invalid request: {str(e)}"}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"success": False, "error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )

