from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class UserBase(BaseModel):
    email: str
    display_name: str

class UserCreate(UserBase):
    azure_user_id: str

class User(UserBase):
    id: int
    azure_user_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ModelConfigurationBase(BaseModel):
    name: str
    azure_endpoint: str
    azure_deployment: str
    model_name: str
    api_version: str = "2024-06-01"
    is_default: bool = False

class ModelConfigurationCreate(ModelConfigurationBase):
    user_id: int

class ModelConfiguration(ModelConfigurationBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AgentConfigurationBase(BaseModel):
    agent_name: str
    system_message: str
    model_config_id: int
    mcp_server_config: Optional[Dict[str, Any]] = None
    is_active: bool = True

class AgentConfigurationCreate(AgentConfigurationBase):
    user_id: int

class AgentConfiguration(AgentConfigurationBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DiagnosticRequest(BaseModel):
    device_id: Optional[str] = None
    query_type: str = Field(..., description="Type of diagnostic query to run")
    parameters: Optional[Dict[str, Any]] = None

class DiagnosticResponse(BaseModel):
    session_id: str
    device_id: Optional[str]
    query_type: str
    results: Optional[Dict[str, Any]]
    status: str
    error_message: Optional[str]
    created_at: datetime

class TableData(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
    total_rows: int

class AgentResponse(BaseModel):
    response: str
    table_data: Optional[TableData] = None  # First / primary table (backward compatibility)
    tables: Optional[List[TableData]] = None  # All tables if multiple
    session_id: str