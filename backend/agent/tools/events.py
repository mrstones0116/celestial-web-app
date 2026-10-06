"""
功能③：近期天象推荐指数
- 读取内置天象日历
- 结合当前月相（新月=最佳）调整推荐指数
"""
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from .registry import register

_DATA = Path(__file__).resolve().parent.parent / "data" / "celestial_events.json"


def _load_events() -> List[Dict[str, Any]]:
    try:
        with open(_DATA, "r", encoding="utf-8") as f:
            return json.load(f).get("events", [])
    except Exception as e:
        print(f"[events] 天象数据加载失败: {e}")
        return []


def _moon_phase_factor(date_iso: str) -> float:
    """
    返回 0~1 的月相因子：新月≈1（适合观星），满月≈0.2（月亮干扰大）。
    用简单近似算法，误差 ±1 天可接受。
    """
    try:
        dt = datetime.fromisoformat(date_iso).replace(tzinfo=timezone.utc)
    except Exception:
        return 0.7
    # 参考新月：2000-01-06 18:14 UTC
    ref = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    days = (dt - ref).total_seconds() / 86400
    synodic = 29.530588853
    phase = (days % synodic) / synodic   # 0=新月, 0.5=满月
    # cos(2π·phase)：新月→1，满月→-1，映射到 [0.2, 1.0]
    return 0.6 + 0.4 * math.cos(2 * math.pi * phase)


@register(
    name="get_celestial_events",
    schema={
        "type": "function",
        "function": {
            "name": "get_celestial_events",
            "description": "获取未来 N 天内的天象事件及其推荐指数（0~1）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "未来多少天，默认 30，最大 90",
                        "default": 30,
                    },
                    "event_type": {
                        "type": "string",
                        "description": "可选过滤：meteor_shower / planet_opposition / full_moon / new_moon / eclipse / conjunction",
                    },
                },
            },
        },
    },
)
async def get_celestial_events(
    days_ahead: int = 30,
    event_type: str = None,
) -> Dict[str, Any]:
    days_ahead = max(1, min(days_ahead, 90))
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    events = _load_events()
    out = []
    for e in events:
        try:
            d = datetime.fromisoformat(e["date"]).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if not (now <= d <= end):
            continue
        if event_type and e.get("type") != event_type:
            continue

        base = float(e.get("base_score", 0.6))
        moon_f = _moon_phase_factor(e["date"])
        final = round(base * (0.4 + 0.6 * moon_f), 3)

        out.append({
            "name": e["name"],
            "date": e["date"],
            "event_type": e["type"],
            "recommendation": final,
            "reason": e.get("reason", ""),
            "visibility": e.get("visibility"),
        })

    out.sort(key=lambda x: x["recommendation"], reverse=True)
    return {
        "events": out,
        "range": f"{now.date()} ~ {end.date()}",
        "note": "推荐指数已结合月相调整（新月+满月权重）",
    }