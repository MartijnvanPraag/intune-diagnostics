# Agent Looping Fix - Version 2 (Generic for All Scenarios)

## Problem
The agent was stuck in an infinite loop even after successfully executing queries:
1. Agent would call `search_scenarios` and `get_scenario` correctly
2. Execute some queries successfully  
3. Then the **orchestrator would detect "stalling"** and reset
4. Agent would start over from step 1 (search_scenarios again)
5. This loop continued indefinitely

## Root Cause
The agent instructions were:
1. **Too verbose and repetitive** - Multiple sections saying similar things caused confusion
2. **Scenario-specific** - Device Timeline had 80+ lines of specific instructions that didn't apply to other scenarios
3. **Missing clear completion signal** - Agent didn't know exactly when to STOP making tool calls
4. **No explicit "return results and STOP" instruction** - Orchestrator couldn't detect completion

## Solution Applied

### 1. Simplified System Instructions
**Before**: ~200 lines of verbose, repetitive instructions
**After**: ~50 lines of concise, clear workflow

Key changes:
- **Three-phase workflow** (Discovery → Execution → Completion)
- Each phase is **numbered and explicit**
- **CRITICAL RULES** section at the end
- Clear **COMPLETION DETECTION** guidance

```python
WORKFLOW - HOW TO EXECUTE SCENARIOS (FOLLOW THIS ORDER STRICTLY):

**PHASE 1: SCENARIO DISCOVERY (DO ONCE)**
1. Call search_scenarios ONCE with user's keywords
2. Call get_scenario ONCE with the slug

**PHASE 2: QUERY EXECUTION (DO FOR ALL STEPS)**
3. For EACH step: substitute_and_get_query + execute_query

**PHASE 3: COMPLETION (REQUIRED)**
4. Format results, return to user, STOP CALLING TOOLS

CRITICAL RULES:
- search_scenarios: Call EXACTLY ONCE
- get_scenario: Call EXACTLY ONCE  
- After returning results: STOP (no more tool calls)
- Do NOT loop back to Phase 1 after Phase 3
```

### 2. Removed Scenario-Specific Instructions
**Before**: Device Timeline had 80+ lines of batch-specific execution instructions
**After**: Generic instructions work for ALL scenarios

Key changes:
- **No hardcoded batch strategies** (agent figures out dependencies from metadata)
- **No scenario-specific completion criteria**
- **Single generic query_message** used for all scenarios
- Parallel execution mentioned as an **optimization option**, not a requirement

```python
# OLD (device_timeline specific):
if query_type == "device_timeline":
    timeline_instructions = (
        "BATCH 1: Step 1...\n"
        "BATCH 2: Steps 2,3,6,7 IN PARALLEL...\n"
        # 80+ lines of device_timeline specific logic
    )
    query_message = f"{timeline_instructions}\n..."
else:
    query_message = f"Please execute a {query_type}..."

# NEW (generic for ALL scenarios):
query_message = (
    f"Execute the '{query_type}' scenario with parameters: {parameters}\n\n"
    f"WORKFLOW (follow EXACTLY):\n"
    f"1. search_scenarios ONCE\n"
    f"2. get_scenario ONCE\n"
    f"3. Execute ALL steps\n"
    f"4. Return results and STOP\n"
)
```

### 3. Added Explicit Completion Signal
**Before**: Orchestrator didn't know when agent was done
**After**: Clear completion criteria in multiple places

Added to system instructions:
```python
COMPLETION DETECTION:
When you have executed all scenario steps and formatted the results:
1. Return the formatted tables and summary to the user
2. DO NOT make any more tool calls
3. DO NOT call search_scenarios or get_scenario again
4. The orchestrator will detect completion when you return text without tool calls

If the orchestrator asks you to continue after you've returned results, respond with:
"Scenario execution completed. All queries have been executed and results returned."
```

Added to query message:
```python
COMPLETION CRITERIA:
You are DONE when:
- All scenario steps have been executed (or attempted)
- Results have been formatted and returned to user
- You have provided a final text response (not just tool calls)
After returning your final formatted response, make NO MORE TOOL CALLS.
```

## Testing
Test with ALL scenarios in `instructions.md`:
- [x] `device-details` - Simple 1-step scenario
- [ ] `user-id-lookup` - 1-step scenario
- [ ] `tenant-information` - 1-step scenario
- [ ] `device-compliance-status` - 1-step scenario  
- [ ] `policy-setting-status` - Multi-query scenario
- [ ] `effective-groups` - Multi-step with dependencies
- [ ] `mam-policy` - 1-step scenario
- [ ] `applications` - Multi-query scenario
- [ ] `third-party-integration` - 1-step scenario
- [ ] `dcv1-dcv2-conflicts` - Complex single query
- [ ] `autopilot-summary` - Multi-step workflow
- [ ] `device-timeline` - Most complex (8 steps with dependencies)

## Expected Behavior
For any scenario (e.g., device_timeline):

1. **Discovery Phase** (2 tool calls):
   - Call `search_scenarios("device timeline")` → Get slug
   - Call `get_scenario("device-timeline")` → Get 8 steps

2. **Execution Phase** (N tool calls for N steps):
   - Step 1: `substitute_and_get_query` + `execute_query`
   - Steps 2,3,6,7: (in parallel) `substitute_and_get_query` + `execute_query` 
   - Step 4: `substitute_and_get_query` + `execute_query`
   - Step 5: `substitute_and_get_query` + `execute_query`
   - Step 8: `substitute_and_get_query` + `execute_query` (if applicable)

3. **Completion Phase** (1 text response, 0 tool calls):
   - Agent formats results as markdown tables
   - Agent provides summary
   - Agent returns final response **without any tool calls**
   - Orchestrator detects completion (no pending tool calls)
   - Workflow ends successfully

4. **NO LOOP BACK**:
   - Agent does NOT call `search_scenarios` again
   - Agent does NOT call `get_scenario` again
   - Agent does NOT make any additional tool calls
   - If orchestrator prompts for more, agent responds "Scenario execution completed"

## Key Differences from V1

| Aspect | V1 (Looping Fix) | V2 (This Fix) |
|--------|------------------|---------------|
| **Instructions Length** | ~200 lines | ~50 lines |
| **Scenario Handling** | Device Timeline specific | Generic for ALL |
| **Completion Signal** | Implicit | Explicit multiple places |
| **Batch Instructions** | Hardcoded 5 batches | Agent determines from metadata |
| **Query Message** | Different per scenario | Same for ALL scenarios |
| **Workflow Phases** | Numbered steps | Named phases (Discovery/Execution/Completion) |
| **Stalling Prevention** | Not addressed | Explicit "STOP" instructions |

## Files Changed
- `backend/services/agent_framework_service.py`
  - Lines ~668-720: System instructions (simplified from ~200 to ~50 lines)
  - Lines ~1040-1070: Query message (removed device_timeline specific code)

## Success Criteria
✅ Agent executes scenarios without looping
✅ Works for simple scenarios (1 step)
✅ Works for complex scenarios (8+ steps)  
✅ Works for scenarios with dependencies
✅ Agent stops after returning results
✅ Orchestrator detects completion correctly
✅ No "stalling detected" resets occur

## Next Steps
1. Test Device Timeline end-to-end
2. Test other scenarios (compliance, policy, apps, etc.)
3. Monitor for any new looping behavior
4. If successful, close the looping issue permanently
