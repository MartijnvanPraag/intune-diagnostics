# Magentic Task Completion Fix

**Date**: 2025-10-14  
**Issue**: Agent executes queries successfully but orchestrator detects "stalling" and resets, causing infinite loop  
**Root Cause**: Task lacks explicit completion criteria for orchestrator's progress ledger evaluation  

---

## Problem Analysis

### What Was Happening

1. **User requests**: "Device Timeline for DeviceId X"
2. **Agent executes**: All queries successfully (steps 1-9)
3. **Agent behavior**: Executes tools, receives results, but doesn't generate user-facing response
4. **Orchestrator checks progress ledger**: "Is the request fully satisfied?"
5. **LLM evaluates**: 
   - ✅ Queries executed
   - ❌ No formatted response to user
   - **Result**: `is_request_satisfied: False`
6. **Orchestrator continues**: Sends more instructions to agent
7. **After N rounds with no change**: `is_progress_being_made: False` → stall count increases
8. **After max_stall_count reached**: Reset and replan → **infinite loop**

### Why This Happens

According to the Magentic source code (`_magentic.py` lines 1540-1548):

```python
# Check for task completion
if current_progress_ledger.is_request_satisfied.answer:
    logger.info("Magentic Orchestrator: Task completed")
    await self._prepare_final_answer(context)
    return
```

**Every round**, the orchestrator calls `create_progress_ledger()` which uses this prompt:

```python
ORCHESTRATOR_PROGRESS_LEDGER_PROMPT = """
...
- Is the request fully satisfied? (True if complete, or False if the 
  original request has yet to be SUCCESSFULLY and FULLY addressed)
...
"""
```

The LLM evaluating the progress ledger considers the task **incomplete** because:
- The original task was: "Device Timeline for DeviceId X"
- The agent executed queries but **didn't return a formatted response**
- The LLM thinks: "Tool execution happened, but no user-facing answer was provided"
- Therefore: `is_request_satisfied: False`

### The Missing Piece

The **task definition** must include **explicit completion criteria** that the orchestrator can check. Without this:

- ❌ Task: "Device Timeline for DeviceId X" → Ambiguous when it's complete
- ✅ Task: "Device Timeline for DeviceId X. COMPLETE when queries executed AND results presented to user"

---

## Solution

### Fix 1: Add Explicit Completion Criteria to Task

Modified `agent_framework_service.py` lines 1350-1380 to inject completion criteria into the task:

**Before**:
```python
composite_task = message
```

**After**:
```python
composite_task = (
    f"{message}\n\n"
    "TASK COMPLETION CRITERIA:\n"
    "The task is COMPLETE when:\n"
    "1. All necessary information has been gathered (queries executed if needed)\n"
    "2. Results have been formatted and presented to the user\n"
    "3. A clear response addressing the user's request has been provided\n"
    "The task is NOT complete until a user-facing response is given."
)
```

This ensures the orchestrator's progress ledger evaluates completion correctly:
- ✅ LLM sees explicit criteria: "Must present results to user"
- ✅ After agent returns formatted response: `is_request_satisfied: True`
- ✅ Orchestrator calls `prepare_final_answer()` and completes

### Fix 2: Agent Instructions Already Updated

Previously added (lines 693-710) explicit completion instructions to agent:

```python
"CRITICAL: HOW TO COMPLETE YOUR TASK:\n"
"After executing all required queries, you MUST:\n"
"1. Format the results into clear, readable tables\n"
"2. Provide a summary of findings\n"
"3. Return your response to the user\n"
"4. **STOP** - do not continue or call more tools\n"
...
"Your response with tables and summary IS the completion signal."
```

### Fix 3: Orchestrator Limits Already Increased

Previously increased (lines 983-984):
- `max_round_count`: 20 → 50 (allow more rounds for complex scenarios)
- `max_stall_count`: 3 → 5 (avoid premature reset)

---

## How The Fix Works

### Before Fix (Infinite Loop)

```
Round 1-5: Agent executes queries
Round 6: Progress ledger: is_request_satisfied=False (no user response)
Round 7-9: Agent continues executing more queries
Round 10: Progress ledger: is_progress_being_made=False (repeating)
Round 11: Stall count = 4, orchestrator RESETS
Round 12-15: Agent starts over (search_scenarios again)
... INFINITE LOOP ...
```

### After Fix (Completes Successfully)

```
Task includes: "COMPLETE when results presented to user"

Round 1-5: Agent executes queries
Round 6: Agent formats results, returns response to user
Round 7: Progress ledger evaluates:
  - Task: "COMPLETE when results presented to user"
  - Agent provided formatted response ✅
  - is_request_satisfied=True
Round 8: Orchestrator calls prepare_final_answer()
DONE ✅
```

---

## Key Insights from Magentic Source Code

### 1. Progress Ledger is The Completion Signal

From `_magentic.py` line 1540:
```python
if current_progress_ledger.is_request_satisfied.answer:
    logger.info("Magentic Orchestrator: Task completed")
    await self._prepare_final_answer(context)
    return
```

**Not** agent returning a token, **not** a callback, **the progress ledger evaluation**.

### 2. Progress Ledger Prompt Structure

The orchestrator asks the LLM to evaluate:
```python
- Is the request fully satisfied? (True if complete, or False if the 
  original request has yet to be SUCCESSFULLY and FULLY addressed)
```

The LLM uses:
- **The original task** (what we pass to `run_stream()`)
- **The conversation history** (all agent messages and tool calls)
- **The team composition** (agent descriptions)

To determine: "Is this task done?"

### 3. Task Phrasing Matters

❌ **Vague task**: "Device Timeline for DeviceId X"
- LLM thinks: "Is executing queries enough? Or must results be returned?"
- **Ambiguous** → likely returns False even after queries execute

✅ **Explicit task**: "Device Timeline for DeviceId X. Task COMPLETE when queries executed AND results presented to user"
- LLM thinks: "Did agent present results to user? Yes → True"
- **Clear criteria** → returns True when appropriate

---

## Testing Checklist

After applying this fix, test:

1. **Device Timeline End-to-End**:
   - Run: "Device Timeline for [DeviceId]"
   - Expected: Agent executes all 9 queries sequentially
   - Expected: Agent returns formatted tables and timeline summary
   - Expected: Orchestrator detects completion and stops (no reset)
   - Expected: Total rounds: ~20-30 (not infinite)

2. **Check Logs For**:
   - ✅ "Progress evaluation: satisfied=True" after agent returns response
   - ✅ "Task completed" log message
   - ✅ No "Stalling detected. Resetting and replanning" messages
   - ✅ `search_scenarios` called only once at start
   - ✅ `get_scenario` called 1-2 times (not 4+ times)

3. **Verify Task Includes Completion Criteria**:
   - Check first log message: "[Magentic] Running workflow with message: ..."
   - Should contain: "TASK COMPLETION CRITERIA"
   - Should contain: "The task is NOT complete until a user-facing response is given"

---

## Alternative Solutions (If This Fails)

If the explicit completion criteria in the task don't work:

### Option A: Custom Progress Ledger Prompt

Override the orchestrator's progress ledger prompt to be more explicit:

```python
custom_progress_prompt = """
...
- Is the request fully satisfied? (True ONLY if the agent has:
  1. Executed all required queries AND
  2. Returned formatted results to the user AND
  3. Provided a summary or analysis
  False if any of the above are missing)
...
"""

.with_standard_manager(
    chat_client=self.chat_client,
    progress_ledger_prompt=custom_progress_prompt,
    ...
)
```

### Option B: Custom Manager with Completion Detection

Extend `StandardMagenticManager` to override `create_progress_ledger()`:

```python
class IntuneExpertManager(StandardMagenticManager):
    async def create_progress_ledger(self, context: MagenticContext) -> MagenticProgressLedger:
        # Custom logic to detect completion
        # E.g., check if last message from agent contains tables
        last_msg = context.chat_history[-1] if context.chat_history else None
        if last_msg and "```table" in last_msg.text:
            # Agent returned formatted results → task complete
            return MagenticProgressLedger(
                is_request_satisfied=MagenticProgressLedgerItem(
                    reason="Agent returned formatted results",
                    answer=True
                ),
                ...
            )
        return await super().create_progress_ledger(context)
```

### Option C: Different Orchestration Pattern

Switch from Magentic to simpler sequential orchestration:

```python
# Instead of: await workflow.run_stream(task)
# Use: Direct agent invocation with manual completion check
response = await agent.run(task)
if self._has_completed(response):
    return response
```

---

## Files Modified

1. **backend/services/agent_framework_service.py**:
   - Lines 1337-1365: Added completion criteria to task with history
   - Lines 1350-1380: Added completion criteria to task without history
   - Lines 1055-1095: Added completion criteria to Device Timeline specific task

---

## Summary

**Root Cause**: Task lacked explicit completion criteria, causing orchestrator's progress ledger to continuously return `is_request_satisfied: False` even after queries executed.

**Fix**: Inject explicit completion criteria into the task definition before passing to `run_stream()`. This guides the orchestrator's LLM-based progress evaluation to correctly detect when the task is complete.

**Expected Result**: Agent executes queries → formats results → returns response → orchestrator detects completion via progress ledger → workflow completes successfully (no infinite loop).

**Key Insight**: In Magentic orchestration, **the task definition is critical** because it's used by the progress ledger LLM to evaluate `is_request_satisfied`. Vague tasks lead to ambiguous completion detection.
