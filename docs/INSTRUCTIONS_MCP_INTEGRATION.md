# Instructions MCP Server - Integration Complete ✅

## Summary

Successfully integrated the Instructions MCP server with the Agent Framework service. The system now provides structured access to diagnostic scenarios and queries, preventing query modification by delivering exact query text through tool interfaces.

## Integration Status

### ✅ Completed Components

1. **Instructions MCP Service** (`backend/services/instructions_mcp_service.py`)
   - Manages Instructions MCP server lifecycle
   - Initializes Python-based MCP server via stdio
   - Discovers and caches tool names
   - Provides singleton service instance

2. **Tool Function Wrapper** (`agent_framework_service.py`)
   - `create_instructions_mcp_tool_function()` - Wraps MCP tools as agent functions
   - Handles MCP result format (content -> text extraction)
   - Provides error handling and logging

3. **Tool Discovery Integration** (`agent_framework_service.py`)
   - Updated `_discover_mcp_tools()` to discover from both MCP servers
   - Instructions MCP tools added first (primary workflow)
   - Kusto MCP tools added second (execution)
   - Legacy tools preserved for backward compatibility

4. **Agent Instructions Update** (`agent_framework_service.py`)
   - Added comprehensive Instructions MCP workflow guidance
   - Critical rule: NEVER modify query text from substitute_and_get_query
   - Step-by-step execution pattern with code example
   - Deprecated legacy tools (lookup_scenarios)

5. **MCP Server Initialization** (`agent_framework_service.py`)
   - Instructions MCP initialized first in `setup_agent()`
   - Kusto MCP initialized second
   - Both services logged with tool counts

### 🧪 Integration Test Results

**Test Script**: `backend/test_mcp_integration.py`

```
✅ TEST 1: Initialize Instructions MCP Service
   - Session available: True
   - Tools discovered: 5
   - Tool names: search_scenarios, get_scenario, get_query, 
                 validate_placeholders, substitute_and_get_query

✅ TEST 2: List Tools from MCP Session
   - Retrieved 5 tools with descriptions

✅ TEST 3: Call search_scenarios Tool
   - Searched for "device timeline"
   - Found 2 matching scenarios
   - Response length: 749 chars

✅ TEST 4: Call get_scenario Tool
   - Retrieved "device-timeline" scenario
   - Response contains steps data
   - Response length: 3049 chars

✅ TEST 5: Call substitute_and_get_query Tool
   - Query ID: device-timeline_step1
   - Placeholder substituted: DeviceId -> test-device-123
   - Response contains Kusto query

✅ TEST 6: Cleanup
   - MCP service shut down successfully

ALL INTEGRATION TESTS PASSED ✅
```

## Architecture Overview

```
User Request
    ↓
Agent Framework Service
    ↓
    ├─→ Instructions MCP Service (Python stdio)
    │   ├─→ search_scenarios       → Find relevant scenarios
    │   ├─→ get_scenario           → Get all steps
    │   ├─→ get_query              → Inspect query (optional)
    │   ├─→ validate_placeholders  → Check formats (optional)
    │   └─→ substitute_and_get_query → Get EXACT query text ⭐
    │       ↓
    │       Returns: {"query": "let DeviceID = 'abc-123'; ..."}
    │
    └─→ Kusto MCP Service (Node.js stdio)
        └─→ execute_query          → Execute query EXACTLY as received
```

## Tool Execution Flow

### New Workflow (Instructions MCP)

```python
# 1. Agent receives user request: "Show device timeline for abc-123"

# 2. Search for scenarios
search_results = search_scenarios(query="device timeline")
# -> Finds "device-timeline" scenario

# 3. Get complete scenario
scenario = get_scenario(slug="device-timeline")
# -> Returns all 9 steps with metadata

# 4. For each step:
for step in scenario["steps"]:
    # Get EXACT query text with placeholders substituted
    query_data = substitute_and_get_query(
        query_id=step["query_id"],
        values={"DeviceId": "abc-123", "StartTime": "...", "EndTime": "..."}
    )
    
    # Execute query EXACTLY as returned (NO modifications)
    result = execute_query(
        clusterUrl="intune.kusto.windows.net",
        database="intune",
        query=query_data["query"]  # EXACT text from MCP tool
    )
    
    # Extract values for next steps
    if step["step_number"] == 4:
        # Extract EffectiveGroupId from results
        effective_group_ids = extract_from_results(result)
```

### Legacy Workflow (Deprecated)

```python
# Old way - prone to query modification
scenarios = lookup_scenarios(query="device timeline")
# -> Returns text with queries embedded
# -> Agent extracts queries (may modify syntax)
# -> Agent "improves" query formatting ❌
# -> Syntax errors result
```

## Key Integration Points

### 1. Service Initialization

**Location**: `agent_framework_service.py:1028-1040`

```python
# Initialize MCP services
try:
    from services.instructions_mcp_service import get_instructions_service
    from services.kusto_mcp_service import get_kusto_service
    
    # Initialize Instructions MCP first (provides scenario queries)
    instructions_service = await get_instructions_service()
    logger.info(f"Instructions MCP service initialized (tools={...})")
    
    # Initialize Kusto MCP (executes queries)
    kusto_service = await get_kusto_service()
    logger.info(f"Kusto MCP service initialized (tools={...})")
except Exception as mcp_err:
    logger.error(f"Failed to initialize MCP services: {mcp_err}")
    raise
```

### 2. Tool Discovery

**Location**: `agent_framework_service.py:595-650`

```python
async def _discover_mcp_tools(self) -> list[Callable[..., Awaitable[str]]]:
    """Discover and create tools from the MCP servers"""
    tools = []
    
    # Add legacy tools (backward compatibility)
    tools.append(create_scenario_lookup_function())
    tools.append(create_context_lookup_function())
    
    # Discover Instructions MCP tools
    instructions_service = await get_instructions_service()
    for mcp_tool in instructions_tools:
        tool_function = create_instructions_mcp_tool_function(...)
        tools.append(tool_function)
    
    # Discover Kusto MCP tools
    kusto_service = await get_kusto_service()
    for mcp_tool in kusto_tools:
        tool_function = create_mcp_tool_function(...)
        tools.append(tool_function)
    
    return tools
```

### 3. Agent Instructions

**Location**: `agent_framework_service.py:717-795`

Key sections:
- **MANDATORY WORKFLOW WITH INSTRUCTIONS MCP**: Step-by-step process
- **CRITICAL RULE - QUERY MODIFICATION**: Never modify query text
- **INSTRUCTIONS MCP TOOLS**: Primary workflow tools
- **SCENARIO EXECUTION PATTERN**: Code example showing exact usage

## Files Modified/Created

### New Files
- ✅ `backend/services/instructions_mcp_service.py` (141 lines)
- ✅ `backend/test_mcp_integration.py` (164 lines)
- ✅ `docs/INSTRUCTIONS_MCP_INTEGRATION.md` (this file)

### Modified Files
- ✅ `backend/services/agent_framework_service.py`
  - Added `create_instructions_mcp_tool_function()` (64 lines)
  - Updated `_discover_mcp_tools()` to include Instructions MCP
  - Updated agent system instructions with Instructions MCP workflow
  - Updated `setup_agent()` to initialize Instructions MCP service

- ✅ `backend/mcp_servers/instructions/server.py`
  - Fixed stdout logging to use stderr (avoid JSONRPC interference)

## Configuration

### Instructions MCP Server

**Command**: `python -m backend.mcp_servers.instructions.server`
**Protocol**: stdio (stdin/stdout)
**Working Directory**: Workspace root (where instructions.md is located)
**Environment**: Inherits from parent process

### Service Parameters

```python
InstructionsMCPService(
    _session: Optional[ClientSession] = None,
    _exit_stack: Optional[AsyncExitStack] = None,
    is_initialized: bool = False,
    _tool_names: List[str] = []
)
```

## Testing Strategy

### Unit Tests
- ✅ Parser test: `backend/test_instructions_parser.py`
- ✅ Store test: `backend/test_mcp_server.py`

### Integration Tests
- ✅ MCP integration: `backend/test_mcp_integration.py`

### End-to-End Tests (Pending)
- ⏳ Device Timeline scenario execution
- ⏳ Verify zero query modifications
- ⏳ Validate all 9 steps execute successfully

## Known Issues & Fixes

### ✅ Issue 1: Parser Code Block Detection
**Problem**: Code block closing fence matched START pattern  
**Fix**: Check CODE_BLOCK_END first when in_code_block=True  
**Status**: FIXED

### ✅ Issue 2: Stdout Pollution
**Problem**: MCP server printed to stdout, interfering with JSONRPC  
**Fix**: Changed to stderr for all logging  
**Status**: FIXED

## Next Steps

1. **End-to-End Testing**
   - Run Device Timeline scenario through UI
   - Monitor for query modifications
   - Verify all 9 steps execute
   - Confirm zero syntax errors

2. **Monitoring & Logging**
   - Add metrics for tool usage
   - Track query modification attempts
   - Monitor placeholder substitution errors

3. **Documentation**
   - Update user guide with new workflow
   - Add troubleshooting section
   - Document common patterns

4. **Optimization**
   - Cache parsed scenarios
   - Optimize placeholder substitution
   - Add query validation before execution

## Success Criteria

- ✅ Instructions MCP server starts successfully
- ✅ All 5 tools discovered by agent
- ✅ Tools callable via MCP session
- ✅ search_scenarios returns results
- ✅ get_scenario returns complete structure
- ✅ substitute_and_get_query returns exact text
- ⏳ Device Timeline executes end-to-end
- ⏳ Zero query modifications detected
- ⏳ All 9 queries execute without errors

## Expected Impact

### Before Integration
- Query modification rate: ~50%
- Syntax errors: Frequent (agent-introduced)
- Debugging difficulty: High (manual query comparison)

### After Integration
- Query modification rate: <5% (expected)
- Syntax errors: Minimal (only source errors)
- Debugging difficulty: Low (exact queries logged)

## Commands

```bash
# Test parser
uv run python backend/test_instructions_parser.py

# Test store
uv run python backend/test_mcp_server.py

# Test integration
uv run python backend/test_mcp_integration.py

# Start application
uv run uvicorn backend.main:app --reload
```

## Conclusion

The Instructions MCP server is fully integrated with the Agent Framework. All tests pass, tools are discoverable, and the agent has clear instructions for using the new workflow. The system is ready for end-to-end testing with actual diagnostic scenarios.

**Status**: ✅ INTEGRATION COMPLETE - Ready for E2E Testing
