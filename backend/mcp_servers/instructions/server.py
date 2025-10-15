"""
Instructions MCP Server

Provides structured access to diagnostic scenarios and queries from instructions.md.
Prevents query modification by providing exact query text through tool interface.
"""

import os
import re
from pathlib import Path
from typing import Optional

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

from .store import ScenarioStore
from .models import (
    ValidationError, ValidationResult, SubstitutionResult,
    PlaceholderType
)


# Initialize store
store = ScenarioStore()

# Load instructions.md on startup
instructions_path = Path(__file__).parent.parent.parent.parent / "instructions.md"
if instructions_path.exists():
    num_scenarios = store.load_from_file(str(instructions_path))
    # Log to stderr to avoid interfering with MCP protocol on stdout
    import sys
    print(f"[Instructions MCP] Loaded {num_scenarios} scenarios from instructions.md", file=sys.stderr, flush=True)
else:
    import sys
    print(f"[Instructions MCP] Warning: instructions.md not found at {instructions_path}", file=sys.stderr, flush=True)


# Create MCP server
server = Server("intune-instructions")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="search_scenarios",
            description=(
                "Search for diagnostic scenarios by keywords. "
                "Returns matching scenarios with metadata. "
                "Use this when the user asks about a diagnostic task or troubleshooting scenario."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "Search keywords (e.g., 'device timeline', 'compliance', 'autopilot', 'device_details')"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (alias for 'keywords')"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter (device, user, application, autopilot)",
                        "enum": ["device", "user", "application", "autopilot", "tenant"]
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_scenario",
            description=(
                "Get complete scenario details including all steps and queries. "
                "Returns structured scenario with execution order, dependencies, and exact query text. "
                "Use this after identifying the correct scenario via search_scenarios."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Scenario slug (e.g., 'device-timeline', 'autopilot-summary')"
                    }
                },
                "required": ["slug"]
            }
        ),
        Tool(
            name="get_query",
            description=(
                "Get a specific query by query_id. "
                "Returns exact query text with metadata about placeholders. "
                "Use when you know the specific query ID from a scenario."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query_id": {
                        "type": "string",
                        "description": "Query ID (e.g., 'device-timeline_step1')"
                    }
                },
                "required": ["query_id"]
            }
        ),
        Tool(
            name="validate_placeholders",
            description=(
                "Validate placeholder values before query execution. "
                "Checks types, formats (GUID, datetime, etc.). "
                "Use this to ensure placeholder values are correct before substitution."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query_id": {
                        "type": "string",
                        "description": "Query ID"
                    },
                    "placeholder_values": {
                        "type": "object",
                        "description": "Placeholder name -> value mapping",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["query_id", "placeholder_values"]
            }
        ),
        Tool(
            name="substitute_and_get_query",
            description=(
                "Get query with placeholders substituted - ready for execution. "
                "This is the KEY tool - returns execution-ready query with NO opportunity for modification. "
                "CRITICAL: Execute the returned query EXACTLY as provided. Do NOT modify query syntax."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query_id": {
                        "type": "string",
                        "description": "Query ID"
                    },
                    "placeholder_values": {
                        "type": "object",
                        "description": "Placeholder name -> value mapping",
                        "additionalProperties": {"type": "string"}
                    },
                    "validate": {
                        "type": "boolean",
                        "description": "Whether to validate placeholders first (default: true)"
                    }
                },
                "required": ["query_id", "placeholder_values"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    
    if name == "search_scenarios":
        # Support both 'query' and 'keywords' parameter names for backwards compatibility
        query = arguments.get("query") or arguments.get("keywords", "")
        domain = arguments.get("domain")
        
        results = store.search(query, domain)
        
        if not results:
            import json
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "no_results",
                    "query": query,
                    "results": []
                })
            )]
        
        # Format results as JSON
        import json
        results_json = []
        for scenario in results:
            results_json.append({
                "slug": scenario.slug,
                "title": scenario.title,
                "domain": scenario.domain or "general",
                "required_identifiers": scenario.required_identifiers,
                "num_queries": scenario.num_queries,
                "description": scenario.description,
                "keywords": scenario.keywords[:10]
            })
        
        output = {
            "status": "success",
            "query": query,
            "count": len(results),
            "results": results_json
        }
        
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
    
    elif name == "get_scenario":
        slug = arguments["slug"]
        scenario = store.get_scenario(slug)
        
        if not scenario:
            import json
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "not_found",
                    "slug": slug,
                    "message": f"Scenario '{slug}' not found. Use search_scenarios to find available scenarios."
                })
            )]
        
        # Format scenario details as JSON
        import json
        steps_json = []
        for step in scenario.steps:
            step_data = {
                "order": step.step_number,
                "query_id": step.query_id,
                "title": step.title,
                "purpose": step.purpose,
                "placeholders": {name: {"type": p.type.value, "required": p.required, "description": p.description}
                                for name, p in step.placeholders.items()},
                "extracts": step.extracts,
                "provides_for_steps": step.provides_for_steps,
                "optional": step.optional
            }
            steps_json.append(step_data)
        
        output = {
            "status": "success",
            "slug": scenario.slug,
            "title": scenario.title,
            "domain": scenario.domain,
            "required_identifiers": scenario.required_identifiers,
            "execution_mode": scenario.execution_mode,
            "description": scenario.description,
            "critical_requirements": scenario.critical_requirements,
            "num_steps": len(scenario.steps),
            "steps": steps_json
        }
        
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
    
    elif name == "get_query":
        query_id = arguments["query_id"]
        result = store.get_query_step(query_id)
        
        if not result:
            import json
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "not_found",
                    "query_id": query_id,
                    "message": f"Query '{query_id}' not found."
                })
            )]
        
        scenario, step = result
        
        # Format as JSON
        import json
        placeholders_data = {}
        for name, placeholder in step.placeholders.items():
            placeholders_data[name] = {
                "type": placeholder.type.value,
                "required": placeholder.required,
                "description": placeholder.description
            }
        
        output = {
            "status": "success",
            "query_id": step.query_id,
            "scenario_slug": scenario.slug,
            "scenario_title": scenario.title,
            "step_number": step.step_number,
            "step_title": step.title,
            "purpose": step.purpose,
            "query_text": step.query_text,
            "placeholders": placeholders_data
        }
        
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
    
    elif name == "validate_placeholders":
        query_id = arguments["query_id"]
        placeholder_values = arguments["placeholder_values"]
        
        result = store.get_query_step(query_id)
        if not result:
            import json
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "not_found",
                    "query_id": query_id,
                    "message": f"Query '{query_id}' not found."
                })
            )]
        
        _, step = result
        validation_result = validate_placeholder_values(step, placeholder_values)
        
        import json
        if validation_result.valid:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "valid": True,
                    "query_id": query_id
                })
            )]
        else:
            errors_list = []
            for error in validation_result.errors:
                errors_list.append({
                    "placeholder": error.placeholder,
                    "issue": error.issue,
                    "expected_format": error.expected_format
                })
            return [TextContent(type="text", text=json.dumps({
                "status": "validation_failed",
                "valid": False,
                "query_id": query_id,
                "errors": errors_list
            }))]
    
    elif name == "substitute_and_get_query":
        query_id = arguments["query_id"]
        placeholder_values = arguments["placeholder_values"]
        validate = arguments.get("validate", True)
        
        result = store.get_query_step(query_id)
        if not result:
            import json
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "not_found",
                    "query_id": query_id,
                    "message": f"Query '{query_id}' not found."
                })
            )]
        
        scenario, step = result
        
        # Validate if requested
        if validate:
            validation_result = validate_placeholder_values(step, placeholder_values)
            if not validation_result.valid:
                import json
                errors_list = [{"placeholder": e.placeholder, "issue": e.issue, "expected_format": e.expected_format}
                              for e in validation_result.errors]
                return [TextContent(type="text", text=json.dumps({
                    "status": "validation_failed",
                    "query_id": query_id,
                    "errors": errors_list
                }))]
        
        # Substitute placeholders
        substitution_result = substitute_placeholders(step, placeholder_values)
        
        # Return JSON with the execution-ready query
        import json
        output = {
            "status": "success",
            "query_id": query_id,
            "scenario_slug": scenario.slug,
            "step_number": step.step_number,
            "step_title": step.title,
            "query_text": substitution_result.query_text,
            "placeholders_used": substitution_result.placeholders_used,
            "warnings": substitution_result.warnings
        }
        
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
    
    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]


def validate_placeholder_values(step, placeholder_values: dict) -> ValidationResult:
    """Validate placeholder values"""
    errors = []
    
    for name, placeholder in step.placeholders.items():
        if placeholder.required and name not in placeholder_values:
            errors.append(ValidationError(
                placeholder=name,
                issue="Required placeholder not provided"
            ))
            continue
        
        if name not in placeholder_values:
            continue
        
        value = placeholder_values[name]
        
        # Type-specific validation
        if placeholder.type == PlaceholderType.GUID:
            if not is_valid_guid(value):
                errors.append(ValidationError(
                    placeholder=name,
                    issue="Invalid GUID format",
                    expected_format="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                ))
        
        elif placeholder.type == PlaceholderType.DATETIME:
            if not is_valid_datetime(value):
                errors.append(ValidationError(
                    placeholder=name,
                    issue="Invalid datetime format",
                    expected_format="YYYY-MM-DD HH:MM:SS or datetime(YYYY-MM-DD HH:MM:SS)"
                ))
    
    return ValidationResult(valid=len(errors) == 0, errors=errors)


def substitute_placeholders(step, placeholder_values: dict) -> SubstitutionResult:
    """Substitute placeholders in query"""
    query = step.query_text
    warnings = []
    placeholders_used = {}
    
    # Find all placeholders in query
    pattern = re.compile(r'<([A-Za-z][A-Za-z0-9_]*)>')
    
    for match in pattern.finditer(step.query_text):
        placeholder_name = match.group(1)
        
        if placeholder_name in placeholder_values:
            value = placeholder_values[placeholder_name]
            placeholders_used[placeholder_name] = value
            
            # Substitute
            query = query.replace(f"<{placeholder_name}>", value)
        else:
            warnings.append(f"Placeholder <{placeholder_name}> not provided - left as-is")
    
    return SubstitutionResult(
        query_text=query,
        placeholders_used=placeholders_used,
        warnings=warnings
    )


def is_valid_guid(value: str) -> bool:
    """Check if value is a valid GUID"""
    guid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(guid_pattern.match(value))


def is_valid_datetime(value: str) -> bool:
    """Check if value is a valid datetime"""
    # Accept various formats
    patterns = [
        r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
        r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$',  # YYYY-MM-DD HH:MM:SS
        r'^datetime\(["\']?\d{4}-\d{2}-\d{2}',  # datetime(...)
    ]
    return any(re.match(pattern, value) for pattern in patterns)


async def main():
    """Run the server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
