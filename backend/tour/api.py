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
from .planner import (
    build_plan,
    build_dynamic_plan,
    detect_intent,
    build_plan_from_llm_response,   # ✅ 新增
)
from .llm_client import (
    parse_instruction,
    generate_narration,
    generate_batch_narration,
    generate_tour_plan_from_snapshot,   # ✅ 新增
)
from .session_store import tour_store
from .planner import build_plan, build_dynamic_plan, detect_intent
from .llm_client import parse_instruction, generate_narration, generate_batch_narration
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

# 前端 buildPrompt() 输出的报告里必然包含这个标志串
_SNAPSHOT_MARKER = "实时星空观测报告"


async def _build_snapshot_plan(prompt_text: str, config: dict):
    """
    「实时星空快照」专用通道：
    跳过关键词意图识别，直接让 LLM 生成完整 TourPlan。
    返回 TourPlan 或 None（失败时前端会自动回退到本地兜底导览）。
    """
    data = await generate_tour_plan_from_snapshot(prompt_text, config)
    if not data:
        print("[tour] 快照导览：LLM 未返回有效 JSON")
        return None
    plan = build_plan_from_llm_response(data, config)
    if plan is None:
        print("[tour] 快照导览：JSON 转换 TourPlan 失败")
    return plan

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

    config = session.get("config", {})

    # ============================================================
    # ★ 快照通道：前端发来的「实时星空观测报告」→ LLM 直接产完整计划
    # ============================================================
    if _SNAPSHOT_MARKER in (req.text or ""):
        print(f"[tour] 检测到实时星空快照提示（长度 {len(req.text)}），走专用通道")
        plan = await _build_snapshot_plan(req.text, config)

        if plan is None:
            # 让前端拿到可识别的失败信号，它会自动降级到本地兜底
            return TourSessionResponse(
                session_id=session_id,
                status="empty",
                plan=None,
                current_step_index=0,
                message="AI 暂时无法生成导览，请稍后重试（已自动降级）",
            ).model_dump()

        history = list(session.get("history", []))
        history.append("[实时星空快照]")

        tour_store.update(session_id, {
            "status": "ready",
            "plan": plan.model_dump(),
            "current_step_index": 0,
            "history": history,
            "last_intent": {
                "intent": "sky_snapshot",
                "source": "llm",
                "confidence": 1.0,
                "entities": {},
            },
        })

        print(f"[tour] ✅ 快照导览已生成：{len(plan.steps)} 步")
        return TourSessionResponse(
            session_id=session_id,
            status="ready",
            plan=plan,
            current_step_index=0,
            message=f"导览已生成（{len(plan.steps)} 步）",
        ).model_dump()

    # ============================================================
    # 以下为原有逻辑（用户自然语言指令），完全保留
    # ============================================================
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
    # ⚠️ 注意：原来这里有一行 `config = session.get("config", {})`
    #    因为上面已经定义了 config，这里删掉该行避免重复赋值
    config = session.get("config", {})

    # ✅ 时间处理：如果提到“现在/今晚/明早”等，强制使用实时/近期时间
    time_exp = entities.get("time_expression", "")
    if any(kw in time_exp for kw in ["现在", "今晚", "now", "tonight", "明天", "日出", "凌晨"]):
        config.setdefault("observing_time", {})["use_real_time"] = True

    plan = None

    # ==================== 分支1：实时可见查询 ====================
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
                session_id=session_id, status="empty", plan=None, current_step_index=0,
                message="当前时间地点下未找到足够亮的可见天体。请尝试到光污染更少的地方，或稍后再试。",
            ).model_dump()
            
        plan = build_dynamic_plan(
            stars=visible,
            config=config,
            title="实时星空导览" if intent == "what_visible" else "推荐观测顺序",
            description="根据你的时间和位置，为你实时计算的可见亮星。",
            max_steps=min(10, len(visible)),
            sort_by_path=(intent == "recommend_order"),
        )

    # ==================== 分支2：主题导览（如夏季星空） ====================
    else:
        # 使用原有的静态模板生成计划（内部已包含可见性标注）
        plan = build_plan(intent, config=config)

    # ==================== 🌟 统一增强：为所有计划生成 LLM 个性化解说 ====================
    if plan and plan.steps:
        try:
            stars_info = []
            for step in plan.steps:
                if step.targets:
                    t = step.targets[0]
                    stars_info.append({
                        "name_zh": t.name_zh,
                        "name_en": t.name_en,
                        "constellation": t.constellation,
                        "magnitude": t.magnitude,
                        "altitude_deg": t.altitude_deg,
                        "azimuth_deg": t.azimuth_deg,
                    })
            
            prefs = config.get("preferences") or {}
            narrations = await generate_batch_narration(
                stars_info=stars_info,
                location_summary="香港",
                user_style=prefs.get("style", "story"),
                locale="zh-CN",
            )
            
            # 将 LLM 生成的解说写入每个步骤
            for i, step in enumerate(plan.steps):
                if i < len(narrations) and isinstance(narrations[i], dict):
                    n = narrations[i]
                    step.narration.short = n.get("short", step.narration.short)
                    step.narration.long = n.get("long", step.narration.long)
                    step.narration.best_time = n.get("best_time")
                    step.narration.cultural_story = n.get("cultural_story")
                    step.narration.observation_tip = n.get("observation_tip", step.narration.observation_tip)
                    step.narration.fun_fact = n.get("fun_fact")
                    
            print(f"[tour] ✅ 已为 {len(narrations)} 颗星生成个性化解说")
        except Exception as e:
            print(f"[tour] ⚠️ 解说生成失败，使用模板兜底: {e}")

    # ==================== 保存状态并返回 ====================
    history = list(session.get("history", []))
    history.append(req.text)
    
    tour_store.update(session_id, {
        "status": "ready",
        "plan": plan.model_dump() if plan else None,
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