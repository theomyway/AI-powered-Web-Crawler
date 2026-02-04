"""
RFP Generator API endpoints.

Provides endpoints for generating and downloading RFP response documents.
Uses Azure Functions for AI-powered RFP response generation via Azure OpenAI GPT-4o.
"""

import io
import re
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, TokenUser
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.document import Document
from app.models.opportunity import Opportunity
from app.schemas.rfp_generator import (
    GenerateRfpRequest,
    GenerateRfpResponse,
    DownloadRfpRequest,
)

logger = get_logger(__name__)
router = APIRouter()
settings = get_settings()

# Type alias for database dependency
DB = Annotated[AsyncSession, Depends(get_db)]


def generate_placeholder_content(opportunity: Opportunity, company_info: dict) -> str:
    """
    Generate a placeholder RFP response document.
    
    Phase 1: Uses a template with actual data but no AI generation.
    Phase 2 will integrate Azure OpenAI for intelligent content generation.
    """
    certifications_list = company_info.get("certifications", [])
    certifications_text = ", ".join(certifications_list) if certifications_list else "None listed"
    
    deadline_text = "Not specified"
    if opportunity.submission_deadline:
        deadline_text = opportunity.submission_deadline.strftime("%B %d, %Y at %I:%M %p")
    
    content = f"""# RFP Response: {opportunity.title}

## Executive Summary

{company_info.get('company_name', 'Our Company')} is pleased to submit this proposal in response to your Request for Proposal (RFP) for **{opportunity.title}**.

We believe our extensive experience and proven track record make us an ideal partner for this opportunity.

---

## About {company_info.get('company_name', 'Our Company')}

{company_info.get('company_bio', 'Company bio not provided. Please update your company information.')}

---

## Relevant Experience

{company_info.get('relevant_experience', 'Relevant experience not provided. Please update your company information.')}

---

## Certifications & Qualifications

**Our certifications include:** {certifications_text}

---

## Opportunity Details

| Field | Value |
|-------|-------|
| **Title** | {opportunity.title} |
| **Category** | {', '.join(opportunity.categories) if opportunity.categories else 'Not specified'} |
| **Submission Deadline** | {deadline_text} |
| **Estimated Value** | {f'${opportunity.estimated_value:,.2f}' if opportunity.estimated_value else 'Not specified'} |
| **Department/Agency** | {getattr(opportunity, 'department', None) or getattr(opportunity, 'agency', None) or 'Not specified'} |
| **Location** | {opportunity.city or ''} {opportunity.state_code or ''} |

---

## Scope of Work

{opportunity.description or opportunity.summary or 'No description available for this opportunity.'}

---

## Our Approach

*[This section will be AI-generated in Phase 2 based on the RFP requirements and your company's capabilities.]*

We propose a comprehensive approach that leverages our expertise to deliver exceptional results for this project.

---

## Timeline & Deliverables

*[This section will be AI-generated in Phase 2 based on the RFP requirements.]*

We are committed to meeting all deadlines and delivering high-quality work throughout the project lifecycle.

---

## Pricing

*[Pricing details to be added based on detailed requirements analysis.]*

---

## Conclusion

{company_info.get('company_name', 'Our Company')} is committed to delivering excellence and looks forward to the opportunity to partner with you on this project.

For questions or additional information, please contact us.

---

*Document generated on {datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p UTC')}*
"""
    return content


async def call_rfp_generator_function(
    opportunity: Opportunity,
    document_url: str | None,
    company_info: dict,
) -> str:
    """
    Call the Azure Function to generate an AI-powered RFP response.

    Args:
        opportunity: The opportunity model instance
        document_url: URL to the RFP document (optional)
        company_info: Company information dict

    Returns:
        Generated RFP response content in markdown format

    Raises:
        HTTPException: If the Azure Function call fails
    """
    function_url = f"{settings.azure_function_url}/api/generate-rfp-response"

    # Prepare request payload
    payload = {
        "opportunity_id": str(opportunity.id),
        "opportunity_title": opportunity.title,
        "document_url": document_url,
        "company_info": {
            "company_name": company_info.get("company_name"),
            "company_bio": company_info.get("company_bio"),
            "relevant_experience": company_info.get("relevant_experience"),
            "certifications": company_info.get("certifications", []),
        },
        "opportunity_details": {
            "deadline": opportunity.submission_deadline.isoformat() if opportunity.submission_deadline else None,
            "category": opportunity.categories[0] if opportunity.categories else None,
            "estimated_value": float(opportunity.estimated_value) if opportunity.estimated_value else None,
        },
    }

    # Prepare headers (include function key if configured)
    headers = {"Content-Type": "application/json"}
    if settings.azure_function_key:
        headers["x-functions-key"] = settings.azure_function_key

    logger.info(
        "Calling Azure Function for RFP generation",
        function_url=function_url,
        opportunity_id=str(opportunity.id),
        has_document=bool(document_url),
    )

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minute timeout for AI generation
            response = await client.post(
                function_url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            result = response.json()

            if not result.get("success"):
                error_msg = result.get("error", "Unknown error from Azure Function")
                logger.error(f"Azure Function returned error: {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"RFP generation failed: {error_msg}",
                )

            return result.get("document_content", "")

    except httpx.TimeoutException:
        logger.error("Azure Function call timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="RFP generation timed out. Please try again.",
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"Azure Function returned HTTP error: {e.response.status_code}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RFP generation service error: {e.response.status_code}",
        )
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to Azure Function: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RFP generation service is unavailable. Please try again later.",
        )


@router.post("/generate", response_model=GenerateRfpResponse)
async def generate_rfp(
    db: DB,
    request: GenerateRfpRequest,
    current_user: TokenUser = Depends(get_current_user),
) -> GenerateRfpResponse:
    """
    Generate an AI-powered RFP response document for the selected opportunity.

    Calls Azure Function to:
    1. Download and extract text from the RFP document
    2. Use Azure OpenAI GPT-4o to generate a professional response
    """
    # Fetch the opportunity (without eager loading documents to avoid missing column issues)
    result = await db.execute(
        select(Opportunity).where(
            Opportunity.id == request.opportunity_id,
            Opportunity.deleted_at.is_(None),
        )
    )
    opportunity = result.scalar_one_or_none()

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Opportunity with ID {request.opportunity_id} not found",
        )

    # Get the document URL
    # The PDF URL is stored in opportunity.source_url (set during crawling from document_url field)
    # Fall back to documents table if source_url doesn't look like a document
    document_url = None

    # Check if opportunity.source_url is a document URL (PDF, DOC, etc.)
    source_url = opportunity.source_url
    if source_url:
        # Check if it looks like a document URL
        doc_extensions = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx')
        if any(source_url.lower().endswith(ext) for ext in doc_extensions) or '/document' in source_url.lower() or '/dam/' in source_url.lower():
            document_url = source_url
            logger.info(f"Using opportunity.source_url as document URL: {document_url}")

    # If source_url is not a document, try the documents table
    if not document_url:
        try:
            # First try to find primary document
            doc_result = await db.execute(
                select(Document.source_url).where(
                    Document.opportunity_id == opportunity.id,
                    Document.is_primary == True,
                ).limit(1)
            )
            primary_url = doc_result.scalar_one_or_none()

            if primary_url:
                document_url = primary_url
                logger.info(f"Using primary document URL from documents table: {document_url}")
            else:
                # Fall back to first document
                doc_result = await db.execute(
                    select(Document.source_url).where(
                        Document.opportunity_id == opportunity.id,
                    ).limit(1)
                )
                document_url = doc_result.scalar_one_or_none()
                if document_url:
                    logger.info(f"Using first document URL from documents table: {document_url}")
        except Exception as e:
            logger.warning(f"Could not fetch document URL from documents table: {e}")

    if not document_url:
        logger.warning(f"No document URL found for opportunity {opportunity.id}. source_url was: {source_url}")

    # Check if Azure Function is configured
    if not settings.azure_function_url:
        logger.warning("Azure Function URL not configured, using placeholder content")
        company_info_dict = request.company_info.model_dump()
        document_content = generate_placeholder_content(opportunity, company_info_dict)
    else:
        # Call Azure Function for AI-powered generation
        try:
            document_content = await call_rfp_generator_function(
                opportunity=opportunity,
                document_url=document_url,
                company_info=request.company_info.model_dump(),
            )
        except Exception as e:
            logger.error(f"Azure Function call failed: {e}", exc_info=True)
            # Fall back to placeholder content on error
            logger.warning("Falling back to placeholder content due to Azure Function error")
            company_info_dict = request.company_info.model_dump()
            document_content = generate_placeholder_content(opportunity, company_info_dict)

    logger.info(
        "RFP response generated",
        opportunity_id=str(request.opportunity_id),
        opportunity_title=opportunity.title,
        user=current_user.email,
        ai_generated=bool(settings.azure_function_url),
    )

    return GenerateRfpResponse(
        success=True,
        document_content=document_content,
        generated_at=datetime.now(timezone.utc),
        opportunity_title=opportunity.title,
    )


def markdown_to_docx(content: str, title: str) -> io.BytesIO:
    """
    Convert markdown content to a DOCX document.

    Simple conversion that handles basic markdown formatting.
    """
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # Set document margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Handle headers
        if line.startswith('# '):
            p = doc.add_heading(line[2:], level=0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif line.startswith('## '):
            doc.add_heading(line[3:], level=1)
        elif line.startswith('### '):
            doc.add_heading(line[4:], level=2)
        elif line.startswith('---'):
            # Add a horizontal line (paragraph with bottom border)
            doc.add_paragraph()
        elif line.startswith('| '):
            # Handle markdown tables
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            i -= 1  # Adjust for the outer loop increment

            if len(table_lines) >= 2:
                # Parse table
                header_cells = [c.strip() for c in table_lines[0].split('|')[1:-1]]
                data_rows = []
                for tl in table_lines[2:]:  # Skip header and separator
                    cells = [c.strip() for c in tl.split('|')[1:-1]]
                    data_rows.append(cells)

                # Create table
                if header_cells:
                    table = doc.add_table(rows=1 + len(data_rows), cols=len(header_cells))
                    table.style = 'Table Grid'

                    # Header row
                    hdr_cells = table.rows[0].cells
                    for idx, val in enumerate(header_cells):
                        if idx < len(hdr_cells):
                            # Remove markdown bold markers
                            clean_val = val.replace('**', '')
                            hdr_cells[idx].text = clean_val

                    # Data rows
                    for row_idx, row_data in enumerate(data_rows):
                        row_cells = table.rows[row_idx + 1].cells
                        for idx, val in enumerate(row_data):
                            if idx < len(row_cells):
                                row_cells[idx].text = val
        elif line.startswith('*[') and line.endswith(']*'):
            # Placeholder/note text - add as italic
            p = doc.add_paragraph()
            run = p.add_run(line[2:-2])
            run.italic = True
        elif line.startswith('*') and line.endswith('*') and not line.startswith('**'):
            # Italic text
            p = doc.add_paragraph()
            run = p.add_run(line.strip('*'))
            run.italic = True
        else:
            # Regular paragraph - handle inline formatting
            p = doc.add_paragraph()
            # Simple handling of bold text
            parts = re.split(r'\*\*([^*]+)\*\*', line)
            for idx, part in enumerate(parts):
                if idx % 2 == 1:  # Bold part
                    run = p.add_run(part)
                    run.bold = True
                else:
                    p.add_run(part)

        i += 1

    # Save to BytesIO
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


@router.post("/download")
async def download_rfp(
    request: DownloadRfpRequest,
    current_user: TokenUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download the generated RFP document in the specified format.

    Currently supports DOCX format. PDF support will be added in a future phase.
    """
    if request.format == "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF format is not yet supported. Please use DOCX format.",
        )

    # Generate filename
    title_slug = re.sub(r'[^\w\s-]', '', request.opportunity_title or 'rfp-response')
    title_slug = re.sub(r'[-\s]+', '-', title_slug).strip('-').lower()[:50]
    filename = f"{title_slug}-response.docx"

    # Convert to DOCX
    try:
        docx_buffer = markdown_to_docx(
            request.document_content,
            request.opportunity_title or "RFP Response"
        )
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document generation library not available. Please install python-docx.",
        )
    except Exception as e:
        logger.error(f"Error generating DOCX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate document. Please try again.",
        )

    logger.info(
        "RFP document downloaded",
        opportunity_id=str(request.opportunity_id),
        format=request.format,
        user=current_user.email,
    )

    return StreamingResponse(
        docx_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

