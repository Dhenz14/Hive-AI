"""Tooling — CLI frameworks, Rich TUI, and argument parsing."""

PAIRS = [
    (
        "python/click-cli",
        "Show Click CLI patterns: commands, groups, options, arguments, and progress bars.",
        '''Click CLI framework patterns:

```python
import click
import sys
import json
from pathlib import Path
from typing import Optional


# --- Command group with shared options ---

@click.group()
@click.version_option(version="1.0.0")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--config", "-c", type=click.Path(exists=True),
              help="Config file path")
@click.pass_context
def cli(ctx, verbose, config):
    """My awesome CLI tool."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    if config:
        with open(config) as f:
            ctx.obj["config"] = json.load(f)


# --- Subcommand with arguments and options ---

@cli.command()
@click.argument("source", type=click.Path(exists=True))
@click.argument("dest", type=click.Path())
@click.option("--format", "-f", "fmt",
              type=click.Choice(["json", "csv", "parquet"]),
              default="json", help="Output format")
@click.option("--filter", "-F", "filters", multiple=True,
              help="Filter expressions (can specify multiple)")
@click.option("--limit", "-n", type=int, default=None,
              help="Limit number of records")
@click.option("--dry-run", is_flag=True, help="Preview without writing")
@click.pass_context
def convert(ctx, source, dest, fmt, filters, limit, dry_run):
    """Convert data files between formats."""
    verbose = ctx.obj["verbose"]

    if verbose:
        click.echo(f"Converting {source} -> {dest} (format: {fmt})")
        for f in filters:
            click.echo(f"  Filter: {f}")

    records = load_data(source)

    for expr in filters:
        records = apply_filter(records, expr)

    if limit:
        records = records[:limit]

    if dry_run:
        click.echo(f"Would write {len(records)} records to {dest}")
        return

    with click.progressbar(records, label="Converting") as bar:
        for record in bar:
            process(record)

    click.secho(f"Wrote {len(records)} records to {dest}", fg="green")


# --- Interactive prompts ---

@cli.command()
@click.option("--name", prompt="Project name",
              help="Name of the project")
@click.option("--template",
              type=click.Choice(["web", "api", "cli", "library"]),
              prompt="Template type")
@click.option("--description", prompt="Description",
              default="", help="Project description")
@click.confirmation_option(prompt="Create project?")
def init(name, template, description):
    """Initialize a new project."""
    click.echo(f"Creating {template} project: {name}")

    with click.progressbar(length=5, label="Setting up") as bar:
        for step in setup_steps(name, template):
            step()
            bar.update(1)

    click.secho(f"Project '{name}' created!", fg="green", bold=True)


# --- File output ---

@cli.command()
@click.argument("query")
@click.option("--output", "-o", type=click.File("w"), default="-",
              help="Output file (default: stdout)")
@click.option("--format", "-f", "fmt",
              type=click.Choice(["table", "json", "csv"]),
              default="table")
def search(query, output, fmt):
    """Search and output results."""
    results = do_search(query)

    if fmt == "json":
        output.write(json.dumps(results, indent=2))
    elif fmt == "csv":
        import csv
        writer = csv.DictWriter(output, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    else:
        for r in results:
            click.echo(f"{r['name']:30s} {r['score']:.2f}", file=output)


# --- Error handling ---

@cli.command()
@click.argument("url")
def fetch(url):
    """Fetch a URL."""
    try:
        result = do_fetch(url)
        click.echo(result)
    except ConnectionError:
        click.secho("Error: Could not connect", fg="red", err=True)
        sys.exit(1)
    except TimeoutError:
        click.secho("Error: Request timed out", fg="red", err=True)
        sys.exit(1)


# --- Custom parameter types ---

class DateType(click.ParamType):
    name = "date"

    def convert(self, value, param, ctx):
        from datetime import datetime
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            self.fail(f"'{value}' is not a valid date (YYYY-MM-DD)", param, ctx)

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

Click patterns:
1. **`@click.group()`** — nested command hierarchy with shared context
2. **`multiple=True`** — accept repeated options (`-F filter1 -F filter2`)
3. **`click.progressbar`** — built-in progress bar for iteration
4. **`type=click.File("w")`** — automatic file handling with stdout default
5. **Custom `ParamType`** — extend Click with domain-specific types'''
    ),
    (
        "python/rich-tui",
        "Show Rich library patterns: tables, progress bars, live displays, and terminal UI.",
        '''Rich terminal UI patterns:

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import (
    Progress, SpinnerColumn, BarColumn,
    TextColumn, TimeRemainingColumn, MofNCompleteColumn,
)
from rich.syntax import Syntax
from rich.tree import Tree
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.logging import RichHandler
from rich import print as rprint
import logging
import time

console = Console()


# --- Rich tables ---

def show_users(users: list[dict]):
    table = Table(
        title="Users",
        show_header=True,
        header_style="bold magenta",
        show_lines=True,
    )
    table.add_column("ID", style="dim", width=8)
    table.add_column("Name", style="cyan")
    table.add_column("Email", style="green")
    table.add_column("Status", justify="center")
    table.add_column("Score", justify="right")

    for user in users:
        status = ("[green]Active[/]" if user["active"]
                  else "[red]Inactive[/]")
        table.add_row(
            user["id"], user["name"], user["email"],
            status, f"{user['score']:.1f}",
        )

    console.print(table)


# --- Progress bars ---

def process_files(files: list[str]):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing...", total=len(files))

        for file in files:
            progress.update(task, description=f"Processing {file}")
            process_file(file)
            progress.advance(task)


# Multi-task progress
def download_and_process(urls: list[str]):
    with Progress(console=console) as progress:
        download_task = progress.add_task("Downloading", total=len(urls))
        process_task = progress.add_task("Processing", total=len(urls))

        for url in urls:
            data = download(url)
            progress.advance(download_task)

            process(data)
            progress.advance(process_task)


# --- Live display (real-time updates) ---

def monitor_system():
    with Live(console=console, refresh_per_second=2) as live:
        while True:
            table = Table(title="System Monitor")
            table.add_column("Metric")
            table.add_column("Value")
            table.add_column("Status")

            cpu = get_cpu_usage()
            mem = get_memory_usage()
            disk = get_disk_usage()

            table.add_row("CPU", f"{cpu}%",
                         "[red]HIGH[/]" if cpu > 80 else "[green]OK[/]")
            table.add_row("Memory", f"{mem}%",
                         "[red]HIGH[/]" if mem > 85 else "[green]OK[/]")
            table.add_row("Disk", f"{disk}%",
                         "[yellow]WARN[/]" if disk > 70 else "[green]OK[/]")

            live.update(table)
            time.sleep(1)


# --- Panels and layout ---

def show_dashboard():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right", ratio=2),
    )

    layout["header"].update(
        Panel("[bold blue]Dashboard[/]", style="blue")
    )
    layout["left"].update(Panel("Navigation", title="Menu"))
    layout["right"].update(Panel("Main Content", title="Details"))
    layout["footer"].update(
        Panel("[dim]Press Ctrl+C to exit[/]")
    )

    console.print(layout)


# --- Tree display ---

def show_project_structure(path: str):
    tree = Tree(f"[bold]{path}[/]", guide_style="dim")
    src = tree.add("[bold cyan]src/[/]")
    src.add("[green]main.py[/]")
    src.add("[green]utils.py[/]")
    components = src.add("[bold cyan]components/[/]")
    components.add("[green]header.py[/]")
    components.add("[green]footer.py[/]")
    tree.add("[yellow]README.md[/]")
    tree.add("[yellow]pyproject.toml[/]")
    console.print(tree)


# --- Interactive prompts ---

def setup_wizard():
    name = Prompt.ask("Project name", default="my-project")
    template = Prompt.ask(
        "Template",
        choices=["web", "api", "cli"],
        default="web",
    )
    port = IntPrompt.ask("Port", default=8000)
    use_docker = Confirm.ask("Include Docker?", default=True)

    console.print(Panel(
        f"Name: [cyan]{name}[/]\\n"
        f"Template: [green]{template}[/]\\n"
        f"Port: [yellow]{port}[/]\\n"
        f"Docker: {'Yes' if use_docker else 'No'}",
        title="Configuration",
    ))


# --- Rich logging ---

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
log = logging.getLogger("app")
# log.info("Server started", extra={"port": 8000})
```

Rich patterns:
1. **`Table`** — formatted tables with styled columns and row data
2. **`Progress`** — multi-task progress bars with spinners and ETA
3. **`Live`** — real-time updating display (dashboards, monitors)
4. **`Layout`** — split terminal into panels (header/body/footer)
5. **`RichHandler`** — drop-in logging handler with syntax-highlighted tracebacks'''
    ),
    (
        "python/argparse-typer",
        "Show Typer CLI patterns: type-annotated commands, auto-completion, and testing.",
        '''Typer CLI patterns:

```python
import typer
from typing import Annotated, Optional
from pathlib import Path
from enum import Enum
import json
import sys

app = typer.Typer(
    name="myctl",
    help="My CLI tool",
    add_completion=True,
    no_args_is_help=True,
)


# --- Enum for choices ---

class OutputFormat(str, Enum):
    json = "json"
    table = "table"
    csv = "csv"


class LogLevel(str, Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


# --- Commands with type annotations ---

@app.command()
def process(
    source: Annotated[Path, typer.Argument(
        help="Source file to process",
        exists=True,
        file_okay=True,
        dir_okay=False,
    )],
    output: Annotated[Optional[Path], typer.Option(
        "--output", "-o",
        help="Output file (default: stdout)",
    )] = None,
    format: Annotated[OutputFormat, typer.Option(
        "--format", "-f",
        help="Output format",
    )] = OutputFormat.table,
    limit: Annotated[int, typer.Option(
        "--limit", "-n",
        min=1, max=10000,
        help="Max records to process",
    )] = 100,
    verbose: Annotated[bool, typer.Option(
        "--verbose", "-v",
        help="Enable verbose output",
    )] = False,
):
    """Process a data file and output results."""
    if verbose:
        typer.echo(f"Processing {source} (format: {format.value})")

    data = json.loads(source.read_text())[:limit]

    if format == OutputFormat.json:
        result = json.dumps(data, indent=2)
    elif format == OutputFormat.csv:
        result = to_csv(data)
    else:
        result = to_table(data)

    if output:
        output.write_text(result)
        typer.secho(f"Wrote to {output}", fg=typer.colors.GREEN)
    else:
        typer.echo(result)


# --- Subcommand groups ---

db_app = typer.Typer(help="Database operations")
app.add_typer(db_app, name="db")

@db_app.command("migrate")
def db_migrate(
    target: Annotated[Optional[str], typer.Argument()] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
):
    """Run database migrations."""
    if dry_run:
        typer.echo("Would run migrations (dry run)")
        return

    with typer.progressbar(get_pending_migrations(), label="Migrating") as bar:
        for migration in bar:
            run_migration(migration)

    typer.secho("Migrations complete!", fg=typer.colors.GREEN)


@db_app.command("seed")
def db_seed(
    count: Annotated[int, typer.Option("--count", "-n")] = 100,
):
    """Seed database with test data."""
    if not typer.confirm(f"Seed {count} records?"):
        raise typer.Abort()

    for i in typer.progressbar(range(count)):
        create_test_record(i)

    typer.echo(f"Seeded {count} records")


# --- Error handling with exit codes ---

@app.command()
def deploy(
    env: Annotated[str, typer.Argument(help="Target environment")],
    force: Annotated[bool, typer.Option("--force")] = False,
):
    """Deploy to environment."""
    if env == "production" and not force:
        typer.secho("Use --force for production deploys", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        run_deploy(env)
        typer.secho(f"Deployed to {env}", fg=typer.colors.GREEN)
    except DeployError as e:
        typer.secho(f"Deploy failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- Callback for global options ---

@app.callback()
def main(
    log_level: Annotated[LogLevel, typer.Option(
        "--log-level", envvar="LOG_LEVEL",
    )] = LogLevel.info,
):
    """My CLI tool with global options."""
    import logging
    logging.basicConfig(level=getattr(logging, log_level.value.upper()))


# --- Testing Typer apps ---

# from typer.testing import CliRunner
# runner = CliRunner()
#
# def test_process():
#     result = runner.invoke(app, ["process", "data.json", "-f", "json"])
#     assert result.exit_code == 0
#
# def test_deploy_requires_force():
#     result = runner.invoke(app, ["deploy", "production"])
#     assert result.exit_code == 1
#     assert "force" in result.output


if __name__ == "__main__":
    app()
```

Typer patterns:
1. **`Annotated` types** — type hints drive argument parsing and validation
2. **`typer.Typer()` groups** — nested subcommands via `add_typer()`
3. **`typer.progressbar`** — built-in progress bar for iterations
4. **`envvar="LOG_LEVEL"`** — option values from environment variables
5. **`CliRunner`** — test CLI commands with captured output and exit codes'''
    ),
]
"""
