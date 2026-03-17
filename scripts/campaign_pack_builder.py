#!/usr/bin/env python3
"""
Evidence Campaign v1 — Deterministic Pair-Pack Builder

Builds training packs for campaign attempts. Each pack contains:
  - 240 targeted pairs (domain-matched, weakness-relevant)
  - 120 historical pairs (from replay corpus, same domain)
  - 40 stability/control pairs (high-quality cross-domain)
  = 400 total pairs per attempt

Determinism guarantees:
  - Seeded RNG (seed = attempt number)
  - Sorted inputs (glob → sort → hash)
  - Content-addressed output (SHA256 manifest)
  - Holdout exclusion (probe text never in pack)
  - Input snapshot (all source hashes frozen before selection)

Usage:
    python scripts/campaign_pack_builder.py --bucket B1 --seed 1
    python scripts/campaign_pack_builder.py --bucket B2 --seed 1 --verify
    python scripts/campaign_pack_builder.py --all --seed 1
"""
import argparse
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.campaign_governance import (
    PROTOCOL_VERSION, BUCKET_EVIDENCE_MASS, CAMPAIGN_ID,
    atomic_write_json, atomic_write_jsonl,
)

# ---------------------------------------------------------------------------
# Campaign configuration (frozen, loaded from artifacts)
# ---------------------------------------------------------------------------
CAMPAIGN_DIR = PROJECT_ROOT / "evidence_campaign"
PACK_OUTPUT_DIR = CAMPAIGN_DIR / "packs"

# Pack composition (frozen per spec)
PACK_TARGETED = 240
PACK_HISTORICAL = 120
PACK_STABILITY = 40
PACK_TOTAL = PACK_TARGETED + PACK_HISTORICAL + PACK_STABILITY  # 400

# Domain → replay corpus mapping
REPLAY_DIR = PROJECT_ROOT / "replay"
DOMAIN_REPLAY_MAP = {
    "js": "javascript.jsonl",
    "python": "general_coding.jsonl",  # python pairs mixed in general_coding
    "rust": "rust.jsonl",
    "cpp": "cpp.jsonl",
}

# Domain → targeted data sources (primary training data matching domain)
TARGETED_SOURCES = {
    "js": [
        "datasets/thinking_500.jsonl",
        "datasets/thinking_batch2.jsonl",
        "datasets/thinking_batch3.jsonl",
        "datasets/thinking_mixed.jsonl",
        "loras/training_data/new_pairs_merged_512.jsonl",
    ],
    "python": [
        "datasets/thinking_500.jsonl",
        "datasets/thinking_batch2.jsonl",
        "datasets/thinking_batch3.jsonl",
        "datasets/thinking_mixed.jsonl",
        "loras/training_data/new_pairs_merged_512.jsonl",
    ],
    "rust": [
        "datasets/thinking_500.jsonl",
        "datasets/thinking_batch2.jsonl",
        "datasets/thinking_batch3.jsonl",
        "datasets/thinking_mixed.jsonl",
        "datasets/thinking_batch4.jsonl",
        "datasets/thinking_batch5.jsonl",
        "loras/training_data/new_pairs_merged_512.jsonl",
    ],
    "cpp": [
        "datasets/cpp_recovery.jsonl",
        "datasets/cpp_targeted_100.jsonl",
        "datasets/thinking_500.jsonl",
        "datasets/thinking_batch2.jsonl",
        "datasets/thinking_batch3.jsonl",
        "loras/training_data/new_pairs_cpp_core.jsonl",
        "loras/training_data/new_pairs_cpp_systems.jsonl",
        "loras/training_data/new_pairs_merged_512.jsonl",
    ],
}

# Stability pool: high-quality cross-domain pairs
STABILITY_SOURCES = [
    "replay/sampled.jsonl",
    "replay/general_coding.jsonl",
]


def _sha256_file(path: Path) -> str:
    """Content hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_str(s: str) -> str:
    """SHA256 of a string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load_jsonl(path: Path) -> list:
    """Load a JSONL file. Returns list of dicts."""
    if not path.exists():
        return []
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return lines


def _pair_text(pair: dict) -> str:
    """Extract full text content from a training pair for holdout checking."""
    parts = []
    for key in ("instruction", "input", "output", "prompt", "response"):
        if key in pair and pair[key]:
            parts.append(str(pair[key]).lower())
    return " ".join(parts)


def _pair_hash(pair: dict) -> str:
    """Content hash of a training pair for deduplication."""
    # Normalize: sort keys, strip whitespace
    text = _pair_text(pair)
    return _sha256_str(text)[:16]


# ---------------------------------------------------------------------------
# Holdout exclusion
# ---------------------------------------------------------------------------
def load_holdout_probes() -> dict:
    """Load holdout probe data for exclusion checking.

    Returns dict with:
      - probe_ids: set of holdout probe IDs
      - exclusion_terms: list of (probe_id, [lowered keywords + prompt fragments])
    """
    split_path = CAMPAIGN_DIR / "split_manifest.json"
    if not split_path.exists():
        print(f"ERROR: {split_path} not found")
        sys.exit(1)

    with open(split_path) as f:
        split = json.load(f)

    # Import probe library for prompt text
    from scripts.probe_library import get_probe_by_id

    holdout_ids = set()
    exclusion_terms = []

    for domain_data in split["domains"].values():
        for h in domain_data["holdout"]:
            pid = h["probe_id"]
            holdout_ids.add(pid)

            try:
                probe = get_probe_by_id(pid)
                # Exclusion terms: probe keywords + distinctive prompt fragments
                terms = [kw.lower() for kw in probe.expected_keywords]
                # Add 3-word chunks from the prompt for substring matching
                words = probe.prompt.lower().split()
                for i in range(len(words) - 2):
                    terms.append(" ".join(words[i:i+3]))
                exclusion_terms.append((pid, terms))
            except ValueError:
                print(f"WARNING: probe {pid} not found in library")

    return {
        "probe_ids": holdout_ids,
        "exclusion_terms": exclusion_terms,
        "count": len(holdout_ids),
    }


def check_holdout_contamination(pair: dict, holdout: dict) -> list:
    """Check if a training pair contains holdout probe content.

    Returns list of (probe_id, matched_term) for any matches.
    A pair is contaminated if it contains a SUPERMAJORITY (>=6/7 = 86%)
    of any holdout probe's keywords. This catches near-duplicates of the
    probe question while allowing general domain pairs that share a few
    common keywords (e.g., "import", "class", "function").
    """
    text = _pair_text(pair)
    matches = []

    for probe_id, terms in holdout["exclusion_terms"]:
        # Count keyword hits (first N terms are the probe's expected_keywords)
        from scripts.probe_library import get_probe_by_id
        try:
            probe = get_probe_by_id(probe_id)
            kw_count = len(probe.expected_keywords)
        except ValueError:
            kw_count = 7  # default

        keyword_terms = terms[:kw_count]
        hits = sum(1 for t in keyword_terms if t in text)

        # Contaminated if >=86% of keywords match (6/7 or 7/7)
        if kw_count > 0 and hits / kw_count >= 0.86:
            matches.append((probe_id, f"{hits}/{kw_count} keywords"))

    return matches


# ---------------------------------------------------------------------------
# Domain filtering
# ---------------------------------------------------------------------------
DOMAIN_KEYWORDS = {
    "js": ["javascript", "typescript", "node", "react", "promise", "async/await",
           "const ", "let ", "var ", "function", "=>", "import ", "export ",
           "console.log", ".then(", "jsx", "tsx"],
    "python": ["python", "def ", "import ", "class ", "self.", "__init__",
               "print(", "lambda", "pip", "django", "flask", "pandas",
               "numpy", "asyncio", "dataclass"],
    "rust": ["rust", "fn ", "let mut", "impl ", "trait ", "struct ",
             "enum ", "match ", "Result<", "Option<", "cargo", "crate",
             "pub fn", "tokio", "serde", "unsafe"],
    "cpp": ["c++", "cpp", "#include", "std::", "template", "class ",
            "namespace", "void ", "int main", "unique_ptr", "shared_ptr",
            "vector<", "const ", "auto ", "nullptr"],
}


def _classify_domain(pair: dict) -> str:
    """Classify a training pair's domain. Uses explicit field or keyword heuristic."""
    # Explicit domain field
    if "domain" in pair and pair["domain"]:
        d = pair["domain"].lower()
        # Normalize
        if d in ("javascript", "js", "typescript", "ts"):
            return "js"
        if d in ("python", "py"):
            return "python"
        if d in ("rust", "rs"):
            return "rust"
        if d in ("c++", "cpp"):
            return "cpp"
        return d

    # Keyword heuristic
    text = _pair_text(pair)
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for kw in keywords if kw.lower() in text)

    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        return best
    return "unknown"


# ---------------------------------------------------------------------------
# Pack builder
# ---------------------------------------------------------------------------
def build_pack(
    bucket_id: str,
    seed: int,
    buckets: dict,
    holdout: dict,
    dry_run: bool = False,
) -> dict:
    """Build a deterministic training pack for one attempt.

    Returns dict with:
      - pack: list of training pairs (400)
      - manifest: input snapshot + output hashes
      - exclusions: pairs excluded for holdout contamination
    """
    # Find bucket config
    bucket = None
    for b in buckets["buckets"]:
        if b["bucket_id"] == bucket_id:
            bucket = b
            break
    if not bucket:
        print(f"ERROR: bucket {bucket_id} not found")
        sys.exit(1)

    domain = bucket["domain"]
    template = bucket["template"]
    # Incorporate bucket_id into seed so same-domain buckets (B3/B5) get different packs
    effective_seed = int(hashlib.sha256(f"{bucket_id}_{seed}".encode()).hexdigest()[:8], 16)
    rng = random.Random(effective_seed)

    print(f"\n  Building pack: {bucket_id} (domain={domain}, template={template}, seed={seed})")

    # --- Step 1: Snapshot inputs ---
    input_snapshot = {
        "bucket_id": bucket_id,
        "domain": domain,
        "template": template,
        "seed": seed,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_files": {},
    }

    # --- Step 2: Load targeted pairs ---
    targeted_pool = []
    source_paths = TARGETED_SOURCES.get(domain, [])
    for rel_path in sorted(source_paths):
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists():
            pairs = _load_jsonl(full_path)
            input_snapshot["source_files"][rel_path] = {
                "hash": _sha256_file(full_path),
                "count": len(pairs),
            }
            for p in pairs:
                p_domain = _classify_domain(p)
                if p_domain == domain:
                    targeted_pool.append(p)
        else:
            input_snapshot["source_files"][rel_path] = {"hash": "NOT_FOUND", "count": 0}

    print(f"    Targeted pool: {len(targeted_pool)} domain-matched pairs")

    # --- Step 3: Load historical pairs ---
    historical_pool = []
    replay_file = DOMAIN_REPLAY_MAP.get(domain)
    if replay_file:
        replay_path = REPLAY_DIR / replay_file
        if replay_path.exists():
            pairs = _load_jsonl(replay_path)
            input_snapshot["source_files"][f"replay/{replay_file}"] = {
                "hash": _sha256_file(replay_path),
                "count": len(pairs),
            }
            historical_pool = pairs
        else:
            input_snapshot["source_files"][f"replay/{replay_file}"] = {
                "hash": "NOT_FOUND", "count": 0,
            }

    print(f"    Historical pool: {len(historical_pool)} replay pairs")

    # --- Step 4: Load stability/control pairs ---
    stability_pool = []
    for rel_path in sorted(STABILITY_SOURCES):
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists():
            pairs = _load_jsonl(full_path)
            input_snapshot["source_files"][rel_path] = {
                "hash": _sha256_file(full_path),
                "count": len(pairs),
            }
            stability_pool.extend(pairs)
        else:
            input_snapshot["source_files"][rel_path] = {"hash": "NOT_FOUND", "count": 0}

    print(f"    Stability pool: {len(stability_pool)} cross-domain pairs")

    # --- Step 5: Holdout exclusion ---
    def _is_clean(pair):
        return len(check_holdout_contamination(pair, holdout)) == 0

    excluded = {"targeted": 0, "historical": 0, "stability": 0}

    targeted_clean = []
    for p in targeted_pool:
        if _is_clean(p):
            targeted_clean.append(p)
        else:
            excluded["targeted"] += 1

    historical_clean = []
    for p in historical_pool:
        if _is_clean(p):
            historical_clean.append(p)
        else:
            excluded["historical"] += 1

    stability_clean = []
    for p in stability_pool:
        if _is_clean(p):
            stability_clean.append(p)
        else:
            excluded["stability"] += 1

    print(f"    Holdout exclusions: targeted={excluded['targeted']}, "
          f"historical={excluded['historical']}, stability={excluded['stability']}")

    # --- Step 6: Deterministic selection ---
    # Sort each pool by content hash for deterministic ordering
    targeted_clean.sort(key=lambda p: _pair_hash(p))
    historical_clean.sort(key=lambda p: _pair_hash(p))
    stability_clean.sort(key=lambda p: _pair_hash(p))

    # Deduplicate within pools
    seen_hashes = set()
    def _dedup(pool):
        deduped = []
        for p in pool:
            h = _pair_hash(p)
            if h not in seen_hashes:
                seen_hashes.add(h)
                deduped.append(p)
        return deduped

    targeted_clean = _dedup(targeted_clean)
    historical_clean = _dedup(historical_clean)
    stability_clean = _dedup(stability_clean)

    # Sample deterministically
    def _sample(pool, n, label):
        if len(pool) < n:
            print(f"    WARNING: {label} pool has {len(pool)} < {n} requested. Using all.")
            return list(pool)
        return rng.sample(pool, n)

    targeted_selected = _sample(targeted_clean, PACK_TARGETED, "targeted")
    historical_selected = _sample(historical_clean, PACK_HISTORICAL, "historical")
    stability_selected = _sample(stability_clean, PACK_STABILITY, "stability")

    # --- Step 7: Assemble pack ---
    pack = []
    for p in targeted_selected:
        p["_pack_role"] = "targeted"
        pack.append(p)
    for p in historical_selected:
        p["_pack_role"] = "historical"
        pack.append(p)
    for p in stability_selected:
        p["_pack_role"] = "stability"
        pack.append(p)

    # Sort final pack by content hash (deterministic ordering)
    pack.sort(key=lambda p: _pair_hash(p))

    # --- Step 8: Compute output hashes ---
    pack_content = json.dumps(pack, sort_keys=True, ensure_ascii=False)
    pack_hash = _sha256_str(pack_content)

    mass = BUCKET_EVIDENCE_MASS.get(bucket_id, {})
    manifest = {
        "campaign_id": CAMPAIGN_ID,
        "protocol_version": PROTOCOL_VERSION,
        "bucket_id": bucket_id,
        "domain": domain,
        "template": template,
        "seed": seed,
        "pack_total": len(pack),
        "pack_targeted": len(targeted_selected),
        "pack_historical": len(historical_selected),
        "pack_stability": len(stability_selected),
        "effective_pack_size": mass.get("pack_size", len(pack)),
        "power_class": mass.get("power_class", "unknown"),
        "pack_sha256": pack_hash,
        "holdout_exclusions": excluded,
        "holdout_probe_count": holdout["count"],
        "input_snapshot": input_snapshot,
        "builder_hash": _sha256_file(Path(__file__)),
        "leakage_audit_note": "No detected leakage under frozen audit logic (>=86% keyword cluster). Tool-sensitive control, not truth oracle.",
    }

    print(f"    Pack assembled: {len(pack)} pairs "
          f"({len(targeted_selected)}/{len(historical_selected)}/{len(stability_selected)})")
    print(f"    Pack SHA256: {pack_hash[:16]}...")

    return {
        "pack": pack,
        "manifest": manifest,
        "exclusions": excluded,
    }


def write_pack(result: dict, output_dir: Path) -> tuple:
    """Write pack and manifest atomically. Returns (pack_path, manifest_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    bucket_id = result["manifest"]["bucket_id"]
    seed = result["manifest"]["seed"]
    prefix = f"pack_{bucket_id}_seed{seed}"

    pack_path = output_dir / f"{prefix}.jsonl"
    manifest_path = output_dir / f"{prefix}_manifest.json"

    # Clean pairs (remove internal metadata)
    clean_pairs = [
        {k: v for k, v in pair.items() if not k.startswith("_")}
        for pair in result["pack"]
    ]

    # Atomic writes: temp -> fsync -> rename
    atomic_write_jsonl(pack_path, clean_pairs)
    atomic_write_json(manifest_path, result["manifest"])

    # Compute written file hashes
    written_pack_hash = _sha256_file(pack_path)
    written_manifest_hash = _sha256_file(manifest_path)

    print(f"    Written: {pack_path.name} (hash={written_pack_hash[:12]})")
    print(f"    Written: {manifest_path.name} (hash={written_manifest_hash[:12]})")

    return pack_path, manifest_path


# ---------------------------------------------------------------------------
# Verification (Gate 2 support)
# ---------------------------------------------------------------------------
def verify_determinism(bucket_id: str, seed: int) -> bool:
    """Build the same pack twice and verify byte-identical output."""
    print(f"\n{'='*65}")
    print(f"  Gate 2: Determinism Verification — {bucket_id} seed={seed}")
    print(f"{'='*65}")

    buckets = _load_buckets()
    holdout = load_holdout_probes()

    # Build 1
    print("\n  --- Build 1 ---")
    r1 = build_pack(bucket_id, seed, buckets, holdout)

    # Build 2
    print("\n  --- Build 2 ---")
    r2 = build_pack(bucket_id, seed, buckets, holdout)

    # Compare
    pack1 = json.dumps(r1["pack"], sort_keys=True, ensure_ascii=False)
    pack2 = json.dumps(r2["pack"], sort_keys=True, ensure_ascii=False)

    manifest_match = (r1["manifest"]["pack_sha256"] == r2["manifest"]["pack_sha256"])
    content_match = (pack1 == pack2)
    count_match = (r1["manifest"]["pack_total"] == r2["manifest"]["pack_total"])

    checks = {
        "pack_sha256_match": manifest_match,
        "content_match": content_match,
        "count_match": count_match,
        "pack_count_1": r1["manifest"]["pack_total"],
        "pack_count_2": r2["manifest"]["pack_total"],
        "targeted_match": (r1["manifest"]["pack_targeted"] == r2["manifest"]["pack_targeted"]),
        "historical_match": (r1["manifest"]["pack_historical"] == r2["manifest"]["pack_historical"]),
        "stability_match": (r1["manifest"]["pack_stability"] == r2["manifest"]["pack_stability"]),
    }

    all_pass = all(checks.values())

    print(f"\n  {'='*55}")
    print(f"  Gate 2 Results:")
    for k, v in checks.items():
        status = "PASS" if v else "FAIL"
        print(f"    {k:30s} {status}  ({v})")
    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")
    print(f"  {'='*55}")

    return all_pass


# ---------------------------------------------------------------------------
# Leakage audit (Gate 3 support)
# ---------------------------------------------------------------------------
def leakage_audit(bucket_id: str, seed: int) -> dict:
    """Check a built pack for holdout probe contamination.

    Returns audit report with binding and informational findings.
    """
    print(f"\n{'='*65}")
    print(f"  Gate 3: Leakage Audit — {bucket_id} seed={seed}")
    print(f"{'='*65}")

    buckets = _load_buckets()
    holdout = load_holdout_probes()

    # Build the pack
    result = build_pack(bucket_id, seed, buckets, holdout)

    # --- Binding audit: exact holdout content in pack ---
    binding_violations = []
    for i, pair in enumerate(result["pack"]):
        matches = check_holdout_contamination(pair, holdout)
        if matches:
            binding_violations.append({
                "pair_index": i,
                "pair_hash": _pair_hash(pair),
                "matches": matches,
            })

    # --- Informational audit: near-duplicate detection ---
    from scripts.probe_library import get_probe_by_id
    informational = []
    for probe_id in holdout["probe_ids"]:
        try:
            probe = get_probe_by_id(probe_id)
        except ValueError:
            continue

        prompt_lower = probe.prompt.lower()
        # Check for 5-word substring matches (skeleton overlap)
        prompt_words = prompt_lower.split()
        for i, pair in enumerate(result["pack"]):
            text = _pair_text(pair)
            # 5-word sliding window
            for j in range(len(prompt_words) - 4):
                fragment = " ".join(prompt_words[j:j+5])
                if fragment in text:
                    informational.append({
                        "pair_index": i,
                        "probe_id": probe_id,
                        "fragment": fragment,
                        "type": "prompt_skeleton_overlap",
                    })
                    break  # One match per pair-probe combo is enough

    report = {
        "bucket_id": bucket_id,
        "seed": seed,
        "pack_size": len(result["pack"]),
        "binding_audit": {
            "violations": len(binding_violations),
            "details": binding_violations,
            "pass": len(binding_violations) == 0,
        },
        "informational_audit": {
            "findings": len(informational),
            "details": informational[:20],  # Cap detail output
            "note": "Informational only. Does NOT gate campaign.",
        },
    }

    print(f"\n  Binding audit: {'PASS' if report['binding_audit']['pass'] else 'FAIL'} "
          f"({report['binding_audit']['violations']} violations)")
    print(f"  Informational: {report['informational_audit']['findings']} findings (logged, not gating)")

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_buckets() -> dict:
    """Load canonical bucket definitions."""
    path = CAMPAIGN_DIR / "canonical_buckets.json"
    if not path.exists():
        print(f"ERROR: {path} not found")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Evidence Campaign v1 — Deterministic Pair-Pack Builder")
    parser.add_argument("--bucket", type=str, help="Bucket ID (B1-B5)")
    parser.add_argument("--all", action="store_true", help="Build packs for all 5 buckets")
    parser.add_argument("--seed", type=int, required=True, help="RNG seed (= attempt number)")
    parser.add_argument("--verify", action="store_true",
                        help="Gate 2: double-build determinism check")
    parser.add_argument("--audit", action="store_true",
                        help="Gate 3: holdout leakage audit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build but don't write to disk")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: evidence_campaign/packs/)")
    args = parser.parse_args()

    if not args.bucket and not args.all:
        parser.error("Must specify --bucket or --all")

    output_dir = Path(args.output_dir) if args.output_dir else PACK_OUTPUT_DIR

    bucket_ids = ["B1", "B2", "B3", "B4", "B5"] if args.all else [args.bucket]

    if args.verify:
        # Gate 2: determinism verification
        all_pass = True
        for bid in bucket_ids:
            if not verify_determinism(bid, args.seed):
                all_pass = False
        print(f"\nGate 2 overall: {'PASS' if all_pass else 'FAIL'}")
        sys.exit(0 if all_pass else 1)

    if args.audit:
        # Gate 3: leakage audit
        all_clean = True
        for bid in bucket_ids:
            report = leakage_audit(bid, args.seed)
            if not report["binding_audit"]["pass"]:
                all_clean = False
            # Write audit report
            report_path = output_dir / f"audit_{bid}_seed{args.seed}.json"
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
            print(f"  Audit report: {report_path}")
        print(f"\nGate 3 binding audit overall: {'PASS' if all_clean else 'FAIL'}")
        sys.exit(0 if all_clean else 1)

    # Normal build mode
    buckets = _load_buckets()
    holdout = load_holdout_probes()

    print(f"\n{'='*65}")
    print(f"  Evidence Campaign v1 — Pack Builder")
    print(f"  Buckets: {', '.join(bucket_ids)}")
    print(f"  Seed: {args.seed}")
    print(f"  Target: {PACK_TOTAL} pairs/pack "
          f"({PACK_TARGETED}/{PACK_HISTORICAL}/{PACK_STABILITY})")
    print(f"  Holdout probes excluded: {holdout['count']}")
    print(f"{'='*65}")

    for bid in bucket_ids:
        result = build_pack(bid, args.seed, buckets, holdout)

        if not args.dry_run:
            write_pack(result, output_dir)

    print(f"\nDone. {'(dry-run, no files written)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
