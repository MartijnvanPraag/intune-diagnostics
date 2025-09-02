import asyncio
import os
import sys
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Set the correct event loop policy for Windows to support subprocesses
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from azure.identity import DefaultAzureCredential

from models.database import Base
from routers import auth, settings, diagnostics
from services.agent_service import AgentService
from dependencies import engine, get_db


security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    await init_db()
    # Initialize agent service
    await AgentService.initialize()
    yield
    # Cleanup
    await AgentService.cleanup()

app = FastAPI(
    title="Intune Diagnostics API",
    description="Modern web app for Intune diagnostics with Agentic AI",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"],  # React/Vite dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(diagnostics.router, prefix="/api/diagnostics", tags=["diagnostics"])

# App-level debug route listing (not in schema docs)
@app.get("/api/debug/routes", include_in_schema=False)
async def debug_list_routes():
    from fastapi.routing import APIRoute
    info = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            methods = ",".join(sorted(r.methods)) if r.methods else ""
            info.append(f"{r.path} -> {methods}")
    return sorted(info)

@app.get("/")
async def root():
    return {"message": "Intune Diagnostics API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)