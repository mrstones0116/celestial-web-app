"""Plate solving：RANSAC + ICP 拟合 HYG 星表到图像亮点的相似变换。

关键：
- 相似变换 b = w·a + t（复数形式）共 4 自由度，2 对点闭式解
- **一对一内点匹配**：每个图像亮点最多被一颗模板星占用
- **scale 先验**：由模板角跨度和图像对角线约束
- **LO-RANSAC**：局部优化，2 点解出后立刻用内点 LS 精修
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .projection import gnomonic_project, _radec_to_xyz


# ---------- 复数相似变换 ----------

def _similarity_from_two_points(
    a1: Tuple[float, float], a2: Tuple[float, float],
    b1: Tuple[float, float], b2: Tuple[float, float],
) -> Optional[Tuple[complex, complex]]:
    za = complex(a1[0] - a2[0], a1[1] - a2[1])
    zb = complex(b1[0] - b2[0], b1[1] - b2[1])
    if abs(za) < 1e-12:
        return None
    w = zb / za
    t = complex(b1[0], b1[1]) - w * complex(a1[0], a1[1])
    return w, t


def _apply(A: np.ndarray, w: complex, t: complex) -> np.ndarray:
    za = A[:, 0] + 1j * A[:, 1]
    zb = w * za + t
    return np.stack([zb.real, zb.imag], axis=1)


def _fit_ls(A: np.ndarray, B: np.ndarray) -> Optional[Tuple[complex, complex]]:
    if A.shape[0] < 2 or A.shape[0] != B.shape[0]:
        return None
    za = A[:, 0] + 1j * A[:, 1]
    zb = B[:, 0] + 1j * B[:, 1]
    a_mean = za.mean()
    b_mean = zb.mean()
    da = za - a_mean
    db = zb - b_mean
    denom = float((da * np.conj(da)).sum().real)
    if denom < 1e-12:
        return None
    w = complex((db * np.conj(da)).sum() / denom)
    t = b_mean - w * a_mean
    return w, t


# ---------- 一对一内点匹配 ----------

def _match_one_to_one(
    A_proj: np.ndarray,
    B: np.ndarray,
    eps2: float,
) -> List[Tuple[int, int]]:
    """
    每个图像点最多匹配一个模板点，每个模板点最多匹配一个图像点。
    贪心：从最近的对开始占用。
    """
    d2 = ((A_proj[:, None, :] - B[None, :, :]) ** 2).sum(axis=2)
    nearest_j = d2.argmin(axis=1)
    min_d2 = d2[np.arange(A_proj.shape[0]), nearest_j]

    # 快速路径：如果一个都没命中，直接返回
    if int((min_d2 < eps2).sum()) == 0:
        return []

    order = np.argsort(min_d2)
    used_b = set()
    pairs: List[Tuple[int, int]] = []
    for i in order:
        if min_d2[i] >= eps2:
            break
        j = int(nearest_j[i])
        if j in used_b:
            continue
        used_b.add(j)
        pairs.append((int(i), j))
    return pairs


# ---------- 主入口 ----------

def solve(
    template_radec: np.ndarray,          # (N, 2) [ra_deg, dec_deg]
    image_points: np.ndarray,            # (M, 2) [px, py]，按亮度降序
    template_mags: Optional[np.ndarray] = None,
    image_size: Optional[Tuple[int, int]] = None,   # (w, h)
    ra0: Optional[float] = None,
    dec0: Optional[float] = None,
    ransac_iter: int = 6000,
    eps_px: float = 6.0,
    min_inliers: int = 3,
    icp_iter: int = 10,
    seed: int = 42,
) -> Optional[Dict[str, Any]]:
    """
    返回:
        {
          "w": complex, "t": complex,
          "ra0": float, "dec0": float,
          "inliers": int,
          "scale_px_per_rad": float,
          "matched_pairs": [(i_template, j_image), ...],
          "projector": callable(ra, dec) -> (px, py) or None,
        }
    或 None。
    """
    N = template_radec.shape[0]
    M = image_points.shape[0]
    if N < 2 or M < 2:
        return None

    # ---- 1) 选投影中心 ----
    if ra0 is None or dec0 is None:
        xyz_all = _radec_to_xyz(template_radec[:, 0], template_radec[:, 1])
        v0 = xyz_all.mean(axis=0)
        n0 = float(np.linalg.norm(v0))
        if n0 < 1e-9:
            return None
        v0 = v0 / n0
        ra0 = float(np.degrees(np.arctan2(v0[1], v0[0])) % 360.0)
        dec0 = float(np.degrees(np.arcsin(np.clip(v0[2], -1.0, 1.0))))

    # ---- 2) 模板角跨度（用于 scale 先验） ----
    xyz_all = _radec_to_xyz(template_radec[:, 0], template_radec[:, 1])
    cos_mat = xyz_all @ xyz_all.T
    span_rad = float(np.arccos(np.clip(cos_mat.min(), -1.0, 1.0)))
    if span_rad < np.radians(3.0):
        span_rad = np.radians(3.0)

    # ---- 3) 图像跨度（对角线） ----
    if image_size is not None:
        w_img, h_img = float(image_size[0]), float(image_size[1])
    else:
        # 从图像点范围估算
        w_img = float(image_points[:, 0].max() - image_points[:, 0].min()) + 1.0
        h_img = float(image_points[:, 1].max() - image_points[:, 1].min()) + 1.0
    diag_px = float(np.hypot(w_img, h_img))
    if diag_px < 1.0:
        diag_px = 1.0

    # ---- 4) 合理 scale 范围 ----
    # 假设模板角跨度对应图像上 0.15~3 倍对角线
    s_nominal = diag_px / span_rad
    s_min = 0.15 * s_nominal
    s_max = 3.0 * s_nominal

    # ---- 5) 投影到切平面 ----
    xi, eta, valid = gnomonic_project(
        template_radec[:, 0], template_radec[:, 1], ra0, dec0,
    )
    if int(valid.sum()) < 2:
        return None

    A_all = np.stack([xi[valid], eta[valid]], axis=1)  # (Na, 2)
    Na = A_all.shape[0]

    # ---- 6) 用最亮的子集做 RANSAC ----
    if template_mags is not None and len(template_mags) >= N:
        mags_v = np.asarray(template_mags)[valid]
        order = np.argsort(mags_v)
        n_bright = min(Na, max(6, Na // 2))
        A_ransac = A_all[order[:n_bright]]
    else:
        A_ransac = A_all

    n_br = min(M, 30)
    B_ransac = image_points[:n_br]

    # ---- 7) RANSAC + LO（local optimization） ----
    rng = np.random.default_rng(seed)
    n_ar = A_ransac.shape[0]
    eps2 = eps_px * eps_px

    # 图像对点的最小间距（相对图像对角线），避免 scale 抖动
    b_min_dist2 = (0.01 * diag_px) ** 2

    best: Optional[Tuple[int, complex, complex]] = None

    for _ in range(ransac_iter):
        i1, i2 = rng.choice(n_ar, 2, replace=False)
        j1, j2 = rng.choice(n_br, 2, replace=False)

        # 图像对点太近 → scale 不稳
        d_b2 = (
            (B_ransac[j1, 0] - B_ransac[j2, 0]) ** 2
            + (B_ransac[j1, 1] - B_ransac[j2, 1]) ** 2
        )
        if d_b2 < b_min_dist2:
            continue

        res = _similarity_from_two_points(
            A_ransac[i1], A_ransac[i2],
            B_ransac[j1], B_ransac[j2],
        )
        if res is None:
            continue
        w, t = res

        s = abs(w)
        if s < s_min or s > s_max:
            continue

        # 一对一内点计数
        A_proj = _apply(A_ransac, w, t)
        pairs = _match_one_to_one(A_proj, B_ransac, eps2)
        n_in = len(pairs)
        if n_in < 3:
            continue

        # LO：用内点做一次最小二乘，再重新计数
        ia = np.array([p[0] for p in pairs], dtype=int)
        ib = np.array([p[1] for p in pairs], dtype=int)
        res2 = _fit_ls(A_ransac[ia], B_ransac[ib])
        if res2 is not None:
            w2, t2 = res2
            if s_min <= abs(w2) <= s_max:
                A_proj2 = _apply(A_ransac, w2, t2)
                pairs2 = _match_one_to_one(A_proj2, B_ransac, eps2)
                if len(pairs2) > n_in:
                    w, t, n_in = w2, t2, len(pairs2)

        if best is None or n_in > best[0]:
            best = (n_in, w, t)

    if best is None or best[0] < min_inliers:
        return None

    # ---- 8) ICP 精修（全量模板 + 全量图像点） ----
    _, w, t = best
    for _ in range(icp_iter):
        A_proj = _apply(A_all, w, t)
        pairs = _match_one_to_one(A_proj, image_points, eps2)
        if len(pairs) < 2:
            break
        ia = np.array([p[0] for p in pairs], dtype=int)
        ib = np.array([p[1] for p in pairs], dtype=int)
        res = _fit_ls(A_all[ia], image_points[ib])
        if res is None:
            break
        w_new, t_new = res
        if abs(w_new - w) < 1e-7 and abs(t_new - t) < 1e-3:
            w, t = w_new, t_new
            break
        w, t = w_new, t_new

    # ---- 9) 最终统计 ----
    A_proj = _apply(A_all, w, t)
    final_pairs = _match_one_to_one(A_proj, image_points, eps2)
    n_final = len(final_pairs)
    if n_final < min_inliers:
        return None

    # 把 valid 索引映射回原始模板索引
    valid_idx = np.where(valid)[0]
    template_indices = valid_idx[[p[0] for p in final_pairs]]
    image_indices = [p[1] for p in final_pairs]

    def projector(ra_deg: float, dec_deg: float):
        xi_, eta_, ok_ = gnomonic_project(
            np.array([ra_deg]), np.array([dec_deg]), ra0, dec0,
        )
        if not bool(ok_[0]):
            return None
        za = complex(float(xi_[0]), float(eta_[0]))
        zb = w * za + t
        return float(zb.real), float(zb.imag)

    return {
        "w": w,
        "t": t,
        "ra0": float(ra0),
        "dec0": float(dec0),
        "inliers": n_final,
        "scale_px_per_rad": float(abs(w)),
        "matched_pairs": [
            (int(template_indices[k]), int(image_indices[k]))
            for k in range(len(template_indices))
        ],
        "projector": projector,
    }