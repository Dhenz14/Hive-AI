#!/usr/bin/env python3
"""Analyze and compare PEFT LoRA adapter weights.

Reports per-layer rank, alpha, weight magnitude (Frobenius norm),
and identifies which layers changed most between two adapters.

Usage:
    python scripts/analyze_lora_layers.py --adapter loras/v7
    python scripts/analyze_lora_layers.py --adapter loras/v7 --compare loras/v8
    python scripts/analyze_lora_layers.py --adapter loras/v7 --compare loras/v8 --json

Reference: HiveAI improvement_notes.md §26
"""

import argparse
import json
import sys
from pathlib import Path

import torch


def load_adapter(adapter_path: str) -> dict:
    """Load PEFT adapter config and weights."""
    path = Path(adapter_path)

    # Load config
    config_file = path / "adapter_config.json"
    if not config_file.exists():
        print(f"ERROR: No adapter_config.json in {path}", file=sys.stderr)
        sys.exit(1)

    with open(config_file) as f:
        config = json.load(f)

    # Load weights — try safetensors first, then bin
    weights = {}
    safetensor_files = list(path.glob("adapter_model*.safetensors"))
    bin_files = list(path.glob("adapter_model*.bin"))

    if safetensor_files:
        try:
            from safetensors.torch import load_file
            for sf in sorted(safetensor_files):
                weights.update(load_file(str(sf), device="cpu"))
        except ImportError:
            print("WARNING: safetensors not installed, trying .bin", file=sys.stderr)

    if not weights and bin_files:
        for bf in sorted(bin_files):
            weights.update(torch.load(str(bf), map_location="cpu", weights_only=True))

    if not weights:
        print(f"ERROR: No adapter weights found in {path}", file=sys.stderr)
        sys.exit(1)

    return {"config": config, "weights": weights, "path": str(path)}


def analyze_layers(adapter: dict) -> list[dict]:
    """Analyze each LoRA layer in the adapter."""
    config = adapter["config"]
    weights = adapter["weights"]
    r = config.get("r", "?")
    alpha = config.get("lora_alpha", "?")

    # Group by layer name (strip lora_A/lora_B suffix)
    layers = {}
    for key, tensor in weights.items():
        # Key format: base_model.model.model.layers.N.self_attn.q_proj.lora_A.weight
        parts = key.rsplit(".", 2)
        if len(parts) >= 3 and parts[-2] in ("lora_A", "lora_B"):
            layer_name = parts[0]  # everything before .lora_A/.lora_B
            ab = parts[-2]  # lora_A or lora_B
        elif ".lora_A." in key or ".lora_B." in key:
            # Alternative format
            if ".lora_A." in key:
                layer_name = key.split(".lora_A.")[0]
                ab = "lora_A"
            else:
                layer_name = key.split(".lora_B.")[0]
                ab = "lora_B"
        else:
            continue

        if layer_name not in layers:
            layers[layer_name] = {}
        layers[layer_name][ab] = tensor

    results = []
    for name in sorted(layers.keys()):
        tensors = layers[name]
        info = {
            "name": name,
            "rank": r,
            "alpha": alpha,
        }

        if "lora_A" in tensors:
            a = tensors["lora_A"].float()
            info["A_shape"] = list(a.shape)
            info["A_frobenius"] = float(torch.norm(a, p="fro").item())
            info["A_mean"] = float(a.mean().item())
            info["A_std"] = float(a.std().item())

        if "lora_B" in tensors:
            b = tensors["lora_B"].float()
            info["B_shape"] = list(b.shape)
            info["B_frobenius"] = float(torch.norm(b, p="fro").item())
            info["B_mean"] = float(b.mean().item())
            info["B_std"] = float(b.std().item())

        # Combined effective weight norm: ||B @ A|| (approximate LoRA contribution)
        if "lora_A" in tensors and "lora_B" in tensors:
            a = tensors["lora_A"].float()
            b = tensors["lora_B"].float()
            effective = b @ a
            info["effective_frobenius"] = float(torch.norm(effective, p="fro").item())
            info["effective_max"] = float(effective.abs().max().item())

        results.append(info)

    return results


def compare_adapters(layers1: list[dict], layers2: list[dict]) -> list[dict]:
    """Compare two adapters, identify biggest deltas."""
    map1 = {l["name"]: l for l in layers1}
    map2 = {l["name"]: l for l in layers2}

    all_names = sorted(set(map1.keys()) | set(map2.keys()))
    deltas = []

    for name in all_names:
        l1 = map1.get(name)
        l2 = map2.get(name)

        entry = {"name": name}

        if l1 and l2:
            e1 = l1.get("effective_frobenius", 0)
            e2 = l2.get("effective_frobenius", 0)
            entry["adapter1_norm"] = e1
            entry["adapter2_norm"] = e2
            entry["abs_delta"] = abs(e2 - e1)
            entry["rel_delta"] = abs(e2 - e1) / max(e1, 1e-8)

            a1_norm = l1.get("A_frobenius", 0)
            a2_norm = l2.get("A_frobenius", 0)
            b1_norm = l1.get("B_frobenius", 0)
            b2_norm = l2.get("B_frobenius", 0)
            entry["A_delta"] = abs(a2_norm - a1_norm)
            entry["B_delta"] = abs(b2_norm - b1_norm)
        elif l1:
            entry["adapter1_norm"] = l1.get("effective_frobenius", 0)
            entry["adapter2_norm"] = None
            entry["status"] = "only_in_adapter1"
        else:
            entry["adapter1_norm"] = None
            entry["adapter2_norm"] = l2.get("effective_frobenius", 0)
            entry["status"] = "only_in_adapter2"

        deltas.append(entry)

    # Sort by absolute delta descending
    deltas.sort(key=lambda d: d.get("abs_delta", 0), reverse=True)
    return deltas


def print_analysis(adapter: dict, layers: list[dict]) -> None:
    """Pretty-print single adapter analysis."""
    config = adapter["config"]
    print(f"\n{'='*72}")
    print(f"  Adapter: {adapter['path']}")
    print(f"  Rank: {config.get('r', '?')}  Alpha: {config.get('lora_alpha', '?')}  "
          f"Dropout: {config.get('lora_dropout', '?')}  "
          f"RSLoRA: {config.get('use_rslora', False)}")
    print(f"  Target modules: {config.get('target_modules', '?')}")
    print(f"  Total LoRA layers: {len(layers)}")
    print(f"{'='*72}\n")

    print(f"{'Layer':<55} {'||Eff||':>10} {'||A||':>10} {'||B||':>10}")
    print("-" * 90)
    for l in layers:
        short = l["name"].replace("base_model.model.", "")
        eff = f"{l.get('effective_frobenius', 0):.4f}"
        a_n = f"{l.get('A_frobenius', 0):.4f}"
        b_n = f"{l.get('B_frobenius', 0):.4f}"
        print(f"{short:<55} {eff:>10} {a_n:>10} {b_n:>10}")

    # Summary stats
    eff_norms = [l.get("effective_frobenius", 0) for l in layers]
    if eff_norms:
        print(f"\n  Effective weight stats:")
        print(f"    Mean: {sum(eff_norms)/len(eff_norms):.6f}")
        print(f"    Max:  {max(eff_norms):.6f}")
        print(f"    Min:  {min(eff_norms):.6f}")


def print_comparison(deltas: list[dict], path1: str, path2: str, top_n: int = 20) -> None:
    """Pretty-print comparison results."""
    print(f"\n{'='*80}")
    print(f"  Comparison: {path1} vs {path2}")
    print(f"  Top {top_n} layers by absolute weight delta")
    print(f"{'='*80}\n")

    print(f"{'Layer':<50} {'Adpt1':>8} {'Adpt2':>8} {'Delta':>8} {'Rel%':>8}")
    print("-" * 85)

    shown = 0
    for d in deltas:
        if shown >= top_n:
            break
        if "status" in d:
            continue

        short = d["name"].replace("base_model.model.", "")
        n1 = f"{d['adapter1_norm']:.4f}"
        n2 = f"{d['adapter2_norm']:.4f}"
        delta = f"{d['abs_delta']:.4f}"
        rel = f"{d['rel_delta']*100:.1f}%"
        print(f"{short:<50} {n1:>8} {n2:>8} {delta:>8} {rel:>8}")
        shown += 1


def main():
    parser = argparse.ArgumentParser(description="Analyze PEFT LoRA adapter layers")
    parser.add_argument("--adapter", required=True, help="Path to PEFT adapter directory")
    parser.add_argument("--compare", help="Second adapter to compare against")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--top", type=int, default=20, help="Top N layers to show in comparison")
    args = parser.parse_args()

    adapter1 = load_adapter(args.adapter)
    layers1 = analyze_layers(adapter1)

    if args.compare:
        adapter2 = load_adapter(args.compare)
        layers2 = analyze_layers(adapter2)
        deltas = compare_adapters(layers1, layers2)

        if args.json:
            output = {
                "adapter1": {"path": args.adapter, "layers": layers1},
                "adapter2": {"path": args.compare, "layers": layers2},
                "deltas": deltas[:args.top],
            }
            print(json.dumps(output, indent=2))
        else:
            print_analysis(adapter1, layers1)
            print_analysis(adapter2, layers2)
            print_comparison(deltas, args.adapter, args.compare, args.top)
    else:
        if args.json:
            output = {"path": args.adapter, "layers": layers1}
            print(json.dumps(output, indent=2))
        else:
            print_analysis(adapter1, layers1)


if __name__ == "__main__":
    main()
