"""自适应 K-means 聚类 + 主星/边缘星/邻居计算。"""
from typing import Any, Dict, List, Optional

import numpy as np

from .config import VisionConfig


# ---------- K-means (K-means++ + 多初始化) ----------

def _kpp_init(X: np.ndarray, k: int, rng) -> np.ndarray:
    n = X.shape[0]
    centers = [X[int(rng.integers(n))]]
    for _ in range(k - 1):
        d2 = np.min([np.sum((X - c) ** 2, axis=1) for c in centers], axis=0)
        total = float(d2.sum())
        if total <= 0:
            centers.append(X[int(rng.integers(n))])
        else:
            centers.append(X[int(rng.choice(n, p=d2 / total))])
    return np.asarray(centers, dtype=float)


def _kmeans_once(X: np.ndarray, k: int, rng, n_iter: int):
    n = X.shape[0]
    centers = _kpp_init(X, k, rng)
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
    inertia = float(((X - centers[labels]) ** 2).sum())
    return labels, centers, inertia


def kmeans(X, k, n_init=10, n_iter=200, seed=42):
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        labels, centers, inertia = _kmeans_once(X, k, rng, n_iter)
        if best is None or inertia < best[2]:
            best = (labels, centers, inertia)
    return best[0], best[1]


def silhouette_score(X: np.ndarray, labels: np.ndarray) -> float:
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


# ---------- 单簇信息打包 ----------

def _build_cluster_payload(
    stars: List[Dict[str, Any]],
    labels: np.ndarray,
    k: int,
) -> Optional[List[Dict[str, Any]]]:
    clusters = []
    for cid in range(k):
        idx = [int(i) for i in np.where(labels == cid)[0]]
        if not idx:
            return None
        members = [stars[i] for i in idx]

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
            weight = (
                VisionConfig.WEIGHT_BRIGHTNESS * b_norm
                + VisionConfig.WEIGHT_DISTANCE * d_norm
            )
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
        nbrs = [
            {
                "cluster_id": o["id"],
                "center_x": o["center_x"],
                "center_y": o["center_y"],
                "star_count": o["star_count"],
                "distance": round(
                    float(np.hypot(o["center_x"] - cx, o["center_y"] - cy)), 2
                ),
            }
            for o in clusters if o["id"] != c["id"]
        ]
        nbrs.sort(key=lambda x: x["distance"])
        c["neighbors"] = nbrs

    return clusters


# ---------- 自适应 K ----------

def cluster_stars(
    stars: List[Dict[str, Any]],
    forced_k: Optional[int] = None,
    min_k: int = VisionConfig.MIN_K,
    max_k: int = VisionConfig.MAX_K,
    min_stars_per_cluster: int = VisionConfig.CLUSTER_MIN_STARS,
) -> List[Dict[str, Any]]:
    """
    返回按 silhouette 降序（同分优先小 K）的候选结果列表。
    调用方取 [0] 即为最佳。空列表代表聚类失败。
    """
    n = len(stars)
    if n == 0:
        return []

    X = np.asarray([[s["px"], s["py"]] for s in stars], dtype=float)

    if forced_k is not None and forced_k >= 2:
        k_candidates = [int(forced_k)]
    else:
        upper = min(int(max_k), n // max(1, min_stars_per_cluster))
        if upper < min_k:
            return []
        k_candidates = list(range(min_k, upper + 1))

    results: List[Dict[str, Any]] = []
    for k in k_candidates:
        if n < k * min_stars_per_cluster:
            continue

        labels, _ = kmeans(
            X, k,
            n_init=VisionConfig.KMEANS_N_INIT,
            n_iter=VisionConfig.KMEANS_MAX_ITER,
        )
        if len(np.unique(labels)) < k:
            continue
        counts = np.bincount(labels, minlength=k)
        if int(counts.min()) < min_stars_per_cluster:
            continue

        clusters = _build_cluster_payload(stars, labels, k)
        if clusters is None:
            continue

        score = silhouette_score(X, labels)

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

    # silhouette 优先，其次 K 小者优先（避免过分割）
    results.sort(key=lambda r: (-r["score"], r["k"]))
    return results