"""导入所有工具模块，触发 @register 装饰器执行。"""
from . import location   # noqa
from . import events     # noqa
from . import transport  # noqa

from .registry import get_tool_schemas, execute_tool, list_tools

__all__ = ["get_tool_schemas", "execute_tool", "list_tools"]