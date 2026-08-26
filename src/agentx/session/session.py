import uuid
import json
from typing import List, Dict, Any, Optional


def estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数: 中文按 1 字 ≈ 1 token, 其他按 4 字符 ≈ 1 token。

    用于上下文压缩触发判断, 不需要精确。
    """
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3400" <= c <= "\u4dbf")
    other = len(text) - cjk
    return cjk + other // 4 + 1


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

    def add_assistant(self, content: str, reasoning_content: Optional[str] = None):
        msg = {"role": "assistant", "content": content}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        self._messages.append(msg)

    def add_assistant_tool_calls(self, tool_calls: list, reasoning_content: Optional[str] = None):
        """保存 assistant 的工具调用声明 (三段式历史的中间段)。"""
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        }
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        self._messages.append(msg)

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

    # ------------------------------------------------------------------
    # 上下文压缩: 超过 token 阈值时把旧消息摘要成一条, 避免长对话退化
    # ------------------------------------------------------------------
    @staticmethod
    def _message_tokens(m: Dict[str, Any]) -> int:
        """估算单条消息的 token 数(含 content / reasoning_content / tool_calls)。"""
        total = estimate_tokens(str(m.get("content", "")))
        total += estimate_tokens(str(m.get("reasoning_content", "")))
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            total += estimate_tokens(str(fn.get("name", "")))
            total += estimate_tokens(str(fn.get("arguments", "")))
        return total

    def estimate_total_tokens(self) -> int:
        """估算当前消息历史总 token 数(含 system)。"""
        return sum(Session._message_tokens(m) for m in self._messages)

    @staticmethod
    def _render_message(m: Dict[str, Any]) -> str:
        """把单条历史消息渲染成可摘要的纯文本。"""
        role = m.get("role", "?")
        content = m.get("content")
        if content:
            return f"[{role}] {content}"
        if m.get("tool_calls"):
            parts = []
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                parts.append(f"{fn.get('name', '?')}({fn.get('arguments', '')})")
            return f"[assistant->tool] {'; '.join(parts)}"
        if role == "tool":
            return f"[tool] {content}"
        return f"[{role}] {content}"

    def compress_old(self, llm, max_tokens: int, keep_ratio: float = 0.4,
                     max_retries: int = 2) -> bool:
        """把旧消息压缩成一条摘要, 保留最近 keep_ratio 比例的消息。

        llm: BaseLLM 实例, 用于生成摘要。
        返回 True=压缩成功, False=无需压缩或摘要失败(保持原样不阻塞)。
        """
        if len(self._messages) <= 4:
            return False

        # 从后往前累积 token, 保留最近 keep_ratio 阈值内的消息
        budget = max(int(max_tokens * keep_ratio), 2000)
        acc = 0
        keep_start = len(self._messages)
        for i in range(len(self._messages) - 1, 0, -1):  # 跳过 index 0 的 system
            acc += Session._message_tokens(self._messages[i])
            if acc > budget:
                break
            keep_start = i

        # 边界闭合: 截断后第一条绝不能是孤立的 tool 消息
        while keep_start < len(self._messages) and self._messages[keep_start].get("role") == "tool":
            keep_start -= 1
        if keep_start <= 1:
            return False  # 历史太短或全是工具消息, 不值得压缩

        old = self._messages[1:keep_start]
        recent = self._messages[keep_start:]
        summary = self._summarize(llm, old, max_retries=max_retries)
        if not summary or not summary.strip():
            return False

        summary_msg = {
            "role": "user",
            "content": "以下是先前对话的压缩摘要, 作为背景上下文参考, 不要把它当作当前问题:\n\n" + summary.strip(),
        }
        self._messages = [self._messages[0], summary_msg] + recent
        return True

    @staticmethod
    def _summarize(llm, messages: List[Dict[str, Any]], max_retries: int = 2) -> str:
        """调用 LLM 把一段历史消息压缩成要点摘要。失败返回空串。"""
        from agentx.llm.base import Message, Role

        history_text = "\n".join(Session._render_message(m) for m in messages)
        if len(history_text) > 40000:
            history_text = history_text[:40000] + "\n...(过长已截断)"

        sys_msg = Message(
            role=Role.SYSTEM,
            content=(
                "你是对话摘要器。把给定的一段 AgentX 历史对话压缩成中文要点摘要, "
                "保留所有关键决定、结论、用户偏好、未完成任务和重要数据。"
                "输出 200~400 字, 直接输出摘要正文, 不要解释, 不要用任何开场白。"
            ),
        )
        user_msg = Message(role=Role.USER, content="需要摘要的历史对话:\n\n" + history_text)

        for _ in range(max_retries):
            try:
                for delta, is_final, response in llm.chat_stream([sys_msg, user_msg], tools=[]):
                    if is_final:
                        return (response.content or "").strip()
            except Exception:
                continue
        return ""
