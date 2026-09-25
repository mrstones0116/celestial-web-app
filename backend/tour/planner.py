from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime

from .templates import (
    build_summer_sky_steps,
    build_winter_sky_steps,
    build_bright_star_steps,
    build_messier_marathon_steps,
)
from .schemas import TourPlan, TourStep, TourTarget, CameraTarget, Narration
from .astro_utils import annotate_plan, compute_visible_objects, sort_observation_path, _ra_to_deg, _dec_to_deg
# ✅ 扩展关键词，支持更自然的表达
_INTENT_KEYWORDS = {
    "what_visible": [
        "现在能看到", "现在看什么", "今晚能看到", "能看到什么星星",
        "有什么星星", "推荐星星", "现在看", "今晚看", "今晚有什么",
        "能看到什么", "什么星星", "哪些星", "可见的星",
        "what can i see", "visible now", "what's out tonight",
        "what stars", "can i see",
    ],
    "recommend_order": [
        "观测顺序", "推荐顺序", "先看什么", "按什么顺序",
        "什么顺序", "路线", "规划", "帮我推荐", "观测计划",
        "从哪开始", "先看哪颗", "观测路线",
        "observation order", "observation plan", "where to start",
    ],
    "summer_sky": ["夏季星空", "夏季大三角", "夏夜", "夏天星空", "summer sky", "织女", "牛郎", "天津四"],
    "winter_sky": ["冬季星空", "冬季大三角", "冬夜", "冬天星空", "winter sky", "猎户", "天狼"],
    "messier_marathon": ["梅西耶", "messier", "深空", "星云", "星团"],
    "bright_star_tour": ["亮星", "最亮的星", "最亮", "bright star", "brightest"],
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


# ==================== ✅ 新增：动态导览计划生成 ====================

def _star_to_target(star: Dict[str, Any], index: int) -> TourTarget:
    """将 get_stars() 返回的星表记录转换为 TourTarget。"""

    # ✅ 修正：get_stars() 返回的是 "name"，不是 "proper"
    name_en = str(star.get("name", "") or star.get("proper", "") or "").strip()

    # ✅ 过滤无意义的名称（纯数字、"未知"、"Star_xxx"）
    if not name_en or name_en == "未知" or name_en.startswith("Star_"):
        name_en = ""

    STAR_NAME_ZH = {
        "Sirius": "天狼星", "Canopus": "老人星", "Arcturus": "大角星",
        "Vega": "织女星", "Capella": "五车二", "Rigel": "参宿七",
        "Procyon": "南河三", "Achernar": "水委一", "Betelgeuse": "参宿四",
        "Hadar": "马腹一", "Altair": "牛郎星", "Acrux": "十字架二",
        "Aldebaran": "毕宿五", "Antares": "心宿二", "Spica": "角宿一",
        "Pollux": "北河三", "Fomalhaut": "北落师门", "Deneb": "天津四",
        "Regulus": "轩辕十四", "Adhara": "弧矢七", "Castor": "北河二",
        "Mimosa": "十字架三", "Shaula": "尾宿八", "Bellatrix": "参宿五",
        "Elnath": "五车五", "Alnilam": "参宿二", "Alnitak": "参宿一",
        "Alioth": "玉衡", "Dubhe": "天枢", "Merak": "天璇",
        "Phecda": "天玑", "Megrez": "天权", "Mizar": "开阳",
        "Alkaid": "摇光", "Polaris": "北极星",
    }

    name_zh = STAR_NAME_ZH.get(name_en, "")
    if not name_zh:
        name_zh = name_en if name_en else f"亮星 {index + 1}"

    # ✅ 修正：get_stars() 没有 "id"/"hip"，用 name 生成唯一 ID
    hyg_id = str(star.get("id", star.get("hip", f"star_{name_en or index}")))

    # ✅ 修正：优先用已转换的 ra_deg/dec_deg，否则从 ra_hours 转
    ra_deg = star.get("ra_deg")
    dec_deg = star.get("dec_deg")
    if ra_deg is None:
        ra_deg = _ra_to_deg(star.get("ra_hours") or star.get("ra"))
    if dec_deg is None:
        dec_deg = _dec_to_deg(star.get("dec"))

    # ✅ 修正：get_stars() 返回 "constellation"，不是 "con"
    constellation = star.get("constellation") or star.get("con")

    return TourTarget(
        type="star",
        id=hyg_id,
        hyg_id=hyg_id,
        name_zh=name_zh,
        name_en=name_en,
        constellation=constellation,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        magnitude=star.get("mag"),
        altitude_deg=star.get("altitude_deg"),
        azimuth_deg=star.get("azimuth_deg"),
        description=star.get("description"),
        is_visible=star.get("is_visible", True),
        visibility_note=star.get("visibility_note"),
    )


def build_dynamic_plan(
    stars: List[Dict[str, Any]],
    config: Optional[dict] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    max_steps: int = 8,
    sort_by_path: bool = True,
) -> TourPlan:
    """
    基于实时可见性动态生成导览计划。
    stars: 已由 compute_visible_objects 筛选排序后的星表数据。
    """
    config = config or {}
    prefs = config.get("preferences") or {}
    max_steps = prefs.get("max_steps", max_steps)

    # 计算每个星的实时位置（若尚未计算）
    annotated = compute_visible_objects(stars, config, limit=max_steps * 2)

    if sort_by_path:
        annotated = sort_observation_path(annotated)

    # 截断到最大步骤数
    annotated = annotated[:max_steps]

    if not annotated:
        # ✅ 无可见天体时的兜底：返回空计划并给出警告
        return TourPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:10]}",
            title=title or "当前暂无明亮可见天体",
            description=description or "可能是白天、阴天，或光污染严重。请尝试到更黑暗的地方，或稍后再试。",
            total_minutes=0,
            difficulty="easy",
            steps=[],
            warnings=["当前时间/地点下未找到足够亮的可见天体"],
        )

    steps: List[TourStep] = []
    for i, star in enumerate(annotated):
        target = _star_to_target(star, i)

        # 相机指向该星
        camera = CameraTarget(
            center_ra_deg=target.ra_deg or 0,
            center_dec_deg=target.dec_deg or 0,
            fov_deg=25.0,
            highlight_ids=[target.id],
        )

        # ✅ 基础解说，后续可由 LLM 增强
        alt = target.altitude_deg or 0
        az = target.azimuth_deg or 0
        direction = _azimuth_to_direction(az)

        narration = Narration(
            short=f"{target.name_zh}，视星等 {target.magnitude:.1f}" if target.magnitude else target.name_zh,
            long=f"{target.name_zh}目前位于{direction}，高度约{alt:.0f}°。",
            observation_tip=f"面向{direction}，仰角约{alt:.0f}°，寻找这颗星。",
        )

        steps.append(TourStep(
            step_index=i,
            title=target.name_zh or f"亮星 {i+1}",
            subtitle=f"视星等 {target.magnitude:.1f}" if target.magnitude else None,
            targets=[target],
            camera=camera,
            narration=narration,
            estimated_minutes=2,
            next_hint="点击下一步，继续探索" if i < len(annotated) - 1 else "导览结束，感谢观看",
        ))

    location = config.get("location") or {}
    lat = location.get("latitude", 22.3193)
    lon = location.get("longitude", 114.1694)

    plan = TourPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:10]}",
        title=title or "实时星空导览",
        description=description or f"基于当前时间地点为你推荐的 {len(steps)} 颗明亮天体。",
        total_minutes=sum(s.estimated_minutes for s in steps),
        difficulty="easy",
        steps=steps,
        generated_at=datetime.now().isoformat(),
        location_summary=f"纬度 {lat:.2f}°, 经度 {lon:.2f}°",
    )

    # 统一标注可见性（若 build_dynamic_plan 内部已计算，此步可省略）
    # annotate_plan(plan, config)
    return plan


def _azimuth_to_direction(az: float) -> str:
    """方位角转中文方向。"""
    if az is None:
        return "未知方向"
    dirs = ["正北", "东北", "正东", "东南", "正南", "西南", "正西", "西北"]
    idx = int((az + 22.5) / 45) % 8
    return dirs[idx]


# ==================== 保留原有静态计划生成（作为兜底） ====================

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

    annotate_plan(plan, config)
    return plan