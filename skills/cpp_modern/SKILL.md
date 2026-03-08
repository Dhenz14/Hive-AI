# Modern C++ Patterns (C++17/20/23)

## Smart Pointers
```cpp
auto p = std::make_unique<Widget>(args...);   // Exclusive ownership
auto s = std::make_shared<Widget>(args...);   // Shared ownership (ref-counted)

// Transfer ownership
void take(std::unique_ptr<Widget> w);
take(std::move(p));  // p is now nullptr

// Weak reference (breaks cycles)
std::weak_ptr<Widget> w = s;
if (auto locked = w.lock()) { use(*locked); }
```

## Move Semantics
```cpp
class Buffer {
    std::vector<uint8_t> data_;
public:
    Buffer(Buffer&& other) noexcept : data_(std::move(other.data_)) {}
    Buffer& operator=(Buffer&& other) noexcept {
        data_ = std::move(other.data_);
        return *this;
    }
};

// Perfect forwarding
template<typename... Args>
auto make(Args&&... args) {
    return Widget(std::forward<Args>(args)...);
}
```

## RAII
```cpp
// Scope guard via unique_ptr + custom deleter
auto guard = std::unique_ptr<FILE, decltype(&fclose)>(
    fopen("data.bin", "rb"), &fclose);

// Lock guard
{
    std::scoped_lock lock(mutex_a, mutex_b);  // Deadlock-free multi-lock
    // ... critical section, auto-unlocks at scope exit
}
```

## Templates & Concepts (C++20)
```cpp
// Concept definition
template<typename T>
concept Numeric = std::integral<T> || std::floating_point<T>;

// Constrained function
template<Numeric T>
T clamp(T val, T lo, T hi) { return std::max(lo, std::min(val, hi)); }

// Terse syntax (abbreviated function template)
void process(const std::ranges::range auto& r) { for (auto& x : r) use(x); }
```

## std::variant & std::optional
```cpp
// Type-safe union (C++17)
using Value = std::variant<int, double, std::string>;
Value v = "hello"s;
std::visit([](auto&& x) { std::cout << x; }, v);
auto* p = std::get_if<std::string>(&v);  // nullptr if wrong type

// Nullable value (C++17)
std::optional<int> find(const std::string& key) {
    if (auto it = map.find(key); it != map.end()) return it->second;
    return std::nullopt;
}
auto val = find("k").value_or(-1);
```

## Ranges (C++20)
```cpp
#include <ranges>
namespace rv = std::views;

auto result = numbers
    | rv::filter([](int n) { return n % 2 == 0; })
    | rv::transform([](int n) { return n * n; })
    | rv::take(10);

// Lazy — nothing computed until iteration
for (int x : result) { process(x); }
```

## Error Handling
```cpp
// std::expected (C++23) — Result type
std::expected<User, Error> parse(std::string_view json) {
    if (bad) return std::unexpected(Error::ParseFail);
    return User{...};
}
auto user = parse(input);
if (user) use(*user);
else handle(user.error());

// Prefer expected/optional over exceptions for expected failure paths.
// Use exceptions for truly exceptional conditions (OOM, logic errors).
```

## Key Gotchas
- **Dangling references**: Never return `const auto&` to a temporary or local. `string_view` from a destroyed `string` = UB.
- **Object slicing**: Passing `Derived` by value to `Base` param silently chops derived data. Use pointers/refs.
- **UB pitfalls**: Signed overflow, null deref, use-after-move, iterator invalidation (erasing while iterating).
- **Rule of 5**: If you define any of destructor/copy-ctor/copy-assign/move-ctor/move-assign, define all five (or `= default`/`= delete`).
- **`const` everything**: `const auto&` for read-only params, `constexpr` for compile-time values.
- **`[[nodiscard]]`**: Mark functions whose return value must not be ignored (error codes, RAII guards).
