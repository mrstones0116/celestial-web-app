from typing import Any, Dict, Callable, Awaitable, List

# 每个工具：{schema, handler}
_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register(name: str, schema: Dict[str, Any]):
    """装饰器：注册一个工具。"""
    def deco(fn: Callable[..., Awaitable[Any]]):
        _REGISTRY[name] = {"schema": schema, "handler": fn}
        return fn
    return deco


def get_tool_schemas() -> List[Dict[str, Any]]:
    """返回 OpenAI function calling 格式的工具列表。"""
    return [v["schema"] for v in _REGISTRY.values()]


async def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """执行工具，永远返回 {'ok': bool, 'data'|'error': ...}。"""
    entry = _REGISTRY.get(name)
    if not entry:
        return {"ok": False, "error": f"未知工具: {name}"}
    try:
        result = await entry["handler"](**(arguments or {}))
        return {"ok": True, "data": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def list_tools() -> List[str]:
    return list(_REGISTRY.keys())