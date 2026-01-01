"""
Azure Functions V2 Programming Model Entry Point.

This file registers HTTP and Service Bus triggers for the Function App.
Supports both:
1. HTTP trigger (legacy) - for direct API calls
2. Service Bus trigger - for queue-based sequential URL processing
"""

import json
import logging
import azure.functions as func

# Import the main handlers from rfp_crawler
from rfp_crawler import main as rfp_crawler_main, process_servicebus_message

# Create the Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="crawl", methods=["POST"])
async def crawl(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger for RFP crawling and classification (legacy).

    Delegates to the rfp_crawler module's main function.
    """
    return await rfp_crawler_main(req)


@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="url-crawl-queue",
    connection="SERVICEBUS_CONNECTION_STRING"
)
async def process_url_queue(msg: func.ServiceBusMessage) -> None:
    """
    Service Bus Queue trigger for sequential URL processing.

    Each message contains a single URL to crawl. Messages are processed
    one at a time, ensuring sequential processing.

    Message format:
    {
        "url": "https://...",
        "source_id": "uuid",
        "crawl_session_id": "uuid",
        "categories": ["dynamics_365", "ai"],
        "backend_url": "https://..."
    }
    """
    try:
        # Decode message body
        message_body = msg.get_body().decode('utf-8')
        logging.info(f"Processing Service Bus message: {message_body[:200]}...")

        # Process the message
        await process_servicebus_message(message_body)

        logging.info("Service Bus message processed successfully")
    except Exception as e:
        logging.error(f"Error processing Service Bus message: {e}", exc_info=True)
        # Re-raise to trigger dead-letter queue
        raise

