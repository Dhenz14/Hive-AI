"""Modern C++ (C++20/23) — concepts, ranges, coroutines, std::expected, smart pointers and RAII."""

PAIRS = [
    (
        "cpp/concepts-constraints",
        "Show C++20 concepts and constraints including defining concepts, constraining templates, and requires expressions.",
        '''C++20 concepts and constraints for type-safe generic programming:

```cpp
// --- Defining and using concepts ---

#include <concepts>
#include <iostream>
#include <string>
#include <vector>
#include <numeric>
#include <type_traits>

// Basic concept: requires a type to support certain operations
template<typename T>
concept Numeric = std::integral<T> || std::floating_point<T>;

template<typename T>
concept Addable = requires(T a, T b) {
    { a + b } -> std::convertible_to<T>;
};

template<typename T>
concept Printable = requires(std::ostream& os, const T& val) {
    { os << val } -> std::same_as<std::ostream&>;
};

// Concept with multiple requirements
template<typename T>
concept Hashable = requires(T val) {
    { std::hash<T>{}(val) } -> std::convertible_to<std::size_t>;
};

// Compound concept combining others
template<typename T>
concept Sortable = std::totally_ordered<T> && std::movable<T>;

// Concept for container-like types
template<typename C>
concept Container = requires(C c) {
    typename C::value_type;
    typename C::iterator;
    { c.begin() } -> std::input_or_output_iterator;
    { c.end() } -> std::sentinel_for<decltype(c.begin())>;
    { c.size() } -> std::convertible_to<std::size_t>;
    { c.empty() } -> std::convertible_to<bool>;
};

// Concept for callable with specific signature
template<typename F, typename... Args>
concept Invocable = std::invocable<F, Args...>;

template<typename F, typename R, typename... Args>
concept InvocableReturning = std::invocable<F, Args...> &&
    std::convertible_to<std::invoke_result_t<F, Args...>, R>;
```

```cpp
// --- Using concepts in function templates ---

#include <algorithm>
#include <ranges>
#include <span>

// Syntax 1: requires clause
template<typename T>
    requires Numeric<T>
T sum(std::span<const T> values) {
    return std::accumulate(values.begin(), values.end(), T{});
}

// Syntax 2: concept as type constraint (terse syntax)
auto multiply(Numeric auto a, Numeric auto b) {
    return a * b;
}

// Syntax 3: trailing requires clause
template<typename T>
T clamp_value(T value, T min_val, T max_val)
    requires std::totally_ordered<T>
{
    if (value < min_val) return min_val;
    if (value > max_val) return max_val;
    return value;
}

// Constrained template class
template<Sortable T>
class SortedSet {
public:
    void insert(const T& value) {
        auto pos = std::lower_bound(data_.begin(), data_.end(), value);
        if (pos == data_.end() || *pos != value) {
            data_.insert(pos, value);
        }
    }

    bool contains(const T& value) const {
        return std::binary_search(data_.begin(), data_.end(), value);
    }

    std::size_t size() const { return data_.size(); }

    auto begin() const { return data_.begin(); }
    auto end() const { return data_.end(); }

private:
    std::vector<T> data_;
};

// Overloading with concepts (most constrained wins)
void process(auto value) {
    std::cout << "Generic: " << typeid(value).name() << "\\n";
}

void process(Numeric auto value) {
    std::cout << "Numeric: " << value << "\\n";
}

void process(std::integral auto value) {
    // More constrained than Numeric — preferred for integers
    std::cout << "Integral: " << value << "\\n";
}

// Concept-based function dispatch
template<Container C>
void print_container(const C& container) {
    std::cout << "[";
    bool first = true;
    for (const auto& elem : container) {
        if (!first) std::cout << ", ";
        std::cout << elem;
        first = false;
    }
    std::cout << "]\\n";
}
```

```cpp
// --- Advanced requires expressions ---

#include <memory>
#include <optional>

// Nested requirements
template<typename T>
concept Serializable = requires(T val, std::ostream& os, std::istream& is) {
    // Simple requirement: expression must be valid
    val.serialize(os);
    // Type requirement: nested type must exist
    typename T::serialized_type;
    // Compound requirement: expression valid + return type constraint
    { val.serialize(os) } -> std::same_as<bool>;
    { T::deserialize(is) } -> std::same_as<std::optional<T>>;
    // Nested requirement: additional constraints
    requires std::copyable<T>;
    requires sizeof(T) <= 1024;  // Size constraint
};

// Requires expression as a boolean
template<typename T>
constexpr bool has_toString = requires(const T& val) {
    { val.toString() } -> std::convertible_to<std::string>;
};

// SFINAE replacement with concepts
template<typename T>
concept SmartPointerLike = requires(T ptr) {
    { *ptr } -> std::same_as<typename T::element_type&>;
    { ptr.get() } -> std::same_as<typename T::element_type*>;
    { static_cast<bool>(ptr) };
};

// Generic factory with constraints
template<typename T, typename... Args>
    requires std::constructible_from<T, Args...>
std::unique_ptr<T> make(Args&&... args) {
    return std::make_unique<T>(std::forward<Args>(args)...);
}

int main() {
    // Concept usage
    process(42);          // "Integral: 42"
    process(3.14);        // "Numeric: 3.14"
    process("hello");     // "Generic: ..."

    SortedSet<int> set;
    set.insert(5);
    set.insert(3);
    set.insert(7);
    print_container(set); // [3, 5, 7]

    int arr[] = {1, 2, 3, 4, 5};
    std::cout << sum<int>(arr) << "\\n"; // 15

    // Concepts checked at compile time
    // SortedSet<std::vector<int>> bad; // ERROR: vector<int> is not Sortable
}
```

Concept definition styles:

| Style | Syntax | Use Case |
|-------|--------|----------|
| Simple concept | `concept X = std::integral<T>` | Alias for existing constraints |
| Requires expression | `concept X = requires(T v) { v.foo(); }` | Check operations exist |
| Compound requirement | `{ expr } -> constraint` | Check expression + return type |
| Nested requirement | `requires std::copyable<T>` | Compose constraints |
| Conjunction | `concept X = A<T> && B<T>` | Multiple requirements |
| Disjunction | `concept X = A<T> \\|\\| B<T>` | Alternative requirements |

Key patterns:
1. Concepts replace SFINAE with clear, readable constraints — error messages show which concept failed
2. Use the terse syntax (`Numeric auto x`) for short constraints; use `requires` clauses for complex ones
3. Overload resolution picks the most constrained matching concept — enables clean function dispatch
4. `requires` expressions check validity of operations at compile time without executing them
5. Combine standard library concepts (`std::integral`, `std::totally_ordered`, `std::invocable`) with custom ones
6. Concepts subsume each other: `std::integral` is more constrained than `Numeric`, so it wins in overload resolution'''
    ),
    (
        "cpp/ranges-views",
        "Show C++20 ranges and views including lazy evaluation, view adapters, custom views, and pipeline composition.",
        '''C++20 ranges and views for composable, lazy data processing:

```cpp
// --- Ranges basics and view adapters ---

#include <ranges>
#include <algorithm>
#include <iostream>
#include <vector>
#include <string>
#include <numeric>
#include <map>

namespace views = std::ranges::views;

void ranges_fundamentals() {
    std::vector<int> numbers = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // Lazy pipeline: no intermediate containers created
    auto result = numbers
        | views::filter([](int n) { return n % 2 == 0; })     // 2, 4, 6, 8, 10
        | views::transform([](int n) { return n * n; })        // 4, 16, 36, 64, 100
        | views::take(3);                                       // 4, 16, 36

    // Materialize into a vector
    std::vector<int> squares(result.begin(), result.end());
    // Or in C++23: auto squares = result | std::ranges::to<std::vector>();

    // views::iota — infinite sequence generator
    auto first_10_squares = views::iota(1)
        | views::transform([](int n) { return n * n; })
        | views::take(10);

    for (int sq : first_10_squares) {
        std::cout << sq << " "; // 1 4 9 16 25 36 49 64 81 100
    }
    std::cout << "\\n";

    // views::zip (C++23) — combine multiple ranges
    std::vector<std::string> names = {"Alice", "Bob", "Charlie"};
    std::vector<int> scores = {95, 87, 92};

    // C++23: for (auto [name, score] : views::zip(names, scores)) { ... }

    // views::enumerate (C++23) — index + value
    // for (auto [i, name] : views::enumerate(names)) { ... }

    // views::chunk (C++23) — split into groups
    auto chunks = views::iota(1, 10) | views::chunk(3);
    // [[1,2,3], [4,5,6], [7,8,9]]

    // views::slide (C++23) — sliding window
    auto windows = views::iota(1, 6) | views::slide(3);
    // [[1,2,3], [2,3,4], [3,4,5]]
}

// String processing with ranges
void string_processing() {
    std::string csv = "Alice,Bob,Charlie,Diana,Eve";

    // Split string
    auto names = csv | views::split(',');
    for (auto name_range : names) {
        std::string name(name_range.begin(), name_range.end());
        std::cout << name << "\\n";
    }

    // views::join — flatten ranges
    std::vector<std::vector<int>> nested = {{1, 2}, {3, 4}, {5, 6}};
    auto flat = nested | views::join;
    for (int n : flat) std::cout << n << " "; // 1 2 3 4 5 6

    // Reverse and drop
    std::vector<int> nums = {1, 2, 3, 4, 5};
    auto last_three = nums
        | views::reverse
        | views::take(3)
        | views::reverse; // Back to original order: 3, 4, 5
}
```

```cpp
// --- Range algorithms (constrained versions) ---

#include <ranges>
#include <algorithm>
#include <vector>
#include <string>

struct Employee {
    std::string name;
    std::string department;
    double salary;
    int years;
};

void range_algorithms() {
    std::vector<Employee> employees = {
        {"Alice", "Engineering", 120000, 5},
        {"Bob", "Marketing", 85000, 3},
        {"Charlie", "Engineering", 140000, 8},
        {"Diana", "Marketing", 95000, 6},
        {"Eve", "Engineering", 130000, 4},
    };

    // ranges::sort with projection
    std::ranges::sort(employees, std::ranges::greater{},
        &Employee::salary);
    // Sorted by salary descending

    // ranges::find_if with projection
    auto senior = std::ranges::find_if(employees,
        [](int years) { return years > 5; },
        &Employee::years);

    if (senior != employees.end()) {
        std::cout << "Senior: " << senior->name << "\\n";
    }

    // ranges::count_if
    auto eng_count = std::ranges::count_if(employees,
        [](const std::string& dept) { return dept == "Engineering"; },
        &Employee::department);

    // ranges::min_element / max_element with projection
    auto highest_paid = std::ranges::max_element(employees,
        {}, &Employee::salary);

    // ranges::all_of / any_of / none_of
    bool all_high = std::ranges::all_of(employees,
        [](double s) { return s > 80000; },
        &Employee::salary);

    // ranges::partition
    auto [eng_end, _] = std::ranges::partition(employees,
        [](const std::string& d) { return d == "Engineering"; },
        &Employee::department);

    // ranges::unique (after sorting)
    std::vector<int> nums = {1, 1, 2, 2, 3, 3, 3, 4};
    auto [new_end, old_end] = std::ranges::unique(nums);
    nums.erase(new_end, nums.end()); // {1, 2, 3, 4}

    // ranges::fold_left (C++23) — like std::accumulate but range-based
    // double total = std::ranges::fold_left(employees, 0.0,
    //     [](double acc, const Employee& e) { return acc + e.salary; });
}

// Projections replace verbose lambda patterns
void projections_demo() {
    std::vector<std::pair<std::string, int>> scores = {
        {"Alice", 95}, {"Bob", 87}, {"Charlie", 92}
    };

    // Old way:
    // std::sort(scores.begin(), scores.end(),
    //     [](const auto& a, const auto& b) { return a.second > b.second; });

    // Ranges with projection:
    std::ranges::sort(scores, std::ranges::greater{}, &std::pair<std::string, int>::second);
}
```

```cpp
// --- Custom view and practical patterns ---

#include <ranges>
#include <vector>
#include <optional>
#include <functional>

// Custom range adaptor closure (C++23 style)
// Filter + transform in one pass
template<typename Pred, typename Func>
auto filter_map(Pred pred, Func func) {
    return views::transform([pred, func](const auto& elem) -> std::optional<decltype(func(elem))> {
        if (pred(elem)) return func(elem);
        return std::nullopt;
    })
    | views::filter([](const auto& opt) { return opt.has_value(); })
    | views::transform([](const auto& opt) { return *opt; });
}

// Practical: data processing pipeline
struct LogEntry {
    std::string level;    // "INFO", "WARN", "ERROR"
    std::string message;
    int timestamp;
};

void process_logs(const std::vector<LogEntry>& logs) {
    // Pipeline: filter errors -> extract messages -> take first 5
    auto error_messages = logs
        | views::filter([](const LogEntry& log) {
            return log.level == "ERROR";
        })
        | views::transform(&LogEntry::message)
        | views::take(5);

    for (const auto& msg : error_messages) {
        std::cout << "ERROR: " << msg << "\\n";
    }

    // Group-like operation: count by level
    std::map<std::string, int> counts;
    for (const auto& log : logs) {
        counts[log.level]++;
    }

    // Running average pattern
    std::vector<double> values = {10.0, 20.0, 30.0, 40.0, 50.0};
    std::vector<double> running_avg;
    double sum = 0;
    int count = 0;
    for (double v : values) {
        sum += v;
        count++;
        running_avg.push_back(sum / count);
    }
}

// Type-erased range (for interfaces)
void print_ints(std::ranges::input_range auto&& range)
    requires std::same_as<std::ranges::range_value_t<decltype(range)>, int>
{
    for (int val : range) {
        std::cout << val << " ";
    }
    std::cout << "\\n";
}

int main() {
    ranges_fundamentals();
    string_processing();
    range_algorithms();

    // Views are cheap to copy (they do not own data)
    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    auto even_squares = data
        | views::filter([](int n) { return n % 2 == 0; })
        | views::transform([](int n) { return n * n; });

    // Can iterate multiple times
    print_ints(even_squares);
    print_ints(even_squares);

    return 0;
}
```

View adaptor comparison:

| Adaptor | Category | C++ Version | Example |
|---------|----------|------------|---------|
| `views::filter` | Selection | C++20 | `v \\| views::filter(pred)` |
| `views::transform` | Projection | C++20 | `v \\| views::transform(fn)` |
| `views::take` | Truncation | C++20 | `v \\| views::take(5)` |
| `views::drop` | Truncation | C++20 | `v \\| views::drop(3)` |
| `views::reverse` | Reorder | C++20 | `v \\| views::reverse` |
| `views::split` | Decomposition | C++20 | `s \\| views::split(',')` |
| `views::join` | Flattening | C++20 | `nested \\| views::join` |
| `views::iota` | Generation | C++20 | `views::iota(1, 100)` |
| `views::zip` | Combination | C++23 | `views::zip(a, b)` |
| `views::chunk` | Grouping | C++23 | `v \\| views::chunk(3)` |
| `views::slide` | Windowing | C++23 | `v \\| views::slide(3)` |
| `views::enumerate` | Indexing | C++23 | `v \\| views::enumerate` |
| `std::ranges::to<V>` | Materialization | C++23 | `v \\| std::ranges::to<vector>()` |

Key patterns:
1. Views are lazy — they compute values on demand, creating no intermediate containers
2. Use the pipe operator (`|`) to compose view adaptors into readable pipelines
3. Range algorithms (`std::ranges::sort`) accept projections, eliminating verbose comparison lambdas
4. Views do not own data — they reference the underlying range, so the source must outlive the view
5. `views::iota` creates infinite sequences — combine with `views::take` to limit output
6. C++23 adds `std::ranges::to<Container>()` for materializing views into concrete containers'''
    ),
    (
        "cpp/coroutines",
        "Show C++20 coroutines including co_await, co_yield, generators, and async task patterns.",
        '''C++20 coroutines for generators and async programming:

```cpp
// --- Generator coroutine ---

#include <coroutine>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <vector>
#include <string>

// Generator<T>: produces a lazy sequence of values via co_yield
template<typename T>
class Generator {
public:
    struct promise_type {
        T current_value;
        std::exception_ptr exception;

        Generator get_return_object() {
            return Generator{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }

        std::suspend_always initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }

        std::suspend_always yield_value(T value) {
            current_value = std::move(value);
            return {};
        }

        void return_void() {}

        void unhandled_exception() {
            exception = std::current_exception();
        }
    };

    using handle_type = std::coroutine_handle<promise_type>;

    explicit Generator(handle_type handle) : handle_(handle) {}

    ~Generator() {
        if (handle_) handle_.destroy();
    }

    // Move-only
    Generator(Generator&& other) noexcept : handle_(other.handle_) {
        other.handle_ = nullptr;
    }
    Generator& operator=(Generator&& other) noexcept {
        if (this != &other) {
            if (handle_) handle_.destroy();
            handle_ = other.handle_;
            other.handle_ = nullptr;
        }
        return *this;
    }
    Generator(const Generator&) = delete;
    Generator& operator=(const Generator&) = delete;

    // Iterator interface for range-based for
    class iterator {
        handle_type handle_;
    public:
        using iterator_category = std::input_iterator_tag;
        using value_type = T;
        using difference_type = std::ptrdiff_t;

        explicit iterator(handle_type handle) : handle_(handle) {}

        T& operator*() { return handle_.promise().current_value; }
        iterator& operator++() {
            handle_.resume();
            if (handle_.done()) {
                if (auto& ex = handle_.promise().exception) {
                    std::rethrow_exception(ex);
                }
            }
            return *this;
        }
        bool operator==(std::default_sentinel_t) const { return handle_.done(); }
    };

    iterator begin() {
        handle_.resume(); // Execute until first yield
        return iterator{handle_};
    }
    std::default_sentinel_t end() { return {}; }

private:
    handle_type handle_;
};
```

```cpp
// --- Using generators ---

// Fibonacci sequence generator
Generator<uint64_t> fibonacci() {
    uint64_t a = 0, b = 1;
    while (true) {
        co_yield a;
        auto next = a + b;
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

// File line reader generator
Generator<std::string> read_lines(const std::string& filename) {
    std::ifstream file(filename);
    std::string line;
    while (std::getline(file, line)) {
        co_yield std::move(line);
    }
}

// Flat map: yield from nested ranges
Generator<int> flatten(const std::vector<std::vector<int>>& nested) {
    for (const auto& inner : nested) {
        for (int val : inner) {
            co_yield val;
        }
    }
}

// Filter generator
Generator<int> filter_gen(Generator<int> source, std::function<bool(int)> pred) {
    for (int val : source) {
        if (pred(val)) {
            co_yield val;
        }
    }
}

void generator_usage() {
    // Take first 10 Fibonacci numbers
    int count = 0;
    for (auto fib : fibonacci()) {
        if (count++ >= 10) break;
        std::cout << fib << " "; // 0 1 1 2 3 5 8 13 21 34
    }
    std::cout << "\\n";

    // Compose generators
    for (int val : range(0, 20, 3)) {
        std::cout << val << " "; // 0 3 6 9 12 15 18
    }
    std::cout << "\\n";

    // Lazy pipeline
    std::vector<std::vector<int>> data = {{1, 2, 3}, {4, 5, 6}, {7, 8, 9}};
    for (int val : flatten(data)) {
        std::cout << val << " ";
    }
    std::cout << "\\n";
}
```

```cpp
// --- Async Task coroutine (simplified) ---

#include <coroutine>
#include <future>
#include <thread>
#include <functional>

// Simple async Task<T>
template<typename T>
class Task {
public:
    struct promise_type {
        std::optional<T> result;
        std::exception_ptr exception;
        std::coroutine_handle<> continuation;

        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        std::suspend_never initial_suspend() { return {}; }

        auto final_suspend() noexcept {
            struct Awaiter {
                bool await_ready() noexcept { return false; }
                std::coroutine_handle<> await_suspend(
                    std::coroutine_handle<promise_type> h) noexcept {
                    if (h.promise().continuation)
                        return h.promise().continuation;
                    return std::noop_coroutine();
                }
                void await_resume() noexcept {}
            };
            return Awaiter{};
        }

        void return_value(T value) { result = std::move(value); }
        void unhandled_exception() { exception = std::current_exception(); }
    };

    // Awaitable interface
    bool await_ready() const { return handle_.done(); }

    std::coroutine_handle<> await_suspend(std::coroutine_handle<> caller) {
        handle_.promise().continuation = caller;
        return handle_;
    }

    T await_resume() {
        if (handle_.promise().exception) {
            std::rethrow_exception(handle_.promise().exception);
        }
        return std::move(*handle_.promise().result);
    }

    // Get result (blocking)
    T get() {
        // Simplified: in real code, use proper synchronization
        while (!handle_.done()) {
            std::this_thread::yield();
        }
        return await_resume();
    }

    ~Task() { if (handle_) handle_.destroy(); }

    Task(Task&& other) noexcept : handle_(other.handle_) {
        other.handle_ = nullptr;
    }
    Task(const Task&) = delete;

private:
    explicit Task(std::coroutine_handle<promise_type> h) : handle_(h) {}
    std::coroutine_handle<promise_type> handle_;
};

// Usage: composing async tasks
Task<int> compute_value(int x) {
    // Simulate async work
    co_return x * x;
}

Task<int> combine_values() {
    int a = co_await compute_value(3);
    int b = co_await compute_value(4);
    co_return a + b; // 9 + 16 = 25
}

int main() {
    generator_usage();

    auto task = combine_values();
    std::cout << "Result: " << task.get() << "\\n"; // 25

    return 0;
}
```

Coroutine keyword comparison:

| Keyword | Purpose | Return Type | Suspends? |
|---------|---------|-------------|-----------|
| `co_yield value` | Produce value in sequence | Generator<T> | Yes (after yield) |
| `co_return value` | Return final result | Task<T> | Yes (final suspend) |
| `co_return` | Complete void coroutine | Task<void> | Yes (final suspend) |
| `co_await expr` | Suspend until expr ready | Any awaitable | Conditional |
| `initial_suspend` | Before body executes | suspend_always/never | Configuration |
| `final_suspend` | After body completes | suspend_always/never | Configuration |

Key patterns:
1. Generators use `co_yield` + `suspend_always` to lazily produce values on demand
2. Tasks use `co_await` + `co_return` for async composition without callbacks
3. The `promise_type` nested struct controls coroutine behavior (suspend points, return handling, exceptions)
4. Generators are lazy and composable — values are computed only when iterated
5. Always implement move semantics and delete copy operations for coroutine handle wrappers
6. Use `std::generator<T>` (C++23) instead of writing custom generator types when available'''
    ),
    (
        "cpp/expected-print",
        "Show C++23 std::expected for error handling and std::print for formatted output, comparing to exceptions and printf.",
        '''C++23 std::expected and std::print for modern error handling and output:

```cpp
// --- std::expected for value-or-error returns ---

#include <expected>
#include <string>
#include <system_error>
#include <fstream>
#include <vector>
#include <charconv>
#include <format>

// Error type for domain errors
enum class ParseError {
    EmptyInput,
    InvalidFormat,
    OutOfRange,
    UnknownField,
};

std::string to_string(ParseError e) {
    switch (e) {
        case ParseError::EmptyInput:    return "Empty input";
        case ParseError::InvalidFormat: return "Invalid format";
        case ParseError::OutOfRange:    return "Value out of range";
        case ParseError::UnknownField:  return "Unknown field";
    }
    return "Unknown error";
}

// Functions returning expected<T, E> instead of throwing
std::expected<int, ParseError> parse_int(std::string_view str) {
    if (str.empty()) {
        return std::unexpected(ParseError::EmptyInput);
    }

    int value;
    auto [ptr, ec] = std::from_chars(str.data(), str.data() + str.size(), value);
    if (ec != std::errc{}) {
        return std::unexpected(ParseError::InvalidFormat);
    }
    return value;
}

std::expected<double, ParseError> parse_temperature(std::string_view str) {
    auto result = parse_int(str);
    if (!result) {
        return std::unexpected(result.error());
    }

    double temp = static_cast<double>(*result);
    if (temp < -273.15 || temp > 1000.0) {
        return std::unexpected(ParseError::OutOfRange);
    }
    return temp;
}

// Monadic operations (C++23)
struct Config {
    std::string host;
    int port;
    int max_connections;
};

std::expected<Config, std::string> load_config(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        return std::unexpected("Cannot open config file: " + path);
    }

    // Chain operations with and_then, transform, or_else
    auto parse_port = [](std::string_view val) -> std::expected<int, std::string> {
        int port;
        auto [ptr, ec] = std::from_chars(val.data(), val.data() + val.size(), port);
        if (ec != std::errc{}) return std::unexpected("Invalid port");
        if (port < 1 || port > 65535) return std::unexpected("Port out of range");
        return port;
    };

    // Using and_then for chaining
    auto result = parse_port("8080")
        .and_then([](int port) -> std::expected<Config, std::string> {
            return Config{"localhost", port, 100};
        })
        .transform([](Config cfg) {
            cfg.max_connections = 200; // Modify the value
            return cfg;
        })
        .or_else([](const std::string& err) -> std::expected<Config, std::string> {
            // Fallback to defaults
            return Config{"localhost", 3000, 50};
        });

    return result;
}
```

```cpp
// --- std::expected in layered architecture ---

#include <expected>
#include <variant>
#include <memory>

// Domain errors as a variant
struct NotFoundError { std::string resource; };
struct ValidationError { std::string field; std::string message; };
struct DatabaseError { int code; std::string message; };

using AppError = std::variant<NotFoundError, ValidationError, DatabaseError>;

struct User {
    int id;
    std::string name;
    std::string email;
};

// Repository layer
class UserRepository {
public:
    std::expected<User, AppError> find_by_id(int id) {
        if (id <= 0) {
            return std::unexpected(ValidationError{"id", "must be positive"});
        }
        // Simulate DB lookup
        if (id == 999) {
            return std::unexpected(DatabaseError{500, "Connection timeout"});
        }
        if (id > 100) {
            return std::unexpected(NotFoundError{"User:" + std::to_string(id)});
        }
        return User{id, "Alice", "alice@example.com"};
    }
};

// Service layer
class UserService {
    UserRepository repo_;
public:
    std::expected<User, AppError> get_user(int id) {
        return repo_.find_by_id(id)
            .transform([](User u) {
                // Post-processing
                u.email = mask_email(u.email);
                return u;
            });
    }

    static std::string mask_email(const std::string& email) {
        auto at = email.find('@');
        if (at == std::string::npos || at < 2) return email;
        return email.substr(0, 1) + "***" + email.substr(at);
    }
};

// Handler layer
std::string handle_user_request(int user_id) {
    UserService service;
    auto result = service.get_user(user_id);

    if (result.has_value()) {
        const auto& user = result.value();
        return std::format("User: {} ({})", user.name, user.email);
    }

    // Pattern match on error type
    return std::visit([](const auto& err) -> std::string {
        using T = std::decay_t<decltype(err)>;
        if constexpr (std::is_same_v<T, NotFoundError>) {
            return std::format("404: {} not found", err.resource);
        } else if constexpr (std::is_same_v<T, ValidationError>) {
            return std::format("400: {}: {}", err.field, err.message);
        } else if constexpr (std::is_same_v<T, DatabaseError>) {
            return std::format("500: DB error {}: {}", err.code, err.message);
        }
    }, result.error());
}
```

```cpp
// --- std::print and std::format (C++23) ---

#include <print>    // C++23
#include <format>   // C++20
#include <vector>
#include <chrono>

void print_examples() {
    // std::print — type-safe printf replacement
    std::print("Hello, {}!\\n", "world");
    std::print("Pi is approximately {:.4f}\\n", 3.14159);
    std::print("Hex: {:#x}, Oct: {:#o}, Bin: {:#b}\\n", 255, 255, 255);

    // std::println — includes newline
    std::println("Value: {}", 42);

    // Positional arguments
    std::print("{1} loves {0}\\n", "cats", "Alice");

    // Width and alignment
    std::print("{:>10}\\n", "right");     // "     right"
    std::print("{:<10}\\n", "left");      // "left      "
    std::print("{:^10}\\n", "center");    // "  center  "
    std::print("{:*^10}\\n", "pad");      // "***pad****"

    // std::format returns a string
    std::string msg = std::format("Error {}: {}", 404, "Not Found");

    // Formatting containers (C++23 ranges formatting)
    std::vector<int> nums = {1, 2, 3, 4, 5};
    std::println("{}", nums);  // [1, 2, 3, 4, 5]

    // Chrono formatting
    auto now = std::chrono::system_clock::now();
    std::println("Current time: {:%Y-%m-%d %H:%M:%S}", now);

    // Custom formatter (C++20)
    // struct std::formatter<User> : std::formatter<std::string> {
    //     auto format(const User& u, auto& ctx) const {
    //         return std::format_to(ctx.out(), "User({}, {})", u.name, u.email);
    //     }
    // };
}

// Table formatting utility
void print_table() {
    struct Row { std::string name; int score; double gpa; };
    std::vector<Row> rows = {
        {"Alice", 95, 3.9}, {"Bob", 87, 3.5}, {"Charlie", 92, 3.7},
    };

    std::println("{:<10} {:>6} {:>6}", "Name", "Score", "GPA");
    std::println("{:-<10} {:->6} {:->6}", "", "", "");
    for (const auto& [name, score, gpa] : rows) {
        std::println("{:<10} {:>6} {:>6.1f}", name, score, gpa);
    }
    // Name        Score    GPA
    // ---------- ------ ------
    // Alice          95    3.9
    // Bob            87    3.5
    // Charlie        92    3.7
}

int main() {
    // std::expected usage
    auto result = parse_int("42");
    if (result) {
        std::println("Parsed: {}", *result);
    }

    auto bad = parse_int("abc");
    if (!bad) {
        std::println("Error: {}", to_string(bad.error()));
    }

    std::println("{}", handle_user_request(1));
    std::println("{}", handle_user_request(200));
    std::println("{}", handle_user_request(-1));

    print_table();
    return 0;
}
```

Error handling approach comparison:

| Approach | Overhead | Composable? | C++ Version | Use Case |
|----------|---------|-------------|-------------|----------|
| Exceptions | Stack unwinding | Try-catch | C++98 | Truly exceptional cases |
| `std::expected<T,E>` | Zero (value type) | `.and_then`, `.transform` | C++23 | Expected failure paths |
| `std::optional<T>` | Zero | `.transform`, `.or_else` | C++17 | Missing value (no error info) |
| Error codes | Zero | Manual `if` chains | C | C interop, performance-critical |
| `std::error_code` | Zero | `std::system_error` | C++11 | System/OS errors |
| `std::variant<T,E>` | Zero | `std::visit` | C++17 | Multiple error types |

Key patterns:
1. `std::expected<T, E>` returns either a value or an error — no exceptions, no runtime overhead
2. Monadic operations (`.and_then`, `.transform`, `.or_else`) chain computations without manual error checking
3. Use `std::unexpected(error)` to construct the error case — analogous to returning an error
4. Combine `std::expected` with `std::variant` for multiple error types with pattern matching via `std::visit`
5. `std::print` / `std::println` (C++23) replace `printf` and `cout` with type-safe, format-string-based output
6. `std::format` (C++20) returns `std::string` — use it for building error messages and log output'''
    ),
    (
        "cpp/smart-pointers-raii",
        "Show C++ smart pointers and RAII patterns including unique_ptr, shared_ptr, weak_ptr, and custom deleters.",
        '''C++ smart pointers and RAII for automatic resource management:

```cpp
// --- unique_ptr: exclusive ownership ---

#include <memory>
#include <iostream>
#include <vector>
#include <fstream>
#include <functional>
#include <cassert>

// Basic unique_ptr usage
class DatabaseConnection {
public:
    explicit DatabaseConnection(const std::string& url) : url_(url) {
        std::cout << "Connected to " << url_ << "\\n";
    }
    ~DatabaseConnection() {
        std::cout << "Disconnected from " << url_ << "\\n";
    }

    void query(const std::string& sql) {
        std::cout << "Executing: " << sql << "\\n";
    }

    // Non-copyable, movable
    DatabaseConnection(const DatabaseConnection&) = delete;
    DatabaseConnection& operator=(const DatabaseConnection&) = delete;

private:
    std::string url_;
};

// Factory function returning unique_ptr
std::unique_ptr<DatabaseConnection> create_connection(const std::string& url) {
    return std::make_unique<DatabaseConnection>(url);
}

// Unique ownership transfer
class Repository {
public:
    explicit Repository(std::unique_ptr<DatabaseConnection> conn)
        : conn_(std::move(conn)) {}  // Takes ownership

    void find_user(int id) {
        conn_->query("SELECT * FROM users WHERE id = " + std::to_string(id));
    }

private:
    std::unique_ptr<DatabaseConnection> conn_;
};

// unique_ptr with custom deleter
struct FileDeleter {
    void operator()(FILE* fp) const {
        if (fp) {
            std::fclose(fp);
            std::cout << "File closed\\n";
        }
    }
};

using FilePtr = std::unique_ptr<FILE, FileDeleter>;

FilePtr open_file(const char* path, const char* mode) {
    return FilePtr(std::fopen(path, mode));
}

// Lambda deleter for C library resources
auto create_ssl_context() {
    auto deleter = [](SSL_CTX* ctx) {
        // SSL_CTX_free(ctx);
    };
    // return std::unique_ptr<SSL_CTX, decltype(deleter)>(SSL_CTX_new(), deleter);
}

// unique_ptr for polymorphism
class Shape {
public:
    virtual ~Shape() = default;
    virtual double area() const = 0;
    virtual std::string name() const = 0;
};

class Circle : public Shape {
    double radius_;
public:
    explicit Circle(double r) : radius_(r) {}
    double area() const override { return 3.14159 * radius_ * radius_; }
    std::string name() const override { return "Circle"; }
};

class Rectangle : public Shape {
    double w_, h_;
public:
    Rectangle(double w, double h) : w_(w), h_(h) {}
    double area() const override { return w_ * h_; }
    std::string name() const override { return "Rectangle"; }
};

// Collection of polymorphic objects
std::vector<std::unique_ptr<Shape>> create_shapes() {
    std::vector<std::unique_ptr<Shape>> shapes;
    shapes.push_back(std::make_unique<Circle>(5.0));
    shapes.push_back(std::make_unique<Rectangle>(3.0, 4.0));
    return shapes;
}
```

```cpp
// --- shared_ptr and weak_ptr ---

#include <memory>
#include <unordered_map>
#include <mutex>
#include <string>

// shared_ptr: reference-counted shared ownership
class CacheEntry {
public:
    CacheEntry(std::string key, std::string value)
        : key_(std::move(key)), value_(std::move(value)) {}

    const std::string& key() const { return key_; }
    const std::string& value() const { return value_; }

private:
    std::string key_;
    std::string value_;
};

// Cache with weak_ptr to avoid preventing cleanup
class Cache {
public:
    std::shared_ptr<CacheEntry> get(const std::string& key) {
        std::lock_guard lock(mutex_);

        auto it = entries_.find(key);
        if (it != entries_.end()) {
            // Try to promote weak_ptr to shared_ptr
            if (auto entry = it->second.lock()) {
                return entry; // Still alive
            }
            entries_.erase(it); // Expired
        }
        return nullptr;
    }

    void put(const std::string& key, std::shared_ptr<CacheEntry> entry) {
        std::lock_guard lock(mutex_);
        entries_[key] = entry; // Store as weak_ptr
    }

    void cleanup() {
        std::lock_guard lock(mutex_);
        std::erase_if(entries_, [](const auto& pair) {
            return pair.second.expired();
        });
    }

private:
    std::mutex mutex_;
    std::unordered_map<std::string, std::weak_ptr<CacheEntry>> entries_;
};

// Observer pattern with weak_ptr (prevents prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent  prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent  prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent prevent  circular references)
class EventEmitter;

class Observer : public std::enable_shared_from_this<Observer> {
public:
    explicit Observer(std::string name) : name_(std::move(name)) {}

    void on_event(const std::string& event) {
        std::cout << name_ << " received: " << event << "\\n";
    }

    const std::string& name() const { return name_; }

private:
    std::string name_;
};

class EventEmitter {
public:
    void subscribe(std::shared_ptr<Observer> observer) {
        observers_.push_back(observer); // Store as weak_ptr
    }

    void emit(const std::string& event) {
        // Clean up expired observers and notify active ones
        std::erase_if(observers_, [](const std::weak_ptr<Observer>& wp) {
            return wp.expired();
        });

        for (auto& weak_obs : observers_) {
            if (auto obs = weak_obs.lock()) {
                obs->on_event(event);
            }
        }
    }

private:
    std::vector<std::weak_ptr<Observer>> observers_;
};

// shared_ptr with custom allocator (arena/pool)
auto create_pooled() {
    // Custom deleter that returns to pool instead of deallocating
    auto pool_deleter = [](int* ptr) {
        // pool.deallocate(ptr);
        delete ptr; // Simplified
    };
    return std::shared_ptr<int>(new int(42), pool_deleter);
}
```

```cpp
// --- RAII patterns and scope guards ---

#include <functional>
#include <mutex>
#include <fstream>

// Scope guard: execute cleanup on scope exit
class ScopeGuard {
public:
    explicit ScopeGuard(std::function<void()> cleanup)
        : cleanup_(std::move(cleanup)), active_(true) {}

    ~ScopeGuard() {
        if (active_) cleanup_();
    }

    void dismiss() { active_ = false; } // Cancel cleanup

    ScopeGuard(ScopeGuard&& other) noexcept
        : cleanup_(std::move(other.cleanup_)), active_(other.active_) {
        other.active_ = false;
    }

    ScopeGuard(const ScopeGuard&) = delete;
    ScopeGuard& operator=(const ScopeGuard&) = delete;

private:
    std::function<void()> cleanup_;
    bool active_;
};

// Usage: transaction-like cleanup
void process_file(const std::string& input, const std::string& output) {
    std::ifstream in(input);
    std::ofstream out(output);

    // If we throw before commit, remove partial output
    ScopeGuard cleanup([&output]() {
        std::remove(output.c_str());
        std::cout << "Cleaned up partial output\\n";
    });

    // Process...
    std::string line;
    while (std::getline(in, line)) {
        out << line << "\\n";
    }

    cleanup.dismiss(); // Success — keep the output file
}

// RAII lock wrapper (std::lock_guard / std::unique_lock)
class ThreadSafeCounter {
public:
    void increment() {
        std::lock_guard lock(mutex_);  // RAII: auto-unlock on scope exit
        ++count_;
    }

    int get() const {
        std::lock_guard lock(mutex_);
        return count_;
    }

    // unique_lock for conditional locking
    bool try_increment() {
        std::unique_lock lock(mutex_, std::try_to_lock);
        if (lock.owns_lock()) {
            ++count_;
            return true;
        }
        return false;
    }

private:
    mutable std::mutex mutex_;
    int count_ = 0;
};

int main() {
    // unique_ptr
    auto conn = create_connection("postgres://localhost/mydb");
    auto repo = Repository(std::move(conn));
    repo.find_user(42);

    auto shapes = create_shapes();
    for (const auto& shape : shapes) {
        std::cout << shape->name() << ": " << shape->area() << "\\n";
    }

    // shared_ptr + weak_ptr
    auto emitter = EventEmitter();
    {
        auto obs1 = std::make_shared<Observer>("Logger");
        auto obs2 = std::make_shared<Observer>("Metrics");
        emitter.subscribe(obs1);
        emitter.subscribe(obs2);
        emitter.emit("user.login"); // Both receive
    }
    // obs1 and obs2 are destroyed here
    emitter.emit("user.logout"); // No one receives (weak_ptrs expired)

    return 0;
}
```

Smart pointer comparison:

| Type | Ownership | Overhead | Thread-Safe? | Use Case |
|------|----------|---------|-------------|----------|
| `unique_ptr<T>` | Exclusive | Zero (no refcount) | N/A (single owner) | Default choice, factories |
| `shared_ptr<T>` | Shared (refcounted) | Atomic refcount | Refcount only | Shared caches, observers |
| `weak_ptr<T>` | Non-owning observer | None (borrows shared) | Via `lock()` | Breaking cycles, caches |
| `T*` (raw) | Non-owning | None | N/A | Borrowed references only |
| `std::observer_ptr<T>` | Non-owning (explicit) | None | N/A | Documentation intent |
| Custom deleter | Any | Depends on deleter | Depends | C library wrappers, pools |

Key patterns:
1. Use `std::make_unique<T>(args)` as the default — it prevents memory leaks from exception-unsafe expressions
2. Transfer `unique_ptr` ownership with `std::move` — the source becomes null after the move
3. Use `weak_ptr` in observer/cache patterns to avoid preventing cleanup of watched objects
4. `enable_shared_from_this` lets an object safely create `shared_ptr` references to itself
5. Custom deleters wrap C APIs (FILE*, SSL_CTX*, etc.) in RAII for automatic cleanup
6. Prefer `unique_ptr` over `shared_ptr` unless you genuinely need shared ownership — it has zero overhead'''
    ),
]
