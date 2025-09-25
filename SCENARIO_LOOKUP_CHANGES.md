# Agent Configuration Optimization - Scenario Lookup System

## Overview

The agent configuration has been refactored from loading the entire `instructions.md` file (724 lines) into the system prompt to using an efficient lookup-based system. This significantly reduces token usage and improves agent performance by only loading relevant scenarios when needed.

## Previous Architecture Issues

- **Token Bloat**: The entire `instructions.md` file was injected into every agent conversation
- **Inefficient**: Agent had to parse through all scenarios even when only one was needed
- **Performance**: Large system prompts could overwhelm the agent and impact response quality
- **Scalability**: As scenarios grew, the system prompt would become unmanageably large

## New Architecture

### 1. Scenario Lookup Service (`scenario_lookup_service.py`)

**Key Features:**
- Parses `instructions.md` once at startup and indexes all scenarios
- Creates keyword indexes for efficient scenario matching
- Provides lightweight scenario summaries for the system prompt
- Enables precise scenario retrieval based on user intent

**Core Components:**
- `ScenarioInfo`: Lightweight scenario metadata for quick lookups
- `DetailedScenario`: Full scenario data with queries and descriptions
- `ScenarioLookupService`: Main service class handling all lookups

### 2. Agent Integration

**System Prompt Changes:**
- Instead of full instructions content, agent gets a concise scenario summary
- Agent learns about available scenarios and their keywords
- Agent instructions emphasize using the `lookup_scenarios` tool

**New Tool: `lookup_scenarios`**
- Agent function that accepts user request text
- Returns relevant scenarios with full query details
- Matches based on keywords and content analysis

## How It Works

### 1. Initialization
```python
# Service automatically loads and indexes scenarios
service = get_scenario_service()
```

### 2. Agent Workflow
1. User makes a request: *"I need device details for device 12345"*
2. Agent calls `lookup_scenarios("I need device details for device 12345")`
3. Service returns relevant scenarios (e.g., "Device Details" scenario with Kusto queries)
4. Agent executes the specific queries from the retrieved scenario
5. Agent returns results using only the relevant queries

### 3. Scenario Matching
The service uses multiple matching strategies:
- **Direct keyword matching**: "device" matches "Device Details" scenario
- **Partial keyword matching**: "compliance" matches scenarios with "compliant" keywords
- **Title matching**: Scenario titles are indexed and searchable
- **Weighted scoring**: More keyword matches = higher relevance

## Benefits

### Performance Improvements
- **Reduced Token Usage**: System prompt reduced from ~724 lines to ~50 lines summary
- **Faster Response**: Agent doesn't need to parse entire instruction set
- **Focused Context**: Only relevant scenarios are loaded per request

### Maintainability
- **Centralized Logic**: All scenario parsing in one service
- **Easy Updates**: Changes to `instructions.md` automatically reflected
- **Better Testing**: Service can be tested independently

### Scalability
- **Growing Instructions**: New scenarios don't bloat system prompt
- **Multiple Contexts**: Same service can support different instruction sets
- **Efficient Caching**: Scenarios loaded once, used many times

## Usage Examples

### Basic Scenario Lookup
```python
# Find scenarios for user request
scenarios = service.find_scenarios_by_keywords("device compliance status", max_results=3)
# Returns: ['compliance_(last_10_days)', 'device_details', 'policy___setting_status_and_assignments']

# Get detailed scenario
scenario = service.get_scenario_by_title("Device Details") 
# Returns: DetailedScenario with title, description, queries, keywords
```

### Agent Function Usage
```python
# Agent calls this function during conversation
result = await lookup_scenarios("Show me device compliance for device 12345")
# Returns formatted text with relevant scenarios and their Kusto queries
```

## Available Scenarios

The system currently indexes **18 scenarios** from `instructions.md`:

1. **Device Details** - Basic device information queries
2. **User ID Lookup** - Extract user associations  
3. **Policy / Setting Status** - Configuration and policy states
4. **Effective Group Troubleshooting** - Group membership analysis
5. **Compliance (Last 10 Days)** - Recent compliance changes
6. **Applications** - App installation and status
7. **Tenant Information** - Tenant and context details
8. **Advanced Scenario: Device Timeline** - Historical device data
9. And 10 more specialized scenarios...

## Configuration

### Service Initialization
```python
from services.scenario_lookup_service import get_scenario_service

# Service auto-initializes with instructions.md
service = get_scenario_service()

# For testing/development, reload scenarios
from services.scenario_lookup_service import reload_scenarios
reload_scenarios()
```

### Agent Integration
The agent automatically gets the `lookup_scenarios` tool and updated system prompt. No additional configuration required.

## Testing

### Scenario Service Test
```bash
python test_scenario_lookup.py
```
Verifies:
- Service initialization
- Scenario indexing
- Keyword matching
- Scenario retrieval

### Results
- ✓ 18 scenarios successfully indexed
- ✓ Keyword matching working correctly
- ✓ Scenario summaries generated efficiently
- ✓ All lookups functioning as expected

## Migration Notes

### What Changed
- `AgentService.__init__()`: Removed `instructions_content` and `scenarios` attributes
- `AgentService._load_instructions()`: Simplified to just initialize scenario service
- System prompt: Replaced full instructions with scenario summary
- Tool addition: Added `lookup_scenarios` tool to agent toolkit

### What Stayed the Same
- `instructions.md` format unchanged
- Existing scenario execution via `run_instruction_scenario()`
- MCP tool integration remains identical
- Agent conversation flow unchanged

### Backward Compatibility  
- All existing agent functions still work
- Scenario execution methods unchanged
- API endpoints remain compatible

## Conclusion

This refactoring transforms the agent from a "kitchen sink" approach (loading everything) to a "just-in-time" approach (loading what's needed). The result is:

- **Better Performance**: Faster responses, less token usage
- **Better User Experience**: More focused, relevant responses  
- **Better Maintainability**: Cleaner code, easier to extend
- **Better Scalability**: Can handle growing instruction sets

The agent now efficiently looks up only the diagnostic scenarios it needs, when it needs them, resulting in a more responsive and capable diagnostic assistant.