import uuid
from typing import List, Optional, cast
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from models.database import DiagnosticSession, ModelConfiguration, ChatSession, ChatMessage
from models.schemas import DiagnosticRequest, DiagnosticResponse, AgentResponse
from pydantic import BaseModel
from services.agent_service import agent_service as global_agent_service, AgentService

router = APIRouter()

from dependencies import get_db


class BulkDeleteRequest(BaseModel):
    session_ids: List[str]

class ChatRequest(BaseModel):
    message: str
    parameters: Optional[dict] = None
    session_id: Optional[str] = None
    strict: Optional[bool] = False

class ChatResponse(BaseModel):
    response: str
    data: Optional[dict] = None
    state: Optional[dict] = None
    tables: Optional[List[dict]] = None
    clarification_needed: Optional[bool] = None
    candidates: Optional[List[dict]] = None
    session_id: Optional[str] = None
    user_message_id: Optional[int] = None
    agent_message_id: Optional[int] = None

class ChatSessionSummary(BaseModel):
    session_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    state_snapshot: Optional[dict] = None

class ChatMessageRecord(BaseModel):
    id: int
    role: str
    content: str
    params: Optional[dict]
    # Stored agent responses use a list of table objects (each with columns, rows, total_rows)
    # Original schema incorrectly declared this as a single dict causing validation errors when a list is present.
    tables: Optional[List[dict]]
    intent: Optional[str]
    clarification_needed: bool
    created_at: Optional[str]
    state_after: Optional[dict]

@router.get("/chat/sessions", response_model=List[ChatSessionSummary])
async def list_chat_sessions(user_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc()))
    sessions = res.scalars().all()
    out: List[ChatSessionSummary] = []
    for s in sessions:
        out.append(ChatSessionSummary(
            session_id=getattr(s, "session_id"),
            created_at=str(getattr(s, "created_at", "")),
            updated_at=str(getattr(s, "updated_at", "")),
            state_snapshot=getattr(s, "state_snapshot", None),
        ))
    return out

@router.get("/chat/sessions/{session_id}/messages", response_model=List[ChatMessageRecord])
async def list_chat_messages(session_id: str, user_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ChatSession).where(ChatSession.session_id == session_id, ChatSession.user_id == user_id))
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    res_msgs = await db.execute(select(ChatMessage).where(ChatMessage.chat_session_id == getattr(session, "id")).order_by(ChatMessage.created_at.asc()))
    msgs = res_msgs.scalars().all()
    records: List[ChatMessageRecord] = []
    for m in msgs:
        records.append(ChatMessageRecord(
            id=getattr(m, "id"),
            role=getattr(m, "role"),
            content=getattr(m, "content"),
            params=getattr(m, "params"),
            tables=getattr(m, "tables"),
            intent=getattr(m, "intent"),
            clarification_needed=bool(getattr(m, "clarification_needed")),
            created_at=str(getattr(m, "created_at", "")),
            state_after=getattr(m, "state_after", None),
        ))
    return records

@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str, user_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ChatSession).where(ChatSession.session_id == session_id, ChatSession.user_id == user_id))
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    # Delete messages then session (ondelete may not cascade in SQLite without fk pragma)
    await db.execute(delete(ChatMessage).where(ChatMessage.chat_session_id == getattr(session, 'id')))
    await db.execute(delete(ChatSession).where(ChatSession.id == getattr(session, 'id')))
    await db.commit()
    return {"message": "Chat session deleted", "session_id": session_id}

@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    request: ChatRequest,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Conversational endpoint with persistence: manages chat sessions and messages."""
    # Ensure agent service ready
    svc = global_agent_service
    if svc is None:
        await AgentService.initialize()
        from services.agent_service import agent_service as refreshed_agent_service
        svc = refreshed_agent_service
    if svc is None:
        raise HTTPException(status_code=500, detail="Agent service not initialized")

    # Ensure agent model loaded (reuse default config logic from query endpoint)
    result = await db.execute(
        select(ModelConfiguration)
        .where(ModelConfiguration.user_id == user_id)
        .where(ModelConfiguration.is_default == True)
    )
    model_config = result.scalar_one_or_none()
    if not model_config:
        raise HTTPException(status_code=400, detail="No default model configuration found.")
    if not svc.intune_expert_agent:
        await svc.setup_agent(model_config)

    # Retrieve or create chat session
    session_obj: Optional[ChatSession] = None
    if request.session_id:
        res = await db.execute(select(ChatSession).where(ChatSession.session_id == request.session_id, ChatSession.user_id == user_id))
        session_obj = res.scalar_one_or_none()
    if session_obj is None:
        import uuid as _uuid
        session_id = request.session_id or str(_uuid.uuid4())
        # Create without premature snapshot so first turn can persist populated state
        session_obj = ChatSession(session_id=session_id, user_id=user_id, state_snapshot=None)
        db.add(session_obj)
        await db.commit()
        await db.refresh(session_obj)
    session_id = session_obj.session_id  # type: ignore[attr-defined]

    # Hydrate conversation state from stored snapshot (ensures continuity after restart)
    try:
        svc.state.load_from_snapshot(session_obj.state_snapshot or {})  # type: ignore[arg-type]
    except Exception:
        pass

    # Persist user message early
    user_msg = ChatMessage(
        chat_session_id=session_obj.id,  # type: ignore[attr-defined]
        role="user",
        content=request.message,
        params=request.parameters,
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    # Assemble minimal conversation history (last N prior turns) for natural continuity
    history_res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_session_id == session_obj.id)  # type: ignore[attr-defined]
        .order_by(ChatMessage.created_at.asc())
    )
    prior_msgs = history_res.scalars().all()
    # Exclude the just-persisted current user message when passing history (model will see it separately in composite)
    history_payload = []
    for m in prior_msgs[:-1]:
        history_payload.append({"role": getattr(m, "role"), "content": getattr(m, "content")})
    # Limit to last 12 turns (configurable) to control token growth
    if len(history_payload) > 12:
        history_payload = history_payload[-12:]

    enriched_params = dict(request.parameters or {})
    if request.strict:
        enriched_params["strict_mode"] = True
    enriched_params["conversation_history"] = history_payload

    chat_result = await svc.chat(request.message, enriched_params)
    # Prefer explicit agent natural language response, fall back to earlier message or generic OK
    summary = chat_result.get("response") or chat_result.get("summary") or chat_result.get("message") or "OK"

    # Persist agent message
    agent_msg = ChatMessage(
        chat_session_id=session_obj.id,  # type: ignore[attr-defined]
        role="agent",
        content=summary,
        params=chat_result.get("parameters"),
        tables=chat_result.get("tables"),
        state_after=chat_result.get("state"),
        intent=chat_result.get("intent"),
        clarification_needed=bool(chat_result.get("clarification_needed")),
    )
    db.add(agent_msg)
    # Update session snapshot
    session_obj.state_snapshot = chat_result.get("state")  # type: ignore[assignment]
    await db.commit()
    await db.refresh(agent_msg)

    return ChatResponse(
        response=summary,
        data=chat_result,
        state=chat_result.get("state"),
        tables=chat_result.get("tables"),
        clarification_needed=chat_result.get("clarification_needed"),
        candidates=chat_result.get("candidates"),
    session_id=str(session_id),
        user_message_id=user_msg.id,  # type: ignore[attr-defined]
        agent_message_id=agent_msg.id,  # type: ignore[attr-defined]
    )


@router.post("/query", response_model=AgentResponse)
async def execute_diagnostic_query(
    request: DiagnosticRequest,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Execute a diagnostic query through the Intune Expert agent"""
    try:
        # Get user's default model configuration
        result = await db.execute(
            select(ModelConfiguration)
            .where(ModelConfiguration.user_id == user_id)
            .where(ModelConfiguration.is_default == True)
        )
        model_config = result.scalar_one_or_none()
        
        if not model_config:
            raise HTTPException(
                status_code=400, 
                detail="No default model configuration found. Please go to Settings and configure an Azure AI model first."
            )
        
        # Create diagnostic session
        session_id = str(uuid.uuid4())
        diagnostic_session = DiagnosticSession(
            user_id=user_id,
            session_id=session_id,
            device_id=request.device_id,
            query_type=request.query_type,
            query_parameters=request.parameters,
            status="pending"
        )
        db.add(diagnostic_session)
        await db.commit()
        
        # Ensure agent service initialized (global may be None at import time)
        svc = global_agent_service
        if svc is None:
            # Initialize (will set global variable inside AgentService.initialize)
            await AgentService.initialize()
            from services.agent_service import agent_service as refreshed_agent_service  # late import
            svc = refreshed_agent_service
        if svc is None:
            raise HTTPException(status_code=500, detail="Agent service failed to initialize")

        # Setup agent if not already done
        if not svc.intune_expert_agent:
            await svc.setup_agent(model_config)
        
        # Execute query through agent
        try:
            result_data = await svc.query_diagnostics(
                request.query_type, 
                request.parameters or {}
            )
            
            # Update session with results
            diagnostic_session.results = result_data  # type: ignore[assignment]
            diagnostic_session.status = "completed"  # type: ignore[assignment]
            await db.commit()
            
            # Extract all tables if available
            table_data = None
            tables_list = None
            if isinstance(result_data.get("tables"), list) and result_data["tables"]:
                raw_tables = result_data["tables"]
                tables_list = []
                for t in raw_tables:
                    if isinstance(t, dict) and 'columns' in t and 'rows' in t:
                        tables_list.append(t)
                if tables_list:
                    table_data = tables_list[0]

            return AgentResponse(
                response=result_data.get("summary", "Query executed successfully"),
                table_data=table_data,
                tables=tables_list,
                session_id=session_id
            )
        
        except Exception as e:
            # Update session with error
            diagnostic_session.status = "failed"  # type: ignore[assignment]
            diagnostic_session.error_message = str(e)  # type: ignore[assignment]
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process diagnostic request: {str(e)}")

@router.get("/sessions", response_model=List[DiagnosticResponse])
async def get_diagnostic_sessions(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get all diagnostic sessions for a user"""
    result = await db.execute(
        select(DiagnosticSession)
        .where(DiagnosticSession.user_id == user_id)
        .order_by(DiagnosticSession.created_at.desc())
    )
    
    sessions = result.scalars().all()
    responses: List[DiagnosticResponse] = []
    for session in sessions:
        # Extract attributes (helps type checkers)
        sid: str = getattr(session, "session_id")
        device_id: Optional[str] = getattr(session, "device_id")
        qtype: str = getattr(session, "query_type")
        results_val = getattr(session, "results")
        status_val: str = getattr(session, "status")
        err_msg: Optional[str] = getattr(session, "error_message")
        created_at_val = getattr(session, "created_at")
        responses.append(
            DiagnosticResponse(
                session_id=sid,
                device_id=device_id,
                query_type=qtype,
                results=results_val,  # type: ignore[arg-type]
                status=status_val,
                error_message=err_msg,
                created_at=created_at_val  # type: ignore[arg-type]
            )
        )
    return responses

@router.get("/sessions/{session_id}", response_model=DiagnosticResponse)
async def get_diagnostic_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific diagnostic session"""
    result = await db.execute(
        select(DiagnosticSession).where(DiagnosticSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Diagnostic session not found")
    
    return DiagnosticResponse(
        session_id=getattr(session, "session_id"),
        device_id=getattr(session, "device_id"),
        query_type=getattr(session, "query_type"),
        results=getattr(session, "results"),  # type: ignore[arg-type]
        status=getattr(session, "status"),
        error_message=getattr(session, "error_message"),
        created_at=getattr(session, "created_at")  # type: ignore[arg-type]
    )

@router.get("/query-types")
async def get_available_query_types():
    """Get list of available diagnostic query types"""
    return {
        "query_types": [
            {
                "id": "device_details",
                "name": "Device Details",
                "description": "Get comprehensive device information including OS version, enrollment details, and basic properties",
                "required_params": ["device_id"]
            },
            {
                "id": "compliance",
                "name": "Compliance Status",
                "description": "Check device compliance status changes over the last 10 days",
                "required_params": ["device_id"]
            },
            {
                "id": "policy_status",
                "name": "Policy Status",
                "description": "Get policy and setting status for the device",
                "required_params": ["device_id", "context_id"]
            },
            {
                "id": "user_lookup",
                "name": "User Lookup",
                "description": "Find user IDs associated with the device",
                "required_params": ["device_id"]
            },
            {
                "id": "tenant_info",
                "name": "Tenant Information",
                "description": "Get tenant details including flighting tags and scale unit",
                "required_params": ["account_id"]
            },
            {
                "id": "effective_groups",
                "name": "Effective Groups",
                "description": "Get effective group memberships and policy assignments",
                "required_params": ["device_id", "account_id"]
            },
            {
                "id": "applications",
                "name": "Application Status",
                "description": "Get application deployment status and installation attempts",
                "required_params": ["device_id"]
            },
            {
                "id": "mam_policy",
                "name": "MAM Policy",
                "description": "Check Mobile Application Management policy status",
                "required_params": ["device_id", "context_id"]
            }
        ]
    }

@router.get("/chat/mcp-health")
async def mcp_health():
    try:
        from services.kusto_mcp_service import kusto_mcp_service
        if not kusto_mcp_service or not kusto_mcp_service.is_initialized:
            return {"initialized": False}
        return {
            "initialized": True,
            "tools": getattr(kusto_mcp_service, "_tool_names", []),
        }
    except Exception as e:  # noqa: BLE001
        return {"initialized": False, "error": str(e)}


@router.delete("/sessions/{session_id}")
async def delete_diagnostic_session(
    session_id: str,
    user_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db)
):
    """Delete a single diagnostic session.

    If user_id not provided, infer from the session record.
    """
    try:
        # Fetch session first
        result = await db.execute(
            select(DiagnosticSession).where(DiagnosticSession.session_id == session_id)
        )
        session_obj = result.scalar_one_or_none()
        if not session_obj:
            raise HTTPException(status_code=404, detail="Diagnostic session not found")
        # Authorization / ownership check when user_id supplied
        session_user_id = getattr(session_obj, "user_id")
        if user_id is not None and int(session_user_id) != user_id:
            raise HTTPException(status_code=403, detail="Session does not belong to specified user")
        inferred_user_id = int(session_user_id)
    # (debug removed) Attempting delete of session
        # Perform deletion
        await db.execute(
            delete(DiagnosticSession).where(DiagnosticSession.id == session_obj.id)
        )
        await db.commit()
    # (debug removed) Session deleted
        return {"message": "Diagnostic session deleted", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


@router.delete("/sessions", summary="Delete sessions (all or bulk)")
async def delete_sessions(
    user_id: Optional[int] = Query(default=None),
    payload: Optional[BulkDeleteRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db)
):
    """Delete sessions.

    Behavior:
    - If payload with session_ids provided and user_id omitted: infer user ownership ensuring all sessions share same user.
    - If payload omitted and user_id provided: delete ALL sessions for that user.
    - If neither condition satisfied -> 400.
    """
    try:
        if payload and payload.session_ids:
            # Fetch sessions to infer user / validate consistency
            result = await db.execute(
                select(DiagnosticSession).where(
                    DiagnosticSession.session_id.in_(payload.session_ids)
                )
            )
            sessions = result.scalars().all()
            if not sessions:
                return {"message": "No matching sessions", "deleted": 0}
            # Ensure all session IDs found
            found_ids = {str(getattr(s, "session_id")) for s in sessions}
            missing = set(payload.session_ids) - found_ids
            if missing:
                raise HTTPException(status_code=404, detail=f"Session IDs not found: {sorted(missing)}")
            # Infer user
            user_ids = {s.user_id for s in sessions}
            if len(user_ids) != 1:
                raise HTTPException(status_code=400, detail="Session user ownership mismatch")
            inferred_user_id = next(iter(user_ids))
            if user_id is not None and user_id != inferred_user_id:
                raise HTTPException(status_code=403, detail="Specified user_id does not own all sessions")
            # (debug removed) Bulk delete specific sessions
            del_result = await db.execute(
                delete(DiagnosticSession)
                .where(DiagnosticSession.session_id.in_(payload.session_ids))
            )
            deleted = del_result.rowcount or 0
            await db.commit()
            # (debug removed) Bulk delete result
            return {"message": f"Deleted {deleted} session(s)", "deleted": deleted}
        elif user_id is not None:
            # (debug removed) Delete ALL sessions for user
            result = await db.execute(
                delete(DiagnosticSession).where(DiagnosticSession.user_id == user_id)
            )
            deleted = result.rowcount or 0
            await db.commit()
            # (debug removed) Delete ALL sessions result
            return {"message": f"Deleted {deleted} session(s)", "deleted": deleted}
        else:
            raise HTTPException(status_code=400, detail="Must supply user_id to delete all sessions or session_ids payload for specific sessions")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete sessions failed: {str(e)}")

@router.post("/sessions/bulk-delete", summary="Bulk delete specific sessions")
async def bulk_delete_sessions_post(
    user_id: Optional[int] = Query(default=None),
    payload: BulkDeleteRequest = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """POST variant used by frontend for bulk deletion of specified session IDs."""
    if not payload.session_ids:
        raise HTTPException(status_code=400, detail="session_ids list cannot be empty")
    # Reuse logic by calling delete_sessions with payload
    return await delete_sessions(user_id=user_id, payload=payload, db=db)

@router.post("/sessions/{session_id}/delete", summary="Delete a session (POST fallback)")
async def delete_session_post_fallback(
    session_id: str,
    user_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db)
):
    """Fallback deletion route in case DELETE is blocked by proxies or method mismatch in frontend."""
    return await delete_diagnostic_session(session_id=session_id, user_id=user_id, db=db)

@router.get("/sessions/{session_id}/delete", summary="Delete a session (GET fallback)")
async def delete_session_get_fallback(
    session_id: str,
    user_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db)
):
    """Extreme fallback: some clients might only be able to issue GET links for destructive actions (not recommended)."""
    return await delete_diagnostic_session(session_id=session_id, user_id=user_id, db=db)

@router.post("/sessions/delete", summary="Bulk delete via POST (alternate)")
async def bulk_delete_sessions_generic_post(
    user_id: Optional[int] = Query(default=None),
    payload: Optional[BulkDeleteRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db)
):
    """Generic POST endpoint to mirror DELETE /sessions logic for environments blocking DELETE with body."""
    return await delete_sessions(user_id=user_id, payload=payload, db=db)

# Trailing slash tolerant duplicates (not shown in schema)
@router.delete("/sessions/{session_id}/", include_in_schema=False)
async def delete_diagnostic_session_slash(session_id: str, user_id: Optional[int] = Query(default=None), db: AsyncSession = Depends(get_db)):
    return await delete_diagnostic_session(session_id=session_id, user_id=user_id, db=db)

@router.delete("/sessions/", include_in_schema=False)
async def delete_sessions_slash(user_id: Optional[int] = Query(default=None), db: AsyncSession = Depends(get_db)):
    return await delete_sessions(user_id=user_id, payload=None, db=db)


@router.delete("/sessions/recent", summary="Delete most recent N sessions")
async def delete_recent_sessions(
    user_id: int,
    limit: int = Query(10, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """Delete the most recent N diagnostic sessions for a user (default 10)."""
    try:
        # Get most recent session IDs limited by 'limit'
        result = await db.execute(
            select(DiagnosticSession.session_id)
            .where(DiagnosticSession.user_id == user_id)
            .order_by(DiagnosticSession.created_at.desc())
            .limit(limit)
        )
        session_ids = [row[0] for row in result.all()]
        if not session_ids:
            return {"message": "No sessions to delete", "deleted": 0}
    # (debug removed) Recent sessions selected for deletion
        del_result = await db.execute(
            delete(DiagnosticSession)
            .where(DiagnosticSession.user_id == user_id)
            .where(DiagnosticSession.session_id.in_(session_ids))
        )
        deleted = del_result.rowcount or 0
        await db.commit()
    # (debug removed) Recent sessions deletion result
        return {"message": f"Deleted {deleted} recent session(s)", "deleted": deleted}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete recent sessions: {str(e)}")

# Debug helper endpoint for route listing (optional; not included in schema docs)
@router.get("/debug/routes", include_in_schema=False)
async def list_routes():
    from fastapi.routing import APIRoute
    info = []
    for r in router.routes:
        if isinstance(r, APIRoute):
            methods = ",".join(sorted(r.methods)) if r.methods else ""
            info.append(f"{r.path} -> {methods}")
    return sorted(info)

# Simple DELETE verb test endpoint
@router.delete("/ping-delete-check", summary="DELETE verb test")
async def delete_ping():
    return {"message": "DELETE verb reachable"}




