"""
天球可视化系统 - FastAPI 后端
照片识星 v13
· 纯 VL 识别（不依赖 astrometry.net）
· 提示词拆分任务：观察 → 找图案 → 判断 → 定位
· 只画星点 + 星座标签，不画骨架连线
· 过滤低置信度结果
"""
import os
import sys
from pathlib import Path

# ---- 1) 先算目录，再把 .env 提前加载 ----
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

# ---- 2) .env 加载完成后，再 import 其他模块 ----
import json
import base64
import re
from io import BytesIO
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, Query, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from data_loader import HYGDataLoader
from tour.api import router as tour_router, set_loader

from PIL import Image
import numpy as np
import cv2

app = FastAPI(title="3D天球可视化系统 API", version="2.4.0")

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

ZHIPU_API_URL = os.getenv(
    "ZHIPU_API_URL",
    "https://api-inference.modelscope.cn/v1/chat/completions"
).strip()

ZHIPU_API_KEY = os.getenv(
    "MODELSCOPE_API_KEY",
    os.getenv("ZHIPU_API_KEY", "")
).strip()

VL_MODEL = os.getenv("VL_MODEL", "deepseek-ai/DeepSeek-V4-Flash-Vision-Exp").strip()

VERIFY_MAX_MAG = float(os.getenv("VERIFY_MAX_MAG", "6.5"))
DEBUG_VISION = os.getenv("DEBUG_VISION", "0") == "1"

# ---- VL 识星的置信度门槛 ----
MIN_CONF_DRAW = float(os.getenv("MIN_CONF_DRAW", "0.45"))


# ==================== 88 星座标准名 ====================

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

_ABBR_TO_FULL = {abbr: full for abbr, full in _CONSTELLATION_PAIRS}
_FULL_LOWER_TO_ABBR = {full.lower(): abbr for abbr, full in _CONSTELLATION_PAIRS}
_ABBR_LOWER_TO_ABBR = {abbr.lower(): abbr for abbr, full in _CONSTELLATION_PAIRS}

SEASON_ZH = {
    "spring": "春季", "summer": "夏季",
    "autumn": "秋季", "winter": "冬季",
    "unknown": "不确定", "": "",
}

_ALLOWED_POSITIONS = {
    "左上", "上", "右上", "左", "中央", "右", "左下", "下", "右下", "不确定",
}

_POSITION_TO_BOX = {
    "左上": (0.02, 0.02, 0.35, 0.35),
    "上":   (0.34, 0.02, 0.66, 0.35),
    "右上": (0.65, 0.02, 0.98, 0.35),
    "左":   (0.02, 0.34, 0.35, 0.66),
    "中央": (0.34, 0.34, 0.66, 0.66),
    "右":   (0.65, 0.34, 0.98, 0.66),
    "左下": (0.02, 0.65, 0.35, 0.98),
    "下":   (0.34, 0.65, 0.66, 0.98),
    "右下": (0.65, 0.65, 0.98, 0.98),
    "不确定": (0.34, 0.34, 0.66, 0.66),
}


# ==================== 基础数据 API ====================

@app.get("/api/status")
async def get_status():
    return {
        "loaded": loader.loaded,
        "total_stars": len(loader.df) if loader.df is not None else 0,
    }


@app.post("/api/load")
async def load_data():
    r = loader.load_data()
    return r


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


# ==================== 工具函数 ====================

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        v = float(value)
    except Exception:
        return lo
    return max(lo, min(hi, v))


def _norm(name: str) -> str:
    if not name:
        return ""
    n = str(name).strip().lower()
    n = re.sub(r"[^a-z0-9]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if not n:
        return ""
    compact = n.replace(" ", "")
    if compact in _ABBR_LOWER_TO_ABBR:
        return _ABBR_LOWER_TO_ABBR[compact]
    if n in _FULL_LOWER_TO_ABBR:
        return _FULL_LOWER_TO_ABBR[n]
    if n.startswith("the "):
        n2 = n[4:]
        if n2 in _FULL_LOWER_TO_ABBR:
            return _FULL_LOWER_TO_ABBR[n2]
    return ""


def _normalize_season(value: Any) -> str:
    if not value:
        return "unknown"
    t = str(value).strip().lower()
    if any(k in t for k in ["spring", "春"]):
        return "spring"
    if any(k in t for k in ["summer", "夏"]):
        return "summer"
    if any(k in t for k in ["autumn", "fall", "秋"]):
        return "autumn"
    if any(k in t for k in ["winter", "冬"]):
        return "winter"
    return "unknown"


def _clean_position(value: Any) -> str:
    p = str(value or "").strip()
    if p in _ALLOWED_POSITIONS:
        return p
    p_lower = p.lower()
    position_map = {
        "top left": "左上", "left top": "左上",
        "upper left": "左上", "left upper": "左上",
        "top": "上", "upper": "上",
        "top right": "右上", "right top": "右上",
        "upper right": "右上", "right upper": "右上",
        "left": "左",
        "center": "中央", "centre": "中央", "middle": "中央",
        "right": "右",
        "bottom left": "左下", "left bottom": "左下",
        "lower left": "左下", "left lower": "左下",
        "bottom": "下", "lower": "下",
        "bottom right": "右下", "right bottom": "右下",
        "lower right": "右下", "right lower": "右下",
    }
    if p_lower in position_map:
        return position_map[p_lower]
    return "不确定"


def _clean_bright_stars(items: Any) -> List[Dict[str, str]]:
    if not isinstance(items, list):
        return []
    out: List[Dict[str, str]] = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        if re.search(r"\d", name):
            continue
        out.append({
            "name": name,
            "position": _clean_position(item.get("position")),
        })
    return out


def _clean_vl_stars(items: Any) -> List[Dict[str, Any]]:
    """
    清洗 VL 返回的 stars 数组：
      · x, y 归一化到 0~1
      · 过滤明显越界、重复、无效的坐标
      · 最多保留 8 颗（避免 VL 乱标）
    """
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in items[:12]:
        if not isinstance(item, dict):
            continue
        try:
            x = float(item.get("x"))
            y = float(item.get("y"))
        except (TypeError, ValueError):
            continue
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            continue
        key = (round(x, 2), round(y, 2))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": str(item.get("name", "")).strip(),
            "x": round(x, 4),
            "y": round(y, 4),
        })
        if len(out) >= 8:
            break
    return out


def _star_constellation(star: Dict[str, Any]) -> str:
    return str(star.get("constellation", star.get("con", ""))).strip()


def _star_mag(star: Dict[str, Any]) -> float:
    for key in ("mag", "magnitude", "Vmag", "v_mag"):
        if key in star:
            try:
                return float(star[key])
            except Exception:
                pass
    return 99.0


def _star_display_name(star: Dict[str, Any]) -> str:
    keys = ("proper", "name", "desig", "bayer", "bf")
    for key in keys:
        v = star.get(key)
        if v is None:
            continue
        v = str(v).strip()
        if not v:
            continue
        if v.lower() in {"nan", "none", "null"}:
            continue
        if re.fullmatch(r"[\d\s\-+./]+", v):
            continue
        if re.search(r"\b(hd|hip|hr|gliese|groombridge)\b", v, re.IGNORECASE):
            continue
        if re.search(r"\d", v):
            continue
        return v
    return ""


def _clean_star_for_output(star: Dict[str, Any], display_name: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "name": display_name,
        "display_name": display_name,
        "constellation": _star_constellation(star),
        "mag": _star_mag(star),
    }
    for key in ("ra", "dec", "x", "y", "z"):
        if key in star:
            try:
                out[key] = float(star[key])
            except Exception:
                pass
    return out


def _select_skeleton_stars(
    stars: List[Dict[str, Any]],
    limit: int = 8,
) -> List[Dict[str, Any]]:
    if not stars:
        return []
    sorted_stars = sorted(stars, key=_star_mag)
    chosen: List[Dict[str, Any]] = []
    seen_names = set()
    for s in sorted_stars:
        name = _star_display_name(s)
        if not name:
            continue
        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        chosen.append(_clean_star_for_output(s, name))
        if len(chosen) >= limit:
            break
    if not chosen:
        for s in sorted_stars[:3]:
            chosen.append(_clean_star_for_output(s, ""))
    return chosen


# ==================== 图片准备 ====================

def _prepare_two_versions(image_bytes: bytes, max_dim: int = 1280) -> Dict[str, Any]:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    arr = np.array(img)

    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    adapted_arr = cv2.cvtColor(cv2.merge([l2, a, b]), cv2.COLOR_LAB2RGB)
    adapted = Image.fromarray(adapted_arr)

    def _b64_png(pil_img: Image.Image) -> str:
        buf = BytesIO()
        pil_img.save(buf, format="PNG", optimize=False)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _b64_jpg(pil_img: Image.Image, q: int = 95) -> str:
        buf = BytesIO()
        pil_img.save(buf, format="JPEG", quality=q)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    if DEBUG_VISION:
        try:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            img.save(_DEBUG_DIR / f"{ts}_original.png")
            adapted.save(_DEBUG_DIR / f"{ts}_adapted.png")
        except Exception:
            pass

    return {
        "original_b64": _b64_jpg(img, q=95),
        "original_mime": "image/jpeg",
        "adapted_b64": _b64_png(adapted),
        "adapted_mime": "image/png",
        "original_pil": img,
        "adapted_pil": adapted,
    }


# ==================== Prompt ====================

VL_PROMPT = """你是天文识别专家。这是同一张夜空照片的两个版本：
图1：原图。
图2：暗部提亮版（暗星更容易看见）。

请严格按照以下四步分析，不要跳步：

【第一步 · 观察】
描述照片内容：是否有银河？银河走向如何？有没有明显的亮星组成图案？画面噪点水平如何？

【第二步 · 找图案】
在画面中寻找 3~7 颗星组成的、容易辨认的几何图案，例如：
- 三颗几乎等距排列成一条直线（如猎户腰带）
- 一个明显的"勺子"或"W"形（如北斗、仙后座）
- 一个大的三角形或四边形（如夏季大三角、秋季四边形）
- 一条弯曲的"钩子"或"S"形（如天蝎座尾部）
请用自然语言描述你看到的图案。

【第三步 · 判断星座】
根据图案，判断最可能的星座。只判断你有把握的星座：
- 如果只能猜到 1~2 个，就只返回 1~2 个
- 如果完全认不出，visible 设为 false
- 不要为了凑数而编造

【第四步 · 定位】
对每个你判断出的星座，给出你能确认的 3~7 颗主要亮星的位置：
- x, y 为归一化坐标（0~1，左上角是 (0,0)，右下角是 (1,1)）
- 允许坐标有误差（±0.05 也可接受），但【相对位置必须符合该星座的特征】：
  · 猎户腰带三颗星必须近似排成一条直线
  · 北斗七星必须形成勺子形
  · 夏季大三角必须两两之间距离相当
- 如果拿不准某颗星的位置，宁可不标它，也不要乱标

【返回要求】
- 星座名用标准英文名（如 Orion、Ursa Major、Cygnus）
- 亮星名用常见英文名（如 Betelgeuse、Vega、Deneb）；不确定就留空字符串
- confidence 要诚实：非常确定 ≥ 0.8，比较确定 0.5~0.7，不确定 ≤ 0.4
- 画面里没有星座时 visible = false，constellations 返回空数组

只输出 JSON，不要 markdown，不要解释：

{
  "visible": true,
  "image_description": "20~60 字的画面描述",
  "pattern_description": "用一句话描述找到的几何图案",
  "estimated_season": "summer",
  "constellations": [
    {
      "name": "Cygnus",
      "confidence": 0.7,
      "position": "中央",
      "stars": [
        {"name": "Deneb",  "x": 0.45, "y": 0.20},
        {"name": "Sadr",   "x": 0.50, "y": 0.42},
        {"name": "Albireo","x": 0.55, "y": 0.68},
        {"name": "Gienah", "x": 0.32, "y": 0.38},
        {"name": "Delta Cygni", "x": 0.68, "y": 0.40}
      ],
      "bright_stars": [
        {"name": "Deneb", "position": "上"},
        {"name": "Albireo", "position": "下"}
      ],
      "reason": "十字形，Deneb 亮度突出，符合天鹅座"
    }
  ],
  "note": "一句话结论"
}
"""


# ==================== VL 调用 ====================

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


def _extract_json(text: str) -> Dict[str, Any]:
    t = _strip_fence(text)
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    raise ValueError("JSON parse failed")


async def _call_vl(images: list, prompt: str) -> dict:
    if not ZHIPU_API_KEY:
        return {"success": False, "error": "未配置 ZHIPU_API_KEY"}

    content = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}
        })

    payload = {
        "model": VL_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2048,
        "temperature": 0.0,     # 让输出最确定
        "top_p": 0.2,           # 缩小采样空间
    }
    headers = {"Authorization": f"Bearer {ZHIPU_API_KEY}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(ZHIPU_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                err_msg = data["error"]
                if isinstance(err_msg, dict):
                    err_msg = err_msg.get("message", str(err_msg))
                return {"success": False, "error": f"API 业务报错: {err_msg}", "raw_content": str(data)}

            choices = data.get("choices")
            if not choices:
                return {"success": False, "error": f"API 返回数据异常(无choices): {str(data)[:200]}", "raw_content": str(data)}

            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if not message:
                return {"success": False, "error": f"API 返回数据异常(无message): {str(data)[:200]}", "raw_content": str(data)}

            raw = message.get("content", "")

            if isinstance(raw, list):
                raw = " ".join(p.get("text", "") for p in raw if isinstance(p, dict) and p.get("type") == "text")

            raw = _strip_fence(str(raw))
            try:
                return {"success": True, "data": json.loads(raw)}
            except json.JSONDecodeError:
                return {"success": False, "error": f"模型返回非 JSON: {raw[:400]}", "raw_content": raw}

        except httpx.HTTPStatusError as e:
            body = e.response.text[:400] if e.response is not None else ""
            return {"success": False, "error": f"API HTTP {e.response.status_code}: {body}"}
        except httpx.TimeoutException:
            return {"success": False, "error": "VL 调用超时 (timeout)"}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"调用失败: {str(e)}"}


# ==================== 标注图 ====================

def _annotate_image(
    pil_img: Image.Image,
    vl_items: List[Dict[str, Any]],
    min_conf: float = 0.45,
    max_constellations: int = 6,
) -> str:
    """
    在照片上标注 VL 识别出的星点 + 星座标签：
      · 每个星座画出它标出的星点（圆点）
      · 在星点几何中心写星座名
      · 不画骨架连线（避免一根线错全盘崩）
      · 只画 confidence >= min_conf 的星座
      · 若某星座标出的星点不足 2 颗，则退化为在九宫格中心位置标一个标签
    """
    from PIL import ImageDraw, ImageFont

    img = pil_img.convert("RGB").copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    try:
        font_size = max(18, int(min(w, h) * 0.028))
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    star_radius = max(4, int(min(w, h) * 0.007))

    drawn = 0
    for item in vl_items or []:
        if not isinstance(item, dict):
            continue
        try:
            conf = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        if conf < min_conf:
            continue

        abbr = _norm(item.get("name", ""))
        if not abbr:
            continue

        stars = _clean_vl_stars(item.get("stars"))

        # ---- 收集像素坐标 ----
        pts: List[tuple] = []
        for s in stars:
            pts.append((s["x"] * w, s["y"] * h))

        # ---- 若星点不足，用九宫格中心作为标签位置 ----
        if len(pts) < 2:
            pos = _clean_position(item.get("position"))
            x1, y1, x2, y2 = _POSITION_TO_BOX.get(pos, _POSITION_TO_BOX["不确定"])
            cx = (x1 + x2) / 2 * w
            cy = (y1 + y2) / 2 * h
        else:
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)

        # ---- 画星点 ----
        for (px, py) in pts:
            draw.ellipse(
                [px - star_radius, py - star_radius,
                 px + star_radius, py + star_radius],
                fill=(255, 255, 0, 255),
                outline=(255, 120, 0, 255),
                width=2,
            )

        # ---- 写星座名（英文全名 + 置信度）----
        label = _ABBR_TO_FULL.get(abbr, abbr)
        label = f"{label}  {conf:.0%}"

        try:
            left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
            tw = right - left
            th = bottom - top
        except Exception:
            tw, th = draw.textsize(label, font=font)

        tx = cx - tw / 2
        ty = cy - th / 2

        draw.rectangle(
            [tx - 8, ty - 5, tx + tw + 8, ty + th + 5],
            fill=(0, 0, 0, 200),
        )
        draw.text((tx, ty), label, font=font, fill=(255, 255, 255, 255))

        drawn += 1
        if drawn >= max_constellations:
            break

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ==================== 后端校验 ====================

def _verify(vl_items: List[Dict[str, Any]], hyg_stars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in vl_items or []:
        if not isinstance(item, dict):
            continue
        abbr = _norm(item.get("name", ""))
        if not abbr:
            continue
        conf = _clamp(item.get("confidence", 0.5))
        position = _clean_position(item.get("position"))

        constellation_records = [
            s for s in hyg_stars
            if _star_constellation(s) == abbr
        ]

        filtered: List[tuple] = []
        for s in constellation_records:
            mag = _star_mag(s)
            if mag <= VERIFY_MAX_MAG:
                filtered.append((mag, s))
        filtered.sort(key=lambda x: x[0])

        if filtered:
            matched_stars = [s for _, s in filtered[:12]]
        else:
            all_records = [(_star_mag(s), s) for s in constellation_records]
            all_records.sort(key=lambda x: x[0])
            matched_stars = [s for _, s in all_records[:12]]

        if not matched_stars:
            continue

        skeleton_stars = _select_skeleton_stars(matched_stars, limit=8)

        out.append({
            "abbr": abbr,
            "full": _ABBR_TO_FULL.get(abbr, abbr),
            "confidence": round(conf, 3),
            "position": position,
            "stars": _clean_vl_stars(item.get("stars")),
            "reason": str(item.get("reason", "")),
            "bright_stars": _clean_bright_stars(item.get("bright_stars")),
            "matched_stars": skeleton_stars,
            "skeleton_stars": skeleton_stars,
            "star_count": len(skeleton_stars),
            "raw_star_count": len(matched_stars),
        })
    out.sort(key=lambda x: -x["confidence"])
    return out


# ==================== 识别端点 ====================

@app.get("/api/vision/vl-status")
async def vl_status():
    return {
        "configured": bool(ZHIPU_API_KEY),
        "model": VL_MODEL,
        "hint": "未配置 MODELSCOPE_API_KEY / ZHIPU_API_KEY"
        if not ZHIPU_API_KEY
        else "已就绪",
        "min_conf_draw": MIN_CONF_DRAW,
    }


@app.post("/api/vision/vl-identify")
async def vl_identify(file: UploadFile = File(...)):
    if not loader.loaded:
        try:
            load_result = loader.load_data()
            if not load_result.get("success"):
                return {"success": False, "message": "请先加载 HYG 星表数据"}
        except Exception:
            return {"success": False, "message": "请先加载 HYG 星表数据"}

    if not ZHIPU_API_KEY:
        return {"success": False, "message": "未配置 MODELSCOPE_API_KEY / ZHIPU_API_KEY"}

    try:
        img_bytes = await file.read()
        if not img_bytes:
            return {"success": False, "message": "图片为空"}
        if len(img_bytes) > 15 * 1024 * 1024:
            return {"success": False, "message": "图片过大（>15MB）"}

        try:
            imgs = _prepare_two_versions(img_bytes, max_dim=1280)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "message": f"读取图片失败: {e}"}

        vl_images = [
            {"b64": imgs["original_b64"], "mime": imgs["original_mime"]},
            {"b64": imgs["adapted_b64"], "mime": imgs["adapted_mime"]},
        ]

        vl = await _call_vl(vl_images, VL_PROMPT)

        if not vl["success"]:
            return {
                "success": False,
                "message": vl.get("error"),
                "raw_content": vl.get("raw_content"),
                "annotated_image": "",
                "annotated_mime": "image/png",
            }

        feat = vl["data"]
        if not isinstance(feat, dict):
            return {
                "success": False,
                "message": "模型返回格式异常",
                "raw_content": str(feat)[:500],
                "annotated_image": "",
                "annotated_mime": "image/png",
            }

        visible = bool(feat.get("visible", True))
        image_description = str(feat.get("image_description", ""))
        pattern_description = str(feat.get("pattern_description", ""))
        estimated_season = _normalize_season(feat.get("estimated_season", ""))
        vl_items = feat.get("constellations") or []
        note = str(feat.get("note", ""))

        print(
            f"[vl] visible={visible}, season={estimated_season}, "
            f"items={[(i.get('name'), i.get('confidence')) for i in vl_items]}"
        )
        print(f"[vl] image_description: {image_description}")
        print(f"[vl] pattern: {pattern_description}")
        print(f"[vl] note: {note}")

        if not visible or not vl_items:
            return {
                "success": True,
                "cross_check_passed": False,
                "vl_visible": False,
                "vl_constellations": [],
                "matched_stars": [],
                "matched_count": 0,
                "final_confidence": 0.0,
                "estimated_season": estimated_season,
                "vl_season": estimated_season,
                "vl_season_zh": SEASON_ZH.get(estimated_season, ""),
                "image_description": image_description,
                "vl_pattern_description": pattern_description or image_description or note,
                "vl_note": note,
                "raw_vl_features": feat,
                "annotated_image": "",
                "annotated_mime": "image/png",
                "message": f"未能识别出足够可信的结果：{note}".strip("："),
            }

        try:
            hyg_stars = loader.get_stars(max_mag=VERIFY_MAX_MAG)
        except Exception:
            hyg_stars = loader.get_bright_stars(max_mag=VERIFY_MAX_MAG)

        verified = _verify(vl_items, hyg_stars)

        annotated_image = ""
        try:
            annotate_source = imgs.get("original_pil")
            if annotate_source is None:
                annotate_source = Image.open(BytesIO(img_bytes)).convert("RGB")
            annotated_image = _annotate_image(
                annotate_source, vl_items, min_conf=MIN_CONF_DRAW
            )
        except Exception:
            import traceback
            traceback.print_exc()
            annotated_image = ""

        if not verified:
            return {
                "success": True,
                "cross_check_passed": False,
                "vl_visible": True,
                "vl_constellations": [],
                "matched_stars": [],
                "matched_count": 0,
                "final_confidence": 0.0,
                "estimated_season": estimated_season,
                "vl_season": estimated_season,
                "vl_season_zh": SEASON_ZH.get(estimated_season, ""),
                "image_description": image_description,
                "vl_pattern_description": pattern_description or image_description or note,
                "vl_note": note,
                "raw_vl_features": feat,
                "annotated_image": annotated_image,
                "annotated_mime": "image/png",
                "message": "模型给出了结果，但未能通过星表校验。",
            }

        top = verified[0]
        return {
            "success": True,
            "cross_check_passed": top["confidence"] >= 0.5,
            "vl_visible": True,
            "vl_constellations": verified,
            "matched_stars": top["matched_stars"],
            "matched_count": len(top["matched_stars"]),
            "estimated_season": estimated_season,
            "vl_season": estimated_season,
            "vl_season_zh": SEASON_ZH.get(estimated_season, ""),
            "final_confidence": top["confidence"],
            "image_description": image_description,
            "vl_pattern_description": pattern_description or image_description or note,
            "vl_note": note,
            "raw_vl_features": feat,
            "annotated_image": annotated_image,
            "annotated_mime": "image/png",
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"识别失败: {e}"}


# 兼容别名
@app.post("/api/vision/identify")
async def identify(file: UploadFile = File(...)):
    return await vl_identify(file)


if __name__ == "__main__":
    import uvicorn
    if not ZHIPU_API_KEY:
        print("⚠️ 未配置 MODELSCOPE_API_KEY / ZHIPU_API_KEY")
    else:
        print(f"✅ API Key: {ZHIPU_API_KEY[:6]}...")
        print(f"✅ 模型: {VL_MODEL}")
        print(f"📁 debug: {_DEBUG_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=8000)