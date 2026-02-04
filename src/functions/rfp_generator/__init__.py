"""
RFP Response Generator Azure Function.

HTTP-triggered function that generates professional RFP response documents
using Azure Document Intelligence for text extraction and Azure OpenAI for generation.
"""

import json
import logging
from typing import Any

import azure.functions as func
import httpx

from shared.config import get_settings
from shared.document_processor import DocumentProcessorService
from shared.rfp_generator_service import RfpGeneratorService

logger = logging.getLogger(__name__)


async def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger for generating RFP responses.
    
    Expected JSON body:
    {
        "opportunity_id": "uuid",
        "opportunity_title": "string",
        "document_url": "string" (optional),
        "company_info": {
            "company_name": "string",
            "company_bio": "string" (optional),
            "relevant_experience": "string" (optional),
            "certifications": ["string"] (optional)
        },
        "opportunity_details": {
            "deadline": "string" (optional),
            "category": "string" (optional),
            "estimated_value": float (optional)
        }
    }
    
    Returns:
    {
        "success": true,
        "document_content": "markdown string",
        "message": "string"
    }
    """
    logger.info("RFP Response Generator function triggered")
    
    try:
        # Parse request body
        req_body = req.get_json()
        
        opportunity_id = req_body.get("opportunity_id")
        opportunity_title = req_body.get("opportunity_title", "Untitled Opportunity")
        document_url = req_body.get("document_url")
        company_info = req_body.get("company_info", {})
        opportunity_details = req_body.get("opportunity_details", {})
        
        if not opportunity_id:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "opportunity_id is required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        if not company_info.get("company_name"):
            return func.HttpResponse(
                json.dumps({"success": False, "error": "company_info.company_name is required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        logger.info("=" * 80)
        logger.info("RFP RESPONSE GENERATOR - PROCESSING REQUEST")
        logger.info("=" * 80)
        logger.info(f"Opportunity ID: {opportunity_id}")
        logger.info(f"Opportunity Title: {opportunity_title}")
        logger.info(f"Document URL: {document_url if document_url else 'NOT PROVIDED'}")
        logger.info(f"Company Name: {company_info.get('company_name', 'N/A')}")
        logger.info(f"Company Bio Length: {len(company_info.get('company_bio', '') or '')} chars")
        logger.info(f"Relevant Experience Length: {len(company_info.get('relevant_experience', '') or '')} chars")
        logger.info(f"Certifications: {company_info.get('certifications', [])}")
        logger.info(f"Opportunity Details: {opportunity_details}")
        logger.info("=" * 80)

        # Step 1: Extract text from RFP document if URL is provided
        rfp_content = ""
        if document_url:
            logger.info("Document URL provided - proceeding with extraction...")
            rfp_content = await extract_document_text(document_url)
            logger.info(f"Extraction complete. RFP content length: {len(rfp_content)} chars")
        else:
            logger.warning("NO DOCUMENT URL PROVIDED - Will generate generic response without RFP content")

        # Step 2: Generate RFP response using AI
        logger.info("=" * 80)
        logger.info("[STEP 2] AI RESPONSE GENERATION - Starting")
        logger.info("=" * 80)
        generator = RfpGeneratorService()
        response_content = generator.generate_response(
            rfp_content=rfp_content,
            opportunity_title=opportunity_title,
            company_info=company_info,
            opportunity_details=opportunity_details
        )

        logger.info("=" * 80)
        logger.info(f"[FINAL] RFP response generated successfully!")
        logger.info(f"  - Total response length: {len(response_content)} chars")
        logger.info("=" * 80)
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "document_content": response_content,
                "message": "RFP response generated successfully"
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logger.error(f"Error generating RFP response: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


async def extract_document_text(document_url: str) -> str:
    """
    Download and extract text from an RFP document.

    Uses PageCrawlerService for robust downloading with proxy support,
    then Azure Document Intelligence for text extraction.
    """
    logger.info("=" * 80)
    logger.info("[STEP 1] DOCUMENT EXTRACTION - Starting")
    logger.info("=" * 80)
    logger.info(f"[STEP 1.1] Document URL: {document_url}")

    try:
        # Use PageCrawlerService which has proxy support and stealth headers
        # This is the same approach used by the crawler
        from shared.page_crawler_lite import PageCrawlerService

        logger.info("[STEP 1.2] Using PageCrawlerService to download document...")
        crawler = PageCrawlerService()

        document_bytes, error = await crawler.download_document(document_url)

        if error:
            logger.error(f"[STEP 1.2] Download failed: {error}")
            return ""

        if not document_bytes:
            logger.error("[STEP 1.2] Download returned no data")
            return ""

        logger.info(f"[STEP 1.2] Download successful: {len(document_bytes)} bytes ({len(document_bytes)/1024:.2f} KB)")

        # Use Document Intelligence to extract text
        logger.info("-" * 40)
        logger.info("[STEP 1.3] Starting Document Intelligence text extraction...")
        logger.info("  - Page limit: 20 pages")

        processor = DocumentProcessorService(page_limit=20)
        extracted_text, extraction_error = processor.extract_text_from_bytes(
            document_bytes,
            process_all_pages=False  # Use page limit
        )

        if extraction_error:
            logger.warning(f"[STEP 1.4] Document Intelligence WARNING: {extraction_error}")

        if extracted_text:
            logger.info("[STEP 1.5] Text extraction SUCCESSFUL")
            logger.info(f"  - Total extracted length: {len(extracted_text)} characters")
            logger.info(f"  - Estimated tokens: ~{len(extracted_text) // 4}")
            logger.info("-" * 40)
            logger.info("[STEP 1.6] EXTRACTED TEXT PREVIEW (first 1500 chars):")
            logger.info("-" * 40)
            preview = extracted_text[:1500].replace('\n', '\n  ')
            logger.info(f"  {preview}")
            if len(extracted_text) > 1500:
                logger.info(f"  ... [truncated, {len(extracted_text) - 1500} more chars]")
            logger.info("-" * 40)
            logger.info("[STEP 1] DOCUMENT EXTRACTION - Complete")
            logger.info("=" * 80)
            return extracted_text

        logger.warning("[STEP 1.5] No text extracted from document - extraction returned empty")
        logger.info("=" * 80)
        return ""

    except Exception as e:
        logger.error(f"[STEP 1 ERROR] Failed to extract document text: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"  Stack trace: {traceback.format_exc()}")
        return ""

