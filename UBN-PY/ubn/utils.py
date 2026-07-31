from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box
import json

console = Console()

def print_error(msg: str) -> None:
    console.print(f"[bold red]❌ {msg}[/bold red]")

def print_success(msg: str) -> None:
    console.print(f"[bold green]✅ {msg}[/bold green]")

def print_warning(msg: str) -> None:
    console.print(f"[bold yellow]⚠️  {msg}[/bold yellow]")

def print_info(msg: str) -> None:
    console.print(f"[bold blue]ℹ️  {msg}[/bold blue]")

def print_json(data: dict) -> None:
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))

def table_from_dicts(headers: list[str], rows: list[list[str]], title: str = "") -> Table:
    table = Table(title=title, box=box.ROUNDED, show_header=True, header_style="bold cyan")
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*row)
    return table

def panel_text(content: str, title: str = "", style: str = "white") -> Panel:
    return Panel(content, title=title, border_style=style)