from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import User
from models.schemas import User as UserSchema, UserCreate
from services.auth_service import auth_service

router = APIRouter()

from dependencies import get_db

@router.post("/login")
async def login():
    """Initiate Azure interactive authentication"""
    try:
        auth_result = await auth_service.authenticate_user()
        return {
            "status": "success",
            "message": "Authentication successful",
            "user": {
                "azure_user_id": auth_result["azure_user_id"],
                "email": auth_result["email"],
                "display_name": auth_result["display_name"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

@router.post("/register", response_model=UserSchema)
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register or update user in database after authentication"""
    try:
        # Check if user already exists
        result = await db.execute(
            select(User).where(User.azure_user_id == user_data.azure_user_id)
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            # Update existing user
            existing_user.email = user_data.email
            existing_user.display_name = user_data.display_name
            existing_user.is_active = True
            await db.commit()
            await db.refresh(existing_user)
            return existing_user
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
            return new_user
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"User registration failed: {str(e)}")

@router.get("/me", response_model=UserSchema)
async def get_current_user(azure_user_id: str, db: AsyncSession = Depends(get_db)):
    """Get current user information"""
    result = await db.execute(
        select(User).where(User.azure_user_id == azure_user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user