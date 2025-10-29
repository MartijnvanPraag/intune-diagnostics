# PolicyIdList Kusto Syntax Fix

**Date**: October 29, 2025  
**Issue**: Orchestrator looping after Step 5 due to Kusto query syntax error  
**Root Cause**: Query template + agent interpretation caused PolicyIdList substitution to create invalid KQL `in` operator syntax

## Problem Description

### Symptom
After successfully fixing two previous orchestrator loop issues:
1. ✅ Vague user prompt → explicit CRITICAL WORKFLOW instructions
2. ✅ Missing execute_query calls → two-call pattern emphasis

The orchestrator still looped after Step 5, but with different behavior - it was now executing all steps correctly but the Step 5 query was failing.

### Root Cause Analysis

**User discovered by examining app.log line 394:**

The generated Kusto query had invalid syntax:
```kusto
where PolicyId in (guid1,guid2,guid3)
```

This treats the GUIDs as **unquoted identifiers**, which is invalid KQL.

**Correct KQL `in` operator syntax requires individual quoted values:**
```kusto
where PolicyId in ('guid1', 'guid2', 'guid3')
```

### Investigation Results

**Problem 1: Query Template had extra quotes**

File: `instructions.md` Line 741 (BEFORE FIX #1)
```kusto
| where PolicyId in ('<PolicyIdList>')
```

The query template wrapped `<PolicyIdList>` in single quotes, expecting a single value.

**Problem 2: Agent was not preserving quote formatting**

Even though `conversation_state.json` stored the correctly formatted value:
```json
"policy_id_list": "'guid1', 'guid2', 'guid3'"
```

The agent was providing it to the MCP tool **without quotes**:
```python
'PolicyIdList': 'guid1,guid2,guid3'  # No quotes!
```

### The Dual Bug

**What happened during placeholder substitution:**

1. conversation_state extracts PolicyId values from Step 4 results
2. Formats them correctly: `'guid1', 'guid2', 'guid3'`
3. Stores in `policy_id_list` field
4. Saves to conversation_state.json with quotes: `"policy_id_list": "'guid1', 'guid2', 'guid3'"`
5. System instructions show this to the agent in JSON format
6. **Agent interprets the single quotes as Python/JSON string delimiters** and strips them
7. Agent provides to MCP tool: `'PolicyIdList': 'guid1,guid2,guid3'`
8. Query template substitutes into: `where PolicyId in (<PolicyIdList>)`
9. **Result**: `where PolicyId in (guid1,guid2,guid3)`
   - Unquoted identifiers instead of quoted string values
   - KQL parser fails
   - Query execution fails
   - Orchestrator detects failure
   - Orchestrator retries → **LOOP**

## Solution

### Fix #1: Remove Extra Quotes from Template

**File: `instructions.md` Line 741**
```kusto
| where PolicyId in (<PolicyIdList>)  # No quotes around placeholder
```

**Rationale**: Since the placeholder value should contain the quotes, don't add extra ones in the template.

### Fix #2: Add Safety Net for List Formatting

**File: `backend/services/agent_framework_service.py` Lines 323-342**

Added special handling in the MCP tool call normalization to ensure list placeholders are properly formatted:

```python
# Special handling for list placeholders (PolicyIdList, GroupIdList, etc.)
# Convert comma-separated GUIDs to quoted KQL format
if key.endswith('List') and isinstance(val, str) and ',' in val:
    # Remove any existing quotes and spaces, then reformat
    clean_values = [v.strip().strip("'\"") for v in val.split(',')]
    formatted_val = ', '.join(f"'{v}'" for v in clean_values if v)
    normalized[key] = formatted_val
    logger.debug(f"[AgentFramework] Formatted {key} for KQL: {formatted_val[:100]}...")
```

**How this works:**
1. Detects any placeholder ending with "List" (PolicyIdList, GroupIdList, etc.)
2. Strips existing quotes and whitespace from each value
3. Reformats with proper single quotes: `'value1', 'value2', 'value3'`
4. Logs the formatted result for debugging

**Why this is needed:**
- The agent (GPT model) may interpret the quotes in the JSON as string delimiters
- When constructing the placeholder_values dict, it provides just the raw values
- This safety net ensures proper KQL formatting regardless of how the agent provides the value

### Documentation Update

Updated placeholder description in instructions.md line 785:

```markdown
- `<PolicyIdList>`: Comma-separated list of individually quoted PolicyId/PayloadId values 
  (e.g., 'guid1', 'guid2', 'guid3') - formatted automatically by conversation_state service and agent_framework_service
```

## Testing

### Expected Behavior After Fix

1. Agent executes Steps 1-4 successfully ✅
2. conversation_state extracts PolicyId values from Step 4
3. Formats as: `'policy-guid-1', 'policy-guid-2', 'policy-guid-3'`
4. Agent calls substitute_and_get_query for Step 5
5. Template substitutes correctly:
   ```kusto
   | where PolicyId in ('policy-guid-1', 'policy-guid-2', 'policy-guid-3')
   ```
6. Agent calls execute_query for Step 5
7. Query executes successfully ✅
8. Agent completes device_timeline scenario
9. **No orchestrator loop** ✅

### Verification Steps

To test the fix:

```bash
# 1. Restart backend to reload updated instructions.md
cd c:\dev\intune-diagnostics
uv run uvicorn backend.main:app --reload

# 2. Start frontend
cd frontend
npm run dev

# 3. Run device_timeline scenario with known device ID
# 4. Monitor app.log for:
#    - Step 5 query text (should have correct 'in' syntax)
#    - Step 5 execute_query success (not HTTP 400 or syntax error)
#    - Agent completion (no loop after Step 5)
```

### Log Verification

**Check app.log for these indicators:**

✅ **Good - Correct query syntax:**
```
substitute_and_get_query: step 5
Query text: ... | where PolicyId in ('guid1', 'guid2', 'guid3')
```

✅ **Good - Successful execution:**
```
execute_query: step 5
Query executed successfully
Results: X rows
```

✅ **Good - Agent completion:**
```
Agent marked conversation as Final
Task completed successfully
```

❌ **Bad - Would indicate fix didn't work:**
```
Query text: ... | where PolicyId in (''guid1', 'guid2', 'guid3'')  # Double quotes
Query execution failed: Syntax error
Agent retrying step 5  # Loop indicator
```

## Related Issues

This fix completes the orchestrator loop resolution sequence:

1. **First Loop** (FIXED in ORCHESTRATOR_LOOPING_FIX.md):
   - Cause: Vague user prompt made agent think task incomplete
   - Fix: Added explicit CRITICAL WORKFLOW instructions
   
2. **Second Loop** (FIXED in AGENT_QUERY_ENTITY_FIX.md):
   - Cause: Agent using query_entity with $filter/$select → HTTP 400
   - Fix: Added API limitation warnings, made find_device_by_id recommended
   
3. **Third Loop** (FIXED in ORCHESTRATOR_LOOP_FIX_V2.md):
   - Cause: Agent stopping after substitute_and_get_query without execute_query
   - Fix: Emphasized two-call pattern in CRITICAL WORKFLOW
   
4. **Fourth Loop** (THIS FIX):
   - Cause: Query template created invalid KQL syntax in PolicyIdList substitution
   - Fix: Removed extra quotes from template, rely on conversation_state formatting

## Key Learnings

1. **Placeholder formatting responsibility**: conversation_state service formats list values, not query templates
2. **KQL `in` operator syntax**: Requires individual quoted values, not a single quoted string
3. **Query template design**: Templates should substitute pre-formatted values, not add additional formatting
4. **Debugging approach**: Examining actual generated query text in logs revealed the syntax error
5. **Separation of concerns**: 
   - conversation_state: Extract and format values
   - Query template: Structure and substitute
   - Don't duplicate formatting logic

## Files Modified

1. `instructions.md`:
   - Line 741: Removed quotes around `<PolicyIdList>` in Step 5 query
   - Line 785: Updated placeholder documentation to clarify formatting

2. `docs/POLICYIDLIST_KUSTO_SYNTAX_FIX.md`:
   - This documentation file

## Next Steps

After verifying this fix works:

1. ✅ Test device_timeline scenario end-to-end
2. ✅ Verify no orchestrator loops after Step 5
3. ✅ Confirm Step 5 query executes successfully
4. ✅ Check if any other scenarios use list-type placeholders (none found - PolicyIdList is the only one)
5. Consider: Add validation to conversation_state service to ensure formatted lists are valid for KQL

## Prevention

To prevent similar issues in the future:

1. **Query template review**: When adding new list-type placeholders, verify template doesn't add extra formatting
2. **conversation_state formatting**: Document which service is responsible for formatting each placeholder type
3. **Integration testing**: Test placeholder substitution with actual multi-value lists
4. **Syntax validation**: Consider adding KQL syntax validation before executing queries
5. **Log inspection**: Continue examining actual generated query text when debugging execution failures

---

**Status**: ✅ Fix implemented, ready for testing  
**Impact**: Resolves fourth orchestrator loop issue, completes device_timeline scenario execution
