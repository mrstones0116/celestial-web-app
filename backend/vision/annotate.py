"""图像标注：检测图 / VL 标注图 / 星座位置图。"""
import base64
from io import BytesIO
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_CLUSTER_PALETTE = [
    (255, 0, 0), (255, 140, 0), (255, 0, 180), (180, 0, 255),
    (255, 200, 0), (0, 200, 255), (0, 220, 100), (255, 100, 100),
]

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


def _to_b64(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def palette_color(cid: int):
    return _CLUSTER_PALETTE[cid % len(_CLUSTER_PALETTE)]


# ---------- 前端展示图（星点 + 簇色） ----------

def annotate_stars(
    pil: Image.Image,
    stars: List[Dict[str, Any]],
    clusters: Optional[List[Dict[str, Any]]] = None,
) -> str:
    img = pil.convert("RGB").copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    r_base = max(3.0, min(w, h) * 0.006)
    r_min, r_max = r_base * 0.6, r_base * 1.9

    fluxes = [max(float(s.get("brightness", 0.0)), 1e-6) for s in stars]
    radii = []
    if fluxes:
        log_vals = np.log(fluxes)
        lo, hi = float(log_vals.min()), float(log_vals.max())
        span = hi - lo
        for lv in log_vals:
            t = 0.0 if span < 1e-9 else (lv - lo) / span
            radii.append(r_min + t * (r_max - r_min))
    else:
        radii = [r_base] * len(stars)

    use_cluster_color = bool(clusters) and len(clusters) > 1
    for s, r in zip(stars, radii):
        px, py = float(s["px"]), float(s["py"])
        if use_cluster_color:
            color = palette_color(int(s.get("cluster", 0)))
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
    return _to_b64(img)


# ---------- VL 标注图（所有簇 + 主星 + C 编号） ----------

def annotate_clusters_for_vl(
    pil: Image.Image,
    clusters: List[Dict[str, Any]],
) -> str:
    img = pil.convert("RGB").copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    r_base = max(4.0, min(w, h) * 0.007)
    font = _load_font(max(16, int(min(w, h) * 0.022)))

    for c in clusters:
        cid = c["id"]
        color = palette_color(cid)
        main = c["main_star"]

        for s in c["stars"]:
            px, py = float(s["px"]), float(s["py"])
            r = r_base * 0.75
            draw.ellipse(
                [px - r, py - r, px + r, py + r],
                fill=(*color, 255),
                outline=(max(0, color[0] - 80), max(0, color[1] - 80),
                         max(0, color[2] - 80), 255),
                width=1,
            )

        mx, my = float(main["px"]), float(main["py"])
        R = r_base * 2.2
        draw.ellipse(
            [mx - R, my - R, mx + R, my + R],
            outline=(*color, 255),
            width=max(2, int(r_base * 0.8)),
        )
        draw.ellipse(
            [mx - r_base * 0.6, my - r_base * 0.6,
             mx + r_base * 0.6, my + r_base * 0.6],
            fill=(255, 255, 255, 255),
        )

        try:
            label = f"C{cid}"
            l, t, rr, b = draw.textbbox((0, 0), label, font=font)
            tw, th = rr - l, b - t
            tx, ty = mx + R + 4, my - th / 2
            if tx + tw + 6 > w:
                tx = mx - R - tw - 10
            tx = max(2, tx)
            ty = max(2, min(ty, h - th - 4))
            draw.rectangle(
                [tx - 3, ty - 2, tx + tw + 3, ty + th + 2],
                fill=(0, 0, 0, 195),
            )
            draw.text((tx, ty), label, font=font, fill=(*color, 255))
        except Exception:
            pass

    return _to_b64(img)


# ---------- 星座位置标注图（VL 结果写回图像） ----------

def annotate_constellation_positions(
    pil: Image.Image,
    clusters: List[Dict[str, Any]],
) -> str:
    img = pil.convert("RGB").copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    r_base = max(4.0, min(w, h) * 0.007)
    font_label = _load_font(max(18, int(min(w, h) * 0.024)))
    font_sub = _load_font(max(13, int(min(w, h) * 0.017)))

    for c in clusters:
        cid = c["id"]
        color = palette_color(cid)
        main = c["main_star"]
        mx, my = float(main["px"]), float(main["py"])

        for s in c["stars"]:
            px, py = float(s["px"]), float(s["py"])
            r = r_base * 0.6
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(*color, 185))

        R = r_base * 2.4
        draw.ellipse(
            [mx - R, my - R, mx + R, my + R],
            outline=(*color, 255), width=max(2, int(r_base * 0.9)),
        )
        draw.ellipse(
            [mx - r_base * 0.55, my - r_base * 0.55,
             mx + r_base * 0.55, my + r_base * 0.55],
            fill=(255, 255, 255, 255),
        )

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
            line1, line2 = f"C{cid}: ?", "VL 未判定"

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
        tx = max(2, tx)
        ty = max(2, min(ty, h - box_h - 2))

        draw.rectangle(
            [tx - 4, ty - 3, tx + box_w, ty + box_h],
            fill=(0, 0, 0, 205), outline=(*color, 255), width=2,
        )
        draw.text((tx + 3, ty + 1), line1, font=font_label, fill=(*color, 255))
        draw.text((tx + 3, ty + th1 + 5), line2, font=font_sub,
                  fill=(235, 235, 235, 255))

    return _to_b64(img)


# ---------- VL 输入图（原图 / 提亮 / 反相） ----------

def prepare_versions(pil: Image.Image) -> List[Dict[str, str]]:
    rgb = np.asarray(pil.convert("RGB"), dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)

    p_low, p_high = np.percentile(gray, [0.5, 99.5])
    if p_high - p_low < 1.0:
        p_high = p_low + 1.0
    stretch = np.clip((gray - p_low) / (p_high - p_low), 0.0, 1.0)
    bright_arr = (np.power(stretch, 0.5) * 255.0).astype(np.uint8)

    bright = Image.fromarray(cv2.cvtColor(bright_arr, cv2.COLOR_GRAY2RGB))
    inverted = Image.fromarray(cv2.cvtColor(255 - bright_arr, cv2.COLOR_GRAY2RGB))

    return [
        {"b64": _to_b64(pil.convert("RGB")), "mime": "image/png", "label": "原图"},
        {"b64": _to_b64(bright), "mime": "image/png", "label": "提亮图"},
        {"b64": _to_b64(inverted), "mime": "image/png", "label": "反相图"},
    ]