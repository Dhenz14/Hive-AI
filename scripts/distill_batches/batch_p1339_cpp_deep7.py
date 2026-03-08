"""C++ deep reasoning pairs batch 7: design patterns and architecture."""
PAIRS = [
    ("cpp_deep/meyers_singleton", r'''How do I implement a thread-safe Singleton in modern C++ without using mutexes or double-checked locking?''', r'''<think>
The user wants a thread-safe Singleton without explicit mutexes. The classic modern approach
is Meyer's Singleton, which exploits the C++11 guarantee that local static variable
initialization is thread-safe (magic statics, mandated by [stmt.dcl]p4).

Key design considerations:
- Delete copy constructor and copy assignment to prevent copies.
- Delete move constructor and move assignment as well.
- Make the constructor private so only the static method can create it.
- Return by reference, not pointer, to prevent deletion by callers.
- The static local variable is initialized on first call and destroyed at program exit.
- No need for std::mutex, std::call_once, or DCLP — the compiler handles it.
- Destruction order pitfall: if Singleton A depends on Singleton B, the destruction
  order is reverse of construction. We can use the Schwarz counter or explicit
  dependency ordering if needed, but for simple cases Meyer's is sufficient.
- We should also consider marking the destructor private or protected to prevent
  stack/heap allocation outside the getInstance method.
- Thread safety of access after initialization is a separate concern — if the
  singleton has mutable state, callers still need synchronization for that state.
- This pattern works on all major compilers since C++11 (GCC, Clang, MSVC).
- We can make this a CRTP base to reduce boilerplate for multiple singletons.
</think>

The best modern approach is **Meyer's Singleton**, which relies on the C++11 guarantee that initialization of function-local statics is thread-safe. No mutexes needed.

```cpp
#include <iostream>
#include <string>
#include <thread>
#include <vector>

// Meyer's Singleton — thread-safe by language guarantee (C++11 [stmt.dcl]p4)
class AppConfig {
public:
    static AppConfig& getInstance() {
        // Thread-safe initialization guaranteed by C++11.
        // Destroyed automatically at program exit (reverse construction order).
        static AppConfig instance;
        return instance;
    }

    // Delete copy and move to prevent any duplication
    AppConfig(const AppConfig&) = delete;
    AppConfig& operator=(const AppConfig&) = delete;
    AppConfig(AppConfig&&) = delete;
    AppConfig& operator=(AppConfig&&) = delete;

    void set(const std::string& key, const std::string& value) {
        // In production you'd guard mutable state with a mutex
        std::lock_guard<std::mutex> lock(mtx_);
        data_[key] = value;
    }

    std::string get(const std::string& key) const {
        std::lock_guard<std::mutex> lock(mtx_);
        auto it = data_.find(key);
        return it != data_.end() ? it->second : "";
    }

private:
    AppConfig() {
        std::cout << "AppConfig created (thread "
                  << std::this_thread::get_id() << ")\n";
    }
    ~AppConfig() {
        std::cout << "AppConfig destroyed\n";
    }

    mutable std::mutex mtx_;  // protects data_ after init
    std::unordered_map<std::string, std::string> data_;
};

// Optional: CRTP base to reduce boilerplate for multiple singletons
template <typename Derived>
class Singleton {
public:
    static Derived& getInstance() {
        static Derived instance;
        return instance;
    }

    Singleton(const Singleton&) = delete;
    Singleton& operator=(const Singleton&) = delete;

protected:
    Singleton() = default;
    ~Singleton() = default;
};

// Usage with CRTP
class Logger : public Singleton<Logger> {
    friend class Singleton<Logger>;  // allow base to call private ctor
    Logger() { std::cout << "Logger created\n"; }
public:
    void log(const std::string& msg) {
        std::cout << "[LOG] " << msg << "\n";
    }
};

#include <mutex>
#include <unordered_map>

int main() {
    // Demonstrate thread-safe first access
    std::vector<std::thread> threads;
    for (int i = 0; i < 8; ++i) {
        threads.emplace_back([i] {
            auto& cfg = AppConfig::getInstance();
            cfg.set("thread_" + std::to_string(i), "ran");
        });
    }
    for (auto& t : threads) t.join();

    // Verify all writes landed
    auto& cfg = AppConfig::getInstance();
    for (int i = 0; i < 8; ++i) {
        std::cout << "thread_" << i << " = "
                  << cfg.get("thread_" + std::to_string(i)) << "\n";
    }

    // CRTP singleton
    Logger::getInstance().log("All done");
    return 0;
}
```

Key points:
- **No mutex for initialization** — the compiler emits the equivalent of `std::call_once` for the `static AppConfig instance;` line.
- The mutex inside `AppConfig` is for protecting *mutable state after construction*, which is a separate concern.
- The CRTP `Singleton<Derived>` base eliminates boilerplate when you have multiple singletons.
- Destruction happens automatically at program exit in reverse construction order.'''),

    ("cpp_deep/factory_registration", r'''Show me how to implement a self-registering Factory pattern in C++ where new product types can be added without modifying the factory class itself.''', r'''<think>
The user wants a factory with self-registration — the open/closed principle applied
to object creation. Each concrete product registers itself with the factory at
static-initialization time, so adding a new type requires zero changes to existing code.

Design approach:
- A central Factory class holds a map from string keys to creator functions.
- Each concrete product uses a static bool or a registration helper that calls
  Factory::registerType() during static initialization.
- We can use a macro to reduce boilerplate, but I should show the mechanism first.
- The static initialization order fiasco is a real risk: the factory's map must
  exist before any product tries to register. Solution: use a function-local static
  for the map (construct-on-first-use idiom).
- Creator functions should return std::unique_ptr for clear ownership.
- C++17 inline variables can help with header-only registration, but the
  function-local-static approach is more portable.
- I'll demonstrate with a Shape hierarchy: Circle, Rectangle, Triangle each
  self-register. Adding a new shape requires only a new .cpp file.
- The macro approach (REGISTER_TYPE) is common in game engines and plugin systems.
</think>

A self-registering factory uses static-initialization-time registration so new types are added by writing a new class — the factory never changes.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <functional>
#include <unordered_map>
#include <stdexcept>

// --- Base product ---
class Shape {
public:
    virtual ~Shape() = default;
    virtual void draw() const = 0;
    virtual double area() const = 0;
};

// --- Self-registering Factory ---
class ShapeFactory {
public:
    using Creator = std::function<std::unique_ptr<Shape>()>;

    // Construct-on-first-use to avoid static init order fiasco
    static std::unordered_map<std::string, Creator>& registry() {
        static std::unordered_map<std::string, Creator> reg;
        return reg;
    }

    static bool registerType(const std::string& name, Creator creator) {
        registry()[name] = std::move(creator);
        return true;  // return value used to trigger static init
    }

    static std::unique_ptr<Shape> create(const std::string& name) {
        auto it = registry().find(name);
        if (it == registry().end()) {
            throw std::runtime_error("Unknown shape: " + name);
        }
        return it->second();
    }

    static void listTypes() {
        for (const auto& [name, _] : registry()) {
            std::cout << "  " << name << "\n";
        }
    }
};

// --- Registration macro (optional convenience) ---
#define REGISTER_SHAPE(Type, Name)                                  \
    static bool Type##_registered = ShapeFactory::registerType(     \
        Name, []() -> std::unique_ptr<Shape> {                      \
            return std::make_unique<Type>();                         \
        });

// --- Concrete products: each self-registers ---

class Circle : public Shape {
public:
    void draw() const override { std::cout << "Drawing Circle\n"; }
    double area() const override { return 3.14159 * 5 * 5; }
};
REGISTER_SHAPE(Circle, "circle")

class Rectangle : public Shape {
public:
    void draw() const override { std::cout << "Drawing Rectangle\n"; }
    double area() const override { return 4.0 * 6.0; }
};
REGISTER_SHAPE(Rectangle, "rectangle")

class Triangle : public Shape {
public:
    void draw() const override { std::cout << "Drawing Triangle\n"; }
    double area() const override { return 0.5 * 3.0 * 4.0; }
};
REGISTER_SHAPE(Triangle, "triangle")

// To add a new shape, just write a new class + REGISTER_SHAPE line.
// No factory code changes needed.

int main() {
    std::cout << "Registered shapes:\n";
    ShapeFactory::listTypes();

    std::cout << "\nCreating shapes by name:\n";
    for (const auto& name : {"circle", "rectangle", "triangle"}) {
        auto shape = ShapeFactory::create(name);
        shape->draw();
        std::cout << "  area = " << shape->area() << "\n";
    }

    // Unknown type throws
    try {
        ShapeFactory::create("hexagon");
    } catch (const std::runtime_error& e) {
        std::cout << "\nCaught: " << e.what() << "\n";
    }

    return 0;
}
```

Key design decisions:
- **Construct-on-first-use** (`registry()` returns a function-local static) avoids the static initialization order fiasco.
- The `REGISTER_SHAPE` macro assigns to a `static bool`, ensuring the registration call runs before `main()`.
- `std::function<std::unique_ptr<Shape>()>` as the creator type allows lambdas with captures if needed (e.g., parameterized construction).
- Adding a new shape in a separate translation unit requires only a class definition and one `REGISTER_SHAPE` line — the factory remains closed for modification, open for extension.'''),

    ("cpp_deep/abstract_factory_gui", r'''How would you design an Abstract Factory in C++ to support cross-platform GUI elements (buttons, text fields, dialogs) while keeping platform-specific code isolated?''', r'''<think>
The Abstract Factory pattern provides an interface for creating families of related
objects without specifying their concrete classes. For a cross-platform GUI:

- Define abstract product interfaces: Button, TextField, Dialog.
- Define an abstract GUIFactory with createButton(), createTextField(), createDialog().
- Concrete factories: WindowsFactory, LinuxFactory, MacFactory — each returns
  platform-specific implementations.
- Client code only uses the abstract interfaces, never the concrete types.

Modern C++ additions:
- Use std::unique_ptr for ownership of created widgets.
- Use enum class or string to select the factory at runtime.
- Can use a factory-of-factories (registry) pattern for extensibility.
- C++17 std::variant could replace virtual dispatch in some cases, but for a
  true abstract factory the inheritance approach is cleaner and more extensible.
- Consider using concepts (C++20) to constrain factory types if using templates.

I'll keep it practical: show the full hierarchy, a factory selector, and client
code that works identically on any platform. The code should compile and run
(using stubs that print which platform widget is being used).
</think>

The Abstract Factory isolates platform-specific creation behind a common interface. Client code never mentions `Windows`, `Linux`, or `Mac` directly.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <stdexcept>

// ====== Abstract Products ======

class Button {
public:
    virtual ~Button() = default;
    virtual void render() const = 0;
    virtual void onClick(std::function<void()> handler) = 0;
};

class TextField {
public:
    virtual ~TextField() = default;
    virtual void render() const = 0;
    virtual void setText(const std::string& text) = 0;
    virtual std::string getText() const = 0;
};

class Dialog {
public:
    virtual ~Dialog() = default;
    virtual void show(const std::string& title, const std::string& message) const = 0;
};

// ====== Abstract Factory ======

class GUIFactory {
public:
    virtual ~GUIFactory() = default;
    virtual std::unique_ptr<Button>    createButton(const std::string& label) const = 0;
    virtual std::unique_ptr<TextField> createTextField() const = 0;
    virtual std::unique_ptr<Dialog>    createDialog() const = 0;
};

// ====== Windows Concrete Products ======

class WindowsButton : public Button {
    std::string label_;
public:
    explicit WindowsButton(std::string label) : label_(std::move(label)) {}
    void render() const override {
        std::cout << "[Win32 Button: " << label_ << "]\n";
    }
    void onClick(std::function<void()> handler) override {
        std::cout << "  Win32 click handler set\n";
        handler();
    }
};

class WindowsTextField : public TextField {
    std::string text_;
public:
    void render() const override { std::cout << "[Win32 EditControl: " << text_ << "]\n"; }
    void setText(const std::string& t) override { text_ = t; }
    std::string getText() const override { return text_; }
};

class WindowsDialog : public Dialog {
public:
    void show(const std::string& title, const std::string& msg) const override {
        std::cout << "[Win32 MessageBox] " << title << ": " << msg << "\n";
    }
};

// ====== Linux Concrete Products ======

class LinuxButton : public Button {
    std::string label_;
public:
    explicit LinuxButton(std::string label) : label_(std::move(label)) {}
    void render() const override { std::cout << "[GTK Button: " << label_ << "]\n"; }
    void onClick(std::function<void()> handler) override {
        std::cout << "  GTK signal connected\n";
        handler();
    }
};

class LinuxTextField : public TextField {
    std::string text_;
public:
    void render() const override { std::cout << "[GTK Entry: " << text_ << "]\n"; }
    void setText(const std::string& t) override { text_ = t; }
    std::string getText() const override { return text_; }
};

class LinuxDialog : public Dialog {
public:
    void show(const std::string& title, const std::string& msg) const override {
        std::cout << "[GTK Dialog] " << title << ": " << msg << "\n";
    }
};

// ====== Concrete Factories ======

class WindowsFactory : public GUIFactory {
public:
    std::unique_ptr<Button> createButton(const std::string& label) const override {
        return std::make_unique<WindowsButton>(label);
    }
    std::unique_ptr<TextField> createTextField() const override {
        return std::make_unique<WindowsTextField>();
    }
    std::unique_ptr<Dialog> createDialog() const override {
        return std::make_unique<WindowsDialog>();
    }
};

class LinuxFactory : public GUIFactory {
public:
    std::unique_ptr<Button> createButton(const std::string& label) const override {
        return std::make_unique<LinuxButton>(label);
    }
    std::unique_ptr<TextField> createTextField() const override {
        return std::make_unique<LinuxTextField>();
    }
    std::unique_ptr<Dialog> createDialog() const override {
        return std::make_unique<LinuxDialog>();
    }
};

// ====== Factory Selector ======

enum class Platform { Windows, Linux };

std::unique_ptr<GUIFactory> createFactory(Platform p) {
    switch (p) {
        case Platform::Windows: return std::make_unique<WindowsFactory>();
        case Platform::Linux:   return std::make_unique<LinuxFactory>();
    }
    throw std::runtime_error("Unknown platform");
}

// ====== Client code — completely platform-agnostic ======

void buildLoginScreen(const GUIFactory& factory) {
    auto userField = factory.createTextField();
    auto passField = factory.createTextField();
    auto loginBtn  = factory.createButton("Login");
    auto dialog    = factory.createDialog();

    userField->setText("admin");
    passField->setText("****");

    std::cout << "--- Login Screen ---\n";
    userField->render();
    passField->render();
    loginBtn->render();
    loginBtn->onClick([&] {
        dialog->show("Login", "Welcome, " + userField->getText() + "!");
    });
}

int main() {
    std::cout << "=== Windows Platform ===\n";
    auto winFactory = createFactory(Platform::Windows);
    buildLoginScreen(*winFactory);

    std::cout << "\n=== Linux Platform ===\n";
    auto linFactory = createFactory(Platform::Linux);
    buildLoginScreen(*linFactory);

    return 0;
}
```

The `buildLoginScreen` function demonstrates the core value: it uses only abstract types (`Button`, `TextField`, `Dialog`) and never imports or names any platform-specific class. Swapping the factory swaps the entire widget family atomically.'''),

    ("cpp_deep/builder_compile_time", r'''Can you show a Builder pattern in C++ that uses compile-time validation to ensure all required fields are set before build() can be called?''', r'''<think>
The user wants a Builder that catches missing fields at compile time, not runtime.
The classic approach returns a different type after each required setter, so build()
is only available on the final type. This is sometimes called the "phantom type"
or "type-state" builder pattern.

Approach:
- Use a template parameter pack or bitfield template parameter to track which
  fields have been set.
- Each required setter returns a builder with an updated type parameter.
- build() is only enabled (via requires or SFINAE) when all required bits are set.

C++20 approach with concepts is cleanest:
- Template parameter: a bitmask tracking set fields.
- Each setter returns Builder<Mask | ThisBit>.
- build() is constrained with requires (Mask == AllRequired).

This gives a zero-cost abstraction: the compiler enforces the protocol, and in
optimized builds the builder chain compiles down to direct construction.

I need to be careful:
- Optional fields can be set on any builder state.
- The data must transfer between builder types (different template instantiations).
- Use friendship between all Builder<N> instantiations to share private data.
- Show a practical example like building an HttpRequest or DatabaseConfig.
</think>

Use type-state encoding: each required setter changes the builder's template parameter, and `build()` only exists when all required bits are set.

```cpp
#include <iostream>
#include <string>
#include <optional>
#include <cstdint>

// The product
struct HttpRequest {
    std::string method;
    std::string url;
    std::string host;
    std::optional<std::string> body;
    std::optional<std::string> auth_token;
    int timeout_ms = 5000;

    void print() const {
        std::cout << method << " " << url << " (host=" << host
                  << ", timeout=" << timeout_ms << "ms";
        if (body)       std::cout << ", body=" << *body;
        if (auth_token) std::cout << ", auth=***";
        std::cout << ")\n";
    }
};

// Bit flags for required fields
enum FieldBits : uint8_t {
    NONE   = 0,
    METHOD = 1 << 0,   // required
    URL    = 1 << 1,   // required
    HOST   = 1 << 2,   // required
    ALL_REQUIRED = METHOD | URL | HOST
};

// Type-state builder: Mask tracks which required fields have been set
template <uint8_t Mask = NONE>
class HttpRequestBuilder {
    // All instantiations are friends so data transfers between states
    template <uint8_t> friend class HttpRequestBuilder;

    std::string method_;
    std::string url_;
    std::string host_;
    std::optional<std::string> body_;
    std::optional<std::string> auth_token_;
    int timeout_ms_ = 5000;

    // Private constructor for state transitions
    template <uint8_t OtherMask>
    explicit HttpRequestBuilder(HttpRequestBuilder<OtherMask>&& other)
        : method_(std::move(other.method_))
        , url_(std::move(other.url_))
        , host_(std::move(other.host_))
        , body_(std::move(other.body_))
        , auth_token_(std::move(other.auth_token_))
        , timeout_ms_(other.timeout_ms_) {}

public:
    HttpRequestBuilder() = default;

    // --- Required setters: each returns a new type with updated mask ---

    auto method(std::string m) && -> HttpRequestBuilder<Mask | METHOD> {
        method_ = std::move(m);
        return HttpRequestBuilder<Mask | METHOD>(std::move(*this));
    }

    auto url(std::string u) && -> HttpRequestBuilder<Mask | URL> {
        url_ = std::move(u);
        return HttpRequestBuilder<Mask | URL>(std::move(*this));
    }

    auto host(std::string h) && -> HttpRequestBuilder<Mask | HOST> {
        host_ = std::move(h);
        return HttpRequestBuilder<Mask | HOST>(std::move(*this));
    }

    // --- Optional setters: return same type (mask unchanged) ---

    auto body(std::string b) && -> HttpRequestBuilder<Mask> {
        body_ = std::move(b);
        return HttpRequestBuilder<Mask>(std::move(*this));
    }

    auto auth(std::string token) && -> HttpRequestBuilder<Mask> {
        auth_token_ = std::move(token);
        return HttpRequestBuilder<Mask>(std::move(*this));
    }

    auto timeout(int ms) && -> HttpRequestBuilder<Mask> {
        timeout_ms_ = ms;
        return HttpRequestBuilder<Mask>(std::move(*this));
    }

    // --- build() only compiles when all required fields are set ---

    auto build() && -> HttpRequest
        requires ((Mask & ALL_REQUIRED) == ALL_REQUIRED)
    {
        return HttpRequest{
            std::move(method_), std::move(url_), std::move(host_),
            std::move(body_), std::move(auth_token_), timeout_ms_
        };
    }
};

int main() {
    // This compiles: all required fields set
    auto req = HttpRequestBuilder<>()
        .method("POST")
        .url("/api/v2/data")
        .host("example.com")
        .body(R"({"key": "value"})")
        .auth("Bearer xyz")
        .timeout(3000)
        .build();

    req.print();

    // Minimal valid request (optional fields omitted)
    auto req2 = HttpRequestBuilder<>()
        .url("/health")
        .method("GET")
        .host("localhost")
        .build();

    req2.print();

    // This would NOT compile — missing .host():
    // auto bad = HttpRequestBuilder<>()
    //     .method("GET")
    //     .url("/oops")
    //     .build();  // error: constraints not satisfied

    return 0;
}
```

The key insight: `build()` has a `requires` clause that checks the bitmask at compile time. If you forget `.host()`, the mask is `METHOD | URL` which does not satisfy `(Mask & ALL_REQUIRED) == ALL_REQUIRED`, and the compiler rejects it with a clear constraints error. Setters can be called in any order and optional fields do not affect the mask.'''),

    ("cpp_deep/prototype_clone", r'''How do I implement the Prototype pattern in modern C++ with proper clone() semantics and covariant return types?''', r'''<think>
The Prototype pattern creates new objects by cloning existing ones. In C++, this is
typically done via a virtual clone() method. Modern C++ considerations:

- clone() should return std::unique_ptr for clear ownership.
- Covariant return types only work with raw pointers, not smart pointers.
  So we need a two-level approach: a private virtual clone_impl() that returns
  a raw pointer, and a public non-virtual clone() that wraps it in unique_ptr.
- Or use the CRTP to automate clone() for derived classes.
- Deep copy semantics: clone() should produce an independent copy.
- We can use the CRTP approach to avoid writing clone_impl() in every derived class.
- Need to handle the case where derived classes add members.
- Should show both the manual approach and the CRTP-automated approach.
- C++17 auto return type deduction helps but doesn't solve the covariant smart pointer issue.
- The CRTP base can also provide a covariant unique_ptr<Derived> via static_cast.

I'll show a practical example: a document with different element types (text, image, table)
that can be deep-cloned.
</think>

The challenge is that covariant return types only work with raw pointers, not `std::unique_ptr`. The solution is a CRTP mixin that provides both type-safe cloning and ownership semantics.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>

// ====== Base with virtual clone infrastructure ======

class DocumentElement {
public:
    virtual ~DocumentElement() = default;

    // Public clone returns unique_ptr — not covariant but type-safe
    std::unique_ptr<DocumentElement> clone() const {
        return std::unique_ptr<DocumentElement>(clone_impl());
    }

    virtual void render() const = 0;
    virtual std::string type() const = 0;

protected:
    // Private virtual does the actual cloning (raw pointer for covariance)
    virtual DocumentElement* clone_impl() const = 0;
};

// ====== CRTP mixin automates clone_impl for any derived class ======

template <typename Derived, typename Base = DocumentElement>
class Cloneable : public Base {
protected:
    // Automatically implements clone_impl using Derived's copy constructor
    Base* clone_impl() const override {
        return new Derived(static_cast<const Derived&>(*this));
    }

public:
    // Type-safe clone that returns unique_ptr<Derived>
    std::unique_ptr<Derived> cloneAs() const {
        return std::unique_ptr<Derived>(
            static_cast<Derived*>(clone_impl()));
    }
};

// ====== Concrete prototypes — just inherit from Cloneable ======

class TextElement : public Cloneable<TextElement> {
    std::string content_;
    int font_size_;
public:
    TextElement(std::string text, int size)
        : content_(std::move(text)), font_size_(size) {}

    void render() const override {
        std::cout << "  [Text size=" << font_size_ << "] " << content_ << "\n";
    }
    std::string type() const override { return "Text"; }

    void setContent(const std::string& c) { content_ = c; }
};

class ImageElement : public Cloneable<ImageElement> {
    std::string path_;
    int width_, height_;
public:
    ImageElement(std::string path, int w, int h)
        : path_(std::move(path)), width_(w), height_(h) {}

    void render() const override {
        std::cout << "  [Image " << width_ << "x" << height_
                  << "] " << path_ << "\n";
    }
    std::string type() const override { return "Image"; }
};

class TableElement : public Cloneable<TableElement> {
    int rows_, cols_;
    std::vector<std::vector<std::string>> data_;
public:
    TableElement(int r, int c) : rows_(r), cols_(c), data_(r, std::vector<std::string>(c, "")) {}

    void setCell(int r, int c, const std::string& val) { data_[r][c] = val; }
    void render() const override {
        std::cout << "  [Table " << rows_ << "x" << cols_ << "]\n";
        for (const auto& row : data_) {
            std::cout << "    |";
            for (const auto& cell : row) std::cout << " " << cell << " |";
            std::cout << "\n";
        }
    }
    std::string type() const override { return "Table"; }
};

// ====== Prototype registry ======

class PrototypeRegistry {
    std::unordered_map<std::string, std::unique_ptr<DocumentElement>> prototypes_;
public:
    void registerPrototype(const std::string& name, std::unique_ptr<DocumentElement> proto) {
        prototypes_[name] = std::move(proto);
    }
    std::unique_ptr<DocumentElement> create(const std::string& name) const {
        auto it = prototypes_.find(name);
        if (it == prototypes_.end()) return nullptr;
        return it->second->clone();
    }
};

#include <unordered_map>

int main() {
    // Set up prototypes
    PrototypeRegistry registry;
    registry.registerPrototype("heading",
        std::make_unique<TextElement>("Default Heading", 24));
    registry.registerPrototype("body",
        std::make_unique<TextElement>("Default body text", 12));
    registry.registerPrototype("thumbnail",
        std::make_unique<ImageElement>("placeholder.png", 150, 150));

    // Clone from registry
    auto h1 = registry.create("heading");
    auto h2 = registry.create("heading");
    auto img = registry.create("thumbnail");

    std::cout << "Cloned elements:\n";
    h1->render();
    h2->render();
    img->render();

    // Type-safe cloneAs() — returns unique_ptr<TextElement>
    TextElement original("Deep copy test", 16);
    auto copy = original.cloneAs();  // unique_ptr<TextElement>, not DocumentElement
    copy->setContent("Modified copy");

    std::cout << "\nOriginal vs clone:\n";
    original.render();
    copy->render();

    // Deep clone a table
    TableElement table(2, 3);
    table.setCell(0, 0, "A1"); table.setCell(0, 1, "B1"); table.setCell(0, 2, "C1");
    table.setCell(1, 0, "A2"); table.setCell(1, 1, "B2"); table.setCell(1, 2, "C2");

    auto tableCopy = table.cloneAs();
    tableCopy->setCell(0, 0, "MODIFIED");

    std::cout << "\nOriginal table:\n"; table.render();
    std::cout << "Cloned table:\n";    tableCopy->render();

    return 0;
}
```

The CRTP `Cloneable<Derived>` mixin eliminates boilerplate: each concrete class just inherits from it and gets both `clone()` (returns `unique_ptr<DocumentElement>`) and `cloneAs()` (returns `unique_ptr<Derived>`) for free, using the derived class's copy constructor.'''),

    ("cpp_deep/adapter_c_api", r'''How do I wrap a C API (like POSIX file descriptors or a C library) in a modern C++ RAII adapter class?''', r'''<think>
The Adapter pattern wraps an incompatible interface to make it work with a target
interface. Wrapping C APIs in C++ RAII is one of the most practical uses.

Key concerns:
- RAII: resource acquired in constructor, released in destructor.
- Move semantics: allow transfer of ownership, disable copying.
- noexcept move: critical for use in containers (std::vector reallocation).
- Error handling: convert C error codes to exceptions or std::expected (C++23).
- Type safety: prevent mixing up raw handles.
- Zero overhead: the wrapper should compile down to the same code as raw C calls.

I'll show a practical example wrapping POSIX file descriptors, since that's universal.
Then show how to generalize to any C handle type using a template.

The template approach (HandleWrapper) can wrap any C resource: file descriptors,
FILE*, OpenGL handles, database connections, etc.

I should also mention std::expected (C++23) for error handling as a modern alternative
to exceptions.
</think>

Wrapping C APIs in RAII adapters is one of the most valuable patterns in C++. Here is a concrete example wrapping POSIX file descriptors, plus a generic template for any C handle.

```cpp
#include <iostream>
#include <string>
#include <string_view>
#include <stdexcept>
#include <utility>
#include <cstring>
#include <cerrno>
#include <cstdio>

// Simulate POSIX-like API for portability (replace with <unistd.h> on Linux)
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#define posix_open   _open
#define posix_close  _close
#define posix_read   _read
#define posix_write  _write
#else
#include <unistd.h>
#include <fcntl.h>
#define posix_open   ::open
#define posix_close  ::close
#define posix_read   ::read
#define posix_write  ::write
#endif

// ====== Specific Adapter: POSIX File Descriptor ======

class FileDescriptor {
public:
    // Acquire resource
    explicit FileDescriptor(const char* path, int flags = O_RDONLY, int mode = 0644)
        : fd_(posix_open(path, flags, mode))
    {
        if (fd_ < 0) {
            throw std::runtime_error(
                std::string("open failed: ") + path + ": " + std::strerror(errno));
        }
    }

    // Wrap an existing fd (takes ownership)
    explicit FileDescriptor(int fd) noexcept : fd_(fd) {}

    // RAII: release resource
    ~FileDescriptor() { close(); }

    // Move semantics (transfer ownership)
    FileDescriptor(FileDescriptor&& other) noexcept
        : fd_(std::exchange(other.fd_, -1)) {}

    FileDescriptor& operator=(FileDescriptor&& other) noexcept {
        if (this != &other) {
            close();
            fd_ = std::exchange(other.fd_, -1);
        }
        return *this;
    }

    // No copying (would create double-close)
    FileDescriptor(const FileDescriptor&) = delete;
    FileDescriptor& operator=(const FileDescriptor&) = delete;

    // Adapted operations
    size_t read(void* buf, size_t count) const {
        auto n = posix_read(fd_, static_cast<char*>(buf), static_cast<unsigned>(count));
        if (n < 0) throw std::runtime_error("read failed: " + std::string(std::strerror(errno)));
        return static_cast<size_t>(n);
    }

    size_t write(const void* buf, size_t count) const {
        auto n = posix_write(fd_, static_cast<const char*>(buf), static_cast<unsigned>(count));
        if (n < 0) throw std::runtime_error("write failed: " + std::string(std::strerror(errno)));
        return static_cast<size_t>(n);
    }

    void write_all(std::string_view data) const {
        while (!data.empty()) {
            auto written = write(data.data(), data.size());
            data.remove_prefix(written);
        }
    }

    // Access raw handle when interfacing with other C APIs
    int get() const noexcept { return fd_; }
    int release() noexcept { return std::exchange(fd_, -1); }
    explicit operator bool() const noexcept { return fd_ >= 0; }

private:
    void close() noexcept {
        if (fd_ >= 0) {
            posix_close(fd_);
            fd_ = -1;
        }
    }
    int fd_ = -1;
};

// ====== Generic Adapter: works for any C handle type ======

template <typename Handle, typename Traits>
class UniqueHandle {
public:
    UniqueHandle() noexcept : handle_(Traits::invalid()) {}
    explicit UniqueHandle(Handle h) noexcept : handle_(h) {}
    ~UniqueHandle() { reset(); }

    UniqueHandle(UniqueHandle&& other) noexcept
        : handle_(std::exchange(other.handle_, Traits::invalid())) {}

    UniqueHandle& operator=(UniqueHandle&& other) noexcept {
        if (this != &other) {
            reset();
            handle_ = std::exchange(other.handle_, Traits::invalid());
        }
        return *this;
    }

    UniqueHandle(const UniqueHandle&) = delete;
    UniqueHandle& operator=(const UniqueHandle&) = delete;

    Handle get() const noexcept { return handle_; }
    Handle release() noexcept { return std::exchange(handle_, Traits::invalid()); }
    explicit operator bool() const noexcept { return handle_ != Traits::invalid(); }

    void reset(Handle h = Traits::invalid()) noexcept {
        if (handle_ != Traits::invalid()) Traits::close(handle_);
        handle_ = h;
    }

private:
    Handle handle_;
};

// Traits for FILE*
struct FileTraits {
    static FILE* invalid() noexcept { return nullptr; }
    static void close(FILE* f) noexcept { std::fclose(f); }
};
using UniqueFile = UniqueHandle<FILE*, FileTraits>;

// Traits for POSIX fd
struct FdTraits {
    static int invalid() noexcept { return -1; }
    static void close(int fd) noexcept { posix_close(fd); }
};
using UniqueFd = UniqueHandle<int, FdTraits>;

int main() {
    // Specific adapter
    try {
        FileDescriptor fd("test_adapter.tmp", O_WRONLY | O_CREAT | O_TRUNC);
        fd.write_all("Hello from RAII adapter!\n");
        std::cout << "Wrote to file via FileDescriptor adapter\n";
    }  // fd closed automatically here

    {
        FileDescriptor fd("test_adapter.tmp", O_RDONLY);
        char buf[256] = {};
        auto n = fd.read(buf, sizeof(buf) - 1);
        std::cout << "Read back: " << std::string_view(buf, n);
    }

    // Generic adapter with FILE*
    {
        UniqueFile f(std::fopen("test_adapter.tmp", "a"));
        if (f) {
            std::fputs("Appended via UniqueFile\n", f.get());
            std::cout << "Appended via generic UniqueHandle<FILE*>\n";
        }
    }  // fclose called automatically

    std::remove("test_adapter.tmp");
    return 0;
}
```

Two patterns shown: (1) a hand-crafted `FileDescriptor` adapter with domain-specific methods like `write_all`, and (2) a generic `UniqueHandle<Handle, Traits>` template that wraps any C handle type with just a small traits struct. Both ensure RAII, move-only semantics, and `noexcept` move operations for container compatibility.'''),

    ("cpp_deep/bridge_pattern", r'''How do I implement the Bridge pattern in C++ to decouple an abstraction from its implementation so both can vary independently?''', r'''<think>
The Bridge pattern separates abstraction (what) from implementation (how) using
composition instead of inheritance. In C++:

- The "abstraction" holds a pointer/reference to the "implementor" interface.
- Both hierarchies can be extended independently.
- Classic example: Shape (abstraction) x Renderer (implementation).
  Shapes can be Circle, Rectangle. Renderers can be OpenGL, Vulkan, SVG.
  Without Bridge, you'd need CircleOpenGL, CircleVulkan, RectOpenGL, etc. — combinatorial.

Modern C++ considerations:
- Use std::unique_ptr for owning the implementation.
- Consider using std::shared_ptr if multiple abstractions share an implementation.
- The Pimpl idiom is a degenerate form of Bridge (1 abstraction, 1 implementation).
- Can use concepts/templates for compile-time bridge (zero overhead), but the
  classic runtime bridge is more flexible for plugin architectures.

I'll show a practical renderer example: shapes x rendering backends.
</think>

The Bridge decouples an abstraction hierarchy from an implementation hierarchy, preventing the combinatorial explosion of subclasses. Here shapes and renderers can vary independently.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <cmath>

// ====== Implementation interface (the "bridge") ======

class Renderer {
public:
    virtual ~Renderer() = default;
    virtual void renderCircle(float x, float y, float radius) = 0;
    virtual void renderRect(float x, float y, float w, float h) = 0;
    virtual void renderLine(float x1, float y1, float x2, float y2) = 0;
    virtual std::string name() const = 0;
};

// ====== Concrete implementations ======

class OpenGLRenderer : public Renderer {
public:
    void renderCircle(float x, float y, float r) override {
        std::cout << "  [OpenGL] glDrawArrays circle at (" << x << "," << y
                  << ") r=" << r << "\n";
    }
    void renderRect(float x, float y, float w, float h) override {
        std::cout << "  [OpenGL] glDrawElements rect at (" << x << "," << y
                  << ") " << w << "x" << h << "\n";
    }
    void renderLine(float x1, float y1, float x2, float y2) override {
        std::cout << "  [OpenGL] glDrawArrays line (" << x1 << "," << y1
                  << ")->(" << x2 << "," << y2 << ")\n";
    }
    std::string name() const override { return "OpenGL"; }
};

class SVGRenderer : public Renderer {
public:
    void renderCircle(float x, float y, float r) override {
        std::cout << "  <circle cx=\"" << x << "\" cy=\"" << y
                  << "\" r=\"" << r << "\"/>\n";
    }
    void renderRect(float x, float y, float w, float h) override {
        std::cout << "  <rect x=\"" << x << "\" y=\"" << y
                  << "\" width=\"" << w << "\" height=\"" << h << "\"/>\n";
    }
    void renderLine(float x1, float y1, float x2, float y2) override {
        std::cout << "  <line x1=\"" << x1 << "\" y1=\"" << y1
                  << "\" x2=\"" << x2 << "\" y2=\"" << y2 << "\"/>\n";
    }
    std::string name() const override { return "SVG"; }
};

// ====== Abstraction ======

class Shape {
public:
    explicit Shape(std::shared_ptr<Renderer> renderer)
        : renderer_(std::move(renderer)) {}
    virtual ~Shape() = default;
    virtual void draw() const = 0;
    virtual void resize(float factor) = 0;

    void setRenderer(std::shared_ptr<Renderer> r) { renderer_ = std::move(r); }

protected:
    std::shared_ptr<Renderer> renderer_;  // bridge to implementation
};

// ====== Refined abstractions ======

class Circle : public Shape {
    float cx_, cy_, radius_;
public:
    Circle(float x, float y, float r, std::shared_ptr<Renderer> renderer)
        : Shape(std::move(renderer)), cx_(x), cy_(y), radius_(r) {}

    void draw() const override {
        renderer_->renderCircle(cx_, cy_, radius_);
    }
    void resize(float factor) override { radius_ *= factor; }
};

class Rectangle : public Shape {
    float x_, y_, w_, h_;
public:
    Rectangle(float x, float y, float w, float h, std::shared_ptr<Renderer> renderer)
        : Shape(std::move(renderer)), x_(x), y_(y), w_(w), h_(h) {}

    void draw() const override {
        renderer_->renderRect(x_, y_, w_, h_);
    }
    void resize(float factor) override { w_ *= factor; h_ *= factor; }
};

class Triangle : public Shape {
    float x1_, y1_, x2_, y2_, x3_, y3_;
public:
    Triangle(float x1, float y1, float x2, float y2, float x3, float y3,
             std::shared_ptr<Renderer> renderer)
        : Shape(std::move(renderer)), x1_(x1), y1_(y1), x2_(x2), y2_(y2),
          x3_(x3), y3_(y3) {}

    void draw() const override {
        renderer_->renderLine(x1_, y1_, x2_, y2_);
        renderer_->renderLine(x2_, y2_, x3_, y3_);
        renderer_->renderLine(x3_, y3_, x1_, y1_);
    }
    void resize(float factor) override {
        // Scale from centroid
        float cx = (x1_ + x2_ + x3_) / 3, cy = (y1_ + y2_ + y3_) / 3;
        auto scale = [&](float& x, float& y) {
            x = cx + (x - cx) * factor;
            y = cy + (y - cy) * factor;
        };
        scale(x1_, y1_); scale(x2_, y2_); scale(x3_, y3_);
    }
};

int main() {
    auto gl  = std::make_shared<OpenGLRenderer>();
    auto svg = std::make_shared<SVGRenderer>();

    // Same shapes, different renderers
    std::vector<std::unique_ptr<Shape>> shapes;
    shapes.push_back(std::make_unique<Circle>(100, 100, 50, gl));
    shapes.push_back(std::make_unique<Rectangle>(10, 20, 200, 100, gl));
    shapes.push_back(std::make_unique<Triangle>(0, 0, 100, 0, 50, 80, gl));

    std::cout << "=== OpenGL rendering ===\n";
    for (const auto& s : shapes) s->draw();

    // Switch all shapes to SVG renderer at runtime
    for (auto& s : shapes) s->setRenderer(svg);

    std::cout << "\n=== SVG rendering (same shapes) ===\n";
    for (const auto& s : shapes) s->draw();

    return 0;
}
```

Without Bridge, you would need `CircleOpenGL`, `CircleSVG`, `RectOpenGL`, `RectSVG`, etc. — N shapes times M renderers = N*M classes. With Bridge, you have N + M classes and can swap renderers at runtime via `setRenderer()`.'''),

    ("cpp_deep/composite_tree", r'''Show me how to implement the Composite pattern in C++ for a tree structure like a file system, where both files and directories are treated uniformly.''', r'''<think>
The Composite pattern lets you treat individual objects and compositions uniformly.
A file system is the canonical example: files and directories share a common interface,
but directories can contain children (which can be files or more directories).

Design decisions for modern C++:
- Base class FileSystemNode with virtual methods: name(), size(), display().
- File is a leaf — has no children.
- Directory is a composite — owns children as vector<unique_ptr<FileSystemNode>>.
- Use the visitor pattern or a simple display(indent) method for traversal.
- Consider whether add/remove should be on the base or only on Directory.
  Classic GoF puts it on the base (transparency), but that's type-unsafe.
  Modern approach: put it only on Directory (safety) and use dynamic_cast if needed.
- Support iteration: begin()/end() on Directory for range-for.
- Show practical operations: total size, find by name, recursive display.
</think>

The Composite pattern treats leaves and composites uniformly. Here is a filesystem tree with files (leaves) and directories (composites) sharing a common interface.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <algorithm>
#include <numeric>
#include <functional>

// ====== Component interface ======

class FileSystemNode {
public:
    explicit FileSystemNode(std::string name) : name_(std::move(name)) {}
    virtual ~FileSystemNode() = default;

    const std::string& name() const { return name_; }
    virtual size_t size() const = 0;
    virtual bool isDirectory() const = 0;
    virtual void display(std::ostream& os, int indent = 0) const = 0;

    // Find all nodes matching a predicate (uniform traversal)
    virtual void find(const std::function<bool(const FileSystemNode&)>& pred,
                      std::vector<const FileSystemNode*>& results) const {
        if (pred(*this)) results.push_back(this);
    }

protected:
    std::string name_;
};

// ====== Leaf: File ======

class File : public FileSystemNode {
    size_t size_;
public:
    File(std::string name, size_t size)
        : FileSystemNode(std::move(name)), size_(size) {}

    size_t size() const override { return size_; }
    bool isDirectory() const override { return false; }

    void display(std::ostream& os, int indent = 0) const override {
        os << std::string(indent, ' ') << name_ << " (" << size_ << " bytes)\n";
    }
};

// ====== Composite: Directory ======

class Directory : public FileSystemNode {
    std::vector<std::unique_ptr<FileSystemNode>> children_;
public:
    explicit Directory(std::string name) : FileSystemNode(std::move(name)) {}

    // Add child (file or subdirectory)
    template <typename T, typename... Args>
    T& add(Args&&... args) {
        auto child = std::make_unique<T>(std::forward<Args>(args)...);
        auto& ref = *child;
        children_.push_back(std::move(child));
        return ref;
    }

    // Convenience: add an existing node
    FileSystemNode& add(std::unique_ptr<FileSystemNode> node) {
        auto& ref = *node;
        children_.push_back(std::move(node));
        return ref;
    }

    // Remove by name
    bool remove(const std::string& name) {
        auto it = std::find_if(children_.begin(), children_.end(),
            [&](const auto& c) { return c->name() == name; });
        if (it != children_.end()) { children_.erase(it); return true; }
        return false;
    }

    // Composite: size is sum of children
    size_t size() const override {
        return std::accumulate(children_.begin(), children_.end(), size_t{0},
            [](size_t sum, const auto& c) { return sum + c->size(); });
    }

    bool isDirectory() const override { return true; }

    void display(std::ostream& os, int indent = 0) const override {
        os << std::string(indent, ' ') << name_ << "/\n";
        for (const auto& child : children_) {
            child->display(os, indent + 2);
        }
    }

    // Recursive find
    void find(const std::function<bool(const FileSystemNode&)>& pred,
              std::vector<const FileSystemNode*>& results) const override {
        if (pred(*this)) results.push_back(this);
        for (const auto& child : children_) {
            child->find(pred, results);
        }
    }

    // Iteration support
    auto begin() const { return children_.begin(); }
    auto end()   const { return children_.end(); }
    size_t childCount() const { return children_.size(); }
};

// ====== Helper: find by extension ======

std::vector<const FileSystemNode*> findByExtension(
    const FileSystemNode& root, const std::string& ext)
{
    std::vector<const FileSystemNode*> results;
    root.find([&](const FileSystemNode& node) {
        if (node.isDirectory()) return false;
        const auto& n = node.name();
        return n.size() >= ext.size() &&
               n.compare(n.size() - ext.size(), ext.size(), ext) == 0;
    }, results);
    return results;
}

int main() {
    // Build a file system tree
    Directory root("project");

    auto& src = root.add<Directory>("src");
    src.add<File>("main.cpp", 2400);
    src.add<File>("utils.cpp", 1800);
    src.add<File>("utils.h", 450);

    auto& build = root.add<Directory>("build");
    build.add<File>("main.o", 48000);
    build.add<File>("utils.o", 32000);
    build.add<File>("app.exe", 256000);

    auto& docs = root.add<Directory>("docs");
    docs.add<File>("README.md", 3200);
    docs.add<File>("API.md", 8500);

    root.add<File>(".gitignore", 120);
    root.add<File>("CMakeLists.txt", 680);

    // Uniform operations on the tree
    std::cout << "=== File System Tree ===\n";
    root.display(std::cout);

    std::cout << "\nTotal size: " << root.size() << " bytes\n";
    std::cout << "src/ size:  " << src.size() << " bytes\n";

    // Find all .cpp files
    std::cout << "\n=== .cpp files ===\n";
    for (auto* node : findByExtension(root, ".cpp")) {
        std::cout << "  " << node->name() << " (" << node->size() << " bytes)\n";
    }

    // Find large files
    std::cout << "\n=== Files > 10KB ===\n";
    std::vector<const FileSystemNode*> large;
    root.find([](const FileSystemNode& n) {
        return !n.isDirectory() && n.size() > 10000;
    }, large);
    for (auto* node : large) {
        std::cout << "  " << node->name() << " (" << node->size() << " bytes)\n";
    }

    return 0;
}
```

The key: `Directory::size()` recursively sums its children, and `display()` recursively prints the tree. Client code calls these on any `FileSystemNode*` without knowing whether it is a file or a directory. The `find()` method demonstrates uniform recursive traversal with a predicate.'''),

    ("cpp_deep/decorator_forwarding", r'''How do I implement the Decorator pattern in C++ with proper forwarding so decorators can be stacked and composed?''', r'''<think>
The Decorator pattern dynamically adds behavior to an object by wrapping it. In C++:

- Base interface (Component) defines the operations.
- ConcreteComponent is the core object.
- Decorator holds a pointer to Component and forwards calls, adding behavior before/after.
- Decorators are stackable: LoggingStream wrapping CompressingStream wrapping FileStream.

Modern C++ considerations:
- Use std::unique_ptr for ownership of the wrapped component.
- Move the wrapped component into the decorator (transfer ownership).
- Decorators should forward all interface methods — missed ones break the chain.
- Consider using CRTP or a forwarding base to reduce boilerplate.
- Can compose decorators with a variadic template helper.

I'll use a data stream example: read/write with logging, compression, encryption decorators.
</think>

The Decorator wraps an object to add behavior while preserving its interface. Decorators stack by each wrapping the previous layer.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <algorithm>
#include <sstream>
#include <vector>

// ====== Component interface ======

class DataStream {
public:
    virtual ~DataStream() = default;
    virtual void write(const std::string& data) = 0;
    virtual std::string read() = 0;
    virtual std::string describe() const = 0;
};

// ====== Concrete component ======

class FileStream : public DataStream {
    std::string buffer_;  // simulates a file
public:
    explicit FileStream(std::string filename) {
        (void)filename;  // in real code, open the file
    }
    void write(const std::string& data) override {
        buffer_ = data;
    }
    std::string read() override {
        return buffer_;
    }
    std::string describe() const override { return "FileStream"; }
};

class MemoryStream : public DataStream {
    std::string buffer_;
public:
    void write(const std::string& data) override { buffer_ = data; }
    std::string read() override { return buffer_; }
    std::string describe() const override { return "MemoryStream"; }
};

// ====== Base Decorator (forwards everything by default) ======

class StreamDecorator : public DataStream {
protected:
    std::unique_ptr<DataStream> wrapped_;
public:
    explicit StreamDecorator(std::unique_ptr<DataStream> stream)
        : wrapped_(std::move(stream)) {}

    void write(const std::string& data) override { wrapped_->write(data); }
    std::string read() override { return wrapped_->read(); }
    std::string describe() const override { return wrapped_->describe(); }
};

// ====== Concrete Decorators ======

class LoggingDecorator : public StreamDecorator {
    std::ostream& log_;
public:
    LoggingDecorator(std::unique_ptr<DataStream> stream, std::ostream& log = std::cout)
        : StreamDecorator(std::move(stream)), log_(log) {}

    void write(const std::string& data) override {
        log_ << "[LOG] Writing " << data.size() << " bytes to " << describe() << "\n";
        StreamDecorator::write(data);
    }
    std::string read() override {
        auto data = StreamDecorator::read();
        log_ << "[LOG] Read " << data.size() << " bytes from " << describe() << "\n";
        return data;
    }
    std::string describe() const override {
        return "Logging(" + StreamDecorator::describe() + ")";
    }
};

class EncryptionDecorator : public StreamDecorator {
    int key_;
    std::string xorTransform(const std::string& data) const {
        std::string result = data;
        for (auto& c : result) c ^= static_cast<char>(key_);
        return result;
    }
public:
    EncryptionDecorator(std::unique_ptr<DataStream> stream, int key = 42)
        : StreamDecorator(std::move(stream)), key_(key) {}

    void write(const std::string& data) override {
        StreamDecorator::write(xorTransform(data));
    }
    std::string read() override {
        return xorTransform(StreamDecorator::read());  // XOR is its own inverse
    }
    std::string describe() const override {
        return "Encrypted(" + StreamDecorator::describe() + ")";
    }
};

class CompressionDecorator : public StreamDecorator {
    // Simple RLE compression for demonstration
    static std::string compress(const std::string& data) {
        std::ostringstream out;
        for (size_t i = 0; i < data.size();) {
            char c = data[i];
            size_t count = 1;
            while (i + count < data.size() && data[i + count] == c && count < 255)
                ++count;
            out << c << static_cast<char>(count);
            i += count;
        }
        return out.str();
    }
    static std::string decompress(const std::string& data) {
        std::string out;
        for (size_t i = 0; i + 1 < data.size(); i += 2) {
            out.append(static_cast<unsigned char>(data[i + 1]), data[i]);
        }
        return out;
    }
public:
    explicit CompressionDecorator(std::unique_ptr<DataStream> stream)
        : StreamDecorator(std::move(stream)) {}

    void write(const std::string& data) override {
        StreamDecorator::write(compress(data));
    }
    std::string read() override {
        return decompress(StreamDecorator::read());
    }
    std::string describe() const override {
        return "Compressed(" + StreamDecorator::describe() + ")";
    }
};

// ====== Composable helper: build a decorator stack ======

template <typename... Decorators>
std::unique_ptr<DataStream> makeStream(std::unique_ptr<DataStream> base) {
    return base;  // base case
}

template <typename First, typename... Rest>
std::unique_ptr<DataStream> makeStream(std::unique_ptr<DataStream> base) {
    return makeStream<Rest...>(std::make_unique<First>(std::move(base)));
}

int main() {
    // Manual stacking: File -> Compress -> Encrypt -> Log
    auto stream = std::make_unique<LoggingDecorator>(
        std::make_unique<EncryptionDecorator>(
            std::make_unique<CompressionDecorator>(
                std::make_unique<FileStream>("data.bin")
            )
        )
    );

    std::cout << "Stream: " << stream->describe() << "\n\n";

    std::string original = "aaaaaabbbbbccccdddddddddd";
    std::cout << "Original:    \"" << original << "\" (" << original.size() << " bytes)\n";

    stream->write(original);
    std::string recovered = stream->read();

    std::cout << "Recovered:   \"" << recovered << "\" (" << recovered.size() << " bytes)\n";
    std::cout << "Round-trip:  " << (original == recovered ? "OK" : "FAIL") << "\n";

    // Using the composable helper
    std::cout << "\n--- Using makeStream helper ---\n";
    auto stream2 = makeStream<CompressionDecorator, EncryptionDecorator, LoggingDecorator>(
        std::make_unique<MemoryStream>()
    );
    stream2->write("Hello, Decorated World!");
    std::cout << "Read back: " << stream2->read() << "\n";

    return 0;
}
```

The `StreamDecorator` base forwards all methods by default so concrete decorators only override what they modify. Decorators stack in any order and each transforms data before/after delegating to the wrapped stream. The `makeStream` variadic template helper provides a clean way to compose decorators without deep nesting.'''),

    ("cpp_deep/flyweight_memory", r'''How do I implement the Flyweight pattern in C++ to minimize memory usage when many objects share common data?''', r'''<think>
The Flyweight pattern shares common state (intrinsic) across many objects, while
keeping unique state (extrinsic) separate. Classic example: text rendering where
character glyphs (font, metrics) are shared but positions are per-instance.

Modern C++ approach:
- Use std::shared_ptr or a pool (unordered_map) to store shared flyweight objects.
- A FlyweightFactory manages the pool and returns existing instances.
- The extrinsic state is passed as parameters to methods, not stored in the flyweight.
- std::unordered_map with string keys for lookup.
- Can use std::string_view for keys if lifetime is managed.

I'll use a particle system example: thousands of particles share texture/mesh data
(flyweight) but have unique position/velocity (extrinsic).

Memory savings: instead of 10,000 copies of a texture object, share one per type.
</think>

The Flyweight shares intrinsic state across many objects, dramatically cutting memory when thousands of instances exist. Here is a particle system example.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
#include <random>
#include <cmath>
#include <cassert>

// ====== Flyweight: shared intrinsic state ======

struct ParticleType {
    std::string name;
    std::string texture_path;    // expensive asset (imagine megabytes)
    float base_size;
    float r, g, b, a;           // color

    size_t memoryEstimate() const {
        // In reality, texture_path would reference a loaded GPU texture
        return sizeof(*this) + texture_path.size() + 4096;  // simulate texture data
    }
};

// ====== Flyweight Factory ======

class ParticleTypeFactory {
    std::unordered_map<std::string, std::shared_ptr<const ParticleType>> pool_;
public:
    std::shared_ptr<const ParticleType> get(
        const std::string& name,
        const std::string& texture,
        float size, float r, float g, float b, float a)
    {
        auto it = pool_.find(name);
        if (it != pool_.end()) return it->second;

        auto type = std::make_shared<const ParticleType>(
            ParticleType{name, texture, size, r, g, b, a});
        pool_[name] = type;
        return type;
    }

    size_t typeCount() const { return pool_.size(); }

    size_t sharedMemory() const {
        size_t total = 0;
        for (const auto& [_, t] : pool_) total += t->memoryEstimate();
        return total;
    }
};

// ====== Context: extrinsic (per-instance) state ======

struct Particle {
    std::shared_ptr<const ParticleType> type;  // shared flyweight
    // Extrinsic state — unique per particle
    float x, y, z;
    float vx, vy, vz;
    float life;          // seconds remaining
    float current_size;  // may differ from base_size

    size_t uniqueMemory() const {
        return sizeof(*this) - sizeof(type);  // exclude the shared_ptr itself
    }

    void update(float dt) {
        x += vx * dt;
        y += vy * dt;
        z += vz * dt;
        vy -= 9.81f * dt;  // gravity
        life -= dt;
        current_size = type->base_size * (life > 0 ? life : 0);
    }

    void render() const {
        if (life <= 0) return;
        // In reality, bind type->texture and draw a billboard
        std::cout << "  [" << type->name << "] pos=("
                  << x << "," << y << "," << z
                  << ") size=" << current_size << "\n";
    }
};

// ====== Particle System ======

class ParticleSystem {
    ParticleTypeFactory factory_;
    std::vector<Particle> particles_;
    std::mt19937 rng_{42};
public:
    void emit(const std::string& typeName, const std::string& texture,
              float size, float r, float g, float b, float a,
              float x, float y, float z, int count)
    {
        auto type = factory_.get(typeName, texture, size, r, g, b, a);
        std::uniform_real_distribution<float> vel(-5.0f, 5.0f);
        std::uniform_real_distribution<float> life(1.0f, 3.0f);

        for (int i = 0; i < count; ++i) {
            particles_.push_back(Particle{
                type, x, y, z,
                vel(rng_), std::abs(vel(rng_)) + 2.0f, vel(rng_),
                life(rng_), size
            });
        }
    }

    void update(float dt) {
        for (auto& p : particles_) p.update(dt);
        // Remove dead particles
        particles_.erase(
            std::remove_if(particles_.begin(), particles_.end(),
                [](const Particle& p) { return p.life <= 0; }),
            particles_.end());
    }

    void printMemoryStats() const {
        size_t shared = factory_.sharedMemory();
        size_t perParticle = particles_.empty() ? 0 : particles_[0].uniqueMemory();
        size_t unique = perParticle * particles_.size();
        size_t withoutFlyweight = particles_.size() *
            (perParticle + (particles_.empty() ? 0 : particles_[0].type->memoryEstimate()));

        std::cout << "=== Memory Stats ===\n"
                  << "Particle count:    " << particles_.size() << "\n"
                  << "Unique types:      " << factory_.typeCount() << "\n"
                  << "Shared memory:     " << shared << " bytes\n"
                  << "Per-instance mem:  " << unique << " bytes\n"
                  << "Total (flyweight): " << (shared + unique) << " bytes\n"
                  << "Total (no flyweight): " << withoutFlyweight << " bytes\n"
                  << "Savings:           "
                  << (withoutFlyweight > 0
                      ? 100.0 * (1.0 - double(shared + unique) / withoutFlyweight)
                      : 0.0)
                  << "%\n";
    }

    size_t count() const { return particles_.size(); }
};

int main() {
    ParticleSystem system;

    // Emit 5000 fire particles — all share one ParticleType
    system.emit("fire", "textures/fire_sprite.png",
                2.0f, 1.0f, 0.5f, 0.0f, 0.8f,
                0, 0, 0, 5000);

    // Emit 3000 smoke particles — share a different ParticleType
    system.emit("smoke", "textures/smoke_sprite.png",
                3.0f, 0.3f, 0.3f, 0.3f, 0.5f,
                0, 5, 0, 3000);

    // Emit 2000 spark particles
    system.emit("spark", "textures/spark_sprite.png",
                0.5f, 1.0f, 1.0f, 0.0f, 1.0f,
                0, 0, 0, 2000);

    std::cout << "10,000 particles using only 3 shared type objects:\n\n";
    system.printMemoryStats();

    // Simulate a few frames
    std::cout << "\nAfter 2 seconds of simulation:\n";
    for (int i = 0; i < 120; ++i) system.update(1.0f / 60.0f);
    std::cout << "Remaining particles: " << system.count() << "\n";

    return 0;
}
```

10,000 particles share only 3 `ParticleType` objects (one per visual style). Without Flyweight, each particle would duplicate the texture reference and metadata — with Flyweight, that data exists exactly once per type, yielding significant memory savings.'''),

    ("cpp_deep/proxy_smart_ref", r'''How do I implement a Proxy pattern in C++ that provides smart reference semantics with transparent logging and access control?''', r'''<think>
The Proxy pattern provides a surrogate for another object to control access.
Modern C++ proxy variants:
- Virtual proxy: lazy initialization
- Protection proxy: access control
- Logging proxy: transparent audit trail
- Smart reference: automatic reference counting, locking, etc.

I'll combine logging + access control in a single proxy that:
- Wraps any service object
- Logs all method calls transparently
- Checks permissions before forwarding
- Uses operator-> overloading for transparent access

Key technique: overload operator-> to return a wrapper that logs entry/exit.
The "call proxy" pattern: operator-> returns a temporary whose destructor fires
after the method call completes.

This is a powerful C++ idiom that doesn't exist in most languages.
</think>

The Proxy controls access to an object. Here is a smart-reference proxy that combines transparent logging, access control, and lazy initialization using `operator->` overloading.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <chrono>
#include <functional>
#include <unordered_set>
#include <mutex>

// ====== Real service interface ======

class Database {
public:
    virtual ~Database() = default;
    virtual std::string query(const std::string& sql) = 0;
    virtual void execute(const std::string& sql) = 0;
    virtual bool isConnected() const = 0;
};

// ====== Real implementation ======

class PostgresDB : public Database {
    std::string connStr_;
    bool connected_ = false;
public:
    explicit PostgresDB(std::string connStr) : connStr_(std::move(connStr)) {
        // Simulate expensive connection
        std::cout << "[PostgresDB] Connecting to " << connStr_ << "...\n";
        connected_ = true;
    }
    ~PostgresDB() { std::cout << "[PostgresDB] Disconnected\n"; }

    std::string query(const std::string& sql) override {
        return "ResultSet{rows=42, sql=\"" + sql + "\"}";
    }
    void execute(const std::string& sql) override {
        std::cout << "[PostgresDB] Executed: " << sql << "\n";
    }
    bool isConnected() const override { return connected_; }
};

// ====== Call Logger: RAII object returned by operator-> ======

template <typename T>
class CallLogger {
    T* obj_;
    std::string context_;
    std::chrono::steady_clock::time_point start_;
public:
    CallLogger(T* obj, std::string ctx)
        : obj_(obj), context_(std::move(ctx))
        , start_(std::chrono::steady_clock::now()) {
        std::cout << "[Proxy] >> " << context_ << " access\n";
    }
    ~CallLogger() {
        auto elapsed = std::chrono::steady_clock::now() - start_;
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(elapsed).count();
        std::cout << "[Proxy] << " << context_ << " (" << us << " us)\n";
    }
    T* operator->() { return obj_; }

    // Non-copyable, non-movable — lives only as a temporary
    CallLogger(const CallLogger&) = delete;
    CallLogger& operator=(const CallLogger&) = delete;
};

// ====== Proxy with logging, access control, lazy init ======

class DatabaseProxy : public Database {
    std::string connStr_;
    mutable std::unique_ptr<PostgresDB> real_;  // lazy
    mutable std::mutex mtx_;

    // Access control
    std::string currentUser_;
    std::unordered_set<std::string> allowedUsers_{"admin", "app_service"};
    std::unordered_set<std::string> readOnlyUsers_{"readonly", "analyst"};

    PostgresDB& getReal() const {
        std::lock_guard lock(mtx_);
        if (!real_) {
            std::cout << "[Proxy] Lazy-initializing connection...\n";
            real_ = std::make_unique<PostgresDB>(connStr_);
        }
        return *real_;
    }

    void checkAccess(const std::string& operation) const {
        if (allowedUsers_.count(currentUser_) == 0 &&
            readOnlyUsers_.count(currentUser_) == 0) {
            throw std::runtime_error("Access denied for user: " + currentUser_);
        }
        if (readOnlyUsers_.count(currentUser_) && operation == "write") {
            throw std::runtime_error("Write access denied for read-only user: " + currentUser_);
        }
    }

public:
    DatabaseProxy(std::string connStr, std::string user)
        : connStr_(std::move(connStr)), currentUser_(std::move(user)) {}

    std::string query(const std::string& sql) override {
        checkAccess("read");
        std::cout << "[Proxy] User '" << currentUser_ << "' querying\n";
        return getReal().query(sql);
    }

    void execute(const std::string& sql) override {
        checkAccess("write");
        std::cout << "[Proxy] User '" << currentUser_ << "' executing\n";
        getReal().execute(sql);
    }

    bool isConnected() const override {
        return real_ && real_->isConnected();
    }

    // Smart reference: operator-> returns a CallLogger temporary
    CallLogger<PostgresDB> operator->() {
        checkAccess("read");
        return CallLogger<PostgresDB>(&getReal(), currentUser_);
    }
};

// ====== Generic smart-reference proxy ======

template <typename T>
class LoggingProxy {
    std::shared_ptr<T> target_;
    std::string label_;
    mutable size_t accessCount_ = 0;
public:
    LoggingProxy(std::shared_ptr<T> target, std::string label)
        : target_(std::move(target)), label_(std::move(label)) {}

    CallLogger<T> operator->() {
        ++accessCount_;
        return CallLogger<T>(target_.get(), label_ + " #" + std::to_string(accessCount_));
    }

    const T& operator*() const { return *target_; }
    size_t accessCount() const { return accessCount_; }
};

int main() {
    // Proxy with access control + lazy init
    std::cout << "=== Admin user ===\n";
    DatabaseProxy adminDb("postgresql://localhost/mydb", "admin");
    std::cout << "Connected? " << adminDb.isConnected() << "\n";  // false (lazy)
    std::cout << adminDb.query("SELECT * FROM users") << "\n";    // triggers connect
    adminDb.execute("INSERT INTO logs VALUES('test')");

    std::cout << "\n=== Read-only user ===\n";
    DatabaseProxy roDb("postgresql://localhost/mydb", "analyst");
    std::cout << roDb.query("SELECT count(*) FROM orders") << "\n";
    try {
        roDb.execute("DROP TABLE users");  // should fail
    } catch (const std::runtime_error& e) {
        std::cout << "Caught: " << e.what() << "\n";
    }

    std::cout << "\n=== Generic logging proxy ===\n";
    auto realDb = std::make_shared<PostgresDB>("postgresql://localhost/test");
    LoggingProxy<PostgresDB> proxy(realDb, "db_proxy");
    proxy->query("SELECT 1");
    proxy->execute("UPDATE stats SET count = count + 1");
    std::cout << "Total accesses: " << proxy.accessCount() << "\n";

    return 0;
}
```

The `CallLogger` trick is the key C++ idiom: `operator->` returns a temporary `CallLogger` object whose constructor logs entry and whose destructor (which fires after the chained method call) logs exit with timing. This makes every method call on the proxy transparently logged without modifying the real object.'''),

    ("cpp_deep/chain_of_responsibility", r'''How do I implement the Chain of Responsibility pattern in modern C++ so that handlers can be composed flexibly?''', r'''<think>
Chain of Responsibility passes a request along a chain of handlers. Each handler
decides whether to process it or pass it to the next handler.

Modern C++ approach:
- Use std::unique_ptr for ownership chaining.
- Or use a vector of handlers (flat chain) instead of linked list.
- std::function-based handlers for maximum flexibility.
- Can use std::optional to indicate whether the request was handled.
- Builder/fluent API for composing the chain.

I'll show both approaches: the classic linked-list chain and a modern flat chain
with lambdas. Use case: HTTP middleware pipeline (authentication, logging, rate
limiting, routing).
</think>

Chain of Responsibility passes requests along a chain until one handles it. Here is both a classic linked-list approach and a modern flat pipeline.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <functional>
#include <optional>
#include <unordered_map>
#include <chrono>

// ====== Request / Response ======

struct HttpRequest {
    std::string method;
    std::string path;
    std::unordered_map<std::string, std::string> headers;
    std::string body;
};

struct HttpResponse {
    int status = 200;
    std::string body;
    std::unordered_map<std::string, std::string> headers;
};

// ====== Classic Chain: linked handlers ======

class Handler {
    std::unique_ptr<Handler> next_;
public:
    virtual ~Handler() = default;

    Handler& setNext(std::unique_ptr<Handler> next) {
        next_ = std::move(next);
        return *next_;  // return reference for chaining
    }

    virtual std::optional<HttpResponse> handle(HttpRequest& req) {
        if (next_) return next_->handle(req);
        return std::nullopt;  // end of chain, unhandled
    }
};

class AuthHandler : public Handler {
    std::string validToken_;
public:
    explicit AuthHandler(std::string token) : validToken_(std::move(token)) {}

    std::optional<HttpResponse> handle(HttpRequest& req) override {
        auto it = req.headers.find("Authorization");
        if (it == req.headers.end() || it->second != "Bearer " + validToken_) {
            std::cout << "[Auth] Rejected: missing/invalid token\n";
            return HttpResponse{401, "Unauthorized"};
        }
        std::cout << "[Auth] Passed\n";
        return Handler::handle(req);  // forward to next
    }
};

class RateLimitHandler : public Handler {
    int maxRequests_;
    int count_ = 0;
public:
    explicit RateLimitHandler(int max) : maxRequests_(max) {}

    std::optional<HttpResponse> handle(HttpRequest& req) override {
        if (++count_ > maxRequests_) {
            std::cout << "[RateLimit] Rejected: limit exceeded\n";
            return HttpResponse{429, "Too Many Requests"};
        }
        std::cout << "[RateLimit] Passed (" << count_ << "/" << maxRequests_ << ")\n";
        return Handler::handle(req);
    }
};

class LoggingHandler : public Handler {
public:
    std::optional<HttpResponse> handle(HttpRequest& req) override {
        std::cout << "[Log] " << req.method << " " << req.path << "\n";
        return Handler::handle(req);
    }
};

class RouteHandler : public Handler {
public:
    std::optional<HttpResponse> handle(HttpRequest& req) override {
        if (req.path == "/api/data") {
            return HttpResponse{200, R"({"data": [1,2,3]})"};
        }
        if (req.path == "/api/health") {
            return HttpResponse{200, "OK"};
        }
        return HttpResponse{404, "Not Found"};
    }
};

// ====== Modern approach: flat middleware pipeline ======

using Middleware = std::function<std::optional<HttpResponse>(HttpRequest&,
    std::function<std::optional<HttpResponse>(HttpRequest&)>)>;

class Pipeline {
    std::vector<Middleware> layers_;
public:
    Pipeline& use(Middleware mw) {
        layers_.push_back(std::move(mw));
        return *this;
    }

    std::optional<HttpResponse> process(HttpRequest& req) const {
        // Build the chain from back to front
        std::function<std::optional<HttpResponse>(HttpRequest&)> chain =
            [](HttpRequest&) -> std::optional<HttpResponse> {
                return HttpResponse{404, "No handler matched"};
            };

        for (auto it = layers_.rbegin(); it != layers_.rend(); ++it) {
            auto& mw = *it;
            chain = [mw, next = std::move(chain)](HttpRequest& r)
                -> std::optional<HttpResponse> {
                return mw(r, next);
            };
        }
        return chain(req);
    }
};

int main() {
    // === Classic linked chain ===
    std::cout << "=== Classic Chain ===\n";
    auto chain = std::make_unique<LoggingHandler>();
    chain->setNext(std::make_unique<AuthHandler>("secret123"))
         .setNext(std::make_unique<RateLimitHandler>(3))
         .setNext(std::make_unique<RouteHandler>());

    HttpRequest req{"GET", "/api/data", {{"Authorization", "Bearer secret123"}}, ""};
    auto resp = chain->handle(req);
    if (resp) std::cout << "Response: " << resp->status << " " << resp->body << "\n\n";

    // No auth header -> rejected at auth
    HttpRequest badReq{"GET", "/api/data", {}, ""};
    resp = chain->handle(badReq);
    if (resp) std::cout << "Response: " << resp->status << " " << resp->body << "\n\n";

    // === Modern flat pipeline ===
    std::cout << "=== Modern Pipeline ===\n";
    Pipeline pipeline;
    pipeline
        .use([](HttpRequest& r, auto next) -> std::optional<HttpResponse> {
            std::cout << "[MW:Log] " << r.method << " " << r.path << "\n";
            auto resp = next(r);
            if (resp) std::cout << "[MW:Log] Response: " << resp->status << "\n";
            return resp;
        })
        .use([](HttpRequest& r, auto next) -> std::optional<HttpResponse> {
            auto it = r.headers.find("Authorization");
            if (it == r.headers.end()) {
                return HttpResponse{401, "Unauthorized"};
            }
            return next(r);
        })
        .use([](HttpRequest& r, auto /*next*/) -> std::optional<HttpResponse> {
            if (r.path == "/api/data")
                return HttpResponse{200, R"({"items": ["a","b","c"]})"};
            return HttpResponse{404, "Not Found"};
        });

    HttpRequest req2{"GET", "/api/data", {{"Authorization", "Bearer token"}}, ""};
    resp = pipeline.process(req2);
    if (resp) std::cout << "Final: " << resp->status << " " << resp->body << "\n";

    return 0;
}
```

Two approaches: the classic linked chain uses virtual dispatch and `unique_ptr` ownership, while the modern pipeline uses `std::function` lambdas composed in a functional style (each middleware receives a `next` callback). The pipeline approach is more flexible since middleware can run code both before and after the next handler.'''),

    ("cpp_deep/command_undo_redo", r'''How do I implement the Command pattern in C++ with full undo/redo support?''', r'''<think>
The Command pattern encapsulates a request as an object, enabling undo/redo.

Design:
- Command interface with execute() and undo().
- ConcreteCommands capture the receiver and parameters.
- CommandHistory manages two stacks: undo and redo.
- Executing a command pushes to undo stack and clears redo stack.
- Undo pops from undo, calls undo(), pushes to redo.
- Redo pops from redo, calls execute(), pushes to undo.

I'll use a text editor example with commands: InsertText, DeleteText, ReplaceText.
Each command stores enough state to undo itself.

Modern C++ features: unique_ptr ownership, std::deque for bounded history,
macro commands (composite command that groups multiple commands).
</think>

The Command pattern encapsulates operations as objects, enabling undo, redo, and macro recording. Here is a text editor with full history.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <deque>
#include <stdexcept>
#include <cassert>

// ====== Receiver ======

class TextDocument {
    std::string text_;
public:
    void insert(size_t pos, const std::string& str) {
        if (pos > text_.size()) throw std::out_of_range("insert position out of range");
        text_.insert(pos, str);
    }
    void erase(size_t pos, size_t len) {
        if (pos + len > text_.size()) throw std::out_of_range("erase range out of bounds");
        text_.erase(pos, len);
    }
    const std::string& text() const { return text_; }
    size_t size() const { return text_.size(); }

    void print() const {
        std::cout << "\"" << text_ << "\" (len=" << text_.size() << ")\n";
    }
};

// ====== Command interface ======

class Command {
public:
    virtual ~Command() = default;
    virtual void execute() = 0;
    virtual void undo() = 0;
    virtual std::string description() const = 0;
};

// ====== Concrete Commands ======

class InsertCommand : public Command {
    TextDocument& doc_;
    size_t pos_;
    std::string text_;
public:
    InsertCommand(TextDocument& doc, size_t pos, std::string text)
        : doc_(doc), pos_(pos), text_(std::move(text)) {}

    void execute() override { doc_.insert(pos_, text_); }
    void undo() override    { doc_.erase(pos_, text_.size()); }
    std::string description() const override {
        return "Insert \"" + text_ + "\" at " + std::to_string(pos_);
    }
};

class DeleteCommand : public Command {
    TextDocument& doc_;
    size_t pos_;
    size_t len_;
    std::string deleted_;  // saved for undo
public:
    DeleteCommand(TextDocument& doc, size_t pos, size_t len)
        : doc_(doc), pos_(pos), len_(len) {}

    void execute() override {
        deleted_ = doc_.text().substr(pos_, len_);
        doc_.erase(pos_, len_);
    }
    void undo() override { doc_.insert(pos_, deleted_); }
    std::string description() const override {
        return "Delete " + std::to_string(len_) + " chars at " + std::to_string(pos_);
    }
};

class ReplaceCommand : public Command {
    TextDocument& doc_;
    size_t pos_;
    size_t len_;
    std::string newText_;
    std::string oldText_;  // saved for undo
public:
    ReplaceCommand(TextDocument& doc, size_t pos, size_t len, std::string newText)
        : doc_(doc), pos_(pos), len_(len), newText_(std::move(newText)) {}

    void execute() override {
        oldText_ = doc_.text().substr(pos_, len_);
        doc_.erase(pos_, len_);
        doc_.insert(pos_, newText_);
    }
    void undo() override {
        doc_.erase(pos_, newText_.size());
        doc_.insert(pos_, oldText_);
    }
    std::string description() const override {
        return "Replace \"" + oldText_ + "\" with \"" + newText_ + "\"";
    }
};

// ====== Macro Command (composite) ======

class MacroCommand : public Command {
    std::string name_;
    std::vector<std::unique_ptr<Command>> commands_;
public:
    explicit MacroCommand(std::string name) : name_(std::move(name)) {}

    void add(std::unique_ptr<Command> cmd) {
        commands_.push_back(std::move(cmd));
    }

    void execute() override {
        for (auto& cmd : commands_) cmd->execute();
    }
    void undo() override {
        // Undo in reverse order
        for (auto it = commands_.rbegin(); it != commands_.rend(); ++it) {
            (*it)->undo();
        }
    }
    std::string description() const override {
        return "Macro[" + name_ + "] (" + std::to_string(commands_.size()) + " commands)";
    }
};

// ====== Command History (undo/redo manager) ======

class CommandHistory {
    std::deque<std::unique_ptr<Command>> undoStack_;
    std::deque<std::unique_ptr<Command>> redoStack_;
    size_t maxHistory_;
public:
    explicit CommandHistory(size_t maxHistory = 100) : maxHistory_(maxHistory) {}

    void execute(std::unique_ptr<Command> cmd) {
        cmd->execute();
        std::cout << "  Execute: " << cmd->description() << "\n";
        undoStack_.push_back(std::move(cmd));
        redoStack_.clear();  // new action invalidates redo history

        // Bound history size
        if (undoStack_.size() > maxHistory_) undoStack_.pop_front();
    }

    bool undo() {
        if (undoStack_.empty()) return false;
        auto cmd = std::move(undoStack_.back());
        undoStack_.pop_back();
        cmd->undo();
        std::cout << "  Undo: " << cmd->description() << "\n";
        redoStack_.push_back(std::move(cmd));
        return true;
    }

    bool redo() {
        if (redoStack_.empty()) return false;
        auto cmd = std::move(redoStack_.back());
        redoStack_.pop_back();
        cmd->execute();
        std::cout << "  Redo: " << cmd->description() << "\n";
        undoStack_.push_back(std::move(cmd));
        return true;
    }

    size_t undoCount() const { return undoStack_.size(); }
    size_t redoCount() const { return redoStack_.size(); }
};

int main() {
    TextDocument doc;
    CommandHistory history;

    std::cout << "=== Building document ===\n";
    history.execute(std::make_unique<InsertCommand>(doc, 0, "Hello World"));
    doc.print();

    history.execute(std::make_unique<InsertCommand>(doc, 5, ","));
    doc.print();

    history.execute(std::make_unique<InsertCommand>(doc, doc.size(), "!"));
    doc.print();

    history.execute(std::make_unique<ReplaceCommand>(doc, 7, 5, "C++"));
    doc.print();

    std::cout << "\n=== Undo x2 ===\n";
    history.undo(); doc.print();
    history.undo(); doc.print();

    std::cout << "\n=== Redo x1 ===\n";
    history.redo(); doc.print();

    std::cout << "\n=== Macro command ===\n";
    auto macro = std::make_unique<MacroCommand>("format_greeting");
    macro->add(std::make_unique<DeleteCommand>(doc, 0, doc.size()));
    macro->add(std::make_unique<InsertCommand>(doc, 0, "Greetings, Modern C++!"));
    history.execute(std::move(macro));
    doc.print();

    std::cout << "\n=== Undo macro (undoes all sub-commands at once) ===\n";
    history.undo(); doc.print();

    std::cout << "\nHistory: " << history.undoCount() << " undo, "
              << history.redoCount() << " redo\n";

    return 0;
}
```

Each command stores enough state to reverse itself. `MacroCommand` groups multiple commands and undoes them in reverse order. `CommandHistory` uses a deque for bounded history and clears the redo stack on any new action (standard editor behavior).'''),

    ("cpp_deep/mediator_decoupled", r'''How do I implement the Mediator pattern in C++ to decouple components that need to communicate?''', r'''<think>
The Mediator centralizes communication between components so they don't reference
each other directly. Instead of N*(N-1) direct connections, you have N connections
to one mediator.

Modern C++ approach:
- Components hold a reference/pointer to the mediator.
- Mediator knows all components and routes messages.
- Can use std::any or std::variant for type-safe event payloads.
- Can use templates for compile-time type safety.

Practical example: a UI dialog where changing one control affects others
(checkbox enables/disables text field, dropdown changes label, etc.).
</think>

The Mediator centralizes communication so components interact through it instead of referencing each other directly. Here is a UI dialog example.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <any>
#include <unordered_map>
#include <functional>

// Forward declaration
class Mediator;

// ====== Component base ======

class UIComponent {
protected:
    Mediator* mediator_ = nullptr;
    std::string name_;
    bool enabled_ = true;
public:
    explicit UIComponent(std::string name) : name_(std::move(name)) {}
    virtual ~UIComponent() = default;

    void setMediator(Mediator* m) { mediator_ = m; }
    const std::string& name() const { return name_; }
    bool isEnabled() const { return enabled_; }
    void setEnabled(bool e) {
        enabled_ = e;
        std::cout << "  [" << name_ << "] " << (e ? "enabled" : "disabled") << "\n";
    }
};

// ====== Mediator interface ======

class Mediator {
public:
    virtual ~Mediator() = default;
    virtual void notify(UIComponent* sender, const std::string& event,
                        const std::any& data = {}) = 0;
};

// ====== Concrete Components ======

class CheckBox : public UIComponent {
    bool checked_ = false;
public:
    using UIComponent::UIComponent;
    bool isChecked() const { return checked_; }

    void toggle() {
        checked_ = !checked_;
        std::cout << "  [" << name_ << "] toggled to " << (checked_ ? "ON" : "OFF") << "\n";
        if (mediator_) mediator_->notify(this, "toggled", checked_);
    }
};

class TextInput : public UIComponent {
    std::string text_;
public:
    using UIComponent::UIComponent;
    const std::string& text() const { return text_; }

    void setText(const std::string& t) {
        if (!enabled_) { std::cout << "  [" << name_ << "] disabled, ignoring input\n"; return; }
        text_ = t;
        std::cout << "  [" << name_ << "] text = \"" << t << "\"\n";
        if (mediator_) mediator_->notify(this, "changed", text_);
    }
};

class DropDown : public UIComponent {
    std::vector<std::string> options_;
    int selected_ = -1;
public:
    DropDown(std::string name, std::vector<std::string> opts)
        : UIComponent(std::move(name)), options_(std::move(opts)) {}

    void select(int idx) {
        if (idx < 0 || idx >= static_cast<int>(options_.size())) return;
        selected_ = idx;
        std::cout << "  [" << name_ << "] selected: " << options_[idx] << "\n";
        if (mediator_) mediator_->notify(this, "selected", options_[idx]);
    }
    std::string selectedValue() const {
        return selected_ >= 0 ? options_[selected_] : "";
    }
};

class Label : public UIComponent {
    std::string text_;
public:
    using UIComponent::UIComponent;

    void setText(const std::string& t) {
        text_ = t;
        std::cout << "  [" << name_ << "] label = \"" << t << "\"\n";
    }
    const std::string& text() const { return text_; }
};

class Button : public UIComponent {
public:
    using UIComponent::UIComponent;
    void click() {
        if (!enabled_) { std::cout << "  [" << name_ << "] disabled\n"; return; }
        std::cout << "  [" << name_ << "] clicked\n";
        if (mediator_) mediator_->notify(this, "clicked");
    }
};

// ====== Concrete Mediator: Login Dialog ======

class LoginDialog : public Mediator {
    CheckBox rememberMe_;
    TextInput username_;
    TextInput password_;
    DropDown  authType_;
    Label     statusLabel_;
    Button    loginBtn_;

public:
    LoginDialog()
        : rememberMe_("RememberMe")
        , username_("Username")
        , password_("Password")
        , authType_("AuthType", {"Password", "OAuth", "SSO"})
        , statusLabel_("Status")
        , loginBtn_("LoginBtn")
    {
        // Register mediator with all components
        rememberMe_.setMediator(this);
        username_.setMediator(this);
        password_.setMediator(this);
        authType_.setMediator(this);
        statusLabel_.setMediator(this);
        loginBtn_.setMediator(this);

        statusLabel_.setText("Enter credentials");
        loginBtn_.setEnabled(false);
    }

    // Central coordination logic — components don't know about each other
    void notify(UIComponent* sender, const std::string& event,
                const std::any& data) override
    {
        if (sender == &authType_ && event == "selected") {
            auto method = std::any_cast<std::string>(data);
            if (method == "Password") {
                password_.setEnabled(true);
                statusLabel_.setText("Enter username and password");
            } else {
                password_.setEnabled(false);
                statusLabel_.setText("Using " + method + " — password not needed");
            }
        }
        else if (sender == &username_ && event == "changed") {
            auto text = std::any_cast<std::string>(data);
            loginBtn_.setEnabled(!text.empty());
        }
        else if (sender == &loginBtn_ && event == "clicked") {
            statusLabel_.setText("Logging in as " + username_.text() + "...");
        }
        else if (sender == &rememberMe_ && event == "toggled") {
            auto checked = std::any_cast<bool>(data);
            statusLabel_.setText(checked ? "Credentials will be saved" : "Session only");
        }
    }

    // Expose components for simulation
    void simulate() {
        std::cout << "=== User interaction simulation ===\n\n";

        std::cout << "1. Select auth type:\n";
        authType_.select(0);  // Password

        std::cout << "\n2. Type username:\n";
        username_.setText("admin");

        std::cout << "\n3. Type password:\n";
        password_.setText("secret");

        std::cout << "\n4. Toggle remember me:\n";
        rememberMe_.toggle();

        std::cout << "\n5. Click login:\n";
        loginBtn_.click();

        std::cout << "\n6. Switch to OAuth:\n";
        authType_.select(1);  // OAuth

        std::cout << "\n7. Try typing password (should be disabled):\n";
        password_.setText("nope");
    }
};

int main() {
    LoginDialog dialog;
    dialog.simulate();
    return 0;
}
```

Without a mediator, each component would need references to every other component it affects — `CheckBox` would know about `TextInput`, `Label`, `Button`, etc. The mediator centralizes all coordination logic in one place, so components only know about the mediator interface.'''),

    ("cpp_deep/memento_state_snapshot", r'''How do I implement the Memento pattern in C++ to save and restore object state without exposing internal details?''', r'''<think>
The Memento pattern captures an object's internal state so it can be restored later,
without violating encapsulation. In C++:

- Originator: the object whose state we save.
- Memento: opaque snapshot of the originator's state.
- Caretaker: manages mementos (stores history).

Key encapsulation challenge: the memento needs access to the originator's private
state, but the caretaker should not. Solutions:
1. Make Memento a nested class with private members, friend the Originator.
2. Use an opaque handle (type-erased memento).

I'll use approach 1 (nested class) since it's cleanest in C++.
Example: a game character with HP, position, inventory — save/restore game state.
</think>

The Memento saves and restores state without exposing internals. The key is making the memento's contents accessible only to the originator.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <deque>
#include <chrono>
#include <ctime>
#include <sstream>
#include <iomanip>

// ====== Originator: Game Character ======

class GameCharacter {
public:
    // Memento as nested class — only GameCharacter can read its internals
    class Memento {
        friend class GameCharacter;  // only originator can access
        int hp_, maxHp_, x_, y_, level_;
        std::vector<std::string> inventory_;
        std::string timestamp_;

        Memento(int hp, int maxHp, int x, int y, int lvl,
                std::vector<std::string> inv, std::string ts)
            : hp_(hp), maxHp_(maxHp), x_(x), y_(y), level_(lvl)
            , inventory_(std::move(inv)), timestamp_(std::move(ts)) {}
    public:
        // Caretaker can only see metadata, not the actual state
        const std::string& timestamp() const { return timestamp_; }
        std::string summary() const {
            return "Save@" + timestamp_ + " (HP:" + std::to_string(hp_) +
                   "/" + std::to_string(maxHp_) + " Lv:" + std::to_string(level_) + ")";
        }
    };

    GameCharacter(std::string name, int hp, int x, int y)
        : name_(std::move(name)), hp_(hp), maxHp_(hp), x_(x), y_(y) {}

    // Create a memento (save state)
    std::unique_ptr<Memento> save() const {
        auto now = std::chrono::system_clock::now();
        auto time = std::chrono::system_clock::to_time_t(now);
        std::ostringstream ts;
        ts << std::put_time(std::localtime(&time), "%H:%M:%S");

        return std::unique_ptr<Memento>(new Memento(
            hp_, maxHp_, x_, y_, level_, inventory_, ts.str()));
    }

    // Restore from a memento
    void restore(const Memento& memento) {
        hp_ = memento.hp_;
        maxHp_ = memento.maxHp_;
        x_ = memento.x_;
        y_ = memento.y_;
        level_ = memento.level_;
        inventory_ = memento.inventory_;
        std::cout << "[Restored to " << memento.timestamp() << "]\n";
    }

    // Game actions that modify state
    void move(int dx, int dy) {
        x_ += dx; y_ += dy;
        std::cout << name_ << " moved to (" << x_ << "," << y_ << ")\n";
    }

    void takeDamage(int dmg) {
        hp_ = std::max(0, hp_ - dmg);
        std::cout << name_ << " took " << dmg << " damage (HP: " << hp_ << "/" << maxHp_ << ")\n";
    }

    void heal(int amount) {
        hp_ = std::min(maxHp_, hp_ + amount);
        std::cout << name_ << " healed (HP: " << hp_ << "/" << maxHp_ << ")\n";
    }

    void addItem(const std::string& item) {
        inventory_.push_back(item);
        std::cout << name_ << " got [" << item << "]\n";
    }

    void levelUp() {
        ++level_;
        maxHp_ += 10;
        hp_ = maxHp_;
        std::cout << name_ << " reached level " << level_ << "! (HP: " << hp_ << ")\n";
    }

    void printStatus() const {
        std::cout << "--- " << name_ << " ---\n"
                  << "  HP: " << hp_ << "/" << maxHp_
                  << "  Pos: (" << x_ << "," << y_ << ")"
                  << "  Level: " << level_ << "\n"
                  << "  Inventory: [";
        for (size_t i = 0; i < inventory_.size(); ++i) {
            if (i) std::cout << ", ";
            std::cout << inventory_[i];
        }
        std::cout << "]\n";
    }

private:
    std::string name_;
    int hp_, maxHp_;
    int x_ = 0, y_ = 0;
    int level_ = 1;
    std::vector<std::string> inventory_;
};

// ====== Caretaker: Save Manager ======

class SaveManager {
    std::deque<std::unique_ptr<GameCharacter::Memento>> saves_;
    size_t maxSaves_;
public:
    explicit SaveManager(size_t maxSaves = 10) : maxSaves_(maxSaves) {}

    void quickSave(const GameCharacter& character) {
        saves_.push_back(character.save());
        if (saves_.size() > maxSaves_) saves_.pop_front();
        std::cout << "[Saved: " << saves_.back()->summary() << "]\n";
    }

    bool quickLoad(GameCharacter& character) {
        if (saves_.empty()) {
            std::cout << "[No saves available]\n";
            return false;
        }
        character.restore(*saves_.back());
        saves_.pop_back();
        return true;
    }

    void listSaves() const {
        std::cout << "=== Save Slots (" << saves_.size() << ") ===\n";
        for (size_t i = 0; i < saves_.size(); ++i) {
            std::cout << "  [" << i << "] " << saves_[i]->summary() << "\n";
        }
    }

    bool loadSlot(GameCharacter& character, size_t slot) {
        if (slot >= saves_.size()) return false;
        character.restore(*saves_[slot]);
        return true;
    }
};

int main() {
    GameCharacter hero("Knight", 100, 0, 0);
    SaveManager saves(5);

    hero.printStatus();

    // Play through some encounters
    std::cout << "\n--- Exploring ---\n";
    hero.move(10, 5);
    hero.addItem("Iron Sword");
    saves.quickSave(hero);  // Save point 1

    hero.move(20, 10);
    hero.takeDamage(30);
    hero.addItem("Health Potion");
    saves.quickSave(hero);  // Save point 2

    hero.levelUp();
    hero.move(30, 15);
    saves.quickSave(hero);  // Save point 3

    std::cout << "\n--- Boss fight goes badly ---\n";
    hero.takeDamage(80);
    hero.takeDamage(50);
    hero.printStatus();

    std::cout << "\n--- Quick load! ---\n";
    saves.listSaves();
    saves.quickLoad(hero);
    hero.printStatus();

    std::cout << "\n--- Load earlier save ---\n";
    saves.loadSlot(hero, 0);
    hero.printStatus();

    return 0;
}
```

The `Memento` is a nested class with all members private and `GameCharacter` as a friend. The `SaveManager` (caretaker) can store and list mementos but cannot read or modify their internal state — only `GameCharacter::restore()` can do that. This preserves encapsulation while enabling full state snapshots.'''),

    ("cpp_deep/observer_weak_ptr", r'''How do I implement the Observer pattern in C++ using weak_ptr to prevent dangling pointers when observers are destroyed?''', r'''<think>
The classic Observer pattern has a lifetime problem: if an observer is destroyed
without unsubscribing, the subject holds a dangling pointer. Solutions:
1. Manual unsubscribe in observer destructor (error-prone).
2. Use std::weak_ptr — the subject stores weak_ptr and automatically detects
   when observers are gone.

Design:
- Subject stores vector<weak_ptr<Observer>>.
- On notify, iterate and try to lock() each weak_ptr.
- Expired ones are cleaned up automatically.
- Observers are managed via shared_ptr by their owners.
- Can also provide a subscription handle (RAII unsubscribe).

I'll show both the weak_ptr approach and a type-safe signal/slot variant with
automatic cleanup.
</think>

Using `weak_ptr` solves the dangling observer problem: the subject automatically detects when observers have been destroyed.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <functional>
#include <algorithm>

// ====== Observer interface ======

class StockObserver {
public:
    virtual ~StockObserver() = default;
    virtual void onPriceChanged(const std::string& symbol, double price) = 0;
};

// ====== Subject with weak_ptr observers ======

class StockExchange {
    struct Subscription {
        std::weak_ptr<StockObserver> observer;
        std::string symbol;  // filter: "" means all symbols
    };

    std::vector<Subscription> subs_;

    void cleanup() {
        // Remove expired observers
        subs_.erase(
            std::remove_if(subs_.begin(), subs_.end(),
                [](const Subscription& s) { return s.observer.expired(); }),
            subs_.end());
    }

public:
    // Subscribe with automatic lifetime management
    void subscribe(std::shared_ptr<StockObserver> obs, const std::string& symbol = "") {
        subs_.push_back({obs, symbol});
    }

    void updatePrice(const std::string& symbol, double price) {
        std::cout << "\n[Exchange] " << symbol << " -> $" << price << "\n";

        bool needsCleanup = false;
        for (auto& sub : subs_) {
            if (auto obs = sub.observer.lock()) {
                // Notify if subscribed to this symbol or to all
                if (sub.symbol.empty() || sub.symbol == symbol) {
                    obs->onPriceChanged(symbol, price);
                }
            } else {
                needsCleanup = true;  // observer was destroyed
            }
        }
        if (needsCleanup) cleanup();
    }

    size_t subscriberCount() const {
        size_t count = 0;
        for (const auto& s : subs_) {
            if (!s.observer.expired()) ++count;
        }
        return count;
    }
};

// ====== Concrete Observers ======

class PriceDisplay : public StockObserver {
    std::string name_;
public:
    explicit PriceDisplay(std::string name) : name_(std::move(name)) {
        std::cout << "  [" << name_ << "] created\n";
    }
    ~PriceDisplay() override {
        std::cout << "  [" << name_ << "] destroyed\n";
    }
    void onPriceChanged(const std::string& symbol, double price) override {
        std::cout << "  [" << name_ << "] " << symbol << " = $" << price << "\n";
    }
};

class PriceAlert : public StockObserver {
    std::string symbol_;
    double threshold_;
    std::string name_;
public:
    PriceAlert(std::string name, std::string sym, double threshold)
        : symbol_(std::move(sym)), threshold_(threshold), name_(std::move(name)) {
        std::cout << "  [" << name_ << "] alert created for " << symbol_
                  << " > $" << threshold_ << "\n";
    }
    ~PriceAlert() override {
        std::cout << "  [" << name_ << "] alert destroyed\n";
    }
    void onPriceChanged(const std::string& symbol, double price) override {
        if (symbol == symbol_ && price > threshold_) {
            std::cout << "  [" << name_ << "] ALERT! " << symbol
                      << " exceeded $" << threshold_ << " (now $" << price << ")\n";
        }
    }
};

// ====== RAII subscription handle (alternative approach) ======

class Signal {
    struct Slot {
        std::function<void(const std::string&, double)> callback;
        std::weak_ptr<void> guard;  // if this expires, slot is dead
    };
    std::vector<Slot> slots_;
public:
    // Returns a shared_ptr<void> that acts as a subscription lifetime guard
    [[nodiscard]] std::shared_ptr<void> connect(
        std::function<void(const std::string&, double)> fn)
    {
        auto guard = std::make_shared<int>(0);  // dummy shared_ptr
        slots_.push_back({std::move(fn), guard});
        return guard;
    }

    void emit(const std::string& symbol, double price) {
        bool dirty = false;
        for (auto& slot : slots_) {
            if (slot.guard.lock()) {
                slot.callback(symbol, price);
            } else {
                dirty = true;
            }
        }
        if (dirty) {
            slots_.erase(
                std::remove_if(slots_.begin(), slots_.end(),
                    [](const Slot& s) { return s.guard.expired(); }),
                slots_.end());
        }
    }
};

int main() {
    StockExchange exchange;

    // Create observers with shared_ptr
    auto display1 = std::make_shared<PriceDisplay>("MainBoard");
    auto display2 = std::make_shared<PriceDisplay>("TradingDesk");
    auto alert    = std::make_shared<PriceAlert>("Alert1", "AAPL", 180.0);

    exchange.subscribe(display1);           // all symbols
    exchange.subscribe(display2, "AAPL");   // only AAPL
    exchange.subscribe(alert, "AAPL");      // only AAPL

    std::cout << "\nSubscribers: " << exchange.subscriberCount() << "\n";

    exchange.updatePrice("AAPL", 175.50);
    exchange.updatePrice("GOOGL", 140.00);
    exchange.updatePrice("AAPL", 182.30);

    // Destroy one observer — no manual unsubscribe needed!
    std::cout << "\n--- Destroying TradingDesk ---\n";
    display2.reset();  // shared_ptr releases, weak_ptr expires

    exchange.updatePrice("AAPL", 185.00);
    std::cout << "Subscribers after destruction: " << exchange.subscriberCount() << "\n";

    // Destroy alert
    std::cout << "\n--- Destroying Alert1 ---\n";
    alert.reset();
    exchange.updatePrice("AAPL", 190.00);
    std::cout << "Subscribers: " << exchange.subscriberCount() << "\n";

    // === RAII Signal approach ===
    std::cout << "\n=== Signal/Slot with RAII guard ===\n";
    Signal sig;
    {
        auto sub1 = sig.connect([](auto& sym, auto p) {
            std::cout << "  Listener1: " << sym << " = $" << p << "\n";
        });
        auto sub2 = sig.connect([](auto& sym, auto p) {
            std::cout << "  Listener2: " << sym << " = $" << p << "\n";
        });

        sig.emit("MSFT", 350.0);

        // sub2 goes out of scope here
        std::cout << "--- sub2 goes out of scope ---\n";
    }
    // Both subs out of scope
    sig.emit("MSFT", 355.0);  // no listeners fire
    std::cout << "(no output expected above)\n";

    return 0;
}
```

Two approaches shown: (1) `weak_ptr<Observer>` — the subject stores weak pointers and cleans up expired ones during notification. (2) `Signal` with RAII guards — `connect()` returns a `shared_ptr<void>` that acts as a subscription lifetime token; when it is destroyed, the slot auto-expires. Both eliminate the dangling observer problem without requiring manual unsubscribe.'''),

    ("cpp_deep/state_variant_machine", r'''How do I implement the State pattern using std::variant in C++ for a type-safe state machine?''', r'''<think>
Using std::variant for state machines gives us:
- Exhaustive pattern matching via std::visit (compiler warns on unhandled states).
- Value semantics (no heap allocation for states).
- Type safety — invalid state transitions are compile errors if designed well.

Approach:
- Each state is a struct holding state-specific data.
- The state machine holds a std::variant of all state types.
- Events are also structs, and transitions are handled by std::visit with
  overloaded lambdas or a visitor.
- The "overloaded" pattern (inheriting from multiple lambdas) is key.

I'll implement a TCP connection state machine: Closed -> SynSent -> Established ->
FinWait -> Closed, with events like Connect, SynAck, Data, Close.
</think>

Using `std::variant` for the State pattern gives exhaustive matching, value semantics, and zero heap allocation. The compiler enforces that all state/event combinations are handled.

```cpp
#include <iostream>
#include <variant>
#include <string>
#include <optional>
#include <queue>
#include <cassert>

// ====== Overloaded visitor helper ======

template <typename... Ts>
struct overloaded : Ts... { using Ts::operator()...; };
template <typename... Ts>
overloaded(Ts...) -> overloaded<Ts...>;

// ====== States (each can hold state-specific data) ======

struct Closed {};
struct Listening { int port; };
struct SynSent { std::string remoteAddr; };
struct Established {
    std::string remoteAddr;
    size_t bytesTransferred = 0;
};
struct FinWait { std::string reason; };

using TcpState = std::variant<Closed, Listening, SynSent, Established, FinWait>;

// ====== Events ======

struct Listen { int port; };
struct Connect { std::string addr; };
struct SynAck {};
struct Data { std::string payload; };
struct Close { std::string reason = "normal"; };
struct Timeout {};
struct Reset {};

using TcpEvent = std::variant<Listen, Connect, SynAck, Data, Close, Timeout, Reset>;

// ====== State machine ======

class TcpConnection {
    TcpState state_ = Closed{};

    // Transition table: (State, Event) -> new State
    // Returns nullopt if the transition is invalid
    std::optional<TcpState> transition(const TcpState& state, const TcpEvent& event) {
        return std::visit(overloaded{
            // From Closed
            [](const Closed&, const Listen& e) -> std::optional<TcpState> {
                std::cout << "  Listening on port " << e.port << "\n";
                return Listening{e.port};
            },
            [](const Closed&, const Connect& e) -> std::optional<TcpState> {
                std::cout << "  Sending SYN to " << e.addr << "\n";
                return SynSent{e.addr};
            },

            // From Listening
            [](const Listening&, const SynAck&) -> std::optional<TcpState> {
                std::cout << "  Accepted incoming connection\n";
                return Established{"client", 0};
            },
            [](const Listening&, const Close&) -> std::optional<TcpState> {
                std::cout << "  Stopped listening\n";
                return Closed{};
            },

            // From SynSent
            [](const SynSent& s, const SynAck&) -> std::optional<TcpState> {
                std::cout << "  Connection established with " << s.remoteAddr << "\n";
                return Established{s.remoteAddr, 0};
            },
            [](const SynSent&, const Timeout&) -> std::optional<TcpState> {
                std::cout << "  Connection timed out\n";
                return Closed{};
            },

            // From Established
            [](Established s, const Data& d) -> std::optional<TcpState> {
                s.bytesTransferred += d.payload.size();
                std::cout << "  Received " << d.payload.size()
                          << " bytes (total: " << s.bytesTransferred << ")\n";
                return s;
            },
            [](const Established& s, const Close& c) -> std::optional<TcpState> {
                std::cout << "  Closing connection to " << s.remoteAddr
                          << " (" << c.reason << ")\n";
                return FinWait{c.reason};
            },
            [](const Established&, const Reset&) -> std::optional<TcpState> {
                std::cout << "  Connection reset!\n";
                return Closed{};
            },

            // From FinWait
            [](const FinWait&, const SynAck&) -> std::optional<TcpState> {
                std::cout << "  FIN acknowledged, connection closed\n";
                return Closed{};
            },
            [](const FinWait&, const Timeout&) -> std::optional<TcpState> {
                std::cout << "  FIN timeout, force closed\n";
                return Closed{};
            },

            // Default: invalid transition
            [](const auto& s, const auto&) -> std::optional<TcpState> {
                return std::nullopt;
            }
        }, state, event);
    }

public:
    bool processEvent(const TcpEvent& event) {
        auto result = transition(state_, event);
        if (result) {
            state_ = *result;
            return true;
        }
        std::cout << "  [Invalid transition in state: " << stateName() << "]\n";
        return false;
    }

    std::string stateName() const {
        return std::visit(overloaded{
            [](const Closed&)      { return std::string("CLOSED"); },
            [](const Listening& s) { return std::string("LISTENING:") + std::to_string(s.port); },
            [](const SynSent& s)   { return std::string("SYN_SENT->") + s.remoteAddr; },
            [](const Established& s) {
                return std::string("ESTABLISHED(") + s.remoteAddr +
                       ", " + std::to_string(s.bytesTransferred) + "B)";
            },
            [](const FinWait& s) { return std::string("FIN_WAIT(") + s.reason + ")"; },
        }, state_);
    }

    // Type-safe state query
    template <typename S>
    bool isInState() const { return std::holds_alternative<S>(state_); }

    template <typename S>
    const S* getState() const { return std::get_if<S>(&state_); }
};

int main() {
    TcpConnection conn;
    std::cout << "State: " << conn.stateName() << "\n\n";

    // Normal connection lifecycle
    std::cout << "--- Connect ---\n";
    conn.processEvent(Connect{"192.168.1.100"});
    std::cout << "State: " << conn.stateName() << "\n\n";

    std::cout << "--- SynAck ---\n";
    conn.processEvent(SynAck{});
    std::cout << "State: " << conn.stateName() << "\n\n";

    std::cout << "--- Transfer data ---\n";
    conn.processEvent(Data{"Hello, server!"});
    conn.processEvent(Data{"More data here, this is a longer payload."});
    std::cout << "State: " << conn.stateName() << "\n\n";

    std::cout << "--- Invalid: Listen while established ---\n";
    conn.processEvent(Listen{8080});
    std::cout << "\n";

    std::cout << "--- Close ---\n";
    conn.processEvent(Close{"done"});
    std::cout << "State: " << conn.stateName() << "\n\n";

    std::cout << "--- FIN ack ---\n";
    conn.processEvent(SynAck{});
    std::cout << "State: " << conn.stateName() << "\n\n";

    // Type-safe state query
    assert(conn.isInState<Closed>());
    std::cout << "Connection is closed: " << conn.isInState<Closed>() << "\n";

    return 0;
}
```

The `std::visit` with `overloaded` lambdas acts as a transition table: each lambda handles a specific (State, Event) pair. The catch-all `(auto&, auto&)` handles invalid transitions. The compiler warns if you add a new state or event without handling all combinations. States hold their own data (e.g., `Established` tracks `bytesTransferred`), and everything lives on the stack — no heap allocation for state objects.'''),

    ("cpp_deep/template_method_nvi", r'''Show me the Template Method pattern using Non-Virtual Interface (NVI) idiom in C++. Why is NVI preferred?''', r'''<think>
The Template Method pattern defines the skeleton of an algorithm in a base class,
with subclasses overriding specific steps. The NVI (Non-Virtual Interface) idiom
enhances this by making public methods non-virtual and virtual methods private.

Why NVI is preferred:
1. Separates the interface (what clients call) from the customization points (what subclasses override).
2. The base class can add pre/post conditions, logging, locking around the virtual call.
3. Prevents derived classes from forgetting to call base class logic.
4. The public interface is stable — adding cross-cutting concerns doesn't break derived classes.

Herb Sutter advocated this strongly in his "Virtuality" article.

I'll show a data processing pipeline: read, validate, transform, write — with
NVI separating the public API from the customization hooks.
</think>

NVI (Non-Virtual Interface) makes the Template Method pattern safer: public methods are non-virtual (control the algorithm skeleton), while private virtual methods are the customization hooks.

```cpp
#include <iostream>
#include <string>
#include <vector>
#include <chrono>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <algorithm>

// ====== Base class with NVI Template Method ======

class DataProcessor {
public:
    virtual ~DataProcessor() = default;

    // Public non-virtual interface — clients call this
    // The base class controls the algorithm skeleton and cross-cutting concerns
    void process(const std::string& source) {
        auto start = std::chrono::steady_clock::now();
        std::cout << "[" << name() << "] Starting processing of: " << source << "\n";

        // Step 1: Read
        auto data = doRead(source);
        std::cout << "  Read " << data.size() << " records\n";
        if (data.empty()) {
            std::cout << "  No data to process.\n";
            return;
        }

        // Step 2: Validate (hook can reject records)
        auto valid = doValidate(data);
        std::cout << "  " << valid.size() << "/" << data.size() << " records valid\n";

        // Step 3: Transform
        auto transformed = doTransform(valid);
        std::cout << "  Transformed " << transformed.size() << " records\n";

        // Step 4: Write
        doWrite(transformed);

        // Step 5: Optional hook for cleanup
        doCleanup();

        auto elapsed = std::chrono::steady_clock::now() - start;
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count();
        std::cout << "[" << name() << "] Complete in " << ms << "ms\n\n";
    }

protected:
    // Pure virtual — must be implemented
    virtual std::string name() const = 0;
    virtual std::vector<std::string> doRead(const std::string& source) = 0;
    virtual std::vector<std::string> doTransform(const std::vector<std::string>& data) = 0;
    virtual void doWrite(const std::vector<std::string>& data) = 0;

    // Virtual with default — can be overridden
    virtual std::vector<std::string> doValidate(const std::vector<std::string>& data) {
        return data;  // default: accept all
    }

    virtual void doCleanup() {
        // default: no cleanup needed
    }
};

// ====== Concrete implementation: CSV processor ======

class CsvProcessor : public DataProcessor {
protected:
    std::string name() const override { return "CsvProcessor"; }

    std::vector<std::string> doRead(const std::string& /*source*/) override {
        // Simulated CSV data
        return {"Alice,30,Engineer", "Bob,25,Designer", ",,-Invalid", "Carol,28,Manager"};
    }

    std::vector<std::string> doValidate(const std::vector<std::string>& data) override {
        std::vector<std::string> valid;
        for (const auto& row : data) {
            // Check: must have exactly 2 commas and no empty fields
            int commas = std::count(row.begin(), row.end(), ',');
            if (commas == 2 && row.front() != ',' && row.back() != ',') {
                valid.push_back(row);
            } else {
                std::cout << "    Rejected: \"" << row << "\"\n";
            }
        }
        return valid;
    }

    std::vector<std::string> doTransform(const std::vector<std::string>& data) override {
        // Convert to uppercase
        std::vector<std::string> result;
        for (auto row : data) {
            std::transform(row.begin(), row.end(), row.begin(), ::toupper);
            result.push_back(std::move(row));
        }
        return result;
    }

    void doWrite(const std::vector<std::string>& data) override {
        std::cout << "  Output:\n";
        for (const auto& row : data) {
            std::cout << "    " << row << "\n";
        }
    }
};

// ====== Concrete implementation: JSON processor ======

class JsonProcessor : public DataProcessor {
protected:
    std::string name() const override { return "JsonProcessor"; }

    std::vector<std::string> doRead(const std::string& /*source*/) override {
        return {
            R"({"name":"Alice","score":95})",
            R"({"name":"Bob","score":42})",
            R"({"name":"Carol","score":88})",
        };
    }

    std::vector<std::string> doTransform(const std::vector<std::string>& data) override {
        // Add a "grade" field based on score (simplified string manipulation)
        std::vector<std::string> result;
        for (const auto& record : data) {
            auto pos = record.find("\"score\":");
            if (pos != std::string::npos) {
                int score = std::stoi(record.substr(pos + 8));
                std::string grade = score >= 90 ? "A" : score >= 70 ? "B" : "C";
                std::string modified = record.substr(0, record.size() - 1)
                    + ",\"grade\":\"" + grade + "\"}";
                result.push_back(modified);
            }
        }
        return result;
    }

    void doWrite(const std::vector<std::string>& data) override {
        std::cout << "  Output JSON array:\n  [\n";
        for (size_t i = 0; i < data.size(); ++i) {
            std::cout << "    " << data[i];
            if (i + 1 < data.size()) std::cout << ",";
            std::cout << "\n";
        }
        std::cout << "  ]\n";
    }

    void doCleanup() override {
        std::cout << "  [Cleanup] Clearing JSON parser cache\n";
    }
};

// ====== Why NVI matters: base can add cross-cutting concerns ======

// If process() were virtual, a derived class could override it and skip
// the timing, logging, or validation steps. With NVI, the base class
// guarantees the skeleton always runs — derived classes only customize
// the individual hooks.

int main() {
    std::vector<std::unique_ptr<DataProcessor>> processors;
    processors.push_back(std::make_unique<CsvProcessor>());
    processors.push_back(std::make_unique<JsonProcessor>());

    for (auto& proc : processors) {
        proc->process("input_data");
    }

    return 0;
}
```

Why NVI is preferred over public virtual methods:

1. **Guaranteed invariants** — the non-virtual `process()` always runs timing, logging, and the full pipeline. A derived class cannot accidentally skip steps.
2. **Single point of control** — adding metrics or locking requires changing only the base class, not every override.
3. **Separate concerns** — the public API (what clients call) is decoupled from customization points (what subclasses override). You can change one without affecting the other.
4. **Clear contract** — private virtuals signal "this is a hook for implementors" vs public methods that signal "this is the API for callers."'''),

    ("cpp_deep/type_erasure_polymorphism", r'''How do I implement type erasure in C++ for runtime polymorphism without requiring classes to inherit from a common base?''', r'''<think>
Type erasure allows runtime polymorphism without inheritance. The key idea:
- An outer class holds a pointer to an internal concept (abstract base).
- A templated model class implements the concept for any type.
- The outer class presents a uniform interface.

This is how std::function, std::any, and std::format work internally.

I'll show a practical example: a `Drawable` type that can hold any object with
a draw() method, without requiring inheritance. Also show how to add SBO (Small
Buffer Optimization) for avoiding heap allocation on small types.

Key steps:
1. Define Concept (pure virtual interface) as a private nested class.
2. Define Model<T> that wraps any T satisfying the concept.
3. Outer class stores unique_ptr<Concept>.
4. Optionally add concept (C++20) to constrain what T is accepted.
</think>

Type erasure gives you runtime polymorphism without requiring types to inherit from a common base. This is the technique behind `std::function` and `std::any`.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <cmath>

// ====== C++20 concept to constrain acceptable types ======

template <typename T>
concept HasDraw = requires(const T& t) {
    { t.draw() } -> std::same_as<void>;
    { t.area() } -> std::convertible_to<double>;
    { t.name() } -> std::convertible_to<std::string>;
};

// ====== Type-erased Drawable ======

class Drawable {
    // Internal concept (private abstract base)
    struct Concept {
        virtual ~Concept() = default;
        virtual void draw() const = 0;
        virtual double area() const = 0;
        virtual std::string name() const = 0;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };

    // Model wraps any type T that satisfies the concept
    template <HasDraw T>
    struct Model final : Concept {
        T data_;

        explicit Model(T obj) : data_(std::move(obj)) {}

        void draw() const override { data_.draw(); }
        double area() const override { return data_.area(); }
        std::string name() const override { return data_.name(); }
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model>(data_);
        }
    };

    std::unique_ptr<Concept> pimpl_;

public:
    // Constructor: accepts any type that satisfies HasDraw
    template <HasDraw T>
    Drawable(T obj) : pimpl_(std::make_unique<Model<T>>(std::move(obj))) {}

    // Value semantics (copy & move)
    Drawable(const Drawable& other) : pimpl_(other.pimpl_->clone()) {}
    Drawable(Drawable&&) noexcept = default;
    Drawable& operator=(const Drawable& other) {
        pimpl_ = other.pimpl_->clone();
        return *this;
    }
    Drawable& operator=(Drawable&&) noexcept = default;

    // Forwarding interface
    void draw() const { pimpl_->draw(); }
    double area() const { return pimpl_->area(); }
    std::string name() const { return pimpl_->name(); }
};

// ====== Types that satisfy the concept — NO inheritance needed ======

// These are completely independent types with no common base

struct Circle {
    double radius;
    void draw() const {
        std::cout << "  Drawing circle (r=" << radius << ")\n";
    }
    double area() const { return M_PI * radius * radius; }
    std::string name() const { return "Circle"; }
};

struct Rectangle {
    double width, height;
    void draw() const {
        std::cout << "  Drawing rectangle (" << width << "x" << height << ")\n";
    }
    double area() const { return width * height; }
    std::string name() const { return "Rectangle"; }
};

struct Triangle {
    double base, height;
    void draw() const {
        std::cout << "  Drawing triangle (b=" << base << " h=" << height << ")\n";
    }
    double area() const { return 0.5 * base * height; }
    std::string name() const { return "Triangle"; }
};

// Even a lambda-based shape works!
struct CustomShape {
    std::string label;
    double a;
    void draw() const {
        std::cout << "  Drawing custom: " << label << "\n";
    }
    double area() const { return a; }
    std::string name() const { return label; }
};

// ====== Free function that works on any Drawable ======

void renderScene(const std::vector<Drawable>& shapes) {
    double totalArea = 0;
    for (const auto& shape : shapes) {
        std::cout << shape.name() << " (area=" << shape.area() << "):\n";
        shape.draw();
        totalArea += shape.area();
    }
    std::cout << "Total area: " << totalArea << "\n";
}

int main() {
    // Heterogeneous collection with value semantics — no pointers, no inheritance
    std::vector<Drawable> scene;
    scene.emplace_back(Circle{5.0});
    scene.emplace_back(Rectangle{10.0, 3.0});
    scene.emplace_back(Triangle{8.0, 4.0});
    scene.emplace_back(CustomShape{"Star", 12.5});

    std::cout << "=== Scene ===\n";
    renderScene(scene);

    // Value semantics: copy the entire scene
    std::cout << "\n=== Copied scene (independent) ===\n";
    auto sceneCopy = scene;
    sceneCopy.push_back(Circle{2.0});
    renderScene(sceneCopy);

    // The original is unchanged
    std::cout << "\n=== Original scene (unchanged) ===\n";
    std::cout << "Original has " << scene.size() << " shapes\n";
    std::cout << "Copy has " << sceneCopy.size() << " shapes\n";

    // This would NOT compile — std::string doesn't have draw()/area()/name():
    // Drawable bad = std::string("hello");  // concept constraint fails

    return 0;
}
```

The critical insight: `Circle`, `Rectangle`, `Triangle`, and `CustomShape` are completely independent types with no common base class. The `Drawable` wrapper erases their types behind a uniform interface using the internal Concept/Model pattern. The C++20 `HasDraw` concept provides clear compile-time errors if you try to wrap an incompatible type.

This is exactly how `std::function` works: it can hold any callable — lambdas, function pointers, functors — without requiring them to inherit from anything.'''),

    ("cpp_deep/ecs_architecture", r'''How do I design an Entity Component System (ECS) architecture in modern C++?''', r'''<think>
ECS separates data (Components) from logic (Systems) and identity (Entities).
This is the dominant architecture in game engines (Unity DOTS, Entt, Flecs).

Key principles:
- Entity: just an ID (integer).
- Component: pure data, no behavior (Position, Velocity, Health, etc.).
- System: logic that operates on entities with specific component combinations.

Modern C++ ECS design:
- Use sparse sets or unordered_maps per component type.
- Type erasure for component storage (each component type gets its own pool).
- Compile-time component queries using variadic templates.
- Cache-friendly: iterate components contiguously, not scattered across objects.

I'll build a minimal but functional ECS with:
- Entity creation/destruction
- Component add/remove/get
- System registration and execution
- A view/query system for iterating entities with specific components
</think>

ECS separates identity (Entity), data (Component), and logic (System) for cache-friendly, composable game architectures. Here is a minimal but functional implementation.

```cpp
#include <iostream>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <memory>
#include <typeindex>
#include <any>
#include <functional>
#include <algorithm>
#include <cmath>
#include <cassert>

// ====== Entity: just an ID ======

using Entity = uint32_t;
constexpr Entity NULL_ENTITY = 0;

// ====== Component Storage (type-erased pool per component type) ======

class IComponentPool {
public:
    virtual ~IComponentPool() = default;
    virtual void remove(Entity e) = 0;
    virtual bool has(Entity e) const = 0;
};

template <typename T>
class ComponentPool : public IComponentPool {
    std::unordered_map<Entity, T> data_;
public:
    T& add(Entity e, T component) {
        return data_.emplace(e, std::move(component)).first->second;
    }
    void remove(Entity e) override { data_.erase(e); }
    bool has(Entity e) const override { return data_.count(e) > 0; }
    T& get(Entity e) { return data_.at(e); }
    const T& get(Entity e) const { return data_.at(e); }

    // Iterate all components of this type
    template <typename Fn>
    void forEach(Fn&& fn) {
        for (auto& [entity, comp] : data_) fn(entity, comp);
    }

    auto begin() { return data_.begin(); }
    auto end()   { return data_.end(); }
    size_t size() const { return data_.size(); }
};

// ====== World: manages entities, components, and systems ======

class World {
    Entity nextId_ = 1;
    std::unordered_set<Entity> alive_;
    std::unordered_map<std::type_index, std::unique_ptr<IComponentPool>> pools_;

    template <typename T>
    ComponentPool<T>& getPool() {
        auto idx = std::type_index(typeid(T));
        auto it = pools_.find(idx);
        if (it == pools_.end()) {
            auto pool = std::make_unique<ComponentPool<T>>();
            auto& ref = *pool;
            pools_[idx] = std::move(pool);
            return ref;
        }
        return static_cast<ComponentPool<T>&>(*it->second);
    }

public:
    Entity createEntity() {
        Entity e = nextId_++;
        alive_.insert(e);
        return e;
    }

    void destroyEntity(Entity e) {
        for (auto& [_, pool] : pools_) pool->remove(e);
        alive_.erase(e);
    }

    bool isAlive(Entity e) const { return alive_.count(e) > 0; }

    template <typename T, typename... Args>
    T& addComponent(Entity e, Args&&... args) {
        return getPool<T>().add(e, T{std::forward<Args>(args)...});
    }

    template <typename T>
    void removeComponent(Entity e) { getPool<T>().remove(e); }

    template <typename T>
    bool hasComponent(Entity e) { return getPool<T>().has(e); }

    template <typename T>
    T& getComponent(Entity e) { return getPool<T>().get(e); }

    // Query: iterate all entities that have ALL of the specified components
    template <typename... Components, typename Fn>
    void each(Fn&& fn) {
        // Find smallest pool to iterate (optimization)
        auto& firstPool = getPool<std::tuple_element_t<0, std::tuple<Components...>>>();

        for (auto& [entity, _] : firstPool) {
            if ((getPool<Components>().has(entity) && ...)) {
                fn(entity, getPool<Components>().get(entity)...);
            }
        }
    }

    size_t entityCount() const { return alive_.size(); }
};

// ====== Components: pure data, no behavior ======

struct Position { float x = 0, y = 0; };
struct Velocity { float dx = 0, dy = 0; };
struct Health { int current = 100, max = 100; };
struct Sprite { std::string texture; int layer = 0; };
struct Collider { float radius = 1.0f; };

// ====== Systems: pure logic ======

void movementSystem(World& world, float dt) {
    world.each<Position, Velocity>([dt](Entity, Position& pos, Velocity& vel) {
        pos.x += vel.dx * dt;
        pos.y += vel.dy * dt;
    });
}

void gravitySystem(World& world, float dt) {
    world.each<Velocity>([dt](Entity, Velocity& vel) {
        vel.dy -= 9.81f * dt;
    });
}

void collisionSystem(World& world) {
    struct EntityPos { Entity e; float x, y, r; };
    std::vector<EntityPos> collidables;

    world.each<Position, Collider>([&](Entity e, Position& p, Collider& c) {
        collidables.push_back({e, p.x, p.y, c.radius});
    });

    for (size_t i = 0; i < collidables.size(); ++i) {
        for (size_t j = i + 1; j < collidables.size(); ++j) {
            auto& a = collidables[i];
            auto& b = collidables[j];
            float dx = a.x - b.x, dy = a.y - b.y;
            float dist = std::sqrt(dx * dx + dy * dy);
            if (dist < a.r + b.r) {
                std::cout << "  Collision: Entity " << a.e
                          << " <-> Entity " << b.e << "\n";
                // Apply damage if they have Health
                if (world.hasComponent<Health>(a.e))
                    world.getComponent<Health>(a.e).current -= 10;
                if (world.hasComponent<Health>(b.e))
                    world.getComponent<Health>(b.e).current -= 10;
            }
        }
    }
}

void renderSystem(World& world) {
    world.each<Position, Sprite>([](Entity e, Position& pos, Sprite& spr) {
        std::cout << "  Render Entity " << e << " [" << spr.texture
                  << "] at (" << pos.x << ", " << pos.y << ")\n";
    });
}

void healthSystem(World& world, std::vector<Entity>& toDestroy) {
    world.each<Health>([&](Entity e, Health& hp) {
        if (hp.current <= 0) {
            std::cout << "  Entity " << e << " died!\n";
            toDestroy.push_back(e);
        }
    });
}

int main() {
    World world;

    // Create entities with different component combinations
    Entity player = world.createEntity();
    world.addComponent<Position>(player, 0.0f, 10.0f);
    world.addComponent<Velocity>(player, 2.0f, 0.0f);
    world.addComponent<Health>(player, 100, 100);
    world.addComponent<Sprite>(player, "hero.png", 1);
    world.addComponent<Collider>(player, 1.5f);

    Entity enemy = world.createEntity();
    world.addComponent<Position>(enemy, 3.0f, 10.0f);
    world.addComponent<Velocity>(enemy, -1.0f, 0.0f);
    world.addComponent<Health>(enemy, 30, 50);
    world.addComponent<Sprite>(enemy, "goblin.png", 1);
    world.addComponent<Collider>(enemy, 1.0f);

    // Scenery: position + sprite only (no health, velocity, or collider)
    Entity tree = world.createEntity();
    world.addComponent<Position>(tree, 5.0f, 0.0f);
    world.addComponent<Sprite>(tree, "tree.png", 0);

    std::cout << "Entities: " << world.entityCount() << "\n\n";

    // Game loop simulation
    float dt = 1.0f / 60.0f;
    for (int frame = 0; frame < 5; ++frame) {
        std::cout << "=== Frame " << frame << " ===\n";

        gravitySystem(world, dt);
        movementSystem(world, dt);
        collisionSystem(world);

        std::vector<Entity> dead;
        healthSystem(world, dead);
        for (Entity e : dead) world.destroyEntity(e);

        renderSystem(world);
        std::cout << "\n";
    }

    return 0;
}
```

Key ECS principles demonstrated:
- **Entities** are just IDs — no classes, no inheritance.
- **Components** are pure data structs — no methods or behavior.
- **Systems** are free functions that query the world for entities with specific component combinations.
- The `world.each<Position, Velocity>(...)` query iterates only entities that have both components, using fold expressions for compile-time component matching.
- Adding new behavior means adding a new System — no existing code changes.'''),

    ("cpp_deep/pimpl_compilation_firewall", r'''How do I implement the Pimpl idiom in C++ properly as a compilation firewall?''', r'''<think>
Pimpl (Pointer to Implementation) hides implementation details behind an opaque
pointer, reducing compile-time dependencies. It's a degenerate Bridge pattern.

Key considerations:
- Forward-declare Impl in header, define in .cpp.
- Use std::unique_ptr<Impl> — requires destructor defined in .cpp (where Impl is complete).
- Must declare destructor in header, define in .cpp.
- Same for move constructor/assignment if needed.
- Copy: either delete or deep-copy the Impl.
- Propagate const: raw pimpl pointer doesn't propagate const — use
  std::experimental::propagate_const or a helper.

I'll show both the header and implementation file, plus the const-propagation issue
and its solution.
</think>

Pimpl hides implementation details behind an opaque pointer, drastically reducing recompilation when internals change. Here is the complete pattern with proper const propagation.

```cpp
// ====== widget.h — public header (what clients include) ======

// This header has NO implementation details, NO private member types,
// and NO expensive #includes. Changing the implementation recompiles
// only widget.cpp, not every file that includes widget.h.

#ifndef WIDGET_H
#define WIDGET_H

#include <memory>
#include <string>

// Const-propagating unique_ptr wrapper
// (std::unique_ptr<Impl> doesn't propagate const to pointee)
template <typename T>
class PropagateConst {
    std::unique_ptr<T> ptr_;
public:
    PropagateConst(std::unique_ptr<T> p) : ptr_(std::move(p)) {}
    PropagateConst(PropagateConst&&) noexcept = default;
    PropagateConst& operator=(PropagateConst&&) noexcept = default;
    ~PropagateConst() = default;

    T& operator*() { return *ptr_; }
    const T& operator*() const { return *ptr_; }
    T* operator->() { return ptr_.get(); }
    const T* operator->() const { return ptr_.get(); }
    explicit operator bool() const { return bool(ptr_); }
};

class Widget {
public:
    // Constructor / destructor must be declared here, defined in .cpp
    explicit Widget(const std::string& name, int width = 100, int height = 50);
    ~Widget();

    // Move: declared here, defined in .cpp (needs complete Impl type)
    Widget(Widget&& other) noexcept;
    Widget& operator=(Widget&& other) noexcept;

    // Copy: deep-copies the Impl
    Widget(const Widget& other);
    Widget& operator=(const Widget& other);

    // Public interface — stable, rarely changes
    void setSize(int width, int height);
    void setText(const std::string& text);
    void setVisible(bool visible);

    int width() const;
    int height() const;
    std::string text() const;
    bool isVisible() const;

    void render() const;

private:
    struct Impl;  // forward declaration only
    PropagateConst<Impl> pimpl_;  // const Widget -> const Impl
};

#endif // WIDGET_H


// ====== widget.cpp — implementation (hidden from clients) ======

// In a real project, this would be a separate .cpp file.
// #include "widget.h"

#include <iostream>
#include <vector>
#include <algorithm>
// These expensive headers are only included in the .cpp,
// not in every file that uses Widget.

// The actual implementation — completely hidden from clients
struct Widget::Impl {
    std::string name;
    std::string text;
    int width, height;
    bool visible = true;

    // Can include complex members without affecting client compilation
    struct RenderCache {
        bool dirty = true;
        std::vector<std::string> lines;
    };
    RenderCache cache;

    Impl(std::string n, int w, int h)
        : name(std::move(n)), width(w), height(h) {}

    void invalidateCache() { cache.dirty = true; }

    void rebuildCache() {
        if (!cache.dirty) return;
        cache.lines.clear();
        std::string border(width, '-');
        cache.lines.push_back("+" + border + "+");
        // Center the text
        int pad = std::max(0, (width - static_cast<int>(text.size())) / 2);
        std::string content = std::string(pad, ' ') + text;
        content.resize(width, ' ');
        cache.lines.push_back("|" + content + "|");
        cache.lines.push_back("+" + border + "+");
        cache.dirty = false;
    }
};

// Constructor — creates Impl
Widget::Widget(const std::string& name, int width, int height)
    : pimpl_(std::make_unique<Impl>(name, width, height)) {}

// Destructor — must be here where Impl is complete
Widget::~Widget() = default;

// Move operations
Widget::Widget(Widget&& other) noexcept = default;
Widget& Widget::operator=(Widget&& other) noexcept = default;

// Deep copy
Widget::Widget(const Widget& other)
    : pimpl_(std::make_unique<Impl>(*other.pimpl_)) {}

Widget& Widget::operator=(const Widget& other) {
    if (this != &other) {
        pimpl_ = PropagateConst<Impl>(std::make_unique<Impl>(*other.pimpl_));
    }
    return *this;
}

// Public methods forward to Impl
void Widget::setSize(int w, int h) {
    pimpl_->width = w;
    pimpl_->height = h;
    pimpl_->invalidateCache();
}

void Widget::setText(const std::string& t) {
    pimpl_->text = t;
    pimpl_->invalidateCache();
}

void Widget::setVisible(bool v) { pimpl_->visible = v; }

int Widget::width() const { return pimpl_->width; }
int Widget::height() const { return pimpl_->height; }
std::string Widget::text() const { return pimpl_->text; }
bool Widget::isVisible() const { return pimpl_->visible; }

void Widget::render() const {
    if (!pimpl_->visible) return;
    // const Widget -> const Impl via PropagateConst, but rebuildCache
    // mutates cache. In production, make cache mutable or use const_cast
    // for the cache specifically. For demo, we cast:
    const_cast<Impl*>(&*pimpl_)->rebuildCache();
    for (const auto& line : pimpl_->cache.lines) {
        std::cout << line << "\n";
    }
}

// ====== main.cpp — client code ======

int main() {
    // Client only needs widget.h — never sees Impl details
    Widget w("MyButton", 20, 3);
    w.setText("Click Me");
    w.render();

    std::cout << "\n";
    w.setSize(30, 3);
    w.setText("Resized Button");
    w.render();

    // Copy works (deep copy of Impl)
    Widget copy = w;
    copy.setText("I'm a copy");
    std::cout << "\nOriginal: " << w.text() << "\n";
    std::cout << "Copy:     " << copy.text() << "\n";

    // Move works
    Widget moved = std::move(copy);
    std::cout << "Moved:    " << moved.text() << "\n";
    moved.render();

    return 0;
}
```

The compilation firewall works because `widget.h` contains zero implementation details. Adding members to `Impl`, changing algorithms, or adding `#include`s in `widget.cpp` does not trigger recompilation of any file that includes `widget.h`. The `PropagateConst` wrapper ensures that `const Widget` methods cannot accidentally mutate the `Impl` through the pointer.'''),

    ("cpp_deep/dependency_injection_templates", r'''How do I implement dependency injection in C++ using templates for compile-time injection with zero overhead?''', r'''<think>
Dependency injection in C++ can be done:
1. Runtime: via virtual interfaces (like Java/C#) — overhead of virtual dispatch.
2. Compile-time: via templates — zero overhead, types resolved at compile time.

Template-based DI:
- Services are template parameters.
- The component is templated on its dependencies.
- Different "configurations" instantiate different templates.
- Concepts (C++20) constrain the dependencies.
- No virtual dispatch, no heap allocation for the DI mechanism.

Tradeoff: templates expose implementation in headers and increase compile time,
but produce optimal runtime code. For hot paths, this is preferred.

I'll show a practical example: an application with Logger, Database, and Cache
dependencies, all injected via templates. Show how to swap implementations for
testing.
</think>

Template-based dependency injection gives zero-overhead polymorphism: dependencies are resolved at compile time with no virtual dispatch.

```cpp
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
#include <chrono>
#include <cassert>

// ====== Concepts: define what dependencies must provide ======

template <typename T>
concept LoggerLike = requires(T& logger, const std::string& msg) {
    { logger.info(msg) } -> std::same_as<void>;
    { logger.error(msg) } -> std::same_as<void>;
};

template <typename T>
concept CacheLike = requires(T& cache, const std::string& key, const std::string& val) {
    { cache.get(key) } -> std::same_as<std::string>;
    { cache.set(key, val) } -> std::same_as<void>;
    { cache.has(key) } -> std::same_as<bool>;
};

template <typename T>
concept DatabaseLike = requires(T& db, const std::string& query) {
    { db.execute(query) } -> std::same_as<std::vector<std::string>>;
};

// ====== Production implementations ======

class ConsoleLogger {
public:
    void info(const std::string& msg)  { std::cout << "[INFO]  " << msg << "\n"; }
    void error(const std::string& msg) { std::cout << "[ERROR] " << msg << "\n"; }
};

class RedisCache {
    std::unordered_map<std::string, std::string> store_;
public:
    std::string get(const std::string& key) {
        auto it = store_.find(key);
        return it != store_.end() ? it->second : "";
    }
    void set(const std::string& key, const std::string& val) {
        store_[key] = val;
    }
    bool has(const std::string& key) {
        return store_.count(key) > 0;
    }
};

class PostgresDatabase {
public:
    std::vector<std::string> execute(const std::string& query) {
        // Simulated query results
        return {"row1: " + query, "row2: " + query};
    }
};

// ====== Test/Mock implementations ======

class NullLogger {
public:
    void info(const std::string&) {}   // silently discard
    void error(const std::string&) {}
};

class MockLogger {
public:
    std::vector<std::string> messages;
    void info(const std::string& msg)  { messages.push_back("INFO: " + msg); }
    void error(const std::string& msg) { messages.push_back("ERROR: " + msg); }
};

class MockCache {
    std::unordered_map<std::string, std::string> store_;
public:
    int getCount = 0, setCount = 0;
    std::string get(const std::string& key) { ++getCount; return store_[key]; }
    void set(const std::string& key, const std::string& val) { ++setCount; store_[key] = val; }
    bool has(const std::string& key) { return store_.count(key) > 0; }
};

class MockDatabase {
public:
    std::vector<std::string> lastResults = {"mock_row_1", "mock_row_2"};
    int queryCount = 0;
    std::vector<std::string> execute(const std::string&) {
        ++queryCount;
        return lastResults;
    }
};

// ====== Service: templated on its dependencies (DI) ======

template <LoggerLike Logger, CacheLike Cache, DatabaseLike Database>
class UserService {
    Logger& logger_;
    Cache& cache_;
    Database& db_;

public:
    UserService(Logger& logger, Cache& cache, Database& db)
        : logger_(logger), cache_(cache), db_(db) {}

    std::vector<std::string> getUsers() {
        const std::string cacheKey = "users:all";

        if (cache_.has(cacheKey)) {
            logger_.info("Cache hit for users");
            auto cached = cache_.get(cacheKey);
            return {cached};
        }

        logger_.info("Cache miss — querying database");
        auto results = db_.execute("SELECT * FROM users");

        if (results.empty()) {
            logger_.error("No users found");
            return {};
        }

        cache_.set(cacheKey, results[0]);
        logger_.info("Cached " + std::to_string(results.size()) + " results");
        return results;
    }
};

// ====== Composition root: wire dependencies ======

// Production configuration
struct ProductionContainer {
    ConsoleLogger logger;
    RedisCache cache;
    PostgresDatabase db;

    auto createUserService() {
        return UserService<ConsoleLogger, RedisCache, PostgresDatabase>(logger, cache, db);
    }
};

// Test configuration
struct TestContainer {
    MockLogger logger;
    MockCache cache;
    MockDatabase db;

    auto createUserService() {
        return UserService<MockLogger, MockCache, MockDatabase>(logger, cache, db);
    }
};

int main() {
    // === Production ===
    std::cout << "=== Production ===\n";
    {
        ProductionContainer container;
        auto userService = container.createUserService();

        auto users = userService.getUsers();  // cache miss
        std::cout << "Got " << users.size() << " results\n\n";

        users = userService.getUsers();  // cache hit
        std::cout << "Got " << users.size() << " results\n";
    }

    // === Testing ===
    std::cout << "\n=== Testing ===\n";
    {
        TestContainer container;
        auto userService = container.createUserService();

        auto users = userService.getUsers();
        assert(container.db.queryCount == 1);
        assert(container.cache.setCount == 1);

        users = userService.getUsers();
        assert(container.db.queryCount == 1);  // not called again
        assert(container.cache.getCount >= 1);

        // Verify log messages
        for (const auto& msg : container.logger.messages) {
            std::cout << "  " << msg << "\n";
        }
        std::cout << "  DB queries: " << container.db.queryCount << "\n";
        std::cout << "  Cache sets: " << container.cache.setCount << "\n";
        std::cout << "  All assertions passed!\n";
    }

    return 0;
}
```

Key advantages of template-based DI:
- **Zero overhead**: no virtual dispatch, no heap allocation for the DI mechanism. The compiler inlines everything.
- **Compile-time safety**: C++20 concepts ensure dependencies satisfy the required interface at template instantiation time.
- **Easy testing**: swap `ConsoleLogger` for `MockLogger` by changing template parameters. No factory or DI framework needed.
- **Composition root**: `ProductionContainer` and `TestContainer` wire dependencies in one place, following the DI principle of composing at the top.'''),

    ("cpp_deep/event_bus_type_safe", r'''How do I build a type-safe event bus in C++ where subscribers receive strongly-typed events without downcasting?''', r'''<think>
A type-safe event bus routes events to subscribers based on event type. The key
challenge is storing handlers for different event types in a single container
without losing type safety.

Approach:
- Use std::type_index as the key to a map of handler lists.
- Each handler list is type-erased (std::any wrapping vector<function<void(const Event&)>>).
- When publishing, look up the event's type_index and call all registered handlers.
- Subscribers get strongly-typed references — no downcasting.

Alternative: use templates and std::function with proper type erasure.

I'll also add:
- Subscription handles for RAII unsubscribe.
- Priority ordering.
- Event filtering.
</think>

A type-safe event bus dispatches events to subscribers with strong typing — no `dynamic_cast`, no `void*`, no base event class needed.

```cpp
#include <iostream>
#include <functional>
#include <unordered_map>
#include <vector>
#include <typeindex>
#include <any>
#include <memory>
#include <string>
#include <algorithm>

// ====== Subscription handle for RAII unsubscribe ======

class SubscriptionHandle {
    std::function<void()> unsubscribe_;
public:
    SubscriptionHandle() = default;
    explicit SubscriptionHandle(std::function<void()> unsub)
        : unsubscribe_(std::move(unsub)) {}
    ~SubscriptionHandle() { if (unsubscribe_) unsubscribe_(); }

    SubscriptionHandle(SubscriptionHandle&&) noexcept = default;
    SubscriptionHandle& operator=(SubscriptionHandle&&) noexcept = default;
    SubscriptionHandle(const SubscriptionHandle&) = delete;
    SubscriptionHandle& operator=(const SubscriptionHandle&) = delete;

    void release() { unsubscribe_ = nullptr; }  // keep subscription alive
};

// ====== Type-safe Event Bus ======

class EventBus {
    struct HandlerEntry {
        uint64_t id;
        int priority;
        std::any callback;  // stores std::function<void(const EventType&)>
    };

    std::unordered_map<std::type_index, std::vector<HandlerEntry>> handlers_;
    uint64_t nextId_ = 0;

    template <typename Event>
    using HandlerFn = std::function<void(const Event&)>;

public:
    // Subscribe to an event type. Returns RAII handle that auto-unsubscribes.
    template <typename Event>
    [[nodiscard]] SubscriptionHandle subscribe(
        HandlerFn<Event> handler, int priority = 0)
    {
        auto idx = std::type_index(typeid(Event));
        uint64_t id = nextId_++;

        handlers_[idx].push_back(HandlerEntry{id, priority,
            std::any(std::move(handler))});

        // Sort by priority (higher = called first)
        std::sort(handlers_[idx].begin(), handlers_[idx].end(),
            [](const auto& a, const auto& b) { return a.priority > b.priority; });

        return SubscriptionHandle([this, idx, id] {
            auto it = handlers_.find(idx);
            if (it != handlers_.end()) {
                auto& vec = it->second;
                vec.erase(std::remove_if(vec.begin(), vec.end(),
                    [id](const auto& e) { return e.id == id; }),
                    vec.end());
            }
        });
    }

    // Publish an event to all subscribers of its type
    template <typename Event>
    void publish(const Event& event) const {
        auto it = handlers_.find(std::type_index(typeid(Event)));
        if (it == handlers_.end()) return;

        for (const auto& entry : it->second) {
            const auto& fn = std::any_cast<const HandlerFn<Event>&>(entry.callback);
            fn(event);
        }
    }

    // Convenience: publish with in-place construction
    template <typename Event, typename... Args>
    void emit(Args&&... args) {
        publish(Event{std::forward<Args>(args)...});
    }

    template <typename Event>
    size_t subscriberCount() const {
        auto it = handlers_.find(std::type_index(typeid(Event)));
        return it != handlers_.end() ? it->second.size() : 0;
    }
};

// ====== Event types (plain structs — no base class needed) ======

struct PlayerJoined {
    std::string name;
    int team;
};

struct PlayerLeft {
    std::string name;
    std::string reason;
};

struct ChatMessage {
    std::string sender;
    std::string text;
    int channel;
};

struct DamageEvent {
    int attackerId;
    int targetId;
    float amount;
    std::string type;  // "physical", "magic", etc.
};

// ====== Systems that subscribe to events ======

class ChatSystem {
    SubscriptionHandle msgSub_;
    SubscriptionHandle joinSub_;
    SubscriptionHandle leaveSub_;
public:
    explicit ChatSystem(EventBus& bus) {
        msgSub_ = bus.subscribe<ChatMessage>([](const ChatMessage& msg) {
            std::cout << "  [Chat #" << msg.channel << "] "
                      << msg.sender << ": " << msg.text << "\n";
        });
        joinSub_ = bus.subscribe<PlayerJoined>([](const PlayerJoined& e) {
            std::cout << "  [Chat] " << e.name << " joined team " << e.team << "\n";
        });
        leaveSub_ = bus.subscribe<PlayerLeft>([](const PlayerLeft& e) {
            std::cout << "  [Chat] " << e.name << " left (" << e.reason << ")\n";
        });
    }
};

class StatsSystem {
    SubscriptionHandle damageSub_;
    float totalDamage_ = 0;
public:
    explicit StatsSystem(EventBus& bus) {
        damageSub_ = bus.subscribe<DamageEvent>([this](const DamageEvent& e) {
            totalDamage_ += e.amount;
            std::cout << "  [Stats] " << e.type << " damage: " << e.amount
                      << " (total: " << totalDamage_ << ")\n";
        }, 10);  // high priority: stats run before other handlers
    }
};

class AchievementSystem {
    SubscriptionHandle damageSub_;
    SubscriptionHandle joinSub_;
    int killStreak_ = 0;
public:
    explicit AchievementSystem(EventBus& bus) {
        damageSub_ = bus.subscribe<DamageEvent>([this](const DamageEvent& e) {
            if (e.amount > 50) {
                std::cout << "  [Achievement] MASSIVE HIT! " << e.amount << " damage\n";
            }
        }, 5);  // lower priority than StatsSystem
    }
};

int main() {
    EventBus bus;

    std::cout << "=== Creating systems ===\n";
    ChatSystem chat(bus);
    StatsSystem stats(bus);

    std::cout << "\n=== Game events ===\n";
    bus.publish(PlayerJoined{"Alice", 1});
    bus.publish(PlayerJoined{"Bob", 2});
    bus.publish(ChatMessage{"Alice", "Hello everyone!", 0});
    bus.publish(DamageEvent{1, 2, 35.0f, "physical"});
    bus.publish(DamageEvent{2, 1, 60.0f, "magic"});

    std::cout << "\n=== Adding achievement system mid-game ===\n";
    AchievementSystem achievements(bus);
    bus.publish(DamageEvent{1, 2, 75.0f, "critical"});

    std::cout << "\n=== RAII auto-unsubscribe ===\n";
    {
        auto tempSub = bus.subscribe<ChatMessage>([](const ChatMessage& msg) {
            std::cout << "  [TempListener] heard: " << msg.text << "\n";
        });
        bus.publish(ChatMessage{"System", "This reaches temp listener", 0});
        std::cout << "  (TempListener going out of scope...)\n";
    }
    bus.publish(ChatMessage{"System", "Temp listener is gone", 0});

    std::cout << "\nChatMessage subscribers: " << bus.subscriberCount<ChatMessage>() << "\n";
    bus.publish(PlayerLeft{"Bob", "disconnected"});

    return 0;
}
```

Key design features:
- **No base event class**: events are plain structs, dispatched by `std::type_index`.
- **Strong typing**: handlers receive `const Event&` directly — no casting.
- **RAII subscriptions**: `SubscriptionHandle` auto-unsubscribes on destruction, so systems cannot leak handlers.
- **Priority ordering**: higher-priority handlers run first (e.g., StatsSystem at priority 10 runs before AchievementSystem at priority 5).
- **Dynamic composition**: systems can subscribe/unsubscribe at any time during runtime.'''),

    ("cpp_deep/service_locator_vs_di", r'''What are the tradeoffs between the Service Locator pattern and Dependency Injection in C++? Show both implementations.''', r'''<think>
Service Locator vs DI is a classic debate. I need to show both patterns, explain
when each is appropriate, and be honest about tradeoffs.

Service Locator: global registry that components query for their dependencies.
- Pro: simple to use, easy to add to existing code, works well for optional services.
- Con: hidden dependencies, harder to test, runtime errors for missing services.

Dependency Injection: dependencies passed in via constructor/setter.
- Pro: explicit dependencies, easy to test, compile-time safety with templates.
- Con: can lead to "constructor parameter explosion", requires wiring code.

I'll implement both for the same set of services and show the testing story for each.
</think>

Both patterns decouple components from their concrete dependencies, but with different tradeoffs. Here is the same application built both ways.

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <unordered_map>
#include <typeindex>
#include <stdexcept>
#include <cassert>
#include <vector>

// ====== Service interfaces ======

class ILogger {
public:
    virtual ~ILogger() = default;
    virtual void log(const std::string& msg) = 0;
};

class IDatabase {
public:
    virtual ~IDatabase() = default;
    virtual std::string query(const std::string& sql) = 0;
};

class ICache {
public:
    virtual ~ICache() = default;
    virtual void set(const std::string& key, const std::string& val) = 0;
    virtual std::string get(const std::string& key) = 0;
};

// ====== Production implementations ======

class ConsoleLogger : public ILogger {
public:
    void log(const std::string& msg) override {
        std::cout << "[LOG] " << msg << "\n";
    }
};

class SqlDatabase : public IDatabase {
public:
    std::string query(const std::string& sql) override {
        return "Result of: " + sql;
    }
};

class MemoryCache : public ICache {
    std::unordered_map<std::string, std::string> store_;
public:
    void set(const std::string& key, const std::string& val) override {
        store_[key] = val;
    }
    std::string get(const std::string& key) override {
        auto it = store_.find(key);
        return it != store_.end() ? it->second : "";
    }
};

// ============================================================
// APPROACH 1: SERVICE LOCATOR
// ============================================================

class ServiceLocator {
    std::unordered_map<std::type_index, std::shared_ptr<void>> services_;

    // Singleton (for demonstration — in practice, prefer passing by reference)
    ServiceLocator() = default;
public:
    static ServiceLocator& instance() {
        static ServiceLocator loc;
        return loc;
    }

    template <typename T>
    void provide(std::shared_ptr<T> service) {
        services_[std::type_index(typeid(T))] = std::move(service);
    }

    template <typename T>
    std::shared_ptr<T> get() const {
        auto it = services_.find(std::type_index(typeid(T)));
        if (it == services_.end()) {
            throw std::runtime_error(
                std::string("Service not registered: ") + typeid(T).name());
        }
        return std::static_pointer_cast<T>(it->second);
    }

    template <typename T>
    bool has() const {
        return services_.count(std::type_index(typeid(T))) > 0;
    }

    void clear() { services_.clear(); }
};

// Component using Service Locator — dependencies are HIDDEN
class UserService_SL {
public:
    std::string getUser(int id) {
        // Dependencies fetched internally — caller can't see them
        auto& loc = ServiceLocator::instance();
        auto logger = loc.get<ILogger>();
        auto db = loc.get<IDatabase>();
        auto cache = loc.get<ICache>();

        std::string key = "user:" + std::to_string(id);
        auto cached = cache->get(key);
        if (!cached.empty()) {
            logger->log("Cache hit for user " + std::to_string(id));
            return cached;
        }

        logger->log("Querying user " + std::to_string(id));
        auto result = db->query("SELECT * FROM users WHERE id=" + std::to_string(id));
        cache->set(key, result);
        return result;
    }
};

// ============================================================
// APPROACH 2: DEPENDENCY INJECTION
// ============================================================

// Component using DI — dependencies are EXPLICIT in constructor
class UserService_DI {
    ILogger& logger_;
    IDatabase& db_;
    ICache& cache_;
public:
    // Constructor makes dependencies visible
    UserService_DI(ILogger& logger, IDatabase& db, ICache& cache)
        : logger_(logger), db_(db), cache_(cache) {}

    std::string getUser(int id) {
        std::string key = "user:" + std::to_string(id);
        auto cached = cache_.get(key);
        if (!cached.empty()) {
            logger_.log("Cache hit for user " + std::to_string(id));
            return cached;
        }

        logger_.log("Querying user " + std::to_string(id));
        auto result = db_.query("SELECT * FROM users WHERE id=" + std::to_string(id));
        cache_.set(key, result);
        return result;
    }
};

// ====== Mock implementations for testing ======

class MockLogger : public ILogger {
public:
    std::vector<std::string> messages;
    void log(const std::string& msg) override { messages.push_back(msg); }
};

class MockDatabase : public IDatabase {
public:
    int queryCount = 0;
    std::string query(const std::string& sql) override {
        ++queryCount;
        return "MockResult:" + sql;
    }
};

class MockCache : public ICache {
    std::unordered_map<std::string, std::string> store_;
public:
    void set(const std::string& key, const std::string& val) override { store_[key] = val; }
    std::string get(const std::string& key) override {
        auto it = store_.find(key);
        return it != store_.end() ? it->second : "";
    }
};

int main() {
    // ============================================================
    // SERVICE LOCATOR in action
    // ============================================================
    std::cout << "=== Service Locator ===\n";
    {
        auto& loc = ServiceLocator::instance();
        loc.provide<ILogger>(std::make_shared<ConsoleLogger>());
        loc.provide<IDatabase>(std::make_shared<SqlDatabase>());
        loc.provide<ICache>(std::make_shared<MemoryCache>());

        UserService_SL service;  // no constructor params — dependencies hidden
        std::cout << service.getUser(42) << "\n";
        std::cout << service.getUser(42) << "\n";  // cache hit

        loc.clear();
    }

    // Testing with Service Locator — must set up global state
    std::cout << "\n=== Testing with Service Locator ===\n";
    {
        auto& loc = ServiceLocator::instance();
        auto mockLog = std::make_shared<MockLogger>();
        auto mockDb  = std::make_shared<MockDatabase>();
        auto mockCache = std::make_shared<MockCache>();
        loc.provide<ILogger>(mockLog);
        loc.provide<IDatabase>(mockDb);
        loc.provide<ICache>(mockCache);

        UserService_SL service;
        service.getUser(1);
        assert(mockDb->queryCount == 1);
        service.getUser(1);  // cache hit
        assert(mockDb->queryCount == 1);  // not called again
        std::cout << "  SL tests passed (but required global state mutation)\n";
        loc.clear();
    }

    // ============================================================
    // DEPENDENCY INJECTION in action
    // ============================================================
    std::cout << "\n=== Dependency Injection ===\n";
    {
        ConsoleLogger logger;
        SqlDatabase db;
        MemoryCache cache;

        UserService_DI service(logger, db, cache);  // dependencies explicit
        std::cout << service.getUser(42) << "\n";
        std::cout << service.getUser(42) << "\n";
    }

    // Testing with DI — no global state needed
    std::cout << "\n=== Testing with DI ===\n";
    {
        MockLogger logger;
        MockDatabase db;
        MockCache cache;

        UserService_DI service(logger, db, cache);  // inject mocks directly
        service.getUser(1);
        assert(db.queryCount == 1);
        service.getUser(1);
        assert(db.queryCount == 1);
        std::cout << "  DI tests passed (no global state, pure local)\n";
    }

    /*
    ============================================================
    TRADEOFF SUMMARY
    ============================================================

    Service Locator:
    + Simple to add to existing code (no constructor changes)
    + Good for optional services (check has<T>() before get<T>())
    + Works well in plugin architectures
    - Hidden dependencies (can't see them from the API)
    - Runtime errors if service not registered
    - Tests must mutate global state (fragile, not parallelizable)
    - Harder to reason about what a class needs

    Dependency Injection:
    + Explicit dependencies (visible in constructor)
    + Compile-time safety (missing dependency = compile error)
    + Trivial to test (just pass mocks, no global state)
    + Can use templates for zero-overhead (no virtual dispatch)
    - "Constructor parameter explosion" with many dependencies
    - Requires wiring code (composition root)
    - Harder to retrofit into existing codebases

    Recommendation: Prefer DI for new code. Use Service Locator only
    for truly optional/plugin-based services or when retrofitting
    legacy code.
    */

    return 0;
}
```

The fundamental difference: with DI, looking at `UserService_DI`'s constructor tells you exactly what it needs. With Service Locator, you must read the entire implementation to discover its dependencies. DI makes testing trivial (pass mocks locally) while Service Locator requires mutating global state, which breaks test parallelism.'''),

    ("cpp_deep/cpp20_modules", r'''How do I use C++20 modules to organize code, and how does the module pattern replace traditional headers?''', r'''<think>
C++20 modules are a major change to how C++ code is organized. They replace
the preprocessor-based #include model with a proper module system.

Key concepts:
- Module declaration: `export module my_module;`
- Export: `export class Foo { ... };` or `export { ... }`
- Import: `import my_module;`
- Module partitions: `export module my_module:part1;`
- Global module fragment: `module; #include <legacy.h> export module my_module;`

Benefits over headers:
- No include guards needed
- No macro leakage between translation units
- Faster compilation (modules are compiled once, not per-TU)
- Better encapsulation (non-exported symbols are truly hidden)

Challenges:
- Build system support is still maturing (CMake 3.28+, MSVC, GCC 14+, Clang 16+)
- Module interface units vs implementation units
- Standard library modules (`import std;`) in C++23

I'll show a practical module-based project structure: a math library with
partitions for geometry and linear algebra.
</think>

C++20 modules replace the preprocessor `#include` model with proper compilation units. Here is a complete module-based library with partitions.

```cpp
// ====================================================================
// NOTE: Module support requires specific compiler flags:
//   MSVC:  cl /std:c++20 /experimental:module
//   GCC:   g++ -std=c++20 -fmodules-ts
//   Clang: clang++ -std=c++20 -fmodules
// Build order matters: module interface units must be compiled first.
// ====================================================================

// ====== File: math_types.cppm (module partition) ======
// Module partition for shared types

export module math_lib:types;

export namespace math {

struct Vec2 {
    double x = 0, y = 0;

    Vec2 operator+(const Vec2& other) const { return {x + other.x, y + other.y}; }
    Vec2 operator-(const Vec2& other) const { return {x - other.x, y - other.y}; }
    Vec2 operator*(double s) const { return {x * s, y * s}; }
    double dot(const Vec2& other) const { return x * other.x + y * other.y; }
    double length() const;  // defined in implementation unit
};

struct Vec3 {
    double x = 0, y = 0, z = 0;

    Vec3 operator+(const Vec3& o) const { return {x+o.x, y+o.y, z+o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x-o.x, y-o.y, z-o.z}; }
    Vec3 operator*(double s) const { return {x*s, y*s, z*s}; }
    double dot(const Vec3& o) const { return x*o.x + y*o.y + z*o.z; }
    Vec3 cross(const Vec3& o) const;
    double length() const;
};

}  // namespace math


// ====== File: math_geometry.cppm (module partition) ======
// Geometry functions partition

export module math_lib:geometry;
import :types;  // import the types partition

export namespace math::geometry {

double distance(const Vec2& a, const Vec2& b);
double triangleArea(const Vec2& a, const Vec2& b, const Vec2& c);
bool pointInCircle(const Vec2& point, const Vec2& center, double radius);

// Shapes
struct Circle {
    Vec2 center;
    double radius;
    double area() const;
    double circumference() const;
    bool contains(const Vec2& point) const;
};

struct AABB {
    Vec2 min, max;
    bool contains(const Vec2& point) const;
    bool intersects(const AABB& other) const;
    double area() const;
};

}  // namespace math::geometry


// ====== File: math_linalg.cppm (module partition) ======
// Linear algebra partition

export module math_lib:linalg;
import :types;

export namespace math::linalg {

struct Mat2 {
    double m[2][2] = {{1,0},{0,1}};  // identity by default

    Vec2 operator*(const Vec2& v) const {
        return {m[0][0]*v.x + m[0][1]*v.y,
                m[1][0]*v.x + m[1][1]*v.y};
    }

    Mat2 operator*(const Mat2& other) const;
    double determinant() const { return m[0][0]*m[1][1] - m[0][1]*m[1][0]; }
    static Mat2 rotation(double radians);
    static Mat2 scale(double sx, double sy);
};

}  // namespace math::linalg


// ====== File: math_lib.cppm (primary module interface) ======
// This is the main module that re-exports all partitions

export module math_lib;

// Re-export all partitions
export import :types;
export import :geometry;
export import :linalg;

// Module-level declarations
export namespace math {
    constexpr double PI = 3.14159265358979323846;
    constexpr double TAU = 2.0 * PI;
    constexpr double DEG_TO_RAD = PI / 180.0;
}


// ====== File: math_lib.cpp (module implementation unit) ======
// Non-exported implementation details

module math_lib;  // no "export" — this is an implementation unit

// Global module fragment for legacy C headers
// module;
// #include <cmath>
// module math_lib;

#include <cmath>

namespace math {

double Vec2::length() const { return std::sqrt(x*x + y*y); }
double Vec3::length() const { return std::sqrt(x*x + y*y + z*z); }
Vec3 Vec3::cross(const Vec3& o) const {
    return {y*o.z - z*o.y, z*o.x - x*o.z, x*o.y - y*o.x};
}

}  // namespace math

namespace math::geometry {

double distance(const Vec2& a, const Vec2& b) {
    return (b - a).length();
}

double triangleArea(const Vec2& a, const Vec2& b, const Vec2& c) {
    return std::abs((b.x-a.x)*(c.y-a.y) - (c.x-a.x)*(b.y-a.y)) / 2.0;
}

bool pointInCircle(const Vec2& point, const Vec2& center, double radius) {
    return distance(point, center) <= radius;
}

double Circle::area() const { return math::PI * radius * radius; }
double Circle::circumference() const { return math::TAU * radius; }
bool Circle::contains(const Vec2& p) const {
    return distance(p, center) <= radius;
}

bool AABB::contains(const Vec2& p) const {
    return p.x >= min.x && p.x <= max.x && p.y >= min.y && p.y <= max.y;
}

bool AABB::intersects(const AABB& other) const {
    return min.x <= other.max.x && max.x >= other.min.x &&
           min.y <= other.max.y && max.y >= other.min.y;
}

double AABB::area() const {
    return (max.x - min.x) * (max.y - min.y);
}

}  // namespace math::geometry

namespace math::linalg {

Mat2 Mat2::operator*(const Mat2& o) const {
    Mat2 r;
    r.m[0][0] = m[0][0]*o.m[0][0] + m[0][1]*o.m[1][0];
    r.m[0][1] = m[0][0]*o.m[0][1] + m[0][1]*o.m[1][1];
    r.m[1][0] = m[1][0]*o.m[0][0] + m[1][1]*o.m[1][0];
    r.m[1][1] = m[1][0]*o.m[0][1] + m[1][1]*o.m[1][1];
    return r;
}

Mat2 Mat2::rotation(double radians) {
    double c = std::cos(radians), s = std::sin(radians);
    Mat2 r;
    r.m[0][0] = c;  r.m[0][1] = -s;
    r.m[1][0] = s;  r.m[1][1] = c;
    return r;
}

Mat2 Mat2::scale(double sx, double sy) {
    Mat2 r;
    r.m[0][0] = sx; r.m[1][1] = sy;
    return r;
}

}  // namespace math::linalg


// ====== File: main.cpp (consumer) ======

// In a real build, this file just does:
//   import math_lib;
// No #include needed. No include guards. No macro pollution.
// For this single-file demo, the above code is conceptually separate files.

#include <iostream>

// Simulating what "import math_lib;" gives us:
using namespace math;
using namespace math::geometry;
using namespace math::linalg;

int main() {
    std::cout << "=== C++20 Modules: math_lib demo ===\n\n";

    // Types partition
    Vec2 a{3, 4};
    std::cout << "Vec2 length: " << a.length() << "\n";

    Vec3 u{1, 0, 0}, v{0, 1, 0};
    auto cross = u.cross(v);
    std::cout << "Cross product: (" << cross.x << "," << cross.y << "," << cross.z << ")\n\n";

    // Geometry partition
    Circle c{{0, 0}, 5};
    std::cout << "Circle area: " << c.area() << "\n";
    std::cout << "Contains (3,4): " << c.contains({3, 4}) << "\n";
    std::cout << "Contains (4,4): " << c.contains({4, 4}) << "\n";

    AABB box{{0, 0}, {10, 10}};
    AABB box2{{5, 5}, {15, 15}};
    std::cout << "\nAABB area: " << box.area() << "\n";
    std::cout << "Boxes intersect: " << box.intersects(box2) << "\n";

    std::cout << "\nTriangle area: "
              << triangleArea({0,0}, {4,0}, {0,3}) << "\n";

    // Linear algebra partition
    auto rot = Mat2::rotation(math::PI / 4);  // 45 degrees
    Vec2 point{1, 0};
    auto rotated = rot * point;
    std::cout << "\nRotated (1,0) by 45deg: ("
              << rotated.x << ", " << rotated.y << ")\n";

    auto transform = Mat2::rotation(math::PI / 2) * Mat2::scale(2, 2);
    auto result = transform * Vec2{1, 0};
    std::cout << "Scale 2x then rotate 90deg: ("
              << result.x << ", " << result.y << ")\n";

    return 0;
}

/*
=== Headers vs Modules: Key Differences ===

Headers (#include):                     Modules (import):
- Textual inclusion (copy-paste)        - Compiled once, binary interface
- Include guards needed                 - No guards needed
- Macros leak between files             - No macro leakage
- Order of #includes can matter         - Import order doesn't matter
- Recompiled in every TU               - Compiled once, cached
- All symbols visible                  - Only exported symbols visible
- Slow builds (redundant parsing)      - Fast builds (no re-parsing)

Module partitions (:types, :geometry) let you split a module
into logical sections while presenting a unified import to consumers.

The global module fragment (module; #include <legacy.h> export module X;)
bridges legacy headers into the module world.
*/
```

Modules solve the fundamental scalability problem of C++ builds: headers are textually copied into every translation unit that includes them, leading to redundant parsing. A module is compiled once into a binary module interface (BMI), and importing it is essentially loading pre-parsed AST data — orders of magnitude faster. Non-exported symbols in a module are completely invisible to consumers, providing true encapsulation that headers cannot achieve.'''),
]
