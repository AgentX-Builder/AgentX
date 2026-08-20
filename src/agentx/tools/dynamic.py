"""动态工具生成 — 模型运行时通过 register_tool 自动创建并注册新工具。

机制说明:
    1. register_tool 以内置工具形式注册进 ToolRegistry。
    2. 模型想用新能力时, 调用 register_tool(name, description, code),
       把 Python 函数源码作为 code 传入。
    3. 系统编译源码得到函数对象, 按签名生成输入 schema, 注册为正式工具,
       之后即可像内置工具一样被 agent 调用。
"""

from __future__ import annotations

import inspect
import json
import math
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from agentx.tools.base import ToolRegistry, ToolSpec, ToolError, tool

# 动态工具执行环境预置的常用标准库, 避免模型生成的代码里用 os/json 等报 NameError。
_BUILTIN_NAMESPACE: Dict[str, Any] = {
    "os": os,
    "sys": sys,
    "json": json,
    "re": re,
    "math": math,
    "random": random,
    "datetime": datetime,
    "Path": Path,
}


def build_tool_spec(name: str, description: str, code: str) -> ToolSpec:
    """把 Python 函数源码编译为 ToolSpec。

    code 必须包含一个函数定义; 参数用类型注解(str/int/bool/float),
    用于自动生成输入 schema; 函数体执行环境预置常用标准库, 见 _BUILTIN_NAMESPACE。
    """
    ns: Dict[str, Any] = dict(_BUILTIN_NAMESPACE)
    try:
        exec(compile(code, f"<dynamic_tool:{name}>", "exec"), ns)
    except Exception as e:
        raise ToolError(f"动态工具编译失败: {e}")

    funcs = [v for v in ns.values() if inspect.isfunction(v)]
    if not funcs:
        raise ToolError("动态工具源码必须定义一个函数")

    spec = tool(funcs[0])
    spec.name = name
    spec.description = description
    return spec


def build_register_tool(registry: ToolRegistry) -> ToolSpec:
    """构造 register_tool 的 ToolSpec, 供模型动态注册新工具。"""

    def _register(name: str, description: str, code: str) -> str:
        if name in registry._tools:
            raise ToolError(f"工具已存在: {name}")
        spec = build_tool_spec(name, description, code)
        registry.register(spec)
        return f"已动态注册工具 [{name}]: {description}"

    return ToolSpec(
        name="register_tool",
        description=(
            "动态创建并注册一个新工具, 注册后即可像内置工具一样被调用。"
            "name: 新工具名(小写下划线, 如 read_config); "
            "description: 工具功能说明; "
            "code: Python 函数源码, 必须包含 def 语句, 参数需类型注解"
            "(str/int/bool/float, 带默认值的参数为可选)。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "新工具名称, 如 read_config"},
                "description": {"type": "string", "description": "工具功能说明"},
                "code": {"type": "string", "description": "Python 函数源码"},
            },
            "required": ["name", "description", "code"],
        },
        func=_register,
    )
