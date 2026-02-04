"""
Schemas for RFP Generator API.

Provides request/response validation for RFP document generation and download.
"""

from datetime import datetime
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, Field


class CompanyInfoInput(BaseModel):
    """Company information for RFP generation."""

    company_name: str = Field(
        min_length=1,
        max_length=255,
        description="Company name to use in the RFP response",
    )
    company_bio: str | None = Field(
        default=None,
        description="Company description/about text",
    )
    relevant_experience: str | None = Field(
        default=None,
        description="Description of past projects and relevant experience",
    )
    certifications: list[str] = Field(
        default_factory=list,
        description="List of certifications held by the company",
    )


class GenerateRfpRequest(BaseModel):
    """Request schema for generating an RFP response."""

    opportunity_id: UUID = Field(
        description="ID of the opportunity to generate RFP response for",
    )
    company_info: CompanyInfoInput = Field(
        description="Company information to include in the RFP response",
    )


class GenerateRfpResponse(BaseModel):
    """Response schema for RFP generation."""

    success: bool = Field(
        description="Whether the generation was successful",
    )
    document_content: str = Field(
        description="Generated RFP document content in markdown format",
    )
    generated_at: datetime = Field(
        description="Timestamp when the document was generated",
    )
    opportunity_title: str = Field(
        description="Title of the opportunity for reference",
    )


class DownloadRfpRequest(BaseModel):
    """Request schema for downloading an RFP document."""

    document_content: str = Field(
        description="The generated document content to convert",
    )
    opportunity_id: UUID = Field(
        description="ID of the opportunity (for filename)",
    )
    format: Literal["docx", "pdf"] = Field(
        default="docx",
        description="Output format for the document",
    )
    opportunity_title: str | None = Field(
        default=None,
        description="Title of the opportunity (for filename)",
    )

