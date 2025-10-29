# Agent query_entity Usage Fix

## Problem

The agent was still calling `query_entity` with `$filter` and `$select` parameters, even though these cause HTTP 400 errors from the Data Warehouse API. The log showed:

```
[INFO] agent_framework: Function name: query_entity
[INFO] services.agent_framework_service: [AgentFramework] Calling Data Warehouse MCP tool 'query_entity' 
      with args: {'entity': 'devices', 'filter': "deviceId eq 'a50be5c2-d482-40ab-af57-18bace67b0ec'", 
                   'select': 'deviceId,deviceName,...'}
[DataWarehouse MCP] Tool error for query_entity: {
  code: 'HTTP_400',
  message: '...$select=...&$filter=...'  ← THESE PARAMETERS CAUSE HTTP 400
}
[INFO] agent_framework: Function name: find_device_by_id  ← THEN falls back to this (correct tool)
```

The agent was:
1. ❌ Trying `query_entity` with filter/select first (fails with HTTP 400)
2. ✅ Falling back to `find_device_by_id` (succeeds)

This causes:
- Unnecessary failed API calls
- Wasted orchestrator rounds
- Slower query execution
- Confusing logs

## Root Cause

The **system instructions** in `agent_framework_service.py` (lines 820-900) didn't clearly communicate the API limitation. The agent had:

**Before:**
```python
AVAILABLE TOOLS:
Data Warehouse API (Historical Data):
- query_entity: Query an entity with OData filters (e.g., "deviceId eq 'abc123'")  ← MISLEADING
```

This made the agent think `query_entity` supports filters, so it tried filter/select first.

## Solution

Updated system instructions to **explicitly warn** about the limitation:

### 1. Added Warning Section (Line ~851)

```python
⚠️ DATA WAREHOUSE API LIMITATIONS:
The Data Warehouse API does NOT support $filter or $select OData parameters - both cause HTTP 400 errors.
Instead:
- To find a specific device: Use find_device_by_id(device_id) - NOT query_entity with filter
- To get all devices: Use query_entity(entity="devices") without filter/select parameters
- The API returns all 39 fields per device - you cannot select specific columns
- Client-side filtering is the only reliable method for single-device lookups
```

### 2. Updated Tool Descriptions (Line ~863)

```python
Data Warehouse API (Historical Data):
- list_entities: List all available Data Warehouse entities
- get_entity_schema: Get schema/properties for an entity
- query_entity: Query entity WITHOUT filters (⚠️ $filter and $select cause HTTP 400)  ← EXPLICIT
- execute_odata_query: Execute raw OData query URL (advanced use only)
- find_device_by_id: Find a specific device by ID (RECOMMENDED for single device lookups)  ← RECOMMENDED
```

### 3. Updated Critical Rules (Line ~877)

```python
CRITICAL RULES:
1. Execute scenarios step by step in sequential order (1, 2, 3, ...)
2. For Kusto steps: Use exact queries from substitute_and_get_query - never modify them
3. For Data Warehouse device lookups: ALWAYS use find_device_by_id(device_id) - NEVER query_entity with filter  ← EXPLICIT
4. For Data Warehouse bulk queries: Use query_entity(entity) without $filter or $select parameters
5. NEVER pass filter= or select= parameters to query_entity - they cause HTTP 400 errors  ← NEW RULE
6. Don't write your own Kusto queries
7. substitute_and_get_query validates automatically - don't call separate validation
8. After completing all steps, format results and stop
9. Present results as formatted markdown tables
```

### 4. Updated Example Workflow (Line ~895)

**Before:**
```python
3. Step 1 (Data Warehouse - Device Baseline):
   - query_entity(entity="devices", filter="deviceId eq 'abc123'", 
                  select="deviceId,deviceName,manufacturer,model,osVersion")  ← WRONG
```

**After:**
```python
3. Step 1 (Data Warehouse - Device Baseline):
   - find_device_by_id(device_id="abc123") → Returns device with all 39 fields  ← CORRECT
```

## Expected Behavior After Fix

The agent should now:

**Superstep 1:**
```
✅ search_scenarios("device-timeline")
✅ get_scenario("device-timeline")
✅ find_device_by_id(device_id="a50be5c2-d482-40ab-af57-18bace67b0ec")  ← DIRECT CALL
   (No query_entity attempt with filter/select)
✅ substitute_and_get_query(query_id="device-timeline_step2", ...)
✅ execute_query(...)
... (continue through all steps)
```

**No more failed query_entity calls with filter/select parameters.**

## Files Modified

1. **backend/services/agent_framework_service.py** (Lines 820-905)
   - Added ⚠️ DATA WAREHOUSE API LIMITATIONS section
   - Updated tool descriptions with explicit warnings
   - Added Critical Rule #5: NEVER pass filter/select to query_entity
   - Updated example workflow to use find_device_by_id

## Testing

To verify the fix:

1. Restart backend: `uv run uvicorn backend.main:app --reload`
2. Run device-timeline query
3. Check logs for:
   - ❌ Should NOT see: `query_entity` with `filter=` or `select=` parameters
   - ✅ Should see: `find_device_by_id` called directly without prior query_entity attempt
   - ✅ Should see: No HTTP 400 errors from Data Warehouse API

Expected log pattern:
```
[INFO] agent_framework: Function name: search_scenarios
[INFO] agent_framework: Function name: get_scenario
[INFO] agent_framework: Function name: find_device_by_id  ← DIRECT, no query_entity before it
[INFO] services.datawarehouse_mcp_service: Found device: NUC
[INFO] agent_framework: Function name: substitute_and_get_query
[INFO] agent_framework: Function name: execute_query
... (continue)
```

## Related Documentation

- `docs/DATA_WAREHOUSE_API_LIMITATIONS.md` - Comprehensive API limitation guide
- `docs/ORCHESTRATOR_LOOPING_FIX.md` - Orchestrator loop prevention (different issue)
- `backend/services/datawarehouse_mcp_service.py` - find_device_by_id implementation (lines 198-255)
- `instructions.md` (line 704) - device_timeline Step 1 updated to use find_device_by_id

## Impact

This fix should:
- ✅ Eliminate unnecessary HTTP 400 errors from Data Warehouse API
- ✅ Reduce orchestrator rounds (no retry/fallback needed)
- ✅ Speed up query execution (direct tool usage)
- ✅ Cleaner logs (no failed query_entity attempts)
- ✅ Better agent efficiency (correct tool selection on first try)
