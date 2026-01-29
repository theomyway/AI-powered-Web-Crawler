"""
CompanyInfo model - Stores company profile information.

Each tenant/organization has a single company profile record.
"""

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CompanyInfo(Base, TimestampMixin):
    """
    Company profile information for the organization.
    
    Stores company details used for RFP responses and proposals.
    One record per tenant (identified by tenant_id from Azure AD).
    
    Attributes:
        tenant_id: Azure AD tenant ID (unique identifier for the organization)
        company_name: Official company name
        email: Primary contact email
        phone: Contact phone number
        street_address: Street address line
        city: City name
        state: State/Province
        zip_code: Postal/ZIP code
        company_bio: Company description/about text
        relevant_experience: Description of past projects and experience
        certifications: List of certifications held
    """

    __tablename__ = "company_info"

    # Tenant identifier (from Azure AD)
    tenant_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Azure AD tenant ID for the organization",
    )

    # Basic Information
    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Official company name",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Primary contact email",
    )
    phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Contact phone number",
    )

    # Address Fields
    street_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Street address",
    )
    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="City",
    )
    state: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="State/Province",
    )
    zip_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Postal/ZIP code",
    )

    # Extended Information
    company_bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Company description/about text",
    )
    relevant_experience: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Description of past projects and relevant experience",
    )
    certifications: Mapped[list[str]] = mapped_column(
        ARRAY(String(255)),
        default=list,
        nullable=False,
        comment="List of certifications held by the company",
    )

    def __repr__(self) -> str:
        return f"<CompanyInfo(tenant_id='{self.tenant_id}', company_name='{self.company_name}')>"

