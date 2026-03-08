"""C++ deep reasoning pairs batch 1: memory and ownership."""
PAIRS = [
    ("cpp_deep/raii_file_handle_custom_deleter", r'''How do I implement RAII for file handles in modern C++ using a custom deleter? I want something safer than raw FILE* pointers.''', r'''<think>
The user wants RAII-managed FILE* handles. Let me think through the options.

Option 1: Wrap in a class with destructor. Works but verbose — rule of five kicks in.
Option 2: Use unique_ptr with a custom deleter. Elegant, zero-overhead if we use a function pointer or stateless lambda... wait, actually a function pointer deleter increases unique_ptr size to 2 pointers. A stateless functor/lambda keeps it at 1 pointer. That matters.

What about error handling? fclose() can fail (returns EOF on error, flushes buffers). In a destructor we can't throw. We could log, but silently ignoring flush errors is a real data-loss risk. So maybe we should offer an explicit close() that CAN throw, and the destructor is the fallback.

Should I use fopen or the C++ fstream? The user specifically said FILE*, so they probably need C interop (e.g., calling a C library that takes FILE*). Let me stick with FILE*.

For the deleter: a struct with operator() is cleanest — zero size overhead, inlineable, and self-documenting. I'll also add a factory function that returns nullopt on failure rather than throwing, giving the caller choice.

One gotcha: if fopen returns nullptr, we shouldn't wrap that. unique_ptr handles nullptr fine (won't call deleter), but semantically we should signal failure. I'll use std::optional or expected.

Let me also consider thread safety. FILE* operations are thread-safe per-handle in POSIX, but not on all platforms. That's outside scope here — just mention it.

Self-correction: I was going to use std::expected but that's C++23. Let me provide both a C++17 version with optional and note the C++23 alternative.
</think>

Here is a complete, compilable RAII file handle using `unique_ptr` with a custom deleter:

```cpp
#include <cstdio>
#include <memory>
#include <optional>
#include <string>
#include <stdexcept>
#include <iostream>

// Stateless functor deleter — sizeof(unique_ptr) remains 1 pointer
struct FileCloser {
    void operator()(std::FILE* fp) const noexcept {
        if (fp) {
            // fclose can fail (flush error), but we cannot throw in a deleter.
            // Best-effort: log on failure.
            if (std::fclose(fp) != 0) {
                std::perror("FileCloser: fclose failed (possible data loss)");
            }
        }
    }
};

using UniqueFile = std::unique_ptr<std::FILE, FileCloser>;

// Factory: returns empty optional on failure instead of throwing
[[nodiscard]]
std::optional<UniqueFile> open_file(const std::string& path, const char* mode) {
    std::FILE* raw = std::fopen(path.c_str(), mode);
    if (!raw) {
        return std::nullopt;
    }
    return UniqueFile{raw};
}

// Alternative factory: throws on failure
[[nodiscard]]
UniqueFile open_file_or_throw(const std::string& path, const char* mode) {
    std::FILE* raw = std::fopen(path.c_str(), mode);
    if (!raw) {
        throw std::runtime_error("Failed to open: " + path);
    }
    return UniqueFile{raw};
}

int main() {
    // Safe usage — file closes automatically at scope exit
    if (auto file = open_file("test_output.txt", "w")) {
        std::fprintf(file->get(), "Hello from RAII FILE*!\n");
        std::fprintf(file->get(), "No leak, guaranteed.\n");
        // Explicit close before destructor if you need error checking:
        // file->reset();
    } else {
        std::cerr << "Could not open file\n";
    }

    // Throwing variant
    try {
        auto f = open_file_or_throw("test_output.txt", "r");
        char buf[256];
        while (std::fgets(buf, sizeof(buf), f.get())) {
            std::fputs(buf, stdout);
        }
    } catch (const std::runtime_error& e) {
        std::cerr << e.what() << '\n';
    }

    return 0;
}
```

**Key design decisions:**

- **Stateless functor deleter** (`FileCloser`): keeps `sizeof(UniqueFile) == sizeof(FILE*)`. A `std::function` or capturing lambda would double the size.
- **`fclose` error in destructor**: logged, not thrown. If flush-on-close matters (write mode), call `.reset()` explicitly and check `errno`.
- **Factory returns `optional`**: caller decides how to handle failure without forcing exceptions into non-exceptional control flow.
- **`[[nodiscard]]`**: prevents accidentally ignoring the returned handle (which would immediately close the file).'''),

    ("cpp_deep/unique_ptr_polymorphic_custom_deleter", r'''Show me how to use unique_ptr with polymorphic types and custom deleters in C++17. I'm confused about when the deleter needs to know the concrete type.''', r'''<think>
This is a subtle topic. The key question: does unique_ptr call the deleter with the static type or the stored pointer type?

unique_ptr<Base> stores a Base*. When it destructs, it calls deleter(stored_pointer), where stored_pointer is Base*. If Base doesn't have a virtual destructor and we stored a Derived*, we get UB — the standard says deleting through a base pointer without virtual destructor is undefined.

But wait — with a custom deleter, we're NOT calling delete. We're calling our own function. So if we capture the concrete type in the deleter at construction time, we can safely destroy without a virtual destructor. This is actually how shared_ptr works — it type-erases the deleter. Can we do the same with unique_ptr?

Yes! We can use a type-erased deleter like std::function<void(Base*)> and capture the concrete type at creation time. But this has overhead — std::function allocates, and unique_ptr's size grows.

Alternative: just make the destructor virtual. That's the standard approach and nearly zero overhead (one vtable pointer, one indirect call). The custom deleter approach is only worth it in specific scenarios like: the type comes from a C library, or you're working with incomplete types, or you need a specific deallocation strategy (pool, arena).

Let me show both approaches: virtual destructor (preferred) and type-erased deleter (when you can't modify the base class). I should also mention that unique_ptr<Derived> implicitly converts to unique_ptr<Base> ONLY when Base has a virtual destructor or a compatible deleter.

Actually, correction: the implicit conversion works regardless of virtual destructor — the compiler doesn't check that. It's the programmer's responsibility. That's a common source of bugs.

Let me demonstrate the UB case too, so the user understands why it matters.
</think>

Here is a complete example showing both the standard approach and the type-erased deleter technique:

```cpp
#include <memory>
#include <iostream>
#include <functional>

// === APPROACH 1: Virtual destructor (preferred) ===

struct Animal {
    virtual ~Animal() = default;  // Makes polymorphic delete safe
    virtual void speak() const = 0;
};

struct Dog : Animal {
    std::string name;
    Dog(std::string n) : name(std::move(n)) {
        std::cout << "Dog(" << name << ") born\n";
    }
    ~Dog() override { std::cout << "Dog(" << name << ") destroyed\n"; }
    void speak() const override { std::cout << name << " says Woof!\n"; }
};

struct Cat : Animal {
    ~Cat() override { std::cout << "Cat destroyed\n"; }
    void speak() const override { std::cout << "Meow!\n"; }
};

// === APPROACH 2: Type-erased deleter (when base is not yours) ===

// Imagine this comes from a C library — you cannot add virtual destructor
struct Sensor {
    int id;
    // NO virtual destructor — not your code to modify
};

struct TemperatureSensor : Sensor {
    double calibration_offset;
    std::string label;
    TemperatureSensor(int i, double off, std::string l)
        : Sensor{i}, calibration_offset(off), label(std::move(l)) {
        std::cout << "TempSensor(" << label << ") created\n";
    }
    ~TemperatureSensor() {
        std::cout << "TempSensor(" << label << ") destroyed\n";
    }
};

// Type-erased deleter: captures concrete type at creation, erases it behind std::function
using Deleter = std::function<void(Sensor*)>;
using PolySensor = std::unique_ptr<Sensor, Deleter>;

template <typename Derived, typename... Args>
PolySensor make_poly_sensor(Args&&... args) {
    auto* p = new Derived(std::forward<Args>(args)...);
    return PolySensor(p, [](Sensor* base) {
        // The lambda captures the knowledge that base is really Derived*
        delete static_cast<Derived*>(base);
    });
}

// === APPROACH 3: Stateless deleter with concrete type baked in ===
// Zero-overhead but requires template propagation

template <typename Derived>
struct ConcreteDeleter {
    void operator()(Sensor* p) const noexcept {
        delete static_cast<Derived*>(p);
    }
};

int main() {
    std::cout << "=== Approach 1: virtual destructor (standard) ===\n";
    {
        // unique_ptr<Derived> converts to unique_ptr<Base> — safe due to virtual dtor
        std::unique_ptr<Animal> a = std::make_unique<Dog>("Rex");
        a->speak();
        // ~Dog() called correctly through virtual dispatch
    }

    std::cout << "\n=== Approach 2: type-erased deleter ===\n";
    {
        PolySensor s = make_poly_sensor<TemperatureSensor>(42, 0.5, "Lab-A");
        std::cout << "Sensor id: " << s->id << "\n";
        // ~TemperatureSensor() called correctly via captured static_cast
    }

    std::cout << "\n=== Polymorphic container with type-erased deleters ===\n";
    {
        std::vector<PolySensor> sensors;
        sensors.push_back(make_poly_sensor<TemperatureSensor>(1, 0.1, "S1"));
        sensors.push_back(make_poly_sensor<TemperatureSensor>(2, 0.2, "S2"));
        // All destroyed correctly when vector goes out of scope
    }

    std::cout << "\nDone.\n";
    return 0;
}
```

**When to use which:**

| Approach | Overhead | When to use |
|----------|----------|-------------|
| Virtual destructor | 1 vptr per object, 1 indirect call | You own the base class (95% of cases) |
| `std::function` deleter | ~32 bytes per `unique_ptr` + possible heap alloc | Base is from external library, need container of mixed types |
| Template deleter struct | Zero (stateless) | Base is external, but you don't need type erasure in containers |

**The trap**: `unique_ptr<Base> p = make_unique<Derived>(...)` compiles even without a virtual destructor. The compiler does not warn you. The resulting `delete` through `Base*` is silent undefined behavior — often appears to "work" but corrupts memory or skips `Derived`'s destructor.'''),

    ("cpp_deep/shared_ptr_control_block_overhead", r'''What's the actual memory overhead of shared_ptr? I've heard it has a "control block" — what's in it and when does it matter?''', r'''<think>
Let me think through the shared_ptr control block layout carefully.

A shared_ptr<T> itself is two pointers: one to the managed object, one to the control block. So sizeof(shared_ptr<T>) == 2 * sizeof(void*) = 16 bytes on 64-bit. That's already 2x the size of a raw pointer or unique_ptr.

The control block contains:
1. Strong reference count (atomic — typically 4 or 8 bytes)
2. Weak reference count (atomic — same)
3. Deleter (if custom — type-erased, so it depends)
4. Allocator (if custom — type-erased)
5. Virtual destructor mechanism (vtable pointer) for type erasure
6. If make_shared: the object itself is embedded in the control block

So minimum control block: vtable ptr (8) + strong count (8 aligned) + weak count (8) = ~24 bytes on 64-bit. Plus padding. In practice GCC/libstdc++ and MSVC control blocks are around 16-32 bytes for the counts + vtable.

make_shared vs shared_ptr(new T):
- shared_ptr(new T): TWO allocations — one for T, one for control block. Object and control block at different addresses. Cache-unfriendly.
- make_shared: ONE allocation — control block and T are colocated. But! The entire block (including T's storage) lives until the last weak_ptr dies, even if all shared_ptrs are gone. This can be a hidden memory issue.

When does overhead matter?
- Millions of small objects (e.g., nodes in a graph): the per-object overhead dominates. A 4-byte int costs 40+ bytes total under shared_ptr.
- Atomic ref counting: every copy/destroy does an atomic increment/decrement. On x86 that's a LOCK prefix — not free, especially under contention.
- Cache: two-pointer shared_ptr means less fits in cache vs raw pointers.

I should show the actual sizes with a program that prints them out, and demonstrate the make_shared vs new difference.

Wait, should I mention enable_shared_from_this? It embeds a weak_ptr in the object itself, adding another ~16 bytes. That's relevant to overhead discussion.
</think>

Here is a program that reveals the actual overhead of `shared_ptr` on your platform:

```cpp
#include <memory>
#include <iostream>
#include <string>
#include <vector>
#include <cstdint>

struct Tiny { int x; }; // 4 bytes of actual data

struct WithSharedFromThis : std::enable_shared_from_this<WithSharedFromThis> {
    int x;
};

// Custom deleter to show its effect on control block
struct LoggingDeleter {
    std::string tag;  // non-trivial state in deleter
    void operator()(Tiny* p) const {
        std::cout << "[" << tag << "] deleting Tiny\n";
        delete p;
    }
};

// Helper: estimate control block size by comparing allocations
static std::size_t g_total_allocated = 0;
static int g_alloc_count = 0;

void* operator new(std::size_t n) {
    g_total_allocated += n;
    g_alloc_count++;
    return std::malloc(n);
}

void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

void reset_counters() { g_total_allocated = 0; g_alloc_count = 0; }

int main() {
    std::cout << "=== Pointer sizes ===\n";
    std::cout << "sizeof(Tiny):              " << sizeof(Tiny) << "\n";
    std::cout << "sizeof(Tiny*):             " << sizeof(Tiny*) << "\n";
    std::cout << "sizeof(unique_ptr<Tiny>):  " << sizeof(std::unique_ptr<Tiny>) << "\n";
    std::cout << "sizeof(shared_ptr<Tiny>):  " << sizeof(std::shared_ptr<Tiny>) << "\n";
    std::cout << "sizeof(weak_ptr<Tiny>):    " << sizeof(std::weak_ptr<Tiny>) << "\n";

    std::cout << "\n=== shared_ptr(new T) — two allocations ===\n";
    reset_counters();
    {
        auto p = std::shared_ptr<Tiny>(new Tiny{42});
        std::cout << "Allocations: " << g_alloc_count << "\n";
        std::cout << "Total bytes: " << g_total_allocated << "\n";
        std::cout << "Overhead:    " << (g_total_allocated - sizeof(Tiny)) << " bytes\n";
    }

    std::cout << "\n=== make_shared<T> — single allocation ===\n";
    reset_counters();
    {
        auto p = std::make_shared<Tiny>(42);
        std::cout << "Allocations: " << g_alloc_count << "\n";
        std::cout << "Total bytes: " << g_total_allocated << "\n";
        std::cout << "Overhead:    " << (g_total_allocated - sizeof(Tiny)) << " bytes\n";
    }

    std::cout << "\n=== shared_ptr with custom deleter ===\n";
    reset_counters();
    {
        auto p = std::shared_ptr<Tiny>(new Tiny{42}, LoggingDeleter{"myTag"});
        std::cout << "Allocations: " << g_alloc_count << "\n";
        std::cout << "Total bytes: " << g_total_allocated << "\n";
    }

    std::cout << "\n=== enable_shared_from_this overhead ===\n";
    std::cout << "sizeof(WithSharedFromThis): " << sizeof(WithSharedFromThis) << "\n";
    std::cout << "  (vs plain int:            " << sizeof(int) << ")\n";
    std::cout << "  embedded weak_ptr adds:   "
              << (sizeof(WithSharedFromThis) - sizeof(int)) << " bytes\n";

    std::cout << "\n=== Scalability: 1M shared_ptr<int> vs raw int ===\n";
    constexpr int N = 1'000'000;
    std::cout << "Raw array:      " << (N * sizeof(int)) / 1024 << " KB\n";
    std::cout << "shared_ptr arr: ~" << (N * (sizeof(std::shared_ptr<int>) + 40)) / 1024
              << " KB (ptrs + control blocks)\n";
    std::cout << "Ratio:          ~"
              << (sizeof(std::shared_ptr<int>) + 40) / static_cast<double>(sizeof(int))
              << "x\n";

    return 0;
}
```

**Typical output (64-bit, libstdc++):**

| What | Bytes |
|------|-------|
| `sizeof(shared_ptr<T>)` | 16 (2 pointers) |
| Control block (make_shared) | ~32 bytes |
| Control block (new + separate) | ~24-32 bytes (separate alloc) |
| `enable_shared_from_this` | +16 bytes in object |

**When the overhead matters:**
1. **Millions of small objects** (graph nodes, particles): 14x overhead for a 4-byte int is devastating.
2. **Atomic ref counting under contention**: each copy/destroy is a `LOCK XADD` — measurable in tight loops.
3. **make_shared + weak_ptr trap**: the object's memory is not freed until all `weak_ptr`s die, because the object is embedded in the control block.

**Rule of thumb**: if you're storing more than ~10K `shared_ptr` to small objects, reconsider your ownership model. Arenas, intrusive reference counting, or `unique_ptr` with clear ownership often outperform.'''),

    ("cpp_deep/weak_ptr_observer_pattern_cycles", r'''Show me how to use weak_ptr to implement the observer pattern in C++ while breaking reference cycles. I keep getting crashes from dangling observer pointers.''', r'''<think>
The observer pattern has a classic cycle problem: Subject holds references to Observers, Observers hold references back to the Subject. If both use shared_ptr, neither can be destroyed.

The standard solution: Subject holds weak_ptr<Observer>. When notifying, lock() each weak_ptr. If lock() returns nullptr, the observer is dead — remove it from the list. This is "self-cleaning" observer.

But there's a subtlety: who owns the observers? If nothing else holds a shared_ptr to them, they die immediately. The pattern requires that observer lifetime is managed externally (e.g., by the GUI framework, game engine, etc.). The subject just holds weak references.

What about thread safety? If observers can be added/removed from different threads while notification is happening, we need synchronization. For simplicity I'll use a mutex, but note that calling observer->on_event() while holding the mutex risks deadlock if the observer tries to unsubscribe in its callback. Classic solution: copy the list under the lock, then iterate the copy without the lock.

Another issue: what if an observer unsubscribes during notification? With the copy-and-iterate approach, the callback still fires for that iteration but the observer gets removed for next time. That's usually acceptable.

Let me also think about the return type of subscribe(). Returning a raw subscription token is error-prone. Better: return a shared_ptr<void> as a "subscription handle" — when the caller drops it, the observer is automatically unsubscribed (because the weak_ptr in the subject expires). Actually wait, that conflates observer lifetime with subscription lifetime. Sometimes you want an observer to exist but not be subscribed. Let me keep it simple: subscribe returns void, unsubscribe takes an observer pointer.

Actually, the cleanest modern approach: subscribe() returns a "connection" RAII object. When the connection dies, the subscription is canceled. Like Boost.Signals2. But that's complex. Let me show the weak_ptr self-cleaning approach which is the direct answer to the question.

Self-correction: I should make Observer itself be managed by shared_ptr and have Subject store weak_ptr<Observer>. That way when external code drops the last shared_ptr to an observer, the subject's weak_ptr expires naturally.
</think>

Here is a complete, thread-aware observer pattern using `weak_ptr` for automatic cycle breaking:

```cpp
#include <memory>
#include <vector>
#include <string>
#include <iostream>
#include <algorithm>
#include <mutex>
#include <functional>

// Forward declaration
class Subject;

// Observer interface — must be managed by shared_ptr
class Observer : public std::enable_shared_from_this<Observer> {
public:
    virtual ~Observer() = default;
    virtual void on_event(const std::string& event) = 0;
};

// Subject holds weak_ptrs to observers — never prevents their destruction
class Subject {
    mutable std::mutex mtx_;
    std::vector<std::weak_ptr<Observer>> observers_;

    // Remove expired weak_ptrs (call under lock)
    void purge_expired() {
        observers_.erase(
            std::remove_if(observers_.begin(), observers_.end(),
                [](const std::weak_ptr<Observer>& wp) { return wp.expired(); }),
            observers_.end()
        );
    }

public:
    void subscribe(std::shared_ptr<Observer> obs) {
        std::lock_guard lock(mtx_);
        purge_expired();
        // Prevent double-subscribe
        for (const auto& wp : observers_) {
            if (auto sp = wp.lock(); sp == obs) return;
        }
        observers_.push_back(obs);
    }

    void unsubscribe(const std::shared_ptr<Observer>& obs) {
        std::lock_guard lock(mtx_);
        observers_.erase(
            std::remove_if(observers_.begin(), observers_.end(),
                [&obs](const std::weak_ptr<Observer>& wp) {
                    auto sp = wp.lock();
                    return !sp || sp == obs;
                }),
            observers_.end()
        );
    }

    void notify(const std::string& event) {
        // Copy live observers under lock, then notify without lock
        // This prevents deadlock if a callback tries to unsubscribe
        std::vector<std::shared_ptr<Observer>> live;
        {
            std::lock_guard lock(mtx_);
            purge_expired();
            live.reserve(observers_.size());
            for (auto& wp : observers_) {
                if (auto sp = wp.lock()) {
                    live.push_back(std::move(sp));
                }
            }
        }
        // No lock held — safe for callbacks to call subscribe/unsubscribe
        for (auto& obs : live) {
            obs->on_event(event);
        }
    }

    std::size_t observer_count() const {
        std::lock_guard lock(mtx_);
        std::size_t count = 0;
        for (auto& wp : observers_) {
            if (!wp.expired()) ++count;
        }
        return count;
    }
};

// Concrete observers
class Logger : public Observer {
    std::string name_;
public:
    explicit Logger(std::string name) : name_(std::move(name)) {
        std::cout << "[Logger:" << name_ << "] created\n";
    }
    ~Logger() override {
        std::cout << "[Logger:" << name_ << "] destroyed\n";
    }
    void on_event(const std::string& event) override {
        std::cout << "[Logger:" << name_ << "] received: " << event << "\n";
    }
};

int main() {
    Subject subject;

    auto log_a = std::make_shared<Logger>("A");
    auto log_b = std::make_shared<Logger>("B");

    subject.subscribe(log_a);
    subject.subscribe(log_b);
    std::cout << "Observers: " << subject.observer_count() << "\n";

    subject.notify("event-1");

    std::cout << "\n--- Dropping Logger B (simulating scope exit) ---\n";
    log_b.reset();  // B is destroyed; weak_ptr in subject expires automatically

    std::cout << "Observers after B dropped: " << subject.observer_count() << "\n";
    subject.notify("event-2");  // Only A receives this

    std::cout << "\n--- Dropping Logger A ---\n";
    log_a.reset();

    std::cout << "Observers after all dropped: " << subject.observer_count() << "\n";
    subject.notify("event-3");  // No one receives this, no crash

    std::cout << "\nNo dangling pointers. No crashes. No cycles.\n";
    return 0;
}
```

**Why this is crash-proof:**
- `weak_ptr::lock()` atomically checks and promotes — no TOCTOU race.
- Dead observers are automatically pruned; no stale raw pointers.
- No reference cycle: Subject -> `weak_ptr<Observer>` does not extend Observer lifetime.
- Copy-then-notify pattern prevents deadlock if callbacks modify the observer list.'''),

    ("cpp_deep/make_unique_exception_safety", r'''Why is make_unique preferred over "new" with unique_ptr? I've heard it's about exception safety but I don't understand the argument.''', r'''<think>
The classic exception safety argument is about function arguments. Consider:

    process(std::unique_ptr<Foo>(new Foo), bar());

Before C++17, argument evaluation order was unspecified. The compiler could:
1. new Foo
2. call bar()        ← if this throws, Foo leaks!
3. construct unique_ptr

With make_unique:
    process(std::make_unique<Foo>(), bar());

make_unique is a single function call. The allocation and unique_ptr construction happen atomically inside make_unique. So even if bar() is evaluated between make_unique's return and process's call... wait, actually make_unique returns a unique_ptr by value, so the allocation is always wrapped by the time the next argument is evaluated.

But wait — C++17 fixed this! In C++17, function arguments are indeterminately sequenced but each argument's side effects are completed before the next begins. So the leak in the pre-C++17 example is no longer possible.

Does that mean make_unique is unnecessary? No! There are other benefits:
1. No redundant type repetition: make_unique<Foo>(args) vs unique_ptr<Foo>(new Foo(args))
2. No accidental mismatch: new Foo[] with non-array unique_ptr
3. Consistency with make_shared
4. Grep-ability: if you ban naked "new" in code review, make_unique enables that

But make_unique has limitations:
- Can't use custom deleters
- Can't adopt a pointer from C API (need unique_ptr(raw_ptr, deleter))
- Can't use list initialization (make_unique uses parentheses, not braces)
- For make_shared: the combined allocation means memory isn't freed until weak_ptrs die

I should show the pre-C++17 leak scenario concretely, then explain why make_unique is still preferred even in C++17+.

Self-correction: I said C++17 fixed argument evaluation. Let me be precise: C++17 says each argument expression is indeterminately sequenced (fully evaluated before or after other arguments), not interleaved. So "new Foo" and "construct unique_ptr" in a single argument expression are still sequenced together. The leak was from interleaving ACROSS arguments. Yes, C++17 fixes it but make_unique remains best practice.
</think>

Here is a program that demonstrates the exception safety issue and why `make_unique` remains best practice:

```cpp
#include <memory>
#include <iostream>
#include <stdexcept>

struct Resource {
    int id;
    Resource(int i) : id(i) { std::cout << "Resource(" << id << ") allocated\n"; }
    ~Resource() { std::cout << "Resource(" << id << ") freed\n"; }
};

// A function that might throw
int maybe_throws(bool do_throw) {
    if (do_throw) {
        std::cout << "  >> throwing exception!\n";
        throw std::runtime_error("boom");
    }
    return 42;
}

// Takes two arguments — the classic problem case
void process(std::unique_ptr<Resource> r, int value) {
    std::cout << "Processing resource " << r->id << " with value " << value << "\n";
}

// =====================================================
// THE PROBLEM (pre-C++17, still bad style in C++17+)
// =====================================================
// process(std::unique_ptr<Resource>(new Resource(1)), maybe_throws(true));
//
// Pre-C++17, compiler COULD evaluate as:
//   Step 1: new Resource(1)            → raw pointer on heap
//   Step 2: maybe_throws(true)         → THROWS! Stack unwinds.
//   Step 3: unique_ptr(raw_ptr)        → NEVER REACHED. Resource leaked!
//
// C++17 guarantees each argument fully evaluates before the next,
// so this specific interleaving can't happen. BUT...

// =====================================================
// WHY make_unique IS STILL PREFERRED (even in C++17+)
// =====================================================
void demonstrate_safety() {
    // BAD: type repetition, easy to get wrong
    // std::unique_ptr<Resource>(new Resource(1))   // "Resource" written twice
    // std::unique_ptr<Resource>(new DerivedResource(1))  // easy mismatch

    // GOOD: single source of truth for the type
    auto r = std::make_unique<Resource>(1);
    std::cout << "Resource " << r->id << " safely created\n";
}

// make_unique LIMITATIONS — when you can't use it:
struct CHandle {
    int fd;
};

void c_api_cleanup(CHandle* h) {
    std::cout << "C API cleanup for fd=" << h->fd << "\n";
    delete h;  // or free(), or custom API call
}

void show_limitations() {
    // 1. Custom deleter — must use constructor directly
    auto h = std::unique_ptr<CHandle, decltype(&c_api_cleanup)>(
        new CHandle{42}, &c_api_cleanup
    );

    // 2. Brace initialization — make_unique uses () not {}
    // auto v = std::make_unique<std::vector<int>>({1,2,3});  // WON'T COMPILE
    auto v = std::make_unique<std::vector<int>>(std::initializer_list<int>{1, 2, 3});

    // 3. Array form works differently
    auto arr = std::make_unique<int[]>(10);  // 10 value-initialized ints
    arr[0] = 42;
}

int main() {
    // Safe version — make_unique wraps allocation atomically
    try {
        process(std::make_unique<Resource>(1), maybe_throws(false));
    } catch (...) {}

    std::cout << "\n--- Now with exception ---\n";
    try {
        // Even if argument order is unspecified, make_unique ensures
        // the Resource is ALWAYS inside a unique_ptr before anything
        // else can throw.
        process(std::make_unique<Resource>(2), maybe_throws(true));
    } catch (const std::runtime_error& e) {
        std::cout << "Caught: " << e.what() << "\n";
        std::cout << "Resource was properly cleaned up (check output above)\n";
    }

    std::cout << "\n--- Demonstrating safety ---\n";
    demonstrate_safety();

    std::cout << "\n--- Limitations ---\n";
    show_limitations();

    return 0;
}
```

**Summary of reasons to prefer `make_unique`:**

| Reason | Applies in | Importance |
|--------|-----------|------------|
| Exception safety (argument eval) | Pre-C++17 | Critical |
| No type repetition | All versions | Readability |
| Enables `new`-free codebases | All versions | Code review |
| No array/non-array mismatch | All versions | Correctness |
| Consistency with `make_shared` | All versions | Consistency |

**When you must use the constructor:**
- Custom deleters (C API handles, pool allocators)
- Adopting existing raw pointers
- Brace-initialization edge cases'''),

    ("cpp_deep/movable_only_type", r'''How do I implement a movable-only type in modern C++? When would I want one, and what happens if I accidentally copy it?''', r'''<think>
A movable-only type is one where copy is deleted but move is defined. Classic examples: unique_ptr, thread, fstream, unique_lock.

When do you want this? When the object represents exclusive ownership of a resource — a file handle, a socket, a GPU buffer, a thread. Copying would mean two owners, violating the exclusivity invariant.

Implementation: delete copy constructor and copy assignment, define move constructor and move assignment. The moved-from state must be valid (destructible, assignable). A common pattern is to set the resource handle to a sentinel (nullptr, -1, etc.) in the moved-from object.

What happens if you try to copy? Compile error. That's the whole point — the compiler enforces ownership semantics.

Gotchas:
1. Can't put movable-only types in some containers that require copyability (e.g., older APIs). But since C++11, standard containers work with move-only types for most operations.
2. std::vector<MoveOnly>::push_back needs std::move() or emplace_back.
3. Returning from functions works because of copy elision / implicit move.
4. Lambda captures: can't capture move-only types by value in pre-C++14. In C++14+, use init-capture: [x = std::move(x)](...){}.

Let me implement a concrete example: a UniqueSocket class that wraps a file descriptor (or SOCKET on Windows). I'll show the deleted copies generating compile errors, proper move semantics, and container usage.

One subtlety: if you declare move operations, should you also declare the destructor? Yes — rule of five says if you declare any special member function, declare all five. But since we're deleting two (copy ctor, copy assign), we declare 5 total: 2 deleted, 2 defined (move), 1 defined (destructor).
</think>

Here is a complete move-only type with all the nuances:

```cpp
#include <iostream>
#include <vector>
#include <algorithm>
#include <utility>
#include <functional>
#include <cassert>

// Move-only type: represents exclusive ownership of a system resource
class UniqueBuffer {
    int* data_;
    std::size_t size_;

    static int instance_count;  // Track for leak detection

public:
    // Constructor: acquires resource
    explicit UniqueBuffer(std::size_t size)
        : data_(new int[size]{}), size_(size) {
        ++instance_count;
        std::cout << "  Acquired buffer[" << size_ << "] @ " << data_
                  << " (live: " << instance_count << ")\n";
    }

    // Destructor: releases resource
    ~UniqueBuffer() {
        if (data_) {
            std::cout << "  Released buffer[" << size_ << "] @ " << data_
                      << " (live: " << instance_count - 1 << ")\n";
            delete[] data_;
            --instance_count;
        }
        // moved-from objects have data_ == nullptr, no action needed
    }

    // === COPY: DELETED ===
    UniqueBuffer(const UniqueBuffer&) = delete;
    UniqueBuffer& operator=(const UniqueBuffer&) = delete;

    // === MOVE: DEFINED ===
    UniqueBuffer(UniqueBuffer&& other) noexcept
        : data_(other.data_), size_(other.size_) {
        // Pilfer resources, leave other in valid empty state
        other.data_ = nullptr;
        other.size_ = 0;
        std::cout << "  Moved buffer @ " << data_ << "\n";
    }

    UniqueBuffer& operator=(UniqueBuffer&& other) noexcept {
        if (this != &other) {  // Self-move check
            // Release current resource
            delete[] data_;
            // Pilfer from other
            data_ = other.data_;
            size_ = other.size_;
            other.data_ = nullptr;
            other.size_ = 0;
            std::cout << "  Move-assigned buffer @ " << data_ << "\n";
        }
        return *this;
    }

    // Accessors
    int& operator[](std::size_t i) { return data_[i]; }
    const int& operator[](std::size_t i) const { return data_[i]; }
    std::size_t size() const { return size_; }
    bool valid() const { return data_ != nullptr; }
    explicit operator bool() const { return valid(); }

    static int live_count() { return instance_count; }
};

int UniqueBuffer::instance_count = 0;

// Factory function — return by value (move or copy elision)
UniqueBuffer create_buffer(std::size_t n) {
    UniqueBuffer buf(n);
    buf[0] = 42;
    return buf;  // NRVO or implicit move — no copy needed
}

// Sink function — takes ownership via move
void consume(UniqueBuffer buf) {
    std::cout << "  Consumed buffer of size " << buf.size() << "\n";
    // buf destroyed at end of scope
}

int main() {
    std::cout << "=== Construction ===\n";
    auto a = create_buffer(10);  // NRVO: likely zero moves
    assert(a.valid());

    std::cout << "\n=== Move construction ===\n";
    auto b = std::move(a);  // a is now in moved-from state
    assert(!a.valid());     // moved-from: valid but empty
    assert(b.valid());

    std::cout << "\n=== Move assignment ===\n";
    UniqueBuffer c(5);
    c = std::move(b);  // old c's buffer freed, b's transferred
    assert(!b.valid());
    assert(c.valid());

    // === COMPILE ERRORS (uncomment to see) ===
    // UniqueBuffer copy = c;                  // ERROR: copy ctor deleted
    // UniqueBuffer copy2(c);                  // ERROR: copy ctor deleted
    // UniqueBuffer x(1); x = c;              // ERROR: copy assign deleted

    std::cout << "\n=== Container usage ===\n";
    std::vector<UniqueBuffer> buffers;
    buffers.push_back(UniqueBuffer(3));    // rvalue — moves in
    buffers.push_back(std::move(c));       // explicit move
    buffers.emplace_back(7);               // construct in-place (best)

    std::cout << "\n=== Lambda capture (C++14 init-capture) ===\n";
    auto buf = UniqueBuffer(4);
    buf[0] = 99;
    auto lambda = [b = std::move(buf)]() {
        std::cout << "  Lambda owns buffer, b[0] = " << b[0] << "\n";
    };
    lambda();
    assert(!buf.valid());  // buf was moved into lambda

    std::cout << "\n=== Sink pattern ===\n";
    consume(UniqueBuffer(2));

    std::cout << "\n=== Cleanup ===\n";
    // Everything destroyed when main exits
    return 0;
}
```

**Key rules for move-only types:**
1. **Delete copy, define move, define destructor** — that's 5 special member functions (rule of five).
2. **Moved-from state must be valid**: destructible and assignable, but not usable for business logic.
3. **Mark move operations `noexcept`**: `std::vector` uses `move_if_noexcept` during reallocation — without `noexcept`, it falls back to copy (which is deleted → compile error).
4. **Use `emplace` or `std::move`** to put move-only types into containers.'''),

    ("cpp_deep/perfect_forwarding_universal_refs", r'''Explain perfect forwarding with universal references in C++. When should I use std::forward vs std::move, and what happens if I get it wrong?''', r'''<think>
Perfect forwarding is about preserving the value category (lvalue vs rvalue) of arguments when passing them through a template function. This is critical for factory functions, wrappers, and emplace-style APIs.

The mechanism:
1. Universal reference (forwarding reference): T&& where T is a deduced template parameter. This is NOT an rvalue reference — it collapses based on what's passed.
2. If an lvalue of type X is passed, T deduces to X&, and T&& becomes X& && → X& (reference collapsing).
3. If an rvalue of type X is passed, T deduces to X, and T&& becomes X&&.
4. std::forward<T>(arg) casts arg back to T&&, which is either X& or X&& — preserving the original value category.

std::forward vs std::move:
- std::move: ALWAYS casts to rvalue. Use when you KNOW you want to move (you're done with the object).
- std::forward: conditionally casts to rvalue ONLY if the original was an rvalue. Use ONLY with forwarding references.

What happens if you get it wrong?
- Using std::move on a forwarding reference: you'd unconditionally move lvalue arguments. The caller's variable gets moved from — silent data loss.
- Using std::forward without a forwarding reference: it "works" but is confusing and may not do what you expect.
- Forwarding the same argument twice: after the first forward, if it was an rvalue, the second forward operates on a moved-from object. Bug!

Let me show a concrete example: a make_unique-style factory function, and contrast correct vs incorrect implementations.

I should also mention auto&& — it's a forwarding reference in a different context (range-for loops, lambdas with auto&&). Same rules apply.
</think>

Here is a comprehensive example demonstrating perfect forwarding, its pitfalls, and when to use each cast:

```cpp
#include <iostream>
#include <string>
#include <utility>
#include <memory>
#include <vector>
#include <type_traits>

struct Widget {
    std::string name;
    int value;

    Widget(const std::string& n, int v) : name(n), value(v) {
        std::cout << "  Widget COPY-constructed: " << name << "\n";
    }
    Widget(std::string&& n, int v) : name(std::move(n)), value(v) {
        std::cout << "  Widget MOVE-constructed: " << name << "\n";
    }
};

// === CORRECT: Perfect forwarding factory ===
template <typename T, typename... Args>
std::unique_ptr<T> make_thing(Args&&... args) {
    // std::forward preserves each argument's original value category
    return std::unique_ptr<T>(new T(std::forward<Args>(args)...));
}

// === WRONG 1: Using std::move instead of std::forward ===
template <typename T, typename... Args>
std::unique_ptr<T> make_thing_WRONG_move(Args&&... args) {
    // BUG: unconditionally moves — steals from caller's lvalues!
    return std::unique_ptr<T>(new T(std::move(args)...));
}

// === WRONG 2: Not forwarding at all ===
template <typename T, typename... Args>
std::unique_ptr<T> make_thing_WRONG_copy(Args&&... args) {
    // BUG: always passes as lvalue — never moves rvalues, wastes performance
    return std::unique_ptr<T>(new T(args...));
}

// === Demonstrating reference collapsing ===
template <typename T>
void show_category(T&& arg) {
    if constexpr (std::is_lvalue_reference_v<T>) {
        std::cout << "  Received LVALUE (T = " << typeid(T).name() << ")\n";
    } else {
        std::cout << "  Received RVALUE (T = " << typeid(T).name() << ")\n";
    }
    // std::forward<T>(arg) would cast to:
    //   T = string&  → forward returns string&  (stays lvalue)
    //   T = string   → forward returns string&& (becomes rvalue)
}

// === Real-world: wrapper that logs and forwards ===
class EventBus {
    std::vector<std::unique_ptr<Widget>> widgets_;
public:
    template <typename... Args>
    Widget& emplace(Args&&... args) {
        widgets_.push_back(
            std::make_unique<Widget>(std::forward<Args>(args)...)
        );
        return *widgets_.back();
    }
};

// === Pitfall: forwarding same argument twice ===
template <typename T>
void double_use_BAD(T&& arg) {
    // If arg is an rvalue, first forward moves it
    // Second forward operates on moved-from string — BUG!
    // auto a = std::forward<T>(arg);  // moves if rvalue
    // auto b = std::forward<T>(arg);  // UB: moved-from!

    // CORRECT: forward only once, copy if you need it twice
    auto copy = arg;  // always copies (arg is lvalue in this scope)
    auto final_val = std::forward<T>(arg);  // forward the original
    std::cout << "  copy: " << copy << ", final: " << final_val << "\n";
}

int main() {
    std::cout << "=== Reference collapsing ===\n";
    std::string name = "Alice";
    show_category(name);              // lvalue → T = string&
    show_category(std::string("Bob")); // rvalue → T = string

    std::cout << "\n=== Correct: perfect forwarding ===\n";
    auto w1 = make_thing<Widget>(name, 1);         // lvalue → copy-constructed
    auto w2 = make_thing<Widget>(std::string("Bob"), 2); // rvalue → move-constructed

    std::cout << "\n=== WRONG: std::move (steals lvalues) ===\n";
    std::string safe_name = "Charlie";
    auto w3 = make_thing_WRONG_move<Widget>(safe_name, 3);
    std::cout << "  safe_name after WRONG call: \"" << safe_name << "\" (STOLEN!)\n";

    std::cout << "\n=== WRONG: no forwarding (wastes moves) ===\n";
    auto w4 = make_thing_WRONG_copy<Widget>(std::string("Dave"), 4);
    // ^ rvalue string gets copy-constructed instead of moved

    std::cout << "\n=== Real-world: EventBus emplace ===\n";
    EventBus bus;
    std::string s = "Sensor";
    bus.emplace(s, 10);                   // lvalue: copies string
    bus.emplace(std::string("Alarm"), 20); // rvalue: moves string

    std::cout << "\n=== Pitfall: double-forward ===\n";
    double_use_BAD(std::string("test"));

    return 0;
}
```

**Cheat sheet:**

| Situation | Use | Why |
|-----------|-----|-----|
| Forwarding reference (`T&&` in template) | `std::forward<T>(arg)` | Preserves value category |
| You own it, done with it | `std::move(arg)` | Unconditional rvalue cast |
| Concrete rvalue ref (`string&&`) | `std::move(arg)` | Named rvalue refs are lvalues |
| `auto&&` in range-for | `std::forward<decltype(x)>(x)` | Same rules as template `T&&` |

**The one rule**: `std::forward` is for forwarding references. `std::move` is for everything else. Never swap them.'''),

    ("cpp_deep/reference_collapsing_rules", r'''What are the reference collapsing rules in C++ and why do they matter? I keep hearing about them in the context of templates.''', r'''<think>
Reference collapsing is what makes forwarding references work. Without it, templates couldn't handle both lvalue and rvalue arguments uniformly.

The rules are simple — there are exactly 4 combinations:
- T& &   → T&
- T& &&  → T&
- T&& &  → T&
- T&& && → T&&

The pattern: if either reference is an lvalue reference (&), the result is lvalue reference. Only && + && gives &&. "Lvalue reference is sticky."

Why this matters: when you write template<typename T> void f(T&& x):
- If called with an lvalue of type int, T deduces to int&. Then T&& = int& && = int& (by collapsing). So x is an lvalue reference. Perfect.
- If called with an rvalue of type int, T deduces to int. Then T&& = int&&. So x is an rvalue reference. Perfect.

This is the ONLY context where T&& is a forwarding reference. If T is not a deduced template parameter, then T&& is just an rvalue reference. So void f(int&& x) is always an rvalue reference, not a forwarding reference.

Where else does collapsing occur?
1. Template instantiation (the main case)
2. typedef / using declarations
3. decltype

I should show a concrete example that makes the collapsing visible, perhaps with static_assert and type_traits to prove what's happening.

Common confusion: people think auto&& is always an rvalue reference. Wrong — auto deduces like a template parameter, so auto&& is a forwarding reference. In range-for (for(auto&& x : container)), x can be lvalue or rvalue reference depending on what the iterator yields.
</think>

Here is a program that demonstrates reference collapsing with compile-time proofs:

```cpp
#include <iostream>
#include <type_traits>
#include <string>

// === The 4 Reference Collapsing Rules ===
// Applied by the compiler during template instantiation:
//
//   T& &    →  T&     (lvalue + lvalue = lvalue)
//   T& &&   →  T&     (lvalue + rvalue = lvalue)  ← THIS IS THE KEY ONE
//   T&& &   →  T&     (rvalue + lvalue = lvalue)
//   T&& &&  →  T&&    (rvalue + rvalue = rvalue)
//
// Summary: & is "sticky". Any & in the chain makes the result &.

// Helper to print type information at compile time
template <typename T>
constexpr const char* type_name() {
    if constexpr (std::is_lvalue_reference_v<T>) {
        if constexpr (std::is_const_v<std::remove_reference_t<T>>)
            return "const T&";
        else
            return "T&";
    } else if constexpr (std::is_rvalue_reference_v<T>) {
        return "T&&";
    } else {
        return "T (value)";
    }
}

// === This is a FORWARDING REFERENCE (T is deduced) ===
template <typename T>
void forwarding_ref(T&& arg) {
    std::cout << "  T deduced as:     " << type_name<T>() << "\n";
    std::cout << "  T&& collapses to: " << type_name<decltype(arg)>() << "\n";

    // Prove it with static_assert
    if constexpr (std::is_lvalue_reference_v<T>) {
        // T = X&, so T&& = X& && = X& (rule 2)
        static_assert(std::is_lvalue_reference_v<decltype(arg)>);
    } else {
        // T = X, so T&& = X&& (no collapsing needed)
        static_assert(std::is_rvalue_reference_v<decltype(arg)>);
    }
}

// === This is NOT a forwarding reference (T is not deduced here) ===
template <typename T>
struct Processor {
    // T is already known when process() is called — no deduction
    void process(T&& arg) {
        std::cout << "  Always rvalue ref: " << type_name<decltype(arg)>() << "\n";
    }
};

// === Collapsing through type aliases ===
template <typename T>
void alias_demo() {
    using Ref = T&;
    using RefRef = Ref&&;  // T& && collapses to T&

    static_assert(std::is_same_v<RefRef, T&>,
                  "T& && must collapse to T&");
    std::cout << "  using Ref = T&; using RefRef = Ref&&; → RefRef is "
              << type_name<RefRef>() << "\n";
}

// === Collapsing through decltype ===
void decltype_demo() {
    int x = 42;

    // decltype(x) = int (named variable, not expression)
    // decltype((x)) = int& (lvalue expression)

    decltype(x)&& a = 42;      // int && = rvalue ref
    decltype((x))&& b = x;     // int& && = int& (collapsed!) = lvalue ref

    static_assert(std::is_rvalue_reference_v<decltype(a)>);
    static_assert(std::is_lvalue_reference_v<decltype(b)>);

    std::cout << "  decltype(x)&&:   " << type_name<decltype(a)>() << " (int&&)\n";
    std::cout << "  decltype((x))&&: " << type_name<decltype(b)>() << " (int& && → int&)\n";
}

// === auto&& is a forwarding reference ===
void auto_ref_demo() {
    std::string s = "hello";

    auto&& r1 = s;               // s is lvalue → auto = string& → string& && → string&
    auto&& r2 = std::move(s);    // rvalue → auto = string → string&&
    auto&& r3 = std::string("temp"); // rvalue → auto = string → string&&

    static_assert(std::is_lvalue_reference_v<decltype(r1)>);
    static_assert(std::is_rvalue_reference_v<decltype(r2)>);
    static_assert(std::is_rvalue_reference_v<decltype(r3)>);

    std::cout << "  auto&& from lvalue:  " << type_name<decltype(r1)>() << "\n";
    std::cout << "  auto&& from xvalue:  " << type_name<decltype(r2)>() << "\n";
    std::cout << "  auto&& from prvalue: " << type_name<decltype(r3)>() << "\n";
}

int main() {
    int x = 42;

    std::cout << "=== Forwarding reference with lvalue ===\n";
    forwarding_ref(x);           // T = int&, T&& = int& && = int&

    std::cout << "\n=== Forwarding reference with rvalue ===\n";
    forwarding_ref(42);          // T = int, T&& = int&&

    std::cout << "\n=== Forwarding reference with const lvalue ===\n";
    const int cx = 99;
    forwarding_ref(cx);          // T = const int&, T&& = const int& && = const int&

    std::cout << "\n=== NOT a forwarding reference ===\n";
    Processor<int> p;
    // p.process(x);  // ERROR: can't bind lvalue to rvalue ref
    p.process(42);    // OK: 42 is rvalue

    std::cout << "\n=== Collapsing through aliases ===\n";
    alias_demo<int>();

    std::cout << "\n=== Collapsing through decltype ===\n";
    decltype_demo();

    std::cout << "\n=== auto&& is a forwarding reference ===\n";
    auto_ref_demo();

    return 0;
}
```

**The rules distilled:**

```
& + &   = &       "lvalue wins"
& + &&  = &       "lvalue wins"
&& + &  = &       "lvalue wins"
&& + && = &&      "only rvalue + rvalue = rvalue"
```

**Why it matters:** reference collapsing is the compiler mechanism that makes `T&&` a forwarding reference. Without it, you could not write a single template that accepts both lvalues and rvalues and preserves their value category through `std::forward`.'''),

    ("cpp_deep/copy_elision_nrvo_rvo", r'''When does copy elision (RVO/NRVO) work in C++ and when does it fail? I want to know when I should add std::move to return statements.''', r'''<think>
Copy elision is when the compiler eliminates copy/move operations by constructing the object directly in the caller's storage. There are two main forms:

1. RVO (Return Value Optimization): returning a prvalue (temporary). Example: return Widget(args). Mandatory in C++17.
2. NRVO (Named Return Value Optimization): returning a named local variable. Example: Widget w; return w. Optional, not mandated by standard, but implemented by all major compilers.

When does NRVO fail?
1. Multiple return paths with different named variables:
   if (cond) return a; else return b;  // compiler can't place both in caller's slot
2. Returning a parameter (it's in the caller's frame, not the function's)
3. Returning a member variable
4. Returning through a reference/pointer parameter
5. The variable's type differs from the return type (even by cv-qualification)
6. The variable is a structured binding or a tuple element

When should you NOT add std::move?
- If NRVO is possible, std::move PREVENTS it! Because std::move changes the expression from a named variable to an xvalue, and the compiler can only do NRVO on a named variable directly.
- BUT: if NRVO is already impossible (multiple return paths, parameter, etc.), std::move helps because it triggers move construction instead of copy.

Wait, actually C++11/14/17 already have implicit move: returning a local variable that's eligible for NRVO but NRVO isn't applied still gets implicit move (the compiler treats it as an rvalue). C++20 further relaxed this to include more cases (returning parameters).

So in C++17+: almost never write std::move on a return statement. The compiler will either do NRVO (best case) or implicit move (second best). Adding std::move only prevents NRVO.

Exception: returning a member variable — std::move is correct because members aren't eligible for implicit move.

Let me build a program that demonstrates each case with output showing whether copy, move, or elision occurred.
</think>

Here is a program that reveals exactly when copy elision happens and when it does not:

```cpp
#include <iostream>
#include <string>

struct Trace {
    std::string label;

    Trace(std::string l) : label(std::move(l)) {
        std::cout << "  [" << label << "] CONSTRUCTED\n";
    }
    ~Trace() {
        std::cout << "  [" << label << "] destroyed\n";
    }
    Trace(const Trace& o) : label(o.label + "-COPY") {
        std::cout << "  [" << label << "] COPY constructed\n";
    }
    Trace(Trace&& o) noexcept : label(std::move(o.label)) {
        label += "-MOVE";
        std::cout << "  [" << label << "] MOVE constructed\n";
    }
};

// === CASE 1: RVO — returning temporary (mandatory C++17) ===
Trace make_rvo() {
    return Trace("rvo");  // Prvalue: MUST be elided in C++17
}

// === CASE 2: NRVO — returning named local (optional, but always done) ===
Trace make_nrvo() {
    Trace t("nrvo");
    t.label += "-modified";
    return t;  // Named return: compiler usually elides
}

// === CASE 3: NRVO FAILS — multiple return paths ===
Trace make_branch(bool flag) {
    Trace a("branch-A");
    Trace b("branch-B");
    if (flag)
        return a;  // Compiler can't place both a AND b in caller's slot
    else
        return b;  // Falls back to implicit move (not copy!)
}

// === CASE 4: DON'T add std::move — it PREVENTS NRVO ===
Trace make_nrvo_with_move() {
    Trace t("nrvo-moved");
    return std::move(t);  // BAD: forces move, prevents elision!
}

// === CASE 5: Returning parameter — no NRVO (parameter in caller's frame) ===
Trace forward_param(Trace t) {
    return t;  // Can't elide (t is a parameter), but implicit move kicks in
}

// === CASE 6: Returning member — std::move IS correct here ===
struct Factory {
    Trace member{"member"};

    Trace extract() && {
        return std::move(member);  // Members don't get implicit move
    }
};

// === CASE 7: Conditional with same variable — NRVO works ===
Trace make_single_path(bool flag) {
    Trace t("single-path");
    if (flag) {
        t.label += "-flagged";
    }
    return t;  // Only one named variable — NRVO applies
}

int main() {
    std::cout << "=== Case 1: RVO (mandatory C++17) ===\n";
    auto r1 = make_rvo();

    std::cout << "\n=== Case 2: NRVO (named, single path) ===\n";
    auto r2 = make_nrvo();

    std::cout << "\n=== Case 3: NRVO fails (multiple named variables) ===\n";
    auto r3 = make_branch(true);

    std::cout << "\n=== Case 4: std::move PREVENTS elision ===\n";
    auto r4 = make_nrvo_with_move();

    std::cout << "\n=== Case 5: Returning parameter (implicit move) ===\n";
    auto r5 = forward_param(Trace("param"));

    std::cout << "\n=== Case 6: Returning member (std::move correct) ===\n";
    {
        Factory f;
        auto r6 = std::move(f).extract();
    }

    std::cout << "\n=== Case 7: Single variable, multiple paths (NRVO works) ===\n";
    auto r7 = make_single_path(true);

    std::cout << "\n=== All going out of scope ===\n";
    return 0;
}
```

**Decision table: should you `std::move` a return value?**

| Scenario | `return x;` | `return std::move(x);` |
|----------|-------------|----------------------|
| Single named local | NRVO (zero cost) | Prevents NRVO — WORSE |
| Multiple named locals | Implicit move | Explicit move (same result) |
| Function parameter | Implicit move (C++20) | Needed in C++17 and earlier |
| Class member | COPIES (no implicit move) | Correct — use std::move |
| Temporary / prvalue | Mandatory RVO | Prevents RVO — WORSE |

**Rule of thumb: never write `std::move` on a `return` unless returning a member or a global.** The compiler handles everything else correctly.'''),

    ("cpp_deep/rule_of_five_resource_class", r'''Show me a correct Rule of Five implementation for a class that owns a dynamically allocated resource. I want to understand all the edge cases.''', r'''<think>
The Rule of Five: if you define any of {destructor, copy ctor, copy assign, move ctor, move assign}, you should define ALL five. This is because defining any one usually means you're managing a resource manually.

Let me implement a dynamically-sized integer array class. Key edge cases to handle:

1. Self-assignment in operator= (both copy and move)
2. Exception safety in copy constructor / copy assignment
3. noexcept on move operations (critical for std::vector)
4. Moved-from state must be valid (destructible, assignable)
5. Copy-and-swap idiom vs direct implementation
6. Strong exception guarantee in copy assignment

For copy assignment, the copy-and-swap idiom gives strong exception guarantee automatically:
- Make a copy (if this throws, *this is untouched)
- Swap with the copy (noexcept)
- Old data destroyed in the copy's destructor

This is simpler and safer than writing manual copy-then-delete logic. But it does force a copy even during move assignment if you use a single unified operator=. So I'll use separate copy and move assignment.

Actually, with the unified approach (taking by value), move assignment becomes: construct temporary via move ctor, then swap. Two operations instead of direct member transfer. Slight overhead. Let me show the separate approach and mention copy-and-swap as alternative.

For move assignment: I need to handle self-move-assignment. The standard says self-move leaves the object in a "valid but unspecified state", but in practice we should handle it gracefully. Simple check: if (this != &other).

Wait, should I use the copy-and-swap for copy assignment and a separate move assignment? That's the cleanest approach. Let me do that.
</think>

Here is a complete Rule of Five implementation with every edge case annotated:

```cpp
#include <iostream>
#include <algorithm>
#include <cstddef>
#include <cassert>
#include <utility>
#include <vector>

class DynArray {
    int* data_;
    std::size_t size_;

    static int alive;  // Leak detector

public:
    // === CONSTRUCTOR ===
    explicit DynArray(std::size_t size = 0)
        : data_(size ? new int[size]{} : nullptr)
        , size_(size)
    {
        ++alive;
        std::cout << "  Ctor: size=" << size_ << " @ " << data_ << "\n";
    }

    // === 1. DESTRUCTOR ===
    ~DynArray() {
        --alive;
        std::cout << "  Dtor: size=" << size_ << " @ " << data_ << "\n";
        delete[] data_;
    }

    // === 2. COPY CONSTRUCTOR ===
    // Strong guarantee: if new[] throws, no resources are leaked
    DynArray(const DynArray& other)
        : data_(other.size_ ? new int[other.size_] : nullptr)
        , size_(other.size_)
    {
        ++alive;
        std::copy(other.data_, other.data_ + size_, data_);
        std::cout << "  CopyCtor: size=" << size_ << "\n";
    }

    // === 3. COPY ASSIGNMENT (copy-and-swap idiom) ===
    // Strong exception guarantee:
    //   - Copy is made first (may throw — *this untouched)
    //   - Swap is noexcept — always succeeds
    //   - Old data destroyed by temp's destructor
    DynArray& operator=(const DynArray& other) {
        std::cout << "  CopyAssign: ";
        if (this == &other) {
            std::cout << "self-assign, skipping\n";
            return *this;
        }
        DynArray temp(other);      // Copy (may throw)
        swap(*this, temp);         // Swap (noexcept)
        std::cout << "done, size=" << size_ << "\n";
        return *this;
        // temp (holding old data) destroyed here
    }

    // === 4. MOVE CONSTRUCTOR ===
    // Must be noexcept! (std::vector relies on this)
    DynArray(DynArray&& other) noexcept
        : data_(other.data_)
        , size_(other.size_)
    {
        ++alive;
        other.data_ = nullptr;    // Leave other in valid empty state
        other.size_ = 0;
        std::cout << "  MoveCtor: size=" << size_ << "\n";
    }

    // === 5. MOVE ASSIGNMENT ===
    // Must be noexcept!
    DynArray& operator=(DynArray&& other) noexcept {
        std::cout << "  MoveAssign: ";
        if (this == &other) {  // Self-move: technically UB in std, but be safe
            std::cout << "self-move, skipping\n";
            return *this;
        }
        delete[] data_;           // Release current resource
        data_ = other.data_;     // Pilfer
        size_ = other.size_;
        other.data_ = nullptr;   // Leave other in valid state
        other.size_ = 0;
        std::cout << "done, size=" << size_ << "\n";
        return *this;
    }

    // === Friend swap (used by copy-and-swap idiom) ===
    friend void swap(DynArray& a, DynArray& b) noexcept {
        using std::swap;
        swap(a.data_, b.data_);
        swap(a.size_, b.size_);
    }

    // === Accessors ===
    int& operator[](std::size_t i) { assert(i < size_); return data_[i]; }
    const int& operator[](std::size_t i) const { assert(i < size_); return data_[i]; }
    std::size_t size() const { return size_; }
    bool empty() const { return size_ == 0; }

    static int alive_count() { return alive; }

    friend std::ostream& operator<<(std::ostream& os, const DynArray& a) {
        os << "[";
        for (std::size_t i = 0; i < a.size_; ++i) {
            if (i) os << ", ";
            os << a.data_[i];
        }
        return os << "]";
    }
};

int DynArray::alive = 0;

int main() {
    std::cout << "=== Construction ===\n";
    DynArray a(5);
    for (std::size_t i = 0; i < a.size(); ++i) a[i] = static_cast<int>(i * 10);
    std::cout << "a = " << a << "\n";

    std::cout << "\n=== Copy construction ===\n";
    DynArray b(a);
    std::cout << "b = " << b << "\n";

    std::cout << "\n=== Copy assignment ===\n";
    DynArray c(3);
    c[0] = 99;
    c = a;  // Old c's data freed, new copy of a's data
    std::cout << "c = " << c << "\n";

    std::cout << "\n=== Self-assignment ===\n";
    c = c;  // Must not crash or corrupt

    std::cout << "\n=== Move construction ===\n";
    DynArray d(std::move(a));
    std::cout << "d = " << d << "\n";
    std::cout << "a (moved-from) = " << a << " empty=" << a.empty() << "\n";

    std::cout << "\n=== Move assignment ===\n";
    DynArray e(2);
    e = std::move(b);
    std::cout << "e = " << e << "\n";
    std::cout << "b (moved-from) = " << b << " empty=" << b.empty() << "\n";

    std::cout << "\n=== Works with std::vector (needs noexcept move) ===\n";
    std::vector<DynArray> vec;
    vec.push_back(DynArray(3));
    vec.push_back(DynArray(4));
    vec.push_back(DynArray(5));  // May trigger reallocation → move

    std::cout << "\n=== Cleanup (alive=" << DynArray::alive_count() << ") ===\n";
    return 0;
}
```

**Critical edge cases handled:**
1. **Self-assignment**: early return prevents double-free.
2. **Exception safety**: copy-and-swap gives strong guarantee — if `new[]` throws during copy, `*this` is unchanged.
3. **`noexcept` move**: without this, `std::vector` reallocation copies instead of moves (or fails to compile for move-only types).
4. **Moved-from state**: `data_ = nullptr, size_ = 0` — destructible, assignable, printable.'''),

    ("cpp_deep/rule_of_zero_composition", r'''Explain the Rule of Zero in C++. When can I avoid writing any special member functions, and how does composing RAII types give me that?''', r'''<think>
The Rule of Zero: if your class doesn't manage resources directly, don't declare any special member functions (destructor, copy/move ctors, copy/move assignment). Let the compiler generate them.

This works because if all your members are RAII types (unique_ptr, shared_ptr, string, vector, etc.), the compiler-generated special member functions do the right thing:
- Destructor: destroys each member (which triggers their destructors → RAII cleanup)
- Copy: copies each member (works for copyable types like string, vector)
- Move: moves each member (works for movable types like unique_ptr)

The key insight: the Rule of Five is for classes that directly manage resources. The Rule of Zero is for classes that COMPOSE such types. In a well-designed codebase, almost all classes should follow the Rule of Zero. Only a handful of low-level resource wrappers need the Rule of Five.

When does Rule of Zero break?
1. You have a non-RAII resource (raw pointer with ownership, C handle, etc.)
2. You need custom behavior (like logging in destructor, deep clone semantics)
3. You have a base class with virtual functions — need virtual destructor (but that triggers the rule of five)

Wait, the virtual destructor case is interesting. If you declare `virtual ~Base() = default;`, the compiler deletes the move operations (declaring a destructor inhibits implicit move generation). So you need to explicitly default them:
    virtual ~Base() = default;
    Base(Base&&) = default;
    Base& operator=(Base&&) = default;
    Base(const Base&) = default;
    Base& operator=(const Base&) = default;

This is sometimes called the "Rule of Five defaults" for polymorphic types.

Let me show concrete examples: a class that follows Rule of Zero vs one that incorrectly tries to manage resources manually.
</think>

Here is a complete demonstration of the Rule of Zero and when it applies:

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <fstream>

// === LOW-LEVEL: Rule of Five (manages resource directly) ===
// This class exists so that EVERYONE ELSE can follow Rule of Zero.
class MappedBuffer {
    void* data_;
    std::size_t size_;
public:
    explicit MappedBuffer(std::size_t sz)
        : data_(std::malloc(sz)), size_(sz) {
        if (!data_) throw std::bad_alloc();
    }
    ~MappedBuffer() { std::free(data_); }
    MappedBuffer(const MappedBuffer& o)
        : data_(std::malloc(o.size_)), size_(o.size_) {
        if (!data_) throw std::bad_alloc();
        std::memcpy(data_, o.data_, size_);
    }
    MappedBuffer& operator=(const MappedBuffer& o) {
        if (this != &o) { MappedBuffer tmp(o); swap(*this, tmp); }
        return *this;
    }
    MappedBuffer(MappedBuffer&& o) noexcept : data_(o.data_), size_(o.size_) {
        o.data_ = nullptr; o.size_ = 0;
    }
    MappedBuffer& operator=(MappedBuffer&& o) noexcept {
        if (this != &o) { std::free(data_); data_ = o.data_; size_ = o.size_;
            o.data_ = nullptr; o.size_ = 0; }
        return *this;
    }
    friend void swap(MappedBuffer& a, MappedBuffer& b) noexcept {
        std::swap(a.data_, b.data_); std::swap(a.size_, b.size_);
    }
    void* data() { return data_; }
    std::size_t size() const { return size_; }
};

// === HIGH-LEVEL: Rule of Zero (composes RAII types) ===
// NO destructor, NO copy/move operations — compiler generates them all correctly.
struct UserProfile {
    std::string name;                          // copyable, movable
    std::string email;                         // copyable, movable
    std::vector<std::string> tags;             // copyable, movable
    std::shared_ptr<MappedBuffer> avatar;      // copyable (shared), movable

    // That's it. No special member functions. Everything just works.
};

// === Rule of Zero with move-only semantics (via composition) ===
struct Connection {
    std::string host;
    std::unique_ptr<MappedBuffer> recv_buffer;   // move-only → Connection is move-only

    // No special member functions declared.
    // Compiler generates:
    //   - Move ctor: moves string + moves unique_ptr ✓
    //   - Move assign: same ✓
    //   - Destructor: destroys string + destroys unique_ptr (frees buffer) ✓
    //   - Copy ctor: DELETED (because unique_ptr is not copyable) ✓
    //   - Copy assign: DELETED ✓
    // This is EXACTLY the semantics we want for an exclusive connection!
};

// === Polymorphic base: "Rule of Five Defaults" ===
struct Shape {
    virtual ~Shape() = default;                    // Need virtual dtor
    Shape() = default;
    Shape(const Shape&) = default;                 // Must re-declare: dtor
    Shape& operator=(const Shape&) = default;      // inhibits implicit
    Shape(Shape&&) = default;                      // move generation
    Shape& operator=(Shape&&) = default;

    virtual double area() const = 0;
};

struct Circle : Shape {
    double radius;
    Circle(double r) : radius(r) {}
    double area() const override { return 3.14159265 * radius * radius; }
    // Rule of Zero: no special member functions needed in derived class
};

// === ANTI-PATTERN: unnecessarily breaking Rule of Zero ===
struct BadProfile {
    char* name;  // Raw owning pointer — now you NEED Rule of Five
    // Forgetting any of the 5 → bugs. Don't do this.

    BadProfile(const char* n) {
        name = new char[std::strlen(n) + 1];
        std::strcpy(name, n);
    }
    ~BadProfile() { delete[] name; }
    // MISSING: copy ctor, copy assign, move ctor, move assign
    // = double-free on copy, leak on assign
};

int main() {
    std::cout << "=== Rule of Zero: UserProfile ===\n";
    UserProfile alice{"Alice", "alice@example.com", {"admin", "dev"},
                      std::make_shared<MappedBuffer>(1024)};

    // Compiler-generated copy — deep copies strings/vector, shares avatar
    UserProfile alice_copy = alice;
    std::cout << "Copied. Same avatar? "
              << (alice.avatar == alice_copy.avatar ? "yes (shared)" : "no") << "\n";

    // Compiler-generated move — zero-cost transfer
    UserProfile moved = std::move(alice);
    std::cout << "Moved. alice.name is now: \"" << alice.name << "\" (empty)\n";

    std::cout << "\n=== Rule of Zero: move-only Connection ===\n";
    Connection conn{"localhost", std::make_unique<MappedBuffer>(4096)};
    // Connection conn2 = conn;  // COMPILE ERROR: unique_ptr not copyable
    Connection conn2 = std::move(conn);  // OK: moves ownership
    std::cout << "conn2.host = " << conn2.host << "\n";
    std::cout << "conn.host = \"" << conn.host << "\" (moved-from)\n";

    std::cout << "\n=== Polymorphic: Rule of Five Defaults ===\n";
    std::vector<std::unique_ptr<Shape>> shapes;
    shapes.push_back(std::make_unique<Circle>(5.0));
    std::cout << "Circle area: " << shapes[0]->area() << "\n";

    std::cout << "\n=== Works in containers ===\n";
    std::vector<UserProfile> profiles;
    profiles.emplace_back(UserProfile{"Bob", "bob@x.com", {"user"}, nullptr});
    profiles.push_back(alice_copy);  // Copies
    std::cout << "Profiles: " << profiles.size() << "\n";

    return 0;
}
```

**The hierarchy of rules:**

| Rule | When | You write |
|------|------|-----------|
| Rule of Zero | Class composes RAII members | Nothing (let compiler generate all) |
| Rule of Five | Class directly owns a resource | All 5 special member functions |
| Rule of Five Defaults | Polymorphic base class | `= default` for all 5 |

**Guideline**: in a well-designed codebase, ~95% of classes follow Rule of Zero. Only a small number of resource-wrapper classes at the bottom of the abstraction stack need Rule of Five.'''),

    ("cpp_deep/placement_new_manual_lifetime", r'''How does placement new work in C++? When would I need manual lifetime management, and what are the pitfalls?''', r'''<think>
Placement new constructs an object at a specific memory address without allocating memory. You provide the address, the compiler just calls the constructor at that location.

Syntax: new (address) Type(args...);

Why use it?
1. Custom allocators (arena, pool, slab)
2. Implementing std::optional, std::variant, std::vector internals
3. Memory-mapped I/O where you need an object at a specific address
4. Avoiding default construction in array-like containers (construct on demand)

Key pitfalls:
1. Alignment: the memory must be properly aligned for the type. alignas or std::aligned_storage (deprecated in C++23 — use alignas + char array instead).
2. You MUST explicitly call the destructor before reusing the memory or freeing it. delete does NOT work on placement-new'd objects.
3. After calling the destructor, the memory is NOT freed — you manage that separately.
4. std::launder may be needed if you construct a new object of a different type at the same address (strict aliasing, const members, reference members).
5. Exception safety: if the constructor throws during placement new, the memory is NOT freed (but the object wasn't constructed, so no destructor needed).

C++17 introduced std::destroy_at, std::construct_at (C++20) as safer alternatives to explicit destructor calls and placement new.

Let me build a small manual optional<T> to demonstrate all these concepts concretely.

I should also show the aligned_storage situation. std::aligned_storage is deprecated in C++23. The modern way is:
    alignas(T) std::byte storage[sizeof(T)];
or:
    alignas(T) unsigned char storage[sizeof(T)];
</think>

Here is a complete example showing placement new, manual lifetime management, and a real use case:

```cpp
#include <iostream>
#include <new>       // placement new
#include <memory>    // construct_at, destroy_at (C++20)
#include <cstddef>
#include <string>
#include <cassert>
#include <cstring>

// === Manual Optional<T> using placement new ===
template <typename T>
class ManualOptional {
    // Modern aligned storage (std::aligned_storage deprecated in C++23)
    alignas(T) unsigned char storage_[sizeof(T)];
    bool has_value_ = false;

    T* ptr() { return reinterpret_cast<T*>(storage_); }
    const T* ptr() const { return reinterpret_cast<const T*>(storage_); }

public:
    ManualOptional() = default;

    // Construct in-place
    template <typename... Args>
    explicit ManualOptional(std::in_place_t, Args&&... args) {
        // Placement new: constructs T at &storage_[0]
        ::new (storage_) T(std::forward<Args>(args)...);
        has_value_ = true;
    }

    // Must destroy manually — delete[] storage_ would be WRONG
    ~ManualOptional() {
        reset();
    }

    // Copy
    ManualOptional(const ManualOptional& other) {
        if (other.has_value_) {
            ::new (storage_) T(*other.ptr());
            has_value_ = true;
        }
    }

    ManualOptional& operator=(const ManualOptional& other) {
        if (this == &other) return *this;
        reset();
        if (other.has_value_) {
            ::new (storage_) T(*other.ptr());
            has_value_ = true;
        }
        return *this;
    }

    // Move
    ManualOptional(ManualOptional&& other) noexcept {
        if (other.has_value_) {
            ::new (storage_) T(std::move(*other.ptr()));
            has_value_ = true;
            other.reset();
        }
    }

    ManualOptional& operator=(ManualOptional&& other) noexcept {
        if (this == &other) return *this;
        reset();
        if (other.has_value_) {
            ::new (storage_) T(std::move(*other.ptr()));
            has_value_ = true;
            other.reset();
        }
        return *this;
    }

    // Emplace: destroy existing, construct new
    template <typename... Args>
    T& emplace(Args&&... args) {
        reset();
        ::new (storage_) T(std::forward<Args>(args)...);
        has_value_ = true;
        return *ptr();
    }

    void reset() {
        if (has_value_) {
            ptr()->~T();  // EXPLICIT destructor call — critical!
            has_value_ = false;
        }
        // storage_ memory is NOT freed — it's on the stack
    }

    bool has_value() const { return has_value_; }
    T& value() { assert(has_value_); return *ptr(); }
    const T& value() const { assert(has_value_); return *ptr(); }
    T& operator*() { return value(); }
};

// === Demonstrating alignment requirements ===
struct Aligned32 {
    alignas(32) double data[4];  // Requires 32-byte alignment
};

void alignment_demo() {
    // WRONG: char buffer has alignment 1
    // char bad_buf[sizeof(Aligned32)];
    // new (bad_buf) Aligned32{};  // Potential UB: misaligned!

    // CORRECT: specify alignment
    alignas(Aligned32) unsigned char good_buf[sizeof(Aligned32)];
    auto* obj = new (good_buf) Aligned32{};
    std::cout << "  Aligned32 requires: " << alignof(Aligned32) << "\n";
    std::cout << "  Buffer alignment:   " << alignof(decltype(good_buf)) << "\n";
    std::cout << "  Object address:     " << obj << "\n";
    std::cout << "  Address % 32 == "
              << (reinterpret_cast<std::uintptr_t>(obj) % 32) << "\n";
    obj->~Aligned32();
}

// === Object pool using placement new ===
template <typename T, std::size_t N>
class FixedPool {
    alignas(T) unsigned char storage_[N * sizeof(T)];
    bool occupied_[N] = {};

public:
    template <typename... Args>
    T* construct(Args&&... args) {
        for (std::size_t i = 0; i < N; ++i) {
            if (!occupied_[i]) {
                T* p = new (storage_ + i * sizeof(T)) T(std::forward<Args>(args)...);
                occupied_[i] = true;
                return p;
            }
        }
        return nullptr;  // Pool exhausted
    }

    void destroy(T* p) {
        auto offset = reinterpret_cast<unsigned char*>(p) - storage_;
        std::size_t idx = offset / sizeof(T);
        assert(idx < N && occupied_[idx]);
        p->~T();
        occupied_[idx] = false;
    }

    ~FixedPool() {
        for (std::size_t i = 0; i < N; ++i) {
            if (occupied_[i]) {
                reinterpret_cast<T*>(storage_ + i * sizeof(T))->~T();
            }
        }
    }
};

int main() {
    std::cout << "=== ManualOptional ===\n";
    {
        ManualOptional<std::string> opt;
        std::cout << "Empty: has_value=" << opt.has_value() << "\n";

        opt.emplace("Hello, placement new!");
        std::cout << "After emplace: \"" << *opt << "\"\n";

        opt.emplace("Replaced!");  // Destroys old string, constructs new
        std::cout << "After re-emplace: \"" << *opt << "\"\n";

        auto opt2 = std::move(opt);
        std::cout << "After move: opt2=\"" << *opt2 << "\"\n";
        std::cout << "opt has_value=" << opt.has_value() << "\n";
    }

    std::cout << "\n=== Alignment ===\n";
    alignment_demo();

    std::cout << "\n=== Fixed Pool ===\n";
    {
        FixedPool<std::string, 4> pool;
        auto* s1 = pool.construct("first");
        auto* s2 = pool.construct("second");
        auto* s3 = pool.construct("third");
        std::cout << "Pool: " << *s1 << ", " << *s2 << ", " << *s3 << "\n";

        pool.destroy(s2);  // Explicit destroy, slot reusable
        auto* s4 = pool.construct("recycled");
        std::cout << "After recycle: " << *s4 << "\n";
    }

    return 0;
}
```

**Critical rules for placement new:**

| Rule | Violation consequence |
|------|----------------------|
| Memory must be aligned for `T` | Undefined behavior (crash on some platforms) |
| Must call destructor explicitly | Resource leak (strings, file handles, etc.) |
| Never call `delete` on placement-new'd object | Double-free / heap corruption |
| Use `std::launder` after reusing memory for different type | Strict aliasing violation (C++17) |
| Handle constructor exceptions | Object not constructed, no destructor needed, but memory still valid |'''),

    ("cpp_deep/custom_arena_allocator", r'''How do I implement a custom arena allocator in modern C++? I want to use it with STL containers.''', r'''<think>
An arena allocator (also called bump allocator or linear allocator) allocates from a pre-allocated block by bumping a pointer. Deallocation is a no-op — the entire arena is freed at once. This is great for:
- Parsing (allocate many small nodes, free all at end)
- Per-frame game allocations
- Compiler/interpreter data structures

For STL compatibility, we need to implement the Allocator concept. In C++17, the minimum requirements are:
- value_type typedef
- allocate(n) → pointer
- deallocate(p, n) (can be no-op for arena)
- operator== and operator!= (for container compatibility)
- Rebinding: the allocator must be rebindable to different types (e.g., std::list<int> internally needs allocator for list_node<int>, not int)

Important: STL allocators must be copyable, and copies must be "interchangeable" (can deallocate memory allocated by the other). For arena allocators, this means all copies share the same arena (via pointer or reference).

Alignment is critical: each allocation must return memory aligned for the requested type. The arena bump must account for alignment padding.

One subtlety: std::vector needs contiguous memory that can grow. An arena allocator that can't grow individual allocations won't work well with vector's reallocation strategy. It works, but wastes memory as vector reallocates. It's better suited for std::list, std::map, or containers where you know the final size upfront (reserve + push_back).

Let me implement a simple arena and the allocator adapter. I'll use C++17 features.

Actually, I should also mention PMR (Polymorphic Memory Resources) as the modern alternative — but the user asked for a custom allocator, so I'll do that and mention PMR briefly.
</think>

Here is a complete arena allocator that works with STL containers:

```cpp
#include <iostream>
#include <cstddef>
#include <cstdint>
#include <cassert>
#include <vector>
#include <list>
#include <string>
#include <memory>
#include <algorithm>

// === The Arena: owns a block of memory, bump-allocates from it ===
class Arena {
    unsigned char* base_;
    std::size_t capacity_;
    std::size_t offset_ = 0;
    std::size_t alloc_count_ = 0;
    std::size_t wasted_ = 0;

public:
    explicit Arena(std::size_t capacity)
        : base_(static_cast<unsigned char*>(std::malloc(capacity)))
        , capacity_(capacity)
    {
        if (!base_) throw std::bad_alloc();
        std::cout << "Arena: " << capacity << " bytes allocated\n";
    }

    ~Arena() {
        std::cout << "Arena: freed (" << alloc_count_ << " allocations, "
                  << offset_ << "/" << capacity_ << " bytes used, "
                  << wasted_ << " bytes alignment padding)\n";
        std::free(base_);
    }

    // Non-copyable, non-movable (allocator copies reference it)
    Arena(const Arena&) = delete;
    Arena& operator=(const Arena&) = delete;

    void* allocate(std::size_t bytes, std::size_t alignment) {
        // Align the current offset
        std::size_t aligned_offset = (offset_ + alignment - 1) & ~(alignment - 1);
        std::size_t padding = aligned_offset - offset_;
        wasted_ += padding;

        if (aligned_offset + bytes > capacity_) {
            throw std::bad_alloc();  // Arena exhausted
        }

        void* ptr = base_ + aligned_offset;
        offset_ = aligned_offset + bytes;
        ++alloc_count_;
        return ptr;
    }

    // Deallocate is intentionally a no-op — arena frees everything at once
    void deallocate(void* /*ptr*/, std::size_t /*bytes*/) noexcept {
        // No-op! This is the whole point of arena allocation.
    }

    void reset() noexcept {
        offset_ = 0;
        alloc_count_ = 0;
        wasted_ = 0;
    }

    std::size_t used() const { return offset_; }
    std::size_t remaining() const { return capacity_ - offset_; }
};

// === STL-compatible Allocator adapter ===
template <typename T>
class ArenaAllocator {
    Arena* arena_;

    template <typename U>
    friend class ArenaAllocator;  // For rebinding

public:
    using value_type = T;

    // Propagation traits — tell containers that copies share the arena
    using propagate_on_container_copy_assignment = std::true_type;
    using propagate_on_container_move_assignment = std::true_type;
    using propagate_on_container_swap = std::true_type;

    explicit ArenaAllocator(Arena& arena) noexcept : arena_(&arena) {}

    // Rebinding constructor: ArenaAllocator<U> → ArenaAllocator<T>
    template <typename U>
    ArenaAllocator(const ArenaAllocator<U>& other) noexcept
        : arena_(other.arena_) {}

    T* allocate(std::size_t n) {
        return static_cast<T*>(arena_->allocate(n * sizeof(T), alignof(T)));
    }

    void deallocate(T* ptr, std::size_t n) noexcept {
        arena_->deallocate(ptr, n * sizeof(T));
    }

    // Two allocators are equal if they share the same arena
    template <typename U>
    bool operator==(const ArenaAllocator<U>& other) const noexcept {
        return arena_ == other.arena_;
    }

    template <typename U>
    bool operator!=(const ArenaAllocator<U>& other) const noexcept {
        return arena_ != other.arena_;
    }
};

int main() {
    std::cout << "=== Arena with std::vector ===\n";
    {
        Arena arena(4096);
        ArenaAllocator<int> alloc(arena);

        // IMPORTANT: reserve upfront! vector reallocation wastes arena space
        // because deallocate is a no-op.
        std::vector<int, ArenaAllocator<int>> vec(alloc);
        vec.reserve(100);
        for (int i = 0; i < 100; ++i) {
            vec.push_back(i);
        }
        std::cout << "Vector size: " << vec.size()
                  << ", arena used: " << arena.used() << " bytes\n";

        // Sum to prove data integrity
        int sum = 0;
        for (int x : vec) sum += x;
        std::cout << "Sum 0..99 = " << sum << " (expected 4950)\n";
    }

    std::cout << "\n=== Arena with std::list (ideal use case) ===\n";
    {
        Arena arena(8192);
        ArenaAllocator<int> alloc(arena);

        // list is ideal: each node is a separate allocation, no reallocation waste
        std::list<int, ArenaAllocator<int>> lst(alloc);
        for (int i = 0; i < 50; ++i) {
            lst.push_back(i * 10);
        }
        lst.sort();
        std::cout << "List size: " << lst.size()
                  << ", arena used: " << arena.used() << " bytes\n";
    }

    std::cout << "\n=== Arena reuse (reset and reuse) ===\n";
    {
        Arena arena(2048);

        for (int round = 0; round < 3; ++round) {
            ArenaAllocator<double> alloc(arena);
            std::vector<double, ArenaAllocator<double>> v(alloc);
            v.reserve(50);
            for (int i = 0; i < 50; ++i) v.push_back(i * 1.5);
            std::cout << "Round " << round << ": used " << arena.used()
                      << " bytes, remaining " << arena.remaining() << "\n";
            // Vector destructor runs here (calls deallocate = no-op)
            arena.reset();  // Reclaim all memory for next round
        }
    }

    return 0;
}
```

**Performance characteristics:**

| Operation | Arena | malloc/new |
|-----------|-------|-----------|
| Allocate | O(1) bump pointer | O(n) free-list search |
| Deallocate | O(1) no-op | O(1) amortized |
| Reset all | O(1) | Not possible |
| Fragmentation | Zero | Can be severe |
| Thread safety | Needs external sync | Built-in (with overhead) |

**When to use**: parsers, per-frame game logic, short-lived batch processing, compilers — anywhere you can "allocate a lot, free everything at once."'''),

    ("cpp_deep/pmr_pool_allocation", r'''How do Polymorphic Memory Resources (PMR) work in C++17? Show me pool allocation with std::pmr containers.''', r'''<think>
PMR (Polymorphic Memory Resources) is the modern C++ approach to custom allocation. Unlike the classic Allocator template parameter that bakes the allocator into the type, PMR uses runtime polymorphism via std::pmr::memory_resource.

Key components:
1. std::pmr::memory_resource — abstract base class with do_allocate, do_deallocate, do_is_equal
2. std::pmr::polymorphic_allocator<T> — wraps a memory_resource*, satisfies Allocator concept
3. std::pmr::vector, std::pmr::string, etc. — typedefs for containers using polymorphic_allocator
4. Built-in resources: new_delete_resource(), null_memory_resource()
5. Pool resources: monotonic_buffer_resource, unsynchronized_pool_resource, synchronized_pool_resource

The big win: std::pmr::vector<int> and std::pmr::vector<int> from different memory resources are THE SAME TYPE. With classic allocators, vector<int, ArenaAlloc> and vector<int, PoolAlloc> are different types.

monotonic_buffer_resource: like our arena — fast bump allocation, no individual deallocation, frees everything in destructor. Can optionally use a stack buffer as initial backing.

unsynchronized_pool_resource: maintains pools of different block sizes. Good for varied allocation patterns. Not thread-safe.

synchronized_pool_resource: thread-safe version. Uses per-thread pools to minimize contention.

Let me show practical usage with stack-backed monotonic, pool, and custom memory_resource implementations.
</think>

Here is a complete PMR example showing pool allocation, monotonic buffers, and custom resources:

```cpp
#include <iostream>
#include <memory_resource>
#include <vector>
#include <list>
#include <map>
#include <string>
#include <array>
#include <chrono>
#include <cstddef>

// === Custom memory resource: tracks allocations for debugging ===
class TracingResource : public std::pmr::memory_resource {
    std::pmr::memory_resource* upstream_;
    std::size_t total_allocated_ = 0;
    std::size_t total_deallocated_ = 0;
    int alloc_count_ = 0;
    std::string name_;

protected:
    void* do_allocate(std::size_t bytes, std::size_t alignment) override {
        void* p = upstream_->allocate(bytes, alignment);
        total_allocated_ += bytes;
        ++alloc_count_;
        std::cout << "  [" << name_ << "] allocate(" << bytes
                  << ", align=" << alignment << ") → " << p << "\n";
        return p;
    }

    void do_deallocate(void* p, std::size_t bytes, std::size_t alignment) override {
        std::cout << "  [" << name_ << "] deallocate(" << bytes << ") @ " << p << "\n";
        total_deallocated_ += bytes;
        upstream_->deallocate(p, bytes, alignment);
    }

    bool do_is_equal(const memory_resource& other) const noexcept override {
        return this == &other;
    }

public:
    TracingResource(std::string name,
                    std::pmr::memory_resource* upstream = std::pmr::get_default_resource())
        : upstream_(upstream), name_(std::move(name)) {}

    ~TracingResource() {
        std::cout << "  [" << name_ << "] TOTAL: " << alloc_count_ << " allocs, "
                  << total_allocated_ << " bytes allocated, "
                  << total_deallocated_ << " bytes freed\n";
    }
};

// === Monotonic buffer with stack-backed initial buffer ===
void demo_monotonic() {
    std::cout << "=== Monotonic Buffer Resource ===\n";

    // Stack buffer — avoids heap for small allocations
    std::array<std::byte, 1024> stack_buf;

    // Monotonic: bump-allocates from stack_buf first,
    // overflows to upstream (new_delete) if needed
    std::pmr::monotonic_buffer_resource mbr(
        stack_buf.data(), stack_buf.size(),
        std::pmr::new_delete_resource()
    );

    TracingResource tracer("mono", &mbr);

    // All these containers share the same memory resource and same TYPE
    std::pmr::vector<int> nums(&tracer);
    nums.reserve(50);
    for (int i = 0; i < 50; ++i) nums.push_back(i);

    std::cout << "  Vector of " << nums.size() << " ints created\n";
    // No individual deallocation — everything freed when mbr dies
}

// === Pool resource for varied allocation patterns ===
void demo_pool() {
    std::cout << "\n=== Pool Resource (unsynchronized) ===\n";

    std::pmr::pool_options opts;
    opts.max_blocks_per_chunk = 16;
    opts.largest_required_pool_block = 256;

    std::pmr::unsynchronized_pool_resource pool(
        opts, std::pmr::new_delete_resource()
    );

    TracingResource tracer("pool", &pool);

    // std::pmr::list — ideal for pool allocation (fixed-size nodes)
    std::pmr::list<int> lst(&tracer);
    for (int i = 0; i < 20; ++i) lst.push_back(i);
    std::cout << "  List of " << lst.size() << " nodes\n";

    // std::pmr::map — internal nodes benefit from pooling
    std::pmr::map<int, std::pmr::string> registry(&tracer);
    registry[1] = "alpha";
    registry[2] = "beta";
    registry[3] = "gamma";
    std::cout << "  Map with " << registry.size() << " entries\n";
}

// === Key advantage: same type regardless of allocator ===
void demo_type_erasure() {
    std::cout << "\n=== Type Erasure Advantage ===\n";

    std::array<std::byte, 2048> buf;
    std::pmr::monotonic_buffer_resource mbr(buf.data(), buf.size());

    // These are ALL the same type: std::pmr::vector<int>
    std::pmr::vector<int> heap_vec(std::pmr::get_default_resource());
    std::pmr::vector<int> stack_vec(&mbr);

    heap_vec = {1, 2, 3};
    stack_vec = {4, 5, 6};

    // Can pass to same function, store in same container, etc.
    auto print = [](const std::pmr::vector<int>& v, const char* label) {
        std::cout << "  " << label << ": ";
        for (int x : v) std::cout << x << " ";
        std::cout << "\n";
    };

    print(heap_vec, "heap");
    print(stack_vec, "stack");
}

// === Nested containers: pmr propagation ===
void demo_nested() {
    std::cout << "\n=== Nested Container Propagation ===\n";

    std::array<std::byte, 4096> buf;
    std::pmr::monotonic_buffer_resource mbr(buf.data(), buf.size());
    TracingResource tracer("nested", &mbr);

    // Vector of vectors — inner vectors inherit the outer's allocator
    using InnerVec = std::pmr::vector<int>;
    std::pmr::vector<InnerVec> matrix(&tracer);

    for (int i = 0; i < 3; ++i) {
        // Inner vector automatically uses parent's memory resource
        auto& row = matrix.emplace_back(&tracer);
        for (int j = 0; j < 4; ++j) {
            row.push_back(i * 4 + j);
        }
    }

    std::cout << "  Matrix:\n";
    for (const auto& row : matrix) {
        std::cout << "    ";
        for (int x : row) std::cout << x << " ";
        std::cout << "\n";
    }
}

int main() {
    demo_monotonic();
    demo_pool();
    demo_type_erasure();
    demo_nested();
    return 0;
}
```

**PMR resource comparison:**

| Resource | Allocate | Deallocate | Thread-safe | Best for |
|----------|----------|------------|-------------|----------|
| `new_delete_resource` | `::operator new` | `::operator delete` | Yes | Default fallback |
| `monotonic_buffer_resource` | O(1) bump | No-op | No | Parse trees, temp data |
| `unsynchronized_pool_resource` | O(1) from pool | Returns to pool | No | Node-based containers |
| `synchronized_pool_resource` | O(1) per-thread | Returns to pool | Yes | Multi-threaded apps |

**Why PMR over classic allocators:** containers with different allocators are the **same type** (`std::pmr::vector<int>`), so they can be stored together, passed to the same functions, and swapped freely.'''),

    ("cpp_deep/small_buffer_optimization", r'''How is Small Buffer Optimization (SBO) implemented? Show me a working SBO string or variant type.''', r'''<think>
SBO (Small Buffer Optimization, also called SSO for Small String Optimization): store small objects inline within the class instead of heap-allocating. If the data fits in a pre-allocated internal buffer, avoid the heap entirely. If it doesn't fit, fall back to heap allocation.

std::string uses this — most implementations store strings up to 15 or 22 bytes inline. std::function also uses SBO for small callables.

Key implementation challenges:
1. Union of inline buffer and heap pointer — they share the same memory
2. Need a flag to know which is active (inline vs heap). Often encode this in the size/capacity fields cleverly
3. Alignment of the inline buffer must match the stored type
4. Move semantics: if inline, must actually copy/move the data (can't just transfer a pointer). If heap, can transfer the pointer.
5. Destruction: must call the right path

Let me implement a SBO string class. For simplicity:
- 24 bytes total object size (3 pointers on 64-bit)
- If string <= 22 chars (23 bytes including null), store inline
- If longer, heap allocate
- Use the last byte of the inline buffer to store both the inline length AND the inline/heap flag

Actually, let me implement something slightly different — a SmallFunction (like std::function with SBO). That shows the pattern more broadly.

Hmm, a SBO string is more approachable. Let me do that. I'll use a simple flag rather than the clever encoding that libc++ uses.

Design:
- Total size: 32 bytes
- Inline buffer: 24 bytes (23 chars + null)
- Size: 4 bytes
- is_heap flag: 1 byte (could be packed, but keeping simple)
- When heap: buffer stores {char* ptr, size_t capacity} reinterpreted

Wait, the standard trick: use a union of the inline buffer and the heap struct. That way they share the same space.

Let me keep it straightforward for educational purposes.
</think>

Here is a working Small Buffer Optimization string implementation:

```cpp
#include <iostream>
#include <cstring>
#include <algorithm>
#include <cassert>
#include <utility>
#include <cstddef>

class SboString {
    // Layout: 32 bytes total on 64-bit
    // Inline mode: 31 chars + null terminator stored directly
    // Heap mode: pointer + size + capacity stored in same space
    static constexpr std::size_t BUF_SIZE = 32;
    static constexpr std::size_t INLINE_CAP = BUF_SIZE - 1; // 31 chars + flag byte

    union {
        char inline_buf_[BUF_SIZE]; // Small strings live here
        struct {
            char* ptr_;
            std::size_t size_;
            std::size_t capacity_;
            // Remaining bytes unused in heap mode, except last byte = flag
        } heap_;
    };

    // Last byte doubles as inline/heap flag
    // If inline: last byte = remaining capacity (0..31), always >= 0
    // If heap: last byte = 0xFF (sentinel, > INLINE_CAP)
    static constexpr char HEAP_FLAG = static_cast<char>(0xFF);

    bool is_heap() const {
        return inline_buf_[BUF_SIZE - 1] == HEAP_FLAG;
    }

    void set_inline_size(std::size_t n) {
        // Store "remaining" in last byte — if we use n chars, remaining = INLINE_CAP - n
        inline_buf_[BUF_SIZE - 1] = static_cast<char>(INLINE_CAP - n);
    }

    std::size_t inline_size() const {
        return INLINE_CAP - static_cast<unsigned char>(inline_buf_[BUF_SIZE - 1]);
    }

public:
    SboString() {
        inline_buf_[0] = '\0';
        set_inline_size(0);
    }

    SboString(const char* s) : SboString(s, std::strlen(s)) {}

    SboString(const char* s, std::size_t len) {
        if (len <= INLINE_CAP) {
            // Fits inline — no heap allocation
            std::memcpy(inline_buf_, s, len);
            inline_buf_[len] = '\0';
            set_inline_size(len);
        } else {
            // Heap allocate
            heap_.capacity_ = len + 1;
            heap_.ptr_ = new char[heap_.capacity_];
            heap_.size_ = len;
            std::memcpy(heap_.ptr_, s, len);
            heap_.ptr_[len] = '\0';
            inline_buf_[BUF_SIZE - 1] = HEAP_FLAG;
        }
    }

    ~SboString() {
        if (is_heap()) {
            delete[] heap_.ptr_;
        }
    }

    // Copy constructor
    SboString(const SboString& other) {
        if (other.is_heap()) {
            heap_.capacity_ = other.heap_.capacity_;
            heap_.ptr_ = new char[heap_.capacity_];
            heap_.size_ = other.heap_.size_;
            std::memcpy(heap_.ptr_, other.heap_.ptr_, heap_.size_ + 1);
            inline_buf_[BUF_SIZE - 1] = HEAP_FLAG;
        } else {
            std::memcpy(inline_buf_, other.inline_buf_, BUF_SIZE);
        }
    }

    // Move constructor
    SboString(SboString&& other) noexcept {
        if (other.is_heap()) {
            // Steal heap pointer — O(1)
            heap_.ptr_ = other.heap_.ptr_;
            heap_.size_ = other.heap_.size_;
            heap_.capacity_ = other.heap_.capacity_;
            inline_buf_[BUF_SIZE - 1] = HEAP_FLAG;
            // Leave other in valid inline state
            other.inline_buf_[0] = '\0';
            other.set_inline_size(0);
        } else {
            // Inline: must copy the buffer — can't steal, no pointer to transfer
            std::memcpy(inline_buf_, other.inline_buf_, BUF_SIZE);
            other.inline_buf_[0] = '\0';
            other.set_inline_size(0);
        }
    }

    // Copy assignment
    SboString& operator=(const SboString& other) {
        if (this != &other) {
            SboString tmp(other);
            swap(*this, tmp);
        }
        return *this;
    }

    // Move assignment
    SboString& operator=(SboString&& other) noexcept {
        if (this != &other) {
            if (is_heap()) delete[] heap_.ptr_;
            new (this) SboString(std::move(other)); // Move-construct in place
        }
        return *this;
    }

    friend void swap(SboString& a, SboString& b) noexcept {
        // Both might be inline — just swap the raw bytes
        char tmp[BUF_SIZE];
        std::memcpy(tmp, a.inline_buf_, BUF_SIZE);
        std::memcpy(a.inline_buf_, b.inline_buf_, BUF_SIZE);
        std::memcpy(b.inline_buf_, tmp, BUF_SIZE);
    }

    const char* c_str() const {
        return is_heap() ? heap_.ptr_ : inline_buf_;
    }

    std::size_t size() const {
        return is_heap() ? heap_.size_ : inline_size();
    }

    bool is_inline() const { return !is_heap(); }

    friend std::ostream& operator<<(std::ostream& os, const SboString& s) {
        return os << s.c_str();
    }
};

// Verify no extra overhead
static_assert(sizeof(SboString) == 32, "SboString should be 32 bytes");

int main() {
    std::cout << "sizeof(SboString) = " << sizeof(SboString) << " bytes\n";
    std::cout << "Inline capacity:    " << 31 << " chars\n\n";

    std::cout << "=== Short string (inline) ===\n";
    SboString short_str("Hello, SBO!");
    std::cout << "\"" << short_str << "\" size=" << short_str.size()
              << " inline=" << short_str.is_inline() << "\n";

    std::cout << "\n=== Long string (heap) ===\n";
    SboString long_str("This is a much longer string that exceeds the inline buffer capacity!");
    std::cout << "\"" << long_str << "\"\n"
              << "  size=" << long_str.size()
              << " inline=" << long_str.is_inline() << "\n";

    std::cout << "\n=== Copy (inline stays inline) ===\n";
    SboString copy = short_str;
    std::cout << "copy: \"" << copy << "\" inline=" << copy.is_inline() << "\n";

    std::cout << "\n=== Move heap string (O(1) pointer steal) ===\n";
    SboString moved_heap = std::move(long_str);
    std::cout << "moved: \"" << moved_heap << "\"\n";
    std::cout << "source after move: \"" << long_str << "\" (empty)\n";

    std::cout << "\n=== Move inline string (must copy bytes) ===\n";
    SboString moved_inline = std::move(short_str);
    std::cout << "moved: \"" << moved_inline << "\"\n";

    std::cout << "\n=== Boundary test ===\n";
    std::string exactly31(31, 'X');
    std::string exactly32(32, 'Y');
    SboString fits(exactly31.c_str());
    SboString overflows(exactly32.c_str());
    std::cout << "31 chars: inline=" << fits.is_inline() << "\n";
    std::cout << "32 chars: inline=" << overflows.is_inline() << " (heap)\n";

    return 0;
}
```

**Key insight**: moving a heap-allocated SBO string is O(1) (pointer steal), but moving an inline string is O(n) (byte copy). This is why `noexcept` on move is critical — even though the inline case does real work, it never throws.

**Real-world SBO sizes**: libstdc++ `std::string` = 15 chars inline, libc++ = 22 chars, MSVC = 15 chars. `std::function` typically uses 16-32 bytes of SBO for small callables.'''),

    ("cpp_deep/stack_vs_heap_escape_analysis", r'''When should I allocate on the stack vs the heap in C++? How do compilers reason about escape analysis, and what's the real performance difference?''', r'''<think>
This is about understanding allocation strategies and when the compiler can optimize.

Stack allocation:
- O(1): just bump the stack pointer (sub rsp, N)
- Automatic lifetime: destroyed at scope exit
- Cache-friendly: stack is almost always in L1 cache
- Fixed size: must be known at compile time (VLAs are non-standard in C++)
- Limited: typical stack is 1-8MB

Heap allocation:
- O(n) worst case: free-list traversal, possible system call for large allocations
- Manual lifetime (or via smart pointers)
- Cache-unfriendly: scattered memory locations
- Dynamic size: can grow at runtime
- Limited only by available memory

Escape analysis: in Java/Go, the compiler can prove a heap allocation doesn't escape a function and move it to the stack. C++ doesn't need this as much because the programmer explicitly controls allocation. BUT the compiler can still optimize:
1. It can elide allocations entirely if the object is never observed (as-if rule)
2. It can replace heap allocation with stack allocation via inlining + optimization
3. SROA (Scalar Replacement of Aggregates) can decompose stack objects into registers

When does the compiler actually replace new/delete with stack allocation? In practice: rarely, because operator new is replaceable (the program might have a custom allocator), so the compiler can't assume the default behavior. C++14 allows this optimization explicitly (N3664), but few compilers implement it aggressively.

Clang/GCC with -O2 can sometimes eliminate trivial new/delete pairs where the object is small, non-escaping, and uses default new/delete. But it's not reliable.

Key performance numbers:
- Stack allocation: ~1 CPU cycle
- Heap allocation (malloc): ~50-100 cycles (hot path, no contention)
- Heap allocation (with syscall): ~1000+ cycles
- Cache miss penalty: ~100-300 cycles

So for hot paths, stack > heap, not just because of allocation cost, but because of cache locality.

Let me provide a benchmark and practical guidelines.
</think>

Here is a program demonstrating the performance difference and practical decision-making:

```cpp
#include <iostream>
#include <chrono>
#include <vector>
#include <memory>
#include <array>
#include <numeric>
#include <cstddef>
#include <cstdlib>

// Timing helper
struct Timer {
    std::chrono::high_resolution_clock::time_point start;
    const char* label;

    Timer(const char* l) : start(std::chrono::high_resolution_clock::now()), label(l) {}
    ~Timer() {
        auto end = std::chrono::high_resolution_clock::now();
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        std::cout << "  " << label << ": " << us << " us\n";
    }
};

// Prevent compiler from optimizing away the result
template <typename T>
void do_not_optimize(T&& val) {
    asm volatile("" : : "r,m"(val) : "memory");
}

// === Benchmark 1: allocation cost ===
void bench_allocation() {
    constexpr int N = 100'000;

    std::cout << "=== Allocation Cost (" << N << " iterations) ===\n";

    {
        Timer t("Stack (array<int,64>)");
        long sum = 0;
        for (int i = 0; i < N; ++i) {
            std::array<int, 64> buf;
            buf[0] = i;
            sum += buf[0];
            do_not_optimize(sum);
        }
    }

    {
        Timer t("Heap  (new int[64])");
        long sum = 0;
        for (int i = 0; i < N; ++i) {
            int* buf = new int[64];
            buf[0] = i;
            sum += buf[0];
            delete[] buf;
            do_not_optimize(sum);
        }
    }

    {
        Timer t("Heap  (make_unique<array<int,64>>)");
        long sum = 0;
        for (int i = 0; i < N; ++i) {
            auto buf = std::make_unique<std::array<int, 64>>();
            (*buf)[0] = i;
            sum += (*buf)[0];
            do_not_optimize(sum);
        }
    }
}

// === Benchmark 2: cache locality ===
void bench_cache() {
    constexpr int N = 10'000;
    std::cout << "\n=== Cache Locality (" << N << " objects, sum fields) ===\n";

    struct Data { int values[16]; };

    // Contiguous: array of structs on stack (or contiguous heap)
    {
        std::vector<Data> contiguous(N);
        for (int i = 0; i < N; ++i) contiguous[i].values[0] = i;

        Timer t("Contiguous (vector<Data>)");
        long sum = 0;
        for (int rep = 0; rep < 1000; ++rep) {
            for (int i = 0; i < N; ++i) sum += contiguous[i].values[0];
        }
        do_not_optimize(sum);
    }

    // Scattered: array of pointers to heap-allocated structs
    {
        std::vector<std::unique_ptr<Data>> scattered(N);
        for (int i = 0; i < N; ++i) {
            scattered[i] = std::make_unique<Data>();
            scattered[i]->values[0] = i;
        }

        Timer t("Scattered  (vector<unique_ptr<Data>>)");
        long sum = 0;
        for (int rep = 0; rep < 1000; ++rep) {
            for (int i = 0; i < N; ++i) sum += scattered[i]->values[0];
        }
        do_not_optimize(sum);
    }
}

// === Decision framework ===
void print_guidelines() {
    std::cout << R"(
=== Stack vs Heap Decision Framework ===

USE STACK when:
  - Size known at compile time
  - Object fits comfortably (< ~100KB rule of thumb)
  - Short lifetime (scope-bounded)
  - Performance-critical hot path
  - No need for dynamic polymorphism
  Examples: loop variables, small arrays, RAII guards, iterators

USE HEAP when:
  - Size determined at runtime
  - Large objects (> 100KB — stack overflow risk)
  - Lifetime must outlive the creating scope
  - Need polymorphic types (base pointer to derived)
  - Shared ownership (shared_ptr)
  - Collections that grow (vector, map)
  Examples: dynamic arrays, tree nodes, interned strings, connection pools

HYBRID patterns:
  - SBO (Small Buffer Optimization): inline for small, heap for large
  - PMR monotonic_buffer_resource: stack-backed initial buffer, heap overflow
  - alloca(): stack allocation with runtime size (non-standard, dangerous)
  - Custom pool: heap-allocated pool, stack-speed bump allocation

COMPILER OPTIMIZATIONS (don't rely on these):
  - C++14 allows new/delete elision (N3664), but compilers rarely do it
  - SROA: stack objects decomposed into registers
  - Inlining: can expose new/delete to optimizer, enabling elision
)";
}

int main() {
    bench_allocation();
    bench_cache();
    print_guidelines();
    return 0;
}
```

**Typical benchmark results (x86-64, -O2):**

| Allocation type | Time per alloc | Why |
|----------------|---------------|-----|
| Stack array | ~1 ns | Single `sub rsp` instruction |
| `new int[64]` | ~30-80 ns | malloc free-list + bookkeeping |
| Contiguous iteration | 1x baseline | Prefetcher-friendly, L1 cache hits |
| Scattered iteration | 3-10x slower | Pointer chasing, cache misses |

**The real cost is not just allocation — it is cache locality.** A program that heap-allocates millions of small objects and iterates them pays a massive cache-miss penalty, even if the allocation itself is amortized.'''),

    ("cpp_deep/memory_order_lockfree_shared_ptr", r'''What memory orderings are needed for a lock-free reference-counted pointer (like shared_ptr's atomic ref count)? Why not just use memory_order_seq_cst everywhere?''', r'''<think>
This is one of the subtler topics in C++. Let me think through the memory orderings for atomic reference counting.

A reference count has two operations:
1. Increment (copy/share): just atomically increment. Any ordering that prevents it from being lost.
2. Decrement (release/destroy): atomically decrement, and if it reaches zero, destroy the object.

For increment (adding a reference):
- memory_order_relaxed is sufficient. Why? We already have a reference (we're copying from an existing shared_ptr). The existence of that reference guarantees the object is alive. We don't need to synchronize any other memory with this operation.

For decrement (removing a reference):
- We need memory_order_release. Why? When we drop a reference, any writes we made to the shared object must be visible to whichever thread later destroys it. Release ensures our stores are published before the count drops.
- But wait: the thread that sees the count drop to zero must also see all writes from ALL threads that previously decremented. So it needs memory_order_acquire (or a fence).

The classic pattern:
```
// Increment
ref_count.fetch_add(1, memory_order_relaxed);

// Decrement
if (ref_count.fetch_sub(1, memory_order_release) == 1) {
    atomic_thread_fence(memory_order_acquire);
    delete obj;
}
```

Why the fence instead of memory_order_acq_rel on the fetch_sub? Because only the thread that gets 1 (meaning it's the last one) needs acquire semantics. Using acq_rel on every decrement forces an unnecessary acquire barrier on threads that don't destroy. The fence is cheaper in that only the destroying thread pays for acquire.

Actually, this is the Boost.Atomic / libstdc++ pattern. Some implementations just use acq_rel on the fetch_sub for simplicity, which is correct but slightly less optimal.

Why not seq_cst everywhere?
1. seq_cst adds a full memory fence (MFENCE on x86, DMB on ARM). On x86, most operations are already strongly ordered, so the difference is small. On ARM/POWER, the difference is significant.
2. seq_cst provides a single total order across all seq_cst operations. Reference counting doesn't need a total order — it only needs that the destroying thread sees all prior modifications.
3. Using the weakest correct ordering documents intent and prevents accidentally relying on stronger-than-necessary guarantees.

Let me implement a simplified atomic_shared_ptr to demonstrate.
</think>

Here is a simplified reference-counted pointer showing correct memory orderings with explanations:

```cpp
#include <iostream>
#include <atomic>
#include <thread>
#include <vector>
#include <cassert>

// Simplified intrusive reference counting with correct memory orderings
template <typename T>
class IntrusivePtr {
    struct ControlBlock {
        T object;
        std::atomic<int> ref_count{1};

        template <typename... Args>
        explicit ControlBlock(Args&&... args) : object(std::forward<Args>(args)...) {}
    };

    ControlBlock* block_ = nullptr;

    void add_ref() {
        if (block_) {
            // RELAXED: We already hold a reference, so the object is guaranteed
            // alive. We just need the increment to be atomic, not ordered
            // relative to other memory operations.
            //
            // No other thread can destroy the object while we hold a reference,
            // so there's no race to protect against.
            block_->ref_count.fetch_add(1, std::memory_order_relaxed);
        }
    }

    void release() {
        if (block_) {
            // RELEASE: Ensures all our writes to the shared object are
            // published BEFORE the ref count drops. Without this, the
            // destroying thread might see stale data.
            //
            // Why not ACQ_REL? Only the destroying thread needs acquire.
            // Non-destroying threads waste cycles acquiring unnecessarily.
            int prev = block_->ref_count.fetch_sub(1, std::memory_order_release);

            if (prev == 1) {
                // We're the last reference. We need to SEE all writes from
                // every thread that previously released their reference.
                //
                // ACQUIRE fence: synchronizes with all the release stores
                // from other threads' fetch_sub operations.
                std::atomic_thread_fence(std::memory_order_acquire);

                // Now safe to read/destroy the object — we've acquired
                // all modifications.
                delete block_;
            }
        }
    }

public:
    IntrusivePtr() = default;

    template <typename... Args>
    static IntrusivePtr make(Args&&... args) {
        IntrusivePtr p;
        p.block_ = new ControlBlock(std::forward<Args>(args)...);
        return p;
    }

    ~IntrusivePtr() { release(); }

    IntrusivePtr(const IntrusivePtr& other) : block_(other.block_) {
        add_ref();
    }

    IntrusivePtr& operator=(const IntrusivePtr& other) {
        if (this != &other) {
            release();
            block_ = other.block_;
            add_ref();
        }
        return *this;
    }

    IntrusivePtr(IntrusivePtr&& other) noexcept : block_(other.block_) {
        other.block_ = nullptr;  // No ref count change — transfer ownership
    }

    IntrusivePtr& operator=(IntrusivePtr&& other) noexcept {
        if (this != &other) {
            release();
            block_ = other.block_;
            other.block_ = nullptr;
        }
        return *this;
    }

    T& operator*() { return block_->object; }
    T* operator->() { return &block_->object; }
    int use_count() const {
        return block_ ? block_->ref_count.load(std::memory_order_relaxed) : 0;
    }
    explicit operator bool() const { return block_ != nullptr; }
};

// === Test: concurrent reference counting ===
struct SharedData {
    std::atomic<int> value{0};
    ~SharedData() { std::cout << "  SharedData destroyed (value=" << value.load() << ")\n"; }
};

void concurrent_test() {
    std::cout << "=== Concurrent reference counting ===\n";

    auto ptr = IntrusivePtr<SharedData>::make();
    constexpr int NUM_THREADS = 8;
    constexpr int OPS_PER_THREAD = 100'000;

    std::vector<std::thread> threads;

    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&ptr, t]() {
            for (int i = 0; i < OPS_PER_THREAD; ++i) {
                // Copy (increment ref count)
                IntrusivePtr<SharedData> local = ptr;
                // Modify shared data
                local->value.fetch_add(1, std::memory_order_relaxed);
                // local goes out of scope (decrement ref count)
            }
        });
    }

    for (auto& t : threads) t.join();

    std::cout << "  Final value: " << ptr->value.load() << "\n";
    std::cout << "  Expected:    " << NUM_THREADS * OPS_PER_THREAD << "\n";
    std::cout << "  Ref count:   " << ptr.use_count() << "\n";

    std::cout << "\n  Dropping last reference...\n";
    // ptr goes out of scope here — destroying SharedData
}

int main() {
    concurrent_test();

    std::cout << R"(
=== Memory Ordering Summary ===

Operation          | Ordering          | Why
-------------------|-------------------|------------------------------------------
Increment (copy)   | relaxed           | Object already alive, just need atomicity
Decrement (drop)   | release           | Publish our writes before count drops
Destroy (count==0) | acquire fence     | See all writes from all prior releasers
Load count (debug) | relaxed           | Approximate value is fine

=== Why NOT seq_cst everywhere? ===

Platform  | seq_cst cost          | relaxed/release cost
----------|-----------------------|---------------------
x86-64    | MFENCE (~20 cycles)   | LOCK XADD (~10 cycles)
ARM       | DMB ISH (~40 cycles)  | no barrier / DMB (~10 cycles)
POWER     | hwsync (~50+ cycles)  | lwsync (~20 cycles)

For hot ref counting (millions of copies/sec), the difference is measurable.
seq_cst also obscures intent: readers of the code can't tell WHAT ordering
constraint you actually need.
)";

    return 0;
}
```

**The three rules of atomic reference counting:**
1. **Increment = relaxed** — you already own a reference, so the object cannot die.
2. **Decrement = release** — publish your writes before the count drops.
3. **Delete = acquire fence** — the destroyer must see all prior writes from all threads.

This is exactly what `std::shared_ptr` implementations use internally.'''),

    ("cpp_deep/preventing_dangling_references", r'''How do I prevent dangling references in C++? What tools and patterns exist for catching these bugs at compile time or runtime?''', r'''<think>
Dangling references are one of the most common C++ bugs. A reference (or pointer) outlives the object it refers to. Accessing it is undefined behavior.

Common causes:
1. Returning a reference to a local variable
2. Storing a reference to a temporary
3. Iterator invalidation (vector reallocation while holding iterators)
4. Use-after-move
5. Capturing local variables by reference in lambdas that outlive them
6. string_view/span pointing to destroyed data

Prevention strategies:

Compile-time:
1. -Wreturn-local-addr / -Wdangling (GCC/Clang): catches obvious cases
2. [[clang::lifetimebound]] attribute: tells compiler a parameter's lifetime is bound to return value
3. C++ Core Guidelines Lifetime Profile: experimental clang-tidy checks
4. Rust-style ownership thinking: design APIs so lifetimes are clear

Runtime:
1. AddressSanitizer (ASan): catches use-after-free, stack-use-after-return
2. Valgrind: memory error detection
3. Debug iterators (MSVC _ITERATOR_DEBUG_LEVEL, libstdc++ _GLIBCXX_DEBUG)

Design patterns:
1. Return by value, not by reference
2. Use smart pointers for heap objects
3. weak_ptr for non-owning references to shared objects
4. string/vector over string_view/span for owned data
5. Avoid reference members in classes (they're hard to reason about)

Let me show concrete examples of each dangling pattern and its fix.
</think>

Here is a catalog of dangling reference patterns and their prevention:

```cpp
#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <memory>
#include <functional>
#include <optional>
#include <span>

// Compile with:
//   g++ -std=c++20 -Wall -Wextra -Wdangling -fsanitize=address,undefined -g

// ==========================================================
// PATTERN 1: Returning reference to local
// ==========================================================
namespace pattern1 {
    // BAD: dangling reference to destroyed local
    // const std::string& bad_get_name() {
    //     std::string name = "Alice";
    //     return name;  // WARNING: reference to local variable returned
    // }

    // FIX: return by value (NRVO eliminates the copy anyway)
    std::string good_get_name() {
        std::string name = "Alice";
        return name;  // NRVO: constructed directly in caller's storage
    }
}

// ==========================================================
// PATTERN 2: Reference to temporary
// ==========================================================
namespace pattern2 {
    struct Config {
        std::string name;
        const std::string& get_name() const { return name; }
    };

    Config make_config() { return Config{"temp"}; }

    void demo() {
        // BAD: reference binds to temporary Config, which is destroyed at semicolon
        // const std::string& name = make_config().get_name();  // DANGLING!

        // FIX 1: extend temporary lifetime by binding the whole object
        const Config& cfg = make_config();  // Temporary lifetime extended
        const std::string& name = cfg.get_name();  // Safe: cfg is alive
        std::cout << "  Pattern 2 fix: " << name << "\n";

        // FIX 2: copy into a value
        std::string name2 = make_config().get_name();  // Copy, always safe
        std::cout << "  Pattern 2 fix2: " << name2 << "\n";
    }
}

// ==========================================================
// PATTERN 3: Iterator invalidation
// ==========================================================
namespace pattern3 {
    void demo() {
        std::vector<int> v = {1, 2, 3, 4, 5};
        // auto it = v.begin();  // Points to v[0]
        // v.push_back(6);       // May reallocate! 'it' is now DANGLING

        // FIX 1: use index instead of iterator across mutations
        std::size_t idx = 0;
        v.push_back(6);
        std::cout << "  Pattern 3 fix: v[" << idx << "] = " << v[idx] << "\n";

        // FIX 2: reserve() before taking iterators
        v.reserve(100);
        auto it = v.begin();
        v.push_back(7);  // Safe: no reallocation (size < capacity)
        std::cout << "  Pattern 3 fix2: *it = " << *it << "\n";
    }
}

// ==========================================================
// PATTERN 4: Lambda capturing local by reference
// ==========================================================
namespace pattern4 {
    // BAD: lambda captures local by reference, outlives function
    // std::function<int()> bad_make_counter() {
    //     int count = 0;
    //     return [&count]() { return ++count; };  // DANGLING capture!
    // }

    // FIX: capture by value (or use shared state)
    std::function<int()> good_make_counter() {
        auto count = std::make_shared<int>(0);
        return [count]() { return ++(*count); };  // Shared ownership, safe
    }

    // FIX 2: mutable lambda with value capture
    std::function<int()> good_make_counter_v2() {
        int count = 0;
        return [count]() mutable { return ++count; };  // Own copy, safe
    }
}

// ==========================================================
// PATTERN 5: string_view dangling
// ==========================================================
namespace pattern5 {
    // BAD: returning string_view to a local/temporary
    // std::string_view bad_trim(const std::string& s) {
    //     std::string trimmed = s.substr(1);  // New string
    //     return trimmed;  // DANGLING: trimmed destroyed at return
    // }

    // FIX: return string when you create new data
    std::string good_trim(const std::string& s) {
        return s.substr(1);  // Return owned string
    }

    // string_view is SAFE when pointing to data that outlives it
    std::string_view safe_prefix(std::string_view sv) {
        return sv.substr(0, 5);  // Points into caller's data — safe if caller's data lives
    }
}

// ==========================================================
// PATTERN 6: Use-after-move
// ==========================================================
namespace pattern6 {
    void demo() {
        std::string s = "important data";
        std::vector<std::string> v;

        v.push_back(std::move(s));

        // BAD: s is in moved-from state
        // std::cout << s.size() << "\n";  // Technically valid but empty/unspecified

        // FIX: don't use after move, or reassign first
        s = "new data";  // Valid: reassigned
        std::cout << "  Pattern 6 fix: " << s << "\n";
    }
}

// ==========================================================
// PATTERN 7: Preventing with weak_ptr
// ==========================================================
namespace pattern7 {
    void demo() {
        std::weak_ptr<int> wp;
        {
            auto sp = std::make_shared<int>(42);
            wp = sp;
            if (auto locked = wp.lock()) {
                std::cout << "  Alive: " << *locked << "\n";
            }
        }
        // sp destroyed, wp expired
        if (auto locked = wp.lock()) {
            std::cout << "  Should not print\n";
        } else {
            std::cout << "  Pattern 7: weak_ptr correctly detected dead object\n";
        }
    }
}

int main() {
    std::cout << "=== Pattern 1: return by value ===\n";
    std::cout << "  " << pattern1::good_get_name() << "\n";

    std::cout << "\n=== Pattern 2: temporary lifetime ===\n";
    pattern2::demo();

    std::cout << "\n=== Pattern 3: iterator invalidation ===\n";
    pattern3::demo();

    std::cout << "\n=== Pattern 4: lambda capture ===\n";
    auto counter = pattern4::good_make_counter();
    std::cout << "  count: " << counter() << ", " << counter() << "\n";

    std::cout << "\n=== Pattern 5: string_view ===\n";
    std::string data = "Hello World";
    auto prefix = pattern5::safe_prefix(data);
    std::cout << "  prefix: " << prefix << "\n";

    std::cout << "\n=== Pattern 6: use-after-move ===\n";
    pattern6::demo();

    std::cout << "\n=== Pattern 7: weak_ptr detection ===\n";
    pattern7::demo();

    std::cout << R"(
=== Compile-time flags to catch dangling ===
  -Wreturn-local-addr      Returning reference to local
  -Wdangling               Dangling references (GCC 12+)
  -Wlifetime               Lifetime analysis (experimental)
  -fsanitize=address       ASan: catches use-after-free at runtime
  -D_GLIBCXX_DEBUG         Debug mode: checked iterators (libstdc++)
  -D_ITERATOR_DEBUG_LEVEL=2  MSVC checked iterators
)";

    return 0;
}
```

**Prevention hierarchy (most effective first):**
1. **Return by value** — eliminates most dangling returns (NRVO makes it free)
2. **Smart pointers** — `unique_ptr` for ownership, `weak_ptr` for observation
3. **Compiler warnings** — `-Wdangling`, `-Wreturn-local-addr`
4. **AddressSanitizer** — catches what the compiler misses at runtime
5. **Design rules** — avoid reference members, prefer value semantics, minimize raw pointer APIs'''),

    ("cpp_deep/string_view_dangling_dangers", r'''What are the specific dangers of std::string_view? I keep hearing it's dangerous with temporaries. Show me every way it can go wrong.''', r'''<think>
string_view is a non-owning view — it's just a (pointer, length) pair. It doesn't own the data, doesn't manage lifetime. This makes it dangerous when the underlying data is destroyed.

The key dangers:
1. string_view from a temporary string — the temporary is destroyed, view is dangling
2. Storing string_view as a class member — the source may die first
3. Returning string_view from a function that creates a string
4. string_view from string concatenation (the result is a temporary)
5. Implicit conversion: functions taking string_view can silently bind to temporaries
6. string_view from c_str() of a moved string
7. Null termination: string_view is NOT null-terminated — c_str()-like usage fails

Let me catalog each one with compilable examples and fixes.
</think>

Here is a comprehensive catalog of every `string_view` pitfall with fixes:

```cpp
#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <map>
#include <optional>
#include <sstream>

// ==========================================================
// DANGER 1: string_view from temporary string
// ==========================================================
namespace danger1 {
    std::string make_greeting(const std::string& name) {
        return "Hello, " + name + "!";
    }

    void demo() {
        // BAD: string_view binds to temporary returned by make_greeting
        // Temporary is destroyed at end of statement. sv is DANGLING.
        std::string_view sv = make_greeting("Alice");
        // std::cout << sv << "\n";  // UB: reading destroyed memory

        // FIX: store in a std::string
        std::string safe = make_greeting("Alice");
        std::string_view sv2 = safe;  // OK: safe outlives sv2
        std::cout << "  Fix: " << sv2 << "\n";
    }
}

// ==========================================================
// DANGER 2: string_view as class member
// ==========================================================
namespace danger2 {
    // BAD: stores non-owning view — source can die at any time
    struct BadConfig {
        std::string_view name;  // Who owns the string this points to?
    };

    // FIX: store std::string for owned data
    struct GoodConfig {
        std::string name;  // Owns the data
    };

    void demo() {
        GoodConfig cfg;
        {
            std::string temp = "database_host";
            cfg.name = temp;  // Copies into cfg.name
        }
        // temp is destroyed, but cfg.name owns its own copy
        std::cout << "  Fix: " << cfg.name << "\n";
    }
}

// ==========================================================
// DANGER 3: Returning string_view from function that creates data
// ==========================================================
namespace danger3 {
    // BAD: returns view into local string
    // std::string_view bad_upper(std::string_view input) {
    //     std::string result(input);
    //     for (auto& c : result) c = toupper(c);
    //     return result;  // DANGLING: result destroyed
    // }

    // FIX: return std::string when you create new data
    std::string good_upper(std::string_view input) {
        std::string result(input);
        for (auto& c : result) c = static_cast<char>(std::toupper(c));
        return result;
    }

    // OK: return string_view into the INPUT data (caller manages lifetime)
    std::string_view safe_trim_front(std::string_view sv) {
        auto pos = sv.find_first_not_of(' ');
        return pos == std::string_view::npos ? "" : sv.substr(pos);
    }
}

// ==========================================================
// DANGER 4: string_view from concatenation
// ==========================================================
namespace danger4 {
    void demo() {
        std::string a = "hello";
        std::string b = "world";

        // BAD: a + " " + b creates a temporary std::string
        // string_view binds to it, temporary dies at semicolon
        // std::string_view sv = a + " " + b;  // DANGLING!

        // FIX: store the concatenation
        std::string concat = a + " " + b;
        std::string_view sv = concat;
        std::cout << "  Fix: " << sv << "\n";
    }
}

// ==========================================================
// DANGER 5: Implicit conversion to string_view
// ==========================================================
namespace danger5 {
    void process(std::string_view sv) {
        std::cout << "  Processing: " << sv << "\n";
    }

    void demo() {
        // OK: string literal has static lifetime
        process("literal");  // Safe

        // OK: named string outlives the call
        std::string s = "named";
        process(s);  // Safe

        // SUBTLE: temporary from function return
        // process(std::string("temp"));  // "Safe" within function call (temp lives until ;)
        // But if process() STORES the string_view, it's dangling after the call!
    }
}

// ==========================================================
// DANGER 6: string_view after move
// ==========================================================
namespace danger6 {
    void demo() {
        std::string original = "important";
        std::string_view sv = original;

        // Move the string — sv now points to freed/stolen memory
        std::string stolen = std::move(original);
        // std::cout << sv << "\n";  // UB: original's buffer is gone

        // FIX: invalidate views before moving
        sv = {};  // Clear the view
        std::string stolen2 = std::move(stolen);
        std::cout << "  Fix: explicitly clear views before move\n";
    }
}

// ==========================================================
// DANGER 7: Not null-terminated
// ==========================================================
namespace danger7 {
    void demo() {
        std::string full = "Hello, World!";
        std::string_view sv = full;
        std::string_view sub = sv.substr(0, 5);  // "Hello"

        // BAD: sub is NOT null-terminated
        // printf("%s", sub.data());  // Prints "Hello, World!" (reads past end)

        // FIX: convert to string if you need null termination
        std::string safe(sub);
        std::printf("  Fix: %s\n", safe.c_str());
    }
}

// ==========================================================
// DANGER 8: string_view in containers as keys
// ==========================================================
namespace danger8 {
    void demo() {
        std::map<std::string_view, int> bad_map;

        {
            std::string key = "temp_key";
            bad_map[key] = 42;  // string_view points into key's buffer
        }
        // key destroyed — map now has dangling key
        // for (auto& [k, v] : bad_map) std::cout << k << "\n";  // UB

        // FIX: use std::string as key, or ensure all keys are string literals / static
        std::map<std::string, int> good_map;
        {
            std::string key = "temp_key";
            good_map[key] = 42;  // Copies key into map
        }
        std::cout << "  Fix: good_map[temp_key] = " << good_map["temp_key"] << "\n";
    }
}

int main() {
    std::cout << "=== Danger 1: temporary string ===\n";
    danger1::demo();

    std::cout << "\n=== Danger 2: class member ===\n";
    danger2::demo();

    std::cout << "\n=== Danger 3: returning from function ===\n";
    std::cout << "  " << danger3::good_upper("hello") << "\n";

    std::cout << "\n=== Danger 4: concatenation ===\n";
    danger4::demo();

    std::cout << "\n=== Danger 5: implicit conversion ===\n";
    danger5::demo();

    std::cout << "\n=== Danger 6: after move ===\n";
    danger6::demo();

    std::cout << "\n=== Danger 7: not null-terminated ===\n";
    danger7::demo();

    std::cout << "\n=== Danger 8: container keys ===\n";
    danger8::demo();

    std::cout << R"(
=== SAFE uses of string_view ===
  1. Function parameters (caller's string outlives the call)
  2. Views into string literals (static lifetime)
  3. Substring views within the same scope as the parent string
  4. Range-for over tokens (within parsing scope)

=== UNSAFE uses of string_view ===
  1. Class members (unless lifetime is externally guaranteed)
  2. Return values from functions that create strings
  3. Container keys/values (unless data is static)
  4. Stored in data structures that outlive the source
)";

    return 0;
}
```

**One-line rule**: `string_view` is safe when you can prove the source outlives the view. If in doubt, use `std::string`.'''),

    ("cpp_deep/span_nonowning_view", r'''Show me how to use std::span as a non-owning view over contiguous data in C++20. What are the advantages over raw pointer + length?''', r'''<think>
std::span is C++20's answer to the "pointer + size" pattern. It's a non-owning view over contiguous memory, similar to string_view but for any type. It carries type information, bounds checking (in debug), and works with all contiguous containers.

Key features:
- Fixed extent (compile-time size) or dynamic extent (runtime size)
- No ownership — same dangling risks as string_view
- Works with arrays, vectors, unique_ptr<T[]>, etc.
- Subspan operations without copying
- Type-safe: no void* casting

Advantages over raw pointer + length:
1. Single parameter instead of two
2. Carries element type
3. Range-based for loop support
4. .size(), .empty(), .front(), .back(), operator[]
5. Optional bounds checking in debug builds
6. Fixed extent version encodes size in the type

I should show practical examples: function signatures, subspans, fixed vs dynamic extent, interop with C APIs.
</think>

Here is a comprehensive `std::span` tutorial with practical patterns:

```cpp
#include <iostream>
#include <span>
#include <vector>
#include <array>
#include <numeric>
#include <algorithm>
#include <cstddef>
#include <memory>

// === OLD WAY: raw pointer + size (error-prone) ===
void old_sum(const int* data, std::size_t size) {
    int s = 0;
    for (std::size_t i = 0; i < size; ++i) s += data[i];
    // Easy to pass wrong size, no type safety, no range-for
    std::cout << "  old_sum: " << s << "\n";
}

// === NEW WAY: std::span (dynamic extent) ===
void modern_sum(std::span<const int> data) {
    // Single parameter carries both pointer AND size
    int s = 0;
    for (int x : data) s += x;  // Range-based for loop!
    std::cout << "  modern_sum: " << s << " (size=" << data.size() << ")\n";
}

// === Fixed extent: size baked into the type ===
void process_triple(std::span<int, 3> rgb) {
    // Compiler enforces exactly 3 elements
    std::cout << "  RGB: " << rgb[0] << ", " << rgb[1] << ", " << rgb[2] << "\n";
}

// === Span as a function parameter: works with anything contiguous ===
double average(std::span<const double> values) {
    if (values.empty()) return 0.0;
    double sum = 0.0;
    for (double v : values) sum += v;
    return sum / static_cast<double>(values.size());
}

// === Subspan: zero-copy slicing ===
void subspan_demo(std::span<const int> data) {
    std::cout << "  Full span:  ";
    for (int x : data) std::cout << x << " ";
    std::cout << "\n";

    // First 3 elements
    auto head = data.first(3);
    std::cout << "  first(3):   ";
    for (int x : head) std::cout << x << " ";
    std::cout << "\n";

    // Last 2 elements
    auto tail = data.last(2);
    std::cout << "  last(2):    ";
    for (int x : tail) std::cout << x << " ";
    std::cout << "\n";

    // Middle slice: offset 2, count 3
    auto mid = data.subspan(2, 3);
    std::cout << "  subspan(2,3): ";
    for (int x : mid) std::cout << x << " ";
    std::cout << "\n";
}

// === Interop with C APIs ===
// Simulated C function
extern "C" void c_api_process(float* buffer, int count) {
    for (int i = 0; i < count; ++i) {
        buffer[i] *= 2.0f;
    }
}

void c_interop_demo() {
    std::vector<float> data = {1.0f, 2.0f, 3.0f, 4.0f};
    std::span<float> view(data);

    // Pass span to C API
    c_api_process(view.data(), static_cast<int>(view.size()));

    std::cout << "  After C API: ";
    for (float f : view) std::cout << f << " ";
    std::cout << "\n";
}

// === Mutable span: modifying data through the view ===
void fill_pattern(std::span<int> output) {
    for (std::size_t i = 0; i < output.size(); ++i) {
        output[i] = static_cast<int>(i * i);
    }
}

// === Span of bytes: type-erased binary data ===
template <typename T>
void print_bytes(const T& obj) {
    auto bytes = std::as_bytes(std::span{&obj, 1});
    std::cout << "  Bytes (" << bytes.size() << "): ";
    for (auto b : bytes) {
        std::printf("%02x ", static_cast<unsigned>(b));
    }
    std::cout << "\n";
}

int main() {
    std::cout << "=== Dynamic extent: accepts any contiguous source ===\n";

    int c_array[] = {1, 2, 3, 4, 5};
    std::vector<int> vec = {10, 20, 30, 40, 50};
    std::array<int, 5> arr = {100, 200, 300, 400, 500};

    // ALL of these work with the same function:
    modern_sum(c_array);       // C array
    modern_sum(vec);           // std::vector
    modern_sum(arr);           // std::array
    modern_sum({1, 2, 3});     // initializer_list (temporary — careful!)

    std::cout << "\n=== Fixed extent: compile-time size ===\n";
    int rgb_data[3] = {255, 128, 0};
    process_triple(rgb_data);  // OK: exactly 3 elements
    // process_triple(vec);    // COMPILE ERROR: can't convert dynamic to fixed extent 3

    std::cout << "\n=== Subspan (zero-copy slicing) ===\n";
    subspan_demo(vec);

    std::cout << "\n=== Average (works with any contiguous doubles) ===\n";
    std::vector<double> prices = {9.99, 14.50, 7.25, 22.00};
    std::cout << "  Average price: " << average(prices) << "\n";

    double raw[] = {1.0, 2.0, 3.0};
    std::cout << "  Average raw:   " << average(raw) << "\n";

    std::cout << "\n=== Mutable span (write through view) ===\n";
    std::vector<int> output(6);
    fill_pattern(output);
    std::cout << "  Pattern: ";
    for (int x : output) std::cout << x << " ";
    std::cout << "\n";

    std::cout << "\n=== C API interop ===\n";
    c_interop_demo();

    std::cout << "\n=== Byte-level view ===\n";
    int32_t val = 0xDEADBEEF;
    print_bytes(val);

    std::cout << R"(
=== span vs pointer+size ===
Feature               | raw ptr+size  | std::span
---------------------------------------------------
Single parameter      | No (2 params) | Yes
Range-based for       | No            | Yes
.size(), .empty()     | Manual        | Built-in
Bounds check (debug)  | No            | Yes
Type safety           | Weak          | Strong
Subspan/slicing       | Manual math   | .first/.last/.subspan
Works with vector     | .data()       | Implicit conversion
sizeof                | 16 bytes      | 16 bytes (identical!)
)";

    return 0;
}
```

**`std::span` is the C++20 replacement for `(T* ptr, size_t n)` pairs.** Same performance, zero overhead, dramatically safer and more expressive. Use it for all function parameters that need a view into contiguous data.

**Caveat**: like `string_view`, span is **non-owning**. The same dangling-reference dangers apply — never store a span that outlives its source data.'''),

    ("cpp_deep/rvo_vs_stdmove_return", r'''When should I use std::move on a return statement vs relying on RVO? I've heard conflicting advice.''', r'''<think>
This overlaps somewhat with the copy elision pair, but the user is asking specifically about the return std::move anti-pattern. Let me focus on the decision tree and the C++17 vs C++20 differences.

The simple rule: almost never use std::move on return. Let me explain the cases:

1. Return local variable → compiler does NRVO or implicit move. Adding std::move PREVENTS NRVO.
2. Return parameter → C++20 does implicit move. C++17 requires explicit std::move for move semantics (but even in C++17, it still gets implicit move in many implementations).
3. Return member → need std::move (members don't get implicit move).
4. Return conditional (ternary) → may need std::move depending on context.
5. Return result of function call → RVO (prvalue), std::move is redundant/harmful.

Let me create a focused example with a clear decision tree.
</think>

Here is a definitive guide with a concrete decision tree:

```cpp
#include <iostream>
#include <string>
#include <utility>
#include <vector>
#include <optional>

struct Heavy {
    std::string data;
    Heavy(std::string d) : data(std::move(d)) {
        std::cout << "  Construct: " << data << "\n";
    }
    Heavy(const Heavy& o) : data(o.data) {
        std::cout << "  COPY: " << data << "\n";
    }
    Heavy(Heavy&& o) noexcept : data(std::move(o.data)) {
        std::cout << "  MOVE: " << data << "\n";
    }
    Heavy& operator=(Heavy&&) noexcept = default;
    Heavy& operator=(const Heavy&) = default;
};

// ==========================================================
// CASE 1: Returning local variable
// VERDICT: NO std::move (NRVO does better)
// ==========================================================
Heavy case1_good() {
    Heavy h("local");
    h.data += "-modified";
    return h;          // NRVO: zero copies, zero moves. Best possible.
}

Heavy case1_bad() {
    Heavy h("local");
    h.data += "-modified";
    return std::move(h); // PREVENTS NRVO! Forces a move. Strictly worse.
}

// ==========================================================
// CASE 2: Returning function parameter
// VERDICT: std::move in C++17, not needed in C++20
// ==========================================================
Heavy case2_cpp17(Heavy h) {
    h.data += "-processed";
    return std::move(h); // C++17: needed (parameters don't get implicit move)
                         // C++20: unnecessary (P1825 added implicit move for params)
}

// ==========================================================
// CASE 3: Returning class member
// VERDICT: YES std::move (members never get implicit move)
// ==========================================================
struct Wrapper {
    Heavy member{"member"};

    Heavy extract() && {
        return std::move(member);  // CORRECT: members need explicit move
    }

    // BAD: without move, this COPIES
    // Heavy extract_bad() && {
    //     return member;  // COPIES! member is an lvalue, no implicit move
    // }
};

// ==========================================================
// CASE 4: Returning result of a function call (prvalue)
// VERDICT: NO std::move (already RVO, move is redundant)
// ==========================================================
Heavy make_heavy() { return Heavy("factory"); }

Heavy case4_good() {
    return make_heavy();           // RVO: mandatory elision in C++17
}

Heavy case4_bad() {
    return std::move(make_heavy()); // Prevents RVO! Forces a move.
}

// ==========================================================
// CASE 5: Conditional return — depends on structure
// ==========================================================
Heavy case5_same_var(bool flag) {
    Heavy h("conditional");
    if (flag) {
        h.data += "-flagged";
    }
    return h;  // OK: same variable on all paths → NRVO possible
}

Heavy case5_diff_vars(bool flag) {
    // NRVO impossible: different objects on different paths
    if (flag) {
        Heavy a("path-A");
        return a;  // Implicit move (no NRVO, but still moves not copies)
    } else {
        Heavy b("path-B");
        return b;  // Implicit move
    }
    // No need for std::move — implicit move kicks in when NRVO fails
}

// ==========================================================
// CASE 6: Returning through optional/variant
// ==========================================================
std::optional<Heavy> case6() {
    Heavy h("optional-payload");
    return h;  // Implicit move into optional (NRVO doesn't apply to optional wrapping)
    // std::move is not needed — compiler knows h is about to die
}

int main() {
    std::cout << "=== Case 1: Local (NO std::move) ===\n";
    std::cout << "  --- Good (NRVO) ---\n";
    auto r1 = case1_good();
    std::cout << "  --- Bad (forced move) ---\n";
    auto r1b = case1_bad();

    std::cout << "\n=== Case 2: Parameter (std::move in C++17) ===\n";
    auto r2 = case2_cpp17(Heavy("param"));

    std::cout << "\n=== Case 3: Member (YES std::move) ===\n";
    Wrapper w;
    auto r3 = std::move(w).extract();

    std::cout << "\n=== Case 4: Prvalue return (NO std::move) ===\n";
    std::cout << "  --- Good (RVO) ---\n";
    auto r4 = case4_good();
    std::cout << "  --- Bad (forced move) ---\n";
    auto r4b = case4_bad();

    std::cout << "\n=== Case 5: Conditional ===\n";
    auto r5a = case5_same_var(true);
    auto r5b = case5_diff_vars(true);

    std::cout << "\n=== Case 6: Through optional ===\n";
    auto r6 = case6();

    std::cout << R"(
=== DECISION TREE ===

  Returning what?
  |
  +-- Local variable ──────────── return x;        (NRVO or implicit move)
  |
  +-- Function parameter ─────── return x;         (C++20: implicit move)
  |                               return move(x);  (C++17: explicit move)
  |
  +-- Class member ────────────── return move(m);   (always: members need it)
  |
  +-- Function call result ────── return f();       (RVO: mandatory elision)
  |
  +-- Ternary/conditional ─────── return x;         (implicit move if NRVO fails)

  Rule: "return std::move(x)" is almost always wrong unless x is a MEMBER.
)";

    return 0;
}
```

**The one rule to remember: `std::move` on return is only correct for class members.** Everything else either gets NRVO (best), implicit move (good), or is already a prvalue (mandatory RVO). Adding `std::move` can only make things worse in those cases.'''),

    ("cpp_deep/self_assignment_operator_eq", r'''How do I make operator= safe against self-assignment? What patterns exist and which is best?''', r'''<think>
Self-assignment (a = a) can cause bugs in copy assignment if the implementation deletes the old resource before copying from the source — if source IS this, you've just destroyed what you're trying to copy.

Three main approaches:
1. Self-assignment check: if (this == &other) return *this;
2. Copy-and-swap idiom: make a copy first, then swap
3. Copy-then-release: allocate new resource, then release old

The copy-and-swap is generally considered the best because it also provides strong exception safety. But it forces a copy even when self-assigning (minor overhead).

The self-assignment check is an optimization for the rare case of self-assignment, but it adds a branch to EVERY assignment. Since self-assignment is extremely rare, the branch is almost always mispredicted or just wasted.

Actually, the real question is: does the code work WITHOUT the self-assignment check? If copy-and-swap is used, yes — because the copy is made from other before anything is destroyed. If manual delete-then-copy is used, no — self-assignment destroys the source before copying.

For move assignment, self-move is a different beast. The standard says the object should be in a "valid but unspecified state" after self-move, but in practice, writing x = std::move(x) should not crash or corrupt. A simple self-check or the swap idiom handles it.

Let me show all three approaches and benchmark the self-assignment check overhead.
</think>

Here is a complete comparison of self-assignment safety patterns:

```cpp
#include <iostream>
#include <cstring>
#include <algorithm>
#include <utility>
#include <cassert>

// === Resource-owning class for demonstration ===
class Buffer {
    char* data_;
    std::size_t size_;

    void log(const char* msg) const {
        std::cout << "  [Buffer@" << this << " size=" << size_ << "] " << msg << "\n";
    }

public:
    explicit Buffer(const char* s)
        : data_(new char[std::strlen(s) + 1])
        , size_(std::strlen(s))
    {
        std::strcpy(data_, s);
    }

    ~Buffer() { delete[] data_; }

    Buffer(const Buffer& o)
        : data_(new char[o.size_ + 1])
        , size_(o.size_)
    {
        std::strcpy(data_, o.data_);
    }

    Buffer(Buffer&& o) noexcept : data_(o.data_), size_(o.size_) {
        o.data_ = nullptr;
        o.size_ = 0;
    }

    // ============================================================
    // APPROACH 1: NAIVE (BROKEN) — self-assignment causes UB
    // ============================================================
    // Buffer& operator=(const Buffer& o) {
    //     delete[] data_;               // Destroys our data
    //     data_ = new char[o.size_ + 1]; // o.data_ is GONE if o is *this!
    //     std::strcpy(data_, o.data_);   // UB: reading freed memory
    //     size_ = o.size_;
    //     return *this;
    // }

    // ============================================================
    // APPROACH 2: Self-assignment check
    // ============================================================
    // Buffer& operator=(const Buffer& o) {
    //     if (this == &o) return *this;  // Early return on self-assign
    //     delete[] data_;
    //     data_ = new char[o.size_ + 1];
    //     std::strcpy(data_, o.data_);
    //     size_ = o.size_;
    //     return *this;
    //     // Problem: if new[] throws, data_ is dangling (already deleted)
    //     // Not exception-safe!
    // }

    // ============================================================
    // APPROACH 3: Copy-and-swap (RECOMMENDED)
    // ============================================================
    Buffer& operator=(const Buffer& o) {
        log("copy-assign (copy-and-swap)");
        Buffer temp(o);          // Step 1: copy (may throw — *this untouched)
        swap(*this, temp);       // Step 2: swap (noexcept)
        return *this;            // Step 3: temp destructs, freeing old data
        // Self-assignment: copies self, swaps, destroys copy. Correct but wastes a copy.
        // Exception-safe: if copy throws, *this is unchanged.
    }

    // ============================================================
    // APPROACH 4: Allocate-then-release (manual, exception-safe)
    // ============================================================
    // Buffer& operator=(const Buffer& o) {
    //     char* new_data = new char[o.size_ + 1]; // Allocate first
    //     std::strcpy(new_data, o.data_);           // Copy from source
    //     delete[] data_;                            // THEN release old
    //     data_ = new_data;                          // Install new
    //     size_ = o.size_;
    //     return *this;
    //     // Self-assignment safe: copies before destroying
    //     // Exception-safe: if new[] throws, *this unchanged
    //     // More manual than copy-and-swap
    // }

    // Move assignment with self-check
    Buffer& operator=(Buffer&& o) noexcept {
        log("move-assign");
        if (this != &o) {      // Self-move check
            delete[] data_;
            data_ = o.data_;
            size_ = o.size_;
            o.data_ = nullptr;
            o.size_ = 0;
        }
        return *this;
    }

    friend void swap(Buffer& a, Buffer& b) noexcept {
        using std::swap;
        swap(a.data_, b.data_);
        swap(a.size_, b.size_);
    }

    const char* c_str() const { return data_ ? data_ : "(null)"; }
    std::size_t size() const { return size_; }

    friend std::ostream& operator<<(std::ostream& os, const Buffer& b) {
        return os << "\"" << b.c_str() << "\"";
    }
};

int main() {
    std::cout << "=== Normal assignment ===\n";
    Buffer a("Hello");
    Buffer b("World");
    std::cout << "Before: a=" << a << " b=" << b << "\n";
    a = b;
    std::cout << "After a=b: a=" << a << " b=" << b << "\n";

    std::cout << "\n=== Self-assignment (copy) ===\n";
    Buffer c("SelfTest");
    std::cout << "Before: c=" << c << "\n";
    c = c;  // Must not crash, corrupt, or leak
    std::cout << "After c=c: c=" << c << "\n";

    std::cout << "\n=== Self-move-assignment ===\n";
    Buffer d("MoveTest");
    std::cout << "Before: d=" << d << "\n";
    d = std::move(d);  // Should not crash
    std::cout << "After d=move(d): d=" << d << "\n";

    std::cout << "\n=== Chained assignment ===\n";
    Buffer e("E"), f("F"), g("G");
    e = f = g;  // Tests that operator= returns *this correctly
    std::cout << "After e=f=g: e=" << e << " f=" << f << " g=" << g << "\n";

    std::cout << R"(
=== Approach Comparison ===

Approach            | Self-safe | Exception-safe | Overhead
--------------------|-----------|----------------|------------------
Naive (delete first) | NO (UB)   | NO             | None
Self-check          | YES       | NO (if new throws) | Branch every call
Copy-and-swap       | YES       | YES (strong)    | Extra copy on self
Allocate-then-release | YES     | YES (strong)    | None significant

RECOMMENDATION: Use copy-and-swap. Self-assignment is rare (~0.001% of
assignments), so the wasted copy doesn't matter. The strong exception
guarantee and code simplicity are worth it.
)";

    return 0;
}
```

**Bottom line**: copy-and-swap is the gold standard. It handles self-assignment, provides strong exception safety, and is simple to write. The "wasted copy on self-assignment" cost is irrelevant in practice because self-assignment almost never happens.'''),

    ("cpp_deep/exception_safety_constructors", r'''What's the best approach for exception safety in constructors? Should I use two-phase initialization or RAII? Show me both patterns.''', r'''<think>
Two-phase init: constructor does minimal work, then an init() method does the real initialization that might fail. Problems: object exists in a half-initialized state, user can forget to call init(), can't use const or reference members.

RAII: constructor does everything. If it fails, it throws. The destructor of successfully constructed members is called automatically (stack unwinding). This is the preferred approach in modern C++.

The key insight: if a constructor throws, the destructor of the partially constructed object is NOT called (because the object was never fully constructed). BUT the destructors of all fully-constructed member subobjects ARE called. So if each resource is wrapped in its own RAII type, partial construction is safe.

Example of the problem: a class acquires resource A and resource B in its constructor. If acquiring B throws, A must be released. If A is a raw pointer, it leaks. If A is a unique_ptr, its destructor runs automatically.

Let me show both approaches and explain why RAII wins.
</think>

Here is a complete comparison of both approaches with exception safety analysis:

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <stdexcept>
#include <fstream>
#include <vector>

// Simulated resources that can fail
class Database {
    std::string name_;
public:
    Database(const std::string& name, bool fail = false) : name_(name) {
        if (fail) throw std::runtime_error("DB connection failed: " + name);
        std::cout << "  DB[" << name_ << "] connected\n";
    }
    ~Database() { std::cout << "  DB[" << name_ << "] disconnected\n"; }
    void query(const std::string& q) { std::cout << "  DB[" << name_ << "] query: " << q << "\n"; }
};

class CachePool {
    int size_;
public:
    CachePool(int size, bool fail = false) : size_(size) {
        if (fail) throw std::runtime_error("Cache allocation failed");
        std::cout << "  Cache[" << size_ << "] allocated\n";
    }
    ~CachePool() { std::cout << "  Cache[" << size_ << "] freed\n"; }
};

// ============================================================
// BAD: Two-Phase Initialization
// ============================================================
class BadService {
    Database* db_ = nullptr;      // Raw pointers — manual cleanup
    CachePool* cache_ = nullptr;
    bool initialized_ = false;

public:
    BadService() {
        std::cout << "  BadService: minimal construction\n";
    }

    // "Phase 2" — must be called separately, can fail
    bool init(const std::string& db_name, int cache_size) {
        try {
            db_ = new Database(db_name);
            cache_ = new CachePool(cache_size);  // If this throws, db_ leaks!
            initialized_ = true;
            return true;
        } catch (const std::exception& e) {
            // Manual cleanup — error-prone
            delete cache_; cache_ = nullptr;
            delete db_; db_ = nullptr;
            std::cerr << "  BadService::init failed: " << e.what() << "\n";
            return false;
        }
    }

    void process() {
        if (!initialized_) {
            std::cerr << "  BadService: NOT INITIALIZED! (forgot to call init?)\n";
            return;
        }
        db_->query("SELECT 1");
    }

    ~BadService() {
        delete cache_;
        delete db_;
    }

    // Problems:
    // 1. User can forget to call init()
    // 2. User can call process() before init()
    // 3. Manual cleanup is error-prone
    // 4. Can't make members const or reference
    // 5. Object exists in invalid state between construction and init()
};

// ============================================================
// GOOD: RAII — constructor does everything
// ============================================================
class GoodService {
    // RAII members: if constructor throws, their destructors run automatically
    std::unique_ptr<Database> db_;
    std::unique_ptr<CachePool> cache_;
    // Could also store by value if types support it

public:
    // Single-phase: fully initialized or not constructed at all
    GoodService(const std::string& db_name, int cache_size)
        : db_(std::make_unique<Database>(db_name))          // Step 1
        , cache_(std::make_unique<CachePool>(cache_size))   // Step 2
    {
        // If Step 2 throws:
        //   - cache_ was never constructed → nothing to clean up
        //   - db_ WAS fully constructed → its destructor runs (stack unwinding)
        //   - GoodService destructor does NOT run (object incomplete)
        //   - No leak, no corruption, no half-state
        std::cout << "  GoodService: fully initialized\n";
    }

    void process() {
        // No need to check initialized_ — if we have an object, it's valid
        db_->query("SELECT 1");
    }

    // Destructor is trivial — unique_ptrs clean up automatically
    ~GoodService() {
        std::cout << "  GoodService: destroying\n";
    }
};

// ============================================================
// ADVANCED: Multiple resources with rollback
// ============================================================
class RobustService {
    std::unique_ptr<Database> primary_db_;
    std::unique_ptr<Database> replica_db_;
    std::unique_ptr<CachePool> cache_;
    std::vector<std::string> config_;

public:
    RobustService(const std::string& primary, const std::string& replica,
                  int cache_size, std::vector<std::string> config)
        : primary_db_(std::make_unique<Database>(primary))
        , replica_db_(std::make_unique<Database>(replica))
        , cache_(std::make_unique<CachePool>(cache_size))
        , config_(std::move(config))
    {
        // If cache_ construction fails:
        //   - replica_db_ destructor runs (closes connection)
        //   - primary_db_ destructor runs (closes connection)
        //   - No leak, correct rollback order (reverse of construction)
        std::cout << "  RobustService: all " << 2 + 1 << " resources acquired\n";
    }

    // Constructor that wraps a fallible post-init step
    static RobustService create_with_validation(
            const std::string& primary, const std::string& replica,
            int cache_size, std::vector<std::string> config) {
        RobustService svc(primary, replica, cache_size, std::move(config));
        // Additional validation after construction
        // If this throws, svc's destructor runs — all resources freed
        if (svc.config_.empty()) {
            throw std::invalid_argument("Config cannot be empty");
        }
        return svc;  // NRVO
    }
};

int main() {
    std::cout << "=== Two-Phase (BAD) — success case ===\n";
    {
        BadService svc;
        svc.process();           // BUG: forgot to call init()!
        svc.init("mydb", 100);   // Now it works, but process() already failed above
        svc.process();
    }

    std::cout << "\n=== Two-Phase (BAD) — failure case ===\n";
    {
        BadService svc;
        svc.init("mydb", -1);   // Suppose this fails
        svc.process();           // Silently operates on uninitialized service
    }

    std::cout << "\n=== RAII (GOOD) — success case ===\n";
    {
        GoodService svc("mydb", 100);
        svc.process();  // Always safe — object is fully initialized
    }

    std::cout << "\n=== RAII (GOOD) — failure with automatic cleanup ===\n";
    try {
        // DB connects, then cache fails → DB automatically disconnected
        GoodService svc("mydb_ok", -1);
    } catch (const std::exception& e) {
        std::cout << "  Caught: " << e.what() << "\n";
        std::cout << "  All resources were automatically cleaned up!\n";
    }

    std::cout << "\n=== Robust multi-resource ===\n";
    try {
        auto svc = RobustService::create_with_validation(
            "primary", "replica", 256, {"setting1", "setting2"}
        );
        std::cout << "  Service created successfully\n";
    } catch (const std::exception& e) {
        std::cout << "  Caught: " << e.what() << "\n";
    }

    std::cout << R"(
=== RAII vs Two-Phase Init ===

                    | Two-Phase Init        | RAII Constructor
--------------------|-----------------------|--------------------
Object state        | Can be half-init      | Fully valid or doesn't exist
Forgot to call init | Silent bugs           | Impossible
Cleanup on failure  | Manual, error-prone   | Automatic (stack unwinding)
const/ref members   | Can't use             | Works fine
Exception safety    | Must code manually    | Built-in (strong guarantee)
API surface         | Constructor + init()  | Just constructor

VERDICT: Always prefer RAII. Two-phase init is a C/Java pattern that
fights against C++'s strength (deterministic destruction).
)";

    return 0;
}
```

**The core principle**: if your class acquires resources through RAII-wrapped members (`unique_ptr`, `string`, `vector`), then constructor failure is automatically safe — the compiler unwinds all successfully constructed members. No manual cleanup code needed.'''),

    ("cpp_deep/strict_aliasing_std_launder", r'''Explain strict aliasing rules and std::launder in C++. When is type punning actually undefined behavior?''', r'''<think>
Strict aliasing is one of the most misunderstood rules in C++. The rule says: you can only access an object through an expression of its actual type (or a compatible type like char/unsigned char/std::byte). Accessing through an unrelated type is UB, even if the memory layout matches.

Why does this rule exist? It allows the compiler to assume that pointers of different types don't alias each other. This enables aggressive optimizations: the compiler can cache values in registers, reorder loads/stores, and eliminate redundant reads.

Common violations:
1. Type punning through pointer casts: float f = 1.0f; int i = *(int*)&f; — UB
2. Union type punning: writing one member, reading another. In C, this is defined. In C++, it's UB (though compilers often support it as an extension).
3. Placement new of a different type without std::launder

Legal type punning methods:
1. memcpy — always safe, and compilers optimize it to a register move
2. std::bit_cast (C++20) — constexpr-safe, same as memcpy for trivially copyable types
3. char/unsigned char/std::byte aliasing — you can always read any object as bytes

std::launder (C++17): it "launders" a pointer, telling the compiler that the pointer refers to an object that might not be the same object that was originally at that address. Needed when:
- You've used placement new to create a new object at the same address as a destroyed one
- The new object has const or reference members that differ from the old one
- Without launder, the compiler might optimize based on the assumption that const members haven't changed

Let me create examples showing the UB, the correct alternatives, and when std::launder is needed.
</think>

Here is a comprehensive guide to strict aliasing and `std::launder`:

```cpp
#include <iostream>
#include <cstring>
#include <cstdint>
#include <bit>       // C++20: bit_cast
#include <new>       // std::launder
#include <cassert>
#include <type_traits>

// ============================================================
// STRICT ALIASING RULE:
// You may only access an object through:
//   1. Its actual type (or cv-qualified version)
//   2. A signed/unsigned variant of its type
//   3. char, unsigned char, or std::byte
//   4. An aggregate/union containing one of the above
// Anything else = Undefined Behavior.
// ============================================================

// === UB EXAMPLE 1: Type punning through pointer cast ===
void ub_pointer_cast() {
    float f = 3.14f;

    // BAD: strict aliasing violation — int* and float* cannot alias
    // int i = *reinterpret_cast<int*>(&f);
    // The compiler may optimize assuming int* and float* point to
    // different memory, reordering or eliminating the read entirely.

    // CORRECT: use memcpy (compilers optimize to single register move)
    int i;
    std::memcpy(&i, &f, sizeof(i));
    std::cout << "  float 3.14 as int bits: 0x" << std::hex << i << std::dec << "\n";

    // CORRECT (C++20): std::bit_cast
    auto i2 = std::bit_cast<int>(f);
    std::cout << "  bit_cast result:        0x" << std::hex << i2 << std::dec << "\n";

    assert(i == i2);
}

// === UB EXAMPLE 2: Union type punning ===
void ub_union_punning() {
    // In C: reading inactive union member is defined (implementation-defined repr.)
    // In C++: reading inactive union member is UNDEFINED BEHAVIOR!
    // (Though GCC and Clang support it as an extension with -fno-strict-aliasing)

    union FloatBits {
        float f;
        uint32_t u;
    };

    // BAD in standard C++:
    // FloatBits fb;
    // fb.f = 1.0f;
    // uint32_t bits = fb.u;  // UB: reading inactive member

    // CORRECT: memcpy
    float f = 1.0f;
    uint32_t bits;
    std::memcpy(&bits, &f, sizeof(bits));
    std::cout << "  float 1.0 bits: 0x" << std::hex << bits << std::dec << "\n";
}

// === CHAR ALIASING: Always legal ===
void char_aliasing() {
    double d = 2.718281828;
    auto* bytes = reinterpret_cast<const unsigned char*>(&d);

    // LEGAL: any object can be examined as bytes
    std::cout << "  double 2.718... as bytes: ";
    for (std::size_t i = 0; i < sizeof(d); ++i) {
        std::printf("%02x ", bytes[i]);
    }
    std::cout << "\n";
}

// ============================================================
// STD::LAUNDER
// Needed when placement new creates a new object and the old
// pointer might not be valid for the new object (const members,
// reference members, or different type).
// ============================================================

struct Immutable {
    const int value;  // const member!
    Immutable(int v) : value(v) {}
};

void launder_demo() {
    std::cout << "\n=== std::launder ===\n";

    alignas(Immutable) unsigned char storage[sizeof(Immutable)];

    // Construct first object
    auto* p1 = new (storage) Immutable(42);
    std::cout << "  p1->value = " << p1->value << "\n";

    // Destroy and construct a NEW object at the same address
    p1->~Immutable();
    auto* p2_raw = new (storage) Immutable(99);

    // BUG: Using p1 to access the new object is UB!
    // The compiler may have cached p1->value as 42 (it's const, can't change).
    // std::cout << p1->value << "\n";  // Might print 42 due to optimization!

    // CORRECT: use std::launder to tell the compiler "this is a new object"
    auto* p2 = std::launder(reinterpret_cast<Immutable*>(storage));
    std::cout << "  laundered->value = " << p2->value << " (should be 99)\n";

    // Or simply use p2_raw directly (placement new return value is always valid)
    std::cout << "  p2_raw->value = " << p2_raw->value << "\n";

    p2->~Immutable();
}

// === When launder is NOT needed ===
struct Mutable {
    int value;  // Non-const member
    Mutable(int v) : value(v) {}
};

void no_launder_needed() {
    std::cout << "\n=== No launder needed (no const/ref members) ===\n";

    alignas(Mutable) unsigned char storage[sizeof(Mutable)];
    auto* p1 = new (storage) Mutable(42);
    p1->~Mutable();
    auto* p2 = new (storage) Mutable(99);

    // Same type, no const/ref members → p1 and p2 are interchangeable
    // (But using the return value of placement new is still best practice)
    std::cout << "  p2->value = " << p2->value << "\n";
    p2->~Mutable();
}

// === Real-world example: implementing optional with launder ===
template <typename T>
class SimpleOptional {
    alignas(T) unsigned char storage_[sizeof(T)];
    bool engaged_ = false;

public:
    SimpleOptional() = default;

    template <typename... Args>
    void emplace(Args&&... args) {
        if (engaged_) {
            reinterpret_cast<T*>(storage_)->~T();
        }
        new (storage_) T(std::forward<Args>(args)...);
        engaged_ = true;
    }

    T& value() {
        assert(engaged_);
        // std::launder needed because T might have const/ref members
        return *std::launder(reinterpret_cast<T*>(storage_));
    }

    ~SimpleOptional() {
        if (engaged_) {
            std::launder(reinterpret_cast<T*>(storage_))->~T();
        }
    }
};

int main() {
    std::cout << "=== Strict Aliasing Violations (correct alternatives) ===\n";
    ub_pointer_cast();

    std::cout << "\n=== Union type punning ===\n";
    ub_union_punning();

    std::cout << "\n=== Char aliasing (always legal) ===\n";
    char_aliasing();

    launder_demo();
    no_launder_needed();

    std::cout << "\n=== SimpleOptional with launder ===\n";
    SimpleOptional<Immutable> opt;
    opt.emplace(42);
    std::cout << "  optional value: " << opt.value().value << "\n";
    opt.emplace(100);
    std::cout << "  after re-emplace: " << opt.value().value << "\n";

    std::cout << R"(
=== Type Punning Cheat Sheet ===

Method                 | Legal? | Constexpr? | Use when
-----------------------|--------|------------|-------------------
reinterpret_cast<T*>   | UB     | No         | NEVER for type punning
Union member read      | UB*    | No         | C only (* compilers extend)
memcpy                 | Legal  | No         | C++11/14/17
std::bit_cast          | Legal  | Yes        | C++20 (preferred)
char* aliasing         | Legal  | No         | Byte-level inspection
std::launder           | Legal  | No         | After placement new (const/ref members)

Rule: if you're casting between unrelated pointer types to read data,
you're almost certainly violating strict aliasing. Use memcpy or bit_cast.
)";

    return 0;
}
```

**The two essential rules:**
1. **Type punning**: use `memcpy` or `std::bit_cast`, never `reinterpret_cast` to read through a different type.
2. **`std::launder`**: needed after placement new when the new object has `const` or reference members, or when accessing through an old pointer to the same address.'''),

    ("cpp_deep/memory_layout_padding_alignment_cache", r'''Explain C++ memory layout: padding, alignment, and cache lines. How do I optimize struct layout for performance?''', r'''<think>
Memory layout is critical for performance. Key concepts:

1. Alignment: every type has an alignment requirement (alignof(T)). Objects must be placed at addresses that are multiples of their alignment. Common alignments: char=1, short=2, int=4, double=8, pointer=8, __m256=32.

2. Padding: the compiler inserts unused bytes between members to satisfy alignment. This can waste significant space. A struct with char, double, char might be 24 bytes instead of 10.

3. Struct size: must be a multiple of the largest alignment of any member (so arrays of structs maintain alignment).

4. Cache lines: typically 64 bytes on x86. Loading one byte pulls the entire 64-byte line into cache. Adjacent data that's accessed together should be in the same cache line.

5. False sharing: two threads accessing different members of the same cache line cause cache line ping-pong. Use alignas(64) to put thread-local data on separate cache lines.

Optimization strategies:
- Sort members by size (largest first, or smallest first grouping similar sizes)
- Use [[no_unique_address]] (C++20) for empty members
- Align hot data to cache lines
- Separate hot and cold fields
- Consider SoA (Structure of Arrays) vs AoS (Array of Structures)

Let me build a comprehensive example showing all of this.
</think>

Here is a complete analysis of C++ memory layout with optimization techniques:

```cpp
#include <iostream>
#include <cstddef>
#include <cstdint>
#include <chrono>
#include <vector>
#include <new>
#include <thread>
#include <atomic>

// Helper macro to show offset and size
#define SHOW_LAYOUT(Type) \
    std::cout << "sizeof(" #Type ") = " << sizeof(Type) \
              << ", alignof = " << alignof(Type) << "\n"

#define SHOW_MEMBER(Type, member) \
    std::cout << "  " #member ": offset=" << offsetof(Type, member) \
              << " size=" << sizeof(std::declval<Type>().member) << "\n"

// ============================================================
// PADDING WASTE: Member order matters!
// ============================================================

// BAD: wasteful ordering (6 bytes of padding)
struct BadLayout {
    char a;       // 1 byte  + 7 bytes padding (align double)
    double b;     // 8 bytes
    char c;       // 1 byte  + 3 bytes padding (align int)
    int d;        // 4 bytes
    char e;       // 1 byte  + 7 bytes padding (struct alignment = 8)
};
// Total: 32 bytes, but only 15 bytes of actual data. 53% waste!

// GOOD: sorted by descending size
struct GoodLayout {
    double b;     // 8 bytes (offset 0)
    int d;        // 4 bytes (offset 8)
    char a;       // 1 byte  (offset 12)
    char c;       // 1 byte  (offset 13)
    char e;       // 1 byte  (offset 14)
                  // 1 byte padding (struct alignment = 8)
};
// Total: 16 bytes, same data. 50% smaller!

// ============================================================
// CACHE LINE AWARENESS
// ============================================================

// Hot/cold separation: frequently accessed fields together
struct GameEntity_Bad {
    // HOT (accessed every frame)
    float pos_x, pos_y, pos_z;
    float vel_x, vel_y, vel_z;
    // COLD (rarely accessed)
    char name[64];
    uint64_t creation_timestamp;
    int32_t entity_id;
    uint16_t flags;
    // Total: ~104 bytes — hot and cold data mixed across cache lines
};

struct GameEntity_Good {
    // HOT data first — fits in one cache line (64 bytes)
    float pos_x, pos_y, pos_z;     // 12 bytes
    float vel_x, vel_y, vel_z;     // 12 bytes
    int32_t entity_id;              // 4 bytes
    uint16_t flags;                 // 2 bytes
    // 34 bytes of hot data — all in first cache line

    // COLD data after — in a separate cache line
    char name[64];                  // 64 bytes
    uint64_t creation_timestamp;    // 8 bytes
};

// ============================================================
// FALSE SHARING: threads on same cache line
// ============================================================

// BAD: two atomics on same cache line — false sharing
struct BadShared {
    std::atomic<int64_t> counter_a{0};
    std::atomic<int64_t> counter_b{0};  // Same cache line as counter_a!
};

// GOOD: each atomic on its own cache line
struct GoodShared {
    alignas(64) std::atomic<int64_t> counter_a{0};
    alignas(64) std::atomic<int64_t> counter_b{0};
};
// C++17: can also use std::hardware_destructive_interference_size

// ============================================================
// [[no_unique_address]] (C++20): eliminate empty member padding
// ============================================================

struct EmptyTag {};

struct WithPadding {
    int value;
    EmptyTag tag;   // 0 bytes of data, but takes 1 byte (unique address rule)
                    // + 3 bytes padding = 4 bytes wasted
};

struct NoPadding {
    int value;
    [[no_unique_address]] EmptyTag tag;  // Shares address with value — 0 overhead
};

// ============================================================
// PRACTICAL: AoS vs SoA
// ============================================================

// Array of Structures (AoS) — natural but cache-unfriendly for single-field access
struct Particle_AoS {
    float x, y, z;
    float vx, vy, vz;
    float mass;
    int type;
};

// Structure of Arrays (SoA) — cache-friendly for SIMD and single-field sweeps
struct Particles_SoA {
    std::vector<float> x, y, z;
    std::vector<float> vx, vy, vz;
    std::vector<float> mass;
    std::vector<int> type;

    void resize(std::size_t n) {
        x.resize(n); y.resize(n); z.resize(n);
        vx.resize(n); vy.resize(n); vz.resize(n);
        mass.resize(n); type.resize(n);
    }
};

void benchmark_layout() {
    constexpr int N = 1'000'000;
    constexpr int ITERS = 100;

    // AoS benchmark: sum all x values
    std::vector<Particle_AoS> aos(N);
    for (int i = 0; i < N; ++i) aos[i].x = static_cast<float>(i);

    auto t1 = std::chrono::high_resolution_clock::now();
    float sum_aos = 0;
    for (int iter = 0; iter < ITERS; ++iter) {
        for (int i = 0; i < N; ++i) sum_aos += aos[i].x;
    }
    auto t2 = std::chrono::high_resolution_clock::now();

    // SoA benchmark: sum all x values
    Particles_SoA soa;
    soa.resize(N);
    for (int i = 0; i < N; ++i) soa.x[i] = static_cast<float>(i);

    auto t3 = std::chrono::high_resolution_clock::now();
    float sum_soa = 0;
    for (int iter = 0; iter < ITERS; ++iter) {
        for (int i = 0; i < N; ++i) sum_soa += soa.x[i];
    }
    auto t4 = std::chrono::high_resolution_clock::now();

    auto us_aos = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
    auto us_soa = std::chrono::duration_cast<std::chrono::microseconds>(t4 - t3).count();

    std::cout << "  AoS sum: " << us_aos << " us\n";
    std::cout << "  SoA sum: " << us_soa << " us\n";
    std::cout << "  SoA speedup: " << static_cast<double>(us_aos) / us_soa << "x\n";
}

int main() {
    std::cout << "=== Padding Waste ===\n";
    SHOW_LAYOUT(BadLayout);
    SHOW_MEMBER(BadLayout, a);
    SHOW_MEMBER(BadLayout, b);
    SHOW_MEMBER(BadLayout, c);
    SHOW_MEMBER(BadLayout, d);
    SHOW_MEMBER(BadLayout, e);

    std::cout << "\n";
    SHOW_LAYOUT(GoodLayout);
    SHOW_MEMBER(GoodLayout, b);
    SHOW_MEMBER(GoodLayout, d);
    SHOW_MEMBER(GoodLayout, a);
    SHOW_MEMBER(GoodLayout, c);
    SHOW_MEMBER(GoodLayout, e);

    std::cout << "\nSaved: " << sizeof(BadLayout) - sizeof(GoodLayout)
              << " bytes per object ("
              << 100.0 * (sizeof(BadLayout) - sizeof(GoodLayout)) / sizeof(BadLayout)
              << "% reduction)\n";

    std::cout << "\n=== [[no_unique_address]] ===\n";
    SHOW_LAYOUT(WithPadding);
    SHOW_LAYOUT(NoPadding);

    std::cout << "\n=== False Sharing ===\n";
    SHOW_LAYOUT(BadShared);
    SHOW_LAYOUT(GoodShared);
    std::cout << "  BadShared: both atomics in same " << sizeof(BadShared) << "-byte block\n";
    std::cout << "  GoodShared: each atomic on its own 64-byte cache line\n";

    std::cout << "\n=== AoS vs SoA Benchmark (1M particles, sum x) ===\n";
    std::cout << "  AoS stride: " << sizeof(Particle_AoS) << " bytes (cache wastes "
              << sizeof(Particle_AoS) - sizeof(float) << " bytes per access)\n";
    std::cout << "  SoA stride: " << sizeof(float) << " bytes (perfectly packed)\n";
    benchmark_layout();

    std::cout << R"(
=== Layout Optimization Rules ===
1. Sort members by descending alignment (double, int64, int, short, char)
2. Group hot fields first (within one cache line if possible)
3. Use alignas(64) between thread-private atomics to prevent false sharing
4. Use [[no_unique_address]] for empty tag types (C++20)
5. Consider SoA for data-parallel workloads (SIMD, GPU)
6. Use #pragma pack(1) ONLY for serialization, never for performance
7. Verify with static_assert(sizeof(T) == expected)
)";

    return 0;
}
```

**Key numbers to remember:**
- Cache line: **64 bytes** (x86/ARM)
- L1 cache hit: ~1 ns, L2: ~5 ns, L3: ~15 ns, RAM: ~100 ns
- Padding waste in poorly ordered structs: commonly **30-50%**
- False sharing penalty: can make multi-threaded code **10-100x slower**'''),
]
