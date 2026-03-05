"""P1 Batch: C++23, WebAssembly, eBPF, Zig, modern systems programming."""

PAIRS = [
    (
        "C++23 and C++26 modern features",
        "What are the most impactful features in C++23 and the upcoming C++26 standard? Show practical code examples demonstrating std::expected, std::print, deducing this, and std::generator.",
        """## C++23/26: The Features That Change How You Write C++

### std::expected — Error Handling Without Exceptions

The biggest pain point in C++ error handling: exceptions are expensive (stack unwinding) and error codes lose type safety. `std::expected<T, E>` gives you Rust-style `Result<T, E>` in C++.

```cpp
#include <expected>
#include <string>
#include <fstream>
#include <print>

// Before C++23: exceptions or error codes, both painful
// Old way with exceptions:
//   double parse_config(const std::string& path) { throw std::runtime_error("..."); }
// Old way with error codes:
//   int parse_config(const std::string& path, double* out) { return -1; }

// C++23: clean, composable, zero-overhead error handling
enum class ConfigError {
    file_not_found,
    parse_error,
    value_out_of_range,
};

std::expected<double, ConfigError> parse_config(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        return std::unexpected(ConfigError::file_not_found);
    }

    double value;
    if (!(file >> value)) {
        return std::unexpected(ConfigError::parse_error);
    }

    if (value < 0.0 || value > 100.0) {
        return std::unexpected(ConfigError::value_out_of_range);
    }

    return value;  // Implicit conversion to expected<double, ConfigError>
}

// Monadic chaining (like Rust's .map() and .and_then())
void use_config() {
    auto result = parse_config("settings.conf")
        .transform([](double v) { return v * 2.0; })  // .map()
        .transform([](double v) { return static_cast<int>(v); });

    if (result) {
        std::println("Config value: {}", *result);
    } else {
        std::println("Error: {}", static_cast<int>(result.error()));
    }
}
```

### std::print — Finally, Type-Safe Formatted Output

```cpp
#include <print>
#include <vector>
#include <chrono>

void modern_printing() {
    // Before: std::cout << "Value: " << x << " at " << timestamp << std::endl;
    // Problem: no format control, type-unsafe with operator<<

    // C++23: Python-style f-strings with compile-time format checking
    int count = 42;
    double ratio = 3.14159;
    std::string name = "HiveAI";

    std::println("Model: {}, params: {}, ratio: {:.2f}", name, count, ratio);
    // Output: Model: HiveAI, params: 42, ratio: 3.14

    // Alignment and padding
    std::println("{:<20} {:>10} {:^10}", "Name", "Score", "Rank");
    std::println("{:<20} {:>10.3f} {:^10}", "Qwen3-14B", 0.853, 1);
    std::println("{:<20} {:>10.3f} {:^10}", "Baseline", 0.742, 2);

    // Chrono integration — no more strftime
    auto now = std::chrono::system_clock::now();
    std::println("Timestamp: {}", now);
}
```

### Deducing This — CRTP Without the Boilerplate

```cpp
#include <print>

// Before C++23: CRTP for static polymorphism was verbose and error-prone
// template <typename Derived>
// struct Base {
//     void interface() { static_cast<Derived*>(this)->implementation(); }
// };
// struct Concrete : Base<Concrete> { void implementation() { ... } };

// C++23: "deducing this" — the object parameter is explicit
struct Builder {
    std::string name_;
    int value_ = 0;

    // 'this' is deduced — works for both lvalue and rvalue
    // No more CRTP needed for fluent interfaces!
    auto&& set_name(this auto&& self, std::string name) {
        self.name_ = std::move(name);
        return std::forward<decltype(self)>(self);
    }

    auto&& set_value(this auto&& self, int v) {
        self.value_ = v;
        return std::forward<decltype(self)>(self);
    }

    void build(this auto&& self) {
        std::println("Building: {} = {}", self.name_, self.value_);
    }
};

// Usage: clean fluent API without CRTP
void use_builder() {
    Builder{}
        .set_name("learning_rate")
        .set_value(42)
        .build();

    // Also enables perfect forwarding of *this:
    // Builder b;
    // b.set_name("lr");              // lvalue: returns Builder&
    // Builder{}.set_name("lr");      // rvalue: returns Builder&&
}

// Deducing this also enables recursive lambdas (huge win):
void recursive_lambda_example() {
    auto fibonacci = [](this auto&& self, int n) -> int {
        if (n <= 1) return n;
        return self(n - 1) + self(n - 2);
    };
    std::println("fib(10) = {}", fibonacci(10));  // 55
}
```

### std::generator — Lazy Sequences (C++23 Coroutines Made Easy)

```cpp
#include <generator>
#include <print>
#include <ranges>

// Before: custom iterator classes (50+ lines of boilerplate)
// After: Python-style generators in C++

std::generator<int> fibonacci() {
    int a = 0, b = 1;
    while (true) {
        co_yield a;
        auto next = a + b;
        a = b;
        b = next;
    }
}

std::generator<std::string> read_lines(const std::string& filename) {
    std::ifstream file(filename);
    std::string line;
    while (std::getline(file, line)) {
        co_yield line;
    }
}

void use_generators() {
    // Take first 10 Fibonacci numbers
    for (auto n : fibonacci() | std::views::take(10)) {
        std::print("{} ", n);
    }
    // Output: 0 1 1 2 3 5 8 13 21 34

    // Filter and transform lines from a file
    for (auto& line : read_lines("data.txt")
            | std::views::filter([](auto& s) { return !s.empty(); })
            | std::views::take(100)) {
        std::println("Line: {}", line);
    }
}
```

### Why These Features Matter Together

C++23 closes the expressiveness gap with Rust and Python while keeping C++'s zero-overhead abstraction principle. `std::expected` gives Rust-style error handling, `std::print` gives Python-style formatting, deducing this eliminates CRTP boilerplate, and `std::generator` gives Python-style generators. The result: modern C++ that's both safe and ergonomic, without sacrificing performance.""",
    ),

    (
        "WebAssembly for high-performance web and edge computing",
        "Explain WebAssembly (WASM) — how it works, when to use it over JavaScript, and how to compile Rust/C++ to WASM. Show practical examples including a performance-critical module and WASI for server-side WASM.",
        """## WebAssembly: Near-Native Speed in the Browser and Beyond

### What WASM Actually Is

WebAssembly is a binary instruction format — a portable compilation target. Think of it as a virtual CPU instruction set designed for safe, sandboxed execution. Unlike JavaScript, which is parsed and JIT-compiled, WASM is pre-compiled to a compact binary that the runtime can execute almost immediately.

Key properties that make WASM important:
- **Near-native speed**: typically 1-2× slower than native, vs JavaScript at 5-50×
- **Sandboxed**: runs in a memory-safe sandbox, can't access the host system without explicit imports
- **Portable**: same .wasm binary runs in browsers, Node.js, edge runtimes (Cloudflare Workers), and standalone runtimes (Wasmtime, Wasmer)

### When WASM Beats JavaScript

| Use Case | JS Performance | WASM Performance | Winner |
|----------|---------------|-----------------|--------|
| DOM manipulation | Fast (native API) | Slow (must cross JS bridge) | JS |
| String processing | Good (JIT-optimized) | Similar | Tie |
| Image/video processing | Slow | 5-10× faster | WASM |
| Cryptography | Slow | 10-20× faster | WASM |
| Scientific computation | Slow | 5-15× faster | WASM |
| Game physics/rendering | Variable | 3-8× faster | WASM |

**Rule of thumb**: use WASM for CPU-bound computation, keep JS for DOM and I/O.

### Rust to WASM: Image Processing Example

```rust
// lib.rs — Compile with: wasm-pack build --target web
use wasm_bindgen::prelude::*;

/// Grayscale conversion: 5-10× faster than JavaScript canvas API
///
/// Why WASM wins here: this is a tight loop over millions of pixels.
/// JavaScript's overhead per-iteration (bounds checks, type coercion,
/// GC pressure from Uint8Array views) adds up. WASM compiles to
/// a simple loop with direct memory access.
#[wasm_bindgen]
pub fn grayscale(pixels: &mut [u8]) {
    // pixels is RGBA: [r, g, b, a, r, g, b, a, ...]
    for chunk in pixels.chunks_exact_mut(4) {
        // ITU-R BT.709 luminance formula
        let gray = (0.2126 * chunk[0] as f64
                  + 0.7152 * chunk[1] as f64
                  + 0.0722 * chunk[2] as f64) as u8;
        chunk[0] = gray;
        chunk[1] = gray;
        chunk[2] = gray;
        // chunk[3] (alpha) unchanged
    }
}

/// Gaussian blur: O(n*k) per pixel, where k is kernel size
/// For a 4K image with 5×5 kernel: 8M pixels × 25 operations = 200M ops
/// JS: ~2000ms, WASM: ~200ms
#[wasm_bindgen]
pub fn gaussian_blur(pixels: &mut [u8], width: u32, height: u32, radius: u32) {
    let w = width as usize;
    let h = height as usize;
    let r = radius as i32;
    let mut output = pixels.to_vec();

    for y in 0..h {
        for x in 0..w {
            let mut r_sum: f64 = 0.0;
            let mut g_sum: f64 = 0.0;
            let mut b_sum: f64 = 0.0;
            let mut weight_sum: f64 = 0.0;

            for dy in -r..=r {
                for dx in -r..=r {
                    let nx = (x as i32 + dx).clamp(0, w as i32 - 1) as usize;
                    let ny = (y as i32 + dy).clamp(0, h as i32 - 1) as usize;
                    let idx = (ny * w + nx) * 4;

                    let dist_sq = (dx * dx + dy * dy) as f64;
                    let sigma = radius as f64 / 2.0;
                    let weight = (-dist_sq / (2.0 * sigma * sigma)).exp();

                    r_sum += pixels[idx] as f64 * weight;
                    g_sum += pixels[idx + 1] as f64 * weight;
                    b_sum += pixels[idx + 2] as f64 * weight;
                    weight_sum += weight;
                }
            }

            let out_idx = (y * w + x) * 4;
            output[out_idx] = (r_sum / weight_sum) as u8;
            output[out_idx + 1] = (g_sum / weight_sum) as u8;
            output[out_idx + 2] = (b_sum / weight_sum) as u8;
        }
    }

    pixels.copy_from_slice(&output);
}
```

### Using WASM from JavaScript

```javascript
// index.js — Using the compiled WASM module
import init, { grayscale, gaussian_blur } from './pkg/image_processor.js';

async function processImage(imageUrl) {
    await init();  // Load and instantiate the WASM module

    const img = await loadImage(imageUrl);
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0);

    const imageData = ctx.getImageData(0, 0, img.width, img.height);

    // Process pixels in WASM — 5-10× faster than doing this in JS
    console.time('wasm-grayscale');
    grayscale(imageData.data);  // Modifies pixels in-place via shared memory
    console.timeEnd('wasm-grayscale');

    ctx.putImageData(imageData, 0, 0);
    return canvas;
}
```

### WASI: Server-Side WASM

WASI (WebAssembly System Interface) extends WASM beyond the browser. It provides a capability-based API for filesystem, networking, and environment access.

```rust
// WASI example: a portable CLI tool that runs anywhere
// Compile: cargo build --target wasm32-wasi
// Run: wasmtime target/wasm32-wasi/release/tool.wasm -- input.txt

use std::env;
use std::fs;
use std::io::{self, BufRead};

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: tool <filename>");
        std::process::exit(1);
    }

    let file = fs::File::open(&args[1])?;
    let reader = io::BufReader::new(file);

    let mut word_count = 0;
    let mut line_count = 0;

    for line in reader.lines() {
        let line = line?;
        line_count += 1;
        word_count += line.split_whitespace().count();
    }

    println!("Lines: {}, Words: {}", line_count, word_count);
    Ok(())
}
// This same .wasm binary runs on: Linux, macOS, Windows, Docker,
// Cloudflare Workers, Fastly Compute, Fermyon Spin, and any WASI runtime.
```

### When to Choose WASM

Use WASM when you need: computation speed in the browser, portable sandboxed execution, or a universal plugin format. Don't use it for: DOM manipulation (use JS), simple CRUD apps (overhead not worth it), or when native code is an option (native is still faster).""",
    ),

    (
        "eBPF for observability and performance monitoring",
        "Explain eBPF — what it is, why it's revolutionizing Linux observability, and how to write eBPF programs for tracing, networking, and security monitoring. Show practical examples with bpftrace and Python BCC.",
        """## eBPF: Programmable Kernel Without Kernel Modules

### Why eBPF Matters

Traditionally, if you wanted to add custom monitoring to the Linux kernel, you had two options: write a kernel module (dangerous — a bug crashes the entire system) or use static tracepoints (limited — only the predefined ones). eBPF is a third option: **safe, dynamic, programmable kernel instrumentation**.

eBPF programs run in a sandboxed virtual machine inside the kernel. The kernel verifier checks every program before loading to guarantee: no infinite loops, no out-of-bounds memory access, no crashes. This means you can instrument ANY kernel function at runtime without rebooting.

### What eBPF Can Do

```
User Space                    Kernel Space
┌─────────────┐              ┌─────────────────────────┐
│ Your app    │              │ eBPF Programs:          │
│             │◄─── maps ───►│  - Trace syscalls       │
│ bpftrace    │              │  - Filter packets       │
│ BCC/Python  │              │  - Profile CPU usage    │
│ Cilium      │              │  - Monitor file I/O     │
│ Falco       │              │  - Enforce security     │
└─────────────┘              └─────────────────────────┘
```

### bpftrace: One-Liners for Kernel Tracing

```bash
# Who is doing disk I/O right now? (like iotop but better)
bpftrace -e 'tracepoint:block:block_rq_issue {
    printf("%-8d %-16s %s %d bytes\\n", pid, comm, args->rwbs, args->bytes);
}'

# Latency histogram of read() syscalls (in microseconds)
bpftrace -e 'tracepoint:syscalls:sys_enter_read { @start[tid] = nsecs; }
tracepoint:syscalls:sys_exit_read /@start[tid]/ {
    @us = hist((nsecs - @start[tid]) / 1000);
    delete(@start[tid]);
}'

# Trace which files a process opens (replace PID)
bpftrace -e 'tracepoint:syscalls:sys_enter_openat /pid == 12345/ {
    printf("%s\\n", str(args->filename));
}'

# TCP connection latency (time from SYN to ESTABLISHED)
bpftrace -e 'kprobe:tcp_v4_connect { @start[tid] = nsecs; }
kretprobe:tcp_v4_connect /@start[tid]/ {
    @tcp_connect_ms = hist((nsecs - @start[tid]) / 1000000);
    delete(@start[tid]);
}'
```

### Python BCC: Production-Grade eBPF Programs

```python
#!/usr/bin/env python3
\"\"\"
Trace slow HTTP responses using eBPF + uprobes.

This attaches to a running web server (no restart needed!)
and traces every HTTP response that takes longer than a threshold.

Why eBPF instead of application-level tracing?
1. Zero code changes to the application
2. Works on ANY web server (nginx, Apache, your Python app)
3. Kernel-level precision (nanosecond timestamps)
4. Near-zero overhead (<1% CPU) even under high load
\"\"\"
from bcc import BPF

# eBPF C program that runs in the kernel
bpf_program = r\"\"\"
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

struct event_t {
    u32 pid;
    u64 latency_ns;
    char comm[16];
};

BPF_HASH(start_times, u32);  // pid -> timestamp
BPF_PERF_OUTPUT(events);

// Triggered when a socket write begins (sending HTTP response)
int trace_write_entry(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 ts = bpf_ktime_get_ns();
    start_times.update(&pid, &ts);
    return 0;
}

// Triggered when socket write completes
int trace_write_return(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 *start = start_times.lookup(&pid);
    if (!start) return 0;

    u64 latency = bpf_ktime_get_ns() - *start;
    start_times.delete(&pid);

    // Only report if latency > 10ms (filter in kernel = less overhead)
    if (latency > 10000000) {
        struct event_t event = {};
        event.pid = pid;
        event.latency_ns = latency;
        bpf_get_current_comm(&event.comm, sizeof(event.comm));
        events.perf_submit(ctx, &event, sizeof(event));
    }
    return 0;
}
\"\"\"

def main():
    b = BPF(text=bpf_program)

    # Attach to kernel socket write functions
    b.attach_kprobe(event="sock_sendmsg", fn_name="trace_write_entry")
    b.attach_kretprobe(event="sock_sendmsg", fn_name="trace_write_return")

    print("Tracing slow socket writes (>10ms)... Ctrl+C to stop")
    print(f"{'PID':<8} {'COMM':<16} {'LATENCY (ms)':>12}")

    def print_event(cpu, data, size):
        event = b["events"].event(data)
        latency_ms = event.latency_ns / 1_000_000
        print(f"{event.pid:<8} {event.comm.decode():<16} {latency_ms:>12.2f}")

    b["events"].open_perf_buffer(print_event)

    try:
        while True:
            b.perf_buffer_poll()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
```

### eBPF for Security: Runtime Enforcement

```python
\"\"\"
Block unauthorized file access using eBPF LSM hooks.

This is how tools like Falco and Tetragon work: instead of
scanning logs after the fact, eBPF programs intercept security-
relevant events IN REAL TIME and can block them before they complete.
\"\"\"
from bcc import BPF

security_program = r\"\"\"
#include <linux/lsm_hooks.h>

// Block any process from reading /etc/shadow except root
int block_shadow_read(struct pt_regs *ctx) {
    char filename[64];
    bpf_probe_read_user_str(filename, sizeof(filename), (void *)PT_REGS_PARM2(ctx));

    char target[] = "/etc/shadow";
    // Compare filenames
    for (int i = 0; i < sizeof(target); i++) {
        if (filename[i] != target[i]) return 0;  // Not our target
        if (target[i] == 0) break;
    }

    // Check if caller is root
    u32 uid = bpf_get_current_uid_gid() & 0xFFFFFFFF;
    if (uid != 0) {
        // Log the attempt
        bpf_trace_printk("BLOCKED: uid=%d tried to read /etc/shadow\\n", uid);
        return -1;  // Deny access
    }
    return 0;  // Allow
}
\"\"\"
```

### The eBPF Ecosystem

| Tool | Purpose | Use Case |
|------|---------|----------|
| **bpftrace** | One-liner tracing | Quick debugging, performance investigation |
| **BCC** | Python-scriptable eBPF | Custom monitoring tools, production tracing |
| **Cilium** | eBPF networking | Kubernetes networking, load balancing, firewalling |
| **Falco** | eBPF security | Runtime threat detection, compliance |
| **Tetragon** | eBPF security | Process-level security policies |
| **Pixie** | eBPF observability | Auto-instrumented K8s monitoring |

The key insight: eBPF turns Linux itself into a programmable platform. Instead of running separate monitoring agents (Prometheus exporters, Datadog agents), you program the kernel to emit exactly the metrics you need with near-zero overhead.""",
    ),

    (
        "Zig programming language for systems programming",
        "Explain the Zig programming language — why it exists, what problems it solves over C and C++, and when to choose it. Show practical code examples demonstrating its key features: comptime, error handling, and C interop.",
        """## Zig: The Modern C Alternative

### Why Zig Exists

C is 50 years old. It has no generics, no error handling beyond errno, no memory safety, and undefined behavior lurks everywhere. C++ tried to fix these problems but became enormously complex (2000+ page standard). Rust took a different path with ownership/borrowing but has a steep learning curve.

Zig takes a third approach: **keep C's simplicity, fix the safety issues, add just enough modern features**. The core philosophy: no hidden control flow, no hidden memory allocations, no undefined behavior.

### Key Feature 1: comptime — Compile-Time Execution

```zig
const std = @import("std");

// In C, you'd use macros or code generation for this.
// In C++, you'd use template metaprogramming.
// In Zig, you just write normal code and run it at compile time.

fn Matrix(comptime T: type, comptime rows: usize, comptime cols: usize) type {
    // This function RUNS AT COMPILE TIME and returns a TYPE.
    // No templates, no macros, no code generation — just Zig.
    return struct {
        data: [rows][cols]T,

        const Self = @This();

        pub fn zero() Self {
            return Self{ .data = .{.{0} ** cols} ** rows };
        }

        pub fn multiply(self: Self, other: Matrix(T, cols, cols)) Matrix(T, rows, cols) {
            var result = Matrix(T, rows, cols).zero();
            for (0..rows) |i| {
                for (0..cols) |j| {
                    for (0..cols) |k| {
                        result.data[i][j] += self.data[i][k] * other.data[k][j];
                    }
                }
            }
            return result;
        }

        // comptime-generated debug printing
        pub fn print(self: Self) void {
            for (self.data) |row| {
                for (row) |val| {
                    std.debug.print("{d:>6.2} ", .{val});
                }
                std.debug.print("\n", .{});
            }
        }
    };
}

pub fn main() void {
    // Types are first-class values — this is just a function call
    const Mat3x3 = Matrix(f64, 3, 3);
    var m = Mat3x3.zero();
    m.data[0][0] = 1.0;
    m.data[1][1] = 1.0;
    m.data[2][2] = 1.0;
    m.print();

    // Compile-time validation: Matrix(f64, 3, 2) * Matrix(f64, 3, 3)
    // would be a COMPILE ERROR because cols(3x2) != rows(3x3).
    // No runtime cost for this check.
}
```

### Key Feature 2: Error Handling — Explicit and Composable

```zig
const std = @import("std");

// Zig errors are values, not exceptions. They compose with the ! operator.
// Unlike Go's if err != nil boilerplate, Zig has `try` and `catch` as
// single-character operators that eliminate the noise.

const FileError = error{
    NotFound,
    PermissionDenied,
    TooLarge,
};

fn readConfig(allocator: std.mem.Allocator, path: []const u8) FileError![]u8 {
    // The ! means this function returns either []u8 or a FileError.
    const file = std.fs.cwd().openFile(path, .{}) catch |err| {
        return switch (err) {
            error.FileNotFound => FileError.NotFound,
            error.AccessDenied => FileError.PermissionDenied,
            else => FileError.NotFound,
        };
    };
    defer file.close();  // RAII-like: runs when scope exits (success or error)

    const stat = try file.stat();  // `try` = return error if it fails
    if (stat.size > 1024 * 1024) {
        return FileError.TooLarge;
    }

    return file.readToEndAlloc(allocator, 1024 * 1024) catch FileError.NotFound;
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();  // Detect memory leaks in debug mode
    const allocator = gpa.allocator();

    const config = readConfig(allocator, "config.txt") catch |err| {
        std.debug.print("Failed: {}\n", .{err});
        return;
    };
    defer allocator.free(config);

    std.debug.print("Config: {s}\n", .{config});
}
```

### Key Feature 3: Seamless C Interop

```zig
// Zig can import C headers directly — no bindings, no FFI declarations.
// This is Zig's killer feature for adoption: use ANY C library immediately.

const c = @cImport({
    @cInclude("sqlite3.h");
});
const std = @import("std");

pub fn main() !void {
    var db: ?*c.sqlite3 = null;

    // Call C functions directly — Zig handles the ABI
    const rc = c.sqlite3_open(":memory:", &db);
    if (rc != c.SQLITE_OK) {
        std.debug.print("Failed to open DB: {s}\n", .{c.sqlite3_errmsg(db)});
        return;
    }
    defer _ = c.sqlite3_close(db);

    // Execute SQL
    var err_msg: [*c]u8 = null;
    const sql = "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT);";
    const exec_rc = c.sqlite3_exec(db, sql, null, null, &err_msg);
    if (exec_rc != c.SQLITE_OK) {
        std.debug.print("SQL error: {s}\n", .{err_msg});
        c.sqlite3_free(err_msg);
    }

    std.debug.print("SQLite version: {s}\n", .{c.sqlite3_libversion()});
}

// Compile: zig build-exe main.zig -lsqlite3 -lc
// Zig's build system handles linking C libraries automatically.
```

### When to Choose Zig

| Choose Zig When | Choose Rust When | Choose C When |
|----------------|-----------------|---------------|
| Replacing C in existing projects | New systems from scratch | Legacy codebases |
| Need C library interop | Need borrow checker guarantees | Extreme portability (embedded) |
| Want simpler language than C++ | Building concurrent systems | Kernel/driver development |
| Cross-compilation is important | Large team, enforce safety | Standards compliance required |

Zig's sweet spot: projects that would otherwise be C or C++, especially when you need C library interop. Its cross-compilation support is best-in-class — `zig cc` can cross-compile C/C++ code to any target, which alone makes it valuable as a build tool even if you don't write Zig code.""",
    ),
]
