"""
Batch P6 -- Concurrency: lock-free data structures, actor model, async/await internals,
software transactional memory, parallel algorithms.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Lock-Free Data Structures ---
    (
        "concurrency/lock-free-data-structures-cas-aba",
        "Explain lock-free data structures in depth including compare-and-swap primitives, the ABA problem and its solutions, the Michael-Scott lock-free queue algorithm, memory ordering semantics such as acquire-release and sequentially consistent, and provide complete Python and C++ implementations with detailed analysis of correctness guarantees and performance characteristics.",
        r"""
# Lock-Free Data Structures: CAS, ABA, and the Michael-Scott Queue

## Why Lock-Free Matters

Traditional mutex-based synchronization has a fundamental problem: a thread holding a lock can be **descheduled**, causing every other thread that needs that lock to block. This leads to **priority inversion** (a low-priority thread blocks a high-priority one), **convoying** (threads pile up behind a slow lock holder), and worst of all, **deadlock** when locks are acquired in inconsistent orders. Lock-free data structures eliminate these problems by guaranteeing that **at least one thread makes progress** in a finite number of steps, regardless of what other threads are doing.

The **trade-off** is significant: lock-free code is harder to write correctly, harder to reason about, and can actually be slower under low contention because CAS loops burn CPU cycles that a mutex-based approach would spend sleeping. However, under high contention and on many-core systems, lock-free structures dramatically outperform locked alternatives because they eliminate the serial bottleneck entirely.

**Common mistake**: conflating "lock-free" with "wait-free." Lock-free guarantees system-wide progress (some thread completes). Wait-free guarantees per-thread progress (every thread completes in bounded steps). Wait-free is strictly stronger and much harder to achieve.

## Compare-And-Swap: The Atomic Foundation

Compare-and-swap (CAS) is the fundamental hardware primitive that makes lock-free programming possible. It atomically reads a memory location, compares it to an expected value, and writes a new value only if the comparison succeeds. On x86, this maps to the `CMPXCHG` instruction; on ARM, it uses the load-linked/store-conditional pair (`LDXR`/`STXR`).

### CAS Semantics

```cpp
#include <atomic>
#include <cstdint>
#include <optional>
#include <iostream>

// CAS semantics demonstrated with std::atomic
// The hardware guarantees this entire operation is atomic
template <typename T>
bool compare_and_swap(std::atomic<T>& target, T expected, T desired) {
    // compare_exchange_strong returns true if the swap succeeded.
    // If it fails, 'expected' is updated to the current value,
    // which is useful for retry loops.
    return target.compare_exchange_strong(
        expected, desired,
        std::memory_order_acq_rel,  // success ordering
        std::memory_order_acquire    // failure ordering
    );
}

// A simple lock-free counter using CAS
class LockFreeCounter {
    std::atomic<int64_t> value_{0};

public:
    // Increment using CAS loop -- guaranteed to succeed eventually
    // because the CAS only fails when another thread succeeded
    // (system-wide progress guarantee)
    int64_t increment() {
        int64_t old_val = value_.load(std::memory_order_relaxed);
        while (!value_.compare_exchange_weak(
            old_val, old_val + 1,
            std::memory_order_acq_rel,
            std::memory_order_relaxed
        )) {
            // old_val is automatically updated on failure
            // We spin and retry -- this is the CAS loop pattern
        }
        return old_val + 1;
    }

    int64_t get() const {
        return value_.load(std::memory_order_acquire);
    }
};
```

**Best practice**: use `compare_exchange_weak` in loops (it can spuriously fail but is faster on ARM) and `compare_exchange_strong` when you need a single attempt. The weak variant maps more naturally to LL/SC on ARM architectures.

## The ABA Problem

The ABA problem is the most insidious **pitfall** in lock-free programming. It occurs when a CAS succeeds even though the data structure has been modified, because the value happens to have returned to its original state.

### ABA Scenario

Consider a lock-free stack:
1. Thread A reads top = node X (value A), prepares to pop
2. Thread A is preempted
3. Thread B pops X (A), pops Y (B), pushes X (A) back -- top is X again
4. Thread A resumes, CAS sees top == X, succeeds -- but X's next pointer now points to freed memory because Y was popped

### ABA Solutions

**Tagged pointers** (most common): pack a monotonically increasing counter alongside the pointer. Every CAS increments the counter, so even if the pointer returns to the same value, the tag differs.

**Hazard pointers**: each thread publishes which nodes it is currently accessing. Nodes are not freed until no thread has a hazard pointer to them.

**Epoch-based reclamation**: threads enter and leave "epochs." Memory is freed only when all threads have advanced past the epoch in which it was retired.

```cpp
#include <atomic>
#include <cstdint>
#include <memory>
#include <iostream>
#include <thread>
#include <vector>

// Tagged pointer to solve the ABA problem
// We pack a 16-bit tag with a 48-bit pointer (x86-64 uses only 48 bits)
template <typename T>
struct TaggedPtr {
    T* ptr;
    uint16_t tag;

    TaggedPtr() : ptr(nullptr), tag(0) {}
    TaggedPtr(T* p, uint16_t t) : ptr(p), tag(t) {}

    bool operator==(const TaggedPtr& other) const {
        return ptr == other.ptr && tag == other.tag;
    }
};

// Lock-free stack with ABA protection via tagged pointers
template <typename T>
class LockFreeStack {
    struct Node {
        T data;
        Node* next;
        Node(const T& val) : data(val), next(nullptr) {}
    };

    // Using a struct that can be compared atomically
    // In production, use double-width CAS (DWCAS) or
    // std::atomic with 128-bit support
    struct Head {
        Node* ptr;
        uint64_t tag;  // monotonic counter prevents ABA
    };

    std::atomic<Node*> head_{nullptr};
    std::atomic<uint64_t> tag_{0};

public:
    void push(const T& value) {
        Node* new_node = new Node(value);
        new_node->next = head_.load(std::memory_order_relaxed);
        // CAS loop: keep trying until we successfully link the new node
        while (!head_.compare_exchange_weak(
            new_node->next, new_node,
            std::memory_order_release,
            std::memory_order_relaxed
        )) {
            // On failure, new_node->next is updated to current head
        }
    }

    std::optional<T> pop() {
        Node* old_head = head_.load(std::memory_order_acquire);
        while (old_head != nullptr) {
            Node* next = old_head->next;
            if (head_.compare_exchange_weak(
                old_head, next,
                std::memory_order_acq_rel,
                std::memory_order_acquire
            )) {
                T result = old_head->data;
                // In production: defer deletion via hazard pointers
                // or epoch-based reclamation instead of immediate delete
                delete old_head;
                return result;
            }
            // old_head updated automatically on CAS failure
        }
        return std::nullopt;
    }
};
```

## The Michael-Scott Lock-Free Queue

The Michael-Scott queue (1996) is the foundational lock-free FIFO queue algorithm. It uses **two CAS operations** -- one for the tail (enqueue) and one for the head (dequeue) -- allowing enqueue and dequeue to proceed concurrently without interfering with each other.

### Key Insight

The algorithm uses a **sentinel node** (dummy node) so that the queue is never truly empty from the perspective of the pointers. This eliminates the special case where head == tail and we need to update both atomically.

### The Helping Mechanism

A critical design feature is **helping**: during enqueue, if a thread observes that the tail pointer is lagging (tail->next is not null), it advances the tail pointer before attempting its own operation. This ensures the data structure remains consistent even if a thread is preempted mid-operation.

```python
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TypeVar, Generic, Optional
import ctypes
import time

T = TypeVar("T")


@dataclass
class Node(Generic[T]):
    # A node in the lock-free queue
    # Using a simple Python implementation -- in production,
    # you would need actual atomic operations via ctypes or cffi
    value: Optional[T] = None
    next_node: Optional[Node[T]] = None


class AtomicReference(Generic[T]):
    # Simulates an atomic reference with a tag counter
    # to prevent ABA problems. Uses a lock internally because
    # Python lacks native CAS, but the algorithm structure
    # demonstrates the lock-free pattern correctly.

    def __init__(self, initial: T, tag: int = 0) -> None:
        self._lock = threading.Lock()
        self._ref: T = initial
        self._tag: int = tag

    def get(self) -> tuple[T, int]:
        # Read the reference and its tag atomically
        with self._lock:
            return self._ref, self._tag

    def cas(self, expected_ref: T, new_ref: T, expected_tag: int) -> bool:
        # Compare-and-swap: atomically update if current matches expected
        with self._lock:
            if self._ref is expected_ref and self._tag == expected_tag:
                self._ref = new_ref
                self._tag = expected_tag + 1
                return True
            return False


class MichaelScottQueue(Generic[T]):
    # Lock-free FIFO queue based on the Michael-Scott algorithm.
    # This implementation demonstrates the algorithm structure
    # with tagged pointers for ABA protection and the critical
    # helping mechanism for tail advancement.

    def __init__(self) -> None:
        # Initialize with a sentinel (dummy) node
        sentinel: Node[T] = Node()
        self._head = AtomicReference(sentinel, tag=0)
        self._tail = AtomicReference(sentinel, tag=0)

    def enqueue(self, value: T) -> None:
        # Add a value to the tail of the queue.
        # The algorithm has three phases:
        # 1. Read current tail
        # 2. If tail.next is None, CAS our new node in
        # 3. Advance the tail pointer (helping mechanism)
        new_node = Node(value=value)

        while True:
            tail, tail_tag = self._tail.get()
            next_node = tail.next_node

            # Re-read tail to check consistency
            current_tail, current_tag = self._tail.get()
            if tail is not current_tail or tail_tag != current_tag:
                continue  # tail changed, retry

            if next_node is None:
                # Tail is pointing to the last node -- try to link new node
                # This is the linearization point for enqueue
                old_next = tail.next_node
                if old_next is None:
                    tail.next_node = new_node  # simulated CAS on next pointer
                    # Advance tail pointer -- if this fails, another thread helped us
                    self._tail.cas(tail, new_node, tail_tag)
                    return
            else:
                # Tail is lagging -- help advance it before retrying
                # This is the HELPING mechanism: threads cooperate
                # to keep the data structure consistent
                self._tail.cas(tail, next_node, tail_tag)

    def dequeue(self) -> Optional[T]:
        # Remove and return the value at the head of the queue.
        # Returns None if the queue is empty.
        while True:
            head, head_tag = self._head.get()
            tail, tail_tag = self._tail.get()
            next_node = head.next_node

            # Consistency check
            current_head, current_tag = self._head.get()
            if head is not current_head or head_tag != current_tag:
                continue

            if head is tail:
                if next_node is None:
                    # Queue is empty (only sentinel remains)
                    return None
                # Tail is lagging -- help advance it
                self._tail.cas(tail, next_node, tail_tag)
            else:
                if next_node is None:
                    continue  # inconsistent read, retry
                # Read value before CAS -- because after CAS the node
                # could be freed by another thread
                value = next_node.value
                # Swing head to the next node (linearization point for dequeue)
                if self._head.cas(head, next_node, head_tag):
                    return value

    def __len__(self) -> int:
        # O(n) traversal -- not linearizable, only approximate
        count = 0
        current = self._head.get()[0].next_node
        while current is not None:
            count += 1
            current = current.next_node
        return count


def stress_test_queue(num_producers: int = 4, num_consumers: int = 4,
                      items_per_producer: int = 1000) -> None:
    # Stress test demonstrating concurrent enqueue/dequeue
    queue: MichaelScottQueue[int] = MichaelScottQueue()
    results: list[int] = []
    results_lock = threading.Lock()

    def producer(start: int, count: int) -> None:
        for i in range(start, start + count):
            queue.enqueue(i)

    def consumer(expected_total: int) -> None:
        local_results: list[int] = []
        empty_spins = 0
        while len(local_results) < expected_total:
            val = queue.dequeue()
            if val is not None:
                local_results.append(val)
                empty_spins = 0
            else:
                empty_spins += 1
                if empty_spins > 10000:
                    break
                time.sleep(0.0001)
        with results_lock:
            results.extend(local_results)

    total = num_producers * items_per_producer
    producers = [
        threading.Thread(target=producer, args=(i * items_per_producer, items_per_producer))
        for i in range(num_producers)
    ]
    consumers = [
        threading.Thread(target=consumer, args=(total // num_consumers,))
        for i in range(num_consumers)
    ]

    start_time = time.monotonic()
    for t in producers + consumers:
        t.start()
    for t in producers:
        t.join()
    for t in consumers:
        t.join(timeout=5.0)
    elapsed = time.monotonic() - start_time

    print(f"Produced {total} items, consumed {len(results)}, "
          f"time={elapsed:.3f}s, throughput={len(results)/elapsed:.0f} ops/s")
```

## Memory Ordering: The Invisible Minefield

Memory ordering is where lock-free programming goes from "tricky" to "terrifying." Modern CPUs reorder instructions aggressively for performance. Without explicit memory ordering constraints, your carefully designed algorithm can fail because the CPU or compiler rearranged your reads and writes.

### The Memory Ordering Hierarchy

| Ordering | Guarantee | Cost |
|----------|-----------|------|
| `relaxed` | Atomicity only, no ordering | Near-zero |
| `acquire` | No reads/writes after this can be reordered before it | Load fence |
| `release` | No reads/writes before this can be reordered after it | Store fence |
| `acq_rel` | Both acquire and release | Full fence on the operation |
| `seq_cst` | Total global ordering visible to all threads | Most expensive |

**Therefore**, the correct strategy is to use the **weakest ordering that maintains correctness**. Using `seq_cst` everywhere is correct but leaves performance on the table; using `relaxed` everywhere is fast but almost certainly wrong.

**Best practice**: start with `seq_cst` to get a correct implementation, then carefully relax orderings one at a time, proving each relaxation is safe. The canonical pattern for lock-free structures is `release` on stores that publish data, `acquire` on loads that consume data, and `relaxed` for counter increments that only need atomicity.

## Performance Analysis and When to Use Lock-Free

### When Lock-Free Wins
- **High contention**: many threads competing for the same data structure
- **Real-time systems**: no unbounded blocking, no priority inversion
- **Asymmetric workloads**: fast producers, slow consumers (or vice versa)

### When Locks Win
- **Low contention**: mutex fast path (uncontended) is a single atomic exchange
- **Complex operations**: when the critical section does substantial work, the overhead of retrying a CAS loop outweighs the cost of briefly holding a lock
- **Simplicity**: lock-based code is easier to audit and maintain

### Common Pitfall: False Sharing

Two threads operating on different atomic variables that share a cache line will experience **false sharing** -- each CAS invalidates the other thread's cache line, causing excessive cache coherency traffic. The solution is to pad atomic variables to cache line boundaries (typically 64 bytes).

## Summary and Key Takeaways

- **Compare-and-swap** (CAS) is the atomic primitive underlying all lock-free structures; it reads, compares, and conditionally writes in a single hardware operation
- The **ABA problem** occurs when CAS succeeds spuriously because a value returned to its original state; solutions include tagged pointers, hazard pointers, and epoch-based reclamation
- The **Michael-Scott queue** uses a sentinel node and a helping mechanism where threads cooperatively advance the tail pointer, achieving lock-free FIFO with separate head/tail CAS operations
- **Memory ordering** is critical: `acquire` on loads, `release` on stores, `relaxed` only for operations that need atomicity without ordering
- **Best practice**: start with locks, profile, and only move to lock-free structures when contention is proven to be the bottleneck -- premature optimization toward lock-free is a recipe for subtle, unreproducible bugs
- **Trade-off**: lock-free gives progress guarantees and eliminates priority inversion at the cost of implementation complexity, memory reclamation challenges, and potentially higher CPU usage under low contention
""",
    ),

    # --- 2. Actor Model (Akka/Erlang Style) ---
    (
        "concurrency/actor-model-message-passing-supervision",
        "Explain the actor model of concurrency in the style of Akka and Erlang including message passing semantics, supervision trees and failure handling strategies, location transparency for distributed actors, mailbox management and back-pressure, and provide a complete Python actor framework implementation with typed messages and supervision hierarchy.",
        r"""
# The Actor Model: Message Passing, Supervision, and Location Transparency

## Why the Actor Model Exists

The actor model was conceived by Carl Hewitt in 1973 and later refined by Gul Agha. Its core premise is radical: **shared mutable state is the root cause of concurrency bugs**, so eliminate it entirely. Instead of threads sharing memory and coordinating via locks, actors are isolated entities that communicate exclusively through **asynchronous message passing**. Each actor has a private state that no other actor can access directly.

Erlang/OTP proved this model at industrial scale -- Ericsson's telephone switches achieved **99.9999999% uptime** (nine nines) using actors. Akka brought the model to the JVM ecosystem. The actor model's resurgence in modern systems (Microsoft Orleans, Proto.Actor, Elixir/Phoenix) reflects a growing recognition that **shared-memory concurrency does not scale** to distributed systems.

**Common mistake**: treating actors like lightweight threads that happen to use message passing. Actors are a fundamentally different abstraction -- they enforce isolation by construction, not by convention. You cannot accidentally share state between actors because there is no mechanism to do so.

## Core Principles

### Everything is an Actor

In a pure actor system, actors are the **only** unit of computation. When an actor receives a message, it can:
1. **Send** a finite number of messages to other actors
2. **Create** a finite number of new actors
3. **Designate** a behavior for the next message it processes

This is the complete set of operations. There are no locks, no shared variables, no condition variables. Concurrency emerges from the fact that actors process messages independently and in parallel.

### Message Passing Semantics

Messages are sent **asynchronously** -- the sender does not block waiting for the receiver to process the message. Messages are delivered **at most once** in the basic model (Akka provides at-least-once delivery as an opt-in). Within a single sender-receiver pair, message ordering is preserved (Erlang and Akka both guarantee this), however messages from different senders may interleave arbitrarily.

**Best practice**: design message protocols to be **idempotent** whenever possible. Because message delivery is not guaranteed in distributed settings, receivers should handle duplicate messages gracefully.

## Supervision Trees: Let It Crash

The **"let it crash"** philosophy is perhaps the actor model's most revolutionary contribution to software engineering. Instead of defensively handling every possible error at the point of occurrence, actors are organized into **supervision hierarchies** where parent actors decide how to handle child failures.

### Supervision Strategies

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| **One-for-one** | Restart only the failed child | Independent children |
| **One-for-all** | Restart all children when one fails | Interdependent children |
| **Rest-for-one** | Restart the failed child and all children started after it | Sequential dependencies |
| **Escalate** | Propagate failure to parent supervisor | Unrecoverable errors |

**Therefore**, error handling becomes a structural property of the system rather than scattered try/catch blocks. This is fundamentally more maintainable because failure policies are declared in one place (the supervisor) rather than duplicated across every function call.

## Complete Python Actor Framework Implementation

```python
from __future__ import annotations

import asyncio
import enum
import logging
import traceback
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Coroutine, Dict, Generic, List, Optional,
    Set, Type, TypeVar, Union,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
M = TypeVar("M")


# ---- Message Types ----

@dataclass(frozen=True)
class ActorRef:
    # A handle to an actor that can be used to send messages.
    # Actors never interact with each other directly -- only
    # through ActorRef, which provides location transparency.
    actor_id: str
    _system: ActorSystem

    async def tell(self, message: Any) -> None:
        # Fire-and-forget message send (asynchronous)
        await self._system.deliver(self.actor_id, message)

    async def ask(self, message: Any, timeout: float = 5.0) -> Any:
        # Request-response pattern with timeout
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        wrapped = AskMessage(payload=message, reply_to=future)
        await self._system.deliver(self.actor_id, wrapped)
        return await asyncio.wait_for(future, timeout=timeout)


@dataclass(frozen=True)
class AskMessage:
    # Wraps a message with a future for request-response
    payload: Any
    reply_to: asyncio.Future


@dataclass(frozen=True)
class PoisonPill:
    # Tells an actor to stop processing and shut down
    pass


@dataclass(frozen=True)
class ChildFailed:
    # Notification sent to supervisor when a child actor crashes
    child_id: str
    exception: Exception


# ---- Supervision ----

class SupervisionStrategy(enum.Enum):
    RESTART = "restart"       # Restart the failed child
    STOP = "stop"             # Permanently stop the failed child
    ESCALATE = "escalate"     # Propagate failure to parent
    RESUME = "resume"         # Ignore the failure and continue


@dataclass
class SupervisionPolicy:
    # Defines how a parent handles child failures
    strategy: SupervisionStrategy = SupervisionStrategy.RESTART
    max_restarts: int = 10
    within_seconds: float = 60.0
    _restart_timestamps: List[float] = field(default_factory=list)

    def should_restart(self, current_time: float) -> bool:
        # Check if we have exceeded the restart limit within the window
        cutoff = current_time - self.within_seconds
        self._restart_timestamps = [
            t for t in self._restart_timestamps if t > cutoff
        ]
        if len(self._restart_timestamps) >= self.max_restarts:
            return False
        self._restart_timestamps.append(current_time)
        return True


# ---- Actor Base Class ----

class Actor(ABC):
    # Base class for all actors. Subclasses implement receive()
    # to define message handling behavior.

    def __init__(self) -> None:
        self.context: Optional[ActorContext] = None

    def pre_start(self) -> None:
        # Called before the actor starts processing messages.
        # Override to perform initialization.
        pass

    def post_stop(self) -> None:
        # Called after the actor stops processing messages.
        # Override to perform cleanup.
        pass

    def pre_restart(self, reason: Exception) -> None:
        # Called before the actor is restarted after a failure.
        # Default behavior: stop all children.
        if self.context:
            for child_id in list(self.context.children):
                asyncio.ensure_future(
                    self.context.stop_child(child_id)
                )

    @abstractmethod
    async def receive(self, message: Any) -> None:
        # Handle an incoming message. This is the core method
        # that defines the actor's behavior.
        ...


class ActorContext:
    # Provides the execution context for an actor, including
    # the ability to create children, access self reference,
    # and interact with the supervision hierarchy.

    def __init__(self, actor_id: str, system: ActorSystem,
                 parent_id: Optional[str] = None) -> None:
        self.actor_id = actor_id
        self.self_ref = ActorRef(actor_id, system)
        self.parent_id = parent_id
        self.children: Dict[str, ActorRef] = {}
        self._system = system
        self.supervision = SupervisionPolicy()

    async def spawn(self, actor_class: Type[Actor], name: str,
                    *args: Any, **kwargs: Any) -> ActorRef:
        # Create a child actor under this actor's supervision
        child_id = f"{self.actor_id}/{name}"
        ref = await self._system.create_actor(
            actor_class, child_id, parent_id=self.actor_id,
            *args, **kwargs
        )
        self.children[child_id] = ref
        return ref

    async def stop_child(self, child_id: str) -> None:
        # Stop a specific child actor
        if child_id in self.children:
            await self._system.stop_actor(child_id)
            del self.children[child_id]


# ---- Actor Cell (runtime wrapper) ----

class ActorCell:
    # Manages the lifecycle and mailbox of a single actor instance.
    # The cell decouples the actor's identity from its instance,
    # enabling restarts without changing the ActorRef.

    def __init__(self, actor: Actor, context: ActorContext,
                 supervision: SupervisionPolicy) -> None:
        self.actor = actor
        self.context = context
        self.supervision = supervision
        self.mailbox: asyncio.Queue[Any] = asyncio.Queue(maxsize=1000)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self.actor.context = self.context
        self.actor.pre_start()
        self._running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.actor.post_stop()

    async def _process_loop(self) -> None:
        # Main message processing loop -- processes one message at a time
        # ensuring that the actor's state is never accessed concurrently
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self.mailbox.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            if isinstance(message, PoisonPill):
                await self.stop()
                return

            try:
                if isinstance(message, AskMessage):
                    await self.actor.receive(message.payload)
                else:
                    await self.actor.receive(message)
            except Exception as exc:
                logger.error(
                    f"Actor {self.context.actor_id} failed: {exc}"
                )
                await self._handle_failure(exc)

    async def _handle_failure(self, exc: Exception) -> None:
        # Notify parent supervisor about the failure
        if self.context.parent_id:
            parent_ref = ActorRef(self.context.parent_id, self.context._system)
            await parent_ref.tell(ChildFailed(
                child_id=self.context.actor_id,
                exception=exc
            ))


# ---- Actor System ----

class ActorSystem:
    # The top-level container for all actors. Creates, manages,
    # and provides routing for actor message delivery.
    # Acts as the root supervisor for top-level actors.

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._actors: Dict[str, ActorCell] = {}
        self._actor_factories: Dict[str, tuple] = {}

    async def create_actor(self, actor_class: Type[Actor],
                           actor_id: Optional[str] = None,
                           parent_id: Optional[str] = None,
                           *args: Any, **kwargs: Any) -> ActorRef:
        # Create and start a new actor
        if actor_id is None:
            actor_id = f"{actor_class.__name__}-{uuid.uuid4().hex[:8]}"

        context = ActorContext(actor_id, self, parent_id)
        actor = actor_class(*args, **kwargs)
        supervision = SupervisionPolicy()

        cell = ActorCell(actor, context, supervision)
        self._actors[actor_id] = cell
        self._actor_factories[actor_id] = (actor_class, args, kwargs)
        await cell.start()

        logger.info(f"Actor started: {actor_id}")
        return ActorRef(actor_id, self)

    async def deliver(self, actor_id: str, message: Any) -> None:
        # Deliver a message to an actor's mailbox
        cell = self._actors.get(actor_id)
        if cell is None:
            logger.warning(f"Dead letter: {message} -> {actor_id}")
            return
        try:
            cell.mailbox.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning(f"Mailbox full for {actor_id}, dropping message")

    async def stop_actor(self, actor_id: str) -> None:
        cell = self._actors.pop(actor_id, None)
        if cell:
            await cell.stop()
            logger.info(f"Actor stopped: {actor_id}")

    async def restart_actor(self, actor_id: str, reason: Exception) -> None:
        # Restart an actor by creating a new instance but keeping the same ID
        cell = self._actors.get(actor_id)
        if cell is None:
            return
        factory = self._actor_factories.get(actor_id)
        if factory is None:
            return

        actor_class, args, kwargs = factory
        cell.actor.pre_restart(reason)
        await cell.stop()

        # Create new instance with same identity
        new_actor = actor_class(*args, **kwargs)
        new_cell = ActorCell(new_actor, cell.context, cell.supervision)
        self._actors[actor_id] = new_cell
        await new_cell.start()
        logger.info(f"Actor restarted: {actor_id} (reason: {reason})")

    async def shutdown(self) -> None:
        for actor_id in list(self._actors.keys()):
            await self.stop_actor(actor_id)
        logger.info(f"ActorSystem '{self.name}' shut down")
```

### Example: Worker Pool with Supervision

```python
import asyncio
import random
from typing import Any

# Using the actor framework defined above

@dataclass(frozen=True)
class WorkItem:
    task_id: int
    payload: str

@dataclass(frozen=True)
class WorkResult:
    task_id: int
    result: str


class WorkerActor(Actor):
    # A worker that processes tasks and may randomly fail
    # to demonstrate supervision recovery

    def __init__(self, failure_rate: float = 0.1) -> None:
        super().__init__()
        self.failure_rate = failure_rate
        self.processed = 0

    async def receive(self, message: Any) -> None:
        if isinstance(message, WorkItem):
            # Simulate occasional failures
            if random.random() < self.failure_rate:
                raise RuntimeError(
                    f"Worker crashed processing task {message.task_id}"
                )
            # Process the work item
            result = f"Processed '{message.payload}' -> done"
            self.processed += 1
            logger.info(
                f"Worker {self.context.actor_id}: task {message.task_id} "
                f"complete (total: {self.processed})"
            )


class SupervisorActor(Actor):
    # Supervises a pool of workers with one-for-one restart strategy

    def __init__(self, num_workers: int = 4) -> None:
        super().__init__()
        self.num_workers = num_workers
        self.workers: list[ActorRef] = []
        self.round_robin_idx = 0

    def pre_start(self) -> None:
        # Spawn worker pool on startup
        asyncio.ensure_future(self._spawn_workers())

    async def _spawn_workers(self) -> None:
        for i in range(self.num_workers):
            ref = await self.context.spawn(
                WorkerActor, f"worker-{i}", failure_rate=0.15
            )
            self.workers.append(ref)

    async def receive(self, message: Any) -> None:
        if isinstance(message, WorkItem):
            # Route work to next worker (round-robin)
            worker = self.workers[self.round_robin_idx % len(self.workers)]
            await worker.tell(message)
            self.round_robin_idx += 1

        elif isinstance(message, ChildFailed):
            # One-for-one supervision: restart only the failed child
            logger.warning(
                f"Supervisor: child {message.child_id} failed "
                f"with {message.exception}, restarting..."
            )
            import time
            policy = self.context.supervision
            if policy.should_restart(time.time()):
                await self.context._system.restart_actor(
                    message.child_id, message.exception
                )
            else:
                logger.error(
                    f"Max restarts exceeded for {message.child_id}, stopping"
                )
                await self.context.stop_child(message.child_id)


async def run_actor_demo() -> None:
    system = ActorSystem("demo")
    supervisor = await system.create_actor(SupervisorActor, "supervisor")

    await asyncio.sleep(0.5)  # let workers initialize

    for i in range(20):
        await supervisor.tell(WorkItem(task_id=i, payload=f"job-{i}"))
        await asyncio.sleep(0.05)

    await asyncio.sleep(2.0)
    await system.shutdown()
```

## Location Transparency

Location transparency means that an `ActorRef` works the same way whether the target actor is in the same process, on another machine, or in another data center. The messaging layer handles serialization and routing transparently. In Akka, this is achieved through the `RemoteActorRef` that serializes messages over the network using Akka Remoting or Akka Cluster.

**However**, location transparency is not a free abstraction. Network calls introduce latency, partial failures, and message loss that local calls do not. **Best practice**: design your message protocols to tolerate these realities from the start -- use idempotent messages, include correlation IDs for request-response, and implement explicit acknowledgment where reliability matters.

```python
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class RemoteEnvelope:
    # Wraps a message for transmission across the network.
    # Includes routing metadata so the remote ActorSystem
    # can deliver it to the correct actor.
    sender_path: str
    target_path: str
    message_type: str
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None  # for request-response tracking

    def serialize(self) -> bytes:
        return json.dumps(asdict(self)).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> RemoteEnvelope:
        d = json.loads(data.decode("utf-8"))
        return cls(**d)


class RemoteActorRef:
    # An ActorRef that sends messages over the network.
    # From the caller's perspective, it has the same interface
    # as a local ActorRef -- this is location transparency.

    def __init__(self, remote_path: str, transport: Any) -> None:
        self.remote_path = remote_path
        self._transport = transport

    async def tell(self, message: Any, sender_path: str = "anonymous") -> None:
        envelope = RemoteEnvelope(
            sender_path=sender_path,
            target_path=self.remote_path,
            message_type=type(message).__name__,
            payload=asdict(message) if hasattr(message, "__dataclass_fields__") else {"value": message},
        )
        await self._transport.send(envelope.serialize())
```

## Summary and Key Takeaways

- The actor model eliminates shared mutable state by **isolating** actors and using **asynchronous message passing** as the sole communication mechanism
- **Supervision trees** implement the "let it crash" philosophy where parent actors declaratively define failure recovery strategies (restart, stop, escalate)
- **Location transparency** decouples actor identity from physical location, enabling seamless distribution across nodes -- however this abstraction has real costs in latency and reliability
- **Mailbox management** and back-pressure are critical for production systems: unbounded mailboxes lead to OOM, while bounded mailboxes require explicit dropping or flow control strategies
- **Trade-off**: the actor model excels at managing massive concurrency (millions of actors) and fault tolerance, but introduces complexity in debugging (no stack traces across actors), testing (non-deterministic message ordering), and reasoning about global system state
- **Pitfall**: using actors for compute-heavy blocking operations defeats the purpose -- actors should do small units of work and yield; delegate heavy computation to dedicated thread pools
""",
    ),

    # --- 3. Async/Await Internals ---
    (
        "concurrency/async-await-coroutine-internals",
        "Explain async/await internals in depth including how coroutines compile to state machines, event loop implementation and scheduling algorithms, cooperative scheduling and its implications, Python asyncio internals covering tasks futures and the selector-based event loop, and provide complete implementations of a minimal event loop and coroutine scheduler with performance analysis.",
        r"""
# Async/Await Internals: Coroutine State Machines, Event Loops, and Cooperative Scheduling

## The Core Abstraction

Async/await is **syntactic sugar** over coroutines, which are themselves a form of cooperative multitasking. When you write `await some_io()`, the runtime suspends the current coroutine, registers interest in an I/O event, and runs other coroutines until that event fires. No threads are created, no context switches happen at the OS level -- everything runs on a **single thread** (in the default case).

This is fundamentally different from preemptive multitasking (threads) where the OS scheduler can interrupt any thread at any point. **Because** async/await is cooperative, a coroutine that never yields (never hits an `await`) will **block the entire event loop**. This is the single most important thing to understand about async programming.

**Common mistake**: using `time.sleep(5)` inside an async function instead of `await asyncio.sleep(5)`. The synchronous sleep blocks the event loop thread, freezing all other coroutines for 5 seconds. This mistake is surprisingly common in production code.

## How Coroutines Compile to State Machines

When the Python compiler encounters an `async def` function, it does not generate a function that runs to completion. Instead, it creates a **coroutine object** -- a state machine that can be suspended and resumed. Each `await` point becomes a **suspension point** where the state machine saves its local variables, instruction pointer, and yields control back to the caller.

### Desugared Coroutine

Consider this async function:

```python
from __future__ import annotations

import asyncio
from typing import Any, Optional

# Original async function
async def fetch_and_process(url: str) -> dict:
    response = await http_get(url)           # suspension point 1
    data = await response.json()              # suspension point 2
    processed = transform(data)
    await save_to_db(processed)               # suspension point 3
    return processed

# The compiler transforms this into roughly equivalent to:
class FetchAndProcessStateMachine:
    # Each await point becomes a state transition.
    # Local variables are stored as instance attributes
    # so they survive across suspensions.

    STATE_INIT = 0
    STATE_AFTER_HTTP_GET = 1
    STATE_AFTER_JSON = 2
    STATE_AFTER_SAVE = 3
    STATE_DONE = 4

    def __init__(self, url: str) -> None:
        self._state = self.STATE_INIT
        self._url = url
        # Local variables stored as fields for persistence across yields
        self._response: Any = None
        self._data: Any = None
        self._processed: Any = None
        self._result: Any = None

    def send(self, value: Any = None) -> Any:
        # Called by the event loop to advance the coroutine.
        # Returns the next awaitable or raises StopIteration with the result.
        if self._state == self.STATE_INIT:
            self._state = self.STATE_AFTER_HTTP_GET
            return http_get(self._url)  # yield the awaitable

        elif self._state == self.STATE_AFTER_HTTP_GET:
            self._response = value  # value sent by event loop
            self._state = self.STATE_AFTER_JSON
            return self._response.json()  # yield next awaitable

        elif self._state == self.STATE_AFTER_JSON:
            self._data = value
            self._processed = transform(self._data)
            self._state = self.STATE_AFTER_SAVE
            return save_to_db(self._processed)

        elif self._state == self.STATE_AFTER_SAVE:
            self._result = self._processed
            raise StopIteration(self._result)  # coroutine complete

        raise RuntimeError(f"Invalid state: {self._state}")
```

**Therefore**, the async/await transformation is fundamentally a **CPS (continuation-passing style) transformation** where each continuation is encoded as a state in the state machine. The compiler handles this automatically, but understanding the underlying mechanism explains why coroutines have near-zero overhead compared to threads (no stack allocation, no OS context switch).

## Building a Minimal Event Loop from Scratch

```python
from __future__ import annotations

import heapq
import selectors
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Coroutine, Deque, Dict, Generator, List,
    Optional, Set, Tuple, TypeVar,
)

T = TypeVar("T")


class Future:
    # A placeholder for a result that will be available later.
    # Tasks await futures; when a future resolves, its waiters are scheduled.

    def __init__(self) -> None:
        self._result: Any = None
        self._exception: Optional[Exception] = None
        self._done: bool = False
        self._callbacks: List[Callable] = []

    def set_result(self, result: Any) -> None:
        if self._done:
            raise RuntimeError("Future already resolved")
        self._result = result
        self._done = True
        self._fire_callbacks()

    def set_exception(self, exc: Exception) -> None:
        if self._done:
            raise RuntimeError("Future already resolved")
        self._exception = exc
        self._done = True
        self._fire_callbacks()

    def result(self) -> Any:
        if not self._done:
            raise RuntimeError("Future not yet resolved")
        if self._exception:
            raise self._exception
        return self._result

    def done(self) -> bool:
        return self._done

    def add_callback(self, cb: Callable) -> None:
        if self._done:
            cb(self)
        else:
            self._callbacks.append(cb)

    def _fire_callbacks(self) -> None:
        for cb in self._callbacks:
            cb(self)
        self._callbacks.clear()

    # Make Future awaitable
    def __await__(self) -> Generator:
        if not self._done:
            yield self  # suspend until resolved
        return self.result()


class Task:
    # Wraps a coroutine and drives it to completion.
    # Each call to _step() advances the coroutine to the next await point.

    _task_counter = 0

    def __init__(self, coro: Coroutine, loop: EventLoop,
                 name: Optional[str] = None) -> None:
        Task._task_counter += 1
        self.id = Task._task_counter
        self.name = name or f"Task-{self.id}"
        self._coro = coro
        self._loop = loop
        self._future = Future()
        self._step()  # start executing immediately

    def _step(self, value: Any = None, exc: Optional[Exception] = None) -> None:
        # Advance the coroutine by one step
        try:
            if exc:
                result = self._coro.throw(type(exc), exc)
            else:
                result = self._coro.send(value)
        except StopIteration as e:
            # Coroutine completed normally
            self._future.set_result(e.value)
            return
        except Exception as e:
            # Coroutine raised an exception
            self._future.set_exception(e)
            return

        # The coroutine yielded a Future -- wait for it
        if isinstance(result, Future):
            result.add_callback(self._on_future_done)
        else:
            # If the coroutine yielded something else, schedule next step
            self._loop.call_soon(self._step)

    def _on_future_done(self, future: Future) -> None:
        try:
            result = future.result()
            self._loop.call_soon(self._step, result)
        except Exception as exc:
            self._loop.call_soon(self._step, None, exc)


@dataclass(order=True)
class TimerHandle:
    # A scheduled callback with a timestamp for the timer heap
    when: float
    callback: Callable = field(compare=False)
    args: tuple = field(compare=False, default_factory=tuple)
    cancelled: bool = field(compare=False, default=False)

    def cancel(self) -> None:
        self.cancelled = True


class EventLoop:
    # A minimal event loop implementation demonstrating the core
    # mechanics of asyncio. Uses selectors for I/O multiplexing
    # and a timer heap for delayed callbacks.

    def __init__(self) -> None:
        self._ready: Deque[Tuple[Callable, tuple]] = deque()
        self._timers: List[TimerHandle] = []
        self._selector = selectors.DefaultSelector()
        self._running = False
        self._task_count = 0

    def run_until_complete(self, coro: Coroutine) -> Any:
        # Run the event loop until the given coroutine completes
        task = self.create_task(coro)
        self._running = True

        while self._running and not task._future.done():
            self._run_once()

        return task._future.result()

    def create_task(self, coro: Coroutine, name: Optional[str] = None) -> Task:
        # Wrap a coroutine in a Task and schedule it
        self._task_count += 1
        return Task(coro, self, name=name)

    def call_soon(self, callback: Callable, *args: Any) -> None:
        # Schedule a callback to run on the next iteration
        self._ready.append((callback, args))

    def call_later(self, delay: float, callback: Callable,
                   *args: Any) -> TimerHandle:
        # Schedule a callback after a delay (in seconds)
        handle = TimerHandle(
            when=time.monotonic() + delay,
            callback=callback,
            args=args,
        )
        heapq.heappush(self._timers, handle)
        return handle

    def add_reader(self, fd: int, callback: Callable, *args: Any) -> None:
        # Register interest in a file descriptor becoming readable
        self._selector.register(fd, selectors.EVENT_READ, (callback, args))

    def remove_reader(self, fd: int) -> None:
        self._selector.unregister(fd)

    def _run_once(self) -> None:
        # One iteration of the event loop:
        # 1. Process all ready callbacks
        # 2. Fire any expired timers
        # 3. Poll for I/O events

        # Calculate how long we can block in select()
        timeout = 0.0 if self._ready else self._get_next_timer_delay()

        # Poll for I/O
        events = self._selector.select(timeout=timeout)
        for key, mask in events:
            callback, args = key.data
            self._ready.append((callback, args))

        # Fire expired timers
        now = time.monotonic()
        while self._timers and self._timers[0].when <= now:
            handle = heapq.heappop(self._timers)
            if not handle.cancelled:
                self._ready.append((handle.callback, handle.args))

        # Process ready callbacks
        # Process a snapshot to avoid infinite loops if callbacks schedule more
        ntodo = len(self._ready)
        for _ in range(ntodo):
            callback, args = self._ready.popleft()
            callback(*args)

    def _get_next_timer_delay(self) -> Optional[float]:
        # Returns seconds until next timer, or None for indefinite block
        while self._timers and self._timers[0].cancelled:
            heapq.heappop(self._timers)
        if self._timers:
            return max(0, self._timers[0].when - time.monotonic())
        return 0.5  # default poll interval


# ---- Async sleep using our event loop ----

async def sleep(seconds: float) -> None:
    # Suspends the current coroutine for the given duration.
    # This is how asyncio.sleep works internally.
    future = Future()
    loop = _current_loop
    loop.call_later(seconds, future.set_result, None)
    await future

_current_loop: EventLoop = None  # set during run_until_complete
```

## Python asyncio Internals Deep Dive

### The Selector Event Loop

CPython's default event loop (`SelectorEventLoop`) uses the `selectors` module, which wraps the OS-specific I/O multiplexing mechanism: **epoll** on Linux, **kqueue** on macOS/BSD, and **select** on Windows (or IOCP via `ProactorEventLoop`).

### Task Scheduling

asyncio's scheduling is **FIFO with no priorities**: tasks are placed in a ready queue and executed in order. **However**, this means a burst of CPU-bound coroutines can starve I/O-bound coroutines. The **best practice** is to insert `await asyncio.sleep(0)` in long-running loops to yield control back to the event loop, allowing I/O callbacks to fire.

```python
import asyncio
from typing import AsyncGenerator, List

async def cpu_bound_with_yielding(data: List[int]) -> int:
    # Demonstrates cooperative yielding in a CPU-bound coroutine.
    # Without the sleep(0), this would block the event loop for
    # the entire computation, starving other coroutines.
    total = 0
    for i, value in enumerate(data):
        total += value * value  # some computation
        if i % 10000 == 0:
            await asyncio.sleep(0)  # yield to event loop
    return total


async def monitor_progress() -> None:
    # This coroutine would be starved without cooperative yielding
    for i in range(5):
        print(f"Monitor heartbeat {i}")
        await asyncio.sleep(0.1)


async def demonstrate_cooperation() -> None:
    # Run CPU-bound and I/O-bound tasks concurrently
    data = list(range(100_000))

    # Both tasks share the single event loop thread
    result, _ = await asyncio.gather(
        cpu_bound_with_yielding(data),
        monitor_progress(),
    )
    print(f"Computation result: {result}")


# --- Inspecting asyncio internals ---

async def inspect_event_loop() -> None:
    # Demonstrates how to inspect the running event loop
    loop = asyncio.get_running_loop()

    # The loop tracks all active tasks
    all_tasks = asyncio.all_tasks()
    current = asyncio.current_task()

    print(f"Loop implementation: {type(loop).__name__}")
    print(f"Active tasks: {len(all_tasks)}")
    print(f"Current task: {current.get_name()}")

    # Create a low-level future
    future = loop.create_future()

    # Schedule a callback to resolve it
    loop.call_later(0.1, future.set_result, "resolved!")

    result = await future
    print(f"Future resolved with: {result}")
```

## Cooperative Scheduling Implications

### The GIL Interaction

In CPython, the Global Interpreter Lock (GIL) means that threads do not achieve true parallelism for CPU-bound work anyway. **Therefore**, asyncio's single-threaded model is not actually a limitation for I/O-bound workloads -- it is an advantage because it eliminates thread synchronization overhead entirely.

**However**, for CPU-bound work, you must use `loop.run_in_executor()` with a `ProcessPoolExecutor` to achieve real parallelism:

```python
import asyncio
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from typing import List

# CPU-bound work MUST be offloaded to a process pool
def heavy_computation(n: int) -> int:
    # This runs in a separate process to bypass the GIL
    total = 0
    for i in range(n):
        total += i * i
    return total


async def hybrid_async_processing(items: List[int]) -> List[int]:
    # Demonstrates mixing async I/O with CPU-bound work.
    # I/O operations use the event loop directly.
    # CPU-bound operations are offloaded to processes.
    loop = asyncio.get_running_loop()

    # Create a process pool for CPU-bound work
    with ProcessPoolExecutor(max_workers=4) as pool:
        # Submit CPU work to the process pool
        futures = [
            loop.run_in_executor(pool, heavy_computation, item)
            for item in items
        ]
        results = await asyncio.gather(*futures)
        return list(results)


async def benchmark_async_patterns() -> None:
    # Compare sequential, threaded, and process-based execution
    items = [10_000_000] * 4

    # Sequential (blocks event loop)
    start = time.perf_counter()
    sequential_results = [heavy_computation(n) for n in items]
    seq_time = time.perf_counter() - start

    # Process pool (true parallelism)
    start = time.perf_counter()
    parallel_results = await hybrid_async_processing(items)
    par_time = time.perf_counter() - start

    print(f"Sequential: {seq_time:.3f}s")
    print(f"Parallel:   {par_time:.3f}s")
    print(f"Speedup:    {seq_time / par_time:.1f}x")
```

## Summary and Key Takeaways

- Async/await desugars to **coroutine state machines** where each `await` point becomes a state transition; local variables are stored as object attributes to survive suspension
- The **event loop** is the scheduler: it maintains a ready queue, a timer heap, and an I/O multiplexer (epoll/kqueue/IOCP), processing callbacks in FIFO order each iteration
- **Cooperative scheduling** means coroutines must explicitly yield via `await`; a coroutine that never yields blocks the entire event loop, which is the most common async programming **pitfall**
- Python's asyncio uses **`selectors`** for I/O multiplexing and wraps coroutines in **`Task`** objects that drive the coroutine's state machine by calling `send()` and `throw()`
- **Best practice**: use `await asyncio.sleep(0)` to yield in CPU-bound loops, offload heavy computation to `ProcessPoolExecutor`, and never call blocking I/O functions directly in async code
- **Trade-off**: async/await provides excellent throughput for I/O-bound workloads (thousands of concurrent connections on one thread) but adds complexity to debugging (stack traces are fragmented), testing (requires async test runners), and error handling (exceptions propagate differently through `gather` and `TaskGroup`)
- **Because** the GIL already prevents thread-level parallelism for CPU work, asyncio's single-threaded model is not a real limitation for I/O -- it eliminates thread synchronization overhead entirely
""",
    ),

    # --- 4. Software Transactional Memory ---
    (
        "concurrency/software-transactional-memory-stm",
        "Explain Software Transactional Memory in depth including optimistic concurrency control, conflict detection and resolution strategies, retry and orElse combinators for composable blocking, comparison with lock-based approaches, and provide a complete Python STM implementation with transactional variables nested transactions and performance benchmarks.",
        r"""
# Software Transactional Memory: Optimistic Concurrency Without Locks

## The Problem STM Solves

Lock-based concurrency has a composability problem. If you have two thread-safe operations -- transferring money from account A to B, and transferring money from C to D -- composing them into a single atomic operation (transfer A->B AND C->D) requires knowing the internal locking strategy of each operation. You cannot simply call both operations sequentially because the intermediate state (A->B done, C->D not started) is visible to other threads. This is **fundamentally** a composability failure: thread-safe components do not compose into thread-safe systems.

Software Transactional Memory solves this by borrowing the **transaction** concept from databases. Code blocks execute **optimistically** -- they read and write shared variables without acquiring any locks. At commit time, the runtime checks whether any variables read during the transaction were modified by another transaction. If so, the transaction is **rolled back and retried automatically**. If not, all writes become visible atomically.

**Best practice**: think of STM as database transactions for in-memory shared state. The same intuitions apply: keep transactions short, minimize the read set, and avoid side effects inside transactions (because retries will re-execute them).

**Common mistake**: performing I/O or other non-reversible side effects inside an STM transaction. Because transactions can be retried an arbitrary number of times, any side effect will be repeated. Only read and write transactional variables inside the transaction; perform I/O after the transaction commits.

## How STM Works: Optimistic Concurrency Control

### The TVar Abstraction

The fundamental unit of STM is the **transactional variable** (TVar). A TVar holds a value that can only be read or written inside a transaction. Each TVar maintains a **version number** that is incremented on every committed write.

### Transaction Execution

1. **Begin**: create a transaction log (read set + write set)
2. **Read**: when reading a TVar, record (tvar, version_read) in the read set; if already in the write set, return the written value
3. **Write**: when writing a TVar, record (tvar, new_value) in the write set; do NOT modify the actual TVar yet
4. **Validate**: at commit time, check that every TVar in the read set still has the same version as when it was read
5. **Commit**: if validation passes, atomically apply all writes and increment version numbers
6. **Retry**: if validation fails, discard the write set and re-execute the entire transaction

### Conflict Detection Strategies

**Read-set validation** (used by GHC Haskell's STM): at commit time, re-read every TVar in the read set and compare versions. This detects **write-read conflicts**: another transaction wrote to a TVar that we read.

**Write-set intersection** (optimistic): only check if the write sets of concurrent transactions overlap. This allows more concurrency but can produce inconsistent reads during execution (which may cause exceptions before commit). **Therefore**, Haskell's approach of validating the entire read set is safer.

## Complete Python STM Implementation

```python
from __future__ import annotations

import copy
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, Generic, List, Optional, Set, TypeVar, Tuple,
)

T = TypeVar("T")

# Global lock for commit-time validation
# This serializes commits but NOT transaction execution.
# Transactions execute concurrently and optimistically;
# only the brief commit phase is serialized.
_commit_lock = threading.Lock()

# Global version clock for ordering
_global_clock = 0
_clock_lock = threading.Lock()


def _next_version() -> int:
    global _global_clock
    with _clock_lock:
        _global_clock += 1
        return _global_clock


class TVar(Generic[T]):
    # Transactional Variable: the fundamental unit of STM.
    # Can only be read/written inside a transaction context.

    def __init__(self, initial: T) -> None:
        self._value: T = initial
        self._version: int = 0
        self._lock = threading.Lock()

    def _read_committed(self) -> Tuple[T, int]:
        # Read the committed value and version (used at commit time)
        with self._lock:
            return self._value, self._version

    def _write_committed(self, value: T, version: int) -> None:
        # Write a new committed value (only called during commit)
        with self._lock:
            self._value = value
            self._version = version

    @property
    def value(self) -> T:
        # Public read -- must be inside a transaction
        tx = _current_transaction.get()
        if tx is None:
            raise RuntimeError("TVar.value can only be read inside a transaction")
        return tx.read(self)

    @value.setter
    def value(self, new_value: T) -> None:
        # Public write -- must be inside a transaction
        tx = _current_transaction.get()
        if tx is None:
            raise RuntimeError("TVar.value can only be set inside a transaction")
        tx.write(self, new_value)


# Thread-local storage for the current transaction
_current_transaction: threading.local = threading.local()


class RetryException(Exception):
    # Raised by retry() to indicate the transaction should
    # block until one of its read TVars changes
    pass


class Transaction:
    # Represents an in-flight STM transaction.
    # Maintains a read set (TVars read + their versions)
    # and a write set (TVars written + their new values).

    def __init__(self) -> None:
        self.read_set: Dict[int, Tuple[TVar, int]] = {}  # id(tvar) -> (tvar, version)
        self.write_set: Dict[int, Tuple[TVar, Any]] = {}  # id(tvar) -> (tvar, value)
        self.start_version = _global_clock

    def read(self, tvar: TVar[T]) -> T:
        # Read a TVar within this transaction
        tvar_id = id(tvar)

        # If we have already written to this TVar, return our written value
        if tvar_id in self.write_set:
            return self.write_set[tvar_id][1]

        # If we have already read this TVar, return the cached value
        if tvar_id in self.read_set:
            tvar_ref, version = self.read_set[tvar_id]
            value, current_version = tvar_ref._read_committed()
            if current_version != version:
                # The TVar was modified since we read it -- abort
                raise ConflictException("Read conflict detected during read")
            return value

        # First read of this TVar -- record in read set
        value, version = tvar._read_committed()
        self.read_set[tvar_id] = (tvar, version)
        return value

    def write(self, tvar: TVar[T], value: T) -> None:
        # Write a TVar within this transaction (buffered, not committed)
        tvar_id = id(tvar)
        # Ensure the TVar is in our read set for conflict detection
        if tvar_id not in self.read_set and tvar_id not in self.write_set:
            self.read(tvar)  # establish the read version
        self.write_set[tvar_id] = (tvar, value)

    def validate(self) -> bool:
        # Check that all TVars in the read set still have the same version.
        # This is the key correctness check: if any TVar was modified
        # by another committed transaction, our reads may be inconsistent.
        for tvar_id, (tvar, expected_version) in self.read_set.items():
            _, current_version = tvar._read_committed()
            if current_version != expected_version:
                return False
        return True

    def commit(self) -> bool:
        # Atomically validate and apply all writes
        with _commit_lock:
            if not self.validate():
                return False
            # Apply all writes atomically
            new_version = _next_version()
            for tvar_id, (tvar, value) in self.write_set.items():
                tvar._write_committed(value, new_version)
            return True


class ConflictException(Exception):
    pass


def atomically(func: Callable[[], T], max_retries: int = 1000) -> T:
    # Execute a function as an STM transaction.
    # Automatically retries on conflict.
    for attempt in range(max_retries):
        tx = Transaction()
        _current_transaction.__dict__["tx"] = tx

        # Monkey-patch thread local to use our custom attribute
        old_get = getattr(_current_transaction, "get", None)
        _current_transaction.get = lambda: tx

        try:
            result = func()
            if tx.commit():
                return result
            # Commit failed -- retry with exponential backoff
        except ConflictException:
            pass  # Read conflict -- retry
        except RetryException:
            # Block until a read TVar changes
            _wait_for_change(tx)
        finally:
            _current_transaction.get = lambda: None

    raise RuntimeError(f"STM transaction failed after {max_retries} retries")


def retry() -> None:
    # Block the current transaction until one of the TVars
    # it has read is modified. This is how STM implements
    # composable blocking -- the equivalent of a condition variable
    # but without explicit signaling.
    raise RetryException()


def or_else(tx_a: Callable[[], T], tx_b: Callable[[], T]) -> T:
    # Composable choice: try tx_a first. If it calls retry(),
    # try tx_b instead. If both retry, retry the whole thing.
    # This is the STM equivalent of select/alt in CSP.
    try:
        return tx_a()
    except RetryException:
        return tx_b()


def _wait_for_change(tx: Transaction) -> None:
    # Simplified blocking: sleep briefly and hope a TVar changed.
    # A production implementation would use condition variables
    # per TVar to wake waiters efficiently.
    time.sleep(0.001)
```

### Bank Transfer Example

```python
import threading
import time
from typing import List

# Using the STM framework defined above

def create_accounts(count: int, initial_balance: float) -> List[TVar[float]]:
    return [TVar(initial_balance) for _ in range(count)]


def transfer(from_acct: TVar[float], to_acct: TVar[float],
             amount: float) -> None:
    # Transfer money between accounts atomically.
    # If either account is modified concurrently, the
    # transaction retries automatically.
    def tx() -> None:
        balance_from = from_acct.value
        if balance_from < amount:
            retry()  # block until sufficient funds available
        from_acct.value = balance_from - amount
        to_acct.value = to_acct.value + amount
    atomically(tx)


def total_balance(accounts: List[TVar[float]]) -> float:
    # Read all balances atomically -- guaranteed consistent snapshot
    def tx() -> float:
        return sum(acct.value for acct in accounts)
    return atomically(tx)


def stm_benchmark() -> None:
    # Benchmark: many threads transferring between accounts
    num_accounts = 10
    num_threads = 8
    transfers_per_thread = 500
    initial_balance = 1000.0

    accounts = create_accounts(num_accounts, initial_balance)
    expected_total = num_accounts * initial_balance

    def worker() -> None:
        import random
        for _ in range(transfers_per_thread):
            i, j = random.sample(range(num_accounts), 2)
            amount = random.uniform(1.0, 50.0)
            transfer(accounts[i], accounts[j], amount)

    start = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start

    final_total = total_balance(accounts)
    total_transfers = num_threads * transfers_per_thread

    print(f"Accounts: {num_accounts}, Threads: {num_threads}")
    print(f"Total transfers: {total_transfers} in {elapsed:.3f}s")
    print(f"Throughput: {total_transfers / elapsed:.0f} tx/s")
    print(f"Expected total: {expected_total:.2f}")
    print(f"Actual total:   {final_total:.2f}")
    print(f"Conservation:   {'PASS' if abs(final_total - expected_total) < 0.01 else 'FAIL'}")
```

## STM vs Locks: When to Choose What

| Dimension | STM | Locks |
|-----------|-----|-------|
| **Composability** | Transactions compose freely | Locks do not compose safely |
| **Deadlock** | Impossible (no lock ordering) | Possible if ordering violated |
| **Read contention** | Readers never block each other | Readers block with write locks |
| **Write contention** | Retries waste CPU | Waiters sleep efficiently |
| **Debugging** | Transaction replay is deterministic | Lock bugs are non-deterministic |
| **Performance** | Overhead from versioning and validation | Minimal overhead per operation |

**Trade-off**: STM excels when read-heavy workloads dominate, transactions are short, and composability matters. Locks excel when write contention is high and critical sections are well-defined. **However**, the correctness advantages of STM often outweigh the performance costs because concurrency bugs in lock-based code are notoriously hard to find and fix.

### Composable or_else in Practice

```python
from typing import Optional

# Using the STM framework defined above

def withdraw_from_primary(primary: TVar[float], amount: float) -> float:
    # Try to withdraw from primary account
    bal = primary.value
    if bal < amount:
        retry()  # block if insufficient funds
    primary.value = bal - amount
    return bal - amount

def withdraw_from_backup(backup: TVar[float], amount: float) -> float:
    # Fallback: withdraw from backup account
    bal = backup.value
    if bal < amount:
        retry()  # block if insufficient funds here too
    backup.value = bal - amount
    return bal - amount

def smart_withdraw(primary: TVar[float], backup: TVar[float],
                   amount: float) -> float:
    # Composable choice: try primary first, fall back to backup.
    # If BOTH retry, the entire transaction blocks until either
    # account has sufficient funds. This composability is
    # impossible to achieve cleanly with locks or condition variables.
    def tx() -> float:
        return or_else(
            lambda: withdraw_from_primary(primary, amount),
            lambda: withdraw_from_backup(backup, amount),
        )
    return atomically(tx)
```

## Summary and Key Takeaways

- **Software Transactional Memory** uses optimistic concurrency control: transactions execute without locks, and conflicts are detected at commit time by validating the read set
- The **TVar** (transactional variable) is the fundamental unit -- all reads and writes inside a transaction are buffered and only become visible on successful commit
- **retry()** implements composable blocking: a transaction that cannot proceed blocks until a relevant TVar changes, replacing manual condition variable management
- **or_else** provides composable choice: try one transaction, fall back to another if the first retries, enabling complex coordination patterns without explicit signaling
- **Pitfall**: never perform side effects (I/O, logging, network calls) inside a transaction -- they will be replayed on every retry; instead, collect results and perform side effects after commit
- **Best practice**: keep transactions short and minimize the read set to reduce conflict probability; high-contention transactions with large read sets will suffer excessive retries
- The **trade-off** between STM and locks mirrors the database choice between optimistic and pessimistic concurrency: STM (optimistic) wins when conflicts are rare; locks (pessimistic) win when conflicts are frequent
""",
    ),

    # --- 5. Parallel Algorithms ---
    (
        "concurrency/parallel-algorithms-work-stealing-fork-join",
        "Explain parallel algorithms in depth including work stealing schedulers and their deque-based design, fork-join parallelism and recursive decomposition, parallel prefix sum scan algorithm, MapReduce programming model, and provide complete Python implementations using concurrent.futures with performance analysis comparing sequential and parallel execution across different workload types.",
        r"""
# Parallel Algorithms: Work Stealing, Fork-Join, Prefix Sum, and MapReduce

## Why Parallelism is Hard

Sequential algorithms have a simple cost model: count the operations. Parallel algorithms must reason about **work** (total operations), **span** (longest sequential dependency chain), **communication overhead** (data movement between threads/cores), and **load balancing** (keeping all cores busy). The theoretical speedup is bounded by **Amdahl's Law**: if `f` is the fraction of work that must be sequential, the maximum speedup with `p` processors is `1 / (f + (1-f)/p)`. Even with infinite processors, if 5% of your work is sequential, you cannot exceed 20x speedup.

**Therefore**, the first step in parallelizing an algorithm is identifying the **critical path** -- the longest chain of sequential dependencies. Reducing the span (depth) of the computation graph is often more important than reducing the total work.

**Common mistake**: assuming that more threads always means faster execution. Thread creation, synchronization, and cache coherency overhead can easily dominate the actual computation for fine-grained tasks. There is a **crossover point** below which sequential execution is faster, and finding this point is essential for practical parallelism.

## Work Stealing: The Gold Standard Scheduler

Work stealing is the scheduling algorithm used by Java's ForkJoinPool, Intel TBB, Cilk, Rayon (Rust), and Go's goroutine scheduler. Its core insight is that **each worker has a local double-ended queue (deque) of tasks**. Workers push and pop tasks from their own deque (LIFO, for cache locality), and idle workers **steal** from the top of other workers' deques (FIFO, for large tasks).

### Why LIFO Local + FIFO Steal?

- **LIFO local execution** exploits temporal locality: the most recently created task is likely to access data that is still in the L1/L2 cache
- **FIFO stealing** takes the oldest (and usually largest) tasks, which amortizes the overhead of cross-thread communication -- stealing is expensive, so steal big tasks that will keep the thief busy for a while

### Theoretical Guarantee

Blumofe and Leiserson proved that a work-stealing scheduler executes a computation with work `W` and span `S` on `p` processors in expected time `O(W/p + S)`. This is **asymptotically optimal** -- you cannot do better without knowing the computation graph in advance.

```python
from __future__ import annotations

import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Deque, Dict, Generic, List, Optional, TypeVar,
)
from concurrent.futures import Future

T = TypeVar("T")


class WorkStealingDeque(Generic[T]):
    # A simplified work-stealing deque.
    # The owner pushes/pops from the bottom (LIFO).
    # Thieves steal from the top (FIFO).
    # In production, this uses atomic operations and
    # the Chase-Lev deque algorithm for lock-freedom.

    def __init__(self) -> None:
        self._deque: Deque[T] = deque()
        self._lock = threading.Lock()

    def push(self, item: T) -> None:
        # Owner pushes to bottom
        with self._lock:
            self._deque.append(item)

    def pop(self) -> Optional[T]:
        # Owner pops from bottom (LIFO)
        with self._lock:
            if self._deque:
                return self._deque.pop()
            return None

    def steal(self) -> Optional[T]:
        # Thief steals from top (FIFO -- oldest/largest task)
        with self._lock:
            if self._deque:
                return self._deque.popleft()
            return None

    def __len__(self) -> int:
        with self._lock:
            return len(self._deque)


@dataclass
class WorkItem:
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    future: Future = field(default_factory=Future)

    def execute(self) -> None:
        try:
            result = self.func(*self.args, **self.kwargs)
            self.future.set_result(result)
        except Exception as exc:
            self.future.set_exception(exc)


class WorkStealingPool:
    # A work-stealing thread pool demonstrating the core algorithm.
    # Each worker maintains its own deque. Idle workers steal
    # from random other workers' deques.

    def __init__(self, num_workers: int = 4) -> None:
        self.num_workers = num_workers
        self._deques: List[WorkStealingDeque[WorkItem]] = [
            WorkStealingDeque() for _ in range(num_workers)
        ]
        self._workers: List[threading.Thread] = []
        self._running = True
        self._submit_counter = 0
        self._submit_lock = threading.Lock()

        for i in range(num_workers):
            t = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            self._workers.append(t)
            t.start()

    def submit(self, func: Callable, *args: Any, **kwargs: Any) -> Future:
        # Submit work to the pool, distributing round-robin
        item = WorkItem(func=func, args=args, kwargs=kwargs)
        with self._submit_lock:
            target = self._submit_counter % self.num_workers
            self._submit_counter += 1
        self._deques[target].push(item)
        return item.future

    def _worker_loop(self, worker_id: int) -> None:
        my_deque = self._deques[worker_id]
        backoff = 0

        while self._running:
            # Try to get work from own deque (LIFO)
            item = my_deque.pop()

            if item is None:
                # No local work -- try to steal from a random other worker
                victim = random.randint(0, self.num_workers - 1)
                if victim != worker_id:
                    item = self._deques[victim].steal()

            if item is not None:
                item.execute()
                backoff = 0
            else:
                # No work anywhere -- back off to avoid busy-waiting
                backoff = min(backoff + 1, 10)
                time.sleep(0.001 * backoff)

    def shutdown(self) -> None:
        self._running = False
        for t in self._workers:
            t.join(timeout=2.0)
```

## Fork-Join Parallelism

Fork-join is the **recursive decomposition pattern** that naturally pairs with work stealing. A task splits (forks) into subtasks, which execute in parallel, and then the results are combined (joined). This maps directly to divide-and-conquer algorithms.

### Parallel Merge Sort

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import List, TypeVar
import time

T = TypeVar("T")

SEQUENTIAL_THRESHOLD = 1024  # Below this, use sequential sort

def parallel_merge_sort(arr: List[int], pool: ThreadPoolExecutor,
                        depth: int = 0, max_depth: int = 3) -> List[int]:
    # Fork-join parallel merge sort.
    # Recursively splits the array, sorts halves in parallel,
    # and merges the results.
    #
    # The max_depth parameter limits parallelism to avoid
    # the overhead of creating too many tasks for small arrays.

    if len(arr) <= SEQUENTIAL_THRESHOLD or depth >= max_depth:
        return sorted(arr)  # fall back to sequential sort

    mid = len(arr) // 2
    left_half = arr[:mid]
    right_half = arr[mid:]

    # Fork: submit both halves for parallel execution
    left_future = pool.submit(
        parallel_merge_sort, left_half, pool, depth + 1, max_depth
    )
    right_future = pool.submit(
        parallel_merge_sort, right_half, pool, depth + 1, max_depth
    )

    # Join: wait for both halves to complete
    left_sorted = left_future.result()
    right_sorted = right_future.result()

    # Merge the sorted halves
    return _merge(left_sorted, right_sorted)


def _merge(left: List[int], right: List[int]) -> List[int]:
    # Standard merge operation: O(n) time, O(n) space
    result: List[int] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result


def benchmark_merge_sort() -> None:
    import random
    sizes = [10_000, 100_000, 1_000_000]

    for size in sizes:
        data = [random.randint(0, 10_000_000) for _ in range(size)]

        # Sequential
        start = time.perf_counter()
        seq_result = sorted(data)
        seq_time = time.perf_counter() - start

        # Parallel fork-join
        with ThreadPoolExecutor(max_workers=4) as pool:
            start = time.perf_counter()
            par_result = parallel_merge_sort(data.copy(), pool)
            par_time = time.perf_counter() - start

        assert par_result == seq_result, "Sort results differ!"
        speedup = seq_time / par_time if par_time > 0 else float('inf')
        print(f"n={size:>10,}: seq={seq_time:.4f}s, "
              f"par={par_time:.4f}s, speedup={speedup:.2f}x")
```

## Parallel Prefix Sum (Scan)

The parallel prefix sum is a **fundamental building block** for parallel algorithms. Given an array `[a, b, c, d]` and an associative operator `+`, the inclusive prefix sum is `[a, a+b, a+b+c, a+b+c+d]`. It appears in sorting (radix sort), compaction (stream filtering), tree operations, and GPU programming (where it is called "scan").

### The Blelloch Algorithm

The Blelloch scan runs in `O(n)` work and `O(log n)` span, achieving optimal work efficiency. It has two phases:

1. **Up-sweep (reduce)**: build a balanced tree of partial sums bottom-up
2. **Down-sweep (distribute)**: propagate prefix sums top-down using the tree

```python
import math
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, List, TypeVar
import itertools

T = TypeVar("T")


def sequential_prefix_sum(arr: List[int]) -> List[int]:
    # O(n) sequential inclusive prefix sum
    result = [0] * len(arr)
    result[0] = arr[0]
    for i in range(1, len(arr)):
        result[i] = result[i - 1] + arr[i]
    return result


def parallel_prefix_sum(arr: List[int], num_workers: int = 4) -> List[int]:
    # Three-phase parallel prefix sum:
    # Phase 1: Each worker computes local prefix sums on its chunk
    # Phase 2: Compute prefix sums of chunk totals (sequential, O(p))
    # Phase 3: Each worker adds the prefix of previous chunks to its elements
    #
    # Work: O(n), Span: O(n/p + p), which is O(n/p) when p << n

    n = len(arr)
    if n == 0:
        return []
    if n <= num_workers:
        return sequential_prefix_sum(arr)

    chunk_size = math.ceil(n / num_workers)
    chunks = [arr[i:i + chunk_size] for i in range(0, n, chunk_size)]
    num_chunks = len(chunks)

    # Phase 1: parallel local prefix sums
    local_results: List[List[int]] = [[] for _ in range(num_chunks)]
    chunk_totals: List[int] = [0] * num_chunks

    def compute_local(idx: int) -> None:
        chunk = chunks[idx]
        local = sequential_prefix_sum(chunk)
        local_results[idx] = local
        chunk_totals[idx] = local[-1]  # total of this chunk

    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = [pool.submit(compute_local, i) for i in range(num_chunks)]
        for f in futures:
            f.result()

    # Phase 2: sequential prefix sum of chunk totals
    # This is O(p) where p = num_workers, so it is negligible
    offsets = [0] * num_chunks
    for i in range(1, num_chunks):
        offsets[i] = offsets[i - 1] + chunk_totals[i - 1]

    # Phase 3: parallel offset addition
    def apply_offset(idx: int) -> None:
        offset = offsets[idx]
        for j in range(len(local_results[idx])):
            local_results[idx][j] += offset

    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = [pool.submit(apply_offset, i) for i in range(num_chunks)]
        for f in futures:
            f.result()

    # Flatten results
    return list(itertools.chain.from_iterable(local_results))


def benchmark_prefix_sum() -> None:
    import random
    sizes = [100_000, 1_000_000, 10_000_000]
    workers = [1, 2, 4, 8]

    for size in sizes:
        data = [random.randint(1, 100) for _ in range(size)]

        # Sequential baseline
        start = time.perf_counter()
        expected = sequential_prefix_sum(data)
        seq_time = time.perf_counter() - start

        print(f"\nn={size:>12,}, sequential: {seq_time:.4f}s")

        for w in workers:
            start = time.perf_counter()
            result = parallel_prefix_sum(data, num_workers=w)
            par_time = time.perf_counter() - start

            correct = result == expected
            speedup = seq_time / par_time if par_time > 0 else float('inf')
            print(f"  workers={w}: {par_time:.4f}s, "
                  f"speedup={speedup:.2f}x, correct={correct}")
```

## MapReduce: Parallel Data Processing at Scale

MapReduce is both an **algorithm pattern** and a **system architecture**. The pattern decomposes computation into two phases: **Map** (apply a function independently to each element, producing key-value pairs) and **Reduce** (aggregate values by key). **Because** map operations are embarrassingly parallel and reduce operations are associative, the pattern parallelizes naturally.

### Python concurrent.futures MapReduce

```python
from __future__ import annotations

import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import (
    ProcessPoolExecutor, ThreadPoolExecutor, as_completed,
)
from dataclasses import dataclass
from typing import (
    Any, Callable, Dict, Generic, Iterable, List, Tuple, TypeVar,
)

K = TypeVar("K")
V = TypeVar("V")
R = TypeVar("R")


class MapReduceFramework(Generic[K, V, R]):
    # A generic MapReduce implementation using concurrent.futures.
    # Supports both thread and process-based parallelism.

    def __init__(self, num_mappers: int = 4, num_reducers: int = 2,
                 use_processes: bool = False) -> None:
        self.num_mappers = num_mappers
        self.num_reducers = num_reducers
        self._executor_class = (
            ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        )

    def execute(
        self,
        data: List[Any],
        mapper: Callable[[Any], List[Tuple[K, V]]],
        reducer: Callable[[K, List[V]], R],
    ) -> Dict[K, R]:
        # Execute a complete MapReduce pipeline:
        # 1. Partition input data among mappers
        # 2. Run map phase in parallel
        # 3. Shuffle: group intermediate results by key
        # 4. Run reduce phase in parallel

        # --- Map Phase ---
        chunk_size = max(1, len(data) // self.num_mappers)
        chunks = [
            data[i:i + chunk_size]
            for i in range(0, len(data), chunk_size)
        ]

        intermediate: List[Tuple[K, V]] = []
        with self._executor_class(max_workers=self.num_mappers) as pool:
            futures = {
                pool.submit(self._map_chunk, chunk, mapper): i
                for i, chunk in enumerate(chunks)
            }
            for future in as_completed(futures):
                intermediate.extend(future.result())

        # --- Shuffle Phase ---
        grouped: Dict[K, List[V]] = defaultdict(list)
        for key, value in intermediate:
            grouped[key].append(value)

        # --- Reduce Phase ---
        results: Dict[K, R] = {}
        with self._executor_class(max_workers=self.num_reducers) as pool:
            futures = {
                pool.submit(reducer, key, values): key
                for key, values in grouped.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                results[key] = future.result()

        return results

    @staticmethod
    def _map_chunk(
        chunk: List[Any],
        mapper: Callable[[Any], List[Tuple[K, V]]],
    ) -> List[Tuple[K, V]]:
        # Apply mapper to each element in the chunk
        results: List[Tuple[K, V]] = []
        for item in chunk:
            results.extend(mapper(item))
        return results


# --- Example: Parallel Word Count ---

def word_count_mapper(text: str) -> List[Tuple[str, int]]:
    # Emit (word, 1) for each word in the text
    words = re.findall(r'\w+', text.lower())
    return [(word, 1) for word in words]


def word_count_reducer(word: str, counts: List[int]) -> int:
    # Sum all counts for this word
    return sum(counts)


def parallel_word_count_demo() -> None:
    # Generate sample data
    sample_texts = [
        "the quick brown fox jumps over the lazy dog",
        "the fox is quick and the dog is lazy",
        "brown foxes are quick but lazy dogs sleep",
        "the dog and the fox became friends however",
    ] * 10000  # repeat for meaningful benchmark

    framework = MapReduceFramework(
        num_mappers=4, num_reducers=2, use_processes=False
    )

    start = time.perf_counter()
    results = framework.execute(
        sample_texts, word_count_mapper, word_count_reducer
    )
    parallel_time = time.perf_counter() - start

    # Sequential baseline
    start = time.perf_counter()
    counter: Counter = Counter()
    for text in sample_texts:
        words = re.findall(r'\w+', text.lower())
        counter.update(words)
    sequential_time = time.perf_counter() - start

    top_10 = sorted(results.items(), key=lambda x: x[1], reverse=True)[:10]
    print("Top 10 words:")
    for word, count in top_10:
        print(f"  {word}: {count}")

    speedup = sequential_time / parallel_time if parallel_time > 0 else 0
    print(f"\nSequential: {sequential_time:.4f}s")
    print(f"Parallel:   {parallel_time:.4f}s")
    print(f"Speedup:    {speedup:.2f}x")
```

## Performance Analysis: When Parallelism Pays Off

### The Crossover Point

**Best practice**: always measure the sequential baseline before parallelizing. Python's `concurrent.futures` has significant overhead per task submission (~50-100 microseconds for threads, ~1-10 milliseconds for processes). **Therefore**, the computation per task must be large enough to amortize this overhead.

| Workload Type | Min Work per Task | Recommended Executor |
|---------------|-------------------|---------------------|
| CPU-bound, GIL-free (NumPy, C extensions) | 1ms | ThreadPoolExecutor |
| CPU-bound, pure Python | 10ms | ProcessPoolExecutor |
| I/O-bound (network, disk) | Any | ThreadPoolExecutor or asyncio |
| Mixed CPU + I/O | Varies | Hybrid: asyncio + ProcessPoolExecutor |

### Pitfall: The GIL and CPU-Bound Work

For pure Python CPU-bound work, `ThreadPoolExecutor` provides **zero speedup** because the GIL serializes execution. You must use `ProcessPoolExecutor`, which incurs serialization overhead for passing data between processes. **However**, for NumPy/pandas operations that release the GIL, `ThreadPoolExecutor` works perfectly.

### Practical Guidelines

1. **Profile first**: use `cProfile` or `py-spy` to identify the actual bottleneck
2. **Chunk appropriately**: too many small tasks waste overhead; too few large tasks underutilize cores
3. **Watch memory**: `ProcessPoolExecutor` serializes arguments via pickle -- large data transfers can negate parallelism gains
4. **Use `as_completed`** for heterogeneous tasks to process results as they arrive rather than waiting for all to finish
5. **Set `max_workers` deliberately**: more workers than CPU cores causes context-switch overhead without additional throughput for CPU-bound work

## Summary and Key Takeaways

- **Work stealing** is the optimal dynamic scheduling algorithm: workers maintain local deques (LIFO for locality, FIFO for stealing) and achieve `O(W/p + S)` expected execution time
- **Fork-join** naturally maps divide-and-conquer algorithms to parallel execution; the key is choosing a **sequential threshold** below which parallel overhead exceeds the benefit
- **Parallel prefix sum** (scan) is a fundamental primitive with `O(n)` work and `O(log n)` span; the three-phase approach (local scan, aggregate scan, offset addition) is practical and efficient
- **MapReduce** decomposes data processing into embarrassingly parallel map operations and associative reduce operations; Python's `concurrent.futures` provides a clean API for this pattern
- **Pitfall**: Python's GIL means `ThreadPoolExecutor` provides no speedup for pure-Python CPU-bound work -- use `ProcessPoolExecutor` instead, accepting the serialization overhead
- **Trade-off**: parallelism adds complexity (debugging, non-determinism, overhead) that is only justified when the workload is large enough and the sequential bottleneck is proven by profiling
- **Best practice**: always start with the sequential version, measure its performance, and only parallelize the proven bottleneck with appropriate chunk sizes and executor selection
""",
    ),
]
