"""
实时光污染查询：DarkSkySites API
- 返回 SQM (mag/arcsec²) 与 Bortle 等级 (1-9)
- 需要环境变量 DARKSKYSITES_API_KEY
- 失败时抛异常，由 registry 统一包装为 {"ok": False, "error": ...}
"""
import os
from typing import Any, Dict

import httpx

from .registry import register


def _api_key() -> str:
    return os.getenv("DARKSKYSITES_API_KEY", "").strip()


@register(
    name="get_light_pollution",
    schema={
        "type": "function",
        "function": {
            "name": "get_light_pollution",
            "description": (
                "查询指定经纬度的实时天空亮度和光污染等级，返回 SQM (mag/arcsec²) "
                "和 Bortle 等级 (1-9，1 最暗、9 最亮)。"
                "评估单一地点观测条件时必须调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "纬度，-90~90"},
                    "lon": {"type": "number", "description": "经度，-180~180"},
                },
                "required": ["lat", "lon"],
            },
        },
    },
)
async def get_light_pollution(lat: float, lon: float) -> Dict[str, Any]:
    key = _api_key()
    if not key:
        raise RuntimeError("光污染数据服务未配置（缺少 DARKSKYSITES_API_KEY）")

    url = "https://darkskysites.com/api/sqm"
    params = {"lat": lat, "lng": lon}
    headers = {"x-api-key": key}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    bortle = data.get("bortleClass")
    sqm = data.get("sqm")
    if bortle is None and sqm is None:
        raise RuntimeError("光污染服务返回空数据")

    return {
        "lat": lat,
        "lon": lon,
        "sqm": sqm,
        "bortle_class": bortle,
        "bortle_description": data.get("bortleDescription"),
        "attribution": "darkskysites.com",
    }