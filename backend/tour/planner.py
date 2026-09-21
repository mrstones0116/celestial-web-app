from typing import Optional
import uuid

from .templates import (
    build_summer_sky_steps,
    build_winter_sky_steps,
    build_bright_star_steps,
    build_messier_marathon_steps,
)
from .schemas import TourPlan
from .astro_utils import annotate_plan


# 意图关键词：使用更具体的词组，避免 "夏" 命中 "夏天很热" 之类误判
_INTENT_KEYWORDS = {
    "summer_sky":       ["夏季星空", "夏季大三角", "夏夜", "夏天星空", "summer sky"],
    "winter_sky":       ["冬季星空", "冬季大三角", "冬夜", "冬天星空", "winter sky"],
    "messier_marathon": ["梅西耶", "messier", "深空", "星云", "星团"],
    "bright_star_tour": ["亮星", "最亮的星", "bright star"],
}


def detect_intent(text: str) -> dict:
    t = text.lower()
    for intent, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in t:
                return {"intent": intent}
    return {"intent": "default"}


def _select_builder(intent: str):
    if intent == "summer_sky":
        return build_summer_sky_steps, "夏季星空漫游", "从织女星开始，认识夏季大三角。"
    if intent == "winter_sky":
        return build_winter_sky_steps, "冬季星空漫游", "猎户座、天狼星与冬季亮星。"
    if intent == "messier_marathon":
        return build_messier_marathon_steps, "梅西耶马拉松（示例）", "深空天体观测路线示例。"
    if intent == "bright_star_tour":
        return build_bright_star_steps, "亮星之旅", "认识夜空中最亮的恒星。"
    return build_bright_star_steps, "星空入门漫游", "默认入门路线。"


def build_plan(intent: str, config: Optional[dict] = None) -> TourPlan:
    config = config or {}
    prefs = config.get("preferences") or {}
    max_steps = prefs.get("max_steps", 10)

    builder, title, desc = _select_builder(intent)
    steps = builder(max_steps=max_steps)

    plan = TourPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:10]}",
        title=title,
        description=desc,
        total_minutes=sum(s.estimated_minutes for s in steps),
        difficulty="easy",
        steps=steps,
    )

    # 填充每颗星的 alt/az
    annotate_plan(plan, config)

    return plan