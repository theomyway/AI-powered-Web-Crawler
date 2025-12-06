"""
Page Crawler Service using Playwright for JavaScript-rendered pages.

Handles:
- Fetching HTML content from URLs
- Proxy support for geo-restricted sites (HTTP/SOCKS5)
- Retry logic with exponential backoff
- Stealth mode to avoid bot detection
- Graceful error handling with detailed diagnostics
- Comprehensive step-by-step logging

Note: Uses async Playwright API to work with Azure Functions asyncio loop.
"""

import asyncio
import logging
import random
import time
from datetime import datetime
from enum import Enum

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout, Error as PlaywrightError

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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Common screen resolutions for stealth mode
STEALTH_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]


class PageCrawlerService:
    """Service for crawling web pages using Playwright with stealth and proxy support."""

    def __init__(self):
        self.settings = get_settings()
        self.timeout = self.settings.crawler_timeout  # Already in ms from config
        self.navigation_timeout = self.settings.crawler_navigation_timeout  # Already in ms
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

    def _get_viewport(self) -> dict:
        """Get viewport - either configured or random stealth."""
        if self.stealth_mode:
            return random.choice(STEALTH_VIEWPORTS)
        return {
            "width": self.settings.crawler_viewport_width,
            "height": self.settings.crawler_viewport_height
        }

    def _get_proxy_config(self) -> dict | None:
        """Build proxy configuration for Playwright."""
        if not self.settings.crawler_proxy_url:
            return None

        proxy_config = {"server": self.settings.crawler_proxy_url}

        if self.settings.crawler_proxy_username:
            proxy_config["username"] = self.settings.crawler_proxy_username
        if self.settings.crawler_proxy_password:
            proxy_config["password"] = self.settings.crawler_proxy_password

        return proxy_config

    def _classify_error(self, error: Exception, response=None) -> tuple[CrawlErrorType, str]:
        """Classify the error type and provide helpful message."""
        error_str = str(error).lower()

        # Check response status codes first
        if response:
            status = response.status
            if status == 403:
                return CrawlErrorType.GEO_BLOCKED, (
                    "HTTP 403 Forbidden: Access denied. This may be due to geo-blocking. "
                    "Try using a US-based VPN or proxy."
                )
            elif status == 451:
                return CrawlErrorType.GEO_BLOCKED, (
                    "HTTP 451 Unavailable For Legal Reasons: Content blocked in your region. "
                    "A US-based VPN or proxy is required."
                )
            elif status == 429:
                return CrawlErrorType.BOT_DETECTED, (
                    "HTTP 429 Too Many Requests: Rate limited. Wait before retrying or use proxy rotation."
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
        if "timeout" in error_str or isinstance(error, PlaywrightTimeout):
            if "net::err_timed_out" in error_str:
                return CrawlErrorType.TIMEOUT, (
                    "Connection timed out. This often indicates geo-blocking or the server refusing "
                    "connections from your IP. Try using a US-based VPN or proxy."
                )
            return CrawlErrorType.TIMEOUT, (
                "Page load timeout. The page took too long to respond. This may be due to "
                "geo-blocking, slow connection, or heavy JavaScript content."
            )

        # DNS errors
        if "net::err_name_not_resolved" in error_str or "dns" in error_str:
            return CrawlErrorType.DNS_ERROR, (
                "DNS resolution failed. Could not find the server. Check the URL or your "
                "network configuration."
            )

        # Connection errors
        if "net::err_connection_refused" in error_str:
            return CrawlErrorType.CONNECTION_ERROR, (
                "Connection refused by server. The server actively rejected the connection. "
                "This may be IP-based blocking."
            )
        if "net::err_connection_reset" in error_str:
            return CrawlErrorType.CONNECTION_ERROR, (
                "Connection reset. The connection was forcibly closed. This often indicates "
                "geo-blocking or firewall interference."
            )
        if "net::err_connection_closed" in error_str:
            return CrawlErrorType.CONNECTION_ERROR, (
                "Connection closed unexpectedly. May indicate bot detection or network issues."
            )

        # SSL errors
        if "ssl" in error_str or "certificate" in error_str:
            return CrawlErrorType.SSL_ERROR, (
                "SSL/TLS error. There may be a certificate issue or man-in-the-middle interference."
            )

        # Bot detection patterns
        if any(pattern in error_str for pattern in ["captcha", "robot", "blocked", "denied"]):
            return CrawlErrorType.BOT_DETECTED, (
                "Bot detection triggered. The site has anti-bot protection. Try enabling "
                "stealth mode or using a different proxy."
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
        Fetch HTML content from a URL using Playwright with stealth and retry support.

        Features:
        - Stealth mode to avoid bot detection
        - Proxy support (HTTP/SOCKS5) for geo-restricted sites
        - Automatic retry with exponential backoff
        - Detailed error classification
        - Comprehensive step-by-step logging

        Args:
            url: The URL to crawl
            retry_count: Current retry attempt (internal use)

        Returns:
            CrawlResult with HTML content or error info
        """
        start_time = time.time()
        user_agent = self._get_user_agent()
        viewport = self._get_viewport()
        proxy_config = self._get_proxy_config()

        # Step 1: Starting crawl
        self._log_step(1, "Starting Crawl", "initiated", metrics={
            "url": url[:80] + "..." if len(url) > 80 else url,
            "attempt": f"{retry_count + 1}/{self.max_retries + 1}",
            "stealth_mode": self.stealth_mode,
            "proxy": bool(proxy_config)
        })

        try:
            async with async_playwright() as p:
                # Configure browser launch options for stealth
                launch_options = {
                    "headless": True,
                }

                # If using proxy, set it at browser level for some proxy types
                if proxy_config:
                    launch_options["proxy"] = proxy_config

                # Configure context with stealth settings
                context_options = {
                    "user_agent": user_agent,
                    "viewport": viewport,
                    "java_script_enabled": True,
                    "locale": "en-US",
                    "timezone_id": "America/New_York",
                    "color_scheme": "light",
                }

                # Add stealth headers
                if self.stealth_mode:
                    context_options["extra_http_headers"] = {
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                        "Sec-Ch-Ua-Mobile": "?0",
                        "Sec-Ch-Ua-Platform": '"Windows"',
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Upgrade-Insecure-Requests": "1",
                    }

                # Step 2: Launch browser
                browser_start = time.time()
                browser = await p.chromium.launch(**launch_options)
                context = await browser.new_context(**context_options)
                self._log_step(2, "Browser Launch", "completed",
                              duration=time.time() - browser_start)

                # Add stealth scripts to bypass detection
                if self.stealth_mode:
                    await context.add_init_script("""
                        // Override webdriver property
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });

                        // Override plugins
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });

                        // Override languages
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['en-US', 'en']
                        });

                        // Hide automation indicators
                        window.chrome = { runtime: {} };

                        // Override permissions
                        const originalQuery = window.navigator.permissions.query;
                        window.navigator.permissions.query = (parameters) => (
                            parameters.name === 'notifications' ?
                                Promise.resolve({ state: Notification.permission }) :
                                originalQuery(parameters)
                        );
                    """)

                page = await context.new_page()

                # Set timeouts
                page.set_default_timeout(self.timeout)
                page.set_default_navigation_timeout(self.navigation_timeout)

                # Add random delay before navigation (stealth)
                await self._random_delay()

                response = None
                try:
                    # Step 3: Navigate to page
                    self._log_step(3, "Navigation", "started", metrics={
                        "timeout_ms": self.navigation_timeout
                    })
                    nav_start = time.time()
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout)

                    nav_duration = time.time() - nav_start

                    # Check for immediate failures
                    if response is None:
                        raise PlaywrightError("No response received from server")

                    self._log_step(3, "Navigation", "completed", duration=nav_duration,
                                  metrics={"status": response.status})

                    if not response.ok:
                        error_type, error_msg = self._classify_error(Exception("HTTP error"), response)
                        logger.error(f"HTTP {response.status} for {url}: {error_msg}")

                        # Retry on certain error codes
                        if retry_count < self.max_retries and response.status in [429, 503, 502, 504]:
                            wait_time = self.settings.crawler_retry_min_wait * (2 ** retry_count)
                            wait_time = min(wait_time, self.settings.crawler_retry_max_wait)
                            logger.info(f"Retrying in {wait_time}s due to HTTP {response.status}...")
                            await context.close()
                            await browser.close()
                            await asyncio.sleep(wait_time)
                            return await self.fetch_page(url, retry_count + 1)

                        return CrawlResult(
                            url=url,
                            success=False,
                            error_message=error_msg,
                            error_type=error_type.value,
                            crawl_duration_seconds=time.time() - start_time
                        )

                    # Step 4: Wait for network idle and dynamic content
                    self._log_step(4, "Content Loading", "waiting for network idle")
                    network_start = time.time()
                    try:
                        await page.wait_for_load_state("networkidle", timeout=30000)
                    except PlaywrightTimeout:
                        logger.warning(f"Network idle timeout for {url}, continuing with available content")

                    # Additional wait for dynamic content
                    dynamic_wait = random.uniform(3.0, 5.0) if self.stealth_mode else 3.0
                    await page.wait_for_timeout(int(dynamic_wait * 1000))

                    # Step 5: Full page scroll to trigger lazy loading
                    self._log_step(5, "Lazy Load Trigger", "scrolling page")
                    scroll_start = time.time()
                    try:
                        # Scroll to bottom in steps
                        await page.evaluate("""
                            async () => {
                                const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                                const height = document.body.scrollHeight;
                                const step = height / 4;
                                for (let i = 0; i <= 4; i++) {
                                    window.scrollTo(0, step * i);
                                    await delay(300);
                                }
                                window.scrollTo(0, 0);
                            }
                        """)
                        await page.wait_for_timeout(1000)
                    except Exception as scroll_err:
                        logger.warning(f"Scroll error (non-fatal): {scroll_err}")

                    self._log_step(5, "Lazy Load Trigger", "completed",
                                  duration=time.time() - scroll_start)

                    # Get the full HTML content
                    html_content = await page.content()

                    self._log_step(4, "Content Loading", "completed",
                                  duration=time.time() - network_start,
                                  metrics={"html_chars": len(html_content)})

                    # === ENHANCED LOGGING: HTML EXTRACTION ===
                    logger.info("\n" + "=" * 70)
                    logger.info("=== STEP 1: HTML EXTRACTION ===")
                    logger.info("=" * 70)
                    logger.info(f"URL: {url}")
                    logger.info(f"Total HTML size: {len(html_content):,} characters")

                    # Count table rows (likely RFP entries)
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html_content, 'html.parser')
                        tables = soup.find_all('table')
                        total_rows = sum(len(t.find_all('tr')) for t in tables)
                        logger.info(f"Tables found: {len(tables)}")
                        logger.info(f"Total table rows: {total_rows}")
                    except Exception:
                        logger.info("Could not parse table rows (BeautifulSoup not available)")

                    # Preview of HTML content (first 500 chars)
                    preview = html_content[:500].replace('\n', ' ').replace('\r', '')
                    logger.info(f"HTML Preview: {preview}...")
                    logger.info("=" * 70 + "\n")

                    # Check for bot detection pages
                    if self._is_bot_detection_page(html_content):
                        logger.warning(f"Bot detection page detected for {url}")
                        if retry_count < self.max_retries:
                            wait_time = self.settings.crawler_retry_min_wait * (2 ** retry_count)
                            logger.info(f"Retrying in {wait_time}s...")
                            await context.close()
                            await browser.close()
                            await asyncio.sleep(wait_time)
                            return await self.fetch_page(url, retry_count + 1)

                        return CrawlResult(
                            url=url,
                            success=False,
                            error_message="Bot detection triggered. The site has anti-bot protection.",
                            error_type=CrawlErrorType.BOT_DETECTED.value,
                            crawl_duration_seconds=time.time() - start_time
                        )

                    total_duration = time.time() - start_time
                    self._log_step(6, "Crawl Complete", "success", duration=total_duration,
                                  metrics={"html_chars": len(html_content)})

                    return CrawlResult(
                        url=url,
                        success=True,
                        html_content=html_content,
                        error_type=CrawlErrorType.SUCCESS.value,
                        crawl_duration_seconds=total_duration
                    )

                finally:
                    await context.close()
                    await browser.close()

        except (PlaywrightTimeout, PlaywrightError) as e:
            error_type, error_msg = self._classify_error(e)
            logger.error(f"{error_type.value} crawling {url}: {e}")

            # Retry on timeout errors
            if retry_count < self.max_retries and error_type in [CrawlErrorType.TIMEOUT, CrawlErrorType.CONNECTION_ERROR]:
                wait_time = self.settings.crawler_retry_min_wait * (2 ** retry_count)
                wait_time = min(wait_time, self.settings.crawler_retry_max_wait)
                logger.info(f"Retrying in {wait_time}s after {error_type.value}...")
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
            error_type, error_msg = self._classify_error(e)
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
            "blocked",
            "cloudflare",
            "please enable javascript",
            "unusual traffic",
            "automated access",
        ]

        # Check for indicators but avoid false positives with short content
        if len(html_content) < 2000:
            return any(indicator in html_lower for indicator in bot_indicators)

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
        import httpx

        user_agent = self._get_user_agent()
        proxy_config = self._get_proxy_config()

        logger.info(f"Downloading document: {url}")

        for attempt in range(self.max_retries + 1):
            try:
                # Build client options
                timeout_seconds = self.timeout / 1000
                client_options = {
                    "timeout": httpx.Timeout(timeout_seconds, connect=30.0),
                    "follow_redirects": True,
                    "headers": {
                        "User-Agent": user_agent,
                        "Accept": "application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,*/*",
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                }

                if proxy_config:
                    # Build proxy URL with auth if provided
                    proxy_url = proxy_config["server"]
                    if proxy_config.get("username"):
                        # Insert auth into proxy URL
                        from urllib.parse import urlparse, urlunparse
                        parsed = urlparse(proxy_url)
                        auth_proxy = f"{parsed.scheme}://{proxy_config['username']}:{proxy_config.get('password', '')}@{parsed.netloc}{parsed.path}"
                        proxy_url = auth_proxy
                    client_options["proxy"] = proxy_url

                async with httpx.AsyncClient(**client_options) as client:
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
                    error = f"HTTP {status}: Access denied. This may be geo-blocking. Use a US-based VPN or proxy."
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

