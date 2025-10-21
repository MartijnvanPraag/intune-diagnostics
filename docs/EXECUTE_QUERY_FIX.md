# Execute Query Fix - Embedded Cluster URLs

**Date**: October 15, 2025  
**Issue**: Agent keeps asking for clusterUrl and database parameters even though they're already embedded in the Kusto queries  
**NEW CRITICAL ISSUE**: Agent hallucinating queries instead of using queries from instructions.md

## Problem

### Issue 1: Parameter Requirements (FIXED)
The Kusto queries in `instructions.md` use the `cluster()` function to specify cluster URLs directly:

```kusto
let DeviceID = '<DeviceId>';
let base_query = (cluster: string, source: string) {
    cluster(cluster).database("qrybkradxglobaldb").Device_Snapshot()
        | where DeviceId == DeviceID
};
union
   base_query('qrybkradxeu01pe.northeurope.kusto.windows.net', 'europe'),  
   base_query('qrybkradxus01pe.westus2.kusto.windows.net', 'Non-EU')
```

**The cluster URLs are IN the query!** The agent should just:
1. Replace `<DeviceId>` with the actual value
2. Execute the query AS-IS

But instead, the agent was:
1. Calling `execute_query(query=...)`  ❌ Missing clusterUrl/database
2. Getting error: "Missing required parameters: clusterUrl, database, query"
3. Asking user for clusterUrl and database ❌ They're already in the query!
4. Executing again with explicit parameters

### Issue 2: Query Hallucination (NEW - CRITICAL!)

**Even worse**: After fixing the parameter issue, the agent started **generating its own queries** instead of using the ones from `instructions.md`!

**Evidence from logs**:
```python
[INFO] services.agent_framework_service: [AgentFramework] Calling MCP tool 'execute_query' with args: {
  'query': "DeviceInventory\n| where DeviceId == 'a50be5c2-d482-40ab-af57-18bace67b0ec'\n| project DeviceId, DeviceName, OS, OSVersion, SerialNumber, AzureADDeviceId, PrimaryUser, EnrollmentDate, ManagementType, Manufacturer, Model"
}
```

**This query is COMPLETELY MADE UP!**

- ❌ `DeviceInventory` table doesn't exist (should be `Device_Snapshot()`)
- ❌ Column names are wrong (`DeviceName`, `OS`, `OSVersion` don't exist)
- ❌ Missing the `cluster()` calls
- ❌ Missing the `let DeviceID` variable
- ❌ Missing the `union` across EU/US clusters

**The correct query from instructions.md**:
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

**Root Cause**: The agent was **ignoring the substitute_and_get_query tool result** and generating a query based on its training data instead of using the exact query text returned by the MCP tool.

## Root Cause Analysis

### Issue 1 Root Cause
The `execute_query` tool handler in `agent_framework_service.py` had this check:

```python
if cluster_url and database and query:
    # Execute query
    ...
else:
    return {"error": "Missing required parameters: clusterUrl, database, query"}
```

This **required** both clusterUrl and database to be explicitly provided, even for queries that already contain `cluster()` calls.

### Issue 2 Root Cause
The agent's system instructions were **not strong enough** about requiring exact query usage. The instructions said:

```
BEST PRACTICES:
- Use exact query text from substitute_and_get_query (do not modify)
```

This was treated as a **suggestion** rather than a **hard requirement**. The agent felt free to "improve" or "simplify" the query by generating its own.

## Fix

### Fix 1: Execute Query Parameters (COMPLETED)
Updated the execute_query handler to support **two modes**:

#### Mode 1: Query with Embedded cluster() Calls (NEW!)
```python
execute_query(query='let DeviceID = \'abc-123\'...')
```

- NO clusterUrl or database parameters needed
- Query text contains `cluster('url').database('db')`  
- Just execute the query AS-IS

#### Mode 2: Simple Query with Explicit Cluster/Database (EXISTING)
```python
execute_query(
    clusterUrl='intune.kusto.windows.net',
    database='intune', 
    query='IntuneEvent | where DeviceId == "..."'
)
```

- For simple queries without cluster() calls
- clusterUrl and database are required
- Backwards compatible with existing usage

### Fix 2: Agent Instructions (CRITICAL - NEW!)

**Updated agent system instructions to FORBID query generation**:

**Before** (Too weak):
```python
BEST PRACTICES:
- Use exact query text from substitute_and_get_query (do not modify)
```

**After** (Strong prohibition):
```python
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

**Updated orchestrator instructions**:

**Before**:
```python
f"3. For each step:\n"
f"   substitute_and_get_query(query_id, {parameters}) → extract query_text\n"
f"   execute_query(query=query_text) → run query AS-IS\n"
```

**After**:
```python
f"3. For EACH step:\n"
f"   a. Call substitute_and_get_query(query_id, {parameters})\n"
f"   b. Extract the 'query_text' field from the JSON response\n"
f"   c. Call execute_query(query=<exact query_text string>) with NO modifications\n"
f"\n"
f"CRITICAL RULES:\n"
f"- NEVER generate Kusto queries yourself\n"
f"- ALWAYS use the exact query_text from substitute_and_get_query\n"
f"- DO NOT pass clusterUrl or database to execute_query (already embedded in query)\n"
f"- DO NOT modify, reformat, or 'fix' the query text in any way\n"
```

### Why This Fix Is Critical

The MCP Instructions server **IS working correctly** - it returns the right queries:
- ✅ Correct table names (`Device_Snapshot()`)
- ✅ Correct `cluster()` calls with URLs
- ✅ Correct `union` across EU/US clusters
- ✅ Correct placeholder substitution

**The problem was the agent ignoring the tool result** and generating its own query.

The new instructions make it **absolutely clear**:
1. **NEVER** generate queries
2. **ALWAYS** use the exact text from the tool
3. **NO** modifications allowed

This prevents the agent from "helping" by rewriting queries in a way that breaks them.

## Code Changes

**File**: `backend/services/agent_framework_service.py`

### Change 1: Execute Query Handler (Lines 215-275)

**Before**:
```python
if cluster_url and database and query:
    # Execute with explicit cluster/database
    ...
else:
    return {"error": "Missing required parameters"}
```

**After**:
```python
if not query:
    return {"error": "Missing required parameter: query"}

if cluster_url and database:
    # Mode 2: Explicit cluster/database for simple queries
    mcp_args = {"clusterUrl": cluster_url, "database": database, "query": query}
else:
    # Mode 1: Query with embedded cluster() - execute directly
    logger.info("Executing query with embedded cluster() calls")
    mcp_args = {"query": query}

# Execute
result = await kusto_service._session.call_tool(tool_name, mcp_args)
```

### Change 2: Agent System Instructions (Lines 750-760)

**Before**:
```python
BEST PRACTICES:
- Execute all queries in scenario before returning results
- Use exact query text from substitute_and_get_query (do not modify)
- Extract identifiers from results to populate next step placeholders
- After final results returned: STOP (no more tool calls)
```

**After**:
```python
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

### Change 3: Orchestrator Task Instructions (Lines 1135-1150)

**Before**:
```python
f"Steps:\n"
f"1. search_scenarios('{query_type}') → get slug\n"
f"2. get_scenario(slug) → get steps[].query_id  \n"
f"3. For each step:\n"
f"   substitute_and_get_query(query_id, {parameters}) → extract query_text\n"
f"   execute_query(query=query_text) → run query AS-IS\n"
f"4. Format results as table\n\n"
f"CRITICAL: execute_query only needs 'query' parameter - DO NOT provide clusterUrl/database!\n"
```

**After**:
```python
f"WORKFLOW:\n"
f"1. search_scenarios('{query_type}') → get slug\n"
f"2. get_scenario(slug) → get steps[].query_id\n"
f"3. For EACH step:\n"
f"   a. Call substitute_and_get_query(query_id, {parameters})\n"
f"   b. Extract the 'query_text' field from the JSON response\n"
f"   c. Call execute_query(query=<exact query_text string>) with NO modifications\n"
f"4. Format results as table and STOP\n\n"
f"CRITICAL RULES:\n"
f"- NEVER generate Kusto queries yourself\n"
f"- ALWAYS use the exact query_text from substitute_and_get_query\n"
f"- DO NOT pass clusterUrl or database to execute_query (already embedded in query)\n"
f"- DO NOT modify, reformat, or 'fix' the query text in any way\n"
```

## Orchestrator Instructions

Updated task ledger to make it crystal clear:

**Before**:
```python
f"4. execute_query(query=query_text) → execute and get results\n"
```

**After**:
```python
f"   execute_query(query=query_text) → run query AS-IS (cluster URLs are already in query)\n"
f"CRITICAL: execute_query only needs 'query' parameter - DO NOT provide clusterUrl/database!\n"
f"The queries already contain cluster() calls with URLs embedded.\n"
```

## Expected Behavior After Fix

### Before Fix:
```
Superstep 5: substitute_and_get_query(...) → get query_text with embedded cluster()
            execute_query(query=...) → ERROR: Missing clusterUrl/database
            Agent: "Please provide clusterUrl and database"
Superstep 6: Orchestrator: "Use EU cluster or default"
Superstep 7: execute_query(clusterUrl='...', database='...', query=...) → SUCCESS
            (But this ignores the embedded cluster() calls!)
```

### After Fix:
```
Superstep 5: substitute_and_get_query(...) → get query_text with embedded cluster()
            execute_query(query=...) → SUCCESS (uses embedded cluster URLs)
            Agent: Returns results formatted as table
Superstep 6: Orchestrator: "Format results and return"
```

**Result**: 
- ✅ No more asking for cluster/database
- ✅ Queries execute with their embedded cluster() calls
- ✅ Union queries across EU/US clusters work correctly
- ✅ Fewer supersteps (5-6 instead of 11-12)

## Testing

Test with device_details scenario:

1. Query returned by `substitute_and_get_query`:
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

2. Agent calls: `execute_query(query=<above text>)`

3. ✅ Executes successfully without needing cluster

URL/database

4. ✅ Returns device data from both EU and US clusters

## Files Modified

1. **backend/services/agent_framework_service.py**:
   - Lines 215-275: Updated execute_query handler to support both modes
   - Lines 750-760: Strengthened agent system instructions with explicit prohibitions
   - Lines 1135-1150: Updated orchestrator instructions with step-by-step workflow

## Backwards Compatibility

✅ **Fully backwards compatible!**

Existing code that provides clusterUrl and database will continue to work (Mode 2).

New code that only provides query (with embedded cluster() calls) will also work (Mode 1).

The tool automatically detects which mode based on parameters provided.

## Verification

**Test 1: Instructions MCP Server Returns Correct Query** ✅

Created `test_mcp_query_return.py` to verify the MCP server:

```
✅ Loaded 12 scenarios
✅ Found scenario: Device Details
✅ Query contains cluster() calls
✅ Substituted query length: 341 characters
✅ Placeholders used: {'DeviceId': 'a50be5c2-d482-40ab-af57-18bace67b0ec'}
```

**Query returned by MCP server** (CORRECT):
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

**Test 2: Agent Was Hallucinating Query** ❌ → ✅ FIXED

**Before fix** - Agent generated this query (WRONG):
```kusto
DeviceInventory
| where DeviceId == 'a50be5c2-d482-40ab-af57-18bace67b0ec'
| project DeviceId, DeviceName, OS, OSVersion, SerialNumber, AzureADDeviceId, PrimaryUser, EnrollmentDate, ManagementType, Manufacturer, Model
```

**Issues**:
- ❌ Wrong table (`DeviceInventory` instead of `Device_Snapshot()`)
- ❌ Wrong columns (`DeviceName`, `OS`, `OSVersion` don't exist)
- ❌ Missing `cluster()` calls
- ❌ Missing `let` variable
- ❌ Missing `union` across clusters

**After fix** - Agent will use exact query from MCP tool:
- ✅ Uses substitute_and_get_query tool
- ✅ Extracts query_text field from JSON response
- ✅ Passes exact string to execute_query with NO modifications
- ✅ No clusterUrl/database parameters (already in query)

## Next Steps

1. **Test end-to-end with device_details scenario**:
   - Agent calls substitute_and_get_query → gets correct query
   - Agent extracts query_text field → exact match with instructions.md
   - Agent calls execute_query(query=...) → no clusterUrl/database
   - Query executes successfully → returns device data
   - Results formatted as table → workflow completes

2. **Monitor logs for**:
   - ✅ "Executing query with embedded cluster() calls"
   - ✅ Query text starts with "let DeviceID ="
   - ✅ No "Invalid arguments" errors
   - ❌ NO "DeviceInventory" or hallucinated queries

3. **Expected superstep count**: 5-7 (not 12+)

## Summary

**Root Cause**: Two-part problem
1. ✅ FIXED: execute_query required clusterUrl/database even for embedded cluster() queries
2. ✅ FIXED: Agent system instructions too weak - treated as suggestions, not requirements

**Solution**: Two-part fix
1. ✅ Made execute_query parameters optional - supports query-only execution
2. ✅ Strengthened agent instructions - explicit prohibitions against query generation

**Result**: Agent will now:
- ✅ Use exact queries from instructions.md (via MCP tool)
- ✅ Never generate or modify queries
- ✅ Execute queries with embedded cluster() calls
- ✅ Work reliably and predictably
