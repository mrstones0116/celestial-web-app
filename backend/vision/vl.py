"""VL（视觉语言模型）客户端：连接池 + 指数退避 + JSON 稳健解析 + prompt 构造。"""
import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx

from .config import VisionConfig
from .constellations import ABBR_TO_FULL, normalize_constellation


# ============================================================
# Prompt
# ============================================================

_CONSTELLATION_PROMPT = """[INST] 你是天文识星专家。请仔细分析下面提供的同一张星空照片的多个版本（原图 / 提亮图 / 反相图），识别其中的星座。

═══════════════════════════════════════
⚠️ 输出格式硬性要求（违反将被拒绝）
═══════════════════════════════════════
你必须**只输出一个 JSON 对象**，任何其他内容都是错误的。
- 第一个字符必须是左大括号
- 最后一个字符必须是右大括号
- 不要输出任何解释、前言、后语
- 不要用 markdown 代码块（不要三反引号 json）
- 不要在 JSON 前后加任何文字

═══════════════════════════════════════
任务
═══════════════════════════════════════
识别照片中所有你能辨认的星座，只报告**三字母缩写**。
不要给任何像素坐标、不要给 bbox、不要给星点位置。
一张广角星空照片通常覆盖 2~8 个星座，请扫描整幅图像。

每个星座只给：
- abbr：三字母缩写（如 Cyg / Cas / Lyr / Aql / Cep / Dra）
- name：英文全称（如 Cygnus）
- name_cn：中文名（如 天鹅座）
- confidence：0~1
- reason：判断依据（简短）

严格要求：
1. 只报告你**真正能在图中辨认出结构**的星座；完全看不出则返回空数组。
2. 绝不为了凑数而编造：只能辨认 1 个就返回 1 个。
3. ≤ 0.3 把握的星座宁可不返回。
4. 同一星座不要拆成多个。
5. 绝对不要输出 bbox / x / y / pixel 等字样。

═══════════════════════════════════════
输出（只输出下面这个 JSON，不要有别的字）
═══════════════════════════════════════
{{"constellations":[{{"abbr":"Cyg","name":"Cygnus","name_cn":"天鹅座","confidence":0.95,"reason":"十字形主体，天津四"}}],"summary":"...","sky_region":"..."}}

无法辨认时，只输出：
{{"constellations":[],"summary":"无法辨认","sky_region":""}}
"""

def build_constellation_prompt(w: int = 0, h: int = 0) -> str:
    return _CONSTELLATION_PROMPT

def parse_constellation_item(item):
    if not isinstance(item, dict):
        return None

    abbr_raw = str(item.get("abbr") or item.get("constellation_abbr")
                   or item.get("name") or "").strip()
    abbr = normalize_constellation(abbr_raw)
    if not abbr:
        return None

    name = str(item.get("name") or "").strip()
    name_cn = str(item.get("name_cn") or "").strip()
    full = ABBR_TO_FULL.get(abbr, name or abbr)

    try:
        conf = round(max(0.0, min(1.0, float(item.get("confidence", 0.0)))), 3)
    except (TypeError, ValueError):
        conf = 0.0

    return {
        "abbr": abbr,
        "name": full,
        "name_cn": name_cn,
        "confidence": conf,
        "low_confidence": conf < VisionConfig.CONFIDENCE_THRESHOLD,
        "reason": str(item.get("reason") or "").strip(),
    }
# ============================================================
# 客户端
# ============================================================

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

def _extract_first_json_object(text: str) -> Optional[str]:
    """从任意文本中提取第一个平衡的 {...} JSON 块。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """先直接解析，失败则提取第一个 {...} 再解析。"""
    try:
        v = json.loads(raw)
        if isinstance(v, dict):
            return v
    except json.JSONDecodeError:
        pass

    chunk = _extract_first_json_object(raw)
    if chunk is None:
        return None
    try:
        v = json.loads(chunk)
        if isinstance(v, dict):
            print("   ⚠️ VL 返回非纯 JSON，已自动提取 JSON 块")
            return v
    except json.JSONDecodeError:
        return None
    return None

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
                parsed = _try_parse_json(raw)
                if parsed is None:
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