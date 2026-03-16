#!/usr/bin/env python3
"""Audit all C++ training pairs across all sources."""
import json
import hashlib
import os

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

absorbed = set()
for f in ["v1.jsonl", "v1_6.jsonl", "v2.jsonl", "v3.jsonl", "v4.jsonl", "v5.jsonl"]:
    path = os.path.join(PROJECT, "loras", "training_data", f)
    if not os.path.exists(path):
        continue
    with open(path) as fh:
        for line in fh:
            if line.strip():
                absorbed.add(hashlib.md5(line.strip().encode()).hexdigest())

def is_cpp(pair):
    instr = pair.get("instruction", "").lower()
    output = pair.get("output", "")
    non_cpp = ["python", "django", "flask", "pandas", "pip install",
               "rust ", "cargo ", "tokio", "golang", "goroutine",
               "javascript", "react ", "node.js", "npm ",
               "hive ", "beem", "blockchain", "decentralized",
               "java ", "spring", "kotlin"]
    if any(kw in instr for kw in non_cpp):
        return False
    cpp_instr = ["c++", "cpp", "raii", "unique_ptr", "shared_ptr", "weak_ptr",
                 "move semantic", "move constructor", "std::move", "std::forward",
                 "constexpr", "cmake", "variadic template", "smart pointer",
                 "destructor", "rule of five", "rule of zero", "const correct",
                 "template<", "stl", "std::", "#include <",
                 "c++17", "c++20", "c++23", "namespace", "nullptr",
                 "operator overload", "crtp", "sfinae", "concepts ",
                 "coroutine", "co_await", "ranges", "jthread",
                 "lambda", "std::optional", "std::variant", "std::format"]
    if any(kw in instr for kw in cpp_instr):
        return True
    cpp_output = ["#include <", "std::", "nullptr", "template<", "auto "]
    if sum(1 for m in cpp_output if m in output) >= 2:
        return True
    return False

lifetime_kws = ["raii", "unique_ptr", "shared_ptr", "weak_ptr", "move",
                "destructor", "ownership", "rule of five", "rule of zero",
                "const correct", "mutable", "scope_guard", "exception safe",
                "custom deleter", "copy-on-write", "smart pointer",
                "make_unique", "make_shared", "enable_shared_from_this",
                "copy constructor", "move assignment", "const_cast"]

sources = [
    ("v6 (FAILED)", "loras/training_data/v6.jsonl"),
    ("v7 (FAILED)", "loras/training_data/v7.jsonl"),
    ("new_pairs_cpp_core", "loras/training_data/new_pairs_cpp_core.jsonl"),
    ("new_pairs_cpp_systems", "loras/training_data/new_pairs_cpp_systems.jsonl"),
    ("new_pairs_merged_512", "loras/training_data/new_pairs_merged_512.jsonl"),
    ("cpp_recovery", "datasets/cpp_recovery.jsonl"),
    ("v8_go_cpp", "loras/training_data/v8_go_cpp_pairs.jsonl"),
    ("v9_research", "loras/training_data/v9_research_pairs.jsonl"),
    ("replay/cpp", "replay/cpp.jsonl"),
    ("categories/cpp_replay", "loras/training_data/categories/cpp_with_replay.jsonl"),
]

seen = set()
total_cpp = 0
total_lifetime = 0
total_other = 0
untrained_cpp = 0
all_untrained_pairs = []

hdr = f"{'Source':<28} {'Total':>6} {'C++':>5} {'Life':>5} {'Other':>5} {'Untrained':>10}"
print(hdr)
print("-" * len(hdr))

for label, rel_path in sources:
    path = os.path.join(PROJECT, rel_path)
    if not os.path.exists(path):
        continue
    with open(path) as fh:
        lines = [l for l in fh if l.strip()]

    total = len(lines)
    cpp_count = life_count = other_count = new_cpp = 0

    for line in lines:
        pair = json.loads(line.strip())
        h = hashlib.md5(line.strip().encode()).hexdigest()
        if not is_cpp(pair):
            continue
        if h in seen:
            continue
        seen.add(h)
        cpp_count += 1
        instr = pair.get("instruction", "").lower()
        if any(kw in instr for kw in lifetime_kws):
            life_count += 1
        else:
            other_count += 1
        if h not in absorbed:
            new_cpp += 1
            all_untrained_pairs.append(pair)

    total_cpp += cpp_count
    total_lifetime += life_count
    total_other += other_count
    untrained_cpp += new_cpp

    if cpp_count > 0:
        print(f"{label:<28} {total:>6} {cpp_count:>5} {life_count:>5} {other_count:>5} {new_cpp:>10}")

print("-" * len(hdr))
print(f"{'TOTAL (deduplicated)':<28} {'':>6} {total_cpp:>5} {total_lifetime:>5} {total_other:>5} {untrained_cpp:>10}")

# Write all untrained C++ pairs
out_path = os.path.join(PROJECT, "loras", "training_data", "untrained", "cpp_all_untrained.jsonl")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f:
    for p in all_untrained_pairs:
        f.write(json.dumps(p) + "\n")
print(f"\nWrote {len(all_untrained_pairs)} untrained C++ pairs to {out_path}")

# Show sample of untrained lifetime pairs
print("\n--- UNTRAINED LIFETIME-FOCUSED (sample) ---")
life_pairs = [p for p in all_untrained_pairs
              if any(kw in p.get("instruction","").lower() for kw in lifetime_kws)]
for p in life_pairs[:8]:
    print(f"  {p.get('instruction','')[:90]}")
print(f"  ... total: {len(life_pairs)}")

print("\n--- UNTRAINED OTHER C++ (sample) ---")
other_pairs = [p for p in all_untrained_pairs
               if not any(kw in p.get("instruction","").lower() for kw in lifetime_kws)]
for p in other_pairs[:8]:
    print(f"  {p.get('instruction','')[:90]}")
print(f"  ... total: {len(other_pairs)}")
