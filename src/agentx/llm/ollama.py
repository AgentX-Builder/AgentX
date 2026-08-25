import json
import requests
from typing import List, Optional, Dict, Any, Generator

from agentx.llm.base import BaseLLM, Message, Role, ToolSpec, LLMResponse, Usage, ReasoningDelta


class OllamaLLM(BaseLLM):
    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434",
                 api_key: Optional[str] = None):
        super().__init__(model, base_url, api_key)
        self.base_url = base_url.rstrip("/")

    def _normalize_tool_calls(self, tool_calls):
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
            result.append(msg)
        return result

    def _build_payload(self, messages: List[Message],
                       tools: Optional[List[ToolSpec]], stream: bool) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "stream": stream,
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": {
                    "name": t.name, "description": t.description,
                    "parameters": t.input_schema}}
                for t in tools
            ]
        return payload

    def chat(self, messages: List[Message],
             tools: Optional[List[ToolSpec]] = None) -> LLMResponse:
        url = f"{self.base_url}/api/chat"
        payload = self._build_payload(messages, tools, stream=False)

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            message = data.get("message", {})
            content = message.get("content", "")
            reasoning_content = message.get("reasoning_content")
            tool_calls = message.get("tool_calls")
            if tool_calls:
                tool_calls = self._normalize_tool_calls(tool_calls)
            return LLMResponse(content=content, tool_calls=tool_calls,
                               reasoning_content=reasoning_content)
        except requests.exceptions.ConnectionError:
            return LLMResponse(
                content="[Error] Failed to connect to Ollama. Please ensure 'ollama serve' is running.")
        except Exception as e:
            return LLMResponse(content=f"[Error] {e}")

    def chat_stream(self, messages: List[Message],
                    tools: Optional[List[ToolSpec]] = None) -> Generator:
        url = f"{self.base_url}/api/chat"
        payload = self._build_payload(messages, tools, stream=True)

        try:
            with requests.post(url, json=payload, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                buffer = ""
                reasoning_buffer = ""
                got_final = False
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "message" not in data:
                        continue
                    msg = data["message"]
                    if msg.get("reasoning_content"):
                        rc = msg["reasoning_content"]
                        reasoning_buffer += rc
                        yield ("", False, ReasoningDelta(rc))
                    if msg.get("content"):
                        buffer += msg["content"]
                        yield (msg["content"], False, None)
                    if msg.get("tool_calls"):
                        fake_resp = LLMResponse(
                            content=buffer,
                            tool_calls=self._normalize_tool_calls(msg["tool_calls"]),
                            reasoning_content=reasoning_buffer or None,
                        )
                        yield ("", True, fake_resp)
                        got_final = True
                if not got_final:
                    yield ("", True, LLMResponse(content=buffer,
                                                 reasoning_content=reasoning_buffer or None))
        except Exception as e:
            # 错误信息放进 response.content, 不再吞掉 -> 用户能看到真实错误而非空回复
            yield ("", True, LLMResponse(content=f"[Error] {e}"))

    def close(self):
        """Ollama 无需关闭的资源, 保持接口一致。"""
        pass
