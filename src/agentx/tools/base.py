from typing import List, Dict, Any, Callable
import inspect


class ToolError(Exception):
    pass


class ToolSpec:
    def __init__(self, name: str, description: str,
                 input_schema: Dict[str, Any], func: Callable,
                 confirm: bool = False):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.func = func
        self.confirm = confirm


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        # 确认钩子: callable(name, arguments) -> bool
        # 返回 False 表示用户拒绝执行, 工具不会被调用
        self.confirm_hook = None

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def list_specs(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def call(self, name: str, arguments: Dict[str, Any]) -> str:
        if name not in self._tools:
            raise ToolError(f"Tool '{name}' not found.")
        spec = self._tools[name]
        if spec.confirm and self.confirm_hook is not None:
            if not self.confirm_hook(name, arguments):
                return "已取消执行（用户拒绝了该操作）"
        try:
            return spec.func(**arguments)
        except ToolError:
            raise
        except TypeError as e:
            raise ToolError(f"参数错误: {e}")
        except Exception as e:
            # 统一捕获: 文件不存在、权限错误等不再向上冒泡导致整个程序崩溃
            raise ToolError(f"工具执行失败: {e}")


# --- 工具结果统一截断 ---
# 防止大输出(整文件、超长 shell 输出)塞爆 LLM 上下文导致空回复 / 超时。
# agent.py / planner.py / cli 均复用此函数, 保证行为一致。
_TOOL_RESULT_LIMITS = {
    "run_shell_cmd": 4000,
    "read_file": 12000,
    "http_get_url": 6000,
    "grep_code": 6000,
    "find_files": 3000,
    "list_dir": 3000,
    "write_file": 1000,
    "install_package": 2000,
}
_DEFAULT_TOOL_LIMIT = 4000


def truncate_result(tool_name: str, result: Any) -> str:
    """工具结果统一截断, 保留首尾。非字符串自动转字符串。"""
    if not isinstance(result, str):
        result = str(result)
    limit = _TOOL_RESULT_LIMITS.get(tool_name, _DEFAULT_TOOL_LIMIT)
    if len(result) <= limit:
        return result
    keep_head = int(limit * 0.7)
    keep_tail = limit - keep_head - 30
    head = result[:keep_head]
    tail = result[-keep_tail:] if keep_tail > 0 else ""
    return (f"{head}\n...[输出已截断, 原长 {len(result)} 字符, 仅保留首尾]...\n{tail}")


def tool(func: Callable | None = None, *, confirm: bool = False):
    def wrap(f: Callable) -> ToolSpec:
        sig = inspect.signature(f)
        parameters = {"type": "object", "properties": {}, "required": []}
        for name, param in sig.parameters.items():
            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == bool:
                param_type = "boolean"
            elif param.annotation == float:
                param_type = "number"
            parameters["properties"][name] = {
                "type": param_type, "description": f"Parameter {name}"
            }
            if param.default is inspect.Parameter.empty:
                parameters["required"].append(name)

        return ToolSpec(
            name=f.__name__,
            description=f.__doc__ or f.__name__,
            input_schema=parameters,
            func=f,
            confirm=confirm,
        )

    if func is not None:
        return wrap(func)
    return wrap
