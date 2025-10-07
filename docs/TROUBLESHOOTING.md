# Troubleshooting Guide

## MCP JSONRPC Validation Errors (RESOLVED)

### Symptoms
```
ERROR:mcp.client.stdio:Failed to parse JSONRPC message from server
pydantic_core._pydantic_core.ValidationError: 1 validation error for JSONRPCMessage
Invalid JSON: expected value at line 1 column 1
input_value='Creating new Kusto clien...'
```

### Root Cause
The external Kusto MCP server (`@mcp-apps/kusto-mcp-server`) incorrectly writes log messages to **stdout** instead of **stderr**. The MCP protocol requires:
- **stdout** = JSON-RPC messages ONLY
- **stderr** = Log messages

When the Kusto server logs to stdout, the MCP client tries to parse these log lines as JSON-RPC and fails.

### Impact
- ✅ **Functionality**: MCP service still works correctly
- ⚠️ **Logs**: Console shows validation errors (noise)
- ℹ️ **Performance**: No impact

### Solution
The errors are now **suppressed via logging filter** in `backend/main.py`:

```python
class MCPJsonRpcFilter(logging.Filter):
    def filter(self, record):
        if record.name == "mcp.client.stdio" and "Failed to parse JSONRPC message" in record.getMessage():
            return False
        return True

mcp_logger = logging.getLogger("mcp.client.stdio")
mcp_logger.addFilter(MCPJsonRpcFilter())
```

### Verification
After applying the fix, you should see:
- ✅ `INFO:services.kusto_mcp_service:MCP prewarm list_tables success`
- ❌ No more `ERROR:mcp.client.stdio:Failed to parse JSONRPC message`

## Agent Framework Import Errors (RESOLVED)

### Symptoms
```
ModuleNotFoundError: No module named 'agent_framework'
```

### Root Cause
Using system Python instead of UV virtual environment.

### Solution
Always use `uv run` prefix:

```powershell
# ✅ Correct
uv run uvicorn backend.main:app --reload

# ❌ Wrong
python backend/main.py
uvicorn backend.main:app --reload
```

See [UV_USAGE.md](UV_USAGE.md) for details.

## Agent Framework Type Errors (RESOLVED)

### Problem 1: Async Credential Type Mismatch
**Symptom**: `Argument of type "DefaultAzureCredential" cannot be assigned to parameter "credential"`

**Root Cause**: Used async credential (`azure.identity.aio.DefaultAzureCredential`) when `AzureOpenAIChatClient` expects sync.

**Solution**: Changed to use `auth_service.wam_credential` for consistency with Autogen implementation

### Problem 2: None Iteration Error
**Symptom**: `Object of type "None" cannot be used as iterable value`

**Root Cause**: Missing null check before iterating `conversation_history`

**Solution**: Added `if raw_hist:` guard before loop

### Problem 3: Authentication State Mismatch (RESOLVED)
**Symptom**: `Authentication failed: state mismatch: [hash1] vs [hash2]` and `InteractiveBrowserCredential.get_token failed`

**Root Cause**: Creating multiple `DefaultAzureCredential()` instances caused authentication state conflicts

**Solution**: Use shared `auth_service.wam_credential` instead of creating new credential instances
- **Before**: `credential = DefaultAzureCredential()` (creates new instance each time)
- **After**: `credential=auth_service.wam_credential` (reuses shared credential)

This maintains authentication consistency across both Autogen and Agent Framework implementations.

## Frontend ECONNREFUSED Errors

### Symptoms
```
[vite] http proxy error: /api/auth/me?azure_user_id=...
AggregateError [ECONNREFUSED]
```

### Root Cause
Frontend (Vite) starting before backend (FastAPI) is ready.

### Solution
1. Start backend first:
   ```powershell
   uv run uvicorn backend.main:app --reload --port 8000
   ```

2. Wait for "Application startup complete"

3. Then start frontend:
   ```powershell
   cd frontend
   npm run dev
   ```

### Prevention
Create a startup script (`start.ps1`):

```powershell
# Start backend in background
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd backend; uv run uvicorn main:app --reload --port 8000"

# Wait for backend to be ready
Start-Sleep -Seconds 5

# Start frontend
cd frontend
npm run dev
```

## Common Issues

### Issue: "Package agent-framework not found"
**Solution**: Run `uv sync --prerelease=allow`

### Issue: "Python module not found" when running scripts
**Solution**: Always use `uv run python script.py`, never just `python script.py`

### Issue: Database locked
**Solution**: Close all connections and restart:
```powershell
# Kill any running backend processes
Get-Process | Where-Object {$_.ProcessName -like "*python*" -or $_.ProcessName -like "*uvicorn*"} | Stop-Process -Force

# Restart backend
uv run uvicorn backend.main:app --reload --port 8000
```

### Issue: "Error: listen EADDRINUSE"
**Solution**: Port 8000 or 5173 already in use:
```powershell
# Find and kill process using port 8000
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Or use different port
uv run uvicorn backend.main:app --reload --port 8001
```

## Debugging Tips

### Enable Verbose Logging
```python
# In backend/main.py or any service
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Agent Framework Version
```powershell
uv run python -c "import agent_framework; print(agent_framework.__version__)"
# Expected: 1.0.0b251001
```

### Test Agent Framework Imports
```powershell
uv run python -c "from agent_framework import ChatAgent; from agent_framework.azure import AzureOpenAIChatClient; print('SUCCESS')"
```

### Verify MCP Server
```powershell
# Test Kusto MCP server directly
npx -y @mcp-apps/kusto-mcp-server
```

### Check Database Schema
```powershell
uv run python -c "from backend.models.database import Base; from backend.dependencies import engine; import asyncio; asyncio.run(Base.metadata.create_all(bind=engine.sync_engine))"
```

## Performance Optimization

### Reduce MCP Startup Time
Set environment variable:
```powershell
$env:MCP_INIT_TIMEOUT = "30"  # Default is 60 seconds
```

### Skip MCP Prewarm
If Kusto queries aren't needed immediately:
```python
# In backend/services/kusto_mcp_service.py
# Comment out prewarm calls in main.py lifespan
```

## Getting Help

1. Check logs carefully - most issues have clear error messages
2. Verify you're using `uv run` for all Python commands
3. Ensure backend starts before frontend
4. Check this guide for known issues
5. Review [UV_USAGE.md](UV_USAGE.md) for package management

## Known Limitations

- **MCP Server Logs**: Kusto MCP server has a bug writing to stdout (suppressed via filter)
- **Agent Framework**: Pre-release package (1.0.0b251001) - API may change
- **Windows Only**: Some features require Windows-specific async event loop policy
