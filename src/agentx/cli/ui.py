"""UI helpers — Rich rendering, pet mascot, panels, status bar."""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

PET_ART = {
    "idle": """[bold yellow]😺[/bold yellow]
   /\\_/\\
  ( o.o )
   > ^ <""",
    "thinking": """[bold cyan]🤔[/bold cyan]
   /\\_/\\
  ( ◕ ◕ )
   > ? <""",
    "working": """[bold orange3]😤[/bold orange3]
   /\\_/\\
  ( > < )
   / | \\""",
    "streaming": """[bold green]💬[/bold green]
   /\\_/\\
  ( ^.^ )
   ~ ~ ~""",
    "tool_call": """[bold magenta]🔧[/bold magenta]
   /\\_/\\
  ( @.@ ){ [] }""",
    "done": """[bold green]✅[/bold green]
   /\\_/\\
  ( ^.^ )
  / ___ \\""",
    "error": """[bold red]💥[/bold red]
   /\\_/\\
  ( x.x )
   X   X""",
    "waiting": """[bold blue]⏳[/bold blue]
   /\\_/\\
  ( -.- )
   z Z Z""",
}

class PetMascot:
    def __init__(self, pet_name: str = "小智"):
        self.pet_name = pet_name
        self.state = "idle"

    def set_state(self, state: str) -> None:
        self.state = state

    def render(self) -> Panel:
        art = PET_ART.get(self.state, PET_ART["idle"])
        return Panel(
            art,
            title=f"[bold cyan]{self.pet_name}[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )

def status_bar(model: str, session_id: str, tokens: int = 0) -> Panel:
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

def tool_call_panel(tool_name: str, arguments: dict, result: str, elapsed: float) -> Panel:
    args_str = ", ".join(f"{k}={v}" for k, v in arguments.items())
    content = f"[bold yellow]{tool_name}[/bold yellow]({args_str})\n[dim]{elapsed:.2f}s[/dim]\n\n[green]→ {result[:200]}[/green]"
    return Panel(content, title="Tool Call", border_style="yellow", padding=(0, 1))
