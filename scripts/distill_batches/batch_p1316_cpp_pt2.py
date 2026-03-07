"""C++ training pairs (part 2): coroutines, modules, TMP, design patterns, algorithms."""

PAIRS = [
    (
        "cpp/coroutines-co-await-co-yield",
        r'''How do C++20 coroutines work? Show a generator using co_yield.''',
        r'''<think>
C++20 coroutines use co_await, co_yield, and co_return to suspend and resume execution.
A coroutine needs a promise_type that defines how the coroutine behaves.
The generator pattern uses co_yield to lazily produce values on demand.
I need to show the promise_type, the Generator wrapper, and the iterator interface.
The coroutine frame is heap-allocated by default; the compiler may elide this.
I should keep the example practical — a simple range generator is clear and useful.
</think>

C++20 coroutines let you write functions that can suspend and resume. Here's a lazy generator using `co_yield`:

```cpp
#include <coroutine>
#include <iostream>
#include <optional>

template <typename T>
struct Generator {
    struct promise_type {
        T current_value;

        Generator get_return_object() {
            return Generator{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        std::suspend_always yield_value(T value) {
            current_value = std::move(value);
            return {};
        }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    std::coroutine_handle<promise_type> handle;

    explicit Generator(std::coroutine_handle<promise_type> h) : handle(h) {}
    ~Generator() { if (handle) handle.destroy(); }

    // Move-only
    Generator(const Generator&) = delete;
    Generator(Generator&& other) noexcept : handle(std::exchange(other.handle, {})) {}

    std::optional<T> next() {
        if (!handle || handle.done()) return std::nullopt;
        handle.resume();
        if (handle.done()) return std::nullopt;
        return handle.promise().current_value;
    }
};

Generator<int> range(int start, int end) {
    for (int i = start; i < end; ++i) {
        co_yield i;
    }
}

int main() {
    auto gen = range(1, 6);
    while (auto val = gen.next()) {
        std::cout << *val << " ";  // 1 2 3 4 5
    }
}
```

Key points:
- **`promise_type`** controls coroutine lifecycle (suspend, yield, return)
- **`co_yield value`** suspends the coroutine and makes `value` available to the caller
- **`std::suspend_always`** means the coroutine starts suspended (lazy)
- The coroutine frame must be explicitly destroyed in the destructor
- Coroutines are move-only — copying a coroutine handle would cause double-destroy'''
    ),
    (
        "cpp/modules-basics",
        r'''What are C++20 modules and how do I create one? Show an example replacing a traditional header.''',
        r'''<think>
C++20 modules replace the #include preprocessor model with a proper module system.
Modules avoid repeated parsing of headers, macro leakage, and include-order issues.
A module interface unit uses `export module` and `export` on declarations.
A module implementation unit uses `module` without `export`.
Compiler support varies — MSVC is most mature, GCC/Clang catching up.
I should show a simple module interface and consumer to illustrate the basics.
</think>

C++20 modules replace `#include` with a compiled, encapsulated unit. No more header guards, no macro leakage, and faster compilation.

**Module interface unit** (`math_utils.cppm` or `.ixx` on MSVC):
```cpp
export module math_utils;

// Only exported symbols are visible to importers
export namespace math {

constexpr double pi = 3.14159265358979323846;

double circle_area(double radius) {
    return pi * radius * radius;
}

template <typename T>
T clamp(T value, T lo, T hi) {
    return (value < lo) ? lo : (value > hi) ? hi : value;
}

}  // namespace math

// Non-exported — internal to this module
int internal_helper() { return 42; }
```

**Consumer** (`main.cpp`):
```cpp
import math_utils;
#include <iostream>

int main() {
    std::cout << math::circle_area(5.0) << "\n";
    std::cout << math::clamp(15, 0, 10) << "\n";

    // internal_helper();  // ERROR: not exported
}
```

**Module implementation unit** (optional, `math_utils_impl.cpp`):
```cpp
module math_utils;  // no 'export' keyword

// Can define non-exported helpers or split implementation
int internal_helper() { return 42; }
```

**Building** (MSVC example):
```bash
cl /std:c++20 /c /interface math_utils.cppm
cl /std:c++20 main.cpp math_utils.obj
```

Key differences from headers:
- **No include guards needed** — modules are only compiled once
- **No macro leakage** — `#define` inside a module doesn't affect importers
- **Explicit exports** — only `export`-marked declarations are visible
- **Order-independent** — `import` doesn't depend on textual inclusion order
- **`import std;`** — C++23 adds standard library modules for even faster builds'''
    ),
    (
        "cpp/template-metaprogramming-fibonacci",
        r'''Show compile-time Fibonacci using template metaprogramming in C++. Compare the old-style TMP approach with modern constexpr.''',
        r'''<think>
Classic TMP uses recursive template specialization to compute values at compile time.
Fibonacci is the canonical example — base cases 0 and 1, recursive case F(N) = F(N-1) + F(N-2).
Modern C++ (17+) makes this much simpler with constexpr and if constexpr.
I should show both approaches to highlight how the language evolved.
The old approach uses struct templates with a static value member.
static_assert can verify the result is truly compile-time in both cases.
</think>

Two approaches — classic TMP (C++11) vs modern `constexpr` (C++17+):

**Classic template metaprogramming:**
```cpp
// Recursive case
template <int N>
struct Fibonacci {
    static constexpr long long value = Fibonacci<N-1>::value + Fibonacci<N-2>::value;
};

// Base cases (template specialization)
template <> struct Fibonacci<0> { static constexpr long long value = 0; };
template <> struct Fibonacci<1> { static constexpr long long value = 1; };

static_assert(Fibonacci<10>::value == 55);
static_assert(Fibonacci<20>::value == 6765);
```

**Modern constexpr (C++17+):**
```cpp
constexpr long long fib(int n) {
    if (n <= 1) return n;
    long long a = 0, b = 1;
    for (int i = 2; i <= n; ++i) {
        long long tmp = a + b;
        a = b;
        b = tmp;
    }
    return b;
}

static_assert(fib(10) == 55);
static_assert(fib(50) == 12586269025LL);
```

**C++20 consteval (guaranteed compile-time):**
```cpp
consteval long long fib_ct(int n) {
    if (n <= 1) return n;
    long long a = 0, b = 1;
    for (int i = 2; i <= n; ++i) {
        auto tmp = a + b;
        a = b;
        b = tmp;
    }
    return b;
}

// Always computed at compile time — runtime call is a compile error
constexpr auto f30 = fib_ct(30);  // 832040
```

Key differences:

| Aspect | Classic TMP | Modern constexpr |
|--------|-------------|------------------|
| Readability | Poor (recursive types) | Clear (normal code) |
| Debugging | Template error walls | Normal error messages |
| Depth limit | Compiler template depth (~1024) | No recursion limit (iterative) |
| Compile speed | Slow (instantiates N types) | Fast (evaluated like code) |

**Verdict:** Use `constexpr`/`consteval` for new code. Classic TMP is still needed for type-level computation (type lists, trait composition).'''
    ),
    (
        "cpp/crtp-pattern",
        r'''Explain the Curiously Recurring Template Pattern (CRTP) in C++ with a practical example.''',
        r'''<think>
CRTP is when a class derives from a template parameterized by itself: class Derived : Base<Derived>.
It enables static polymorphism — the base class can call derived methods without virtual dispatch.
Common uses: mixin functionality, static interfaces, expression templates.
I should show a practical example like adding comparison operators or a counter mixin.
CRTP avoids vtable overhead while still allowing code reuse in base classes.
With C++23 deducing-this, some CRTP uses become unnecessary, worth mentioning.
</think>

CRTP lets a base class know its derived type at compile time, enabling static polymorphism without virtual dispatch.

```cpp
#include <iostream>
#include <string>

// CRTP base: provides operators from a single compare() method
template <typename Derived>
struct Comparable {
    bool operator==(const Derived& other) const {
        return self().compare(other) == 0;
    }
    bool operator<(const Derived& other) const {
        return self().compare(other) < 0;
    }
    bool operator>(const Derived& other) const {
        return self().compare(other) > 0;
    }

private:
    const Derived& self() const { return static_cast<const Derived&>(*this); }
};

// CRTP base: instance counter mixin
template <typename Derived>
struct InstanceCounter {
    static int count;
    InstanceCounter()  { ++count; }
    ~InstanceCounter() { --count; }
    static int alive() { return count; }
};
template <typename T> int InstanceCounter<T>::count = 0;

// Derived class uses both CRTP bases
class Student : public Comparable<Student>,
                public InstanceCounter<Student> {
    std::string name_;
    double gpa_;
public:
    Student(std::string name, double gpa) : name_(std::move(name)), gpa_(gpa) {}

    int compare(const Student& other) const {
        if (gpa_ < other.gpa_) return -1;
        if (gpa_ > other.gpa_) return  1;
        return 0;
    }

    friend std::ostream& operator<<(std::ostream& os, const Student& s) {
        return os << s.name_ << " (" << s.gpa_ << ")";
    }
};

int main() {
    Student a("Alice", 3.9), b("Bob", 3.7);

    std::cout << (a > b) << "\n";                // 1 (Alice has higher GPA)
    std::cout << Student::alive() << "\n";        // 2

    {
        Student c("Charlie", 3.5);
        std::cout << Student::alive() << "\n";    // 3
    }
    std::cout << Student::alive() << "\n";        // 2
}
```

**Why CRTP over virtual functions:**
- **Zero overhead** — no vtable pointer, no indirect call; everything inlines
- **Composable** — stack multiple CRTP bases (mixin pattern)
- **Compile-time enforcement** — missing `compare()` gives a compile error, not a runtime crash

**C++23 alternative — deducing this:**
```cpp
struct Comparable {
    bool operator==(this auto const& self, auto const& other) {
        return self.compare(other) == 0;
    }
};
```
Deducing `this` eliminates the need for the template parameter in many CRTP use cases.'''
    ),
    (
        "cpp/policy-based-design",
        r'''What is policy-based design in C++? Show a practical example.''',
        r'''<think>
Policy-based design uses template parameters to inject behavior into a class at compile time.
Alexandrescu popularized this in "Modern C++ Design" — it's a compile-time strategy pattern.
Each policy is a small class providing a specific behavior (logging, threading, allocation).
The host class combines policies via inheritance or composition.
I'll show a smart pointer or logger with pluggable policies for a clear example.
This gives zero-overhead abstraction since policies are resolved at compile time.
</think>

Policy-based design uses template parameters to compose behavior at compile time — like the strategy pattern, but with zero runtime overhead.

```cpp
#include <iostream>
#include <mutex>
#include <fstream>
#include <string>

// --- Output Policies ---
struct ConsoleOutput {
    void write(const std::string& msg) {
        std::cout << msg << "\n";
    }
};

struct FileOutput {
    std::ofstream file{"app.log", std::ios::app};
    void write(const std::string& msg) {
        file << msg << "\n";
    }
};

// --- Formatting Policies ---
struct PlainFormat {
    std::string format(const std::string& level, const std::string& msg) {
        return "[" + level + "] " + msg;
    }
};

struct TimestampFormat {
    std::string format(const std::string& level, const std::string& msg) {
        // Simplified — production code would use <chrono>
        return "2026-03-07T12:00:00 [" + level + "] " + msg;
    }
};

// --- Threading Policies ---
struct SingleThreaded {
    struct Lock { Lock(SingleThreaded&) {} };  // No-op
};

struct MultiThreaded {
    std::mutex mtx;
    struct Lock {
        std::scoped_lock<std::mutex> lk;
        Lock(MultiThreaded& p) : lk(p.mtx) {}
    };
};

// --- Host class combines all policies ---
template <typename OutputPolicy   = ConsoleOutput,
          typename FormatPolicy   = PlainFormat,
          typename ThreadPolicy   = SingleThreaded>
class Logger : private OutputPolicy,
               private FormatPolicy,
               private ThreadPolicy {
public:
    void info(const std::string& msg) {
        log("INFO", msg);
    }
    void error(const std::string& msg) {
        log("ERROR", msg);
    }

private:
    void log(const std::string& level, const std::string& msg) {
        typename ThreadPolicy::Lock lock(*this);
        auto formatted = FormatPolicy::format(level, msg);
        OutputPolicy::write(formatted);
    }
};

int main() {
    // Console, plain, single-threaded (default)
    Logger<> simple;
    simple.info("Application started");

    // File, timestamped, thread-safe
    Logger<FileOutput, TimestampFormat, MultiThreaded> production;
    production.error("Disk full");

    // Console, timestamped, single-threaded
    Logger<ConsoleOutput, TimestampFormat> dev;
    dev.info("Debug build running");
}
```

**Benefits over runtime polymorphism:**
- **Zero overhead** — no vtables, policies inline completely
- **Compile-time errors** — missing policy methods caught at build time
- **Combinatorial flexibility** — 2 outputs x 2 formats x 2 threading = 8 logger types from 6 small classes
- **No heap allocation** — everything lives on the stack

**When to use:** System libraries, allocators, smart pointers, containers — anywhere you need pluggable behavior without runtime cost.'''
    ),
    (
        "cpp/type-erasure-pattern",
        r'''Explain the type erasure pattern in C++ and show how to implement it.''',
        r'''<think>
Type erasure hides concrete types behind a uniform interface without inheritance.
std::function, std::any, and std::packaged_task all use type erasure internally.
The pattern uses a non-template outer class, an abstract inner concept, and a templated inner model.
This gives runtime polymorphism without forcing users to inherit from a base class.
Sean Parent's talk "Inheritance is the Base Class of Evil" popularized this pattern.
I'll implement a simplified Drawable-style example to show the mechanics clearly.
</think>

Type erasure gives you runtime polymorphism without requiring types to inherit from a common base. The user's types stay clean — no virtual functions, no base class coupling.

```cpp
#include <iostream>
#include <memory>
#include <vector>
#include <string>

class Printable {
    // Abstract concept (internal interface)
    struct Concept {
        virtual ~Concept() = default;
        virtual void print(std::ostream& os) const = 0;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };

    // Templated model (wraps any type with a print() method)
    template <typename T>
    struct Model : Concept {
        T data;
        Model(T d) : data(std::move(d)) {}
        void print(std::ostream& os) const override { data.print(os); }
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model>(*this);
        }
    };

    std::unique_ptr<Concept> ptr_;

public:
    // Constructor accepts ANY type with a .print(ostream&) method
    template <typename T>
    Printable(T obj) : ptr_(std::make_unique<Model<T>>(std::move(obj))) {}

    // Value semantics (copy via clone)
    Printable(const Printable& other) : ptr_(other.ptr_->clone()) {}
    Printable& operator=(const Printable& other) {
        ptr_ = other.ptr_->clone();
        return *this;
    }
    Printable(Printable&&) = default;
    Printable& operator=(Printable&&) = default;

    void print(std::ostream& os) const { ptr_->print(os); }
};

// --- Unrelated types, no common base class ---
struct Circle {
    double radius;
    void print(std::ostream& os) const {
        os << "Circle(r=" << radius << ")";
    }
};

struct Document {
    std::string title;
    void print(std::ostream& os) const {
        os << "Doc: " << title;
    }
};

int main() {
    // Heterogeneous container — no shared base class needed!
    std::vector<Printable> items;
    items.emplace_back(Circle{5.0});
    items.emplace_back(Document{"Design Patterns"});
    items.emplace_back(Circle{2.5});

    for (const auto& item : items) {
        item.print(std::cout);
        std::cout << "\n";
    }
    // Circle(r=5)
    // Doc: Design Patterns
    // Circle(r=2.5)
}
```

**How it works:**
1. **Concept** — abstract interface (the hidden base class)
2. **Model<T>** — templated wrapper that adapts any type to the Concept
3. **Outer class** — non-template, holds a `unique_ptr<Concept>`, provides value semantics

**Standard library examples:**
- `std::function<void()>` — erases any callable
- `std::any` — erases any copyable type
- `std::move_only_function` (C++23) — erases move-only callables

**Trade-off:** One heap allocation per object (can be optimized with small-buffer optimization).'''
    ),
    (
        "cpp/custom-allocator",
        r'''How do I write a custom allocator in C++17? Show an arena/bump allocator example.''',
        r'''<think>
C++17 simplified the allocator interface — you only need allocate() and deallocate().
An arena/bump allocator is the simplest useful allocator: increment a pointer, never free individually.
Good for frame-based game allocations or request-scoped work.
The allocator must be stateful (holds the arena pointer), so I need the propagate/select traits.
I'll show a simple monotonic arena that works with std::vector.
Need to satisfy the Allocator named requirements for STL compatibility.
</think>

C++17 simplified custom allocators. Here's a monotonic arena (bump allocator) that works with STL containers:

```cpp
#include <cstddef>
#include <iostream>
#include <vector>
#include <memory>
#include <cassert>

class Arena {
    char* buffer_;
    std::size_t capacity_;
    std::size_t offset_ = 0;

public:
    explicit Arena(std::size_t capacity)
        : buffer_(new char[capacity]), capacity_(capacity) {}

    ~Arena() { delete[] buffer_; }
    Arena(const Arena&) = delete;
    Arena& operator=(const Arena&) = delete;

    void* allocate(std::size_t bytes, std::size_t alignment) {
        // Align the offset
        std::size_t aligned = (offset_ + alignment - 1) & ~(alignment - 1);
        if (aligned + bytes > capacity_)
            throw std::bad_alloc();
        void* ptr = buffer_ + aligned;
        offset_ = aligned + bytes;
        return ptr;
    }

    void reset() { offset_ = 0; }  // "Free" everything at once
    std::size_t used() const { return offset_; }
};

// STL-compatible allocator adapter
template <typename T>
class ArenaAllocator {
    Arena* arena_;

public:
    using value_type = T;

    explicit ArenaAllocator(Arena& arena) : arena_(&arena) {}

    template <typename U>
    ArenaAllocator(const ArenaAllocator<U>& other) noexcept
        : arena_(other.arena_) {}

    T* allocate(std::size_t n) {
        return static_cast<T*>(arena_->allocate(n * sizeof(T), alignof(T)));
    }

    void deallocate(T*, std::size_t) noexcept {
        // Arena doesn't free individual allocations
    }

    template <typename U> friend class ArenaAllocator;

    bool operator==(const ArenaAllocator& other) const {
        return arena_ == other.arena_;
    }
};

int main() {
    Arena arena(4096);  // 4KB arena

    // Vector using arena allocation
    std::vector<int, ArenaAllocator<int>> nums(ArenaAllocator<int>(arena));
    for (int i = 0; i < 100; ++i)
        nums.push_back(i);

    std::cout << "Arena used: " << arena.used() << " bytes\n";
    std::cout << "Vector size: " << nums.size() << "\n";

    // Reset arena — all memory reclaimed instantly
    nums.clear();
    arena.reset();
    std::cout << "After reset: " << arena.used() << " bytes\n";  // 0
}
```

**Why use a custom allocator?**
- **Game engines:** per-frame bump allocator, reset each frame (zero fragmentation)
- **Servers:** per-request arena, free all memory when request completes
- **Real-time systems:** avoid `malloc`/`free` jitter during critical paths

**C++17 PMR alternative** (easier — see `std::pmr::monotonic_buffer_resource`):
```cpp
#include <memory_resource>
char buf[4096];
std::pmr::monotonic_buffer_resource pool(buf, sizeof(buf));
std::pmr::vector<int> v(&pool);
```
PMR is the modern approach for new code — custom allocators are still needed for legacy STL interfaces.'''
    ),
    (
        "cpp/exception-safety-guarantees",
        r'''What are the exception safety guarantees in C++ and how do I write exception-safe code?''',
        r'''<think>
The three guarantees are: basic (invariants preserved), strong (commit-or-rollback), and nothrow.
The copy-and-swap idiom is the classic technique for strong guarantee.
RAII is foundational — destructors clean up even when exceptions fly.
I should show practical examples of each level, not just theory.
noexcept is important for move operations and swap — enables optimizations.
The key insight: design operations so partial failure leaves objects in valid states.
</think>

C++ defines three levels of exception safety:

| Guarantee | Promise | Example |
|-----------|---------|---------|
| **Nothrow** | Never throws | Destructors, swap, move ops |
| **Strong** | Commit-or-rollback; state unchanged on failure | `std::vector::push_back` |
| **Basic** | No leaks, object in valid (but unspecified) state | Most STL operations |

```cpp
#include <vector>
#include <string>
#include <algorithm>
#include <utility>

class Database {
    std::vector<std::string> records_;
    std::string name_;

public:
    // --- NOTHROW GUARANTEE ---
    // Destructors, swap, and move should never throw
    ~Database() = default;  // implicitly noexcept

    void swap(Database& other) noexcept {
        records_.swap(other.records_);
        name_.swap(other.name_);
    }

    Database(Database&& other) noexcept = default;
    Database& operator=(Database&& other) noexcept = default;

    // --- STRONG GUARANTEE (copy-and-swap idiom) ---
    Database(const Database&) = default;

    Database& operator=(const Database& other) {
        Database tmp(other);  // Copy: if this throws, *this is untouched
        swap(tmp);            // Swap: noexcept, always succeeds
        return *this;         // tmp destroyed, old data freed
    }

    // --- STRONG GUARANTEE (manual) ---
    void add_record(const std::string& record) {
        // vector::push_back provides strong guarantee:
        // if reallocation fails, the vector is unchanged
        records_.push_back(record);
    }

    // --- BASIC GUARANTEE (valid but unspecified state) ---
    void bulk_add(const std::vector<std::string>& new_records) {
        // If an exception occurs mid-loop, some records are added, some aren't.
        // Object is still valid (no leaks, invariants hold), but state is partial.
        for (const auto& r : new_records) {
            records_.push_back(r);
        }
    }

    // --- STRONG via temporary + swap ---
    void bulk_add_strong(const std::vector<std::string>& new_records) {
        auto copy = records_;  // Work on a copy
        for (const auto& r : new_records) {
            copy.push_back(r);  // If this throws, records_ is untouched
        }
        records_.swap(copy);   // noexcept commit
    }

    size_t size() const noexcept { return records_.size(); }
};
```

**Core rules for exception-safe code:**
1. **RAII everywhere** — resources in constructors, cleanup in destructors (no manual `delete`)
2. **Mark moves and swap `noexcept`** — enables STL optimizations (`vector` won't use your move if it might throw)
3. **Do all throwing work before modifying state** — the "do work on the side, then swap" pattern
4. **Never throw from destructors** — `std::terminate` will be called if a destructor throws during stack unwinding'''
    ),
    (
        "cpp/std-any-usage",
        r'''How do I use std::any in C++17? When is it appropriate vs std::variant?''',
        r'''<think>
std::any holds any copyable type, type-checked at runtime with any_cast.
std::variant is a closed set of types (compile-time checked, no heap allocation).
std::any uses type erasure internally (heap allocation for large types).
Good for plugin systems, config values, or truly heterogeneous storage.
Bad when you know the set of types — variant is safer and faster.
I should show basic usage, bad_any_cast handling, and comparison with variant.
</think>

`std::any` holds a value of any copyable type, type-checked at runtime:

```cpp
#include <any>
#include <iostream>
#include <string>
#include <vector>
#include <unordered_map>

int main() {
    // Basic usage
    std::any value = 42;
    std::cout << std::any_cast<int>(value) << "\n";  // 42

    value = std::string("hello");
    std::cout << std::any_cast<std::string>(value) << "\n";  // hello

    value = 3.14;
    std::cout << std::any_cast<double>(value) << "\n";  // 3.14

    // Type checking
    std::cout << value.type().name() << "\n";  // "d" (double)
    std::cout << value.has_value() << "\n";    // true

    // Safe access (pointer — returns nullptr on mismatch)
    if (auto* p = std::any_cast<int>(&value)) {
        std::cout << *p << "\n";  // Not reached — it's a double
    }

    // Throws on type mismatch
    try {
        std::any_cast<int>(value);  // value is double, not int
    } catch (const std::bad_any_cast& e) {
        std::cout << "Wrong type: " << e.what() << "\n";
    }

    // Practical: configuration map with mixed types
    std::unordered_map<std::string, std::any> config;
    config["port"] = 8080;
    config["host"] = std::string("localhost");
    config["debug"] = true;
    config["ratio"] = 0.75;

    int port = std::any_cast<int>(config["port"]);
    auto host = std::any_cast<std::string>(config["host"]);

    // Reset
    value.reset();
    std::cout << value.has_value() << "\n";  // false
}
```

**`std::any` vs `std::variant`:**

| Feature | `std::any` | `std::variant<int, string, double>` |
|---------|-----------|--------------------------------------|
| Type set | Open (any copyable type) | Closed (fixed at compile time) |
| Type safety | Runtime (`bad_any_cast`) | Compile-time (`std::visit`) |
| Storage | Heap (large types) | Stack (no allocation) |
| Size | ~32 bytes + heap | `sizeof(largest alternative)` + tag |
| Use case | Plugin data, configs | State machines, parsers |

**Rule of thumb:**
- Know the types at compile time? Use `std::variant`
- Truly open-ended (plugin APIs, serialization)? Use `std::any`
- Just need nullable? Use `std::optional`'''
    ),
    (
        "cpp/stl-containers-algorithms-deep-dive",
        r'''Show some advanced STL container and algorithm usage in C++17/20 that most developers don't know about.''',
        r'''<think>
There are many lesser-known STL features worth highlighting.
C++17 added node extraction/insertion, std::reduce, std::transform_reduce.
C++20 added ranges, which transform how algorithms are composed.
I should cover: node handles, structured bindings with maps, erase_if, ranges pipelines.
Also: std::partition, std::nth_element, std::rotate for in-place operations.
Keep it practical — show things people can use immediately.
</think>

Here are powerful STL features many developers overlook:

```cpp
#include <algorithm>
#include <iostream>
#include <map>
#include <numeric>
#include <ranges>
#include <set>
#include <string>
#include <vector>

int main() {
    // --- C++17: Node extraction (move elements between containers) ---
    std::map<int, std::string> src{{1,"one"}, {2,"two"}, {3,"three"}};
    std::map<int, std::string> dst;

    auto node = src.extract(2);     // Remove without copy/destroy
    node.key() = 20;               // Modify key (impossible otherwise!)
    dst.insert(std::move(node));   // Transfer to dst
    // src = {1:one, 3:three}, dst = {20:two}

    // --- C++17: try_emplace (no-op if key exists) ---
    std::map<std::string, std::vector<int>> groups;
    groups.try_emplace("a", std::initializer_list<int>{1, 2, 3});
    groups.try_emplace("a", std::initializer_list<int>{4, 5});  // No-op, "a" exists
    // groups["a"] is still {1, 2, 3}

    // --- C++20: std::erase_if (uniform container erasure) ---
    std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8};
    std::erase_if(v, [](int x) { return x % 2 == 0; });
    // v = {1, 3, 5, 7} — works on vector, deque, list, map, set

    // --- C++20: Ranges pipelines ---
    std::vector<int> data{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    auto result = data
        | std::views::filter([](int x) { return x % 2 == 0; })
        | std::views::transform([](int x) { return x * x; })
        | std::views::take(3);
    // Lazy: {4, 16, 36} — nothing computed until iterated

    for (int x : result) std::cout << x << " ";
    std::cout << "\n";

    // --- std::nth_element (O(n) partial sort) ---
    std::vector<int> scores{90, 20, 50, 70, 30, 80, 10, 60, 40};
    std::nth_element(scores.begin(), scores.begin() + 4, scores.end());
    // scores[4] is the median; left side <= median, right side >= median

    // --- std::transform_reduce (parallel-friendly map-reduce) ---
    std::vector<double> xs{1, 2, 3}, ys{4, 5, 6};
    double dot = std::transform_reduce(
        xs.begin(), xs.end(), ys.begin(), 0.0);  // dot product: 32

    // --- std::rotate (in-place rotation) ---
    std::vector<int> ring{1, 2, 3, 4, 5};
    std::rotate(ring.begin(), ring.begin() + 2, ring.end());
    // ring = {3, 4, 5, 1, 2}
}
```

**Overlooked gems:**
- **`std::partition`** — O(n) split without sorting
- **`node.extract()`** — move map/set elements between containers or change keys
- **`std::transform_reduce`** — parallelizable map-reduce in one call
- **Ranges views** — lazy, composable, no intermediate allocations'''
    ),
    (
        "cpp/custom-iterator-implementation",
        r'''How do I implement a custom iterator in C++20? Show a complete example.''',
        r'''<think>
C++20 simplified iterators with concepts like std::input_iterator, std::forward_iterator, etc.
A custom iterator needs: value_type, difference_type, operator*, operator++, and sentinel comparison.
I'll implement an iterator for a simple ring buffer to show a practical use case.
Using C++20 concepts, the compiler gives clear errors if the iterator interface is wrong.
The key iterator categories: input, forward, bidirectional, random_access, contiguous.
I should show both the iterator definition and range-based for loop usage.
</think>

Here's a custom forward iterator for a ring buffer, using C++20 conventions:

```cpp
#include <cstddef>
#include <iostream>
#include <iterator>
#include <algorithm>
#include <array>

template <typename T, std::size_t N>
class RingBuffer {
    std::array<T, N> data_{};
    std::size_t head_ = 0;
    std::size_t size_ = 0;

public:
    void push(const T& value) {
        data_[(head_ + size_) % N] = value;
        if (size_ < N) ++size_;
        else head_ = (head_ + 1) % N;
    }

    std::size_t size() const { return size_; }

    // --- Iterator ---
    class Iterator {
    public:
        // C++20 iterator traits (via alias declarations)
        using iterator_category = std::forward_iterator_tag;
        using value_type        = T;
        using difference_type   = std::ptrdiff_t;
        using pointer           = const T*;
        using reference         = const T&;

    private:
        const RingBuffer* ring_;
        std::size_t index_;

    public:
        Iterator() : ring_(nullptr), index_(0) {}  // Sentinel
        Iterator(const RingBuffer* r, std::size_t idx)
            : ring_(r), index_(idx) {}

        reference operator*() const {
            return ring_->data_[(ring_->head_ + index_) % N];
        }
        pointer operator->() const { return &(**this); }

        Iterator& operator++() {
            ++index_;
            return *this;
        }
        Iterator operator++(int) {
            auto tmp = *this;
            ++(*this);
            return tmp;
        }

        bool operator==(const Iterator& other) const {
            return index_ == other.index_;
        }
    };

    Iterator begin() const { return Iterator(this, 0); }
    Iterator end() const   { return Iterator(this, size_); }
};

// Verify our iterator satisfies the concept
static_assert(std::forward_iterator<RingBuffer<int, 8>::Iterator>);

int main() {
    RingBuffer<int, 5> ring;
    for (int i = 1; i <= 8; ++i) ring.push(i);

    // Ring contains last 5: {4, 5, 6, 7, 8}
    for (int val : ring) {
        std::cout << val << " ";
    }
    std::cout << "\n";

    // Works with STL algorithms
    auto it = std::find(ring.begin(), ring.end(), 6);
    if (it != ring.end()) {
        std::cout << "Found: " << *it << "\n";
    }

    // Works with ranges
    auto even = std::ranges::count_if(ring, [](int x) { return x % 2 == 0; });
    std::cout << "Even count: " << even << "\n";  // 3 (4, 6, 8)
}
```

**C++20 iterator checklist:**
- `value_type`, `difference_type` — required type aliases
- `operator*` — dereference
- `operator++` (pre and post) — advance
- `operator==` — comparison (C++20 auto-generates `!=`)
- Default constructor — required for `std::forward_iterator`

**Tip:** Use `static_assert(std::forward_iterator<YourIterator>)` to get clear compile errors if you miss something.'''
    ),
    (
        "cpp/parallel-algorithms-execution-policies",
        r'''How do I use C++17 parallel algorithms? Show execution policies with practical examples.''',
        r'''<think>
C++17 added execution policies: seq, par, par_unseq, and C++20 added unseq.
These are passed as the first argument to standard algorithms.
std::execution::par enables multi-threaded execution.
std::execution::par_unseq allows both parallelism and vectorization (SIMD).
Important caveats: no exceptions propagate (std::terminate), data races are UB.
Need to link with TBB on GCC/Clang; MSVC has built-in support.
</think>

C++17 added execution policies that parallelize standard algorithms with a single argument:

```cpp
#include <algorithm>
#include <execution>
#include <iostream>
#include <numeric>
#include <vector>
#include <chrono>
#include <cmath>

int main() {
    constexpr size_t N = 10'000'000;
    std::vector<double> data(N);
    std::iota(data.begin(), data.end(), 1.0);

    auto time_it = [](auto&& fn, const char* label) {
        auto start = std::chrono::high_resolution_clock::now();
        auto result = fn();
        auto ms = std::chrono::duration<double, std::milli>(
            std::chrono::high_resolution_clock::now() - start).count();
        std::cout << label << ": " << ms << " ms (result: " << result << ")\n";
    };

    // --- std::reduce (parallel-safe accumulate) ---
    time_it([&] {
        return std::reduce(std::execution::seq, data.begin(), data.end(), 0.0);
    }, "Sequential reduce");

    time_it([&] {
        return std::reduce(std::execution::par, data.begin(), data.end(), 0.0);
    }, "Parallel reduce");

    // --- std::transform with execution policy ---
    std::vector<double> output(N);

    // Parallel sqrt of every element
    std::transform(std::execution::par_unseq,
                   data.begin(), data.end(), output.begin(),
                   [](double x) { return std::sqrt(x); });

    // --- std::sort ---
    std::vector<int> unsorted(N);
    std::iota(unsorted.begin(), unsorted.end(), 0);
    std::shuffle(unsorted.begin(), unsorted.end(),
                 std::mt19937{42});

    time_it([&] {
        auto v = unsorted;
        std::sort(std::execution::par, v.begin(), v.end());
        return v.back();
    }, "Parallel sort");

    // --- std::for_each (parallel) ---
    std::vector<int> counts(N, 0);
    std::for_each(std::execution::par, counts.begin(), counts.end(),
                  [](int& x) { x = x * 2 + 1; });  // No data races — each element independent

    // --- std::transform_reduce (parallel dot product) ---
    std::vector<double> a(N, 2.0), b(N, 3.0);
    double dot = std::transform_reduce(
        std::execution::par,
        a.begin(), a.end(), b.begin(), 0.0);
    std::cout << "Dot product: " << dot << "\n";  // 6 * N
}
```

**Execution policies:**

| Policy | Meaning | Use when |
|--------|---------|----------|
| `seq` | Sequential (default) | Debugging, small data |
| `par` | Multi-threaded | CPU-bound, large data |
| `par_unseq` | Threads + SIMD | No mutex/allocation in lambda |
| `unseq` (C++20) | SIMD only, single thread | Vectorizable math loops |

**Critical rules:**
- Lambda must be **thread-safe** — no shared mutable state without atomics
- Exceptions in parallel algorithms call **`std::terminate`** (not caught)
- Operation must be **associative + commutative** for `std::reduce` (unlike `std::accumulate`)
- **Link TBB** on GCC/Clang: `g++ -std=c++17 -ltbb file.cpp`'''
    ),
    (
        "cpp/memory-model-memory-order",
        r'''Explain the C++ memory model and std::memory_order. When would I use relaxed vs acquire/release?''',
        r'''<think>
The C++ memory model defines how atomic operations interact across threads.
Six memory orderings: relaxed, consume, acquire, release, acq_rel, seq_cst.
seq_cst is the default (safest, slowest), relaxed is cheapest (just atomicity, no ordering).
acquire/release gives happens-before without full sequential consistency.
Practical use cases: counters (relaxed), flag-based synchronization (acquire/release).
This is expert territory — most developers should stick with seq_cst or mutex.
I need to explain clearly with concrete examples of each level.
</think>

The C++ memory model defines how threads see each other's memory operations. `std::memory_order` controls the guarantees:

```cpp
#include <atomic>
#include <cassert>
#include <iostream>
#include <thread>

// --- RELAXED: just atomicity, no ordering guarantees ---
// Use for: counters, statistics — don't care about order, just accuracy
std::atomic<int> counter{0};

void count_relaxed() {
    for (int i = 0; i < 1000; ++i)
        counter.fetch_add(1, std::memory_order_relaxed);
    // Other threads may see increments in any order
    // But the final count will be correct
}

// --- ACQUIRE/RELEASE: producer-consumer synchronization ---
// Release "publishes" data; Acquire "receives" it
std::atomic<bool> ready{false};
int payload = 0;  // non-atomic!

void producer() {
    payload = 42;                                      // Write data FIRST
    ready.store(true, std::memory_order_release);      // Then signal
    // release: all writes before this store are visible to the acquirer
}

void consumer() {
    while (!ready.load(std::memory_order_acquire)) {}  // Wait for signal
    // acquire: all writes before the paired release are now visible
    assert(payload == 42);  // Guaranteed! acquire syncs with release
}

// --- SEQ_CST (default): total order across all threads ---
// Safest but slowest — all threads agree on the order of all seq_cst operations
std::atomic<int> x{0}, y{0};
int r1 = 0, r2 = 0;

void thread_a() {
    x.store(1);  // seq_cst by default
    r1 = y.load();
}
void thread_b() {
    y.store(1);
    r2 = x.load();
}
// With seq_cst: r1 == 0 && r2 == 0 is IMPOSSIBLE
// With relaxed: r1 == 0 && r2 == 0 IS possible (both threads see "old" values)

int main() {
    // Relaxed counter
    std::thread t1(count_relaxed), t2(count_relaxed);
    t1.join(); t2.join();
    std::cout << "Counter: " << counter.load() << "\n";  // Always 2000

    // Acquire/release sync
    std::thread tp(producer), tc(consumer);
    tp.join(); tc.join();
    std::cout << "Payload: " << payload << "\n";  // Always 42
}
```

**Summary table:**

| Order | Cost | Guarantee | Use case |
|-------|------|-----------|----------|
| `relaxed` | Cheapest | Atomicity only | Counters, stats |
| `acquire` | Moderate | Sees all writes before paired `release` | Consumer side |
| `release` | Moderate | Publishes all prior writes | Producer side |
| `acq_rel` | Moderate | Both acquire and release | Read-modify-write |
| `seq_cst` | Most expensive | Total global order | Default; correctness-critical |

**Practical advice:**
- **Start with `seq_cst`** (the default) — it's correct and the performance difference is negligible on x86
- Use `relaxed` for fire-and-forget counters where ordering doesn't matter
- Use `acquire`/`release` pairs when you need to synchronize data (not just a flag)
- **Never use `relaxed` for synchronization** — you'll get data races'''
    ),
    (
        "cpp/mutex-scoped-lock",
        r'''Show how to use std::mutex and std::scoped_lock in C++17. What are the pitfalls?''',
        r'''<think>
std::scoped_lock is the C++17 replacement for lock_guard — it can lock multiple mutexes.
It uses CTAD and variadic templates to avoid deadlocks with multiple mutexes.
Common pitfalls: forgetting to hold the lock during the entire critical section, lock ordering.
I should show basic usage, multiple mutex locking, and typical mistakes.
Also mention shared_mutex for reader-writer patterns.
Keep examples practical and highlight RAII-based locking.
</think>

`std::scoped_lock` (C++17) is the preferred RAII lock — it handles single and multiple mutexes safely:

```cpp
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <vector>
#include <string>

// --- Basic usage ---
class BankAccount {
    mutable std::mutex mtx_;
    double balance_ = 0.0;
    std::string name_;

public:
    BankAccount(std::string name, double bal) : name_(std::move(name)), balance_(bal) {}

    void deposit(double amount) {
        std::scoped_lock lock(mtx_);  // CTAD — deduces mutex type
        balance_ += amount;
    }

    double balance() const {
        std::scoped_lock lock(mtx_);
        return balance_;
    }

    // --- Multiple mutex locking (deadlock-free) ---
    static void transfer(BankAccount& from, BankAccount& to, double amount) {
        // scoped_lock locks both mutexes atomically — no deadlock
        // regardless of argument order
        std::scoped_lock lock(from.mtx_, to.mtx_);
        if (from.balance_ >= amount) {
            from.balance_ -= amount;
            to.balance_ += amount;
        }
    }
};

// --- Reader-writer lock ---
class ConfigStore {
    mutable std::shared_mutex mtx_;
    std::unordered_map<std::string, std::string> data_;

public:
    // Multiple readers can read concurrently
    std::string get(const std::string& key) const {
        std::shared_lock lock(mtx_);  // Shared (read) access
        auto it = data_.find(key);
        return it != data_.end() ? it->second : "";
    }

    // Writers get exclusive access
    void set(const std::string& key, const std::string& value) {
        std::scoped_lock lock(mtx_);  // Exclusive (write) access
        data_[key] = value;
    }
};

int main() {
    BankAccount alice("Alice", 1000), bob("Bob", 500);

    std::vector<std::thread> threads;
    for (int i = 0; i < 100; ++i) {
        threads.emplace_back([&] { BankAccount::transfer(alice, bob, 5); });
        threads.emplace_back([&] { BankAccount::transfer(bob, alice, 3); });
    }
    for (auto& t : threads) t.join();

    std::cout << "Alice: " << alice.balance() << "\n";
    std::cout << "Bob: " << bob.balance() << "\n";
    std::cout << "Total: " << alice.balance() + bob.balance() << "\n";  // Always 1500
}
```

**Common pitfalls:**

```cpp
// BAD: Lock then return reference — caller uses data after lock released
std::string& get_name() {
    std::scoped_lock lock(mtx_);
    return name_;  // BUG: reference outlives the lock
}

// BAD: Manual lock/unlock — exception-unsafe
mtx_.lock();
do_work();  // If this throws, mutex is never unlocked → deadlock
mtx_.unlock();

// BAD: Locking two mutexes separately → deadlock risk
void transfer_bad(Account& a, Account& b) {
    std::scoped_lock l1(a.mtx_);  // Thread 1: locks A, waits for B
    std::scoped_lock l2(b.mtx_);  // Thread 2: locks B, waits for A → DEADLOCK
}

// GOOD: std::scoped_lock(a.mtx_, b.mtx_) uses std::lock() internally — deadlock-free
```

**Lock type guide:**
| Type | Use case |
|------|----------|
| `scoped_lock` | Default choice; single or multiple mutexes |
| `unique_lock` | Need to unlock early, use with condition_variable |
| `shared_lock` | Reader side of shared_mutex |
| `lock_guard` | Legacy C++11; prefer scoped_lock |'''
    ),
    (
        "cpp/condition-variables",
        r'''How do condition variables work in C++? Show a producer-consumer queue.''',
        r'''<think>
std::condition_variable pairs with std::mutex for thread signaling.
Must use std::unique_lock (not scoped_lock) with condition_variable.
The classic pattern: wait with a predicate to handle spurious wakeups.
A bounded producer-consumer queue is the canonical example.
notify_one wakes one waiter, notify_all wakes all.
I should show the complete thread-safe queue with proper shutdown.
</think>

`std::condition_variable` lets threads wait for a condition and be woken by another thread:

```cpp
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <optional>
#include <queue>
#include <thread>
#include <vector>

template <typename T>
class ThreadSafeQueue {
    std::queue<T> queue_;
    mutable std::mutex mtx_;
    std::condition_variable not_empty_;
    std::condition_variable not_full_;
    std::size_t max_size_;
    bool shutdown_ = false;

public:
    explicit ThreadSafeQueue(std::size_t max_size = 100) : max_size_(max_size) {}

    void push(T value) {
        std::unique_lock lock(mtx_);
        // Wait until queue has space OR shutdown
        not_full_.wait(lock, [&] {
            return queue_.size() < max_size_ || shutdown_;
        });
        if (shutdown_) return;
        queue_.push(std::move(value));
        not_empty_.notify_one();  // Wake one consumer
    }

    std::optional<T> pop() {
        std::unique_lock lock(mtx_);
        // Wait until queue has data OR shutdown
        not_empty_.wait(lock, [&] {
            return !queue_.empty() || shutdown_;
        });
        if (queue_.empty()) return std::nullopt;  // Shutdown with empty queue
        T value = std::move(queue_.front());
        queue_.pop();
        not_full_.notify_one();  // Wake one producer
        return value;
    }

    void close() {
        std::scoped_lock lock(mtx_);
        shutdown_ = true;
        not_empty_.notify_all();  // Wake ALL waiters
        not_full_.notify_all();
    }
};

int main() {
    ThreadSafeQueue<int> queue(10);  // Bounded to 10 items

    // Producer threads
    std::vector<std::thread> producers;
    for (int p = 0; p < 3; ++p) {
        producers.emplace_back([&, p] {
            for (int i = 0; i < 5; ++i) {
                queue.push(p * 100 + i);
            }
        });
    }

    // Consumer threads
    std::vector<std::thread> consumers;
    for (int c = 0; c < 2; ++c) {
        consumers.emplace_back([&, c] {
            while (auto val = queue.pop()) {
                std::cout << "Consumer " << c << " got: " << *val << "\n";
            }
        });
    }

    for (auto& t : producers) t.join();
    queue.close();  // Signal consumers to stop
    for (auto& t : consumers) t.join();
}
```

**Condition variable rules:**
1. **Always use a predicate** — `cv.wait(lock, predicate)` handles spurious wakeups
2. **Must use `std::unique_lock`** — not `scoped_lock` (cv needs to unlock/relock internally)
3. **Hold the mutex when modifying shared state** — then notify after or outside the lock
4. **`notify_all` for shutdown** — `notify_one` might only wake one of many waiters

**Common bug — notifying under lock vs outside:**
```cpp
// Both work, but notifying outside the lock can be slightly more efficient:
{
    std::scoped_lock lock(mtx_);
    queue_.push(value);
}                            // Lock released
not_empty_.notify_one();    // Consumer wakes and can immediately acquire lock
```'''
    ),
    (
        "cpp/thread-pool-implementation",
        r'''How do I implement a simple thread pool in C++17?''',
        r'''<think>
A thread pool pre-creates worker threads that pull tasks from a shared queue.
Need: vector of threads, task queue (std::function), mutex, condition variable, shutdown flag.
The submit function should return a std::future for getting results.
Use std::packaged_task to wrap callables and extract futures.
Keep it simple but production-quality: proper shutdown, move semantics.
This is an advanced topic combining threading primitives together.
</think>

A practical thread pool using `std::function`, condition variables, and `std::future` for results:

```cpp
#include <condition_variable>
#include <functional>
#include <future>
#include <iostream>
#include <mutex>
#include <queue>
#include <thread>
#include <vector>

class ThreadPool {
    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> tasks_;
    std::mutex mtx_;
    std::condition_variable cv_;
    bool stop_ = false;

public:
    explicit ThreadPool(std::size_t num_threads = std::thread::hardware_concurrency()) {
        for (std::size_t i = 0; i < num_threads; ++i) {
            workers_.emplace_back([this] { worker_loop(); });
        }
    }

    ~ThreadPool() {
        {
            std::scoped_lock lock(mtx_);
            stop_ = true;
        }
        cv_.notify_all();
        for (auto& w : workers_) w.join();
    }

    // Non-copyable, non-movable
    ThreadPool(const ThreadPool&) = delete;
    ThreadPool& operator=(const ThreadPool&) = delete;

    // Submit a task and get a future for the result
    template <typename F, typename... Args>
    auto submit(F&& f, Args&&... args) -> std::future<std::invoke_result_t<F, Args...>> {
        using ReturnType = std::invoke_result_t<F, Args...>;

        auto task = std::make_shared<std::packaged_task<ReturnType()>>(
            std::bind(std::forward<F>(f), std::forward<Args>(args)...)
        );
        auto future = task->get_future();

        {
            std::scoped_lock lock(mtx_);
            if (stop_) throw std::runtime_error("submit on stopped pool");
            tasks_.emplace([task]() { (*task)(); });
        }
        cv_.notify_one();
        return future;
    }

private:
    void worker_loop() {
        while (true) {
            std::function<void()> task;
            {
                std::unique_lock lock(mtx_);
                cv_.wait(lock, [this] { return stop_ || !tasks_.empty(); });
                if (stop_ && tasks_.empty()) return;
                task = std::move(tasks_.front());
                tasks_.pop();
            }
            task();  // Execute outside the lock
        }
    }
};

int main() {
    ThreadPool pool(4);

    // Submit tasks and collect futures
    std::vector<std::future<int>> results;
    for (int i = 0; i < 20; ++i) {
        results.push_back(pool.submit([i] {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            return i * i;
        }));
    }

    // Collect results
    for (auto& f : results) {
        std::cout << f.get() << " ";
    }
    std::cout << "\n";

    // Submit with arguments
    auto sum_future = pool.submit([](int a, int b) { return a + b; }, 100, 200);
    std::cout << "Sum: " << sum_future.get() << "\n";  // 300
}
```

**Design notes:**
- **`std::packaged_task`** wraps any callable and provides a `std::future` for the result
- **RAII shutdown** — destructor sets `stop_`, notifies all, and joins
- **Workers drain the queue** before stopping (`stop_ && tasks_.empty()`)
- **Task executes outside the lock** — only queue access is synchronized

**Limitations of this simple pool:**
- No task priorities or cancellation
- No work stealing (each thread contends on one queue)
- `std::function` has overhead (type erasure + possible allocation)

For production, consider libraries like `BS::thread_pool` or Intel TBB's `task_group`.'''
    ),
    (
        "cpp/consteval-constinit",
        r'''What are consteval and constinit in C++20? How do they differ from constexpr?''',
        r'''<think>
consteval forces compile-time evaluation — runtime calls are errors.
constinit ensures a variable is initialized at compile time but can be modified at runtime.
constexpr functions CAN run at compile time or runtime; consteval MUST run at compile time.
constinit solves the "static initialization order fiasco" without making the variable const.
These are distinct tools for different compile-time guarantees.
Good examples: consteval for lookup tables, constinit for global state.
</think>

C++20 adds two new keywords to complement `constexpr`:

```cpp
#include <array>
#include <iostream>
#include <cmath>

// --- consteval: MUST be evaluated at compile time ---
consteval int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; ++i) result *= i;
    return result;
}

// Always computed at compile time
constexpr int f10 = factorial(10);  // 3628800 — OK

void example_consteval() {
    constexpr auto x = factorial(5);  // OK: compile-time
    // int n = 5;
    // auto y = factorial(n);  // ERROR: n is not a compile-time constant

    // Use consteval to build compile-time lookup tables
    constexpr auto table = [] consteval {
        std::array<int, 10> t{};
        for (int i = 0; i < 10; ++i) t[i] = factorial(i + 1);
        return t;
    }();
    static_assert(table[4] == 120);
}

// --- constinit: compile-time initialization, runtime mutability ---
// Solves the Static Initialization Order Fiasco

constinit int global_counter = 0;          // Initialized at compile time
constinit thread_local int tls_val = 42;   // Works with thread_local too

struct Config {
    int max_threads;
    bool debug;
};
constinit Config config{8, false};  // No dynamic initialization

void example_constinit() {
    // constinit variables CAN be modified at runtime (unlike constexpr)
    global_counter++;
    config.debug = true;
    std::cout << "Counter: " << global_counter << "\n";
}

// --- Comparison ---
constexpr int ce_func(int n) { return n * 2; }   // MAY be compile-time
consteval int cv_func(int n) { return n * 2; }   // MUST be compile-time

void comparison() {
    int runtime_val = 5;

    auto a = ce_func(runtime_val);  // OK: runs at runtime
    // auto b = cv_func(runtime_val);  // ERROR: not compile-time

    constexpr auto c = ce_func(5);  // OK: compile-time
    constexpr auto d = cv_func(5);  // OK: compile-time
}

int main() {
    example_consteval();
    example_constinit();
}
```

**Summary:**

| Keyword | Applies to | Initialization | Mutable at runtime? |
|---------|-----------|----------------|---------------------|
| `constexpr` (var) | Variables | Compile-time | No (it's `const`) |
| `constexpr` (func) | Functions | Compile-time OR runtime | N/A |
| `consteval` | Functions only | Always compile-time | N/A |
| `constinit` | Variables only | Must be compile-time | **Yes** |

**When to use each:**
- **`constexpr` function:** "This can be computed at compile time if you want"
- **`consteval` function:** "This MUST be computed at compile time" — lookup tables, code generation
- **`constinit` variable:** "Initialize at compile time, but allow runtime changes" — globals, singletons'''
    ),
    (
        "cpp/aggregate-initialization-designated",
        r'''How do aggregate initialization and designated initializers work in C++20?''',
        r'''<think>
Aggregate initialization is list-initialization of structs/arrays without constructors.
C++20 added designated initializers (from C99) to C++.
Designated initializers must be in declaration order in C++ (unlike C).
This makes code more readable by naming fields at the call site.
Also covers CTAD and parenthesized aggregate init in C++20.
Useful for config structs, options patterns, and clear API design.
</think>

C++20 brings designated initializers and parenthesized aggregate init, making struct initialization much clearer:

```cpp
#include <iostream>
#include <string>
#include <optional>

// An aggregate: no user-declared constructors, no private members
struct ServerConfig {
    std::string host = "localhost";
    int port = 8080;
    int max_connections = 100;
    bool tls_enabled = false;
    std::optional<std::string> cert_path;
};

// Nested aggregates
struct AppConfig {
    std::string name;
    ServerConfig server;
    bool verbose = false;
};

int main() {
    // --- C++20 Designated initializers ---
    // Name the fields — much clearer than positional
    ServerConfig cfg1{
        .host = "example.com",
        .port = 443,
        .tls_enabled = true,
        .cert_path = "/etc/ssl/cert.pem"
    };
    // .max_connections uses default (100) — can skip fields with defaults

    // --- Order matters in C++ (unlike C) ---
    // ServerConfig bad{.port = 80, .host = "x"};  // ERROR: out of order

    // --- Nested designated init ---
    AppConfig app{
        .name = "MyApp",
        .server = {
            .host = "0.0.0.0",
            .port = 9090
        },
        .verbose = true
    };

    // --- Traditional aggregate init (positional) ---
    ServerConfig cfg2{"10.0.0.1", 3000, 50, true};
    // Hard to read — which field is 50? Is true for tls?

    // --- Partial initialization (rest get defaults) ---
    ServerConfig cfg3{.port = 9999};
    // host="localhost", port=9999, max_connections=100, tls_enabled=false

    // --- C++20: Parenthesized aggregate init (works with make_unique) ---
    auto ptr = std::make_unique<ServerConfig>("api.com", 443, 200, true);
    // Before C++20, this required a constructor

    // --- Arrays ---
    int arr[] = {1, 2, 3, 4, 5};  // Size deduced

    // --- Structured bindings (C++17) to decompose ---
    auto [host, port, max_conn, tls, cert] = cfg1;
    std::cout << host << ":" << port << " tls=" << tls << "\n";
}
```

**Rules for aggregates (C++20):**
- No user-declared or inherited constructors
- No private/protected non-static data members
- No virtual functions
- Can have base classes (C++17: must be public, non-virtual)

**Designated initializer rules:**
- Must follow **declaration order** (C++ requirement, not in C)
- Can **skip fields** with default values
- Cannot **mix** designated and positional
- Work with **nested aggregates**

**Best practice:** Use designated initializers for any struct with 3+ fields — it's self-documenting and lets you skip defaults.'''
    ),
    (
        "cpp/if-constexpr-compile-time-branching",
        r'''How does if constexpr work in C++17? Show practical use cases.''',
        r'''<think>
if constexpr evaluates a condition at compile time and discards the false branch entirely.
This replaces SFINAE and tag dispatch for many template specialization scenarios.
The discarded branch doesn't need to be valid code for the given template arguments.
Great for: type-based dispatch, simplifying variadic templates, feature detection.
I should show practical before/after comparisons with SFINAE.
This is one of the most impactful C++17 features for template code.
</think>

`if constexpr` evaluates conditions at compile time — the false branch is completely discarded (not just not-executed, but not even compiled for that instantiation):

```cpp
#include <iostream>
#include <type_traits>
#include <string>
#include <vector>
#include <sstream>

// --- Type-based dispatch (replaces tag dispatch / SFINAE) ---
template <typename T>
std::string to_string(const T& value) {
    if constexpr (std::is_arithmetic_v<T>) {
        return std::to_string(value);
    } else if constexpr (std::is_same_v<T, std::string>) {
        return value;
    } else if constexpr (std::is_same_v<T, const char*>) {
        return std::string(value);
    } else {
        // This branch doesn't compile if T is int — that's the point
        std::ostringstream oss;
        oss << value;
        return oss.str();
    }
}

// --- Variadic template processing (replaces recursive specialization) ---
template <typename... Args>
void print_all(const Args&... args) {
    // Fold expression + if constexpr
    ((std::cout << args << " "), ...);
    std::cout << "\n";
}

// --- Compile-time feature detection ---
template <typename T>
auto get_size(const T& container) {
    if constexpr (requires { container.size(); }) {
        return container.size();
    } else if constexpr (requires { std::size(container); }) {
        return std::size(container);
    } else {
        return 0;  // Fallback
    }
}

// --- Optimize based on type properties ---
template <typename Container>
void fast_clear(Container& c) {
    if constexpr (std::is_trivially_destructible_v<typename Container::value_type>) {
        // POD types: just reset size, skip destructors
        c.resize(0);
    } else {
        // Non-trivial: must call destructors
        c.clear();
    }
}

// --- Before C++17: SFINAE version (ugly) ---
// template <typename T>
// std::enable_if_t<std::is_arithmetic_v<T>, std::string>
// to_string_old(const T& v) { return std::to_string(v); }
//
// template <typename T>
// std::enable_if_t<std::is_same_v<T, std::string>, std::string>
// to_string_old(const T& v) { return v; }
// ... one overload per type — much harder to read

int main() {
    std::cout << to_string(42) << "\n";             // "42"
    std::cout << to_string(3.14) << "\n";           // "3.140000"
    std::cout << to_string(std::string("hi")) << "\n";

    print_all(1, "hello", 3.14, 'x');

    std::vector<int> v{1, 2, 3};
    int arr[] = {1, 2, 3, 4};
    std::cout << "vector size: " << get_size(v) << "\n";    // 3
    std::cout << "array size: " << get_size(arr) << "\n";   // 4
}
```

**Key insight:** The discarded branch is not instantiated. This is NOT the same as a runtime `if`:

```cpp
template <typename T>
void example(T val) {
    if constexpr (std::is_integral_v<T>) {
        val++;  // Only compiled when T is integral
    } else {
        val.process();  // Only compiled when T is NOT integral
        // Not an error even if int has no .process()
    }
}
```

**Replaces:** SFINAE, tag dispatch, `enable_if`, multiple overloads — with one clear function.'''
    ),
    (
        "cpp/user-defined-literals",
        r'''How do I create user-defined literals in C++? Show practical examples.''',
        r'''<think>
User-defined literals (UDLs) let you write 10_km, "hello"_s, etc.
They come in raw and cooked forms for different types.
The standard library has ""s for strings, ""sv for string_view, time literals.
Custom UDLs are great for units, strong types, and DSLs.
Must use the _suffix convention (no leading underscore — reserved for std).
I should show both string and numeric literal operators.
</think>

User-defined literals let you attach meaning to literal values like `100_km` or `"hello"_upper`:

```cpp
#include <iostream>
#include <string>
#include <string_view>
#include <chrono>
#include <cmath>

// --- Strong types with units ---
struct Meters {
    double value;
    friend std::ostream& operator<<(std::ostream& os, Meters m) {
        return os << m.value << "m";
    }
};
struct Kilometers {
    double value;
    operator Meters() const { return {value * 1000.0}; }
};

// Numeric literal operators
constexpr Meters operator""_m(long double val) {
    return {static_cast<double>(val)};
}
constexpr Meters operator""_m(unsigned long long val) {
    return {static_cast<double>(val)};
}
constexpr Kilometers operator""_km(long double val) {
    return {static_cast<double>(val)};
}

// --- String literal operator ---
std::string operator""_upper(const char* str, std::size_t len) {
    std::string result(str, len);
    for (auto& c : result) c = static_cast<char>(std::toupper(c));
    return result;
}

// --- Compile-time binary literals ---
consteval unsigned long long operator""_b(const char* str) {
    unsigned long long result = 0;
    while (*str) {
        result = (result << 1) | (*str++ - '0');
    }
    return result;
}

// --- Percentage type ---
struct Percent {
    double value;
    double of(double total) const { return total * value / 100.0; }
};
constexpr Percent operator""_pct(long double val) {
    return {static_cast<double>(val)};
}

int main() {
    // Unit-safe calculations
    Meters distance = 5.0_km;  // Implicit conversion: 5000m
    std::cout << distance << "\n";  // 5000m

    Meters height = 180_m;
    std::cout << height << "\n";  // 180m

    // String literals
    auto greeting = "hello world"_upper;
    std::cout << greeting << "\n";  // HELLO WORLD

    // Standard library literals
    using namespace std::string_literals;
    auto s = "std::string, not const char*"s;

    using namespace std::string_view_literals;
    auto sv = "zero-copy view"sv;

    using namespace std::chrono_literals;
    auto timeout = 500ms;
    auto duration = 2h + 30min + 15s;

    // Binary literals
    constexpr auto flags = 11010110_b;  // 214
    std::cout << "Binary: " << flags << "\n";

    // Percentage
    auto tax = 8.5_pct;
    std::cout << "Tax on $100: $" << tax.of(100.0) << "\n";  // $8.5
}
```

**Literal operator forms:**

| Form | Accepts | Example |
|------|---------|---------|
| `operator""_x(unsigned long long)` | Integer literals: `42_x` |
| `operator""_x(long double)` | Float literals: `3.14_x` |
| `operator""_x(const char*, size_t)` | String literals: `"hi"_x` |
| `operator""_x(char)` | Char literals: `'a'_x` |
| `operator""_x(const char*)` | Raw form (digit string): `123_x` as `"123"` |

**Rules:**
- User suffixes should NOT start with `_` followed by uppercase (reserved)
- Standard library uses no underscore (`s`, `sv`, `ms`)
- Use `constexpr`/`consteval` for compile-time evaluation'''
    ),
    (
        "cpp/deduction-guides",
        r'''What are deduction guides in C++17 and when do I need to write custom ones?''',
        r'''<think>
CTAD (Class Template Argument Deduction) lets you write vector v{1,2,3} instead of vector<int>.
Implicit deduction guides are generated from constructors automatically.
Custom deduction guides are needed when the constructor doesn't directly reveal the template args.
Common cases: string_view from string literals, container from iterator pairs.
I should show when implicit guides work, when they fail, and how to write explicit ones.
Keep examples practical with a wrapper class.
</think>

C++17 CTAD (Class Template Argument Deduction) lets you omit template arguments. Custom deduction guides tell the compiler how to deduce them when it can't figure it out from constructors:

```cpp
#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <array>

// --- Implicit guides work when constructors reveal the type ---
template <typename T>
struct Wrapper {
    T value;
    Wrapper(T v) : value(std::move(v)) {}  // Implicit guide: Wrapper(T) -> Wrapper<T>
};

// These just work:
// Wrapper w1(42);           // Wrapper<int>
// Wrapper w2(std::string("hi"));  // Wrapper<std::string>

// --- Problem: const char* deduces Wrapper<const char*>, not Wrapper<std::string> ---
// Wrapper w3("hello");  // Wrapper<const char*> — probably not what you want

// Fix with an explicit deduction guide:
Wrapper(const char*) -> Wrapper<std::string>;
// Now: Wrapper w3("hello") -> Wrapper<std::string>

// --- Custom guide for iterator-pair construction ---
template <typename T>
struct MyVec {
    std::vector<T> data;

    MyVec(std::initializer_list<T> init) : data(init) {}

    template <typename Iter>
    MyVec(Iter first, Iter last) : data(first, last) {}
};

// Iterator constructor can't deduce T — need a guide
template <typename Iter>
MyVec(Iter, Iter) -> MyVec<typename std::iterator_traits<Iter>::value_type>;

// --- Deduction guide for aggregate (C++20) ---
template <typename T, typename U>
struct Pair {
    T first;
    U second;
};
// C++20: aggregates get implicit deduction guides
// Pair p{42, "hello"};  // Pair<int, const char*>
// But we might want:
Pair(int, const char*) -> Pair<int, std::string>;

// --- Practical: type-erased function wrapper ---
template <typename Sig>
struct Callback;

template <typename Ret, typename... Args>
struct Callback<Ret(Args...)> {
    using FuncPtr = Ret(*)(Args...);
    FuncPtr fn;
    Callback(FuncPtr f) : fn(f) {}
    Ret operator()(Args... args) const { return fn(args...); }
};

// Guide: deduce signature from function pointer
template <typename Ret, typename... Args>
Callback(Ret(*)(Args...)) -> Callback<Ret(Args...)>;

int square(int x) { return x * x; }

int main() {
    // Implicit guide
    Wrapper w1(42);         // Wrapper<int>

    // Custom guide: const char* -> std::string
    Wrapper w2("hello");    // Wrapper<std::string> (not const char*!)
    std::cout << w2.value << "\n";

    // Iterator guide
    std::vector<int> src{1, 2, 3, 4, 5};
    MyVec mv(src.begin(), src.end());  // MyVec<int>

    // Standard library CTAD examples
    std::pair p{1, 3.14};           // pair<int, double>
    std::tuple t{1, "hi", 3.14};    // tuple<int, const char*, double>
    std::array a{1, 2, 3, 4};       // array<int, 4>

    // Function pointer guide
    Callback cb(square);  // Callback<int(int)>
    std::cout << cb(5) << "\n";  // 25
}
```

**When you need custom guides:**
1. **String literals:** `const char*` should become `std::string`
2. **Iterator pairs:** Can't deduce element type from iterator type alone
3. **Smart pointers from raw pointers:** `Ptr(new int)` → `Ptr<int>`
4. **Function signatures:** Deduce return/param types from function pointers

**When implicit guides suffice:** Constructor parameter types directly match template parameters (the common case).'''
    ),
    (
        "cpp/spaceship-operator-three-way-comparison",
        r'''How does the spaceship operator (<=>) work in C++20?''',
        r'''<think>
The three-way comparison operator (<=>) returns an ordering category.
It can auto-generate all six comparison operators from one declaration.
Three categories: strong_ordering, weak_ordering, partial_ordering.
= default generates memberwise comparison.
This dramatically reduces boilerplate for comparable types.
I should show default, custom, and the different ordering categories.
</think>

The spaceship operator `<=>` generates all six comparison operators from a single declaration:

```cpp
#include <compare>
#include <iostream>
#include <string>
#include <set>
#include <vector>
#include <algorithm>

// --- Default: compiler generates memberwise comparison ---
struct Point {
    int x, y;
    auto operator<=>(const Point&) const = default;
    // Generates: ==, !=, <, >, <=, >= (all six!)
};

// --- Custom three-way comparison ---
struct CaseInsensitiveString {
    std::string value;

    std::weak_ordering operator<=>(const CaseInsensitiveString& other) const {
        auto to_lower = [](std::string s) {
            for (auto& c : s) c = static_cast<char>(std::tolower(c));
            return s;
        };
        auto a = to_lower(value);
        auto b = to_lower(other.value);

        if (a < b) return std::weak_ordering::less;
        if (a > b) return std::weak_ordering::greater;
        return std::weak_ordering::equivalent;
        // weak_ordering: "Hello" == "hello" (equivalent but not identical)
    }

    // Must define == separately for case-insensitive equality
    bool operator==(const CaseInsensitiveString& other) const {
        return (*this <=> other) == 0;
    }
};

// --- Ordering categories ---
struct Temperature {
    double celsius;

    // partial_ordering because NaN is unordered
    std::partial_ordering operator<=>(const Temperature& other) const {
        return celsius <=> other.celsius;  // double uses partial_ordering
    }
    bool operator==(const Temperature& other) const = default;
};

// --- Mixed-type comparison ---
struct Dollars {
    int cents;

    auto operator<=>(const Dollars& other) const = default;

    // Compare Dollars with plain int (dollar amount)
    std::strong_ordering operator<=>(int dollars) const {
        return cents <=> (dollars * 100);
    }
    bool operator==(int dollars) const {
        return cents == dollars * 100;
    }
};

int main() {
    // Default spaceship
    Point a{1, 2}, b{1, 3};
    std::cout << (a < b) << "\n";   // 1 (lexicographic: x equal, 2 < 3)
    std::cout << (a == b) << "\n";  // 0

    std::set<Point> points{{3,1}, {1,2}, {1,1}};  // Sorted automatically

    // Case-insensitive
    CaseInsensitiveString s1{"Hello"}, s2{"hello"};
    std::cout << (s1 == s2) << "\n";  // 1
    std::cout << (s1 <=> s2 == 0) << "\n";  // 1

    // Mixed-type
    Dollars price{1500};
    std::cout << (price > 10) << "\n";   // 1 (1500 cents > 1000 cents)
    std::cout << (price == 15) << "\n";  // 1

    // Sorting with spaceship
    std::vector<Point> v{{3,1}, {1,2}, {2,0}};
    std::ranges::sort(v);  // Uses <=> automatically
}
```

**Ordering categories:**

| Category | Meaning | Example types |
|----------|---------|--------------|
| `strong_ordering` | Equal values are identical | `int`, `char`, `string` |
| `weak_ordering` | Equivalent but distinguishable | Case-insensitive strings |
| `partial_ordering` | Some values incomparable | `double` (NaN), partial orders |

**Key rules:**
- `= default` generates memberwise comparison in declaration order
- `<=>` auto-generates `<`, `>`, `<=`, `>=`
- `==` and `!=` are generated separately (from `operator==`, not `<=>`)
- If you define custom `<=>`, you usually need custom `==` too'''
    ),
    (
        "cpp/pmr-polymorphic-memory-resources",
        r'''What are polymorphic memory resources (PMR) in C++17? Show practical usage.''',
        r'''<think>
PMR provides runtime-polymorphic allocators via std::pmr namespace.
Key classes: memory_resource (base), monotonic_buffer_resource, pool_resource.
std::pmr::vector, std::pmr::string etc. use pmr::polymorphic_allocator.
Advantage over classic allocators: same container type regardless of allocator (no template parameter).
Practical for arena allocation, pools, and memory tracking without changing container types.
I should show monotonic_buffer_resource and unsynchronized_pool_resource.
</think>

PMR (C++17) provides runtime-swappable allocators without changing container types:

```cpp
#include <cstddef>
#include <iostream>
#include <memory_resource>
#include <string>
#include <vector>
#include <list>
#include <chrono>

// --- Basic: stack-backed vector (zero heap allocations) ---
void stack_allocation_example() {
    alignas(16) char buffer[4096];  // Stack memory
    std::pmr::monotonic_buffer_resource pool(buffer, sizeof(buffer));

    // This vector allocates from the stack buffer — no malloc!
    std::pmr::vector<int> v(&pool);
    for (int i = 0; i < 100; ++i) {
        v.push_back(i);
    }
    std::cout << "Stack vector size: " << v.size() << "\n";
    // When pool goes out of scope, ALL memory freed at once (no per-element dealloc)
}

// --- Custom memory resource: tracking allocator ---
class TrackingResource : public std::pmr::memory_resource {
    std::pmr::memory_resource* upstream_;
    std::size_t allocated_ = 0;
    std::size_t deallocated_ = 0;
    int alloc_count_ = 0;

protected:
    void* do_allocate(std::size_t bytes, std::size_t align) override {
        allocated_ += bytes;
        ++alloc_count_;
        return upstream_->allocate(bytes, align);
    }
    void do_deallocate(void* p, std::size_t bytes, std::size_t align) override {
        deallocated_ += bytes;
        upstream_->deallocate(p, bytes, align);
    }
    bool do_is_equal(const memory_resource& other) const noexcept override {
        return this == &other;
    }

public:
    explicit TrackingResource(std::pmr::memory_resource* up = std::pmr::get_default_resource())
        : upstream_(up) {}

    void report() const {
        std::cout << "Allocations: " << alloc_count_
                  << " | Allocated: " << allocated_
                  << " | Deallocated: " << deallocated_
                  << " | In-use: " << (allocated_ - deallocated_) << " bytes\n";
    }
};

// --- Key advantage: same type regardless of allocator ---
void process(std::pmr::vector<std::pmr::string>& data) {
    // Works with ANY underlying memory resource
    data.push_back("processed");
}

int main() {
    stack_allocation_example();

    // Tracking resource
    TrackingResource tracker;
    {
        std::pmr::vector<std::pmr::string> names(&tracker);
        names.push_back("Alice");
        names.push_back("Bob");
        names.push_back("Charlie");
        process(names);
        tracker.report();
    }
    std::cout << "After cleanup: ";
    tracker.report();

    // Pool resource (good for many same-sized allocations)
    std::pmr::unsynchronized_pool_resource pool;
    std::pmr::list<int> lst(&pool);
    for (int i = 0; i < 1000; ++i) {
        lst.push_back(i);  // Node allocations served from pools
    }

    // Monotonic + pool chain
    char buf[8192];
    std::pmr::monotonic_buffer_resource mono(buf, sizeof(buf));
    std::pmr::unsynchronized_pool_resource chained(&mono);
    // Pool allocates from monotonic → monotonic uses stack buffer
    // Overflow goes to default (heap)
}
```

**PMR resource types:**

| Resource | Behavior | Use case |
|----------|----------|----------|
| `monotonic_buffer_resource` | Bump allocator, free all at once | Per-frame, per-request |
| `unsynchronized_pool_resource` | Size-bucketed pools (single-thread) | Many same-sized allocs |
| `synchronized_pool_resource` | Thread-safe pool | Multi-threaded pools |
| Custom `memory_resource` | Your own logic | Tracking, debugging, NUMA |

**PMR vs classic allocators:**
- Classic: `vector<int, MyAlloc<int>>` — different type per allocator (can't mix)
- PMR: `pmr::vector<int>` — same type, swap allocator at runtime'''
    ),
    (
        "cpp/small-buffer-optimization",
        r'''What is Small Buffer Optimization (SBO) in C++ and how do I implement it?''',
        r'''<think>
SBO stores small objects inline (on stack) to avoid heap allocation.
std::string, std::function, and std::any all use SBO internally.
The idea: if the object fits in a buffer embedded in the class, use that; otherwise heap-allocate.
Implementation uses a union of a stack buffer and a heap pointer.
Need to handle construction, destruction, move, and copy correctly.
This is an advanced optimization technique — great for performance-critical code.
</think>

Small Buffer Optimization (SBO) avoids heap allocation for small objects by storing them inline. `std::string`, `std::function`, and `std::any` all use this technique internally.

```cpp
#include <cstddef>
#include <cstring>
#include <iostream>
#include <memory>
#include <new>
#include <type_traits>
#include <utility>

// Type-erased callable with SBO (simplified std::function)
class SmallFunction {
    static constexpr std::size_t BUF_SIZE = 48;  // Inline buffer size

    // Vtable for type-erased operations
    struct Ops {
        void (*destroy)(void* storage);
        void (*move)(void* dst, void* src);
        void (*call)(void* storage, int arg);
    };

    // Inline buffer OR heap pointer
    alignas(std::max_align_t) char buffer_[BUF_SIZE];
    const Ops* ops_ = nullptr;
    bool on_heap_ = false;

    void* storage() { return on_heap_ ? *reinterpret_cast<void**>(buffer_) : buffer_; }
    const void* storage() const { return on_heap_ ? *reinterpret_cast<void* const*>(buffer_) : buffer_; }

    template <typename F>
    static const Ops* get_ops() {
        static const Ops ops{
            [](void* s) { static_cast<F*>(s)->~F(); },
            [](void* d, void* s) { new (d) F(std::move(*static_cast<F*>(s))); },
            [](void* s, int arg) { (*static_cast<F*>(s))(arg); }
        };
        return &ops;
    }

public:
    SmallFunction() = default;

    template <typename F>
    SmallFunction(F func) {
        ops_ = get_ops<F>();
        if constexpr (sizeof(F) <= BUF_SIZE && std::is_nothrow_move_constructible_v<F>) {
            // SBO: construct in-place
            new (buffer_) F(std::move(func));
            on_heap_ = false;
        } else {
            // Too large: heap allocate
            auto* p = new F(std::move(func));
            std::memcpy(buffer_, &p, sizeof(p));
            on_heap_ = true;
        }
    }

    ~SmallFunction() {
        if (ops_) {
            ops_->destroy(storage());
            if (on_heap_) delete static_cast<char*>(storage());
        }
    }

    void operator()(int arg) {
        ops_->call(storage(), arg);
    }

    explicit operator bool() const { return ops_ != nullptr; }
};

int main() {
    // Small lambda — fits in SBO (no heap allocation)
    int multiplier = 3;
    SmallFunction small_fn([multiplier](int x) {
        std::cout << "Small: " << x * multiplier << "\n";
    });
    small_fn(10);  // Small: 30

    // Large lambda — forces heap allocation
    std::array<char, 128> big_capture{};
    SmallFunction big_fn([big_capture](int x) {
        std::cout << "Big: " << x << "\n";
    });
    big_fn(42);  // Big: 42
}
```

**How standard library types use SBO:**

| Type | Typical SBO size | Falls back to |
|------|-----------------|---------------|
| `std::string` | 15-22 bytes (SSO) | Heap allocation |
| `std::function` | ~32-48 bytes | Heap allocation |
| `std::any` | Implementation-defined | Heap allocation |

**Implementation checklist:**
1. **Alignment:** Buffer must be properly aligned (`alignas(std::max_align_t)`)
2. **Size check:** `sizeof(T) <= BUF_SIZE` at compile time with `if constexpr`
3. **Nothrow move:** SBO usually requires nothrow move (otherwise heap is safer)
4. **Placement new/destroy:** Manual lifetime management in the inline buffer
5. **Move semantics:** Move the buffer contents, not just the pointer

**When to use SBO:** Hot paths where small objects are common and heap allocation shows up in profiling (allocators, callbacks, variant-like types).'''
    ),
    (
        "cpp/compile-time-reflection-concepts-preview",
        r'''What's coming with compile-time reflection in C++26? Show what we can do today with concepts and traits.''',
        r'''<think>
C++26 reflection (P2996) adds the ^ operator to reflect on types, members, and enums at compile time.
It's not finalized yet, but the direction is clear from the proposals.
Today we approximate reflection with concepts, type_traits, and structured bindings.
I should show current techniques and preview what reflection will enable.
This is expert-level content about the cutting edge of C++.
Keep the preview speculative but grounded in actual proposals.
</think>

C++26 reflection (P2996) is on track to be the biggest metaprogramming upgrade since templates. Here's what we can do today and what's coming:

**Today: concepts + traits (C++20)**
```cpp
#include <concepts>
#include <iostream>
#include <string>
#include <type_traits>
#include <vector>
#include <tuple>

// --- Concepts: constrained templates with clear errors ---
template <typename T>
concept Serializable = requires(T obj, std::ostream& os) {
    { obj.serialize(os) } -> std::same_as<void>;
    { T::type_name() } -> std::convertible_to<std::string>;
};

template <typename T>
concept Arithmetic = std::is_arithmetic_v<T>;

template <typename T>
concept Container = requires(T c) {
    typename T::value_type;
    { c.begin() } -> std::input_or_output_iterator;
    { c.end() } -> std::input_or_output_iterator;
    { c.size() } -> std::convertible_to<std::size_t>;
};

// Use concepts directly in function signatures
void process(Container auto const& c) {
    std::cout << "Container with " << c.size() << " elements\n";
}

// --- Compile-time type inspection (current limits) ---
template <typename T>
void describe_type() {
    if constexpr (std::is_integral_v<T>)
        std::cout << "integral";
    else if constexpr (std::is_floating_point_v<T>)
        std::cout << "floating point";
    else if constexpr (std::is_class_v<T>)
        std::cout << "class type";
    else
        std::cout << "other";

    if constexpr (std::is_const_v<T>) std::cout << " (const)";
    if constexpr (std::is_pointer_v<T>) std::cout << " (pointer)";
    std::cout << "\n";
}

// --- Structured bindings for pseudo-reflection (limited to aggregates) ---
struct Config {
    int port;
    std::string host;
    bool debug;
};

template <typename T>
constexpr auto field_count() {
    // Hack: try binding with increasing count (fragile, but works for small structs)
    if constexpr (requires { auto [a, b, c] = T{}; }) return 3;
    else if constexpr (requires { auto [a, b] = T{}; }) return 2;
    else if constexpr (requires { auto [a] = T{}; }) return 1;
    else return 0;
}

int main() {
    std::vector<int> v{1, 2, 3};
    process(v);  // Container with 3 elements

    describe_type<int>();            // integral
    describe_type<const double>();   // floating point (const)

    std::cout << "Config has " << field_count<Config>() << " fields\n";  // 3
}
```

**C++26 reflection preview (P2996 — proposed syntax):**
```cpp
// NOTE: This is PROPOSED syntax, not yet standardized

#include <meta>  // New reflection header

struct Person {
    std::string name;
    int age;
    double height;
};

// Iterate over struct members at COMPILE TIME
template <typename T>
void auto_print(const T& obj) {
    // ^T reflects on type T, producing a meta::info
    template for (constexpr auto member : std::meta::members_of(^T)) {
        std::cout << std::meta::name_of(member) << " = "
                  << obj.[:member:]  // "splice" — access member by reflection
                  << "\n";
    }
}

// Auto-generate comparison, serialization, hashing from reflection
template <typename T>
auto auto_to_json(const T& obj) -> std::string {
    std::string json = "{";
    bool first = true;
    template for (constexpr auto m : std::meta::nonstatic_data_members_of(^T)) {
        if (!first) json += ", ";
        json += "\"" + std::string(std::meta::name_of(m)) + "\": ";
        json += to_json_value(obj.[:m:]);
        first = false;
    }
    return json + "}";
}

// Enum to string (the holy grail)
template <typename E> requires std::is_enum_v<E>
std::string enum_to_string(E value) {
    template for (constexpr auto e : std::meta::enumerators_of(^E)) {
        if (value == [:e:])
            return std::string(std::meta::name_of(e));
    }
    return "<unknown>";
}
```

**What reflection unlocks:**
- **Auto-serialization** — JSON/protobuf from struct definition alone
- **Enum-to-string** — no more manual `switch` statements
- **ORM mapping** — struct fields to SQL columns automatically
- **Debug printing** — `auto_print(any_struct)` just works
- **Dependency injection** — inspect constructor parameters

**Timeline:** P2996 is targeting C++26. Clang has experimental support via `-freflection`.'''
    ),
]
