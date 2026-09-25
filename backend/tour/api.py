from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime

from .schemas import (
    CreateTourSessionRequest,
    InstructionRequest,
    TourSessionResponse,
    ChatRequest,
    ChatResponse,
    TourTarget,
)
from .session_store import tour_store
from .planner import build_plan, build_dynamic_plan, detect_intent
from .llm_client import parse_instruction, generate_narration
from .astro_utils import compute_visible_objects, sort_observation_path

# ✅ 注意：这里需要从主应用获取 HYGDataLoader。
# 由于 api.py 是子模块，通过延迟导入或依赖注入解决。
# 推荐方案：在 server.py 中，创建 router 时传入 loader。
# 为保持兼容性，这里先用延迟导入 + 全局变量。
_loader = None

def set_loader(loader_instance):
    """由 server.py 在启动时调用，注入星表加载器。"""
    global _loader
    _loader = loader_instance

router = APIRouter()


def _get_loader():
    if _loader is None:
        raise HTTPException(503, "星表数据加载器未初始化")
    if not _loader.loaded:
        try:
            _loader.load_data()
        except Exception as e:
            raise HTTPException(503, f"星表数据加载失败: {e}")
    return _loader


def _load_session(session_id: str) -> dict:
    session = tour_store.get(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    return session


# ==================== 会话管理 ====================

@router.post("/sessions")
async def create_tour_session(req: CreateTourSessionRequest):
    session_id = tour_store.create_session(req.model_dump())
    session = tour_store.get(session_id)
    return {
        "session_id": session_id,
        "status": session["status"],
        "message": "会话创建成功",
    }

@router.post("/sessions/{session_id}/visible-now")
async def get_visible_now(session_id: str):
    session = _load_session(session_id)
    config = session.get("config", {})
    config.setdefault("observing_time", {})["use_real_time"] = True

    loader = _get_loader()
    try:
        stars = loader.get_stars(max_mag=5.5)
    except Exception:
        stars = loader.get_bright_stars(max_mag=4.0)

    visible = compute_visible_objects(stars, config, min_altitude=15.0, limit=15)

    targets = []
    for i, star in enumerate(visible):
        # ✅ 修正：使用 "name" 而非 "proper"
        name_en = str(star.get("name", "") or "").strip()
        name_zh = star.get("name_zh", name_en or f"亮星 {i+1}")

        # ✅ 修正：优先用已转换的 ra_deg/dec_deg
        ra_deg = star.get("ra_deg")
        dec_deg = star.get("dec_deg")
        if ra_deg is None:
            ra_deg = _ra_to_deg(star.get("ra_hours") or star.get("ra"))
        if dec_deg is None:
            dec_deg = _dec_to_deg(star.get("dec"))

        targets.append(TourTarget(
            type="star",
            id=str(star.get("id", f"star_{name_en or i}")),
            hyg_id=str(star.get("id", f"star_{name_en or i}")),
            name_zh=name_zh,
            name_en=name_en,
            constellation=star.get("constellation") or star.get("con"),
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            magnitude=star.get("mag"),
            altitude_deg=star.get("altitude_deg"),
            azimuth_deg=star.get("azimuth_deg"),
            is_visible=True,
            visibility_note=f"高度角 {star.get('altitude_deg', 0):.0f}°",
        ))
    # ... 后面不变 ...

    tour_store.update(session_id, {
        "status": "visible_queried",
        "visible_objects": [t.model_dump() for t in targets],
    })

    return {
        "session_id": session_id,
        "status": "visible_queried",
        "message": f"为你找到 {len(targets)} 颗当前可见的明亮天体",
        "visible_objects": [t.model_dump() for t in targets],
        "suggested_tour_available": len(targets) > 0,
    }

# ==================== 核心：智能指令处理 ====================

@router.post("/sessions/{session_id}/instruction")
async def submit_instruction(session_id: str, req: InstructionRequest):
    session = _load_session(session_id)
    if session["status"] == "stopped":
        return {"status": "stopped"}

    parsed = await parse_instruction(req.text)
    intent = parsed["intent"]
    entities = parsed.get("entities", {})

    print(
        f"[tour] intent={intent} "
        f"source={parsed.get('source')} "
        f"confidence={parsed.get('confidence')} "
        f"entities={entities} "
        f"reason={str(parsed.get('reason', ''))[:80]}"
    )

    loader = _get_loader()
    config = session.get("config", {})

    # ✅ 如果用户提到"现在"或"今晚"，强制使用实时时间
    if entities.get("time_expression") in ["现在", "今晚", "now", "tonight"]:
        config.setdefault("observing_time", {})["use_real_time"] = True

    # ---------- 分支1：实时可见查询 ----------
    if intent in ["what_visible", "recommend_order"]:
        try:
            stars = loader.get_stars(max_mag=5.5)
        except Exception:
            stars = loader.get_bright_stars(max_mag=4.0)

        visible = compute_visible_objects(stars, config, min_altitude=15.0, limit=15)

        if intent == "recommend_order":
            visible = sort_observation_path(visible)

        if not visible:
            return TourSessionResponse(
                session_id=session_id,
                status="empty",
                plan=None,
                current_step_index=0,
                message="当前时间地点下未找到足够亮的可见天体。请尝试到光污染更少的地方，或稍后再试。",
            ).model_dump()

        # 生成动态导览计划
        plan = build_dynamic_plan(
            stars=visible,
            config=config,
            title="实时星空导览" if intent == "what_visible" else "推荐观测顺序",
            description="根据你的时间和位置，为你实时计算的可见亮星。",
            max_steps=min(10, len(visible)),
            sort_by_path=(intent == "recommend_order"),
        )

        # ✅ 异步增强解说（可选，若追求速度可注释掉）
        # 为简化，这里先使用基础解说。如需 LLM 增强，可遍历 steps 调用 generate_narration。

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
            message=f"已根据你的实时位置生成导览路线（{parsed.get('source')}）",
        ).model_dump()

    # ---------- 分支2：主题导览（原有逻辑，但增加可见性验证） ----------
    plan = build_plan(intent, config=config)

    # ✅ 可选：对静态模板生成的计划做可见性标注
    # annotate_plan 已在 build_plan 内部调用，会填充 is_visible

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


# ==================== ✅ 新增：自由问答（导览中提问） ====================

@router.post("/sessions/{session_id}/chat")
async def chat_in_tour(session_id: str, req: ChatRequest):
    """
    用户在导览过程中自由提问。
    例如："旁边那颗亮星是什么？"、"这个星座有什么故事？"
    """
    session = _load_session(session_id)
    current_idx = session.get("current_step_index", 0)
    plan = session.get("plan")

    # 构建上下文：当前步骤信息
    context_info = {}
    if plan and "steps" in plan and current_idx < len(plan["steps"]):
        step = plan["steps"][current_idx]
        context_info = {
            "current_step": step.get("title"),
            "targets": [t.get("name_zh") for t in step.get("targets", [])],
        }

    # 简化版：直接调用 LLM 生成回答（实际应接入 RAG 或更复杂的 Agent）
    # 这里仅返回框架，具体实现可调用 generate_narration 或新的 chat_completion
    answer = f"关于'{req.text}'的回答（当前在观测：{context_info.get('current_step', '未知')}）。"

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        referenced_targets=[],
        suggested_action=None,
    ).model_dump()


# ==================== 导览控制（保持不变） ====================

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