"""
Batch p1334 — C++ Templates and Metaprogramming (deep2)
25 training pairs covering template basics, SFINAE, variadic templates,
compile-time computation, C++20 concepts, and advanced patterns.
"""

PAIRS = [
    # -------------------------------------------------------------------------
    # 1-5: Template basics and SFINAE
    # -------------------------------------------------------------------------
    (
        "cpp_deep2_01",
        r'''Write a C++ function template `max_of` that works for any type supporting `operator<`, but provide a specialization for `const char*` that compares by string content rather than pointer value.''',
        r'''<think>
The user wants a function template with a specialization for C-strings.
The generic version just uses operator<, which works for numeric and comparable types.
For const char* we need strcmp, otherwise we compare pointer addresses which is meaningless.
I should use a full specialization of the function template for const char*.
An alternative is overloading rather than specialization — in fact, function template specialization
has well-known pitfalls (it doesn't participate in overload resolution the same way).
I'll show both approaches: the specialization they asked for, plus a note about the overload alternative.
Need to include <cstring> for strcmp and <algorithm> or just rely on operator<.
Edge case: null pointers — I'll add a brief guard.
Should return const reference for the generic version to avoid copies, but for const char* we return the pointer.
</think>

Here is a function template with a `const char*` specialization:

```cpp
#include <cstring>
#include <iostream>

// Primary template — works for any type with operator<
template <typename T>
const T& max_of(const T& a, const T& b) {
    return (a < b) ? b : a;
}

// Full specialization for const char*
template <>
const char* const& max_of<const char*>(const char* const& a, const char* const& b) {
    return (std::strcmp(a, b) < 0) ? b : a;
}

int main() {
    std::cout << max_of(3, 7) << "\n";           // 7
    std::cout << max_of(2.5, 1.8) << "\n";       // 2.5

    const char* s1 = "apple";
    const char* s2 = "banana";
    std::cout << max_of(s1, s2) << "\n";          // banana (by strcmp)

    return 0;
}
```

**Note:** A common alternative is to use a plain overload instead of a specialization, because function template specializations do not participate in overload resolution independently — they attach to their primary template. An overload is often cleaner:

```cpp
const char* max_of(const char* a, const char* b) {
    return (std::strcmp(a, b) < 0) ? b : a;
}
```

This non-template overload will be preferred by the compiler when called with `const char*` arguments, which is typically the recommended approach in modern C++.'''
    ),
    (
        "cpp_deep2_02",
        r'''Explain and demonstrate class template partial specialization in C++ with a `Storage` class that behaves differently for pointer types vs. value types.''',
        r'''<think>
Class template partial specialization is one of the most powerful C++ template features.
The primary template handles value types normally. The partial specialization for T* (pointer types)
should manage ownership — perhaps storing a deep copy or at least clearly wrapping the pointer.
I'll make the primary template hold a value by copy, and the pointer specialization
hold an owned heap allocation (deep copy semantics) to show genuinely different behavior.
Need to handle copy/move correctly for the pointer specialization to avoid leaks.
I'll keep it focused but include destructor, copy constructor, and copy assignment
to demonstrate Rule of Three. This shows why partial specialization matters — you get
completely different class bodies for different type patterns.
Edge cases: self-assignment in operator=, null pointer construction.
I'll use C++17 style with inline variables where helpful.
</think>

Here is a `Storage` class with partial specialization for pointer types:

```cpp
#include <iostream>
#include <utility>
#include <cstring>

// Primary template: stores values directly
template <typename T>
class Storage {
    T value_;
public:
    explicit Storage(const T& v) : value_(v) {}
    const T& get() const { return value_; }
    void set(const T& v) { value_ = v; }
};

// Partial specialization for pointer types: owns a deep copy
template <typename T>
class Storage<T*> {
    T* ptr_;

    void copy_from(const T* other) {
        ptr_ = other ? new T(*other) : nullptr;
    }
public:
    explicit Storage(const T* p = nullptr) : ptr_(nullptr) {
        copy_from(p);
    }

    ~Storage() { delete ptr_; }

    // Copy constructor
    Storage(const Storage& other) : ptr_(nullptr) {
        copy_from(other.ptr_);
    }

    // Copy assignment
    Storage& operator=(const Storage& other) {
        if (this != &other) {
            delete ptr_;
            ptr_ = nullptr;
            copy_from(other.ptr_);
        }
        return *this;
    }

    // Move constructor
    Storage(Storage&& other) noexcept : ptr_(other.ptr_) {
        other.ptr_ = nullptr;
    }

    // Move assignment
    Storage& operator=(Storage&& other) noexcept {
        if (this != &other) {
            delete ptr_;
            ptr_ = other.ptr_;
            other.ptr_ = nullptr;
        }
        return *this;
    }

    const T* get() const { return ptr_; }
    void set(const T* p) {
        delete ptr_;
        ptr_ = nullptr;
        copy_from(p);
    }
};

int main() {
    // Value storage
    Storage<int> vs(42);
    std::cout << "Value: " << vs.get() << "\n";

    // Pointer storage — owns a deep copy
    int x = 99;
    Storage<int*> ps(&x);
    x = 0;  // modifying original doesn't affect storage
    std::cout << "Pointer storage (deep copy): " << *ps.get() << "\n"; // still 99

    // Copy semantics
    Storage<int*> ps2 = ps;
    std::cout << "Copied: " << *ps2.get() << "\n";
    std::cout << "Independent: " << (ps.get() != ps2.get()) << "\n"; // true

    return 0;
}
```

The primary template simply wraps a value. The partial specialization `Storage<T*>` allocates heap memory and performs deep copies, giving pointer types ownership semantics. This pattern is the foundation of smart pointers and handle classes.'''
    ),
    (
        "cpp_deep2_03",
        r'''Show how to use `std::enable_if` in C++ to create a function that only accepts integral types, and another overload that only accepts floating-point types. Explain the SFINAE mechanism.''',
        r'''<think>
SFINAE — Substitution Failure Is Not An Error — is the core mechanism that makes enable_if work.
When the compiler tries to substitute template arguments and the substitution fails (e.g.,
enable_if condition is false, so ::type doesn't exist), it silently removes that overload
from the candidate set instead of emitting a hard error.
I need two function overloads: one for integral, one for floating-point.
I'll show the classic enable_if-in-return-type style and the enable_if-as-extra-template-parameter style.
For the integral version: use std::is_integral_v<T>.
For the floating version: use std::is_floating_point_v<T>.
I should also briefly mention that C++20 concepts replace most enable_if usage.
Should include <type_traits> and <iostream>.
I'll demonstrate with a `describe` function that prints type-specific info.
</think>

Here is a demonstration of `std::enable_if` with SFINAE:

```cpp
#include <type_traits>
#include <iostream>
#include <string>

// Style 1: enable_if in the return type
template <typename T>
std::enable_if_t<std::is_integral_v<T>, std::string>
describe(T value) {
    return "Integer value: " + std::to_string(value)
         + " (is_signed=" + (std::is_signed_v<T> ? "true" : "false") + ")";
}

template <typename T>
std::enable_if_t<std::is_floating_point_v<T>, std::string>
describe(T value) {
    return "Floating-point value: " + std::to_string(value)
         + " (precision=" + std::to_string(sizeof(T) * 8) + " bits)";
}

// Style 2: enable_if as a default template parameter
template <typename T,
          std::enable_if_t<std::is_integral_v<T>, int> = 0>
void print_type_info(T v) {
    std::cout << "Integral, sizeof=" << sizeof(T)
              << ", value=" << v << "\n";
}

template <typename T,
          std::enable_if_t<std::is_floating_point_v<T>, int> = 0>
void print_type_info(T v) {
    std::cout << "Floating-point, sizeof=" << sizeof(T)
              << ", value=" << v << "\n";
}

int main() {
    std::cout << describe(42) << "\n";
    std::cout << describe(3.14) << "\n";
    std::cout << describe(-7L) << "\n";
    std::cout << describe(2.71828f) << "\n";

    print_type_info(100);
    print_type_info(1.618);

    // This would fail to compile — no matching overload:
    // describe("hello");

    return 0;
}
```

**How SFINAE works:**

1. The compiler sees `describe(42)` and tries both overloads.
2. For the integral overload: `std::is_integral_v<int>` is `true`, so `std::enable_if_t<true, std::string>` resolves to `std::string`. Substitution succeeds.
3. For the floating-point overload: `std::is_floating_point_v<int>` is `false`, so `std::enable_if_t<false, std::string>` has no `::type` member. Substitution *fails* — but instead of a compiler error, the overload is silently removed from the candidate set.
4. Only the integral overload remains, so it is selected.

In modern C++20 code, prefer `requires` clauses or concepts over `enable_if`, as they produce clearer error messages and are more readable.'''
    ),
    (
        "cpp_deep2_04",
        r'''Implement the detection idiom using `std::void_t` in C++ to check at compile time whether a type has a `size()` member function and a nested `value_type` typedef.''',
        r'''<think>
The detection idiom uses void_t to create SFINAE-friendly type traits.
void_t<Ts...> is just void when all Ts are well-formed, and causes substitution failure otherwise.
I need two detectors:
1. has_size — checks if T has a .size() method
2. has_value_type — checks if T::value_type exists
The pattern is: primary template (false case), partial specialization using void_t (true case).
I should show how this works with standard containers (which have both),
raw arrays (neither), and maybe a custom type (one but not the other).
Since C++17, void_t is in <type_traits>. For pre-C++17 I could define it manually.
I'll also show the is_detected pattern from Library Fundamentals TS v2 as a more general approach.
Should keep the examples practical and testable with static_assert.
</think>

Here is the detection idiom implemented with `std::void_t`:

```cpp
#include <type_traits>
#include <vector>
#include <string>
#include <iostream>

// Detector: has_size — checks for .size() member function
template <typename T, typename = void>
struct has_size : std::false_type {};

template <typename T>
struct has_size<T, std::void_t<decltype(std::declval<const T&>().size())>>
    : std::true_type {};

template <typename T>
inline constexpr bool has_size_v = has_size<T>::value;

// Detector: has_value_type — checks for nested value_type typedef
template <typename T, typename = void>
struct has_value_type : std::false_type {};

template <typename T>
struct has_value_type<T, std::void_t<typename T::value_type>>
    : std::true_type {};

template <typename T>
inline constexpr bool has_value_type_v = has_value_type<T>::value;

// Combined detector
template <typename T>
inline constexpr bool is_container_like_v = has_size_v<T> && has_value_type_v<T>;

// Generic detector utility (like std::experimental::is_detected)
template <typename, template <typename...> class Op, typename... Args>
struct is_detected_impl : std::false_type {};

template <template <typename...> class Op, typename... Args>
struct is_detected_impl<std::void_t<Op<Args...>>, Op, Args...>
    : std::true_type {};

template <template <typename...> class Op, typename... Args>
using is_detected = is_detected_impl<void, Op, Args...>;

// Usage with the generic detector
template <typename T>
using size_expr = decltype(std::declval<T>().size());

template <typename T>
using value_type_expr = typename T::value_type;

// Test types
struct Widget {
    int size() const { return 42; }
    // no value_type
};

int main() {
    // Specific detectors
    static_assert(has_size_v<std::vector<int>>);
    static_assert(has_size_v<std::string>);
    static_assert(has_size_v<Widget>);
    static_assert(!has_size_v<int>);

    static_assert(has_value_type_v<std::vector<int>>);
    static_assert(!has_value_type_v<Widget>);
    static_assert(!has_value_type_v<int>);

    static_assert(is_container_like_v<std::vector<int>>);
    static_assert(!is_container_like_v<Widget>);  // has size but no value_type

    // Generic detector
    static_assert(is_detected<size_expr, std::vector<int>>::value);
    static_assert(!is_detected<value_type_expr, int>::value);

    std::cout << "All static_asserts passed.\n";
    return 0;
}
```

**How `void_t` detection works:**

- The primary template defaults the second parameter to `void` and inherits `false_type`.
- The partial specialization also produces `void` (via `void_t`), but only when the expression inside `void_t` is well-formed.
- When substitution succeeds, the specialization is more specialized than the primary, so it wins — giving `true_type`.
- When substitution fails (SFINAE), the primary template's `false_type` is selected.'''
    ),
    (
        "cpp_deep2_05",
        r'''Write a C++ type trait `is_callable` that detects whether a type can be invoked with a given set of argument types. For example, `is_callable<F, int, double>` should be true if `F` can be called with `(int, double)`.''',
        r'''<think>
This is a practical detection idiom that checks if std::declval<F>()(std::declval<Args>()...) is valid.
I can use void_t or the detection idiom approach.
C++17 has std::is_invocable which does exactly this, but the exercise is to build it ourselves.
I'll use void_t with decltype of the call expression.
Need to handle: regular functions (via function pointers), lambdas, functors, member function pointers.
For member function pointers, std::invoke handles them but a plain call operator won't.
I'll focus on callable objects (operator()) and function pointers, noting that
std::is_invocable handles the full range including member pointers.
I should also provide is_callable_r to check the return type.
The tricky part is getting the SFINAE expression right with the parameter pack.
</think>

Here is a custom `is_callable` trait:

```cpp
#include <type_traits>
#include <iostream>
#include <string>

// Primary template: not callable
template <typename, typename = void>
struct is_callable_impl : std::false_type {};

// Specialization: callable if the expression F(Args...) is well-formed
template <typename F, typename... Args>
struct is_callable_impl<
    F(Args...),
    std::void_t<decltype(std::declval<F>()(std::declval<Args>()...))>
> : std::true_type {};

// User-facing alias: is_callable<F, Args...>
// Encodes as is_callable_impl<F(Args...)>
template <typename F, typename... Args>
struct is_callable : is_callable_impl<F(Args...)> {};

template <typename F, typename... Args>
inline constexpr bool is_callable_v = is_callable<F, Args...>::value;

// Extended: check return type too
template <typename, typename, typename = void>
struct is_callable_r_impl : std::false_type {};

template <typename R, typename F, typename... Args>
struct is_callable_r_impl<
    R, F(Args...),
    std::void_t<decltype(std::declval<F>()(std::declval<Args>()...))>
> : std::is_convertible<
        decltype(std::declval<F>()(std::declval<Args>()...)), R
    > {};

template <typename R, typename F, typename... Args>
struct is_callable_r : is_callable_r_impl<R, F(Args...)> {};

template <typename R, typename F, typename... Args>
inline constexpr bool is_callable_r_v = is_callable_r<R, F, Args...>::value;

// Test types
struct Adder {
    int operator()(int a, int b) const { return a + b; }
};

struct Greeter {
    std::string operator()(const std::string& name) const {
        return "Hello, " + name;
    }
};

int main() {
    // Lambda
    auto square = [](double x) { return x * x; };
    static_assert(is_callable_v<decltype(square), double>);
    static_assert(is_callable_v<decltype(square), int>);    // int converts to double
    static_assert(!is_callable_v<decltype(square), int, int>); // wrong arity

    // Functor
    static_assert(is_callable_v<Adder, int, int>);
    static_assert(!is_callable_v<Adder, int>);             // wrong arity
    static_assert(!is_callable_v<Adder, std::string, int>); // no matching conversion

    // Function pointer
    using FnPtr = int(*)(int, int);
    static_assert(is_callable_v<FnPtr, int, int>);
    static_assert(!is_callable_v<FnPtr, int>);

    // Return type checking
    static_assert(is_callable_r_v<int, Adder, int, int>);
    static_assert(is_callable_r_v<double, Adder, int, int>); // int converts to double
    static_assert(!is_callable_r_v<std::string, Adder, int, int>);

    static_assert(is_callable_r_v<std::string, Greeter, const std::string&>);

    // Non-callable type
    static_assert(!is_callable_v<int, int>);
    static_assert(!is_callable_v<std::string>);

    std::cout << "All static_asserts passed.\n";
    return 0;
}
```

The trick is encoding the callable signature as `F(Args...)` in a single template parameter. The `void_t` specialization attempts `std::declval<F>()(std::declval<Args>()...)` — if the call expression is ill-formed, SFINAE kicks in and the primary `false_type` template is selected.'''
    ),

    # -------------------------------------------------------------------------
    # 6-10: Variadic templates
    # -------------------------------------------------------------------------
    (
        "cpp_deep2_06",
        r'''Write a C++ variadic template function `print_all` that prints any number of arguments separated by commas, using both recursive expansion and C++17 fold expressions. Show both approaches.''',
        r'''<think>
Two approaches to handle parameter packs:
1. Recursive: base case + recursive case, classic pre-C++17 technique
2. Fold expression: (expr op ... op pack) or (pack op ... op expr), C++17
For the recursive version I need a base case (single argument or zero arguments).
For the fold version, the comma-separated output is trickier — I can't just fold over operator<<
because I also need the comma delimiter.
One trick: use a lambda or helper that prints comma-then-value, with special handling for the first.
Or I can use the comma operator fold: ((std::cout << ", " << args), ...) but need to skip
the first comma. An alternative is to print the first arg separately and fold the rest.
Actually, cleanest fold approach: use an index or print first, then fold remaining.
I'll show an initializer_list trick too for the fold version.
Let me keep it clear and show both patterns distinctly.
</think>

Here are both approaches:

```cpp
#include <iostream>
#include <sstream>
#include <string>

// ============================================================
// Approach 1: Recursive template expansion (C++11/14)
// ============================================================

// Base case: single argument
template <typename T>
void print_recursive(const T& arg) {
    std::cout << arg;
}

// Recursive case: first argument + rest
template <typename T, typename... Rest>
void print_recursive(const T& first, const Rest&... rest) {
    std::cout << first << ", ";
    print_recursive(rest...);
}

// ============================================================
// Approach 2: C++17 fold expression
// ============================================================

template <typename... Args>
void print_fold(const Args&... args) {
    bool first = true;
    // Fold over the comma operator
    ((std::cout << (first ? "" : ", ") << args, first = false), ...);
    std::cout << "\n";
}

// ============================================================
// Bonus: fold into a string
// ============================================================

template <typename... Args>
std::string to_csv(const Args&... args) {
    std::ostringstream oss;
    bool first = true;
    ((oss << (first ? "" : ", ") << args, first = false), ...);
    return oss.str();
}

// ============================================================
// Bonus: fold to compute sum
// ============================================================

template <typename... Args>
auto sum(const Args&... args) {
    return (args + ...);  // Unary right fold
}

template <typename... Args>
auto sum_with_init(const Args&... args) {
    return (0 + ... + args);  // Binary left fold with init=0
}

int main() {
    std::cout << "Recursive: ";
    print_recursive(1, "hello", 3.14, 'X');
    std::cout << "\n";

    std::cout << "Fold:      ";
    print_fold(1, "hello", 3.14, 'X');

    std::cout << "CSV: " << to_csv("Alice", 30, "NYC", 3.5) << "\n";

    std::cout << "Sum: " << sum(1, 2, 3, 4, 5) << "\n";        // 15
    std::cout << "Sum: " << sum_with_init(1.5, 2.5, 3.0) << "\n"; // 7.0

    return 0;
}
```

**Key differences:**

| Aspect | Recursive | Fold |
|--------|-----------|------|
| Standard | C++11+ | C++17+ |
| Base case | Explicit overload needed | Handled by fold semantics |
| Compile time | O(N) instantiations | Single expansion |
| Readability | Familiar | More concise |

The fold expression `((expr, first = false), ...)` uses the comma *operator* — each sub-expression is evaluated left-to-right, and the fold expands over the outer comma operator.'''
    ),
    (
        "cpp_deep2_07",
        r'''Implement a simplified `Tuple` class in C++ using variadic templates and recursive inheritance. Support `get<I>(tuple)` to access elements by index.''',
        r'''<think>
This is a classic exercise. The standard approach:
1. Base case: empty tuple (TupleImpl<N> with no types)
2. Recursive case: TupleImpl<N, Head, Tail...> inherits from TupleImpl<N+1, Tail...> and stores Head
3. get<I> uses the index to select the right base class

I need:
- TupleImpl with an index parameter to disambiguate bases with the same type
- TupleLeaf or direct storage in each level
- A get<I> function template that casts to the right base

Alternative: use composition instead of inheritance, but inheritance is the classic
approach and what std::tuple implementations typically use.

I'll keep it simple but functional: construction, get, and tuple_size.
Need to be careful with the indexing — element 0 is stored in the most-derived class.
I'll also add a make_tuple helper and a tuple_size trait.
Edge cases: empty tuple, single-element tuple.
</think>

Here is a simplified `Tuple` implementation:

```cpp
#include <iostream>
#include <type_traits>
#include <cstddef>
#include <utility>

// Base case: empty tuple
template <std::size_t I, typename... Ts>
struct TupleImpl {};

// Recursive case: stores Head at index I, inherits rest
template <std::size_t I, typename Head, typename... Tail>
struct TupleImpl<I, Head, Tail...> : TupleImpl<I + 1, Tail...> {
    Head value;

    TupleImpl() = default;

    template <typename H, typename... T>
    explicit TupleImpl(H&& h, T&&... t)
        : TupleImpl<I + 1, Tail...>(std::forward<T>(t)...)
        , value(std::forward<H>(h)) {}
};

// The user-facing Tuple type
template <typename... Ts>
struct Tuple : TupleImpl<0, Ts...> {
    Tuple() = default;

    template <typename... Args>
    explicit Tuple(Args&&... args)
        : TupleImpl<0, Ts...>(std::forward<Args>(args)...) {}
};

// tuple_size trait
template <typename T>
struct tuple_size;

template <typename... Ts>
struct tuple_size<Tuple<Ts...>>
    : std::integral_constant<std::size_t, sizeof...(Ts)> {};

template <typename T>
inline constexpr std::size_t tuple_size_v = tuple_size<T>::value;

// tuple_element trait (get the type at index I)
template <std::size_t I, typename T>
struct tuple_element;

template <std::size_t I, typename Head, typename... Tail>
struct tuple_element<I, Tuple<Head, Tail...>>
    : tuple_element<I - 1, Tuple<Tail...>> {};

template <typename Head, typename... Tail>
struct tuple_element<0, Tuple<Head, Tail...>> {
    using type = Head;
};

template <std::size_t I, typename T>
using tuple_element_t = typename tuple_element<I, T>::type;

// get<I> implementation — cast to the right base class
template <std::size_t I, typename... Ts>
auto& get(Tuple<Ts...>& t) {
    // Cast to the TupleImpl level that stores index I
    TupleImpl<I, tuple_element_t<I, Tuple<Ts...>>,
              /* remaining types would follow but we just need the base */
              void /* placeholder trick — see below */
    >& base = static_cast<TupleImpl<I, tuple_element_t<I, Tuple<Ts...>>>&>(
        // We actually need a different approach — cast through the recursive chain
        t
    );
    return base.value;
}

// Cleaner approach: helper that extracts from TupleImpl directly
template <std::size_t I, typename Head, typename... Tail>
Head& get_impl(TupleImpl<I, Head, Tail...>& t) {
    return t.value;
}

template <std::size_t I, typename Head, typename... Tail>
const Head& get_impl(const TupleImpl<I, Head, Tail...>& t) {
    return t.value;
}

// Clean get that uses implicit base-class conversion
template <std::size_t I, typename... Ts>
auto& get(Tuple<Ts...>& t) requires (I < sizeof...(Ts)) {
    return get_impl<I>(t);
}

template <std::size_t I, typename... Ts>
const auto& get(const Tuple<Ts...>& t) requires (I < sizeof...(Ts)) {
    return get_impl<I>(t);
}

// make_tuple helper
template <typename... Ts>
Tuple<std::decay_t<Ts>...> make_tuple(Ts&&... args) {
    return Tuple<std::decay_t<Ts>...>(std::forward<Ts>(args)...);
}

int main() {
    auto t = make_tuple(42, 3.14, std::string("hello"));

    std::cout << "Element 0: " << get<0>(t) << "\n";  // 42
    std::cout << "Element 1: " << get<1>(t) << "\n";  // 3.14
    std::cout << "Element 2: " << get<2>(t) << "\n";  // hello
    std::cout << "Size: " << tuple_size_v<decltype(t)> << "\n"; // 3

    // Modify through get
    get<0>(t) = 100;
    std::cout << "Modified 0: " << get<0>(t) << "\n"; // 100

    // Compile-time type access
    static_assert(std::is_same_v<tuple_element_t<0, decltype(t)>, int>);
    static_assert(std::is_same_v<tuple_element_t<1, decltype(t)>, double>);

    return 0;
}
```

The key insight is that `Tuple<int, double, string>` inherits from a chain: `TupleImpl<0, int, double, string>` -> `TupleImpl<1, double, string>` -> `TupleImpl<2, string>` -> `TupleImpl<3>`. Each level stores one element. The `get_impl<I>` function uses implicit derived-to-base conversion to reach the correct level, since only one base class has index `I`.'''
    ),
    (
        "cpp_deep2_08",
        r'''Write a type-safe printf in C++ using variadic templates that validates format specifiers against argument types at compile time.''',
        r'''<think>
A type-safe printf needs to:
1. Parse the format string for % specifiers
2. Match each specifier to the corresponding argument type
3. Ideally catch mismatches at compile time

For compile-time format checking, I'd need constexpr string parsing (C++20 with consteval).
For a practical C++17 version, I can do runtime type checking with better safety than printf.
Let me do a hybrid: a runtime version that's type-safe (no UB, throws on mismatch),
plus a C++20 consteval version sketch.

The runtime approach: process the format string character by character. When we hit %,
look at the next character for the specifier, then call the appropriate output method.
Use variadic templates to consume arguments one at a time.

I'll make it throw on type mismatch and on wrong argument count.
Specifiers: %d (integral), %f (floating), %s (string-like), %c (char), %% (literal %).
</think>

Here is a type-safe printf using variadic templates:

```cpp
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>
#include <stdexcept>
#include <type_traits>

namespace safe {

// Helper: format a single argument based on specifier
template <typename T>
void format_arg(std::ostream& os, char spec, const T& arg) {
    switch (spec) {
        case 'd':
            if constexpr (std::is_integral_v<T>) {
                os << arg;
            } else {
                throw std::invalid_argument(
                    "%d requires an integral type");
            }
            break;
        case 'f':
            if constexpr (std::is_floating_point_v<T>) {
                os << arg;
            } else if constexpr (std::is_integral_v<T>) {
                os << static_cast<double>(arg);  // allow implicit widening
            } else {
                throw std::invalid_argument(
                    "%f requires a numeric type");
            }
            break;
        case 's':
            if constexpr (std::is_convertible_v<T, std::string_view>) {
                os << arg;
            } else {
                throw std::invalid_argument(
                    "%s requires a string-like type");
            }
            break;
        case 'c':
            if constexpr (std::is_same_v<std::decay_t<T>, char>) {
                os << arg;
            } else {
                throw std::invalid_argument(
                    "%c requires char type");
            }
            break;
        default:
            throw std::invalid_argument(
                std::string("Unknown format specifier: %") + spec);
    }
}

// Base case: no more arguments — scan for unmatched specifiers
inline void printf_impl(std::ostream& os, std::string_view fmt) {
    for (std::size_t i = 0; i < fmt.size(); ++i) {
        if (fmt[i] == '%') {
            if (i + 1 < fmt.size() && fmt[i + 1] == '%') {
                os << '%';
                ++i;
            } else {
                throw std::invalid_argument(
                    "Not enough arguments for format string");
            }
        } else {
            os << fmt[i];
        }
    }
}

// Recursive case: consume one argument per format specifier
template <typename T, typename... Rest>
void printf_impl(std::ostream& os, std::string_view fmt,
                 const T& arg, const Rest&... rest) {
    for (std::size_t i = 0; i < fmt.size(); ++i) {
        if (fmt[i] == '%') {
            if (i + 1 >= fmt.size()) {
                throw std::invalid_argument("Truncated format specifier");
            }
            if (fmt[i + 1] == '%') {
                os << '%';
                ++i;
                continue;
            }
            char spec = fmt[i + 1];
            format_arg(os, spec, arg);
            // Recurse with remaining format and remaining args
            printf_impl(os, fmt.substr(i + 2), rest...);
            return;
        }
        os << fmt[i];
    }
    // If we get here, there are leftover arguments
    throw std::invalid_argument("Too many arguments for format string");
}

// User-facing function
template <typename... Args>
void printf(std::string_view fmt, const Args&... args) {
    printf_impl(std::cout, fmt, args...);
}

template <typename... Args>
std::string sprintf(std::string_view fmt, const Args&... args) {
    std::ostringstream oss;
    printf_impl(oss, fmt, args...);
    return oss.str();
}

} // namespace safe

int main() {
    safe::printf("Hello %s, you are %d years old.\n",
                 "Alice", 30);

    safe::printf("Pi is approximately %f\n", 3.14159);

    safe::printf("Initial: %c\n", 'A');

    safe::printf("100%% complete\n");  // escaped %%

    auto result = safe::sprintf("%s scored %d/%d (%f%%)",
                                "Bob", 95, 100, 95.0);
    std::cout << result << "\n";

    // These would throw at runtime:
    // safe::printf("%d", "not an int");   // type mismatch
    // safe::printf("%d %d", 42);          // too few args
    // safe::printf("%d", 1, 2);           // too many args

    return 0;
}
```

This is safer than C `printf` because:
- **No undefined behavior** — type mismatches throw exceptions instead of reading garbage memory
- **Argument count validation** — detects too many or too few arguments
- **`if constexpr` branches** — the wrong-type code paths are discarded at compile time, so there is no implicit reinterpretation of bits
- Literal `%%` is handled correctly'''
    ),
    (
        "cpp_deep2_09",
        r'''Write a C++ function `apply_to_each` that takes a callable and a parameter pack, applies the callable to each argument, and returns the results as a `std::tuple`. Use C++17 features.''',
        r'''<think>
This is a transformation over a parameter pack, collecting results into a tuple.
With C++17 I can use std::make_tuple with a pack expansion.
The expression is: std::make_tuple(f(args)...)
This expands to std::make_tuple(f(arg1), f(arg2), ..., f(argN)).
But I also need to handle the case where f returns void — that can't go into a tuple.
I'll focus on the non-void case and mention the void case.
I should also show a version that preserves evaluation order (left to right)
since C++17 guarantees left-to-right evaluation of function arguments in braced-init-lists.
Let me also add a transform_tuple that applies f to each element of an existing tuple.
I'll use std::index_sequence for that.
</think>

Here is `apply_to_each` with several useful variants:

```cpp
#include <tuple>
#include <string>
#include <iostream>
#include <utility>
#include <type_traits>

// Apply f to each argument, return results as a tuple
template <typename F, typename... Args>
auto apply_to_each(F&& f, Args&&... args) {
    return std::make_tuple(f(std::forward<Args>(args))...);
}

// Version that guarantees left-to-right evaluation order
// (uses braced-init-list which has sequenced evaluation in C++17)
template <typename F, typename... Args>
auto apply_to_each_ordered(F&& f, Args&&... args) {
    return std::tuple{f(std::forward<Args>(args))...};
}

// Apply f to each element of an existing tuple, return new tuple
template <typename F, typename Tuple, std::size_t... Is>
auto transform_tuple_impl(F&& f, Tuple&& t, std::index_sequence<Is...>) {
    return std::make_tuple(
        f(std::get<Is>(std::forward<Tuple>(t)))...
    );
}

template <typename F, typename Tuple>
auto transform_tuple(F&& f, Tuple&& t) {
    constexpr auto size = std::tuple_size_v<std::decay_t<Tuple>>;
    return transform_tuple_impl(
        std::forward<F>(f),
        std::forward<Tuple>(t),
        std::make_index_sequence<size>{}
    );
}

// for_each on a parameter pack (void return, side effects only)
template <typename F, typename... Args>
void for_each_arg(F&& f, Args&&... args) {
    (f(std::forward<Args>(args)), ...);  // fold over comma operator
}

// Zip-apply: apply binary function to pairs from two tuples
template <typename F, typename T1, typename T2, std::size_t... Is>
auto zip_apply_impl(F&& f, T1&& t1, T2&& t2, std::index_sequence<Is...>) {
    return std::make_tuple(
        f(std::get<Is>(std::forward<T1>(t1)),
          std::get<Is>(std::forward<T2>(t2)))...
    );
}

template <typename F, typename T1, typename T2>
auto zip_apply(F&& f, T1&& t1, T2&& t2) {
    constexpr auto size = std::tuple_size_v<std::decay_t<T1>>;
    static_assert(size == std::tuple_size_v<std::decay_t<T2>>,
                  "Tuples must have the same size");
    return zip_apply_impl(std::forward<F>(f),
                          std::forward<T1>(t1),
                          std::forward<T2>(t2),
                          std::make_index_sequence<size>{});
}

int main() {
    // apply_to_each: double each value
    auto doubled = apply_to_each([](auto x) { return x * 2; },
                                  1, 2.5, 3L);
    std::cout << std::get<0>(doubled) << ", "
              << std::get<1>(doubled) << ", "
              << std::get<2>(doubled) << "\n";
    // Output: 2, 5, 6

    // apply_to_each with type-changing transformation
    auto as_strings = apply_to_each(
        [](const auto& x) { return std::to_string(x); },
        42, 3.14, 100L);
    std::cout << std::get<0>(as_strings) << " | "
              << std::get<1>(as_strings) << " | "
              << std::get<2>(as_strings) << "\n";

    // transform_tuple: square each element of an existing tuple
    auto original = std::make_tuple(3, 4.0, 5L);
    auto squared = transform_tuple([](auto x) { return x * x; }, original);
    std::cout << std::get<0>(squared) << ", "
              << std::get<1>(squared) << ", "
              << std::get<2>(squared) << "\n";
    // Output: 9, 16, 25

    // for_each_arg: print with side effects
    std::cout << "Items: ";
    for_each_arg([](const auto& x) { std::cout << x << " "; },
                 "hello", 42, 3.14);
    std::cout << "\n";

    // zip_apply: pairwise addition
    auto sums = zip_apply([](auto a, auto b) { return a + b; },
                          std::make_tuple(1, 2, 3),
                          std::make_tuple(10, 20, 30));
    std::cout << std::get<0>(sums) << ", "
              << std::get<1>(sums) << ", "
              << std::get<2>(sums) << "\n";
    // Output: 11, 22, 33

    return 0;
}
```

The key insight is that `f(args)...` is a pack expansion — the compiler generates `f(arg1), f(arg2), ..., f(argN)` and wraps them in `std::make_tuple(...)`. This single expression replaces what would require explicit recursion in C++11/14.'''
    ),
    (
        "cpp_deep2_10",
        r'''Implement a C++ function `concat_tuples` that takes any number of tuples and concatenates them into a single tuple. Use `std::index_sequence` for element extraction.''',
        r'''<think>
I need to merge N tuples into one. The approach:
1. For two tuples: extract elements from both using index_sequence, pack into a new tuple.
2. For N tuples: recursively apply the two-tuple concat (fold-style).
Actually, std::tuple_cat already does this, but implementing it manually is the exercise.

The two-tuple case uses two index_sequences, one per tuple.
For the N-tuple fold, I can use a fold expression over a binary concat.
Or I can directly flatten all tuples: compute the total size, map each global index
to (which tuple, which element within that tuple). That's harder.

Simpler approach: binary concat + fold.
Binary concat: take two tuples, expand both with index_sequence, merge.
Then concat_tuples(t1, t2, t3, ...) = concat(concat(t1, t2), t3, ...)

Let me also handle the edge cases: zero tuples (return empty tuple),
one tuple (return as-is).
</think>

Here is a manual `concat_tuples` implementation:

```cpp
#include <tuple>
#include <string>
#include <iostream>
#include <utility>
#include <type_traits>

// Binary concat: merge two tuples into one
template <typename T1, typename T2, std::size_t... I1, std::size_t... I2>
auto concat_two_impl(T1&& t1, T2&& t2,
                     std::index_sequence<I1...>,
                     std::index_sequence<I2...>) {
    return std::make_tuple(
        std::get<I1>(std::forward<T1>(t1))...,
        std::get<I2>(std::forward<T2>(t2))...
    );
}

template <typename T1, typename T2>
auto concat_two(T1&& t1, T2&& t2) {
    return concat_two_impl(
        std::forward<T1>(t1),
        std::forward<T2>(t2),
        std::make_index_sequence<
            std::tuple_size_v<std::decay_t<T1>>>{},
        std::make_index_sequence<
            std::tuple_size_v<std::decay_t<T2>>>{}
    );
}

// Base case: no tuples -> empty tuple
auto concat_tuples() {
    return std::tuple<>{};
}

// Base case: single tuple -> return as-is
template <typename T>
auto concat_tuples(T&& t) {
    return std::forward<T>(t);
}

// Recursive case: concat first two, then recurse
template <typename T1, typename T2, typename... Rest>
auto concat_tuples(T1&& t1, T2&& t2, Rest&&... rest) {
    return concat_tuples(
        concat_two(std::forward<T1>(t1), std::forward<T2>(t2)),
        std::forward<Rest>(rest)...
    );
}

// Bonus: flatten nested tuples (one level deep)
template <typename Tuple, std::size_t... Is>
auto flatten_impl(Tuple&& t, std::index_sequence<Is...>) {
    return concat_tuples(std::get<Is>(std::forward<Tuple>(t))...);
}

template <typename Tuple>
auto flatten(Tuple&& t) {
    return flatten_impl(
        std::forward<Tuple>(t),
        std::make_index_sequence<
            std::tuple_size_v<std::decay_t<Tuple>>>{}
    );
}

// Helper to print any tuple
template <typename Tuple, std::size_t... Is>
void print_tuple_impl(const Tuple& t, std::index_sequence<Is...>) {
    std::cout << "(";
    ((std::cout << (Is == 0 ? "" : ", ") << std::get<Is>(t)), ...);
    std::cout << ")";
}

template <typename... Ts>
void print_tuple(const std::tuple<Ts...>& t) {
    print_tuple_impl(t, std::make_index_sequence<sizeof...(Ts)>{});
}

int main() {
    auto t1 = std::make_tuple(1, 2.0);
    auto t2 = std::make_tuple(std::string("hello"), 'X');
    auto t3 = std::make_tuple(42L, 3.14f, true);

    // Concat two
    auto merged2 = concat_tuples(t1, t2);
    std::cout << "Two: ";
    print_tuple(merged2);
    std::cout << "\n";
    // (1, 2, hello, X)

    // Concat three
    auto merged3 = concat_tuples(t1, t2, t3);
    std::cout << "Three: ";
    print_tuple(merged3);
    std::cout << "\n";
    // (1, 2, hello, X, 42, 3.14, true)

    // Empty concat
    auto empty = concat_tuples();
    static_assert(std::tuple_size_v<decltype(empty)> == 0);

    // Flatten a tuple of tuples
    auto nested = std::make_tuple(t1, t2, t3);
    auto flat = flatten(nested);
    std::cout << "Flat: ";
    print_tuple(flat);
    std::cout << "\n";
    // Same as merged3

    // Type verification
    static_assert(std::tuple_size_v<decltype(merged3)> == 7);
    static_assert(std::is_same_v<
        std::tuple_element_t<2, decltype(merged3)>, std::string>);

    return 0;
}
```

The implementation chains binary `concat_two` calls recursively. Each binary concat uses two `std::index_sequence` expansions to extract elements from both input tuples and pack them into `std::make_tuple(...)`. The recursion terminates at the single-tuple or zero-tuple base case.'''
    ),

    # -------------------------------------------------------------------------
    # 11-15: Compile-time computation
    # -------------------------------------------------------------------------
    (
        "cpp_deep2_11",
        r'''Write constexpr functions in C++ for factorial and fibonacci that work both at compile time and runtime. Compare with the old-style template metaprogramming approach.''',
        r'''<think>
I should show three approaches:
1. Classic TMP (template struct with value, recursive specialization) — C++98/11 style
2. constexpr function (C++14 style with loops)
3. C++20 consteval (forced compile-time only)

For factorial: straightforward recursion or loop.
For fibonacci: the naive recursive version is exponential, so for TMP it's fine
(compiler memoizes template instantiations), but for constexpr I should use iteration.

I'll demonstrate compile-time usage with static_assert and runtime usage too.
Should mention the key advantage of constexpr functions: they're readable normal code
that works in both contexts, unlike TMP which is hard to read and debug.
I'll also show a constexpr array generation to demonstrate practical use.
</think>

Here are three generations of compile-time computation:

```cpp
#include <iostream>
#include <array>
#include <cstdint>
#include <type_traits>

// ================================================================
// Approach 1: Classic Template Metaprogramming (C++98/11)
// ================================================================

template <uint64_t N>
struct Factorial {
    static constexpr uint64_t value = N * Factorial<N - 1>::value;
};

template <>
struct Factorial<0> {
    static constexpr uint64_t value = 1;
};

template <uint64_t N>
struct Fibonacci {
    // Compiler memoizes instantiations, so this is O(N), not O(2^N)
    static constexpr uint64_t value =
        Fibonacci<N - 1>::value + Fibonacci<N - 2>::value;
};

template <>
struct Fibonacci<0> {
    static constexpr uint64_t value = 0;
};

template <>
struct Fibonacci<1> {
    static constexpr uint64_t value = 1;
};

// ================================================================
// Approach 2: constexpr functions (C++14/17)
// ================================================================

constexpr uint64_t factorial(uint64_t n) {
    uint64_t result = 1;
    for (uint64_t i = 2; i <= n; ++i) {
        result *= i;
    }
    return result;
}

constexpr uint64_t fibonacci(uint64_t n) {
    if (n <= 1) return n;
    uint64_t a = 0, b = 1;
    for (uint64_t i = 2; i <= n; ++i) {
        uint64_t tmp = a + b;
        a = b;
        b = tmp;
    }
    return b;
}

// ================================================================
// Approach 3: C++20 consteval (compile-time only)
// ================================================================

consteval uint64_t factorial_ct(uint64_t n) {
    uint64_t result = 1;
    for (uint64_t i = 2; i <= n; ++i)
        result *= i;
    return result;
}

consteval uint64_t fibonacci_ct(uint64_t n) {
    if (n <= 1) return n;
    uint64_t a = 0, b = 1;
    for (uint64_t i = 2; i <= n; ++i) {
        auto tmp = a + b;
        a = b;
        b = tmp;
    }
    return b;
}

// ================================================================
// Practical use: compile-time lookup table generation
// ================================================================

template <std::size_t N>
constexpr auto make_fib_table() {
    std::array<uint64_t, N> table{};
    for (std::size_t i = 0; i < N; ++i) {
        table[i] = fibonacci(i);
    }
    return table;
}

inline constexpr auto fib_table = make_fib_table<20>();

int main() {
    // TMP approach — values baked into types
    static_assert(Factorial<5>::value == 120);
    static_assert(Factorial<10>::value == 3628800);
    static_assert(Fibonacci<10>::value == 55);

    // constexpr — works at compile time
    static_assert(factorial(5) == 120);
    static_assert(fibonacci(10) == 55);

    // constexpr — also works at runtime
    uint64_t n;
    std::cout << "Enter n: ";
    std::cin >> n;
    std::cout << n << "! = " << factorial(n) << "\n";
    std::cout << "fib(" << n << ") = " << fibonacci(n) << "\n";

    // consteval — compile-time only (would fail if called with runtime value)
    constexpr auto f20 = factorial_ct(20);
    std::cout << "20! = " << f20 << "\n";

    // Compile-time lookup table
    std::cout << "Fibonacci table: ";
    for (auto v : fib_table) std::cout << v << " ";
    std::cout << "\n";

    return 0;
}
```

| Feature | TMP Structs | `constexpr` | `consteval` |
|---------|-------------|-------------|-------------|
| Compile-time | Yes | Yes | Yes (only) |
| Runtime | No | Yes | No |
| Readability | Poor | Excellent | Excellent |
| Debugging | Hard | Normal | Normal |
| Minimum standard | C++98 | C++14 | C++20 |

Modern C++ strongly favors `constexpr` functions over TMP structs for computation. Reserve TMP for type-level programming (type lists, type transformations) where you actually need to manipulate types, not values.'''
    ),
    (
        "cpp_deep2_12",
        r'''Implement a compile-time type list in C++ with operations: `push_front`, `push_back`, `pop_front`, `at`, `size`, `contains`, and `remove`. No Boost allowed.''',
        r'''<think>
A type list is a fundamental TMP building block. The classic approach uses a variadic
template struct TypeList<Ts...> and then defines operations as template aliases or structs.

Operations I need:
- push_front<List, T>: prepend a type
- push_back<List, T>: append a type
- pop_front<List>: remove first type
- at<List, I>: get type at index I
- size<List>: number of types
- contains<List, T>: check if T is in the list
- remove<List, T>: remove all occurrences of T

All of these are type-level operations, returning types or compile-time values.
I'll use partial specialization to destructure the TypeList and extract/manipulate types.
For contains and remove, I need to iterate over the pack.
For remove, I can use a conditional push_back in a fold.
I should use static_assert for testing since there are no runtime values.
</think>

Here is a complete compile-time type list library:

```cpp
#include <type_traits>
#include <cstddef>

// ==========================================================
// Core type list
// ==========================================================
template <typename... Ts>
struct TypeList {};

// ==========================================================
// size
// ==========================================================
template <typename List>
struct size;

template <typename... Ts>
struct size<TypeList<Ts...>>
    : std::integral_constant<std::size_t, sizeof...(Ts)> {};

template <typename List>
inline constexpr std::size_t size_v = size<List>::value;

// ==========================================================
// push_front
// ==========================================================
template <typename List, typename T>
struct push_front;

template <typename... Ts, typename T>
struct push_front<TypeList<Ts...>, T> {
    using type = TypeList<T, Ts...>;
};

template <typename List, typename T>
using push_front_t = typename push_front<List, T>::type;

// ==========================================================
// push_back
// ==========================================================
template <typename List, typename T>
struct push_back;

template <typename... Ts, typename T>
struct push_back<TypeList<Ts...>, T> {
    using type = TypeList<Ts..., T>;
};

template <typename List, typename T>
using push_back_t = typename push_back<List, T>::type;

// ==========================================================
// pop_front
// ==========================================================
template <typename List>
struct pop_front;

template <typename Head, typename... Tail>
struct pop_front<TypeList<Head, Tail...>> {
    using type = TypeList<Tail...>;
};

template <typename List>
using pop_front_t = typename pop_front<List>::type;

// ==========================================================
// front
// ==========================================================
template <typename List>
struct front;

template <typename Head, typename... Tail>
struct front<TypeList<Head, Tail...>> {
    using type = Head;
};

template <typename List>
using front_t = typename front<List>::type;

// ==========================================================
// at (index-based access)
// ==========================================================
template <typename List, std::size_t I>
struct at;

template <typename Head, typename... Tail>
struct at<TypeList<Head, Tail...>, 0> {
    using type = Head;
};

template <typename Head, typename... Tail, std::size_t I>
struct at<TypeList<Head, Tail...>, I> {
    using type = typename at<TypeList<Tail...>, I - 1>::type;
};

template <typename List, std::size_t I>
using at_t = typename at<List, I>::type;

// ==========================================================
// contains
// ==========================================================
template <typename List, typename T>
struct contains;

template <typename T>
struct contains<TypeList<>, T> : std::false_type {};

template <typename T, typename... Tail>
struct contains<TypeList<T, Tail...>, T> : std::true_type {};

template <typename Head, typename... Tail, typename T>
struct contains<TypeList<Head, Tail...>, T>
    : contains<TypeList<Tail...>, T> {};

template <typename List, typename T>
inline constexpr bool contains_v = contains<List, T>::value;

// ==========================================================
// remove (all occurrences)
// ==========================================================
template <typename List, typename T>
struct remove;

template <typename T>
struct remove<TypeList<>, T> {
    using type = TypeList<>;
};

template <typename T, typename... Tail>
struct remove<TypeList<T, Tail...>, T> {
    // Skip T, continue with tail
    using type = typename remove<TypeList<Tail...>, T>::type;
};

template <typename Head, typename... Tail, typename T>
struct remove<TypeList<Head, Tail...>, T> {
    // Keep Head, continue with tail
    using type = push_front_t<
        typename remove<TypeList<Tail...>, T>::type,
        Head
    >;
};

template <typename List, typename T>
using remove_t = typename remove<List, T>::type;

// ==========================================================
// concat (merge two type lists)
// ==========================================================
template <typename L1, typename L2>
struct concat;

template <typename... T1s, typename... T2s>
struct concat<TypeList<T1s...>, TypeList<T2s...>> {
    using type = TypeList<T1s..., T2s...>;
};

template <typename L1, typename L2>
using concat_t = typename concat<L1, L2>::type;

// ==========================================================
// Tests (all compile-time)
// ==========================================================

using Empty = TypeList<>;
using List1 = TypeList<int, double, char>;

// size
static_assert(size_v<Empty> == 0);
static_assert(size_v<List1> == 3);

// push_front / push_back
static_assert(std::is_same_v<
    push_front_t<List1, float>,
    TypeList<float, int, double, char>>);

static_assert(std::is_same_v<
    push_back_t<List1, float>,
    TypeList<int, double, char, float>>);

// pop_front / front
static_assert(std::is_same_v<front_t<List1>, int>);
static_assert(std::is_same_v<
    pop_front_t<List1>,
    TypeList<double, char>>);

// at
static_assert(std::is_same_v<at_t<List1, 0>, int>);
static_assert(std::is_same_v<at_t<List1, 1>, double>);
static_assert(std::is_same_v<at_t<List1, 2>, char>);

// contains
static_assert(contains_v<List1, int>);
static_assert(contains_v<List1, double>);
static_assert(!contains_v<List1, float>);
static_assert(!contains_v<Empty, int>);

// remove
static_assert(std::is_same_v<
    remove_t<TypeList<int, double, int, char>, int>,
    TypeList<double, char>>);

static_assert(std::is_same_v<
    remove_t<List1, float>,  // removing non-existent type
    List1>);

// concat
static_assert(std::is_same_v<
    concat_t<TypeList<int, double>, TypeList<char, float>>,
    TypeList<int, double, char, float>>);

int main() {
    // All work is done at compile time via static_assert.
    // If this compiles, everything works.
    return 0;
}
```

Every operation is purely a type-level transformation with zero runtime cost. The compiler resolves all template instantiations during compilation, and the resulting program contains no type list logic at all.'''
    ),
    (
        "cpp_deep2_13",
        r'''Write a C++17 constexpr function that computes the SHA-256 of a compile-time string (or at least demonstrate significant compile-time string processing — hash, reverse, transform).''',
        r'''<think>
Full SHA-256 at compile time is doable but very long. I'll focus on practical
compile-time string processing: FNV-1a hash (widely used, simple), reverse, transform,
and a compile-time string class that can be used as a template parameter (C++20 fixed_string).

For C++17 constexpr: I can use string_view and operate on it. For NTTP strings I need C++20.
I'll show:
1. constexpr FNV-1a hash
2. constexpr string reverse (returning array)
3. constexpr to_upper / to_lower
4. constexpr string contains/find
5. A FixedString class for NTTP usage (C++20)

These are genuinely useful — compile-time hashing is used for string switch statements,
and fixed strings enable strings as template parameters.
</think>

Here is a comprehensive compile-time string processing library:

```cpp
#include <array>
#include <cstdint>
#include <cstddef>
#include <string_view>
#include <iostream>
#include <type_traits>

namespace ct {

// ================================================================
// FNV-1a hash (64-bit) — compile-time string hashing
// ================================================================
constexpr uint64_t fnv1a_hash(std::string_view sv) {
    uint64_t hash = 14695981039346656037ULL;  // FNV offset basis
    for (char c : sv) {
        hash ^= static_cast<uint64_t>(c);
        hash *= 1099511628211ULL;             // FNV prime
    }
    return hash;
}

// Operator for ergonomic usage
constexpr uint64_t operator""_hash(const char* str, std::size_t len) {
    return fnv1a_hash({str, len});
}

// ================================================================
// Compile-time string reverse
// ================================================================
template <std::size_t N>
constexpr std::array<char, N + 1> reverse(const char (&str)[N]) {
    std::array<char, N + 1> result{};
    for (std::size_t i = 0; i < N - 1; ++i) {
        result[i] = str[N - 2 - i];  // N includes null terminator
    }
    result[N - 1] = '\0';
    return result;
}

// ================================================================
// Compile-time case conversion
// ================================================================
constexpr char to_upper_char(char c) {
    return (c >= 'a' && c <= 'z') ? static_cast<char>(c - 32) : c;
}

constexpr char to_lower_char(char c) {
    return (c >= 'A' && c <= 'Z') ? static_cast<char>(c + 32) : c;
}

template <std::size_t N>
constexpr std::array<char, N> to_upper(const char (&str)[N]) {
    std::array<char, N> result{};
    for (std::size_t i = 0; i < N; ++i)
        result[i] = to_upper_char(str[i]);
    return result;
}

template <std::size_t N>
constexpr std::array<char, N> to_lower(const char (&str)[N]) {
    std::array<char, N> result{};
    for (std::size_t i = 0; i < N; ++i)
        result[i] = to_lower_char(str[i]);
    return result;
}

// ================================================================
// Compile-time string search
// ================================================================
constexpr bool contains(std::string_view haystack, std::string_view needle) {
    if (needle.size() > haystack.size()) return false;
    for (std::size_t i = 0; i <= haystack.size() - needle.size(); ++i) {
        bool match = true;
        for (std::size_t j = 0; j < needle.size(); ++j) {
            if (haystack[i + j] != needle[j]) {
                match = false;
                break;
            }
        }
        if (match) return true;
    }
    return false;
}

constexpr std::size_t count_char(std::string_view sv, char c) {
    std::size_t n = 0;
    for (char ch : sv) {
        if (ch == c) ++n;
    }
    return n;
}

// ================================================================
// C++20: FixedString for non-type template parameters
// ================================================================
template <std::size_t N>
struct FixedString {
    char data[N]{};

    constexpr FixedString(const char (&str)[N]) {
        for (std::size_t i = 0; i < N; ++i)
            data[i] = str[i];
    }

    constexpr operator std::string_view() const {
        return {data, N - 1};
    }

    constexpr std::size_t size() const { return N - 1; }
};

// Use FixedString as NTTP (C++20)
template <FixedString Name>
struct NamedTag {
    static constexpr auto name = Name;
    static constexpr auto hash = fnv1a_hash(Name);
};

} // namespace ct

// ================================================================
// Practical use: compile-time string switch
// ================================================================
constexpr int command_id(std::string_view cmd) {
    switch (ct::fnv1a_hash(cmd)) {
        case "start"_hash:  return 1;
        case "stop"_hash:   return 2;
        case "pause"_hash:  return 3;
        case "resume"_hash: return 4;
        default:            return -1;
    }
}

int main() {
    // Hash — compile-time
    static_assert(ct::fnv1a_hash("hello") == "hello"_hash);
    static_assert(ct::fnv1a_hash("hello") != ct::fnv1a_hash("world"));

    // Reverse
    constexpr auto rev = ct::reverse("abcdef");
    static_assert(std::string_view(rev.data()) == "fedcba");

    // Case conversion
    constexpr auto upper = ct::to_upper("Hello World!");
    static_assert(std::string_view(upper.data()) == "HELLO WORLD!");

    constexpr auto lower = ct::to_lower("Hello World!");
    static_assert(std::string_view(lower.data()) == "hello world!");

    // String search
    static_assert(ct::contains("hello world", "world"));
    static_assert(!ct::contains("hello world", "xyz"));
    static_assert(ct::count_char("mississippi", 's') == 4);

    // String switch (works at runtime with compile-time hashes)
    std::cout << "start -> " << command_id("start") << "\n";   // 1
    std::cout << "stop  -> " << command_id("stop") << "\n";    // 2
    std::cout << "other -> " << command_id("other") << "\n";   // -1

    // C++20 FixedString as NTTP
    using Tag = ct::NamedTag<"player_health">;
    std::cout << "Tag: " << std::string_view(Tag::name) << "\n";
    std::cout << "Hash: " << Tag::hash << "\n";

    return 0;
}
```

The FNV-1a hash is particularly useful — it enables string "switch" statements by comparing precomputed hashes. Note that hash collisions are theoretically possible, so for safety-critical code you should add a string comparison fallback.'''
    ),
    (
        "cpp_deep2_14",
        r'''Show how to build a compile-time state machine in C++ using template metaprogramming. The state machine should validate transitions at compile time.''',
        r'''<think>
A compile-time state machine validates that state transitions are legal during compilation.
The approach:
1. Define states and events as types (or enums)
2. Define a transition table mapping (State, Event) -> NextState
3. Use template specialization or constexpr to look up transitions
4. Chain transitions and verify the final state

I'll model a simple turnstile: Locked --(Coin)--> Unlocked --(Push)--> Locked.
Invalid transitions (Push when Locked, Coin when Unlocked) should cause compile errors.

For the type-level approach: each transition is a template specialization.
Missing specializations = compile error = invalid transition detected.
I'll also show a constexpr approach that's more readable.
</think>

Here is a compile-time state machine with transition validation:

```cpp
#include <type_traits>
#include <iostream>

// ================================================================
// Approach 1: Type-level state machine (compile error on bad transition)
// ================================================================

namespace type_fsm {

// States
struct Locked {};
struct Unlocked {};

// Events
struct Coin {};
struct Push {};

// Transition table: undefined primary = invalid transition
template <typename State, typename Event>
struct Transition;  // No default — instantiating this for an invalid
                    // (State, Event) pair causes a compile error.

// Valid transitions
template <>
struct Transition<Locked, Coin> {
    using next_state = Unlocked;
};

template <>
struct Transition<Unlocked, Push> {
    using next_state = Locked;
};

// Optional: allow Coin when already Unlocked (stays Unlocked)
template <>
struct Transition<Unlocked, Coin> {
    using next_state = Unlocked;
};

// Apply a sequence of events at compile time
template <typename State>
struct Machine {
    using state = State;

    template <typename Event>
    using apply = Machine<typename Transition<State, Event>::next_state>;
};

// Tests: valid sequences compile, invalid ones don't
using M0 = Machine<Locked>;
using M1 = M0::apply<Coin>;         // Locked --Coin--> Unlocked
using M2 = M1::apply<Push>;         // Unlocked --Push--> Locked
using M3 = M2::apply<Coin>;         // Locked --Coin--> Unlocked
using M4 = M3::apply<Coin>;         // Unlocked --Coin--> Unlocked (self-loop)

static_assert(std::is_same_v<M0::state, Locked>);
static_assert(std::is_same_v<M1::state, Unlocked>);
static_assert(std::is_same_v<M2::state, Locked>);
static_assert(std::is_same_v<M4::state, Unlocked>);

// This would cause a compile error (Push when Locked is undefined):
// using Bad = M0::apply<Push>;

} // namespace type_fsm


// ================================================================
// Approach 2: constexpr state machine (better error messages)
// ================================================================

namespace constexpr_fsm {

enum class State { Locked, Unlocked, Error };
enum class Event { Coin, Push };

constexpr State transition(State s, Event e) {
    switch (s) {
        case State::Locked:
            switch (e) {
                case Event::Coin: return State::Unlocked;
                case Event::Push: return State::Locked;  // or Error
            }
            break;
        case State::Unlocked:
            switch (e) {
                case Event::Coin: return State::Unlocked;
                case Event::Push: return State::Locked;
            }
            break;
        default:
            return State::Error;
    }
    return State::Error;
}

// Apply a sequence of events
template <typename... Events>
constexpr State run(State initial, Events... events) {
    State s = initial;
    // Fold expression to apply each event
    ((s = transition(s, events)), ...);
    return s;
}

// Validate at compile time
static_assert(
    run(State::Locked, Event::Coin) == State::Unlocked
);
static_assert(
    run(State::Locked, Event::Coin, Event::Push) == State::Locked
);
static_assert(
    run(State::Locked, Event::Coin, Event::Push, Event::Coin, Event::Push)
        == State::Locked
);

// ================================================================
// Approach 3: Table-driven with constexpr validation
// ================================================================

struct TransitionEntry {
    State from;
    Event event;
    State to;
};

constexpr TransitionEntry table[] = {
    {State::Locked,   Event::Coin, State::Unlocked},
    {State::Unlocked, Event::Push, State::Locked},
    {State::Unlocked, Event::Coin, State::Unlocked},
    {State::Locked,   Event::Push, State::Locked},
};

constexpr State lookup(State from, Event ev) {
    for (const auto& entry : table) {
        if (entry.from == from && entry.event == ev)
            return entry.to;
    }
    return State::Error;
}

constexpr bool validate_sequence(State init, const Event* events, std::size_t n) {
    State s = init;
    for (std::size_t i = 0; i < n; ++i) {
        s = lookup(s, events[i]);
        if (s == State::Error) return false;
    }
    return true;
}

constexpr Event seq[] = {Event::Coin, Event::Push, Event::Coin};
static_assert(validate_sequence(State::Locked, seq, 3));

} // namespace constexpr_fsm

int main() {
    std::cout << "All compile-time state machine checks passed.\n";

    // Runtime usage of the constexpr FSM
    using namespace constexpr_fsm;
    State s = State::Locked;
    Event events[] = {Event::Coin, Event::Push, Event::Coin, Event::Push};

    for (auto e : events) {
        s = transition(s, e);
        std::cout << "State: " << (s == State::Locked ? "Locked" : "Unlocked") << "\n";
    }

    return 0;
}
```

The type-level approach (Approach 1) gives the strongest guarantee: invalid transitions literally fail to compile because there is no template specialization for them. The constexpr approaches (2 and 3) are more readable and allow runtime use, while still being verifiable at compile time via `static_assert`.'''
    ),
    (
        "cpp_deep2_15",
        r'''Implement a compile-time regular expression matcher in C++ that handles literal characters, `.` (any char), `*` (zero or more of previous), and `+` (one or more). It should work entirely at compile time.''',
        r'''<think>
A constexpr regex matcher needs to handle:
- Literal character matching
- '.' matches any single character
- '*' zero or more of the preceding element
- '+' one or more of the preceding element

This is essentially a recursive descent matcher. The key challenge is handling * and +
which require backtracking.

I'll implement this as a constexpr function taking string_view for both pattern and text.
The algorithm:
- If pattern is empty, match succeeds iff text is empty (for full match) or always (for search)
- If next pattern char is followed by *, try matching 0 or more of current
- If next pattern char is followed by +, try matching 1 or more of current
- Otherwise, match current char and recurse

I need to be careful with the recursion depth for constexpr evaluation.
I'll provide both full-match and search (find) variants.
Let me keep it clean and well-commented since regex matching logic can be confusing.
</think>

Here is a compile-time regex matcher:

```cpp
#include <string_view>
#include <iostream>
#include <cstddef>

namespace ct_regex {

// Check if a pattern character matches a text character
constexpr bool char_matches(char pattern, char text) {
    return pattern == '.' || pattern == text;
}

// Forward declaration
constexpr bool match_here(std::string_view pattern, std::string_view text);

// Match pattern starting with c* or c+ against text
// 'star' handles *, 'plus' handles + (requires at least one match)
constexpr bool match_star(char c, std::string_view pattern,
                          std::string_view text) {
    // Try matching zero occurrences first, then one, two, etc.
    // (This gives shortest-match semantics; reverse loop for greedy)
    std::size_t i = 0;
    do {
        if (match_here(pattern, text.substr(i)))
            return true;
        if (i >= text.size() || !char_matches(c, text[i]))
            break;
        ++i;
    } while (true);
    return false;
}

constexpr bool match_plus(char c, std::string_view pattern,
                          std::string_view text) {
    // Must match at least one occurrence of c
    std::size_t i = 0;
    while (i < text.size() && char_matches(c, text[i])) {
        ++i;
        if (match_here(pattern, text.substr(i)))
            return true;
    }
    return false;
}

// Match pattern at the beginning of text
constexpr bool match_here(std::string_view pattern, std::string_view text) {
    if (pattern.empty())
        return text.empty();  // Full match requires consuming all text

    // Check for quantifiers on the next character
    if (pattern.size() >= 2) {
        if (pattern[1] == '*')
            return match_star(pattern[0], pattern.substr(2), text);
        if (pattern[1] == '+')
            return match_plus(pattern[0], pattern.substr(2), text);
    }

    // Handle $ anchor at end of pattern
    if (pattern[0] == '$' && pattern.size() == 1)
        return text.empty();

    // Match single character
    if (!text.empty() && char_matches(pattern[0], text[0]))
        return match_here(pattern.substr(1), text.substr(1));

    return false;
}

// Full match: pattern must match entire text
constexpr bool full_match(std::string_view pattern, std::string_view text) {
    return match_here(pattern, text);
}

// Search: find pattern anywhere in text
constexpr bool search(std::string_view pattern, std::string_view text) {
    // ^ anchor
    if (!pattern.empty() && pattern[0] == '^')
        return match_here(pattern.substr(1), text);

    // Try matching at every position
    for (std::size_t i = 0; i <= text.size(); ++i) {
        // Need a modified match_here that allows trailing text
        // Use a helper that doesn't require consuming all text
        if ([&]() -> bool {
            // Inline partial match (pattern consumed = success)
            return match_partial(pattern, text.substr(i));
        }())
            return true;
    }
    return false;
}

// Partial match: pattern must be fully consumed, text can have remainder
constexpr bool match_partial_here(std::string_view pattern,
                                  std::string_view text);

constexpr bool match_partial_star(char c, std::string_view pattern,
                                  std::string_view text) {
    std::size_t i = 0;
    do {
        if (match_partial_here(pattern, text.substr(i)))
            return true;
        if (i >= text.size() || !char_matches(c, text[i]))
            break;
        ++i;
    } while (true);
    return false;
}

constexpr bool match_partial_plus(char c, std::string_view pattern,
                                  std::string_view text) {
    std::size_t i = 0;
    while (i < text.size() && char_matches(c, text[i])) {
        ++i;
        if (match_partial_here(pattern, text.substr(i)))
            return true;
    }
    return false;
}

constexpr bool match_partial_here(std::string_view pattern,
                                  std::string_view text) {
    if (pattern.empty())
        return true;  // Pattern consumed = success

    if (pattern.size() >= 2) {
        if (pattern[1] == '*')
            return match_partial_star(pattern[0], pattern.substr(2), text);
        if (pattern[1] == '+')
            return match_partial_plus(pattern[0], pattern.substr(2), text);
    }

    if (pattern[0] == '$' && pattern.size() == 1)
        return text.empty();

    if (!text.empty() && char_matches(pattern[0], text[0]))
        return match_partial_here(pattern.substr(1), text.substr(1));

    return false;
}

constexpr bool match_partial(std::string_view pattern,
                             std::string_view text) {
    return match_partial_here(pattern, text);
}

constexpr bool contains(std::string_view pattern, std::string_view text) {
    for (std::size_t i = 0; i <= text.size(); ++i) {
        if (match_partial(pattern, text.substr(i)))
            return true;
    }
    return false;
}

} // namespace ct_regex

// ================================================================
// Compile-time tests
// ================================================================

// Literal matching
static_assert(ct_regex::full_match("abc", "abc"));
static_assert(!ct_regex::full_match("abc", "abd"));
static_assert(!ct_regex::full_match("abc", "ab"));

// Dot (any character)
static_assert(ct_regex::full_match("a.c", "abc"));
static_assert(ct_regex::full_match("a.c", "axc"));
static_assert(!ct_regex::full_match("a.c", "ac"));

// Star (zero or more)
static_assert(ct_regex::full_match("ab*c", "ac"));      // zero b's
static_assert(ct_regex::full_match("ab*c", "abc"));     // one b
static_assert(ct_regex::full_match("ab*c", "abbbc"));   // three b's
static_assert(ct_regex::full_match("a.*c", "aXYZc"));   // .* matches anything

// Plus (one or more)
static_assert(!ct_regex::full_match("ab+c", "ac"));     // needs at least one b
static_assert(ct_regex::full_match("ab+c", "abc"));
static_assert(ct_regex::full_match("ab+c", "abbbbc"));

// Combined
static_assert(ct_regex::full_match("a.*b.+c", "aXXXbYc"));
static_assert(!ct_regex::full_match("a.*b.+c", "aXXXbc")); // .+ needs at least 1

// Search (find anywhere)
static_assert(ct_regex::contains("b+c", "aabbcc"));
static_assert(!ct_regex::contains("xyz", "aabbcc"));

int main() {
    std::cout << "All compile-time regex tests passed.\n";

    // Also works at runtime
    std::string text = "hello world";
    std::cout << "contains 'wo.ld': "
              << ct_regex::contains("wo.ld", text) << "\n";  // 1
    std::cout << "contains 'hel+o': "
              << ct_regex::contains("hel+o", text) << "\n";  // 1

    return 0;
}
```

This matcher handles the core regex features entirely at compile time. The `static_assert` lines prove the compiler evaluates every match during compilation. The same functions work at runtime too, since `constexpr` functions are dual-use. For production use, you would add character classes (`[a-z]`), escape sequences (`\.`), and alternation (`|`).'''
    ),

    # -------------------------------------------------------------------------
    # 16-20: Concepts (C++20)
    # -------------------------------------------------------------------------
    (
        "cpp_deep2_16",
        r'''Define C++20 concepts for `Hashable`, `Printable`, and `Container`. Show how to use them to constrain function templates with clear error messages.''',
        r'''<think>
C++20 concepts replace enable_if for constraining templates. I need to define:
1. Hashable — type can be hashed with std::hash
2. Printable — type can be streamed to std::ostream with operator<<
3. Container — type has begin(), end(), size(), and value_type

I should show:
- concept definition with requires expression
- Using concepts in function declarations (shorthand and long form)
- How errors look when constraints aren't met
- Concept composition with && and ||

For Container, I'll check for the standard container interface.
I'll demonstrate with functions that use these concepts.
</think>

Here is a set of well-defined C++20 concepts:

```cpp
#include <concepts>
#include <type_traits>
#include <iostream>
#include <string>
#include <vector>
#include <unordered_map>
#include <sstream>
#include <functional>

// ================================================================
// Concept: Hashable
// ================================================================
template <typename T>
concept Hashable = requires(const T& a) {
    { std::hash<T>{}(a) } -> std::convertible_to<std::size_t>;
};

// ================================================================
// Concept: Printable (streamable to ostream)
// ================================================================
template <typename T>
concept Printable = requires(std::ostream& os, const T& val) {
    { os << val } -> std::same_as<std::ostream&>;
};

// ================================================================
// Concept: Container
// ================================================================
template <typename T>
concept Container = requires(T a, const T& ca) {
    typename T::value_type;
    typename T::iterator;
    typename T::const_iterator;
    typename T::size_type;
    { ca.begin() } -> std::input_or_output_iterator;
    { ca.end() }   -> std::input_or_output_iterator;
    { ca.size() }  -> std::convertible_to<std::size_t>;
    { ca.empty() } -> std::convertible_to<bool>;
};

// Refined: SizedContainer with random access
template <typename T>
concept RandomAccessContainer = Container<T> && requires(const T& c, std::size_t i) {
    { c[i] } -> std::same_as<typename T::const_reference>;
};

// ================================================================
// Concept: Arithmetic (composition example)
// ================================================================
template <typename T>
concept Arithmetic = std::is_arithmetic_v<T>;

template <typename T>
concept PrintableArithmetic = Printable<T> && Arithmetic<T>;

// ================================================================
// Using concepts to constrain functions
// ================================================================

// Style 1: Trailing requires clause
template <typename T>
void print_hash(const T& value) requires Hashable<T> && Printable<T> {
    std::cout << "Value: " << value
              << " -> Hash: " << std::hash<T>{}(value) << "\n";
}

// Style 2: Concept as type constraint (shorthand)
void print_all(const Container auto& c) {
    bool first = true;
    for (const auto& elem : c) {
        if (!first) std::cout << ", ";
        std::cout << elem;
        first = false;
    }
    std::cout << "\n";
}

// Style 3: requires expression inline
template <typename T>
auto to_string_safe(const T& val) -> std::string {
    if constexpr (Printable<T>) {
        std::ostringstream oss;
        oss << val;
        return oss.str();
    } else {
        return "[unprintable type]";
    }
}

// Style 4: Concept in template parameter list
template <Container C>
auto sum_elements(const C& container) {
    typename C::value_type total{};
    for (const auto& elem : container) {
        total += elem;
    }
    return total;
}

// Overloading with concepts — most constrained wins
template <Container C>
std::string describe(const C& c) {
    return "Container with " + std::to_string(c.size()) + " elements";
}

template <RandomAccessContainer C>
std::string describe_detailed(const C& c) {
    return "RandomAccess container, size=" + std::to_string(c.size())
         + ", first=" + to_string_safe(c[0]);
}

// ================================================================
// Custom type to test concepts
// ================================================================
struct Widget {
    int id;
    std::string name;
    // Not Printable, not Hashable — will trigger concept errors if misused
};

int main() {
    // Hashable + Printable
    print_hash(42);
    print_hash(std::string("hello"));
    // print_hash(Widget{1, "w"});  // Compile error: Widget is not Hashable

    // Container
    std::vector<int> v = {1, 2, 3, 4, 5};
    std::cout << "Vector: ";
    print_all(v);

    std::string s = "hello";
    std::cout << "String: ";
    print_all(s);  // string is a Container of chars

    // Sum
    std::cout << "Sum: " << sum_elements(v) << "\n";

    // Concept-based overload resolution
    std::cout << describe(v) << "\n";
    std::cout << describe_detailed(v) << "\n";

    // Compile-time concept checks
    static_assert(Hashable<int>);
    static_assert(Hashable<std::string>);
    static_assert(!Hashable<Widget>);
    static_assert(Printable<int>);
    static_assert(!Printable<Widget>);
    static_assert(Container<std::vector<int>>);
    static_assert(Container<std::string>);
    static_assert(!Container<int>);
    static_assert(RandomAccessContainer<std::vector<int>>);

    std::cout << "All checks passed.\n";
    return 0;
}
```

When a concept constraint is violated, the compiler produces an error message that names the unsatisfied concept and shows which requirement failed. This is vastly better than the cryptic template errors from SFINAE-based `enable_if` approaches.'''
    ),
    (
        "cpp_deep2_17",
        r'''Show how to write complex `requires` clauses in C++20 — nested requirements, compound expressions, type requirements, and how to use `requires requires`.''',
        r'''<think>
The requires clause syntax in C++20 has several forms:
1. Simple requirements — just check if an expression is valid
2. Type requirements — check if a type exists (typename T::something)
3. Compound requirements — check expression validity AND constrain the return type
4. Nested requirements — requires { requires expr; } for boolean constraints
5. The confusing "requires requires" — a requires clause containing a requires expression

I need to show all of these clearly with examples.
I should also demonstrate the difference between a requires-clause (on a template)
and a requires-expression (an expression that evaluates to bool).
</think>

Here is a comprehensive guide to `requires` clauses:

```cpp
#include <concepts>
#include <type_traits>
#include <iostream>
#include <string>
#include <vector>

// ================================================================
// 1. Simple requirements — check expression validity
// ================================================================
template <typename T>
concept Addable = requires(T a, T b) {
    a + b;       // Must be valid expression (return type not checked)
    a += b;      // Must support +=
};

// ================================================================
// 2. Type requirements — check that types exist
// ================================================================
template <typename T>
concept HasValueType = requires {
    typename T::value_type;      // T must have a nested value_type
    typename T::iterator;        // and an iterator type
};

// ================================================================
// 3. Compound requirements — expression validity + return type constraint
// ================================================================
template <typename T>
concept Stringifiable = requires(const T& v) {
    // Expression must be valid AND return something convertible to std::string
    { v.to_string() } -> std::convertible_to<std::string>;
};

template <typename T>
concept Comparable = requires(const T& a, const T& b) {
    // Each comparison must return something boolean-testable
    { a == b } -> std::convertible_to<bool>;
    { a != b } -> std::convertible_to<bool>;
    { a < b }  -> std::convertible_to<bool>;
    { a > b }  -> std::convertible_to<bool>;
};

// ================================================================
// 4. Nested requirements — boolean constraints inside requires
// ================================================================
template <typename T>
concept SmallTrivial = requires {
    // 'requires' inside 'requires' = evaluate a boolean condition
    requires sizeof(T) <= 16;
    requires std::is_trivially_copyable_v<T>;
};

template <typename T>
concept SignedNumeric = requires(T a) {
    a + a;
    a * a;
    -a;
    requires std::is_signed_v<T>;           // Nested requirement
    requires !std::is_same_v<T, bool>;      // Exclude bool
};

// ================================================================
// 5. The "requires requires" pattern
// ================================================================

// The FIRST 'requires' is a requires-CLAUSE (constrains the template).
// The SECOND 'requires' begins a requires-EXPRESSION (evaluates to bool).
template <typename T>
    requires requires(T a, T b) {   // requires-clause + requires-expression
        { a + b } -> std::same_as<T>;
    }
void add_in_place(T& a, const T& b) {
    a = a + b;
}

// This is equivalent to defining a concept first:
template <typename T>
concept ClosedUnderAddition = requires(T a, T b) {
    { a + b } -> std::same_as<T>;
};

template <ClosedUnderAddition T>  // Much cleaner
void add_in_place_v2(T& a, const T& b) {
    a = a + b;
}

// ================================================================
// 6. Combining all forms in one concept
// ================================================================
template <typename T>
concept SerializableContainer = requires(T container, const T& cc) {
    // Type requirement
    typename T::value_type;
    typename T::size_type;

    // Simple requirements
    container.clear();
    container.begin();
    container.end();

    // Compound requirements
    { cc.size() } -> std::convertible_to<std::size_t>;
    { cc.empty() } -> std::same_as<bool>;
    { cc.data() } -> std::same_as<const typename T::value_type*>;

    // Nested requirements
    requires std::is_trivially_copyable_v<typename T::value_type>;
    requires sizeof(typename T::value_type) <= 64;
};

// ================================================================
// 7. Conditional / disjunctive requirements
// ================================================================
template <typename T>
concept Displayable = Stringifiable<T> || requires(std::ostream& os, const T& v) {
    { os << v } -> std::same_as<std::ostream&>;
};

// ================================================================
// Test types
// ================================================================
struct Point {
    double x, y;

    std::string to_string() const {
        return "(" + std::to_string(x) + ", " + std::to_string(y) + ")";
    }

    auto operator<=>(const Point&) const = default;
    bool operator==(const Point&) const = default;
};

int main() {
    // Concept checks
    static_assert(Addable<int>);
    static_assert(Addable<std::string>);  // string supports + and +=

    static_assert(HasValueType<std::vector<int>>);
    static_assert(!HasValueType<int>);

    static_assert(Stringifiable<Point>);

    static_assert(Comparable<int>);
    static_assert(Comparable<Point>);

    static_assert(SmallTrivial<int>);
    static_assert(SmallTrivial<double>);
    static_assert(!SmallTrivial<std::string>);  // not trivially copyable

    static_assert(SignedNumeric<int>);
    static_assert(SignedNumeric<double>);
    static_assert(!SignedNumeric<unsigned int>);  // not signed
    static_assert(!SignedNumeric<bool>);          // explicitly excluded

    // vector<int> has data() and int is trivially copyable
    static_assert(SerializableContainer<std::vector<int>>);
    // string is not (value_type=char is trivial, and string has data(), but...)
    // std::string doesn't return const char* from data() in non-const? Actually it does.
    // But string::empty() might not return exactly bool on some impls.

    // requires requires in action
    int a = 10, b = 5;
    add_in_place(a, b);
    std::cout << "a + b = " << a << "\n";  // 15

    add_in_place_v2(a, b);
    std::cout << "a + b = " << a << "\n";  // 20

    std::cout << "Point: " << Point{1.0, 2.0}.to_string() << "\n";

    std::cout << "All checks passed.\n";
    return 0;
}
```

**Summary of requires syntax:**

| Form | Purpose | Example |
|------|---------|---------|
| Simple | Expression validity | `a + b;` |
| Type | Nested type exists | `typename T::value_type;` |
| Compound | Validity + return type | `{ expr } -> concept;` |
| Nested | Boolean condition | `requires sizeof(T) <= 8;` |
| `requires requires` | Inline constraint | `requires requires(T a) { a.foo(); }` |

The `requires requires` pattern is valid but considered a code smell — define a named concept instead for readability.'''
    ),
    (
        "cpp_deep2_18",
        r'''Show how C++20 concept subsumption works for overload resolution. Demonstrate a case where a more constrained overload is selected over a less constrained one.''',
        r'''<think>
Concept subsumption is how the compiler decides which constrained overload is "more specialized."
If concept A implies concept B (A subsumes B), then a function constrained by A is more
constrained and wins in overload resolution when both match.

This works through the logical structure of requires clauses — the compiler decomposes
constraints into atomic constraints and checks if one logically implies another.

Key rules:
- A && B subsumes A (and B)
- A subsumes A || B
- Subsumption only works through concepts, not through arbitrary boolean expressions

I need to show:
1. Simple subsumption: Integral -> Arithmetic (if defined correctly)
2. Concept refinement chain
3. The gotcha: subsumption doesn't work with ad-hoc requires clauses using type_traits directly
</think>

Here is a demonstration of concept subsumption:

```cpp
#include <concepts>
#include <type_traits>
#include <iostream>
#include <string>

// ================================================================
// Define a concept hierarchy where subsumption works
// ================================================================

// Base concept: anything with operator+
template <typename T>
concept Addable = requires(T a, T b) {
    { a + b } -> std::convertible_to<T>;
};

// More constrained: Addable AND has operator*
template <typename T>
concept Ring = Addable<T> && requires(T a, T b) {
    { a * b } -> std::convertible_to<T>;
    { -a } -> std::convertible_to<T>;
};

// Even more constrained: Ring AND has operator/
template <typename T>
concept Field = Ring<T> && requires(T a, T b) {
    { a / b } -> std::convertible_to<T>;
};

// ================================================================
// Overloads with subsumption
// ================================================================

// Least constrained
template <Addable T>
std::string classify(T) {
    return "Addable (supports +)";
}

// More constrained — Ring subsumes Addable
// So for types that satisfy Ring, this overload wins
template <Ring T>
std::string classify(T) {
    return "Ring (supports +, *, unary -)";
}

// Most constrained — Field subsumes Ring which subsumes Addable
template <Field T>
std::string classify(T) {
    return "Field (supports +, *, /, unary -)";
}

// ================================================================
// Another hierarchy: standard library concepts
// ================================================================

// std::integral subsumes std::signed_integral? No — it's the reverse:
// std::signed_integral is defined as std::integral<T> && is_signed
// So std::signed_integral subsumes (is more constrained than) std::integral

template <std::integral T>
std::string int_classify(T v) {
    return std::to_string(v) + " is integral";
}

template <std::signed_integral T>
std::string int_classify(T v) {
    return std::to_string(v) + " is signed integral";
}

template <std::unsigned_integral T>
std::string int_classify(T v) {
    return std::to_string(v) + " is unsigned integral";
}

// ================================================================
// GOTCHA: Subsumption does NOT work with raw type_traits
// ================================================================

// These would be AMBIGUOUS because the compiler can't see the
// logical relationship between arbitrary boolean expressions:
//
// template <typename T>
//     requires std::is_integral_v<T>
// void broken(T) {}
//
// template <typename T>
//     requires std::is_integral_v<T> && std::is_signed_v<T>
// void broken(T) {}   // AMBIGUOUS with the above!
//
// But wrapping in concepts fixes it:

template <typename T>
concept MyIntegral = std::is_integral_v<T>;

template <typename T>
concept MySignedIntegral = MyIntegral<T> && std::is_signed_v<T>;

// Now subsumption works because the compiler sees
// MySignedIntegral = MyIntegral && (something_else)

template <MyIntegral T>
std::string my_classify(T) { return "MyIntegral"; }

template <MySignedIntegral T>
std::string my_classify(T) { return "MySignedIntegral"; }

// ================================================================
// Custom type for testing
// ================================================================
struct Vec2 {
    double x, y;
    Vec2 operator+(Vec2 o) const { return {x + o.x, y + o.y}; }
    Vec2 operator-() const { return {-x, -y}; }
    // No operator* or operator/, so it's Addable but not Ring
};

int main() {
    // Custom hierarchy
    std::cout << classify(42)    << "\n";  // Field (int has +, *, /)
    std::cout << classify(3.14)  << "\n";  // Field (double has +, *, /)
    std::cout << classify(Vec2{1,2}) << "\n"; // Addable (only has +)

    // Standard library hierarchy
    std::cout << int_classify(42)   << "\n"; // signed integral (more constrained)
    std::cout << int_classify(42u)  << "\n"; // unsigned integral
    std::cout << int_classify('A')  << "\n"; // integral (char — may vary by platform)

    // Fixed subsumption with named concepts
    std::cout << my_classify(42)   << "\n";  // MySignedIntegral (more constrained)
    std::cout << my_classify(42u)  << "\n";  // MyIntegral (unsigned doesn't match signed)

    return 0;
}
```

**Subsumption rules summarized:**

1. `A && B` subsumes `A` — the conjunction is more constrained than either operand.
2. `A` subsumes `A || B` — the disjunction is less constrained.
3. Subsumption only works through **named concepts** — the compiler normalizes concept definitions into atomic constraints and checks implication. Raw `requires` clauses with type traits are opaque to the subsumption checker.
4. When multiple overloads match, the most constrained (most specific) one wins. If no overload is strictly more constrained than another, the call is ambiguous.'''
    ),
    (
        "cpp_deep2_19",
        r'''Write a C++20 concept `Serializable` that checks whether a type can be serialized to and deserialized from a byte buffer. Use it to build a generic serialize/deserialize framework.''',
        r'''<think>
I need a Serializable concept that checks for serialize/deserialize capabilities.
Options for the interface:
1. Member functions: .serialize(buffer), static T::deserialize(buffer)
2. Free functions: serialize(buffer, obj), deserialize<T>(buffer)
3. Trait-based: specialization of a Serializer<T> struct

I'll go with the free function approach as it's more extensible (works with types you don't own).
The concept should check:
- serialize(buffer&, const T&) is valid
- deserialize<T>(buffer&) returns a T
I'll define a ByteBuffer type (simple wrapper around vector<uint8_t>).
Then provide default serialization for trivially copyable types using memcpy,
and show custom serialization for a complex type.

I should also add a concept for automatically serializable types (trivially copyable).
</think>

Here is a serialize/deserialize framework using C++20 concepts:

```cpp
#include <concepts>
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <iostream>
#include <type_traits>
#include <span>
#include <stdexcept>

// ================================================================
// ByteBuffer: simple serialization target
// ================================================================
class ByteBuffer {
    std::vector<uint8_t> data_;
    std::size_t read_pos_ = 0;

public:
    void write(const void* src, std::size_t n) {
        auto* p = static_cast<const uint8_t*>(src);
        data_.insert(data_.end(), p, p + n);
    }

    void read(void* dst, std::size_t n) {
        if (read_pos_ + n > data_.size())
            throw std::runtime_error("Buffer underflow");
        std::memcpy(dst, data_.data() + read_pos_, n);
        read_pos_ += n;
    }

    std::size_t size() const { return data_.size(); }
    void reset_read() { read_pos_ = 0; }
    const uint8_t* data() const { return data_.data(); }
};

// ================================================================
// Forward declarations for free functions (ADL-found)
// ================================================================
// Users specialize these for their types.

// Default: trivially copyable types serialize via memcpy
template <typename T>
    requires std::is_trivially_copyable_v<T>
void serialize(ByteBuffer& buf, const T& val) {
    buf.write(&val, sizeof(T));
}

template <typename T>
    requires std::is_trivially_copyable_v<T>
T deserialize(ByteBuffer& buf) {
    T val;
    buf.read(&val, sizeof(T));
    return val;
}

// Specialization for std::string
inline void serialize(ByteBuffer& buf, const std::string& s) {
    uint32_t len = static_cast<uint32_t>(s.size());
    serialize(buf, len);                        // length prefix
    buf.write(s.data(), s.size());              // string data
}

template <>
inline std::string deserialize<std::string>(ByteBuffer& buf) {
    auto len = deserialize<uint32_t>(buf);
    std::string s(len, '\0');
    buf.read(s.data(), len);
    return s;
}

// Specialization for std::vector<T> (where T is itself serializable)
template <typename T>
void serialize(ByteBuffer& buf, const std::vector<T>& vec) {
    serialize(buf, static_cast<uint32_t>(vec.size()));
    for (const auto& elem : vec) {
        serialize(buf, elem);
    }
}

template <typename T>
    requires (!std::is_trivially_copyable_v<std::vector<T>>)  // avoid ambiguity
std::vector<T> deserialize_vec(ByteBuffer& buf) {
    auto count = deserialize<uint32_t>(buf);
    std::vector<T> result;
    result.reserve(count);
    for (uint32_t i = 0; i < count; ++i) {
        result.push_back(deserialize<T>(buf));
    }
    return result;
}

// ================================================================
// The Serializable concept
// ================================================================
template <typename T>
concept Serializable = requires(ByteBuffer& buf, const T& val) {
    serialize(buf, val);              // Can write to buffer
    { deserialize<T>(buf) } -> std::same_as<T>; // Can read from buffer
};

// ================================================================
// Generic framework functions using the concept
// ================================================================

// Serialize multiple values into a single buffer
template <Serializable... Ts>
ByteBuffer serialize_all(const Ts&... values) {
    ByteBuffer buf;
    (serialize(buf, values), ...);  // fold expression
    return buf;
}

// Round-trip test helper
template <Serializable T>
bool round_trip_check(const T& original) {
    ByteBuffer buf;
    serialize(buf, original);
    buf.reset_read();
    T restored = deserialize<T>(buf);
    return original == restored;
}

// ================================================================
// Custom type example
// ================================================================
struct Player {
    uint32_t id;
    std::string name;
    float health;
    float x, y;

    bool operator==(const Player&) const = default;
};

// Custom serialize/deserialize for Player
void serialize(ByteBuffer& buf, const Player& p) {
    serialize(buf, p.id);
    serialize(buf, p.name);
    serialize(buf, p.health);
    serialize(buf, p.x);
    serialize(buf, p.y);
}

template <>
Player deserialize<Player>(ByteBuffer& buf) {
    Player p;
    p.id     = deserialize<uint32_t>(buf);
    p.name   = deserialize<std::string>(buf);
    p.health = deserialize<float>(buf);
    p.x      = deserialize<float>(buf);
    p.y      = deserialize<float>(buf);
    return p;
}

// Verify Player satisfies the concept
static_assert(Serializable<int>);
static_assert(Serializable<float>);
static_assert(Serializable<std::string>);
static_assert(Serializable<Player>);

int main() {
    // Primitive round-trip
    std::cout << "int:    " << round_trip_check(42) << "\n";
    std::cout << "float:  " << round_trip_check(3.14f) << "\n";
    std::cout << "string: " << round_trip_check(std::string("hello")) << "\n";

    // Complex type round-trip
    Player p{1, "Alice", 100.0f, 10.5f, 20.3f};
    std::cout << "Player: " << round_trip_check(p) << "\n";

    // Multi-value serialization
    auto buf = serialize_all(42, std::string("world"), 3.14f);
    std::cout << "Buffer size: " << buf.size() << " bytes\n";

    buf.reset_read();
    std::cout << "Restored: "
              << deserialize<int>(buf) << ", "
              << deserialize<std::string>(buf) << ", "
              << deserialize<float>(buf) << "\n";

    return 0;
}
```

The `Serializable` concept cleanly expresses the interface contract: a type must support both `serialize(buf, val)` and `deserialize<T>(buf)`. Any function constrained with `Serializable` will produce a clear compiler error if used with a type that lacks serialization support, naming the exact unsatisfied requirement.'''
    ),
    (
        "cpp_deep2_20",
        r'''Demonstrate concept composition in C++20 — combining multiple concepts with logical operators, building concept hierarchies, and using concepts with auto parameters.''',
        r'''<think>
I need to show:
1. Combining concepts with && and ||
2. Building concept hierarchies (one concept refining another)
3. Using concepts with abbreviated function templates (auto parameters)
4. Concepts in lambda parameters (C++20)
5. Concepts with variable templates and class templates

I should create a practical example — maybe a math/geometry library with a type hierarchy:
Number -> OrderedNumber -> RealNumber, and geometric concepts like HasArea, HasPerimeter.
This gives natural composition opportunities.
</think>

Here is a comprehensive demonstration of concept composition:

```cpp
#include <concepts>
#include <type_traits>
#include <iostream>
#include <cmath>
#include <vector>
#include <string>
#include <algorithm>
#include <numeric>

// ================================================================
// 1. Base concepts
// ================================================================

template <typename T>
concept Number = requires(T a, T b) {
    { a + b } -> std::convertible_to<T>;
    { a - b } -> std::convertible_to<T>;
    { a * b } -> std::convertible_to<T>;
};

template <typename T>
concept Ordered = requires(T a, T b) {
    { a < b } -> std::convertible_to<bool>;
    { a > b } -> std::convertible_to<bool>;
    { a <= b } -> std::convertible_to<bool>;
};

template <typename T>
concept Divisible = requires(T a, T b) {
    { a / b } -> std::convertible_to<T>;
};

// ================================================================
// 2. Concept composition with && (conjunction)
// ================================================================

template <typename T>
concept OrderedNumber = Number<T> && Ordered<T>;

template <typename T>
concept RealNumber = OrderedNumber<T> && Divisible<T> && std::floating_point<T>;

// ================================================================
// 3. Concept composition with || (disjunction)
// ================================================================

template <typename T>
concept StringLike = std::same_as<T, std::string>
                  || std::same_as<T, std::string_view>
                  || std::same_as<T, const char*>;

template <typename T>
concept Displayable = requires(std::ostream& os, const T& v) {
    { os << v } -> std::same_as<std::ostream&>;
} || requires(const T& v) {
    { v.to_string() } -> std::convertible_to<std::string>;
};

// ================================================================
// 4. Geometric concept hierarchy
// ================================================================

template <typename T>
concept HasArea = requires(const T& shape) {
    { shape.area() } -> std::floating_point;
};

template <typename T>
concept HasPerimeter = requires(const T& shape) {
    { shape.perimeter() } -> std::floating_point;
};

// Composed: a full Shape has both area and perimeter
template <typename T>
concept Shape = HasArea<T> && HasPerimeter<T> && Displayable<T>;

// ================================================================
// 5. Shapes implementing the concepts
// ================================================================

struct Circle {
    double radius;

    double area() const { return M_PI * radius * radius; }
    double perimeter() const { return 2.0 * M_PI * radius; }

    friend std::ostream& operator<<(std::ostream& os, const Circle& c) {
        return os << "Circle(r=" << c.radius << ")";
    }
};

struct Rectangle {
    double width, height;

    double area() const { return width * height; }
    double perimeter() const { return 2.0 * (width + height); }

    friend std::ostream& operator<<(std::ostream& os, const Rectangle& r) {
        return os << "Rect(" << r.width << "x" << r.height << ")";
    }
};

static_assert(Shape<Circle>);
static_assert(Shape<Rectangle>);
static_assert(!Shape<int>);  // int has no area()

// ================================================================
// 6. Using concepts with auto (abbreviated function templates)
// ================================================================

// Each 'auto' with a concept creates an independent template parameter
void print_shape(const Shape auto& s) {
    std::cout << s << ": area=" << s.area()
              << ", perimeter=" << s.perimeter() << "\n";
}

// Multiple constrained auto parameters
auto larger_area(const HasArea auto& a, const HasArea auto& b) {
    return a.area() > b.area() ? a.area() : b.area();
}

// ================================================================
// 7. Concepts with lambdas (C++20)
// ================================================================

auto clamp_value = []<OrderedNumber T>(T val, T lo, T hi) -> T {
    if (val < lo) return lo;
    if (val > hi) return hi;
    return val;
};

auto numeric_transform = [](const auto& container, auto fn)
    requires requires { fn(*container.begin()); }
{
    using T = std::decay_t<decltype(fn(*container.begin()))>;
    std::vector<T> result;
    result.reserve(container.size());
    for (const auto& elem : container)
        result.push_back(fn(elem));
    return result;
};

// ================================================================
// 8. Concept-constrained variable templates
// ================================================================

template <typename T>
    requires std::floating_point<T>
constexpr T pi = static_cast<T>(3.14159265358979323846L);

template <typename T>
    requires std::integral<T>
constexpr T max_safe_value = std::numeric_limits<T>::max() / 2;

// ================================================================
// 9. Concept-constrained class template
// ================================================================

template <OrderedNumber T>
class Range {
    T lo_, hi_;
public:
    constexpr Range(T lo, T hi) : lo_(lo), hi_(hi) {}
    constexpr bool contains(T val) const { return val >= lo_ && val <= hi_; }
    constexpr T span() const requires Divisible<T> { return hi_ - lo_; }
};

int main() {
    // Shape operations
    Circle c{5.0};
    Rectangle r{3.0, 4.0};

    print_shape(c);
    print_shape(r);
    std::cout << "Larger area: " << larger_area(c, r) << "\n";

    // Constrained lambda
    std::cout << "Clamp: " << clamp_value(15, 0, 10) << "\n";       // 10
    std::cout << "Clamp: " << clamp_value(3.7, 1.0, 5.0) << "\n";  // 3.7

    // Generic transform
    std::vector<int> nums = {1, 2, 3, 4, 5};
    auto squares = numeric_transform(nums, [](int n) { return n * n; });
    for (int s : squares) std::cout << s << " ";
    std::cout << "\n";

    // Variable templates
    std::cout << "pi<float>:  " << pi<float> << "\n";
    std::cout << "pi<double>: " << pi<double> << "\n";
    std::cout << "max_safe<int>: " << max_safe_value<int> << "\n";

    // Constrained class
    Range<double> temp_range{-40.0, 50.0};
    std::cout << "20.0 in range: " << temp_range.contains(20.0) << "\n";
    std::cout << "Span: " << temp_range.span() << "\n";

    return 0;
}
```

**Composition patterns:**

| Pattern | Syntax | Meaning |
|---------|--------|---------|
| Conjunction | `A && B` | Must satisfy both |
| Disjunction | `A \|\| B` | Must satisfy at least one |
| Refinement | `concept B = A<T> && extra` | B is "A plus more" |
| Abbreviated | `void f(Concept auto x)` | Implicit template |
| Conditional member | `T foo() requires C<T>` | Member exists only if C holds |'''
    ),

    # -------------------------------------------------------------------------
    # 21-25: Advanced patterns
    # -------------------------------------------------------------------------
    (
        "cpp_deep2_21",
        r'''Implement the Curiously Recurring Template Pattern (CRTP) in C++ to add comparison operators and a clone() method to derived classes without virtual functions.''',
        r'''<think>
CRTP is where a base class is templated on the derived class: class Derived : public Base<Derived>.
This enables:
1. Static polymorphism — no vtable overhead
2. Mixin functionality — inject methods into derived classes
3. Access to derived class members from base class (via static_cast)

I need to show:
1. Comparison mixin — derive all comparison ops from operator< (like pre-C++20 approach)
2. Clone mixin — provide a clone() method that returns the correct derived type
3. Maybe a counter mixin that tracks instances

I should show why CRTP is preferable to virtual functions in certain cases:
no vtable, no dynamic dispatch overhead, enables inlining.
Also mention C++23 deducing this as a modern alternative.
</think>

Here is CRTP used for mixin functionality:

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <algorithm>

// ================================================================
// CRTP Mixin 1: Comparison operators from operator<
// (Pre-C++20 approach; spaceship operator is now preferred)
// ================================================================

template <typename Derived>
class Comparable {
public:
    friend bool operator>(const Derived& a, const Derived& b) {
        return b < a;
    }
    friend bool operator<=(const Derived& a, const Derived& b) {
        return !(b < a);
    }
    friend bool operator>=(const Derived& a, const Derived& b) {
        return !(a < b);
    }
    friend bool operator==(const Derived& a, const Derived& b) {
        return !(a < b) && !(b < a);
    }
    friend bool operator!=(const Derived& a, const Derived& b) {
        return (a < b) || (b < a);
    }
};

// ================================================================
// CRTP Mixin 2: Clonable — polymorphic clone without virtual
// ================================================================

class ClonableBase {
public:
    virtual ~ClonableBase() = default;
    virtual std::unique_ptr<ClonableBase> clone_base() const = 0;
};

template <typename Derived>
class Clonable : public ClonableBase {
public:
    std::unique_ptr<ClonableBase> clone_base() const override {
        return std::make_unique<Derived>(static_cast<const Derived&>(*this));
    }

    // Type-safe clone returning the correct derived type
    std::unique_ptr<Derived> clone() const {
        return std::make_unique<Derived>(static_cast<const Derived&>(*this));
    }
};

// ================================================================
// CRTP Mixin 3: Instance counter
// ================================================================

template <typename Derived>
class InstanceCounted {
    static inline int count_ = 0;
protected:
    InstanceCounted()  { ++count_; }
    ~InstanceCounted() { --count_; }
    InstanceCounted(const InstanceCounted&) { ++count_; }
    InstanceCounted& operator=(const InstanceCounted&) = default;
public:
    static int instance_count() { return count_; }
};

// ================================================================
// Derived classes using the CRTP mixins
// ================================================================

class Temperature : public Comparable<Temperature>,
                    public Clonable<Temperature>,
                    public InstanceCounted<Temperature> {
    double celsius_;
public:
    explicit Temperature(double c) : celsius_(c) {}
    double celsius() const { return celsius_; }

    // Only need to define operator< — Comparable provides the rest
    friend bool operator<(const Temperature& a, const Temperature& b) {
        return a.celsius_ < b.celsius_;
    }

    friend std::ostream& operator<<(std::ostream& os, const Temperature& t) {
        return os << t.celsius_ << "C";
    }
};

class Score : public Comparable<Score>,
              public InstanceCounted<Score> {
    int points_;
    std::string player_;
public:
    Score(std::string player, int pts)
        : points_(pts), player_(std::move(player)) {}

    friend bool operator<(const Score& a, const Score& b) {
        return a.points_ < b.points_;
    }

    friend std::ostream& operator<<(std::ostream& os, const Score& s) {
        return os << s.player_ << ":" << s.points_;
    }
};

int main() {
    // Comparison operators — all derived from operator<
    Temperature t1{20.0}, t2{25.0}, t3{20.0};

    std::cout << t1 << " < " << t2 << ": " << (t1 < t2) << "\n";   // 1
    std::cout << t1 << " > " << t2 << ": " << (t1 > t2) << "\n";   // 0
    std::cout << t1 << " == " << t3 << ": " << (t1 == t3) << "\n"; // 1
    std::cout << t1 << " != " << t2 << ": " << (t1 != t2) << "\n"; // 1

    // Sorting works because all comparison ops exist
    std::vector<Temperature> temps = {
        Temperature{30}, Temperature{10}, Temperature{25}, Temperature{15}
    };
    std::sort(temps.begin(), temps.end());
    std::cout << "Sorted: ";
    for (const auto& t : temps) std::cout << t << " ";
    std::cout << "\n";

    // Clone — returns correct derived type
    auto t_clone = t1.clone();
    std::cout << "Original: " << t1 << ", Clone: " << *t_clone << "\n";
    static_assert(std::is_same_v<decltype(t_clone), std::unique_ptr<Temperature>>);

    // Instance counting — separate counts per derived type
    std::cout << "Temperature instances: " << Temperature::instance_count() << "\n";
    std::cout << "Score instances: " << Score::instance_count() << "\n";
    {
        Score s1{"Alice", 100}, s2{"Bob", 95};
        std::cout << "Score instances (in scope): " << Score::instance_count() << "\n";
        std::cout << s1 << " > " << s2 << ": " << (s1 > s2) << "\n";
    }
    std::cout << "Score instances (after scope): " << Score::instance_count() << "\n";

    return 0;
}
```

**CRTP advantages over virtual functions:**
- Zero runtime overhead — all dispatch resolved at compile time
- Enables inlining of mixin methods
- Each derived class gets its own static data (like instance_count)

**Modern alternative (C++23):** Deducing `this` can replace many CRTP uses:
```cpp
struct Comparable {
    bool operator>(this auto const& self, auto const& other) {
        return other < self;
    }
};
```'''
    ),
    (
        "cpp_deep2_22",
        r'''Implement policy-based design in C++ — a configurable class that selects behavior through template policy parameters. Show a logger with output policy, format policy, and filter policy.''',
        r'''<think>
Policy-based design (Alexandrescu's Modern C++ Design) uses template parameters as
"policy classes" that inject behavior. Each policy handles one axis of variability.

For a Logger, I'll define three policy axes:
1. Output policy — where to write (console, file, null/discard)
2. Format policy — how to format messages (plain, timestamped, JSON)
3. Filter policy — which messages pass (all, severity-based, regex)

The Logger class inherits from or contains instances of each policy.
Typically you inherit privately to leverage EBO (empty base optimization) for stateless policies.

I'll make policies composable with sensible defaults.
Each policy is a simple class with a specific interface.
</think>

Here is a policy-based logger:

```cpp
#include <iostream>
#include <fstream>
#include <string>
#include <string_view>
#include <chrono>
#include <sstream>
#include <iomanip>
#include <concepts>

// ================================================================
// Severity levels
// ================================================================
enum class Severity { Debug, Info, Warning, Error, Fatal };

constexpr const char* severity_name(Severity s) {
    switch (s) {
        case Severity::Debug:   return "DEBUG";
        case Severity::Info:    return "INFO";
        case Severity::Warning: return "WARN";
        case Severity::Error:   return "ERROR";
        case Severity::Fatal:   return "FATAL";
    }
    return "UNKNOWN";
}

// ================================================================
// Policy concepts (optional, but gives better errors)
// ================================================================
template <typename T>
concept OutputPolicy = requires(T out, std::string_view msg) {
    out.write(msg);
};

template <typename T>
concept FormatPolicy = requires(T fmt, Severity s, std::string_view msg) {
    { fmt.format(s, msg) } -> std::convertible_to<std::string>;
};

template <typename T>
concept FilterPolicy = requires(T flt, Severity s) {
    { flt.should_log(s) } -> std::convertible_to<bool>;
};

// ================================================================
// Output Policies
// ================================================================

struct ConsoleOutput {
    void write(std::string_view msg) const {
        std::cout << msg << "\n";
    }
};

struct StderrOutput {
    void write(std::string_view msg) const {
        std::cerr << msg << "\n";
    }
};

class FileOutput {
    mutable std::ofstream file_;
public:
    explicit FileOutput(const std::string& path) : file_(path, std::ios::app) {}
    void write(std::string_view msg) const {
        file_ << msg << "\n";
    }
};

struct NullOutput {
    void write(std::string_view) const {}  // discard
};

// Composite: write to multiple outputs
template <OutputPolicy... Outputs>
struct MultiOutput {
    std::tuple<Outputs...> outputs;

    explicit MultiOutput(Outputs... outs) : outputs(std::move(outs)...) {}

    void write(std::string_view msg) const {
        std::apply([&](const auto&... out) {
            (out.write(msg), ...);
        }, outputs);
    }
};

// ================================================================
// Format Policies
// ================================================================

struct PlainFormat {
    std::string format(Severity s, std::string_view msg) const {
        return std::string("[") + severity_name(s) + "] " + std::string(msg);
    }
};

struct TimestampFormat {
    std::string format(Severity s, std::string_view msg) const {
        auto now = std::chrono::system_clock::now();
        auto time = std::chrono::system_clock::to_time_t(now);
        std::ostringstream oss;
        oss << std::put_time(std::localtime(&time), "%Y-%m-%d %H:%M:%S")
            << " [" << severity_name(s) << "] " << msg;
        return oss.str();
    }
};

struct JsonFormat {
    std::string format(Severity s, std::string_view msg) const {
        // Simple JSON (no escaping for brevity)
        return std::string(R"({"level":")")
             + severity_name(s)
             + R"(","message":")" + std::string(msg) + R"("})";
    }
};

// ================================================================
// Filter Policies
// ================================================================

struct AllPassFilter {
    bool should_log(Severity) const { return true; }
};

struct SeverityFilter {
    Severity min_level;
    explicit SeverityFilter(Severity min = Severity::Info) : min_level(min) {}
    bool should_log(Severity s) const {
        return static_cast<int>(s) >= static_cast<int>(min_level);
    }
};

struct ErrorOnlyFilter {
    bool should_log(Severity s) const {
        return s >= Severity::Error;
    }
};

// ================================================================
// The Logger — assembled from policies
// ================================================================

template <OutputPolicy   Output   = ConsoleOutput,
          FormatPolicy   Format   = PlainFormat,
          FilterPolicy   Filter   = AllPassFilter>
class Logger : private Output, private Format, private Filter {
    // Private inheritance for EBO (empty base optimization)
public:
    Logger() = default;

    explicit Logger(Output out, Format fmt = {}, Filter flt = {})
        : Output(std::move(out))
        , Format(std::move(fmt))
        , Filter(std::move(flt)) {}

    void log(Severity severity, std::string_view message) {
        if (!Filter::should_log(severity)) return;

        std::string formatted = Format::format(severity, message);
        Output::write(formatted);
    }

    void debug(std::string_view msg)   { log(Severity::Debug, msg); }
    void info(std::string_view msg)    { log(Severity::Info, msg); }
    void warning(std::string_view msg) { log(Severity::Warning, msg); }
    void error(std::string_view msg)   { log(Severity::Error, msg); }
    void fatal(std::string_view msg)   { log(Severity::Fatal, msg); }
};

// ================================================================
// Type aliases for common configurations
// ================================================================

using SimpleLogger     = Logger<ConsoleOutput, PlainFormat, AllPassFilter>;
using ProductionLogger = Logger<ConsoleOutput, TimestampFormat, SeverityFilter>;
using JsonLogger       = Logger<ConsoleOutput, JsonFormat, SeverityFilter>;
using DebugLogger      = Logger<StderrOutput, TimestampFormat, AllPassFilter>;

int main() {
    // Simple console logger
    SimpleLogger simple;
    simple.info("Application started");
    simple.debug("Debug details here");

    std::cout << "\n--- Production Logger (Info+) ---\n";
    ProductionLogger prod(ConsoleOutput{}, TimestampFormat{},
                          SeverityFilter{Severity::Info});
    prod.debug("This is filtered out");
    prod.info("Server listening on port 8080");
    prod.warning("High memory usage");
    prod.error("Connection timeout");

    std::cout << "\n--- JSON Logger (Warning+) ---\n";
    JsonLogger json(ConsoleOutput{}, JsonFormat{},
                    SeverityFilter{Severity::Warning});
    json.info("Filtered out");
    json.warning("Disk space low");
    json.error("Database connection failed");

    std::cout << "\n--- Multi-Output Logger ---\n";
    Logger<MultiOutput<ConsoleOutput, StderrOutput>,
           PlainFormat, AllPassFilter>
        multi(MultiOutput<ConsoleOutput, StderrOutput>(
            ConsoleOutput{}, StderrOutput{}));
    multi.info("Goes to both cout and cerr");

    return 0;
}
```

**Policy-based design benefits:**
- **Zero overhead** — policies are resolved at compile time, stateless policies consume zero bytes (EBO)
- **Combinatorial flexibility** — 4 outputs x 3 formats x 3 filters = 36 configurations from 10 small classes
- **Open for extension** — add new policies without modifying the Logger
- **Type safety** — concepts ensure each policy meets its contract'''
    ),
    (
        "cpp_deep2_23",
        r'''Implement expression templates in C++ to optimize chained vector arithmetic operations like `a + b * c - d` by eliminating temporaries.''',
        r'''<think>
Expression templates are the classic lazy evaluation technique for numeric C++.
The idea: instead of operator+ returning a new vector (temporary), it returns a
lightweight expression object that captures the operation. The actual computation
happens only when the result is assigned to a concrete vector.

This eliminates temporaries and enables loop fusion — instead of:
  temp1 = b * c  (loop 1)
  temp2 = a + temp1  (loop 2)
  result = temp2 - d  (loop 3)
We get a single loop: result[i] = a[i] + b[i]*c[i] - d[i]

I need:
1. A Vec class that stores data
2. Expression template classes for Add, Sub, Mul, ScalarMul
3. Operators that return expression objects
4. Vec's assignment operator that evaluates the expression

The expression types need operator[] and size() so they can be nested.
I'll use CRTP or a simple base class for the expression interface.
</think>

Here are expression templates for zero-temporary vector math:

```cpp
#include <iostream>
#include <vector>
#include <cstddef>
#include <cassert>
#include <chrono>

// ================================================================
// Expression base — CRTP for the expression interface
// ================================================================

template <typename E>
struct VecExpr {
    double operator[](std::size_t i) const {
        return static_cast<const E&>(*this)[i];
    }
    std::size_t size() const {
        return static_cast<const E&>(*this).size();
    }
};

// ================================================================
// Concrete vector
// ================================================================

class Vec : public VecExpr<Vec> {
    std::vector<double> data_;
public:
    explicit Vec(std::size_t n, double val = 0.0) : data_(n, val) {}
    Vec(std::initializer_list<double> init) : data_(init) {}

    // Construct from any expression (this is where evaluation happens)
    template <typename E>
    Vec(const VecExpr<E>& expr) : data_(expr.size()) {
        for (std::size_t i = 0; i < data_.size(); ++i)
            data_[i] = expr[i];
    }

    // Assign from any expression (single-pass evaluation)
    template <typename E>
    Vec& operator=(const VecExpr<E>& expr) {
        assert(data_.size() == expr.size());
        for (std::size_t i = 0; i < data_.size(); ++i)
            data_[i] = expr[i];
        return *this;
    }

    double  operator[](std::size_t i) const { return data_[i]; }
    double& operator[](std::size_t i) { return data_[i]; }
    std::size_t size() const { return data_.size(); }
};

// ================================================================
// Binary expression template
// ================================================================

template <typename E1, typename E2, typename Op>
class BinaryExpr : public VecExpr<BinaryExpr<E1, E2, Op>> {
    const E1& lhs_;
    const E2& rhs_;
public:
    BinaryExpr(const E1& lhs, const E2& rhs) : lhs_(lhs), rhs_(rhs) {
        assert(lhs.size() == rhs.size());
    }

    double operator[](std::size_t i) const {
        return Op::apply(lhs_[i], rhs_[i]);
    }
    std::size_t size() const { return lhs_.size(); }
};

// ================================================================
// Scalar expression template
// ================================================================

template <typename E, typename Op>
class ScalarExpr : public VecExpr<ScalarExpr<E, Op>> {
    const E& vec_;
    double scalar_;
public:
    ScalarExpr(const E& vec, double s) : vec_(vec), scalar_(s) {}

    double operator[](std::size_t i) const {
        return Op::apply(vec_[i], scalar_);
    }
    std::size_t size() const { return vec_.size(); }
};

// Unary negate
template <typename E>
class NegateExpr : public VecExpr<NegateExpr<E>> {
    const E& expr_;
public:
    explicit NegateExpr(const E& e) : expr_(e) {}
    double operator[](std::size_t i) const { return -expr_[i]; }
    std::size_t size() const { return expr_.size(); }
};

// ================================================================
// Operation functors
// ================================================================

struct AddOp { static double apply(double a, double b) { return a + b; } };
struct SubOp { static double apply(double a, double b) { return a - b; } };
struct MulOp { static double apply(double a, double b) { return a * b; } };
struct DivOp { static double apply(double a, double b) { return a / b; } };

// ================================================================
// Operators (return expression objects, NOT evaluated vectors)
// ================================================================

template <typename E1, typename E2>
BinaryExpr<E1, E2, AddOp>
operator+(const VecExpr<E1>& a, const VecExpr<E2>& b) {
    return {static_cast<const E1&>(a), static_cast<const E2&>(b)};
}

template <typename E1, typename E2>
BinaryExpr<E1, E2, SubOp>
operator-(const VecExpr<E1>& a, const VecExpr<E2>& b) {
    return {static_cast<const E1&>(a), static_cast<const E2&>(b)};
}

template <typename E1, typename E2>
BinaryExpr<E1, E2, MulOp>
operator*(const VecExpr<E1>& a, const VecExpr<E2>& b) {
    return {static_cast<const E1&>(a), static_cast<const E2&>(b)};
}

// Scalar multiplication
template <typename E>
ScalarExpr<E, MulOp>
operator*(const VecExpr<E>& a, double s) {
    return {static_cast<const E&>(a), s};
}

template <typename E>
ScalarExpr<E, MulOp>
operator*(double s, const VecExpr<E>& a) {
    return {static_cast<const E&>(a), s};
}

// Unary negate
template <typename E>
NegateExpr<E> operator-(const VecExpr<E>& a) {
    return NegateExpr<E>(static_cast<const E&>(a));
}

// ================================================================
// Helper: print vector
// ================================================================

std::ostream& operator<<(std::ostream& os, const Vec& v) {
    os << "[";
    for (std::size_t i = 0; i < v.size(); ++i) {
        if (i > 0) os << ", ";
        os << v[i];
    }
    return os << "]";
}

int main() {
    Vec a = {1.0, 2.0, 3.0, 4.0};
    Vec b = {10.0, 20.0, 30.0, 40.0};
    Vec c = {0.1, 0.2, 0.3, 0.4};
    Vec d = {5.0, 5.0, 5.0, 5.0};

    // This expression creates ZERO temporaries.
    // The type of (a + b * c - d) is a nested expression template.
    // Evaluation happens in a single loop inside operator=.
    Vec result = a + b * c - d;
    // result[i] = a[i] + b[i]*c[i] - d[i]
    // = {1+1-5, 2+4-5, 3+9-5, 4+16-5} = {-3, 1, 7, 15}
    std::cout << "a + b*c - d = " << result << "\n";

    // Scalar operations
    Vec scaled = 2.0 * a + b * 0.5;
    std::cout << "2*a + b*0.5 = " << scaled << "\n";

    // Negate
    Vec neg = -a + b;
    std::cout << "-a + b = " << neg << "\n";

    // Performance comparison
    constexpr std::size_t N = 1'000'000;
    Vec x(N, 1.0), y(N, 2.0), z(N, 3.0), w(N, 4.0);
    Vec out(N);

    auto start = std::chrono::high_resolution_clock::now();
    for (int iter = 0; iter < 100; ++iter)
        out = x + y * z - w;
    auto end = std::chrono::high_resolution_clock::now();

    auto ms = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    std::cout << "Expression template: " << ms.count() << " us (100 iters)\n";
    std::cout << "Sample: out[0]=" << out[0] << "\n";

    return 0;
}
```

**How it works:** `a + b * c - d` does not perform any computation. Instead, the compiler builds a nested type:
```
BinaryExpr<
    BinaryExpr<Vec, BinaryExpr<Vec, Vec, MulOp>, AddOp>,
    Vec, SubOp>
```
When assigned to `Vec result`, a single loop evaluates `result[i] = a[i] + b[i]*c[i] - d[i]` — one pass through memory, zero temporaries, maximum cache efficiency.'''
    ),
    (
        "cpp_deep2_24",
        r'''Implement type erasure in C++ to create a polymorphic `AnyDrawable` container that can hold any type with a `draw()` method, without requiring inheritance from a common base class.''',
        r'''<think>
Type erasure hides the concrete type behind a uniform interface, like std::any or std::function.
The classic implementation uses:
1. An abstract base class (internal, not user-facing) defining the interface
2. A templated derived class that wraps the concrete type
3. A handle class that owns a pointer to the base, providing value semantics

This is basically what std::function does internally.
For AnyDrawable I need:
- Store any type that has draw() and optionally name()
- Support copy/move semantics
- No external inheritance required (the type just needs to have draw())
- Maybe add a bounds() method too to show multi-method type erasure

I'll also show the small buffer optimization (SBO) concept briefly.
C++20 concepts can validate that the type satisfies the required interface.
</think>

Here is a type erasure implementation:

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <concepts>

// ================================================================
// Concept: what types can be erased into AnyDrawable
// ================================================================

template <typename T>
concept Drawable = requires(const T& obj) {
    { obj.draw() } -> std::same_as<void>;
    { obj.name() } -> std::convertible_to<std::string>;
};

// ================================================================
// Type-erased AnyDrawable (value-semantic polymorphism)
// ================================================================

class AnyDrawable {
    // Internal interface (hidden from users)
    struct Concept {
        virtual ~Concept() = default;
        virtual void draw() const = 0;
        virtual std::string name() const = 0;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };

    // Templated model wrapping any Drawable type
    template <Drawable T>
    struct Model final : Concept {
        T obj_;

        explicit Model(T obj) : obj_(std::move(obj)) {}

        void draw() const override { obj_.draw(); }
        std::string name() const override { return obj_.name(); }
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model>(obj_);
        }
    };

    std::unique_ptr<Concept> impl_;

public:
    // Construct from any Drawable type
    template <Drawable T>
    AnyDrawable(T obj)
        : impl_(std::make_unique<Model<T>>(std::move(obj))) {}

    // Copy semantics (deep copy via clone)
    AnyDrawable(const AnyDrawable& other)
        : impl_(other.impl_ ? other.impl_->clone() : nullptr) {}

    AnyDrawable& operator=(const AnyDrawable& other) {
        if (this != &other)
            impl_ = other.impl_ ? other.impl_->clone() : nullptr;
        return *this;
    }

    // Move semantics
    AnyDrawable(AnyDrawable&&) noexcept = default;
    AnyDrawable& operator=(AnyDrawable&&) noexcept = default;

    // Forwarded interface
    void draw() const { impl_->draw(); }
    std::string name() const { return impl_->name(); }
};

// ================================================================
// A more general TypeErased<Interface> factory (reusable pattern)
// ================================================================

// For demonstration: AnyCallable (like a simplified std::function)
template <typename Signature>
class AnyCallable;

template <typename R, typename... Args>
class AnyCallable<R(Args...)> {
    struct Concept {
        virtual ~Concept() = default;
        virtual R invoke(Args... args) const = 0;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };

    template <typename F>
    struct Model final : Concept {
        F func_;
        explicit Model(F f) : func_(std::move(f)) {}
        R invoke(Args... args) const override {
            return func_(std::forward<Args>(args)...);
        }
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model>(func_);
        }
    };

    std::unique_ptr<Concept> impl_;

public:
    template <typename F>
        requires std::invocable<F, Args...>
    AnyCallable(F func) : impl_(std::make_unique<Model<F>>(std::move(func))) {}

    AnyCallable(const AnyCallable& o) : impl_(o.impl_->clone()) {}
    AnyCallable& operator=(const AnyCallable& o) {
        impl_ = o.impl_->clone();
        return *this;
    }
    AnyCallable(AnyCallable&&) noexcept = default;
    AnyCallable& operator=(AnyCallable&&) noexcept = default;

    R operator()(Args... args) const {
        return impl_->invoke(std::forward<Args>(args)...);
    }
};

// ================================================================
// Concrete types (NO inheritance required)
// ================================================================

struct Circle {
    double radius;
    void draw() const {
        std::cout << "  Drawing circle with radius " << radius << "\n";
    }
    std::string name() const { return "Circle"; }
};

struct Rectangle {
    double w, h;
    void draw() const {
        std::cout << "  Drawing rectangle " << w << "x" << h << "\n";
    }
    std::string name() const { return "Rectangle"; }
};

struct Text {
    std::string content;
    int font_size;
    void draw() const {
        std::cout << "  Drawing text '" << content
                  << "' at " << font_size << "pt\n";
    }
    std::string name() const { return "Text"; }
};

// These types have NO common base class, yet they can all go in the same container:

int main() {
    // Heterogeneous container of unrelated types
    std::vector<AnyDrawable> scene;
    scene.emplace_back(Circle{5.0});
    scene.emplace_back(Rectangle{10.0, 3.0});
    scene.emplace_back(Text{"Hello, World!", 24});
    scene.emplace_back(Circle{2.5});

    std::cout << "Drawing scene:\n";
    for (const auto& drawable : scene) {
        std::cout << "[" << drawable.name() << "]\n";
        drawable.draw();
    }

    // Value semantics — copy the entire scene
    auto scene_copy = scene;
    std::cout << "\nCopied scene has " << scene_copy.size() << " objects\n";

    // AnyCallable demonstration
    std::vector<AnyCallable<int(int, int)>> ops;
    ops.emplace_back([](int a, int b) { return a + b; });
    ops.emplace_back([](int a, int b) { return a * b; });
    ops.emplace_back([](int a, int b) { return a - b; });

    std::cout << "\nOperations on (10, 3):\n";
    for (const auto& op : ops) {
        std::cout << "  Result: " << op(10, 3) << "\n";
    }

    return 0;
}
```

**Type erasure vs. inheritance:**

| Aspect | Inheritance | Type Erasure |
|--------|-------------|--------------|
| Coupling | Types must inherit base | No inheritance needed |
| Ownership | Usually pointer/reference | Value semantics (deep copy) |
| Adding types | Must modify class hierarchy | Any conforming type works |
| Performance | Virtual dispatch | Virtual dispatch (same) |
| Use with third-party types | Requires adapter | Works directly |

The pattern is: **Concept** (internal abstract interface) + **Model** (templated wrapper) + **Handle** (the public type-erased class). This is exactly what `std::function`, `std::any`, and `std::move_only_function` use internally.'''
    ),
    (
        "cpp_deep2_25",
        r'''Implement tag dispatch in C++ to select algorithm implementations based on iterator categories. Show how this technique enables optimal implementations for different iterator strengths.''',
        r'''<think>
Tag dispatch uses type tags (typically empty structs from <iterator>) to select overloads.
The iterator category tags form a hierarchy:
  input_iterator_tag -> forward_iterator_tag -> bidirectional_iterator_tag -> random_access_iterator_tag

Classic example: std::advance uses tag dispatch internally:
- For input iterators: increment one by one (O(n))
- For bidirectional iterators: can go forward or backward
- For random access: direct arithmetic (O(1))

I'll implement:
1. my_advance — the classic example
2. my_distance — O(1) for random access, O(n) for input
3. my_rotate — different algorithms based on iterator category
4. A practical container_sort that picks insertion sort vs std::sort

I should show both the traditional tag dispatch pattern and the C++17/20 alternatives
(if constexpr with iterator concepts).
</think>

Here is tag dispatch for iterator-category-aware algorithms:

```cpp
#include <iostream>
#include <iterator>
#include <vector>
#include <list>
#include <forward_list>
#include <algorithm>
#include <type_traits>
#include <string>
#include <numeric>

// ================================================================
// 1. my_advance — classic tag dispatch example
// ================================================================

namespace detail {

// Input iterator: can only go forward, one step at a time
template <typename It>
void advance_impl(It& it, typename std::iterator_traits<It>::difference_type n,
                  std::input_iterator_tag) {
    // O(n) — must increment one by one
    assert(n >= 0 && "Input iterators can only advance forward");
    while (n-- > 0) ++it;
}

// Bidirectional: can go forward or backward
template <typename It>
void advance_impl(It& it, typename std::iterator_traits<It>::difference_type n,
                  std::bidirectional_iterator_tag) {
    // O(|n|) — but can go either direction
    if (n > 0) {
        while (n-- > 0) ++it;
    } else {
        while (n++ < 0) --it;
    }
}

// Random access: direct arithmetic
template <typename It>
void advance_impl(It& it, typename std::iterator_traits<It>::difference_type n,
                  std::random_access_iterator_tag) {
    // O(1) — direct pointer arithmetic
    it += n;
}

} // namespace detail

template <typename It>
void my_advance(It& it, typename std::iterator_traits<It>::difference_type n) {
    // Tag dispatch: the third argument is a tag object whose TYPE selects the overload
    detail::advance_impl(it, n,
        typename std::iterator_traits<It>::iterator_category{});
}

// ================================================================
// 2. my_distance — O(1) for random access, O(n) otherwise
// ================================================================

namespace detail {

template <typename It>
auto distance_impl(It first, It last, std::input_iterator_tag) {
    typename std::iterator_traits<It>::difference_type count = 0;
    while (first != last) { ++first; ++count; }
    return count;
}

template <typename It>
auto distance_impl(It first, It last, std::random_access_iterator_tag) {
    return last - first;  // O(1)
}

} // namespace detail

template <typename It>
auto my_distance(It first, It last) {
    return detail::distance_impl(first, last,
        typename std::iterator_traits<It>::iterator_category{});
}

// ================================================================
// 3. my_reverse — only available for bidirectional+
// ================================================================

namespace detail {

template <typename It>
void reverse_impl(It first, It last, std::bidirectional_iterator_tag) {
    // Standard two-pointer approach
    while (first != last && first != --last) {
        std::iter_swap(first, last);
        ++first;
    }
}

template <typename It>
void reverse_impl(It first, It last, std::random_access_iterator_tag) {
    // Can use the same algorithm, but also could use index arithmetic
    if (first == last) return;
    --last;
    while (first < last) {
        std::iter_swap(first, last);
        ++first;
        --last;
    }
}

// Note: no input_iterator_tag overload — reversing is impossible with single-pass

} // namespace detail

template <typename It>
void my_reverse(It first, It last) {
    detail::reverse_impl(first, last,
        typename std::iterator_traits<It>::iterator_category{});
}

// ================================================================
// 4. Modern alternative: if constexpr with concepts (C++20)
// ================================================================

template <typename It>
void modern_advance(It& it, std::iter_difference_t<It> n) {
    if constexpr (std::random_access_iterator<It>) {
        it += n;  // O(1)
    } else if constexpr (std::bidirectional_iterator<It>) {
        if (n > 0) while (n--) ++it;
        else       while (n++) --it;
    } else {
        while (n-- > 0) ++it;
    }
}

// ================================================================
// 5. Practical: sort dispatch based on container type
// ================================================================

namespace detail {

// Random access: use introsort (std::sort)
template <typename It>
void sort_dispatch(It first, It last, std::random_access_iterator_tag) {
    std::cout << "  -> Using std::sort (random access)\n";
    std::sort(first, last);
}

// Bidirectional: use merge sort via std::list::sort pattern
template <typename It>
void sort_dispatch(It first, It last, std::bidirectional_iterator_tag) {
    std::cout << "  -> Using insertion sort (bidirectional)\n";
    // Simple insertion sort for bidirectional iterators
    if (first == last) return;
    for (auto it = std::next(first); it != last; ++it) {
        auto key = *it;
        auto j = it;
        auto prev = std::prev(j);
        while (j != first && *prev > key) {
            *j = *prev;
            --j;
            if (j != first) --prev;
        }
        *j = key;
    }
}

// Forward: copy to vector, sort, copy back
template <typename It>
void sort_dispatch(It first, It last, std::forward_iterator_tag) {
    std::cout << "  -> Copy-sort-copy (forward only)\n";
    using T = typename std::iterator_traits<It>::value_type;
    std::vector<T> temp(first, last);
    std::sort(temp.begin(), temp.end());
    std::copy(temp.begin(), temp.end(), first);
}

} // namespace detail

template <typename It>
void universal_sort(It first, It last) {
    detail::sort_dispatch(first, last,
        typename std::iterator_traits<It>::iterator_category{});
}

// ================================================================
// Helper: print any range
// ================================================================

template <typename Container>
void print(const std::string& label, const Container& c) {
    std::cout << label << ": ";
    for (const auto& v : c) std::cout << v << " ";
    std::cout << "\n";
}

int main() {
    // --- advance ---
    std::vector<int> vec = {10, 20, 30, 40, 50};
    auto vit = vec.begin();
    my_advance(vit, 3);
    std::cout << "advance(vec, 3): " << *vit << "\n";  // 40

    std::list<int> lst = {10, 20, 30, 40, 50};
    auto lit = lst.begin();
    my_advance(lit, 3);
    std::cout << "advance(list, 3): " << *lit << "\n"; // 40

    // Bidirectional can go backwards
    my_advance(lit, -2);
    std::cout << "advance(list, -2): " << *lit << "\n"; // 20

    // --- distance ---
    std::cout << "vec distance: " << my_distance(vec.begin(), vec.end()) << "\n";
    std::cout << "lst distance: " << my_distance(lst.begin(), lst.end()) << "\n";

    // --- reverse ---
    my_reverse(vec.begin(), vec.end());
    print("reversed vec", vec);

    my_reverse(lst.begin(), lst.end());
    print("reversed lst", lst);

    // --- universal sort with dispatch ---
    std::vector<int> v2 = {5, 3, 8, 1, 9, 2};
    std::cout << "\nSorting vector:";
    universal_sort(v2.begin(), v2.end());
    print("  result", v2);

    std::list<int> l2 = {5, 3, 8, 1, 9, 2};
    std::cout << "Sorting list:";
    universal_sort(l2.begin(), l2.end());
    print("  result", l2);

    std::forward_list<int> fl = {5, 3, 8, 1, 9, 2};
    std::cout << "Sorting forward_list:";
    universal_sort(fl.begin(), fl.end());
    print("  result", fl);

    return 0;
}
```

**Tag dispatch vs. `if constexpr` vs. concepts:**

| Technique | Standard | Extensible | Readability |
|-----------|----------|------------|-------------|
| Tag dispatch | C++98 | Via new tags | Moderate |
| `if constexpr` | C++17 | Closed set | Good |
| Concepts + overloads | C++20 | Via new concepts | Best |

Tag dispatch remains prevalent in legacy code and the standard library. For new code, C++20 concepts with constrained overloads or `if constexpr` with concept checks are preferred for clarity.'''
    ),
]
