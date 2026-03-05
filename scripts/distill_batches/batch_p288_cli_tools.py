"""CLI tools — argument parsing (Click/Typer), progress bars, interactive prompts, config files, plugin systems."""

PAIRS = [
    (
        "cli-tools/typer-advanced-application",
        "Build a production-quality CLI application using Typer with subcommands, auto-completion, rich output, configuration management, and error handling.",
        '''Production CLI application with Typer, Rich, and config management:

```python
"""Production CLI tool using Typer + Rich — database migration manager."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.tree import Tree

console = Console()
err_console = Console(stderr=True)

# ============================================================
# 1. App structure with subcommand groups
# ============================================================

app = typer.Typer(
    name="dbmigrate",
    help="Database migration manager — apply, rollback, and inspect migrations.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)

# Subcommand groups
migrate_app = typer.Typer(help="Migration commands", no_args_is_help=True)
config_app = typer.Typer(help="Configuration management", no_args_is_help=True)
app.add_typer(migrate_app, name="migrate")
app.add_typer(config_app, name="config")


# ============================================================
# 2. Shared options and configuration
# ============================================================

class Environment(StrEnum):
    DEV = "development"
    STAGING = "staging"
    PROD = "production"


class Config:
    """Layered configuration: defaults -> config file -> env vars -> CLI args."""

    DEFAULT_CONFIG_PATH = Path.home() / ".config" / "dbmigrate" / "config.json"

    def __init__(self) -> None:
        self.database_url: str = ""
        self.migrations_dir: Path = Path("./migrations")
        self.environment: Environment = Environment.DEV
        self.dry_run: bool = False
        self.verbose: bool = False
        self.timeout: int = 30

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Config":
        """Load config with layered precedence."""
        cfg = cls()

        # Layer 1: Config file
        path = config_path or cls.DEFAULT_CONFIG_PATH
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            cfg.database_url = data.get("database_url", cfg.database_url)
            cfg.migrations_dir = Path(data.get("migrations_dir", str(cfg.migrations_dir)))
            cfg.environment = Environment(data.get("environment", cfg.environment.value))
            cfg.timeout = data.get("timeout", cfg.timeout)

        # Layer 2: Environment variables (override config file)
        if url := os.environ.get("DBMIGRATE_DATABASE_URL"):
            cfg.database_url = url
        if env := os.environ.get("DBMIGRATE_ENVIRONMENT"):
            cfg.environment = Environment(env)

        return cfg

    def save(self, path: Path | None = None) -> None:
        target = path or self.DEFAULT_CONFIG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w") as f:
            json.dump({
                "database_url": self.database_url,
                "migrations_dir": str(self.migrations_dir),
                "environment": self.environment.value,
                "timeout": self.timeout,
            }, f, indent=2)


# Global state via Typer context
class State:
    config: Config = Config()

state = State()


@app.callback()
def main(
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to config file", envvar="DBMIGRATE_CONFIG"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without executing"),
    ] = False,
    database_url: Annotated[
        Optional[str],
        typer.Option("--database-url", "-d", help="Database connection URL", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """[bold blue]dbmigrate[/] — Database migration manager.

    Manage database schema migrations with safety checks and rollback support.
    """
    state.config = Config.load(config_file)
    state.config.verbose = verbose
    state.config.dry_run = dry_run
    if database_url:
        state.config.database_url = database_url


# ============================================================
# 3. Migration commands with rich output
# ============================================================

@migrate_app.command("up")
def migrate_up(
    target: Annotated[
        Optional[str],
        typer.Argument(help="Target migration version (default: latest)"),
    ] = None,
    steps: Annotated[
        int,
        typer.Option("--steps", "-s", help="Number of migrations to apply"),
    ] = 0,
    environment: Annotated[
        Environment,
        typer.Option("--env", "-e", help="Target environment"),
    ] = Environment.DEV,
) -> None:
    """Apply pending migrations [bold green]upward[/]."""
    cfg = state.config

    if not cfg.database_url:
        err_console.print("[red]Error:[/] No database URL configured")
        err_console.print("Set via --database-url, DBMIGRATE_DATABASE_URL, or config file")
        raise typer.Exit(code=1)

    # Discover migrations
    migrations = _discover_migrations(cfg.migrations_dir)
    if not migrations:
        console.print("[yellow]No migrations found[/]")
        raise typer.Exit()

    pending = [m for m in migrations if not m.get("applied")]
    if steps > 0:
        pending = pending[:steps]
    if target:
        pending = [m for m in pending if m["version"] <= target]

    if not pending:
        console.print("[green]All migrations are up to date![/]")
        raise typer.Exit()

    # Show plan
    table = Table(title="Migration Plan", show_header=True, header_style="bold cyan")
    table.add_column("Version", style="dim")
    table.add_column("Name")
    table.add_column("Status")
    for m in pending:
        table.add_row(m["version"], m["name"], "[yellow]pending[/]")
    console.print(table)

    if cfg.dry_run:
        console.print("[yellow]Dry run — no changes applied[/]")
        raise typer.Exit()

    # Confirm for production
    if environment == Environment.PROD:
        confirm = typer.confirm(
            f"Apply {len(pending)} migration(s) to PRODUCTION?",
            abort=True,
        )

    # Apply with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Applying migrations...", total=len(pending))

        for migration in pending:
            progress.update(task, description=f"Applying {migration['version']}...")
            time.sleep(0.5)  # Simulate migration execution
            progress.advance(task)

    console.print(Panel(
        f"[green]Successfully applied {len(pending)} migration(s)[/]",
        title="Complete",
        border_style="green",
    ))


@migrate_app.command("down")
def migrate_down(
    steps: Annotated[
        int,
        typer.Option("--steps", "-s", help="Number of migrations to roll back"),
    ] = 1,
) -> None:
    """Roll back migrations [bold red]downward[/]."""
    cfg = state.config

    if cfg.dry_run:
        console.print(f"[yellow]Would roll back {steps} migration(s)[/]")
        raise typer.Exit()

    if steps > 1 or cfg.environment == Environment.PROD:
        typer.confirm(
            f"Roll back {steps} migration(s) in {cfg.environment.value}?",
            abort=True,
        )

    with console.status("[bold yellow]Rolling back...") as status:
        for i in range(steps):
            status.update(f"Rolling back step {i + 1}/{steps}...")
            time.sleep(0.3)

    console.print(f"[green]Rolled back {steps} migration(s)[/]")


@migrate_app.command("status")
def migrate_status() -> None:
    """Show current migration status."""
    cfg = state.config
    migrations = _discover_migrations(cfg.migrations_dir)

    tree = Tree("[bold]Migration Status[/]")
    applied_branch = tree.add("[green]Applied[/]")
    pending_branch = tree.add("[yellow]Pending[/]")

    for m in migrations:
        if m.get("applied"):
            applied_branch.add(f"[dim]{m['version']}[/] {m['name']}")
        else:
            pending_branch.add(f"[bold]{m['version']}[/] {m['name']}")

    console.print(tree)


@migrate_app.command("create")
def migrate_create(
    name: Annotated[str, typer.Argument(help="Migration name (e.g., 'add_users_table')")],
    sql: Annotated[
        bool,
        typer.Option("--sql", help="Generate SQL migration (vs Python)"),
    ] = False,
) -> None:
    """Create a new migration file."""
    cfg = state.config
    cfg.migrations_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    version = f"V{timestamp}"
    ext = "sql" if sql else "py"
    filename = f"{version}__{name}.{ext}"
    filepath = cfg.migrations_dir / filename

    if sql:
        content = f"-- Migration: {name}\\n-- Version: {version}\\n\\n-- UP\\n\\n-- DOWN\\n"
    else:
        content = f'''"""Migration: {name}"""

def up(connection):
    """Apply migration."""
    pass

def down(connection):
    """Roll back migration."""
    pass
'''

    filepath.write_text(content)
    console.print(f"[green]Created:[/] {filepath}")


# ============================================================
# 4. Config management commands
# ============================================================

@config_app.command("init")
def config_init() -> None:
    """Initialize configuration interactively."""
    rprint("[bold]Database Migration Manager Setup[/]\\n")

    db_url = typer.prompt("Database URL", default="postgresql://localhost/mydb")
    migrations_dir = typer.prompt("Migrations directory", default="./migrations")
    environment = typer.prompt(
        "Default environment",
        default="development",
        type=typer.Choice(["development", "staging", "production"]),
    )

    cfg = Config()
    cfg.database_url = db_url
    cfg.migrations_dir = Path(migrations_dir)
    cfg.environment = Environment(environment)
    cfg.save()

    console.print(f"[green]Config saved to {Config.DEFAULT_CONFIG_PATH}[/]")


@config_app.command("show")
def config_show() -> None:
    """Display current configuration."""
    cfg = state.config
    table = Table(title="Current Configuration", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    table.add_row("database_url", cfg.database_url or "[red]not set[/]", "config/env")
    table.add_row("migrations_dir", str(cfg.migrations_dir), "config")
    table.add_row("environment", cfg.environment.value, "config/env")
    table.add_row("timeout", str(cfg.timeout), "config")
    table.add_row("verbose", str(cfg.verbose), "CLI flag")
    table.add_row("dry_run", str(cfg.dry_run), "CLI flag")

    console.print(table)


# ============================================================
# 5. Helpers
# ============================================================

def _discover_migrations(migrations_dir: Path) -> list[dict]:
    """Discover migration files and their status."""
    if not migrations_dir.exists():
        return []

    migrations = []
    for f in sorted(migrations_dir.glob("V*__*")):
        version = f.stem.split("__")[0]
        name = f.stem.split("__")[1] if "__" in f.stem else f.stem
        migrations.append({
            "version": version,
            "name": name.replace("_", " "),
            "path": f,
            "applied": False,  # Would check DB in real implementation
        })
    return migrations


# ============================================================
# 6. Shell completion
# ============================================================

def complete_environment(incomplete: str) -> list[str]:
    """Auto-complete environment names."""
    return [e.value for e in Environment if e.value.startswith(incomplete)]


def complete_migration_version(incomplete: str) -> list[str]:
    """Auto-complete migration versions from discovered files."""
    migrations = _discover_migrations(state.config.migrations_dir)
    return [m["version"] for m in migrations if m["version"].startswith(incomplete)]


# Entry point
if __name__ == "__main__":
    app()
```

**CLI architecture patterns:**

| Pattern | Implementation | Benefit |
|---------|---------------|---------|
| Subcommand groups | `app.add_typer(sub, name="x")` | Organized command hierarchy |
| Layered config | File -> env vars -> CLI args | Flexible configuration |
| Rich output | Tables, trees, progress bars | Professional UX |
| Dry-run mode | `--dry-run` flag checks throughout | Safe testing |
| Interactive confirmation | `typer.confirm()` for destructive ops | Production safety |
| Shell completion | Callback functions | Tab completion |

**Best practices:**
- Use `Annotated` type hints for CLI argument metadata (Typer 0.9+)
- Always provide `--help` context with `rich_markup_mode="rich"`
- Implement `--dry-run` for any command that modifies state
- Require confirmation for production/destructive operations
- Layer config: defaults < config file < env vars < CLI args'''
    ),
    (
        "cli-tools/progress-bars-and-interactive-prompts",
        "Build advanced progress bar patterns and interactive prompts for CLI tools using Rich, including nested progress, file transfers, multi-task tracking, and interactive selection menus.",
        '''Advanced progress bars and interactive CLI patterns with Rich:

```python
"""Rich progress bars, interactive prompts, and live displays."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.columns import Columns
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

console = Console()


# ============================================================
# 1. Custom progress bar with multiple task types
# ============================================================

def create_download_progress() -> Progress:
    """Progress bar styled for file downloads."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
        BarColumn(bar_width=40),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console,
    )


def create_processing_progress() -> Progress:
    """Progress bar styled for data processing."""
    return Progress(
        SpinnerColumn("dots"),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30, complete_style="green", finished_style="bold green"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


async def download_files(urls: list[str]) -> None:
    """Simulate downloading multiple files with per-file progress."""
    progress = create_download_progress()

    with progress:
        tasks = {}
        for url in urls:
            filename = url.split("/")[-1]
            file_size = random.randint(10_000, 10_000_000)
            task_id = progress.add_task(
                "downloading",
                filename=filename,
                total=file_size,
            )
            tasks[task_id] = file_size

        while not progress.finished:
            for task_id, total_size in tasks.items():
                if not progress.tasks[task_id].finished:
                    chunk = random.randint(1000, 50000)
                    progress.update(task_id, advance=chunk)
            await asyncio.sleep(0.05)


# ============================================================
# 2. Nested progress — overall + per-item
# ============================================================

def process_batches(batches: list[list[dict]]) -> None:
    """Two-level progress: overall batches + items within each batch."""
    overall_progress = Progress(
        TextColumn("[bold blue]Overall"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )
    batch_progress = Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=25),
        TaskProgressColumn(),
    )

    # Combine into a Group for simultaneous display
    progress_group = Group(
        Panel(overall_progress, title="Batches", border_style="blue"),
        Panel(batch_progress, title="Current Batch", border_style="cyan"),
    )

    with Live(progress_group, console=console, refresh_per_second=10):
        overall_task = overall_progress.add_task("batches", total=len(batches))

        for batch_idx, batch in enumerate(batches):
            batch_task = batch_progress.add_task(
                f"Batch {batch_idx + 1}/{len(batches)}",
                total=len(batch),
            )

            for item in batch:
                time.sleep(random.uniform(0.01, 0.05))
                batch_progress.advance(batch_task)

            batch_progress.update(batch_task, visible=False)
            overall_progress.advance(overall_task)


# ============================================================
# 3. Live dashboard with real-time metrics
# ============================================================

@dataclass
class ServiceMetrics:
    name: str
    requests_per_sec: float = 0.0
    error_rate: float = 0.0
    p99_latency_ms: float = 0.0
    active_connections: int = 0
    status: str = "healthy"


def build_dashboard(metrics: list[ServiceMetrics]) -> Table:
    """Build a metrics table for live display."""
    table = Table(title="Service Health Dashboard", show_header=True, header_style="bold magenta")
    table.add_column("Service", style="cyan", width=20)
    table.add_column("RPS", justify="right")
    table.add_column("Error Rate", justify="right")
    table.add_column("P99 Latency", justify="right")
    table.add_column("Connections", justify="right")
    table.add_column("Status", justify="center")

    for m in metrics:
        error_style = "red" if m.error_rate > 5.0 else "yellow" if m.error_rate > 1.0 else "green"
        latency_style = "red" if m.p99_latency_ms > 500 else "yellow" if m.p99_latency_ms > 200 else "green"
        status_icon = {
            "healthy": "[green]OK[/]",
            "degraded": "[yellow]WARN[/]",
            "down": "[red bold]DOWN[/]",
        }.get(m.status, m.status)

        table.add_row(
            m.name,
            f"{m.requests_per_sec:.0f}",
            f"[{error_style}]{m.error_rate:.2f}%[/]",
            f"[{latency_style}]{m.p99_latency_ms:.0f}ms[/]",
            str(m.active_connections),
            status_icon,
        )

    return table


def live_dashboard(duration: int = 30) -> None:
    """Live-updating service dashboard."""
    services = [
        ServiceMetrics("api-gateway"),
        ServiceMetrics("auth-service"),
        ServiceMetrics("user-service"),
        ServiceMetrics("payment-service"),
        ServiceMetrics("notification-svc"),
    ]

    with Live(build_dashboard(services), console=console, refresh_per_second=4) as live:
        for _ in range(duration * 4):
            # Simulate metric changes
            for svc in services:
                svc.requests_per_sec = random.uniform(100, 5000)
                svc.error_rate = random.uniform(0, 3)
                svc.p99_latency_ms = random.uniform(10, 400)
                svc.active_connections = random.randint(10, 500)
                svc.status = random.choice(["healthy"] * 8 + ["degraded"] + ["down"])

            live.update(build_dashboard(services))
            time.sleep(0.25)


# ============================================================
# 4. Interactive selection menus
# ============================================================

def interactive_multi_select(
    title: str,
    options: list[str],
    max_selections: int = 0,
) -> list[str]:
    """Interactive multi-select menu using keyboard input.

    For production use, consider questionary or InquirerPy libraries.
    This shows the pattern with Rich rendering.
    """
    selected: set[int] = set()
    cursor = 0

    def render() -> Panel:
        items = []
        for i, option in enumerate(options):
            prefix = "[bold green]>[/] " if i == cursor else "  "
            checkbox = "[green][X][/]" if i in selected else "[ ]"
            style = "bold" if i == cursor else ""
            items.append(f"{prefix}{checkbox} [{style}]{option}[/]")
        content = "\\n".join(items)
        footer = "\\n[dim]Space=toggle  Enter=confirm  q=cancel[/]"
        return Panel(content + footer, title=title, border_style="cyan")

    # In a real implementation, use raw terminal input
    # Here we show the rendering pattern
    console.print(render())

    # Simplified: use prompts as fallback
    console.print(f"\\n[bold]{title}[/]")
    for i, option in enumerate(options):
        console.print(f"  {i + 1}. {option}")

    choices = Prompt.ask(
        "Enter numbers separated by commas",
        default="1",
    )

    indices = [int(c.strip()) - 1 for c in choices.split(",") if c.strip().isdigit()]
    return [options[i] for i in indices if 0 <= i < len(options)]


def interactive_wizard() -> dict[str, Any]:
    """Multi-step wizard with validation and defaults."""
    console.print(Panel("[bold]Project Setup Wizard[/]", border_style="blue"))

    # Step 1: Project name
    name = Prompt.ask(
        "[cyan]Project name[/]",
        default="my-project",
    )
    while not name.replace("-", "").replace("_", "").isalnum():
        console.print("[red]Name must be alphanumeric (hyphens/underscores allowed)[/]")
        name = Prompt.ask("[cyan]Project name[/]")

    # Step 2: Language selection
    language = Prompt.ask(
        "[cyan]Primary language[/]",
        choices=["python", "typescript", "go", "rust"],
        default="python",
    )

    # Step 3: Port number
    port = IntPrompt.ask(
        "[cyan]Server port[/]",
        default=8000,
    )
    while port < 1024 or port > 65535:
        console.print("[red]Port must be between 1024 and 65535[/]")
        port = IntPrompt.ask("[cyan]Server port[/]")

    # Step 4: Features
    features = interactive_multi_select(
        "Select features",
        ["Docker support", "CI/CD pipeline", "Database migrations",
         "API documentation", "Monitoring", "Authentication"],
    )

    # Step 5: Confirmation
    console.print()
    summary = Table(title="Project Configuration", show_header=False)
    summary.add_column("Setting", style="cyan")
    summary.add_column("Value")
    summary.add_row("Name", name)
    summary.add_row("Language", language)
    summary.add_row("Port", str(port))
    summary.add_row("Features", ", ".join(features) if features else "None")
    console.print(summary)

    if not Confirm.ask("\\nCreate project with these settings?"):
        console.print("[yellow]Cancelled[/]")
        raise SystemExit(0)

    return {"name": name, "language": language, "port": port, "features": features}


# ============================================================
# 5. Spinner patterns for long operations
# ============================================================

def deploy_with_stages() -> None:
    """Multi-stage deployment with spinners and status updates."""
    stages = [
        ("Building application...", 2.0),
        ("Running tests...", 3.0),
        ("Creating container image...", 4.0),
        ("Pushing to registry...", 2.5),
        ("Updating deployment...", 1.5),
        ("Waiting for health check...", 3.0),
    ]

    for i, (description, duration) in enumerate(stages, 1):
        with console.status(f"[bold cyan]({i}/{len(stages)})[/] {description}") as status:
            # Simulate work with status updates
            steps = int(duration / 0.1)
            for step in range(steps):
                if step == steps // 2:
                    status.update(f"[bold cyan]({i}/{len(stages)})[/] {description} [dim](halfway)[/]")
                time.sleep(0.1)

        console.print(f"  [green]\\u2713[/] {description.rstrip('.')} — [green]done[/]")

    console.print()
    console.print(Panel(
        "[bold green]Deployment complete![/]\\n\\n"
        "URL: https://app.example.com\\n"
        "Version: v2.3.1",
        title="Success",
        border_style="green",
    ))
```

**CLI UX patterns:**

| Pattern | Library | Use Case |
|---------|---------|----------|
| Progress bars | `rich.progress` | File downloads, batch processing |
| Live display | `rich.live` | Real-time dashboards, monitoring |
| Spinners | `console.status` | Long-running single operations |
| Tables | `rich.table` | Structured data display |
| Panels | `rich.panel` | Highlighted messages, summaries |
| Prompts | `rich.prompt` | User input with validation |
| Trees | `rich.tree` | Hierarchical data |

**Best practices:**
- Use `stderr` for progress/status output, `stdout` for data (enables piping)
- Always provide `--quiet` / `--json` flags for scriptable output
- Show elapsed time for operations over 2 seconds
- Use spinners for indeterminate tasks, progress bars for measurable ones
- Combine `Live` with `Group` for multi-section real-time displays'''
    ),
    (
        "cli-tools/config-files-and-plugin-systems",
        "Build a CLI plugin system with TOML/YAML configuration, plugin discovery via entry points, hook-based extensibility, and a plugin marketplace pattern.",
        '''CLI plugin system with config management and extensibility:

```python
"""CLI plugin system — entry points, hooks, config management."""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import logging
import tomllib
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum, auto
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

import yaml

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================
# 1. Layered configuration system (TOML + YAML + env)
# ============================================================

@dataclass
class AppConfig:
    """Application configuration with typed fields."""
    app_name: str = "myapp"
    version: str = "0.0.0"
    debug: bool = False
    log_level: str = "INFO"
    database: DatabaseConfig = field(default_factory=lambda: DatabaseConfig())
    plugins: dict[str, dict[str, Any]] = field(default_factory=dict)
    hooks: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class DatabaseConfig:
    url: str = "sqlite:///app.db"
    pool_size: int = 5
    echo: bool = False


class ConfigLoader:
    """Load config from multiple sources with precedence."""

    SEARCH_PATHS = [
        Path("myapp.toml"),
        Path("pyproject.toml"),
        Path.home() / ".config" / "myapp" / "config.toml",
        Path("/etc/myapp/config.toml"),
    ]

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> AppConfig:
        """Load config with precedence: defaults < file < env < overrides."""
        raw: dict[str, Any] = {}

        # Find and load config file
        path = config_path or cls._find_config()
        if path and path.exists():
            raw = cls._load_file(path)
            logger.info("Loaded config from %s", path)

        # Apply environment variable overrides
        import os
        env_mapping = {
            "MYAPP_DEBUG": ("debug", lambda v: v.lower() in ("1", "true")),
            "MYAPP_LOG_LEVEL": ("log_level", str),
            "MYAPP_DATABASE_URL": ("database.url", str),
            "MYAPP_DATABASE_POOL_SIZE": ("database.pool_size", int),
        }
        for env_key, (config_key, converter) in env_mapping.items():
            if value := os.environ.get(env_key):
                cls._set_nested(raw, config_key, converter(value))

        # Apply CLI overrides
        if overrides:
            for key, value in overrides.items():
                cls._set_nested(raw, key, value)

        return cls._build_config(raw)

    @classmethod
    def _find_config(cls) -> Path | None:
        for path in cls.SEARCH_PATHS:
            if path.exists():
                return path
        return None

    @classmethod
    def _load_file(cls, path: Path) -> dict[str, Any]:
        content = path.read_text()
        if path.suffix == ".toml":
            data = tomllib.loads(content)
            # Handle pyproject.toml nesting
            if "tool" in data and "myapp" in data["tool"]:
                return data["tool"]["myapp"]
            return data
        elif path.suffix in (".yml", ".yaml"):
            return yaml.safe_load(content)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}")

    @classmethod
    def _set_nested(cls, d: dict, key: str, value: Any) -> None:
        """Set a nested key like 'database.url'."""
        parts = key.split(".")
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value

    @classmethod
    def _build_config(cls, raw: dict[str, Any]) -> AppConfig:
        db_raw = raw.get("database", {})
        db_config = DatabaseConfig(
            url=db_raw.get("url", DatabaseConfig.url),
            pool_size=db_raw.get("pool_size", DatabaseConfig.pool_size),
            echo=db_raw.get("echo", DatabaseConfig.echo),
        )
        return AppConfig(
            app_name=raw.get("app_name", AppConfig.app_name),
            version=raw.get("version", AppConfig.version),
            debug=raw.get("debug", AppConfig.debug),
            log_level=raw.get("log_level", AppConfig.log_level),
            database=db_config,
            plugins=raw.get("plugins", {}),
            hooks=raw.get("hooks", {}),
        )


# ============================================================
# 2. Plugin protocol and base class
# ============================================================

class HookType(StrEnum):
    PRE_COMMAND = auto()
    POST_COMMAND = auto()
    ON_ERROR = auto()
    ON_STARTUP = auto()
    ON_SHUTDOWN = auto()
    TRANSFORM_OUTPUT = auto()


@runtime_checkable
class PluginProtocol(Protocol):
    """Minimum interface a plugin must satisfy."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def activate(self, config: dict[str, Any]) -> None: ...

    def deactivate(self) -> None: ...


class BasePlugin(ABC):
    """Base class for plugins with lifecycle and hook registration."""

    def __init__(self) -> None:
        self._hooks: dict[HookType, list[Callable]] = {}
        self._active = False

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    def active(self) -> bool:
        return self._active

    def activate(self, config: dict[str, Any]) -> None:
        """Initialize plugin with its config section."""
        self._active = True
        self.on_activate(config)

    def deactivate(self) -> None:
        self.on_deactivate()
        self._active = False

    def on_activate(self, config: dict[str, Any]) -> None:
        """Override for custom activation logic."""
        pass

    def on_deactivate(self) -> None:
        """Override for custom deactivation logic."""
        pass

    def register_hook(self, hook_type: HookType, handler: Callable) -> None:
        self._hooks.setdefault(hook_type, []).append(handler)

    def get_hooks(self, hook_type: HookType) -> list[Callable]:
        return self._hooks.get(hook_type, [])


# ============================================================
# 3. Plugin registry with discovery
# ============================================================

class PluginRegistry:
    """Discovers, loads, and manages plugins."""

    ENTRY_POINT_GROUP = "myapp.plugins"

    def __init__(self) -> None:
        self._plugins: dict[str, BasePlugin] = {}
        self._hooks: dict[HookType, list[Callable]] = {h: [] for h in HookType}

    def discover(self) -> list[str]:
        """Discover plugins via setuptools entry points."""
        discovered = []
        try:
            eps = importlib.metadata.entry_points()
            # Python 3.12+ returns a SelectableGroups
            if hasattr(eps, "select"):
                plugin_eps = eps.select(group=self.ENTRY_POINT_GROUP)
            else:
                plugin_eps = eps.get(self.ENTRY_POINT_GROUP, [])

            for ep in plugin_eps:
                discovered.append(ep.name)
                logger.info("Discovered plugin: %s (%s)", ep.name, ep.value)
        except Exception as exc:
            logger.warning("Plugin discovery failed: %s", exc)

        return discovered

    def load(self, name: str, config: dict[str, Any] | None = None) -> BasePlugin:
        """Load and activate a plugin by name."""
        if name in self._plugins:
            return self._plugins[name]

        # Try entry point first
        plugin_class = self._load_from_entry_point(name)
        if not plugin_class:
            # Try direct module import
            plugin_class = self._load_from_module(name)

        if not plugin_class:
            raise PluginNotFoundError(f"Plugin not found: {name}")

        plugin = plugin_class()
        if not isinstance(plugin, PluginProtocol):
            raise PluginError(f"Plugin {name} does not satisfy PluginProtocol")

        plugin.activate(config or {})
        self._plugins[name] = plugin

        # Register hooks
        if isinstance(plugin, BasePlugin):
            for hook_type in HookType:
                for handler in plugin.get_hooks(hook_type):
                    self._hooks[hook_type].append(handler)

        logger.info("Loaded plugin: %s v%s", plugin.name, plugin.version)
        return plugin

    def _load_from_entry_point(self, name: str) -> type[BasePlugin] | None:
        try:
            eps = importlib.metadata.entry_points()
            if hasattr(eps, "select"):
                matches = list(eps.select(group=self.ENTRY_POINT_GROUP, name=name))
            else:
                matches = [ep for ep in eps.get(self.ENTRY_POINT_GROUP, []) if ep.name == name]

            if matches:
                return matches[0].load()
        except Exception as exc:
            logger.debug("Entry point load failed for %s: %s", name, exc)
        return None

    def _load_from_module(self, name: str) -> type[BasePlugin] | None:
        try:
            module = importlib.import_module(f"myapp_plugins.{name}")
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    return obj
        except ImportError:
            pass
        return None

    async def run_hooks(self, hook_type: HookType, **kwargs: Any) -> list[Any]:
        """Execute all registered hooks of a given type."""
        results = []
        for handler in self._hooks.get(hook_type, []):
            try:
                if inspect.iscoroutinefunction(handler):
                    result = await handler(**kwargs)
                else:
                    result = handler(**kwargs)
                results.append(result)
            except Exception as exc:
                logger.error("Hook %s failed in handler %s: %s",
                             hook_type, handler.__name__, exc)
                if hook_type == HookType.ON_ERROR:
                    raise  # Don't swallow errors in error handlers
        return results

    def unload(self, name: str) -> None:
        plugin = self._plugins.pop(name, None)
        if plugin:
            plugin.deactivate()
            logger.info("Unloaded plugin: %s", name)

    def list_plugins(self) -> list[dict[str, str]]:
        return [
            {"name": p.name, "version": p.version, "active": str(p.active)}
            for p in self._plugins.values()
        ]


class PluginNotFoundError(Exception):
    pass

class PluginError(Exception):
    pass


# ============================================================
# 4. Example plugins
# ============================================================

class TimingPlugin(BasePlugin):
    """Measures command execution time."""

    name = "timing"
    version = "1.0.0"

    def on_activate(self, config: dict[str, Any]) -> None:
        self._threshold_ms = config.get("threshold_ms", 100)
        self.register_hook(HookType.PRE_COMMAND, self._start_timer)
        self.register_hook(HookType.POST_COMMAND, self._stop_timer)

    def _start_timer(self, **kwargs: Any) -> None:
        import time
        self._start = time.monotonic()

    def _stop_timer(self, **kwargs: Any) -> None:
        import time
        elapsed_ms = (time.monotonic() - self._start) * 1000
        if elapsed_ms > self._threshold_ms:
            logger.warning("Command took %.1fms (threshold: %dms)",
                          elapsed_ms, self._threshold_ms)


class AuditPlugin(BasePlugin):
    """Logs all commands for audit trail."""

    name = "audit"
    version = "1.0.0"

    def on_activate(self, config: dict[str, Any]) -> None:
        self._log_file = Path(config.get("log_file", "audit.log"))
        self.register_hook(HookType.PRE_COMMAND, self._log_command)
        self.register_hook(HookType.ON_ERROR, self._log_error)

    def _log_command(self, command: str = "", **kwargs: Any) -> None:
        from datetime import datetime, timezone
        entry = f"{datetime.now(timezone.utc).isoformat()} CMD: {command}\\n"
        with open(self._log_file, "a") as f:
            f.write(entry)

    def _log_error(self, error: Exception | None = None, **kwargs: Any) -> None:
        from datetime import datetime, timezone
        entry = f"{datetime.now(timezone.utc).isoformat()} ERR: {error}\\n"
        with open(self._log_file, "a") as f:
            f.write(entry)


# ============================================================
# 5. Config file example (myapp.toml)
# ============================================================

EXAMPLE_CONFIG = """
# myapp.toml
app_name = "myapp"
version = "1.2.0"
debug = false
log_level = "INFO"

[database]
url = "postgresql://localhost:5432/mydb"
pool_size = 10
echo = false

[plugins.timing]
threshold_ms = 200

[plugins.audit]
log_file = "/var/log/myapp/audit.log"

[hooks]
pre_command = ["timing", "audit"]
post_command = ["timing"]
on_error = ["audit"]
"""

# Entry point registration in pyproject.toml:
# [project.entry-points."myapp.plugins"]
# timing = "myapp_plugins.timing:TimingPlugin"
# audit = "myapp_plugins.audit:AuditPlugin"
```

**Plugin system architecture:**

| Component | Role | Discovery |
|-----------|------|-----------|
| `PluginProtocol` | Contract for all plugins | Type checking |
| `BasePlugin` | Lifecycle + hook registration | Inheritance |
| `PluginRegistry` | Load/unload/discover | Entry points + module import |
| `HookType` | Named extension points | Enum-based hook dispatch |
| `ConfigLoader` | Layered config management | TOML/YAML + env vars |

**Best practices:**
- Use entry points (`pyproject.toml`) for discoverable plugin distribution
- Define a minimal protocol; use base class for convenience
- Always provide `activate`/`deactivate` lifecycle hooks
- Support both sync and async hook handlers
- Layer config: file < environment < CLI for 12-factor compliance
- Log plugin load/unload events for debugging'''
    ),
    (
        "cli-tools/click-advanced-patterns",
        "Show advanced Click patterns including custom parameter types, lazy loading command groups, command chaining, context passing, and testing CLI applications.",
        '''Advanced Click patterns for production CLI tools:

```python
"""Advanced Click — custom types, lazy groups, chaining, testing."""

from __future__ import annotations

import functools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
from click.testing import CliRunner


# ============================================================
# 1. Custom parameter types with validation
# ============================================================

class DateTimeType(click.ParamType):
    """Click parameter type for datetime parsing with multiple formats."""

    name = "datetime"
    FORMATS = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y",
    ]

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> datetime:
        if isinstance(value, datetime):
            return value

        for fmt in self.FORMATS:
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        self.fail(
            f"Cannot parse datetime: {value!r}. "
            f"Supported formats: {', '.join(self.FORMATS)}",
            param, ctx,
        )


class SemVerType(click.ParamType):
    """Semantic version parameter type."""

    name = "semver"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> tuple[int, int, int]:
        if isinstance(value, tuple):
            return value

        import re
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", value)
        if not match:
            self.fail(f"Invalid semantic version: {value!r} (expected X.Y.Z)", param, ctx)

        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


class KeyValueType(click.ParamType):
    """Key=value parameter type for metadata/labels."""

    name = "key=value"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> tuple[str, str]:
        if isinstance(value, tuple):
            return value

        if "=" not in value:
            self.fail(f"Expected KEY=VALUE format, got: {value!r}", param, ctx)

        key, _, val = value.partition("=")
        if not key:
            self.fail("Key cannot be empty", param, ctx)

        return (key, val)


DATETIME = DateTimeType()
SEMVER = SemVerType()
KEY_VALUE = KeyValueType()


# ============================================================
# 2. Context object for shared state
# ============================================================

class AppContext:
    """Shared context passed through Click's context system."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = {}
        self.verbose: bool = False
        self.output_format: str = "text"
        self.dry_run: bool = False

    def log(self, message: str, level: str = "info") -> None:
        if self.verbose or level in ("warning", "error"):
            prefix = {"info": "INFO", "warning": "WARN", "error": "ERROR"}.get(level, level.upper())
            click.echo(f"[{prefix}] {message}", err=True)

    def output(self, data: Any) -> None:
        """Output data in configured format."""
        if self.output_format == "json":
            click.echo(json.dumps(data, indent=2, default=str))
        elif self.output_format == "csv":
            if isinstance(data, list) and data:
                keys = data[0].keys()
                click.echo(",".join(keys))
                for row in data:
                    click.echo(",".join(str(row.get(k, "")) for k in keys))
        else:
            if isinstance(data, list):
                for item in data:
                    click.echo(item)
            else:
                click.echo(data)


pass_context = click.make_pass_decorator(AppContext, ensure=True)


# ============================================================
# 3. Main CLI group with shared options
# ============================================================

@click.group(chain=True)  # Enable command chaining
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--format", "output_format",
              type=click.Choice(["text", "json", "csv"]),
              default="text", help="Output format")
@click.option("--dry-run", "-n", is_flag=True, help="Simulate without executing")
@click.option("--config", "config_path",
              type=click.Path(exists=True, path_type=Path),
              envvar="MYAPP_CONFIG", help="Config file path")
@click.version_option("1.0.0", prog_name="myapp")
@pass_context
def cli(ctx: AppContext, verbose: bool, output_format: str,
        dry_run: bool, config_path: Path | None) -> None:
    """MyApp CLI — manage deployments and infrastructure.

    Commands can be chained: myapp filter --env prod list deploy
    """
    ctx.verbose = verbose
    ctx.output_format = output_format
    ctx.dry_run = dry_run

    if config_path:
        with open(config_path) as f:
            ctx.config = json.load(f)


# ============================================================
# 4. Commands with custom types and chaining
# ============================================================

@cli.command()
@click.option("--env", "-e",
              type=click.Choice(["dev", "staging", "prod"]),
              help="Filter by environment")
@click.option("--since", type=DATETIME, help="Filter since datetime")
@click.option("--label", "-l", type=KEY_VALUE, multiple=True,
              help="Filter by label (KEY=VALUE)")
@pass_context
def filter(ctx: AppContext, env: str | None, since: datetime | None,
           label: tuple[tuple[str, str], ...]) -> None:
    """Filter resources by criteria. Can be chained with other commands."""
    filters = {}
    if env:
        filters["environment"] = env
    if since:
        filters["since"] = since.isoformat()
    if label:
        filters["labels"] = dict(label)

    ctx.config["active_filters"] = filters
    ctx.log(f"Applied filters: {filters}")


@cli.command("list")
@click.option("--limit", "-n", default=50, show_default=True,
              help="Maximum items to show")
@click.option("--sort", type=click.Choice(["name", "date", "status"]),
              default="date", help="Sort field")
@pass_context
def list_resources(ctx: AppContext, limit: int, sort: str) -> None:
    """List resources matching current filters."""
    filters = ctx.config.get("active_filters", {})

    # Simulated data
    resources = [
        {"name": "api-v2", "env": "prod", "status": "running", "updated": "2026-03-01"},
        {"name": "worker-3", "env": "prod", "status": "running", "updated": "2026-02-28"},
        {"name": "api-v2", "env": "staging", "status": "stopped", "updated": "2026-02-25"},
    ]

    # Apply filters
    if env := filters.get("environment"):
        resources = [r for r in resources if r["env"] == env]

    resources = sorted(resources, key=lambda r: r.get(sort, ""))[:limit]
    ctx.output(resources)


@cli.command()
@click.argument("targets", nargs=-1, required=True)
@click.option("--version", "-V", type=SEMVER, required=True,
              help="Version to deploy (X.Y.Z)")
@click.option("--strategy",
              type=click.Choice(["rolling", "blue-green", "canary"]),
              default="rolling", show_default=True)
@click.option("--canary-percent", type=click.IntRange(1, 100), default=10,
              help="Canary traffic percentage")
@click.confirmation_option(prompt="Are you sure you want to deploy?")
@pass_context
def deploy(ctx: AppContext, targets: tuple[str, ...], version: tuple[int, int, int],
           strategy: str, canary_percent: int) -> None:
    """Deploy to specified targets."""
    ver_str = ".".join(str(v) for v in version)

    if ctx.dry_run:
        ctx.log(f"[DRY RUN] Would deploy v{ver_str} to {', '.join(targets)} "
                f"using {strategy} strategy")
        return

    for target in targets:
        ctx.log(f"Deploying v{ver_str} to {target} ({strategy})...")
        # Simulate deployment steps
        with click.progressbar(
            range(10),
            label=f"Deploying to {target}",
            show_percent=True,
            show_eta=True,
        ) as steps:
            for step in steps:
                import time
                time.sleep(0.1)

        click.secho(f"  Deployed to {target}", fg="green")

    ctx.output({"deployed": list(targets), "version": ver_str, "strategy": strategy})


# ============================================================
# 5. Lazy-loaded command groups (for large CLIs)
# ============================================================

class LazyGroup(click.Group):
    """Lazy-loading command group — imports commands only when invoked."""

    def __init__(self, *args: Any, lazy_subcommands: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lazy_subcommands = lazy_subcommands or {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        base = super().list_commands(ctx)
        lazy = sorted(self._lazy_subcommands.keys())
        return base + lazy

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self._lazy_subcommands:
            return self._load_command(cmd_name)
        return super().get_command(ctx, cmd_name)

    def _load_command(self, name: str) -> click.Command:
        module_path = self._lazy_subcommands[name]
        module_name, attr_name = module_path.rsplit(":", 1)
        module = importlib.import_module(module_name)
        return getattr(module, attr_name)


# Usage:
# @click.group(cls=LazyGroup, lazy_subcommands={
#     "database": "myapp.commands.database:db_group",
#     "monitor": "myapp.commands.monitor:monitor_group",
#     "plugin": "myapp.commands.plugins:plugin_group",
# })
# def cli(): ...


# ============================================================
# 6. Testing CLI commands
# ============================================================

import pytest


class TestCLI:
    """Test suite for CLI commands using Click's CliRunner."""

    def setup_method(self) -> None:
        self.runner = CliRunner(mix_stderr=False)

    def test_list_text_output(self) -> None:
        result = self.runner.invoke(cli, ["list", "--limit", "2"])
        assert result.exit_code == 0
        assert "api-v2" in result.output

    def test_list_json_output(self) -> None:
        result = self.runner.invoke(cli, ["--format", "json", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_filter_chain_list(self) -> None:
        """Test command chaining: filter then list."""
        result = self.runner.invoke(
            cli, ["filter", "--env", "prod", "list", "--sort", "name"]
        )
        assert result.exit_code == 0

    def test_deploy_dry_run(self) -> None:
        result = self.runner.invoke(
            cli, ["--dry-run", "deploy", "api-v2", "--version", "2.1.0",
                  "--strategy", "rolling", "--yes"]
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.stderr

    def test_deploy_invalid_version(self) -> None:
        result = self.runner.invoke(
            cli, ["deploy", "api-v2", "--version", "invalid"]
        )
        assert result.exit_code != 0
        assert "Invalid semantic version" in result.output or result.exit_code == 2

    def test_custom_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"environment": "test"}))

        result = self.runner.invoke(
            cli, ["--config", str(config_file), "list"]
        )
        assert result.exit_code == 0

    def test_verbose_output(self) -> None:
        result = self.runner.invoke(
            cli, ["-v", "filter", "--env", "prod"]
        )
        assert result.exit_code == 0
        assert "Applied filters" in result.stderr

    def test_env_var_config(self) -> None:
        result = self.runner.invoke(
            cli, ["list"],
            env={"MYAPP_CONFIG": "/nonexistent"},
        )
        # Should fail gracefully or use defaults
        assert result.exit_code in (0, 2)
```

**Click vs Typer comparison:**

| Feature | Click | Typer |
|---------|-------|-------|
| Type hints for args | Custom `ParamType` classes | Native Python type hints |
| Subcommands | `@group.command()` | `app.add_typer()` |
| Command chaining | `chain=True` on group | Not built-in |
| Lazy loading | Custom `Group` subclass | Not built-in |
| Testing | `CliRunner` | `CliRunner` (from Click) |
| Auto-completion | Plugin-based | Built-in |
| Rich output | Manual integration | Built-in |
| Learning curve | Moderate | Low (Python-native feel) |

**Best practices:**
- Use `CliRunner(mix_stderr=False)` in tests to separate stdout/stderr
- Define custom `ParamType` for domain-specific values (dates, versions, etc.)
- Use `click.make_pass_decorator` for shared state across commands
- Implement `LazyGroup` for CLIs with many commands to reduce import time
- Always test both success and error paths, including validation failures
- Use `--yes` / `@click.confirmation_option` for destructive commands'''
    ),
]
"""
