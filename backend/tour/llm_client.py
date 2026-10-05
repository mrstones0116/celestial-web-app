from __future__ import annotations
import json
import os
import re
from typing import Any, Dict, List, Optional
import httpx


# ==================== 环境配置 ====================

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
        or "deepseek-chat"
    ).strip()


def _llm_enabled() -> bool:
    return os.getenv("TOUR_LLM_ENABLED", "1") == "1"


def _llm_timeout() -> float:
    try:
        return float(os.getenv("TOUR_LLM_TIMEOUT", "120"))
    except Exception:
        return 120.0


# ★ Token 预算（可通过环境变量覆盖，默认给推理模型留足空间）
def _max_tokens_parse() -> int:
    try:
        return int(os.getenv("TOUR_LLM_MAX_TOKENS_PARSE", "4000"))
    except Exception:
        return 4000


def _max_tokens_narration() -> int:
    try:
        return int(os.getenv("TOUR_LLM_MAX_TOKENS_NARRATION", "8000"))
    except Exception:
        return 8000


def _max_tokens_batch() -> int:
    try:
        return int(os.getenv("TOUR_LLM_MAX_TOKENS_BATCH", "32000"))
    except Exception:
        return 32000


def _max_tokens_skeleton() -> int:
    try:
        return int(os.getenv("TOUR_LLM_MAX_TOKENS_SKELETON", "64000"))
    except Exception:
        return 64000


# ==================== 意图识别 ====================

ALLOWED_INTENTS = {
    "what_visible",
    "recommend_order",
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


# ==================== JSON 提取 ====================

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_fence(text: str) -> str:
    t = str(text).strip()
    if "```" in t:
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

    try:
        return json.loads(t)
    except Exception:
        pass

    m = _JSON_RE.search(t)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    candidate = t
    if candidate.startswith("{") and not candidate.endswith("}"):
        open_count = candidate.count("{") - candidate.count("}")
        if open_count > 0:
            last_quote = candidate.rfind('"')
            if last_quote > 0:
                candidate = candidate[:last_quote + 1] + "}" * open_count
            else:
                candidate += "}" * open_count
            try:
                return json.loads(candidate)
            except Exception:
                pass

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


# ==================== 通用请求封装 ====================

async def _post_chat(
    messages: List[Dict[str, str]],
    *,
    max_tokens: int,
    temperature: float = 0.7,
    timeout: Optional[float] = None,
    json_mode: bool = False,
    tag: str = "LLM",
) -> Optional[Dict[str, Any]]:
    """
    统一的 chat/completions 请求封装。
    返回原始响应 dict，失败返回 None。
    会打印诊断日志（model / finish / usage / content_len / reasoning_len）。
    """
    api_key = _get_api_key()
    if not api_key:
        print(f"[tour][{tag}] 未配置 API Key")
        return None

    payload: Dict[str, Any] = {
        "model": _get_model(),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        # ★ 部分兼容层不支持 response_format，报 400 时请注释掉下面这一行
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    to = timeout if timeout is not None else _llm_timeout()

    try:
        async with httpx.AsyncClient(timeout=to) as client:
            resp = await client.post(_get_api_url(), json=payload, headers=headers)

            # ★ 若 json_mode 请求被拒，自动降级重试一次（去掉 response_format）
            if resp.status_code == 400 and json_mode:
                body_lower = (resp.text or "").lower()
                if "response_format" in body_lower or "json_object" in body_lower:
                    print(f"[tour][{tag}] response_format 不被支持，降级重试")
                    payload.pop("response_format", None)
                    resp = await client.post(
                        _get_api_url(), json=payload, headers=headers
                    )

            resp.raise_for_status()
            data = resp.json()

        # ===== 诊断区 =====
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {}) or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        finish = choice.get("finish_reason", "")
        usage = data.get("usage", {})
        model_used = data.get("model", "?")

        print(
            f"[tour][{tag}] model={model_used} finish={finish} "
            f"usage={usage} content_len={len(content)} reasoning_len={len(reasoning)}"
        )

        # content 空但 reasoning 有内容：兜底（你的 prompt 要求 JSON，reasoning 末尾常带 JSON）
        if not content and reasoning:
            print(f"[tour][{tag}] content 为空，改用 reasoning_content 兜底")
            content = reasoning

        if not content:
            print(f"[tour][{tag}] ⚠️ content 与 reasoning 均为空，原始响应：{str(data)[:800]}")
            return None

        if finish == "length":
            print(f"[tour][{tag}] ⚠️ 响应被截断（max_tokens={max_tokens}）")

        # 归一化：把 content 塞回 msg，便于调用方直接取
        msg["content"] = content
        choice["message"] = msg
        data["choices"] = [choice]
        return data

    except httpx.TimeoutException:
        print(f"[tour][{tag}] ⚠️ 超时（>{to}s）")
        return None
    except httpx.HTTPStatusError as e:
        body = e.response.text[:300] if e.response is not None else ""
        print(f"[tour][{tag}] ⚠️ HTTP {e.response.status_code}: {body}")
        return None
    except Exception as e:
        import traceback
        print(f"[tour][{tag}] ⚠️ 调用失败: {e}")
        traceback.print_exc()
        return None


def _normalize_content(raw: Any) -> str:
    """兼容 content 是数组（多模态返回）的情况。"""
    if isinstance(raw, list):
        return " ".join(
            p.get("text", "")
            for p in raw
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return str(raw or "")


# ==================== 意图解析 ====================

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

    if not _llm_enabled():
        return _fallback(text, "LLM 已通过 TOUR_LLM_ENABLED=0 关闭")

    if not _get_api_key():
        return _fallback(text, "未配置 TOUR_LLM_API_KEY / DEEPSEEK_API_KEY")

    data = await _post_chat(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        max_tokens=_max_tokens_parse(),
        temperature=0.0,
        json_mode=True,
        tag="parse",
    )
    if not data:
        return _fallback(text, "LLM 请求失败或返回空")

    raw = _normalize_content(data["choices"][0]["message"].get("content", ""))
    try:
        parsed = _extract_json(raw)
    except Exception as e:
        return _fallback(text, f"JSON 解析失败: {e}")

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
        "source": "llm",
        "entities": entities,
    }


# ==================== 单颗解说 ====================

async def generate_narration(
    target_name: str,
    target_info: Dict[str, Any],
    user_style: str = "story",
    locale: str = "zh-CN",
) -> Dict[str, str]:
    fallback = {
        "short": target_name,
        "long": f"{target_name}是一颗值得观测的天体。",
        "fun_fact": None,
        "observation_tip": "抬头寻找最亮的那颗。",
    }
    if not _get_api_key():
        return fallback

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

    data = await _post_chat(
        messages=[
            {"role": "system", "content": "你是天文解说专家，输出必须为纯 JSON。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=_max_tokens_narration(),
        temperature=0.7,
        json_mode=True,
        tag="narr",
    )
    if not data:
        return fallback

    raw = _normalize_content(data["choices"][0]["message"].get("content", ""))
    try:
        parsed = _extract_json(raw)
    except Exception:
        return fallback

    return {
        "short": str(parsed.get("short", target_name)),
        "long": str(parsed.get("long", "")),
        "fun_fact": parsed.get("fun_fact"),
        "observation_tip": str(parsed.get("observation_tip", "")),
    }


# ==================== 批量解说 ====================

async def generate_batch_narration(
    stars_info: List[Dict[str, Any]],
    location_summary: str = "香港",
    user_style: str = "story",
    locale: str = "zh-CN",
) -> List[Dict[str, str]]:
    count = len(stars_info)

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

    if count == 0:
        return []
    if not _get_api_key():
        return _fallback_all()

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
- best_time：今晚最佳观测时段（如"21:00-23:00"或"整晚可见"）
- cultural_story：与该星相关的文化典故、神话故事或历史轶事（50-100字）。没有著名典故则填 null
- observation_tip：实用观测建议
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

    data = await _post_chat(
        messages=[
            {"role": "system", "content": "你是天文导览专家，输出必须为纯 JSON 数组。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=_max_tokens_batch(),
        temperature=0.7,
        json_mode=True,
        tag="batch",
    )
    if not data:
        return _fallback_all()

    raw = _normalize_content(data["choices"][0]["message"].get("content", ""))
    text = _strip_fence(raw)

    try:
        result = json.loads(text)
    except Exception:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(0))
            except Exception:
                return _fallback_all()
        else:
            return _fallback_all()

    if not isinstance(result, list) or len(result) != count:
        fallback = _fallback_all()
        for i in range(min(len(result), count)):
            if isinstance(result[i], dict):
                fallback[i].update({
                    k: result[i].get(k) for k in
                    ["short", "long", "best_time", "cultural_story",
                     "observation_tip", "fun_fact"]
                    if result[i].get(k) is not None
                })
        return fallback

    return result


# ==================== 快照导览骨架 ====================

# ★ Prompt 精简：去掉"硬性规则"措辞，减少推理模型的防御性思考；
#   末尾"直接开始写 {"对推理模型特别有效，能把它拉到输出阶段。
_SKELETON_SYSTEM_PROMPT = """你是天文导览规划师。根据用户给出的实时星空可见天体清单，规划 4-6 站的观览骨架。

只输出 JSON，不要 markdown，不要解释，不要思考过程。直接开始写 {。

JSON 格式：
{"title":"...","description":"...","steps":[{"title":"...","targets":[{"name_zh":"...","name_en":"...","type":"star","ra_deg":0,"dec_deg":0,"magnitude":0,"constellation":"...","altitude_deg":0}],"camera":{"center_ra_deg":0,"center_dec_deg":0,"fov_deg":30}}]}

规则：
1. 只用清单里的天体，禁止推荐地平线以下的。
2. 每步只放 1 个 target。
3. camera.center_ra_deg / center_dec_deg 必须与 target 的 ra_deg / dec_deg 一致。
4. type 只能是：star / planet / moon / messier / ngc / constellation。
"""


async def _generate_skeleton(snapshot_prompt: str) -> Optional[Dict[str, Any]]:
    if not _get_api_key():
        print("[tour] 未配置 LLM API Key，跳过快照导览")
        return None

    data = await _post_chat(
        messages=[
            {"role": "system", "content": _SKELETON_SYSTEM_PROMPT},
            {"role": "user", "content": snapshot_prompt},
        ],
        max_tokens=_max_tokens_skeleton(),
        temperature=0.3,
        timeout=180.0,           # ★ 骨架生成单独给 180s
        json_mode=True,
        tag="skeleton",
    )
    if not data:
        return None

    raw = _normalize_content(data["choices"][0]["message"].get("content", ""))
    try:
        parsed = _extract_json(raw)
    except Exception as e:
        print(f"[tour][skeleton] JSON 解析失败: {e}")
        return None

    if not isinstance(parsed, dict):
        print(f"[tour][skeleton] 返回非 dict: {type(parsed)}")
        return None
    if not isinstance(parsed.get("steps"), list) or not parsed["steps"]:
        print(f"[tour][skeleton] 缺少 steps: {str(parsed)[:200]}")
        return None

    return parsed


async def generate_tour_plan_from_snapshot(
    snapshot_prompt: str,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    skeleton = await _generate_skeleton(snapshot_prompt)
    if not skeleton:
        return None

    steps = skeleton.get("steps") or []

    valid_targets: List[Dict[str, Any]] = []
    for s in steps:
        ts = s.get("targets") or []
        t = ts[0] if ts else None
        if isinstance(t, dict) and (t.get("name_zh") or t.get("name_en")):
            valid_targets.append({
                "name_zh": t.get("name_zh") or t.get("name_en") or "",
                "name_en": t.get("name_en") or t.get("name_zh") or "",
                "constellation": t.get("constellation") or "",
                "magnitude": t.get("magnitude"),
                "altitude_deg": t.get("altitude_deg"),
                "azimuth_deg": t.get("azimuth_deg"),
            })

    if valid_targets:
        try:
            narrations = await generate_batch_narration(
                stars_info=valid_targets,
                location_summary="香港",
                user_style="story",
                locale="zh-CN",
            )
            for i, s in enumerate(steps):
                if i < len(narrations) and isinstance(narrations[i], dict):
                    n = narrations[i]
                    s["narration"] = {
                        "long": n.get("long") or "",
                        "best_time": n.get("best_time"),
                        "cultural_story": n.get("cultural_story"),
                        "observation_tip": n.get("observation_tip"),
                        "fun_fact": n.get("fun_fact"),
                    }
            print(f"[tour] ✅ 骨架 {len(steps)} 步，已生成 {len(narrations)} 段解说")
        except Exception as e:
            print(f"[tour] ⚠️ 批量解说生成失败，使用模板兜底: {e}")

    return skeleton