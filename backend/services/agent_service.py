import json
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import MagenticOneGroupChat
from autogen_core.models import ChatCompletionClient
from autogen_core.tools import BaseTool, FunctionTool
from autogen_ext.auth.azure import AzureTokenProvider
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from models.schemas import ModelConfiguration
from services.auth_service import auth_service
from services.instructions_parser import parse_instructions


def create_mcp_tool_function(tool_name: str, tool_description: str) -> Callable[..., Awaitable[str]]:
    """Create an async function wrapper for an MCP tool"""
    
    async def mcp_tool_func(**kwargs: Any) -> str:
        """Execute the MCP tool with given parameters"""
        try:
            from services.kusto_mcp_service import get_kusto_service
            
            kusto_service = await get_kusto_service()
            
            # Handle nested kwargs structure from agent calls
            if "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
                # Agent passed arguments nested under 'kwargs'
                actual_args = kwargs["kwargs"]
            else:
                # Direct argument passing
                actual_args = kwargs
            
            logger.info(f"Calling MCP tool '{tool_name}' with args: {actual_args}")
            
            # For execute_query tool, ensure proper clusterUrl format and call MCP server directly
            if tool_name == "execute_query" and hasattr(kusto_service, '_session') and kusto_service._session:
                cluster_url = actual_args.get("clusterUrl")
                database = actual_args.get("database") 
                query = actual_args.get("query")
                
                if cluster_url and database and query:
                    # Ensure clusterUrl has https:// prefix as required by MCP server
                    if not cluster_url.startswith(("https://", "http://")):
                        normalized_cluster_url = f"https://{cluster_url}"
                    else:
                        normalized_cluster_url = cluster_url
                    
                    logger.info(f"Using cluster URL: {normalized_cluster_url}")
                    logger.info(f"Query: {query}")
                    
                    # Pass parameters directly to MCP server
                    mcp_args = {
                        "clusterUrl": normalized_cluster_url,
                        "database": database,
                        "query": query,
                        **{k: v for k, v in actual_args.items() if k not in ["clusterUrl", "database", "query"]}
                    }
                    
                    result = await kusto_service._session.call_tool(tool_name, mcp_args)
                    normalized = kusto_service._normalize_tool_result(result)
                    return json.dumps(normalized)
                else:
                    return json.dumps({"success": False, "error": f"Missing required parameters for {tool_name}: clusterUrl, database, query"})
            
            # For other tools, call MCP session directly
            elif hasattr(kusto_service, '_session') and kusto_service._session:
                result = await kusto_service._session.call_tool(tool_name, actual_args)
                # Normalize the result
                normalized = kusto_service._normalize_tool_result(result)
                return json.dumps(normalized)
            else:
                return json.dumps({"success": False, "error": "MCP session not available"})
                
        except Exception as e:
            logger.error(f"MCP tool {tool_name} execution failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
    
    # Set function metadata for FunctionTool
    mcp_tool_func.__name__ = tool_name
    mcp_tool_func.__doc__ = tool_description
    
    return mcp_tool_func

class AgentService:
    """Autogen-based multi-agent orchestrator for Intune diagnostics"""
    
    def __init__(self) -> None:
        self.intune_expert_agent: AssistantAgent | None = None
        self.magentic_one_team: MagenticOneGroupChat | None = None
        self.model_client: ChatCompletionClient | None = None
        self.instructions_path = Path(__file__).parent.parent.parent / "instructions.md"
        self.scenarios: list[dict[str, Any]] = []
        self.instructions_content: str = ""

    def list_instruction_scenarios(self) -> list[dict[str, Any]]:
        """Return a lightweight summary of parsed instruction scenarios."""
        return [
            {
                "index": idx,
                "title": sc.get("title"),
                "query_count": len(sc.get("queries", [])),
                "description": (sc.get("description") or "").split("\n")[0][:160]
            }
            for idx, sc in enumerate(self.scenarios)
        ]

    async def run_instruction_scenario(self, scenario_ref: int | str) -> dict[str, Any]:
        """Execute all queries in a referenced scenario via the Intune expert agent.
        
        This method delegates to the IntuneExpert agent which will use its natural language
        understanding to interpret and execute the appropriate scenario queries.
        """
        if not self.intune_expert_agent:
            raise ValueError("Intune expert agent not initialized")
        
        try:
            if not self.scenarios:
                raise ValueError("No scenarios parsed from instructions.md")

            scenario: dict[str, Any] | None = None
            if isinstance(scenario_ref, int):
                if 0 <= scenario_ref < len(self.scenarios):
                    scenario = self.scenarios[scenario_ref]
            else:
                ref_lower = scenario_ref.lower()
                for sc in self.scenarios:
                    if sc.get("title", "").lower() == ref_lower:
                        scenario = sc
                        break
                if scenario is None:
                    for sc in self.scenarios:
                        if ref_lower in sc.get("title", "").lower():
                            scenario = sc
                            break

            if scenario is None:
                raise ValueError(f"Scenario not found: {scenario_ref}")

            from services.kusto_mcp_service import get_kusto_service
            kusto_service = await get_kusto_service()

            tables: list[dict[str, Any]] = []
            errors: list[str] = []
            for idx, query in enumerate(scenario.get("queries", [])):
                res = await kusto_service.execute_kusto_query(query)
                if res.get("success"):
                    tables.append(res.get("table", {"columns": ["Result"], "rows": [["(empty)"]], "total_rows": 0}))
                else:
                    err = res.get("error", "Unknown error")
                    errors.append(f"Query {idx+1}: {err}")
                    tables.append({"columns": ["Error"], "rows": [[err]], "total_rows": 1})

            summary_parts = [f"Scenario: {scenario.get('title')} ({len(tables)} queries)"]
            if errors:
                summary_parts.append(f"{len(errors)} query errors encountered.")
            summary = " \n".join(summary_parts)

            return {
                "scenario": scenario.get("title"),
                "description": scenario.get("description"),
                "tables": tables,
                "summary": summary,
                "errors": errors,
            }
        except Exception as e:
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
        """Initialize the global agent service"""
        global agent_service
        agent_service = cls()
        await agent_service._load_instructions()
    
    @classmethod
    async def cleanup(cls) -> None:
        """Cleanup agent service resources"""
        pass
    
    async def _load_instructions(self) -> None:
        """Load instructions.md content for agent context"""
        try:
            with open(self.instructions_path, encoding='utf-8') as f:
                self.instructions_content = f.read()
            # Parse scenarios for structured access
            try:
                parsed = parse_instructions(self.instructions_content)
                self.scenarios = parsed
                logger.info(f"Parsed {len(self.scenarios)} instruction scenarios with queries")
            except Exception as perr:  # noqa: BLE001
                logger.warning(f"Failed to parse instruction scenarios: {perr}")
        except FileNotFoundError:
            self.instructions_content = "Instructions file not found"
            self.scenarios = []
    
    def _create_azure_model_client(self, model_config: ModelConfiguration) -> AzureOpenAIChatCompletionClient:
        """Create Azure OpenAI client for the given model configuration"""
        # Use WAM broker credential for Azure OpenAI authentication
        token_provider = AzureTokenProvider(
            auth_service.wam_credential,
            "https://cognitiveservices.azure.com/.default"
        )
        
        return AzureOpenAIChatCompletionClient(
            azure_deployment=model_config.azure_deployment,
            model=model_config.model_name,
            api_version=model_config.api_version,
            azure_endpoint=model_config.azure_endpoint,
            azure_ad_token_provider=token_provider
        )
    
    async def _discover_mcp_tools(self) -> list[BaseTool[Any, Any] | Callable[..., Any] | Callable[..., Awaitable[Any]]]:
        """Discover and create tools from the MCP server"""
        try:
            from services.kusto_mcp_service import get_kusto_service
            
            kusto_service = await get_kusto_service()
            
            # Get the available tools from the MCP server
            if hasattr(kusto_service, '_session') and kusto_service._session:
                tool_list = await kusto_service._session.list_tools()
                mcp_tools = getattr(tool_list, "tools", [])
                
                # Create FunctionTool wrappers for each MCP tool
                tools: list[BaseTool[Any, Any] | Callable[..., Any] | Callable[..., Awaitable[Any]]] = []
                
                for mcp_tool in mcp_tools:
                    tool_name = mcp_tool.name
                    tool_description = getattr(mcp_tool, 'description', f'MCP tool: {tool_name}')
                    
                    # Create a function wrapper for this MCP tool
                    tool_function = create_mcp_tool_function(tool_name, tool_description)
                    
                    # Create FunctionTool from the function
                    function_tool = FunctionTool(
                        tool_function,
                        name=tool_name,
                        description=tool_description
                    )
                    tools.append(function_tool)
                    logger.info(f"Created tool wrapper for MCP tool: {tool_name}")
                
                return tools
            else:
                logger.warning("MCP session not available for tool discovery")
                return []
                
        except Exception as e:
            logger.error(f"Failed to discover MCP tools: {e}")
            return []
    
    async def create_intune_expert_agent(self, model_config: ModelConfiguration) -> AssistantAgent:
        """Create the IntuneExpert agent with Kusto MCP tools access"""
        logger.info("Creating Intune Expert agent with Kusto MCP tools")
        model_client = self._create_azure_model_client(model_config)
        
        system_message = f"""
        You are an Intune Expert agent specializing in Microsoft Intune diagnostics and troubleshooting.
        
        Your role is to interpret natural language requests from support engineers and execute the appropriate
        Kusto queries using the MCP server tools to retrieve and analyze Intune device diagnostics information.
        
        CRITICAL INSTRUCTIONS FROM INSTRUCTIONS.MD:
        {self.instructions_content}
        
        NATURAL LANGUAGE UNDERSTANDING:
        - Interpret user requests naturally without requiring specific keywords or parameters
        - Extract relevant identifiers (Device IDs, Account IDs, Context IDs) from user messages
        - Map user intents to appropriate scenarios and queries from instructions.md
        - Use the MCP server tools to execute the queries defined in instructions.md
        
        KUSTO QUERY EXECUTION:
        - Use ONLY the queries provided in instructions.md - do not create your own queries
        - The MCP server provides various tools for executing Kusto queries
        - Common tools include: execute_query, executeQuery, and other MCP-specific tools
        - Always use the appropriate cluster URLs and database names from the queries in instructions.md
        
        RESPONSE FORMAT (MANDATORY):
        1. Always return a TABLE first (raw results as markdown)
        2. Include all key identifier columns (DeviceId, AccountId, ContextId, etc.)
        3. Provide concise summaries after tables highlighting key findings
        4. Follow all formatting requirements from instructions.md
        5. If multiple datasets needed, show multiple labeled tables
        
        EXAMPLE INTERACTIONS:
        - "Show me device details for abc-123" -> Find device details query in instructions.md and execute it
        - "What's the compliance status?" -> Use compliance query from instructions.md
        - "Device enrollment issues" -> Execute relevant diagnostic queries from instructions.md
        - "Execute scenario X" -> Run all queries defined for scenario X in instructions.md
        
        Always rely on instructions.md for the correct Kusto queries and use your MCP tools to execute them.
        """
        
        # Discover and create tools from MCP server
        tools = await self._discover_mcp_tools()
        agent = AssistantAgent(
            name="IntuneExpert",
            model_client=model_client,
            system_message=system_message,
            tools=tools
        )
        logger.info("IntuneExpert agent created successfully with Kusto tools")
        
        return agent

    
    async def setup_agent(self, model_config: ModelConfiguration) -> bool:
        """Set up the Magentic One team with IntuneExpert agent"""
        try:
            logger.info(f"Setting up Magentic One team with model: {model_config.model_name}")
            
            # Store the model client for the orchestrator
            self.model_client = self._create_azure_model_client(model_config)
            
            # Create the IntuneExpert agent with tools
            self.intune_expert_agent = await self.create_intune_expert_agent(model_config)
            
            # Create the Magentic One team with the orchestrator model and expert agent
            termination_condition = MaxMessageTermination(max_messages=20)
            
            self.magentic_one_team = MagenticOneGroupChat(
                participants=[self.intune_expert_agent],
                model_client=self.model_client,
                name="IntuneDignosticsTeam",
                description="Autogen Magentic One team for Intune diagnostics and troubleshooting",
                termination_condition=termination_condition,
                max_turns=20,
                max_stalls=3
            )
            
            # Initialize Kusto MCP service
            try:
                from services.kusto_mcp_service import get_kusto_service
                kusto_service = await get_kusto_service()
                logger.info(f"Kusto MCP service initialized (tools={getattr(kusto_service, '_tool_names', [])})")
            except Exception as mcp_err:
                logger.error(f"Failed to initialize Kusto MCP service: {mcp_err}")
                raise
            
            logger.info("Magentic One team setup completed successfully")
            return True
            
        except Exception as e:
            error_msg = f"Failed to setup Magentic One team: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    async def query_diagnostics(self, query_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute diagnostic query through the Magentic One team"""
        if not self.magentic_one_team:
            raise Exception("Magentic One team not initialized")
        
        try:
            logger.info(f"Executing diagnostic query: {query_type}")
            
            # Handle scenario queries
            if query_type == "scenario":
                scenario_ref = parameters.get("scenario") or parameters.get("name") or parameters.get("index")
                if scenario_ref is None:
                    raise Exception("Parameter 'scenario' is required for scenario execution")
                
                try:
                    if isinstance(scenario_ref, str) and scenario_ref.isdigit():
                        scenario_ref_val: int | str = int(scenario_ref)
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
            
            # For other query types, delegate to the Magentic One team
            # The team will use MCP tools and instructions.md to handle the request
            query_message = f"Please execute a {query_type} query with the following parameters: {parameters}"
            
            # Use the Magentic One team to process this request
            try:
                team_result = await self.magentic_one_team.run(task=query_message)
                
                # Extract results from team execution
                if hasattr(team_result, 'messages') and team_result.messages:
                    last_message = team_result.messages[-1]
                    response_content = getattr(last_message, 'content', str(last_message))
                    
                    return {
                        "query_type": query_type,
                        "parameters": parameters,
                        "response": response_content,
                        "team_execution": True,
                        "summary": f"Executed {query_type} query via Magentic One team"
                    }
                else:
                    raise Exception("No response from Magentic One team")
                    
            except Exception as e:
                logger.error(f"Team execution failed for {query_type}: {e}")
                return {
                    "query_type": query_type,
                    "parameters": parameters,
                    "tables": [{
                        "columns": ["Error"],
                        "rows": [[f"Team execution failed: {str(e)}"]],
                        "total_rows": 1
                    }],
                    "summary": f"Failed to execute {query_type} query via team: {str(e)}"
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
        """Natural language chat interface using the Magentic One team.
        
        This method uses the Magentic One orchestrator with the IntuneExpert agent to understand
        and respond to natural language requests through multi-agent collaboration.
        """
        if not self.magentic_one_team:
            raise Exception("Magentic One team not initialized")
        
        try:
            logger.info(f"Processing chat message through Magentic One team: {message[:100]}...")
            
            # Use the Magentic One team to process the request
            team_result = await self.magentic_one_team.run(task=message)
            
            # Extract the response from the team result
            if hasattr(team_result, 'messages') and team_result.messages:
                last_message = team_result.messages[-1]
                response_content = getattr(last_message, 'content', str(last_message))
                
                return {
                    "message": message,
                    "response": response_content,
                    "team_result": "success",
                    "agent_used": "MagenticOneTeam"
                }
            else:
                # Fallback to simple intent detection if team doesn't return expected results
                return await self._fallback_intent_detection(message, extra_parameters)
                
        except Exception as e:
            logger.error(f"Magentic One team processing failed: {e}")
            # Fallback to simple processing
            return await self._fallback_intent_detection(message, extra_parameters)
    
    async def _fallback_intent_detection(self, message: str, extra_parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fallback method for simple intent detection when Magentic One team fails"""
        logger.info(f"Using fallback intent detection: {message[:100]}...")
        
        # Extract any obvious identifiers from the message for context
        guid_match = re.search(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", message)
        
        # Check for scenario references
        if self.scenarios:
            message_lower = message.lower()
            for scenario in self.scenarios:
                title = scenario.get("title", "").lower()
                if title and (title in message_lower or any(word in title for word in message_lower.split() if len(word) > 3)):
                    logger.info(f"Scenario match found: {scenario.get('title')}")
                    return await self.query_diagnostics("scenario", {"scenario": scenario.get("title")})
        
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
        
        # Build parameters with proper type handling
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

# Global agent service instance
agent_service: AgentService | None = None
