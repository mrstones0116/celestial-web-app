"""
天球可视化系统 - FastAPI 后端 · 照片识星 v1
· 本地 OpenCV 检测 + K-means 聚类（强制 K=6）
· 整图一次调用 VL，让 VL 同时判断全部 6 个簇
· 前端可按颜色区分簇，VL 也按颜色对齐 id
· 不输出 default 单图，只输出 K=6 的标注图
"""
import os
import sys
import asyncio
import json
import re
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

import base64
from io import BytesIO
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Query, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from data_loader import HYGDataLoader
from tour.api import router as tour_router, set_loader

from PIL import Image, ImageDraw, ImageFont
import numpy as np
import cv2

app = FastAPI(title="3D天球可视化系统 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tour_router, prefix="/api/tour", tags=["tour"])

loader = HYGDataLoader()
set_loader(loader)

_DEBUG_DIR = _BACKEND_DIR / "debug"
_DEBUG_DIR.mkdir(exist_ok=True)


# ==================== 配置 ====================

DEBUG_VISION = os.getenv("DEBUG_VISION", "0") == "1"
MAX_DIM = int(os.getenv("VISION_MAX_DIM", "1280"))
TOP_N = int(os.getenv("VISION_TOP_N", "100"))
MAX_UPLOAD_BYTES = int(os.getenv("VISION_MAX_UPLOAD_MB", "20")) * 1024 * 1024
EDGE_MARGIN_RATIO = float(os.getenv("VISION_EDGE_MARGIN", "0.10"))
DETECT_SIGMA = float(os.getenv("VISION_DETECT_SIGMA", "6.0"))

# 强制 K=6
FORCED_K = 6
CLUSTER_K_LIST = [FORCED_K]
VL_CLUSTER_K = FORCED_K

CLUSTER_MIN_STARS_PER_CLUSTER = int(
    os.getenv("VISION_CLUSTER_MIN_STARS_PER_CLUSTER", "3")
)

# VL 配置
ZHIPU_API_URL = os.getenv(
    "ZHIPU_API_URL",
    "https://api-inference.modelscope.cn/v1/chat/completions",
).strip()
ZHIPU_API_KEY = os.getenv(
    "MODELSCOPE_API_KEY",
    os.getenv("ZHIPU_API_KEY", ""),
).strip()
VL_MODEL = os.getenv(
    "VL_MODEL", "Qwen/Qwen3.8-Flash-Next"
).strip()

# 主星权重系数（亮度 + 距主星距离）
WEIGHT_BRIGHTNESS = float(os.getenv("VISION_WEIGHT_BRIGHTNESS", "0.65"))
WEIGHT_DISTANCE = float(os.getenv("VISION_WEIGHT_DISTANCE", "0.35"))
CONFIDENCE_THRESHOLD = float(os.getenv("VISION_CONFIDENCE_THRESHOLD", "0.51"))


# ==================== 88 星座对照表 ====================

_CONSTELLATION_PAIRS = [
    ("And", "Andromeda"), ("Ant", "Antlia"), ("Aps", "Apus"),
    ("Aqr", "Aquarius"), ("Aql", "Aquila"), ("Ara", "Ara"),
    ("Ari", "Aries"), ("Aur", "Auriga"), ("Boo", "Bootes"),
    ("Cae", "Caelum"), ("Cam", "Camelopardalis"), ("Cnc", "Cancer"),
    ("CMa", "Canis Major"), ("CMi", "Canis Minor"),
    ("Cap", "Capricornus"), ("Car", "Carina"), ("Cas", "Cassiopeia"),
    ("Cen", "Centaurus"), ("Cep", "Cepheus"), ("Cet", "Cetus"),
    ("Cha", "Chamaeleon"), ("Cir", "Circinus"), ("Col", "Columba"),
    ("Com", "Coma Berenices"), ("CrA", "Corona Australis"),
    ("CrB", "Corona Borealis"), ("Crv", "Corvus"), ("Crt", "Crater"),
    ("Cru", "Crux"), ("Cyg", "Cygnus"), ("Del", "Delphinus"),
    ("Dor", "Dorado"), ("Dra", "Draco"), ("Equ", "Equuleus"),
    ("Eri", "Eridanus"), ("For", "Fornax"), ("Gem", "Gemini"),
    ("Gru", "Grus"), ("Her", "Hercules"), ("Hor", "Horologium"),
    ("Hya", "Hydra"), ("Hyi", "Hydrus"), ("Ind", "Indus"),
    ("Lac", "Lacerta"), ("Leo", "Leo"), ("LMi", "Leo Minor"),
    ("Lep", "Lepus"), ("Lib", "Libra"), ("Lup", "Lupus"),
    ("Lyn", "Lynx"), ("Lyr", "Lyra"), ("Men", "Mensa"),
    ("Mic", "Microscopium"), ("Mon", "Monoceros"), ("Mus", "Musca"),
    ("Nor", "Norma"), ("Oct", "Octans"), ("Oph", "Ophiuchus"),
    ("Ori", "Orion"), ("Peg", "Pegasus"), ("Per", "Perseus"),
    ("Phe", "Phoenix"), ("Pic", "Pictor"), ("Psc", "Pisces"),
    ("PsA", "Piscis Austrinus"), ("Pup", "Puppis"), ("Pyx", "Pyxis"),
    ("Ret", "Reticulum"), ("Sge", "Sagitta"), ("Sgr", "Sagittarius"),
    ("Sco", "Scorpius"), ("Scl", "Sculptor"), ("Sct", "Scutum"),
    ("Ser", "Serpens"), ("Sex", "Sextans"), ("Tau", "Taurus"),
    ("Tel", "Telescopium"), ("Tri", "Triangulum"),
    ("TrA", "Triangulum Australe"), ("Tuc", "Tucana"),
    ("UMa", "Ursa Major"), ("UMi", "Ursa Minor"), ("Vel", "Vela"),
    ("Vir", "Virgo"), ("Vol", "Volans"), ("Vul", "Vulpecula"),
]
_ABBR_TO_FULL = {a: f for a, f in _CONSTELLATION_PAIRS}
_ABBR_LOWER_TO_ABBR = {a.lower(): a for a, _ in _CONSTELLATION_PAIRS}
_FULL_LOWER_TO_ABBR = {f.lower(): a for a, f in _CONSTELLATION_PAIRS}


def _norm_constellation(name: str) -> str:
    if not name:
        return ""
    n = re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()
    if not n:
        return ""
    compact = n.replace(" ", "")
    if compact in _ABBR_LOWER_TO_ABBR:
        return _ABBR_LOWER_TO_ABBR[compact]
    if n in _FULL_LOWER_TO_ABBR:
        return _FULL_LOWER_TO_ABBR[n]
    return ""


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


# ==================== 星点检测 ====================

def _detect_brightest_stars(
    image_bytes: bytes,
    max_dim: int = MAX_DIM,
    top_n: int = TOP_N,
    edge_margin: float = EDGE_MARGIN_RATIO,
) -> Dict[str, Any]:
    pil = Image.open(BytesIO(image_bytes)).convert("RGB")
    w0, h0 = pil.size
    if max(w0, h0) > max_dim:
        s = max_dim / float(max(w0, h0))
        pil = pil.resize(
            (max(1, int(w0 * s)), max(1, int(h0 * s))),
            Image.LANCZOS,
        )
    w, h = pil.size

    rgb = np.asarray(pil, dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gray_s = cv2.GaussianBlur(gray, (3, 3), 0.6)

    k = max(15, (min(h, w) // 15) | 1)
    if k % 2 == 0:
        k += 1
    bg = cv2.medianBlur(gray_s.astype(np.uint8), k).astype(np.float32)
    bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=max(1.0, k / 4.0))

    residual = np.clip(gray_s - bg, 0.0, None)

    edge_margin = max(0.0, min(0.45, float(edge_margin)))
    mx = int(round(w * edge_margin))
    my = int(round(h * edge_margin))
    mx = min(mx, max(0, w // 2 - 10))
    my = min(my, max(0, h // 2 - 10))

    inner_mask = np.zeros((h, w), dtype=bool)
    if mx or my:
        inner_mask[my:h - my, mx:w - mx] = True
    else:
        inner_mask[:] = True

    inner = residual[inner_mask] if inner_mask.any() else residual.ravel()

    med = float(np.median(inner))
    mad = float(np.median(np.abs(inner - med)))
    sigma = 1.4826 * mad
    if sigma < 1e-3:
        sigma = float(inner.std())
    if sigma < 1e-3:
        sigma = 1.0

    thresh = max(med + DETECT_SIGMA * sigma, 6.0)
    mask = (residual > thresh).astype(np.uint8)
    mask[~inner_mask] = 0

    roi = {"x0": mx, "y0": my, "x1": w - mx, "y1": h - my}

    if int(mask.sum()) == 0:
        return {
            "stars": [], "pil": pil, "size": (w, h),
            "threshold": float(thresh), "candidate_count": 0,
            "edge_margin": edge_margin, "roi": roi,
        }

    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    max_area = max(20, int((min(h, w) * 0.02) ** 2))

    candidates: List[Dict[str, Any]] = []
    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 1 or area > max_area:
            continue
        ys, xs = np.where(labels == i)
        vals = residual[ys, xs]
        candidates.append({
            "cx": float(xs.mean()), "cy": float(ys.mean()),
            "flux": float(vals.sum()), "peak": float(vals.max()),
            "area": area,
        })

    candidates.sort(key=lambda c: -c["flux"])
    min_dist = max(5.0, min(h, w) * 0.008)
    min_dist2 = min_dist * min_dist

    accepted: List[Dict[str, Any]] = []
    for c in candidates:
        too_close = any(
            (c["cx"] - a["cx"]) ** 2 + (c["cy"] - a["cy"]) ** 2 < min_dist2
            for a in accepted
        )
        if not too_close:
            accepted.append(c)
        if len(accepted) >= top_n:
            break

    stars = []
    for idx, c in enumerate(accepted):
        stars.append({
            "rank": idx + 1,
            "x": round(c["cx"] / w, 5), "y": round(c["cy"] / h, 5),
            "px": round(c["cx"], 2), "py": round(c["cy"], 2),
            "brightness": round(c["flux"], 3),
            "peak": round(c["peak"], 3), "area": c["area"],
            "cluster": -1,
        })

    return {
        "stars": stars, "pil": pil, "size": (w, h),
        "threshold": float(thresh), "candidate_count": len(candidates),
        "edge_margin": edge_margin, "roi": roi,
    }


# ==================== K-means 聚类 ====================

_CLUSTER_PALETTE = [
    (255, 0, 0),      # 红
    (255, 140, 0),    # 橙
    (255, 0, 180),    # 品红
    (180, 0, 255),    # 紫
    (255, 200, 0),    # 金
    (0, 200, 255),    # 天蓝
    (0, 220, 100),    # 绿
    (255, 100, 100),  # 珊瑚
]


def _kmeans(X: np.ndarray, k: int, n_iter: int = 100, seed: int = 42):
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    centers = [X[int(rng.integers(n))]]
    for _ in range(k - 1):
        d2 = np.min([np.sum((X - c) ** 2, axis=1) for c in centers], axis=0)
        total = float(d2.sum())
        if total <= 0:
            centers.append(X[int(rng.integers(n))])
        else:
            centers.append(X[int(rng.choice(n, p=d2 / total))])
    centers = np.asarray(centers, dtype=float)

    labels = np.full(n, -1, dtype=int)
    for _ in range(n_iter):
        d = np.linalg.norm(X[:, None, :] - centers[None, :, :], axis=2)
        new_labels = np.argmin(d, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for i in range(k):
            m = labels == i
            if m.any():
                centers[i] = X[m].mean(axis=0)
    return labels, centers


def _silhouette_score(X: np.ndarray, labels: np.ndarray) -> float:
    n = X.shape[0]
    uniq = np.unique(labels)
    if len(uniq) < 2 or n < 4:
        return -1.0
    d = np.linalg.norm(X[:, None, :] - X[None, :, :], axis=2)
    sils = np.zeros(n, dtype=float)
    for i in range(n):
        same = labels == labels[i]
        same[i] = False
        if not same.any():
            continue
        a = float(d[i, same].mean())
        b = min(
            float(d[i, labels == c].mean())
            for c in uniq if c != labels[i] and (labels == c).any()
        )
        denom = max(a, b)
        sils[i] = (b - a) / denom if denom > 0 else 0.0
    return float(sils.mean())


def _build_cluster_payload(
    stars: List[Dict[str, Any]],
    labels: np.ndarray,
    k: int,
) -> Optional[List[Dict[str, Any]]]:
    clusters = []
    for cid in range(k):
        idx = np.where(labels == cid)[0]
        if len(idx) == 0:
            return None
        idx_list = [int(i) for i in idx]
        members = [stars[i] for i in idx_list]

        main = max(members, key=lambda s: s["brightness"])
        max_b = max(m["brightness"] for m in members) or 1.0
        dists = [
            float(np.hypot(m["px"] - main["px"], m["py"] - main["py"]))
            for m in members
        ]
        max_d = max(dists) if dists else 1.0
        if max_d < 1e-6:
            max_d = 1.0

        enriched = []
        for m, d in zip(members, dists):
            b_norm = m["brightness"] / max_b
            d_norm = 1.0 - d / max_d
            weight = WEIGHT_BRIGHTNESS * b_norm + WEIGHT_DISTANCE * d_norm
            enriched.append({
                **m,
                "cluster": cid,
                "dist_to_main": round(d, 2),
                "weight": round(float(weight), 4),
            })
        enriched.sort(key=lambda x: -x["weight"])

        edge_n = max(2, len(members) // 3)
        edge_members = sorted(
            enriched, key=lambda s: -s["dist_to_main"]
        )[:edge_n]

        xs = [m["px"] for m in members]
        ys = [m["py"] for m in members]
        bs = [m["brightness"] for m in members]

        clusters.append({
            "id": cid,
            "star_count": len(members),
            "center_x": round(float(np.mean(xs)), 2),
            "center_y": round(float(np.mean(ys)), 2),
            "bbox": {
                "x0": round(float(min(xs)), 2), "y0": round(float(min(ys)), 2),
                "x1": round(float(max(xs)), 2), "y1": round(float(max(ys)), 2),
            },
            "avg_brightness": round(float(np.mean(bs)), 3),
            "main_star": {
                "px": main["px"], "py": main["py"],
                "x": main["x"], "y": main["y"],
                "brightness": main["brightness"],
            },
            "stars": enriched,
            "edge_stars": [
                {"px": e["px"], "py": e["py"],
                 "brightness": e["brightness"],
                 "dist_to_main": e["dist_to_main"]}
                for e in edge_members
            ],
            "neighbors": [],
        })

    for c in clusters:
        cx, cy = c["center_x"], c["center_y"]
        nbrs = []
        for o in clusters:
            if o["id"] == c["id"]:
                continue
            d = float(np.hypot(o["center_x"] - cx, o["center_y"] - cy))
            nbrs.append({
                "cluster_id": o["id"],
                "center_x": o["center_x"],
                "center_y": o["center_y"],
                "star_count": o["star_count"],
                "distance": round(d, 2),
            })
        nbrs.sort(key=lambda x: x["distance"])
        c["neighbors"] = nbrs

    # clusters.sort(key=lambda c: -c["star_count"])
    # for new_id, c in enumerate(clusters):
    #     c["id"] = new_id
    #     for m in c["stars"]:
    #         m["cluster"] = new_id
    return clusters


def _cluster_stars_all(
    stars: List[Dict[str, Any]],
    forced_k: Optional[int] = None,
    min_stars_per_cluster: int = CLUSTER_MIN_STARS_PER_CLUSTER,
) -> List[Dict[str, Any]]:
    n = len(stars)
    if n == 0:
        return []

    X = np.asarray([[s["px"], s["py"]] for s in stars], dtype=float)

    if forced_k is not None:
        k_list = [int(forced_k)] if int(forced_k) in CLUSTER_K_LIST else []
    else:
        k_list = CLUSTER_K_LIST

    results: List[Dict[str, Any]] = []
    for k in k_list:
        if k < 2 or n < k * min_stars_per_cluster:
            continue
        labels, _ = _kmeans(X, k)
        if len(np.unique(labels)) < k:
            continue
        counts = np.bincount(labels, minlength=k)
        if int(np.min(counts)) < min_stars_per_cluster:
            continue

        clusters = _build_cluster_payload(stars, labels, k)
        if clusters is None:
            continue

        score = _silhouette_score(X, labels)

        star_dicts = []
        for i, s in enumerate(stars):
            ss = dict(s)
            ss["cluster"] = int(labels[i])
            star_dicts.append(ss)

        results.append({
            "k": int(k),
            "score": round(float(score), 4),
            "clusters": clusters,
            "stars": star_dicts,
        })

    results.sort(key=lambda r: r["k"])
    return results


# ==================== 图片预处理（给 VL 用） ====================

def _prepare_versions(pil: Image.Image) -> List[Dict[str, str]]:
    rgb = np.asarray(pil.convert("RGB"), dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)

    p_low, p_high = np.percentile(gray, [0.5, 99.5])
    if p_high - p_low < 1.0:
        p_high = p_low + 1.0
    stretch = np.clip((gray - p_low) / (p_high - p_low), 0.0, 1.0)
    bright_arr = (np.power(stretch, 0.5) * 255.0).astype(np.uint8)
    bright = Image.fromarray(cv2.cvtColor(bright_arr, cv2.COLOR_GRAY2RGB))

    inverted = Image.fromarray(
        cv2.cvtColor(255 - bright_arr, cv2.COLOR_GRAY2RGB)
    )

    def _b64(im: Image.Image) -> str:
        buf = BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    return [
        {"b64": _b64(pil.convert("RGB")), "mime": "image/png", "label": "原图"},
        {"b64": _b64(bright), "mime": "image/png", "label": "提亮图"},
        {"b64": _b64(inverted), "mime": "image/png", "label": "反相图"},
    ]


# ==================== 字体缓存 ====================

_FONT_CACHE: Dict[int, Any] = {}


def _load_font(size: int):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    font = None
    for name in ("arial.ttf", "DejaVuSans-Bold.ttf", "msyh.ttc",
                 "simhei.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, size)
            break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
    _FONT_CACHE[size] = font
    return font


# ==================== 整图标注（给 VL 用） ====================

def _annotate_cluster_for_vl(
    pil: Image.Image,
    cluster: Dict[str, Any],
    all_clusters: List[Dict[str, Any]],
) -> str:
    """
    整图标注：所有簇用不同颜色，主星画大圈 + 白心 + 簇编号。
    参数 cluster 保留仅为兼容签名，实际不使用。
    """
    img = pil.convert("RGB").copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    r_base = max(4.0, min(w, h) * 0.007)
    font = _load_font(max(16, int(min(w, h) * 0.022)))

    for c in all_clusters:
        cid = c["id"]
        color = _CLUSTER_PALETTE[cid % len(_CLUSTER_PALETTE)]
        main = c["main_star"]

        # 成员星（实心圆）
        for s in c["stars"]:
            px, py = float(s["px"]), float(s["py"])
            r = r_base * 0.75
            draw.ellipse(
                [px - r, py - r, px + r, py + r],
                fill=(color[0], color[1], color[2], 255),
                outline=(
                    max(0, color[0] - 80),
                    max(0, color[1] - 80),
                    max(0, color[2] - 80),
                    255,
                ),
                width=1,
            )

        # 主星：大圈 + 白心
        mx, my = float(main["px"]), float(main["py"])
        R = r_base * 2.2
        draw.ellipse(
            [mx - R, my - R, mx + R, my + R],
            outline=(color[0], color[1], color[2], 255),
            width=max(2, int(r_base * 0.8)),
        )
        draw.ellipse(
            [mx - r_base * 0.6, my - r_base * 0.6,
             mx + r_base * 0.6, my + r_base * 0.6],
            fill=(255, 255, 255, 255),
        )

        # 簇编号
        try:
            label = f"C{cid}"
            l, t, rr, b = draw.textbbox((0, 0), label, font=font)
            tw, th = rr - l, b - t
            tx = mx + R + 4
            ty = my - th / 2
            if tx + tw + 6 > w:
                tx = mx - R - tw - 10
            if tx < 2:
                tx = 2
            if ty < 2:
                ty = 2
            if ty + th + 4 > h:
                ty = h - th - 4
            draw.rectangle(
                [tx - 3, ty - 2, tx + tw + 3, ty + th + 2],
                fill=(0, 0, 0, 195),
            )
            draw.text((tx, ty), label, font=font,
                      fill=(color[0], color[1], color[2], 255))
        except Exception:
            pass

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ==================== VL Prompt & 调用 ====================

FULL_IMAGE_VL_PROMPT = """你是一名天文识星专家。这是同一张星空照片的 3 个版本（原图 / 提亮图 / 反相图）。

照片中已经用【{k} 种不同颜色】的圆点标出了 {k} 个星群（cluster），每个星群可能对应一个星座。
每簇的**主星**用【大圆圈 + 中心白点】标出，旁边有小标签 C0~C{k_minus_1}。

【颜色 → 簇 对照表】
{cluster_table}

【所有簇的量化信息】
{cluster_details}

【任务】
对**每一个簇**，判断它最可能对应的星座（88 星座之一）。每个簇独立判断。

【判断要点】
1. 每簇的**主星**（大圆圈白心）权重最高，是形状锚点
2. 越亮、离主星越近的成员星越可信
3. 边缘星可能属于邻近簇，不要强行纳入当前星座形状
4. 参考邻近簇的颜色和位置，相邻簇的星也有微小可能属于当前簇，但优先考虑主星和簇内成员
5. 注意图像上的颜色和 C 编号，严格对齐 JSON 里的 id，不要错位

【最终裁决规则（务必严格遵守）】
1. **取置信度最高的星座**作为该簇的最终判定结果，填入 `constellation` / `constellation_abbr`。
   每簇只能给一个最终答案，不要模糊两可。
2. **必须结合现实世界中星座在天球上的相邻关系**做交叉校验与最终裁决：
   - 相邻簇判出的星座在天球上必须**相邻、相接或属于同一片天区**；
   - 若两个相邻簇分别判出天球上完全不相邻的星座（例如一簇 Orion、相邻簇却判 Cygnus），
     必须重新评估，调整其中**置信度较低**的那一簇，使整体自洽；
   - 若多个簇落在同一片连续天区（如夏季大三角、天蝎-人马区域），
     则整体判定的 sky_region / summary 必须与这些相邻星座一致。
   - 常见相邻星座参考：
     * Cygnus ↔ Lyra / Aquila / Vulpecula / Cepheus / Draco / Pegasus / Lacerta
     * Lyra ↔ Cygnus / Hercules / Draco / Vulpecula
     * Aquila ↔ Cygnus / Lyra / Sagitta / Delphinus / Sagittarius / Scutum / Ophiuchus / Hercules / Aquarius
     * Sagittarius ↔ Scorpius / Ophiuchus / Aquila / Scutum / Corona Australis / Telescopium / Capricornus / Indus
     * Scorpius ↔ Sagittarius / Ophiuchus / Libra / Corona Australis / Lupus / Norma / Ara
     * Cassiopeia ↔ Cepheus / Camelopardalis / Perseus / Andromeda / Lacerta
     * Orion ↔ Taurus / Gemini / Monoceros / Lepus / Eridanus
     * Taurus ↔ Orion / Gemini / Auriga / Perseus / Aries / Cetus / Eridanus
     * Ursa Major ↔ Ursa Minor / Draco / Bootes / Canes Venatici / Leo / Leo Minor / Lynx / Camelopardalis
     * Ursa Minor ↔ Ursa Major / Draco / Cepheus / Camelopardalis
     * Crux ↔ Centaurus / Musca / Carina
3. `confidence` 为最终置信度（0~1）。若最佳星座的 confidence < 0.3，
   视为低置信，应在 `reason` / `edge_note` 里说明不确定点。
4. `alternative` 按置信度降序给出前 1~3 个候选，每个候选说明其判断依据。
5. 所有簇的最终判定必须构成一片**天球上物理自洽的连续区域**；
   若不满足，请回到第 2 条重新调整最低置信度的簇。


【输出格式】只输出 JSON，不要 markdown，不要解释：
{{
  "clusters": [
    {{
      "id": 0,
      "constellation": "Orion",
      "constellation_abbr": "Ori",
      "confidence": 0.82,
      "reason": "主星为参宿四（Betelgeuse），三星腰带（参宿一/二/三）清晰可见，四角亮星构成猎户主体；与相邻 Taurus / Gemini 簇在天球上自洽",
      "alternative": [
        {{"name": "Taurus", "confidence": 0.28, "reason": "若主星实为毕宿五则可能是金牛座，但缺少 V 形毕星团结构"}}
      ],
      "shape_description": "四边形主体 + 中央三星腰带 + 下方剑状星云",
      "edge_note": "右下角一颗边缘星可能是大犬座天狼星（Sirius）"
    }},
    {{
      "id": 1,
      "constellation": "Taurus",
      "constellation_abbr": "Tau",
      "confidence": 0.71,
      "reason": "主星为毕宿五（Aldebaran），呈 V 形毕星团结构，附近可见昴星团；与相邻 Orion / Auriga 簇在天球上相邻",
      "alternative": [
        {{"name": "Auriga", "confidence": 0.25, "reason": "V 形也可联想五车二附近，但缺少御夫五边形"}}
      ],
      "shape_description": "V 形毕星团 + 牛角尖指向西北",
      "edge_note": "西北侧一串密集小星可能是昴星团（M45），仍属金牛座"
    }},
    {{
      "id": 2,
      "constellation": "Canis Major",
      "constellation_abbr": "CMa",
      "confidence": 0.68,
      "reason": "主星为天狼星（Sirius），全图最亮，附近有弧矢一等亮星群；与相邻 Orion 簇在天球上自洽",
      "alternative": [
        {{"name": "Canis Minor", "confidence": 0.22, "reason": "若主星为南河三则可能是小犬座，但缺少单独亮星对"}}
      ],
      "shape_description": "天狼星领衔的散开星群，无明显几何轮廓",
      "edge_note": "北侧边缘星可能是小犬座南河三（Procyon）"
    }},
    {{
      "id": 3,
      "constellation": "Auriga",
      "constellation_abbr": "Aur",
      "confidence": 0.60,
      "reason": "主星为五车二（Capella），五颗亮星构成近似五边形；与相邻 Taurus / Gemini 簇在天球上相邻",
      "alternative": [
        {{"name": "Perseus", "confidence": 0.20, "reason": "若星群呈长条弧线则可能是英仙座，但缺少长链结构"}}
      ],
      "shape_description": "五边形轮廓，顶点为五车二",
      "edge_note": "东南角一颗星可能是金牛座 β（Elnath），历史上曾共享御夫/金牛边界"
    }},
    {{
      "id": 4,
      "constellation": "Gemini",
      "constellation_abbr": "Gem",
      "confidence": 0.55,
      "reason": "主星为北河三（Pollux），附近北河二（Castor）构成双子头部一对亮星；与相邻 Orion / Auriga 簇在天球上相邻",
      "alternative": [
        {{"name": "Cancer", "confidence": 0.15, "reason": "若星群较暗且呈散开状则可能是巨蟹座，但缺少鬼星团"}}
      ],
      "shape_description": "两条平行亮星链由头部向下延伸",
      "edge_note": "南端一颗暗星可能是巨蟹座边界星，注意不要误纳"
    }},
    {{
      "id": 5,
      "constellation": "Canis Minor",
      "constellation_abbr": "CMi",
      "confidence": 0.48,
      "reason": "主星为南河三（Procyon），仅两颗亮星构成简短线；与相邻 Orion / Canis Major 簇在天球上自洽",
      "alternative": [
        {{"name": "Monoceros", "confidence": 0.18, "reason": "该天区暗星多属麒麟座，但缺少可辨形状"}}
      ],
      "shape_description": "两颗亮星组成极简短连线",
      "edge_note": "西南侧弱星密集区多为麒麟座，不必强行归入本簇"
    }}
  ],
  "summary": "整张照片覆盖猎户座经金牛座至大犬座、御夫座至双子座一带的冬季天区",
  "sky_region": "冬季大三角 / 冬季六边形区域（Orion–Taurus–Auriga–Gemini–Canis Major–Canis Minor）"
}}
"""

RECHECK_VL_PROMPT = """你是一名天文识星专家。这是同一张星空照片的 3 个版本（原图 / 提亮图 / 反相图）。

照片中已经用【{k} 种不同颜色】的圆点标出了 {k} 个星群（cluster），每簇的**主星**用【大圆圈 + 中心白点】标出，旁边有小标签 C0~C{k_minus_1}。

【颜色 → 簇 对照表】
{cluster_table}

【已高置信度确认的星座（锚点，不可更改；新判定必须与它们在天球上相邻/相接）】
{confirmed_clusters}

【需要重新判断的低置信度簇（置信度 < {threshold}）】
{low_conf_clusters}

【任务】
只对上面列出的**低置信度簇**重新判定星座。**必须以所有高置信度簇的星座位置作为锚点**：
1. 新判定的星座必须与相邻的高置信度锚点在**天球上物理相邻、相接或属于同一片天区**；
2. 若低置信度簇与某个高置信度锚点判出的星座在天球上完全不相邻（例如锚点是 Orion，低置信簇却判 Cygnus），
   必须改成与锚点相邻的星座（例如 Orion ↔ Taurus / Gemini / Monoceros / Lepus / Eridanus）；
3. 若多个低置信度簇与高置信度锚点构成一片连续天区（夏季大三角、天蝎-人马区域等），
   整体 sky_region / summary 必须与这些星座一致；
4. **只输出需要修改的簇**（即上面列出的低置信度簇）；已经被高置信度确认的簇不要再返回。

【判断要点】
1. 每簇主星（大圆圈白心）权重最高，是形状锚点
2. 越亮、离主星越近的成员星越可信
3. 边缘星可能属于邻近簇，不要强行纳入当前星座形状
4. 注意图像上的颜色和 C 编号，严格对齐 JSON 里的 id
5. 优先选择与已确认锚点星座相邻的星座

【最终裁决规则】
1. 每簇只给一个最终答案（constellation / constellation_abbr），不要模糊两可
2. confidence 为最终置信度（0~1），必须 ≥ 0.5（若仍 < 0.5，请在 reason 里说明不确定点）
3. alternative 按置信度降序给出前 1~3 个候选

【输出格式】只输出 JSON，不要 markdown，不要解释：
{{
  "clusters": [
    {{
      "id": 2,
      "constellation": "Taurus",
      "constellation_abbr": "Tau",
      "confidence": 0.72,
      "reason": "以已确认的 Orion 为锚点，本簇在图像上位于 Orion 西北侧，V 形毕星团结构清晰，与 Orion / Auriga 在天球上相邻",
      "alternative": [
        {{"name": "Auriga", "confidence": 0.25, "reason": "V 形也可联想五车二附近，但缺少御夫五边形"}}
      ],
      "shape_description": "V 形毕星团 + 牛角尖指向西北",
      "edge_note": "西北侧一串密集小星可能是昴星团（M45），仍属金牛座"
    }}
  ],
  "summary": "整张照片覆盖猎户座经金牛座至御夫座一带的冬季天区",
  "sky_region": "冬季大三角 / 冬季六边形区域"
}}
"""

def _parse_vl_item(item: Dict[str, Any]):
    """把 VL 返回的单条 cluster 解析成 (id, parsed_dict)，解析失败返回 None。"""
    if not isinstance(item, dict):
        return None
    try:
        cid = int(item.get("id", -1))
    except (TypeError, ValueError):
        return None
    if cid < 0:
        return None

    abbr = _norm_constellation(
        item.get("constellation_abbr") or item.get("constellation") or ""
    )
    full = _ABBR_TO_FULL.get(abbr, abbr) if abbr else ""
    try:
        conf = round(max(0.0, min(1.0, float(item.get("confidence", 0.0)))), 3)
    except (TypeError, ValueError):
        conf = 0.0

    alts = item.get("alternative")
    clean_alts = []
    if isinstance(alts, list):
        for a in alts[:4]:
            if not isinstance(a, dict):
                continue
            a_abbr = _norm_constellation(a.get("name") or "")
            try:
                a_conf = float(a.get("confidence", 0.0))
            except (TypeError, ValueError):
                a_conf = 0.0
            clean_alts.append({
                "name": _ABBR_TO_FULL.get(a_abbr, a_abbr) or str(a.get("name") or ""),
                "abbr": a_abbr,
                "confidence": round(max(0.0, min(1.0, a_conf)), 3),
                "reason": str(a.get("reason") or "").strip(),
            })

    return cid, {
        "success": True,
        "constellation": full or str(item.get("constellation") or ""),
        "constellation_abbr": abbr,
        "constellation_full": full,
        "confidence": conf,
        "reason": str(item.get("reason") or "").strip(),
        "alternative": clean_alts,
        "shape_description": str(item.get("shape_description") or "").strip(),
        "edge_note": str(item.get("edge_note") or "").strip(),
    }

def _strip_fence(text: str) -> str:
    t = str(text).strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if len(lines) > 1 and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


async def _call_vl_for_cluster(
    images: List[Dict[str, str]],
    cluster_prompt: str,
    max_retries: int = 4,
) -> Dict[str, Any]:
    """整图调用；支持 429 指数退避重试。"""
    if not ZHIPU_API_KEY:
        return {"success": False, "error": "未配置 MODELSCOPE_API_KEY / ZHIPU_API_KEY"}

    content = [{"type": "text", "text": cluster_prompt}]
    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"},
        })

    payload = {
        "model": VL_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 3000,
        "temperature": 0.1,
        "top_p": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }

    delay = 2.0
    last_err = ""

    for attempt in range(max_retries):
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                resp = await client.post(ZHIPU_API_URL, json=payload, headers=headers)

                if resp.status_code == 429:
                    last_err = f"429 限流: {resp.text[:200]}"
                    print(f"   ⏳ 429 限流，{delay:.1f}s 后重试 ({attempt+1}/{max_retries})")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue

                if resp.status_code == 400:
                    try:
                        body = resp.json()
                        msg = (body.get("error") or {}).get("message", resp.text[:200])
                    except Exception:
                        msg = resp.text[:200]
                    return {"success": False, "error": f"400: {msg}"}

                if resp.status_code in (500, 502, 503, 504):
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    print(f"   ⏳ 服务端错误，{delay:.1f}s 后重试 ({attempt+1}/{max_retries})")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue

                resp.raise_for_status()

                txt = (resp.text or "").strip()

                if not txt:
                    last_err = f"HTTP {resp.status_code} 返回空内容"
                    print(f"   ⏳ 空响应，{delay:.1f}s 后重试 ({attempt+1}/{max_retries})")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue

                try:
                    data = json.loads(txt)
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "error": f"API 返回非 JSON(HTTP {resp.status_code}): {txt[:300]}"
                    }

                if "error" in data:
                    err = data["error"]
                    if isinstance(err, dict):
                        err = err.get("message", str(err))
                    return {"success": False, "error": f"API 报错: {err}"}

                choices = data.get("choices")
                if not choices:
                    return {"success": False, "error": f"返回异常: {str(data)[:200]}"}

                msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                if not msg:
                    return {"success": False, "error": f"返回异常: {str(data)[:200]}"}

                raw = msg.get("content", "")
                if isinstance(raw, list):
                    raw = " ".join(
                        p.get("text", "") for p in raw
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                raw = _strip_fence(str(raw))

                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    return {"success": False, "error": f"非 JSON: {raw[:300]}"}

                if not isinstance(parsed, dict):
                    return {"success": False, "error": "返回非对象"}

                return {"success": True, "data": parsed}

            except httpx.HTTPStatusError as e:
                body = e.response.text[:300] if e.response is not None else ""
                return {"success": False, "error": f"HTTP {e.response.status_code}: {body}"}
            except httpx.TimeoutException:
                last_err = "VL 调用超时"
                print(f"   ⏳ 超时，{delay:.1f}s 后重试 ({attempt+1}/{max_retries})")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            except Exception as e:
                import traceback
                traceback.print_exc()
                return {"success": False, "error": f"调用失败: {e}"}

    return {"success": False, "error": f"重试 {max_retries} 次仍失败: {last_err}"}


def _build_cluster_prompt(
    cluster: Dict[str, Any],
    all_clusters: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    整图 prompt：把全部簇的信息拼成一份。
    参数 cluster 保留兼容签名；实际使用 all_clusters（若提供）。
    """
    clusters = all_clusters if all_clusters else [cluster]
    k = len(clusters)

    color_rows = []
    for c in clusters:
        rgb = _CLUSTER_PALETTE[c["id"] % len(_CLUSTER_PALETTE)]
        color_rows.append(
            f"  - C{c['id']}：RGB{rgb}（成员 {c['star_count']} 颗）"
        )
    cluster_table = "\n".join(color_rows)

    details = []
    for c in clusters:
        rgb = _CLUSTER_PALETTE[c["id"] % len(_CLUSTER_PALETTE)]
        main = c["main_star"]
        members = c["stars"][:8]

        member_lines = "\n".join(
            f"      {i+1}. ({m['px']:.0f},{m['py']:.0f}) "
            f"亮度={m['brightness']:.1f} 权重={m['weight']:.3f} "
            f"距主星={m['dist_to_main']:.1f}"
            for i, m in enumerate(members)
        ) or "      （无）"

        edge_lines = "\n".join(
            f"      ({e['px']:.0f},{e['py']:.0f}) 亮度={e['brightness']:.1f}"
            for e in c.get("edge_stars", [])
        ) or "      （无）"

        neighbor_lines = ", ".join(
            f"C{n['cluster_id']}({n['distance']:.0f}px)"
            for n in c.get("neighbors", [])[:3]
        ) or "（无）"

        details.append(f"""
  ── C{c['id']}（颜色 RGB{rgb}）──
    成员数：{c['star_count']}
    主星：像素({main['px']:.0f},{main['py']:.0f}) 亮度={main['brightness']:.1f}
    平均亮度：{c['avg_brightness']}
    bbox：x[{c['bbox']['x0']:.0f},{c['bbox']['x1']:.0f}] y[{c['bbox']['y0']:.0f},{c['bbox']['y1']:.0f}]
    成员星（按权重降序）：
{member_lines}
    边缘星：
{edge_lines}
    邻近簇：{neighbor_lines}
""")

    cluster_details = "\n".join(details)

    return FULL_IMAGE_VL_PROMPT.format(
        k=k,
        k_minus_1=k - 1,
        cluster_table=cluster_table,
        cluster_details=cluster_details,
    )

def _build_recheck_prompt(
    all_clusters: List[Dict[str, Any]],
    confirmed: List[tuple],
    low_conf: List[Dict[str, Any]],
    threshold: float = CONFIDENCE_THRESHOLD,
) -> str:
    """构造重新判断 prompt：只对低置信度簇重新判定，锚定高置信度簇。"""
    k = len(all_clusters)

    color_rows = []
    for c in all_clusters:
        rgb = _CLUSTER_PALETTE[c["id"] % len(_CLUSTER_PALETTE)]
        color_rows.append(
            f"  - C{c['id']}：RGB{rgb}（成员 {c['star_count']} 颗）"
        )
    cluster_table = "\n".join(color_rows)

    # ---- 已确认锚点 ----
    confirmed_rows = []
    for c, vr in confirmed:
        rgb = _CLUSTER_PALETTE[c["id"] % len(_CLUSTER_PALETTE)]
        main = c["main_star"]
        name = (vr.get("constellation_full")
                or vr.get("constellation")
                or vr.get("constellation_abbr") or "")
        abbr = vr.get("constellation_abbr") or ""
        try:
            conf = float(vr.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        confirmed_rows.append(
            f"  - C{c['id']}（RGB{rgb}）→ {name} ({abbr})，置信度 {conf:.2f}\n"
            f"      主星像素：({main['px']:.0f},{main['py']:.0f})"
        )
    confirmed_text = "\n".join(confirmed_rows) or "（无）"

    # ---- 低置信度簇详细信息 ----
    low_details = []
    for c in low_conf:
        rgb = _CLUSTER_PALETTE[c["id"] % len(_CLUSTER_PALETTE)]
        main = c["main_star"]
        vr = c.get("vl_result") or {}

        if vr.get("success"):
            prev_name = (vr.get("constellation_full")
                         or vr.get("constellation")
                         or vr.get("constellation_abbr") or "")
            try:
                prev_conf = float(vr.get("confidence") or 0.0)
            except (TypeError, ValueError):
                prev_conf = 0.0
        else:
            prev_name = "（初次未判定）"
            prev_conf = 0.0

        members = c["stars"][:8]
        member_lines = "\n".join(
            f"      {i+1}. ({m['px']:.0f},{m['py']:.0f}) "
            f"亮度={m['brightness']:.1f} 权重={m['weight']:.3f} "
            f"距主星={m['dist_to_main']:.1f}"
            for i, m in enumerate(members)
        ) or "      （无）"

        edge_lines = "\n".join(
            f"      ({e['px']:.0f},{e['py']:.0f}) 亮度={e['brightness']:.1f}"
            for e in c.get("edge_stars", [])
        ) or "      （无）"

        neighbor_lines = ", ".join(
            f"C{n['cluster_id']}({n['distance']:.0f}px)"
            for n in c.get("neighbors", [])[:3]
        ) or "（无）"

        low_details.append(f"""
  ── C{c['id']}（颜色 RGB{rgb}）──
    初次判定：{prev_name}（置信度 {prev_conf:.2f}，低于阈值 {threshold}）
    成员数：{c['star_count']}
    主星：像素({main['px']:.0f},{main['py']:.0f}) 亮度={main['brightness']:.1f}
    平均亮度：{c['avg_brightness']}
    bbox：x[{c['bbox']['x0']:.0f},{c['bbox']['x1']:.0f}] y[{c['bbox']['y0']:.0f},{c['bbox']['y1']:.0f}]
    成员星（按权重降序）：
{member_lines}
    边缘星：
{edge_lines}
    邻近簇：{neighbor_lines}
""")
    low_text = "\n".join(low_details)

    return RECHECK_VL_PROMPT.format(
        k=k,
        k_minus_1=k - 1,
        cluster_table=cluster_table,
        threshold=threshold,
        confirmed_clusters=confirmed_text,
        low_conf_clusters=low_text,
    )
    
async def _identify_clusters_vl(
    pil: Image.Image,
    clusters: List[Dict[str, Any]],
    base_versions: List[Dict[str, str]],
) -> Dict[str, Any]:
    """整图一次调用，返回 {"success": bool, "by_id": {...}, "summary": ..., "raw": ...}"""
    if not ZHIPU_API_KEY:
        for c in clusters:
            c["vl_result"] = {"success": False, "error": "未配置 VL API Key"}
        return {"success": False, "error": "未配置 VL API Key"}

    # 整图标注（所有簇一起）
    annotated = _annotate_cluster_for_vl(pil, clusters[0], clusters)
    images = list(base_versions) + [
        {"b64": annotated, "mime": "image/png", "label": "聚类标注图"},
    ]
    prompt = _build_cluster_prompt(clusters[0], clusters)

    print(f"🤖 VL 整图调用：{len(clusters)} 个簇，{len(images)} 张图 ...")
    res = await _call_vl_for_cluster(images, prompt)

    if not res.get("success"):
        for c in clusters:
            c["vl_result"] = {"success": False,
                              "error": res.get("error", "整图调用失败")}
        return res

    data = res["data"]
    parsed_clusters = data.get("clusters") if isinstance(data, dict) else None
    if not isinstance(parsed_clusters, list):
        for c in clusters:
            c["vl_result"] = {"success": False, "error": "返回缺少 clusters 字段"}
        return {"success": False, "error": "返回缺少 clusters 字段"}

    by_id: Dict[int, Dict[str, Any]] = {}
    for item in parsed_clusters:
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("id", -1))
        except (TypeError, ValueError):
            continue

        abbr = _norm_constellation(
            item.get("constellation_abbr") or item.get("constellation") or ""
        )
        full = _ABBR_TO_FULL.get(abbr, abbr) if abbr else ""
        try:
            conf = round(max(0.0, min(1.0, float(item.get("confidence", 0.0)))), 3)
        except (TypeError, ValueError):
            conf = 0.0

        alts = item.get("alternative")
        clean_alts = []
        if isinstance(alts, list):
            for a in alts[:4]:
                if not isinstance(a, dict):
                    continue
                a_abbr = _norm_constellation(a.get("name") or "")
                try:
                    a_conf = float(a.get("confidence", 0.0))
                except (TypeError, ValueError):
                    a_conf = 0.0
                clean_alts.append({
                    "name": _ABBR_TO_FULL.get(a_abbr, a_abbr) or str(a.get("name") or ""),
                    "abbr": a_abbr,
                    "confidence": round(max(0.0, min(1.0, a_conf)), 3),
                    "reason": str(a.get("reason") or "").strip(),
                })

        by_id[cid] = {
            "success": True,
            "constellation": full or str(item.get("constellation") or ""),
            "constellation_abbr": abbr,
            "constellation_full": full,
            "confidence": conf,
            "reason": str(item.get("reason") or "").strip(),
            "alternative": clean_alts,
            "shape_description": str(item.get("shape_description") or "").strip(),
            "edge_note": str(item.get("edge_note") or "").strip(),
        }

    for c in clusters:
        c["vl_result"] = by_id.get(c["id"], {
            "success": False,
            "error": "VL 未返回该簇的判断",
        })

    return {
        "success": True,
        "by_id": by_id,
        "summary": str(data.get("summary") or "").strip(),
        "sky_region": str(data.get("sky_region") or "").strip(),
        "raw": data,
    }

async def _recheck_low_confidence_clusters(
    pil: Image.Image,
    clusters: List[Dict[str, Any]],
    base_versions: List[Dict[str, str]],
    threshold: float = CONFIDENCE_THRESHOLD,
) -> Dict[str, Any]:
    """
    对置信度 < threshold 的簇重新调用 VL，以高置信度簇为锚点。
    返回只包含需要修改的簇 id 与其新旧值。
    """
    if not ZHIPU_API_KEY:
        return {"success": False, "error": "未配置 VL API Key"}

    confirmed: List[tuple] = []
    low_conf: List[Dict[str, Any]] = []
    for c in clusters:
        vr = c.get("vl_result") or {}
        if not vr.get("success"):
            low_conf.append(c)
            continue
        try:
            conf = float(vr.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf >= threshold:
            confirmed.append((c, vr))
        else:
            low_conf.append(c)

    if not low_conf:
        return {"success": True, "no_change": True,
                "changed_ids": [], "changes": []}

    if not confirmed:
        return {"success": True, "no_change": True,
                "changed_ids": [], "changes": [],
                "skipped": "无高置信度锚点，跳过重新判断"}

    prompt = _build_recheck_prompt(clusters, confirmed, low_conf, threshold)
    annotated = _annotate_cluster_for_vl(pil, clusters[0], clusters)
    images = list(base_versions) + [
        {"b64": annotated, "mime": "image/png", "label": "聚类标注图"},
    ]

    print(f"🔁 VL 重新判断：低置信度 {len(low_conf)} 个"
          f"（<{threshold}），锚点 {len(confirmed)} 个 ...")
    res = await _call_vl_for_cluster(images, prompt)
    if not res.get("success"):
        return res

    data = res["data"]
    parsed = data.get("clusters") if isinstance(data, dict) else None
    if not isinstance(parsed, list):
        return {"success": False, "error": "重新判断返回缺少 clusters 字段"}

    low_ids = {int(c["id"]) for c in low_conf}
    updated: Dict[int, Dict[str, Any]] = {}
    for item in parsed:
        pr = _parse_vl_item(item)
        if pr is None:
            continue
        cid, parsed_item = pr
        if cid in low_ids:  # 只接受低置信度簇的修改
            updated[cid] = parsed_item

    changes: List[Dict[str, Any]] = []
    for c in clusters:
        if c["id"] not in updated:
            continue
        old = c.get("vl_result") or {}
        new = updated[c["id"]]
        c["vl_result"] = new
        changes.append({
            "id": c["id"],
            "old": {
                "constellation": old.get("constellation"),
                "constellation_abbr": old.get("constellation_abbr"),
                "confidence": old.get("confidence"),
                "success": bool(old.get("success")),
            },
            "new": {
                "constellation": new.get("constellation"),
                "constellation_abbr": new.get("constellation_abbr"),
                "confidence": new.get("confidence"),
                "success": True,
            },
        })
        print(f"   ↻ C{c['id']} "
              f"{old.get('constellation_abbr') or old.get('constellation') or '?'}"
              f"({old.get('confidence', 0)}) → "
              f"{new.get('constellation_abbr')}({new.get('confidence')})")

    return {
        "success": True,
        "changed_ids": [ch["id"] for ch in changes],
        "changes": changes,
        "summary": str(data.get("summary") or "").strip(),
        "sky_region": str(data.get("sky_region") or "").strip(),
    }

# ==================== 前端展示标注 ====================

def _annotate(
    pil: Image.Image,
    stars: List[Dict[str, Any]],
    clusters: Optional[List[Dict[str, Any]]] = None,
) -> str:
    img = pil.convert("RGB").copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    r_base = max(3.0, min(w, h) * 0.006)
    r_min = r_base * 0.6
    r_max = r_base * 1.9

    fluxes = [max(float(s.get("brightness", 0.0)), 1e-6) for s in stars]
    if fluxes:
        log_vals = np.log(fluxes)
        lo, hi = float(log_vals.min()), float(log_vals.max())
        span = hi - lo
        for s, lv in zip(stars, log_vals):
            t = 0.0 if span < 1e-9 else (lv - lo) / span
            s["_r"] = r_min + t * (r_max - r_min)
    else:
        for s in stars:
            s["_r"] = r_base

    use_cluster_color = bool(clusters) and len(clusters) > 1

    for s in stars:
        px, py = float(s["px"]), float(s["py"])
        r = float(s["_r"])
        if use_cluster_color:
            cid = int(s.get("cluster", 0))
            color = _CLUSTER_PALETTE[cid % len(_CLUSTER_PALETTE)]
        else:
            color = (255, 0, 0)

        draw.ellipse(
            [px - r * 2.2, py - r * 2.2, px + r * 2.2, py + r * 2.2],
            fill=(color[0], color[1], color[2], 60),
        )
        draw.ellipse(
            [px - r, py - r, px + r, py + r],
            fill=(color[0], color[1], color[2], 255),
            outline=(max(0, color[0] - 100), max(0, color[1] - 60),
                     max(0, color[2] - 60), 255),
            width=1,
        )
        s.pop("_r", None)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def _annotate_constellation_positions(
    pil: Image.Image,
    clusters: List[Dict[str, Any]],
) -> str:
    """
    生成“星座位置标注图”：
      · 每个簇用其调色板颜色高亮，主星画大圈 + 白心
      · 每个主星旁边标注 C{id} + 星座名 + 缩写 + 置信度
    返回 base64 PNG。
    """
    img = pil.convert("RGB").copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    r_base = max(4.0, min(w, h) * 0.007)
    font_label = _load_font(max(18, int(min(w, h) * 0.024)))
    font_sub = _load_font(max(13, int(min(w, h) * 0.017)))

    for c in clusters:
        cid = c["id"]
        color = _CLUSTER_PALETTE[cid % len(_CLUSTER_PALETTE)]
        main = c["main_star"]
        mx, my = float(main["px"]), float(main["py"])

        # 簇成员：半透明小实心点
        for s in c["stars"]:
            px, py = float(s["px"]), float(s["py"])
            r = r_base * 0.6
            draw.ellipse(
                [px - r, py - r, px + r, py + r],
                fill=(color[0], color[1], color[2], 185),
            )

        # 主星：大圈 + 白心
        R = r_base * 2.4
        draw.ellipse(
            [mx - R, my - R, mx + R, my + R],
            outline=(color[0], color[1], color[2], 255),
            width=max(2, int(r_base * 0.9)),
        )
        draw.ellipse(
            [mx - r_base * 0.55, my - r_base * 0.55,
             mx + r_base * 0.55, my + r_base * 0.55],
            fill=(255, 255, 255, 255),
        )

        # ---- 读取 VL 结果 ----
        vr = c.get("vl_result") or {}
        if vr.get("success"):
            name = (vr.get("constellation_full")
                    or vr.get("constellation")
                    or vr.get("constellation_abbr") or "")
            abbr = vr.get("constellation_abbr") or ""
            try:
                conf = float(vr.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
            line1 = f"C{cid}: {name}"
            line2 = f"({abbr} {conf:.2f})" if abbr else f"({conf:.2f})"
        else:
            line1 = f"C{cid}: ?"
            line2 = "VL 未判定"

        # ---- 标签框大小 ----
        try:
            l1, t1, r1, b1 = draw.textbbox((0, 0), line1, font=font_label)
            l2, t2, r2, b2 = draw.textbbox((0, 0), line2, font=font_sub)
            tw1, th1 = r1 - l1, b1 - t1
            tw2, th2 = r2 - l2, b2 - t2
        except Exception:
            tw1, th1, tw2, th2 = 120, 22, 80, 16

        box_w = max(tw1, tw2) + 16
        box_h = th1 + th2 + 12

        tx = mx + R + 8
        ty = my - box_h // 2
        if tx + box_w > w - 2:
            tx = mx - R - box_w - 8
        if tx < 2:
            tx = 2
        if ty < 2:
            ty = 2
        if ty + box_h > h - 2:
            ty = h - box_h - 2

        draw.rectangle(
            [tx - 4, ty - 3, tx + box_w, ty + box_h],
            fill=(0, 0, 0, 205),
            outline=(color[0], color[1], color[2], 255),
            width=2,
        )
        draw.text(
            (tx + 3, ty + 1), line1, font=font_label,
            fill=(color[0], color[1], color[2], 255),
        )
        draw.text(
            (tx + 3, ty + th1 + 5), line2, font=font_sub,
            fill=(235, 235, 235, 255),
        )

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

# ==================== 识别端点 ====================

@app.get("/api/vision/status")
async def vision_status():
    return {
        "engine": "opencv-local+kmeans(K=6)+vl",
        "configured": bool(ZHIPU_API_KEY),
        "model": VL_MODEL,
        "hint": (
            "已就绪" if ZHIPU_API_KEY
            else "未配置 MODELSCOPE_API_KEY / ZHIPU_API_KEY"
        ),
        "top_n_default": TOP_N,
        "max_dim": MAX_DIM,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "edge_margin": EDGE_MARGIN_RATIO,
        "forced_k": FORCED_K,
        "min_stars_per_cluster": CLUSTER_MIN_STARS_PER_CLUSTER,
        "weight_brightness": WEIGHT_BRIGHTNESS,
        "weight_distance": WEIGHT_DISTANCE,
        "confidence_threshold": CONFIDENCE_THRESHOLD,  # 新增
    }


@app.get("/api/vision/vl-status")
async def vl_status_compat():
    return await vision_status()


async def _handle_brightest(
    file: UploadFile,
    top_n: int,
    forced_k: Optional[int] = None,
    vl_k: Optional[int] = None,
) -> Dict[str, Any]:
    # ---- 读取上传 ----
    try:
        data = await file.read()
    except Exception as e:
        return {"success": False, "identifiable": False,
                "message": f"读取上传文件失败: {e}"}

    print(f"📥 上传: {file.filename!r} size={len(data)}")

    if not data:
        return {"success": False, "identifiable": False, "message": "图片为空"}
    if len(data) > MAX_UPLOAD_BYTES:
        return {"success": False, "identifiable": False,
                "message": f"图片过大（>{MAX_UPLOAD_BYTES // (1024*1024)}MB）"}

    # ---- 检测 ----
    try:
        result = _detect_brightest_stars(data, max_dim=MAX_DIM, top_n=top_n)
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"success": False, "identifiable": False,
                "message": f"图像处理失败: {e}"}

    stars = result.get("stars", [])
    pil = result["pil"]
    w, h = result.get("size", pil.size)
    print(f"🔎 候选 {result.get('candidate_count', 0)} 个, "
          f"保留 {len(stars)} 颗")

    # ---- 聚类：强制 K=6 ----
    cluster_results: List[Dict[str, Any]] = []
    if len(stars) >= FORCED_K * CLUSTER_MIN_STARS_PER_CLUSTER:
        try:
            cluster_results = _cluster_stars_all(stars, forced_k=FORCED_K)
            if cluster_results:
                print(f"🧩 聚类: K=[{cluster_results[0]['k']}]")
            else:
                print(f"🧩 K={FORCED_K} 不满足每簇最少 {CLUSTER_MIN_STARS_PER_CLUSTER} 颗，无有效聚类")
        except Exception:
            import traceback; traceback.print_exc()

    if not cluster_results:
        # 聚类失败 → 只返回星点，不生成任何标注图
        return {
            "success": True,
            "identifiable": len(stars) > 0,
            "count": len(stars),
            "stars": stars,
            "clusters": [],
            "all_cluster_results": [],
            "vl_clusters": [],
            "vl_summary": None,
            "vl_sky_region": None,
            "image_width": w,
            "image_height": h,
            "threshold": result.get("threshold"),
            "candidate_count": result.get("candidate_count", 0),
            "edge_margin": result.get("edge_margin"),
            "roi": result.get("roi"),
            "annotated_image": "",
            "annotated_mime": "image/png",
            "source": "opencv-local+kmeans+vl",
            "message": f"检测 {len(stars)} 颗星，但 K={FORCED_K} 聚类失败",
        }

    chosen_k_result = cluster_results[0]

    # ---- 为 K=6 生成标注图 ----
    try:
        chosen_k_result["annotated_image"] = _annotate(
            pil, chosen_k_result["stars"], chosen_k_result["clusters"]
        )
        chosen_k_result["annotated_mime"] = "image/png"
    except Exception:
        import traceback; traceback.print_exc()
        chosen_k_result["annotated_image"] = ""
        chosen_k_result["annotated_mime"] = None

    # ---- 整图一次调用 VL ----
    vl_summary = None
    vl_summary = None
    vl_recheck: Optional[Dict[str, Any]] = None

    if ZHIPU_API_KEY:
        print(f"🤖 VL 整图判断：K={FORCED_K}，共 {len(chosen_k_result['clusters'])} 个簇")
        try:
            base_versions = _prepare_versions(pil)
            vl_summary = await _identify_clusters_vl(
                pil, chosen_k_result["clusters"], base_versions
            )
            for c in chosen_k_result["clusters"]:
                vr = c.get("vl_result") or {}
                if vr.get("success"):
                    print(f"   ✓ C{c['id']} → "
                          f"{vr.get('constellation') or vr.get('constellation_abbr')} "
                          f"({vr.get('confidence', 0):.2f})")
                else:
                    print(f"   ✗ C{c['id']} → {vr.get('error')}")

            # ---- 低置信度重新判断 ----
            if vl_summary and vl_summary.get("success"):
                try:
                    vl_recheck = await _recheck_low_confidence_clusters(
                        pil, chosen_k_result["clusters"], base_versions,
                        threshold=CONFIDENCE_THRESHOLD,
                    )
                    if vl_recheck.get("success") and vl_recheck.get("changed_ids"):
                        # 用重新判断的 summary / sky_region 覆盖（若返回）
                        if vl_recheck.get("summary"):
                            vl_summary["summary"] = vl_recheck["summary"]
                        if vl_recheck.get("sky_region"):
                            vl_summary["sky_region"] = vl_recheck["sky_region"]
                        vl_summary["recheck"] = vl_recheck
                except Exception:
                    import traceback; traceback.print_exc()
        except Exception:
            import traceback; traceback.print_exc()
    else:
        for c in chosen_k_result["clusters"]:
            c["vl_result"] = {"success": False, "error": "未配置 VL API Key"}

    # ---- 让 stars[i].cluster 对应 K=6 的分配 ----
    if len(chosen_k_result.get("stars", [])) == len(stars):
        for orig, marked in zip(stars, chosen_k_result["stars"]):
            orig["cluster"] = int(marked.get("cluster", -1))

    # ---- 调试图 ----
    if DEBUG_VISION:
        try:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 1) 输入图（预处理后）
            pil.save(_DEBUG_DIR / f"{ts}_input.png")

            # 2) 簇颜色标注图
            if chosen_k_result.get("annotated_image"):
                (_DEBUG_DIR / f"{ts}_k{FORCED_K}_clusters.png").write_bytes(
                    base64.b64decode(chosen_k_result["annotated_image"])
                )

            # 3) 星座位置标注图（含 VL 判定结果）
            try:
                const_b64 = _annotate_constellation_positions(
                    pil, chosen_k_result["clusters"]
                )
                (_DEBUG_DIR
                 / f"{ts}_k{FORCED_K}_constellations.png").write_bytes(
                    base64.b64decode(const_b64)
                )
                # 也挂回结果，前端有需要可直接取
                chosen_k_result["constellation_annotated_image"] = const_b64
                print(f"💾 星座位置标注图已保存: "
                      f"{ts}_k{FORCED_K}_constellations.png")
            except Exception as e:
                print(f"⚠️ 生成星座位置标注图失败: {e}")

            print(f"💾 调试图: {ts}_*.png")
        except Exception as e:
            print(f"⚠️ 保存调试图失败: {e}")

    # ---- 消息 ----
    identifiable = len(stars) > 0
    vl_ok = sum(
        1 for c in chosen_k_result["clusters"]
        if (c.get("vl_result") or {}).get("success")
    )
    if vl_ok:
        msg = (f"检测 {len(stars)} 颗星，K={FORCED_K}；"
               f"VL 成功判断 {vl_ok}/{len(chosen_k_result['clusters'])} 簇")
    else:
        msg = f"检测 {len(stars)} 颗星，K={FORCED_K}；VL 未返回有效结果"

    # ---- 返回 ----
    all_results = [{
        "k": chosen_k_result["k"],
        "score": chosen_k_result["score"],
        "cluster_count": len(chosen_k_result["clusters"]),
        "clusters": chosen_k_result["clusters"],
        "annotated_image": chosen_k_result.get("annotated_image", ""),
        "annotated_mime": "image/png",
        "used_for_vl": True,
    }]

    return {
        "success": True,
        "identifiable": identifiable,

        "count": len(stars),
        "matched_count": len(stars),
        "detected_star_count": len(stars),
        "stars": stars,
        "detected_stars": [{"x": s["x"], "y": s["y"]} for s in stars],

        # K=6 的聚类（同时作为顶层字段，方便前端读取）
        "clusters": chosen_k_result["clusters"],
        "cluster_k": FORCED_K,
        "cluster_score": chosen_k_result["score"],

        # 全部 K（现在只有 6）
        "all_cluster_results": all_results,
        # VL 结果
        "vl_cluster_k": FORCED_K,
        "vl_clusters": chosen_k_result["clusters"],
        "vl_summary": vl_summary.get("summary") if vl_summary else None,
        "vl_sky_region": vl_summary.get("sky_region") if vl_summary else None,

        # 低置信度重新判断（只包含被修改的簇）
        "vl_low_confidence_threshold": CONFIDENCE_THRESHOLD,
        "vl_recheck": {
            "performed": bool(
                vl_recheck
                and vl_recheck.get("success")
                and not vl_recheck.get("no_change")
            ),
            "threshold": CONFIDENCE_THRESHOLD,
            "changed_ids": vl_recheck.get("changed_ids", []) if vl_recheck else [],
            "changes": vl_recheck.get("changes", []) if vl_recheck else [],
            "skipped": vl_recheck.get("skipped") if vl_recheck else None,
        } if vl_recheck else None,

        # 图像信息
        "image_width": w,
        "image_height": h,
        "threshold": result.get("threshold"),
        "candidate_count": result.get("candidate_count", 0),
        "edge_margin": result.get("edge_margin"),
        "roi": result.get("roi"),

        # 标注图（K=6）
        "annotated_image": chosen_k_result.get("annotated_image", ""),
        "annotated_mime": "image/png",

        "source": "opencv-local+kmeans+vl",
        "message": msg,
    }


@app.post("/api/vision/brightest-stars")
async def brightest_stars(
    file: UploadFile = File(...),
    top_n: int = Query(default=TOP_N, ge=1, le=200),
    cluster_k: Optional[int] = Query(default=FORCED_K, ge=2, le=10),
    vl_k: Optional[int] = Query(default=FORCED_K, ge=2, le=10),
):
    return await _handle_brightest(
        file, top_n, forced_k=FORCED_K, vl_k=FORCED_K
    )


@app.post("/api/vision/identify")
async def identify(file: UploadFile = File(...)):
    return await _handle_brightest(
        file, TOP_N, forced_k=FORCED_K, vl_k=FORCED_K
    )


@app.post("/api/vision/vl-identify")
async def vl_identify_compat(file: UploadFile = File(...)):
    return await _handle_brightest(
        file, TOP_N, forced_k=FORCED_K, vl_k=FORCED_K
    )


if __name__ == "__main__":
    import uvicorn

    print(f"🔭 识星引擎: OpenCV + K-means (强制 K={FORCED_K}) + VL 整图调用")
    print(f"📁 debug: {_DEBUG_DIR}  (DEBUG_VISION={DEBUG_VISION})")
    print(f"🖼  边缘遮罩: {EDGE_MARGIN_RATIO:.0%}")
    print(f"🧩 聚类: 强制 K={FORCED_K}，每簇至少 {CLUSTER_MIN_STARS_PER_CLUSTER} 颗")
    if ZHIPU_API_KEY:
        print(f"🤖 VL: {VL_MODEL}  Key={ZHIPU_API_KEY[:6]}...")
    else:
        print("⚠️  未配置 VL API Key，将只输出聚类结果")

    uvicorn.run(app, host="0.0.0.0", port=8000)