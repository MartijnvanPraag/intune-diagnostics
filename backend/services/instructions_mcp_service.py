"""
Instructions MCP Service

Manages the Instructions MCP server that provides structured access to diagnostic scenarios
and queries from instructions.md. Prevents query modification by providing exact query text
through tool interface.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional, List
from contextlib import AsyncExitStack

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# Logging is configured in main.py
logger = logging.getLogger(__name__)


class InstructionsMCPService:
    """Instructions MCP service using the official MCP Python SDK"""

    def __init__(self):
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self.is_initialized = False
        self._init_lock = asyncio.Lock()
        self._tool_names: List[str] = []  # cache of server tools

    async def initialize(self):
        """Initialize the Instructions MCP server"""
        async with self._init_lock:
            if self.is_initialized:
                return

            logger.info("Starting Instructions MCP server with official MCP SDK...")

            try:
                # The server is a Python module, so we use the Python interpreter
                python_cmd = sys.executable
                server_module = "backend.mcp_servers.instructions.server"
                
                # Get the workspace root (where backend/ is located)
                workspace_root = Path(__file__).parent.parent.parent
                
                logger.info(f"Spawning Instructions MCP server: {python_cmd} -m {server_module}")
                logger.info(f"Working directory: {workspace_root}")

                self._exit_stack = AsyncExitStack()
                server_params = StdioServerParameters(
                    command=python_cmd,
                    args=["-m", server_module],
                    env=None,
                    cwd=str(workspace_root)
                )
                
                read_stream, write_stream = await self._exit_stack.enter_async_context(
                    stdio_client(server=server_params)
                )
                logger.info("Acquired stdio streams from Instructions MCP server")

                # Enter ClientSession as async context so background tasks start
                self._session = await self._exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )

                logger.info("Initializing Instructions MCP protocol...")
                try:
                    await asyncio.wait_for(self._session.initialize(), timeout=30)
                    logger.info("Instructions MCP initialize completed")
                except asyncio.TimeoutError:
                    logger.error("Instructions MCP session initialize timed out")
                    raise

                # Tool discovery
                try:
                    tool_list = await self._session.list_tools()
                    self._tool_names = [t.name for t in getattr(tool_list, "tools", [])]
                    logger.info(f"Discovered Instructions MCP tools: {', '.join(self._tool_names)}")
                except Exception as tool_err:
                    logger.warning(f"Failed to list Instructions MCP tools: {tool_err}")

                self.is_initialized = True
                logger.info("Instructions MCP server initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize Instructions MCP server: {e}")
                # Clean up on failure
                if self._exit_stack:
                    try:
                        await self._exit_stack.aclose()
                    except Exception as cleanup_err:
                        logger.error(f"Error during cleanup: {cleanup_err}")
                    self._exit_stack = None
                self._session = None
                raise

    async def shutdown(self):
        """Clean shutdown of the MCP server"""
        logger.info("Shutting down Instructions MCP server...")
        try:
            if self._exit_stack:
                await self._exit_stack.aclose()
                logger.info("Instructions MCP server shutdown complete")
        except Exception as e:
            logger.error(f"Error during Instructions MCP shutdown: {e}")
        finally:
            self._session = None
            self._exit_stack = None
            self.is_initialized = False

    def get_tool_names(self) -> List[str]:
        """Get list of available tool names"""
        return self._tool_names.copy()


# Singleton instance
_instructions_service: Optional[InstructionsMCPService] = None


async def get_instructions_service() -> InstructionsMCPService:
    """Get or create the singleton Instructions MCP service instance"""
    global _instructions_service
    
    if _instructions_service is None:
        _instructions_service = InstructionsMCPService()
    
    if not _instructions_service.is_initialized:
        await _instructions_service.initialize()
    
    return _instructions_service


async def shutdown_instructions_service():
    """Shutdown the Instructions MCP service"""
    global _instructions_service
    
    if _instructions_service:
        await _instructions_service.shutdown()
        _instructions_service = None
