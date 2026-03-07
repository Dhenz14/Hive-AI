"""
Rust language training pairs - ownership, borrowing, lifetimes, Rc/Arc, interior mutability
"""

pairs = [
    {
        "instruction": r'''<thinking>
The user wants to understand Rust's ownership and borrowing rules. I should explain the three core rules and show how borrowing works with mutable and immutable references. I will demonstrate with a practical example that shows common pitfalls and how the borrow checker enforces safety.
</thinking>

Explain Rust's ownership model and borrowing rules with examples showing mutable vs immutable borrows.''',
        "output": r'''Rust enforces memory safety at compile time through three ownership rules:

1. Each value has exactly one owner.
2. When the owner goes out of scope, the value is dropped.
3. You can have either ONE mutable reference OR any number of immutable references -- never both at the same time.

```rust
fn main() {
    // Ownership transfer (move)
    let s1 = String::from("hello");
    let s2 = s1; // s1 is moved to s2; s1 is no longer valid
    // println!("{s1}"); // compile error: value used after move

    // Immutable borrowing -- multiple readers allowed
    let data = vec![1, 2, 3, 4, 5];
    let r1 = &data;
    let r2 = &data;
    println!("r1={r1:?}, r2={r2:?}"); // both valid

    // Mutable borrowing -- exclusive access
    let mut scores = vec![10, 20, 30];
    let m = &mut scores;
    m.push(40);
    // let r3 = &scores; // error: cannot borrow while mutably borrowed
    println!("scores via m: {m:?}");

    // After mutable borrow ends, immutable borrows are fine again
    println!("scores: {scores:?}");

    // Borrowing in functions
    let name = String::from("Rust");
    greet(&name); // borrows, does not consume
    println!("Still own: {name}");
}

fn greet(name: &str) {
    println!("Hello, {name}!");
}
```

The borrow checker prevents data races at compile time. A mutable reference guarantees exclusive access, so no other code can read or write the data simultaneously. This eliminates an entire class of bugs without runtime overhead.'''
    },
    {
        "instruction": r'''<thinking>
The user asks about lifetimes in Rust. I should explain lifetime annotations, why they exist, and show a function that requires explicit lifetime parameters. I will include the case where the compiler cannot infer lifetimes and the programmer must annotate them.
</thinking>

How do lifetime annotations work in Rust? Show a function that requires explicit lifetime parameters and explain when the compiler needs them.''',
        "output": r'''Lifetime annotations tell the compiler how long references are valid relative to each other. The compiler uses three elision rules to infer lifetimes automatically, but when multiple input references could determine the output lifetime, you must annotate explicitly.

```rust
// The compiler cannot tell which input reference the return value
// borrows from, so we annotate with 'a to say: the returned
// reference lives at least as long as both inputs.
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() >= y.len() { x } else { y }
}

// Lifetime in a struct -- the struct cannot outlive the reference it holds
struct Excerpt<'a> {
    text: &'a str,
}

impl<'a> Excerpt<'a> {
    // Elision rule: &self lifetime is assigned to the return value
    fn first_word(&self) -> &str {
        self.text.split_whitespace().next().unwrap_or("")
    }

    // Multiple inputs with &self -- still needs annotation if
    // the return could come from the other reference
    fn longer_than(&self, other: &'a str) -> &'a str {
        if self.text.len() > other.len() {
            self.text
        } else {
            other
        }
    }
}

fn main() {
    let novel = String::from("Call me Ishmael. Some years ago...");
    let first_sentence;
    {
        let idx = novel.find('.').unwrap_or(novel.len());
        first_sentence = &novel[..idx];
    }
    let excerpt = Excerpt { text: first_sentence };
    println!("Excerpt: {}", excerpt.first_word());

    let a = String::from("long string");
    let result;
    {
        let b = String::from("xyz");
        result = longest(a.as_str(), b.as_str());
        println!("Longest: {result}");
        // result cannot escape this block if b is shorter-lived
    }
}
```

The key insight: lifetimes do not change how long values live. They let the compiler verify that references are always valid, preventing dangling pointers.'''
    },
    {
        "instruction": r'''Show how to use Rc and Arc in Rust for shared ownership, including when to pick each one.''',
        "output": r'''`Rc<T>` (reference-counted) allows multiple owners of the same heap data in single-threaded code. `Arc<T>` (atomic reference-counted) does the same but is safe to share across threads.

```rust
use std::rc::Rc;
use std::sync::Arc;
use std::thread;

fn demo_rc() {
    // Rc for single-threaded shared ownership
    let shared = Rc::new(vec![1, 2, 3]);
    let a = Rc::clone(&shared); // cheap pointer copy, not deep clone
    let b = Rc::clone(&shared);

    println!("a={a:?}, b={b:?}");
    println!("Reference count: {}", Rc::strong_count(&shared)); // 3

    // When all Rc handles drop, the vec is freed
    drop(a);
    println!("After drop: {}", Rc::strong_count(&shared)); // 2
}

fn demo_arc() {
    // Arc for multi-threaded shared ownership
    let data = Arc::new(vec![10, 20, 30, 40, 50]);

    let mut handles = vec![];
    for i in 0..3 {
        let data_clone = Arc::clone(&data);
        handles.push(thread::spawn(move || {
            let sum: i32 = data_clone.iter().sum();
            println!("Thread {i}: sum = {sum}");
        }));
    }

    for h in handles {
        h.join().unwrap();
    }
    println!("Original still valid: {data:?}");
}

fn main() {
    demo_rc();
    demo_arc();
}
```

Decision guide:
- Single thread, shared reads --> `Rc<T>`
- Multiple threads, shared reads --> `Arc<T>`
- Need mutation too? Combine with interior mutability:
  - `Rc<RefCell<T>>` for single-threaded mutable sharing
  - `Arc<Mutex<T>>` or `Arc<RwLock<T>>` for multi-threaded mutable sharing

`Rc` is cheaper than `Arc` because it skips atomic operations, so prefer `Rc` when threads are not involved.'''
    },
    {
        "instruction": r'''Explain interior mutability in Rust using Cell, RefCell, and Mutex. When should I use each?''',
        "output": r'''Interior mutability lets you mutate data even when you only have an immutable reference. Rust provides several types for this, each with different tradeoffs.

```rust
use std::cell::{Cell, RefCell};
use std::sync::Mutex;

// Cell<T> -- for Copy types, zero overhead, single-threaded
struct Counter {
    count: Cell<u32>,
}

impl Counter {
    fn new() -> Self {
        Counter { count: Cell::new(0) }
    }
    fn increment(&self) {
        // &self, not &mut self -- yet we mutate!
        self.count.set(self.count.get() + 1);
    }
    fn value(&self) -> u32 {
        self.count.get()
    }
}

// RefCell<T> -- for non-Copy types, runtime borrow checking, single-threaded
struct Logger {
    messages: RefCell<Vec<String>>,
}

impl Logger {
    fn new() -> Self {
        Logger { messages: RefCell::new(Vec::new()) }
    }
    fn log(&self, msg: &str) {
        // borrow_mut() panics if already borrowed -- checked at runtime
        self.messages.borrow_mut().push(msg.to_string());
    }
    fn dump(&self) {
        for msg in self.messages.borrow().iter() {
            println!("[LOG] {msg}");
        }
    }
}

// Mutex<T> -- for any type, thread-safe, blocks on contention
fn demo_mutex() {
    let shared = Mutex::new(vec![1, 2, 3]);
    {
        let mut guard = shared.lock().unwrap();
        guard.push(4);
    } // MutexGuard drops here, releasing the lock
    println!("{:?}", shared.lock().unwrap());
}

fn main() {
    let c = Counter::new();
    c.increment();
    c.increment();
    println!("Count: {}", c.value());

    let logger = Logger::new();
    logger.log("started");
    logger.log("finished");
    logger.dump();

    demo_mutex();
}
```

When to use each:
- `Cell<T>` -- T is Copy, single thread, zero cost
- `RefCell<T>` -- T is not Copy, single thread, small runtime cost
- `Mutex<T>` -- any T, multi-threaded, blocks on contention
- `RwLock<T>` -- multi-threaded, many readers / one writer'''
    },
    {
        "instruction": r'''What is Pin in Rust and why does async code need it? Show a simple example.''',
        "output": r'''`Pin<P>` guarantees that the value behind pointer `P` will not be moved in memory. This matters for self-referential types -- structs that contain pointers to their own fields. Async futures are the most common example because the compiler-generated state machines can hold references across await points.

```rust
use std::pin::Pin;
use std::marker::PhantomPinned;
use std::future::Future;

// A self-referential struct (simplified)
struct SelfRef {
    data: String,
    // This would point into data -- moving the struct would
    // invalidate this pointer
    ptr: *const String,
    _pin: PhantomPinned, // opts out of Unpin
}

impl SelfRef {
    fn new(s: &str) -> Pin<Box<Self>> {
        let mut boxed = Box::new(SelfRef {
            data: s.to_string(),
            ptr: std::ptr::null(),
            _pin: PhantomPinned,
        });
        let self_ptr: *const String = &boxed.data;
        // SAFETY: we do not move the data after pinning
        unsafe {
            let mut_ref = Pin::as_mut(&mut Pin::new_unchecked(&mut *boxed));
            Pin::get_unchecked_mut(mut_ref).ptr = self_ptr;
        }
        unsafe { Pin::new_unchecked(boxed) }
    }

    fn get_data(self: Pin<&Self>) -> &str {
        &self.data
    }
}

// Why async needs Pin:
// When you write:
//   async fn fetch(url: &str) -> String { ... }
// The compiler generates a Future whose poll method is:
//   fn poll(self: Pin<&mut Self>, cx: &mut Context) -> Poll<String>
//
// Pin<&mut Self> ensures the future is not moved between polls,
// keeping internal references valid across .await points.

async fn example() -> u32 {
    let data = vec![1, 2, 3];
    // If this future were moved after this point, the reference
    // to data inside the state machine would dangle.
    tokio::time::sleep(std::time::Duration::from_millis(1)).await;
    data.iter().sum()
}

fn main() {
    let pinned = SelfRef::new("hello pinned world");
    println!("{}", pinned.as_ref().get_data());

    // Futures are automatically pinned by the runtime via Box::pin
    // or tokio::pin! macro -- you rarely build Pin manually.
}
```

In practice, you almost never construct Pin yourself. The async runtime (tokio, async-std) handles pinning futures. You only need Pin directly when implementing Future by hand or building self-referential data structures.'''
    },
]
