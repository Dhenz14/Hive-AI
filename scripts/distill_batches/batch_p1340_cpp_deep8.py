"""C++ deep reasoning pairs batch 8: debugging, performance, and real-world."""
PAIRS = [
    ("cpp_deep/undefined_behavior_traps", r'''What are the most common forms of undefined behavior in C++, and how do I write defensive code to avoid signed overflow, null dereference, and buffer overflow?''', r'''<think>
The user wants practical guidance on the three most dangerous UB categories in C++.
Signed overflow is UB per the standard — the compiler can optimize assuming it never happens.
This means loops like `for (int i = 0; i < n; i++)` can be optimized away if overflow occurs.
Null dereference is UB even if you never read the memory — the compiler can hoist code above null checks.
Buffer overflow is the classic — writing past array bounds corrupts stack/heap, enables exploits.
For signed overflow: use unsigned arithmetic, or check before operating. C++20 has std::midpoint.
For null deref: use references where possible, std::optional, and assert/contract-style checks.
For buffer overflow: use std::span (C++20), std::array, and range-based for loops.
I should show a before/after pattern for each category with concrete compilable code.
The key insight is that UB is not just "crashes" — it's the compiler silently removing your safety checks.
Compilers exploit UB for optimization: if signed overflow is UB, the compiler assumes i+1 > i always.
I'll demonstrate each with a dangerous version and a safe modern C++ version.
GSL's narrow_cast and gsl::not_null are also worth mentioning as defensive tools.
I should compile with -fsanitize=undefined to catch these at runtime during development.
</think>

Here are the three most dangerous forms of undefined behavior in C++ and how to defend against each:

```cpp
#include <cstdint>
#include <cassert>
#include <limits>
#include <optional>
#include <span>
#include <stdexcept>
#include <iostream>
#include <numeric> // std::midpoint (C++20)

// ============================================================
// 1. SIGNED INTEGER OVERFLOW — UB per [expr]/4
// ============================================================

// DANGEROUS: compiler may optimize away the overflow check entirely
bool dangerous_add_check(int a, int b) {
    int sum = a + b;          // UB if overflow — too late to check!
    return sum >= a;          // compiler assumes true (no UB => no overflow)
}

// SAFE: check BEFORE the operation
[[nodiscard]] bool safe_add(int a, int b, int& result) {
    if (b > 0 && a > std::numeric_limits<int>::max() - b) return false;
    if (b < 0 && a < std::numeric_limits<int>::min() - b) return false;
    result = a + b;
    return true;
}

// SAFE (C++20): use std::midpoint to avoid overflow in averaging
int safe_midpoint(int lo, int hi) {
    return std::midpoint(lo, hi); // no overflow, correct for negatives
}

// SAFE: use unsigned when you don't need negative values
uint32_t safe_unsigned_add(uint32_t a, uint32_t b) {
    // unsigned overflow is well-defined (wraps modulo 2^N)
    return a + b;
}

// ============================================================
// 2. NULL POINTER DEREFERENCE — UB per [dcl.ref]/5
// ============================================================

struct Config {
    int timeout = 30;
    std::string host = "localhost";
};

// DANGEROUS: raw pointer, no check
void dangerous_use(Config* cfg) {
    std::cout << cfg->timeout;  // UB if cfg is null
}

// SAFE: use references to make null impossible at the type level
void safe_use_ref(const Config& cfg) {
    std::cout << cfg.timeout;   // cannot be null
}

// SAFE: use std::optional for "maybe no value"
void safe_use_optional(std::optional<Config> cfg) {
    if (cfg) {
        std::cout << cfg->timeout;
    } else {
        std::cout << "no config, using defaults\n";
    }
}

// SAFE: assert + [[assume]] for internal pointers you own
void safe_use_assert(Config* cfg) {
    assert(cfg != nullptr && "cfg must not be null");
    // In debug: aborts. In release: optimized out, but documents intent.
    std::cout << cfg->timeout;
}

// ============================================================
// 3. BUFFER OVERFLOW — UB per [expr.add]/4
// ============================================================

// DANGEROUS: raw array + index, no bounds check
void dangerous_fill(int* arr, size_t len) {
    for (size_t i = 0; i <= len; ++i) {  // off-by-one: writes arr[len]
        arr[i] = static_cast<int>(i);
    }
}

// SAFE (C++20): std::span carries size with the pointer
void safe_fill(std::span<int> buf) {
    for (size_t i = 0; i < buf.size(); ++i) {
        buf[i] = static_cast<int>(i);
    }
}

// SAFE: range-based for — impossible to go out of bounds
void safe_fill_range(std::span<int> buf) {
    int val = 0;
    for (auto& elem : buf) {
        elem = val++;
    }
}

// SAFE: std::array with .at() for bounds-checked access
void safe_checked_access() {
    std::array<int, 5> arr = {10, 20, 30, 40, 50};
    try {
        int x = arr.at(5); // throws std::out_of_range, not UB
        (void)x;
    } catch (const std::out_of_range& e) {
        std::cerr << "Caught: " << e.what() << "\n";
    }
}

int main() {
    // 1. Signed overflow — safe add
    int result = 0;
    if (safe_add(std::numeric_limits<int>::max(), 1, result)) {
        std::cout << "sum = " << result << "\n";
    } else {
        std::cout << "overflow detected, no UB\n";
    }

    // 2. Null deref — safe reference
    Config cfg;
    safe_use_ref(cfg);
    std::cout << "\n";

    // 3. Buffer overflow — safe span
    int data[5];
    safe_fill(data); // span deduces size from C-array
    for (int v : data) std::cout << v << " ";
    std::cout << "\n";

    safe_checked_access();
}
```

Compile with sanitizers during development to catch any UB you missed:
```bash
g++ -std=c++20 -O2 -fsanitize=undefined,address -fno-omit-frame-pointer -o ub_demo ub_demo.cpp
```

Key principles: check **before** the operation (not after), prefer references over pointers, use `std::span` and `std::array` over raw buffers, and always build with `-fsanitize=undefined` during development.'''),

    ("cpp_deep/address_sanitizer_asan", r'''How does AddressSanitizer (ASan) work in C++? Show me how to enable it, what bugs it catches, and a practical example where it detects a use-after-free.''', r'''<think>
ASan is a compile-time instrumentation + runtime library that detects memory errors.
It works by replacing malloc/free with a custom allocator that uses shadow memory.
Every 8 bytes of application memory maps to 1 byte of shadow memory tracking accessibility.
On free, ASan quarantines the memory (marks shadow bytes as poisoned) instead of returning to OS.
Any access to poisoned memory triggers an immediate report with full stack trace.
It catches: heap-buffer-overflow, stack-buffer-overflow, use-after-free, use-after-return,
use-after-scope, double-free, memory leaks (with detect_leaks=1).
Overhead: ~2x slowdown, ~3x memory. Not suitable for production but excellent for CI and testing.
Compile with -fsanitize=address -fno-omit-frame-pointer for good stack traces.
I should show a concrete use-after-free that compiles clean but ASan catches at runtime.
On MSVC you use /fsanitize=address (supported since VS 2019 16.9).
Important: ASan and TSan cannot be combined — they use incompatible shadow memory layouts.
Also show how to read the ASan report output — it gives alloc and free stack traces.
Let me write a small program with a deliberate use-after-free to demonstrate.
I'll also mention ASAN_OPTIONS for controlling behavior like halt_on_error.
</think>

AddressSanitizer (ASan) instruments your code at compile time and catches memory errors at runtime with full stack traces:

```cpp
// asan_demo.cpp — Demonstrates ASan catching use-after-free
#include <iostream>
#include <vector>
#include <string>
#include <memory>

// ============================================================
// Bug 1: Use-after-free (ASan catches this immediately)
// ============================================================
void use_after_free_demo() {
    int* p = new int[10];
    for (int i = 0; i < 10; ++i) p[i] = i * 42;

    delete[] p;

    // BUG: accessing freed memory — may "work" without ASan,
    // but ASan will report it with alloc+free stack traces
    std::cout << "freed value: " << p[3] << "\n";  // ASan: heap-use-after-free
}

// ============================================================
// Bug 2: Heap buffer overflow
// ============================================================
void heap_overflow_demo() {
    int* arr = new int[5];
    arr[5] = 999;   // ASan: heap-buffer-overflow (1 past end)
    delete[] arr;
}

// ============================================================
// Bug 3: Stack buffer overflow
// ============================================================
void stack_overflow_demo() {
    int buf[4] = {1, 2, 3, 4};
    // ASan inserts redzones around stack variables
    volatile int oob = buf[4]; // ASan: stack-buffer-overflow
    (void)oob;
}

// ============================================================
// Bug 4: Use-after-scope (local variable escapes its scope)
// ============================================================
int* use_after_scope_demo() {
    int* ptr = nullptr;
    {
        int local = 42;
        ptr = &local;
    }  // local destroyed here
    // ASan with -fsanitize-address-use-after-scope catches this
    return ptr;  // dangling
}

// ============================================================
// SAFE version: how to write the code correctly
// ============================================================
void safe_version() {
    // Use smart pointers — no manual delete, no use-after-free
    auto arr = std::make_unique<int[]>(10);
    for (int i = 0; i < 10; ++i) arr[i] = i * 42;
    std::cout << "safe value: " << arr[3] << "\n";
    // arr freed automatically at scope exit, pointer is gone

    // Use vector — no buffer overflow possible with .at()
    std::vector<int> vec = {1, 2, 3, 4, 5};
    try {
        vec.at(5) = 999; // throws, no UB
    } catch (const std::out_of_range& e) {
        std::cerr << "caught: " << e.what() << "\n";
    }

    // Use std::optional or return by value — no dangling pointers
    auto make_value = []() -> int { return 42; }; // return by value, safe
    std::cout << "no dangling: " << make_value() << "\n";
}

int main() {
    std::cout << "=== Safe version ===\n";
    safe_version();

    // Uncomment ONE of these to see ASan in action:
    // use_after_free_demo();
    // heap_overflow_demo();
    // stack_overflow_demo();
    // int* dangling = use_after_scope_demo();
    // std::cout << *dangling << "\n";

    std::cout << "Done.\n";
}
```

**Build commands:**
```bash
# GCC / Clang (Linux, macOS, WSL)
g++ -std=c++20 -O1 -g -fsanitize=address -fno-omit-frame-pointer \
    -fsanitize-address-use-after-scope -o asan_demo asan_demo.cpp

# MSVC (Visual Studio 2019 16.9+)
cl /std:c++20 /EHsc /Zi /fsanitize=address asan_demo.cpp

# Run with options:
ASAN_OPTIONS=detect_leaks=1:halt_on_error=0:print_stats=1 ./asan_demo
```

**What ASan catches:**
| Bug class | Detection |
|---|---|
| Heap buffer overflow | Yes |
| Stack buffer overflow | Yes |
| Use-after-free | Yes |
| Use-after-return | Yes (with flag) |
| Use-after-scope | Yes (with flag) |
| Double-free | Yes |
| Memory leaks | Yes (LeakSanitizer) |
| Uninitialized reads | No (use MSan) |
| Data races | No (use TSan) |

ASan adds roughly 2x runtime overhead and 3x memory overhead. It cannot be combined with TSan (they use conflicting shadow memory). Use it in CI builds and during all testing.'''),

    ("cpp_deep/thread_sanitizer_tsan", r'''How do I use ThreadSanitizer (TSan) to detect data races in C++? Show a practical example of a race condition that TSan catches.''', r'''<think>
TSan detects data races: when two threads access the same memory concurrently and at least one is a write.
It uses compile-time instrumentation to intercept every memory access and synchronization operation.
It maintains a "happens-before" graph to determine if accesses are properly synchronized.
TSan is supported by GCC and Clang on Linux/macOS. MSVC does not support TSan.
Overhead: ~5-15x slowdown, ~5-10x memory. More expensive than ASan.
Cannot combine TSan with ASan or MSan — use separate builds.
I should show a classic race condition: two threads incrementing a shared counter without a mutex.
Then show the fix with std::mutex or std::atomic, and how TSan confirms the fix.
TSan output shows the two conflicting accesses with stack traces plus thread creation point.
Key flags: -fsanitize=thread, compile ALL files with it (including libraries if possible).
Let me show a complete example with the race and the fix side by side.
Also mention TSAN_OPTIONS for suppression files and other tuning.
Important: TSan requires all code to be instrumented — uninstrumented libraries cause false positives.
The false positive rate is very low for fully instrumented code — TSan is precise, not heuristic.
</think>

ThreadSanitizer detects data races by tracking happens-before relationships between all memory accesses across threads:

```cpp
// tsan_demo.cpp — Data race detection with ThreadSanitizer
#include <iostream>
#include <thread>
#include <vector>
#include <mutex>
#include <atomic>
#include <numeric>

// ============================================================
// BUGGY: Data race — two threads write to shared counter
// ============================================================
namespace buggy {

int counter = 0;  // shared, unprotected

void increment(int n) {
    for (int i = 0; i < n; ++i) {
        ++counter;  // TSan: data race on 'counter'
        // Read-modify-write is not atomic — threads can interleave
    }
}

void run() {
    constexpr int N = 100'000;
    std::thread t1(increment, N);
    std::thread t2(increment, N);
    t1.join();
    t2.join();
    // Expected 200000, but result is unpredictable due to race
    std::cout << "[BUGGY] counter = " << counter
              << " (expected " << 2 * N << ")\n";
}

}  // namespace buggy

// ============================================================
// FIX 1: std::mutex — correct but slower
// ============================================================
namespace fix_mutex {

int counter = 0;
std::mutex mtx;

void increment(int n) {
    for (int i = 0; i < n; ++i) {
        std::lock_guard<std::mutex> lock(mtx);
        ++counter;  // TSan: no race — mutex establishes happens-before
    }
}

void run() {
    constexpr int N = 100'000;
    std::thread t1(increment, N);
    std::thread t2(increment, N);
    t1.join();
    t2.join();
    std::cout << "[MUTEX] counter = " << counter << "\n";
}

}  // namespace fix_mutex

// ============================================================
// FIX 2: std::atomic — lock-free, correct, fast
// ============================================================
namespace fix_atomic {

std::atomic<int> counter{0};

void increment(int n) {
    for (int i = 0; i < n; ++i) {
        counter.fetch_add(1, std::memory_order_relaxed);
        // relaxed is fine here — we only need atomicity, not ordering
    }
}

void run() {
    constexpr int N = 100'000;
    std::thread t1(increment, N);
    std::thread t2(increment, N);
    t1.join();
    t2.join();
    std::cout << "[ATOMIC] counter = " << counter.load() << "\n";
}

}  // namespace fix_atomic

// ============================================================
// FIX 3: Thread-local accumulation + merge (best throughput)
// ============================================================
namespace fix_local {

void run() {
    constexpr int N = 100'000;
    constexpr int NUM_THREADS = 4;
    std::vector<int> local_counts(NUM_THREADS, 0);

    auto worker = [&](int thread_id) {
        for (int i = 0; i < N; ++i) {
            ++local_counts[thread_id]; // no sharing between threads
        }
    };

    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t)
        threads.emplace_back(worker, t);
    for (auto& th : threads)
        th.join();

    int total = std::accumulate(local_counts.begin(), local_counts.end(), 0);
    std::cout << "[LOCAL] counter = " << total << "\n";
}

}  // namespace fix_local

int main() {
    // Uncomment buggy::run() to trigger TSan report
    // buggy::run();

    fix_mutex::run();
    fix_atomic::run();
    fix_local::run();
}
```

**Build and run:**
```bash
# Compile with TSan (GCC or Clang — MSVC does not support TSan)
g++ -std=c++20 -O1 -g -fsanitize=thread -o tsan_demo tsan_demo.cpp -pthread

# Run (uncomment buggy::run() to see the report)
TSAN_OPTIONS=halt_on_error=0:second_deadlock_stack=1 ./tsan_demo
```

**TSan report for the race looks like:**
```
WARNING: ThreadSanitizer: data race
  Write of size 4 at 0x... by thread T2:
    #0 buggy::increment(int) tsan_demo.cpp:14
  Previous write of size 4 at 0x... by thread T1:
    #0 buggy::increment(int) tsan_demo.cpp:14
  Thread T1 (tid=...) created at:
    #0 pthread_create
    #1 buggy::run() tsan_demo.cpp:19
```

TSan has very low false positive rate when all code is instrumented. Overhead is ~5-15x slower and ~5-10x more memory than normal execution. It cannot be combined with ASan — use separate CI builds for each.'''),

    ("cpp_deep/ubsan_runtime_detection", r'''How do I use UndefinedBehaviorSanitizer (UBSan) to catch UB at runtime in C++? Show examples of what it catches and how to configure it.''', r'''<think>
UBSan is the lightest-weight sanitizer — minimal overhead (~20%) so it can run in production.
It instruments code to check for UB at runtime: signed overflow, shift errors, null deref, etc.
Unlike ASan/TSan, UBSan can be combined with ASan for comprehensive checking.
Key sub-checks: signed-integer-overflow, shift, null, alignment, bool, enum, vptr, float-cast-overflow.
-fsanitize=undefined enables all of them.
-fno-sanitize-recover=undefined makes it abort on first UB (default is to continue with a warning).
I should show concrete examples: signed overflow, shift past width, misaligned access, invalid enum.
UBSan can also catch implicit integer truncation with -fsanitize=implicit-conversion (Clang only).
Show the compilation flags and how to read the diagnostic output.
For production, there's -fsanitize-minimal-runtime which gives smaller binary but less info.
The trap mode (-fsanitize-trap=undefined) replaces reports with __builtin_trap — no runtime library needed.
This is perfect for embedded or production where you want to crash but not link the sanitizer runtime.
Let me demonstrate multiple UB categories in one file.
</think>

UBSan is the lightest sanitizer (~20% overhead) and can run alongside ASan. It catches many classes of undefined behavior at runtime:

```cpp
// ubsan_demo.cpp — UndefinedBehaviorSanitizer demonstrations
#include <cstdint>
#include <climits>
#include <iostream>
#include <cstring>

// ============================================================
// 1. Signed integer overflow
// ============================================================
int signed_overflow_demo() {
    int x = INT_MAX;
    int y = x + 1;  // UBSan: signed integer overflow: 2147483647 + 1
    return y;
}

// ============================================================
// 2. Shift past bit-width
// ============================================================
int bad_shift_demo() {
    int val = 1;
    int shifted = val << 32;  // UBSan: shift exponent 32 >= width of type 'int' (32)
    return shifted;
}

// ============================================================
// 3. Signed shift into sign bit (UB before C++20)
// ============================================================
int sign_shift_demo() {
    int val = 1;
    int result = val << 31;  // UBSan: left shift of 1 by 31 overflows
    return result;           // (well-defined in C++20, UB in C++17)
}

// ============================================================
// 4. Division by zero
// ============================================================
int div_zero_demo(int x) {
    return x / 0;  // UBSan: division by zero
}

// ============================================================
// 5. Null pointer dereference
// ============================================================
int null_deref_demo() {
    int* p = nullptr;
    return *p;  // UBSan: load of null pointer of type 'int'
}

// ============================================================
// 6. Misaligned pointer access
// ============================================================
int misaligned_demo() {
    char buf[16] = {};
    // Create a misaligned int pointer
    int* p = reinterpret_cast<int*>(buf + 1);
    return *p;  // UBSan: load of misaligned address for type 'int' (alignment 4)
}

// ============================================================
// 7. Invalid enum value
// ============================================================
enum Color : uint8_t { Red = 0, Green = 1, Blue = 2 };

Color invalid_enum_demo() {
    uint8_t raw = 42;
    Color c;
    std::memcpy(&c, &raw, sizeof(c));  // Load-bearing: value 42 not in enum range
    return c;  // UBSan (with -fsanitize=enum): load of value 42 not valid for type 'Color'
}

// ============================================================
// 8. Float-to-int overflow
// ============================================================
int float_cast_demo() {
    double huge = 1e18;
    int truncated = static_cast<int>(huge);  // UBSan: value 1e+18 outside range of 'int'
    return truncated;
}

// ============================================================
// SAFE versions showing correct modern C++ patterns
// ============================================================
#include <optional>
#include <bit>       // C++20: std::has_single_bit, etc.
#include <limits>

namespace safe {

// Safe addition with overflow check
std::optional<int> add(int a, int b) {
    if (b > 0 && a > std::numeric_limits<int>::max() - b) return std::nullopt;
    if (b < 0 && a < std::numeric_limits<int>::min() - b) return std::nullopt;
    return a + b;
}

// Safe shift — validate width
uint32_t safe_shift(uint32_t val, unsigned amount) {
    if (amount >= 32) return 0;     // defined behavior
    return val << amount;           // unsigned shift, no sign issues
}

// Safe division
std::optional<int> safe_div(int a, int b) {
    if (b == 0) return std::nullopt;
    if (a == INT_MIN && b == -1) return std::nullopt; // overflow
    return a / b;
}

// Safe float-to-int
std::optional<int> safe_float_to_int(double d) {
    if (d < static_cast<double>(std::numeric_limits<int>::min()) ||
        d > static_cast<double>(std::numeric_limits<int>::max())) {
        return std::nullopt;
    }
    return static_cast<int>(d);
}

}  // namespace safe

int main() {
    // Run safe versions
    auto sum = safe::add(INT_MAX, 1);
    std::cout << "safe add overflow: " << (sum ? std::to_string(*sum) : "none") << "\n";

    std::cout << "safe shift(1, 32): " << safe::safe_shift(1, 32) << "\n";

    auto div = safe::safe_div(10, 0);
    std::cout << "safe div by 0: " << (div ? std::to_string(*div) : "none") << "\n";

    auto flt = safe::safe_float_to_int(1e18);
    std::cout << "safe float cast: " << (flt ? std::to_string(*flt) : "none") << "\n";

    // Uncomment one to trigger UBSan:
    // signed_overflow_demo();
    // bad_shift_demo();
    // div_zero_demo(42);
    // null_deref_demo();
}
```

**Build commands:**
```bash
# Full UBSan — reports but continues (default)
g++ -std=c++20 -O1 -g -fsanitize=undefined -o ubsan_demo ubsan_demo.cpp

# UBSan + ASan together (recommended for CI)
g++ -std=c++20 -O1 -g -fsanitize=undefined,address -fno-omit-frame-pointer \
    -o ubsan_demo ubsan_demo.cpp

# Abort on first UB (strict mode for CI gates)
g++ -std=c++20 -O1 -g -fsanitize=undefined -fno-sanitize-recover=undefined \
    -o ubsan_demo ubsan_demo.cpp

# Trap mode — no runtime lib, just __builtin_trap (for embedded/production)
g++ -std=c++20 -O1 -g -fsanitize=undefined -fsanitize-trap=undefined \
    -o ubsan_demo ubsan_demo.cpp

# Clang extra: implicit integer truncation detection
clang++ -std=c++20 -O1 -g -fsanitize=undefined,implicit-conversion \
    -o ubsan_demo ubsan_demo.cpp
```

UBSan is cheap enough (~20% overhead) to run in pre-release builds. Combine it with ASan in CI for maximum coverage. Use trap mode (`-fsanitize-trap=undefined`) for production or embedded where you want crashes without the sanitizer runtime library.'''),

    ("cpp_deep/valgrind_vs_sanitizers", r'''When should I use Valgrind versus compiler sanitizers (ASan, TSan, MSan, UBSan) in C++? What are the tradeoffs?''', r'''<think>
This is about choosing the right dynamic analysis tool for different situations.
Valgrind (specifically Memcheck) uses binary instrumentation — no recompilation needed.
Sanitizers use compile-time instrumentation — must recompile with flags.
Valgrind is ~20-50x slower, sanitizers are 2-15x slower. Huge difference for CI.
Valgrind catches: uninitialized reads (MSan equivalent), memory leaks, use-after-free, buffer overflows.
ASan catches similar memory bugs to Valgrind but much faster and with better stack traces.
MSan (MemorySanitizer) catches uninitialized reads — Valgrind's unique strength.
TSan catches data races — no Valgrind equivalent (Helgrind exists but is much worse).
UBSan catches undefined behavior — no Valgrind equivalent.
Key advantage of Valgrind: works on unmodified binaries, including third-party libraries.
Key advantage of sanitizers: much faster, better integration with CI, combinable (ASan+UBSan).
MSan is Clang-only and requires ALL libraries instrumented — very hard to use in practice.
Valgrind is Linux-only. ASan works on Linux, macOS, Windows (MSVC). TSan: Linux, macOS only.
I'll present this as a decision matrix with clear recommendations.
For most projects: ASan+UBSan in CI, TSan in separate CI job, Valgrind for occasional deep checks.
Valgrind's Callgrind and Cachegrind are profiling tools with no sanitizer equivalent.
</think>

Here is a practical comparison with a decision matrix and example usage:

```cpp
// analysis_example.cpp — A program with multiple bug types to demonstrate tool coverage
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>
#include <memory>

// Bug 1: Uninitialized read (Valgrind + MSan catch; ASan does NOT)
int uninitialized_read() {
    int x;  // not initialized
    if (x > 0) return 1;  // Conditional jump depends on uninitialized value
    return 0;
}

// Bug 2: Heap use-after-free (Valgrind + ASan both catch)
void use_after_free() {
    int* p = new int(42);
    delete p;
    std::cout << *p << "\n";  // Both Valgrind and ASan detect this
}

// Bug 3: Memory leak (Valgrind + ASan/LeakSanitizer catch)
void memory_leak() {
    int* p = new int[1000];
    p[0] = 42;
    // forgot delete[] — leaked 4000 bytes
}

// Bug 4: Data race (TSan catches; Valgrind's Helgrind catches but 100x slower)
void data_race() {
    int shared = 0;
    std::thread t1([&] { for (int i = 0; i < 10000; ++i) ++shared; });
    std::thread t2([&] { for (int i = 0; i < 10000; ++i) ++shared; });
    t1.join(); t2.join();
}

// Bug 5: Signed overflow (UBSan catches; neither Valgrind nor ASan does)
int signed_overflow() {
    int x = 2'147'483'647;
    return x + 1;  // UB — only UBSan detects
}

int main() {
    // Each function demonstrates a different tool's strength
    // uninitialized_read();  // Valgrind / MSan
    // use_after_free();      // Valgrind / ASan
    // memory_leak();         // Valgrind / LeakSanitizer
    // data_race();           // TSan / Helgrind
    // signed_overflow();     // UBSan only
    std::cout << "Choose which bug to demonstrate.\n";
}
```

**Build commands for each tool:**
```bash
# --- Compiler Sanitizers (fast, compile-time instrumentation) ---

# ASan + UBSan (recommended default CI job)
g++ -std=c++20 -O1 -g -fsanitize=address,undefined \
    -fno-omit-frame-pointer -o test_asan analysis_example.cpp -pthread

# TSan (separate CI job — cannot combine with ASan)
g++ -std=c++20 -O1 -g -fsanitize=thread \
    -o test_tsan analysis_example.cpp -pthread

# MSan (Clang only — ALL deps must be instrumented)
clang++ -std=c++20 -O1 -g -fsanitize=memory \
    -fno-omit-frame-pointer -o test_msan analysis_example.cpp -pthread

# --- Valgrind (slow, binary instrumentation, no recompile needed) ---

# Compile with debug info only (no sanitizer flags)
g++ -std=c++20 -O0 -g -o test_valgrind analysis_example.cpp -pthread

# Memcheck (memory errors + leaks)
valgrind --leak-check=full --track-origins=yes ./test_valgrind

# Helgrind (data race detection)
valgrind --tool=helgrind ./test_valgrind

# Callgrind (CPU profiling — no sanitizer equivalent)
valgrind --tool=callgrind ./test_valgrind
```

**Decision matrix:**

| Bug Class | ASan | TSan | MSan | UBSan | Valgrind |
|---|---|---|---|---|---|
| Heap buffer overflow | YES | - | - | - | YES |
| Stack buffer overflow | YES | - | - | - | NO |
| Use-after-free | YES | - | - | - | YES |
| Memory leaks | YES* | - | - | - | YES |
| Uninitialized reads | NO | - | YES | - | YES |
| Data races | - | YES | - | - | Helgrind |
| Signed overflow | - | - | - | YES | NO |
| Null deref | YES | - | - | YES | YES |
| Misaligned access | - | - | - | YES | NO |
| **Overhead** | 2x | 5-15x | 3x | 1.2x | 20-50x |
| **Recompile needed** | YES | YES | YES | YES | NO |
| **Platform** | Lin/Mac/Win | Lin/Mac | Lin(Clang) | Lin/Mac/Win | Linux |

*ASan detects leaks via the integrated LeakSanitizer on Linux.

**Recommended CI setup:** Run ASan+UBSan as the primary check (fast, broad coverage). Add TSan as a separate job. Use Valgrind periodically for uninitialized read detection and when you cannot recompile third-party code.'''),

    ("cpp_deep/debugging_template_errors", r'''How do I debug complex C++ template error messages? The compiler output is pages long and unreadable. What techniques help?''', r'''<think>
Template error messages are notoriously bad in C++. The key techniques are:
1. Read bottom-up — the root cause is usually at the bottom of the error cascade.
2. Use concepts (C++20) to get much clearer errors.
3. static_assert with descriptive messages for early failure.
4. Use type aliases to reduce noise in error messages.
5. Compile with Clang first — its template errors are generally better than GCC's.
6. Use tools like templight or -ftemplate-backtrace-limit to control output.
7. The "archetype" technique: create a minimal type that satisfies the concept.
8. Build up templates incrementally, testing each layer.
I should show a before/after: a template without concepts (horrible error) vs with concepts (clear error).
Also show the static_assert pattern for catching bad instantiations early.
The most practical advice: use C++20 concepts — they transform template errors from pages to one line.
Let me write concrete examples showing the difference.
I'll also mention -fconcepts-diagnostics-depth for nested concepts.
</think>

Template errors become manageable with C++20 concepts, `static_assert`, and a few reading strategies:

```cpp
// template_debug.cpp — Techniques for readable template errors
#include <concepts>
#include <type_traits>
#include <vector>
#include <string>
#include <iostream>
#include <algorithm>
#include <numeric>

// ============================================================
// BEFORE: C++17 style — horrible error messages
// ============================================================
namespace old_style {

template <typename T>
T sum_elements(const std::vector<T>& vec) {
    T total = T{};
    for (const auto& elem : vec) {
        total = total + elem;  // If T doesn't support +, you get 50 lines of errors
    }                          // pointing deep into vector internals
    return total;
}

// Trying: sum_elements(std::vector<std::mutex>{})
// Error: pages of template instantiation backtrace through vector,
// allocator, move operations... the actual error is buried.

}  // namespace old_style

// ============================================================
// AFTER: C++20 concepts — clear, one-line errors
// ============================================================

// Define what we need from T
template <typename T>
concept Summable = requires(T a, T b) {
    { a + b } -> std::convertible_to<T>;   // must support +
    { T{} };                                // must be default-constructible
};

template <Summable T>
T sum_elements(const std::vector<T>& vec) {
    T total = T{};
    for (const auto& elem : vec) {
        total = total + elem;
    }
    return total;
}
// Now: sum_elements(std::vector<std::mutex>{})
// Error: "constraints not satisfied: std::mutex does not satisfy Summable"
// ONE clear line. Done.

// ============================================================
// Technique 1: Layered concepts for precise diagnostics
// ============================================================
template <typename T>
concept DefaultConstructible = std::is_default_constructible_v<T>;

template <typename T>
concept HasPlus = requires(T a, T b) { { a + b } -> std::convertible_to<T>; };

template <typename T>
concept HasLessThan = requires(T a, T b) { { a < b } -> std::convertible_to<bool>; };

template <typename T>
concept Sortable = HasLessThan<T> && std::movable<T>;

// Each failed concept tells you EXACTLY which requirement is missing

template <Sortable T>
void sort_and_print(std::vector<T>& vec) {
    std::sort(vec.begin(), vec.end());
    for (const auto& v : vec) std::cout << v << " ";
    std::cout << "\n";
}

// ============================================================
// Technique 2: static_assert for early failure with custom message
// ============================================================
template <typename T>
class SafeContainer {
    static_assert(!std::is_reference_v<T>,
        "SafeContainer<T&> is not allowed — use std::reference_wrapper");
    static_assert(!std::is_void_v<T>,
        "SafeContainer<void> is meaningless");
    static_assert(std::is_destructible_v<T>,
        "SafeContainer requires T to be destructible");

    std::vector<T> data_;
public:
    void add(const T& val) { data_.push_back(val); }
    [[nodiscard]] size_t size() const { return data_.size(); }
};

// SafeContainer<int&> c;  // "SafeContainer<T&> is not allowed"
// Much better than a cryptic vector<int&> error deep in <memory>

// ============================================================
// Technique 3: Type alias debugging — print what T actually is
// ============================================================
template <typename T>
struct TypeDebug;  // intentionally undefined

// Usage: TypeDebug<decltype(expr)>{};
// Compiler error shows: "implicit instantiation of undefined template TypeDebug<int>"
// This reveals what T actually is at that point in template instantiation

// ============================================================
// Technique 4: Archetype testing — verify your concept is correct
// ============================================================

// Minimal type that should satisfy Summable
struct SummableArchetype {
    SummableArchetype() = default;
    friend SummableArchetype operator+(SummableArchetype, SummableArchetype) {
        return {};
    }
};
static_assert(Summable<SummableArchetype>, "archetype must satisfy Summable");
static_assert(Summable<int>, "int must satisfy Summable");
static_assert(Summable<double>, "double must satisfy Summable");
static_assert(Summable<std::string>, "string must satisfy Summable");

int main() {
    // Works: int is Summable
    std::vector<int> nums = {1, 2, 3, 4, 5};
    std::cout << "sum = " << sum_elements(nums) << "\n";

    // Works: string is Summable (operator+ concatenates)
    std::vector<std::string> words = {"hello", " ", "world"};
    std::cout << "concat = " << sum_elements(words) << "\n";

    // Works: int is Sortable
    std::vector<int> unsorted = {5, 3, 1, 4, 2};
    sort_and_print(unsorted);

    // SafeContainer with valid type
    SafeContainer<int> c;
    c.add(42);
    std::cout << "container size: " << c.size() << "\n";
}
```

**Compiler flags for better template diagnostics:**
```bash
# Clang — generally best template errors
clang++ -std=c++20 -fconcepts-diagnostics-depth=3 -ftemplate-backtrace-limit=5 \
    -o debug template_debug.cpp

# GCC — use -fconcepts-diagnostics-depth
g++ -std=c++20 -fconcepts-diagnostics-depth=3 -ftemplate-backtrace-limit=10 \
    -o debug template_debug.cpp

# MSVC — /diagnostics:caret for column info
cl /std:c++20 /diagnostics:caret template_debug.cpp
```

**Reading strategy for old-style errors:** Start from the bottom of the error output (the root cause), look for "required from here" to find your code vs library code, and search for the first line mentioning your source file name.'''),

    ("cpp_deep/cache_friendly_soa_vs_aos", r'''What is the difference between Struct of Arrays (SoA) and Array of Structs (AoS) in C++? Show how SoA improves cache performance for data-oriented design.''', r'''<think>
This is about data-oriented design and cache performance.
AoS: struct { float x, y, z, w; } particles[N]; — each particle is contiguous.
SoA: struct { float x[N], y[N], z[N], w[N]; } — each field is contiguous.
When processing all x values (e.g., updating positions), AoS wastes cache lines loading y, z, w.
SoA means sequential x values are adjacent in memory → full cache line utilization.
L1 cache line is typically 64 bytes = 16 floats. In AoS with 4 fields, only 1/4 of each cache line is useful.
SoA is 4x better cache utilization for single-field iteration.
SIMD also benefits: SoA data is already in the right layout for SSE/AVX (4/8 floats contiguous).
The tradeoff: AoS is better when you always access all fields of one entity together.
I should show a benchmark-style comparison with a particle system.
Modern C++ can make SoA ergonomic with helper functions or zip views (C++23 std::views::zip).
Real-world use: game engines (Unity DOTS, EnTT), scientific computing, databases (columnar).
Let me show both layouts, a processing loop for each, and explain the cache behavior.
</think>

SoA vs AoS determines whether your hot loops get full cache line utilization or waste 75% of every line:

```cpp
// soa_vs_aos.cpp — Cache-friendly data layout comparison
#include <array>
#include <cmath>
#include <chrono>
#include <iostream>
#include <vector>
#include <random>
#include <numeric>

constexpr size_t NUM_PARTICLES = 1'000'000;
constexpr int ITERATIONS = 100;

// ============================================================
// AoS: Array of Structs — intuitive, but cache-unfriendly for
//       operations that only touch a few fields
// ============================================================
struct ParticleAoS {
    float x, y, z;         // position
    float vx, vy, vz;      // velocity
    float mass;             // mass
    float pad;              // padding to 32 bytes (likely anyway due to alignment)
};

// When updating positions: reads x, y, z, vx, vy, vz but also loads mass + pad
// into the cache line. For 1M particles, that's ~6MB of wasted memory bandwidth.
void update_positions_aos(std::vector<ParticleAoS>& particles, float dt) {
    for (auto& p : particles) {
        p.x += p.vx * dt;  // Cache line: [x y z vx vy vz mass pad] — 32 bytes
        p.y += p.vy * dt;  // Next particle is 32 bytes away
        p.z += p.vz * dt;  // Only 24/32 bytes are useful = 75% utilization
    }
}

// ============================================================
// SoA: Struct of Arrays — cache-optimal for column operations
// ============================================================
struct ParticlesSoA {
    std::vector<float> x, y, z;
    std::vector<float> vx, vy, vz;
    std::vector<float> mass;

    explicit ParticlesSoA(size_t n)
        : x(n), y(n), z(n), vx(n), vy(n), vz(n), mass(n) {}

    [[nodiscard]] size_t size() const { return x.size(); }
};

// When updating x: reads x[0..N] and vx[0..N] sequentially
// Cache line: [x[i] x[i+1] ... x[i+15]] — 16 consecutive floats
// 100% of every cache line is useful data for this loop
void update_positions_soa(ParticlesSoA& p, float dt) {
    const size_t n = p.size();
    for (size_t i = 0; i < n; ++i) p.x[i] += p.vx[i] * dt;
    for (size_t i = 0; i < n; ++i) p.y[i] += p.vy[i] * dt;
    for (size_t i = 0; i < n; ++i) p.z[i] += p.vz[i] * dt;
    // Each loop is a sequential scan — prefetcher loves this
    // Also: compiler can auto-vectorize with SSE/AVX (4-8 floats per instruction)
}

// ============================================================
// Hybrid AoSoA: Array of Struct of Arrays — best of both worlds
// ============================================================
constexpr size_t CHUNK_SIZE = 16;  // fits in 1-2 cache lines

struct ParticleChunk {
    // Each chunk: 16 particles with each field contiguous within the chunk
    std::array<float, CHUNK_SIZE> x, y, z;
    std::array<float, CHUNK_SIZE> vx, vy, vz;
    std::array<float, CHUNK_SIZE> mass;
};

void update_positions_aosoa(std::vector<ParticleChunk>& chunks, float dt) {
    for (auto& chunk : chunks) {
        // Inner loop on chunk — fits entirely in L1 cache
        for (size_t i = 0; i < CHUNK_SIZE; ++i) chunk.x[i] += chunk.vx[i] * dt;
        for (size_t i = 0; i < CHUNK_SIZE; ++i) chunk.y[i] += chunk.vy[i] * dt;
        for (size_t i = 0; i < CHUNK_SIZE; ++i) chunk.z[i] += chunk.vz[i] * dt;
    }
}

// ============================================================
// Benchmark
// ============================================================
template <typename Fn>
double benchmark(const char* label, Fn fn) {
    // warmup
    fn();
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < ITERATIONS; ++i) fn();
    auto end = std::chrono::high_resolution_clock::now();
    double ms = std::chrono::duration<double, std::milli>(end - start).count();
    std::cout << label << ": " << ms << " ms (" << ITERATIONS << " iterations)\n";
    return ms;
}

int main() {
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(-1.0f, 1.0f);
    float dt = 0.016f;

    // Initialize AoS
    std::vector<ParticleAoS> aos(NUM_PARTICLES);
    for (auto& p : aos) {
        p.x = dist(rng); p.y = dist(rng); p.z = dist(rng);
        p.vx = dist(rng); p.vy = dist(rng); p.vz = dist(rng);
        p.mass = std::abs(dist(rng)) + 0.1f;
    }

    // Initialize SoA
    ParticlesSoA soa(NUM_PARTICLES);
    for (size_t i = 0; i < NUM_PARTICLES; ++i) {
        soa.x[i] = aos[i].x; soa.y[i] = aos[i].y; soa.z[i] = aos[i].z;
        soa.vx[i] = aos[i].vx; soa.vy[i] = aos[i].vy; soa.vz[i] = aos[i].vz;
        soa.mass[i] = aos[i].mass;
    }

    // Initialize AoSoA
    size_t num_chunks = (NUM_PARTICLES + CHUNK_SIZE - 1) / CHUNK_SIZE;
    std::vector<ParticleChunk> aosoa(num_chunks);
    for (size_t i = 0; i < NUM_PARTICLES; ++i) {
        size_t ci = i / CHUNK_SIZE, si = i % CHUNK_SIZE;
        aosoa[ci].x[si] = aos[i].x; aosoa[ci].y[si] = aos[i].y;
        aosoa[ci].z[si] = aos[i].z;
        aosoa[ci].vx[si] = aos[i].vx; aosoa[ci].vy[si] = aos[i].vy;
        aosoa[ci].vz[si] = aos[i].vz;
    }

    benchmark("AoS  ", [&] { update_positions_aos(aos, dt); });
    benchmark("SoA  ", [&] { update_positions_soa(soa, dt); });
    benchmark("AoSoA", [&] { update_positions_aosoa(aosoa, dt); });
}
```

**Build and run:**
```bash
g++ -std=c++20 -O3 -march=native -o soa_demo soa_vs_aos.cpp
./soa_demo
# Typical result: SoA is 2-4x faster than AoS for this workload
```

**Why SoA wins:** A 64-byte cache line holds 16 consecutive floats. In AoS with 8 fields per struct, the position update loop uses only 3/8 of each cache line. In SoA, every byte in the cache line is a float you need. The prefetcher also works perfectly because access is purely sequential.'''),

    ("cpp_deep/simd_intrinsics", r'''How do I use SIMD intrinsics in C++ for parallel data processing? Show a practical example with SSE/AVX for vectorized computation.''', r'''<think>
SIMD (Single Instruction, Multiple Data) processes 4/8/16 floats in one instruction.
SSE: 128-bit registers, 4 floats or 2 doubles at a time. Available on all x86-64.
AVX: 256-bit registers, 8 floats or 4 doubles. Available since Sandy Bridge (2011).
AVX-512: 512-bit, 16 floats. Available on some Intel CPUs (Skylake-X, Ice Lake).
Include <immintrin.h> for all intrinsics.
Key types: __m128 (SSE float), __m256 (AVX float), __m128d (SSE double).
Key operations: _mm256_load_ps, _mm256_add_ps, _mm256_mul_ps, _mm256_store_ps.
Data must be aligned: use alignas(32) for AVX, alignas(16) for SSE.
I should show a real example: vector addition or dot product using AVX.
Also show the scalar version for comparison and mention auto-vectorization.
Important: check CPU support at runtime with __builtin_cpu_supports or CPUID.
For portability, wrap intrinsics in a SIMD library abstraction or use std::experimental::simd.
The key pattern: process N elements per iteration, handle the tail (remainder) with scalar code.
Let me do a float array multiply-add (FMA): result[i] = a[i] * b[i] + c[i].
</think>

SIMD intrinsics let you process 4-16 floats per instruction. Here is a practical example with SSE and AVX:

```cpp
// simd_demo.cpp — SIMD intrinsics for parallel float computation
#include <immintrin.h>  // SSE, AVX, AVX2, FMA intrinsics
#include <iostream>
#include <vector>
#include <chrono>
#include <cstdlib>
#include <cmath>
#include <cassert>

// ============================================================
// Scalar baseline: a[i] * b[i] + c[i]
// ============================================================
void fma_scalar(const float* a, const float* b, const float* c,
                float* result, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        result[i] = a[i] * b[i] + c[i];
    }
}

// ============================================================
// SSE version: 4 floats per iteration (128-bit)
// ============================================================
void fma_sse(const float* a, const float* b, const float* c,
             float* result, size_t n) {
    size_t i = 0;
    // Process 4 floats at a time
    for (; i + 4 <= n; i += 4) {
        __m128 va = _mm_load_ps(a + i);    // load 4 aligned floats
        __m128 vb = _mm_load_ps(b + i);
        __m128 vc = _mm_load_ps(c + i);
        __m128 vmul = _mm_mul_ps(va, vb);  // 4 multiplies in 1 instruction
        __m128 vres = _mm_add_ps(vmul, vc); // 4 adds in 1 instruction
        _mm_store_ps(result + i, vres);     // store 4 results
    }
    // Scalar tail for remaining elements
    for (; i < n; ++i) {
        result[i] = a[i] * b[i] + c[i];
    }
}

// ============================================================
// AVX version: 8 floats per iteration (256-bit)
// ============================================================
void fma_avx(const float* a, const float* b, const float* c,
             float* result, size_t n) {
    size_t i = 0;
    for (; i + 8 <= n; i += 8) {
        __m256 va = _mm256_load_ps(a + i);    // load 8 aligned floats
        __m256 vb = _mm256_load_ps(b + i);
        __m256 vc = _mm256_load_ps(c + i);
        __m256 vmul = _mm256_mul_ps(va, vb);  // 8 multiplies
        __m256 vres = _mm256_add_ps(vmul, vc); // 8 adds
        _mm256_store_ps(result + i, vres);
    }
    // Scalar tail
    for (; i < n; ++i) {
        result[i] = a[i] * b[i] + c[i];
    }
}

// ============================================================
// AVX + FMA3: fused multiply-add in a single instruction
// ============================================================
#ifdef __FMA__
void fma_avx_fma3(const float* a, const float* b, const float* c,
                   float* result, size_t n) {
    size_t i = 0;
    for (; i + 8 <= n; i += 8) {
        __m256 va = _mm256_load_ps(a + i);
        __m256 vb = _mm256_load_ps(b + i);
        __m256 vc = _mm256_load_ps(c + i);
        // Single instruction: va * vb + vc (better precision + throughput)
        __m256 vres = _mm256_fmadd_ps(va, vb, vc);
        _mm256_store_ps(result + i, vres);
    }
    for (; i < n; ++i) {
        result[i] = std::fma(a[i], b[i], c[i]);
    }
}
#endif

// ============================================================
// Aligned memory allocation helper
// ============================================================
float* alloc_aligned(size_t count, size_t alignment = 32) {
    void* ptr = nullptr;
#ifdef _WIN32
    ptr = _aligned_malloc(count * sizeof(float), alignment);
#else
    if (posix_memalign(&ptr, alignment, count * sizeof(float)) != 0)
        ptr = nullptr;
#endif
    assert(ptr && "aligned allocation failed");
    return static_cast<float*>(ptr);
}

void free_aligned(float* ptr) {
#ifdef _WIN32
    _aligned_free(ptr);
#else
    free(ptr);
#endif
}

// ============================================================
// Benchmark
// ============================================================
template <typename Fn>
double bench(const char* label, Fn fn, int iters = 200) {
    fn(); // warmup
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iters; ++i) fn();
    auto end = std::chrono::high_resolution_clock::now();
    double ms = std::chrono::duration<double, std::milli>(end - start).count();
    std::cout << label << ": " << (ms / iters) << " ms/iter\n";
    return ms;
}

int main() {
    constexpr size_t N = 4'000'000; // 16 MB per array

    // Allocate aligned memory (required for _mm_load_ps / _mm256_load_ps)
    float* a = alloc_aligned(N);
    float* b = alloc_aligned(N);
    float* c = alloc_aligned(N);
    float* result = alloc_aligned(N);

    // Initialize with test data
    for (size_t i = 0; i < N; ++i) {
        a[i] = static_cast<float>(i) * 0.001f;
        b[i] = static_cast<float>(N - i) * 0.001f;
        c[i] = 1.0f;
    }

    bench("Scalar", [&] { fma_scalar(a, b, c, result, N); });
    bench("SSE   ", [&] { fma_sse(a, b, c, result, N); });
    bench("AVX   ", [&] { fma_avx(a, b, c, result, N); });
#ifdef __FMA__
    bench("AVX+FMA", [&] { fma_avx_fma3(a, b, c, result, N); });
#endif

    free_aligned(a);
    free_aligned(b);
    free_aligned(c);
    free_aligned(result);
}
```

**Build:**
```bash
# SSE only (baseline — all x86-64 CPUs)
g++ -std=c++20 -O3 -msse4.2 -o simd_demo simd_demo.cpp

# AVX (Sandy Bridge+)
g++ -std=c++20 -O3 -mavx -o simd_demo simd_demo.cpp

# AVX + FMA (Haswell+, most modern CPUs)
g++ -std=c++20 -O3 -mavx -mfma -o simd_demo simd_demo.cpp

# Use native CPU features
g++ -std=c++20 -O3 -march=native -o simd_demo simd_demo.cpp
```

Key rules: align data to 16 bytes (SSE) or 32 bytes (AVX), process in chunks matching the register width, and always handle the scalar tail for non-aligned sizes. For portable SIMD, consider the `std::experimental::simd` library from `<experimental/simd>` (GCC) or libraries like Highway and xsimd.'''),

    ("cpp_deep/branch_prediction_hints", r'''How do branch prediction hints work in C++? When should I use [[likely]]/[[unlikely]] and __builtin_expect?''', r'''<think>
Branch prediction is a CPU mechanism that speculatively executes one path of an if/switch.
Modern CPUs predict correctly ~95%+ of the time using hardware branch predictors.
But for cold branches (error handling, rare conditions), the predictor has no history to learn from.
C++20 added [[likely]] and [[unlikely]] attributes. GCC/Clang have __builtin_expect since forever.
These hints affect code layout: the likely path is placed in the hot code path (fall-through),
the unlikely path is moved to a separate section, improving instruction cache locality.
They do NOT change the hardware predictor — they affect the compiler's code generation decisions.
The main benefit is: better instruction cache utilization, not faster individual branches.
I should show both the C++20 attributes and the __builtin_expect macro.
Important: profile first. Adding hints without profiling can make things worse.
Over-hinting is worse than no hints — it can confuse the optimizer.
Best use cases: error handling paths, assertion-like checks, rare allocations.
Let me write a concrete example with benchmarking to show the difference.
Also mention PGO as the better alternative — it automatically adds the right hints.
</think>

Branch hints affect code layout (not the hardware predictor), improving instruction cache locality for hot paths:

```cpp
// branch_hints.cpp — [[likely]], [[unlikely]], and __builtin_expect
#include <iostream>
#include <vector>
#include <random>
#include <chrono>
#include <cstdlib>
#include <optional>
#include <stdexcept>

// ============================================================
// C++20: [[likely]] and [[unlikely]] attributes
// ============================================================

// Error handling — error path is rare
std::optional<int> parse_positive(int raw) {
    if (raw > 0) [[likely]] {
        return raw;  // compiler puts this on the fall-through path
    } else [[unlikely]] {
        return std::nullopt;  // moved to cold code section
    }
}

// Switch statement hints (C++20)
enum class PacketType : uint8_t { Data = 0, Ack = 1, Heartbeat = 2, Error = 3 };

void handle_packet(PacketType type) {
    switch (type) {
    case PacketType::Data: [[likely]]
        // 90% of traffic — compiler optimizes this as the default path
        std::cout << "data\n";
        break;
    case PacketType::Ack:
        std::cout << "ack\n";
        break;
    case PacketType::Heartbeat:
        std::cout << "heartbeat\n";
        break;
    case PacketType::Error: [[unlikely]]
        // <1% of traffic — moved to cold section
        std::cerr << "error!\n";
        break;
    }
}

// ============================================================
// Pre-C++20: __builtin_expect (GCC, Clang)
// ============================================================
#if defined(__GNUC__) || defined(__clang__)
#define LIKELY(x)   __builtin_expect(!!(x), 1)
#define UNLIKELY(x) __builtin_expect(!!(x), 0)
#else
#define LIKELY(x)   (x)
#define UNLIKELY(x) (x)
#endif

void* safe_malloc(size_t size) {
    void* ptr = std::malloc(size);
    if (UNLIKELY(ptr == nullptr)) {
        // Allocation failure is extremely rare — hint it as unlikely
        throw std::bad_alloc();
    }
    return ptr;
}

// ============================================================
// Benchmark: sum array elements, skip negative (rare condition)
// ============================================================
int64_t sum_no_hints(const std::vector<int>& data) {
    int64_t total = 0;
    for (int val : data) {
        if (val >= 0) {
            total += val;
        } else {
            total -= val;  // rare path: only ~1% of values are negative
        }
    }
    return total;
}

int64_t sum_with_hints(const std::vector<int>& data) {
    int64_t total = 0;
    for (int val : data) {
        if (val >= 0) [[likely]] {
            total += val;
        } else [[unlikely]] {
            total -= val;
        }
    }
    return total;
}

// ============================================================
// Real-world pattern: fast path / slow path separation
// ============================================================
class SmallBuffer {
    static constexpr size_t INLINE_SIZE = 64;
    alignas(16) char inline_buf_[INLINE_SIZE];
    char* data_ = inline_buf_;
    size_t size_ = 0;
    size_t capacity_ = INLINE_SIZE;

public:
    void push_back(char c) {
        if (size_ < capacity_) [[likely]] {
            // Fast path: just append (hot, inlined)
            data_[size_++] = c;
        } else [[unlikely]] {
            // Slow path: grow (cold, may be outlined by compiler)
            grow_and_push(c);
        }
    }

private:
    void grow_and_push(char c) {
        size_t new_cap = capacity_ * 2;
        char* new_data = new char[new_cap];
        std::copy(data_, data_ + size_, new_data);
        if (data_ != inline_buf_) delete[] data_;
        data_ = new_data;
        capacity_ = new_cap;
        data_[size_++] = c;
    }

public:
    ~SmallBuffer() { if (data_ != inline_buf_) delete[] data_; }
    [[nodiscard]] size_t size() const { return size_; }
};

template <typename Fn>
double bench(const char* label, Fn fn, int iters = 100) {
    fn();
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iters; ++i) fn();
    auto end = std::chrono::high_resolution_clock::now();
    double us = std::chrono::duration<double, std::micro>(end - start).count() / iters;
    std::cout << label << ": " << us << " us/iter\n";
    return us;
}

int main() {
    // Generate data: 99% positive, 1% negative
    std::mt19937 rng(42);
    std::uniform_int_distribution<int> dist(1, 1000);
    std::vector<int> data(10'000'000);
    for (auto& v : data) {
        v = dist(rng);
        if (rng() % 100 == 0) v = -v;  // 1% negative
    }

    bench("no hints  ", [&] { return sum_no_hints(data); });
    bench("with hints", [&] { return sum_with_hints(data); });

    // SmallBuffer demo
    SmallBuffer buf;
    for (char c = 'a'; c <= 'z'; ++c) buf.push_back(c);
    std::cout << "buffer size: " << buf.size() << "\n";
}
```

**Build:**
```bash
g++ -std=c++20 -O2 -o branch_demo branch_hints.cpp
```

**When to use hints:**
- Error handling paths (almost always `[[unlikely]]`)
- Allocation failure checks
- Fast path / slow path separation in hot loops
- Assertion-style invariant checks

**When NOT to use:** Do not sprinkle `[[likely]]` everywhere. The hardware branch predictor already handles most branches well. Profile-guided optimization (PGO) is strictly better because it uses real execution data rather than programmer guesses.'''),

    ("cpp_deep/lto_link_time_optimization", r'''What is Link-Time Optimization (LTO) in C++? What are the tradeoffs and how do I enable it?''', r'''<think>
LTO allows the compiler to optimize across translation unit boundaries at link time.
Without LTO: each .cpp is compiled independently, then linked. No cross-TU inlining or optimization.
With LTO: compiler emits IR (intermediate representation) instead of object code, then optimizes all
IR together at link time, enabling cross-file inlining, dead code elimination, and devirtualization.
Two modes: Full LTO (all IR in one pass) and Thin LTO (parallel, scalable).
Full LTO: maximum optimization but O(N) memory and single-threaded link step. Slow for large projects.
Thin LTO: ~95% of Full LTO benefit with parallel compilation. Much faster, much less memory.
Tradeoffs: longer link times, harder debugging (optimized away variables), potential ODR issues exposed.
I should show how to enable it in CMake and raw compiler flags.
Also show the impact: typical 5-20% speedup for real applications.
Important: all object files AND libraries must be compiled with LTO flags.
If you link a non-LTO .o with LTO .o, the non-LTO file doesn't benefit from cross-TU optimization.
Compiler flags: -flto (GCC/Clang), -flto=thin (Clang Thin LTO), /GL + /LTCG (MSVC).
Let me write a multi-file example to demonstrate.
</think>

LTO lets the compiler optimize across all source files at link time, enabling cross-file inlining and dead code elimination:

```cpp
// ============================================================
// math_utils.hpp — header with declarations
// ============================================================
#pragma once

// Without LTO: these are opaque to callers in other .cpp files
// With LTO: compiler can inline them across translation units
double compute_distance(double x1, double y1, double x2, double y2);
double normalize_angle(double radians);
bool is_close(double a, double b, double epsilon = 1e-9);

// Virtual function — LTO enables devirtualization when the concrete type is known
class Shape {
public:
    virtual ~Shape() = default;
    virtual double area() const = 0;
};

class Circle : public Shape {
    double radius_;
public:
    explicit Circle(double r) : radius_(r) {}
    double area() const override;
};

class Rectangle : public Shape {
    double w_, h_;
public:
    Rectangle(double w, double h) : w_(w), h_(h) {}
    double area() const override;
};
```

```cpp
// ============================================================
// math_utils.cpp — definitions in a separate TU
// ============================================================
#include "math_utils.hpp"
#include <cmath>

double compute_distance(double x1, double y1, double x2, double y2) {
    double dx = x2 - x1;
    double dy = y2 - y1;
    return std::sqrt(dx * dx + dy * dy);
}

double normalize_angle(double radians) {
    constexpr double TWO_PI = 2.0 * 3.14159265358979323846;
    radians = std::fmod(radians, TWO_PI);
    if (radians < 0) radians += TWO_PI;
    return radians;
}

bool is_close(double a, double b, double epsilon) {
    return std::abs(a - b) < epsilon;
}

double Circle::area() const { return 3.14159265358979323846 * radius_ * radius_; }
double Rectangle::area() const { return w_ * h_; }
```

```cpp
// ============================================================
// main.cpp — calls functions from another TU
// ============================================================
#include "math_utils.hpp"
#include <iostream>
#include <vector>
#include <memory>
#include <chrono>
#include <numeric>

double total_area(const std::vector<std::unique_ptr<Shape>>& shapes) {
    double sum = 0;
    for (const auto& s : shapes) {
        sum += s->area();  // Without LTO: virtual call (indirect branch)
                           // With LTO: devirtualized to direct call if type known
    }
    return sum;
}

int main() {
    // Benchmark compute_distance — inlineable with LTO
    constexpr int N = 10'000'000;

    auto start = std::chrono::high_resolution_clock::now();
    double total = 0;
    for (int i = 0; i < N; ++i) {
        total += compute_distance(0.0, 0.0, static_cast<double>(i), 1.0);
    }
    auto end = std::chrono::high_resolution_clock::now();
    double ms = std::chrono::duration<double, std::milli>(end - start).count();

    std::cout << "distance sum: " << total << "\n";
    std::cout << "time: " << ms << " ms\n";

    // Shape devirtualization demo
    std::vector<std::unique_ptr<Shape>> shapes;
    for (int i = 0; i < 1000; ++i) {
        shapes.push_back(std::make_unique<Circle>(static_cast<double>(i)));
    }
    std::cout << "total area: " << total_area(shapes) << "\n";
}
```

**Build commands comparing NO LTO vs LTO:**
```bash
# --- Without LTO: each file compiled independently ---
g++ -std=c++20 -O2 -c math_utils.cpp -o math_utils.o
g++ -std=c++20 -O2 -c main.cpp -o main.o
g++ math_utils.o main.o -o app_no_lto

# --- Full LTO: all files optimized together at link time ---
g++ -std=c++20 -O2 -flto -c math_utils.cpp -o math_utils.o
g++ -std=c++20 -O2 -flto -c main.cpp -o main.o
g++ -flto math_utils.o main.o -o app_full_lto

# --- Thin LTO (Clang): parallel, scalable ---
clang++ -std=c++20 -O2 -flto=thin -c math_utils.cpp -o math_utils.o
clang++ -std=c++20 -O2 -flto=thin -c main.cpp -o main.o
clang++ -flto=thin math_utils.o main.o -o app_thin_lto

# --- MSVC ---
cl /std:c++20 /O2 /GL math_utils.cpp main.cpp /link /LTCG /out:app_lto.exe
```

**CMake (modern pattern):**
```cmake
cmake_minimum_required(VERSION 3.9)
project(lto_demo CXX)

include(CheckIPOSupported)
check_ipo_supported(RESULT lto_supported)

add_executable(app main.cpp math_utils.cpp)
target_compile_features(app PRIVATE cxx_std_20)

if(lto_supported)
    set_target_properties(app PROPERTIES INTERPROCEDURAL_OPTIMIZATION TRUE)
    message(STATUS "LTO enabled")
else()
    message(WARNING "LTO not supported by this compiler")
endif()
```

**What LTO enables:** cross-file inlining, devirtualization of virtual calls, whole-program dead code elimination, and constant propagation across TUs. Typical 5-20% speedup. Use Thin LTO for large projects (parallel, lower memory).

**Tradeoffs:** longer link times (2-10x), harder debugging (variables optimized away), all objects must be compiled with LTO flags, and some linker bugs have historically appeared with LTO on bleeding-edge code.'''),

    ("cpp_deep/profile_guided_optimization", r'''How do I use Profile-Guided Optimization (PGO) in C++? What is the workflow and what improvements can I expect?''', r'''<think>
PGO is a three-step workflow:
1. Instrument: compile with profiling instrumentation
2. Train: run the instrumented binary on representative workloads
3. Optimize: recompile using the collected profile data
The compiler uses real execution data to make better decisions about:
- Branch prediction (which path is hot)
- Function inlining (which functions are actually called frequently)
- Code layout (hot code together, cold code separate)
- Loop unrolling (which loops are hot)
- Register allocation priorities
Typical improvement: 10-30% for CPU-bound applications.
GCC: -fprofile-generate / -fprofile-use
Clang: -fprofile-instr-generate / -fprofile-instr-use=file.profdata
MSVC: /GENPROFILE / /USEPROFILE
I should show the complete workflow with a concrete example.
Important: the training workload must be representative of production usage.
PGO is strictly better than manual branch hints because it uses real data.
BOLT (Binary Optimization and Layout Tool) can further optimize after PGO.
Let me write a script-like example showing all three steps.
</think>

PGO is a three-step build process that uses real execution data to optimize code layout, inlining, and branch prediction:

```cpp
// pgo_demo.cpp — A program that benefits significantly from PGO
#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <random>
#include <chrono>
#include <unordered_map>
#include <numeric>

// ============================================================
// Workload: simulated log parser with branchy code
// PGO helps because the compiler learns which branches are hot
// ============================================================
enum class LogLevel { Debug, Info, Warn, Error, Fatal };

struct LogEntry {
    LogLevel level;
    int timestamp;
    std::string message;
};

// Branch-heavy function — PGO learns the distribution
int process_entry(const LogEntry& entry) {
    // In real logs: 60% Debug, 25% Info, 10% Warn, 4% Error, 1% Fatal
    // Without PGO: compiler assumes 50/50 at each branch
    // With PGO: compiler knows Debug is hot, arranges code accordingly
    switch (entry.level) {
    case LogLevel::Debug:
        return 0;  // skip debug in production — hot path
    case LogLevel::Info:
        return 1;
    case LogLevel::Warn:
        return static_cast<int>(entry.message.size());
    case LogLevel::Error:
        return static_cast<int>(entry.message.size()) * 2;
    case LogLevel::Fatal:
        return -1;
    }
    return 0;
}

// Map-heavy function — PGO optimizes hash function and collision handling
std::unordered_map<std::string, int> aggregate_logs(const std::vector<LogEntry>& logs) {
    std::unordered_map<std::string, int> counts;
    counts.reserve(100);  // hint for expected size
    for (const auto& entry : logs) {
        if (entry.level >= LogLevel::Warn) {
            counts[entry.message]++;
        }
    }
    return counts;
}

// Sort-heavy function — PGO helps std::sort choose optimal strategies
void sort_by_timestamp(std::vector<LogEntry>& logs) {
    std::sort(logs.begin(), logs.end(),
        [](const LogEntry& a, const LogEntry& b) {
            return a.timestamp < b.timestamp;
        });
}

std::vector<LogEntry> generate_logs(size_t count) {
    std::mt19937 rng(12345);
    std::discrete_distribution<int> level_dist({60, 25, 10, 4, 1}); // realistic distribution
    std::vector<std::string> messages = {
        "request handled", "cache miss", "timeout", "disk full",
        "auth failed", "rate limited", "connection reset", "OOM"
    };

    std::vector<LogEntry> logs(count);
    for (size_t i = 0; i < count; ++i) {
        logs[i].level = static_cast<LogLevel>(level_dist(rng));
        logs[i].timestamp = static_cast<int>(rng() % 1'000'000);
        logs[i].message = messages[rng() % messages.size()];
    }
    return logs;
}

int main() {
    auto logs = generate_logs(2'000'000);

    auto start = std::chrono::high_resolution_clock::now();

    // Phase 1: Process entries (branch-heavy)
    int total = 0;
    for (const auto& entry : logs) {
        total += process_entry(entry);
    }

    // Phase 2: Aggregate (hash-map-heavy)
    auto agg = aggregate_logs(logs);

    // Phase 3: Sort (comparison-heavy)
    sort_by_timestamp(logs);

    auto end = std::chrono::high_resolution_clock::now();
    double ms = std::chrono::duration<double, std::milli>(end - start).count();

    std::cout << "processed: " << total << "\n";
    std::cout << "unique warnings+: " << agg.size() << "\n";
    std::cout << "time: " << ms << " ms\n";
}
```

**Three-step PGO workflow:**

```bash
#!/bin/bash
# pgo_build.sh — Complete PGO workflow

# ============================================================
# Step 1: INSTRUMENT — compile with profiling instrumentation
# ============================================================

# GCC
g++ -std=c++20 -O2 -fprofile-generate=./pgo_data -o app_instrumented pgo_demo.cpp

# Clang
# clang++ -std=c++20 -O2 -fprofile-instr-generate -o app_instrumented pgo_demo.cpp

echo "=== Step 1: Instrumented build complete ==="

# ============================================================
# Step 2: TRAIN — run on representative workload
# ============================================================

# Run the instrumented binary — this generates .gcda files (GCC) or default.profraw (Clang)
./app_instrumented

# For Clang: merge raw profiles
# llvm-profdata merge -output=pgo_data.profdata default.profraw

echo "=== Step 2: Profile data collected ==="

# ============================================================
# Step 3: OPTIMIZE — recompile using profile data
# ============================================================

# GCC — reads .gcda files from pgo_data/
g++ -std=c++20 -O2 -fprofile-use=./pgo_data -o app_pgo pgo_demo.cpp

# Clang
# clang++ -std=c++20 -O2 -fprofile-instr-use=pgo_data.profdata -o app_pgo pgo_demo.cpp

echo "=== Step 3: PGO-optimized build complete ==="

# ============================================================
# Compare performance
# ============================================================
echo "--- Baseline (no PGO) ---"
g++ -std=c++20 -O2 -o app_baseline pgo_demo.cpp
./app_baseline

echo "--- PGO optimized ---"
./app_pgo
```

**CMake integration:**
```cmake
# CMakeLists.txt — PGO support
option(PGO_GENERATE "Build with PGO instrumentation" OFF)
option(PGO_USE "Build with PGO profile data" OFF)

add_executable(app pgo_demo.cpp)
target_compile_features(app PRIVATE cxx_std_20)
target_compile_options(app PRIVATE -O2)

if(PGO_GENERATE)
    target_compile_options(app PRIVATE -fprofile-generate=${CMAKE_BINARY_DIR}/pgo_data)
    target_link_options(app PRIVATE -fprofile-generate=${CMAKE_BINARY_DIR}/pgo_data)
elseif(PGO_USE)
    target_compile_options(app PRIVATE -fprofile-use=${CMAKE_BINARY_DIR}/pgo_data)
    target_link_options(app PRIVATE -fprofile-use=${CMAKE_BINARY_DIR}/pgo_data)
endif()

# Usage:
# cmake -B build -DPGO_GENERATE=ON && cmake --build build && ./build/app
# cmake -B build -DPGO_USE=ON && cmake --build build && ./build/app
```

PGO typically provides 10-30% speedup for branchy, real-world code. The training workload must be representative of production usage. Combine with LTO for maximum effect. MSVC uses `/GENPROFILE` and `/USEPROFILE` flags.'''),

    ("cpp_deep/google_benchmark", r'''How do I use Google Benchmark to properly benchmark C++ code? Show patterns for avoiding common benchmarking pitfalls.''', r'''<think>
Google Benchmark is the standard C++ microbenchmarking library.
Key pitfalls it solves: optimizer removing dead code, insufficient iterations, cold cache effects.
benchmark::DoNotOptimize() prevents the compiler from optimizing away results.
benchmark::ClobberMemory() forces memory writes to be visible.
The library auto-tunes iteration count for statistical significance.
I should show: basic benchmark, DoNotOptimize, parameterized benchmarks, fixtures, custom counters.
Also show how to compare two implementations side by side.
Important patterns: benchmark::State loop, range parameters, complexity analysis.
Let me write a complete example with several benchmark patterns.
Also mention how to build with CMake and FetchContent.
</think>

Google Benchmark handles iteration tuning, dead-code prevention, and statistical analysis. Here are the essential patterns:

```cpp
// bench_demo.cpp — Google Benchmark patterns and pitfalls
#include <benchmark/benchmark.h>
#include <vector>
#include <algorithm>
#include <numeric>
#include <string>
#include <unordered_map>
#include <map>
#include <random>
#include <memory>
#include <cstring>

// ============================================================
// Pattern 1: Basic benchmark with DoNotOptimize
// ============================================================
static void BM_VectorPushBack(benchmark::State& state) {
    for (auto _ : state) {
        std::vector<int> v;
        v.reserve(1000);
        for (int i = 0; i < 1000; ++i) {
            v.push_back(i);
        }
        // CRITICAL: prevent compiler from removing the entire loop
        benchmark::DoNotOptimize(v.data());
        // Force all pending writes to be committed
        benchmark::ClobberMemory();
    }
}
BENCHMARK(BM_VectorPushBack);

// ============================================================
// Pattern 2: Parameterized benchmark — vary input size
// ============================================================
static void BM_Sort(benchmark::State& state) {
    const int n = state.range(0);
    std::mt19937 rng(42);
    std::vector<int> data(n);

    for (auto _ : state) {
        // Re-generate data each iteration (sorting is destructive)
        state.PauseTiming();  // exclude setup from measurement
        std::generate(data.begin(), data.end(), rng);
        state.ResumeTiming();

        std::sort(data.begin(), data.end());
        benchmark::DoNotOptimize(data.data());
    }
    // Report throughput: elements per second
    state.SetItemsProcessed(static_cast<int64_t>(state.iterations()) * n);
    // Report complexity for Big-O analysis
    state.SetComplexityN(n);
}
BENCHMARK(BM_Sort)
    ->RangeMultiplier(4)
    ->Range(256, 1 << 20)     // 256, 1024, 4096, ..., 1M
    ->Complexity(benchmark::kNLogN);  // expected: O(n log n)

// ============================================================
// Pattern 3: Comparing implementations (A/B testing)
// ============================================================
static void BM_MapLookup(benchmark::State& state) {
    std::map<std::string, int> m;
    for (int i = 0; i < 10000; ++i)
        m["key_" + std::to_string(i)] = i;

    for (auto _ : state) {
        auto it = m.find("key_5000");
        benchmark::DoNotOptimize(it);
    }
}
BENCHMARK(BM_MapLookup);

static void BM_UnorderedMapLookup(benchmark::State& state) {
    std::unordered_map<std::string, int> m;
    for (int i = 0; i < 10000; ++i)
        m["key_" + std::to_string(i)] = i;

    for (auto _ : state) {
        auto it = m.find("key_5000");
        benchmark::DoNotOptimize(it);
    }
}
BENCHMARK(BM_UnorderedMapLookup);

// ============================================================
// Pattern 4: Fixture for shared setup
// ============================================================
class DataFixture : public benchmark::Fixture {
public:
    std::vector<double> data;

    void SetUp(const benchmark::State& state) override {
        data.resize(state.range(0));
        std::mt19937 rng(42);
        std::uniform_real_distribution<double> dist(0.0, 1.0);
        for (auto& d : data) d = dist(rng);
    }

    void TearDown(const benchmark::State&) override {
        data.clear();
        data.shrink_to_fit();
    }
};

BENCHMARK_DEFINE_F(DataFixture, StdAccumulate)(benchmark::State& state) {
    for (auto _ : state) {
        double sum = std::accumulate(data.begin(), data.end(), 0.0);
        benchmark::DoNotOptimize(sum);
    }
    state.SetBytesProcessed(
        static_cast<int64_t>(state.iterations()) *
        static_cast<int64_t>(data.size()) * sizeof(double));
}
BENCHMARK_REGISTER_F(DataFixture, StdAccumulate)->Range(1024, 1 << 20);

BENCHMARK_DEFINE_F(DataFixture, ManualSum)(benchmark::State& state) {
    for (auto _ : state) {
        double sum = 0.0;
        for (size_t i = 0; i < data.size(); ++i) sum += data[i];
        benchmark::DoNotOptimize(sum);
    }
    state.SetBytesProcessed(
        static_cast<int64_t>(state.iterations()) *
        static_cast<int64_t>(data.size()) * sizeof(double));
}
BENCHMARK_REGISTER_F(DataFixture, ManualSum)->Range(1024, 1 << 20);

// ============================================================
// Pattern 5: Custom counters
// ============================================================
static void BM_StringConcat(benchmark::State& state) {
    int64_t total_chars = 0;
    for (auto _ : state) {
        std::string result;
        for (int i = 0; i < 100; ++i) {
            result += "hello world ";
        }
        total_chars += static_cast<int64_t>(result.size());
        benchmark::DoNotOptimize(result);
    }
    state.counters["chars/s"] = benchmark::Counter(
        total_chars, benchmark::Counter::kIsRate);
    state.counters["chars"] = benchmark::Counter(
        total_chars, benchmark::Counter::kAvgThreads);
}
BENCHMARK(BM_StringConcat);

// ============================================================
// Pattern 6: Memory allocation benchmark
// ============================================================
static void BM_UniquePtr(benchmark::State& state) {
    for (auto _ : state) {
        auto p = std::make_unique<int>(42);
        benchmark::DoNotOptimize(p.get());
    }
}
BENCHMARK(BM_UniquePtr);

static void BM_SharedPtr(benchmark::State& state) {
    for (auto _ : state) {
        auto p = std::make_shared<int>(42);
        benchmark::DoNotOptimize(p.get());
    }
}
BENCHMARK(BM_SharedPtr);

BENCHMARK_MAIN();
```

**CMakeLists.txt:**
```cmake
cmake_minimum_required(VERSION 3.14)
project(bench_demo CXX)

include(FetchContent)
FetchContent_Declare(
    benchmark
    GIT_REPOSITORY https://github.com/google/benchmark.git
    GIT_TAG v1.8.3
)
set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(benchmark)

add_executable(bench bench_demo.cpp)
target_compile_features(bench PRIVATE cxx_std_20)
target_link_libraries(bench PRIVATE benchmark::benchmark)
```

**Build and run:**
```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
./build/bench --benchmark_format=console --benchmark_repetitions=3
# JSON output for CI:
./build/bench --benchmark_out=results.json --benchmark_out_format=json
```

Key rules: always use `DoNotOptimize` on results, use `PauseTiming`/`ResumeTiming` sparingly (they add overhead), and run with `--benchmark_repetitions=3` to get standard deviation.'''),

    ("cpp_deep/reducing_compile_times", r'''How do I reduce C++ compile times? Show techniques like precompiled headers, forward declarations, and C++20 modules.''', r'''<think>
C++ compile times are a major productivity drain. Key techniques:
1. Forward declarations — avoid including headers when a pointer/reference suffices.
2. Precompiled headers (PCH) — compile heavy headers once.
3. C++20 modules — the modern replacement for headers.
4. Pimpl idiom — hide implementation details, reduce recompilation cascading.
5. Unity/jumbo builds — compile multiple .cpp files as one TU.
6. Extern templates — prevent implicit instantiation in every TU.
7. ccache / sccache — cache compilation results.
I should show concrete examples of each technique.
PCH: target_precompile_headers in CMake 3.16+.
Modules: import std; (C++23), export module.
Forward declarations are the simplest win — most codebases under-use them.
Pimpl is particularly effective for large classes in widely-included headers.
Let me structure this as a series of concrete patterns.
</think>

Here are the most impactful techniques for reducing C++ compile times, from simplest to most advanced:

```cpp
// ============================================================
// Technique 1: Forward declarations — avoid unnecessary #includes
// ============================================================

// BAD: widget.hpp includes everything
// #include "database.hpp"   // 50K lines of templates
// #include "renderer.hpp"   // pulls in OpenGL headers
// #include "network.hpp"    // pulls in socket headers

// GOOD: widget.hpp — forward-declare, include only in .cpp
// widget.hpp
#pragma once
#include <memory>
#include <string>

// Forward declarations — compiler only needs to know these exist
class Database;
class Renderer;
class NetworkClient;

class Widget {
public:
    Widget(std::string name);
    ~Widget();  // must be declared (defined in .cpp for pimpl)
    void render();
    void save();

private:
    std::string name_;
    // Pointers and references work with forward-declared types
    std::unique_ptr<Database> db_;
    Renderer* renderer_ = nullptr;
};

// widget.cpp — include the heavy headers here, not in the header
// #include "widget.hpp"
// #include "database.hpp"
// #include "renderer.hpp"
// #include "network.hpp"
// Widget::Widget(...) { ... }  // definitions here


// ============================================================
// Technique 2: Pimpl idiom — hide implementation, break dependencies
// ============================================================

// logger.hpp — stable ABI, fast to compile
// Changes to LoggerImpl don't cause recompilation of Logger users
class Logger {
public:
    Logger();
    ~Logger();
    Logger(Logger&&) noexcept;
    Logger& operator=(Logger&&) noexcept;

    void log(const std::string& msg);
    void set_level(int level);

private:
    struct Impl;  // forward-declared — defined only in .cpp
    std::unique_ptr<Impl> impl_;
};

// logger.cpp
// #include "logger.hpp"
// #include <fstream>       // heavy include — only in .cpp
// #include <mutex>
// #include <chrono>
// #include <format>        // C++20 — very heavy header
//
// struct Logger::Impl {
//     std::ofstream file;
//     std::mutex mtx;
//     int level = 0;
// };
//
// Logger::Logger() : impl_(std::make_unique<Impl>()) {}
// Logger::~Logger() = default;
// Logger::Logger(Logger&&) noexcept = default;
// Logger& Logger::operator=(Logger&&) noexcept = default;
// void Logger::log(const std::string& msg) { ... }


// ============================================================
// Technique 3: Extern templates — prevent redundant instantiation
// ============================================================

// my_vector.hpp — declare extern to prevent instantiation in every TU
#include <vector>

// Tell compiler: don't instantiate these — they'll be in one .cpp file
extern template class std::vector<int>;
extern template class std::vector<double>;
extern template class std::vector<std::string>;

// my_vector.cpp — explicit instantiation in exactly one TU
// template class std::vector<int>;
// template class std::vector<double>;
// template class std::vector<std::string>;


// ============================================================
// Technique 4: C++20 Modules (the future)
// ============================================================

// math_module.cppm (module interface unit)
/*
export module math;

export namespace math {
    double add(double a, double b) { return a + b; }
    double multiply(double a, double b) { return a * b; }

    export class Calculator {
    public:
        double eval(double a, double b);
    };
}
*/

// main.cpp using modules
/*
import math;           // replaces #include — only parses once, cached as BMI
import std;            // C++23: import the entire standard library

int main() {
    math::Calculator calc;
    std::cout << math::add(1.0, 2.0) << "\n";
}
*/


// ============================================================
// Main — just proves everything compiles
// ============================================================
int main() {
    // Forward declaration and pimpl patterns demonstrated above
    // Full implementations would be in separate .cpp files
    return 0;
}
```

**CMakeLists.txt with all compile-time optimizations:**
```cmake
cmake_minimum_required(VERSION 3.16)
project(fast_compile CXX)

# --- Precompiled Headers (CMake 3.16+) ---
add_library(app_lib
    widget.cpp
    logger.cpp
    # ... other sources
)
target_compile_features(app_lib PRIVATE cxx_std_20)

# PCH: compile these heavy headers once, reuse across all TUs
target_precompile_headers(app_lib PRIVATE
    <vector>
    <string>
    <memory>
    <unordered_map>
    <algorithm>
    <functional>
    <iostream>
    # Project headers that rarely change:
    # "core/types.hpp"
)

# --- Unity/Jumbo builds (CMake 3.16+) ---
# Combines multiple .cpp files into one TU — fewer compiler invocations
set_target_properties(app_lib PROPERTIES UNITY_BUILD ON)
set_target_properties(app_lib PROPERTIES UNITY_BUILD_BATCH_SIZE 8)

# --- C++20 Modules (CMake 3.28+, experimental) ---
# add_library(math_mod)
# target_sources(math_mod PUBLIC FILE_SET CXX_MODULES FILES math_module.cppm)

# --- ccache integration ---
find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
    set(CMAKE_CXX_COMPILER_LAUNCHER ${CCACHE_PROGRAM})
    message(STATUS "Using ccache: ${CCACHE_PROGRAM}")
endif()

# --- Linker optimization ---
# Use mold (fastest) or lld (fast) instead of default ld
# set(CMAKE_EXE_LINKER_FLAGS "-fuse-ld=mold")
```

**Impact ranking (typical large project):**

| Technique | Effort | Compile time reduction |
|---|---|---|
| ccache/sccache | 5 min setup | 80-95% (incremental) |
| Precompiled headers | 30 min | 20-50% |
| Forward declarations | Hours (ongoing) | 10-30% |
| Unity builds | 5 min CMake | 30-70% |
| Pimpl idiom | Hours per class | Reduces cascading rebuilds |
| C++20 modules | Major refactor | 50-80% (future) |
| Extern templates | 1 hour | 5-15% |
| mold linker | 5 min | 2-5x faster linking |

Start with ccache and precompiled headers for immediate wins. Forward declarations and pimpl are ongoing discipline. C++20 modules are the long-term solution but require CMake 3.28+ and recent compilers.'''),

    ("cpp_deep/dynamic_library_loading", r'''How do I dynamically load shared libraries at runtime in C++ using dlopen on Linux and LoadLibrary on Windows?''', r'''<think>
Dynamic loading lets you load code at runtime without linking at compile time.
Linux: dlopen/dlsym/dlclose from <dlfcn.h>
Windows: LoadLibrary/GetProcAddress/FreeLibrary from <windows.h>
Key issues: name mangling (use extern "C"), error handling, lifetime management.
I should show a cross-platform wrapper using RAII.
The common pattern: load a shared library, get function pointers, call them.
Important: functions must be exported with extern "C" to avoid name mangling.
On Windows: also need __declspec(dllexport) or a .def file.
Let me show both the plugin library and the loader, with a cross-platform abstraction.
The RAII wrapper should handle dlclose/FreeLibrary in the destructor.
</think>

Here is a cross-platform dynamic library loader with RAII and a plugin example:

```cpp
// ============================================================
// plugin_api.h — Shared header defining the plugin interface (C ABI)
// ============================================================
#pragma once

#ifdef _WIN32
    #ifdef PLUGIN_EXPORTS
        #define PLUGIN_API __declspec(dllexport)
    #else
        #define PLUGIN_API __declspec(dllimport)
    #endif
#else
    #define PLUGIN_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

// Plugin functions — extern "C" prevents name mangling
PLUGIN_API const char* plugin_name();
PLUGIN_API int plugin_version();
PLUGIN_API double plugin_compute(double x, double y);

#ifdef __cplusplus
}
#endif
```

```cpp
// ============================================================
// my_plugin.cpp — A shared library implementing the plugin API
// ============================================================
#define PLUGIN_EXPORTS
#include "plugin_api.h"
#include <cmath>

extern "C" {

PLUGIN_API const char* plugin_name() {
    return "MathPlugin";
}

PLUGIN_API int plugin_version() {
    return 1;
}

PLUGIN_API double plugin_compute(double x, double y) {
    return std::sqrt(x * x + y * y);  // Euclidean distance
}

}  // extern "C"
```

```cpp
// ============================================================
// dynlib.hpp — Cross-platform RAII dynamic library loader
// ============================================================
#pragma once

#include <string>
#include <stdexcept>
#include <utility>

#ifdef _WIN32
    #ifndef WIN32_LEAN_AND_MEAN
    #define WIN32_LEAN_AND_MEAN
    #endif
    #include <windows.h>
#else
    #include <dlfcn.h>
#endif

class DynamicLibrary {
public:
    explicit DynamicLibrary(const std::string& path) {
#ifdef _WIN32
        handle_ = LoadLibraryA(path.c_str());
        if (!handle_) {
            throw std::runtime_error(
                "Failed to load " + path + " (error " + std::to_string(GetLastError()) + ")");
        }
#else
        handle_ = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle_) {
            throw std::runtime_error(
                "Failed to load " + path + ": " + dlerror());
        }
#endif
    }

    ~DynamicLibrary() {
        if (handle_) {
#ifdef _WIN32
            FreeLibrary(static_cast<HMODULE>(handle_));
#else
            dlclose(handle_);
#endif
        }
    }

    // Move-only (no copying)
    DynamicLibrary(const DynamicLibrary&) = delete;
    DynamicLibrary& operator=(const DynamicLibrary&) = delete;
    DynamicLibrary(DynamicLibrary&& other) noexcept
        : handle_(std::exchange(other.handle_, nullptr)) {}
    DynamicLibrary& operator=(DynamicLibrary&& other) noexcept {
        std::swap(handle_, other.handle_);
        return *this;
    }

    // Get a typed function pointer by name
    template <typename FuncPtr>
    FuncPtr get(const std::string& name) const {
        void* sym = nullptr;
#ifdef _WIN32
        sym = reinterpret_cast<void*>(
            GetProcAddress(static_cast<HMODULE>(handle_), name.c_str()));
        if (!sym) {
            throw std::runtime_error(
                "Symbol not found: " + name + " (error " + std::to_string(GetLastError()) + ")");
        }
#else
        dlerror();  // clear previous errors
        sym = dlsym(handle_, name.c_str());
        const char* err = dlerror();
        if (err) {
            throw std::runtime_error("Symbol not found: " + name + ": " + err);
        }
#endif
        return reinterpret_cast<FuncPtr>(sym);
    }

private:
    void* handle_ = nullptr;
};
```

```cpp
// ============================================================
// main.cpp — Load plugin at runtime and call its functions
// ============================================================
#include "dynlib.hpp"
#include <iostream>

int main(int argc, char* argv[]) {
    // Default plugin path
    std::string plugin_path =
#ifdef _WIN32
        "my_plugin.dll";
#elif __APPLE__
        "./libmy_plugin.dylib";
#else
        "./libmy_plugin.so";
#endif

    if (argc > 1) plugin_path = argv[1];

    try {
        // Load the shared library (RAII — unloads on scope exit)
        DynamicLibrary plugin(plugin_path);

        // Get typed function pointers
        auto name_fn    = plugin.get<const char*(*)()>("plugin_name");
        auto version_fn = plugin.get<int(*)()>("plugin_version");
        auto compute_fn = plugin.get<double(*)(double, double)>("plugin_compute");

        // Call plugin functions
        std::cout << "Plugin: " << name_fn() << " v" << version_fn() << "\n";
        std::cout << "compute(3.0, 4.0) = " << compute_fn(3.0, 4.0) << "\n";
        // Expected output: 5.0 (Euclidean distance)

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
    // DynamicLibrary destructor calls dlclose/FreeLibrary here
}
```

**Build commands:**
```bash
# Linux — build the plugin as a shared library
g++ -std=c++20 -O2 -shared -fPIC -o libmy_plugin.so my_plugin.cpp

# Build the loader (link with -ldl for dlopen/dlsym)
g++ -std=c++20 -O2 -o loader main.cpp -ldl

# Run
./loader ./libmy_plugin.so

# Windows (MSVC)
# cl /std:c++20 /O2 /LD /DPLUGIN_EXPORTS my_plugin.cpp /Fe:my_plugin.dll
# cl /std:c++20 /O2 main.cpp /Fe:loader.exe

# macOS
# clang++ -std=c++20 -O2 -shared -o libmy_plugin.dylib my_plugin.cpp
# clang++ -std=c++20 -O2 -o loader main.cpp
```

Key points: always use `extern "C"` for plugin APIs to prevent name mangling, use RAII for library lifetime, and prefer `RTLD_NOW` over `RTLD_LAZY` to catch missing symbols at load time rather than at call time.'''),

    ("cpp_deep/plugin_system_c_abi", r'''How do I build a plugin system in C++ with a stable C ABI so that plugins can be compiled with different compilers?''', r'''<think>
A stable plugin system requires a C ABI boundary because C++ ABI is not standardized.
Key design: C function pointers, POD structs for data exchange, no C++ types across the boundary.
The pattern: define a plugin interface as a struct of function pointers (vtable-like).
Each plugin exports a single C function that returns this struct (the "entry point").
No exceptions across the boundary — use error codes.
No STL types across the boundary — use char*, int, etc.
Version the interface so old plugins work with new hosts.
I should show a complete working example: host + plugin interface + concrete plugin.
Memory ownership must be clear: who allocates, who frees? Best: plugin allocates AND frees.
The struct-of-function-pointers approach is used by countless real systems:
Lua, SQLite, VLC, OBS, etc.
</think>

A stable plugin system uses a C ABI with function pointer structs, so plugins can be built with any compiler:

```cpp
// ============================================================
// plugin_interface.h — THE STABLE ABI CONTRACT
// Include this in both host and plugins. Never change, only extend.
// ============================================================
#pragma once

#include <stdint.h>

#ifdef _WIN32
    #define PLUGIN_EXPORT __declspec(dllexport)
#else
    #define PLUGIN_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

// Version for ABI compatibility checking
#define PLUGIN_API_VERSION 1

// Error codes (no exceptions across ABI boundary)
enum PluginError {
    PLUGIN_OK = 0,
    PLUGIN_ERR_INVALID_ARG = -1,
    PLUGIN_ERR_NOT_SUPPORTED = -2,
    PLUGIN_ERR_OUT_OF_MEMORY = -3,
};

// Plugin metadata — POD types only (no std::string, no STL)
struct PluginInfo {
    const char* name;
    const char* author;
    uint32_t    version_major;
    uint32_t    version_minor;
    uint32_t    api_version;  // must match PLUGIN_API_VERSION
};

// The plugin interface — struct of function pointers (manual vtable)
// This is the "contract" between host and plugin
struct PluginInterface {
    // Lifecycle
    PluginError (*init)(void* plugin_data, const char* config);
    void        (*shutdown)(void* plugin_data);

    // Core functionality
    PluginError (*process)(void* plugin_data, const float* input,
                           float* output, uint32_t count);

    // Info
    PluginInfo  (*get_info)(void* plugin_data);

    // Memory ownership: plugin provides its own allocator
    void*       (*create)(void);    // allocate plugin state
    void        (*destroy)(void*);  // free plugin state

    // Reserved for future extension (bump api_version when used)
    void*       reserved[4];
};

// THE SINGLE ENTRY POINT — every plugin exports exactly this function
// Host calls this to get the interface struct
typedef PluginInterface (*PluginGetInterfaceFn)(void);

#ifdef __cplusplus
}
#endif
```

```cpp
// ============================================================
// gain_plugin.cpp — A concrete plugin (compiled separately)
// ============================================================
#include "plugin_interface.h"
#include <cstring>
#include <cstdlib>
#include <cmath>

// Plugin's internal state — can use any C++ features internally
struct GainState {
    float gain = 1.0f;
    bool initialized = false;
};

// --- Implement each function in the interface ---

static void* gain_create() {
    return new (std::nothrow) GainState();
}

static void gain_destroy(void* data) {
    delete static_cast<GainState*>(data);
}

static PluginError gain_init(void* data, const char* config) {
    auto* state = static_cast<GainState*>(data);
    if (!state) return PLUGIN_ERR_INVALID_ARG;

    // Parse simple config: "gain=2.5"
    if (config && std::strncmp(config, "gain=", 5) == 0) {
        state->gain = static_cast<float>(std::atof(config + 5));
    }
    state->initialized = true;
    return PLUGIN_OK;
}

static void gain_shutdown(void* data) {
    auto* state = static_cast<GainState*>(data);
    if (state) state->initialized = false;
}

static PluginError gain_process(void* data, const float* input,
                                 float* output, uint32_t count) {
    auto* state = static_cast<GainState*>(data);
    if (!state || !state->initialized) return PLUGIN_ERR_INVALID_ARG;
    if (!input || !output) return PLUGIN_ERR_INVALID_ARG;

    for (uint32_t i = 0; i < count; ++i) {
        output[i] = input[i] * state->gain;
    }
    return PLUGIN_OK;
}

static PluginInfo gain_get_info(void*) {
    return PluginInfo{
        .name = "GainPlugin",
        .author = "HiveAI",
        .version_major = 1,
        .version_minor = 0,
        .api_version = PLUGIN_API_VERSION,
    };
}

// THE ENTRY POINT — must be extern "C" PLUGIN_EXPORT
extern "C" PLUGIN_EXPORT PluginInterface plugin_get_interface() {
    PluginInterface iface = {};
    iface.init      = gain_init;
    iface.shutdown  = gain_shutdown;
    iface.process   = gain_process;
    iface.get_info  = gain_get_info;
    iface.create    = gain_create;
    iface.destroy   = gain_destroy;
    // reserved fields stay nullptr
    return iface;
}
```

```cpp
// ============================================================
// host.cpp — The host application that loads and uses plugins
// ============================================================
#include "plugin_interface.h"
#include <iostream>
#include <vector>
#include <string>
#include <filesystem>

#ifdef _WIN32
    #ifndef WIN32_LEAN_AND_MEAN
    #define WIN32_LEAN_AND_MEAN
    #endif
    #include <windows.h>
#else
    #include <dlfcn.h>
#endif

// RAII wrapper for a loaded plugin
class LoadedPlugin {
public:
    explicit LoadedPlugin(const std::string& path) {
#ifdef _WIN32
        lib_ = LoadLibraryA(path.c_str());
#else
        lib_ = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
#endif
        if (!lib_) throw std::runtime_error("Cannot load: " + path);

        // Get the single entry point
#ifdef _WIN32
        auto get_iface = reinterpret_cast<PluginGetInterfaceFn>(
            GetProcAddress(static_cast<HMODULE>(lib_), "plugin_get_interface"));
#else
        auto get_iface = reinterpret_cast<PluginGetInterfaceFn>(
            dlsym(lib_, "plugin_get_interface"));
#endif
        if (!get_iface) throw std::runtime_error("Missing plugin_get_interface");

        iface_ = get_iface();

        // Version check
        auto info = iface_.get_info(nullptr);
        if (info.api_version != PLUGIN_API_VERSION) {
            throw std::runtime_error("API version mismatch");
        }

        // Create plugin state
        data_ = iface_.create();
        if (!data_) throw std::runtime_error("Plugin create() failed");
    }

    ~LoadedPlugin() {
        if (data_) {
            iface_.shutdown(data_);
            iface_.destroy(data_);
        }
#ifdef _WIN32
        if (lib_) FreeLibrary(static_cast<HMODULE>(lib_));
#else
        if (lib_) dlclose(lib_);
#endif
    }

    LoadedPlugin(const LoadedPlugin&) = delete;
    LoadedPlugin& operator=(const LoadedPlugin&) = delete;

    PluginError init(const char* config) { return iface_.init(data_, config); }
    PluginError process(const float* in, float* out, uint32_t n) {
        return iface_.process(data_, in, out, n);
    }
    PluginInfo info() const { return iface_.get_info(data_); }

private:
    void* lib_ = nullptr;
    void* data_ = nullptr;
    PluginInterface iface_ = {};
};

int main() {
    try {
#ifdef _WIN32
        LoadedPlugin plugin("gain_plugin.dll");
#else
        LoadedPlugin plugin("./libgain_plugin.so");
#endif
        auto info = plugin.info();
        std::cout << "Loaded: " << info.name << " v"
                  << info.version_major << "." << info.version_minor << "\n";

        plugin.init("gain=2.5");

        float input[] = {1.0f, 2.0f, 3.0f, 4.0f};
        float output[4] = {};
        plugin.process(input, output, 4);

        for (int i = 0; i < 4; ++i)
            std::cout << input[i] << " * 2.5 = " << output[i] << "\n";

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
}
```

**Build:**
```bash
# Build plugin as shared library
g++ -std=c++20 -O2 -shared -fPIC -fvisibility=hidden -o libgain_plugin.so gain_plugin.cpp

# Build host
g++ -std=c++20 -O2 -o host host.cpp -ldl

./host  # Loads plugin, applies gain
```

The struct-of-function-pointers pattern gives you ABI stability, cross-compiler compatibility, and clean versioning. Real systems using this: VLC, OBS Studio, SQLite, and most audio plugin formats (VST, AU).'''),

    ("cpp_deep/pybind11_ffi", r'''How do I expose C++ code to Python using pybind11? Show practical patterns for functions, classes, and NumPy arrays.''', r'''<think>
pybind11 is the most popular C++/Python FFI library. Header-only, modern C++.
Key patterns: module definition, function binding, class binding, NumPy array buffers.
I should show: exposing functions, classes with constructors/methods, operator overloads,
and the critical buffer_info pattern for zero-copy NumPy integration.
Important: pybind11 handles reference counting, GIL, and type conversion automatically.
For performance-critical code: use py::array_t<T> for zero-copy NumPy access.
Let me write a complete module with multiple patterns.
Build with CMake and pybind11's cmake integration, or use setup.py.
Also mention py::gil_scoped_release for releasing the GIL during C++ computation.
</think>

pybind11 provides zero-overhead Python bindings for C++ with automatic type conversion and NumPy integration:

```cpp
// math_module.cpp — pybind11 module exposing C++ to Python
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>          // automatic std::vector, std::map conversion
#include <pybind11/numpy.h>        // NumPy array support
#include <pybind11/functional.h>   // std::function support

#include <vector>
#include <string>
#include <cmath>
#include <numeric>
#include <stdexcept>
#include <algorithm>

namespace py = pybind11;

// ============================================================
// Pattern 1: Free functions
// ============================================================
double euclidean_distance(double x1, double y1, double x2, double y2) {
    double dx = x2 - x1, dy = y2 - y1;
    return std::sqrt(dx * dx + dy * dy);
}

// ============================================================
// Pattern 2: Class with constructor, methods, properties
// ============================================================
class Matrix {
    std::vector<double> data_;
    size_t rows_, cols_;

public:
    Matrix(size_t rows, size_t cols)
        : data_(rows * cols, 0.0), rows_(rows), cols_(cols) {}

    // Element access
    double get(size_t r, size_t c) const {
        if (r >= rows_ || c >= cols_) throw std::out_of_range("index out of bounds");
        return data_[r * cols_ + c];
    }

    void set(size_t r, size_t c, double val) {
        if (r >= rows_ || c >= cols_) throw std::out_of_range("index out of bounds");
        data_[r * cols_ + c] = val;
    }

    // Properties
    size_t rows() const { return rows_; }
    size_t cols() const { return cols_; }
    size_t size() const { return data_.size(); }

    // Operations
    Matrix operator+(const Matrix& other) const {
        if (rows_ != other.rows_ || cols_ != other.cols_)
            throw std::invalid_argument("dimension mismatch");
        Matrix result(rows_, cols_);
        for (size_t i = 0; i < data_.size(); ++i)
            result.data_[i] = data_[i] + other.data_[i];
        return result;
    }

    double sum() const {
        return std::accumulate(data_.begin(), data_.end(), 0.0);
    }

    std::string repr() const {
        return "Matrix(" + std::to_string(rows_) + "x" + std::to_string(cols_) + ")";
    }

    // Expose raw buffer for NumPy zero-copy access
    const double* data() const { return data_.data(); }
    double* mutable_data() { return data_.data(); }
};

// ============================================================
// Pattern 3: NumPy array processing (zero-copy)
// ============================================================

// Process NumPy array in C++ — no data copying
py::array_t<double> normalize_array(py::array_t<double> input) {
    // Request buffer info (zero-copy view into NumPy data)
    auto buf = input.request();

    if (buf.ndim != 1)
        throw std::runtime_error("expected 1D array");

    auto* ptr = static_cast<double*>(buf.ptr);
    size_t n = buf.shape[0];

    // Allocate output
    auto result = py::array_t<double>(n);
    auto result_buf = result.request();
    auto* out = static_cast<double*>(result_buf.ptr);

    // Compute (release GIL for parallelism)
    double sum = 0;
    {
        py::gil_scoped_release release;  // allow other Python threads
        for (size_t i = 0; i < n; ++i) sum += ptr[i] * ptr[i];
        double norm = std::sqrt(sum);
        if (norm > 0) {
            for (size_t i = 0; i < n; ++i) out[i] = ptr[i] / norm;
        }
    }

    return result;
}

// In-place modification of NumPy array
void scale_inplace(py::array_t<double> arr, double factor) {
    auto buf = arr.mutable_unchecked<1>();  // 1D, mutable, no bounds checking
    py::gil_scoped_release release;
    for (py::ssize_t i = 0; i < buf.shape(0); ++i) {
        buf(i) *= factor;
    }
}

// ============================================================
// Pattern 4: Callbacks (Python callable from C++)
// ============================================================
double apply_twice(std::function<double(double)> fn, double x) {
    return fn(fn(x));
}

// ============================================================
// MODULE DEFINITION — binds everything to Python
// ============================================================
PYBIND11_MODULE(fastmath, m) {
    m.doc() = "Fast math utilities implemented in C++";

    // Functions
    m.def("euclidean_distance", &euclidean_distance,
          py::arg("x1"), py::arg("y1"), py::arg("x2"), py::arg("y2"),
          "Compute Euclidean distance between two 2D points");

    m.def("normalize_array", &normalize_array,
          py::arg("input"), "Normalize a 1D array to unit length");

    m.def("scale_inplace", &scale_inplace,
          py::arg("arr"), py::arg("factor"), "Scale array elements in-place");

    m.def("apply_twice", &apply_twice,
          py::arg("fn"), py::arg("x"), "Apply a callable twice: fn(fn(x))");

    // Class
    py::class_<Matrix>(m, "Matrix")
        .def(py::init<size_t, size_t>(), py::arg("rows"), py::arg("cols"))
        .def("get", &Matrix::get)
        .def("set", &Matrix::set)
        .def("sum", &Matrix::sum)
        .def_property_readonly("rows", &Matrix::rows)
        .def_property_readonly("cols", &Matrix::cols)
        .def("__repr__", &Matrix::repr)
        .def("__len__", &Matrix::size)
        .def(py::self + py::self)  // operator+
        // Expose as NumPy array (zero-copy view)
        .def("to_numpy", [](const Matrix& m) {
            return py::array_t<double>(
                {m.rows(), m.cols()},           // shape
                {m.cols() * sizeof(double),     // row stride
                 sizeof(double)},               // col stride
                m.data()                        // pointer (no copy!)
            );
        }, py::return_value_policy::reference_internal);
}
```

**CMakeLists.txt:**
```cmake
cmake_minimum_required(VERSION 3.14)
project(fastmath CXX)

find_package(pybind11 CONFIG REQUIRED)
# Or use FetchContent:
# include(FetchContent)
# FetchContent_Declare(pybind11 GIT_REPOSITORY https://github.com/pybind/pybind11 GIT_TAG v2.12)
# FetchContent_MakeAvailable(pybind11)

pybind11_add_module(fastmath math_module.cpp)
target_compile_features(fastmath PRIVATE cxx_std_20)
```

**Usage from Python:**
```python
import numpy as np
import fastmath

# Functions
print(fastmath.euclidean_distance(0, 0, 3, 4))  # 5.0

# NumPy integration (zero-copy)
arr = np.array([3.0, 4.0, 0.0])
normed = fastmath.normalize_array(arr)  # [0.6, 0.8, 0.0]
fastmath.scale_inplace(arr, 2.0)        # arr is now [6.0, 8.0, 0.0]

# Class
m = fastmath.Matrix(3, 3)
m.set(0, 0, 1.0)
print(m)            # Matrix(3x3)
print(m.to_numpy()) # NumPy view of the matrix data

# Callbacks
print(fastmath.apply_twice(lambda x: x * 2, 3.0))  # 12.0
```

Key patterns: use `py::array_t<T>` for zero-copy NumPy, release the GIL with `py::gil_scoped_release` for parallel C++ code, and use `py::return_value_policy::reference_internal` when returning views into C++ data.'''),

    ("cpp_deep/embedded_cpp_constraints", r'''How do I write C++ for embedded systems where exceptions and RTTI are disabled? What patterns replace them?''', r'''<think>
Embedded C++ typically uses -fno-exceptions -fno-rtti for code size and deterministic timing.
Without exceptions: use error codes, std::expected (C++23), or Result<T,E> types.
Without RTTI: no dynamic_cast, no typeid. Use enum-based type tags or CRTP for polymorphism.
No heap allocation in many cases: use stack allocation, static pools, placement new.
Other constraints: no STL containers (heap-based), no iostream (too heavy).
Replacements: etl::vector (fixed capacity), snprintf instead of iostream.
I should show practical patterns: error handling without exceptions, static polymorphism,
fixed-size containers, and no-allocation patterns.
Also mention -fno-threadsafe-statics to remove the mutex in static local initialization.
Important: C++17/20 features work fine without exceptions/RTTI (constexpr, structured bindings, etc.).
Let me write code that compiles with -fno-exceptions -fno-rtti.
</think>

Embedded C++ disables exceptions and RTTI for deterministic timing and smaller binaries. Here are the replacement patterns:

```cpp
// embedded_patterns.cpp
// Compile with: g++ -std=c++20 -O2 -fno-exceptions -fno-rtti -fno-threadsafe-statics
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <array>
#include <type_traits>
#include <utility>
#include <optional>
#include <new>       // placement new

// ============================================================
// Pattern 1: Error handling without exceptions
// ============================================================

enum class Error : uint8_t {
    Ok = 0,
    InvalidArg,
    Timeout,
    BufferFull,
    HardwareFault,
};

// Result type — like Rust's Result<T, E> or C++23 std::expected
template <typename T>
struct Result {
    T value;
    Error error;

    [[nodiscard]] bool ok() const { return error == Error::Ok; }
    [[nodiscard]] static Result success(T val) { return {val, Error::Ok}; }
    [[nodiscard]] static Result fail(Error e) { return {{}, e}; }
};

// Usage: return error codes, never throw
Result<uint16_t> read_adc(uint8_t channel) {
    if (channel > 7) return Result<uint16_t>::fail(Error::InvalidArg);
    // Simulate ADC read (real code would access hardware registers)
    volatile uint16_t* adc_reg = reinterpret_cast<volatile uint16_t*>(0x40012000);
    (void)adc_reg;  // suppress unused warning in demo
    uint16_t value = 2048;  // simulated 12-bit ADC value
    return Result<uint16_t>::success(value);
}

// ============================================================
// Pattern 2: Static polymorphism with CRTP (no RTTI, no virtual)
// ============================================================

// Base class template — no virtual functions, no vtable overhead
template <typename Derived>
class SensorBase {
public:
    // Static dispatch: resolved at compile time, zero overhead
    Error init() {
        return static_cast<Derived*>(this)->do_init();
    }

    Result<int32_t> read() {
        return static_cast<Derived*>(this)->do_read();
    }

    const char* name() const {
        return static_cast<const Derived*>(this)->do_name();
    }
};

class TemperatureSensor : public SensorBase<TemperatureSensor> {
    int32_t offset_ = 0;
public:
    Error do_init() {
        offset_ = -3;  // calibration offset
        return Error::Ok;
    }

    Result<int32_t> do_read() {
        return Result<int32_t>::success(2500 + offset_);  // 25.00°C
    }

    const char* do_name() const { return "TempSensor"; }
};

class PressureSensor : public SensorBase<PressureSensor> {
public:
    Error do_init() { return Error::Ok; }

    Result<int32_t> do_read() {
        return Result<int32_t>::success(101325);  // 1013.25 hPa
    }

    const char* do_name() const { return "PressureSensor"; }
};

// Generic function works with any sensor — no virtual dispatch
template <typename S>
void print_reading(SensorBase<S>& sensor) {
    auto result = sensor.read();
    if (result.ok()) {
        std::printf("%s: %ld\n", sensor.name(), static_cast<long>(result.value));
    } else {
        std::printf("%s: ERROR %d\n", sensor.name(), static_cast<int>(result.error));
    }
}

// ============================================================
// Pattern 3: Fixed-capacity container (no heap allocation)
// ============================================================

template <typename T, size_t Capacity>
class StaticVector {
    alignas(T) uint8_t storage_[Capacity * sizeof(T)];
    size_t size_ = 0;

    T* data() { return reinterpret_cast<T*>(storage_); }
    const T* data() const { return reinterpret_cast<const T*>(storage_); }

public:
    StaticVector() = default;

    ~StaticVector() {
        for (size_t i = 0; i < size_; ++i)
            data()[i].~T();
    }

    [[nodiscard]] bool push_back(const T& val) {
        if (size_ >= Capacity) return false;  // no exception — return false
        new (&data()[size_]) T(val);          // placement new
        ++size_;
        return true;
    }

    [[nodiscard]] size_t size() const { return size_; }
    [[nodiscard]] size_t capacity() const { return Capacity; }
    [[nodiscard]] bool full() const { return size_ >= Capacity; }
    [[nodiscard]] bool empty() const { return size_ == 0; }

    T& operator[](size_t i) { return data()[i]; }
    const T& operator[](size_t i) const { return data()[i]; }

    T* begin() { return data(); }
    T* end() { return data() + size_; }
    const T* begin() const { return data(); }
    const T* end() const { return data() + size_; }
};

// ============================================================
// Pattern 4: Enum-based type dispatch (replaces dynamic_cast)
// ============================================================

enum class MsgType : uint8_t { Heartbeat, Data, Command };

struct MessageHeader {
    MsgType type;
    uint8_t length;
};

struct HeartbeatMsg {
    MessageHeader header;
    uint32_t uptime_ms;
};

struct DataMsg {
    MessageHeader header;
    int16_t values[8];
};

void handle_message(const uint8_t* raw, size_t len) {
    if (len < sizeof(MessageHeader)) return;
    const auto* header = reinterpret_cast<const MessageHeader*>(raw);

    switch (header->type) {
    case MsgType::Heartbeat: {
        if (len < sizeof(HeartbeatMsg)) return;
        const auto* msg = reinterpret_cast<const HeartbeatMsg*>(raw);
        std::printf("Heartbeat: uptime=%lu ms\n",
                    static_cast<unsigned long>(msg->uptime_ms));
        break;
    }
    case MsgType::Data: {
        if (len < sizeof(DataMsg)) return;
        const auto* msg = reinterpret_cast<const DataMsg*>(raw);
        std::printf("Data: first=%d\n", msg->values[0]);
        break;
    }
    default:
        std::printf("Unknown message type %d\n", static_cast<int>(header->type));
    }
}

// ============================================================
// Pattern 5: Compile-time configuration (no runtime cost)
// ============================================================

struct BoardConfig {
    static constexpr uint32_t CLOCK_HZ = 168'000'000;
    static constexpr size_t MAX_SENSORS = 8;
    static constexpr size_t UART_BUFFER_SIZE = 256;
    static constexpr bool HAS_DISPLAY = false;
};

template <typename Config>
class System {
    StaticVector<int32_t, Config::MAX_SENSORS> readings_;

public:
    void update() {
        if constexpr (Config::HAS_DISPLAY) {
            // display code — compiled out entirely when false
            // display_update(readings_);
        }
    }

    [[nodiscard]] size_t sensor_count() const { return readings_.size(); }
};

int main() {
    // Error handling
    auto adc = read_adc(3);
    if (adc.ok()) std::printf("ADC: %u\n", adc.value);

    // CRTP sensors
    TemperatureSensor temp;
    PressureSensor pres;
    temp.init();
    pres.init();
    print_reading(temp);
    print_reading(pres);

    // Fixed-capacity container
    StaticVector<int32_t, 16> readings;
    readings.push_back(100);
    readings.push_back(200);
    for (auto val : readings) std::printf("reading: %ld\n", static_cast<long>(val));

    // System with compile-time config
    System<BoardConfig> sys;
    sys.update();
}
```

**Build:**
```bash
g++ -std=c++20 -O2 -fno-exceptions -fno-rtti -fno-threadsafe-statics \
    -Wall -Wextra -o embedded embedded_patterns.cpp
```

Key principles: return error codes instead of throwing, use CRTP for static polymorphism, use fixed-capacity containers on the stack, use `if constexpr` for compile-time feature flags, and use `std::printf` instead of `std::cout`.'''),

    ("cpp_deep/realtime_constraints", r'''How do I write C++ code for real-time systems where dynamic allocation and non-deterministic timing are forbidden?''', r'''<think>
Real-time C++ forbids: heap allocation (malloc/new), unbounded loops, syscalls that can block.
The key constraint: every operation must have bounded, deterministic worst-case execution time.
Patterns: pre-allocated memory pools, lock-free data structures, monotonic clock for timing.
std::pmr (polymorphic memory resources) from C++17 are designed exactly for this.
monotonic_buffer_resource: allocates from a pre-allocated buffer, never frees (fast, deterministic).
I should show: pmr containers, a fixed pool allocator, lock-free queue, and timing measurement.
No exceptions either (same as embedded), use error codes.
Important: avoid std::mutex in the real-time thread (priority inversion risk).
Use lock-free atomics or single-producer/single-consumer queues for thread communication.
Let me write a practical real-time audio processing example.
</think>

Real-time C++ requires deterministic timing: no allocation, no locks, no unbounded operations in the hot path:

```cpp
// realtime_patterns.cpp — Zero-allocation, deterministic-timing patterns
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory_resource>  // C++17 pmr
#include <new>
#include <thread>
#include <vector>

// ============================================================
// Pattern 1: Pre-allocated memory pool with std::pmr
// ============================================================
void pmr_realtime_demo() {
    // Allocate ALL memory upfront (non-real-time init phase)
    alignas(alignof(std::max_align_t)) std::array<std::byte, 65536> buffer;

    // monotonic_buffer_resource: O(1) allocation, never calls malloc
    std::pmr::monotonic_buffer_resource pool(buffer.data(), buffer.size(),
                                              std::pmr::null_memory_resource());

    // pmr::vector uses the pool — no heap allocation
    std::pmr::vector<float> samples(&pool);
    samples.reserve(1024);  // pre-reserve during init

    // Real-time section: push_back is O(1) if capacity is pre-reserved
    for (int i = 0; i < 512; ++i) {
        samples.push_back(static_cast<float>(i) * 0.001f);
    }

    std::printf("PMR samples: %zu (from stack buffer)\n", samples.size());
}

// ============================================================
// Pattern 2: Lock-free SPSC ring buffer
// (Single Producer, Single Consumer — no mutex needed)
// ============================================================
template <typename T, size_t Capacity>
class SPSCRingBuffer {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");
    static constexpr size_t MASK = Capacity - 1;

    std::array<T, Capacity> buffer_{};
    alignas(64) std::atomic<size_t> head_{0};  // separate cache lines
    alignas(64) std::atomic<size_t> tail_{0};  // to avoid false sharing

public:
    // Called by producer thread — lock-free, O(1)
    [[nodiscard]] bool try_push(const T& item) {
        size_t head = head_.load(std::memory_order_relaxed);
        size_t next = (head + 1) & MASK;
        if (next == tail_.load(std::memory_order_acquire)) return false; // full
        buffer_[head] = item;
        head_.store(next, std::memory_order_release);
        return true;
    }

    // Called by consumer thread — lock-free, O(1)
    [[nodiscard]] bool try_pop(T& item) {
        size_t tail = tail_.load(std::memory_order_relaxed);
        if (tail == head_.load(std::memory_order_acquire)) return false; // empty
        item = buffer_[tail];
        tail_.store((tail + 1) & MASK, std::memory_order_release);
        return true;
    }

    [[nodiscard]] bool empty() const {
        return head_.load(std::memory_order_acquire) ==
               tail_.load(std::memory_order_acquire);
    }
};

// ============================================================
// Pattern 3: Real-time audio processing (zero allocation)
// ============================================================
struct AudioFrame {
    static constexpr size_t BLOCK_SIZE = 256;
    std::array<float, BLOCK_SIZE> left;
    std::array<float, BLOCK_SIZE> right;
    uint64_t timestamp_ns;
};

class RealtimeAudioProcessor {
    // All state pre-allocated
    float gain_ = 1.0f;
    float prev_left_ = 0.0f;
    float prev_right_ = 0.0f;

    // Lowpass coefficient (pre-computed, not computed per-sample)
    float alpha_ = 0.1f;

public:
    // Called from real-time audio thread — MUST be deterministic
    // No allocation, no locks, no syscalls, no exceptions
    void process(AudioFrame& frame) noexcept {
        for (size_t i = 0; i < AudioFrame::BLOCK_SIZE; ++i) {
            // Simple lowpass filter (IIR)
            frame.left[i] = prev_left_ + alpha_ * (frame.left[i] * gain_ - prev_left_);
            frame.right[i] = prev_right_ + alpha_ * (frame.right[i] * gain_ - prev_right_);
            prev_left_ = frame.left[i];
            prev_right_ = frame.right[i];
        }
    }

    // Called from non-real-time thread (UI) — safe parameter update
    void set_gain(float g) noexcept { gain_ = g; }
    void set_cutoff(float normalized) noexcept { alpha_ = normalized; }
};

// ============================================================
// Pattern 4: Deterministic timing measurement
// ============================================================
class ScopedTimer {
    const char* label_;
    std::chrono::steady_clock::time_point start_;
    uint64_t deadline_ns_;

public:
    ScopedTimer(const char* label, uint64_t deadline_ns)
        : label_(label), start_(std::chrono::steady_clock::now()),
          deadline_ns_(deadline_ns) {}

    ~ScopedTimer() {
        auto end = std::chrono::steady_clock::now();
        uint64_t elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            end - start_).count();
        if (elapsed > deadline_ns_) {
            std::printf("DEADLINE MISS: %s took %lu ns (limit: %lu ns)\n",
                        label_, static_cast<unsigned long>(elapsed),
                        static_cast<unsigned long>(deadline_ns_));
        }
    }
};

// ============================================================
// Pattern 5: Object pool (fixed-size, no heap)
// ============================================================
template <typename T, size_t N>
class ObjectPool {
    union Slot {
        T object;
        size_t next_free;
        Slot() : next_free(0) {}
        ~Slot() {}
    };

    std::array<Slot, N> slots_;
    size_t free_head_ = 0;
    size_t count_ = 0;

public:
    ObjectPool() {
        for (size_t i = 0; i < N - 1; ++i) slots_[i].next_free = i + 1;
        slots_[N - 1].next_free = N;  // sentinel
    }

    template <typename... Args>
    T* allocate(Args&&... args) {
        if (free_head_ >= N) return nullptr;  // pool exhausted
        size_t idx = free_head_;
        free_head_ = slots_[idx].next_free;
        T* obj = new (&slots_[idx].object) T(std::forward<Args>(args)...);
        ++count_;
        return obj;
    }

    void deallocate(T* obj) {
        obj->~T();
        size_t idx = reinterpret_cast<Slot*>(obj) - slots_.data();
        reinterpret_cast<Slot*>(obj)->next_free = free_head_;
        free_head_ = idx;
        --count_;
    }

    [[nodiscard]] size_t available() const { return N - count_; }
};

int main() {
    // Pattern 1: PMR
    pmr_realtime_demo();

    // Pattern 2: Lock-free queue between threads
    SPSCRingBuffer<AudioFrame, 64> audio_queue;

    std::thread producer([&] {
        AudioFrame frame{};
        for (int i = 0; i < 32; ++i) {
            frame.left.fill(static_cast<float>(i) * 0.01f);
            frame.right.fill(static_cast<float>(i) * 0.01f);
            while (!audio_queue.try_push(frame)) { /* spin */ }
        }
    });

    std::thread consumer([&] {
        RealtimeAudioProcessor proc;
        AudioFrame frame;
        int processed = 0;
        while (processed < 32) {
            if (audio_queue.try_pop(frame)) {
                ScopedTimer timer("audio_process", 1'000'000); // 1ms deadline
                proc.process(frame);
                ++processed;
            }
        }
        std::printf("Processed %d audio frames\n", processed);
    });

    producer.join();
    consumer.join();

    // Pattern 5: Object pool
    struct Particle { float x, y, z; };
    ObjectPool<Particle, 1024> pool;
    auto* p = pool.allocate(1.0f, 2.0f, 3.0f);
    std::printf("Particle: (%.1f, %.1f, %.1f), pool available: %zu\n",
                p->x, p->y, p->z, pool.available());
    pool.deallocate(p);
}
```

**Build:**
```bash
g++ -std=c++20 -O2 -fno-exceptions -fno-rtti -o realtime realtime_patterns.cpp -pthread
```

Rules for real-time code: pre-allocate everything during init, use lock-free structures for inter-thread communication, measure timing with `steady_clock` and check deadlines, mark all hot-path functions `noexcept`, and never call `new`/`delete`/`malloc`/`free` in the real-time thread.'''),

    ("cpp_deep/ecs_game_engine", r'''How do I implement an Entity Component System (ECS) in C++ with cache-optimal iteration for a game engine?''', r'''<think>
ECS separates data (components) from behavior (systems) for cache-friendly iteration.
Key design: entities are just IDs, components are stored in contiguous arrays (SoA-style),
systems iterate over component arrays sequentially.
The archetype-based approach (used by Unity DOTS, flecs): entities with same component set
are stored together in the same array. This means iterating all entities with (Position, Velocity)
touches only contiguous memory — no cache misses.
Simpler approach: sparse set per component type. Each component type has its own dense array.
I'll implement a simple but correct ECS with:
- Entity IDs (just size_t)
- Component storage with dense arrays
- System that iterates matching entities
This demonstrates the cache-friendly iteration pattern.
Let me keep it practical and compilable, not a full engine.
</think>

Here is a minimal but cache-optimal ECS with dense component arrays and system iteration:

```cpp
// ecs.cpp — Entity Component System with cache-friendly iteration
#include <array>
#include <bitset>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <functional>
#include <memory>
#include <unordered_map>
#include <vector>

// ============================================================
// Core types
// ============================================================
using Entity = uint32_t;
constexpr size_t MAX_COMPONENTS = 32;
using ComponentMask = std::bitset<MAX_COMPONENTS>;

// Global component type ID counter
inline size_t next_component_id() {
    static size_t id = 0;
    return id++;
}

template <typename T>
size_t component_id() {
    static size_t id = next_component_id();
    return id;
}

// ============================================================
// Component Pool — dense array storage for one component type
// ============================================================
class IComponentPool {
public:
    virtual ~IComponentPool() = default;
    virtual void remove(Entity e) = 0;
    virtual bool has(Entity e) const = 0;
};

template <typename T>
class ComponentPool : public IComponentPool {
    // Dense array: components stored contiguously for cache-friendly iteration
    std::vector<T> dense_data_;
    std::vector<Entity> dense_to_entity_;

    // Sparse array: entity -> index in dense array
    std::unordered_map<Entity, size_t> entity_to_dense_;

public:
    T& add(Entity e, T component) {
        assert(!has(e) && "entity already has this component");
        size_t index = dense_data_.size();
        dense_data_.push_back(std::move(component));
        dense_to_entity_.push_back(e);
        entity_to_dense_[e] = index;
        return dense_data_.back();
    }

    T& get(Entity e) {
        return dense_data_[entity_to_dense_.at(e)];
    }

    const T& get(Entity e) const {
        return dense_data_[entity_to_dense_.at(e)];
    }

    bool has(Entity e) const override {
        return entity_to_dense_.count(e) > 0;
    }

    void remove(Entity e) override {
        if (!has(e)) return;
        size_t removed = entity_to_dense_[e];
        size_t last = dense_data_.size() - 1;

        if (removed != last) {
            // Swap-and-pop to maintain dense packing
            dense_data_[removed] = std::move(dense_data_[last]);
            dense_to_entity_[removed] = dense_to_entity_[last];
            entity_to_dense_[dense_to_entity_[removed]] = removed;
        }

        dense_data_.pop_back();
        dense_to_entity_.pop_back();
        entity_to_dense_.erase(e);
    }

    // Direct iteration over dense array — cache-optimal
    size_t size() const { return dense_data_.size(); }
    T* data() { return dense_data_.data(); }
    Entity entity_at(size_t i) const { return dense_to_entity_[i]; }
};

// ============================================================
// World — manages entities and component pools
// ============================================================
class World {
    Entity next_entity_ = 0;
    std::vector<ComponentMask> masks_;
    std::array<std::unique_ptr<IComponentPool>, MAX_COMPONENTS> pools_;

    template <typename T>
    ComponentPool<T>& get_pool() {
        size_t id = component_id<T>();
        if (!pools_[id]) {
            pools_[id] = std::make_unique<ComponentPool<T>>();
        }
        return static_cast<ComponentPool<T>&>(*pools_[id]);
    }

public:
    Entity create() {
        Entity e = next_entity_++;
        if (e >= masks_.size()) masks_.resize(e + 1);
        masks_[e].reset();
        return e;
    }

    void destroy(Entity e) {
        for (size_t i = 0; i < MAX_COMPONENTS; ++i) {
            if (masks_[e].test(i) && pools_[i]) {
                pools_[i]->remove(e);
            }
        }
        masks_[e].reset();
    }

    template <typename T>
    T& add(Entity e, T component = {}) {
        masks_[e].set(component_id<T>());
        return get_pool<T>().add(e, std::move(component));
    }

    template <typename T>
    T& get(Entity e) { return get_pool<T>().get(e); }

    template <typename T>
    bool has(Entity e) const {
        return masks_[e].test(component_id<T>());
    }

    // ============================================================
    // System iteration — iterate all entities matching component set
    // ============================================================

    // Iterate entities with ALL of the specified components
    // Uses the smallest pool as the driving iterator (fewer cache misses)
    template <typename... Cs, typename Fn>
    void each(Fn&& fn) {
        // Get all required pools
        auto& first_pool = get_pool<std::tuple_element_t<0, std::tuple<Cs...>>>();

        // Build required mask
        ComponentMask required;
        (required.set(component_id<Cs>()), ...);

        // Iterate the first pool's dense array
        for (size_t i = 0; i < first_pool.size(); ++i) {
            Entity e = first_pool.entity_at(i);
            if ((masks_[e] & required) == required) {
                fn(e, get_pool<Cs>().get(e)...);
            }
        }
    }

    size_t entity_count() const { return next_entity_; }
};

// ============================================================
// Game components
// ============================================================
struct Position { float x = 0, y = 0, z = 0; };
struct Velocity { float vx = 0, vy = 0, vz = 0; };
struct Health   { float hp = 100, max_hp = 100; };
struct Sprite   { uint32_t texture_id = 0; int layer = 0; };
struct Gravity  { float force = -9.81f; };

// ============================================================
// Game systems (pure functions operating on components)
// ============================================================
void movement_system(World& world, float dt) {
    world.each<Position, Velocity>([dt](Entity, Position& pos, Velocity& vel) {
        pos.x += vel.vx * dt;
        pos.y += vel.vy * dt;
        pos.z += vel.vz * dt;
    });
}

void gravity_system(World& world, float dt) {
    world.each<Velocity, Gravity>([dt](Entity, Velocity& vel, Gravity& g) {
        vel.vy += g.force * dt;
    });
}

void health_regen_system(World& world, float dt) {
    world.each<Health>([dt](Entity, Health& h) {
        if (h.hp < h.max_hp) {
            h.hp = std::min(h.hp + 1.0f * dt, h.max_hp);
        }
    });
}

int main() {
    World world;

    // Create entities with different component combinations
    constexpr int NUM_ENTITIES = 100'000;

    for (int i = 0; i < NUM_ENTITIES; ++i) {
        Entity e = world.create();
        world.add<Position>(e, {static_cast<float>(i), 0.0f, 0.0f});
        world.add<Velocity>(e, {1.0f, 0.0f, 0.0f});

        if (i % 2 == 0) world.add<Gravity>(e);      // 50% have gravity
        if (i % 3 == 0) world.add<Health>(e);        // 33% have health
        if (i % 4 == 0) world.add<Sprite>(e, {42, 0}); // 25% have sprites
    }

    // Simulate 100 frames
    float dt = 1.0f / 60.0f;
    auto start = std::chrono::high_resolution_clock::now();

    for (int frame = 0; frame < 100; ++frame) {
        gravity_system(world, dt);
        movement_system(world, dt);
        health_regen_system(world, dt);
    }

    auto end = std::chrono::high_resolution_clock::now();
    double ms = std::chrono::duration<double, std::milli>(end - start).count();

    std::printf("Simulated %d entities x 100 frames in %.1f ms (%.2f ms/frame)\n",
                NUM_ENTITIES, ms, ms / 100.0);

    // Verify a sample entity
    Entity e0 = 0;
    auto& pos = world.get<Position>(e0);
    std::printf("Entity 0 position: (%.2f, %.2f, %.2f)\n", pos.x, pos.y, pos.z);
}
```

**Build:**
```bash
g++ -std=c++20 -O3 -march=native -o ecs ecs.cpp
```

The key performance insight: components of the same type are stored in dense contiguous arrays, so `movement_system` iterating 100K `Position` and `Velocity` components touches sequential memory. This gives near-optimal cache utilization, similar to SoA layout but with the flexibility to add/remove components per entity.'''),

    ("cpp_deep/http_server_sockets", r'''How do I build a simple HTTP server from raw sockets in C++? Show a minimal but working implementation.''', r'''<think>
A minimal HTTP server needs: socket creation, bind, listen, accept, read request, write response.
On Linux/macOS: POSIX sockets (sys/socket.h, netinet/in.h).
On Windows: Winsock (winsock2.h, ws2tcpip.h).
I'll write a cross-platform version using preprocessor for the platform differences.
The minimal flow: parse the first line of the HTTP request, route it, send a response.
For simplicity: single-threaded, blocking I/O, HTTP/1.0 (close after each response).
Parse: METHOD PATH HTTP/1.x\r\n, then headers until \r\n\r\n, then body.
I should show proper cleanup, SO_REUSEADDR, and graceful shutdown.
This is educational — production code would use async I/O or a library.
Let me keep it focused and compilable.
</think>

Here is a minimal but working HTTP server built from raw sockets:

```cpp
// http_server.cpp — Minimal HTTP server from raw POSIX/Winsock sockets
#include <cstring>
#include <cstdio>
#include <string>
#include <string_view>
#include <functional>
#include <unordered_map>
#include <sstream>
#include <csignal>

#ifdef _WIN32
    #ifndef WIN32_LEAN_AND_MEAN
    #define WIN32_LEAN_AND_MEAN
    #endif
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib")
    using socket_t = SOCKET;
    constexpr socket_t INVALID_SOCK = INVALID_SOCKET;
    inline int close_socket(socket_t s) { return closesocket(s); }
    inline void init_sockets() {
        WSADATA wsa; WSAStartup(MAKEWORD(2, 2), &wsa);
    }
    inline void cleanup_sockets() { WSACleanup(); }
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    using socket_t = int;
    constexpr socket_t INVALID_SOCK = -1;
    inline int close_socket(socket_t s) { return close(s); }
    inline void init_sockets() {}
    inline void cleanup_sockets() {}
#endif

// ============================================================
// HTTP types
// ============================================================
struct HttpRequest {
    std::string method;
    std::string path;
    std::unordered_map<std::string, std::string> headers;
    std::string body;
};

struct HttpResponse {
    int status = 200;
    std::string status_text = "OK";
    std::unordered_map<std::string, std::string> headers;
    std::string body;

    static HttpResponse ok(const std::string& body, const std::string& content_type = "text/html") {
        HttpResponse resp;
        resp.body = body;
        resp.headers["Content-Type"] = content_type;
        resp.headers["Content-Length"] = std::to_string(body.size());
        return resp;
    }

    static HttpResponse not_found() {
        HttpResponse resp;
        resp.status = 404;
        resp.status_text = "Not Found";
        resp.body = "<h1>404 Not Found</h1>";
        resp.headers["Content-Type"] = "text/html";
        resp.headers["Content-Length"] = std::to_string(resp.body.size());
        return resp;
    }

    std::string serialize() const {
        std::ostringstream oss;
        oss << "HTTP/1.1 " << status << " " << status_text << "\r\n";
        for (const auto& [key, val] : headers) {
            oss << key << ": " << val << "\r\n";
        }
        oss << "Connection: close\r\n";
        oss << "\r\n";
        oss << body;
        return oss.str();
    }
};

// ============================================================
// HTTP parser (minimal — handles GET and POST)
// ============================================================
HttpRequest parse_request(const std::string& raw) {
    HttpRequest req;
    std::istringstream stream(raw);
    std::string line;

    // Request line: GET /path HTTP/1.1
    if (std::getline(stream, line)) {
        // Remove trailing \r
        if (!line.empty() && line.back() == '\r') line.pop_back();
        size_t sp1 = line.find(' ');
        size_t sp2 = line.find(' ', sp1 + 1);
        if (sp1 != std::string::npos && sp2 != std::string::npos) {
            req.method = line.substr(0, sp1);
            req.path = line.substr(sp1 + 1, sp2 - sp1 - 1);
        }
    }

    // Headers
    while (std::getline(stream, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) break;  // empty line = end of headers
        size_t colon = line.find(':');
        if (colon != std::string::npos) {
            std::string key = line.substr(0, colon);
            std::string val = line.substr(colon + 1);
            // Trim leading space
            if (!val.empty() && val[0] == ' ') val = val.substr(1);
            req.headers[key] = val;
        }
    }

    // Body (remainder)
    std::ostringstream body_stream;
    body_stream << stream.rdbuf();
    req.body = body_stream.str();

    return req;
}

// ============================================================
// HTTP Server
// ============================================================
using Handler = std::function<HttpResponse(const HttpRequest&)>;

class HttpServer {
    socket_t server_sock_ = INVALID_SOCK;
    uint16_t port_;
    std::unordered_map<std::string, Handler> routes_;
    bool running_ = false;

public:
    explicit HttpServer(uint16_t port) : port_(port) {}

    void route(const std::string& path, Handler handler) {
        routes_[path] = std::move(handler);
    }

    bool start() {
        init_sockets();

        server_sock_ = socket(AF_INET, SOCK_STREAM, 0);
        if (server_sock_ == INVALID_SOCK) {
            std::perror("socket");
            return false;
        }

        // Allow port reuse (avoid "address already in use")
        int opt = 1;
        setsockopt(server_sock_, SOL_SOCKET, SO_REUSEADDR,
                   reinterpret_cast<const char*>(&opt), sizeof(opt));

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = INADDR_ANY;
        addr.sin_port = htons(port_);

        if (bind(server_sock_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
            std::perror("bind");
            return false;
        }

        if (listen(server_sock_, 10) < 0) {
            std::perror("listen");
            return false;
        }

        std::printf("Listening on http://localhost:%u\n", port_);
        running_ = true;

        while (running_) {
            sockaddr_in client_addr{};
            socklen_t client_len = sizeof(client_addr);
            socket_t client = accept(server_sock_,
                reinterpret_cast<sockaddr*>(&client_addr), &client_len);

            if (client == INVALID_SOCK) continue;

            handle_client(client);
            close_socket(client);
        }

        close_socket(server_sock_);
        cleanup_sockets();
        return true;
    }

    void stop() { running_ = false; }

private:
    void handle_client(socket_t client) {
        // Read request (up to 8KB — sufficient for most requests)
        char buf[8192] = {};
        int n = recv(client, buf, sizeof(buf) - 1, 0);
        if (n <= 0) return;

        auto req = parse_request(std::string(buf, n));
        std::printf("%s %s\n", req.method.c_str(), req.path.c_str());

        // Route to handler
        HttpResponse resp;
        auto it = routes_.find(req.path);
        if (it != routes_.end()) {
            resp = it->second(req);
        } else {
            resp = HttpResponse::not_found();
        }

        // Send response
        std::string raw = resp.serialize();
        send(client, raw.c_str(), static_cast<int>(raw.size()), 0);
    }
};

// ============================================================
// Main — define routes and start server
// ============================================================
int main() {
    HttpServer server(8080);

    server.route("/", [](const HttpRequest&) {
        return HttpResponse::ok(
            "<html><body>"
            "<h1>Hello from C++ HTTP Server</h1>"
            "<p>Built from raw sockets.</p>"
            "<a href=\"/api/status\">Status API</a>"
            "</body></html>"
        );
    });

    server.route("/api/status", [](const HttpRequest&) {
        return HttpResponse::ok(
            R"({"status":"ok","server":"cpp-http","version":"1.0"})",
            "application/json"
        );
    });

    server.route("/api/echo", [](const HttpRequest& req) {
        std::string body = "Method: " + req.method + "\n"
                         + "Path: " + req.path + "\n"
                         + "Body: " + req.body + "\n";
        return HttpResponse::ok(body, "text/plain");
    });

    server.start();
}
```

**Build and test:**
```bash
g++ -std=c++20 -O2 -o http_server http_server.cpp -pthread
./http_server &
curl http://localhost:8080/
curl http://localhost:8080/api/status
curl -X POST -d "hello" http://localhost:8080/api/echo
```

This is single-threaded, blocking I/O — suitable for learning and small tools. For production, use `epoll`/`kqueue`/`IOCP` for async I/O, or a library like Boost.Beast or cpp-httplib.'''),

    ("cpp_deep/recursive_descent_json_parser", r'''How do I write a JSON parser in C++ using recursive descent? Show a complete implementation that handles objects, arrays, strings, numbers, booleans, and null.''', r'''<think>
A recursive descent parser has one function per grammar rule.
JSON grammar: value = object | array | string | number | "true" | "false" | "null"
object = '{' (string ':' value (',' string ':' value)*)? '}'
array = '[' (value (',' value)*)? ']'
I need a JsonValue type that can hold any JSON value — use std::variant or a tagged union.
For simplicity, I'll use a class with a variant.
The parser needs: skip whitespace, peek char, consume char, parse_value, parse_object, etc.
Error handling: throw on invalid input (or return optional in no-exception mode).
Let me write a complete, compilable parser with a test.
I'll represent JSON as a tree of JsonValue nodes.
</think>

Here is a complete recursive descent JSON parser with a clean value type:

```cpp
// json_parser.cpp — Recursive descent JSON parser
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

// ============================================================
// JSON Value type
// ============================================================
class JsonValue;
using JsonObject = std::map<std::string, JsonValue>;
using JsonArray = std::vector<JsonValue>;
using JsonNull = std::monostate;

class JsonValue {
public:
    using Variant = std::variant<JsonNull, bool, double, std::string, JsonArray, JsonObject>;

    JsonValue() : data_(JsonNull{}) {}
    JsonValue(std::nullptr_t) : data_(JsonNull{}) {}
    JsonValue(bool b) : data_(b) {}
    JsonValue(double d) : data_(d) {}
    JsonValue(int i) : data_(static_cast<double>(i)) {}
    JsonValue(const std::string& s) : data_(s) {}
    JsonValue(std::string&& s) : data_(std::move(s)) {}
    JsonValue(const char* s) : data_(std::string(s)) {}
    JsonValue(JsonArray arr) : data_(std::move(arr)) {}
    JsonValue(JsonObject obj) : data_(std::move(obj)) {}

    bool is_null()   const { return std::holds_alternative<JsonNull>(data_); }
    bool is_bool()   const { return std::holds_alternative<bool>(data_); }
    bool is_number() const { return std::holds_alternative<double>(data_); }
    bool is_string() const { return std::holds_alternative<std::string>(data_); }
    bool is_array()  const { return std::holds_alternative<JsonArray>(data_); }
    bool is_object() const { return std::holds_alternative<JsonObject>(data_); }

    bool               as_bool()   const { return std::get<bool>(data_); }
    double             as_number() const { return std::get<double>(data_); }
    const std::string& as_string() const { return std::get<std::string>(data_); }
    const JsonArray&   as_array()  const { return std::get<JsonArray>(data_); }
    const JsonObject&  as_object() const { return std::get<JsonObject>(data_); }

    // Convenience accessors
    const JsonValue& operator[](size_t i) const { return as_array().at(i); }
    const JsonValue& operator[](const std::string& key) const { return as_object().at(key); }

    // Stringify
    std::string dump(int indent = -1) const {
        std::ostringstream oss;
        dump_impl(oss, indent, 0);
        return oss.str();
    }

private:
    Variant data_;

    void dump_impl(std::ostringstream& oss, int indent, int depth) const {
        std::string pad = (indent >= 0) ? std::string(depth * indent, ' ') : "";
        std::string pad_inner = (indent >= 0) ? std::string((depth + 1) * indent, ' ') : "";
        std::string nl = (indent >= 0) ? "\n" : "";
        std::string sep = (indent >= 0) ? ", " : ",";

        if (is_null()) {
            oss << "null";
        } else if (is_bool()) {
            oss << (as_bool() ? "true" : "false");
        } else if (is_number()) {
            double d = as_number();
            if (d == static_cast<int64_t>(d) && std::abs(d) < 1e15)
                oss << static_cast<int64_t>(d);
            else
                oss << d;
        } else if (is_string()) {
            oss << '"';
            for (char c : as_string()) {
                switch (c) {
                    case '"':  oss << "\\\""; break;
                    case '\\': oss << "\\\\"; break;
                    case '\n': oss << "\\n";  break;
                    case '\t': oss << "\\t";  break;
                    case '\r': oss << "\\r";  break;
                    default:   oss << c;
                }
            }
            oss << '"';
        } else if (is_array()) {
            const auto& arr = as_array();
            if (arr.empty()) { oss << "[]"; return; }
            oss << "[" << nl;
            for (size_t i = 0; i < arr.size(); ++i) {
                oss << pad_inner;
                arr[i].dump_impl(oss, indent, depth + 1);
                if (i + 1 < arr.size()) oss << ",";
                oss << nl;
            }
            oss << pad << "]";
        } else if (is_object()) {
            const auto& obj = as_object();
            if (obj.empty()) { oss << "{}"; return; }
            oss << "{" << nl;
            size_t i = 0;
            for (const auto& [key, val] : obj) {
                oss << pad_inner << '"' << key << "\": ";
                val.dump_impl(oss, indent, depth + 1);
                if (++i < obj.size()) oss << ",";
                oss << nl;
            }
            oss << pad << "}";
        }
    }
};

// ============================================================
// Recursive descent parser
// ============================================================
class JsonParser {
    std::string_view input_;
    size_t pos_ = 0;

public:
    explicit JsonParser(std::string_view input) : input_(input) {}

    JsonValue parse() {
        skip_ws();
        auto val = parse_value();
        skip_ws();
        if (pos_ < input_.size()) {
            error("unexpected trailing content");
        }
        return val;
    }

private:
    // Grammar: value = object | array | string | number | true | false | null
    JsonValue parse_value() {
        skip_ws();
        if (pos_ >= input_.size()) error("unexpected end of input");

        char c = peek();
        switch (c) {
            case '{': return parse_object();
            case '[': return parse_array();
            case '"': return parse_string();
            case 't': return parse_literal("true", true);
            case 'f': return parse_literal("false", false);
            case 'n': return parse_literal("null", nullptr);
            default:
                if (c == '-' || (c >= '0' && c <= '9'))
                    return parse_number();
                error("unexpected character '" + std::string(1, c) + "'");
        }
        return {}; // unreachable
    }

    // object = '{' (string ':' value (',' string ':' value)*)? '}'
    JsonValue parse_object() {
        consume('{');
        JsonObject obj;
        skip_ws();
        if (peek() == '}') { advance(); return obj; }

        while (true) {
            skip_ws();
            if (peek() != '"') error("expected string key in object");
            std::string key = parse_string().as_string();
            skip_ws();
            consume(':');
            skip_ws();
            obj[std::move(key)] = parse_value();
            skip_ws();
            if (peek() == ',') { advance(); continue; }
            break;
        }
        consume('}');
        return obj;
    }

    // array = '[' (value (',' value)*)? ']'
    JsonValue parse_array() {
        consume('[');
        JsonArray arr;
        skip_ws();
        if (peek() == ']') { advance(); return arr; }

        while (true) {
            skip_ws();
            arr.push_back(parse_value());
            skip_ws();
            if (peek() == ',') { advance(); continue; }
            break;
        }
        consume(']');
        return arr;
    }

    // string = '"' chars '"'
    JsonValue parse_string() {
        consume('"');
        std::string result;
        while (pos_ < input_.size() && input_[pos_] != '"') {
            if (input_[pos_] == '\\') {
                advance();
                if (pos_ >= input_.size()) error("unexpected end in string escape");
                switch (input_[pos_]) {
                    case '"':  result += '"';  break;
                    case '\\': result += '\\'; break;
                    case '/':  result += '/';  break;
                    case 'n':  result += '\n'; break;
                    case 't':  result += '\t'; break;
                    case 'r':  result += '\r'; break;
                    case 'b':  result += '\b'; break;
                    case 'f':  result += '\f'; break;
                    case 'u': {
                        // Unicode escape: \uXXXX
                        if (pos_ + 4 >= input_.size()) error("incomplete unicode escape");
                        std::string hex(input_.substr(pos_ + 1, 4));
                        unsigned long cp = std::strtoul(hex.c_str(), nullptr, 16);
                        // Simple UTF-8 encoding (BMP only)
                        if (cp < 0x80) {
                            result += static_cast<char>(cp);
                        } else if (cp < 0x800) {
                            result += static_cast<char>(0xC0 | (cp >> 6));
                            result += static_cast<char>(0x80 | (cp & 0x3F));
                        } else {
                            result += static_cast<char>(0xE0 | (cp >> 12));
                            result += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
                            result += static_cast<char>(0x80 | (cp & 0x3F));
                        }
                        pos_ += 4;
                        break;
                    }
                    default: error("invalid escape sequence");
                }
            } else {
                result += input_[pos_];
            }
            advance();
        }
        consume('"');
        return result;
    }

    // number = [-] digits [. digits] [(e|E) [+-] digits]
    JsonValue parse_number() {
        size_t start = pos_;
        if (peek() == '-') advance();
        if (!is_digit(peek())) error("expected digit");
        while (pos_ < input_.size() && is_digit(input_[pos_])) advance();
        if (pos_ < input_.size() && input_[pos_] == '.') {
            advance();
            if (!is_digit(peek())) error("expected digit after decimal point");
            while (pos_ < input_.size() && is_digit(input_[pos_])) advance();
        }
        if (pos_ < input_.size() && (input_[pos_] == 'e' || input_[pos_] == 'E')) {
            advance();
            if (pos_ < input_.size() && (input_[pos_] == '+' || input_[pos_] == '-')) advance();
            if (!is_digit(peek())) error("expected digit in exponent");
            while (pos_ < input_.size() && is_digit(input_[pos_])) advance();
        }
        std::string num_str(input_.substr(start, pos_ - start));
        return std::strtod(num_str.c_str(), nullptr);
    }

    template <typename T>
    JsonValue parse_literal(const char* expected, T value) {
        size_t len = std::strlen(expected);
        if (input_.substr(pos_, len) != expected)
            error(std::string("expected '") + expected + "'");
        pos_ += len;
        return JsonValue(value);
    }

    // Helpers
    char peek() const {
        if (pos_ >= input_.size()) error("unexpected end of input");
        return input_[pos_];
    }
    void advance() { ++pos_; }
    void consume(char expected) {
        if (pos_ >= input_.size() || input_[pos_] != expected)
            error(std::string("expected '") + expected + "'");
        advance();
    }
    void skip_ws() {
        while (pos_ < input_.size() &&
               (input_[pos_] == ' ' || input_[pos_] == '\t' ||
                input_[pos_] == '\n' || input_[pos_] == '\r'))
            ++pos_;
    }
    static bool is_digit(char c) { return c >= '0' && c <= '9'; }

    [[noreturn]] void error(const std::string& msg) const {
        throw std::runtime_error("JSON parse error at position " +
                                 std::to_string(pos_) + ": " + msg);
    }
};

// Convenience function
JsonValue json_parse(std::string_view input) {
    return JsonParser(input).parse();
}

// ============================================================
// Test
// ============================================================
int main() {
    const char* input = R"({
        "name": "HiveAI",
        "version": 2.5,
        "features": ["training", "inference", "eval"],
        "config": {
            "lora_rank": 16,
            "learning_rate": 0.0001,
            "use_kl": true,
            "notes": null
        },
        "tags": [1, 2, 3],
        "escaped": "line1\nline2\ttab"
    })";

    try {
        auto val = json_parse(input);

        std::cout << "Parsed successfully!\n\n";
        std::cout << "Pretty print:\n" << val.dump(2) << "\n\n";

        // Access nested values
        std::cout << "name: " << val["name"].as_string() << "\n";
        std::cout << "version: " << val["version"].as_number() << "\n";
        std::cout << "features[1]: " << val["features"][1].as_string() << "\n";
        std::cout << "lora_rank: " << val["config"]["lora_rank"].as_number() << "\n";
        std::cout << "use_kl: " << (val["config"]["use_kl"].as_bool() ? "true" : "false") << "\n";
        std::cout << "notes is null: " << (val["config"]["notes"].is_null() ? "yes" : "no") << "\n";

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
}
```

**Build:**
```bash
g++ -std=c++20 -O2 -o json_parser json_parser.cpp
./json_parser
```

Each JSON grammar rule maps directly to a `parse_*` method. The parser consumes one character at a time, dispatches based on the next character, and recurses for nested structures. The `JsonValue` type uses `std::variant` to hold any JSON type with zero heap overhead for scalars.'''),

    ("cpp_deep/cli_argument_parser", r'''How do I build a command-line argument parser from scratch in C++? Show a clean, reusable implementation.''', r'''<think>
A CLI parser needs to handle: positional args, named options (--flag, -f), values (--name=val or --name val),
boolean flags, required vs optional, help text generation.
I'll design a fluent API: parser.add("--output", "-o").help("output file").required()
The parser stores option definitions, then processes argv against them.
Key features: short and long forms, default values, type conversion, auto-generated help.
I should use modern C++ patterns: string_view for parsing, optional for results.
Let me write a self-contained, header-only-style parser.
</think>

Here is a clean, reusable CLI argument parser with a fluent API:

```cpp
// argparse.cpp — Command-line argument parser from scratch
#include <algorithm>
#include <functional>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include <iomanip>

class ArgParser {
public:
    struct Option {
        std::string long_name;     // --output
        std::string short_name;    // -o
        std::string help;          // description for help text
        std::string default_val;   // default if not provided
        std::string metavar;       // placeholder in help: --output FILE
        bool is_flag = false;      // true = boolean, no value
        bool required = false;     // true = error if missing
    };

private:
    std::string prog_name_;
    std::string description_;
    std::vector<Option> options_;
    std::vector<std::string> positional_names_;
    std::vector<std::string> positional_help_;

    // Parsed results
    std::map<std::string, std::string> values_;
    std::vector<std::string> positional_values_;

    // Lookup: short name -> long name
    std::map<std::string, std::string> short_to_long_;

public:
    explicit ArgParser(std::string prog, std::string desc = "")
        : prog_name_(std::move(prog)), description_(std::move(desc)) {}

    // Fluent API for adding options
    class OptionBuilder {
        ArgParser& parser_;
        size_t index_;
    public:
        OptionBuilder(ArgParser& p, size_t i) : parser_(p), index_(i) {}
        OptionBuilder& help(std::string h) { opt().help = std::move(h); return *this; }
        OptionBuilder& default_value(std::string d) { opt().default_val = std::move(d); return *this; }
        OptionBuilder& metavar(std::string m) { opt().metavar = std::move(m); return *this; }
        OptionBuilder& required() { opt().required = true; return *this; }
        OptionBuilder& flag() { opt().is_flag = true; return *this; }
    private:
        Option& opt() { return parser_.options_[index_]; }
    };

    OptionBuilder add(std::string long_name, std::string short_name = "") {
        Option opt;
        opt.long_name = std::move(long_name);
        opt.short_name = std::move(short_name);
        if (!opt.short_name.empty()) {
            short_to_long_[opt.short_name] = opt.long_name;
        }
        options_.push_back(std::move(opt));
        return OptionBuilder(*this, options_.size() - 1);
    }

    void add_positional(std::string name, std::string help_text = "") {
        positional_names_.push_back(std::move(name));
        positional_help_.push_back(std::move(help_text));
    }

    // Parse argv
    bool parse(int argc, char* argv[]) {
        // Apply defaults
        for (const auto& opt : options_) {
            if (opt.is_flag) {
                values_[opt.long_name] = "false";
            } else if (!opt.default_val.empty()) {
                values_[opt.long_name] = opt.default_val;
            }
        }

        size_t pos_idx = 0;

        for (int i = 1; i < argc; ++i) {
            std::string_view arg(argv[i]);

            if (arg == "--help" || arg == "-h") {
                print_help();
                return false;
            }

            if (arg.starts_with("--")) {
                // Long option: --key=value or --key value or --flag
                auto eq = arg.find('=');
                std::string key;
                std::string val;

                if (eq != std::string_view::npos) {
                    key = std::string(arg.substr(0, eq));
                    val = std::string(arg.substr(eq + 1));
                } else {
                    key = std::string(arg);
                    auto* opt = find_option(key);
                    if (opt && opt->is_flag) {
                        val = "true";
                    } else if (i + 1 < argc) {
                        val = argv[++i];
                    } else {
                        std::cerr << "Error: " << key << " requires a value\n";
                        return false;
                    }
                }
                values_[key] = val;

            } else if (arg.starts_with("-") && arg.size() > 1) {
                // Short option: -o value or -f (flag)
                std::string short_key(arg);
                auto it = short_to_long_.find(short_key);
                if (it == short_to_long_.end()) {
                    std::cerr << "Error: unknown option " << arg << "\n";
                    return false;
                }
                const std::string& long_key = it->second;
                auto* opt = find_option(long_key);

                if (opt && opt->is_flag) {
                    values_[long_key] = "true";
                } else if (i + 1 < argc) {
                    values_[long_key] = argv[++i];
                } else {
                    std::cerr << "Error: " << arg << " requires a value\n";
                    return false;
                }

            } else {
                // Positional argument
                positional_values_.push_back(std::string(arg));
                ++pos_idx;
            }
        }

        // Check required options
        for (const auto& opt : options_) {
            if (opt.required && values_.find(opt.long_name) == values_.end()) {
                std::cerr << "Error: " << opt.long_name << " is required\n";
                return false;
            }
        }

        return true;
    }

    // Accessors
    std::string get(const std::string& name) const {
        auto it = values_.find(name);
        if (it != values_.end()) return it->second;
        // Try as positional
        for (size_t i = 0; i < positional_names_.size(); ++i) {
            if (positional_names_[i] == name && i < positional_values_.size())
                return positional_values_[i];
        }
        return "";
    }

    template <typename T>
    T get_as(const std::string& name) const {
        std::string val = get(name);
        if (val.empty()) return T{};
        std::istringstream iss(val);
        T result;
        iss >> result;
        return result;
    }

    bool get_flag(const std::string& name) const {
        return get(name) == "true";
    }

    bool has(const std::string& name) const {
        return values_.count(name) > 0;
    }

    const std::vector<std::string>& positional() const { return positional_values_; }

    void print_help() const {
        std::cout << "Usage: " << prog_name_;
        for (const auto& name : positional_names_) {
            std::cout << " <" << name << ">";
        }
        std::cout << " [options]\n";

        if (!description_.empty()) {
            std::cout << "\n" << description_ << "\n";
        }

        if (!positional_names_.empty()) {
            std::cout << "\nPositional arguments:\n";
            for (size_t i = 0; i < positional_names_.size(); ++i) {
                std::cout << "  " << std::setw(20) << std::left << positional_names_[i];
                if (i < positional_help_.size()) std::cout << positional_help_[i];
                std::cout << "\n";
            }
        }

        std::cout << "\nOptions:\n";
        std::cout << "  " << std::setw(20) << std::left << "-h, --help" << "Show this help\n";
        for (const auto& opt : options_) {
            std::string names;
            if (!opt.short_name.empty()) names = opt.short_name + ", ";
            names += opt.long_name;
            if (!opt.is_flag) {
                names += " " + (opt.metavar.empty() ? "VALUE" : opt.metavar);
            }

            std::cout << "  " << std::setw(20) << std::left << names << opt.help;
            if (opt.required) std::cout << " (required)";
            if (!opt.default_val.empty()) std::cout << " [default: " << opt.default_val << "]";
            std::cout << "\n";
        }
    }

private:
    Option* find_option(const std::string& long_name) {
        for (auto& opt : options_) {
            if (opt.long_name == long_name) return &opt;
        }
        return nullptr;
    }
};

// ============================================================
// Example usage
// ============================================================
int main(int argc, char* argv[]) {
    ArgParser parser("image_convert", "Convert images between formats");

    parser.add_positional("input", "Input image file");
    parser.add_positional("output", "Output image file");

    parser.add("--format", "-f")
        .help("Output format")
        .metavar("FMT")
        .default_value("png");

    parser.add("--quality", "-q")
        .help("Compression quality (1-100)")
        .metavar("N")
        .default_value("90");

    parser.add("--width", "-w")
        .help("Resize width in pixels")
        .metavar("PX");

    parser.add("--verbose", "-v")
        .help("Enable verbose output")
        .flag();

    parser.add("--output-dir", "-d")
        .help("Output directory")
        .metavar("DIR")
        .required();

    if (!parser.parse(argc, argv)) {
        return 1;
    }

    // Use parsed values
    auto positional = parser.positional();
    if (positional.size() >= 2) {
        std::cout << "Input:   " << positional[0] << "\n";
        std::cout << "Output:  " << positional[1] << "\n";
    }

    std::cout << "Format:  " << parser.get("--format") << "\n";
    std::cout << "Quality: " << parser.get_as<int>("--quality") << "\n";
    std::cout << "Verbose: " << (parser.get_flag("--verbose") ? "yes" : "no") << "\n";
    std::cout << "OutDir:  " << parser.get("--output-dir") << "\n";

    if (parser.has("--width")) {
        std::cout << "Width:   " << parser.get_as<int>("--width") << "px\n";
    }
}
```

**Build and test:**
```bash
g++ -std=c++20 -O2 -o imgconv argparse.cpp
./imgconv photo.jpg result.png --output-dir /tmp -f jpeg -q 85 -v
./imgconv --help
```

The fluent builder pattern (`add("--flag").help("...").required()`) makes option definitions readable. The parser handles `--key=value`, `--key value`, `-k value`, boolean flags, positional args, auto-generated help, and required option validation.'''),

    ("cpp_deep/catch2_unit_testing", r'''How do I write unit tests in C++ using the Catch2 framework? Show common patterns including TEST_CASE, SECTION, REQUIRE, and generators.''', r'''<think>
Catch2 is the most popular C++ testing framework — header-only (v2) or CMake-integrated (v3).
Key features: TEST_CASE, SECTION (nested test contexts), REQUIRE/CHECK, Matchers, Generators.
SECTION is unique to Catch2 — it lets you share setup code and branch into sub-tests.
Each SECTION re-runs the TEST_CASE from the top, so each section gets fresh setup.
Generators (GENERATE) provide parametric testing similar to property-based testing.
I should show: basic tests, sections, matchers, BDD-style, and generators.
Catch2 v3 requires linking, v2 is single-header. I'll target v3 patterns (current).
REQUIRE aborts the test, CHECK continues — show both.
Let me write a comprehensive test file for a small library.
</think>

Here is a comprehensive Catch2 v3 test file demonstrating all the key patterns:

```cpp
// test_calculator.cpp — Catch2 v3 testing patterns
#define CATCH_CONFIG_MAIN  // generates main() automatically
#include <catch2/catch_test_macros.hpp>
#include <catch2/catch_approx.hpp>
#include <catch2/matchers/catch_matchers_string.hpp>
#include <catch2/matchers/catch_matchers_vector.hpp>
#include <catch2/generators/catch_generators.hpp>
#include <catch2/generators/catch_generators_range.hpp>

#include <vector>
#include <string>
#include <stdexcept>
#include <cmath>
#include <algorithm>
#include <numeric>

// ============================================================
// Code under test
// ============================================================
class Calculator {
public:
    double add(double a, double b) const { return a + b; }
    double subtract(double a, double b) const { return a - b; }
    double multiply(double a, double b) const { return a * b; }

    double divide(double a, double b) const {
        if (b == 0.0) throw std::domain_error("division by zero");
        return a / b;
    }

    double factorial(int n) const {
        if (n < 0) throw std::invalid_argument("negative factorial");
        double result = 1.0;
        for (int i = 2; i <= n; ++i) result *= i;
        return result;
    }
};

class StringUtils {
public:
    static std::string to_upper(std::string s) {
        std::transform(s.begin(), s.end(), s.begin(), ::toupper);
        return s;
    }

    static std::vector<std::string> split(const std::string& s, char delim) {
        std::vector<std::string> parts;
        std::istringstream iss(s);
        std::string token;
        while (std::getline(iss, token, delim)) {
            if (!token.empty()) parts.push_back(token);
        }
        return parts;
    }

    static std::string join(const std::vector<std::string>& parts, const std::string& sep) {
        if (parts.empty()) return "";
        std::string result = parts[0];
        for (size_t i = 1; i < parts.size(); ++i) {
            result += sep + parts[i];
        }
        return result;
    }
};

// ============================================================
// Pattern 1: Basic TEST_CASE with REQUIRE and CHECK
// ============================================================
TEST_CASE("Calculator basic operations", "[calculator][basic]") {
    Calculator calc;

    // REQUIRE: stops test on failure (assertion)
    REQUIRE(calc.add(2, 3) == 5);
    REQUIRE(calc.subtract(10, 4) == 6);
    REQUIRE(calc.multiply(3, 7) == 21);

    // CHECK: reports failure but continues (soft assertion)
    CHECK(calc.add(0, 0) == 0);
    CHECK(calc.add(-1, 1) == 0);
    CHECK(calc.multiply(0, 1000) == 0);
}

// ============================================================
// Pattern 2: SECTION — shared setup, branching test paths
// Each SECTION re-executes the TEST_CASE from the top
// ============================================================
TEST_CASE("Calculator divide", "[calculator][divide]") {
    Calculator calc;  // fresh for each SECTION

    SECTION("normal division") {
        REQUIRE(calc.divide(10, 2) == 5.0);
        REQUIRE(calc.divide(7, 2) == 3.5);
    }

    SECTION("division by zero throws") {
        REQUIRE_THROWS_AS(calc.divide(1, 0), std::domain_error);
        REQUIRE_THROWS_WITH(calc.divide(1, 0), "division by zero");
    }

    SECTION("negative numbers") {
        REQUIRE(calc.divide(-10, 2) == -5.0);
        REQUIRE(calc.divide(-10, -2) == 5.0);
    }
}

// ============================================================
// Pattern 3: Floating point comparison with Approx
// ============================================================
TEST_CASE("Floating point precision", "[calculator][float]") {
    Calculator calc;

    // NEVER compare floats with ==
    // BAD:  REQUIRE(calc.divide(1, 3) == 0.333333);
    // GOOD: use Catch::Approx with configurable epsilon
    REQUIRE(calc.divide(1, 3) == Catch::Approx(0.33333).epsilon(0.001));
    REQUIRE(calc.divide(22, 7) == Catch::Approx(3.14286).margin(0.001));

    // Approx works with standard math
    REQUIRE(std::sqrt(2.0) == Catch::Approx(1.41421356).epsilon(1e-5));
}

// ============================================================
// Pattern 4: Exception testing
// ============================================================
TEST_CASE("Calculator error handling", "[calculator][errors]") {
    Calculator calc;

    REQUIRE_THROWS(calc.divide(1, 0));
    REQUIRE_THROWS_AS(calc.factorial(-1), std::invalid_argument);
    REQUIRE_NOTHROW(calc.factorial(0));
    REQUIRE_NOTHROW(calc.factorial(10));
}

// ============================================================
// Pattern 5: Matchers — expressive assertions
// ============================================================
TEST_CASE("String operations with matchers", "[string][matchers]") {
    using Catch::Matchers::Equals;
    using Catch::Matchers::ContainsSubstring;
    using Catch::Matchers::StartsWith;
    using Catch::Matchers::EndsWith;

    REQUIRE_THAT(StringUtils::to_upper("hello"), Equals("HELLO"));
    REQUIRE_THAT(StringUtils::to_upper("Hello World"),
                 ContainsSubstring("WORLD"));
    REQUIRE_THAT(StringUtils::to_upper("test"), StartsWith("T"));
}

TEST_CASE("Vector matchers", "[string][matchers]") {
    using Catch::Matchers::Contains;
    using Catch::Matchers::SizeIs;

    auto parts = StringUtils::split("a,b,c", ',');
    REQUIRE_THAT(parts, SizeIs(3));
    REQUIRE_THAT(parts, Contains(std::string("b")));
}

// ============================================================
// Pattern 6: Generators — parameterized tests
// ============================================================
TEST_CASE("Factorial with generators", "[calculator][generator]") {
    Calculator calc;

    // GENERATE creates multiple test runs with different values
    auto [input, expected] = GENERATE(table<int, double>({
        {0, 1.0},
        {1, 1.0},
        {2, 2.0},
        {3, 6.0},
        {4, 24.0},
        {5, 120.0},
        {10, 3628800.0},
    }));

    CAPTURE(input);  // print input value on failure
    REQUIRE(calc.factorial(input) == expected);
}

TEST_CASE("Addition is commutative", "[calculator][property]") {
    Calculator calc;

    // Generate random-ish pairs to test commutativity
    auto a = GENERATE(take(10, random(-1000.0, 1000.0)));
    auto b = GENERATE(take(10, random(-1000.0, 1000.0)));

    CAPTURE(a, b);
    REQUIRE(calc.add(a, b) == Catch::Approx(calc.add(b, a)));
}

// ============================================================
// Pattern 7: BDD-style (Scenario / Given / When / Then)
// ============================================================
SCENARIO("Splitting and joining strings", "[string][bdd]") {
    GIVEN("a comma-separated string") {
        std::string input = "one,two,three";

        WHEN("split by comma") {
            auto parts = StringUtils::split(input, ',');

            THEN("it produces three parts") {
                REQUIRE(parts.size() == 3);
                REQUIRE(parts[0] == "one");
                REQUIRE(parts[1] == "two");
                REQUIRE(parts[2] == "three");
            }

            AND_WHEN("joined back with comma") {
                auto result = StringUtils::join(parts, ",");

                THEN("it equals the original") {
                    REQUIRE(result == input);
                }
            }
        }
    }

    GIVEN("an empty string") {
        std::string input;

        WHEN("split") {
            auto parts = StringUtils::split(input, ',');

            THEN("result is empty") {
                REQUIRE(parts.empty());
            }
        }
    }
}

// ============================================================
// Pattern 8: Nested sections for matrix testing
// ============================================================
TEST_CASE("Calculator operations maintain properties", "[calculator][properties]") {
    Calculator calc;

    SECTION("identity elements") {
        double x = 42.0;
        REQUIRE(calc.add(x, 0) == x);       // additive identity
        REQUIRE(calc.multiply(x, 1) == x);   // multiplicative identity
    }

    SECTION("inverse operations") {
        double x = 42.0;

        SECTION("add then subtract") {
            REQUIRE(calc.subtract(calc.add(x, 10), 10) == Catch::Approx(x));
        }

        SECTION("multiply then divide") {
            REQUIRE(calc.divide(calc.multiply(x, 3), 3) == Catch::Approx(x));
        }
    }
}
```

**CMakeLists.txt:**
```cmake
cmake_minimum_required(VERSION 3.14)
project(tests CXX)

include(FetchContent)
FetchContent_Declare(
    Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG v3.5.2
)
FetchContent_MakeAvailable(Catch2)

add_executable(tests test_calculator.cpp)
target_compile_features(tests PRIVATE cxx_std_20)
target_link_libraries(tests PRIVATE Catch2::Catch2WithMain)

# CTest integration
include(CTest)
include(Catch)
catch_discover_tests(tests)
```

**Build and run:**
```bash
cmake -B build && cmake --build build
./build/tests                        # run all tests
./build/tests "[calculator]"         # run tests tagged [calculator]
./build/tests -s                     # show successful tests too
./build/tests --list-tests           # list all test names
```

Key patterns: `SECTION` for shared setup with branching, `Catch::Approx` for floats, `GENERATE` for parameterized tests, `REQUIRE_THROWS_AS` for exception testing, and tags (`[tag]`) for selective test running.'''),

    ("cpp_deep/mocking_virtual_interfaces", r'''How do I use virtual interfaces for mocking in C++ unit tests? Show the dependency injection pattern for testable code.''', r'''<think>
Mocking in C++ typically uses virtual interfaces (unlike languages with reflection-based mocking).
The pattern: define an interface (pure virtual class), have the production code depend on the interface,
then provide a mock implementation in tests.
This is dependency injection (DI) via constructor or method parameters.
I'll show: interface definition, production class using the interface, mock for testing,
and the actual test verifying behavior.
For a manual mock: override virtual methods, record calls, return canned values.
There are frameworks (GoogleMock/gmock) but manual mocks are often clearer for teaching.
I should show both the manual mock pattern and mention gmock.
Key: the production code never knows it's talking to a mock vs real implementation.
</think>

Virtual interfaces enable dependency injection for testable, mockable C++ code:

```cpp
// testable_service.cpp — Dependency injection + mocking pattern
#include <cassert>
#include <functional>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

// ============================================================
// Step 1: Define interfaces (pure virtual abstract classes)
// ============================================================

class IDatabase {
public:
    virtual ~IDatabase() = default;
    virtual bool connect(const std::string& connection_string) = 0;
    virtual std::vector<std::string> query(const std::string& sql) = 0;
    virtual bool execute(const std::string& sql) = 0;
    virtual void disconnect() = 0;
};

class ILogger {
public:
    virtual ~ILogger() = default;
    virtual void info(const std::string& msg) = 0;
    virtual void error(const std::string& msg) = 0;
};

class INotifier {
public:
    virtual ~INotifier() = default;
    virtual bool send(const std::string& to, const std::string& message) = 0;
};

// ============================================================
// Step 2: Production code depends on interfaces (not implementations)
// ============================================================

class UserService {
    IDatabase& db_;
    ILogger& logger_;
    INotifier& notifier_;

public:
    // Constructor injection — interfaces passed in, not created internally
    UserService(IDatabase& db, ILogger& logger, INotifier& notifier)
        : db_(db), logger_(logger), notifier_(notifier) {}

    bool create_user(const std::string& name, const std::string& email) {
        logger_.info("Creating user: " + name);

        // Check if user exists
        auto results = db_.query("SELECT id FROM users WHERE email='" + email + "'");
        if (!results.empty()) {
            logger_.error("User already exists: " + email);
            return false;
        }

        // Insert user
        bool ok = db_.execute("INSERT INTO users (name, email) VALUES ('" +
                              name + "', '" + email + "')");
        if (!ok) {
            logger_.error("Failed to insert user: " + name);
            return false;
        }

        // Send welcome notification
        notifier_.send(email, "Welcome, " + name + "!");
        logger_.info("User created: " + name);
        return true;
    }

    std::vector<std::string> list_users() {
        return db_.query("SELECT name FROM users");
    }
};

// ============================================================
// Step 3: Mock implementations for testing
// ============================================================

class MockDatabase : public IDatabase {
public:
    // Track calls for verification
    int connect_count = 0;
    int query_count = 0;
    int execute_count = 0;
    std::string last_query;
    std::string last_execute;

    // Configurable behavior
    bool connect_result = true;
    bool execute_result = true;
    std::vector<std::string> query_result;

    bool connect(const std::string&) override {
        ++connect_count;
        return connect_result;
    }

    std::vector<std::string> query(const std::string& sql) override {
        ++query_count;
        last_query = sql;
        return query_result;
    }

    bool execute(const std::string& sql) override {
        ++execute_count;
        last_execute = sql;
        return execute_result;
    }

    void disconnect() override {}
};

class MockLogger : public ILogger {
public:
    std::vector<std::string> info_messages;
    std::vector<std::string> error_messages;

    void info(const std::string& msg) override {
        info_messages.push_back(msg);
    }

    void error(const std::string& msg) override {
        error_messages.push_back(msg);
    }
};

class MockNotifier : public INotifier {
public:
    int send_count = 0;
    std::string last_to;
    std::string last_message;
    bool send_result = true;

    bool send(const std::string& to, const std::string& message) override {
        ++send_count;
        last_to = to;
        last_message = message;
        return send_result;
    }
};

// ============================================================
// Step 4: Tests using mocks
// ============================================================

void test_create_user_success() {
    // Arrange
    MockDatabase db;
    MockLogger logger;
    MockNotifier notifier;
    db.query_result = {};       // no existing user
    db.execute_result = true;    // insert succeeds

    UserService service(db, logger, notifier);

    // Act
    bool result = service.create_user("Alice", "alice@example.com");

    // Assert
    assert(result == true);
    assert(db.query_count == 1);       // checked for existing user
    assert(db.execute_count == 1);     // inserted the user
    assert(notifier.send_count == 1);  // sent welcome email
    assert(notifier.last_to == "alice@example.com");
    assert(logger.error_messages.empty());
    assert(logger.info_messages.size() == 2);  // "Creating" + "created"
    std::cout << "PASS: test_create_user_success\n";
}

void test_create_user_already_exists() {
    // Arrange
    MockDatabase db;
    MockLogger logger;
    MockNotifier notifier;
    db.query_result = {"existing_user_id"};  // user already exists

    UserService service(db, logger, notifier);

    // Act
    bool result = service.create_user("Alice", "alice@example.com");

    // Assert
    assert(result == false);
    assert(db.execute_count == 0);     // never tried to insert
    assert(notifier.send_count == 0);  // never sent notification
    assert(logger.error_messages.size() == 1);
    std::cout << "PASS: test_create_user_already_exists\n";
}

void test_create_user_db_failure() {
    // Arrange
    MockDatabase db;
    MockLogger logger;
    MockNotifier notifier;
    db.query_result = {};          // no existing user
    db.execute_result = false;     // INSERT fails

    UserService service(db, logger, notifier);

    // Act
    bool result = service.create_user("Alice", "alice@example.com");

    // Assert
    assert(result == false);
    assert(db.execute_count == 1);     // tried to insert
    assert(notifier.send_count == 0);  // no notification on failure
    assert(logger.error_messages.size() == 1);
    std::cout << "PASS: test_create_user_db_failure\n";
}

void test_list_users() {
    MockDatabase db;
    MockLogger logger;
    MockNotifier notifier;
    db.query_result = {"Alice", "Bob", "Charlie"};

    UserService service(db, logger, notifier);
    auto users = service.list_users();

    assert(users.size() == 3);
    assert(users[0] == "Alice");
    assert(db.query_count == 1);
    std::cout << "PASS: test_list_users\n";
}

// ============================================================
// Step 5: Real implementations (used in production)
// ============================================================

class ConsoleLogger : public ILogger {
public:
    void info(const std::string& msg) override {
        std::cout << "[INFO] " << msg << "\n";
    }
    void error(const std::string& msg) override {
        std::cerr << "[ERROR] " << msg << "\n";
    }
};

// Real DB and notifier would connect to actual services...

int main() {
    // Run tests with mocks
    test_create_user_success();
    test_create_user_already_exists();
    test_create_user_db_failure();
    test_list_users();

    std::cout << "\nAll tests passed!\n";

    // In production:
    // RealDatabase db;
    // ConsoleLogger logger;
    // EmailNotifier notifier;
    // UserService service(db, logger, notifier);
}
```

**Build:**
```bash
g++ -std=c++20 -O2 -o test_service testable_service.cpp
./test_service
```

The pattern: production code takes interfaces by reference in its constructor (dependency injection). Tests create mock objects with configurable behavior and call-tracking. Each test arranges the mock state, calls the code under test, then asserts on both the return value and the mock's recorded interactions. This approach has zero runtime overhead in production (virtual dispatch is one indirection) and makes every dependency explicit and testable.'''),

    ("cpp_deep/cmake_modern_patterns", r'''Show me modern CMake patterns: target-based linking, generator expressions, presets, and FetchContent for dependencies.''', r'''<think>
Modern CMake means: everything is target-based (no global variables),
PRIVATE/PUBLIC/INTERFACE for transitive properties, generator expressions for conditional logic,
CMakePresets.json for reproducible builds, FetchContent for dependency management.
Anti-patterns to avoid: include_directories(), link_libraries() (global), CMAKE_CXX_FLAGS (global).
I should show a complete project structure with multiple targets, proper visibility,
generator expressions, and FetchContent for a dependency.
Also show CMakePresets.json for common build configurations.
This is more of a CMake file than C++ code, but it's critical for real-world C++ projects.
Let me write a realistic project layout.
</think>

Here is a modern CMake project demonstrating target-based design, generator expressions, presets, and dependency management:

```cpp
// src/core/engine.hpp
#pragma once
#include <string>
#include <vector>

namespace myapp {

class Engine {
public:
    Engine();
    void add_module(std::string name);
    [[nodiscard]] std::vector<std::string> modules() const;
    [[nodiscard]] std::string version() const;
private:
    std::vector<std::string> modules_;
};

}  // namespace myapp
```

```cpp
// src/core/engine.cpp
#include "engine.hpp"

namespace myapp {

Engine::Engine() = default;

void Engine::add_module(std::string name) {
    modules_.push_back(std::move(name));
}

std::vector<std::string> Engine::modules() const { return modules_; }
std::string Engine::version() const { return "1.0.0"; }

}  // namespace myapp
```

```cpp
// src/app/main.cpp
#include "engine.hpp"
#include <fmt/core.h>
#include <iostream>

int main() {
    myapp::Engine engine;
    engine.add_module("graphics");
    engine.add_module("audio");

    fmt::print("Engine v{}\n", engine.version());
    for (const auto& mod : engine.modules()) {
        fmt::print("  Module: {}\n", mod);
    }
}
```

```cpp
// tests/test_engine.cpp
#define CATCH_CONFIG_MAIN
#include <catch2/catch_test_macros.hpp>
#include "engine.hpp"

TEST_CASE("Engine module management", "[engine]") {
    myapp::Engine engine;

    SECTION("starts empty") {
        REQUIRE(engine.modules().empty());
    }

    SECTION("add modules") {
        engine.add_module("net");
        engine.add_module("physics");
        REQUIRE(engine.modules().size() == 2);
    }

    SECTION("version") {
        REQUIRE(engine.version() == "1.0.0");
    }
}
```

**Root CMakeLists.txt:**
```cmake
# CMakeLists.txt — Modern CMake patterns
cmake_minimum_required(VERSION 3.21)
project(myapp
    VERSION 1.0.0
    LANGUAGES CXX
    DESCRIPTION "Modern CMake example"
)

# ============================================================
# Project-wide settings (target-based, not global)
# ============================================================
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)  # for clangd/IDEs

# ============================================================
# FetchContent — download dependencies at configure time
# ============================================================
include(FetchContent)

FetchContent_Declare(
    fmt
    GIT_REPOSITORY https://github.com/fmtlib/fmt.git
    GIT_TAG 10.2.1
)

FetchContent_Declare(
    Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG v3.5.2
)

FetchContent_MakeAvailable(fmt)

# Only fetch test deps if testing is enabled
option(MYAPP_BUILD_TESTS "Build tests" ON)
if(MYAPP_BUILD_TESTS)
    FetchContent_MakeAvailable(Catch2)
endif()

# ============================================================
# Core library target
# ============================================================
add_library(myapp_core
    src/core/engine.cpp
)

# PUBLIC: consumers of myapp_core also get these settings
# PRIVATE: only myapp_core itself uses these
target_include_directories(myapp_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src/core>
        $<INSTALL_INTERFACE:include>
)

target_compile_features(myapp_core PUBLIC cxx_std_20)

# ============================================================
# Generator expressions — conditional compilation
# ============================================================
target_compile_options(myapp_core PRIVATE
    # Warnings: different flags per compiler
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic -Wshadow>
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /permissive->

    # Debug-only: sanitizers
    $<$<AND:$<CONFIG:Debug>,$<NOT:$<CXX_COMPILER_ID:MSVC>>>:
        -fsanitize=address,undefined -fno-omit-frame-pointer>

    # Release: optimize
    $<$<CONFIG:Release>:-O3>
)

target_link_options(myapp_core PRIVATE
    $<$<AND:$<CONFIG:Debug>,$<NOT:$<CXX_COMPILER_ID:MSVC>>>:
        -fsanitize=address,undefined>
)

# ============================================================
# Application target
# ============================================================
add_executable(myapp src/app/main.cpp)

target_link_libraries(myapp
    PRIVATE
        myapp_core  # transitively gets include dirs + compile features
        fmt::fmt    # FetchContent target
)

# ============================================================
# Tests (optional)
# ============================================================
if(MYAPP_BUILD_TESTS)
    enable_testing()

    add_executable(myapp_tests tests/test_engine.cpp)
    target_link_libraries(myapp_tests
        PRIVATE
            myapp_core
            Catch2::Catch2WithMain
    )

    include(CTest)
    include(Catch)
    catch_discover_tests(myapp_tests)
endif()

# ============================================================
# LTO for Release builds
# ============================================================
include(CheckIPOSupported)
check_ipo_supported(RESULT lto_supported)
if(lto_supported)
    set_target_properties(myapp myapp_core PROPERTIES
        INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE
    )
endif()

# ============================================================
# Install rules
# ============================================================
install(TARGETS myapp RUNTIME DESTINATION bin)
install(TARGETS myapp_core
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)
install(FILES src/core/engine.hpp DESTINATION include/myapp)
```

**CMakePresets.json — reproducible builds:**
```json
{
    "version": 6,
    "configurePresets": [
        {
            "name": "default",
            "hidden": true,
            "generator": "Ninja",
            "binaryDir": "${sourceDir}/build/${presetName}",
            "cacheVariables": {
                "CMAKE_EXPORT_COMPILE_COMMANDS": "ON"
            }
        },
        {
            "name": "debug",
            "inherits": "default",
            "displayName": "Debug",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Debug",
                "MYAPP_BUILD_TESTS": "ON"
            }
        },
        {
            "name": "release",
            "inherits": "default",
            "displayName": "Release",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Release",
                "MYAPP_BUILD_TESTS": "OFF"
            }
        },
        {
            "name": "ci",
            "inherits": "debug",
            "displayName": "CI",
            "cacheVariables": {
                "CMAKE_CXX_COMPILER": "g++"
            }
        }
    ],
    "buildPresets": [
        { "name": "debug",   "configurePreset": "debug" },
        { "name": "release", "configurePreset": "release" },
        { "name": "ci",      "configurePreset": "ci" }
    ],
    "testPresets": [
        {
            "name": "ci",
            "configurePreset": "ci",
            "output": { "outputOnFailure": true }
        }
    ]
}
```

**Build commands:**
```bash
# Using presets (recommended)
cmake --preset debug
cmake --build --preset debug
ctest --preset ci

# Traditional
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

Key principles: every property is on a target (never `include_directories()` or `add_definitions()` globally), use `PUBLIC`/`PRIVATE`/`INTERFACE` for transitive propagation, use generator expressions for per-compiler and per-config logic, and use `FetchContent` to eliminate manual dependency management.'''),
]
