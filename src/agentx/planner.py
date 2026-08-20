"""Task planning layer — split a big task into subtasks, execute them one by one.

2.0 核心: 模型先拆任务清单 (create_task_plan 工具), 再逐项执行并汇总。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agentx.llm.base import Message, Role
from agentx.tools.base import ToolRegistry, ToolSpec, truncate_result


@dataclass
class TaskItem:
    id: int
    title: str
    description: str
    status: str = "pending"  # pending | running | done | failed
    result: str = ""


class Planner:
    """基于工具调用的规划器。

    流程:
        1. create_plan(task): 给模型一个 create_task_plan 工具,
           模型调用它把大任务拆成子任务清单, 我们解析参数得到 TaskItem 列表。
        2. execute_plan(task): 规划 -> 逐项执行(复用 agent 的工具循环) -> 汇总。
    """

    def __init__(self, llm, tool_registry: ToolRegistry):
        self.llm = llm
        self.tool_registry = tool_registry

    # ------------------------------------------------------------------
    # 规划工具: 模型通过调用它提交任务清单
    # ------------------------------------------------------------------
    def _plan_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name="create_task_plan",
            description=(
                "将用户的复杂任务拆解为有序的子任务清单。"
                "必须为每个子任务提供清晰的 title 和 description, "
                "description 要包含足够的执行细节。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "子任务标题"},
                                "description": {"type": "string", "description": "子任务执行细节"},
                            },
                            "required": ["title", "description"],
                        },
                    }
                },
                "required": ["tasks"],
            },
            func=self._noop,
        )

    @staticmethod
    def _noop(**kwargs) -> str:
        return "ok"

    # ------------------------------------------------------------------
    # 规划阶段: 让模型生成任务清单
    # ------------------------------------------------------------------
    def create_plan(self, task: str, max_rounds: int = 3) -> List[TaskItem]:
        messages = [
            Message(
                role=Role.SYSTEM,
                content=(
                    "你是任务规划器。用户会给一个复杂任务, "
                    "你必须调用 create_task_plan 工具把它拆成 2~6 个有序子任务。"
                    "子任务要可独立执行, 按依赖顺序排列。"
                ),
            ),
            Message(role=Role.USER, content=task),
        ]
        spec = self._plan_tool_spec()

        for _ in range(max_rounds):
            final_response = None
            for delta, is_final, response in self.llm.chat_stream(messages, tools=[spec]):
                if is_final:
                    final_response = response
                    break

            if final_response and final_response.tool_calls:
                for tc in final_response.tool_calls:
                    fn = tc.get("function", {})
                    if fn.get("name") != "create_task_plan":
                        continue
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    tasks = args.get("tasks", [])
                    items = []
                    for i, t in enumerate(tasks, start=1):
                        items.append(TaskItem(
                            id=i,
                            title=t.get("title", f"任务{i}"),
                            description=t.get("description", ""),
                        ))
                    if items:
                        return items

            # 模型没有调用规划工具 -> 无法拆解, 视为单任务
            if final_response and final_response.content:
                return [TaskItem(
                    id=1,
                    title="执行任务",
                    description=task,
                    status="running",
                )]

        return [TaskItem(id=1, title="执行任务", description=task, status="running")]

    # ------------------------------------------------------------------
    # 执行单个子任务 (复用 agent 的多轮工具循环)
    # ------------------------------------------------------------------
    def _run_subtask(self, messages: List[Message], max_rounds: int = 8) -> str:
        """对给定消息执行多轮工具循环, 返回最终文本。"""
        tool_specs = self.tool_registry.list_specs()
        final_response = None
        stream_buffer = ""

        for _ in range(max_rounds):
            final_response = None
            try:
                for delta, is_final, response in self.llm.chat_stream(messages, tools=tool_specs):
                    if is_final:
                        final_response = response
                        break
                    elif delta:
                        stream_buffer += delta
            except Exception:
                return stream_buffer or "(执行出错)"

            if not final_response or not final_response.tool_calls:
                break

            # 三段式: 保存 assistant 调用声明
            messages.append(Message(
                role=Role.ASSISTANT, content=None,
                tool_calls=final_response.tool_calls,
            ))

            # 执行本轮所有工具
            for tc in final_response.tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
                try:
                    result = self.tool_registry.call(tool_name, args)
                except Exception as e:
                    result = f"Error: {e}"
                messages.append(Message(
                    role=Role.TOOL, content=truncate_result(tool_name, result),
                    tool_call_id=tc["id"],
                ))

        if final_response and final_response.content:
            return final_response.content
        return stream_buffer or "(无输出)"

    # ------------------------------------------------------------------
    # 完整流程: 规划 -> 逐项执行 -> 汇总
    # ------------------------------------------------------------------
    def execute_plan(self, task: str, on_subtask=None) -> str:
        """执行完整规划流程, 返回汇总报告。on_subtask: 可选回调(id, title, status, result)。"""
        items = self.create_plan(task)

        if len(items) == 1 and items[0].status == "running":
            # 模型未拆解 -> 单任务直跑
            messages = [
                Message(role=Role.SYSTEM, content="你是命令行工具的执行引擎, 直接完成任务。"),
                Message(role=Role.USER, content=task),
            ]
            return self._run_subtask(messages)

        # 多任务: 逐项执行, 每项独立上下文
        for item in items:
            item.status = "running"
            if on_subtask:
                on_subtask(item.id, item.title, "running", "")

            messages = [
                Message(
                    role=Role.SYSTEM,
                    content=(
                        "你是命令行工具的干活引擎。正在执行总体规划中的一个子任务。"
                        "只完成该子任务, 拿到结论后直接输出, 不要提'规划'或'子任务'这些词。"
                    ),
                ),
                Message(role=Role.USER, content=f"任务: {item.title}\n说明: {item.description}"),
            ]
            item.result = self._run_subtask(messages)
            item.status = "done"

            if on_subtask:
                on_subtask(item.id, item.title, "done", item.result)

        # 汇总报告
        report = ["### 任务执行汇总\n"]
        for item in items:
            status_mark = "✓" if item.status == "done" else "✗"
            title_part = item.result.split("\n")[0] if item.result else ""
            report.append(f"- **{status_mark} {item.title}**")
            if title_part:
                report.append(f"  - {title_part}")
        report.append("")
        report.append("### 详细结果\n")
        for item in items:
            report.append(f"**{item.id}. {item.title}**\n")
            report.append((item.result or "(无输出)") + "\n")
        return "\n".join(report)
