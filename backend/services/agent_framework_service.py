"""
Agent Framework implementation for Intune Diagnostics

This module provides a feature-complete alternative to the Autogen Framework implementation,
using Microsoft's Agent Framework for multi-agent orchestration and diagnostics.

Migration Notes:
- Full feature parity with autogen_service.py (Autogen)
- Compatible with the same interfaces and return types
- Can be switched via settings toggle
- Supports all existing tools, MCP integration, and scenario lookup
"""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias

# Agent Framework imports (equivalent to Autogen)
# The agent-framework package provides the core chat agent functionality
# Documentation: https://github.com/microsoft/agent-framework/tree/main/python
from agent_framework import (
    ChatAgent,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticBuilder,
    MagenticFinalResultEvent,
    MagenticOrchestratorMessageEvent,
    WorkflowOutputEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from models.schemas import ModelConfiguration
from services.auth_service import auth_service
from services.scenario_lookup_service import get_scenario_service

# Logging is configured in main.py
logger = logging.getLogger(__name__)

# Buffer to hold recent MCP tool normalized results (tables) because Agent Framework
# streaming events are not currently exposing function result payloads needed for
# table reconstruction. This allows a fallback after workflow completion.
TOOL_RESULTS_BUFFER: list[dict[str, Any]] = []

# Define the Union type for Magentic callback events
MagenticCallbackEvent: TypeAlias = (
    MagenticOrchestratorMessageEvent
    | MagenticAgentDeltaEvent
    | MagenticAgentMessageEvent
    | MagenticFinalResultEvent
)



def _normalize_datetime_value(raw: Any) -> Any:
    """Convert common ISO 8601 datetime strings to Kusto friendly format."""
    from datetime import datetime as dt_parser

    if not isinstance(raw, str):
        return raw
    if 'T' not in raw and ':' in raw:
        return raw
    iso_candidates = [
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f+00:00',
        '%Y-%m-%dT%H:%M:%S+00:00'
    ]
    for fmt in iso_candidates:
        try:
            return dt_parser.strptime(raw, fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    if raw.endswith('Z'):
        try:
            trimmed = raw.rstrip('Z')
            return dt_parser.strptime(trimmed, '%Y-%m-%dT%H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            return raw
    return raw


def _normalize_placeholder_value(key_name: str, raw: Any) -> Any:
    """Apply post-processing to match Instructions MCP expectations."""
    if raw is None:
        return raw
    if isinstance(raw, list):
        return ','.join(str(item) for item in raw)
    if isinstance(raw, (int, float)):
        return str(raw)
    if isinstance(raw, str) and key_name.lower().endswith('time'):
        return _normalize_datetime_value(raw)
    return raw


def create_context_lookup_function() -> Callable[..., Awaitable[str]]:
    """Create a function for looking up stored conversation context"""
    
    async def lookup_context(key: str = "") -> str:
        """Look up stored conversation context values like DeviceId, AccountId, ContextId from previous queries.
        
        Use this when you need values from earlier in the conversation to fill placeholders in queries.
        Call with no parameters to see all available context, or with a specific key to get one value.
        
        Args:
            key: Optional specific context key to look up (e.g., 'DeviceId', 'AccountId')
            
        Returns:
            The requested context value(s) or information about available context
        """
        try:
            from services.conversation_state import get_conversation_state_service
            
            context_service = get_conversation_state_service()
            
            logger.info(f"[AgentFramework] Context lookup called with key: '{key}'")
            
            if key:
                # Look up specific key
                value = context_service.get_context_value(key)
                if value:
                    logger.info(f"[AgentFramework] Found context {key}: {value}")
                    return f"Found {key}: {value}"
                else:
                    available_keys = list(context_service.get_all_context().keys())
                    logger.warning(f"[AgentFramework] No value for '{key}'. Available: {available_keys}")
                    return f"No value found for key '{key}'. Available context: {available_keys}"
            else:
                # Return all available context
                all_context = context_service.get_all_context()
                if all_context:
                    context_lines = [f"{k}: {v}" for k, v in all_context.items()]
                    logger.info(f"[AgentFramework] Returning all context: {list(all_context.keys())}")
                    return "Available conversation context:\n" + "\n".join(context_lines)
                else:
                    logger.info("[AgentFramework] No conversation context available")
                    return "No conversation context available."
                    
        except Exception as e:
            logger.error(f"[AgentFramework] Error in context lookup: {e}")
            return f"Error looking up context: {str(e)}"
    
    # Set function metadata for proper tool registration
    lookup_context.__name__ = "lookup_context"
    
    return lookup_context

def create_mcp_tool_function(tool_name: str, tool_description: str) -> Callable[..., Awaitable[str]]:
    """Create an async function wrapper for an MCP tool
    
    This maintains compatibility with the Autogen implementation's MCP tool pattern,
    including the same parameter handling and context substitution logic.
    """
    
    async def mcp_tool_func(**kwargs: Any) -> str:
        """Execute MCP tool.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            Result from the MCP tool execution
        """
        try:
            from services.conversation_state import get_conversation_state_service
            from services.kusto_mcp_service import get_kusto_service
            
            kusto_service = await get_kusto_service()
            context_service = get_conversation_state_service()
            
            # Handle nested kwargs structure from agent calls
            if "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
                # Agent passed arguments nested under 'kwargs'
                actual_args = kwargs["kwargs"]
            else:
                # Direct argument passing
                actual_args = kwargs
            
            logger.info(f"[AgentFramework] Calling MCP tool '{tool_name}' with args: {actual_args}")
            
            # For execute_query tool, ensure proper clusterUrl format and call MCP server directly
            if tool_name == "execute_query" and hasattr(kusto_service, '_session') and kusto_service._session:
                query = actual_args.get("query")
                
                if not query:
                    return json.dumps({"success": False, "error": "Missing required parameter: query"})
                
                # Substitute placeholders in query with stored context
                query = context_service.substitute_placeholders(query)
                
                logger.info(f"[AgentFramework] Query length: {len(query)} characters")
                logger.info(f"[AgentFramework] Query (first 500 chars): {query[:500]}...")
                
                # Extract cluster URL and database from the query
                import re
                
                cluster_url = None
                database = None
                
                # Pattern 1: Direct cluster calls - cluster("url").database("db") or cluster('url').database('db')
                # Handles both single and double quotes, with or without https:// prefix
                direct_cluster_match = re.search(r"cluster\(['\"](?:https?://)?([^'\"]+)['\"]\)", query)
                if direct_cluster_match:
                    cluster_url = direct_cluster_match.group(1)
                
                # Pattern 2: base_query function calls - base_query('url', 'label')
                # This pattern is used when queries define a function parameter
                if not cluster_url or cluster_url == "cluster":
                    base_query_match = re.search(r"base_query\(['\"]([^'\"]+)['\"]", query)
                    if base_query_match:
                        cluster_url = base_query_match.group(1)
                
                # Extract database name
                database_match = re.search(r"\.database\(['\"]([^'\"]+)['\"]\)", query)
                if database_match:
                    database = database_match.group(1)
                
                # Use fallback defaults if not found
                if not cluster_url or cluster_url == "cluster":
                    cluster_url = "intune.kusto.windows.net"
                    logger.warning(f"[AgentFramework] Could not extract cluster URL, using default: {cluster_url}")
                
                if not database:
                    database = "intune"
                    logger.warning(f"[AgentFramework] Could not extract database, using default: {database}")
                
                # Ensure cluster URL is properly formatted (add https:// if missing)
                if not cluster_url.startswith("https://"):
                    cluster_url = f"https://{cluster_url}"
                
                logger.info(f"[AgentFramework] Extracted cluster URL: {cluster_url}")
                logger.info(f"[AgentFramework] Extracted database: {database}")
                
                mcp_args = {
                    "clusterUrl": cluster_url,
                    "database": database,
                    "query": query,
                    **{k: v for k, v in actual_args.items() if k not in ["clusterUrl", "database", "query"]}
                }
                
                try:
                    result = await kusto_service._session.call_tool(tool_name, mcp_args)
                    normalized = kusto_service._normalize_tool_result(result)
                except Exception as e:
                    logger.error(f"[AgentFramework] MCP call_tool failed: {type(e).__name__}: {e}")
                    logger.error(f"[AgentFramework] Tool: {tool_name}")
                    logger.error(f"[AgentFramework] Query contained {len(query)} chars")
                    raise
                
                # Store query results in conversation context
                if normalized and isinstance(normalized, dict) and normalized.get("success"):
                    context_service.update_from_query_result(normalized)
                    try:
                        if isinstance(normalized.get("table"), dict):
                            TOOL_RESULTS_BUFFER.append(normalized)
                    except Exception:  # noqa: BLE001
                        pass
                
                return json.dumps(normalized)
            
            # For other tools, call MCP session directly
            elif hasattr(kusto_service, '_session') and kusto_service._session:
                result = await kusto_service._session.call_tool(tool_name, actual_args)
                # Normalize the result
                normalized = kusto_service._normalize_tool_result(result)
                
                # Store query results in conversation context if successful
                if normalized and isinstance(normalized, dict) and normalized.get("success"):
                    context_service.update_from_query_result(normalized)
                    try:
                        if isinstance(normalized.get("table"), dict):
                            TOOL_RESULTS_BUFFER.append(normalized)
                    except Exception:  # noqa: BLE001
                        pass
                
                return json.dumps(normalized)
            else:
                return json.dumps({"success": False, "error": "MCP session not available"})
                
        except Exception as e:
            logger.error(f"MCP tool {tool_name} execution failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
    
    # Set function metadata for proper tool registration
    mcp_tool_func.__name__ = tool_name
    mcp_tool_func.__doc__ = tool_description
    
    return mcp_tool_func


def create_instructions_mcp_tool_function(tool_name: str, tool_description: str) -> Callable[..., Awaitable[str]]:
    """Create an async function wrapper for an Instructions MCP tool
    
    Similar to create_mcp_tool_function but for the Instructions MCP server.
    These tools provide structured access to diagnostic scenarios and queries.
    """
    
    async def instructions_mcp_tool_func(**kwargs: Any) -> str:
        """Execute Instructions MCP tool.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            Result from the Instructions MCP tool execution
        """
        try:
            from services.instructions_mcp_service import get_instructions_service
            
            instructions_service = await get_instructions_service()
            
            # Handle nested kwargs structure from agent calls
            if "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
                actual_args = kwargs["kwargs"]
            else:
                actual_args = kwargs
            
            logger.info(f"[AgentFramework] Calling Instructions MCP tool '{tool_name}' with args: {actual_args}")
            
            if hasattr(instructions_service, '_session') and instructions_service._session:
                # Normalize placeholder values to formats expected by Instructions MCP
                if isinstance(actual_args, dict) and 'placeholder_values' in actual_args:
                    placeholder_values = actual_args['placeholder_values']
                    if isinstance(placeholder_values, dict):
                        normalized: dict[str, Any] = {}
                        for key, val in placeholder_values.items():
                            # Special handling for list placeholders (PolicyIdList, GroupIdList, etc.)
                            # Convert comma-separated GUIDs to quoted KQL format
                            if key.endswith('List') and isinstance(val, str) and ',' in val:
                                # Remove any existing quotes and spaces, then reformat
                                clean_values = [v.strip().strip("'\"") for v in val.split(',')]
                                formatted_val = ', '.join(f"'{v}'" for v in clean_values if v)
                                normalized[key] = formatted_val
                                logger.debug(f"[AgentFramework] Formatted {key} for KQL: {formatted_val[:100]}...")
                            else:
                                normalized[key] = _normalize_placeholder_value(key, val)
                        actual_args = {**actual_args, 'placeholder_values': normalized}
                        logger.debug(f"[AgentFramework] Normalized placeholder values for {tool_name}: {normalized}")

                result = await instructions_service._session.call_tool(tool_name, actual_args)
                
                # Properly serialize the result
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, list) and content:
                        # Handle TextContent objects
                        text_content = content[0]
                        text_attr = getattr(text_content, 'text', None)
                        if text_attr is not None:
                            result_text = str(text_attr)
                            # Log the response for debugging
                            if len(result_text) <= 500:
                                logger.info(f"[AgentFramework] Instructions MCP tool '{tool_name}' returned: {result_text}")
                            else:
                                logger.info(f"[AgentFramework] Instructions MCP tool '{tool_name}' returned {len(result_text)} chars: {result_text[:500]}...")
                            return result_text
                        else:
                            return json.dumps({"content": str(text_content)})
                    return json.dumps({"content": "No content returned"})
                else:
                    return json.dumps({"result": str(result)})
            else:
                return json.dumps({"success": False, "error": "Instructions MCP session not available"})
                
        except Exception as e:
            logger.error(f"Instructions MCP tool {tool_name} execution failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
    
    # Set function metadata for proper tool registration
    instructions_mcp_tool_func.__name__ = tool_name
    instructions_mcp_tool_func.__doc__ = tool_description
    
    return instructions_mcp_tool_func


def create_datawarehouse_mcp_tool_function(tool_name: str, tool_description: str) -> Callable[..., Awaitable[str]]:
    """Create an async function wrapper for a Data Warehouse MCP tool
    
    Similar to create_mcp_tool_function but for the Data Warehouse MCP server.
    These tools provide OData-based access to Intune historical data (24-hour snapshots).
    """
    
    async def datawarehouse_mcp_tool_func(**kwargs: Any) -> str:
        """Execute Data Warehouse MCP tool.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            Result from the Data Warehouse MCP tool execution
        """
        try:
            from services.datawarehouse_mcp_service import get_datawarehouse_service
            
            datawarehouse_service = await get_datawarehouse_service()
            
            # Handle nested kwargs structure from agent calls
            if "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
                actual_args = kwargs["kwargs"]
            else:
                actual_args = kwargs
            
            logger.info(f"[AgentFramework] Calling Data Warehouse MCP tool '{tool_name}' with args: {actual_args}")
            
            if hasattr(datawarehouse_service, '_session') and datawarehouse_service._session:
                result = await datawarehouse_service._session.call_tool(tool_name, actual_args)
                
                # Properly serialize the result
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, list) and content:
                        # Handle TextContent objects
                        text_content = content[0]
                        text_attr = getattr(text_content, 'text', None)
                        if text_attr is not None:
                            result_text = str(text_attr)
                            # Log the response for debugging
                            if len(result_text) <= 500:
                                logger.info(f"[AgentFramework] Data Warehouse MCP tool '{tool_name}' returned: {result_text}")
                            else:
                                logger.info(f"[AgentFramework] Data Warehouse MCP tool '{tool_name}' returned {len(result_text)} chars: {result_text[:500]}...")
                            return result_text
                        else:
                            return json.dumps({"content": str(text_content)})
                    return json.dumps({"content": "No content returned"})
                else:
                    return json.dumps({"result": str(result)})
            else:
                return json.dumps({"success": False, "error": "Data Warehouse MCP session not available"})
                
        except Exception as e:
            logger.error(f"Data Warehouse MCP tool {tool_name} execution failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
    
    # Set function metadata for proper tool registration
    datawarehouse_mcp_tool_func.__name__ = tool_name
    datawarehouse_mcp_tool_func.__doc__ = tool_description
    
    return datawarehouse_mcp_tool_func


class AgentFrameworkService:
    """Agent Framework implementation for Intune diagnostics
    
    This class provides full feature parity with the Autogen-based AgentService,
    using Microsoft's Agent Framework instead. It supports:
    
    - Multi-agent orchestration (via ChatAgent workflows)
    - MCP tool integration
    - Scenario-based diagnostics
    - Conversation context management
    - All query types from the original implementation
    
    The interface is designed to be a drop-in replacement for AgentService,
    maintaining the same method signatures and return types.
    """
    
    def __init__(self) -> None:
        self.intune_expert_agent: ChatAgent | None = None
        self.magentic_workflow: Any | None = None  # MagenticWorkflow instance
        self.chat_client: AzureOpenAIChatClient | None = None
        
        # Force reload scenarios to ensure we have the latest matching logic
        from services.scenario_lookup_service import reload_scenarios
        reload_scenarios()
        self.scenario_service = get_scenario_service()
        
        logger.info("AgentFrameworkService initialized (Agent Framework implementation)")

    def list_instruction_scenarios(self) -> list[dict[str, Any]]:
        """Return a lightweight summary of parsed instruction scenarios."""
        scenario_titles = self.scenario_service.list_all_scenario_titles()
        scenarios = []
        
        for idx, title in enumerate(scenario_titles):
            scenario = self.scenario_service.get_scenario_by_title(title)
            if scenario:
                scenarios.append({
                    "index": idx,
                    "title": scenario.title,
                    "query_count": len(scenario.queries),
                    "description": scenario.description.split("\n")[0][:160] if scenario.description else ""
                })
        
        return scenarios

    async def run_instruction_scenario(self, scenario_ref: int | str) -> dict[str, Any]:
        """Execute all queries in a referenced scenario
        
        Maintains compatibility with Autogen implementation by executing
        scenarios directly through the Kusto MCP service.
        """
        try:
            scenario_titles = self.scenario_service.list_all_scenario_titles()
            
            if not scenario_titles:
                raise ValueError("No scenarios available")

            scenario = None
            if isinstance(scenario_ref, int):
                if 0 <= scenario_ref < len(scenario_titles):
                    title = scenario_titles[scenario_ref]
                    scenario = self.scenario_service.get_scenario_by_title(title)
            else:
                # Find by title
                scenario = self.scenario_service.get_scenario_by_title(scenario_ref)
                
                # If not found, try partial match
                if not scenario:
                    ref_lower = scenario_ref.lower()
                    for title in scenario_titles:
                        if ref_lower in title.lower():
                            scenario = self.scenario_service.get_scenario_by_title(title)
                            break

            if scenario is None:
                raise ValueError(f"Scenario not found: {scenario_ref}")

            from services.kusto_mcp_service import get_kusto_service
            kusto_service = await get_kusto_service()

            tables: list[dict[str, Any]] = []
            errors: list[str] = []
            for idx, query in enumerate(scenario.queries):
                res = await kusto_service.execute_kusto_query(query)
                if res.get("success"):
                    tables.append(res.get("table", {"columns": ["Result"], "rows": [["(empty)"]], "total_rows": 0}))
                else:
                    err = res.get("error", "Unknown error")
                    errors.append(f"Query {idx+1}: {err}")
                    tables.append({"columns": ["Error"], "rows": [[err]], "total_rows": 1})

            summary_parts = [f"Scenario: {scenario.title} ({len(tables)} queries)"]
            if errors:
                summary_parts.append(f"{len(errors)} query errors encountered.")
            summary = " \n".join(summary_parts)

            return {
                "scenario": scenario.title,
                "description": scenario.description,
                "tables": tables,
                "summary": summary,
                "errors": errors,
            }
        except Exception as e:  # noqa: BLE001
            logger.error(f"Scenario execution failed: {e}")
            return {
                "scenario": str(scenario_ref),
                "description": "Execution failed",
                "tables": [{"columns": ["Error"], "rows": [[str(e)]], "total_rows": 1}],
                "summary": f"Failed to execute scenario: {e}",
                "errors": [str(e)],
            }
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize the global agent framework service and eagerly start MCP server"""
        global agent_framework_service
        agent_framework_service = cls()
        await agent_framework_service._load_instructions()
        
        # Proactively validate authentication for cognitive services
        await agent_framework_service._validate_authentication()
        
        # Eagerly spin up MCP server
        try:
            from services.kusto_mcp_service import get_kusto_service
            kusto_service = await get_kusto_service()
            logger.info("Eager MCP server initialization completed during AgentFrameworkService startup")
            
            # Prewarm MCP sessions with cluster/database pairs
            try:
                all_queries: list[str] = []
                scenario_titles = agent_framework_service.scenario_service.list_all_scenario_titles()
                for title in scenario_titles:
                    scenario = agent_framework_service.scenario_service.get_scenario_by_title(title)
                    if scenario:
                        all_queries.extend(scenario.queries)
                
                if all_queries:
                    import re
                    pair_pattern = r"cluster\([\"']([^\"']+)[\"']\)\.database\([\"']([^\"']+)[\"']\)"
                    cluster_db_pairs: list[tuple[str, str]] = []
                    seen_pairs: set[tuple[str, str]] = set()
                    for q in all_queries:
                        m = re.search(pair_pattern, q)
                        if m:
                            pair = (m.group(1), m.group(2))
                            if pair not in seen_pairs:
                                seen_pairs.add(pair)
                                cluster_db_pairs.append(pair)
                    if cluster_db_pairs:
                        await kusto_service.prewarm_mcp_sessions(cluster_db_pairs)
                    else:
                        logger.info("No cluster/database pairs found for MCP session prewarm")
                else:
                    logger.info("No queries found for MCP prewarm")
            except Exception as prewarm_err:  # noqa: BLE001
                logger.warning(f"MCP session prewarm encountered issues: {prewarm_err}")
        except Exception as mcp_init_err:  # noqa: BLE001
            logger.warning(f"Eager MCP initialization failed (will lazy-init on first use): {mcp_init_err}")
    
    @classmethod
    async def cleanup(cls) -> None:
        """Cleanup agent service resources"""
        try:
            # Attempt to cleanup Kusto MCP service if loaded
            try:
                from services.kusto_mcp_service import kusto_mcp_service
                if kusto_mcp_service:
                    await kusto_mcp_service.cleanup()
            except Exception as mcp_err:  # noqa: BLE001
                logger.warning(f"MCP service cleanup warning: {mcp_err}")

            global agent_framework_service
            agent_framework_service = None
            logger.info("AgentFrameworkService cleanup completed")
        except Exception as e:  # noqa: BLE001
            logger.error(f"AgentFrameworkService cleanup failed: {e}")
    
    async def _load_instructions(self) -> None:
        """Initialize scenario service (scenarios are loaded automatically)"""
        try:
            scenario_titles = self.scenario_service.list_all_scenario_titles()
            logger.info(f"Loaded {len(scenario_titles)} instruction scenarios")
        except Exception as e:
            logger.warning(f"Failed to load instruction scenarios: {e}")
    
    def reload_scenarios(self) -> None:
        """Reload scenarios from instructions.md"""
        try:
            from services.scenario_lookup_service import reload_scenarios
            reload_scenarios()
            self.scenario_service = get_scenario_service()
            scenario_titles = self.scenario_service.list_all_scenario_titles()
            logger.info(f"Reloaded {len(scenario_titles)} instruction scenarios")
        except Exception as e:
            logger.error(f"Failed to reload scenarios: {e}")
    
    async def _validate_authentication(self) -> None:
        """Proactively validate authentication tokens"""
        try:
            logger.info("Validating authentication tokens...")
            
            # Test cognitive services token retrieval
            cognitive_token = await auth_service.get_cognitive_services_token()
            if not cognitive_token:
                raise Exception("Failed to retrieve cognitive services token")
            
            # Test graph token retrieval
            graph_token = await auth_service.get_graph_token()
            if not graph_token:
                raise Exception("Failed to retrieve Microsoft Graph token")
                
            logger.info("Authentication validation successful - all required tokens obtained")
            
        except Exception as e:
            logger.error(f"Authentication validation failed: {e}")
            logger.info("Clearing token cache and forcing fresh authentication...")
            
            auth_service.clear_token_cache()
            
            try:
                await auth_service.get_cognitive_services_token()
                await auth_service.get_graph_token()
                logger.info("Authentication validation successful after cache clear")
            except Exception as retry_e:
                logger.error(f"Authentication validation failed even after cache clear: {retry_e}")
                raise Exception(f"Authentication system not ready: {retry_e}") from retry_e

    def _create_azure_chat_client(self, model_config: ModelConfiguration) -> AzureOpenAIChatClient:
        """Create Azure OpenAI chat client for Agent Framework
        
        Uses the same WAM credential from auth_service to maintain authentication
        consistency across both Autogen and Agent Framework implementations.
        """
        # Use the WAM credential from auth_service for consistent authentication
        # This matches the pattern used in autogen_service.py
        return AzureOpenAIChatClient(
            endpoint=model_config.azure_endpoint,
            deployment_name=model_config.azure_deployment,
            api_version=model_config.api_version,
            credential=auth_service.wam_credential
        )
    
    async def _discover_mcp_tools(self) -> list[Callable[..., Awaitable[str]]]:
        """Discover and create tools from the MCP servers with Instructions MCP as primary source
        
        Returns a list of async functions that can be used as tools
        in the Agent Framework's function calling system.
        
        Tool Priority:
        1. Instructions MCP tools (scenario management)
        2. Data Warehouse MCP tools (historical device/user data via OData API)
           - 4 MCP tools: list_entities, get_entity_schema, query_entity, execute_odata_query
           - 1 helper: find_device_by_id (client-side filtering workaround for API limitations)
        3. Kusto MCP execute_query only (real-time event query execution)
        4. lookup_context (conversation state)
        """
        tools: list[Callable[..., Awaitable[str]]] = []
        
        # Primary: Instructions MCP tools (scenario management)
        try:
            from services.instructions_mcp_service import get_instructions_service
            instructions_service = await get_instructions_service()
            
            if hasattr(instructions_service, '_session') and instructions_service._session:
                inst_tool_list = await instructions_service._session.list_tools()
                inst_tools = getattr(inst_tool_list, "tools", [])
                
                # Add Instructions MCP tools FIRST (higher priority)
                # Skip validate_placeholders - substitute_and_get_query auto-validates
                for tool in inst_tools:
                    tool_name = getattr(tool, "name", "unknown")
                    
                    # Skip validate_placeholders - it's redundant since substitute_and_get_query
                    # validates by default (validate=True). This prevents the agent from making
                    # 2-3 failed attempts at calling validate_placeholders with wrong parameters.
                    if tool_name == "validate_placeholders":
                        logger.info(f"Skipping {tool_name} - auto-validation handled by substitute_and_get_query")
                        continue
                    
                    tool_desc = getattr(tool, "description", "No description")
                    tool_func = create_instructions_mcp_tool_function(tool_name, tool_desc)
                    tools.append(tool_func)
                    logger.info(f"Added Instructions MCP tool: {tool_name}")
            else:
                logger.warning("Instructions MCP session not available")
        except Exception as e:
            logger.error(f"Failed to load Instructions MCP tools: {e}")
        
        # Secondary: Data Warehouse MCP tools (historical baseline data)
        try:
            from services.datawarehouse_mcp_service import get_datawarehouse_service
            datawarehouse_service = await get_datawarehouse_service()
            
            if hasattr(datawarehouse_service, '_session') and datawarehouse_service._session:
                dw_tool_list = await datawarehouse_service._session.list_tools()
                dw_tools = getattr(dw_tool_list, "tools", [])
                
                # Add all Data Warehouse MCP tools
                for tool in dw_tools:
                    tool_name = getattr(tool, "name", "unknown")
                    tool_desc = getattr(tool, "description", "No description")
                    tool_func = create_datawarehouse_mcp_tool_function(tool_name, tool_desc)
                    tools.append(tool_func)
                    logger.info(f"Added Data Warehouse MCP tool: {tool_name}")
                
                # Add helper method: find_device_by_id (client-side filtering workaround)
                async def find_device_by_id(device_id: str, max_results: int = 100) -> str:
                    """
                    Find a device by deviceId using client-side filtering.
                    
                    This is a workaround for the Data Warehouse API limitation where $filter parameter
                    causes HTTP 400 errors. Fetches devices and filters client-side.
                    
                    Args:
                        device_id: The device GUID to search for
                        max_results: Maximum devices to search (default: 100)
                        
                    Returns:
                        JSON string with device data if found, or error if not found
                    """
                    try:
                        result = await datawarehouse_service.find_device_by_id(device_id, max_results)
                        
                        if result.get("success") and result.get("data", {}).get("found"):
                            device = result["data"]["device"]
                            return json.dumps({
                                "success": True,
                                "device": device,
                                "message": f"Found device: {device.get('deviceName', 'Unknown')}"
                            }, indent=2)
                        elif result.get("success"):
                            searched = result.get("data", {}).get("searched", 0)
                            return json.dumps({
                                "success": False,
                                "error": f"Device {device_id} not found in first {searched} devices",
                                "suggestion": "Try increasing max_results or verify device ID is correct"
                            }, indent=2)
                        else:
                            return json.dumps(result, indent=2)
                    except Exception as e:
                        logger.error(f"find_device_by_id failed: {e}")
                        return json.dumps({"success": False, "error": str(e)})
                
                tools.append(find_device_by_id)
                logger.info(f"Added Data Warehouse helper tool: find_device_by_id")
            else:
                logger.warning("Data Warehouse MCP session not available")
        except Exception as e:
            logger.error(f"Failed to load Data Warehouse MCP tools: {e}")
        
        # Tertiary: Kusto MCP for query execution only (real-time events)
        try:
            from services.kusto_mcp_service import get_kusto_service
            kusto_service = await get_kusto_service()
            
            if hasattr(kusto_service, '_session') and kusto_service._session:
                # Only add execute_query from Kusto MCP
                execute_func = create_mcp_tool_function("execute_query", 
                    "Execute a Kusto query. Use ONLY with queries from substitute_and_get_query.")
                tools.append(execute_func)
                logger.info("Added execute_query tool from Kusto MCP")
            else:
                logger.warning("Kusto MCP session not available")
        except Exception as e:
            logger.error(f"Failed to load Kusto MCP: {e}")
        
        # Add context lookup (but not scenario lookup - Instructions MCP handles that)
        context_func = create_context_lookup_function()
        tools.append(context_func)
        logger.info("Added lookup_context tool for conversation state access")
        
        logger.info(f"Total tools registered: {len(tools)}")
        return tools
    
    async def create_intune_expert_agent(self, model_config: ModelConfiguration) -> ChatAgent:
        """Create the IntuneExpert agent using Agent Framework
        
        This creates a ChatAgent with the same capabilities as the Autogen
        AssistantAgent, including MCP tools and scenario lookup.
        """
        logger.info("Creating Intune Expert agent with Kusto MCP tools (Agent Framework)")
        
        # Create the Azure OpenAI chat client
        chat_client = self._create_azure_chat_client(model_config)
        
        # SIMPLIFIED system instructions - focus on workflow, not anti-patterns
        system_instructions = """You are an Intune Expert assistant specializing in Microsoft Intune diagnostics.

Your primary role is to execute queries to retrieve and analyze Intune device information using two data sources:
1. Data Warehouse API - For historical baseline data (devices, users, apps, policies) updated daily
2. Kusto queries - For real-time event data and telemetry

WORKFLOW:
1. Use search_scenarios(query) to find relevant scenarios
2. Use get_scenario(slug) to get scenario details with steps
3. For each step in order:
   - If step uses Data Warehouse: Use query_entity() with appropriate filters
   - If step uses Kusto: Use substitute_and_get_query() then execute_query()
4. Format results as tables and provide summary

DATA SOURCE SELECTION:
- Use Data Warehouse API for:
  * Device baseline information (deviceId, deviceName, manufacturer, model, OS version)
  * User information (userId, userPrincipalName, displayName)
  * App installation status
  * Policy compliance status
  * Historical snapshots (data refreshed daily at Midnight UTC)
  
- Use Kusto (execute_query) for:
  * Real-time events and telemetry
  * Event sequences and timelines
  * Complex joins and aggregations
  * Custom diagnostic queries

⚠️ DATA WAREHOUSE API LIMITATIONS:
The Data Warehouse API does NOT support $filter or $select OData parameters - both cause HTTP 400 errors.
Instead:
- To find a specific device: Use find_device_by_id(device_id) - NOT query_entity with filter
- To get all devices: Use query_entity(entity="devices") without filter/select parameters
- The API returns all 39 fields per device - you cannot select specific columns
- Client-side filtering is the only reliable method for single-device lookups

AVAILABLE TOOLS:
Scenario Management:
- search_scenarios: Find scenarios matching keywords
- get_scenario: Get full scenario definition  
- get_query: Get raw query text for a specific query_id
- substitute_and_get_query: Get executable query with placeholders filled and validated

Data Warehouse API (Historical Data):
- list_entities: List all available Data Warehouse entities
- get_entity_schema: Get schema/properties for an entity
- query_entity: Query entity WITHOUT filters (⚠️ $filter and $select cause HTTP 400)
- execute_odata_query: Execute raw OData query URL (advanced use only)
- find_device_by_id: Find a specific device by ID (RECOMMENDED for single device lookups)

Kusto (Real-time Data):
- execute_query: Run Kusto query (use ONLY with queries from substitute_and_get_query)

Context:
- lookup_context: Get stored values from previous queries

CRITICAL RULES:
1. Execute scenarios step by step in sequential order (1, 2, 3, ...)
2. For Kusto steps: ALWAYS call substitute_and_get_query AND execute_query - both required
3. Getting a query with substitute_and_get_query is NOT execution - you must call execute_query next
4. For Data Warehouse device lookups: ALWAYS use find_device_by_id(device_id) - NEVER query_entity with filter
5. For Data Warehouse bulk queries: Use query_entity(entity) without $filter or $select parameters
6. NEVER pass filter= or select= parameters to query_entity - they cause HTTP 400 errors
7. Don't write your own Kusto queries - use exact queries from substitute_and_get_query
8. substitute_and_get_query validates automatically - don't call separate validation
9. After completing ALL steps (every execute_query call), format results and provide summary
10. Present results as formatted markdown tables

⚠️ SCENARIO COMPLETION SIGNAL (MANDATORY):
When you have completed ALL steps in a scenario and provided the summary:
- End your response with the exact marker: **[SCENARIO_COMPLETE]**
- This marker MUST appear on its own line at the very end of your response
- Do NOT add this marker until ALL steps are executed and results are formatted
- The orchestrator uses this marker to detect completion and stop the workflow
- Example:
  
  (... tables and summary here ...)
  
  **[SCENARIO_COMPLETE]**

PLACEHOLDER HANDLING:
- Always use PascalCase: DeviceId, StartTime, EndTime, EffectiveGroupIdList
- Call lookup_context() if you need values from previous queries
- Pass all placeholders to substitute_and_get_query as a dictionary
- If substitute_and_get_query returns validation errors, fix the values and retry

EXAMPLE WORKFLOW (Data Warehouse + Kusto):
1. search_scenarios(query="device timeline") → Get slug
2. get_scenario(slug="device-timeline") → Get steps array (returns 5 steps)
3. Step 1 (Data Warehouse - Device Baseline):
   - find_device_by_id(device_id="abc123") → Returns device with all 39 fields
4. Step 2 (Kusto - Events):
   - substitute_and_get_query(query_id="device-timeline_step2", placeholder_values={"DeviceId": "abc123"})
   - execute_query(query="<returned query>") ← REQUIRED - don't skip this
5. Step 3 (Kusto - Events):
   - substitute_and_get_query(query_id="device-timeline_step3", placeholder_values={"DeviceId": "abc123"})
   - execute_query(query="<returned query>") ← REQUIRED - don't skip this
6. Step 4 (Kusto - Events):
   - substitute_and_get_query(query_id="device-timeline_step4", placeholder_values={"DeviceId": "abc123"})
   - execute_query(query="<returned query>") ← REQUIRED - don't skip this
7. Step 5 (Kusto - Events):
   - substitute_and_get_query(query_id="device-timeline_step5", placeholder_values={"PolicyIdList": "..."})
   - execute_query(query="<returned query>") ← REQUIRED - don't skip this
8. After ALL execute_query calls complete, format all results and provide summary
"""
        
        # Discover and create tools from MCP server
        tools = await self._discover_mcp_tools()
        
        # Create the agent with tools
        agent = ChatAgent(
            chat_client=chat_client,
            instructions=system_instructions,
            tools=tools
        )
        
        logger.info("IntuneExpert agent created successfully with Kusto tools (Agent Framework)")
        
        return agent

    # --- Post-processing helpers (same as Autogen implementation) ---------
    def _apply_speculation_filter(self, text: str, tables: list[dict[str, Any]] | None, strict: bool) -> str:
        """In strict mode, remove or flag speculative phrases if unsupported by data."""
        if not strict or not text:
            return text
        speculative_markers = ["likely", "probably", "possible", "might", "inferred", "it is probable"]
        has_data = bool(tables)
        lines = text.split('\n')
        cleaned: list[str] = []
        for line in lines:
            lower = line.lower()
            if any(tok in lower for tok in speculative_markers):
                if not has_data:
                    continue
                else:
                    line += "  (Speculative wording trimmed under strict mode; verify with actual query results.)"
            cleaned.append(line)
        result = '\n'.join(cleaned).strip()
        if not result:
            return "(Strict mode removed speculative content; no factual data returned.)"
        return result

    def _extract_json_objects(self, text: str) -> list[Any]:
        """Extract multiple JSON objects/lists from arbitrary concatenated text."""
        results: list[Any] = []
        if not text or ('{' not in text and '[' not in text):
            return results
        start_idx: int | None = None
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text):
            if start_idx is None:
                if ch in '{[':
                    start_idx = i
                    depth = 1
                    in_string = False
                    escape = False
                continue
            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch in '{[':
                    depth += 1
                elif ch in '}]':
                    depth -= 1
                    if depth == 0 and start_idx is not None:
                        candidate = text[start_idx:i+1].strip()
                        try:
                            results.append(json.loads(candidate))
                        except Exception:
                            pass
                        start_idx = None
            if start_idx is not None and (i - start_idx) > 200_000:
                start_idx = None
        return results

    def _clean_summary_from_json(self, text: str) -> str:
        """Remove raw JSON objects and markdown tables from text to create a clean natural language summary.
        
        This prevents the AI summary from displaying garbled table data that's already
        being shown in the Kusto Query Results table below.
        """
        if not text:
            return text
        
        import re
        cleaned = text
        
        # Step 1: Remove markdown tables (lines with | separators)
        # A markdown table has:
        # - Header row with | separators
        # - Separator row with |---|---| pattern
        # - Data rows with | separators
        
        # Remove entire markdown table blocks
        # This regex matches from a table header through all table rows
        markdown_table_pattern = r'\n?\s*\|[^\n]+\|\s*\n\s*\|[\s\-:|]+\|\s*\n(?:\s*\|[^\n]+\|\s*\n)+'
        cleaned = re.sub(markdown_table_pattern, '\n', cleaned)
        
        # Also remove standalone table rows that might remain
        cleaned = re.sub(r'\n\s*\|[^\n]+\|\s*\n', '\n', cleaned)
        
        # Step 2: Remove markdown table headers/titles (e.g., "**Device Details Table**")
        cleaned = re.sub(r'\*\*[^*]*Table\*\*\s*\n?', '', cleaned, flags=re.IGNORECASE)
        
        # Step 3: Remove JSON objects
        if '{' in cleaned or '[' in cleaned:
            # Track JSON object positions to remove
            start_idx: int | None = None
            depth = 0
            in_string = False
            escape = False
            json_ranges: list[tuple[int, int]] = []
            
            for i, ch in enumerate(cleaned):
                if start_idx is None:
                    if ch in '{[':
                        start_idx = i
                        depth = 1
                        in_string = False
                        escape = False
                    continue
                if in_string:
                    if escape:
                        escape = False
                    elif ch == '\\':
                        escape = True
                    elif ch == '"':
                        in_string = False
                else:
                    if ch == '"':
                        in_string = True
                    elif ch in '{[':
                        depth += 1
                    elif ch in '}]':
                        depth -= 1
                        if depth == 0 and start_idx is not None:
                            # Found complete JSON object - mark for removal
                            json_ranges.append((start_idx, i + 1))
                            start_idx = None
                if start_idx is not None and (i - start_idx) > 200_000:
                    start_idx = None
            
            # Build cleaned text by excluding JSON ranges
            if json_ranges:
                cleaned_parts = []
                last_end = 0
                for start, end in json_ranges:
                    if start > last_end:
                        cleaned_parts.append(cleaned[last_end:start])
                    last_end = end
                if last_end < len(cleaned):
                    cleaned_parts.append(cleaned[last_end:])
                
                cleaned = ''.join(cleaned_parts)
        
        # Step 4: Clean up formatting
        # Remove multiple consecutive newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # Remove leading/trailing whitespace
        cleaned = cleaned.strip()
        
        # Remove empty bullet points or list markers that might be left over
        cleaned = re.sub(r'\n\s*[-*]\s*\n', '\n', cleaned)
        
        return cleaned

    def _normalize_table_objects(self, objs: list[Any]) -> list[dict[str, Any]]:
        """Normalize heterogeneous JSON shapes into table dictionaries."""
        tables: list[dict[str, Any]] = []
        def add(columns: list[Any], rows: list[list[Any]], total_rows: int | None = None, name: str | None = None):
            tbl: dict[str, Any] = {
                'columns': columns,
                'rows': rows,
                'total_rows': total_rows if total_rows is not None else len(rows)
            }
            if name:
                tbl['name'] = name
            tables.append(tbl)

        def from_data_rows(obj: dict[str, Any]):
            data_rows_any = obj.get('data')
            if isinstance(data_rows_any, list) and data_rows_any and all(isinstance(r, dict) for r in data_rows_any):
                columns: list[str] = []
                for r in data_rows_any:
                    for k in r.keys():
                        if k not in columns:
                            columns.append(k)
                row_matrix = [[str(r.get(c, '')) for c in columns] for r in data_rows_any]
                add(columns, row_matrix, name=str(obj.get('name')) if obj.get('name') else None)

        queue: list[Any] = list(objs)
        while queue:
            obj = queue.pop(0)
            if isinstance(obj, list):
                queue[:0] = obj
                continue
            if not isinstance(obj, dict):
                continue
            if 'table' in obj and isinstance(obj['table'], dict):
                tbl = obj['table']
                if all(k in tbl for k in ('columns', 'rows')):
                    add(tbl.get('columns', []), tbl.get('rows', []), tbl.get('total_rows'), name=str(obj.get('name')) if obj.get('name') else None)
            if 'columns' in obj and 'rows' in obj and isinstance(obj.get('columns'), list):
                add(obj.get('columns', []), obj.get('rows', []), obj.get('total_rows'), name=str(obj.get('name')) if obj.get('name') else None)
            if 'data' in obj and isinstance(obj.get('data'), list):
                from_data_rows(obj)
        return tables

    def _dedupe_tables(self, tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicate tables based on structure signature."""
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for t in tables:
            name = t.get('name') or ''
            sig = f"{name}:{tuple(t.get('columns', []))}:{len(t.get('rows', []))}"
            if sig not in seen:
                seen.add(sig)
                unique.append(t)
        return unique

    async def _magentic_event_callback(self, event: MagenticCallbackEvent) -> None:
        """Handle Magentic Team callback events and log them to console.
        
        This callback receives all orchestrator and agent messages during workflow execution,
        providing visibility into the multi-agent conversation and tracking scenario execution state.
        
        Args:
            event: One of MagenticOrchestratorMessageEvent, MagenticAgentDeltaEvent,
                   MagenticAgentMessageEvent, or MagenticFinalResultEvent
        """
        try:
            from services.scenario_state import scenario_tracker
            
            if isinstance(event, MagenticOrchestratorMessageEvent):
                # Orchestrator messages (planning, task ledger, instructions, notices)
                message = getattr(event, 'message', None)
                kind = getattr(event, 'kind', 'unknown')
                
                if message:
                    message_text = getattr(message, 'text', '')
                    truncated = message_text[:300] + "..." if len(message_text) > 300 else message_text
                    logger.info(f"[Magentic-Orchestrator] [{kind}] {truncated}")
            
            elif isinstance(event, MagenticAgentDeltaEvent):
                # Agent streaming deltas (real-time response chunks)
                agent_id = getattr(event, 'agent_id', 'agent')
                text = getattr(event, 'text', '')
                role = getattr(event, 'role', None)
                
                # Log function calls if present
                fn_call_name = getattr(event, 'function_call_name', None)
                fn_result_id = getattr(event, 'function_result_id', None)
                fn_result = getattr(event, 'function_result', None)
                
                if fn_call_name:
                    logger.info(f"[Magentic-Agent-{agent_id}] Function call: {fn_call_name}")
                    
                    # Track scenario initialization
                    if fn_call_name == "get_scenario" and fn_result:
                        try:
                            result_data = json.loads(fn_result) if isinstance(fn_result, str) else fn_result
                            if isinstance(result_data, dict) and 'steps' in result_data:
                                slug = result_data.get('slug', 'unknown')
                                scenario_tracker.start_scenario(slug, result_data['steps'])
                                logger.info(f"Initialized tracking for scenario: {slug} with {len(result_data['steps'])} steps")
                        except Exception as e:
                            logger.error(f"Failed to parse scenario from get_scenario result: {e}")
                    
                    # Track step completion
                    elif fn_call_name == "execute_query" and fn_result:
                        scenario = scenario_tracker.get_active_scenario()
                        if scenario:
                            next_step = scenario.get_next_pending_step()
                            if next_step:
                                scenario.mark_step_complete(next_step.step_number, fn_result)
                                logger.info(f"Marked step {next_step.step_number} complete - {scenario.get_progress_summary()}")
                                
                                # Store result in buffer for table extraction
                                if isinstance(fn_result, str):
                                    try:
                                        result_obj = json.loads(fn_result)
                                        if isinstance(result_obj, dict) and result_obj.get('success') and 'table' in result_obj:
                                            TOOL_RESULTS_BUFFER.append(result_obj)
                                            logger.debug(f"Added query result to buffer (total: {len(TOOL_RESULTS_BUFFER)})")
                                    except Exception:
                                        pass
                
                elif fn_result_id:
                    logger.info(f"[Magentic-Agent-{agent_id}] Function result received")
                elif text:
                    logger.info(f"[Magentic-Agent-{agent_id}] ({role}): {text[:100]}")
            
            elif isinstance(event, MagenticAgentMessageEvent):
                # Complete agent message (final aggregated response)
                agent_id = getattr(event, 'agent_id', 'agent')
                message = getattr(event, 'message', None)
                
                if message:
                    message_text = getattr(message, 'text', '')
                    role = getattr(message, 'role', 'unknown')
                    truncated = message_text[:300] + "..." if len(message_text) > 300 else message_text
                    logger.info(f"[Magentic-Agent-{agent_id}] ({role}) Final: {truncated}")
            
            elif isinstance(event, MagenticFinalResultEvent):
                # Final workflow result
                message = getattr(event, 'message', None)
                if message:
                    message_text = getattr(message, 'text', '')
                    truncated = message_text[:300] + "..." if len(message_text) > 300 else message_text
                    logger.info(f"[Magentic-FinalResult] {truncated}")
                
                # Log final scenario progress
                scenario = scenario_tracker.get_active_scenario()
                if scenario:
                    logger.info(f"[Workflow] Scenario completion: {scenario.get_progress_summary()}")
        
        except Exception as callback_err:
            logger.warning(f"Magentic event callback error: {callback_err}")

    async def setup_agent(self, model_config: ModelConfiguration) -> bool:
        """Set up the Agent Framework with Magentic orchestration"""
        try:
            logger.info(f"Setting up Agent Framework with Magentic orchestration - model: {model_config.model_name}")
            
            # Store the chat client for the orchestrator
            self.chat_client = self._create_azure_chat_client(model_config)
            
            # Create the IntuneExpert agent with tools
            self.intune_expert_agent = await self.create_intune_expert_agent(model_config)
            
            # Build the Magentic workflow with orchestration
            # This is equivalent to Autogen's MagenticOneGroupChat
            logger.info("Building Magentic workflow with IntuneExpert agent...")
            
            # Custom progress ledger prompt that checks for scenario completion marker
            custom_progress_prompt = """Recall we are working on the following request:
{task}

And we have assembled the following team:
{team}

To make progress on the request, please answer the following questions, including necessary reasoning:

- Is the request fully satisfied? 
  * Check if the agent's last response contains the marker **[SCENARIO_COMPLETE]**
  * If the marker is present, the request IS satisfied (answer True)
  * If the marker is NOT present but the agent has executed all scenario steps and provided results, the request may still be satisfied
  * If work is still in progress or no results have been provided, answer False

- Are we in a loop where we are repeating the same requests and/or getting the same responses?
  * Check if search_scenarios or get_scenario was called multiple times
  * Check if the same steps are being executed repeatedly
  * If yes, answer True

- Are we making forward progress?
  * True if recent messages show new query executions or results
  * False if stuck, repeating, or getting errors

- Who should speak next? (select from: {names})
  * If request is satisfied, you can select any agent (the workflow will end anyway)
  * Otherwise select the agent best suited to continue the work

- What instruction or question would you give this team member?
  * If request is satisfied, say "Task complete - no further action needed"
  * Otherwise provide specific next steps

Please output an answer in pure JSON format according to the following schema. The JSON object must be parsable as-is.
DO NOT OUTPUT ANYTHING OTHER THAN JSON, AND DO NOT DEVIATE FROM THIS SCHEMA:

{{
    "is_request_satisfied": {{
        "reason": string,
        "answer": boolean
    }},
    "is_in_loop": {{
        "reason": string,
        "answer": boolean
    }},
    "is_progress_being_made": {{
        "reason": string,
        "answer": boolean
    }},
    "next_speaker": {{
        "reason": string,
        "answer": string (select from: {names})
    }},
    "instruction_or_question": {{
        "reason": string,
        "answer": string
    }}
}}"""
            
            self.magentic_workflow = (
                MagenticBuilder()
                .participants(IntuneExpert=self.intune_expert_agent)
                .with_standard_manager(
                    chat_client=self.chat_client,
                    max_round_count=30,  # Reduced from 50 - prevents excessive looping (device-timeline has 4 steps)
                    max_stall_count=3,   # Reduced from 5 - fail faster if stuck
                    progress_ledger_prompt=custom_progress_prompt,  # Custom prompt that checks for [SCENARIO_COMPLETE]
                )
                .build()
            )
            
            # Initialize MCP services
            try:
                from services.instructions_mcp_service import get_instructions_service
                from services.kusto_mcp_service import get_kusto_service
                
                # Initialize Instructions MCP first (provides scenario queries)
                instructions_service = await get_instructions_service()
                logger.info(f"Instructions MCP service initialized (tools={getattr(instructions_service, '_tool_names', [])})")
                
                # Initialize Kusto MCP (executes queries)
                kusto_service = await get_kusto_service()
                logger.info(f"Kusto MCP service initialized (tools={getattr(kusto_service, '_tool_names', [])})")
            except Exception as mcp_err:
                logger.error(f"Failed to initialize MCP services: {mcp_err}")
                raise
            
            logger.info("Agent Framework with Magentic orchestration setup completed successfully")
            return True
            
        except Exception as e:
            error_msg = f"Failed to setup Agent Framework: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    def _build_placeholder_values(self, parameters: dict[str, Any], context_values: dict[str, Any]) -> dict[str, Any]:
        """Build complete placeholder values with proper PascalCase conversion.
        
        This ensures that all placeholder names match the expected format in the MCP server,
        regardless of whether they come from API parameters (snake_case) or context (snake_case).
        
        Args:
            parameters: Initial parameters from the API request
            context_values: Values from conversation state (lookup_context)
            
        Returns:
            Dictionary with all placeholders in PascalCase format
        """
        placeholder_values: dict[str, Any] = {}

        # Add initial parameters with PascalCase conversion
        for key, value in parameters.items():
            pascal_key = ''.join(word.capitalize() for word in key.split('_'))
            normalized_value = _normalize_placeholder_value(pascal_key, value)
            placeholder_values[pascal_key] = normalized_value
        
        # Add context values with proper case mapping
        # Map snake_case context keys to PascalCase placeholder names
        context_mapping = {
            'device_id': 'DeviceId',
            'account_id': 'AccountId',
            'context_id': 'ContextId',
            'tenant_id': 'TenantId',
            'user_id': 'UserId',
            'scale_unit_name': 'ScaleUnitName',
            'serial_number': 'SerialNumber',
            'device_name': 'DeviceName',
            'azure_ad_device_id': 'AzureAdDeviceId',
            'primary_user': 'PrimaryUser',
            'enrolled_by_user': 'EnrolledByUser',
            'start_time': 'StartTime',
            'end_time': 'EndTime',
            # List-based identifiers (critical for multi-step scenarios)
            'effective_group_id_list': 'EffectiveGroupIdList',
            'group_id_list': 'GroupIdList',
            'policy_id_list': 'PolicyIdList'
        }
        
        for context_key, context_value in context_values.items():
            if context_value is not None:
                pascal_key = context_mapping.get(context_key,
                    ''.join(word.capitalize() for word in context_key.split('_')))
                # Don't override if already set from parameters
                if pascal_key not in placeholder_values:
                    placeholder_values[pascal_key] = _normalize_placeholder_value(pascal_key, context_value)
        
        logger.info(f"[AgentFramework] Built placeholder values with {len(placeholder_values)} keys: {list(placeholder_values.keys())}")
        
        return placeholder_values

    async def query_diagnostics(self, query_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute diagnostic query through the Magentic workflow orchestration
        
        Simplified version that focuses on clear instructions and state tracking.
        """
        if not self.magentic_workflow:
            raise Exception("Magentic workflow not initialized")
        
        try:
            from services.scenario_state import scenario_tracker
            
            logger.info(f"Executing diagnostic query: {query_type}")
            
            # Clear state and buffers for fresh execution
            TOOL_RESULTS_BUFFER.clear()
            scenario_tracker.clear_scenario()
            
            from services.conversation_state import get_conversation_state_service
            context_service = get_conversation_state_service()
            # Reset conversation context so each diagnostics run starts clean with user-provided parameters
            context_service.start_new_run(parameters)

            # Handle scenario execution directly
            if query_type == "scenario":
                scenario_ref = parameters.get("scenario") or parameters.get("name") or parameters.get("index")
                if scenario_ref is None:
                    raise Exception("Parameter 'scenario' is required for scenario execution")
                try:
                    scenario_ref_val: int | str
                    if isinstance(scenario_ref, str) and scenario_ref.isdigit():
                        scenario_ref_val = int(scenario_ref)
                    else:
                        scenario_ref_val = str(scenario_ref)
                except ValueError:
                    scenario_ref_val = str(scenario_ref)
                scenario_run = await self.run_instruction_scenario(scenario_ref_val)
                return {
                    "query_type": "scenario",
                    "scenario": scenario_run.get("scenario"),
                    "description": scenario_run.get("description"),
                    "parameters": parameters,
                    "tables": scenario_run.get("tables", []),
                    "summary": scenario_run.get("summary"),
                    "errors": scenario_run.get("errors", []),
                }
            
            # Get all available context values
            context_values = context_service.get_all_context()
            
            logger.info(f"[AgentFramework] Available context values: {list(context_values.keys())}")
            
            # Build complete placeholder values with proper PascalCase conversion
            all_placeholder_values = self._build_placeholder_values(parameters, context_values)
            
            # Create JSON representation for instructions
            placeholder_str = json.dumps(all_placeholder_values, indent=2)
            
            # Normalize query_type for search
            normalized_query_type = query_type.replace('_', '-')
            
            # Specialized guidance for device timeline scenarios (mermaid output)
            device_timeline_guidance = ""
            if normalized_query_type in {"device-timeline", "device_timeline"}:
                device_id = all_placeholder_values.get('DeviceId', 'DEVICE_ID')
                start_time = all_placeholder_values.get('StartTime', 'START_TIME')
                end_time = all_placeholder_values.get('EndTime', 'END_TIME')
                device_timeline_guidance = (
                    "\nSpecial Instructions for Device Timeline:\n"
                    "You are an Intune diagnostics expert. Build a chronological device event timeline covering compliance status changes, policy assignment or evaluation outcomes, application install attempts (success/failure), device check-ins (including failures or long gaps), enrollment/sync events, and notable error events for the specified device and time window.\n"
                    "IMPORTANT: This scenario contains 4 steps. Ensure you complete all steps in this scenario.\n"
                    "1. Discover and aggregate relevant events via available tools / queries.\n"
                    "2. Normalize timestamps to UTC ISO8601 (YYYY-MM-DD HH:MM).\n"
                    "3. Group logically similar rapid events but keep important state transitions explicit.\n"
                    "4. Output a concise narrative summary first (outside code fence).\n"
                    "5. Then output EXACTLY ONE fenced mermaid code block using the simple timeline syntax (NOT gantt):\n"
                    "```mermaid\n"
                    f"Title: Device Timeline ({device_id})\n"
                    f"Start: <earliest timestamp in YYYY-MM-DD HH:MM format>\n"
                    "<YYYY-MM-DD HH:MM>: <Category> - <Brief description>\n"
                    "<YYYY-MM-DD HH:MM>: <Category> - <Brief description>\n"
                    "...\n"
                    "```\n"
                    "Rules:\n"
                    "- Use the simple timeline format shown above - do NOT use gantt syntax, sections, or milestones.\n"
                    "- Each event line format: timestamp: Category - Description\n"
                    "- Do not include any other fenced mermaid blocks.\n"
                    "- Categories: Compliance, Policy, App, Check-in, Error, Enrollment, Other.\n"
                    "- If no events found, still return an empty timeline code block with a 'No significant events' note.\n"
                    f"Parameters: device_id={device_id}, start_time={start_time}, end_time={end_time}. Return the narrative summary first, then the mermaid block.\n"
                )

            # EXPLICIT query message - prevents orchestrator loop
            base_query_message = f"""Execute the COMPLETE '{query_type}' scenario with these parameters:
{placeholder_str}

CRITICAL WORKFLOW (Execute Once, Do NOT Restart):
1. Call search_scenarios(query="{normalized_query_type}") ONCE at the beginning
2. Call get_scenario(slug) ONCE to get scenario details
3. Execute ALL scenario steps sequentially (step 1, 2, 3, 4, etc. until complete)
   - Data Warehouse steps: Call find_device_by_id() or query_entity() as appropriate
   - Kusto steps: Call substitute_and_get_query() then execute_query() - BOTH required
   - Continue through ALL steps without stopping
4. After executing the FINAL step, format results and output **[SCENARIO_COMPLETE]** marker

EXECUTION RULES:
- search_scenarios is ONLY called ONCE at the start - never call it again
- get_scenario is ONLY called ONCE after search_scenarios - never call it again
- Each Kusto step needs substitute_and_get_query AND execute_query - both are required
- substitute_and_get_query only RETRIEVES the query text - it does NOT execute anything
- execute_query is the ONLY tool that actually runs the query and returns data
- A step is NOT complete until execute_query returns results
- Execute ALL scenario steps in one continuous sequence - do NOT restart the scenario
- After the LAST execute_query call completes, you MUST output **[SCENARIO_COMPLETE]** marker

⚠️ SCENARIO COMPLETION SIGNAL (MANDATORY) ⚠️
After you execute the LAST step and format the results, you MUST end your response with:

**[SCENARIO_COMPLETE]**

This marker tells the orchestrator to stop. Without it, the orchestrator will keep looping.
The marker must appear on its own line at the very end of your response.

Do NOT say "I will now execute" - just execute by calling the tools.
Actions speak louder than words - call the tools, don't announce them."""
            query_message = base_query_message + device_timeline_guidance
            
            # Run the Magentic workflow with streaming
            logger.info(f"[Magentic] Running workflow for {query_type}")
            response_content = ""
            tables = []
            scenario_complete = False  # Track completion marker
            
            # Import event types for proper type checking
            from agent_framework._workflows._magentic import (
                MagenticOrchestratorMessageEvent,
                MagenticAgentDeltaEvent,
                MagenticAgentMessageEvent,
                MagenticFinalResultEvent,
            )
            
            async for event in self.magentic_workflow.run_stream(query_message):
                # Log orchestrator messages (task, ledger, instructions, notices)
                if isinstance(event, MagenticOrchestratorMessageEvent):
                    message = getattr(event, 'message', None)
                    kind = getattr(event, 'kind', 'unknown')
                    if message:
                        message_text = getattr(message, 'text', '')
                        truncated = message_text[:300] + "..." if len(message_text) > 300 else message_text
                        logger.info(f"[Magentic-Orchestrator] [{kind}] {truncated}")
                
                # Log agent streaming deltas
                elif isinstance(event, MagenticAgentDeltaEvent):
                    agent_id = getattr(event, 'agent_id', 'agent')
                    text = getattr(event, 'text', '')
                    fn_call_name = getattr(event, 'function_call_name', None)
                    
                    if fn_call_name:
                        logger.info(f"[Magentic-Agent-{agent_id}] Function call: {fn_call_name}")
                    elif text:
                        # Only log first 100 chars of streaming text to avoid spam
                        logger.debug(f"[Magentic-Agent-{agent_id}] {text[:100]}")
                
                # Log complete agent messages AND check for completion marker
                elif isinstance(event, MagenticAgentMessageEvent):
                    agent_id = getattr(event, 'agent_id', 'agent')
                    message = getattr(event, 'message', None)
                    if message:
                        message_text = getattr(message, 'text', '')
                        truncated = message_text[:300] + "..." if len(message_text) > 300 else message_text
                        logger.info(f"[Magentic-Agent-{agent_id}] Complete: {truncated}")
                        
                        # Check for completion marker in agent messages
                        if "[SCENARIO_COMPLETE]" in message_text:
                            scenario_complete = True
                            response_content = message_text
                            logger.info("[Magentic] ✅ SCENARIO_COMPLETE marker detected in agent message - scenario finished successfully")
                            break  # Exit loop immediately - scenario is done
                
                # Log final result
                elif isinstance(event, MagenticFinalResultEvent):
                    message = getattr(event, 'message', None)
                    if message:
                        message_text = getattr(message, 'text', '')
                        logger.info(f"[Magentic-Final] Task completed")
                        
                        # Also check completion marker in final result
                        if "[SCENARIO_COMPLETE]" in message_text:
                            scenario_complete = True
                            response_content = message_text
                            logger.info("[Magentic] ✅ SCENARIO_COMPLETE marker detected in final result")
                            break
                
                # Capture the final output
                if isinstance(event, WorkflowOutputEvent):
                    logger.info("[Magentic] Received WorkflowOutputEvent - extracting response")
                    data = getattr(event, 'data', None)
                    extracted_text = ""
                    try:
                        if data is None:
                            extracted_text = ""
                        elif hasattr(data, 'text') and data.text:
                            extracted_text = data.text  # type: ignore[assignment]
                        elif hasattr(data, 'content') and data.content:
                            extracted_text = str(data.content)
                        elif hasattr(data, 'contents') and data.contents:
                            contents = data.contents
                            try:
                                extracted_text = " ".join(
                                    c.text for c in contents if hasattr(c, 'text') and c.text
                                )
                            except Exception:  # noqa: BLE001
                                extracted_text = ""
                            if not extracted_text:
                                extracted_text = str(data)
                        else:
                            extracted_text = str(data)
                    except Exception as extract_err:  # noqa: BLE001
                        logger.warning(f"Failed to extract text from workflow output: {extract_err}")
                        extracted_text = str(data) if data else ""
                    response_content = extracted_text
                    
                    # Check for SCENARIO_COMPLETE marker in workflow output
                    if "[SCENARIO_COMPLETE]" in extracted_text:
                        scenario_complete = True
                        logger.info("[Magentic] ✅ SCENARIO_COMPLETE marker detected in workflow output - scenario finished successfully")
                        break  # Exit loop immediately - scenario is done
            
            if scenario_complete:
                logger.info("[Magentic] Scenario completed successfully with completion marker")
            else:
                logger.warning("[Magentic] ⚠️ Workflow ended without SCENARIO_COMPLETE marker - may be incomplete")
            
            # Extract tables from buffer (populated by event callback)
            if TOOL_RESULTS_BUFFER:
                for result in TOOL_RESULTS_BUFFER:
                    if 'table' in result:
                        tables.append(result['table'])
                logger.info(f"Extracted {len(tables)} tables from buffer")
            
            # Extract mermaid timeline if present in final response
            mermaid_block: str | None = None
            if isinstance(response_content, str):
                pattern = re.compile(r"```mermaid\s+([\s\S]*?)```", re.IGNORECASE)
                match = pattern.search(response_content)
                if match:
                    mermaid_block = match.group(1).strip()
                elif "timeline" in response_content.lower():
                    lines = response_content.splitlines()
                    collected: list[str] = []
                    capture = False
                    for ln in lines:
                        if ln.strip().lower().startswith("timeline"):
                            capture = True
                            collected.append("timeline")
                            continue
                        if capture:
                            if ln.strip().startswith("```"):
                                break
                            collected.append(ln)
                    if len(collected) > 1:
                        mermaid_block = "\n".join(collected).strip()

            if mermaid_block:
                mermaid_table = {"columns": ["mermaid_timeline"], "rows": [[mermaid_block]], "total_rows": 1}
                tables.append(mermaid_table)
                response_content = f"{response_content}\n\n[Mermaid timeline extracted successfully]"

            # Clean up the summary
            summary = self._clean_summary_from_json(response_content)
            
            # Log progress
            progress = scenario_tracker.get_progress_info()
            logger.info(f"[AgentFramework] {progress}")
            
            return {
                "query_type": query_type,
                "parameters": parameters,
                "response": response_content,
                "tables": tables or None,
                "summary": summary,
                "mermaid_timeline": mermaid_block
            }
            
        except Exception as e:
            logger.error(f"Diagnostic query failed: {e}", exc_info=True)
            return {
                "query_type": query_type,
                "parameters": parameters,
                "error": str(e),
                "summary": f"Failed to execute diagnostic query: {e}"
            }

    async def chat(self, message: str, extra_parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Natural language chat interface using Magentic workflow orchestration
        
        This maintains full compatibility with the Autogen implementation's
        chat interface while using Agent Framework's Magentic orchestration.
        """
        if not self.magentic_workflow:
            raise Exception("Magentic workflow not initialized")
        
        try:
            logger.info(f"Processing chat message through Magentic orchestration: {message[:100]}...")

            # Incorporate prior conversation history
            history = []
            if extra_parameters and isinstance(extra_parameters.get("conversation_history"), list):
                raw_hist = extra_parameters.get("conversation_history")
                # Ensure raw_hist is not None before iterating
                if raw_hist:
                    for h in raw_hist:
                        if not isinstance(h, dict):
                            continue
                        role = h.get("role")
                        content = h.get("content")
                        if not (isinstance(role, str) and isinstance(content, str)):
                            continue
                        if len(content) > 4000:
                            content = content[:4000] + "... [truncated]"
                        history.append({"role": role, "content": content})

            strict_mode = bool(extra_parameters.get("strict_mode")) if extra_parameters else False

            # Build the composite task with history and guardrails
            if history:
                history_lines = []
                for turn in history:
                    role_tag = "USER" if turn["role"] == "user" else "ASSISTANT"
                    history_lines.append(f"{role_tag}: {turn['content']}")
                guardrail = """
STRICT RESPONSE CONSTRAINTS:
- ALWAYS use lookup_scenarios to find the appropriate query for the user's request
- EXECUTE the exact query from instructions.md - do not skip query execution
- Do NOT create analysis, fact sheets, or speculation - execute queries and return table results
- Only report data that comes from successful query results
- If a query fails, report the error and ask for guidance
- Use lookup_context to get stored values for placeholders in queries

TASK COMPLETION CRITERIA:
The task is COMPLETE when ALL of the following are satisfied:
1. All required queries have been executed successfully
2. Query results have been formatted and presented to the user
3. A summary or analysis has been provided based on the results
The task is NOT complete if queries are executed but no response is given to the user.
""" if strict_mode else """
TASK COMPLETION CRITERIA:
The task is COMPLETE when:
1. All necessary information has been gathered
2. Results have been formatted and presented to the user
3. A clear response addressing the user's request has been provided
The task is NOT complete until a user-facing response is given.
"""
                composite_task = (
                    ("The following is the prior conversation (most recent last). Use it to maintain context such as referenced device IDs or other identifiers.\n" + "\n".join(history_lines) + "\n\n")
                    + (guardrail)
                    + "New USER message: " + message + "\nRespond taking earlier context into account."
                )
            else:
                if strict_mode:
                    composite_task = (
                        "STRICT RESPONSE MODE:\n" 
                        "- ALWAYS start by calling lookup_scenarios with the user's request\n"
                        "- EXECUTE the queries returned by lookup_scenarios - do not skip execution\n"
                        "- Use lookup_context to get stored values if queries have placeholders\n"
                        "- Only return factual data from query results, no speculation\n\n"
                        f"User message: {message}\n\n"
                        "TASK COMPLETION CRITERIA:\n"
                        "The task is COMPLETE when ALL of the following are satisfied:\n"
                        "1. All required queries have been executed successfully\n"
                        "2. Query results have been formatted and presented to the user\n"
                        "3. A summary or analysis has been provided based on the results\n"
                        "The task is NOT complete if queries are executed but no response is given to the user."
                    )
                else:
                    composite_task = (
                        f"{message}\n\n"
                        "TASK COMPLETION CRITERIA:\n"
                        "The task is COMPLETE when:\n"
                        "1. All necessary information has been gathered (queries executed if needed)\n"
                        "2. Results have been formatted and presented to the user\n"
                        "3. A clear response addressing the user's request has been provided\n"
                        "The task is NOT complete until a user-facing response is given."
                    )

            # Run the Magentic workflow with streaming
            logger.info(f"[Magentic] Running workflow with message: {composite_task[:100]}...")
            response_content = ""
            TOOL_RESULTS_BUFFER.clear()
            extracted_objs = []
            
            async for event in self.magentic_workflow.run_stream(composite_task):
                # Log orchestrator and agent events for debugging
                if hasattr(event, '__class__'):
                    event_type = event.__class__.__name__
                    logger.info(f"[Magentic] Received event: {event_type}")
                    
                    # Log message content for debugging the conversation
                    if hasattr(event, 'message'):
                        msg = getattr(event, 'message', None)
                        if msg:
                            # Log sender if available
                            sender = getattr(msg, 'sender', 'unknown')
                            role = getattr(msg, 'role', 'unknown')
                            
                            # Extract text content
                            msg_text = ""
                            if hasattr(msg, 'text') and msg.text:
                                msg_text = msg.text
                            elif hasattr(msg, 'contents') and msg.contents:
                                contents = msg.contents
                                text_parts = []
                                for c in contents:
                                    if hasattr(c, 'text') and c.text:
                                        text_parts.append(str(c.text))
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
                
                # Capture the final output
                if isinstance(event, WorkflowOutputEvent):
                    logger.info("[Magentic] Received WorkflowOutputEvent - task completed")
                    # Robust extraction of textual content from Agent Framework objects
                    data = getattr(event, 'data', None)
                    extracted_text = ""
                    try:
                        if data is None:
                            extracted_text = ""
                        elif hasattr(data, 'text') and data.text:
                            extracted_text = data.text  # ChatResponse or ChatMessage.text
                        elif hasattr(data, 'content') and data.content:
                            extracted_text = str(data.content)
                        elif hasattr(data, 'contents') and data.contents:
                            contents = data.contents
                            try:
                                extracted_text = " ".join(
                                    c.text for c in contents if hasattr(c, 'text') and c.text
                                )
                            except Exception:  # noqa: BLE001
                                extracted_text = ""
                            if not extracted_text:
                                extracted_text = str(data)
                        else:
                            extracted_text = str(data)
                    except Exception as extract_err:  # noqa: BLE001
                        logger.warning(f"[Magentic] Failed to extract text from workflow output: {extract_err}")
                        extracted_text = str(data) if data else ""
                    response_content = extracted_text
                
                # Extract tables from function result events
                if hasattr(event, 'message'):
                    event_message = getattr(event, 'message', None)
                    if event_message and hasattr(event_message, 'contents'):
                        logger.debug(f"[Magentic] Event message has {len(event_message.contents)} content items (chat phase)")
                        try:
                            from agent_framework._types import FunctionResultContent
                        except ImportError:
                            from agent_framework import FunctionResultContent
                        
                        for content in event_message.contents:
                            try:
                                if isinstance(content, FunctionResultContent) or hasattr(content, 'result'):
                                    if hasattr(content, 'result') and content.result:
                                        result_data = content.result
                                        logger.debug(f"[Magentic] FunctionResultContent detected (type={type(result_data)})")
                                        if isinstance(result_data, dict):
                                            extracted_objs.append(result_data)
                                        elif isinstance(result_data, str):
                                            try:
                                                parsed = json.loads(result_data)
                                                if isinstance(parsed, dict):
                                                    extracted_objs.append(parsed)
                                            except json.JSONDecodeError:
                                                multi = self._extract_json_objects(result_data)
                                                if multi:
                                                    extracted_objs.extend(obj for obj in multi if isinstance(obj, dict))
                                text_val = getattr(content, 'text', None)
                                if text_val:
                                    logger.debug(f"[Magentic] Text content candidate length={len(text_val)} (chat phase)")
                                    if ('{' in text_val and '}' in text_val) or ('[' in text_val and ']' in text_val):
                                        objs = self._extract_json_objects(text_val)
                                        if objs:
                                            logger.debug(f"[Magentic] Extracted {len(objs)} JSON object(s) from text content")
                                            extracted_objs.extend(obj for obj in objs if isinstance(obj, dict))
                            except Exception as content_err:  # noqa: BLE001
                                logger.debug(f"[Magentic] Content parsing error (chat): {content_err}")
            
            logger.info(f"[Magentic] Extracted {len(extracted_objs)} objects from function results")
            
            # If no objects from function results, try extracting from text response (fallback)
            if not extracted_objs:
                logger.info("[Magentic] No function results found, trying to extract from response text")
                extracted_objs = self._extract_json_objects(response_content)
                logger.info(f"[Magentic] Extracted {len(extracted_objs)} JSON objects from response text")
            
            tables_all = self._normalize_table_objects(extracted_objs)
            unique_tables = self._dedupe_tables(tables_all)

            # Fallback buffer for chat path
            if (not unique_tables) and TOOL_RESULTS_BUFFER:
                buffered_tables: list[dict[str, Any]] = []
                for entry in TOOL_RESULTS_BUFFER:
                    table_obj = entry.get("table") if isinstance(entry, dict) else None
                    if isinstance(table_obj, dict) and table_obj.get("columns") and table_obj.get("rows"):
                        buffered_tables.append({
                            "columns": table_obj.get("columns", []),
                            "rows": table_obj.get("rows", []),
                            "total_rows": table_obj.get("total_rows", len(table_obj.get("rows", [])))
                        })
                if buffered_tables:
                    unique_tables = self._dedupe_tables(buffered_tables)
                    logger.info(f"[Magentic] Chat fallback buffer recovered {len(unique_tables)} table(s)")
                TOOL_RESULTS_BUFFER.clear()
            
            if unique_tables:
                logger.info(f"[Magentic] Found {len(unique_tables)} unique tables")
            else:
                logger.warning("[Magentic] No tables found - check if Kusto tool is being called")

            # Clean the response by removing raw JSON objects (they're already in tables)
            # This prevents the AI summary from showing garbled table data
            clean_response = self._clean_summary_from_json(response_content)
            
            return {
                "message": message,
                "response": self._apply_speculation_filter(clean_response, unique_tables if unique_tables else None, strict_mode),
                "agent_used": "AgentFramework (Magentic)",
                "tables": unique_tables if unique_tables else None,
                "state": {"history_turns": len(history), "strict": strict_mode} if (history or strict_mode) else None,
            }

        except Exception as e:
            logger.error(f"Magentic orchestration processing failed: {e}")
            return await self._fallback_intent_detection(message, extra_parameters)
    
    async def _fallback_intent_detection(self, message: str, extra_parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fallback method for simple intent detection"""
        logger.info(f"Using fallback intent detection: {message[:100]}...")
        
        # Extract any obvious identifiers from the message
        guid_match = re.search(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", message)
        
        # Check for scenario references
        scenario_titles = self.scenario_service.list_all_scenario_titles()
        if scenario_titles:
            message_lower = message.lower()
            for title in scenario_titles:
                title_lower = title.lower()
                if title_lower and (title_lower in message_lower or any(word in title_lower for word in message_lower.split() if len(word) > 3)):
                    logger.info(f"Scenario match found: {title}")
                    return await self.query_diagnostics("scenario", {"scenario": title})
        
        # Simple intent mapping as fallback
        intent_keywords = {
            "device_details": ["device", "details", "information", "info", "properties"],
            "compliance": ["compliance", "compliant", "policy", "complies"],
            "applications": ["app", "application", "software", "install"],
            "user_lookup": ["user", "owner", "who"],
            "tenant_info": ["tenant", "organization", "company"],
            "effective_groups": ["group", "membership", "assigned"],
            "mam_policy": ["mam", "mobile", "management"]
        }
        
        detected_intent = None
        for intent, keywords in intent_keywords.items():
            if any(keyword in message.lower() for keyword in keywords):
                detected_intent = intent
                break
        
        # Build parameters
        params = extra_parameters.copy() if extra_parameters else {}
        if guid_match:
            params.setdefault("device_id", guid_match.group(0))
        
        if detected_intent:
            logger.info(f"Fallback intent detected: {detected_intent}")
            try:
                return await self.query_diagnostics(detected_intent, params)
            except Exception as e:
                error_msg = str(e)
                if "is required" in error_msg:
                    return {
                        "message": message,
                        "error": error_msg,
                        "response": f"I detected you want {detected_intent.replace('_', ' ')}, but {error_msg.lower()}. Please provide the missing information.",
                        "suggestions": [f"Try: '{message} [provide missing ID]'"]
                    }
                raise
        
        # If no clear intent, provide help
        return {
            "message": message,
            "response": "I can help you with Intune diagnostics. Try asking about:\\n\\n" +
                      "• Device details (provide a device ID)\\n" +
                      "• Compliance status\\n" +
                      "• Applications and policies\\n" +
                      "• User lookups\\n" +
                      "• Group memberships\\n\\n" +
                      "Or mention a scenario from the instructions.",
            "suggestions": [
                "Show device details for [device-id]",
                "Check compliance status",  
                "Get application status",
                "Find user information"
            ]
        }


# Global agent framework service instance
agent_framework_service: AgentFrameworkService | None = None
