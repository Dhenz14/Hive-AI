PAIRS = [
    ("thinking/debugging", r'''My Python web service's memory usage grows continuously until it gets OOM-killed. I've traced it to circular references. Here's a simplified version of the problematic code:

```python
class Node:
    def __init__(self, value):
        self.value = value
        self.parent = None
        self.children = []

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

class TreeProcessor:
    _cache = {}  # class-level cache

    def process(self, data):
        root = Node("root")
        for item in data:
            child = Node(item)
            root.add_child(child)
        TreeProcessor._cache[id(root)] = root
        return self._compute(root)

    def _compute(self, node):
        return sum(len(c.value) for c in node.children)
```

Memory profile shows:
```
Line #    Mem usage    Increment
    22    150.3 MiB      0.0 MiB   def process(data):
    23    150.3 MiB      0.0 MiB       root = Node("root")
    24    180.5 MiB     30.2 MiB       for item in data:
    ...
```

Each call to process() adds ~30MB that never gets freed. Why?''', r'''<think>
Let me analyze this memory leak step by step.

1. The Node class has parent-child circular references: parent points to child, child.parent points back to parent. My first instinct is that circular references are the culprit... but wait, Python's cyclic garbage collector should handle those. Let me look more carefully.

2. Hmm, I initially thought the circular references were the main issue, but actually the critical problem is `TreeProcessor._cache = {}` at the class level. I considered whether this might be an instance variable that gets cleaned up, but no -- it is a class variable (shared across all instances) that persists for the lifetime of the program. Because it is class-level, every TreeProcessor instance shares the same dict, and it never gets garbage collected.

3. Even though the local variable `root` goes out of scope after process() returns, _cache still holds a strong reference to it. This means the root node, all its children, and the circular parent references are all kept alive. I briefly wondered if the circular references would prevent collection even without _cache, but actually Python's cyclic GC can handle simple cycles -- it is the external strong reference from _cache that is the real anchor.

4. The `id(root)` as key is also problematic. Wait, I need to reconsider something here -- could id reuse cause old entries to be overwritten, effectively limiting growth? No, because the cache holds strong references preventing deallocation, so ids are always unique, and the cache grows without bound. If objects were freed, id reuse would be a different bug (stale cache hits), but here they are never freed.

5. I considered using __slots__ as a fix, but actually that only reduces per-object memory overhead -- it does not solve the unbounded growth. Option A (weakref) would allow automatic cleanup but might evict entries too aggressively. Option B (LRU cache with a size limit) is simpler to reason about. Option C (no caching) is safest if the results are not reused. The tradeoff is between memory safety and cache hit rates.

The circular references themselves are not the main problem here -- the unbounded cache is. The circular references just make it harder for gc to collect if there were no external references.
</think>

The memory leak has two contributing factors, but the primary culprit is the unbounded class-level cache.

**Root cause: `TreeProcessor._cache` never releases references**

`_cache` is a class variable (not instance variable), meaning it lives for the entire lifetime of the process. Every call to `process()` adds a root node to this dict, and those entries are never removed. Each root holds references to all its children, and each child holds a back-reference to the root via `parent`. The cache keeps all of this alive permanently.

**Why the circular references matter:**

Python's cyclic GC can collect circular references, but only if there are no external strong references keeping the cycle alive. Here, `_cache` is that external reference. Even if you deleted `_cache`, the circular references would slow down GC because they cannot be collected by simple reference counting -- they require a full GC cycle.

**Fix 1: Use weakref for the cache**

```python
import weakref

class TreeProcessor:
    _cache = weakref.WeakValueDictionary()

    def process(self, data):
        root = Node("root")
        for item in data:
            child = Node(item)
            root.add_child(child)
        TreeProcessor._cache[id(root)] = root
        return self._compute(root)
```

With `WeakValueDictionary`, entries are automatically removed when the root node has no other strong references.

**Fix 2: Use an LRU cache with a size limit**

```python
from functools import lru_cache
from collections import OrderedDict

class TreeProcessor:
    _cache = OrderedDict()
    MAX_CACHE_SIZE = 100

    def process(self, data):
        root = Node("root")
        for item in data:
            child = Node(item)
            root.add_child(child)

        cache_key = hash(tuple(data))
        TreeProcessor._cache[cache_key] = root
        if len(TreeProcessor._cache) > self.MAX_CACHE_SIZE:
            TreeProcessor._cache.popitem(last=False)

        return self._compute(root)
```

**Fix 3: Break circular references explicitly**

If you do need strong caching, break cycles when removing entries:

```python
class Node:
    def __init__(self, value):
        self.value = value
        self.parent = None
        self.children = []

    def destroy(self):
        """Break circular references for GC."""
        self.parent = None
        for child in self.children:
            child.destroy()
        self.children.clear()
```

**Fix 4: Use __slots__ to reduce per-object overhead**

```python
class Node:
    __slots__ = ('value', 'parent', 'children')

    def __init__(self, value):
        self.value = value
        self.parent = None
        self.children = []
```

This reduces memory per Node from ~400 bytes to ~150 bytes by eliminating the per-instance `__dict__`.

**Prevention tips:**
- Never use class-level mutable containers without size limits
- Profile with `tracemalloc` to find allocation hotspots
- Use `objgraph.show_growth()` to detect leaking object types
- Set `gc.set_debug(gc.DEBUG_SAVEALL)` to inspect uncollectable cycles'''),

    ("thinking/debugging", r'''My class has a __del__ method and objects are never getting garbage collected:

```python
import gc

class DatabaseConnection:
    def __init__(self, conn_string):
        self.conn = connect(conn_string)
        self.cursors = []

    def create_cursor(self):
        cursor = Cursor(self)
        self.cursors.append(cursor)
        return cursor

    def __del__(self):
        print(f"Closing connection")
        self.conn.close()

class Cursor:
    def __init__(self, connection):
        self.connection = connection  # back-reference

    def __del__(self):
        print(f"Closing cursor")
        self.connection.cursors.remove(self)
```

After processing, gc.collect() returns objects but the __del__ methods never fire:

```python
gc.set_debug(gc.DEBUG_SAVEALL)
gc.collect()
print(len(gc.garbage))  # prints 24, growing every minute
```

Why are these objects uncollectable?''', r'''<think>
This is a Python GC issue with __del__ and circular references. Let me trace through the problem.

1. DatabaseConnection holds a list of Cursor objects in self.cursors
2. Each Cursor holds a back-reference to the DatabaseConnection in self.connection
3. This creates a circular reference: Connection -> cursors list -> Cursor -> connection -> Connection

My first thought is that this is the pre-3.4 uncollectable cycle problem. In older Python, the garbage collector could not collect cycles that involve objects with __del__ methods, because it could not determine a safe order to call the finalizers. If A references B and both have __del__, should A.__del__ run first or B.__del__? The answer matters because Cursor.__del__ needs the Connection to still be valid.

In Python 3.4+ (PEP 442), this was mostly fixed -- the GC can collect cycles with __del__. But wait, there is still an issue here: the Cursor.__del__ method accesses self.connection.cursors.remove(self). If the Connection is being finalized at the same time, this could access a partially-destroyed object.

Hmm, but the user says gc.garbage has 24 objects. In Python 3.4+, this should mostly work. Let me reconsider... why would gc.garbage grow?

Actually, I just realized something I initially overlooked -- if gc.DEBUG_SAVEALL is set, ALL collected objects are put into gc.garbage instead of being freed. That is the debug flag's entire purpose -- it saves objects for inspection rather than collecting them. So the user might be misinterpreting what gc.garbage means with DEBUG_SAVEALL enabled. The objects could be perfectly collectable, but DEBUG_SAVEALL prevents actual collection. This is ironic -- the debugging tool itself is causing the apparent leak.

I considered whether object resurrection via __del__ could be a factor too, but the simpler explanation (DEBUG_SAVEALL) is more likely. Still, I should cover both the pre-3.4 case and the DEBUG_SAVEALL misunderstanding, because the user has not told us which Python version they are running.
</think>

There are two issues here, and which one matters depends on your Python version.

**Issue 1 (Python < 3.4): Circular references with __del__ are uncollectable**

Before PEP 442 (Python 3.4), the garbage collector refused to collect reference cycles involving objects with `__del__` methods. It could not determine a safe finalization order, so it placed them in `gc.garbage` and gave up. Your Connection-Cursor cycle has both objects defining `__del__`, making them permanently uncollectable.

**Issue 2 (All versions): gc.DEBUG_SAVEALL misleads you**

When you call `gc.set_debug(gc.DEBUG_SAVEALL)`, ALL objects that the GC would normally collect are instead saved to `gc.garbage` for inspection. They are NOT freed. This means your debugging tool is itself causing the leak. Remove `DEBUG_SAVEALL` before measuring.

**Issue 3: Cursor.__del__ accesses the Connection**

`self.connection.cursors.remove(self)` in `Cursor.__del__` is dangerous. During GC finalization, the order in which `__del__` methods run is undefined. If `DatabaseConnection.__del__` runs first and closes the connection, then `Cursor.__del__` tries to access a partially-destroyed object.

**The proper fix -- use context managers instead of __del__:**

```python
class DatabaseConnection:
    def __init__(self, conn_string):
        self.conn = connect(conn_string)
        self.cursors = []

    def create_cursor(self):
        cursor = Cursor(self)
        self.cursors.append(cursor)
        return cursor

    def close(self):
        for cursor in self.cursors:
            cursor.close()
        self.cursors.clear()
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

class Cursor:
    def __init__(self, connection):
        self.connection = weakref.ref(connection)  # weak reference!

    def close(self):
        conn = self.connection()
        if conn is not None:
            try:
                conn.cursors.remove(self)
            except ValueError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

Usage:
```python
with DatabaseConnection("postgres://...") as db:
    with db.create_cursor() as cur:
        cur.execute("SELECT 1")
# Both automatically closed, no __del__ needed
```

**Key changes:**

1. **Replaced `__del__` with explicit `close()` + context manager** -- deterministic cleanup
2. **Used `weakref.ref`** for the Cursor's back-reference to Connection, breaking the cycle
3. **Removed DEBUG_SAVEALL** which was preventing actual collection

**Prevention tips:**
- Avoid `__del__` entirely in modern Python; use `__enter__`/`__exit__` or `atexit`
- If you must use `__del__`, never create circular references in that class
- Use `weakref.ref` or `weakref.proxy` for back-references
- Use `weakref.finalize()` as a safer alternative to `__del__`'''),

    ("thinking/debugging", r'''My Pandas data pipeline is using 10x more memory than expected:

```python
import pandas as pd

def transform_data(df):
    # Add computed columns
    df_filtered = df[df['status'] == 'active']
    df_filtered['full_name'] = df_filtered['first'] + ' ' + df_filtered['last']
    df_filtered['age_group'] = df_filtered['age'].apply(categorize_age)
    df_upper = df_filtered.copy()
    df_upper['full_name'] = df_upper['full_name'].str.upper()
    df_final = df_upper[['id', 'full_name', 'age_group', 'email']]
    return df_final

# Memory usage:
# Input df: 500MB
# Peak during transform_data: 5GB
# Expected: ~1GB
```

The input DataFrame is 500MB but during transformation peak memory hits 5GB. What's causing the bloat?''', r'''<think>
Let me trace through the memory usage at each step. This could be a view-vs-copy issue, or it could be sheer accumulation of intermediates...

1. `df` - 500MB (input)
2. `df_filtered = df[df['status'] == 'active']` - This creates a boolean mask and then a new DataFrame. I initially thought df_filtered might be a VIEW of df (which would share memory), but wait -- boolean indexing always returns a copy in modern pandas. So if 80% of rows are active, this is ~400MB of new memory.
3. `df_filtered['full_name'] = ...` - I considered whether this triggers SettingWithCopyWarning, but since df_filtered is from boolean indexing, it IS a copy, so this is fine. Adds a column to df_filtered.
4. `df_filtered['age_group'] = ...` - Another column added via apply(), which itself creates a temporary Series.
5. `df_upper = df_filtered.copy()` - EXPLICIT copy! Hmm, actually this is unnecessary since df_filtered is already a copy. This is wasted memory. Now we have df + df_filtered + df_upper all in memory simultaneously. That is 500 + 400 + 400 = 1.3GB just for these three.
6. `df_upper['full_name'] = df_upper['full_name'].str.upper()` - str.upper() creates yet another temporary Series internally.
7. `df_final = df_upper[['id', 'full_name', 'age_group', 'email']]` - Another subset copy.

But wait, 1.3GB does not explain the 5GB peak. The real multiplier must be the string operations. Because string columns use Python object dtype, each string is a separate heap-allocated Python object with ~50-100 bytes overhead. The concatenation `first + ' ' + last` creates TWO temporary Series (one for the intermediate `first + ' '`, another for adding `last`). So the hidden temporaries are the real memory amplifier.

The fix involves several tradeoffs: chaining operations avoids intermediates but hurts readability. Using inplace modifications saves memory but makes debugging harder. The best approach is to build the result DataFrame directly from the filtered data, avoiding all intermediates.
</think>

The memory bloat comes from multiple intermediate DataFrames existing simultaneously, unnecessary copies, and inefficient string storage. Let me break down the memory at each step:

```
df                    = 500 MB  (input, stays alive throughout)
df_filtered           = ~400 MB (boolean indexing creates a copy)
df_filtered + columns = ~500 MB (adding full_name and age_group)
df_upper = .copy()    = ~500 MB (EXPLICIT unnecessary copy)
df_final              = ~200 MB (subset of columns)
Peak total            = 500 + 500 + 500 + 200 = ~1.7 GB
```

But the real culprits multiplying this further are:

1. **String columns use `object` dtype** -- each string is a separate Python object on the heap, roughly 50-100 bytes overhead per string
2. **`.apply(categorize_age)`** creates temporary Series
3. **String concatenation** `first + ' ' + last` creates two temporary Series
4. **`.str.upper()`** creates another temporary Series

**Optimized version:**

```python
import pandas as pd

def transform_data(df):
    # Filter first to reduce working set size
    mask = df['status'] == 'active'

    # Build result directly, no intermediate DataFrames
    result = pd.DataFrame({
        'id': df.loc[mask, 'id'],
        'full_name': (df.loc[mask, 'first'] + ' ' + df.loc[mask, 'last']).str.upper(),
        'age_group': df.loc[mask, 'age'].apply(categorize_age),
        'email': df.loc[mask, 'email'],
    })

    return result
```

**Further optimizations for large datasets:**

```python
def transform_data_optimized(df):
    # 1. Use categorical for low-cardinality columns
    df['status'] = df['status'].astype('category')

    # 2. Use string[pyarrow] dtype (pandas 2.0+) for 50-70% less memory
    string_cols = ['first', 'last', 'email']
    for col in string_cols:
        df[col] = df[col].astype('string[pyarrow]')

    # 3. Filter and build result in one pass
    active = df.query("status == 'active'")

    result = pd.DataFrame({
        'id': active['id'].values,
        'full_name': (active['first'] + ' ' + active['last']).str.upper(),
        'age_group': pd.Categorical(active['age'].apply(categorize_age)),
        'email': active['email'].values,
    })

    return result
```

**For truly large datasets, use chunked processing:**

```python
def transform_chunked(filepath, chunksize=50000):
    chunks = []
    for chunk in pd.read_csv(filepath, chunksize=chunksize):
        result = transform_data(chunk)
        chunks.append(result)
    return pd.concat(chunks, ignore_index=True)
```

**Prevention tips:**
- Use `df.info(memory_usage='deep')` to see actual memory including string contents
- Use `memory_profiler` with `@profile` decorator to track per-line memory
- Prefer PyArrow-backed string columns over object dtype
- Delete intermediate DataFrames with `del` and call `gc.collect()` in tight memory situations
- Use `.pipe()` for chaining transformations without storing intermediates'''),

    ("thinking/debugging", r'''I'm getting a memory leak from string interning in a long-running service:

```python
import sys

def process_message(msg):
    key = msg['type']  # e.g., "event_user_login_v2_region_us_east_1"
    interned = sys.intern(key)
    registry[interned] = handler_for(key)
    return interned

# After 48 hours:
# RSS: 4.2 GB
# Expected: ~500 MB
# sys.intern table has 2.3 million entries
```

I was told interning strings saves memory. Why is it doing the opposite?''', r'''<think>
sys.intern() is designed for strings that are used many times -- it stores one canonical copy in an internal dictionary and returns a reference to it. This saves memory when you have millions of references to the same small set of strings. So my first thought was "interning should help"... but wait, let me look at the actual key pattern.

The user's key pattern is "event_user_login_v2_region_us_east_1" -- this looks like it contains dynamic components. I initially assumed these would be a small set of event types, but 2.3 million entries in the intern table tells a different story. If the keys contain user IDs, timestamps, or session identifiers, then nearly every key is unique. Interning unique strings does not save memory at all -- instead, it:

1. Stores every unique string permanently in Python's intern table
2. The intern table is a dict that holds strong references -- strings are never freed even when no other code references them
3. With 2.3 million unique keys, each ~50 chars, that is 2.3M * ~100 bytes = ~230MB just for the strings, plus the dict overhead

I considered whether the registry dict might be the primary leak instead of the intern table, but actually both contribute. The registry maps interned keys to handler objects, also growing without bound. Because the interned strings are never freed, the registry keys are never freed, so the handler objects are never freed either. It is a cascade of retention.

I also thought about whether switching to a WeakValueDictionary for the registry would help, but that alone would not fix the intern table growth. The real fix needs to address both: only intern strings from a known finite set, AND add eviction to the registry. A simpler alternative is to not intern at all and just use an LRU cache for the handlers.
</think>

`sys.intern()` is being misused here. String interning saves memory only when you have many references to the same small set of strings. In your case, the message types contain dynamic components, producing millions of unique strings that are each interned exactly once.

**How sys.intern() works:**

Python maintains an internal dictionary mapping strings to themselves. When you call `sys.intern(s)`, Python checks if an identical string exists in this dict. If yes, it returns the existing one (saving memory when multiple variables reference it). If no, it adds `s` to the dict and returns it.

The intern dict holds **strong references** -- interned strings are never garbage collected, even if no other code references them.

**Why you have 4.2 GB RSS:**

With 2.3 million unique keys:
- Intern table: 2.3M entries * ~100 bytes per string = ~230 MB for strings alone
- Dict overhead for intern table: ~150 MB (hash table with 2.3M entries)
- `registry` dict: another ~150 MB plus the handler objects it references
- Handler objects that are never evicted: potentially gigabytes depending on their size

**The fix:**

```python
# Option 1: Don't intern dynamic strings. Just use them directly.
def process_message(msg):
    key = msg['type']
    registry[key] = handler_for(key)
    return key

# Option 2: Normalize keys to a known finite set
EVENT_TYPES = frozenset([
    "user_login", "user_logout", "page_view",
    "purchase", "error",
])

def process_message(msg):
    raw_key = msg['type']
    # Extract the base event type from the dynamic string
    base_type = extract_event_type(raw_key)  # "user_login"
    if base_type not in EVENT_TYPES:
        base_type = "unknown"
    registry[base_type] = handler_for(base_type)
    return base_type

# Option 3: Use an LRU cache to bound memory
from functools import lru_cache

@lru_cache(maxsize=10000)
def get_handler(key):
    return handler_for(key)

def process_message(msg):
    key = msg['type']
    handler = get_handler(key)
    return handler
```

**When to use sys.intern():**

- Dictionary keys that are always from a small finite set (like JSON field names)
- Attribute names in hot paths
- Identifiers read from config files at startup

**When NOT to use sys.intern():**

- User-generated content or dynamic strings
- Strings containing timestamps, IDs, or session tokens
- Any situation where the set of unique strings grows without bound

**Prevention tips:**
- Monitor `len(sys.intern)` is not possible directly, but you can track your registry size
- Add a maximum size check before interning: `if len(registry) < MAX_ENTRIES`
- Use `weakref.WeakValueDictionary` for caches that should allow GC
- Profile with `tracemalloc.get_traced_memory()` to catch gradual growth early'''),

    ("thinking/debugging", r'''My application is leaking memory through mmap and the process RSS keeps growing:

```python
import mmap
import os

def read_record(filepath, offset, length):
    fd = os.open(filepath, os.O_RDONLY)
    mm = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
    data = mm[offset:offset + length]
    os.close(fd)
    return data

# Called millions of times per hour
# /proc/self/status shows:
# VmRSS:   8234512 kB  (8GB!)
# VmSize: 92341232 kB  (92GB virtual!)
```

The virtual memory is 92GB despite the files being only 2GB total. What's happening?''', r'''<think>
The problem looks straightforward at first glance: `mm = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)` creates a memory mapping, and `os.close(fd)` closes the file descriptor, but the mmap object `mm` is NEVER explicitly closed.

When you call mmap.mmap(), the kernel creates a virtual memory mapping for the file. Each call creates a new mapping. Even though `os.close(fd)` closes the file descriptor, the memory mapping remains valid -- the kernel keeps the file reference alive through the mapping itself.

But wait, I need to reconsider something. When the function returns, `mm` goes out of scope, and CPython's reference counting should immediately drop the refcount to zero and unmap it. So why would mappings accumulate?

Hmm, actually there could be several reasons. First, this function is called millions of times per hour. Under high load, the rate of new mmap allocations might exceed the rate of GC cleanup, especially if there is any delay in reference counting (e.g., temporary references in the call stack, debug traces, or exception handling). Second, if running on PyPy instead of CPython, there is no deterministic reference counting at all -- objects are only freed during GC sweeps.

I also initially overlooked that `length=0` means map the ENTIRE file. If the files are 2GB total and there are multiple files, each call creates a multi-hundred-MB or multi-GB virtual mapping just to read a small slice. After just 46 calls to a 2GB file, you would have 92GB of virtual mappings. That is extremely wasteful.

I considered whether the right fix is just adding mm.close(), but actually the better question is: why use mmap at all for small reads? Regular file I/O with seek() has zero virtual memory overhead. mmap makes sense for repeated random access to the same file, but creating a new mapping per read defeats the purpose entirely. The tradeoff is: a single reusable mmap per file is fast for random access, but a new mmap per read is worse than simple file I/O.
</think>

The `mmap` object is never explicitly closed. Each call to `read_record()` creates a new memory mapping of the entire file but never calls `mm.close()`. While CPython's reference counting will eventually clean up the mmap when `mm` goes out of scope, this is not guaranteed to happen immediately, and in practice under high load, mappings accumulate faster than they are collected.

**Key problems:**

1. **`mmap.mmap(fd, 0)`** maps the ENTIRE file (length=0 means whole file). If the file is 2GB, each call creates a 2GB virtual mapping
2. **No `mm.close()`** -- the mapping persists until GC collects the mmap object
3. **Millions of calls** = millions of concurrent mappings before GC catches up
4. **`os.close(fd)` does NOT close the mmap** -- the kernel maintains the mapping independently of the file descriptor

**Fix 1: Proper cleanup with context manager**

```python
def read_record(filepath, offset, length):
    with open(filepath, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            data = mm[offset:offset + length]
    return data
```

**Fix 2: Don't use mmap for small reads (much better)**

```python
def read_record(filepath, offset, length):
    with open(filepath, 'rb') as f:
        f.seek(offset)
        data = f.read(length)
    return data
```

For reading a small slice from a known offset, regular file I/O with seek is more appropriate and has no virtual memory overhead.

**Fix 3: Reuse a single mmap per file (best for repeated access)**

```python
import mmap
from functools import lru_cache

class FileReader:
    def __init__(self):
        self._mappings = {}

    def read_record(self, filepath, offset, length):
        if filepath not in self._mappings:
            fd = os.open(filepath, os.O_RDONLY)
            mm = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
            self._mappings[filepath] = (fd, mm)
        _, mm = self._mappings[filepath]
        return mm[offset:offset + length]

    def close(self):
        for fd, mm in self._mappings.values():
            mm.close()
            os.close(fd)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

This creates one mapping per file instead of millions.

**Why virtual memory is 92GB but RSS is only 8GB:**

The kernel is lazy about actually loading pages into physical memory. Virtual mappings reserve address space but physical pages are only allocated when accessed (page faults). The 8GB RSS represents pages that were actually touched. On a 64-bit system, the 92GB virtual space is not inherently problematic, but it wastes page table entries and can cause issues if overcommit is disabled.

**Prevention tips:**
- Always use mmap as a context manager
- Prefer regular file I/O for small, targeted reads
- Reuse mmap objects for files accessed repeatedly
- Monitor `/proc/self/maps` to count active mappings
- Set a process virtual memory limit with `resource.setrlimit(resource.RLIMIT_AS, ...)`'''),
]
