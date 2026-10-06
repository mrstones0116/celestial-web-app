"""
Agent 核心：观察 → 决策 → 执行 循环
使用 OpenAI Function Calling，让 LLM 自主决定调哪个工具。
"""
import json
from typing import Any, Dict, List, Tuple

from .llm import chat_with_tools
from .prompts import SYSTEM_PROMPT, build_user_context
from .schemas import ToolCallRecord
from .session_store import agent_store
from .tools import get_tool_schemas, execute_tool

MAX_ITERATIONS = 5         # 最多 5 轮 tool-calling
MAX_TOOLS_PER_TURN = 3     # 单轮最多 3 个工具


async def run_agent(
    user_message: str,
    session_id: str,
    location: Dict[str, float] | None = None,
) -> Tuple[str, List[ToolCallRecord]]:
    """
    返回 (最终回答, 工具调用记录)
    """
    session = agent_store.get(session_id)
    if not session:
        session_id = agent_store.create()
        session = agent_store.get(session_id)

    # ========== 组装 messages ==========
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + build_user_context(location)}
    ]
    messages.extend(session["messages"])   # 历史对话
    messages.append({"role": "user", "content": user_message})

    tool_schemas = get_tool_schemas()
    tool_records: List[ToolCallRecord] = []

    # ========== 循环 ==========
    for iteration in range(MAX_ITERATIONS):
        msg = await chat_with_tools(
            messages=messages,
            tools=tool_schemas if tool_schemas else None,
            tag=f"agent#{iteration+1}",
        )
        if msg is None:
            return "抱歉，AI 服务暂时不可用，请稍后再试。", tool_records

        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""

        # ---------- 情形 A：没有工具调用 → 最终回答 ----------
        if not tool_calls:
            final = content or "（无回复）"
            # 落盘对话历史
            agent_store.append_messages(session_id, [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": final},
            ])
            return final, tool_records

        # ---------- 情形 B：有工具调用 → 执行，然后继续循环 ----------
        # 1. 把 assistant 的 tool_calls 消息加入
        assistant_msg: Dict[str, Any] = {
            "role": "assistant",
            "content": content or None,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_msg)

        # 2. 逐个执行工具（限制数量）
        for call in tool_calls[:MAX_TOOLS_PER_TURN]:
            fn = call.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except Exception:
                args = {}

            print(f"[agent] 调用工具: {name} args={args}")
            result = await execute_tool(name, args)

            tool_records.append(ToolCallRecord(
                tool_name=name,
                arguments=args,
                result=result.get("data") if result.get("ok") else None,
                error=result.get("error"),
            ))

            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False)[:6000],
            })

    # ========== 超过最大迭代 ==========
    return "抱歉，我思考了太多步。请把问题拆小一点再问我。", tool_records