# Agent Looping Issue - Root Cause Analysis and Fixes

## Problem Summary
The agent was continuously looping when executing the Device Timeline scenario:
1. Agent would search for scenarios and start executing queries
2. After executing 1-2 queries, it would loop back and search for scenarios AGAIN
3. This cycle repeated indefinitely until the orchestrator detected a stall (after ~10 supersteps)
4. The Manager was not appearing in logs (expected "Manager: Creating plan")

## Root Causes Identified

### 1. **Outdated Device Timeline Instructions** (Line 1089)
**Problem**: The `device_timeline` query type had instructions that referenced the OLD legacy tool:
```python
"1. Look up the 'Advanced Scenario: Device Timeline' from instructions.md using lookup_scenarios\n"
```

**Impact**: Agent was told to use a tool that **doesn't exist anymore** (we removed `lookup_scenarios`)

**Fix**: Updated to use new Instructions MCP workflow:
```python
"1. Call search_scenarios('device timeline') to find the scenario\n"
"2. Call get_scenario('device-timeline') to get all 9 steps\n"
"3. For EACH of the 9 steps in order:\n"
"   a. Call substitute_and_get_query with the query_id and required placeholder values\n"
"   b. Execute the returned query EXACTLY using execute_query\n"
```

### 2. **Agent Instructions Referenced Removed Tools** (Lines 708, 751)
**Problem**: Agent system instructions still contained:
- Line 708: "lookup_context: Still useful for checking stored context"
- Line 751: "ALWAYS use lookup_scenarios first"

**Impact**: Agent was being instructed to use tools that no longer exist, causing confusion

**Fix**: 
- Removed references to `lookup_scenarios` and `lookup_context`
- Marked both as DEPRECATED with clear instructions not to use them
- Added "lookup_context: DEPRECATED - Context is automatically handled"

### 3. **No Completion Criteria** (Agent didn't know when to STOP)
**Problem**: Agent instructions had no clear guidance on when execution is complete. After executing queries, it would think "Should I search for scenarios again?" and loop back.

**Impact**: Agent never finished - kept searching and re-executing in an endless cycle

**Fix**: Added explicit **COMPLETION CRITERIA** section:
```python
COMPLETION CRITERIA (WHEN TO STOP):
- After executing ALL steps in a scenario, return the results immediately
- Do NOT search for scenarios again after starting execution
- Do NOT validate placeholders multiple times for the same query
- Once you have executed all required queries, format results and return
- If user asks for a scenario with N steps, execute exactly N queries then stop
```

Also updated STRICT BEHAVIOR RULES:
```python
- Once all scenario queries are executed, return results immediately - do NOT loop back to search_scenarios
```

### 4. **Wrong Parameter Name in Example Code** (Line 734)
**Problem**: Example code showed:
```python
substitute_and_get_query(
    query_id=step.query_id,
    values=dict with DeviceId, ...  # WRONG PARAMETER NAME
)
```

**Impact**: LLM tried calling with BOTH `values` and `placeholder_values`, causing duplicate tool calls

**Fix**: Updated example to use correct parameter name:
```python
substitute_and_get_query(
    query_id="device-timeline_step1",
    placeholder_values={"DeviceId": "abc-123", ...}  # CORRECT
)
```

### 5. **Unclear Workflow Steps**
**Problem**: Original example was pseudo-code ("values=dict with...") without clear step-by-step execution flow

**Impact**: Agent wasn't clear about the sequential nature - execute ALL steps before returning

**Fix**: Added detailed 7-step workflow:
```
Step 1: Search for scenarios
Step 2: Get scenario details
Step 3: For EACH step, substitute placeholders and execute
Step 4: Execute the returned query EXACTLY
Step 5: Extract values from results for next step (if needed)
Step 6: Repeat steps 3-5 for ALL remaining queries in the scenario
Step 7: Return results after ALL queries are executed
```

## Why Manager Wasn't Appearing

The **Manager** in Magentic framework is only active when there are **multiple agents** and routing decisions are needed. In our setup:

```python
self.magentic_workflow = (
    MagenticBuilder()
    .participants(IntuneExpert=self.intune_expert_agent)  # ONLY ONE AGENT
    .with_standard_manager(...)
    .build()
)
```

With only **one participant**, the orchestrator doesn't need a "Manager" to decide routing - it just invokes the single agent directly. The logs show:
- "Magentic Orchestrator: Inner loop" - the orchestrator coordinating execution
- "Agent IntuneExpert: Received request to respond" - the agent being invoked directly

This is **expected behavior** for single-agent workflows. The orchestrator acts as a simple coordinator, not a planning manager.

## Expected Behavior After Fixes

### Before (Looping):
```
Superstep 1: search_scenarios → get_scenario
Superstep 3: substitute_and_get_query (step1) → execute_query (step1)
            → substitute_and_get_query (step2) → validate_placeholders
            → STOPS without executing step2
Superstep 5: search_scenarios → get_scenario → LOOPS BACK
Superstep 7: search_scenarios → get_scenario → LOOPS BACK AGAIN
Superstep 10: STALL DETECTED → reset/replan
```

### After (Linear Execution):
```
Superstep 1: search_scenarios("device timeline")
Superstep 3: get_scenario("device-timeline")
Superstep 5: substitute_and_get_query(step1) → execute_query
Superstep 7: substitute_and_get_query(step2) → execute_query
Superstep 9: substitute_and_get_query(step3) → execute_query
... (continue for all 9 steps)
Superstep 27: Return final results → DONE
```

## Testing Checklist

- [ ] Device Timeline executes all 9 queries without looping
- [ ] Agent does NOT call search_scenarios more than once
- [ ] Agent does NOT call validate_placeholders multiple times for same query
- [ ] Agent does NOT call substitute_and_get_query with wrong parameter names
- [ ] Agent returns results after completing all queries
- [ ] No "Stalling detected" messages in logs
- [ ] Execution completes in ~20-30 supersteps (not 10 with stall)

## Files Modified
1. `backend/services/agent_framework_service.py`:
   - Line ~1089: Updated device_timeline query type instructions
   - Line ~708: Deprecated lookup_context reference
   - Line ~705-722: Added COMPLETION CRITERIA section
   - Line ~758: Updated STRICT BEHAVIOR RULES with completion instruction
   - Line ~723-750: Updated SCENARIO EXECUTION PATTERN with correct parameters and 7-step workflow

## Related Documentation
- `docs/LEGACY_TOOL_REMOVAL.md` - Context about why legacy tools were removed
- `docs/INSTRUCTIONS_MCP_COMPLETE.md` - Instructions MCP implementation details
- `docs/INSTRUCTIONS_MCP_REFERENCE.md` - Tool reference guide

## Date
October 14, 2025
