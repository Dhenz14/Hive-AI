PAIRS = [
    (
        "memory/rust-ownership-borrowing-lifetimes",
        "Explain Rust ownership system internals including the borrow checker algorithm, lifetime annotations and elision rules, interior mutability with Cell and RefCell, and smart pointers Rc Arc Mutex with practical patterns for common ownership challenges",
        r"""# Rust Ownership, Borrowing, and Lifetimes Deep Dive

## The Ownership Model: Compile-Time Memory Safety

Rust's ownership system eliminates use-after-free, double-free, and data races at **compile time** with zero runtime overhead. This is fundamentally different from garbage collection **because** GC adds runtime pauses and memory overhead, while Rust's borrow checker runs only during compilation. **Therefore**, Rust achieves C-level performance with memory safety guarantees.

### Ownership Rules and Move Semantics

```rust
// --- Ownership fundamentals ---
// Rule 1: Each value has exactly one owner
// Rule 2: When the owner goes out of scope, the value is dropped
// Rule 3: Ownership can be transferred (moved) or borrowed

// Best practice: prefer borrowing over cloning
// Common mistake: cloning everything to "make it compile"

struct Document {
    title: String,
    content: String,
    metadata: Vec<(String, String)>,
}

impl Document {
    // Takes ownership — caller can no longer use the Document
    fn into_bytes(self) -> Vec<u8> {
        // self is consumed — dropped after this function
        format!("{}\n{}", self.title, self.content).into_bytes()
    }

    // Borrows immutably — multiple readers allowed
    fn word_count(&self) -> usize {
        self.content.split_whitespace().count()
    }

    // Borrows mutably — exclusive access required
    fn append(&mut self, text: &str) {
        self.content.push_str(text);
    }

    // Returns a reference tied to self's lifetime
    // Therefore, the returned &str cannot outlive the Document
    fn title_ref(&self) -> &str {
        &self.title
    }
}

// --- Lifetime annotations ---
// Lifetimes tell the compiler how long references are valid
// Pitfall: fighting the borrow checker instead of restructuring code

// Explicit lifetime: both inputs must live at least as long as output
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

// Struct containing references needs lifetime annotations
struct Parser<'input> {
    source: &'input str,
    position: usize,
}

impl<'input> Parser<'input> {
    fn new(source: &'input str) -> Self {
        Parser { source, position: 0 }
    }

    // Return value's lifetime is tied to 'input
    fn next_word(&mut self) -> Option<&'input str> {
        let remaining = &self.source[self.position..];
        let trimmed = remaining.trim_start();
        if trimmed.is_empty() {
            return None;
        }
        let end = trimmed.find(char::is_whitespace).unwrap_or(trimmed.len());
        let start = self.source.len() - remaining.len()
            + (remaining.len() - trimmed.len());
        self.position = start + end;
        Some(&self.source[start..start + end])
    }
}

// Lifetime elision rules (compiler infers lifetimes):
// 1. Each reference param gets its own lifetime
// 2. If exactly one input lifetime, it's assigned to all outputs
// 3. If &self or &mut self, self's lifetime is assigned to outputs

// These two signatures are identical:
// fn first_word(s: &str) -> &str
// fn first_word<'a>(s: &'a str) -> &'a str

fn main() {
    let mut doc = Document {
        title: String::from("Rust Guide"),
        content: String::from("Memory safety without garbage collection"),
        metadata: vec![],
    };

    // Immutable borrows — multiple allowed simultaneously
    let title = doc.title_ref();
    let count = doc.word_count();
    println!("{}: {} words", title, count);

    // Mutable borrow — exclusive, no other borrows allowed
    doc.append(". Zero-cost abstractions.");
    println!("Updated: {} words", doc.word_count());

    // Move — doc is consumed, can't use it after this
    let bytes = doc.into_bytes();
    // println!("{}", doc.title); // COMPILE ERROR: use after move
    println!("Serialized: {} bytes", bytes.len());
}
```

### Interior Mutability and Smart Pointers

**However**, sometimes you need mutation through shared references — for example, a cache that's logically immutable but lazily populates. Rust provides **interior mutability** types that enforce borrowing rules at runtime instead of compile time. The **trade-off** is moving from compile-time to runtime checking.

```rust
use std::cell::{Cell, RefCell};
use std::rc::Rc;
use std::sync::{Arc, Mutex, RwLock};

// --- Cell: for Copy types, zero-overhead interior mutability ---

struct Counter {
    count: Cell<u32>, // Can mutate through &self
}

impl Counter {
    fn new() -> Self {
        Counter { count: Cell::new(0) }
    }

    fn increment(&self) {
        // No &mut self needed — Cell provides interior mutability
        // Trade-off: Cell only works for Copy types
        self.count.set(self.count.get() + 1);
    }

    fn get(&self) -> u32 {
        self.count.get()
    }
}

// --- RefCell: runtime borrow checking for non-Copy types ---

struct Cache {
    data: RefCell<std::collections::HashMap<String, String>>,
    hits: Cell<u64>,
    misses: Cell<u64>,
}

impl Cache {
    fn new() -> Self {
        Cache {
            data: RefCell::new(std::collections::HashMap::new()),
            hits: Cell::new(0),
            misses: Cell::new(0),
        }
    }

    fn get(&self, key: &str) -> Option<String> {
        // borrow() panics if already mutably borrowed
        // Common mistake: holding RefCell borrows across await points
        let data = self.data.borrow();
        match data.get(key) {
            Some(val) => {
                self.hits.set(self.hits.get() + 1);
                Some(val.clone())
            }
            None => {
                self.misses.set(self.misses.get() + 1);
                None
            }
        }
    }

    fn insert(&self, key: String, value: String) {
        // borrow_mut() panics if any borrow is active
        // Pitfall: calling get() then insert() while holding the borrow
        self.data.borrow_mut().insert(key, value);
    }
}

// --- Rc: shared ownership (single-threaded) ---

#[derive(Debug)]
struct Node {
    value: i32,
    // Rc allows multiple owners — reference counted
    // However, Rc is NOT thread-safe (use Arc for threads)
    children: Vec<Rc<Node>>,
}

fn build_tree() -> Rc<Node> {
    let shared_child = Rc::new(Node {
        value: 42,
        children: vec![],
    });

    // Multiple parents can own the same child
    let parent1 = Rc::new(Node {
        value: 1,
        children: vec![Rc::clone(&shared_child)],
    });

    let parent2 = Rc::new(Node {
        value: 2,
        children: vec![Rc::clone(&shared_child)],
    });

    println!("Reference count: {}", Rc::strong_count(&shared_child)); // 3

    parent1
}

// --- Arc + Mutex: thread-safe shared mutable state ---

struct SharedState {
    // Arc<Mutex<T>> is the standard pattern for shared mutable state
    // Best practice: hold the lock for as short as possible
    counter: Arc<Mutex<u64>>,
    config: Arc<RwLock<std::collections::HashMap<String, String>>>,
}

impl SharedState {
    fn new() -> Self {
        SharedState {
            counter: Arc::new(Mutex::new(0)),
            config: Arc::new(RwLock::new(std::collections::HashMap::new())),
        }
    }

    fn increment(&self) {
        // lock() blocks until mutex is available
        // Pitfall: holding lock across async .await causes deadlocks
        // Therefore, use tokio::sync::Mutex for async code
        let mut count = self.counter.lock().unwrap();
        *count += 1;
        // Lock is released when `count` goes out of scope (Drop trait)
    }

    fn get_config(&self, key: &str) -> Option<String> {
        // RwLock allows multiple readers OR one writer
        // Trade-off: more overhead than Mutex but better for read-heavy workloads
        let config = self.config.read().unwrap();
        config.get(key).cloned()
    }

    fn set_config(&self, key: String, value: String) {
        let mut config = self.config.write().unwrap();
        config.insert(key, value);
    }
}
```

### Common Ownership Patterns

Understanding when to use each smart pointer is essential for productive Rust development.

```rust
// --- Decision guide for ownership ---

// 1. Single owner, stack allocation: just use the value directly
//    let x = String::from("hello");

// 2. Transfer ownership: move (default for non-Copy types)
//    fn process(s: String) { ... }

// 3. Temporary access: borrow with &T or &mut T
//    fn analyze(s: &str) -> usize { s.len() }

// 4. Shared ownership, single thread: Rc<T>
//    Multiple parts of code need to own the same data

// 5. Shared ownership, multi-thread: Arc<T>
//    Same as Rc but with atomic reference counting

// 6. Shared mutable state, single thread: Rc<RefCell<T>>
//    Multiple owners that also need to mutate

// 7. Shared mutable state, multi-thread: Arc<Mutex<T>> or Arc<RwLock<T>>
//    Read-heavy: RwLock, write-heavy: Mutex

// --- Cow (Clone on Write): avoid unnecessary cloning ---

use std::borrow::Cow;

fn normalize_name(name: &str) -> Cow<'_, str> {
    // Only allocates if modification is needed
    // Therefore, borrowed data passes through without copying
    if name.contains(char::is_uppercase) {
        // Need to modify — clone and return owned
        Cow::Owned(name.to_lowercase())
    } else {
        // No modification needed — return borrowed reference
        Cow::Borrowed(name)
    }
}

// --- Error pattern: self-referential structs ---
// Pitfall: Rust cannot express structs that reference themselves
// because moves would invalidate the reference

// This WON'T compile:
// struct SelfRef {
//     data: String,
//     slice: &str, // Can't reference data
// }

// Solutions:
// 1. Use indices instead of references
struct Buffer {
    data: Vec<u8>,
    // Store offsets, not references
    segments: Vec<(usize, usize)>, // (start, end)
}

impl Buffer {
    fn get_segment(&self, idx: usize) -> &[u8] {
        let (start, end) = self.segments[idx];
        &self.data[start..end]
    }
}

// 2. Use Pin for self-referential async futures
// The compiler handles this automatically for async/await

// 3. Use ouroboros or self_cell crates for advanced cases
```

## Summary and Key Takeaways

- **Ownership** ensures exactly one owner per value — moves transfer ownership, borrows provide temporary access
- **Lifetime annotations** tell the compiler how long references are valid — most are inferred via elision rules
- A **common mistake** is fighting the borrow checker by cloning everything — restructure code to use references instead
- **`Cell<T>`** for Copy types, **`RefCell<T>`** for non-Copy types — both provide interior mutability with different trade-offs
- **`Rc<T>`** for single-threaded shared ownership, **`Arc<T>`** for multi-threaded — the difference is atomic vs non-atomic reference counting
- The **pitfall** of `Arc<Mutex<T>>` in async code is holding the lock across `.await` points — use `tokio::sync::Mutex` instead
- **`Cow<'_, T>`** avoids unnecessary cloning when data might or might not need modification
- **Best practice**: prefer `&T` borrows over `Rc/Arc` whenever possible — smart pointers add overhead and complexity"""
    ),
    (
        "memory/garbage-collection-algorithms-comparison",
        "Compare garbage collection algorithms including mark-sweep, mark-compact, generational collection, concurrent collectors like G1 and ZGC, reference counting with cycle detection, and region-based memory management with implementation details and performance trade-offs",
        r"""# Garbage Collection Algorithms: A Deep Comparison

## Why GC Algorithm Choice Matters

Garbage collection strategy directly impacts application **latency**, **throughput**, and **memory overhead**. A web server with a stop-the-world collector might have 99th percentile latencies of 500ms+, while the same server with a concurrent collector stays under 10ms. **Because** modern applications have diverse requirements — real-time gaming, financial trading, batch processing — understanding GC trade-offs is essential for choosing the right runtime and tuning it.

### Mark-Sweep and Mark-Compact

```python
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
import time

# --- Mark-Sweep Garbage Collector ---

@dataclass
class GCObject:
    obj_id: int
    size: int  # bytes
    marked: bool = False
    references: list[int] = field(default_factory=list)  # IDs of referenced objects

class MarkSweepGC:
    # Simplest tracing GC: mark reachable objects, sweep unmarked
    # Trade-off: simple but causes fragmentation
    # Best practice: understand mark-sweep as the foundation for all tracing GCs

    def __init__(self, heap_size: int = 1024 * 1024):
        self.heap_size = heap_size
        self.used = 0
        self.objects: dict[int, GCObject] = {}
        self.roots: set[int] = set()  # Root references (stack, globals)
        self._next_id = 0
        self.stats = {"collections": 0, "freed_bytes": 0, "freed_objects": 0}

    def allocate(self, size: int) -> Optional[int]:
        if self.used + size > self.heap_size:
            self.collect()  # Try to free space
            if self.used + size > self.heap_size:
                return None  # Out of memory

        obj_id = self._next_id
        self._next_id += 1
        self.objects[obj_id] = GCObject(obj_id=obj_id, size=size)
        self.used += size
        return obj_id

    def add_reference(self, from_id: int, to_id: int) -> None:
        if from_id in self.objects and to_id in self.objects:
            self.objects[from_id].references.append(to_id)

    def add_root(self, obj_id: int) -> None:
        self.roots.add(obj_id)

    def remove_root(self, obj_id: int) -> None:
        self.roots.discard(obj_id)

    def collect(self) -> dict:
        start = time.perf_counter()

        # Phase 1: Mark — trace from roots
        # Therefore, any object not reachable from roots is garbage
        for obj in self.objects.values():
            obj.marked = False

        # DFS from roots
        stack = list(self.roots)
        while stack:
            obj_id = stack.pop()
            obj = self.objects.get(obj_id)
            if obj is None or obj.marked:
                continue
            obj.marked = True
            stack.extend(obj.references)

        # Phase 2: Sweep — free unmarked objects
        freed_bytes = 0
        freed_count = 0
        to_remove = []

        for obj_id, obj in self.objects.items():
            if not obj.marked:
                freed_bytes += obj.size
                freed_count += 1
                to_remove.append(obj_id)

        for obj_id in to_remove:
            del self.objects[obj_id]
        self.used -= freed_bytes

        elapsed = time.perf_counter() - start
        self.stats["collections"] += 1
        self.stats["freed_bytes"] += freed_bytes
        self.stats["freed_objects"] += freed_count

        return {
            "freed_bytes": freed_bytes,
            "freed_objects": freed_count,
            "pause_ms": elapsed * 1000,
            "heap_used": self.used,
            "heap_total": self.heap_size,
        }

# --- Mark-Compact: eliminates fragmentation ---
# However, compaction requires updating all references (expensive)

class MarkCompactGC(MarkSweepGC):
    # After marking, compact live objects to eliminate fragmentation
    # Common mistake: using mark-sweep for long-running servers
    # where fragmentation grows over time

    def collect(self) -> dict:
        result = super().collect()

        # Compact phase: move live objects to fill gaps
        # Pitfall: must update ALL references to moved objects
        compact_start = time.perf_counter()

        # Reassign contiguous IDs (simulating address compaction)
        old_to_new: dict[int, int] = {}
        new_objects: dict[int, GCObject] = {}
        new_id = 0

        for old_id in sorted(self.objects.keys()):
            old_to_new[old_id] = new_id
            obj = self.objects[old_id]
            obj.obj_id = new_id
            new_objects[new_id] = obj
            new_id += 1

        # Update all references
        for obj in new_objects.values():
            obj.references = [
                old_to_new[ref_id] for ref_id in obj.references
                if ref_id in old_to_new
            ]

        # Update roots
        self.roots = {old_to_new[r] for r in self.roots if r in old_to_new}
        self.objects = new_objects
        self._next_id = new_id

        compact_ms = (time.perf_counter() - compact_start) * 1000
        result["compact_ms"] = compact_ms
        result["total_pause_ms"] = result["pause_ms"] + compact_ms
        return result
```

### Generational and Concurrent Collectors

The **generational hypothesis** states that most objects die young. **Therefore**, dividing the heap into generations (young, old) and collecting the young generation frequently is much more efficient than collecting everything every time.

```python
# --- Generational Garbage Collector ---

class GenerationalGC:
    # Young generation: small, collected frequently (minor GC)
    # Old generation: large, collected rarely (major GC)
    # Trade-off: fast minor GCs but need write barriers for cross-gen references

    def __init__(
        self,
        young_size: int = 256 * 1024,
        old_size: int = 1024 * 1024,
        promotion_threshold: int = 3,
    ):
        self.young = {"objects": {}, "used": 0, "size": young_size}
        self.old = {"objects": {}, "used": 0, "size": old_size}
        self.promotion_threshold = promotion_threshold
        self.roots: set[int] = set()
        self._next_id = 0
        # Write barrier: track old->young references
        # Best practice: use card table for efficient write barrier
        self.remembered_set: set[int] = set()  # Old objects pointing to young
        self.stats = {"minor_gcs": 0, "major_gcs": 0, "promotions": 0}

    def allocate(self, size: int) -> Optional[int]:
        # Always allocate in young generation
        if self.young["used"] + size > self.young["size"]:
            self.minor_gc()
            if self.young["used"] + size > self.young["size"]:
                self.major_gc()
                if self.young["used"] + size > self.young["size"]:
                    return None

        obj_id = self._next_id
        self._next_id += 1
        self.young["objects"][obj_id] = GCObject(obj_id=obj_id, size=size)
        self.young["used"] += size
        return obj_id

    def write_barrier(self, from_id: int, to_id: int) -> None:
        # Called whenever a reference is updated
        # If old object references young object, add to remembered set
        # Therefore, minor GC can find all old->young references
        if from_id in self.old["objects"] and to_id in self.young["objects"]:
            self.remembered_set.add(from_id)
        # Update reference
        all_objects = {**self.young["objects"], **self.old["objects"]}
        if from_id in all_objects and to_id in all_objects:
            all_objects[from_id].references.append(to_id)

    def minor_gc(self) -> dict:
        # Only collect young generation
        # Roots = stack roots + remembered set (old->young refs)
        start = time.perf_counter()

        # Mark from roots + remembered set
        mark_roots = self.roots | self.remembered_set
        reachable = self._mark(mark_roots, include_old=True)

        # Sweep young generation
        freed = 0
        to_remove = []
        to_promote = []

        for obj_id, obj in self.young["objects"].items():
            if obj_id not in reachable:
                freed += obj.size
                to_remove.append(obj_id)
            else:
                # Survived — check promotion threshold
                # Pitfall: promoting too eagerly fills old gen
                obj.marked = False  # Reset for next GC
                # Simplified: promote after surviving N collections
                to_promote.append(obj_id)

        # Remove garbage
        for obj_id in to_remove:
            del self.young["objects"][obj_id]
        self.young["used"] -= freed

        # Promote survivors to old generation
        for obj_id in to_promote:
            obj = self.young["objects"].pop(obj_id)
            self.old["objects"][obj_id] = obj
            self.young["used"] -= obj.size
            self.old["used"] += obj.size
            self.stats["promotions"] += 1

        self.remembered_set.clear()
        self.stats["minor_gcs"] += 1

        return {
            "type": "minor",
            "freed_bytes": freed,
            "promoted": len(to_promote),
            "pause_ms": (time.perf_counter() - start) * 1000,
        }

    def major_gc(self) -> dict:
        # Full heap collection — expensive but thorough
        start = time.perf_counter()
        reachable = self._mark(self.roots, include_old=True)

        freed = 0
        for gen in [self.young, self.old]:
            to_remove = [
                oid for oid in gen["objects"] if oid not in reachable
            ]
            for oid in to_remove:
                freed += gen["objects"][oid].size
                del gen["objects"][oid]
            gen["used"] -= sum(
                gen["objects"].get(oid, GCObject(0, 0)).size
                for oid in to_remove
                if oid in gen["objects"]
            )

        self.stats["major_gcs"] += 1

        return {
            "type": "major",
            "freed_bytes": freed,
            "pause_ms": (time.perf_counter() - start) * 1000,
        }

    def _mark(self, roots: set[int], include_old: bool = False) -> set[int]:
        all_objects = {**self.young["objects"]}
        if include_old:
            all_objects.update(self.old["objects"])

        reachable: set[int] = set()
        stack = [r for r in roots if r in all_objects]

        while stack:
            obj_id = stack.pop()
            if obj_id in reachable:
                continue
            reachable.add(obj_id)
            obj = all_objects.get(obj_id)
            if obj:
                for ref_id in obj.references:
                    if ref_id in all_objects and ref_id not in reachable:
                        stack.append(ref_id)

        return reachable
```

### Modern Concurrent Collectors

Modern JVM collectors (G1, ZGC, Shenandoah) perform most work concurrently with the application. **However**, concurrent collection introduces complexity: the mutator (application) can modify the heap while the collector is tracing it. This requires **tri-color marking** and read/write barriers.

```python
# --- Concurrent collector concepts ---

class TriColor(Enum):
    WHITE = "white"   # Not yet visited — potentially garbage
    GRAY = "gray"     # Visited but references not scanned
    BLACK = "black"   # Visited and all references scanned

class ConcurrentCollectorSim:
    # Simulates concurrent mark with tri-color invariant
    # Invariant: no black object points to a white object
    # Common mistake: thinking concurrent means "no pauses"
    # — there are still short stop-the-world pauses for root scanning

    def __init__(self):
        self.objects: dict[int, GCObject] = {}
        self.colors: dict[int, TriColor] = {}
        self.roots: set[int] = set()
        # Snapshot-at-the-beginning barrier (used by G1, Shenandoah)
        self.write_barrier_log: list[tuple[int, int]] = []

    def concurrent_mark(self) -> dict:
        # Phase 1: Initial mark (STW pause — scan roots only)
        stw_start = time.perf_counter()

        for oid in self.objects:
            self.colors[oid] = TriColor.WHITE

        gray_set: set[int] = set()
        for root_id in self.roots:
            if root_id in self.objects:
                self.colors[root_id] = TriColor.GRAY
                gray_set.add(root_id)

        initial_pause_ms = (time.perf_counter() - stw_start) * 1000

        # Phase 2: Concurrent mark (runs alongside application)
        # Trade-off: uses CPU cycles but doesn't pause the app
        mark_start = time.perf_counter()

        while gray_set:
            obj_id = gray_set.pop()
            obj = self.objects.get(obj_id)
            if obj is None:
                continue

            for ref_id in obj.references:
                if ref_id in self.objects and self.colors.get(ref_id) == TriColor.WHITE:
                    self.colors[ref_id] = TriColor.GRAY
                    gray_set.add(ref_id)

            self.colors[obj_id] = TriColor.BLACK

        mark_time_ms = (time.perf_counter() - mark_start) * 1000

        # Phase 3: Remark (STW pause — process write barrier log)
        remark_start = time.perf_counter()

        for from_id, to_id in self.write_barrier_log:
            if self.colors.get(to_id) == TriColor.WHITE:
                self.colors[to_id] = TriColor.GRAY
                # Re-scan this reference
                gray_set.add(to_id)

        while gray_set:
            obj_id = gray_set.pop()
            obj = self.objects.get(obj_id)
            if obj:
                for ref_id in obj.references:
                    if self.colors.get(ref_id) == TriColor.WHITE:
                        self.colors[ref_id] = TriColor.GRAY
                        gray_set.add(ref_id)
                self.colors[obj_id] = TriColor.BLACK

        self.write_barrier_log.clear()
        remark_pause_ms = (time.perf_counter() - remark_start) * 1000

        # Count garbage (white objects)
        garbage = [oid for oid, color in self.colors.items() if color == TriColor.WHITE]

        return {
            "initial_pause_ms": initial_pause_ms,
            "concurrent_mark_ms": mark_time_ms,
            "remark_pause_ms": remark_pause_ms,
            "total_stw_ms": initial_pause_ms + remark_pause_ms,
            "garbage_count": len(garbage),
            "live_count": len(self.objects) - len(garbage),
        }

    def snapshot_write_barrier(self, from_id: int, old_ref: int, new_ref: int) -> None:
        # SATB: log the old reference being overwritten
        # Therefore, if the old reference was the only path to an object,
        # we won't lose it during concurrent marking
        self.write_barrier_log.append((from_id, old_ref))

# --- GC comparison table ---

GC_COMPARISON = {
    "mark_sweep": {
        "pause_type": "stop-the-world",
        "throughput": "high",
        "latency": "high (proportional to heap size)",
        "fragmentation": "yes — free list allocation",
        "use_case": "batch processing, non-interactive",
    },
    "mark_compact": {
        "pause_type": "stop-the-world",
        "throughput": "medium (compaction overhead)",
        "latency": "high but consistent",
        "fragmentation": "no — bump pointer allocation",
        "use_case": "long-running servers",
    },
    "generational": {
        "pause_type": "minor STW + occasional major STW",
        "throughput": "very high",
        "latency": "low for minor GC, high for major",
        "fragmentation": "depends on old gen strategy",
        "use_case": "general purpose (most JVMs default)",
    },
    "G1": {
        "pause_type": "mixed (mostly concurrent + short STW)",
        "throughput": "good",
        "latency": "configurable target (e.g., 200ms)",
        "fragmentation": "region-based, periodic compaction",
        "use_case": "large heaps (4GB+), balanced latency/throughput",
    },
    "ZGC": {
        "pause_type": "sub-millisecond STW (root scanning only)",
        "throughput": "good (colored pointers overhead)",
        "latency": "ultra-low (<1ms pauses regardless of heap size)",
        "fragmentation": "region-based with concurrent compaction",
        "use_case": "latency-critical (trading, gaming, real-time)",
    },
}
```

## Summary and Key Takeaways

- **Mark-sweep** is simple but causes fragmentation — use for short-lived programs or as a fallback
- **Generational GC** exploits the fact that most objects die young — minor collections are fast and frequent
- A **common mistake** is not understanding write barriers — they're essential for generational and concurrent collectors
- **G1** provides configurable pause targets and works well for heaps 4GB+ — the JVM default since Java 9
- **ZGC** achieves sub-millisecond pauses regardless of heap size by using colored pointers and concurrent relocation
- The **trade-off** of concurrent collectors: they use 10-15% more CPU but avoid long pauses that affect user experience
- The **pitfall** of reference counting is cycles — Python/Swift use reference counting with cycle detection as backup
- **Best practice**: choose GC based on workload — throughput-first for batch, latency-first for interactive, memory-first for constrained"""
    ),
]
