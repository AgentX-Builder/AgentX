"""思维链(reasoning_content)流式展示验证: OpenAI 兼容 + Ollama 通用支持。"""

import json

from agentx.llm.base import Message, Role, ReasoningDelta
from agentx.llm.openai import OpenAILLM
from agentx.llm.ollama import OllamaLLM


class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self._lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _collect(gen):
    """消费 chat_stream, 返回 (正文, 思维链片段列表, 最终响应)。"""
    content = []
    reasoning = []
    final = None
    for delta, is_final, response in gen:
        if isinstance(response, ReasoningDelta):
            reasoning.append(response.text)
        elif delta:
            content.append(delta)
        if is_final:
            final = response
    return "".join(content), "".join(reasoning), final


def test_openai_stream_reasoning_delta(monkeypatch):
    """OpenAI 兼容: 流式输出 reasoning_content 时 yield ReasoningDelta,
    最终响应带完整 reasoning_content, 且不影响正文收集。"""
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"先分析需求"}}]}'.encode(),
        'data: {"choices":[{"delta":{"reasoning_content":"再调用工具"}}]}'.encode(),
        'data: {"choices":[{"delta":{"content":"答案是 X"}}]}'.encode(),
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        b'data: [DONE]',
    ]

    def fake_post(url, json=None, headers=None, stream=False, timeout=None):
        return FakeStreamResponse(lines)

    monkeypatch.setattr("agentx.llm.openai.requests.post", fake_post)
    llm = OpenAILLM(model="deepseek-v4-flash",
                    base_url="https://api.deepseek.com", api_key="k")
    content, reasoning, final = _collect(
        llm.chat_stream([Message(role=Role.USER, content="hi")], tools=[])
    )
    assert reasoning == "先分析需求再调用工具"
    assert content == "答案是 X"
    assert final.reasoning_content == "先分析需求再调用工具"
    assert final.content == "答案是 X"


def test_ollama_stream_reasoning_delta(monkeypatch):
    """Ollama: 同样支持 reasoning_content(DeepSeek R1 / Qwen3 蒸馏系)。"""
    lines = [
        json.dumps({"message": {"reasoning_content": "先推理"}}).encode(),
        json.dumps({"message": {"reasoning_content": "再推理"}}).encode(),
        json.dumps({"message": {"content": "干活了"}}).encode(),
        json.dumps({"message": {"content": "完成"}}).encode(),
    ]

    def fake_post(url, json=None, headers=None, stream=False, timeout=None):
        return FakeStreamResponse(lines)

    monkeypatch.setattr("agentx.llm.ollama.requests.post", fake_post)
    llm = OllamaLLM(model="deepseek-r1:1.5b", base_url="http://127.0.0.1:11434")
    content, reasoning, final = _collect(
        llm.chat_stream([Message(role=Role.USER, content="hi")], tools=[])
    )
    assert reasoning == "先推理再推理"
    assert content == "干活了完成"
    assert final.reasoning_content == "先推理再推理"


def test_ollama_chat_nonstream_reasoning(monkeypatch):
    """Ollama 非流式: reasoning_content 进入 LLMResponse。"""

    def fake_post(url, json=None, headers=None, stream=False, timeout=None):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {
                    "content": "答案",
                    "reasoning_content": "思考过程",
                }}

        return Resp()

    monkeypatch.setattr("agentx.llm.ollama.requests.post", fake_post)
    llm = OllamaLLM(model="deepseek-r1:1.5b")
    resp = llm.chat([Message(role=Role.USER, content="hi")])
    assert resp.content == "答案"
    assert resp.reasoning_content == "思考过程"


def test_reasoning_delta_ignored_by_final_only_consumers():
    """只关心最终响应的消费方(agent/planner)应自动跳过 ReasoningDelta。"""
    from agentx.llm.base import LLMResponse

    def gen():
        yield ("", False, ReasoningDelta("思考..."))
        yield ("正文", False, None)
        yield ("", True, LLMResponse(content="正文"))

    content = ""
    final = None
    for delta, is_final, response in gen():
        if is_final:
            final = response
            break
        if delta:
            content += delta
    assert content == "正文"
    assert final.content == "正文"


def test_openai_convert_messages_omits_reasoning_content():
    """OpenAI 兼容端点不接受 assistant 历史消息带 reasoning_content,
    该字段只用于本地展示, 不得回发给 API。"""
    from agentx.llm.base import Message, Role

    llm = OpenAILLM(model="deepseek-v4-flash", base_url="https://api.deepseek.com", api_key="k")
    out = llm._convert_messages([
        Message(role=Role.SYSTEM, content="sys"),
        Message(role=Role.USER, content="hi"),
        Message(role=Role.ASSISTANT, content="答案", reasoning_content="思考过程"),
    ])
    assert out[2]["content"] == "答案"
    assert "reasoning_content" not in out[2]
