"""Configuration system — reads from ~/.agentx/config.toml with env var overrides."""

from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

DEFAULT_CONFIG_PATH = Path.home() / ".agentx" / "config.toml"


def _load_toml(path: Path) -> dict:
    if not path.exists() or tomllib is None:
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


class Config:
    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or DEFAULT_CONFIG_PATH
        self._file = _load_toml(self._path)
        self._data: dict = {}

    def _get(self, *keys: str, default=None):
        node = self._file
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def _env(self, key: str, default=None):
        return os.environ.get(key, default)

    # --- LLM 基础配置 ---
    @property
    def llm_provider(self) -> str:
        return self._env("AGENTX_LLM_PROVIDER") or self._get("llm", "provider", default="ollama")

    @property
    def llm_model(self) -> str:
        return self._env("AGENTX_LLM_MODEL") or self._get("llm", "model", default="phi4-mini")

    @property
    def llm_base_url(self) -> str:
        return self._env("AGENTX_LLM_BASE_URL") or self._get("llm", "base_url", default="http://localhost:11434")

    @property
    def llm_api_key(self) -> str | None:
        return self._env("AGENTX_LLM_API_KEY") or self._get("llm", "api_key", default=None)

    # --- 人设 (Persona) 配置 ---
    @property
    def persona(self) -> str:
        """自定义系统人设。为空时使用默认 system prompt。"""
        return self._get("agent", "persona", default="") or ""

    # --- 工具确认级别 ---
    @property
    def confirm_level(self) -> str:
        """工具确认级别: auto(危险命令才确认) / strict(所有 shell 都确认) / off(全自动)。"""
        level = self._get("tools", "confirm_level", default="auto") or "auto"
        return level if level in ("auto", "strict", "off") else "auto"

    # --- 上下文压缩 ---
    @property
    def context_max_tokens(self) -> int:
        """上下文 token 上限, 超过后自动压缩旧消息。默认 32K(手机端蒸馏模型窗口普遍 32K)。"""
        val = self._get("context", "max_tokens", default=32000)
        try:
            return int(val)
        except (TypeError, ValueError):
            return 32000

    # --- 界面 UI 配置 ---
    @property
    def ui_pet(self) -> bool:
        return self._get("ui", "pet", default=True)

    @property
    def ui_pet_name(self) -> str:
        return self._get("ui", "pet_name", default="小智")

    @property
    def ui_show_tokens(self) -> bool:
        return self._get("ui", "show_tokens", default=True)

    # --- 会话 (Session) 配置 ---
    @property
    def session_auto_save(self) -> bool:
        return self._get("session", "auto_save", default=True)

    @property
    def session_max_history(self) -> int:
        return self._get("session", "max_history", default=50)

    # --- 目录配置 ---
    @property
    def data_dir(self) -> Path:
        return Path.home() / ".agentx"

    @property
    def sessions_dir(self) -> Path:
        d = self.data_dir / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def memory_dir(self) -> Path:
        d = self.data_dir / "memory"
        d.mkdir(parents=True, exist_ok=True)
        return d
