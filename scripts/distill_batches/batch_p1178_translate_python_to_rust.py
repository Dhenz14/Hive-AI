"""Code translation pairs: Python to Rust (ownership, lifetimes, Result)."""

PAIRS = [
    (
        "code-translation/python-to-rust",
        r'''Convert this Python file reader with error handling to Rust:

def read_config(path):
    config = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    raise ValueError(f"Invalid line: {line}")
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    except FileNotFoundError:
        print(f"Config file not found: {path}")
        return None
    except ValueError as e:
        print(f"Parse error: {e}")
        return None
    return config''',
        r'''<think>
Python file reading with error handling to Rust. This is a great example because it touches on several core Rust concepts:

1. Error handling: Python uses try/except with None returns. Rust uses Result<T, E>. I should define a proper error enum or use anyhow/thiserror. For teaching purposes, I'll use a custom enum.

2. HashMap instead of dict. Need to import from std::collections.

3. File reading: Python's `with open(path) as f` -> Rust's `std::fs::read_to_string` or `BufReader`. For line-by-line, BufReader with .lines() is idiomatic.

4. String handling: Python's strip() -> Rust's trim(). split("=", 1) -> splitn(2, '='). starts_with("#") same in both.

5. The None return for errors -- in Rust this maps to Result<HashMap, ConfigError> where we return Err variants.

6. Ownership: the config HashMap owns its String keys and values. No lifetime issues here since we're creating owned Strings from the file content.

Let me think about the error type. Two error cases: file not found and parse error. I'll make a simple enum.
</think>

```rust
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::fmt;

#[derive(Debug)]
enum ConfigError {
    FileNotFound(String),
    ParseError(String),
}

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ConfigError::FileNotFound(path) => {
                write!(f, "Config file not found: {}", path)
            }
            ConfigError::ParseError(msg) => {
                write!(f, "Parse error: {}", msg)
            }
        }
    }
}

fn read_config(path: &str) -> Result<HashMap<String, String>, ConfigError> {
    let file = File::open(path)
        .map_err(|_| ConfigError::FileNotFound(path.to_string()))?;

    let reader = BufReader::new(file);
    let mut config = HashMap::new();

    for line_result in reader.lines() {
        let line = line_result
            .map_err(|e| ConfigError::ParseError(e.to_string()))?;
        let trimmed = line.trim().to_string();

        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        let (key, value) = trimmed.split_once('=')
            .ok_or_else(|| {
                ConfigError::ParseError(
                    format!("Invalid line: {}", trimmed)
                )
            })?;

        config.insert(
            key.trim().to_string(),
            value.trim().to_string(),
        );
    }

    Ok(config)
}

fn main() {
    match read_config("app.conf") {
        Ok(cfg) => {
            for (k, v) in &cfg {
                println!("{} = {}", k, v);
            }
        }
        Err(e) => eprintln!("{}", e),
    }
}
```

Key differences:

- `try/except` with None returns -> `Result<T, E>` with custom error enum and `?` operator for propagation
- `dict` -> `HashMap<String, String>` with explicit key/value types
- `line.split("=", 1)` -> `split_once('=')` returning `Option<(&str, &str)>`
- `with open(path)` -> `File::open()` + `BufReader` (file is closed when dropped -- RAII)
- All strings are owned `String` values in the HashMap; `.to_string()` or `.trim().to_string()` converts `&str` slices to owned data''',
    ),
    (
        "code-translation/python-to-rust",
        r'''Translate this Python class with methods and operator overloading to Rust:

class Vec2:
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y

    def length(self):
        return (self.x ** 2 + self.y ** 2) ** 0.5

    def normalized(self):
        ln = self.length()
        if ln == 0:
            return Vec2(0, 0)
        return Vec2(self.x / ln, self.y / ln)

    def dot(self, other):
        return self.x * other.x + self.y * other.y

    def __add__(self, other):
        return Vec2(self.x + other.x, self.y + other.y)

    def __mul__(self, scalar):
        return Vec2(self.x * scalar, self.y * scalar)

    def __eq__(self, other):
        return abs(self.x - other.x) < 1e-9 and abs(self.y - other.y) < 1e-9

    def __repr__(self):
        return f"Vec2({self.x}, {self.y})"''',
        r'''```rust
use std::fmt;
use std::ops::{Add, Mul};

#[derive(Debug, Clone, Copy)]
struct Vec2 {
    x: f64,
    y: f64,
}

impl Vec2 {
    fn new(x: f64, y: f64) -> Self {
        Vec2 { x, y }
    }

    fn length(&self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }

    fn normalized(&self) -> Vec2 {
        let ln = self.length();
        if ln == 0.0 {
            return Vec2::new(0.0, 0.0);
        }
        Vec2::new(self.x / ln, self.y / ln)
    }

    fn dot(&self, other: &Vec2) -> f64 {
        self.x * other.x + self.y * other.y
    }
}

impl Add for Vec2 {
    type Output = Vec2;
    fn add(self, other: Vec2) -> Vec2 {
        Vec2::new(self.x + other.x, self.y + other.y)
    }
}

impl Mul<f64> for Vec2 {
    type Output = Vec2;
    fn mul(self, scalar: f64) -> Vec2 {
        Vec2::new(self.x * scalar, self.y * scalar)
    }
}

impl PartialEq for Vec2 {
    fn eq(&self, other: &Vec2) -> bool {
        (self.x - other.x).abs() < 1e-9
            && (self.y - other.y).abs() < 1e-9
    }
}

impl fmt::Display for Vec2 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Vec2({}, {})", self.x, self.y)
    }
}

fn main() {
    let a = Vec2::new(3.0, 4.0);
    let b = Vec2::new(1.0, 2.0);
    println!("a = {}", a);
    println!("length = {}", a.length());
    println!("a + b = {}", a + b);
    println!("a * 2 = {}", a * 2.0);
    println!("dot = {}", a.dot(&b));
    println!("normalized = {}", a.normalized());
}
```

Translation notes:

- Python `__init__` -> Rust `fn new()` convention (no constructor syntax in Rust)
- `__add__`, `__mul__` -> implement `std::ops::Add`, `std::ops::Mul` traits with associated `Output` type
- `__eq__` with epsilon -> `PartialEq` trait (not `Eq`, since float comparison is not exact)
- `__repr__` -> `fmt::Display` for user-facing output, `#[derive(Debug)]` for debug printing
- `#[derive(Clone, Copy)]` lets Vec2 be passed by value without moves -- small structs like this should be Copy
- `dot(&self, other: &Vec2)` takes a reference to avoid consuming the argument -- Rust's ownership system requires this choice''',
    ),
    (
        "code-translation/python-to-rust",
        r'''Convert this Python LRU cache implementation to Rust:

from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key):
        if key not in self.cache:
            return -1
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)''',
        r'''<think>
Python LRU cache to Rust. This is challenging because:

1. OrderedDict is a hash map that remembers insertion order and supports move_to_end and popitem. Rust's std HashMap doesn't preserve order.

2. Options in Rust:
   - Use a crate like `lru` (but that defeats the purpose of translation)
   - Implement with a HashMap + linked list (classic LRU implementation)
   - Use `indexmap::IndexMap` which is like OrderedDict but no move_to_end
   - Use `std::collections::LinkedList` + HashMap -- but LinkedList in Rust is painful due to ownership rules (no easy node references)

3. The most practical approach for a clean translation: use a Vec as a simple ordered container and a HashMap for O(1) lookup. This makes move_to_end O(n) but keeps the code readable. For production, you'd use the `lru` crate.

Actually, let me use a HashMap<K, V> combined with a VecDeque for ordering. Or better yet -- I'll use a HashMap and a Vec<K> where we track order. The get operation moves the key to the end of the Vec.

Wait, this is getting complex. The cleanest teaching translation is to use HashMap + VecDeque for the ordering, accepting O(n) for the "move to end" operation, since the Python version also doesn't guarantee better than O(n) for move_to_end (CPython's OrderedDict uses a doubly linked list internally for O(1), but that's an implementation detail).

Let me keep it simple and use HashMap + Vec.
</think>

```rust
use std::collections::HashMap;

struct LRUCache {
    capacity: usize,
    map: HashMap<i32, i32>,
    order: Vec<i32>,  // keys in access order (oldest first)
}

impl LRUCache {
    fn new(capacity: usize) -> Self {
        LRUCache {
            capacity,
            map: HashMap::with_capacity(capacity),
            order: Vec::with_capacity(capacity),
        }
    }

    fn touch(&mut self, key: i32) {
        // Move key to end (most recently used)
        if let Some(pos) = self.order.iter().position(|&k| k == key) {
            self.order.remove(pos);
        }
        self.order.push(key);
    }

    fn get(&mut self, key: i32) -> i32 {
        match self.map.get(&key) {
            Some(&val) => {
                self.touch(key);
                val
            }
            None => -1,
        }
    }

    fn put(&mut self, key: i32, value: i32) {
        if self.map.contains_key(&key) {
            self.touch(key);
        } else {
            if self.map.len() >= self.capacity {
                // Evict least recently used (front of order vec)
                let evicted = self.order.remove(0);
                self.map.remove(&evicted);
            }
            self.order.push(key);
        }
        self.map.insert(key, value);
    }
}

fn main() {
    let mut cache = LRUCache::new(2);
    cache.put(1, 10);
    cache.put(2, 20);
    println!("{}", cache.get(1));  // 10 (moves 1 to end)
    cache.put(3, 30);             // evicts key 2
    println!("{}", cache.get(2));  // -1 (evicted)
    println!("{}", cache.get(3));  // 30
}
```

Key differences:

- `OrderedDict` has no direct Rust stdlib equivalent. We simulate it with `HashMap` + `Vec` for ordering
- `self.cache[key]` -> `self.map.get(&key)` returns `Option`, not the value directly
- `move_to_end(key)` -> manual `position()` + `remove()` + `push()`. This is O(n) vs Python's O(1)
- `popitem(last=False)` -> `self.order.remove(0)` + `self.map.remove()`
- `get(&mut self)` takes `&mut self` because it modifies access order -- Rust forces you to declare mutation explicitly
- For production Rust, use the `lru` crate which implements O(1) operations with an unsafe linked list internally''',
    ),
    (
        "code-translation/python-to-rust",
        r'''Translate this Python iterator/generator pattern to Rust:

def fibonacci():
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b

def take(n, iterable):
    for i, item in enumerate(iterable):
        if i >= n:
            break
        yield item

def filter_even(iterable):
    for item in iterable:
        if item % 2 == 0:
            yield item

# Usage:
# list(take(10, filter_even(fibonacci())))
# -> [0, 2, 8, 34, 144, 610, 2584, 10946, 46368, 196418]''',
        r'''```rust
struct Fibonacci {
    a: u64,
    b: u64,
}

impl Fibonacci {
    fn new() -> Self {
        Fibonacci { a: 0, b: 1 }
    }
}

impl Iterator for Fibonacci {
    type Item = u64;

    fn next(&mut self) -> Option<u64> {
        let current = self.a;
        let new_b = self.a + self.b;
        self.a = self.b;
        self.b = new_b;
        Some(current)  // infinite iterator -- always returns Some
    }
}

fn main() {
    // Rust's Iterator trait has built-in .take() and .filter()
    // so we do not need custom implementations
    let result: Vec<u64> = Fibonacci::new()
        .filter(|x| x % 2 == 0)
        .take(10)
        .collect();

    println!("{:?}", result);
    // [0, 2, 8, 34, 144, 610, 2584, 10946, 46368, 196418]
}
```

Translation notes:

- Python `yield` generators -> Rust `Iterator` trait with a struct holding state. Rust has no built-in generator/yield syntax (it exists in nightly only)
- The generator's local variables `a, b` become struct fields that persist between `.next()` calls
- `take(n, iter)` and `filter_even(iter)` are unnecessary in Rust -- the `Iterator` trait provides `.take(n)` and `.filter(pred)` as built-in adapters
- Python's lazy generators compose with function calls: `take(10, filter_even(fibonacci()))`. Rust composes with method chaining: `Fibonacci::new().filter(...).take(10)`
- `.collect()` materializes the lazy iterator into a `Vec` -- equivalent to wrapping with `list()` in Python
- The infinite `while True: yield` pattern maps to always returning `Some(value)` from `next()`''',
    ),
    (
        "code-translation/python-to-rust",
        r'''Convert this Python multithreaded worker pool to Rust:

import threading
import queue
import time

def worker(task_queue, results, worker_id):
    while True:
        task = task_queue.get()
        if task is None:
            break
        result = task * task  # simulate work
        time.sleep(0.01)
        results.append((worker_id, task, result))
        task_queue.task_done()

def run_pool(tasks, num_workers=4):
    task_queue = queue.Queue()
    results = []
    threads = []

    for t in tasks:
        task_queue.put(t)

    for i in range(num_workers):
        t = threading.Thread(target=worker, args=(task_queue, results, i))
        t.start()
        threads.append(t)

    task_queue.join()

    for _ in range(num_workers):
        task_queue.put(None)
    for t in threads:
        t.join()

    return results''',
        r'''```rust
use std::sync::{Arc, Mutex, mpsc};
use std::thread;
use std::time::Duration;

fn run_pool(tasks: Vec<i64>, num_workers: usize) -> Vec<(usize, i64, i64)> {
    let (tx_task, rx_task) = mpsc::channel::<Option<i64>>();
    let rx_task = Arc::new(Mutex::new(rx_task));
    let (tx_result, rx_result) = mpsc::channel();

    let mut handles = Vec::new();

    for worker_id in 0..num_workers {
        let rx = Arc::clone(&rx_task);
        let tx = tx_result.clone();

        let handle = thread::spawn(move || {
            loop {
                let task = {
                    let receiver = rx.lock().unwrap();
                    receiver.recv().unwrap_or(None)
                };
                match task {
                    Some(value) => {
                        let result = value * value;
                        thread::sleep(Duration::from_millis(10));
                        tx.send((worker_id, value, result)).unwrap();
                    }
                    None => break,
                }
            }
        });
        handles.push(handle);
    }

    // Send all tasks
    for t in tasks {
        tx_task.send(Some(t)).unwrap();
    }
    // Send poison pills to stop workers
    for _ in 0..num_workers {
        tx_task.send(None).unwrap();
    }
    drop(tx_task);

    // Wait for all workers
    for h in handles {
        h.join().unwrap();
    }
    drop(tx_result);

    // Collect results
    let mut results = Vec::new();
    while let Ok(r) = rx_result.recv() {
        results.push(r);
    }
    results
}

fn main() {
    let tasks: Vec<i64> = (1..=20).collect();
    let results = run_pool(tasks, 4);
    for (wid, task, result) in &results {
        println!("worker {}: {} -> {}", wid, task, result);
    }
}
```

Key differences:

- `queue.Queue` (thread-safe) -> `mpsc::channel` wrapped in `Arc<Mutex<>>` so multiple workers can receive from one channel
- `results.append(...)` (shared list with GIL protection) -> a separate `mpsc::channel` for results since Rust has no GIL
- `threading.Thread(target=fn, args=(...))` -> `thread::spawn(move || { ... })` with `move` to transfer ownership of captured variables
- Python's None poison pill pattern works the same way: `send(None)` to signal shutdown
- `task_queue.join()` (wait for all tasks processed) -> explicit `join()` on thread handles after sending poison pills
- Rust forces explicit `Arc::clone` for shared ownership and `Mutex` for safe concurrent access -- Python hides this behind the GIL''',
    ),
]
