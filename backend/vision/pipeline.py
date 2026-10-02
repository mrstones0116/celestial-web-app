"""识星全流程：检测 → VL 语义识别星座 → 标准投影参考图。"""
import asyncio
import base64
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from .annotate import (
    annotate_stars,
    prepare_versions,
    render_constellation_reference,
)
from .config import DEBUG_DIR, VisionConfig
from .detection import detect_stars
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
            "engine": "opencv-detect + vl-semantic + standard-projection",
            "configured": self.vl.configured,
            "model": self.vl.model,
            "catalog_available": self.catalog is not None,
            "top_n_default": cfg.TOP_N,
            "max_dim": cfg.MAX_DIM,
            "max_upload_mb": cfg.MAX_UPLOAD_MB,
            "edge_margin": cfg.EDGE_MARGIN,
            "detect_sigma": cfg.DETECT_SIGMA,
            "confidence_threshold": cfg.CONFIDENCE_THRESHOLD,
            "min_confidence_keep": cfg.MIN_CONFIDENCE_KEEP,
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
        vl_summary: Optional[str] = None
        vl_sky_region: Optional[str] = None
        vl_error: Optional[str] = None

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

        # 4) 标准投影参考图
        constellation_annotated = ""
        if constellations and self.catalog is not None:
            try:
                constellation_annotated = await asyncio.to_thread(
                    render_constellation_reference,
                    pil, constellations, self.catalog,
                )
                print("🎨 标准投影参考图已生成")
            except Exception:
                import traceback; traceback.print_exc()

        # 5) 调试图
        if VisionConfig.DEBUG_VISION:
            await asyncio.to_thread(
                self._save_debug, pil, star_annotated, constellation_annotated,
            )

        # 6) 组装响应
        return self._build_response(
            stars, constellations,
            vl_summary, vl_sky_region, vl_error,
            detection, w, h, ow, oh,
            star_annotated, constellation_annotated,
        )

    # ---------- VL 步骤 ----------

    async def _vl_identify_constellations(
        self,
        w: int,
        h: int,
        base_versions: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        if not self.vl.configured:
            return {"success": False, "error": "未配置 VL API Key"}

        prompt = build_constellation_prompt(w, h)
        print(f"🤖 VL 整图识别星座（{len(base_versions)} 张图）...")
        res = await self.vl.chat_json(prompt, base_versions)
        if not res.get("success"):
            return res

        data = res["data"]
        raw_list = data.get("constellations") if isinstance(data, dict) else None
        if not isinstance(raw_list, list):
            return {"success": False, "error": "返回缺少 constellations 字段"}

        parsed: List[Dict[str, Any]] = []
        for item in raw_list:
            p = parse_constellation_item(item)
            if p is not None:
                parsed.append(p)

        # 硬地板
        floor = VisionConfig.MIN_CONFIDENCE_KEEP
        parsed = [c for c in parsed if c["confidence"] >= floor]

        # 按置信度降序
        parsed.sort(key=lambda c: -c["confidence"])

        # 软上限
        MAX_CONSTELLATIONS = 8
        if len(parsed) > MAX_CONSTELLATIONS:
            print(f"⚠️ VL 返回 {len(parsed)} 个，截断为前 {MAX_CONSTELLATIONS}")
            parsed = parsed[:MAX_CONSTELLATIONS]

        low = [c for c in parsed if c["low_confidence"]]
        if low:
            print(f"⚠️ {len(low)} 个星座置信度 < "
                  f"{VisionConfig.CONFIDENCE_THRESHOLD}: "
                  f"{[c['abbr'] for c in low]}")

        return {
            "success": True,
            "constellations": parsed,
            "summary": str(data.get("summary") or "").strip(),
            "sky_region": str(data.get("sky_region") or "").strip(),
        }

    # ---------- 调试图 ----------

    def _save_debug(
        self,
        pil,
        star_b64: str,
        const_b64: str,
    ):
        try:
            DEBUG_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            pil.save(DEBUG_DIR / f"{ts}_input.png")
            if star_b64:
                (DEBUG_DIR / f"{ts}_stars.png").write_bytes(
                    base64.b64decode(star_b64)
                )
            if const_b64:
                (DEBUG_DIR / f"{ts}_constellations_reference.png").write_bytes(
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
        stars, constellations,
        vl_summary, vl_sky_region, vl_error,
        detection, w, h, ow, oh,
        star_annotated, constellation_annotated,
    ) -> Dict[str, Any]:

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
            msg = (f"检测 {len(stars)} 颗星；识别 {len(constellations)} 个星座，"
                   f"已生成标准投影参考图: {names}")

        return {
            "success": True,
            "identifiable": len(constellations) > 0 or len(stars) > 0,

            # 星点
            "count": len(stars),
            "stars": stars,
            "detected_stars": [{"x": s["x"], "y": s["y"]} for s in stars],

            # 星座
            "constellations": constellations,
            "constellation_count": len(constellations),

            "vl_summary": vl_summary,
            "vl_sky_region": vl_sky_region,
            "vl_error": vl_error,
            "vl_confidence_threshold": VisionConfig.CONFIDENCE_THRESHOLD,

            # 图像信息
            "image_width": w,
            "image_height": h,
            "original_width": ow,
            "original_height": oh,
            "threshold": detection["threshold"],
            "candidate_count": detection["candidate_count"],
            "edge_margin": detection["edge_margin"],
            "roi": detection["roi"],

            # 标注图
            "star_annotated_image": star_annotated,
            "constellation_annotated_image": constellation_annotated,
            "annotated_image": constellation_annotated or star_annotated,
            "annotated_mime": "image/png",

            "source": "opencv-detect+vl-semantic+standard-projection",
            "message": msg,
        }