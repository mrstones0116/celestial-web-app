"""
功能②：观测地点推荐
- 静态站点表（data/light_pollution.json）作为候选种子
- 若配置 DARKSKYSITES_API_KEY，对候选点用实时 API 补全校验
- 可选：OpenWeatherMap 云量（WEATHER_API_KEY）
"""
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .registry import register
from .pollution import get_light_pollution

_DATA = Path(__file__).resolve().parent.parent / "data" / "light_pollution.json"


def _load_sites() -> List[Dict[str, Any]]:
    try:
        with open(_DATA, "r", encoding="utf-8") as f:
            return json.load(f).get("sites", [])
    except Exception as e:
        print(f"[location] 光污染数据加载失败: {e}")
        return []


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def _get_cloud_cover(lat: float, lon: float) -> Optional[float]:
    key = os.getenv("WEATHER_API_KEY", "").strip()
    if not key:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": key, "units": "metric"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            return float(r.json().get("clouds", {}).get("all", 0))
    except Exception as e:
        print(f"[location] 云量获取失败: {e}")
        return None


async def _enrich_realtime(site: Dict[str, Any]) -> None:
    """
    用实时光污染 API 补全/覆盖单个候选点的 Bortle 与 SQM。
    API 失败时静默保持静态值。
    """
    try:
        rt = await get_light_pollution(site["lat"], site["lon"])
    except Exception as e:
        print(f"[location] 实时光污染查询失败（保持静态值）: {e}")
        return

    if rt.get("bortle_class") is not None:
        site["bortle_class"] = rt["bortle_class"]
    if rt.get("sqm") is not None:
        site["sqm"] = rt["sqm"]
    site["data_source"] = "darkskysites.com (realtime)"
    site["attribution"] = rt.get("attribution")


@register(
    name="recommend_observation_site",
    schema={
        "type": "function",
        "function": {
            "name": "recommend_observation_site",
            "description": (
                "根据用户经纬度推荐附近适合观星的地点，"
                "考虑光污染（Bortle/SQM）、距离，可选附云量。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "用户纬度"},
                    "lon": {"type": "number", "description": "用户经度"},
                    "max_distance_km": {
                        "type": "number",
                        "description": "最大搜索半径（公里），默认 80",
                        "default": 80,
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "返回几个推荐，默认 3，最大 5",
                        "default": 3,
                    },
                },
                "required": ["lat", "lon"],
            },
        },
    },
)
async def recommend_observation_site(
    lat: float, lon: float,
    max_distance_km: float = 80,
    top_n: int = 3,
) -> Dict[str, Any]:
    sites = _load_sites()
    if not sites:
        return {"sites": [], "note": "本地光污染站点表为空或未加载"}

    top_n = max(1, min(int(top_n), 5))
    max_distance_km = max(5.0, min(float(max_distance_km), 200.0))

    scored = []
    for s in sites:
        d = _haversine_km(lat, lon, s["lat"], s["lon"])
        if d > max_distance_km:
            continue
        dist_score = max(0.0, 1 - d / max_distance_km)
        bortle_score = max(0.0, (9 - s.get("bortle", 5)) / 8)
        total = dist_score * 0.35 + bortle_score * 0.65
        scored.append({
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "distance_km": round(d, 1),
            "bortle_class": s.get("bortle", 5),
            "score": round(total, 3),
            "reason": s.get("note", f"Bortle {s.get('bortle', '?')} 级暗夜环境"),
            "data_source": "static",
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]

    # 对 top_n 做实时补全（最多 top_n 次 API 调用）
    for site in top:
        await _enrich_realtime(site)

    # 可选云量
    for site in top:
        cc = await _get_cloud_cover(site["lat"], site["lon"])
        if cc is not None:
            site["cloud_cover_pct"] = cc

    realtime_used = any(s.get("data_source", "").startswith("darkskysites") for s in top)
    return {
        "sites": top,
        "note": (
            "评分 = 距离 35% + 光污染 65%。Bortle 1 最暗、9 最亮。"
            + ("已用实时 API 补全光污染数据。" if realtime_used else "实时 API 未启用，使用本地静态数据。")
            + ("已附加云量。" if any("cloud_cover_pct" in s for s in top) else "")
        ),
        "attribution": "darkskysites.com" if realtime_used else None,
    }