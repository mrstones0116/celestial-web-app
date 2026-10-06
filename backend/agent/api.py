from fastapi import APIRouter, HTTPException

from .agent import run_agent
from .schemas import AgentChatRequest, AgentChatResponse
from .session_store import agent_store

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/sessions")
async def create_session():
    sid = agent_store.create()
    return {"session_id": sid, "message": "Agent 会话已创建"}


@router.post("/chat", response_model=AgentChatResponse)
async def chat(req: AgentChatRequest):
    sid = req.session_id
    if not sid or not agent_store.get(sid):
        sid = agent_store.create()

    loc = None
    if req.location:
        loc = {"lat": req.location.lat, "lon": req.location.lon}

    answer, tool_records = await run_agent(
        user_message=req.message,
        session_id=sid,
        location=loc,
    )

    return AgentChatResponse(
        session_id=sid,
        answer=answer,
        tool_calls=tool_records,
    )


@router.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    if not agent_store.get(session_id):
        raise HTTPException(404, "会话不存在")
    agent_store.clear(session_id)
    return {"ok": True}