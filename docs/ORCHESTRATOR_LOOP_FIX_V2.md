# Orchestrator Loop Fix V2 - Missing execute_query Calls

## Problem Description

The orchestrator was still looping even after the initial loop fix. Analysis of the app.log revealed a new pattern:

**Superstep 1:**
- ✅ search_scenarios("device-timeline")
- ✅ get_scenario("device-timeline") → Returns 5 steps
- ✅ find_device_by_id(...) → Step 1 complete
- ✅ substitute_and_get_query("device-timeline_step2") → Get query
- ✅ execute_query(...) → Step 2 complete
- ✅ substitute_and_get_query("device-timeline_step3") → Get query
- ✅ execute_query(...) → Step 3 complete
- ✅ substitute_and_get_query("device-timeline_step4") → Get query
- ✅ execute_query(...) → Step 4 complete
- ✅ substitute_and_get_query("device-timeline_step5") → Get query
- ❌ Agent says "Final: I will now run the Kusto query" **BUT NEVER CALLS execute_query**

**Superstep 3:**
- ❌ Orchestrator restarts from search_scenarios (loop begins)

## Root Cause Analysis

### The Pattern

Looking at line 400 in app.log:
```
[Magentic-Agent-IntuneExpert] (assistant) Final: I will now run the Kusto query exactly as provided.
```

The agent marked itself as "Final" (complete) **after calling substitute_and_get_query** but **before calling execute_query**.

### Why This Happens

The agent is counting **tool calls** instead of **completed steps**:

| What Agent Counts | What Agent Should Count |
|-------------------|-------------------------|
| ✅ get_scenario (1 call) | ✅ Step 1: find_device_by_id |
| ✅ substitute_and_get_query step2 (1 call) | ✅ Step 2: substitute + **execute** |
| ✅ substitute_and_get_query step3 (1 call) | ✅ Step 3: substitute + **execute** |
| ✅ substitute_and_get_query step4 (1 call) | ✅ Step 4: substitute + **execute** |
| ✅ substitute_and_get_query step5 (1 call) | ✅ Step 5: substitute + **execute** |
| **Total: 5 calls → DONE** ❌ | **Total: 5 steps → NOT DONE** ❌ |

The agent thinks:
- "get_scenario said there are 5 steps"
- "I called substitute_and_get_query 4 times + find_device_by_id once = 5 calls"
- "I'm done!" ❌

But actually:
- Step 1 is complete (find_device_by_id returned data)
- Steps 2-4 are complete (substitute + execute for each)
- **Step 5 is INCOMPLETE** (substitute called, but execute NOT called)

### The Confusion

The agent doesn't understand that **getting a query is not the same as executing it**. The instructions said:

**Before (Vague):**
```
3. Execute ALL scenario steps sequentially (step 1, 2, 3, 4, 5, etc. until complete)
   - For each step: call substitute_and_get_query(query_id) then execute_query
```

The agent interpreted "for each step" as "call substitute_and_get_query for each step" and didn't realize that execute_query is **also required for each step**.

## Solution Implemented

### 1. Expanded CRITICAL WORKFLOW Section (Line ~1426)

**Before:**
```python
3. Execute ALL scenario steps sequentially (step 1, 2, 3, 4, 5, etc. until complete)
   - For each step: call substitute_and_get_query(query_id) then execute_query
   - Continue through ALL steps without stopping
```

**After:**
```python
3. Execute ALL scenario steps sequentially (step 1, 2, 3, 4, 5, etc. until complete)
   - Each Kusto step requires TWO tool calls in sequence:
     a) substitute_and_get_query(query_id="scenario-slug_stepN", placeholder_values={...})
     b) execute_query(query="<exact query from step a>")
   - Do NOT skip the execute_query call - getting the query is NOT execution
   - Continue through ALL steps without stopping
```

### 2. Updated EXECUTION RULES (Line ~1435)

Added explicit rules:
```python
- Each Kusto step needs substitute_and_get_query AND execute_query - both are required
- A step is NOT complete until execute_query returns results
- Do NOT stop after calling substitute_and_get_query - you must call execute_query next
- The scenario is complete when you've called execute_query for every step returned by get_scenario
```

### 3. Expanded CRITICAL RULES (Line ~878)

**Added new rules:**
```python
2. For Kusto steps: ALWAYS call substitute_and_get_query AND execute_query - both required
3. Getting a query with substitute_and_get_query is NOT execution - you must call execute_query next
```

### 4. Detailed EXAMPLE WORKFLOW (Line ~900)

**Before:**
```python
4. Step 2 (Kusto - Events):
   - substitute_and_get_query(...)
   - execute_query(...)
5. Continue through all remaining steps
```

**After:**
```python
4. Step 2 (Kusto - Events):
   - substitute_and_get_query(query_id="device-timeline_step2", ...)
   - execute_query(query="<returned query>") ← REQUIRED - don't skip this
5. Step 3 (Kusto - Events):
   - substitute_and_get_query(query_id="device-timeline_step3", ...)
   - execute_query(query="<returned query>") ← REQUIRED - don't skip this
6. Step 4 (Kusto - Events):
   - substitute_and_get_query(query_id="device-timeline_step4", ...)
   - execute_query(query="<returned query>") ← REQUIRED - don't skip this
7. Step 5 (Kusto - Events):
   - substitute_and_get_query(query_id="device-timeline_step5", ...)
   - execute_query(query="<returned query>") ← REQUIRED - don't skip this
8. After ALL execute_query calls complete, format all results and provide summary
```

Shows **all 5 steps explicitly** with both calls for each step.

## Expected Behavior After Fix

**Superstep 1 (Complete execution):**
```
✅ search_scenarios("device-timeline") → ONCE
✅ get_scenario("device-timeline") → ONCE (returns 5 steps)
✅ find_device_by_id(...) → Step 1 complete
✅ substitute_and_get_query("device-timeline_step2") → Get query for step 2
✅ execute_query(...) → Step 2 complete
✅ substitute_and_get_query("device-timeline_step3") → Get query for step 3
✅ execute_query(...) → Step 3 complete
✅ substitute_and_get_query("device-timeline_step4") → Get query for step 4
✅ execute_query(...) → Step 4 complete
✅ substitute_and_get_query("device-timeline_step5") → Get query for step 5
✅ execute_query(...) → Step 5 complete ← MUST HAPPEN
✅ Format results and return

Workflow complete (no loop, no restart)
```

## Key Insights

1. **The agent counts tool calls, not completed steps**
   - We need to be explicit about what constitutes a "complete step"
   - "Getting a query" ≠ "Executing a query"

2. **The two-call pattern must be crystal clear**
   - Showing all 5 steps explicitly in the example prevents ambiguity
   - Adding "← REQUIRED - don't skip this" reinforces the necessity

3. **Completion criteria must be unambiguous**
   - "The scenario is complete when you've called execute_query for every step"
   - Not "when you've called substitute_and_get_query for every step"

4. **Negative instructions are important**
   - "Do NOT stop after calling substitute_and_get_query"
   - "Do NOT skip the execute_query call"

## Diagnostic Tips

To diagnose similar issues in the future:

1. **Look for "Final:" markers in agent logs**
   - These indicate when the agent thinks it's done
   - Check what the last tool call was before "Final:"

2. **Count tool calls vs steps**
   - If agent stops after N calls where N = number of steps, it's counting wrong
   - Each Kusto step = 2 calls (substitute + execute)

3. **Check for incomplete step patterns**
   - `substitute_and_get_query` without corresponding `execute_query` = incomplete

4. **Monitor superstep transitions**
   - If orchestrator starts new superstep after agent says "Final:", agent completed early

## Files Modified

1. **backend/services/agent_framework_service.py** (Lines 1426-1450, 878-887, 900-920)
   - Expanded CRITICAL WORKFLOW with two-call pattern details
   - Updated EXECUTION RULES with step completion criteria
   - Added CRITICAL RULES #2 and #3 about both calls being required
   - Detailed EXAMPLE WORKFLOW showing all 5 steps with both calls

## Testing

To verify the fix:

1. Restart backend
2. Run device-timeline query
3. Monitor log for:
   - ✅ Step 5: Both `substitute_and_get_query` AND `execute_query` called
   - ✅ No "Final:" marker after substitute_and_get_query for step 5
   - ✅ "Final:" marker only appears after execute_query for step 5
   - ✅ No "Starting superstep 3" (workflow completes in supersteps 1-2)

Expected log pattern:
```
[INFO] substitute_and_get_query for device-timeline_step5
[INFO] execute_query (step 5 query)  ← MUST SEE THIS
[INFO] [Magentic-Agent] Final: ...   ← SHOULD BE AFTER execute_query
```

## Related Documentation

- `docs/ORCHESTRATOR_LOOPING_FIX.md` - Original loop fix (generic instructions issue)
- `docs/AGENT_QUERY_ENTITY_FIX.md` - query_entity with filter issue
- `backend/services/agent_framework_service.py` - System instructions implementation

## Impact

This fix should:
- ✅ Eliminate premature completion after step 5's substitute_and_get_query
- ✅ Ensure ALL execute_query calls happen for all scenario steps
- ✅ Prevent orchestrator loop (no restart needed)
- ✅ Complete device-timeline in single superstep
- ✅ Provide complete results (all 5 steps executed)
