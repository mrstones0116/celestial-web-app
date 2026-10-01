"""OpenCV 星点检测：中值背景 + 残差阈值 + 连通域 + 亮星去重。"""
from io import BytesIO
from typing import Any, Dict, List

import cv2
import numpy as np
from PIL import Image, ImageOps

from .config import VisionConfig


def detect_stars(
    image_bytes: bytes,
    max_dim: int = VisionConfig.MAX_DIM,
    top_n: int = VisionConfig.TOP_N,
    edge_margin: float = VisionConfig.EDGE_MARGIN,
    detect_sigma: float = VisionConfig.DETECT_SIGMA,
) -> Dict[str, Any]:
    pil = Image.open(BytesIO(image_bytes))
    pil = ImageOps.exif_transpose(pil).convert("RGB")   # 修正手机竖拍
    original_size = pil.size

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
    mx = min(int(round(w * edge_margin)), max(0, w // 2 - 10))
    my = min(int(round(h * edge_margin)), max(0, h // 2 - 10))

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

    thresh = max(med + detect_sigma * sigma, 6.0)
    mask = (residual > thresh).astype(np.uint8)
    mask[~inner_mask] = 0

    roi = {"x0": mx, "y0": my, "x1": w - mx, "y1": h - my}

    base = {
        "stars": [], "pil": pil, "size": (w, h),
        "original_size": original_size,
        "threshold": float(thresh), "candidate_count": 0,
        "edge_margin": edge_margin, "roi": roi,
    }
    if int(mask.sum()) == 0:
        return base

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
        if all(
            (c["cx"] - a["cx"]) ** 2 + (c["cy"] - a["cy"]) ** 2 >= min_dist2
            for a in accepted
        ):
            accepted.append(c)
        if len(accepted) >= top_n:
            break

    stars = [{
        "rank": i + 1,
        "x": round(c["cx"] / w, 5), "y": round(c["cy"] / h, 5),
        "px": round(c["cx"], 2), "py": round(c["cy"], 2),
        "brightness": round(c["flux"], 3),
        "peak": round(c["peak"], 3), "area": c["area"],
        "cluster": -1,
    } for i, c in enumerate(accepted)]

    return {**base, "stars": stars, "candidate_count": len(candidates)}