import asyncio
import json
import os
import logging
import re
from typing import Dict, Any, Optional, List
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from autogen_ext.auth.azure import AzureTokenProvider
from azure.identity import DefaultAzureCredential
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import ChatAgent
from typing import Union

from models.schemas import ModelConfiguration, AgentConfiguration
from services.auth_service import auth_service
from services.instructions_parser import parse_instructions
from services.conversation_state import ConversationState, classify_intent
from services.entity_resolution import resolve_entities, needed_slots_for_intent

class AgentService:
    def __init__(self):
        self.intune_expert_agent: Optional[AssistantAgent] = None
        self.instructions_path = Path(__file__).parent.parent.parent / "instructions.md"
        self.scenarios: List[Dict[str, Any]] = []
        self.state = ConversationState()

    def list_instruction_scenarios(self) -> List[Dict[str, Any]]:
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

    async def run_instruction_scenario(self, scenario_ref: Union[int, str]) -> Dict[str, Any]:
        """Execute all queries in a referenced scenario and aggregate results.

        scenario_ref can be an integer index or a case-insensitive title substring.
        Returns structure with tables (list) and combined summary placeholder.
        """
        if not self.scenarios:
            raise ValueError("No scenarios parsed from instructions.md")

        scenario: Optional[Dict[str, Any]] = None
        if isinstance(scenario_ref, int):
            if 0 <= scenario_ref < len(self.scenarios):
                scenario = self.scenarios[scenario_ref]
        else:
            ref_lower = scenario_ref.lower()
            # Exact title match first
            for sc in self.scenarios:
                if sc.get("title", "").lower() == ref_lower:
                    scenario = sc
                    break
            if scenario is None:
                # substring fallback
                for sc in self.scenarios:
                    if ref_lower in sc.get("title", "").lower():
                        scenario = sc
                        break

        if scenario is None:
            raise ValueError(f"Scenario not found: {scenario_ref}")

        from services.kusto_mcp_service import get_kusto_service  # local import
        kusto_service = await get_kusto_service()

        tables: List[Dict[str, Any]] = []
        errors: List[str] = []
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
    
    @classmethod
    async def initialize(cls):
        """Initialize the global agent service"""
        global agent_service
        agent_service = cls()
        await agent_service._load_instructions()
    
    @classmethod
    async def cleanup(cls):
        """Cleanup agent service resources"""
        pass
    
    async def _load_instructions(self):
        """Load instructions.md content for agent context"""
        try:
            with open(self.instructions_path, 'r', encoding='utf-8') as f:
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
    
    async def create_intune_expert_agent(self, model_config: ModelConfiguration) -> AssistantAgent:
        """Create the IntuneExpert agent with Kusto MCP tools access"""
        print(f"[DEBUG] Creating Azure model client...")
        model_client = self._create_azure_model_client(model_config)
        print(f"[DEBUG] Azure model client created: {type(model_client)}")
        
        system_message = f"""
        You are an Intune Expert agent specializing in Microsoft Intune diagnostics and troubleshooting.
        
        Your role is to help support engineers retrieve and analyze Intune device diagnostics information
        using Kusto queries through the MCP server.
        
        CRITICAL INSTRUCTIONS FROM INSTRUCTIONS.MD:
        {self.instructions_content}
        
        You have access to Kusto MCP tools that can execute the queries provided in the instructions.
        Always follow the output rules from instructions.md:
        1. Always return a TABLE first
        2. Show raw result sets as markdown tables
        3. Provide concise summaries after tables
        4. Follow the specific formatting requirements outlined in instructions.md
        
        When users request diagnostics information, use the appropriate Kusto queries from instructions.md
        and execute them through the Kusto MCP server tools.
        """
        
        # Create AssistantAgent with model client
        print(f"[DEBUG] Creating AssistantAgent...")
        agent = AssistantAgent(
            name="IntuneExpert",
            model_client=model_client,
            system_message=system_message,
        )
        print(f"[DEBUG] AssistantAgent created successfully: {agent}")
        
        return agent
    
    async def setup_agent(self, model_config: ModelConfiguration):
        """Set up IntuneExpert agent"""
        try:
            logger.info(f"[DEBUG] Setting up agent with model config: {model_config.model_name}")
            # Create the IntuneExpert agent
            self.intune_expert_agent = await self.create_intune_expert_agent(model_config)
            logger.info(f"[DEBUG] Agent setup completed successfully")
            # Force early MCP (Kusto) service initialization so it's ready for first chat
            try:
                from services.kusto_mcp_service import get_kusto_service
                kusto_service = await get_kusto_service()
                logger.info(f"[DEBUG] Kusto MCP pre-initialized (tools={getattr(kusto_service, '_tool_names', [])})")
            except Exception as mcp_err:  # noqa: BLE001
                logger.error(f"[DEBUG] Failed to pre-initialize Kusto MCP service: {mcp_err}")
                # Escalate so caller knows agent setup incomplete
                raise
            return True
        except Exception as e:
            error_msg = f"Failed to setup agent: {str(e)}"
            print(f"[DEBUG] Agent setup failed: {error_msg}")
            print(f"[DEBUG] Exception type: {type(e)}")
            print(f"[DEBUG] Exception args: {e.args}")
            raise Exception(error_msg)
    
    async def query_diagnostics(self, query_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute diagnostic query through the agent with Kusto MCP integration"""
        if not self.intune_expert_agent:
            raise Exception("Agent not initialized")
        
        try:
            print(f"[DEBUG] Starting query_diagnostics for query_type: {query_type}")
            # Import here to avoid circular imports
            from services.kusto_mcp_service import get_kusto_service
            
            print(f"[DEBUG] Getting Kusto MCP service...")
            # Get Kusto MCP service
            kusto_service = await get_kusto_service()
            print(f"[DEBUG] Kusto MCP service obtained: {kusto_service}")
            
            # Execute the appropriate query based on type
            kusto_result = None
            
            if query_type == "device_details":
                device_id = parameters.get("device_id") or parameters.get("deviceid")
                if not device_id:
                    raise Exception("Device ID is required for device details query")
                kusto_result = await kusto_service.get_device_details(device_id)
                
            elif query_type == "compliance":
                device_id = parameters.get("device_id") or parameters.get("deviceid")
                if not device_id:
                    raise Exception("Device ID is required for compliance query")
                kusto_result = await kusto_service.get_compliance_status(device_id)
                
            elif query_type == "policy_status":
                device_id = parameters.get("device_id") or parameters.get("deviceid")
                context_id = parameters.get("context_id") or parameters.get("contextid")
                if not device_id or not context_id:
                    raise Exception("Both Device ID and Context ID are required for policy status query")
                kusto_result = await kusto_service.get_policy_status(context_id, device_id)
                
            elif query_type == "user_lookup":
                device_id = parameters.get("device_id") or parameters.get("deviceid")
                if not device_id:
                    raise Exception("Device ID is required for user lookup query")
                kusto_result = await kusto_service.get_user_lookup(device_id)
                
            elif query_type == "tenant_info":
                account_id = parameters.get("account_id") or parameters.get("accountid")
                if not account_id:
                    raise Exception("Account ID is required for tenant info query")
                kusto_result = await kusto_service.get_tenant_info(account_id)
                
            elif query_type == "effective_groups":
                device_id = parameters.get("device_id") or parameters.get("deviceid")
                account_id = parameters.get("account_id") or parameters.get("accountid")
                if not device_id or not account_id:
                    raise Exception("Both Device ID and Account ID are required for effective groups query")
                kusto_result = await kusto_service.get_effective_groups(account_id, device_id)
                
            elif query_type == "applications":
                device_id = parameters.get("device_id") or parameters.get("deviceid")
                context_id = parameters.get("context_id") or parameters.get("contextid")
                if not device_id or not context_id:
                    raise Exception("Both Device ID and Context ID are required for applications query")
                kusto_result = await kusto_service.get_applications(context_id, device_id)
                
            elif query_type == "mam_policy":
                device_id = parameters.get("device_id") or parameters.get("deviceid")
                context_id = parameters.get("context_id") or parameters.get("contextid")
                if not device_id or not context_id:
                    raise Exception("Both Device ID and Context ID are required for MAM policy query")
                kusto_result = await kusto_service.get_mam_policy(context_id, device_id)
            elif query_type == "scenario":
                scenario_ref = parameters.get("scenario") or parameters.get("name") or parameters.get("index")
                if scenario_ref is None:
                    raise Exception("Parameter 'scenario' (name substring or index) is required for scenario execution")
                # Convert numeric indices passed as strings
                try:
                    if isinstance(scenario_ref, str) and scenario_ref.isdigit():
                        scenario_ref_val: Union[int, str] = int(scenario_ref)
                    else:
                        scenario_ref_val = scenario_ref
                except ValueError:
                    scenario_ref_val = scenario_ref
                scenario_run = await self.run_instruction_scenario(scenario_ref_val)  # type: ignore[arg-type]
                for t in scenario_run.get("tables", []):
                    self.state.update_from_table(t)
                self.state.record_action("scenario", {"scenario": scenario_ref})
                return {
                    "query_type": "scenario",
                    "scenario": scenario_run.get("scenario"),
                    "description": scenario_run.get("description"),
                    "parameters": parameters,
                    "tables": scenario_run.get("tables", []),
                    "summary": scenario_run.get("summary"),
                    "errors": scenario_run.get("errors", []),
                    "state": self.state.snapshot(),
                }
                
            else:
                raise Exception(f"Unknown query type: {query_type}")
            
            # Check if query was successful
            if kusto_result.get("success"):
                summary = await self._generate_summary(query_type, kusto_result, parameters)
                table_obj = kusto_result.get("table", {})
                self.state.update_from_table(table_obj)
                self.state.record_action(query_type, parameters)
                return {
                    "query_type": query_type,
                    "parameters": parameters,
                    "tables": [table_obj],
                    "summary": summary,
                    "state": self.state.snapshot(),
                }
            else:
                # Query failed
                error_msg = kusto_result.get("error", "Unknown error occurred")
                return {
                    "query_type": query_type,
                    "parameters": parameters,
                    "tables": [{
                        "columns": ["Error"],
                        "rows": [[error_msg]],
                        "total_rows": 1
                    }],
                    "summary": f"Query failed: {error_msg}"
                }
                
        except Exception as e:
            # Return error information with debugging
            error_msg = str(e) if str(e) else f"Unknown error of type {type(e).__name__}"
            print(f"[DEBUG] Agent service error: {error_msg}")
            print(f"[DEBUG] Exception type: {type(e)}")
            print(f"[DEBUG] Exception args: {e.args}")
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
    
    async def _generate_summary(self, query_type: str, kusto_result: Dict[str, Any], parameters: Dict[str, Any]) -> str:
        """Generate AI summary based on query results"""
        try:
            table_data = kusto_result.get("table", {})
            rows = table_data.get("rows", [])
            columns = table_data.get("columns", [])
            
            if not rows:
                return f"No data found for {query_type} query."
            
            # Create a basic summary based on query type
            device_id = parameters.get("device_id", "Unknown")
            
            if query_type == "device_details":
                return f"Device details retrieved for {device_id}. Found {len(rows)} record(s). Key information includes device properties, enrollment status, and system details."
            
            elif query_type == "compliance":
                return f"Compliance status retrieved for {device_id}. Found {len(rows)} status change(s) in the last 10 days. Review the table for detailed compliance history."
            
            elif query_type == "policy_status":
                return f"Policy status retrieved for {device_id}. Found {len(rows)} policy setting(s). Check individual policy compliance and error states in the table."
            
            elif query_type == "user_lookup":
                return f"User lookup completed for {device_id}. Found {len(rows)} associated user ID(s). Review the results to identify the primary user."
            
            elif query_type == "tenant_info":
                return f"Tenant information retrieved. Found {len(rows)} tenant record(s) with details including flighting tags and scale unit information."
            
            elif query_type == "effective_groups":
                return f"Effective group memberships retrieved for {device_id}. Found {len(rows)} group association(s). This shows policy targeting and group-based assignments."
            
            elif query_type == "applications":
                return f"Application status retrieved for {device_id}. Found {len(rows)} application record(s). Review installation status and deployment details."
            
            elif query_type == "mam_policy":
                return f"MAM policy status retrieved for {device_id}. Found {len(rows)} MAM policy record(s). Check mobile application management policies and compliance."
            
            else:
                return f"Query completed successfully. Retrieved {len(rows)} record(s) from Kusto database."
                
        except Exception as e:
            return f"Summary generation failed: {str(e)}. Raw results available in table above."
    
    def _format_diagnostic_query(self, query_type: str, parameters: Dict[str, Any]) -> str:
        """Format diagnostic query based on type and parameters"""
        device_id = parameters.get("device_id", "")
        
        if query_type == "device_details":
            return f"Get device details for DeviceId: {device_id}"
        elif query_type == "compliance":
            return f"Check compliance status for DeviceId: {device_id} over the last 10 days"
        elif query_type == "policy_status":
            return f"Get policy and setting status for DeviceId: {device_id}"
        elif query_type == "user_lookup":
            return f"Find user IDs associated with DeviceId: {device_id}"
        elif query_type == "tenant_info":
            account_id = parameters.get("account_id", "")
            return f"Get tenant information for AccountId: {account_id}"
        elif query_type == "effective_groups":
            return f"Get effective group memberships for DeviceId: {device_id}"
        elif query_type == "applications":
            return f"Get application status and deployment details for DeviceId: {device_id}"
        elif query_type == "mam_policy":
            context_id = parameters.get("context_id", "")
            return f"Check MAM policy status for DeviceId: {device_id} in ContextId: {context_id}"
        else:
            return f"Execute {query_type} query with parameters: {parameters}"

    async def chat(self, message: str, extra_parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """High-level conversational entrypoint.

        1. Classify intent using keyword rules.
        2. If no direct intent, attempt scenario fuzzy match by title substring.
        3. Auto-fill missing parameters from conversation state.
        4. Delegate to query_diagnostics.
        """
        params = extra_parameters.copy() if extra_parameters else {}
        intent = classify_intent(message)

        if intent:
            needed = needed_slots_for_intent(intent)
            logger.info(f"[CHAT] Intent detected: {intent} needed={needed} raw_message='{message}' params_before={params}")
            # First: attempt heuristic resolution
            resolved, meta = resolve_entities(message, intent, needed, self.state.snapshot())
            logger.info(f"[CHAT] Heuristic resolved={resolved} ambiguities={meta.get('ambiguities')} state_before={self.state.snapshot()}")
            # Merge resolved into params if slot empty
            for slot, val in resolved.items():
                params.setdefault(slot, val)
            # BEFORE deciding clarification, try conversation state to fill missing slots
            params = self.state.fill_defaults(params)
            # Fallback GUID extraction if still missing a single required device_id
            if 'device_id' in needed and 'device_id' not in params:
                m_guid = re.search(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", message)
                if m_guid:
                    params['device_id'] = m_guid.group(0)
                    logger.info(f"[CHAT] Fallback regex captured device_id={params['device_id']}")
            logger.info(f"[CHAT] Params after state fill={params}")
            # Recompute ambiguities / missing after state fill
            ambiguous_slots = [a["slot"] for a in meta.get("ambiguities", [])]
            missing_slots = [s for s in needed if s not in params]
            if ambiguous_slots or missing_slots:
                # Only clarify if still missing after using state
                logger.info(f"[CHAT] Clarification needed ambiguous={ambiguous_slots} missing={missing_slots}")
                return {
                    "message": "Clarification needed to proceed",
                    "intent": intent,
                    "needed_slots": needed,
                    "resolved": resolved,
                    "ambiguities": meta.get("ambiguities"),
                    "candidates": meta.get("candidates"),
                    "clarification_needed": True,
                    "state": self.state.snapshot(),
                }
            # Fill remaining defaults from conversation state
            # Update state proactively with high-confidence resolved entities
            if params.get("device_id") and not self.state.device_id:
                self.state.device_id = params["device_id"]
            if params.get("account_id") and not self.state.account_id:
                self.state.account_id = params["account_id"]
            if params.get("context_id") and not self.state.context_id:
                self.state.context_id = params["context_id"]
            return await self.query_diagnostics(intent, params)

        # Attempt scenario match
        scenario_ref: Optional[str] = None
        if self.scenarios:
            low = message.lower()
            exact = [s for s in self.scenarios if s.get("title", "").lower() == low]
            if exact:
                scenario_ref = exact[0].get("title")
            else:
                partial = [s for s in self.scenarios if low in s.get("title", "").lower()]
                if partial:
                    scenario_ref = partial[0].get("title")
        if scenario_ref:
            params["scenario"] = scenario_ref
            return await self.query_diagnostics("scenario", params)
        # Fallback: if message has a GUID and mentions device, attempt device_details
        guid_match = re.search(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", message)
        if guid_match and ("device" in message.lower() or "information" in message.lower() or "detail" in message.lower()):
            fallback_device_id = guid_match.group(0)
            logger.info(f"[CHAT] Fallback auto-routing to device_details for device_id={fallback_device_id}")
            return await self.query_diagnostics("device_details", {"device_id": fallback_device_id})

        return {
            "message": message,
            "error": "Unable to classify intent or scenario. Provide more specific request (e.g., 'device details', 'compliance', or scenario title).",
            "state": self.state.snapshot(),
        }

# Global agent service instance
agent_service: Optional[AgentService] = None