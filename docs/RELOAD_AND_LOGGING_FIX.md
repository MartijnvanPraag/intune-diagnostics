# Reload and Logging Fixes

## Auto-Reload Disabled

**Problem**: Uvicorn's auto-reload feature was causing the backend to hang when service files were modified. This happened because:
- Services maintain persistent connections (MCP stdio clients, auth credentials)
- These connections block clean shutdown during reload
- CTRL+C would not work, requiring forcefully closing the terminal

**Solution**: Disabled auto-reload completely in `package.json`:
```json
"backend:dev": "cd backend && uv run uvicorn main:app --host 0.0.0.0 --port 8000"
```

**Impact**:
- ✅ No more hanging reloads
- ✅ CTRL+C works properly again
- ⚠️ **Manual restart required** for backend code changes: Press CTRL+C and run `npm run dev` again
- ✅ Frontend still has hot-reload (Vite)

**Workflow**:
1. Make backend changes
2. Press CTRL+C to stop backend
3. Run `npm run dev` to restart
4. Frontend changes still auto-reload

---

## Logging Configuration Fixed

**Problem**: Intermittent loss of all logging after app restart. Root cause:
- Multiple service files called `logging.basicConfig()` independently
- In Python, **only the first `basicConfig()` call has any effect**
- Import order determined which service's config would apply
- Sometimes logging wasn't configured at all

**Solution**: Centralized logging configuration in `main.py`:

```python
# Configure logging FIRST before any other imports
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
    force=True  # Force reconfiguration if already configured
)
```

**Changes Made**:
1. **`backend/main.py`**: Added comprehensive logging setup with `force=True`
2. **`backend/services/autogen_service.py`**: Removed `logging.basicConfig()`
3. **`backend/services/agent_framework_service.py`**: Removed `logging.basicConfig()`
4. **`backend/services/kusto_mcp_service.py`**: Removed `logging.basicConfig()`

**Impact**:
- ✅ Logging consistently works on every startup
- ✅ All service logs are visible
- ✅ MCP JSONRPC errors still filtered out
- ✅ Consistent log format across all modules

---

## Log Format

All logs now use the consistent format:
```
[LEVEL] module.name: message
```

Examples:
```
[INFO] services.agent_framework_service: Processing response with 3 messages
[INFO] services.agent_framework_service: Extracted 1 objects from function results
[INFO] services.agent_framework_service: Found 1 unique tables
```

---

## Troubleshooting

### No logs appearing after restart
- **Fixed**: This should no longer occur with centralized logging config
- If it does: Check that `main.py` is imported before service modules

### MCP JSONRPC errors still appearing
- These are from the Kusto MCP server writing to stdout
- They are filtered by `MCPJsonRpcFilter` in `main.py`
- The errors don't affect functionality

### Need to see more detailed logs
- Edit `backend/main.py` line with `level=logging.INFO`
- Change to `level=logging.DEBUG` for verbose output
- Restart backend (CTRL+C and `npm run dev`)

---

## Summary

| Issue | Status | Impact |
|-------|--------|--------|
| Reload hanging | ✅ Fixed | Manual restart required |
| CTRL+C not working | ✅ Fixed | Now works immediately |
| Intermittent logging loss | ✅ Fixed | Always logs now |
| Log consistency | ✅ Fixed | Uniform format |

**Developer Experience**:
- Slightly more manual (need to restart backend)
- But much more reliable (no hanging, consistent logs)
- Frontend still has instant hot-reload
