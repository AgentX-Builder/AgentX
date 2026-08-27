"""AgentX extras — /work file history, /memory cross-session recall, /gacha pet gacha."""

from __future__ import annotations

import json
import os
import random
import time
from datetime import date, datetime
from pathlib import Path

from rich import box
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

WORK_HISTORY_DIR = Path.home() / ".work_history"
MEMORY_DIR = Path.home() / ".agentx" / "memory"
PET_DATA_PATH = Path.home() / ".pet_data.json"

DAILY_PULL_LIMIT = 10
GOD_CHANCE = 0.001

RARITY_STYLE = {
    "普通": "grey50",
    "非凡": "green",
    "稀有": "blue",
    "史诗": "magenta",
    "传说": "yellow",
    "神级": "gold1",
}
RARITY_STARS = {
    "普通": "★",
    "非凡": "★★",
    "稀有": "★★★",
    "史诗": "★★★★",
    "传说": "★★★★★",
    "神级": "S+",
}

CATS = {
    "普通": {"chance": 60.0, "pets": ["橘猫", "黑猫", "白猫", "狸花猫"]},
    "非凡": {"chance": 25.0, "pets": ["英短", "美短", "暹罗", "布偶猫"]},
    "稀有": {"chance": 10.0, "pets": ["缅因猫", "波斯猫", "豹猫", "猞猁"]},
    "史诗": {"chance": 4.0, "pets": ["老虎", "狮子", "豹", "雪豹"]},
    "传说": {"chance": 1.0, "pets": ["原猫"]},
}

CAT_ICONS = {
    "橘猫": "🐱", "黑猫": "🐈‍⬛", "白猫": "🐱", "狸花猫": "🐱",
    "英短": "🐱", "美短": "🐱", "暹罗": "🐱", "布偶猫": "🐱",
    "缅因猫": "🐱", "波斯猫": "🐱", "豹猫": "🐆", "猞猁": "🐱",
    "老虎": "🐯", "狮子": "🦁", "豹": "🐆", "雪豹": "🐆",
    "原猫": "🐾",
}

CAT_ARTS = {
    "橘猫": """[bold orange3]     /\\    /\\
    /  \\__/  \\
   |   o  o   |
   |    '-'   |
   |  [bold orange1]( ⌄ )[/bold orange1]  |
    \\  ▓▓▓▓  /
     █▓█▓█▓█[/bold orange3]""",
    "黑猫": """[bold grey30]      /\\
     /  \\
    / ▔▔ \\__
   ( [bold yellow]◉◉[/bold yellow] )[bold grey30]/
    ( [bold yellow]⌄[/bold yellow] )[bold grey30]
     \\__/
     ███
      ██[/bold grey30]""",
    "白猫": """[bold bright_white]     /\\    /\\
    /  \\__/  \\
   ( [bold bright_magenta]♥♥[/bold bright_magenta] )[bold bright_white]
   (   ⌄   )
   (  ▔▔▔  )
    ░░░░░
     ░░[/bold bright_white]""",
    "狸花猫": """[bold grey58]     /\\
    /  \\
   | [bold grey35]M[/bold grey35] |
   | [bold grey35]◠◠[/bold grey35] |
   |  ⌄  |
    > ▓▓ <
    ▓█▓█▓[/bold grey58]""",
    "英短": """[bold steel_blue]      ______
     /      \\
    |  [bold bright_cyan]o  o[/bold bright_cyan]  |
    |   ⌄    |
    |  ⌄⌄    |
     \\  ▄▄  /
      ▄▄▄▄▄[/bold steel_blue]""",
    "美短": """[bold bright_cyan]     /\\    /\\
    /  \\__/  \\
   ( [bold grey50]◠ ◠[/bold grey50] )[bold bright_cyan]
   (   ‿   )
    \\  ▒▓  /
     ▒▓▒▓▒
      ▒▓[/bold bright_cyan]""",
    "暹罗": """[bold tan]      /\\
     /  \\
    / [bold grey15]▓▓[/bold grey15] \\
   ( [bold bright_blue]◉◉[/bold bright_blue] )
    \\  ▲  /
     \\ ▓░▓ /
      ▓░▓[/bold tan]""",
    "布偶猫": """[bold bright_white]     /\\   /\\
    (  \\_/  )
    ( [bold bright_blue]✧✧[/bold bright_blue] )
     >  ⌄  <
    ▄▄▄▄▄▄
    ██████[/bold bright_white]""",
    "缅因猫": """[bold dark_khaki]    ▄▄▄   ▄▄▄
   █  ██  █
   █  [bold orange1]◠◠[/bold orange1]  █
    █  ⌄  █
     █ ▓▓ █
     ██████
      ████[/bold dark_khaki]""",
    "波斯猫": """[bold bright_white]     ▔▔▔▔▔
    ( [bold white]▓▓[/bold white] )
    (  ‿  )
    ( ▔▔▔ )
     ▄▄▄▄▄
     █████
      ███[/bold bright_white]""",
    "豹猫": """[bold gold3]     /\\  /\\
    (  \\/  )
    ( [bold green4]◉◉[/bold green4] )
     ▣ ◉ ▣
      ███
       █
      ██[/bold gold3]""",
    "猞猁": """[bold grey50]     ▏▔▔▔▔▏
     ▏ /\\ ▏
     ▏([bold grey19]◉◉[/bold grey19])▏
     ▏ ⌄  ▏
      ███
      █  █
     ░   ░[/bold grey50]""",
    "老虎": """[bold orange3]     /\\_/\\
    ( [bold yellow]王 王[/bold yellow] )
    ( [bold bright_white]⌄⌄⌄[/bold bright_white] )
    (  ██  )
    █▒█▒█▒█
    █▒█▒█▒█[/bold orange3]""",
    "狮子": """[bold yellow]   █▄▄▄▄▄█
  █   /\\   █
  █  ( [bold orange1]♛♛[/bold orange1] )  █
  █   ⌄   █
   █  ██  █
    ██████[/bold yellow]""",
    "豹": """[bold gold3]     /\\_/\\
    ( [bold dark_goldenrod]◈◈[/bold dark_goldenrod] )
    (  ⌄  )
     ◉ ▣ ◉
      ███
       ~
       ~[/bold gold3]""",
    "雪豹": """[bold bright_white]     /\\    /\\
    /  \\__/  \\
   ( [bold grey50]◠ ◠[/bold grey50] )
    ▤  ▦  ▤
   ████████
    ▔▔▔▔▔▔
     ██████[/bold bright_white]""",
    "原猫": """[bold gold1]    ✨    ✨
    ✨ /\\ ✨
   ✨([bold dark_orange]◕‿◕[/bold dark_orange])✨
    ✨ ⌄ ✨
    ▒░▒░▒░▒
   ✨ ░▒░▒░ ✨
    ✨ ▀▀▀ ✨[/bold gold1]""",
}

ACTION_TAG = {
    "创建": "🆕 创建",
    "写入": "✏️ 写入",
    "读取": "📖 读取",
    "命令": "⚡ 命令",
}


# ── /work 会话文件操作记录 ─────────────────────────────────────────


class WorkHistory:
    def __init__(self, session_id: str, work_dir: Path | None = None):
        self.session_id = session_id
        self.work_dir = Path(work_dir) if work_dir else WORK_HISTORY_DIR
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._ops = self._load()

    def _path(self) -> Path:
        return self.work_dir / f"{self.session_id}.json"

    def _load(self) -> list:
        p = self._path()
        if not p.exists():
            return []
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("operations", [])
        except Exception:
            return []

    @staticmethod
    def _abs(path: str) -> str:
        return os.path.abspath(os.path.expanduser(path))

    def _rel(self, path: str) -> str:
        try:
            return os.path.relpath(self._abs(path), os.getcwd())
        except Exception:
            return path

    def record(self, tool: str, path: str, action: str, content: str | None = None) -> None:
        op = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tool": tool,
            "action": action,
            "path": self._rel(path),
            "abs_path": self._abs(path),
        }
        if content is not None:
            op["content"] = content
        self._ops.append(op)
        self._flush()

    def _flush(self) -> None:
        data = {
            "session_id": self.session_id,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operations": self._ops,
        }
        self._path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self) -> list:
        return list(self._ops)


# ── /memory 跨会话记忆 ─────────────────────────────────────────────


class MemoryStore:
    def __init__(self, memory_dir: Path | None = None):
        self.memory_dir = Path(memory_dir) if memory_dir else MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def save(self, session) -> None:
        topics = []
        summaries = []
        for msg in getattr(session, "_messages", []) or []:
            role = msg.get("role")
            content = msg.get("content")
            if not content:
                continue
            if role == "user":
                topics.append(str(content)[:500])
            elif role == "assistant" and not msg.get("tool_calls"):
                summaries.append(str(content)[:2000])
        entry = {
            "session_id": session.id,
            "turn_count": getattr(session, "turn_count", 0),
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "topics": topics,
            "summaries": summaries[-10:],
        }
        self.memory_dir / f"{session.id}.json"
        (self.memory_dir / f"{session.id}.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

    def _iter_entries(self) -> list:
        entries = []
        for f in sorted(self.memory_dir.glob("*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                entries.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return entries

    def list_all(self) -> list:
        return self._iter_entries()[:10]

    def search(self, keyword: str) -> list:
        kw = keyword.lower()
        results = []
        for e in self._iter_entries():
            if kw in json.dumps(e, ensure_ascii=False).lower():
                results.append(e)
        return results


# ── /gacha 抽卡宠物系统 ────────────────────────────────────────────


class GachaSystem:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else PET_DATA_PATH
        self._data = self._load()

    def _load(self) -> dict:
        data = {
            "quota": {"date": date.today().isoformat(), "used": 0, "daily_limit": DAILY_PULL_LIMIT},
            "collection": {},
            "active": None,
            "stats": {"total": 0, "god": 0},
        }
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update(loaded)
                    if not isinstance(data.get("quota"), dict):
                        data["quota"] = {}
            except Exception:
                pass
        if data.get("quota", {}).get("date") != date.today().isoformat():
            data["quota"] = {"date": date.today().isoformat(), "used": 0,
                             "daily_limit": DAILY_PULL_LIMIT}
        data.setdefault("collection", {})
        data.setdefault("active", None)
        data.setdefault("stats", {"total": 0, "god": 0})
        return data

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def remaining(self) -> int:
        q = self._data.get("quota", {})
        return max(0, int(q.get("daily_limit", DAILY_PULL_LIMIT)) - int(q.get("used", 0)))

    def _roll_rarity(self) -> str:
        r = random.random() * 100
        acc = 0.0
        for rarity, spec in CATS.items():
            acc += spec["chance"]
            if r < acc:
                return rarity
        return "普通"

    def _roll_pet(self) -> dict:
        rarity = self._roll_rarity()
        name = random.choice(CATS[rarity]["pets"])
        god = False
        if name == "原猫" and random.random() < GOD_CHANCE:
            god = True
        return {"name": name, "rarity": rarity, "icon": CAT_ICONS.get(name, "🐱"),
                "art": CAT_ARTS.get(name, ""), "god": god}

    def pull(self):
        if self.remaining() <= 0:
            return None, f"今日免费抽卡次数已用完(每天{DAILY_PULL_LIMIT}次, 0点重置)"
        self._data["quota"]["used"] += 1
        pet = self._roll_pet()
        self._data["stats"]["total"] += 1
        if pet["god"]:
            self._data["stats"]["god"] += 1
            pet["rarity"] = "神级"
        col = self._data["collection"].setdefault(
            pet["name"], {"count": 0, "first": None, "rarity": pet["rarity"], "god": False})
        col["count"] += 1
        if col.get("first") is None:
            col["first"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if pet["god"]:
            col["rarity"] = "神级"
            col["god"] = True
        self._data["active"] = pet["name"]
        self._flush()
        return pet, None

    def collection(self) -> dict:
        return self._data.get("collection", {})

    def active_pet(self) -> dict | None:
        name = self._data.get("active")
        if not name:
            return None
        info = self._data["collection"].get(name, {})
        return {"name": name, "rarity": info.get("rarity", "普通"), "god": bool(info.get("god"))}

    def active_pet_art(self) -> str:
        """当前活跃皮肤的 ASCII 艺术画, 无则返回空串。"""
        active = self.active_pet()
        if not active:
            return ""
        return CAT_ARTS.get(active["name"], "")


# ── 渲染 ────────────────────────────────────────────────────────────


def gacha_animation(console, rounds: int = 4, delay: float = 0.12) -> None:
    frames = [
        "[bold]🎰 抽取中...[/bold] 🐱",
        "[bold]🎰 抽取中...[/bold] 🐈",
        "[bold]🎰 抽取中...[/bold] 🐈⬛",
        "[bold]🎰 抽取中...[/bold] 🐾",
        "[bold]🎰 抽取中...[/bold] ✨",
    ]
    try:
        with Live(console=console, refresh_per_second=12, transient=True) as live:
            for _ in range(rounds):
                for f in frames:
                    live.update(Text.from_markup(f))
                    time.sleep(delay)
    except Exception:
        console.print("[dim]🎰 抽取中...[/dim]")


def render_gacha(console, pet: dict, remaining: int) -> None:
    name = pet["name"]
    rarity = pet["rarity"]
    god = bool(pet.get("god"))
    style = RARITY_STYLE.get(rarity, "cyan")
    stars = RARITY_STARS.get(rarity, "")
    icon = pet.get("icon", "🐱")
    art = pet.get("art", "")
    header = f"[bold {style}]{icon} {name} · {rarity} {stars}[/bold {style}]"
    parts = [header]
    if art:
        parts.append("\n" + art)
    lines = "\n".join(parts)
    if god:
        lines += "\n[bold gold1]✨ 神级 S+ —— 所有猫科动物的共同祖先 ✨[/bold gold1]"
    console.print(Panel(lines, title="[bold]🎉 抽卡结果[/bold]",
                        border_style=style, expand=False))
    console.print(f"[dim]今日剩余抽卡次数: {remaining}/{DAILY_PULL_LIMIT}[/dim]")


def render_collection(console, gacha: GachaSystem) -> None:
    col = gacha.collection()
    if not col:
        console.print("[dim]图鉴还是空的, 输入 /gacha 抽第一只猫猫吧[/dim]")
        return
    order = {"神级": 99, "传说": 5, "史诗": 4, "稀有": 3, "非凡": 2, "普通": 1}
    table = Table(title="📚 宠物图鉴", box=box.ROUNDED)
    table.add_column("宠物", style="bold")
    table.add_column("稀有度")
    table.add_column("数量", justify="right")
    table.add_column("首次获得", style="dim")
    for name, info in sorted(col.items(),
                             key=lambda x: (order.get(x[1].get("rarity", "普通"), 0), x[0])):
        rar = info.get("rarity", "普通")
        style = RARITY_STYLE.get(rar, "cyan")
        god_mark = " ✨" if info.get("god") else ""
        table.add_row(f"{name}{god_mark}", f"[{style}]{rar}[/{style}]",
                      str(info.get("count", 0)), str(info.get("first", "—")))
    console.print(table)
    active = gacha.active_pet()
    if active:
        a_style = RARITY_STYLE.get(active["rarity"], "cyan")
        glow = " ✨" if active["god"] else ""
        console.print(f"[dim]当前活跃: [bold {a_style}]{active['name']}[/bold {a_style}]"
                      f" ({active['rarity']}){glow}[/dim]")


def render_work_list(console, ops: list, ask) -> None:
    if not ops:
        console.print("[dim]当前会话还没有任何文件操作记录[/dim]")
        return
    console.print("[bold]📁 当前会话文件操作记录[/bold]")
    for i, op in enumerate(ops, start=1):
        action = op.get("action", "")
        tag = ACTION_TAG.get(action, action)
        console.print(f"[cyan]{i}.[/cyan] {op.get('ts', '')}  {tag}  [bold]{op.get('path', '')}[/bold]")
    console.print("[dim]输入编号或文件名查看文件完整内容, 回车取消[/dim]")
    try:
        choice = ask("选择")
    except (KeyboardInterrupt, EOFError):
        return
    if not choice:
        return
    target = None
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(ops):
            target = ops[idx - 1]
        else:
            console.print("[red]编号超出范围[/red]")
            return
    else:
        for op in ops:
            if choice in op.get("path", ""):
                target = op
                break
        if target is None:
            console.print(f"[red]未找到: {choice}[/red]")
            return
    show_work_file(console, target)


def show_work_file(console, op: dict) -> None:
    content = op.get("content")
    if content is None:
        try:
            content = Path(op.get("abs_path", "")).read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = "(无法读取文件内容)"
    action = op.get("action", "")
    console.print(Panel(Text(content), title=f"[bold]{op.get('path', '')}[/bold]  ({action})",
                        border_style="cyan"))


def render_memory(console, memory: MemoryStore, keyword: str, ask) -> str | None:
    entries = memory.search(keyword) if keyword else memory.list_all()
    if not entries:
        if keyword:
            console.print(f"[red]没有找到包含 '{keyword}' 的会话记忆[/red]")
        else:
            console.print("[dim]还没有任何记忆[/dim]")
        return None
    if keyword:
        console.print(f"[bold]🧠 搜索 '{keyword}' 结果 ({len(entries)}):[/bold]")
    else:
        console.print(f"[bold]🧠 最近会话记忆 ({len(entries)}):[/bold]")
    for i, e in enumerate(entries, start=1):
        topics = e.get("topics") or []
        topic = topics[0][:60] if topics else "(无对话)"
        console.print(f"[cyan]{i}.[/cyan] {e['session_id']}  {e.get('saved_at', '')}"
                      f"  [dim]{topic}[/dim]")
    console.print("[dim]输入序号进入对应会话, 回车取消[/dim]")
    try:
        choice = ask("选择")
    except (KeyboardInterrupt, EOFError):
        return None
    if choice and choice.isdigit() and 1 <= int(choice) <= len(entries):
        return entries[int(choice) - 1]["session_id"]
    return None
