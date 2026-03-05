"""Python — multiprocessing, subprocess, and system administration patterns."""

PAIRS = [
    (
        "python/multiprocessing",
        "Show Python multiprocessing patterns: process pools, shared memory, and inter-process communication.",
        '''Python multiprocessing patterns:

```python
from multiprocessing import Pool, Process, Queue, Value, Array, Manager
from multiprocessing import shared_memory
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import numpy as np


# --- ProcessPoolExecutor (preferred API) ---

def cpu_intensive(data: list[int]) -> int:
    """CPU-bound work: sum of squares."""
    return sum(x * x for x in data)


def parallel_processing():
    """Process large dataset in parallel."""
    # Split data into chunks
    data = list(range(10_000_000))
    chunk_size = len(data) // os.cpu_count()
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        # Submit all tasks
        futures = {
            executor.submit(cpu_intensive, chunk): i
            for i, chunk in enumerate(chunks)
        }

        # Collect results as they complete
        total = 0
        for future in as_completed(futures):
            chunk_id = futures[future]
            result = future.result()
            total += result
            print(f"Chunk {chunk_id}: {result}")

    print(f"Total: {total}")


# --- Pool with map (simpler API) ---

def process_image(path: str) -> dict:
    """Process a single image (CPU-bound)."""
    # ... image processing ...
    return {"path": path, "size": os.path.getsize(path)}


def batch_process_images(image_paths: list[str]) -> list[dict]:
    with Pool(processes=os.cpu_count()) as pool:
        # map() preserves order
        results = pool.map(process_image, image_paths)

        # imap_unordered() for streaming results (better memory)
        for result in pool.imap_unordered(process_image, image_paths, chunksize=10):
            print(result)

    return results


# --- Shared memory (zero-copy between processes) ---

def shared_numpy_array():
    """Share numpy array between processes without copying."""
    # Create shared memory
    arr = np.random.rand(1000, 1000)
    shm = shared_memory.SharedMemory(create=True, size=arr.nbytes)

    # Create numpy array backed by shared memory
    shared_arr = np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)
    shared_arr[:] = arr[:]  # Copy data into shared memory

    # In child process:
    # existing_shm = shared_memory.SharedMemory(name=shm.name)
    # shared_arr = np.ndarray((1000, 1000), dtype=np.float64, buffer=existing_shm.buf)
    # ... read/write shared_arr ...
    # existing_shm.close()

    # Cleanup
    shm.close()
    shm.unlink()  # Delete shared memory block


# --- Queue for producer-consumer ---

def producer(queue: Queue, items: list):
    for item in items:
        queue.put(item)
    queue.put(None)  # Sentinel


def consumer(queue: Queue, results: list):
    while True:
        item = queue.get()
        if item is None:
            break
        results.append(process(item))


def producer_consumer_pattern():
    queue = Queue(maxsize=100)
    manager = Manager()
    results = manager.list()

    p = Process(target=producer, args=(queue, data))
    c = Process(target=consumer, args=(queue, results))

    p.start()
    c.start()
    p.join()
    c.join()

    print(f"Processed {len(results)} items")
```

Multiprocessing patterns:
1. **`ProcessPoolExecutor`** — cleanest API for CPU-bound parallelism
2. **`imap_unordered`** — stream results without holding all in memory
3. **`shared_memory`** — zero-copy shared arrays between processes
4. **`chunksize`** — batch small tasks to reduce IPC overhead
5. **`os.cpu_count()`** — match worker count to available cores'''
    ),
    (
        "python/subprocess-patterns",
        "Show Python subprocess patterns: safe command execution, piping, timeouts, and output capture.",
        '''Python subprocess patterns:

```python
import subprocess
import shlex
import os
import sys
import logging
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class CommandResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str
    success: bool


# --- Safe command execution ---

def run_command(
    cmd: list[str],
    cwd: str | Path | None = None,
    timeout: float = 30.0,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> CommandResult:
    """Run command safely with timeout and output capture."""
    try:
        # Merge environment
        run_env = {**os.environ, **(env or {})}

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=run_env,
            input=input_text,
            # NEVER use shell=True with user input
        )

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            success=result.returncode == 0,
        )

    except subprocess.TimeoutExpired:
        logger.error("Command timed out after %.0fs: %s", timeout, cmd)
        return CommandResult(-1, "", f"Timeout after {timeout}s", False)

    except FileNotFoundError:
        return CommandResult(-1, "", f"Command not found: {cmd[0]}", False)


# Usage:
# result = run_command(["git", "status", "--porcelain"])
# if result.success:
#     print(result.stdout)

# NEVER do this with user input:
# subprocess.run(f"ls {user_input}", shell=True)  # Command injection!

# SAFE alternative:
# subprocess.run(["ls", user_input])  # Arguments are properly escaped


# --- Piping commands ---

def pipe_commands(cmd1: list[str], cmd2: list[str]) -> CommandResult:
    """Pipe output of cmd1 into cmd2 (like cmd1 | cmd2)."""
    p1 = subprocess.Popen(
        cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    p2 = subprocess.Popen(
        cmd2, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    p1.stdout.close()  # Allow p1 to receive SIGPIPE if p2 exits

    stdout, stderr = p2.communicate()
    p1.wait()

    return CommandResult(
        p2.returncode,
        stdout.decode().strip(),
        stderr.decode().strip(),
        p2.returncode == 0,
    )

# result = pipe_commands(["cat", "access.log"], ["grep", "ERROR"])


# --- Streaming output ---

def stream_command(cmd: list[str], callback=None):
    """Stream command output line by line."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
    )

    for line in process.stdout:
        line = line.rstrip()
        if callback:
            callback(line)
        else:
            print(line)

    process.wait()
    return process.returncode


# --- Git helpers ---

def git_current_branch() -> str:
    result = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout if result.success else ""


def git_changed_files() -> list[str]:
    result = run_command(["git", "diff", "--name-only", "HEAD"])
    return result.stdout.splitlines() if result.success else []


def git_commit_count(since: str = "HEAD~10") -> int:
    result = run_command(["git", "rev-list", "--count", f"{since}..HEAD"])
    return int(result.stdout) if result.success else 0


# --- Process management ---

def run_background(cmd: list[str], log_file: str | None = None):
    """Start background process, return Popen handle."""
    stdout = open(log_file, "w") if log_file else subprocess.DEVNULL

    process = subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # Detach from parent
    )

    logger.info("Started PID %d: %s", process.pid, " ".join(cmd))
    return process
```

Subprocess patterns:
1. **Never `shell=True`** — use list args to prevent command injection
2. **`capture_output=True`** — capture stdout/stderr as strings
3. **`timeout`** — prevent hung commands from blocking forever
4. **`subprocess.PIPE` chaining** — pipe output between processes safely
5. **`bufsize=1`** — line-buffered output for real-time streaming'''
    ),
    (
        "python/file-processing",
        "Show Python file processing patterns: CSV, JSON lines, streaming large files, and parallel file I/O.",
        '''File processing patterns:

```python
import csv
import json
import gzip
from pathlib import Path
from typing import Iterator, Any
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)


# --- Stream large files line by line ---

def process_large_file(path: Path, batch_size: int = 1000) -> int:
    """Process large file without loading into memory."""
    processed = 0

    with open(path, "r", encoding="utf-8") as f:
        batch = []
        for line in f:
            batch.append(line.strip())
            if len(batch) >= batch_size:
                process_batch(batch)
                processed += len(batch)
                batch.clear()

        if batch:
            process_batch(batch)
            processed += len(batch)

    return processed


# --- JSON Lines (one JSON object per line) ---

def read_jsonl(path: Path) -> Iterator[dict]:
    """Stream JSONL file."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON at line %d: %s", line_num, e)


def write_jsonl(path: Path, items: Iterator[dict], compress: bool = False):
    """Write items as JSONL."""
    opener = gzip.open if compress else open
    with opener(path, "wt", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, default=str) + "\\n")


# --- CSV processing ---

def process_csv(path: Path) -> list[dict]:
    """Read CSV with type conversion."""
    results = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Type conversion
            row["amount"] = float(row.get("amount", 0))
            row["quantity"] = int(row.get("quantity", 0))
            results.append(row)
    return results


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None):
    """Write dicts to CSV."""
    if not rows:
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# --- Parallel file processing ---

def process_files_parallel(
    paths: list[Path],
    processor: callable,
    max_workers: int = 4,
) -> dict[str, Any]:
    """Process multiple files in parallel using threads."""
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(processor, path): path
            for path in paths
        }

        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                results[str(path)] = future.result()
            except Exception as e:
                logger.error("Failed to process %s: %s", path, e)
                results[str(path)] = {"error": str(e)}

    return results


# --- File watcher ---

def watch_directory(path: Path, pattern: str = "*",
                    callback: callable = None, poll_interval: float = 1.0):
    """Simple file watcher using polling."""
    import time
    seen: dict[Path, float] = {}

    while True:
        current = {}
        for f in path.glob(pattern):
            mtime = f.stat().st_mtime
            current[f] = mtime

            if f not in seen:
                logger.info("New file: %s", f)
                if callback:
                    callback("created", f)
            elif seen[f] != mtime:
                logger.info("Modified: %s", f)
                if callback:
                    callback("modified", f)

        for f in seen:
            if f not in current:
                logger.info("Deleted: %s", f)
                if callback:
                    callback("deleted", f)

        seen = current
        time.sleep(poll_interval)
```

File processing patterns:
1. **Batch streaming** — process large files in chunks without loading all into memory
2. **JSONL format** — one JSON object per line for streaming and `grep`-ability
3. **`gzip.open`** — transparent compressed file reading/writing
4. **`ThreadPoolExecutor`** — parallel file I/O (threads are fine for I/O-bound)
5. **`csv.DictReader`** — access CSV columns by name, auto-parse headers'''
    ),
    (
        "python/cli-argument-parsing",
        "Show Python CLI argument parsing patterns: argparse, subcommands, and environment variable fallbacks.",
        '''CLI argument parsing patterns:

```python
import argparse
import os
import sys
from pathlib import Path
from typing import Any


def create_parser() -> argparse.ArgumentParser:
    """Build CLI parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="myapp",
        description="My Application CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  myapp serve --port 8080
  myapp migrate --database postgresql://localhost/mydb
  myapp export --format csv --output data.csv
        """,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="count", default=0,
        help="Increase verbosity (-v, -vv, -vvv)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config file (default: config.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- serve command ---
    serve = subparsers.add_parser("serve", help="Start the server")
    serve.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Bind address (env: HOST, default: 0.0.0.0)",
    )
    serve.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("PORT", "8080")),
        help="Port number (env: PORT, default: 8080)",
    )
    serve.add_argument(
        "--workers", "-w",
        type=int,
        default=os.cpu_count(),
        help="Number of workers (default: CPU count)",
    )
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    # --- migrate command ---
    migrate = subparsers.add_parser("migrate", help="Run database migrations")
    migrate.add_argument(
        "--database",
        required=True,
        help="Database URL",
    )
    migrate.add_argument(
        "--revision",
        default="head",
        help="Target revision (default: head)",
    )
    migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Show SQL without executing",
    )

    # --- export command ---
    export = subparsers.add_parser("export", help="Export data")
    export.add_argument(
        "--format", "-f",
        choices=["csv", "json", "parquet"],
        default="csv",
        help="Output format",
    )
    export.add_argument(
        "--output", "-o",
        type=Path,
        required=True,
        help="Output file path",
    )
    export.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Filter expression (can repeat: --filter 'status=active')",
    )
    export.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to export",
    )

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Set log level based on verbosity
    import logging
    log_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = log_levels[min(args.verbose, len(log_levels) - 1)]
    logging.basicConfig(level=level)

    # Dispatch to command handler
    handlers = {
        "serve": handle_serve,
        "migrate": handle_migrate,
        "export": handle_export,
    }

    handler = handlers.get(args.command)
    if handler:
        try:
            handler(args)
        except KeyboardInterrupt:
            print("\\nInterrupted")
            sys.exit(130)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def handle_serve(args):
    print(f"Starting server on {args.host}:{args.port} "
          f"with {args.workers} workers")
    if args.reload:
        print("Auto-reload enabled")


def handle_migrate(args):
    print(f"Migrating {args.database} to {args.revision}")
    if args.dry_run:
        print("(dry run — no changes)")


def handle_export(args):
    print(f"Exporting to {args.output} as {args.format}")
    for f in args.filter:
        print(f"  Filter: {f}")


if __name__ == "__main__":
    main()
```

CLI argument parsing patterns:
1. **Subcommands** — `serve`, `migrate`, `export` with separate arguments
2. **Env var fallback** — `default=os.environ.get("PORT", "8080")`
3. **`action="count"`** — `-vvv` gives verbosity level 3
4. **`action="append"`** — repeat `--filter` for multiple values
5. **`choices`** — restrict `--format` to valid options with auto error messages'''
    ),
]
"""
