"""
天球可视化系统 - FastAPI 后端
照片识星 v11
· 简洁提示词
· 输出季节、星座、亮星、位置
· 返回骨架星，过滤数字编号
· 返回标注图，便于前端弹窗显示与保存
"""

import os
import sys
import json
import base64
import httpx
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import FastAPI, Query, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from data_loader import HYGDataLoader

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_DIR / ".env")
except Exception:
    pass

from PIL import Image
import numpy as np
import cv2


app = FastAPI(title="3D天球可视化系统 API", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

loader = HYGDataLoader()

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

VL_MODEL = os.getenv(
    "VL_MODEL",
    "Qwen/Qwen3-VL-8B-Instruct"
).strip()

VERIFY_MAX_MAG = float(os.getenv("VERIFY_MAX_MAG", "6.5"))
DEBUG_VISION = os.getenv("DEBUG_VISION", "0") == "1"


# ==================== 88 星座标准名 ====================

_CONSTELLATION_PAIRS = [
    ("And", "Andromeda"),
    ("Ant", "Antlia"),
    ("Aps", "Apus"),
    ("Aqr", "Aquarius"),
    ("Aql", "Aquila"),
    ("Ara", "Ara"),
    ("Ari", "Aries"),
    ("Aur", "Auriga"),
    ("Boo", "Bootes"),
    ("Cae", "Caelum"),
    ("Cam", "Camelopardalis"),
    ("Cnc", "Cancer"),
    ("CMa", "Canis Major"),
    ("CMi", "Canis Minor"),
    ("Cap", "Capricornus"),
    ("Car", "Carina"),
    ("Cas", "Cassiopeia"),
    ("Cen", "Centaurus"),
    ("Cep", "Cepheus"),
    ("Cet", "Cetus"),
    ("Cha", "Chamaeleon"),
    ("Cir", "Circinus"),
    ("Col", "Columba"),
    ("Com", "Coma Berenices"),
    ("CrA", "Corona Australis"),
    ("CrB", "Corona Borealis"),
    ("Crv", "Corvus"),
    ("Crt", "Crater"),
    ("Cru", "Crux"),
    ("Cyg", "Cygnus"),
    ("Del", "Delphinus"),
    ("Dor", "Dorado"),
    ("Dra", "Draco"),
    ("Equ", "Equuleus"),
    ("Eri", "Eridanus"),
    ("For", "Fornax"),
    ("Gem", "Gemini"),
    ("Gru", "Grus"),
    ("Her", "Hercules"),
    ("Hor", "Horologium"),
    ("Hya", "Hydra"),
    ("Hyi", "Hydrus"),
    ("Ind", "Indus"),
    ("Lac", "Lacerta"),
    ("Leo", "Leo"),
    ("LMi", "Leo Minor"),
    ("Lep", "Lepus"),
    ("Lib", "Libra"),
    ("Lup", "Lupus"),
    ("Lyn", "Lynx"),
    ("Lyr", "Lyra"),
    ("Men", "Mensa"),
    ("Mic", "Microscopium"),
    ("Mon", "Monoceros"),
    ("Mus", "Musca"),
    ("Nor", "Norma"),
    ("Oct", "Octans"),
    ("Oph", "Ophiuchus"),
    ("Ori", "Orion"),
    ("Peg", "Pegasus"),
    ("Per", "Perseus"),
    ("Phe", "Phoenix"),
    ("Pic", "Pictor"),
    ("Psc", "Pisces"),
    ("PsA", "Piscis Austrinus"),
    ("Pup", "Puppis"),
    ("Pyx", "Pyxis"),
    ("Ret", "Reticulum"),
    ("Sge", "Sagitta"),
    ("Sgr", "Sagittarius"),
    ("Sco", "Scorpius"),
    ("Scl", "Sculptor"),
    ("Sct", "Scutum"),
    ("Ser", "Serpens"),
    ("Sex", "Sextans"),
    ("Tau", "Taurus"),
    ("Tel", "Telescopium"),
    ("Tri", "Triangulum"),
    ("TrA", "Triangulum Australe"),
    ("Tuc", "Tucana"),
    ("UMa", "Ursa Major"),
    ("UMi", "Ursa Minor"),
    ("Vel", "Vela"),
    ("Vir", "Virgo"),
    ("Vol", "Volans"),
    ("Vul", "Vulpecula"),
]

_ABBR_TO_FULL = {abbr: full for abbr, full in _CONSTELLATION_PAIRS}
_FULL_LOWER_TO_ABBR = {full.lower(): abbr for abbr, full in _CONSTELLATION_PAIRS}
_ABBR_LOWER_TO_ABBR = {abbr.lower(): abbr for abbr, full in _CONSTELLATION_PAIRS}

SEASON_ZH = {
    "spring": "春季",
    "summer": "夏季",
    "autumn": "秋季",
    "winter": "冬季",
    "unknown": "不确定",
    "": "",
}

_ALLOWED_POSITIONS = {
    "左上",
    "上",
    "右上",
    "左",
    "中央",
    "右",
    "左下",
    "下",
    "右下",
    "不确定",
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
    if not r["success"]:
        raise HTTPException(500, r["message"])
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
    """
    将模型返回的星座名归一化为 IAU 缩写。
    """
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
        "top left": "左上",
        "left top": "左上",
        "upper left": "左上",
        "left upper": "左上",
        "top": "上",
        "upper": "上",
        "top right": "右上",
        "right top": "右上",
        "upper right": "右上",
        "right upper": "右上",
        "left": "左",
        "center": "中央",
        "centre": "中央",
        "middle": "中央",
        "right": "右",
        "bottom left": "左下",
        "left bottom": "左下",
        "lower left": "左下",
        "left lower": "左下",
        "bottom": "下",
        "lower": "下",
        "bottom right": "右下",
        "right bottom": "右下",
        "lower right": "右下",
        "right lower": "右下",
    }

    if p_lower in position_map:
        return position_map[p_lower]

    return "不确定"


def _clean_bbox(value: Any) -> List[float]:
    """
    清洗模型返回的 bbox。
    支持：
    · 0~1
    · 0~1000
    """
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return []

    try:
        nums = [float(v) for v in value]
    except Exception:
        return []

    if max(nums) > 1.5:
        nums = [v / 1000.0 for v in nums]

    x1, y1, x2, y2 = [_clamp(v) for v in nums]

    if x2 < x1:
        x1, x2 = x2, x1

    if y2 < y1:
        y1, y2 = y2, y1

    if x2 - x1 < 0.02 or y2 - y1 < 0.02:
        return []

    return [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)]


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

        out.append(
            {
                "name": name,
                "position": _clean_position(item.get("position")),
            }
        )

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
    """
    返回适合展示的恒星名。
    过滤数字编号、HD / HIP / HR 等。
    """
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
    """
    只输出必要字段，避免大量数字编号字段。
    """
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
    """
    选择骨架星：
    · 优先有名字的亮星；
    · 过滤数字编号；
    · 如果没有合适名字星，给少量无名亮星占位，但不显示编号。
    """
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
    """
    返回：
    · original_b64：缩放后的原图
    · adapted_b64：暗部增强版
    · original_pil：原图 PIL 对象
    · adapted_pil：增强版 PIL 对象
    """
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

    if DEBUG_VISION:
        try:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            img.save(_DEBUG_DIR / f"{ts}_original.png")
            adapted.save(_DEBUG_DIR / f"{ts}_adapted.png")
        except Exception:
            pass

    return {
        "original_b64": _b64_png(img),
        "adapted_b64": _b64_png(adapted),
        "original_pil": img,
        "adapted_pil": adapted,
    }


# ==================== Prompt ====================

VL_PROMPT = """这是同一张夜空照片的两个版本：
图1：原图。
图2：暗部提亮版。

请先解读这张图你看到了什么，再分析这可能是哪个季节的星空，具体都有什么星座和亮星，分别在哪里。

要求：
1. 不确定就降低置信度，或者返回 visible: false。
2. 不要编造星座或亮星。
3. 星座名使用标准英文名。
4. 亮星名使用常见英文名；不确定就留空。
5. 位置只能填：左上、上、右上、左、中央、右、左下、下、右下、不确定。
6. 如果可以，请为每个星座给出画面范围 bbox：[x_min, y_min, x_max, y_max]，数值范围 0~1；不确定就填 []。
7. 亮星名中不要输出数字编号。
8. estimated_season 只能填：spring、summer、autumn、winter、unknown。

只输出 JSON，不要 markdown：
{
  "visible": true,
  "image_description": "简短描述你看到的天空情况",
  "estimated_season": "unknown",
  "constellations": [
    {
      "name": "英文名",
      "confidence": 0.55,
      "position": "中央",
      "bbox": [0.35, 0.30, 0.70, 0.80],
      "bright_stars": [
        {
          "name": "英文名",
          "position": "中央"
        }
      ],
      "reason": "简短说明"
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


async def _call_vl(images: List[Dict[str, str]], prompt: str) -> Dict[str, Any]:
    if not ZHIPU_API_KEY:
        return {"success": False, "error": "未配置 MODELSCOPE_API_KEY / ZHIPU_API_KEY"}

    content = [{"type": "text", "text": prompt}]

    for img in images:
        b64 = img.get("b64", "")
        mime = img.get("mime", "image/png")
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}"
                },
            }
        )

    payload = {
        "model": VL_MODEL,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "max_tokens": 2048,
        "temperature": 0.0,
    }

    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(ZHIPU_API_URL, json=payload, headers=headers)
            resp.raise_for_status()

            data = resp.json()
            raw = data["choices"][0]["message"]["content"]

            if isinstance(raw, list):
                raw = " ".join(
                    p.get("text", "")
                    for p in raw
                    if isinstance(p, dict) and p.get("type") == "text"
                )

            try:
                parsed = _extract_json(str(raw))
                return {"success": True, "data": parsed}
            except Exception:
                return {
                    "success": False,
                    "error": f"模型返回非 JSON: {str(raw)[:400]}",
                    "raw_content": str(raw),
                }

        except httpx.HTTPStatusError as e:
            body = e.response.text[:400] if e.response is not None else ""
            return {
                "success": False,
                "error": f"API HTTP {e.response.status_code}: {body}",
            }

        except httpx.TimeoutException:
            return {"success": False, "error": "VL 调用超时"}

        except Exception as e:
            return {"success": False, "error": f"调用失败: {e}"}


# ==================== 标注图 ====================

def _annotate_image(
    pil_img: Image.Image,
    verified: List[Dict[str, Any]],
    max_annotations: int = 6,
) -> str:
    """
    在图片上标注识别到的星座。
    返回 base64 PNG。
    """
    from PIL import ImageDraw, ImageFont

    img = pil_img.convert("RGB").copy()
    draw = ImageDraw.Draw(img, "RGBA")

    w, h = img.size

    try:
        font_size = max(16, int(min(w, h) * 0.035))
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    line_width = max(2, int(min(w, h) * 0.004))

    for item in verified[:max_annotations]:
        bbox = item.get("bbox") or []

        if len(bbox) == 4:
            x1, y1, x2, y2 = bbox
        else:
            pos = item.get("position", "不确定")
            x1, y1, x2, y2 = _POSITION_TO_BOX.get(pos, _POSITION_TO_BOX["不确定"])

        px1 = int(x1 * w)
        py1 = int(y1 * h)
        px2 = int(x2 * w)
        py2 = int(y2 * h)

        draw.rectangle(
            [px1, py1, px2, py2],
            outline=(0, 255, 255, 255),
            width=line_width,
        )

        label = str(item.get("full") or item.get("abbr") or "")

        if not label:
            continue

        try:
            left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
            tw = right - left
            th = bottom - top
        except Exception:
            tw, th = draw.textsize(label, font=font)

        text_y = max(0, py1 - th - 10)

        draw.rectangle(
            [px1, text_y, px1 + tw + 12, text_y + th + 10],
            fill=(0, 0, 0, 180),
        )

        draw.text(
            (px1 + 6, text_y + 5),
            label,
            font=font,
            fill=(255, 255, 0, 255),
        )

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
        bbox = _clean_bbox(item.get("bbox"))

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

        out.append(
            {
                "abbr": abbr,
                "full": _ABBR_TO_FULL.get(abbr, abbr),
                "confidence": round(conf, 3),
                "position": position,
                "bbox": bbox,
                "reason": str(item.get("reason", "")),
                "bright_stars": _clean_bright_stars(item.get("bright_stars")),

                # 对外只给骨架星
                "matched_stars": skeleton_stars,
                "skeleton_stars": skeleton_stars,

                "star_count": len(skeleton_stars),
                "raw_star_count": len(matched_stars),
            }
        )

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
            {"b64": imgs["original_b64"], "mime": "image/png"},
            {"b64": imgs["adapted_b64"], "mime": "image/png"},
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
        estimated_season = _normalize_season(feat.get("estimated_season", ""))
        vl_items = feat.get("constellations") or []
        note = str(feat.get("note", ""))

        print(
            f"[vl] visible={visible}, season={estimated_season}, "
            f"items={[(i.get('name'), i.get('confidence')) for i in vl_items]}"
        )
        print(f"[vl] image_description: {image_description}")
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
                "vl_pattern_description": image_description or note,
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
            annotate_source = imgs.get("adapted_pil")

            if annotate_source is None:
                annotate_source = Image.open(BytesIO(img_bytes)).convert("RGB")

            annotated_image = _annotate_image(annotate_source, verified)
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
                "vl_pattern_description": image_description or note,
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
            "vl_pattern_description": image_description or note,
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