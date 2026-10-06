from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Optional
import httpx


def _api_url() -> str:
    return os.getenv(
        "TOUR_LLM_API_URL",
        "https://api.deepseek.com/v1/chat/completions",
    ).strip()


def _api_key() -> str:
    return (
        os.getenv("TOUR_LLM_API_KEY", "")
        or os.getenv("DEEPSEEK_API_KEY", "")
        or os.getenv("MODELSCOPE_API_KEY", "")
    ).strip()


def _model() -> str:
    return os.getenv("AGENT_LLM_MODEL") or os.getenv("TOUR_LLM_MODEL") or "deepseek-chat"


def _timeout() -> float:
    try:
        return float(os.getenv("AGENT_LLM_TIMEOUT", "120"))
    except Exception:
        return 120.0


def _max_tokens() -> int:
    try:
        return int(os.getenv("AGENT_LLM_MAX_TOKENS", "8000"))
    except Exception:
        return 8000


async def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 0.4,
    tag: str = "agent",
) -> Optional[Dict[str, Any]]:
    """
    单次 LLM 调用，返回 OpenAI 格式的 message 对象。
    message 可能包含 .content 或 .tool_calls。
    """
    key = _api_key()
    if not key:
        print(f"[{tag}] 未配置 API Key")
        return None

    payload: Dict[str, Any] = {
        "model": _model(),
        "messages": messages,
        "max_tokens": _max_tokens(),
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            resp = await client.post(_api_url(), json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        print(f"[{tag}] ⚠️ 超时")
        return None
    except httpx.HTTPStatusError as e:
        print(f"[{tag}] ⚠️ HTTP {e.response.status_code}: {e.response.text[:300]}")
        return None
    except Exception as e:
        print(f"[{tag}] ⚠️ 调用失败: {e}")
        return None

    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    finish = choice.get("finish_reason", "")
    usage = data.get("usage", {})
    content_len = len(msg.get("content") or "")
    tool_calls = msg.get("tool_calls") or []

    print(f"[{tag}] finish={finish} usage={usage} "
          f"content_len={content_len} tool_calls={len(tool_calls)}")

    # 推理模型兜底
    if not msg.get("content") and msg.get("reasoning_content") and not tool_calls:
        msg["content"] = msg["reasoning_content"]

    return msg