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
        """Initialize the global agent service and eagerly start MCP server"""
        global agent_service
        agent_service = cls()
        await agent_service._load_instructions()
        # Eagerly spin up MCP server so auth is handled once at startup
        try:
            from services.kusto_mcp_service import get_kusto_service
            kusto_service = await get_kusto_service()
            logger.info("Eager MCP server initialization completed during AgentService startup")
            # Extract cluster/database pairs for a single list_tables prewarm per cluster
            try:
                all_queries: list[str] = []
                for sc in agent_service.scenarios:
                    all_queries.extend(sc.get("queries", []))
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

            global agent_service
            agent_service = None
            logger.info("AgentService cleanup completed")
        except Exception as e:  # noqa: BLE001
            logger.error(f"AgentService cleanup failed: {e}")
            # Swallow errors so reload can proceed
    
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
        
    INFRASTRUCTURE LABELS (IGNORE):
    - Any internal agent/orchestrator names such as "MagenticOneOrchestrator", "IntuneDiagnosticsTeam", or other system-generated identifiers are infrastructure metadata.
    - They are NOT user facts, NOT products, and NOT part of the Intune diagnostic domain.
    - Do NOT list them under GIVEN FACTS or treat them as entities that require lookup or explanation.
    - If they appear in prior context, silently ignore them unless explicitly asked by the user to explain internal architecture (rare; otherwise omit).
        
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

    STRICT BEHAVIOR RULES (GLOBAL):
    - DO NOT speculate about group memberships, policies, or statuses not explicitly present in returned query/table data.
    - If user asks for data you have not fetched yet, either (a) run ONLY the minimal specific query from instructions.md, or (b) ask for required identifiers you lack.
    - Never invent likely or probable groups; only list groups surfaced by queries. If resolution of IDs fails, report the failure and request guidance.
    - If previous attempts produced HTTP errors, summarize the error and await user direction instead of guessing.
    - Keep answers tightly scoped to the user request; avoid expanding into unrelated diagnostics.
    - If context is ambiguous (missing device/account/context IDs), ask a concise clarifying question instead of assuming.
        
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

    # --- Post-processing helpers -------------------------------------------------
    def _apply_speculation_filter(self, text: str, tables: list[dict[str, Any]] | None, strict: bool) -> str:
        """In strict mode, remove or flag speculative phrases if unsupported by data.

        We avoid deep heuristics: simply detect key speculative tokens and either
        (a) remove the sentence if no tables present, or (b) append a note.
        """
        if not strict or not text:
            return text
        speculative_markers = ["likely", "probably", "possible", "might", "inferred", "it is probable"]
        has_data = bool(tables)
        # Split into simple lines (keep formatting minimal)
        lines = text.split('\n')
        cleaned: list[str] = []
        for line in lines:
            lower = line.lower()
            if any(tok in lower for tok in speculative_markers):
                if not has_data:
                    # Drop speculative line entirely
                    continue
                else:
                    # Keep but annotate
                    line += "  (Speculative wording trimmed under strict mode; verify with actual query results.)"
            cleaned.append(line)
        result = '\n'.join(cleaned).strip()
        if not result:
            return "(Strict mode removed speculative content; no factual data returned. Provide a clarifying instruction or run a specific query.)"
        return result

    # --- JSON/Table extraction helpers -------------------------------------------
    def _extract_json_objects(self, text: str) -> list[Any]:
        """Extract multiple JSON objects/lists from arbitrary concatenated text.

        Uses a streaming brace/bracket depth scan to delimit JSON. More robust than
        naive regex splitting for concatenated tool outputs.
        """
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
                # safety cut — abandon overly large block
                start_idx = None
        return results

    def _normalize_table_objects(self, objs: list[Any]) -> list[dict[str, Any]]:
        """Normalize heterogeneous JSON shapes into table dictionaries.

        Recognized patterns:
        - {"table": {"columns": [...], "rows": [...]}}
        - {"columns": [...], "rows": [...]}
        - {"name": "X", "data": [{col:val,...}, ...]}
        - Lists containing any mix of above
        """
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
                name="IntuneDiagnosticsTeam",
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
        """Execute diagnostic query through the Magentic One team (refactored)."""
        if not self.magentic_one_team:
            raise Exception("Magentic One team not initialized")
        try:
            logger.info(f"Executing diagnostic query: {query_type}")
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

            query_message = f"Please execute a {query_type} query with the following parameters: {parameters}"
            team_result = await self.magentic_one_team.run(task=query_message)
            if not (hasattr(team_result, 'messages') and team_result.messages):
                raise Exception("No response from Magentic One team")

            last_message = team_result.messages[-1]
            response_content = getattr(last_message, 'content', str(last_message))

            extracted_objs: list[Any] = []
            for m in team_result.messages:  # type: ignore[attr-defined]
                msg_text = getattr(m, 'content', '') or ''
                if not isinstance(msg_text, str):
                    continue
                objs = self._extract_json_objects(msg_text)
                if objs:
                    logger.debug(f"[query_diagnostics] Extracted {len(objs)} JSON object(s) from a message")
                extracted_objs.extend(objs)
            tables_all = self._normalize_table_objects(extracted_objs)
            unique_tables = self._dedupe_tables(tables_all)
            if unique_tables:
                logger.debug(f"[query_diagnostics] Total tables after normalization: {len(unique_tables)}")

            return {
                "query_type": query_type,
                "parameters": parameters,
                "response": response_content,
                "team_execution": True,
                "summary": response_content or f"Executed {query_type} query via Magentic One team",
                "tables": unique_tables if unique_tables else None,
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

            # Incorporate prior conversation history (if provided) to give model natural continuity
            history = []
            if extra_parameters and isinstance(extra_parameters.get("conversation_history"), list):
                raw_hist = extra_parameters.get("conversation_history")  # type: ignore[assignment]
                # Expect list of {role, content}
                for h in raw_hist:  # type: ignore[assignment]
                    if not isinstance(h, dict):
                        continue
                    role = h.get("role")
                    content = h.get("content")
                    if not (isinstance(role, str) and isinstance(content, str)):
                        continue
                    # Truncate very long historical entries to avoid context bloat
                    if len(content) > 4000:
                        content = content[:4000] + "... [truncated]"
                    history.append({"role": role, "content": content})

            strict_mode = bool(extra_parameters.get("strict_mode")) if extra_parameters else False

            if history:
                history_lines = []
                for turn in history:
                    role_tag = "USER" if turn["role"] == "user" else "ASSISTANT"
                    history_lines.append(f"{role_tag}: {turn['content']}")
                guardrail = """
STRICT RESPONSE CONSTRAINTS (if any data not already retrieved DO NOT invent it):
- Do NOT speculate about memberships, policies, or group names if they have not been explicitly retrieved via a successful query/table.
- If the user requests something requiring additional lookup, respond with a concise clarification request or perform ONLY the minimal exact query needed (from instructions.md) to obtain it.
- Never list 'likely' or 'probable' groups; only report factual rows from returned tables.
- If prior attempts produced errors (HTTP 400 etc.), summarize the failure and ask for next instruction instead of guessing.
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
                        "- Only answer using factual data already retrieved or newly queried via allowed instructions.\n"
                        "- Do not speculate or infer. If data missing, ask a clarifying question or state required query.\n\n"
                        f"User message: {message}"
                    )
                else:
                    composite_task = message

            team_result = await self.magentic_one_team.run(task=composite_task)
            if not (hasattr(team_result, 'messages') and team_result.messages):
                return await self._fallback_intent_detection(message, extra_parameters)

            last_message = team_result.messages[-1]
            response_content = getattr(last_message, 'content', str(last_message))

            extracted_objs: list[Any] = []
            for m in team_result.messages:  # type: ignore[attr-defined]
                msg_text = getattr(m, 'content', '') or ''
                if not isinstance(msg_text, str):
                    continue
                objs = self._extract_json_objects(msg_text)
                if objs:
                    logger.debug(f"[chat] Extracted {len(objs)} JSON object(s) from a message")
                extracted_objs.extend(objs)
            tables_all = self._normalize_table_objects(extracted_objs)
            unique_tables = self._dedupe_tables(tables_all)
            if unique_tables:
                logger.debug(f"[chat] Total tables after normalization: {len(unique_tables)}")

            return {
                "message": message,
                "response": self._apply_speculation_filter(response_content, unique_tables if unique_tables else None, strict_mode),
                "team_result": "success",
                "agent_used": "MagenticOneTeam",
                "tables": unique_tables if unique_tables else None,
                "state": {"history_turns": len(history), "strict": strict_mode} if (history or strict_mode) else None,
            }

        except Exception as e:
            logger.error(f"Magentic One team processing failed: {e}")
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
