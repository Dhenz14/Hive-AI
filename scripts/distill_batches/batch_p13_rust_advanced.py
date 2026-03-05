PAIRS = [
    (
        "rust-advanced/async-runtime-internals",
        r"""Explain Rust async runtime internals including the Future trait and polling mechanism, waker and context design, executor implementation from scratch, task scheduling strategies, and how tokio's work-stealing scheduler achieves high performance.""",
        r"""## Rust Async Runtime Internals: Futures, Wakers, Executors, and Work-Stealing

Rust's async system is fundamentally different from other languages. Instead of green threads (Go) or callback-based event loops (Node.js), Rust uses **zero-cost futures** that are state machines compiled at build time. **Because** futures are lazy and poll-based, the runtime has complete control over scheduling without hidden allocations. **However**, this design pushes complexity into the runtime implementation, making it essential to understand the polling mechanism, waker system, and executor design.

### The Future Trait and Polling

At its core, every Rust `async fn` compiles into a state machine implementing the `Future` trait. The runtime repeatedly **polls** the future until it returns `Poll::Ready`.

```rust
use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll, Waker, RawWaker, RawWakerVTable};
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;

// The Future trait (simplified from std)
// trait Future {
//     type Output;
//     fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output>;
// }

// A simple future that counts down
// Common mistake: forgetting that poll() can be called multiple times
// Therefore, futures must be idempotent and track their state
struct CountdownFuture {
    count: u32,
    waker: Option<Waker>,
}

impl Future for CountdownFuture {
    type Output = String;

    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        if self.count == 0 {
            Poll::Ready("Done!".to_string())
        } else {
            self.count -= 1;
            // Store waker so we can wake the task later
            // Best practice: always update the waker on each poll
            // because the executor may move the task between threads
            self.waker = Some(cx.waker().clone());
            // Wake immediately to be re-polled (in real code, this would
            // be triggered by an I/O event or timer)
            cx.waker().wake_by_ref();
            Poll::Pending
        }
    }
}

// Pin ensures the future doesn't move in memory after first poll
// Pitfall: self-referential futures break if moved
// Pin<&mut Self> guarantees the future stays at its address
// This is critical because async state machines often contain
// references to their own fields

// Waker internals — how the runtime knows to re-poll a future
// The Waker is a fat pointer: data pointer + vtable
fn create_raw_waker(task_id: usize, queue: Arc<Mutex<VecDeque<usize>>>) -> RawWaker {
    let data = Arc::into_raw(Arc::new((task_id, queue))) as *const ();

    unsafe fn clone_fn(ptr: *const ()) -> RawWaker {
        let arc = Arc::from_raw(ptr as *const (usize, Arc<Mutex<VecDeque<usize>>>));
        let cloned = arc.clone();
        std::mem::forget(arc); // don't drop the original
        RawWaker::new(Arc::into_raw(cloned) as *const (), &VTABLE)
    }

    unsafe fn wake_fn(ptr: *const ()) {
        let arc = Arc::from_raw(ptr as *const (usize, Arc<Mutex<VecDeque<usize>>>));
        let (task_id, queue) = &*arc;
        queue.lock().unwrap().push_back(*task_id);
        // arc is dropped here, decrementing refcount
    }

    unsafe fn wake_by_ref_fn(ptr: *const ()) {
        let arc = Arc::from_raw(ptr as *const (usize, Arc<Mutex<VecDeque<usize>>>));
        let (task_id, queue) = &*arc;
        queue.lock().unwrap().push_back(*task_id);
        std::mem::forget(arc); // don't drop, we don't own it
    }

    unsafe fn drop_fn(ptr: *const ()) {
        drop(Arc::from_raw(ptr as *const (usize, Arc<Mutex<VecDeque<usize>>>)));
    }

    static VTABLE: RawWakerVTable = RawWakerVTable::new(
        clone_fn, wake_fn, wake_by_ref_fn, drop_fn,
    );

    RawWaker::new(data, &VTABLE)
}
```

### Building a Minimal Executor

An **executor** drives futures to completion by polling them when woken. The simplest executor is a single-threaded run loop, but production runtimes use multi-threaded work-stealing.

```rust
use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll, Waker};
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;

// Task wraps a future with its metadata
struct Task {
    future: Pin<Box<dyn Future<Output = ()> + Send>>,
    // Trade-off: Box<dyn Future> adds allocation but enables type erasure
    // However, this is necessary because the executor stores heterogeneous futures
}

struct SimpleExecutor {
    // Single-threaded executor — simple but not production-grade
    // Best practice: use this for understanding, use tokio for production
    task_queue: Arc<Mutex<VecDeque<usize>>>,
    tasks: Vec<Option<Task>>,
}

impl SimpleExecutor {
    fn new() -> Self {
        SimpleExecutor {
            task_queue: Arc::new(Mutex::new(VecDeque::new())),
            tasks: Vec::new(),
        }
    }

    fn spawn<F>(&mut self, future: F)
    where
        F: Future<Output = ()> + Send + 'static,
    {
        let task_id = self.tasks.len();
        self.tasks.push(Some(Task {
            future: Box::pin(future),
        }));
        self.task_queue.lock().unwrap().push_back(task_id);
    }

    fn run(&mut self) {
        // Main event loop: poll tasks that have been woken
        loop {
            let task_id = {
                let mut queue = self.task_queue.lock().unwrap();
                if queue.is_empty() {
                    // No more tasks to poll — check if all done
                    if self.tasks.iter().all(|t| t.is_none()) {
                        return; // All tasks completed
                    }
                    // Pitfall: busy-waiting here wastes CPU
                    // Production runtimes use condvar or epoll to block
                    continue;
                }
                queue.pop_front().unwrap()
            };

            if let Some(task) = &mut self.tasks[task_id] {
                // Create waker for this task
                let raw_waker = create_raw_waker(task_id, self.task_queue.clone());
                let waker = unsafe { Waker::from_raw(raw_waker) };
                let mut cx = Context::from_waker(&waker);

                // Poll the future
                match task.future.as_mut().poll(&mut cx) {
                    Poll::Ready(()) => {
                        // Task completed — remove it
                        self.tasks[task_id] = None;
                    }
                    Poll::Pending => {
                        // Task will be re-queued when its waker is called
                    }
                }
            }
        }
    }
}
```

### Tokio's Work-Stealing Scheduler

**Tokio** uses a multi-threaded work-stealing scheduler inspired by Go's goroutine scheduler. Each worker thread has a local run queue, and idle workers **steal** tasks from busy workers' queues. **Therefore**, work is automatically balanced across threads without central coordination.

```rust
use std::sync::atomic::{AtomicUsize, Ordering};
use std::collections::VecDeque;

// Simplified model of tokio's work-stealing scheduler
// Each worker has:
// 1. A local queue (LIFO for cache locality)
// 2. Access to a global injection queue
// 3. Ability to steal from other workers' queues

struct WorkStealingScheduler {
    workers: Vec<WorkerState>,
    global_queue: Mutex<VecDeque<usize>>,  // task IDs
    num_workers: usize,
    // Steal counter for round-robin victim selection
    steal_offset: AtomicUsize,
}

struct WorkerState {
    // Local queue: bounded, overflow goes to global queue
    // Trade-off: larger local queue = less contention but more imbalance
    local_queue: VecDeque<usize>,
    local_capacity: usize,  // typically 256 in tokio
}

impl WorkStealingScheduler {
    fn new(num_workers: usize) -> Self {
        let workers = (0..num_workers)
            .map(|_| WorkerState {
                local_queue: VecDeque::with_capacity(256),
                local_capacity: 256,
            })
            .collect();

        WorkStealingScheduler {
            workers,
            global_queue: Mutex::new(VecDeque::new()),
            num_workers,
            steal_offset: AtomicUsize::new(0),
        }
    }

    fn schedule_task(&mut self, worker_id: usize, task_id: usize) {
        let worker = &mut self.workers[worker_id];
        if worker.local_queue.len() < worker.local_capacity {
            // Push to local queue (fast path, no contention)
            worker.local_queue.push_back(task_id);
        } else {
            // Local queue full — move half to global queue
            // Best practice: batch-drain to reduce global queue contention
            // Common mistake: pushing one task at a time to global queue
            let drain_count = worker.local_queue.len() / 2;
            let mut global = self.global_queue.lock().unwrap();
            for _ in 0..drain_count {
                if let Some(t) = worker.local_queue.pop_front() {
                    global.push_back(t);
                }
            }
            worker.local_queue.push_back(task_id);
        }
    }

    fn next_task(&mut self, worker_id: usize) -> Option<usize> {
        // 1. Try local queue first (LIFO for cache locality)
        if let Some(task) = self.workers[worker_id].local_queue.pop_back() {
            return Some(task);
        }

        // 2. Try global queue
        // However, global queue access requires a lock
        {
            let mut global = self.global_queue.lock().unwrap();
            if let Some(task) = global.pop_front() {
                // Batch-steal from global: take up to half
                let steal_count = std::cmp::min(global.len(), self.workers[worker_id].local_capacity / 2);
                for _ in 0..steal_count {
                    if let Some(t) = global.pop_front() {
                        self.workers[worker_id].local_queue.push_back(t);
                    }
                }
                return Some(task);
            }
        }

        // 3. Steal from other workers
        // Round-robin starting from a random offset to avoid contention
        let offset = self.steal_offset.fetch_add(1, Ordering::Relaxed);
        for i in 0..self.num_workers {
            let victim = (offset + i) % self.num_workers;
            if victim == worker_id {
                continue;
            }
            // Steal half of victim's queue
            // Therefore, work is balanced without central coordination
            let victim_len = self.workers[victim].local_queue.len();
            if victim_len > 1 {
                let steal_count = victim_len / 2;
                // In real tokio, this uses atomic operations on a lock-free deque
                // Pitfall: naive stealing with locks creates contention
                for _ in 0..steal_count {
                    if let Some(t) = self.workers[victim].local_queue.pop_front() {
                        self.workers[worker_id].local_queue.push_back(t);
                    }
                }
                return self.workers[worker_id].local_queue.pop_back();
            }
        }

        None // No work available — worker should park
    }
}
```

### Key Takeaways

- Rust futures are **zero-cost state machines** compiled at build time — **because** there's no runtime overhead, the only cost is what you explicitly opt into
- The **Waker** mechanism is how I/O events signal the executor — a **common mistake** is not updating the waker on each poll, which can cause missed wake-ups
- **Pin** prevents self-referential futures from being moved — **pitfall**: using `unsafe` to circumvent Pin guarantees leads to undefined behavior
- **Work-stealing** achieves load balancing without central coordination — the **trade-off** is implementation complexity vs. near-optimal CPU utilization
- **Best practice**: use tokio or async-std for production, build your own executor only for learning
- **However**, understanding the internals helps debug async performance issues — **therefore**, knowing about task scheduling, waker semantics, and Pin is valuable even if you never write a runtime
"""
    ),
    (
        "rust-advanced/unsafe-ffi-patterns",
        r"""Explain Rust unsafe code and FFI patterns including when unsafe is justified, common unsafe patterns like raw pointer manipulation, safe abstraction boundaries, C interop with bindgen and cbindgen, and strategies for auditing and minimizing unsafe code.""",
        r"""## Rust Unsafe Code and FFI: Raw Pointers, Safe Abstractions, and C Interop

**Unsafe Rust** exists **because** some valid programs cannot be verified by the borrow checker. Hardware access, C interop, performance-critical data structures, and certain lock-free algorithms all require operations the compiler can't prove safe. **However**, unsafe doesn't mean "no rules" — it means "the programmer guarantees correctness instead of the compiler." The **trade-off** is between expressiveness and automated safety verification.

### When Unsafe is Justified

**Best practice**: unsafe should only be used when there is no safe alternative, and unsafe blocks should be as small as possible, wrapped in safe abstractions.

```rust
use std::ptr;
use std::alloc::{self, Layout};
use std::mem;

// Justified uses of unsafe:
// 1. Implementing data structures that require raw pointer manipulation
// 2. Calling C functions (FFI)
// 3. Implementing Send/Sync for types the compiler can't verify
// 4. Performance-critical code where bounds checks are prohibitive

// Example: A simple arena allocator
// Common mistake: making the entire struct unsafe instead of isolating unsafe operations
struct Arena {
    buffer: *mut u8,
    capacity: usize,
    offset: usize, // next free byte
}

impl Arena {
    fn new(capacity: usize) -> Self {
        // unsafe is required for raw memory allocation
        let layout = Layout::from_size_align(capacity, 8).unwrap();
        let buffer = unsafe { alloc::alloc(layout) };
        if buffer.is_null() {
            alloc::handle_alloc_error(layout);
        }
        Arena { buffer, capacity, offset: 0 }
    }

    fn alloc<T>(&mut self, value: T) -> &mut T {
        // Align the offset
        let align = mem::align_of::<T>();
        let size = mem::size_of::<T>();
        self.offset = (self.offset + align - 1) & !(align - 1);

        if self.offset + size > self.capacity {
            panic!("Arena out of memory");
        }

        // Safety: we've verified alignment and bounds above
        // Therefore, the pointer arithmetic is valid
        // Pitfall: forgetting to check alignment causes UB on some architectures
        let ptr = unsafe { self.buffer.add(self.offset) as *mut T };
        unsafe { ptr::write(ptr, value) };
        self.offset += size;

        // Safety: ptr is valid, aligned, and exclusively borrowed through &mut self
        unsafe { &mut *ptr }
    }
}

impl Drop for Arena {
    fn drop(&mut self) {
        // Must deallocate with the same layout used for allocation
        // Common mistake: using a different layout in drop
        let layout = Layout::from_size_align(self.capacity, 8).unwrap();
        unsafe { alloc::dealloc(self.buffer, layout) };
    }
}

// Safe API: users never see raw pointers
// Best practice: expose a safe interface that encapsulates all unsafe operations
fn example_usage() {
    let mut arena = Arena::new(1024);
    let x: &mut i32 = arena.alloc(42);
    let y: &mut f64 = arena.alloc(3.14);
    // x and y are safe references with proper lifetimes
}
```

### FFI with C: bindgen and cbindgen

**FFI (Foreign Function Interface)** allows Rust to call C libraries and vice versa. **Because** C has no ownership or lifetime system, every FFI boundary is inherently unsafe.

```rust
// Calling C from Rust using bindgen-generated bindings
// bindgen reads C headers and generates Rust extern declarations

// Generated by bindgen from a C header:
// typedef struct {
//     int width;
//     int height;
//     unsigned char* data;
// } Image;
// Image* image_create(int w, int h);
// void image_destroy(Image* img);
// int image_get_pixel(const Image* img, int x, int y);

#[repr(C)]  // Ensure C-compatible memory layout
struct Image {
    width: i32,
    height: i32,
    data: *mut u8,
}

extern "C" {
    fn image_create(w: i32, h: i32) -> *mut Image;
    fn image_destroy(img: *mut Image);
    fn image_get_pixel(img: *const Image, x: i32, y: i32) -> i32;
}

// Safe Rust wrapper around the C library
// Trade-off: wrapper adds a thin layer but prevents misuse
struct SafeImage {
    ptr: *mut Image,
}

impl SafeImage {
    fn new(width: i32, height: i32) -> Option<Self> {
        // Safety: image_create returns null on failure
        let ptr = unsafe { image_create(width, height) };
        if ptr.is_null() {
            None
        } else {
            Some(SafeImage { ptr })
        }
    }

    fn get_pixel(&self, x: i32, y: i32) -> Option<i32> {
        // Bounds checking in the safe wrapper
        // Best practice: validate inputs before passing to C
        // because C functions typically don't bounds-check
        let img = unsafe { &*self.ptr };
        if x < 0 || x >= img.width || y < 0 || y >= img.height {
            return None;
        }
        Some(unsafe { image_get_pixel(self.ptr, x, y) })
    }

    fn width(&self) -> i32 {
        unsafe { (*self.ptr).width }
    }

    fn height(&self) -> i32 {
        unsafe { (*self.ptr).height }
    }
}

impl Drop for SafeImage {
    fn drop(&mut self) {
        // Ensure C resources are always freed
        // Pitfall: forgetting to call the C destructor leaks memory
        // However, Rust's Drop trait guarantees cleanup
        unsafe { image_destroy(self.ptr) };
    }
}

// Cannot be shared across threads unless the C library is thread-safe
// Common mistake: implementing Send/Sync without verifying thread safety
// unsafe impl Send for SafeImage {}

// Exposing Rust to C with cbindgen
// cbindgen generates C headers from Rust code

#[no_mangle]
pub extern "C" fn rust_process_data(data: *const u8, len: usize) -> i32 {
    // Safety contract: caller must provide valid pointer and length
    if data.is_null() || len == 0 {
        return -1; // Error code
    }

    // Convert to safe Rust slice
    // Safety: we checked for null, caller guarantees len is valid
    let slice = unsafe { std::slice::from_raw_parts(data, len) };

    // Now we can use safe Rust operations
    slice.iter().map(|&b| b as i32).sum()
}

// String handling across FFI boundary
use std::ffi::{CStr, CString};

#[no_mangle]
pub extern "C" fn rust_greet(name: *const std::os::raw::c_char) -> *mut std::os::raw::c_char {
    // Convert C string to Rust string
    // Pitfall: CStr::from_ptr panics on null, so check first
    if name.is_null() {
        return ptr::null_mut();
    }

    let c_str = unsafe { CStr::from_ptr(name) };
    let name_str = match c_str.to_str() {
        Ok(s) => s,
        Err(_) => return ptr::null_mut(), // Invalid UTF-8
    };

    // Create greeting and return as C string
    // The caller is responsible for freeing this with rust_free_string
    let greeting = format!("Hello, {}!", name_str);
    match CString::new(greeting) {
        Ok(c_greeting) => c_greeting.into_raw(),
        Err(_) => ptr::null_mut(), // Contained null byte
    }
}

#[no_mangle]
pub extern "C" fn rust_free_string(s: *mut std::os::raw::c_char) {
    // Safety: pointer must have been created by CString::into_raw
    // Common mistake: freeing with C's free() instead of Rust's deallocator
    // because Rust and C may use different allocators
    if !s.is_null() {
        unsafe { drop(CString::from_raw(s)) };
    }
}
```

### Auditing Unsafe Code

```rust
// Strategies for minimizing and auditing unsafe code:

// 1. Use #[deny(unsafe_code)] at the crate level, allow only in specific modules
// #![deny(unsafe_code)]
// mod ffi {
//     #![allow(unsafe_code)]
//     // All unsafe code lives here
// }

// 2. Document safety invariants with SAFETY comments
// Best practice: every unsafe block should have a SAFETY comment
// explaining why the operation is sound

// 3. Use cargo-geiger to audit unsafe usage across dependencies
// $ cargo install cargo-geiger
// $ cargo geiger
// This shows exactly how much unsafe code each dependency uses

// 4. Prefer safe abstractions from well-audited crates
// - crossbeam for lock-free data structures
// - parking_lot for mutexes
// - bytes for byte buffer management

// 5. Use Miri for detecting undefined behavior
// $ cargo +nightly miri test
// Miri executes code in an interpreter that checks for UB:
// - Out-of-bounds access
// - Use-after-free
// - Data races
// - Invalid pointer alignment

// 6. Encapsulation pattern: unsafe module with safe public API
mod inner {
    // All unsafe operations are private
    pub(super) unsafe fn raw_operation(ptr: *mut u8, offset: usize) -> u8 {
        // SAFETY: caller must ensure ptr is valid for offset bytes
        *ptr.add(offset)
    }
}

pub fn safe_operation(buffer: &[u8], index: usize) -> Option<u8> {
    // Safe wrapper does bounds checking
    if index >= buffer.len() {
        return None;
    }
    // SAFETY: we verified index < buffer.len(), so ptr + index is valid
    Some(unsafe { inner::raw_operation(buffer.as_ptr() as *mut u8, index) })
}

// 7. Property testing with proptest/quickcheck for unsafe code
// Therefore, even if you can't formally verify, you can fuzz
// Trade-off: testing catches bugs but doesn't prove absence of bugs
```

### Key Takeaways

- **Unsafe** means "I guarantee correctness" not "anything goes" — **because** undefined behavior in unsafe blocks can affect the entire program
- **Best practice**: isolate unsafe in small blocks with `SAFETY` comments explaining invariants
- **FFI boundaries** are always unsafe — **therefore** wrap C APIs in safe Rust types with proper Drop implementations
- **Common mistake**: implementing `Send`/`Sync` without verifying thread safety of the underlying C library
- **Pitfall**: using C's `free()` on Rust-allocated memory (or vice versa) — allocators may differ
- **However**, well-designed safe abstractions over unsafe code are the foundation of Rust's ecosystem — `Vec`, `String`, `Arc` all use unsafe internally
- Tools like **Miri** and **cargo-geiger** help audit unsafe — the **trade-off** is that they add CI time but catch real bugs
"""
    ),
]
