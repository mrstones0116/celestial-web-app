"""VL（视觉语言模型）客户端：连接池 + 指数退避 + JSON 稳健解析 + prompt 构造。"""
import asyncio
import json
import re
from typing import Any, Dict, List, Optional

import httpx

from .config import VisionConfig
from .constellations import ABBR_TO_FULL, normalize_constellation


# ---------- Prompt 模板 ----------

_FULL_PROMPT = """你是一名天文识星专家。这是同一张星空照片的 3 个版本（原图 / 提亮图 / 反相图），以及 1 张带聚类标注的图。

照片中已经用【{k} 种不同颜色】的圆点标出了 {k} 个星群（cluster），每簇的**主星**用【大圆圈 + 中心白点】标出，旁边有小标签 C0~C{k_minus_1}。

【颜色 → 簇 对照表】
{cluster_table}

【所有簇的量化信息】
{cluster_details}

【任务】
对**每一个簇**，判断它最可能对应的星座（88 星座之一）。每个簇独立判断。

【判断要点】
1. 每簇的**主星**（大圆圈白心）权重最高，是形状锚点
2. 越亮、离主星越近的成员星越可信
3. 边缘星可能属于邻近簇，不要强行纳入当前星座形状
4. 参考邻近簇的颜色和位置，优先考虑主星和簇内成员
5. 严格对齐 JSON 里的 id，不要错位

【最终裁决规则】
1. 每簇只给一个最终答案（constellation / constellation_abbr），不要模糊两可。
2. 相邻簇判出的星座在天球上必须相邻、相接或属于同一片天区；
   若出现完全不相邻（如 Orion 与 Cygnus 相邻），必须调整置信度较低的簇。
3. confidence 为最终置信度（0~1）。若 < 0.3 视为低置信。
4. alternative 按置信度降序给出前 1~3 个候选。
5. 所有簇的最终判定必须构成一片**天球上物理自洽的连续区域**。

【输出格式】只输出 JSON，不要 markdown，不要解释：
{{
  "clusters": [
    {{
      "id": 0,
      "constellation": "Orion",
      "constellation_abbr": "Ori",
      "confidence": 0.82,
      "reason": "...",
      "alternative": [
        {{"name": "Taurus", "confidence": 0.28, "reason": "..."}}
      ],
      "shape_description": "...",
      "edge_note": "..."
    }}
  ],
  "summary": "...",
  "sky_region": "..."
}}
"""

_RECHECK_PROMPT = """你是一名天文识星专家。这是同一张星空照片的 3 个版本（原图 / 提亮图 / 反相图），以及 1 张带聚类标注的图。

照片中已经用【{k} 种不同颜色】的圆点标出了 {k} 个星群（cluster），每簇的**主星**用【大圆圈 + 中心白点】标出，旁边有小标签 C0~C{k_minus_1}。

【颜色 → 簇 对照表】
{cluster_table}

【已高置信度确认的星座（锚点，不可更改；新判定必须与它们在天球上相邻/相接）】
{confirmed_clusters}

【需要重新判断的低置信度簇（置信度 < {threshold}）】
{low_conf_clusters}

【任务】
只对上面列出的**低置信度簇**重新判定星座。**必须以所有高置信度簇的星座位置作为锚点**：
1. 新判定的星座必须与相邻的高置信度锚点在**天球上物理相邻、相接或属于同一片天区**；
2. 若低置信度簇与某个高置信度锚点判出的星座在天球上完全不相邻，必须改成与锚点相邻的星座；
3. **只输出需要修改的簇**；已被高置信度确认的簇不要再返回。

【最终裁决规则】
1. 每簇只给一个最终答案；不要模糊两可
2. confidence 为最终置信度（0~1），必须 ≥ 0.5
3. alternative 按置信度降序给出前 1~3 个候选

【输出格式】只输出 JSON，不要 markdown，不要解释：
{{
  "clusters": [
    {{
      "id": 2,
      "constellation": "Taurus",
      "constellation_abbr": "Tau",
      "confidence": 0.72,
      "reason": "...",
      "alternative": [],
      "shape_description": "...",
      "edge_note": "..."
    }}
  ],
  "summary": "...",
  "sky_region": "..."
}}
"""


def _strip_fence(text: str) -> str:
    t = str(text).strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if len(lines) > 1 and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


# ---------- Prompt 构造 ----------

def _cluster_table(clusters: List[Dict[str, Any]]) -> str:
    from .annotate import palette_color
    return "\n".join(
        f"  - C{c['id']}：RGB{palette_color(c['id'])}（成员 {c['star_count']} 颗）"
        for c in clusters
    )


def _cluster_block(c: Dict[str, Any]) -> str:
    from .annotate import palette_color
    rgb = palette_color(c["id"])
    main = c["main_star"]
    members = c["stars"][:8]
    member_lines = "\n".join(
        f"      {i+1}. ({m['px']:.0f},{m['py']:.0f}) "
        f"亮度={m['brightness']:.1f} 权重={m['weight']:.3f} "
        f"距主星={m['dist_to_main']:.1f}"
        for i, m in enumerate(members)
    ) or "      （无）"
    edge_lines = "\n".join(
        f"      ({e['px']:.0f},{e['py']:.0f}) 亮度={e['brightness']:.1f}"
        for e in c.get("edge_stars", [])
    ) or "      （无）"
    neighbor_lines = ", ".join(
        f"C{n['cluster_id']}({n['distance']:.0f}px)"
        for n in c.get("neighbors", [])[:3]
    ) or "（无）"

    return f"""
  ── C{c['id']}（颜色 RGB{rgb}）──
    成员数：{c['star_count']}
    主星：像素({main['px']:.0f},{main['py']:.0f}) 亮度={main['brightness']:.1f}
    平均亮度：{c['avg_brightness']}
    bbox：x[{c['bbox']['x0']:.0f},{c['bbox']['x1']:.0f}] y[{c['bbox']['y0']:.0f},{c['bbox']['y1']:.0f}]
    成员星（按权重降序）：
{member_lines}
    边缘星：
{edge_lines}
    邻近簇：{neighbor_lines}
"""


def build_full_prompt(clusters: List[Dict[str, Any]]) -> str:
    k = len(clusters)
    return _FULL_PROMPT.format(
        k=k, k_minus_1=k - 1,
        cluster_table=_cluster_table(clusters),
        cluster_details="\n".join(_cluster_block(c) for c in clusters),
    )


def build_recheck_prompt(
    all_clusters: List[Dict[str, Any]],
    confirmed: List[tuple],
    low_conf: List[Dict[str, Any]],
    threshold: float,
) -> str:
    k = len(all_clusters)

    from .annotate import palette_color
    confirmed_rows = []
    for c, vr in confirmed:
        rgb = palette_color(c["id"])
        name = (vr.get("constellation_full")
                or vr.get("constellation")
                or vr.get("constellation_abbr") or "")
        abbr = vr.get("constellation_abbr") or ""
        try:
            conf = float(vr.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        confirmed_rows.append(
            f"  - C{c['id']}（RGB{rgb}）→ {name} ({abbr})，置信度 {conf:.2f}\n"
            f"      主星像素：({c['main_star']['px']:.0f},{c['main_star']['py']:.0f})"
        )
    confirmed_text = "\n".join(confirmed_rows) or "（无）"

    low_blocks = []
    for c in low_conf:
        block = _cluster_block(c)
        vr = c.get("vl_result") or {}
        if vr.get("success"):
            prev = (vr.get("constellation_full")
                    or vr.get("constellation")
                    or vr.get("constellation_abbr") or "")
            try:
                prev_conf = float(vr.get("confidence") or 0.0)
            except (TypeError, ValueError):
                prev_conf = 0.0
        else:
            prev, prev_conf = "（初次未判定）", 0.0
        low_blocks.append(
            f"\n  初次判定：{prev}（置信度 {prev_conf:.2f}，低于阈值 {threshold}）"
            + block
        )

    return _RECHECK_PROMPT.format(
        k=k, k_minus_1=k - 1,
        cluster_table=_cluster_table(all_clusters),
        threshold=threshold,
        confirmed_clusters=confirmed_text,
        low_conf_clusters="\n".join(low_blocks),
    )


# ---------- 单条 VL cluster 解析 ----------

def parse_vl_item(item: Dict[str, Any]):
    if not isinstance(item, dict):
        return None
    try:
        cid = int(item.get("id", -1))
    except (TypeError, ValueError):
        return None
    if cid < 0:
        return None

    abbr = normalize_constellation(
        item.get("constellation_abbr") or item.get("constellation") or ""
    )
    full = ABBR_TO_FULL.get(abbr, abbr) if abbr else ""

    try:
        conf = round(max(0.0, min(1.0, float(item.get("confidence", 0.0)))), 3)
    except (TypeError, ValueError):
        conf = 0.0

    clean_alts = []
    alts = item.get("alternative")
    if isinstance(alts, list):
        for a in alts[:4]:
            if not isinstance(a, dict):
                continue
            a_abbr = normalize_constellation(a.get("name") or "")
            try:
                a_conf = float(a.get("confidence", 0.0))
            except (TypeError, ValueError):
                a_conf = 0.0
            clean_alts.append({
                "name": ABBR_TO_FULL.get(a_abbr, a_abbr) or str(a.get("name") or ""),
                "abbr": a_abbr,
                "confidence": round(max(0.0, min(1.0, a_conf)), 3),
                "reason": str(a.get("reason") or "").strip(),
            })

    return cid, {
        "success": True,
        "constellation": full or str(item.get("constellation") or ""),
        "constellation_abbr": abbr,
        "constellation_full": full,
        "confidence": conf,
        "reason": str(item.get("reason") or "").strip(),
        "alternative": clean_alts,
        "shape_description": str(item.get("shape_description") or "").strip(),
        "edge_note": str(item.get("edge_note") or "").strip(),
    }


# ---------- 客户端 ----------

class VLClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or VisionConfig.VL_API_KEY
        self.api_url = api_url or VisionConfig.VL_API_URL
        self.model = model or VisionConfig.VL_MODEL
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=VisionConfig.VL_TIMEOUT,
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            )
        return self._client

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat_json(
        self,
        prompt: str,
        images: List[Dict[str, str]],
        max_retries: int = VisionConfig.VL_MAX_RETRIES,
    ) -> Dict[str, Any]:
        if not self.configured:
            return {"success": False, "error": "未配置 VL API Key"}

        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"},
            })

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": VisionConfig.VL_MAX_TOKENS,
            "temperature": 0.1,
            "top_p": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        client = await self._get_client()
        delay = 2.0
        last_err = ""

        for attempt in range(max_retries):
            try:
                resp = await client.post(self.api_url, json=payload, headers=headers)

                if resp.status_code == 429:
                    last_err = f"429 限流: {resp.text[:200]}"
                    print(f"   ⏳ 429 限流，{delay:.1f}s 后重试 ({attempt+1}/{max_retries})")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue

                if resp.status_code == 400:
                    try:
                        body = resp.json()
                        msg = (body.get("error") or {}).get("message", resp.text[:200])
                    except Exception:
                        msg = resp.text[:200]
                    return {"success": False, "error": f"400: {msg}"}

                if resp.status_code in (500, 502, 503, 504):
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    print(f"   ⏳ 服务端错误，{delay:.1f}s 后重试 ({attempt+1}/{max_retries})")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue

                resp.raise_for_status()
                txt = (resp.text or "").strip()
                if not txt:
                    last_err = "HTTP 返回空内容"
                    print(f"   ⏳ 空响应，{delay:.1f}s 后重试 ({attempt+1}/{max_retries})")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue

                try:
                    data = json.loads(txt)
                except json.JSONDecodeError:
                    return {"success": False,
                            "error": f"API 返回非 JSON: {txt[:300]}"}

                if "error" in data:
                    err = data["error"]
                    if isinstance(err, dict):
                        err = err.get("message", str(err))
                    return {"success": False, "error": f"API 报错: {err}"}

                choices = data.get("choices") or []
                if not choices:
                    return {"success": False, "error": f"返回异常: {str(data)[:200]}"}

                msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                if not msg:
                    return {"success": False, "error": f"返回异常: {str(data)[:200]}"}

                raw = msg.get("content", "")
                if isinstance(raw, list):
                    raw = " ".join(
                        p.get("text", "") for p in raw
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                raw = _strip_fence(str(raw))
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    return {"success": False, "error": f"非 JSON: {raw[:300]}"}
                if not isinstance(parsed, dict):
                    return {"success": False, "error": "返回非对象"}
                return {"success": True, "data": parsed}

            except httpx.HTTPStatusError as e:
                body = e.response.text[:300] if e.response is not None else ""
                return {"success": False,
                        "error": f"HTTP {e.response.status_code}: {body}"}
            except httpx.TimeoutException:
                last_err = "VL 调用超时"
                print(f"   ⏳ 超时，{delay:.1f}s 后重试 ({attempt+1}/{max_retries})")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            except Exception as e:
                import traceback
                traceback.print_exc()
                return {"success": False, "error": f"调用失败: {e}"}

        return {"success": False, "error": f"重试 {max_retries} 次仍失败: {last_err}"}