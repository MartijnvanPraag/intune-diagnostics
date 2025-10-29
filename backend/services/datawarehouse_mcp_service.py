"""
Data Warehouse MCP Service - Wrapper for Intune Data Warehouse API via MCP
"""

import asyncio
import json
import os
import sys
import time
import logging
from typing import Dict, Any, List, Optional
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import types
from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)

class DataWarehouseMCPService:
    """Service wrapper for Intune Data Warehouse MCP server"""

    def __init__(self):
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self.is_initialized = False
        self._init_lock = asyncio.Lock()
        self._tool_names: List[str] = []
        
        # Data Warehouse API configuration
        self.base_url = os.getenv("INTUNE_DATAWAREHOUSE_URL", "https://fef.msud01.manage.microsoft.com/ReportingService/DataWarehouseFEService")
        self.api_version = os.getenv("INTUNE_DATAWAREHOUSE_API_VERSION", "v1.0")

    async def initialize(self):
        """Initialize the MCP server connection"""
        async with self._init_lock:
            if self.is_initialized:
                return

            logger.info("Starting Data Warehouse MCP server...")

            try:
                # Get access token for Intune API
                from backend.services.auth_service import auth_service
                access_token = await auth_service.get_intune_datawarehouse_token()
                logger.info("Acquired Intune Data Warehouse access token")

                # Spawn TypeScript MCP server via npm
                base_cmd = "npx.cmd" if sys.platform.startswith("win") else "npx"
                server_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "mcp_servers",
                    "datawarehouse",
                    "dist",
                    "index.js"
                )
                
                # Check if server is built
                if not os.path.exists(server_path):
                    raise RuntimeError(
                        f"Data Warehouse MCP server not built. Run 'npm run build' in backend/mcp_servers/datawarehouse/"
                    )

                args = ["-y", "tsx", server_path]
                init_timeout = int(os.getenv("MCP_INIT_TIMEOUT", "60"))
                
                logger.info(f"Spawning MCP server: {base_cmd} {' '.join(args)}")

                # Set environment variables for the MCP server
                env = os.environ.copy()
                env["INTUNE_DATAWAREHOUSE_URL"] = self.base_url
                env["INTUNE_DATAWAREHOUSE_TOKEN"] = access_token
                env["INTUNE_DATAWAREHOUSE_API_VERSION"] = self.api_version

                self._exit_stack = AsyncExitStack()
                server_params = StdioServerParameters(
                    command=base_cmd,
                    args=args,
                    env=env
                )
                
                read_stream, write_stream = await self._exit_stack.enter_async_context(
                    stdio_client(server=server_params)
                )
                logger.info("Acquired stdio streams from MCP server")

                # Enter ClientSession as async context
                self._session = await self._exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )

                logger.info(f"Initializing MCP protocol (timeout={init_timeout}s)...")
                try:
                    start = time.monotonic()
                    await asyncio.wait_for(self._session.initialize(), timeout=init_timeout)
                    elapsed = time.monotonic() - start
                    logger.info(f"MCP initialize completed in {elapsed:.2f}s")
                except asyncio.TimeoutError:
                    logger.error("MCP session initialize timed out")
                    raise

                # Discover available tools
                try:
                    tool_list = await self._session.list_tools()
                    self._tool_names = [t.name for t in getattr(tool_list, "tools", [])]
                    logger.info(f"Discovered tools: {', '.join(self._tool_names)}")
                except Exception as tool_err:
                    logger.warning(f"Failed to list tools: {tool_err}")

                self.is_initialized = True
                logger.info("Data Warehouse MCP server initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize Data Warehouse MCP service: {e}")
                await self.cleanup()
                raise RuntimeError(f"MCP initialization failed: {e}")

    async def list_entities(self) -> Dict[str, Any]:
        """List all available Data Warehouse entities"""
        if not self.is_initialized:
            await self.initialize()
        
        if not self._session:
            return {"success": False, "error": "MCP session not initialized"}
        
        try:
            logger.info("Calling list_entities tool")
            result = await self._session.call_tool("list_entities", {})
            return self._normalize_tool_result(result)
        except Exception as e:
            logger.error(f"Error calling list_entities: {e}")
            return {"success": False, "error": str(e)}

    async def get_entity_schema(self, entity: str) -> Dict[str, Any]:
        """Get schema for a specific entity"""
        if not self.is_initialized:
            await self.initialize()
        
        if not self._session:
            return {"success": False, "error": "MCP session not initialized"}
        
        try:
            logger.info(f"Getting schema for entity: {entity}")
            result = await self._session.call_tool("get_entity_schema", {"entity": entity})
            return self._normalize_tool_result(result)
        except Exception as e:
            logger.error(f"Error getting entity schema: {e}")
            return {"success": False, "error": str(e)}

    async def query_entity(
        self,
        entity: str,
        select: Optional[str] = None,
        filter: Optional[str] = None,
        orderby: Optional[str] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        expand: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query an entity with OData parameters.
        
        IMPORTANT LIMITATIONS (as of Oct 2025):
        - $filter parameter causes HTTP 400 errors for deviceId filtering
        - $select parameter causes HTTP 400 errors for column selection
        - API returns all ~39 fields per device record
        - Use find_device_by_id() for client-side filtering instead
        
        For reliable queries, use only 'top', 'skip', and 'orderby' parameters.
        """
        if not self.is_initialized:
            await self.initialize()
        
        if not self._session:
            return {"success": False, "error": "MCP session not initialized"}
        
        try:
            params: Dict[str, Any] = {"entity": entity}
            if select:
                params["select"] = select
            if filter:
                params["filter"] = filter
            if orderby:
                params["orderby"] = orderby
            if top is not None:
                params["top"] = int(top) if not isinstance(top, int) else top
            if skip is not None:
                params["skip"] = int(skip) if not isinstance(skip, int) else skip
            if expand:
                params["expand"] = expand
            
            logger.info(f"Querying entity '{entity}' with params: {list(params.keys())}")
            result = await self._session.call_tool("query_entity", params)
            return self._normalize_tool_result(result)
        except Exception as e:
            logger.error(f"Error querying entity: {e}")
            return {"success": False, "error": str(e)}

    async def find_device_by_id(self, device_id: str, max_results: int = 100) -> Dict[str, Any]:
        """
        Find a device by deviceId using client-side filtering.
        
        This is a workaround for the Data Warehouse API's limitation where
        $filter parameter causes HTTP 400 errors. Instead, we fetch devices
        and filter client-side.
        
        Args:
            device_id: The device GUID to search for
            max_results: Maximum number of devices to fetch for searching (default: 100)
            
        Returns:
            Dict with structure:
            {
                "success": True/False,
                "data": {
                    "device": {...},  # The found device record, or None if not found
                    "searched": N,    # Number of devices searched
                    "found": True/False
                }
            }
        """
        try:
            logger.info(f"Searching for device {device_id} (client-side filtering, max {max_results} devices)")
            
            # Query devices without filter
            result = await self.query_entity(entity="devices", top=max_results)
            
            if not result.get("success"):
                return result
            
            # Extract actual data from wrapped response
            actual_data = result.get("data")
            
            if not isinstance(actual_data, dict) or "value" not in actual_data:
                return {"success": False, "error": "No 'value' array in API response"}
            
            devices = actual_data["value"]
            logger.info(f"Retrieved {len(devices)} devices, searching for deviceId={device_id}")
            
            # Search for the target device
            target_device = None
            for device in devices:
                if device.get("deviceId") == device_id:
                    target_device = device
                    logger.info(f"Found device: {device.get('deviceName', 'Unknown')}")
                    break
            
            return {
                "success": True,
                "data": {
                    "device": target_device,
                    "searched": len(devices),
                    "found": target_device is not None
                }
            }
            
        except Exception as e:
            logger.error(f"Error finding device by ID: {e}")
            return {"success": False, "error": str(e)}

    async def execute_odata_query(self, url: str) -> Dict[str, Any]:
        """Execute a raw OData query URL"""
        if not self.is_initialized:
            await self.initialize()
        
        if not self._session:
            return {"success": False, "error": "MCP session not initialized"}
        
        try:
            logger.info(f"Executing OData query: {url[:100]}...")
            result = await self._session.call_tool("execute_odata_query", {"url": url})
            return self._normalize_tool_result(result)
        except Exception as e:
            logger.error(f"Error executing OData query: {e}")
            return {"success": False, "error": str(e)}

    def _normalize_tool_result(self, result: types.CallToolResult) -> Dict[str, Any]:
        """Normalize MCP tool result to dict format"""
        try:
            if not result.content:
                return {"success": False, "error": "Empty result from MCP server"}
            
            # Extract text content
            content_items = result.content if isinstance(result.content, list) else [result.content]
            text_content = []
            
            for item in content_items:
                if hasattr(item, 'text') and hasattr(item, 'type') and item.type == 'text':
                    text_content.append(item.text)
                elif isinstance(item, dict) and 'text' in item:
                    text_content.append(item['text'])
            
            if not text_content:
                return {"success": False, "error": "No text content in result"}
            
            # Try to parse as JSON
            combined_text = '\n'.join(text_content)
            try:
                parsed = json.loads(combined_text)
                return {"success": True, "data": parsed}
            except json.JSONDecodeError:
                # Return raw text if not JSON
                return {"success": True, "data": combined_text}
                
        except Exception as e:
            logger.error(f"Error normalizing tool result: {e}")
            return {"success": False, "error": f"Failed to normalize result: {str(e)}"}

    async def cleanup(self):
        """Clean up resources"""
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
                logger.info("Data Warehouse MCP exit stack closed")
            except Exception as e:
                logger.error(f"Error closing exit stack: {e}")
            finally:
                self._exit_stack = None
                self._session = None
                self.is_initialized = False

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()
        return False


# Global service instance
datawarehouse_mcp_service: DataWarehouseMCPService | None = None


async def get_datawarehouse_service() -> DataWarehouseMCPService:
    """Get or create the global Data Warehouse MCP service instance"""
    global datawarehouse_mcp_service
    if datawarehouse_mcp_service is None:
        datawarehouse_mcp_service = DataWarehouseMCPService()
        await datawarehouse_mcp_service.initialize()
    return datawarehouse_mcp_service
