#!/usr/bin/env python3
"""
API Key 连通性测试（独立脚本，不依赖项目其他模块）

逐个测试：
  1. LLM（DeepSeek / 兼容 OpenAI 协议）
  2. DarkSkySites 光污染
  3. Google Routes 路线
  4. OpenWeatherMap 云量

用法：
  python test_api_keys.py                     # 自动加载 ./.env
  python test_api_keys.py --env .env.local
  python test_api_keys.py --only llm,routes
  python test_api_keys.py --skip weather

退出码：
  0 = 全部通过
  1 = 有任一失败
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Tuple

import httpx


# ============================================================
# .env 加载（不依赖 python-dotenv）
# ============================================================
def load_env_file(path: Optional[Path]) -> None:
    if not path or not path.exists():
        return
    print(f"[env] 加载 {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:   # 已存在的真实环境变量优先
            os.environ[k] = v


def mask(secret: str) -> str:
    if not secret:
        return "(空)"
    if len(secret) <= 8:
        return "*" * len(secret)
    return secret[:4] + "..." + secret[-4:]


# ============================================================
# 测试 1：LLM
# ============================================================
async def test_llm() -> Tuple[bool, str]:
    url = os.getenv(
        "TOUR_LLM_API_URL", "https://api.deepseek.com/v1/chat/completions"
    ).strip()
    key = (
        os.getenv("TOUR_LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("MODELSCOPE_API_KEY")
        or ""
    ).strip()
    model = (
        os.getenv("AGENT_LLM_MODEL")
        or os.getenv("TOUR_LLM_MODEL")
        or "deepseek-chat"
    )

    if not key:
        return False, "未配置 TOUR_LLM_API_KEY / DEEPSEEK_API_KEY / MODELSCOPE_API_KEY"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "回复两个字：收到"}],
        "max_tokens": 16,
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, json=payload, headers=headers)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"

    try:
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return False, f"响应解析失败: {e}"

    if not content:
        return False, f"返回空内容，原始响应: {r.text[:200]}"

    return True, f"model={model} reply={content!r} key={mask(key)}"


# ============================================================
# 测试 2：DarkSkySites 光污染
# ============================================================
async def test_darkskysites() -> Tuple[bool, str]:
    key = os.getenv("DARKSKYSITES_API_KEY", "").strip()
    base = os.getenv("DARKSKYSITES_API_URL", "https://darkskysites.com/api/sqm").strip()

    if not key:
        return False, "未配置 DARKSKYSITES_API_KEY"

    # 用北京海淀做测试点
    params = {"lat": 39.959, "lng": 116.298}
    headers = {"x-api-key": key}

    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(base, params=params, headers=headers)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if r.status_code == 401 or r.status_code == 403:
        return False, f"HTTP {r.status_code}：key 无效或权限不足"
    if r.status_code == 404:
        return False, (
            "HTTP 404：端点可能已变更。当前使用 "
            f"{base}，请查 darkskysites.com 官方文档，"
            "并用 DARKSKYSITES_API_URL 环境变量覆盖"
        )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"

    try:
        data = r.json()
    except Exception as e:
        return False, f"返回非 JSON: {e}，原始内容: {r.text[:200]}"

    sqm = data.get("sqm")
    bortle = data.get("bortleClass")
    if sqm is None and bortle is None:
        return False, f"返回缺字段 sqm/bortleClass，原始: {data}"

    return True, f"sqm={sqm} bortle={bortle} key={mask(key)}"


# ============================================================
# 测试 3：Google Routes
# ============================================================
async def test_google_routes() -> Tuple[bool, str]:
    key = os.getenv("GOOGLE_ROUTES_API_KEY", "").strip()
    if not key:
        return False, "未配置 GOOGLE_ROUTES_API_KEY"

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
    }
    # 天安门 → 颐和园，短距离测试
    payload = {
        "origin": {
            "location": {"latLng": {"latitude": 39.9087, "longitude": 116.3975}}
        },
        "destination": {
            "location": {"latLng": {"latitude": 39.9999, "longitude": 116.2755}}
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": False,
        "languageCode": "zh-CN",
        "units": "METRIC",
    }

    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(url, json=payload, headers=headers)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if r.status_code in (401, 403):
        return False, (
            f"HTTP {r.status_code}：key 无效、未启用 Routes API，或未开通计费。"
            f"详情: {r.text[:300]}"
        )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:300]}"

    try:
        data = r.json()
    except Exception as e:
        return False, f"返回非 JSON: {e}"

    routes = data.get("routes") or []
    if not routes:
        return False, f"返回无路线，原始: {data}"

    rt = routes[0]
    duration = rt.get("duration", "?")
    distance_m = rt.get("distanceMeters", "?")
    return True, f"duration={duration} distanceMeters={distance_m} key={mask(key)}"


# ============================================================
# 测试 4：OpenWeatherMap
# ============================================================
async def test_openweather() -> Tuple[bool, str]:
    key = os.getenv("WEATHER_API_KEY", "").strip()
    if not key:
        return False, "未配置 WEATHER_API_KEY（可选，缺省时 Agent 无云量数据）"

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": 39.959, "lon": 116.298, "appid": key, "units": "metric"}

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params=params)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if r.status_code == 401:
        return False, "HTTP 401：key 无效"
    if r.status_code == 429:
        return False, "HTTP 429：调用频率超限（免费版有每分钟限制）"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"

    try:
        data = r.json()
    except Exception as e:
        return False, f"返回非 JSON: {e}"

    clouds = data.get("clouds", {}).get("all")
    city = data.get("name", "?")
    if clouds is None:
        return False, f"返回缺 clouds 字段，原始: {data}"

    return True, f"city={city} clouds={clouds}% key={mask(key)}"


# ============================================================
# 执行入口
# ============================================================
ALL_TESTS: List[Tuple[str, Callable[[], Awaitable[Tuple[bool, str]]]]] = [
    ("llm",      test_llm),
    ("pollution", test_darkskysites),
    ("routes",   test_google_routes),
    ("weather",  test_openweather),
]


async def run_selected(names: List[str]) -> int:
    selected = [(n, f) for n, f in ALL_TESTS if n in names]
    if not selected:
        print(f"[!] 没有匹配的测试名，可选: {[n for n, _ in ALL_TESTS]}")
        return 1

    results: List[Tuple[str, bool, str]] = []
    for name, fn in selected:
        print(f"\n>>> 测试 {name} ...")
        try:
            ok, detail = await fn()
        except Exception as e:
            ok, detail = False, f"未捕获异常: {type(e).__name__}: {e}"
        results.append((name, ok, detail))
        mark = "✅ PASS" if ok else "❌ FAIL"
        print(f"    {mark}  {detail}")

    # 汇总
    print("\n" + "=" * 60)
    print("汇总：")
    passed = 0
    for name, ok, _ in results:
        print(f"  {'✅' if ok else '❌'} {name}")
        if ok:
            passed += 1
    print(f"通过 {passed}/{len(results)}")
    print("=" * 60)

    return 0 if passed == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="API Key 连通性测试")
    parser.add_argument(
        "--env",
        default=".env",
        help="要加载的 env 文件，默认 ./.env；设为空字符串则不加载",
    )
    parser.add_argument(
        "--only",
        default="",
        help="只测指定项，逗号分隔：llm,pollution,routes,weather",
    )
    parser.add_argument(
        "--skip",
        default="",
        help="跳过指定项，逗号分隔",
    )
    args = parser.parse_args()

    if args.env:
        load_env_file(Path(args.env))

    all_names = [n for n, _ in ALL_TESTS]
    names = all_names
    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip()]
    if args.skip:
        skip = {n.strip() for n in args.skip.split(",") if n.strip()}
        names = [n for n in names if n not in skip]

    try:
        return asyncio.run(run_selected(names))
    except KeyboardInterrupt:
        print("\n[!] 已中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())