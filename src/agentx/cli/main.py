"""CLI main entry — Typer app with beautiful terminal UI."""

from __future__ import annotations

import json
import os
import re
import fnmatch
import sys
import time
from pathlib import Path

try:
    import readline  # 启用 input() 的行编辑能力(退格删除/方向键/历史)
except ImportError:
    pass

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from rich.table import Table
from rich import box

from agentx.cli.ui import PetMascot
from agentx.cli.extras import (
    WorkHistory,
    MemoryStore,
    GachaSystem,
    RARITY_STYLE,
    gacha_animation,
    render_gacha,
    render_collection,
    render_work_list,
    render_memory,
)
from agentx.config import Config
from agentx.agent import Agent
from agentx.llm.base import Message, Role, ToolSpec, ReasoningDelta
from agentx.tools.base import ToolRegistry, ToolError, tool, truncate_result
from agentx.tools.dynamic import build_register_tool
from agentx.session.session import Session


app = typer.Typer(
    name="agentx",
    help="🐱 Terminal AI Agent — local, Ollama-first",
    no_args_is_help=True,
)
console = Console()
pet = PetMascot()


# ── chat (interactive) ──────────────────────────────────────────────

@app.command()
def chat(
    resume: str | None = typer.Option(None, "--resume", "-r", help="Resume a session by ID"),
    new: bool = typer.Option(False, "--new", help="Start a fresh session (skip auto-resume)"),
    model: str | None = typer.Option(None, "--model", "-m", help="Override model"),
):
    """Start an interactive chat session."""
    cfg = Config()
    llm_model = model or cfg.llm_model
    llm_provider = cfg.llm_provider
    llm_base_url = cfg.llm_base_url
    llm_api_key = cfg.llm_api_key
    persona = cfg.persona

    if resume:
        session = _load_session(cfg, resume)
    elif not new:
        session = _load_recent_session(cfg)
    else:
        session = None
    if session:
        console.print(f"[dim]Resumed session: {session.id} ({session.turn_count} turns)[/dim]")

    tool_registry = ToolRegistry()
    _register_builtin_tools(tool_registry)
    confirm_level = cfg.confirm_level
    tool_registry.confirm_hook = (
        lambda name, args, _level=confirm_level: _confirm_dangerous(name, args, _level)
    )

    agent = Agent(
        provider=llm_provider,
        model=llm_model,
        base_url=llm_base_url,
        api_key=llm_api_key,
        tool_registry=tool_registry,
        persona=persona or None,
    )

    _show_welcome(llm_model, llm_provider, session, cfg)

    work_history = WorkHistory(session.id) if session else None
    memory_store = MemoryStore()
    gacha = GachaSystem()
    _apply_pet_skin(pet, gacha)

    try:
        while True:
            try:
                user_input = _read_input(
                    f"\n[bold cyan]{_active_pet_label(gacha)}你[/bold cyan]"
                )
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]再见! 👋[/yellow]")
                break

            if not user_input.strip():
                continue

            cmd = user_input.strip()
            if cmd in ("/exit", "/quit", "exit", "quit"):
                if session:
                    _save_session(cfg, session)
                console.print("[yellow]再见! 👋[/yellow]")
                break

            if cmd in ("/clear",):
                session = Session(system_prompt=agent.system_prompt)
                work_history = WorkHistory(session.id)
                console.print("[dim]会话已清空[/dim]")
                continue

            if cmd in ("/tools",):
                _show_tools(tool_registry)
                continue

            if cmd in ("/model",):
                console.print(f"[dim]当前模型: {llm_model} ({llm_provider})[/dim]")
                continue

            if cmd in ("/config",):
                if _config_setup(cfg, in_chat=True):
                    llm_provider = cfg.llm_provider
                    llm_model = cfg.llm_model
                    llm_base_url = cfg.llm_base_url
                    llm_api_key = cfg.llm_api_key
                    agent.close()
                    agent = Agent(
                        provider=llm_provider,
                        model=llm_model,
                        base_url=llm_base_url,
                        api_key=llm_api_key,
                        tool_registry=tool_registry,
                        persona=persona or None,
                    )
                    console.print(f"\n[green]✔ 配置已生效, 当前模型: {llm_model} ({llm_provider})[/green]")
                continue

            if cmd == "/prompt" or cmd.startswith("/prompt "):
                if cmd.strip() == "/prompt clear":
                    _config_set(cfg, "agent.persona", "")
                    persona = ""
                    changed = True
                else:
                    new_persona = _prompt_setup(cfg)
                    if new_persona is not None:
                        persona = new_persona
                        changed = True
                    else:
                        changed = False
                if changed:
                    agent.close()
                    agent = Agent(
                        provider=llm_provider,
                        model=llm_model,
                        base_url=llm_base_url,
                        api_key=llm_api_key,
                        tool_registry=tool_registry,
                        persona=persona or None,
                    )
                    if session:
                        session.system_prompt = agent.system_prompt
                        if session._messages:
                            session._messages[0]["content"] = agent.system_prompt
                    preview = persona[:40] + "..." if len(persona) > 40 else persona
                    console.print(
                        f"[green]✔ 人设已生效[/green]"
                        + (f"[dim] ({preview})[/dim]" if persona else " [dim](恢复默认)[/dim]")
                    )
                continue

            if cmd in ("/sessions", "/list"):
                picked = _pick_session(cfg)
                if picked:
                    if session:
                        _save_session(cfg, session)
                    session = picked
                    work_history = WorkHistory(picked.id)
                    console.print(f"[dim]已切换到会话: {picked.id} ({picked.turn_count} turns)[/dim]")
                continue

            if cmd == "/work":
                if work_history is None:
                    console.print("[dim]当前会话还没有任何文件操作记录[/dim]")
                else:
                    render_work_list(console, work_history.list(), _read_input)
                continue

            if cmd == "/memory" or cmd.startswith("/memory "):
                keyword = cmd[len("/memory"):].strip()
                picked_id = render_memory(console, memory_store, keyword, _read_input)
                if picked_id:
                    if session:
                        _save_session(cfg, session)
                    session = _load_session(cfg, picked_id)
                    if session:
                        work_history = WorkHistory(session.id)
                        console.print(
                            f"[dim]已切换到会话: {picked_id} — 输入 /work 查看该会话文件操作记录[/dim]"
                        )
                continue

            if cmd == "/gacha":
                if gacha.remaining() <= 0:
                    console.print("[red]今日免费抽卡次数已用完(每天10次, 0点重置)[/red]")
                    continue
                gacha_animation(console)
                pet_result, err = gacha.pull()
                if err:
                    console.print(f"[red]{err}[/red]")
                    continue
                render_gacha(console, pet_result, gacha.remaining())
                console.print("[dim]提示: 输入 /collection 可挑选已抽到的宠物皮肤[/dim]")
                continue

            if cmd == "/collection":
                picked = render_collection(console, gacha, _read_input)
                if picked:
                    gacha.activate(picked)
                    _apply_pet_skin(pet, gacha)
                    console.print(f"[green]✔ 已切换宠物皮肤: {picked}[/green]")
                continue

            if cmd.startswith("/"):
                console.print("[red]未知命令。可用: /exit /clear /tools /model /config /prompt /sessions /work /memory /gacha /collection[/red]")
                continue

            # 关键修复: _run_turn 返回会话, 保证历史跨轮累积
            session = _run_turn(
                console, pet, agent, user_input, session, cfg, llm_model,
                work_history=work_history,
            )
            if work_history is None:
                work_history = WorkHistory(session.id)

    finally:
        agent.close()


@app.command()
def run(
    task: str = typer.Argument(..., help="Task to execute"),
    model: str | None = typer.Option(None, "--model", "-m"),
    plan: bool = typer.Option(False, "--plan", "-p", help="2.0: 先规划任务清单再逐项执行"),
):
    """Run a single task (non-interactive)."""
    cfg = Config()
    llm_model = model or cfg.llm_model

    tool_registry = ToolRegistry()
    _register_builtin_tools(tool_registry)
    agent = Agent(
        provider=cfg.llm_provider,
        model=llm_model,
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        tool_registry=tool_registry,
        persona=cfg.persona or None,
    )

    console.print(f"[dim]Task: {task}[/dim]\n")

    with console.status("[bold yellow]🧠 思考中...[/bold yellow]"):
        time.sleep(0.2)
        if plan:
            def on_subtask(i, title, status, result):
                if status == "running":
                    console.print(f"[cyan]  ▶ 任务{i}: {title}[/cyan]")
                else:
                    first_line = result.split("\n")[0] if result else ""
                    console.print(f"[green]  ✓ 任务{i} 完成: {first_line[:80]}[/green]")
            result = agent.plan_and_run(task, on_subtask=on_subtask)
        else:
            result = agent.run(task)

    console.print(Panel(Markdown(result), title="[bold green]结果[/bold green]", border_style="green"))
    agent.close()


@app.command("config")
def config_cmd(
    action: str = typer.Argument("list", help="list / setup / set / get"),
    key: str | None = typer.Option(None, "--key", "-k"),
    value: str | None = typer.Option(None, "--value", "-v"),
):
    """Manage configuration."""
    cfg = Config()

    if action == "list":
        console.print(f"[bold]Provider:[/bold] {cfg.llm_provider}")
        console.print(f"[bold]Model:[/bold] {cfg.llm_model}")
        console.print(f"[bold]Base URL:[/bold] {cfg.llm_base_url}")
        console.print(f"[bold]API Key:[/bold] {mask_api_key(cfg.llm_api_key)}")
        console.print(f"[bold]Persona:[/bold] {'on' if cfg.persona else 'off'}")
        console.print(f"[bold]Confirm level:[/bold] {cfg.confirm_level}")
        console.print(f"[bold]Context max tokens:[/bold] {cfg.context_max_tokens}")
        console.print(f"[bold]Pet:[/bold] {'on' if cfg.ui_pet else 'off'}")
        console.print(f"[bold]Config file:[/bold] {cfg._path}")
        return

    if action == "setup":
        _config_setup(cfg)
        return

    if action == "set" and key and value:
        _config_set(cfg, key, value)
        console.print(f"[green]Set {key} = {value}[/green]")
        return

    if action == "get" and key:
        val = _config_get(cfg, key)
        console.print(f"{key} = {val}")
        return

    console.print("[red]Usage: agentx config list | setup | set --key K --value V | get --key K[/red]")


@app.command("tools")
def tools_list():
    """List all available tools."""
    registry = ToolRegistry()
    _register_builtin_tools(registry)
    table = Table(title="Available Tools", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Parameters", style="dim")
    for spec in registry.list_specs():
        params = ", ".join(spec.input_schema.get("properties", {}).keys())
        table.add_row(spec.name, spec.description, params or "—")
    console.print(table)


def _register_builtin_tools(registry: ToolRegistry) -> None:
    """Register file/shell/http tools."""
    import subprocess
    import httpx

    def run_shell(command: str) -> str:
        try:
            result = subprocess.run(command, shell=True,
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout.strip()
            if result.returncode != 0 and result.stderr.strip():
                output = (output + "\n" if output else "") + f"[stderr] {result.stderr.strip()}"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: command timed out (30s)"
        except Exception as e:
            return f"Error: {e}"

    def http_get(url: str) -> str:
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            return resp.text[:3000]
        except Exception as e:
            return f"Error: {e}"

    fs = _FileSystem()

    @tool
    def read_file(path: str) -> str:
        """读取指定文件的文本内容(UTF-8, 解码失败处以替换符代替)。"""
        return fs.read_file(path)

    @tool(confirm=True)
    def write_file(path: str, content: str) -> str:
        """把文本内容写入指定文件(自动创建父目录)。"""
        return fs.write_file(path, content)

    @tool
    def list_dir(path: str = ".") -> str:
        """列出指定目录下的条目, 目录用 [DIR] 标注。"""
        return fs.list_dir(path)

    @tool(confirm=True)
    def run_shell_cmd(command: str) -> str:
        """在本地 shell 执行命令并返回输出(超时 30s)。"""
        return run_shell(command)

    @tool
    def http_get_url(url: str) -> str:
        """对 URL 发起 HTTP GET 请求并返回响应文本(前 3000 字符)。"""
        return http_get(url)

    @tool
    def grep_code(pattern: str, path: str = ".") -> str:
        """在项目中按正则搜索代码内容, 返回文件路径+行号+匹配行"""
        return fs.grep_code(pattern, path)

    @tool
    def find_files(name_pattern: str, path: str = ".") -> str:
        """按文件名模式查找文件(支持 * ? 通配符), 返回匹配的文件路径列表"""
        return fs.find_files(name_pattern, path)

    @tool
    def list_cwd() -> str:
        """查看当前目录下的所有文件和子目录(递归展开全部层级), 无需参数"""
        return fs.list_tree(".")

    for spec in [read_file, write_file, list_dir, run_shell_cmd, http_get_url,
                 grep_code, find_files, list_cwd]:
        registry.register(spec)

    # 动态工具生成入口: 模型可调用 register_tool 运行时创建新工具
    registry.register(build_register_tool(registry))


class _FileSystem:
    def read_file(self, path: str) -> str:
        path = os.path.expanduser(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> str:
        p = Path(os.path.expanduser(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"

    def list_dir(self, path: str) -> str:
        p = Path(os.path.expanduser(path))
        if not p.exists():
            return f"Error: {path} does not exist"
        items = []
        for item in sorted(p.iterdir()):
            prefix = "[DIR]" if item.is_dir() else "     "
            items.append(f"  {prefix} {item.name}")
        return "\n".join(items) if items else "(empty)"

    def list_tree(self, path: str) -> str:
        """递归列出 path 下的所有文件和目录, 目录用 [DIR] 标注。"""
        p = Path(os.path.expanduser(path))
        if not p.exists():
            return f"Error: {path} does not exist"
        lines = []
        for root, dirs, files in os.walk(str(p)):
            dirs.sort()
            files.sort()
            rel = os.path.relpath(root, str(p))
            base = "" if rel == "." else rel + os.sep
            for d in dirs:
                lines.append(f"[DIR] {base}{d}/")
            for f in files:
                lines.append(f"      {base}{f}")
        return "\n".join(lines) if lines else "(empty)"

    # 2.0: 代码搜索工具
    _SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv",
                  "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache"}

    def _walk(self, path: str):
        """递归遍历, 跳过常见无关目录。"""
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            yield root, files

    def grep_code(self, pattern: str, path: str = ".") -> str:
        p = Path(os.path.expanduser(path))
        if not p.exists():
            return f"Error: {path} does not exist"
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"Error: 正则无效 - {e}"

        MAX_MATCHES = 50
        matches = []
        for root, files in self._walk(str(p)):
            for fname in files:
                fp = Path(root) / fname
                if fp.suffix not in {".py", ".js", ".ts", ".jsx", ".tsx",
                                     ".go", ".rs", ".java", ".c", ".cpp",
                                     ".h", ".md", ".txt", ".toml", ".json",
                                     ".yaml", ".yml", ".sh", ".html", ".css"}:
                    continue
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        for lineno, line in enumerate(f, start=1):
                            if rx.search(line):
                                matches.append(f"{fp}:{lineno}: {line.rstrip()[:200]}")
                                if len(matches) >= MAX_MATCHES:
                                    return "\n".join(matches) + "\n...(结果过多已截断)"
                except (OSError, UnicodeDecodeError):
                    continue
        return "\n".join(matches) if matches else f"无匹配: {pattern}"

    def find_files(self, name_pattern: str, path: str = ".") -> str:
        p = Path(os.path.expanduser(path))
        if not p.exists():
            return f"Error: {path} does not exist"
        try:
            rx = re.compile(fnmatch.translate(name_pattern))
        except re.error:
            return f"Error: 无效的模式 {name_pattern}"

        MAX_RESULTS = 100
        results = []
        for root, files in self._walk(str(p)):
            for fname in files:
                if rx.match(fname):
                    results.append(str(Path(root) / fname))
                    if len(results) >= MAX_RESULTS:
                        return "\n".join(results) + "\n...(结果过多已截断)"
        return "\n".join(results) if results else f"未找到: {name_pattern}"


# 权限分级: 只对会修改系统/文件/数据的操作要求确认, 只读普通命令自动执行
_DANGEROUS_CMDS = {
    # 删除/移动/复制/清空
    "rm", "rmdir", "mv", "cp", "dd", "truncate", "shred", "unlink",
    # 文件系统/磁盘/分区
    "mkfs", "mkfs.ext2", "mkfs.ext3", "mkfs.ext4", "mkfs.xfs", "fdisk",
    "parted", "gdisk", "mount", "umount", "lvm", "pvcreate", "vgcreate",
    # 系统电源/内核/引导
    "shutdown", "reboot", "poweroff", "halt", "init", "telinit",
    "modprobe", "insmod", "rmmod", "sysctl", "update-grub", "grub-install",
    # 进程/权限/用户
    "kill", "killall", "pkill", "chmod", "chown", "chgrp",
    "useradd", "userdel", "usermod", "groupadd", "groupdel", "passwd",
    "visudo", "chroot",
    # 防火墙/网络管理
    "iptables", "ip6tables", "nft", "nftables", "ufw", "firewall-cmd",
    # 包管理器(修改系统)
    "apt", "apt-get", "yum", "dnf", "zypper", "pacman", "dpkg", "rpm",
    # git 破坏性操作
    "git-reset", "git-clean",
    # 提权
    "sudo", "su",
}

# 命中即确认的 git 子命令
_DANGEROUS_GIT = {"reset", "clean", "push", "rebase", "merge", "cherry-pick",
                  "branch", "tag", "checkout", "restore", "stash"}


def _is_dangerous_command(cmd: str, level: str = "auto") -> bool:
    """权限分级: 判断 shell 命令是否需要用户确认。

    level=strict: 所有 shell 命令都确认。
    level=off: 永不确认。
    level=auto: 命中危险黑名单或含文件重定向写入时才确认。
    """
    if level == "off":
        return False
    if level == "strict":
        return True
    cmd = cmd.strip()
    if not cmd:
        return False

    # 输出重定向到文件(排除 /dev/null 与 2>&1) = 写操作
    for mtch in re.finditer(r"(?:^|[\s;&|])(?:[12]?[>]+)\s*(\S+)", cmd):
        target = mtch.group(1).strip()
        if target.startswith("/dev/null"):
            continue
        if target.startswith("&"):
            continue
        return True

    # 取命令头(第一个词), 支持 sudo/doas 前缀递归判断
    head = re.split(r"[\s;&|]+", cmd, maxsplit=1)[0].lower()
    if head in ("sudo", "doas"):
        rest = re.split(r"[\s;&|]+", cmd, maxsplit=1)[1] if " " in cmd else ""
        return _is_dangerous_command(rest, level)
    if head in _DANGEROUS_CMDS:
        return True
    # git 子命令: git reset/clean/push 等需要确认
    if head == "git":
        parts = re.split(r"[\s;&|]+", cmd)
        if len(parts) > 1 and parts[1].replace("-", "").lower() in _DANGEROUS_GIT:
            return True
    return False


def _confirm_dangerous(name: str, arguments: dict, level: str = "auto") -> bool:
    """危险操作确认钩子。返回 True=执行, False=取消。"""
    if name == "run_shell_cmd":
        cmd = arguments.get("command", "")
        if not _is_dangerous_command(cmd, level):
            return True  # 普通只读命令自动执行, 不打扰
        console.print(Panel(
            f"[bold yellow]将执行 shell 命令:[/bold yellow]\n[red]{cmd}[/red]",
            title="⚠ 危险操作确认",
            border_style="yellow",
        ))
    elif name == "write_file":
        path = arguments.get("path", "?")
        console.print(Panel(
            f"[bold yellow]将写入文件:[/bold yellow] [red]{path}[/red]",
            title="⚠ 危险操作确认",
            border_style="yellow",
        ))
    try:
        return typer.confirm("[yellow]是否执行?[/yellow]", default=False)
    except (KeyboardInterrupt, EOFError):
        return False


def _show_welcome(model: str, provider: str, session, cfg=None):
    pet.set_state("idle")
    console.clear()
    api_key = mask_api_key(cfg.llm_api_key) if cfg else "(未设置)"
    console.print(Panel.fit(
        "[bold cyan]🐱 AgentX[/bold cyan]\n"
        "[dim]Terminal AI Agent — local, Ollama-first[/dim]\n\n"
        f"[bold]Model:[/bold] {model}  [bold]Provider:[/bold] {provider}\n"
        f"[bold]API Key:[/bold] {api_key}\n"
        f"[bold]Session:[/bold] {session.id if session else 'new'}",
        border_style="cyan",
        box=box.DOUBLE,
    ))
    console.print("[dim]Commands: /exit /clear /tools /model /config /prompt /sessions /work /memory /gacha /collection | 直接输入开始对话[/dim]\n")


def _to_provider_messages(session: Session, max_history: int = 50) -> list[Message]:
    """把 session 历史转成 provider 消息列表 (带历史截断)。"""
    return [
        Message(role=Role(m["role"]),
                content=m.get("content"),
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id"),
                reasoning_content=m.get("reasoning_content"))
        for m in session.get_llm_messages(max_history)
    ]


def _run_turn(console, pet, agent, user_input, session, cfg, llm_model,
              work_history=None) -> Session:
    """处理一轮对话, 返回(可能更新的)会话。

    完整 agent 循环:
        用户消息 -> LLM -> (工具调用? 执行->回传->继续 : 最终答案)
    """
    if session is None:
        session = Session(system_prompt=agent.system_prompt)

    # 关键修复 1: 用户输入必须进会话, 模型才能收到问题
    session.add_user(user_input)

    # 上下文自动压缩: 估算 token 超阈值时把旧消息摘要成一条,
    # 防止长对话上下文膨胀导致回答退化/断断续续
    max_tokens = int(getattr(cfg, "context_max_tokens", 100000) or 100000)
    try:
        if session.estimate_total_tokens() > max_tokens:
            console.print(f"[dim]上下文超限(>{max_tokens} tokens), 自动压缩中...[/dim]")
            before = session.estimate_total_tokens()
            if session.compress_old(agent.llm, max_tokens):
                console.print(
                    f"[dim]✔ 已压缩 {before} → {session.estimate_total_tokens()} tokens[/dim]"
                )
            else:
                console.print("[dim]压缩未执行, 保持原上下文[/dim]")
    except Exception as e:
        console.print(f"[dim]上下文压缩跳过: {e}[/dim]")

    tool_specs = agent.tool_registry.list_specs()
    max_history = getattr(cfg, "session_max_history", 50) or 50
    messages = _to_provider_messages(session, max_history)

    full_text = ""
    tool_calls_made = []
    final_response = None
    stream_buffer = ""

    pet.set_state("thinking")
    console.print(pet.render())

    # 多轮工具循环
    for _ in range(agent.max_tool_rounds):
        # 调用 LLM: 思维链流式闪现(Live 局部刷新), 正文静默累积, 最终答案一次性完整输出
        final_response = None
        stream_buffer = ""
        thinking_buffer = ""
        console.print("[dim]思考中...[/dim]")
        try:
            with Live(console=console, refresh_per_second=8, screen=False) as live:
                for delta, is_final, response in agent.llm.chat_stream(messages, tools=tool_specs):
                    # 思维链: 实时闪现, 不整屏重绘, 进入正文后停止
                    if isinstance(response, ReasoningDelta):
                        thinking_buffer += response.text
                        live.update(Panel(
                            Text(f"思考中...\n\n{thinking_buffer}", style="dim italic"),
                            title="[dim]思维链[/dim]",
                            border_style="dim",
                            title_align="left",
                        ))
                        continue
                    if is_final:
                        final_response = response
                        break
                    elif delta:
                        stream_buffer += delta
        except Exception as e:
            pet.set_state("error")
            console.print(f"[red]Error: {e}[/red]")
            return session

        if not final_response or not final_response.tool_calls:
            break  # 没有工具调用 -> 最终答案

        # 关键修复 2: 保存 assistant 的调用声明 (三段式)
        session.add_assistant_tool_calls(final_response.tool_calls,
                                         reasoning_content=getattr(final_response, "reasoning_content", None))

        # 执行本轮所有工具
        pet.set_state("working")
        console.print()
        for tc in final_response.tool_calls:
            tool_name = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, TypeError):
                arguments = {}

            arg_str = ", ".join(f"{k}={repr(v)[:40]}" for k, v in arguments.items())
            console.print(f"[yellow]🔧 {tool_name}({arg_str})[/yellow]")

            t_start = time.time()
            try:
                result = agent.tool_registry.call(tool_name, arguments)
            except ToolError as e:
                result = f"Error: {e}"
            elapsed = time.time() - t_start

            preview = result[:200].replace("\n", " ")
            console.print(f"[dim]   ⏱ {elapsed:.2f}s → {preview}[/dim]")

            if work_history is not None:
                _record_work_history(work_history, tool_name, arguments)

            session.add_tool_result(tc["id"], tool_name, truncate_result(tool_name, result))
            tool_calls_made.append(tc)

        # 工具结果已进 session, 更新消息列表继续循环
        messages = _to_provider_messages(session, max_history)

    # 最终答案: 优先 final.content, 为空则回退流式累积
    if final_response and final_response.content:
        full_text = final_response.content
    else:
        full_text = stream_buffer

    # 思考模式兜底: 若最终 content 为空但模型只输出了思维链, 展示思维链避免空屏
    if not full_text.strip():
        rc = getattr(final_response, "reasoning_content", None) if final_response else None
        if rc and rc.strip():
            full_text = f"[思维过程]\n{rc}"

    # 关键修复 4: 空回复自动重试 (最多 3 次, 间隔递增)
    # DeepSeek V4 思考模式 / 高负载时段偶发空响应, 重试可显著降低用户可见空回复
    retries = 3
    attempt = 0
    while not full_text.strip() and attempt < retries:
        attempt += 1
        console.print(f"[dim]检测到空回复, 自动重试 ({attempt}/{retries})...[/dim]")
        time.sleep(1.0 + attempt * 0.5)
        retry_messages = _to_provider_messages(session, max_history=10)
        retry_messages.append(Message(
            role=Role("user"),
            content="请基于以上对话内容直接输出最终结论(中文), 不要调用任何工具, 不要复述过程。",
        ))
        retry_text = ""
        try:
            for delta, is_final, response in agent.llm.chat_stream(retry_messages, tools=[]):
                if is_final:
                    retry_text = response.content or ""
                    break
                retry_text += delta
        except Exception:
            retry_text = ""
        if retry_text.strip():
            full_text = retry_text

    pet.set_state("done")
    console.clear()
    console.print(pet.render())

    if tool_calls_made:
        for tc in tool_calls_made:
            try:
                args = json.loads(tc["function"]["arguments"])
            except Exception:
                args = {}
            arg_str = ", ".join(f"{k}={repr(v)[:30]}" for k, v in args.items())
            console.print(f"[yellow]  🔧 {tc['function']['name']}({arg_str})[/yellow]")

    console.print(Panel(
        Markdown(full_text) if full_text.strip() else Text("(空回复)"),
        title="[bold cyan]小智[/bold cyan]",
        border_style="cyan",
        title_align="left",
    ))

    if full_text.strip():
        session.add_assistant(full_text,
                              reasoning_content=getattr(final_response, "reasoning_content", None))
    session.turn_count += 1

    tokens = final_response.usage.total_tokens if final_response and final_response.usage else 0
    console.print(status_bar(llm_model, session.id, tokens))

    if cfg.session_auto_save:
        _save_session(cfg, session)

    return session  # 关键修复 3: 返回会话, 历史跨轮保留


def _read_input(prompt_markup: str) -> str:
    """读取一行输入并去掉首尾空白。

    用 input() 替代 typer.prompt: 后者在部分终端(Termux)下退格键
    会被吞掉导致打错字删不掉, readline 提供完整的行编辑能力。
    """
    console.print(prompt_markup, end="")
    try:
        return input().strip()
    except (KeyboardInterrupt, EOFError):
        raise


def _active_pet_label(gacha) -> str:
    """返回活跃宠物提示符前缀 (含稀有度颜色), 无宠物时返回空串。"""
    active = gacha.active_pet()
    if not active:
        return ""
    style = RARITY_STYLE.get(active["rarity"], "cyan")
    glow = " ✨" if active["god"] else ""
    return f"[bold {style}]{active['name']}[/bold {style}]({active['rarity']}){glow} "


def _apply_pet_skin(pet, gacha) -> None:
    """把抽卡获得的皮肤应用到界面宠物形象。"""
    active = gacha.active_pet()
    art = gacha.active_pet_art()
    pet.apply_skin(art, active["name"] if active else None)


def _record_work_history(work_history, tool_name: str, arguments: dict) -> None:
    """把文件类工具调用写入当前会话的工作记录。"""
    if tool_name == "write_file":
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        exists = os.path.exists(os.path.expanduser(path))
        work_history.record("write_file", path, "修改" if exists else "创建", content=content)
    elif tool_name == "read_file":
        path = arguments.get("path", "")
        work_history.record("read_file", path, "读取")
    elif tool_name == "run_shell_cmd":
        command = arguments.get("command", "")
        work_history.record("run_shell_cmd", command, "命令")


def _load_recent_session(cfg):
    """加载最近一次保存的会话, 没有则返回 None。"""
    files = sorted(
        cfg.sessions_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None
    return _load_session(cfg, files[0].stem)


def _pick_session(cfg):
    """列出最近 10 条会话, 用户选择序号后返回对应会话。"""
    from datetime import datetime
    files = sorted(
        cfg.sessions_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]
    if not files:
        console.print("[dim]没有任何历史会话[/dim]")
        return None
    console.print("[bold]历史会话:[/bold]")
    for i, f in enumerate(files, start=1):
        ts = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        console.print(f"[cyan]{i}.[/cyan] {f.stem}  [dim]({ts})[/dim]")
    try:
        choice = _read_input("输入序号进入会话 (回车取消)")
    except (KeyboardInterrupt, EOFError):
        return None
    if not choice:
        return None
    try:
        idx = int(choice)
    except ValueError:
        console.print("[red]无效输入, 请输入序号[/red]")
        return None
    if not (1 <= idx <= len(files)):
        console.print("[red]序号超出范围[/red]")
        return None
    return _load_session(cfg, files[idx - 1].stem)


def _load_session(cfg, session_id):
    path = cfg.sessions_dir / f"{session_id}.json"
    if not path.exists():
        for f in cfg.sessions_dir.glob(f"{session_id}*.json"):
            path = f
            break
        else:
            console.print(f"[red]Session not found: {session_id}[/red]")
            return None
    try:
        data = json.loads(path.read_text())
        return Session.from_dict(data)
    except Exception as e:
        console.print(f"[red]Failed to load session: {e}[/red]")
        return None


def _save_session(cfg, session):
    path = cfg.sessions_dir / f"{session.id}.json"
    path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2))
    try:
        MemoryStore().save(session)
    except Exception:
        pass


def _show_tools(registry):
    table = Table(title="Registered Tools", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Parameters", style="dim")
    for spec in registry.list_specs():
        params = ", ".join(spec.input_schema.get("properties", {}).keys())
        table.add_row(spec.name, spec.description, params or "—")
    console.print(table)


def mask_api_key(key):
    """API Key 掩码显示: 保留前4位与后2位, 中间打码。空值返回提示。"""
    if not key:
        return "(未设置)"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * (len(key) - 6)}{key[-2:]}"


def _prompt_setup(cfg) -> str | None:
    """交互式编辑系统人设: 多行输入, 空行结束。返回新 persona, 取消/不变返回 None。"""
    current = cfg.persona or "(未设置, 使用默认人设)"
    console.print(Panel(
        "[bold cyan]🧠 自定义系统人设[/bold cyan]\n"
        f"[dim]当前人设:[/dim]\n{current}",
        border_style="cyan",
    ))
    console.print(
        "[dim]输入新的人设内容(支持多行, 空行回车结束), 直接回车保持不变; "
        "回复 /prompt clear 可清空恢复默认。[/dim]"
    )
    lines = []
    try:
        while True:
            line = _read_input("> ")
            if line == "":
                break
            lines.append(line)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]已取消[/yellow]")
        return None
    if not lines:
        console.print("[dim]人设未修改[/dim]")
        return None
    persona = "\n".join(lines).strip()
    _config_set(cfg, "agent.persona", persona)
    console.print(f"[green]✔ 人设已保存到 {cfg._path}[/green]")
    return persona


def _config_setup(cfg, in_chat: bool = False) -> bool:
    """交互式配置向导: 引导填入 provider / base_url / model / api_key。

    返回 True=配置已保存, False=取消或失败。in_chat=True 时用于 chat 内的 /config。
    """
    console.print(Panel(
        "[bold cyan]⚙️  AgentX 配置向导[/bold cyan]\n"
        "[dim]按 Ctrl+C 随时取消, 直接回车使用方括号内的当前值[/dim]",
        border_style="cyan",
    ))

    try:
        provider = _read_input(
            f"模型服务 provider [dim](ollama / openai)[/dim] [{cfg.llm_provider}]: "
        ) or cfg.llm_provider
        provider = provider.strip().lower()
        if provider not in ("ollama", "openai"):
            console.print("[red]无效 provider, 仅支持 ollama / openai[/red]")
            return False

        if provider == "ollama":
            default_url = cfg.llm_base_url or "http://localhost:11434"
            base_url = _read_input(f"Ollama 地址 [{default_url}]: ") or default_url
            default_model = cfg.llm_model or "phi4-mini"
            model = _read_input(f"模型名 [{default_model}]: ") or default_model
            api_key = ""
        else:
            default_url = cfg.llm_base_url or "https://api.deepseek.com"
            base_url = _read_input(f"OpenAI 兼容接口地址 [{default_url}]: ") or default_url
            default_model = cfg.llm_model or "deepseek-v4-flash"
            model = _read_input(f"模型名 [{default_model}]: ") or default_model
            prompt = f"API Key [dim](直接回车保持不变)[/dim]: "
            console.print(prompt, end="")
            api_key = _read_input("").strip()
            if not api_key:
                api_key = cfg.llm_api_key or ""
            else:
                console.print(f"[dim]已接收 API Key: {mask_api_key(api_key)}[/dim]")
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]配置已取消[/yellow]")
        return False

    _config_set(cfg, "llm.provider", provider)
    _config_set(cfg, "llm.base_url", base_url)
    _config_set(cfg, "llm.model", model)
    if api_key:
        _config_set(cfg, "llm.api_key", api_key)
    else:
        _config_set(cfg, "llm.api_key", "")

    console.print(f"\n[green]✔ 配置已保存到 {cfg._path}[/green]")
    console.print(f"[bold]Provider:[/bold] {provider}")
    console.print(f"[bold]Model:[/bold] {model}")
    console.print(f"[bold]Base URL:[/bold] {base_url}")
    console.print(f"[bold]API Key:[/bold] {mask_api_key(api_key)}")
    if not in_chat:
        console.print("\n[dim]提示: 直接运行 agentx chat 即可开始对话[/dim]")
    return True


def _config_set(cfg, key, value):
    import tomli_w
    if isinstance(value, str):
        low = value.lower()
        if low in ("true", "false"):
            value = low == "true"
        else:
            try:
                value = int(value)
            except ValueError:
                pass
    parts = key.split(".")
    node = cfg._file
    for p in parts[:-1]:
        if isinstance(node, dict):
            if p not in node or not isinstance(node[p], dict):
                node[p] = {}
            node = node[p]
    if isinstance(node, dict):
        node[parts[-1]] = value
    cfg._path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg._path, "w") as f:
        f.write(tomli_w.dumps(cfg._file))


def _config_get(cfg, key):
    parts = key.split(".")
    node = cfg._file
    for p in parts:
        if isinstance(node, dict) and p in node:
            node = node[p]
        else:
            return None
    return node


def status_bar(model: str, session_id: str, tokens: int = 0):
    from datetime import datetime
    from rich.table import Table
    from rich.panel import Panel
    now = datetime.now().strftime("%H:%M:%S")
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(style="white")
    table.add_row("model", model)
    table.add_row("session", session_id[:8])
    if tokens:
        table.add_row("tokens", str(tokens))
    table.add_row("time", now)
    return Panel(table, border_style="dim", padding=(0, 1))


if __name__ == "__main__":
    app()
