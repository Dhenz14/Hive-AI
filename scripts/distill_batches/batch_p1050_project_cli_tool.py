PAIRS = [
    ("projects/cli-tool", r'''<think>
The user wants to build a CLI tool with argument parsing and subcommands.
I should use argparse with subparsers for a clean CLI interface,
and include a config file loader for persistent settings.
</think>
Build a Python CLI tool with argument parsing, subcommands, and config file support. Show the main entry point and argument setup.''', r'''import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_DIR = Path.home() / ".mycli"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> Dict[str, Any]:
    """Load configuration from the config file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"default_format": "json", "verbose": False, "output_dir": "."}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to the config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new project in the current directory."""
    project_dir = Path(args.path or ".")
    project_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": args.name or project_dir.name,
        "version": "0.1.0",
        "description": "",
    }
    manifest_path = project_dir / "manifest.json"
    if manifest_path.exists() and not args.force:
        print(f"Error: {manifest_path} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Initialized project '{manifest['name']}' at {project_dir.resolve()}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Get or set configuration values."""
    config = load_config()
    if args.action == "get":
        if args.key:
            value = config.get(args.key)
            if value is None:
                print(f"Key '{args.key}' not found.", file=sys.stderr)
                return 1
            print(f"{args.key} = {value}")
        else:
            for k, v in config.items():
                print(f"{k} = {v}")
    elif args.action == "set":
        if not args.key or args.value is None:
            print("Both --key and --value are required for 'set'.", file=sys.stderr)
            return 1
        config[args.key] = args.value
        save_config(config)
        print(f"Set {args.key} = {args.value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="mycli",
        description="A project management CLI tool",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--version", action="version", version="mycli 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init subcommand
    init_parser = subparsers.add_parser("init", help="Initialize a new project")
    init_parser.add_argument("--name", "-n", help="Project name")
    init_parser.add_argument("--path", "-p", help="Project path")
    init_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")
    init_parser.set_defaults(func=cmd_init)

    # config subcommand
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_parser.add_argument("action", choices=["get", "set"], help="Action to perform")
    config_parser.add_argument("--key", "-k", help="Configuration key")
    config_parser.add_argument("--value", help="Configuration value")
    config_parser.set_defaults(func=cmd_config)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
'''),
    ("projects/cli-tool", r'''Add colored terminal output support to the CLI tool. Implement a color utility module that works cross-platform.''', r'''import sys
from typing import Optional


# ANSI color codes
class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"


def _supports_color() -> bool:
    """Check if the terminal supports color output."""
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable ANSI escape sequences on Windows 10+
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True


_color_enabled = _supports_color()


def colorize(text: str, color: str, bold: bool = False) -> str:
    """Apply color to text if the terminal supports it."""
    if not _color_enabled:
        return text
    prefix = ""
    if bold:
        prefix = Colors.BOLD
    return f"{prefix}{color}{text}{Colors.RESET}"


def success(message: str) -> None:
    """Print a success message in green."""
    symbol = colorize("[OK]", Colors.GREEN, bold=True)
    print(f"{symbol} {message}")


def error(message: str) -> None:
    """Print an error message in red to stderr."""
    symbol = colorize("[ERROR]", Colors.RED, bold=True)
    print(f"{symbol} {message}", file=sys.stderr)


def warning(message: str) -> None:
    """Print a warning message in yellow."""
    symbol = colorize("[WARN]", Colors.YELLOW, bold=True)
    print(f"{symbol} {message}")


def info(message: str) -> None:
    """Print an info message in blue."""
    symbol = colorize("[INFO]", Colors.BLUE, bold=True)
    print(f"{symbol} {message}")


def header(title: str) -> None:
    """Print a bold header with a separator line."""
    line = colorize("=" * (len(title) + 4), Colors.CYAN)
    title_text = colorize(f"  {title}  ", Colors.CYAN, bold=True)
    print(line)
    print(title_text)
    print(line)


class Spinner:
    """A simple terminal spinner for long-running operations."""
    FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, message: str = "Working"):
        self.message = message
        self._frame = 0

    def tick(self) -> None:
        """Advance the spinner by one frame."""
        frame_char = self.FRAMES[self._frame % len(self.FRAMES)]
        colored_frame = colorize(frame_char, Colors.CYAN, bold=True)
        sys.stdout.write(f"\r{colored_frame} {self.message}...")
        sys.stdout.flush()
        self._frame += 1

    def done(self, final_message: Optional[str] = None) -> None:
        """Complete the spinner with a final message."""
        msg = final_message or self.message
        sys.stdout.write(f"\r{colorize('[OK]', Colors.GREEN, bold=True)} {msg}   \n")
        sys.stdout.flush()


# Usage example:
# header("Project Setup")
# info("Loading configuration...")
# success("Project initialized successfully")
# warning("No .gitignore found")
# error("Failed to connect to remote")
'''),
    ("projects/cli-tool", r'''<think>
A progress bar is essential for CLI tools that process files or data.
I need to handle terminal width detection, percentage calculation,
and ETA estimation. Should work both for known and unknown totals.
</think>
Implement a progress bar component for the CLI tool that supports both determinate and indeterminate progress, ETA estimation, and transfer rate display.''', r'''import sys
import time
import shutil
from typing import Optional


class ProgressBar:
    """A terminal progress bar with ETA and rate estimation."""

    def __init__(
        self,
        total: Optional[int] = None,
        description: str = "",
        unit: str = "it",
        bar_width: Optional[int] = None,
    ):
        self.total = total
        self.description = description
        self.unit = unit
        self.current = 0
        self._start_time = time.monotonic()
        self._last_update = 0.0
        self._min_interval = 0.05  # minimum seconds between redraws

        term_width = shutil.get_terminal_size((80, 24)).columns
        if bar_width is None:
            self.bar_width = max(10, term_width - 60)
        else:
            self.bar_width = bar_width

    def update(self, n: int = 1) -> None:
        """Advance the progress bar by n steps."""
        self.current += n
        now = time.monotonic()
        if now - self._last_update < self._min_interval:
            return
        self._last_update = now
        self._render()

    def _format_time(self, seconds: float) -> str:
        """Format seconds into human-readable time string."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}m{s:02d}s"
        else:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"{h}h{m:02d}m"

    def _format_rate(self, rate: float) -> str:
        """Format the processing rate."""
        if rate < 1:
            return f"{rate:.2f} {self.unit}/s"
        elif rate < 1000:
            return f"{rate:.1f} {self.unit}/s"
        else:
            return f"{rate/1000:.1f}k {self.unit}/s"

    def _render(self) -> None:
        """Render the progress bar to stdout."""
        elapsed = time.monotonic() - self._start_time
        rate = self.current / elapsed if elapsed > 0 else 0.0

        if self.total is not None and self.total > 0:
            fraction = min(1.0, self.current / self.total)
            percent = fraction * 100
            filled = int(self.bar_width * fraction)
            bar = "#" * filled + "-" * (self.bar_width - filled)

            if rate > 0 and fraction < 1.0:
                remaining = (self.total - self.current) / rate
                eta_str = self._format_time(remaining)
            else:
                eta_str = "???"

            line = (
                f"\r{self.description} "
                f"[{bar}] "
                f"{percent:5.1f}% "
                f"{self.current}/{self.total} "
                f"[{self._format_time(elapsed)}<{eta_str}, {self._format_rate(rate)}]"
            )
        else:
            # Indeterminate progress - spinning indicator
            spinner_chars = "|/-\\"
            spinner = spinner_chars[self.current % len(spinner_chars)]
            line = (
                f"\r{self.description} "
                f"{spinner} "
                f"{self.current} {self.unit} "
                f"[{self._format_time(elapsed)}, {self._format_rate(rate)}]"
            )

        term_width = shutil.get_terminal_size((80, 24)).columns
        line = line[:term_width]
        sys.stdout.write(line)
        sys.stdout.flush()

    def finish(self) -> None:
        """Complete the progress bar and print a newline."""
        self._render()
        sys.stdout.write("\n")
        sys.stdout.flush()

    def __enter__(self) -> "ProgressBar":
        return self

    def __exit__(self, *args) -> None:
        self.finish()


def iterate_with_progress(iterable, description: str = "", unit: str = "it"):
    """Wrap an iterable with a progress bar."""
    try:
        total = len(iterable)
    except TypeError:
        total = None

    with ProgressBar(total=total, description=description, unit=unit) as bar:
        for item in iterable:
            yield item
            bar.update(1)


# Usage:
# with ProgressBar(total=1000, description="Processing", unit="files") as bar:
#     for i in range(1000):
#         process(i)
#         bar.update(1)
#
# for item in iterate_with_progress(my_list, "Loading"):
#     handle(item)
'''),
    ("projects/cli-tool", r'''Implement the subcommand system for the CLI tool, including a build subcommand that compiles project assets, and a run subcommand that executes the project.''', r'''import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable

# Assuming color utilities and progress bar from previous modules
# from .colors import success, error, info, warning
# from .progress import ProgressBar


class SubcommandRegistry:
    """Registry for CLI subcommands with plugin support."""

    def __init__(self):
        self._commands: Dict[str, dict] = {}

    def register(
        self,
        name: str,
        help_text: str,
        handler: Callable,
        aliases: Optional[List[str]] = None,
    ):
        """Register a subcommand with its handler."""
        entry = {
            "name": name,
            "help": help_text,
            "handler": handler,
            "aliases": aliases or [],
        }
        self._commands[name] = entry
        for alias in (aliases or []):
            self._commands[alias] = entry

    def get(self, name: str) -> Optional[dict]:
        return self._commands.get(name)

    def all_commands(self) -> List[dict]:
        seen = set()
        result = []
        for entry in self._commands.values():
            if entry["name"] not in seen:
                seen.add(entry["name"])
                result.append(entry)
        return result

    def attach_to_parser(self, subparsers) -> None:
        for cmd in self.all_commands():
            p = subparsers.add_parser(
                cmd["name"],
                help=cmd["help"],
                aliases=cmd.get("aliases", []),
            )
            p.set_defaults(func=cmd["handler"])
            yield cmd["name"], p


registry = SubcommandRegistry()


def cmd_build(args: argparse.Namespace) -> int:
    """Build command - compiles project assets."""
    project_dir = Path(args.project_dir or ".")
    manifest_path = project_dir / "manifest.json"

    if not manifest_path.exists():
        print("Error: No manifest.json found. Run 'mycli init' first.", file=sys.stderr)
        return 1

    src_dir = project_dir / "src"
    build_dir = project_dir / "build"
    build_dir.mkdir(exist_ok=True)

    if not src_dir.exists():
        print("Error: No src/ directory found.", file=sys.stderr)
        return 1

    source_files = list(src_dir.rglob("*.py"))
    if not source_files:
        print("No source files found to build.")
        return 0

    print(f"Building {len(source_files)} file(s)...")

    errors = []
    for i, src_file in enumerate(source_files):
        rel_path = src_file.relative_to(src_dir)
        dest = build_dir / rel_path.with_suffix(".pyc")
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            import py_compile
            py_compile.compile(str(src_file), str(dest), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append((src_file, str(e)))
            continue

        progress = (i + 1) / len(source_files) * 100
        print(f"  [{progress:5.1f}%] Compiled {rel_path}")

    if errors:
        print(f"\nBuild completed with {len(errors)} error(s):", file=sys.stderr)
        for path, msg in errors:
            print(f"  - {path}: {msg}", file=sys.stderr)
        return 1

    print(f"\nBuild successful: {len(source_files)} file(s) compiled to {build_dir}/")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run command - executes the project entry point."""
    project_dir = Path(args.project_dir or ".")
    entry_point = project_dir / "src" / "main.py"

    if not entry_point.exists():
        print(f"Error: Entry point not found at {entry_point}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_dir / "src") + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [sys.executable, str(entry_point)] + (args.extra_args or [])
    print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, env=env, cwd=str(project_dir))
        return result.returncode
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130


def cmd_clean(args: argparse.Namespace) -> int:
    """Clean command - removes build artifacts."""
    import shutil
    project_dir = Path(args.project_dir or ".")
    build_dir = project_dir / "build"

    if build_dir.exists():
        shutil.rmtree(build_dir)
        print(f"Removed {build_dir}/")
    else:
        print("Nothing to clean.")
    return 0


# Register all commands
registry.register("build", "Compile project assets", cmd_build, aliases=["b"])
registry.register("run", "Execute the project", cmd_run, aliases=["r"])
registry.register("clean", "Remove build artifacts", cmd_clean)
'''),
    ("projects/cli-tool", r'''<think>
The final piece is interactive prompts and confirmation dialogs.
This makes the CLI user-friendly for destructive operations and setup wizards.
I need to handle input validation and default values cleanly.
</think>
Implement interactive prompts for the CLI tool: confirmation dialogs, text input with defaults, selection menus, and a setup wizard.''', r'''import sys
from typing import Any, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")


def confirm(message: str, default: bool = False) -> bool:
    """Ask the user a yes/no question and return a boolean."""
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        response = input(message + suffix).strip().lower()
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def prompt(
    message: str,
    default: Optional[str] = None,
    validator: Optional[Callable[[str], bool]] = None,
    error_message: str = "Invalid input. Please try again.",
) -> str:
    """Prompt the user for text input with optional validation."""
    suffix = f" [{default}]" if default else ""
    while True:
        response = input(f"{message}{suffix}: ").strip()
        if not response and default is not None:
            response = default
        if not response:
            print("Input is required.")
            continue
        if validator and not validator(response):
            print(error_message)
            continue
        return response


def select(
    message: str,
    options: List[str],
    default: Optional[int] = None,
) -> int:
    """Display a selection menu and return the chosen index."""
    print(f"\n{message}")
    for i, option in enumerate(options):
        marker = ">" if i == default else " "
        print(f"  {marker} {i + 1}. {option}")
    print()

    while True:
        default_str = f" [{default + 1}]" if default is not None else ""
        response = input(f"Select an option{default_str}: ").strip()

        if not response and default is not None:
            return default

        try:
            choice = int(response) - 1
            if 0 <= choice < len(options):
                return choice
        except ValueError:
            pass
        print(f"Please enter a number between 1 and {len(options)}.")


def multi_select(
    message: str,
    options: List[str],
    defaults: Optional[List[int]] = None,
) -> List[int]:
    """Display a multi-selection menu. Return list of chosen indices."""
    selected = set(defaults or [])
    print(f"\n{message}")
    print("  (Use numbers to toggle, 'a' for all, 'n' for none, Enter to confirm)\n")

    while True:
        for i, option in enumerate(options):
            check = "[x]" if i in selected else "[ ]"
            print(f"  {check} {i + 1}. {option}")
        print()

        response = input("Toggle (or Enter to confirm): ").strip().lower()
        if not response:
            return sorted(selected)
        if response == "a":
            selected = set(range(len(options)))
        elif response == "n":
            selected = set()
        else:
            try:
                idx = int(response) - 1
                if 0 <= idx < len(options):
                    if idx in selected:
                        selected.discard(idx)
                    else:
                        selected.add(idx)
                else:
                    print(f"Invalid option: {response}")
            except ValueError:
                print(f"Invalid input: {response}")


def setup_wizard() -> Dict[str, Any]:
    """Run an interactive setup wizard for project initialization."""
    print("\n--- Project Setup Wizard ---\n")

    name = prompt("Project name", default="my-project",
                  validator=lambda s: s.replace("-", "").replace("_", "").isalnum(),
                  error_message="Name must be alphanumeric (hyphens and underscores allowed).")

    version = prompt("Initial version", default="0.1.0")

    description = prompt("Short description", default="")

    project_type = select(
        "Select project type:",
        ["Library", "CLI Application", "Web Service", "Script Collection"],
        default=0,
    )
    type_names = ["library", "cli", "web", "scripts"]

    features_idx = multi_select(
        "Select features to enable:",
        ["Linting (ruff)", "Type checking (mypy)", "Testing (pytest)",
         "Docker support", "CI/CD (GitHub Actions)"],
        defaults=[0, 1, 2],
    )
    feature_keys = ["linting", "type_checking", "testing", "docker", "ci"]
    features = [feature_keys[i] for i in features_idx]

    license_choice = select(
        "Select a license:",
        ["MIT", "Apache 2.0", "GPL 3.0", "BSD 3-Clause", "No license"],
        default=0,
    )
    license_names = ["MIT", "Apache-2.0", "GPL-3.0", "BSD-3-Clause", "UNLICENSED"]

    config = {
        "name": name,
        "version": version,
        "description": description,
        "type": type_names[project_type],
        "features": features,
        "license": license_names[license_choice],
    }

    print("\n--- Configuration Summary ---")
    for key, value in config.items():
        print(f"  {key}: {value}")
    print()

    if confirm("Proceed with this configuration?", default=True):
        return config
    else:
        print("Setup cancelled.")
        sys.exit(1)
'''),
]
