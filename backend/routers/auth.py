from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional
import jwt
from jwt import PyJWKClient
import logging

from models.database import User
from models.schemas import User as UserSchema, UserCreate
from dependencies import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

# Azure AD JWT validation configuration
TENANT_ID = "72f988bf-86f1-41af-91ab-2d7cd011db47"  # Microsoft tenant (single-tenant app)
CLIENT_ID = "fbadc585-90b3-48ab-8052-c1fcc32ce3fe"  # Your Entra App ID
JWKS_URI = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"

# Initialize JWKS client for token signature verification
jwks_client = PyJWKClient(JWKS_URI)


async def verify_token(authorization: Optional[str] = Header(None)) -> dict:
    """
    Verify JWT token from Authorization header
    
    This validates:
    1. Token signature (using Azure AD's public keys)
    2. Token expiration
    3. Audience (ensures token is for our app)
    4. Issuer (ensures token is from Azure AD)
    
    Returns decoded token claims if valid, raises HTTPException if invalid
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )
    
    # Extract Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'"
        )
    
    token = parts[1]
    
    try:
        # Get signing key from JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and validate token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=CLIENT_ID,  # Validates token is for our app
            issuer=ISSUER,  # Validates token is from Azure AD
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            }
        )
        
        logger.info(f"Token validated for user: {payload.get('preferred_username', 'unknown')}")
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=401, detail="Invalid token audience")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=401, detail="Invalid token issuer")
    except Exception as e:
        logger.error(f"Token validation failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")


@router.post("/register", response_model=UserSchema)
async def register_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    """
    Register or update user in database
    
    This endpoint is called after successful MSAL authentication.
    The JWT token is validated to ensure the user is authenticated.
    """
    try:
        # Verify the user data matches the token claims (security check)
        token_user_id = token_payload.get("oid") or token_payload.get("sub")
        if user_data.azure_user_id != token_user_id:
            raise HTTPException(
                status_code=403,
                detail="User data doesn't match token claims"
            )
        
        # Check if user already exists
        result = await db.execute(
            select(User).where(User.azure_user_id == user_data.azure_user_id)
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            # Update existing user
            await db.execute(
                update(User)
                .where(User.azure_user_id == user_data.azure_user_id)
                .values(
                    email=user_data.email,
                    display_name=user_data.display_name,
                    is_active=True
                )
            )
            await db.commit()
            
            # Fetch updated user
            result = await db.execute(
                select(User).where(User.azure_user_id == user_data.azure_user_id)
            )
            updated_user = result.scalar_one()
            logger.info(f"Updated user: {updated_user.email}")
            return updated_user
        else:
            # Create new user
            new_user = User(
                azure_user_id=user_data.azure_user_id,
                email=user_data.email,
                display_name=user_data.display_name
            )
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            logger.info(f"Created new user: {new_user.email}")
            return new_user
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"User registration failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"User registration failed: {str(e)}")


@router.post("/logout")
async def logout():
    """
    Logout endpoint (optional - MSAL handles logout client-side)
    
    This can be used to clear server-side session/cache if needed.
    For MSAL, the actual logout happens in the browser.
    """
    return {
        "status": "success",
        "message": "Logout successful (client-side logout required)"
    }


@router.get("/me", response_model=UserSchema)
async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    """
    Get current authenticated user from database
    
    Requires valid JWT token in Authorization header.
    """
    # Extract user ID from token
    azure_user_id = token_payload.get("oid") or token_payload.get("sub")
    
    result = await db.execute(
        select(User).where(User.azure_user_id == azure_user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user