# Orchestrator Looping Fix

## Problem Description

The Magentic orchestrator was entering an infinite loop when executing multi-step scenarios (like `device-timeline` with 8 steps). The agent would:

1. Execute steps 1-3 correctly (search_scenarios → get_scenario → find_device → execute step 2 → execute step 3)
2. Stop after step 3 without calling `execute_query` for step 4
3. Orchestrator detects incomplete execution and sends new instruction
4. Agent restarts from `search_scenarios` instead of continuing from step 4
5. Loop repeats indefinitely

## Root Cause Analysis

### Symptom Timeline (from app.log)

```
Superstep 1: Agent executes:
  - search_scenarios("device-timeline") ✓
  - get_scenario("device-timeline") ✓  
  - find_device_by_id(...) ✓
  - substitute_and_get_query(step2) → execute_query ✓
  - substitute_and_get_query(step3) → execute_query ✓
  - substitute_and_get_query(step4) ✓
  - Agent says: "I will now execute the Kusto query exactly as returned for step 4"
  - BUT NEVER CALLS execute_query for step 4 ❌

Superstep 3: Orchestrator issues new instruction:
  - "Please execute the device_timeline scenario exactly as specified, end-to-end, without restarting"
  - Agent RESTARTS from search_scenarios ❌

Superstep 5: Same pattern repeats
Superstep 7: Same pattern repeats
... infinite loop
```

### Root Cause

The original user prompt was **too generic**:

```python
Steps:
1. search_scenarios(query="device-timeline")
2. get_scenario(slug) from the results
3. Execute each step sequentially
4. Return formatted results

Do not restart or loop.
```

**Problem**: The orchestrator interpreted "Steps 1-4" as the complete task definition. When the agent executed steps 1-3 (search → get → execute *some* steps), the orchestrator thought the task was partially complete and needed to be re-executed from the beginning.

The vague "Execute each step sequentially" in step 3 didn't convey that:
- The scenario has 8 internal steps (not 4)
- ALL 8 steps must be executed in one continuous sequence
- `search_scenarios` and `get_scenario` are DISCOVERY steps (run once)
- Steps 2-8 are EXECUTION steps (run sequentially after discovery)

## Solution Implemented

### Updated User Prompt (Lines 1418-1437 in agent_framework_service.py)

```python
base_query_message = f"""Execute the COMPLETE '{query_type}' scenario with these parameters:
{placeholder_str}

CRITICAL WORKFLOW (Execute Once, Do NOT Restart):
1. Call search_scenarios(query="{normalized_query_type}") ONCE at the beginning
2. Call get_scenario(slug) ONCE to get scenario details
3. Execute ALL scenario steps sequentially (step 1, 2, 3, 4, 5, etc. until complete)
   - For each step: call substitute_and_get_query(query_id) then execute_query
   - Continue through ALL steps without stopping
4. After executing the FINAL step, provide formatted results

EXECUTION RULES:
- search_scenarios is ONLY called ONCE at the start - never call it again
- get_scenario is ONLY called ONCE after search_scenarios - never call it again
- Execute ALL scenario steps in one continuous sequence
- Do NOT restart, loop back, or re-discover the scenario
- Do NOT stop after step 3 or 4 - continue until ALL steps are complete
- The scenario is complete when you've executed every step returned by get_scenario"""
```

### Key Improvements

1. **Explicit ONCE constraint**: Makes it crystal clear that discovery tools are one-time operations
2. **Step 3 expansion**: Changed from vague "Execute each step sequentially" to detailed execution pattern with sub-steps
3. **Completion criteria**: "The scenario is complete when you've executed every step returned by get_scenario"
4. **Negative instructions**: Added explicit "Do NOT" rules to prevent common failure modes
5. **Continuous sequence emphasis**: "Execute ALL scenario steps in one continuous sequence"

## Expected Behavior After Fix

```
Superstep 1: Agent executes:
  - search_scenarios("device-timeline") ✓ (ONCE)
  - get_scenario("device-timeline") ✓ (ONCE)
  - find_device_by_id(...) ✓
  - substitute_and_get_query(step2) → execute_query ✓
  - substitute_and_get_query(step3) → execute_query ✓
  - substitute_and_get_query(step4) → execute_query ✓
  - substitute_and_get_query(step5) → execute_query ✓
  - substitute_and_get_query(step6) → execute_query ✓
  - substitute_and_get_query(step7) → execute_query ✓
  - substitute_and_get_query(step8) → execute_query ✓
  - Return formatted results ✓

Workflow complete (no loop, no restart)
```

## Related Configuration

### Orchestrator Limits (Lines 1238-1240)

```python
.with_standard_manager(
    chat_client=self.chat_client,
    max_round_count=30,  # Sufficient for 8-step scenarios
    max_stall_count=3,   # Fail faster if stuck
)
```

- `max_round_count=30`: Allows ~3-4 rounds per scenario step (adequate with fixed prompt)
- `max_stall_count=3`: Prevents infinite loops if agent gets stuck

## Testing

To validate the fix:

1. Run a device-timeline query:
   ```bash
   # From frontend or API
   POST /api/diagnostics/run-query
   {
     "query_type": "device_timeline",
     "device_id": "a50be5c2-d482-40ab-af57-18bace67b0ec",
     "start_time": "2025-10-22 02:01:00",
     "end_time": "2025-10-29 02:01:00"
   }
   ```

2. Monitor app.log for expected pattern:
   - `search_scenarios` called ONCE (should appear 1 time in log)
   - `get_scenario` called ONCE (should appear 1 time in log)  
   - `execute_query` called 8 times consecutively (steps 1-8)
   - No "Starting superstep 3" message (workflow completes in supersteps 1-2)

3. Verify completion:
   - Check that all 8 Kusto queries execute successfully
   - Response contains formatted timeline results
   - No "Magentic Orchestrator: Inner loop - round 3" messages

## Files Modified

1. **backend/services/agent_framework_service.py** (Line 1418-1437)
   - Updated `base_query_message` with explicit workflow and execution rules
   - Changed from generic 4-step instructions to detailed multi-step execution guidance
   - Added negative constraints to prevent restart/loop behavior

## Rollback Plan

If this fix causes issues, revert to original prompt:

```python
base_query_message = f"""Execute the '{query_type}' scenario with these parameters:
{placeholder_str}

Steps:
1. search_scenarios(query="{normalized_query_type}")
2. get_scenario(slug) from the results
3. Execute each step sequentially
4. Return formatted results

Do not restart or loop."""
```

However, this will restore the looping behavior.

## Additional Notes

- The orchestrator behavior is controlled by `autogen-magentic-one` library (PyPI package)
- Orchestrator uses `gpt-5-272k-00` model for decision-making
- The model receives full conversation history including user prompt, agent responses, and tool results
- More explicit prompts reduce ambiguity in multi-agent orchestration scenarios
- This pattern applies to other complex multi-step scenarios (not just device-timeline)

## Related Documentation

- `docs/AGENT_FRAMEWORK_QUICK_REFERENCE.md` - Agent framework architecture
- `docs/MAGENTIC_IMPLEMENTATION.md` - Magentic orchestration setup
- `docs/AGENT_LOOPING_FIX.md` - Previous loop prevention work (different issue)
- `instructions.md` - Scenario definitions and execution patterns
