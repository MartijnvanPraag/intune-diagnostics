# Quick Reference: Agent Looping Fix

## What Was Fixed

✅ **Agent executing queries but never completing (infinite loop)**

## Root Cause

The Magentic orchestrator uses a **progress ledger** (LLM-based evaluation) to determine task completion. The task lacked explicit completion criteria, so the LLM kept returning `is_request_satisfied: False` even after queries executed.

## The Key Fix

**Added explicit completion criteria to all task definitions** before passing to `workflow.run_stream(task)`:

```python
# BEFORE
task = "Device Timeline for DeviceId X"

# AFTER
task = (
    "Device Timeline for DeviceId X\n\n"
    "TASK COMPLETION CRITERIA:\n"
    "The task is COMPLETE when:\n"
    "1. All 9 queries executed\n"
    "2. Results formatted and presented to user\n"
    "3. Timeline visualization provided\n"
    "NOT complete until user-facing response given."
)
```

## Where Changes Were Made

### 1. Generic Chat Tasks (Lines 1337-1380)
- Tasks with conversation history
- Tasks without conversation history
- Both now include completion criteria

### 2. Device Timeline Specific (Lines 1055-1095)
- Device Timeline task instructions
- Explicit 9-query completion criteria
- Timeline visualization requirement

### 3. Agent System Instructions (Lines 661-730)
- Already updated in previous fixes
- Tells agent to respond after queries
- Emphasizes completion signal

## How to Test

```bash
# Start the app
cd c:\dev\intune-diagnostics
uv run python backend/main.py

# Test Device Timeline
# In the UI, enter: "Device Timeline for [DeviceId]"
```

**Expected Behavior**:
1. Agent calls `search_scenarios` once
2. Agent calls `get_scenario` 1-2 times
3. Agent executes all 9 queries
4. Agent returns formatted response with timeline
5. **Orchestrator detects completion and stops** ✅
6. Total rounds: ~20-40 (not infinite)

**Log Checks**:
```
✅ "TASK COMPLETION CRITERIA" appears in first log
✅ "Progress evaluation: satisfied=True" after agent responds
✅ "Task completed" message
✅ NO "Stalling detected. Resetting and replanning"
```

## Why This Works

**Magentic's Progress Ledger Evaluation** (every round):
- Reads: Original task (including completion criteria)
- Reads: Conversation history (all agent messages)
- Asks: "Is the request fully satisfied?"
- Before fix: Task vague → LLM unsure → returns False
- After fix: Task explicit → LLM sees response given → returns True ✅

## Quick Verification

```bash
# Check code compiles
cd c:\dev\intune-diagnostics\backend
uv run python -c "from services.agent_framework_service import AgentFrameworkService; print('✓ OK')"
# Expected: ✓ OK

# Check completion criteria in code
grep -n "TASK COMPLETION CRITERIA" services/agent_framework_service.py
# Expected: 3 matches (lines ~1070, ~1342, ~1359)
```

## Documentation

- **Full Analysis**: `docs/MAGENTIC_TASK_COMPLETION_FIX.md`
- **Complete Summary**: `docs/AGENT_LOOPING_FIX_SUMMARY.md`
- **This Quick Ref**: `docs/AGENT_LOOPING_QUICK_REF.md`

## Status

✅ All fixes applied  
✅ Code compiles  
⏳ Awaiting end-to-end test
