"""识星模块配置：所有环境变量集中读取一次。"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEBUG_DIR = BACKEND_DIR / "debug"


def _env(name: str, default, cast=str):
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


class VisionConfig:
    # ---- 检测 ----
    MAX_DIM         = _env("VISION_MAX_DIM", 1280, int)
    TOP_N           = _env("VISION_TOP_N", 50, int)       # 100 → 50
    MAX_UPLOAD_MB   = _env("VISION_MAX_UPLOAD_MB", 20, int)
    MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
    EDGE_MARGIN     = _env("VISION_EDGE_MARGIN", 0.10, float)
    DETECT_SIGMA    = _env("VISION_DETECT_SIGMA", 10.0, float)  # 6.0 → 10.0

    # ---- 置信度（仅用于标记低置信结果 + bbox 过滤） ----
    CONFIDENCE_THRESHOLD = _env("VISION_CONFIDENCE_THRESHOLD", 0.51, float)
    # 硬地板：低于该值的 VL 结果直接丢弃
    MIN_CONFIDENCE_KEEP  = _env("VISION_MIN_CONFIDENCE_KEEP", 0.20, float)
    
    # ---- 星座投影拟合 ----
    CATALOG_MAX_MAG    = _env("VISION_CATALOG_MAX_MAG", 5.0, float)
    RANSAC_ITER        = _env("VISION_RANSAC_ITER", 8000, int)
    RANSAC_EPS_RATIO   = _env("VISION_RANSAC_EPS_RATIO", 0.03, float)
    RANSAC_SHAPE_TOL   = _env("VISION_RANSAC_SHAPE_TOL", 0.15, float)
    MIN_INLIERS        = _env("VISION_MIN_INLIERS", 5, int)

    # ---- VL ----
    VL_API_URL = os.getenv(
        "ZHIPU_API_URL",
        "https://api-inference.modelscope.cn/v1/chat/completions",
    ).strip()
    VL_API_KEY = os.getenv(
        "MODELSCOPE_API_KEY", os.getenv("ZHIPU_API_KEY", "")
    ).strip()
    VL_MODEL       = os.getenv("VL_MODEL", "deepseek-ai/DeepSeek-V4-Flash-Vision-Exp").strip()
    VL_TIMEOUT     = _env("VISION_VL_TIMEOUT", 300.0, float)
    VL_MAX_RETRIES = _env("VISION_VL_MAX_RETRIES", 4, int)
    VL_MAX_TOKENS  = _env("VISION_VL_MAX_TOKENS", 4000, int)

    DEBUG_VISION = _env("DEBUG_VISION", 0, int) == 1