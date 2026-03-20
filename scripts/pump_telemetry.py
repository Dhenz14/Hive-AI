#!/usr/bin/env python3
"""Pump diverse queries through the chat API for telemetry collection."""
import requests
import time
import sys

URL = "http://localhost:5001/api/chat"
TIMEOUT = 120

QUESTIONS = [
    # Python (10)
    "What is a Python list comprehension? Give one example.",
    "Write a Python context manager for timing code blocks.",
    "Explain Python's GIL and how to work around it for CPU-bound tasks.",
    "Write a Python async generator that yields fibonacci numbers.",
    "How do Python descriptors work? Show __get__ and __set__ example.",
    "Implement a simple LRU cache decorator in Python.",
    "What are Python metaclasses? When would you use one?",
    "Write a Python function that flattens nested dictionaries.",
    "Explain Python slots and when to use them.",
    "How does Python garbage collection work? Explain reference counting vs cyclic GC.",
    # Rust (5)
    "How do I handle errors in Rust with Result and the ? operator?",
    "Write a Rust function that safely shares data between threads using Arc and Mutex.",
    "What are Rust lifetimes? Explain with a function that returns a reference.",
    "Explain Rust's ownership model. What happens when you move a value?",
    "Write a Rust trait with a default implementation and show polymorphism.",
    # Go (5)
    "Write a Go function that reverses a linked list.",
    "How do goroutines differ from OS threads?",
    "Implement a simple pub/sub system in Go using channels.",
    "Write a Go HTTP middleware that logs request duration.",
    "Explain Go interfaces and show the empty interface pattern.",
    # C++ (5)
    "What is RAII in C++? Show a simple example.",
    "What is move semantics in C++11? Show before/after code.",
    "Implement a simple smart pointer in C++ (unique_ptr equivalent).",
    "Explain C++ templates and SFINAE with a practical example.",
    "Write a C++ class with rule of five (copy/move constructors and assignment).",
    # TypeScript/JavaScript (5)
    "Write a TypeScript utility type that makes all nested properties optional.",
    "Explain the JavaScript event loop with a code example.",
    "Write a JavaScript debounce function with TypeScript types.",
    "How do TypeScript generics work? Show a generic stack implementation.",
    "Explain JavaScript closures and show a practical use case.",
    # Hive (5)
    "How does Hive DPoS consensus work?",
    "How do Hive custom_json operations work for layer 2 apps?",
    "How does the Hive reward pool distribute author vs curator rewards?",
    "How do I broadcast a Hive transaction using the dhive library?",
    "What is Hive Engine and how do custom tokens work on Hive?",
    # Architecture/Design (5)
    "Explain the CAP theorem with a concrete example.",
    "What is event sourcing? When should you use it over CRUD?",
    "Explain database sharding strategies and their tradeoffs.",
    "What is the circuit breaker pattern? Show a simple implementation.",
    "Explain CQRS and how it pairs with event sourcing.",
    # Debugging (5)
    "I get 'TypeError: Cannot read properties of undefined' in React. How do I debug?",
    "My Python script uses 100% CPU. How do I profile and fix it?",
    "How do I debug a memory leak in a Node.js application?",
    "My Go program has a goroutine leak. How do I find and fix it?",
    "How do I debug a segfault in a C++ program using gdb?",
    # Comparison/Cross-domain (5)
    "Compare async/await in Python vs JavaScript. Key differences?",
    "When should I use PostgreSQL vs MongoDB?",
    "Compare Rust's Result type vs Go's error handling pattern.",
    "What are the tradeoffs between REST and GraphQL?",
    "Compare Docker Compose vs Kubernetes for small teams.",
]

def main():
    success = 0
    failed = 0
    for i, q in enumerate(QUESTIONS):
        try:
            t0 = time.time()
            r = requests.post(URL, json={"message": q}, timeout=TIMEOUT)
            elapsed = time.time() - t0
            if r.status_code == 200:
                d = r.json()
                reply_len = len(d.get("reply", ""))
                sources = len(d.get("sources", []) or [])
                print(f"[{i+1}/{len(QUESTIONS)}] {elapsed:.0f}s | {reply_len}ch | {sources}src | {q[:60]}")
                success += 1
            else:
                print(f"[{i+1}/{len(QUESTIONS)}] HTTP {r.status_code} in {elapsed:.0f}s | {q[:60]}")
                failed += 1
        except Exception as e:
            print(f"[{i+1}/{len(QUESTIONS)}] ERROR: {str(e)[:50]} | {q[:60]}")
            failed += 1

    print(f"\nDone: {success} success, {failed} failed out of {len(QUESTIONS)}")

    # Check telemetry
    import sqlite3
    conn = sqlite3.connect("hiveai.db")
    conn.execute("PRAGMA wal_checkpoint(FULL)")
    t = conn.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0]
    groups = conn.execute(
        "SELECT experiment_group, COUNT(*) FROM telemetry_events GROUP BY experiment_group"
    ).fetchall()
    print(f"\nTelemetry: {t} events")
    for g, c in groups:
        print(f"  {g}: {c}")


if __name__ == "__main__":
    main()
