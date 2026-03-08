"""TIES merge multiple category LoRAs into a single unified adapter.

TIES (Trim, Elect sign, merge) resolves parameter conflicts between
independently trained category LoRAs:
  1. Trim: removes 65% of smallest parameter deltas (noise)
  2. Elect: when adapters disagree on a weight's direction, majority wins
  3. Merge: averages aligned parameters

The v7 "general brain" adapter gets a 1.4x weight to preserve base knowledge.

Usage:
    python scripts/merge_category_loras.py
    python scripts/merge_category_loras.py --categories loras/v8_go loras/v8_cpp
    python scripts/merge_category_loras.py --density 0.5  # keep more params
"""
import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def merge_category_loras(
    base_model: str,
    v7_dir: str,
    category_dirs: list[str],
    output_dir: str,
    density: float = 0.35,
    v7_weight: float = 1.4,
):
    """Merge v7 + category adapters using TIES."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    # Filter to existing directories
    valid_dirs = [d for d in category_dirs if os.path.isdir(d) and
                  os.path.exists(os.path.join(d, "adapter_config.json"))]

    if not valid_dirs:
        print("ERROR: No valid category adapter directories found!")
        print(f"  Checked: {category_dirs}")
        sys.exit(1)

    print(f"TIES Merge: {len(valid_dirs)} category adapters + v7 base")
    print(f"  v7 adapter: {v7_dir} (weight: {v7_weight})")
    for d in valid_dirs:
        print(f"  Category:   {d} (weight: 1.0)")
    print(f"  Density:    {density} (keep top {density*100:.0f}% of parameter changes)")
    print(f"  Output:     {output_dir}")

    # Load base model in 4-bit
    print("\nLoading base model (4-bit)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

    # Load v7 as default adapter
    print(f"Loading v7 adapter from {v7_dir}...")
    model = PeftModel.from_pretrained(model, v7_dir, adapter_name="v7")

    # Load each category adapter
    adapter_names = ["v7"]
    weights = [v7_weight]
    for i, path in enumerate(valid_dirs):
        name = f"cat_{Path(path).name}"
        print(f"Loading adapter: {name} from {path}...")
        model.load_adapter(path, adapter_name=name)
        adapter_names.append(name)
        weights.append(1.0)

    # TIES merge
    print(f"\nRunning TIES merge (density={density})...")
    print(f"  Adapters: {adapter_names}")
    print(f"  Weights:  {weights}")

    model.add_weighted_adapter(
        adapters=adapter_names,
        weights=weights,
        adapter_name="merged",
        combination_type="ties",
        density=density,
    )
    model.set_adapter("merged")

    # Save merged adapter
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nSaving merged adapter to {output_dir}...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Write merge metadata
    import json
    meta = {
        "merge_type": "ties",
        "density": density,
        "v7_dir": v7_dir,
        "v7_weight": v7_weight,
        "category_dirs": valid_dirs,
        "adapter_count": len(adapter_names),
    }
    with open(os.path.join(output_dir, "merge_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nTIES merge complete -> {output_dir}")
    print(f"  Next: convert to GGUF for llama-server deployment")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TIES merge category LoRAs")
    parser.add_argument("--base-model", default="unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit",
                        help="Base model (HF name or local path)")
    parser.add_argument("--v7", default=str(PROJECT_ROOT / "loras" / "v7"),
                        help="v7 adapter directory")
    parser.add_argument("--categories", nargs="+",
                        default=[str(PROJECT_ROOT / "loras" / f"v8_{cat}")
                                 for cat in ["go", "cpp", "rust", "hive"]],
                        help="Category adapter directories")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "loras" / "v8"),
                        help="Output directory for merged adapter")
    parser.add_argument("--density", type=float, default=0.35,
                        help="TIES density — fraction of params to keep (default: 0.35)")
    parser.add_argument("--v7-weight", type=float, default=1.4,
                        help="Weight for v7 adapter in merge (default: 1.4)")
    args = parser.parse_args()

    merge_category_loras(
        base_model=args.base_model,
        v7_dir=args.v7,
        category_dirs=args.categories,
        output_dir=args.output,
        density=args.density,
        v7_weight=args.v7_weight,
    )
