#!/usr/bin/env python3
"""Prepare final C++-lifetime training dataset per ChatGPT recommendations.

1. Cut complement pairs to <=10% (only lifetime-adjacent)
2. Truncate most outputs to 1200-1800 chars (keep 20% long)
3. No replay, no non-C++ data
"""
import json
import hashlib
import random
import os

random.seed(42)
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load lifetime core
with open(os.path.join(PROJECT, "loras/training_data/cpp_lifetime_combined.jsonl")) as f:
    lifetime = [json.loads(l) for l in f if l.strip()]

# Load all clean C++ for complement selection
with open(os.path.join(PROJECT, "loras/training_data/untrained/cpp_clean.jsonl")) as f:
    all_cpp = [json.loads(l) for l in f if l.strip()]

lifetime_hashes = set()
for p in lifetime:
    lifetime_hashes.add(hashlib.md5(p["instruction"].strip().lower().encode()).hexdigest())

# TIGHT complement filter: only lifetime-adjacent modern C++
adjacent_kws = ["move-only", "std::optional", "optional", "std::variant", "variant",
                "value category", "visitation", "visit", "raii", "unique_ptr",
                "scope_guard", "lock", "mutex"]
cpp_required = ["c++", "cpp", "std::", "#include"]

complements = []
for p in all_cpp:
    h = hashlib.md5(p["instruction"].strip().lower().encode()).hexdigest()
    if h in lifetime_hashes:
        continue
    instr = p["instruction"].lower()
    out = p.get("output", "")

    is_cpp = any(kw in instr for kw in cpp_required) or ("#include" in out and "std::" in out)
    if not is_cpp:
        continue

    if any(kw in instr for kw in adjacent_kws):
        complements.append(p)

print(f"Lifetime-adjacent complements found: {len(complements)}")
for p in complements[:5]:
    print(f"  {p['instruction'][:100]}")

# Cap at 15 (<=10% of ~140)
if len(complements) > 15:
    complements = random.sample(complements, 15)


def truncate_output(text, max_chars=1600):
    if len(text) <= max_chars:
        return text
    chunk = text[:max_chars]
    # Try to cut at code block boundary
    marker = chunk.rfind("```\n")
    if marker > max_chars * 0.6:
        return text[:marker + 4]
    # Try paragraph boundary
    para = chunk.rfind("\n\n")
    if para > max_chars * 0.6:
        return text[:para]
    # Sentence boundary
    period = chunk.rfind(". ")
    if period > max_chars * 0.5:
        return text[:period + 1]
    return chunk


# Load boundary replay pairs (variant/optional anchors — prevent nearby concept damage)
boundary_path = os.path.join(PROJECT, "loras/training_data/cpp_lifetime_boundary.jsonl")
boundary = []
if os.path.exists(boundary_path):
    with open(boundary_path) as f:
        boundary = [json.loads(l) for l in f if l.strip()]
    print(f"Boundary replay pairs: {len(boundary)}")
else:
    print("No boundary replay file found")

all_pairs = lifetime + complements + boundary
print(f"\nBefore truncation:")
print(f"  Total pairs: {len(all_pairs)}")
avg_before = sum(len(p["output"]) for p in all_pairs) / len(all_pairs)
print(f"  Avg output: {avg_before:.0f} chars")
long_count = sum(1 for p in all_pairs if len(p["output"]) > 1800)
print(f"  Long (>1800): {long_count} ({100 * long_count / len(all_pairs):.0f}%)")

# Keep ~20% of pairs long (randomly selected), truncate the rest
long_indices = set()
all_indices = list(range(len(all_pairs)))
random.shuffle(all_indices)
for i in all_indices:
    if len(all_pairs[i]["output"]) > 1800 and len(long_indices) < int(0.20 * len(all_pairs)):
        long_indices.add(i)

truncated = []
for i, p in enumerate(all_pairs):
    new_p = dict(p)
    if i not in long_indices:
        new_p["output"] = truncate_output(p["output"], 1600)
    truncated.append(new_p)

avg_after = sum(len(p["output"]) for p in truncated) / len(truncated)
long_after = sum(1 for p in truncated if len(p["output"]) > 1800)
print(f"\nAfter truncation:")
print(f"  Avg output: {avg_after:.0f} chars")
print(f"  Long (>1800): {long_after} ({100 * long_after / len(truncated):.0f}%)")

# Write final training dataset
out = os.path.join(PROJECT, "loras/training_data/cpp_lifetime_training.jsonl")
with open(out, "w") as f:
    for p in truncated:
        f.write(json.dumps(p) + "\n")

print(f"\nFinal dataset: {len(truncated)} pairs")
print(f"  Lifetime core: {len(lifetime)} ({100 * len(lifetime) / len(truncated):.0f}%)")
print(f"  Boundary replay: {len(boundary)} ({100 * len(boundary) / len(truncated):.0f}%)")
print(f"  Complement: {len(complements)} ({100 * len(complements) / len(truncated):.0f}%)")
print(f"Written to: {out}")
