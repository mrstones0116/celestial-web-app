"""识星全流程：检测 → VL 语义识别 → plate solving → 绘制。"""
import asyncio
import base64
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import UploadFile

from .annotate import (
    annotate_stars,
    prepare_versions,
    render_constellation_reference,
)
from .config import DEBUG_DIR, VisionConfig
from .detection import detect_stars
from .plate_solve import solve as plate_solve
from .vl import (
    VLClient,
    build_constellation_prompt,
    parse_constellation_item,
)


class VisionPipeline:
    def __init__(self, catalog=None):
        self.vl = VLClient()
        self.catalog = catalog

    # ---------- 状态 ----------

    def status(self) -> Dict[str, Any]:
        cfg = VisionConfig
        return {
            "engine": "opencv-detect + vl-semantic + plate-solve",
            "configured": self.vl.configured,
            "model": self.vl.model,
            "catalog_available": self.catalog is not None,
            "top_n_default": cfg.TOP_N,
            "max_dim": cfg.MAX_DIM,
            "detect_sigma": cfg.DETECT_SIGMA,
            "plate_template_mag": cfg.PLATE_TEMPLATE_MAG,
            "plate_eps_px": cfg.PLATE_EPS_PX,
            "plate_min_inliers": cfg.PLATE_MIN_INLIERS,
            "confidence_threshold": cfg.CONFIDENCE_THRESHOLD,
            "min_confidence_keep": cfg.MIN_CONFIDENCE_KEEP,
        }

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

        # 2) 星点图
        try:
            star_annotated = await asyncio.to_thread(
                annotate_stars, pil, stars, None,
            )
        except Exception:
            import traceback; traceback.print_exc()
            star_annotated = ""

        # 3) VL 语义识别
        constellations: List[Dict[str, Any]] = []
        vl_summary = vl_sky_region = None
        vl_error = None

        if not self.vl.configured:
            vl_error = "未配置 VL API Key"
        else:
            try:
                base_versions = await asyncio.to_thread(prepare_versions, pil)
                vl_result = await self._vl_identify_constellations(
                    w, h, base_versions,
                )
                if vl_result.get("success"):
                    constellations = vl_result["constellations"]
                    vl_summary = vl_result.get("summary")
                    vl_sky_region = vl_result.get("sky_region")
                    print(f"🤖 VL 识别到 {len(constellations)} 个星座：")
                    for c in constellations:
                        print(f"   · {c.get('name_cn') or c.get('name')} "
                              f"({c['abbr']} {c['confidence']:.2f})")
                else:
                    vl_error = vl_result.get("error")
                    print(f"   ✗ VL 失败: {vl_error}")
            except Exception as e:
                import traceback; traceback.print_exc()
                vl_error = str(e)

        # 4) Plate solving
        plate_fit = None
        projector = None
        if constellations and self.catalog is not None and len(stars) >= 2:
            try:
                plate_fit = await asyncio.to_thread(
                    self._try_plate_solve,
                    constellations, stars, (w, h),   # ← 加 (w, h)
                )
                if plate_fit:
                    projector = plate_fit["projector"]
                    print(f"🎯 plate solve 成功：inliers={plate_fit['inliers']}, "
                          f"scale={plate_fit['scale_px_per_rad']:.0f} px/rad, "
                          f"center=({plate_fit['ra0']:.2f}, {plate_fit['dec0']:.2f})")
                else:
                    print("⚠️ plate solve 失败，退回标准投影")
            except Exception:
                import traceback; traceback.print_exc()

        # 5) 绘制（projector 为 None 时 annotate 内部退回标准投影）
        constellation_annotated = ""
        if constellations and self.catalog is not None:
            try:
                constellation_annotated = await asyncio.to_thread(
                    render_constellation_reference,
                    pil,
                    constellations,
                    self.catalog,
                    projector=projector,
                    draw_extra_members=True,
                    extra_members_max_mag=VisionConfig.PLATE_TEMPLATE_MAG,
                )
                print("🎨 星座投影图已生成"
                      f"（{'plate-solved' if projector else 'standard'}）")
            except Exception:
                import traceback; traceback.print_exc()

        # 6) 调试图
        if VisionConfig.DEBUG_VISION:
            await asyncio.to_thread(
                self._save_debug, pil, star_annotated, constellation_annotated,
            )

        # 7) 组装响应
        return self._build_response(
            stars, constellations, plate_fit,
            vl_summary, vl_sky_region, vl_error,
            detection, w, h, ow, oh,
            star_annotated, constellation_annotated,
        )

    # ---------- plate solve ----------

    def _try_plate_solve(self, constellations, stars, image_size):
        """
        收集这些星座的 HYG 亮星做模板，与图像星点做 RANSAC + ICP 拟合。
        """
        template_ra: List[float] = []
        template_dec: List[float] = []
        template_mag: List[float] = []
        for c in constellations:
            abbr = c.get("abbr")
            if not abbr:
                continue
            members = self.catalog.get_members(abbr)
            for m in members:
                if m["mag"] > VisionConfig.PLATE_TEMPLATE_MAG:
                    continue
                try:
                    ra = float(m["ra"])
                    dec = float(m["dec"])
                    mag = float(m["mag"])
                except (TypeError, ValueError):
                    continue
                if np.isnan(ra) or np.isnan(dec):
                    continue
                template_ra.append(ra)
                template_dec.append(dec)
                template_mag.append(mag)

        if len(template_ra) < 3:
            return None

        template_radec = np.stack(
            [np.array(template_ra), np.array(template_dec)], axis=1,
        )
        template_mags = np.array(template_mag)

        image_points = np.array(
            [[float(s["px"]), float(s["py"])] for s in stars],
            dtype=float,
        )

        return plate_solve(
            template_radec=template_radec,
            image_points=image_points,
            template_mags=template_mags,
            image_size=image_size,               # ← 新增
            ransac_iter=VisionConfig.PLATE_RANSAC_ITER,
            eps_px=VisionConfig.PLATE_EPS_PX,
            min_inliers=VisionConfig.PLATE_MIN_INLIERS,
            icp_iter=VisionConfig.PLATE_ICP_ITER,
        )

    # ---------- VL ----------

    async def _vl_identify_constellations(self, w, h, base_versions):
        if not self.vl.configured:
            return {"success": False, "error": "未配置 VL API Key"}
        prompt = build_constellation_prompt(w, h)
        print(f"🤖 VL 整图识别星座（{len(base_versions)} 张图）...")
        res = await self.vl.chat_json(prompt, base_versions)
        if not res.get("success"):
            return res

        data = res["data"]
        raw = data.get("constellations") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return {"success": False, "error": "返回缺少 constellations"}

        parsed: List[Dict[str, Any]] = []
        for item in raw:
            p = parse_constellation_item(item)
            if p is not None:
                parsed.append(p)

        floor = VisionConfig.MIN_CONFIDENCE_KEEP
        parsed = [c for c in parsed if c["confidence"] >= floor]
        parsed.sort(key=lambda c: -c["confidence"])
        parsed = parsed[:8]

        return {
            "success": True,
            "constellations": parsed,
            "summary": str(data.get("summary") or "").strip(),
            "sky_region": str(data.get("sky_region") or "").strip(),
        }

    # ---------- 调试 ----------

    def _save_debug(self, pil, star_b64, const_b64):
        try:
            DEBUG_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            pil.save(DEBUG_DIR / f"{ts}_input.png")
            if star_b64:
                (DEBUG_DIR / f"{ts}_stars.png").write_bytes(
                    base64.b64decode(star_b64)
                )
            if const_b64:
                (DEBUG_DIR / f"{ts}_constellations.png").write_bytes(
                    base64.b64decode(const_b64)
                )
            print(f"💾 调试图已保存: {ts}_*.png")
        except Exception as e:
            print(f"⚠️ 保存调试图失败: {e}")

    # ---------- 组装响应 ----------

    @staticmethod
    def _error(message: str) -> Dict[str, Any]:
        return {"success": False, "identifiable": False, "message": message}

    @staticmethod
    def _build_response(
        stars, constellations, plate_fit,
        vl_summary, vl_sky_region, vl_error,
        detection, w, h, ow, oh,
        star_annotated, constellation_annotated,
    ):
        if not constellations:
            if vl_error:
                msg = f"检测 {len(stars)} 颗星；VL 未返回有效结果: {vl_error}"
            else:
                msg = f"检测 {len(stars)} 颗星；未识别出可辨认的星座"
        else:
            names = "、".join(
                c.get("name_cn") or c.get("name") or c.get("abbr") or "?"
                for c in constellations
            )
            if plate_fit:
                msg = (f"检测 {len(stars)} 颗星；识别 {len(constellations)} 个星座，"
                       f"plate solve 成功（inliers={plate_fit['inliers']}）: {names}")
            else:
                msg = (f"检测 {len(stars)} 颗星；识别 {len(constellations)} 个星座，"
                       f"plate solve 失败（回退标准投影）: {names}")

        return {
            "success": True,
            "identifiable": len(constellations) > 0 or len(stars) > 0,
            "count": len(stars),
            "stars": stars,
            "detected_stars": [{"x": s["x"], "y": s["y"]} for s in stars],

            "constellations": constellations,
            "constellation_count": len(constellations),

            "plate_solve": {
                "ok": plate_fit is not None,
                "inliers": plate_fit["inliers"] if plate_fit else 0,
                "scale_px_per_rad": (
                    plate_fit["scale_px_per_rad"] if plate_fit else None
                ),
                "center_ra": plate_fit["ra0"] if plate_fit else None,
                "center_dec": plate_fit["dec0"] if plate_fit else None,
            },

            "vl_summary": vl_summary,
            "vl_sky_region": vl_sky_region,
            "vl_error": vl_error,
            "vl_confidence_threshold": VisionConfig.CONFIDENCE_THRESHOLD,

            "image_width": w,
            "image_height": h,
            "original_width": ow,
            "original_height": oh,
            "threshold": detection["threshold"],
            "candidate_count": detection["candidate_count"],
            "edge_margin": detection["edge_margin"],
            "roi": detection["roi"],

            "star_annotated_image": star_annotated,
            "constellation_annotated_image": constellation_annotated,
            "annotated_image": constellation_annotated or star_annotated,
            "annotated_mime": "image/png",

            "source": "opencv-detect+vl-semantic+plate-solve",
            "message": msg,
        }