"""
Authentication Endpoints

Provides endpoints for authentication operations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from app.core.auth import get_current_user, TokenUser, validate_token
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class UserInfoResponse(BaseModel):
    """Response model for user information."""
    sub: str
    name: Optional[str] = None
    email: Optional[str] = None
    preferred_username: Optional[str] = None
    oid: Optional[str] = None
    tid: Optional[str] = None
    is_authenticated: bool = True


class TokenValidationRequest(BaseModel):
    """Request model for token validation."""
    access_token: str


class TokenValidationResponse(BaseModel):
    """Response model for token validation."""
    valid: bool
    user: Optional[UserInfoResponse] = None
    error: Optional[str] = None


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: TokenUser = Depends(get_current_user),
) -> UserInfoResponse:
    """
    Get the current authenticated user's information.
    
    Returns the user information extracted from the access token.
    """
    logger.info(
        "User info requested",
        user_id=current_user.sub,
        username=current_user.preferred_username,
    )
    
    return UserInfoResponse(
        sub=current_user.sub,
        name=current_user.name,
        email=current_user.email,
        preferred_username=current_user.preferred_username,
        oid=current_user.oid,
        tid=current_user.tid,
        is_authenticated=True,
    )


@router.post("/validate", response_model=TokenValidationResponse)
async def validate_access_token(
    request: TokenValidationRequest,
) -> TokenValidationResponse:
    """
    Validate an access token.
    
    This endpoint can be used to verify if a token is valid without
    requiring it in the Authorization header.
    """
    try:
        user = await validate_token(request.access_token)
        logger.info(
            "Token validation successful",
            user_id=user.sub,
        )
        return TokenValidationResponse(
            valid=True,
            user=UserInfoResponse(
                sub=user.sub,
                name=user.name,
                email=user.email,
                preferred_username=user.preferred_username,
                oid=user.oid,
                tid=user.tid,
                is_authenticated=True,
            ),
        )
    except HTTPException as e:
        logger.warning("Token validation failed", detail=e.detail)
        return TokenValidationResponse(
            valid=False,
            error=e.detail,
        )
    except Exception as e:
        logger.error("Token validation error", error=str(e))
        return TokenValidationResponse(
            valid=False,
            error="Token validation failed",
        )


@router.post("/logout")
async def logout(
    current_user: TokenUser = Depends(get_current_user),
) -> dict:
    """
    Logout endpoint.
    
    This endpoint is primarily for logging purposes since actual
    logout is handled client-side by MSAL. The server can perform
    any necessary cleanup here.
    """
    logger.info(
        "User logged out",
        user_id=current_user.sub,
        username=current_user.preferred_username,
    )
    
    return {
        "message": "Logged out successfully",
        "user_id": current_user.sub,
    }

