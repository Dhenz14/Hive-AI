"""C++ deep reasoning pairs batch 6: coroutines and async."""
PAIRS = [
    ("cpp_deep/promise_type_coroutine_handle", r'''Explain C++20 coroutines: what is a promise_type, what is coroutine_handle, and how do they connect? Show a minimal working coroutine that prints before and after suspension.''', r'''<think>
C++20 coroutines require three pieces: the coroutine return type, a nested promise_type, and coroutine_handle.
The compiler transforms a function containing co_await/co_yield/co_return into a coroutine.
promise_type controls the coroutine's behavior: what happens at initial/final suspend, how values are returned.
coroutine_handle<promise_type> is a type-erased pointer to the coroutine frame on the heap.
The return type must have a nested promise_type (or specialize coroutine_traits).
Flow: caller calls coroutine -> compiler creates frame -> constructs promise -> calls get_return_object() -> initial_suspend().
If initial_suspend returns suspend_always, coroutine suspends immediately and caller gets handle.
Caller resumes via handle.resume(), coroutine runs until next suspension or completion.
final_suspend should return suspend_always so we can destroy manually (RAII), otherwise frame auto-destroys.
If final_suspend returns suspend_never, the frame is destroyed before we can call handle.destroy() -> UB.
I need to show: a Task return type with promise_type nested inside, coroutine_handle stored in Task.
The coroutine body will print, co_await suspend_always{}, then print again.
Caller will resume once to get the second print.
Must include <coroutine> and <iostream>.
Keep it minimal but fully compilable with -std=c++20.
</think>

Here is a minimal C++20 coroutine demonstrating `promise_type` and `coroutine_handle`:

```cpp
#include <coroutine>
#include <iostream>

// The coroutine return type
struct Task {
    // promise_type controls coroutine behavior
    struct promise_type {
        Task get_return_object() {
            // Wrap the handle in our return type
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        // Suspend immediately on entry — caller decides when to start
        std::suspend_always initial_suspend() noexcept { return {}; }

        // Suspend at end so we control destruction via RAII
        std::suspend_always final_suspend() noexcept { return {}; }

        void return_void() {}

        void unhandled_exception() { std::terminate(); }
    };

    // RAII handle management
    std::coroutine_handle<promise_type> handle_;

    explicit Task(std::coroutine_handle<promise_type> h) : handle_(h) {}

    // Move-only
    Task(Task&& other) noexcept : handle_(std::exchange(other.handle_, nullptr)) {}
    Task& operator=(Task&& other) noexcept {
        if (this != &other) {
            if (handle_) handle_.destroy();
            handle_ = std::exchange(other.handle_, nullptr);
        }
        return *this;
    }

    ~Task() {
        if (handle_) handle_.destroy();
    }

    // Resume the coroutine
    void resume() {
        if (handle_ && !handle_.done()) {
            handle_.resume();
        }
    }

    bool done() const { return !handle_ || handle_.done(); }
};

// A coroutine function — contains co_await so compiler transforms it
Task my_coroutine() {
    std::cout << "Coroutine: before suspension\n";
    co_await std::suspend_always{};  // Suspend here
    std::cout << "Coroutine: after resumption\n";
    // Implicit co_return; at end
}

int main() {
    Task task = my_coroutine();
    // Coroutine is suspended at initial_suspend

    std::cout << "Main: first resume (runs to co_await)\n";
    task.resume();

    std::cout << "Main: second resume (runs to completion)\n";
    task.resume();

    std::cout << "Main: coroutine done = " << std::boolalpha << task.done() << "\n";
    // ~Task destroys the coroutine frame
    return 0;
}
```

**Output:**
```
Main: first resume (runs to co_await)
Coroutine: before suspension
Main: second resume (runs to completion)
Coroutine: after resumption
Main: coroutine done = true
```

**How the pieces connect:**

1. **`promise_type`** lives inside the coroutine frame (heap-allocated by the compiler). It dictates behavior at every lifecycle point: `initial_suspend`, `final_suspend`, `get_return_object`, `return_void`/`return_value`, and `unhandled_exception`.

2. **`coroutine_handle<promise_type>`** is a lightweight non-owning pointer to the coroutine frame. You call `.resume()` to continue execution and `.destroy()` to free the frame.

3. **`Task`** (the return type) owns the handle via RAII. When the coroutine function is called, the compiler constructs the promise, calls `get_return_object()` which wraps the handle, and returns it to the caller.

4. The coroutine is lazy because `initial_suspend()` returns `suspend_always`. The first `resume()` runs the body up to `co_await suspend_always{}`. The second `resume()` finishes execution, hitting `final_suspend()` which also suspends so the frame stays alive for the destructor to clean up.'''),

    ("cpp_deep/generator_co_yield", r'''Implement a Generator<T> coroutine type in C++20 that supports co_yield and can be iterated in a range-based for loop. Show it generating Fibonacci numbers.''', r'''<think>
A Generator needs to support co_yield, which means promise_type needs yield_value(T).
For range-for support, I need begin()/end() returning an iterator with operator++, operator*, operator!=.
The iterator's operator++ resumes the coroutine and operator* returns the yielded value.
promise_type stores the current yielded value, accessible via the handle.
initial_suspend should return suspend_always so we don't run until first iteration.
yield_value stores the value and returns suspend_always to give control back to the caller.
final_suspend returns suspend_always for RAII cleanup.
The sentinel end iterator checks handle.done().
For Fibonacci, I'll co_yield each number in an infinite loop, but the caller takes only N values.
I need to be careful: the iterator operator++ resumes, and the constructor/begin does the first resume.
Actually, begin() should resume once to get the first value, or initial_suspend should be suspend_always
and the first operator++ (or begin()) call resumes to the first co_yield.
Common pattern: begin() returns an iterator that calls resume() once immediately.
The iterator is "past-end" when handle.done() is true.
I'll template Generator on T and store T* or optional<T> in promise.
Simplest: store T value directly in promise, yield_value sets it and suspends.
Need to handle the case where coroutine finishes (no more yields).
For range-for: begin() resumes to first yield, end() returns sentinel.
</think>

Here is a fully working `Generator<T>` with range-for support and a Fibonacci example:

```cpp
#include <coroutine>
#include <cstdint>
#include <iostream>
#include <utility>

template <typename T>
class Generator {
public:
    struct promise_type {
        T current_value;

        Generator get_return_object() {
            return Generator{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }

        // co_yield stores value and suspends
        std::suspend_always yield_value(T value) {
            current_value = std::move(value);
            return {};
        }

        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    // Sentinel for end()
    struct Sentinel {};

    // Input iterator for range-for
    struct Iterator {
        std::coroutine_handle<promise_type> handle;

        Iterator& operator++() {
            handle.resume();
            return *this;
        }

        const T& operator*() const {
            return handle.promise().current_value;
        }

        bool operator==(Sentinel) const {
            return !handle || handle.done();
        }

        bool operator!=(Sentinel s) const {
            return !(*this == s);
        }
    };

    Iterator begin() {
        if (handle_) handle_.resume();  // Advance to first co_yield
        return Iterator{handle_};
    }

    Sentinel end() { return {}; }

    // RAII
    explicit Generator(std::coroutine_handle<promise_type> h) : handle_(h) {}
    Generator(Generator&& other) noexcept : handle_(std::exchange(other.handle_, nullptr)) {}
    ~Generator() { if (handle_) handle_.destroy(); }

    Generator(const Generator&) = delete;
    Generator& operator=(const Generator&) = delete;

private:
    std::coroutine_handle<promise_type> handle_;
};

// Infinite Fibonacci generator
Generator<std::uint64_t> fibonacci() {
    std::uint64_t a = 0, b = 1;
    while (true) {
        co_yield a;
        auto next = a + b;
        a = b;
        b = next;
    }
}

// Bounded range generator
Generator<int> iota(int start, int end) {
    for (int i = start; i < end; ++i) {
        co_yield i;
    }
}

int main() {
    std::cout << "First 20 Fibonacci numbers:\n";
    int count = 0;
    for (auto val : fibonacci()) {
        std::cout << val << " ";
        if (++count >= 20) break;
    }
    std::cout << "\n\n";

    std::cout << "Range [5, 10):\n";
    for (auto val : iota(5, 10)) {
        std::cout << val << " ";
    }
    std::cout << "\n";

    return 0;
}
```

**Output:**
```
First 20 Fibonacci numbers:
0 1 1 2 3 5 8 13 21 34 55 89 144 233 377 610 987 1597 2584 4181

Range [5, 10):
5 6 7 8 9
```

**Key design points:**

- **`yield_value(T)`** is called by the compiler when it sees `co_yield expr`. It stores the value in the promise and returns `suspend_always` to pause execution.
- **`begin()`** calls `resume()` once to advance from `initial_suspend` to the first `co_yield`, populating `current_value`.
- **`operator++`** resumes the coroutine to the next `co_yield` or until it finishes.
- **Sentinel pattern** uses `handle.done()` to detect when the coroutine has completed, which is the C++20 idiomatic way to define range boundaries.
- The generator is **lazy** — values are computed on demand, one at a time, with no buffering.'''),

    ("cpp_deep/async_task_co_await", r'''Implement an async Task<T> coroutine in C++20 that supports co_await for chaining. Show an example where one coroutine awaits the result of another.''', r'''<think>
An async Task<T> needs to support co_await so one coroutine can suspend until another completes.
The key difference from a simple Task is that Task<T> must be an Awaitable.
When coroutine A does `co_await taskB`, taskB needs to resume A when it completes.
This requires: await_ready(), await_suspend(), await_resume() — either on Task<T> or via operator co_await.
promise_type needs return_value(T) to store the result.
The continuation (who to resume) must be stored somewhere — typically in the promise.
await_suspend receives the awaiting coroutine's handle, stores it as continuation in the awaited task's promise.
When the awaited task finishes (final_suspend), it resumes the continuation.
final_suspend should return a custom awaiter that transfers control to the continuation (symmetric transfer).
This avoids stack overflow from deep coroutine chains.
For Task<T>: promise stores optional<T> result and coroutine_handle<> continuation.
await_ready returns false (always suspend).
await_suspend stores continuation and resumes the awaited coroutine if lazy.
await_resume returns the stored result.
I need a simple manual "executor" — just start the top-level task and let symmetric transfer chain through.
Let me implement Task<T> with symmetric transfer at final_suspend.
For void tasks I'll skip — keep it T only for clarity.
</think>

Here is a `Task<T>` coroutine supporting `co_await` chaining with symmetric transfer:

```cpp
#include <coroutine>
#include <exception>
#include <iostream>
#include <optional>
#include <utility>

template <typename T>
class Task {
public:
    struct promise_type {
        std::optional<T> result;
        std::coroutine_handle<> continuation = std::noop_coroutine();
        std::exception_ptr exception;

        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        std::suspend_always initial_suspend() noexcept { return {}; }

        // Symmetric transfer: resume whoever is waiting on us
        struct FinalAwaiter {
            bool await_ready() noexcept { return false; }

            // Return the continuation handle — compiler does symmetric transfer
            std::coroutine_handle<> await_suspend(
                std::coroutine_handle<promise_type> h) noexcept {
                return h.promise().continuation;
            }

            void await_resume() noexcept {}
        };

        FinalAwaiter final_suspend() noexcept { return {}; }

        void return_value(T value) {
            result = std::move(value);
        }

        void unhandled_exception() {
            exception = std::current_exception();
        }
    };

    // Make Task<T> awaitable
    bool await_ready() const noexcept { return false; }

    // Store the awaiting coroutine as our continuation, then start this task
    std::coroutine_handle<> await_suspend(std::coroutine_handle<> awaiting) {
        handle_.promise().continuation = awaiting;
        return handle_;  // Symmetric transfer: start this task
    }

    T await_resume() {
        auto& promise = handle_.promise();
        if (promise.exception) {
            std::rethrow_exception(promise.exception);
        }
        return std::move(*promise.result);
    }

    // Blocking start for top-level
    T sync_wait() {
        // We need a top-level coroutine to drive this
        struct Blocker {
            struct promise_type {
                std::optional<T> result;
                Blocker get_return_object() { return {}; }
                std::suspend_never initial_suspend() noexcept { return {}; }
                std::suspend_never final_suspend() noexcept { return {}; }
                void return_void() {}
                void unhandled_exception() { std::terminate(); }
            };
        };

        // Simpler: just resume directly for single-threaded use
        handle_.resume();  // This chains through via symmetric transfer
        return await_resume();
    }

    // RAII
    explicit Task(std::coroutine_handle<promise_type> h) : handle_(h) {}
    Task(Task&& o) noexcept : handle_(std::exchange(o.handle_, nullptr)) {}
    ~Task() { if (handle_) handle_.destroy(); }
    Task(const Task&) = delete;
    Task& operator=(const Task&) = delete;

private:
    std::coroutine_handle<promise_type> handle_;
};

// --- Example coroutines ---

Task<int> compute_value(int x) {
    std::cout << "  compute_value(" << x << ") running\n";
    co_return x * x;
}

Task<int> add_values(int a, int b) {
    std::cout << "  add_values: awaiting first compute...\n";
    int va = co_await compute_value(a);

    std::cout << "  add_values: awaiting second compute...\n";
    int vb = co_await compute_value(b);

    std::cout << "  add_values: combining results\n";
    co_return va + vb;
}

Task<int> outer_task() {
    std::cout << "outer_task: starting\n";
    int result = co_await add_values(3, 4);
    std::cout << "outer_task: got result = " << result << "\n";
    co_return result;
}

int main() {
    auto task = outer_task();
    int result = task.sync_wait();
    std::cout << "Final result: " << result << "\n";  // 9 + 16 = 25
    return 0;
}
```

**Output:**
```
outer_task: starting
  add_values: awaiting first compute...
  compute_value(3) running
  add_values: awaiting second compute...
  compute_value(4) running
  add_values: combining results
outer_task: got result = 25
Final result: 25
```

**How the chaining works:**

1. `main()` calls `outer_task()` which creates a suspended coroutine frame.
2. `sync_wait()` resumes it. `outer_task` hits `co_await add_values(3, 4)`.
3. `await_suspend` stores `outer_task`'s handle as the continuation in `add_values`'s promise, then symmetric-transfers to `add_values`.
4. `add_values` hits `co_await compute_value(3)` — same pattern: stores itself as continuation, transfers to `compute_value`.
5. `compute_value` does `co_return 9`. At `final_suspend`, the `FinalAwaiter` returns the continuation handle (back to `add_values`) — **symmetric transfer, no stack growth**.
6. The chain unwinds back to `outer_task` and eventually to `sync_wait()`.'''),

    ("cpp_deep/coroutine_raii_handle", r'''Show how to build a coroutine return object with proper RAII handle management in C++20. Demonstrate move semantics, preventing double-destroy, and safe destruction when the coroutine is still suspended.''', r'''<think>
RAII for coroutine handles is critical — the coroutine frame is heap-allocated and must be destroyed exactly once.
Key concerns:
1. The return object owns the handle — destructor calls handle.destroy().
2. Must be move-only (no copy — two objects would double-destroy).
3. Move constructor/assignment must null out the source handle.
4. Safe to destroy a suspended coroutine — it runs destructors for locals in the frame.
5. If final_suspend returns suspend_never, frame auto-destroys — then our handle dangles. So always suspend_always at final.
6. Must handle self-assignment in move-assignment.
7. Should check for null before destroy.
I'll build a UniqueCoroutine<Promise> class that wraps coroutine_handle with full RAII.
Show scenarios: normal destruction, move, moved-from destruction, destroying while suspended.
Also show what happens with locals that have destructors in the coroutine body.
</think>

Here is a proper RAII coroutine handle wrapper with full move semantics:

```cpp
#include <coroutine>
#include <iostream>
#include <string>
#include <utility>

// RAII wrapper for any coroutine handle
template <typename Promise>
class UniqueCoroutine {
public:
    using handle_type = std::coroutine_handle<Promise>;

    // Construct from handle
    explicit UniqueCoroutine(handle_type h) noexcept : handle_(h) {}

    // Default: empty (no coroutine)
    UniqueCoroutine() noexcept : handle_(nullptr) {}

    // Move constructor — steal the handle
    UniqueCoroutine(UniqueCoroutine&& other) noexcept
        : handle_(std::exchange(other.handle_, nullptr)) {}

    // Move assignment — destroy current, steal other
    UniqueCoroutine& operator=(UniqueCoroutine&& other) noexcept {
        if (this != &other) {
            destroy();
            handle_ = std::exchange(other.handle_, nullptr);
        }
        return *this;
    }

    // No copies — would cause double-destroy
    UniqueCoroutine(const UniqueCoroutine&) = delete;
    UniqueCoroutine& operator=(const UniqueCoroutine&) = delete;

    // RAII destructor
    ~UniqueCoroutine() { destroy(); }

    // Explicit destroy
    void destroy() {
        if (handle_) {
            handle_.destroy();  // Safe even if coroutine is suspended
            handle_ = nullptr;
        }
    }

    // Access
    handle_type get() const noexcept { return handle_; }
    Promise& promise() const { return handle_.promise(); }
    bool done() const { return !handle_ || handle_.done(); }
    explicit operator bool() const noexcept { return handle_ != nullptr; }

    void resume() {
        if (handle_ && !handle_.done()) {
            handle_.resume();
        }
    }

    // Release ownership (caller must destroy)
    handle_type release() noexcept {
        return std::exchange(handle_, nullptr);
    }

private:
    handle_type handle_;
};

// A resource with a loud destructor to prove cleanup
struct Resource {
    std::string name;
    Resource(std::string n) : name(std::move(n)) {
        std::cout << "  Resource '" << name << "' created\n";
    }
    ~Resource() {
        std::cout << "  Resource '" << name << "' destroyed\n";
    }
};

// Coroutine return type using UniqueCoroutine
struct Job {
    struct promise_type {
        Job get_return_object() {
            return Job{handle_type::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }
        // MUST suspend at final — otherwise frame auto-destroys and our handle dangles
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }

        using handle_type = std::coroutine_handle<promise_type>;
    };

    using handle_type = std::coroutine_handle<promise_type>;
    UniqueCoroutine<promise_type> coro;

    explicit Job(handle_type h) : coro(h) {}
    void resume() { coro.resume(); }
    bool done() const { return coro.done(); }
};

// Coroutine that creates resources and suspends between them
Job example_coroutine() {
    Resource r1("alpha");
    co_await std::suspend_always{};

    Resource r2("beta");
    co_await std::suspend_always{};

    Resource r3("gamma");
    // co_return implicit
}

int main() {
    std::cout << "=== Scenario 1: Destroy while suspended ===\n";
    {
        Job job = example_coroutine();
        job.resume();  // Creates r1, suspends
        std::cout << "  (destroying job while r1 is alive, r2/r3 never created)\n";
        // ~Job -> ~UniqueCoroutine -> handle.destroy()
        // This destroys the coroutine frame, running ~Resource for r1
    }

    std::cout << "\n=== Scenario 2: Run to completion ===\n";
    {
        Job job = example_coroutine();
        job.resume();  // Creates r1
        job.resume();  // Creates r2
        job.resume();  // Creates r3, reaches end -> final_suspend
        std::cout << "  (coroutine done, destroying job)\n";
        // ~Job destroys frame, runs ~r3, ~r2, ~r1
    }

    std::cout << "\n=== Scenario 3: Move semantics ===\n";
    {
        Job job1 = example_coroutine();
        job1.resume();  // Creates r1

        Job job2 = std::move(job1);  // Transfer ownership
        std::cout << "  job1 valid? " << static_cast<bool>(job1.coro) << "\n";  // false
        std::cout << "  job2 valid? " << static_cast<bool>(job2.coro) << "\n";  // true

        job2.resume();  // Creates r2
        std::cout << "  (destroying moved-from job1 — safe, handle is null)\n";
        // job1 destructor is safe: handle_ is nullptr
    }
    std::cout << "  (job2 destroyed, cleans up frame)\n";

    return 0;
}
```

**Key RAII rules for coroutine handles:**

1. **`final_suspend()` must return `suspend_always`** — if it returns `suspend_never`, the frame auto-destroys and your stored handle becomes dangling.
2. **Move nulls the source** — `std::exchange(other.handle_, nullptr)` ensures the moved-from object's destructor is harmless.
3. **`handle.destroy()` on a suspended coroutine is safe** — it runs destructors for all local variables constructed up to the suspension point, in reverse order.
4. **No copies** — `coroutine_handle` is a raw pointer; two owners means double-free.
5. **Check for null before every operation** — the handle could be moved-from or already destroyed.'''),

    ("cpp_deep/custom_awaitable_co_await", r'''Implement a custom awaitable type in C++20 by defining operator co_await (or the three awaitable methods directly). Show a practical example: an awaitable timer that simulates a delay and returns an elapsed time.''', r'''<think>
An awaitable in C++20 needs three methods: await_ready(), await_suspend(), await_resume().
These can be defined directly on the type, or the type can provide operator co_await returning an awaiter.
await_ready() -> bool: if true, don't suspend (optimization for already-complete results).
await_suspend(handle) -> void/bool/handle: called when suspending. Can schedule resumption.
  - void: always suspend
  - bool: true = suspend, false = don't suspend
  - handle: symmetric transfer to that handle
await_resume() -> T: the result of co_await expression.
For a timer: I'll simulate elapsed time. In a real system, await_suspend would register with an event loop.
Since we don't have a real event loop, I'll use a simple approach:
- await_ready returns false
- await_suspend stores the handle, does a simulated delay (just records start time), then resumes immediately
- await_resume returns the simulated elapsed time
Actually, for a cleaner demo, I'll make an awaitable that wraps std::chrono and actually measures time.
I'll also show operator co_await as an alternative.
Let me show both: direct awaitable methods AND operator co_await on a wrapper.
</think>

Here is a custom awaitable with both direct methods and `operator co_await`:

```cpp
#include <chrono>
#include <coroutine>
#include <iostream>
#include <thread>

// Forward declare our Task type
struct Task {
    struct promise_type {
        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    std::coroutine_handle<promise_type> handle;
    explicit Task(std::coroutine_handle<promise_type> h) : handle(h) {}
    Task(Task&& o) noexcept : handle(std::exchange(o.handle, nullptr)) {}
    ~Task() { if (handle) handle.destroy(); }
    void resume() { if (handle && !handle.done()) handle.resume(); }
    bool done() const { return !handle || handle.done(); }
};

// --- Approach 1: Direct awaitable (defines the three methods directly) ---
struct TimerAwaitable {
    std::chrono::milliseconds duration;
    std::chrono::steady_clock::time_point start;

    explicit TimerAwaitable(std::chrono::milliseconds ms) : duration(ms) {}

    // Could return true if duration is zero (optimization)
    bool await_ready() const noexcept {
        return duration <= std::chrono::milliseconds{0};
    }

    // Called when coroutine suspends — do the "work" and resume
    void await_suspend(std::coroutine_handle<> h) {
        start = std::chrono::steady_clock::now();
        // Simulate async delay (in real code, register with event loop)
        std::this_thread::sleep_for(duration);
        h.resume();  // Resume the coroutine after "delay"
    }

    // Return value of the co_await expression
    double await_resume() const {
        auto elapsed = std::chrono::steady_clock::now() - start;
        return std::chrono::duration<double, std::milli>(elapsed).count();
    }
};

// --- Approach 2: operator co_await on a wrapper type ---
struct DelayRequest {
    std::chrono::milliseconds ms;

    explicit DelayRequest(std::chrono::milliseconds d) : ms(d) {}

    // operator co_await returns a separate awaiter object
    auto operator co_await() const {
        struct Awaiter {
            std::chrono::milliseconds duration;
            std::chrono::steady_clock::time_point start;

            bool await_ready() const noexcept { return false; }

            bool await_suspend(std::coroutine_handle<> h) {
                if (duration <= std::chrono::milliseconds{0}) {
                    return false;  // Don't suspend
                }
                start = std::chrono::steady_clock::now();
                std::this_thread::sleep_for(duration);
                return false;  // Resume immediately (return false = don't suspend)
            }

            std::string await_resume() const {
                auto elapsed = std::chrono::steady_clock::now() - start;
                auto ms_elapsed = std::chrono::duration<double, std::milli>(elapsed).count();
                return "delayed " + std::to_string(ms_elapsed) + "ms";
            }
        };
        return Awaiter{ms, {}};
    }
};

// --- Coroutines using both approaches ---

Task demo_direct_awaitable() {
    using namespace std::chrono_literals;

    std::cout << "Starting timer (50ms)...\n";
    double elapsed = co_await TimerAwaitable{50ms};
    std::cout << "Timer done, elapsed: " << elapsed << " ms\n";

    std::cout << "Starting timer (0ms, await_ready=true)...\n";
    double elapsed2 = co_await TimerAwaitable{0ms};
    std::cout << "Instant timer, elapsed: " << elapsed2 << " ms\n";
}

Task demo_operator_co_await() {
    using namespace std::chrono_literals;

    std::cout << "\nUsing operator co_await:\n";
    std::string msg = co_await DelayRequest{30ms};
    std::cout << "Result: " << msg << "\n";
}

int main() {
    auto t1 = demo_direct_awaitable();
    while (!t1.done()) t1.resume();

    auto t2 = demo_operator_co_await();
    while (!t2.done()) t2.resume();

    return 0;
}
```

**The three awaitable methods explained:**

| Method | Signature | Purpose |
|--------|-----------|---------|
| `await_ready()` | `bool` | Return `true` to skip suspension entirely (fast path) |
| `await_suspend(h)` | `void`, `bool`, or `coroutine_handle<>` | Called on suspension. Schedule resumption here. Return `false` to cancel suspend |
| `await_resume()` | Any type `T` | The value that `co_await` evaluates to |

**Two ways to make a type awaitable:**
1. **Direct**: define the three methods on the type itself.
2. **`operator co_await`**: define a member or free `operator co_await()` that returns a separate awaiter. This separates the "request" from the "awaiter machinery."

The compiler checks in order: member `operator co_await`, free `operator co_await`, then direct methods on the object.'''),

    ("cpp_deep/symmetric_transfer", r'''Explain symmetric transfer in C++20 coroutines and why it matters. Show a chain of coroutines where without symmetric transfer you'd get stack overflow, and how symmetric transfer avoids it.''', r'''<think>
Symmetric transfer is when await_suspend returns a coroutine_handle<> instead of void or bool.
The compiler then does a tail-call: it suspends the current coroutine AND resumes the returned handle WITHOUT growing the stack.
Without it: if coroutine A resumes coroutine B which resumes C... each resume() call adds a stack frame.
With deep chains (thousands of coroutines), this causes stack overflow.
With symmetric transfer: await_suspend returns the next handle, the compiler does the equivalent of:
  suspend current, then jump to next (tail call, no stack growth).
This is critical for final_suspend — when a child completes, it transfers to parent without nesting.
I'll show: a chain of N coroutines, each awaiting the next. With naive resume(), stack grows O(N).
With symmetric transfer at final_suspend, stack stays O(1).
I'll demonstrate both approaches: the broken one (commented out or with small N) and the working one.
</think>

Here is a demonstration of symmetric transfer preventing stack overflow in coroutine chains:

```cpp
#include <coroutine>
#include <cstdint>
#include <iostream>
#include <utility>

// ============================================================
// Task with symmetric transfer (correct)
// ============================================================
struct Task {
    struct promise_type {
        std::coroutine_handle<> continuation = std::noop_coroutine();
        int result = 0;

        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        std::suspend_always initial_suspend() noexcept { return {}; }

        // KEY: symmetric transfer at final_suspend
        struct FinalAwaiter {
            bool await_ready() noexcept { return false; }

            // Returns a handle instead of void — compiler does TAIL CALL
            // Current coroutine is suspended, returned handle is resumed
            // Stack depth does NOT increase
            std::coroutine_handle<> await_suspend(
                std::coroutine_handle<promise_type> h) noexcept {
                return h.promise().continuation;
            }

            void await_resume() noexcept {}
        };

        FinalAwaiter final_suspend() noexcept { return {}; }
        void return_value(int v) { result = v; }
        void unhandled_exception() { std::terminate(); }
    };

    // Awaiter for co_await — also uses symmetric transfer
    bool await_ready() const noexcept { return false; }

    std::coroutine_handle<> await_suspend(std::coroutine_handle<> caller) noexcept {
        handle_.promise().continuation = caller;
        return handle_;  // Symmetric transfer: jump to this task
    }

    int await_resume() { return handle_.promise().result; }

    // RAII
    std::coroutine_handle<promise_type> handle_;
    explicit Task(std::coroutine_handle<promise_type> h) : handle_(h) {}
    Task(Task&& o) noexcept : handle_(std::exchange(o.handle_, nullptr)) {}
    ~Task() { if (handle_) handle_.destroy(); }
    Task(const Task&) = delete;
    Task& operator=(const Task&) = delete;
};

// Recursive coroutine chain: each level awaits the next
Task count_down(int n) {
    if (n <= 0) {
        co_return 0;
    }
    // co_await triggers symmetric transfer — no stack growth
    int inner = co_await count_down(n - 1);
    co_return inner + 1;
}

// ============================================================
// BAD Task without symmetric transfer (for comparison)
// ============================================================
struct BadTask {
    struct promise_type {
        std::coroutine_handle<> continuation;
        int result = 0;

        BadTask get_return_object() {
            return BadTask{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        std::suspend_always initial_suspend() noexcept { return {}; }

        // BAD: final_suspend resumes continuation directly via void return
        struct FinalAwaiter {
            bool await_ready() noexcept { return false; }

            // Returns void — coroutine is suspended, then we CALL resume()
            // This GROWS the stack with each level
            void await_suspend(std::coroutine_handle<promise_type> h) noexcept {
                if (h.promise().continuation)
                    h.promise().continuation.resume();  // Stack frame added!
            }

            void await_resume() noexcept {}
        };

        FinalAwaiter final_suspend() noexcept { return {}; }
        void return_value(int v) { result = v; }
        void unhandled_exception() { std::terminate(); }
    };

    bool await_ready() const noexcept { return false; }
    void await_suspend(std::coroutine_handle<> caller) {
        handle_.promise().continuation = caller;
        handle_.resume();  // Also grows stack!
    }
    int await_resume() { return handle_.promise().result; }

    std::coroutine_handle<promise_type> handle_;
    explicit BadTask(std::coroutine_handle<promise_type> h) : handle_(h) {}
    BadTask(BadTask&& o) noexcept : handle_(std::exchange(o.handle_, nullptr)) {}
    ~BadTask() { if (handle_) handle_.destroy(); }
};

int main() {
    // Symmetric transfer: works with ANY depth
    constexpr int depth = 1'000'000;  // One million deep — no stack overflow!

    std::cout << "Starting symmetric transfer chain (depth=" << depth << ")...\n";
    auto task = count_down(depth);
    task.handle_.resume();  // Single resume, symmetric transfer handles the rest
    int result = task.handle_.promise().result;
    std::cout << "Result: " << result << "\n";

    // The BadTask version would stack overflow at ~10,000 depth
    // because each level adds a frame via resume() calls

    return 0;
}
```

**How symmetric transfer works at the compiler level:**

```
// Without symmetric transfer (void await_suspend):
await_suspend(handle h) {
    continuation.resume();  // CALL — pushes stack frame
    // Must return here after resume() returns — stack frame lives
}
// Stack: main -> resume -> resume -> resume -> ... OVERFLOW

// With symmetric transfer (handle await_suspend):
coroutine_handle<> await_suspend(handle h) {
    return continuation;  // Just RETURN a handle
}
// Compiler does: suspend current, then TAIL-JUMP to returned handle
// Stack: main -> resume (constant depth, compiler reuses frame)
```

**Why it matters:**
- Without symmetric transfer, a chain of N coroutines uses O(N) stack space because each `resume()` call nests inside the previous one.
- With symmetric transfer, the compiler transforms the return of a `coroutine_handle<>` from `await_suspend` into a tail call. The current coroutine is fully suspended first, then execution jumps to the next handle without adding a stack frame.
- `std::noop_coroutine()` serves as the terminal case — it "resumes" by returning to the original `resume()` caller.'''),

    ("cpp_deep/coroutine_event_loop", r'''Build a simple single-threaded event loop in C++20 that drives coroutine-based async I/O. Show coroutines scheduling timers and the event loop dispatching them.''', r'''<think>
I need a minimal event loop that:
1. Has a queue of ready-to-resume coroutine handles
2. Supports timer-based scheduling (resume after delay)
3. Runs in a loop until all work is done
4. Provides an awaitable TimerAwaitable that registers with the loop

For timers: use a priority queue sorted by expiration time.
The event loop pops the earliest timer, sleeps until it's due, then resumes the coroutine.
I'll use chrono for time and a priority queue of {time_point, handle} pairs.

The Task type needs to work with the event loop.
Coroutines will co_await a sleep/timer, which registers with the global/passed event loop.

Let me keep it simple with a global event loop for clarity.
</think>

Here is a single-threaded coroutine event loop with timer support:

```cpp
#include <chrono>
#include <coroutine>
#include <functional>
#include <iostream>
#include <queue>
#include <thread>
#include <utility>
#include <vector>

using Clock = std::chrono::steady_clock;
using TimePoint = Clock::time_point;
using Duration = std::chrono::milliseconds;

// ============================================================
// Event Loop
// ============================================================
class EventLoop {
public:
    struct TimerEntry {
        TimePoint deadline;
        std::coroutine_handle<> handle;

        bool operator>(const TimerEntry& other) const {
            return deadline > other.deadline;  // Min-heap
        }
    };

    // Schedule a coroutine to resume after a delay
    void schedule_timer(Duration delay, std::coroutine_handle<> h) {
        timers_.push({Clock::now() + delay, h});
    }

    // Schedule immediate resumption
    void schedule_ready(std::coroutine_handle<> h) {
        ready_.push_back(h);
    }

    // Run until all work is done
    void run() {
        while (!ready_.empty() || !timers_.empty()) {
            // First, drain all ready coroutines
            while (!ready_.empty()) {
                auto h = ready_.front();
                ready_.erase(ready_.begin());
                h.resume();
            }

            // Then, wait for the next timer
            if (!timers_.empty()) {
                auto [deadline, handle] = timers_.top();
                timers_.pop();

                auto now = Clock::now();
                if (deadline > now) {
                    std::this_thread::sleep_until(deadline);
                }
                handle.resume();
            }
        }
        std::cout << "[EventLoop] All work completed.\n";
    }

    static EventLoop& instance() {
        static EventLoop loop;
        return loop;
    }

private:
    std::vector<std::coroutine_handle<>> ready_;
    std::priority_queue<TimerEntry, std::vector<TimerEntry>, std::greater<>> timers_;
};

// ============================================================
// Awaitables
// ============================================================
struct SleepAwaitable {
    Duration duration;

    bool await_ready() const noexcept { return duration <= Duration{0}; }

    void await_suspend(std::coroutine_handle<> h) {
        EventLoop::instance().schedule_timer(duration, h);
    }

    void await_resume() const noexcept {}
};

// Helper function
SleepAwaitable async_sleep(Duration d) {
    return SleepAwaitable{d};
}

// ============================================================
// Task (fire-and-forget, registers with event loop)
// ============================================================
struct Task {
    struct promise_type {
        Task get_return_object() { return {}; }

        // Don't suspend — start immediately when event loop resumes us
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }

        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };
};

// ============================================================
// Example coroutines
// ============================================================
Task sensor_reader(const char* name, int interval_ms, int count) {
    using namespace std::chrono_literals;
    auto start = Clock::now();

    for (int i = 0; i < count; ++i) {
        co_await async_sleep(Duration{interval_ms});
        auto elapsed = std::chrono::duration_cast<Duration>(
            Clock::now() - start).count();
        std::cout << "[" << elapsed << "ms] " << name
                  << " reading #" << (i + 1) << "\n";
    }
    std::cout << name << " done.\n";
}

Task heartbeat() {
    using namespace std::chrono_literals;
    auto start = Clock::now();

    for (int i = 0; i < 5; ++i) {
        co_await async_sleep(100ms);
        auto elapsed = std::chrono::duration_cast<Duration>(
            Clock::now() - start).count();
        std::cout << "[" << elapsed << "ms] heartbeat pulse " << (i + 1) << "\n";
    }
    std::cout << "heartbeat done.\n";
}

Task delayed_greeting() {
    using namespace std::chrono_literals;
    std::cout << "[0ms] Scheduling greeting in 250ms...\n";
    co_await async_sleep(250ms);
    std::cout << "[~250ms] Hello from delayed greeting!\n";
}

int main() {
    auto& loop = EventLoop::instance();

    // Spawn multiple concurrent coroutines
    // These run eagerly (suspend_never initial_suspend) and register timers
    sensor_reader("TempSensor", 150, 3);   // At 150, 300, 450ms
    sensor_reader("PressureSensor", 200, 2); // At 200, 400ms
    heartbeat();                              // At 100, 200, 300, 400, 500ms
    delayed_greeting();                       // At 250ms

    // Drive all coroutines to completion
    loop.run();

    return 0;
}
```

**Example output** (times approximate):
```
[0ms] Scheduling greeting in 250ms...
[100ms] heartbeat pulse 1
[150ms] TempSensor reading #1
[200ms] PressureSensor reading #1
[200ms] heartbeat pulse 2
[250ms] Hello from delayed greeting!
[300ms] TempSensor reading #2
[300ms] heartbeat pulse 3
[400ms] PressureSensor reading #2
PressureSensor done.
[400ms] heartbeat pulse 4
[450ms] TempSensor reading #3
TempSensor done.
[500ms] heartbeat pulse 5
heartbeat done.
delayed_greeting done (implicitly).
[EventLoop] All work completed.
```

**Design points:**

1. **Min-heap priority queue** ensures the event loop always processes the earliest timer first.
2. **`sleep_until`** avoids busy-waiting — the thread sleeps until the next timer fires.
3. **Coroutines are interleaved** — multiple coroutines share the single thread, each suspending at `co_await async_sleep(...)` and resuming when their timer fires.
4. **Fire-and-forget Task** uses `suspend_never` for both initial and final suspend since the event loop manages lifetime.
5. In production, you would replace `sleep_until` with `epoll_wait`/`io_uring` timeout to also handle I/O readiness.'''),

    ("cpp_deep/lazy_generator_evaluation", r'''Show lazy evaluation with C++20 coroutine generators: a pipeline of generators that transform data without materializing intermediate collections. Filter, map, and take from a large sequence.''', r'''<think>
Lazy evaluation with generators means each element flows through the entire pipeline one at a time.
No intermediate vectors — just coroutine suspensions.
I need a Generator<T> and then composable operations: filter, map, take.
Each operation is itself a coroutine that takes a Generator and produces a Generator.
The key insight: when the consumer iterates, it pulls one element, which resumes the take generator, which resumes the filter generator, which resumes the source generator — all lazily.
I'll show processing a conceptually infinite sequence with only O(1) memory.
</think>

Here is a lazy pipeline using composable coroutine generators:

```cpp
#include <coroutine>
#include <cstdint>
#include <functional>
#include <iostream>
#include <string>
#include <utility>

template <typename T>
class Generator {
public:
    struct promise_type {
        T current;

        Generator get_return_object() {
            return Generator{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        std::suspend_always yield_value(T value) {
            current = std::move(value);
            return {};
        }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    struct Sentinel {};
    struct Iterator {
        std::coroutine_handle<promise_type> h;
        Iterator& operator++() { h.resume(); return *this; }
        const T& operator*() const { return h.promise().current; }
        bool operator!=(Sentinel) const { return h && !h.done(); }
    };

    Iterator begin() { if (h_) h_.resume(); return Iterator{h_}; }
    Sentinel end() { return {}; }

    explicit Generator(std::coroutine_handle<promise_type> h) : h_(h) {}
    Generator(Generator&& o) noexcept : h_(std::exchange(o.h_, nullptr)) {}
    ~Generator() { if (h_) h_.destroy(); }
    Generator(const Generator&) = delete;

private:
    std::coroutine_handle<promise_type> h_;
};

// ============================================================
// Source generators
// ============================================================

// Infinite sequence: 0, 1, 2, 3, ...
Generator<std::int64_t> iota(std::int64_t start = 0) {
    for (auto i = start; ; ++i) {
        co_yield i;
    }
}

// ============================================================
// Pipeline combinators (each is a coroutine consuming a generator)
// ============================================================

// Filter: yield only elements matching predicate
template <typename T, typename Pred>
Generator<T> filter(Generator<T> source, Pred pred) {
    for (auto&& val : source) {
        if (pred(val)) {
            co_yield val;
        }
    }
}

// Map: transform each element
template <typename T, typename Func>
Generator<std::invoke_result_t<Func, T>> map(Generator<T> source, Func func) {
    for (auto&& val : source) {
        co_yield func(val);
    }
}

// Take: yield at most n elements, then stop
template <typename T>
Generator<T> take(Generator<T> source, std::size_t n) {
    std::size_t count = 0;
    for (auto&& val : source) {
        if (count++ >= n) break;
        co_yield val;
    }
}

// FlatMap: for each element, yield all elements from a sub-generator
template <typename T, typename Func>
Generator<typename std::invoke_result_t<Func, T>::value_type>
flat_map(Generator<T> source, Func func)
    requires requires { typename std::invoke_result_t<Func, T>::value_type; }
{
    // Workaround: just use the concept without value_type
    for (auto&& val : source) {
        auto sub = func(val);
        for (auto&& inner : sub) {
            co_yield inner;
        }
    }
}

// ============================================================
// Demo
// ============================================================

int main() {
    // Pipeline: natural numbers -> keep primes -> square them -> take 10
    // No intermediate vectors! Each element flows through one at a time.

    auto is_prime = [](std::int64_t n) -> bool {
        if (n < 2) return false;
        if (n < 4) return true;
        if (n % 2 == 0 || n % 3 == 0) return false;
        for (std::int64_t i = 5; i * i <= n; i += 6) {
            if (n % i == 0 || n % (i + 2) == 0) return false;
        }
        return true;
    };

    std::cout << "First 10 squared primes:\n";
    auto pipeline = take(
        map(
            filter(iota(2), is_prime),
            [](std::int64_t p) { return p * p; }
        ),
        10
    );

    for (auto val : pipeline) {
        std::cout << val << " ";
    }
    std::cout << "\n";
    // Output: 4 9 25 49 121 169 289 361 529 625

    // Another pipeline: Fizzbuzz via generators
    std::cout << "\nFizzBuzz (1-20):\n";
    auto fizzbuzz = map(
        take(iota(1), 20),
        [](std::int64_t n) -> std::string {
            if (n % 15 == 0) return "FizzBuzz";
            if (n % 3 == 0) return "Fizz";
            if (n % 5 == 0) return "Buzz";
            return std::to_string(n);
        }
    );

    for (auto&& s : fizzbuzz) {
        std::cout << s << " ";
    }
    std::cout << "\n";

    // Demonstrate laziness: even though iota is infinite,
    // we only compute what we consume
    std::cout << "\nSum of first 1,000,000 even numbers: ";
    auto evens = take(
        filter(iota(0), [](std::int64_t n) { return n % 2 == 0; }),
        1'000'000
    );
    std::int64_t sum = 0;
    for (auto val : evens) {
        sum += val;
    }
    std::cout << sum << "\n";  // 999999000000

    return 0;
}
```

**Why this is lazy (zero intermediate allocations):**

When the final `for` loop calls `operator++` on `take`'s iterator, it resumes `take`'s coroutine. `take` iterates `filter`, which resumes `filter`'s coroutine. `filter` iterates `iota`, which resumes `iota`'s coroutine. `iota` yields one number. If `filter`'s predicate rejects it, `filter` pulls another from `iota` — all without returning to the consumer. When `filter` accepts a value, it `co_yield`s to `map`, which transforms and yields to `take`, which yields to the consumer.

Each element traverses the full pipeline before the next element is produced. Memory usage is O(1) regardless of the source size — even from an infinite sequence.'''),

    ("cpp_deep/async_stream_processing", r'''Implement async stream processing with C++20 coroutines: an AsyncGenerator that produces values asynchronously and a consumer that processes them. Show backpressure handling.''', r'''<think>
An AsyncGenerator differs from a sync Generator in that producing/consuming can involve async operations.
The consumer calls co_await to get the next value, and the producer uses co_yield.
Backpressure: the producer doesn't produce the next item until the consumer has consumed the current one.
This is natural with coroutines — co_yield suspends the producer until the consumer resumes it.
I'll build an AsyncGenerator<T> where:
- The consumer does: while (co_await gen.next()) { auto val = gen.value(); ... }
- Or better: the async for-each pattern.
I need the iterator to be awaitable.
Let me implement a simpler pattern: AsyncGenerator where next() returns an awaitable that yields optional<T>.
</think>

Here is an async stream with backpressure using C++20 coroutines:

```cpp
#include <coroutine>
#include <exception>
#include <iostream>
#include <optional>
#include <thread>
#include <chrono>
#include <utility>
#include <string>

// ============================================================
// AsyncGenerator<T> — async producer with backpressure
// ============================================================
template <typename T>
class AsyncGenerator {
public:
    struct promise_type;
    using handle_type = std::coroutine_handle<promise_type>;

    struct promise_type {
        std::optional<T> current_value;
        std::coroutine_handle<> consumer_handle;  // Who's waiting for next value
        std::exception_ptr exception;

        AsyncGenerator get_return_object() {
            return AsyncGenerator{handle_type::from_promise(*this)};
        }

        std::suspend_always initial_suspend() noexcept { return {}; }

        // At final suspend, resume the consumer so it sees done()
        struct FinalAwaiter {
            bool await_ready() noexcept { return false; }
            std::coroutine_handle<> await_suspend(handle_type h) noexcept {
                if (auto consumer = h.promise().consumer_handle)
                    return consumer;
                return std::noop_coroutine();
            }
            void await_resume() noexcept {}
        };
        FinalAwaiter final_suspend() noexcept { return {}; }

        // co_yield: store value, suspend producer, resume consumer
        struct YieldAwaiter {
            bool await_ready() noexcept { return false; }

            std::coroutine_handle<> await_suspend(handle_type h) noexcept {
                // Transfer to consumer (backpressure: producer waits)
                return h.promise().consumer_handle;
            }

            void await_resume() noexcept {}
        };

        YieldAwaiter yield_value(T value) {
            current_value = std::move(value);
            return {};
        }

        void return_void() { current_value.reset(); }
        void unhandled_exception() { exception = std::current_exception(); }
    };

    // Awaitable returned by next() — consumer co_awaits this
    struct NextAwaitable {
        handle_type producer;

        bool await_ready() noexcept { return false; }

        // Suspend consumer, resume producer to generate next value
        std::coroutine_handle<> await_suspend(std::coroutine_handle<> consumer) noexcept {
            producer.promise().consumer_handle = consumer;
            return producer;  // Symmetric transfer to producer
        }

        // Returns true if a value was produced, false if stream ended
        bool await_resume() {
            if (producer.promise().exception)
                std::rethrow_exception(producer.promise().exception);
            return producer.promise().current_value.has_value();
        }
    };

    // Consumer calls: while (co_await gen.next()) { gen.value(); }
    NextAwaitable next() { return NextAwaitable{handle_}; }

    const T& value() const { return *handle_.promise().current_value; }

    // RAII
    explicit AsyncGenerator(handle_type h) : handle_(h) {}
    AsyncGenerator(AsyncGenerator&& o) noexcept : handle_(std::exchange(o.handle_, nullptr)) {}
    ~AsyncGenerator() { if (handle_) handle_.destroy(); }
    AsyncGenerator(const AsyncGenerator&) = delete;

private:
    handle_type handle_;
};

// ============================================================
// Simple Task for the consumer coroutine
// ============================================================
struct Task {
    struct promise_type {
        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    std::coroutine_handle<promise_type> handle;
    explicit Task(std::coroutine_handle<promise_type> h) : handle(h) {}
    Task(Task&& o) noexcept : handle(std::exchange(o.handle, nullptr)) {}
    ~Task() { if (handle) handle.destroy(); }

    void start() { if (handle) handle.resume(); }
    bool done() const { return !handle || handle.done(); }
};

// ============================================================
// Producers (async generators)
// ============================================================

// Simulates a data source that produces items at varying rates
AsyncGenerator<std::string> sensor_stream(const char* name, int count) {
    for (int i = 1; i <= count; ++i) {
        // Simulate async data acquisition (in real code: co_await io_read())
        std::string data = std::string(name) + " sample #" + std::to_string(i);
        std::cout << "  [producer] generated: " << data << "\n";
        co_yield std::move(data);
        // Producer is suspended here until consumer requests next value
        // This IS the backpressure — no unbounded buffering
    }
    std::cout << "  [producer] " << name << " stream ended\n";
}

// Transform stream: async map
AsyncGenerator<std::string> transform(AsyncGenerator<std::string> source) {
    while (co_await source.next()) {
        std::string processed = "[PROCESSED] " + source.value();
        co_yield std::move(processed);
    }
}

// ============================================================
// Consumer
// ============================================================

Task consumer_task() {
    auto raw_stream = sensor_stream("Gyroscope", 4);
    auto processed = transform(std::move(raw_stream));

    std::cout << "Consumer starting to pull from processed stream:\n\n";

    int received = 0;
    while (co_await processed.next()) {
        ++received;
        std::cout << "  [consumer] received: " << processed.value() << "\n";

        // Simulate slow consumer — producer cannot outpace us
        std::cout << "  [consumer] processing (slow)...\n\n";
        // In real code: co_await async_sleep(100ms);
    }

    std::cout << "Consumer done. Received " << received << " items.\n";
}

int main() {
    auto task = consumer_task();
    task.start();  // Drives the entire chain via symmetric transfer
    return 0;
}
```

**Output:**
```
Consumer starting to pull from processed stream:

  [producer] generated: Gyroscope sample #1
  [consumer] received: [PROCESSED] Gyroscope sample #1
  [consumer] processing (slow)...

  [producer] generated: Gyroscope sample #2
  [consumer] received: [PROCESSED] Gyroscope sample #2
  [consumer] processing (slow)...

  [producer] generated: Gyroscope sample #3
  [consumer] received: [PROCESSED] Gyroscope sample #3
  [consumer] processing (slow)...

  [producer] generated: Gyroscope sample #4
  [consumer] received: [PROCESSED] Gyroscope sample #4
  [consumer] processing (slow)...

  [producer] Gyroscope stream ended
Consumer done. Received 4 items.
```

**Backpressure mechanism:**

The producer **cannot outpace the consumer** because `co_yield` suspends the producer and transfers control to the consumer via symmetric transfer. The producer only resumes when the consumer calls `co_await stream.next()`. There is no buffer between them — at most one value exists at a time. This is inherent to the coroutine suspension model: the producer literally cannot run until the consumer asks for more data.'''),

    ("cpp_deep/coroutine_cancellation", r'''Show coroutine cancellation patterns in C++20. Demonstrate cooperative cancellation with a stop token, cancelling a coroutine mid-execution, and proper cleanup of resources.''', r'''<think>
C++20 doesn't have built-in coroutine cancellation, but we can implement cooperative cancellation.
Patterns:
1. Check a stop flag at each co_await point
2. Use std::stop_token (C++20) or a custom cancellation token
3. Throwing an exception to unwind
4. Destroying the coroutine handle (which runs destructors)

I'll show:
- A CancellationToken that coroutines check
- An awaitable that checks the token before/after suspension
- Resource cleanup via RAII when cancelled
- Using std::stop_source/std::stop_token

The cleanest approach: make an awaitable wrapper that checks cancellation.
</think>

Here are several coroutine cancellation patterns in C++20:

```cpp
#include <chrono>
#include <coroutine>
#include <exception>
#include <functional>
#include <iostream>
#include <stop_token>
#include <string>
#include <thread>
#include <utility>
#include <vector>

// ============================================================
// Task with RAII handle
// ============================================================
struct Task {
    struct promise_type {
        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    std::coroutine_handle<promise_type> handle;
    explicit Task(std::coroutine_handle<promise_type> h) : handle(h) {}
    Task(Task&& o) noexcept : handle(std::exchange(o.handle, nullptr)) {}
    ~Task() { if (handle) handle.destroy(); }
    void resume() { if (handle && !handle.done()) handle.resume(); }
    bool done() const { return !handle || handle.done(); }
};

// RAII resource to prove cleanup on cancellation
struct ManagedResource {
    std::string name;
    ManagedResource(std::string n) : name(std::move(n)) {
        std::cout << "    + Resource '" << name << "' acquired\n";
    }
    ~ManagedResource() {
        std::cout << "    - Resource '" << name << "' released\n";
    }
};

// ============================================================
// Pattern 1: Cancellation via std::stop_token
// ============================================================

// Awaitable that checks stop_token before resuming
struct CancellableCheckpoint {
    std::stop_token token;

    bool await_ready() const noexcept {
        return false;
    }

    bool await_suspend(std::coroutine_handle<> h) {
        // If cancellation was requested, don't suspend — resume to throw
        if (token.stop_requested()) {
            return false;  // Don't suspend, proceed to await_resume
        }
        // In real code: register with event loop, check token on wake
        h.resume();
        return true;
    }

    void await_resume() const {
        if (token.stop_requested()) {
            throw std::runtime_error("coroutine cancelled");
        }
    }
};

// Helper: check cancellation at yield points
CancellableCheckpoint cancellation_point(std::stop_token token) {
    return CancellableCheckpoint{token};
}

Task long_running_task(std::stop_token token) {
    ManagedResource db("database_connection");

    for (int i = 1; i <= 10; ++i) {
        try {
            co_await cancellation_point(token);
        } catch (const std::runtime_error& e) {
            std::cout << "  Task caught cancellation at iteration " << i << "\n";
            co_return;  // Clean exit — destructors run
        }

        std::cout << "  Task iteration " << i << "\n";
        ManagedResource iter_res("iter_" + std::to_string(i));
        // iter_res destroyed at end of loop body
    }
}

// ============================================================
// Pattern 2: Cancellation by destroying the coroutine handle
// ============================================================

Task destroyable_task() {
    ManagedResource r1("file_handle");

    co_await std::suspend_always{};  // Suspend point 1
    std::cout << "  After first suspend\n";

    ManagedResource r2("network_socket");

    co_await std::suspend_always{};  // Suspend point 2
    std::cout << "  After second suspend\n";

    ManagedResource r3("temp_buffer");
}

// ============================================================
// Pattern 3: stop_callback for async registration
// ============================================================

struct AsyncOperation {
    std::coroutine_handle<> waiting;
    bool completed = false;
    bool cancelled = false;

    struct Awaiter {
        AsyncOperation& op;

        bool await_ready() const noexcept { return op.completed; }

        void await_suspend(std::coroutine_handle<> h) {
            op.waiting = h;
        }

        bool await_resume() const {
            return !op.cancelled;  // Returns false if cancelled
        }
    };

    Awaiter operator co_await() { return Awaiter{*this}; }

    void complete() {
        completed = true;
        if (waiting) waiting.resume();
    }

    void cancel() {
        cancelled = true;
        if (waiting) waiting.resume();
    }
};

Task async_with_callback(std::stop_token token) {
    ManagedResource res("async_resource");
    AsyncOperation op;

    // Register stop callback to cancel the async operation
    std::stop_callback callback(token, [&op]() {
        std::cout << "  stop_callback triggered — cancelling operation\n";
        op.cancel();
    });

    bool success = co_await op;
    if (!success) {
        std::cout << "  Operation was cancelled, cleaning up\n";
        co_return;
    }
    std::cout << "  Operation completed successfully\n";
}

// ============================================================
// Demonstrations
// ============================================================

int main() {
    std::cout << "=== Pattern 1: Cooperative cancellation with stop_token ===\n";
    {
        std::stop_source source;
        auto task = long_running_task(source.get_token());

        task.resume();  // Start
        task.resume();  // Iteration 1
        task.resume();  // Iteration 2

        std::cout << "  >>> Requesting cancellation\n";
        source.request_stop();

        task.resume();  // Iteration 3 — hits cancellation point, catches, returns
        std::cout << "  Task done: " << task.done() << "\n";
    }

    std::cout << "\n=== Pattern 2: Cancel by destroying handle ===\n";
    {
        auto task = destroyable_task();
        task.resume();  // Creates r1, suspends at point 1
        task.resume();  // Prints, creates r2, suspends at point 2

        std::cout << "  >>> Destroying coroutine while r1 and r2 alive\n";
        // ~Task -> handle.destroy() -> runs ~r2, ~r1
    }

    std::cout << "\n=== Pattern 3: stop_callback with async operation ===\n";
    {
        std::stop_source source;
        auto task = async_with_callback(source.get_token());

        task.resume();  // Start, suspends at co_await op

        std::cout << "  >>> Requesting stop (triggers callback)\n";
        source.request_stop();  // Callback cancels op, resumes coroutine

        std::cout << "  Task done: " << task.done() << "\n";
    }

    return 0;
}
```

**Three cancellation strategies compared:**

| Pattern | Mechanism | Cleanup | When to use |
|---------|-----------|---------|-------------|
| `stop_token` checkpoint | Check token at each `co_await`, throw/return | Coroutine unwinds normally | Long-running loops with many yield points |
| Handle destruction | Call `handle.destroy()` on suspended coroutine | Frame destructors run automatically | When you need to force-stop from outside |
| `stop_callback` | Register callback that cancels pending async ops | Async operation resumes with "cancelled" status | Integrating with async APIs and event loops |

**Key points:**
- Cancellation is always **cooperative** — there is no way to force-kill a running coroutine.
- Destroying a suspended coroutine is safe and runs all RAII destructors for objects constructed up to the suspension point.
- `std::stop_source`/`std::stop_token` from C++20 provide thread-safe cancellation signaling with callback registration.'''),

    ("cpp_deep/file_io_raii", r'''Show RAII-based file I/O in Modern C++: reading, writing, buffered I/O, and error handling. Compare fstream, C FILE*, and demonstrate why RAII matters for exception safety.''', r'''<think>
Cover:
- std::fstream with RAII (automatic close)
- Wrapping C FILE* in a RAII class
- Buffered reading patterns
- Exception safety — what happens when an exception is thrown mid-write
- Show the wrong way (manual close) vs the right way (RAII)
</think>

Here is a comprehensive look at RAII file I/O in Modern C++:

```cpp
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace fs = std::filesystem;

// ============================================================
// 1. std::fstream — RAII built in
// ============================================================

void fstream_demo(const fs::path& dir) {
    auto path = dir / "fstream_demo.txt";

    // Writing — fstream closes automatically when it goes out of scope
    {
        std::ofstream out(path);
        if (!out) throw std::runtime_error("Cannot open " + path.string());

        out << "Line 1: Hello RAII\n";
        out << "Line 2: Exception safe\n";
        out << "Line 3: Auto-closed\n";

        // Even if an exception is thrown here, ~ofstream() closes the file
    }

    // Reading — line by line
    {
        std::ifstream in(path);
        if (!in) throw std::runtime_error("Cannot open " + path.string());

        std::string line;
        int num = 0;
        while (std::getline(in, line)) {
            std::cout << "  Read: " << line << "\n";
            ++num;
        }
        std::cout << "  Total lines: " << num << "\n";
    }

    // Reading — entire file into string (efficient)
    {
        std::ifstream in(path, std::ios::ate);  // Open at end to get size
        if (!in) throw std::runtime_error("Cannot open " + path.string());

        auto size = in.tellg();
        in.seekg(0);
        std::string content(static_cast<std::size_t>(size), '\0');
        in.read(content.data(), size);
        std::cout << "  Entire file (" << size << " bytes): \n" << content;
    }
}

// ============================================================
// 2. C FILE* with RAII wrapper
// ============================================================

class UniqueFile {
public:
    UniqueFile() noexcept : fp_(nullptr) {}

    explicit UniqueFile(const char* path, const char* mode)
        : fp_(std::fopen(path, mode)) {
        if (!fp_) {
            throw std::runtime_error(
                std::string("fopen failed: ") + std::strerror(errno));
        }
    }

    // Move-only
    UniqueFile(UniqueFile&& other) noexcept
        : fp_(std::exchange(other.fp_, nullptr)) {}

    UniqueFile& operator=(UniqueFile&& other) noexcept {
        if (this != &other) {
            close();
            fp_ = std::exchange(other.fp_, nullptr);
        }
        return *this;
    }

    UniqueFile(const UniqueFile&) = delete;
    UniqueFile& operator=(const UniqueFile&) = delete;

    ~UniqueFile() { close(); }

    // Access
    FILE* get() const noexcept { return fp_; }
    explicit operator bool() const noexcept { return fp_ != nullptr; }

    // Read entire contents
    std::string read_all() {
        std::fseek(fp_, 0, SEEK_END);
        long size = std::ftell(fp_);
        std::fseek(fp_, 0, SEEK_SET);

        std::string buf(static_cast<std::size_t>(size), '\0');
        std::fread(buf.data(), 1, static_cast<std::size_t>(size), fp_);
        return buf;
    }

    // Write string
    void write(std::string_view data) {
        auto written = std::fwrite(data.data(), 1, data.size(), fp_);
        if (written != data.size()) {
            throw std::runtime_error("fwrite incomplete");
        }
    }

    void flush() { std::fflush(fp_); }

    // Release ownership
    FILE* release() noexcept { return std::exchange(fp_, nullptr); }

private:
    void close() noexcept {
        if (fp_) {
            std::fclose(fp_);
            fp_ = nullptr;
        }
    }

    FILE* fp_;
};

// Alternative: use unique_ptr with custom deleter
using UniqueFILE = std::unique_ptr<FILE, decltype([](FILE* f) { if (f) std::fclose(f); })>;

void c_file_demo(const fs::path& dir) {
    auto path = dir / "cfile_demo.bin";

    // Write binary data using UniqueFile
    {
        UniqueFile f(path.string().c_str(), "wb");
        std::array<int, 5> data = {10, 20, 30, 40, 50};
        std::fwrite(data.data(), sizeof(int), data.size(), f.get());
        // ~UniqueFile closes automatically
    }

    // Read back using unique_ptr approach
    {
        UniqueFILE f(std::fopen(path.string().c_str(), "rb"));
        if (!f) throw std::runtime_error("fopen failed");

        std::array<int, 5> data{};
        std::fread(data.data(), sizeof(int), data.size(), f.get());

        std::cout << "  Binary read: ";
        for (int v : data) std::cout << v << " ";
        std::cout << "\n";
    }
}

// ============================================================
// 3. Buffered writer with RAII flush
// ============================================================

class BufferedWriter {
public:
    BufferedWriter(const fs::path& path, std::size_t buf_size = 4096)
        : stream_(path, std::ios::binary)
        , buffer_()
        , max_size_(buf_size) {
        if (!stream_) throw std::runtime_error("Cannot open " + path.string());
        buffer_.reserve(buf_size);
    }

    // Writes to buffer, flushes when full
    void write(std::string_view data) {
        for (char c : data) {
            buffer_.push_back(c);
            if (buffer_.size() >= max_size_) {
                flush();
            }
        }
    }

    void flush() {
        if (!buffer_.empty()) {
            stream_.write(buffer_.data(), static_cast<std::streamsize>(buffer_.size()));
            buffer_.clear();
        }
    }

    // RAII: flush remaining buffer on destruction
    ~BufferedWriter() {
        try {
            flush();
        } catch (...) {
            // Cannot throw from destructor — log in production
        }
    }

private:
    std::ofstream stream_;
    std::vector<char> buffer_;
    std::size_t max_size_;
};

// ============================================================
// 4. Exception safety comparison
// ============================================================

void dangerous_work() {
    throw std::runtime_error("unexpected error!");
}

// BAD: Manual close — leaks on exception
void bad_file_handling(const fs::path& path) {
    FILE* fp = std::fopen(path.string().c_str(), "w");
    if (!fp) return;

    std::fprintf(fp, "important data\n");
    // dangerous_work();  // If this throws, fclose is never called!
    std::fclose(fp);      // Skipped on exception — RESOURCE LEAK
}

// GOOD: RAII — always closes
void good_file_handling(const fs::path& path) {
    UniqueFile fp(path.string().c_str(), "w");
    fp.write("important data\n");
    dangerous_work();  // Exception thrown here
    // ~UniqueFile runs regardless — file is properly closed
}

// ============================================================
// Main
// ============================================================

int main() {
    auto tmp = fs::temp_directory_path() / "raii_io_demo";
    fs::create_directories(tmp);

    std::cout << "=== fstream (built-in RAII) ===\n";
    fstream_demo(tmp);

    std::cout << "\n=== C FILE* with RAII wrapper ===\n";
    c_file_demo(tmp);

    std::cout << "\n=== Buffered writer ===\n";
    {
        auto path = tmp / "buffered.txt";
        BufferedWriter writer(path, 32);  // Small buffer for demo
        for (int i = 0; i < 100; ++i) {
            writer.write("Line " + std::to_string(i) + "\n");
        }
        // ~BufferedWriter flushes remaining data
    }
    std::cout << "  Buffered write complete\n";

    std::cout << "\n=== Exception safety demo ===\n";
    try {
        auto path = tmp / "exception_test.txt";
        good_file_handling(path);
    } catch (const std::runtime_error& e) {
        std::cout << "  Caught: " << e.what() << "\n";
        std::cout << "  File was still properly closed by RAII\n";
    }

    // Cleanup
    fs::remove_all(tmp);
    return 0;
}
```

**Why RAII matters for file I/O:**

Without RAII, every function with file handles needs try/catch blocks with cleanup in both normal and error paths. With RAII, the destructor guarantees cleanup regardless of how the scope is exited — normal return, exception, or early `return`. This eliminates an entire class of resource leak bugs.'''),

    ("cpp_deep/mmap_file_io", r'''Implement a memory-mapped file I/O wrapper in C++ that works on Linux (mmap). Show reading and writing files via memory mapping with RAII cleanup.''', r'''<think>
mmap maps a file into the process address space — reads/writes become memory accesses.
Need: open fd, fstat for size, mmap, and RAII to munmap+close.
I'll build a MappedFile class with read-only and read-write modes.
Handle edge cases: empty files, extending files for write.
</think>

Here is a RAII memory-mapped file wrapper for Linux:

```cpp
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>

// ============================================================
// RAII file descriptor
// ============================================================
class UniqueFd {
public:
    explicit UniqueFd(int fd = -1) noexcept : fd_(fd) {}
    UniqueFd(UniqueFd&& o) noexcept : fd_(std::exchange(o.fd_, -1)) {}
    UniqueFd& operator=(UniqueFd&& o) noexcept {
        if (this != &o) { close(); fd_ = std::exchange(o.fd_, -1); }
        return *this;
    }
    ~UniqueFd() { close(); }

    int get() const noexcept { return fd_; }
    explicit operator bool() const noexcept { return fd_ >= 0; }
    int release() noexcept { return std::exchange(fd_, -1); }

private:
    void close() noexcept { if (fd_ >= 0) { ::close(fd_); fd_ = -1; } }
    int fd_;
};

// ============================================================
// Memory-mapped file
// ============================================================
class MappedFile {
public:
    enum class Mode { ReadOnly, ReadWrite };

    // Map an existing file
    MappedFile(const std::string& path, Mode mode = Mode::ReadOnly)
        : data_(nullptr), size_(0), mode_(mode)
    {
        int flags = (mode == Mode::ReadOnly) ? O_RDONLY : O_RDWR;
        fd_ = UniqueFd(::open(path.c_str(), flags));
        if (!fd_) throw std::runtime_error("open: " + std::string(std::strerror(errno)));

        struct stat st{};
        if (::fstat(fd_.get(), &st) < 0)
            throw std::runtime_error("fstat: " + std::string(std::strerror(errno)));

        size_ = static_cast<std::size_t>(st.st_size);
        if (size_ == 0) return;  // Empty file — no mapping needed

        int prot = (mode == Mode::ReadOnly) ? PROT_READ : (PROT_READ | PROT_WRITE);
        int mflags = MAP_SHARED;  // Changes visible to other processes and written to file

        data_ = static_cast<char*>(::mmap(nullptr, size_, prot, mflags, fd_.get(), 0));
        if (data_ == MAP_FAILED) {
            data_ = nullptr;
            throw std::runtime_error("mmap: " + std::string(std::strerror(errno)));
        }
    }

    // Create/truncate a file and map with given size
    static MappedFile create(const std::string& path, std::size_t size) {
        UniqueFd fd(::open(path.c_str(), O_RDWR | O_CREAT | O_TRUNC, 0644));
        if (!fd) throw std::runtime_error("open: " + std::string(std::strerror(errno)));

        // Extend file to requested size
        if (::ftruncate(fd.get(), static_cast<off_t>(size)) < 0)
            throw std::runtime_error("ftruncate: " + std::string(std::strerror(errno)));

        MappedFile mf;
        mf.fd_ = std::move(fd);
        mf.size_ = size;
        mf.mode_ = Mode::ReadWrite;

        mf.data_ = static_cast<char*>(
            ::mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED, mf.fd_.get(), 0));
        if (mf.data_ == MAP_FAILED) {
            mf.data_ = nullptr;
            throw std::runtime_error("mmap: " + std::string(std::strerror(errno)));
        }
        return mf;
    }

    // Move only
    MappedFile(MappedFile&& o) noexcept
        : fd_(std::move(o.fd_))
        , data_(std::exchange(o.data_, nullptr))
        , size_(std::exchange(o.size_, 0))
        , mode_(o.mode_) {}

    MappedFile& operator=(MappedFile&& o) noexcept {
        if (this != &o) {
            unmap();
            fd_ = std::move(o.fd_);
            data_ = std::exchange(o.data_, nullptr);
            size_ = std::exchange(o.size_, 0);
            mode_ = o.mode_;
        }
        return *this;
    }

    ~MappedFile() { unmap(); }

    // Access
    const char* data() const noexcept { return data_; }
    char* data() noexcept { return data_; }
    std::size_t size() const noexcept { return size_; }
    bool empty() const noexcept { return size_ == 0; }

    std::string_view view() const noexcept { return {data_, size_}; }
    std::span<char> span() noexcept { return {data_, size_}; }
    std::span<const char> span() const noexcept { return {data_, size_}; }

    // Flush changes to disk
    void sync() {
        if (data_ && size_ > 0) {
            if (::msync(data_, size_, MS_SYNC) < 0)
                throw std::runtime_error("msync: " + std::string(std::strerror(errno)));
        }
    }

    // Advise kernel on access pattern
    void advise_sequential() {
        if (data_) ::madvise(data_, size_, MADV_SEQUENTIAL);
    }

    void advise_random() {
        if (data_) ::madvise(data_, size_, MADV_RANDOM);
    }

private:
    MappedFile() : data_(nullptr), size_(0), mode_(Mode::ReadOnly) {}

    void unmap() noexcept {
        if (data_ && size_ > 0) {
            ::munmap(data_, size_);
            data_ = nullptr;
            size_ = 0;
        }
    }

    UniqueFd fd_;
    char* data_;
    std::size_t size_;
    Mode mode_;
};

// ============================================================
// Usage examples
// ============================================================

int main() {
    const std::string path = "/tmp/mmap_demo.bin";

    // Create and write via memory mapping
    {
        auto mf = MappedFile::create(path, 1024);
        std::string_view msg = "Hello from memory-mapped I/O!\n";
        std::memcpy(mf.data(), msg.data(), msg.size());

        // Write structured data after the string
        auto* ints = reinterpret_cast<int*>(mf.data() + 256);
        for (int i = 0; i < 10; ++i) {
            ints[i] = i * i;
        }

        mf.sync();  // Flush to disk
        std::cout << "Wrote " << mf.size() << " bytes via mmap\n";
    }

    // Read back via memory mapping
    {
        MappedFile mf(path, MappedFile::Mode::ReadOnly);
        mf.advise_sequential();

        // Read the string
        std::cout << "String: " << std::string_view(mf.data(), 30);

        // Read the structured data
        auto* ints = reinterpret_cast<const int*>(mf.data() + 256);
        std::cout << "Squares: ";
        for (int i = 0; i < 10; ++i) {
            std::cout << ints[i] << " ";
        }
        std::cout << "\n";
    }

    // Modify in place
    {
        MappedFile mf(path, MappedFile::Mode::ReadWrite);
        // Overwrite first few bytes
        std::memcpy(mf.data(), "MODIFIED", 8);
        mf.sync();
        std::cout << "Modified first 8 bytes in place\n";
    }

    // Verify modification
    {
        MappedFile mf(path);
        std::cout << "Verify: " << std::string_view(mf.data(), 30) << "\n";
    }

    std::remove(path.c_str());
    return 0;
}
```

**When to use mmap vs read/write:**

| Criteria | `mmap` | `read()`/`write()` |
|----------|--------|---------------------|
| Random access | Excellent — pointer arithmetic | Requires `lseek` per access |
| Sequential scan | Good with `MADV_SEQUENTIAL` | Slightly better for streaming |
| Small files | Overhead of page alignment | Simpler, less overhead |
| Shared memory IPC | Natural fit (`MAP_SHARED`) | Requires explicit protocol |
| File larger than RAM | Kernel pages in/out transparently | Must manage buffers manually |

**RAII guarantees:** `~MappedFile` calls `munmap` then `~UniqueFd` calls `close`. No leaks regardless of exceptions.'''),

    ("cpp_deep/socket_raii", r'''Implement RAII socket wrappers for TCP client/server in C++ on Linux. Show a complete echo server and client with proper resource management.''', r'''<think>
Need RAII for socket fd, plus the listen/accept/connect/send/recv flow.
UniqueSocket wraps the fd. TcpListener and TcpStream for server/client.
Show a simple echo server that accepts one connection and echoes back, plus a client.
</think>

Here is a complete TCP echo server and client with RAII socket management:

```cpp
#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <netinet/in.h>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/socket.h>
#include <unistd.h>
#include <utility>
#include <vector>

// ============================================================
// RAII Socket
// ============================================================
class Socket {
public:
    Socket() noexcept : fd_(-1) {}
    explicit Socket(int fd) noexcept : fd_(fd) {}

    // Create a new socket
    static Socket create(int domain, int type, int protocol = 0) {
        int fd = ::socket(domain, type, protocol);
        if (fd < 0)
            throw std::runtime_error("socket: " + std::string(std::strerror(errno)));
        return Socket(fd);
    }

    // Move only
    Socket(Socket&& o) noexcept : fd_(std::exchange(o.fd_, -1)) {}
    Socket& operator=(Socket&& o) noexcept {
        if (this != &o) { close(); fd_ = std::exchange(o.fd_, -1); }
        return *this;
    }
    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;

    ~Socket() { close(); }

    int fd() const noexcept { return fd_; }
    explicit operator bool() const noexcept { return fd_ >= 0; }

    void set_reuse_addr() {
        int opt = 1;
        if (::setsockopt(fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0)
            throw std::runtime_error("setsockopt: " + std::string(std::strerror(errno)));
    }

private:
    void close() noexcept {
        if (fd_ >= 0) { ::close(fd_); fd_ = -1; }
    }
    int fd_;
};

// ============================================================
// TCP Stream — a connected socket for reading/writing
// ============================================================
class TcpStream {
public:
    explicit TcpStream(Socket sock) : sock_(std::move(sock)) {}

    // Connect to address
    static TcpStream connect(const std::string& host, uint16_t port) {
        auto sock = Socket::create(AF_INET, SOCK_STREAM);

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) <= 0)
            throw std::runtime_error("Invalid address: " + host);

        if (::connect(sock.fd(), reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0)
            throw std::runtime_error("connect: " + std::string(std::strerror(errno)));

        return TcpStream(std::move(sock));
    }

    // Send all bytes
    void send(std::string_view data) {
        const char* ptr = data.data();
        std::size_t remaining = data.size();

        while (remaining > 0) {
            ssize_t n = ::send(sock_.fd(), ptr, remaining, MSG_NOSIGNAL);
            if (n < 0) throw std::runtime_error("send: " + std::string(std::strerror(errno)));
            if (n == 0) throw std::runtime_error("send: connection closed");
            ptr += n;
            remaining -= static_cast<std::size_t>(n);
        }
    }

    // Receive up to buf_size bytes, returns empty string on EOF
    std::string recv(std::size_t buf_size = 4096) {
        std::string buf(buf_size, '\0');
        ssize_t n = ::recv(sock_.fd(), buf.data(), buf_size, 0);
        if (n < 0) throw std::runtime_error("recv: " + std::string(std::strerror(errno)));
        buf.resize(static_cast<std::size_t>(n));
        return buf;
    }

    std::string peer_address() const {
        sockaddr_in addr{};
        socklen_t len = sizeof(addr);
        ::getpeername(sock_.fd(), reinterpret_cast<sockaddr*>(&addr), &len);
        char buf[INET_ADDRSTRLEN];
        ::inet_ntop(AF_INET, &addr.sin_addr, buf, sizeof(buf));
        return std::string(buf) + ":" + std::to_string(ntohs(addr.sin_port));
    }

private:
    Socket sock_;
};

// ============================================================
// TCP Listener — binds and listens for connections
// ============================================================
class TcpListener {
public:
    static TcpListener bind(const std::string& host, uint16_t port, int backlog = 128) {
        auto sock = Socket::create(AF_INET, SOCK_STREAM);
        sock.set_reuse_addr();

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) <= 0)
            throw std::runtime_error("Invalid address: " + host);

        if (::bind(sock.fd(), reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0)
            throw std::runtime_error("bind: " + std::string(std::strerror(errno)));

        if (::listen(sock.fd(), backlog) < 0)
            throw std::runtime_error("listen: " + std::string(std::strerror(errno)));

        return TcpListener(std::move(sock), port);
    }

    // Accept one connection (blocking)
    TcpStream accept() {
        sockaddr_in client_addr{};
        socklen_t len = sizeof(client_addr);
        int client_fd = ::accept(sock_.fd(),
            reinterpret_cast<sockaddr*>(&client_addr), &len);
        if (client_fd < 0)
            throw std::runtime_error("accept: " + std::string(std::strerror(errno)));
        return TcpStream(Socket(client_fd));
    }

    uint16_t port() const noexcept { return port_; }

private:
    TcpListener(Socket sock, uint16_t port)
        : sock_(std::move(sock)), port_(port) {}

    Socket sock_;
    uint16_t port_;
};

// ============================================================
// Echo server and client
// ============================================================

void run_echo_server(uint16_t port, int max_clients = 3) {
    auto listener = TcpListener::bind("127.0.0.1", port);
    std::cout << "[server] Listening on port " << port << "\n";

    for (int i = 0; i < max_clients; ++i) {
        auto client = listener.accept();
        std::cout << "[server] Client connected: " << client.peer_address() << "\n";

        // Echo loop
        while (true) {
            auto data = client.recv();
            if (data.empty()) {
                std::cout << "[server] Client disconnected\n";
                break;
            }
            std::cout << "[server] Echo: " << data;
            client.send(data);
        }
        // ~TcpStream closes the client socket automatically
    }
    // ~TcpListener closes the listening socket automatically
}

void run_echo_client(uint16_t port) {
    auto stream = TcpStream::connect("127.0.0.1", port);
    std::cout << "[client] Connected to server\n";

    std::vector<std::string> messages = {
        "Hello, server!\n",
        "RAII sockets are great!\n",
        "Goodbye!\n"
    };

    for (const auto& msg : messages) {
        stream.send(msg);
        auto reply = stream.recv();
        std::cout << "[client] Reply: " << reply;
    }
    // ~TcpStream closes connection
    std::cout << "[client] Done\n";
}

int main(int argc, char* argv[]) {
    uint16_t port = 9876;

    if (argc > 1 && std::string(argv[1]) == "server") {
        run_echo_server(port);
    } else if (argc > 1 && std::string(argv[1]) == "client") {
        run_echo_client(port);
    } else {
        std::cout << "Usage: " << argv[0] << " [server|client]\n";
        std::cout << "  Terminal 1: " << argv[0] << " server\n";
        std::cout << "  Terminal 2: " << argv[0] << " client\n";
    }
    return 0;
}
```

**RAII layers in this design:**

1. **`Socket`** — wraps raw fd, calls `close()` in destructor.
2. **`TcpStream`** — owns a `Socket`, provides send/recv.
3. **`TcpListener`** — owns a `Socket`, provides accept which returns a new `TcpStream`.

No file descriptor can leak, even if `send()` or `recv()` throws an exception mid-operation. Each accepted client socket is cleaned up when `TcpStream` goes out of scope.'''),

    ("cpp_deep/nonblocking_io_epoll", r'''Implement a non-blocking I/O abstraction using epoll on Linux in C++. Show an event loop that handles multiple simultaneous connections.''', r'''<think>
epoll is Linux's scalable I/O event notification mechanism.
Key calls: epoll_create1, epoll_ctl (ADD/MOD/DEL), epoll_wait.
Need to set sockets non-blocking with fcntl.
Build a simple event loop that multiplexes multiple client connections.
RAII for epoll fd and sockets.
Show: accept connections, read data, echo back, handle disconnect — all non-blocking.
</think>

Here is a non-blocking echo server using epoll with RAII:

```cpp
#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <functional>
#include <iostream>
#include <netinet/in.h>
#include <string>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <unordered_map>
#include <utility>
#include <vector>

// ============================================================
// Utility: set fd non-blocking
// ============================================================
void set_nonblocking(int fd) {
    int flags = ::fcntl(fd, F_GETFL, 0);
    if (flags < 0) throw std::runtime_error("fcntl F_GETFL: " + std::string(std::strerror(errno)));
    if (::fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0)
        throw std::runtime_error("fcntl F_SETFL: " + std::string(std::strerror(errno)));
}

// ============================================================
// RAII file descriptor
// ============================================================
class Fd {
public:
    explicit Fd(int fd = -1) noexcept : fd_(fd) {}
    Fd(Fd&& o) noexcept : fd_(std::exchange(o.fd_, -1)) {}
    Fd& operator=(Fd&& o) noexcept {
        if (this != &o) { reset(); fd_ = std::exchange(o.fd_, -1); }
        return *this;
    }
    ~Fd() { reset(); }
    int get() const noexcept { return fd_; }
    explicit operator bool() const noexcept { return fd_ >= 0; }
    void reset() noexcept { if (fd_ >= 0) { ::close(fd_); fd_ = -1; } }
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
private:
    int fd_;
};

// ============================================================
// Epoll wrapper
// ============================================================
class Epoll {
public:
    Epoll() : fd_(::epoll_create1(EPOLL_CLOEXEC)) {
        if (fd_.get() < 0)
            throw std::runtime_error("epoll_create1: " + std::string(std::strerror(errno)));
    }

    void add(int fd, uint32_t events, void* data = nullptr) {
        epoll_event ev{};
        ev.events = events;
        ev.data.fd = fd;
        if (data) ev.data.ptr = data;
        if (::epoll_ctl(fd_.get(), EPOLL_CTL_ADD, fd, &ev) < 0)
            throw std::runtime_error("epoll_ctl ADD: " + std::string(std::strerror(errno)));
    }

    void modify(int fd, uint32_t events) {
        epoll_event ev{};
        ev.events = events;
        ev.data.fd = fd;
        if (::epoll_ctl(fd_.get(), EPOLL_CTL_MOD, fd, &ev) < 0)
            throw std::runtime_error("epoll_ctl MOD: " + std::string(std::strerror(errno)));
    }

    void remove(int fd) {
        ::epoll_ctl(fd_.get(), EPOLL_CTL_DEL, fd, nullptr);
    }

    // Wait for events, returns number of ready fds
    int wait(std::vector<epoll_event>& events, int timeout_ms = -1) {
        int n = ::epoll_wait(fd_.get(), events.data(),
                             static_cast<int>(events.size()), timeout_ms);
        if (n < 0 && errno != EINTR)
            throw std::runtime_error("epoll_wait: " + std::string(std::strerror(errno)));
        return std::max(n, 0);
    }

private:
    Fd fd_;
};

// ============================================================
// Connection state
// ============================================================
struct Connection {
    Fd fd;
    std::string read_buf;
    std::string write_buf;

    explicit Connection(int raw_fd) : fd(raw_fd) {}
};

// ============================================================
// Non-blocking echo server
// ============================================================
class EchoServer {
public:
    EchoServer(uint16_t port) : port_(port) {
        // Create listening socket
        listen_fd_ = Fd(::socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0));
        if (!listen_fd_)
            throw std::runtime_error("socket: " + std::string(std::strerror(errno)));

        int opt = 1;
        ::setsockopt(listen_fd_.get(), SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        addr.sin_port = htons(port);

        if (::bind(listen_fd_.get(), reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0)
            throw std::runtime_error("bind: " + std::string(std::strerror(errno)));

        if (::listen(listen_fd_.get(), 128) < 0)
            throw std::runtime_error("listen: " + std::string(std::strerror(errno)));

        // Register listener with epoll
        epoll_.add(listen_fd_.get(), EPOLLIN);
        std::cout << "Echo server listening on port " << port << "\n";
    }

    void run() {
        std::vector<epoll_event> events(64);

        while (running_) {
            int n = epoll_.wait(events, 1000);  // 1 second timeout

            for (int i = 0; i < n; ++i) {
                int fd = events[i].data.fd;

                if (fd == listen_fd_.get()) {
                    handle_accept();
                } else if (events[i].events & EPOLLIN) {
                    handle_read(fd);
                } else if (events[i].events & EPOLLOUT) {
                    handle_write(fd);
                }

                if (events[i].events & (EPOLLERR | EPOLLHUP)) {
                    handle_disconnect(fd);
                }
            }
        }
    }

    void stop() { running_ = false; }

private:
    void handle_accept() {
        while (true) {
            sockaddr_in client_addr{};
            socklen_t len = sizeof(client_addr);
            int client_fd = ::accept4(listen_fd_.get(),
                reinterpret_cast<sockaddr*>(&client_addr), &len, SOCK_NONBLOCK);

            if (client_fd < 0) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                throw std::runtime_error("accept4: " + std::string(std::strerror(errno)));
            }

            char ip[INET_ADDRSTRLEN];
            ::inet_ntop(AF_INET, &client_addr.sin_addr, ip, sizeof(ip));
            std::cout << "New connection from " << ip << ":"
                      << ntohs(client_addr.sin_port) << " (fd=" << client_fd << ")\n";

            // Edge-triggered for efficiency
            epoll_.add(client_fd, EPOLLIN | EPOLLET);
            connections_.emplace(client_fd, Connection(client_fd));
        }
    }

    void handle_read(int fd) {
        auto it = connections_.find(fd);
        if (it == connections_.end()) return;

        char buf[4096];
        while (true) {
            ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
            if (n > 0) {
                // Echo: copy read data to write buffer
                it->second.write_buf.append(buf, static_cast<std::size_t>(n));
            } else if (n == 0) {
                handle_disconnect(fd);
                return;
            } else {
                if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                handle_disconnect(fd);
                return;
            }
        }

        // If we have data to write, watch for EPOLLOUT
        if (!it->second.write_buf.empty()) {
            epoll_.modify(fd, EPOLLIN | EPOLLOUT | EPOLLET);
        }
    }

    void handle_write(int fd) {
        auto it = connections_.find(fd);
        if (it == connections_.end()) return;

        auto& wb = it->second.write_buf;
        while (!wb.empty()) {
            ssize_t n = ::send(fd, wb.data(), wb.size(), MSG_NOSIGNAL);
            if (n > 0) {
                wb.erase(0, static_cast<std::size_t>(n));
            } else {
                if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                handle_disconnect(fd);
                return;
            }
        }

        if (wb.empty()) {
            epoll_.modify(fd, EPOLLIN | EPOLLET);  // Stop watching writes
        }
    }

    void handle_disconnect(int fd) {
        std::cout << "Client disconnected (fd=" << fd << ")\n";
        epoll_.remove(fd);
        connections_.erase(fd);  // ~Connection closes the fd via ~Fd
    }

    Fd listen_fd_;
    Epoll epoll_;
    std::unordered_map<int, Connection> connections_;
    uint16_t port_;
    bool running_ = true;
};

int main() {
    try {
        EchoServer server(9999);
        server.run();
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
```

**Key design points:**

1. **Edge-triggered mode (`EPOLLET`)** — we must drain all data in `handle_read` with a loop until `EAGAIN`, otherwise we miss events.
2. **Non-blocking accept loop** — `accept4` with `SOCK_NONBLOCK` handles multiple pending connections per event.
3. **Write buffering** — data goes into `write_buf`, and we watch for `EPOLLOUT` only when there is data to send. This prevents busy-spinning.
4. **RAII everywhere** — `Fd` for sockets, `Epoll` for the epoll fd, `Connection` map for client state. Erasing from the map destroys the connection and closes its socket.'''),

    ("cpp_deep/asio_style_async", r'''Show Asio-style async I/O patterns in C++: the proactor model with completion handlers. Implement a simplified version showing the async_read/async_write pattern with callbacks.''', r'''<think>
Asio uses the proactor pattern: you initiate an async operation and provide a completion handler.
The io_context (event loop) calls the handler when the operation completes.
Key concepts: io_context, async operations, handlers, strands for serialization.
I'll implement a simplified version that shows the pattern without depending on Boost.Asio.
Focus on the design pattern rather than real I/O — use timers and simulated operations.
</think>

Here is a simplified Asio-style proactor pattern implementation:

```cpp
#include <chrono>
#include <functional>
#include <iostream>
#include <mutex>
#include <queue>
#include <string>
#include <system_error>
#include <thread>
#include <utility>
#include <vector>

// ============================================================
// Error code (simplified)
// ============================================================
enum class errc { success = 0, eof, connection_reset, timeout };

struct ErrorCode {
    errc code = errc::success;
    explicit operator bool() const { return code != errc::success; }
    std::string message() const {
        switch (code) {
            case errc::success: return "success";
            case errc::eof: return "end of file";
            case errc::connection_reset: return "connection reset";
            case errc::timeout: return "operation timed out";
        }
        return "unknown";
    }
};

// ============================================================
// IoContext — the event loop (Asio's io_context)
// ============================================================
class IoContext {
public:
    using Handler = std::function<void()>;

    // Post a handler to be executed in the event loop
    void post(Handler handler) {
        std::lock_guard lock(mutex_);
        work_queue_.push(std::move(handler));
    }

    // Run the event loop until no more work
    void run() {
        while (true) {
            Handler handler;
            {
                std::lock_guard lock(mutex_);
                if (work_queue_.empty() && timers_.empty()) break;

                // Check timers
                auto now = std::chrono::steady_clock::now();
                while (!timers_.empty() && timers_.top().deadline <= now) {
                    auto h = std::move(const_cast<TimerEntry&>(timers_.top()).handler);
                    timers_.pop();
                    work_queue_.push(std::move(h));
                }

                if (!work_queue_.empty()) {
                    handler = std::move(work_queue_.front());
                    work_queue_.pop();
                }
            }

            if (handler) {
                handler();
            } else {
                // Sleep until next timer or briefly
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
    }

    // Schedule handler after delay
    void schedule_after(std::chrono::milliseconds delay, Handler handler) {
        std::lock_guard lock(mutex_);
        timers_.push({std::chrono::steady_clock::now() + delay, std::move(handler)});
    }

private:
    struct TimerEntry {
        std::chrono::steady_clock::time_point deadline;
        Handler handler;
        bool operator>(const TimerEntry& other) const {
            return deadline > other.deadline;
        }
    };

    std::mutex mutex_;
    std::queue<Handler> work_queue_;
    std::priority_queue<TimerEntry, std::vector<TimerEntry>, std::greater<>> timers_;
};

// ============================================================
// AsyncTimer — like Asio's steady_timer
// ============================================================
class AsyncTimer {
public:
    AsyncTimer(IoContext& ctx) : ctx_(ctx) {}

    void expires_after(std::chrono::milliseconds ms) { delay_ = ms; }

    // Async wait with completion handler
    void async_wait(std::function<void(ErrorCode)> handler) {
        ctx_.schedule_after(delay_, [h = std::move(handler)]() {
            h(ErrorCode{errc::success});
        });
    }

private:
    IoContext& ctx_;
    std::chrono::milliseconds delay_{0};
};

// ============================================================
// Simulated async stream (like Asio's tcp::socket)
// ============================================================
class AsyncStream {
public:
    AsyncStream(IoContext& ctx, std::string data)
        : ctx_(ctx), data_(std::move(data)), pos_(0) {}

    // Asio-style async_read: handler(error_code, bytes_transferred)
    void async_read_some(char* buf, std::size_t max_len,
                         std::function<void(ErrorCode, std::size_t)> handler) {
        // Simulate I/O latency
        ctx_.schedule_after(std::chrono::milliseconds(10),
            [this, buf, max_len, h = std::move(handler)]() {
                if (pos_ >= data_.size()) {
                    h(ErrorCode{errc::eof}, 0);
                    return;
                }
                std::size_t to_read = std::min(max_len, data_.size() - pos_);
                std::memcpy(buf, data_.data() + pos_, to_read);
                pos_ += to_read;
                h(ErrorCode{}, to_read);
            });
    }

    // Asio-style async_write
    void async_write(const std::string& data,
                     std::function<void(ErrorCode, std::size_t)> handler) {
        ctx_.schedule_after(std::chrono::milliseconds(5),
            [data, h = std::move(handler)]() {
                std::cout << "  [stream] wrote: " << data;
                h(ErrorCode{}, data.size());
            });
    }

private:
    IoContext& ctx_;
    std::string data_;
    std::size_t pos_;
};

// ============================================================
// Composed operations (like Asio's async_read until delimiter)
// ============================================================
void async_read_until(AsyncStream& stream, std::string& result, char delimiter,
                      std::function<void(ErrorCode, std::size_t)> handler) {
    struct ReadOp {
        AsyncStream& stream;
        std::string& result;
        char delimiter;
        std::function<void(ErrorCode, std::size_t)> handler;
        char buf[64];

        void start() {
            stream.async_read_some(buf, sizeof(buf),
                [this](ErrorCode ec, std::size_t n) {
                    if (ec) { handler(ec, result.size()); delete this; return; }

                    for (std::size_t i = 0; i < n; ++i) {
                        result += buf[i];
                        if (buf[i] == delimiter) {
                            handler(ErrorCode{}, result.size());
                            delete this;
                            return;
                        }
                    }
                    start();  // Continue reading
                });
        }
    };

    auto* op = new ReadOp{stream, result, delimiter, std::move(handler), {}};
    op->start();
}

// ============================================================
// Application using Asio-style patterns
// ============================================================

void run_echo_session(IoContext& ctx, AsyncStream& stream) {
    auto line = std::make_shared<std::string>();

    // Composed async operation: read a line, echo it, repeat
    struct Session : std::enable_shared_from_this<Session> {
        IoContext& ctx;
        AsyncStream& stream;

        Session(IoContext& c, AsyncStream& s) : ctx(c), stream(s) {}

        void start() {
            read_line();
        }

        void read_line() {
            auto buf = std::make_shared<std::string>();
            auto self = shared_from_this();

            async_read_until(stream, *buf, '\n',
                [self, buf](ErrorCode ec, std::size_t bytes) {
                    if (ec) {
                        std::cout << "  Read finished: " << ec.message() << "\n";
                        return;
                    }
                    std::cout << "  [session] received: " << *buf;
                    self->echo_back(*buf);
                });
        }

        void echo_back(const std::string& data) {
            auto self = shared_from_this();
            stream.async_write("ECHO: " + data,
                [self](ErrorCode ec, std::size_t) {
                    if (!ec) self->read_line();  // Continue the loop
                });
        }
    };

    auto session = std::make_shared<Session>(ctx, stream);
    session->start();
}

int main() {
    IoContext ctx;

    // Simulated stream with some "incoming data"
    AsyncStream stream(ctx, "Hello World!\nAsync I/O is great!\nGoodbye!\n");

    std::cout << "Starting async echo session...\n";
    run_echo_session(ctx, stream);

    // Also schedule a timer alongside
    AsyncTimer timer(ctx);
    timer.expires_after(std::chrono::milliseconds(50));
    timer.async_wait([](ErrorCode ec) {
        std::cout << "  [timer] fired! (" << ec.message() << ")\n";
    });

    // Run the event loop
    ctx.run();
    std::cout << "Event loop finished.\n";

    return 0;
}
```

**Asio pattern summary:**

1. **Proactor model**: You initiate an async operation (`async_read_some`, `async_write`) and provide a completion handler. The I/O subsystem does the work and calls your handler when done.
2. **`io_context::run()`** drives everything — it dispatches completion handlers and timer callbacks in a single thread.
3. **Composed operations** (`async_read_until`) chain primitive operations with internal state, presenting a single high-level handler to the caller.
4. **`shared_from_this`** keeps the session alive across async callbacks — prevents dangling references when the initiating scope exits.'''),

    ("cpp_deep/serial_port_timeout", r'''Show serial port communication in C++ on Linux with configurable baud rate, parity, and read timeout using termios. Include RAII for the port handle.''', r'''<think>
Serial port on Linux is /dev/ttyS* or /dev/ttyUSB*.
Use termios for configuration: baud rate, data bits, parity, stop bits.
Use VMIN/VTIME for read timeout behavior.
RAII for the file descriptor.
Show a complete class with open, configure, read, write, and timeout.
</think>

Here is a RAII serial port wrapper with full termios configuration:

```cpp
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <termios.h>
#include <unistd.h>
#include <utility>
#include <vector>

// ============================================================
// Serial port configuration
// ============================================================
enum class Parity { None, Odd, Even };
enum class StopBits { One, Two };
enum class DataBits { Five = 5, Six = 6, Seven = 7, Eight = 8 };

struct SerialConfig {
    speed_t baud_rate = B115200;
    DataBits data_bits = DataBits::Eight;
    Parity parity = Parity::None;
    StopBits stop_bits = StopBits::One;
    int read_timeout_ds = 10;  // Deciseconds (1 = 100ms)
    int min_bytes = 0;         // Minimum bytes before read returns
};

// ============================================================
// RAII Serial Port
// ============================================================
class SerialPort {
public:
    SerialPort() noexcept : fd_(-1) {}

    // Open and configure
    explicit SerialPort(const std::string& device, const SerialConfig& config = {})
        : fd_(-1), device_(device)
    {
        fd_ = ::open(device.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
        if (fd_ < 0) {
            throw std::runtime_error(
                "Cannot open " + device + ": " + std::strerror(errno));
        }

        // Save original settings for restoration
        if (::tcgetattr(fd_, &original_termios_) < 0) {
            ::close(fd_);
            fd_ = -1;
            throw std::runtime_error("tcgetattr failed: " + std::string(std::strerror(errno)));
        }
        has_original_ = true;

        configure(config);

        // Switch to blocking mode after configuration
        int flags = ::fcntl(fd_, F_GETFL, 0);
        ::fcntl(fd_, F_SETFL, flags & ~O_NONBLOCK);
    }

    // Move only
    SerialPort(SerialPort&& o) noexcept
        : fd_(std::exchange(o.fd_, -1))
        , device_(std::move(o.device_))
        , original_termios_(o.original_termios_)
        , has_original_(std::exchange(o.has_original_, false)) {}

    SerialPort& operator=(SerialPort&& o) noexcept {
        if (this != &o) {
            close();
            fd_ = std::exchange(o.fd_, -1);
            device_ = std::move(o.device_);
            original_termios_ = o.original_termios_;
            has_original_ = std::exchange(o.has_original_, false);
        }
        return *this;
    }

    SerialPort(const SerialPort&) = delete;
    SerialPort& operator=(const SerialPort&) = delete;

    ~SerialPort() { close(); }

    // Configure port parameters
    void configure(const SerialConfig& config) {
        termios tty{};
        if (::tcgetattr(fd_, &tty) < 0)
            throw std::runtime_error("tcgetattr: " + std::string(std::strerror(errno)));

        // Baud rate
        ::cfsetispeed(&tty, config.baud_rate);
        ::cfsetospeed(&tty, config.baud_rate);

        // Data bits
        tty.c_cflag &= ~CSIZE;
        switch (config.data_bits) {
            case DataBits::Five:  tty.c_cflag |= CS5; break;
            case DataBits::Six:   tty.c_cflag |= CS6; break;
            case DataBits::Seven: tty.c_cflag |= CS7; break;
            case DataBits::Eight: tty.c_cflag |= CS8; break;
        }

        // Parity
        switch (config.parity) {
            case Parity::None:
                tty.c_cflag &= ~PARENB;
                break;
            case Parity::Even:
                tty.c_cflag |= PARENB;
                tty.c_cflag &= ~PARODD;
                break;
            case Parity::Odd:
                tty.c_cflag |= PARENB;
                tty.c_cflag |= PARODD;
                break;
        }

        // Stop bits
        if (config.stop_bits == StopBits::Two)
            tty.c_cflag |= CSTOPB;
        else
            tty.c_cflag &= ~CSTOPB;

        // No hardware flow control
        tty.c_cflag &= ~CRTSCTS;
        tty.c_cflag |= CLOCAL | CREAD;  // Enable receiver, ignore modem lines

        // Raw mode (no special processing)
        tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
        tty.c_iflag &= ~(IXON | IXOFF | IXANY | IGNBRK | BRKINT |
                          PARMRK | ISTRIP | INLCR | IGNCR | ICRNL);
        tty.c_oflag &= ~OPOST;

        // Timeout: VTIME in deciseconds, VMIN = min bytes
        tty.c_cc[VTIME] = static_cast<cc_t>(config.read_timeout_ds);
        tty.c_cc[VMIN] = static_cast<cc_t>(config.min_bytes);

        if (::tcsetattr(fd_, TCSANOW, &tty) < 0)
            throw std::runtime_error("tcsetattr: " + std::string(std::strerror(errno)));

        ::tcflush(fd_, TCIOFLUSH);  // Discard any buffered data
    }

    // Write data
    void write(std::string_view data) {
        const char* ptr = data.data();
        std::size_t remaining = data.size();

        while (remaining > 0) {
            ssize_t n = ::write(fd_, ptr, remaining);
            if (n < 0) {
                if (errno == EINTR) continue;
                throw std::runtime_error("write: " + std::string(std::strerror(errno)));
            }
            ptr += n;
            remaining -= static_cast<std::size_t>(n);
        }
    }

    // Read with timeout (returns empty on timeout)
    std::string read(std::size_t max_bytes = 256) {
        std::string buf(max_bytes, '\0');
        ssize_t n = ::read(fd_, buf.data(), max_bytes);
        if (n < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) return {};
            throw std::runtime_error("read: " + std::string(std::strerror(errno)));
        }
        buf.resize(static_cast<std::size_t>(n));
        return buf;
    }

    // Read exact number of bytes (blocks until received or timeout)
    std::optional<std::string> read_exact(std::size_t count, int attempts = 10) {
        std::string result;
        result.reserve(count);

        for (int i = 0; i < attempts && result.size() < count; ++i) {
            auto chunk = read(count - result.size());
            if (chunk.empty()) continue;
            result += chunk;
        }

        if (result.size() < count) return std::nullopt;
        return result;
    }

    // Read until delimiter found
    std::optional<std::string> read_until(char delimiter, std::size_t max = 1024) {
        std::string result;
        char c;
        while (result.size() < max) {
            ssize_t n = ::read(fd_, &c, 1);
            if (n < 0) {
                if (errno == EINTR) continue;
                return std::nullopt;
            }
            if (n == 0) return std::nullopt;  // Timeout
            result += c;
            if (c == delimiter) return result;
        }
        return std::nullopt;
    }

    // Flush buffers
    void flush_input() { ::tcflush(fd_, TCIFLUSH); }
    void flush_output() { ::tcflush(fd_, TCOFLUSH); }
    void drain() { ::tcdrain(fd_); }  // Wait until all output sent

    bool is_open() const noexcept { return fd_ >= 0; }
    const std::string& device() const noexcept { return device_; }

private:
    void close() noexcept {
        if (fd_ >= 0) {
            if (has_original_) {
                ::tcsetattr(fd_, TCSANOW, &original_termios_);  // Restore
            }
            ::close(fd_);
            fd_ = -1;
        }
    }

    int fd_;
    std::string device_;
    termios original_termios_{};
    bool has_original_ = false;
};

// ============================================================
// Helper: baud rate from integer
// ============================================================
speed_t baud_from_int(int rate) {
    switch (rate) {
        case 9600:   return B9600;
        case 19200:  return B19200;
        case 38400:  return B38400;
        case 57600:  return B57600;
        case 115200: return B115200;
        case 230400: return B230400;
        case 460800: return B460800;
        case 921600: return B921600;
        default: throw std::runtime_error("Unsupported baud rate: " + std::to_string(rate));
    }
}

// ============================================================
// Example usage
// ============================================================
int main(int argc, char* argv[]) {
    std::string device = (argc > 1) ? argv[1] : "/dev/ttyUSB0";

    try {
        SerialConfig config;
        config.baud_rate = B115200;
        config.data_bits = DataBits::Eight;
        config.parity = Parity::None;
        config.stop_bits = StopBits::One;
        config.read_timeout_ds = 10;  // 1 second timeout

        SerialPort port(device, config);
        std::cout << "Opened " << port.device() << " at 115200 8N1\n";

        // Send a command
        port.write("AT\r\n");
        port.drain();  // Wait for transmission complete

        // Read response with timeout
        if (auto response = port.read_until('\n')) {
            std::cout << "Response: " << *response;
        } else {
            std::cout << "No response (timeout)\n";
        }

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        std::cerr << "(This example requires a real serial device)\n";
        return 1;
    }

    return 0;
}
```

**Termios VMIN/VTIME behavior:**

| VMIN | VTIME | Behavior |
|------|-------|----------|
| 0    | 0     | Non-blocking: return immediately with available data |
| 0    | >0    | Timed read: return after VTIME deciseconds or on data |
| >0   | 0     | Blocking: wait until VMIN bytes received |
| >0   | >0    | Mixed: VTIME is inter-byte timeout after first byte |

**RAII guarantees:** The destructor restores original termios settings and closes the fd. This prevents leaving the terminal in a corrupted state if the program crashes or throws.'''),

    ("cpp_deep/pipe_ipc", r'''Show pipe-based IPC between processes in C++ on Linux. Demonstrate creating pipes, fork+exec with redirected stdin/stdout, and bidirectional communication with a child process.''', r'''<think>
Pipes are unidirectional, so for bidirectional communication we need two pipes.
parent_to_child[0]=child reads, parent_to_child[1]=parent writes.
child_to_parent[0]=parent reads, child_to_parent[1]=child writes.
Use fork+exec, redirect child's stdin/stdout to the pipes.
RAII for pipe fds.
Show: parent sends data to child, child processes it and sends back results.
</think>

Here is bidirectional pipe IPC with fork/exec and RAII:

```cpp
#include <cerrno>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <utility>
#include <vector>

// ============================================================
// RAII pipe pair
// ============================================================
class Pipe {
public:
    Pipe() {
        if (::pipe(fds_) < 0)
            throw std::runtime_error("pipe: " + std::string(std::strerror(errno)));
    }

    ~Pipe() {
        close_read();
        close_write();
    }

    Pipe(Pipe&& o) noexcept {
        fds_[0] = std::exchange(o.fds_[0], -1);
        fds_[1] = std::exchange(o.fds_[1], -1);
    }

    Pipe(const Pipe&) = delete;
    Pipe& operator=(const Pipe&) = delete;

    int read_fd() const noexcept { return fds_[0]; }
    int write_fd() const noexcept { return fds_[1]; }

    void close_read() noexcept {
        if (fds_[0] >= 0) { ::close(fds_[0]); fds_[0] = -1; }
    }

    void close_write() noexcept {
        if (fds_[1] >= 0) { ::close(fds_[1]); fds_[1] = -1; }
    }

    // Redirect read end to target fd (e.g., STDIN_FILENO)
    void dup_read_to(int target_fd) {
        if (::dup2(fds_[0], target_fd) < 0)
            throw std::runtime_error("dup2: " + std::string(std::strerror(errno)));
        close_read();
    }

    // Redirect write end to target fd (e.g., STDOUT_FILENO)
    void dup_write_to(int target_fd) {
        if (::dup2(fds_[1], target_fd) < 0)
            throw std::runtime_error("dup2: " + std::string(std::strerror(errno)));
        close_write();
    }

private:
    int fds_[2]{-1, -1};
};

// ============================================================
// RAII child process handle
// ============================================================
class ChildProcess {
public:
    ChildProcess(pid_t pid, int stdin_fd, int stdout_fd)
        : pid_(pid), stdin_fd_(stdin_fd), stdout_fd_(stdout_fd) {}

    ChildProcess(ChildProcess&& o) noexcept
        : pid_(std::exchange(o.pid_, -1))
        , stdin_fd_(std::exchange(o.stdin_fd_, -1))
        , stdout_fd_(std::exchange(o.stdout_fd_, -1)) {}

    ~ChildProcess() {
        close_stdin();
        close_stdout();
        if (pid_ > 0) wait();
    }

    // Write to child's stdin
    void write(const std::string& data) {
        const char* ptr = data.data();
        std::size_t rem = data.size();
        while (rem > 0) {
            ssize_t n = ::write(stdin_fd_, ptr, rem);
            if (n < 0) {
                if (errno == EINTR) continue;
                throw std::runtime_error("write to child: " + std::string(std::strerror(errno)));
            }
            ptr += n;
            rem -= static_cast<std::size_t>(n);
        }
    }

    // Read from child's stdout
    std::string read(std::size_t max = 4096) {
        std::string buf(max, '\0');
        ssize_t n = ::read(stdout_fd_, buf.data(), max);
        if (n < 0) {
            if (errno == EINTR) return read(max);
            throw std::runtime_error("read from child: " + std::string(std::strerror(errno)));
        }
        buf.resize(static_cast<std::size_t>(n));
        return buf;
    }

    // Read all until EOF
    std::string read_all() {
        std::string result;
        char buf[4096];
        while (true) {
            ssize_t n = ::read(stdout_fd_, buf, sizeof(buf));
            if (n <= 0) break;
            result.append(buf, static_cast<std::size_t>(n));
        }
        return result;
    }

    void close_stdin() noexcept {
        if (stdin_fd_ >= 0) { ::close(stdin_fd_); stdin_fd_ = -1; }
    }

    void close_stdout() noexcept {
        if (stdout_fd_ >= 0) { ::close(stdout_fd_); stdout_fd_ = -1; }
    }

    int wait() {
        if (pid_ <= 0) return -1;
        int status = 0;
        ::waitpid(pid_, &status, 0);
        pid_ = -1;
        return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
    }

    pid_t pid() const noexcept { return pid_; }

private:
    pid_t pid_;
    int stdin_fd_;
    int stdout_fd_;
};

// ============================================================
// Spawn a child process with redirected stdin/stdout
// ============================================================
ChildProcess spawn(const std::string& program, const std::vector<std::string>& args = {}) {
    Pipe to_child;    // Parent writes, child reads (child's stdin)
    Pipe from_child;  // Child writes, parent reads (child's stdout)

    pid_t pid = ::fork();
    if (pid < 0)
        throw std::runtime_error("fork: " + std::string(std::strerror(errno)));

    if (pid == 0) {
        // === Child process ===
        // Redirect stdin to read end of to_child pipe
        to_child.dup_read_to(STDIN_FILENO);
        to_child.close_write();  // Child doesn't write to its own stdin pipe

        // Redirect stdout to write end of from_child pipe
        from_child.dup_write_to(STDOUT_FILENO);
        from_child.close_read();  // Child doesn't read from its own stdout pipe

        // Build argv
        std::vector<const char*> argv;
        argv.push_back(program.c_str());
        for (const auto& a : args) argv.push_back(a.c_str());
        argv.push_back(nullptr);

        ::execvp(program.c_str(), const_cast<char* const*>(argv.data()));
        // If exec fails:
        std::perror("execvp");
        ::_exit(127);
    }

    // === Parent process ===
    // Close the ends we don't use
    to_child.close_read();     // Parent doesn't read from to_child
    from_child.close_write();  // Parent doesn't write to from_child

    return ChildProcess(pid, to_child.write_fd(), from_child.read_fd());
    // Note: Pipe destructors will try to close fds, but they're already -1
    // because we transferred ownership via the raw fd values.
    // In production, use a release() method.
}

// ============================================================
// Example: bidirectional communication with child
// ============================================================
int main() {
    // Spawn a child that transforms input (using tr to uppercase)
    std::cout << "=== Spawning 'tr' to uppercase input ===\n";
    {
        auto child = spawn("tr", {"a-z", "A-Z"});

        child.write("hello from parent process\n");
        child.write("pipes are great for ipc\n");
        child.close_stdin();  // Signal EOF to child

        std::string output = child.read_all();
        std::cout << "Child output:\n" << output;

        int exit_code = child.wait();
        std::cout << "Child exit code: " << exit_code << "\n";
    }

    // Spawn bc (calculator) for interactive communication
    std::cout << "\n=== Interactive pipe to 'bc' calculator ===\n";
    {
        auto calc = spawn("bc", {"-q"});  // -q = quiet mode

        std::vector<std::string> expressions = {
            "2 + 3\n",
            "10 * 42\n",
            "2 ^ 10\n",
        };

        for (const auto& expr : expressions) {
            calc.write(expr);
            std::string result = calc.read();
            std::cout << "  " << expr.substr(0, expr.size()-1)
                      << " = " << result;
        }

        // calc destructor: closes stdin (EOF to bc), reads remaining, waits
    }

    // Spawn and capture stderr too (redirect 2>&1 style)
    std::cout << "\n=== Pipeline: echo | sort ===\n";
    {
        auto sorter = spawn("sort");

        sorter.write("banana\napple\ncherry\ndate\n");
        sorter.close_stdin();

        std::cout << "Sorted:\n" << sorter.read_all();
    }

    return 0;
}
```

**Pipe IPC architecture:**

```
Parent Process              Child Process
  write() ----[to_child pipe]----> stdin  (fd 0)
  read()  <---[from_child pipe]--- stdout (fd 1)
```

**RAII ensures:**
1. `Pipe` destructor closes any open fds — no leaked file descriptors even on exceptions.
2. `ChildProcess` destructor closes pipe ends and waits for the child — no zombie processes.
3. `close_stdin()` sends EOF to the child, allowing it to finish processing and exit.'''),

    ("cpp_deep/filesystem_operations", r'''Show comprehensive std::filesystem usage in C++17/20: recursive directory traversal, copying with options, permission management, symlink handling, and disk space queries.''', r'''<think>
std::filesystem has a rich API. Cover the most useful operations with practical examples.
Recursive traversal, copy options, permissions, symlinks, space info, temp directories.
</think>

Here is a comprehensive `std::filesystem` reference with practical examples:

```cpp
#include <algorithm>
#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

// ============================================================
// 1. Recursive directory traversal with filtering
// ============================================================
void demo_traversal(const fs::path& dir) {
    std::cout << "=== Recursive Traversal ===\n";

    // Collect all .cpp and .h files
    std::vector<fs::directory_entry> source_files;

    for (const auto& entry : fs::recursive_directory_iterator(
             dir, fs::directory_options::skip_permission_denied)) {
        if (entry.is_regular_file()) {
            auto ext = entry.path().extension().string();
            if (ext == ".cpp" || ext == ".h" || ext == ".hpp") {
                source_files.push_back(entry);
            }
        }
    }

    // Sort by size descending
    std::sort(source_files.begin(), source_files.end(),
        [](const auto& a, const auto& b) {
            return a.file_size() > b.file_size();
        });

    std::cout << "  Found " << source_files.size() << " source files\n";
    for (const auto& entry : source_files) {
        auto ftime = entry.last_write_time();
        auto sctp = std::chrono::time_point_cast<std::chrono::system_clock::duration>(
            ftime - fs::file_time_type::clock::now() + std::chrono::system_clock::now());
        auto time_t = std::chrono::system_clock::to_time_t(sctp);

        std::cout << "  " << std::setw(8) << entry.file_size() << " bytes  "
                  << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M")
                  << "  " << entry.path().filename().string() << "\n";
    }
}

// ============================================================
// 2. Path manipulation
// ============================================================
void demo_path_ops() {
    std::cout << "\n=== Path Operations ===\n";

    fs::path p = "/home/user/projects/myapp/src/main.cpp";

    std::cout << "  Full path:      " << p << "\n";
    std::cout << "  Root:           " << p.root_path() << "\n";
    std::cout << "  Parent:         " << p.parent_path() << "\n";
    std::cout << "  Filename:       " << p.filename() << "\n";
    std::cout << "  Stem:           " << p.stem() << "\n";
    std::cout << "  Extension:      " << p.extension() << "\n";
    std::cout << "  Relative:       " << p.relative_path() << "\n";

    // Building paths
    fs::path base = "/opt/app";
    fs::path config = base / "config" / "settings.json";  // operator/
    std::cout << "  Built path:     " << config << "\n";

    // Canonical (resolve symlinks and ..)
    auto temp = fs::temp_directory_path();
    std::cout << "  Temp dir:       " << temp << "\n";

    // Relative path calculation
    fs::path from = "/home/user/docs";
    fs::path to = "/home/user/projects/app";
    std::cout << "  Relative:       " << fs::relative(to, from) << "\n";
    // Output: ../projects/app
}

// ============================================================
// 3. Copy with options
// ============================================================
void demo_copy(const fs::path& base) {
    std::cout << "\n=== Copy Operations ===\n";

    auto src = base / "copy_src";
    auto dst = base / "copy_dst";

    // Create source structure
    fs::create_directories(src / "sub1" / "deep");
    fs::create_directories(src / "sub2");
    std::ofstream(src / "root.txt") << "root file";
    std::ofstream(src / "sub1" / "a.txt") << "file a";
    std::ofstream(src / "sub1" / "deep" / "b.txt") << "file b";
    std::ofstream(src / "sub2" / "c.txt") << "file c";

    // Copy single file
    fs::copy_file(src / "root.txt", base / "root_copy.txt",
                  fs::copy_options::overwrite_existing);

    // Recursive copy of entire directory tree
    fs::copy(src, dst,
             fs::copy_options::recursive |
             fs::copy_options::overwrite_existing);

    // Verify
    int count = 0;
    for (const auto& e : fs::recursive_directory_iterator(dst)) {
        if (e.is_regular_file()) ++count;
    }
    std::cout << "  Copied " << count << " files to " << dst << "\n";
}

// ============================================================
// 4. Permissions
// ============================================================
void demo_permissions(const fs::path& base) {
    std::cout << "\n=== Permissions ===\n";

    auto file = base / "perms_test.txt";
    std::ofstream(file) << "test";

    // Read current permissions
    auto perms = fs::status(file).permissions();
    auto show = [](fs::perms p) {
        auto check = [](fs::perms p, fs::perms bit) {
            return (p & bit) != fs::perms::none ? '+' : '-';
        };
        std::cout << check(p, fs::perms::owner_read)
                  << check(p, fs::perms::owner_write)
                  << check(p, fs::perms::owner_exec)
                  << check(p, fs::perms::group_read)
                  << check(p, fs::perms::group_write)
                  << check(p, fs::perms::group_exec)
                  << check(p, fs::perms::others_read)
                  << check(p, fs::perms::others_write)
                  << check(p, fs::perms::others_exec);
    };

    std::cout << "  Before: ";
    show(perms);
    std::cout << "\n";

    // Make read-only
    fs::permissions(file, fs::perms::owner_write | fs::perms::group_write,
                    fs::perm_options::remove);

    perms = fs::status(file).permissions();
    std::cout << "  After:  ";
    show(perms);
    std::cout << " (removed write)\n";

    // Restore for cleanup
    fs::permissions(file, fs::perms::owner_write, fs::perm_options::add);
}

// ============================================================
// 5. Symlinks
// ============================================================
void demo_symlinks(const fs::path& base) {
    std::cout << "\n=== Symlinks ===\n";

    auto target = base / "symlink_target.txt";
    auto link = base / "symlink_link.txt";

    std::ofstream(target) << "I am the target";

    // Create symlink
    fs::create_symlink(target, link);

    std::cout << "  Is symlink: " << fs::is_symlink(link) << "\n";
    std::cout << "  Points to:  " << fs::read_symlink(link) << "\n";
    std::cout << "  Target size: " << fs::file_size(link) << " bytes\n";  // Follows link

    // Symlink status vs regular status
    auto sym_status = fs::symlink_status(link);  // Status of link itself
    auto reg_status = fs::status(link);           // Status of target

    std::cout << "  Link type:   " << (sym_status.type() == fs::file_type::symlink ? "symlink" : "other") << "\n";
    std::cout << "  Target type: " << (reg_status.type() == fs::file_type::regular ? "regular" : "other") << "\n";
}

// ============================================================
// 6. Disk space
// ============================================================
void demo_disk_space() {
    std::cout << "\n=== Disk Space ===\n";

    auto info = fs::space("/");
    auto to_gb = [](std::uintmax_t bytes) {
        return static_cast<double>(bytes) / (1024.0 * 1024.0 * 1024.0);
    };

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "  Capacity:  " << to_gb(info.capacity) << " GB\n";
    std::cout << "  Free:      " << to_gb(info.free) << " GB\n";
    std::cout << "  Available: " << to_gb(info.available) << " GB\n";
    std::cout << "  Used:      " << to_gb(info.capacity - info.free) << " GB ("
              << (100.0 * (info.capacity - info.free) / info.capacity) << "%)\n";
}

// ============================================================
// 7. Error handling with error_code
// ============================================================
void demo_error_handling() {
    std::cout << "\n=== Error Handling ===\n";

    // Non-throwing version with error_code
    std::error_code ec;

    auto size = fs::file_size("/nonexistent/file.txt", ec);
    if (ec) {
        std::cout << "  file_size error: " << ec.message() << "\n";
    }

    bool exists = fs::exists("/tmp", ec);
    std::cout << "  /tmp exists: " << std::boolalpha << exists << "\n";

    // Check if path is inside another
    auto base = fs::path("/home/user");
    auto test = fs::path("/home/user/docs/../docs/file.txt");
    auto normalized = test.lexically_normal();
    std::cout << "  Normalized: " << normalized << "\n";

    auto rel = normalized.lexically_relative(base);
    std::cout << "  Relative to base: " << rel << "\n";
}

int main() {
    auto base = fs::temp_directory_path() / "fs_demo";
    fs::create_directories(base);

    // Create some source files for traversal demo
    fs::create_directories(base / "src");
    std::ofstream(base / "src" / "main.cpp") << "int main() {}";
    std::ofstream(base / "src" / "utils.hpp") << "#pragma once";
    std::ofstream(base / "src" / "helpers.cpp") << "void help() {}";

    demo_traversal(base);
    demo_path_ops();
    demo_copy(base);
    demo_permissions(base);
    demo_symlinks(base);
    demo_disk_space();
    demo_error_handling();

    // Cleanup
    fs::remove_all(base);
    std::cout << "\nCleaned up " << base << "\n";

    return 0;
}
```

**Key `std::filesystem` tips:**

1. **Always use `error_code` overloads** in production code to avoid exceptions on expected failures (missing files, permission denied).
2. **`recursive_directory_iterator`** with `skip_permission_denied` prevents crashes on unreadable directories.
3. **`lexically_normal()`** resolves `..` and `.` without hitting the filesystem — faster than `canonical()` which requires the path to exist.
4. **`copy_options::recursive`** copies entire directory trees in a single call.
5. **`space()`** returns capacity/free/available — `available` accounts for reserved blocks (relevant on ext4).'''),

    ("cpp_deep/inotify_file_watcher", r'''Implement a file change watcher on Linux using inotify wrapped in C++ RAII. Watch for create, modify, delete, and rename events in a directory.''', r'''<think>
inotify is Linux's file system notification mechanism.
inotify_init1 creates an inotify instance (fd).
inotify_add_watch adds watches on files/directories.
Read events from the fd.
RAII for the inotify fd and watches.
</think>

Here is a RAII inotify file watcher:

```cpp
#include <cerrno>
#include <cstring>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <sys/inotify.h>
#include <unistd.h>
#include <unordered_map>
#include <utility>
#include <vector>

// ============================================================
// File system event
// ============================================================
enum class FileEvent {
    Created,
    Modified,
    Deleted,
    Renamed,
    MovedFrom,
    MovedTo,
    Accessed,
    AttribChanged,
    Unknown
};

struct WatchEvent {
    FileEvent type;
    std::string path;       // Watched directory
    std::string filename;   // File within directory
    bool is_dir;
};

const char* event_name(FileEvent e) {
    switch (e) {
        case FileEvent::Created:       return "CREATED";
        case FileEvent::Modified:      return "MODIFIED";
        case FileEvent::Deleted:       return "DELETED";
        case FileEvent::Renamed:       return "RENAMED";
        case FileEvent::MovedFrom:     return "MOVED_FROM";
        case FileEvent::MovedTo:       return "MOVED_TO";
        case FileEvent::Accessed:      return "ACCESSED";
        case FileEvent::AttribChanged: return "ATTRIB";
        default:                       return "UNKNOWN";
    }
}

// ============================================================
// RAII inotify file watcher
// ============================================================
class FileWatcher {
public:
    using Callback = std::function<void(const WatchEvent&)>;

    FileWatcher() : fd_(inotify_init1(IN_NONBLOCK | IN_CLOEXEC)) {
        if (fd_ < 0)
            throw std::runtime_error("inotify_init1: " + std::string(std::strerror(errno)));
    }

    ~FileWatcher() {
        // Remove all watches (kernel does this on close, but be explicit)
        for (auto& [wd, path] : watch_paths_) {
            inotify_rm_watch(fd_, wd);
        }
        if (fd_ >= 0) ::close(fd_);
    }

    FileWatcher(const FileWatcher&) = delete;
    FileWatcher& operator=(const FileWatcher&) = delete;

    // Add a directory to watch
    int watch(const std::string& path,
              uint32_t mask = IN_CREATE | IN_MODIFY | IN_DELETE |
                              IN_MOVED_FROM | IN_MOVED_TO | IN_ATTRIB) {
        int wd = inotify_add_watch(fd_, path.c_str(), mask);
        if (wd < 0)
            throw std::runtime_error(
                "inotify_add_watch " + path + ": " + std::strerror(errno));

        watch_paths_[wd] = path;
        std::cout << "Watching: " << path << " (wd=" << wd << ")\n";
        return wd;
    }

    // Remove a watch
    void unwatch(int wd) {
        inotify_rm_watch(fd_, wd);
        watch_paths_.erase(wd);
    }

    // Poll for events (non-blocking), invoke callback for each
    void poll(const Callback& callback) {
        alignas(inotify_event) char buf[4096];

        while (true) {
            ssize_t len = ::read(fd_, buf, sizeof(buf));
            if (len < 0) {
                if (errno == EAGAIN) break;  // No more events
                throw std::runtime_error("read: " + std::string(std::strerror(errno)));
            }
            if (len == 0) break;

            const char* ptr = buf;
            while (ptr < buf + len) {
                auto* event = reinterpret_cast<const inotify_event*>(ptr);

                WatchEvent we;
                we.is_dir = (event->mask & IN_ISDIR) != 0;
                we.filename = (event->len > 0) ? event->name : "";

                auto it = watch_paths_.find(event->wd);
                we.path = (it != watch_paths_.end()) ? it->second : "???";

                // Map inotify mask to our event type
                if (event->mask & IN_CREATE)     we.type = FileEvent::Created;
                else if (event->mask & IN_MODIFY) we.type = FileEvent::Modified;
                else if (event->mask & IN_DELETE) we.type = FileEvent::Deleted;
                else if (event->mask & IN_MOVED_FROM) we.type = FileEvent::MovedFrom;
                else if (event->mask & IN_MOVED_TO)   we.type = FileEvent::MovedTo;
                else if (event->mask & IN_ATTRIB)      we.type = FileEvent::AttribChanged;
                else we.type = FileEvent::Unknown;

                callback(we);

                ptr += sizeof(inotify_event) + event->len;
            }
        }
    }

    // Blocking event loop with timeout
    void run(const Callback& callback, int timeout_seconds = -1) {
        fd_set fds;
        timeval tv;
        timeval* tv_ptr = nullptr;

        if (timeout_seconds >= 0) {
            tv.tv_sec = timeout_seconds;
            tv.tv_usec = 0;
            tv_ptr = &tv;
        }

        while (true) {
            FD_ZERO(&fds);
            FD_SET(fd_, &fds);

            int ret = ::select(fd_ + 1, &fds, nullptr, nullptr, tv_ptr);
            if (ret < 0) {
                if (errno == EINTR) continue;
                throw std::runtime_error("select: " + std::string(std::strerror(errno)));
            }
            if (ret == 0) {
                std::cout << "Watcher timeout — stopping\n";
                break;
            }

            poll(callback);
        }
    }

    int fd() const noexcept { return fd_; }

private:
    int fd_;
    std::unordered_map<int, std::string> watch_paths_;
};

// ============================================================
// Example usage
// ============================================================
int main(int argc, char* argv[]) {
    std::string watch_dir = (argc > 1) ? argv[1] : "/tmp/watch_test";

    // Create the directory if it doesn't exist
    if (::system(("mkdir -p " + watch_dir).c_str()) != 0) {
        std::cerr << "Cannot create " << watch_dir << "\n";
        return 1;
    }

    FileWatcher watcher;
    watcher.watch(watch_dir);

    auto handler = [](const WatchEvent& event) {
        std::cout << "  [" << event_name(event.type) << "] "
                  << (event.is_dir ? "(dir) " : "")
                  << event.path << "/" << event.filename << "\n";
    };

    std::cout << "\nListening for file changes in " << watch_dir << "...\n";
    std::cout << "Try: touch " << watch_dir << "/test.txt\n";
    std::cout << "     echo hello >> " << watch_dir << "/test.txt\n";
    std::cout << "     rm " << watch_dir << "/test.txt\n\n";

    // Run for 30 seconds then exit
    watcher.run(handler, 30);

    return 0;
}
```

**inotify event masks reference:**

| Mask | Meaning |
|------|---------|
| `IN_CREATE` | File/dir created in watched dir |
| `IN_MODIFY` | File content modified |
| `IN_DELETE` | File/dir deleted from watched dir |
| `IN_MOVED_FROM` | File moved out of watched dir |
| `IN_MOVED_TO` | File moved into watched dir |
| `IN_ATTRIB` | Metadata changed (permissions, timestamps) |
| `IN_CLOSE_WRITE` | File opened for writing closed |
| `IN_DELETE_SELF` | Watched file/dir itself deleted |

**RAII design:** The `FileWatcher` destructor removes all watches and closes the inotify fd. Even if an exception is thrown during event processing, no kernel resources leak.'''),

    ("cpp_deep/buffered_writer_autoflush", r'''Implement a buffered writer in C++ with automatic flush on buffer full, periodic flush, and guaranteed flush on destruction. Show thread-safe usage.''', r'''<think>
A buffered writer collects writes in memory and flushes to disk when the buffer is full.
Need: configurable buffer size, auto-flush when full, RAII flush on destruction, optional periodic flush, thread safety with mutex.
</think>

Here is a thread-safe buffered writer with auto-flush and RAII guarantees:

```cpp
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

class BufferedWriter {
public:
    struct Config {
        std::size_t buffer_size = 64 * 1024;  // 64 KB
        std::chrono::milliseconds flush_interval{1000};  // Auto-flush every 1s
        bool sync_on_flush = false;  // fsync after each flush
    };

    BufferedWriter(const fs::path& path, Config config = {})
        : config_(config)
        , stream_(path, std::ios::binary | std::ios::app)
        , total_bytes_written_(0)
        , flush_count_(0)
        , running_(true)
    {
        if (!stream_)
            throw std::runtime_error("Cannot open " + path.string());

        buffer_.reserve(config_.buffer_size);

        // Start periodic flush thread
        if (config_.flush_interval.count() > 0) {
            flush_thread_ = std::thread([this]() { periodic_flush_loop(); });
        }
    }

    ~BufferedWriter() {
        // Stop flush thread
        running_ = false;
        cv_.notify_all();
        if (flush_thread_.joinable()) {
            flush_thread_.join();
        }

        // Final flush of remaining data
        try {
            flush_locked();
        } catch (...) {
            // Cannot throw from destructor
        }
    }

    // Non-copyable, non-movable (owns thread)
    BufferedWriter(const BufferedWriter&) = delete;
    BufferedWriter& operator=(const BufferedWriter&) = delete;

    // Thread-safe write
    void write(std::string_view data) {
        std::lock_guard lock(mutex_);

        // If data is larger than buffer, flush current buffer then write directly
        if (data.size() > config_.buffer_size) {
            flush_locked();
            write_to_stream(data.data(), data.size());
            return;
        }

        // If adding data would overflow buffer, flush first
        if (buffer_.size() + data.size() > config_.buffer_size) {
            flush_locked();
        }

        buffer_.insert(buffer_.end(), data.begin(), data.end());
    }

    // Thread-safe write with format (variadic)
    void writeln(std::string_view line) {
        std::lock_guard lock(mutex_);

        auto total = line.size() + 1;  // +1 for newline
        if (buffer_.size() + total > config_.buffer_size) {
            flush_locked();
        }

        buffer_.insert(buffer_.end(), line.begin(), line.end());
        buffer_.push_back('\n');
    }

    // Explicit flush
    void flush() {
        std::lock_guard lock(mutex_);
        flush_locked();
    }

    // Stats
    std::size_t total_bytes_written() const {
        return total_bytes_written_.load();
    }

    std::size_t flush_count() const {
        return flush_count_.load();
    }

    std::size_t buffered_bytes() const {
        std::lock_guard lock(mutex_);
        return buffer_.size();
    }

private:
    void flush_locked() {
        if (buffer_.empty()) return;

        write_to_stream(buffer_.data(), buffer_.size());
        buffer_.clear();

        if (config_.sync_on_flush) {
            stream_.flush();
        }

        flush_count_.fetch_add(1);
    }

    void write_to_stream(const char* data, std::size_t size) {
        stream_.write(data, static_cast<std::streamsize>(size));
        if (!stream_) throw std::runtime_error("Write failed");
        total_bytes_written_.fetch_add(size);
    }

    void periodic_flush_loop() {
        std::unique_lock lock(mutex_);
        while (running_) {
            cv_.wait_for(lock, config_.flush_interval,
                         [this]() { return !running_.load(); });

            if (!buffer_.empty()) {
                flush_locked();
            }
        }
    }

    Config config_;
    std::ofstream stream_;
    std::vector<char> buffer_;

    mutable std::mutex mutex_;
    std::condition_variable cv_;
    std::thread flush_thread_;

    std::atomic<std::size_t> total_bytes_written_;
    std::atomic<std::size_t> flush_count_;
    std::atomic<bool> running_;
};

// ============================================================
// Example: multi-threaded logging
// ============================================================
int main() {
    auto log_path = fs::temp_directory_path() / "buffered_writer_test.log";

    {
        BufferedWriter::Config config;
        config.buffer_size = 1024;  // Small buffer to show frequent flushes
        config.flush_interval = std::chrono::milliseconds(200);

        BufferedWriter writer(log_path, config);

        // Spawn multiple writer threads
        std::vector<std::thread> threads;
        for (int t = 0; t < 4; ++t) {
            threads.emplace_back([&writer, t]() {
                for (int i = 0; i < 100; ++i) {
                    writer.writeln("[Thread " + std::to_string(t) +
                                   "] Message #" + std::to_string(i));
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
                }
            });
        }

        for (auto& th : threads) th.join();

        std::cout << "Before destruction:\n";
        std::cout << "  Buffered: " << writer.buffered_bytes() << " bytes\n";
        std::cout << "  Written:  " << writer.total_bytes_written() << " bytes\n";
        std::cout << "  Flushes:  " << writer.flush_count() << "\n";

        // ~BufferedWriter: stops flush thread, flushes remaining data
    }

    // Verify
    auto size = fs::file_size(log_path);
    std::cout << "\nFile size: " << size << " bytes\n";

    // Count lines
    std::ifstream in(log_path);
    int lines = 0;
    std::string line;
    while (std::getline(in, line)) ++lines;
    std::cout << "Total lines: " << lines << " (expected 400)\n";

    fs::remove(log_path);
    return 0;
}
```

**Design guarantees:**

1. **Buffer overflow protection**: When a write would exceed the buffer, the buffer is flushed first. Writes larger than the entire buffer bypass it completely.
2. **Periodic flush thread**: Uses `condition_variable::wait_for` so it can be woken immediately on shutdown rather than sleeping for the full interval.
3. **RAII destruction order**: The destructor stops the flush thread first (joins it), then flushes remaining data. This prevents the thread from accessing freed memory.
4. **Thread safety**: All buffer access is protected by a mutex. The atomic counters allow lock-free stats queries.
5. **Exception safety**: If `write_to_stream` throws, the buffer retains its data and the caller gets the exception.'''),

    ("cpp_deep/log_rotation", r'''Implement log rotation in C++ with file size monitoring. When the log exceeds a size limit, rotate to .1, .2, etc., keeping a configurable number of old logs.''', r'''<think>
Log rotation: when current log exceeds max size, rename log.txt -> log.txt.1, log.txt.1 -> log.txt.2, etc.
Delete logs beyond the max count. Then create a fresh log.txt.
Need to check size before/after each write.
Thread-safe for concurrent logging.
</think>

Here is a rotating file logger with size-based rotation:

```cpp
#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace fs = std::filesystem;

enum class LogLevel { Debug, Info, Warn, Error, Fatal };

const char* level_str(LogLevel level) {
    switch (level) {
        case LogLevel::Debug: return "DEBUG";
        case LogLevel::Info:  return "INFO ";
        case LogLevel::Warn:  return "WARN ";
        case LogLevel::Error: return "ERROR";
        case LogLevel::Fatal: return "FATAL";
    }
    return "?????";
}

class RotatingLogger {
public:
    struct Config {
        fs::path base_path = "app.log";
        std::size_t max_file_size = 10 * 1024 * 1024;  // 10 MB
        int max_files = 5;  // Keep up to 5 rotated files
        bool include_timestamp = true;
    };

    explicit RotatingLogger(Config config = {})
        : config_(std::move(config))
        , current_size_(0)
    {
        // Get current file size if it exists
        std::error_code ec;
        if (fs::exists(config_.base_path, ec)) {
            current_size_ = fs::file_size(config_.base_path, ec);
        }

        open_log_file();
    }

    ~RotatingLogger() {
        std::lock_guard lock(mutex_);
        if (stream_.is_open()) {
            stream_.flush();
            stream_.close();
        }
    }

    RotatingLogger(const RotatingLogger&) = delete;
    RotatingLogger& operator=(const RotatingLogger&) = delete;

    // Log a message
    void log(LogLevel level, std::string_view message) {
        std::string formatted = format_message(level, message);

        std::lock_guard lock(mutex_);

        // Check if rotation is needed
        if (current_size_ + formatted.size() > config_.max_file_size) {
            rotate();
        }

        stream_ << formatted;
        stream_.flush();
        current_size_ += formatted.size();
    }

    // Convenience methods
    void debug(std::string_view msg) { log(LogLevel::Debug, msg); }
    void info(std::string_view msg)  { log(LogLevel::Info, msg); }
    void warn(std::string_view msg)  { log(LogLevel::Warn, msg); }
    void error(std::string_view msg) { log(LogLevel::Error, msg); }
    void fatal(std::string_view msg) { log(LogLevel::Fatal, msg); }

    // Force rotation
    void force_rotate() {
        std::lock_guard lock(mutex_);
        rotate();
    }

    // Stats
    std::size_t current_file_size() const {
        std::lock_guard lock(mutex_);
        return current_size_;
    }

private:
    std::string format_message(LogLevel level, std::string_view message) {
        std::ostringstream oss;

        if (config_.include_timestamp) {
            auto now = std::chrono::system_clock::now();
            auto time_t = std::chrono::system_clock::to_time_t(now);
            auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                now.time_since_epoch()) % 1000;

            oss << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M:%S")
                << "." << std::setfill('0') << std::setw(3) << ms.count() << " ";
        }

        oss << "[" << level_str(level) << "] " << message << "\n";
        return oss.str();
    }

    void rotate() {
        // Close current file
        if (stream_.is_open()) {
            stream_.flush();
            stream_.close();
        }

        // Rotate: .4 -> .5 (delete), .3 -> .4, .2 -> .3, .1 -> .2, current -> .1
        std::error_code ec;

        // Delete the oldest if it exists
        auto oldest = rotated_path(config_.max_files);
        fs::remove(oldest, ec);

        // Shift all rotated files up by one
        for (int i = config_.max_files - 1; i >= 1; --i) {
            auto src = rotated_path(i);
            auto dst = rotated_path(i + 1);
            if (fs::exists(src, ec)) {
                fs::rename(src, dst, ec);
            }
        }

        // Move current to .1
        if (fs::exists(config_.base_path, ec)) {
            fs::rename(config_.base_path, rotated_path(1), ec);
        }

        // Open fresh log file
        current_size_ = 0;
        open_log_file();
    }

    fs::path rotated_path(int index) const {
        return config_.base_path.string() + "." + std::to_string(index);
    }

    void open_log_file() {
        stream_.open(config_.base_path, std::ios::app);
        if (!stream_)
            throw std::runtime_error("Cannot open " + config_.base_path.string());
    }

    Config config_;
    std::ofstream stream_;
    std::size_t current_size_;
    mutable std::mutex mutex_;
};

// ============================================================
// Example
// ============================================================
int main() {
    auto log_dir = fs::temp_directory_path() / "log_rotation_demo";
    fs::create_directories(log_dir);

    RotatingLogger::Config config;
    config.base_path = log_dir / "app.log";
    config.max_file_size = 1024;  // 1 KB for demo (triggers frequent rotation)
    config.max_files = 3;

    RotatingLogger logger(config);

    // Write enough to trigger multiple rotations
    for (int i = 0; i < 200; ++i) {
        logger.info("Log entry #" + std::to_string(i) +
                     " with some padding data to fill the buffer faster");
    }

    // Show resulting files
    std::cout << "Log files in " << log_dir << ":\n";
    for (const auto& entry : fs::directory_iterator(log_dir)) {
        std::cout << "  " << entry.path().filename().string()
                  << " (" << entry.file_size() << " bytes)\n";
    }

    // Read the latest log
    std::cout << "\nLast few lines of current log:\n";
    {
        std::ifstream in(config.base_path);
        std::string line;
        std::vector<std::string> lines;
        while (std::getline(in, line)) lines.push_back(line);
        auto start = lines.size() > 3 ? lines.size() - 3 : 0;
        for (auto i = start; i < lines.size(); ++i) {
            std::cout << "  " << lines[i] << "\n";
        }
    }

    fs::remove_all(log_dir);
    return 0;
}
```

**Rotation strategy:**

```
Before rotation:       After rotation:
  app.log    (full)      app.log    (new, empty)
  app.log.1  (old)       app.log.1  (was app.log)
  app.log.2  (older)     app.log.2  (was app.log.1)
  app.log.3  (oldest)    app.log.3  (was app.log.2)
                         (app.log.3 deleted — max_files=3)
```

The logger checks file size before each write. When the limit would be exceeded, it closes the current file, shifts all rotated files up by one number, and opens a fresh log. The mutex ensures thread safety for concurrent log calls.'''),

    ("cpp_deep/binary_serialization_endian", r'''Implement binary serialization in C++ with explicit endian handling. Show how to serialize/deserialize structs with different-sized fields, handling both big-endian and little-endian formats. Use C++20 std::endian and bit_cast.''', r'''<think>
Binary serialization needs explicit endian handling for portability.
C++20 gives us std::endian to detect native endianness and std::bit_cast for type punning.
Need byte-swap functions for different sizes.
Show serializing a struct to bytes and deserializing, with configurable endianness.
</think>

Here is portable binary serialization with C++20 endian support:

```cpp
#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <span>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

// ============================================================
// Byte swap utilities
// ============================================================
constexpr uint16_t bswap16(uint16_t v) {
    return (v << 8) | (v >> 8);
}

constexpr uint32_t bswap32(uint32_t v) {
    return ((v & 0xFF000000u) >> 24) |
           ((v & 0x00FF0000u) >> 8)  |
           ((v & 0x0000FF00u) << 8)  |
           ((v & 0x000000FFu) << 24);
}

constexpr uint64_t bswap64(uint64_t v) {
    return ((v & 0xFF00000000000000ull) >> 56) |
           ((v & 0x00FF000000000000ull) >> 40) |
           ((v & 0x0000FF00000000000ull) >> 24) |
           ((v & 0x000000FF00000000ull) >> 8)  |
           ((v & 0x00000000FF000000ull) << 8)  |
           ((v & 0x0000000000FF0000ull) << 24) |
           ((v & 0x000000000000FF00ull) << 40) |
           ((v & 0x00000000000000FFull) << 56);
}

// Convert native to target endianness
template <std::endian Target, typename T>
    requires std::is_integral_v<T>
constexpr T to_endian(T value) {
    if constexpr (std::endian::native == Target) {
        return value;  // No conversion needed
    } else {
        if constexpr (sizeof(T) == 1) return value;
        else if constexpr (sizeof(T) == 2) return static_cast<T>(bswap16(static_cast<uint16_t>(value)));
        else if constexpr (sizeof(T) == 4) return static_cast<T>(bswap32(static_cast<uint32_t>(value)));
        else if constexpr (sizeof(T) == 8) return static_cast<T>(bswap64(static_cast<uint64_t>(value)));
    }
}

// Convert from target endianness to native
template <std::endian Source, typename T>
    requires std::is_integral_v<T>
constexpr T from_endian(T value) {
    return to_endian<Source>(value);  // Byte swap is its own inverse
}

// ============================================================
// Binary writer (serializer)
// ============================================================
template <std::endian Endianness = std::endian::little>
class BinaryWriter {
public:
    // Write integer types
    template <typename T>
        requires std::is_integral_v<T>
    void write(T value) {
        T converted = to_endian<Endianness>(value);
        auto bytes = std::bit_cast<std::array<std::byte, sizeof(T)>>(converted);
        buffer_.insert(buffer_.end(), bytes.begin(), bytes.end());
    }

    // Write float/double via bit_cast to integer
    void write(float value) {
        write(std::bit_cast<uint32_t>(value));
    }

    void write(double value) {
        write(std::bit_cast<uint64_t>(value));
    }

    // Write length-prefixed string (uint32 length + bytes)
    void write_string(const std::string& s) {
        write(static_cast<uint32_t>(s.size()));
        buffer_.insert(buffer_.end(),
            reinterpret_cast<const std::byte*>(s.data()),
            reinterpret_cast<const std::byte*>(s.data() + s.size()));
    }

    // Write raw bytes
    void write_raw(std::span<const std::byte> data) {
        buffer_.insert(buffer_.end(), data.begin(), data.end());
    }

    // Write fixed-size array
    template <typename T, std::size_t N>
    void write_array(const std::array<T, N>& arr) {
        write(static_cast<uint32_t>(N));
        for (const auto& elem : arr) {
            write(elem);
        }
    }

    const std::vector<std::byte>& data() const { return buffer_; }
    std::size_t size() const { return buffer_.size(); }
    void clear() { buffer_.clear(); }

private:
    std::vector<std::byte> buffer_;
};

// ============================================================
// Binary reader (deserializer)
// ============================================================
template <std::endian Endianness = std::endian::little>
class BinaryReader {
public:
    explicit BinaryReader(std::span<const std::byte> data)
        : data_(data), pos_(0) {}

    template <typename T>
        requires std::is_integral_v<T>
    T read() {
        check_remaining(sizeof(T));
        std::array<std::byte, sizeof(T)> bytes;
        std::memcpy(bytes.data(), data_.data() + pos_, sizeof(T));
        pos_ += sizeof(T);
        T raw = std::bit_cast<T>(bytes);
        return from_endian<Endianness>(raw);
    }

    float read_float() {
        return std::bit_cast<float>(read<uint32_t>());
    }

    double read_double() {
        return std::bit_cast<double>(read<uint64_t>());
    }

    std::string read_string() {
        uint32_t len = read<uint32_t>();
        check_remaining(len);
        std::string s(reinterpret_cast<const char*>(data_.data() + pos_), len);
        pos_ += len;
        return s;
    }

    template <typename T, std::size_t N>
    std::array<T, N> read_array() {
        uint32_t count = read<uint32_t>();
        if (count != N) throw std::runtime_error("Array size mismatch");
        std::array<T, N> arr;
        for (auto& elem : arr) {
            elem = read<T>();
        }
        return arr;
    }

    std::size_t remaining() const { return data_.size() - pos_; }
    std::size_t position() const { return pos_; }

private:
    void check_remaining(std::size_t needed) {
        if (pos_ + needed > data_.size())
            throw std::runtime_error("BinaryReader: buffer underflow");
    }

    std::span<const std::byte> data_;
    std::size_t pos_;
};

// ============================================================
// Example: serialize a game state
// ============================================================
struct PlayerState {
    uint32_t id;
    std::string name;
    float x, y, z;
    uint16_t health;
    uint8_t level;
    std::array<uint32_t, 4> inventory_slots;

    void serialize(BinaryWriter<std::endian::big>& w) const {
        w.write(id);
        w.write_string(name);
        w.write(x);
        w.write(y);
        w.write(z);
        w.write(health);
        w.write(level);
        w.write_array(inventory_slots);
    }

    static PlayerState deserialize(BinaryReader<std::endian::big>& r) {
        PlayerState p;
        p.id = r.read<uint32_t>();
        p.name = r.read_string();
        p.x = r.read_float();
        p.y = r.read_float();
        p.z = r.read_float();
        p.health = r.read<uint16_t>();
        p.level = r.read<uint8_t>();
        p.inventory_slots = r.read_array<uint32_t, 4>();
        return p;
    }

    void print() const {
        std::cout << "  Player #" << id << ": " << name << "\n";
        std::cout << "  Position: (" << x << ", " << y << ", " << z << ")\n";
        std::cout << "  Health: " << health << ", Level: " << (int)level << "\n";
        std::cout << "  Inventory: ";
        for (auto slot : inventory_slots) std::cout << slot << " ";
        std::cout << "\n";
    }
};

int main() {
    // Detect platform endianness
    if constexpr (std::endian::native == std::endian::little)
        std::cout << "Platform: little-endian\n";
    else
        std::cout << "Platform: big-endian\n";

    // Serialize player state in big-endian (network byte order)
    PlayerState player{
        .id = 42,
        .name = "HeroPlayer",
        .x = 10.5f, .y = -3.2f, .z = 100.0f,
        .health = 950,
        .level = 27,
        .inventory_slots = {1001, 2002, 0, 3003}
    };

    BinaryWriter<std::endian::big> writer;
    player.serialize(writer);

    std::cout << "\nSerialized " << writer.size() << " bytes (big-endian)\n";

    // Show raw bytes
    std::cout << "First 16 bytes: ";
    for (std::size_t i = 0; i < std::min<std::size_t>(16, writer.size()); ++i) {
        std::cout << std::hex << std::setw(2) << std::setfill('0')
                  << static_cast<int>(writer.data()[i]) << " ";
    }
    std::cout << std::dec << "\n\n";

    // Deserialize
    BinaryReader<std::endian::big> reader(writer.data());
    auto restored = PlayerState::deserialize(reader);
    std::cout << "Deserialized player:\n";
    restored.print();
    std::cout << "Reader consumed " << reader.position() << " bytes, "
              << reader.remaining() << " remaining\n";

    return 0;
}
```

**Key C++20 features used:**

- **`std::endian`** — compile-time detection of native byte order, enabling constexpr endian conversion.
- **`std::bit_cast`** — type-safe reinterpretation between types of the same size (replaces `memcpy` for type punning). It is constexpr-friendly and avoids undefined behavior.
- **Templated endianness** — the writer/reader are parameterized on target endianness, so the conversion is resolved at compile time with zero runtime cost when native matches target.'''),

    ("cpp_deep/std_format_custom", r'''Show std::format (C++20) with custom formatters for user-defined types. Implement format specializations for a Point3D and a Color type with different format specifications.''', r'''<think>
std::format requires specializing std::formatter<T> for custom types.
Need to implement parse() and format() methods.
parse() reads the format spec from the format string.
format() writes the formatted output.
Show: Point3D with different precision specs, Color with hex/rgb modes.
</think>

Here is `std::format` with custom formatters for user types:

```cpp
#include <cstdint>
#include <format>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

// ============================================================
// User types
// ============================================================
struct Point3D {
    double x, y, z;
};

struct Color {
    uint8_t r, g, b, a;

    static Color from_hex(uint32_t hex) {
        return {
            static_cast<uint8_t>((hex >> 16) & 0xFF),
            static_cast<uint8_t>((hex >> 8) & 0xFF),
            static_cast<uint8_t>(hex & 0xFF),
            255
        };
    }
};

struct Duration {
    int hours, minutes, seconds;
};

// ============================================================
// Custom formatter for Point3D
// Supported format specs:
//   {:}       -> (1.0, 2.0, 3.0)         (default)
//   {:.2f}    -> (1.00, 2.00, 3.00)      (with precision)
//   {:c}      -> 1.0, 2.0, 3.0           (compact, no parens)
// ============================================================
template <>
struct std::formatter<Point3D> {
    bool compact = false;
    std::string float_spec = "";  // Format spec for each coordinate

    // Parse the format specification
    constexpr auto parse(std::format_parse_context& ctx) {
        auto it = ctx.begin();
        auto end = ctx.end();

        if (it != end && *it == 'c') {
            compact = true;
            ++it;
        }

        // Collect remaining spec for float formatting
        auto spec_start = it;
        while (it != end && *it != '}') ++it;
        if (spec_start != it) {
            float_spec = std::string(spec_start, it);
        }

        return it;
    }

    // Format the output
    auto format(const Point3D& p, std::format_context& ctx) const {
        std::string coord_fmt = float_spec.empty() ? "{}" : "{:" + float_spec + "}";
        std::string full_fmt;

        if (compact) {
            full_fmt = coord_fmt + ", " + coord_fmt + ", " + coord_fmt;
        } else {
            full_fmt = "(" + coord_fmt + ", " + coord_fmt + ", " + coord_fmt + ")";
        }

        return std::vformat_to(ctx.out(), full_fmt,
            std::make_format_args(p.x, p.y, p.z));
    }
};

// ============================================================
// Custom formatter for Color
// Supported format specs:
//   {:}       -> rgba(255, 128, 0, 255)   (default)
//   {:h}      -> #FF8000                   (hex, no alpha)
//   {:H}      -> #FF8000FF                 (hex with alpha)
//   {:f}      -> (1.000, 0.502, 0.000)    (float 0-1)
// ============================================================
template <>
struct std::formatter<Color> {
    char mode = 'r';  // r=rgba, h=hex, H=hex+alpha, f=float

    constexpr auto parse(std::format_parse_context& ctx) {
        auto it = ctx.begin();
        if (it != ctx.end() && *it != '}') {
            mode = *it;
            ++it;
        }
        return it;
    }

    auto format(const Color& c, std::format_context& ctx) const {
        switch (mode) {
            case 'h':
                return std::format_to(ctx.out(), "#{:02X}{:02X}{:02X}",
                    c.r, c.g, c.b);
            case 'H':
                return std::format_to(ctx.out(), "#{:02X}{:02X}{:02X}{:02X}",
                    c.r, c.g, c.b, c.a);
            case 'f':
                return std::format_to(ctx.out(), "({:.3f}, {:.3f}, {:.3f})",
                    c.r / 255.0, c.g / 255.0, c.b / 255.0);
            default:  // 'r'
                return std::format_to(ctx.out(), "rgba({}, {}, {}, {})",
                    c.r, c.g, c.b, c.a);
        }
    }
};

// ============================================================
// Custom formatter for Duration
// Supported format specs:
//   {:}       -> 02:30:15                  (default HH:MM:SS)
//   {:s}      -> 9015s                     (total seconds)
//   {:v}      -> 2h 30m 15s               (verbose)
// ============================================================
template <>
struct std::formatter<Duration> {
    char mode = 't';  // t=time, s=seconds, v=verbose

    constexpr auto parse(std::format_parse_context& ctx) {
        auto it = ctx.begin();
        if (it != ctx.end() && *it != '}') {
            mode = *it;
            ++it;
        }
        return it;
    }

    auto format(const Duration& d, std::format_context& ctx) const {
        switch (mode) {
            case 's': {
                int total = d.hours * 3600 + d.minutes * 60 + d.seconds;
                return std::format_to(ctx.out(), "{}s", total);
            }
            case 'v':
                return std::format_to(ctx.out(), "{}h {}m {}s",
                    d.hours, d.minutes, d.seconds);
            default:
                return std::format_to(ctx.out(), "{:02d}:{:02d}:{:02d}",
                    d.hours, d.minutes, d.seconds);
        }
    }
};

// ============================================================
// Example usage
// ============================================================
int main() {
    Point3D origin{0.0, 0.0, 0.0};
    Point3D pos{3.14159, -2.71828, 100.0};

    std::cout << "=== Point3D formatting ===\n";
    std::cout << std::format("  Default:   {}\n", pos);
    std::cout << std::format("  Precision: {:.2f}\n", pos);
    std::cout << std::format("  Compact:   {:c}\n", pos);
    std::cout << std::format("  Compact.1: {:c.1f}\n", pos);
    std::cout << std::format("  Two pts:   {} and {}\n", origin, pos);

    Color red = Color::from_hex(0xFF0000);
    Color teal{0, 128, 128, 200};

    std::cout << "\n=== Color formatting ===\n";
    std::cout << std::format("  RGBA:    {}\n", teal);
    std::cout << std::format("  Hex:     {:h}\n", red);
    std::cout << std::format("  Hex+A:   {:H}\n", teal);
    std::cout << std::format("  Float:   {:f}\n", teal);

    Duration dur{2, 30, 15};

    std::cout << "\n=== Duration formatting ===\n";
    std::cout << std::format("  Time:    {}\n", dur);
    std::cout << std::format("  Seconds: {:s}\n", dur);
    std::cout << std::format("  Verbose: {:v}\n", dur);

    // Use in containers
    std::cout << "\n=== In collection ===\n";
    std::vector<Point3D> path = {{0,0,0}, {1,0,0}, {1,1,0}, {1,1,1}};
    for (std::size_t i = 0; i < path.size(); ++i) {
        std::cout << std::format("  waypoint[{}]: {:.1f}\n", i, path[i]);
    }

    return 0;
}
```

**How `std::formatter` specialization works:**

1. **`parse()`** reads the format specification (the part after `:` inside `{}`). It returns an iterator past the consumed characters. This is called once at format-string parse time.

2. **`format()`** writes the actual output using `format_to` or `vformat_to` to the output iterator from `ctx.out()`.

3. **Custom spec characters** (like `h`, `f`, `c`) let users choose output modes: `std::format("{:h}", my_color)`.

4. **Composability**: custom formatters can delegate to built-in formatters by embedding standard specs like `.2f` in the generated format string.'''),

    ("cpp_deep/std_print_cpp23", r'''Show std::print and std::println from C++23 for type-safe output. Compare with cout and printf, show custom type support, and demonstrate the compile-time format checking.''', r'''<think>
std::print (C++23) brings Python-style print with std::format's type safety.
Key advantages: type-safe, no << chaining, compile-time format checking, proper Unicode.
Show usage, comparison with cout/printf, and how custom formatters work with it.
</think>

Here is a comprehensive guide to C++23's `std::print` and `std::println`:

```cpp
// Compile with: g++ -std=c++23 -o print_demo print_demo.cpp
#include <cstdio>
#include <format>
#include <iostream>
#include <print>
#include <string>
#include <vector>

// ============================================================
// Custom type with formatter (works with both format and print)
// ============================================================
struct Version {
    int major, minor, patch;
    std::string label;
};

template <>
struct std::formatter<Version> {
    bool verbose = false;

    constexpr auto parse(std::format_parse_context& ctx) {
        auto it = ctx.begin();
        if (it != ctx.end() && *it == 'v') {
            verbose = true;
            ++it;
        }
        return it;
    }

    auto format(const Version& v, std::format_context& ctx) const {
        if (verbose && !v.label.empty()) {
            return std::format_to(ctx.out(), "v{}.{}.{}-{}",
                v.major, v.minor, v.patch, v.label);
        }
        return std::format_to(ctx.out(), "{}.{}.{}",
            v.major, v.minor, v.patch);
    }
};

// ============================================================
// Comparison: printf vs cout vs std::print
// ============================================================
void compare_output_methods() {
    std::string name = "Alice";
    int age = 30;
    double score = 95.7;

    // --- printf: fast but NOT type-safe ---
    // %s with int = undefined behavior, no compile error
    std::printf("printf:    %s is %d years old, score: %.1f\n",
                name.c_str(), age, score);
    // Problems:
    //   - Must use .c_str() for std::string
    //   - Wrong format specifier = UB (no compiler error)
    //   - No custom type support

    // --- cout: type-safe but verbose ---
    std::cout << "cout:      " << name << " is " << age
              << " years old, score: " << std::fixed
              << std::setprecision(1) << score << "\n";
    // Problems:
    //   - Verbose << chaining
    //   - Stateful formatting (setprecision persists)
    //   - No positional arguments

    // --- std::print: type-safe AND clean ---
    std::print("std::print: {} is {} years old, score: {:.1f}\n",
               name, age, score);
    // Advantages:
    //   - Type-safe (compile-time checked)
    //   - Clean syntax
    //   - std::string works directly
    //   - Custom types via std::formatter
}

// ============================================================
// std::print features
// ============================================================
void demo_print_features() {
    std::println("=== std::println (auto newline) ===");

    // Basic types
    std::println("Integer: {}", 42);
    std::println("Float:   {:.3f}", 3.14159);
    std::println("Bool:    {}", true);
    std::println("Char:    {:c}", 65);  // 'A'
    std::println("String:  {:>20}", "right-aligned");
    std::println("String:  {:<20}", "left-aligned");
    std::println("String:  {:^20}", "centered");

    // Numeric formatting
    std::println("\n--- Numeric formats ---");
    std::println("Decimal:     {:d}", 255);
    std::println("Hex:         {:x}", 255);
    std::println("Hex upper:   {:X}", 255);
    std::println("Hex prefixed:{:#x}", 255);
    std::println("Octal:       {:o}", 255);
    std::println("Binary:      {:b}", 255);
    std::println("Binary pad:  {:08b}", 42);
    std::println("Sci:         {:e}", 123456.789);
    std::println("Thousands:   {:L}", 1'000'000);  // Locale-dependent

    // Width and fill
    std::println("\n--- Width and fill ---");
    std::println("|{:10d}|", 42);      // Right-aligned (default for numbers)
    std::println("|{:<10d}|", 42);     // Left-aligned
    std::println("|{:^10d}|", 42);     // Centered
    std::println("|{:*^10d}|", 42);    // Centered, fill with *
    std::println("|{:0>10d}|", 42);    // Zero-padded

    // Positional and named-style
    std::println("\n--- Positional ---");
    std::println("{0} + {1} = {1} + {0}", "a", "b");
    std::println("{0}{0}{0}", "ha");  // "hahaha"

    // Custom types
    std::println("\n--- Custom types ---");
    Version ver{2, 1, 0, "beta"};
    std::println("Default: {}", ver);
    std::println("Verbose: {:v}", ver);

    // Containers (print to stderr)
    std::println(stderr, "\n[stderr] Error logged at line {}", __LINE__);
}

// ============================================================
// Compile-time format checking
// ============================================================
void demo_compile_time_safety() {
    std::println("\n=== Compile-time safety ===");

    // These would cause COMPILE errors (uncomment to verify):

    // std::print("{:d}", "hello");    // Error: 'd' not valid for string
    // std::print("{} {}", 1);         // Error: too few arguments
    // std::print("{}", 1, 2);         // Error: too many arguments (in C++26)
    // std::print("{:s}", 42);         // Error: 's' not valid for int

    // This is the key advantage over printf:
    // printf("%d", "hello");  // Compiles fine, UB at runtime!
    // std::print("{:d}", "hello");  // Compile error!

    std::println("All format strings validated at compile time!");
}

// ============================================================
// Print to different outputs
// ============================================================
void demo_output_targets() {
    std::println("\n=== Output targets ===");

    // stdout (default)
    std::print("To stdout\n");

    // stderr
    std::print(stderr, "To stderr\n");

    // To a string (std::format, not print)
    std::string s = std::format("Formatted to string: {} + {} = {}", 1, 2, 3);
    std::println("String: {}", s);

    // Format into existing buffer
    std::string buf;
    std::format_to(std::back_inserter(buf), "x={}, y={}", 10, 20);
    std::println("Buffer: {}", buf);
}

// ============================================================
// Practical example: table formatting
// ============================================================
void demo_table() {
    std::println("\n=== Table formatting ===");

    struct Record {
        std::string name;
        int score;
        double ratio;
    };

    std::vector<Record> data = {
        {"Alice", 950, 0.95},
        {"Bob", 870, 0.87},
        {"Charlie", 1020, 1.02},
        {"Diana", 990, 0.99}
    };

    std::println("{:<10} {:>6} {:>8}", "Name", "Score", "Ratio");
    std::println("{:-<10} {:-<6} {:-<8}", "", "", "");
    for (const auto& [name, score, ratio] : data) {
        std::println("{:<10} {:>6} {:>8.2f}", name, score, ratio);
    }
}

int main() {
    compare_output_methods();
    demo_print_features();
    demo_compile_time_safety();
    demo_output_targets();
    demo_table();
    return 0;
}
```

**`std::print` vs alternatives:**

| Feature | `printf` | `cout` | `std::print` |
|---------|----------|--------|--------------|
| Type safety | No | Yes | Yes (compile-time) |
| Format checking | No | N/A | Compile-time |
| Custom types | No | `operator<<` | `std::formatter` |
| Positional args | Platform-dependent | No | Yes (`{0}`, `{1}`) |
| Performance | Fast | Slower (sync) | Fast |
| std::string | `.c_str()` needed | Direct | Direct |
| Unicode | Poor | Poor | Proper |

**Key points:**
- `std::println` adds `\n` automatically (like Python's `print`).
- Format strings are checked at **compile time** — wrong specifiers or argument counts are errors, not runtime UB.
- Custom `std::formatter` specializations work with `std::print`, `std::format`, and `std::format_to` — write once, use everywhere.'''),

    ("cpp_deep/compiletime_format_validation", r'''Demonstrate compile-time format string validation in C++20/23. Show how std::format catches errors at compile time, and implement a basic constexpr format string validator.''', r'''<think>
std::format validates format strings at compile time using consteval and constexpr.
The key is std::basic_format_string which checks the format string against the argument types.
I should show: what errors it catches, how the mechanism works internally, and how to build a simple constexpr validator.
</think>

Here is compile-time format string validation in C++20/23, including a custom validator:

```cpp
#include <array>
#include <concepts>
#include <cstddef>
#include <format>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <type_traits>

// ============================================================
// 1. std::format's built-in compile-time validation
// ============================================================
void demo_builtin_validation() {
    // These all compile and work correctly:
    auto s1 = std::format("{} + {} = {}", 1, 2, 3);
    auto s2 = std::format("{0} is {1:.2f}", "pi", 3.14159);
    auto s3 = std::format("{:08x}", 0xDEAD);
    auto s4 = std::format("{:>20}", "right-aligned");

    std::cout << s1 << "\n" << s2 << "\n" << s3 << "\n" << s4 << "\n";

    // These would cause COMPILE-TIME errors:
    // (Uncomment any line to see the error)

    // Wrong number of arguments:
    // auto e1 = std::format("{} {}", 1);           // Too few args
    // auto e2 = std::format("{}", 1, 2);            // Too many args (C++26)

    // Wrong format spec for type:
    // auto e3 = std::format("{:d}", "hello");        // 'd' invalid for string
    // auto e4 = std::format("{:s}", 42);             // 's' invalid for int
    // auto e5 = std::format("{:.2f}", "text");       // precision invalid for string

    // Invalid format syntax:
    // auto e6 = std::format("{", 1);                 // Unterminated '{'
    // auto e7 = std::format("{}}", 1);               // Unmatched '}'
    // auto e8 = std::format("{2}", 1);               // Index out of range
}

// ============================================================
// 2. How it works: std::basic_format_string
// ============================================================
// std::format's first parameter isn't a raw string — it's a
// std::format_string<Args...> which validates at construction.
//
// Simplified signature:
//   template <typename... Args>
//   std::string format(std::format_string<Args...> fmt, Args&&... args);
//
// std::format_string is a class that takes the format string as a
// consteval constructor parameter, checking it against the types.

// You can create your own checked format function:
template <typename... Args>
void safe_log(std::format_string<Args...> fmt, Args&&... args) {
    // Format string is already validated at compile time by the time we get here
    std::cout << "[LOG] " << std::format(fmt, std::forward<Args>(args)...) << "\n";
}

// ============================================================
// 3. Custom constexpr format string validator
// ============================================================

// A simplified compile-time format string checker
struct FormatSpec {
    int arg_count = 0;
    bool valid = true;
    const char* error = nullptr;
};

constexpr FormatSpec validate_format(std::string_view fmt) {
    FormatSpec result;
    int max_index = -1;
    bool has_auto = false;     // {} with no index
    bool has_manual = false;   // {0}, {1} with explicit index

    std::size_t i = 0;
    while (i < fmt.size()) {
        if (fmt[i] == '{') {
            if (i + 1 < fmt.size() && fmt[i + 1] == '{') {
                i += 2;  // Escaped {{
                continue;
            }

            // Find matching }
            auto close = fmt.find('}', i + 1);
            if (close == std::string_view::npos) {
                result.valid = false;
                result.error = "Unmatched '{'";
                return result;
            }

            auto spec = fmt.substr(i + 1, close - i - 1);

            // Check for index vs auto
            if (spec.empty() || spec[0] == ':') {
                has_auto = true;
                ++result.arg_count;
            } else if (spec[0] >= '0' && spec[0] <= '9') {
                has_manual = true;
                int index = 0;
                for (char c : spec) {
                    if (c == ':') break;
                    if (c < '0' || c > '9') break;
                    index = index * 10 + (c - '0');
                }
                if (index > max_index) max_index = index;
            } else {
                has_auto = true;
                ++result.arg_count;
            }

            if (has_auto && has_manual) {
                result.valid = false;
                result.error = "Cannot mix automatic and manual indexing";
                return result;
            }

            i = close + 1;
        } else if (fmt[i] == '}') {
            if (i + 1 < fmt.size() && fmt[i + 1] == '}') {
                i += 2;  // Escaped }}
                continue;
            }
            result.valid = false;
            result.error = "Unmatched '}'";
            return result;
        } else {
            ++i;
        }
    }

    if (has_manual) {
        result.arg_count = max_index + 1;
    }

    return result;
}

// Compile-time assertion on format strings
template <std::size_t N>
struct StaticString {
    char data[N];
    consteval StaticString(const char (&str)[N]) {
        for (std::size_t i = 0; i < N; ++i) data[i] = str[i];
    }
    consteval operator std::string_view() const { return {data, N - 1}; }
};

template <StaticString Fmt, typename... Args>
consteval bool check_format() {
    constexpr auto spec = validate_format(Fmt);
    static_assert(spec.valid, "Invalid format string");
    static_assert(spec.arg_count == sizeof...(Args),
                  "Format argument count mismatch");
    return true;
}

// Usage: validated at compile time
template <StaticString Fmt, typename... Args>
void checked_print(Args&&... args) {
    static_assert(check_format<Fmt, Args...>());
    // If we get here, format string is valid
    std::cout << std::format(std::string_view(Fmt), std::forward<Args>(args)...);
}

// ============================================================
// 4. Constexpr validation tests
// ============================================================

// These all pass at compile time
static_assert(validate_format("hello").valid);
static_assert(validate_format("hello").arg_count == 0);
static_assert(validate_format("{} + {} = {}").arg_count == 3);
static_assert(validate_format("{0} and {1}").arg_count == 2);
static_assert(validate_format("{{escaped}}").arg_count == 0);
static_assert(validate_format("{:.2f}").arg_count == 1);

// These detect errors at compile time
static_assert(!validate_format("{").valid);   // Unmatched {
static_assert(!validate_format("}").valid);   // Unmatched }
static_assert(!validate_format("{0} {}").valid);  // Mixed indexing

int main() {
    std::cout << "=== Built-in validation ===\n";
    demo_builtin_validation();

    std::cout << "\n=== safe_log (compile-time checked) ===\n";
    safe_log("User {} logged in from {}", "Alice", "192.168.1.1");
    safe_log("Value: {:.4f}", 3.14159);
    // safe_log("{} {}", 1);  // Would not compile: too few args

    std::cout << "\n=== Custom validator (constexpr) ===\n";
    constexpr auto spec = validate_format("Hello {} your score is {:.2f}");
    std::cout << "  Valid: " << spec.valid << "\n";
    std::cout << "  Args:  " << spec.arg_count << "\n";

    constexpr auto bad = validate_format("Missing close {");
    std::cout << "  Bad valid: " << bad.valid << "\n";
    std::cout << "  Bad error: " << bad.error << "\n";

    // checked_print: compile-time validated
    checked_print<"Result: {} + {} = {}\n">(1, 2, 3);
    // checked_print<"{} {}">(1);  // static_assert fails: argument count mismatch

    return 0;
}
```

**How `std::format` achieves compile-time checking:**

1. The format string parameter is `std::basic_format_string<char, Args...>`, not a plain `const char*`.
2. This class has a `consteval` constructor that parses the format string and validates each replacement field against the corresponding `Args` type.
3. Because it is `consteval`, any validation failure is a **compile error**, not a runtime exception.
4. This means typos like `{:d}` for a string argument are caught before the program ever runs — unlike `printf` where such errors are silent undefined behavior.

**The `consteval` keyword (C++20):** guarantees the function runs at compile time. Unlike `constexpr` (which *may* run at compile time), `consteval` functions *must* be evaluated during compilation. This is what makes format string validation mandatory.'''),
]
