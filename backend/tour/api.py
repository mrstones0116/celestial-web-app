from fastapi import APIRouter, HTTPException

from .schemas import (
    CreateTourSessionRequest,
    InstructionRequest,
    TourSessionResponse,
)
from .session_store import tour_store
from .planner import build_plan
from .llm_client import parse_instruction

router = APIRouter()


def _load_session(session_id: str) -> dict:
    session = tour_store.get(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    return session


@router.post("/sessions")
async def create_tour_session(req: CreateTourSessionRequest):
    session_id = tour_store.create_session(req.model_dump())
    session = tour_store.get(session_id)
    return {
        "session_id": session_id,
        "status": session["status"],
        "message": "会话创建成功",
    }


@router.post("/sessions/{session_id}/instruction")
async def submit_instruction(session_id: str, req: InstructionRequest):
    session = _load_session(session_id)

    if session["status"] == "stopped":
        return {"status": "stopped"}

    parsed = await parse_instruction(req.text)
    intent = parsed["intent"]

    print(
        f"[tour] intent={intent} "
        f"source={parsed.get('source')} "
        f"confidence={parsed.get('confidence')} "
        f"reason={str(parsed.get('reason', ''))[:80]}"
    )

    plan = build_plan(intent, config=session.get("config", {}))

    history = list(session.get("history", []))
    history.append(req.text)

    tour_store.update(session_id, {
        "status": "ready",
        "plan": plan.model_dump(),
        "current_step_index": 0,
        "history": history,
        "last_intent": parsed,
    })

    return TourSessionResponse(
        session_id=session_id,
        status="ready",
        plan=plan,
        current_step_index=0,
        message=f"路线已生成（{parsed.get('source')}）",
    ).model_dump()


@router.post("/sessions/{session_id}/next")
async def next_step(session_id: str):
    session = _load_session(session_id)

    if session["status"] == "stopped":
        return {"status": "stopped"}
    if not session.get("plan"):
        return {"status": "no_plan"}

    plan = session["plan"]
    steps = plan["steps"]
    idx = session["current_step_index"]

    if idx + 1 >= len(steps):
        tour_store.update(session_id, {
            "status": "finished",
            "current_step_index": len(steps) - 1,
        })
        return {
            "status": "finished",
            "current_step_index": len(steps) - 1,
        }

    new_idx = idx + 1
    tour_store.update(session_id, {"current_step_index": new_idx})
    return {
        "status": "running",
        "current_step_index": new_idx,
        "step": steps[new_idx],
    }


@router.post("/sessions/{session_id}/prev")
async def prev_step(session_id: str):
    session = _load_session(session_id)

    if session["status"] == "stopped":
        return {"status": "stopped"}
    if not session.get("plan"):
        return {"status": "no_plan"}

    idx = session["current_step_index"]
    if idx == 0:
        return {
            "status": "at_first_step",
            "current_step_index": 0,
            "step": session["plan"]["steps"][0],
        }

    new_idx = idx - 1
    tour_store.update(session_id, {"current_step_index": new_idx})
    return {
        "status": "running",
        "current_step_index": new_idx,
        "step": session["plan"]["steps"][new_idx],
    }


@router.post("/sessions/{session_id}/pause")
async def pause_tour(session_id: str):
    session = _load_session(session_id)
    if session["status"] == "stopped":
        return {"status": "stopped"}

    tour_store.update(session_id, {"status": "paused"})
    return {
        "status": "paused",
        "current_step_index": session["current_step_index"],
    }


@router.post("/sessions/{session_id}/stop")
async def stop_tour(session_id: str):
    session = tour_store.stop(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    return {"status": "stopped"}