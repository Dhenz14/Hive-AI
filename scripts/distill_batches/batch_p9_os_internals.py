"""
Batch P9 — Operating System Internals
Covers: virtual memory and page tables, process scheduling algorithms,
file system internals, inter-process communication, container internals.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Virtual Memory and Page Tables ---
    (
        "os-internals/virtual-memory-page-tables-fault-handling",
        "Explain virtual memory internals including multi-level page tables, TLB caching, page fault handling with demand paging, huge pages for TLB efficiency, copy-on-write fork semantics, and LRU page replacement with a Python simulator implementing page table walks and fault tracking",
        r"""# Virtual Memory and Page Tables: From Hardware to Simulation

## Why Virtual Memory Exists

Every modern operating system relies on **virtual memory** to provide each process with its own isolated address space. Without virtual memory, processes would need to coordinate physical memory usage directly, leading to fragmentation, security vulnerabilities, and impossible multitasking. The **Memory Management Unit (MMU)**, a hardware component on the CPU, translates virtual addresses to physical addresses on every memory access. This translation is governed by **page tables**, hierarchical data structures maintained by the OS kernel.

The key insight is that virtual memory decouples the address a program uses from the physical RAM location, therefore the OS can place pages anywhere in physical memory (or even on disk) without the process knowing. This enables **demand paging**, **memory-mapped files**, **copy-on-write**, and **memory overcommit**.

## Multi-Level Page Tables

### The Problem with Flat Page Tables

A single-level page table for a 64-bit address space would require an astronomical number of entries. Even with 4KB pages, a 48-bit virtual address space (used by x86-64) would need 2^36 entries, each 8 bytes, totaling **512 GB** just for the page table. This is clearly impractical, because most of that address space is unused.

### Hierarchical Solution

x86-64 uses a **4-level page table** (PML4, PDPT, PD, PT), where each level is a 4KB page containing 512 entries (9 bits per level). A 48-bit virtual address is split as:

- **Bits 47-39**: PML4 index (Page Map Level 4)
- **Bits 38-30**: PDPT index (Page Directory Pointer Table)
- **Bits 29-21**: PD index (Page Directory)
- **Bits 20-12**: PT index (Page Table)
- **Bits 11-0**: Page offset (12 bits = 4KB page)

**Best practice**: Intel introduced **5-level paging** (PML5) for 57-bit virtual addresses, but most systems still use 4-level. The Linux kernel supports both via the `CONFIG_X86_5LEVEL` option.

Each entry in these tables contains the **physical frame number** plus permission bits (present, writable, user-accessible, no-execute, accessed, dirty). If the **present bit** is zero at any level, the MMU raises a **page fault**.

## TLB: Translation Lookaside Buffer

The MMU would need 4 memory accesses to walk a 4-level page table for every single instruction fetch or data access. This would make memory access 5x slower. The **TLB** solves this by caching recent virtual-to-physical translations.

### TLB Architecture

Modern CPUs have split TLBs:
- **L1 iTLB**: 64-128 entries for instruction pages, fully associative
- **L1 dTLB**: 64-128 entries for data pages, fully associative
- **L2 sTLB**: 1024-2048 entries, shared, 8-way set associative

A **TLB miss** triggers a hardware page table walk (on x86) or a software-managed walk (on MIPS/RISC-V). **Common mistake**: Assuming TLB misses are cheap. A 4-level walk costs ~100 cycles in the best case (all page table pages in L2 cache) and potentially thousands of cycles if page table pages are themselves evicted from cache.

### TLB Shootdowns

When the kernel modifies page tables (e.g., `munmap`, `mprotect`), it must invalidate stale TLB entries on **all** CPU cores that might cache them. This is done via **Inter-Processor Interrupts (IPIs)**, which are expensive. Therefore, frequent page table modifications on multi-core systems can cause significant performance degradation.

## Page Fault Handling and Demand Paging

When the MMU cannot resolve a virtual address, it raises a **page fault** exception. The kernel's page fault handler classifies the fault:

1. **Minor fault (soft)**: The page exists in memory (e.g., in the page cache) but the page table entry is not yet set up. The handler maps the page and returns. No disk I/O.
2. **Major fault (hard)**: The page must be read from disk (swap or a file). The handler initiates I/O, blocks the faulting thread, and reschedules. This costs millions of cycles.
3. **Invalid fault**: The address is not mapped in the process's address space. The kernel sends SIGSEGV (segmentation fault).

**Demand paging** means the kernel does not load a program's entire binary into memory at `exec()` time. Instead, it sets up page table entries as "not present" and lets page faults lazily load pages as the program accesses them. This dramatically reduces startup time and memory usage for large binaries where only a fraction of code is actually executed.

## Huge Pages

Standard 4KB pages mean the TLB can only cover 8MB of memory with 2048 entries. For workloads with large working sets (databases, scientific computing), **huge pages** are essential:

- **2MB huge pages** (x86-64): Each TLB entry covers 2MB instead of 4KB, so 2048 TLB entries cover **4GB**
- **1GB huge pages**: Each entry covers 1GB; 2048 entries cover **2TB**

The **trade-off** is that huge pages increase internal fragmentation (unused portions of a 2MB page are wasted) and are harder for the kernel to allocate because they require contiguous physical memory. Linux provides **Transparent Huge Pages (THP)** that automatically merge contiguous 4KB pages into 2MB pages, however THP can cause latency spikes due to background compaction and defragmentation. **Pitfall**: For latency-sensitive applications (Redis, real-time systems), THP should be disabled and explicit huge pages (`hugetlbfs`) used instead.

## Copy-on-Write (CoW)

When `fork()` creates a child process, the kernel does **not** copy the parent's entire address space. Instead, both parent and child share the same physical pages, with all writable pages marked as **read-only** in both page tables. When either process writes to a shared page, the resulting page fault triggers the **copy-on-write** mechanism: the kernel allocates a new physical page, copies the content, and updates the faulting process's page table to point to the new page with write permissions.

This is critical for performance because many forked processes immediately call `exec()`, replacing their address space entirely. Without CoW, `fork()` would waste time copying pages that are immediately discarded.

## Page Table Simulator with LRU Replacement

```python
from __future__ import annotations
import collections
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PageTableEntry:
    # Represents a single page table entry with metadata
    frame_number: int = -1
    present: bool = False
    dirty: bool = False
    accessed: bool = False
    writable: bool = True
    last_access_time: int = 0


@dataclass
class PageFaultStats:
    # Track page fault statistics for analysis
    total_faults: int = 0
    minor_faults: int = 0
    major_faults: int = 0
    cow_faults: int = 0
    evictions: int = 0


class LRUPageReplacer:
    # LRU page replacement using an ordered dictionary for O(1) operations
    def __init__(self, max_frames: int) -> None:
        self.max_frames = max_frames
        self.frame_map: collections.OrderedDict[int, int] = collections.OrderedDict()
        # frame_map: frame_number -> virtual_page_number

    def access(self, frame: int, vpn: int) -> None:
        # Move accessed frame to end (most recently used)
        if frame in self.frame_map:
            self.frame_map.move_to_end(frame)
        else:
            self.frame_map[frame] = vpn

    def evict(self) -> tuple[int, int]:
        # Evict the least recently used frame (first item)
        # Returns (frame_number, virtual_page_number)
        if not self.frame_map:
            raise RuntimeError("No frames to evict")
        frame, vpn = self.frame_map.popitem(last=False)
        return frame, vpn

    def is_full(self) -> bool:
        return len(self.frame_map) >= self.max_frames

    def remove(self, frame: int) -> None:
        if frame in self.frame_map:
            del self.frame_map[frame]
```

### Multi-Level Page Table Walk

```python
class MultiLevelPageTable:
    # Simulates a 3-level page table (simplified from x86-64 4-level)
    # Level 0: 10 bits, Level 1: 10 bits, Level 2: 10 bits, Offset: 2 bits
    LEVELS = 3
    BITS_PER_LEVEL = 10
    ENTRIES_PER_TABLE = 1 << BITS_PER_LEVEL  # 1024
    OFFSET_BITS = 2

    def __init__(self, num_physical_frames: int) -> None:
        self.num_frames = num_physical_frames
        self.next_free_frame: int = 0
        self.stats = PageFaultStats()
        self.replacer = LRUPageReplacer(num_physical_frames)
        self.access_counter: int = 0
        # Root table: list of optional child tables or PTEs
        self.root: list[Optional[dict]] = [None] * self.ENTRIES_PER_TABLE
        # Reverse map: frame -> (vpn, pte reference) for eviction
        self.frame_to_vpn: dict[int, tuple[int, PageTableEntry]] = {}
        # TLB simulation: vpn -> (frame, writable)
        self.tlb: collections.OrderedDict[int, tuple[int, bool]] = (
            collections.OrderedDict()
        )
        self.tlb_capacity: int = 64
        self.tlb_hits: int = 0
        self.tlb_misses: int = 0

    def _extract_indices(self, virtual_address: int) -> list[int]:
        # Split virtual address into per-level indices
        indices = []
        addr = virtual_address >> self.OFFSET_BITS
        for _ in range(self.LEVELS):
            indices.append(addr & (self.ENTRIES_PER_TABLE - 1))
            addr >>= self.BITS_PER_LEVEL
        return list(reversed(indices))

    def _vpn_from_address(self, virtual_address: int) -> int:
        return virtual_address >> self.OFFSET_BITS

    def _allocate_frame(self, vpn: int, pte: PageTableEntry) -> int:
        # Allocate a physical frame, evicting if necessary
        if self.replacer.is_full():
            evicted_frame, evicted_vpn = self.replacer.evict()
            self.stats.evictions += 1
            # Invalidate the evicted page's PTE
            if evicted_frame in self.frame_to_vpn:
                _, evicted_pte = self.frame_to_vpn[evicted_frame]
                evicted_pte.present = False
                del self.frame_to_vpn[evicted_frame]
            # Invalidate TLB entry for evicted page
            if evicted_vpn in self.tlb:
                del self.tlb[evicted_vpn]
            frame = evicted_frame
        else:
            frame = self.next_free_frame
            self.next_free_frame += 1
        self.frame_to_vpn[frame] = (vpn, pte)
        self.replacer.access(frame, vpn)
        return frame

    def _tlb_lookup(self, vpn: int) -> Optional[tuple[int, bool]]:
        if vpn in self.tlb:
            self.tlb_hits += 1
            self.tlb.move_to_end(vpn)
            return self.tlb[vpn]
        self.tlb_misses += 1
        return None

    def _tlb_insert(self, vpn: int, frame: int, writable: bool) -> None:
        if len(self.tlb) >= self.tlb_capacity:
            self.tlb.popitem(last=False)
        self.tlb[vpn] = (frame, writable)

    def access_address(
        self, virtual_address: int, write: bool = False
    ) -> tuple[int, str]:
        # Translate virtual address to physical; returns (physical_addr, event_type)
        self.access_counter += 1
        vpn = self._vpn_from_address(virtual_address)
        offset = virtual_address & ((1 << self.OFFSET_BITS) - 1)

        # Check TLB first
        tlb_result = self._tlb_lookup(vpn)
        if tlb_result is not None:
            frame, writable = tlb_result
            physical_addr = (frame << self.OFFSET_BITS) | offset
            return physical_addr, "tlb_hit"

        # Walk the multi-level page table
        indices = self._extract_indices(virtual_address)
        current_table = self.root

        for level in range(self.LEVELS - 1):
            idx = indices[level]
            if current_table[idx] is None:
                # Allocate intermediate table on demand
                current_table[idx] = {"table": [None] * self.ENTRIES_PER_TABLE}
            current_table = current_table[idx]["table"]

        # Leaf level: contains PTEs
        leaf_idx = indices[-1]
        if current_table[leaf_idx] is None:
            current_table[leaf_idx] = PageTableEntry()

        pte: PageTableEntry = current_table[leaf_idx]

        if not pte.present:
            # PAGE FAULT
            self.stats.total_faults += 1
            self.stats.major_faults += 1
            frame = self._allocate_frame(vpn, pte)
            pte.frame_number = frame
            pte.present = True
            pte.accessed = True
            pte.last_access_time = self.access_counter
            self._tlb_insert(vpn, frame, pte.writable)
            physical_addr = (frame << self.OFFSET_BITS) | offset
            return physical_addr, "page_fault"

        # Page is present
        pte.accessed = True
        pte.last_access_time = self.access_counter
        if write:
            pte.dirty = True
        self.replacer.access(pte.frame_number, vpn)
        self._tlb_insert(vpn, pte.frame_number, pte.writable)
        physical_addr = (pte.frame_number << self.OFFSET_BITS) | offset
        return physical_addr, "page_table_walk"
```

### Simulation Driver and Analysis

```python
def run_simulation() -> None:
    # Demonstrate page table behavior with realistic access patterns
    pt = MultiLevelPageTable(num_physical_frames=8)

    # Simulate a workload: sequential scan then hot-set re-access
    addresses = []
    # Phase 1: Sequential scan of 12 pages (more than 8 frames)
    for page in range(12):
        addresses.append(page << pt.OFFSET_BITS)
    # Phase 2: Re-access hot set (pages 8-11 are in memory, 0-3 were evicted)
    for page in [0, 1, 2, 3]:
        addresses.append(page << pt.OFFSET_BITS)
    # Phase 3: Repeated access to same page (TLB hits)
    for _ in range(5):
        addresses.append(0 << pt.OFFSET_BITS)

    print("=== Virtual Memory Page Table Simulation ===\n")
    for addr in addresses:
        phys, event = pt.access_address(addr, write=False)
        vpn = addr >> pt.OFFSET_BITS
        print(f"  VPN {vpn:4d} -> PFN {phys >> pt.OFFSET_BITS:4d}  [{event}]")

    print(f"\n--- Statistics ---")
    print(f"  Total page faults: {pt.stats.total_faults}")
    print(f"  Major faults:      {pt.stats.major_faults}")
    print(f"  Evictions:         {pt.stats.evictions}")
    print(f"  TLB hits:          {pt.tlb_hits}")
    print(f"  TLB misses:        {pt.tlb_misses}")
    hit_rate = pt.tlb_hits / (pt.tlb_hits + pt.tlb_misses) * 100
    print(f"  TLB hit rate:      {hit_rate:.1f}%")

    # Demonstrate working set analysis
    print(f"\n--- Working Set Analysis ---")
    print(f"  Physical frames:   {pt.num_frames}")
    print(f"  Unique pages accessed: {len(set(a >> pt.OFFSET_BITS for a in addresses))}")
    print(f"  Best practice: size your physical memory to hold the working set")


if __name__ == "__main__":
    run_simulation()
```

## Summary and Key Takeaways

- **Multi-level page tables** solve the memory overhead problem by only allocating table pages for address ranges actually in use, therefore a process using 100MB does not need gigabytes of page table entries.
- The **TLB** is the single most important performance factor in virtual memory; a TLB miss triggers a multi-level walk costing hundreds of cycles. **Huge pages** dramatically improve TLB coverage for large-memory workloads.
- **Demand paging** and **copy-on-write** are lazy strategies that defer physical memory allocation until absolutely necessary, because most allocated virtual pages are never accessed.
- **LRU replacement** approximates the optimal (Belady's) algorithm by evicting the least recently used page, however real kernels use clock-based approximations (second-chance algorithm) because true LRU tracking is too expensive.
- The **trade-off** between page size and fragmentation is fundamental: larger pages improve TLB efficiency but waste memory when allocation granularity does not match page size.
- **Pitfall**: THP (Transparent Huge Pages) can cause unpredictable latency spikes in production systems due to background compaction; always benchmark before enabling."""
    ),

    # --- 2. Process Scheduling Algorithms ---
    (
        "os-internals/process-scheduling-cfs-realtime-algorithms",
        "Explain Linux process scheduling including the Completely Fair Scheduler virtual runtime and red-black tree, real-time scheduling policies FIFO and Round Robin and EDF, nice values and their weight mapping, cgroups CPU controller bandwidth throttling, and implement a CFS simulator in Python",
        r"""# Process Scheduling Algorithms: CFS, Real-Time, and Beyond

## The Scheduling Problem

The CPU scheduler is one of the most critical components of an operating system kernel because it determines which process runs on which CPU at any given moment. A poor scheduler leads to starvation, priority inversion, wasted CPU cycles, and unresponsive systems. Linux has evolved through multiple scheduler designs: the **O(n) scheduler** (Linux 2.4), the **O(1) scheduler** (Linux 2.6), and the current **Completely Fair Scheduler (CFS)** introduced in Linux 2.6.23 by Ingo Molnar.

The fundamental **trade-off** in scheduler design is between **throughput** (maximizing total work completed) and **latency** (minimizing response time for interactive tasks). Batch workloads favor throughput; desktop and real-time workloads favor latency.

## Completely Fair Scheduler (CFS)

### Core Concept: Virtual Runtime

CFS models an idealized **perfectly fair** multi-tasking CPU where all runnable tasks execute simultaneously, each receiving an equal share of CPU time. Since real CPUs execute one task at a time per core, CFS tracks how much CPU time each task has received relative to its fair share using **virtual runtime** (`vruntime`).

The `vruntime` of a task increases as it runs. The key equation is:

**vruntime_delta = actual_runtime * (NICE_0_WEIGHT / task_weight)**

A task with the default nice value (0, weight 1024) increments `vruntime` at the same rate as wall-clock time. A task with a lower nice value (higher priority, higher weight) accumulates `vruntime` more slowly, therefore it can run longer before being preempted. A task with a higher nice value (lower priority, lower weight) accumulates `vruntime` faster.

### Nice Values and Weight Mapping

Linux maps nice values (-20 to +19) to weights using a carefully chosen table where each nice level represents approximately a **10% change** in CPU share:

| Nice | Weight | CPU Share (approx) |
|------|--------|--------------------|
| -20  | 88761  | ~20x default       |
|  -5  | 3121   | ~3x default        |
|   0  | 1024   | 1x (baseline)      |
|   5  |  335   | ~0.33x default     |
|  19  |   15   | ~0.015x default    |

**Common mistake**: Thinking nice values are linear. The weight mapping is exponential, so the difference between nice 0 and nice 1 is much larger in absolute terms than between nice 18 and nice 19.

### Red-Black Tree for Task Selection

CFS organizes all runnable tasks in a **red-black tree** (self-balancing BST) keyed by `vruntime`. The task with the **lowest vruntime** (leftmost node) is always the next to run, because it has received the least CPU time relative to its fair share. This selection is **O(1)** because the leftmost node is cached. Insertion and deletion are **O(log n)**.

### Time Slice Calculation

CFS does not use fixed time slices. Instead, the **scheduling period** (typically 6ms for up to 8 tasks) is divided proportionally among all runnable tasks based on their weights:

**time_slice = scheduling_period * (task_weight / total_weight_of_all_runnable)**

However, there is a minimum granularity (typically 0.75ms) to prevent excessive context switching. This is a **pitfall** when running many tasks: if you have 1000 runnable tasks, the scheduling period stretches to maintain the minimum granularity, causing higher latency.

## Real-Time Scheduling Policies

Linux supports three real-time scheduling policies with **strict priority** over all normal (CFS) tasks:

### SCHED_FIFO (First-In, First-Out)

A SCHED_FIFO task runs until it voluntarily yields, blocks on I/O, or is preempted by a **higher-priority** SCHED_FIFO/SCHED_RR task. Tasks at the same priority level run in FIFO order with no time slicing. **Pitfall**: A runaway SCHED_FIFO task at the highest priority can completely starve the system, including the kernel's own housekeeping threads.

### SCHED_RR (Round Robin)

SCHED_RR is identical to SCHED_FIFO except that tasks at the **same priority level** are time-sliced with a configurable quantum (default 100ms). This prevents starvation among equal-priority real-time tasks.

### SCHED_DEADLINE (Earliest Deadline First)

Introduced in Linux 3.14, SCHED_DEADLINE implements **Earliest Deadline First (EDF)** scheduling. Each task declares three parameters: **runtime**, **deadline**, and **period**. The scheduler guarantees that the task receives `runtime` microseconds of CPU within every `period`, and always picks the task with the nearest deadline. EDF is provably optimal for uniprocessor preemptive scheduling. **Best practice**: Use SCHED_DEADLINE for hard real-time tasks instead of manually managing SCHED_FIFO priorities.

## Cgroups CPU Controller

The **cgroups v2 CPU controller** provides hierarchical CPU bandwidth management. Two key files:

- `cpu.max`: Format `"quota period"` (microseconds). E.g., `"200000 1000000"` means the cgroup gets 200ms out of every 1000ms (20% of one CPU). Setting quota to `"max"` means unlimited.
- `cpu.weight`: Proportional sharing (1-10000, default 100). Analogous to CFS nice weights but applied to the cgroup hierarchy.

The bandwidth throttling mechanism works by assigning each cgroup a **token bucket** that refills every `period` microseconds with `quota` tokens. When a cgroup exhausts its tokens, all its tasks are throttled until the next refill.

## CFS Simulator Implementation

```python
from __future__ import annotations
import heapq
from dataclasses import dataclass, field
from typing import Optional


# Nice-to-weight mapping table (subset)
NICE_TO_WEIGHT: dict[int, int] = {
    -20: 88761, -15: 29154, -10: 9548, -5: 3121,
    -4: 2586, -3: 2145, -2: 1776, -1: 1476,
    0: 1024, 1: 820, 2: 655, 3: 526, 4: 423, 5: 335,
    10: 110, 15: 36, 19: 15,
}
NICE_0_WEIGHT = 1024


@dataclass(order=True)
class Task:
    # CFS task with virtual runtime tracking
    vruntime: float = field(compare=True)
    pid: int = field(compare=False)
    name: str = field(compare=False, default="")
    nice: int = field(compare=False, default=0)
    weight: int = field(compare=False, default=NICE_0_WEIGHT)
    total_runtime: float = field(compare=False, default=0.0)
    remaining_work: float = field(compare=False, default=0.0)

    def __post_init__(self) -> None:
        # Lookup weight from nice value
        if self.nice in NICE_TO_WEIGHT:
            self.weight = NICE_TO_WEIGHT[self.nice]


class CFSScheduler:
    # Simplified CFS scheduler using a min-heap (simulating red-black tree)
    # The task with lowest vruntime is always selected next

    SCHEDULING_PERIOD_MS: float = 6.0
    MIN_GRANULARITY_MS: float = 0.75

    def __init__(self) -> None:
        self.run_queue: list[Task] = []  # min-heap by vruntime
        self.current: Optional[Task] = None
        self.clock_ms: float = 0.0
        self.min_vruntime: float = 0.0  # tracks minimum vruntime for new tasks
        self.completed: list[Task] = []
        self.context_switches: int = 0
        self.timeline: list[dict] = []

    def add_task(self, pid: int, name: str, nice: int, work_ms: float) -> None:
        # New tasks start at min_vruntime to prevent starvation
        task = Task(
            vruntime=self.min_vruntime,
            pid=pid,
            name=name,
            nice=nice,
            remaining_work=work_ms,
        )
        heapq.heappush(self.run_queue, task)

    def _calc_time_slice(self, task: Task) -> float:
        # Calculate proportional time slice based on weight
        nr_running = len(self.run_queue) + (1 if self.current else 0)
        if nr_running <= 1:
            return self.SCHEDULING_PERIOD_MS

        total_weight = sum(t.weight for t in self.run_queue)
        if self.current:
            total_weight += self.current.weight

        period = max(
            self.SCHEDULING_PERIOD_MS,
            nr_running * self.MIN_GRANULARITY_MS
        )
        time_slice = period * (task.weight / total_weight)
        return max(time_slice, self.MIN_GRANULARITY_MS)

    def _update_vruntime(self, task: Task, runtime_ms: float) -> None:
        # vruntime increases slower for higher-weight (lower nice) tasks
        vruntime_delta = runtime_ms * (NICE_0_WEIGHT / task.weight)
        task.vruntime += vruntime_delta
        task.total_runtime += runtime_ms

    def run(self, verbose: bool = True) -> None:
        # Main scheduling loop
        if verbose:
            print("=== CFS Scheduler Simulation ===\n")

        while self.run_queue:
            # Pick task with lowest vruntime (leftmost in RB-tree)
            task = heapq.heappop(self.run_queue)
            self.current = task
            self.context_switches += 1

            time_slice = self._calc_time_slice(task)
            actual_run = min(time_slice, task.remaining_work)

            if verbose:
                print(
                    f"  t={self.clock_ms:8.2f}ms | "
                    f"Run [{task.name}] (nice={task.nice:+d}, "
                    f"weight={task.weight}) "
                    f"slice={time_slice:.2f}ms, "
                    f"vruntime={task.vruntime:.2f}"
                )

            self._update_vruntime(task, actual_run)
            task.remaining_work -= actual_run
            self.clock_ms += actual_run

            self.timeline.append({
                "time": self.clock_ms,
                "pid": task.pid,
                "name": task.name,
                "ran_ms": actual_run,
            })

            # Update min_vruntime (never decreases)
            candidates = [task.vruntime]
            if self.run_queue:
                candidates.append(self.run_queue[0].vruntime)
            self.min_vruntime = max(self.min_vruntime, min(candidates))

            if task.remaining_work <= 0:
                if verbose:
                    print(f"           -> [{task.name}] COMPLETED at {self.clock_ms:.2f}ms")
                self.completed.append(task)
            else:
                heapq.heappush(self.run_queue, task)

            self.current = None

        if verbose:
            self._print_summary()

    def _print_summary(self) -> None:
        print(f"\n--- Scheduling Summary ---")
        print(f"  Total wall time:    {self.clock_ms:.2f}ms")
        print(f"  Context switches:   {self.context_switches}")
        print(f"\n  Task completion order:")
        for task in self.completed:
            print(
                f"    [{task.name}] nice={task.nice:+d} "
                f"runtime={task.total_runtime:.2f}ms "
                f"final_vruntime={task.vruntime:.2f}"
            )
```

### Running the CFS Simulation

```python
def demonstrate_cfs() -> None:
    scheduler = CFSScheduler()

    # Mix of priorities: lower nice = higher priority = more CPU share
    scheduler.add_task(1, "compiler", nice=-5, work_ms=20.0)
    scheduler.add_task(2, "webserver", nice=0, work_ms=15.0)
    scheduler.add_task(3, "backup", nice=10, work_ms=25.0)
    scheduler.add_task(4, "editor", nice=-2, work_ms=10.0)

    scheduler.run(verbose=True)

    # Verify fairness: higher-priority tasks should finish first
    # because their vruntime increases more slowly, giving them
    # more actual CPU time per scheduling period
    print("\n--- Fairness Analysis ---")
    for task in sorted(scheduler.completed, key=lambda t: t.nice):
        share_pct = task.total_runtime / scheduler.clock_ms * 100
        print(
            f"  [{task.name}] nice={task.nice:+d} "
            f"got {share_pct:.1f}% of CPU "
            f"(weight proportion: "
            f"{task.weight / sum(t.weight for t in scheduler.completed) * 100:.1f}%)"
        )


if __name__ == "__main__":
    demonstrate_cfs()
```

### Real-Time Scheduler Comparison

```python
from __future__ import annotations
from dataclasses import dataclass
from collections import deque


@dataclass
class RTTask:
    pid: int
    name: str
    priority: int  # lower number = higher priority
    burst_ms: float
    remaining_ms: float = 0.0
    deadline_ms: float = 0.0  # for EDF

    def __post_init__(self) -> None:
        self.remaining_ms = self.burst_ms


def simulate_fifo(tasks: list[RTTask]) -> list[str]:
    # SCHED_FIFO: tasks run to completion in priority order, no preemption
    # among equal priority; higher-priority tasks preempt lower ones
    sorted_tasks = sorted(tasks, key=lambda t: t.priority)
    log: list[str] = []
    clock = 0.0
    for task in sorted_tasks:
        log.append(f"  t={clock:6.1f}ms: [{task.name}] runs (prio={task.priority})")
        clock += task.burst_ms
        log.append(f"  t={clock:6.1f}ms: [{task.name}] completes")
    return log


def simulate_rr(tasks: list[RTTask], quantum_ms: float = 2.0) -> list[str]:
    # SCHED_RR: round-robin among same-priority tasks
    log: list[str] = []
    queue: deque[RTTask] = deque(sorted(tasks, key=lambda t: t.priority))
    clock = 0.0
    while queue:
        task = queue.popleft()
        run_time = min(quantum_ms, task.remaining_ms)
        log.append(
            f"  t={clock:6.1f}ms: [{task.name}] runs {run_time:.1f}ms "
            f"(prio={task.priority}, remaining={task.remaining_ms:.1f}ms)"
        )
        clock += run_time
        task.remaining_ms -= run_time
        if task.remaining_ms > 0:
            queue.append(task)
        else:
            log.append(f"  t={clock:6.1f}ms: [{task.name}] completes")
    return log


def compare_rt_schedulers() -> None:
    print("\n=== Real-Time Scheduler Comparison ===\n")

    tasks_fifo = [
        RTTask(1, "audio", priority=1, burst_ms=3.0),
        RTTask(2, "video", priority=2, burst_ms=5.0),
        RTTask(3, "logger", priority=3, burst_ms=4.0),
    ]
    print("SCHED_FIFO (no preemption at same priority):")
    for line in simulate_fifo(tasks_fifo):
        print(line)

    tasks_rr = [
        RTTask(1, "worker-A", priority=1, burst_ms=6.0),
        RTTask(2, "worker-B", priority=1, burst_ms=4.0),
        RTTask(3, "worker-C", priority=1, burst_ms=5.0),
    ]
    print("\nSCHED_RR (quantum=2ms, same priority):")
    for line in simulate_rr(tasks_rr, quantum_ms=2.0):
        print(line)


if __name__ == "__main__":
    compare_rt_schedulers()
```

## Summary and Key Takeaways

- **CFS achieves fairness** by tracking virtual runtime and always scheduling the task with the lowest vruntime, therefore higher-priority tasks accumulate vruntime more slowly and receive proportionally more CPU.
- The **red-black tree** provides O(log n) insertion/deletion and O(1) leftmost selection (cached), making CFS efficient even with thousands of runnable tasks.
- **Real-time policies** (SCHED_FIFO, SCHED_RR, SCHED_DEADLINE) have strict priority over CFS tasks. **Best practice**: Use SCHED_DEADLINE for deadline-sensitive workloads instead of manually juggling FIFO priorities.
- **Cgroups v2 CPU controller** adds hierarchical bandwidth throttling, enabling container platforms to enforce CPU limits. The **trade-off** is between hard limits (cpu.max) that throttle and soft limits (cpu.weight) that share proportionally.
- **Pitfall**: Running too many SCHED_FIFO tasks can starve the entire system, including kernel threads. Linux provides `sched_rt_runtime_us` (default 950ms/1000ms) as a safety net to reserve 5% of CPU for non-RT tasks.
- **Common mistake**: Assuming nice values are linear in their effect. The exponential weight mapping means each nice level changes CPU share by roughly 10%, not by a fixed amount."""
    ),

    # --- 3. File System Internals ---
    (
        "os-internals/filesystem-internals-inode-ext4-journaling",
        "Explain file system internals including inode structure and metadata, ext4 extent trees replacing indirect block mapping, journaling with write-ahead logging and crash recovery, the VFS abstraction layer, block allocation strategies, and implement a simplified in-memory filesystem with inodes and directory entries in Python",
        r"""# File System Internals: Inodes, Journaling, and VFS

## The Role of a File System

A file system transforms raw storage blocks into a structured hierarchy of files and directories. It must solve several hard problems simultaneously: **naming** (human-readable paths), **allocation** (tracking which blocks belong to which file), **metadata** (permissions, timestamps, size), **crash recovery** (maintaining consistency after power loss), and **performance** (minimizing seeks and maximizing throughput). Understanding file system internals is essential because every application ultimately depends on reliable, efficient storage.

## Inode Structure

The **inode** (index node) is the fundamental data structure representing a file or directory on disk. Each inode contains all metadata about a file **except** its name:

- **File type**: regular, directory, symlink, block device, char device, FIFO, socket
- **Permissions**: owner, group, other (rwx) plus setuid, setgid, sticky bits
- **Ownership**: uid, gid
- **Timestamps**: atime (last access), mtime (last modification), ctime (last inode change), crtime (creation, ext4)
- **Size**: in bytes
- **Link count**: number of hard links (directory entries pointing to this inode)
- **Block pointers**: locations of data blocks on disk

**Common mistake**: Thinking file names are stored in inodes. Names are stored in **directory entries** (dentries), which map names to inode numbers. This is why hard links work: multiple directory entries can point to the same inode.

### Traditional Block Mapping (ext2/ext3)

The classic inode contains 15 block pointers:
- **12 direct pointers**: point directly to data blocks
- **1 single-indirect pointer**: points to a block of pointers (e.g., 1024 pointers with 4KB blocks)
- **1 double-indirect pointer**: two levels of indirection
- **1 triple-indirect pointer**: three levels of indirection

This scheme supports files up to ~4TB with 4KB blocks, however it is extremely inefficient for large files because reading a contiguous 1GB file requires thousands of indirect block lookups scattered across the disk.

## ext4 Extent Trees

ext4 replaced indirect block mapping with **extent trees**. An **extent** describes a contiguous range of physical blocks:

```
struct ext4_extent {
    __le32 ee_block;      // first logical block
    __le16 ee_len;        // number of blocks (up to 32768)
    __le16 ee_start_hi;   // upper 16 bits of physical block
    __le32 ee_start_lo;   // lower 32 bits of physical block
};
```

A single extent can represent up to 128MB of contiguous data (32768 blocks * 4KB). The inode can hold 4 extents directly. If more are needed, ext4 builds a **B-tree** (extent tree) with the inode as the root, allowing efficient lookup of any logical block.

The **trade-off** is that extent trees are more complex to implement and debug, however they deliver dramatically better performance for large files and reduce metadata overhead. For a 1GB contiguous file, one extent replaces 262,144 indirect block pointers.

## Journaling and Write-Ahead Logging

### The Crash Consistency Problem

Updating a file typically requires multiple disk writes: the data block, the inode (to update size/timestamps), the block bitmap (to mark blocks as allocated), and possibly directory entries. If power is lost mid-update, these structures can become inconsistent, leading to data corruption.

### Write-Ahead Logging (WAL)

ext4 uses **journaling** (a form of write-ahead logging) to ensure crash consistency. Before modifying the file system, the kernel writes the intended changes to a dedicated **journal** (a circular log on disk):

1. **Journal write**: Write all modified metadata blocks (and optionally data) to the journal
2. **Journal commit**: Write a commit block with a checksum, marking the transaction as complete
3. **Checkpoint**: Write the actual changes to their final locations on disk
4. **Journal clear**: Mark the journal space as reusable

If a crash occurs before the commit block is written, the transaction is discarded on recovery. If the crash occurs after the commit, the recovery process **replays** the journal to complete the update. This guarantees **atomicity** of file system operations.

### Journaling Modes

ext4 supports three journaling modes:
- **journal**: Both data and metadata are journaled. Safest but slowest (data written twice).
- **ordered** (default): Only metadata is journaled, but data is written before the metadata journal commit. Prevents stale data exposure.
- **writeback**: Only metadata is journaled; data can be written in any order. Fastest but a crash can expose stale data from previously deleted files.

**Best practice**: Use `ordered` mode for most workloads. Use `journal` mode only for critical databases where data integrity justifies the performance cost.

## VFS (Virtual File System) Layer

The **VFS** is the kernel's abstraction layer that allows user-space programs to use the same system calls (`open`, `read`, `write`, `stat`) regardless of the underlying file system (ext4, XFS, Btrfs, NFS, procfs, etc.).

VFS defines four key object types:
- **superblock**: represents a mounted file system (block size, total blocks, fs-specific operations)
- **inode**: represents a file (permissions, size, block mapping, inode operations)
- **dentry**: represents a directory entry (name-to-inode mapping, cached in the dentry cache)
- **file**: represents an open file descriptor (current offset, access mode, file operations)

Each file system implements the VFS operations interface (e.g., `inode_operations.lookup`, `file_operations.read_iter`). The **dentry cache** (dcache) is critical for performance because it avoids repeated directory lookups by caching the path-to-inode resolution.

**Pitfall**: The dcache and inode cache can consume significant memory on systems with millions of files. The kernel reclaims this memory under pressure, however sudden cache eviction can cause performance cliffs.

## In-Memory File System Implementation

```python
from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class FileType(Enum):
    REGULAR = auto()
    DIRECTORY = auto()
    SYMLINK = auto()


@dataclass
class Inode:
    # Core inode structure: metadata + block references
    ino: int
    file_type: FileType
    permissions: int = 0o644
    uid: int = 0
    gid: int = 0
    size: int = 0
    link_count: int = 0
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    # Block numbers allocated to this file
    blocks: list[int] = field(default_factory=list)
    # For directories: name -> inode number mapping
    dir_entries: dict[str, int] = field(default_factory=dict)
    # For symlinks: target path
    symlink_target: str = ""


class BlockAllocator:
    # Bitmap-based block allocator for fixed-size blocks
    def __init__(self, total_blocks: int, block_size: int = 4096) -> None:
        self.total_blocks = total_blocks
        self.block_size = block_size
        self.bitmap: list[bool] = [False] * total_blocks
        self.free_count = total_blocks
        # Storage: block_number -> bytes
        self.storage: dict[int, bytearray] = {}

    def allocate(self, count: int = 1) -> list[int]:
        # First-fit allocation strategy
        allocated: list[int] = []
        for i in range(self.total_blocks):
            if not self.bitmap[i]:
                self.bitmap[i] = True
                self.free_count -= 1
                self.storage[i] = bytearray(self.block_size)
                allocated.append(i)
                if len(allocated) == count:
                    return allocated
        # Not enough free blocks; roll back
        for blk in allocated:
            self.bitmap[blk] = False
            self.free_count += 1
            del self.storage[blk]
        raise OSError(f"No space left: requested {count}, free {self.free_count}")

    def free(self, block_numbers: list[int]) -> None:
        for blk in block_numbers:
            if self.bitmap[blk]:
                self.bitmap[blk] = False
                self.free_count += 1
                if blk in self.storage:
                    del self.storage[blk]

    def write_block(self, block_num: int, data: bytes, offset: int = 0) -> int:
        buf = self.storage[block_num]
        end = min(offset + len(data), self.block_size)
        buf[offset:end] = data[:end - offset]
        return end - offset

    def read_block(self, block_num: int, offset: int = 0, length: int = -1) -> bytes:
        buf = self.storage[block_num]
        if length < 0:
            return bytes(buf[offset:])
        return bytes(buf[offset:offset + length])


class SimpleFileSystem:
    # In-memory file system with inodes, directories, and block allocation
    # Demonstrates core FS concepts: inode management, path resolution,
    # block allocation, and directory traversal

    def __init__(self, total_blocks: int = 1024, block_size: int = 4096) -> None:
        self.block_size = block_size
        self.allocator = BlockAllocator(total_blocks, block_size)
        self.inodes: dict[int, Inode] = {}
        self.next_ino: int = 1
        # Create root directory
        root = self._alloc_inode(FileType.DIRECTORY, permissions=0o755)
        root.dir_entries["."] = root.ino
        root.dir_entries[".."] = root.ino
        root.link_count = 2
        self.root_ino = root.ino

    def _alloc_inode(
        self, file_type: FileType, permissions: int = 0o644
    ) -> Inode:
        ino = self.next_ino
        self.next_ino += 1
        inode = Inode(ino=ino, file_type=file_type, permissions=permissions)
        self.inodes[ino] = inode
        return inode

    def _resolve_path(self, path: str) -> tuple[Inode, str]:
        # Walk path components from root, return (parent_inode, final_name)
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            return self.inodes[self.root_ino], ""

        current = self.inodes[self.root_ino]
        for component in parts[:-1]:
            if current.file_type != FileType.DIRECTORY:
                raise OSError(f"Not a directory: {component}")
            if component not in current.dir_entries:
                raise FileNotFoundError(f"No such directory: {component}")
            current = self.inodes[current.dir_entries[component]]
        return current, parts[-1]

    def _lookup(self, path: str) -> Inode:
        # Resolve full path to an inode
        parent, name = self._resolve_path(path)
        if not name:
            return parent
        if name not in parent.dir_entries:
            raise FileNotFoundError(f"No such file: {path}")
        return self.inodes[parent.dir_entries[name]]

    def mkdir(self, path: str) -> Inode:
        parent, name = self._resolve_path(path)
        if name in parent.dir_entries:
            raise FileExistsError(f"Already exists: {path}")
        new_dir = self._alloc_inode(FileType.DIRECTORY, permissions=0o755)
        new_dir.dir_entries["."] = new_dir.ino
        new_dir.dir_entries[".."] = parent.ino
        new_dir.link_count = 2
        parent.dir_entries[name] = new_dir.ino
        parent.link_count += 1  # '..' in child points to parent
        return new_dir

    def create_file(self, path: str, data: bytes = b"") -> Inode:
        parent, name = self._resolve_path(path)
        if name in parent.dir_entries:
            raise FileExistsError(f"Already exists: {path}")
        inode = self._alloc_inode(FileType.REGULAR)
        inode.link_count = 1
        parent.dir_entries[name] = inode.ino
        if data:
            self.write(path, data)
        return inode

    def write(self, path: str, data: bytes) -> int:
        inode = self._lookup(path)
        if inode.file_type != FileType.REGULAR:
            raise OSError(f"Not a regular file: {path}")
        # Free old blocks
        if inode.blocks:
            self.allocator.free(inode.blocks)
            inode.blocks = []
        # Allocate new blocks
        blocks_needed = (len(data) + self.block_size - 1) // self.block_size
        if blocks_needed == 0:
            inode.size = 0
            return 0
        new_blocks = self.allocator.allocate(blocks_needed)
        inode.blocks = new_blocks
        written = 0
        for i, blk in enumerate(new_blocks):
            chunk = data[i * self.block_size:(i + 1) * self.block_size]
            written += self.allocator.write_block(blk, chunk)
        inode.size = len(data)
        inode.modified_at = time.time()
        return written

    def read(self, path: str) -> bytes:
        inode = self._lookup(path)
        if inode.file_type != FileType.REGULAR:
            raise OSError(f"Not a regular file: {path}")
        inode.accessed_at = time.time()
        result = bytearray()
        remaining = inode.size
        for blk in inode.blocks:
            to_read = min(remaining, self.block_size)
            result.extend(self.allocator.read_block(blk, length=to_read))
            remaining -= to_read
        return bytes(result)

    def stat(self, path: str) -> dict:
        inode = self._lookup(path)
        return {
            "ino": inode.ino,
            "type": inode.file_type.name,
            "size": inode.size,
            "links": inode.link_count,
            "blocks": len(inode.blocks),
            "permissions": oct(inode.permissions),
        }

    def ls(self, path: str = "/") -> list[str]:
        inode = self._lookup(path)
        if inode.file_type != FileType.DIRECTORY:
            raise OSError(f"Not a directory: {path}")
        return [
            name for name in sorted(inode.dir_entries.keys())
            if name not in (".", "..")
        ]
```

### Exercising the File System

```python
def demo_filesystem() -> None:
    fs = SimpleFileSystem(total_blocks=256, block_size=512)

    # Create directory structure
    fs.mkdir("/home")
    fs.mkdir("/home/user")
    fs.mkdir("/etc")

    # Create and write files
    fs.create_file("/etc/hostname", b"myserver.local\n")
    fs.create_file(
        "/home/user/notes.txt",
        b"File system internals are fascinating.\n" * 30
    )

    # Read back
    content = fs.read("/etc/hostname")
    print(f"hostname: {content.decode().strip()}")

    # Stat
    info = fs.stat("/home/user/notes.txt")
    print(f"notes.txt: {info}")

    # List directories
    print(f"/ contents: {fs.ls('/')}")
    print(f"/home contents: {fs.ls('/home')}")

    # Show allocator state
    print(f"\nBlock allocator: "
          f"{fs.allocator.free_count}/{fs.allocator.total_blocks} free")


if __name__ == "__main__":
    demo_filesystem()
```

## Summary and Key Takeaways

- **Inodes** store all file metadata except the name; directory entries are the name-to-inode mappings. This decoupling is why hard links, `mv` within the same filesystem, and `ls -i` work the way they do.
- **ext4 extent trees** replaced the wasteful indirect block mapping with contiguous range descriptors, therefore a 1GB contiguous file needs one extent instead of hundreds of thousands of indirect pointers.
- **Journaling** (write-ahead logging) ensures crash consistency by writing changes to a journal before committing them to their final locations. The **trade-off** between journal modes (journal, ordered, writeback) balances safety against performance.
- The **VFS layer** is a brilliant abstraction that lets Linux support dozens of file systems through a unified interface. However, leaky abstractions exist: not all file systems support all operations (e.g., FAT32 lacks Unix permissions).
- **Block allocation** strategy significantly impacts performance. Best practice is contiguous allocation (extent-based) for sequential workloads and delayed allocation (ext4's `delalloc`) to batch allocations for better contiguity.
- **Pitfall**: Running `atime` updates on every file read can cause significant write amplification. Most production systems mount with `relatime` or `noatime` to reduce unnecessary inode updates."""
    ),

    # --- 4. Inter-Process Communication ---
    (
        "os-internals/ipc-shared-memory-ring-buffer-synchronization",
        "Explain inter-process communication mechanisms including Unix pipes and named FIFOs, POSIX shared memory segments, System V message queues, Unix domain sockets, memory-mapped files with mmap, and implement a shared memory ring buffer with synchronization primitives and IPC performance comparison in Python",
        r"""# Inter-Process Communication: Mechanisms, Trade-offs, and Implementation

## Why IPC Matters

Processes in modern operating systems are **isolated by design**: each has its own virtual address space, file descriptor table, and signal handlers. This isolation is fundamental to security and stability, however it creates a challenge when processes need to exchange data. **Inter-process communication (IPC)** mechanisms bridge this gap, and choosing the right one is critical because the performance difference between IPC methods can span orders of magnitude.

## Unix Pipes

### Anonymous Pipes

The simplest IPC mechanism is the **anonymous pipe**, created by the `pipe()` system call. It provides a unidirectional byte stream between related processes (parent-child or siblings). The kernel allocates a **pipe buffer** (typically 64KB on Linux, configurable via `/proc/sys/fs/pipe-max-size`) in kernel memory. Writes to the pipe copy data from user-space into the kernel buffer; reads copy data out.

**Common mistake**: Assuming pipes are zero-copy. Pipe I/O involves **two copies**: user-space to kernel buffer on write, and kernel buffer to user-space on read. For high-throughput IPC, this overhead is significant.

### Named Pipes (FIFOs)

**Named pipes** (`mkfifo`) are like anonymous pipes but exist as entries in the filesystem, therefore unrelated processes can communicate by opening the same FIFO path. They share the same kernel buffer mechanism and same performance characteristics. The **trade-off** is convenience (any process can connect) versus security (filesystem permissions must be carefully set).

**Pitfall**: Opening a FIFO for reading blocks until a writer opens it (and vice versa), unless `O_NONBLOCK` is used. This can cause deadlocks if a process opens both ends sequentially.

## POSIX Shared Memory

**Shared memory** is the fastest IPC mechanism because it eliminates kernel involvement after the initial setup. Two or more processes map the same physical memory region into their virtual address spaces using `shm_open()` + `mmap()`.

The key advantage is **zero-copy**: once mapped, processes read and write shared data directly, with no system calls for data transfer. However, this comes with a critical requirement: processes must implement their own **synchronization** (mutexes, semaphores, or lock-free algorithms) to prevent data races.

On Linux, POSIX shared memory segments appear as files under `/dev/shm/` (a tmpfs filesystem backed by RAM). The maximum size is typically half of physical RAM, configurable via `sysctl`.

**Best practice**: Use `shm_unlink()` to clean up shared memory segments when done. Leaked segments in `/dev/shm/` persist until reboot and consume RAM.

## System V Message Queues

**System V message queues** provide typed, prioritized message passing. Each message has a **type** field (a long integer), and receivers can selectively dequeue messages by type. This enables multiplexing multiple logical channels over a single queue.

However, System V IPC has significant limitations: small default message sizes (typically 8KB), global kernel limits on total queue bytes, and an aging API that does not integrate with `select()`/`poll()`/`epoll`. **POSIX message queues** (`mq_open`) are the modern replacement, offering file-descriptor-based notification and integration with event loops.

The **trade-off** with message queues versus shared memory is that message queues provide implicit synchronization (each message is atomic) and decoupling (sender and receiver need not run simultaneously) at the cost of kernel-mediated copies.

## Unix Domain Sockets

**Unix domain sockets** provide bidirectional, connection-oriented (SOCK_STREAM) or datagram (SOCK_DGRAM) communication between processes on the same host. They use the socket API (`socket()`, `bind()`, `connect()`, `accept()`) with `AF_UNIX` addressing (filesystem paths or abstract namespace on Linux).

Key advantages over pipes:
- **Bidirectional**: A single socket pair replaces two pipes
- **Datagram support**: SOCK_DGRAM preserves message boundaries (unlike the byte stream of pipes)
- **File descriptor passing**: `sendmsg()` with `SCM_RIGHTS` can transfer open file descriptors between processes
- **Credential passing**: `SCM_CREDENTIALS` allows the receiver to verify the sender's PID, UID, and GID

**Common mistake**: Using TCP sockets (`AF_INET` on `127.0.0.1`) for local IPC. Unix domain sockets are significantly faster because they bypass the entire TCP/IP stack (no checksums, no routing, no segmentation).

## Memory-Mapped Files (mmap)

`mmap()` maps a file (or anonymous memory) into a process's virtual address space. For IPC, two processes can `mmap()` the same file with `MAP_SHARED`, enabling communication through direct memory access backed by the page cache.

The kernel's **page cache** manages the synchronization between the memory-mapped region and the file on disk. Writes to the mapped region are visible to other processes mapping the same file (via page table sharing). `msync()` can force dirty pages to disk.

**Best practice**: For pure IPC without persistence, use `mmap()` with `MAP_SHARED | MAP_ANONYMOUS` (no file backing) or POSIX shared memory (`shm_open` + `mmap`), which avoids filesystem overhead.

## Shared Memory Ring Buffer Implementation

The following implements a **lock-free single-producer single-consumer (SPSC) ring buffer** using shared memory, suitable for high-performance IPC.

```python
from __future__ import annotations
import mmap
import struct
import os
import time
import multiprocessing
from multiprocessing import shared_memory
from typing import Optional


class SharedRingBuffer:
    # Lock-free SPSC ring buffer in shared memory
    # Layout:
    #   [0:8]   - write_pos (uint64, only modified by producer)
    #   [8:16]  - read_pos  (uint64, only modified by consumer)
    #   [16:20] - capacity   (uint32, immutable after init)
    #   [20:24] - slot_size  (uint32, immutable after init)
    #   [24:28] - msg_count  (uint32, for statistics)
    #   [32+]   - slot data  (each slot: [4-byte length][payload])
    HEADER_SIZE = 32
    SLOT_HEADER_SIZE = 4  # 4 bytes for message length

    def __init__(
        self,
        name: str,
        capacity: int = 1024,
        slot_size: int = 256,
        create: bool = True,
    ) -> None:
        self.name = name
        self.capacity = capacity
        self.slot_size = slot_size
        total_size = self.HEADER_SIZE + capacity * (slot_size + self.SLOT_HEADER_SIZE)

        if create:
            # Producer creates the shared memory segment
            self.shm = shared_memory.SharedMemory(
                name=name, create=True, size=total_size
            )
            self._write_header(0, 0, capacity, slot_size)
        else:
            # Consumer attaches to existing segment
            self.shm = shared_memory.SharedMemory(name=name, create=False)
            _, _, self.capacity, self.slot_size = self._read_header()

    def _write_header(
        self, write_pos: int, read_pos: int, capacity: int, slot_size: int
    ) -> None:
        struct.pack_into("QQII", self.shm.buf, 0,
                         write_pos, read_pos, capacity, slot_size)

    def _read_header(self) -> tuple[int, int, int, int]:
        return struct.unpack_from("QQIi", self.shm.buf, 0)

    def _get_write_pos(self) -> int:
        return struct.unpack_from("Q", self.shm.buf, 0)[0]

    def _set_write_pos(self, pos: int) -> None:
        struct.pack_into("Q", self.shm.buf, 0, pos)

    def _get_read_pos(self) -> int:
        return struct.unpack_from("Q", self.shm.buf, 8)[0]

    def _set_read_pos(self, pos: int) -> None:
        struct.pack_into("Q", self.shm.buf, 8, pos)

    def _slot_offset(self, index: int) -> int:
        return (
            self.HEADER_SIZE
            + index * (self.slot_size + self.SLOT_HEADER_SIZE)
        )

    def write(self, data: bytes) -> bool:
        # Producer: write data to the next slot
        # Returns False if buffer is full
        if len(data) > self.slot_size:
            raise ValueError(
                f"Data size {len(data)} exceeds slot size {self.slot_size}"
            )
        w = self._get_write_pos()
        r = self._get_read_pos()
        next_w = (w + 1) % self.capacity
        if next_w == r:
            return False  # Buffer full

        offset = self._slot_offset(w)
        struct.pack_into("I", self.shm.buf, offset, len(data))
        self.shm.buf[offset + self.SLOT_HEADER_SIZE:
                     offset + self.SLOT_HEADER_SIZE + len(data)] = data
        # Memory barrier: ensure data is written before updating write_pos
        # In CPython, the GIL provides sufficient ordering for this demo
        self._set_write_pos(next_w)
        return True

    def read(self) -> Optional[bytes]:
        # Consumer: read data from the next slot
        # Returns None if buffer is empty
        w = self._get_write_pos()
        r = self._get_read_pos()
        if r == w:
            return None  # Buffer empty

        offset = self._slot_offset(r)
        msg_len = struct.unpack_from("I", self.shm.buf, offset)[0]
        data = bytes(
            self.shm.buf[offset + self.SLOT_HEADER_SIZE:
                         offset + self.SLOT_HEADER_SIZE + msg_len]
        )
        self._set_read_pos((r + 1) % self.capacity)
        return data

    def close(self) -> None:
        self.shm.close()

    def unlink(self) -> None:
        self.shm.unlink()
```

### Producer-Consumer with Performance Measurement

```python
def producer_worker(
    shm_name: str, num_messages: int, msg_size: int, ready_event, start_event
) -> None:
    # Producer process: writes messages to the ring buffer
    ring = SharedRingBuffer(shm_name, create=False)
    payload = b"X" * msg_size
    ready_event.set()
    start_event.wait()

    sent = 0
    while sent < num_messages:
        if ring.write(payload):
            sent += 1
        # Busy-wait if full (for benchmarking; use semaphore in production)
    ring.close()


def consumer_worker(
    shm_name: str, num_messages: int, ready_event, start_event, result_dict
) -> None:
    # Consumer process: reads messages from the ring buffer
    ring = SharedRingBuffer(shm_name, create=False)
    ready_event.set()
    start_event.wait()

    received = 0
    total_bytes = 0
    t0 = time.perf_counter()
    while received < num_messages:
        data = ring.read()
        if data is not None:
            received += 1
            total_bytes += len(data)
    elapsed = time.perf_counter() - t0

    result_dict["elapsed"] = elapsed
    result_dict["total_bytes"] = total_bytes
    result_dict["messages"] = received
    ring.close()


def benchmark_ring_buffer() -> None:
    num_messages = 100_000
    msg_size = 128
    shm_name = "ipc_bench_ring"

    # Create the ring buffer in the main process
    ring = SharedRingBuffer(shm_name, capacity=4096, slot_size=msg_size, create=True)

    manager = multiprocessing.Manager()
    result_dict = manager.dict()
    prod_ready = multiprocessing.Event()
    cons_ready = multiprocessing.Event()
    start_event = multiprocessing.Event()

    producer = multiprocessing.Process(
        target=producer_worker,
        args=(shm_name, num_messages, msg_size, prod_ready, start_event),
    )
    consumer = multiprocessing.Process(
        target=consumer_worker,
        args=(shm_name, num_messages, cons_ready, start_event, result_dict),
    )

    producer.start()
    consumer.start()
    prod_ready.wait()
    cons_ready.wait()

    print("=== Shared Memory Ring Buffer Benchmark ===")
    print(f"  Messages: {num_messages}, Size: {msg_size} bytes each\n")

    start_event.set()  # Start both simultaneously
    producer.join()
    consumer.join()

    elapsed = result_dict["elapsed"]
    total_bytes = result_dict["total_bytes"]
    throughput_msgs = num_messages / elapsed
    throughput_mb = (total_bytes / 1024 / 1024) / elapsed

    print(f"  Elapsed:    {elapsed:.3f}s")
    print(f"  Throughput: {throughput_msgs:,.0f} msg/s")
    print(f"  Bandwidth:  {throughput_mb:.1f} MB/s")
    print(f"  Latency:    {elapsed / num_messages * 1e6:.2f} us/msg")

    ring.close()
    ring.unlink()


if __name__ == "__main__":
    benchmark_ring_buffer()
```

### IPC Performance Comparison

```python
import socket
import tempfile


def benchmark_pipe(num_messages: int, msg_size: int) -> float:
    # Benchmark anonymous pipe throughput
    r_fd, w_fd = os.pipe()
    payload = b"X" * msg_size

    pid = os.fork()
    if pid == 0:
        # Child: writer
        os.close(r_fd)
        for _ in range(num_messages):
            os.write(w_fd, payload)
        os.close(w_fd)
        os._exit(0)
    else:
        # Parent: reader
        os.close(w_fd)
        t0 = time.perf_counter()
        received = 0
        while received < num_messages:
            data = os.read(r_fd, msg_size)
            if not data:
                break
            received += len(data) // msg_size
        elapsed = time.perf_counter() - t0
        os.close(r_fd)
        os.waitpid(pid, 0)
        return elapsed


def benchmark_unix_socket(num_messages: int, msg_size: int) -> float:
    # Benchmark Unix domain socket throughput
    sock_path = tempfile.mktemp(suffix=".sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)
    payload = b"X" * msg_size

    pid = os.fork()
    if pid == 0:
        # Child: sender
        server.close()
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(sock_path)
        for _ in range(num_messages):
            client.sendall(payload)
        client.close()
        os._exit(0)
    else:
        # Parent: receiver
        conn, _ = server.accept()
        t0 = time.perf_counter()
        total = 0
        target = num_messages * msg_size
        while total < target:
            data = conn.recv(msg_size * 64)
            if not data:
                break
            total += len(data)
        elapsed = time.perf_counter() - t0
        conn.close()
        server.close()
        os.unlink(sock_path)
        os.waitpid(pid, 0)
        return elapsed


def compare_ipc_methods() -> None:
    n, size = 50_000, 128
    print("=== IPC Method Comparison ===")
    print(f"  {n} messages x {size} bytes\n")

    pipe_time = benchmark_pipe(n, size)
    print(f"  Pipe:          {n / pipe_time:>10,.0f} msg/s")

    sock_time = benchmark_unix_socket(n, size)
    print(f"  Unix socket:   {n / sock_time:>10,.0f} msg/s")

    print(f"\n  Shared memory ring buffer is typically 5-10x faster")
    print(f"  because it avoids kernel-mediated copies entirely.")
```

## Summary and Key Takeaways

- **Pipes** are the simplest IPC mechanism but involve two kernel copies per message (user-to-kernel, kernel-to-user). Therefore, they are unsuitable for high-throughput data transfer.
- **Shared memory** is the fastest IPC because data transfer is zero-copy after initial `mmap()`. However, applications must implement their own synchronization, which is a significant source of bugs.
- **Unix domain sockets** offer the best balance of performance and features: bidirectional, message boundaries (SOCK_DGRAM), and file descriptor passing. **Best practice**: Always use `AF_UNIX` instead of `AF_INET` loopback for local IPC.
- **Ring buffers** in shared memory enable lock-free SPSC communication with predictable latency. The **trade-off** is complexity: multi-producer or multi-consumer scenarios require more sophisticated synchronization.
- **Pitfall**: Forgetting to clean up shared memory segments (`shm_unlink`), named pipes (`unlink`), or socket files leads to resource leaks that persist across process restarts.
- **Common mistake**: Using TCP loopback (127.0.0.1) for local IPC. It is measurably slower than Unix domain sockets because the data traverses the full TCP/IP stack including checksums, sequence numbers, and congestion control."""
    ),

    # --- 5. Container Internals ---
    (
        "os-internals/container-internals-namespaces-cgroups-overlay",
        "Explain Linux container internals including the six namespace types for pid net mnt uts ipc and user isolation, cgroups v2 resource controllers for CPU memory and IO limits, overlay filesystem for layered container images, seccomp-bpf syscall filtering for security, and implement a minimal container runtime in Python using OS primitives",
        r"""# Container Internals: Namespaces, Cgroups, and Building a Runtime

## What Containers Actually Are

Containers are not virtual machines. A container is a **regular Linux process** that has been isolated from the rest of the system using **kernel namespaces**, resource-limited using **cgroups**, and security-hardened using **seccomp-bpf** and **capabilities**. There is no hypervisor, no separate kernel, and no hardware virtualization. Understanding this is critical because it explains both the performance advantages (near-native speed) and the security limitations (shared kernel attack surface) of containers.

Docker, Podman, and containerd are orchestration tools that automate the creation and management of these kernel primitives. The actual isolation is performed entirely by the Linux kernel.

## Linux Namespaces

Namespaces partition kernel resources so that one set of processes sees one set of resources while another set of processes sees a different set. Linux supports **eight** namespace types (six original plus cgroup and time namespaces).

### PID Namespace

The **PID namespace** gives a process its own view of process IDs. The first process in a new PID namespace becomes PID 1 (the init process for that namespace). Processes inside cannot see or signal processes outside their namespace. However, the host can see all processes because namespaces are **hierarchical**: the parent namespace sees the child's processes with different PIDs.

**Pitfall**: PID 1 in a container has special responsibilities. If it does not reap zombie children (via `wait()`), zombie processes accumulate. This is why containers often use `tini` or `dumb-init` as PID 1 instead of the application directly.

### Network Namespace

Each **network namespace** has its own network stack: interfaces, routing tables, iptables rules, and `/proc/net`. Container runtimes create a **veth pair** (virtual Ethernet) to connect the container's network namespace to the host's. One end goes inside the container, the other attaches to a bridge (e.g., `docker0`) on the host.

**Common mistake**: Assuming network namespaces provide firewall isolation by default. Without explicit iptables rules, containers on the same bridge can communicate freely. Docker adds iptables rules automatically, but this is an application-level feature, not a kernel guarantee.

### Mount Namespace

The **mount namespace** gives a process its own view of the filesystem mount tree. Container runtimes use this to present the container with its own root filesystem (from the container image) while hiding the host's filesystems. `pivot_root()` or `chroot()` changes the apparent root directory.

### UTS Namespace

The **UTS namespace** isolates hostname and domain name. Each container can have its own hostname (`sethostname()`), therefore `hostname` inside the container returns the container's name, not the host's.

### IPC Namespace

The **IPC namespace** isolates System V IPC objects (shared memory segments, message queues, semaphores) and POSIX message queues. Without IPC namespace isolation, a container could access or interfere with the host's shared memory segments.

### User Namespace

The **user namespace** maps UIDs and GIDs inside the container to different UIDs outside. A process can be root (UID 0) inside its user namespace while being an unprivileged user (e.g., UID 100000) on the host. This is the foundation of **rootless containers**, which run without any host-level privileges.

**Best practice**: Always use user namespace mapping in production. Running containers as actual root on the host is a significant security risk because a container escape grants root access to the entire host.

## Cgroups v2 Resource Controllers

**Control groups (cgroups)** limit, account for, and isolate the resource usage of process groups. Cgroups v2 (unified hierarchy) replaced the fragmented cgroups v1 with a single, consistent tree mounted at `/sys/fs/cgroup/`.

### CPU Controller

- `cpu.max`: Hard bandwidth limit. Format: `"quota period"` in microseconds. `"200000 1000000"` limits the group to 200ms per 1000ms (20% of one CPU).
- `cpu.weight`: Proportional sharing (1-10000, default 100). Only takes effect when CPUs are contended.
- `cpu.max.burst`: Allows temporary burst above quota using accumulated idle time.

### Memory Controller

- `memory.max`: Hard limit in bytes. Exceeding triggers the OOM killer on processes in the cgroup.
- `memory.high`: Soft limit. Exceeding causes aggressive memory reclaim (slows the process) but does not kill it.
- `memory.swap.max`: Limits swap usage separately from physical memory.

The **trade-off** between `memory.max` and `memory.high` is that hard limits cause OOM kills (unpredictable application failures) while soft limits cause slowdowns (degraded but continued operation).

### IO Controller

- `io.max`: Limits read/write bandwidth and IOPS per device. Format: `"major:minor rbps=X wbps=Y riops=Z wiops=W"`.
- `io.weight`: Proportional IO sharing (1-10000).

**Pitfall**: IO cgroup limits only apply to **direct IO** by default. Buffered writes go through the page cache and are charged when pages are flushed, therefore writes may appear to exceed the limit in bursts.

## Overlay Filesystem

Container images use **layered filesystems** to enable efficient storage and fast startup. **OverlayFS** merges multiple directory trees into a single unified view:

- **lowerdir**: One or more read-only layers (the container image layers)
- **upperdir**: A writable layer for container modifications
- **workdir**: Scratch space for OverlayFS internal operations
- **merged**: The unified view presented to the container

When the container reads a file, OverlayFS searches from the upperdir down through the lowerdirs. When the container writes, a **copy-up** operation copies the file from the lower layer to the upperdir before modifying it. Deleted files are represented by **whiteout files** in the upperdir.

This layering is why `docker pull` only downloads layers you do not already have, and why running a container adds minimal storage overhead (only the upperdir changes).

## Seccomp-BPF

**Seccomp-BPF** restricts which system calls a process can make. Container runtimes install a BPF program that filters syscall numbers and arguments. Docker's default seccomp profile blocks approximately 44 syscalls out of ~300+, including dangerous ones like `reboot`, `kexec_load`, `mount` (within the container namespace), and `ptrace`.

**Best practice**: Use allowlisting (only permit known-good syscalls) rather than blocklisting for security-critical containers, because new syscalls added in kernel updates are automatically blocked.

## Minimal Container Runtime in Python

```python
from __future__ import annotations
import ctypes
import ctypes.util
import os
import socket
import struct
import sys
from typing import Optional


# Linux namespace flags (from linux/sched.h)
CLONE_NEWNS = 0x00020000    # Mount namespace
CLONE_NEWUTS = 0x04000000   # UTS namespace
CLONE_NEWIPC = 0x08000000   # IPC namespace
CLONE_NEWPID = 0x20000000   # PID namespace
CLONE_NEWNET = 0x40000000   # Network namespace
CLONE_NEWUSER = 0x10000000  # User namespace

# Cgroup v2 paths
CGROUP_ROOT = "/sys/fs/cgroup"

# Load libc for unshare and pivot_root
libc_name = ctypes.util.find_library("c")
libc = ctypes.CDLL(libc_name, use_errno=True)


def unshare(flags: int) -> None:
    # Create new namespaces for the calling process
    ret = libc.unshare(flags)
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, f"unshare failed: {os.strerror(errno)}")


def sethostname(name: str) -> None:
    # Set hostname in the current UTS namespace
    name_bytes = name.encode()
    ret = libc.sethostname(name_bytes, len(name_bytes))
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, f"sethostname failed: {os.strerror(errno)}")


def setup_user_namespace(pid: int, uid_map: str, gid_map: str) -> None:
    # Write uid_map and gid_map for user namespace
    # Must be done from parent process before child calls setgroups
    with open(f"/proc/{pid}/uid_map", "w") as f:
        f.write(uid_map)
    # Deny setgroups to allow gid_map write from unprivileged parent
    with open(f"/proc/{pid}/setgroups", "w") as f:
        f.write("deny")
    with open(f"/proc/{pid}/gid_map", "w") as f:
        f.write(gid_map)


def setup_cgroup(name: str, memory_max: int, cpu_quota: int, cpu_period: int) -> str:
    # Create a cgroup v2 group and set resource limits
    cg_path = os.path.join(CGROUP_ROOT, name)
    os.makedirs(cg_path, exist_ok=True)

    # Enable controllers
    with open(os.path.join(cg_path, "cgroup.subtree_control"), "w") as f:
        f.write("+memory +cpu +io")

    # Set memory limit
    with open(os.path.join(cg_path, "memory.max"), "w") as f:
        f.write(str(memory_max))

    # Set CPU quota
    with open(os.path.join(cg_path, "cpu.max"), "w") as f:
        f.write(f"{cpu_quota} {cpu_period}")

    return cg_path


def add_to_cgroup(cg_path: str, pid: int) -> None:
    # Move a process into a cgroup
    with open(os.path.join(cg_path, "cgroup.procs"), "w") as f:
        f.write(str(pid))


def setup_rootfs(rootfs_path: str) -> None:
    # Set up a minimal root filesystem using bind mounts
    # In production, this would use overlayfs with image layers
    os.makedirs(os.path.join(rootfs_path, "proc"), exist_ok=True)
    os.makedirs(os.path.join(rootfs_path, "sys"), exist_ok=True)
    os.makedirs(os.path.join(rootfs_path, "dev"), exist_ok=True)
    os.makedirs(os.path.join(rootfs_path, "tmp"), exist_ok=True)

    # Mount proc inside the new mount namespace
    # In a real runtime, pivot_root would be used here
    libc.mount(
        b"proc", os.path.join(rootfs_path, "proc").encode(),
        b"proc", 0, None
    )


class MiniContainer:
    # A minimal container runtime demonstrating namespace isolation,
    # cgroup resource limits, and filesystem setup
    #
    # WARNING: This is educational code. Production runtimes like runc
    # handle hundreds of edge cases this code does not.

    def __init__(
        self,
        name: str,
        rootfs: str,
        command: list[str],
        hostname: str = "container",
        memory_limit: int = 64 * 1024 * 1024,  # 64MB default
        cpu_quota: int = 50000,
        cpu_period: int = 100000,
    ) -> None:
        self.name = name
        self.rootfs = rootfs
        self.command = command
        self.hostname = hostname
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota
        self.cpu_period = cpu_period
        self.pid: Optional[int] = None

    def _child_process(self, sync_pipe_r: int, sync_pipe_w: int) -> None:
        # Runs inside the new namespaces
        os.close(sync_pipe_w)

        # Wait for parent to set up user namespace mappings
        os.read(sync_pipe_r, 1)
        os.close(sync_pipe_r)

        # Set hostname in our UTS namespace
        sethostname(self.hostname)

        # Set up root filesystem
        setup_rootfs(self.rootfs)

        # Change root to the container's rootfs
        os.chroot(self.rootfs)
        os.chdir("/")

        # Mount /proc for ps and other tools
        # (already mounted by setup_rootfs, but chroot moved us)

        # Drop all capabilities except those needed
        # In production: use libcap or prctl(PR_CAPBSET_DROP)

        # Execute the container's command
        print(f"[container] PID namespace PID: {os.getpid()}")
        print(f"[container] Hostname: {socket.gethostname()}")
        print(f"[container] Running: {self.command}")

        os.execvp(self.command[0], self.command)

    def start(self) -> int:
        # Create namespaces and launch the container process
        print(f"=== Starting container '{self.name}' ===")
        print(f"  Rootfs:       {self.rootfs}")
        print(f"  Memory limit: {self.memory_limit // 1024 // 1024}MB")
        print(f"  CPU quota:    {self.cpu_quota}/{self.cpu_period}us")

        # Create sync pipe for parent-child coordination
        sync_r, sync_w = os.pipe()

        # Set up cgroup before forking
        cg_path = setup_cgroup(
            f"minicontainer-{self.name}",
            self.memory_limit,
            self.cpu_quota,
            self.cpu_period,
        )

        # Fork with new namespaces
        flags = (
            CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC |
            CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWUSER
        )

        # Use fork + unshare pattern (clone is harder to use from Python)
        pid = os.fork()
        if pid == 0:
            # Child
            try:
                unshare(flags)
                self._child_process(sync_r, sync_w)
            except Exception as e:
                print(f"[container] Error: {e}", file=sys.stderr)
                os._exit(1)
        else:
            # Parent
            os.close(sync_r)
            self.pid = pid

            # Set up user namespace mapping (root in container = our uid outside)
            our_uid = os.getuid()
            our_gid = os.getgid()
            setup_user_namespace(
                pid,
                uid_map=f"0 {our_uid} 1",
                gid_map=f"0 {our_gid} 1",
            )

            # Add child to cgroup
            add_to_cgroup(cg_path, pid)

            # Signal child to proceed
            os.write(sync_w, b"\x00")
            os.close(sync_w)

            print(f"  Container PID (host): {pid}")
            return pid

    def wait(self) -> int:
        if self.pid is None:
            raise RuntimeError("Container not started")
        _, status = os.waitpid(self.pid, 0)
        exit_code = os.WEXITSTATUS(status)
        print(f"\n=== Container '{self.name}' exited with code {exit_code} ===")
        return exit_code
```

### Overlay Filesystem Setup Utility

```python
import subprocess


def setup_overlay(
    lower_dirs: list[str],
    upper_dir: str,
    work_dir: str,
    merged_dir: str,
) -> None:
    # Mount an overlayfs combining multiple lower layers with a writable upper
    # This is how container images work: each layer is a lowerdir
    os.makedirs(upper_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(merged_dir, exist_ok=True)

    lower = ":".join(lower_dirs)
    mount_opts = (
        f"lowerdir={lower},"
        f"upperdir={upper_dir},"
        f"workdir={work_dir}"
    )

    subprocess.run(
        ["mount", "-t", "overlay", "overlay", "-o", mount_opts, merged_dir],
        check=True,
    )
    print(f"OverlayFS mounted at {merged_dir}")
    print(f"  Lower layers: {lower_dirs}")
    print(f"  Upper (writable): {upper_dir}")
```

### Container Concepts Demonstration and Namespace Inspection

```python
def demonstrate_container_concepts() -> None:
    # Demonstrate container internals without requiring root
    # This shows the API and concepts even on systems where
    # we cannot actually create namespaces
    print("=== Container Internals Demonstration ===\n")

    print("Namespace types and their isolation:")
    namespaces = {
        "PID":     ("CLONE_NEWPID",  "Process ID tree"),
        "Network": ("CLONE_NEWNET",  "Network stack, interfaces, routes"),
        "Mount":   ("CLONE_NEWNS",   "Filesystem mount tree"),
        "UTS":     ("CLONE_NEWUTS",  "Hostname and domain name"),
        "IPC":     ("CLONE_NEWIPC",  "SysV IPC, POSIX message queues"),
        "User":    ("CLONE_NEWUSER", "UID/GID mappings"),
    }
    for ns_name, (flag, desc) in namespaces.items():
        print(f"  {ns_name:10s} | {flag:16s} | {desc}")

    print("\nCgroup v2 controllers:")
    controllers = {
        "cpu":    "CPU bandwidth (cpu.max) and proportional share (cpu.weight)",
        "memory": "Memory hard limit (memory.max) and soft limit (memory.high)",
        "io":     "Block IO bandwidth and IOPS limits per device",
        "pids":   "Maximum number of processes (fork bomb protection)",
    }
    for ctrl, desc in controllers.items():
        print(f"  {ctrl:8s} | {desc}")

    # Show current namespace IDs (works without privileges)
    print(f"\nCurrent process namespace IDs:")
    ns_dir = "/proc/self/ns"
    if os.path.exists(ns_dir):
        for ns_file in sorted(os.listdir(ns_dir)):
            target = os.readlink(os.path.join(ns_dir, ns_file))
            print(f"  {ns_file:12s} -> {target}")

    # Demonstrate cgroup resource limit file structure
    print("\nExample cgroup v2 resource limit commands:")
    examples = [
        ("Create cgroup",    "mkdir /sys/fs/cgroup/mycontainer"),
        ("Set memory limit", "echo 268435456 > /sys/fs/cgroup/mycontainer/memory.max"),
        ("Set CPU quota",    "echo '50000 100000' > /sys/fs/cgroup/mycontainer/cpu.max"),
        ("Set PID limit",    "echo 100 > /sys/fs/cgroup/mycontainer/pids.max"),
        ("Add process",      "echo $PID > /sys/fs/cgroup/mycontainer/cgroup.procs"),
    ]
    for label, cmd in examples:
        print(f"  {label:20s}: {cmd}")


if __name__ == "__main__":
    demonstrate_container_concepts()
```

## Summary and Key Takeaways

- Containers are **not virtual machines**; they are regular Linux processes isolated by kernel namespaces and resource-limited by cgroups. Therefore, container overhead is negligible compared to VMs.
- **Six namespace types** provide isolation: PID (process tree), Network (network stack), Mount (filesystem view), UTS (hostname), IPC (shared memory/queues), and User (UID/GID mapping). **Best practice**: Always use user namespaces to avoid running as true root on the host.
- **Cgroups v2** provides hierarchical resource control. The **trade-off** between hard limits (`memory.max`, `cpu.max`) and soft limits (`memory.high`, `cpu.weight`) determines whether overuse causes kills/throttling or graceful degradation.
- **OverlayFS** enables the layered image model that makes containers space-efficient and fast to start. However, heavy writes cause **copy-up** overhead, which is a **pitfall** for write-intensive workloads (use volumes instead).
- **Seccomp-BPF** restricts available syscalls, reducing the kernel attack surface. **Common mistake**: Running containers with `--privileged`, which disables seccomp, AppArmor, and most namespace restrictions, negating container security entirely.
- A production container runtime (runc, crun) handles hundreds of edge cases: cgroup cleanup on failure, proper signal forwarding, terminal management, rootfs pivot, capability dropping, and OCI spec compliance. The minimal runtime above demonstrates the core concepts but should never be used in production."""
    ),
]
