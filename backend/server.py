"""
天球可视化系统 - FastAPI 后端
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from data_loader import HYGDataLoader

app = FastAPI(
    title="3D天球可视化系统 API",
    description="HYG星表数据 - 天球可视化后端服务",
    version="1.0.0"
)

# CORS 配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局数据加载器实例
loader = HYGDataLoader()

# 注意：已删除 @app.get("/") 路由，让根路径直接返回 index.html，避免白屏 JSON

@app.get("/api/status")
async def get_status():
    """获取数据加载状态"""
    return {
        "loaded": loader.loaded,
        "total_stars": len(loader.df) if loader.df is not None else 0
    }

@app.post("/api/load")
async def load_data():
    """加载HYG星表数据"""
    result = loader.load_data()
    if not result['success']:
        raise HTTPException(status_code=500, detail=result['message'])
    return result

@app.get("/api/stars")
async def get_stars(
    max_mag: float = Query(default=6.0, ge=-2, le=6, description="最大星等")
):
    """获取星星数据（支持星等筛选）"""
    if not loader.loaded:
        raise HTTPException(status_code=400, detail="数据尚未加载，请先调用 /api/load")
    stars = loader.get_stars(max_mag=max_mag)
    return {
        "count": len(stars),
        "stars": stars
    }

@app.get("/api/bright-stars")
async def get_bright_stars(
    max_mag: float = Query(default=2.5, description="亮星阈值")
):
    """获取亮星标注数据"""
    if not loader.loaded:
        raise HTTPException(status_code=400, detail="数据尚未加载")
    stars = loader.get_bright_stars(max_mag=max_mag)
    return {"count": len(stars), "stars": stars}

@app.get("/api/stats")
async def get_stats(
    max_mag: float = Query(default=6.0, description="最大星等")
):
    """获取统计信息"""
    if not loader.loaded:
        raise HTTPException(status_code=400, detail="数据尚未加载")
    return loader.get_stats(max_mag=max_mag)

@app.get("/api/constellations")
async def get_constellations(
    max_mag: float = Query(default=6.0, description="最大星等")
):
    """获取星座统计"""
    if not loader.loaded:
        raise HTTPException(status_code=400, detail="数据尚未加载")
    stats = loader.get_constellation_stats(max_mag=max_mag)
    return {"count": len(stats), "constellations": stats}

@app.get("/api/top-bright")
async def get_top_bright(
    limit: int = Query(default=15, ge=1, le=100, description="返回数量"),
    max_mag: float = Query(default=6.0, description="最大星等")
):
    """获取最亮的星星"""
    if not loader.loaded:
        raise HTTPException(status_code=400, detail="数据尚未加载")
    stars = loader.get_top_bright_stars(limit=limit, max_mag=max_mag)
    return {"count": len(stars), "stars": stars}

@app.get("/api/spectral-info")
async def get_spectral_info():
    """获取光谱类型信息"""
    return {
        "colors": HYGDataLoader.SPECTRAL_COLORS,
        "info": HYGDataLoader.SPECTRAL_INFO
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)