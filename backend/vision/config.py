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
    TOP_N           = _env("VISION_TOP_N", 50, int)
    MAX_UPLOAD_MB   = _env("VISION_MAX_UPLOAD_MB", 20, int)
    MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
    EDGE_MARGIN     = _env("VISION_EDGE_MARGIN", 0.10, float)
    DETECT_SIGMA    = _env("VISION_DETECT_SIGMA", 10.0, float)

    # ---- 置信度 ----
    CONFIDENCE_THRESHOLD = _env("VISION_CONFIDENCE_THRESHOLD", 0.51, float)
    MIN_CONFIDENCE_KEEP  = _env("VISION_MIN_CONFIDENCE_KEEP", 0.20, float)

    # ---- 星座目录 ----
    CATALOG_MAX_MAG  = _env("VISION_CATALOG_MAX_MAG", 5.0, float)

    # ---- Plate solving ----
    PLATE_TEMPLATE_MAG    = _env("VISION_PLATE_TEMPLATE_MAG", 4.5, float)
    PLATE_RANSAC_ITER     = _env("VISION_PLATE_RANSAC_ITER", 6000, int)
    PLATE_EPS_PX          = _env("VISION_PLATE_EPS_PX", 6.0, float)
    PLATE_MIN_INLIERS     = _env("VISION_PLATE_MIN_INLIERS", 3, int)
    PLATE_ICP_ITER        = _env("VISION_PLATE_ICP_ITER", 10, int)
    PLATE_DRAW_ALL_STARS  = _env("VISION_PLATE_DRAW_ALL_STARS", 1, int) == 1

    # ---- VL ----
    VL_API_URL = os.getenv(
        "ZHIPU_API_URL",
        "https://api-inference.modelscope.cn/v1/chat/completions",
    ).strip()
    VL_API_KEY = os.getenv(
        "MODELSCOPE_API_KEY", os.getenv("ZHIPU_API_KEY", "")
    ).strip()
    VL_MODEL       = os.getenv("VL_MODEL", "Qwen/Qwen3.8-Flash-Next").strip()
    VL_TIMEOUT     = _env("VISION_VL_TIMEOUT", 300.0, float)
    VL_MAX_RETRIES = _env("VISION_VL_MAX_RETRIES", 4, int)
    VL_MAX_TOKENS  = _env("VISION_VL_MAX_TOKENS", 4000, int)

    DEBUG_VISION = _env("DEBUG_VISION", 0, int) == 0