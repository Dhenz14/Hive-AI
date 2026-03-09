"""Safe Merge: Alpha grid search merge with perplexity validation.

Dual-path merge:
  Path A — GGUF (for inference): llama-export-lora merges LoRA into base GGUF
  Path B — HF bf16 (for next training cycle): PEFT merge_and_unload()

Alpha grid search: try [0.75, 0.85, 0.95, 1.0], pick lowest perplexity.

Based on: ProgLoRA (ACL 2025), Merge before Forget (arXiv 2512.23017)

Usage:
    # GGUF merge with alpha grid search
    python scripts/safe_merge.py \\
        --base-gguf models/deploy/current_base.gguf \\
        --lora-gguf models/hiveai-v9-lora-f16.gguf \\
        --output-dir models/deploy/v1-hive \\
        --validation-data replay/sampled.jsonl \\
        --version v1-hive

    # Full dual-path merge (GGUF + HF)
    python scripts/safe_merge.py \\
        --base-gguf models/deploy/current_base.gguf \\
        --lora-gguf models/hiveai-v9-lora-f16.gguf \\
        --base-hf /opt/hiveai/project/models/training/v1.0/hf \\
        --lora-hf loras/v9_hive \\
        --output-dir models/deploy/v1-hive \\
        --output-hf /opt/hiveai/project/models/training/v1-hive/hf \\
        --validation-data replay/sampled.jsonl \\
        --version v1-hive
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default llama.cpp binary paths
LLAMA_CPP_DIR = os.environ.get("LLAMA_CPP_DIR", "/tmp/llama.cpp")
LLAMA_EXPORT_LORA = os.path.join(LLAMA_CPP_DIR, "bin", "llama-export-lora")
LLAMA_PERPLEXITY = os.path.join(LLAMA_CPP_DIR, "bin", "llama-perplexity")

# Windows paths (fallback)
if sys.platform == "win32":
    win_llama = os.environ.get("LLAMA_CPP_DIR", r"c:\Users\theyc\llama.cpp\bin")
    if os.path.exists(win_llama):
        LLAMA_EXPORT_LORA = os.path.join(win_llama, "llama-export-lora.exe")
        LLAMA_PERPLEXITY = os.path.join(win_llama, "llama-perplexity.exe")


def gguf_merge_at_alpha(base_gguf: str, lora_gguf: str, output_path: str,
                         alpha: float) -> bool:
    """Merge LoRA into base GGUF at the given alpha scale using llama-export-lora."""
    cmd = [
        LLAMA_EXPORT_LORA,
        "-m", base_gguf,
        "-o", output_path,
        "--lora-scaled", f"{lora_gguf}:{alpha}",
    ]
    print(f"  Merging at alpha={alpha}: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            size_gb = os.path.getsize(output_path) / (1024**3)
            print(f"    OK: {output_path} ({size_gb:.1f} GB)")
            return True
        else:
            print(f"    FAILED: {result.stderr[:500]}")
            return False
    except FileNotFoundError:
        print(f"    ERROR: llama-export-lora not found at {LLAMA_EXPORT_LORA}")
        print(f"    Set LLAMA_CPP_DIR env var or build llama.cpp")
        return False
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT: merge took >10 minutes")
        return False


def compute_perplexity_gguf(gguf_path: str, validation_file: str) -> float:
    """Compute perplexity on validation data using llama-perplexity."""
    cmd = [
        LLAMA_PERPLEXITY,
        "-m", gguf_path,
        "-f", validation_file,
        "--ctx-size", "512",
        "-ngl", "99",
    ]
    print(f"  Computing perplexity on {gguf_path}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            # Parse perplexity from output (format: "Final estimate: perplexity = X.XXX")
            for line in result.stdout.split("\n"):
                if "perplexity" in line.lower() and "=" in line:
                    try:
                        ppl = float(line.split("=")[-1].strip().split()[0])
                        print(f"    Perplexity: {ppl:.4f}")
                        return ppl
                    except (ValueError, IndexError):
                        continue
            # Try stderr too
            for line in result.stderr.split("\n"):
                if "perplexity" in line.lower() and "=" in line:
                    try:
                        ppl = float(line.split("=")[-1].strip().split()[0])
                        print(f"    Perplexity: {ppl:.4f}")
                        return ppl
                    except (ValueError, IndexError):
                        continue
            print(f"    WARNING: Could not parse perplexity from output")
            return float("inf")
        else:
            print(f"    FAILED: {result.stderr[:500]}")
            return float("inf")
    except FileNotFoundError:
        print(f"    ERROR: llama-perplexity not found at {LLAMA_PERPLEXITY}")
        return float("inf")
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT")
        return float("inf")


def prepare_validation_text(validation_jsonl: str, output_txt: str, max_samples: int = 100):
    """Convert JSONL to plain text for llama-perplexity."""
    texts = []
    with open(validation_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            sample = json.loads(line)
            text = sample.get("text", "")
            if not text:
                inst = sample.get("instruction", "")
                out = sample.get("output", "")
                text = f"{inst}\n{out}"
            if text.strip():
                texts.append(text.strip())
            if len(texts) >= max_samples:
                break

    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("\n\n".join(texts))

    print(f"  Validation text: {len(texts)} samples -> {output_txt}")
    return output_txt


def hf_merge_at_alpha(base_hf: str, lora_hf: str, output_hf: str, alpha: float):
    """Merge LoRA into HF base at the given alpha scale using PEFT."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"  HF merge at alpha={alpha}: {base_hf} + {lora_hf}")
    print(f"    Loading base model (bf16, CPU)...")

    model = AutoModelForCausalLM.from_pretrained(
        base_hf,
        torch_dtype=torch.bfloat16,
        device_map="cpu",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_hf, trust_remote_code=True)

    print(f"    Loading LoRA adapter...")
    model = PeftModel.from_pretrained(model, lora_hf)

    # Scale adapter weights by alpha before merge
    if alpha != 1.0:
        print(f"    Scaling adapter weights by alpha={alpha}...")
        for name, param in model.named_parameters():
            if "lora_B" in name and param.requires_grad:
                param.data *= alpha

    print(f"    Merging and unloading...")
    model = model.merge_and_unload()

    print(f"    Saving merged model to {output_hf}...")
    os.makedirs(output_hf, exist_ok=True)
    model.save_pretrained(output_hf)
    tokenizer.save_pretrained(output_hf)

    # Size check
    total_size = sum(f.stat().st_size for f in Path(output_hf).rglob("*") if f.is_file())
    print(f"    Saved: {total_size / (1024**3):.1f} GB")

    # Cleanup
    del model
    import gc
    gc.collect()

    return output_hf


def alpha_grid_search(base_gguf: str, lora_gguf: str, output_dir: str,
                       validation_file: str, alphas: list[float]) -> tuple[float, str]:
    """Try each alpha, compute perplexity, return best."""
    os.makedirs(output_dir, exist_ok=True)

    # Prepare validation text
    val_txt = os.path.join(output_dir, "_validation.txt")
    prepare_validation_text(validation_file, val_txt)

    results = []
    merged_paths = {}

    for alpha in alphas:
        merged_path = os.path.join(output_dir, f"merged_alpha_{alpha}.gguf")
        success = gguf_merge_at_alpha(base_gguf, lora_gguf, merged_path, alpha)
        if success:
            ppl = compute_perplexity_gguf(merged_path, val_txt)
            results.append((alpha, ppl, merged_path))
            merged_paths[alpha] = merged_path
            print(f"  Alpha {alpha}: perplexity = {ppl:.4f}")
        else:
            print(f"  Alpha {alpha}: MERGE FAILED — skipping")

    if not results:
        print("ERROR: All alpha merges failed!")
        sys.exit(1)

    # Pick best (lowest perplexity)
    results.sort(key=lambda x: x[1])
    best_alpha, best_ppl, best_path = results[0]
    print(f"\n  BEST: alpha={best_alpha}, perplexity={best_ppl:.4f}")

    # Rename best to merged.gguf, delete others
    final_path = os.path.join(output_dir, "merged.gguf")
    if best_path != final_path:
        shutil.move(best_path, final_path)

    for alpha, ppl, path in results:
        if path != best_path and os.path.exists(path):
            os.remove(path)
            print(f"  Cleaned up: {path}")

    # Cleanup validation text
    if os.path.exists(val_txt):
        os.remove(val_txt)

    return best_alpha, final_path


def main():
    parser = argparse.ArgumentParser(description="Safe merge with alpha grid search")
    parser.add_argument("--base-gguf", required=True,
                        help="Path to base GGUF model")
    parser.add_argument("--lora-gguf", required=True,
                        help="Path to LoRA adapter GGUF")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory for merged model")
    parser.add_argument("--validation-data", required=True,
                        help="JSONL file for perplexity validation")
    parser.add_argument("--alphas", type=str, default="0.75,0.85,0.95,1.0",
                        help="Comma-separated alpha values to try (default: 0.75,0.85,0.95,1.0)")
    parser.add_argument("--version", type=str, default="v1",
                        help="Version string for metadata")
    # HF merge path (optional — for next training cycle)
    parser.add_argument("--base-hf", type=str, default=None,
                        help="Path to HF bf16 base model (for training path)")
    parser.add_argument("--lora-hf", type=str, default=None,
                        help="Path to PEFT adapter directory (for training path)")
    parser.add_argument("--output-hf", type=str, default=None,
                        help="Output path for merged HF model (for training path)")
    args = parser.parse_args()

    alphas = [float(a.strip()) for a in args.alphas.split(",")]
    print(f"=" * 60)
    print(f"  Safe Merge — Alpha Grid Search")
    print(f"=" * 60)
    print(f"  Base GGUF: {args.base_gguf}")
    print(f"  LoRA GGUF: {args.lora_gguf}")
    print(f"  Alphas: {alphas}")
    print(f"  Validation: {args.validation_data}")
    print(f"  Output: {args.output_dir}")
    print(f"=" * 60)

    start = time.time()

    # Path A: GGUF merge with alpha grid search
    best_alpha, merged_gguf = alpha_grid_search(
        args.base_gguf, args.lora_gguf, args.output_dir,
        args.validation_data, alphas
    )

    # Path B: HF merge (if paths provided)
    if args.base_hf and args.lora_hf and args.output_hf:
        print(f"\n--- HF Merge Path (for next training cycle) ---")
        hf_merge_at_alpha(args.base_hf, args.lora_hf, args.output_hf, best_alpha)
    elif args.base_hf or args.lora_hf or args.output_hf:
        print("WARNING: HF merge requires all three: --base-hf, --lora-hf, --output-hf")

    # Save metadata
    elapsed = time.time() - start
    metadata = {
        "version": args.version,
        "parent_gguf": args.base_gguf,
        "lora_gguf": args.lora_gguf,
        "best_alpha": best_alpha,
        "alphas_tested": alphas,
        "merged_gguf": merged_gguf,
        "merged_hf": args.output_hf,
        "validation_data": args.validation_data,
        "merge_time_s": round(elapsed),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  Merge complete!")
    print(f"  Best alpha: {best_alpha}")
    print(f"  Merged GGUF: {merged_gguf}")
    if args.output_hf:
        print(f"  Merged HF: {args.output_hf}")
    print(f"  Metadata: {meta_path}")
    print(f"  Time: {elapsed:.0f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
