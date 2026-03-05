"""P3 Batch: Modern C++ — concurrency, STL, performance, templates, memory management."""

PAIRS = [
    (
        "C++ concurrency with std::jthread, stop_token, atomics, and lock-free data structures",
        "Explain modern C++ concurrency patterns including std::jthread with cooperative cancellation via stop_token, atomic operations with different memory orderings (relaxed, acquire, release, seq_cst), and lock-free data structures. Build a production-grade thread pool with work stealing and a lock-free MPMC queue. Show why each memory ordering matters and common mistakes developers make.",
        """## Modern C++ Concurrency: From Threads to Lock-Free Architectures

### Why std::jthread Changed Everything

Before C++20, `std::thread` had a fatal design flaw: if you forgot to call `join()` or `detach()` before the thread object was destroyed, the program called `std::terminate()`. This was a **common source of crashes** in production code, especially during exception unwinding. `std::jthread` fixes this because it automatically joins in its destructor, and — critically — it supports **cooperative cancellation** through `std::stop_token`.

The key insight is that cooperative cancellation is almost always better than forceful thread termination. When you forcefully kill a thread (like `pthread_cancel`), you risk leaving mutexes locked, memory leaked, and invariants broken. With `stop_token`, the thread checks periodically whether it should stop, giving it the chance to clean up properly.

### Production Thread Pool with Work Stealing

A naive thread pool uses a single shared queue, but this creates a **bottleneck** because every thread contends on the same mutex. A work-stealing pool gives each thread its own local queue; threads only steal from others when their queue is empty. This dramatically reduces contention and improves **cache locality** because a thread typically processes items it recently enqueued.

```cpp
#include <atomic>
#include <concepts>
#include <deque>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <optional>
#include <random>
#include <stop_token>
#include <thread>
#include <type_traits>
#include <vector>

// Lock-free MPMC bounded queue using acquire/release ordering.
// We avoid seq_cst here because it forces a full memory fence on x86,
// which is unnecessary when we only need to synchronize producer/consumer pairs.
template <typename T, std::size_t Capacity = 1024>
class LockFreeQueue {
    struct Slot {
        std::atomic<std::size_t> turn{0};
        alignas(64) T value;  // Separate cache line to avoid false sharing
    };

    alignas(64) std::atomic<std::size_t> head_{0};  // Consumer index
    alignas(64) std::atomic<std::size_t> tail_{0};  // Producer index
    std::array<Slot, Capacity> slots_;

public:
    LockFreeQueue() {
        for (std::size_t i = 0; i < Capacity; ++i) {
            slots_[i].turn.store(i, std::memory_order_relaxed);
        }
    }

    /// Try to push an item. Returns false if the queue is full.
    /// Uses acquire/release: the store-release on turn synchronizes
    /// with the load-acquire in try_pop, ensuring the value write
    /// is visible to the consumer.
    bool try_push(T item) {
        auto tail = tail_.load(std::memory_order_relaxed);
        for (;;) {
            auto& slot = slots_[tail % Capacity];
            auto turn = slot.turn.load(std::memory_order_acquire);
            if (turn == tail) {
                // Slot is ready for writing
                if (tail_.compare_exchange_weak(tail, tail + 1,
                        std::memory_order_relaxed)) {
                    slot.value = std::move(item);
                    // Release: makes value visible to consumer
                    slot.turn.store(tail + 1, std::memory_order_release);
                    return true;
                }
            } else if (turn < tail) {
                // Queue is full
                return false;
            } else {
                // Another producer beat us, reload tail
                tail = tail_.load(std::memory_order_relaxed);
            }
        }
    }

    /// Try to pop an item. Returns std::nullopt if empty.
    std::optional<T> try_pop() {
        auto head = head_.load(std::memory_order_relaxed);
        for (;;) {
            auto& slot = slots_[head % Capacity];
            auto turn = slot.turn.load(std::memory_order_acquire);
            if (turn == head + 1) {
                // Slot has data ready
                if (head_.compare_exchange_weak(head, head + 1,
                        std::memory_order_relaxed)) {
                    T result = std::move(slot.value);
                    // Release: marks slot as available for producers
                    slot.turn.store(head + Capacity, std::memory_order_release);
                    return result;
                }
            } else if (turn == head) {
                // Queue is empty
                return std::nullopt;
            } else {
                head = head_.load(std::memory_order_relaxed);
            }
        }
    }

    [[nodiscard]] bool empty() const {
        auto head = head_.load(std::memory_order_relaxed);
        auto tail = tail_.load(std::memory_order_relaxed);
        return head >= tail;
    }
};

/// Work-stealing thread pool with cooperative cancellation.
/// Best practice: size the pool to hardware_concurrency minus 1,
/// leaving one core for the OS scheduler and I/O threads.
class ThreadPool {
    using Task = std::function<void()>;

    struct WorkerState {
        LockFreeQueue<Task> local_queue;
        std::mutex fallback_mutex;           // For overflow tasks
        std::deque<Task> fallback_queue;     // Unbounded overflow
        std::atomic<bool> has_work{false};
    };

    std::vector<std::unique_ptr<WorkerState>> workers_;
    std::vector<std::jthread> threads_;
    std::atomic<std::size_t> next_submit_{0};
    std::atomic<bool> stopped_{false};

    /// Each worker thread runs this loop.
    /// The stop_token enables graceful shutdown: the pool destructor
    /// requests stop, and each thread finishes its current task then exits.
    void worker_loop(std::stop_token stop, std::size_t id) {
        thread_local std::mt19937 rng(std::random_device{}());

        while (!stop.stop_requested()) {
            // 1. Try local queue first (best cache locality)
            if (auto task = workers_[id]->local_queue.try_pop()) {
                (*task)();
                continue;
            }

            // 2. Try local fallback queue
            {
                std::unique_lock lock(workers_[id]->fallback_mutex);
                if (!workers_[id]->fallback_queue.empty()) {
                    auto task = std::move(workers_[id]->fallback_queue.front());
                    workers_[id]->fallback_queue.pop_front();
                    lock.unlock();
                    task();
                    continue;
                }
            }

            // 3. Work stealing: pick a random victim
            auto victim = rng() % workers_.size();
            if (victim != id) {
                if (auto task = workers_[victim]->local_queue.try_pop()) {
                    (*task)();
                    continue;
                }
            }

            // 4. Nothing to do — yield to avoid busy-spinning.
            // A common mistake is using sleep_for here, which adds
            // unnecessary latency. yield() is cheaper.
            std::this_thread::yield();
        }
    }

public:
    explicit ThreadPool(
        std::size_t num_threads = std::thread::hardware_concurrency())
    {
        // Avoid pitfall: hardware_concurrency() can return 0
        if (num_threads == 0) num_threads = 4;

        workers_.reserve(num_threads);
        for (std::size_t i = 0; i < num_threads; ++i) {
            workers_.push_back(std::make_unique<WorkerState>());
        }

        threads_.reserve(num_threads);
        for (std::size_t i = 0; i < num_threads; ++i) {
            // jthread passes stop_token as first argument automatically
            threads_.emplace_back([this, i](std::stop_token st) {
                worker_loop(st, i);
            });
        }
    }

    ~ThreadPool() {
        stopped_.store(true, std::memory_order_release);
        // jthread destructor requests stop and joins automatically
    }

    /// Submit a callable and get a future for the result.
    /// Round-robin assignment with fallback to overflow queue.
    template <std::invocable Func>
    auto submit(Func&& func) -> std::future<std::invoke_result_t<Func>> {
        using ReturnType = std::invoke_result_t<Func>;
        auto promise = std::make_shared<std::promise<ReturnType>>();
        auto future = promise->get_future();

        auto idx = next_submit_.fetch_add(1, std::memory_order_relaxed)
                   % workers_.size();

        auto wrapper = [p = std::move(promise),
                        f = std::forward<Func>(func)]() mutable {
            try {
                if constexpr (std::is_void_v<ReturnType>) {
                    f();
                    p->set_value();
                } else {
                    p->set_value(f());
                }
            } catch (...) {
                p->set_exception(std::current_exception());
            }
        };

        if (!workers_[idx]->local_queue.try_push(Task{std::move(wrapper)})) {
            // Overflow to unbounded fallback
            std::lock_guard lock(workers_[idx]->fallback_mutex);
            workers_[idx]->fallback_queue.push_back(Task{std::move(wrapper)});
        }

        return future;
    }
};
```

### Memory Ordering Explained

This is where most developers get confused, and consequently where the worst bugs hide. Here is the mental model:

- **`relaxed`**: No ordering guarantees at all. The CPU and compiler can reorder freely. Use only for counters and statistics where you do not care about the relationship to other memory operations.
- **`acquire`**: A load with acquire ordering guarantees that all reads and writes **after** it in program order cannot be reordered **before** it. Think of it as "acquire the lock — everything I read after this point sees the latest data."
- **`release`**: A store with release ordering guarantees that all reads and writes **before** it cannot be reordered **after** it. Think of it as "release the lock — everything I wrote before this point is now visible."
- **`seq_cst`**: Total ordering across all threads. Every thread sees the same order of seq_cst operations. This is the **strongest** and **slowest** ordering. On x86, seq_cst stores emit an `MFENCE` instruction (or `XCHG`), while acquire/release is free because x86 already has a strong memory model.

**Best practice**: start with `seq_cst` for correctness, then weaken to `acquire`/`release` where profiling shows contention. Never use `relaxed` unless you can formally prove no other thread depends on the ordering.

### Testing Lock-Free Code

```cpp
#include <cassert>
#include <iostream>
#include <latch>

/// Stress test: multiple producers and consumers hammer the queue.
/// A common mistake is testing with a single thread — data races
/// only manifest under concurrent access.
void test_lock_free_queue() {
    LockFreeQueue<int, 256> queue;
    constexpr int num_producers = 4;
    constexpr int items_per_producer = 10000;
    std::atomic<int> total_consumed{0};
    std::latch start_barrier(num_producers + num_producers);

    std::vector<std::jthread> producers;
    for (int p = 0; p < num_producers; ++p) {
        producers.emplace_back([&, p](std::stop_token) {
            start_barrier.arrive_and_wait();  // Synchronized start
            for (int i = 0; i < items_per_producer; ++i) {
                while (!queue.try_push(p * items_per_producer + i)) {
                    std::this_thread::yield();
                }
            }
        });
    }

    std::vector<std::jthread> consumers;
    for (int c = 0; c < num_producers; ++c) {
        consumers.emplace_back([&](std::stop_token) {
            start_barrier.arrive_and_wait();
            int local_count = 0;
            while (local_count < items_per_producer) {
                if (auto val = queue.try_pop()) {
                    ++local_count;
                }
            }
            total_consumed.fetch_add(local_count, std::memory_order_relaxed);
        });
    }

    producers.clear();  // Join producers
    consumers.clear();  // Join consumers

    assert(total_consumed.load() == num_producers * items_per_producer);
    std::cout << "Lock-free queue test passed: "
              << total_consumed.load() << " items processed\\n";
}

void test_thread_pool() {
    ThreadPool pool(4);
    std::atomic<int> counter{0};

    std::vector<std::future<int>> futures;
    for (int i = 0; i < 1000; ++i) {
        futures.push_back(pool.submit([&counter, i]() {
            counter.fetch_add(1, std::memory_order_relaxed);
            return i * i;
        }));
    }

    for (std::size_t i = 0; i < futures.size(); ++i) {
        assert(futures[i].get() == static_cast<int>(i * i));
    }
    assert(counter.load() == 1000);
    std::cout << "Thread pool test passed\\n";
}

int main() {
    test_lock_free_queue();
    test_thread_pool();
    return 0;
}
```

### Summary and Key Takeaways

- **Use `std::jthread` over `std::thread`** — automatic join prevents crashes and stop_token enables clean shutdown patterns.
- **Lock-free structures reduce contention** but are harder to reason about. Always stress-test with `ThreadSanitizer` (`-fsanitize=thread`).
- **Memory ordering matters for performance**: on ARM/RISC-V, acquire/release is significantly cheaper than seq_cst because those architectures have weak memory models. Even on x86, seq_cst stores are more expensive.
- **Work stealing** is the gold standard for thread pool design because it balances load automatically and preserves cache locality.
- **Common pitfall**: using `std::atomic<std::shared_ptr<T>>` — this is supported in C++20 but the implementation typically uses a spinlock internally, defeating the purpose. Use `std::atomic<T*>` with manual reference counting for truly lock-free shared ownership.
"""
    ),
    (
        "Modern C++ STL with ranges, views, std::expected, std::optional, and std::variant",
        "Demonstrate modern C++ STL patterns including ranges and views for lazy data pipelines, std::expected for error handling without exceptions, std::optional for nullable values, and std::variant with std::visit for type-safe unions. Build a real-world data processing pipeline that shows how these features compose together. Explain the performance implications and common pitfalls.",
        """## Modern C++ STL: Composable, Type-Safe, Zero-Cost Abstractions

### Why Ranges and Views Are a Paradigm Shift

Before C++20 ranges, composing algorithms required temporary containers at every step. If you wanted to filter a vector, then transform the results, then take the first 10, you had to allocate three intermediate vectors. Ranges fix this with **lazy evaluation**: views do not materialize data until you iterate. This means a pipeline like `filter | transform | take` runs in a single pass with zero allocations.

The deeper insight is that ranges turn the STL from an "algorithm library" into a **data pipeline library**, similar to LINQ in C# or Java streams but with **zero overhead** because views are evaluated at compile time and the compiler inlines everything.

### Building a Real-World Data Pipeline

Let us build a CSV log processor that parses server access logs, filters by status code, aggregates statistics, and handles errors gracefully using `std::expected` instead of exceptions.

```cpp
#include <algorithm>
#include <charconv>
#include <expected>
#include <format>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <ranges>
#include <span>
#include <sstream>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

// ---------- Error handling with std::expected ----------

/// Parse errors are explicit in the return type — no exceptions needed.
/// This is better for performance-critical code because exceptions have
/// a non-trivial cost on the error path (stack unwinding), whereas
/// std::expected is just a tagged union with zero overhead on success.
enum class ParseError {
    EmptyLine,
    MissingFields,
    InvalidStatusCode,
    InvalidResponseTime,
    MalformedTimestamp,
};

/// Human-readable error messages for diagnostics.
[[nodiscard]] constexpr std::string_view to_string(ParseError e) {
    switch (e) {
        case ParseError::EmptyLine:          return "empty line";
        case ParseError::MissingFields:      return "missing required fields";
        case ParseError::InvalidStatusCode:  return "invalid HTTP status code";
        case ParseError::InvalidResponseTime: return "invalid response time";
        case ParseError::MalformedTimestamp: return "malformed timestamp";
    }
    return "unknown error";
}

struct LogEntry {
    std::string timestamp;
    std::string method;       // GET, POST, etc.
    std::string path;
    int status_code;
    double response_time_ms;
    std::optional<std::string> user_agent;  // May be absent in some logs
};

/// Parse a single CSV line into a LogEntry.
/// Returns std::expected so callers can handle errors without try/catch.
[[nodiscard]] auto parse_log_line(std::string_view line)
    -> std::expected<LogEntry, ParseError>
{
    if (line.empty()) {
        return std::unexpected(ParseError::EmptyLine);
    }

    // Split by comma — using ranges::split_view (C++23 improvement)
    auto fields = line
        | std::views::split(',')
        | std::views::transform([](auto&& rng) {
              return std::string_view(rng.begin(), rng.end());
          });

    std::vector<std::string_view> parts(fields.begin(), fields.end());

    if (parts.size() < 5) {
        return std::unexpected(ParseError::MissingFields);
    }

    // Parse status code with std::from_chars (no allocations, no exceptions)
    int status = 0;
    auto [ptr, ec] = std::from_chars(
        parts[3].data(), parts[3].data() + parts[3].size(), status);
    if (ec != std::errc{}) {
        return std::unexpected(ParseError::InvalidStatusCode);
    }

    // Parse response time
    double resp_time = 0.0;
    auto [ptr2, ec2] = std::from_chars(
        parts[4].data(), parts[4].data() + parts[4].size(), resp_time);
    if (ec2 != std::errc{}) {
        return std::unexpected(ParseError::InvalidResponseTime);
    }

    return LogEntry{
        .timestamp = std::string(parts[0]),
        .method = std::string(parts[1]),
        .path = std::string(parts[2]),
        .status_code = status,
        .response_time_ms = resp_time,
        .user_agent = parts.size() > 5
            ? std::optional<std::string>(std::string(parts[5]))
            : std::nullopt,
    };
}
```

### Composing Views into Pipelines

```cpp
/// Statistics aggregated from log entries.
struct PipelineStats {
    std::size_t total_requests{0};
    std::size_t error_requests{0};        // 4xx and 5xx
    double avg_response_time{0.0};
    double p99_response_time{0.0};
    std::map<std::string, std::size_t> path_counts;
};

/// Process raw log lines through a lazy pipeline.
/// Because views are lazy, this makes exactly ONE pass over the data,
/// regardless of how many transformations we chain together.
[[nodiscard]] PipelineStats process_logs(std::span<const std::string> raw_lines) {
    // Step 1: Parse all lines, keeping only successful parses.
    //         and_then chains expected computations (monadic operation).
    auto parsed_entries = raw_lines
        | std::views::transform([](const std::string& line) {
              return parse_log_line(line);
          })
        | std::views::filter([](const auto& result) {
              if (!result.has_value()) {
                  // Log parse errors but continue processing
                  std::cerr << "Parse warning: "
                            << to_string(result.error()) << "\\n";
              }
              return result.has_value();
          })
        | std::views::transform([](const auto& result) -> const LogEntry& {
              return result.value();
          });

    // Step 2: Collect into a vector (we need random access for percentile)
    std::vector<LogEntry> entries;
    for (const auto& entry : parsed_entries) {
        entries.push_back(entry);
    }

    if (entries.empty()) return {};

    // Step 3: Compute statistics using ranges algorithms
    PipelineStats stats;
    stats.total_requests = entries.size();

    // Count errors: status >= 400
    stats.error_requests = std::ranges::count_if(entries,
        [](const LogEntry& e) { return e.status_code >= 400; });

    // Average response time using ranges::fold_left (C++23)
    double total_time = 0.0;
    for (const auto& e : entries) {
        total_time += e.response_time_ms;
    }
    stats.avg_response_time = total_time / static_cast<double>(entries.size());

    // P99 response time: sort and pick the 99th percentile
    auto times = entries
        | std::views::transform(&LogEntry::response_time_ms);
    std::vector<double> sorted_times(times.begin(), times.end());
    std::ranges::sort(sorted_times);
    auto p99_idx = static_cast<std::size_t>(
        0.99 * static_cast<double>(sorted_times.size()));
    stats.p99_response_time = sorted_times[p99_idx];

    // Path frequency using ranges
    for (const auto& entry : entries) {
        stats.path_counts[entry.path]++;
    }

    return stats;
}
```

### std::variant for Type-Safe Event Handling

```cpp
/// Use variant to model different log event types without inheritance.
/// This is more cache-friendly than virtual dispatch because all variants
/// live inline (no heap pointer chasing), and std::visit compiles to a
/// jump table rather than a vtable indirection.
struct AccessEvent   { LogEntry entry; };
struct ErrorEvent    { std::string message; int severity; };
struct MetricEvent   { std::string name; double value; };

using LogEvent = std::variant<AccessEvent, ErrorEvent, MetricEvent>;

/// Process events with std::visit.
/// The overloaded lambda pattern avoids writing a separate visitor class.
template <typename... Ts>
struct overloaded : Ts... { using Ts::operator()...; };

void handle_events(std::span<const LogEvent> events) {
    for (const auto& event : events) {
        std::visit(overloaded{
            [](const AccessEvent& e) {
                std::cout << std::format("[ACCESS] {} {} -> {}\\n",
                    e.entry.method, e.entry.path, e.entry.status_code);
            },
            [](const ErrorEvent& e) {
                std::cout << std::format("[ERROR severity={}] {}\\n",
                    e.severity, e.message);
            },
            [](const MetricEvent& e) {
                std::cout << std::format("[METRIC] {} = {:.2f}\\n",
                    e.name, e.value);
            },
        }, event);
    }
}
```

### Testing the Pipeline

```cpp
void test_pipeline() {
    std::vector<std::string> raw_logs = {
        "2024-01-15T10:30:00,GET,/api/users,200,12.5,Mozilla/5.0",
        "2024-01-15T10:30:01,POST,/api/users,201,45.2,curl/7.88",
        "2024-01-15T10:30:02,GET,/api/users/1,404,3.1,",
        "",  // Empty line — should be filtered out
        "2024-01-15T10:30:03,GET,/api/health,200,1.0",
        "2024-01-15T10:30:04,POST,/api/orders,500,120.8,PostmanRuntime",
    };

    auto stats = process_logs(raw_logs);

    std::cout << std::format("Total requests: {}\\n", stats.total_requests);
    std::cout << std::format("Error rate: {:.1f}%\\n",
        100.0 * static_cast<double>(stats.error_requests)
              / static_cast<double>(stats.total_requests));
    std::cout << std::format("Avg response time: {:.2f}ms\\n",
        stats.avg_response_time);
    std::cout << std::format("P99 response time: {:.2f}ms\\n",
        stats.p99_response_time);

    // Test optional user_agent
    auto result = parse_log_line(
        "2024-01-15T10:30:00,GET,/api/test,200,5.0");
    assert(result.has_value());
    assert(!result->user_agent.has_value());  // No user agent provided

    auto result2 = parse_log_line(
        "2024-01-15T10:30:00,GET,/api/test,200,5.0,Firefox");
    assert(result2.has_value());
    assert(result2->user_agent.value() == "Firefox");

    std::cout << "All pipeline tests passed\\n";
}

int main() {
    test_pipeline();
    return 0;
}
```

### Monadic Operations on std::expected and std::optional

C++23 added monadic operations (`and_then`, `transform`, `or_else`) to both `std::expected` and `std::optional`, enabling functional-style chaining without nested if-checks. This is similar to Rust's `Result::and_then` or Haskell's `>>=` bind operator. The **performance** benefit is not just ergonomic — the compiler can optimize chained monadic operations into straight-line code because each operation is a simple branch-on-tag, not an exception throw.

```cpp
/// Monadic chaining: parse a config value through multiple validation stages.
/// Each stage returns expected, and and_then chains them without nesting.
auto parse_port(std::string_view input)
    -> std::expected<int, ParseError>
{
    return parse_log_line(input)
        .transform([](const LogEntry& entry) {
            return entry.status_code;  // Extract a field
        })
        .and_then([](int code) -> std::expected<int, ParseError> {
            if (code < 100 || code > 599) {
                return std::unexpected(ParseError::InvalidStatusCode);
            }
            return code;
        });
}

/// Using or_else to provide fallback values on error.
/// This pattern avoids the "pyramid of doom" that nested if-checks create.
auto get_status_or_default(std::string_view line) -> int {
    return parse_log_line(line)
        .transform(&LogEntry::status_code)
        .or_else([](ParseError err) -> std::expected<int, ParseError> {
            std::cerr << "Falling back to 500 due to: "
                      << to_string(err) << "\\n";
            return 500;  // Default to internal server error
        })
        .value();  // Safe because or_else guarantees a value
}
```

### Summary and Key Takeaways

- **Ranges views are lazy** — they compose without allocating intermediate containers. However, be careful with dangling: views do **not** own their data, so the underlying container must outlive the view. A **common mistake** is returning a view from a function where the underlying container is a local variable — the view will dangle immediately.
- **`std::expected` replaces exceptions** for recoverable errors in performance-sensitive code. The **trade-off** is verbosity: you need explicit checks instead of try/catch, but you gain predictable performance and self-documenting error types. With C++23 monadic operations, the verbosity gap shrinks significantly.
- **`std::optional` signals nullable values** without sentinel values or raw pointers. Although it has a small overhead (bool flag + storage), the compiler usually optimizes it away. **Avoid** using `optional<reference_wrapper<T>>` — use a raw pointer or `std::optional<T*>` instead, because reference_wrapper inside optional has surprising semantics.
- **`std::variant` with `std::visit` replaces virtual dispatch** for closed type sets. The **performance** advantage is significant: no heap allocation, no vtable indirection, and better cache **throughput** because variant objects are stored inline. Consequently, variant-based designs often outperform inheritance hierarchies in latency-sensitive systems.
- **Common mistake**: using `std::get<T>(variant)` without checking — this throws `std::bad_variant_access`. Always use `std::visit` or `std::get_if` instead.
- **Best practice**: prefer `std::from_chars` over `std::stoi`/`std::stod` for parsing — it is locale-independent, exception-free, and significantly faster. In production pipelines, `from_chars` can be 3-5x faster than stream-based parsing because it avoids locale machinery and virtual function calls through the `std::locale` facet system.
"""
    ),
    (
        "C++ performance optimization with cache-friendly data layouts and SIMD",
        "Explain C++ performance optimization techniques including cache-friendly data structures (Struct of Arrays vs Array of Structs), SIMD vectorization with std::simd, branch prediction optimization, and profile-guided optimization. Show concrete benchmarks and explain why data layout affects performance by orders of magnitude. Cover common bottlenecks in production C++ code.",
        """## C++ Performance Optimization: Data Layout, SIMD, and the Memory Wall

### Why Data Layout Matters More Than Algorithms

Most developers optimize algorithms first, but in modern hardware the **memory wall** dominates: a cache miss costs 100-300 cycles on modern CPUs, while an L1 cache hit costs 4 cycles. Consequently, a theoretically O(n log n) algorithm with poor cache behavior can be slower than an O(n^2) algorithm that fits in cache. The single most impactful optimization in production C++ code is rearranging data so that cache lines are fully utilized.

A cache line is 64 bytes on x86. When you access one byte, the CPU fetches the entire 64-byte line. If your data layout means that only 8 of those 64 bytes are useful for the current computation (because the rest belong to unrelated fields), you are wasting 87.5% of memory bandwidth. This is the fundamental problem with Array of Structs (AoS) layout for batch processing.

### AoS vs SoA: Concrete Example

```cpp
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <numeric>
#include <random>
#include <vector>

// ---- Array of Structs (AoS): traditional OOP layout ----
// sizeof(ParticleAoS) = 32 bytes (with padding)
// When updating positions, we load 32 bytes per particle
// but only use 24 bytes (x, y, z). The mass field pollutes the cache.
struct ParticleAoS {
    float x, y, z;       // Position: 12 bytes
    float mass;           // 4 bytes (unused during position update!)
    float vx, vy, vz;    // Velocity: 12 bytes
    float charge;         // 4 bytes (unused during position update!)
};

/// AoS update: iterates over particles, updating position from velocity.
/// Cache-unfriendly because each ParticleAoS is 32 bytes but we only
/// need 24 bytes of it per iteration, wasting 25% of bandwidth.
void update_positions_aos(std::vector<ParticleAoS>& particles, float dt) {
    for (auto& p : particles) {
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.z += p.vz * dt;
    }
}

// ---- Struct of Arrays (SoA): data-oriented layout ----
// Each array contains ONLY the data needed for a specific operation.
// Position update reads x, y, z, vx, vy, vz arrays — 100% utilization.
struct ParticlesSoA {
    std::vector<float> x, y, z;
    std::vector<float> vx, vy, vz;
    std::vector<float> mass;     // Separate — not loaded during position update
    std::vector<float> charge;   // Separate — not loaded during position update

    explicit ParticlesSoA(std::size_t n)
        : x(n), y(n), z(n), vx(n), vy(n), vz(n), mass(n), charge(n) {}

    [[nodiscard]] std::size_t size() const { return x.size(); }
};

/// SoA update: operates on contiguous float arrays.
/// The compiler can auto-vectorize this to use SSE/AVX because
/// the data is contiguous and there are no aliasing concerns.
void update_positions_soa(ParticlesSoA& particles, float dt) {
    const auto n = particles.size();
    for (std::size_t i = 0; i < n; ++i) {
        particles.x[i] += particles.vx[i] * dt;
        particles.y[i] += particles.vy[i] * dt;
        particles.z[i] += particles.vz[i] * dt;
    }
}
```

### Explicit SIMD with std::simd (C++26 / std::experimental::simd)

```cpp
// std::experimental::simd provides portable SIMD without intrinsics.
// This compiles to AVX2 on x86-64 and NEON on ARM automatically.
// The key advantage over compiler auto-vectorization: you CONTROL
// the vector width and operations, rather than hoping the compiler
// figures it out.

#include <experimental/simd>
namespace stdx = std::experimental;

/// SIMD-accelerated distance calculation.
/// Processes 8 floats at once with AVX2 (256-bit registers).
/// On a 4GHz CPU, this achieves ~32 GFLOPS vs ~4 GFLOPS scalar.
void compute_distances_simd(
    const ParticlesSoA& particles,
    float ref_x, float ref_y, float ref_z,
    std::vector<float>& distances)
{
    using simd_f = stdx::native_simd<float>;
    constexpr std::size_t lanes = simd_f::size();  // 8 for AVX2

    const auto n = particles.size();
    distances.resize(n);

    const simd_f rx(ref_x), ry(ref_y), rz(ref_z);

    std::size_t i = 0;
    // Process full SIMD vectors
    for (; i + lanes <= n; i += lanes) {
        simd_f px(&particles.x[i], stdx::element_aligned);
        simd_f py(&particles.y[i], stdx::element_aligned);
        simd_f pz(&particles.z[i], stdx::element_aligned);

        auto dx = px - rx;
        auto dy = py - ry;
        auto dz = pz - rz;

        // sqrt(dx^2 + dy^2 + dz^2) — fused multiply-add where available
        auto dist = stdx::sqrt(dx * dx + dy * dy + dz * dz);
        dist.copy_to(&distances[i], stdx::element_aligned);
    }

    // Scalar remainder
    for (; i < n; ++i) {
        float dx = particles.x[i] - ref_x;
        float dy = particles.y[i] - ref_y;
        float dz = particles.z[i] - ref_z;
        distances[i] = std::sqrt(dx * dx + dy * dy + dz * dz);
    }
}
```

### Branch Prediction Optimization

```cpp
/// Branch prediction: the CPU speculatively executes one path.
/// If the prediction is wrong, it flushes the pipeline (15-20 cycle penalty).
/// For hot loops, arrange branches so the common case falls through.

// BAD: Unpredictable branch in a hot loop.
// If particles are randomly distributed, this branch mispredicts ~50%.
int count_nearby_bad(const std::vector<float>& distances, float threshold) {
    int count = 0;
    for (float d : distances) {
        if (d < threshold) {  // Unpredictable branch!
            ++count;
        }
    }
    return count;
}

// GOOD: Branchless version using arithmetic.
// The compiler may do this automatically, but being explicit helps.
int count_nearby_branchless(const std::vector<float>& distances,
                            float threshold) {
    int count = 0;
    for (float d : distances) {
        count += static_cast<int>(d < threshold);  // No branch
    }
    return count;
}

// BETTER: Sort the data first if you process it multiple times.
// After sorting, the branch predictor sees a long run of true
// followed by a long run of false — nearly 100% prediction accuracy.
// Although sorting is O(n log n), the improvement in branch prediction
// often makes the total faster for repeated queries.
int count_nearby_sorted(std::vector<float>& distances, float threshold) {
    std::ranges::sort(distances);
    auto it = std::ranges::lower_bound(distances, threshold);
    return static_cast<int>(std::distance(distances.begin(), it));
}
```

### Benchmarking Framework

```cpp
/// Simple benchmark utility. In production, use Google Benchmark or nanobench.
/// A common mistake is benchmarking without warming up the cache first.
template <typename Func>
double benchmark_ms(Func&& func, int iterations = 100) {
    // Warmup: 10 iterations to fill caches and trigger JIT (if applicable)
    for (int i = 0; i < 10; ++i) {
        func();
    }

    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iterations; ++i) {
        func();
    }
    auto end = std::chrono::high_resolution_clock::now();

    auto elapsed = std::chrono::duration<double, std::milli>(end - start);
    return elapsed.count() / iterations;
}

int main() {
    constexpr std::size_t N = 1'000'000;
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(-100.0f, 100.0f);

    // Initialize AoS
    std::vector<ParticleAoS> aos(N);
    for (auto& p : aos) {
        p.x = dist(rng); p.y = dist(rng); p.z = dist(rng);
        p.vx = dist(rng); p.vy = dist(rng); p.vz = dist(rng);
        p.mass = dist(rng); p.charge = dist(rng);
    }

    // Initialize SoA with same data
    ParticlesSoA soa(N);
    for (std::size_t i = 0; i < N; ++i) {
        soa.x[i] = aos[i].x; soa.y[i] = aos[i].y; soa.z[i] = aos[i].z;
        soa.vx[i] = aos[i].vx; soa.vy[i] = aos[i].vy; soa.vz[i] = aos[i].vz;
    }

    float dt = 0.016f;

    double aos_time = benchmark_ms([&]{ update_positions_aos(aos, dt); });
    double soa_time = benchmark_ms([&]{ update_positions_soa(soa, dt); });

    std::cout << "AoS position update: " << aos_time << " ms\\n";
    std::cout << "SoA position update: " << soa_time << " ms\\n";
    std::cout << "Speedup: " << aos_time / soa_time << "x\\n";
    // Typical result: 2-4x speedup on modern x86 CPUs

    // Branch prediction benchmark
    std::vector<float> dists(N);
    for (auto& d : dists) d = std::abs(dist(rng));

    double bad_time = benchmark_ms([&]{
        volatile int r = count_nearby_bad(dists, 50.0f);
        (void)r;
    });
    double branchless_time = benchmark_ms([&]{
        volatile int r = count_nearby_branchless(dists, 50.0f);
        (void)r;
    });

    std::cout << "Branchy count: " << bad_time << " ms\\n";
    std::cout << "Branchless count: " << branchless_time << " ms\\n";

    return 0;
}
```

### Profile-Guided Optimization (PGO)

Profile-guided optimization lets the compiler use real runtime data to make better optimization decisions. The workflow is:

1. **Instrument**: `g++ -O2 -fprofile-generate -o app_instrumented main.cpp`
2. **Profile**: Run `app_instrumented` with representative workload — generates `.gcda` files
3. **Optimize**: `g++ -O2 -fprofile-use -o app_optimized main.cpp`

PGO typically yields **10-20% improvement** over `-O2` alone because the compiler can:

- **Inline hot functions** that it would not normally inline due to size constraints
- **Reorder basic blocks** so the hot path has no taken branches (better branch prediction)
- **Size cold code** more aggressively, keeping the instruction cache focused on hot code
- **Optimize switch statements** based on actual case frequencies

**Best practice**: integrate PGO into your CI pipeline. Collect profiles from staging environments with realistic traffic, then use those profiles for production builds.

### Summary and Key Takeaways

- **Data layout is the #1 performance lever** — SoA beats AoS by 2-4x for batch processing because of cache utilization. The **trade-off** is code complexity: SoA is less ergonomic than AoS for single-entity operations.
- **SIMD with `std::simd`** gives portable 4-8x speedups without architecture-specific intrinsics. However, avoid SIMD for branchy code — use it for uniform, data-parallel operations.
- **Branch prediction** penalties are 15-20 cycles. For hot loops with unpredictable branches, use branchless techniques or sort the data to make branches predictable.
- **PGO is free performance** (10-20%) for any production binary. The common mistake is never setting it up because it requires a two-pass build.
- **Common bottleneck in production**: `std::unordered_map` — it uses a linked-list hash table with terrible cache behavior. Consider flat hash maps (Abseil, Boost) or `std::vector` with binary search for small collections.
"""
    ),
    (
        "C++ template metaprogramming with concepts, CRTP, type erasure, and constexpr",
        "Build a practical C++ template metaprogramming system using concepts for constraints, CRTP for static polymorphism, type erasure for runtime flexibility, and constexpr for compile-time computation. Design a plugin system or serialization framework that demonstrates when to use each technique. Explain the trade-offs between compile-time and runtime polymorphism and common template pitfalls in production code.",
        """## C++ Template Metaprogramming: Building a Plugin and Serialization Framework

### When Compile-Time vs Runtime Polymorphism

The fundamental **trade-off** in C++ design is: virtual functions (runtime polymorphism) vs templates (compile-time polymorphism). Virtual functions are flexible — you can load plugins at runtime from shared libraries — but they cost a vtable indirection per call and prevent inlining. Templates are zero-cost at runtime but require all types to be known at compile time, which increases compile times and binary size.

The insight is that **you rarely need pure runtime or pure compile-time polymorphism**. Real systems use a layered approach: concepts constrain template interfaces at compile time, CRTP eliminates vtable overhead for known hierarchies, and type erasure bridges compile-time and runtime worlds when you need a container of heterogeneous objects.

### Concepts: Constraining Template Interfaces

Concepts replace SFINAE with readable, compiler-friendly constraints. Before concepts, a template error message could span 200 lines of nested `enable_if` failures. With concepts, the compiler tells you exactly which requirement failed.

```cpp
#include <concepts>
#include <cstdint>
#include <functional>
#include <iostream>
#include <memory>
#include <span>
#include <sstream>
#include <string>
#include <string_view>
#include <type_traits>
#include <unordered_map>
#include <vector>

// ---------- Concepts for the Serialization Framework ----------

/// A type is Serializable if it provides serialize/deserialize methods
/// with the correct signatures. The compiler checks this at instantiation.
template <typename T>
concept Serializable = requires(const T& obj, std::ostream& os,
                                std::istream& is, T& mut_obj) {
    { obj.serialize(os) } -> std::same_as<void>;
    { mut_obj.deserialize(is) } -> std::same_as<bool>;
    { T::type_name() } -> std::convertible_to<std::string_view>;
};

/// A type is Pluggable if it has a name, version, and execute method.
/// This is checked at compile time — no runtime cost.
template <typename T>
concept Pluggable = requires(T& plugin) {
    { T::name() } -> std::convertible_to<std::string_view>;
    { T::version() } -> std::same_as<int>;
    { plugin.execute(std::span<const std::string>{}) } -> std::same_as<int>;
};

/// Composable concept: a plugin that can also serialize its state.
template <typename T>
concept StatefulPlugin = Pluggable<T> && Serializable<T>;
```

### CRTP: Static Polymorphism Without vtables

```cpp
/// CRTP base for serializable types.
/// The Derived class provides the actual implementation; the base
/// provides shared infrastructure (like size-prefixed wire format).
/// Because the base knows the Derived type at compile time, all
/// calls are resolved statically — no vtable, full inlining.
template <typename Derived>
class SerializableBase {
public:
    /// Serialize with a type tag and size prefix for framing.
    void write_framed(std::ostream& os) const {
        // Write type tag
        auto name = Derived::type_name();
        auto name_len = static_cast<std::uint32_t>(name.size());
        os.write(reinterpret_cast<const char*>(&name_len), sizeof(name_len));
        os.write(name.data(), name.size());

        // Serialize to a temporary buffer to get the size
        std::ostringstream buf;
        static_cast<const Derived*>(this)->serialize(buf);
        std::string data = buf.str();

        auto data_len = static_cast<std::uint32_t>(data.size());
        os.write(reinterpret_cast<const char*>(&data_len), sizeof(data_len));
        os.write(data.data(), data.size());
    }

    /// Static dispatch — no virtual call overhead.
    /// The compiler sees through the cast and inlines the derived method.
    [[nodiscard]] std::string to_string() const {
        std::ostringstream os;
        static_cast<const Derived*>(this)->serialize(os);
        return os.str();
    }

protected:
    // Prevent slicing: only Derived can construct/destroy
    SerializableBase() = default;
    ~SerializableBase() = default;
};

/// Example: a config entry that is Serializable via CRTP.
class ConfigEntry : public SerializableBase<ConfigEntry> {
    std::string key_;
    std::string value_;
    int priority_;

public:
    ConfigEntry() = default;
    ConfigEntry(std::string key, std::string value, int priority)
        : key_(std::move(key)), value_(std::move(value)),
          priority_(priority) {}

    static constexpr std::string_view type_name() { return "ConfigEntry"; }

    void serialize(std::ostream& os) const {
        auto klen = static_cast<std::uint32_t>(key_.size());
        os.write(reinterpret_cast<const char*>(&klen), sizeof(klen));
        os.write(key_.data(), key_.size());

        auto vlen = static_cast<std::uint32_t>(value_.size());
        os.write(reinterpret_cast<const char*>(&vlen), sizeof(vlen));
        os.write(value_.data(), value_.size());

        os.write(reinterpret_cast<const char*>(&priority_), sizeof(priority_));
    }

    bool deserialize(std::istream& is) {
        try {
            std::uint32_t klen = 0;
            is.read(reinterpret_cast<char*>(&klen), sizeof(klen));
            key_.resize(klen);
            is.read(key_.data(), klen);

            std::uint32_t vlen = 0;
            is.read(reinterpret_cast<char*>(&vlen), sizeof(vlen));
            value_.resize(vlen);
            is.read(value_.data(), vlen);

            is.read(reinterpret_cast<char*>(&priority_), sizeof(priority_));
            return is.good();
        } catch (...) {
            return false;
        }
    }

    [[nodiscard]] const std::string& key() const { return key_; }
    [[nodiscard]] const std::string& value() const { return value_; }
};
```

### Type Erasure: Runtime Flexibility with Value Semantics

```cpp
/// Type erasure bridges compile-time and runtime polymorphism.
/// Unlike std::function (which erases callable types), we erase
/// the Pluggable concept into a value type that can be stored
/// in containers, copied, and moved without slicing.
///
/// The pattern: concept (interface) + inner model (type-specific)
/// + outer wrapper (value semantics with SBO).
class AnyPlugin {
    // Inner interface — the erased concept
    struct Concept {
        virtual ~Concept() = default;
        virtual std::string_view name() const = 0;
        virtual int version() const = 0;
        virtual int execute(std::span<const std::string> args) = 0;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };

    // Inner model — wraps any Pluggable type
    template <Pluggable T>
    struct Model final : Concept {
        T plugin_;

        explicit Model(T plugin) : plugin_(std::move(plugin)) {}

        std::string_view name() const override { return T::name(); }
        int version() const override { return T::version(); }

        int execute(std::span<const std::string> args) override {
            return plugin_.execute(args);
        }

        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model>(plugin_);
        }
    };

    std::unique_ptr<Concept> impl_;

public:
    /// Construct from any Pluggable type — the template is erased.
    template <Pluggable T>
    AnyPlugin(T plugin)  // NOLINT: implicit conversion is intentional
        : impl_(std::make_unique<Model<T>>(std::move(plugin))) {}

    // Value semantics: copy, move, assign
    AnyPlugin(const AnyPlugin& other) : impl_(other.impl_->clone()) {}
    AnyPlugin(AnyPlugin&&) noexcept = default;
    AnyPlugin& operator=(const AnyPlugin& other) {
        impl_ = other.impl_->clone();
        return *this;
    }
    AnyPlugin& operator=(AnyPlugin&&) noexcept = default;

    // Forwarding interface
    [[nodiscard]] std::string_view name() const { return impl_->name(); }
    [[nodiscard]] int version() const { return impl_->version(); }
    int execute(std::span<const std::string> args) { return impl_->execute(args); }
};

/// Plugin registry: stores type-erased plugins by name.
/// This enables runtime discovery without knowing concrete types.
class PluginRegistry {
    std::unordered_map<std::string, AnyPlugin> plugins_;

public:
    template <Pluggable T>
    void register_plugin(T plugin) {
        auto name = std::string(T::name());
        plugins_.emplace(std::move(name), AnyPlugin(std::move(plugin)));
    }

    int execute(std::string_view name, std::span<const std::string> args) {
        auto it = plugins_.find(std::string(name));
        if (it == plugins_.end()) {
            std::cerr << "Plugin not found: " << name << "\\n";
            return -1;
        }
        return it->second.execute(args);
    }

    void list_plugins() const {
        for (const auto& [name, plugin] : plugins_) {
            std::cout << "  " << name << " v" << plugin.version() << "\\n";
        }
    }
};
```

### Compile-Time Computation with constexpr

```cpp
/// constexpr hash for compile-time string lookup tables.
/// This lets us build switch statements on strings, which normally
/// require if/else chains or map lookups.
constexpr std::uint64_t fnv1a_hash(std::string_view str) {
    std::uint64_t hash = 14695981039346656037ULL;
    for (char c : str) {
        hash ^= static_cast<std::uint64_t>(c);
        hash *= 1099511628211ULL;
    }
    return hash;
}

/// Compile-time type registry using constexpr.
/// The compiler evaluates this at compile time — zero runtime cost.
template <typename... Types>
struct TypeRegistry {
    static constexpr std::size_t count = sizeof...(Types);

    /// Find a type by its name at compile time.
    template <std::size_t I = 0>
    static constexpr bool has_type(std::string_view name) {
        if constexpr (I >= count) {
            return false;
        } else {
            using T = std::tuple_element_t<I, std::tuple<Types...>>;
            if (T::type_name() == name) return true;
            return has_type<I + 1>(name);
        }
    }
};
```

### Putting It All Together: Concrete Plugins and Tests

```cpp
// Concrete plugin implementations satisfying the Pluggable concept.
struct GrepPlugin {
    static constexpr std::string_view name() { return "grep"; }
    static constexpr int version() { return 1; }

    int execute(std::span<const std::string> args) {
        if (args.empty()) {
            std::cerr << "grep: missing pattern\\n";
            return 1;
        }
        std::cout << "Searching for: " << args[0] << "\\n";
        return 0;
    }
};

struct WordCountPlugin {
    static constexpr std::string_view name() { return "wc"; }
    static constexpr int version() { return 2; }

    int execute(std::span<const std::string> args) {
        std::size_t total_words = 0;
        for (const auto& arg : args) {
            std::istringstream iss(arg);
            std::string word;
            while (iss >> word) ++total_words;
        }
        std::cout << "Word count: " << total_words << "\\n";
        return 0;
    }
};

// Compile-time verification that our plugins satisfy the concept
static_assert(Pluggable<GrepPlugin>);
static_assert(Pluggable<WordCountPlugin>);
static_assert(Serializable<ConfigEntry>);

void test_plugin_system() {
    PluginRegistry registry;
    registry.register_plugin(GrepPlugin{});
    registry.register_plugin(WordCountPlugin{});

    std::cout << "Registered plugins:\\n";
    registry.list_plugins();

    std::vector<std::string> args = {"hello world foo bar"};
    int result = registry.execute("wc", args);
    assert(result == 0);

    result = registry.execute("grep", std::vector<std::string>{"pattern"});
    assert(result == 0);

    // Test type erasure: copy plugin
    AnyPlugin p1 = GrepPlugin{};
    AnyPlugin p2 = p1;  // Deep copy via clone
    assert(p2.name() == "grep");

    std::cout << "Plugin system tests passed\\n";
}

void test_serialization() {
    ConfigEntry entry("database.host", "localhost:5432", 10);
    std::ostringstream os;
    entry.write_framed(os);  // CRTP method — no virtual dispatch

    // Verify round-trip
    std::string serialized = entry.to_string();
    std::istringstream is(serialized);
    ConfigEntry restored;
    assert(restored.deserialize(is));
    assert(restored.key() == "database.host");
    assert(restored.value() == "localhost:5432");

    // constexpr hash at compile time
    constexpr auto h1 = fnv1a_hash("ConfigEntry");
    constexpr auto h2 = fnv1a_hash("ConfigEntry");
    static_assert(h1 == h2, "Hash must be deterministic");

    std::cout << "Serialization tests passed\\n";
}

int main() {
    test_plugin_system();
    test_serialization();
    return 0;
}
```

### Summary and Key Takeaways

- **Concepts** replace SFINAE and give clear error messages. **Best practice**: define concepts for your domain interfaces (Serializable, Pluggable) and use them consistently. Avoid overly broad concepts like `typename T` when you have specific requirements.
- **CRTP** eliminates vtable overhead for hierarchies known at compile time. The **trade-off** is that CRTP types cannot be stored in a heterogeneous container without type erasure.
- **Type erasure** is the bridge: it uses virtual dispatch internally but presents value semantics externally. **Common mistake**: forgetting the clone method, which breaks copy semantics and leads to subtle bugs.
- **constexpr** moves computation to compile time, reducing runtime cost to zero. However, excessive constexpr can dramatically increase compile times — profile your builds.
- **Production pitfall**: template code in headers increases compile time because every translation unit instantiates its own copy. Use explicit template instantiation (`template class Foo<int>;` in a .cpp file) to reduce this.
"""
    ),
    (
        "C++ memory management with smart pointers, custom allocators, and memory-mapped I/O",
        "Explain advanced C++ memory management patterns including smart pointers in complex ownership graphs (weak_ptr for breaking cycles in observer pattern), custom allocators (arena and pool allocators), memory-mapped I/O for large file processing, and how to identify and avoid undefined behavior. Build working examples of each pattern with production-quality error handling and explain the performance implications.",
        """## C++ Memory Management: Ownership, Allocators, and Avoiding Undefined Behavior

### Why Smart Pointers Are Not Enough

`std::shared_ptr` and `std::unique_ptr` handle most ownership scenarios, but they break down in two cases: **cyclic references** (A owns B, B owns A — memory leak) and **high-frequency allocations** where the overhead of `new`/`delete` (which call `malloc`/`free`, which acquire a global mutex) becomes a **bottleneck**. Understanding when to reach for `weak_ptr`, custom allocators, or memory-mapped I/O is what separates competent C++ from production C++.

### Observer Pattern with weak_ptr

The observer pattern is a classic source of memory leaks and dangling pointers. If the subject holds `shared_ptr<Observer>`, observers can never be freed while the subject lives. If the subject holds raw pointers, you get use-after-free when an observer is destroyed. `weak_ptr` solves both: it does not prevent destruction, and it can detect when the target has been freed.

```cpp
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <new>
#include <span>
#include <string>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

// ---------- Observer Pattern with weak_ptr ----------

/// Observer interface for type-safe event notification.
template <typename EventType>
class Observer : public std::enable_shared_from_this<Observer<EventType>> {
public:
    virtual ~Observer() = default;
    virtual void on_event(const EventType& event) = 0;
};

/// Subject that notifies observers without preventing their destruction.
/// Uses weak_ptr so destroyed observers are automatically cleaned up.
/// This is a common mistake: using shared_ptr here would create a
/// reference cycle if observers also hold a reference to the subject.
template <typename EventType>
class Subject {
    mutable std::mutex mutex_;
    std::vector<std::weak_ptr<Observer<EventType>>> observers_;

public:
    /// Subscribe an observer. We store a weak_ptr, so the observer
    /// can be destroyed independently of the subject.
    void subscribe(std::shared_ptr<Observer<EventType>> observer) {
        std::lock_guard lock(mutex_);
        observers_.push_back(observer);  // Implicit conversion to weak_ptr
    }

    /// Notify all living observers and clean up dead ones.
    /// The lock() call on weak_ptr is atomic and thread-safe.
    void notify(const EventType& event) {
        std::lock_guard lock(mutex_);

        // Erase-remove idiom for dead observers
        std::erase_if(observers_, [&event](auto& weak_obs) {
            if (auto obs = weak_obs.lock()) {
                // Observer is still alive — notify it
                obs->on_event(event);
                return false;  // Keep
            }
            return true;  // Remove dead observer
        });
    }

    [[nodiscard]] std::size_t observer_count() const {
        std::lock_guard lock(mutex_);
        return observers_.size();
    }
};

// Concrete observer for testing
struct PriceUpdate { std::string symbol; double price; };

class PriceLogger : public Observer<PriceUpdate> {
    std::string name_;
public:
    explicit PriceLogger(std::string name) : name_(std::move(name)) {}
    ~PriceLogger() override {
        std::cout << name_ << " destroyed\\n";
    }

    void on_event(const PriceUpdate& event) override {
        std::cout << name_ << ": " << event.symbol
                  << " = $" << event.price << "\\n";
    }
};
```

### Arena Allocator: Bulk Allocation, Bulk Deallocation

```cpp
/// Arena (bump) allocator: allocates by incrementing a pointer.
/// Deallocation is a no-op — the entire arena is freed at once.
///
/// Performance: allocation is O(1) with no mutex contention.
/// malloc is O(log n) in the worst case and acquires a lock.
/// For request-scoped allocations (parse a request, process, free everything),
/// arenas are 10-100x faster than malloc.
///
/// The trade-off: you cannot free individual objects. If your workload
/// requires fine-grained deallocation, use a pool allocator instead.
class ArenaAllocator {
    struct Block {
        std::unique_ptr<std::byte[]> data;
        std::size_t size;
        std::size_t used;
        std::unique_ptr<Block> next;

        explicit Block(std::size_t sz)
            : data(std::make_unique<std::byte[]>(sz)), size(sz), used(0) {}
    };

    std::unique_ptr<Block> head_;
    std::size_t block_size_;
    std::size_t total_allocated_{0};

    /// Allocate a new block when the current one is full.
    void grow(std::size_t min_size) {
        auto new_size = std::max(block_size_, min_size);
        auto new_block = std::make_unique<Block>(new_size);
        new_block->next = std::move(head_);
        head_ = std::move(new_block);
    }

public:
    explicit ArenaAllocator(std::size_t initial_block_size = 64 * 1024)
        : block_size_(initial_block_size)
    {
        head_ = std::make_unique<Block>(block_size_);
    }

    /// Allocate n bytes with specified alignment.
    /// Returns nullptr only if the system is out of memory.
    [[nodiscard]] void* allocate(std::size_t size, std::size_t alignment = 8) {
        if (!head_ || head_->used + size + alignment > head_->size) {
            grow(size + alignment);
        }

        // Align the pointer
        auto* ptr = head_->data.get() + head_->used;
        auto space = head_->size - head_->used;
        void* aligned = ptr;
        if (!std::align(alignment, size, aligned, space)) {
            // Should not happen after grow, but handle defensively
            grow(size + alignment);
            ptr = head_->data.get() + head_->used;
            space = head_->size - head_->used;
            aligned = ptr;
            std::align(alignment, size, aligned, space);
        }

        head_->used = static_cast<std::size_t>(
            static_cast<std::byte*>(aligned) - head_->data.get()) + size;
        total_allocated_ += size;
        return aligned;
    }

    /// Allocate and construct an object in the arena.
    template <typename T, typename... Args>
    [[nodiscard]] T* create(Args&&... args) {
        void* mem = allocate(sizeof(T), alignof(T));
        return new (mem) T(std::forward<Args>(args)...);
    }

    /// Reset the arena: all previously allocated memory becomes invalid.
    /// This is O(number of blocks), not O(number of allocations).
    void reset() {
        // Keep the first block, release the rest
        if (head_) {
            head_->next.reset();
            head_->used = 0;
        }
        total_allocated_ = 0;
    }

    [[nodiscard]] std::size_t total_allocated() const {
        return total_allocated_;
    }
};

/// Pool allocator: fixed-size block allocation with O(1) alloc/free.
/// Use this when all objects are the same size (e.g., AST nodes, ECS components).
/// The free list is embedded in the freed blocks themselves — no extra memory.
template <std::size_t BlockSize, std::size_t BlocksPerChunk = 1024>
class PoolAllocator {
    static_assert(BlockSize >= sizeof(void*),
        "Block must be large enough to hold a free-list pointer");

    union Block {
        Block* next;
        alignas(std::max_align_t) std::byte data[BlockSize];
    };

    struct Chunk {
        std::array<Block, BlocksPerChunk> blocks;
        std::unique_ptr<Chunk> next;
    };

    std::unique_ptr<Chunk> chunks_;
    Block* free_list_{nullptr};
    std::size_t allocated_count_{0};

    void grow() {
        auto chunk = std::make_unique<Chunk>();
        // Thread the free list through the new blocks
        for (std::size_t i = 0; i < BlocksPerChunk - 1; ++i) {
            chunk->blocks[i].next = &chunk->blocks[i + 1];
        }
        chunk->blocks[BlocksPerChunk - 1].next = free_list_;
        free_list_ = &chunk->blocks[0];
        chunk->next = std::move(chunks_);
        chunks_ = std::move(chunk);
    }

public:
    PoolAllocator() { grow(); }

    [[nodiscard]] void* allocate() {
        if (!free_list_) grow();
        Block* block = free_list_;
        free_list_ = block->next;
        ++allocated_count_;
        return block->data;
    }

    void deallocate(void* ptr) {
        auto* block = reinterpret_cast<Block*>(ptr);
        block->next = free_list_;
        free_list_ = block;
        --allocated_count_;
    }

    template <typename T, typename... Args>
    [[nodiscard]] T* create(Args&&... args) {
        static_assert(sizeof(T) <= BlockSize,
            "Type is too large for this pool");
        void* mem = allocate();
        return new (mem) T(std::forward<Args>(args)...);
    }

    template <typename T>
    void destroy(T* obj) {
        obj->~T();
        deallocate(obj);
    }

    [[nodiscard]] std::size_t allocated_count() const {
        return allocated_count_;
    }
};
```

### Memory-Mapped I/O for Large Files

```cpp
/// Cross-platform memory-mapped file for zero-copy I/O.
/// Instead of read() copying data from kernel to userspace buffer,
/// mmap maps the file pages directly into the process address space.
///
/// Performance implications:
/// - No copy from kernel buffer to user buffer (zero-copy)
/// - The OS manages page-in/page-out automatically
/// - Sequential access benefits from readahead prefetching
/// - Random access is efficient because only accessed pages are loaded
///
/// Common mistake: mmapping a file on a network filesystem (NFS) —
/// the latency of page faults becomes catastrophic. Only mmap local files.
class MemoryMappedFile {
    void* data_{nullptr};
    std::size_t size_{0};
#ifdef _WIN32
    HANDLE file_handle_{INVALID_HANDLE_VALUE};
    HANDLE mapping_handle_{nullptr};
#else
    int fd_{-1};
#endif

public:
    MemoryMappedFile() = default;

    /// Open and map a file. Returns false on failure.
    [[nodiscard]] bool open(const std::filesystem::path& path) {
        close();  // Clean up any previous mapping

#ifdef _WIN32
        file_handle_ = CreateFileW(
            path.c_str(), GENERIC_READ, FILE_SHARE_READ,
            nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file_handle_ == INVALID_HANDLE_VALUE) return false;

        LARGE_INTEGER file_size;
        if (!GetFileSizeEx(file_handle_, &file_size)) {
            close();
            return false;
        }
        size_ = static_cast<std::size_t>(file_size.QuadPart);

        mapping_handle_ = CreateFileMappingW(
            file_handle_, nullptr, PAGE_READONLY, 0, 0, nullptr);
        if (!mapping_handle_) {
            close();
            return false;
        }

        data_ = MapViewOfFile(mapping_handle_, FILE_MAP_READ, 0, 0, 0);
        if (!data_) {
            close();
            return false;
        }
#else
        fd_ = ::open(path.c_str(), O_RDONLY);
        if (fd_ < 0) return false;

        struct stat st;
        if (fstat(fd_, &st) < 0) {
            close();
            return false;
        }
        size_ = static_cast<std::size_t>(st.st_size);

        data_ = mmap(nullptr, size_, PROT_READ, MAP_PRIVATE, fd_, 0);
        if (data_ == MAP_FAILED) {
            data_ = nullptr;
            close();
            return false;
        }

        // Advise the kernel we will read sequentially
        madvise(data_, size_, MADV_SEQUENTIAL);
#endif
        return true;
    }

    void close() {
#ifdef _WIN32
        if (data_) { UnmapViewOfFile(data_); data_ = nullptr; }
        if (mapping_handle_) { CloseHandle(mapping_handle_); mapping_handle_ = nullptr; }
        if (file_handle_ != INVALID_HANDLE_VALUE) {
            CloseHandle(file_handle_);
            file_handle_ = INVALID_HANDLE_VALUE;
        }
#else
        if (data_) { munmap(data_, size_); data_ = nullptr; }
        if (fd_ >= 0) { ::close(fd_); fd_ = -1; }
#endif
        size_ = 0;
    }

    ~MemoryMappedFile() { close(); }

    // Non-copyable, movable
    MemoryMappedFile(const MemoryMappedFile&) = delete;
    MemoryMappedFile& operator=(const MemoryMappedFile&) = delete;
    MemoryMappedFile(MemoryMappedFile&& other) noexcept
        : data_(other.data_), size_(other.size_)
    {
#ifdef _WIN32
        file_handle_ = other.file_handle_;
        mapping_handle_ = other.mapping_handle_;
        other.file_handle_ = INVALID_HANDLE_VALUE;
        other.mapping_handle_ = nullptr;
#else
        fd_ = other.fd_;
        other.fd_ = -1;
#endif
        other.data_ = nullptr;
        other.size_ = 0;
    }

    [[nodiscard]] std::span<const std::byte> data() const {
        return {static_cast<const std::byte*>(data_), size_};
    }

    [[nodiscard]] std::string_view as_string() const {
        return {static_cast<const char*>(data_), size_};
    }

    [[nodiscard]] std::size_t size() const { return size_; }
    [[nodiscard]] bool is_open() const { return data_ != nullptr; }
};
```

### Avoiding Undefined Behavior: A Checklist

Undefined behavior (UB) is the #1 source of security vulnerabilities in C++. The compiler **assumes UB never happens** and optimizes accordingly, which means UB can cause effects that seem impossible (time travel, code deletion).

```cpp
/// Common UB patterns and their safe alternatives.
namespace ub_examples {

// UB #1: Signed integer overflow.
// The compiler assumes this never happens and may optimize away checks.
// AVOID: if (x + 1 > x) — compiler can remove this as "always true"
// FIX: use unsigned arithmetic or __builtin_add_overflow
[[nodiscard]] bool safe_add(int a, int b, int& result) {
#if defined(__GNUC__) || defined(__clang__)
    return !__builtin_add_overflow(a, b, &result);
#else
    // Manual check: overflow occurs if both operands have same sign
    // and the result has a different sign
    result = a + b;  // technically UB if overflow, but MSVC defines it
    if (a > 0 && b > 0 && result < 0) return false;
    if (a < 0 && b < 0 && result > 0) return false;
    return true;
#endif
}

// UB #2: Use after free / dangling reference.
// This compiles and runs but returns garbage or crashes randomly.
// FIX: use weak_ptr::lock() to check if the object is still alive.
// FIX: use std::optional<std::reference_wrapper<T>> instead of T&.

// UB #3: Data race — two threads access same memory, one writes.
// FIX: use std::atomic or std::mutex.

// UB #4: Strict aliasing violation.
// Casting int* to float* and reading through it is UB.
// FIX: use std::memcpy or std::bit_cast (C++20).
[[nodiscard]] float int_bits_to_float(int x) {
    // SAFE: bit_cast is defined behavior
    return std::bit_cast<float>(x);
}

}  // namespace ub_examples
```

### Test Suite

```cpp
void test_observer_pattern() {
    Subject<PriceUpdate> market;

    auto logger1 = std::make_shared<PriceLogger>("Logger1");
    auto logger2 = std::make_shared<PriceLogger>("Logger2");

    market.subscribe(logger1);
    market.subscribe(logger2);
    assert(market.observer_count() == 2);

    market.notify(PriceUpdate{"AAPL", 150.0});

    // Destroy logger1 — subject should automatically clean up
    logger1.reset();
    market.notify(PriceUpdate{"GOOG", 2800.0});
    // After notification, dead observer is removed
    assert(market.observer_count() == 1);

    std::cout << "Observer pattern test passed\\n";
}

void test_arena_allocator() {
    ArenaAllocator arena(4096);

    // Allocate 1000 objects — much faster than 1000 malloc calls
    struct Node { int value; Node* next; };
    Node* head = nullptr;
    for (int i = 0; i < 1000; ++i) {
        auto* node = arena.create<Node>(i, head);
        head = node;
    }

    // Verify
    int count = 0;
    for (auto* n = head; n; n = n->next) ++count;
    assert(count == 1000);

    // Reset frees everything at once — O(1) effectively
    arena.reset();
    assert(arena.total_allocated() == 0);
    std::cout << "Arena allocator test passed\\n";
}

void test_pool_allocator() {
    struct SmallObj { int x; double y; };
    PoolAllocator<sizeof(SmallObj)> pool;

    auto* obj1 = pool.create<SmallObj>(42, 3.14);
    auto* obj2 = pool.create<SmallObj>(99, 2.71);

    assert(obj1->x == 42);
    assert(obj2->y == 2.71);
    assert(pool.allocated_count() == 2);

    pool.destroy(obj1);
    assert(pool.allocated_count() == 1);

    // Reuse freed slot
    auto* obj3 = pool.create<SmallObj>(7, 1.41);
    assert(pool.allocated_count() == 2);
    // obj3 likely reuses obj1's memory (LIFO free list)
    assert(obj3->x == 7);

    pool.destroy(obj2);
    pool.destroy(obj3);
    assert(pool.allocated_count() == 0);
    std::cout << "Pool allocator test passed\\n";
}

void test_mmap() {
    // Create a test file
    const auto path = std::filesystem::temp_directory_path() / "mmap_test.txt";
    {
        std::ofstream ofs(path);
        ofs << "Hello, memory-mapped world!";
    }

    MemoryMappedFile mmf;
    assert(mmf.open(path));
    assert(mmf.is_open());
    assert(mmf.as_string() == "Hello, memory-mapped world!");
    std::cout << "Memory-mapped I/O test passed\\n";

    mmf.close();
    std::filesystem::remove(path);
}

int main() {
    test_observer_pattern();
    test_arena_allocator();
    test_pool_allocator();
    test_mmap();

    int result = 0;
    assert(ub_examples::safe_add(INT32_MAX, 1, result) == false);
    assert(ub_examples::safe_add(100, 200, result) == true);
    assert(result == 300);

    std::cout << "All memory management tests passed\\n";
    return 0;
}
```

### Summary and Key Takeaways

- **`weak_ptr` breaks ownership cycles** — use it whenever two objects reference each other. The observer pattern is the canonical example, but it also applies to caches, parent-child trees, and dependency graphs.
- **Arena allocators** are 10-100x faster than `malloc` for request-scoped allocations. The **trade-off** is that individual deallocation is impossible — you free everything at once. This is perfect for parsers, compilers, and per-request server processing.
- **Pool allocators** give O(1) alloc and O(1) free for fixed-size objects. The free list is embedded in the freed blocks, so there is zero overhead per block. **Best practice**: use pools for ECS components, AST nodes, and network packet buffers.
- **Memory-mapped I/O** eliminates the kernel-to-user copy for file reads. **Common mistake**: using mmap for small files (< 4KB) — the page fault overhead exceeds the benefit of zero-copy. Use `read()` for small files, `mmap` for large sequential or random-access files.
- **Undefined behavior** is not "implementation-defined" — it means **anything can happen**, including nasal demons. Always compile with `-fsanitize=undefined,address` during development to catch UB early. In production, use hardened builds (`-D_FORTIFY_SOURCE=2 -fstack-protector-strong`).
"""
    ),
]
