import asyncio
import os
import sys
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Set the correct event loop policy for Windows to support subprocesses
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Configure logging FIRST before any other imports
# This ensures logging is properly set up for all modules
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
    force=True  # Force reconfiguration if already configured
)

# Configure logging to suppress MCP JSONRPC validation errors
# These occur because the Kusto MCP server incorrectly writes logs to stdout
# The MCP client still works correctly, so we suppress these non-critical errors
class MCPJsonRpcFilter(logging.Filter):
    """Filter to suppress MCP JSONRPC validation errors from external Kusto server"""
    def filter(self, record):
        # Suppress "Failed to parse JSONRPC message" errors - these are from the buggy Kusto MCP server
        if record.name == "mcp.client.stdio" and "Failed to parse JSONRPC message" in record.getMessage():
            return False
        return True

# Apply the filter to the MCP logger
mcp_logger = logging.getLogger("mcp.client.stdio")
mcp_logger.addFilter(MCPJsonRpcFilter())

load_dotenv()
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from azure.identity import DefaultAzureCredential
from pathlib import Path

from models.database import Base
from routers import auth, settings, diagnostics
from services.autogen_service import AgentService
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

# Get allowed origins from environment variable for production
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:5173").split(",")

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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

# Mount static files for production (built React app)
# This serves the frontend from the /static directory
static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")
    
    # Serve index.html for all non-API routes (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA for all non-API routes"""
        # Skip API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Serve index.html for SPA routing
        index_file = static_dir / "index.html"
        if index_file.exists():
            from fastapi.responses import FileResponse
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend not built")

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

@app.get("/api")
async def root():
    return {"message": "Intune Diagnostics API is running"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)