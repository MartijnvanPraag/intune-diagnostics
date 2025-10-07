# Table Rendering Troubleshooting Guide

## Issue: Tables Not Rendering with Agent Framework

### Symptoms
- Agent Framework responses show text but tables appear empty or garbled
- "Kusto Query Results" pane shows "No table data available"
- Tables work with Autogen but not with Agent Framework

### Root Cause

Agent Framework's `ChatAgent.run()` returns an `AgentRunResponse` object with a `.text` property. The response text contains the agent's natural language summary, but **Kusto query results (JSON tables) might not be automatically included in the text**.

### How Table Extraction Works

1. **Agent calls Kusto tool** → Tool returns JSON with `{success: true, data: [...], columns: [...]}`
2. **Agent processes result** → Creates natural language summary
3. **Response extraction** → We extract the `.text` property
4. **Table parsing** → `_extract_json_objects()` looks for JSON in the text
5. **Frontend rendering** → Displays tables from the `tables` array

### Debugging Steps

#### 1. Check if Agent is Calling Kusto Tools

Look for these log messages:
```
INFO:backend.services.agent_framework_service:[AgentFramework] Raw response type: <class '...'>
INFO:backend.services.agent_framework_service:[AgentFramework] Extracted X JSON objects from response
```

If it shows **0 JSON objects extracted**, the agent either:
- Didn't call the Kusto tool
- Called it but didn't include the result in its response text

#### 2. Verify Tool Registration

Check that MCP tools are discovered:
```
INFO:backend.services.agent_framework_service:Discovered X MCP tools
```

Should show tools like:
- `execute_kusto_query`
- `list_tables`
- `list_columns`

#### 3. Check Agent Instructions

The `IntuneExpert` agent should be instructed to:
```python
"""You are an expert at Intune diagnostics.

IMPORTANT: When you execute Kusto queries:
1. Always call the execute_kusto_query tool
2. Include the complete JSON result in your response
3. Format the data as a table for the user

Example response format:
Here are the device details:

{JSON table data here}

Summary: Found 1 device...
"""
```

### Solution Options

#### Option 1: Enhanced Logging (Implemented)

Added debug logging to see exactly what Agent Framework returns:

```python
logger.info(f"[AgentFramework] Raw response type: {type(response)}")
logger.info(f"[AgentFramework] Raw response (first 500 chars): {response_content[:500]}")
logger.info(f"[AgentFramework] Extracted {len(extracted_objs)} JSON objects")
```

**Action**: Run the app and check logs to see what's happening.

#### Option 2: Access Tool Results Directly

Instead of relying on text extraction, access tool results from the response object:

```python
# Check if AgentRunResponse has raw_representation or similar
if hasattr(response, 'raw_representation'):
    # Extract tool results directly
    ...
```

**Status**: Need to investigate `AgentRunResponse` structure further.

#### Option 3: Modify Agent Instructions

Update the agent's system message to explicitly include query results:

```python
self.agent_instructions = """
...
CRITICAL: When you execute a Kusto query, you MUST include the complete 
JSON result in your response. Copy the entire tool result into your message.

Example:
User: Show device details for abc-123
Agent: Here are the device details:

{"success": true, "data": [{...}], "columns": [...]}

The device was last seen on...
"""
```

**Status**: Requires testing.

#### Option 4: Use Streaming with Tool Call Capture

Use `agent.run_stream()` to capture tool calls as they happen:

```python
tool_results = []
async for chunk in self.intune_expert_agent.run_stream(composite_task):
    if hasattr(chunk, 'tool_call_result'):
        tool_results.append(chunk.tool_call_result)
```

**Status**: Needs implementation.

### Comparison: Autogen vs Agent Framework

#### Autogen (Working)
```python
# MagenticOneGroupChat automatically includes tool results
result = await team.run(task=message)

# Messages include all tool calls and results
for msg in result.messages:
    if "execute_kusto_query" in msg.content:
        # Tool result is in message content
        extract_json_from_text(msg.content)
```

#### Agent Framework (Current)
```python
# ChatAgent.run() returns AgentRunResponse
response = await agent.run(task)

# response.text contains summary, but tool results might not be included
response_text = response.text  # ← May not contain JSON tables
```

### Testing Checklist

- [ ] Start backend with Agent Framework selected
- [ ] Check logs for "Discovered X MCP tools"
- [ ] Send test query: "Show device details for [device-id]"
- [ ] Check logs for:
  - [ ] "Calling Kusto tool execute_kusto_query"
  - [ ] "Extracted X JSON objects" (should be > 0)
  - [ ] "Found X unique tables" (should be > 0)
- [ ] Check frontend:
  - [ ] AI response text appears
  - [ ] "Kusto Query Results" pane has tables
  - [ ] Tables render correctly

### Expected Log Output (Success)

```
INFO:backend.services.agent_framework_service:Processing chat message through Agent Framework
INFO:backend.services.agent_framework_service:[AgentFramework] Raw response type: <class 'AgentRunResponse'>
INFO:backend.services.agent_framework_service:[AgentFramework] Raw response (first 500 chars): Here are the device details: {success: true, data: [...]}
INFO:backend.services.agent_framework_service:[AgentFramework] Extracted 1 JSON objects from response
INFO:backend.services.agent_framework_service:[AgentFramework] Found 1 unique tables
```

### Temporary Workaround

If tables don't render with Agent Framework, switch back to Autogen:

1. Go to **Settings** page
2. Edit model configuration
3. Select **"Autogen Framework"**
4. Save configuration

This will use the working Autogen implementation while we debug Agent Framework.

### Next Steps

1. **Run the app** and collect logs
2. **Send test query** with Agent Framework selected
3. **Analyze logs** to see if:
   - Tools are being called
   - JSON is in the response
   - Extraction is working
4. **Report findings** to determine root cause
5. **Implement fix** based on findings

---

**Status**: Under investigation with enhanced logging  
**Workaround**: Use Autogen Framework  
**Priority**: High (blocks Agent Framework adoption)
