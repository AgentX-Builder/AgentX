"""AgentX 全链路测试 — 工具注册/执行、会话、agent 循环、规划、动态工具生成。"""

import json

from rich.console import Console

import agentx.cli.main as m
from agentx.agent import Agent
from agentx.config import Config
from agentx.llm.base import LLMResponse
from agentx.llm.openai import _is_repeating, _trim_repeating, OpenAILLM
from agentx.session.session import Session
from agentx.tools.base import ToolError, ToolRegistry, truncate_result


# ---------------------------------------------------------------------------
# 工具注册与执行
# ---------------------------------------------------------------------------

def make_registry():
    reg = ToolRegistry()
    m._register_builtin_tools(reg)
    return reg


def test_registry_has_all_tools():
    reg = make_registry()
    names = [s.name for s in reg.list_specs()]
    expect = ["read_file", "write_file", "list_dir", "run_shell_cmd",
              "http_get_url", "grep_code", "find_files", "list_cwd",
              "register_tool"]
    assert sorted(names) == sorted(expect)
    assert reg._tools["write_file"].confirm
    assert reg._tools["run_shell_cmd"].confirm


def test_file_tools():
    reg = make_registry()
    out = reg.call("list_cwd", {})
    assert "src" in out
    out = reg.call("list_dir", {"path": "/workspace/agentx/src"})
    assert "agentx" in out

    p = "/tmp/opencode/_pytest_agentx.txt"
    out = reg.call("write_file", {"path": p, "content": "hello agentx\n"})
    assert "Written" in out
    out = reg.call("read_file", {"path": p})
    assert "hello agentx" in out


def test_search_tools():
    reg = make_registry()
    out = reg.call("grep_code", {"pattern": "class ToolRegistry", "path": "/workspace/agentx/src"})
    assert "tools/base.py" in out
    out = reg.call("find_files", {"name_pattern": "main.py", "path": "/workspace/agentx/src"})
    assert "cli/main.py" in out


def test_http_tool():
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><body>agentx-http-ok</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        reg = make_registry()
        out = reg.call("http_get_url", {"url": f"http://127.0.0.1:{port}/"})
        assert "agentx-http-ok" in out
    finally:
        server.shutdown()


def test_shell_tool():
    reg = make_registry()
    out = reg.call("run_shell_cmd", {"command": "echo agentx-ok"})
    assert "agentx-ok" in out


def test_unknown_tool_raises():
    reg = make_registry()
    try:
        reg.call("no_such_tool", {})
        assert False, "should raise"
    except ToolError as e:
        assert "not found" in str(e)


def test_confirm_hook_rejects():
    reg = make_registry()
    reg.confirm_hook = lambda name, args: False
    out = reg.call("write_file", {"path": "/tmp/_x", "content": "x"})
    assert "已取消执行" in out


def test_truncate_result():
    long = "x" * 5000
    out = truncate_result("run_shell_cmd", long)
    assert len(out) < 5000 and "输出已截断" in out
    short = "hi"
    assert truncate_result("read_file", short) == short


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------

def test_session_roundtrip():
    s = Session(system_prompt="sys")
    s.add_user("hi")
    s.add_assistant("hello")
    data = s.to_dict()
    s2 = Session.from_dict(data)
    assert s2.id == s.id
    assert len(s2.get_llm_messages()) == 3


def test_session_truncation_safe():
    s = Session()
    s.add_user("u")
    s.add_assistant_tool_calls([{"id": "c1", "type": "function",
                                 "function": {"name": "x", "arguments": "{}"}}])
    s.add_tool_result("c1", "x", "result")
    s.add_user("u2")
    s.add_assistant_tool_calls([{"id": "c2", "type": "function",
                                 "function": {"name": "x", "arguments": "{}"}}])
    s.add_tool_result("c2", "x", "result2")
    msgs = s.get_llm_messages(max_history=4)
    first = msgs[1] if msgs[0].get("role") == "system" else msgs[0]
    assert first.get("role") != "tool"
    assert msgs[0].get("role") == "system"


# ---------------------------------------------------------------------------
# Agent 循环
# ---------------------------------------------------------------------------

class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat_stream(self, messages, tools=None):
        self.calls.append(list(messages))
        spec = self.responses.pop(0) if self.responses else LLMResponse(content="(done)")
        if callable(spec):
            resp = spec(messages)
        elif isinstance(spec, tuple):
            resp = LLMResponse(content=spec[0], tool_calls=spec[1])
        else:
            resp = spec
        yield ("", True, resp)

    def close(self):
        pass


def make_agent(reg, responses):
    agent = Agent(provider="fake", model="m", base_url="http://x", api_key=None,
                  tool_registry=reg)
    agent._llm = FakeLLM(responses)
    return agent


def test_agent_run_direct():
    reg = make_registry()
    agent = make_agent(reg, [LLMResponse(content="直接回答")])
    out = agent.run("hello")
    assert out == "直接回答"
    assert agent._llm.calls[0][0].role.value == "system"


def test_agent_run_tool_loop():
    reg = make_registry()

    def first_resp(messages):
        return LLMResponse(content=None, tool_calls=[{
            "id": "call_0", "type": "function",
            "function": {"name": "list_cwd", "arguments": "{}"},
        }])

    agent = make_agent(reg, [first_resp, LLMResponse(content="目录里有 src")])
    out = agent.run("看下目录")
    assert out == "目录里有 src"
    tool_msgs = [x for x in agent._llm.calls[1] if x.role.value == "tool"]
    assert any("src" in (x.content or "") for x in tool_msgs)


def test_agent_run_tool_error_no_crash():
    reg = make_registry()

    def err_resp(messages):
        return LLMResponse(content=None, tool_calls=[{
            "id": "call_0", "type": "function",
            "function": {"name": "list_dir", "arguments": '{"path": "/nonexistent_zzz"}'},
        }])

    agent = make_agent(reg, [err_resp, LLMResponse(content="处理完")])
    assert agent.run("x") == "处理完"


def test_planner_execute():
    reg = make_registry()

    def plan_resp(messages):
        return LLMResponse(content=None, tool_calls=[{
            "id": "p1", "type": "function",
            "function": {"name": "create_task_plan", "arguments": json.dumps({
                "tasks": [{"title": "任务一", "description": "查看目录"},
                          {"title": "任务二", "description": "再确认"}]},
                ensure_ascii=False)},
        }])

    def task1_resp(messages):
        return LLMResponse(content="子任务一完成")

    def task2_resp(messages):
        return LLMResponse(content="子任务二完成")

    agent = make_agent(reg, [plan_resp, task1_resp, task2_resp])
    subtasks = []
    out = agent.plan_and_run("大任务", on_subtask=lambda i, t, s, r: subtasks.append((i, t, s)))
    assert "任务一" in out and "任务二" in out
    assert len(subtasks) >= 4


# ---------------------------------------------------------------------------
# CLI 单轮对话 (_run_turn)
# ---------------------------------------------------------------------------

def test_run_turn_accumulates_history():
    cfg = Config()
    reg = make_registry()
    agent = make_agent(reg, [LLMResponse(content="你好啊")])
    console = Console(force_terminal=False)
    session = m._run_turn(console, m.pet, agent, "你好", None, cfg, "m")
    assert isinstance(session, Session)
    msgs = session.get_llm_messages()
    assert any(x.get("role") == "user" and x.get("content") == "你好" for x in msgs)
    assert any(x.get("role") == "assistant" and x.get("content") == "你好啊" for x in msgs)

    agent._llm = FakeLLM([LLMResponse(content="再回答")])
    session2 = m._run_turn(console, m.pet, agent, "再见", session, cfg, "m")
    assert sum(1 for x in session2.get_llm_messages() if x.get("role") == "user") == 2


def test_run_turn_tool_path():
    cfg = Config()
    reg = make_registry()
    agent = make_agent(reg, [
        LLMResponse(content=None, tool_calls=[{"id": "c0", "type": "function",
                                               "function": {"name": "list_cwd", "arguments": "{}"}}]),
        LLMResponse(content="目录已列出"),
    ])
    console = Console(force_terminal=False)
    session = m._run_turn(console, m.pet, agent, "列出目录", None, cfg, "m")
    roles = [x.get("role") for x in session.get_llm_messages()]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]


# ---------------------------------------------------------------------------
# tool_calls 规范化
# ---------------------------------------------------------------------------

def test_normalize_tool_calls():
    llm = OpenAILLM(model="m", base_url="http://x", api_key=None)
    n1 = llm._normalize_tool_calls([{"id": "a", "function": {"name": "f", "arguments": '{"x":1}'}}])
    assert n1[0]["function"]["name"] == "f" and n1[0]["id"] == "a"
    n2 = llm._normalize_tool_calls([{"name": "g", "arguments": {"y": 2}}])
    assert n2[0]["function"]["name"] == "g"
    assert isinstance(n2[0]["function"]["arguments"], str)


# ---------------------------------------------------------------------------
# 防复读
# ---------------------------------------------------------------------------

def test_repeat_detection():
    assert not _is_repeating("正常文本不重复" * 1 + "补充说明")
    assert _is_repeating("复读" * 40)
    assert len(_trim_repeating("复读" * 40)) >= 16


# ---------------------------------------------------------------------------
# 动态工具生成
# ---------------------------------------------------------------------------

def test_dynamic_tool_register_and_call():
    reg = make_registry()
    code = 'def double(x: int) -> str:\n    return f"{x}*2={x*2}"'
    out = reg.call("register_tool", {"name": "double", "description": "求两倍", "code": code})
    assert "已动态注册工具" in out
    assert reg.call("double", {"x": 21}) == "21*2=42"


def test_dynamic_tool_builtins_available():
    reg = make_registry()
    code = ("def count_py(path: str) -> str:\n"
            "    n = 0\n"
            "    for root, _, files in os.walk(path):\n"
            "        for f in files:\n"
            "            if f.endswith('.py'):\n"
            "                n += 1\n"
            "    return f'py: {n}'")
    reg.call("register_tool", {"name": "count_py", "description": "统计py", "code": code})
    assert "py:" in reg.call("count_py", {"path": "/workspace/agentx/src"})


def test_dynamic_tool_rejects():
    reg = make_registry()
    try:
        reg.call("register_tool", {"name": "bad", "description": "x", "code": "def broken(:\n"})
        assert False, "should reject bad code"
    except ToolError:
        pass
    try:
        reg.call("register_tool", {"name": "nofn", "description": "x", "code": "a = 1"})
        assert False, "should reject no function"
    except ToolError:
        pass

    reg.call("register_tool", {"name": "dup", "description": "x", "code": "def dup() -> str:\n    return 'd'"})
    try:
        reg.call("register_tool", {"name": "dup", "description": "x", "code": "def dup() -> str:\n    return 'd'"})
        assert False, "should reject duplicate"
    except ToolError:
        pass
