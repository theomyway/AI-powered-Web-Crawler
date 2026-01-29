"""
Company Info management endpoints.

Provides GET and PUT operations for managing company profile information.
Each tenant has a single company profile record.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, TokenUser
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.company_info import CompanyInfo
from app.schemas.company_info import (
    CompanyInfoCreate,
    CompanyInfoResponse,
    CompanyInfoUpdate,
)

logger = get_logger(__name__)
router = APIRouter()

# Type alias for database dependency
DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=CompanyInfoResponse | None)
async def get_company_info(
    db: DB,
    current_user: TokenUser = Depends(get_current_user),
) -> CompanyInfoResponse | None:
    """
    Get the company profile for the current tenant.
    
    Returns the company info if it exists, or null if not yet created.
    Requires authentication.
    """
    tenant_id = current_user.tid
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID not found in user token",
        )

    result = await db.execute(
        select(CompanyInfo).where(CompanyInfo.tenant_id == tenant_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        return None

    logger.info(
        "Company info retrieved",
        tenant_id=tenant_id,
        company_name=company.company_name,
    )
    return CompanyInfoResponse.model_validate(company)


@router.put("", response_model=CompanyInfoResponse)
async def update_company_info(
    db: DB,
    data: CompanyInfoCreate | CompanyInfoUpdate,
    current_user: TokenUser = Depends(get_current_user),
) -> CompanyInfoResponse:
    """
    Create or update the company profile for the current tenant.
    
    If no company info exists, creates a new record.
    If company info exists, updates the existing record.
    Requires authentication.
    """
    tenant_id = current_user.tid
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID not found in user token",
        )

    # Check if company info already exists
    result = await db.execute(
        select(CompanyInfo).where(CompanyInfo.tenant_id == tenant_id)
    )
    company = result.scalar_one_or_none()

    if company:
        # Update existing record
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in update_data.items():
            setattr(company, field, value)
        
        logger.info(
            "Company info updated",
            tenant_id=tenant_id,
            company_name=company.company_name,
        )
    else:
        # Create new record - need full data
        if isinstance(data, CompanyInfoUpdate):
            # For update schema, check required fields
            if not data.company_name or not data.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="company_name and email are required for first-time setup",
                )
        
        create_data = data.model_dump(exclude_unset=True)
        company = CompanyInfo(
            tenant_id=tenant_id,
            **create_data,
        )
        db.add(company)
        
        logger.info(
            "Company info created",
            tenant_id=tenant_id,
            company_name=company.company_name,
        )

    await db.commit()
    await db.refresh(company)

    return CompanyInfoResponse.model_validate(company)

