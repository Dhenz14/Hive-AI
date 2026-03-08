"""C++ deep reasoning pairs batch 3: concurrency and parallelism."""
PAIRS = [
    ("cpp_deep/thread_scope_guard", r'''How do I ensure std::thread is always joined even if an exception is thrown? I keep getting std::terminate crashes.''', r'''<think>
The problem is that if an exception is thrown between thread creation and the join() call,
the thread destructor fires on a joinable thread, which calls std::terminate(). This is a
classic RAII problem. We need a scope guard that joins (or detaches) in its destructor.

Pre-C++20, we must write our own scope guard or use a wrapper class. Post-C++20, std::jthread
handles this automatically, but the user is asking about std::thread specifically.

The scope guard approach: wrap the thread in a class whose destructor calls join(). We need
to handle move semantics properly — the guard should be non-copyable but movable. Actually,
simpler: just make a non-copyable, non-movable guard that takes a reference to the thread.

We should also consider: what if join() itself throws? In practice join() can throw
std::system_error if the thread is not joinable, so we check joinable() first.

Alternative approach: a generic scope_exit guard that takes a callable. This is more
flexible and mirrors the Guideline Support Library (GSL) finally() pattern. Let me show
both approaches — a dedicated ThreadGuard and a generic scope_exit.

The generic scope_exit is more idiomatic modern C++ and can be used for any cleanup.
We should use noexcept on the destructor lambda capture to be safe.

Edge cases: if the thread was default-constructed (not joinable), join would be wrong.
Always check joinable() before calling join(). Also, if someone moves the thread out
from under us, the guard must handle that gracefully.
</think>

When a `std::thread` object is destroyed while still joinable, `std::terminate()` is called. You need RAII to guarantee `join()` happens even during stack unwinding. Here are two approaches:

**Approach 1: Dedicated ThreadGuard**

```cpp
#include <thread>
#include <stdexcept>
#include <iostream>

class ThreadGuard {
    std::thread& t_;
public:
    explicit ThreadGuard(std::thread& t) : t_(t) {}

    ~ThreadGuard() {
        if (t_.joinable()) {
            t_.join();
        }
    }

    // Non-copyable, non-movable — it references an external thread
    ThreadGuard(const ThreadGuard&) = delete;
    ThreadGuard& operator=(const ThreadGuard&) = delete;
};

void do_work() {
    std::cout << "Worker thread running\n";
}

void risky_function() {
    std::thread worker(do_work);
    ThreadGuard guard(worker);  // join guaranteed in destructor

    // Simulate work that might throw
    throw std::runtime_error("something went wrong");

    // Without the guard, worker's destructor would call std::terminate
}

int main() {
    try {
        risky_function();
    } catch (const std::exception& e) {
        std::cout << "Caught: " << e.what() << "\n";
        std::cout << "Thread was safely joined before unwinding\n";
    }
    return 0;
}
```

**Approach 2: Generic scope_exit (GSL-style)**

```cpp
#include <thread>
#include <iostream>
#include <stdexcept>
#include <utility>

template<typename F>
class scope_exit {
    F func_;
    bool active_;
public:
    explicit scope_exit(F f) : func_(std::move(f)), active_(true) {}

    ~scope_exit() {
        if (active_) func_();
    }

    void dismiss() { active_ = false; }

    scope_exit(scope_exit&& other) noexcept
        : func_(std::move(other.func_)), active_(other.active_) {
        other.dismiss();
    }

    scope_exit(const scope_exit&) = delete;
    scope_exit& operator=(const scope_exit&) = delete;
    scope_exit& operator=(scope_exit&&) = delete;
};

template<typename F>
scope_exit<F> make_scope_exit(F f) {
    return scope_exit<F>(std::move(f));
}

int main() {
    std::thread worker([] {
        std::cout << "Worker doing work\n";
    });

    auto guard = make_scope_exit([&worker] {
        if (worker.joinable()) worker.join();
    });

    // Any exception here is safe — guard joins in destructor
    std::cout << "Main thread doing risky stuff\n";

    return 0;
}
```

The `ThreadGuard` is simpler for the single-purpose case. The `scope_exit` is reusable for any cleanup (file handles, locks, etc.). In C++20, prefer `std::jthread` which does this automatically.'''),

    ("cpp_deep/jthread_stop_token", r'''Can you show me how std::jthread cooperative cancellation works with stop_token? I want a worker thread that periodically checks if it should stop.''', r'''<think>
std::jthread (C++20) solves two problems: automatic join in destructor, and cooperative
cancellation via stop_token/stop_source. When the jthread is destroyed or when
request_stop() is called on its stop_source, the associated stop_token signals.

The worker function can accept a std::stop_token as its first parameter — jthread
automatically passes it. The worker then checks stop_token::stop_requested() periodically.

Key points to cover:
- jthread destructor calls request_stop() then join()
- stop_callback allows registering a callback when stop is requested
- stop_token is thread-safe to query from the worker
- The worker must cooperate — it's not forced termination
- stop_callback is useful for waking up blocked threads (e.g., unblocking a condition_variable)

I should show a practical example: a worker that does periodic work and checks the token,
plus a stop_callback example where we wake a sleeping thread.

For the condition_variable integration, std::condition_variable_any can work with
stop_token directly via its wait() overload that takes a stop_token. This is the
cleanest pattern for interruptible waits.

Let me also show how to manually get the stop_source from the jthread to request
early cancellation without destroying the jthread object.
</think>

`std::jthread` (C++20) provides built-in cooperative cancellation. The thread function receives a `std::stop_token` as its first parameter, and the `jthread` destructor automatically calls `request_stop()` then `join()`.

```cpp
#include <iostream>
#include <thread>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <vector>

using namespace std::chrono_literals;

// --- Example 1: Simple periodic worker with stop_token ---
void periodic_worker(std::stop_token stoken, int id) {
    int iteration = 0;
    while (!stoken.stop_requested()) {
        std::cout << "Worker " << id << " iteration " << ++iteration << "\n";
        std::this_thread::sleep_for(200ms);
    }
    std::cout << "Worker " << id << " received stop signal, cleaning up\n";
}

// --- Example 2: Interruptible wait with stop_callback ---
class InterruptibleQueue {
    std::mutex mtx_;
    std::condition_variable_any cv_;
    std::vector<int> data_;

public:
    void push(int value) {
        {
            std::lock_guard lock(mtx_);
            data_.push_back(value);
        }
        cv_.notify_one();
    }

    // Blocks until data available OR stop requested
    bool pop(int& out, std::stop_token stoken) {
        std::unique_lock lock(mtx_);
        // condition_variable_any::wait with stop_token (C++20)
        if (!cv_.wait(lock, stoken, [this] { return !data_.empty(); })) {
            // Returned false means stop was requested
            return false;
        }
        out = data_.back();
        data_.pop_back();
        return true;
    }
};

// --- Example 3: Manual stop_callback for custom wakeup ---
void callback_demo(std::stop_token stoken) {
    std::mutex mtx;
    std::condition_variable cv;
    bool ready = false;

    // Register callback: when stop is requested, wake up the cv
    std::stop_callback on_stop(stoken, [&] {
        {
            std::lock_guard lock(mtx);
            ready = true;
        }
        cv.notify_one();
    });

    std::unique_lock lock(mtx);
    cv.wait(lock, [&] { return ready; });
    std::cout << "callback_demo woke up due to stop request\n";
}

int main() {
    // Example 1: periodic worker, auto-cancelled on scope exit
    {
        std::cout << "=== Periodic worker ===\n";
        std::jthread t1(periodic_worker, 1);
        std::this_thread::sleep_for(1s);
        // t1 destructor calls request_stop() then join()
    }
    std::cout << "\n";

    // Example 2: interruptible queue consumer
    {
        std::cout << "=== Interruptible queue ===\n";
        InterruptibleQueue queue;

        std::jthread consumer([&](std::stop_token stoken) {
            int value;
            while (queue.pop(value, stoken)) {
                std::cout << "Consumed: " << value << "\n";
            }
            std::cout << "Consumer stopped\n";
        });

        queue.push(10);
        queue.push(20);
        std::this_thread::sleep_for(100ms);
        // Request early stop without destroying jthread
        consumer.request_stop();
        consumer.join();
    }
    std::cout << "\n";

    // Example 3: stop_callback
    {
        std::cout << "=== Stop callback ===\n";
        std::jthread t3(callback_demo);
        std::this_thread::sleep_for(500ms);
        t3.request_stop();
    }

    return 0;
}
```

Compile with: `g++ -std=c++20 -pthread -o jthread_demo jthread_demo.cpp`

Key design points:
- **`stop_token::stop_requested()`** is lock-free and thread-safe
- **`stop_callback`** fires immediately if stop was already requested before registration
- **`condition_variable_any::wait(lock, stoken, pred)`** is the cleanest pattern for interruptible blocking
- The jthread destructor order is: `request_stop()` first, then `join()` — so the worker sees the signal before the join blocks'''),

    ("cpp_deep/async_launch_policies", r'''What is the difference between std::async with std::launch::async vs std::launch::deferred? When should I use each? I find the default behavior confusing.''', r'''<think>
This is a common source of confusion. std::async has three launch modes:
1. std::launch::async — guaranteed to run on a new thread
2. std::launch::deferred — lazy evaluation, runs on calling thread when get()/wait() called
3. std::launch::async | std::launch::deferred — the default, implementation chooses

The default (async|deferred) is the problem: you don't know if the task actually launched.
This has consequences:
- If deferred, thread_local variables refer to the calling thread's TLS
- If deferred, the task never runs unless you call get()/wait()
- If deferred, wait_for()/wait_until() always return std::future_status::deferred
- Loops checking wait_for() will spin forever if the task was deferred

Scott Meyers (Effective Modern C++) recommends: either explicitly specify the policy,
or use a wrapper that detects deferred and handles it.

When to use async: you want true parallelism, fire-and-forget with result collection.
When to use deferred: lazy evaluation, compute-on-demand, memoization patterns.

I should show the gotcha with default policy + wait_for loop, and a safe wrapper.
Also worth noting: std::async with launch::async guarantees the future's destructor
will block (join), which is both a feature and a gotcha.

The blocking destructor of futures from async is unique — futures from promise/packaged_task
don't block. This only applies to shared state from std::async with async policy.
</think>

The confusion around `std::async` launch policies is well-documented. Here is a complete breakdown with examples showing the gotchas:

```cpp
#include <future>
#include <iostream>
#include <thread>
#include <chrono>

using namespace std::chrono_literals;

int compute(int x) {
    std::cout << "  Running on thread: " << std::this_thread::get_id() << "\n";
    std::this_thread::sleep_for(500ms);
    return x * x;
}

// --- Gotcha: default policy with wait_for loop ---
void default_policy_gotcha() {
    std::cout << "=== Default policy gotcha ===\n";
    auto fut = std::async(compute, 42);  // default: async | deferred

    // This loop may NEVER terminate if implementation chose deferred!
    // wait_for on a deferred task always returns future_status::deferred
    auto status = fut.wait_for(0ms);
    if (status == std::future_status::deferred) {
        std::cout << "  Task was deferred — calling get() to execute\n";
        std::cout << "  Result: " << fut.get() << "\n";
    } else {
        // Either ready or still running
        std::cout << "  Task launched async, result: " << fut.get() << "\n";
    }
}

// --- Explicit async: guaranteed new thread ---
void explicit_async() {
    std::cout << "\n=== launch::async ===\n";
    std::cout << "Main thread: " << std::this_thread::get_id() << "\n";

    auto fut = std::async(std::launch::async, compute, 7);
    // Guaranteed to run on a different thread
    std::cout << "Result: " << fut.get() << "\n";
    // NOTE: if you discard the future, its destructor blocks (joins)!
}

// --- Explicit deferred: lazy evaluation ---
void explicit_deferred() {
    std::cout << "\n=== launch::deferred (lazy) ===\n";
    std::cout << "Main thread: " << std::this_thread::get_id() << "\n";

    auto fut = std::async(std::launch::deferred, compute, 5);
    std::cout << "Task not running yet...\n";
    std::this_thread::sleep_for(1s);
    std::cout << "Now calling get() — runs on THIS thread:\n";
    std::cout << "Result: " << fut.get() << "\n";
}

// --- Safe wrapper (Scott Meyers pattern) ---
template<typename F, typename... Args>
auto real_async(F&& f, Args&&... args) {
    return std::async(std::launch::async,
                      std::forward<F>(f),
                      std::forward<Args>(args)...);
}

// --- Deferred for memoization / compute-on-demand ---
class LazyValue {
    std::shared_future<int> value_;
public:
    LazyValue(int input)
        : value_(std::async(std::launch::deferred, [input] {
            std::cout << "  Computing (only once)...\n";
            return input * input * input;
        }).share()) {}

    int get() const { return value_.get(); }
};

void memoization_demo() {
    std::cout << "\n=== Deferred for memoization ===\n";
    LazyValue lazy(10);
    std::cout << "LazyValue created, not computed yet\n";
    std::cout << "First access: " << lazy.get() << "\n";
    std::cout << "Second access: " << lazy.get() << "\n";  // cached
}

// --- Blocking destructor gotcha ---
void blocking_destructor_demo() {
    std::cout << "\n=== Blocking destructor ===\n";
    {
        // This future is discarded — destructor blocks until task completes!
        auto ignored = std::async(std::launch::async, [] {
            std::this_thread::sleep_for(2s);
            std::cout << "  Async task done (destructor waited for me)\n";
        });
        std::cout << "About to leave scope...\n";
    } // blocks here for ~2 seconds
    std::cout << "Scope exited\n";
}

int main() {
    default_policy_gotcha();
    explicit_async();
    explicit_deferred();
    memoization_demo();
    blocking_destructor_demo();
    return 0;
}
```

**Guidelines:**
- Use `std::launch::async` when you need true parallelism
- Use `std::launch::deferred` for lazy/memoized computation
- **Avoid the default policy** — it makes behavior unpredictable
- Remember: `std::async` futures block in their destructor (unique to async, not promise/packaged_task)'''),

    ("cpp_deep/promise_future_oneshot", r'''Show me how to use std::promise and std::future together for passing a result from a worker thread back to the main thread. When would I prefer this over std::async?''', r'''<think>
std::promise/std::future provide a one-shot communication channel between threads.
The promise is the "write" end, the future is the "read" end. Unlike std::async,
you manage the thread yourself, which gives you more control.

When to prefer promise/future over async:
1. When you need the thread to exist before setting the result (long-lived worker)
2. When you want to set a result OR an exception explicitly
3. When the thread does multiple things and the result is just one part
4. When you need to detach the thread (async futures block on destruction)
5. When you want to pass the result to a different thread than the one that created it

Important points:
- Setting a promise twice throws std::future_error
- If the promise is destroyed without setting a value, the future gets a broken_promise exception
- get() on the future blocks until the promise is fulfilled
- A future can only be get()'d once (use shared_future for multiple reads)
- promise::set_value_at_thread_exit() delays visibility until thread exits

I should show: basic usage, exception propagation, and the broken_promise case.
Also show a practical pattern like a thread that signals "ready" via a promise
and then continues doing work.

The "thread ready" signal pattern is particularly useful — it's a one-shot gate
that lets the main thread know the worker has initialized.
</think>

`std::promise`/`std::future` give you a one-shot channel where you control the thread yourself. This is more flexible than `std::async` when the thread has a longer lifecycle or when you need explicit control.

```cpp
#include <iostream>
#include <thread>
#include <future>
#include <stdexcept>
#include <chrono>
#include <string>

using namespace std::chrono_literals;

// --- Basic: worker sends result back via promise ---
void basic_example() {
    std::cout << "=== Basic promise/future ===\n";

    std::promise<int> prom;
    std::future<int> fut = prom.get_future();  // one future per promise

    std::thread worker([p = std::move(prom)]() mutable {
        std::this_thread::sleep_for(500ms);  // simulate work
        p.set_value(42);
        // Thread can continue doing other work after setting the value
        std::this_thread::sleep_for(200ms);
        std::cout << "  Worker finishing extra work\n";
    });

    std::cout << "  Waiting for result...\n";
    int result = fut.get();  // blocks until promise is set
    std::cout << "  Got: " << result << "\n";

    worker.join();
}

// --- Exception propagation through promise ---
void exception_example() {
    std::cout << "\n=== Exception propagation ===\n";

    std::promise<std::string> prom;
    auto fut = prom.get_future();

    std::thread worker([p = std::move(prom)]() mutable {
        try {
            // Simulate failure
            throw std::runtime_error("database connection failed");
        } catch (...) {
            // Propagate exception to the waiting thread
            p.set_exception(std::current_exception());
        }
    });

    try {
        std::string result = fut.get();  // rethrows the exception
    } catch (const std::exception& e) {
        std::cout << "  Caught from worker: " << e.what() << "\n";
    }

    worker.join();
}

// --- Broken promise (destroyed without setting value) ---
void broken_promise_example() {
    std::cout << "\n=== Broken promise ===\n";

    std::future<int> fut;
    {
        std::promise<int> prom;
        fut = prom.get_future();
        // prom destroyed here without set_value or set_exception
    }

    try {
        fut.get();
    } catch (const std::future_error& e) {
        std::cout << "  Caught: " << e.what() << "\n";
        // e.code() == std::future_errc::broken_promise
    }
}

// --- Practical pattern: "thread ready" gate ---
void ready_gate_pattern() {
    std::cout << "\n=== Ready gate pattern ===\n";

    std::promise<void> ready_promise;  // void promise = pure signal
    auto ready_future = ready_promise.get_future();

    std::thread server([p = std::move(ready_promise)]() mutable {
        // Simulate server initialization
        std::this_thread::sleep_for(300ms);
        std::cout << "  Server initialized, signaling ready\n";
        p.set_value();  // signal "ready"

        // Continue serving
        std::this_thread::sleep_for(500ms);
        std::cout << "  Server shutting down\n";
    });

    std::cout << "  Waiting for server to be ready...\n";
    ready_future.get();  // blocks until server signals
    std::cout << "  Server is ready, proceeding\n";

    server.join();
}

// --- set_value_at_thread_exit: delays visibility ---
void at_thread_exit_example() {
    std::cout << "\n=== set_value_at_thread_exit ===\n";

    std::promise<int> prom;
    auto fut = prom.get_future();

    std::thread([p = std::move(prom)]() mutable {
        // Value becomes visible only when thread exits,
        // guaranteeing all thread-local destructors have run
        p.set_value_at_thread_exit(99);
        std::cout << "  Value set (but not visible yet)\n";
        std::this_thread::sleep_for(300ms);
        std::cout << "  Thread about to exit\n";
    }).detach();

    std::cout << "  Result: " << fut.get() << "\n";
}

int main() {
    basic_example();
    exception_example();
    broken_promise_example();
    ready_gate_pattern();
    at_thread_exit_example();

    std::this_thread::sleep_for(500ms);  // let detached thread finish
    return 0;
}
```

**When to prefer promise/future over async:**
- Thread does initialization then long-lived work (ready gate pattern)
- You need explicit exception propagation control
- Thread is detached (async futures block in destructor)
- You want to separate "set result" from "thread lifetime"
- Multiple stages of work where the result is an intermediate product'''),

    ("cpp_deep/shared_future_multiple_consumers", r'''I need multiple threads to wait on the same result. std::future can only be get()'d once. What is the correct pattern?''', r'''<think>
std::future is move-only and get() can only be called once — it moves the value out.
std::shared_future is the solution: it's copyable and get() returns a const reference,
so multiple threads can call get() on their own copy.

Creation: either std::future::share() or construct shared_future from a moved future.
Each thread should have its own copy of the shared_future (not a reference to one).

Key differences from std::future:
- get() returns const T& (not T&&), so it doesn't move the value
- Copyable — each thread gets its own copy
- Multiple get() calls are fine, all return the same value
- Thread-safe to call get() on different copies concurrently
- NOT thread-safe to call get() on the SAME shared_future from multiple threads

That last point is subtle and important. Each thread must have its own shared_future
copy. The shared state is thread-safe, but the shared_future object itself is not.

Practical use case: a config/initialization result that multiple worker threads need.
Another: fan-out pattern where one producer feeds many consumers.

I should show the correct copy pattern and warn about the shared access pitfall.
Also show how this works with promise for a realistic initialization broadcast.
</think>

`std::shared_future` is the answer — it is copyable and `get()` returns `const T&`, allowing multiple threads to safely read the same result. The key is that **each thread must own its own copy**.

```cpp
#include <iostream>
#include <thread>
#include <future>
#include <vector>
#include <string>
#include <chrono>

using namespace std::chrono_literals;

// --- Example 1: Multiple consumers waiting on one result ---
void fan_out_example() {
    std::cout << "=== Fan-out: one producer, many consumers ===\n";

    std::promise<std::string> config_promise;
    // .share() converts future<T> to shared_future<T>
    std::shared_future<std::string> config = config_promise.get_future().share();

    // Launch multiple consumer threads, each with its OWN COPY of shared_future
    std::vector<std::thread> consumers;
    for (int i = 0; i < 5; ++i) {
        consumers.emplace_back([config, i]() {  // config COPIED into lambda
            // All threads block here until producer sets the value
            const std::string& cfg = config.get();  // returns const T&
            std::cout << "  Consumer " << i << " got config: " << cfg << "\n";
        });
    }

    // Simulate slow initialization
    std::this_thread::sleep_for(500ms);
    config_promise.set_value("database_url=localhost:5432");

    for (auto& t : consumers) t.join();
}

// --- Example 2: Initialization barrier (real-world pattern) ---
struct ServiceConfig {
    std::string db_host;
    int port;
    bool debug;
};

class Application {
    std::shared_future<ServiceConfig> config_;

public:
    explicit Application(std::shared_future<ServiceConfig> config)
        : config_(std::move(config)) {}

    void run_web_server() {
        const auto& cfg = config_.get();  // blocks until config ready
        std::cout << "  Web server using " << cfg.db_host
                  << ":" << cfg.port << "\n";
    }

    void run_worker() {
        const auto& cfg = config_.get();  // same config, safe to call again
        std::cout << "  Worker debug=" << std::boolalpha
                  << cfg.debug << "\n";
    }

    void run_monitor() {
        const auto& cfg = config_.get();
        std::cout << "  Monitor connected to " << cfg.db_host << "\n";
    }
};

void initialization_barrier_example() {
    std::cout << "\n=== Initialization barrier ===\n";

    std::promise<ServiceConfig> config_promise;
    auto config_future = config_promise.get_future().share();

    Application app(config_future);

    // Start all services — they all wait on config
    std::thread t1([&app] { app.run_web_server(); });
    std::thread t2([&app] { app.run_worker(); });
    std::thread t3([&app] { app.run_monitor(); });

    // Load config (simulated delay)
    std::this_thread::sleep_for(300ms);
    config_promise.set_value({"prod-db.example.com", 5432, false});

    t1.join(); t2.join(); t3.join();
}

// --- WRONG: sharing a reference to one shared_future ---
void show_wrong_pattern() {
    std::cout << "\n=== WRONG vs RIGHT ===\n";

    std::promise<int> prom;
    std::shared_future<int> sf = prom.get_future().share();
    prom.set_value(42);

    // WRONG: multiple threads accessing the SAME shared_future object
    // std::thread t1([&sf]() { sf.get(); });  // DATA RACE on sf
    // std::thread t2([&sf]() { sf.get(); });  // DATA RACE on sf

    // RIGHT: each thread gets its own copy
    std::thread t1([sf]() { std::cout << "  t1: " << sf.get() << "\n"; });
    std::thread t2([sf]() { std::cout << "  t2: " << sf.get() << "\n"; });

    t1.join(); t2.join();
}

int main() {
    fan_out_example();
    initialization_barrier_example();
    show_wrong_pattern();
    return 0;
}
```

**Critical rule:** each thread must own a **copy** of the `shared_future`, not a reference. The shared state is thread-safe; the `shared_future` object wrapper is not. Capture by value in lambdas (`[config]`, not `[&config]`).'''),

    ("cpp_deep/scoped_lock_multi_mutex", r'''How does std::scoped_lock handle multiple mutexes? I keep getting deadlocks when two threads lock two mutexes in different orders.''', r'''<think>
The classic deadlock scenario: thread A locks mutex1 then mutex2, thread B locks mutex2
then mutex1. Both block forever. std::scoped_lock (C++17) solves this by locking multiple
mutexes atomically using a deadlock-avoidance algorithm (typically try-and-back-off).

Under the hood, scoped_lock uses std::lock() which implements a deadlock-avoidance
algorithm. The exact algorithm is implementation-defined, but typically it's a try-lock
and back-off strategy that guarantees no deadlock regardless of call order.

scoped_lock vs lock_guard:
- lock_guard: single mutex, simple RAII
- scoped_lock: zero or more mutexes, deadlock-free for multiple
- scoped_lock with one mutex is equivalent to lock_guard
- scoped_lock with zero mutexes is a no-op (useful in generic code)

The key insight is that scoped_lock guarantees the same locking ORDER internally
regardless of the order you pass the mutexes. So even if thread A does
scoped_lock(m1, m2) and thread B does scoped_lock(m2, m1), no deadlock occurs.

I should show: the deadlock problem, the scoped_lock fix, and a practical example
like a bank transfer between accounts that needs to lock both accounts.

Also worth mentioning: std::unique_lock is needed if you want deferred locking,
try_lock, or condition_variable usage. scoped_lock is strictly for "lock now, unlock
at scope exit" patterns.
</think>

`std::scoped_lock` (C++17) uses a deadlock-avoidance algorithm internally, so it locks multiple mutexes safely regardless of the order you pass them. Here is the problem and solution:

```cpp
#include <iostream>
#include <thread>
#include <mutex>
#include <vector>
#include <string>

// --- The deadlock problem ---
struct BankAccount {
    std::string name;
    double balance;
    mutable std::mutex mtx;

    BankAccount(std::string n, double b) : name(std::move(n)), balance(b) {}
};

// DEADLOCKED version: manual locking in different orders
void transfer_DEADLOCK(BankAccount& from, BankAccount& to, double amount) {
    std::lock_guard lock1(from.mtx);  // Thread A: locks 'from' first
    std::lock_guard lock2(to.mtx);    // Thread A: waits for 'to'
    // If Thread B calls transfer(to, from, ...) simultaneously:
    //   Thread B locks 'to' first, waits for 'from' -> DEADLOCK
    from.balance -= amount;
    to.balance += amount;
}

// CORRECT version: std::scoped_lock handles ordering internally
void transfer(BankAccount& from, BankAccount& to, double amount) {
    // Locks both mutexes atomically — no deadlock regardless of argument order
    std::scoped_lock lock(from.mtx, to.mtx);

    if (from.balance >= amount) {
        from.balance -= amount;
        to.balance += amount;
        std::cout << "  Transferred $" << amount
                  << " from " << from.name << " to " << to.name << "\n";
    }
}

// --- Under the hood: equivalent to std::lock + adopt_lock ---
void transfer_manual_equivalent(BankAccount& from, BankAccount& to, double amount) {
    // std::lock uses try-and-back-off to avoid deadlock
    std::lock(from.mtx, to.mtx);
    // adopt_lock tells lock_guard the mutex is already locked
    std::lock_guard lg1(from.mtx, std::adopt_lock);
    std::lock_guard lg2(to.mtx, std::adopt_lock);

    from.balance -= amount;
    to.balance += amount;
}

// --- scoped_lock with zero/one mutexes (generic code) ---
template<typename... Mutexes>
void critical_section(Mutexes&... mutexes) {
    std::scoped_lock lock(mutexes...);  // works with 0, 1, or N mutexes
    std::cout << "  Inside critical section with "
              << sizeof...(Mutexes) << " mutex(es)\n";
}

int main() {
    BankAccount alice("Alice", 1000.0);
    BankAccount bob("Bob", 1000.0);

    std::cout << "=== Concurrent transfers (no deadlock) ===\n";

    // These run concurrently with opposite lock ordering — safe with scoped_lock
    std::vector<std::thread> threads;
    for (int i = 0; i < 50; ++i) {
        threads.emplace_back([&] { transfer(alice, bob, 10.0); });
        threads.emplace_back([&] { transfer(bob, alice, 10.0); });
    }
    for (auto& t : threads) t.join();

    std::cout << "\nFinal balances:\n";
    std::cout << "  Alice: $" << alice.balance << "\n";
    std::cout << "  Bob:   $" << bob.balance << "\n";

    // Generic: zero and one mutex
    std::cout << "\n=== Generic scoped_lock ===\n";
    std::mutex m1;
    critical_section();       // zero mutexes — no-op, compiles fine
    critical_section(m1);     // one mutex — equivalent to lock_guard

    return 0;
}
```

**Key points:**
- `scoped_lock(m1, m2)` and `scoped_lock(m2, m1)` are both safe — internal algorithm prevents deadlock
- With a single mutex, `scoped_lock` is equivalent to `lock_guard`
- With zero mutexes, it is a no-op (useful in templates)
- Use `unique_lock` instead when you need deferred locking, try_lock, or condition variables'''),

    ("cpp_deep/unique_lock_deferred_condvar", r'''When should I use std::unique_lock instead of std::lock_guard? Show me the deferred locking and condition_variable use cases.''', r'''<think>
std::unique_lock is more flexible than lock_guard/scoped_lock at the cost of slight overhead.
It supports:
1. Deferred locking (std::defer_lock) — construct without locking, lock later
2. Try-locking (try_lock()) — non-blocking attempt
3. Timed locking (try_lock_for, try_lock_until) with timed_mutex
4. Manual unlock/relock within scope
5. Required by std::condition_variable (wait() needs to unlock/relock internally)
6. Movable (can transfer ownership, return from functions)

The condition_variable use case is the most important one — condition_variable::wait()
requires unique_lock because it needs to atomically unlock the mutex and sleep, then
relock when woken up.

Deferred locking is useful with std::lock() for deadlock avoidance (pre-C++17 pattern,
now superseded by scoped_lock).

I should show: condition_variable with unique_lock, deferred locking, try_lock,
and timed locking patterns. The condition_variable example should be a proper
producer-consumer queue.
</think>

`std::unique_lock` is required whenever you need more control than "lock on construction, unlock on destruction." Here are the key use cases:

```cpp
#include <iostream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <chrono>
#include <optional>

using namespace std::chrono_literals;

// === 1. condition_variable (most common use case) ===
template<typename T>
class ThreadSafeQueue {
    std::queue<T> queue_;
    mutable std::mutex mtx_;
    std::condition_variable cv_;

public:
    void push(T value) {
        {
            std::lock_guard lock(mtx_);
            queue_.push(std::move(value));
        }
        cv_.notify_one();
    }

    T pop() {
        // condition_variable REQUIRES unique_lock (not lock_guard)
        // because wait() must atomically unlock + sleep, then relock on wake
        std::unique_lock lock(mtx_);
        cv_.wait(lock, [this] { return !queue_.empty(); });
        T value = std::move(queue_.front());
        queue_.pop();
        return value;
    }

    // Timed wait variant
    std::optional<T> try_pop(std::chrono::milliseconds timeout) {
        std::unique_lock lock(mtx_);
        if (!cv_.wait_for(lock, timeout, [this] { return !queue_.empty(); })) {
            return std::nullopt;  // timed out
        }
        T value = std::move(queue_.front());
        queue_.pop();
        return value;
    }
};

// === 2. Deferred locking (lock later, or use with std::lock) ===
void deferred_locking_example() {
    std::cout << "\n=== Deferred locking ===\n";

    std::mutex m1, m2;

    // Pre-C++17 deadlock avoidance pattern (superseded by scoped_lock)
    std::unique_lock lock1(m1, std::defer_lock);  // not locked yet
    std::unique_lock lock2(m2, std::defer_lock);  // not locked yet

    std::lock(lock1, lock2);  // locks both without deadlock
    std::cout << "  Both mutexes locked safely\n";
    // Unlocked when lock1/lock2 go out of scope
}

// === 3. Try-lock (non-blocking) ===
void try_lock_example() {
    std::cout << "\n=== Try-lock ===\n";

    std::mutex mtx;
    std::unique_lock lock(mtx, std::try_to_lock);

    if (lock.owns_lock()) {
        std::cout << "  Acquired the lock\n";
    } else {
        std::cout << "  Lock is busy, doing something else\n";
    }
}

// === 4. Manual unlock/relock within scope ===
void manual_unlock_example() {
    std::cout << "\n=== Manual unlock/relock ===\n";

    std::mutex mtx;
    int shared_data = 0;

    std::unique_lock lock(mtx);
    shared_data = 42;  // access shared data
    lock.unlock();     // release lock for expensive non-critical work

    // Do expensive computation without holding the lock
    std::this_thread::sleep_for(100ms);

    lock.lock();       // reacquire for more shared access
    shared_data += 1;
    std::cout << "  Final value: " << shared_data << "\n";
    // lock releases in destructor
}

// === 5. Timed mutex ===
void timed_locking_example() {
    std::cout << "\n=== Timed locking ===\n";

    std::timed_mutex tmtx;

    std::thread holder([&] {
        std::lock_guard lock(tmtx);
        std::this_thread::sleep_for(1s);
    });

    std::this_thread::sleep_for(50ms);  // let holder grab it

    std::unique_lock lock(tmtx, std::defer_lock);
    if (lock.try_lock_for(200ms)) {
        std::cout << "  Got the lock within 200ms\n";
    } else {
        std::cout << "  Timed out after 200ms, lock is held\n";
    }

    holder.join();
}

// === 6. Movable — transfer lock ownership ===
std::unique_lock<std::mutex> acquire_lock(std::mutex& m) {
    std::unique_lock lock(m);
    // Prepare shared state...
    return lock;  // transfer ownership to caller
}

int main() {
    // Producer-consumer with condition_variable
    std::cout << "=== Producer-consumer queue ===\n";
    ThreadSafeQueue<int> queue;

    std::thread producer([&] {
        for (int i = 0; i < 5; ++i) {
            std::this_thread::sleep_for(100ms);
            queue.push(i);
            std::cout << "  Produced: " << i << "\n";
        }
    });

    std::thread consumer([&] {
        for (int i = 0; i < 5; ++i) {
            int val = queue.pop();
            std::cout << "  Consumed: " << val << "\n";
        }
    });

    producer.join();
    consumer.join();

    deferred_locking_example();
    try_lock_example();
    manual_unlock_example();
    timed_locking_example();

    return 0;
}
```

**Decision guide:**
| Need | Use |
|------|-----|
| Simple lock/unlock scope | `lock_guard` or `scoped_lock` |
| Multiple mutexes | `scoped_lock` |
| `condition_variable` | `unique_lock` (required) |
| Try-lock or timed lock | `unique_lock` |
| Unlock/relock mid-scope | `unique_lock` |
| Transfer lock ownership | `unique_lock` (movable) |'''),

    ("cpp_deep/condvar_producer_consumer", r'''Show me a correct producer-consumer implementation using std::condition_variable with proper shutdown signaling.''', r'''<think>
A proper producer-consumer needs:
1. A mutex-protected queue
2. A condition_variable for "data available" notification
3. A shutdown mechanism so the consumer doesn't block forever after producer is done
4. Handling of spurious wakeups (always use predicate form of wait)

The shutdown is the tricky part. Common approaches:
- A boolean "done" flag protected by the same mutex
- A poison pill / sentinel value in the queue
- Using std::optional<T> where nullopt means "shutdown"

I'll use the done flag approach as it's the most general. The consumer's wait predicate
checks both "queue not empty" OR "done flag set". After waking, it checks which
condition is true.

Multiple consumers: notify_one() wakes one consumer per item. notify_all() is needed
when shutting down so all consumers wake up and see the done flag.

Important: the done flag must be set while holding the lock, then notify_all() is
called. If you notify without holding the lock, there's a race where the consumer
checks the predicate, finds it false, then the producer sets done+notifies, then
the consumer sleeps — missing the notification forever.

Actually, notify can be called outside the lock — the important thing is that the
flag is set under the lock. The consumer will recheck the predicate after being woken.
But calling notify under the lock is also fine and simpler to reason about.

Let me show a multi-producer multi-consumer bounded queue with proper shutdown.
</think>

Here is a correct bounded producer-consumer queue with proper shutdown semantics, handling spurious wakeups, and supporting multiple producers/consumers:

```cpp
#include <iostream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <vector>
#include <optional>
#include <chrono>
#include <atomic>

using namespace std::chrono_literals;

template<typename T, std::size_t MaxSize = 16>
class BoundedQueue {
    std::queue<T> queue_;
    mutable std::mutex mtx_;
    std::condition_variable not_empty_;   // consumers wait on this
    std::condition_variable not_full_;    // producers wait on this
    bool shutdown_ = false;

public:
    // Returns false if queue is shut down (producer should stop)
    bool push(T value) {
        std::unique_lock lock(mtx_);
        // Wait until queue has space OR shutdown
        not_full_.wait(lock, [this] {
            return queue_.size() < MaxSize || shutdown_;
        });

        if (shutdown_) return false;

        queue_.push(std::move(value));
        not_empty_.notify_one();  // wake one consumer
        return true;
    }

    // Returns nullopt when queue is empty AND shutdown
    std::optional<T> pop() {
        std::unique_lock lock(mtx_);
        // Wait until queue has data OR (shutdown AND empty)
        not_empty_.wait(lock, [this] {
            return !queue_.empty() || shutdown_;
        });

        // Drain remaining items even after shutdown
        if (queue_.empty()) {
            return std::nullopt;  // shutdown and nothing left
        }

        T value = std::move(queue_.front());
        queue_.pop();
        not_full_.notify_one();  // wake one blocked producer
        return value;
    }

    void close() {
        {
            std::lock_guard lock(mtx_);
            shutdown_ = true;
        }
        // Wake ALL waiting threads so they see shutdown flag
        not_empty_.notify_all();
        not_full_.notify_all();
    }

    bool is_closed() const {
        std::lock_guard lock(mtx_);
        return shutdown_ && queue_.empty();
    }
};

int main() {
    BoundedQueue<int, 4> queue;  // capacity 4
    std::atomic<int> produced{0};
    std::atomic<int> consumed{0};

    constexpr int NUM_PRODUCERS = 3;
    constexpr int NUM_CONSUMERS = 2;
    constexpr int ITEMS_PER_PRODUCER = 10;

    // --- Producers ---
    std::vector<std::thread> producers;
    for (int p = 0; p < NUM_PRODUCERS; ++p) {
        producers.emplace_back([&queue, &produced, p] {
            for (int i = 0; i < ITEMS_PER_PRODUCER; ++i) {
                int item = p * 100 + i;
                if (!queue.push(item)) {
                    std::cout << "  Producer " << p << " stopped (shutdown)\n";
                    return;
                }
                ++produced;
                std::cout << "  P" << p << " -> " << item << "\n";
                std::this_thread::sleep_for(10ms);
            }
            std::cout << "  Producer " << p << " finished\n";
        });
    }

    // --- Consumers ---
    std::vector<std::thread> consumers;
    for (int c = 0; c < NUM_CONSUMERS; ++c) {
        consumers.emplace_back([&queue, &consumed, c] {
            while (true) {
                auto item = queue.pop();
                if (!item.has_value()) {
                    std::cout << "  Consumer " << c << " stopped (shutdown)\n";
                    return;
                }
                ++consumed;
                std::cout << "  C" << c << " <- " << *item << "\n";
                std::this_thread::sleep_for(15ms);  // simulate processing
            }
        });
    }

    // Wait for all producers to finish
    for (auto& t : producers) t.join();

    // Signal shutdown — consumers will drain remaining items then exit
    std::cout << "\n  All producers done, closing queue...\n\n";
    queue.close();

    // Wait for consumers to drain and exit
    for (auto& t : consumers) t.join();

    std::cout << "\nProduced: " << produced.load()
              << ", Consumed: " << consumed.load() << "\n";

    return 0;
}
```

**Design decisions explained:**
- **Bounded queue**: `not_full_` cv prevents producers from overwhelming consumers (back-pressure)
- **`close()` sets flag under lock, then `notify_all()`**: ensures no thread misses the signal
- **Consumers drain after shutdown**: `pop()` returns data if available even after `close()`; returns `nullopt` only when empty AND closed
- **Predicate form of `wait()`**: handles spurious wakeups correctly — the lambda is re-evaluated after each wake'''),

    ("cpp_deep/condvar_spurious_wakeup", r'''Why do condition_variables have spurious wakeups? How do I handle them correctly? I have a race condition in my code but I am not sure if this is the cause.''', r'''<think>
Spurious wakeups are a fundamental aspect of condition variables across all platforms.
They happen because:
1. OS kernel can wake threads for internal reasons (signal delivery on POSIX)
2. Pthread implementations on some platforms use futexes that can have false wakes
3. The C++ standard explicitly allows them to enable efficient implementations
4. On multiprocessor systems, the notify may wake more threads than intended

But the bigger issue people face is usually NOT spurious wakeups — it's the "lost wake"
or "stolen wake" problem:
- Thread A checks condition (false), is about to wait
- Thread B sets condition, calls notify
- Thread A calls wait — misses the notification, sleeps forever

The predicate form of wait() solves both problems:
  cv.wait(lock, predicate) is equivalent to:
    while (!predicate()) cv.wait(lock);

This means:
1. Spurious wakeup: re-checks predicate, goes back to sleep if still false
2. Lost wake: checks predicate BEFORE sleeping, never misses a notification

The user mentions a race condition — it's likely a notification before wait, or
checking the condition outside the lock. I should show both the wrong and right
patterns, and explain the real-world race conditions.

Common mistakes:
- Checking condition outside the lock
- Using if instead of while (or not using predicate form)
- notify without holding the lock (or at least setting the flag under the lock)
</think>

Spurious wakeups are permitted by the C++ standard (and POSIX) to allow efficient implementations. But the real bugs people hit are usually **lost wakes** or **stolen wakes**, not true spurious wakeups. Here is a complete breakdown:

```cpp
#include <iostream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <chrono>

using namespace std::chrono_literals;

std::mutex mtx;
std::condition_variable cv;
bool ready = false;

// === BUG 1: Using `if` instead of `while` (spurious wakeup bug) ===
void consumer_WRONG_v1() {
    std::unique_lock lock(mtx);
    if (!ready) {           // BUG: if spurious wakeup, proceeds with ready==false
        cv.wait(lock);
    }
    std::cout << "  Consumer proceeds, ready=" << std::boolalpha << ready << "\n";
}

// === BUG 2: Checking condition outside the lock (lost wake) ===
void consumer_WRONG_v2() {
    // BUG: race between check and wait
    if (!ready) {                        // (1) checks ready == false
        // Producer sets ready=true and calls notify HERE
        std::unique_lock lock(mtx);
        cv.wait(lock);                   // (2) sleeps forever — missed the notify
    }
}

// === BUG 3: Raw wait without any condition check ===
void consumer_WRONG_v3() {
    std::unique_lock lock(mtx);
    cv.wait(lock);  // BUG: if notify happened before wait(), sleeps forever
    // Also: spurious wakeup proceeds without checking anything
}

// === CORRECT: Predicate form (handles ALL edge cases) ===
void consumer_CORRECT() {
    std::unique_lock lock(mtx);
    // Equivalent to: while (!ready) cv.wait(lock);
    cv.wait(lock, [] { return ready; });  // handles spurious + lost wakes
    std::cout << "  Consumer correctly sees ready=true\n";
}

// === Demo: proving spurious wakeups and correct handling ===
class RobustGate {
    std::mutex mtx_;
    std::condition_variable cv_;
    bool open_ = false;
    int spurious_count_ = 0;

public:
    void wait_for_open() {
        std::unique_lock lock(mtx_);

        // Manual loop to COUNT spurious wakeups
        while (!open_) {
            cv.wait(lock);
            if (!open_) {
                ++spurious_count_;
                std::cout << "  Spurious wakeup #" << spurious_count_ << "!\n";
            }
        }
        std::cout << "  Gate opened (after " << spurious_count_
                  << " spurious wakeups)\n";
    }

    void open() {
        {
            std::lock_guard lock(mtx_);
            open_ = true;           // set flag UNDER lock
        }
        cv_.notify_all();           // notify can be outside lock
    }
};

// === Correct producer-side pattern ===
void producer_correct() {
    std::this_thread::sleep_for(500ms);

    // IMPORTANT: set the flag while holding the lock
    {
        std::lock_guard lock(mtx);
        ready = true;
    }
    // notify can be outside the lock — consumer will re-check predicate
    cv.notify_one();
}

int main() {
    std::cout << "=== Correct pattern demo ===\n";

    ready = false;
    std::thread prod(producer_correct);
    std::thread cons(consumer_CORRECT);

    prod.join();
    cons.join();

    // === Show the timeline of what can go wrong ===
    std::cout << R"(
=== Why predicate form is essential ===

Timeline of BUG (no predicate):
  Consumer: lock mutex
  Consumer: cv.wait(lock) — unlocks and sleeps
  [spurious wakeup]
  Consumer: wakes up, lock reacquired
  Consumer: proceeds WITHOUT checking if data is ready  <-- BUG

Timeline of BUG (check outside lock):
  Consumer: checks ready (false)
  Producer: sets ready=true, calls notify_one()
  Consumer: locks mutex, calls cv.wait()  <-- sleeps forever (missed notify)

Timeline of CORRECT (predicate form):
  Consumer: locks mutex
  Consumer: checks predicate (false), atomically unlocks + sleeps
  [spurious wakeup]
  Consumer: reacquires lock, checks predicate (still false), goes back to sleep
  Producer: sets ready=true (under lock), notifies
  Consumer: wakes, checks predicate (true), proceeds  <-- correct
)";

    return 0;
}
```

**Rules to never violate:**
1. **Always use predicate form**: `cv.wait(lock, pred)` — never bare `cv.wait(lock)`
2. **Set the flag under the lock**: `{ lock_guard lk(mtx); ready = true; }`
3. **Check the condition under the lock**: the `wait(lock, pred)` form does this for you
4. **`notify_one/all`** can be called outside the lock (slight performance benefit) but the flag mutation must be inside'''),

    ("cpp_deep/shared_mutex_rw_lock", r'''I have a data structure that is read frequently but written rarely. Can I allow multiple readers concurrently while still having exclusive writers?''', r'''<think>
This is the classic readers-writer lock pattern. C++17 provides std::shared_mutex for this.

std::shared_mutex supports two locking modes:
- Exclusive (write): std::unique_lock<std::shared_mutex> or std::lock_guard
- Shared (read): std::shared_lock<std::shared_mutex>

Multiple threads can hold shared locks simultaneously. An exclusive lock waits for all
shared locks to release and blocks new shared locks from being acquired.

Important caveats:
- Writer starvation: if readers keep coming, writer may never get the lock.
  std::shared_mutex implementations typically prevent this (writer-preferring), but
  the standard doesn't guarantee it.
- shared_mutex is heavier than plain mutex. Only worth it if reads vastly outnumber writes.
- Don't use shared_mutex for short critical sections — the overhead isn't worth it.
- C++14 had shared_timed_mutex, C++17 added shared_mutex (without timed operations).

I'll show a thread-safe cache/config store as a practical example. Also show the
lock types: shared_lock for readers, unique_lock/lock_guard for writers.

A DNS cache or config map is a great example — read on every request, update rarely.
</think>

Yes, `std::shared_mutex` (C++17) implements a readers-writer lock. Multiple readers can hold the lock concurrently, but a writer gets exclusive access.

```cpp
#include <iostream>
#include <thread>
#include <shared_mutex>
#include <mutex>
#include <unordered_map>
#include <string>
#include <vector>
#include <chrono>
#include <atomic>

using namespace std::chrono_literals;

// Thread-safe config store: many readers, rare writers
class ConfigStore {
    mutable std::shared_mutex mtx_;  // mutable for const read methods
    std::unordered_map<std::string, std::string> data_;

public:
    // READ: shared_lock allows multiple concurrent readers
    std::string get(const std::string& key) const {
        std::shared_lock lock(mtx_);  // shared (read) access
        auto it = data_.find(key);
        return (it != data_.end()) ? it->second : "";
    }

    bool contains(const std::string& key) const {
        std::shared_lock lock(mtx_);
        return data_.count(key) > 0;
    }

    std::size_t size() const {
        std::shared_lock lock(mtx_);
        return data_.size();
    }

    // WRITE: unique_lock/lock_guard gives exclusive access
    void set(const std::string& key, const std::string& value) {
        std::unique_lock lock(mtx_);  // exclusive (write) access
        data_[key] = value;
    }

    void remove(const std::string& key) {
        std::unique_lock lock(mtx_);
        data_.erase(key);
    }

    // UPGRADE pattern: read first, write only if needed
    bool set_if_absent(const std::string& key, const std::string& value) {
        // First try with shared lock (cheap)
        {
            std::shared_lock read_lock(mtx_);
            if (data_.count(key) > 0) return false;
        }
        // Key not found — acquire exclusive lock and double-check
        {
            std::unique_lock write_lock(mtx_);
            // Double-check: another writer may have inserted between locks
            auto [it, inserted] = data_.try_emplace(key, value);
            return inserted;
        }
    }
};

// DNS cache example
class DnsCache {
    mutable std::shared_mutex mtx_;
    std::unordered_map<std::string, std::string> cache_;

public:
    std::string resolve(const std::string& hostname) const {
        std::shared_lock lock(mtx_);
        auto it = cache_.find(hostname);
        if (it != cache_.end()) return it->second;
        return "";  // cache miss
    }

    void update(const std::string& hostname, const std::string& ip) {
        std::unique_lock lock(mtx_);
        cache_[hostname] = ip;
    }
};

int main() {
    ConfigStore config;
    std::atomic<int> reads{0};
    std::atomic<int> writes{0};

    // Pre-populate
    config.set("db_host", "localhost");
    config.set("db_port", "5432");
    config.set("log_level", "info");

    std::cout << "=== Concurrent readers + rare writer ===\n";

    // 8 reader threads
    std::vector<std::thread> readers;
    for (int i = 0; i < 8; ++i) {
        readers.emplace_back([&config, &reads, i] {
            for (int j = 0; j < 100; ++j) {
                auto val = config.get("db_host");
                ++reads;
                std::this_thread::sleep_for(1ms);
            }
        });
    }

    // 1 writer thread (rare updates)
    std::thread writer([&config, &writes] {
        for (int i = 0; i < 5; ++i) {
            std::this_thread::sleep_for(50ms);
            config.set("log_level", "debug_" + std::to_string(i));
            ++writes;
            std::cout << "  Writer updated config\n";
        }
    });

    for (auto& t : readers) t.join();
    writer.join();

    std::cout << "Total reads: " << reads.load()
              << ", writes: " << writes.load() << "\n";
    std::cout << "Final log_level: " << config.get("log_level") << "\n";

    return 0;
}
```

**When to use `shared_mutex` vs plain `mutex`:**
| Scenario | Recommendation |
|----------|---------------|
| Reads >> writes (100:1 or more) | `shared_mutex` |
| Short critical sections | Plain `mutex` (shared_mutex overhead not worth it) |
| Roughly equal reads/writes | Plain `mutex` |
| Need timed locking | `shared_timed_mutex` (C++14) |

**Pitfall — the upgrade pattern** (`set_if_absent`): you cannot atomically upgrade a shared lock to exclusive. You must release the shared lock, acquire exclusive, then double-check. This creates a TOCTOU window that must be handled with a re-check.'''),

    ("cpp_deep/atomic_memory_orderings", r'''Explain the different std::atomic memory orderings (relaxed, acquire, release, seq_cst) with practical examples. When would I use each one?''', r'''<think>
Memory orderings are one of the hardest topics in C++ concurrency. Let me break them down:

memory_order_seq_cst (default): Total order across all threads. Easiest to reason about.
Most expensive on weakly-ordered architectures (ARM, POWER). This is what you get by default.

memory_order_relaxed: No ordering guarantees between threads. Only guarantees atomicity.
Use for counters, statistics, progress indicators where you don't need synchronization.

memory_order_acquire: A load with acquire means: all reads/writes after this load in
the current thread are guaranteed to happen after the load. "No reads/writes can be
moved before this load." Used on the reading/consuming side.

memory_order_release: A store with release means: all reads/writes before this store
in the current thread are guaranteed to happen before the store. "No reads/writes can
be moved after this store." Used on the writing/producing side.

acquire-release pair: Forms a synchronizes-with relationship. When a release store is
seen by an acquire load, all writes before the release are visible to the acquirer.

memory_order_acq_rel: Combined acquire+release for read-modify-write operations (CAS).

I need to show concrete examples:
1. Relaxed: simple counter
2. Acquire-release: producer-consumer flag
3. Seq_cst: the default, why it's safest
4. A case where relaxed is wrong and you need acquire-release

The classic example: a data structure protected by a flag. The producer writes data,
then sets flag with release. Consumer reads flag with acquire, then reads data.
Without acquire-release, the consumer might see the flag but not the data (on ARM/POWER).
</think>

Memory orderings control how atomic operations synchronize between threads. On x86 they often compile to the same instructions, but on ARM/POWER they generate different barriers. Here is each ordering with a concrete use case:

```cpp
#include <iostream>
#include <thread>
#include <atomic>
#include <cassert>
#include <vector>
#include <chrono>

using namespace std::chrono_literals;

// ============================================================
// 1. RELAXED: Only guarantees atomicity, no ordering
//    Use for: counters, statistics, progress tracking
// ============================================================
void relaxed_counter_example() {
    std::cout << "=== relaxed: concurrent counter ===\n";
    std::atomic<int> counter{0};

    std::vector<std::thread> threads;
    for (int i = 0; i < 8; ++i) {
        threads.emplace_back([&counter] {
            for (int j = 0; j < 10000; ++j) {
                // Relaxed is fine — we only care about the final total,
                // not about ordering relative to other operations
                counter.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }
    for (auto& t : threads) t.join();
    std::cout << "  Counter: " << counter.load(std::memory_order_relaxed)
              << " (expected 80000)\n";
}

// ============================================================
// 2. ACQUIRE-RELEASE: Synchronizes data between producer/consumer
//    Release store "publishes" all prior writes
//    Acquire load "sees" all writes from the release store
// ============================================================
struct Payload {
    int x = 0;
    int y = 0;
    std::string msg;
};

void acquire_release_example() {
    std::cout << "\n=== acquire-release: publish data ===\n";

    Payload data;
    std::atomic<bool> ready{false};

    // Producer: writes data, then RELEASES the flag
    std::thread producer([&] {
        // These non-atomic writes happen-before the release store
        data.x = 42;
        data.y = 99;
        data.msg = "hello from producer";

        // Release: guarantees all writes above are visible
        // to any thread that acquires this flag
        ready.store(true, std::memory_order_release);
    });

    // Consumer: ACQUIRES the flag, then reads data
    std::thread consumer([&] {
        // Spin until flag is set (acquire load)
        while (!ready.load(std::memory_order_acquire)) {
            // Busy wait (in practice, you'd use a better mechanism)
        }
        // Acquire guarantees: all writes before the release store are visible here
        assert(data.x == 42);
        assert(data.y == 99);
        std::cout << "  Received: " << data.msg << "\n";
        std::cout << "  x=" << data.x << " y=" << data.y << "\n";
    });

    producer.join();
    consumer.join();
}

// WHY relaxed would be WRONG for the above:
// On ARM/POWER with relaxed, the consumer might see ready==true
// but data.x==0 because the CPU reordered the stores.

// ============================================================
// 3. SEQ_CST: Total order (the default, safest, slowest)
// ============================================================
void seq_cst_example() {
    std::cout << "\n=== seq_cst: total order ===\n";

    // Classic Dekker/Peterson scenario where seq_cst matters
    std::atomic<bool> flag_a{false}, flag_b{false};
    std::atomic<int> result_a{0}, result_b{0};

    // With seq_cst, at least one thread sees the other's flag as true
    // With acquire-release, BOTH could see false (no total order)
    std::thread a([&] {
        flag_a.store(true);  // seq_cst by default
        result_a = flag_b.load() ? 1 : 0;
    });

    std::thread b([&] {
        flag_b.store(true);  // seq_cst by default
        result_b = flag_a.load() ? 1 : 0;
    });

    a.join();
    b.join();

    // With seq_cst: result_a + result_b >= 1 (always)
    // With relaxed: result_a + result_b could be 0 (both miss)
    std::cout << "  result_a=" << result_a << " result_b=" << result_b
              << " sum=" << (result_a + result_b) << " (must be >= 1)\n";
}

// ============================================================
// 4. ACQ_REL: Combined acquire+release for read-modify-write
// ============================================================
void acq_rel_example() {
    std::cout << "\n=== acq_rel: atomic exchange ===\n";

    // Spinlock using exchange
    std::atomic<bool> lock{false};
    int shared_counter = 0;

    auto worker = [&](int id) {
        for (int i = 0; i < 1000; ++i) {
            // Acquire+release: see prior writes AND publish our writes
            while (lock.exchange(true, std::memory_order_acquire)) {
                // spin
            }
            // Critical section
            ++shared_counter;
            lock.store(false, std::memory_order_release);
        }
    };

    std::thread t1(worker, 1);
    std::thread t2(worker, 2);
    t1.join();
    t2.join();
    std::cout << "  shared_counter: " << shared_counter << " (expected 2000)\n";
}

int main() {
    relaxed_counter_example();
    acquire_release_example();
    seq_cst_example();
    acq_rel_example();
    return 0;
}
```

**Decision table:**

| Ordering | Cost | Use when |
|----------|------|----------|
| `relaxed` | Cheapest | Counters, stats, no data dependencies |
| `acquire` | Load fence | Reading side of publish pattern |
| `release` | Store fence | Writing side of publish pattern |
| `acq_rel` | Both fences | Read-modify-write (CAS, exchange) |
| `seq_cst` | Full fence | Default, total order needed, or when unsure |

**Rule of thumb:** Use `seq_cst` (the default) unless profiling shows it is a bottleneck. Weakening to acquire-release is the most common optimization. Only use `relaxed` when the atomic is truly independent.'''),

    ("cpp_deep/cas_loop_pattern", r'''Show me how to implement a compare-and-swap (CAS) loop in C++. What are the common pitfalls?''', r'''<think>
Compare-and-swap (CAS) is the fundamental building block of lock-free programming.
In C++, it's std::atomic::compare_exchange_weak/strong.

compare_exchange_weak: may spuriously fail (even if value matches). Must be used in a loop.
compare_exchange_strong: fails only if value actually doesn't match. More expensive on
some architectures (LL/SC based like ARM).

The pattern:
1. Load the current value
2. Compute the desired new value based on current
3. CAS: if current hasn't changed, atomically swap to new value
4. If CAS fails, the "expected" parameter is updated with the actual current value
5. Retry from step 2 with the new current value

Pitfalls:
- Forgetting that compare_exchange_weak can spuriously fail
- Not understanding that "expected" is an in/out parameter (updated on failure)
- ABA problem: value changes A->B->A, CAS succeeds but intervening state was missed
- Using too-strong memory ordering (seq_cst when acq_rel suffices)
- Infinite retry under high contention (may need backoff)

I should show: basic atomic increment (to demonstrate the pattern), a lock-free stack push,
and mention the ABA problem. Also show the difference between weak and strong.
</think>

CAS (compare-and-swap) is the foundation of lock-free algorithms. C++ provides `compare_exchange_weak` and `compare_exchange_strong` on `std::atomic`. Here is the pattern with pitfalls:

```cpp
#include <iostream>
#include <thread>
#include <atomic>
#include <vector>
#include <cmath>

// ============================================================
// Basic CAS loop pattern
// ============================================================
void cas_increment(std::atomic<int>& value) {
    int expected = value.load(std::memory_order_relaxed);
    while (!value.compare_exchange_weak(
            expected,                      // in/out: current value
            expected + 1,                  // desired new value
            std::memory_order_acq_rel,     // success ordering
            std::memory_order_relaxed))    // failure ordering
    {
        // CAS failed: "expected" was updated to the actual current value
        // Loop retries with the new "expected"
        // No need to reload — compare_exchange updates expected for us
    }
}

// ============================================================
// Practical: lock-free atomic max
// ============================================================
void atomic_max(std::atomic<int>& target, int value) {
    int current = target.load(std::memory_order_relaxed);
    while (current < value) {
        // Try to replace current with value if current hasn't changed
        if (target.compare_exchange_weak(
                current, value,
                std::memory_order_release,
                std::memory_order_relaxed)) {
            break;  // success
        }
        // Failed: current was updated to actual value, loop re-checks condition
    }
}

// ============================================================
// Practical: lock-free atomic floating-point add (C++20 has fetch_add for float,
// but this shows the CAS pattern for custom operations)
// ============================================================
void atomic_float_add(std::atomic<double>& target, double addend) {
    double current = target.load(std::memory_order_relaxed);
    double desired;
    do {
        desired = current + addend;
    } while (!target.compare_exchange_weak(
        current, desired,
        std::memory_order_acq_rel,
        std::memory_order_relaxed));
}

// ============================================================
// Lock-free stack push (simple, has ABA problem — see discussion)
// ============================================================
struct Node {
    int data;
    Node* next;
    Node(int d) : data(d), next(nullptr) {}
};

class LockFreeStack {
    std::atomic<Node*> head_{nullptr};

public:
    void push(int value) {
        Node* new_node = new Node(value);
        new_node->next = head_.load(std::memory_order_relaxed);

        // CAS loop: try to set head to new_node
        while (!head_.compare_exchange_weak(
                new_node->next,   // expected = current head (updated on failure)
                new_node,         // desired = new node becomes head
                std::memory_order_release,
                std::memory_order_relaxed))
        {
            // Failed: another thread modified head
            // new_node->next was updated to actual head, retry
        }
    }

    // WARNING: This pop has the ABA problem!
    Node* pop() {
        Node* old_head = head_.load(std::memory_order_acquire);
        while (old_head && !head_.compare_exchange_weak(
                old_head,           // expected
                old_head->next,     // desired = second node
                std::memory_order_acq_rel,
                std::memory_order_relaxed))
        {
            // old_head updated to current head on failure
        }
        return old_head;  // caller owns this node (or nullptr if empty)
    }

    ~LockFreeStack() {
        while (Node* n = pop()) delete n;
    }
};

// ============================================================
// Weak vs Strong comparison
// ============================================================
void weak_vs_strong_demo() {
    std::cout << "=== weak vs strong ===\n";
    std::atomic<int> val{0};

    // STRONG: fails only if value actually mismatches. Use outside loops.
    int expected = 0;
    bool success = val.compare_exchange_strong(expected, 42);
    std::cout << "  strong CAS: success=" << std::boolalpha << success
              << " val=" << val.load() << "\n";

    // WEAK: may spuriously fail even if value matches. MUST be in a loop.
    // On LL/SC architectures (ARM), weak maps directly to LL/SC without retry,
    // making it cheaper per attempt. Strong adds a retry loop internally.
    val.store(0);
    expected = 0;
    while (!val.compare_exchange_weak(expected, 99)) {
        expected = 0;  // reset expected for retry
    }
    std::cout << "  weak CAS in loop: val=" << val.load() << "\n";
}

int main() {
    // Test CAS increment
    std::cout << "=== CAS increment ===\n";
    std::atomic<int> counter{0};
    std::vector<std::thread> threads;
    for (int i = 0; i < 8; ++i) {
        threads.emplace_back([&] {
            for (int j = 0; j < 10000; ++j) {
                cas_increment(counter);
            }
        });
    }
    for (auto& t : threads) t.join();
    std::cout << "  Counter: " << counter.load() << " (expected 80000)\n";

    // Test atomic max
    std::cout << "\n=== Atomic max ===\n";
    std::atomic<int> max_val{0};
    threads.clear();
    for (int i = 0; i < 8; ++i) {
        threads.emplace_back([&max_val, i] {
            atomic_max(max_val, i * 100 + 50);
        });
    }
    for (auto& t : threads) t.join();
    std::cout << "  Max: " << max_val.load() << " (expected 750)\n";

    // Test lock-free stack
    std::cout << "\n=== Lock-free stack ===\n";
    LockFreeStack stack;
    threads.clear();
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&stack, i] {
            for (int j = 0; j < 100; ++j) {
                stack.push(i * 100 + j);
            }
        });
    }
    for (auto& t : threads) t.join();
    int popped = 0;
    while (auto* n = stack.pop()) { ++popped; delete n; }
    std::cout << "  Popped " << popped << " items (expected 400)\n";

    weak_vs_strong_demo();

    return 0;
}
```

**Common pitfalls:**
1. **`expected` is in/out**: on failure, it is updated to the actual value — do not manually reload
2. **`weak` must be in a loop**: it can spuriously fail on LL/SC architectures
3. **ABA problem**: the stack `pop()` above is vulnerable — a value might change A->B->A and the CAS succeeds incorrectly (fix with tagged pointers or hazard pointers)
4. **Contention**: under heavy contention, CAS loops spin-wait — add exponential backoff for production code'''),

    ("cpp_deep/lockfree_stack_aba", r'''Can you explain the ABA problem in lock-free data structures and show approaches to solve it?''', r'''<think>
The ABA problem occurs in CAS-based lock-free data structures:
1. Thread 1 reads value A from a shared location
2. Thread 1 is preempted
3. Thread 2 changes the value from A to B, then back to A
4. Thread 1 resumes, does CAS, sees A, succeeds — but the state has changed

For a lock-free stack:
- Thread 1 sees head=A, wants to pop A, so desired new head = A->next
- Thread 2 pops A, pops B, pushes A back (now A->next points to something different)
- Thread 1's CAS succeeds (head is still A), but A->next is wrong now

Solutions:
1. Tagged pointers (version counter): pack a counter with the pointer. Each CAS increments
   the counter, so even if the pointer is the same, the tag differs. On 64-bit, use the
   upper bits or use a 128-bit CAS (std::atomic<pair> or platform-specific).
2. Hazard pointers: threads publish what pointers they're currently accessing. Defer
   deletion until no thread has a hazard pointer to the node.
3. Epoch-based reclamation (EBR): tracks global epochs, frees memory only after all
   threads have passed the epoch boundary.
4. RCU (Read-Copy-Update): Linux kernel technique, now in userspace libraries.

I'll show the tagged pointer approach as it's the most self-contained. Also briefly
mention hazard pointers. The tagged pointer can use std::atomic with a struct on
platforms supporting double-width CAS (most x86_64 support cmpxchg16b).

Actually, simpler: use a uintptr_t and pack the tag in the upper bits (on x86_64,
only 48 bits of virtual address are used, leaving 16 bits for a tag).
</think>

The ABA problem is the most subtle bug in lock-free programming. It occurs when a CAS succeeds because the value looks the same, but the underlying state has changed. Here is a demonstration and two solutions:

```cpp
#include <iostream>
#include <thread>
#include <atomic>
#include <vector>
#include <cstdint>

// ============================================================
// THE PROBLEM: ABA in a lock-free stack
// ============================================================
// Scenario:
//   Stack: A -> B -> C
//   Thread 1: pop(), reads head=A, old_head->next=B, about to CAS(head, A, B)
//   Thread 1 preempted...
//   Thread 2: pop() A, pop() B, push(A) back. Stack is now: A -> C
//   Thread 1 resumes: CAS(head, A, B) succeeds! (head is A)
//   But head should be C, not B. B was freed. UNDEFINED BEHAVIOR.

// ============================================================
// SOLUTION 1: Tagged pointer (version counter)
// ============================================================
// Pack a monotonically increasing tag with the pointer.
// Even if the pointer value is reused (ABA), the tag will differ.

struct Node {
    int data;
    Node* next;
    Node(int d) : data(d), next(nullptr) {}
};

struct TaggedPtr {
    Node* ptr;
    std::uintptr_t tag;  // version counter

    bool operator==(const TaggedPtr& other) const {
        return ptr == other.ptr && tag == other.tag;
    }
};

class ABAFreeStack {
    // Requires double-width CAS support (128-bit on x86_64)
    // Most compilers support this with -mcx16 flag
    std::atomic<TaggedPtr> head_{{nullptr, 0}};

public:
    void push(int value) {
        Node* new_node = new Node(value);
        TaggedPtr old_head = head_.load(std::memory_order_relaxed);
        TaggedPtr new_head;
        do {
            new_node->next = old_head.ptr;
            new_head = {new_node, old_head.tag + 1};  // increment tag
        } while (!head_.compare_exchange_weak(
            old_head, new_head,
            std::memory_order_release,
            std::memory_order_relaxed));
    }

    Node* pop() {
        TaggedPtr old_head = head_.load(std::memory_order_acquire);
        TaggedPtr new_head;
        do {
            if (!old_head.ptr) return nullptr;
            new_head = {old_head.ptr->next, old_head.tag + 1};
            // If another thread popped and re-pushed the same node,
            // the TAG will be different, so CAS fails correctly
        } while (!head_.compare_exchange_weak(
            old_head, new_head,
            std::memory_order_acq_rel,
            std::memory_order_relaxed));
        return old_head.ptr;
    }

    ~ABAFreeStack() {
        while (Node* n = pop()) delete n;
    }
};

// ============================================================
// SOLUTION 2: Simplified hazard pointer concept
// ============================================================
// Idea: before accessing a node, a thread "claims" it by publishing
// a hazard pointer. Other threads check hazard pointers before freeing.

static constexpr int MAX_THREADS = 16;

class HazardPointerDomain {
    std::atomic<Node*> hazard_ptrs_[MAX_THREADS] = {};
    std::atomic<int> next_slot_{0};

    // Thread-local slot assignment
    static thread_local int my_slot_;

public:
    int acquire_slot() {
        if (my_slot_ < 0) {
            my_slot_ = next_slot_.fetch_add(1, std::memory_order_relaxed);
        }
        return my_slot_;
    }

    void set_hazard(int slot, Node* ptr) {
        hazard_ptrs_[slot].store(ptr, std::memory_order_release);
    }

    void clear_hazard(int slot) {
        hazard_ptrs_[slot].store(nullptr, std::memory_order_release);
    }

    bool is_hazardous(Node* ptr) const {
        for (int i = 0; i < MAX_THREADS; ++i) {
            if (hazard_ptrs_[i].load(std::memory_order_acquire) == ptr) {
                return true;  // someone is using this node
            }
        }
        return false;
    }

    // Safe deletion: only delete if no thread has a hazard pointer to it
    void safe_delete(Node* ptr) {
        if (!is_hazardous(ptr)) {
            delete ptr;
        } else {
            // In production: add to a retired list and retry later
            // For simplicity, we leak here (real implementation defers)
            std::cout << "  Node " << ptr->data
                      << " deferred (hazard pointer active)\n";
        }
    }
};

thread_local int HazardPointerDomain::my_slot_ = -1;

// ============================================================
// Demo
// ============================================================
int main() {
    std::cout << "=== ABA-free stack with tagged pointers ===\n";

    ABAFreeStack stack;

    // Concurrent push/pop stress test
    std::vector<std::thread> threads;
    std::atomic<int> push_count{0}, pop_count{0};

    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&stack, &push_count, i] {
            for (int j = 0; j < 1000; ++j) {
                stack.push(i * 1000 + j);
                ++push_count;
            }
        });
    }

    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&stack, &pop_count] {
            for (int j = 0; j < 1000; ++j) {
                if (Node* n = stack.pop()) {
                    delete n;
                    ++pop_count;
                }
            }
        });
    }

    for (auto& t : threads) t.join();

    // Drain remaining
    while (Node* n = stack.pop()) { delete n; ++pop_count; }

    std::cout << "  Pushed: " << push_count.load()
              << " Popped: " << pop_count.load() << "\n";

    std::cout << R"(
=== ABA Problem Summary ===
Problem:
  CAS(ptr, A, B) succeeds even though ptr went A -> X -> A
  The "second A" may have different state than the "first A"

Solutions:
  1. Tagged pointer: pack version counter with pointer (shown above)
     + Simple, fast, no memory management complexity
     - Requires 128-bit CAS (cmpxchg16b on x86_64)
     - Tag can theoretically wrap around (2^64 iterations = practically never)

  2. Hazard pointers: threads publish what they're reading
     + Bounded memory overhead
     - Complex implementation, per-thread bookkeeping

  3. Epoch-based reclamation (EBR): global epoch counter
     + Simpler than hazard pointers
     - Blocking thread delays all reclamation

  4. RCU (Read-Copy-Update): readers never block
     + Best read performance
     - Writers must copy and defer deletion
)";

    return 0;
}
```

**Compile note:** For 128-bit CAS on GCC/Clang, compile with `-mcx16 -std=c++17`. MSVC supports it natively on x86_64. If `std::atomic<TaggedPtr>` is not lock-free on your platform, check `std::atomic<TaggedPtr>::is_lock_free()`.'''),

    ("cpp_deep/lockfree_spsc_queue", r'''I need a lock-free single-producer single-consumer (SPSC) queue. Show me a correct implementation with proper memory ordering.''', r'''<think>
SPSC queues are the simplest lock-free structure because there's no contention — only
one thread writes and one thread reads. This means we don't need CAS at all, just
atomic loads and stores with proper memory ordering.

The classic implementation uses a fixed-size ring buffer with two atomic indices:
- write_pos_: only written by producer, read by consumer
- read_pos_: only written by consumer, read by producer

Since each index is only written by one thread, we don't need CAS. We just need:
- Producer: store to write_pos_ with release (publishes the data written before it)
- Consumer: load write_pos_ with acquire (sees the data the producer wrote)
- Consumer: store to read_pos_ with release (publishes that the slot is free)
- Producer: load read_pos_ with acquire (sees that the slot was freed)

Capacity is power of 2 for fast modulo (bitwise AND). We use size = capacity + 1
or keep the indices unbounded and mask them — the unbounded approach is cleaner as
it avoids the "full vs empty" ambiguity problem.

Actually, the simplest correct approach: use indices that grow forever (never wrap),
and mask them when indexing into the buffer. Full = (write - read) == capacity.
Empty = write == read. Since indices are size_t, they wrap at 2^64 which is fine.

Key: the data in the buffer itself is NOT atomic. The acquire-release on the indices
provides the necessary ordering guarantees.
</think>

SPSC queues are the simplest lock-free structure: no CAS needed, just atomic loads/stores. One thread writes, one reads, so there is no contention on any index.

```cpp
#include <iostream>
#include <thread>
#include <atomic>
#include <vector>
#include <optional>
#include <cstddef>
#include <cassert>
#include <chrono>
#include <new>  // for hardware_destructive_interference_size

// Cache line size (prevent false sharing between read_pos_ and write_pos_)
#ifdef __cpp_lib_hardware_interference_size
    static constexpr std::size_t CACHE_LINE = std::hardware_destructive_interference_size;
#else
    static constexpr std::size_t CACHE_LINE = 64;
#endif

template<typename T, std::size_t Capacity>
class SPSCQueue {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");
    static constexpr std::size_t MASK = Capacity - 1;

    // Align to separate cache lines to prevent false sharing
    alignas(CACHE_LINE) std::atomic<std::size_t> write_pos_{0};
    alignas(CACHE_LINE) std::atomic<std::size_t> read_pos_{0};
    alignas(CACHE_LINE) T buffer_[Capacity];

public:
    // Called ONLY by the producer thread
    bool try_push(const T& value) {
        const auto write = write_pos_.load(std::memory_order_relaxed);
        const auto read = read_pos_.load(std::memory_order_acquire);  // see consumer's progress

        if (write - read == Capacity) {
            return false;  // full
        }

        buffer_[write & MASK] = value;

        // Release: publishes the data written above to the consumer
        write_pos_.store(write + 1, std::memory_order_release);
        return true;
    }

    // Called ONLY by the consumer thread
    std::optional<T> try_pop() {
        const auto read = read_pos_.load(std::memory_order_relaxed);
        const auto write = write_pos_.load(std::memory_order_acquire);  // see producer's data

        if (read == write) {
            return std::nullopt;  // empty
        }

        T value = buffer_[read & MASK];

        // Release: publishes that this slot is now free for the producer
        read_pos_.store(read + 1, std::memory_order_release);
        return value;
    }

    bool empty() const {
        return read_pos_.load(std::memory_order_acquire)
            == write_pos_.load(std::memory_order_acquire);
    }

    std::size_t size() const {
        auto write = write_pos_.load(std::memory_order_acquire);
        auto read = read_pos_.load(std::memory_order_acquire);
        return write - read;
    }

    // Blocking push (spins) — for when you can't afford to drop data
    void push(const T& value) {
        while (!try_push(value)) {
            // Optionally: std::this_thread::yield() or pause intrinsic
        }
    }

    // Blocking pop (spins)
    T pop() {
        std::optional<T> result;
        while (!(result = try_pop())) {
            // Spin
        }
        return *result;
    }
};

// ============================================================
// Benchmark / correctness test
// ============================================================
int main() {
    constexpr std::size_t QUEUE_SIZE = 1024;  // must be power of 2
    constexpr std::size_t NUM_ITEMS = 1'000'000;

    SPSCQueue<std::size_t, QUEUE_SIZE> queue;

    auto start = std::chrono::high_resolution_clock::now();

    // Producer thread
    std::thread producer([&] {
        for (std::size_t i = 0; i < NUM_ITEMS; ++i) {
            queue.push(i);
        }
    });

    // Consumer thread
    std::size_t sum = 0;
    std::size_t count = 0;
    std::thread consumer([&] {
        for (std::size_t i = 0; i < NUM_ITEMS; ++i) {
            std::size_t val = queue.pop();
            assert(val == i);  // verify ordering
            sum += val;
            ++count;
        }
    });

    producer.join();
    consumer.join();

    auto elapsed = std::chrono::high_resolution_clock::now() - start;
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count();

    // Verify correctness
    std::size_t expected_sum = (NUM_ITEMS - 1) * NUM_ITEMS / 2;
    std::cout << "Items: " << count << " (expected " << NUM_ITEMS << ")\n";
    std::cout << "Sum:   " << sum << " (expected " << expected_sum << ")\n";
    std::cout << "Match: " << std::boolalpha << (sum == expected_sum) << "\n";
    std::cout << "Time:  " << ms << " ms\n";
    std::cout << "Rate:  " << (NUM_ITEMS * 1000 / (ms ? ms : 1)) << " items/sec\n";

    return 0;
}
```

**Why this is correct:**
1. **No CAS needed**: each index is written by exactly one thread
2. **`release` on write_pos_ store**: guarantees the buffer write is visible before the index update
3. **`acquire` on write_pos_ load**: the consumer sees the data the producer wrote
4. **Same logic for read_pos_**: consumer releases, producer acquires
5. **Power-of-2 capacity**: `index & MASK` is a fast modulo
6. **Unbounded indices**: they grow forever; wrapping at 2^64 is not a practical concern
7. **Cache line alignment**: `write_pos_` and `read_pos_` are on separate cache lines to prevent false sharing

This design typically achieves 100M+ operations/second on modern hardware.'''),

    ("cpp_deep/thread_pool_work_stealing", r'''Show me a thread pool implementation with a task queue. Bonus if it supports work stealing between threads.''', r'''<think>
A thread pool needs:
1. A fixed number of worker threads
2. A task queue (thread-safe)
3. A way to submit tasks and get futures back
4. Graceful shutdown

For work stealing: each thread has its own local deque. When a thread's deque is empty,
it steals from another thread's deque. This reduces contention on a single shared queue.

The full work-stealing implementation is complex. Let me do a practical version:
- Global shared queue for submitted tasks
- Per-thread local queues for work stealing
- Actually, let me keep it simpler but still functional: a thread pool with a single
  concurrent queue, plus a simplified stealing mechanism.

Actually, for a training pair, a clean thread pool with std::function + futures is more
useful than a complex work-stealing implementation. Let me do a high-quality thread pool
that covers the key patterns, and then add a simplified work-stealing variant.

Key features:
- submit() returns std::future<ReturnType>
- Uses std::packaged_task under the hood
- Proper shutdown with draining
- Move-only tasks (std::function can't hold move-only callables, so use std::packaged_task
  or a custom wrapper)

Actually std::function requires copyable callables. For move-only, I'll use
std::packaged_task<void()> or a custom type-erased wrapper with std::unique_ptr.

Let me use std::function<void()> for simplicity and wrap the packaged_task in a
shared_ptr to make it copyable. This is the standard approach.
</think>

Here is a production-quality thread pool with task submission via futures, plus a simplified work-stealing variant:

```cpp
#include <iostream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <functional>
#include <future>
#include <vector>
#include <atomic>
#include <memory>
#include <type_traits>
#include <deque>
#include <random>

// ============================================================
// ThreadPool: shared queue, submit returns std::future
// ============================================================
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

    // Submit a callable, returns future<ReturnType>
    template<typename F, typename... Args>
    auto submit(F&& f, Args&&... args) -> std::future<std::invoke_result_t<F, Args...>> {
        using ReturnType = std::invoke_result_t<F, Args...>;

        // packaged_task is move-only, so wrap in shared_ptr for std::function
        auto task = std::make_shared<std::packaged_task<ReturnType()>>(
            std::bind(std::forward<F>(f), std::forward<Args>(args)...)
        );

        std::future<ReturnType> result = task->get_future();

        {
            std::lock_guard lock(mtx_);
            if (stop_) throw std::runtime_error("submit to stopped pool");
            tasks_.emplace([task]() { (*task)(); });
        }
        cv_.notify_one();

        return result;
    }

    ~ThreadPool() {
        {
            std::lock_guard lock(mtx_);
            stop_ = true;
        }
        cv_.notify_all();
        for (auto& w : workers_) w.join();
    }

    std::size_t thread_count() const { return workers_.size(); }

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
            task();
        }
    }
};

// ============================================================
// WorkStealingPool: per-thread deques, steal from others when idle
// ============================================================
class WorkStealingPool {
    struct WorkerData {
        std::deque<std::function<void()>> local_queue;
        std::mutex mtx;
    };

    std::vector<std::thread> workers_;
    std::vector<std::unique_ptr<WorkerData>> worker_data_;
    std::atomic<bool> stop_{false};
    std::atomic<std::size_t> next_submit_{0};  // round-robin submission
    std::mutex global_mtx_;
    std::condition_variable global_cv_;

public:
    explicit WorkStealingPool(std::size_t num_threads = std::thread::hardware_concurrency()) {
        for (std::size_t i = 0; i < num_threads; ++i) {
            worker_data_.push_back(std::make_unique<WorkerData>());
        }
        for (std::size_t i = 0; i < num_threads; ++i) {
            workers_.emplace_back([this, i] { worker_loop(i); });
        }
    }

    template<typename F, typename... Args>
    auto submit(F&& f, Args&&... args) -> std::future<std::invoke_result_t<F, Args...>> {
        using ReturnType = std::invoke_result_t<F, Args...>;

        auto task = std::make_shared<std::packaged_task<ReturnType()>>(
            std::bind(std::forward<F>(f), std::forward<Args>(args)...)
        );
        auto result = task->get_future();

        // Round-robin to distribute work
        auto idx = next_submit_.fetch_add(1, std::memory_order_relaxed)
                   % worker_data_.size();
        {
            std::lock_guard lock(worker_data_[idx]->mtx);
            worker_data_[idx]->local_queue.emplace_back([task] { (*task)(); });
        }
        global_cv_.notify_all();

        return result;
    }

    ~WorkStealingPool() {
        stop_.store(true, std::memory_order_release);
        global_cv_.notify_all();
        for (auto& w : workers_) w.join();
    }

private:
    bool try_pop_local(std::size_t id, std::function<void()>& task) {
        std::lock_guard lock(worker_data_[id]->mtx);
        if (worker_data_[id]->local_queue.empty()) return false;
        task = std::move(worker_data_[id]->local_queue.front());
        worker_data_[id]->local_queue.pop_front();
        return true;
    }

    bool try_steal(std::size_t thief_id, std::function<void()>& task) {
        for (std::size_t i = 0; i < worker_data_.size(); ++i) {
            if (i == thief_id) continue;
            std::lock_guard lock(worker_data_[i]->mtx);
            if (!worker_data_[i]->local_queue.empty()) {
                // Steal from the BACK (opposite end from owner)
                task = std::move(worker_data_[i]->local_queue.back());
                worker_data_[i]->local_queue.pop_back();
                return true;
            }
        }
        return false;
    }

    void worker_loop(std::size_t id) {
        while (!stop_.load(std::memory_order_acquire)) {
            std::function<void()> task;

            // 1. Try own queue first
            if (try_pop_local(id, task)) {
                task();
                continue;
            }

            // 2. Try stealing from another thread
            if (try_steal(id, task)) {
                task();
                continue;
            }

            // 3. Wait for new work
            std::unique_lock lock(global_mtx_);
            global_cv_.wait_for(lock, std::chrono::milliseconds(1));
        }

        // Drain remaining tasks
        std::function<void()> task;
        while (try_pop_local(id, task)) task();
    }
};

// ============================================================
// Demo
// ============================================================
int main() {
    std::cout << "=== Basic ThreadPool ===\n";
    {
        ThreadPool pool(4);

        // Submit tasks and collect futures
        std::vector<std::future<int>> results;
        for (int i = 0; i < 20; ++i) {
            results.push_back(pool.submit([i] {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                return i * i;
            }));
        }

        int sum = 0;
        for (auto& f : results) sum += f.get();
        std::cout << "  Sum of squares 0..19: " << sum << "\n";

        // Submit void tasks
        auto done = pool.submit([] {
            std::cout << "  Void task on thread "
                      << std::this_thread::get_id() << "\n";
        });
        done.get();
    }

    std::cout << "\n=== Work-Stealing Pool ===\n";
    {
        WorkStealingPool pool(4);

        std::atomic<int> completed{0};
        std::vector<std::future<int>> futures;

        for (int i = 0; i < 100; ++i) {
            futures.push_back(pool.submit([i, &completed] {
                // Simulate variable work
                volatile int x = 0;
                for (int j = 0; j < i * 100; ++j) ++x;
                ++completed;
                return i;
            }));
        }

        for (auto& f : futures) f.get();
        std::cout << "  Completed: " << completed.load() << " tasks\n";
    }

    return 0;
}
```

**Design notes:**
- **`submit()` returns `std::future<T>`**: type-erased via `shared_ptr<packaged_task>` to fit into `std::function<void()>`
- **Work stealing**: thieves take from the back of another thread's deque (opposite end), reducing contention with the owner
- **Graceful shutdown**: destructor sets stop flag, notifies all, joins all threads, drains remaining tasks
- In production, consider lock-free deques (Chase-Lev) for the per-thread queues'''),

    ("cpp_deep/latch_synchronization", r'''Show me how to use std::latch (C++20) for one-time synchronization. When would I prefer it over a barrier?''', r'''<think>
std::latch is a single-use countdown synchronization primitive. You set an initial count,
threads call count_down(), and threads waiting on arrive_and_wait() or wait() are released
when the count reaches zero. Once triggered, the latch is permanently open.

Key differences from barrier:
- latch: single-use, count down to zero, done forever
- barrier: reusable, all threads arrive, resets, can be used again

Use cases for latch:
- Wait for N initialization tasks to complete before proceeding
- Fan-out: main thread creates workers, waits for all to be ready
- One-shot gate: release multiple waiting threads simultaneously

count_down() can be called multiple times by the same thread (e.g., one thread does
multiple units of work). This is different from barrier where each thread arrives once.

Let me show practical examples: initialization barrier, fan-in/fan-out, and compare
with barrier.
</think>

`std::latch` (C++20) is a single-use countdown synchronization primitive. Once the count reaches zero, it stays open forever. Compare this to `std::barrier` which resets and can be reused.

```cpp
#include <iostream>
#include <thread>
#include <latch>
#include <vector>
#include <string>
#include <chrono>

using namespace std::chrono_literals;

// ============================================================
// Example 1: Wait for all workers to initialize before starting
// ============================================================
void initialization_gate() {
    std::cout << "=== Initialization gate ===\n";
    constexpr int NUM_WORKERS = 5;

    std::latch init_done(NUM_WORKERS);   // counts down from 5
    std::latch start_gate(1);            // released by main thread

    std::vector<std::thread> workers;
    for (int i = 0; i < NUM_WORKERS; ++i) {
        workers.emplace_back([&, i] {
            // Phase 1: Initialize
            std::this_thread::sleep_for(std::chrono::milliseconds(i * 50));
            std::cout << "  Worker " << i << " initialized\n";
            init_done.count_down();  // signal "I'm ready"

            // Phase 2: Wait for all workers to be ready
            start_gate.wait();       // blocks until main releases

            std::cout << "  Worker " << i << " running\n";
        });
    }

    // Main: wait for all initializations, then release everyone
    init_done.wait();  // blocks until count reaches 0
    std::cout << "  All workers initialized, starting!\n";
    start_gate.count_down();  // release all workers

    for (auto& t : workers) t.join();
}

// ============================================================
// Example 2: Fan-in — wait for parallel subtasks
// ============================================================
void fan_in_example() {
    std::cout << "\n=== Fan-in: parallel subtasks ===\n";

    struct Result {
        std::string data;
    };

    constexpr int NUM_TASKS = 4;
    std::vector<Result> results(NUM_TASKS);
    std::latch completion(NUM_TASKS);

    std::vector<std::thread> tasks;
    for (int i = 0; i < NUM_TASKS; ++i) {
        tasks.emplace_back([&results, &completion, i] {
            std::this_thread::sleep_for(std::chrono::milliseconds(100 - i * 20));
            results[i].data = "result_" + std::to_string(i);
            completion.count_down();
        });
    }

    completion.wait();  // all subtasks done
    std::cout << "  All results:";
    for (const auto& r : results) std::cout << " " << r.data;
    std::cout << "\n";

    for (auto& t : tasks) t.join();
}

// ============================================================
// Example 3: One thread counting down multiple times
// ============================================================
void multi_count_example() {
    std::cout << "\n=== Single thread, multiple count_downs ===\n";

    std::latch work_done(10);  // total 10 units of work

    // One thread does 7 units, another does 3
    std::thread t1([&] {
        for (int i = 0; i < 7; ++i) {
            std::cout << "  t1 completed unit " << i << "\n";
            work_done.count_down();
        }
    });

    std::thread t2([&] {
        for (int i = 0; i < 3; ++i) {
            std::cout << "  t2 completed unit " << i << "\n";
            work_done.count_down();
        }
    });

    work_done.wait();
    std::cout << "  All 10 units complete\n";

    t1.join();
    t2.join();
}

// ============================================================
// Example 4: arrive_and_wait (combine count_down + wait)
// ============================================================
void arrive_and_wait_example() {
    std::cout << "\n=== arrive_and_wait ===\n";
    constexpr int N = 3;
    std::latch sync_point(N);

    std::vector<std::thread> threads;
    for (int i = 0; i < N; ++i) {
        threads.emplace_back([&sync_point, i] {
            std::cout << "  Thread " << i << " doing setup\n";
            std::this_thread::sleep_for(std::chrono::milliseconds(i * 100));

            // Atomically: count_down AND wait for count to reach 0
            sync_point.arrive_and_wait();

            std::cout << "  Thread " << i << " past the latch\n";
        });
    }

    for (auto& t : threads) t.join();
}

int main() {
    initialization_gate();
    fan_in_example();
    multi_count_example();
    arrive_and_wait_example();

    std::cout << R"(
=== latch vs barrier ===
  latch:   single-use, count_down can be called multiple times per thread
  barrier: reusable, each thread arrives exactly once per phase

  Use latch when: one-time initialization, fan-in, fire-once gate
  Use barrier when: iterative phases (e.g., simulation steps)
)";

    return 0;
}
```

**Key properties:**
- `count_down(n)`: decrement by n (default 1). A single thread can count down multiple times.
- `wait()`: blocks until count reaches zero. Subsequent calls return immediately (latch stays open).
- `arrive_and_wait()`: equivalent to `count_down(); wait();`
- `try_wait()`: non-blocking check if count has reached zero
- Once the count hits zero, the latch is **permanently open** — it cannot be reset'''),

    ("cpp_deep/barrier_completion_function", r'''Show me std::barrier (C++20) with a completion function for iterative computation phases.''', r'''<think>
std::barrier is a reusable synchronization point. Unlike latch, it resets automatically
after all threads arrive, allowing iterative use. The completion function runs exactly
once per phase, after all threads arrive but before any are released.

Constructor: std::barrier(count, completion_function)
- count: number of threads that must arrive
- completion_function: callable invoked once per phase, on one (unspecified) thread

The completion function is useful for:
- Phase transition logic (swap buffers, accumulate results, check convergence)
- Printing progress
- Deciding whether to continue iteration

arrive_and_wait(): blocks until all threads arrive, runs completion function, releases all.
arrive_and_drop(): thread permanently leaves the barrier (decrements expected count).

Practical example: parallel Jacobi iteration or parallel simulation where threads compute
their portion, barrier syncs, completion function swaps buffers, repeat.

I'll show a parallel computation with phases: each thread processes a chunk of an array,
barrier completion swaps double-buffered arrays, repeat for N iterations.
</think>

`std::barrier` (C++20) is a reusable synchronization point with an optional completion function that runs once per phase. Perfect for iterative parallel algorithms.

```cpp
#include <iostream>
#include <thread>
#include <barrier>
#include <vector>
#include <numeric>
#include <cmath>
#include <functional>
#include <chrono>

using namespace std::chrono_literals;

// ============================================================
// Example 1: Parallel averaging with double-buffering
// Each iteration, each cell becomes the average of its neighbors.
// Completion function swaps source/destination buffers.
// ============================================================
void parallel_averaging() {
    std::cout << "=== Parallel iterative averaging ===\n";

    constexpr int SIZE = 20;
    constexpr int ITERATIONS = 5;
    constexpr int NUM_THREADS = 4;
    constexpr int CHUNK = SIZE / NUM_THREADS;

    std::vector<double> buf_a(SIZE), buf_b(SIZE);
    // Initialize with a spike
    buf_a[SIZE / 2] = 100.0;

    double* src = buf_a.data();
    double* dst = buf_b.data();
    int iteration = 0;

    // Completion function: runs once per phase after all threads arrive
    auto on_phase_complete = [&]() noexcept {
        std::swap(src, dst);
        ++iteration;
        std::cout << "  Phase " << iteration << " complete. Center value: "
                  << src[SIZE / 2] << "\n";
    };

    std::barrier sync_point(NUM_THREADS, on_phase_complete);

    std::vector<std::thread> workers;
    for (int t = 0; t < NUM_THREADS; ++t) {
        int start = t * CHUNK;
        int end = (t == NUM_THREADS - 1) ? SIZE : start + CHUNK;

        workers.emplace_back([&sync_point, &src, &dst, start, end, SIZE] {
            for (int iter = 0; iter < ITERATIONS; ++iter) {
                // Each thread processes its chunk
                for (int i = start; i < end; ++i) {
                    double left  = (i > 0)        ? src[i - 1] : 0.0;
                    double right = (i < SIZE - 1) ? src[i + 1] : 0.0;
                    dst[i] = (left + src[i] + right) / 3.0;
                }
                // Wait for all threads + run completion function
                sync_point.arrive_and_wait();
            }
        });
    }

    for (auto& w : workers) w.join();

    std::cout << "  Final array:";
    for (int i = 0; i < SIZE; ++i) {
        if (src[i] > 0.01) std::cout << " [" << i << "]=" << src[i];
    }
    std::cout << "\n";
}

// ============================================================
// Example 2: Pipeline stages with barrier
// ============================================================
void pipeline_example() {
    std::cout << "\n=== Pipeline with barrier ===\n";

    constexpr int NUM_STAGES = 3;
    constexpr int NUM_ITEMS = 5;

    int phase = 0;
    auto on_complete = [&phase]() noexcept {
        std::cout << "  --- Pipeline phase " << phase++ << " complete ---\n";
    };

    std::barrier sync(NUM_STAGES, on_complete);

    std::vector<std::thread> stages;
    std::string stage_names[] = {"Parse", "Transform", "Output"};

    for (int s = 0; s < NUM_STAGES; ++s) {
        stages.emplace_back([&sync, &stage_names, s] {
            for (int item = 0; item < NUM_ITEMS; ++item) {
                std::cout << "  " << stage_names[s]
                          << " processing item " << item << "\n";
                std::this_thread::sleep_for(
                    std::chrono::milliseconds(20 * (s + 1)));
                sync.arrive_and_wait();
            }
        });
    }

    for (auto& t : stages) t.join();
}

// ============================================================
// Example 3: arrive_and_drop (thread leaves early)
// ============================================================
void drop_example() {
    std::cout << "\n=== arrive_and_drop ===\n";

    int phase = 0;
    auto on_complete = [&phase]() noexcept {
        std::cout << "  Phase " << phase++ << " done\n";
    };

    std::barrier sync(3, on_complete);

    std::thread t1([&sync] {
        for (int i = 0; i < 3; ++i) {
            std::cout << "  t1 phase " << i << "\n";
            sync.arrive_and_wait();
        }
    });

    std::thread t2([&sync] {
        for (int i = 0; i < 3; ++i) {
            std::cout << "  t2 phase " << i << "\n";
            sync.arrive_and_wait();
        }
    });

    std::thread t3([&sync] {
        std::cout << "  t3 phase 0 (then dropping out)\n";
        sync.arrive_and_drop();  // permanently reduces expected count from 3 to 2
        std::cout << "  t3 has left the barrier\n";
    });

    t1.join();
    t2.join();
    t3.join();
}

int main() {
    parallel_averaging();
    pipeline_example();
    drop_example();
    return 0;
}
```

**Key properties of `std::barrier`:**
- **Reusable**: automatically resets after each phase (unlike `latch`)
- **Completion function**: runs once per phase, on an arbitrary arriving thread, before anyone is released. Must be `noexcept`.
- **`arrive_and_drop()`**: permanently reduces the expected count — useful for threads that finish early
- **Phase token**: `arrive()` returns a token that can be passed to `wait(token)` for more advanced patterns

**When to use barrier vs latch:**
| Scenario | Use |
|----------|-----|
| One-time sync (init gate) | `std::latch` |
| Iterative phases (simulation) | `std::barrier` |
| Variable per-thread work units | `std::latch` (count_down multiple times) |
| Phase transition logic | `std::barrier` (completion function) |'''),

    ("cpp_deep/counting_semaphore", r'''How do I use std::counting_semaphore (C++20) to limit concurrent access to a resource? Show me a connection pool example.''', r'''<think>
std::counting_semaphore<N> limits N concurrent accesses. It's like a counter with
acquire() that decrements (blocks if zero) and release() that increments.

std::binary_semaphore is an alias for std::counting_semaphore<1>.

Key difference from mutex:
- Mutex has ownership — only the locking thread can unlock
- Semaphore has no ownership — any thread can release
- Semaphore can have count > 1 (multiple concurrent accesses)

Use cases:
- Connection pool: limit concurrent DB connections
- Rate limiting: limit concurrent API calls
- Producer-consumer: count available items

For a connection pool: semaphore count = max connections. acquire() before getting
a connection, release() after returning it. This naturally limits concurrency.

I'll show a connection pool and a rate limiter.
</think>

`std::counting_semaphore` (C++20) limits the number of concurrent accesses to a resource. Unlike a mutex (which allows exactly 1), a semaphore allows up to N.

```cpp
#include <iostream>
#include <thread>
#include <semaphore>
#include <vector>
#include <queue>
#include <mutex>
#include <string>
#include <chrono>
#include <memory>
#include <atomic>

using namespace std::chrono_literals;

// ============================================================
// Example 1: Database connection pool
// ============================================================
class DatabaseConnection {
    int id_;
public:
    explicit DatabaseConnection(int id) : id_(id) {}

    std::string query(const std::string& sql) {
        std::this_thread::sleep_for(50ms);  // simulate query
        return "result_from_conn_" + std::to_string(id_);
    }

    int id() const { return id_; }
};

class ConnectionPool {
    static constexpr int MAX_CONNECTIONS = 3;

    std::counting_semaphore<MAX_CONNECTIONS> semaphore_{MAX_CONNECTIONS};
    std::mutex mtx_;
    std::queue<std::unique_ptr<DatabaseConnection>> pool_;

public:
    ConnectionPool() {
        for (int i = 0; i < MAX_CONNECTIONS; ++i) {
            pool_.push(std::make_unique<DatabaseConnection>(i));
        }
    }

    // RAII connection handle — returns connection on destruction
    class ConnectionHandle {
        ConnectionPool& pool_;
        std::unique_ptr<DatabaseConnection> conn_;
    public:
        ConnectionHandle(ConnectionPool& pool,
                         std::unique_ptr<DatabaseConnection> conn)
            : pool_(pool), conn_(std::move(conn)) {}

        ~ConnectionHandle() {
            if (conn_) pool_.return_connection(std::move(conn_));
        }

        DatabaseConnection* operator->() { return conn_.get(); }
        DatabaseConnection& operator*() { return *conn_; }

        // Move-only
        ConnectionHandle(ConnectionHandle&&) = default;
        ConnectionHandle& operator=(ConnectionHandle&&) = default;
        ConnectionHandle(const ConnectionHandle&) = delete;
        ConnectionHandle& operator=(const ConnectionHandle&) = delete;
    };

    ConnectionHandle acquire() {
        semaphore_.acquire();  // blocks if all connections are in use

        std::unique_lock lock(mtx_);
        auto conn = std::move(pool_.front());
        pool_.pop();
        return ConnectionHandle(*this, std::move(conn));
    }

private:
    void return_connection(std::unique_ptr<DatabaseConnection> conn) {
        {
            std::lock_guard lock(mtx_);
            pool_.push(std::move(conn));
        }
        semaphore_.release();  // signal that a connection is available
    }
};

// ============================================================
// Example 2: Rate limiter (max N concurrent operations)
// ============================================================
class RateLimiter {
    std::counting_semaphore<> sem_;  // default max = implementation-defined

public:
    explicit RateLimiter(int max_concurrent) : sem_(max_concurrent) {}

    // RAII guard
    class Guard {
        std::counting_semaphore<>& sem_;
    public:
        explicit Guard(std::counting_semaphore<>& s) : sem_(s) { sem_.acquire(); }
        ~Guard() { sem_.release(); }
        Guard(const Guard&) = delete;
        Guard& operator=(const Guard&) = delete;
    };

    Guard enter() { return Guard(sem_); }

    // Try to enter without blocking
    bool try_enter_for(std::chrono::milliseconds timeout) {
        return sem_.try_acquire_for(timeout);
    }
};

// ============================================================
// Example 3: Binary semaphore for signaling (not locking)
// ============================================================
void binary_semaphore_signaling() {
    std::cout << "\n=== Binary semaphore: thread signaling ===\n";

    std::binary_semaphore signal(0);  // starts "not signaled"

    std::thread worker([&signal] {
        std::cout << "  Worker: doing setup...\n";
        std::this_thread::sleep_for(200ms);
        std::cout << "  Worker: setup done, signaling\n";
        signal.release();  // signal the main thread
    });

    std::cout << "  Main: waiting for worker signal...\n";
    signal.acquire();  // blocks until worker calls release()
    std::cout << "  Main: received signal, proceeding\n";

    worker.join();
}

int main() {
    // Connection pool demo
    std::cout << "=== Connection pool (max 3 concurrent) ===\n";
    ConnectionPool pool;
    std::atomic<int> completed{0};

    std::vector<std::thread> clients;
    for (int i = 0; i < 10; ++i) {
        clients.emplace_back([&pool, &completed, i] {
            auto conn = pool.acquire();  // blocks if all 3 are busy
            std::cout << "  Client " << i << " using connection "
                      << conn->id() << "\n";
            auto result = conn->query("SELECT * FROM users");
            ++completed;
            // Connection returned automatically via RAII
        });
    }

    for (auto& t : clients) t.join();
    std::cout << "  Completed: " << completed.load() << " queries\n";

    // Rate limiter demo
    std::cout << "\n=== Rate limiter (max 2 concurrent) ===\n";
    RateLimiter limiter(2);

    std::vector<std::thread> tasks;
    for (int i = 0; i < 6; ++i) {
        tasks.emplace_back([&limiter, i] {
            auto guard = limiter.enter();
            std::cout << "  Task " << i << " running\n";
            std::this_thread::sleep_for(100ms);
            std::cout << "  Task " << i << " done\n";
        });
    }
    for (auto& t : tasks) t.join();

    binary_semaphore_signaling();

    return 0;
}
```

**Semaphore vs mutex vs condition_variable:**

| Feature | mutex | semaphore | condition_variable |
|---------|-------|-----------|--------------------|
| Max concurrent | 1 | N | N/A (for signaling) |
| Ownership | Yes (same thread must unlock) | No (any thread can release) | N/A |
| Use case | Mutual exclusion | Resource limiting | Wait for condition |
| Can signal from other thread | No | Yes | Yes |

**Key API:**
- `acquire()`: blocks until count > 0, then decrements
- `release(n)`: increments count by n (default 1), wakes waiting threads
- `try_acquire()`: non-blocking attempt
- `try_acquire_for(duration)`: timed blocking attempt'''),

    ("cpp_deep/parallel_execution_policies", r'''Show me how to use C++17 parallel algorithms with execution policies. What are the gotchas?''', r'''<think>
C++17 added execution policies to standard algorithms:
- std::execution::seq — sequential (same as no policy)
- std::execution::par — parallel execution
- std::execution::par_unseq — parallel + vectorized (SIMD)
- C++20 added std::execution::unseq — vectorized but single-threaded

Key gotchas:
1. Not all standard library implementations support parallel algorithms (libstdc++ needs TBB)
2. par requires thread-safe element access functions (no data races in predicates/ops)
3. par_unseq requires additionally: no locks, no memory allocation, no syscalls in callbacks
   (because vectorization may interleave operations within a single thread)
4. Exceptions: if an exception is thrown during parallel execution, std::terminate is called
5. Performance: small datasets may be slower due to thread spawning overhead
6. Iterator requirements: par needs at least ForwardIterator

I should show: sort, transform, reduce, and for_each with execution policies.
Also show the gotcha with par_unseq and locks.

Need to mention: compile with -ltbb on GCC/libstdc++.
</think>

C++17 execution policies let you parallelize standard algorithms with a single extra argument. Here are the policies, practical usage, and the important gotchas:

```cpp
#include <iostream>
#include <vector>
#include <algorithm>
#include <numeric>
#include <execution>
#include <chrono>
#include <mutex>
#include <cmath>
#include <random>

class Timer {
    std::chrono::high_resolution_clock::time_point start_;
    std::string label_;
public:
    explicit Timer(std::string label)
        : start_(std::chrono::high_resolution_clock::now()), label_(std::move(label)) {}
    ~Timer() {
        auto elapsed = std::chrono::high_resolution_clock::now() - start_;
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count();
        std::cout << "  " << label_ << ": " << ms << " ms\n";
    }
};

int main() {
    constexpr int N = 10'000'000;
    std::vector<double> data(N);

    // Initialize with random data
    std::mt19937 rng(42);
    std::uniform_real_distribution<double> dist(0.0, 1000.0);
    std::generate(data.begin(), data.end(), [&] { return dist(rng); });

    // ============================================================
    // 1. Parallel sort
    // ============================================================
    std::cout << "=== sort ===\n";
    {
        auto d = data;
        Timer t("seq");
        std::sort(std::execution::seq, d.begin(), d.end());
    }
    {
        auto d = data;
        Timer t("par");
        std::sort(std::execution::par, d.begin(), d.end());
    }

    // ============================================================
    // 2. Parallel transform (element-wise computation)
    // ============================================================
    std::cout << "\n=== transform (sqrt of each element) ===\n";
    std::vector<double> results(N);
    {
        Timer t("seq");
        std::transform(std::execution::seq,
                       data.begin(), data.end(), results.begin(),
                       [](double x) { return std::sqrt(x); });
    }
    {
        Timer t("par_unseq");
        std::transform(std::execution::par_unseq,
                       data.begin(), data.end(), results.begin(),
                       [](double x) { return std::sqrt(x); });
    }

    // ============================================================
    // 3. Parallel reduce (sum)
    // ============================================================
    std::cout << "\n=== reduce (sum) ===\n";
    {
        Timer t("seq");
        double sum = std::reduce(std::execution::seq,
                                 data.begin(), data.end(), 0.0);
        std::cout << "  sum=" << sum << "\n";
    }
    {
        Timer t("par");
        double sum = std::reduce(std::execution::par,
                                 data.begin(), data.end(), 0.0);
        std::cout << "  sum=" << sum << "\n";
    }
    // NOTE: reduce with floating-point may give slightly different results
    // due to non-deterministic reduction order. Use accumulate for exact order.

    // ============================================================
    // 4. Parallel for_each
    // ============================================================
    std::cout << "\n=== for_each ===\n";
    {
        Timer t("par");
        std::for_each(std::execution::par, data.begin(), data.end(),
                      [](double& x) { x = std::sin(x) * std::cos(x); });
    }

    // ============================================================
    // 5. Parallel find / count / any_of
    // ============================================================
    std::cout << "\n=== count_if ===\n";
    {
        Timer t("par");
        auto count = std::count_if(std::execution::par,
                                   data.begin(), data.end(),
                                   [](double x) { return x > 0.0; });
        std::cout << "  count > 0: " << count << "\n";
    }

    // ============================================================
    // 6. transform_reduce (map-reduce in one call)
    // ============================================================
    std::cout << "\n=== transform_reduce (sum of squares) ===\n";
    {
        Timer t("par");
        double sum_sq = std::transform_reduce(
            std::execution::par,
            data.begin(), data.end(),
            0.0,                                // init
            std::plus<>{},                      // reduce op
            [](double x) { return x * x; }     // transform op
        );
        std::cout << "  sum of squares: " << sum_sq << "\n";
    }

    // ============================================================
    // GOTCHAS
    // ============================================================
    std::cout << R"(
=== GOTCHAS ===

1. WRONG: mutex in par_unseq (may deadlock — same thread reentrant)
   std::mutex m;
   std::for_each(std::execution::par_unseq, v.begin(), v.end(),
       [&m](int x) {
           std::lock_guard lock(m);  // BUG: par_unseq may interleave
                                     // on SAME thread (vectorized)
       });

2. WRONG: data race in par
   int count = 0;
   std::for_each(std::execution::par, v.begin(), v.end(),
       [&count](int x) { if (x > 0) ++count; });  // DATA RACE
   // Fix: use std::count_if, or std::atomic<int>

3. Floating-point non-determinism:
   std::reduce with par may sum in different order → different rounding
   Use std::accumulate (sequential) if exact reproducibility is needed

4. Compiler/library support:
   - GCC/libstdc++: link with -ltbb (Intel TBB required)
   - Clang/libc++: limited support
   - MSVC: built-in support, works out of the box

5. Small datasets: parallel overhead > benefit. Profile first.
)";

    return 0;
}
```

**Compile:**
- MSVC: `cl /std:c++17 /EHsc parallel.cpp` (just works)
- GCC: `g++ -std=c++17 -ltbb -O2 parallel.cpp`

**Execution policy rules:**

| Policy | Threading | SIMD | Callbacks must NOT |
|--------|-----------|------|--------------------|
| `seq` | No | No | (anything goes) |
| `unseq` (C++20) | No | Yes | Use locks, allocate, syscalls |
| `par` | Yes | No | Have data races |
| `par_unseq` | Yes | Yes | Use locks, data races, allocate, syscalls |'''),

    ("cpp_deep/atomic_ref_external", r'''What is std::atomic_ref (C++20) and when would I use it instead of std::atomic?''', r'''<think>
std::atomic_ref<T> provides atomic operations on a non-atomic object. You create an
atomic_ref that refers to a regular T, and all accesses through the atomic_ref are atomic.

Key use cases:
1. You have data in arrays/containers that you sometimes need to access atomically
2. You're interfacing with legacy code or C APIs that use plain types
3. You want atomic access to members of a struct without making them std::atomic<T>
   (which changes layout, alignment, and prevents aggregate initialization)
4. Performance: std::atomic<T> may have overhead even for non-concurrent access
   due to alignment requirements or volatile-like semantics

Important rules:
- All concurrent accesses must go through atomic_ref (or be otherwise synchronized)
- The underlying object must be properly aligned (std::atomic_ref<T>::required_alignment)
- Multiple atomic_refs to the same object are fine — they all see the same atomic state
- The object must outlive all atomic_refs to it
- You can mix atomic_ref access with non-atomic access, but not concurrently

This is particularly useful for SIMD-friendly arrays where you want normal array
layout but occasional atomic operations on specific elements.
</think>

`std::atomic_ref<T>` (C++20) provides atomic operations on an existing non-atomic variable. This avoids the layout, alignment, and initialization restrictions of `std::atomic<T>`.

```cpp
#include <iostream>
#include <thread>
#include <atomic>
#include <vector>
#include <array>
#include <numeric>
#include <cstddef>

// ============================================================
// Problem: std::atomic<T> prevents aggregate init and changes layout
// ============================================================
struct SensorData_Atomic {
    std::atomic<double> temperature;  // Can't aggregate-initialize
    std::atomic<double> humidity;     // std::atomic<double> may have different alignment
    std::atomic<int> readings;
    // SensorData_Atomic s = {20.0, 50.0, 0};  // ERROR: no aggregate init
};

// Solution: plain struct + atomic_ref for concurrent access
struct SensorData {
    alignas(std::atomic_ref<double>::required_alignment) double temperature;
    alignas(std::atomic_ref<double>::required_alignment) double humidity;
    alignas(std::atomic_ref<int>::required_alignment) int readings;
};

// ============================================================
// Example 1: Concurrent updates to plain struct members
// ============================================================
void sensor_example() {
    std::cout << "=== atomic_ref on struct members ===\n";

    SensorData sensor = {20.0, 50.0, 0};  // aggregate initialization works!

    std::vector<std::thread> threads;
    for (int i = 0; i < 8; ++i) {
        threads.emplace_back([&sensor, i] {
            for (int j = 0; j < 1000; ++j) {
                // Create atomic_ref on-the-fly for concurrent access
                std::atomic_ref<double> temp(sensor.temperature);
                std::atomic_ref<int> count(sensor.readings);

                // Atomic read-modify-write on plain double
                double old_temp = temp.load(std::memory_order_relaxed);
                temp.store(old_temp + 0.001, std::memory_order_relaxed);
                count.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }
    for (auto& t : threads) t.join();

    std::cout << "  Temperature: " << sensor.temperature << "\n";
    std::cout << "  Readings: " << sensor.readings << " (expected 8000)\n";
}

// ============================================================
// Example 2: Atomic access to array elements
// (SIMD-friendly layout, occasional atomic ops)
// ============================================================
void array_example() {
    std::cout << "\n=== atomic_ref on array elements ===\n";

    constexpr int SIZE = 16;
    // Regular array — no atomic overhead for normal access
    alignas(std::atomic_ref<int>::required_alignment) int counters[SIZE] = {};

    std::vector<std::thread> threads;
    for (int t = 0; t < 4; ++t) {
        threads.emplace_back([&counters, t] {
            for (int i = 0; i < 10000; ++i) {
                int idx = (t * 4 + i) % SIZE;
                // Atomic increment on a specific array element
                std::atomic_ref<int> elem(counters[idx]);
                elem.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }
    for (auto& t : threads) t.join();

    int total = std::accumulate(std::begin(counters), std::end(counters), 0);
    std::cout << "  Total increments: " << total << " (expected 40000)\n";
}

// ============================================================
// Example 3: Interfacing with C API or legacy code
// ============================================================
struct LegacyConfig {
    int max_connections;
    int timeout_ms;
    int debug_level;
};

// Legacy C function that returns a pointer to shared config
LegacyConfig* get_global_config() {
    alignas(std::atomic_ref<int>::required_alignment)
    static LegacyConfig config = {100, 5000, 0};
    return &config;
}

void legacy_example() {
    std::cout << "\n=== atomic_ref with legacy types ===\n";

    auto* config = get_global_config();

    std::thread reader([config] {
        for (int i = 0; i < 100; ++i) {
            std::atomic_ref<int> level(config->debug_level);
            int val = level.load(std::memory_order_acquire);
            if (val == 42) {
                std::cout << "  Reader saw debug_level=42\n";
                return;
            }
        }
    });

    std::thread writer([config] {
        std::this_thread::sleep_for(std::chrono::microseconds(10));
        std::atomic_ref<int> level(config->debug_level);
        level.store(42, std::memory_order_release);
    });

    reader.join();
    writer.join();
    std::cout << "  Final debug_level: " << config->debug_level << "\n";
}

// ============================================================
// Alignment check utility
// ============================================================
void alignment_info() {
    std::cout << "\n=== Alignment requirements ===\n";
    std::cout << "  atomic_ref<int>:    " << std::atomic_ref<int>::required_alignment << "\n";
    std::cout << "  atomic_ref<double>: " << std::atomic_ref<double>::required_alignment << "\n";
    std::cout << "  atomic_ref<long long>: "
              << std::atomic_ref<long long>::required_alignment << "\n";

    // Check if lock-free
    alignas(std::atomic_ref<double>::required_alignment) double val = 0.0;
    std::atomic_ref<double> ref(val);
    std::cout << "  atomic_ref<double> lock-free: "
              << std::boolalpha << ref.is_lock_free() << "\n";
}

int main() {
    sensor_example();
    array_example();
    legacy_example();
    alignment_info();
    return 0;
}
```

**When to use `atomic_ref<T>` vs `atomic<T>`:**

| Scenario | Use |
|----------|-----|
| Dedicated concurrent variable | `std::atomic<T>` |
| Aggregate struct with occasional atomic access | `std::atomic_ref<T>` |
| Array with SIMD-friendly layout | `std::atomic_ref<T>` |
| C interop / legacy code | `std::atomic_ref<T>` |
| Performance-critical path (avoid atomic overhead on non-concurrent access) | `std::atomic_ref<T>` |

**Critical rule:** the underlying object must be aligned to `std::atomic_ref<T>::required_alignment`. Use `alignas()` to ensure this.'''),

    ("cpp_deep/hazard_pointers_concept", r'''Explain hazard pointers for lock-free memory reclamation. How do they solve the use-after-free problem in lock-free data structures?''', r'''<think>
Hazard pointers solve the fundamental problem of lock-free memory reclamation:
"When is it safe to delete a node that was removed from a lock-free data structure?"

The problem: In a lock-free stack or list, when you pop a node, another thread might
still be reading that node (dereferencing its ->next pointer). You can't delete it
immediately because that would cause use-after-free.

Hazard pointers: Each thread publishes "I am currently accessing this pointer" in a
shared array. Before deleting a node, you check all hazard pointers. If any thread
has a hazard pointer to that node, defer deletion.

Algorithm:
1. Before accessing a shared node, publish its address as your hazard pointer
2. Re-verify the node is still valid (could have changed between read and publish)
3. Do your operation
4. Clear your hazard pointer when done
5. When retiring a node, add it to a thread-local retired list
6. Periodically scan all hazard pointers and delete retired nodes that aren't hazardous

The tricky part is step 2: the validation loop. You must ensure the hazard pointer
was published before anyone could delete the node.

C++26 is adding std::hazard_pointer to the standard. But the concept is useful now.

Let me show a simplified but correct implementation with a lock-free stack.
</think>

Hazard pointers solve the memory reclamation problem in lock-free data structures: **when can you safely free a node that another thread might still be reading?**

```cpp
#include <iostream>
#include <thread>
#include <atomic>
#include <vector>
#include <unordered_set>
#include <functional>
#include <cassert>

// ============================================================
// Simplified Hazard Pointer system
// ============================================================
template<typename T>
class HazardPointerDomain {
    static constexpr int MAX_THREADS = 32;
    static constexpr int SCAN_THRESHOLD = 16;  // scan when retired list grows

    // Global array of hazard pointers (one per thread)
    std::atomic<T*> hazard_ptrs_[MAX_THREADS] = {};
    std::atomic<bool> slot_used_[MAX_THREADS] = {};

    // Per-thread retired nodes (thread-local storage)
    struct ThreadData {
        int slot = -1;
        std::vector<T*> retired;
        HazardPointerDomain* domain = nullptr;

        ~ThreadData() {
            // Final cleanup: force-delete everything
            // (In production, this requires more careful handling)
            if (domain) domain->clear_hazard(slot);
            for (T* p : retired) delete p;
        }
    };

    static thread_local ThreadData tls_;

public:
    // Acquire a slot for the current thread
    int acquire_slot() {
        if (tls_.slot >= 0) return tls_.slot;
        for (int i = 0; i < MAX_THREADS; ++i) {
            bool expected = false;
            if (slot_used_[i].compare_exchange_strong(expected, true)) {
                tls_.slot = i;
                tls_.domain = this;
                return i;
            }
        }
        throw std::runtime_error("No hazard pointer slots available");
    }

    // Step 1: Publish hazard pointer (announce "I'm reading this")
    void set_hazard(int slot, T* ptr) {
        hazard_ptrs_[slot].store(ptr, std::memory_order_release);
    }

    void clear_hazard(int slot) {
        hazard_ptrs_[slot].store(nullptr, std::memory_order_release);
    }

    // Step 2: Retire a node (defer deletion until safe)
    void retire(T* ptr) {
        int slot = acquire_slot();
        tls_.retired.push_back(ptr);
        if (tls_.retired.size() >= SCAN_THRESHOLD) {
            scan();
        }
    }

    // Step 3: Scan and delete nodes that no thread is reading
    void scan() {
        // Collect all active hazard pointers
        std::unordered_set<T*> hazardous;
        for (int i = 0; i < MAX_THREADS; ++i) {
            T* hp = hazard_ptrs_[i].load(std::memory_order_acquire);
            if (hp) hazardous.insert(hp);
        }

        // Delete retired nodes that aren't in any hazard pointer
        auto& retired = tls_.retired;
        auto it = retired.begin();
        while (it != retired.end()) {
            if (hazardous.find(*it) == hazardous.end()) {
                delete *it;
                it = retired.erase(it);
            } else {
                ++it;  // still hazardous, keep in retired list
            }
        }
    }
};

template<typename T>
thread_local typename HazardPointerDomain<T>::ThreadData
    HazardPointerDomain<T>::tls_;

// ============================================================
// Lock-free stack using hazard pointers
// ============================================================
struct Node {
    int data;
    Node* next;
    Node(int d) : data(d), next(nullptr) {}
};

class SafeLockFreeStack {
    std::atomic<Node*> head_{nullptr};
    HazardPointerDomain<Node> hp_domain_;

public:
    void push(int value) {
        Node* new_node = new Node(value);
        new_node->next = head_.load(std::memory_order_relaxed);
        while (!head_.compare_exchange_weak(
            new_node->next, new_node,
            std::memory_order_release,
            std::memory_order_relaxed)) {}
    }

    bool pop(int& result) {
        int slot = hp_domain_.acquire_slot();

        Node* old_head;
        while (true) {
            old_head = head_.load(std::memory_order_acquire);
            if (!old_head) return false;  // empty

            // Publish hazard pointer BEFORE dereferencing
            hp_domain_.set_hazard(slot, old_head);

            // Validate: head might have changed between load and set_hazard
            if (head_.load(std::memory_order_acquire) != old_head) {
                continue;  // retry — our hazard pointer might be stale
            }

            // Safe to dereference old_head->next (protected by hazard pointer)
            Node* new_head = old_head->next;

            if (head_.compare_exchange_strong(
                    old_head, new_head,
                    std::memory_order_acq_rel,
                    std::memory_order_relaxed)) {
                break;  // successfully popped
            }
            // CAS failed, retry
        }

        // Clear hazard pointer — we're done reading the node
        hp_domain_.clear_hazard(slot);

        result = old_head->data;

        // Retire the node — will be deleted when no thread has a hazard pointer to it
        hp_domain_.retire(old_head);

        return true;
    }

    ~SafeLockFreeStack() {
        int val;
        while (pop(val)) {}
    }
};

// ============================================================
// Demo
// ============================================================
int main() {
    std::cout << "=== Lock-free stack with hazard pointers ===\n";

    SafeLockFreeStack stack;
    std::atomic<int> push_count{0}, pop_count{0};

    std::vector<std::thread> threads;

    // 4 producer threads
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&stack, &push_count, i] {
            for (int j = 0; j < 1000; ++j) {
                stack.push(i * 1000 + j);
                push_count.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }

    // 4 consumer threads
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&stack, &pop_count] {
            int val;
            for (int j = 0; j < 1000; ++j) {
                while (!stack.pop(val)) {
                    std::this_thread::yield();
                }
                pop_count.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }

    for (auto& t : threads) t.join();

    std::cout << "  Pushed: " << push_count.load() << "\n";
    std::cout << "  Popped: " << pop_count.load() << "\n";
    std::cout << "  No use-after-free, no memory leaks\n";

    std::cout << R"(
=== Hazard pointer protocol ===
  1. PUBLISH:  Set hazard pointer to the node you want to read
  2. VALIDATE: Re-check the source pointer hasn't changed
  3. ACCESS:   Dereference the node (safe — protected by HP)
  4. CLEAR:    Remove your hazard pointer
  5. RETIRE:   Add removed nodes to a thread-local retired list
  6. SCAN:     Periodically delete retired nodes not in any HP

=== Comparison of reclamation schemes ===
  Hazard Pointers: bounded memory overhead, per-node protection
  Epoch-Based (EBR): simpler, but one slow thread delays all reclamation
  RCU: best reader performance, complex writer side
  Reference Counting: simple but high overhead (atomic inc/dec per access)

Note: C++26 std::hazard_pointer will standardize this.
)";

    return 0;
}
```

The critical invariant: **a node is never freed while any thread's hazard pointer points to it.** The validate-after-publish step (step 2) ensures the hazard pointer was set before the node could be removed from the data structure.'''),

    ("cpp_deep/double_checked_locking", r'''Show me how to implement double-checked locking correctly in C++. I heard it is broken without proper memory ordering.''', r'''<think>
Double-checked locking (DCL) is a pattern for lazy initialization of a singleton or
shared resource. The naive version is broken without proper memory ordering.

The problem:
1. Thread A checks if ptr is null (no lock) — sees null
2. Thread A locks mutex, checks again (double check), creates object, sets ptr
3. Thread B checks if ptr is null (no lock) — sees non-null
4. Thread B uses ptr... but the object's constructor may not have completed yet!

Why? On CPUs with weak memory ordering (ARM, POWER), the store to ptr can be reordered
before the constructor's stores. So thread B sees a non-null pointer to an
uninitialized object.

Fix: use std::atomic<T*> with acquire/release ordering:
- Store to ptr with memory_order_release (after constructor)
- Load from ptr with memory_order_acquire (before using the object)

Or better: just use std::call_once / static local variables (C++11 guarantees
thread-safe static local initialization).

I should show: broken version, fixed atomic version, and the preferred C++ alternatives.

Actually the simplest C++ solution is a function-local static:
  Foo& get_instance() { static Foo instance; return instance; }
C++11 guarantees this is thread-safe (the compiler inserts the necessary barriers).
</think>

Double-checked locking (DCL) is notoriously error-prone. The naive version is broken on CPUs with weak memory ordering. Here are the broken version, the correct fix, and the preferred C++ alternatives:

```cpp
#include <iostream>
#include <thread>
#include <mutex>
#include <atomic>
#include <memory>
#include <vector>

class ExpensiveResource {
    int data_[100];
public:
    ExpensiveResource() {
        // Simulate expensive initialization
        for (int i = 0; i < 100; ++i) data_[i] = i * 42;
        std::cout << "  ExpensiveResource constructed\n";
    }
    int check() const { return data_[99]; }
};

// ============================================================
// BROKEN: Naive double-checked locking
// ============================================================
class Singleton_BROKEN {
    static ExpensiveResource* instance_;
    static std::mutex mtx_;

public:
    static ExpensiveResource& get() {
        if (instance_ == nullptr) {          // First check (no lock)
            std::lock_guard lock(mtx_);
            if (instance_ == nullptr) {      // Second check (with lock)
                instance_ = new ExpensiveResource();
                // BUG: On ARM/POWER, the compiler or CPU can reorder:
                //   1. Allocate memory
                //   2. Store pointer to instance_ (other threads see non-null!)
                //   3. Run constructor (not finished yet!)
                // Thread B sees non-null instance_ but reads uninitialized data
            }
        }
        return *instance_;
    }
};
ExpensiveResource* Singleton_BROKEN::instance_ = nullptr;
std::mutex Singleton_BROKEN::mtx_;

// ============================================================
// CORRECT: DCL with std::atomic and proper memory ordering
// ============================================================
class Singleton_Atomic {
    static std::atomic<ExpensiveResource*> instance_;
    static std::mutex mtx_;

public:
    static ExpensiveResource& get() {
        // Acquire load: if non-null, we're guaranteed to see the
        // fully constructed object (pairs with release store below)
        auto* ptr = instance_.load(std::memory_order_acquire);

        if (ptr == nullptr) {
            std::lock_guard lock(mtx_);
            ptr = instance_.load(std::memory_order_relaxed);  // re-check under lock
            if (ptr == nullptr) {
                ptr = new ExpensiveResource();
                // Release store: guarantees all constructor writes are
                // visible before the pointer becomes non-null
                instance_.store(ptr, std::memory_order_release);
            }
        }
        return *ptr;
    }
};
std::atomic<ExpensiveResource*> Singleton_Atomic::instance_{nullptr};
std::mutex Singleton_Atomic::mtx_;

// ============================================================
// BEST: std::call_once (cleaner, same performance)
// ============================================================
class Singleton_CallOnce {
    static std::unique_ptr<ExpensiveResource> instance_;
    static std::once_flag flag_;

public:
    static ExpensiveResource& get() {
        std::call_once(flag_, [] {
            instance_ = std::make_unique<ExpensiveResource>();
        });
        return *instance_;
    }
};
std::unique_ptr<ExpensiveResource> Singleton_CallOnce::instance_;
std::once_flag Singleton_CallOnce::flag_;

// ============================================================
// BEST: C++11 static local (Meyers' Singleton)
// ============================================================
class Singleton_Static {
public:
    static ExpensiveResource& get() {
        // C++11 guarantees thread-safe initialization of static locals
        // The compiler generates the necessary barriers internally
        static ExpensiveResource instance;
        return instance;
    }
};

// ============================================================
// Generic lazy<T> with DCL done right
// ============================================================
template<typename T>
class Lazy {
    std::atomic<T*> ptr_{nullptr};
    std::mutex mtx_;
    std::function<T*()> factory_;

public:
    explicit Lazy(std::function<T*()> factory)
        : factory_(std::move(factory)) {}

    T& get() {
        T* ptr = ptr_.load(std::memory_order_acquire);
        if (!ptr) {
            std::lock_guard lock(mtx_);
            ptr = ptr_.load(std::memory_order_relaxed);
            if (!ptr) {
                ptr = factory_();
                ptr_.store(ptr, std::memory_order_release);
            }
        }
        return *ptr;
    }

    ~Lazy() {
        delete ptr_.load(std::memory_order_relaxed);
    }
};

// ============================================================
// Demo
// ============================================================
int main() {
    std::cout << "=== Atomic DCL ===\n";
    std::vector<std::thread> threads;
    for (int i = 0; i < 8; ++i) {
        threads.emplace_back([] {
            auto& r = Singleton_Atomic::get();
            std::cout << "  Thread " << std::this_thread::get_id()
                      << " check=" << r.check() << "\n";
        });
    }
    for (auto& t : threads) t.join();
    threads.clear();

    std::cout << "\n=== Meyers' Singleton (preferred) ===\n";
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([] {
            auto& r = Singleton_Static::get();
            std::cout << "  Thread " << std::this_thread::get_id()
                      << " check=" << r.check() << "\n";
        });
    }
    for (auto& t : threads) t.join();
    threads.clear();

    std::cout << "\n=== Generic Lazy<T> ===\n";
    Lazy<ExpensiveResource> lazy([] { return new ExpensiveResource(); });
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&lazy] {
            std::cout << "  Lazy check=" << lazy.get().check() << "\n";
        });
    }
    for (auto& t : threads) t.join();

    return 0;
}
```

**Recommendation hierarchy:**
1. **Meyers' Singleton** (`static` local) — simplest, compiler handles everything
2. **`std::call_once`** — when you need more control over the initialization
3. **Atomic DCL** — when you need a generic `Lazy<T>` or non-singleton patterns
4. **Never use raw pointer DCL** without `std::atomic` + acquire/release'''),

    ("cpp_deep/thread_local_patterns", r'''Show me practical uses of thread_local in C++. What are the gotchas with thread-local storage?''', r'''<think>
thread_local gives each thread its own copy of a variable. Introduced in C++11 to
replace the non-standard __thread and __declspec(thread).

Use cases:
1. Per-thread caches (avoid contention)
2. Per-thread allocators / memory pools
3. Per-thread random number generators
4. errno-style error codes
5. Per-thread statistics / counters
6. Thread-safe singleton per thread

Gotchas:
1. Destruction order: thread_local objects are destroyed when the thread exits,
   in reverse order of construction. But for detached threads, destructors may not
   run (implementation-defined).
2. DLL/shared library issues: on Windows, thread_local in DLLs can cause issues
   with DllMain threading rules.
3. Performance: first access to thread_local may be slower (TLS lookup).
4. Memory: each thread gets its own copy, so many threads = many copies.
5. thread_local in header files: each TU gets its own definition if not inline.
   Use inline thread_local in headers (C++17).
6. Interaction with thread pools: thread_local state persists across tasks —
   this can be a feature or a bug depending on expectations.

Let me show practical examples covering these.
</think>

`thread_local` gives each thread its own independent copy of a variable. Here are practical patterns and the important gotchas:

```cpp
#include <iostream>
#include <thread>
#include <vector>
#include <string>
#include <random>
#include <numeric>
#include <unordered_map>
#include <mutex>
#include <sstream>

// ============================================================
// Pattern 1: Per-thread RNG (avoid mutex contention)
// ============================================================
int thread_safe_random(int min, int max) {
    // Each thread gets its own engine, seeded differently
    thread_local std::mt19937 engine(
        std::hash<std::thread::id>{}(std::this_thread::get_id())
    );
    std::uniform_int_distribution<int> dist(min, max);
    return dist(engine);
}

// ============================================================
// Pattern 2: Per-thread cache (avoid sharing / locking)
// ============================================================
class ExpensiveComputer {
    // Each thread has its own cache — no locking needed
    thread_local static std::unordered_map<int, double> cache_;

public:
    static double compute(int input) {
        auto it = cache_.find(input);
        if (it != cache_.end()) return it->second;

        // Expensive computation
        double result = 0;
        for (int i = 1; i <= input; ++i) result += 1.0 / i;

        cache_[input] = result;
        return result;
    }

    static void clear_cache() { cache_.clear(); }
    static size_t cache_size() { return cache_.size(); }
};

thread_local std::unordered_map<int, double> ExpensiveComputer::cache_;

// ============================================================
// Pattern 3: Per-thread counters (aggregate at end)
// ============================================================
struct ThreadStats {
    long long operations = 0;
    long long cache_hits = 0;
    long long cache_misses = 0;

    // Global collection
    static std::mutex mtx;
    static std::vector<ThreadStats> all_stats;

    ~ThreadStats() {
        // Auto-report when thread exits
        std::lock_guard lock(mtx);
        all_stats.push_back(*this);
    }
};

std::mutex ThreadStats::mtx;
std::vector<ThreadStats> ThreadStats::all_stats;

thread_local ThreadStats t_stats;  // one per thread

// ============================================================
// Pattern 4: errno-style last error (per-thread error context)
// ============================================================
struct ErrorContext {
    int code = 0;
    std::string message;
};

thread_local ErrorContext last_error;

void set_error(int code, const std::string& msg) {
    last_error.code = code;
    last_error.message = msg;
}

const ErrorContext& get_last_error() {
    return last_error;
}

// ============================================================
// Pattern 5: Thread-local string buffer (avoid allocation)
// ============================================================
const std::string& thread_id_string() {
    thread_local std::string cached = [] {
        std::ostringstream oss;
        oss << std::this_thread::get_id();
        return oss.str();
    }();
    return cached;
}

// ============================================================
// GOTCHA 1: thread_local in thread pools
// ============================================================
void thread_pool_gotcha() {
    std::cout << "\n=== GOTCHA: thread_local in thread pools ===\n";

    // Problem: thread_local state persists across tasks in a pool
    thread_local int task_count = 0;

    auto run_task = [](int task_id) {
        ++task_count;  // This accumulates across tasks on the same thread!
        std::cout << "  Task " << task_id
                  << " on thread " << std::this_thread::get_id()
                  << " (task_count=" << task_count << ")\n";
    };

    // Simulate a thread pool reusing threads
    std::thread t1([&] {
        run_task(1);
        run_task(2);  // task_count is now 2, not 1!
        run_task(3);  // task_count is now 3
    });
    t1.join();

    std::cout << "  Fix: explicitly reset thread_local state at task boundaries\n";
}

// ============================================================
// GOTCHA 2: inline thread_local for header-only (C++17)
// ============================================================
// In a header file, use `inline thread_local` to avoid ODR violations:
//   inline thread_local int per_thread_value = 0;
// Without `inline`, each TU gets a separate variable.

int main() {
    std::cout << "=== Per-thread RNG ===\n";
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([i] {
            int val = thread_safe_random(1, 100);
            std::cout << "  Thread " << i << " random: " << val << "\n";
        });
    }
    for (auto& t : threads) t.join();
    threads.clear();

    std::cout << "\n=== Per-thread cache ===\n";
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([i] {
            // Each thread builds its own cache independently
            for (int j = 1; j <= 10; ++j) {
                ExpensiveComputer::compute(j);
            }
            ExpensiveComputer::compute(5);  // cache hit (per-thread)
            std::cout << "  Thread " << i << " cache size: "
                      << ExpensiveComputer::cache_size() << "\n";
        });
    }
    for (auto& t : threads) t.join();
    threads.clear();

    std::cout << "\n=== Per-thread error context ===\n";
    std::thread err_demo([] {
        set_error(404, "not found");
        auto& err = get_last_error();
        std::cout << "  Error: " << err.code << " " << err.message << "\n";
    });
    err_demo.join();
    // Main thread's error is independent
    std::cout << "  Main thread error code: " << get_last_error().code
              << " (should be 0)\n";

    thread_pool_gotcha();

    std::cout << R"(
=== thread_local gotchas summary ===
  1. Thread pool reuse: state persists across tasks (reset explicitly)
  2. Detached threads: destructors may not run
  3. DLL boundaries: may not work across DLL loads on Windows
  4. Performance: first access has TLS lookup overhead
  5. Memory: N threads × sizeof(T) — watch for large thread_local objects
  6. Headers: use `inline thread_local` (C++17) to avoid ODR violations
)";

    return 0;
}
```

**When to use `thread_local`:**
- Per-thread caches, RNGs, allocators, error contexts
- Avoiding mutex contention on frequently-accessed data
- Statistics/counters that are aggregated at sync points

**When NOT to use:**
- In thread pools without explicit reset (stale state between tasks)
- For large objects when thread count is high (memory waste)
- When data needs to be shared between threads (use atomics/mutexes instead)'''),

    ("cpp_deep/false_sharing_cacheline", r'''What is false sharing and how do I prevent it? I have threads each working on their own counter but performance is terrible.''', r'''<think>
False sharing occurs when two or more threads access different variables that happen to
reside on the same CPU cache line (typically 64 bytes). Even though the threads are
writing to different variables, the CPU's cache coherency protocol (MESI) treats the
entire cache line as the unit of sharing.

When thread A writes to its variable, thread B's cache line is invalidated even though
thread B is accessing a different variable. Thread B must reload the cache line from
main memory (or another core's cache). This back-and-forth invalidation can cause
100x slowdown compared to properly aligned data.

Solutions:
1. alignas(std::hardware_destructive_interference_size) — C++17
2. Manual padding to 64 bytes
3. Thread-local variables (each thread's TLS is on different pages)

std::hardware_destructive_interference_size: minimum offset between two objects to
avoid false sharing. Typically 64 bytes on x86, 128 on some ARM.

std::hardware_constructive_interference_size: maximum size of two objects that can
share a cache line for true sharing (when you WANT them on the same line).

I should show: the problem with a benchmark, then the fix with alignment.
The benchmark should be dramatic — false sharing can show 5-10x slowdown.
</think>

False sharing is one of the most insidious performance killers in concurrent code. It happens when threads write to different variables that share the same CPU cache line.

```cpp
#include <iostream>
#include <thread>
#include <vector>
#include <atomic>
#include <chrono>
#include <new>  // hardware_destructive_interference_size

#ifdef __cpp_lib_hardware_interference_size
    static constexpr std::size_t CACHE_LINE =
        std::hardware_destructive_interference_size;  // usually 64
#else
    static constexpr std::size_t CACHE_LINE = 64;
#endif

constexpr int NUM_THREADS = 4;
constexpr int ITERATIONS = 100'000'000;

// ============================================================
// BAD: Counters packed together — FALSE SHARING
// ============================================================
struct CountersPacked {
    // All 4 counters fit in ONE cache line (4 * 8 = 32 bytes < 64)
    // When thread 0 writes counter[0], it invalidates the cache line
    // for threads 1, 2, 3 — even though they write to different counters
    int64_t counter[NUM_THREADS] = {};
};

// ============================================================
// GOOD: Each counter on its own cache line
// ============================================================
struct alignas(CACHE_LINE) PaddedCounter {
    int64_t value = 0;
    // Padding fills the rest of the cache line
    // sizeof(PaddedCounter) == 64 (or whatever CACHE_LINE is)
};

struct CountersPadded {
    PaddedCounter counter[NUM_THREADS];
};

// ============================================================
// GOOD (alternative): Using atomic with padding
// ============================================================
struct alignas(CACHE_LINE) AlignedAtomic {
    std::atomic<int64_t> value{0};
};

// ============================================================
// Benchmark function
// ============================================================
template<typename Counters, typename Accessor>
auto benchmark(const std::string& label, Counters& counters, Accessor accessor) {
    auto start = std::chrono::high_resolution_clock::now();

    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&counters, &accessor, t] {
            for (int i = 0; i < ITERATIONS; ++i) {
                ++accessor(counters, t);
            }
        });
    }
    for (auto& th : threads) th.join();

    auto elapsed = std::chrono::high_resolution_clock::now() - start;
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count();
    std::cout << "  " << label << ": " << ms << " ms\n";
    return ms;
}

// ============================================================
// Visual: cache line layout
// ============================================================
void show_layout() {
    CountersPacked packed;
    CountersPadded padded;

    std::cout << "=== Memory layout ===\n";
    std::cout << "  sizeof(CountersPacked):  " << sizeof(packed)
              << " bytes (all in ~1 cache line)\n";
    std::cout << "  sizeof(CountersPadded):  " << sizeof(padded)
              << " bytes (" << NUM_THREADS << " cache lines)\n";
    std::cout << "  Cache line size:         " << CACHE_LINE << " bytes\n\n";

    // Show addresses
    for (int i = 0; i < NUM_THREADS; ++i) {
        auto addr_packed = reinterpret_cast<uintptr_t>(&packed.counter[i]);
        auto addr_padded = reinterpret_cast<uintptr_t>(&padded.counter[i].value);
        std::cout << "  packed[" << i << "] @ cache line "
                  << (addr_packed / CACHE_LINE)
                  << "  |  padded[" << i << "] @ cache line "
                  << (addr_padded / CACHE_LINE) << "\n";
    }
}

// ============================================================
// Real-world fix: per-thread accumulation + final merge
// ============================================================
class ConcurrentCounter {
    struct alignas(CACHE_LINE) Slot {
        int64_t local_count = 0;
    };
    Slot slots_[NUM_THREADS];

public:
    void increment(int thread_id) {
        ++slots_[thread_id].local_count;
    }

    int64_t total() const {
        int64_t sum = 0;
        for (int i = 0; i < NUM_THREADS; ++i) {
            sum += slots_[i].local_count;
        }
        return sum;
    }
};

int main() {
    show_layout();

    std::cout << "\n=== Benchmark: " << ITERATIONS << " increments/thread, "
              << NUM_THREADS << " threads ===\n";

    // False sharing (BAD)
    CountersPacked packed;
    auto slow = benchmark("Packed (false sharing)", packed,
        [](CountersPacked& c, int t) -> int64_t& { return c.counter[t]; });

    // No false sharing (GOOD)
    CountersPadded padded;
    auto fast = benchmark("Padded (no sharing)  ", padded,
        [](CountersPadded& c, int t) -> int64_t& { return c.counter[t].value; });

    if (fast > 0) {
        std::cout << "\n  Speedup: " << static_cast<double>(slow) / fast
                  << "x faster without false sharing\n";
    }

    // Verify correctness
    int64_t sum_packed = 0, sum_padded = 0;
    for (int i = 0; i < NUM_THREADS; ++i) {
        sum_packed += packed.counter[i];
        sum_padded += padded.counter[i].value;
    }
    std::cout << "  Packed total: " << sum_packed << "\n";
    std::cout << "  Padded total: " << sum_padded << "\n";

    std::cout << R"(
=== Prevention strategies ===
  1. alignas(64) on per-thread data (shown above)
  2. C++17: alignas(std::hardware_destructive_interference_size)
  3. thread_local variables (each on separate pages)
  4. Per-thread accumulation + merge (best for counters)
  5. In structs: group "hot" fields together, pad between
     fields accessed by different threads

=== Detection ===
  - perf c2c (Linux): directly detects cache line contention
  - Intel VTune: "Memory Access" analysis shows false sharing
  - Look for: multiple threads + separate variables + poor scaling
)";

    return 0;
}
```

**The numbers speak for themselves:** on a typical 4-core machine, the padded version is 3-10x faster than the packed version, even though both do the exact same logical work. The only difference is memory layout.

**Rule of thumb:** any time multiple threads write to nearby memory locations, ensure those locations are on separate cache lines using `alignas(64)` or `alignas(std::hardware_destructive_interference_size)`.'''),

    ("cpp_deep/coroutine_cooperative_scheduling", r'''Show me how C++20 coroutines can be used for cooperative scheduling. I want to understand the awaiter mechanism and how to build a simple coroutine scheduler.''', r'''<think>
C++20 coroutines are a compiler feature that transforms functions into state machines.
The key abstractions:
- co_await: suspend and (optionally) transfer control
- co_yield: suspend and produce a value
- co_return: complete the coroutine

To build a scheduler, I need:
1. A Task type (the return type of the coroutine, contains the promise_type)
2. An Awaiter type (decides when to suspend and what to resume)
3. A Scheduler that maintains a queue of ready coroutines

The promise_type controls:
- initial_suspend: suspend immediately? (lazy start vs eager)
- final_suspend: suspend at end? (keeps coroutine alive for result retrieval)
- get_return_object: creates the Task from the promise
- return_value/return_void: handles co_return
- unhandled_exception: handles exceptions

The Awaiter controls:
- await_ready: should we suspend? (false = always suspend)
- await_suspend: what to do when suspended (schedule another coroutine)
- await_resume: what to return when resumed

For a scheduler:
- Tasks are coroutine_handle<> stored in a queue
- co_await scheduler.yield() suspends current, queues it, resumes next
- The scheduler runs until all tasks complete

Let me build a round-robin cooperative scheduler.
</think>

C++20 coroutines enable cooperative multitasking where tasks explicitly yield control. Here is a complete scheduler built from the ground up, explaining each component:

```cpp
#include <iostream>
#include <coroutine>
#include <queue>
#include <vector>
#include <string>
#include <functional>
#include <optional>
#include <chrono>

// ============================================================
// Forward declaration
// ============================================================
class Scheduler;

// ============================================================
// Task: The coroutine return type
// ============================================================
class Task {
public:
    struct promise_type {
        // What to do at the start of the coroutine
        std::suspend_always initial_suspend() noexcept { return {}; }  // lazy start

        // What to do when the coroutine finishes
        std::suspend_always final_suspend() noexcept { return {}; }  // don't destroy yet

        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        void return_void() {}

        void unhandled_exception() {
            std::terminate();  // or store exception_ptr for later
        }
    };

    using handle_type = std::coroutine_handle<promise_type>;

    explicit Task(handle_type h) : handle_(h) {}

    // Move-only
    Task(Task&& other) noexcept : handle_(other.handle_) { other.handle_ = nullptr; }
    Task& operator=(Task&& other) noexcept {
        if (handle_) handle_.destroy();
        handle_ = other.handle_;
        other.handle_ = nullptr;
        return *this;
    }

    ~Task() {
        if (handle_) handle_.destroy();
    }

    Task(const Task&) = delete;
    Task& operator=(const Task&) = delete;

    handle_type handle() const { return handle_; }
    bool done() const { return handle_.done(); }

private:
    handle_type handle_;
};

// ============================================================
// Scheduler: Round-robin cooperative scheduler
// ============================================================
class Scheduler {
    std::queue<std::coroutine_handle<>> ready_queue_;

public:
    // Custom awaiter: when co_await'd, suspends current and schedules next
    struct YieldAwaiter {
        Scheduler& scheduler;

        bool await_ready() const noexcept { return false; }  // always suspend

        void await_suspend(std::coroutine_handle<> current) const noexcept {
            // Put current task back in the ready queue
            scheduler.ready_queue_.push(current);
            // Scheduler will pick up the next task
        }

        void await_resume() const noexcept {}  // nothing to return
    };

    // Awaiter for yielding control to another task
    YieldAwaiter yield() { return YieldAwaiter{*this}; }

    // Add a task to the scheduler
    void spawn(Task& task) {
        ready_queue_.push(task.handle());
    }

    // Run all tasks to completion
    void run() {
        while (!ready_queue_.empty()) {
            auto handle = ready_queue_.front();
            ready_queue_.pop();

            if (!handle.done()) {
                handle.resume();  // runs until next co_await or co_return
            }
            // If the task suspended via yield(), it re-queued itself
            // If it finished (co_return), it's just removed
        }
    }

    size_t pending() const { return ready_queue_.size(); }
};

// ============================================================
// Example coroutines
// ============================================================
Scheduler g_scheduler;  // global scheduler for simplicity

Task counter_task(std::string name, int count) {
    for (int i = 0; i < count; ++i) {
        std::cout << "  [" << name << "] step " << i << "\n";
        co_await g_scheduler.yield();  // give other tasks a chance
    }
    std::cout << "  [" << name << "] done!\n";
}

Task fibonacci_task() {
    int a = 0, b = 1;
    for (int i = 0; i < 8; ++i) {
        std::cout << "  [fib] " << a << "\n";
        int next = a + b;
        a = b;
        b = next;
        co_await g_scheduler.yield();
    }
}

// ============================================================
// Generator: co_yield for producing values lazily
// ============================================================
template<typename T>
class Generator {
public:
    struct promise_type {
        T current_value;

        Generator get_return_object() {
            return Generator{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }

        std::suspend_always yield_value(T value) {
            current_value = std::move(value);
            return {};
        }

        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    using handle_type = std::coroutine_handle<promise_type>;

    explicit Generator(handle_type h) : handle_(h) {}
    Generator(Generator&& other) noexcept : handle_(other.handle_) { other.handle_ = nullptr; }
    ~Generator() { if (handle_) handle_.destroy(); }

    Generator(const Generator&) = delete;
    Generator& operator=(const Generator&) = delete;

    // Iterator-like interface
    struct Sentinel {};

    struct Iterator {
        handle_type handle;

        Iterator& operator++() {
            handle.resume();
            return *this;
        }

        const T& operator*() const {
            return handle.promise().current_value;
        }

        bool operator!=(Sentinel) const {
            return !handle.done();
        }
    };

    Iterator begin() {
        handle_.resume();  // advance to first yield
        return Iterator{handle_};
    }

    Sentinel end() { return {}; }

private:
    handle_type handle_;
};

// Fibonacci generator
Generator<int> fibonacci(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        co_yield a;
        int next = a + b;
        a = b;
        b = next;
    }
}

// Range generator
Generator<int> range(int start, int end, int step = 1) {
    for (int i = start; i < end; i += step) {
        co_yield i;
    }
}

// ============================================================
// Demo
// ============================================================
int main() {
    // Cooperative scheduling demo
    std::cout << "=== Cooperative scheduler ===\n";
    auto t1 = counter_task("A", 3);
    auto t2 = counter_task("B", 4);
    auto t3 = fibonacci_task();

    g_scheduler.spawn(t1);
    g_scheduler.spawn(t2);
    g_scheduler.spawn(t3);

    g_scheduler.run();  // interleaves all three tasks

    // Generator demo
    std::cout << "\n=== Generator: fibonacci ===\n";
    for (int val : fibonacci(10)) {
        std::cout << "  " << val << "\n";
    }

    std::cout << "\n=== Generator: range ===\n";
    for (int val : range(0, 20, 3)) {
        std::cout << "  " << val << "\n";
    }

    std::cout << R"(
=== Coroutine anatomy ===
  promise_type:    Controls coroutine behavior (suspend policy, return handling)
  coroutine_handle: Raw handle to resume/destroy the coroutine
  Awaiter:          Controls co_await (await_ready, await_suspend, await_resume)

  co_await expr:   Suspends, runs awaiter logic, resumes later
  co_yield val:    Shorthand for co_await promise.yield_value(val)
  co_return:       Completes the coroutine

  Key insight: coroutines are STATE MACHINES compiled by the compiler.
  They don't create threads — they're cooperative (explicit suspension points).
)";

    return 0;
}
```

Compile with: `g++ -std=c++20 -fcoroutines -o coro coro.cpp` (GCC) or `cl /std:c++20 coro.cpp` (MSVC).

**Why coroutines over threads for cooperative scheduling:**
- No context switch overhead (coroutine resume is a function call)
- No synchronization needed (only one coroutine runs at a time)
- Deterministic interleaving (you control suspension points)
- Scales to millions of coroutines (each is ~200 bytes of state, not a full thread stack)'''),
]
