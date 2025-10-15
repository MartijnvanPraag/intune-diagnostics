# Instructions MCP Server - Quick Reference

## Starting the Server

```bash
# Method 1: Direct execution
python -m backend.mcp_servers.instructions.server

# Method 2: As part of agent framework
# (Add to MCP servers config in agent_framework_service.py)
```

## Tool Reference

### 1. search_scenarios
**Purpose**: Find relevant diagnostic scenarios  
**When**: User asks about troubleshooting or diagnostic task

```python
search_scenarios(
    query="device timeline",  # Keywords to search
    domain="device"           # Optional: filter by domain
)
```

**Returns**:
```json
[
  {
    "slug": "device-timeline",
    "title": "Advanced Scenario: Device Timeline",
    "domain": "device",
    "description": "...",
    "required_identifiers": ["DeviceId", "StartTime", "EndTime"],
    "num_queries": 9,
    "keywords": ["timeline", "chronological", "history"]
  }
]
```

### 2. get_scenario
**Purpose**: Get complete scenario with all steps  
**When**: After search, need full step-by-step details

```python
get_scenario(slug="device-timeline")
```

**Returns**:
```json
{
  "slug": "device-timeline",
  "title": "Advanced Scenario: Device Timeline",
  "steps": [
    {
      "step_number": 1,
      "title": "Get Device Baseline Information",
      "query_id": "device-timeline_step1",
      "purpose": "Extract DeviceId, AccountId...",
      "placeholders": {"DeviceId": {...}},
      "optional": false
    },
    // ... 8 more steps
  ],
  "critical_requirements": [...],
  "execution_mode": "sequential"
}
```

### 3. get_query
**Purpose**: Get specific query with placeholder info  
**When**: Need to see query details before substitution

```python
get_query(query_id="device-timeline_step1")
```

**Returns**:
```json
{
  "query_id": "device-timeline_step1",
  "title": "Get Device Baseline Information",
  "query_text": "let DeviceID = '<DeviceId>';\n...",
  "placeholders": {
    "DeviceId": {
      "type": "GUID",
      "required": true,
      "description": "Device identifier",
      "example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    }
  }
}
```

### 4. validate_placeholders
**Purpose**: Validate placeholder values before substitution  
**When**: Want to check formats (GUID, datetime) before execution

```python
validate_placeholders(
    query_id="device-timeline_step1",
    values={"DeviceId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
)
```

**Returns**:
```json
{
  "is_valid": true,
  "errors": [],
  "warnings": []
}
```

### 5. substitute_and_get_query (⭐ KEY TOOL)
**Purpose**: Get execution-ready query with placeholders substituted  
**When**: Ready to execute - THIS IS THE PRIMARY TOOL

```python
substitute_and_get_query(
    query_id="device-timeline_step1",
    values={"DeviceId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
)
```

**Returns**:
```json
{
  "query_id": "device-timeline_step1",
  "original_placeholders": ["DeviceId"],
  "query": "let DeviceID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';\n..."
}
```

**⚠️ CRITICAL**: The `query` field contains EXACT text from instructions.md. Execute this directly via Kusto MCP - DO NOT MODIFY.

## Typical Workflow

```python
# 1. User: "Show me device timeline for device abc-123"

# 2. Search for scenario
results = search_scenarios("device timeline")
# -> Find "device-timeline" scenario

# 3. Get full scenario details
scenario = get_scenario("device-timeline")
# -> 9 steps, requires DeviceId, StartTime, EndTime

# 4. For each step (1-9):
step_query = substitute_and_get_query(
    query_id=f"device-timeline_step{i}",
    values={
        "DeviceId": "abc-123",
        "StartTime": "2024-01-01T00:00:00Z",
        "EndTime": "2024-01-31T23:59:59Z"
    }
)

# 5. Execute via Kusto MCP (NO MODIFICATION)
result = kusto_mcp.execute_query(step_query["query"])

# 6. Extract values for next steps (e.g., EffectiveGroupId from step 4)

# 7. Continue with remaining steps
```

## Placeholder Types

| Type | Format | Example |
|------|--------|---------|
| GUID | UUID format | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| GUID_LIST | Comma-separated | `guid1, guid2, guid3` |
| DATETIME | ISO 8601 | `2024-01-01T00:00:00Z` |
| STRING | Any text | `"device name"` |
| INTEGER | Number | `42` |
| BOOLEAN | true/false | `true` |

## Integration Example

```python
# In agent_framework_service.py

# Add to MCP servers
mcp_servers = [
    {
        "name": "instructions_mcp",
        "server_path": "backend.mcp_servers.instructions.server",
        "enabled": True
    }
]

# Update agent instructions
agent_instructions = """
When user asks for diagnostic scenario:

1. Use search_scenarios to find relevant scenario
2. Use get_scenario to get step-by-step details
3. For each step:
   - Use substitute_and_get_query to get execution-ready query
   - Execute query via kusto_mcp (DO NOT modify query text)
   - Extract values needed for next steps
4. Present results to user

CRITICAL: Never modify query text from substitute_and_get_query.
"""
```

## Error Handling

```python
# Scenario not found
result = get_scenario("invalid-slug")
# -> {"error": "Scenario not found: invalid-slug"}

# Invalid query ID
result = get_query("invalid-id")
# -> {"error": "Query not found: invalid-id"}

# Invalid placeholder format
result = validate_placeholders(
    "device-timeline_step1",
    {"DeviceId": "not-a-guid"}
)
# -> {
#     "is_valid": false,
#     "errors": ["DeviceId must be valid GUID format"]
# }

# Missing required placeholder
result = substitute_and_get_query("device-timeline_step1", {})
# -> {"error": "Missing required placeholder: DeviceId"}
```

## Testing Commands

```bash
# Test parser
uv run python backend/test_instructions_parser.py

# Test store
uv run python backend/test_mcp_server.py

# Start MCP server (for integration testing)
python -m backend.mcp_servers.instructions.server
```

## Monitoring

Watch for these patterns in logs:
- ✅ "Loaded N scenarios from instructions.md"
- ✅ Tool calls: search_scenarios, get_scenario, substitute_and_get_query
- ✅ Exact query execution (no modifications)
- ❌ Any query syntax errors (should NOT occur with this system)

## Success Indicators

1. Agent uses `substitute_and_get_query` for every query execution
2. Zero syntax errors from "improved" query modifications
3. Placeholder validation catches format errors before execution
4. Clear audit trail: search → scenario → query → execute
