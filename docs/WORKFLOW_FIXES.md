# Instructions MCP Server - Workflow Fixes

**Date**: October 15, 2025  
**Issue**: Agent workflow inefficiencies causing extra tool calls and confusion

## Problems Identified

### 1. Query ID Format Guessing ❌
**Issue**: Agent was fabricating query_id values like `device-details-step-1` instead of reading the actual ID from `get_scenario` response.

**Evidence**:
```
[INFO] substitute_and_get_query with args: {'query_id': 'device-details-step-1', ...}
[INFO] Final: There was an issue: the query_id device-details-step-1 was not found
```

**Actual query_id**: `device-details_step1` (underscores, not hyphens)

**Root Cause**: Orchestrator instructions said "Call substitute_and_get_query(query_id, ...)" without specifying HOW to get the query_id.

### 2. Placeholder Key Case Sensitivity ❌
**Issue**: User provides `{'deviceid': '...'}` but scenario expects `{'DeviceId': '...'}` - exact case match required.

**Evidence**:
```
Superstep 5: Agent tries {'deviceid': '...'} → fails
Superstep 8: Orchestrator corrects to {"DeviceId": "..."} → succeeds
```

**Root Cause**: `substitute_placeholders()` function used exact case-sensitive matching:
```python
if placeholder_name in placeholder_values:  # Case-sensitive!
```

### 3. Query Re-execution Confusion ❌
**Issue**: Agent calls `execute_query`, gets results successfully, but then asks for cluster/database parameters and executes the query AGAIN.

**Evidence**:
```
Superstep 9:  execute_query(...) → SUCCESS, returns data
Agent response: "I require the following details: clusterUrl, database..."
Superstep 11: execute_query(...clusterUrl=..., database=...) → executes AGAIN
```

**Root Cause**: Agent doesn't recognize successful execution, thinks query failed because of the multi-cluster union syntax in the query text.

---

## Fixes Applied

### Fix 1: Explicit Query ID Extraction Instructions ✅
**File**: `backend/services/agent_framework_service.py`

**Before**:
```python
f"5. For EACH step in the steps array:\n"
f"   a) Call substitute_and_get_query(query_id, placeholder_values)\n"
```

**After**:
```python
f"5. For EACH step in the steps array (in order):\n"
f"   a) Get step.query_id from the step object (e.g., 'device-details_step1')\n"
f"   b) Call substitute_and_get_query(query_id=step.query_id, placeholder_values={parameters})\n"
f"      NOTE: Placeholder keys are case-INSENSITIVE (deviceid = DeviceId = DEVICEID)\n"
```

**Added Critical Rule**:
```python
f"CRITICAL RULES:\n"
f"- NEVER guess query_id format - always read it from get_scenario response\n"
f"- If execute_query returns data successfully, do NOT call it again with different parameters\n"
f"- Placeholder keys match case-insensitively (deviceid works for DeviceId)\n\n"
```

### Fix 2: Case-Insensitive Placeholder Matching ✅
**File**: `backend/mcp_servers/instructions/server.py`

**Before**:
```python
def substitute_placeholders(step, placeholder_values: dict) -> SubstitutionResult:
    for match in pattern.finditer(step.query_text):
        placeholder_name = match.group(1)
        
        if placeholder_name in placeholder_values:  # ❌ Case-sensitive
            value = placeholder_values[placeholder_name]
```

**After**:
```python
def substitute_placeholders(step, placeholder_values: dict) -> SubstitutionResult:
    """Substitute placeholders in query with case-insensitive matching"""
    
    # Create case-insensitive lookup map
    value_map_lower = {k.lower(): v for k, v in placeholder_values.items()}
    
    for match in pattern.finditer(step.query_text):
        placeholder_name = match.group(1)
        placeholder_lower = placeholder_name.lower()
        
        # Try case-insensitive lookup
        if placeholder_lower in value_map_lower:  # ✅ Case-insensitive
            value = value_map_lower[placeholder_lower]
```

**Test Results**:
```
✅ DeviceId   → works
✅ deviceid   → works
✅ DeviceID   → works
✅ DEVICEID   → works
✅ WrongKey   → warning (as expected)
```

### Fix 3: Execute Query Success Recognition ✅
**File**: `backend/services/agent_framework_service.py`

**Added to workflow**:
```python
f"   d) Call execute_query(query=query_text)\n"
f"      NOTE: If execute_query returns data, the query succeeded - do NOT retry\n"
```

**Added to critical rules**:
```python
f"- If execute_query returns data successfully, do NOT call it again with different parameters\n"
```

---

## Expected Workflow Improvements

### Before Fixes:
```
Superstep 1: search_scenarios('device_details') ✅
Superstep 2: Orchestrator → "call get_scenario" ✅
Superstep 3: get_scenario('device-details') ✅
Superstep 4: Orchestrator → "call substitute_and_get_query" ⚠️
Superstep 5: substitute_and_get_query(query_id='device-details-step-1', ...) ❌ WRONG ID
           → Error: query_id not found
Superstep 6: Orchestrator → "review steps array, confirm query_id" ⚠️
Superstep 7: get_scenario('device-details') AGAIN ❌ REDUNDANT
           → Agent discovers correct ID: 'device-details_step1'
Superstep 8: Orchestrator → "use query_id='device-details_step1'" ✅
Superstep 9: substitute_and_get_query(query_id='device-details_step1', {'deviceid': '...'}) ⚠️
           → Case mismatch, but orchestrator fixes to DeviceId
           → execute_query() → SUCCESS with data ✅
           → Agent: "I need clusterUrl and database" ❌ CONFUSION
Superstep 10: Orchestrator → "use EU cluster or default" ⚠️
Superstep 11: substitute_and_get_query(...) AGAIN ❌ REDUNDANT
            → execute_query(clusterUrl=..., database=...) ❌ REDUNDANT
            → SUCCESS with data ✅
Superstep 12: Orchestrator → "Task completed" ✅
```

**Total**: 12 supersteps, 2 errors, 3 redundant calls

### After Fixes (Expected):
```
Superstep 1: search_scenarios('device_details') ✅
Superstep 2: Orchestrator → "call get_scenario with slug='device-details'" ✅
Superstep 3: get_scenario('device-details') ✅
           → Agent extracts: query_id='device-details_step1', placeholders={'DeviceId': guid}
Superstep 4: Orchestrator → "call substitute_and_get_query with query_id from step" ✅
Superstep 5: substitute_and_get_query(query_id='device-details_step1', {'deviceid': '...'}) ✅
           → Case-insensitive match works! ✅
           → extract query_text
           → execute_query(query=...) ✅
           → SUCCESS with data ✅
Superstep 6: Orchestrator → "Format results, provide summary, STOP" ✅
Superstep 7: Agent → Final formatted response ✅
```

**Total**: 7 supersteps, 0 errors, 0 redundant calls

**Improvement**: 
- ✅ 42% fewer supersteps (12 → 7)
- ✅ 0 errors (was 2)
- ✅ 0 redundant tool calls (was 3)
- ✅ Linear execution (no backtracking)

---

## Testing

### Test 1: Case-Insensitive Placeholders
**File**: `test_case_insensitive_placeholders.py`

**Results**: ✅ All tests pass
- Exact case: `DeviceId` → substitutes correctly
- Lowercase: `deviceid` → substitutes correctly
- Uppercase: `DEVICEID` → substitutes correctly
- Mixed case: `DeviceID` → substitutes correctly
- Wrong key: `SomeOtherId` → warning (expected)

### Test 2: Parser Fix (12 scenarios)
**File**: `test_parser_fix.py`

**Results**: ✅ All 12 scenarios load
- Device Details: 1 step with query_id='device-details_step1'
- All alias searches work (device_details, device-details, device info)
- get_scenario works for both slug and alias

### Test 3: End-to-End Workflow
**Pending**: Need to test actual agent execution with fixed instructions

**Expected behavior**:
1. Agent reads query_id from get_scenario response (not guesses)
2. Agent passes {'deviceid': '...'} and it works (case-insensitive)
3. Agent recognizes execute_query success on first call (no retry)
4. Workflow completes in ~7 supersteps (not 12)

---

## Files Modified

1. **backend/mcp_servers/instructions/server.py**
   - `substitute_placeholders()` - Added case-insensitive placeholder matching
   - Lines 434-463

2. **backend/services/agent_framework_service.py**
   - Orchestrator workflow instructions - Added explicit query_id extraction steps
   - Added "CRITICAL RULES" section
   - Lines 1123-1155

3. **backend/mcp_servers/instructions/parser.py**
   - Fixed implicit step creation for scenarios without step headings
   - Lines 207-224

4. **instructions.md**
   - Fixed Device Details metadata (removed duplicate slug values)
   - Line 107

---

## Next Steps

- [ ] Test end-to-end with device_details scenario
- [ ] Verify 7-step workflow (not 12)
- [ ] Verify no query_id errors
- [ ] Verify no placeholder case mismatch errors
- [ ] Verify no redundant execute_query calls
- [ ] Test other scenarios (device-timeline, autopilot-summary) to ensure generalization
