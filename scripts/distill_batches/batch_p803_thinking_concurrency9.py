"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 9)

Lock-free data structures, compare-and-swap (CAS) operations, atomic operations,
and wait-free algorithms for high-performance concurrent access.
"""

PAIRS = [
    (
        "thinking/concurrency-cas-counter",
        r'''We have a high-throughput metrics counter that's losing updates under contention.
The lock-based version is too slow:

```python
import threading

class MetricsCounter:
    def __init__(self):
        self._lock = threading.Lock()
        self._counts = {}

    def increment(self, key: str, amount: int = 1):
        with self._lock:  # all threads serialize here
            self._counts[key] = self._counts.get(key, 0) + amount

    def get(self, key: str) -> int:
        with self._lock:
            return self._counts.get(key, 0)
```

With 100 threads incrementing different keys, they all contend on the same lock.
How do we make this lock-free or reduce contention?''',
        r'''<think>
The problem: a single global lock means all threads serialize, even when they're
updating different keys. This is unnecessary contention.

Approaches to reduce contention:
1. **Striped locking** — hash keys to N separate locks (reduces contention by N)
2. **Per-key locking** — one lock per key (eliminates cross-key contention)
3. **CAS-based atomic increment** — no locks at all
4. **Thread-local counters** — each thread has its own counter, merge on read
5. **concurrent.futures / atomic integers** — language-level support

In Python specifically:
- The GIL makes simple dict operations atomic for CPython, but that's an implementation
  detail we shouldn't rely on
- `threading.Lock` contention is real even with GIL — acquiring a contested lock involves
  OS-level synchronization
- For pure counters, we can use `collections.Counter` with thread-local storage

For a truly lock-free CAS approach (more relevant in languages without GIL):
- Read current value
- Compute new value
- Atomically swap if unchanged (compare-and-swap)
- Retry if another thread modified it

Let me show both the practical Python solution and the conceptual CAS approach.
</think>

## Solution 1: Striped Locking (Practical Python)

```python
import threading
from collections import defaultdict

class StripedCounter:
    """Reduces contention by hashing keys to separate lock stripes."""

    def __init__(self, num_stripes: int = 64):
        self._num_stripes = num_stripes
        self._locks = [threading.Lock() for _ in range(num_stripes)]
        self._counts = defaultdict(int)

    def _get_stripe(self, key: str) -> int:
        return hash(key) % self._num_stripes

    def increment(self, key: str, amount: int = 1):
        stripe = self._get_stripe(key)
        with self._locks[stripe]:
            self._counts[key] += amount

    def get(self, key: str) -> int:
        stripe = self._get_stripe(key)
        with self._locks[stripe]:
            return self._counts[key]
```

## Solution 2: Thread-Local Counters (Highest Throughput)

```python
import threading
from collections import Counter

class ShardedCounter:
    """Each thread has its own counter. Merge on read. Zero contention on write."""

    def __init__(self):
        self._local = threading.local()
        self._shards = []  # references to all thread-local counters
        self._shards_lock = threading.Lock()

    def _get_local_counter(self) -> Counter:
        if not hasattr(self._local, 'counter'):
            self._local.counter = Counter()
            with self._shards_lock:
                self._shards.append(self._local.counter)
        return self._local.counter

    def increment(self, key: str, amount: int = 1):
        # No lock needed — each thread writes to its own Counter
        self._get_local_counter()[key] += amount

    def get(self, key: str) -> int:
        # Merge all shards (read is slower, but writes are lock-free)
        total = 0
        with self._shards_lock:
            for shard in self._shards:
                total += shard.get(key, 0)
        return total

    def get_all(self) -> Counter:
        merged = Counter()
        with self._shards_lock:
            for shard in self._shards:
                merged.update(shard)
        return merged
```

## Solution 3: CAS Loop (Conceptual / C-like Languages)

```python
import ctypes
import threading

class CASCounter:
    """Demonstrates CAS (compare-and-swap) loop pattern.

    In real systems, use std::atomic (C++), AtomicInteger (Java),
    or sync/atomic (Go). Python's GIL makes true CAS unnecessary,
    but the pattern is fundamental.
    """

    def __init__(self):
        self._values = {}
        # In a real lock-free implementation, each slot would be an atomic int

    def increment(self, key: str, amount: int = 1):
        while True:
            old_value = self._values.get(key, 0)  # Read
            new_value = old_value + amount           # Compute
            # CAS: only update if no one else changed it
            if self._cas(key, old_value, new_value): # Swap if unchanged
                return new_value
            # Another thread changed it — retry (spin)

    def _cas(self, key, expected, desired) -> bool:
        """Simulated CAS — real implementations use CPU instructions."""
        # In C++: std::atomic::compare_exchange_weak
        # In Java: AtomicInteger.compareAndSet
        # In Go: atomic.CompareAndSwapInt64
        current = self._values.get(key, 0)
        if current == expected:
            self._values[key] = desired
            return True
        return False
```

**Contention comparison with 100 threads, 10 keys:**

| Approach | Lock Contention | Write Speed | Read Speed |
|----------|----------------|-------------|------------|
| Single lock | 100 threads contend | Slow | Slow |
| 64 stripes | ~1.6 threads/stripe | 50-60x faster | Fast |
| Thread-local | Zero on write | Fastest | Slower (merge) |
| CAS loop | No locks, spin on conflict | Fast (low contention) | Fast |'''
    ),
    (
        "thinking/concurrency-lock-free-queue",
        r'''I need a thread-safe queue for a high-performance logging system. The standard
`queue.Queue` uses a mutex and condition variables, which causes contention with many
producer threads. Can you explain how a lock-free queue works and when it's appropriate?

```python
# Current approach — contention at high throughput
import queue

log_queue = queue.Queue(maxsize=10000)

def log_message(msg):
    try:
        log_queue.put_nowait(msg)
    except queue.Full:
        pass  # drop message

def consumer():
    while True:
        msg = log_queue.get()
        write_to_file(msg)
```''',
        r'''<think>
Lock-free queue algorithms (Michael-Scott queue is the classic):
1. Use CAS operations instead of locks
2. Nodes are linked together
3. Enqueue: CAS the tail pointer to new node
4. Dequeue: CAS the head pointer to next node
5. If CAS fails (another thread modified it), retry

Key concepts:
- **ABA problem**: CAS succeeds even if value changed A->B->A. Solved with version counters.
- **Memory reclamation**: Can't free dequeued nodes immediately (another thread might be reading). Use hazard pointers or epoch-based reclamation.
- **Progress guarantees**:
  - Lock-free: at least one thread makes progress (no deadlock)
  - Wait-free: every thread makes progress (stronger, harder to implement)
  - Obstruction-free: a thread makes progress if run in isolation

For Python specifically, lock-free isn't as beneficial due to the GIL. But the concepts
matter for C/C++/Rust/Java systems. In Python, better approaches:
- Use `collections.deque` (thread-safe append/popleft due to GIL)
- Use multiprocessing.Queue for cross-process
- Use thread-local batching to reduce contention

Let me explain the algorithm conceptually and give practical Python advice.
</think>

## Lock-Free Queue: Michael-Scott Algorithm

### Conceptual Implementation (pseudocode / educational)

```python
from dataclasses import dataclass
from typing import Optional, Any

@dataclass
class Node:
    value: Any
    next: Optional['Node'] = None  # atomically updated via CAS

class LockFreeQueue:
    """Michael-Scott lock-free queue (conceptual).

    Real implementations use CPU-level CAS instructions:
    - C++: std::atomic<Node*>::compare_exchange_weak
    - Java: AtomicReference.compareAndSet
    - Rust: std::sync::atomic::AtomicPtr
    """

    def __init__(self):
        sentinel = Node(value=None)  # dummy head node
        self.head = sentinel  # atomic pointer
        self.tail = sentinel  # atomic pointer

    def enqueue(self, value):
        new_node = Node(value=value)
        while True:
            tail = self.tail           # read tail
            next_node = tail.next      # read tail.next

            if tail is self.tail:      # still consistent?
                if next_node is None:
                    # Tail is at the real end. Try to link new node.
                    if CAS(tail, 'next', None, new_node):  # tail.next = new_node
                        # Linked! Now try to advance tail pointer.
                        CAS(self, 'tail', tail, new_node)
                        return
                else:
                    # Tail fell behind. Help advance it.
                    CAS(self, 'tail', tail, next_node)

    def dequeue(self) -> Optional[Any]:
        while True:
            head = self.head
            tail = self.tail
            next_node = head.next

            if head is self.head:      # still consistent?
                if head is tail:
                    if next_node is None:
                        return None    # queue is empty
                    # Tail fell behind. Help advance it.
                    CAS(self, 'tail', tail, next_node)
                else:
                    # Read value before CAS (another dequeue might free the node)
                    value = next_node.value
                    if CAS(self, 'head', head, next_node):
                        # Successfully dequeued. Old head can be reclaimed.
                        return value
```

### Practical Python: Batched Logging Queue

```python
import collections
import threading
import time

class HighThroughputLogger:
    """Reduces contention by batching log messages per thread."""

    def __init__(self, flush_interval=0.1, batch_size=100):
        self._local = threading.local()
        self._output_lock = threading.Lock()
        self._file = open("app.log", "a", buffering=8192)
        self._flush_interval = flush_interval
        self._batch_size = batch_size
        self._running = True

        # Background flusher
        self._flusher = threading.Thread(target=self._flush_loop, daemon=True)
        self._flusher.start()

        # Collect references to thread-local buffers
        self._buffers_lock = threading.Lock()
        self._buffers = []

    def _get_buffer(self):
        if not hasattr(self._local, 'buffer'):
            self._local.buffer = collections.deque()
            with self._buffers_lock:
                self._buffers.append(self._local.buffer)
        return self._local.buffer

    def log(self, message: str):
        """Lock-free per-thread buffering."""
        buf = self._get_buffer()
        buf.append(message)  # deque.append is thread-safe (GIL)

        # Flush if buffer is large
        if len(buf) >= self._batch_size:
            self._flush_buffer(buf)

    def _flush_buffer(self, buf):
        messages = []
        while buf:
            try:
                messages.append(buf.popleft())
            except IndexError:
                break
        if messages:
            batch = "\n".join(messages) + "\n"
            with self._output_lock:
                self._file.write(batch)

    def _flush_loop(self):
        while self._running:
            time.sleep(self._flush_interval)
            with self._buffers_lock:
                for buf in self._buffers:
                    self._flush_buffer(buf)
```

**When to use lock-free structures:**
- C/C++/Rust/Java with truly parallel threads and no GIL
- When profiling shows lock contention is the bottleneck
- High-throughput, low-latency systems (trading, game engines)
- Python: usually better to use thread-local batching or `collections.deque`'''
    ),
    (
        "thinking/concurrency-atomic-state-machine",
        r'''Our connection object can be in states: CONNECTING, CONNECTED, DISCONNECTING,
DISCONNECTED. Multiple threads call connect() and disconnect() concurrently, causing
invalid state transitions:

```python
class Connection:
    def __init__(self):
        self.state = "DISCONNECTED"

    def connect(self):
        if self.state == "DISCONNECTED":
            self.state = "CONNECTING"
            self._do_connect()
            self.state = "CONNECTED"

    def disconnect(self):
        if self.state == "CONNECTED":
            self.state = "DISCONNECTING"
            self._do_disconnect()
            self.state = "DISCONNECTED"
```

Thread A calls connect(), reads state as DISCONNECTED, gets preempted. Thread B also
reads DISCONNECTED and starts connecting. Both threads now attempt to connect
simultaneously. How do we make state transitions atomic?''',
        r'''<think>
The problem is a classic TOCTOU (time-of-check-time-of-use) race condition:
1. Thread A checks state == DISCONNECTED (True)
2. Thread A gets preempted
3. Thread B checks state == DISCONNECTED (still True)
4. Both proceed to connect

Solutions:
1. **Lock-based**: wrap check-and-transition in a lock
2. **CAS-based**: atomically check-and-swap state (the state IS the lock)
3. **State machine with lock**: define valid transitions, enforce atomically

The CAS approach is elegant: instead of lock-check-modify-unlock, do
compare_and_swap(expected=DISCONNECTED, desired=CONNECTING). Only one thread succeeds.
The others get a failed CAS and know someone else is already transitioning.

In Python, we can simulate CAS with a lock (due to GIL), but the pattern matters
for understanding concurrent state machines in any language.
</think>

## Fix: CAS-Based State Machine

```python
import threading
import enum
from typing import Optional

class State(enum.Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DISCONNECTING = "DISCONNECTING"

# Define valid transitions
VALID_TRANSITIONS = {
    State.DISCONNECTED: {State.CONNECTING},
    State.CONNECTING: {State.CONNECTED, State.DISCONNECTED},  # can fail
    State.CONNECTED: {State.DISCONNECTING},
    State.DISCONNECTING: {State.DISCONNECTED},
}

class Connection:
    def __init__(self):
        self._state = State.DISCONNECTED
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        return self._state

    def _cas_state(self, expected: State, desired: State) -> bool:
        """Atomically transition from expected to desired state.
        Returns True if transition succeeded, False if current state
        was not the expected state.
        """
        with self._lock:
            if self._state != expected:
                return False
            if desired not in VALID_TRANSITIONS.get(expected, set()):
                raise ValueError(
                    f"Invalid transition: {expected} -> {desired}"
                )
            self._state = desired
            return True

    def connect(self) -> bool:
        # Atomically: DISCONNECTED -> CONNECTING (only one thread succeeds)
        if not self._cas_state(State.DISCONNECTED, State.CONNECTING):
            return False  # another thread is already connecting

        try:
            self._do_connect()
            # CONNECTING -> CONNECTED
            self._cas_state(State.CONNECTING, State.CONNECTED)
            return True
        except Exception:
            # CONNECTING -> DISCONNECTED (rollback)
            self._cas_state(State.CONNECTING, State.DISCONNECTED)
            raise

    def disconnect(self) -> bool:
        if not self._cas_state(State.CONNECTED, State.DISCONNECTING):
            return False

        try:
            self._do_disconnect()
            self._cas_state(State.DISCONNECTING, State.DISCONNECTED)
            return True
        except Exception:
            # Rollback to CONNECTED if disconnect fails
            self._cas_state(State.DISCONNECTING, State.CONNECTED)
            raise
```

### With Condition Variable (wait for state)

```python
class Connection:
    def __init__(self):
        self._state = State.DISCONNECTED
        self._condition = threading.Condition()

    def connect(self, timeout: float = 30.0) -> bool:
        with self._condition:
            # Wait until we can transition (not already connecting)
            while self._state not in (State.DISCONNECTED,):
                if not self._condition.wait(timeout=timeout):
                    raise TimeoutError("Timed out waiting for DISCONNECTED state")

            self._state = State.CONNECTING
            self._condition.notify_all()

        try:
            self._do_connect()
        except Exception:
            with self._condition:
                self._state = State.DISCONNECTED
                self._condition.notify_all()
            raise

        with self._condition:
            self._state = State.CONNECTED
            self._condition.notify_all()
        return True

    def wait_for_state(self, target: State, timeout: float = None) -> bool:
        """Block until connection reaches the target state."""
        with self._condition:
            return self._condition.wait_for(
                lambda: self._state == target,
                timeout=timeout,
            )
```

**Key insight:** The CAS operation (compare-and-swap) combines the check and the
modification into a single atomic step, eliminating the TOCTOU window. Only one
thread can win the CAS; all others see a failed swap and know to back off.'''
    ),
    (
        "thinking/concurrency-lock-free-ring-buffer",
        r'''We're building a real-time audio processing system where a producer thread writes
audio samples and a consumer thread reads them. We need the lowest possible latency:

```python
import numpy as np
import threading

class AudioBuffer:
    def __init__(self, size=4096):
        self.buffer = np.zeros(size, dtype=np.float32)
        self.write_pos = 0
        self.read_pos = 0
        self.lock = threading.Lock()

    def write(self, samples):
        with self.lock:
            for s in samples:
                self.buffer[self.write_pos % len(self.buffer)] = s
                self.write_pos += 1

    def read(self, count):
        with self.lock:
            result = []
            for _ in range(count):
                if self.read_pos < self.write_pos:
                    result.append(self.buffer[self.read_pos % len(self.buffer)])
                    self.read_pos += 1
            return np.array(result, dtype=np.float32)
```

The lock adds latency jitter. Can we make this lock-free for a single-producer
single-consumer (SPSC) scenario?''',
        r'''<think>
For a single-producer, single-consumer (SPSC) ring buffer, we can make it completely
lock-free. The key insight:

- Only the producer writes to `write_pos`
- Only the consumer writes to `read_pos`
- Each side only READS the other's position

As long as position updates are visible across threads (memory ordering), no lock needed.

The SPSC ring buffer is one of the simplest lock-free structures:
1. Producer writes data, then advances write_pos
2. Consumer reads data, then advances read_pos
3. Buffer is full when: write_pos - read_pos == capacity
4. Buffer is empty when: write_pos == read_pos

Memory ordering matters:
- Producer: write data first, THEN update write_pos (write barrier)
- Consumer: read write_pos first, THEN read data (read barrier)
- In Python, GIL provides this ordering. In C/C++, need memory_order_release/acquire.

Also, the buffer size should be a power of 2 so we can use bitwise AND instead of
modulo for the index calculation (faster).

For the numpy buffer, we should use bulk copies instead of per-sample loops.
</think>

## Lock-Free SPSC Ring Buffer

```python
import numpy as np
import threading

class SPSCRingBuffer:
    """Single-Producer Single-Consumer lock-free ring buffer.

    No locks needed because:
    - Only producer modifies write_pos
    - Only consumer modifies read_pos
    - Power-of-2 size enables branchless index wrapping
    """

    def __init__(self, capacity: int = 4096):
        # Round up to power of 2
        self._capacity = 1 << (capacity - 1).bit_length()
        self._mask = self._capacity - 1  # for fast modulo
        self._buffer = np.zeros(self._capacity, dtype=np.float32)

        # Positions — each only written by one thread
        self._write_pos = 0  # only producer writes
        self._read_pos = 0   # only consumer writes

    def available_write(self) -> int:
        """How many samples can be written without overflowing."""
        return self._capacity - (self._write_pos - self._read_pos)

    def available_read(self) -> int:
        """How many samples are available to read."""
        return self._write_pos - self._read_pos

    def write(self, samples: np.ndarray) -> int:
        """Write samples into buffer. Returns number written.
        ONLY called from producer thread.
        """
        available = self.available_write()
        count = min(len(samples), available)
        if count == 0:
            return 0

        write_idx = self._write_pos & self._mask

        # Handle wrap-around with two copies
        first_chunk = min(count, self._capacity - write_idx)
        self._buffer[write_idx:write_idx + first_chunk] = samples[:first_chunk]

        if first_chunk < count:
            remainder = count - first_chunk
            self._buffer[:remainder] = samples[first_chunk:count]

        # Update position AFTER writing data (acts as write barrier)
        self._write_pos += count
        return count

    def read(self, count: int) -> np.ndarray:
        """Read up to count samples. Returns array (may be shorter).
        ONLY called from consumer thread.
        """
        available = self.available_read()
        count = min(count, available)
        if count == 0:
            return np.array([], dtype=np.float32)

        read_idx = self._read_pos & self._mask

        # Handle wrap-around
        first_chunk = min(count, self._capacity - read_idx)
        result = np.empty(count, dtype=np.float32)
        result[:first_chunk] = self._buffer[read_idx:read_idx + first_chunk]

        if first_chunk < count:
            remainder = count - first_chunk
            result[first_chunk:] = self._buffer[:remainder]

        # Update position AFTER reading data (acts as read barrier)
        self._read_pos += count
        return result

# Usage: audio processing pipeline
buffer = SPSCRingBuffer(capacity=8192)

def audio_capture_thread():
    """Producer: reads from audio hardware."""
    while running:
        samples = audio_device.read(256)  # 256 samples per callback
        written = buffer.write(samples)
        if written < len(samples):
            print("Buffer overflow! Consumer too slow.")

def audio_process_thread():
    """Consumer: processes audio with effects."""
    while running:
        samples = buffer.read(256)
        if len(samples) > 0:
            processed = apply_effects(samples)
            output_device.write(processed)
```

**Performance characteristics:**

| Aspect | Lock-based | SPSC Lock-free |
|--------|-----------|----------------|
| Latency | Variable (lock contention) | Deterministic |
| Jitter | High under contention | Near-zero |
| Throughput | Limited by lock overhead | Near-memory bandwidth |
| Cache behavior | Lock causes cache line bouncing | Minimal sharing |

**When to use SPSC ring buffers:**
- Audio/video real-time processing
- Sensor data acquisition
- Inter-thread communication in latency-sensitive systems
- Exactly one producer and one consumer (use MPMC for multiple)'''
    ),
    (
        "thinking/concurrency-aba-problem",
        r'''I'm implementing a lock-free stack in C++ using compare-and-swap. My colleague
says it has an ABA bug. Can you explain what ABA is and how to fix it?

```cpp
struct Node {
    int data;
    Node* next;
};

class LockFreeStack {
    std::atomic<Node*> top{nullptr};

public:
    void push(int value) {
        Node* new_node = new Node{value, nullptr};
        new_node->next = top.load();
        while (!top.compare_exchange_weak(new_node->next, new_node)) {
            // CAS failed, new_node->next is updated to current top
        }
    }

    int pop() {
        Node* old_top = top.load();
        while (old_top &&
               !top.compare_exchange_weak(old_top, old_top->next)) {
            // retry
        }
        if (old_top) {
            int value = old_top->data;
            delete old_top;
            return value;
        }
        throw std::runtime_error("empty stack");
    }
};
```''',
        r'''<think>
The ABA problem:

1. Thread 1 reads top = A (where A->next = B)
2. Thread 1 is preempted before CAS
3. Thread 2 pops A, pops B, pushes C, pushes A back (reusing or reallocating same address)
4. Now top = A again, but A->next = C (not B!)
5. Thread 1 resumes, CAS succeeds (top was A, still A)
6. Thread 1 sets top = B (the OLD next of A), but B was already freed!

The CAS only checks "is the pointer the same?" not "has anything changed since I read it?"
If a node is freed and its address is reused, CAS sees the same address and incorrectly succeeds.

This is the ABA problem: the value went A -> B -> A, and CAS can't detect that it changed.

Fixes:
1. **Tagged pointers** — pair the pointer with a version counter. CAS on (pointer, version).
   Even if pointer returns to A, the version is different.
2. **Hazard pointers** — register pointers you're reading so other threads won't free them.
3. **Epoch-based reclamation (EBR)** — defer freeing until all threads have moved past the epoch.
4. **Don't reuse nodes** — use a separate free list or never delete (works for some cases).
</think>

## The ABA Problem Explained

```
Timeline:
  Thread 1                              Thread 2
  --------                              --------
  old_top = A (A->next = B)
  [preempted]
                                        pop() -> removes A (top = B)
                                        pop() -> removes B (top = nullptr)
                                        delete B
                                        push(C) -> (top = C)
                                        push(new A at SAME address)
                                        Now: top = A, A->next = C
  [resumes]
  CAS(top, A, A->next)
  CAS sees top==A, succeeds!
  But A->next was B (stale!), now top = B
  B is FREED MEMORY -> undefined behavior
```

## Fix 1: Tagged Pointer (Version Counter)

```cpp
#include <atomic>

struct Node {
    int data;
    Node* next;
};

struct TaggedPtr {
    Node* ptr;
    uintptr_t tag;  // version counter
};

class LockFreeStack {
    // CAS on (pointer + tag) atomically — needs 128-bit CAS or packed struct
    std::atomic<TaggedPtr> top{{nullptr, 0}};

public:
    void push(int value) {
        Node* new_node = new Node{value, nullptr};
        TaggedPtr old_top = top.load();
        TaggedPtr new_top;
        do {
            new_node->next = old_top.ptr;
            new_top = {new_node, old_top.tag + 1};  // increment version
        } while (!top.compare_exchange_weak(old_top, new_top));
    }

    int pop() {
        TaggedPtr old_top = top.load();
        TaggedPtr new_top;
        do {
            if (!old_top.ptr) throw std::runtime_error("empty");
            new_top = {old_top.ptr->next, old_top.tag + 1};
        } while (!top.compare_exchange_weak(old_top, new_top));

        int value = old_top.ptr->data;
        // Don't delete immediately — use safe reclamation (see Fix 2)
        retire(old_top.ptr);
        return value;
    }
};
```

## Fix 2: Hazard Pointers (Safe Memory Reclamation)

```cpp
// Each thread publishes pointers it is currently reading
thread_local Node* hazard_pointer = nullptr;

class LockFreeStack {
    std::atomic<Node*> top{nullptr};
    // Retired nodes waiting to be freed
    thread_local static std::vector<Node*> retired;

public:
    int pop() {
        Node* old_top;
        do {
            old_top = top.load();
            if (!old_top) throw std::runtime_error("empty");

            // Publish: "I'm reading this node, don't free it"
            hazard_pointer = old_top;

            // Re-check top hasn't changed while we set hazard pointer
            if (top.load() != old_top) continue;

        } while (!top.compare_exchange_weak(old_top, old_top->next));

        hazard_pointer = nullptr;  // done reading

        int value = old_top->data;

        // Retire the node — will be freed when no hazard pointers reference it
        retired.push_back(old_top);
        if (retired.size() > threshold) {
            scan_and_free();  // free nodes not in any hazard pointer
        }
        return value;
    }
};
```

**ABA prevention strategies:**

| Strategy | Overhead | Complexity | Use Case |
|----------|---------|-----------|----------|
| Tagged pointer | 8 bytes per pointer | Low | Simple lock-free structures |
| Hazard pointers | Per-thread pointer array | Medium | General lock-free structures |
| Epoch-based (EBR) | Epoch counter | Medium | Read-heavy workloads (RCU) |
| No reuse (arena) | Memory growth | Low | Short-lived data structures |

**Python note:** The GIL prevents true ABA in CPython, but understanding ABA is essential
for systems programming in C/C++/Rust/Java where threads run in true parallel.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
