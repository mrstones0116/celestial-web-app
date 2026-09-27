"""
tour 模块的自然语言解析。
优先调用 LLM，失败时自动回退到关键词识别。
支持通过环境变量灵活配置 DeepSeek API。
"""
from __future__ import annotations
import json
import os
import re
from typing import Any, Dict, List, Optional
import httpx

# ---------------- 配置（运行时读取） ----------------
def _get_api_url() -> str:
    return os.getenv(
        "TOUR_LLM_API_URL",
        os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions"),
    ).strip()


def _get_api_key() -> str:
    return (
        os.getenv("TOUR_LLM_API_KEY", "")
        or os.getenv("DEEPSEEK_API_KEY", "")
        or os.getenv("MODELSCOPE_API_KEY", "")
        or os.getenv("ZHIPU_API_KEY", "")
    ).strip()


def _get_model() -> str:
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


# ---------------- 意图白名单（扩展） ----------------
ALLOWED_INTENTS = {
    "what_visible",       # ✅ 新增：现在能看到什么
    "recommend_order",    # ✅ 新增：推荐观测顺序
    "summer_sky",
    "winter_sky",
    "messier_marathon",
    "bright_star_tour",
    "default",
}

_INTENT_DESC = """
what_visible：用户想知道现在/今晚能看到什么星星，例如"现在我能看到什么星星"、"今晚有什么亮的星"。
recommend_order：用户想要一个观测顺序推荐，例如"能帮我推荐一个观测的顺序吗"、"先看什么好"。
summer_sky：用户想看夏季星空、夏季大三角、织女星、牛郎星、天津四等。
winter_sky：用户想看冬季星空、猎户座、天狼星、冬季亮星等。
messier_marathon：用户想看梅西耶天体、深空、星云、星团等。
bright_star_tour：用户想看最亮的恒星、亮星巡礼等。
default：无法判断或用户没给明确偏好，用入门路线。
""".strip()

# ---------------- Prompt ----------------
_SYSTEM_PROMPT = f"""你是一个专业的天文导览助手，不仅要识别用户意图，还要提取关键信息。

用户会用自然语言描述他们想看的星空内容。
你需要判断用户最可能的意图，只能从下面这些值里选一个：
{_INTENT_DESC}

同时提取以下实体（如果用户提到）：
- time_expression：用户提到的时间，如"现在"、"今晚"、"22点"、"2024-07-15"
- specific_objects：用户提到的具体天体名称，如"织女星"、"猎户座"
- observation_goal：观测目的，如"随便看看"、"拍照"、"学习星座"

只输出 JSON，不要 markdown，不要多余解释。格式：
{{
  "intent": "what_visible",
  "confidence": 0.9,
  "reason": "用户明确问现在能看到什么",
  "entities": {{
    "time_expression": "现在",
    "specific_objects": [],
    "observation_goal": "随便看看"
  }}
}}

如果完全无法判断，intent 填 "default"，confidence 填 0.0，entities 留空。
"""

# ==================== 工具函数（增强版） ====================

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_fence(text: str) -> str:
    t = str(text).strip()
    # 处理 ```json ... ``` 或 ``` ... ```
    if "```" in t:
        # 提取 ``` 之间的内容
        parts = t.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                return part
    return t.strip()


def _extract_json(text: str) -> Dict[str, Any]:
    t = _strip_fence(text)

    # 1) 直接尝试解析
    try:
        return json.loads(t)
    except Exception:
        pass

    # 2) 正则提取 {...}
    m = _JSON_RE.search(t)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    # 3) ✅ 新增：尝试修复被截断的 JSON（补全缺失的括号）
    candidate = t
    if candidate.startswith("{") and not candidate.endswith("}"):
        # 计算未闭合的括号数量
        open_count = candidate.count("{") - candidate.count("}")
        if open_count > 0:
            # 尝试截断到最后一个完整的键值对
            last_quote = candidate.rfind('"')
            if last_quote > 0:
                candidate = candidate[:last_quote + 1] + "}" * open_count
            else:
                candidate += "}" * open_count
            try:
                return json.loads(candidate)
            except Exception:
                pass

    # 4) ✅ 新增：尝试提取 "intent" 字段作为最后兜底
    intent_match = re.search(r'"intent"\s*:\s*"([^"]+)"', t)
    if intent_match:
        return {
            "intent": intent_match.group(1),
            "confidence": 0.5,
            "reason": "JSON 解析失败，仅提取到 intent 字段",
            "entities": {},
        }

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
            "entities": {},
        }
    kw = _kw(text)
    kw["source"] = "keyword"
    kw["confidence"] = 0.3
    kw["entities"] = {}
    if reason:
        kw["reason"] = reason
    return kw

async def parse_instruction(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {
            "intent": "default",
            "confidence": 0.0,
            "reason": "空输入",
            "source": "keyword",
            "entities": {},
        }

    # ✅ 移除关键词优先逻辑，所有请求都走 LLM
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
        "max_tokens": 512,
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

        finish_reason = data["choices"][0].get("finish_reason", "")
        if finish_reason == "length":
            print(f"[tour] ⚠️ LLM 响应被截断 (max_tokens=512)")

        parsed = _extract_json(str(raw))
        intent = str(parsed.get("intent", "")).strip().lower()

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except Exception:
            confidence = 0.0

        reason = str(parsed.get("reason", ""))
        entities = parsed.get("entities", {}) or {}

        if intent not in ALLOWED_INTENTS:
            return _fallback(text, f"LLM 返回未知意图: {intent}")

        return {
            "intent": intent,
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": reason,
            "source": "llm",       # ✅ 始终标记为 llm
            "entities": entities,  # ✅ 始终包含 LLM 提取的实体
        }

    except httpx.TimeoutException:
        return _fallback(text, f"LLM 超时（>{timeout}s）")
    except httpx.HTTPStatusError as e:
        body = e.response.text[:120] if e.response is not None else ""
        return _fallback(text, f"LLM HTTP {e.response.status_code}: {body}")
    except Exception as e:
        return _fallback(text, f"LLM 调用失败: {e}")

# ==================== ✅ 新增：LLM 动态解说生成 ====================

async def generate_narration(
    target_name: str,
    target_info: Dict[str, Any],
    user_style: str = "story",
    locale: str = "zh-CN",
) -> Dict[str, str]:
    """
    为单个天体生成个性化解说。
    返回 {"short": "...", "long": "...", "fun_fact": "...", "observation_tip": "..."}
    """
    api_key = _get_api_key()
    if not api_key:
        return {
            "short": target_name,
            "long": f"{target_name}是一颗值得观测的天体。",
            "fun_fact": None,
            "observation_tip": "抬头寻找最亮的那颗。",
        }

    style_desc = {
        "story": "用浪漫的神话故事或传说来讲解",
        "science": "用严谨的天文物理知识来讲解",
        "observation": "侧重观测技巧、寻找方法、最佳观测时间",
        "photography": "侧重拍摄参数、构图建议、后期技巧",
    }.get(user_style, "用通俗易懂的语言讲解")

    prompt = f"""你是一位资深的天文向导，正在为用户讲解"{target_name}"。
天体信息：{json.dumps(target_info, ensure_ascii=False)}

要求：
1. 风格：{style_desc}
2. 语言：{"中文" if locale.startswith("zh") else "English"}
3. 输出 JSON，包含四个字段：
   - short: 一句话介绍（不超过30字）
   - long: 详细讲解（100-150字）
   - fun_fact: 一个有趣的冷知识（可选，没有就填 null）
   - observation_tip: 给观测者的实用建议（如何找到它、注意什么）

只输出 JSON，不要 markdown。"""

    payload = {
        "model": _get_model(),
        "messages": [
            {"role": "system", "content": "你是天文解说专家，输出必须为纯 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 512,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_llm_timeout()) as client:
            resp = await client.post(_get_api_url(), json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        raw = data["choices"][0]["message"]["content"]
        if isinstance(raw, list):
            raw = " ".join(p.get("text", "") for p in raw if isinstance(p, dict))

        parsed = _extract_json(str(raw))
        return {
            "short": str(parsed.get("short", target_name)),
            "long": str(parsed.get("long", "")),
            "fun_fact": parsed.get("fun_fact"),
            "observation_tip": str(parsed.get("observation_tip", "")),
        }
    except Exception:
        # 生成失败时返回基础版本
        return {
            "short": target_name,
            "long": f"{target_name}是夜空中一个有趣的目标。",
            "fun_fact": None,
            "observation_tip": "抬头寻找最亮的那颗。",
        }
        
# ==================== ✅ 新增：批量生成导览解说 ====================

async def generate_batch_narration(
    stars_info: List[Dict[str, Any]],
    location_summary: str = "香港",
    user_style: str = "story",
    locale: str = "zh-CN",
) -> List[Dict[str, str]]:
    """
    一次性为多颗星生成个性化解说。
    返回与 stars_info 等长的列表，每项包含:
    {
      "short", "long", "best_time", "cultural_story",
      "observation_tip", "fun_fact"
    }
    """
    api_key = _get_api_key()
    count = len(stars_info)

    # LLM 不可用时的兜底模板
    def _fallback_all():
        return [
            {
                "short": s.get("name_zh", s.get("name_en", "")),
                "long": f"{s.get('name_zh', '')}是一颗值得观测的天体。",
                "best_time": "天黑后1小时内",
                "cultural_story": None,
                "observation_tip": "抬头寻找最亮的那颗。",
                "fun_fact": None,
            }
            for s in stars_info
        ]

    if not api_key:
        return _fallback_all()

    # 构建星表摘要
    stars_text = ""
    for i, s in enumerate(stars_info):
        stars_text += (
            f"{i+1}. {s.get('name_zh', '')} / {s.get('name_en', '')}，"
            f"星座：{s.get('constellation', '未知')}，"
            f"视星等：{s.get('magnitude', '?')}，"
            f"当前高度角：{s.get('altitude_deg', '?')}°，"
            f"方位角：{s.get('azimuth_deg', '?')}°\n"
        )

    style_desc = {
        "story": "浪漫、有故事感，适合普通观星爱好者",
        "science": "严谨、数据丰富，适合天文发烧友",
        "observation": "实用、侧重观测技巧",
        "photography": "侧重拍摄建议和构图",
    }.get(user_style, "通俗易懂，有趣味性")

    prompt = f"""你是一位资深天文导览员，正在为位于{location_summary}的观星者做现场解说。
当前是今晚观测。

以下是今晚推荐的 {count} 颗天体：
{stars_text}

请为每颗星生成以下 6 个字段：
- short：一句话介绍（不超过25字）
- long：详细讲解（80-120字），包含这颗星的物理特征（颜色、距离、光谱型等）
- best_time：今晚最佳观测时段（如"21:00-23:00"或"整晚可见"），根据当前高度角和运动趋势判断
- cultural_story：与该星相关的文化典故、神话故事或历史轶事（50-100字）。如果没有著名典故，填 null
- observation_tip：实用观测建议（如何用肉眼找到它、用什么设备看更好）
- fun_fact：一个有趣的冷知识（可选，没有填 null）

风格要求：{style_desc}
语言：{"中文" if locale.startswith("zh") else "English"}

严格输出 JSON 数组，不要 markdown，不要多余解释。格式：
[
  {{
    "short": "...",
    "long": "...",
    "best_time": "...",
    "cultural_story": "...",
    "observation_tip": "...",
    "fun_fact": "..."
  }},
  ...
]

数组长度必须等于 {count}。"""

    payload = {
        "model": _get_model(),
        "messages": [
            {"role": "system", "content": "你是天文导览专家，输出必须为纯 JSON 数组。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 2048,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_get_api_url(), json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        raw = data["choices"][0]["message"]["content"]
        if isinstance(raw, list):
            raw = " ".join(p.get("text", "") for p in raw if isinstance(p, dict))

        # 提取 JSON 数组
        text = _strip_fence(str(raw))
        # 尝试直接解析
        try:
            result = json.loads(text)
        except Exception:
            # 尝试提取 [...] 部分
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                result = json.loads(m.group(0))
            else:
                return _fallback_all()

        if not isinstance(result, list) or len(result) != count:
            # 数量不匹配时，尽量对齐
            fallback = _fallback_all()
            for i in range(min(len(result), count)):
                if isinstance(result[i], dict):
                    fallback[i].update({
                        k: result[i].get(k) for k in
                        ["short", "long", "best_time", "cultural_story", "observation_tip", "fun_fact"]
                        if result[i].get(k) is not None
                    })
            return fallback

        return result

    except Exception as e:
        print(f"[tour] 批量解说生成失败: {e}")
        return _fallback_all()