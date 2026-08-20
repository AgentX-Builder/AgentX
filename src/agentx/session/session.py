import uuid
import json
from typing import List, Dict, Any, Optional


class Session:
    def __init__(self, session_id: Optional[str] = None,
                 system_prompt: str = "You are a helpful assistant."):
        self.id = session_id or str(uuid.uuid4())[:8]
        self.system_prompt = system_prompt
        self.turn_count = 0
        self._messages: List[Dict[str, Any]] = []
        self._add_system_message()

    def _add_system_message(self):
        self._messages.append({"role": "system", "content": self.system_prompt})

    def add_user(self, content: str):
        """保存用户消息。"""
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        self._messages.append({"role": "assistant", "content": content})

    def add_assistant_tool_calls(self, tool_calls: list):
        """保存 assistant 的工具调用声明 (三段式历史的中间段)。"""
        self._messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        })

    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str):
        self._messages.append({
            "role": "tool", "content": result, "tool_call_id": tool_call_id
        })

    def get_llm_messages(self, max_history: int = 50) -> List[Dict[str, Any]]:
        """返回消息历史, 超过 max_history 时截断 (保留 system + 最近 N 条)。

        关键修复: 截断边界安全化 —— 绝不从 tool 结果消息处开头。
        tool 消息必须紧跟其对应的 assistant tool_calls, 若截断后第一条
        历史是 tool, 则向前并入更多消息直到边界闭合, 否则部分 LLM API
        会直接报 400 (孤立 tool 消息)。
        """
        msgs = self._messages
        if len(msgs) <= max_history:
            return msgs

        # 找到安全的起始位置: 向前回退直到不是 tool 消息
        start = len(msgs) - max_history
        while start < len(msgs) and msgs[start].get("role") == "tool":
            start -= 1
        if start <= 0:
            # 极端情况: 历史几乎全是 tool 消息, 全部保留(保证正确性优先)
            return msgs

        return [msgs[0]] + msgs[start:]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "system_prompt": self.system_prompt,
            "turn_count": self.turn_count,
            "messages": self._messages
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        s = cls(session_id=data["id"],
                system_prompt=data.get("system_prompt") or "You are a helpful assistant.")
        s.turn_count = data.get("turn_count", 0)
        s._messages = data.get("messages", [])
        # 保证 system 消息在首位
        if not s._messages or s._messages[0].get("role") != "system":
            s._messages.insert(0, {"role": "system", "content": s.system_prompt})
        return s
