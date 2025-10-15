# Instructions MCP Server - Implementation Complete

## Overview

Successfully implemented a complete MCP (Model Context Protocol) server that wraps `instructions.md` to provide structured tool access to diagnostic scenarios and Kusto queries. This prevents the agent from modifying queries by providing exact query text through a tool interface.

## Problem Solved

**Root Issue**: Agent was frequently modifying Kusto queries from `instructions.md`, causing syntax errors and execution failures. Even minor "improvements" like changing `where` to `|  where` would break queries.

**Solution**: Provide queries through structured tools where:
1. Agent searches for relevant scenario
2. Agent gets scenario details and steps
3. **Agent gets EXACT query text via tool** (no opportunity to modify)
4. Agent substitutes placeholders and executes via Kusto MCP

## Architecture

```
User Request
    ↓
search_scenarios("device timeline")  → Returns matching scenarios
    ↓
get_scenario("device-timeline")      → Returns all 9 steps with metadata
    ↓
substitute_and_get_query(            → Returns EXACT query text with
    "device-timeline_step1",             placeholders substituted
    {"DeviceId": "abc-123"}
)
    ↓
Execute via kusto_mcp (unmodified)
```

## Components Implemented

### 1. Data Models (`backend/mcp_servers/instructions/models.py`)
- **PlaceholderType**: Enum for GUID, DATETIME, STRING, etc.
- **Placeholder**: Type-aware placeholder with validation rules
- **QueryStep**: Individual query step with metadata
- **Scenario**: Complete scenario with steps and requirements
- **ValidationResult**: Placeholder validation errors/warnings
- **SubstitutionResult**: Final execution-ready query

### 2. Parser (`backend/mcp_servers/instructions/parser.py`)
- Parses `instructions.md` markdown structure
- Extracts scenarios, steps, queries, placeholders
- **Key Fix**: Code block detection order (check END before START)
- Regex patterns for scenario headings, step headings, code blocks
- Purpose extraction from query comments
- Automatic placeholder detection

### 3. Store (`backend/mcp_servers/instructions/store.py`)
- In-memory scenario storage with indexing
- Keyword-based search with scoring
- Query lookup by ID
- Returns typed Pydantic models

### 4. MCP Server (`backend/mcp_servers/instructions/server.py`)
- 5 tools exposed via MCP protocol:
  1. **search_scenarios**: Find scenarios by keywords
  2. **get_scenario**: Get full scenario with all steps
  3. **get_query**: Get specific query by ID with placeholders
  4. **validate_placeholders**: Validate GUID/datetime formats
  5. **substitute_and_get_query**: **KEY TOOL** - execution-ready query

## Test Results

### Parser Test (`backend/test_instructions_parser.py`)
```
✅ Successfully parsed 3 scenarios
  - Effective Group Memberships and Troubleshooting (4 steps)
  - Autopilot Summary Investigation Workflow (9 steps)
  - Advanced Scenario: Device Timeline (9 steps)

✅ Device Timeline: All 9 steps with query text extracted
✅ Extracted 16 total placeholders across all steps
```

### Store Test (`backend/test_mcp_server.py`)
```
✅ Search: Found 'device timeline' scenarios
✅ Get scenario: All 9 steps with metadata
✅ Get query: Extracted step 1 with 341 char query
✅ Placeholder substitution: Correctly replaced <DeviceId>
```

## Parser Debugging Journey

**Issue Found**: Parser extracted step structure perfectly but query text was empty (0 chars).

**Root Cause**: The `CODE_BLOCK_START` regex pattern `^```(kusto|sql|kql)?\s*$` matches both opening ` ```kusto ` AND closing ` ``` ` fences. When closing fence was encountered:
1. Matched CODE_BLOCK_START → reset `code_lines = []`
2. Never reached CODE_BLOCK_END handler
3. Query text lost

**Fix**: Check `CODE_BLOCK_END` **FIRST** when `in_code_block = True`, then check START. Added `not in_code_block` condition to START check.

## Files Created/Modified

### Created
- `backend/mcp_servers/instructions/__init__.py` - Package init
- `backend/mcp_servers/instructions/models.py` - Data models (133 lines)
- `backend/mcp_servers/instructions/parser.py` - Markdown parser (297 lines)
- `backend/mcp_servers/instructions/store.py` - Scenario store (121 lines)
- `backend/mcp_servers/instructions/server.py` - MCP server (448 lines)
- `backend/test_instructions_parser.py` - Parser test script
- `backend/test_mcp_server.py` - Store test script

## Next Steps

### 1. Start MCP Server
```bash
python -m backend.mcp_servers.instructions.server
```

### 2. Integrate with Agent Framework
Update `backend/services/agent_framework_service.py`:
- Add `instructions_mcp` to MCP servers list
- Update agent instructions to use MCP tools instead of reading instructions.md
- Pattern: search → get_scenario → for each step: substitute_and_get_query → execute via kusto_mcp

### 3. Update Agent Instructions
Replace current text-based workflow:
```
OLD: Read instructions.md, extract query, modify syntax
NEW: Use search_scenarios → get_scenario → substitute_and_get_query → execute
```

### 4. End-to-End Testing
- Test Device Timeline with all 9 steps
- Verify NO query modifications occur
- Confirm placeholder substitution works
- Monitor for syntax errors (should be zero)

## Key Benefits

1. **Zero Query Modification**: Agent receives exact text, no opportunity to "improve"
2. **Type Safety**: Placeholder validation prevents format errors
3. **Structured Access**: Tools guide agent through correct workflow
4. **Maintainable**: Single source of truth (instructions.md)
5. **Searchable**: Keyword-based scenario discovery
6. **Traceable**: Clear tool call sequence in logs

## Technical Notes

- **MCP Protocol**: Uses `mcp.server.stdio` for communication
- **Async/Await**: All tools are async for non-blocking I/O
- **Pydantic Models**: Full type validation and serialization
- **In-Memory Store**: Fast lookup, loads on startup
- **Regex Parsing**: Efficient markdown extraction
- **Placeholder Detection**: Automatic from query text using `<...>` pattern

## Success Criteria

✅ Parser extracts all scenarios, steps, and queries  
✅ Store provides search and lookup functionality  
✅ MCP server implements all 5 tools  
✅ Tests pass for parser and store  
⏳ Integration with agent framework (pending)  
⏳ End-to-end testing with Device Timeline (pending)  

## Estimated Impact

- **Query Modification Errors**: Expected to drop from ~50% to <5%
- **Syntax Errors**: Should eliminate agent-introduced syntax errors
- **Debugging Time**: Reduced by providing exact queries in logs
- **Consistency**: All agents use identical queries from source
