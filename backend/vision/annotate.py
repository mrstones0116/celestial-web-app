"""图像标注：星点图 / 标准投影参考图 / VL 输入版本。"""
import base64
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from .projection import _radec_to_xyz, gnomonic_project

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


# ============================================================
# 前端展示图：星点
# ============================================================

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
    radii: List[float] = []
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


# ============================================================
# VL 输入版本：原图 / 提亮图 / 反相图
# ============================================================

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


# ============================================================
# 骨架端点 → HYG 最近邻
# ============================================================

def _collect_skeleton_endpoints(catalog, abbr: str) -> List[Tuple[float, float]]:
    """从 constellations.lines.json 里提取该星座骨架线的所有端点，去重。"""
    seen = set()
    pts: List[Tuple[float, float]] = []
    for line in catalog.get_lines(abbr):
        for ra, dec in line:
            key = (round(float(ra), 3), round(float(dec), 3))
            if key in seen:
                continue
            seen.add(key)
            pts.append((float(ra), float(dec)))
    return pts


def _match_endpoints_to_hyg(
    endpoints: List[Tuple[float, float]],
    members: List[Dict[str, Any]],
    max_ang_deg: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    每个骨架端点，在 HYG 成员星里找角距最近的星（< max_ang_deg）。
    返回匹配到的 HYG 星列表（去重，保留最亮信息）。
    """
    if not endpoints or not members:
        return []

    ra_arr = np.array([m["ra"] for m in members], dtype=float)
    dec_arr = np.array([m["dec"] for m in members], dtype=float)
    member_xyz = _radec_to_xyz(ra_arr, dec_arr)

    matched: List[Dict[str, Any]] = []
    used_idx = set()

    for ra, dec in endpoints:
        v = _radec_to_xyz(np.array([ra]), np.array([dec]))[0]
        cos_ang = np.clip(member_xyz @ v, -1.0, 1.0)
        ang = np.degrees(np.arccos(cos_ang))
        idx = int(np.argmin(ang))
        if ang[idx] > max_ang_deg:
            continue
        if idx in used_idx:
            continue
        used_idx.add(idx)
        matched.append(members[idx])

    return matched


# ============================================================
# 标准投影参考图：以成员星质心为中心，用 gnomonic 投影画 HYG 骨架
# ============================================================

def render_constellation_reference(
    base_image: Image.Image,
    constellations: List[Dict[str, Any]],
    catalog,
    fov_scale: float = 1.6,
    dim_base: float = 0.55,
    endpoint_match_deg: float = 0.5,
) -> str:
    """
    在原图之上，用标准 gnomonic 投影绘制 VL 识别出的星座骨架。

    - 投影中心 = 所有骨架端点的向量质心
    - FOV 自动覆盖所有骨架端点（× fov_scale）
    - 骨架线 = constellations.lines.json
    - **只画骨架端点上的星**（用 HYG 最近邻坐标 + 名字）
    - 底层原图变暗
    """
    img = base_image.convert("RGB").copy()
    if dim_base < 1.0:
        img = ImageEnhance.Brightness(img).enhance(dim_base)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    # 1) 收集每个星座的骨架端点 + HYG 匹配星
    per_abbr_lines: Dict[str, List[List[List[float]]]] = {}
    per_abbr_stars: Dict[str, List[Dict[str, Any]]] = {}
    all_ra: List[float] = []
    all_dec: List[float] = []

    for c in constellations:
        abbr = c.get("abbr")
        if not abbr:
            continue
        lines = catalog.get_lines(abbr)
        if not lines:
            continue
        per_abbr_lines[abbr] = lines

        endpoints = _collect_skeleton_endpoints(catalog, abbr)
        members = catalog.get_members(abbr)
        matched = _match_endpoints_to_hyg(
            endpoints, members, max_ang_deg=endpoint_match_deg,
        )
        per_abbr_stars[abbr] = matched

        # 用端点坐标（不是成员星）决定投影范围和中心
        for ra, dec in endpoints:
            all_ra.append(ra)
            all_dec.append(dec)

    if not all_ra:
        return _to_b64(img)

    # 2) 向量质心 → 投影中心
    ra_arr = np.array(all_ra, dtype=float)
    dec_arr = np.array(all_dec, dtype=float)
    xyz = _radec_to_xyz(ra_arr, dec_arr)
    v0 = xyz.mean(axis=0)
    n0 = float(np.linalg.norm(v0))
    if n0 < 1e-9:
        return _to_b64(img)
    v0 = v0 / n0
    dec0 = float(np.degrees(np.arcsin(np.clip(v0[2], -1.0, 1.0))))
    ra0 = float(np.degrees(np.arctan2(v0[1], v0[0])) % 360.0)

    # 3) 最大角半径
    cos_ang = np.clip(xyz @ v0, -1.0, 1.0)
    ang_deg = np.degrees(np.arccos(cos_ang))
    max_ang = float(ang_deg.max())
    if max_ang < 1e-3:
        max_ang = 1.0

    # 4) FOV
    fov = float(np.clip(max_ang * 2.0 * fov_scale, 5.0, 150.0))

    # 5) 半宽/半高角度
    aspect = w / max(h, 1)
    if aspect >= 1.0:
        half_w_deg = fov / 2.0
        half_h_deg = half_w_deg / aspect
    else:
        half_h_deg = fov / 2.0
        half_w_deg = half_h_deg * aspect

    tw = max(np.tan(np.radians(half_w_deg)), 1e-9)
    th = max(np.tan(np.radians(half_h_deg)), 1e-9)

    def project(ra_deg: float, dec_deg: float) -> Optional[Tuple[float, float]]:
        xi, eta, valid = gnomonic_project(
            np.array([ra_deg]), np.array([dec_deg]), ra0, dec0,
        )
        if not bool(valid[0]):
            return None
        # 天球从内向外看，RA 增加方向在图上向左 → 镜像翻转
        px = w / 2.0 - (float(xi[0]) / tw) * (w / 2.0)
        py = h / 2.0 - (float(eta[0]) / th) * (h / 2.0)
        return px, py

    # 6) 绘制
    r_base = max(3.0, min(w, h) * 0.006)
    font_label = _load_font(max(16, int(min(w, h) * 0.024)))
    font_small = _load_font(max(11, int(min(w, h) * 0.016)))

    for i, c in enumerate(constellations):
        abbr = c.get("abbr")
        if abbr not in per_abbr_lines:
            continue
        color = _CLUSTER_PALETTE[i % len(_CLUSTER_PALETTE)]

        # ---- 骨架线 ----
        for line in per_abbr_lines[abbr]:
            seg: List[Tuple[float, float]] = []
            for ra, dec in line:
                p = project(ra, dec)
                inside = False
                if p is not None:
                    px, py = p
                    inside = (-w <= px <= 2 * w) and (-h <= py <= 2 * h)
                if inside and p is not None:
                    seg.append(p)
                else:
                    if len(seg) >= 2:
                        draw.line(seg, fill=(*color, 230),
                                  width=max(2, int(r_base * 0.8)),
                                  joint="curve")
                    seg = []
            if len(seg) >= 2:
                draw.line(seg, fill=(*color, 230),
                          width=max(2, int(r_base * 0.8)),
                          joint="curve")

        # ---- 只画骨架端点上的星 ----
        for m in per_abbr_stars.get(abbr, []):
            p = project(m["ra"], m["dec"])
            if p is None:
                continue
            px, py = p
            if not (-r_base * 6 <= px <= w + r_base * 6):
                continue
            if not (-r_base * 6 <= py <= h + r_base * 6):
                continue

            mag = float(m["mag"])
            if mag < 2.5:
                rr = r_base * 1.8
            elif mag < 3.5:
                rr = r_base * 1.2
            else:
                rr = r_base * 0.9

            draw.ellipse(
                [px - rr, py - rr, px + rr, py + rr],
                fill=(*color, 240),
                outline=(255, 255, 255, 230),
                width=1,
            )

            nm = (
                m.get("display_name")
                or m.get("name")
                or m.get("bf")
                or ""
            ).strip()
            
            if nm:
                try:
                    tx, ty = px + rr + 3, py - 9
                    bb = draw.textbbox((tx, ty), nm, font=font_small)
                    draw.rectangle(
                        [bb[0] - 2, bb[1] - 1, bb[2] + 2, bb[3] + 1],
                        fill=(0, 0, 0, 170),
                    )
                    draw.text((tx, ty), nm, font=font_small,
                              fill=(240, 240, 240, 240))
                except Exception:
                    pass

        # ---- 星座名（骨架端点质心处） ----
        cx_list: List[float] = []
        cy_list: List[float] = []
        for ra, dec in _collect_skeleton_endpoints(catalog, abbr):
            p = project(ra, dec)
            if p is None:
                continue
            px, py = p
            if 0 <= px < w and 0 <= py < h:
                cx_list.append(px)
                cy_list.append(py)
        if cx_list:
            cx = float(np.mean(cx_list))
            cy = float(np.mean(cy_list))
            cn = catalog.get_cn_name(abbr)
            label = f"{cn} ({abbr})" if cn else abbr
            try:
                bb = draw.textbbox((0, 0), label, font=font_label)
                tw2, th2 = bb[2] - bb[0], bb[3] - bb[1]
                tx = max(2, min(int(cx - tw2 / 2), w - tw2 - 4))
                ty = max(2, min(int(cy - th2 / 2), h - th2 - 4))
                draw.rectangle(
                    [tx - 4, ty - 3, tx + tw2 + 4, ty + th2 + 3],
                    fill=(0, 0, 0, 200),
                    outline=(*color, 255), width=2,
                )
                draw.text((tx, ty), label, font=font_label,
                          fill=(*color, 255))
            except Exception:
                pass

    # 角标
    info = (f"standard view  RA0={ra0:.2f}°  Dec0={dec0:.2f}°  "
            f"FOV={fov:.1f}°")
    try:
        bb = draw.textbbox((0, 0), info, font=font_small)
        tw3, th3 = bb[2] - bb[0], bb[3] - bb[1]
        draw.rectangle([6, 6, 6 + tw3 + 8, 6 + th3 + 6],
                       fill=(0, 0, 0, 180))
        draw.text((10, 9), info, font=font_small,
                  fill=(210, 210, 210, 230))
    except Exception:
        pass

    return _to_b64(img)