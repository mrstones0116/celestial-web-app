"""
三角形匹配模块 —— 将照片星点与 HYG 星表匹配
核心原理：三角形三边比例对旋转 / 缩放不变
"""
import numpy as np
from itertools import combinations
from typing import List, Dict, Optional


class StarPatternMatcher:
    """
    用法：
        matcher = StarPatternMatcher(catalog_stars)   # 传入 loader.get_stars()
        result  = matcher.match(detected_stars)
    """

    # ---------- 构造 ----------
    def __init__(self, catalog_stars: List[Dict], max_mag: float = 3.0):
        """
        catalog_stars : loader.get_stars() 返回的列表
        max_mag       : 只取亮于该星等的星做索引
        """
        self.catalog = sorted(
            [s for s in catalog_stars if s.get("mag") is not None and s["mag"] <= max_mag],
            key=lambda s: s["mag"],
        )
        # 限制索引规模（最亮 60 颗 → C(60,3)=34220 个三角形，可控）
        self.catalog = self.catalog[:60]
        self._build_index()

    # ---------- 预计算星表三角形 ----------
    def _build_index(self):
        n = len(self.catalog)
        ratios, star_triples = [], []

        for i, j, k in combinations(range(n), 3):
            s1, s2, s3 = self.catalog[i], self.catalog[j], self.catalog[k]
            d12 = self._ang_dist(s1, s2)
            d13 = self._ang_dist(s1, s3)
            d23 = self._ang_dist(s2, s3)
            sides = sorted([d12, d13, d23])

            if sides[0] < 1.0 or sides[2] < 1e-6:   # 跳过退化 / 过密三角形
                continue
            ratios.append([s / sides[2] for s in sides])
            star_triples.append((s1, s2, s3))

        self._tri_ratios = np.array(ratios, dtype=np.float64)   # (M, 3)
        self._tri_stars  = star_triples                          # M 个 (star,star,star)

    @staticmethod
    def _ang_dist(a: Dict, b: Dict) -> float:
        """两星角距离（度）"""
        ra1, dec1 = np.radians(a["ra_hours"] * 15.0), np.radians(a["dec"])
        ra2, dec2 = np.radians(b["ra_hours"] * 15.0), np.radians(b["dec"])
        cosd = (np.sin(dec1) * np.sin(dec2)
                + np.cos(dec1) * np.cos(dec2) * np.cos(ra1 - ra2))
        return float(np.degrees(np.arccos(np.clip(cosd, -1, 1))))

    # ---------- 匹配入口 ----------
    def match(
        self,
        detected: List[Dict],
        top_n: int = 8,
        tolerance: float = 0.10,
    ) -> Dict:
        """
        detected : detect_stars() 的输出
        返回     : { matched_stars, constellations, confidence, ... }
        """
        if len(detected) < 3:
            return self._empty_result(len(detected))

        top = detected[:top_n]

        # 投票表：每个检测星点 → { 星名: 票数 }
        votes: List[Dict[str, int]] = [{} for _ in range(len(top))]
        tri_matched = 0
        tri_total   = 0

        for ci, cj, ck in combinations(range(len(top)), 3):
            r = self._pixel_ratio(top[ci], top[cj], top[ck])
            if r is None:
                continue
            tri_total += 1

            # ---- NumPy 向量化：一次算出与所有星表三角形的差异 ----
            diffs = np.abs(self._tri_ratios - r).sum(axis=1)   # (M,)
            best  = int(np.argmin(diffs))
            if diffs[best] > tolerance:
                continue
            tri_matched += 1

            # ---- 投票 ----
            cat_triple = self._tri_stars[best]
            det_pts    = [top[ci], top[cj], top[ck]]

            # 按边长排序建立顶点对应
            det_order = self._sort_vertices_by_side(det_pts)
            cat_order = self._sort_catalog_by_side(cat_triple)

            for d_idx, c_star in zip(det_order, cat_order):
                name = c_star.get("name") or f"HIP{c_star.get('id','?')}"
                votes[d_idx][name] = votes[d_idx].get(name, 0) + 1

        # ---- 汇总投票 → 最终匹配 ----
        matched = []
        for i, vd in enumerate(votes):
            if not vd:
                continue
            best_name  = max(vd, key=vd.get)
            best_votes = vd[best_name]
            cat = next((s for s in self.catalog if (s.get("name") or "") == best_name), None)
            if cat is None:
                continue
            matched.append({
                "px": top[i]["x"], "py": top[i]["y"],
                "name": best_name,
                "ra_hours": cat.get("ra_hours"),
                "dec": cat.get("dec"),
                "mag": cat.get("mag"),
                "constellation": cat.get("constellation"),
                "spect": cat.get("spect"),
                "dist_ly": cat.get("dist_ly"),
                "votes": best_votes,
            })

        constellations = sorted({m["constellation"] for m in matched if m["constellation"]})
        confidence = tri_matched / tri_total if tri_total else 0.0

        return {
            "matched_stars": matched,
            "constellations": constellations,
            "confidence": round(confidence, 3),
            "total_detected": len(detected),
            "total_matched": len(matched),
        }

    # ---------- 工具 ----------
    @staticmethod
    def _pixel_ratio(p1, p2, p3):
        d12 = np.hypot(p1["x"]-p2["x"], p1["y"]-p2["y"])
        d13 = np.hypot(p1["x"]-p3["x"], p1["y"]-p3["y"])
        d23 = np.hypot(p2["x"]-p3["x"], p2["y"]-p3["y"])
        sides = sorted([d12, d13, d23])
        if sides[2] < 8 or sides[0] < 3:
            return None
        return np.array([s / sides[2] for s in sides])

    @staticmethod
    def _sort_vertices_by_side(pts):
        """返回按对边长度升序的顶点索引"""
        d01 = np.hypot(pts[0]["x"]-pts[1]["x"], pts[0]["y"]-pts[1]["y"])
        d02 = np.hypot(pts[0]["x"]-pts[2]["x"], pts[0]["y"]-pts[2]["y"])
        d12 = np.hypot(pts[1]["x"]-pts[2]["x"], pts[1]["y"]-pts[2]["y"])
        # 顶点0 对边 d12，顶点1 对边 d02，顶点2 对边 d01
        order = sorted([0, 1, 2], key=lambda v: [d12, d02, d01][v])
        return order

    @staticmethod
    def _sort_catalog_by_side(triple):
        s1, s2, s3 = triple
        d12 = StarPatternMatcher._ang_dist(s1, s2)
        d13 = StarPatternMatcher._ang_dist(s1, s3)
        d23 = StarPatternMatcher._ang_dist(s2, s3)
        order = sorted([0, 1, 2], key=lambda v: [d23, d13, d12][v])
        return [triple[o] for o in order]

    @staticmethod
    def _empty_result(n):
        return {
            "matched_stars": [], "constellations": [],
            "confidence": 0.0, "total_detected": n, "total_matched": 0,
        }