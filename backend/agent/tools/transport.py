"""
功能④：智能交通安排
- 优先 Google Routes API（需 GOOGLE_ROUTES_API_KEY）
- 失败/未配置时回退免费 OSRM
- 失败时 raise，由 registry 统一包装
"""
import os
from typing import Any, Dict

import httpx

from .registry import register

_GOOGLE_MODE = {
    "driving": "DRIVE",
    "walking": "WALK",
    "cycling": "BICYCLE",
    "transit": "TRANSIT",
}


def _routes_key() -> str:
    return os.getenv("GOOGLE_ROUTES_API_KEY", "").strip()


async def _plan_via_google(
    from_lat: float, from_lon: float,
    to_lat: float, to_lon: float,
    mode: str,
) -> Dict[str, Any]:
    key = _routes_key()
    if not key:
        raise RuntimeError("GOOGLE_ROUTES_API_KEY 未配置")

    travel_mode = _GOOGLE_MODE.get(mode)
    if not travel_mode:
        raise RuntimeError(f"Google Routes 不支持模式: {mode}")

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        # 只取必要字段，控制计费成本
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
    }
    payload = {
        "origin": {"location": {"latLng": {
            "latitude": from_lat, "longitude": from_lon}}},
        "destination": {"location": {"latLng": {
            "latitude": to_lat, "longitude": to_lon}}},
        "travelMode": travel_mode,
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": False,
        "languageCode": "zh-CN",
        "units": "METRIC",
    }

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("Google Routes 未找到可用路线")

    rt = routes[0]
    dur_str = str(rt.get("duration", "0s")).rstrip("s")
    try:
        dur_sec = float(dur_str)
    except ValueError:
        dur_sec = 0.0

    return {
        "distance_km": round(rt.get("distanceMeters", 0) / 1000, 1),
        "duration_minutes": int(round(dur_sec / 60)),
        "source": "google_routes",
    }


async def _plan_via_osrm(
    from_lat: float, from_lon: float,
    to_lat: float, to_lon: float,
    mode: str,
) -> Dict[str, Any]:
    if mode not in {"driving", "walking", "cycling"}:
        mode = "driving"
    url = (
        f"http://router.project-osrm.org/route/v1/{mode}/"
        f"{from_lon},{from_lat};{to_lon},{to_lat}"
    )
    params = {"overview": "false", "steps": "false"}

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("OSRM 未找到可用路线")

    rt = routes[0]
    return {
        "distance_km": round(rt["distance"] / 1000, 1),
        "duration_minutes": int(rt["duration"] / 60),
        "source": "osrm",
    }


def _suggestion(mode: str, dur_min: int) -> str:
    if mode == "driving":
        if dur_min <= 15:
            return "短途自驾，注意夜间山区道路。"
        if dur_min <= 60:
            return "中程自驾，出发前检查油量，带上红光手电。"
        return "长途自驾，建议两人轮流驾驶，提前查看路况和天气。"
    if mode == "walking":
        return "步行路线，注意夜间安全和照明。"
    if mode == "cycling":
        return "骑行路线，注意车灯和反光装备。"
    return "注意出行安全。"


@register(
    name="plan_transport",
    schema={
        "type": "function",
        "function": {
            "name": "plan_transport",
            "description": (
                "规划从起点到观测地点的路线（真实距离 + 预计耗时），"
                "支持驾车/步行/骑行/公交。用户询问交通方式或行程时间时必须调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_lat": {"type": "number"},
                    "from_lon": {"type": "number"},
                    "to_lat": {"type": "number"},
                    "to_lon": {"type": "number"},
                    "mode": {
                        "type": "string",
                        "enum": ["driving", "walking", "cycling", "transit"],
                        "description": "出行方式，默认 driving",
                        "default": "driving",
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
    mode = (mode or "driving").lower()
    route: Dict[str, Any] | None = None

    # 1) 优先 Google Routes
    try:
        route = await _plan_via_google(from_lat, from_lon, to_lat, to_lon, mode)
    except Exception as e:
        print(f"[transport] Google Routes 失败，回退 OSRM: {e}")

    # 2) 回退 OSRM
    if route is None:
        try:
            route = await _plan_via_osrm(from_lat, from_lon, to_lat, to_lon, mode)
        except Exception as e:
            raise RuntimeError(f"路线服务均不可用: {e}") from e

    dur = route["duration_minutes"]
    return {
        "mode": mode,
        "distance_km": route["distance_km"],
        "duration_minutes": dur,
        "suggestion": _suggestion(mode, dur),
        "data_source": route["source"],
    }