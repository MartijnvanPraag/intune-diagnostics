from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from models.database import ModelConfiguration, AgentConfiguration
from models.schemas import (
    ModelConfiguration as ModelConfigSchema,
    ModelConfigurationCreate,
    AgentConfiguration as AgentConfigSchema,
    AgentConfigurationCreate
)

router = APIRouter()

from dependencies import get_db

# Model Configuration endpoints
@router.post("/models", response_model=ModelConfigSchema)
async def create_model_config(
    config: ModelConfigurationCreate, 
    db: AsyncSession = Depends(get_db)
):
    """Create a new model configuration"""
    try:
        # If this is set as default, unset other defaults for this user
        if config.is_default:
            await db.execute(
                update(ModelConfiguration)
                .where(ModelConfiguration.user_id == config.user_id)
                .values(is_default=False)
            )
        
        new_config = ModelConfiguration(**config.dict())
        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)
        return new_config
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create model configuration: {str(e)}")

@router.get("/models", response_model=List[ModelConfigSchema])
async def get_model_configs(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get all model configurations for a user"""
    result = await db.execute(
        select(ModelConfiguration).where(ModelConfiguration.user_id == user_id)
    )
    return result.scalars().all()

@router.get("/models/{config_id}", response_model=ModelConfigSchema)
async def get_model_config(config_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific model configuration"""
    result = await db.execute(
        select(ModelConfiguration).where(ModelConfiguration.id == config_id)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Model configuration not found")
    
    return config

@router.put("/models/{config_id}", response_model=ModelConfigSchema)
async def update_model_config(
    config_id: int, 
    config_update: ModelConfigurationCreate,
    db: AsyncSession = Depends(get_db)
):
    """Update a model configuration"""
    try:
        # Get existing config
        result = await db.execute(
            select(ModelConfiguration).where(ModelConfiguration.id == config_id)
        )
        existing_config = result.scalar_one_or_none()
        
        if not existing_config:
            raise HTTPException(status_code=404, detail="Model configuration not found")
        
        # If this is set as default, unset other defaults for this user
        if config_update.is_default:
            await db.execute(
                update(ModelConfiguration)
                .where(ModelConfiguration.user_id == config_update.user_id)
                .where(ModelConfiguration.id != config_id)
                .values(is_default=False)
            )
        
        # Update the configuration
        update_data = config_update.dict(exclude_unset=True)
        await db.execute(
            update(ModelConfiguration)
            .where(ModelConfiguration.id == config_id)
            .values(**update_data)
        )
        
        await db.commit()
        
        # Return updated config
        result = await db.execute(
            select(ModelConfiguration).where(ModelConfiguration.id == config_id)
        )
        return result.scalar_one()
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update model configuration: {str(e)}")

@router.delete("/models/{config_id}")
async def delete_model_config(config_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a model configuration"""
    try:
        result = await db.execute(
            delete(ModelConfiguration).where(ModelConfiguration.id == config_id)
        )
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Model configuration not found")
        
        await db.commit()
        return {"message": "Model configuration deleted successfully"}
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete model configuration: {str(e)}")

# Agent Configuration endpoints
@router.post("/agents", response_model=AgentConfigSchema)
async def create_agent_config(
    config: AgentConfigurationCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new agent configuration"""
    try:
        new_config = AgentConfiguration(**config.dict())
        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)
        return new_config
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create agent configuration: {str(e)}")

@router.get("/agents", response_model=List[AgentConfigSchema])
async def get_agent_configs(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get all agent configurations for a user"""
    result = await db.execute(
        select(AgentConfiguration).where(AgentConfiguration.user_id == user_id)
    )
    return result.scalars().all()