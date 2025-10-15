# Agent Looping Issue - Root Cause Analysis v2

## Date
October 14, 2025

## Problem
Agent continues to loop endlessly despite all previous fixes:
- Calls `search_scenarios` and `get_scenario` multiple times
- Executes some queries, then starts over
- Orchestrator detects "stalling" and resets/replans
- Cycle repeats indefinitely

## Log Analysis

### Superstep 15-17 (After Reset):
```
[] search_scenarios('device timeline')  ← Called again after reset
[] get_scenario('device-timeline')      ← Called again
[] substitute_and_get_query(step1)
```

### Superstep 19 (Parallel Execution):
```
[] get_scenario('device-timeline')       ← Called AGAIN
[] substitute_and_get_query(step1)       ← Query 3 steps in parallel
[] substitute_and_get_query(step2)
[] substitute_and_get_query(step3)
[] execute_query(...)                    ← Execute 2 queries
[] [Agent goes silent - no response]
```

### Superstep 21-23 (Yet Another Loop):
```
[] get_scenario (with kwargs={'slug': ...})  ← Wrong parameter format
[] get_scenario('device-timeline')            ← Called AGAIN
[] substitute_and_get_query(step1)
[] execute_query(...)
[] substitute_and_get_query(step2)
[] [Agent goes silent again]
```

### Superstep 24:
```
[] Orchestrator: Stalling detected. Resetting and replanning
```

## Root Cause

### Issue 1: Agent Never Signals Completion
The agent executes queries but **never returns a final response**. After `execute_query` succeeds, the agent doesn't respond with formatted results. The orchestrator interprets this silence as "stalling" because:
- No visible progress toward task completion
- No response message generated
- Agent appears stuck/deadlocked

### Issue 2: Orchestrator Configuration Too Strict
```python
max_stall_count=3   # Too low - triggers reset too early
max_round_count=20  # Too low for 9-step scenario
```

After 3 consecutive rounds with no progress, orchestrator resets. For a 9-step scenario:
- Each step needs ~2-3 rounds (substitute → execute → process)
- Total rounds needed: ~20-30
- But stalls trigger reset before completion

### Issue 3: No Explicit Completion Signal
The Magentic framework expects agents to either:
1. Return a final message/response to the user
2. Signal task completion explicitly
3. Make visible progress each round

Our agent does none of these - it just executes tools and waits.

## Why This Happens

**The Pattern**:
1. Agent calls `search_scenarios` and `get_scenario`
2. Agent calls `substitute_and_get_query` for 1-3 steps
3. Agent calls `execute_query` and gets results
4. **Agent goes silent** (doesn't generate response)
5. Orchestrator waits for agent response
6. No response after N rounds → detected as "stall"
7. Orchestrator resets and replans
8. GOTO step 1 (infinite loop)

**The Missing Piece**:
After executing queries, the agent should:
```
execute_query(...) → SUCCESS
[Agent should now]: "Here are the results: [tables] [summary]"
[Orchestrator sees]: Agent completed task → DONE
```

But instead:
```
execute_query(...) → SUCCESS
[Agent does]: [silence]
[Orchestrator sees]: Agent stalled → RESET
```

## Solutions Applied

### Fix 1: Explicit Completion Instructions
Added to agent system instructions:
```python
CRITICAL: HOW TO COMPLETE YOUR TASK
After executing all required queries:
1. Format the results as markdown tables
2. Provide a summary of findings  
3. Return your response to the user
4. **STOP** - do NOT call search_scenarios or get_scenario again
5. Do NOT execute additional tool calls after returning results

The workflow should be: search → get_scenario → execute queries → RETURN RESULTS → DONE
Do NOT loop back to search after executing queries.
```

Also added:
```python
IMPORTANT: After executing all queries, you MUST respond with your formatted results.
Do NOT wait for further instructions. Do NOT call search_scenarios again.
Your response with tables and summary IS the completion signal.
```

### Fix 2: Increased Orchestrator Limits
```python
max_round_count=50,  # Increased from 20 to allow all 9 queries
max_stall_count=5,   # Increased from 3 to avoid premature reset
```

This gives the agent more room to complete the task before being reset.

### Fix 3: Emphasized Response Requirement
```python
RESPONSE FORMAT:
- Return tables first (raw results as markdown)
- Include key identifier columns
- Provide concise summaries
- For multiple datasets, show multiple labeled tables
- After returning results, you are DONE - do not continue
```

## Expected Behavior After Fixes

### Before (Looping):
```
Superstep 1-3: search → get_scenario
Superstep 5-7: execute step1 → [silence]
Superstep 9: [STALL DETECTED] → reset/replan
Superstep 11-15: search → get_scenario → execute → [silence]
Superstep 17: [STALL DETECTED] → reset/replan
... infinite loop
```

### After (Linear with Completion):
```
Superstep 1-3: search_scenarios → get_scenario
Superstep 5-7: substitute step1 → execute step1
Superstep 9-11: substitute step2 → execute step2
Superstep 13-15: substitute step3 → execute step3
... (continue for all 9 steps)
Superstep 27-29: substitute step9 → execute step9
Superstep 31: [AGENT RESPONDS] "Here are the results: [tables] [summary]"
Superstep 33: [ORCHESTRATOR] Task complete → DONE
```

## Testing Checklist

- [ ] Agent completes all 9 Device Timeline queries
- [ ] Agent returns formatted results after executing queries
- [ ] Agent does NOT call search_scenarios more than once
- [ ] Agent does NOT call get_scenario more than twice (once to get, maybe once to double-check)
- [ ] No "Stalling detected" messages in logs
- [ ] Execution completes in ~30-40 supersteps (not indefinite)
- [ ] Final response contains tables and summary

## Files Modified
1. `backend/services/agent_framework_service.py`:
   - Line ~693-715: Added "CRITICAL: HOW TO COMPLETE YOUR TASK" section
   - Line ~717: Added "IMPORTANT: After executing..." reminder
   - Line ~730: Added "After returning results, you are DONE" reminder
   - Line ~983: Increased `max_round_count` from 20 to 50
   - Line ~984: Increased `max_stall_count` from 3 to 5

## Related Issues
- Azure content filter jailbreak detection (fixed by softening language)
- F-string formatting error (fixed by removing dictionary literals)
- Legacy tool removal (fixed by unregistering lookup_scenarios)

## Next Steps
1. Test Device Timeline scenario end-to-end
2. Monitor logs for completion behavior
3. If still looping, may need to investigate Agent Framework's completion mechanisms
4. Consider adding explicit termination condition or stop signal

## Alternative Solutions (If This Fails)
1. **Add explicit stop token**: Configure agent to return "TERMINATE" when done
2. **Use task-based orchestration**: Switch from Magentic to a simpler sequential executor
3. **Add completion callback**: Hook into execute_query to detect "all steps complete"
4. **Change orchestration pattern**: Use AutoGen style with max_consecutive_auto_reply

