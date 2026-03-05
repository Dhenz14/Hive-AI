"""CLI tools -- argument parsing (Click/Typer), progress bars, interactive prompts, config files, plugin systems."""

PAIRS = [
    (
        "cli-tools/typer-advanced-application",
        "Build a production-quality CLI application using Typer with subcommands, auto-completion, rich output, configuration management, and error handling.",
        '''Production CLI tool using Typer + Rich -- database migration manager."""

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
    TimeRemainingColumn,'''
    ),
    (
        "timeout",
        "}, f, indent=2)",
        '''class State:
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
    """[bold blue]dbmigrate[/] -- Database migration manager.

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
        console.print("[yellow]Dry run -- no changes applied[/]")
        raise typer.Exit()

    # Confirm for production
    if environment == Environment.PROD:
        confirm = typer.confirm(
            f"Apply {len(pending)} migration(s) to PRODUCTION?",
            abort=True,'''
    ),
    (
        "applied",
        "}) return migrations",
        '''# 6. Shell completion
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
        '''Rich progress bars, interactive prompts, and live displays."""

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
    TransferSpeedColumn,'''
    ),
    (
        "downloading",
        "filename=filename total=file_size ) tasks[task_id] = file_size while not progress.finished: for task_id, total_size in tasks.items(): if not progress.tasks[task_id].finished: chunk = random.randint(1000, 50000) progress.update(task_id, advance=chunk) await asyncio.sleep(0.05)",
        '''# 2. Nested progress -- overall + per-item
# ============================================================

def process_batches(batches: list[list[dict]]) -> None:
    """Two-level progress: overall batches + items within each batch."""
    overall_progress = Progress(
        TextColumn("[bold blue]Overall"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),'''
    ),
    (
        "down",
        "}.get(m.status, m.status) table.add_row( m.name f'{m.requests_per_sec:.0f}' f'[{error_style}]{m.error_rate:.2f}%[/]' f'[{latency_style}]{m.p99_latency_ms:.0f}ms[/]' str(m.active_connections) status_icon ) return table def live_dashboard(duration: int = 30) -> None:",
        '''ServiceMetrics("api-gateway"),
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
        default="1",'''
    ),
    (
        "cli-tools/config-files-and-plugin-systems",
        "Build a CLI plugin system with TOML/YAML configuration, plugin discovery via entry points, hook-based extensibility, and a plugin marketplace pattern.",
        '''CLI plugin system -- entry points, hooks, config management."""

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
        env_mapping = {'''
    ),
    (
        "MYAPP_DATABASE_POOL_SIZE",
        "} for env_key, (config_key, converter) in env_mapping.items(): if value := os.environ.get(env_key): cls._set_nested(raw, config_key, converter(value))",
        '''if overrides:
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
            echo=db_raw.get("echo", DatabaseConfig.echo),'''
    ),
    (
        "cli-tools/click-advanced-patterns",
        "Show advanced Click patterns including custom parameter types, lazy loading command groups, command chaining, context passing, and testing CLI applications.",
        '''Advanced Click -- custom types, lazy groups, chaining, testing."""

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
            param, ctx,'''
    ),
    (
        "--strategy",
        ") assert result.exit_code == 0 assert 'DRY RUN' in result.stderr def test_deploy_invalid_version(self) -> None: result = self.runner.invoke( cli, ['deploy', 'api-v2', '--version', 'invalid'] ) assert result.exit_code != 0 assert 'Invalid semantic version' in result.output or result.exit_code == 2 def test_custom_config(self, tmp_path: Path) -> None: config_file = tmp_path / 'config.json config_file.write_text(json.dumps({'environment': 'test'})) result = self.runner.invoke( cli, ['--config', str(config_file), 'list'] ) assert result.exit_code == 0 def test_verbose_output(self) -> None: result = self.runner.invoke( cli, ['-v', 'filter', '--env', 'prod'] ) assert result.exit_code == 0 assert 'Applied filters' in result.stderr def test_env_var_config(self) -> None: result = self.runner.invoke( cli, ['list'] env={'MYAPP_CONFIG': '/nonexistent'} )",
        '''assert result.exit_code in (0, 2)
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
