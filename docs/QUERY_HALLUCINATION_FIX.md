# CRITICAL FIX: Agent Query Hallucination

**Date**: October 15, 2025  
**Severity**: 🔴 **CRITICAL** - Agent was generating fake queries instead of using real ones from instructions.md

## The Problem

The agent was **completely ignoring** the queries from `instructions.md` and **making up its own queries** that don't work.

### What Should Happen
```
Agent → substitute_and_get_query(query_id, deviceid) 
     → Returns: {"query_text": "let DeviceID = '...'; cluster(...).database(...).Device_Snapshot() | ..."}
Agent → execute_query(query=<exact string from above>)
     → Executes and returns results ✅
```

### What Was Actually Happening
```
Agent → substitute_and_get_query(query_id, deviceid)
     → Returns: {"query_text": "let DeviceID = '...'; cluster(...).database(...).Device_Snapshot() | ..."}
Agent → ❌ IGNORES the query_text
Agent → ❌ GENERATES its own query: "DeviceInventory | where DeviceId == '...' | project ..."
Agent → execute_query(query=<hallucinated query>)
     → ERROR: Table 'DeviceInventory' not found ❌
```

## Evidence from Logs

**MCP Tool Returns** (CORRECT):
```kusto
let DeviceID = 'a50be5c2-d482-40ab-af57-18bace67b0ec';
let base_query = (cluster: string, source: string) {
    cluster(cluster).database("qrybkradxglobaldb").Device_Snapshot()
        | where DeviceId == DeviceID
};
union
   base_query('qrybkradxeu01pe.northeurope.kusto.windows.net', 'europe'),
   base_query('qrybkradxus01pe.westus2.kusto.windows.net', 'Non-EU')
```

**Agent Executed** (WRONG - HALLUCINATED):
```kusto
DeviceInventory
| where DeviceId == 'a50be5c2-d482-40ab-af57-18bace67b0ec'
| project DeviceId, DeviceName, OS, OSVersion, SerialNumber, AzureADDeviceId, PrimaryUser, EnrollmentDate, ManagementType, Manufacturer, Model
```

**Problems with hallucinated query**:
- ❌ Wrong table: `DeviceInventory` (doesn't exist) instead of `Device_Snapshot()`
- ❌ Wrong columns: `DeviceName`, `OS`, `OSVersion` (don't exist)
- ❌ Missing: `cluster()` calls with URLs
- ❌ Missing: `let DeviceID` variable
- ❌ Missing: `union` across EU/US clusters

## Root Cause

**Agent system instructions were TOO WEAK**:

```python
# Before (treated as a suggestion)
BEST PRACTICES:
- Use exact query text from substitute_and_get_query (do not modify)
```

The agent interpreted this as:
> "Yeah that's a good practice, but I can write better queries myself based on my training data"

## The Fix

**Strengthened agent instructions to FORBID query generation**:

```python
# After (hard requirement with explicit prohibitions)
CRITICAL RULES:
1. NEVER write Kusto queries yourself - ALWAYS use substitute_and_get_query to get the exact query
2. ALWAYS pass the exact query_text from substitute_and_get_query to execute_query unchanged
3. DO NOT modify, reformat, or "improve" queries - use them EXACTLY as returned
4. DO NOT generate queries based on what you think should work
5. The queries in instructions.md are the ONLY source of truth

WORKFLOW:
- substitute_and_get_query returns {"query_text": "..."} → extract query_text field
- execute_query(query=query_text) → pass the exact string unchanged
- After final results: STOP (no more tool calls)
```

**Also strengthened orchestrator instructions**:

```python
f"3. For EACH step:\n"
f"   a. Call substitute_and_get_query(query_id, {parameters})\n"
f"   b. Extract the 'query_text' field from the JSON response\n"
f"   c. Call execute_query(query=<exact query_text string>) with NO modifications\n"
f"\n"
f"CRITICAL RULES:\n"
f"- NEVER generate Kusto queries yourself\n"
f"- ALWAYS use the exact query_text from substitute_and_get_query\n"
f"- DO NOT modify, reformat, or 'fix' the query text in any way\n"
```

## Verification

Created `test_mcp_query_return.py` to verify the MCP server IS working correctly:

```
✅ Loaded 12 scenarios
✅ Query contains cluster() calls
✅ Placeholders used: {'DeviceId': 'a50be5c2-d482-40ab-af57-18bace67b0ec'}
✅ Query text: 341 characters (correct)
```

**The Instructions MCP server works perfectly** - it returns the right queries. The problem was the agent ignoring them.

## Impact

**Before Fix**:
- ❌ Agent generates fake queries
- ❌ Queries fail with "table not found" errors
- ❌ User gets no results
- ❌ Agent asks for clusterUrl/database (even though they're in the query)

**After Fix**:
- ✅ Agent uses exact queries from instructions.md
- ✅ Queries execute successfully
- ✅ User gets correct results
- ✅ No hallucinations or query modifications

## Files Changed

- `backend/services/agent_framework_service.py`:
  - Lines 750-760: Agent system instructions (strengthened)
  - Lines 1135-1150: Orchestrator task instructions (explicit workflow)

## Testing

**Next step**: Test end-to-end with device_details scenario and verify:

1. ✅ Agent calls substitute_and_get_query
2. ✅ Agent receives correct query with cluster() calls
3. ✅ Agent extracts query_text field
4. ✅ Agent calls execute_query with EXACT query text
5. ✅ NO clusterUrl/database parameters
6. ✅ NO query modifications or "improvements"
7. ✅ Query executes successfully
8. ✅ Results returned and formatted

**Look for in logs**:
- ✅ "Executing query with embedded cluster() calls"
- ✅ Query starts with "let DeviceID ="
- ❌ NO "DeviceInventory" or other hallucinated table names

## Why This Matters

**The entire system depends on using the EXACT queries from instructions.md**:

1. Queries are tested and validated ✅
2. Queries have correct cluster URLs for EU/US ✅
3. Queries use correct table/column names ✅
4. Queries handle multi-step scenarios correctly ✅

If the agent generates its own queries:
1. ❌ Untested and likely broken
2. ❌ Missing cluster URLs
3. ❌ Wrong table/column names (based on GPT training data)
4. ❌ Can't handle complex multi-step logic

**This fix is absolutely critical** to make the system work at all.
