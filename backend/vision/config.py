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
    TOP_N           = _env("VISION_TOP_N", 100, int)
    MAX_UPLOAD_MB   = _env("VISION_MAX_UPLOAD_MB", 20, int)
    MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
    EDGE_MARGIN     = _env("VISION_EDGE_MARGIN", 0.10, float)
    DETECT_SIGMA    = _env("VISION_DETECT_SIGMA", 6.0, float)

    # ---- 聚类（自适应 K） ----
    # 设为 >=2 时强制该 K；否则在 [MIN_K, MAX_K] 内自适应
    FORCED_K        = _env("VISION_FORCED_K", 0, int) or None
    MIN_K           = _env("VISION_MIN_K", 2, int)
    MAX_K           = _env("VISION_MAX_K", 8, int)
    KMEANS_N_INIT   = _env("VISION_KMEANS_N_INIT", 10, int)
    KMEANS_MAX_ITER = _env("VISION_KMEANS_MAX_ITER", 200, int)
    CLUSTER_MIN_STARS = _env("VISION_CLUSTER_MIN_STARS", 3, int)

    # ---- 权重 ----
    WEIGHT_BRIGHTNESS = _env("VISION_WEIGHT_BRIGHTNESS", 0.65, float)
    WEIGHT_DISTANCE   = _env("VISION_WEIGHT_DISTANCE", 0.35, float)

    # ---- 置信度 ----
    CONFIDENCE_THRESHOLD = _env("VISION_CONFIDENCE_THRESHOLD", 0.51, float)

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

    DEBUG_VISION = _env("DEBUG_VISION", 0, int) == 1