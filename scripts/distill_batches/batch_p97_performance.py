"""Performance — profiling, optimization, caching strategies, and benchmarking."""

PAIRS = [
    (
        "performance/python-profiling",
        "Show Python profiling patterns: cProfile, memory profiling, line profiling, and flamegraphs.",
        '''Python profiling patterns:

```python
import cProfile
import pstats
import tracemalloc
import functools
import time
from io import StringIO
from contextlib import contextmanager


# --- Quick function timing ---

@contextmanager
def timer(label: str = ""):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"{label}: {elapsed:.4f}s" if label else f"{elapsed:.4f}s")

# with timer("DB query"):
#     results = db.query(...)


# --- cProfile decorator ---

def profile(func):
    """Profile a function and print stats."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        result = func(*args, **kwargs)
        profiler.disable()

        stream = StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.strip_dirs()
        stats.sort_stats("cumulative")
        stats.print_stats(20)  # Top 20 functions
        print(stream.getvalue())

        return result
    return wrapper

# @profile
# def expensive_function():
#     ...


# --- Memory profiling ---

def track_memory(func):
    """Track memory allocations in a function."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tracemalloc.start()
        result = func(*args, **kwargs)
        snapshot = tracemalloc.take_snapshot()

        # Top 10 memory consumers
        stats = snapshot.statistics("lineno")
        print(f"\\n=== Memory profile: {func.__name__} ===")
        for stat in stats[:10]:
            print(f"  {stat}")

        current, peak = tracemalloc.get_traced_memory()
        print(f"  Current: {current / 1024:.1f} KB")
        print(f"  Peak:    {peak / 1024:.1f} KB")
        tracemalloc.stop()

        return result
    return wrapper


# --- Benchmark comparison ---

def benchmark(funcs: dict[str, callable], *args,
              iterations: int = 1000, warmup: int = 10) -> dict:
    """Compare execution time of multiple functions."""
    results = {}

    for name, func in funcs.items():
        # Warmup
        for _ in range(warmup):
            func(*args)

        # Measure
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            func(*args)
            times.append(time.perf_counter() - start)

        results[name] = {
            "mean": sum(times) / len(times),
            "min": min(times),
            "max": max(times),
            "median": sorted(times)[len(times) // 2],
            "p99": sorted(times)[int(len(times) * 0.99)],
        }

    # Print comparison
    fastest = min(results.items(), key=lambda x: x[1]["mean"])
    for name, stats in sorted(results.items(), key=lambda x: x[1]["mean"]):
        ratio = stats["mean"] / fastest[1]["mean"]
        print(f"  {name:20s}  mean={stats['mean']*1e6:8.1f}µs  "
              f"p99={stats['p99']*1e6:8.1f}µs  ({ratio:.2f}x)")

    return results


# --- Common optimizations ---

# 1. Use generators for large sequences
# BAD:  data = [process(x) for x in huge_list]
# GOOD: data = (process(x) for x in huge_list)

# 2. Use __slots__ for many instances
class Point:
    __slots__ = ("x", "y")
    def __init__(self, x, y):
        self.x, self.y = x, y

# 3. Local variable access is faster than global
def fast_loop(items):
    local_process = process  # Cache function lookup
    result = []
    append = result.append   # Cache method lookup
    for item in items:
        append(local_process(item))
    return result

# 4. Use dict.get() instead of try/except for key access
# 5. Use set for membership testing (O(1) vs O(n) for list)
# 6. String joining: "".join(parts) vs += concatenation
# 7. Use collections.deque for queue operations (O(1) popleft)
```

Profiling patterns:
1. **`cProfile`** — function-level CPU profiling with cumulative stats
2. **`tracemalloc`** — track memory allocations by source line
3. **`time.perf_counter()`** — high-resolution timing (nanosecond precision)
4. **Benchmark comparison** — measure mean, p99, ratio vs fastest
5. **`__slots__`** — 40% less memory per instance, faster attribute access'''
    ),
    (
        "performance/caching-strategies",
        "Show caching patterns: memoization, LRU, TTL, cache invalidation, and multi-level caching.",
        '''Caching strategy patterns:

```python
import asyncio
import hashlib
import json
import time
import logging
from typing import TypeVar, Callable, Any
from functools import lru_cache, wraps
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
T = TypeVar("T")


# --- TTL cache decorator ---

def ttl_cache(ttl: float = 300, maxsize: int = 128):
    """Cache with time-to-live expiration."""
    def decorator(func):
        cache: dict[str, tuple[float, Any]] = {}

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = str((args, sorted(kwargs.items())))
            now = time.time()

            if key in cache:
                expires, value = cache[key]
                if now < expires:
                    return value

            result = func(*args, **kwargs)
            cache[key] = (now + ttl, result)

            # Evict expired entries if cache too large
            if len(cache) > maxsize:
                expired = [k for k, (exp, _) in cache.items() if now >= exp]
                for k in expired:
                    del cache[k]

            return result
        wrapper.cache_clear = lambda: cache.clear()
        return wrapper
    return decorator


# @ttl_cache(ttl=60)
# def get_exchange_rate(currency: str) -> float:
#     return fetch_from_api(currency)


# --- Async TTL cache ---

def async_ttl_cache(ttl: float = 300):
    """TTL cache for async functions."""
    def decorator(func):
        cache: dict[str, tuple[float, Any]] = {}
        locks: dict[str, asyncio.Lock] = {}

        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = str((args, sorted(kwargs.items())))
            now = time.time()

            # Check cache
            if key in cache:
                expires, value = cache[key]
                if now < expires:
                    return value

            # Prevent cache stampede with per-key lock
            if key not in locks:
                locks[key] = asyncio.Lock()

            async with locks[key]:
                # Double-check after acquiring lock
                if key in cache:
                    expires, value = cache[key]
                    if now < expires:
                        return value

                result = await func(*args, **kwargs)
                cache[key] = (time.time() + ttl, result)
                return result

        return wrapper
    return decorator


# --- Multi-level cache ---

class MultiLevelCache:
    """L1 (in-memory) + L2 (Redis) cache."""

    def __init__(self, redis_client, l1_ttl: int = 60, l2_ttl: int = 3600):
        self._l1: dict[str, tuple[float, Any]] = {}
        self._redis = redis_client
        self.l1_ttl = l1_ttl
        self.l2_ttl = l2_ttl

    async def get(self, key: str) -> Any | None:
        now = time.time()

        # L1: in-memory (fastest)
        if key in self._l1:
            expires, value = self._l1[key]
            if now < expires:
                logger.debug("L1 hit: %s", key)
                return value
            del self._l1[key]

        # L2: Redis
        raw = await self._redis.get(f"cache:{key}")
        if raw:
            logger.debug("L2 hit: %s", key)
            value = json.loads(raw)
            # Promote to L1
            self._l1[key] = (now + self.l1_ttl, value)
            return value

        logger.debug("Cache miss: %s", key)
        return None

    async def set(self, key: str, value: Any):
        now = time.time()
        serialized = json.dumps(value, default=str)

        # Write to both levels
        self._l1[key] = (now + self.l1_ttl, value)
        await self._redis.set(f"cache:{key}", serialized, ex=self.l2_ttl)

    async def invalidate(self, key: str):
        self._l1.pop(key, None)
        await self._redis.delete(f"cache:{key}")

    async def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern."""
        # Clear L1
        to_delete = [k for k in self._l1 if k.startswith(pattern.rstrip("*"))]
        for k in to_delete:
            del self._l1[k]
        # Clear L2
        async for key in self._redis.scan_iter(f"cache:{pattern}"):
            await self._redis.delete(key)


# --- Cache-aside pattern ---

class UserService:
    def __init__(self, db, cache: MultiLevelCache):
        self.db = db
        self.cache = cache

    async def get_user(self, user_id: str) -> dict:
        # 1. Check cache
        cached = await self.cache.get(f"user:{user_id}")
        if cached:
            return cached

        # 2. Cache miss — fetch from DB
        user = await self.db.get_user(user_id)

        # 3. Populate cache
        if user:
            await self.cache.set(f"user:{user_id}", user)

        return user

    async def update_user(self, user_id: str, data: dict):
        # 1. Update DB
        await self.db.update_user(user_id, data)

        # 2. Invalidate cache (write-invalidate pattern)
        await self.cache.invalidate(f"user:{user_id}")

        # Or: write-through (update cache immediately)
        # updated = await self.db.get_user(user_id)
        # await self.cache.set(f"user:{user_id}", updated)
```

Caching patterns:
1. **TTL cache** — auto-expire entries after fixed duration
2. **Stampede prevention** — per-key async lock prevents concurrent cache fills
3. **Multi-level** — L1 in-memory (fast) + L2 Redis (shared, durable)
4. **Cache-aside** — check cache, miss → DB → populate cache
5. **Write-invalidate** — invalidate cache on write, lazy repopulate on read'''
    ),
    (
        "performance/web-optimization",
        "Show web performance optimization patterns: lazy loading, code splitting, image optimization, and Core Web Vitals.",
        '''Web performance optimization:

```typescript
// --- Code splitting with dynamic imports ---

// React lazy loading
import { lazy, Suspense } from 'react';

// Component loaded only when rendered
const Dashboard = lazy(() => import('./pages/Dashboard'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));

function App() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/admin" element={<AdminPanel />} />
      </Routes>
    </Suspense>
  );
}

// Route-based splitting with prefetch
const routes = [
  {
    path: '/dashboard',
    component: lazy(() =>
      import(/* webpackPrefetch: true */ './pages/Dashboard')
    ),
  },
];


// --- Image optimization ---

// Next.js Image component (auto-optimizes)
// import Image from 'next/image';
// <Image src="/hero.jpg" width={1200} height={600}
//   sizes="(max-width: 768px) 100vw, 1200px"
//   placeholder="blur" blurDataURL={blurHash}
//   priority  // LCP image — load immediately
// />

// Native lazy loading
// <img src="photo.jpg" loading="lazy" decoding="async"
//   width="400" height="300" alt="Photo" />

// Responsive images
// <picture>
//   <source srcset="hero.avif" type="image/avif" />
//   <source srcset="hero.webp" type="image/webp" />
//   <img src="hero.jpg" alt="Hero" width="1200" height="600" />
// </picture>


// --- Resource hints ---

// Preload critical resources (fonts, hero image)
// <link rel="preload" href="/fonts/inter.woff2" as="font"
//   type="font/woff2" crossorigin />
// <link rel="preload" href="/hero.webp" as="image" />

// Prefetch next page resources
// <link rel="prefetch" href="/dashboard.js" />

// Preconnect to API domain
// <link rel="preconnect" href="https://api.example.com" />
// <link rel="dns-prefetch" href="https://cdn.example.com" />


// --- Virtual scrolling for large lists ---

import { useVirtualizer } from '@tanstack/react-virtual';
import { useRef } from 'react';

function VirtualList({ items }: { items: any[] }) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 50,     // Estimated row height
    overscan: 5,                // Render 5 extra items above/below
  });

  return (
    <div ref={parentRef} style={{ height: '600px', overflow: 'auto' }}>
      <div style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
        {virtualizer.getVirtualItems().map((virtualItem) => (
          <div
            key={virtualItem.key}
            style={{
              position: 'absolute',
              top: 0,
              transform: `translateY(${virtualItem.start}px)`,
              height: `${virtualItem.size}px`,
            }}
          >
            {items[virtualItem.index].name}
          </div>
        ))}
      </div>
    </div>
  );
}


// --- Debounce and throttle ---

function debounce<T extends (...args: any[]) => any>(
  fn: T, ms: number
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout>;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function throttle<T extends (...args: any[]) => any>(
  fn: T, ms: number
): (...args: Parameters<T>) => void {
  let last = 0;
  return (...args) => {
    const now = Date.now();
    if (now - last >= ms) {
      last = now;
      fn(...args);
    }
  };
}

// const handleSearch = debounce((query: string) => {
//   fetch(`/api/search?q=${query}`);
// }, 300);

// const handleScroll = throttle(() => {
//   updateScrollPosition();
// }, 100);
```

Web performance patterns:
1. **`lazy()` + `Suspense`** — load page components only when navigated to
2. **`loading="lazy"`** — defer offscreen images until near viewport
3. **`<link rel="preload">`** — prioritize critical resources (fonts, LCP image)
4. **Virtual scrolling** — render only visible rows for 10K+ item lists
5. **Debounce/throttle** — limit rapid-fire events (search input, scroll)'''
    ),
]
"""
