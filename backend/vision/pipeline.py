"""识星全流程编排：检测 → 聚类 → VL → 低置信度重判 → 标注。"""
import asyncio
import base64
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from .annotate import (
    annotate_clusters_for_vl,
    annotate_constellation_positions,
    annotate_stars,
    prepare_versions,
)
from .clustering import cluster_stars
from .config import DEBUG_DIR, VisionConfig
from .detection import detect_stars
from .vl import (
    VLClient,
    build_full_prompt,
    build_recheck_prompt,
    parse_vl_item,
)


class VisionPipeline:
    def __init__(self):
        self.vl = VLClient()

    # ---------- 状态 ----------

    def status(self) -> Dict[str, Any]:
        cfg = VisionConfig
        return {
            "engine": "opencv-local+adaptive-kmeans+vl",
            "configured": self.vl.configured,
            "model": self.vl.model,
            "hint": "已就绪" if self.vl.configured
                    else "未配置 MODELSCOPE_API_KEY / ZHIPU_API_KEY",
            "top_n_default": cfg.TOP_N,
            "max_dim": cfg.MAX_DIM,
            "max_upload_mb": cfg.MAX_UPLOAD_MB,
            "edge_margin": cfg.EDGE_MARGIN,
            "forced_k": cfg.FORCED_K,
            "min_k": cfg.MIN_K,
            "max_k": cfg.MAX_K,
            "min_stars_per_cluster": cfg.CLUSTER_MIN_STARS,
            "weight_brightness": cfg.WEIGHT_BRIGHTNESS,
            "weight_distance": cfg.WEIGHT_DISTANCE,
            "confidence_threshold": cfg.CONFIDENCE_THRESHOLD,
        }

    # ---------- 上传入口 ----------

    async def identify_upload(
        self,
        file: UploadFile,
        top_n: int = VisionConfig.TOP_N,
    ) -> Dict[str, Any]:
        try:
            data = await file.read()
        except Exception as e:
            return self._error(f"读取上传文件失败: {e}")

        print(f"📥 上传: {file.filename!r} size={len(data)}")

        if not data:
            return self._error("图片为空")
        if len(data) > VisionConfig.MAX_UPLOAD_BYTES:
            return self._error(f"图片过大（>{VisionConfig.MAX_UPLOAD_MB}MB）")

        return await self.identify_bytes(data, top_n=top_n)

    # ---------- 主流程 ----------

    async def identify_bytes(
        self,
        data: bytes,
        top_n: int = VisionConfig.TOP_N,
    ) -> Dict[str, Any]:

        # 1) 检测
        try:
            detection = await asyncio.to_thread(
                detect_stars, data, VisionConfig.MAX_DIM, top_n,
            )
        except Exception as e:
            import traceback; traceback.print_exc()
            return self._error(f"图像处理失败: {e}")

        stars = detection["stars"]
        pil = detection["pil"]
        w, h = detection["size"]
        ow, oh = detection["original_size"]
        print(f"🔎 候选 {detection['candidate_count']} 个, 保留 {len(stars)} 颗")

        # 2) 聚类（自适应 K）
        cluster_results: List[Dict[str, Any]] = []
        if len(stars) >= VisionConfig.MIN_K * VisionConfig.CLUSTER_MIN_STARS:
            try:
                cluster_results = await asyncio.to_thread(
                    cluster_stars, stars, VisionConfig.FORCED_K,
                )
            except Exception:
                import traceback; traceback.print_exc()

        if not cluster_results:
            return {
                "success": True,
                "identifiable": len(stars) > 0,
                "count": len(stars),
                "matched_count": len(stars),
                "detected_star_count": len(stars),
                "stars": stars,
                "detected_stars": [{"x": s["x"], "y": s["y"]} for s in stars],
                "clusters": [],
                "cluster_k": None,
                "cluster_score": None,
                "all_cluster_results": [],
                "vl_cluster_k": None,
                "vl_clusters": [],
                "vl_summary": None,
                "vl_sky_region": None,
                "vl_low_confidence_threshold": VisionConfig.CONFIDENCE_THRESHOLD,
                "vl_recheck": None,
                "image_width": w,
                "image_height": h,
                "original_width": ow,
                "original_height": oh,
                "threshold": detection["threshold"],
                "candidate_count": detection["candidate_count"],
                "edge_margin": detection["edge_margin"],
                "roi": detection["roi"],
                "annotated_image": "",
                "annotated_mime": "image/png",
                "source": "opencv-local+adaptive-kmeans+vl",
                "message": f"检测 {len(stars)} 颗星，但聚类失败",
            }

        chosen = cluster_results[0]
        chosen_k = chosen["k"]
        print(f"🧩 聚类: K={chosen_k} silhouette={chosen['score']}")

        # 3) 前端展示标注图
        try:
            chosen["annotated_image"] = await asyncio.to_thread(
                annotate_stars, pil, chosen["stars"], chosen["clusters"],
            )
            chosen["annotated_mime"] = "image/png"
        except Exception:
            import traceback; traceback.print_exc()
            chosen["annotated_image"] = ""
            chosen["annotated_mime"] = None

        # 4) VL 整图识别
        vl_summary: Optional[Dict[str, Any]] = None
        vl_recheck: Optional[Dict[str, Any]] = None

        if self.vl.configured:
            print(f"🤖 VL 整图判断：K={chosen_k}，共 {len(chosen['clusters'])} 个簇")
            try:
                base_versions = await asyncio.to_thread(prepare_versions, pil)
                vl_summary = await self._vl_identify(
                    pil, chosen["clusters"], base_versions,
                )
                for c in chosen["clusters"]:
                    vr = c.get("vl_result") or {}
                    if vr.get("success"):
                        print(f"   ✓ C{c['id']} → "
                              f"{vr.get('constellation') or vr.get('constellation_abbr')} "
                              f"({vr.get('confidence', 0):.2f})")
                    else:
                        print(f"   ✗ C{c['id']} → {vr.get('error')}")

                # 5) 低置信度重判
                if vl_summary and vl_summary.get("success"):
                    try:
                        vl_recheck = await self._vl_recheck(
                            pil, chosen["clusters"], base_versions,
                            VisionConfig.CONFIDENCE_THRESHOLD,
                        )
                        if vl_recheck.get("success") and vl_recheck.get("changed_ids"):
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
            for c in chosen["clusters"]:
                c["vl_result"] = {"success": False, "error": "未配置 VL API Key"}

        # 6) 回填 stars[i].cluster
        if len(chosen.get("stars", [])) == len(stars):
            for orig, marked in zip(stars, chosen["stars"]):
                orig["cluster"] = int(marked.get("cluster", -1))

        # 7) 调试图
        if VisionConfig.DEBUG_VISION:
            await asyncio.to_thread(self._save_debug, pil, chosen, chosen_k)

        # 8) 组装响应
        return self._build_response(
            stars, chosen, vl_summary, vl_recheck,
            detection, w, h, ow, oh,
        )

    # ---------- VL 步骤 ----------

    async def _vl_identify(
        self,
        pil,
        clusters: List[Dict[str, Any]],
        base_versions: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        if not self.vl.configured:
            for c in clusters:
                c["vl_result"] = {"success": False, "error": "未配置 VL API Key"}
            return {"success": False, "error": "未配置 VL API Key"}

        annotated = annotate_clusters_for_vl(pil, clusters)
        images = list(base_versions) + [
            {"b64": annotated, "mime": "image/png", "label": "聚类标注图"},
        ]
        prompt = build_full_prompt(clusters)

        res = await self.vl.chat_json(prompt, images)
        if not res.get("success"):
            for c in clusters:
                c["vl_result"] = {"success": False,
                                  "error": res.get("error", "整图调用失败")}
            return res

        data = res["data"]
        parsed = data.get("clusters") if isinstance(data, dict) else None
        if not isinstance(parsed, list):
            for c in clusters:
                c["vl_result"] = {"success": False, "error": "返回缺少 clusters 字段"}
            return {"success": False, "error": "返回缺少 clusters 字段"}

        by_id: Dict[int, Dict[str, Any]] = {}
        for item in parsed:
            pr = parse_vl_item(item)
            if pr is not None:
                by_id[pr[0]] = pr[1]

        for c in clusters:
            c["vl_result"] = by_id.get(c["id"], {
                "success": False, "error": "VL 未返回该簇的判断",
            })

        return {
            "success": True,
            "by_id": by_id,
            "summary": str(data.get("summary") or "").strip(),
            "sky_region": str(data.get("sky_region") or "").strip(),
            "raw": data,
        }

    async def _vl_recheck(
        self,
        pil,
        clusters: List[Dict[str, Any]],
        base_versions: List[Dict[str, str]],
        threshold: float,
    ) -> Dict[str, Any]:
        if not self.vl.configured:
            return {"success": False, "error": "未配置 VL API Key"}

        confirmed, low_conf = [], []
        for c in clusters:
            vr = c.get("vl_result") or {}
            if not vr.get("success"):
                low_conf.append(c)
                continue
            try:
                conf = float(vr.get("confidence") or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            (confirmed if conf >= threshold else low_conf).append(
                (c, vr) if conf >= threshold else c
            )

        if not low_conf:
            return {"success": True, "no_change": True, "changed_ids": [], "changes": []}
        if not confirmed:
            return {"success": True, "no_change": True, "changed_ids": [], "changes": [],
                    "skipped": "无高置信度锚点，跳过重新判断"}

        prompt = build_recheck_prompt(clusters, confirmed, low_conf, threshold)
        annotated = annotate_clusters_for_vl(pil, clusters)
        images = list(base_versions) + [
            {"b64": annotated, "mime": "image/png", "label": "聚类标注图"},
        ]

        print(f"🔁 VL 重新判断：低置信度 {len(low_conf)} 个"
              f"（<{threshold}），锚点 {len(confirmed)} 个 ...")
        res = await self.vl.chat_json(prompt, images)
        if not res.get("success"):
            return res

        data = res["data"]
        parsed = data.get("clusters") if isinstance(data, dict) else None
        if not isinstance(parsed, list):
            return {"success": False, "error": "重新判断返回缺少 clusters 字段"}

        low_ids = {int(c["id"]) for c in low_conf}
        updated: Dict[int, Dict[str, Any]] = {}
        for item in parsed:
            pr = parse_vl_item(item)
            if pr is not None and pr[0] in low_ids:
                updated[pr[0]] = pr[1]

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

    # ---------- 调试图 ----------

    def _save_debug(self, pil, chosen, chosen_k: int):
        try:
            DEBUG_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            pil.save(DEBUG_DIR / f"{ts}_input.png")

            if chosen.get("annotated_image"):
                (DEBUG_DIR / f"{ts}_k{chosen_k}_clusters.png").write_bytes(
                    base64.b64decode(chosen["annotated_image"])
                )
            try:
                const_b64 = annotate_constellation_positions(
                    pil, chosen["clusters"]
                )
                (DEBUG_DIR / f"{ts}_k{chosen_k}_constellations.png").write_bytes(
                    base64.b64decode(const_b64)
                )
                chosen["constellation_annotated_image"] = const_b64
                print(f"💾 调试图已保存: {ts}_k{chosen_k}_*.png")
            except Exception as e:
                print(f"⚠️ 生成星座位置标注图失败: {e}")
        except Exception as e:
            print(f"⚠️ 保存调试图失败: {e}")

    # ---------- 组装响应 ----------

    @staticmethod
    def _error(message: str) -> Dict[str, Any]:
        return {"success": False, "identifiable": False, "message": message}

    @staticmethod
    def _build_response(
        stars, chosen, vl_summary, vl_recheck,
        detection, w, h, ow, oh,
    ) -> Dict[str, Any]:
        clusters = chosen["clusters"]
        vl_ok = sum(1 for c in clusters
                    if (c.get("vl_result") or {}).get("success"))

        if vl_ok:
            msg = (f"检测 {len(stars)} 颗星，K={chosen['k']}；"
                   f"VL 成功判断 {vl_ok}/{len(clusters)} 簇")
        else:
            msg = f"检测 {len(stars)} 颗星，K={chosen['k']}；VL 未返回有效结果"

        return {
            "success": True,
            "identifiable": len(stars) > 0,

            "count": len(stars),
            "matched_count": len(stars),
            "detected_star_count": len(stars),
            "stars": stars,
            "detected_stars": [{"x": s["x"], "y": s["y"]} for s in stars],

            "clusters": clusters,
            "cluster_k": chosen["k"],
            "cluster_score": chosen["score"],

            "all_cluster_results": [{
                "k": chosen["k"],
                "score": chosen["score"],
                "cluster_count": len(clusters),
                "clusters": clusters,
                "annotated_image": chosen.get("annotated_image", ""),
                "annotated_mime": "image/png",
                "used_for_vl": True,
            }],

            "vl_cluster_k": chosen["k"],
            "vl_clusters": clusters,
            "vl_summary": vl_summary.get("summary") if vl_summary else None,
            "vl_sky_region": vl_summary.get("sky_region") if vl_summary else None,

            "vl_low_confidence_threshold": VisionConfig.CONFIDENCE_THRESHOLD,
            "vl_recheck": {
                "performed": bool(
                    vl_recheck and vl_recheck.get("success")
                    and not vl_recheck.get("no_change")
                ),
                "threshold": VisionConfig.CONFIDENCE_THRESHOLD,
                "changed_ids": vl_recheck.get("changed_ids", []) if vl_recheck else [],
                "changes": vl_recheck.get("changes", []) if vl_recheck else [],
                "skipped": vl_recheck.get("skipped") if vl_recheck else None,
            } if vl_recheck else None,

            "image_width": w,
            "image_height": h,
            "original_width": ow,
            "original_height": oh,
            "threshold": detection["threshold"],
            "candidate_count": detection["candidate_count"],
            "edge_margin": detection["edge_margin"],
            "roi": detection["roi"],

            "annotated_image": chosen.get("annotated_image", ""),
            "annotated_mime": "image/png",

            "source": "opencv-local+adaptive-kmeans+vl",
            "message": msg,
        }