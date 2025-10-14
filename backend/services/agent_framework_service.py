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
from pathlib import Path
from typing import Any, AsyncGenerator

# Logging is configured in main.py
logger = logging.getLogger(__name__)

# Buffer to hold recent MCP tool normalized results (tables) because Agent Framework
# streaming events are not currently exposing function result payloads needed for
# table reconstruction. This allows a fallback after workflow completion.
TOOL_RESULTS_BUFFER: list[dict[str, Any]] = []

# Agent Framework imports (equivalent to Autogen)
# The agent-framework package provides the core chat agent functionality
# Documentation: https://github.com/microsoft/agent-framework/tree/main/python
from agent_framework import (
    ChatAgent,
    MagenticBuilder,
    WorkflowOutputEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from models.schemas import ModelConfiguration
from services.auth_service import auth_service
from services.scenario_lookup_service import get_scenario_service


def create_scenario_lookup_function() -> Callable[..., Awaitable[str]]:
    """Create a function for looking up scenarios from instructions.md.

    This function relies on the ScenarioLookupService keyword scoring to find
    relevant scenarios without depending on the experimental semantic search
    subsystem.
    """
    
    async def lookup_scenarios(user_request: str, max_scenarios: int = 3) -> str:
        """Look up relevant diagnostic scenarios from instructions.md.
        
        This tool uses the ScenarioLookupService keyword scoring engine to
        understand user intent and return the most relevant diagnostic
        scenarios.
        
        Use this tool to find the appropriate Kusto queries for a user's diagnostic request.
        This is the PRIMARY tool for finding diagnostic queries - ALWAYS use this first.
        
        Args:
            user_request: The user's diagnostic request or keywords to search for
            max_scenarios: Maximum number of scenarios to return (default: 3)
            
        Returns:
            Matching diagnostic scenarios with their queries from instructions.md
        """
        try:
            # Get scenario service and use keyword-based lookup
            scenario_service = get_scenario_service()

            # Log the user request for debugging
            logger.info(f"[AgentFramework] Scenario lookup called with: '{user_request}'")

            matching_titles = scenario_service.find_scenarios_by_keywords(user_request, max_scenarios)
            
            logger.info(f"[AgentFramework] Found matching scenarios via keyword lookup: {matching_titles}")
            
            if not matching_titles:
                available = scenario_service.list_all_scenario_titles()
                logger.warning(f"[AgentFramework] No matching scenarios found. Available: {available}")
                return "No matching diagnostic scenarios found. Available scenarios: " + \
                       ", ".join(available)
            
            # Get detailed scenarios
            scenarios = scenario_service.get_scenarios_by_titles(matching_titles)
            
            # Format response
            response_parts = ["Found matching diagnostic scenarios:\n"]
            
            for i, scenario in enumerate(scenarios, 1):
                response_parts.append(f"## {i}. {scenario.title}")
                response_parts.append(f"**Description:** {scenario.description}")
                response_parts.append("**Queries:**")
                
                for j, query in enumerate(scenario.queries, 1):
                    response_parts.append(f"```kusto\n{query}\n```")
                
                response_parts.append("")  # Add spacing
            
            result = "\n".join(response_parts)
            logger.info(f"[AgentFramework] Returning {len(scenarios)} scenarios with {sum(len(s.queries) for s in scenarios)} queries")
            return result
            
        except Exception as e:
            logger.error(f"[AgentFramework] Error in scenario lookup: {e}")
            return f"Error looking up scenarios: {str(e)}"
    
    # Set function metadata for proper tool registration
    lookup_scenarios.__name__ = "lookup_scenarios"
    
    return lookup_scenarios


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
        f"""Execute MCP tool: {tool_name}
        
        {tool_description}
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            Result from the MCP tool execution
        """
        try:
            from services.kusto_mcp_service import get_kusto_service
            from services.conversation_state import get_conversation_state_service
            
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
                cluster_url = actual_args.get("clusterUrl")
                database = actual_args.get("database") 
                query = actual_args.get("query")
                
                if cluster_url and database and query:
                    # Substitute placeholders in query with stored context
                    query = context_service.substitute_placeholders(query)
                    
                    # Ensure clusterUrl has https:// prefix as required by MCP server
                    if not cluster_url.startswith(("https://", "http://")):
                        normalized_cluster_url = f"https://{cluster_url}"
                    else:
                        normalized_cluster_url = cluster_url
                    
                    logger.info(f"[AgentFramework] Using cluster URL: {normalized_cluster_url}")
                    logger.info(f"[AgentFramework] Query length: {len(query)} characters")
                    logger.info(f"[AgentFramework] Query (first 500 chars): {query[:500]}...")
                    
                    # Pass parameters directly to MCP server
                    mcp_args = {
                        "clusterUrl": normalized_cluster_url,
                        "database": database,
                        "query": query,
                        **{k: v for k, v in actual_args.items() if k not in ["clusterUrl", "database", "query"]}
                    }
                    
                    try:
                        result = await kusto_service._session.call_tool(tool_name, mcp_args)
                        normalized = kusto_service._normalize_tool_result(result)
                    except Exception as e:
                        logger.error(f"[AgentFramework] MCP call_tool failed: {type(e).__name__}: {e}")
                        logger.error(f"[AgentFramework] Tool: {tool_name}, Database: {database}")
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
                else:
                    return json.dumps({"success": False, "error": f"Missing required parameters for {tool_name}: clusterUrl, database, query"})
            
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
                raise Exception(f"Authentication system not ready: {retry_e}")

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
        """Discover and create tools from the MCP server
        
        Returns a list of async functions that can be used as tools
        in the Agent Framework's function calling system.
        """
        try:
            from services.kusto_mcp_service import get_kusto_service
            
            kusto_service = await get_kusto_service()
            
            # Get the available tools from the MCP server
            if hasattr(kusto_service, '_session') and kusto_service._session:
                tool_list = await kusto_service._session.list_tools()
                mcp_tools = getattr(tool_list, "tools", [])
                
                # Create function wrappers for each MCP tool
                tools: list[Callable[..., Awaitable[str]]] = []
                
                # Add the scenario lookup tool first
                lookup_function = create_scenario_lookup_function()
                tools.append(lookup_function)
                logger.info("Added scenario lookup tool")
                
                # Add the context lookup tool
                context_function = create_context_lookup_function()
                tools.append(context_function)
                logger.info("Added context lookup tool")
                
                for mcp_tool in mcp_tools:
                    tool_name = mcp_tool.name
                    tool_description = getattr(mcp_tool, 'description', f'MCP tool: {tool_name}')
                    
                    # Create a function wrapper for this MCP tool
                    tool_function = create_mcp_tool_function(tool_name, tool_description)
                    tools.append(tool_function)
                    logger.info(f"Created tool wrapper for MCP tool: {tool_name}")
                
                return tools
            else:
                logger.warning("MCP session not available for tool discovery")
                return []
                
        except Exception as e:
            logger.error(f"Failed to discover MCP tools: {e}")
            return []
    
    async def create_intune_expert_agent(self, model_config: ModelConfiguration) -> ChatAgent:
        """Create the IntuneExpert agent using Agent Framework
        
        This creates a ChatAgent with the same capabilities as the Autogen
        AssistantAgent, including MCP tools and scenario lookup.
        """
        logger.info("Creating Intune Expert agent with Kusto MCP tools (Agent Framework)")
        
        # Create the Azure OpenAI chat client
        chat_client = self._create_azure_chat_client(model_config)
        
        # System instructions (same as Autogen version)
        system_instructions = f"""
        You are an Intune Expert agent specializing in Microsoft Intune diagnostics and troubleshooting.
        
        Your role is to interpret natural language requests from support engineers and execute the appropriate
        Kusto queries using the MCP server tools to retrieve and analyze Intune device diagnostics information.
        
    INFRASTRUCTURE LABELS (IGNORE):
    - Any internal agent/orchestrator names are infrastructure metadata.
    - They are NOT user facts, NOT products, and NOT part of the Intune diagnostic domain.
    - Do NOT list them under GIVEN FACTS or treat them as entities that require lookup or explanation.
        
        AVAILABLE DIAGNOSTIC SCENARIOS:
        {self.scenario_service.get_scenario_summary()}
        
        NATURAL LANGUAGE UNDERSTANDING:
        - Interpret user requests naturally without requiring specific keywords or parameters
        - Extract relevant identifiers (Device IDs, Account IDs, Context IDs) from user messages
        - Use the lookup_scenarios tool to find relevant diagnostic scenarios based on user intent
        - Execute only the queries provided by the lookup_scenarios tool - do not create your own queries
        
        MANDATORY WORKFLOW (MUST FOLLOW IN ORDER):
        1. ALWAYS call lookup_scenarios first with the user's request text
        2. If the scenario requires context from previous queries, call lookup_context to get stored values
        3. Execute ONLY the queries returned by lookup_scenarios using MCP tools
        4. Return results in table format as specified in instructions.md
        
        DO NOT:
        - Create your own queries or speculation
        - Skip the lookup_scenarios step
        - Provide "fact sheets" or analysis without executing queries
        - Make educated guesses about data not retrieved
        
        SCENARIO LOOKUP WORKFLOW:
        1. When a user makes a request, IMMEDIATELY call lookup_scenarios with their request text
        2. The tool will return relevant diagnostic scenarios with their queries  
        3. Use the MCP server tools to execute the queries from the retrieved scenarios
        4. Always use the exact cluster URLs and database names from the scenario queries
        
        CONVERSATION CONTEXT HANDLING:
        - The system automatically stores key identifiers (DeviceId, AccountId, ContextId, etc.) from query results
        - Placeholders are automatically substituted with stored context values
        - For follow-up questions, use lookup_context if you need to check what context is available
        - If needed context is missing, ask the user to provide the required identifiers
        
        KUSTO QUERY EXECUTION:
        - Use ONLY the queries provided by lookup_scenarios
        - The system will automatically substitute stored context values
        - The MCP server provides various tools for executing Kusto queries
        - Always use the appropriate cluster URLs and database names from the scenario queries
        
        RESPONSE FORMAT (MANDATORY):
        1. Always return a TABLE first (raw results as markdown)
        2. Include all key identifier columns (DeviceId, AccountId, ContextId, etc.)
        3. Provide concise summaries after tables highlighting key findings
        4. Follow all formatting requirements from instructions.md
        5. If multiple datasets needed, show multiple labeled tables

    STRICT BEHAVIOR RULES (GLOBAL):
    - ALWAYS use lookup_scenarios first - do not skip this step
    - DO NOT create "fact sheets", "educated guesses", or lengthy analysis - execute queries instead
    - DO NOT speculate about group memberships, policies, or statuses not in query results
    - EXECUTE QUERIES, DON'T ANALYZE - your job is to run Kusto queries
    - Keep answers tightly scoped to the user request
    - If context is ambiguous, ask a concise clarifying question
        
        EXAMPLE INTERACTIONS:
        - "Show me device details for abc-123" -> Find device details query and execute it
        - "What's the compliance status?" -> Use compliance query from instructions.md
        - "Device enrollment issues" -> Execute relevant diagnostic queries
        - "Execute scenario X" -> Run all queries defined for scenario X
        
        Always rely on instructions.md for the correct Kusto queries and use your MCP tools to execute them.
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
            self.magentic_workflow = (
                MagenticBuilder()
                .participants(IntuneExpert=self.intune_expert_agent)
                .with_standard_manager(
                    chat_client=self.chat_client,
                    max_round_count=20,  # Equivalent to max_turns in Autogen
                    max_stall_count=3,   # Equivalent to max_stalls in Autogen
                )
                .build()
            )
            
            # Initialize Kusto MCP service
            try:
                from services.kusto_mcp_service import get_kusto_service
                kusto_service = await get_kusto_service()
                logger.info(f"Kusto MCP service initialized (tools={getattr(kusto_service, '_tool_names', [])})")
            except Exception as mcp_err:
                logger.error(f"Failed to initialize Kusto MCP service: {mcp_err}")
                raise
            
            logger.info("Agent Framework with Magentic orchestration setup completed successfully")
            return True
            
        except Exception as e:
            error_msg = f"Failed to setup Agent Framework: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    async def query_diagnostics(self, query_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute diagnostic query through the Magentic workflow orchestration"""
        if not self.magentic_workflow:
            raise Exception("Magentic workflow not initialized")
        
        try:
            logger.info(f"Executing diagnostic query: {query_type}")
            # Clear any previous buffered tool results to avoid cross-query leakage
            TOOL_RESULTS_BUFFER.clear()
            
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
            
            # Handle device timeline with specialized prompt
            if query_type == "device_timeline":
                device_id = parameters.get("device_id") or parameters.get("deviceid") or parameters.get("device")
                start_time = parameters.get("start_time") or parameters.get("start")
                end_time = parameters.get("end_time") or parameters.get("end")
                timeline_instructions = (
                    "You are an Intune diagnostics expert. Build a comprehensive chronological device event timeline.\n\n"
                    "CRITICAL REQUIREMENTS:\n"
                    "1. Look up the 'Advanced Scenario: Device Timeline' from instructions.md using lookup_scenarios\n"
                    "2. YOU MUST execute ALL queries in the Device Timeline scenario - there are approximately 9 queries total\n"
                    "3. Execute queries in order: Device_Snapshot → Compliance → Applications → Check-ins → Group Membership → Group Definitions → Deployments → Events\n"
                    "4. Do NOT stop after the first few queries - continue until ALL queries have been executed\n"
                    "5. Some queries depend on results from earlier queries (e.g., group IDs, tenant ID) - extract these values and use them\n"
                    "6. If a query needs placeholders like <EffectiveGroupIdList> or <TenantId>, extract them from previous query results\n\n"
                    "7. If any query produces an error, REPORT the error and continue on with the remaining queries\n\n"
                    "OUTPUT FORMAT:\n"
                    "1. Narrative summary of findings\n"
                    "2. List ALL Kusto queries executed (should be ~9 queries)\n"
                    "3. ONE mermaid timeline code block:\n"
                    "```mermaid\\ntimeline\nTitle: Device Timeline (DEVICE_ID)\nStart: <earliest timestamp>\n<YYYY-MM-DD HH:MM>: <Category> - <Brief description>\n...\n```\n\n"
                    "Timeline Rules:\n"
                    "- Categories: Compliance, Policy, App, Check-in, Error, Enrollment, Group, Deployment, Other\n"
                    "- Limit to <= 60 most impactful events\n"
                    "- Normalize all timestamps to UTC ISO8601 (YYYY-MM-DD HH:MM)\n"
                    "- If no events, output empty timeline with 'No significant events' note\n"
                )
                query_message = (
                    f"{timeline_instructions}\nParameters: device_id={device_id}, start_time={start_time}, end_time={end_time}. Return narrative then the mermaid block."
                )
            else:
                query_message = f"Please execute a {query_type} query with the following parameters: {parameters}"
            
            # Run the Magentic workflow with streaming
            logger.info(f"[Magentic] Running workflow with query: {query_message[:100]}...")
            response_content = ""
            extracted_objs = []
            
            async for event in self.magentic_workflow.run_stream(query_message):
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
                
                # Capture the final output
                if isinstance(event, WorkflowOutputEvent):
                    logger.info("[Magentic] Received WorkflowOutputEvent - task completed")
                    # Robust extraction of textual content from Agent Framework objects
                    data = getattr(event, 'data', None)
                    extracted_text = ""
                    try:
                        if data is None:
                            extracted_text = ""
                        # ChatResponse has .text
                        elif hasattr(data, 'text') and getattr(data, 'text'):
                            extracted_text = getattr(data, 'text')  # type: ignore[assignment]
                        # Some objects might expose 'content'
                        elif hasattr(data, 'content') and getattr(data, 'content'):
                            extracted_text = str(getattr(data, 'content'))
                        # ChatMessage has .contents (list) – join any text parts
                        elif hasattr(data, 'contents') and getattr(data, 'contents'):
                            contents = getattr(data, 'contents')
                            try:
                                extracted_text = " ".join(
                                    c.text for c in contents if hasattr(c, 'text') and getattr(c, 'text')
                                )
                            except Exception:  # noqa: BLE001
                                extracted_text = ""
                            if not extracted_text:
                                # Fallback to repr if still empty
                                extracted_text = str(data)
                        else:
                            extracted_text = str(data)
                    except Exception as extract_err:  # noqa: BLE001
                        logger.warning(f"[Magentic] Failed to extract text from workflow output: {extract_err}")
                        extracted_text = str(data) if data else ""
                    response_content = extracted_text
                
                # Extract tables from function result events
                # The workflow may emit events with function call results
                if hasattr(event, 'message'):
                    event_message = getattr(event, 'message', None)
                    if event_message and hasattr(event_message, 'contents'):
                        logger.debug(f"[Magentic] Event message has {len(event_message.contents)} content items (query_diagnostics phase)")
                        try:
                            from agent_framework._types import FunctionResultContent
                        except ImportError:
                            from agent_framework import FunctionResultContent
                        
                        for content in event_message.contents:
                            try:
                                # Function/tool result content
                                if isinstance(content, FunctionResultContent) or hasattr(content, 'result'):
                                    if hasattr(content, 'result') and getattr(content, 'result'):
                                        result_data = getattr(content, 'result')
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
                                # Text content JSON scan
                                if hasattr(content, 'text') and getattr(content, 'text'):
                                    text_val = getattr(content, 'text')
                                    logger.debug(f"[Magentic] Text content candidate length={len(text_val)} (query_diagnostics)")
                                    if ('{' in text_val and '}' in text_val) or ('[' in text_val and ']' in text_val):
                                        objs = self._extract_json_objects(text_val)
                                        if objs:
                                            logger.debug(f"[Magentic] Extracted {len(objs)} JSON object(s) from text content")
                                            extracted_objs.extend(obj for obj in objs if isinstance(obj, dict))
                            except Exception as content_err:  # noqa: BLE001
                                logger.debug(f"[Magentic] Content parsing error (query_diagnostics): {content_err}")
            
            logger.info(f"[Magentic] query_diagnostics: Extracted {len(extracted_objs)} objects from function results")
            if extracted_objs:
                logger.debug("[Magentic] Raw extracted objects sample (first 1): %s", json.dumps(extracted_objs[0])[:500])
            
            # If no objects from function results, try extracting from text response (fallback)
            if not extracted_objs:
                logger.info("[Magentic] query_diagnostics: No function results found, trying to extract from response text")
                extracted_objs = self._extract_json_objects(response_content)
                logger.info(f"[Magentic] query_diagnostics: Extracted {len(extracted_objs)} JSON objects from response text")
            
            # Extract mermaid timeline if requested
            mermaid_block: str | None = None
            if query_type == "device_timeline":
                import re
                pattern = re.compile(r"```mermaid\s+([\s\S]*?)```", re.IGNORECASE)
                match = pattern.search(response_content)
                if match:
                    mermaid_block = match.group(1).strip()
                # Heuristic fallback
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
            
            # Normalize and dedupe tables
            tables_all = self._normalize_table_objects(extracted_objs)
            unique_tables = self._dedupe_tables(tables_all)

            # Fallback: if streaming yielded no tables but MCP normalized results were buffered
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
                    logger.info(f"[Magentic] Fallback buffer recovered {len(unique_tables)} table(s) for query_diagnostics")
                TOOL_RESULTS_BUFFER.clear()
            
            if unique_tables:
                logger.debug(f"[query_diagnostics] Total tables after normalization: {len(unique_tables)}")

            # Add synthetic mermaid table if we captured a block
            if mermaid_block:
                mermaid_table = {"columns": ["mermaid_timeline"], "rows": [[mermaid_block]], "total_rows": 1}
                if unique_tables:
                    unique_tables = unique_tables + [mermaid_table]
                else:
                    unique_tables = [mermaid_table]
                response_content = response_content + "\n\n[Mermaid timeline extracted successfully]"

            # Clean the summary by removing raw JSON objects (they're already in tables)
            # This prevents the AI summary from showing garbled table data
            summary_content = self._clean_summary_from_json(response_content)
            
            return {
                "query_type": query_type,
                "parameters": parameters,
                "response": response_content,
                "summary": summary_content or f"Executed {query_type} query via Agent Framework",
                "tables": unique_tables if unique_tables else None,
                "mermaid_timeline": mermaid_block,
            }
            
        except Exception as e:
            error_msg = str(e) if str(e) else f"Unknown error of type {type(e).__name__}"
            logger.error(f"Diagnostic query failed: {error_msg}")
            return {
                "query_type": query_type,
                "parameters": parameters,
                "tables": [{
                    "columns": ["Error"],
                    "rows": [[error_msg]],
                    "total_rows": 1
                }],
                "summary": f"Diagnostic query failed: {error_msg}"
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
""" if strict_mode else ""
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
                        f"User message: {message}"
                    )
                else:
                    composite_task = message

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
                
                # Capture the final output
                if isinstance(event, WorkflowOutputEvent):
                    logger.info("[Magentic] Received WorkflowOutputEvent - task completed")
                    # Robust extraction of textual content from Agent Framework objects
                    data = getattr(event, 'data', None)
                    extracted_text = ""
                    try:
                        if data is None:
                            extracted_text = ""
                        elif hasattr(data, 'text') and getattr(data, 'text'):
                            extracted_text = getattr(data, 'text')  # ChatResponse or ChatMessage.text
                        elif hasattr(data, 'content') and getattr(data, 'content'):
                            extracted_text = str(getattr(data, 'content'))
                        elif hasattr(data, 'contents') and getattr(data, 'contents'):
                            contents = getattr(data, 'contents')
                            try:
                                extracted_text = " ".join(
                                    c.text for c in contents if hasattr(c, 'text') and getattr(c, 'text')
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
                                    if hasattr(content, 'result') and getattr(content, 'result'):
                                        result_data = getattr(content, 'result')
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
                                if hasattr(content, 'text') and getattr(content, 'text'):
                                    text_val = getattr(content, 'text')
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
