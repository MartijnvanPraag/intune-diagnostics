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
import math
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, AsyncGenerator
from numbers import Number
try:  # numpy optional
    import numpy as _np  # type: ignore
except Exception:  # noqa: BLE001
    _np = None

# Logging is configured in main.py
logger = logging.getLogger(__name__)

# Buffer to hold recent MCP tool normalized results (tables) because Agent Framework
# streaming events are not currently exposing function result payloads needed for
# table reconstruction. This allows a fallback after workflow completion.
TOOL_RESULTS_BUFFER: list[dict[str, Any]] = []

# Scenario execution lock (generic) – when set, only queries belonging to the locked
# scenario may be executed (whitespace/placeholder tolerant). This is NOT scenario-specific
# logic; it is a generic isolation guard to ensure that if a scenario (e.g., one-query
# compliance scenario) is selected, the agent does not autonomously chain unrelated
# queries. Cleared implicitly when a new scenario lookup happens with ambiguous/low confidence.
SCENARIO_LOCK: dict[str, Any] | None = None
# Global allow list of all fenced kusto queries in instructions (patterns + hashes)
GLOBAL_KUSTO_ALLOW: dict[str, Any] | None = None

def _compile_placeholder_tolerant_pattern(templ: str) -> re.Pattern[str] | None:
    """Return a compiled regex that tolerates placeholder substitution & arbitrary whitespace.

    Rules:
    - Any <PlaceholderName> becomes a non-greedy wildcard (.+?)
    - All whitespace (spaces, newlines, tabs) collapses to \\s+
    - Leading/trailing whitespace ignored
    - DOTALL so multi-line queries match
    """
    try:
        work = templ.replace('\r\n', '\n')
        ph_tokens = re.findall(r"<[^<>]+>", work)
        ph_map: dict[str,str] = {}
        for idx, ph in enumerate(ph_tokens):
            marker = f"__PH_{idx}__"
            ph_map[marker] = ph
            work = work.replace(ph, marker)
        esc = re.escape(work)
        for marker in ph_map.keys():
            esc = esc.replace(re.escape(marker), r".+?")
        # After escaping, whitespace/newlines represented as \n, space as space etc. Collapse any run of escaped ws tokens
        esc = re.sub(r"(?:\\[nrtf]|\\ )+", r"\\s+", esc)
        esc = re.sub(r"(?:\\s\+){2,}", r"\\s+", esc)
        pattern_text = rf"^\s*{esc}\s*$"
        return re.compile(pattern_text, re.DOTALL)
    except re.error:
        logger.warning("[ScenarioLock] Pattern compile failed length=%d", len(templ))
        return None

def _strip_leading_let_block(q: str) -> str:
    """Remove a contiguous leading block of `let <identifier> = ...;` definitions.

    This allows acceptance of queries where the agent prepends local variable declarations
    (e.g., DeviceID, AccountID) before the canonical fenced query body.
    """
    lines = q.replace('\r\n','\n').split('\n')
    out = []
    skipping = True
    for line in lines:
        if skipping and re.match(r"^\s*let\s+[A-Za-z_][A-Za-z0-9_]*\s*=.*;\s*$", line):
            continue
        skipping = False
        out.append(line)
    return "\n".join(out)
def _build_global_kusto_allow(instructions_path: Path) -> dict[str, Any]:
    """Extract every fenced ```kusto block from instructions.md and build hash + regex patterns.

    This ignores scenario structure and provides a canonical allow-list so ANY query that exactly
    matches a fenced block (modulo placeholder substitution + whitespace) is accepted.
    """
    import hashlib as _hashlib, re as _re
    text = instructions_path.read_text(encoding='utf-8')
    blocks = _re.findall(r"```kusto\s*\n(.*?)\n```", text, _re.DOTALL | _re.IGNORECASE)
    patterns: list[_re.Pattern[str]] = []
    hashes: list[str] = []
    originals: list[str] = []
    for b in blocks:
        qb = b.strip()
        if not qb:
            continue
        originals.append(qb)
        # placeholder tolerant pattern
        templ = qb
        placeholder_tokens = _re.findall(r"<[^<>]+>", templ)
        ph_map: dict[str,str] = {}
        for idx, ph in enumerate(placeholder_tokens):
            marker = f"__PH_G_{idx}__"
            ph_map[marker] = ph
            templ = templ.replace(ph, marker)
        esc = _re.escape(templ)
        for marker, ph in ph_map.items():
            esc = esc.replace(_re.escape(marker), r".+?")
        esc = _re.sub(r"\\ +", r"\\s+", esc)
        pattern_text = rf"^\s*{esc}\s*$"
        try:
            patterns.append(_re.compile(pattern_text, _re.DOTALL))
        except _re.error:
            pass
        h = _hashlib.sha256(_normalize_query_for_hash(qb).encode('utf-8')).hexdigest()
        hashes.append(h)
    logger.info(f"[GlobalKustoAllow] Extracted {len(originals)} fenced kusto block(s)")
    return {
        'patterns': patterns,
        'hashes': hashes,
        'raw': originals
    }

def _normalize_query_for_hash(q: str) -> str:
    """Produce a stable normalization for query hashing.

    Steps:
    - Convert CRLF to LF
    - Strip leading/trailing whitespace
    - Collapse runs of whitespace (space, tab, newline) to a single space
    - Replace placeholder angle blocks <...> with canonical token <PH>
    """
    import re as _re
    q2 = q.replace('\r\n', '\n')
    # Replace placeholders with canonical marker
    q2 = _re.sub(r"<[^<>]+>", "<PH>", q2)
    # Collapse whitespace
    q2 = _re.sub(r"\s+", " ", q2).strip()
    return q2

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
# Legacy scenario_lookup_service import removed for semantic-only agent framework path
from services.semantic_scenario_search import get_semantic_search


def create_scenario_lookup_function() -> Callable[..., Awaitable[str]]:
    """Create a function for looking up scenarios from instructions.md using semantic search
    
    This function uses FAISS-based semantic search to find relevant scenarios,
    which is much more robust than keyword matching.
    """
    
    async def lookup_scenarios(user_request: str, max_scenarios: int = 3) -> str:
        """Hybrid semantic scenario lookup returning structured JSON + markdown.

        ALWAYS returns a JSON object as the first line so the agent can parse reliably.
        The JSON contains: status, query, scenarios (with scores, placeholders, penalties),
        and recommended (single slug) unless ambiguous/low_confidence.
        """
        try:
            semantic_search = await get_semantic_search()
            logger.info(f"[AgentFramework] Scenario lookup (semantic-only) called with: '{user_request}'")
            if not semantic_search or not semantic_search._initialized:
                return json.dumps({
                    "status": "not_ready",
                    "query": user_request,
                    "message": "Semantic search not initialized",
                    "scenarios": []
                })

            scored = semantic_search.search_with_scores(user_request, max_results=max_scenarios)
            if not scored:
                return json.dumps({
                    "status": "no_match",
                    "query": user_request,
                    "scenarios": [],
                    "message": "No matching scenarios"
                }) + "\nNo matching scenarios."

            # Attach human titles & queries
            def _json_safe(value: Any) -> Any:
                """Recursively convert values to JSON-serializable Python primitives.

                Handles numpy scalars, floats (including NaN/inf), and nested containers.
                """
                # Numpy scalar
                if _np is not None and isinstance(value, (_np.generic,)):
                    return value.item()
                # Basic primitives
                if isinstance(value, (str, bool)) or value is None:
                    return value
                if isinstance(value, (int,)):
                    return int(value)
                if isinstance(value, float):
                    if math.isnan(value) or math.isinf(value):
                        return None
                    return float(value)
                # Support common numeric extras without broad Number which confuses type checkers
                try:
                    from decimal import Decimal
                    if isinstance(value, Decimal):
                        return float(value)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    from fractions import Fraction
                    if isinstance(value, Fraction):
                        return float(value)
                except Exception:  # noqa: BLE001
                    pass
                if isinstance(value, dict):
                    return {str(k): _json_safe(v) for k, v in value.items()}
                if isinstance(value, (list, tuple, set)):
                    return [_json_safe(v) for v in value]
                return str(value)

            detailed_payload: list[dict[str, Any]] = []
            for s in scored:
                norm_title = s['normalized_title']
                scenario = semantic_search.get_scenario_by_normalized(norm_title)
                if scenario:
                    merged = {
                        **s,
                        'title': scenario.get('title'),
                        'queries': scenario.get('queries', []),
                        'query_count': len(scenario.get('queries', []))
                    }
                    detailed_payload.append(_json_safe(merged))
                else:
                    detailed_payload.append(_json_safe(s))

            # Determine status with tie-break heuristics for compliance vs policy ambiguity
            status = 'ok'
            recommended = None
            margin = None
            if len(detailed_payload) >= 2:
                margin = detailed_payload[0]['score'] - detailed_payload[1]['score']
                if margin < 0.05:
                    # Potential ambiguity – apply heuristics to break tie instead of defaulting to ambiguous
                    top = detailed_payload[0]
                    second = detailed_payload[1]
                    qtext_lower = user_request.lower()
                    def _is_compliance_candidate(item: dict[str, Any]) -> bool:
                        nt = item.get('normalized_title','')
                        title = item.get('title','').lower()
                        return ('compliance' in nt) or ('compliance' in title)
                    def _is_policy_candidate(item: dict[str, Any]) -> bool:
                        nt = item.get('normalized_title','')
                        title = item.get('title','').lower()
                        return ('policy' in nt) or ('policy' in title) or ('setting' in title)
                    # Heuristic 1: If both compliance and policy present & user mentions 'compliance' but not 'setting' or 'assignment', prefer compliance
                    user_mentions_setting_like = any(k in qtext_lower for k in ['setting','assignment','assignments'])
                    if _is_compliance_candidate(top) and _is_policy_candidate(second) and not user_mentions_setting_like:
                        # keep top
                        pass
                    elif _is_compliance_candidate(second) and _is_policy_candidate(top) and not user_mentions_setting_like:
                        # swap preference to compliance
                        detailed_payload[0], detailed_payload[1] = detailed_payload[1], detailed_payload[0]
                        margin = detailed_payload[0]['score'] - detailed_payload[1]['score']
                    else:
                        # Heuristic 2: If scores nearly identical (<0.02) choose simpler (fewer queries) scenario
                        if margin < 0.02:
                            if second.get('query_count', 0) == 1 and top.get('query_count', 0) > 1:
                                detailed_payload[0], detailed_payload[1] = detailed_payload[1], detailed_payload[0]
                                margin = detailed_payload[0]['score'] - detailed_payload[1]['score']
                            elif top.get('query_count', 0) == 1 and second.get('query_count', 0) > 1:
                                # Already simplest on top
                                pass
                            # Heuristic 3: Favor scenario whose title directly contains all non-stopword compliance tokens when user query contains 'compliance'
                            elif 'compliance' in qtext_lower:
                                # If second has compliance token and first does not, swap
                                if _is_compliance_candidate(second) and not _is_compliance_candidate(top):
                                    detailed_payload[0], detailed_payload[1] = detailed_payload[1], detailed_payload[0]
                                    margin = detailed_payload[0]['score'] - detailed_payload[1]['score']
                    # After heuristics, if still very close (<0.015) treat as ambiguous; else proceed
                    if margin is not None and margin < 0.015:
                        status = 'ambiguous'
                # end margin check
            # Low confidence override
            if detailed_payload and detailed_payload[0]['score'] < 0.45:
                status = 'low_confidence'
            if status == 'ok':
                recommended = detailed_payload[0]['normalized_title']
            if status == 'ambiguous':
                logger.info("[ScenarioLookup] Ambiguous after heuristics (margin=%s) top=%s second=%s", margin, detailed_payload[0]['title'], detailed_payload[1]['title'])
            # Build / update scenario lock if we have a confident single recommendation
            global SCENARIO_LOCK
            # Ensure global allow list is initialized
            global GLOBAL_KUSTO_ALLOW
            if GLOBAL_KUSTO_ALLOW is None:
                try:
                    GLOBAL_KUSTO_ALLOW = _build_global_kusto_allow(semantic_search.instructions_path)
                except Exception as gerr:  # noqa: BLE001
                    logger.warning(f"[GlobalKustoAllow] Failed to build: {gerr}")

            if recommended:
                try:
                    # Retrieve full scenario for query templates
                    scenario = semantic_search.get_scenario_by_normalized(recommended)
                    scenario_queries = scenario.get('queries', []) if scenario else []
                    # Fallback: if parser yielded zero queries (e.g., single inline block not captured),
                    # re-extract from raw instructions section using a lightweight regex.
                    if scenario and not scenario_queries:
                        # The semantic parser may have dropped code fences; re-read instructions.md section via title search
                        try:
                            instructions_text = semantic_search.instructions_path.read_text(encoding='utf-8')
                            import re as _re
                            scen_title = scenario.get('title') or ''
                            if scen_title:
                                pattern = _re.compile(rf"###\s+{_re.escape(scen_title)}\s+(.*?)(?=\n### |\Z)", _re.DOTALL)
                                m = pattern.search(instructions_text)
                                if m:
                                    section_text = m.group(1)
                                    code_blocks = _re.findall(r"```kusto\s*\n(.*?)\n```", section_text, _re.DOTALL)
                                    if code_blocks:
                                        scenario_queries = [cb.strip() for cb in code_blocks if cb.strip()]
                                        logger.info(
                                            "[ScenarioLock][Fallback] Extracted %d query block(s) directly from instructions for '%s'",
                                            len(scenario_queries), scen_title
                                        )
                        except Exception as fb_err:  # noqa: BLE001
                            logger.warning(f"[ScenarioLock][Fallback] Failed inline extraction: {fb_err}")
                    # Compile tolerant regex patterns using unified helper
                    patterns: list[re.Pattern[str]] = []
                    for qt in scenario_queries:
                        pat = _compile_placeholder_tolerant_pattern(qt)
                        if pat:
                            patterns.append(pat)
                    # Build hash list for stable enforcement (include function-only variants if applicable)
                    import hashlib as _hashlib
                    hashes: list[str] = []
                    # Collect potential variant queries (original + function-only when pattern recognized)
                    variant_queries: list[str] = []
                    func_variant_added = 0
                    func_call_regex = re.compile(r"cluster\(.*?\)\.database\(.*?\)\.([A-Za-z0-9_]+\(.*\))\s*$", re.DOTALL)
                    enable_variants = os.getenv("ENABLE_FUNCTION_VARIANTS", "1") == "1"
                    for original_q in scenario_queries:
                        variant_queries.append(original_q)
                        if enable_variants:
                            mfun = func_call_regex.search(original_q)
                            if mfun:
                                core_call = mfun.group(1).strip()
                                if core_call not in variant_queries:
                                    variant_queries.append(core_call)
                                    func_variant_added += 1
                                    pat_core = _compile_placeholder_tolerant_pattern(core_call)
                                    if pat_core:
                                        patterns.append(pat_core)
                    if func_variant_added:
                        logger.info(f"[ScenarioLock] Added {func_variant_added} function-only variant(s) for scenario '{recommended}'")
                    for oq in variant_queries:
                        norm = _normalize_query_for_hash(oq)
                        h = _hashlib.sha256(norm.encode('utf-8')).hexdigest()
                        if h not in hashes:
                            hashes.append(h)
                    SCENARIO_LOCK = {
                        'scenario': recommended,
                        'patterns': patterns,
                        'query_count': len(patterns),
                        'strict': True,
                        'title': scenario.get('title') if scenario else recommended,
                        'extracted_queries': scenario_queries,
                        'hashes': hashes,
                    }
                    parser_original = len(scenario.get('queries', [])) if scenario else -1
                    variant_ct = max(0, len(patterns) - parser_original) if parser_original >=0 else 0
                    logger.info(
                        "[ScenarioLock] Locked to scenario '%s' with %d allowed pattern(s) (%d original + %d variant); parser_original=%d hash_count=%d",
                        SCENARIO_LOCK['title'], len(patterns), parser_original, variant_ct, parser_original, len(hashes)
                    )
                    if not patterns:
                        logger.warning(
                            "[ScenarioLock] No queries captured for scenario '%s' – scenario-level enforcement inactive; global allow-list still applies.",
                            SCENARIO_LOCK['title']
                        )
                except Exception as lock_err:  # noqa: BLE001
                    logger.warning(f"[ScenarioLock] Failed to establish lock: {lock_err}")
            else:
                # Ambiguous / low confidence – clear lock to allow disambiguation
                if SCENARIO_LOCK is not None:
                    logger.info("[ScenarioLock] Cleared due to ambiguous or low confidence lookup result")
                SCENARIO_LOCK = None

            result_obj = _json_safe({
                'status': status,
                'query': user_request,
                'recommended': recommended,
                'scenarios': detailed_payload
            })

            # Markdown summary for readability
            md_lines = ["# Scenario Suggestions", f"Status: {status}"]
            if status != 'ok':
                md_lines.append("(Agent should confirm or ask clarifying question.)")
            for i, s in enumerate(detailed_payload, 1):
                md_lines.append(f"## {i}. {s.get('title', s['normalized_title'])} (score={s['score']})")
                if 'queries' in s:
                    for q in s['queries'][:2]:  # show at most first 2 queries preview
                        preview = q.split('\n')[0][:100]
                        md_lines.append(f"`{preview}...`")
                if s.get('placeholders'):
                    missing = s.get('missing_placeholders') or []
                    md_lines.append(f"Placeholders: {s['placeholders']}  Missing: {missing}")
            md_output = "\n".join(md_lines)

            return json.dumps(result_obj) + "\n" + md_output
        except Exception as e:  # noqa: BLE001
            logger.error(f"[AgentFramework] Error in scenario lookup: {e}")
            return json.dumps({
                "status": "error",
                "query": user_request,
                "error": str(e)
            })
    
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
                    
                    # Pass parameters directly to MCP server – but first enforce scenario lock if present
                    global SCENARIO_LOCK
                    enforced = False
                    if SCENARIO_LOCK and SCENARIO_LOCK.get('strict'):
                        enforced = True
                        substituted_query = query
                        norm_full = _normalize_query_for_hash(substituted_query)
                        import hashlib as _hashlib
                        h_full = _hashlib.sha256(norm_full.encode('utf-8')).hexdigest()
                        patterns: list[re.Pattern[str]] = SCENARIO_LOCK.get('patterns') or []
                        normalized_incoming = substituted_query.replace('\r\n','\n').strip()
                        match_ok = any(p.fullmatch(normalized_incoming) for p in patterns)
                        hash_ok = h_full in (SCENARIO_LOCK.get('hashes') or [])
                        if not (match_ok or hash_ok):
                            # Try global allow list
                            global GLOBAL_KUSTO_ALLOW
                            global_ok = False
                            if GLOBAL_KUSTO_ALLOW:
                                g_patterns: list[re.Pattern[str]] = GLOBAL_KUSTO_ALLOW.get('patterns') or []
                                g_hashes = GLOBAL_KUSTO_ALLOW.get('hashes') or []
                                g_match = any(p.fullmatch(normalized_incoming) for p in g_patterns)
                                g_hash_ok = h_full in g_hashes
                                global_ok = g_match or g_hash_ok
                                if global_ok:
                                    logger.info("[GlobalKustoAllow] Accepted query outside scenario lock via global fenced allow-list")
                            # Fallback 1: Strip leading let block and re-test hash against scenario / global raws
                            if not (match_ok or hash_ok or global_ok):
                                stripped = _strip_leading_let_block(substituted_query)
                                norm_stripped = _normalize_query_for_hash(stripped)
                                scen_raws = (SCENARIO_LOCK.get('extracted_queries') or [])
                                scen_raw_hashes = { _hashlib.sha256(_normalize_query_for_hash(r).encode('utf-8')).hexdigest() for r in scen_raws }
                                if norm_stripped and _hashlib.sha256(norm_stripped.encode('utf-8')).hexdigest() in scen_raw_hashes:
                                    logger.info("[ScenarioLock] Accepted via stripped-let canonical hash match")
                                    match_ok = True
                                elif GLOBAL_KUSTO_ALLOW:
                                    g_raws = GLOBAL_KUSTO_ALLOW.get('raw') or []
                                    g_raw_hashes = { _hashlib.sha256(_normalize_query_for_hash(r).encode('utf-8')).hexdigest() for r in g_raws }
                                    if norm_stripped and _hashlib.sha256(norm_stripped.encode('utf-8')).hexdigest() in g_raw_hashes:
                                        logger.info("[GlobalKustoAllow] Accepted via stripped-let canonical hash match")
                                        global_ok = True
                            # Fallback 2: Substring canonical detection (normalized containment)
                            if not (match_ok or hash_ok or global_ok):
                                norm_candidate = _normalize_query_for_hash(substituted_query)
                                accepted_sub = False
                                # Check scenario raws then global raws
                                def _contains(raw_list: list[str]) -> bool:
                                    for raw in raw_list:
                                        nraw = _normalize_query_for_hash(raw)
                                        if nraw and nraw in norm_candidate:
                                            # Require ratio to avoid trivial acceptance
                                            if len(nraw) >= 40:  # heuristic length gate
                                                return True
                                    return False
                                if _contains(SCENARIO_LOCK.get('extracted_queries') or []):
                                    logger.info("[ScenarioLock] Accepted via normalized substring canonical match")
                                    accepted_sub = True
                                elif GLOBAL_KUSTO_ALLOW and _contains(GLOBAL_KUSTO_ALLOW.get('raw') or []):
                                    logger.info("[GlobalKustoAllow] Accepted via normalized substring canonical match")
                                    accepted_sub = True
                                if accepted_sub:
                                    match_ok = True
                            if not global_ok:
                                if not match_ok:
                                    logger.warning(
                                        "[ScenarioLock] Rejected query (no pattern/hash/global/substr match) scenario='%s' sha256=%s norm_prefix='%s' patterns=%d hashes=%d global_patterns=%d", 
                                        SCENARIO_LOCK.get('title'), h_full, norm_full[:120], len(patterns), len(SCENARIO_LOCK.get('hashes') or []), len((GLOBAL_KUSTO_ALLOW or {}).get('patterns') or [])
                                    )
                                    # Clear lock to prevent repeated looping retries
                                    SCENARIO_LOCK = None
                                    return json.dumps({
                                        'success': False,
                                        'error': 'Query rejected: not recognized (scenario/global canonical mismatch). Lock cleared to prevent loop.',
                                        'scenario_locked': None,
                                        'allowed_queries': 0,
                                        'guidance': 'Re-issue a scenario lookup or paste an exact fenced query from instructions.md.'
                                    })
                    # Pass parameters directly to MCP server
                    mcp_args = {
                        "clusterUrl": normalized_cluster_url,
                        "database": database,
                        "query": query,
                        **{k: v for k, v in actual_args.items() if k not in ["clusterUrl", "database", "query"]}
                    }
                    
                    try:
                        result = await kusto_service._session.call_tool(tool_name, mcp_args)
                        # Raw logging (size-limited) BEFORE normalization
                        try:
                            raw_repr = getattr(result, 'content', None)
                            if raw_repr is not None:
                                # Build a concise preview
                                parts = []
                                for itm in raw_repr:  # type: ignore
                                    t = getattr(itm, 'text', None)
                                    if t:
                                        parts.append(t[:200])
                                    if len(parts) >= 3:
                                        break
                                logger.info("[KustoMCP][RawResponse] parts=%d preview=%s", len(raw_repr), " | ".join(parts))
                            else:
                                logger.info("[KustoMCP][RawResponse] result_has_no_content_attr type=%s", type(result))
                        except Exception as rl_err:  # noqa: BLE001
                            logger.debug(f"[KustoMCP][RawResponse] logging failed: {rl_err}")
                        normalized = kusto_service._normalize_tool_result(result)
                        # Post-normalization debug path
                        if not normalized.get('success'):
                            logger.warning("[KustoMCP][NormalizedError] %s", normalized.get('error'))
                        else:
                            _tbl = normalized.get('table') or {}
                            _cols = _tbl.get('columns') or []
                            logger.info("[KustoMCP][NormalizedSuccess] rows=%s cols=%d", 
                                        _tbl.get('total_rows'), 
                                        len(_cols))                    
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
        
        # Semantic-only mode: legacy scenario service disabled
        self.scenario_service = None
        logger.info("AgentFrameworkService initialized (Agent Framework implementation)")

    def list_instruction_scenarios(self) -> list[dict[str, Any]]:
        """Return a lightweight summary of parsed instruction scenarios."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            semantic_search = loop.run_until_complete(get_semantic_search()) if not loop.is_running() else None
        except Exception:
            semantic_search = None
        scenarios = []
        if semantic_search and getattr(semantic_search, '_initialized', False):
            for idx, sc in enumerate(semantic_search.get_all_scenarios()):
                scenarios.append({
                    "index": idx,
                    "title": sc.get('title'),
                    "query_count": len(sc.get('queries', [])),
                    "description": (sc.get('description','').split('\n')[0][:160]) if sc.get('description') else ""
                })
            return scenarios
        # Legacy fallback removed (semantic-only)
        return scenarios

    async def run_instruction_scenario(self, scenario_ref: int | str) -> dict[str, Any]:
        """Execute a scenario using semantic search index only.

        Args:
            scenario_ref: Index (int) from list_instruction_scenarios ordering or a (partial) title string.
        Returns:
            Dict with scenario metadata, tables, summary, errors.
        """
        from services.semantic_scenario_search import get_semantic_search  # local import
        try:
            semantic_search = await get_semantic_search()
            if not getattr(semantic_search, '_initialized', False):
                raise ValueError("Semantic scenario index not initialized")
            scenarios = semantic_search.get_all_scenarios()
            if not scenarios:
                raise ValueError("No scenarios indexed")

            target = None
            if isinstance(scenario_ref, int):
                if 0 <= scenario_ref < len(scenarios):
                    target = scenarios[scenario_ref]
            else:
                ref_lower = str(scenario_ref).lower()
                for sc in scenarios:
                    title_lower = sc.get('title', '').lower()
                    norm = sc.get('normalized_title', title_lower)
                    if ref_lower == title_lower or ref_lower == norm:
                        target = sc
                        break
                if target is None:
                    for sc in scenarios:
                        if ref_lower in sc.get('title', '').lower():
                            target = sc
                            break

            if target is None:
                raise ValueError(f"Scenario not found: {scenario_ref}")

            queries = target.get('queries', []) or []
            from services.kusto_mcp_service import get_kusto_service
            kusto_service = await get_kusto_service()

            tables: list[dict[str, Any]] = []
            errors: list[str] = []
            for idx, query in enumerate(queries):
                try:
                    res = await kusto_service.execute_kusto_query(query)
                    if res.get("success"):
                        tables.append(res.get("table", {"columns": ["Result"], "rows": [["(empty)"]], "total_rows": 0}))
                    else:
                        err = res.get("error", "Unknown error")
                        errors.append(f"Query {idx+1}: {err}")
                        tables.append({"columns": ["Error"], "rows": [[err]], "total_rows": 1})
                except Exception as qerr:  # noqa: BLE001
                    err = f"Query {idx+1} execution exception: {qerr}"
                    errors.append(err)
                    tables.append({"columns": ["Error"], "rows": [[err]], "total_rows": 1})

            summary_parts = [f"Scenario: {target.get('title')} ({len(tables)} queries)"]
            if errors:
                summary_parts.append(f"{len(errors)} query errors encountered.")
            summary = " \n".join(summary_parts)

            return {
                "scenario": target.get('title'),
                "description": target.get('description', ''),
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
                # Gather queries from semantic search scenarios
                try:
                    from services.semantic_scenario_search import get_semantic_search as _gss
                    ss = await _gss()
                    if getattr(ss, '_initialized', False):
                        for sc in ss.get_all_scenarios():
                            all_queries.extend(sc.get('queries', []) or [])
                except Exception as ss_err:  # noqa: BLE001
                    logger.warning(f"Semantic search unavailable during prewarm: {ss_err}")
                
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
            # Use semantic search summary when available
            semantic_search = await get_semantic_search()
            if semantic_search and semantic_search._initialized:
                logger.info("Semantic scenario index ready")
            # Legacy scenario service removed; no fallback listing
        except Exception as e:
            logger.warning(f"Failed to load instruction scenarios (semantic-only): {e}")
    
    async def reload_scenarios(self) -> None:
        """Reload scenarios (semantic-only) by re-running semantic search initialization.

        Note: Current SemanticScenarioSearch does not expose a forced rebuild flag; calling initialize()
        again is idempotent and will reuse cache unless underlying instructions changed.
        """
        try:
            from services.semantic_scenario_search import get_semantic_search
            ss = await get_semantic_search()
            await ss.initialize()
            logger.info("Semantic scenario index reloaded (idempotent initialize)")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to reload semantic scenarios: {e}")
    
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

                # Add scenario lock reset tool
                async def reset_scenario_lock() -> str:  # type: ignore
                    """Clear active scenario lock (allows selecting a new scenario)."""
                    global SCENARIO_LOCK
                    if SCENARIO_LOCK:
                        prev = SCENARIO_LOCK.get('title')
                        SCENARIO_LOCK = None
                        return f"Scenario lock cleared (was: {prev})."
                    return "No active scenario lock."
                reset_scenario_lock.__name__ = "reset_scenario_lock"
                tools.append(reset_scenario_lock)
                logger.info("Added reset_scenario_lock tool")
                
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
        """Create the IntuneExpert agent using Agent Framework.

        Builds system instructions dynamically (awaiting semantic summary first).
        """
        logger.info("Creating Intune Expert agent with Kusto MCP tools (Agent Framework)")

        chat_client = self._create_azure_chat_client(model_config)

        # Build semantic summary safely (semantic search may not be ready)
        try:
            ss = await get_semantic_search()
            if getattr(ss, '_initialized', False):
                semantic_summary = ss.build_summary()
            else:
                semantic_summary = 'Semantic scenario index not yet initialized'
        except Exception as _ssi:
            logger.warning(f"Failed to build semantic summary: {_ssi}")
            semantic_summary = 'Semantic scenario index unavailable'

        system_instructions = f"""
        You are an Intune Expert agent specializing in Microsoft Intune diagnostics and troubleshooting.
        
        Your role is to interpret natural language requests from support engineers and execute the appropriate
        Kusto queries using the MCP server tools to retrieve and analyze Intune device diagnostics information.
        
    INFRASTRUCTURE LABELS (IGNORE):
    - Any internal agent/orchestrator names are infrastructure metadata.
    - They are NOT user facts, NOT products, and NOT part of the Intune diagnostic domain.
    - Do NOT list them under GIVEN FACTS or treat them as entities that require lookup or explanation.
        
        AVAILABLE DIAGNOSTIC SCENARIOS (Semantic Index):
    {semantic_summary}

    SEMANTIC-ONLY MODE:
    - Legacy keyword scenario lookup has been removed in this Agent Framework path.
    - All scenario discovery MUST use the lookup_scenarios tool which returns JSON first line.
    - Do NOT attempt to reference legacy scenario services or summaries.
    - If semantic index not ready, inform the user and avoid fabricating scenarios.
        
        NATURAL LANGUAGE UNDERSTANDING:
        - Interpret user requests naturally without requiring specific keywords or parameters
        - Extract relevant identifiers (Device IDs, Account IDs, Context IDs) from user messages
        - Use the lookup_scenarios tool to find relevant diagnostic scenarios based on user intent
        - Execute only the queries provided by the lookup_scenarios tool - do not create your own queries
        
          MANDATORY WORKFLOW (MUST FOLLOW IN ORDER):
        1. ALWAYS call lookup_scenarios first with the user's request text
        2. If the scenario requires context from previous queries, call lookup_context to get stored values
          3. When a single recommended scenario is returned, a SCENARIO LOCK is applied:
              - Only the exact canonical query text (ignoring placeholder substitution + whitespace) is permitted.
              - Any other query attempts MUST be rejected (the system enforces this automatically).
          4. To intentionally switch scope, first call reset_scenario_lock THEN perform a new lookup_scenarios call.
          5. Execute ONLY the canonical scenario query/queries after lock; do NOT invent supportive queries.
          6. Return results in table format as specified in instructions.md
        
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
        
    KUSTO QUERY EXECUTION & ENFORCEMENT:
    - Use ONLY the canonical queries from the selected scenario (enforced via pattern + hash verification).
    - DO NOT attempt to generate alternative or exploratory queries unless user explicitly asks to broaden scope.
    - To broaden scope, call reset_scenario_lock and perform a fresh scenario lookup with clarified intent.
    - Placeholder values (<DeviceId>, <AccountId>, etc.) are auto-substituted from context.
    - If a query is rejected, explain to the user that it is outside the locked scenario and offer to unlock.
        
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
        agent = ChatAgent(chat_client=chat_client, instructions=system_instructions, tools=tools)
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
                    "Build a chronological device event timeline covering compliance status changes, policy assignment or evaluation outcomes, application install attempts (success/failure), device check-ins (including failures or long gaps), enrollment/sync events, and notable error events for the specified device and time window.\n"
                    "1. Use the \"Advanced Scenario: Device Timeline\" scenario from instructions.md to construct the device timeline. Run all Kusto queries in this scenario in sequence.\n"
                    "2. Discover and aggregate relevant events via available tools / queries.\n"
                    "3. Normalize timestamps to UTC ISO8601 (YYYY-MM-DD HH:MM).\n"
                    "4. Group logically similar rapid events but keep important state transitions explicit.\n"
                    "5. Output a concise narrative summary first (outside code fence).\n"
                    "6. Then output EXACTLY ONE fenced mermaid code block using the 'timeline' syntax:```mermaid\\ntimeline\nTitle: Device Timeline (DEVICE_ID)\nStart: <earliest timestamp>\n<YYYY-MM-DD HH:MM>: <Category> - <Brief description>\n...\n```\n"
                    "Rules: \n- Do not include any other fenced mermaid blocks.\n- Categories: Compliance, Policy, App, Check-in, Error, Enrollment, Other.\n- Limit to <= 60 events focusing on impactful changes.\n- If no events found, still return an empty timeline code block with a 'No significant events' note.\n"
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
                    logger.debug(f"[Magentic] Received event: {event_type}")
                
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
                    logger.debug(f"[Magentic] Received event: {event_type}")
                
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
        
        # Check for scenario references (legacy path only if legacy service present)
        scenario_titles = self.scenario_service.list_all_scenario_titles() if self.scenario_service else []
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
