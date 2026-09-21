"""
tour 模块的自然语言解析。

优先调用 LLM，失败时自动回退到关键词识别。
支持通过环境变量灵活配置 DeepSeek API。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

import httpx


# ---------------- 配置（运行时读取） ----------------

def _get_api_url() -> str:
    """优先读取 DeepSeek 专用配置，回退到通用 LLM 配置"""
    return os.getenv(
        "TOUR_LLM_API_URL",
        os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions"),
    ).strip()


def _get_api_key() -> str:
    """优先读取 DeepSeek 专用 Key，回退到通用 LLM Key"""
    return (
        os.getenv("TOUR_LLM_API_KEY", "")
        or os.getenv("DEEPSEEK_API_KEY", "")
        or os.getenv("MODELSCOPE_API_KEY", "")
        or os.getenv("ZHIPU_API_KEY", "")
    ).strip()


def _get_model() -> str:
    """优先读取 Tour 专用模型，回退到通用模型，默认使用 DeepSeek Flash"""
    return (
        os.getenv("TOUR_LLM_MODEL")
        or os.getenv("DEEPSEEK_MODEL")
        or "deepseek-flash"
    ).strip()


def _llm_enabled() -> bool:
    return os.getenv("TOUR_LLM_ENABLED", "1") == "1"


def _llm_timeout() -> float:
    try:
        return float(os.getenv("TOUR_LLM_TIMEOUT", "15"))
    except Exception:
        return 15.0


# ---------------- 意图白名单 ----------------

ALLOWED_INTENTS = {
    "summer_sky",
    "winter_sky",
    "messier_marathon",
    "bright_star_tour",
    "default",
}

_INTENT_DESC = """
- summer_sky：用户想看夏季星空、夏季大三角、夏夜观星等。
- winter_sky：用户想看冬季星空、猎户座、天狼星、冬季亮星等。
- messier_marathon：用户想看梅西耶天体、深空、星云、星团等。
- bright_star_tour：用户想看最亮的恒星、亮星巡礼等。
- default：无法判断或用户没给明确偏好，用入门路线。
""".strip()


# ---------------- Prompt ----------------

_SYSTEM_PROMPT = f"""你是一个天文导览意图识别助手。
用户会用自然语言描述他们想看的星空内容。

你需要判断用户最可能的意图，只能从下面这些值里选一个：
{_INTENT_DESC}

只输出 JSON，不要 markdown，不要多余解释。格式：
{{
  "intent": "summer_sky",
  "confidence": 0.9,
  "reason": "用户明确提到夏季星空"
}}

如果完全无法判断，intent 填 "default"，confidence 填 0.0。
"""


# ---------------- 工具函数 ----------------

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_fence(text: str) -> str:
    t = str(text).strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _extract_json(text: str) -> Dict[str, Any]:
    t = _strip_fence(text)
    try:
        return json.loads(t)
    except Exception:
        m = _JSON_RE.search(t)
        if m:
            return json.loads(m.group(0))
    raise ValueError(f"无法从 LLM 响应里提取 JSON: {text[:200]}")


def _fallback(text: str, reason: str = "") -> Dict[str, Any]:
    """调用 planner 的关键词识别兜底。延迟导入避免循环依赖。"""
    try:
        from .planner import detect_intent as _kw
    except Exception as e:
        return {
            "intent": "default",
            "confidence": 0.0,
            "reason": f"fallback 不可用: {e}",
            "source": "keyword",
        }

    kw = _kw(text)
    kw["source"] = "keyword"
    kw["confidence"] = 0.3
    if reason:
        kw["reason"] = reason
    return kw


# ---------------- 主入口 ----------------

async def parse_instruction(text: str) -> Dict[str, Any]:
    """
    解析用户指令，返回：
      {
        "intent": "summer_sky",
        "confidence": 0.9,
        "reason": "...",
        "source": "llm" | "keyword"
      }
    """
    text = (text or "").strip()
    if not text:
        return {
            "intent": "default",
            "confidence": 0.0,
            "reason": "空输入",
            "source": "keyword",
        }

    if not _llm_enabled():
        return _fallback(text, "LLM 已通过 TOUR_LLM_ENABLED=0 关闭")

    api_key = _get_api_key()
    if not api_key:
        return _fallback(text, "未配置 TOUR_LLM_API_KEY / DEEPSEEK_API_KEY")

    payload = {
        "model": _get_model(),
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "max_tokens": 256,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = _llm_timeout()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(_get_api_url(), json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        raw = data["choices"][0]["message"]["content"]

        if isinstance(raw, list):
            raw = " ".join(
                p.get("text", "")
                for p in raw
                if isinstance(p, dict) and p.get("type") == "text"
            )

        parsed = _extract_json(str(raw))
        intent = str(parsed.get("intent", "")).strip().lower()

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except Exception:
            confidence = 0.0

        reason = str(parsed.get("reason", ""))

        if intent not in ALLOWED_INTENTS:
            return _fallback(text, f"LLM 返回未知意图: {intent}")

        return {
            "intent": intent,
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": reason,
            "source": "llm",
        }

    except httpx.TimeoutException:
        return _fallback(text, f"LLM 超时（>{timeout}s）")

    except httpx.HTTPStatusError as e:
        body = e.response.text[:120] if e.response is not None else ""
        return _fallback(text, f"LLM HTTP {e.response.status_code}: {body}")

    except Exception as e:
        return _fallback(text, f"LLM 调用失败: {e}")