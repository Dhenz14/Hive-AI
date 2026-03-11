"""Safe Merge: Alpha grid search merge with perplexity validation.

bf16 Golden Chain: HF bf16 weights are the source of truth for ALL merges.
GGUF is derived from HF output via convert + quantize. This eliminates
quantization drift from repeated llama-export-lora merges.

Merge paths:
  1. Alpha grid search via llama-export-lora (fast GGUF comparison only)
  2. HF bf16 merge at best alpha via PEFT merge_and_unload() (canonical)
  3. Convert HF → GGUF via convert_hf_to_gguf.py + llama-quantize (deploy)

If HF paths not provided, falls back to llama-export-lora GGUF (legacy mode).

Based on: ProgLoRA (ACL 2025), Merge before Forget (arXiv 2512.23017)

Usage:
    # Full golden chain merge (recommended)
    python scripts/safe_merge.py \\
        --base-gguf models/deploy/current_base.gguf \\
        --lora-gguf loras/v2-think/adapter.gguf \\
        --base-hf /opt/hiveai/project/models/training/v1-hive/hf \\
        --lora-hf loras/v2-think \\
        --output-dir models/deploy/v2-think \\
        --output-hf /opt/hiveai/project/models/training/v2-think/hf \\
        --validation-data replay/sampled.jsonl \\
        --version v2-think

    # Legacy GGUF-only merge (no golden chain)
    python scripts/safe_merge.py \\
        --base-gguf models/deploy/current_base.gguf \\
        --lora-gguf loras/v2-think/adapter.gguf \\
        --output-dir models/deploy/v2-think \\
        --validation-data replay/sampled.jsonl \\
        --version v2-think
"""
import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default llama.cpp binary paths — always use LLAMA_CPP_DIR env var.
# Never hardcode user-specific paths; fall back to system PATH lookup.
LLAMA_CPP_DIR = os.environ.get("LLAMA_CPP_DIR", "")

if LLAMA_CPP_DIR:
    _bin_dir = os.path.join(LLAMA_CPP_DIR, "bin")
    LLAMA_EXPORT_LORA = os.path.join(_bin_dir, "llama-export-lora")
    LLAMA_PERPLEXITY = os.path.join(_bin_dir, "llama-perplexity")
    LLAMA_QUANTIZE = os.path.join(_bin_dir, "llama-quantize")
else:
    LLAMA_EXPORT_LORA = "llama-export-lora"
    LLAMA_PERPLEXITY = "llama-perplexity"
    LLAMA_QUANTIZE = "llama-quantize"

# convert_hf_to_gguf.py search paths
_CONVERT_HF_CANDIDATES = [
    os.path.join(os.environ.get("LLAMA_CPP_DIR", ""), "convert_hf_to_gguf.py"),
    "/tmp/llama.cpp/convert_hf_to_gguf.py",
]


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
    # Estimate timeout based on file size — F16 models (>20GB) need much longer
    file_size_gb = os.path.getsize(gguf_path) / (1024**3) if os.path.exists(gguf_path) else 0
    timeout = 1800 if file_size_gb > 20 else 900 if file_size_gb > 10 else 600
    cmd = [
        LLAMA_PERPLEXITY,
        "-m", gguf_path,
        "-f", validation_file,
        "--ctx-size", "512",
        "-ngl", "99",
        "--threads", "8",
    ]
    print(f"  Computing perplexity on {gguf_path} ({file_size_gb:.1f}GB, timeout={timeout}s)...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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


def della_prune_adapter(lora_hf: str, drop_rate: float = 0.7) -> str:
    """DELLA pruning: drop low-magnitude LoRA delta parameters, rescale survivors.

    Based on DELLA-Merging (2024) — MAGPRUNE strategy. Outperforms TIES by 3.6 pts.
    Reduces interference during merge by keeping only the most significant updates.

    Args:
        lora_hf: Path to PEFT adapter directory
        drop_rate: Fraction of parameters to drop (0.7 = keep top 30%)

    Returns:
        Path to pruned adapter directory (creates a copy)
    """
    import torch

    if drop_rate <= 0.0 or drop_rate >= 1.0:
        print(f"  DELLA: drop_rate={drop_rate} out of range, skipping pruning")
        return lora_hf

    print(f"  DELLA pruning: drop_rate={drop_rate} (keeping top {(1-drop_rate)*100:.0f}% of params)")

    # Load adapter weights
    adapter_file = os.path.join(lora_hf, "adapter_model.safetensors")
    if os.path.exists(adapter_file):
        import safetensors.torch as st
        state_dict = st.load_file(adapter_file)
    else:
        adapter_file = os.path.join(lora_hf, "adapter_model.bin")
        state_dict = torch.load(adapter_file, map_location="cpu", weights_only=True)

    # Prune LoRA delta parameters (only lora_A and lora_B weights)
    total_params = 0
    pruned_params = 0
    for key in state_dict:
        if 'lora_A' not in key and 'lora_B' not in key:
            continue
        delta = state_dict[key]
        total_params += delta.numel()

        # MAGPRUNE: threshold at the drop_rate quantile of absolute values
        threshold = torch.quantile(delta.abs().float(), drop_rate)
        mask = delta.abs() >= threshold

        # Rescale survivors to preserve expected magnitude
        scale = 1.0 / (1.0 - drop_rate)
        state_dict[key] = (delta * mask * scale).to(delta.dtype)
        pruned_params += (~mask).sum().item()

    print(f"    Pruned {pruned_params:,}/{total_params:,} params "
          f"({pruned_params/max(total_params,1)*100:.1f}%), "
          f"rescaled survivors by {1/(1-drop_rate):.2f}x")

    # Save to a temporary pruned copy
    pruned_dir = lora_hf + "_della_pruned"
    os.makedirs(pruned_dir, exist_ok=True)

    # Copy config files
    for cfg in ["adapter_config.json", "tokenizer.json", "tokenizer_config.json",
                "special_tokens_map.json"]:
        src = os.path.join(lora_hf, cfg)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(pruned_dir, cfg))

    # Save pruned weights
    pruned_file = os.path.join(pruned_dir, "adapter_model.safetensors")
    try:
        import safetensors.torch as st
        st.save_file(state_dict, pruned_file)
    except ImportError:
        torch.save(state_dict, os.path.join(pruned_dir, "adapter_model.bin"))

    print(f"    Pruned adapter saved to {pruned_dir}")
    return pruned_dir


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

    # Scale adapter via PEFT's scaling API (works with all adapter configs,
    # unlike manually scaling lora_B which breaks with some PEFT versions)
    if alpha != 1.0:
        print(f"    Scaling adapter weights by alpha={alpha}...")
        try:
            # PEFT >=0.7 supports add_weighted_adapter for scaling
            model.add_weighted_adapter(
                adapters=["default"],
                weights=[alpha],
                adapter_name="scaled",
                combination_type="linear",
            )
            model.set_adapter("scaled")
        except (AttributeError, TypeError):
            # Fallback: manual lora_B scaling for older PEFT versions
            print(f"    (fallback: manual lora_B scaling)")
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


def convert_hf_to_gguf(hf_dir: str, output_gguf: str, quantize_type: str = "Q5_K_M") -> bool:
    """Convert HF bf16 model to quantized GGUF (golden chain final step)."""
    # Find convert_hf_to_gguf.py
    convert_script = None
    for cs in _CONVERT_HF_CANDIDATES:
        if os.path.exists(cs):
            convert_script = cs
            break

    if not convert_script:
        print("  ERROR: convert_hf_to_gguf.py not found")
        print(f"  Searched: {_CONVERT_HF_CANDIDATES}")
        return False

    # Step 1: Convert HF → F16 GGUF
    f16_gguf = output_gguf.replace(".gguf", "_f16.gguf")
    print(f"  Converting HF → F16 GGUF: {hf_dir} → {f16_gguf}")
    try:
        result = subprocess.run(
            [sys.executable, convert_script, hf_dir,
             "--outfile", f16_gguf, "--outtype", "f16"],
            capture_output=True, text=True, timeout=600,
            cwd=os.path.dirname(convert_script),
        )
        if result.returncode != 0:
            print(f"    FAILED: {result.stderr[-500:]}")
            return False
        f16_size = os.path.getsize(f16_gguf) / (1024**3)
        print(f"    F16 GGUF: {f16_size:.1f} GB")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"    ERROR: {e}")
        return False

    # Step 2: Quantize F16 → target quant type
    print(f"  Quantizing F16 → {quantize_type}: {output_gguf}")
    try:
        result = subprocess.run(
            [LLAMA_QUANTIZE, f16_gguf, output_gguf, quantize_type],
            capture_output=True, text=True, timeout=1200,
        )
        if result.returncode != 0:
            print(f"    FAILED: {result.stderr[-500:]}")
            # If quantize fails, keep the F16 as fallback
            if os.path.exists(f16_gguf):
                shutil.move(f16_gguf, output_gguf)
                print(f"    Kept F16 GGUF as fallback (no quantization)")
            return True
        final_size = os.path.getsize(output_gguf) / (1024**3)
        print(f"    Quantized GGUF: {final_size:.1f} GB")
    except FileNotFoundError:
        print(f"    WARNING: llama-quantize not found, keeping F16 GGUF")
        if os.path.exists(f16_gguf):
            shutil.move(f16_gguf, output_gguf)
        return True
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT: quantization took >20 minutes")
        return False

    # Cleanup F16 intermediate
    if os.path.exists(f16_gguf) and os.path.exists(output_gguf):
        os.remove(f16_gguf)
        print(f"    Cleaned up F16 intermediate")

    return True


def alpha_grid_search(base_gguf: str, lora_gguf: str, output_dir: str,
                       validation_file: str, alphas: list[float],
                       early_exit_ppl: float = 0.0) -> tuple[float, str]:
    """Try each alpha, compute perplexity, return best.

    Uses pipeline parallelism: CPU merge of alpha[i+1] overlaps with
    GPU perplexity eval of alpha[i]. Saves ~15 min per cycle (4 alphas).

    If early_exit_ppl > 0 and first alpha achieves perplexity below that
    threshold, skips remaining alphas (saves ~20 min per skipped alpha).
    """
    os.makedirs(output_dir, exist_ok=True)

    # Prepare validation text once (reused for all alphas)
    val_txt = os.path.join(output_dir, "_validation.txt")
    prepare_validation_text(validation_file, val_txt)

    results = []
    merge_ready = queue.Queue()
    early_stop = threading.Event()

    def merge_worker():
        """Merge all alphas sequentially (CPU-bound)."""
        for alpha in alphas:
            if early_stop.is_set():
                print(f"  Skipping alpha {alpha} (early exit triggered)")
                break
            merged_path = os.path.join(output_dir, f"merged_alpha_{alpha}.gguf")
            success = gguf_merge_at_alpha(base_gguf, lora_gguf, merged_path, alpha)
            merge_ready.put((alpha, merged_path, success))
        merge_ready.put(None)  # sentinel

    def eval_worker():
        """Evaluate perplexity as merges complete (GPU-bound)."""
        while True:
            item = merge_ready.get()
            if item is None:
                break
            alpha, merged_path, success = item
            if success:
                ppl = compute_perplexity_gguf(merged_path, val_txt)
                results.append((alpha, ppl, merged_path))
                print(f"  Alpha {alpha}: perplexity = {ppl:.4f}")
                # Early exit: if perplexity is good enough, skip remaining
                if early_exit_ppl > 0 and ppl < early_exit_ppl and len(results) >= 1:
                    print(f"  EARLY EXIT: ppl {ppl:.4f} < threshold {early_exit_ppl:.4f}")
                    early_stop.set()
            else:
                print(f"  Alpha {alpha}: MERGE FAILED — skipping")

    # Run merge (CPU) and eval (GPU) in parallel pipeline
    merge_thread = threading.Thread(target=merge_worker, name="merge-worker")
    eval_thread = threading.Thread(target=eval_worker, name="eval-worker")
    merge_thread.start()
    eval_thread.start()
    merge_thread.join()
    eval_thread.join()

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


def per_layer_alpha_search(base_hf: str, lora_hf: str, global_alpha: float,
                           validation_file: str) -> dict:
    """Refine alpha per layer group around the global optimum.

    Groups: early (0-15), mid (16-31), late (32-47).
    For each group, try candidates around global_alpha, pick lowest perplexity.
    Uses greedy search: optimize one group at a time, holding others fixed.

    Returns {group_name: best_alpha} dict.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"\n--- Per-Layer Alpha Search (global={global_alpha}) ---")

    layer_groups = {
        'early': list(range(0, 16)),
        'mid': list(range(16, 32)),
        'late': list(range(32, 48)),
    }

    # Load validation data for perplexity evaluation
    val_texts = []
    with open(validation_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line.strip())
                text = row.get("output", row.get("text", ""))
                if text and len(text) > 50:
                    val_texts.append(text)
            except json.JSONDecodeError:
                continue
    val_texts = val_texts[:50]  # Cap at 50 for speed
    if not val_texts:
        print("  WARNING: No validation text found, skipping per-layer alpha")
        return {g: global_alpha for g in layer_groups}

    val_text = "\n\n".join(val_texts)

    def eval_with_alphas(alphas_dict):
        """Merge with per-group alphas and compute perplexity."""
        model = AutoModelForCausalLM.from_pretrained(
            base_hf, torch_dtype=torch.bfloat16, device_map="cpu",
            trust_remote_code=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(base_hf, trust_remote_code=True)
        model = PeftModel.from_pretrained(model, lora_hf)

        # Scale lora_B per layer group
        for name, param in model.named_parameters():
            if "lora_B" not in name or not param.requires_grad:
                continue
            # Extract layer number from name (e.g., "model.layers.5.self_attn...")
            layer_num = None
            for part in name.split("."):
                if part.isdigit():
                    layer_num = int(part)
                    break
            if layer_num is None:
                param.data *= global_alpha
                continue

            alpha = global_alpha
            for group_name, layers in layer_groups.items():
                if layer_num in layers:
                    alpha = alphas_dict[group_name]
                    break
            param.data *= alpha

        model = model.merge_and_unload()

        # Quick perplexity on CPU (subset of validation data)
        model.eval()
        encodings = tokenizer(val_text, return_tensors="pt", truncation=True, max_length=2048)
        input_ids = encodings.input_ids

        with torch.no_grad():
            outputs = model(input_ids, labels=input_ids)
            ppl = torch.exp(outputs.loss).item()

        del model
        import gc
        gc.collect()
        return ppl

    # Greedy search: one group at a time
    best_alphas = {g: global_alpha for g in layer_groups}
    candidates_offsets = [-0.15, -0.05, 0.0, 0.05, 0.10]

    for group_name in layer_groups:
        candidates = [global_alpha + offset for offset in candidates_offsets]
        candidates = [c for c in candidates if 0.5 <= c <= 1.0]
        # Deduplicate
        candidates = sorted(set(candidates))

        best_ppl = float('inf')
        best_a = global_alpha

        for alpha in candidates:
            test_alphas = dict(best_alphas)
            test_alphas[group_name] = alpha
            ppl = eval_with_alphas(test_alphas)
            print(f"  {group_name} alpha={alpha:.2f}: ppl={ppl:.4f}")
            if ppl < best_ppl:
                best_ppl = ppl
                best_a = alpha

        best_alphas[group_name] = best_a
        print(f"  -> Best {group_name}: alpha={best_a:.2f} (ppl={best_ppl:.4f})")

    print(f"\n  Per-layer alphas: {best_alphas}")
    return best_alphas


def hf_merge_with_per_layer_alpha(base_hf: str, lora_hf: str, output_hf: str,
                                   per_layer_alphas: dict, global_alpha: float):
    """Merge LoRA into HF base with per-layer-group alpha scaling."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    layer_groups = {
        'early': list(range(0, 16)),
        'mid': list(range(16, 32)),
        'late': list(range(32, 48)),
    }

    print(f"  HF merge with per-layer alphas: {per_layer_alphas}")
    model = AutoModelForCausalLM.from_pretrained(
        base_hf, torch_dtype=torch.bfloat16, device_map="cpu",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_hf, trust_remote_code=True)
    model = PeftModel.from_pretrained(model, lora_hf)

    # Scale lora_B per layer group before merge
    for name, param in model.named_parameters():
        if "lora_B" not in name or not param.requires_grad:
            continue
        layer_num = None
        for part in name.split("."):
            if part.isdigit():
                layer_num = int(part)
                break
        if layer_num is None:
            param.data *= global_alpha
            continue

        alpha = global_alpha
        for group_name, layers in layer_groups.items():
            if layer_num in layers:
                alpha = per_layer_alphas.get(group_name, global_alpha)
                break
        param.data *= alpha

    model = model.merge_and_unload()

    os.makedirs(output_hf, exist_ok=True)
    model.save_pretrained(output_hf)
    tokenizer.save_pretrained(output_hf)

    total_size = sum(f.stat().st_size for f in Path(output_hf).rglob("*") if f.is_file())
    print(f"    Saved: {total_size / (1024**3):.1f} GB")

    del model
    import gc
    gc.collect()
    return output_hf


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
    parser.add_argument("--alphas", type=str, default="0.85,1.0",
                        help="Comma-separated alpha values to try (default: 0.85,1.0)")
    parser.add_argument("--early-exit-ppl", type=float, default=0.0,
                        help="Skip remaining alphas if perplexity drops below this threshold "
                             "(0=disabled, 8.0=recommended for 14B models)")
    parser.add_argument("--version", type=str, default="v1",
                        help="Version string for metadata")
    # HF merge path (optional — for next training cycle)
    parser.add_argument("--base-hf", type=str, default=None,
                        help="Path to HF bf16 base model (for training path)")
    parser.add_argument("--lora-hf", type=str, default=None,
                        help="Path to PEFT adapter directory (for training path)")
    parser.add_argument("--output-hf", type=str, default=None,
                        help="Output path for merged HF model (for training path)")
    parser.add_argument("--quantize-type", type=str, default="Q5_K_M",
                        help="GGUF quantization type when using golden chain (default: Q5_K_M)")
    # === Lossless Continual Learning flags ===
    parser.add_argument("--della-drop", type=float, default=0.0,
                        help="DELLA pruning: drop this fraction of low-magnitude delta params "
                             "before merge (0.0=off, 0.7=recommended, keeps top 30%%)")
    parser.add_argument("--per-layer-alpha", action="store_true",
                        help="Refine merge alpha per layer group (early/mid/late) around global best. "
                             "Requires --base-hf and --lora-hf. Adds ~7 min to merge time.")
    args = parser.parse_args()

    try:
        alphas = [float(a.strip()) for a in args.alphas.split(",")]
    except ValueError as e:
        print(f"ERROR: Invalid alpha values '{args.alphas}': {e}")
        print("  Expected comma-separated floats, e.g., '0.75,0.85,0.95,1.0'")
        sys.exit(1)

    for a in alphas:
        if not (0.0 < a <= 2.0):
            print(f"ERROR: Alpha {a} out of range (expected 0.0 < alpha <= 2.0)")
            sys.exit(1)

    # Disk space check — each merged GGUF is roughly the size of the base
    base_size = os.path.getsize(args.base_gguf) if os.path.exists(args.base_gguf) else 0
    needed_gb = (base_size * len(alphas)) / (1024**3)
    output_dir_for_check = args.output_dir if os.path.exists(args.output_dir) else os.path.dirname(args.output_dir) or "."
    free_gb = shutil.disk_usage(output_dir_for_check).free / (1024**3)
    if needed_gb > 0 and free_gb < needed_gb * 1.2:  # 20% headroom
        print(f"WARNING: Merge needs ~{needed_gb:.1f} GB but only {free_gb:.1f} GB free")
        print(f"  Consider reducing --alphas count or freeing disk space")

    print(f"=" * 60)
    print(f"  Safe Merge — Alpha Grid Search")
    print(f"=" * 60)
    print(f"  Base GGUF: {args.base_gguf}")
    print(f"  LoRA GGUF: {args.lora_gguf}")
    print(f"  Alphas: {alphas}")
    print(f"  Validation: {args.validation_data}")
    print(f"  Output: {args.output_dir}")
    print(f"  Disk: {free_gb:.1f} GB free, ~{needed_gb:.1f} GB needed")
    if args.early_exit_ppl > 0:
        print(f"  Early exit: ppl < {args.early_exit_ppl}")
    print(f"=" * 60)

    start = time.time()

    golden_chain = args.base_hf and args.lora_hf and args.output_hf
    merge_path = "golden_chain" if golden_chain else "legacy_gguf"

    if golden_chain:
        print(f"  Mode: GOLDEN CHAIN (bf16 source of truth)")
    else:
        print(f"  Mode: Legacy GGUF (llama-export-lora)")
        if args.base_hf or args.lora_hf or args.output_hf:
            print("  WARNING: Golden chain requires all three: --base-hf, --lora-hf, --output-hf")

    # Step 1: Alpha grid search via llama-export-lora (fast comparison)
    best_alpha, search_gguf = alpha_grid_search(
        args.base_gguf, args.lora_gguf, args.output_dir,
        args.validation_data, alphas,
        early_exit_ppl=args.early_exit_ppl
    )

    # Step 2: Golden chain — HF merge at best alpha, then convert to GGUF
    if golden_chain:
        lora_hf_for_merge = args.lora_hf

        # Optional: DELLA pruning before merge (drop low-magnitude deltas)
        if args.della_drop > 0:
            print(f"\n--- DELLA Pruning (drop_rate={args.della_drop}) ---")
            lora_hf_for_merge = della_prune_adapter(args.lora_hf, args.della_drop)

        # Per-layer alpha refinement (optional, behind --per-layer-alpha flag)
        per_layer_alphas = None
        if args.per_layer_alpha:
            per_layer_alphas = per_layer_alpha_search(
                args.base_hf, lora_hf_for_merge, best_alpha, args.validation_data
            )

        print(f"\n--- Golden Chain: HF bf16 Merge (source of truth) ---")
        if per_layer_alphas:
            hf_merge_with_per_layer_alpha(
                args.base_hf, lora_hf_for_merge, args.output_hf,
                per_layer_alphas, best_alpha
            )
        else:
            hf_merge_at_alpha(args.base_hf, lora_hf_for_merge, args.output_hf, best_alpha)

        # Cleanup pruned adapter if created
        if lora_hf_for_merge != args.lora_hf and os.path.exists(lora_hf_for_merge):
            shutil.rmtree(lora_hf_for_merge)
            print(f"  Cleaned up DELLA pruned adapter")

        print(f"\n--- Golden Chain: HF → GGUF Conversion ---")
        golden_gguf = os.path.join(args.output_dir, "merged.gguf")
        if convert_hf_to_gguf(args.output_hf, golden_gguf, args.quantize_type):
            # Golden chain GGUF replaces the llama-export-lora version
            if os.path.exists(search_gguf) and search_gguf != golden_gguf:
                os.remove(search_gguf)
                print(f"  Replaced llama-export-lora GGUF with golden chain GGUF")
            merged_gguf = golden_gguf
        else:
            print(f"  WARNING: HF→GGUF conversion failed, keeping llama-export-lora GGUF")
            merged_gguf = search_gguf
    else:
        merged_gguf = search_gguf
        per_layer_alphas = None

    # Save metadata
    elapsed = time.time() - start
    metadata = {
        "version": args.version,
        "merge_path": merge_path,
        "parent_gguf": args.base_gguf,
        "parent_hf": args.base_hf,
        "lora_gguf": args.lora_gguf,
        "lora_hf": args.lora_hf,
        "best_alpha": best_alpha,
        "alphas_tested": alphas,
        "quantize_type": args.quantize_type if golden_chain else "native",
        "merged_gguf": merged_gguf,
        "merged_hf": args.output_hf,
        "validation_data": args.validation_data,
        "della_drop_rate": args.della_drop if args.della_drop > 0 else None,
        "per_layer_alphas": per_layer_alphas if golden_chain and args.per_layer_alpha else None,
        "merge_time_s": round(elapsed),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  Merge complete! ({merge_path})")
    print(f"  Best alpha: {best_alpha}")
    print(f"  Merged GGUF: {merged_gguf}")
    if args.output_hf:
        print(f"  Merged HF (bf16): {args.output_hf}")
    print(f"  Metadata: {meta_path}")
    print(f"  Time: {elapsed:.0f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
