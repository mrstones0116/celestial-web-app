"""
天球可视化系统 - FastAPI 后端 · 照片识星 v4 + AI 天文小助手
· 本地 OpenCV 检测
· VL 只识别星座名（三字母缩写）
· HYG 星表 + RANSAC 拟合投影，忠实绘制星座骨架
· AI Agent：知识问答 / 观测地点推荐 / 天象指数 / 交通安排
"""
import os
import sys
import asyncio
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

try:
    from dotenv import load_dotenv
    _env_path = _BACKEND_DIR / ".env"
    _loaded = load_dotenv(_env_path)
    print(f"✅ .env: {_env_path} （{'已加载' if _loaded else '文件不存在，跳过'}）")
except Exception as _e:
    print(f"⚠️  .env 加载失败: {_e}")

from typing import Optional

from fastapi import FastAPI, Query, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from data_loader import HYGDataLoader
from tour.api import router as tour_router, set_loader

# ★ 新增：AI 天文小助手 Agent
from agent import agent_router

from vision.config import VisionConfig
from vision.pipeline import VisionPipeline
from vision.constellation_catalog import ConstellationCatalog


# ==================== App & 中间件 ====================

app = FastAPI(title="3D天球可视化系统 API", version="4.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 已有：导览模块
app.include_router(tour_router, prefix="/api/tour", tags=["tour"])

# ★ 新增：AI 天文小助手（agent 路由内部已定义 /api/agent 前缀）
app.include_router(agent_router)


# ==================== 全局单例 ====================

loader = HYGDataLoader()
set_loader(loader)

_catalog = ConstellationCatalog(loader)
_vision = VisionPipeline(catalog=_catalog)


# ==================== 启动钩子：预加载星表 ====================

@app.on_event("startup")
async def _startup_load():
    # 1) 加载 HYG 星表
    if not loader.loaded:
        print("⏳ 启动时预加载星表 ...")
        try:
            await asyncio.to_thread(loader.load_data)
            n = len(loader.df) if loader.df is not None else 0
            print(f"✅ 星表已加载: {n} 颗")
        except Exception as e:
            print(f"⚠️ 星表加载失败: {e}")

    # 2) 星表就绪后再加载 catalog
    try:
        _catalog.load()
        s = _catalog.stats()
        print(f"📚 星座目录: {s['members_constellations']} 个成员表, "
              f"{s['lines_constellations']} 个骨架表")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"⚠️ catalog 加载失败: {e}")

    # 3) ★ 新增：探测 Agent 可用工具
    try:
        from agent.tools import list_tools
        tools = list_tools()
        print(f"🤖 AI 小助手: 已注册 {len(tools)} 个工具 → {', '.join(tools)}")
    except Exception as e:
        print(f"⚠️ Agent 工具注册表加载失败: {e}")


# ==================== 基础数据 API ====================

@app.get("/api/status")
async def get_status():
    return {
        "loaded": loader.loaded,
        "total_stars": len(loader.df) if loader.df is not None else 0,
    }


@app.post("/api/load")
async def load_data():
    return loader.load_data()


@app.get("/api/stars")
async def get_stars(max_mag: float = Query(default=6.0, ge=-2, le=8)):
    if not loader.loaded:
        raise HTTPException(400, "数据尚未加载")
    s = loader.get_stars(max_mag=max_mag)
    return {"count": len(s), "stars": s}


@app.get("/api/bright-stars")
async def get_bright_stars(max_mag: float = Query(default=2.5)):
    if not loader.loaded:
        raise HTTPException(400, "数据尚未加载")
    s = loader.get_bright_stars(max_mag=max_mag)
    return {"count": len(s), "stars": s}


@app.get("/api/stats")
async def get_stats(max_mag: float = Query(default=6.0)):
    if not loader.loaded:
        raise HTTPException(400, "数据尚未加载")
    return loader.get_stats(max_mag=max_mag)


@app.get("/api/constellations")
async def get_constellations(max_mag: float = Query(default=6.0)):
    if not loader.loaded:
        raise HTTPException(400, "数据尚未加载")
    stats = loader.get_constellation_stats(max_mag=max_mag)
    return {"count": len(stats), "constellations": stats}


@app.get("/api/top-bright")
async def get_top_bright(
    limit: int = Query(default=15, ge=1, le=100),
    max_mag: float = Query(default=6.0),
):
    if not loader.loaded:
        raise HTTPException(400, "数据尚未加载")
    s = loader.get_top_bright_stars(limit=limit, max_mag=max_mag)
    return {"count": len(s), "stars": s}


@app.get("/api/spectral-info")
async def get_spectral_info():
    return {
        "colors": HYGDataLoader.SPECTRAL_COLORS,
        "info": HYGDataLoader.SPECTRAL_INFO,
    }


# ==================== 照片识星 API ====================

@app.get("/api/vision/status")
async def vision_status():
    return _vision.status()


@app.get("/api/vision/vl-status")
async def vl_status_compat():
    return _vision.status()


@app.post("/api/vision/brightest-stars")
async def brightest_stars(
    file: UploadFile = File(...),
    top_n: int = Query(default=VisionConfig.TOP_N, ge=1, le=200),
    # 兼容旧前端的参数，已无效
    cluster_k: Optional[int] = Query(default=None, ge=2, le=10),
    vl_k: Optional[int] = Query(default=None, ge=2, le=10),
):
    return await _vision.identify_upload(file, top_n=top_n)


@app.post("/api/vision/identify")
async def identify(file: UploadFile = File(...)):
    return await _vision.identify_upload(file)


@app.post("/api/vision/vl-identify")
async def vl_identify_compat(file: UploadFile = File(...)):
    return await _vision.identify_upload(file)


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn

    cfg = VisionConfig
    print("🔭 识星引擎: OpenCV 检测 + VL 语义 + HYG 投影拟合")
    print(f"📁 debug: {cfg.DEBUG_DIR}  (DEBUG_VISION={cfg.DEBUG_VISION})")
    print(f"🖼  边缘遮罩: {cfg.EDGE_MARGIN:.0%}, "
          f"sigma={cfg.DETECT_SIGMA}, top_n={cfg.TOP_N}")
    if cfg.VL_API_KEY:
        print(f"🤖 VL: {cfg.VL_MODEL}  Key={cfg.VL_API_KEY[:6]}...")
    else:
        print("⚠️  未配置 VL API Key")
    print(f"📚 星表: {'已加载' if loader.loaded else '未加载'} "
          f"({len(loader.df) if loader.df is not None else 0} 颗)")

    # ★ 新增：Agent 状态
    try:
        from agent.tools import list_tools
        tools = list_tools()
        print(f"🤖 AI 小助手: {len(tools)} 个工具已注册")
    except Exception as e:
        print(f"⚠️ AI 小助手未就绪: {e}")

    uvicorn.run(app, host="0.0.0.0", port=8000)