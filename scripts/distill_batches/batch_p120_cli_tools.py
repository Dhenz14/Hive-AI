"""CLI tools — Click, Rich, and interactive terminal applications."""

PAIRS = [
    (
        "python/click-cli",
        "Show Python Click CLI patterns: commands, groups, options, and interactive prompts.",
        '''Python Click CLI patterns:

```python
import click
import sys
from pathlib import Path


# --- Basic command with options and arguments ---

@click.command()
@click.argument("name")
@click.option("--greeting", "-g", default="Hello", help="Greeting to use")
@click.option("--count", "-c", default=1, type=int, help="Number of times to greet")
@click.option("--uppercase", "-u", is_flag=True, help="Uppercase the output")
def greet(name: str, greeting: str, count: int, uppercase: bool):
    """Greet someone NAME times."""
    message = f"{greeting}, {name}!"
    if uppercase:
        message = message.upper()
    for _ in range(count):
        click.echo(message)


# --- Command group (subcommands) ---

@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--config", type=click.Path(exists=True), help="Config file path")
@click.pass_context
def cli(ctx, verbose: bool, config: str | None):
    """My Application CLI."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config"] = config


@cli.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--pattern", "-p", default="*", help="Glob pattern")
@click.option("--recursive", "-r", is_flag=True)
@click.pass_context
def search(ctx, directory: str, pattern: str, recursive: bool):
    """Search for files matching pattern."""
    path = Path(directory)
    glob_fn = path.rglob if recursive else path.glob

    count = 0
    for match in glob_fn(pattern):
        click.echo(str(match))
        count += 1

    if ctx.obj["verbose"]:
        click.echo(f"\\nFound {count} files")


@cli.command()
@click.argument("source", type=click.Path(exists=True))
@click.argument("dest", type=click.Path())
@click.option("--force", "-f", is_flag=True, help="Overwrite existing")
@click.confirmation_option(prompt="Are you sure you want to deploy?")
def deploy(source: str, dest: str, force: bool):
    """Deploy SOURCE to DEST."""
    if Path(dest).exists() and not force:
        click.echo(click.style("Error: destination exists. Use --force.", fg="red"), err=True)
        sys.exit(1)

    with click.progressbar(range(100), label="Deploying") as bar:
        for _ in bar:
            import time
            time.sleep(0.02)

    click.echo(click.style("Deployed successfully!", fg="green", bold=True))


# --- Interactive prompts ---

@cli.command()
def init():
    """Initialize a new project interactively."""
    name = click.prompt("Project name", default="my-project")
    language = click.prompt(
        "Language",
        type=click.Choice(["python", "typescript", "rust", "go"]),
        default="python",
    )
    description = click.prompt("Description", default="")
    use_docker = click.confirm("Include Docker support?", default=True)
    port = click.prompt("Server port", default=8000, type=int)

    click.echo(f"\\nCreating {name} ({language})...")
    click.echo(f"  Description: {description}")
    click.echo(f"  Docker: {'yes' if use_docker else 'no'}")
    click.echo(f"  Port: {port}")


# --- File input/output ---

@cli.command()
@click.argument("input", type=click.File("r"), default="-")  # stdin by default
@click.argument("output", type=click.File("w"), default="-")  # stdout by default
@click.option("--format", "fmt", type=click.Choice(["json", "csv", "table"]))
def convert(input, output, fmt: str):
    """Convert data between formats. Reads stdin by default."""
    import json
    data = json.load(input)
    if fmt == "json":
        json.dump(data, output, indent=2)
    # ... other formats


# --- Custom parameter types ---

class DateType(click.ParamType):
    name = "date"

    def convert(self, value, param, ctx):
        from datetime import date
        try:
            return date.fromisoformat(value)
        except ValueError:
            self.fail(f"'{value}' is not a valid date (use YYYY-MM-DD)", param, ctx)

DATE = DateType()

@cli.command()
@click.option("--since", type=DATE, help="Start date (YYYY-MM-DD)")
@click.option("--until", type=DATE, help="End date (YYYY-MM-DD)")
def report(since, until):
    """Generate report for date range."""
    click.echo(f"Report: {since} to {until}")


if __name__ == "__main__":
    cli()
```

Click CLI patterns:
1. **`@click.group()`** — subcommands like `mycli search`, `mycli deploy`
2. **`@click.pass_context`** — share state (verbose, config) across subcommands
3. **`click.progressbar()`** — built-in progress bar for long operations
4. **`type=click.File("r")`** — auto-handle file open/close, `-` for stdin/stdout
5. **`click.prompt()` + `click.confirm()`** — interactive input with defaults and choices'''
    ),
    (
        "python/rich-tui",
        "Show Python Rich patterns: formatted output, tables, progress bars, and live displays.",
        '''Python Rich terminal UI patterns:

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.live import Live
from rich.layout import Layout
from rich.tree import Tree
from rich.syntax import Syntax
from rich.prompt import Prompt, Confirm, IntPrompt
from rich import print as rprint
import time

console = Console()


# --- Formatted output ---

console.print("[bold green]Success![/] Operation completed.")
console.print("[red]Error:[/red] File not found", style="bold")
console.print("Processing...", style="italic dim")

# Print with emoji
console.print(":rocket: Deploying application...")
console.print(":white_check_mark: Tests passed")

# Panels
console.print(Panel(
    "Application started on port 8000",
    title="[bold]Status[/bold]",
    border_style="green",
))

# Rule (horizontal separator)
console.rule("[bold]Section Title[/bold]")


# --- Tables ---

def show_users(users: list[dict]):
    table = Table(title="Users", show_lines=True)

    table.add_column("ID", style="dim", width=6)
    table.add_column("Name", style="bold")
    table.add_column("Email", style="cyan")
    table.add_column("Role", justify="center")
    table.add_column("Status", justify="center")

    for user in users:
        status = "[green]Active[/]" if user["active"] else "[red]Inactive[/]"
        table.add_row(
            str(user["id"]),
            user["name"],
            user["email"],
            user["role"],
            status,
        )

    console.print(table)


# --- Progress bars ---

def process_files(files: list[str]):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing files...", total=len(files))

        for file in files:
            progress.update(task, description=f"Processing {file}...")
            time.sleep(0.1)  # Simulate work
            progress.update(task, advance=1)


# Multiple concurrent progress bars
def parallel_downloads():
    with Progress() as progress:
        download1 = progress.add_task("[cyan]Downloading model...", total=1000)
        download2 = progress.add_task("[green]Downloading data...", total=500)
        compile_task = progress.add_task("[yellow]Compiling...", total=200)

        while not progress.finished:
            progress.update(download1, advance=3)
            progress.update(download2, advance=2)
            progress.update(compile_task, advance=1)
            time.sleep(0.01)


# --- Live display (auto-updating) ---

def live_dashboard():
    table = Table(title="Live Metrics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    with Live(table, console=console, refresh_per_second=4) as live:
        for i in range(100):
            table = Table(title="Live Metrics")
            table.add_column("Metric")
            table.add_column("Value", justify="right")

            table.add_row("Requests/s", f"[green]{100 + i * 5}[/]")
            table.add_row("Latency p95", f"[yellow]{50 + i}ms[/]")
            table.add_row("Errors", f"[red]{i % 3}[/]")
            table.add_row("Active Users", str(200 + i * 2))

            live.update(table)
            time.sleep(0.1)


# --- Tree (directory/hierarchy display) ---

def show_project_structure():
    tree = Tree("[bold]my-project/[/bold]")

    src = tree.add("[bold blue]src/[/bold blue]")
    src.add("[green]main.py[/green]")
    src.add("[green]config.py[/green]")

    api = src.add("[bold blue]api/[/bold blue]")
    api.add("[green]routes.py[/green]")
    api.add("[green]models.py[/green]")

    tests = tree.add("[bold blue]tests/[/bold blue]")
    tests.add("[green]test_main.py[/green]")

    tree.add("[dim]pyproject.toml[/dim]")
    tree.add("[dim]README.md[/dim]")

    console.print(tree)


# --- Syntax highlighting ---

code = '''
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
'''

syntax = Syntax(code, "python", theme="monokai", line_numbers=True)
console.print(syntax)


# --- Interactive prompts ---

name = Prompt.ask("Enter your name", default="World")
age = IntPrompt.ask("Enter your age")
proceed = Confirm.ask("Do you want to continue?")
color = Prompt.ask("Pick a color", choices=["red", "green", "blue"])


# --- Exception handling ---

try:
    1 / 0
except Exception:
    console.print_exception(show_locals=True)
```

Rich patterns:
1. **Markup syntax** — `[bold green]text[/]` for inline styling
2. **`Table`** — formatted tables with column alignment and colors
3. **`Progress`** — multi-bar progress with spinner, percentage, and ETA
4. **`Live`** — auto-refreshing display for dashboards and monitoring
5. **`print_exception(show_locals=True)`** — beautiful tracebacks with local variables'''
    ),
]
"""
