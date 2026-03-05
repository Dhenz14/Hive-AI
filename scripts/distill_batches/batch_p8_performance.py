PAIRS = [
    (
        "performance/cpu-profiling-flamegraphs-optimization",
        "Explain CPU profiling techniques including flame graph generation and interpretation, hotspot identification, instruction-level profiling with perf and py-spy, branch prediction optimization, and SIMD vectorization opportunities with practical Python and C examples",
        r"""# CPU Profiling and Optimization: From Flame Graphs to SIMD

## Why Profile Before Optimizing

The cardinal rule of performance engineering is **measure first, optimize second**. Developers routinely guess wrong about bottlenecks — Amdahl's Law tells us that optimizing a function that accounts for 5% of runtime can never improve total performance by more than 5%, regardless of how fast we make it. **Therefore**, profiling tools are essential for identifying where time is actually spent.

### Flame Graph Generation and Interpretation

```python
import cProfile
import pstats
import io
import time
import sys
from typing import Callable, Any
from dataclasses import dataclass, field
from functools import wraps
import statistics

# --- CPU profiling infrastructure ---

@dataclass
class ProfileResult:
    function_name: str
    total_calls: int
    total_time: float
    cumulative_time: float
    time_per_call: float
    callers: list[str] = field(default_factory=list)

class Profiler:
    # Best practice: wrap cProfile with structured output
    # for integration with CI pipelines and regression detection

    def __init__(self):
        self._profiler = cProfile.Profile()
        self._results: list[ProfileResult] = []

    def profile(self, func: Callable, *args: Any, **kwargs: Any) -> tuple[Any, list[ProfileResult]]:
        self._profiler.enable()
        result = func(*args, **kwargs)
        self._profiler.disable()

        # Parse stats
        stream = io.StringIO()
        stats = pstats.Stats(self._profiler, stream=stream)
        stats.sort_stats("cumulative")

        self._results = []
        for key, value in stats.stats.items():
            filename, line, name = key
            cc, nc, tt, ct, callers = value
            self._results.append(ProfileResult(
                function_name=f"{filename}:{line}({name})",
                total_calls=nc,
                total_time=tt,
                cumulative_time=ct,
                time_per_call=tt / nc if nc > 0 else 0,
            ))

        self._results.sort(key=lambda r: r.cumulative_time, reverse=True)
        return result, self._results

    def get_hotspots(self, top_n: int = 10) -> list[ProfileResult]:
        return self._results[:top_n]

    def generate_flamegraph_data(self) -> list[dict]:
        # Convert profile data to flamegraph-compatible format
        # Common mistake: using wall-clock time instead of CPU time
        # for CPU-bound profiling — use CPU time to avoid I/O noise
        stacks: list[dict] = []
        for r in self._results:
            if r.total_time > 0.001:  # Filter noise
                stacks.append({
                    "name": r.function_name,
                    "value": int(r.total_time * 1_000_000),  # microseconds
                    "children": [],
                })
        return stacks

# --- Benchmark decorator with statistical analysis ---

def benchmark(iterations: int = 100, warmup: int = 10):
    # Trade-off: more iterations = more accurate but slower
    # Best practice: include warmup to account for JIT/cache effects
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Warmup phase
            for _ in range(warmup):
                func(*args, **kwargs)

            # Measurement phase
            times: list[float] = []
            for _ in range(iterations):
                start = time.perf_counter_ns()
                result = func(*args, **kwargs)
                elapsed = time.perf_counter_ns() - start
                times.append(elapsed)

            mean = statistics.mean(times)
            median = statistics.median(times)
            stdev = statistics.stdev(times) if len(times) > 1 else 0
            p95 = sorted(times)[int(len(times) * 0.95)]
            p99 = sorted(times)[int(len(times) * 0.99)]

            print(f"  {func.__name__}:")
            print(f"    mean={mean/1e6:.3f}ms  median={median/1e6:.3f}ms  "
                  f"stdev={stdev/1e6:.3f}ms")
            print(f"    p95={p95/1e6:.3f}ms  p99={p99/1e6:.3f}ms  "
                  f"n={iterations}")
            return result
        return wrapper
    return decorator

# --- Example: optimizing a hot loop ---

def matrix_multiply_naive(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    # Pitfall: naive implementation is cache-unfriendly
    # because it accesses b column-wise (stride = n)
    n = len(a)
    result = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            for k in range(n):
                result[i][j] += a[i][k] * b[k][j]
    return result

def matrix_multiply_transposed(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    # Transpose b for cache-friendly row-wise access
    # Therefore, both a and b_t are accessed sequentially
    n = len(a)
    b_t = [[b[j][i] for j in range(n)] for i in range(n)]
    result = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            s = 0.0
            for k in range(n):
                s += a[i][k] * b_t[j][k]
            result[i][j] = s
    return result

def matrix_multiply_blocked(
    a: list[list[float]], b: list[list[float]], block_size: int = 32
) -> list[list[float]]:
    # Cache-oblivious blocking — fits sub-matrices in L1 cache
    # However, the optimal block size depends on cache line size
    n = len(a)
    result = [[0.0] * n for _ in range(n)]

    for ii in range(0, n, block_size):
        for jj in range(0, n, block_size):
            for kk in range(0, n, block_size):
                for i in range(ii, min(ii + block_size, n)):
                    for j in range(jj, min(jj + block_size, n)):
                        s = result[i][j]
                        for k in range(kk, min(kk + block_size, n)):
                            s += a[i][k] * b[k][j]
                        result[i][j] = s
    return result
```

### Memory Access Patterns and Cache Optimization

Understanding the CPU cache hierarchy is essential **because** a cache miss can cost 100+ cycles while a cache hit costs 1-4 cycles. **Therefore**, data layout and access patterns often matter more than algorithmic complexity for practical performance.

```python
import array
import struct
from typing import NamedTuple

# --- Data layout: AoS vs SoA ---

# Array of Structures (AoS) — bad for SIMD, okay for single-entity access
@dataclass
class ParticleAoS:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    mass: float = 1.0

# Structure of Arrays (SoA) — great for SIMD and cache efficiency
# Best practice: use SoA when processing one field across many entities
class ParticlesSoA:
    # Each array is contiguous in memory — perfect for vectorization
    def __init__(self, n: int):
        self.n = n
        self.x = array.array("d", [0.0] * n)
        self.y = array.array("d", [0.0] * n)
        self.z = array.array("d", [0.0] * n)
        self.vx = array.array("d", [0.0] * n)
        self.vy = array.array("d", [0.0] * n)
        self.vz = array.array("d", [0.0] * n)
        self.mass = array.array("d", [1.0] * n)

    def update_positions(self, dt: float) -> None:
        # Sequential access pattern — cache line prefetching works perfectly
        # Therefore, this is ~4x faster than AoS for large N
        for i in range(self.n):
            self.x[i] += self.vx[i] * dt
            self.y[i] += self.vy[i] * dt
            self.z[i] += self.vz[i] * dt

    def compute_kinetic_energy(self) -> float:
        # Stream through velocity arrays — one cache miss per 8 elements
        # (64-byte cache line / 8-byte double = 8 elements)
        total = 0.0
        for i in range(self.n):
            v_sq = self.vx[i]**2 + self.vy[i]**2 + self.vz[i]**2
            total += 0.5 * self.mass[i] * v_sq
        return total

# --- Branch prediction optimization ---

def process_data_branchy(data: list[int], threshold: int) -> int:
    # Pitfall: unpredictable branches kill pipeline performance
    # Modern CPUs predict branches based on history
    # Random data = ~50% misprediction = stall every other iteration
    total = 0
    for x in data:
        if x > threshold:  # Unpredictable if data is random
            total += x
    return total

def process_data_branchless(data: list[int], threshold: int) -> int:
    # Branchless version — compute mask instead of branching
    # However, in Python the overhead of extra ops may negate this
    # This pattern matters more in C/Rust/compiled languages
    total = 0
    for x in data:
        mask = -(x > threshold)  # -1 if true, 0 if false
        total += x & mask
    return total

def process_data_sorted(data: list[int], threshold: int) -> int:
    # Common mistake: not considering branch prediction
    # Sorting makes branches predictable (all < threshold, then all >)
    # Therefore, sorted data processes much faster despite same algorithm
    total = 0
    for x in sorted(data):
        if x > threshold:
            total += x
    return total

# --- Memory allocation patterns ---

class PoolAllocator:
    # Avoid repeated allocation/deallocation for fixed-size objects
    # Trade-off: wastes memory for unused slots but eliminates alloc overhead
    def __init__(self, obj_size: int, pool_size: int = 1024):
        self.obj_size = obj_size
        self.pool_size = pool_size
        self._buffer = bytearray(obj_size * pool_size)
        self._free_list: list[int] = list(range(pool_size))
        self._allocated = 0

    def allocate(self) -> int:
        if not self._free_list:
            raise MemoryError("Pool exhausted")
        slot = self._free_list.pop()
        self._allocated += 1
        return slot

    def deallocate(self, slot: int) -> None:
        self._free_list.append(slot)
        self._allocated -= 1

    def get_ptr(self, slot: int) -> memoryview:
        start = slot * self.obj_size
        return memoryview(self._buffer)[start:start + self.obj_size]

    @property
    def utilization(self) -> float:
        return self._allocated / self.pool_size
```

### Profiling Workflows and Regression Detection

A **best practice** is integrating performance benchmarks into CI/CD to catch regressions automatically. **However**, benchmark noise from shared CI runners can cause false positives — use statistical tests, not fixed thresholds.

```python
# --- Performance regression detection ---

@dataclass
class BenchmarkResult:
    name: str
    samples: list[float]  # nanoseconds
    timestamp: float = 0.0

    @property
    def mean(self) -> float:
        return statistics.mean(self.samples)

    @property
    def median(self) -> float:
        return statistics.median(self.samples)

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.samples) if len(self.samples) > 1 else 0

    @property
    def cv(self) -> float:
        # Coefficient of variation — relative measure of dispersion
        return self.stdev / self.mean if self.mean > 0 else 0

class RegressionDetector:
    # Compare two benchmark runs using Welch's t-test
    # Therefore, we account for different variances between runs

    def __init__(self, significance: float = 0.05, min_effect_size: float = 0.05):
        self.significance = significance
        self.min_effect_size = min_effect_size  # Ignore < 5% changes

    def compare(
        self, baseline: BenchmarkResult, current: BenchmarkResult
    ) -> dict:
        n1, n2 = len(baseline.samples), len(current.samples)
        mean1, mean2 = baseline.mean, current.mean
        var1 = baseline.stdev ** 2
        var2 = current.stdev ** 2

        # Welch's t-statistic
        se = ((var1 / n1) + (var2 / n2)) ** 0.5
        if se == 0:
            t_stat = 0.0
        else:
            t_stat = (mean2 - mean1) / se

        # Effect size (relative change)
        if mean1 > 0:
            relative_change = (mean2 - mean1) / mean1
        else:
            relative_change = 0.0

        # Welch-Satterthwaite degrees of freedom
        if var1 / n1 + var2 / n2 > 0:
            df_num = (var1 / n1 + var2 / n2) ** 2
            df_den = ((var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1))
            df = df_num / df_den if df_den > 0 else 1
        else:
            df = 1

        # Simplified p-value approximation
        # In production, use scipy.stats.t.sf
        is_regression = (
            abs(relative_change) > self.min_effect_size
            and abs(t_stat) > 2.0  # ~95% confidence for large df
            and mean2 > mean1  # Slower
        )

        return {
            "name": current.name,
            "baseline_mean_ms": mean1 / 1e6,
            "current_mean_ms": mean2 / 1e6,
            "relative_change": f"{relative_change:+.1%}",
            "t_statistic": round(t_stat, 3),
            "is_regression": is_regression,
            "confidence": "high" if abs(t_stat) > 3 else "medium" if abs(t_stat) > 2 else "low",
        }

# --- Py-spy integration for production profiling ---
# Command: py-spy record -o profile.svg --pid <PID>
# Or: py-spy record -o profile.svg -- python my_script.py
# Generates SVG flame graph without modifying code

# --- perf integration for system-level profiling ---
# perf record -g python my_script.py
# perf script | stackcollapse-perf.pl | flamegraph.pl > flame.svg
# This captures kernel + user stacks including C extensions

def demo_profiling():
    import random
    n = 100
    a = [[random.random() for _ in range(n)] for _ in range(n)]
    b = [[random.random() for _ in range(n)] for _ in range(n)]

    profiler = Profiler()
    result, hotspots = profiler.profile(matrix_multiply_naive, a, b)

    print("Top 5 hotspots:")
    for h in profiler.get_hotspots(5):
        print(f"  {h.function_name}: {h.cumulative_time:.3f}s "
              f"({h.total_calls} calls)")

    # SoA benchmark
    particles = ParticlesSoA(10000)
    import random as rng
    for i in range(particles.n):
        particles.vx[i] = rng.random()
        particles.vy[i] = rng.random()
        particles.vz[i] = rng.random()

    start = time.perf_counter()
    for _ in range(100):
        particles.update_positions(0.016)
    elapsed = time.perf_counter() - start
    print(f"SoA particle update: {elapsed:.3f}s for 100 frames x 10k particles")

    # Regression detection
    detector = RegressionDetector()
    baseline = BenchmarkResult("matrix_mul", [1e6 + rng.gauss(0, 5e4) for _ in range(50)])
    current = BenchmarkResult("matrix_mul", [1.15e6 + rng.gauss(0, 5e4) for _ in range(50)])
    comparison = detector.compare(baseline, current)
    print(f"Regression test: {comparison}")

demo_profiling()
```

## Summary and Key Takeaways

- **Profile before optimizing** — use cProfile/py-spy for Python, perf for system-level, and flame graphs for visualization
- **Cache-friendly access patterns** (sequential, SoA layout) can give 4-10x speedups due to the 100x cache hit vs miss cost difference
- A **common mistake** is optimizing code that accounts for <5% of total runtime — Amdahl's Law limits the impact
- **Branch prediction** matters in tight loops — sorted data or branchless code eliminates pipeline stalls
- The **trade-off** of SoA vs AoS: SoA is better for batch processing of single fields, AoS is better for accessing all fields of one entity
- **Statistical regression detection** (Welch's t-test) is more reliable than fixed thresholds for CI benchmarks
- The **pitfall** of microbenchmarking is JIT warmup, GC pauses, and OS scheduling noise — always include warmup iterations and use percentiles, not just mean"""
    ),
    (
        "performance/memory-profiling-leak-detection-gc-tuning",
        "Describe memory profiling and leak detection including Python memory internals with pymalloc and reference counting, generational garbage collection tuning, memory leak hunting with tracemalloc and objgraph, and memory-efficient data structures with slots and arrays",
        r"""# Memory Profiling, Leak Detection, and GC Tuning

## Python Memory Internals

Understanding Python's memory management is essential **because** Python uses a custom allocator (pymalloc) layered on top of the OS allocator, plus a hybrid reference counting + generational GC system. Memory leaks in Python aren't just about forgotten references — they include reference cycles, C extension leaks, and the `__del__` finalizer trap.

### Memory Architecture and Profiling

```python
import sys
import tracemalloc
import gc
import weakref
from typing import Any, Optional
from dataclasses import dataclass, field
import array

# --- Understanding Python object sizes ---

def analyze_object_sizes():
    # sys.getsizeof returns the DIRECT size, not recursive
    # Common mistake: thinking getsizeof gives total memory usage
    # It doesn't count referenced objects

    print("Base object sizes:")
    print(f"  int(0):     {sys.getsizeof(0)} bytes")
    print(f"  int(2**30): {sys.getsizeof(2**30)} bytes")
    print(f"  float:      {sys.getsizeof(1.0)} bytes")
    print(f"  str(''):    {sys.getsizeof('')} bytes")
    print(f"  str('abc'): {sys.getsizeof('abc')} bytes")
    print(f"  list([]):   {sys.getsizeof([])} bytes")
    print(f"  dict({{}}):   {sys.getsizeof({})} bytes")
    print(f"  tuple(()):  {sys.getsizeof(())} bytes")
    print(f"  set():      {sys.getsizeof(set())} bytes")

    # Deep size calculation
    def deep_getsizeof(obj: Any, seen: Optional[set] = None) -> int:
        # Best practice: recursively measure total object graph size
        if seen is None:
            seen = set()
        obj_id = id(obj)
        if obj_id in seen:
            return 0
        seen.add(obj_id)
        size = sys.getsizeof(obj)

        if isinstance(obj, dict):
            size += sum(deep_getsizeof(k, seen) + deep_getsizeof(v, seen)
                        for k, v in obj.items())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            size += sum(deep_getsizeof(item, seen) for item in obj)
        elif hasattr(obj, "__dict__"):
            size += deep_getsizeof(obj.__dict__, seen)
        elif hasattr(obj, "__slots__"):
            size += sum(
                deep_getsizeof(getattr(obj, slot, None), seen)
                for slot in obj.__slots__
                if hasattr(obj, slot)
            )
        return size

    # Compare dict-based vs __slots__ class
    class PointDict:
        def __init__(self, x: float, y: float, z: float):
            self.x = x
            self.y = y
            self.z = z

    class PointSlots:
        __slots__ = ("x", "y", "z")
        def __init__(self, x: float, y: float, z: float):
            self.x = x
            self.y = y
            self.z = z

    pd = PointDict(1.0, 2.0, 3.0)
    ps = PointSlots(1.0, 2.0, 3.0)
    print(f"\nPointDict size:  {deep_getsizeof(pd)} bytes")
    print(f"PointSlots size: {deep_getsizeof(ps)} bytes")
    # Trade-off: __slots__ saves ~40-60% memory per instance
    # but prevents dynamic attribute addition

    return deep_getsizeof

deep_getsizeof = analyze_object_sizes()

# --- tracemalloc for allocation tracking ---

class MemoryTracker:
    # Track memory allocations to find leaks and hotspots
    # However, tracemalloc adds ~10-30% overhead — use in dev/staging

    def __init__(self, top_n: int = 10):
        self.top_n = top_n
        self._snapshot1: Optional[tracemalloc.Snapshot] = None

    def start(self) -> None:
        tracemalloc.start(25)  # 25 frames of traceback
        self._snapshot1 = tracemalloc.take_snapshot()

    def report(self) -> list[dict]:
        snapshot2 = tracemalloc.take_snapshot()
        stats = snapshot2.compare_to(self._snapshot1, "lineno")

        results = []
        for stat in stats[:self.top_n]:
            results.append({
                "file": str(stat.traceback),
                "size_diff_kb": stat.size_diff / 1024,
                "size_kb": stat.size / 1024,
                "count_diff": stat.count_diff,
            })
        return results

    def stop(self) -> dict:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "current_mb": current / 1024 / 1024,
            "peak_mb": peak / 1024 / 1024,
        }
```

### Generational GC and Reference Cycles

Python's GC has three generations (0, 1, 2) with increasing collection thresholds. **Therefore**, long-lived objects migrate to higher generations and are collected less frequently. The **pitfall** is that `__del__` finalizers can prevent garbage collection of reference cycles — this is the most common source of "genuine" memory leaks in Python.

```python
# --- GC tuning and cycle detection ---

class GCMonitor:
    # Monitor garbage collection behavior
    def __init__(self):
        self._stats: list[dict] = []
        self._callbacks_installed = False

    def install(self) -> None:
        if not self._callbacks_installed:
            gc.callbacks.append(self._gc_callback)
            self._callbacks_installed = True

    def _gc_callback(self, phase: str, info: dict) -> None:
        if phase == "stop":
            self._stats.append({
                "generation": info.get("generation", -1),
                "collected": info.get("collected", 0),
                "uncollectable": info.get("uncollectable", 0),
            })

    def report(self) -> dict:
        total_collected = sum(s["collected"] for s in self._stats)
        total_uncollectable = sum(s["uncollectable"] for s in self._stats)
        collections_by_gen = {}
        for s in self._stats:
            gen = s["generation"]
            collections_by_gen[gen] = collections_by_gen.get(gen, 0) + 1
        return {
            "total_collections": len(self._stats),
            "total_collected": total_collected,
            "total_uncollectable": total_uncollectable,
            "collections_by_generation": collections_by_gen,
            "current_thresholds": gc.get_threshold(),
        }

# --- Demonstrating reference cycle leak ---

class Node:
    # Pitfall: circular reference prevents reference counting cleanup
    def __init__(self, name: str):
        self.name = name
        self.neighbors: list[Node] = []
        self._large_data = bytearray(1024 * 10)  # 10KB payload

    def connect(self, other: "Node") -> None:
        self.neighbors.append(other)
        other.neighbors.append(self)

def create_leak():
    # These nodes form a cycle: A -> B -> A
    a = Node("A")
    b = Node("B")
    a.connect(b)
    # When function returns, refcount doesn't drop to 0
    # because of the cycle — GC must detect and collect it
    return None  # Explicitly return None — refs are dropped

# --- Weak references to break cycles ---

class Cache:
    # Best practice: use WeakValueDictionary for caches
    # Objects are automatically evicted when no strong refs exist
    # Therefore, the cache doesn't prevent garbage collection
    def __init__(self, max_size: int = 1000):
        self._cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
        self._access_count = 0

    def get(self, key: str) -> Optional[Any]:
        self._access_count += 1
        return self._cache.get(key)

    def put(self, key: str, value: Any) -> None:
        self._cache[key] = value

    @property
    def size(self) -> int:
        return len(self._cache)

# --- Memory-efficient data structures ---

class CompactArray:
    # Use array module instead of list for homogeneous numeric data
    # Common mistake: using list of ints (28+ bytes each) instead of
    # array.array (8 bytes each for 'q' / 4 bytes for 'i')

    def __init__(self, typecode: str = "i"):
        self._data = array.array(typecode)

    def append(self, value: int) -> None:
        self._data.append(value)

    def extend(self, values: list[int]) -> None:
        self._data.extend(values)

    def __getitem__(self, idx: int) -> int:
        return self._data[idx]

    def __len__(self) -> int:
        return len(self._data)

    @property
    def memory_bytes(self) -> int:
        return self._data.buffer_info()[1] * self._data.itemsize

def compare_memory_usage():
    n = 100_000
    # Python list of ints
    py_list = list(range(n))
    list_size = sys.getsizeof(py_list) + sum(sys.getsizeof(x) for x in py_list[:100]) * (n // 100)

    # array.array
    arr = array.array("i", range(n))
    arr_size = sys.getsizeof(arr)

    print(f"\n{n} integers:")
    print(f"  list:  ~{list_size / 1024:.0f} KB")
    print(f"  array: ~{arr_size / 1024:.0f} KB")
    print(f"  ratio: {list_size / arr_size:.1f}x")

compare_memory_usage()
```

### Leak Hunting Workflow

The practical workflow for finding memory leaks combines `tracemalloc`, `gc.get_objects()`, and heap diffing. A **best practice** is to take snapshots at regular intervals and diff them — growing object counts indicate leaks.

```python
# --- Production leak detection ---

class LeakDetector:
    # Periodically snapshot heap and detect growing object types
    def __init__(self):
        self._snapshots: list[dict[str, int]] = []
        self._gc_monitor = GCMonitor()

    def take_snapshot(self) -> dict[str, int]:
        # Count objects by type
        gc.collect()  # Force collection first
        type_counts: dict[str, int] = {}
        for obj in gc.get_objects():
            type_name = type(obj).__name__
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        self._snapshots.append(type_counts)
        return type_counts

    def find_growing_types(self, min_growth_rate: float = 1.1) -> list[dict]:
        # Compare first and last snapshot
        # Therefore, types growing faster than 10% between snapshots
        # are likely leaking
        if len(self._snapshots) < 2:
            return []

        first = self._snapshots[0]
        last = self._snapshots[-1]

        growing: list[dict] = []
        for type_name, count in last.items():
            initial = first.get(type_name, 0)
            if initial > 0 and count / initial > min_growth_rate:
                growing.append({
                    "type": type_name,
                    "initial_count": initial,
                    "current_count": count,
                    "growth_factor": count / initial,
                })

        growing.sort(key=lambda x: x["growth_factor"], reverse=True)
        return growing

    def find_reference_cycles(self) -> list[list[Any]]:
        # Use gc.get_referrers to trace cycle paths
        gc.collect()
        gc.set_debug(gc.DEBUG_SAVEALL)
        gc.collect()
        cycles = gc.garbage[:]
        gc.garbage.clear()
        gc.set_debug(0)
        return cycles

# --- GC tuning for latency-sensitive applications ---

def tune_gc_for_latency():
    # Default thresholds: (700, 10, 10)
    # meaning: gen0 after 700 allocs-deallocs, gen1 every 10 gen0, gen2 every 10 gen1
    current = gc.get_threshold()
    print(f"Default GC thresholds: {current}")

    # For latency-sensitive code:
    # Option 1: More frequent, smaller collections
    gc.set_threshold(100, 5, 5)
    print("Tuned for latency: (100, 5, 5)")

    # Option 2: Manual GC at known safe points
    gc.disable()
    # ... process requests ...
    # During idle time or between requests:
    gc.collect(generation=0)  # Fast gen0 only
    gc.enable()

    # Option 3: Freeze long-lived objects (Python 3.7+)
    # gc.freeze() moves all current objects to permanent generation
    # Therefore, they're never scanned again — reduces GC pauses
    # Best for forked workers that share objects with parent

def demo_leak_detection():
    tracker = MemoryTracker()
    tracker.start()

    # Simulate work that may leak
    leaked_data = []
    for i in range(1000):
        create_leak()
        if i % 100 == 0:
            gc.collect()

    report = tracker.report()
    print("\nMemory allocation hotspots:")
    for entry in report[:5]:
        print(f"  {entry['file']}: {entry['size_diff_kb']:.1f} KB "
              f"({entry['count_diff']:+d} objects)")

    summary = tracker.stop()
    print(f"\nMemory: current={summary['current_mb']:.1f}MB, "
          f"peak={summary['peak_mb']:.1f}MB")

demo_leak_detection()
```

## Summary and Key Takeaways

- Python uses **hybrid memory management**: reference counting (immediate) + generational GC (cyclic)
- **`tracemalloc`** tracks allocation sites with tracebacks — essential for finding which code allocates the most memory
- A **common mistake** is using `sys.getsizeof()` without recursive traversal — it only measures direct object size, not referenced objects
- **`__slots__`** saves 40-60% memory per instance by eliminating per-object `__dict__` — use for classes with many instances
- The **pitfall** of `__del__` finalizers is that they can prevent GC from collecting reference cycles, causing genuine memory leaks
- **`weakref.WeakValueDictionary`** is the **best practice** for caches — objects are automatically evicted when no strong references exist
- **`gc.freeze()`** (Python 3.7+) moves long-lived objects to a permanent generation, reducing GC pause times for forked workers
- The **trade-off** of `gc.disable()` is zero GC pauses but potential memory growth from uncollected cycles"""
    ),
    (
        "performance/database-query-optimization-indexing",
        "Explain database performance optimization including query execution plan analysis with EXPLAIN ANALYZE, index types and selection strategies for B-tree and GIN and GiST indexes, query rewriting techniques, connection pooling tuning, and partition pruning with practical PostgreSQL examples",
        r"""# Database Performance Optimization and Indexing Strategies

## Reading Execution Plans

The most important skill in database performance is **reading execution plans**. EXPLAIN ANALYZE shows exactly what the database does — sequential scans, index scans, hash joins, sort operations — with actual row counts and timing. **Because** the optimizer makes cost-based decisions, understanding its choices lets you guide it toward better plans.

### EXPLAIN ANALYZE Deep Dive

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import time

# --- Query plan analysis framework ---

class ScanType(Enum):
    SEQ_SCAN = "Seq Scan"
    INDEX_SCAN = "Index Scan"
    INDEX_ONLY_SCAN = "Index Only Scan"
    BITMAP_INDEX_SCAN = "Bitmap Index Scan"
    BITMAP_HEAP_SCAN = "Bitmap Heap Scan"

class JoinType(Enum):
    NESTED_LOOP = "Nested Loop"
    HASH_JOIN = "Hash Join"
    MERGE_JOIN = "Merge Join"

@dataclass
class PlanNode:
    node_type: str
    relation: str = ""
    actual_rows: int = 0
    estimated_rows: int = 0
    actual_time_ms: float = 0.0
    startup_time_ms: float = 0.0
    loops: int = 1
    index_name: str = ""
    filter_condition: str = ""
    rows_removed_by_filter: int = 0
    children: list["PlanNode"] = field(default_factory=list)

    @property
    def estimation_error(self) -> float:
        # Ratio of actual to estimated rows
        # Best practice: investigate when ratio > 10x or < 0.1x
        if self.estimated_rows == 0:
            return float("inf") if self.actual_rows > 0 else 1.0
        return self.actual_rows / self.estimated_rows

    @property
    def is_seq_scan(self) -> bool:
        return self.node_type == ScanType.SEQ_SCAN.value

class QueryAnalyzer:
    # Analyze EXPLAIN ANALYZE output for common problems
    # Trade-off: automated analysis catches common issues but
    # may miss context-specific optimizations

    def __init__(self):
        self.warnings: list[str] = []
        self.suggestions: list[str] = []

    def analyze(self, plan: PlanNode) -> dict:
        self.warnings.clear()
        self.suggestions.clear()
        self._analyze_node(plan)
        return {
            "warnings": self.warnings.copy(),
            "suggestions": self.suggestions.copy(),
            "total_time_ms": plan.actual_time_ms,
        }

    def _analyze_node(self, node: PlanNode) -> None:
        # Check for sequential scans on large tables
        if node.is_seq_scan and node.actual_rows > 10000:
            self.warnings.append(
                f"Sequential scan on {node.relation} "
                f"({node.actual_rows} rows) — consider adding an index"
            )
            if node.filter_condition:
                self.suggestions.append(
                    f"CREATE INDEX ON {node.relation} "
                    f"for filter: {node.filter_condition}"
                )

        # Check for poor cardinality estimates
        # Common mistake: stale statistics cause bad plans
        if node.estimation_error > 10:
            self.warnings.append(
                f"Bad estimate on {node.relation}: "
                f"estimated {node.estimated_rows}, actual {node.actual_rows} "
                f"(ratio: {node.estimation_error:.1f}x) — run ANALYZE"
            )

        # Check for high filter removals
        if node.rows_removed_by_filter > node.actual_rows * 10:
            self.warnings.append(
                f"Scanned {node.rows_removed_by_filter + node.actual_rows} rows "
                f"but kept only {node.actual_rows} on {node.relation} — "
                f"index on filter column would help"
            )

        # Check nested loop with large outer
        if node.node_type == JoinType.NESTED_LOOP.value:
            if node.loops > 1000:
                self.warnings.append(
                    f"Nested loop with {node.loops} iterations — "
                    f"consider hash join (increase work_mem)"
                )

        for child in node.children:
            self._analyze_node(child)
```

### Index Types and Selection Strategies

Choosing the right index type is critical. PostgreSQL offers B-tree, Hash, GIN, GiST, SP-GiST, and BRIN — each optimized for different access patterns. **However**, the **pitfall** is over-indexing: every index slows down writes and consumes disk space. **Therefore**, index only what your queries actually need.

```python
# --- Index selection advisor ---

@dataclass
class QueryPattern:
    table: str
    columns_in_where: list[str]
    columns_in_order_by: list[str] = field(default_factory=list)
    columns_in_select: list[str] = field(default_factory=list)
    operators: dict[str, str] = field(default_factory=dict)  # column -> operator
    estimated_selectivity: float = 0.1  # fraction of rows returned
    frequency: int = 1  # queries per hour

class IndexType(Enum):
    BTREE = "btree"
    HASH = "hash"
    GIN = "gin"
    GIST = "gist"
    BRIN = "brin"

@dataclass
class IndexRecommendation:
    table: str
    columns: list[str]
    index_type: IndexType
    is_partial: bool = False
    partial_condition: str = ""
    is_covering: bool = False
    covering_columns: list[str] = field(default_factory=list)
    reason: str = ""

    def to_sql(self) -> str:
        cols = ", ".join(self.columns)
        name = f"idx_{self.table}_{'_'.join(self.columns)}"

        parts = [f"CREATE INDEX {name}"]
        parts.append(f"ON {self.table}")

        if self.index_type != IndexType.BTREE:
            parts.append(f"USING {self.index_type.value}")

        if self.is_covering and self.covering_columns:
            parts.append(f"({cols}) INCLUDE ({', '.join(self.covering_columns)})")
        else:
            parts.append(f"({cols})")

        if self.is_partial:
            parts.append(f"WHERE {self.partial_condition}")

        return " ".join(parts) + ";"

class IndexAdvisor:
    def recommend(self, patterns: list[QueryPattern]) -> list[IndexRecommendation]:
        recommendations: list[IndexRecommendation] = []

        for pattern in patterns:
            rec = self._analyze_pattern(pattern)
            if rec:
                recommendations.append(rec)

        # Deduplicate and merge overlapping indexes
        return self._merge_recommendations(recommendations)

    def _analyze_pattern(self, p: QueryPattern) -> Optional[IndexRecommendation]:
        if not p.columns_in_where:
            return None

        # Determine index type based on operators
        for col, op in p.operators.items():
            if op in ("@>", "?", "?|", "?&"):
                # JSONB containment/existence — use GIN
                return IndexRecommendation(
                    table=p.table, columns=[col],
                    index_type=IndexType.GIN,
                    reason=f"JSONB operator {op} requires GIN index",
                )
            if op in ("&&", "@>", "<@") and "array" in col.lower():
                return IndexRecommendation(
                    table=p.table, columns=[col],
                    index_type=IndexType.GIN,
                    reason="Array overlap/containment requires GIN index",
                )
            if op in ("<<", ">>", "&<", "&>", "~="):
                # Geometric/range operators — use GiST
                return IndexRecommendation(
                    table=p.table, columns=[col],
                    index_type=IndexType.GIST,
                    reason=f"Range/geometric operator {op} requires GiST index",
                )

        # B-tree for equality and range queries
        columns = p.columns_in_where.copy()
        # Put equality columns first, then range columns (best practice)
        eq_cols = [c for c, op in p.operators.items() if op == "=" and c in columns]
        range_cols = [c for c, op in p.operators.items() if op in (">", "<", ">=", "<=", "BETWEEN") and c in columns]
        ordered = eq_cols + range_cols

        if not ordered:
            ordered = columns

        # Partial index for selective queries
        is_partial = p.estimated_selectivity < 0.05  # < 5% rows
        partial_cond = ""
        if is_partial and len(ordered) == 1:
            col = ordered[0]
            op = p.operators.get(col, "=")
            partial_cond = f"{col} IS NOT NULL"  # Simplified

        # Covering index if SELECT columns are few
        covering = []
        if len(p.columns_in_select) <= 3:
            covering = [c for c in p.columns_in_select if c not in ordered]

        return IndexRecommendation(
            table=p.table, columns=ordered,
            index_type=IndexType.BTREE,
            is_partial=is_partial,
            partial_condition=partial_cond,
            is_covering=bool(covering),
            covering_columns=covering,
            reason=f"Covers WHERE clause ({', '.join(ordered)})",
        )

    def _merge_recommendations(
        self, recs: list[IndexRecommendation]
    ) -> list[IndexRecommendation]:
        # Merge indexes on same table where one is a prefix of another
        # Therefore, index on (a, b) covers queries on (a) alone
        merged: list[IndexRecommendation] = []
        by_table: dict[str, list[IndexRecommendation]] = {}
        for r in recs:
            by_table.setdefault(r.table, []).append(r)

        for table, table_recs in by_table.items():
            table_recs.sort(key=lambda r: len(r.columns), reverse=True)
            kept: list[IndexRecommendation] = []
            for rec in table_recs:
                # Check if any existing rec covers this one
                covered = False
                for existing in kept:
                    if (existing.index_type == rec.index_type and
                        rec.columns == existing.columns[:len(rec.columns)]):
                        covered = True
                        break
                if not covered:
                    kept.append(rec)
            merged.extend(kept)

        return merged

# --- Demo ---

def demo_index_advisor():
    patterns = [
        QueryPattern(
            table="orders",
            columns_in_where=["user_id", "status"],
            columns_in_order_by=["created_at"],
            operators={"user_id": "=", "status": "="},
            estimated_selectivity=0.02,
            frequency=500,
        ),
        QueryPattern(
            table="orders",
            columns_in_where=["created_at"],
            operators={"created_at": "BETWEEN"},
            estimated_selectivity=0.1,
            frequency=50,
        ),
        QueryPattern(
            table="products",
            columns_in_where=["metadata"],
            operators={"metadata": "@>"},
            frequency=200,
        ),
    ]

    advisor = IndexAdvisor()
    recommendations = advisor.recommend(patterns)

    print("Index recommendations:")
    for rec in recommendations:
        print(f"  {rec.to_sql()}")
        print(f"    Reason: {rec.reason}")

demo_index_advisor()
```

### Query Rewriting and Partition Pruning

Sometimes the fastest optimization is **rewriting the query** rather than adding indexes. **Best practice**: replace correlated subqueries with JOINs, use CTEs for readability but know they can be optimization fences, and leverage partition pruning for time-series data.

```python
# --- Query rewriting patterns ---

QUERY_REWRITES = {
    "correlated_subquery_to_join": {
        "before": (
            "SELECT o.id, o.total "
            "FROM orders o "
            "WHERE o.total > ("
            "  SELECT AVG(total) FROM orders WHERE user_id = o.user_id"
            ")"
        ),
        "after": (
            "SELECT o.id, o.total "
            "FROM orders o "
            "JOIN ("
            "  SELECT user_id, AVG(total) AS avg_total "
            "  FROM orders GROUP BY user_id"
            ") avg_by_user ON o.user_id = avg_by_user.user_id "
            "WHERE o.total > avg_by_user.avg_total"
        ),
        "reason": "Correlated subquery executes once per row; JOIN computes avg once",
    },
    "exists_instead_of_in": {
        "before": (
            "SELECT * FROM users "
            "WHERE id IN (SELECT user_id FROM orders WHERE total > 100)"
        ),
        "after": (
            "SELECT u.* FROM users u "
            "WHERE EXISTS ("
            "  SELECT 1 FROM orders o "
            "  WHERE o.user_id = u.id AND o.total > 100"
            ")"
        ),
        "reason": "EXISTS short-circuits after first match; IN materializes full list",
    },
    "lateral_join_for_top_n_per_group": {
        "before": (
            "SELECT DISTINCT ON (user_id) * "
            "FROM orders ORDER BY user_id, created_at DESC"
        ),
        "after": (
            "SELECT u.id, latest_order.* "
            "FROM users u "
            "CROSS JOIN LATERAL ("
            "  SELECT * FROM orders o "
            "  WHERE o.user_id = u.id "
            "  ORDER BY o.created_at DESC LIMIT 3"
            ") latest_order"
        ),
        "reason": "LATERAL join fetches top-N per group using index efficiently",
    },
}

# --- Partition strategy ---

PARTITION_DDLS = {
    "range_by_date": (
        "CREATE TABLE events ("
        "  id BIGSERIAL, "
        "  event_type TEXT NOT NULL, "
        "  payload JSONB, "
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ") PARTITION BY RANGE (created_at);\n"
        "\n"
        "CREATE TABLE events_2024_q1 PARTITION OF events "
        "  FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');\n"
        "CREATE TABLE events_2024_q2 PARTITION OF events "
        "  FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');\n"
        "-- Partition pruning: WHERE created_at >= '2024-04-01' "
        "-- only scans events_2024_q2+"
    ),
    "list_by_region": (
        "CREATE TABLE orders ("
        "  id BIGSERIAL, "
        "  region TEXT NOT NULL, "
        "  total NUMERIC(10,2)"
        ") PARTITION BY LIST (region);\n"
        "\n"
        "CREATE TABLE orders_us PARTITION OF orders FOR VALUES IN ('US');\n"
        "CREATE TABLE orders_eu PARTITION OF orders FOR VALUES IN ('EU', 'UK');\n"
        "CREATE TABLE orders_apac PARTITION OF orders FOR VALUES IN ('JP', 'KR', 'AU');\n"
        "-- Pitfall: queries without partition key in WHERE scan ALL partitions"
    ),
}

def print_query_rewrites():
    for name, rewrite in QUERY_REWRITES.items():
        print(f"\n--- {name} ---")
        print(f"Reason: {rewrite['reason']}")

print_query_rewrites()
```

## Summary and Key Takeaways

- **EXPLAIN ANALYZE** is the single most important tool — it shows actual execution time, row counts, and plan choices
- A **common mistake** is creating indexes without checking if the optimizer actually uses them — always verify with EXPLAIN
- Put **equality columns first** in composite B-tree indexes, then range columns — this maximizes index efficiency
- **Partial indexes** (CREATE INDEX ... WHERE condition) are dramatically smaller and faster for selective queries
- **Covering indexes** (INCLUDE clause) enable index-only scans, eliminating heap fetches entirely
- The **trade-off** of indexing: every index speeds reads but slows writes and consumes disk — index only what queries need
- **Partition pruning** provides order-of-magnitude speedups for time-series data — the **pitfall** is queries without the partition key in WHERE, which scan all partitions
- **LATERAL JOIN** is the best pattern for "top N per group" queries — it leverages indexes instead of sorting entire tables"""
    ),
    (
        "performance/async-io-event-loops-network-optimization",
        "Describe async I/O performance patterns including event loop internals with epoll and kqueue, TCP socket optimization with Nagle algorithm and TCP_NODELAY, connection pooling with health checks, HTTP/2 multiplexing benefits, and zero-copy techniques for file serving",
        r"""# Async I/O and Network Performance Optimization

## Event Loop Internals

Every async framework (asyncio, Node.js, Go runtime, Tokio) is built on the same foundation: an **event loop** that multiplexes I/O using OS primitives — `epoll` (Linux), `kqueue` (macOS/BSD), or `IOCP` (Windows). Understanding these internals is critical **because** the choice of I/O multiplexer and how you interact with it determines whether your server handles 100 or 100,000 concurrent connections.

### Event Loop and Socket Management

```python
import socket
import select
import time
import errno
from typing import Callable, Optional
from dataclasses import dataclass, field
from collections import deque
import struct

# --- Minimal event loop using select (cross-platform) ---

@dataclass
class IOHandler:
    fd: int
    on_readable: Optional[Callable] = None
    on_writable: Optional[Callable] = None
    write_buffer: bytearray = field(default_factory=bytearray)

class MiniEventLoop:
    # Best practice: understand how event loops work internally
    # before optimizing code that runs on them

    def __init__(self):
        self._handlers: dict[int, IOHandler] = {}
        self._timers: list[tuple[float, Callable]] = []
        self._running = False
        # In production: use selectors module which auto-picks
        # epoll/kqueue/IOCP based on platform

    def register(self, sock: socket.socket, handler: IOHandler) -> None:
        sock.setblocking(False)
        self._handlers[sock.fileno()] = handler

    def unregister(self, sock: socket.socket) -> None:
        self._handlers.pop(sock.fileno(), None)

    def call_later(self, delay: float, callback: Callable) -> None:
        self._timers.append((time.monotonic() + delay, callback))
        self._timers.sort(key=lambda t: t[0])

    def run(self, timeout: float = 30.0) -> None:
        self._running = True
        deadline = time.monotonic() + timeout

        while self._running and time.monotonic() < deadline:
            # Process expired timers
            now = time.monotonic()
            while self._timers and self._timers[0][0] <= now:
                _, callback = self._timers.pop(0)
                callback()

            # Calculate select timeout
            if self._timers:
                select_timeout = max(0, self._timers[0][0] - time.monotonic())
            else:
                select_timeout = 0.1

            if not self._handlers:
                time.sleep(min(select_timeout, 0.01))
                continue

            # Determine which fds to watch
            readable_fds = []
            writable_fds = []
            for fd, handler in self._handlers.items():
                if handler.on_readable:
                    readable_fds.append(fd)
                if handler.on_writable and handler.write_buffer:
                    writable_fds.append(fd)

            try:
                readable, writable, _ = select.select(
                    readable_fds, writable_fds, [],
                    select_timeout
                )
            except (ValueError, OSError):
                break

            for fd in readable:
                handler = self._handlers.get(fd)
                if handler and handler.on_readable:
                    handler.on_readable()

            for fd in writable:
                handler = self._handlers.get(fd)
                if handler and handler.on_writable:
                    handler.on_writable()

    def stop(self) -> None:
        self._running = False
```

### TCP Optimization and Connection Pooling

**However**, raw socket performance depends heavily on TCP tuning. The **Nagle algorithm** (enabled by default) buffers small writes to reduce packet count, but adds up to 200ms latency. **Therefore**, for request-response protocols like HTTP, setting `TCP_NODELAY` is essential.

```python
# --- TCP socket optimization ---

def create_optimized_server_socket(
    host: str = "0.0.0.0", port: int = 8080
) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # SO_REUSEADDR: allow binding to recently-closed port
    # Pitfall: without this, server restart fails with "Address already in use"
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # TCP_NODELAY: disable Nagle algorithm
    # Trade-off: more packets but lower latency
    # Best practice: ALWAYS set for request-response protocols
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # TCP_QUICKACK: disable delayed ACKs (Linux only)
    # Complements TCP_NODELAY for full low-latency stack
    try:
        sock.setsockopt(socket.IPPROTO_TCP, 12, 1)  # TCP_QUICKACK = 12
    except (OSError, AttributeError):
        pass  # Not available on all platforms

    # SO_KEEPALIVE: detect dead connections
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    # Increase socket buffer sizes for high throughput
    # Common mistake: using default 8KB buffers for bulk transfers
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)

    # TCP_DEFER_ACCEPT (Linux): don't wake on SYN, wait for data
    # Therefore, accept() returns only when data is ready to read
    try:
        sock.setsockopt(socket.IPPROTO_TCP, 9, 1)  # TCP_DEFER_ACCEPT = 9
    except (OSError, AttributeError):
        pass

    sock.bind((host, port))
    sock.listen(4096)  # Large backlog for burst handling
    sock.setblocking(False)
    return sock

# --- Connection pool with health checking ---

@dataclass
class PooledConnection:
    sock: socket.socket
    created_at: float
    last_used: float
    in_use: bool = False
    healthy: bool = True

class ConnectionPool:
    # Best practice: reuse connections to amortize TCP handshake cost
    # TCP handshake = 1.5 RTT, TLS adds another 1-2 RTT
    def __init__(
        self,
        host: str,
        port: int,
        min_size: int = 5,
        max_size: int = 50,
        max_idle_time: float = 300.0,  # 5 minutes
        health_check_interval: float = 30.0,
    ):
        self.host = host
        self.port = port
        self.min_size = min_size
        self.max_size = max_size
        self.max_idle_time = max_idle_time
        self.health_check_interval = health_check_interval
        self._pool: deque[PooledConnection] = deque()
        self._active_count = 0
        self._total_created = 0
        self._total_reused = 0

    def _create_connection(self) -> PooledConnection:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(5.0)
        sock.connect((self.host, self.port))
        now = time.monotonic()
        self._total_created += 1
        return PooledConnection(
            sock=sock, created_at=now, last_used=now
        )

    def acquire(self) -> PooledConnection:
        now = time.monotonic()

        # Try to reuse an idle connection (LIFO for cache warmth)
        # Trade-off: LIFO keeps fewer connections warm but they're hotter
        while self._pool:
            conn = self._pool.pop()
            age = now - conn.last_used
            if age > self.max_idle_time:
                conn.sock.close()
                continue
            if not self._is_healthy(conn):
                conn.sock.close()
                continue
            conn.in_use = True
            conn.last_used = now
            self._active_count += 1
            self._total_reused += 1
            return conn

        # Create new connection if under limit
        if self._active_count < self.max_size:
            conn = self._create_connection()
            conn.in_use = True
            self._active_count += 1
            return conn

        raise ConnectionError(
            f"Pool exhausted: {self._active_count}/{self.max_size} active"
        )

    def release(self, conn: PooledConnection) -> None:
        conn.in_use = False
        conn.last_used = time.monotonic()
        self._active_count -= 1
        self._pool.append(conn)

    def _is_healthy(self, conn: PooledConnection) -> bool:
        # Check if connection is still alive
        try:
            # Peek without consuming data
            conn.sock.setblocking(False)
            data = conn.sock.recv(1, socket.MSG_PEEK)
            conn.sock.setblocking(True)
            if data == b"":
                return False  # Peer closed
            return True
        except BlockingIOError:
            return True  # No data available = still alive
        except Exception:
            return False

    @property
    def stats(self) -> dict:
        return {
            "active": self._active_count,
            "idle": len(self._pool),
            "total_created": self._total_created,
            "total_reused": self._total_reused,
            "reuse_ratio": (
                self._total_reused / (self._total_created + self._total_reused)
                if (self._total_created + self._total_reused) > 0
                else 0
            ),
        }
```

### HTTP/2 Multiplexing and Zero-Copy

**HTTP/2 multiplexing** eliminates head-of-line blocking at the application layer by interleaving multiple request/response streams over a single TCP connection. For file serving, **zero-copy** techniques like `sendfile()` bypass user-space entirely, copying data directly from disk to network buffer in the kernel.

```python
import os
import mmap

# --- Zero-copy file serving ---

def sendfile_wrapper(
    out_fd: int, in_fd: int, offset: int, count: int
) -> int:
    # os.sendfile() bypasses user-space buffer copies
    # Kernel copies directly from page cache to socket buffer
    # Therefore, no CPU cycles wasted on memory copies
    # Common mistake: reading file into Python bytes then writing to socket
    try:
        return os.sendfile(out_fd, in_fd, offset, count)
    except OSError:
        # Fallback for platforms without sendfile
        return -1

class ZeroCopyFileServer:
    # Serve static files with minimal memory copies
    # Pitfall: sendfile doesn't work with TLS — data must pass through
    # SSL library in user space. Use splice() for encrypted zero-copy.

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self._mmap_cache: dict[str, tuple[mmap.mmap, int]] = {}

    def serve_file(self, path: str, client_sock: socket.socket) -> int:
        full_path = os.path.join(self.root_dir, path.lstrip("/"))
        if not os.path.isfile(full_path):
            return 404

        file_size = os.path.getsize(full_path)

        # Send HTTP headers
        headers = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Length: {file_size}\r\n"
            f"Content-Type: application/octet-stream\r\n"
            f"\r\n"
        )
        client_sock.sendall(headers.encode())

        # Zero-copy file transfer
        with open(full_path, "rb") as f:
            offset = 0
            remaining = file_size
            while remaining > 0:
                sent = sendfile_wrapper(
                    client_sock.fileno(), f.fileno(),
                    offset, min(remaining, 1024 * 1024)  # 1MB chunks
                )
                if sent <= 0:
                    # Fallback to regular send
                    chunk = f.read(min(remaining, 65536))
                    if not chunk:
                        break
                    client_sock.sendall(chunk)
                    sent = len(chunk)
                offset += sent
                remaining -= sent

        return 200

    def serve_with_mmap(self, path: str, client_sock: socket.socket) -> int:
        # Alternative: memory-mapped files for random access
        # Trade-off: mmap uses page cache efficiently but
        # can cause page faults under memory pressure
        full_path = os.path.join(self.root_dir, path.lstrip("/"))
        if not os.path.isfile(full_path):
            return 404

        with open(full_path, "rb") as f:
            file_size = os.path.getsize(full_path)
            if file_size == 0:
                return 204
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                headers = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Length: {file_size}\r\n\r\n"
                )
                client_sock.sendall(headers.encode())
                # Send mmap'd data in chunks
                offset = 0
                while offset < file_size:
                    chunk_size = min(65536, file_size - offset)
                    client_sock.sendall(mm[offset:offset + chunk_size])
                    offset += chunk_size
            finally:
                mm.close()

        return 200

# --- HTTP/2 benefits summary ---

HTTP2_BENEFITS = {
    "multiplexing": (
        "Multiple request/response streams over one TCP connection. "
        "Eliminates HTTP/1.1 head-of-line blocking at application layer. "
        "However, TCP-level HOL blocking still exists (fixed by HTTP/3 QUIC)."
    ),
    "header_compression": (
        "HPACK compresses headers using static + dynamic tables. "
        "Reduces header overhead from ~800 bytes to ~20 bytes for repeat requests."
    ),
    "server_push": (
        "Server proactively sends resources before client requests them. "
        "Trade-off: can waste bandwidth if client already has cached versions. "
        "Best practice: use 103 Early Hints instead (less aggressive)."
    ),
    "stream_prioritization": (
        "Clients can assign priority and dependency to streams. "
        "Allows CSS/JS to load before images. "
        "Pitfall: many servers ignore priority hints."
    ),
}
```

## Summary and Key Takeaways

- Event loops use **epoll/kqueue/IOCP** to handle thousands of connections with a single thread — understand which syscall your platform uses
- **TCP_NODELAY** is essential for request-response protocols — Nagle's algorithm adds up to 200ms latency on small writes
- A **common mistake** is using default socket buffer sizes (8KB) for high-throughput transfers — increase to 256KB+
- **Connection pooling** amortizes TCP handshake cost (1.5 RTT + TLS overhead) — use LIFO for cache-warm connections
- **Zero-copy** with `sendfile()` eliminates user-space buffer copies — the **pitfall** is that it doesn't work with TLS
- **HTTP/2 multiplexing** eliminates application-layer head-of-line blocking — **however**, TCP-level HOL blocking remains (fixed by HTTP/3 QUIC)
- The **trade-off** of connection pool sizing: too few connections = request queuing, too many = resource exhaustion — use Little's Law: `pool_size = throughput * avg_latency`
- **Best practice**: monitor connection reuse ratios — below 80% indicates pool misconfiguration or connection churn"""
    ),
]
