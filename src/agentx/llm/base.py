from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum


class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    role: Role
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Usage] = None
    model: str = ""


class BaseLLM:
    def __init__(self, model: str, base_url: str, api_key: Optional[str] = None):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    def chat(self, messages: List[Message], tools: Optional[List[ToolSpec]] = None) -> LLMResponse:
        raise NotImplementedError

    def chat_stream(self, messages: List[Message], tools: Optional[List[ToolSpec]] = None):
        raise NotImplementedError

    def close(self):
        """关闭底层连接/资源。默认为无操作, 子类按需覆写。"""
        pass
