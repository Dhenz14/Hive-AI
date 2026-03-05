"""Debugging and profiling — Python debugging, memory profiling, performance analysis, production debugging."""

PAIRS = [
    (
        "debugging/python-profiling",
        "Show Python profiling techniques: CPU profiling, memory profiling, line-level profiling, and flame graphs for performance analysis.",
        '''Python profiling techniques for performance optimization:

```python
import cProfile
import pstats
import io
import time
import tracemalloc
from functools import wraps
from contextlib import contextmanager

# --- CPU Profiling with cProfile ---

def profile_function(func, *args, **kwargs):
    """Profile a function and print stats."""
    profiler = cProfile.Profile()
    profiler.enable()
    result = func(*args, **kwargs)
    profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(20)
    print(stream.getvalue())
    return result

# Decorator version
def cpu_profile(sort_by="cumulative", lines=20):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            profiler = cProfile.Profile()
            profiler.enable()
            result = func(*args, **kwargs)
            profiler.disable()

            stats = pstats.Stats(profiler)
            stats.sort_stats(sort_by)
            stats.print_stats(lines)
            return result
        return wrapper
    return decorator

# --- Memory Profiling with tracemalloc ---

@contextmanager
def memory_profile(top_n: int = 10):
    """Track memory allocations within a block."""
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()
    yield
    snapshot2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot2.compare_to(snapshot1, "lineno")
    print(f"\\nTop {top_n} memory changes:")
    for stat in stats[:top_n]:
        print(f"  {stat}")

# Usage:
# with memory_profile():
#     data = process_large_dataset()

def find_memory_leaks():
    """Detect objects that keep growing."""
    tracemalloc.start()

    # Take periodic snapshots
    snapshots = []
    for i in range(5):
        do_work_iteration(i)
        snapshots.append(tracemalloc.take_snapshot())
        time.sleep(1)

    # Compare first and last
    stats = snapshots[-1].compare_to(snapshots[0], "lineno")
    print("\\nGrowing allocations (potential leaks):")
    for stat in stats[:10]:
        if stat.size_diff > 0:
            print(f"  +{stat.size_diff / 1024:.1f} KB: {stat}")

# --- Line-level profiling ---

# Install: pip install line_profiler
# Usage with @profile decorator:
LINE_PROFILER_EXAMPLE = """
# my_module.py
@profile  # Added by line_profiler
def slow_function(data):
    result = []                      # Line 1
    for item in data:                # Line 2
        processed = transform(item)  # Line 3 — most time here?
        if validate(processed):      # Line 4
            result.append(processed) # Line 5
    return result

# Run: kernprof -l -v my_module.py
# Output shows time per line:
# Line #  Hits   Time   Per Hit  % Time  Line Contents
#   1      1      1.0     1.0     0.0    result = []
#   2   1000   100.0     0.1     0.5    for item in data:
#   3    999  15000.0    15.0    74.6    processed = transform(item)
#   4    999   4500.0     4.5    22.4    if validate(processed):
#   5    500    500.0     1.0     2.5    result.append(processed)
"""

# --- Timing utilities ---

@contextmanager
def timer(label: str = ""):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"{label}: {elapsed*1000:.2f}ms")

class PerformanceTracker:
    """Track performance of code sections over time."""

    def __init__(self):
        self.timings: dict[str, list[float]] = {}

    @contextmanager
    def track(self, name: str):
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self.timings.setdefault(name, []).append(elapsed)

    def report(self) -> dict:
        import statistics
        report = {}
        for name, times in self.timings.items():
            report[name] = {
                "count": len(times),
                "total_ms": sum(times) * 1000,
                "mean_ms": statistics.mean(times) * 1000,
                "median_ms": statistics.median(times) * 1000,
                "p95_ms": sorted(times)[int(len(times) * 0.95)] * 1000 if len(times) > 20 else None,
                "max_ms": max(times) * 1000,
            }
        return report

# --- Flame graph generation ---

FLAME_GRAPH_COMMANDS = """
# Generate flame graph with py-spy (no code changes needed!)
# Install: pip install py-spy

# Profile running process
py-spy record -o flame.svg --pid 12345

# Profile a script
py-spy record -o flame.svg -- python my_script.py

# Top-like view of running process
py-spy top --pid 12345

# Profile with native (C) frames
py-spy record -o flame.svg --native -- python my_script.py

# Generate speedscope format (interactive viewer)
py-spy record -o profile.speedscope.json --format speedscope -- python my_script.py
# Open at https://www.speedscope.app/
"""

# --- Async profiling ---

async def profile_async_function(coro):
    """Profile async function execution."""
    import yappi

    yappi.set_clock_type("wall")  # Wall time for async
    yappi.start()
    result = await coro
    yappi.stop()

    # Print stats
    func_stats = yappi.get_func_stats()
    func_stats.sort("totaltime", "desc")
    func_stats.print_all(columns={
        0: ("name", 50), 1: ("ncall", 10),
        2: ("ttot", 10), 3: ("tavg", 10),
    })

    yappi.clear_stats()
    return result
```

Profiling decision tree:
1. **"What's slow?"** → cProfile (function-level CPU time)
2. **"Which line is slow?"** → line_profiler (line-level timing)
3. **"Memory growing?"** → tracemalloc (allocation tracking)
4. **"Visual overview?"** → py-spy flame graph (zero overhead)
5. **"Async bottleneck?"** → yappi with wall clock
6. **"Production profiling?"** → py-spy (attach to running process)'''
    ),
    (
        "debugging/production-debugging",
        "Show production debugging techniques: structured logging analysis, distributed tracing, core dump analysis, and live debugging strategies.",
        '''Production debugging without downtime:

```python
import sys
import signal
import traceback
import threading
import faulthandler
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# --- 1. Enable faulthandler for crash diagnostics ---

faulthandler.enable()  # Print traceback on segfault
faulthandler.register(signal.SIGUSR1)  # Dump traces on SIGUSR1
# kill -USR1 <pid> → prints all thread tracebacks

# --- 2. Thread dump on signal ---

def dump_threads(signum, frame):
    """Print all thread stack traces on SIGUSR2."""
    output = []
    output.append(f"\\n=== Thread Dump at {datetime.now(timezone.utc).isoformat()} ===")

    for thread_id, stack in sys._current_frames().items():
        thread = threading.main_thread()
        for t in threading.enumerate():
            if t.ident == thread_id:
                thread = t
                break
        output.append(f"\\nThread: {thread.name} (id={thread_id}, daemon={thread.daemon})")
        for filename, lineno, name, line in traceback.extract_stack(stack):
            output.append(f"  File: {filename}:{lineno} in {name}")
            if line:
                output.append(f"    {line.strip()}")

    dump = "\\n".join(output)
    log.warning(dump)
    print(dump, file=sys.stderr)

signal.signal(signal.SIGUSR2, dump_threads)

# --- 3. Runtime diagnostics endpoint ---

from fastapi import FastAPI
import psutil
import gc

app = FastAPI()

@app.get("/debug/health")
async def debug_health():
    process = psutil.Process()
    return {
        "pid": process.pid,
        "uptime_seconds": time.time() - process.create_time(),
        "cpu_percent": process.cpu_percent(interval=0.1),
        "memory_mb": process.memory_info().rss / 1024 / 1024,
        "threads": process.num_threads(),
        "open_files": len(process.open_files()),
        "connections": len(process.connections()),
    }

@app.get("/debug/threads")
async def debug_threads():
    threads = []
    for t in threading.enumerate():
        threads.append({
            "name": t.name,
            "daemon": t.daemon,
            "alive": t.is_alive(),
            "ident": t.ident,
        })
    return {"count": len(threads), "threads": threads}

@app.get("/debug/gc")
async def debug_gc():
    gc.collect()
    return {
        "garbage": len(gc.garbage),
        "counts": gc.get_count(),
        "thresholds": gc.get_threshold(),
        "tracked_objects": len(gc.get_objects()),
    }

@app.get("/debug/memory")
async def debug_memory_top():
    """Top memory consumers (requires tracemalloc enabled)."""
    import tracemalloc
    if not tracemalloc.is_tracing():
        tracemalloc.start()
        return {"status": "tracing started, call again for results"}

    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.statistics("lineno")
    return {
        "total_mb": sum(s.size for s in stats) / 1024 / 1024,
        "top_allocations": [
            {"file": str(s.traceback), "size_kb": s.size / 1024}
            for s in stats[:20]
        ],
    }

# --- 4. Structured log analysis queries ---

LOG_QUERIES = """
# Find slow requests (>2s)
cat app.log | jq 'select(.duration_ms > 2000)' | jq '{path, duration_ms, request_id}'

# Error rate per endpoint (last hour)
cat app.log | jq 'select(.level == "error")' | jq -r '.path' | sort | uniq -c | sort -rn

# Trace a request across services
cat app.log | jq 'select(.request_id == "abc-123")'

# Find memory growth pattern
cat app.log | jq 'select(.event == "gc_stats")' | jq '{timestamp, rss_mb: .memory_mb}'

# Correlate errors with deployments
cat app.log | jq 'select(.level == "error" and .timestamp > "2024-03-15T10:00:00")'
"""

# --- 5. Dynamic log level adjustment ---

import logging

@app.post("/debug/log-level")
async def set_log_level(logger_name: str = "root", level: str = "DEBUG"):
    """Temporarily increase log verbosity for debugging."""
    logger = logging.getLogger(logger_name if logger_name != "root" else None)
    old_level = logger.level
    logger.setLevel(getattr(logging, level.upper()))
    log.warning(f"Log level changed: {logging.getLevelName(old_level)} → {level}")
    return {"logger": logger_name, "old_level": logging.getLevelName(old_level), "new_level": level}

# --- 6. Request replay for reproduction ---

class RequestRecorder:
    """Record requests for debugging/replay."""

    def __init__(self, redis_client, max_records: int = 1000):
        self.redis = redis_client
        self.max_records = max_records

    async def record(self, request_id: str, method: str, path: str,
                     headers: dict, body: bytes):
        record = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "headers": {k: v for k, v in headers.items()
                        if k.lower() not in ("authorization", "cookie")},
            "body": body.decode("utf-8", errors="replace")[:10000],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis.lpush("debug:requests", json.dumps(record))
        await self.redis.ltrim("debug:requests", 0, self.max_records)

    async def get_recent(self, count: int = 50) -> list[dict]:
        records = await self.redis.lrange("debug:requests", 0, count)
        return [json.loads(r) for r in records]
```

Production debugging checklist:
1. **Check logs** — structured logs with request_id correlation
2. **Check metrics** — Grafana dashboards for anomaly detection
3. **Check traces** — distributed traces for latency breakdown
4. **Thread dump** — `kill -USR2 <pid>` for deadlock detection
5. **Memory profile** — tracemalloc endpoint for leak detection
6. **Log level boost** — temporarily increase verbosity
7. **Request replay** — reproduce with recorded requests'''
    ),
    (
        "debugging/python-debugging-tools",
        "Show Python debugging techniques beyond print: pdb, breakpoint(), conditional breakpoints, post-mortem debugging, and remote debugging.",
        '''Python debugging tools and techniques:

```python
# --- 1. Built-in breakpoint() (Python 3.7+) ---

def process_data(items):
    results = []
    for item in items:
        transformed = transform(item)
        if transformed is None:
            breakpoint()  # Drops into pdb here
            # pdb commands:
            # n (next), s (step into), c (continue), p expr (print)
            # l (list code), w (where/stack trace), q (quit)
            # pp var (pretty print), h (help)
        results.append(transformed)
    return results

# --- 2. Conditional breakpoints ---

import pdb

def find_bug(data):
    for i, item in enumerate(data):
        result = calculate(item)
        # Only break when a specific condition is met
        if result < 0 and item["type"] == "special":
            pdb.set_trace()
        # Or use conditional in pdb:
        # b 15, result < 0  (break at line 15 when result < 0)

# --- 3. Post-mortem debugging ---

def risky_function():
    try:
        result = might_fail()
    except Exception:
        import pdb; pdb.post_mortem()
        # Drops into debugger at the point of exception
        # Can inspect all local variables at crash point

# Auto post-mortem for scripts:
# python -m pdb script.py
# When it crashes, you're in the debugger at the crash point

# --- 4. Better debuggers ---

# ipdb — IPython-enhanced pdb
# pip install ipdb
# import ipdb; ipdb.set_trace()
# Features: tab completion, syntax highlighting, better introspection

# pudb — visual TUI debugger
# pip install pudb
# import pudb; pudb.set_trace()
# Features: source code view, variable inspector, stack browser

# --- 5. Debugging decorators ---

from functools import wraps
import traceback

def debug_on_error(func):
    """Drop into debugger on exception."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Exception in {func.__name__}: {e}")
            traceback.print_exc()
            import pdb; pdb.post_mortem()
    return wrapper

def trace_calls(func):
    """Log function entry/exit with arguments and return value."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        args_repr = [repr(a)[:50] for a in args]
        kwargs_repr = [f"{k}={v!r:.50}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        print(f"→ {func.__name__}({signature})")
        try:
            result = func(*args, **kwargs)
            print(f"← {func.__name__} returned {result!r:.100}")
            return result
        except Exception as e:
            print(f"✗ {func.__name__} raised {e!r}")
            raise
    return wrapper

def watch_variable(name: str, obj: object):
    """Monitor attribute changes on an object."""
    original_setattr = type(obj).__setattr__

    def watched_setattr(self, attr, value):
        if attr == name:
            old = getattr(self, attr, "<unset>")
            frame = traceback.extract_stack()[-2]
            print(f"  {attr} changed: {old!r} → {value!r}")
            print(f"  at {frame.filename}:{frame.lineno} in {frame.name}")
        original_setattr(self, attr, value)

    type(obj).__setattr__ = watched_setattr

# --- 6. sys.settrace for execution tracing ---

def simple_tracer(frame, event, arg):
    """Trace function calls and returns."""
    if event == "call":
        filename = frame.f_code.co_filename
        if "site-packages" not in filename:
            print(f"  Call: {frame.f_code.co_name} at {filename}:{frame.f_lineno}")
    elif event == "return":
        if "site-packages" not in frame.f_code.co_filename:
            print(f"  Return: {frame.f_code.co_name} → {arg!r:.50}")
    return simple_tracer

# Enable: sys.settrace(simple_tracer)
# Disable: sys.settrace(None)

# --- 7. Debugging async code ---

import asyncio

async def debug_async():
    # Enable asyncio debug mode
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    # Shows: slow callbacks (>100ms), unawaited coroutines, resource warnings

    # Or via environment variable:
    # PYTHONASYNCIODEBUG=1 python script.py

# --- 8. Object inspection ---

def inspect_object(obj, depth: int = 1):
    """Deep inspect any object."""
    print(f"Type: {type(obj).__name__}")
    print(f"ID: {id(obj)}")
    print(f"Size: {sys.getsizeof(obj)} bytes")
    print(f"Dir: {[a for a in dir(obj) if not a.startswith('_')]}")

    if hasattr(obj, "__dict__"):
        print(f"Attrs: {obj.__dict__}")
    if hasattr(obj, "__slots__"):
        print(f"Slots: {obj.__slots__}")

    # MRO for classes
    if isinstance(obj, type):
        print(f"MRO: {[c.__name__ for c in obj.__mro__]}")
```

Debugging strategy:
1. **Read the error** — full traceback, not just last line
2. **Reproduce** — minimal test case that triggers the bug
3. **Isolate** — binary search with breakpoints/print
4. **Understand** — don't just fix symptoms, find root cause
5. **Verify** — write a test that fails without the fix'''
    ),
    (
        "debugging/memory-leak-detection",
        "Show how to detect and fix memory leaks in Python: reference cycles, weak references, __del__ issues, and C extension leaks.",
        '''Detecting and fixing Python memory leaks:

```python
import gc
import sys
import weakref
import tracemalloc
import objgraph  # pip install objgraph
from typing import Any

# --- Common leak pattern 1: Reference cycles ---

class Node:
    """Circular reference — GC handles it, but with __del__ it leaks."""
    def __init__(self, name):
        self.name = name
        self.parent = None
        self.children = []

    def add_child(self, child):
        child.parent = self  # Creates cycle: parent → child → parent
        self.children.append(child)

    # BAD: __del__ with circular reference prevents GC collection
    # def __del__(self):
    #     print(f"Deleting {self.name}")

# Fix: use weakref for back-references
class SafeNode:
    def __init__(self, name):
        self.name = name
        self._parent_ref = None
        self.children = []

    @property
    def parent(self):
        return self._parent_ref() if self._parent_ref else None

    def add_child(self, child):
        child._parent_ref = weakref.ref(self)  # Weak reference breaks cycle
        self.children.append(child)

# --- Common leak pattern 2: Closures capturing large objects ---

def create_processors(large_dataset):
    processors = []
    for i in range(100):
        # BAD: each lambda captures entire large_dataset
        # processors.append(lambda: process(large_dataset[i]))

        # GOOD: capture only what's needed
        item = large_dataset[i]  # Extract needed data
        processors.append(lambda item=item: process(item))
    return processors

# --- Common leak pattern 3: Event handlers not cleaned up ---

class EventSystem:
    def __init__(self):
        self._handlers = {}

    def on(self, event: str, handler):
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler):
        if event in self._handlers:
            self._handlers[event] = [
                h for h in self._handlers[event] if h != handler
            ]

# BAD: bound methods keep object alive
class Widget:
    def __init__(self, events: EventSystem):
        self.events = events
        events.on("click", self.handle_click)  # Prevents GC of Widget

    def handle_click(self):
        pass

    def destroy(self):
        self.events.off("click", self.handle_click)  # Must manually clean up

# GOOD: weak method references
class SafeWidget:
    def __init__(self, events: EventSystem):
        self.events = events
        ref = weakref.WeakMethod(self.handle_click)
        events.on("click", lambda: ref()() if ref() else None)

# --- Detection tools ---

def detect_leaks_gc():
    """Use gc module to find uncollectable objects."""
    gc.set_debug(gc.DEBUG_SAVEALL)
    gc.collect()

    print(f"Garbage objects: {len(gc.garbage)}")
    for obj in gc.garbage[:10]:
        print(f"  Type: {type(obj).__name__}, Repr: {repr(obj)[:100]}")

def detect_leaks_objgraph():
    """Use objgraph to visualize reference chains."""
    gc.collect()

    # Most common types (growing types = potential leaks)
    objgraph.show_most_common_types(limit=10)

    # Growth between calls (call twice with work in between)
    objgraph.show_growth(limit=10)

    # Find what's keeping an object alive
    # objgraph.show_backrefs(obj, max_depth=5, filename="refs.png")

def monitor_memory_growth(interval: float = 5.0, iterations: int = 10):
    """Monitor memory over time to detect leaks."""
    import psutil
    process = psutil.Process()

    baseline = process.memory_info().rss / 1024 / 1024
    print(f"Baseline: {baseline:.1f} MB")

    growth_history = []
    for i in range(iterations):
        # Run your workload here
        do_work()
        gc.collect()

        current = process.memory_info().rss / 1024 / 1024
        growth = current - baseline
        growth_history.append(growth)
        print(f"  Iteration {i}: {current:.1f} MB (+{growth:.1f} MB)")

    # Check if memory is consistently growing
    if len(growth_history) > 3:
        recent_growth = growth_history[-1] - growth_history[-3]
        if recent_growth > 1:  # More than 1MB growth
            print(f"WARNING: Memory growing by ~{recent_growth:.1f} MB")

# --- tracemalloc for allocation tracking ---

def find_leak_source():
    """Compare memory snapshots to find leak source."""
    tracemalloc.start(25)  # Store 25 frames for traceback

    snapshot1 = tracemalloc.take_snapshot()

    # Run workload
    for _ in range(100):
        do_work()

    snapshot2 = tracemalloc.take_snapshot()

    # Compare
    stats = snapshot2.compare_to(snapshot1, "traceback")
    print("\\nTop memory growth by traceback:")
    for stat in stats[:5]:
        print(f"\\n  +{stat.size_diff / 1024:.1f} KB ({stat.count_diff} allocations)")
        for line in stat.traceback.format():
            print(f"    {line}")
```

Memory leak checklist:
1. **Monitor RSS over time** — should plateau, not grow
2. **gc.collect() + gc.garbage** — find uncollectable cycles
3. **objgraph.show_growth()** — types with growing instance counts
4. **tracemalloc snapshots** — find which code allocates growing memory
5. **weakref** — break reference cycles, especially in callbacks/caches
6. **Context managers** — ensure resources are released (files, connections)'''
    ),
]
