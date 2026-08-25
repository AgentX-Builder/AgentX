import json
import requests
from typing import List, Optional, Dict, Any, Generator

from agentx.llm.base import BaseLLM, Message, Role, ToolSpec, LLMResponse, Usage, ReasoningDelta

# 流式防退化: 检测尾部重复段落, 防止模型复读循环刷屏
REPEAT_MIN = 16   # 最小检测周期(字符)
REPEAT_MAX = 120  # 最大检测周期(字符)


def _find_repeat_period(buffer: str) -> int | None:
    """在尾部查找重复周期长度, 找到返回周期 n, 否则返回 None。

    扫描可能周期 n, 若尾部 n 字符与前面 n 字符相同即为循环。
    通过周期倍数对齐, 覆盖任意实际重复单元长度。
    """
    if len(buffer) < REPEAT_MIN * 2:
        return None
    tail = buffer[-REPEAT_MAX * 2:]
    for n in range(REPEAT_MIN, REPEAT_MAX + 1):
        if len(tail) >= n * 2 and tail[-n:] == tail[-n * 2:-n]:
            return n
    return None


def _is_repeating(buffer: str) -> bool:
    return _find_repeat_period(buffer) is not None


def _trim_repeating(buffer: str) -> str:
    """去掉尾部重复段, 循环清洗直到无重复, 返回截断后的文本。"""
    while True:
        n = _find_repeat_period(buffer)
        if not n:
            return buffer
        buffer = buffer[:-n]


class OpenAILLM(BaseLLM):
    def __init__(self, model: str, base_url: str, api_key: Optional[str] = None):
        super().__init__(model, base_url, api_key)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _normalize_tool_calls(self, tool_calls) -> List[Dict[str, Any]]:
        """统一 tool_calls 为 {id, type, function:{name, arguments}} 格式。

        与 OllamaLLM 保持一致: 兼容顶层 {name, arguments} 或
        {function:{...}} 两种上游格式, 并为缺失 id 生成兜底。
        """
        normalized = []
        for i, tc in enumerate(tool_calls):
            fn = tc.get("function", {})
            name = fn.get("name", tc.get("name", ""))
            args = fn.get("arguments", tc.get("arguments", {}))
            if isinstance(args, dict):
                args = json.dumps(args, ensure_ascii=False)
            normalized.append({
                "id": tc.get("id") or f"call_{i}",
                "type": "function",
                "function": {"name": name, "arguments": args},
            })
        return normalized

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        result = []
        for m in messages:
            msg = {"role": m.role.value, "content": m.content or ""}
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.reasoning_content:
                msg["reasoning_content"] = m.reasoning_content
            result.append(msg)
        return result

    def chat(self, messages: List[Message], tools: Optional[List[ToolSpec]] = None) -> LLMResponse:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "messages": self._convert_messages(messages), "stream": False}
        if tools:
            payload["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}} for t in tools]

        try:
            response = requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            content = message.get("content", "") or ""
            tool_calls = message.get("tool_calls")
            if tool_calls:
                tool_calls = self._normalize_tool_calls(tool_calls)
            return LLMResponse(content=content, tool_calls=tool_calls, reasoning_content=message.get("reasoning_content"))
        except Exception as e:
            return LLMResponse(content=f"[Error] {e}")

    def chat_stream(self, messages: List[Message], tools: Optional[List[ToolSpec]] = None) -> Generator:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "messages": self._convert_messages(messages), "stream": True}
        if tools:
            payload["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}} for t in tools]

        try:
            with requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                buffer = ""
                reasoning_buffer = ""
                tool_calls_acc = {}
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        if line.startswith(b"data: "):
                            data = json.loads(line[6:])
                        else:
                            continue
                    except json.JSONDecodeError:
                        continue
                    if "choices" not in data or not data["choices"]:
                        continue
                    choice = data["choices"][0]
                    delta = choice.get("delta", {})
                    if delta.get("reasoning_content"):
                        reasoning_buffer += delta["reasoning_content"]
                        yield ("", False, ReasoningDelta(delta["reasoning_content"]))
                    if delta.get("content"):
                        buffer += delta["content"]
                        if _is_repeating(buffer):
                            buffer = _trim_repeating(buffer)
                            tool_calls = None
                            if tool_calls_acc:
                                tool_calls = [{
                                    "id": v["id"] or f"call_{i}",
                                    "type": "function",
                                    "function": {"name": v["name"], "arguments": v["arguments"]},
                                } for i, v in sorted(tool_calls_acc.items())]
                            yield ("", True, LLMResponse(content=buffer, tool_calls=tool_calls, reasoning_content=reasoning_buffer))
                            return
                        yield (delta["content"], False, None)
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        cur = tool_calls_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            cur["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            cur["name"] = fn["name"]
                        if fn.get("arguments"):
                            cur["arguments"] += fn["arguments"]
                tool_calls = None
                if tool_calls_acc:
                    tool_calls = [{
                        "id": v["id"] or f"call_{i}",
                        "type": "function",
                        "function": {"name": v["name"], "arguments": v["arguments"]},
                    } for i, v in sorted(tool_calls_acc.items())]
                yield ("", True, LLMResponse(content=_trim_repeating(buffer), tool_calls=tool_calls, reasoning_content=reasoning_buffer))
        except Exception as e:
            # 错误信息放进 response.content, 不再吞掉 -> 用户能看到真实错误而非空回复
            yield ("", True, LLMResponse(content=f"[Error] {e}"))

    def close(self):
        """OpenAI 客户端无持久连接, 无需关闭。"""
        pass
