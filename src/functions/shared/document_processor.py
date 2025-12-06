"""
Document Processor Service using Azure Document Intelligence.

Extracts text from PDF/DOCX documents for AI analysis.

Features:
- Page limit optimization: Only processes first N pages for classification
- Comprehensive logging with metrics
- Cost optimization for large documents
"""

import logging
import io
import time
from datetime import datetime
from typing import Optional

from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.config import get_settings

logger = logging.getLogger(__name__)

# Default page limit for classification (first 4 pages usually contain key info)
DEFAULT_PAGE_LIMIT = 4


class DocumentProcessorService:
    """Service for extracting text from documents using Azure Document Intelligence."""

    def __init__(self, page_limit: int = DEFAULT_PAGE_LIMIT):
        """
        Initialize the document processor.

        Args:
            page_limit: Maximum number of pages to process (default: 4).
                       Set to 0 or None to process all pages.
        """
        settings = get_settings()
        self.endpoint = settings.azure_doc_intelligence_endpoint
        self.key = settings.azure_doc_intelligence_key
        self.page_limit = page_limit
        self._client: Optional[DocumentAnalysisClient] = None

    def _log_step(self, step_name: str, status: str,
                  duration: float = None, metrics: dict = None):
        """Log a processing step with standardized format."""
        timestamp = datetime.utcnow().isoformat()
        log_msg = f"[DocProcessor] {step_name}: {status}"
        if duration is not None:
            log_msg += f" (duration: {duration:.2f}s)"
        if metrics:
            metrics_str = ", ".join(f"{k}={v}" for k, v in metrics.items())
            log_msg += f" | {metrics_str}"
        logger.info(f"{timestamp} - {log_msg}")

    @property
    def client(self) -> DocumentAnalysisClient:
        """Lazy-initialize the Document Analysis client."""
        if self._client is None:
            if not self.endpoint or not self.key:
                raise ValueError(
                    "Azure Document Intelligence not configured. "
                    "Please set AZURE_DOC_INTELLIGENCE_ENDPOINT and AZURE_DOC_INTELLIGENCE_KEY."
                )
            self._client = DocumentAnalysisClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.key)
            )
        return self._client

    def _get_pages_param(self) -> Optional[str]:
        """Get the pages parameter for Document Intelligence API."""
        if self.page_limit and self.page_limit > 0:
            return f"1-{self.page_limit}"
        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def extract_text_from_bytes(self, document_bytes: bytes,
                                 process_all_pages: bool = False) -> tuple[str | None, str | None]:
        """
        Extract text from a document provided as bytes.

        Args:
            document_bytes: The document content as bytes
            process_all_pages: If True, process all pages regardless of page_limit

        Returns:
            Tuple of (extracted_text, error_message)
        """
        start_time = time.time()
        pages_param = None if process_all_pages else self._get_pages_param()

        self._log_step("Text Extraction", "started", metrics={
            "bytes": len(document_bytes),
            "pages_limit": pages_param or "all"
        })

        try:
            # Use the prebuilt-read model for general document text extraction
            # Pass pages parameter to limit processing
            kwargs = {}
            if pages_param:
                kwargs["pages"] = pages_param

            poller = self.client.begin_analyze_document(
                "prebuilt-read",
                document=io.BytesIO(document_bytes),
                **kwargs
            )
            result = poller.result()

            # Extract all text content
            text_parts = []
            pages_processed = 0
            for page in result.pages:
                pages_processed += 1
                for line in page.lines:
                    text_parts.append(line.content)
                text_parts.append(f"\n--- Page {page.page_number} ---\n")

            extracted_text = "\n".join(text_parts)
            duration = time.time() - start_time

            self._log_step("Text Extraction", "completed", duration=duration, metrics={
                "pages_processed": pages_processed,
                "chars_extracted": len(extracted_text)
            })

            return extracted_text, None

        except Exception as e:
            error = f"Document extraction failed: {str(e)}"
            logger.error(error)
            return None, error

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def extract_text_from_url(self, document_url: str,
                               process_all_pages: bool = False) -> tuple[str | None, str | None]:
        """
        Extract text from a document at a URL.

        Note: Azure Document Intelligence can analyze documents from URLs,
        but the URL must be publicly accessible.

        Args:
            document_url: The URL of the document
            process_all_pages: If True, process all pages regardless of page_limit

        Returns:
            Tuple of (extracted_text, error_message)
        """
        start_time = time.time()
        pages_param = None if process_all_pages else self._get_pages_param()

        self._log_step("URL Text Extraction", "started", metrics={
            "url": document_url[:60] + "..." if len(document_url) > 60 else document_url,
            "pages_limit": pages_param or "all"
        })

        try:
            # Pass pages parameter to limit processing
            kwargs = {}
            if pages_param:
                kwargs["pages"] = pages_param

            poller = self.client.begin_analyze_document_from_url(
                "prebuilt-read",
                document_url=document_url,
                **kwargs
            )
            result = poller.result()

            text_parts = []
            pages_processed = 0
            for page in result.pages:
                pages_processed += 1
                for line in page.lines:
                    text_parts.append(line.content)
                text_parts.append(f"\n--- Page {page.page_number} ---\n")

            extracted_text = "\n".join(text_parts)
            duration = time.time() - start_time

            self._log_step("URL Text Extraction", "completed", duration=duration, metrics={
                "pages_processed": pages_processed,
                "chars_extracted": len(extracted_text)
            })

            return extracted_text, None

        except Exception as e:
            error = f"Document extraction from URL failed: {str(e)}"
            logger.error(error)
            return None, error


class FallbackTextExtractor:
    """Fallback text extraction using pypdf and python-docx."""

    @staticmethod
    def extract_from_pdf(pdf_bytes: bytes,
                         page_limit: int = DEFAULT_PAGE_LIMIT) -> tuple[str | None, str | None]:
        """
        Extract text from PDF using pypdf.

        Args:
            pdf_bytes: The PDF content as bytes
            page_limit: Maximum number of pages to process (0 or None for all)
        """
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            text_parts = []
            total_pages = len(reader.pages)
            pages_to_process = min(page_limit, total_pages) if page_limit else total_pages

            for i, page in enumerate(reader.pages[:pages_to_process]):
                text_parts.append(page.extract_text())
                text_parts.append(f"\n--- Page {i+1} ---\n")

            if pages_to_process < total_pages:
                text_parts.append(f"\n[Note: Processed {pages_to_process} of {total_pages} pages]\n")

            logger.info(f"Extracted text from {pages_to_process}/{total_pages} PDF pages")
            return "\n".join(text_parts), None
        except Exception as e:
            return None, f"PDF extraction failed: {str(e)}"

    @staticmethod
    def extract_from_docx(docx_bytes: bytes) -> tuple[str | None, str | None]:
        """Extract text from DOCX using python-docx."""
        try:
            from docx import Document
            doc = Document(io.BytesIO(docx_bytes))
            text_parts = [para.text for para in doc.paragraphs]
            return "\n".join(text_parts), None
        except Exception as e:
            return None, f"DOCX extraction failed: {str(e)}"

