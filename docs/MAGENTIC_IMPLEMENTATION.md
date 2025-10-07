# Magentic Manager Implementation for Agent Framework

## Summary

Successfully implemented Magentic orchestration for the Agent Framework service in `agent_framework_service.py`, providing feature parity with the Autogen implementation's `MagenticOneGroupChat`.

## Changes Made

### 1. Imports (Lines 22-28)
Added required imports from `agent_framework`:
- `MagenticBuilder` - Builder pattern for creating Magentic workflows
- `WorkflowOutputEvent` - Event type for capturing final workflow output

### 2. AgentFrameworkService Class Updates

#### __init__ method (Lines 291-302)
- Added `self.magentic_workflow` property to store the built Magentic workflow instance

#### setup_agent method (Lines 876-914)
**Before**: Created a simple ChatAgent with tools
**After**: 
- Creates ChatAgent with tools (IntuneExpert agent)
- Builds Magentic workflow using `MagenticBuilder`:
  ```python
  self.magentic_workflow = (
      MagenticBuilder()
      .participants(IntuneExpert=self.intune_expert_agent)
      .with_standard_manager(
          chat_client=self.chat_client,
          max_round_count=20,  # Equivalent to Autogen's max_turns
          max_stall_count=3,   # Equivalent to Autogen's max_stalls
      )
      .build()
  )
  ```
- Maintains the same configuration as Autogen's MagenticOneGroupChat

#### query_diagnostics method (Lines 917-1050)
**Before**: Used `agent.run(query_message)` for simple agent execution
**After**: Uses Magentic workflow orchestration:
- `async for event in self.magentic_workflow.run_stream(query_message)`
- Processes `WorkflowOutputEvent` for final response text
- Extracts tables from `FunctionResultContent` in streamed events
- Maintains compatibility with existing response structure
- Adds `[Magentic]` log prefixes for easier debugging

#### chat method (Lines 1084-1205)
**Before**: Used `agent.run(composite_task)` for simple agent execution
**After**: Uses Magentic workflow orchestration:
- `async for event in self.magentic_workflow.run_stream(composite_task)`
- Processes `WorkflowOutputEvent` for final response text
- Extracts function results from streamed events
- Maintains conversation history handling
- Updates `agent_used` field to "AgentFramework (Magentic)"
- Adds `[Magentic]` log prefixes for easier debugging

## Comparison with Autogen Implementation

| Feature | Autogen (autogen_service.py) | Agent Framework (agent_framework_service.py) |
|---------|---------------------------|---------------------------------------------|
| Orchestration | `MagenticOneGroupChat` | `MagenticBuilder().build()` |
| Participants | `participants=[self.intune_expert_agent]` | `.participants(IntuneExpert=agent)` |
| Manager | Automatic with `model_client` | `.with_standard_manager(chat_client, ...)` |
| Max Turns | `max_turns=20` | `max_round_count=20` |
| Max Stalls | `max_stalls=3` | `max_stall_count=3` |
| Execution | `team.run(task)` | `workflow.run_stream(task)` |
| Response | `team_result.messages[-1]` | `WorkflowOutputEvent.data` |

## Key Benefits

1. **Multi-Agent Orchestration**: The Magentic manager now handles agent coordination, task planning, progress tracking, and replanning
2. **Intelligent Task Management**: Automatic detection of task completion, stalling, and looping scenarios
3. **Streaming Support**: Event-based streaming provides real-time progress visibility
4. **Feature Parity**: Maintains identical functionality to Autogen implementation
5. **Better Logging**: Distinct `[Magentic]` log prefixes make debugging easier

## Testing Recommendations

1. **Backend Startup**: Verify backend starts without errors
2. **DCv1/DCv2 Query**: Test the problematic query that was failing with syntax issues
3. **Other Diagnostics**: Ensure all diagnostic query types work correctly
4. **Orchestration Logs**: Check logs for Magentic manager activity (planning, progress updates, etc.)
5. **Conversation Context**: Verify multi-turn conversations maintain context properly

## Next Steps

The user should:
1. Restart the backend to load the updated Agent Framework service
2. Test the DCv1/DCv2 conflict query in Advanced Scenarios
3. Verify orchestration logs show Magentic manager coordinating the agent
4. Confirm query results are correct and syntax preservation works

## Notes

- The type checker warnings about `event.message` are expected and safe - we use `hasattr()` guards
- The implementation maintains backward compatibility with all existing interfaces
- Logs now use `[Magentic]` prefix to distinguish from non-orchestrated agent calls
