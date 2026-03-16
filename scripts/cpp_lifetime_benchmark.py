#!/usr/bin/env python3
"""C++-lifetime mini-benchmark: RAII, move semantics, const correctness.

Evaluates adapter quality on 15 target prompts + 6 guardrails.
Deterministic: temperature=0, top_k=1, seed=42.

Usage:
    python scripts/cpp_lifetime_benchmark.py [server_url]
"""
import json
import requests
import sys

SERVER_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:11435"
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."

# ---------------------------------------------------------------------------
# Target prompts: RAII (5), Move (5), Const (4) = 14 total
# ---------------------------------------------------------------------------
TARGET_PROMPTS = [
    # --- RAII (5 prompts) ---
    {
        "id": "raii-1-smartptr",
        "prompt": "Explain RAII in C++ and demonstrate the differences between unique_ptr, shared_ptr, and weak_ptr. Show a concrete example where weak_ptr prevents a circular reference memory leak.",
        "keywords": ["unique_ptr", "shared_ptr", "weak_ptr", "RAII", "destructor", "lock", "cycle"],
        "slice": "raii",
    },
    {
        "id": "raii-2-custom-deleter",
        "prompt": "Write a C++ RAII wrapper for a POSIX file descriptor using unique_ptr with a custom deleter. Show how to handle error cases in the constructor and ensure the fd is always closed.",
        "keywords": ["unique_ptr", "deleter", "close", "RAII", "fd", "constructor", "noexcept"],
        "slice": "raii",
    },
    {
        "id": "raii-3-rule-of-five",
        "prompt": "Implement a C++ class that manages a dynamically allocated array, demonstrating the Rule of Five: destructor, copy constructor, copy assignment, move constructor, move assignment. Explain when Rule of Zero is preferable.",
        "keywords": ["destructor", "copy", "move", "assignment", "delete", "rule", "swap"],
        "slice": "raii",
    },
    {
        "id": "raii-4-exception-safety",
        "prompt": "Show how RAII provides exception safety in C++. Write a function that acquires multiple resources (mutex lock, file handle, memory) and demonstrate how RAII ensures cleanup even when an exception is thrown mid-function.",
        "keywords": ["lock_guard", "exception", "RAII", "destructor", "throw", "unique_ptr", "stack"],
        "slice": "raii",
    },
    {
        "id": "raii-5-scope-guard",
        "prompt": "Implement a C++ scope_guard utility (similar to Go's defer) that executes a cleanup lambda when the scope exits, whether normally or via exception. Make it movable but not copyable.",
        "keywords": ["scope", "lambda", "destructor", "move", "noexcept", "delete", "template"],
        "slice": "raii",
    },
    # --- Move Semantics (5 prompts) ---
    {
        "id": "move-1-basics",
        "prompt": "Explain C++ move semantics: what is an rvalue reference (&&), when does the compiler invoke the move constructor vs copy constructor, and write a class with both. Show std::move usage.",
        "keywords": ["move", "&&", "rvalue", "std::move", "constructor", "noexcept", "swap"],
        "slice": "move",
    },
    {
        "id": "move-2-forward",
        "prompt": "Explain the difference between std::move and std::forward in C++. Write a perfect forwarding function template that preserves value categories. Show what happens if you use std::move instead of std::forward.",
        "keywords": ["forward", "move", "&&", "template", "rvalue", "lvalue", "universal"],
        "slice": "move",
    },
    {
        "id": "move-3-rvo",
        "prompt": "Explain Return Value Optimization (RVO) and Named RVO (NRVO) in C++. When does the compiler elide copy/move? Write examples showing when RVO applies and when it doesn't, and the impact of std::move on return statements.",
        "keywords": ["RVO", "NRVO", "elision", "return", "move", "copy", "constructor"],
        "slice": "move",
    },
    {
        "id": "move-4-container",
        "prompt": "Show how move semantics improve performance when inserting objects into a std::vector. Compare push_back with copy vs move, and explain emplace_back. Demonstrate with a class that tracks copies and moves.",
        "keywords": ["push_back", "emplace_back", "move", "copy", "vector", "constructor", "&&"],
        "slice": "move",
    },
    {
        "id": "move-5-pitfalls",
        "prompt": "What are the common pitfalls of move semantics in C++? Show: moved-from state, using an object after std::move, forgetting noexcept on move constructor (and its impact on std::vector reallocation), and why move assignment should check for self-assignment.",
        "keywords": ["moved-from", "noexcept", "self", "vector", "realloc", "valid", "undefined"],
        "slice": "move",
    },
    # --- Const Correctness (4 prompts) ---
    {
        "id": "const-1-basics",
        "prompt": "Demonstrate C++ const correctness: const member functions, const references, const pointers vs pointer to const, constexpr vs const, mutable keyword for logical constness, and east-const vs west-const style. Show how const propagates through function calls.",
        "keywords": ["const", "mutable", "constexpr", "reference", "pointer", "member", "function"],
        "slice": "const",
    },
    {
        "id": "const-2-api",
        "prompt": "Design a C++ class with a const-correct API: provide both const and non-const overloads of operator[], explain the const_cast trick to avoid duplication, and show how to return const references from getters safely.",
        "keywords": ["const", "operator[]", "const_cast", "reference", "overload", "return", "getter"],
        "slice": "const",
    },
    {
        "id": "const-3-move-interaction",
        "prompt": "Explain how const interacts with move semantics in C++. Why can't you move from a const object? What happens when you call std::move on a const lvalue? Show the overload resolution between T&&, const T&, and T& constructors.",
        "keywords": ["const", "move", "&&", "lvalue", "overload", "copy", "constructor"],
        "slice": "const",
    },
    {
        "id": "const-4-propagation",
        "prompt": "Show how const propagates through C++ templates and auto. Explain: const auto&, const auto&&, decltype(auto) with const, and how std::as_const works. When should you use std::cref vs const&?",
        "keywords": ["const", "auto", "decltype", "as_const", "cref", "template", "propagat"],
        "slice": "const",
    },
]

# ---------------------------------------------------------------------------
# Near-neighbor prompts (semantically close, should NOT be degraded)
# ---------------------------------------------------------------------------
NEIGHBOR_PROMPTS = [
    {
        "id": "neighbor-optional",
        "prompt": "Show how to use std::optional in C++ for functions that may not return a value. Compare with returning pointers, demonstrate value_or, and show monadic operations (and_then, transform) from C++23.",
        "keywords": ["optional", "nullopt", "value_or", "has_value", "and_then", "transform"],
        "domain": "cpp-modern",
    },
    {
        "id": "neighbor-variant",
        "prompt": "Implement a type-safe command pattern in C++ using std::variant and std::visit. Show how to handle multiple command types without virtual functions.",
        "keywords": ["variant", "visit", "overloaded", "holds_alternative", "get", "pattern"],
        "domain": "cpp-modern",
    },
]

# ---------------------------------------------------------------------------
# Guardrail prompts (unrelated domains)
# ---------------------------------------------------------------------------
GUARDRAIL_PROMPTS = [
    {
        "id": "guard-hive",
        "prompt": "Explain Hive blockchain resource credits (RC): what they are, how they regenerate, and how to check RC with the beem library.",
        "keywords": ["rc", "mana", "regenerat", "beem", "max_rc", "get_rc", "resource"],
        "domain": "hive",
    },
    {
        "id": "guard-go",
        "prompt": "Implement a Go worker pool pattern with a configurable number of workers, a job channel, and a results channel.",
        "keywords": ["goroutine", "chan", "waitgroup", "worker", "range", "close", "sync"],
        "domain": "go",
    },
    {
        "id": "guard-python",
        "prompt": "Write a Python async generator that reads chunks from an aiohttp response stream, yields parsed JSON objects, and handles backpressure.",
        "keywords": ["async", "yield", "aiohttp", "chunk", "json", "generator", "await"],
        "domain": "python",
    },
    {
        "id": "guard-rust",
        "prompt": "Explain Rust's ownership and borrowing rules with a concrete example showing what the borrow checker prevents and why.",
        "keywords": ["ownership", "borrow", "lifetime", "move", "reference", "mut", "drop"],
        "domain": "rust",
    },
]


def query(prompt: str) -> str:
    resp = requests.post(
        f"{SERVER_URL}/v1/chat/completions",
        json={
            "model": "hiveai",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 2048,
            "top_k": 1,
            "seed": 42,
        },
        timeout=120,
    )
    data = resp.json()
    return data["choices"][0]["message"].get("content", "")


def score(text: str, keywords: list[str]) -> tuple[float, int, int]:
    t = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in t)
    return hits / len(keywords), hits, len(keywords)


def run_benchmark(label: str):
    print(f"\n{'=' * 70}")
    print(f"  C++-Lifetime Benchmark — {label}")
    print(f"  Server: {SERVER_URL}")
    print(f"  Prompts: {len(TARGET_PROMPTS)} target + {len(NEIGHBOR_PROMPTS)} neighbor + {len(GUARDRAIL_PROMPTS)} guardrail")
    print(f"{'=' * 70}")

    # Target prompts by slice
    slice_scores = {"raii": [], "move": [], "const": []}
    print("\n--- TARGET: RAII ---")
    for p in [x for x in TARGET_PROMPTS if x["slice"] == "raii"]:
        resp = query(p["prompt"])
        s, hits, total = score(resp, p["keywords"])
        slice_scores["raii"].append(s)
        print(f"  {s:.3f} ({hits}/{total}) [{p['id']}]")

    print("\n--- TARGET: MOVE ---")
    for p in [x for x in TARGET_PROMPTS if x["slice"] == "move"]:
        resp = query(p["prompt"])
        s, hits, total = score(resp, p["keywords"])
        slice_scores["move"].append(s)
        print(f"  {s:.3f} ({hits}/{total}) [{p['id']}]")

    print("\n--- TARGET: CONST ---")
    for p in [x for x in TARGET_PROMPTS if x["slice"] == "const"]:
        resp = query(p["prompt"])
        s, hits, total = score(resp, p["keywords"])
        slice_scores["const"].append(s)
        print(f"  {s:.3f} ({hits}/{total}) [{p['id']}]")

    # Neighbors
    print("\n--- NEAR-NEIGHBOR ---")
    neighbor_scores = []
    for p in NEIGHBOR_PROMPTS:
        resp = query(p["prompt"])
        s, hits, total = score(resp, p["keywords"])
        neighbor_scores.append(s)
        print(f"  {s:.3f} ({hits}/{total}) [{p['id']}]")

    # Guardrails
    print("\n--- GUARDRAILS ---")
    guard_scores = []
    for p in GUARDRAIL_PROMPTS:
        resp = query(p["prompt"])
        s, hits, total = score(resp, p["keywords"])
        guard_scores.append(s)
        print(f"  {s:.3f} ({hits}/{total}) {p['domain']:>8} [{p['id']}]")

    # Summary
    raii_avg = sum(slice_scores["raii"]) / len(slice_scores["raii"])
    move_avg = sum(slice_scores["move"]) / len(slice_scores["move"])
    const_avg = sum(slice_scores["const"]) / len(slice_scores["const"])
    target_avg = (raii_avg + move_avg + const_avg) / 3
    neighbor_avg = sum(neighbor_scores) / len(neighbor_scores) if neighbor_scores else 0
    guard_avg = sum(guard_scores) / len(guard_scores)

    print(f"\n{'=' * 70}")
    print(f"  SUMMARY — {label}")
    print(f"{'=' * 70}")
    print(f"  RAII avg:      {raii_avg:.3f}  ({len(slice_scores['raii'])} prompts)")
    print(f"  Move avg:      {move_avg:.3f}  ({len(slice_scores['move'])} prompts)")
    print(f"  Const avg:     {const_avg:.3f}  ({len(slice_scores['const'])} prompts)")
    print(f"  TARGET avg:    {target_avg:.3f}  ({len(TARGET_PROMPTS)} prompts)")
    print(f"  Neighbor avg:  {neighbor_avg:.3f}  ({len(NEIGHBOR_PROMPTS)} prompts)")
    print(f"  Guardrail avg: {guard_avg:.3f}  ({len(GUARDRAIL_PROMPTS)} prompts)")
    print(f"{'=' * 70}")

    return {
        "raii": raii_avg, "move": move_avg, "const": const_avg,
        "target": target_avg, "neighbor": neighbor_avg, "guardrail": guard_avg,
    }


if __name__ == "__main__":
    results = run_benchmark("C++-Lifetime")
