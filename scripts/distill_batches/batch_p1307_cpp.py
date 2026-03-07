"""C++ training pairs (part 1): RAII, smart pointers, move semantics, templates, constexpr."""

PAIRS = [
    (
        "cpp/raii-resource-management",
        r'''How do I manage resources safely in C++ without manually calling delete or close? I keep getting leaks when exceptions are thrown.''',
        r'''<think>
The user is hitting a classic C++ problem: manual resource management is error-prone,
especially with exceptions. RAII (Resource Acquisition Is Initialization) is the
idiomatic solution — tie resource lifetime to object lifetime so destructors handle
cleanup automatically. I should show a practical example with a file handle wrapper
and explain why this is exception-safe. This is a foundational C++ pattern.
</think>

Use **RAII** (Resource Acquisition Is Initialization) — bind resource lifetime to object scope so the destructor always cleans up, even if an exception is thrown.

```cpp
#include <cstdio>
#include <stdexcept>
#include <string>

class FileHandle {
    FILE* fp_;
public:
    explicit FileHandle(const std::string& path, const char* mode)
        : fp_(std::fopen(path.c_str(), mode))
    {
        if (!fp_) throw std::runtime_error("Failed to open: " + path);
    }

    ~FileHandle() {
        if (fp_) std::fclose(fp_);  // guaranteed cleanup
    }

    // Non-copyable
    FileHandle(const FileHandle&) = delete;
    FileHandle& operator=(const FileHandle&) = delete;

    // Movable
    FileHandle(FileHandle&& other) noexcept : fp_(other.fp_) {
        other.fp_ = nullptr;
    }

    FILE* get() const { return fp_; }
};

void process_file() {
    FileHandle file("data.txt", "r");
    // If anything here throws, ~FileHandle() still runs
    char buf[256];
    while (std::fgets(buf, sizeof(buf), file.get())) {
        // process lines...
    }
}  // file closed automatically here
```

Key RAII principles:
- **Acquire in constructor**, release in destructor
- Delete copy operations to prevent double-free
- Support move semantics if ownership transfer makes sense
- Stack unwinding guarantees destructors run on exceptions

The standard library already provides RAII wrappers: `std::unique_ptr`, `std::lock_guard`, `std::fstream`, etc. Prefer those over raw handles whenever possible.'''
    ),
    (
        "cpp/unique-ptr-ownership",
        r'''Can you explain unique_ptr ownership and how to transfer it between functions? When should I use unique_ptr vs raw pointers?''',
        r'''<think>
The user wants to understand unique_ptr ownership semantics and transfer patterns.
I should cover construction, move-based transfer, factory functions returning unique_ptr,
and passing to functions that take ownership vs. borrow. Also clarify when raw pointers
are still appropriate (non-owning observation). This is intermediate-level modern C++.
</think>

`std::unique_ptr` expresses **exclusive ownership** — exactly one pointer owns the resource at any time.

```cpp
#include <memory>
#include <iostream>
#include <string>

struct Connection {
    std::string host;
    Connection(std::string h) : host(std::move(h)) {
        std::cout << "Connected to " << host << "\n";
    }
    ~Connection() { std::cout << "Disconnected from " << host << "\n"; }
};

// Factory — caller receives ownership
std::unique_ptr<Connection> make_connection(const std::string& host) {
    return std::make_unique<Connection>(host);  // RVO, no explicit move
}

// Takes ownership — caller gives up the resource
void consume(std::unique_ptr<Connection> conn) {
    std::cout << "Using " << conn->host << "\n";
}  // conn destroyed here

// Borrows — caller keeps ownership (use raw pointer or reference)
void inspect(const Connection& conn) {
    std::cout << "Inspecting " << conn.host << "\n";
}

int main() {
    auto conn = make_connection("db.example.com");

    inspect(*conn);           // borrow via reference — no ownership change
    inspect(*conn);           // can borrow multiple times

    consume(std::move(conn)); // explicit move — transfers ownership
    // conn is now nullptr
}
```

Guidelines:
| Scenario | Use |
|---|---|
| Owning a heap object | `std::unique_ptr<T>` |
| Transferring ownership | `std::move(ptr)` or return by value |
| Borrowing (no ownership) | `T&` or `T*` (non-owning raw pointer) |
| Shared ownership needed | `std::shared_ptr<T>` instead |

Never call `new`/`delete` directly — use `std::make_unique<T>(args...)`.'''
    ),
    (
        "cpp/shared-ptr-custom-deleter",
        r'''How do I use shared_ptr with a custom deleter? I need to wrap a C library handle that requires a special cleanup function.''',
        r'''<think>
The user needs to wrap a C resource (like SDL, OpenSSL, or a database handle) with
shared_ptr using a custom deleter. shared_ptr accepts a deleter in its constructor,
unlike unique_ptr which takes it as a template parameter. I should show both lambda
and function pointer approaches, and mention make_shared limitations with custom deleters.
This is an intermediate/advanced pattern.
</think>

`std::shared_ptr` accepts a custom deleter as a constructor argument — perfect for wrapping C library handles.

```cpp
#include <memory>
#include <cstdio>
#include <iostream>

// Simulating a C library API
struct DBHandle { int id; };
DBHandle* db_open(const char* name) {
    auto* h = new DBHandle{42};
    std::cout << "db_open: " << name << "\n";
    return h;
}
void db_close(DBHandle* h) {
    std::cout << "db_close: handle " << h->id << "\n";
    delete h;
}

int main() {
    // Lambda deleter (most common)
    std::shared_ptr<DBHandle> db(db_open("mydb"), [](DBHandle* h) {
        db_close(h);
    });

    // Function pointer deleter
    std::shared_ptr<FILE> file(std::fopen("log.txt", "w"), &std::fclose);

    // Use like normal pointers
    std::cout << "DB handle id: " << db->id << "\n";
    if (file) std::fprintf(file.get(), "hello\n");

    // Can copy — ref-counted, last owner calls deleter
    auto db2 = db;
    db.reset();   // doesn't close yet — db2 still holds a reference
}  // db2 destroyed → db_close called; file destroyed → fclose called
```

Important notes:
- **Cannot use `make_shared`** with custom deleters — must use the constructor
- The deleter is type-erased (stored internally), so it doesn't affect the `shared_ptr<T>` type
- For `unique_ptr`, the deleter is part of the type: `std::unique_ptr<DBHandle, decltype(&db_close)>`
- Prefer `unique_ptr` with custom deleter if you don't need shared ownership — less overhead'''
    ),
    (
        "cpp/weak-ptr-circular-refs",
        r'''I have two classes that reference each other with shared_ptr and my objects are never destroyed. How do I fix this memory leak?''',
        r'''<think>
Classic circular reference problem with shared_ptr. When two objects hold shared_ptrs
to each other, the reference counts never reach zero. The fix is to use weak_ptr for
the "back-reference" — the non-owning direction. I should show the problem, then the
fix, and explain how weak_ptr::lock() works. This is intermediate-level.
</think>

You have a **circular reference** — two `shared_ptr`s pointing at each other keep both ref counts at 1 forever. Break the cycle with `std::weak_ptr`.

```cpp
#include <memory>
#include <iostream>
#include <string>

struct Child;  // forward declaration

struct Parent {
    std::string name;
    std::shared_ptr<Child> child;  // parent OWNS child
    ~Parent() { std::cout << name << " destroyed\n"; }
};

struct Child {
    std::string name;
    std::weak_ptr<Parent> parent;  // child OBSERVES parent (weak!)
    ~Child() { std::cout << name << " destroyed\n"; }
};

int main() {
    auto dad = std::make_shared<Parent>(Parent{"Dad"});
    auto kid = std::make_shared<Child>(Child{"Kid"});

    dad->child = kid;
    kid->parent = dad;  // weak_ptr — does NOT increment ref count

    // Access parent from child via lock()
    if (auto p = kid->parent.lock()) {
        std::cout << kid->name << "'s parent: " << p->name << "\n";
    }

    dad.reset();  // ref count → 0, Dad destroyed, which destroys Kid too
    // kid->parent.lock() would now return nullptr (parent is gone)

    std::cout << "No leaks!\n";
}
```

**Output:**
```
Kid's parent: Dad
Dad destroyed
Kid destroyed
No leaks!
```

Rules of thumb:
- **Owning direction** → `shared_ptr` (parent → child)
- **Back-reference / observer** → `weak_ptr` (child → parent)
- Always check `weak_ptr::lock()` — the object may already be gone
- `weak_ptr::expired()` is available but racy in multithreaded code — prefer `lock()` and check the result'''
    ),
    (
        "cpp/move-semantics-basics",
        r'''I don't fully understand move semantics in C++. Why are they useful and how do I implement a move constructor?''',
        r'''<think>
Move semantics is a core modern C++ concept. The user needs to understand the motivation
(avoiding expensive copies), the difference between lvalues and rvalues, and how to write
move constructors/assignments. I should show a practical class with a resource that
benefits from moves, demonstrate the performance difference, and cover the rule of five.
</think>

Move semantics let you **transfer resources** (heap memory, file handles, etc.) from one object to another instead of copying them — turning an O(n) copy into an O(1) pointer swap.

```cpp
#include <algorithm>
#include <cstring>
#include <iostream>
#include <utility>

class Buffer {
    char* data_;
    size_t size_;
public:
    // Constructor
    explicit Buffer(size_t sz) : data_(new char[sz]), size_(sz) {
        std::cout << "Alloc " << sz << " bytes\n";
    }

    // Destructor
    ~Buffer() { delete[] data_; }

    // Copy constructor — expensive O(n)
    Buffer(const Buffer& other) : data_(new char[other.size_]), size_(other.size_) {
        std::memcpy(data_, other.data_, size_);
        std::cout << "Copy " << size_ << " bytes\n";
    }

    // Move constructor — cheap O(1), steals resources
    Buffer(Buffer&& other) noexcept
        : data_(other.data_), size_(other.size_)
    {
        other.data_ = nullptr;  // leave source in valid empty state
        other.size_ = 0;
        std::cout << "Move (zero-cost)\n";
    }

    // Move assignment
    Buffer& operator=(Buffer&& other) noexcept {
        if (this != &other) {
            delete[] data_;
            data_ = other.data_;
            size_ = other.size_;
            other.data_ = nullptr;
            other.size_ = 0;
        }
        return *this;
    }

    size_t size() const { return size_; }
};

Buffer create_large_buffer() {
    Buffer buf(1'000'000);
    return buf;  // NRVO or move — no copy
}

int main() {
    Buffer a(100);
    Buffer b = std::move(a);  // explicit move — a is now empty
    // a.size() == 0, b.size() == 100

    Buffer c = create_large_buffer();  // returned by move (or NRVO)
}
```

Key rules:
- `std::move()` is just a cast to `T&&` — it doesn't move anything by itself
- After a move, the source must be in a **valid but unspecified** state
- Mark move operations `noexcept` — STL containers optimize with noexcept moves
- **Rule of Five**: if you define any of destructor/copy ctor/copy assign/move ctor/move assign, define all five'''
    ),
    (
        "cpp/perfect-forwarding",
        r'''What is perfect forwarding in C++ and when do I need std::forward? I keep seeing it in template code but I'm confused about what it does.''',
        r'''<think>
Perfect forwarding preserves the value category (lvalue/rvalue) of arguments when passing
them through template functions. Without it, rvalue references become lvalues inside the
function body. std::forward conditionally casts back to rvalue if the original was an rvalue.
This is an advanced topic — I need to explain forwarding references (T&&) vs rvalue references,
and show a practical use case like an emplace-style wrapper.
</think>

**Perfect forwarding** passes arguments through a template function while preserving whether they were lvalues or rvalues — so the final callee can move from rvalues and copy lvalues.

```cpp
#include <iostream>
#include <string>
#include <utility>
#include <vector>

struct Widget {
    std::string name;
    Widget(const std::string& n) : name(n) { std::cout << "Copy-constructed\n"; }
    Widget(std::string&& n) : name(std::move(n)) { std::cout << "Move-constructed\n"; }
};

// Forwarding reference (T&& where T is deduced) — NOT an rvalue reference
template <typename... Args>
Widget make_widget(Args&&... args) {
    // std::forward re-applies the original value category
    return Widget(std::forward<Args>(args)...);
}

int main() {
    std::string s = "hello";

    auto w1 = make_widget(s);            // s is lvalue → forward preserves → copy
    auto w2 = make_widget(std::string("world"));  // rvalue → forward preserves → move
    auto w3 = make_widget(std::move(s)); // moved lvalue → forward preserves → move
}
```

**Output:**
```
Copy-constructed
Move-constructed
Move-constructed
```

How it works:
1. `T&&` in a deduced context is a **forwarding reference**, not an rvalue ref
2. If you pass an lvalue, `T` deduces to `T&` → `T& &&` collapses to `T&`
3. If you pass an rvalue, `T` deduces to `T` → the parameter is `T&&`
4. `std::forward<T>(arg)` casts to `T&&` only if the original was an rvalue

**Without `std::forward`**, named parameters are always lvalues inside the function — rvalue arguments would get copied instead of moved. This is the whole point: forward restores the original category.'''
    ),
    (
        "cpp/variadic-templates",
        r'''How do variadic templates work in C++? I want to write a function that accepts any number of arguments of different types.''',
        r'''<think>
Variadic templates use parameter packs to accept any number of template arguments.
The user needs to see the basic syntax, pack expansion, recursive unpacking, and
the modern C++17 fold expression alternative. I'll show a practical logger example
that prints any number of arguments. Intermediate-to-advanced topic.
</think>

Variadic templates use **parameter packs** (`...`) to accept zero or more arguments of any type.

```cpp
#include <iostream>
#include <sstream>
#include <string>

// Base case — ends recursion
void log_impl(std::ostringstream& oss) {
    std::cout << oss.str() << "\n";
}

// Recursive — peel off first arg, recurse on the rest
template <typename T, typename... Rest>
void log_impl(std::ostringstream& oss, const T& first, const Rest&... rest) {
    oss << first;
    if constexpr (sizeof...(rest) > 0) oss << " | ";
    log_impl(oss, rest...);  // expand remaining pack
}

template <typename... Args>
void log(const Args&... args) {
    std::ostringstream oss;
    log_impl(oss, args...);
}

// C++17 fold expression — much simpler
template <typename... Args>
std::string concat(const Args&... args) {
    std::ostringstream oss;
    ((oss << args << " "), ...);  // unary left fold
    return oss.str();
}

// Variadic class template — type-safe tuple-like container
template <typename... Ts>
struct TypeList {
    static constexpr size_t size = sizeof...(Ts);
};

int main() {
    log("status", 200, "OK", 3.14);
    // Output: status | 200 | OK | 3.14

    std::cout << concat("hello", 42, 'x', 2.5) << "\n";
    // Output: hello 42 x 2.5

    static_assert(TypeList<int, double, char>::size == 3);
}
```

Key syntax:
- `typename... Ts` — declares a template parameter pack
- `const Ts&... args` — declares a function parameter pack
- `args...` — **expands** the pack (each element substituted)
- `sizeof...(args)` — number of elements in the pack (compile-time)
- `(expr, ...)` — C++17 fold expression (applies operator across all elements)

Prefer **fold expressions** (C++17) over recursive unpacking — they're shorter and often faster to compile.'''
    ),
    (
        "cpp/sfinae-enable-if",
        r'''How does SFINAE work and how do I use enable_if to constrain template functions? I want different overloads for integral vs floating-point types.''',
        r'''<think>
SFINAE (Substitution Failure Is Not An Error) is an advanced template metaprogramming
technique. When template argument substitution fails, the overload is silently removed
rather than causing a compile error. enable_if exploits this. I should show the classic
enable_if approach, then mention that C++20 concepts are the modern replacement. The user
asked specifically about enable_if, so I'll focus there with a practical example.
</think>

**SFINAE** = Substitution Failure Is Not An Error. If substituting template args makes an expression ill-formed, that overload is silently discarded instead of causing a hard error.

`std::enable_if` leverages this to constrain templates:

```cpp
#include <iostream>
#include <type_traits>

// Only enabled for integral types
template <typename T>
std::enable_if_t<std::is_integral_v<T>, T>
safe_divide(T a, T b) {
    if (b == 0) throw std::runtime_error("division by zero");
    return a / b;
}

// Only enabled for floating-point types
template <typename T>
std::enable_if_t<std::is_floating_point_v<T>, T>
safe_divide(T a, T b) {
    if (b == T{0}) return std::numeric_limits<T>::infinity();
    return a / b;
}

// SFINAE in return type — detect if type has .size()
template <typename T>
auto has_size_impl(const T& x) -> decltype(x.size(), std::true_type{});
std::false_type has_size_impl(...);

template <typename T>
constexpr bool has_size_v = decltype(has_size_impl(std::declval<T>()))::value;

// Use the trait to dispatch
template <typename T>
void describe(const T& x) {
    if constexpr (has_size_v<T>) {
        std::cout << "Container with " << x.size() << " elements\n";
    } else {
        std::cout << "Value: " << x << "\n";
    }
}

int main() {
    std::cout << safe_divide(10, 3) << "\n";       // integral: 3
    std::cout << safe_divide(10.0, 3.0) << "\n";   // floating: 3.33333
    // safe_divide("a", "b");  // compile error — no matching overload

    describe(std::vector{1, 2, 3});  // "Container with 3 elements"
    describe(42);                     // "Value: 42"
}
```

`enable_if_t<condition, T>` resolves to `T` if condition is true, otherwise substitution fails and the overload is removed.

**Modern alternative** — C++20 concepts are cleaner:
```cpp
template <std::integral T>
T safe_divide(T a, T b);  // same constraint, much cleaner syntax
```

Prefer concepts over SFINAE in new C++20 code. Use SFINAE only when targeting C++11/14/17.'''
    ),
    (
        "cpp/concepts-cpp20",
        r'''How do C++20 concepts work? Show me how to define my own concepts and use them to constrain templates.''',
        r'''<think>
C++20 concepts replace SFINAE with clean, readable constraints. The user wants to
define custom concepts and apply them. I should show concept definition with requires
clauses, using standard concepts from <concepts>, applying concepts in different
syntactic positions, and composing concepts with && and ||. This is an advanced topic
that's becoming standard practice.
</think>

C++20 **concepts** are named boolean predicates on template parameters — they replace SFINAE with clear, readable constraints and produce better error messages.

```cpp
#include <concepts>
#include <iostream>
#include <string>
#include <vector>

// Define a concept: type must support iteration
template <typename T>
concept Iterable = requires(T t) {
    std::begin(t);
    std::end(t);
};

// Concept with compound requirements
template <typename T>
concept Printable = requires(std::ostream& os, T val) {
    { os << val } -> std::same_as<std::ostream&>;  // expression must return ostream&
};

// Concept composition
template <typename T>
concept PrintableContainer = Iterable<T> && requires(T t) {
    typename T::value_type;                          // must have value_type
    requires Printable<typename T::value_type>;      // elements must be Printable
};

// Usage 1: requires clause
template <typename T> requires std::integral<T>
T gcd(T a, T b) {
    while (b) { a %= b; std::swap(a, b); }
    return a;
}

// Usage 2: constrained template parameter (most concise)
void print_all(const PrintableContainer auto& container) {
    for (const auto& elem : container) {
        std::cout << elem << " ";
    }
    std::cout << "\n";
}

// Usage 3: trailing requires
template <typename T>
T clamp_positive(T val) requires std::floating_point<T> {
    return val < T{0} ? T{0} : val;
}

int main() {
    std::cout << gcd(12, 8) << "\n";  // 4
    // gcd(1.5, 2.5);  // error: "constraint std::integral<double> not satisfied"

    print_all(std::vector<int>{1, 2, 3});
    print_all(std::vector<std::string>{"hello", "world"});
    // print_all(42);  // error: constraint PrintableContainer not satisfied

    std::cout << clamp_positive(-3.14) << "\n";  // 0
}
```

Standard library concepts (`<concepts>`): `std::integral`, `std::floating_point`, `std::same_as`, `std::convertible_to`, `std::derived_from`, `std::invocable`, `std::copyable`, `std::movable`, and many more.

Concepts are strictly better than SFINAE — use them in all new C++20 code.'''
    ),
    (
        "cpp/constexpr-compile-time",
        r'''How do I use constexpr to do compile-time computation in modern C++? What are the limits of constexpr in C++20?''',
        r'''<think>
constexpr has evolved significantly across C++ standards. In C++20, almost all of the
language is available in constexpr contexts — including dynamic allocation, try-catch,
and virtual functions. I should show constexpr functions, constexpr variables,
consteval (guaranteed compile-time), and if constexpr. The user wants practical
examples showing what's possible at compile time. Advanced topic.
</think>

`constexpr` marks functions/variables as evaluable at compile time. C++20 dramatically expanded what's allowed.

```cpp
#include <array>
#include <algorithm>
#include <iostream>
#include <numeric>

// Compile-time factorial
constexpr int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; ++i)  // loops OK since C++14
        result *= i;
    return result;
}

// Compile-time string hashing (FNV-1a)
constexpr uint64_t hash_string(std::string_view sv) {
    uint64_t hash = 14695981039346656037ULL;
    for (char c : sv) {
        hash ^= static_cast<uint64_t>(c);
        hash *= 1099511628211ULL;
    }
    return hash;
}

// C++20: constexpr std::vector and algorithms (transient allocation)
constexpr auto make_sorted_primes() {
    // Dynamic allocation OK if freed within constexpr context
    auto is_prime = [](int n) {
        if (n < 2) return false;
        for (int i = 2; i * i <= n; ++i)
            if (n % i == 0) return false;
        return true;
    };

    std::array<int, 25> primes{};
    int count = 0;
    for (int i = 2; count < 25; ++i)
        if (is_prime(i)) primes[count++] = i;
    return primes;
}

// consteval — MUST be evaluated at compile time (C++20)
consteval int compile_time_only(int x) {
    return x * x;
}

// if constexpr — compile-time branch elimination
template <typename T>
auto serialize(const T& val) {
    if constexpr (std::is_arithmetic_v<T>) {
        return std::to_string(val);
    } else {
        return std::string(val);
    }
}

int main() {
    // All computed at compile time
    static_assert(factorial(10) == 3628800);
    static_assert(hash_string("hello") != hash_string("world"));

    constexpr auto primes = make_sorted_primes();
    static_assert(primes[0] == 2 && primes[24] == 97);

    constexpr int sq = compile_time_only(7);  // OK
    // int x = 7; compile_time_only(x);  // ERROR: not a constant expression

    std::cout << serialize(42) << " " << serialize("hi") << "\n";
}
```

C++20 constexpr allows: loops, branches, local variables, `std::array`, `std::string` (transient), `std::vector` (transient), `try-catch`, virtual functions, and `dynamic_cast`. The key rule: any dynamic allocation must be freed within the same constexpr evaluation.'''
    ),
    (
        "cpp/ranges-views-cpp20",
        r'''How do C++20 ranges and views work? I want to chain transformations on a container without creating intermediate copies.''',
        r'''<think>
C++20 ranges and views are a major addition — lazy, composable range adaptors that
replace verbose iterator-based code. The user wants to understand the pipe syntax,
common views (filter, transform, take, etc.), and how laziness avoids copies.
I should show practical chaining examples and contrast with pre-ranges code.
This is intermediate-to-advanced C++20 material.
</think>

C++20 **ranges** provide lazy, composable views that transform data without copying. Chain them with the pipe (`|`) operator.

```cpp
#include <algorithm>
#include <iostream>
#include <ranges>
#include <string>
#include <vector>

int main() {
    std::vector<int> nums = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // Lazy pipeline: filter → transform → take
    auto result = nums
        | std::views::filter([](int n) { return n % 2 == 0; })  // 2,4,6,8,10
        | std::views::transform([](int n) { return n * n; })     // 4,16,36,64,100
        | std::views::take(3);                                    // 4,16,36

    for (int x : result) std::cout << x << " ";  // 4 16 36
    std::cout << "\n";

    // Views are lazy — nothing computed until iteration
    // No intermediate vectors are created!

    // Generate infinite sequences
    auto fibonacci = std::views::iota(0)
        | std::views::transform([a = 0, b = 1](int) mutable {
            int val = a; a = b; b = val + b; return val;
        })
        | std::views::take(10);

    // String processing
    std::vector<std::string> words = {"hello", "", "world", "", "foo", "bar"};
    auto non_empty_upper = words
        | std::views::filter([](const auto& s) { return !s.empty(); })
        | std::views::transform([](std::string s) {
            std::ranges::transform(s, s.begin(), ::toupper);
            return s;
        });

    for (const auto& w : non_empty_upper) std::cout << w << " ";
    // HELLO WORLD FOO BAR

    // Collect into a container (C++23: std::ranges::to)
    // C++20 workaround:
    auto evens = nums | std::views::filter([](int n) { return n % 2 == 0; });
    std::vector<int> even_vec(evens.begin(), evens.end());
}
```

Common views: `filter`, `transform`, `take`, `drop`, `reverse`, `split`, `join`, `zip` (C++23), `enumerate` (C++23), `iota` (range generator), `keys`/`values` (for maps).

Views are **non-owning** and **O(1)** to construct — all work happens during iteration.'''
    ),
    (
        "cpp/structured-bindings",
        r'''How do structured bindings work in C++17? Can I use them with my own types?''',
        r'''<think>
Structured bindings (C++17) allow decomposing aggregates, tuples, and pairs into
named variables. The user also wants to know how to make custom types work with
structured bindings. I need to cover arrays, structs, tuple-like types, and the
customization protocol (get<>, tuple_size, tuple_element). Intermediate topic.
</think>

C++17 **structured bindings** let you unpack aggregates, tuples, and pairs into named variables in a single declaration.

```cpp
#include <iostream>
#include <map>
#include <string>
#include <tuple>

// Works with structs (public members)
struct Point { double x, y, z; };

// Works with tuple-like types
auto get_stats(const std::vector<int>& v) {
    auto [mn, mx] = std::minmax_element(v.begin(), v.end());
    double avg = std::accumulate(v.begin(), v.end(), 0.0) / v.size();
    return std::tuple{*mn, *mx, avg};
}

// Custom type support — implement tuple protocol
struct Color {
    uint8_t r, g, b;
};

// Specialize in namespace std
namespace std {
    template<> struct tuple_size<Color> : integral_constant<size_t, 3> {};
    template<size_t I> struct tuple_element<I, Color> { using type = uint8_t; };
}

template <size_t I>
uint8_t get(const Color& c) {
    if constexpr (I == 0) return c.r;
    else if constexpr (I == 1) return c.g;
    else return c.b;
}

int main() {
    // Arrays
    int arr[] = {10, 20, 30};
    auto [a, b, c] = arr;

    // Structs
    Point p{1.0, 2.0, 3.0};
    auto& [x, y, z] = p;  // by reference — modifying x modifies p.x
    x = 99.0;
    std::cout << p.x << "\n";  // 99

    // Maps — clean iteration
    std::map<std::string, int> scores = {{"Alice", 95}, {"Bob", 87}};
    for (const auto& [name, score] : scores) {
        std::cout << name << ": " << score << "\n";
    }

    // Tuples
    auto [min_val, max_val, average] = get_stats({3, 1, 4, 1, 5, 9});
    std::cout << "min=" << min_val << " max=" << max_val << "\n";

    // Custom type
    Color red{255, 0, 0};
    auto [r, g, bl] = red;
    std::cout << "R=" << (int)r << "\n";
}
```

Binding modes: `auto [a,b]` (copy), `auto& [a,b]` (lvalue ref), `const auto& [a,b]` (const ref). The number of bindings must exactly match the number of elements.'''
    ),
    (
        "cpp/fold-expressions",
        r'''Show me how C++17 fold expressions work with variadic templates. I want to sum arguments and also print them with a separator.''',
        r'''<think>
Fold expressions (C++17) apply a binary operator across a parameter pack without
recursion. There are four forms: unary left, unary right, binary left, binary right.
The user wants practical examples — sum and printing with separators. I should show
all four forms briefly and then the practical cases. Intermediate topic.
</think>

C++17 **fold expressions** apply an operator across a parameter pack in a single expression — no recursion needed.

```cpp
#include <iostream>
#include <string>
#include <type_traits>

// Unary left fold: (... op pack) → ((p1 op p2) op p3) ...
template <typename... Args>
auto sum(Args... args) {
    return (... + args);  // ((a1 + a2) + a3) + ...
}

// Unary right fold: (pack op ...) → p1 op (p2 op (p3 op ...))
template <typename... Args>
auto right_sub(Args... args) {
    return (args - ...);  // a1 - (a2 - (a3 - ...))
}

// Print with separator using comma operator fold
template <typename... Args>
void print(const Args&... args) {
    ((std::cout << args << " "), ...);
    std::cout << "\n";
}

// Print with custom separator (binary fold)
template <typename... Args>
void print_csv(const Args&... args) {
    bool first = true;
    auto emit = [&](const auto& arg) {
        if (!first) std::cout << ", ";
        std::cout << arg;
        first = false;
    };
    (emit(args), ...);
    std::cout << "\n";
}

// All-of / any-of checks
template <typename... Args>
bool all_positive(Args... args) {
    return (... && (args > 0));  // (a1>0) && (a2>0) && ...
}

template <typename... Args>
bool any_zero(Args... args) {
    return (... || (args == 0));
}

// Fold over comma to call a function on each argument
template <typename F, typename... Args>
void for_each_arg(F&& f, Args&&... args) {
    (f(std::forward<Args>(args)), ...);
}

int main() {
    std::cout << sum(1, 2, 3, 4, 5) << "\n";     // 15
    std::cout << sum(1.5, 2.5, 3.0) << "\n";      // 7.0

    print("hello", 42, 3.14, 'x');                 // hello 42 3.14 x
    print_csv("Alice", 95, "Bob", 87);             // Alice, 95, Bob, 87

    std::cout << all_positive(1, 2, 3) << "\n";    // 1
    std::cout << any_zero(1, 0, 3) << "\n";        // 1

    for_each_arg([](auto x) { std::cout << x * 2 << " "; }, 1, 2, 3);
    // 2 4 6
}
```

Four fold forms:
| Syntax | Name | Expansion |
|---|---|---|
| `(... op pack)` | Unary left | `((p1 op p2) op p3)...` |
| `(pack op ...)` | Unary right | `p1 op (p2 op (p3...))` |
| `(init op ... op pack)` | Binary left | `((init op p1) op p2)...` |
| `(pack op ... op init)` | Binary right | `p1 op (p2 op (... init))` |'''
    ),
    (
        "cpp/generic-lambdas-captures",
        r'''How do C++14/20 generic lambdas work, especially with captures? Can I capture a move-only type into a lambda?''',
        r'''<think>
Generic lambdas (auto parameters) were C++14, template lambdas were C++20. The user
also asks about capturing move-only types — that requires init captures (C++14).
I should show auto lambdas, template parameter lambdas, init captures for moves,
and mutable lambdas. Intermediate level.
</think>

**Generic lambdas** use `auto` (C++14) or explicit template syntax (C++20) for parameters. **Init captures** (C++14) let you move objects into lambdas.

```cpp
#include <algorithm>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

int main() {
    // C++14: auto parameters → compiler generates a template operator()
    auto add = [](auto a, auto b) { return a + b; };
    std::cout << add(1, 2) << "\n";           // 3
    std::cout << add(1.5, 2.5) << "\n";       // 4.0
    std::cout << add(std::string("hi"), "!") << "\n"; // hi!

    // C++20: explicit template parameters on lambdas
    auto max_of = []<typename T>(const std::vector<T>& v) -> T {
        return *std::max_element(v.begin(), v.end());
    };
    std::cout << max_of(std::vector{3, 1, 4, 1, 5}) << "\n";  // 5

    // Init capture — move a unique_ptr into the lambda
    auto ptr = std::make_unique<std::string>("owned data");
    auto consumer = [p = std::move(ptr)]() {
        std::cout << "Lambda owns: " << *p << "\n";
    };
    // ptr is now null — ownership transferred to lambda
    consumer();

    // Mutable lambda — allows modifying captured-by-value variables
    int counter = 0;
    auto inc = [counter]() mutable { return ++counter; };
    std::cout << inc() << inc() << inc() << "\n";  // 123
    // original counter is still 0

    // Capture with transformation
    std::vector<std::string> names = {"alice", "bob", "charlie"};
    std::string prefix = "user_";
    auto prefixed = [pfx = std::move(prefix)](const std::string& name) {
        return pfx + name;
    };
    // prefix is now empty, pfx lives inside the lambda

    for (const auto& n : names)
        std::cout << prefixed(n) << " ";  // user_alice user_bob user_charlie
}
```

Key captures:
- `[x]` — copy
- `[&x]` — reference
- `[x = std::move(obj)]` — init capture (move into lambda)
- `[x = expr]` — init capture with any expression
- `[this]` — captures `this` pointer
- `[*this]` — captures a **copy** of `*this` (C++17, safe for async)'''
    ),
    (
        "cpp/optional-usage",
        r'''When should I use std::optional and what are the best practices for working with it?''',
        r'''<think>
std::optional represents a value that may or may not be present — a safer alternative
to sentinel values, null pointers, or output parameters. I should show construction,
access patterns, monadic operations (C++23), and common pitfalls. Intermediate topic.
</think>

`std::optional<T>` represents a value that might not exist — replacing nullptrs, sentinel values (`-1`, `""`) and boolean out-parameters.

```cpp
#include <iostream>
#include <optional>
#include <string>
#include <map>
#include <charconv>

// Return optional instead of sentinel values
std::optional<int> parse_int(std::string_view sv) {
    int result{};
    auto [ptr, ec] = std::from_chars(sv.data(), sv.data() + sv.size(), result);
    if (ec == std::errc{} && ptr == sv.data() + sv.size())
        return result;
    return std::nullopt;
}

// Optional for map lookups
std::optional<std::string> find_user(const std::map<int, std::string>& db, int id) {
    auto it = db.find(id);
    if (it != db.end()) return it->second;
    return std::nullopt;
}

int main() {
    // Construction
    std::optional<int> a = 42;
    std::optional<int> b = std::nullopt;
    std::optional<std::string> c = std::make_optional("hello");

    // Safe access
    if (auto val = parse_int("123")) {
        std::cout << "Parsed: " << *val << "\n";   // 123
    }

    auto bad = parse_int("abc");
    std::cout << bad.value_or(-1) << "\n";          // -1 (fallback)

    // has_value() check
    if (!bad.has_value()) {
        std::cout << "Parse failed\n";
    }

    // value() throws std::bad_optional_access if empty
    try {
        [[maybe_unused]] auto v = bad.value();
    } catch (const std::bad_optional_access&) {
        std::cout << "Caught bad access\n";
    }

    // C++23 monadic operations (transform, and_then, or_else)
    // auto result = parse_int("42")
    //     .transform([](int n) { return n * 2; })        // optional<int>{84}
    //     .and_then([](int n) -> std::optional<int> {     // chain optionals
    //         return n > 0 ? std::optional{n} : std::nullopt;
    //     })
    //     .or_else([] { return std::optional{0}; });      // fallback

    // In-place construction (avoid creating temporary)
    std::optional<std::string> s(std::in_place, 5, 'x');  // "xxxxx"
}
```

Best practices:
- Prefer `if (auto val = func())` pattern for clean access
- Use `value_or()` for defaults instead of manual checks
- **Don't** use `optional<T&>` — it doesn't exist. Use `T*` for optional references
- **Don't** use `optional<bool>` — three-state logic is confusing. Use an enum instead
- Avoid `.value()` without checking — prefer `*opt` after an `if` check'''
    ),
    (
        "cpp/variant-visit",
        r'''How do I use std::variant and std::visit to implement a type-safe union? I want to avoid the old-style C union.''',
        r'''<think>
std::variant is a type-safe discriminated union — it holds exactly one of its alternative
types at any time. std::visit dispatches to the correct handler via a visitor (overloaded
callable). I should show basic usage, the overloaded lambda pattern, and practical use
cases like AST nodes or state machines. Advanced topic.
</think>

`std::variant` is a type-safe union that knows which type it holds. `std::visit` dispatches a visitor to handle each alternative.

```cpp
#include <iostream>
#include <string>
#include <variant>
#include <vector>

// Overloaded helper — combines multiple lambdas into one visitor
template <class... Ts>
struct overloaded : Ts... { using Ts::operator()...; };
template <class... Ts> overloaded(Ts...) -> overloaded<Ts...>; // CTAD guide

// Type-safe AST node
using Expr = std::variant<int, double, std::string>;

std::string to_string(const Expr& expr) {
    return std::visit(overloaded{
        [](int i)                { return std::to_string(i); },
        [](double d)             { return std::to_string(d); },
        [](const std::string& s) { return "\"" + s + "\""; },
    }, expr);
}

// Pattern: result-or-error (before C++23 std::expected)
using Result = std::variant<double, std::string>;  // value or error message

Result safe_sqrt(double x) {
    if (x < 0) return std::string("Cannot sqrt negative number");
    return std::sqrt(x);
}

// State machine with variant
struct Idle {};
struct Loading { std::string url; };
struct Ready { std::string data; };
struct Error { std::string msg; };

using State = std::variant<Idle, Loading, Ready, Error>;

void describe_state(const State& s) {
    std::visit(overloaded{
        [](const Idle&)     { std::cout << "Idle\n"; },
        [](const Loading& l){ std::cout << "Loading " << l.url << "\n"; },
        [](const Ready& r)  { std::cout << "Ready: " << r.data.size() << " bytes\n"; },
        [](const Error& e)  { std::cout << "Error: " << e.msg << "\n"; },
    }, s);
}

int main() {
    // Basic usage
    std::vector<Expr> exprs = {42, 3.14, std::string("hello")};
    for (const auto& e : exprs)
        std::cout << to_string(e) << " ";  // 42 3.140000 "hello"
    std::cout << "\n";

    // Check which type is active
    Expr e = 42;
    if (std::holds_alternative<int>(e))
        std::cout << "It's an int: " << std::get<int>(e) << "\n";

    // get_if returns pointer (null if wrong type — no exception)
    if (auto* p = std::get_if<double>(&e))
        std::cout << *p << "\n";  // not reached

    // State machine
    State s = Loading{"https://api.example.com"};
    describe_state(s);  // Loading https://api.example.com
}
```

The `overloaded` pattern with CTAD (class template argument deduction) is the idiomatic way to build visitors from lambdas. Variant never holds "nothing" — if you need an empty state, add `std::monostate` as the first alternative.'''
    ),
    (
        "cpp/expected-cpp23",
        r'''What is std::expected in C++23 and how does it compare to using exceptions or std::optional for error handling?''',
        r'''<think>
std::expected<T, E> is C++23's answer to Rust's Result<T, E> — it holds either a
value or an error, with monadic operations. It's better than optional (which can't
carry error info) and better than exceptions for expected error paths. I should
show the basic API, monadic chaining, and compare with alternatives. Advanced topic.
</think>

`std::expected<T, E>` (C++23) holds either a success value of type `T` or an error of type `E` — similar to Rust's `Result<T, E>`.

```cpp
#include <expected>
#include <iostream>
#include <string>
#include <fstream>
#include <charconv>

enum class ParseError { Empty, InvalidChar, Overflow };

std::string to_string(ParseError e) {
    switch (e) {
        case ParseError::Empty:       return "empty input";
        case ParseError::InvalidChar: return "invalid character";
        case ParseError::Overflow:    return "overflow";
    }
    return "unknown";
}

// Return expected instead of throwing
std::expected<int, ParseError> parse_port(std::string_view sv) {
    if (sv.empty()) return std::unexpected(ParseError::Empty);

    int result{};
    auto [ptr, ec] = std::from_chars(sv.data(), sv.data() + sv.size(), result);

    if (ec == std::errc::result_out_of_range)
        return std::unexpected(ParseError::Overflow);
    if (ec != std::errc{} || ptr != sv.data() + sv.size())
        return std::unexpected(ParseError::InvalidChar);
    if (result < 0 || result > 65535)
        return std::unexpected(ParseError::Overflow);

    return result;
}

std::expected<std::string, std::string> connect(int port) {
    if (port == 0) return std::unexpected("Cannot connect to port 0");
    return "Connected to port " + std::to_string(port);
}

int main() {
    // Basic usage
    auto result = parse_port("8080");
    if (result) {
        std::cout << "Port: " << *result << "\n";  // Port: 8080
    }

    auto bad = parse_port("abc");
    if (!bad) {
        std::cout << "Error: " << to_string(bad.error()) << "\n";
        // Error: invalid character
    }

    // value_or fallback
    int port = parse_port("invalid").value_or(3000);
    std::cout << "Using port: " << port << "\n";  // 3000

    // Monadic chaining (C++23)
    auto msg = parse_port("443")
        .transform([](int p) { return "https://localhost:" + std::to_string(p); })
        .transform_error([](ParseError e) { return to_string(e); });

    if (msg) std::cout << *msg << "\n";  // https://localhost:443

    // and_then chains expected-returning functions
    auto chain = parse_port("8080")
        .and_then([](int p) -> std::expected<std::string, std::string> {
            return connect(p);
        });

    if (chain) std::cout << *chain << "\n";  // Connected to port 8080
}
```

Comparison:
| Mechanism | Carries error info | Zero-cost happy path | Composable |
|---|---|---|---|
| Exceptions | Yes | No (table overhead) | No |
| `std::optional` | No (just "empty") | Yes | C++23 monadic |
| `std::expected` | Yes (typed error) | Yes | Yes (monadic) |
| Error codes | Yes (int) | Yes | No |

Use `expected` for **anticipated failures** (parsing, I/O, validation). Keep exceptions for truly exceptional situations (out of memory, logic bugs).'''
    ),
    (
        "cpp/string-view-zero-copy",
        r'''When should I use std::string_view and what are the pitfalls? I heard it can cause dangling references.''',
        r'''<think>
string_view is a non-owning reference to a string — great for read-only parameters
and zero-copy substrings. The main pitfall is lifetime — if the underlying string is
destroyed, the view dangles. I should show correct usage patterns, the dangling trap,
and when NOT to use it. Intermediate topic.
</think>

`std::string_view` is a non-owning, read-only view into a contiguous character sequence — zero-copy and lightweight (just a pointer + size).

```cpp
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

// Perfect for read-only parameters — accepts string, string_view, char*, literals
void log_message(std::string_view msg) {
    std::cout << "[LOG] " << msg << "\n";
}

// Zero-copy tokenizer
std::vector<std::string_view> split(std::string_view sv, char delim) {
    std::vector<std::string_view> tokens;
    while (!sv.empty()) {
        auto pos = sv.find(delim);
        tokens.push_back(sv.substr(0, pos));
        sv.remove_prefix(pos == std::string_view::npos ? sv.size() : pos + 1);
    }
    return tokens;
}

// Efficient prefix/suffix checks (no allocation)
bool has_extension(std::string_view filename, std::string_view ext) {
    return filename.size() >= ext.size() &&
           filename.substr(filename.size() - ext.size()) == ext;
}

int main() {
    // Accepts anything string-like — no copies
    log_message("literal");                        // const char*
    log_message(std::string("std::string"));       // std::string
    log_message(std::string_view("view"));         // string_view

    // Zero-copy splitting
    std::string csv = "alice,bob,charlie,dave";
    auto names = split(csv, ',');  // views INTO csv — no allocations
    for (auto name : names) std::cout << name << " ";
    std::cout << "\n";

    // Substrings are O(1), not O(n)
    std::string_view sv = "hello world";
    auto word = sv.substr(0, 5);   // just adjusts pointer+size
    std::cout << word << "\n";     // hello

    std::cout << has_extension("photo.jpg", ".jpg") << "\n";  // 1
}
```

**Dangling reference pitfall:**
```cpp
// DANGER: returning view into temporary
std::string_view bad() {
    std::string s = "temporary";
    return s;  // s destroyed → dangling view!
}

// DANGER: view into moved-from string
std::string original = "data";
std::string_view sv = original;
std::string other = std::move(original);  // original may be empty now
// sv might be dangling!
```

Rules:
- Use `string_view` for **function parameters** that only read the string
- **Never** return `string_view` to a local string
- **Never** store `string_view` as a class member unless you guarantee the source outlives it
- If you need to own the data, use `std::string`
- `string_view` is **not null-terminated** — don't pass `.data()` to C APIs expecting `\0`'''
    ),
    (
        "cpp/span-array-view",
        r'''What is std::span and how do I use it to write functions that accept any contiguous container?''',
        r'''<think>
std::span (C++20) is the array equivalent of string_view — a non-owning view over
contiguous memory. It works with vectors, arrays, C arrays, etc. I should show
static and dynamic extent, how it unifies function interfaces, and the same lifetime
caveats as string_view. Intermediate topic.
</think>

`std::span<T>` (C++20) is a non-owning view over contiguous elements — the generalized version of `string_view` for any type.

```cpp
#include <algorithm>
#include <array>
#include <iostream>
#include <numeric>
#include <span>
#include <vector>

// One function handles vector, array, C array — anything contiguous
double average(std::span<const int> data) {
    if (data.empty()) return 0.0;
    return std::accumulate(data.begin(), data.end(), 0.0) / data.size();
}

// Mutable span — modify elements in-place
void fill_ascending(std::span<int> data) {
    std::iota(data.begin(), data.end(), 1);
}

// Fixed-size span (compile-time size check)
void process_rgb(std::span<uint8_t, 3> pixel) {
    std::cout << "R=" << (int)pixel[0]
              << " G=" << (int)pixel[1]
              << " B=" << (int)pixel[2] << "\n";
}

// Subspans — zero-copy slicing
void print_span(std::span<const int> data) {
    for (int x : data) std::cout << x << " ";
    std::cout << "\n";
}

int main() {
    // Works with everything contiguous
    std::vector<int> vec = {1, 2, 3, 4, 5};
    std::array<int, 4> arr = {10, 20, 30, 40};
    int c_arr[] = {100, 200, 300};

    std::cout << average(vec) << "\n";     // 3
    std::cout << average(arr) << "\n";     // 25
    std::cout << average(c_arr) << "\n";   // 200

    // Mutable access
    fill_ascending(vec);  // vec = {1, 2, 3, 4, 5}

    // Static extent
    std::array<uint8_t, 3> pixel = {255, 128, 0};
    process_rgb(pixel);  // R=255 G=128 B=0
    // process_rgb(vec);  // compile error: wrong size

    // Subspan slicing (O(1))
    std::vector<int> nums = {10, 20, 30, 40, 50, 60};
    std::span<int> all(nums);
    print_span(all.first(3));                // 10 20 30
    print_span(all.last(2));                 // 50 60
    print_span(all.subspan(2, 3));           // 30 40 50

    // Size info
    std::cout << "size: " << all.size() << "\n";
    std::cout << "bytes: " << all.size_bytes() << "\n";
}
```

`span<T>` = dynamic extent (size at runtime). `span<T, N>` = static extent (size known at compile time — enables bounds checking).

Same lifetime rules as `string_view` — the span does not own the data. Never return a span to a local container.'''
    ),
    (
        "cpp/format-cpp20",
        r'''How does std::format work in C++20? I'm tired of iostream formatting verbosity.''',
        r'''<think>
std::format (C++20) brings Python-like string formatting to C++. It's type-safe,
extensible, and much cleaner than iostream manipulators or printf. I should show
basic formatting, alignment, custom format specifiers, and how to extend it for
user types. Intermediate topic.
</think>

`std::format` (C++20) provides Python-like, type-safe string formatting — a modern replacement for both `printf` and iostream manipulators.

```cpp
#include <format>
#include <iostream>
#include <string>
#include <vector>
#include <chrono>

struct Point {
    double x, y;
};

// Custom formatter for user types
template <>
struct std::formatter<Point> {
    bool verbose = false;

    constexpr auto parse(std::format_parse_context& ctx) {
        auto it = ctx.begin();
        if (it != ctx.end() && *it == 'v') {  // {:v} for verbose
            verbose = true;
            ++it;
        }
        return it;
    }

    auto format(const Point& p, std::format_context& ctx) const {
        if (verbose)
            return std::format_to(ctx.out(), "Point(x={:.2f}, y={:.2f})", p.x, p.y);
        return std::format_to(ctx.out(), "({:.2f}, {:.2f})", p.x, p.y);
    }
};

int main() {
    // Basic substitution
    std::cout << std::format("Hello, {}!\n", "world");

    // Positional and type formatting
    std::cout << std::format("{0} + {0} = {1}\n", 21, 42);

    // Number formatting
    std::cout << std::format("int: {:>10d}\n", 42);        //         42
    std::cout << std::format("hex: {:#x}\n", 255);         // 0xff
    std::cout << std::format("bin: {:#010b}\n", 42);       // 0b00101010
    std::cout << std::format("float: {:.3f}\n", 3.14159);  // 3.142
    std::cout << std::format("sci: {:e}\n", 1234567.89);   // 1.234568e+06

    // Alignment and fill
    std::cout << std::format("|{:<15}|\n", "left");        // |left           |
    std::cout << std::format("|{:>15}|\n", "right");       // |          right|
    std::cout << std::format("|{:^15}|\n", "center");      // |    center     |
    std::cout << std::format("|{:*^15}|\n", "star");       // |*****star******|

    // Custom type
    Point p{3.14159, 2.71828};
    std::cout << std::format("Short: {}\n", p);    // (3.14, 2.72)
    std::cout << std::format("Long: {:v}\n", p);   // Point(x=3.14, y=2.72)

    // std::print (C++23) — direct formatted output
    // std::print("No more << chaining: {} {}\n", "hello", 42);

    // Format to string
    auto msg = std::format("Status: {} ({})", "OK", 200);
}
```

`std::format` advantages over alternatives:
- **vs printf**: type-safe (no `%d`/`%s` mismatches), supports custom types
- **vs iostream**: concise, no `<<` chaining, no manipulator state leakage
- **Performance**: typically faster than iostream, competitive with printf

C++23 adds `std::print` / `std::println` for direct output without `std::cout <<`.'''
    ),
    (
        "cpp/thread-concurrency",
        r'''How do I use std::thread for basic concurrency in C++? What are the common pitfalls?''',
        r'''<think>
std::thread basics — creating threads, joining, detaching, passing arguments,
sharing data with mutexes. I need to cover the common pitfalls: forgetting to join,
data races, passing references incorrectly. Intermediate level.
</think>

`std::thread` launches OS threads. The key rules: always join or detach, protect shared data, pass references explicitly.

```cpp
#include <iostream>
#include <thread>
#include <vector>
#include <mutex>
#include <numeric>

std::mutex cout_mtx;  // protect std::cout (it's not thread-safe)

void worker(int id, const std::string& task) {
    // Simulate work
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    std::lock_guard lock(cout_mtx);
    std::cout << "Thread " << id << " completed: " << task << "\n";
}

// Shared state with mutex
struct Counter {
    int value = 0;
    std::mutex mtx;

    void increment(int times) {
        for (int i = 0; i < times; ++i) {
            std::lock_guard lock(mtx);
            ++value;
        }
    }
};

int main() {
    // Basic thread creation
    std::thread t1(worker, 1, "download");
    std::thread t2(worker, 2, "parse");

    t1.join();  // wait for completion
    t2.join();  // MUST join or detach before destruction

    // Pass by reference — must use std::ref
    Counter counter;
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back(&Counter::increment, std::ref(counter), 10000);
    }
    for (auto& t : threads) t.join();
    std::cout << "Counter: " << counter.value << "\n";  // exactly 40000

    // Lambda threads
    int result = 0;
    std::mutex result_mtx;
    std::vector<std::thread> pool;
    for (int i = 0; i < 8; ++i) {
        pool.emplace_back([i, &result, &result_mtx] {
            int local = i * i;  // compute locally, lock briefly
            std::lock_guard lock(result_mtx);
            result += local;
        });
    }
    for (auto& t : pool) t.join();
    std::cout << "Sum of squares: " << result << "\n";  // 140

    // Hardware concurrency hint
    std::cout << "Cores: " << std::thread::hardware_concurrency() << "\n";
}
```

Common pitfalls:
- **Forgetting join/detach** → `std::terminate()` called on thread destructor
- **Passing references** without `std::ref()` → thread gets a copy, not a reference
- **Data races** → always protect shared data with a mutex or atomic
- **Deadlock** → use `std::scoped_lock(mtx1, mtx2)` for multiple mutexes
- **Exception safety** → if an exception is thrown before `join()`, the thread is abandoned. Use `std::jthread` (C++20) instead'''
    ),
    (
        "cpp/async-futures",
        r'''How do std::async and futures work? When should I use async instead of raw threads?''',
        r'''<think>
std::async provides a higher-level abstraction than std::thread — it returns a future
that holds the result. The user wants to know when to prefer it. I should cover
launch policies, future::get(), shared_future, and the advantages over raw threads.
Intermediate-to-advanced topic.
</think>

`std::async` launches a task and returns a `std::future` holding the result — higher-level than raw threads with automatic result propagation and exception forwarding.

```cpp
#include <chrono>
#include <cmath>
#include <future>
#include <iostream>
#include <numeric>
#include <vector>
#include <string>

// Expensive computation
double heavy_calculation(int n) {
    double sum = 0;
    for (int i = 1; i <= n; ++i)
        sum += std::sin(i) * std::cos(i);
    return sum;
}

// Function that might fail
std::string fetch_data(const std::string& url) {
    if (url.empty()) throw std::runtime_error("empty URL");
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    return "data from " + url;
}

// Parallel reduce
template <typename Iter>
double parallel_sum(Iter begin, Iter end) {
    auto len = std::distance(begin, end);
    if (len < 10000) return std::accumulate(begin, end, 0.0);

    auto mid = begin + len / 2;
    auto left = std::async(std::launch::async, parallel_sum<Iter>, begin, mid);
    double right = parallel_sum(mid, end);  // compute right half in this thread
    return left.get() + right;
}

int main() {
    // Launch async tasks
    auto f1 = std::async(std::launch::async, heavy_calculation, 1'000'000);
    auto f2 = std::async(std::launch::async, heavy_calculation, 2'000'000);

    // Do other work while tasks run...
    std::cout << "Computing...\n";

    // .get() blocks until result is ready
    double r1 = f1.get();
    double r2 = f2.get();
    std::cout << "Results: " << r1 << ", " << r2 << "\n";

    // Exception propagation through futures
    auto f3 = std::async(std::launch::async, fetch_data, "");
    try {
        auto data = f3.get();  // rethrows the exception from the task
    } catch (const std::runtime_error& e) {
        std::cout << "Caught: " << e.what() << "\n";
    }

    // Launch policies
    auto eager = std::async(std::launch::async, [] { return 1; });  // new thread
    auto lazy  = std::async(std::launch::deferred, [] { return 2; }); // runs on get()
    auto maybe = std::async([] { return 3; });  // implementation decides

    // Parallel reduce
    std::vector<double> data(100000, 1.0);
    std::cout << "Sum: " << parallel_sum(data.begin(), data.end()) << "\n";
}
```

`std::async` vs `std::thread`:
| Feature | `std::thread` | `std::async` |
|---|---|---|
| Return value | Manual (shared variable) | Via `std::future` |
| Exception propagation | Crashes thread | Forwarded to `.get()` |
| Thread management | Manual join/detach | Automatic |
| Deferred execution | No | `launch::deferred` |

Use `async` when you want a **result**. Use raw threads for long-running background work or when you need precise thread control.'''
    ),
    (
        "cpp/jthread-stop-token",
        r'''What is std::jthread and how do stop tokens work for cooperative cancellation in C++20?''',
        r'''<think>
std::jthread (C++20) is an improved thread that auto-joins on destruction and supports
cooperative cancellation via stop_token. This solves two major std::thread problems:
forgetting to join and the lack of a standard cancellation mechanism. Advanced topic.
</think>

`std::jthread` (C++20) auto-joins on destruction and provides **cooperative cancellation** via `std::stop_token` — solving the two biggest `std::thread` pain points.

```cpp
#include <chrono>
#include <iostream>
#include <thread>
#include <vector>
#include <queue>
#include <mutex>
#include <condition_variable>

// Worker that checks for cancellation
void polling_worker(std::stop_token stoken, int id) {
    while (!stoken.stop_requested()) {
        std::cout << "Worker " << id << " polling...\n";
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Worker " << id << " stopped cleanly\n";
}

// Interruptible condition_variable wait
void event_worker(std::stop_token stoken) {
    std::mutex mtx;
    std::condition_variable_any cv;

    std::unique_lock lock(mtx);
    // Wakes on stop request OR condition — no manual flag needed
    bool stopped = cv.wait(lock, stoken, [] { return false; /* never true */ });
    // Returns false if stopped via token
    std::cout << "Event worker: " << (stopped ? "condition met" : "cancelled") << "\n";
}

// Stop callback — run cleanup when stop is requested
void worker_with_cleanup(std::stop_token stoken) {
    std::stop_callback cleanup(stoken, [] {
        std::cout << "Cleanup callback triggered\n";
    });

    while (!stoken.stop_requested()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

int main() {
    {
        // Auto-join on scope exit — no more std::terminate crashes
        std::jthread t1(polling_worker, 1);
        std::jthread t2(polling_worker, 2);
        std::jthread t3(event_worker);

        std::this_thread::sleep_for(std::chrono::seconds(1));

        // Request stop on specific thread
        t1.request_stop();

        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        // t2 and t3 auto-stopped when jthread destructor calls request_stop()
    }
    // All threads joined here — guaranteed

    std::cout << "All threads done\n";

    // Access the stop source for external control
    std::jthread worker([](std::stop_token st) {
        while (!st.stop_requested()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    });

    auto source = worker.get_stop_source();
    source.request_stop();  // can stop from outside via the source
    // worker auto-joins on destruction
}
```

`jthread` vs `thread`:
| Feature | `std::thread` | `std::jthread` |
|---|---|---|
| Auto-join | No (terminates!) | Yes (destructor joins) |
| Cancellation | Manual (bool flag) | Built-in `stop_token` |
| Move-only | Yes | Yes |
| `condition_variable` | Manual flag + notify | `cv.wait(lock, stoken, pred)` |

The first parameter of the callable can optionally be `std::stop_token` — jthread passes it automatically. If your callable doesn't take a `stop_token`, jthread still auto-joins but you can't use cooperative cancellation.'''
    ),
    (
        "cpp/atomics-memory-ordering",
        r'''Explain C++ atomics and memory ordering. When do I need something other than the default memory_order_seq_cst?''',
        r'''<think>
Atomics and memory ordering are expert-level C++. The user needs to understand what
atomic operations guarantee, the different memory orderings, and when relaxed ordering
is appropriate vs sequential consistency. I should show practical examples: counters,
flags, and the classic producer-consumer pattern with acquire/release. Keep it concrete
rather than purely theoretical.
</think>

`std::atomic<T>` provides lock-free operations with configurable memory ordering. The default (`seq_cst`) is safest but most restrictive — weaker orderings can improve performance on weak-memory architectures (ARM, RISC-V).

```cpp
#include <atomic>
#include <iostream>
#include <thread>
#include <vector>
#include <cassert>

// 1. Relaxed — only guarantees atomicity, no ordering
// Use for: counters where you don't care about ordering with other data
std::atomic<int> counter{0};

void count_relaxed(int n) {
    for (int i = 0; i < n; ++i)
        counter.fetch_add(1, std::memory_order_relaxed);
}

// 2. Acquire/Release — establishes happens-before between producer and consumer
// Use for: flags, publication patterns
std::atomic<bool> ready{false};
int payload = 0;  // non-atomic, protected by acquire/release on 'ready'

void producer() {
    payload = 42;                                      // (1) write payload
    ready.store(true, std::memory_order_release);      // (2) publish — (1) visible before (2)
}

void consumer() {
    while (!ready.load(std::memory_order_acquire)) {}  // (3) acquire — sees all writes before (2)
    assert(payload == 42);                              // guaranteed to see 42
}

// 3. Sequential consistency (default) — total global order
// Use for: simple cases where performance isn't critical
std::atomic<int> x{0}, y{0};
int r1 = 0, r2 = 0;

void thread_a() { x.store(1); r1 = y.load(); }  // seq_cst by default
void thread_b() { y.store(1); r2 = x.load(); }
// seq_cst guarantees: r1 == 0 && r2 == 0 is impossible

// 4. Compare-and-swap (CAS) — building block for lock-free algorithms
std::atomic<int> shared_max{0};

void update_max(int val) {
    int current = shared_max.load(std::memory_order_relaxed);
    while (current < val &&
           !shared_max.compare_exchange_weak(
               current, val,
               std::memory_order_release,
               std::memory_order_relaxed)) {
        // current is updated to latest value on failure — retry
    }
}

int main() {
    // Relaxed counter
    std::vector<std::thread> threads;
    for (int i = 0; i < 8; ++i)
        threads.emplace_back(count_relaxed, 100000);
    for (auto& t : threads) t.join();
    std::cout << "Counter: " << counter << "\n";  // exactly 800000

    // Acquire/release
    std::thread p(producer), c(consumer);
    p.join(); c.join();
    std::cout << "Payload received: " << payload << "\n";

    // Lock-free max
    std::vector<std::thread> maxers;
    for (int v : {5, 3, 9, 1, 7, 8})
        maxers.emplace_back(update_max, v);
    for (auto& t : maxers) t.join();
    std::cout << "Max: " << shared_max << "\n";  // 9
}
```

Memory ordering cheat sheet:
| Ordering | Guarantee | Use case |
|---|---|---|
| `relaxed` | Atomicity only | Counters, statistics |
| `acquire` | Reads after this see prior writes | Consumer reads flag |
| `release` | Writes before this visible to acquirer | Producer sets flag |
| `acq_rel` | Both acquire + release | Read-modify-write on shared data |
| `seq_cst` | Total global order (default) | When in doubt |

**Rule**: start with `seq_cst` (the default). Only weaken to `acquire`/`release` or `relaxed` when profiling shows it matters — and prove correctness carefully.'''
    ),
    (
        "cpp/lock-free-queue",
        r'''How do I implement a simple lock-free queue in C++ using atomics? I need a single-producer single-consumer (SPSC) ring buffer.''',
        r'''<think>
A lock-free SPSC ring buffer is the simplest useful lock-free data structure. It uses
two atomic indices (head and tail) with acquire/release ordering. The producer writes
at tail, consumer reads at head. No CAS needed because only one thread modifies each
index. This is an expert-level topic — I need to be precise about memory ordering
and explain why this specific design is correct.
</think>

A **single-producer single-consumer (SPSC) ring buffer** is the simplest practical lock-free structure. Only one thread writes each index, so no CAS is needed — just acquire/release ordering.

```cpp
#include <atomic>
#include <array>
#include <optional>
#include <cassert>
#include <iostream>
#include <thread>
#include <chrono>

template <typename T, size_t Capacity>
class SPSCQueue {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");

    std::array<T, Capacity> buffer_;
    alignas(64) std::atomic<size_t> head_{0};  // consumer reads here
    alignas(64) std::atomic<size_t> tail_{0};  // producer writes here
    // alignas(64) prevents false sharing between head_ and tail_

    size_t mask(size_t idx) const { return idx & (Capacity - 1); }

public:
    // Producer only
    bool try_push(const T& item) {
        size_t tail = tail_.load(std::memory_order_relaxed);  // only producer writes tail
        size_t next = tail + 1;

        // Check if full: if next slot is where consumer is reading
        if (mask(next) == mask(head_.load(std::memory_order_acquire))) {
            return false;  // queue full
        }

        buffer_[mask(tail)] = item;
        tail_.store(next, std::memory_order_release);  // publish the write
        return true;
    }

    // Consumer only
    std::optional<T> try_pop() {
        size_t head = head_.load(std::memory_order_relaxed);  // only consumer writes head

        // Check if empty
        if (mask(head) == mask(tail_.load(std::memory_order_acquire))) {
            return std::nullopt;  // queue empty
        }

        T item = buffer_[mask(head)];
        head_.store(head + 1, std::memory_order_release);  // advance read position
        return item;
    }

    bool empty() const {
        return head_.load(std::memory_order_acquire) ==
               tail_.load(std::memory_order_acquire);
    }

    size_t size_approx() const {
        return tail_.load(std::memory_order_relaxed) -
               head_.load(std::memory_order_relaxed);
    }
};

int main() {
    SPSCQueue<int, 1024> queue;
    constexpr int N = 1'000'000;

    // Producer thread
    std::thread producer([&] {
        for (int i = 0; i < N; ++i) {
            while (!queue.try_push(i)) {
                // spin — in production use _mm_pause() or yield
            }
        }
    });

    // Consumer thread
    int sum = 0;
    int count = 0;
    std::thread consumer([&] {
        while (count < N) {
            if (auto val = queue.try_pop()) {
                sum += *val;
                ++count;
            }
        }
    });

    producer.join();
    consumer.join();

    long long expected = (long long)(N - 1) * N / 2;
    std::cout << "Sum: " << sum << " (overflow expected for large N)\n";
    std::cout << "Count: " << count << "\n";
    assert(count == N);
    std::cout << "All " << N << " items transferred correctly\n";
}
```

Why this works without locks:
- **Single producer** → only one thread writes `tail_` → no CAS needed
- **Single consumer** → only one thread writes `head_` → no CAS needed
- **Release on write** → buffer contents visible to the other thread
- **Acquire on read** → sees all writes before the release store
- **`alignas(64)`** → prevents false sharing (head/tail on separate cache lines)
- **Power-of-2 capacity** → `idx & (capacity - 1)` replaces expensive modulo

For **multi-producer multi-consumer** (MPMC), you need CAS loops on both head and tail — significantly more complex. Consider using a proven library like `moodycamel::ConcurrentQueue` for production MPMC use.'''
    ),
]
