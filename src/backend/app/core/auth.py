"""
Microsoft Entra ID (Azure AD) Authentication Module

Provides token validation and user authentication for the API.
"""

import httpx
from functools import lru_cache
from typing import Optional
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
from jwt import PyJWKClient

from app.core.logging import get_logger

logger = get_logger(__name__)

# Azure AD Configuration
TENANT_ID = "cb8d0f5e-295e-44f1-8cab-184ae827c864"
CLIENT_ID = "36e2ab97-659d-4af6-8caa-e8462bf07a40"

# Azure AD Endpoints
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
JWKS_URI = f"{AUTHORITY}/discovery/v2.0/keys"
ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"

# Security scheme
security = HTTPBearer(auto_error=False)


class TokenUser(BaseModel):
    """Represents an authenticated user from the token."""
    sub: str  # Subject (user ID)
    name: Optional[str] = None
    email: Optional[str] = None
    preferred_username: Optional[str] = None
    oid: Optional[str] = None  # Object ID
    tid: Optional[str] = None  # Tenant ID


@lru_cache(maxsize=1)
def get_jwks_client() -> PyJWKClient:
    """
    Get a cached JWKS client for token validation.
    
    Returns:
        PyJWKClient: Client for retrieving signing keys
    """
    return PyJWKClient(JWKS_URI, cache_keys=True)


async def validate_token(token: str) -> TokenUser:
    """
    Validate a JWT token from Microsoft Entra ID.
    
    Args:
        token: The JWT access token to validate
        
    Returns:
        TokenUser: The authenticated user information
        
    Raises:
        HTTPException: If token validation fails
    """
    try:
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and validate the token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER,
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            }
        )
        
        # Extract user information
        user = TokenUser(
            sub=payload.get("sub"),
            name=payload.get("name"),
            email=payload.get("email") or payload.get("preferred_username"),
            preferred_username=payload.get("preferred_username"),
            oid=payload.get("oid"),
            tid=payload.get("tid"),
        )
        
        logger.debug(
            "Token validated successfully",
            user_id=user.sub,
            username=user.preferred_username,
        )
        
        return user
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidAudienceError:
        logger.warning("Invalid token audience")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token audience",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidIssuerError:
        logger.warning("Invalid token issuer")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error("Token validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenUser:
    """
    FastAPI dependency to get the current authenticated user.
    
    Args:
        credentials: The HTTP Bearer credentials
        
    Returns:
        TokenUser: The authenticated user
        
    Raises:
        HTTPException: If authentication fails
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return await validate_token(credentials.credentials)

