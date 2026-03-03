"""
hiveai/lora/distiller.py

Self-distillation: use Qwen3 to generate its own coding training pairs.
The model already knows Python internals, algorithms, design patterns better
than most web pages. We extract that knowledge as (instruction, response) pairs
before any web crawling happens.

Run: POST /api/lora/distill {"topics": ["python concurrency"], "pairs_per_topic": 10}
"""
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates — 6 patterns that surface different kinds of coding knowledge
# ---------------------------------------------------------------------------
TEMPLATES = [
    (
        "implement",
        "Implement {concept} in Python. Show the complete approach, explain the reasoning "
        "step by step, cover edge cases, and include at least 3 working code examples "
        "ranging from basic to production-ready.",
    ),
    (
        "correct_way",
        "What is the correct way to handle {concept} in Python? "
        "Show at least 2 working code examples: the correct approach and the common wrong "
        "approach side by side. Explain why the correct approach is preferred, what bugs "
        "the wrong approach causes, and when edge cases change the answer.",
    ),
    (
        "why_exists",
        "Explain why {concept} exists in software engineering. "
        "What problem does it solve? When should you use it? When should you NOT use it? "
        "Show at least 3 concrete code examples: the problem without it, the solution with it, "
        "and a real-world usage pattern.",
    ),
    (
        "mistakes",
        "What are the top 5 mistakes developers make with {concept}? "
        "For each mistake: show the wrong code, show the correct code, explain why it matters, "
        "and describe what symptom or bug the wrong code causes in production.",
    ),
    (
        "internals",
        "Explain how {concept} works under the hood in Python. "
        "What does CPython actually do? What are the memory and performance implications? "
        "Show at least 3 code examples demonstrating the internal behavior, including "
        "a benchmark or measurement that proves your explanation.",
    ),
    (
        "compare",
        "Compare all major approaches to {concept} in Python. "
        "For each approach show a complete working code example, then give a concrete "
        "decision framework: under what conditions (data size, team size, latency requirements, "
        "etc.) would you choose each one? Include a summary table.",
    ),
    (
        "test_driven",
        "You are implementing {concept} using strict Test-Driven Development.\n\n"
        "Follow this exact TDD cycle:\n"
        "1. **Red**: Write a comprehensive test suite FIRST. Include at least 8 test cases "
        "covering: happy path, edge cases, error conditions, boundary values, and performance "
        "constraints. Use pytest with fixtures and parametrize where appropriate.\n"
        "2. **Green**: Write the minimal implementation that makes ALL tests pass. Show the "
        "complete implementation with type hints.\n"
        "3. **Refactor**: Improve the implementation for clarity, performance, and maintainability "
        "while keeping all tests green. Show the refactored version.\n\n"
        "Show complete runnable code at each step. Tests must be copy-pasteable and pass with pytest.",
    ),
    (
        "refactor",
        "You are given this messy, poorly-structured implementation of {concept}:\n\n"
        "Write a realistic but problematic version first (code smells: long functions, "
        "no error handling, magic numbers, poor naming, duplicated logic, no types).\n\n"
        "Then refactor it step by step:\n"
        "1. **Identify smells**: List every code smell with line references.\n"
        "2. **Extract and rename**: Break long functions into focused ones with clear names.\n"
        "3. **Add safety**: Error handling, input validation, type hints.\n"
        "4. **Add tests**: Write tests that verify the refactored version behaves identically.\n"
        "5. **Final version**: Show the complete, clean, production-ready code.\n\n"
        "Both the messy and clean versions must be complete and runnable. "
        "Explain each refactoring decision and what it prevents.",
    ),
    (
        "debug_fix",
        "A developer has a bug with {concept} in their Python code.\n\n"
        "Create a realistic buggy implementation (not a toy example — something that would "
        "appear in a real codebase). The bug should be subtle: it passes basic tests but "
        "fails under specific conditions.\n\n"
        "Show the complete debugging process:\n"
        "1. **Buggy code**: The full implementation with the subtle bug.\n"
        "2. **Symptom**: What the developer sees (error message, wrong output, or silent corruption).\n"
        "3. **Diagnosis**: Add strategic logging/assertions to isolate the bug. Show the diagnostic code.\n"
        "4. **Root cause**: Explain exactly why the bug occurs (memory layout, execution order, "
        "type coercion, etc.).\n"
        "5. **Fix**: The corrected code with a comment explaining the fix.\n"
        "6. **Regression test**: A test that catches this exact bug to prevent recurrence.\n\n"
        "All code must be complete and runnable.",
    ),
    (
        "inverse_instruct",
        "Here is a well-written, production-quality Python implementation related to {concept}.\n\n"
        "First, write the complete implementation (200+ lines, with proper structure, error handling, "
        "type hints, and docstrings). Make it realistic and sophisticated.\n\n"
        "Then generate 5 DIFFERENT instruction prompts that would lead to this SAME code:\n"
        "1. A beginner-friendly request (simple language, explains what they need)\n"
        "2. A senior engineer's terse request (technical, assumes context)\n"
        "3. A bug report that the code would fix\n"
        "4. A code review request asking to improve an inferior version\n"
        "5. A system design question where this code is the answer\n\n"
        "For each instruction, explain why it maps to this implementation and what nuances "
        "a good AI coding assistant would need to infer.",
    ),
]

# ---------------------------------------------------------------------------
# o1-STYLE REASONING TEMPLATES — deeper patterns inspired by chain-of-thought,
# self-reflection, and multi-step verification techniques.
# These produce higher-quality pairs that teach the model HOW to think,
# not just WHAT to know.
# ---------------------------------------------------------------------------
O1_TEMPLATES = [
    (
        "reflect_and_revise",
        "I need to solve a complex problem involving {concept} in Python.\n\n"
        "Follow this exact reasoning process:\n"
        "**Step 1 — Initial Analysis**: Break down the problem. What are the core challenges?\n"
        "**Step 2 — First Attempt**: Write a complete initial solution with code.\n"
        "**Step 3 — Self-Critique**: Review your own solution critically. What are the flaws? "
        "What edge cases did you miss? What would break under load or with unexpected input?\n"
        "**Step 4 — Revised Solution**: Write an improved version that addresses every flaw "
        "you identified. Explain each change and why it matters.\n"
        "**Step 5 — Verification**: Prove your revised solution is correct with test cases "
        "covering normal operation, edge cases, and error conditions.\n\n"
        "Show complete working code at each step. The revision must be meaningfully better "
        "than the first attempt.",
    ),
    (
        "debug_reasoning",
        "A developer shows you this situation with {concept} in Python:\n\n"
        "Their code appears to work in development but fails in production. Walk through "
        "the complete debugging reasoning process:\n\n"
        "1. **Hypothesis Generation**: List the top 5 most likely root causes, ranked by probability. "
        "For each, explain WHY it's likely and what evidence would confirm or rule it out.\n"
        "2. **Diagnostic Code**: Write instrumentation code that would isolate each hypothesis "
        "(logging, assertions, timing, memory profiling).\n"
        "3. **Root Cause Analysis**: For the most common root cause, show the buggy code, "
        "explain the exact mechanism of failure (step by step, what happens in memory/CPU), "
        "and show the fix.\n"
        "4. **Prevention**: How would you prevent this class of bug in the future? "
        "Show defensive coding patterns, testing strategies, and CI checks.\n\n"
        "Include at least 4 complete code examples.",
    ),
    (
        "adversarial_review",
        "You are reviewing a pull request that implements {concept} in Python.\n\n"
        "The implementation looks correct at first glance. Your job is to find the subtle bugs, "
        "performance issues, and design flaws that most reviewers would miss.\n\n"
        "Structure your review:\n"
        "1. **What looks correct**: Acknowledge the good parts (briefly).\n"
        "2. **Subtle bug #1**: Show the exact scenario where it fails. Include a reproduction "
        "test case with code.\n"
        "3. **Subtle bug #2**: A different failure mode. Show the triggering condition.\n"
        "4. **Performance trap**: Where does this implementation degrade unexpectedly? "
        "Show a benchmark proving it.\n"
        "5. **Design alternative**: Propose a fundamentally better approach. Show complete code "
        "and explain why it's architecturally superior.\n\n"
        "Write realistic code examples — not toy examples. Each bug should be something a "
        "senior engineer would catch that a junior would miss.",
    ),
    (
        "teach_from_first_principles",
        "Explain {concept} by building it from absolute first principles.\n\n"
        "Imagine the reader knows Python syntax but has never encountered this concept.\n\n"
        "1. **The Problem**: What concrete problem does this solve? Show a painful code example "
        "WITHOUT this concept — make the reader feel the pain.\n"
        "2. **The Insight**: What's the key insight or 'aha moment'? Explain it with an analogy.\n"
        "3. **Building Block by Block**: Implement the concept from scratch in 3-4 progressive "
        "code examples, each building on the last. Each example should add ONE new idea.\n"
        "4. **The Standard Library Way**: Show how Python's standard library provides this "
        "(if applicable). How does it differ from your hand-built version?\n"
        "5. **Expert Usage**: Show a production-quality example that demonstrates mastery. "
        "Include error handling, type hints, and documentation.\n"
        "6. **When NOT to Use It**: Show a case where this concept is the wrong tool. "
        "What should you use instead?\n\n"
        "Every code example must be complete and runnable.",
    ),
    (
        "system_design",
        "Design a production system that relies heavily on {concept}.\n\n"
        "Requirements: The system serves 10,000 requests/day, must handle failures gracefully, "
        "and needs to be maintained by a team of 3 developers.\n\n"
        "**Architecture Decision Record**:\n"
        "1. **Context**: What problem are we solving? What constraints matter?\n"
        "2. **Options Considered**: List 3 different approaches with pros/cons for each.\n"
        "3. **Decision**: Which approach and WHY? Be specific about the deciding factors.\n"
        "4. **Implementation**: Complete working code for the chosen approach, including:\n"
        "   - Core logic with proper abstractions\n"
        "   - Error handling and retry logic\n"
        "   - Monitoring/metrics hooks\n"
        "   - Configuration management\n"
        "5. **Testing Strategy**: Unit tests, integration tests, and a load test sketch.\n"
        "6. **Operational Runbook**: Common failure modes and how to diagnose them.\n\n"
        "Show at least 5 code examples covering the full implementation.",
    ),
    (
        "confidence_analysis",
        "Analyze {concept} in Python with explicit confidence scoring.\n\n"
        "For each claim you make, rate your confidence:\n"
        "- **HIGH (0.9+)**: Documented in official Python docs, widely known\n"
        "- **MEDIUM (0.7-0.9)**: Generally accepted, some edge cases uncertain\n"
        "- **LOW (0.5-0.7)**: Implementation-dependent, version-specific, or debated\n\n"
        "Structure:\n"
        "1. **Core Facts** [HIGH confidence]: The universally true statements about this concept. "
        "Include code proving each fact.\n"
        "2. **Common Beliefs** [MEDIUM confidence]: Things most developers believe that are "
        "MOSTLY true but have exceptions. Show the exceptions with code.\n"
        "3. **Misconceptions** [HIGH confidence that these are WRONG]: Things developers commonly "
        "get wrong. Prove they're wrong with code and measurements.\n"
        "4. **Uncertain Territory** [LOW confidence]: Areas where the answer genuinely depends "
        "on context, Python version, or implementation. Show different outcomes.\n"
        "5. **Synthesis**: A decision framework for practitioners — when does this concept "
        "behave predictably vs. when should you be cautious?\n\n"
        "Every claim must have a code example or benchmark as evidence.",
    ),
]

# ---------------------------------------------------------------------------
# EXPLANATION-FOCUSED TEMPLATES — target the 0.378 explanation quality weakness.
# These force deep "why" reasoning, trade-off analysis, and teaching clarity
# alongside code examples. Models trained on these learn to explain, not just generate.
# ---------------------------------------------------------------------------
EXPLAIN_TEMPLATES = [
    (
        "deep_explanation",
        "Explain in depth: {concept}. Walk through the reasoning step by step. "
        "For each design choice, explain WHY it matters — not just what it does. "
        "Compare trade-offs with concrete benchmarks or measurements. "
        "Include 2+ complete code examples showing the concept in action, "
        "with inline comments explaining every non-obvious line.",
    ),
    (
        "teach_junior",
        "A junior developer asks: 'Can you explain {concept}?'\n\n"
        "Explain it as if teaching someone who knows basic Python but has never "
        "seen this pattern. Structure your explanation:\n"
        "1. **The Problem**: What pain does this solve? Show a concrete example without it.\n"
        "2. **The Analogy**: Compare to something familiar (everyday object, simple system).\n"
        "3. **Basic Example**: The simplest working implementation with every line explained.\n"
        "4. **Intermediate Example**: Add error handling, type hints, and edge case coverage.\n"
        "5. **Production Example**: A real-world usage with logging, testing, and documentation.\n"
        "6. **Common Pitfalls**: What mistakes will they make? Show the wrong way and the right way.\n\n"
        "Every code example must be complete, runnable, and progressively build on the previous one.",
    ),
    (
        "tradeoff_analysis",
        "Compare all major approaches to {concept} in Python.\n\n"
        "For EACH approach:\n"
        "- Show a complete, working code implementation (not pseudocode)\n"
        "- Analyze time complexity (Big-O) and space complexity\n"
        "- Measure actual performance with a benchmark (use timeit or time.perf_counter)\n"
        "- Explain when this approach is the BEST choice and when it's the WORST\n"
        "- List specific conditions: data size thresholds, latency requirements, "
        "team experience, maintainability concerns\n\n"
        "End with a clear decision matrix: given constraint X, choose approach Y.\n"
        "Include at least 3 approaches and a summary comparison table.",
    ),
    (
        "debug_walkthrough",
        "Show a complete debugging session for a realistic bug involving {concept}.\n\n"
        "Structure it as a narrative:\n"
        "1. **The Setup**: Show 50+ lines of realistic code that looks correct at first glance.\n"
        "2. **The Symptom**: What does the developer observe? (Wrong output, crash, silent data corruption)\n"
        "3. **First Hypothesis**: What most developers would guess is wrong — and why that guess is incorrect.\n"
        "4. **Systematic Diagnosis**: Add logging, assertions, and diagnostic code. Show the actual output.\n"
        "5. **The Root Cause**: Explain the exact mechanism — what happens in memory, what order "
        "operations execute in, why Python behaves this way.\n"
        "6. **The Fix**: Corrected code with a comment explaining the fix.\n"
        "7. **The Mental Model**: What understanding prevents this entire class of bugs?\n"
        "8. **Regression Test**: A pytest test that catches this exact bug.\n\n"
        "The bug should be subtle enough that a senior dev might miss it in code review.",
    ),
]

# ---------------------------------------------------------------------------
# C++ TEMPLATES — parallel to Python templates but targeting modern C++ idioms.
# These teach RAII, move semantics, templates, STL, and memory safety.
# Used when distill_batch(language="cpp") is called.
# ---------------------------------------------------------------------------
CPP_TEMPLATES = [
    (
        "implement_cpp",
        "Implement {concept} in modern C++ (C++17 or C++20). Show the complete approach, "
        "explain the reasoning step by step, cover edge cases, and include at least 3 working "
        "code examples ranging from basic to production-ready. Use RAII, smart pointers, "
        "and STL containers/algorithms where appropriate. Include #include directives and "
        "a main() function that demonstrates each example.",
    ),
    (
        "correct_way_cpp",
        "What is the correct way to handle {concept} in C++? "
        "Show at least 2 complete code examples: the modern C++ approach and the common "
        "C-style or legacy approach side by side. Explain why the modern approach is preferred, "
        "what bugs or undefined behavior the wrong approach causes, and when the legacy "
        "approach might still be appropriate. Include compiler flags and standard version notes.",
    ),
    (
        "why_exists_cpp",
        "Explain why {concept} exists in C++. What problem does it solve? "
        "What was the situation before it was introduced? When should you use it? "
        "When should you NOT use it? Show at least 3 concrete code examples: "
        "the painful way without it, the clean way with it, and a production usage pattern. "
        "Discuss compile-time vs runtime implications.",
    ),
    (
        "mistakes_cpp",
        "What are the top 5 mistakes C++ developers make with {concept}? "
        "For each mistake: show the buggy code, show the correct code, explain the "
        "undefined behavior or resource leak it causes, and describe what symptoms "
        "appear (crashes, memory corruption, data races). Include Valgrind/ASan "
        "output or compiler warnings where relevant.",
    ),
    (
        "internals_cpp",
        "Explain how {concept} works under the hood in C++. "
        "What does the compiler generate? What happens at the assembly level for key operations? "
        "What are the memory layout and performance implications? Show at least 3 code examples "
        "demonstrating internal behavior, including sizeof/alignof analysis or benchmark "
        "comparisons that prove your explanation.",
    ),
    (
        "compare_cpp",
        "Compare all major approaches to {concept} in C++. "
        "For each approach show a complete working code example with #includes and main(), "
        "then give a concrete decision framework: under what conditions (data size, "
        "real-time constraints, API stability, ABI compatibility) would you choose each one? "
        "Include a summary comparison table with Big-O and memory overhead.",
    ),
    (
        "tdd_cpp",
        "Implement {concept} using Test-Driven Development in C++.\n\n"
        "Follow this exact TDD cycle:\n"
        "1. **Red**: Write a comprehensive test suite FIRST using Google Test or Catch2. "
        "Include at least 8 test cases covering: happy path, edge cases, error conditions, "
        "boundary values, and exception safety guarantees.\n"
        "2. **Green**: Write the minimal implementation that makes ALL tests pass. "
        "Use modern C++ with proper const-correctness and noexcept where appropriate.\n"
        "3. **Refactor**: Improve for clarity, performance, and memory safety while "
        "keeping all tests green. Apply RAII and move semantics.\n\n"
        "Show complete compilable code at each step.",
    ),
    (
        "memory_safety_cpp",
        "Analyze {concept} from a memory safety perspective in C++.\n\n"
        "1. **Dangerous Version**: Show code that compiles but has undefined behavior "
        "(dangling pointer, use-after-free, buffer overflow, data race, or double-free).\n"
        "2. **Sanitizer Output**: Show what AddressSanitizer/ThreadSanitizer would report.\n"
        "3. **Safe Version**: Rewrite using RAII, smart pointers, std::span, std::string_view, "
        "or other modern C++ safety primitives.\n"
        "4. **Zero-Cost Abstractions**: Prove the safe version has no runtime overhead "
        "vs the dangerous version (compiler explorer output or benchmark).\n"
        "5. **Design Rule**: State the general rule that prevents this class of bug.\n\n"
        "All code must be complete and compilable with g++ -std=c++20 -Wall -Wextra.",
    ),
    (
        "template_metaprogramming_cpp",
        "Explore {concept} using C++ template metaprogramming and compile-time techniques.\n\n"
        "1. **Runtime Version**: A straightforward runtime implementation.\n"
        "2. **Compile-Time Version**: Use constexpr, templates, or concepts to move "
        "computation to compile time where possible.\n"
        "3. **SFINAE/Concepts**: Show how to constrain template parameters "
        "(both C++17 SFINAE and C++20 concepts approaches).\n"
        "4. **Type Traits**: Create custom type traits related to this concept.\n"
        "5. **Performance Comparison**: Measure the runtime vs compile-time approach.\n\n"
        "Include complete code with static_assert verifications.",
    ),
    (
        "concurrency_cpp",
        "Implement {concept} with proper concurrency in C++.\n\n"
        "1. **Single-Threaded Baseline**: Clean, correct implementation.\n"
        "2. **Naive Multi-Threaded**: Add std::thread — show the data race or deadlock.\n"
        "3. **Correct Concurrent Version**: Fix with std::mutex, std::lock_guard, "
        "std::atomic, or lock-free techniques as appropriate.\n"
        "4. **Modern Async**: Use std::async, std::future, or C++20 coroutines.\n"
        "5. **Benchmark**: Compare throughput of all versions with different thread counts.\n\n"
        "Discuss memory ordering (acquire/release/seq_cst) where relevant. "
        "All code must compile with -pthread.",
    ),
]


# ---------------------------------------------------------------------------
# Rust templates — ownership, safety, and zero-cost abstractions
# ---------------------------------------------------------------------------
RUST_TEMPLATES = [
    (
        "implement_rust",
        "Implement {concept} in Rust. Show the complete approach, explain the reasoning "
        "step by step, cover edge cases, and include at least 3 working code examples "
        "ranging from basic to production-ready. Use proper ownership, borrowing, and "
        "lifetimes. Include use statements and fn main().",
    ),
    (
        "correct_way_rust",
        "What is the idiomatic Rust way to handle {concept}? "
        "Show at least 2 complete code examples: the idiomatic approach and the common "
        "anti-pattern side by side. Explain why the idiomatic version is preferred — "
        "how does it leverage the borrow checker, type system, or zero-cost abstractions? "
        "When might the anti-pattern still appear in real codebases?",
    ),
    (
        "ownership_rust",
        "Analyze {concept} through the lens of Rust's ownership system.\n\n"
        "1. **Owned Version**: Implementation using owned types (String, Vec, Box).\n"
        "2. **Borrowed Version**: Refactor to use references (&str, &[T], &dyn Trait).\n"
        "3. **Lifetime Annotations**: Show where explicit lifetimes are needed and why.\n"
        "4. **Clone vs Borrow**: When is cloning the right choice? When is it wasteful?\n"
        "5. **Cow Pattern**: Use Cow<'_, str> or similar for flexible ownership.\n\n"
        "All code must compile with `rustc --edition 2021`. Explain every borrow checker error.",
    ),
    (
        "error_handling_rust",
        "Implement robust error handling for {concept} in Rust.\n\n"
        "1. **Result<T, E>**: Define custom error types with thiserror or manual Display impl.\n"
        "2. **? Operator**: Show how errors propagate through the call stack.\n"
        "3. **Error Conversion**: Implement From<OtherError> for your error type.\n"
        "4. **anyhow vs thiserror**: When to use each, with concrete examples.\n"
        "5. **Panic vs Result**: When panic! is acceptable and when it's a bug.\n\n"
        "Include complete, compilable code with proper error handling at every level.",
    ),
    (
        "concurrency_rust",
        "Implement {concept} with safe concurrency in Rust.\n\n"
        "1. **Single-Threaded**: Clean, correct baseline.\n"
        "2. **Arc<Mutex<T>>**: Shared mutable state across threads.\n"
        "3. **Channels**: mpsc or crossbeam channels for message passing.\n"
        "4. **async/await**: Tokio or async-std implementation.\n"
        "5. **Rayon**: Data parallelism for CPU-bound work.\n\n"
        "Explain Send/Sync bounds, why Rc isn't Send, and how Rust prevents data races "
        "at compile time. All code must compile.",
    ),
    (
        "unsafe_rust",
        "Explore {concept} and when unsafe Rust is needed.\n\n"
        "1. **Safe Version**: Implement entirely in safe Rust.\n"
        "2. **Performance Bottleneck**: Identify where safe abstractions have overhead.\n"
        "3. **Unsafe Version**: Rewrite the hot path using unsafe, explaining each invariant.\n"
        "4. **Safety Proof**: Explain why the unsafe code is actually safe — what invariants "
        "are upheld and how could they be violated.\n"
        "5. **Safe Wrapper**: Encapsulate the unsafe code in a safe API.\n\n"
        "Use miri or address sanitizer to validate. Show benchmarks comparing safe vs unsafe.",
    ),
    (
        "traits_rust",
        "Design and implement {concept} using Rust's trait system.\n\n"
        "1. **Trait Definition**: Define traits with associated types, default methods, and supertraits.\n"
        "2. **Implementations**: Show at least 3 concrete implementations.\n"
        "3. **Dynamic Dispatch**: Use dyn Trait with Box or &dyn for runtime polymorphism.\n"
        "4. **Static Dispatch**: Use impl Trait and generics for zero-cost abstraction.\n"
        "5. **Trait Objects vs Generics**: When to use each, with performance analysis.\n\n"
        "Include complete code with #[derive] macros where appropriate.",
    ),
    (
        "tdd_rust",
        "Implement {concept} using Test-Driven Development in Rust.\n\n"
        "Follow this TDD cycle:\n"
        "1. **Red**: Write comprehensive #[test] functions FIRST. Include at least 8 tests "
        "covering: happy path, edge cases, error conditions, and property-based tests.\n"
        "2. **Green**: Write the minimal implementation that passes all tests.\n"
        "3. **Refactor**: Improve for idiomatic Rust: proper error types, documentation, "
        "and zero-cost abstractions.\n\n"
        "Show complete compilable code at each step. Use #[cfg(test)] mod tests.",
    ),
    (
        "performance_rust",
        "Optimize {concept} for maximum performance in Rust.\n\n"
        "1. **Baseline**: Clean, correct implementation.\n"
        "2. **Profile**: Use criterion for benchmarking, show results.\n"
        "3. **Optimize**: Apply techniques: avoid allocations, use iterators, "
        "leverage SIMD, minimize branching, use stack allocation.\n"
        "4. **Unsafe Optimization**: Where unsafe gives measurable improvement.\n"
        "5. **Comparison with C++**: How does Rust's zero-cost abstraction compare?\n\n"
        "Show benchmarks and explain the assembly output for hot loops.",
    ),
    (
        "ffi_rust",
        "Implement {concept} with FFI (Foreign Function Interface) in Rust.\n\n"
        "1. **Calling C from Rust**: Use extern \"C\" and bindgen patterns.\n"
        "2. **Exposing Rust to C**: Use #[no_mangle] and extern \"C\" fn.\n"
        "3. **Safety Wrapper**: Build safe Rust API around unsafe FFI calls.\n"
        "4. **Memory Management**: Who owns what? How to avoid double-free across FFI boundary.\n"
        "5. **Error Handling**: Map C error codes to Rust Result types.\n\n"
        "Include complete, compilable code with proper unsafe blocks.",
    ),
]


# ---------------------------------------------------------------------------
# Go templates — concurrency, simplicity, and cloud-native patterns
# ---------------------------------------------------------------------------
GO_TEMPLATES = [
    (
        "implement_go",
        "Implement {concept} in Go. Show the complete approach, explain the reasoning "
        "step by step, cover edge cases, and include at least 3 working code examples "
        "ranging from basic to production-ready. Use proper error handling, interfaces, "
        "and goroutine patterns. Include package and import declarations.",
    ),
    (
        "correct_way_go",
        "What is the idiomatic Go way to handle {concept}? "
        "Show at least 2 complete code examples: the idiomatic approach and the common "
        "anti-pattern side by side. Reference Effective Go guidelines and go vet/staticcheck "
        "rules. When would the anti-pattern be acceptable?",
    ),
    (
        "concurrency_go",
        "Implement {concept} with Go concurrency primitives.\n\n"
        "1. **Sequential Baseline**: Clean, correct single-goroutine implementation.\n"
        "2. **Goroutines + WaitGroup**: Parallelize with sync.WaitGroup.\n"
        "3. **Channels**: Refactor using channels for communication.\n"
        "4. **Select**: Use select for multiplexing multiple channels.\n"
        "5. **Context**: Add context.Context for cancellation and timeouts.\n\n"
        "Explain goroutine leak prevention, channel directionality, and when to use "
        "sync.Mutex vs channels. Show race detector output (go run -race).",
    ),
    (
        "error_handling_go",
        "Implement robust error handling for {concept} in Go.\n\n"
        "1. **Basic error returns**: if err != nil patterns.\n"
        "2. **Custom error types**: Implement the error interface.\n"
        "3. **Error wrapping**: Use fmt.Errorf with %w for error chains.\n"
        "4. **errors.Is and errors.As**: Type-safe error checking.\n"
        "5. **Sentinel errors**: When to use package-level error vars.\n"
        "6. **Panic/recover**: When panic is appropriate (never in libraries).\n\n"
        "Show complete, compilable code with proper error propagation at every level.",
    ),
    (
        "interfaces_go",
        "Design {concept} using Go interfaces and composition.\n\n"
        "1. **Small interfaces**: Define focused interfaces (1-3 methods).\n"
        "2. **Implicit satisfaction**: Show how types satisfy interfaces without declaration.\n"
        "3. **Embedding**: Compose larger interfaces from smaller ones.\n"
        "4. **Interface{}→any**: Use generics (Go 1.18+) instead of empty interface.\n"
        "5. **Accept interfaces, return structs**: Show the Go proverb in practice.\n\n"
        "Include table-driven tests with testing.T.",
    ),
    (
        "testing_go",
        "Implement {concept} using Test-Driven Development in Go.\n\n"
        "1. **Table-driven tests**: Write comprehensive TestXxx functions with subtests.\n"
        "2. **Benchmarks**: BenchmarkXxx functions with b.ReportAllocs().\n"
        "3. **Fuzzing**: FuzzXxx for discovering edge cases.\n"
        "4. **Test helpers**: t.Helper() and testify assertions.\n"
        "5. **Mocking**: Interface-based dependency injection for testability.\n\n"
        "Show complete package with _test.go files.",
    ),
    (
        "http_go",
        "Build {concept} as an HTTP service in Go.\n\n"
        "1. **net/http**: Standard library handler with proper routing.\n"
        "2. **Middleware**: Logging, auth, rate limiting as http.Handler wrappers.\n"
        "3. **Graceful shutdown**: Signal handling with context cancellation.\n"
        "4. **Structured logging**: slog or zerolog integration.\n"
        "5. **Health checks**: /healthz and /readyz endpoints.\n\n"
        "Show complete, runnable server code with proper error handling.",
    ),
    (
        "generics_go",
        "Implement {concept} using Go generics (Go 1.18+).\n\n"
        "1. **Type parameters**: Define generic functions and types.\n"
        "2. **Constraints**: Use built-in (comparable, any) and custom constraints.\n"
        "3. **Type inference**: Where Go infers type params automatically.\n"
        "4. **Before generics**: How this was done with interface{}/reflect.\n"
        "5. **Limitations**: Where Go generics fall short vs Rust/C++ templates.\n\n"
        "Include complete, compilable examples with tests.",
    ),
    (
        "performance_go",
        "Optimize {concept} for performance in Go.\n\n"
        "1. **Profile**: Use pprof for CPU and memory profiling.\n"
        "2. **Allocations**: Reduce heap allocations with sync.Pool, pre-allocation.\n"
        "3. **Concurrency**: Optimal goroutine count and work distribution.\n"
        "4. **Memory layout**: Struct field ordering for cache efficiency.\n"
        "5. **Assembly**: When to use Go assembly (rarely).\n\n"
        "Show benchmark results and pprof output analysis.",
    ),
    (
        "systems_go",
        "Implement {concept} for systems programming in Go.\n\n"
        "1. **OS interaction**: syscall, os/exec, file descriptors.\n"
        "2. **Networking**: net.Listener, TCP/UDP, unix sockets.\n"
        "3. **Binary protocols**: encoding/binary for wire formats.\n"
        "4. **Memory mapped files**: Using mmap for large data.\n"
        "5. **Cross-compilation**: CGO_ENABLED=0 for static binaries.\n\n"
        "Show complete examples with proper resource cleanup (defer).",
    ),
]


# ---------------------------------------------------------------------------
# JavaScript/TypeScript templates — async patterns, web, and Hive SDKs
# ---------------------------------------------------------------------------
JS_TEMPLATES = [
    (
        "implement_js",
        "Implement {concept} in JavaScript/TypeScript. Show the complete approach, "
        "explain the reasoning step by step, cover edge cases, and include at least 3 working "
        "code examples ranging from basic to production-ready. Use modern ES2022+ syntax "
        "with async/await, optional chaining, and proper TypeScript types.",
    ),
    (
        "correct_way_js",
        "What is the correct way to handle {concept} in JavaScript? "
        "Show at least 2 complete code examples: the modern approach and the common "
        "legacy/anti-pattern side by side. Explain why the modern approach is preferred, "
        "what bugs the old pattern causes, and when the legacy approach is still seen.",
    ),
    (
        "async_js",
        "Implement {concept} with proper async patterns in JavaScript.\n\n"
        "1. **Callback Version**: The old way (for understanding).\n"
        "2. **Promise Version**: Refactor using Promises and .then/.catch.\n"
        "3. **Async/Await Version**: Clean async/await implementation.\n"
        "4. **Error Handling**: Proper try/catch with async, unhandled rejections.\n"
        "5. **Concurrency**: Promise.all, Promise.allSettled, Promise.race patterns.\n\n"
        "Explain the event loop, microtask queue, and common gotchas.",
    ),
    (
        "node_js",
        "Build {concept} as a Node.js module/service.\n\n"
        "1. **Core Implementation**: Using Node.js built-ins (fs, http, crypto, stream).\n"
        "2. **Error Handling**: EventEmitter errors, stream errors, uncaughtException.\n"
        "3. **Performance**: Worker threads, cluster module, stream backpressure.\n"
        "4. **Testing**: Jest/Vitest tests with mocking.\n"
        "5. **TypeScript**: Add full type definitions.\n\n"
        "Show complete, runnable code with package.json exports.",
    ),
    (
        "typescript_js",
        "Design {concept} with TypeScript's type system.\n\n"
        "1. **Type Definitions**: Interfaces, type aliases, generics, mapped types.\n"
        "2. **Type Guards**: User-defined type guards and discriminated unions.\n"
        "3. **Utility Types**: Pick, Omit, Partial, Record, Readonly for composition.\n"
        "4. **Generic Constraints**: extends keyword for bounded generics.\n"
        "5. **Strict Mode**: What strictNullChecks and strict catch.\n\n"
        "Include complete examples that compile with tsc --strict.",
    ),
    (
        "testing_js",
        "Implement {concept} using Test-Driven Development in JavaScript.\n\n"
        "1. **Jest/Vitest Tests**: Write comprehensive test suites with describe/it blocks.\n"
        "2. **Mocking**: jest.mock, vi.mock for dependencies.\n"
        "3. **Async Tests**: Testing promises, timers, and event-driven code.\n"
        "4. **Snapshot Tests**: When they're useful and when they're brittle.\n"
        "5. **Coverage**: Measuring and interpreting coverage metrics.\n\n"
        "Show complete test files alongside implementation.",
    ),
    (
        "security_js",
        "Analyze {concept} from a security perspective in JavaScript.\n\n"
        "1. **Vulnerable Version**: Show code with XSS, injection, or prototype pollution.\n"
        "2. **Attack Demonstration**: How an attacker exploits the vulnerability.\n"
        "3. **Secure Version**: Fix using input validation, CSP, sanitization.\n"
        "4. **Defense in Depth**: Multiple layers of protection.\n"
        "5. **Security Headers**: Relevant HTTP headers for this scenario.\n\n"
        "Include runnable examples with both attack and defense code.",
    ),
    (
        "hive_js",
        "Implement {concept} for the Hive blockchain using JavaScript.\n\n"
        "1. **dhive Setup**: Install and configure the dhive library.\n"
        "2. **Implementation**: Build the feature using dhive API calls.\n"
        "3. **Key Management**: Use Hive Keychain or secure key handling.\n"
        "4. **Error Handling**: Handle network errors, expired transactions, RC limits.\n"
        "5. **Testing**: Mock blockchain responses for unit tests.\n\n"
        "Show complete, runnable code with proper async/await patterns.",
    ),
]

# ---------------------------------------------------------------------------
# C++ TOPIC LIST — comprehensive coverage of modern C++ for training data
# ---------------------------------------------------------------------------
CPP_TOPICS = [
    # Memory management and ownership
    "C++ RAII pattern and resource management",
    "C++ smart pointers: unique_ptr, shared_ptr, weak_ptr",
    "C++ move semantics and rvalue references",
    "C++ copy and move constructors, rule of five",
    "C++ custom memory allocators and std::pmr",
    "C++ stack vs heap allocation strategies",
    "C++ placement new and object lifetime",
    # Templates and metaprogramming
    "C++ template metaprogramming fundamentals",
    "C++ variadic templates and fold expressions",
    "C++ SFINAE and std::enable_if",
    "C++20 concepts and requires clauses",
    "C++ constexpr and consteval compile-time computation",
    "C++ CRTP (Curiously Recurring Template Pattern)",
    "C++ type traits and type manipulation",
    "C++ template specialization and partial specialization",
    # STL containers and algorithms
    "C++ STL containers: vector, map, unordered_map, set performance",
    "C++ STL algorithms: sort, transform, accumulate, ranges",
    "C++ iterators: categories, custom iterators, and iterator adapters",
    "C++20 ranges and views for lazy evaluation",
    "C++ std::optional, std::variant, std::any",
    "C++ string_view and span for non-owning references",
    # Concurrency and parallelism
    "C++ std::thread and std::jthread",
    "C++ mutex, lock_guard, unique_lock, and scoped_lock",
    "C++ std::atomic and memory ordering",
    "C++ std::async, std::future, and std::promise",
    "C++ condition variables and producer-consumer pattern",
    "C++ lock-free data structures with compare_exchange",
    "C++20 coroutines and co_await",
    "C++ thread pool implementation",
    # Modern C++ patterns
    "C++ lambda expressions and captures",
    "C++ structured bindings and auto deduction",
    "C++ std::function and type erasure",
    "C++ exception safety guarantees (basic, strong, nothrow)",
    "C++ operator overloading best practices",
    "C++ virtual functions, vtables, and polymorphism costs",
    "C++ design patterns: PIMPL, factory, visitor, observer",
    "C++ compile-time polymorphism vs runtime polymorphism",
    # Performance and optimization
    "C++ cache-friendly data structures and data-oriented design",
    "C++ move semantics for zero-copy performance",
    "C++ small buffer optimization (SBO/SSO)",
    "C++ branch prediction and branchless programming",
    "C++ SIMD intrinsics and auto-vectorization",
    "C++ benchmarking with Google Benchmark",
    # Systems programming
    "C++ socket programming with RAII wrappers",
    "C++ file I/O with std::filesystem",
    "C++ interop with C libraries (extern \"C\", ABI compatibility)",
    "C++ building shared libraries and managing ABI stability",
    "C++ error handling: exceptions vs error codes vs std::expected",
]

# ---------------------------------------------------------------------------
# Rust topic list — systems programming, safety, and performance
# ---------------------------------------------------------------------------
RUST_TOPICS = [
    # Ownership and borrowing
    "Rust ownership rules and move semantics",
    "Rust borrowing: shared references (&T) vs mutable references (&mut T)",
    "Rust lifetimes: annotations, elision rules, and 'static",
    "Rust smart pointers: Box, Rc, Arc, Cell, RefCell",
    "Rust Pin and Unpin for self-referential types",
    "Rust Cow (Clone on Write) for flexible ownership",
    # Error handling
    "Rust Result<T, E> and Option<T> patterns",
    "Rust custom error types with thiserror and anyhow",
    "Rust error propagation with the ? operator",
    "Rust panic, unwinding, and abort strategies",
    # Traits and generics
    "Rust trait objects (dyn Trait) vs generics (impl Trait)",
    "Rust associated types and generic associated types (GATs)",
    "Rust derive macros: Debug, Clone, Serialize, PartialEq",
    "Rust Iterator trait and iterator adapters",
    "Rust From/Into/TryFrom/TryInto conversion traits",
    "Rust Deref and DerefMut for smart pointer patterns",
    # Concurrency
    "Rust std::thread and thread::spawn with move closures",
    "Rust channels: mpsc, crossbeam, and async channels",
    "Rust Arc<Mutex<T>> shared state patterns",
    "Rust atomic types and memory ordering (Ordering::SeqCst, Relaxed, AcqRel)",
    "Rust Send and Sync traits: thread safety at compile time",
    "Rust Rayon for data parallelism",
    # Async
    "Rust async/await with Tokio runtime",
    "Rust Future trait and Pin<Box<dyn Future>>",
    "Rust async streams and tokio::select!",
    "Rust async TCP server with tokio::net",
    # Data structures
    "Rust HashMap, BTreeMap, and custom Hash implementations",
    "Rust Vec, VecDeque, and LinkedList performance trade-offs",
    "Rust enums with data (algebraic data types / tagged unions)",
    "Rust pattern matching with match, if let, and while let",
    # Systems programming
    "Rust FFI with C: extern, #[no_mangle], bindgen",
    "Rust unsafe: raw pointers, dereferencing, and safety invariants",
    "Rust SIMD with std::simd and packed_simd",
    "Rust memory layout: repr(C), repr(packed), alignment",
    "Rust file I/O: std::fs, BufReader, BufWriter, memory-mapped files",
    "Rust network programming: TcpListener, UdpSocket, and async networking",
    # Testing and tooling
    "Rust testing: #[test], #[should_panic], integration tests, doc tests",
    "Rust benchmarking with criterion.rs",
    "Rust fuzzing with cargo-fuzz and afl",
    "Rust cargo workspace: multi-crate project organization",
    # Cryptography and blockchain
    "Rust cryptographic primitives: SHA-256, ECDSA, Ed25519 with ring/ed25519-dalek",
    "Rust serialization: serde, bincode, and custom Serialize/Deserialize",
    "Rust WebAssembly: wasm-bindgen, wasm-pack, and browser interop",
    "Rust building CLI tools with clap and structopt",
    "Rust zero-copy parsing with nom and pest",
]

# ---------------------------------------------------------------------------
# Go topic list — cloud-native, concurrency, and network services
# ---------------------------------------------------------------------------
GO_TOPICS = [
    # Concurrency
    "Go goroutines: lifecycle, scheduling, and GOMAXPROCS",
    "Go channels: unbuffered vs buffered, direction, and closing",
    "Go select statement: multiplexing channels and timeouts",
    "Go sync.WaitGroup for coordinating goroutines",
    "Go sync.Mutex and RWMutex for shared state",
    "Go context.Context: cancellation, deadlines, and values",
    "Go worker pool pattern with goroutines and channels",
    "Go race detector: detecting and fixing data races",
    # Error handling
    "Go error handling: if err != nil patterns and best practices",
    "Go custom error types: implementing the error interface",
    "Go error wrapping with fmt.Errorf and %w verb",
    "Go errors.Is and errors.As for error inspection",
    "Go panic and recover: when to use and when not to",
    # Interfaces and types
    "Go interfaces: implicit satisfaction and small interface design",
    "Go embedding: struct and interface composition",
    "Go generics (Go 1.18+): type parameters and constraints",
    "Go type assertions and type switches",
    "Go reflection: reflect package for dynamic type inspection",
    # Standard library
    "Go net/http: building HTTP servers and clients",
    "Go encoding/json: Marshal, Unmarshal, and custom (Un)Marshaler",
    "Go io.Reader and io.Writer: streaming data processing",
    "Go testing package: table-driven tests, benchmarks, and fuzzing",
    "Go database/sql: connection pools, prepared statements, and transactions",
    "Go os/exec: running external commands safely",
    "Go crypto: SHA-256, HMAC, AES encryption, and TLS",
    # Performance
    "Go memory management: stack vs heap, escape analysis",
    "Go profiling with pprof: CPU, memory, and goroutine profiles",
    "Go sync.Pool for reducing GC pressure",
    "Go string handling: strings.Builder, byte slices, and rune iteration",
    "Go struct field ordering for cache-line optimization",
    # Network and systems
    "Go TCP/UDP servers with net.Listener and net.Conn",
    "Go gRPC: defining services with Protocol Buffers",
    "Go WebSocket servers with gorilla/websocket or nhooyr.io/websocket",
    "Go building CLI tools with cobra and flag",
    "Go cross-compilation and static linking (CGO_ENABLED=0)",
    # Cloud native
    "Go Docker containerization: multi-stage builds and minimal images",
    "Go Kubernetes client-go: interacting with K8s API",
    "Go distributed systems: leader election, consistent hashing",
    "Go building microservices: circuit breaker, retry, and health checks",
    # Blockchain relevant
    "Go implementing a simple blockchain with Proof-of-Work",
    "Go cryptographic operations for blockchain: ECDSA signing and verification",
    "Go building a P2P network with libp2p",
    "Go binary protocol encoding with encoding/binary and custom wire formats",
]

# ---------------------------------------------------------------------------
# Built-in topic list — timeless coding knowledge to extract first
# ---------------------------------------------------------------------------
BUILTIN_TOPICS = [
    # Python fundamentals
    "Python generators and itertools",
    "Python decorators and functools",
    "Python context managers and __enter__/__exit__",
    "Python metaclasses and class creation",
    "Python descriptors and __get__/__set__",
    "Python memory management and garbage collection",
    "Python GIL and threading limitations",
    "Python asyncio event loop",
    "Python async/await patterns",
    "Python dataclasses vs namedtuple vs TypedDict",
    "Python type hints and mypy",
    "Python slots and memory optimization",
    "Python weakref and circular references",
    "Python __dunder__ methods and operator overloading",
    "Python comprehensions and generator expressions",
    # Algorithms and data structures
    "binary search and its variants",
    "dynamic programming with memoization",
    "depth-first search and breadth-first search",
    "quicksort and mergesort implementation",
    "heap and priority queue operations",
    "hash table collision resolution",
    "trie data structure",
    "union-find / disjoint sets",
    "sliding window technique",
    "two-pointer technique",
    "backtracking algorithms",
    "graph shortest path algorithms (Dijkstra, Bellman-Ford)",
    "tree traversal patterns",
    # Design patterns
    "singleton pattern thread safety",
    "factory pattern and abstract factory",
    "observer pattern and event systems",
    "strategy pattern for algorithm selection",
    "decorator pattern vs Python decorators",
    "command pattern for undo/redo",
    "repository pattern for data access",
    "dependency injection patterns",
    # Systems and concurrency
    "thread-safe data structures in Python",
    "multiprocessing vs threading vs asyncio",
    "connection pool implementation",
    "rate limiting algorithms (token bucket, leaky bucket)",
    "LRU cache implementation",
    "producer-consumer pattern",
    "circuit breaker pattern",
    # Web and APIs
    "REST API design principles",
    "JWT authentication implementation",
    "SQL injection prevention",
    "database transaction management",
    "database index optimization",
    "N+1 query problem and eager loading",
    "caching strategies (cache-aside, write-through)",
    # Testing
    "unit testing with pytest fixtures",
    "mocking and patching in Python tests",
    "property-based testing with hypothesis",
    "integration test patterns",
]

# ── Hive Blockchain Topics ──────────────────────────────────────────────────
# Comprehensive Hive knowledge for making HiveAI Hive-native.
# Covers SDKs (JS + Python), protocol internals, app patterns, and economics.
HIVE_TOPICS = [
    # Core Blockchain Concepts
    "Hive DPoS consensus mechanism: witness election, block production, and 3-second finality",
    "Hive Resource Credits (RC) system: zero-fee transactions via stake-based rate limiting",
    "Hive VESTS to Hive Power conversion: global dynamic properties and calculation formulas",
    "Hive block structure and transaction lifecycle: from signing to irreversibility",
    "Hive witness node operation: setup, price feed publishing, and signing keys",
    "Hive virtual operations and blockchain state transitions",
    "Hive blockchain forks: hard forks vs soft forks, upgrade coordination with witnesses",
    "Hive vs Ethereum architecture: DPoS social chain vs PoS financial chain trade-offs",
    # Account System
    "Hive account creation: claiming discounted accounts, create_claimed_account, and onboarding patterns",
    "Hive key hierarchy: owner, active, posting, and memo keys with authority levels",
    "Hive multi-signature accounts: threshold authorities and weighted key configurations",
    "Hive account recovery: trustee system, 30-day owner key change window, recovery flow",
    "Hive delegation: vesting shares delegation, RC delegation for app onboarding",
    "Hive account permissions: posting_json_metadata, profile updates, and authority management",
    # Transaction Operations
    "Hive operation types: transfer, vote, comment, custom_json, delegate_vesting_shares",
    "Hive transaction signing: serialization, SHA-256 digest, and ECDSA with posting/active keys",
    "Hive transaction broadcasting: node selection, error handling, and retry strategies",
    "Hive custom_json operations: building Layer 2 protocols on Hive consensus",
    "Hive transfer operations: HIVE, HBD, savings, vesting (power up/down), and memo encryption",
    "Hive comment/post operations: permlinks, parent_author, json_metadata, and beneficiaries",
    "Hive vote operation: weight scaling, vote cooldown, dust threshold, and curation timing",
    "Hive recurrent transfers: automated payment scheduling on-chain",
    # JavaScript SDK (dhive)
    "dhive library: installing, creating Client, and connecting to Hive API nodes",
    "dhive transaction signing: PrivateKey, broadcast.comment, and broadcast.vote patterns",
    "dhive streaming: blockchain.getBlockStream and real-time operation filtering",
    "dhive account operations: getAccounts, getDynamicGlobalProperties, and account history",
    "dhive custom_json broadcasting: posting vs active authority, id field conventions",
    "Building a Hive social app with Node.js and dhive: posting, voting, and following",
    "Building a Hive voting bot with dhive: streaming, vote scheduling, and RC management",
    "Hive Keychain browser extension: requestSignBuffer, requestBroadcast, and login flow",
    "Hive Keychain integration: web app authentication without exposing private keys",
    "dhive cryptography: memo encryption/decryption, key derivation, and signature verification",
    # Python SDK (beem/lighthive)
    "beem library: installing, Hive instance creation, and node configuration",
    "beem account operations: Account class, get_balances, history, and voting power",
    "beem posting and voting: Comment class, commit.post, and commit.vote patterns",
    "beem streaming: blockchain.stream for real-time operation processing in Python",
    "beem custom_json: broadcasting Layer 2 operations with proper authority",
    "lighthive library: lightweight Python client for Hive JSON-RPC API",
    "Building a Hive curation bot with beem: auto-voting rules, trail following, and RC checks",
    "Building a Hive analytics dashboard with Python: account stats, reward history, delegation tracking",
    # Layer 2 and Sidechains
    "Hive Engine: sidechain token creation, staking, and market operations",
    "Hive Engine smart contracts: creating custom tokens with staking and delegation",
    "Building NFTs on Hive: custom_json-based ownership ledger vs Hive Engine NFT standard",
    "Hive Layer 2 protocol design: schema versioning, operation validation, and state machines",
    "Splinterlands architecture: game state on custom_json, asset ownership, and tournament systems",
    "VSC Network: smart contracts on Hive using WebAssembly",
    "SPK Network: decentralized storage and content delivery on Hive",
    # HAF (Hive Application Framework)
    "HAF overview: PostgreSQL-based blockchain indexing for trustless applications",
    "Setting up HAF: hived replay, PostgreSQL schema, and application registration",
    "Building a HAF application: block processor, state tables, and API layer",
    "HAF SQL patterns: querying blockchain operations, account balances, and vote history",
    "HAFah: HAF Application Helper for simplified app development",
    # Economics and DeFi
    "HBD stablecoin mechanics: conversion, savings interest (20% APR), and price feed peg",
    "Hive reward pool: inflation schedule, reward fund math, and vote value calculation",
    "Hive internal market: HIVE/HBD orderbook, limit orders, and market making strategies",
    "Hive Power delegation market: finding delegators, ROI calculation, and delegation services",
    "Hive curation rewards: curation window optimization, vote timing, and trail strategies",
    # Governance
    "Hive DHF (Decentralized Hive Fund): proposal creation, voting, and return proposal threshold",
    "Hive witness voting: selecting witnesses, proxy voting, and governance participation",
    "Hive governance patterns: community-driven development, hard fork consensus, and social norms",
    "Hive content moderation: downvoting mechanics, reputation system, and community standards",
    # Full Application Patterns
    "Building a complete Hive blog platform: user auth, posting, comments, voting, and feeds",
    "Building a Hive-powered e-commerce app: product listings, escrow transfers, and reviews",
    "Building a Hive DAO tool: proposal management, multi-sig treasury, and community voting",
    "Building a Hive game backend: player state on custom_json, asset trading, and leaderboards",
    "Building a Hive content aggregator: tag-based feeds, trending algorithms, and community curation",
    "Migrating an existing web app to Hive: authentication, data storage, and monetization patterns",
]

# ---------------------------------------------------------------------------
# Hive domain detection — shared by quality scorer, distill_from_text, and exporter.
# Two tiers: "strong" signals that are unambiguous Hive terms, and "supporting"
# signals that are Hive-relevant but could appear in generic blockchain text.
# ---------------------------------------------------------------------------
HIVE_STRONG_TERMS = {
    # Protocol-specific
    "hive", "vests", "hive power", "hbd", "resource credits", "dpos",
    "custom_json", "posting_json_metadata", "hive engine", "splinterlands",
    "hive keychain", "hive signer", "hivemind", "haf ", "hafah",
    "hived", "condenser_api", "bridge_api", "account_by_key_api",
    "rc_api", "database_api", "block_api",
    # SDKs
    "dhive", "beem", "lighthive",
    # Operations
    "delegate_vesting_shares", "create_claimed_account", "claim_account",
    "transfer_to_vesting", "withdraw_vesting", "set_withdraw_vesting_route",
    "collateralized_convert", "recurrent_transfer",
    "comment_options", "vote_operation",
    # Governance
    "decentralized hive fund", "dhf", "witness_vote", "witness_update",
    "price_feed", "hive witnesses", "return proposal",
    # Layer 2
    "hive-engine", "vsc network", "spk network", "tribaldex",
}

HIVE_SUPPORTING_TERMS = {
    # Could be generic blockchain, but Hive-relevant in context
    "posting key", "active key", "owner key", "memo key",
    "power up", "power down", "curation", "beneficiaries",
    "permlink", "parent_author", "json_metadata", "reputation",
    "downvote", "mana", "voting mana", "rc mana",
    "3-second block", "irreversibility", "getaccounts",
    "get_dynamic_global_properties", "getblock",
    "broadcast", "streaming", "block_stream",
}


def _is_hive_content(text: str, title: str = "") -> tuple:
    """
    Detect whether text + title are about the Hive blockchain.

    Returns:
        (is_hive, signal_strength) where signal_strength is 0-10.
        is_hive is True when signal_strength >= 2.
    """
    combined = (text + " " + title).lower()
    strong = sum(1 for t in HIVE_STRONG_TERMS if t in combined)
    supporting = sum(1 for t in HIVE_SUPPORTING_TERMS if t in combined)
    # Strong terms count double
    signal = min(strong * 2 + supporting, 10)
    return signal >= 2, signal


def _clean_response(response: str) -> str:
    """
    Clean and repair common LLM output artifacts before scoring/persistence.

    Fixes:
      - Truncated code blocks (unclosed ```)
      - Residual think/analysis blocks from reasoning models
      - Leading/trailing whitespace and excessive blank lines
      - Meta-commentary ("Here is the response...", "I'll explain...")
    """
    if not response:
        return response

    # Strip residual <think>...</think> blocks
    text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    text = re.sub(r'<analysis>.*?</analysis>', '', text, flags=re.DOTALL)

    # Fix truncated code blocks: if odd number of ```, close the last one
    backtick_count = text.count('```')
    if backtick_count % 2 != 0:
        text = text.rstrip() + '\n```'

    # Remove meta-commentary opening lines
    meta_prefixes = [
        "here is", "here's", "i'll explain", "i will explain",
        "let me explain", "sure,", "sure!", "certainly,", "certainly!",
        "of course,", "of course!", "great question",
    ]
    lines = text.split('\n')
    if lines:
        first_line = lines[0].strip().lower()
        if any(first_line.startswith(p) for p in meta_prefixes):
            lines = lines[1:]

    # Collapse excessive blank lines (>2 consecutive → 2)
    cleaned_lines = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                cleaned_lines.append(line)
        else:
            blank_count = 0
            cleaned_lines.append(line)

    return '\n'.join(cleaned_lines).strip()


def _validate_code_blocks(response: str) -> dict:
    """
    Parse and validate code blocks in a response (all languages).
    Returns dict with code quality signals:
      - block_count: number of code blocks (any language)
      - valid_syntax: number with valid syntax (Python via AST, others via heuristics)
      - has_imports: at least one block imports a module
      - has_error_handling: at least one block has try/except or equivalent
      - has_functions: at least one block defines a function or class
      - total_code_lines: aggregate lines of actual code (not comments/blanks)
      - avg_complexity: rough cyclomatic complexity estimate
    """
    import ast as _ast

    # Extract ALL code blocks: ```lang\n...\n``` (any language tag or none)
    code_pattern = re.compile(r"```(\w*)\s*\n(.*?)```", re.DOTALL)
    matches = code_pattern.findall(response)

    # Python-family language tags
    python_tags = {"python", "py", "python3", ""}

    result = {
        "block_count": len(matches),
        "valid_syntax": 0,
        "has_imports": False,
        "has_error_handling": False,
        "has_functions": False,
        "has_type_hints": False,
        "has_docstrings": False,
        "has_test_code": False,
        "total_code_lines": 0,
        "avg_complexity": 0.0,
    }

    if not matches:
        return result

    complexities = []
    for lang, block in matches:
        block = block.strip()
        if not block:
            continue

        lang_lower = lang.lower()

        # Count meaningful lines (skip blanks, skip single-line comments)
        comment_prefixes = ("#",) if lang_lower in python_tags else ("#", "//")
        lines = [ln for ln in block.split("\n")
                 if ln.strip() and not ln.strip().startswith(comment_prefixes)]
        result["total_code_lines"] += len(lines)

        if lang_lower in python_tags:
            # Python: use AST for accurate validation
            try:
                tree = _ast.parse(block)
                result["valid_syntax"] += 1

                complexity = 1
                for node in _ast.walk(tree):
                    if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                        result["has_imports"] = True
                    if isinstance(node, (_ast.Try, _ast.ExceptHandler)):
                        result["has_error_handling"] = True
                    if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                        result["has_functions"] = True
                        # Type hints: check for return annotation or parameter annotations
                        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                            if node.returns is not None:
                                result["has_type_hints"] = True
                            for arg in node.args.args:
                                if arg.annotation is not None:
                                    result["has_type_hints"] = True
                                    break
                            # Docstrings: first statement is a string constant
                            if (node.body and isinstance(node.body[0], _ast.Expr)
                                    and isinstance(node.body[0].value, _ast.Constant)
                                    and isinstance(node.body[0].value.value, str)):
                                result["has_docstrings"] = True
                    # Test code detection
                    if isinstance(node, _ast.Assert):
                        result["has_test_code"] = True
                    if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                        if node.name.startswith("test_"):
                            result["has_test_code"] = True
                    if isinstance(node, (_ast.If, _ast.For, _ast.While, _ast.ExceptHandler,
                                         _ast.With, _ast.Assert)):
                        complexity += 1
                complexities.append(complexity)
            except SyntaxError:
                pass
        else:
            # Non-Python: heuristic validation for JS, TS, Rust, Go, C++, Solidity, etc.
            block_lower = block.lower()
            is_cpp = lang_lower in ("cpp", "c++", "cc", "cxx", "c")

            # Heuristic syntax validation: balanced braces and ≥3 meaningful lines
            is_rust = lang_lower in ("rust", "rs")
            is_go = lang_lower in ("go", "golang")
            is_js = lang_lower in ("javascript", "js", "typescript", "ts", "jsx", "tsx")

            open_braces = block.count("{")
            close_braces = block.count("}")
            brace_balanced = abs(open_braces - close_braces) <= 1
            has_substance = len(lines) >= 3
            if brace_balanced and has_substance:
                result["valid_syntax"] += 1
            # C++ enhanced: #include + balanced braces is strong signal
            elif is_cpp and re.search(r'#include\s*[<"]', block) and brace_balanced:
                result["valid_syntax"] += 1
            # Rust enhanced: use/fn + balanced braces is strong signal
            elif is_rust and re.search(r'(?:use\s+\w+|fn\s+\w+|impl\s)', block) and brace_balanced:
                result["valid_syntax"] += 1
            # Go enhanced: package/func + balanced braces is strong signal
            elif is_go and re.search(r'(?:package\s+\w+|func\s+\w+)', block) and brace_balanced:
                result["valid_syntax"] += 1

            # Import detection (JS/TS: import/require, Rust: use, Go: import, C++: #include)
            import_patterns = [
                r'\bimport\s+', r'\brequire\s*\(', r'\buse\s+\w+::',
                r'\bfrom\s+["\']', r'#include\s*[<"]',
            ]
            if any(re.search(p, block) for p in import_patterns):
                result["has_imports"] = True

            # Error handling detection
            error_patterns = [
                r'\btry\s*\{', r'\bcatch\s*\(', r'\.catch\s*\(',
                r'\bResult\s*<', r'\bErr\s*\(', r'\?;',  # Rust Result/? operator
                r'\bif\s+err\s*!=\s*nil',  # Go error handling
                r'\brevert\s*\(', r'\brequire\s*\(',  # Solidity
                r'\.then\s*\(.*\.catch', r'\btry\s*{',
                r'\bstd::optional\b', r'\bstd::expected\b',  # C++ error types
                r'\bnoexcept\b', r'\bthrow\s+\w+',  # C++ exceptions
            ]
            if any(re.search(p, block) for p in error_patterns):
                result["has_error_handling"] = True

            # Function/class detection
            func_patterns = [
                r'\bfunction\s+\w+', r'\bconst\s+\w+\s*=\s*(?:async\s*)?\(',
                r'\bclass\s+\w+', r'\bfn\s+\w+', r'\bfunc\s+\w+',
                r'\bdef\s+\w+', r'\basync\s+function',
                r'\bcontract\s+\w+', r'\bstruct\s+\w+',
                r'(?:public|private|internal)\s+function\s+\w+',
                r'\binterface\s+\w+', r'\benum\s+\w+',
                r'=>\s*\{',  # arrow functions with body
                r'\btemplate\s*<',  # C++ templates
                r'\bnamespace\s+\w+',  # C++ namespaces
                r'(?:void|int|bool|auto|std::\w+)\s+\w+\s*\(',  # C++ function defs
            ]
            if any(re.search(p, block) for p in func_patterns):
                result["has_functions"] = True

            # Type hint detection (TypeScript, Rust, Go, C++ typed signatures)
            type_hint_patterns = [
                r':\s*(?:string|number|boolean|void|Promise|Array)',  # TS
                r'->\s*(?:Result|Option|Vec|String|bool|i32|u64)',     # Rust
                r'\)\s*(?:string|int|error|bool|\*\w+)\s*\{',         # Go
                r'def\s+\w+\s*\([^)]*:\s*\w+',                        # Python fallback
                r'->\s*\w+\s*:',                                       # Python fallback
                r'\bstd::\w+', r'\bconst\s+\w+&',                     # C++ STL types, const ref
                r'\b(?:unique|shared|weak)_ptr\b',                      # C++ smart pointers
                r'\bauto\s+\w+\s*=', r'->\s*\w+\s*\{',                # C++ auto, trailing return
            ]
            if any(re.search(p, block) for p in type_hint_patterns):
                result["has_type_hints"] = True

            # Language-specific sophistication markers (counted as docstrings for scoring)
            if is_cpp:
                cpp_quality_patterns = [
                    r'\bstd::(?:unique|shared|weak)_ptr\b',  # smart pointers
                    r'\bstd::move\b', r'&&(?!\s*&)',          # move semantics
                    r'\bconstexpr\b', r'\bconsteval\b',       # compile-time
                    r'\btemplate\s*<', r'\brequires\b',       # templates/concepts
                    r'\bstatic_assert\b',                      # compile-time checks
                    r'\bnoexcept\b',                            # exception spec
                    r'\[\[nodiscard\]\]',                       # attributes
                ]
                cpp_hits = sum(1 for p in cpp_quality_patterns if re.search(p, block))
                if cpp_hits >= 2:
                    result["has_docstrings"] = True  # reuse flag for "quality code" signal
            elif is_rust:
                rust_quality_patterns = [
                    r'\bResult<\w+,\s*\w+>',                   # Result type
                    r'\bOption<\w+>',                            # Option type
                    r'\bimpl\s+\w+\s+for\b',                    # trait impl
                    r'\b(?:Arc|Rc|Box|Cow)<',                   # smart pointers
                    r'\blifetime\b|\'[a-z]\b',                  # lifetimes
                    r'\bunsafe\s*\{',                            # unsafe blocks
                    r'#\[derive\(',                              # derive macros
                    r'\basync\s+fn\b',                           # async functions
                    r'\b\.await\b',                              # await syntax
                    r'\bwhere\s+\w+\s*:',                       # where clauses
                ]
                rust_hits = sum(1 for p in rust_quality_patterns if re.search(p, block))
                if rust_hits >= 2:
                    result["has_docstrings"] = True
            elif is_go:
                go_quality_patterns = [
                    r'\bgo\s+func\b',                           # goroutine launch
                    r'\bchan\s+\w+',                             # channels
                    r'\bselect\s*\{',                            # select statement
                    r'\bdefer\s+',                               # defer cleanup
                    r'\bcontext\.(?:WithCancel|WithTimeout)',    # context usage
                    r'\bsync\.(?:Mutex|RWMutex|WaitGroup)\b',   # sync primitives
                    r'\binterface\s*\{',                         # interface definition
                    r'\berrors\.(?:Is|As|New)\b',                # error wrapping
                    r'\bt\.(?:Run|Helper|Parallel)\b',          # test helpers
                    r'\b\[\w+\]\w+',                             # generics
                ]
                go_hits = sum(1 for p in go_quality_patterns if re.search(p, block))
                if go_hits >= 2:
                    result["has_docstrings"] = True

            # Test code detection (all languages)
            test_patterns = [
                r'\b(?:assert|expect|should)\b', r'\bdescribe\s*\(',
                r'\bit\s*\(', r'\btest\s*\(', r'def\s+test_',
                r'#\[test\]', r'func\s+Test\w+',  # Rust, Go
                r'\bTEST\s*\(', r'\bTEST_F\s*\(',  # Google Test
                r'\bTEST_CASE\s*\(', r'\bSECTION\s*\(',  # Catch2
                r'\bstatic_assert\b', r'\bBOOST_CHECK\b',  # C++ static/Boost
            ]
            if any(re.search(p, block) for p in test_patterns):
                result["has_test_code"] = True

            # Heuristic complexity: count branch/loop keywords
            complexity = 1
            branch_patterns = [
                r'\bif\s*[\(\{]', r'\bfor\s*[\(\{]', r'\bwhile\s*[\(\{]',
                r'\bswitch\s*[\(\{]', r'\bmatch\s*[\{\(]', r'\bcase\s+',
                r'\belse\s*\{', r'\belse\s+if',
            ]
            for p in branch_patterns:
                complexity += len(re.findall(p, block))
            complexities.append(min(complexity, 20))

    if complexities:
        result["avg_complexity"] = sum(complexities) / len(complexities)

    return result


def _score_quality(instruction: str, response: str) -> float:
    """
    Multi-signal quality scorer for training pairs.
    Returns 0.0 – 1.0. Must be >= MIN_TRAINING_QUALITY to be eligible.

    v5 scoring breakdown (max 1.05, clamped to 1.0):
      Content depth:     up to 0.20  (word count with diminishing returns)
      Code quality:      up to 0.35  (AST, complexity, type hints, docstrings, tests)
      Reasoning depth:   up to 0.25  (expanded markers + production signals)
      Structure:         up to 0.10  (headers, sections, organization)
      Instruction fit:   up to 0.10  (specificity + topic coverage)
      Hive domain:       up to 0.05  (Hive terminology + SDK patterns)
      Penalties:         up to -0.30 (short, no code, repetitive)

    v5 changes from v4:
      - Code quality raised from 0.25 → 0.35 (core signal for coding model)
      - Added: type hints (+0.03), docstrings (+0.02), test code (+0.03)
      - Imports raised from 0.01 → 0.02
      - Content depth reduced 0.25 → 0.20 (quality > length)
      - Structure reduced 0.15 → 0.10 (code quality > formatting)
      - Penalties: added hard -0.15 for zero code blocks (coding model must code)
    """
    # Clean response before scoring
    response = _clean_response(response)
    score = 0.0
    response_lower = response.lower()
    word_count = len(response.split())

    # =========================================================================
    # 1. CONTENT DEPTH (0.20 max) — diminishing returns above 1200 words
    # =========================================================================
    if word_count >= 1200:
        depth = 0.20
    elif word_count >= 800:
        depth = 0.18
    elif word_count >= 600:
        depth = 0.15
    elif word_count >= 400:
        depth = 0.10
    elif word_count >= 200:
        depth = 0.06
    elif word_count >= 100:
        depth = 0.03
    else:
        depth = 0.0
    score += depth

    # =========================================================================
    # 2. CODE QUALITY (0.35 max) — AST-validated, production signals, typing
    # =========================================================================
    code_info = _validate_code_blocks(response)
    code_score = 0.0

    # Base: code block presence (0.08 max)
    if code_info["block_count"] >= 3:
        code_score += 0.08
    elif code_info["block_count"] >= 2:
        code_score += 0.06
    elif code_info["block_count"] >= 1:
        code_score += 0.03

    # Bonus: valid syntax — Python via AST, others via heuristics (0.07 max)
    if code_info["valid_syntax"] >= 3:
        code_score += 0.07
    elif code_info["valid_syntax"] >= 2:
        code_score += 0.05
    elif code_info["valid_syntax"] >= 1:
        code_score += 0.03

    # Bonus: code sophistication signals (0.11 max)
    if code_info["has_functions"]:
        code_score += 0.04  # defines functions/classes = teaching patterns
    if code_info["has_error_handling"]:
        code_score += 0.03  # try/except = production awareness
    if code_info["has_imports"]:
        code_score += 0.02  # imports = real usable code (was 0.01)
    if code_info["avg_complexity"] >= 3:
        code_score += 0.02  # non-trivial logic

    # Bonus: production-quality code signals (0.08 max, NEW in v5)
    if code_info["has_type_hints"]:
        code_score += 0.03  # type annotations = production-grade code
    if code_info["has_docstrings"]:
        code_score += 0.02  # documented code = maintainable code
    if code_info["has_test_code"]:
        code_score += 0.03  # tests = verifiable correctness

    # Bonus: code depth — reward substantial code, not just many snippets
    total_code_lines = code_info["total_code_lines"]
    if total_code_lines >= 100:
        code_score += 0.03  # substantial implementation
    elif total_code_lines >= 50:
        code_score += 0.02  # solid examples
    elif total_code_lines >= 25:
        code_score += 0.01

    score += min(code_score, 0.35)

    # =========================================================================
    # 3. REASONING DEPTH (0.25 max) — expanded markers + production signals
    # =========================================================================
    # Tier 1: Causal/logical connectors (strongest signal of reasoning)
    causal_markers = [
        "because", "therefore", "consequently", "as a result",
        "this means", "which leads to", "the reason", "due to",
        "this causes", "which implies", "hence",
    ]
    causal_hits = sum(1 for m in causal_markers if m in response_lower)

    # Tier 2: Nuance and qualification markers
    nuance_markers = [
        "however", "although", "on the other hand", "in contrast",
        "alternatively", "it depends", "the trade-off", "tradeoff",
        "caveat", "edge case", "corner case", "exception",
        "unless", "but only if", "depending on",
    ]
    nuance_hits = sum(1 for m in nuance_markers if m in response_lower)

    # Tier 3: Depth vocabulary (production, performance, real-world)
    depth_markers = [
        "production", "real-world", "at scale", "under load",
        "performance", "memory", "latency", "throughput",
        "bottleneck", "optimization", "benchmark", "profiling",
        "thread-safe", "race condition", "deadlock", "concurrent",
        "idempotent", "immutable", "side effect", "pure function",
        "time complexity", "space complexity", "big o", "o(n)",
        "invariant", "precondition", "postcondition",
    ]
    depth_hits = sum(1 for m in depth_markers if m in response_lower)

    # Tier 4: Teaching/comparison markers
    teaching_markers = [
        "common mistake", "pitfall", "anti-pattern", "bad practice",
        "best practice", "instead", "prefer", "avoid",
        "the correct way", "the wrong way", "note that", "important",
        "for example", "consider", "step 1", "step 2", "first,", "second,",
    ]
    teaching_hits = sum(1 for m in teaching_markers if m in response_lower)

    # Tier 5: Production-readiness signals (new in v3)
    production_markers = [
        "monitoring", "observability", "graceful", "resilience", "resilient",
        "circuit breaker", "retry", "backoff", "health check", "failover",
        "load balancing", "horizontal scaling", "vertical scaling",
        "caching strategy", "connection pool", "resource cleanup",
        "graceful shutdown", "signal handling", "logging",
        "error recovery", "fault tolerance", "fault-tolerant",
        "back-pressure", "backpressure", "rate limit",
    ]
    production_hits = sum(1 for m in production_markers if m in response_lower)

    # Weighted reasoning score (v3: raised caps, added production tier)
    reasoning = 0.0
    reasoning += min(causal_hits * 0.025, 0.08)      # up to 0.08
    reasoning += min(nuance_hits * 0.020, 0.05)       # up to 0.05
    reasoning += min(depth_hits * 0.012, 0.06)        # up to 0.06 (was 0.04)
    reasoning += min(teaching_hits * 0.012, 0.04)     # up to 0.04 (was 0.03)
    reasoning += min(production_hits * 0.015, 0.04)   # up to 0.04 (new)
    score += min(reasoning, 0.25)

    # =========================================================================
    # 4. STRUCTURE (0.10 max) — organization, sections, lists
    # =========================================================================
    structure = 0.0

    # Section headers (## Title or **Bold Title**)
    headers = re.findall(r"^#{1,3}\s+\w", response, re.MULTILINE)
    if len(headers) >= 4:
        structure += 0.04
    elif len(headers) >= 2:
        structure += 0.03
    elif len(headers) >= 1:
        structure += 0.01

    # Numbered or bulleted lists
    list_items = re.findall(r"^[\s]*(?:[-*]|\d+\.)\s+", response, re.MULTILINE)
    if len(list_items) >= 5:
        structure += 0.03
    elif len(list_items) >= 2:
        structure += 0.02

    # Has conclusion/summary section
    if re.search(r"(?:summary|conclusion|key takeaway|key insight|in summary|to summarize|takeaway)",
                 response_lower):
        structure += 0.02

    # Bold emphasis for key terms
    bold_terms = re.findall(r"\*\*[^*]{2,30}\*\*", response)
    if len(bold_terms) >= 3:
        structure += 0.01

    score += min(structure, 0.10)

    # =========================================================================
    # 5. INSTRUCTION FIT (0.10 max) — does the response match the instruction?
    # =========================================================================
    instr_score = 0.0
    instr_words = instruction.lower().split()

    # Instruction specificity
    if len(instr_words) >= 15:
        instr_score += 0.04
    elif len(instr_words) >= 8:
        instr_score += 0.03
    elif len(instr_words) >= 4:
        instr_score += 0.01

    # Topic keyword overlap: do key terms from instruction appear in response?
    topic_words = [w for w in instr_words if len(w) >= 5 and w.isalpha()]
    if topic_words:
        overlap = sum(1 for w in topic_words if w in response_lower)
        overlap_ratio = overlap / len(topic_words)
        if overlap_ratio >= 0.7:
            instr_score += 0.06
        elif overlap_ratio >= 0.4:
            instr_score += 0.04
        elif overlap_ratio >= 0.2:
            instr_score += 0.02

    score += min(instr_score, 0.10)

    # =========================================================================
    # 6. HIVE DOMAIN BONUS (0.05 max) — reward Hive-specific knowledge
    # Hive-domain pairs are HiveAI's differentiator. This bonus ensures
    # protocol-accurate but less code-heavy Hive content passes quality gates.
    # =========================================================================
    hive_bonus = 0.0
    combined_text = (instruction + " " + response_lower)

    # Tier 1: Strong Hive terms (unambiguous protocol references)
    strong_hits = sum(1 for t in HIVE_STRONG_TERMS if t in combined_text.lower())
    if strong_hits >= 3:
        hive_bonus += 0.03
    elif strong_hits >= 1:
        hive_bonus += 0.02

    # Tier 2: Hive SDK/API patterns in code (most valuable for code generation)
    hive_code_patterns = [
        r'from\s+beem', r'import\s+beem', r'from\s+lighthive',
        r'require.*dhive', r'import.*dhive', r'Client\s*\(',
        r'hive\.stream', r'hive\.commit', r'blockchain\.stream',
        r'getAccounts', r'getDynamicGlobalProperties',
        r'broadcast\.\w+', r'custom_json',
        r'PrivateKey', r'Hive\s*\(', r'Account\s*\(',
    ]
    api_hits = sum(1 for p in hive_code_patterns if re.search(p, response))
    if api_hits >= 2:
        hive_bonus += 0.02
    elif api_hits >= 1:
        hive_bonus += 0.01

    score += min(hive_bonus, 0.05)

    # =========================================================================
    # 7. PENALTIES — deduct for low-quality signals
    # =========================================================================
    penalties = 0.0

    # Very short response
    if word_count < 100:
        penalties += 0.25
    elif word_count < 150:
        penalties += 0.10

    # No code blocks at all (coding model MUST produce code)
    if code_info["block_count"] == 0:
        penalties += 0.15

    # Repetitive content: check for repeated sentences
    sentences = [s.strip() for s in re.split(r'[.!?]\s+', response) if len(s.strip()) > 20]
    if len(sentences) >= 3:
        unique_ratio = len(set(s.lower()[:50] for s in sentences)) / len(sentences)
        if unique_ratio < 0.7:
            penalties += 0.10  # >30% repeated sentences

    # All code blocks have syntax errors
    if code_info["block_count"] >= 2 and code_info["valid_syntax"] == 0:
        penalties += 0.08

    final = max(0.0, score - penalties)

    # Hard gate: coding model requires minimum code blocks to be eligible
    # Exception: Hive protocol/domain content may be explanation-heavy with minimal code
    from hiveai.config import MIN_CODE_BLOCKS
    if code_info["block_count"] < MIN_CODE_BLOCKS:
        is_hive, _signal = _is_hive_content(instruction + " " + response, "")
        if not is_hive:
            final = min(final, 0.49)  # force below any reasonable quality threshold

    return round(min(final, 1.0), 2)


def score_quality_detailed(instruction: str, response: str) -> dict:
    """
    Return detailed quality breakdown for analytics and debugging.
    Same logic as _score_quality but returns per-signal scores.
    """
    response_lower = response.lower()
    word_count = len(response.split())
    code_info = _validate_code_blocks(response)

    details = {
        "overall": _score_quality(instruction, response),
        "word_count": word_count,
        "code_blocks": code_info["block_count"],
        "valid_syntax": code_info["valid_syntax"],
        "has_functions": code_info["has_functions"],
        "has_error_handling": code_info["has_error_handling"],
        "has_type_hints": code_info["has_type_hints"],
        "has_docstrings": code_info["has_docstrings"],
        "has_test_code": code_info["has_test_code"],
        "total_code_lines": code_info["total_code_lines"],
        "avg_complexity": round(code_info["avg_complexity"], 1),
    }
    return details


def _refine_with_execution(instruction: str, response: str, max_rounds: int = 2) -> tuple:
    """
    Self-refinement loop: execute code, feed errors back, let model fix.

    Returns (final_response, refinement_trajectory) where trajectory is a list
    of dicts recording each round's execution result and fix attempt.
    This trajectory itself becomes valuable training data — the model learns
    to debug, not just to generate correct code on the first try.
    """
    from hiveai.sandbox import verify_response_code

    trajectory = []
    current_response = response

    for round_num in range(max_rounds):
        # Execute all Python code blocks in the response
        exec_result = verify_response_code(current_response, timeout=15)

        trajectory.append({
            "round": round_num,
            "passed": exec_result["passed"],
            "failed": exec_result["failed"],
            "timed_out": exec_result["timed_out"],
            "pass_rate": exec_result["overall_pass_rate"],
        })

        # If all code passes, no refinement needed
        if exec_result["failed"] == 0 and exec_result["timed_out"] == 0:
            logger.debug(f"  Refinement round {round_num}: all code passes, done")
            break

        # If no code blocks at all, can't refine
        if exec_result["total_blocks"] == 0:
            break

        # Collect error details for the fix prompt
        errors = []
        for block_result in exec_result["results"]:
            ex = block_result.get("execution")
            if ex and not ex["success"]:
                errors.append(
                    f"Code: {block_result['code_preview']}...\n"
                    f"Error: {ex.get('error_type', 'Unknown')}: {ex.get('stderr', '')[:200]}"
                )

        if not errors:
            break

        # Ask the model to fix its own code
        error_summary = "\n---\n".join(errors[:3])  # cap at 3 errors
        fix_prompt = (
            f"Your previous code for the following task has execution errors:\n\n"
            f"**Task:** {instruction[:500]}\n\n"
            f"**Errors found:**\n{error_summary}\n\n"
            f"Fix ALL the errors. Return the complete corrected implementation. "
            f"Explain what was wrong and why the fix works."
        )

        try:
            from hiveai.llm.client import reason
            fixed_response = reason(fix_prompt, max_tokens=4096)
            if fixed_response and len(fixed_response.strip()) > 50:
                current_response = fixed_response.strip()
                logger.info(f"  Refinement round {round_num+1}: fixed {len(errors)} errors")
            else:
                break
        except Exception as e:
            logger.warning(f"  Refinement round {round_num+1} failed: {e}")
            break

    return current_response, trajectory


def distill_batch(topics: list, pairs_per_topic: int = 10, db=None,
                  refine: bool = True, language: str = "python") -> list:
    """
    Generate self-distilled training pairs for a list of topics.

    For each topic, runs every TEMPLATE (or up to pairs_per_topic templates cycling)
    against the LLM and collects (instruction, response, quality) dicts.

    When refine=True (default), each response goes through execution-guided
    self-refinement: code is executed, errors are fed back to the model,
    and the fix trajectory is preserved as additional training data.

    Args:
        topics: List of coding topic strings
        pairs_per_topic: Max pairs to generate per topic
        db: Optional SQLAlchemy session — if provided, pairs are committed to DB
        refine: Enable execution-guided self-refinement (default True)
        language: Target language — "python" (default), "cpp", or "javascript"

    Returns:
        List of dicts with keys: source, topic, instruction, response, quality, is_eligible
    """
    from hiveai.llm.client import reason

    # Languages without execution sandboxes — disable refinement automatically
    if language == "go" and refine:
        logger.info(f"{language} mode: disabling execution-based refinement (no sandbox yet)")
        refine = False
    # C++ and Rust now have sandboxes — refinement can stay enabled

    results = []

    for topic in topics:
        logger.info(f"Distilling [{language}]: {topic}")
        # Select templates based on language
        import itertools
        if language == "cpp":
            all_templates = CPP_TEMPLATES
        elif language == "rust":
            all_templates = RUST_TEMPLATES
        elif language == "go":
            all_templates = GO_TEMPLATES
        elif language == "javascript":
            all_templates = JS_TEMPLATES
        else:
            # Python: all template families (basic + O1 reasoning + explanation)
            all_templates = TEMPLATES + O1_TEMPLATES + EXPLAIN_TEMPLATES
        template_cycle = list(itertools.islice(itertools.cycle(all_templates), pairs_per_topic))

        for template_key, template_text in template_cycle:
            instruction = template_text.format(concept=topic)

            from hiveai.llm.prompts import (
                CODING_SYSTEM_PROMPT, CPP_SYSTEM_PROMPT,
                RUST_SYSTEM_PROMPT, GO_SYSTEM_PROMPT, JAVASCRIPT_SYSTEM_PROMPT,
            )

            _system_prompts = {
                "cpp": CPP_SYSTEM_PROMPT,
                "rust": RUST_SYSTEM_PROMPT,
                "go": GO_SYSTEM_PROMPT,
                "javascript": JAVASCRIPT_SYSTEM_PROMPT,
            }
            system_prompt = _system_prompts.get(language, CODING_SYSTEM_PROMPT)
            try:
                response = reason(
                    f"{system_prompt}\n\n{instruction}",
                    max_tokens=4096,
                )
            except Exception as e:
                logger.warning(f"LLM call failed for topic '{topic}' template '{template_key}': {e}")
                continue

            if not response or len(response.strip()) < 50:
                logger.debug(f"Empty/short response for {topic} / {template_key}, skipping")
                continue

            # Self-refinement: execute code, fix errors, keep trajectory
            trajectory = None
            original_response = response.strip()  # save pre-refinement for debug pairs
            if refine:
                try:
                    response, trajectory = _refine_with_execution(instruction, original_response)
                except Exception as e:
                    logger.debug(f"  Refinement skipped: {e}")

            from hiveai.config import MIN_TRAINING_QUALITY
            quality = _score_quality(instruction, response)

            # Bonus: code that actually executes gets a quality boost
            if trajectory and len(trajectory) > 0 and trajectory[-1].get("pass_rate", 0) > 0.5:
                quality = min(quality + 0.05, 1.0)

            is_eligible = quality >= MIN_TRAINING_QUALITY

            # Build metadata with refinement trajectory for future DPO/contrastive training
            pair_metadata = None
            if trajectory and len(trajectory) > 0:
                pair_metadata = {
                    "refinement_rounds": len(trajectory),
                    "initial_pass_rate": trajectory[0].get("pass_rate", 0),
                    "final_pass_rate": trajectory[-1].get("pass_rate", 0),
                    "trajectory": trajectory,
                }

            pair = {
                "source": "self_distill",
                "topic": topic,
                "instruction": instruction,
                "response": response.strip(),
                "quality": quality,
                "is_eligible": is_eligible,
                "metadata": pair_metadata,
            }
            results.append(pair)

            if db is not None:
                _persist_pair(db, pair)

            # If refinement occurred, save the debug trajectory as a training pair.
            # Include the ORIGINAL broken response in the instruction so the pair teaches debugging.
            if trajectory and len(trajectory) > 1 and trajectory[-1].get("pass_rate", 0) > trajectory[0].get("pass_rate", 0):
                # The original (pre-refinement) response had errors — use it as the "broken code"
                from hiveai.sandbox import extract_code_blocks
                original_blocks = extract_code_blocks(original_response)
                original_code = "\n\n".join(b["code"] for b in original_blocks[:3]) if original_blocks else original_response[:500]
                first_round = trajectory[0]
                fail_count = first_round.get("failed", 0)
                lang_label = "C++" if language == "cpp" else "Python"
                lang_tag = "cpp" if language == "cpp" else "python"
                debug_instruction = (
                    f"Debug and fix the following {lang_label} code related to {topic}. "
                    f"The code has {fail_count} execution error(s). "
                    f"Identify the root cause and provide a corrected version.\n\n"
                    f"```{lang_tag}\n{original_code}\n```"
                )
                debug_pair = {
                    "source": "self_distill_debug",
                    "topic": topic,
                    "instruction": debug_instruction,
                    "response": response.strip(),
                    "quality": quality,
                    "is_eligible": is_eligible,
                    "metadata": {
                        "original_pass_rate": trajectory[0].get("pass_rate", 0),
                        "fixed_pass_rate": trajectory[-1].get("pass_rate", 0),
                    },
                }
                results.append(debug_pair)
                if db is not None:
                    _persist_pair(db, debug_pair)

        logger.info(f"  Generated {len([r for r in results if r['topic'] == topic])} pairs for '{topic}'")

    eligible = sum(1 for r in results if r["is_eligible"])
    logger.info(f"Distillation complete: {len(results)} pairs total, {eligible} eligible")
    return results


def mutate_instruction(instruction: str, mutation_type: str) -> str:
    """
    Genetic-Instruct: mutate an existing instruction to create diverse variants.

    Based on Genetic-Instruct (2025) — uses controlled mutations to expand
    training data 5-10x while preserving consistency.

    Mutation types:
      - "add_constraint": Add a performance/memory/threading constraint
      - "change_difficulty": Make harder or easier
      - "compose": Combine with a secondary concept
      - "edge_case": Focus on boundary/error conditions
      - "language_shift": Request in different coding style
    """
    mutations = {
        "add_constraint": [
            "Additionally, ensure the solution is thread-safe and handles concurrent access.",
            "The solution must handle at least 1 million items with O(n log n) or better time complexity.",
            "Memory usage must stay under 100MB even for large inputs. Show memory-efficient patterns.",
            "The implementation must be fully async-compatible.",
            "Include comprehensive error handling for all edge cases including null/None, empty, and malformed input.",
        ],
        "change_difficulty": [
            "Explain this as if teaching a junior developer who just learned the basics.",
            "Now solve the same problem but optimized for a production system handling 10K requests/second.",
            "Implement this without using any standard library helpers — build everything from scratch.",
            "Add comprehensive type annotations, documentation, and tests that verify correctness.",
        ],
        "compose": [
            "Also integrate structured logging and monitoring so the implementation is production-observable.",
            "Combine this with a caching layer (LRU or TTL-based) to optimize repeated calls.",
            "Wrap this in a network service endpoint with proper request validation and error responses.",
            "Add a command-line interface that exposes all the functionality with proper argument parsing.",
            "Include data persistence with proper schema design and migrations.",
        ],
        "edge_case": [
            "Focus specifically on what happens with empty input, null/None values, and extremely large inputs.",
            "Show what happens when this is called recursively — are there stack overflow risks?",
            "Demonstrate the behavior under race conditions with multiple threads.",
            "What happens when the network is unreliable? Show retry and fallback patterns.",
            "Handle Unicode edge cases, mixed encodings, and binary data gracefully.",
        ],
        "language_shift": [
            "Write this in a functional programming style using only pure functions and immutability.",
            "Implement using the builder pattern with method chaining for a fluent API.",
            "Implement using RAII / resource acquisition patterns that handle setup and teardown automatically.",
            "Write this using the strategy pattern so the core algorithm is swappable at runtime.",
            "Use strongly-typed interfaces and generics for a clean, composable API.",
        ],
    }

    if mutation_type not in mutations:
        mutation_type = "add_constraint"

    import random
    suffix = random.choice(mutations[mutation_type])
    return f"{instruction}\n\n{suffix}"


def expand_pairs_genetic(db, expansion_factor: int = 3, min_quality: float = 0.80) -> list:
    """
    Genetic-Instruct expansion: mutate high-quality existing pairs to create
    diverse training variants.

    Takes the best existing pairs and applies controlled mutations to generate
    new instructions that map to the same core knowledge but with different
    constraints, difficulty levels, or composition requirements.

    Args:
        db: SQLAlchemy session
        expansion_factor: How many variants per source pair (default 3)
        min_quality: Minimum quality of source pairs to expand (default 0.80)

    Returns:
        List of new pair dicts
    """
    from hiveai.models import TrainingPair
    from hiveai.llm.client import reason
    import random

    # Fetch high-quality source pairs
    source_pairs = db.query(TrainingPair).filter(
        TrainingPair.is_eligible == True,
        TrainingPair.quality >= min_quality,
    ).order_by(TrainingPair.quality.desc()).limit(500).all()

    if not source_pairs:
        logger.warning("No high-quality pairs found for genetic expansion")
        return []

    logger.info(f"Genetic expansion: {len(source_pairs)} source pairs × {expansion_factor} mutations")

    mutation_types = ["add_constraint", "change_difficulty", "compose", "edge_case", "language_shift"]
    results = []

    for pair in source_pairs:
        # Select random mutation types for this pair
        selected_mutations = random.sample(mutation_types, min(expansion_factor, len(mutation_types)))

        for mutation_type in selected_mutations:
            mutated_instruction = mutate_instruction(pair.instruction, mutation_type)

            from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

            try:
                response = reason(
                    f"{CODING_SYSTEM_PROMPT}\n\n{mutated_instruction}",
                    max_tokens=4096,
                )
            except Exception as e:
                logger.warning(f"Genetic expansion failed for mutation '{mutation_type}': {e}")
                continue

            if not response or len(response.strip()) < 50:
                continue

            from hiveai.config import MIN_TRAINING_QUALITY
            quality = _score_quality(mutated_instruction, response)
            is_eligible = quality >= MIN_TRAINING_QUALITY

            new_pair = {
                "source": f"genetic_{mutation_type}",
                "topic": pair.topic,
                "instruction": mutated_instruction,
                "response": response.strip(),
                "quality": quality,
                "is_eligible": is_eligible,
            }
            results.append(new_pair)

            if db is not None:
                # bypass_dedup: genetic mutations append constraints to existing
                # instructions, causing ~0.90+ cosine similarity. That's by design,
                # not duplication — the response is completely different.
                _persist_pair(db, new_pair, bypass_dedup=True)

        if len(results) % 20 == 0 and results:
            eligible = sum(1 for r in results if r["is_eligible"])
            logger.info(f"  Genetic progress: {len(results)} generated, {eligible} eligible")

    eligible = sum(1 for r in results if r["is_eligible"])
    logger.info(f"Genetic expansion complete: {len(results)} pairs, {eligible} eligible")
    return results


def distill_builtin(pairs_per_topic: int = 3, db=None) -> list:
    """
    Run distillation over the full built-in topic list.
    Use pairs_per_topic=3 for a quick first pass (~150 pairs),
    pairs_per_topic=6 for thorough extraction (~300 pairs).
    """
    return distill_batch(BUILTIN_TOPICS, pairs_per_topic=pairs_per_topic, db=db)


def distill_hive(pairs_per_topic: int = 5, db=None) -> list:
    """
    Run distillation over Hive blockchain topics.
    Generates comprehensive Hive-specific training data covering SDKs,
    protocol internals, app patterns, and economics.
    ~70 topics × 5 pairs = ~350 pairs expected.
    """
    return distill_batch(HIVE_TOPICS, pairs_per_topic=pairs_per_topic, db=db)


def distill_cpp(pairs_per_topic: int = 5, db=None) -> list:
    """
    Run distillation over C++ topics using C++-specific templates.
    Generates modern C++ training data covering memory management, templates,
    STL, concurrency, and performance optimization.
    ~50 topics × 5 pairs = ~250 pairs expected.

    Note: Execution-based refinement is automatically disabled (no g++ sandbox).
    """
    return distill_batch(CPP_TOPICS, pairs_per_topic=pairs_per_topic, db=db, language="cpp")


def distill_rust(pairs_per_topic: int = 5, db=None) -> list:
    """
    Run distillation over Rust systems programming topics.
    Generates Rust training data covering ownership, concurrency, traits,
    error handling, FFI, and performance optimization.
    ~48 topics × 5 pairs = ~240 pairs expected.
    """
    return distill_batch(RUST_TOPICS, pairs_per_topic=pairs_per_topic, db=db, language="rust")


def distill_go(pairs_per_topic: int = 5, db=None) -> list:
    """
    Run distillation over Go cloud-native and systems programming topics.
    Generates Go training data covering goroutines, channels, interfaces,
    error handling, HTTP services, and cloud-native patterns.
    ~44 topics × 5 pairs = ~220 pairs expected.
    """
    return distill_batch(GO_TOPICS, pairs_per_topic=pairs_per_topic, db=db, language="go")


def distill_javascript(pairs_per_topic: int = 5, db=None) -> list:
    """
    Run distillation over JavaScript/TypeScript and Hive JS SDK topics.
    Extracts Hive JavaScript SDK topics from HIVE_TOPICS automatically.
    """
    # Extract JS-relevant topics from HIVE_TOPICS
    js_hive_topics = [t for t in HIVE_TOPICS if any(
        kw in t.lower() for kw in ("dhive", "node.js", "keychain", "javascript", "browser")
    )]
    # General JS/TS topics
    js_general = [
        "JavaScript closures and scope chains",
        "JavaScript Promises and async/await patterns",
        "JavaScript event loop, microtasks, and macrotasks",
        "JavaScript prototypal inheritance vs class syntax",
        "JavaScript WeakMap, WeakSet, and WeakRef for memory management",
        "TypeScript discriminated unions and exhaustive checking",
        "TypeScript utility types: Pick, Omit, Partial, Record, Readonly",
        "TypeScript generics: constraints, conditional types, and infer",
        "Node.js streams: Readable, Writable, Transform, and backpressure",
        "Node.js worker threads for CPU-intensive tasks",
        "Node.js cluster module for multi-process scaling",
        "JavaScript Web Crypto API for browser-side cryptography",
        "JavaScript fetch API, AbortController, and retry patterns",
        "JavaScript Proxy and Reflect for metaprogramming",
        "JavaScript iterators, generators, and async generators",
    ]
    all_topics = js_general + js_hive_topics
    return distill_batch(all_topics, pairs_per_topic=pairs_per_topic, db=db, language="javascript")


def distill_from_text(text: str, title: str, db=None) -> list:
    """
    Extract training pairs FROM provided text (not from model's existing knowledge).
    Sends chunks of the text to the LLM and asks it to generate instruction-response
    pairs that teach the content — factual recall, application, and synthesis.

    Args:
        text:  Raw knowledge content (markdown, code, plaintext)
        title: Topic/title for the knowledge
        db:    Optional DB session for persisting pairs

    Returns:
        List of pair dicts with source, topic, instruction, response, quality, is_eligible
    """
    from hiveai.llm.client import reason
    from hiveai.config import MIN_TRAINING_QUALITY

    TEACH_TEMPLATE = (
        "You are a training data generator for a coding-focused AI assistant. "
        "Given the following knowledge document, create exactly 3 high-quality "
        "instruction-response pairs that teach this knowledge through code.\n\n"
        "Requirements:\n"
        "- Pair 1: Factual recall — test a specific fact or concept from the text. "
        "Include a code example that demonstrates or verifies the fact.\n"
        "- Pair 2: Implementation — write complete, working code with type hints, "
        "imports, error handling, and inline comments. Show both a basic and "
        "production-ready version.\n"
        "- Pair 3: Synthesis — combine multiple concepts from the text into a "
        "real-world coding scenario with complete runnable code.\n\n"
        "MANDATORY: Every response MUST contain at least one Python code block "
        "with ```python fences. Responses without code are not acceptable.\n\n"
        "Each response should be comprehensive (200+ words), include working code "
        "examples with type hints, and teach the concept thoroughly.\n\n"
        "Format each pair as:\n"
        "INSTRUCTION: <the question or task>\n"
        "RESPONSE: <the comprehensive answer>\n"
        "---\n\n"
        "Knowledge document:\n\n{text}"
    )

    HIVE_TEACH_TEMPLATE = (
        "You are a training data generator specializing in Hive blockchain development. "
        "Given the following Hive-related knowledge document, create exactly 5 high-quality "
        "instruction-response pairs that teach an AI assistant this knowledge.\n\n"
        "Requirements:\n"
        "- Pair 1: Factual recall — test a specific fact, number, or concept from the text\n"
        "- Pair 2: SDK usage — show complete working code using beem (Python) or dhive "
        "(JavaScript) that demonstrates this concept. Include imports, initialization, "
        "error handling, and comments explaining each step.\n"
        "- Pair 3: Operation schema — show the exact JSON structure for the relevant Hive "
        "operation (custom_json, transfer, vote, comment, delegate_vesting_shares, etc.) "
        "with all required and optional fields explained.\n"
        "- Pair 4: Troubleshooting — present a common error or misconfiguration related "
        "to this concept and show the diagnostic steps and fix. Include the actual error "
        "message a developer would see.\n"
        "- Pair 5: Synthesis — combine multiple concepts from the text into a real-world "
        "application scenario showing how they work together in production.\n\n"
        "Each response should be comprehensive (200+ words), include code examples, "
        "and teach the concept thoroughly — not just repeat the source text.\n\n"
        "Format each pair as:\n"
        "INSTRUCTION: <the question or task>\n"
        "RESPONSE: <the comprehensive answer>\n"
        "---\n\n"
        "Knowledge document:\n\n{text}"
    )

    # Split text into chunks of ~3000 chars (~750 tokens) to fit context
    chunk_size = 3000
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size].strip()
        if len(chunk) > 100:  # skip tiny fragments
            chunks.append(chunk)

    if not chunks:
        logger.warning(f"distill_from_text: no usable chunks from '{title}' ({len(text)} chars)")
        return []

    logger.info(f"distill_from_text: '{title}' → {len(chunks)} chunks")
    results = []

    for ci, chunk in enumerate(chunks):
        # Use Hive-specific template (5 pair types) when content is about Hive
        is_hive, _ = _is_hive_content(chunk, title)
        template = HIVE_TEACH_TEMPLATE if is_hive else TEACH_TEMPLATE
        prompt = template.format(text=chunk)
        try:
            raw = reason(prompt)
        except Exception as e:
            logger.warning(f"distill_from_text: LLM call failed for chunk {ci}: {e}")
            continue

        # Parse pairs from response
        pairs_raw = re.split(r'\n---\n', raw)
        for pr in pairs_raw:
            match = re.search(
                r'INSTRUCTION:\s*(.+?)(?:\n\s*\n|\n)RESPONSE:\s*(.+)',
                pr, re.DOTALL
            )
            if not match:
                continue

            instruction = match.group(1).strip()
            response = match.group(2).strip()

            if len(instruction) < 10 or len(response) < 50:
                continue

            quality = _score_quality(instruction, response)
            is_eligible = quality >= MIN_TRAINING_QUALITY

            pair = {
                "source": "human_teaching_hive" if is_hive else "human_teaching",
                "topic": title,
                "instruction": instruction,
                "response": response,
                "quality": round(quality, 4),
                "is_eligible": is_eligible,
            }
            results.append(pair)

            if db and is_eligible:
                _persist_pair(db, pair)

    logger.info(
        f"distill_from_text: '{title}' → {len(results)} pairs, "
        f"{sum(1 for p in results if p['is_eligible'])} eligible"
    )
    return results


def _persist_pair(db, pair: dict, bypass_dedup: bool = False) -> None:
    """Save a generated pair to training_pairs table, running dedup gate first.

    Args:
        bypass_dedup: Skip dedup check (for genetic expansion — mutated instructions
                      have high similarity to originals by design, not because they're
                      duplicates). Quality gate still applies.
    """
    from hiveai.lora.dedup import is_duplicate, add_to_cache
    from hiveai.models import TrainingPair

    from hiveai.config import MIN_TRAINING_QUALITY
    if pair["quality"] < MIN_TRAINING_QUALITY:
        return

    try:
        quality = pair["quality"]
        if not bypass_dedup and is_duplicate(pair["instruction"], db, quality=quality):
            logger.debug(f"Dedup: skipping duplicate instruction for topic '{pair['topic']}'")
            return

        # Clean response before persisting
        clean_resp = _clean_response(pair["response"])

        from hiveai.llm.client import embed_text
        embedding = embed_text(pair["instruction"])

        import json as _json
        tp = TrainingPair(
            source=pair["source"],
            topic=pair["topic"],
            instruction=pair["instruction"],
            response=clean_resp,
            quality=quality,
            is_eligible=pair["is_eligible"],
            metadata_json=_json.dumps(pair["metadata"]) if pair.get("metadata") else None,
            created_at=datetime.now(timezone.utc),
        )
        tp.embedding = embedding
        db.add(tp)
        db.commit()

        # Add to in-memory cache so subsequent dedup checks don't need DB reload
        add_to_cache(embedding, quality=quality)
    except Exception as e:
        logger.error(f"Failed to persist training pair: {e}")
        db.rollback()
