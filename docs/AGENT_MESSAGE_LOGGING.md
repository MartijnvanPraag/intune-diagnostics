# Agent Message Logging Enhancement

**Date:** October 14, 2025  
**Purpose:** Enable detailed logging of agent-to-agent communication to diagnose workflow issues  
**Status:** ✅ Implemented

---

## Problem

The device timeline scenario was stalling and resetting without clear indication of what the agents were communicating. The logs showed:

```
[INFO] agent_framework._workflows._magentic: Magentic Orchestrator: Inner loop - round 6
[INFO] agent_framework._workflows._magentic: Magentic Orchestrator: Stalling detected. Resetting and replanning
```

But we couldn't see:
- What instructions the orchestrator was giving to the IntuneExpert agent
- What responses the agent was providing
- Why the orchestrator determined progress had stalled
- What content was being exchanged in each superstep

---

## Solution

Enhanced the event logging in `agent_framework_service.py` to capture and log message content from all workflow events.

### Changes Made

**File:** `backend/services/agent_framework_service.py`

Added detailed message logging in two locations:

1. **query_diagnostics method** (line ~1017)
2. **multi_query_diagnostics method** (line ~1262)

### What's Logged Now

For each workflow event that contains a message:

```python
# Log message content for debugging the conversation
if hasattr(event, 'message'):
    msg = getattr(event, 'message', None)
    if msg:
        # Log sender if available
        sender = getattr(msg, 'sender', 'unknown')
        role = getattr(msg, 'role', 'unknown')
        
        # Extract text content
        msg_text = ""
        if hasattr(msg, 'text') and getattr(msg, 'text'):
            msg_text = getattr(msg, 'text')
        elif hasattr(msg, 'contents') and getattr(msg, 'contents'):
            contents = getattr(msg, 'contents')
            text_parts = []
            for c in contents:
                if hasattr(c, 'text') and getattr(c, 'text'):
                    text_parts.append(str(getattr(c, 'text')))
                elif hasattr(c, '__class__'):
                    # Log non-text content types (like function calls/results)
                    content_type = c.__class__.__name__
                    if 'function' in content_type.lower() or 'tool' in content_type.lower():
                        logger.info(f"[Magentic] {event_type} contains {content_type}")
            msg_text = " ".join(text_parts) if text_parts else ""
        
        # Log the message with truncation for long messages
        if msg_text:
            truncated = msg_text[:500] + "..." if len(msg_text) > 500 else msg_text
            logger.info(f"[Magentic] {event_type} from {sender} ({role}): {truncated}")
        else:
            logger.info(f"[Magentic] {event_type} from {sender} ({role}): <no text content>")
```

### Log Output Format

**Before:**
```
[INFO] agent_framework._workflows._magentic: Magentic Orchestrator: Inner loop - round 3
[INFO] agent_framework._workflows._runner: Starting superstep 5
[INFO] agent_framework._workflows._magentic: Agent IntuneExpert: Received request to respond
```

**After:**
```
[INFO] agent_framework._workflows._magentic: Magentic Orchestrator: Inner loop - round 3
[INFO] services.agent_framework_service: [Magentic] Received event: WorkflowMessageEvent
[INFO] services.agent_framework_service: [Magentic] WorkflowMessageEvent from magentic_orchestrator (assistant): Based on the previous analysis, I need to...
[INFO] agent_framework._workflows._runner: Starting superstep 5
[INFO] agent_framework._workflows._magentic: Agent IntuneExpert: Received request to respond
[INFO] services.agent_framework_service: [Magentic] Received event: WorkflowMessageEvent
[INFO] services.agent_framework_service: [Magentic] WorkflowMessageEvent from IntuneExpert (assistant): I will now execute the queries from the Device Timeline scenario...
[INFO] services.agent_framework_service: [Magentic] WorkflowMessageEvent contains FunctionCallContent
```

---

## Benefits

### 1. **Visibility into Agent Decisions**
- See what instructions the orchestrator sends to agents
- Understand what tasks agents are attempting
- Track the conversation flow across supersteps

### 2. **Debugging Stalls**
- Identify when agents repeat the same actions
- See if agents are ignoring instructions
- Detect when orchestrator determines progress has stopped

### 3. **Tool Call Tracking**
- See when agents call functions (FunctionCallContent)
- Track function execution (FunctionResultContent)
- Identify missing or failed tool calls

### 4. **Performance Analysis**
- Measure how many rounds are needed for completion
- Identify inefficient conversation patterns
- Spot redundant query executions

---

## Usage

### Running Tests

```powershell
# Start the backend with detailed logging
cd C:\dev\intune-diagnostics
uv run uvicorn backend.main:app --reload --log-level info

# Test the device timeline scenario
# The logs will now show all agent messages
```

### Analyzing Logs

Look for these patterns:

**Normal Flow:**
```
[Magentic] WorkflowMessageEvent from magentic_orchestrator (assistant): IntuneExpert, please...
[Magentic] WorkflowMessageEvent from IntuneExpert (assistant): I will execute...
[Magentic] WorkflowMessageEvent contains FunctionCallContent
[Magentic] WorkflowMessageEvent contains FunctionResultContent
[Magentic] WorkflowMessageEvent from magentic_orchestrator (assistant): Good progress...
```

**Stalling Pattern:**
```
[Magentic] WorkflowMessageEvent from magentic_orchestrator (assistant): IntuneExpert, please...
[Magentic] WorkflowMessageEvent from IntuneExpert (assistant): I have completed the analysis...
[Magentic] WorkflowMessageEvent from magentic_orchestrator (assistant): IntuneExpert, please...
[Magentic] WorkflowMessageEvent from IntuneExpert (assistant): I have completed the analysis...
[Magentic] Magentic Orchestrator: Stalling detected. Resetting and replanning
```

**Missing Tool Calls:**
```
[Magentic] WorkflowMessageEvent from IntuneExpert (assistant): Based on the scenario...
# <-- No FunctionCallContent logged = agent didn't call any tools
[Magentic] WorkflowMessageEvent from magentic_orchestrator (assistant): You need to execute...
```

---

## Next Steps for Device Timeline Debugging

With this logging in place, run a device timeline query and analyze:

1. **What instructions is the orchestrator giving?**
   - Are they clear and actionable?
   - Do they match the scenario requirements?

2. **How is the IntuneExpert agent responding?**
   - Is it calling the lookup_scenarios tool?
   - Is it executing the queries from instructions.md?
   - Is it returning results or just descriptions?

3. **Why is it stalling?**
   - Is the agent not making progress?
   - Is the orchestrator not recognizing progress?
   - Are there repeated failed tool calls?

4. **What triggers the reset?**
   - How many rounds before stall detection?
   - What was the last message before reset?
   - Does the reset help or cause a loop?

---

## Related Documentation

- `docs/AGENT_FRAMEWORK_DEADLOCK_FIX.md` - Lock removal fix
- `docs/AGENT_FRAMEWORK_MIGRATION.md` - Original migration guide
- `docs/TROUBLESHOOTING.md` - General troubleshooting
- `backend/services/agent_framework_service.py` - Implementation

---

## Configuration

No configuration changes needed. The logging is automatically enabled at `INFO` level.

To adjust verbosity:

```python
# In backend/main.py or logging configuration
logging.getLogger("services.agent_framework_service").setLevel(logging.INFO)  # Current (verbose)
logging.getLogger("services.agent_framework_service").setLevel(logging.WARNING)  # Quiet
logging.getLogger("services.agent_framework_service").setLevel(logging.DEBUG)  # Very verbose
```

---

**Status:** ✅ Ready for testing - Run a device timeline query to see the detailed agent conversation logs
