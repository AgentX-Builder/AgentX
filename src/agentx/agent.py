"""Core Agent loop — orchestrates LLM calls and tool execution."""

from __future__ import annotations

import json
import time
from typing import Any

from agentx.llm.base import Message, Role, ToolSpec
from agentx.tools.base import ToolRegistry, ToolError, tool, truncate_result


class Agent:
    def __init__(
        self,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.tool_registry = tool_registry or ToolRegistry()
        self._llm = None
        self.system_prompt = (
            "你是命令行工具 agentx 的执行引擎。\n"
            "规则:\n"
            "1. 禁止问候、禁止自我介绍、禁止解释你在做什么。\n"
            "2. 用户给指令 → 要么直接回答, 要么调用工具。\n"
            "3. 需要信息时调用工具, 拿到结果后只输出结论。\n"
            "4. 输出必须是纯内容, 不要任何开头语和结尾语。"
        )
        self.max_tool_rounds = 10

    @property
    def llm(self):
        if self._llm is None:
            from agentx.llm.registry import get_llm
            self._llm = get_llm(
                provider=self.provider,
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key,
            )
        return self._llm

    def run(self, task: str) -> str:
        messages = [
            Message(role=Role.SYSTEM, content=self.system_prompt),
            Message(role=Role.USER, content=task),
        ]
        tool_specs = self.tool_registry.list_specs()
        final_response = None

        # 多轮: 工具调用 -> 执行 -> 回传, 直到模型不再要工具
        for _ in range(self.max_tool_rounds):
            final_response = None
            for delta, is_final, response in self.llm.chat_stream(
                messages, tools=tool_specs
            ):
                if is_final:
                    final_response = response
                    break

            if not final_response or not final_response.tool_calls:
                break  # 没有工具调用 -> 最终答案

            # 三段式: 先保存 assistant 的调用声明
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
                except ToolError as e:
                    result = str(e)

                messages.append(Message(
                    role=Role.TOOL, content=truncate_result(tool_name, result),
                    tool_call_id=tc["id"],
                ))

        return (final_response.content if final_response else "") or "(no response)"

    # 2.0: 规划 -> 逐项执行 -> 汇总
    def plan_and_run(self, task: str, on_subtask=None) -> str:
        from agentx.planner import Planner
        planner = Planner(self.llm, self.tool_registry)
        return planner.execute_plan(task, on_subtask=on_subtask)

    def close(self):
        if self._llm:
            self._llm.close()
