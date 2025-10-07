import asyncio
import json
import os
import sys
import subprocess
import time
import logging
import re
from typing import Dict, Any, List, Optional, Iterable, Tuple
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import types
from contextlib import AsyncExitStack

# Logging is configured in main.py
logger = logging.getLogger(__name__)

MCP_PACKAGE = "@mcp-apps/kusto-mcp-server"

READONLY_BLOCK_PREFIXES = {".drop", ".alter", ".ingest", ".delete", ".set", ".create", ".append"}

class KustoMCPService:
    """Kusto MCP service using the official MCP Python SDK"""

    def __init__(self):
        self._session: Optional[ClientSession] = None
        # Manage async resources (stdio_client context) cleanly
        self._exit_stack: Optional[AsyncExitStack] = None
        self.is_initialized = False
        self._init_lock = asyncio.Lock()
        self._tool_names: List[str] = []  # cache of server tools
        # Config (can be overridden via env vars)
        self.cluster_url = os.getenv("KUSTO_CLUSTER_URL")
        self.database = os.getenv("KUSTO_DATABASE")

    async def initialize(self):
        # Ensure only one initializer runs
        async with self._init_lock:
            if self.is_initialized:
                return

            logger.info("Starting Kusto MCP server with official MCP SDK (with ClientSession context)...")

            try:
                base_cmd = "npx.cmd" if sys.platform.startswith("win") else "npx"
                args = ["-y", MCP_PACKAGE]
                init_timeout = int(os.getenv("MCP_INIT_TIMEOUT", "60"))
                logger.info(f"Spawning MCP server via stdio_client (timeout={init_timeout}s): {base_cmd} {' '.join(args)}")

                self._exit_stack = AsyncExitStack()
                server_params = StdioServerParameters(command=base_cmd, args=args)
                read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(server=server_params))
                logger.info("Acquired stdio streams from MCP server")

                # IMPORTANT: Enter ClientSession as async context so background tasks start
                self._session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))

                logger.info(f"Initializing MCP protocol (timeout={init_timeout}s)...")
                try:
                    start = time.monotonic()
                    await asyncio.wait_for(self._session.initialize(), timeout=init_timeout)
                    elapsed = time.monotonic() - start
                    logger.info(f"MCP initialize completed in {elapsed:.2f}s")
                except asyncio.TimeoutError:
                    logger.error(
                        "MCP session initialize timed out – verify the server implements the MCP handshake and increase MCP_INIT_TIMEOUT if needed."
                    )
                    raise

                # Tool discovery
                try:
                    tool_list = await self._session.list_tools()
                    self._tool_names = [t.name for t in getattr(tool_list, "tools", [])]
                    logger.info(f"Discovered tools: {', '.join(self._tool_names) or '[none]'}")
                except Exception as tool_err:
                    logger.warning(f"Failed to list tools post-initialize: {tool_err}")

                self.is_initialized = True
                logger.info("Kusto MCP server initialized successfully (session active)")
            except Exception as e:
                logger.error(f"Failed to initialize MCP service: {e}")
                await self.cleanup()
                raise RuntimeError(f"MCP initialization failed: {e}")

    async def execute_kusto_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a Kusto query via MCP"""
        if not query or not query.strip():
            return {"success": False, "error": "Empty query"}
        if any(query.strip().lower().startswith(p) for p in READONLY_BLOCK_PREFIXES):
            return {"success": False, "error": "Write/DDL command blocked"}
        
        if not self.is_initialized:
            await self.initialize()
        
        if not self._session:
            return {"success": False, "error": "MCP session not initialized"}
        
        # Ensure mandatory parameters for server tool
        # Allow explicit override, else attempt to parse from query so env vars aren't required
        cluster_url = (parameters or {}).get("clusterUrl") or self.cluster_url
        database = (parameters or {}).get("database") or self.database

        if not cluster_url or not database:
            # Try to extract first cluster("...").database("...") pattern from query
            pattern = r"cluster\([\"']([^\"']+)[\"']\)\.database\([\"']([^\"']+)[\"']\)"
            m = re.search(pattern, query)
            if m:
                cluster_url = cluster_url or m.group(1)
                database = database or m.group(2)
                logger.info(f"Parsed cluster/database from query: {cluster_url} / {database}")

        if not cluster_url or not database:
            return {"success": False, "error": "Unable to determine clusterUrl/database. Provide parameters or include cluster(\"...\").database(\"...\") in the query."}

        # Normalize cluster URL (azure-kusto-data requires full https scheme)
        if not re.match(r"^https?://", cluster_url, re.IGNORECASE):
            normalized = f"https://{cluster_url.strip()}".rstrip('/')
            logger.info(f"Normalizing cluster URL '{cluster_url}' -> '{normalized}'")
            cluster_url = normalized

        # Determine execute tool name (server uses snake_case; README shows camelCase)
        execute_tool_candidates = ["execute_query", "executeQuery"]
        # If we already know tool names, filter to those present
        if self._tool_names:
            execute_tool_candidates = [n for n in execute_tool_candidates if n in self._tool_names] or execute_tool_candidates

        last_error: Optional[str] = None
        for tool_name in execute_tool_candidates:
            try:
                logger.info(f"Calling MCP tool '{tool_name}' with query length: {len(query)} chars")
                # Acquire (cached) AAD token for the cluster
                access_token = None  # Temporarily disable accessToken passing to test if it causes 400 errors
                # try:
                #     from services.auth_service import auth_service
                #     access_token = await auth_service.get_kusto_token(cluster_url)
                # except Exception as token_err:  # noqa: BLE001
                #     logger.warning(f"Failed to acquire Kusto token (continuing unauthenticated) : {token_err}")
                #     access_token = None  # type: ignore
                
                mcp_params = {
                    "clusterUrl": cluster_url, 
                    "database": database, 
                    "query": query, 
                    **({} if parameters is None else parameters), 
                    # **({"accessToken": access_token} if access_token else {})  # DISABLED - may cause 400 errors
                }
                
                logger.debug(f"MCP call params (keys): {list(mcp_params.keys())}")
                result = await self._session.call_tool(tool_name, mcp_params)
                return self._normalize_tool_result(result)
            except Exception as e:  # noqa: BLE001
                last_error = str(e)
                logger.error(f"Tool '{tool_name}' failed with error: {type(e).__name__}: {e}")
                logger.error(f"Error details - cluster: {cluster_url}, db: {database}, query length: {len(query)}")
        
        return {"success": False, "error": f"Error executing Kusto query: {last_error or 'Unknown MCP tool invocation failure'}"}


    def _normalize_tool_result(self, result) -> Dict[str, Any]:
        """Normalize MCP tool result to our expected format"""
        try:
            # The server currently sends text content like:
            #  "Query results: {json}"
            #  or errors starting with "Error ..."
            if hasattr(result, 'content') and result.content:
                # Aggregate all text parts
                texts: List[str] = []
                for item in result.content:  # type: ignore[attr-defined]
                    text_val = getattr(item, 'text', None)
                    if text_val:
                        texts.append(text_val)
                combined = "\n".join(texts)
                if not combined:
                    return {"success": True, "table": {"columns": ["Content"], "rows": [[str(result.content[0])]], "total_rows": 1}}

                # Check for error messages first
                if combined.startswith("Error") or "failed" in combined.lower() or "status code" in combined.lower():
                    logger.error(f"MCP server returned error: {combined}")
                    return {"success": False, "error": combined}

                # Extract JSON after prefix if present
                if combined.startswith("Query results:"):
                    json_part = combined.split(":", 1)[1].strip()
                    try:
                        data = json.loads(json_part)
                        # If data has primaryResults shape from kustoService executeQuery -> may include data property
                        if isinstance(data, dict):
                            # Try to locate rows
                            rows = data.get('data') or data.get('rows') or data.get('table') or data
                            if isinstance(rows, list):
                                # Derive columns from first row keys
                                if rows and isinstance(rows[0], dict):
                                    columns = list(rows[0].keys())
                                    # Convert dict rows to list-of-values
                                    row_list = [[r.get(c) for c in columns] for r in rows]
                                else:
                                    columns = ["Value"]
                                    row_list = [[r] for r in rows]
                                return {"success": True, "table": {"columns": columns, "rows": row_list, "total_rows": len(row_list)}}
                    except json.JSONDecodeError:
                        pass  # fall back to raw text

                # Return raw text if not parseable JSON
                return {"success": True, "table": {"columns": ["Result"], "rows": [[combined]], "total_rows": 1}}

            return {"success": True, "table": {"columns": ["Data"], "rows": [[str(result)]], "total_rows": 1}}
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to normalize tool result: {e}")
            return {"success": False, "error": f"Failed to process result: {e}"}
    
    async def cleanup(self):
        """Clean up resources"""
        # Close any managed async contexts
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.error(f"Error closing MCP stdio context: {e}")

        self._exit_stack = None
        self._session = None
        self.is_initialized = False

    async def prewarm_tokens(self, queries: List[str]) -> None:
        """Attempt to pre-acquire access tokens for clusters referenced in queries.

        Extracts cluster("<cluster>").database("<db>") patterns and asks AuthService for tokens
        so that interactive auth (WAM) happens once at startup instead of per scenario.
        """
        pattern = r"cluster\([\"']([^\"']+)[\"']\)\.database\([\"']([^\"']+)[\"']\)"
        seen: set[tuple[str, str]] = set()
        from services.auth_service import auth_service
        for q in queries:
            try:
                m = re.search(pattern, q)
                if not m:
                    continue
                cluster_url, database = m.group(1), m.group(2)
                key = (cluster_url, database)
                if key in seen:
                    continue
                seen.add(key)
                # Normalize cluster URL and request token (cached in AuthService)
                if not re.match(r"^https?://", cluster_url, re.IGNORECASE):
                    cluster_url_norm = f"https://{cluster_url.strip()}".rstrip('/')
                else:
                    cluster_url_norm = cluster_url.rstrip('/')
                try:
                    await auth_service.get_kusto_token(cluster_url_norm)
                    logger.info(f"Prewarmed Kusto token for {cluster_url_norm} / {database}")
                except Exception as token_err:  # noqa: BLE001
                    logger.warning(f"Failed to prewarm token for {cluster_url_norm}: {token_err}")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Prewarm parsing error ignored: {e}")
        if not seen:
            logger.info("No cluster/database patterns found during token prewarm")

    async def prewarm_mcp_sessions(self, cluster_db_pairs: List[Tuple[str, str]]) -> None:
        """Trigger lightweight MCP tool calls per cluster/database to force Node-side auth once.

        Uses only 'list_tables' if available. No fallback query to avoid extra auth prompts.
        """
        if not cluster_db_pairs:
            logger.info("No cluster/database pairs provided for MCP session prewarm")
            return
        if not self.is_initialized:
            await self.initialize()
        if not self._session:
            logger.warning("Cannot prewarm MCP sessions: session not available")
            return
        # Determine available tools (refresh if empty)
        try:
            if not self._tool_names:
                tool_list = await self._session.list_tools()
                self._tool_names = [t.name for t in getattr(tool_list, "tools", [])]
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Tool list refresh failed during prewarm: {e}")

        if "list_tables" not in self._tool_names:
            logger.info("Skipping prewarm: 'list_tables' tool not available yet")
            return

        # Deduplicate by cluster only (one auth prompt per cluster)
        seen_clusters: set[str] = set()
        for cluster_url, database in cluster_db_pairs:
            # Normalize cluster URL for uniqueness
            if not re.match(r"^https?://", cluster_url, re.IGNORECASE):
                cluster_url_norm = f"https://{cluster_url.strip()}".rstrip('/')
            else:
                cluster_url_norm = cluster_url.rstrip('/')
            host_key = cluster_url_norm.lower()
            if host_key in seen_clusters:
                continue
            seen_clusters.add(host_key)
            try:
                await self._session.call_tool("list_tables", {"clusterUrl": cluster_url_norm, "database": database})
                logger.info(f"MCP prewarm list_tables (single per cluster) success: {cluster_url_norm}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"MCP prewarm list_tables failed for {cluster_url_norm}: {e}")
# Global MCP service instance
kusto_mcp_service: Optional[KustoMCPService] = None

async def get_kusto_service() -> KustoMCPService:
    """Get or create the global Kusto MCP service instance"""
    global kusto_mcp_service
    if kusto_mcp_service is None:
        kusto_mcp_service = KustoMCPService()
        await kusto_mcp_service.initialize()
    return kusto_mcp_service