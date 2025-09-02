from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    azure_user_id = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    display_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class ModelConfiguration(Base):
    __tablename__ = "model_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    azure_endpoint = Column(String(500), nullable=False)
    azure_deployment = Column(String(255), nullable=False)
    model_name = Column(String(255), nullable=False)
    api_version = Column(String(50), default="2024-06-01")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class AgentConfiguration(Base):
    __tablename__ = "agent_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    agent_name = Column(String(255), nullable=False)
    system_message = Column(Text, nullable=False)
    model_config_id = Column(Integer, nullable=False)
    mcp_server_config = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class DiagnosticSession(Base):
    __tablename__ = "diagnostic_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(255), unique=True, nullable=False)
    device_id = Column(String(255), nullable=True)
    query_type = Column(String(100), nullable=False)
    query_parameters = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    status = Column(String(50), default="pending")  # pending, completed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    # latest known state snapshot (device/account/context ids)
    state_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_session_id = Column(Integer, ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' or 'agent'
    content = Column(Text, nullable=False)
    params = Column(JSON, nullable=True)
    tables = Column(JSON, nullable=True)
    state_after = Column(JSON, nullable=True)
    intent = Column(String(100), nullable=True)
    clarification_needed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now(), index=True)