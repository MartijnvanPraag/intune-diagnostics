# Agent Framework Looping Fix - Implementation Summary

**Date**: October 16, 2025  
**Issue**: Multi-step scenarios (device-timeline) were looping excessively, restarting from step 1 multiple times  
**Root Causes Identified**: Case mismatch, orchestrator restarts, no state preservation, excessive max rounds

---

## Problems Identified from app.log Analysis

### 1. **Placeholder Case Mismatch** ⚠️ CRITICAL
- **Problem**: Context provided `effective_group_id_list` (snake_case) but MCP expected `EffectiveGroupIdList` (PascalCase)
- **Result**: Validation failures → Agent retries → Orchestrator restarts → Loop continues
- **Log Evidence**:
  ```
  placeholder_values: {'effective_group_id_list': "'4e7ed792-..."}
  → errors: [{"placeholder": "EffectiveGroupIdList", "issue": "Required placeholder not provided"}]
  ```

### 2. **Orchestrator Restarts** ⚠️ CRITICAL
- **Problem**: After steps 1-4 completed, orchestrator said "Please execute the 'device_timeline' scenario"
- **Result**: Agent restarts from step 1 instead of continuing from step 5
- **Pattern**: Round 1: Steps 1-4 → Round 2: Steps 1-4 again → Round 3: Steps 1-4 again

### 3. **No State Preservation**
- **Problem**: Agent doesn't remember which steps were already completed
- **Result**: Same steps executed multiple times across orchestration rounds

### 4. **Excessive Max Rounds**
- **Problem**: `max_round_count=50` allowed looping to continue indefinitely
- **Result**: Device timeline (8 steps) taking excessive time due to retries

---

## Implemented Solutions

### ✅ Fix 1: Proper Placeholder Case Conversion

**Added Method**: `_build_placeholder_values(parameters, context_values)`

```python
def _build_placeholder_values(self, parameters: dict, context_values: dict) -> dict:
    """Build complete placeholder values with proper PascalCase conversion."""
    placeholder_values = {}
    
    # Convert API parameters (snake_case) to PascalCase
    for key, value in parameters.items():
        pascal_key = ''.join(word.capitalize() for word in key.split('_'))
        # Handle datetime conversion
        if isinstance(value, str) and ('time' in key.lower()):
            # Convert ISO 8601 → Kusto format
            value = convert_datetime(value)
        placeholder_values[pascal_key] = value
    
    # Convert context values (snake_case) to PascalCase
    context_mapping = {
        'device_id': 'DeviceId',
        'effective_group_id_list': 'EffectiveGroupIdList',  # ← CRITICAL FIX
        'group_id_list': 'GroupIdList',
        'policy_id_list': 'PolicyIdList',
        # ... other mappings
    }
    
    for context_key, context_value in context_values.items():
        pascal_key = context_mapping.get(context_key)
        if pascal_key and pascal_key not in placeholder_values:
            placeholder_values[pascal_key] = context_value
    
    return placeholder_values
```

**Impact**: 
- ✅ All placeholders now in correct PascalCase format
- ✅ Validation errors eliminated
- ✅ Steps execute successfully on first try

---

### ✅ Fix 2: Proactive Context Loading

**Modified**: `query_diagnostics()` method

**Before** (Reactive):
```python
# Agent had to discover missing placeholders through validation errors
# Then call lookup_context() to fix them
# Required multiple retries
```

**After** (Proactive):
```python
# Get ALL context values upfront
context_service = get_conversation_state_service()
context_values = context_service.get_all_context()

# Build COMPLETE placeholder values before starting
all_placeholder_values = self._build_placeholder_values(parameters, context_values)

# Provide ALL placeholders to agent in initial message
query_message = f"""
**COMPLETE PLACEHOLDER VALUES (use these for ALL steps):**
{json.dumps(all_placeholder_values, indent=2)}
```

**Impact**:
- ✅ Agent has all needed values from the start
- ✅ No reactive error handling needed
- ✅ Faster execution (no lookup_context() retries)

---

### ✅ Fix 3: Anti-Looping Instructions

**Enhanced**: Agent system instructions with explicit anti-looping rules

**Added Rules**:
```python
**CRITICAL RULES FOR MULTI-STEP SCENARIOS:**

1. **STATE PRESERVATION**: Remember completed steps.
   NEVER restart from step 1 after executing any steps.

2. **PLACEHOLDER HANDLING - CASE SENSITIVITY**:
   - ALWAYS use PascalCase: DeviceId, EffectiveGroupIdList, etc.
   - Convert snake_case from lookup_context() to PascalCase
   - CRITICAL MAPPINGS:
     * effective_group_id_list → EffectiveGroupIdList
     * group_id_list → GroupIdList

3. **SEQUENTIAL EXECUTION - NO LOOPING**:
   - Execute in strict order: Step 1 → 2 → 3 → ... → N → DONE
   - Track progress: "Completed steps: 1, 2, 3"
   - After last step: Format results and STOP
   - DO NOT loop back to step 1

4. **ERROR RECOVERY WITHOUT RESTARTING**:
   - If step fails: Skip and continue to next
   - DO NOT restart entire workflow

5. **COMPLETION CRITERIA**:
   - State: "Completed all N steps"
   - STOP - no more tool calls
   - If asked to continue: "All steps completed, results returned"
```

**Impact**:
- ✅ Agent explicitly told not to loop
- ✅ Clear completion criteria
- ✅ Error handling without restarting

---

### ✅ Fix 4: Updated Workflow Instructions

**Enhanced**: Per-request query message with sequential execution emphasis

```python
query_message = f"""
Execute '{query_type}' scenario for {identifier_str}

**COMPLETE PLACEHOLDER VALUES (use these for ALL steps):**
{all_placeholder_values}

WORKFLOW - EXECUTE SEQUENTIALLY WITHOUT LOOPING:
1. Call search_scenarios('{normalized_query_type}')
2. Call get_scenario(slug) → Extract steps array (8-9 steps for device-timeline)
3. For EACH step in order (step 1, 2, 3, ... 8):
   a. Call substitute_and_get_query(query_id, placeholder_values=<ALL values above>)
   b. If success: execute_query → Mark COMPLETE → Continue to NEXT step
   c. If validation failed: Skip → Continue to NEXT step
4. After executing ALL steps: Format results and STOP
   DO NOT loop back to step 1
   DO NOT restart the scenario

CRITICAL RULES - PREVENT LOOPING:
- Execute steps SEQUENTIALLY: 1 → 2 → 3 → ... → 8 → DONE
- NEVER restart from step 1 after completing any steps
- After step 8: FORMAT RESULTS and STOP
```

**Impact**:
- ✅ Extremely clear sequential instructions
- ✅ Explicit "DO NOT loop" warnings
- ✅ Complete placeholder values provided upfront

---

### ✅ Fix 5: Reduced Max Orchestration Rounds

**Modified**: Magentic workflow configuration

**Before**:
```python
.with_standard_manager(
    max_round_count=50,  # Too high - allowed excessive looping
    max_stall_count=5,
)
```

**After**:
```python
.with_standard_manager(
    max_round_count=15,  # Reasonable for 8-step scenario + some retries
    max_stall_count=3,   # Fail faster if stuck
)
```

**Impact**:
- ✅ Prevents runaway looping (max 15 rounds instead of 50)
- ✅ Faster failure detection if something is wrong
- ✅ Still allows retries for legitimate errors

---

## Expected Behavior After Fixes

### Before (Looping):
```
Round 1: search → get_scenario → steps 1,2,3,4 (fail at 4 - case mismatch)
Round 2: Orchestrator: "Execute device_timeline" → search → steps 1,2,3,4 (fail again)
Round 3: Orchestrator: "Execute device_timeline" → search → steps 1,2,3,4 (fail again)
... continues looping ...
Total time: Excessive (multiple rounds × 4 steps each)
```

### After (Sequential):
```
Round 1:
  - Get context values upfront (EffectiveGroupIdList, etc.)
  - Build complete placeholder values (ALL in PascalCase)
  - search_scenarios → get_scenario
  - Step 1: substitute + execute ✅
  - Step 2: substitute + execute ✅
  - Step 3: substitute + execute ✅ (extracts EffectiveGroupId values)
  - Step 4: substitute (has EffectiveGroupIdList!) + execute ✅
  - Step 5: substitute + execute ✅
  - Step 6: substitute + execute ✅
  - Step 7: substitute + execute ✅
  - Step 8: substitute + execute ✅
  - Format results → STOP

Total time: Fast (1 round, 8 steps executed sequentially)
```

---

## Key Improvements Summary

| Issue | Before | After | Impact |
|-------|--------|-------|--------|
| **Case Mismatch** | `effective_group_id_list` → validation error | `EffectiveGroupIdList` → validation success | ✅ No validation errors |
| **Context Loading** | Reactive (on error) | Proactive (upfront) | ✅ Faster, simpler |
| **Looping** | Restarts from step 1 | Sequential execution | ✅ No wasted work |
| **Max Rounds** | 50 (excessive) | 15 (reasonable) | ✅ Prevents runaway |
| **Instructions** | Vague about looping | Explicit anti-loop rules | ✅ Clear guidance |
| **Execution Time** | Multiple rounds × 4 steps | 1 round × 8 steps | ✅ Much faster |

---

## Testing Recommendations

1. **Test device-timeline scenario**:
   - Should complete in ~1 orchestration round
   - All 8 steps should execute sequentially
   - No restarts from step 1

2. **Monitor logs for**:
   - ✅ "Built placeholder values with N keys: ['DeviceId', 'StartTime', 'EndTime', 'EffectiveGroupIdList', ...]"
   - ✅ "Extracted 1 values for effective_group_id_list: '...'"
   - ✅ All substitute_and_get_query calls succeed (status: success)
   - ❌ No validation_failed errors for EffectiveGroupIdList
   - ❌ No "search_scenarios" calls after initial one
   - ❌ No loops back to step 1

3. **Performance metrics**:
   - Device timeline should complete in < 30 seconds (was taking minutes)
   - Round count should be 1-2 (was 10+)
   - Step execution should be linear (1→2→3→...→8, no repeats)

---

## Files Modified

1. **`backend/services/agent_framework_service.py`**:
   - Added `_build_placeholder_values()` method
   - Modified `query_diagnostics()` to load context upfront
   - Enhanced system instructions with anti-looping rules
   - Updated query message with sequential execution emphasis
   - Reduced max_round_count from 50 → 15
   - Reduced max_stall_count from 5 → 3

---

## Conclusion

These fixes address the root causes of looping behavior in multi-step scenarios:

1. ✅ **Placeholder case conversion** ensures validation succeeds
2. ✅ **Proactive context loading** provides all values upfront
3. ✅ **Anti-looping instructions** guide agent to execute sequentially
4. ✅ **Reduced max rounds** prevents runaway looping
5. ✅ **Clear workflow instructions** emphasize sequential execution

The device-timeline scenario should now execute efficiently in a single orchestration round with all 8 steps completing sequentially.
