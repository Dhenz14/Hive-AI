"""Probe Library: 60 domain probes (10 per domain) for regression evaluation.

Each probe tests a specific coding concept with expected keywords.
Probes are scored via keyword coverage (70%) + structural quality (30%).

Domain coverage:
  - Python (10): decorators, async, metaclass, generators, context managers,
                 dataclasses, typing, pathlib, itertools, walrus
  - Rust (10):   ownership, tokio, traits, lifetimes, error handling,
                 pattern matching, concurrency, serde, macros, unsafe
  - Go (10):     workers, interfaces, channels, context, errors,
                 goroutine leaks, table tests, embedding, sync.Pool, generics
  - C++ (10):    RAII, variadic templates, move semantics, const correctness,
                 concepts, lambdas, optional/variant, CRTP, constexpr, coroutines
  - JS/TS (10):  event loop, promises, generics, closures, WeakMap,
                 proxy, async iterators, modules, mapped types, decorators
  - Hive (10):   custom_json, resource credits, key hierarchy, witness voting,
                 HBD, account authority, vesting, proposals, DHF, multi-sig
"""

from dataclasses import dataclass


@dataclass
class Probe:
    domain: str
    prompt: str
    expected_keywords: list
    id: str = ""          # Unique identifier for tracking
    difficulty: str = "medium"  # easy/medium/hard — hard probes used for mid-training checks


# ============================================================================
# Python probes (10)
# ============================================================================
PYTHON_PROBES = [
    # --- Original 3 ---
    Probe("python",
          "Show how to write a Python decorator that adds both pre-call and "
          "post-call hooks, preserving the original function's signature via "
          "functools.wraps. Demonstrate with a timing decorator.",
          ["functools", "wraps", "wrapper", "def", "time", "args", "kwargs"],
          id="py-decorators", difficulty="medium"),
    Probe("python",
          "Write a Python async generator that reads chunks from an aiohttp "
          "response stream and yields parsed JSON objects as they arrive, "
          "handling partial chunks across boundaries.",
          ["async", "yield", "aiohttp", "json", "chunk", "await", "buffer"],
          id="py-async-gen", difficulty="hard"),
    Probe("python",
          "Implement a Python metaclass that automatically registers all "
          "subclasses of a base class into a registry dict, keyed by a "
          "'name' class attribute. Show how to look up classes by name.",
          ["metaclass", "__init_subclass__", "registry", "class", "name", "dict"],
          id="py-metaclass", difficulty="hard"),

    # --- New 7 ---
    Probe("python",
          "Compare Python list comprehensions vs generator expressions for "
          "processing large datasets. Show memory differences, when to use each, "
          "and demonstrate chaining generators with itertools for lazy pipelines.",
          ["comprehension", "generator", "yield", "memory", "itertools", "lazy", "next"],
          id="py-generators", difficulty="medium"),
    Probe("python",
          "Write a Python context manager using both the class-based approach "
          "(__enter__/__exit__) and the contextlib.contextmanager decorator approach. "
          "Show error handling, cleanup guarantees, and nested context managers.",
          ["__enter__", "__exit__", "contextmanager", "contextlib", "with", "yield", "finally"],
          id="py-context-mgr", difficulty="medium"),
    Probe("python",
          "Demonstrate Python dataclasses: create a nested dataclass hierarchy with "
          "default_factory, frozen instances, __post_init__ validation, field metadata, "
          "and conversion to/from dict using asdict. Compare with NamedTuple.",
          ["dataclass", "field", "default_factory", "frozen", "__post_init__", "asdict", "NamedTuple"],
          id="py-dataclasses", difficulty="medium"),
    Probe("python",
          "Show advanced Python typing: write a generic class with TypeVar, use "
          "Protocol for structural subtyping, demonstrate ParamSpec for decorator "
          "type safety, and show Literal types for constrained values.",
          ["TypeVar", "Generic", "Protocol", "ParamSpec", "Literal", "typing", "overload"],
          id="py-typing", difficulty="hard"),
    Probe("python",
          "Demonstrate pathlib for file operations: recursive glob, path joining, "
          "reading/writing with encoding, checking existence, getting relative paths, "
          "and comparing with os.path. Show Path objects in a real file processing task.",
          ["pathlib", "Path", "glob", "read_text", "write_text", "exists", "relative_to"],
          id="py-pathlib", difficulty="easy"),
    Probe("python",
          "Show practical itertools patterns: groupby with a key function, chain.from_iterable "
          "for flattening, product for combinatorics, islice for lazy slicing, "
          "accumulate for running totals, and zip_longest for uneven sequences.",
          ["itertools", "groupby", "chain", "product", "islice", "accumulate", "zip_longest"],
          id="py-itertools", difficulty="medium"),
    Probe("python",
          "Explain the Python walrus operator (:=) with practical examples: in while loops "
          "for reading input, in list comprehensions for avoiding duplicate computation, "
          "in if statements for pattern matching, and demonstrate where it improves readability.",
          ["walrus", ":=", "while", "comprehension", "assignment", "if", "expression"],
          id="py-walrus", difficulty="easy"),
]

# ============================================================================
# Rust probes (10)
# ============================================================================
RUST_PROBES = [
    # --- Original 3 ---
    Probe("rust",
          "Explain Rust's ownership and borrowing rules with a concrete "
          "example showing how to fix a 'cannot borrow as mutable because "
          "it is also borrowed as immutable' error. Show before and after code.",
          ["borrow", "mut", "&", "let", "fn", "ownership", "lifetime"],
          id="rs-ownership", difficulty="medium"),
    Probe("rust",
          "Write a Rust async function using tokio that spawns multiple tasks, "
          "each making an HTTP request, then collects all results using "
          "JoinSet. Handle individual task failures without cancelling others.",
          ["tokio", "async", "spawn", "JoinSet", "await", "Result", "Error"],
          id="rs-tokio", difficulty="hard"),
    Probe("rust",
          "Compare trait objects (dyn Trait) vs generics (impl Trait / <T: Trait>) "
          "in Rust. When would you choose dynamic dispatch over static dispatch? "
          "Show a concrete example where trait objects are necessary.",
          ["dyn", "impl", "Trait", "dispatch", "vtable", "Box", "generic"],
          id="rs-traits", difficulty="medium"),

    # --- New 7 ---
    Probe("rust",
          "Demonstrate Rust lifetimes in structs: write a struct that holds "
          "references with explicit lifetime parameters. Show how lifetime "
          "elision works in methods, and demonstrate a case where the compiler "
          "cannot infer lifetimes and explicit annotation is required.",
          ["lifetime", "'a", "struct", "impl", "fn", "reference", "elision"],
          id="rs-lifetimes", difficulty="hard"),
    Probe("rust",
          "Show comprehensive Rust error handling: define custom error types "
          "with thiserror, chain errors with anyhow, use the ? operator for "
          "propagation, and demonstrate Result/Option combinators (map, and_then, "
          "unwrap_or_else). Show From trait for error conversion.",
          ["Result", "Option", "thiserror", "anyhow", "From", "map", "and_then"],
          id="rs-errors", difficulty="medium"),
    Probe("rust",
          "Write Rust pattern matching examples: match on enums with data, "
          "use if-let and while-let, demonstrate destructuring in match arms, "
          "show matches! macro, use @ bindings, and demonstrate exhaustive "
          "matching with the compiler enforcing all variants are covered.",
          ["match", "enum", "if let", "while let", "pattern", "destructur", "arm"],
          id="rs-patterns", difficulty="medium"),
    Probe("rust",
          "Demonstrate Rust concurrency with Arc<Mutex<T>>: write a multi-threaded "
          "counter, show deadlock prevention patterns, compare Mutex vs RwLock, "
          "and demonstrate channel-based communication with mpsc. Show when to "
          "use atomic types instead of Mutex.",
          ["Arc", "Mutex", "RwLock", "mpsc", "thread", "atomic", "lock"],
          id="rs-concurrency", difficulty="hard"),
    Probe("rust",
          "Show serde serialization in Rust: derive Serialize/Deserialize for "
          "nested structs, use serde attributes (rename, skip, default, flatten), "
          "implement custom serialization for a type, and demonstrate "
          "serde_json for parsing and generating JSON.",
          ["serde", "Serialize", "Deserialize", "serde_json", "rename", "derive", "json"],
          id="rs-serde", difficulty="medium"),
    Probe("rust",
          "Write Rust declarative macros with macro_rules!: show repetition "
          "patterns ($(...)*), fragment specifiers (expr, ident, ty, tt), "
          "recursive macro expansion, and a practical example like a hashmap! "
          "literal macro. Explain hygiene rules.",
          ["macro_rules", "macro", "expr", "ident", "repetit", "hygiene", "token"],
          id="rs-macros", difficulty="hard"),
    Probe("rust",
          "Explain Rust unsafe blocks: when and why unsafe is needed, the five "
          "unsafe superpowers (raw pointers, unsafe functions, mutable statics, "
          "unsafe traits, union fields). Write a safe abstraction around unsafe "
          "code and explain how to minimize the unsafe surface area.",
          ["unsafe", "raw pointer", "deref", "static mut", "FFI", "abstraction", "invariant"],
          id="rs-unsafe", difficulty="hard"),
]

# ============================================================================
# Go probes (10)
# ============================================================================
GO_PROBES = [
    # --- Original 3 ---
    Probe("go",
          "Implement a Go worker pool pattern with a configurable number of "
          "workers, a job channel, and a results channel. Include graceful "
          "shutdown via context.Context cancellation.",
          ["goroutine", "chan", "context", "WaitGroup", "func", "select", "worker"],
          id="go-workers", difficulty="medium"),
    Probe("go",
          "Show how Go interface composition works by defining small interfaces "
          "(Reader, Writer) and composing them into a ReadWriter. Demonstrate "
          "how a concrete type satisfies the composed interface implicitly.",
          ["interface", "Reader", "Writer", "func", "struct", "Read", "Write"],
          id="go-interfaces", difficulty="medium"),
    Probe("go",
          "Write a Go function that uses select with multiple channels: a data "
          "channel, a done channel, and a time.After timeout. Handle all three "
          "cases and explain the non-deterministic selection behavior.",
          ["select", "case", "chan", "time.After", "done", "func", "default"],
          id="go-channels", difficulty="medium"),

    # --- New 7 ---
    Probe("go",
          "Demonstrate Go context propagation: pass context through an HTTP "
          "handler → service → database call chain. Show context.WithTimeout, "
          "context.WithCancel, and context.WithValue. Explain when to use each "
          "and how cancellation propagates through the call tree.",
          ["context", "WithTimeout", "WithCancel", "WithValue", "Done", "ctx", "Err"],
          id="go-context", difficulty="hard"),
    Probe("go",
          "Show Go error wrapping and unwrapping: use fmt.Errorf with %w, "
          "errors.Is and errors.As for matching, implement the error interface "
          "for custom types with Unwrap(), and demonstrate sentinel errors "
          "vs typed errors. Show a middleware-style error handling pattern.",
          ["error", "fmt.Errorf", "errors.Is", "errors.As", "Unwrap", "wrap", "sentinel"],
          id="go-errors", difficulty="medium"),
    Probe("go",
          "Write Go code that prevents goroutine leaks: show a leaking example "
          "(blocked goroutine on unbuffered channel), then fix it with context "
          "cancellation. Demonstrate the 'done channel' pattern and explain "
          "how to use runtime.NumGoroutine() to detect leaks in tests.",
          ["goroutine", "leak", "context", "cancel", "done", "runtime", "NumGoroutine"],
          id="go-leak-prevention", difficulty="hard"),
    Probe("go",
          "Implement table-driven tests in Go: write a test function with a "
          "slice of test cases (name, input, expected), use t.Run for subtests, "
          "show t.Parallel() for concurrent test execution, demonstrate test "
          "helpers with t.Helper(), and mock dependencies using interfaces.",
          ["t.Run", "testing", "test", "table", "Parallel", "Helper", "struct"],
          id="go-table-tests", difficulty="medium"),
    Probe("go",
          "Compare Go struct embedding vs traditional inheritance: show how "
          "embedding provides method forwarding, demonstrate method overriding "
          "on the outer struct, explain the difference from inheritance (no "
          "polymorphism via embedding), and show when to use interfaces instead.",
          ["embed", "struct", "interface", "method", "override", "composition", "promoted"],
          id="go-embedding", difficulty="medium"),
    Probe("go",
          "Demonstrate sync.Pool in Go for reducing GC pressure: show how to "
          "create a pool with New function, Get and Put objects, and benchmark "
          "the performance difference. Explain when sync.Pool helps (high-allocation "
          "hot paths) and when it hurts (small objects, low contention).",
          ["sync.Pool", "New", "Get", "Put", "GC", "benchmark", "alloc"],
          id="go-sync-pool", difficulty="hard"),
    Probe("go",
          "Write Go generic functions and types: define a generic Map function "
          "over slices, create a generic Set type with constraints, use the "
          "comparable constraint, show type inference, and demonstrate when "
          "generics are better than interface{}/any and when they're not.",
          ["generic", "any", "comparable", "constraint", "type", "func", "interface"],
          id="go-generics", difficulty="medium"),
]

# ============================================================================
# C++ probes (10)
# ============================================================================
CPP_PROBES = [
    # --- Original 3 ---
    Probe("cpp",
          "Explain RAII in C++ and demonstrate the differences between "
          "unique_ptr, shared_ptr, and weak_ptr. Show a concrete example "
          "where weak_ptr prevents a circular reference memory leak.",
          ["unique_ptr", "shared_ptr", "weak_ptr", "RAII", "destructor", "lock", "cycle"],
          id="cpp-raii", difficulty="medium"),
    Probe("cpp",
          "Write a C++ variadic template function that pretty-prints any "
          "number of arguments with their types (using typeid or "
          "if-constexpr). Show fold expressions and parameter pack expansion.",
          ["template", "typename", "Args", "fold", "constexpr", "pack", "variadic"],
          id="cpp-variadic", difficulty="hard"),
    Probe("cpp",
          "Explain C++ move semantics: what is an rvalue reference (&&), when "
          "does the compiler invoke the move constructor vs copy constructor, "
          "and write a class with both. Show std::move usage.",
          ["move", "&&", "rvalue", "std::move", "constructor", "noexcept", "swap"],
          id="cpp-move", difficulty="medium"),

    # --- New 7 ---
    Probe("cpp",
          "Demonstrate C++ const correctness: const member functions, const "
          "references, const pointers vs pointer to const, constexpr vs const, "
          "mutable keyword for logical constness, and east-const vs west-const "
          "style. Show how const propagates through function calls.",
          ["const", "mutable", "constexpr", "reference", "pointer", "member", "function"],
          id="cpp-const", difficulty="medium"),
    Probe("cpp",
          "Compare C++20 concepts with SFINAE and enable_if: write a concept "
          "that constrains a template parameter (e.g., Sortable, Printable), "
          "use requires clauses, show compound requirements, and demonstrate "
          "how concepts improve error messages over SFINAE.",
          ["concept", "requires", "enable_if", "SFINAE", "template", "constraint", "auto"],
          id="cpp-concepts", difficulty="hard"),
    Probe("cpp",
          "Show C++ lambda capture modes: capture by value [=], by reference [&], "
          "individual captures, init captures (C++14), mutable lambdas, generic "
          "lambdas (auto parameters), and demonstrate storing lambdas in "
          "std::function. Show a practical callback pattern.",
          ["lambda", "capture", "mutable", "auto", "std::function", "callback", "closure"],
          id="cpp-lambdas", difficulty="medium"),
    Probe("cpp",
          "Demonstrate std::optional and std::variant in C++17: use optional "
          "for nullable returns, show value_or and transform, use variant as "
          "a type-safe union with std::visit, pattern matching with overloaded "
          "visitors, and compare with traditional inheritance hierarchies.",
          ["optional", "variant", "visit", "value_or", "holds_alternative", "get", "monostate"],
          id="cpp-optional-variant", difficulty="medium"),
    Probe("cpp",
          "Explain the Curiously Recurring Template Pattern (CRTP) in C++: "
          "show static polymorphism, write a CRTP base that adds operator== "
          "and a mixin that adds serialization. Compare CRTP dispatch cost "
          "vs virtual function dispatch. Show practical use cases.",
          ["CRTP", "template", "static", "polymorphism", "virtual", "Derived", "Base"],
          id="cpp-crtp", difficulty="hard"),
    Probe("cpp",
          "Show constexpr programming in C++: constexpr functions, constexpr if, "
          "consteval (C++20), constinit (C++20), compile-time string processing, "
          "and constexpr containers. Demonstrate computing a value at compile time "
          "vs runtime and show how to verify constexpr evaluation.",
          ["constexpr", "consteval", "constinit", "compile", "template", "static_assert", "literal"],
          id="cpp-constexpr", difficulty="hard"),
    Probe("cpp",
          "Write C++20 coroutines: implement a simple generator that yields "
          "values using co_yield, show the promise_type requirements, explain "
          "co_await and co_return, and demonstrate a lazy range generator. "
          "Compare with Python generators and Rust async.",
          ["co_yield", "co_await", "co_return", "promise_type", "coroutine", "generator", "suspend"],
          id="cpp-coroutines", difficulty="hard"),
]

# ============================================================================
# JavaScript/TypeScript probes (10)
# ============================================================================
JS_PROBES = [
    # --- Original 3 ---
    Probe("js",
          "Explain the JavaScript event loop in detail: call stack, task queue, "
          "microtask queue, and how setTimeout(fn, 0) interacts with "
          "Promise.resolve().then(). Show the execution order of a tricky example.",
          ["event loop", "microtask", "setTimeout", "Promise", "stack", "queue", "then"],
          id="js-event-loop", difficulty="hard"),
    Probe("js",
          "Write a JavaScript function that chains promises to: fetch a user, "
          "fetch their posts, then fetch comments for the first post. Handle "
          "errors at each stage with proper .catch() placement. Then rewrite "
          "using async/await with try/catch.",
          ["Promise", "then", "catch", "async", "await", "fetch", "try"],
          id="js-promises", difficulty="medium"),
    Probe("js",
          "Write a TypeScript generic function `pipe` that composes N functions "
          "in sequence, where each function's output type matches the next "
          "function's input type. The final type should be inferred correctly.",
          ["generic", "function", "pipe", "type", "infer", "return", "extends"],
          id="js-generics", difficulty="hard"),

    # --- New 7 ---
    Probe("js",
          "Explain JavaScript closures and scope chain: demonstrate lexical "
          "scoping, show a closure that creates private state (module pattern), "
          "explain the classic loop-var-in-closure bug with var vs let, and "
          "show how closures enable partial application and currying.",
          ["closure", "scope", "lexical", "var", "let", "private", "function"],
          id="js-closures", difficulty="medium"),
    Probe("js",
          "Demonstrate WeakMap and WeakSet in JavaScript: explain weak references "
          "and garbage collection implications, show practical use cases "
          "(private data, DOM metadata, caching), compare with Map/Set, and "
          "demonstrate why WeakMap keys must be objects.",
          ["WeakMap", "WeakSet", "garbage", "reference", "Map", "object", "key"],
          id="js-weakmap", difficulty="medium"),
    Probe("js",
          "Write JavaScript Proxy and Reflect examples: create a validation "
          "proxy that type-checks property assignments, implement a logging "
          "proxy for method calls, show Reflect.get/set/apply, and demonstrate "
          "a reactive data binding system using Proxy traps.",
          ["Proxy", "Reflect", "handler", "trap", "get", "set", "target"],
          id="js-proxy", difficulty="hard"),
    Probe("js",
          "Demonstrate async iterators in JavaScript: implement Symbol.asyncIterator "
          "on a custom class, use for-await-of loops, create an async generator "
          "that paginates through an API, and show how to handle backpressure "
          "and cancellation in async iteration.",
          ["async", "iterator", "Symbol.asyncIterator", "for await", "yield", "generator", "next"],
          id="js-async-iter", difficulty="hard"),
    Probe("js",
          "Show JavaScript module patterns: compare CommonJS (require/module.exports) "
          "vs ES modules (import/export), demonstrate named vs default exports, "
          "dynamic imports with import(), tree shaking implications, and the "
          "module resolution algorithm for Node.js.",
          ["import", "export", "require", "module", "default", "dynamic", "tree"],
          id="js-modules", difficulty="medium"),
    Probe("js",
          "Write TypeScript mapped types: demonstrate Record, Partial, Required, "
          "Pick, Omit. Create custom mapped types using keyof and in. Show "
          "conditional types with extends/infer, template literal types, and "
          "demonstrate how to make deeply nested Partial (DeepPartial).",
          ["Record", "Partial", "keyof", "extends", "infer", "mapped", "conditional"],
          id="js-mapped-types", difficulty="hard"),
    Probe("js",
          "Implement the decorator pattern in TypeScript: write method decorators "
          "for logging and memoization, class decorators for singleton pattern, "
          "property decorators for validation. Show both TC39 stage 3 syntax "
          "and the legacy experimentalDecorators approach.",
          ["decorator", "class", "method", "memoiz", "singleton", "metadata", "target"],
          id="js-decorators", difficulty="medium"),
]

# ============================================================================
# Hive blockchain probes (10)
# ============================================================================
HIVE_PROBES = [
    # --- Original 3 ---
    Probe("hive",
          "Write a Python function using the beem library that broadcasts a "
          "custom_json operation to the Hive blockchain for a Hive Engine token "
          "transfer. Use the ssc-mainnet-hive id and posting authority.",
          ["custom_json", "beem", "posting", "ssc-mainnet-hive", "broadcast", "json", "Hive"],
          id="hive-custom-json", difficulty="medium"),
    Probe("hive",
          "Explain Hive blockchain resource credits (RC): what they are, how "
          "they regenerate, how they limit operations, and write Python code "
          "using beem to check an account's current RC percentage.",
          ["resource", "credit", "RC", "mana", "regenerat", "beem", "account"],
          id="hive-rc", difficulty="medium"),
    Probe("hive",
          "Explain the Hive key hierarchy: owner, active, posting, and memo "
          "keys. What operations does each authorize? Write a Python function "
          "using beem that derives all four keys from a master password.",
          ["owner", "active", "posting", "memo", "key", "beem", "password"],
          id="hive-keys", difficulty="medium"),

    # --- New 7 ---
    Probe("hive",
          "Explain the Hive witness voting system: how witnesses are elected, "
          "the top 20 consensus witnesses vs backup witnesses, witness scheduling, "
          "price feed publishing, and write Python code using beem to vote for "
          "a witness and list the current top witnesses.",
          ["witness", "vote", "top", "schedule", "price_feed", "beem", "consensus"],
          id="hive-witnesses", difficulty="medium"),
    Probe("hive",
          "Explain Hive Backed Dollars (HBD): the stabilization mechanism, "
          "the debt ratio limit, HBD savings with 20% APR interest, conversion "
          "operations (convert and collateralized_convert), and write Python "
          "code to check HBD supply and initiate a conversion using beem.",
          ["HBD", "stabil", "debt", "interest", "savings", "convert", "beem"],
          id="hive-hbd", difficulty="hard"),
    Probe("hive",
          "Explain Hive account authority system: multi-authority transactions, "
          "weight thresholds, how account_update changes authorities, and "
          "the difference between account authority vs key authority. Write "
          "Python code using beem to inspect an account's authority structure.",
          ["authority", "weight", "threshold", "account_update", "key", "beem", "active"],
          id="hive-authority", difficulty="hard"),
    Probe("hive",
          "Explain Hive vesting (HIVE Power): the vesting-to-HIVE conversion "
          "process (power down), the 13-week schedule, delegations, how voting "
          "power relates to vesting shares. Write Python code using beem to "
          "check vesting shares and initiate a power down.",
          ["vesting", "power_down", "delegation", "HIVE", "shares", "beem", "withdraw"],
          id="hive-vesting", difficulty="medium"),
    Probe("hive",
          "Explain the Hive proposal system (Decentralized Hive Fund): how "
          "proposals are created with create_proposal, how stakeholders vote "
          "with update_proposal_votes, the daily pay mechanism, the return "
          "proposal, and write Python code using beem to list active proposals.",
          ["proposal", "DHF", "create_proposal", "vote", "daily_pay", "beem", "fund"],
          id="hive-proposals", difficulty="medium"),
    Probe("hive",
          "Explain how the Decentralized Hive Fund (DHF) allocates funding: "
          "the return proposal threshold, how proposals above the return "
          "proposal get funded proportionally, the total daily budget, and "
          "write Python code using beem to check the DHF balance and current "
          "funded proposals.",
          ["DHF", "fund", "return_proposal", "budget", "threshold", "beem", "balance"],
          id="hive-dhf", difficulty="hard"),
    Probe("hive",
          "Show how to implement multi-signature operations on Hive: set up "
          "an account with multi-sig authority requiring 2-of-3 keys, explain "
          "how to partially sign and broadcast multi-sig transactions using "
          "beem, and demonstrate the authority weight threshold system.",
          ["multi", "signature", "authority", "weight", "threshold", "sign", "beem"],
          id="hive-multisig", difficulty="hard"),
]


# ============================================================================
# Combined probe list
# ============================================================================
ALL_PROBES = PYTHON_PROBES + RUST_PROBES + GO_PROBES + CPP_PROBES + JS_PROBES + HIVE_PROBES

# Quick-check probes: 1 hardest per domain for mid-training regression detection
QUICK_PROBES = [p for p in ALL_PROBES if p.id in (
    "py-async-gen",       # Python — hardest
    "rs-tokio",           # Rust — hardest
    "go-context",         # Go — hardest
    "cpp-concepts",       # C++ — hardest
    "js-event-loop",      # JS — hardest
    "hive-hbd",           # Hive — hardest
)]

# Domain list
DOMAINS = ["python", "rust", "go", "cpp", "js", "hive"]


def get_probes_by_domain(domain: str) -> list:
    """Get all probes for a specific domain."""
    return [p for p in ALL_PROBES if p.domain == domain]


def get_probe_by_id(probe_id: str) -> Probe:
    """Get a specific probe by its ID."""
    for p in ALL_PROBES:
        if p.id == probe_id:
            return p
    raise ValueError(f"Unknown probe ID: {probe_id}")
