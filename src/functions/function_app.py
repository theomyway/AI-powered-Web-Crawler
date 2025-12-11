"""
Azure Functions V2 Programming Model Entry Point.

This file registers all HTTP triggers for the Function App.
"""

import azure.functions as func

# Import the main handler from rfp_crawler
from rfp_crawler import main as rfp_crawler_main

# Create the Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="crawl", methods=["POST"])
async def crawl(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger for RFP crawling and classification.
    
    Delegates to the rfp_crawler module's main function.
    """
    return await rfp_crawler_main(req)

