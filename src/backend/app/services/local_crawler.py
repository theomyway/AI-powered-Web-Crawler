"""
Local Crawler Service for running crawls without Azure Functions.

This provides a fallback when Azure Functions are not configured,
allowing the crawl to run directly in the FastAPI backend.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

from openai import AzureOpenAI
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class LocalCrawlResult:
    """Result of local crawl operation."""
    results: list[dict[str, Any]] = field(default_factory=list)
    total_relevant: int = 0


class LocalCrawlerService:
    """Service for running crawls locally (without Azure Functions)."""
    
    def __init__(self):
        if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
            raise ValueError(
                "Azure OpenAI not configured. "
                "Please set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."
            )
        
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment = settings.azure_openai_deployment
        self.timeout = settings.crawler_timeout * 1000  # Convert to ms
        self.proxy_url = getattr(settings, 'crawler_proxy_url', None)
    
    async def crawl_urls(
        self,
        urls: list[str],
        categories: list[str] = None
    ) -> LocalCrawlResult:
        """
        Crawl URLs and extract RFP opportunities.
        
        Args:
            urls: List of URLs to crawl
            categories: Optional list of target categories
            
        Returns:
            LocalCrawlResult with extracted opportunities
        """
        result = LocalCrawlResult()
        
        for url in urls:
            try:
                url_result = await self._crawl_single_url(url)
                result.results.append(url_result)
                result.total_relevant += url_result.get("relevant_count", 0)
            except Exception as e:
                logger.error(f"Failed to crawl {url}: {e}")
                result.results.append({
                    "url": url,
                    "success": False,
                    "error": str(e),
                    "total_found": 0,
                    "relevant_count": 0,
                    "opportunities": []
                })
        
        return result
    
    async def _crawl_single_url(self, url: str) -> dict[str, Any]:
        """Crawl a single URL and extract opportunities."""
        start_time = datetime.utcnow()
        
        # Fetch HTML
        html_content = await self._fetch_page(url)
        
        if html_content is None:
            return {
                "url": url,
                "success": False,
                "error": "Failed to fetch page. May be geo-blocked or timeout.",
                "total_found": 0,
                "relevant_count": 0,
                "opportunities": []
            }
        
        # Extract and classify using GPT-4o
        opportunities = await self._extract_and_classify(html_content, url)
        
        relevant_count = sum(1 for o in opportunities if o.get("is_relevant"))
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "url": url,
            "success": True,
            "total_found": len(opportunities),
            "relevant_count": relevant_count,
            "opportunities": opportunities,
            "crawl_duration": duration
        }
    
    async def _fetch_page(self, url: str) -> str | None:
        """Fetch HTML content using Playwright."""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                
                context_options = {
                    "user_agent": settings.crawler_user_agent,
                    "viewport": {"width": 1920, "height": 1080},
                }
                
                if self.proxy_url:
                    context_options["proxy"] = {"server": self.proxy_url}
                
                context = await browser.new_context(**context_options)
                page = await context.new_page()
                page.set_default_timeout(self.timeout)
                
                try:
                    response = await page.goto(url, wait_until="networkidle")
                    
                    if response is None or not response.ok:
                        return None
                    
                    await page.wait_for_timeout(2000)
                    html = await page.content()
                    return html
                    
                finally:
                    await context.close()
                    await browser.close()
                    
        except PlaywrightTimeout:
            logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    async def _extract_and_classify(self, html_content: str, url: str) -> list[dict]:
        """Extract RFPs from HTML and classify using GPT-4o."""

        # Truncate if too large
        max_chars = 50000
        if len(html_content) > max_chars:
            html_content = html_content[:max_chars] + "\n... [truncated]"

        system_prompt = """You are an expert RFP analyst. Extract all RFP/RFQ/RFI opportunities from the HTML.

For EACH opportunity, extract:
- document_id: The RFP/RFI/RFQ number
- event_name: The title/name of the opportunity
- document_url: Link to the RFP document (if available)
- event_start_date: Start/posted date
- response_due_date: Submission deadline
- last_updated: Last update date

Classify each as RELEVANT or NOT RELEVANT based on:
RELEVANT: IT, software, AI, cloud, cybersecurity, ERP, CRM, consulting, professional services
NOT RELEVANT: Construction, janitorial, food, medical supplies, vehicles, printing, furniture

Return JSON:
{
  "opportunities": [
    {
      "document_id": "RFP 12345",
      "event_name": "IT Services",
      "document_url": "https://...",
      "event_start_date": "12/01/2025",
      "response_due_date": "02/20/2026",
      "last_updated": null,
      "is_relevant": true,
      "predicted_category": "staff_augmentation",
      "classification_confidence": 0.85,
      "classification_reason": "IT Services indicates technology consulting"
    }
  ]
}
"""

        # Run in thread pool since OpenAI client is sync
        loop = asyncio.get_event_loop()

        def call_openai():
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"URL: {url}\n\nHTML:\n{html_content}"}
                ],
                temperature=0.1,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)

        result = await loop.run_in_executor(None, call_openai)
        return result.get("opportunities", [])

