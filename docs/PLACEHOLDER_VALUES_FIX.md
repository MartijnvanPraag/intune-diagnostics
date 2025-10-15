# Fix: substitute_and_get_query Parameter Format Error

**Date**: October 14, 2025  
**Issue**: Agent failing all Device Timeline queries with "placeholder_values is a required property"

## Problem

The agent was calling `substitute_and_get_query` incorrectly, missing the **required** `placeholder_values` parameter. All queries failed at the substitution step before any Kusto queries could execute.

**Error Pattern**:
```
Query substitution failed: placeholder_values is a required property
```

**Root Cause**: Agent instructions didn't explicitly state that `placeholder_values` is a **required parameter**, nor did they show the correct format for passing it.

## Solution

Updated agent instructions in `agent_framework_service.py` to explicitly specify:

### 1. General Workflow Instructions (lines ~676-682)

**Before**:
```python
"3. For each step in the scenario:
   - Call substitute_and_get_query with the query_id and placeholder values"
```

**After**:
```python
"3. For each step in the scenario:
   - Call substitute_and_get_query with TWO REQUIRED parameters:
     * query_id: the step's query_id from get_scenario
     * placeholder_values: an object/dictionary with placeholder names and their values"
```

### 2. Device Timeline Instructions (lines ~1126-1132)

**Before**:
```python
"4. For each query:
   - Call substitute_and_get_query with query_id and placeholder values"
```

**After**:
```python
"4. For each query:
   - Call substitute_and_get_query with TWO REQUIRED parameters:
     * query_id: e.g. 'device-timeline_step1'
     * placeholder_values: object with keys like DeviceId, StartTime, EndTime
       Example: placeholder_values = DeviceId: abc-123, StartTime: 2025-10-01 00:00:00"
```

### 3. Execution Pattern Example (lines ~742-763)

**Enhanced** with concrete example:
```python
"Step 3: For EACH step call substitute_and_get_query with BOTH parameters:
        - query_id: the step query_id from get_scenario
        - placeholder_values: object with placeholder names as keys and values
        
        Example call format:
        query_id = 'device-timeline_step1'
        placeholder_values = DeviceId: 'abc-123'
        
        Returns JSON with status success and query_text field containing the Kusto query
        Extract: query_text field"
```

## Tool Definition (Reference)

From `backend/mcp_servers/instructions/server.py`:

```python
Tool(
    name="substitute_and_get_query",
    inputSchema={
        "type": "object",
        "properties": {
            "query_id": {
                "type": "string",
                "description": "Query ID"
            },
            "placeholder_values": {
                "type": "object",
                "description": "Placeholder name -> value mapping",
                "additionalProperties": {"type": "string"}
            }
        },
        "required": ["query_id", "placeholder_values"]  # ← BOTH REQUIRED
    }
)
```

## Expected Agent Behavior After Fix

### Step 1: Get scenario steps
```python
# Agent calls get_scenario
result = get_scenario(slug="device-timeline")
# Gets: {"steps": [{"query_id": "device-timeline_step1", "placeholders": {"DeviceId": {...}, "StartTime": {...}}}]}
```

### Step 2: Call substitute_and_get_query correctly
```python
# Agent now calls with BOTH parameters:
result = substitute_and_get_query(
    query_id="device-timeline_step1",
    placeholder_values={
        "DeviceId": "a50be5c2-d482-40ab-af57-18bace67b0ec",
        "StartTime": "2025-10-07 07:42:00",
        "EndTime": "2025-10-14 07:42:00"
    }
)
# Returns: {"status": "success", "query_text": "cluster(...).Device_Snapshot() | where DeviceId == 'a50be5c2-...'"}
```

### Step 3: Execute query
```python
# Agent executes the query
result = execute_query(query_text=result["query_text"])
```

## Testing

**Before fix**:
- All 8 queries: ❌ Failed at substitution
- No Kusto queries executed
- Error: "placeholder_values is a required property"

**After fix** (expected):
- Batch 1 (Step 1): ✅ Substitution succeeds, query executes
- Batch 2 (Steps 2,3,6,7): ✅ All 4 queries substitute and execute in parallel
- Batch 3 (Step 4): ✅ Uses EffectiveGroupId from Step 3
- Batch 4 (Step 5): ✅ Uses GroupId from Step 4
- Batch 5 (Step 8): ✅ Optional, uses TenantId from Step 1

## Related Files

- `backend/services/agent_framework_service.py` - Agent instructions updated
- `backend/mcp_servers/instructions/server.py` - Tool definition (no changes)
- `docs/PARALLEL_EXECUTION.md` - Parallel execution strategy

## Next Steps

1. **Test Device Timeline**: Run a device timeline query to verify substitution works
2. **Monitor logs**: Look for successful substitute_and_get_query calls with both parameters
3. **Verify parallel execution**: Confirm Batch 2 queries (Steps 2,3,6,7) run simultaneously
4. **Check performance**: Total execution time should be ~30s (down from ~60s)
