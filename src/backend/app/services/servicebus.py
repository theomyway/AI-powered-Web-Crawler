"""
Azure Service Bus integration for queue-based URL processing.

This service manages sending URL crawl requests to Service Bus queue
for sequential processing by Azure Functions.
"""

import json
import structlog
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.servicebus.exceptions import ServiceBusError

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class ServiceBusService:
    """Service for sending messages to Azure Service Bus queue."""

    def __init__(self):
        self.settings = get_settings()
        self._client: ServiceBusClient | None = None
        self._sender = None

    @property
    def is_configured(self) -> bool:
        """Check if Service Bus is configured."""
        return bool(self.settings.servicebus_connection_string)

    def _get_client(self) -> ServiceBusClient:
        """Get or create Service Bus client."""
        if self._client is None:
            if not self.settings.servicebus_connection_string:
                raise ValueError("Service Bus connection string not configured")
            self._client = ServiceBusClient.from_connection_string(
                self.settings.servicebus_connection_string
            )
        return self._client

    async def send_crawl_request(
        self,
        url: str,
        source_id: str,
        crawl_session_id: str,
        categories: list[str],
        backend_url: str,
    ) -> bool:
        """
        Send a single URL crawl request to the Service Bus queue.

        Args:
            url: The URL to crawl
            source_id: UUID of the CrawlSource record
            crawl_session_id: Session ID for grouping requests
            categories: List of category filters
            backend_url: Backend URL for callbacks

        Returns:
            bool: True if message was sent successfully
        """
        try:
            message_body = {
                "url": url,
                "source_id": source_id,
                "crawl_session_id": crawl_session_id,
                "categories": categories,
                "backend_url": backend_url,
            }

            client = self._get_client()
            queue_name = self.settings.servicebus_queue_name

            with client.get_queue_sender(queue_name) as sender:
                message = ServiceBusMessage(
                    body=json.dumps(message_body),
                    content_type="application/json",
                    subject=f"crawl-{source_id}",
                )
                sender.send_messages(message)

            logger.info(
                "Sent crawl request to Service Bus",
                url=url[:80],
                source_id=source_id,
                queue=queue_name,
            )
            return True

        except ServiceBusError as e:
            logger.error("Service Bus send failed", error=str(e), url=url[:80])
            return False
        except Exception as e:
            logger.error("Unexpected error sending to Service Bus", error=str(e))
            return False

    async def send_batch_crawl_requests(
        self,
        urls: list[str],
        source_ids: list[str],
        crawl_session_id: str,
        categories: list[str],
        backend_url: str,
    ) -> tuple[int, int]:
        """
        Send multiple URL crawl requests to the Service Bus queue.

        Args:
            urls: List of URLs to crawl
            source_ids: List of source IDs (parallel to urls)
            crawl_session_id: Session ID for grouping requests
            categories: List of category filters
            backend_url: Backend URL for callbacks

        Returns:
            tuple[int, int]: (successful_count, failed_count)
        """
        success_count = 0
        fail_count = 0

        for url, source_id in zip(urls, source_ids):
            result = await self.send_crawl_request(
                url=url,
                source_id=source_id,
                crawl_session_id=crawl_session_id,
                categories=categories,
                backend_url=backend_url,
            )
            if result:
                success_count += 1
            else:
                fail_count += 1

        logger.info(
            "Batch send complete",
            session_id=crawl_session_id,
            success=success_count,
            failed=fail_count,
        )
        return success_count, fail_count

    def close(self):
        """Close the Service Bus client."""
        if self._client:
            self._client.close()
            self._client = None


# Singleton instance
_servicebus_service: ServiceBusService | None = None


def get_servicebus_service() -> ServiceBusService:
    """Get the singleton ServiceBusService instance."""
    global _servicebus_service
    if _servicebus_service is None:
        _servicebus_service = ServiceBusService()
    return _servicebus_service

