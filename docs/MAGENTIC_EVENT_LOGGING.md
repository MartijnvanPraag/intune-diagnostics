# Magentic Event Logging Implementation

## Overview

This document describes the implementation of Magentic Team message logging in the Intune Diagnostics application. The logging feature provides real-time visibility into the multi-agent conversation orchestrated by the Microsoft Agent Framework's Magentic workflow.

## Implementation Details

### Event Types

The following Magentic callback event types are now logged to the console:

```python
MagenticCallbackEvent = Union[
    MagenticOrchestratorMessageEvent,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticFinalResultEvent,
]
```

### Event Type Descriptions

1. **MagenticOrchestratorMessageEvent**
   - Emitted by the orchestrator (manager)
   - Contains planning messages, task ledgers, instructions, and notices
   - Includes a `kind` field indicating the message type (e.g., "user_task", "task_ledger", "instruction", "notice")

2. **MagenticAgentDeltaEvent**
   - Streaming deltas from agent responses (real-time chunks)
   - Only emitted when using `MagenticCallbackMode.STREAMING`
   - Contains partial text, function calls, and function results
   - Useful for real-time progress monitoring

3. **MagenticAgentMessageEvent**
   - Complete agent message after aggregation
   - Always emitted (in both STREAMING and NON_STREAMING modes)
   - Contains the final, complete response from an agent

4. **MagenticFinalResultEvent**
   - Final workflow result
   - Emitted when the entire workflow completes
   - Contains the synthesized final answer

## Code Changes

### 1. Import Event Types

Added imports from `agent_framework._workflows._magentic`:

```python
from agent_framework._workflows._magentic import (
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticFinalResultEvent,
    MagenticOrchestratorMessageEvent,
)

# Define the Union type
MagenticCallbackEvent = Union[
    MagenticOrchestratorMessageEvent,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticFinalResultEvent,
]
```

### 2. Callback Handler Method

Added `_magentic_event_callback` method to `AgentFrameworkService` class:

```python
async def _magentic_event_callback(self, event: MagenticCallbackEvent) -> None:
    """Handle Magentic Team callback events and log them to console.
    
    This callback receives all orchestrator and agent messages during workflow execution,
    providing visibility into the multi-agent conversation.
    """
    try:
        if isinstance(event, MagenticOrchestratorMessageEvent):
            # Log orchestrator messages (planning, instructions, etc.)
            orchestrator_id = getattr(event, 'orchestrator_id', 'orchestrator')
            message = getattr(event, 'message', None)
            kind = getattr(event, 'kind', 'unknown')
            
            if message:
                message_text = getattr(message, 'text', '')
                truncated = message_text[:300] + "..." if len(message_text) > 300 else message_text
                logger.info(f"[Magentic-Orchestrator] [{kind}] {truncated}")
        
        elif isinstance(event, MagenticAgentDeltaEvent):
            # Log agent streaming deltas
            agent_id = getattr(event, 'agent_id', 'agent')
            text = getattr(event, 'text', '')
            role = getattr(event, 'role', None)
            
            # Log function calls if present
            fn_call_name = getattr(event, 'function_call_name', None)
            fn_result_id = getattr(event, 'function_result_id', None)
            
            if fn_call_name:
                logger.info(f"[Magentic-Agent-{agent_id}] Function call: {fn_call_name}")
            elif fn_result_id:
                logger.info(f"[Magentic-Agent-{agent_id}] Function result received")
            elif text:
                logger.info(f"[Magentic-Agent-{agent_id}] ({role}): {text[:100]}")
        
        # ... (similar handling for other event types)
    
    except Exception as callback_err:
        logger.warning(f"Magentic event callback error: {callback_err}")
```

### 3. Register Callback in MagenticBuilder

Updated `setup_agent` method to register the callback:

```python
from agent_framework._workflows._magentic import MagenticCallbackMode

self.magentic_workflow = (
    MagenticBuilder()
    .participants(IntuneExpert=self.intune_expert_agent)
    .with_standard_manager(
        chat_client=self.chat_client,
        max_round_count=50,
        max_stall_count=5,
    )
    .on_event(
        self._magentic_event_callback,
        mode=MagenticCallbackMode.NON_STREAMING  # Or STREAMING for deltas
    )
    .build()
)
```

## Callback Modes

### NON_STREAMING (Current Configuration)

- Only emits `MagenticAgentMessageEvent` (final aggregated messages)
- Does NOT emit `MagenticAgentDeltaEvent` (streaming chunks)
- Lower log volume, cleaner output
- **Recommended for production use**

### STREAMING

- Emits both `MagenticAgentDeltaEvent` (streaming chunks) AND `MagenticAgentMessageEvent` (final)
- Higher log volume with real-time progress
- Useful for debugging agent reasoning
- Change mode by updating: `mode=MagenticCallbackMode.STREAMING`

## Log Format

All Magentic events are logged with the `[Magentic-*]` prefix for easy filtering:

```
[Magentic-Orchestrator] [user_task] Execute the 'device_timeline' diagnostic scenario...
[Magentic-Orchestrator] [task_ledger] We are working to address the following user request...
[Magentic-Orchestrator] [instruction] Call search_scenarios ONCE with 'device timeline'
[Magentic-Agent-IntuneExpert] (assistant) Final: I'll execute the device timeline scenario...
[Magentic-Agent-IntuneExpert] Function call: search_scenarios
[Magentic-Agent-IntuneExpert] Function result received
[Magentic-FinalResult] Here is the comprehensive device timeline...
```

## Benefits

1. **Visibility**: See exactly what the orchestrator and agents are doing
2. **Debugging**: Understand workflow execution and identify looping issues
3. **Monitoring**: Track progress through complex multi-step scenarios
4. **Troubleshooting**: Identify when/why agents make unexpected tool calls

## Reference

Based on the official Agent Framework implementation:
- Source: https://github.com/microsoft/agent-framework/blob/main/python/packages/core/agent_framework/_workflows/_magentic.py
- Lines: 100-200 (event type definitions)
- Lines: 2000+ (MagenticBuilder.on_event implementation)

## Testing

To test the logging:

1. Start the backend: `cd backend && uv run uvicorn main:app --reload`
2. Run a diagnostic query that uses Magentic orchestration
3. Check logs for `[Magentic-*]` prefixed messages
4. Verify you see orchestrator instructions and agent responses

Example test query:
```bash
curl -X POST http://localhost:8000/api/diagnostics \
  -H "Content-Type: application/json" \
  -d '{"message": "Show device timeline for device-123"}'
```

## Future Enhancements

Potential improvements:

1. **Structured Logging**: Use structured log format (JSON) for easier parsing
2. **Event Filtering**: Add configuration to filter specific event types
3. **Performance Metrics**: Track timing between events for performance analysis
4. **Dashboard Integration**: Stream events to frontend for real-time UI updates
5. **Event Persistence**: Store events in database for historical analysis
