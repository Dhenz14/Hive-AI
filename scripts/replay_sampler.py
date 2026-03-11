"""SuRe (Surprise-Driven) Replay Sampler for Continual Learning.

Computes NLL (negative log-likelihood) per sample using llama-server, then
selects the most "surprising" (highest NLL = most forgotten) samples as the
replay buffer. Falls back to diversity sampling if llama-server is unavailable.

Based on: SuRe: Surprise-Driven Prioritised Replay (arXiv 2511.22367, Nov 2025)

Usage:
    # SuRe mode (requires llama-server running on port 11435)
    python scripts/replay_sampler.py --replay-dir replay --keep 500 --output replay/sampled.jsonl

    # Diversity fallback (no server needed)
    python scripts/replay_sampler.py --replay-dir replay --keep 500 --output replay/sampled.jsonl --fallback-diversity
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def detect_category(item: dict) -> str:
    """Detect category of a training pair. Reuses logic from build_replay_buffer.py.

    Uses word boundaries in metadata matching to prevent false positives
    (e.g., "thriving" matching "hive", "gopher" matching "go").
    Content-based detection uses language-specific syntax patterns that are
    unambiguous.
    """
    import re
    text = " ".join(str(v) for v in item.values()).lower()
    meta = item.get("metadata", {})
    source = meta.get("source", "")
    tag = meta.get("tag", "")
    combined = f"{source} {tag}".lower()

    # Metadata-based detection (use word boundaries to avoid false positives)
    if re.search(r"\bhive\b", combined):
        return "hive"
    if re.search(r"\bgo\b|_go\b|golang", combined):
        return "go"
    if re.search(r"\bcpp\b|\bc\+\+\b", combined):
        return "cpp"
    if re.search(r"\brust\b", combined):
        return "rust"
    if re.search(r"\bjavascript\b|\bjs\b|\btypescript\b|\bts\b", combined):
        return "javascript"

    # Content-based detection (language-specific syntax patterns)
    if re.search(r"\bhive\b.*\b(?:blockchain|api|posting|active)\b|dhive|hivejs|beem", text):
        return "hive"
    if re.search(r"\bpackage\s+main\b|go\s+func|goroutine|chan\s+\w+", text):
        return "go"
    if re.search(r"#include\s*<|std::|template\s*<|vector<", text):
        return "cpp"
    if re.search(r"\bfn\s+main|cargo|use\s+std::|impl\s+\w+\s+for\b", text):
        return "rust"
    if re.search(r"\bconst\s+\w+\s*=|async\s+function|=>\s*\{|\.tsx?\b", text):
        return "javascript"

    return "general"


def load_all_replay(replay_dir: str) -> list[dict]:
    """Load all samples from replay/*.jsonl files."""
    samples = []
    replay_path = Path(replay_dir)
    if not replay_path.exists():
        print(f"Warning: replay directory {replay_dir} does not exist")
        return samples

    for jsonl_file in sorted(replay_path.glob("*.jsonl")):
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    sample = json.loads(line)
                    sample.setdefault("domain", detect_category(sample))
                    samples.append(sample)

    return samples


def compute_nll_batch(samples: list[dict], model_url: str,
                      max_samples: int = 1000) -> list[tuple[dict, float]]:
    """Compute NLL per sample via llama-server's /v1/completions endpoint.

    For efficiency, we subsample to max_samples before scoring.
    Returns list of (sample, nll_score) tuples.
    """
    import random
    import requests

    random.seed(42)
    if len(samples) > max_samples:
        candidates = random.sample(samples, max_samples)
    else:
        candidates = samples

    scored = []
    total = len(candidates)
    print(f"  Computing NLL for {total} samples via {model_url}...")
    start = time.time()

    for i, sample in enumerate(candidates):
        text = sample.get("text", "")
        if not text:
            # Build text from instruction/output if 'text' field missing
            inst = sample.get("instruction", "")
            out = sample.get("output", "")
            text = f"{inst}\n{out}" if inst else str(sample)

        # Truncate to avoid timeout on very long samples
        if len(text) > 4000:
            text = text[:4000]

        try:
            resp = requests.post(
                f"{model_url}/v1/completions",
                json={
                    "prompt": text,
                    "max_tokens": 0,
                    "logprobs": 1,
                    "echo": True,
                    "temperature": 0.0,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                logprobs = data.get("choices", [{}])[0].get("logprobs", {})
                token_logprobs = logprobs.get("token_logprobs", [])
                # Skip None entries (first token has no logprob)
                valid_logprobs = [lp for lp in token_logprobs if lp is not None]
                if valid_logprobs:
                    # Average NLL: higher = model is more "surprised" by this
                    # sample = model has forgotten it more = higher replay priority.
                    # This is correct per the SuRe paper (arXiv 2511.22367):
                    # prioritize samples the current model struggles with most.
                    nll = -sum(valid_logprobs) / len(valid_logprobs)
                    sample["nll"] = round(nll, 4)
                    scored.append((sample, nll))
                else:
                    # No logprobs returned — server may have logprobs disabled
                    print(f"    WARNING: No logprobs for sample {i+1} — "
                          "check llama-server supports logprobs")
                    scored.append((sample, 0.0))
            else:
                scored.append((sample, 0.0))
        except (requests.RequestException, KeyError, ValueError):
            scored.append((sample, 0.0))

        if (i + 1) % 100 == 0 or (i + 1) == total:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"    Scored {i + 1}/{total} ({rate:.1f}/s)")

    return scored


def sure_sample(scored: list[tuple[dict, float]], keep: int,
                max_per_domain_pct: float = 0.40) -> list[dict]:
    """Select top-K highest NLL (most forgotten) with diversity constraint."""
    # Sort by NLL descending (highest surprise first)
    scored.sort(key=lambda x: x[1], reverse=True)

    selected = []
    domain_counts = defaultdict(int)
    max_per_domain = int(keep * max_per_domain_pct)

    for sample, nll in scored:
        if len(selected) >= keep:
            break
        domain = sample.get("domain", detect_category(sample))
        if domain_counts[domain] < max_per_domain:
            selected.append(sample)
            domain_counts[domain] += 1

    # If we haven't filled keep yet (due to diversity cap), add remaining
    if len(selected) < keep:
        selected_ids = set(id(s) for s in selected)
        for sample, nll in scored:
            if len(selected) >= keep:
                break
            if id(sample) not in selected_ids:
                selected.append(sample)

    return selected


def domain_balanced_sample(scored: list[tuple[dict, float]], keep: int,
                           domains: list[str] = None) -> list[dict]:
    """Domain-balanced selection: equal samples per domain with SuRe scoring within each.

    Guarantees every domain gets >= keep/N_domains samples. This prevents domain
    starvation where one overrepresented domain crowds out others in replay.

    Within each domain, selects highest-NLL (most forgotten) samples first.
    """
    if domains is None:
        domains = ["hive", "cpp", "rust", "go", "javascript", "general"]

    per_domain = keep // len(domains)
    remainder = keep - per_domain * len(domains)

    # Group by domain
    by_domain = defaultdict(list)
    for sample, nll in scored:
        domain = sample.get("domain", detect_category(sample))
        by_domain[domain].append((sample, nll))

    # Sort each domain by NLL descending (most forgotten first)
    for domain in by_domain:
        by_domain[domain].sort(key=lambda x: x[1], reverse=True)

    selected = []
    overflow = []

    for domain in domains:
        candidates = by_domain.get(domain, [])
        take = per_domain
        actual = candidates[:take]
        selected.extend([s for s, _ in actual])

        # Track unused high-NLL samples for overflow
        if len(candidates) > take:
            overflow.extend(candidates[take:])

    # Collect from unknown domains too
    for domain, candidates in by_domain.items():
        if domain not in domains:
            overflow.extend(candidates)

    # Fill remainder with highest-NLL overflow
    overflow.sort(key=lambda x: x[1], reverse=True)
    for sample, nll in overflow:
        if len(selected) >= keep:
            break
        selected.append(sample)

    return selected[:keep]


def diversity_sample(samples: list[dict], keep: int) -> list[dict]:
    """Fallback: diversity-based sampling (same as build_replay_buffer.py)."""
    import random
    random.seed(42)

    by_category = defaultdict(list)
    for item in samples:
        cat = item.get("domain", detect_category(item))
        by_category[cat].append(item)

    categories = sorted(by_category.keys())
    if not categories:
        return []

    min_per_cat = min(20, keep // len(categories))
    result = []
    remaining = keep

    # First pass: minimum per category
    for cat in categories:
        items = by_category[cat]
        n = min(min_per_cat, len(items))
        sampled = random.sample(items, n)
        result.extend(sampled)
        remaining -= n
        sampled_set = set(id(x) for x in sampled)
        by_category[cat] = [x for x in items if id(x) not in sampled_set]

    # Second pass: proportional fill
    if remaining > 0:
        total_remaining = sum(len(v) for v in by_category.values())
        for cat in categories:
            items = by_category[cat]
            if not items or total_remaining == 0:
                continue
            n = min(int(remaining * len(items) / total_remaining), len(items))
            result.extend(random.sample(items, n))

    result = result[:keep]
    random.shuffle(result)
    return result


def main():
    parser = argparse.ArgumentParser(description="SuRe surprise-driven replay sampler")
    parser.add_argument("--replay-dir", type=str, default="replay",
                        help="Directory with per-domain JSONL files (default: replay/)")
    parser.add_argument("--model-url", type=str, default="http://localhost:11435",
                        help="llama-server URL (default: http://localhost:11435)")
    parser.add_argument("--keep", type=int, default=500,
                        help="Number of replay samples to keep (default: 500)")
    parser.add_argument("--output", type=str, default="replay/sampled.jsonl",
                        help="Output JSONL path")
    parser.add_argument("--max-candidates", type=int, default=1000,
                        help="Max candidates to NLL-score (default: 1000)")
    parser.add_argument("--fallback-diversity", action="store_true",
                        help="Skip NLL scoring, use diversity sampling instead")
    parser.add_argument("--domain-balanced", action="store_true",
                        help="Guarantee equal samples per domain (prevents domain starvation)")
    args = parser.parse_args()

    # Load all replay samples
    samples = load_all_replay(args.replay_dir)
    if not samples:
        print("ERROR: No replay samples found. Populate replay/ directory first.")
        sys.exit(1)

    print(f"Loaded {len(samples)} replay candidates from {args.replay_dir}")

    # Distribution
    dist = defaultdict(int)
    for s in samples:
        dist[s.get("domain", "unknown")] += 1
    print(f"  Distribution: {dict(sorted(dist.items()))}")

    # Select replay buffer
    if args.fallback_diversity:
        print("Using diversity sampling (fallback mode)")
        selected = diversity_sample(samples, args.keep)
    else:
        # Try SuRe NLL scoring
        try:
            import requests
            resp = requests.get(f"{args.model_url}/health", timeout=5)
            if resp.status_code == 200:
                print("llama-server is healthy — using SuRe NLL scoring")
                scored = compute_nll_batch(samples, args.model_url, args.max_candidates)
                if args.domain_balanced:
                    print("  Using domain-balanced selection (equal per domain)")
                    selected = domain_balanced_sample(scored, args.keep)
                else:
                    selected = sure_sample(scored, args.keep)
            else:
                print(f"llama-server returned {resp.status_code} — falling back to diversity sampling")
                selected = diversity_sample(samples, args.keep)
        except Exception as e:
            print(f"llama-server unavailable ({e}) — falling back to diversity sampling")
            selected = diversity_sample(samples, args.keep)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for sample in selected:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # Final stats
    final_dist = defaultdict(int)
    for s in selected:
        final_dist[s.get("domain", "unknown")] += 1
    print(f"\nReplay buffer: {len(selected)} samples -> {args.output}")
    print(f"  Distribution: {dict(sorted(final_dist.items()))}")

    # Report NLL stats if available
    nll_samples = [s for s in selected if s.get("nll") is not None]
    if nll_samples:
        nlls = [s["nll"] for s in nll_samples]
        print(f"  NLL range: {min(nlls):.3f} - {max(nlls):.3f} "
              f"(mean={sum(nlls)/len(nlls):.3f})")


if __name__ == "__main__":
    main()
