"""
功能④：智能交通安排
- 使用免费 OSRM 路由（无需 API Key）
- 输出驾车距离/时长建议
"""
from typing import Any, Dict

import httpx

from .registry import register


@register(
    name="plan_transport",
    schema={
        "type": "function",
        "function": {
            "name": "plan_transport",
            "description": "规划从起点到观测地点的自驾路线（距离 + 时长）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_lat": {"type": "number"},
                    "from_lon": {"type": "number"},
                    "to_lat":   {"type": "number"},
                    "to_lon":   {"type": "number"},
                    "mode": {
                        "type": "string",
                        "enum": ["driving", "walking", "cycling"],
                        "description": "出行方式，默认 driving",
                    },
                },
                "required": ["from_lat", "from_lon", "to_lat", "to_lon"],
            },
        },
    },
)
async def plan_transport(
    from_lat: float, from_lon: float,
    to_lat: float, to_lon: float,
    mode: str = "driving",
) -> Dict[str, Any]:
    url = (
        f"http://router.project-osrm.org/route/v1/{mode}/"
        f"{from_lon},{from_lat};{to_lon},{to_lat}"
    )
    params = {"overview": "false", "steps": "false"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"路由服务不可用: {e}"}

    routes = data.get("routes") or []
    if not routes:
        return {"ok": False, "error": "未找到可用路线"}

    rt = routes[0]
    dur_min = int(rt["duration"] / 60)
    dist_km = round(rt["distance"] / 1000, 1)

    # 生成人性化建议
    if mode == "driving":
        if dur_min <= 15:
            sug = "短途自驾，注意夜间山区道路。"
        elif dur_min <= 60:
            sug = "中程自驾，建议出发前检查油量，带上红光手电。"
        else:
            sug = "长途自驾，建议两人轮流驾驶，提前查看路况和天气。"
    elif mode == "walking":
        sug = "步行路线，注意夜间安全和照明。"
    else:
        sug = "骑行路线，注意车灯和反光装备。"

    return {
        "ok": True,
        "mode": mode,
        "distance_km": dist_km,
        "duration_minutes": dur_min,
        "suggestion": sug,
    }