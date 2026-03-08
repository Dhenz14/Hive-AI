"""C++ deep reasoning pairs batch 5: error handling and type system."""
PAIRS = [
    ("cpp_deep/exception_safety_guarantees", r'''Explain the three exception safety guarantees in C++ (basic, strong, nothrow) and show a class that demonstrates all three levels in different member functions.''', r'''<think>
The three exception safety guarantees are fundamental to writing robust C++ code.
Basic guarantee: invariants preserved, no leaks, but state may change.
Strong guarantee: operation succeeds or state is unchanged (commit-or-rollback).
Nothrow guarantee: operation never throws — critical for destructors and swap.

I need a class that demonstrates all three clearly. A container-like class works well.
For basic: an insert that may leave the container in a valid but modified state.
For strong: a copy-and-swap assignment operator — classic strong guarantee pattern.
For nothrow: swap and destructor, marked noexcept.

I should show how strong guarantee often uses the copy-and-swap idiom.
The basic guarantee minimum is: no resource leaks and class invariants hold.
The nothrow guarantee is needed for swap to enable the strong guarantee in assignment.
This layering — nothrow swap enables strong assignment — is a key design insight.

I will use a simple dynamic array wrapper to keep the example focused.
Each method will be commented with which guarantee it provides and why.
The strong guarantee method will use a temporary to achieve rollback semantics.
</think>

Here is a class demonstrating all three exception safety guarantee levels:

```cpp
#include <algorithm>
#include <cstddef>
#include <iostream>
#include <stdexcept>
#include <utility>

class SafeBuffer {
    int* data_;
    std::size_t size_;
    std::size_t capacity_;

public:
    explicit SafeBuffer(std::size_t cap = 4)
        : data_(new int[cap]), size_(0), capacity_(cap) {}

    ~SafeBuffer() noexcept {           // nothrow guarantee — destructors must never throw
        delete[] data_;
    }

    // --- Nothrow guarantee: swap never throws ---
    void swap(SafeBuffer& other) noexcept {
        std::swap(data_, other.data_);
        std::swap(size_, other.size_);
        std::swap(capacity_, other.capacity_);
    }

    // --- Strong guarantee: copy-and-swap idiom ---
    // If copy construction throws, 'this' is untouched (rollback).
    // The noexcept swap then commits atomically.
    SafeBuffer(const SafeBuffer& other)
        : data_(new int[other.capacity_]), size_(other.size_), capacity_(other.capacity_)
    {
        std::copy(other.data_, other.data_ + other.size_, data_);
    }

    SafeBuffer& operator=(SafeBuffer other) {   // pass by value = copy
        swap(other);                              // noexcept commit
        return *this;                             // old data destroyed in 'other'
    }

    // --- Basic guarantee: push_back ---
    // If reallocation throws, the buffer is still valid but may have new capacity.
    // Invariant (size_ <= capacity_) always holds; no memory is leaked.
    void push_back(int value) {
        if (size_ == capacity_) {
            std::size_t new_cap = capacity_ * 2;
            int* new_data = new int[new_cap];       // may throw — nothing modified yet
            std::copy(data_, data_ + size_, new_data);
            delete[] data_;
            data_ = new_data;
            capacity_ = new_cap;
        }
        data_[size_++] = value;    // nothrow for int
    }

    // --- Strong guarantee: insert at position ---
    // Uses a temporary buffer so failure leaves *this unchanged.
    void insert_at(std::size_t pos, int value) {
        if (pos > size_) throw std::out_of_range("insert_at: pos > size");

        SafeBuffer tmp(capacity_ < size_ + 1 ? capacity_ * 2 : capacity_);
        for (std::size_t i = 0; i < pos; ++i)
            tmp.push_back(data_[i]);
        tmp.push_back(value);
        for (std::size_t i = pos; i < size_; ++i)
            tmp.push_back(data_[i]);

        swap(tmp);   // noexcept commit — strong guarantee achieved
    }

    // --- Nothrow guarantee: element access (bounds-checked variant throws though) ---
    int operator[](std::size_t i) const noexcept { return data_[i]; }

    int at(std::size_t i) const {
        if (i >= size_) throw std::out_of_range("at: index out of range");
        return data_[i];
    }

    std::size_t size() const noexcept { return size_; }
};

int main() {
    SafeBuffer buf;
    buf.push_back(10);        // basic guarantee
    buf.push_back(20);
    buf.push_back(30);

    buf.insert_at(1, 15);     // strong guarantee

    SafeBuffer buf2;
    buf2 = buf;                // strong guarantee (copy-and-swap)

    for (std::size_t i = 0; i < buf2.size(); ++i)
        std::cout << buf2[i] << " ";    // nothrow access
    std::cout << "\n";

    try {
        buf2.at(100);          // throws out_of_range
    } catch (const std::out_of_range& e) {
        std::cout << "Caught: " << e.what() << "\n";
    }
    return 0;
}
```

**Summary of guarantees:**
- **Nothrow**: `swap()`, `operator[]`, destructor — marked `noexcept`, never throw.
- **Strong**: `operator=` (copy-and-swap), `insert_at` (work on temp, swap to commit).
- **Basic**: `push_back` — invariants preserved and no leaks, but internal state (capacity) may change on failure during copy phase if elements had throwing copy constructors.'''),

    ("cpp_deep/noexcept_optimization_impact", r'''How does the noexcept specifier impact optimization in C++? Show concrete examples where adding or removing noexcept changes code generation or behavior, especially with standard containers.''', r'''<think>
noexcept has real impact beyond documentation. The key areas are:
1. std::vector reallocation: uses move if move ctor is noexcept, else copies (strong guarantee).
2. Compiler can skip stack unwinding machinery for noexcept functions.
3. std::move_if_noexcept chooses move vs copy based on noexcept.
4. noexcept is part of the type system since C++17.

The most dramatic example is vector::push_back. If the element type's move
constructor is not noexcept, vector falls back to copying to maintain the
strong exception guarantee during reallocation. This can be orders of magnitude slower.

I should show two classes — one with noexcept move, one without — and demonstrate
the behavioral difference with vector. I can also show the compiler optimization
angle: noexcept lets the compiler omit the unwind tables for that function.

I will also demonstrate std::move_if_noexcept explicitly.
conditional noexcept (noexcept(expr)) is worth showing for generic code.
The is_nothrow_move_constructible type trait is the detection mechanism.
</think>

The `noexcept` specifier has concrete performance and behavioral consequences:

```cpp
#include <iostream>
#include <type_traits>
#include <utility>
#include <vector>

// --- Example 1: vector reallocation behavior ---

struct LoudMove {
    int id;
    LoudMove(int i) : id(i) {}
    LoudMove(const LoudMove& o) : id(o.id) {
        std::cout << "  COPY " << id << "\n";
    }
    // Move is NOT noexcept — vector will prefer copy for strong guarantee
    LoudMove(LoudMove&& o) : id(o.id) {
        std::cout << "  MOVE " << id << "\n";
        o.id = -1;
    }
};

struct QuietMove {
    int id;
    QuietMove(int i) : id(i) {}
    QuietMove(const QuietMove& o) : id(o.id) {
        std::cout << "  COPY " << id << "\n";
    }
    // Move IS noexcept — vector will use move during reallocation
    QuietMove(QuietMove&& o) noexcept : id(o.id) {
        std::cout << "  MOVE " << id << "\n";
        o.id = -1;
    }
};

// --- Example 2: move_if_noexcept ---

struct Widget {
    Widget() = default;
    Widget(const Widget&) { std::cout << "  Widget copied\n"; }
    Widget(Widget&&) noexcept { std::cout << "  Widget moved\n"; }
};

struct Gadget {
    Gadget() = default;
    Gadget(const Gadget&) { std::cout << "  Gadget copied\n"; }
    Gadget(Gadget&&) { std::cout << "  Gadget moved\n"; }  // NOT noexcept
};

// --- Example 3: conditional noexcept for generic code ---

template <typename T>
class Wrapper {
    T value_;
public:
    explicit Wrapper(T val) noexcept(std::is_nothrow_move_constructible_v<T>)
        : value_(std::move(val)) {}

    void swap(Wrapper& other) noexcept(std::is_nothrow_move_constructible_v<T>
                                    && std::is_nothrow_move_assignable_v<T>) {
        using std::swap;
        swap(value_, other.value_);
    }

    const T& get() const noexcept { return value_; }
};

int main() {
    // Example 1: vector reallocation
    std::cout << "=== LoudMove (move NOT noexcept) ===\n";
    {
        std::vector<LoudMove> v;
        v.reserve(2);
        v.emplace_back(1);
        v.emplace_back(2);
        std::cout << "Triggering reallocation:\n";
        v.emplace_back(3);  // Reallocation: existing elements are COPIED, not moved
    }

    std::cout << "\n=== QuietMove (move IS noexcept) ===\n";
    {
        std::vector<QuietMove> v;
        v.reserve(2);
        v.emplace_back(1);
        v.emplace_back(2);
        std::cout << "Triggering reallocation:\n";
        v.emplace_back(3);  // Reallocation: existing elements are MOVED
    }

    // Example 2: move_if_noexcept
    std::cout << "\n=== std::move_if_noexcept ===\n";
    Widget w;
    auto w2 = std::move_if_noexcept(w);   // moves — noexcept move exists

    Gadget g;
    auto g2 = std::move_if_noexcept(g);   // copies — move is not noexcept

    // Example 3: type traits detection
    std::cout << "\n=== Type traits ===\n";
    std::cout << "LoudMove nothrow_move: "
              << std::is_nothrow_move_constructible_v<LoudMove> << "\n";   // 0
    std::cout << "QuietMove nothrow_move: "
              << std::is_nothrow_move_constructible_v<QuietMove> << "\n";  // 1
    std::cout << "Wrapper<int> noexcept swap: "
              << noexcept(std::declval<Wrapper<int>&>().swap(
                          std::declval<Wrapper<int>&>())) << "\n";         // 1

    return 0;
}
```

**Key takeaways:**
- `std::vector` copies instead of moving during reallocation when move is not `noexcept` — this preserves the strong exception guarantee but costs performance.
- `std::move_if_noexcept` returns an rvalue reference only if the move constructor is `noexcept`, otherwise returns a const lvalue reference (triggering copy).
- Conditional `noexcept(expr)` propagates the noexcept status in generic code.
- The compiler can omit stack-unwinding code for `noexcept` functions; if an exception escapes, `std::terminate()` is called immediately.'''),

    ("cpp_deep/exception_vs_error_code", r'''When should I use exceptions versus error codes in C++? Provide a practical design that uses both appropriately in a file I/O library.''', r'''<think>
This is a design question with well-established guidance. The key considerations:
- Exceptions: for truly exceptional, unrecoverable-at-call-site conditions.
- Error codes: for expected failures that callers should handle locally.
- Performance: exceptions have zero cost on the happy path but heavy throw cost.
  Error codes add a branch on every call but no surprise costs.
- APIs: constructor failures must use exceptions (no return value).
  Operators and callbacks often cannot propagate error codes easily.

For a file I/O library, the natural split is:
- Exceptions: opening a file that must exist (programmer error / config error).
- Error codes: trying to open a file that might not exist (expected failure).
- Offer dual APIs: open() throws, try_open() returns error code.

I should also show std::error_code integration for system-level errors.
The dual-API pattern (like std::filesystem) is the modern C++ idiom.
This gives callers the choice: exception-based for simple code, error-code for hot paths.
I will keep the example realistic but focused — a FileReader with both interfaces.
</think>

Here is a file I/O library design that uses both exceptions and error codes in the right places:

```cpp
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#include <system_error>
#include <vector>

// --- Error category for our library ---
enum class FileErr {
    ok = 0,
    not_found,
    permission_denied,
    read_error,
    already_open
};

struct FileErrCategory : std::error_category {
    const char* name() const noexcept override { return "FileIO"; }
    std::string message(int ev) const override {
        switch (static_cast<FileErr>(ev)) {
            case FileErr::ok:                return "success";
            case FileErr::not_found:         return "file not found";
            case FileErr::permission_denied: return "permission denied";
            case FileErr::read_error:        return "read error";
            case FileErr::already_open:      return "file already open";
            default:                         return "unknown error";
        }
    }
};

const FileErrCategory& file_err_category() {
    static FileErrCategory instance;
    return instance;
}

std::error_code make_error_code(FileErr e) {
    return {static_cast<int>(e), file_err_category()};
}

namespace std {
    template<> struct is_error_code_enum<FileErr> : true_type {};
}

// --- File I/O class with dual API ---
class FileReader {
    FILE* fp_ = nullptr;
    std::string path_;

    static FileErr errno_to_file_err() {
        switch (errno) {
            case ENOENT: return FileErr::not_found;
            case EACCES: return FileErr::permission_denied;
            default:     return FileErr::read_error;
        }
    }

public:
    // EXCEPTION API: Use when file MUST exist (config, required data).
    // Constructor failure can only be signaled via exceptions.
    explicit FileReader(const std::string& path) : path_(path) {
        fp_ = std::fopen(path.c_str(), "rb");
        if (!fp_) {
            throw std::system_error(make_error_code(errno_to_file_err()),
                                    "failed to open: " + path);
        }
    }

    // ERROR CODE API: Use when file might not exist (optional config, probing).
    FileReader() = default;

    std::error_code try_open(const std::string& path) {
        if (fp_) return make_error_code(FileErr::already_open);
        fp_ = std::fopen(path.c_str(), "rb");
        if (!fp_) return make_error_code(errno_to_file_err());
        path_ = path;
        return {};   // success
    }

    // Dual read API — both forms available
    std::vector<char> read_all() {
        std::error_code ec;
        auto result = try_read_all(ec);
        if (ec) throw std::system_error(ec, "read_all failed on: " + path_);
        return result;
    }

    std::vector<char> try_read_all(std::error_code& ec) {
        ec.clear();
        if (!fp_) { ec = make_error_code(FileErr::read_error); return {}; }

        std::fseek(fp_, 0, SEEK_END);
        long sz = std::ftell(fp_);
        std::fseek(fp_, 0, SEEK_SET);

        std::vector<char> buf(static_cast<std::size_t>(sz));
        if (std::fread(buf.data(), 1, buf.size(), fp_) != buf.size()) {
            ec = make_error_code(FileErr::read_error);
            return {};
        }
        return buf;
    }

    bool is_open() const noexcept { return fp_ != nullptr; }

    ~FileReader() noexcept {   // destructors never throw
        if (fp_) std::fclose(fp_);
    }

    FileReader(const FileReader&) = delete;
    FileReader& operator=(const FileReader&) = delete;
};

int main() {
    // --- Exception API: required file ---
    try {
        FileReader config("/etc/hostname");   // must exist
        auto data = config.read_all();
        std::cout << "Read " << data.size() << " bytes\n";
    } catch (const std::system_error& e) {
        std::cerr << "Fatal: " << e.what() << " [" << e.code() << "]\n";
        return 1;
    }

    // --- Error code API: optional file ---
    FileReader optional_file;
    std::error_code ec = optional_file.try_open("/tmp/maybe_exists.txt");
    if (ec) {
        std::cout << "Optional file not available: " << ec.message() << "\n";
        // Not fatal — continue with defaults
    } else {
        auto data = optional_file.try_read_all(ec);
        if (!ec) std::cout << "Optional data: " << data.size() << " bytes\n";
    }

    return 0;
}
```

**Guidelines:**
| Use exceptions when | Use error codes when |
|---|---|
| Failure is truly unexpected | Failure is a normal outcome |
| Constructors (no return value) | Hot loops / performance-critical paths |
| Deep call stacks (avoids manual propagation) | Caller will handle immediately |
| Library boundaries (clear contract) | C interop or embedded contexts |

The dual-API pattern (like `std::filesystem::exists()` vs `exists(ec)`) gives callers the choice.'''),

    ("cpp_deep/std_expected_c23", r'''Show how std::expected from C++23 works as an error-as-value type. Demonstrate creating, chaining, and propagating errors without exceptions.''', r'''<think>
std::expected<T, E> is C++23's error-as-value type — like Rust's Result<T, E>.
It holds either a value of type T or an error of type E.
Key operations: value(), error(), has_value(), operator bool.
C++23 added monadic operations: transform, and_then, or_else, transform_error.

I need to show:
1. Basic creation and checking.
2. Returning expected from functions instead of throwing.
3. Chaining with and_then (flatmap) and transform (map).
4. Error propagation without exceptions.

I should create a realistic pipeline — parsing, validating, computing.
Each step returns expected, and they chain together cleanly.
The and_then operation takes a function returning expected (flatmap).
The transform operation takes a function returning a plain value (map).
or_else handles the error case for recovery.

I will use a string-to-config parsing pipeline as the example.
This clearly shows how errors propagate without try/catch.
</think>

`std::expected<T, E>` (C++23) is C++'s answer to Rust's `Result<T, E>`:

```cpp
#include <charconv>
#include <expected>
#include <iostream>
#include <string>
#include <string_view>
#include <system_error>

// --- Error type ---
enum class ParseError {
    empty_input,
    bad_format,
    out_of_range,
    negative_not_allowed
};

std::string_view to_string(ParseError e) {
    switch (e) {
        case ParseError::empty_input:         return "empty input";
        case ParseError::bad_format:          return "bad format";
        case ParseError::out_of_range:        return "out of range";
        case ParseError::negative_not_allowed: return "negative not allowed";
    }
    return "unknown";
}

// --- Functions returning std::expected instead of throwing ---

std::expected<int, ParseError> parse_int(std::string_view sv) {
    if (sv.empty())
        return std::unexpected(ParseError::empty_input);

    int result{};
    auto [ptr, ec] = std::from_chars(sv.data(), sv.data() + sv.size(), result);

    if (ec == std::errc::result_out_of_range)
        return std::unexpected(ParseError::out_of_range);
    if (ec != std::errc{} || ptr != sv.data() + sv.size())
        return std::unexpected(ParseError::bad_format);

    return result;
}

std::expected<int, ParseError> validate_positive(int value) {
    if (value < 0)
        return std::unexpected(ParseError::negative_not_allowed);
    return value;
}

struct Config {
    int port;
    int max_connections;
};

// --- Chaining with monadic operations ---

std::expected<Config, ParseError> parse_config(std::string_view port_str,
                                                std::string_view conn_str) {
    // and_then: chains functions that return expected (flatMap)
    auto port = parse_int(port_str)
        .and_then(validate_positive);

    if (!port)
        return std::unexpected(port.error());

    auto conns = parse_int(conn_str)
        .and_then(validate_positive)
        .transform([](int n) { return std::min(n, 1000); });  // cap at 1000

    if (!conns)
        return std::unexpected(conns.error());

    return Config{port.value(), conns.value()};
}

// --- Demonstration of all monadic operations ---

void demo_monadic() {
    std::cout << "=== Monadic operations ===\n";

    auto result = parse_int("42")
        .transform([](int n) { return n * 2; })           // map: 42 -> 84
        .and_then(validate_positive)                        // flatmap: check positive
        .transform([](int n) { return std::to_string(n); }) // map: 84 -> "84"
        .or_else([](ParseError) -> std::expected<std::string, ParseError> {
            return "default";   // recover from error
        });

    std::cout << "Result: " << result.value() << "\n";  // "84"

    // Error propagation — no exceptions, no if-chains
    auto bad = parse_int("xyz")
        .transform([](int n) { return n * 2; })     // skipped — already error
        .and_then(validate_positive)                  // skipped
        .or_else([](ParseError e) -> std::expected<int, ParseError> {
            std::cout << "Recovered from: " << to_string(e) << "\n";
            return 0;   // provide fallback
        });

    std::cout << "Recovered: " << bad.value() << "\n";  // 0
}

int main() {
    // --- Basic usage ---
    auto good = parse_int("8080");
    auto bad  = parse_int("not_a_number");

    if (good) std::cout << "Parsed: " << good.value() << "\n";
    if (!bad) std::cout << "Error: " << to_string(bad.error()) << "\n";

    // --- Config parsing pipeline ---
    auto cfg = parse_config("8080", "256");
    if (cfg) {
        std::cout << "Port: " << cfg->port
                  << ", Max connections: " << cfg->max_connections << "\n";
    }

    auto bad_cfg = parse_config("8080", "-5");
    if (!bad_cfg) {
        std::cout << "Config error: " << to_string(bad_cfg.error()) << "\n";
    }

    // --- Monadic demo ---
    demo_monadic();

    return 0;
}
```

**Key `std::expected` operations:**
- `value()` / `error()` — access the held value or error.
- `transform(f)` — applies `f` to the value (like `map`); propagates error unchanged.
- `and_then(f)` — applies `f` that itself returns `expected` (like `flatMap`); propagates error.
- `or_else(f)` — handles the error case for recovery or transformation.
- `transform_error(f)` — transforms the error type without touching the value.'''),

    ("cpp_deep/optional_monadic_ops", r'''Demonstrate std::optional's monadic operations (transform, and_then, or_else) from C++23 with a practical example showing how they eliminate nested if-checks.''', r'''<think>
C++23 added monadic operations to std::optional, matching the functional style.
Before C++23, chaining optional operations required nested if-checks or manual unwrapping.
The three operations are:
- transform(f): applies f to the contained value, wraps result in optional. Like map.
- and_then(f): f returns optional itself, flattens. Like flatMap/bind.
- or_else(f): called when empty, f returns optional for recovery.

A practical example: user lookup -> get email -> parse domain -> validate domain.
Each step can fail (return nullopt), and the chain should short-circuit.
I will show the before (nested ifs) and after (monadic chain) to highlight the improvement.

The key insight: and_then is for functions that return optional<U>,
transform is for functions that return U directly.
or_else is for providing fallback values or logging on empty.
</think>

C++23 added `transform`, `and_then`, and `or_else` to `std::optional`, enabling clean functional chaining:

```cpp
#include <cctype>
#include <iostream>
#include <optional>
#include <string>
#include <unordered_map>

// --- Simulated data layer ---
struct User {
    std::string name;
    std::optional<std::string> email;   // email might not be set
};

std::unordered_map<int, User> db = {
    {1, {"Alice", "alice@example.com"}},
    {2, {"Bob", std::nullopt}},           // no email
    {3, {"Charlie", "charlie@corp.io"}},
};

// --- Functions that may fail (return optional) ---

std::optional<User> find_user(int id) {
    auto it = db.find(id);
    if (it == db.end()) return std::nullopt;
    return it->second;
}

std::optional<std::string> get_email(const User& u) {
    return u.email;   // already optional
}

// Plain function — always succeeds (for transform)
std::string extract_domain(const std::string& email) {
    auto pos = email.find('@');
    return (pos != std::string::npos) ? email.substr(pos + 1) : "";
}

// Returns optional — can fail (for and_then)
std::optional<std::string> validate_domain(const std::string& domain) {
    if (domain.empty() || domain.find('.') == std::string::npos)
        return std::nullopt;
    return domain;
}

// ============================================================
// BEFORE C++23: nested if-checks
// ============================================================
std::optional<std::string> get_valid_domain_old(int user_id) {
    auto user = find_user(user_id);
    if (!user) return std::nullopt;

    auto email = get_email(*user);
    if (!email) return std::nullopt;

    std::string domain = extract_domain(*email);

    auto valid = validate_domain(domain);
    if (!valid) return std::nullopt;

    return valid;
}

// ============================================================
// AFTER C++23: monadic chaining
// ============================================================
std::optional<std::string> get_valid_domain_new(int user_id) {
    return find_user(user_id)              // optional<User>
        .and_then(get_email)               // optional<string>  — get_email returns optional
        .transform(extract_domain)         // optional<string>  — extract_domain returns string
        .and_then(validate_domain);        // optional<string>  — validate_domain returns optional
}

int main() {
    // Test both implementations — same results, different style
    for (int id : {1, 2, 3, 99}) {
        auto domain = get_valid_domain_new(id);

        std::cout << "User " << id << ": ";
        if (domain) {
            std::cout << *domain << "\n";
        } else {
            // or_else for side effects / logging
            auto fallback = get_valid_domain_new(id)
                .or_else([]() -> std::optional<std::string> {
                    std::cout << "(unavailable, using fallback) ";
                    return "default.com";
                });
            std::cout << *fallback << "\n";
        }
    }

    // Chaining with transform for data transformation
    auto upper_domain = find_user(1)
        .and_then(get_email)
        .transform(extract_domain)
        .and_then(validate_domain)
        .transform([](std::string d) {
            for (auto& c : d) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
            return d;
        });

    std::cout << "Uppercase domain: " << upper_domain.value_or("N/A") << "\n";

    return 0;
}
```

**Cheat sheet:**
| Operation | Input function signature | When called |
|---|---|---|
| `transform(f)` | `f(T) -> U` | Has value: wraps `f(val)` in `optional<U>` |
| `and_then(f)` | `f(T) -> optional<U>` | Has value: returns `f(val)` directly (flattens) |
| `or_else(f)` | `f() -> optional<T>` | Empty: returns `f()` for recovery |'''),

    ("cpp_deep/variant_visit_sum_types", r'''Show how to use std::variant with std::visit to implement sum types in C++17, including the overloaded lambda pattern for exhaustive matching.''', r'''<think>
std::variant is C++17's type-safe union — a sum type / tagged union.
std::visit applies a visitor to the active alternative.
The overloaded pattern uses a struct inheriting from multiple lambdas for exhaustive matching.

I should show:
1. Basic variant creation and visitation.
2. The overloaded helper (standard idiom).
3. Exhaustive matching — compile error if a case is missing.
4. A practical example: an AST node or shape hierarchy as a variant.
5. Returning values from visit.

The overloaded pattern: template struct overloaded : Ts... { using Ts::operator()...; };
With C++20 CTAD fix it doesn't need the deduction guide.
In C++17 you need the explicit deduction guide.

I'll use a simple expression evaluator as the practical example.
</think>

`std::variant` + `std::visit` gives you algebraic sum types with exhaustive pattern matching:

```cpp
#include <cmath>
#include <iostream>
#include <string>
#include <variant>
#include <vector>

// --- The overloaded pattern (C++17 idiom) ---
template <class... Ts>
struct overloaded : Ts... { using Ts::operator()...; };
// C++17 deduction guide (not needed in C++20)
template <class... Ts>
overloaded(Ts...) -> overloaded<Ts...>;

// --- Sum type: Shape ---
struct Circle    { double radius; };
struct Rectangle { double width, height; };
struct Triangle  { double base, height; };

using Shape = std::variant<Circle, Rectangle, Triangle>;

// Visit returns a value — exhaustive matching
double area(const Shape& s) {
    return std::visit(overloaded{
        [](const Circle& c)    { return M_PI * c.radius * c.radius; },
        [](const Rectangle& r) { return r.width * r.height; },
        [](const Triangle& t)  { return 0.5 * t.base * t.height; }
        // Removing any case here causes a compile error — exhaustive!
    }, s);
}

std::string describe(const Shape& s) {
    return std::visit(overloaded{
        [](const Circle& c)    { return "Circle(r=" + std::to_string(c.radius) + ")"; },
        [](const Rectangle& r) { return "Rect(" + std::to_string(r.width) + "x"
                                                 + std::to_string(r.height) + ")"; },
        [](const Triangle& t)  { return "Tri(b=" + std::to_string(t.base) + ")"; }
    }, s);
}

// --- Sum type: Expression AST ---
struct Literal;
struct Add;
struct Multiply;

using Expr = std::variant<Literal, Add, Multiply>;

struct Literal  { double value; };
struct Add      { std::vector<Expr> operands; };
struct Multiply { std::vector<Expr> operands; };

double evaluate(const Expr& expr) {
    return std::visit(overloaded{
        [](const Literal& lit) {
            return lit.value;
        },
        [](const Add& add) {
            double sum = 0;
            for (const auto& op : add.operands) sum += evaluate(op);
            return sum;
        },
        [](const Multiply& mul) {
            double product = 1;
            for (const auto& op : mul.operands) product *= evaluate(op);
            return product;
        }
    }, expr);
}

// --- Visiting multiple variants simultaneously ---
using Operand = std::variant<int, double, std::string>;

void print_binary_op(const Operand& lhs, const Operand& rhs) {
    std::visit(overloaded{
        [](int a, int b)                          { std::cout << a << " + " << b << " = " << a + b << "\n"; },
        [](double a, double b)                     { std::cout << a << " + " << b << " = " << a + b << "\n"; },
        [](const std::string& a, const std::string& b) { std::cout << "\"" << a + b << "\"\n"; },
        [](const auto& a, const auto& b)           { std::cout << "(incompatible types)\n"; }
    }, lhs, rhs);
}

int main() {
    // --- Shapes ---
    std::vector<Shape> shapes = {
        Circle{5.0},
        Rectangle{3.0, 4.0},
        Triangle{6.0, 3.0}
    };

    for (const auto& s : shapes) {
        std::cout << describe(s) << " -> area = " << area(s) << "\n";
    }

    // --- Expression AST ---
    // (2 + 3) * 4
    Expr expr = Multiply{{
        Add{{ Literal{2.0}, Literal{3.0} }},
        Literal{4.0}
    }};
    std::cout << "\n(2 + 3) * 4 = " << evaluate(expr) << "\n";

    // --- Multi-variant visit ---
    std::cout << "\n=== Multi-variant visit ===\n";
    print_binary_op(3, 4);
    print_binary_op(std::string("hello"), std::string(" world"));
    print_binary_op(3, std::string("oops"));

    // --- Index and holds_alternative ---
    Shape s = Circle{1.0};
    std::cout << "\nIndex: " << s.index() << "\n";               // 0
    std::cout << "Is circle: " << std::holds_alternative<Circle>(s) << "\n";  // 1

    return 0;
}
```

**Key points:**
- `overloaded{lambdas...}` gives exhaustive matching — missing a case is a compile error.
- `std::visit` can match on **multiple** variants simultaneously (multi-visit).
- `std::get<T>(v)` throws `std::bad_variant_access` if wrong type; `std::get_if<T>(&v)` returns `nullptr`.
- Variant is value-typed — no heap allocation, no virtual dispatch overhead.'''),

    ("cpp_deep/pattern_matching_variant", r'''Show advanced pattern matching simulation in C++ using variant and visit, including recursive variants, guards, and multi-dispatch patterns.''', r'''<think>
This builds on variant + visit but goes deeper into pattern matching techniques.
Key topics:
1. Recursive variants (need a wrapper type since variant can't contain itself).
2. Guard-like conditions within visitors.
3. Multi-dispatch (visiting two variants simultaneously).
4. Wildcard / default handling with auto.

For recursive variants, the standard approach is using a unique_ptr or a
box wrapper since std::variant needs complete types at definition.
I'll use a JSON-like value type as the example — it naturally requires recursion.

Guards can be simulated with if/else inside lambda bodies.
Multi-dispatch: visit with two variant arguments.
</think>

Advanced pattern matching in C++ using `std::variant` and `std::visit`, including recursive types:

```cpp
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <variant>
#include <vector>

template <class... Ts>
struct overloaded : Ts... { using Ts::operator()...; };
template <class... Ts>
overloaded(Ts...) -> overloaded<Ts...>;

// --- Recursive variant via Box wrapper ---
template <typename T>
struct Box {
    std::unique_ptr<T> ptr;
    Box(T val) : ptr(std::make_unique<T>(std::move(val))) {}
    Box(const Box& o) : ptr(std::make_unique<T>(*o.ptr)) {}
    Box(Box&&) noexcept = default;
    Box& operator=(Box&&) noexcept = default;
    Box& operator=(const Box& o) { ptr = std::make_unique<T>(*o.ptr); return *this; }
    T& operator*() { return *ptr; }
    const T& operator*() const { return *ptr; }
    T* operator->() { return ptr.get(); }
    const T* operator->() const { return ptr.get(); }
};

// --- JSON-like recursive value type ---
struct JsonNull {};

using JsonValue = std::variant<
    JsonNull,
    bool,
    double,
    std::string,
    Box<std::vector<struct Json>>,    // array (recursive)
    Box<std::map<std::string, struct Json>>  // object (recursive)
>;

struct Json {
    JsonValue val;

    // Convenience constructors
    Json() : val(JsonNull{}) {}
    Json(bool b) : val(b) {}
    Json(double d) : val(d) {}
    Json(const char* s) : val(std::string(s)) {}
    Json(std::string s) : val(std::move(s)) {}
    Json(std::vector<Json> arr) : val(Box<std::vector<Json>>(std::move(arr))) {}
    Json(std::map<std::string, Json> obj) : val(Box<std::map<std::string, Json>>(std::move(obj))) {}
};

// --- Pattern matching with guards ---
std::string stringify(const Json& j, int indent = 0) {
    std::string pad(indent, ' ');
    return std::visit(overloaded{
        [&](JsonNull) -> std::string {
            return "null";
        },
        [&](bool b) -> std::string {
            return b ? "true" : "false";
        },
        [&](double d) -> std::string {
            // Guard: integer-valued doubles print without decimal
            if (d == static_cast<int>(d))
                return std::to_string(static_cast<int>(d));
            return std::to_string(d);
        },
        [&](const std::string& s) -> std::string {
            return "\"" + s + "\"";
        },
        [&](const Box<std::vector<Json>>& arr) -> std::string {
            // Guard: empty array
            if (arr->empty()) return "[]";
            std::string out = "[\n";
            for (std::size_t i = 0; i < arr->size(); ++i) {
                out += pad + "  " + stringify((*arr)[i], indent + 2);
                if (i + 1 < arr->size()) out += ",";
                out += "\n";
            }
            return out + pad + "]";
        },
        [&](const Box<std::map<std::string, Json>>& obj) -> std::string {
            if (obj->empty()) return "{}";
            std::string out = "{\n";
            std::size_t i = 0;
            for (const auto& [k, v] : **obj) {
                out += pad + "  \"" + k + "\": " + stringify(v, indent + 2);
                if (++i < obj->size()) out += ",";
                out += "\n";
            }
            return out + pad + "}";
        }
    }, j.val);
}

// --- Multi-dispatch: comparing two Json values ---
bool json_equal(const Json& a, const Json& b) {
    // Visit both variants simultaneously — all NxN combinations
    return std::visit(overloaded{
        // Same-type matches
        [](JsonNull, JsonNull)                     { return true; },
        [](bool x, bool y)                         { return x == y; },
        [](double x, double y)                     { return x == y; },
        [](const std::string& x, const std::string& y) { return x == y; },
        [](const Box<std::vector<Json>>& a, const Box<std::vector<Json>>& b) {
            if (a->size() != b->size()) return false;
            for (std::size_t i = 0; i < a->size(); ++i)
                if (!json_equal((*a)[i], (*b)[i])) return false;
            return true;
        },
        [](const Box<std::map<std::string, Json>>& a,
           const Box<std::map<std::string, Json>>& b) {
            if (a->size() != b->size()) return false;
            for (const auto& [k, v] : **a) {
                auto it = b->find(k);
                if (it == b->end() || !json_equal(v, it->second)) return false;
            }
            return true;
        },
        // Wildcard: different types are never equal
        [](const auto&, const auto&) { return false; }
    }, a.val, b.val);
}

int main() {
    // Build a JSON structure
    Json config = Json(std::map<std::string, Json>{
        {"name", "HiveAI"},
        {"version", 2.0},
        {"features", Json(std::vector<Json>{"lora", "skills", "eval"})},
        {"debug", false},
        {"metadata", Json()}  // null
    });

    std::cout << stringify(config) << "\n";

    // Multi-dispatch equality
    Json a = Json(std::vector<Json>{1.0, "two", true});
    Json b = Json(std::vector<Json>{1.0, "two", true});
    Json c = Json(std::vector<Json>{1.0, "two", false});

    std::cout << "a == b: " << json_equal(a, b) << "\n";   // 1
    std::cout << "a == c: " << json_equal(a, c) << "\n";   // 0
    std::cout << "1.0 == \"1\": " << json_equal(Json(1.0), Json("1")) << "\n"; // 0

    return 0;
}
```

**Pattern matching techniques demonstrated:**
- **Recursive variant** via `Box<T>` wrapper (heap-allocated to break size dependency).
- **Guards**: if/else within visitor lambdas for sub-case discrimination.
- **Multi-dispatch**: `std::visit(visitor, v1, v2)` matches all type combinations.
- **Wildcard**: `[](const auto&, const auto&)` catches unmatched combinations.'''),

    ("cpp_deep/std_any_type_erased_storage", r'''Explain std::any and demonstrate when it's appropriate to use instead of std::variant. Show practical usage for plugin systems or configuration stores.''', r'''<think>
std::any is a type-safe container for single values of any type.
Unlike variant, you don't need to enumerate the types upfront.
Use cases: plugin systems, config stores, message passing where types are open-ended.
Downsides: heap allocation (for large types), no compile-time exhaustiveness, runtime type checking.

Variant vs any:
- Variant: closed set of types, exhaustive matching, no heap allocation, compile-time safety.
- Any: open set, runtime type checking only, heap allocation for large types.

I should show a practical config store and a plugin system.
any_cast is the access mechanism — throws bad_any_cast on type mismatch.
</think>

`std::any` holds any copyable type without knowing the type set at compile time:

```cpp
#include <any>
#include <functional>
#include <iostream>
#include <string>
#include <typeinfo>
#include <unordered_map>
#include <vector>

// --- Use case 1: Configuration store (open type set) ---
class ConfigStore {
    std::unordered_map<std::string, std::any> values_;

public:
    template <typename T>
    void set(const std::string& key, T value) {
        values_[key] = std::move(value);
    }

    template <typename T>
    T get(const std::string& key) const {
        auto it = values_.find(key);
        if (it == values_.end())
            throw std::runtime_error("Key not found: " + key);
        return std::any_cast<T>(it->second);  // throws bad_any_cast on wrong type
    }

    template <typename T>
    T get_or(const std::string& key, T fallback) const noexcept {
        auto it = values_.find(key);
        if (it == values_.end()) return fallback;
        auto* ptr = std::any_cast<T>(&it->second);  // pointer version: returns nullptr
        return ptr ? *ptr : fallback;
    }

    bool has(const std::string& key) const {
        return values_.count(key) > 0;
    }

    const std::type_info& type_of(const std::string& key) const {
        return values_.at(key).type();
    }
};

// --- Use case 2: Plugin system with type-erased hooks ---
using HookFn = std::function<std::any(const std::any&)>;

class PluginHost {
    std::unordered_map<std::string, std::vector<HookFn>> hooks_;

public:
    void register_hook(const std::string& event, HookFn fn) {
        hooks_[event].push_back(std::move(fn));
    }

    std::vector<std::any> fire(const std::string& event, const std::any& arg) {
        std::vector<std::any> results;
        auto it = hooks_.find(event);
        if (it != hooks_.end()) {
            for (auto& fn : it->second) {
                results.push_back(fn(arg));
            }
        }
        return results;
    }
};

// --- Use case 3: Heterogeneous message queue ---
class MessageQueue {
    std::vector<std::pair<std::string, std::any>> messages_;

public:
    template <typename T>
    void push(std::string type, T payload) {
        messages_.emplace_back(std::move(type), std::move(payload));
    }

    template <typename T>
    bool try_pop(const std::string& type, T& out) {
        for (auto it = messages_.begin(); it != messages_.end(); ++it) {
            if (it->first == type) {
                auto* ptr = std::any_cast<T>(&it->second);
                if (ptr) {
                    out = std::move(*ptr);
                    messages_.erase(it);
                    return true;
                }
            }
        }
        return false;
    }
};

int main() {
    // --- Config store ---
    ConfigStore config;
    config.set("port", 8080);
    config.set("host", std::string("localhost"));
    config.set("debug", true);
    config.set("rate_limit", 3.14);

    std::cout << "port: " << config.get<int>("port") << "\n";
    std::cout << "host: " << config.get<std::string>("host") << "\n";
    std::cout << "missing: " << config.get_or<int>("missing_key", 42) << "\n";

    // Type checking
    std::cout << "port type: " << config.type_of("port").name() << "\n";

    // Wrong type = bad_any_cast
    try {
        config.get<std::string>("port");  // port is int, not string
    } catch (const std::bad_any_cast& e) {
        std::cout << "Type mismatch: " << e.what() << "\n";
    }

    // --- Plugin system ---
    PluginHost host;
    host.register_hook("on_request", [](const std::any& arg) -> std::any {
        auto url = std::any_cast<std::string>(arg);
        std::cout << "Plugin A: logging request to " << url << "\n";
        return std::string("logged");
    });
    host.register_hook("on_request", [](const std::any& arg) -> std::any {
        auto url = std::any_cast<std::string>(arg);
        return static_cast<int>(url.size());  // return different type
    });

    auto results = host.fire("on_request", std::string("/api/data"));
    std::cout << "Hook 1 returned: " << std::any_cast<std::string>(results[0]) << "\n";
    std::cout << "Hook 2 returned: " << std::any_cast<int>(results[1]) << "\n";

    // --- Message queue ---
    MessageQueue mq;
    mq.push("log", std::string("server started"));
    mq.push("metric", 42.5);

    std::string log_msg;
    if (mq.try_pop("log", log_msg))
        std::cout << "Got log: " << log_msg << "\n";

    return 0;
}
```

**When to use `std::any` vs `std::variant`:**

| | `std::variant` | `std::any` |
|---|---|---|
| Type set | Closed (known at compile time) | Open (any copyable type) |
| Safety | Compile-time exhaustive matching | Runtime `any_cast` only |
| Allocation | Inline (no heap) | May heap-allocate (SBO for small types) |
| Use case | AST nodes, state machines | Config stores, plugin APIs, serialization |'''),

    ("cpp_deep/sean_parent_type_erasure", r'''Show the Sean Parent type erasure pattern — runtime polymorphism without inheritance — using a Document/Drawable example.''', r'''<think>
Sean Parent's "Inheritance Is The Base Class of Evil" talk introduced a
type erasure pattern that gives runtime polymorphism without requiring
types to inherit from a base class. The key idea:

1. Public class holds a concept (abstract base) via unique_ptr.
2. A templated model class inherits from concept and wraps the concrete type.
3. External types don't need to know about the concept/model hierarchy.
4. Free functions or member functions define the interface.

This is essentially what std::function does internally.
The classic example is a Document as a vector of "drawable" objects where
any type with a draw() free function can be added.

I need to show:
- The concept (abstract base) with pure virtual.
- The model (template wrapping any T).
- The type-erased wrapper class.
- Value semantics (copyable via clone).
- External types that are completely unaware of the hierarchy.
</think>

The Sean Parent type erasure pattern achieves runtime polymorphism without inheritance — types need no base class:

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>

// --- Free functions that define the "interface" ---
// Any type that has these free functions can participate.
// The types themselves need NO base class, NO virtual methods.

// Forward declarations for the free function interface
class Circle {
    double radius_;
public:
    explicit Circle(double r) : radius_(r) {}
    double radius() const { return radius_; }
};

class Rectangle {
    double w_, h_;
public:
    Rectangle(double w, double h) : w_(w), h_(h) {}
    double width() const { return w_; }
    double height() const { return h_; }
};

// These types know NOTHING about any base class or interface
class TextLabel {
    std::string text_;
public:
    explicit TextLabel(std::string t) : text_(std::move(t)) {}
    const std::string& text() const { return text_; }
};

// Free functions — the "concept" that types must satisfy
void draw(const Circle& c, std::ostream& out, std::size_t indent) {
    out << std::string(indent, ' ') << "Circle(r=" << c.radius() << ")\n";
}

void draw(const Rectangle& r, std::ostream& out, std::size_t indent) {
    out << std::string(indent, ' ') << "Rect(" << r.width() << "x" << r.height() << ")\n";
}

void draw(const TextLabel& t, std::ostream& out, std::size_t indent) {
    out << std::string(indent, ' ') << "\"" << t.text() << "\"\n";
}

// =============================================================
// The type erasure wrapper — this is the Sean Parent pattern
// =============================================================
class Drawable {
    // Internal abstract concept
    struct Concept {
        virtual ~Concept() = default;
        virtual void draw_(std::ostream& out, std::size_t indent) const = 0;
        virtual std::unique_ptr<Concept> clone_() const = 0;
    };

    // Internal model — wraps any T that supports draw()
    template <typename T>
    struct Model final : Concept {
        T data_;
        explicit Model(T val) : data_(std::move(val)) {}
        void draw_(std::ostream& out, std::size_t indent) const override {
            draw(data_, out, indent);   // calls the free function
        }
        std::unique_ptr<Concept> clone_() const override {
            return std::make_unique<Model>(data_);
        }
    };

    std::unique_ptr<Concept> self_;

public:
    // Accept ANY type that has a draw() free function
    template <typename T>
    Drawable(T val) : self_(std::make_unique<Model<T>>(std::move(val))) {}

    // Value semantics — copyable
    Drawable(const Drawable& other) : self_(other.self_->clone_()) {}
    Drawable(Drawable&&) noexcept = default;
    Drawable& operator=(Drawable rhs) {
        self_ = std::move(rhs.self_);
        return *this;
    }

    // Public interface delegates to concept
    friend void draw(const Drawable& d, std::ostream& out, std::size_t indent) {
        d.self_->draw_(out, indent);
    }
};

// --- Document is just a vector of Drawables ---
using Document = std::vector<Drawable>;

void draw(const Document& doc, std::ostream& out, std::size_t indent = 0) {
    out << std::string(indent, ' ') << "<document>\n";
    for (const auto& d : doc) {
        draw(d, out, indent + 2);
    }
    out << std::string(indent, ' ') << "</document>\n";
}

// --- Even later: add a NEW type without modifying anything ---
struct Image {
    std::string path;
    int width, height;
};

void draw(const Image& img, std::ostream& out, std::size_t indent) {
    out << std::string(indent, ' ') << "Image(" << img.path
        << " " << img.width << "x" << img.height << ")\n";
}

int main() {
    Document doc;

    // Add objects of completely unrelated types — no common base class
    doc.emplace_back(Circle{5.0});
    doc.emplace_back(Rectangle{3.0, 4.0});
    doc.emplace_back(TextLabel{"Hello, type erasure!"});
    doc.emplace_back(Image{"/img/logo.png", 256, 256});

    // Documents are value types — can be nested
    Document nested;
    nested.emplace_back(TextLabel{"Nested section"});
    nested.emplace_back(Circle{1.0});

    draw(doc, std::cout);
    std::cout << "\n";

    // Copy works (value semantics)
    Document copy = doc;
    draw(copy, std::cout);

    return 0;
}
```

**Why this pattern matters:**
- Types (`Circle`, `Rectangle`, `TextLabel`, `Image`) are **completely independent** — no base class, no virtual methods, no modification needed.
- New types are added by defining a `draw()` free function — fully open for extension.
- `Drawable` has **value semantics** (copyable, movable) unlike raw polymorphism with pointers.
- This is exactly how `std::function` works internally (Concept = callable interface, Model = templated wrapper).'''),

    ("cpp_deep/type_erasure_concept_function", r'''Show type erasure without inheritance using C++20 concepts and std::function, as a lighter alternative to the Sean Parent pattern.''', r'''<think>
This is a simpler type erasure approach using std::function to store the erased operations.
Instead of the concept/model hierarchy, we capture operations as std::function members.
Combined with C++20 concepts, we get compile-time checking of the interface.

Advantages: simpler code, no manual clone/virtual.
Disadvantages: slightly more overhead (multiple std::function objects), less efficient for many operations.

I'll show:
1. A concept constraining what types can be stored.
2. A wrapper that stores the object as std::any or shared_ptr<void>.
3. Operations captured as std::function during construction.
4. Compare with the heavier pattern.
</think>

A lighter type erasure approach using `std::function` and C++20 concepts — no virtual dispatch hierarchy needed:

```cpp
#include <any>
#include <concepts>
#include <functional>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

// --- C++20 concept: what types must support ---
template <typename T>
concept Serializable = requires(const T& t) {
    { serialize(t) } -> std::convertible_to<std::string>;
    { byte_size(t) } -> std::convertible_to<std::size_t>;
};

// --- Free functions for concrete types (no base class needed) ---

struct UserRecord {
    int id;
    std::string name;
};

std::string serialize(const UserRecord& u) {
    return "{\"id\":" + std::to_string(u.id) + ",\"name\":\"" + u.name + "\"}";
}

std::size_t byte_size(const UserRecord& u) {
    return sizeof(u.id) + u.name.size();
}

struct LogEntry {
    std::string level;
    std::string message;
    long timestamp;
};

std::string serialize(const LogEntry& e) {
    return "[" + e.level + "] " + std::to_string(e.timestamp) + ": " + e.message;
}

std::size_t byte_size(const LogEntry& e) {
    return e.level.size() + e.message.size() + sizeof(e.timestamp);
}

struct Metric {
    std::string name;
    double value;
};

std::string serialize(const Metric& m) {
    return m.name + "=" + std::to_string(m.value);
}

std::size_t byte_size(const Metric&) { return sizeof(double) + sizeof(std::string); }

// --- Type-erased wrapper using std::function ---
class AnySerializable {
    std::any storage_;
    std::function<std::string()> serialize_fn_;
    std::function<std::size_t()> byte_size_fn_;

public:
    // Concept-constrained constructor — compile error if T doesn't match
    template <Serializable T>
    AnySerializable(T value) {
        auto ptr = std::make_shared<T>(std::move(value));
        storage_ = ptr;
        // Capture operations at construction time
        serialize_fn_ = [ptr]() { return serialize(*ptr); };
        byte_size_fn_ = [ptr]() { return byte_size(*ptr); };
    }

    std::string serialize() const { return serialize_fn_(); }
    std::size_t byte_size() const { return byte_size_fn_(); }
};

// --- A buffer that stores any Serializable ---
class SerializationBuffer {
    std::vector<AnySerializable> items_;

public:
    template <Serializable T>
    void add(T item) {
        items_.emplace_back(std::move(item));
    }

    std::string serialize_all() const {
        std::string result;
        for (const auto& item : items_) {
            result += item.serialize() + "\n";
        }
        return result;
    }

    std::size_t total_bytes() const {
        std::size_t total = 0;
        for (const auto& item : items_) {
            total += item.byte_size();
        }
        return total;
    }

    std::size_t count() const { return items_.size(); }
};

// --- Even simpler: single-function erasure with just std::function ---
// For cases where you only need one operation, std::function IS the type erasure.

template <typename T>
concept Printable = requires(const T& t, std::ostream& os) {
    { os << t } -> std::same_as<std::ostream&>;
};

class AnyPrintable {
    std::function<void(std::ostream&)> print_fn_;
public:
    template <Printable T>
    AnyPrintable(T value)
        : print_fn_([v = std::move(value)](std::ostream& os) { os << v; }) {}

    friend std::ostream& operator<<(std::ostream& os, const AnyPrintable& p) {
        p.print_fn_(os);
        return os;
    }
};

int main() {
    // --- Multi-operation type erasure ---
    SerializationBuffer buffer;

    buffer.add(UserRecord{1, "Alice"});
    buffer.add(LogEntry{"ERROR", "disk full", 1709827200});
    buffer.add(Metric{"cpu_usage", 73.5});

    std::cout << "=== Serialized ===\n";
    std::cout << buffer.serialize_all();
    std::cout << "Total bytes: " << buffer.total_bytes() << "\n";
    std::cout << "Items: " << buffer.count() << "\n";

    // --- Single-function erasure ---
    std::cout << "\n=== AnyPrintable ===\n";
    std::vector<AnyPrintable> printables;
    printables.emplace_back(42);
    printables.emplace_back(std::string("hello"));
    printables.emplace_back(3.14);

    for (const auto& p : printables)
        std::cout << p << "\n";

    // Compile error if type doesn't satisfy concept:
    // struct Opaque {};
    // buffer.add(Opaque{});  // error: Opaque does not satisfy Serializable

    return 0;
}
```

**Comparison with Sean Parent pattern:**

| | Sean Parent (Concept/Model) | std::function approach |
|---|---|---|
| Boilerplate | More (virtual base + template model) | Less (just capture lambdas) |
| Performance | One vtable lookup per call | std::function overhead per operation |
| Scaling | Efficient with many operations | Each operation adds a std::function |
| Best for | Core abstractions with many operations | Lightweight wrappers, few operations |

For a single operation, `std::function` alone **is** type erasure.'''),

    ("cpp_deep/algebraic_data_types_monostate", r'''Show how to build proper algebraic data types in C++ using std::variant and std::monostate, including a state machine example.''', r'''<think>
Algebraic data types (ADTs) in C++ are built with:
- Sum types: std::variant (A | B | C)
- Product types: structs (A & B & C)
- Unit type: std::monostate (for variant default construction and as "no data" tag)

std::monostate is useful when:
1. variant needs a default-constructible first type
2. Representing states with no associated data

A state machine is the perfect example — states carry different data,
transitions are modeled as variant changes, and some states have no payload.

I'll build a TCP connection state machine: Closed, Listening, Connected, Error.
Each state carries relevant data. Transitions are functions that return the new state.
</think>

Algebraic data types in C++ using `std::variant`, `std::monostate`, and structs:

```cpp
#include <iostream>
#include <string>
#include <variant>

template <class... Ts>
struct overloaded : Ts... { using Ts::operator()...; };
template <class... Ts>
overloaded(Ts...) -> overloaded<Ts...>;

// =============================================================
// State machine: TCP-like connection
// Each state is a type; associated data varies per state.
// =============================================================

// States as types (product types — each carries relevant data)
struct Closed {};                                    // no data — could use monostate

struct Listening {
    int port;
};

struct Connected {
    std::string remote_addr;
    int remote_port;
    std::size_t bytes_sent = 0;
    std::size_t bytes_received = 0;
};

struct Error {
    std::string reason;
    int code;
};

// Sum type: the connection is in exactly one state
using ConnectionState = std::variant<Closed, Listening, Connected, Error>;

// --- State descriptions ---
std::string describe(const ConnectionState& state) {
    return std::visit(overloaded{
        [](const Closed&)     { return std::string("CLOSED"); },
        [](const Listening& s) { return "LISTENING on port " + std::to_string(s.port); },
        [](const Connected& s) {
            return "CONNECTED to " + s.remote_addr + ":" + std::to_string(s.remote_port)
                 + " (sent=" + std::to_string(s.bytes_sent)
                 + " recv=" + std::to_string(s.bytes_received) + ")";
        },
        [](const Error& s) {
            return "ERROR [" + std::to_string(s.code) + "]: " + s.reason;
        }
    }, state);
}

// --- Transitions: each takes a state and returns a new state ---

ConnectionState listen(const ConnectionState& state, int port) {
    return std::visit(overloaded{
        [port](const Closed&) -> ConnectionState {
            return Listening{port};
        },
        [](const auto&) -> ConnectionState {
            return Error{"Cannot listen: not in CLOSED state", 1};
        }
    }, state);
}

ConnectionState accept(const ConnectionState& state,
                        const std::string& addr, int port) {
    return std::visit(overloaded{
        [&](const Listening&) -> ConnectionState {
            return Connected{addr, port, 0, 0};
        },
        [](const auto&) -> ConnectionState {
            return Error{"Cannot accept: not LISTENING", 2};
        }
    }, state);
}

ConnectionState send(ConnectionState state, std::size_t bytes) {
    return std::visit(overloaded{
        [bytes](Connected s) -> ConnectionState {
            s.bytes_sent += bytes;
            return s;
        },
        [](const auto&) -> ConnectionState {
            return Error{"Cannot send: not CONNECTED", 3};
        }
    }, state);
}

ConnectionState close(const ConnectionState&) {
    return Closed{};
}

// =============================================================
// Option type with monostate for "nothing" + named alternatives
// =============================================================

struct Pending : std::monostate {};   // tag type derived from monostate
struct Success { int value; };
struct Failure { std::string reason; };

using AsyncResult = std::variant<Pending, Success, Failure>;

bool is_complete(const AsyncResult& r) {
    return !std::holds_alternative<Pending>(r);
}

void print_result(const AsyncResult& r) {
    std::visit(overloaded{
        [](const Pending&)    { std::cout << "  Pending...\n"; },
        [](const Success& s)  { std::cout << "  Success: " << s.value << "\n"; },
        [](const Failure& f)  { std::cout << "  Failure: " << f.reason << "\n"; }
    }, r);
}

int main() {
    // --- State machine ---
    std::cout << "=== TCP State Machine ===\n";
    ConnectionState conn = Closed{};
    std::cout << "1. " << describe(conn) << "\n";

    conn = listen(conn, 8080);
    std::cout << "2. " << describe(conn) << "\n";

    conn = accept(conn, "192.168.1.100", 45321);
    std::cout << "3. " << describe(conn) << "\n";

    conn = send(conn, 1024);
    conn = send(conn, 2048);
    std::cout << "4. " << describe(conn) << "\n";

    conn = close(conn);
    std::cout << "5. " << describe(conn) << "\n";

    // Invalid transition — caught by pattern matching
    conn = accept(conn, "x", 0);   // can't accept when closed
    std::cout << "6. " << describe(conn) << "\n";

    // --- monostate-based AsyncResult ---
    std::cout << "\n=== Async Results ===\n";
    AsyncResult r1 = Pending{};      // default: monostate-derived
    AsyncResult r2 = Success{42};
    AsyncResult r3 = Failure{"timeout"};

    print_result(r1);
    print_result(r2);
    print_result(r3);

    std::cout << "r1 complete: " << is_complete(r1) << "\n";
    std::cout << "r2 complete: " << is_complete(r2) << "\n";

    return 0;
}
```

**Key insights:**
- **Sum types** (`variant`): model "one of" — a connection is in exactly one state.
- **Product types** (structs): model "all of" — `Connected` has address AND port AND counters.
- **`std::monostate`**: unit type for states that carry no data; enables default construction of variant.
- State transitions are **pure functions**: old state in, new state out. Invalid transitions return `Error`.'''),

    ("cpp_deep/strong_typedef_opaque", r'''Implement the strong typedef (opaque typedef) pattern in C++ to prevent mixing up values of the same underlying type, like UserID and OrderID both being int.''', r'''<think>
The problem: `using UserID = int; using OrderID = int;` are just aliases — you can
mix them up with no compiler error. We need distinct types that wrap the same
underlying type but are incompatible at the type level.

Approaches:
1. Simple: template class parameterized by a tag type.
2. Advanced: CRTP base with opt-in operators.
3. C++20: with comparison operators via spaceship.

I'll show a clean generic StrongType template that:
- Wraps any underlying type
- Uses a phantom tag to make each instantiation distinct
- Optionally inherits operator skills (comparable, hashable, arithmetic)
- Prevents implicit conversions
</think>

Strong typedefs prevent accidentally mixing values that share the same underlying type:

```cpp
#include <functional>
#include <iostream>
#include <string>
#include <unordered_map>
#include <compare>

// =============================================================
// Generic StrongType wrapper
// =============================================================
template <typename T, typename Tag>
class StrongType {
    T value_;
public:
    constexpr explicit StrongType(T val) : value_(std::move(val)) {}

    // Explicit access only — no implicit conversion back to T
    constexpr const T& value() const & { return value_; }
    constexpr T& value() & { return value_; }
    constexpr T&& value() && { return std::move(value_); }

    // Spaceship operator (C++20) — only compares same StrongType tag
    constexpr auto operator<=>(const StrongType&) const = default;
    constexpr bool operator==(const StrongType&) const = default;
};

// --- Hash support ---
template <typename T, typename Tag>
struct std::hash<StrongType<T, Tag>> {
    std::size_t operator()(const StrongType<T, Tag>& st) const noexcept {
        return std::hash<T>{}(st.value());
    }
};

// --- Stream output ---
template <typename T, typename Tag>
std::ostream& operator<<(std::ostream& os, const StrongType<T, Tag>& st) {
    return os << st.value();
}

// =============================================================
// Define distinct types — each tag makes a unique type
// =============================================================
struct UserIdTag {};
struct OrderIdTag {};
struct ProductIdTag {};
struct EmailTag {};
struct MetersTag {};
struct KilogramsTag {};

using UserId    = StrongType<int, UserIdTag>;
using OrderId   = StrongType<int, OrderIdTag>;
using ProductId = StrongType<int, ProductIdTag>;
using Email     = StrongType<std::string, EmailTag>;
using Meters    = StrongType<double, MetersTag>;
using Kilograms = StrongType<double, KilogramsTag>;

// =============================================================
// Functions that accept ONLY the correct type
// =============================================================
struct User {
    UserId id;
    std::string name;
    Email email;
};

struct Order {
    OrderId id;
    UserId customer_id;
    ProductId product_id;
};

User find_user(UserId id) {
    return {id, "Alice", Email{"alice@example.com"}};
}

Order find_order(OrderId id) {
    return {id, UserId{1}, ProductId{100}};
}

// This would NOT compile — type safety!
// Order bad = find_order(UserId{1});       // ERROR: UserId != OrderId
// void mixup(UserId a, OrderId b) { a == b; } // ERROR: different types

// =============================================================
// Advanced: arithmetic StrongType for physical units
// =============================================================
template <typename T, typename Tag>
class ArithmeticType : public StrongType<T, Tag> {
    using Base = StrongType<T, Tag>;
public:
    using Base::Base;

    constexpr ArithmeticType operator+(const ArithmeticType& rhs) const {
        return ArithmeticType(this->value() + rhs.value());
    }
    constexpr ArithmeticType operator-(const ArithmeticType& rhs) const {
        return ArithmeticType(this->value() - rhs.value());
    }
    constexpr ArithmeticType operator*(T scalar) const {
        return ArithmeticType(this->value() * scalar);
    }
    constexpr ArithmeticType operator/(T scalar) const {
        return ArithmeticType(this->value() / scalar);
    }
};

struct DistanceTag {};
struct DurationTag {};
using Distance = ArithmeticType<double, DistanceTag>;
using Duration = ArithmeticType<double, DurationTag>;

// Can add Distance + Distance, but NOT Distance + Duration
// Distance d = Distance{5.0} + Duration{3.0};  // ERROR!

int main() {
    // --- ID safety ---
    UserId uid{42};
    OrderId oid{42};
    ProductId pid{100};

    // Same underlying value, but distinct types
    std::cout << "User:  " << uid << "\n";
    std::cout << "Order: " << oid << "\n";

    // uid == oid;  // COMPILE ERROR: different types

    // Comparison works within same type
    UserId uid2{43};
    std::cout << "uid < uid2: " << (uid < uid2) << "\n";    // 1
    std::cout << "uid == uid:  " << (uid == uid) << "\n";     // 1

    // --- Use in containers ---
    std::unordered_map<UserId, std::string> user_names;
    user_names[UserId{1}] = "Alice";
    user_names[UserId{2}] = "Bob";

    // --- Physical units ---
    Distance d1{100.0}, d2{50.0};
    Distance total = d1 + d2;
    Distance half = total / 2.0;
    std::cout << "Distance: " << total << " -> half: " << half << "\n";

    Duration t1{10.0};
    // Distance bad = d1 + t1;  // COMPILE ERROR: can't add Distance + Duration

    // --- API safety ---
    auto user = find_user(uid);
    auto order = find_order(oid);
    // auto bad = find_order(uid);  // COMPILE ERROR: expected OrderId, got UserId

    std::cout << "Found user: " << user.name << " <" << user.email << ">\n";
    std::cout << "Order " << order.id << " for user " << order.customer_id << "\n";

    return 0;
}
```

**What this prevents:**
```cpp
void process(UserId user, OrderId order, ProductId product);

// Without strong types: easy to mix up
process(42, 99, 7);         // which is which?

// With strong types: crystal clear, compiler-enforced
process(UserId{42}, OrderId{99}, ProductId{7});
process(OrderId{99}, UserId{42}, ProductId{7});  // COMPILE ERROR
```'''),

    ("cpp_deep/phantom_types_state_tracking", r'''Show how to use phantom types in C++ to track state at compile time, making illegal state transitions a compile error.''', r'''<think>
Phantom types are type parameters that don't correspond to any stored data — they
exist purely to carry compile-time information. In C++, we use empty tag structs
as template parameters to encode state.

Classic example: a file handle that must be opened before reading, and closed
after use. With phantom types, calling read() on a closed handle is a compile error.

The key technique: state transitions return a NEW type (different phantom tag),
not modify the existing object. This makes the state machine visible in the type system.

I'll show:
1. Basic phantom type state machine (file handle).
2. Builder pattern with phantom types (ensures all required fields are set).
3. Using concepts to constrain which states support which operations.
</think>

Phantom types encode state in the type system, making illegal transitions compile errors:

```cpp
#include <concepts>
#include <fstream>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

// =============================================================
// Example 1: File handle with compile-time state tracking
// =============================================================

// Phantom state tags — no data, pure type-level markers
struct FileClosed {};
struct FileOpen {};
struct FileEof {};

template <typename State>
class File {
    std::string path_;
    std::fstream stream_;

    // Private constructor — only transitions can create new states
    File(std::string path, std::fstream stream)
        : path_(std::move(path)), stream_(std::move(stream)) {}

    template <typename> friend class File;   // allow state transitions

public:
    // Start in Closed state
    explicit File(std::string path) requires std::same_as<State, FileClosed>
        : path_(std::move(path)) {}

    // Transition: Closed -> Open
    File<FileOpen> open() && requires std::same_as<State, FileClosed> {
        std::fstream fs(path_, std::ios::in | std::ios::out | std::ios::app);
        if (!fs.is_open()) throw std::runtime_error("Cannot open: " + path_);
        return File<FileOpen>(std::move(path_), std::move(fs));
    }

    // Only available in Open state
    void write(const std::string& data) requires std::same_as<State, FileOpen> {
        stream_ << data;
    }

    std::string read_line() requires std::same_as<State, FileOpen> {
        std::string line;
        std::getline(stream_, line);
        return line;
    }

    // Transition: Open -> Closed
    File<FileClosed> close() && requires std::same_as<State, FileOpen> {
        stream_.close();
        return File<FileClosed>(std::move(path_));
    }

    const std::string& path() const { return path_; }
};

// =============================================================
// Example 2: Builder with phantom types — required fields enforced
// =============================================================

struct MissingHost {};
struct HasHost {};
struct MissingPort {};
struct HasPort {};

template <typename HostState, typename PortState>
class ServerConfigBuilder {
    std::string host_;
    int port_ = 0;
    int max_conns_ = 100;
    bool tls_ = false;

    ServerConfigBuilder(std::string h, int p, int mc, bool t)
        : host_(std::move(h)), port_(p), max_conns_(mc), tls_(t) {}

    template <typename, typename> friend class ServerConfigBuilder;

public:
    ServerConfigBuilder() requires (std::same_as<HostState, MissingHost>
                                 && std::same_as<PortState, MissingPort>) {}

    // Set host: MissingHost -> HasHost
    auto host(std::string h) && -> ServerConfigBuilder<HasHost, PortState> {
        return {std::move(h), port_, max_conns_, tls_};
    }

    // Set port: MissingPort -> HasPort
    auto port(int p) && -> ServerConfigBuilder<HostState, HasPort> {
        return {std::move(host_), p, max_conns_, tls_};
    }

    // Optional fields don't change state
    auto max_connections(int mc) && -> ServerConfigBuilder<HostState, PortState> {
        return {std::move(host_), port_, mc, tls_};
    }

    auto tls(bool t) && -> ServerConfigBuilder<HostState, PortState> {
        return {std::move(host_), port_, max_conns_, t};
    }

    // build() only available when BOTH required fields are set
    struct ServerConfig {
        std::string host;
        int port;
        int max_connections;
        bool tls;
    };

    ServerConfig build() && requires (std::same_as<HostState, HasHost>
                                   && std::same_as<PortState, HasPort>) {
        return {std::move(host_), port_, max_conns_, tls_};
    }
};

using ServerBuilder = ServerConfigBuilder<MissingHost, MissingPort>;

int main() {
    // --- File handle state machine ---
    {
        File<FileClosed> f("/tmp/phantom_test.txt");

        // f.write("x");    // COMPILE ERROR: write requires FileOpen
        // f.read_line();   // COMPILE ERROR: read requires FileOpen

        auto open_f = std::move(f).open();    // Closed -> Open
        open_f.write("hello phantom types\n");

        // Can't open an already open file:
        // std::move(open_f).open();  // COMPILE ERROR: open requires FileClosed

        auto closed_f = std::move(open_f).close();  // Open -> Closed

        // closed_f.write("x");  // COMPILE ERROR: write requires FileOpen

        std::cout << "File state machine: " << closed_f.path() << " OK\n";
    }

    // --- Builder with required fields ---
    {
        auto config = ServerBuilder{}
            .host("0.0.0.0")          // MissingHost -> HasHost
            .port(8080)               // MissingPort -> HasPort
            .max_connections(500)     // optional
            .tls(true)               // optional
            .build();                 // OK: both required fields set

        std::cout << "Server: " << config.host << ":" << config.port
                  << " (max=" << config.max_connections
                  << ", tls=" << config.tls << ")\n";

        // Missing required field:
        // ServerBuilder{}.host("x").build();          // COMPILE ERROR: port missing
        // ServerBuilder{}.port(80).build();           // COMPILE ERROR: host missing
        // ServerBuilder{}.build();                    // COMPILE ERROR: both missing
    }

    return 0;
}
```

**How phantom types work:**
- State tags (`FileClosed`, `FileOpen`) are template parameters that carry no data.
- Transitions return a **new type** (`File<FileOpen>`) — the old type is consumed via `&&`.
- `requires` clauses restrict operations to valid states — violations are compile errors, not runtime errors.
- The `&&` qualifier ensures the old state is moved from, preventing use-after-transition.'''),

    ("cpp_deep/compile_time_units_dimensional", r'''Implement a compile-time units library with dimensional analysis that catches unit errors at compile time, like adding meters to seconds.''', r'''<think>
Compile-time dimensional analysis uses template parameters to encode physical dimensions.
Each dimension (length, time, mass) is an integer exponent in the type.
Multiplication adds exponents, division subtracts them.
Addition requires matching dimensions — enforced at compile time.

I'll use a Quantity template parameterized by dimension exponents:
Quantity<L, T, M> where L=length, T=time, M=mass exponents.
- Meters: Quantity<1, 0, 0>
- Seconds: Quantity<0, 1, 0>
- Velocity (m/s): Quantity<1, -1, 0>
- Acceleration: Quantity<1, -2, 0>
- Force (N = kg*m/s^2): Quantity<1, -2, 1>

This is a simplified version of what mp-units (C++23 library) does.
</think>

A compile-time dimensional analysis library that catches unit errors as compile errors:

```cpp
#include <cmath>
#include <iostream>
#include <ratio>

// =============================================================
// Quantity: value + compile-time dimensions
// Template params are dimension exponents: Length, Time, Mass
// =============================================================
template <int L, int T, int M>
class Quantity {
    double value_;
public:
    constexpr explicit Quantity(double v) : value_(v) {}
    constexpr double value() const { return value_; }

    // Addition: dimensions must match exactly
    constexpr Quantity operator+(Quantity rhs) const {
        return Quantity(value_ + rhs.value_);
    }
    constexpr Quantity operator-(Quantity rhs) const {
        return Quantity(value_ - rhs.value_);
    }

    // Scalar multiplication/division
    constexpr Quantity operator*(double s) const { return Quantity(value_ * s); }
    constexpr Quantity operator/(double s) const { return Quantity(value_ / s); }
    friend constexpr Quantity operator*(double s, Quantity q) { return Quantity(s * q.value_); }

    // Comparison
    constexpr auto operator<=>(const Quantity&) const = default;

    // Negation
    constexpr Quantity operator-() const { return Quantity(-value_); }
};

// Multiplication of quantities: add exponents
template <int L1, int T1, int M1, int L2, int T2, int M2>
constexpr Quantity<L1+L2, T1+T2, M1+M2>
operator*(Quantity<L1,T1,M1> a, Quantity<L2,T2,M2> b) {
    return Quantity<L1+L2, T1+T2, M1+M2>(a.value() * b.value());
}

// Division of quantities: subtract exponents
template <int L1, int T1, int M1, int L2, int T2, int M2>
constexpr Quantity<L1-L2, T1-T2, M1-M2>
operator/(Quantity<L1,T1,M1> a, Quantity<L2,T2,M2> b) {
    return Quantity<L1-L2, T1-T2, M1-M2>(a.value() / b.value());
}

// =============================================================
// Named dimension aliases
// =============================================================
using Scalar       = Quantity<0, 0, 0>;    // dimensionless
using Length       = Quantity<1, 0, 0>;    // meters
using Time         = Quantity<0, 1, 0>;    // seconds
using Mass         = Quantity<0, 0, 1>;    // kilograms
using Velocity     = Quantity<1, -1, 0>;   // m/s
using Acceleration = Quantity<1, -2, 0>;   // m/s^2
using Force        = Quantity<1, -2, 1>;   // N = kg*m/s^2
using Energy       = Quantity<2, -2, 1>;   // J = kg*m^2/s^2
using Area         = Quantity<2, 0, 0>;    // m^2
using Frequency    = Quantity<0, -1, 0>;   // Hz = 1/s

// =============================================================
// User-defined literals for convenience
// =============================================================
constexpr Length       operator""_m(long double v)  { return Length(static_cast<double>(v)); }
constexpr Length       operator""_m(unsigned long long v) { return Length(static_cast<double>(v)); }
constexpr Time         operator""_s(long double v)  { return Time(static_cast<double>(v)); }
constexpr Time         operator""_s(unsigned long long v) { return Time(static_cast<double>(v)); }
constexpr Mass         operator""_kg(long double v) { return Mass(static_cast<double>(v)); }
constexpr Mass         operator""_kg(unsigned long long v) { return Mass(static_cast<double>(v)); }

// Derived unit literals
constexpr Velocity velocity(Length d, Time t) { return d / t; }
constexpr Force    force(Mass m, Acceleration a) { return m * a; }

// =============================================================
// Physics functions — types enforce dimensional correctness
// =============================================================
constexpr Energy kinetic_energy(Mass m, Velocity v) {
    // E = 0.5 * m * v^2
    return (m * v * v) / 2.0;
    // Return type: Mass * Velocity * Velocity = Quantity<0,0,1> * Quantity<1,-1,0> * Quantity<1,-1,0>
    //            = Quantity<2,-2,1> = Energy  ✓
}

constexpr Length free_fall_distance(Acceleration g, Time t) {
    // d = 0.5 * g * t^2
    return (g * t * t) / 2.0;
    // Acceleration * Time * Time = Quantity<1,-2,0> * Quantity<0,1,0> * Quantity<0,1,0>
    //                            = Quantity<1,0,0> = Length  ✓
}

// Print helper
template <int L, int T, int M>
std::ostream& operator<<(std::ostream& os, Quantity<L,T,M> q) {
    os << q.value();
    if constexpr (L != 0) os << " m" << (L != 1 ? "^" + std::to_string(L) : "");
    if constexpr (T != 0) os << " s" << (T != 1 ? "^" + std::to_string(T) : "");
    if constexpr (M != 0) os << " kg" << (M != 1 ? "^" + std::to_string(M) : "");
    if constexpr (L == 0 && T == 0 && M == 0) os << " (dimensionless)";
    return os;
}

int main() {
    constexpr auto distance = 100.0_m;
    constexpr auto time     = 9.58_s;
    constexpr auto mass     = 80.0_kg;

    constexpr auto speed = distance / time;      // Velocity
    constexpr auto g     = Acceleration(9.81);   // m/s^2

    std::cout << "Distance: " << distance << "\n";
    std::cout << "Time:     " << time << "\n";
    std::cout << "Speed:    " << speed << "\n";

    constexpr auto ke = kinetic_energy(mass, speed);
    std::cout << "KE:       " << ke << "\n";

    constexpr auto fall = free_fall_distance(g, 3.0_s);
    std::cout << "Fall 3s:  " << fall << "\n";

    constexpr auto f = force(mass, g);
    std::cout << "Weight:   " << f << "\n";

    // Area
    auto room = 5.0_m * 4.0_m;   // type: Area (Quantity<2,0,0>)
    std::cout << "Room:     " << room << "\n";

    // --- COMPILE-TIME ERRORS (uncomment to see) ---
    // auto bad1 = distance + time;      // ERROR: Length + Time dimension mismatch
    // auto bad2 = distance + mass;      // ERROR: Length + Mass dimension mismatch
    // Force f2 = mass * speed;          // ERROR: kg*m/s is momentum, not force
    // Length d2 = speed;                // ERROR: Velocity is not Length

    // This works — dimensions check out:
    auto momentum = mass * speed;   // Quantity<1,-1,1> = kg*m/s
    std::cout << "Momentum: " << momentum << "\n";

    return 0;
}
```

**Compile-time guarantees:**
- `meters + seconds` = compile error (dimension mismatch in `operator+`)
- `mass * velocity` gives momentum, not force — assigning to `Force` is a compile error
- All dimension arithmetic happens in template parameters — zero runtime cost'''),

    ("cpp_deep/expected_railway_chaining", r'''Show railway-oriented programming in C++ using std::expected chaining, where a pipeline of operations either succeeds through or short-circuits on error.''', r'''<think>
Railway-oriented programming (ROP) models computation as two tracks:
success track and error track. Each function can succeed (continue on success track)
or fail (switch to error track). Once on the error track, remaining steps are skipped.

std::expected's monadic operations (and_then, transform, or_else) implement this pattern.
I'll build a realistic pipeline: validate input -> parse -> transform -> persist.
Each step can fail, and errors propagate automatically.

I should show:
1. A pipeline of and_then calls (the "railway").
2. Error recovery with or_else (switching back from error to success track).
3. transform_error for error type conversion between pipeline stages.
4. Composing smaller pipelines into larger ones.
</think>

Railway-oriented programming uses `std::expected` chaining to model success/error tracks:

```cpp
#include <algorithm>
#include <cctype>
#include <expected>
#include <iostream>
#include <string>
#include <vector>

// =============================================================
// Error types for different pipeline stages
// =============================================================
struct ValidationError {
    std::string field;
    std::string message;
};

struct ProcessingError {
    std::string step;
    std::string detail;
};

std::ostream& operator<<(std::ostream& os, const ValidationError& e) {
    return os << "[Validation] " << e.field << ": " << e.message;
}

std::ostream& operator<<(std::ostream& os, const ProcessingError& e) {
    return os << "[Processing] " << e.step << ": " << e.detail;
}

// Unified error type for the full pipeline
struct PipelineError {
    std::string stage;
    std::string message;

    static PipelineError from(const ValidationError& e) {
        return {"validation", e.field + ": " + e.message};
    }
    static PipelineError from(const ProcessingError& e) {
        return {"processing", e.step + ": " + e.detail};
    }
};

std::ostream& operator<<(std::ostream& os, const PipelineError& e) {
    return os << "[" << e.stage << "] " << e.message;
}

// =============================================================
// Domain types
// =============================================================
struct RawInput {
    std::string email;
    std::string age_str;
    std::string name;
};

struct ValidatedInput {
    std::string email;
    int age;
    std::string name;
};

struct UserProfile {
    std::string email;
    int age;
    std::string display_name;
    std::string tier;
};

// =============================================================
// Pipeline stages — each returns expected
// =============================================================

// Stage 1: Validate email
auto validate_email(RawInput input) -> std::expected<RawInput, ValidationError> {
    if (input.email.empty())
        return std::unexpected(ValidationError{"email", "cannot be empty"});
    if (input.email.find('@') == std::string::npos)
        return std::unexpected(ValidationError{"email", "must contain @"});
    // Normalize to lowercase
    std::transform(input.email.begin(), input.email.end(),
                   input.email.begin(), ::tolower);
    return input;
}

// Stage 2: Validate and parse age
auto validate_age(RawInput input) -> std::expected<ValidatedInput, ValidationError> {
    int age = 0;
    try {
        age = std::stoi(input.age_str);
    } catch (...) {
        return std::unexpected(ValidationError{"age", "not a valid number"});
    }
    if (age < 0 || age > 150)
        return std::unexpected(ValidationError{"age", "must be 0-150"});

    return ValidatedInput{input.email, age, input.name};
}

// Stage 3: Validate name
auto validate_name(ValidatedInput input) -> std::expected<ValidatedInput, ValidationError> {
    if (input.name.size() < 2)
        return std::unexpected(ValidationError{"name", "too short"});
    if (input.name.size() > 100)
        return std::unexpected(ValidationError{"name", "too long"});
    return input;
}

// Stage 4: Build profile (processing stage — different error type)
auto build_profile(ValidatedInput input) -> std::expected<UserProfile, ProcessingError> {
    std::string display = input.name;
    display[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(display[0])));

    std::string tier = (input.age >= 65) ? "senior" :
                       (input.age >= 18) ? "standard" : "junior";

    return UserProfile{input.email, input.age, display, tier};
}

// Stage 5: Persist (simulated)
auto persist_profile(UserProfile profile) -> std::expected<UserProfile, ProcessingError> {
    // Simulate persistence check
    if (profile.email == "banned@evil.com")
        return std::unexpected(ProcessingError{"persist", "email is banned"});
    std::cout << "  [DB] Saved: " << profile.display_name
              << " <" << profile.email << "> tier=" << profile.tier << "\n";
    return profile;
}

// =============================================================
// Composed pipeline using railway-oriented chaining
// =============================================================
auto process_registration(RawInput input) -> std::expected<UserProfile, PipelineError> {
    // Validation stages (ValidationError track)
    auto validated = validate_email(std::move(input))
        .and_then(validate_age)
        .and_then(validate_name);

    // Convert error type at the boundary: ValidationError -> PipelineError
    if (!validated)
        return std::unexpected(PipelineError::from(validated.error()));

    // Processing stages (ProcessingError track)
    return build_profile(std::move(*validated))
        .and_then(persist_profile)
        .transform_error([](ProcessingError e) {
            return PipelineError::from(e);
        });
}

// =============================================================
// Alternative: fully chained with transform_error at each boundary
// =============================================================
auto process_v2(RawInput input) -> std::expected<std::string, PipelineError> {
    return validate_email(std::move(input))
        .and_then(validate_age)
        .and_then(validate_name)
        .transform_error([](ValidationError e) { return PipelineError::from(e); })
        .and_then([](ValidatedInput vi) -> std::expected<UserProfile, PipelineError> {
            return build_profile(std::move(vi))
                .transform_error([](ProcessingError e) { return PipelineError::from(e); });
        })
        .and_then([](UserProfile p) -> std::expected<UserProfile, PipelineError> {
            return persist_profile(std::move(p))
                .transform_error([](ProcessingError e) { return PipelineError::from(e); });
        })
        .transform([](const UserProfile& p) {
            return "Welcome, " + p.display_name + "! Tier: " + p.tier;
        });
}

int main() {
    std::vector<RawInput> registrations = {
        {"Alice@Example.COM", "30",  "alice"},       // valid
        {"",                  "25",  "bob"},          // empty email
        {"charlie@test.com",  "abc", "charlie"},      // bad age
        {"dave@test.com",     "25",  "d"},            // name too short
        {"banned@evil.com",   "40",  "mallory"},      // banned
        {"eve@good.com",      "70",  "eve"},          // senior tier
    };

    for (const auto& reg : registrations) {
        std::cout << "Processing: " << reg.name << " <" << reg.email << ">\n";
        auto result = process_v2(reg);
        if (result) {
            std::cout << "  SUCCESS: " << *result << "\n";
        } else {
            std::cout << "  FAILED:  " << result.error() << "\n";
        }
        std::cout << "\n";
    }

    return 0;
}
```

**Railway-oriented programming concepts:**
- **Success track**: `and_then` / `transform` — data flows through each stage.
- **Error track**: once an error occurs, all subsequent `and_then`/`transform` calls are skipped.
- **Track switch**: `or_else` recovers from error back to success; errors switch to error track.
- **Error type conversion**: `transform_error` at stage boundaries adapts error types.'''),

    ("cpp_deep/custom_exception_hierarchy", r'''Design a proper custom exception hierarchy for a database library, showing best practices for what() messages, error codes, and inheritance.''', r'''<think>
A well-designed exception hierarchy for a database library should:
1. Inherit from std::exception (or its subclasses).
2. Have a base DatabaseException with common info (what, error code, context).
3. Specific exceptions for different failure modes.
4. Store the what() message in a std::string member (not construct on the fly).
5. Support nested exceptions for wrapping lower-level errors.
6. Be nothrow-copyable if possible.
7. Include source location for debugging (C++20 source_location).

Hierarchy:
- DatabaseException (base)
  - ConnectionException (can't connect, timeout, auth)
  - QueryException (syntax error, constraint violation)
  - TransactionException (deadlock, serialization failure)
  - DataException (type mismatch, null violation)

I should include error codes, context (query text, connection string), and chaining.
</think>

A well-designed custom exception hierarchy for a database library:

```cpp
#include <exception>
#include <iostream>
#include <memory>
#include <sstream>
#include <source_location>
#include <string>
#include <utility>

// =============================================================
// Error codes — machine-readable, stable across versions
// =============================================================
enum class DbErrorCode {
    unknown = 0,
    // Connection
    connection_refused = 1000,
    connection_timeout,
    auth_failed,
    connection_lost,
    // Query
    syntax_error = 2000,
    table_not_found,
    column_not_found,
    constraint_violation,
    // Transaction
    deadlock = 3000,
    serialization_failure,
    lock_timeout,
    // Data
    type_mismatch = 4000,
    null_violation,
    value_out_of_range,
};

const char* error_code_name(DbErrorCode code) {
    switch (code) {
        case DbErrorCode::unknown:               return "UNKNOWN";
        case DbErrorCode::connection_refused:     return "CONNECTION_REFUSED";
        case DbErrorCode::connection_timeout:     return "CONNECTION_TIMEOUT";
        case DbErrorCode::auth_failed:            return "AUTH_FAILED";
        case DbErrorCode::connection_lost:        return "CONNECTION_LOST";
        case DbErrorCode::syntax_error:           return "SYNTAX_ERROR";
        case DbErrorCode::table_not_found:        return "TABLE_NOT_FOUND";
        case DbErrorCode::column_not_found:       return "COLUMN_NOT_FOUND";
        case DbErrorCode::constraint_violation:   return "CONSTRAINT_VIOLATION";
        case DbErrorCode::deadlock:               return "DEADLOCK";
        case DbErrorCode::serialization_failure:  return "SERIALIZATION_FAILURE";
        case DbErrorCode::lock_timeout:           return "LOCK_TIMEOUT";
        case DbErrorCode::type_mismatch:          return "TYPE_MISMATCH";
        case DbErrorCode::null_violation:          return "NULL_VIOLATION";
        case DbErrorCode::value_out_of_range:     return "VALUE_OUT_OF_RANGE";
    }
    return "UNKNOWN";
}

// =============================================================
// Base exception — stores message, code, and source location
// =============================================================
class DatabaseException : public std::exception {
    std::string message_;
    DbErrorCode code_;
    std::string location_;
    std::string full_what_;    // pre-built for what() — avoids allocation in what()

    void build_what() {
        std::ostringstream oss;
        oss << "[" << error_code_name(code_) << "] " << message_;
        if (!location_.empty()) oss << " (at " << location_ << ")";
        full_what_ = oss.str();
    }

public:
    DatabaseException(std::string msg, DbErrorCode code,
                      std::source_location loc = std::source_location::current())
        : message_(std::move(msg))
        , code_(code)
        , location_(std::string(loc.file_name()) + ":" + std::to_string(loc.line()))
    {
        build_what();
    }

    const char* what() const noexcept override { return full_what_.c_str(); }
    DbErrorCode code() const noexcept { return code_; }
    const std::string& message() const noexcept { return message_; }
    const std::string& location() const noexcept { return location_; }
};

// =============================================================
// Specific exception types with context
// =============================================================
class ConnectionException : public DatabaseException {
    std::string host_;
    int port_;
public:
    ConnectionException(std::string msg, DbErrorCode code,
                        std::string host, int port,
                        std::source_location loc = std::source_location::current())
        : DatabaseException(std::move(msg) + " [" + host + ":" + std::to_string(port) + "]",
                            code, loc)
        , host_(std::move(host)), port_(port) {}

    const std::string& host() const noexcept { return host_; }
    int port() const noexcept { return port_; }
};

class QueryException : public DatabaseException {
    std::string query_;
    int position_ = -1;   // error position in query
public:
    QueryException(std::string msg, DbErrorCode code, std::string query,
                   int pos = -1,
                   std::source_location loc = std::source_location::current())
        : DatabaseException(std::move(msg), code, loc)
        , query_(std::move(query)), position_(pos) {}

    const std::string& query() const noexcept { return query_; }
    int error_position() const noexcept { return position_; }
};

class TransactionException : public DatabaseException {
    std::string tx_id_;
public:
    TransactionException(std::string msg, DbErrorCode code, std::string tx_id,
                         std::source_location loc = std::source_location::current())
        : DatabaseException(std::move(msg), code, loc)
        , tx_id_(std::move(tx_id)) {}

    const std::string& transaction_id() const noexcept { return tx_id_; }
    bool is_retryable() const noexcept {
        return code() == DbErrorCode::deadlock
            || code() == DbErrorCode::serialization_failure;
    }
};

// =============================================================
// Exception chaining with std::nested_exception
// =============================================================
[[noreturn]] void throw_with_context(const std::string& context, DbErrorCode code) {
    // Wraps the current exception as a nested exception
    std::throw_with_nested(DatabaseException(context, code));
}

void print_exception_chain(const std::exception& e, int depth = 0) {
    std::cerr << std::string(depth * 2, ' ') << e.what() << "\n";
    try {
        std::rethrow_if_nested(e);
    } catch (const std::exception& nested) {
        print_exception_chain(nested, depth + 1);
    }
}

// =============================================================
// Usage: simulated database operations
// =============================================================
void connect(const std::string& host, int port) {
    throw ConnectionException("Connection timed out after 5000ms",
                              DbErrorCode::connection_timeout, host, port);
}

void execute_query(const std::string& sql) {
    throw QueryException("Unknown column 'username'",
                         DbErrorCode::column_not_found, sql, 14);
}

void run_transaction() {
    throw TransactionException("Deadlock detected",
                               DbErrorCode::deadlock, "tx_a1b2c3");
}

int main() {
    // --- Catch specific exception types ---
    std::cout << "=== Connection error ===\n";
    try {
        connect("db.example.com", 5432);
    } catch (const ConnectionException& e) {
        std::cerr << "Connection to " << e.host() << ":" << e.port() << " failed\n";
        std::cerr << "  " << e.what() << "\n";
        std::cerr << "  Code: " << static_cast<int>(e.code()) << "\n";
    }

    // --- Query error with context ---
    std::cout << "\n=== Query error ===\n";
    try {
        execute_query("SELECT username FROM users");
    } catch (const QueryException& e) {
        std::cerr << e.what() << "\n";
        std::cerr << "  Query: " << e.query() << "\n";
        if (e.error_position() >= 0) {
            std::cerr << "  " << std::string(e.error_position() + 9, ' ') << "^\n";
        }
    }

    // --- Retryable transaction error ---
    std::cout << "\n=== Transaction error ===\n";
    try {
        run_transaction();
    } catch (const TransactionException& e) {
        std::cerr << e.what() << "\n";
        std::cerr << "  TX: " << e.transaction_id() << "\n";
        if (e.is_retryable()) {
            std::cerr << "  (retryable — will retry)\n";
        }
    }

    // --- Nested exception chain ---
    std::cout << "\n=== Exception chain ===\n";
    try {
        try {
            connect("db.example.com", 5432);
        } catch (...) {
            throw_with_context("Failed to initialize user service",
                               DbErrorCode::unknown);
        }
    } catch (const std::exception& e) {
        print_exception_chain(e);
    }

    // --- Catch base type for generic handling ---
    std::cout << "\n=== Generic handler ===\n";
    try {
        execute_query("DROP TABLE students");
    } catch (const DatabaseException& e) {
        std::cerr << "DB Error [" << error_code_name(e.code()) << "]: "
                  << e.message() << "\n";
    }

    return 0;
}
```

**Design principles:**
- **Inherit from `std::exception`** — ensures compatibility with generic catch handlers.
- **Pre-build `what()` string** in constructor — `what()` is `noexcept`, so it cannot allocate.
- **Error codes** for programmatic handling; messages for humans.
- **Context-rich subtypes** carry query text, host info, transaction IDs.
- **`is_retryable()`** on transaction exceptions — policy method for retry logic.
- **`std::source_location`** captures file and line automatically.'''),

    ("cpp_deep/stack_unwinding_destructors", r'''Explain stack unwinding in C++ and why destructors must not throw. Show what happens during unwinding and how to handle cleanup errors safely.''', r'''<think>
Stack unwinding is the process of destroying local objects when an exception
propagates up the call stack. Each stack frame's local objects are destroyed
in reverse construction order.

If a destructor throws during unwinding, std::terminate() is called — the program
is killed. This is because two exceptions cannot propagate simultaneously.

Key points:
1. Destructors are implicitly noexcept since C++11.
2. If you throw in a destructor, std::terminate is called if another exception is active.
3. You can check std::uncaught_exceptions() (C++17) to detect unwinding.
4. Cleanup errors in destructors should be swallowed, logged, or stored.
5. The "scope guard" pattern handles cleanup safely.

I'll show the unwinding process, the double-exception problem, and safe patterns.
</think>

Stack unwinding and destructor safety during exception propagation:

```cpp
#include <exception>
#include <iostream>
#include <string>
#include <vector>
#include <functional>

// =============================================================
// Demonstrating stack unwinding order
// =============================================================
struct Tracker {
    std::string name;
    Tracker(std::string n) : name(std::move(n)) {
        std::cout << "  CONSTRUCT: " << name << "\n";
    }
    ~Tracker() noexcept {
        std::cout << "  DESTROY:   " << name << " (uncaught="
                  << std::uncaught_exceptions() << ")\n";
    }
};

void inner() {
    Tracker t3("inner_obj");
    std::cout << "  About to throw...\n";
    throw std::runtime_error("something went wrong");
    // t3 destroyed here during unwinding
}

void middle() {
    Tracker t2("middle_obj");
    inner();
    // t2 destroyed here during unwinding (after t3)
}

void outer() {
    Tracker t1("outer_obj");
    middle();
    // t1 destroyed here during unwinding (after t2)
}

// =============================================================
// Problem: destructor that throws during unwinding = terminate
// =============================================================
struct BadResource {
    ~BadResource() noexcept(false) {   // explicitly non-noexcept (BAD!)
        // If we throw during unwinding, std::terminate() is called
        // throw std::runtime_error("cleanup failed");  // FATAL!
        std::cout << "  [BadResource] destructor called safely\n";
    }
};

// =============================================================
// Solution 1: Swallow errors in destructors, log them
// =============================================================
class FileHandle {
    std::string path_;
    bool open_ = true;

    void do_close() {
        // Simulate close that might fail
        if (path_ == "/bad/path") {
            throw std::runtime_error("close() failed: I/O error");
        }
        open_ = false;
    }

public:
    FileHandle(std::string path) : path_(std::move(path)) {}

    // Explicit close — CAN throw (caller handles it)
    void close() {
        do_close();
    }

    // Destructor — MUST NOT throw
    ~FileHandle() noexcept {
        if (!open_) return;
        try {
            do_close();
        } catch (const std::exception& e) {
            // Swallow the error — log it, don't propagate
            std::cerr << "  [WARNING] destructor cleanup failed: " << e.what() << "\n";
        }
    }
};

// =============================================================
// Solution 2: Scope guard for safe cleanup
// =============================================================
class ScopeGuard {
    std::function<void()> cleanup_;
    bool dismissed_ = false;

public:
    explicit ScopeGuard(std::function<void()> fn) : cleanup_(std::move(fn)) {}

    void dismiss() noexcept { dismissed_ = true; }

    ~ScopeGuard() noexcept {
        if (!dismissed_) {
            try {
                cleanup_();
            } catch (...) {
                // Swallow — we're in a destructor
            }
        }
    }

    ScopeGuard(const ScopeGuard&) = delete;
    ScopeGuard& operator=(const ScopeGuard&) = delete;
};

// =============================================================
// Solution 3: C++17 uncaught_exceptions() for conditional behavior
// =============================================================
class Transaction {
    std::string name_;
    int uncaught_on_entry_;   // snapshot at construction

public:
    Transaction(std::string name)
        : name_(std::move(name))
        , uncaught_on_entry_(std::uncaught_exceptions())
    {
        std::cout << "  BEGIN " << name_ << "\n";
    }

    ~Transaction() noexcept {
        if (std::uncaught_exceptions() > uncaught_on_entry_) {
            // New exception since construction — we're unwinding
            std::cout << "  ROLLBACK " << name_ << " (unwinding detected)\n";
        } else {
            // Normal exit — commit
            std::cout << "  COMMIT " << name_ << "\n";
        }
    }
};

void successful_work() {
    Transaction tx("tx1");
    std::cout << "  doing work...\n";
    // tx commits on normal exit
}

void failing_work() {
    Transaction tx("tx2");
    std::cout << "  doing work...\n";
    throw std::runtime_error("work failed");
    // tx rolls back during unwinding
}

int main() {
    // --- Stack unwinding order ---
    std::cout << "=== Stack unwinding order ===\n";
    try {
        outer();
    } catch (const std::exception& e) {
        std::cout << "Caught: " << e.what() << "\n\n";
    }

    // --- Safe destructor with explicit close ---
    std::cout << "=== FileHandle cleanup ===\n";
    {
        FileHandle good("/tmp/good.txt");
        // Destructor closes safely
    }
    {
        FileHandle bad("/bad/path");
        // Destructor catches and logs the error
    }

    // --- Scope guard ---
    std::cout << "\n=== Scope guard ===\n";
    try {
        int* resource = new int(42);
        ScopeGuard guard([&]() {
            std::cout << "  Cleaning up resource\n";
            delete resource;
        });

        // Simulate work that might throw
        throw std::runtime_error("oops");

        guard.dismiss();   // only reached on success
    } catch (...) {
        std::cout << "  Exception caught, resource was cleaned up\n";
    }

    // --- uncaught_exceptions() for commit/rollback ---
    std::cout << "\n=== Transaction auto-commit/rollback ===\n";
    successful_work();
    try {
        failing_work();
    } catch (...) {
        std::cout << "  Exception handled\n";
    }

    return 0;
}
```

**Rules for destructors:**
1. Destructors are **implicitly `noexcept`** since C++11.
2. If a destructor throws during stack unwinding, **`std::terminate()` is called**.
3. Offer an explicit `close()`/`flush()` method that CAN throw — let callers handle errors.
4. The destructor is the last resort: **catch and swallow** (or log) errors.
5. Use `std::uncaught_exceptions()` (C++17) to detect unwinding and choose commit vs rollback.'''),

    ("cpp_deep/nested_exception_chaining", r'''Show how std::nested_exception enables exception chaining in C++, preserving the full error context from low-level to high-level failures.''', r'''<think>
std::nested_exception allows wrapping a caught exception inside a new one,
creating a chain of exceptions. This is essential for layered architectures
where low-level errors need context added at each layer.

Key API:
- std::throw_with_nested(new_exception): throws new_exception with current exception nested
- std::rethrow_if_nested(e): rethrows the nested exception if present
- std::nested_exception is a mixin — it captures current_exception() at construction

I should show:
1. Basic nesting — wrap a low-level exception in a high-level one.
2. Multi-level chains — 3+ levels deep.
3. Walking the chain to print full context.
4. Combining with custom exception types.
</think>

`std::nested_exception` creates exception chains, preserving context across layers:

```cpp
#include <exception>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

// =============================================================
// Custom exception hierarchy (plays well with nesting)
// =============================================================
class AppException : public std::runtime_error {
    int code_;
public:
    AppException(const std::string& msg, int code)
        : std::runtime_error(msg), code_(code) {}
    int code() const noexcept { return code_; }
};

class NetworkException : public AppException {
public:
    NetworkException(const std::string& msg, int code = 1000)
        : AppException(msg, code) {}
};

class ServiceException : public AppException {
public:
    ServiceException(const std::string& msg, int code = 2000)
        : AppException(msg, code) {}
};

class ApplicationException : public AppException {
public:
    ApplicationException(const std::string& msg, int code = 3000)
        : AppException(msg, code) {}
};

// =============================================================
// Utility: walk and print the full exception chain
// =============================================================
void print_exception_chain(const std::exception& e, int depth = 0) {
    std::string indent(depth * 2, ' ');
    std::cerr << indent << "Exception: " << e.what();

    if (auto* app = dynamic_cast<const AppException*>(&e)) {
        std::cerr << " (code=" << app->code() << ")";
    }
    std::cerr << "\n";

    try {
        std::rethrow_if_nested(e);
    } catch (const std::exception& nested) {
        std::cerr << indent << "Caused by:\n";
        print_exception_chain(nested, depth + 1);
    } catch (...) {
        std::cerr << indent << "Caused by: (unknown exception)\n";
    }
}

// Collect chain into a vector of strings
std::vector<std::string> collect_chain(const std::exception& e) {
    std::vector<std::string> chain;
    chain.push_back(e.what());
    try {
        std::rethrow_if_nested(e);
    } catch (const std::exception& nested) {
        auto inner = collect_chain(nested);
        chain.insert(chain.end(), inner.begin(), inner.end());
    } catch (...) {
        chain.push_back("(unknown)");
    }
    return chain;
}

// =============================================================
// Layered architecture — each layer adds context
// =============================================================

// Layer 1: Low-level network
void tcp_connect(const std::string& host, int port) {
    throw NetworkException("Connection refused to " + host + ":" + std::to_string(port), 1001);
}

// Layer 2: Service client — wraps network errors
void fetch_user_data(int user_id) {
    try {
        tcp_connect("api.example.com", 443);
    } catch (...) {
        // Wrap the current exception (NetworkException) inside ServiceException
        std::throw_with_nested(
            ServiceException("Failed to fetch user " + std::to_string(user_id), 2001));
    }
}

// Layer 3: Application logic — wraps service errors
void handle_login(const std::string& username) {
    try {
        fetch_user_data(42);
    } catch (...) {
        std::throw_with_nested(
            ApplicationException("Login failed for user '" + username + "'", 3001));
    }
}

// =============================================================
// Recovery: inspect the chain to decide what to do
// =============================================================
bool is_network_error(const std::exception& e) {
    if (dynamic_cast<const NetworkException*>(&e)) return true;
    try {
        std::rethrow_if_nested(e);
    } catch (const std::exception& nested) {
        return is_network_error(nested);
    } catch (...) {}
    return false;
}

int find_root_error_code(const std::exception& e) {
    int code = 0;
    if (auto* app = dynamic_cast<const AppException*>(&e)) {
        code = app->code();
    }
    try {
        std::rethrow_if_nested(e);
    } catch (const std::exception& nested) {
        return find_root_error_code(nested);   // dig deeper
    } catch (...) {}
    return code;   // return deepest code found
}

int main() {
    // --- Full chain ---
    std::cout << "=== Exception chain ===\n";
    try {
        handle_login("alice");
    } catch (const std::exception& e) {
        print_exception_chain(e);

        std::cout << "\n--- Chain as list ---\n";
        auto chain = collect_chain(e);
        for (std::size_t i = 0; i < chain.size(); ++i) {
            std::cout << "  [" << i << "] " << chain[i] << "\n";
        }

        std::cout << "\n--- Analysis ---\n";
        std::cout << "Is network error: " << is_network_error(e) << "\n";
        std::cout << "Root error code:  " << find_root_error_code(e) << "\n";
    }

    // --- Selective recovery ---
    std::cout << "\n=== Selective recovery ===\n";
    try {
        handle_login("bob");
    } catch (const ApplicationException& e) {
        if (is_network_error(e)) {
            std::cout << "Network issue detected — will retry\n";
        } else {
            std::cout << "Non-network error — escalating\n";
            throw;
        }
    }

    return 0;
}
```

**Key API:**
- `std::throw_with_nested(e)`: throws `e` with the **current exception** (`std::current_exception()`) captured inside it.
- `std::rethrow_if_nested(e)`: rethrows the nested exception if `e` has one; no-op otherwise.
- The chain can be walked recursively to find root causes or specific error types.
- Each layer adds its own context without losing the original error information.'''),

    ("cpp_deep/error_code_error_category", r'''Show how to use std::error_code and std::error_category to build a proper system-compatible error reporting system in C++.''', r'''<think>
The <system_error> framework provides a standardized way to handle error codes:
- std::error_code: concrete error code + category pair
- std::error_condition: portable error condition (for comparison across categories)
- std::error_category: defines a domain of error codes
- std::system_error: exception wrapping an error_code

To create a custom error domain:
1. Define an enum for error codes
2. Create an error_category subclass
3. Specialize is_error_code_enum
4. Provide make_error_code overload

I'll build a complete example with a custom HTTP error domain that integrates
with the system error codes for comparison.
</think>

Building a proper error reporting system with `std::error_code` and custom categories:

```cpp
#include <iostream>
#include <string>
#include <system_error>

// =============================================================
// Step 1: Define error codes as an enum
// =============================================================
enum class HttpError {
    ok = 0,
    bad_request = 400,
    unauthorized = 401,
    forbidden = 403,
    not_found = 404,
    timeout = 408,
    internal_error = 500,
    bad_gateway = 502,
    service_unavailable = 503,
};

// =============================================================
// Step 2: Create a custom error_category
// =============================================================
class HttpErrorCategory : public std::error_category {
public:
    const char* name() const noexcept override {
        return "http";
    }

    std::string message(int ev) const override {
        switch (static_cast<HttpError>(ev)) {
            case HttpError::ok:                  return "OK";
            case HttpError::bad_request:         return "Bad Request";
            case HttpError::unauthorized:        return "Unauthorized";
            case HttpError::forbidden:           return "Forbidden";
            case HttpError::not_found:           return "Not Found";
            case HttpError::timeout:             return "Request Timeout";
            case HttpError::internal_error:      return "Internal Server Error";
            case HttpError::bad_gateway:         return "Bad Gateway";
            case HttpError::service_unavailable: return "Service Unavailable";
            default:                             return "Unknown HTTP error";
        }
    }

    // Map to portable error_conditions for cross-category comparison
    std::error_condition default_error_condition(int ev) const noexcept override {
        switch (static_cast<HttpError>(ev)) {
            case HttpError::unauthorized:
            case HttpError::forbidden:
                return std::errc::permission_denied;
            case HttpError::not_found:
                return std::errc::no_such_file_or_directory;
            case HttpError::timeout:
                return std::errc::timed_out;
            default:
                return std::error_condition(ev, *this);
        }
    }
};

// Singleton category instance
const HttpErrorCategory& http_category() {
    static HttpErrorCategory instance;
    return instance;
}

// =============================================================
// Step 3: Enable implicit conversion enum -> error_code
// =============================================================
namespace std {
    template<> struct is_error_code_enum<HttpError> : true_type {};
}

std::error_code make_error_code(HttpError e) {
    return {static_cast<int>(e), http_category()};
}

// =============================================================
// Second custom category: application-level errors
// =============================================================
enum class AppError {
    ok = 0,
    invalid_input = 1,
    rate_limited = 2,
    dependency_failed = 3,
    cache_miss = 4,
};

class AppErrorCategory : public std::error_category {
public:
    const char* name() const noexcept override { return "app"; }

    std::string message(int ev) const override {
        switch (static_cast<AppError>(ev)) {
            case AppError::ok:               return "OK";
            case AppError::invalid_input:    return "Invalid input";
            case AppError::rate_limited:     return "Rate limited";
            case AppError::dependency_failed: return "Dependency failed";
            case AppError::cache_miss:       return "Cache miss";
            default:                         return "Unknown app error";
        }
    }
};

const AppErrorCategory& app_category() {
    static AppErrorCategory instance;
    return instance;
}

namespace std {
    template<> struct is_error_code_enum<AppError> : true_type {};
}

std::error_code make_error_code(AppError e) {
    return {static_cast<int>(e), app_category()};
}

// =============================================================
// Usage: functions returning error_code
// =============================================================
std::error_code fetch_resource(const std::string& url) {
    if (url.empty()) return HttpError::bad_request;
    if (url.find("/secret") != std::string::npos) return HttpError::forbidden;
    if (url.find("/missing") != std::string::npos) return HttpError::not_found;
    return {};   // success = default-constructed error_code
}

std::error_code process_request(const std::string& url) {
    auto ec = fetch_resource(url);
    if (ec) {
        // Wrap HTTP error in app error
        return AppError::dependency_failed;
    }
    return {};
}

// Throw as exception when needed
void fetch_or_throw(const std::string& url) {
    auto ec = fetch_resource(url);
    if (ec) {
        throw std::system_error(ec, "Failed to fetch " + url);
    }
}

int main() {
    // --- Basic error_code usage ---
    std::error_code ec = HttpError::not_found;
    std::cout << "Category: " << ec.category().name() << "\n";
    std::cout << "Value:    " << ec.value() << "\n";
    std::cout << "Message:  " << ec.message() << "\n";
    std::cout << "Bool:     " << static_cast<bool>(ec) << "\n\n";

    // --- Function returning error codes ---
    for (const auto& url : {"/api/data", "/secret/keys", "/missing/page", ""}) {
        auto err = fetch_resource(url);
        std::cout << "fetch(\"" << url << "\"): ";
        if (err) {
            std::cout << err.category().name() << "::" << err.message()
                      << " (" << err.value() << ")\n";
        } else {
            std::cout << "OK\n";
        }
    }

    // --- Cross-category comparison via error_condition ---
    std::cout << "\n=== Error condition comparison ===\n";
    std::error_code http_forbidden = HttpError::forbidden;
    std::error_code sys_permission = std::make_error_code(std::errc::permission_denied);

    // Different categories, but same portable condition
    std::cout << "HTTP forbidden == permission_denied: "
              << (http_forbidden == std::errc::permission_denied) << "\n";  // 1
    std::cout << "Different categories: "
              << (&http_forbidden.category() != &sys_permission.category()) << "\n"; // 1

    // --- Throw as system_error ---
    std::cout << "\n=== system_error exception ===\n";
    try {
        fetch_or_throw("/missing/page");
    } catch (const std::system_error& e) {
        std::cout << "Caught: " << e.what() << "\n";
        std::cout << "Code:   " << e.code() << " [" << e.code().category().name() << "]\n";
    }

    return 0;
}
```

**Architecture of `<system_error>`:**
- **`error_code`**: concrete error (specific category + integer value). Used at API boundaries.
- **`error_condition`**: portable condition for comparison. Maps across categories (e.g., HTTP 403 == `permission_denied`).
- **`error_category`**: defines a domain. Override `name()`, `message()`, and `default_error_condition()`.
- **`system_error`**: exception class wrapping an `error_code` for when you want to throw.'''),

    ("cpp_deep/structured_bindings_custom", r'''Show how structured bindings work with custom types in C++17, including the three protocols: arrays, tuple-like, and public members.''', r'''<think>
Structured bindings in C++17 allow `auto [a, b, c] = expr;` syntax.
Three protocols are supported:
1. Arrays: built-in arrays and std::array.
2. Tuple-like: types with std::tuple_size, std::tuple_element, and get<N>().
3. Public data members: structs/classes with all public non-static members.

For custom types to work with structured bindings via the tuple-like protocol,
you need to specialize tuple_size, tuple_element, and provide get<N>() either
as a member function or as a free function found via ADL.

I should show all three protocols with practical examples.
</think>

Structured bindings in C++17 support three protocols for custom types:

```cpp
#include <iostream>
#include <string>
#include <tuple>
#include <utility>

// =============================================================
// Protocol 1: Public data members (simplest)
// Works automatically for aggregates with all-public members
// =============================================================
struct Point3D {
    double x, y, z;
};

struct HttpResponse {
    int status;
    std::string body;
    bool cached;
};

// =============================================================
// Protocol 2: Tuple-like (for types with private members)
// Requires: std::tuple_size, std::tuple_element, get<N>()
// =============================================================
class Color {
    uint8_t r_, g_, b_, a_;
public:
    Color(uint8_t r, uint8_t g, uint8_t b, uint8_t a = 255)
        : r_(r), g_(g), b_(b), a_(a) {}

    // Member get<N>() — one approach
    template <std::size_t N>
    auto get() const {
        if constexpr (N == 0) return r_;
        else if constexpr (N == 1) return g_;
        else if constexpr (N == 2) return b_;
        else if constexpr (N == 3) return a_;
    }

    // Mutable access version
    template <std::size_t N>
    auto& get() {
        if constexpr (N == 0) return r_;
        else if constexpr (N == 1) return g_;
        else if constexpr (N == 2) return b_;
        else if constexpr (N == 3) return a_;
    }
};

// Specialize std::tuple_size and std::tuple_element
namespace std {
    template<> struct tuple_size<Color> : integral_constant<size_t, 4> {};

    template<size_t N> struct tuple_element<N, Color> {
        using type = uint8_t;
    };
}

// =============================================================
// Protocol 2 variant: free function get<N>() via ADL
// =============================================================
class Matrix2x2 {
    double data_[4];
public:
    Matrix2x2(double a, double b, double c, double d)
        : data_{a, b, c, d} {}

    double operator()(int r, int c) const { return data_[r * 2 + c]; }
    double& operator()(int r, int c) { return data_[r * 2 + c]; }

    // Friend get<N> for ADL
    template <std::size_t N>
    friend double get(const Matrix2x2& m) { return m.data_[N]; }

    template <std::size_t N>
    friend double& get(Matrix2x2& m) { return m.data_[N]; }
};

namespace std {
    template<> struct tuple_size<Matrix2x2> : integral_constant<size_t, 4> {};
    template<size_t N> struct tuple_element<N, Matrix2x2> { using type = double; };
}

// =============================================================
// Protocol 2: Mixed types (different tuple_element for each N)
// =============================================================
class NamedValue {
    std::string name_;
    double value_;
    bool valid_;
public:
    NamedValue(std::string n, double v, bool ok)
        : name_(std::move(n)), value_(v), valid_(ok) {}

    template <std::size_t N>
    decltype(auto) get() const {
        if constexpr (N == 0) return (name_);     // parentheses for reference
        else if constexpr (N == 1) return value_;
        else if constexpr (N == 2) return valid_;
    }
};

namespace std {
    template<> struct tuple_size<NamedValue> : integral_constant<size_t, 3> {};
    template<> struct tuple_element<0, NamedValue> { using type = const std::string&; };
    template<> struct tuple_element<1, NamedValue> { using type = double; };
    template<> struct tuple_element<2, NamedValue> { using type = bool; };
}

// =============================================================
// Protocol 3: Arrays (built-in)
// =============================================================

int main() {
    // --- Protocol 1: Public members ---
    std::cout << "=== Public members ===\n";
    Point3D p{1.0, 2.0, 3.0};
    auto [x, y, z] = p;
    std::cout << "Point: " << x << ", " << y << ", " << z << "\n";

    auto [status, body, cached] = HttpResponse{200, "hello", true};
    std::cout << "HTTP " << status << ": " << body
              << (cached ? " [cached]" : "") << "\n";

    // --- Protocol 2: Tuple-like (member get) ---
    std::cout << "\n=== Tuple-like (Color) ===\n";
    Color red{255, 0, 0, 128};
    auto [r, g, b, a] = red;
    std::cout << "RGBA: " << (int)r << "," << (int)g << ","
              << (int)b << "," << (int)a << "\n";

    // Mutable binding
    auto& [r2, g2, b2, a2] = red;
    g2 = 128;  // modifies red directly
    std::cout << "After modify: " << (int)red.get<1>() << "\n";

    // --- Protocol 2: Free function get (Matrix) ---
    std::cout << "\n=== Tuple-like (Matrix2x2) ===\n";
    Matrix2x2 m{1.0, 2.0, 3.0, 4.0};
    auto [m00, m01, m10, m11] = m;
    std::cout << "| " << m00 << " " << m01 << " |\n"
              << "| " << m10 << " " << m11 << " |\n";

    // --- Protocol 2: Mixed types ---
    std::cout << "\n=== Mixed types (NamedValue) ===\n";
    NamedValue nv{"temperature", 23.5, true};
    auto [name, value, valid] = nv;
    std::cout << name << " = " << value << (valid ? " (valid)" : " (invalid)") << "\n";

    // --- Protocol 3: Arrays ---
    std::cout << "\n=== Arrays ===\n";
    int arr[] = {10, 20, 30};
    auto [a1, a2, a3] = arr;
    std::cout << "Array: " << a1 << ", " << a2 << ", " << a3 << "\n";

    // --- With standard library types ---
    std::cout << "\n=== Standard library ===\n";
    std::pair<std::string, int> kv{"count", 42};
    auto [key, val] = kv;
    std::cout << key << " = " << val << "\n";

    auto [first, second, third] = std::tuple{3.14, "pi", true};
    std::cout << first << ", " << second << ", " << third << "\n";

    return 0;
}
```

**Three protocols for structured bindings:**
| Protocol | Requirements | Example |
|---|---|---|
| Public members | All non-static members are public | `struct { int a; double b; };` |
| Tuple-like | `std::tuple_size`, `std::tuple_element`, `get<N>()` | Custom classes with private data |
| Array | C array or `std::array` | `int arr[3]` |

The compiler tries: (1) array, (2) tuple-like, (3) public members.'''),

    ("cpp_deep/designated_initializers", r'''Show designated initializers in C++20 for aggregate types, including rules, restrictions, and practical patterns for configuration objects.''', r'''<think>
Designated initializers in C++20 allow naming members during initialization:
auto cfg = Config{.port = 8080, .host = "localhost"};

Rules and restrictions in C++ (stricter than C):
1. Must be in declaration order.
2. Cannot mix designated and non-designated.
3. Cannot designate nested members directly.
4. Cannot use with non-aggregate types.
5. Omitted members are value-initialized.

I'll show practical patterns for config structs and API options.
</think>

Designated initializers (C++20) enable named initialization for aggregate types:

```cpp
#include <iostream>
#include <optional>
#include <string>
#include <vector>

// =============================================================
// Basic designated initialization
// =============================================================
struct Point {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

struct Color {
    uint8_t r = 0;
    uint8_t g = 0;
    uint8_t b = 0;
    uint8_t a = 255;
};

// =============================================================
// Practical pattern: Configuration objects
// =============================================================
struct ServerConfig {
    std::string host          = "0.0.0.0";
    int port                  = 8080;
    int max_connections       = 100;
    int timeout_ms            = 5000;
    bool enable_tls           = false;
    std::string cert_path     = "";
    int worker_threads        = 4;
    bool enable_compression   = true;
    int max_request_size      = 1024 * 1024;  // 1MB
};

struct LogConfig {
    std::string file_path     = "app.log";
    std::string level         = "info";
    bool console_output       = true;
    int max_file_size_mb      = 100;
    int max_backup_count      = 5;
    bool include_timestamp    = true;
};

// =============================================================
// Pattern: Function options (named parameters)
// =============================================================
struct HttpRequestOptions {
    std::string method           = "GET";
    std::string content_type     = "application/json";
    int timeout_ms               = 30000;
    bool follow_redirects        = true;
    int max_redirects            = 10;
    std::optional<std::string> auth_token = std::nullopt;
    std::vector<std::string> headers = {};
};

struct HttpResponse {
    int status;
    std::string body;
};

HttpResponse http_request(const std::string& url, const HttpRequestOptions& opts = {}) {
    std::cout << opts.method << " " << url << "\n"
              << "  Content-Type: " << opts.content_type << "\n"
              << "  Timeout: " << opts.timeout_ms << "ms\n"
              << "  Follow redirects: " << opts.follow_redirects << "\n";
    if (opts.auth_token)
        std::cout << "  Auth: Bearer " << *opts.auth_token << "\n";
    for (const auto& h : opts.headers)
        std::cout << "  Header: " << h << "\n";

    return {200, "{}"};
}

// =============================================================
// Pattern: Builder-like aggregate with nested configs
// =============================================================
struct RetryPolicy {
    int max_retries     = 3;
    int base_delay_ms   = 100;
    double backoff_mult = 2.0;
};

struct CircuitBreakerConfig {
    int failure_threshold   = 5;
    int reset_timeout_ms    = 30000;
    int half_open_requests  = 1;
};

struct ServiceClientConfig {
    std::string base_url;
    HttpRequestOptions request_opts = {};
    RetryPolicy retry              = {};
    CircuitBreakerConfig breaker   = {};
};

void create_client(const ServiceClientConfig& cfg) {
    std::cout << "\nService client: " << cfg.base_url << "\n"
              << "  Timeout: " << cfg.request_opts.timeout_ms << "ms\n"
              << "  Retries: " << cfg.retry.max_retries << "\n"
              << "  Breaker threshold: " << cfg.breaker.failure_threshold << "\n";
}

int main() {
    // --- Basic: only name what you need ---
    auto origin = Point{};                      // all defaults: {0, 0, 0}
    auto p = Point{.x = 1.0, .z = 3.0};       // y defaults to 0.0
    std::cout << "Point: " << p.x << "," << p.y << "," << p.z << "\n";

    auto red = Color{.r = 255};                 // g=0, b=0, a=255
    auto semi = Color{.r = 0, .g = 128, .b = 255, .a = 128};

    // --- Server config: only override non-defaults ---
    auto server = ServerConfig{
        .port = 443,
        .enable_tls = true,
        .cert_path = "/etc/ssl/cert.pem",
        .worker_threads = 8,
    };
    std::cout << "\nServer: " << server.host << ":" << server.port
              << " (tls=" << server.enable_tls
              << ", workers=" << server.worker_threads << ")\n";

    // --- Named parameters via options struct ---
    std::cout << "\n=== HTTP requests ===\n";

    // Simple GET (all defaults)
    http_request("/api/users");

    std::cout << "\n";

    // Custom POST with auth
    http_request("/api/users", {
        .method = "POST",
        .timeout_ms = 5000,
        .follow_redirects = false,
        .auth_token = "eyJhbGciOi...",
        .headers = {"X-Request-Id: abc123", "X-Trace: true"},
    });

    // --- Nested config ---
    create_client({
        .base_url = "https://api.example.com",
        .request_opts = {
            .timeout_ms = 10000,
            .auth_token = "secret",
        },
        .retry = {
            .max_retries = 5,
            .backoff_mult = 3.0,
        },
        // breaker uses defaults
    });

    // --- RULES (C++20 restrictions) ---
    // 1. Must be in declaration order:
    // Point bad = {.z = 1, .x = 2};       // ERROR: out of order

    // 2. Cannot mix designated and positional:
    // Point bad = {1.0, .z = 3.0};         // ERROR: mixed

    // 3. Omitted members are value-initialized (default member init or zero):
    auto sparse = ServerConfig{.port = 9090};  // everything else = default

    return 0;
}
```

**C++20 designated initializer rules:**
1. Designators must match **declaration order** (unlike C99).
2. Cannot **mix** designated and positional arguments.
3. Omitted members use **default member initializers** (or value-initialize to zero).
4. Only works with **aggregate types** (no user-declared constructors, no virtual functions).
5. Nested aggregates can be initialized with nested `{}` but NOT with nested `.member.sub =` syntax.'''),

    ("cpp_deep/spaceship_operator", r'''Implement the three-way comparison (spaceship operator) for custom types, showing auto-generated operators, custom ordering, and partial ordering.''', r'''<think>
The spaceship operator (<=>) in C++20 enables a single definition that generates
all six comparison operators. The return type determines the ordering:
- std::strong_ordering: total order, substitutable (a == b implies f(a) == f(b))
- std::weak_ordering: total order, not substitutable
- std::partial_ordering: some elements may be incomparable (like NaN)

I should show:
1. Defaulted spaceship — compiler generates everything.
2. Custom spaceship with specific ordering logic.
3. Partial ordering example.
4. Mixed comparisons between different types.
</think>

The three-way comparison operator (`<=>`) in C++20 generates all six comparison operators from one definition:

```cpp
#include <compare>
#include <iostream>
#include <set>
#include <string>
#include <vector>
#include <algorithm>
#include <cmath>

// =============================================================
// 1. Defaulted spaceship: compiler does everything
// =============================================================
struct Point {
    double x;
    double y;
    double z;

    // Compiler generates <=>, ==, !=, <, >, <=, >= for all members
    auto operator<=>(const Point&) const = default;
};

// =============================================================
// 2. Custom strong_ordering (case-insensitive string)
// =============================================================
class CaseInsensitiveString {
    std::string data_;
public:
    CaseInsensitiveString(std::string s) : data_(std::move(s)) {}

    const std::string& str() const { return data_; }

    // Custom spaceship: case-insensitive comparison
    std::strong_ordering operator<=>(const CaseInsensitiveString& other) const {
        auto to_lower = [](char c) -> char {
            return (c >= 'A' && c <= 'Z') ? static_cast<char>(c + 32) : c;
        };

        auto it1 = data_.begin(), it2 = other.data_.begin();
        for (; it1 != data_.end() && it2 != other.data_.end(); ++it1, ++it2) {
            char c1 = to_lower(*it1), c2 = to_lower(*it2);
            if (c1 < c2) return std::strong_ordering::less;
            if (c1 > c2) return std::strong_ordering::greater;
        }
        if (data_.size() < other.data_.size()) return std::strong_ordering::less;
        if (data_.size() > other.data_.size()) return std::strong_ordering::greater;
        return std::strong_ordering::equal;
    }

    // Must define == separately when <=> is custom (not defaulted)
    bool operator==(const CaseInsensitiveString& other) const {
        return (*this <=> other) == 0;
    }
};

// =============================================================
// 3. weak_ordering (version numbers: 1.0.0 == 1.0 but not substitutable)
// =============================================================
struct Version {
    int major = 0;
    int minor = 0;
    int patch = 0;

    std::weak_ordering operator<=>(const Version& other) const {
        // Major is most significant
        if (auto cmp = major <=> other.major; cmp != 0) return cmp;
        if (auto cmp = minor <=> other.minor; cmp != 0) return cmp;
        return patch <=> other.patch;
    }

    bool operator==(const Version& other) const {
        return (*this <=> other) == 0;
    }

    friend std::ostream& operator<<(std::ostream& os, const Version& v) {
        return os << v.major << "." << v.minor << "." << v.patch;
    }
};

// =============================================================
// 4. partial_ordering (values with NaN-like incomparability)
// =============================================================
class FuzzyDouble {
    double value_;
    double tolerance_;
public:
    FuzzyDouble(double v, double tol = 0.001)
        : value_(v), tolerance_(tol) {}

    double value() const { return value_; }

    // Partial ordering: values within tolerance are "equivalent" but
    // NaN is unordered with everything
    std::partial_ordering operator<=>(const FuzzyDouble& other) const {
        if (std::isnan(value_) || std::isnan(other.value_))
            return std::partial_ordering::unordered;

        double diff = value_ - other.value_;
        if (std::abs(diff) <= tolerance_)
            return std::partial_ordering::equivalent;
        if (diff < 0)
            return std::partial_ordering::less;
        return std::partial_ordering::greater;
    }

    bool operator==(const FuzzyDouble& other) const {
        if (std::isnan(value_) || std::isnan(other.value_)) return false;
        return std::abs(value_ - other.value_) <= tolerance_;
    }
};

// =============================================================
// 5. Heterogeneous comparison (compare with different type)
// =============================================================
struct Celsius {
    double temp;

    // Compare Celsius with Celsius
    auto operator<=>(const Celsius&) const = default;

    // Compare Celsius with plain double
    std::strong_ordering operator<=>(double other) const {
        if (temp < other) return std::strong_ordering::less;
        if (temp > other) return std::strong_ordering::greater;
        return std::strong_ordering::equal;
    }

    bool operator==(double other) const { return temp == other; }
};

int main() {
    // --- Defaulted spaceship ---
    std::cout << "=== Defaulted (Point) ===\n";
    Point a{1, 2, 3}, b{1, 2, 4}, c{1, 2, 3};
    std::cout << "a < b:  " << (a < b)  << "\n";   // 1 (lexicographic)
    std::cout << "a == c: " << (a == c) << "\n";    // 1
    std::cout << "b >= a: " << (b >= a) << "\n";    // 1

    // Works with std::set, std::sort, etc.
    std::set<Point> points = {{3,2,1}, {1,2,3}, {1,2,3}, {2,2,2}};
    std::cout << "Unique sorted points: " << points.size() << "\n";

    // --- Case-insensitive string ---
    std::cout << "\n=== Custom strong_ordering ===\n";
    CaseInsensitiveString s1("Hello"), s2("hello"), s3("World");
    std::cout << "Hello == hello: " << (s1 == s2) << "\n";  // 1
    std::cout << "Hello < World:  " << (s1 < s3)  << "\n";  // 1

    // --- Version comparison ---
    std::cout << "\n=== weak_ordering (Version) ===\n";
    Version v1{2, 1, 0}, v2{2, 1, 3}, v3{3, 0, 0};
    std::cout << v1 << " < " << v2 << ": " << (v1 < v2) << "\n";   // 1
    std::cout << v2 << " < " << v3 << ": " << (v2 < v3) << "\n";   // 1

    std::vector<Version> versions = {{1,0,0}, {2,1,0}, {1,5,3}, {2,0,1}};
    std::sort(versions.begin(), versions.end());
    std::cout << "Sorted: ";
    for (const auto& v : versions) std::cout << v << " ";
    std::cout << "\n";

    // --- Partial ordering (FuzzyDouble) ---
    std::cout << "\n=== partial_ordering (FuzzyDouble) ===\n";
    FuzzyDouble f1(1.0), f2(1.0005), f3(2.0);
    FuzzyDouble nan_val(std::numeric_limits<double>::quiet_NaN());

    std::cout << "1.0 == 1.0005: " << (f1 == f2) << "\n";     // 1 (within tolerance)
    std::cout << "1.0 < 2.0:     " << (f1 < f3)  << "\n";     // 1
    std::cout << "NaN == 1.0:    " << (nan_val == f1) << "\n"; // 0
    std::cout << "NaN < 1.0:     " << (nan_val < f1)  << "\n"; // 0 (unordered)
    std::cout << "NaN > 1.0:     " << (nan_val > f1)  << "\n"; // 0 (unordered)

    // --- Heterogeneous comparison ---
    std::cout << "\n=== Heterogeneous (Celsius vs double) ===\n";
    Celsius boiling{100.0};
    std::cout << "100C == 100.0: " << (boiling == 100.0) << "\n";  // 1
    std::cout << "100C > 50.0:   " << (boiling > 50.0)   << "\n";  // 1
    std::cout << "50.0 < 100C:   " << (50.0 < boiling)   << "\n";  // 1 (reversed!)

    return 0;
}
```

**Ordering types:**
| Type | Meaning | Example |
|---|---|---|
| `strong_ordering` | Total order, substitutable | integers, strings |
| `weak_ordering` | Total order, not substitutable | case-insensitive strings |
| `partial_ordering` | Some values incomparable | floating-point (NaN) |

The compiler generates all six operators (`==`, `!=`, `<`, `>`, `<=`, `>=`) from `<=>`, including **reversed** operands for heterogeneous comparisons.'''),

    ("cpp_deep/user_defined_literals", r'''Show how to create user-defined literals in C++ for domain-specific types, covering raw and cooked forms for different use cases.''', r'''<think>
User-defined literals (UDLs) allow creating domain-specific values with suffix notation.
Two forms:
1. Cooked: receives the parsed value (double, unsigned long long, etc.)
2. Raw: receives the raw string (template parameter pack or const char*)

I'll show practical examples: units, strings, regex, binary literals, etc.
Rules: suffix must start with underscore. Standard library uses no underscore prefix.
</think>

User-defined literals enable domain-specific notation in C++:

```cpp
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <regex>
#include <stdexcept>
#include <string>
#include <string_view>

// =============================================================
// 1. Cooked literals: receive parsed values
// =============================================================

// --- Physical units ---
struct Meters { double value; };
struct Kilometers { double value; };
struct Kilograms { double value; };
struct Celsius { double value; };
struct Fahrenheit { double value; };

constexpr Meters operator""_m(long double v) { return {static_cast<double>(v)}; }
constexpr Meters operator""_m(unsigned long long v) { return {static_cast<double>(v)}; }
constexpr Kilometers operator""_km(long double v) { return {static_cast<double>(v)}; }
constexpr Kilograms operator""_kg(long double v) { return {static_cast<double>(v)}; }
constexpr Celsius operator""_C(long double v) { return {static_cast<double>(v)}; }
constexpr Fahrenheit operator""_F(long double v) { return {static_cast<double>(v)}; }

// Conversion
constexpr Meters to_meters(Kilometers km) { return {km.value * 1000.0}; }
constexpr Celsius to_celsius(Fahrenheit f) { return {(f.value - 32.0) * 5.0 / 9.0}; }

std::ostream& operator<<(std::ostream& os, Meters m) { return os << m.value << "m"; }
std::ostream& operator<<(std::ostream& os, Kilometers k) { return os << k.value << "km"; }
std::ostream& operator<<(std::ostream& os, Kilograms k) { return os << k.value << "kg"; }
std::ostream& operator<<(std::ostream& os, Celsius c) { return os << c.value << "°C"; }

// --- Memory sizes ---
struct Bytes {
    std::size_t value;
    friend std::ostream& operator<<(std::ostream& os, Bytes b) {
        if (b.value >= 1024ULL * 1024 * 1024)
            return os << (b.value / (1024.0 * 1024 * 1024)) << " GB";
        if (b.value >= 1024 * 1024)
            return os << (b.value / (1024.0 * 1024)) << " MB";
        if (b.value >= 1024)
            return os << (b.value / 1024.0) << " KB";
        return os << b.value << " B";
    }
};

constexpr Bytes operator""_B(unsigned long long v) { return {v}; }
constexpr Bytes operator""_KB(unsigned long long v) { return {v * 1024}; }
constexpr Bytes operator""_MB(unsigned long long v) { return {v * 1024 * 1024}; }
constexpr Bytes operator""_GB(unsigned long long v) { return {v * 1024ULL * 1024 * 1024}; }

// =============================================================
// 2. String literals
// =============================================================

// Validated email at construction (throws if invalid)
struct Email {
    std::string address;
    friend std::ostream& operator<<(std::ostream& os, const Email& e) {
        return os << e.address;
    }
};

Email operator""_email(const char* str, std::size_t len) {
    std::string_view sv(str, len);
    if (sv.find('@') == std::string_view::npos || sv.find('.') == std::string_view::npos)
        throw std::invalid_argument("Invalid email: " + std::string(sv));
    return Email{std::string(sv)};
}

// Hexadecimal color
struct HexColor {
    uint8_t r, g, b;
    friend std::ostream& operator<<(std::ostream& os, HexColor c) {
        return os << "rgb(" << (int)c.r << "," << (int)c.g << "," << (int)c.b << ")";
    }
};

HexColor operator""_hex(const char* str, std::size_t len) {
    std::string_view sv(str, len);
    if (sv.front() == '#') { sv.remove_prefix(1); --len; }
    if (sv.size() != 6) throw std::invalid_argument("Expected 6 hex digits");

    auto parse = [&](std::size_t pos) -> uint8_t {
        unsigned val = 0;
        for (int i = 0; i < 2; ++i) {
            char c = sv[pos + i];
            val <<= 4;
            if (c >= '0' && c <= '9') val += c - '0';
            else if (c >= 'a' && c <= 'f') val += c - 'a' + 10;
            else if (c >= 'A' && c <= 'F') val += c - 'A' + 10;
            else throw std::invalid_argument("Bad hex char");
        }
        return static_cast<uint8_t>(val);
    };
    return {parse(0), parse(2), parse(4)};
}

// =============================================================
// 3. Raw literal: receives unparsed digits as template params
//    (C++20 for non-type template parameters)
// =============================================================

// Binary literal helper (C++14 has 0b prefix, but this shows the technique)
constexpr unsigned long long operator""_bin(const char* str) {
    unsigned long long result = 0;
    while (*str) {
        result <<= 1;
        if (*str == '1') result |= 1;
        else if (*str != '0') throw "Invalid binary digit";
        ++str;
    }
    return result;
}

// =============================================================
// 4. Percentage type
// =============================================================
struct Percent {
    double value;
    constexpr double as_fraction() const { return value / 100.0; }
    friend std::ostream& operator<<(std::ostream& os, Percent p) {
        return os << p.value << "%";
    }
};

constexpr Percent operator""_pct(long double v) { return {static_cast<double>(v)}; }
constexpr Percent operator""_pct(unsigned long long v) { return {static_cast<double>(v)}; }

int main() {
    // --- Physical units ---
    std::cout << "=== Units ===\n";
    auto distance = 42.195_km;
    auto weight = 75.0_kg;
    auto temp = 212.0_F;

    std::cout << "Marathon: " << distance << " = " << to_meters(distance) << "\n";
    std::cout << "Weight: " << weight << "\n";
    std::cout << "Temp: " << to_celsius(temp) << "\n";

    // Integer literal
    auto height = 180_m;
    std::cout << "Height: " << height << "\n";

    // --- Memory sizes ---
    std::cout << "\n=== Memory ===\n";
    auto cache = 64_KB;
    auto ram = 16_GB;
    auto file = 256_MB;
    std::cout << "Cache: " << cache << "\n";
    std::cout << "RAM:   " << ram << "\n";
    std::cout << "File:  " << file << "\n";

    // --- Validated strings ---
    std::cout << "\n=== Validated strings ===\n";
    auto email = "user@example.com"_email;
    std::cout << "Email: " << email << "\n";

    auto color = "#FF8800"_hex;
    std::cout << "Color: " << color << "\n";

    // Invalid email throws at construction:
    try {
        auto bad = "not-an-email"_email;
    } catch (const std::invalid_argument& e) {
        std::cout << "Caught: " << e.what() << "\n";
    }

    // --- Binary ---
    std::cout << "\n=== Raw literals ===\n";
    auto bits = 11010110_bin;
    std::cout << "11010110 binary = " << bits << " decimal\n";

    // --- Percentage ---
    std::cout << "\n=== Percentage ===\n";
    auto tax = 8.5_pct;
    double price = 100.0;
    double total = price * (1.0 + tax.as_fraction());
    std::cout << "Price $100 + " << tax << " tax = $" << total << "\n";

    // --- Standard library literals ---
    using namespace std::string_literals;
    using namespace std::chrono_literals;

    auto name = "hello\0world"s;     // std::string (includes \0)
    auto delay = 500ms;               // std::chrono::milliseconds
    auto timeout = 2s;                // std::chrono::seconds

    std::cout << "\nString length (with null): " << name.size() << "\n";

    return 0;
}
```

**Literal operator forms:**
| Form | Signature | Receives |
|---|---|---|
| Integer cooked | `operator""_x(unsigned long long)` | Parsed integer |
| Float cooked | `operator""_x(long double)` | Parsed float |
| String cooked | `operator""_x(const char*, size_t)` | String + length |
| Character | `operator""_x(char)` | Single character |
| Raw integer | `operator""_x(const char*)` | Unparsed digit string |'''),

    ("cpp_deep/source_location_errors", r'''Show how std::source_location (C++20) improves error messages and logging compared to __FILE__ and __LINE__ macros.''', r'''<think>
std::source_location provides file, line, column, and function name as a
first-class object that can be passed to functions and stored in data structures.
Key advantage over macros: works with default arguments, so callers don't need
to pass anything explicitly. The default captures the call site automatically.

I'll show:
1. Basic usage vs macros.
2. Logging with source_location.
3. Custom assert.
4. Exception with source location.
5. Trace/profiling.
</think>

`std::source_location` (C++20) replaces `__FILE__`/`__LINE__` macros with a proper object:

```cpp
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <source_location>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

// =============================================================
// 1. Basic: source_location as default parameter
// =============================================================

// The magic: default parameter captures the CALLER'S location, not this function's
void log_message(std::string_view msg,
                 std::source_location loc = std::source_location::current())
{
    std::cout << loc.file_name() << ":" << loc.line()
              << " [" << loc.function_name() << "] " << msg << "\n";
}

// =============================================================
// 2. Structured logger with severity levels
// =============================================================
enum class LogLevel { debug, info, warn, error };

class Logger {
    LogLevel min_level_ = LogLevel::debug;

    static const char* level_str(LogLevel lv) {
        switch (lv) {
            case LogLevel::debug: return "DEBUG";
            case LogLevel::info:  return "INFO ";
            case LogLevel::warn:  return "WARN ";
            case LogLevel::error: return "ERROR";
        }
        return "?????";
    }

public:
    void set_level(LogLevel lv) { min_level_ = lv; }

    void log(LogLevel level, std::string_view msg,
             std::source_location loc = std::source_location::current()) const
    {
        if (level < min_level_) return;

        // Extract just filename from full path
        std::string_view file = loc.file_name();
        auto pos = file.find_last_of("/\\");
        if (pos != std::string_view::npos) file = file.substr(pos + 1);

        std::cout << "[" << level_str(level) << "] "
                  << file << ":" << loc.line()
                  << " (" << loc.function_name() << ") "
                  << msg << "\n";
    }

    void debug(std::string_view msg,
               std::source_location loc = std::source_location::current()) const {
        log(LogLevel::debug, msg, loc);
    }
    void info(std::string_view msg,
              std::source_location loc = std::source_location::current()) const {
        log(LogLevel::info, msg, loc);
    }
    void warn(std::string_view msg,
              std::source_location loc = std::source_location::current()) const {
        log(LogLevel::warn, msg, loc);
    }
    void error(std::string_view msg,
               std::source_location loc = std::source_location::current()) const {
        log(LogLevel::error, msg, loc);
    }
};

// =============================================================
// 3. Custom assert that captures location WITHOUT macros
// =============================================================
inline void runtime_assert(bool condition, std::string_view expr,
                           std::source_location loc = std::source_location::current())
{
    if (!condition) {
        std::cerr << "ASSERTION FAILED: " << expr << "\n"
                  << "  at " << loc.file_name() << ":" << loc.line() << "\n"
                  << "  in " << loc.function_name() << "\n";
        std::abort();
    }
}

// Macro-free assert helper
#define ASSERT(expr) runtime_assert(static_cast<bool>(expr), #expr)

// =============================================================
// 4. Exception with source location baked in
// =============================================================
class TracedException : public std::exception {
    std::string what_;
    std::source_location loc_;

public:
    TracedException(std::string msg,
                    std::source_location loc = std::source_location::current())
        : loc_(loc)
    {
        std::ostringstream oss;
        oss << msg << " [" << loc_.file_name() << ":" << loc_.line()
            << " in " << loc_.function_name() << "]";
        what_ = oss.str();
    }

    const char* what() const noexcept override { return what_.c_str(); }
    const std::source_location& where() const noexcept { return loc_; }
};

// =============================================================
// 5. Call trace recorder
// =============================================================
class CallTracer {
    struct Entry {
        std::string function;
        std::string file;
        int line;
    };
    static inline std::vector<Entry> trace_;

public:
    static void record(std::source_location loc = std::source_location::current()) {
        std::string_view file = loc.file_name();
        auto pos = file.find_last_of("/\\");
        trace_.push_back({
            std::string(loc.function_name()),
            std::string(pos != std::string_view::npos ? file.substr(pos+1) : file),
            static_cast<int>(loc.line())
        });
    }

    static void print_trace() {
        std::cout << "Call trace (" << trace_.size() << " entries):\n";
        for (std::size_t i = 0; i < trace_.size(); ++i) {
            const auto& e = trace_[i];
            std::cout << "  #" << i << " " << e.function
                      << " at " << e.file << ":" << e.line << "\n";
        }
    }

    static void clear() { trace_.clear(); }
};

// =============================================================
// Usage
// =============================================================
void process_data(int value) {
    CallTracer::record();
    Logger logger;

    logger.debug("Starting processing");

    if (value < 0) {
        logger.warn("Negative value received");
        throw TracedException("Cannot process negative value: " + std::to_string(value));
    }

    logger.info("Processed value: " + std::to_string(value));
}

void handle_request(int data) {
    CallTracer::record();
    process_data(data);
}

int main() {
    // --- Basic logging ---
    std::cout << "=== Basic log_message ===\n";
    log_message("application started");
    log_message("initializing subsystems");

    // --- Structured logger ---
    std::cout << "\n=== Structured logger ===\n";
    Logger log;
    log.info("Server starting");
    log.debug("Loading config");
    log.warn("Deprecated API used");

    // --- Traced exceptions ---
    std::cout << "\n=== Traced exception ===\n";
    try {
        handle_request(-5);
    } catch (const TracedException& e) {
        std::cerr << "Exception: " << e.what() << "\n";
        std::cerr << "Thrown at line: " << e.where().line() << "\n";
    }

    // --- Call trace ---
    std::cout << "\n=== Call trace ===\n";
    CallTracer::print_trace();

    // --- source_location fields ---
    std::cout << "\n=== source_location fields ===\n";
    auto here = std::source_location::current();
    std::cout << "file:     " << here.file_name() << "\n";
    std::cout << "line:     " << here.line() << "\n";
    std::cout << "column:   " << here.column() << "\n";
    std::cout << "function: " << here.function_name() << "\n";

    return 0;
}
```

**`std::source_location` vs macros:**

| | `__FILE__` / `__LINE__` | `std::source_location` |
|---|---|---|
| Type safety | String/int literals | Proper object |
| Pass to function | Must use macro wrapper | Default parameter captures call site |
| Store in data | Manual string copy | Copy the object |
| Function name | `__func__` (plain name) | `.function_name()` (decorated) |
| Column | Not available | `.column()` |
| Composable | No (macros are textual) | Yes (regular C++ value) |'''),

    ("cpp_deep/static_assert_validation", r'''Show advanced uses of static_assert with custom messages for compile-time validation in C++, including concept-based and constexpr validation.''', r'''<think>
static_assert evaluates a constant expression at compile time and emits the
message if it fails. Combined with type_traits, concepts, and constexpr,
it enables powerful compile-time validation.

I'll show:
1. Basic type constraints with type_traits.
2. Size and layout validation.
3. Concept-based static_assert.
4. constexpr function validation.
5. Template parameter validation.
6. Platform/ABI assumptions.
</think>

Advanced `static_assert` usage for compile-time validation in C++:

```cpp
#include <bit>
#include <concepts>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <string>
#include <type_traits>

// =============================================================
// 1. Type trait validation
// =============================================================
template <typename T>
class ThreadSafeQueue {
    // Enforce requirements at the point of instantiation
    static_assert(std::is_move_constructible_v<T>,
        "ThreadSafeQueue<T>: T must be move-constructible");
    static_assert(!std::is_reference_v<T>,
        "ThreadSafeQueue<T>: T must not be a reference type");
    static_assert(!std::is_void_v<T>,
        "ThreadSafeQueue<T>: T must not be void");

    // For lock-free optimization
    static_assert(std::is_trivially_copyable_v<T> || sizeof(T) <= 256,
        "ThreadSafeQueue<T>: large non-trivial types will have poor performance");

public:
    void push(T item) { /* ... */ }
};

// =============================================================
// 2. Struct layout and ABI validation
// =============================================================
struct NetworkPacket {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;
    uint32_t payload_size;
    uint64_t timestamp;
    char data[64];
};

// Ensure binary layout matches protocol spec
static_assert(sizeof(NetworkPacket) == 88,
    "NetworkPacket size must be exactly 88 bytes for wire protocol");
static_assert(std::is_trivially_copyable_v<NetworkPacket>,
    "NetworkPacket must be trivially copyable for memcpy/send");
static_assert(std::is_standard_layout_v<NetworkPacket>,
    "NetworkPacket must be standard layout for C interop");

// Offset validation (protocol requires specific field positions)
static_assert(offsetof(NetworkPacket, magic) == 0);
static_assert(offsetof(NetworkPacket, version) == 4);
static_assert(offsetof(NetworkPacket, flags) == 6);
static_assert(offsetof(NetworkPacket, payload_size) == 8);
static_assert(offsetof(NetworkPacket, timestamp) == 16);
static_assert(offsetof(NetworkPacket, data) == 24);

// =============================================================
// 3. Platform assumptions
// =============================================================
static_assert(sizeof(void*) == 8, "This code requires a 64-bit platform");
static_assert(sizeof(int) >= 4, "int must be at least 32 bits");
static_assert(std::endian::native == std::endian::little,
    "This code assumes little-endian byte order");
static_assert(CHAR_BIT == 8, "This code requires 8-bit bytes");

// =============================================================
// 4. constexpr function validation
// =============================================================
constexpr int MAX_CHANNELS = 16;
constexpr int BUFFER_SIZE = 4096;
constexpr double PI = 3.14159265358979323846;

static_assert(MAX_CHANNELS > 0 && (MAX_CHANNELS & (MAX_CHANNELS - 1)) == 0,
    "MAX_CHANNELS must be a power of 2");
static_assert(BUFFER_SIZE >= 1024 && BUFFER_SIZE <= 65536,
    "BUFFER_SIZE must be between 1KB and 64KB");

// Validate constexpr computation results
constexpr int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; ++i) result *= i;
    return result;
}

static_assert(factorial(0) == 1);
static_assert(factorial(5) == 120);
static_assert(factorial(10) == 3628800);

// Validate lookup table at compile time
constexpr int CRC_TABLE_SIZE = 256;
constexpr auto make_crc_table() {
    std::array<uint32_t, CRC_TABLE_SIZE> table{};
    for (uint32_t i = 0; i < CRC_TABLE_SIZE; ++i) {
        uint32_t crc = i;
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        }
        table[i] = crc;
    }
    return table;
}

constexpr auto CRC_TABLE = make_crc_table();
static_assert(CRC_TABLE[0] == 0x00000000);
static_assert(CRC_TABLE[1] == 0x77073096);  // known CRC32 constant

// =============================================================
// 5. Template parameter validation with concepts
// =============================================================
template <typename T, std::size_t N>
    requires (N > 0)
class FixedVector {
    static_assert(N <= 1024,
        "FixedVector: capacity exceeds maximum of 1024");
    static_assert(std::is_default_constructible_v<T>,
        "FixedVector: T must be default constructible");

    T data_[N];
    std::size_t size_ = 0;

public:
    constexpr void push_back(const T& val) {
        if (size_ < N) data_[size_++] = val;
    }
    constexpr std::size_t size() const { return size_; }
    constexpr std::size_t capacity() const { return N; }
    constexpr T& operator[](std::size_t i) { return data_[i]; }
};

// =============================================================
// 6. Enum completeness validation
// =============================================================
enum class Color : uint8_t { Red = 0, Green, Blue, COUNT };

static_assert(static_cast<int>(Color::COUNT) == 3,
    "Color enum: update COUNT if you add new colors");

// Validate enum-indexed array matches
constexpr const char* COLOR_NAMES[] = {"Red", "Green", "Blue"};
static_assert(std::size(COLOR_NAMES) == static_cast<std::size_t>(Color::COUNT),
    "COLOR_NAMES array must match Color enum count");

// =============================================================
// 7. Concept-based validation helper
// =============================================================
template <typename Fn, typename... Args>
concept CallableWith = std::invocable<Fn, Args...>;

template <typename Fn, typename R, typename... Args>
concept ReturnsType = CallableWith<Fn, Args...> &&
    std::same_as<std::invoke_result_t<Fn, Args...>, R>;

template <typename Handler>
void register_handler(Handler h) {
    static_assert(ReturnsType<Handler, bool, int, const std::string&>,
        "Handler must be callable as bool(int, const std::string&)");
    // ...
}

int main() {
    // These compile fine:
    ThreadSafeQueue<int> q1;
    ThreadSafeQueue<std::string> q2;

    // These would fail static_assert:
    // ThreadSafeQueue<int&> q3;           // reference type
    // ThreadSafeQueue<void> q4;           // void type

    FixedVector<int, 100> fv;
    fv.push_back(42);
    std::cout << "FixedVector size: " << fv.size() << "/" << fv.capacity() << "\n";

    // This would fail:
    // FixedVector<int, 0> bad1;           // requires N > 0
    // FixedVector<int, 2000> bad2;        // exceeds max 1024

    // Handler registration
    register_handler([](int code, const std::string& msg) -> bool {
        std::cout << "Handler: " << code << " " << msg << "\n";
        return true;
    });

    // This would fail static_assert:
    // register_handler([](int x) { return x; });  // wrong signature

    std::cout << "NetworkPacket size: " << sizeof(NetworkPacket) << "\n";
    std::cout << "All static_asserts passed at compile time.\n";

    return 0;
}
```

**`static_assert` best practices:**
1. **Type constraints**: validate template parameters at instantiation, not at use.
2. **ABI/layout**: verify struct sizes, offsets, and alignment match protocol specs.
3. **Platform**: assert architecture assumptions (pointer size, endianness, int width).
4. **constexpr validation**: test compile-time computations (lookup tables, constants).
5. **Enum sync**: ensure arrays and enums stay in sync via `COUNT` sentinel.
6. **Clear messages**: the string should say WHAT is wrong and WHY, not just "assertion failed".'''),
]
