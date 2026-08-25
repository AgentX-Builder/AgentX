"""权限分级 / 自定义人设 / 上下文压缩 功能验证。"""

from pathlib import Path
from tempfile import TemporaryDirectory

import agentx.cli.main as m
from agentx.agent import Agent
from agentx.llm.base import LLMResponse
from agentx.session.session import Session, estimate_tokens


# ── 权限分级 ──────────────────────────────────────────────────────────

def test_dangerous_command_auto_level():
    """auto 级别: 只读普通命令自动执行, 危险命令需确认。"""
    # 普通只读命令 -> 自动
    for cmd in [
        "ls -la",
        "cat foo.txt",
        "find . -name '*.py'",
        "grep -r error src",
        "echo hello",
        "pwd",
        "head -20 file.txt",
        "git status",
        "git diff",
        "curl https://example.com",
    ]:
        assert m._is_dangerous_command(cmd, "auto") is False, cmd

    # 危险命令 -> 需确认
    for cmd in [
        "rm -rf /tmp/x",
        "mv a b",
        "cp -r /etc /tmp/backup",
        "dd if=/dev/zero of=/tmp/x",
        "kill 1234",
        "pkill agentx",
        "chmod 777 /tmp/x",
        "chown root:root /tmp/x",
        "shutdown now",
        "apt-get install -y curl",
        "sudo rm -rf /",
        "git push origin main",
        "git reset --hard HEAD",
    ]:
        assert m._is_dangerous_command(cmd, "auto") is True, cmd


def test_dangerous_redirect_detection():
    """输出重定向写入文件 = 危险; 写入 /dev/null 不算。"""
    assert m._is_dangerous_command("echo hi > /tmp/log.txt", "auto") is True
    assert m._is_dangerous_command("cat a b > merged.txt", "auto") is True
    assert m._is_dangerous_command("echo hi >> /tmp/log.txt", "auto") is True
    assert m._is_dangerous_command("ls > /dev/null", "auto") is False
    assert m._is_dangerous_command("ls 2>/dev/null", "auto") is False


def test_confirm_level_modes():
    """strict=全部确认, off=永不确认。"""
    assert m._is_dangerous_command("ls", "strict") is True
    assert m._is_dangerous_command("rm -rf /", "off") is False


# ── 自定义人设 ────────────────────────────────────────────────────────

def test_agent_persona_overrides_default():
    a = Agent(provider="openai", model="m", base_url="http://x", api_key="k",
              persona="你是傲娇猫娘, 说话带喵。")
    assert a.system_prompt == "你是傲娇猫娘, 说话带喵。"
    b = Agent(provider="openai", model="m", base_url="http://x", api_key="k",
              persona=None)
    assert "agentx" in b.system_prompt  # 默认人设


def test_prompt_setup_writes_config():
    from agentx.config import Config
    with TemporaryDirectory() as d:
        path = Path(d) / "config.toml"
        cfg = Config(config_path=path)
        # 模拟多行输入
        inputs = iter(["你是猫娘", "说话带喵", ""])
        m._read_input = lambda prompt="": next(inputs)
        result = m._prompt_setup(cfg)
        assert result == "你是猫娘\n说话带喵"
        assert cfg.persona == "你是猫娘\n说话带喵"


# ── 上下文压缩 ────────────────────────────────────────────────────────

def test_estimate_tokens():
    assert estimate_tokens("你好世界") >= 4
    assert estimate_tokens("hello world") >= 1
    assert estimate_tokens("") == 0
    # 中文按 1 字≈1 token, 英文按 4 字符≈1 token
    assert estimate_tokens("a" * 100) == 26


class FakeLLM:
    """假 LLM: chat_stream 固定返回一条内容。"""

    def __init__(self, content="测试摘要内容"):
        self.content = content
        self.calls = 0

    def chat_stream(self, messages, tools=None):
        self.calls += 1
        yield "", True, LLMResponse(content=self.content)


def test_compress_old_replaces_old_messages():
    s = Session(session_id="c1")
    # 构造长会话: 30 条长消息
    for i in range(30):
        s.add_user(f"第{i}条用户消息 " + "内容" * 200)
        s.add_assistant(f"第{i}条回复 " + "结果" * 200)
    total_before = s.estimate_total_tokens()
    assert total_before > 10000

    fake = FakeLLM()
    ok = s.compress_old(fake, max_tokens=10000)
    assert ok is True
    assert fake.calls >= 1
    # 摘要消息在 system 之后
    assert s._messages[1]["role"] == "user"
    assert "压缩摘要" in s._messages[1]["content"]
    # 总消息数减少
    assert len(s._messages) < 60
    # 压缩后 token 显著下降
    assert s.estimate_total_tokens() < total_before


def test_compress_old_boundary_no_orphan_tool():
    """压缩后最近窗口第一条不能是孤立的 tool 消息。"""
    s = Session(session_id="c2")
    for i in range(20):
        s.add_user("问题" * 100 + str(i))
        s.add_assistant("答案" * 100)
    # 最近部分加入 assistant tool_calls + tool 结果 (三段式)
    s.add_assistant_tool_calls([
        {"id": "call_1", "type": "function",
         "function": {"name": "read_file", "arguments": '{"path":"/tmp/x"}'}}
    ])
    s.add_tool_result("call_1", "read_file", "文件内容" * 50)
    s.add_user("看完文件了吗" * 20)

    fake = FakeLLM()
    ok = s.compress_old(fake, max_tokens=5000)
    assert ok is True
    # 边界闭合: 摘要消息后第一条不能是 tool
    for i, msg in enumerate(s._messages):
        if msg["role"] == "tool":
            # tool 消息必须跟在其 assistant tool_calls 之后
            assert i > 0 and s._messages[i - 1].get("role") in ("assistant", "tool")


def test_compress_old_short_history_noop():
    s = Session(session_id="c3")
    s.add_user("你好")
    s.add_assistant("你好呀")
    fake = FakeLLM()
    assert s.compress_old(fake, max_tokens=100000) is False
    assert fake.calls == 0
