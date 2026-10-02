"""星座骨架匹配：VL 只给星座名 + 主星名，后端用 HYG 星表做几何匹配。

流程：
1. VL 返回星座名 + 主星英文名
2. 从 HYG 查这些主星的 RA/Dec
3. 用 RANSAC + 三角形相似匹配，在检测出的星点中找到对应
4. 用匹配结果反算 bbox
"""
from typing import Any, Callable, Dict, List, Optional

import numpy as np


def _radec_to_vec(ra_deg: np.ndarray, dec_deg: np.ndarray) -> np.ndarray:
    ra = np.radians(ra_deg)
    dec = np.radians(dec_deg)
    return np.stack([
        np.cos(dec) * np.cos(ra),
        np.cos(dec) * np.sin(ra),
        np.sin(dec),
    ], axis=-1)


def _pairwise_angles(vecs: np.ndarray) -> np.ndarray:
    """NxN 角距矩阵（弧度），对角线设为 inf。"""
    cos = np.clip(vecs @ vecs.T, -1.0, 1.0)
    ang = np.arccos(cos)
    np.fill_diagonal(ang, np.inf)
    return ang


def _tri_shape(sides) -> Optional[np.ndarray]:
    s = np.asarray(sides, dtype=float)
    smax = s.max()
    if smax < 1e-9:
        return None
    return np.sort(s / smax)


def match_to_image(
    vl_constellations: List[Dict[str, Any]],
    detected_stars: List[Dict[str, Any]],
    hyg_lookup: Callable[[str], Optional[Dict[str, Any]]],
    image_w: int,
    image_h: int,
    ransac_iter: int = 8000,
    tol: float = 0.15,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    返回更新后的 constellations 列表，每个都带 bbox / main_stars（像素坐标）。
    匹配失败的星座 bbox 为空、match_ok=False。
    """
    # ---- 收集 VL 报告的主星名 ----
    star_names: List[str] = []
    for c in vl_constellations:
        for name in (c.get("main_stars") or []):
            if isinstance(name, str):
                n = name.strip()
                if n and n not in star_names:
                    star_names.append(n)

    # ---- HYG lookup ----
    sky_stars: List[Dict[str, Any]] = []
    for name in star_names:
        info = hyg_lookup(name)
        if not info:
            continue
        sky_stars.append({
            "name": name,
            "ra": float(info["ra"]),
            "dec": float(info["dec"]),
        })

    if len(sky_stars) < 3 or len(detected_stars) < 3:
        return _empty(vl_constellations)

    # ---- 天球角距 ----
    sky_vecs = _radec_to_vec(
        np.array([s["ra"] for s in sky_stars]),
        np.array([s["dec"] for s in sky_stars]),
    )
    sky_angles = _pairwise_angles(sky_vecs)

    # ---- 像素距离 ----
    px = np.array([s["px"] for s in detected_stars], dtype=float)
    py = np.array([s["py"] for s in detected_stars], dtype=float)
    dx = px[:, None] - px[None, :]
    dy = py[:, None] - py[None, :]
    px_dist = np.sqrt(dx ** 2 + dy ** 2)
    np.fill_diagonal(px_dist, np.inf)

    n_sky, n_px = len(sky_stars), len(px)
    rng = np.random.default_rng(seed)
    best = None  # (inliers, match_dict, scale)

    for _ in range(ransac_iter):
        sky_tri = rng.choice(n_sky, 3, replace=False)
        px_tri = rng.choice(n_px, 3, replace=False)

        s_sides = [
            sky_angles[sky_tri[0], sky_tri[1]],
            sky_angles[sky_tri[0], sky_tri[2]],
            sky_angles[sky_tri[1], sky_tri[2]],
        ]
        p_sides = [
            px_dist[px_tri[0], px_tri[1]],
            px_dist[px_tri[0], px_tri[2]],
            px_dist[px_tri[1], px_tri[2]],
        ]

        s_shape = _tri_shape(s_sides)
        p_shape = _tri_shape(p_sides)
        if s_shape is None or p_shape is None:
            continue
        if float(np.abs(s_shape - p_shape).sum()) > tol * 3:
            continue

        scale = max(p_sides) / max(s_sides)
        if not (10.0 < scale < 1e7):
            continue

        # 用这个 scale 检验所有模板星
        match: Dict[int, int] = {}
        tol_px = tol * scale * max(s_sides) * 3.0

        for i in range(n_sky):
            a = np.array([
                sky_angles[i, sky_tri[0]],
                sky_angles[i, sky_tri[1]],
                sky_angles[i, sky_tri[2]],
            ])
            if not np.isfinite(a).all() or (a < 1e-4).any():
                continue

            e = a * scale  # 期望像素距离

            best_j, best_err = -1, float("inf")
            for j in range(n_px):
                d = np.array([
                    px_dist[j, px_tri[0]],
                    px_dist[j, px_tri[1]],
                    px_dist[j, px_tri[2]],
                ])
                err = float(np.abs(d - e).sum())
                if err < best_err:
                    best_err, best_j = err, j
            if best_j >= 0 and best_err < tol_px:
                match[i] = best_j

        if best is None or len(match) > best[0]:
            best = (len(match), match, scale)

    if best is None or best[0] < 3:
        return _empty(vl_constellations)

    _, match_map, _ = best

    # ---- 每个星座反算 bbox ----
    result: List[Dict[str, Any]] = []
    for c in vl_constellations:
        c_names = set(c.get("main_stars") or [])

        matched_px: List[Dict[str, Any]] = []
        for i, sky in enumerate(sky_stars):
            if sky["name"] in c_names and i in match_map:
                j = match_map[i]
                matched_px.append({
                    "name": sky["name"],
                    "cn": "",
                    "x": float(px[j]),
                    "y": float(py[j]),
                })

        if len(matched_px) < 2:
            result.append({
                **c,
                "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0},
                "main_stars": matched_px,
                "match_ok": False,
                "match_count": len(matched_px),
            })
            continue

        xs = [s["x"] for s in matched_px]
        ys = [s["y"] for s in matched_px]
        pad = max(20.0, min(image_w, image_h) * 0.04)

        result.append({
            **c,
            "bbox": {
                "x0": max(0.0, min(xs) - pad),
                "y0": max(0.0, min(ys) - pad),
                "x1": min(float(image_w), max(xs) + pad),
                "y1": min(float(image_h), max(ys) + pad),
            },
            "main_stars": matched_px,
            "match_ok": True,
            "match_count": len(matched_px),
        })

    return result


def _empty(constellations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {**c,
         "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0},
         "main_stars": [],
         "match_ok": False,
         "match_count": 0}
        for c in constellations
    ]