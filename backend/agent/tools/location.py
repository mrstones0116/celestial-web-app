"""
功能②：观测地点推荐
- 读取内置光污染站点表（data/light_pollution.json）
- 按距离过滤 + Bortle 等级评分
- 可选：接入 OpenWeatherMap 云图（需要 WEATHER_API_KEY）
"""
import json
import math
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import httpx

from .registry import register

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
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))


async def _get_cloud_cover(lat: float, lon: float) -> Optional[float]:
    """返回云量 0~100，若未配置天气 API 则返回 None。"""
    key = os.getenv("WEATHER_API_KEY", "").strip()
    if not key:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": key, "units": "metric"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        return float(data.get("clouds", {}).get("all", 0))
    except Exception as e:
        print(f"[location] 云图获取失败: {e}")
        return None


@register(
    name="recommend_observation_site",
    schema={
        "type": "function",
        "function": {
            "name": "recommend_observation_site",
            "description": "根据用户的经纬度推荐附近适合观星的地点（考虑光污染、距离）。",
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
                        "description": "返回几个推荐，默认 3",
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
        return {"sites": [], "note": "光污染数据未加载"}

    scored = []
    for s in sites:
        d = _haversine_km(lat, lon, s["lat"], s["lon"])
        if d > max_distance_km:
            continue
        # 距离越近越好、Bortle 越小越好
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
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]

    # 可选：补充云量信息
    for site in top:
        cc = await _get_cloud_cover(site["lat"], site["lon"])
        if cc is not None:
            site["cloud_cover_pct"] = cc

    return {
        "sites": top,
        "note": (
            "评分 = 距离 35% + 光污染 65%。"
            "Bortle 等级 1 最暗、9 最亮。"
            + ("已附加云量" if any("cloud_cover_pct" in s for s in top) else "未配置 WEATHER_API_KEY，无云量数据")
        ),
    }