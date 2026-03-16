#!/usr/bin/env python3
"""Quick acceptance test: base vs adapter on TS-generics prompts + guardrails."""
import json
import requests
import sys

SERVER_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:11435"
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."

# TS-generics target prompts with keyword rubrics
TARGET_PROMPTS = [
    {
        "prompt": "Write a TypeScript generic function `pipe` that composes N functions with correct type inference, so pipe(f, g, h)(x) infers all intermediate types.",
        "keywords": ["extends", "infer", "generic", "pipe", "compose", "return type", "constraint"],
    },
    {
        "prompt": "Explain TypeScript conditional types with `infer`: show how to extract the return type of a function type using `infer R`.",
        "keywords": ["extends", "infer", "conditional", "ReturnType", "generic", "never"],
    },
    {
        "prompt": "Implement a TypeScript mapped type `Readonly<T>` from scratch and explain how mapped types iterate over keys.",
        "keywords": ["keyof", "in", "mapped", "readonly", "generic", "extends"],
    },
    {
        "prompt": "Write a generic TypeScript function that accepts only objects with a specific shape using extends constraints. Show the error when constraint is violated.",
        "keywords": ["extends", "constraint", "generic", "keyof", "type parameter", "error"],
    },
    {
        "prompt": "Create a variadic tuple type in TypeScript that types a generic `zip` function: zip([1,2], ['a','b']) returns [[1,'a'], [2,'b']] with correct tuple types.",
        "keywords": ["tuple", "variadic", "generic", "infer", "extends", "mapped"],
    },
]

# Guardrail probes (should NOT be affected by adapter)
GUARDRAIL_PROMPTS = [
    {
        "prompt": "Explain Hive blockchain resource credits (RC): what they are, how they regenerate, and how to check RC with the beem library.",
        "keywords": ["rc", "mana", "regenerat", "beem", "max_rc", "get_rc", "resource"],
        "domain": "hive",
    },
    {
        "prompt": "Implement a Go worker pool pattern with a configurable number of workers, a job channel, and a results channel.",
        "keywords": ["goroutine", "chan", "waitgroup", "worker", "range", "close", "sync"],
        "domain": "go",
    },
    {
        "prompt": "Explain RAII in C++ and demonstrate the differences between unique_ptr, shared_ptr, and weak_ptr.",
        "keywords": ["unique_ptr", "shared_ptr", "weak_ptr", "raii", "destructor", "make_unique"],
        "domain": "cpp",
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


def run_suite(label: str):
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"  Server: {SERVER_URL}")
    print(f"{'=' * 60}")

    # Target prompts
    print("\n--- TS-GENERICS TARGET ---")
    target_scores = []
    for i, p in enumerate(TARGET_PROMPTS):
        resp = query(p["prompt"])
        s, hits, total = score(resp, p["keywords"])
        target_scores.append(s)
        print(f"  [{i+1}/{len(TARGET_PROMPTS)}] {s:.3f} ({hits}/{total}) | {p['prompt'][:55]}...")

    avg_target = sum(target_scores) / len(target_scores)
    print(f"  TARGET AVG: {avg_target:.3f}")

    # Guardrail prompts
    print("\n--- GUARDRAILS ---")
    guard_scores = []
    for i, p in enumerate(GUARDRAIL_PROMPTS):
        resp = query(p["prompt"])
        s, hits, total = score(resp, p["keywords"])
        guard_scores.append(s)
        print(f"  [{i+1}/{len(GUARDRAIL_PROMPTS)}] {s:.3f} ({hits}/{total}) {p['domain']:>6} | {p['prompt'][:50]}...")

    avg_guard = sum(guard_scores) / len(guard_scores)
    print(f"  GUARDRAIL AVG: {avg_guard:.3f}")

    print(f"\n  SUMMARY: target={avg_target:.3f}, guardrail={avg_guard:.3f}")
    return avg_target, avg_guard


if __name__ == "__main__":
    run_suite("TS-Generics Acceptance Test")
