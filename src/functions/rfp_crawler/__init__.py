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
import httpx
import azure.functions as func
from dataclasses import asdict
from datetime import datetime

from shared.config import get_settings
from shared.page_crawler import PageCrawlerService
from shared.ai_classifier import AIClassifierService
from shared.document_processor import DocumentProcessorService
from shared.models import OpportunityCategory, ExtractedRFP
from shared.db_service import save_opportunities_to_db

# Configure logging for Azure Functions - use root logger directly
logging.basicConfig(level=logging.INFO)


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
    logging.info(f"{timestamp} - {log_msg}")


async def callback_processing_status(
    backend_url: str,
    source_id: str,
    status: str,
    error_message: str = None,
    opportunities_found: int = None
):
    """
    Callback to the backend to update processing status.

    Args:
        backend_url: Base URL of the backend API
        source_id: UUID of the crawl source
        status: 'success' or 'failed'
        error_message: Error message if status is 'failed'
        opportunities_found: Number of opportunities found
    """
    if not backend_url or not source_id:
        logging.warning("Cannot callback: missing backend_url or source_id")
        return

    try:
        url = f"{backend_url}/api/v1/sources/{source_id}/status"
        payload = {
            "processing_status": status,
            "processing_error_message": error_message,
            "opportunities_found": opportunities_found
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(url, json=payload)

            if response.status_code == 200:
                logging.info(f"Successfully updated processing status for source {source_id} to {status}")
            else:
                logging.warning(f"Failed to update processing status: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Error calling back to backend: {e}")


async def callback_progress_update(
    backend_url: str,
    source_id: str,
    progress_percent: int,
    progress_message: str = None,
    current_processing_url: str = None
):
    """
    Callback to the backend to update real-time progress.

    Args:
        backend_url: Base URL of the backend API
        source_id: UUID of the crawl source
        progress_percent: Progress percentage (0-100)
        progress_message: Human-readable progress message
        current_processing_url: URL currently being processed
    """
    # VERY FIRST LINE - this MUST appear in logs
    logging.info(f"=== PROGRESS CALLBACK ENTERED === percent={progress_percent}, backend={backend_url}, source={source_id}")

    if not backend_url or not source_id:
        logging.warning(f"Progress update skipped: backend_url={backend_url}, source_id={source_id}")
        return  # Skip silently for ad-hoc URLs without source_id

    try:
        url = f"{backend_url}/api/v1/sources/{source_id}/progress"
        payload = {
            "progress_percent": min(max(progress_percent, 0), 100),
            "progress_message": progress_message,
            "current_processing_url": current_processing_url[:500] if current_processing_url else None
        }

        logging.info(f"Sending progress update: {progress_percent}% to {url}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(url, json=payload)

            if response.status_code != 200:
                logging.warning(f"Progress update response: {response.status_code} - {response.text}")
            else:
                logging.info(f"Progress update successful: {progress_percent}%")
    except Exception as e:
        # Don't fail the crawl if progress update fails
        logging.error(f"Progress update failed: {e}")


async def process_single_url(
    url: str,
    crawler: PageCrawlerService,
    classifier: AIClassifierService,
    doc_processor: DocumentProcessorService,
    state_code: str = "TN",
    enable_stage2: bool = True,
    # Progress tracking parameters
    url_index: int = 1,
    total_urls: int = 1,
    backend_url: str = None,
    source_id: str = None
) -> dict:
    """Process a single URL: fetch HTML, extract, classify, and optionally deep-analyze RFPs."""
    log_step(0, "URL Processing", "started", metrics={"url": url[:80] + "..." if len(url) > 80 else url})
    url_start_time = time.time()

    # Calculate progress for this URL (each URL gets an equal slice)
    # Progress stages within a URL: 10% start, 30% fetched, 50% extracted, 70% classifying, 90% classified, 100% done
    url_progress_base = ((url_index - 1) / total_urls) * 100
    url_progress_slice = 100 / total_urls

    def calc_progress(stage_percent: float) -> int:
        """Calculate overall progress: base + (stage_percent * this_url's_slice)"""
        return int(url_progress_base + (stage_percent / 100) * url_progress_slice)

    # Report starting this URL
    logging.info(f">>> CALLING PROGRESS CALLBACK: backend_url={backend_url}, source_id={source_id}")
    await callback_progress_update(
        backend_url, source_id,
        calc_progress(10),
        f"Starting URL {url_index}/{total_urls}",
        url
    )
    logging.info(">>> PROGRESS CALLBACK RETURNED")

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

    # Report page loaded
    await callback_progress_update(
        backend_url, source_id,
        calc_progress(30),
        f"Page loaded ({url_index}/{total_urls})",
        url
    )

    # Step 6-10: Extract and classify RFPs using GPT-4o (Stage 1)
    # Report AI classification starting
    await callback_progress_update(
        backend_url, source_id,
        calc_progress(50),
        f"Extracting content ({url_index}/{total_urls})",
        url
    )

    try:
        # Report AI classification in progress
        await callback_progress_update(
            backend_url, source_id,
            calc_progress(70),
            f"AI classification ({url_index}/{total_urls})",
            url
        )

        extracted_rfps = classifier.extract_and_classify_page(
            crawl_result.html_content,
            url
        )
    except Exception as e:
        logging.error(f"Classification failed for {url}: {e}")
        return {
            "url": url,
            "success": False,
            "error": f"AI classification failed: {str(e)}",
            "total_found": 0,
            "relevant_count": 0,
            "opportunities": [],
            "crawl_duration": time.time() - url_start_time
        }

    # Report classification complete
    await callback_progress_update(
        backend_url, source_id,
        calc_progress(90),
        f"Classification complete ({url_index}/{total_urls})",
        url
    )

    # === STAGE 2: Deep Analysis for Relevant Opportunities ===
    if enable_stage2:
        relevant_rfps = [rfp for rfp in extracted_rfps if rfp.is_relevant]

        if relevant_rfps:
            logging.info("\n" + "=" * 70)
            logging.info("=== STEP 3: STAGE 2 - DOCUMENT INTELLIGENCE & DEEP ANALYSIS ===")
            logging.info("=" * 70)
            logging.info(f"Processing {len(relevant_rfps)} relevant opportunities with Document Intelligence")

            for i, rfp in enumerate(relevant_rfps, 1):
                if not rfp.document_url:
                    logging.info(f"  [{i}] {rfp.document_id}: No document URL, skipping Stage 2")
                    continue

                logging.info(f"\n  [{i}] Processing: {rfp.document_id} - {rfp.event_name[:50]}...")
                logging.info(f"      Document URL: {rfp.document_url[:60]}...")

                try:
                    # Download PDF
                    stage2_start = time.time()
                    doc_bytes, download_error = await crawler.download_document(rfp.document_url)

                    if download_error:
                        logging.warning(f"      Download failed: {download_error}")
                        continue

                    logging.info(f"      Downloaded: {len(doc_bytes):,} bytes")

                    # Extract text using Document Intelligence (first 4 pages)
                    extracted_text, extract_error = doc_processor.extract_text_from_bytes(doc_bytes)

                    if extract_error:
                        logging.warning(f"      Text extraction failed: {extract_error}")
                        continue

                    logging.info(f"      Extracted: {len(extracted_text):,} characters from PDF")

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
                        logging.info(f"      âš¡ Category CHANGED: {old_category} â†’ {deep_result.confirmed_category.value}")
                    else:
                        logging.info(f"      âœ“ Category CONFIRMED: {deep_result.confirmed_category.value}")

                    logging.info(f"      Confidence: {old_confidence:.2f} â†’ {deep_result.category_confidence:.2f}")
                    logging.info(f"      Prequalification Required: {deep_result.requires_prequalification}")
                    if deep_result.requires_prequalification:
                        logging.info(f"      Prequal Deadline: {deep_result.prequalification_deadline}")
                        logging.info(f"      Prequal Details: {len(deep_result.prequalification_details)} requirements")
                    logging.info(f"      Summary: {deep_result.summary[:100]}...")
                    logging.info(f"      Stage 2 Duration: {time.time() - stage2_start:.2f}s")

                except Exception as e:
                    logging.error(f"      Stage 2 error for {rfp.document_id}: {e}")
                    continue

            logging.info("\n" + "=" * 70)

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
    logging.info("\n" + "=" * 70)
    logging.info("=== STEP 4: FINAL STRUCTURED OUTPUT ===")
    logging.info("=" * 70)
    logging.info(f"URL: {url}")
    logging.info(f"Processing Duration: {total_duration:.2f}s")
    logging.info(f"\n--- SUMMARY ---")
    logging.info(f"Total Opportunities Found: {len(extracted_rfps)}")
    logging.info(f"Relevant Opportunities: {relevant_count}")
    logging.info(f"Not Relevant: {len(extracted_rfps) - relevant_count}")

    # Category breakdown
    category_counts = {}
    for rfp in extracted_rfps:
        cat = rfp.predicted_category.value
        category_counts[cat] = category_counts.get(cat, 0) + 1

    logging.info(f"\n--- CATEGORY BREAKDOWN ---")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        logging.info(f"  {cat}: {count}")

    # List relevant opportunities
    relevant_rfps = [rfp for rfp in extracted_rfps if rfp.is_relevant]
    if relevant_rfps:
        logging.info(f"\n--- RELEVANT OPPORTUNITIES DETAILS ---")
        for i, rfp in enumerate(relevant_rfps, 1):
            logging.info(f"\n  [{i}] {rfp.document_id}")
            logging.info(f"      Name: {rfp.event_name}")
            logging.info(f"      Category: {rfp.predicted_category.value}")
            logging.info(f"      Confidence: {rfp.classification_confidence:.2f}")
            logging.info(f"      Due Date: {rfp.response_due_date}")
            if rfp.document_url:
                logging.info(f"      Document: {rfp.document_url[:70]}...")

    logging.info("\n" + "=" * 70)
    logging.info("=== FINAL JSON RESPONSE PREVIEW ===")
    logging.info("=" * 70)
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
    logging.info(json.dumps(result_preview, indent=2))
    logging.info("=" * 70 + "\n")

    log_step(11, "URL Processing", "completed", duration=total_duration,
            metrics={
                "total_found": len(extracted_rfps),
                "relevant": relevant_count,
                "not_relevant": len(extracted_rfps) - relevant_count
            })

    # Report URL complete (100% of this URL's slice)
    await callback_progress_update(
        backend_url, source_id,
        calc_progress(100),
        f"URL {url_index}/{total_urls} complete",
        url
    )

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

    logging.info("=" * 80)
    logging.info("RFP CRAWLER FUNCTION TRIGGERED")
    logging.info("=" * 80)

    # Track source_ids and backend_url for callbacks
    source_ids = []
    backend_url = None

    try:
        # Parse request
        req_body = req.get_json()
        urls = req_body.get("urls", [])
        crawl_session_id = req_body.get("crawl_session_id", str(datetime.utcnow().timestamp()))
        state_code = req_body.get("state_code", "TN")
        source_ids = req_body.get("source_ids", [])  # Source IDs for callback
        backend_url = req_body.get("backend_url")  # Backend URL for callback
        categories = req_body.get("categories", [])  # User-selected categories for filtering

        # DEBUG: Log the actual values of callback parameters
        logging.info(f"!!! CALLBACK PARAMS: backend_url={backend_url}, source_ids={source_ids}")
        logging.info(f"!!! SELECTED CATEGORIES: {categories}")

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
            "stage2_enabled": enable_stage2,
            "categories": categories or "ALL",
            "has_source_ids": len([s for s in source_ids if s]) > 0,
            "has_backend_url": backend_url is not None
        })

        # Initialize services with selected categories for filtering
        crawler = PageCrawlerService()
        classifier = AIClassifierService(selected_categories=categories if categories else None)
        doc_processor = DocumentProcessorService(page_limit=4)  # First 4 pages for classification

        results = []
        total_relevant = 0
        total_found = 0

        for i, url in enumerate(urls, 1):
            logging.info(f"\n{'='*60}")
            logging.info(f"Processing URL {i}/{len(urls)}")
            logging.info(f"{'='*60}")

            # Get source_id for this URL (source_ids are parallel to urls)
            source_id = source_ids[i - 1] if i - 1 < len(source_ids) else None

            url_result = await process_single_url(
                url, crawler, classifier, doc_processor,
                state_code, enable_stage2,
                # Progress tracking parameters
                url_index=i,
                total_urls=len(urls),
                backend_url=backend_url,
                source_id=source_id
            )
            results.append(url_result)
            total_relevant += url_result.get("relevant_count", 0)
            total_found += url_result.get("total_found", 0)

        processing_time = time.time() - start_time

        # === STEP 5: SAVE OPPORTUNITIES TO DATABASE ===
        logging.info("\n" + "=" * 80)
        logging.info("=== STEP 5: SAVING OPPORTUNITIES TO DATABASE ===")
        logging.info("=" * 80)

        saved_count = 0
        db_error = None
        try:
            saved_count = save_opportunities_to_db(results, crawl_session_id)
            logging.info(f"Successfully saved {saved_count} opportunities to database")
        except Exception as e:
            db_error = str(e)
            logging.error(f"Database save failed: {e}", exc_info=True)

        # Final summary
        logging.info("\n" + "=" * 80)
        logging.info("CRAWL SESSION COMPLETE")
        logging.info("=" * 80)
        log_step(12, "Session Complete", "success", duration=processing_time, metrics={
            "urls_processed": len(urls),
            "total_opportunities": total_found,
            "relevant_opportunities": total_relevant,
            "saved_to_db": saved_count,
            "not_relevant": total_found - total_relevant
        })

        # === CALLBACK TO BACKEND: Update processing status ===
        if backend_url and source_ids:
            for source_id in source_ids:
                if source_id:  # Skip None entries (ad-hoc URLs)
                    status = "failed" if db_error else "success"
                    await callback_processing_status(
                        backend_url=backend_url,
                        source_id=source_id,
                        status=status,
                        error_message=db_error,
                        opportunities_found=saved_count
                    )

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
        logging.error(f"Invalid request: {e}")
        # Callback with failure status
        if backend_url and source_ids:
            for source_id in source_ids:
                if source_id:
                    await callback_processing_status(
                        backend_url=backend_url,
                        source_id=source_id,
                        status="failed",
                        error_message=f"Invalid request: {str(e)}"
                    )
        return func.HttpResponse(
            json.dumps({"success": False, "error": f"Invalid request: {str(e)}"}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        # Callback with failure status
        if backend_url and source_ids:
            for source_id in source_ids:
                if source_id:
                    await callback_processing_status(
                        backend_url=backend_url,
                        source_id=source_id,
                        status="failed",
                        error_message=f"Internal error: {str(e)}"
                    )
        return func.HttpResponse(
            json.dumps({"success": False, "error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )


async def process_servicebus_message(message_body: str) -> None:
    """
    Process a single URL from a Service Bus queue message.

    This function handles sequential processing of URLs - one at a time.
    Each message contains a single URL to crawl.

    Args:
        message_body: JSON string containing url, source_id, categories, etc.
    """
    start_time = time.time()

    logging.info("=" * 80)
    logging.info("SERVICE BUS MESSAGE PROCESSING STARTED")
    logging.info("=" * 80)

    # Parse message
    try:
        message = json.loads(message_body)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in message: {e}")
        raise ValueError(f"Invalid JSON message: {e}")

    url = message.get("url")
    source_id = message.get("source_id")
    crawl_session_id = message.get("crawl_session_id", str(datetime.utcnow().timestamp()))
    categories = message.get("categories", [])
    backend_url = message.get("backend_url")
    state_code = message.get("state_code", "TN")

    if not url:
        logging.error("No URL in message")
        raise ValueError("No URL provided in message")

    logging.info(f"Processing URL: {url[:80]}...")
    logging.info(f"Source ID: {source_id}")
    logging.info(f"Session ID: {crawl_session_id}")
    logging.info(f"Categories: {categories}")
    logging.info(f"Backend URL: {backend_url}")

    # Update status to 'processing' immediately when we start
    if backend_url and source_id:
        await callback_processing_status(
            backend_url=backend_url,
            source_id=source_id,
            status="processing"
        )

    try:
        # Initialize services
        crawler = PageCrawlerService()
        classifier = AIClassifierService(selected_categories=categories if categories else None)
        doc_processor = DocumentProcessorService(page_limit=4)

        # Process the single URL
        result = await process_single_url(
            url=url,
            crawler=crawler,
            classifier=classifier,
            doc_processor=doc_processor,
            state_code=state_code,
            enable_stage2=True,
            url_index=1,
            total_urls=1,
            backend_url=backend_url,
            source_id=source_id
        )

        processing_time = time.time() - start_time

        # Save opportunities to database
        saved_count = 0
        db_error = None

        if result.get("success"):
            try:
                saved_count = save_opportunities_to_db([result], crawl_session_id)
                logging.info(f"Saved {saved_count} opportunities to database")
            except Exception as e:
                db_error = str(e)
                logging.error(f"Database save failed: {e}", exc_info=True)

        # Callback to backend with success/failure status
        if backend_url and source_id:
            status = "failed" if db_error or not result.get("success") else "success"
            error_msg = db_error or result.get("error")

            await callback_processing_status(
                backend_url=backend_url,
                source_id=source_id,
                status=status,
                error_message=error_msg,
                opportunities_found=saved_count
            )

        logging.info("=" * 80)
        logging.info(f"SERVICE BUS MESSAGE PROCESSING COMPLETE")
        logging.info(f"Duration: {processing_time:.2f}s")
        logging.info(f"Saved: {saved_count} opportunities")
        logging.info("=" * 80)

    except Exception as e:
        logging.error(f"Error processing URL {url}: {e}", exc_info=True)

        # Callback with failure status
        if backend_url and source_id:
            await callback_processing_status(
                backend_url=backend_url,
                source_id=source_id,
                status="failed",
                error_message=f"Processing error: {str(e)}"
            )

        # Re-raise so the message goes to dead-letter queue
        raise
