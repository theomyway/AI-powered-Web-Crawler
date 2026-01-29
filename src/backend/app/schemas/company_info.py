"""
Schemas for CompanyInfo API.

Provides request/response validation for company profile management.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
import re


class CompanyInfoBase(BaseModel):
    """Base schema for CompanyInfo with common fields."""

    company_name: str = Field(
        min_length=1,
        max_length=255,
        description="Official company name",
    )
    email: EmailStr = Field(
        description="Primary contact email",
    )
    phone: str | None = Field(
        default=None,
        max_length=50,
        description="Contact phone number",
    )
    street_address: str | None = Field(
        default=None,
        description="Street address",
    )
    city: str | None = Field(
        default=None,
        max_length=100,
        description="City",
    )
    state: str | None = Field(
        default=None,
        max_length=100,
        description="State/Province",
    )
    zip_code: str | None = Field(
        default=None,
        max_length=20,
        description="Postal/ZIP code",
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

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        """Validate phone number format (basic validation)."""
        if v is None or v == "":
            return None
        # Remove common formatting characters for validation
        cleaned = re.sub(r"[\s\-\(\)\.\+]", "", v)
        if not cleaned.isdigit() or len(cleaned) < 7 or len(cleaned) > 15:
            raise ValueError(
                "Phone number must contain 7-15 digits (formatting characters allowed)"
            )
        return v

    @field_validator("certifications", mode="before")
    @classmethod
    def parse_certifications(cls, v):
        """Handle certifications as comma-separated string or list."""
        if isinstance(v, str):
            # Split by comma and strip whitespace
            return [cert.strip() for cert in v.split(",") if cert.strip()]
        return v or []


class CompanyInfoCreate(CompanyInfoBase):
    """Schema for creating company info (first-time setup)."""

    pass


class CompanyInfoUpdate(BaseModel):
    """Schema for updating company info (partial update allowed)."""

    model_config = ConfigDict(extra="forbid")

    company_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    street_address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    zip_code: str | None = Field(default=None, max_length=20)
    company_bio: str | None = None
    relevant_experience: str | None = None
    certifications: list[str] | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        """Validate phone number format (basic validation)."""
        if v is None or v == "":
            return None
        cleaned = re.sub(r"[\s\-\(\)\.\+]", "", v)
        if not cleaned.isdigit() or len(cleaned) < 7 or len(cleaned) > 15:
            raise ValueError(
                "Phone number must contain 7-15 digits (formatting characters allowed)"
            )
        return v

    @field_validator("certifications", mode="before")
    @classmethod
    def parse_certifications(cls, v):
        """Handle certifications as comma-separated string or list."""
        if v is None:
            return None
        if isinstance(v, str):
            return [cert.strip() for cert in v.split(",") if cert.strip()]
        return v


class CompanyInfoResponse(CompanyInfoBase):
    """Schema for CompanyInfo API response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    created_at: datetime
    updated_at: datetime

