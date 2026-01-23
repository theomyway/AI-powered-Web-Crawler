"""
Lightweight Page Crawler Service using httpx + BeautifulSoup.

This is a drop-in replacement for the Playwright-based crawler that can run
on Azure Functions Consumption Plan without Docker.

Handles:
- Fetching HTML content from URLs using async httpx
- Proxy support for geo-restricted sites
- Retry logic with exponential backoff
- Stealth headers to avoid bot detection
- Graceful error handling with detailed diagnostics

Limitations:
- No JavaScript rendering (works for most government RFP sites)
- For JS-heavy sites, consider using a headless browser API service

Note: Uses async httpx to work with Azure Functions asyncio loop.
"""

import asyncio
import logging
import random
import time
from datetime import datetime
from enum import Enum

import httpx

from shared.config import get_settings
from shared.models import CrawlResult

logger = logging.getLogger(__name__)


class CrawlErrorType(Enum):
    """Types of errors that can occur during crawling."""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    GEO_BLOCKED = "geo_blocked"
    BOT_DETECTED = "bot_detected"
    CONNECTION_ERROR = "connection_error"
    SSL_ERROR = "ssl_error"
    DNS_ERROR = "dns_error"
    HTTP_ERROR = "http_error"
    UNKNOWN = "unknown"


# Realistic browser user agents (Chrome on Windows)
STEALTH_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class PageCrawlerService:
    """
    Lightweight service for crawling web pages using httpx.
    
    This is a drop-in replacement for the Playwright-based PageCrawlerService.
    It maintains the same interface but uses simple HTTP requests instead of
    a headless browser.
    """

    def __init__(self):
        self.settings = get_settings()
        # Convert timeout from ms to seconds for httpx
        self.timeout_seconds = self.settings.crawler_timeout / 1000
        self.navigation_timeout_seconds = self.settings.crawler_navigation_timeout / 1000
        self.max_retries = self.settings.crawler_max_retries
        self.stealth_mode = self.settings.crawler_stealth_mode

    def _log_step(self, step_num: int, step_name: str, status: str,
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

    def _get_user_agent(self) -> str:
        """Get user agent - either configured or random stealth."""
        if self.settings.crawler_user_agent:
            return self.settings.crawler_user_agent
        return random.choice(STEALTH_USER_AGENTS)

    def _get_headers(self) -> dict:
        """Build request headers with stealth options."""
        headers = {
            "User-Agent": self._get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        }
        
        if self.stealth_mode:
            headers.update({
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            })
        
        return headers

    def _get_proxy_url(self) -> str | None:
        """Build proxy URL for httpx."""
        if not self.settings.crawler_proxy_url:
            return None

        proxy_url = self.settings.crawler_proxy_url
        
        # If credentials provided, insert them into the URL
        if self.settings.crawler_proxy_username:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(proxy_url)
            username = self.settings.crawler_proxy_username
            password = self.settings.crawler_proxy_password or ""
            netloc = f"{username}:{password}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            proxy_url = urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
        
        return proxy_url

    def _classify_error(self, error: Exception, response: httpx.Response = None) -> tuple[CrawlErrorType, str]:
        """Classify the error type and provide helpful message."""
        error_str = str(error).lower()

        # Check response status codes first
        if response is not None:
            status = response.status_code
            if status == 403:
                return CrawlErrorType.GEO_BLOCKED, (
                    "HTTP 403 Forbidden: Access denied. This may be due to geo-blocking. "
                    "Try using a US-based VPN or proxy."
                )
            elif status == 451:
                return CrawlErrorType.GEO_BLOCKED, (
                    "HTTP 451 Unavailable For Legal Reasons: Content blocked in your region."
                )
            elif status == 429:
                return CrawlErrorType.BOT_DETECTED, (
                    "HTTP 429 Too Many Requests: Rate limited. Wait before retrying."
                )
            elif status == 503:
                return CrawlErrorType.BOT_DETECTED, (
                    "HTTP 503 Service Unavailable: May indicate bot detection or server issues."
                )
            elif 400 <= status < 500:
                return CrawlErrorType.HTTP_ERROR, f"HTTP {status}: Client error accessing the page."
            elif 500 <= status < 600:
                return CrawlErrorType.HTTP_ERROR, f"HTTP {status}: Server error. Try again later."

        # Timeout errors
        if isinstance(error, httpx.TimeoutException) or "timeout" in error_str:
            return CrawlErrorType.TIMEOUT, (
                "Request timeout. The page took too long to respond. This may be due to "
                "geo-blocking, slow connection, or server issues."
            )

        # Connection errors
        if isinstance(error, httpx.ConnectError) or "connect" in error_str:
            if "name resolution" in error_str or "dns" in error_str:
                return CrawlErrorType.DNS_ERROR, (
                    "DNS resolution failed. Could not find the server. Check the URL."
                )
            return CrawlErrorType.CONNECTION_ERROR, (
                "Connection failed. The server may be blocking requests or unreachable."
            )

        # SSL errors
        if "ssl" in error_str or "certificate" in error_str:
            return CrawlErrorType.SSL_ERROR, (
                "SSL/TLS error. There may be a certificate issue."
            )

        return CrawlErrorType.UNKNOWN, f"Unexpected error: {str(error)}"

    async def _random_delay(self):
        """Add random delay to mimic human behavior."""
        if self.stealth_mode:
            delay = random.uniform(
                self.settings.crawler_random_delay_min,
                self.settings.crawler_random_delay_max
            )
            await asyncio.sleep(delay)

    async def fetch_page(self, url: str, retry_count: int = 0) -> CrawlResult:
        """
        Fetch HTML content from a URL using httpx with retry support.

        This is a drop-in replacement for the Playwright version.

        Features:
        - Stealth headers to avoid bot detection
        - Proxy support for geo-restricted sites
        - Automatic retry with exponential backoff
        - Detailed error classification

        Args:
            url: The URL to crawl
            retry_count: Current retry attempt (internal use)

        Returns:
            CrawlResult with HTML content or error info
        """
        start_time = time.time()
        headers = self._get_headers()
        proxy_url = self._get_proxy_url()

        # Step 1: Starting crawl
        self._log_step(1, "Starting Crawl (Lite)", "initiated", metrics={
            "url": url[:80] + "..." if len(url) > 80 else url,
            "attempt": f"{retry_count + 1}/{self.max_retries + 1}",
            "stealth_mode": self.stealth_mode,
            "proxy": bool(proxy_url)
        })

        response = None
        try:
            # Add random delay before request (stealth)
            await self._random_delay()

            # Configure httpx client
            timeout = httpx.Timeout(
                self.timeout_seconds,
                connect=30.0,
                read=self.navigation_timeout_seconds
            )

            client_kwargs = {
                "timeout": timeout,
                "follow_redirects": True,
                "headers": headers,
            }

            if proxy_url:
                client_kwargs["proxy"] = proxy_url

            # Step 2: Make HTTP request
            self._log_step(2, "HTTP Request", "started")
            request_start = time.time()

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(url)

            request_duration = time.time() - request_start
            self._log_step(2, "HTTP Request", "completed", duration=request_duration,
                          metrics={"status": response.status_code})

            # Check for HTTP errors
            if response.status_code >= 400:
                error_type, error_msg = self._classify_error(Exception("HTTP error"), response)
                logger.error(f"HTTP {response.status_code} for {url}: {error_msg}")

                # Retry on certain error codes
                if retry_count < self.max_retries and response.status_code in [429, 503, 502, 504]:
                    wait_time = self.settings.crawler_retry_min_wait * (2 ** retry_count)
                    wait_time = min(wait_time, self.settings.crawler_retry_max_wait)
                    logger.info(f"Retrying in {wait_time}s due to HTTP {response.status_code}...")
                    await asyncio.sleep(wait_time)
                    return await self.fetch_page(url, retry_count + 1)

                return CrawlResult(
                    url=url,
                    success=False,
                    error_message=error_msg,
                    error_type=error_type.value,
                    crawl_duration_seconds=time.time() - start_time
                )

            # Get HTML content
            html_content = response.text

            # Step 3: Parse and validate content
            self._log_step(3, "Content Parsing", "started")
            parse_start = time.time()

            # Log content stats
            logger.info("\n" + "=" * 70)
            logger.info("=== HTML EXTRACTION (Lite Mode) ===")
            logger.info("=" * 70)
            logger.info(f"URL: {url}")
            logger.info(f"Total HTML size: {len(html_content):,} characters")
            logger.info(f"Content-Type: {response.headers.get('content-type', 'unknown')}")

            # Count table rows using BeautifulSoup
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                tables = soup.find_all('table')
                total_rows = sum(len(t.find_all('tr')) for t in tables)
                logger.info(f"Tables found: {len(tables)}")
                logger.info(f"Total table rows: {total_rows}")
            except Exception as parse_err:
                logger.warning(f"Could not parse table rows: {parse_err}")

            # Preview of HTML content
            preview = html_content[:500].replace('\n', ' ').replace('\r', '')
            logger.info(f"HTML Preview: {preview}...")
            logger.info("=" * 70 + "\n")

            self._log_step(3, "Content Parsing", "completed", duration=time.time() - parse_start)

            # Check for bot detection pages
            if self._is_bot_detection_page(html_content):
                logger.warning(f"Bot detection page detected for {url}")
                if retry_count < self.max_retries:
                    wait_time = self.settings.crawler_retry_min_wait * (2 ** retry_count)
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    return await self.fetch_page(url, retry_count + 1)

                return CrawlResult(
                    url=url,
                    success=False,
                    error_message="Bot detection triggered. The site may require JavaScript rendering.",
                    error_type=CrawlErrorType.BOT_DETECTED.value,
                    crawl_duration_seconds=time.time() - start_time
                )

            # Check if page seems to require JavaScript
            if self._requires_javascript(html_content):
                logger.warning(f"Page may require JavaScript rendering: {url}")
                # We still return success but log the warning

            total_duration = time.time() - start_time
            self._log_step(4, "Crawl Complete", "success", duration=total_duration,
                          metrics={"html_chars": len(html_content)})

            return CrawlResult(
                url=url,
                success=True,
                html_content=html_content,
                error_type=CrawlErrorType.SUCCESS.value,
                crawl_duration_seconds=total_duration
            )

        except httpx.TimeoutException as e:
            error_type, error_msg = self._classify_error(e)
            logger.error(f"Timeout crawling {url}: {e}")

            if retry_count < self.max_retries:
                wait_time = self.settings.crawler_retry_min_wait * (2 ** retry_count)
                wait_time = min(wait_time, self.settings.crawler_retry_max_wait)
                logger.info(f"Retrying in {wait_time}s after timeout...")
                await asyncio.sleep(wait_time)
                return await self.fetch_page(url, retry_count + 1)

            return CrawlResult(
                url=url,
                success=False,
                error_message=error_msg,
                error_type=error_type.value,
                crawl_duration_seconds=time.time() - start_time
            )

        except httpx.ConnectError as e:
            error_type, error_msg = self._classify_error(e)
            logger.error(f"Connection error crawling {url}: {e}")

            if retry_count < self.max_retries:
                wait_time = self.settings.crawler_retry_min_wait * (2 ** retry_count)
                wait_time = min(wait_time, self.settings.crawler_retry_max_wait)
                logger.info(f"Retrying in {wait_time}s after connection error...")
                await asyncio.sleep(wait_time)
                return await self.fetch_page(url, retry_count + 1)

            return CrawlResult(
                url=url,
                success=False,
                error_message=error_msg,
                error_type=error_type.value,
                crawl_duration_seconds=time.time() - start_time
            )

        except Exception as e:
            error_type, error_msg = self._classify_error(e, response)
            logger.error(f"Unexpected error crawling {url}: {e}")

            return CrawlResult(
                url=url,
                success=False,
                error_message=error_msg,
                error_type=error_type.value,
                crawl_duration_seconds=time.time() - start_time
            )

    def _is_bot_detection_page(self, html_content: str) -> bool:
        """Check if the page content indicates bot detection."""
        html_lower = html_content.lower()
        bot_indicators = [
            "captcha",
            "robot verification",
            "please verify you are human",
            "access denied",
            "cloudflare",
            "unusual traffic",
            "automated access",
            "enable javascript to continue",
        ]

        # Check for indicators but avoid false positives with short content
        if len(html_content) < 2000:
            return any(indicator in html_lower for indicator in bot_indicators)

        return False

    def _requires_javascript(self, html_content: str) -> bool:
        """Check if the page likely requires JavaScript to render content."""
        html_lower = html_content.lower()

        # Common indicators that JS is required
        js_indicators = [
            "please enable javascript",
            "javascript is required",
            "this page requires javascript",
            "noscript",
            "loading...",
            "react-root",
            "ng-app",
            "__next",
        ]

        # If very little content and JS indicators present
        if len(html_content) < 5000:
            if any(indicator in html_lower for indicator in js_indicators):
                return True

        # If body is nearly empty but has lots of scripts
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            body = soup.find('body')
            if body:
                # Get text content length
                text_len = len(body.get_text(strip=True))
                # Get number of script tags
                scripts = len(soup.find_all('script'))

                # If very little text but many scripts, likely JS-rendered
                if text_len < 500 and scripts > 5:
                    return True
        except Exception:
            pass

        return False

    async def download_document(self, url: str, save_path: str = None) -> tuple[bytes | None, str | None]:
        """
        Download a document (PDF/DOCX) from a URL with retry and proxy support.

        Args:
            url: The document URL
            save_path: Optional path to save the document

        Returns:
            Tuple of (document_bytes, error_message)
        """
        headers = self._get_headers()
        headers["Accept"] = "application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,*/*"
        proxy_url = self._get_proxy_url()

        logger.info(f"Downloading document: {url}")

        for attempt in range(self.max_retries + 1):
            try:
                timeout = httpx.Timeout(self.timeout_seconds, connect=30.0)
                client_kwargs = {
                    "timeout": timeout,
                    "follow_redirects": True,
                    "headers": headers,
                }

                if proxy_url:
                    client_kwargs["proxy"] = proxy_url

                async with httpx.AsyncClient(**client_kwargs) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                    content = response.content
                    logger.info(f"Downloaded {len(content)} bytes from {url}")

                    if save_path:
                        with open(save_path, "wb") as f:
                            f.write(content)

                    return content, None

            except httpx.TimeoutException:
                error = "Download timeout: The document took too long to download."
                logger.warning(f"{error} URL: {url} (attempt {attempt + 1}/{self.max_retries + 1})")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.settings.crawler_retry_min_wait * (2 ** attempt))
                    continue
                return None, f"{error} Try using a VPN or proxy for geo-restricted content."

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in [403, 451]:
                    error = f"HTTP {status}: Access denied. This may be geo-blocking."
                elif status == 429:
                    error = f"HTTP {status}: Rate limited. Wait before retrying."
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.settings.crawler_retry_min_wait * (2 ** attempt))
                        continue
                else:
                    error = f"HTTP {status}: Failed to download document."
                logger.error(f"{error} URL: {url}")
                return None, error

            except Exception as e:
                error = f"Download error: {str(e)}"
                logger.error(f"{error} URL: {url}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.settings.crawler_retry_min_wait * (2 ** attempt))
                    continue
                return None, error

        return None, "Max retries exceeded"

