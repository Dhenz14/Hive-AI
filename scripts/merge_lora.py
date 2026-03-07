#!/usr/bin/env python3
"""Merge a PEFT LoRA adapter into the base model and optionally convert to GGUF.

Usage (in WSL):
    python scripts/merge_lora.py --lora-dir loras/v7/ --output-dir models/v7-merged/
    python scripts/merge_lora.py --lora-dir loras/v7/ --output-dir models/v7-merged/ --gguf
"""

import argparse
import gc
import os
import shutil
import subprocess
import sys
import time

import psutil
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

DEFAULT_BASE = (
    "/root/.cache/huggingface/hub/"
    "models--unsloth--Qwen2.5-Coder-14B-Instruct/"
    "snapshots/b693088367af1e4b88711d4038d269733023310d"
)
DEFAULT_LORA = "loras/v7/"
DEFAULT_OUTPUT = "models/v7-merged/"


def mem_gb():
    """Current process RSS in GB."""
    return psutil.Process().memory_info().rss / 1024**3


def fmt_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def main():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter into base model")
    parser.add_argument("--base-model", default=DEFAULT_BASE, help="Path to base model")
    parser.add_argument("--lora-dir", default=DEFAULT_LORA, help="Path to PEFT LoRA adapter dir")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="Where to save merged model")
    parser.add_argument("--gguf", action="store_true", help="Convert merged model to GGUF")
    parser.add_argument("--gguf-type", default="q5_k_m", help="GGUF quantization type (default: q5_k_m)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output dir")
    args = parser.parse_args()

    # Validate inputs
    if not os.path.isdir(args.base_model):
        print(f"ERROR: Base model not found: {args.base_model}")
        sys.exit(1)
    if not os.path.isdir(args.lora_dir):
        print(f"ERROR: LoRA dir not found: {args.lora_dir}")
        sys.exit(1)
    if os.path.exists(args.output_dir) and not args.force:
        print(f"ERROR: Output dir exists: {args.output_dir}")
        print("  Use --force to overwrite")
        sys.exit(1)
    if os.path.exists(args.output_dir) and args.force:
        print(f"Removing existing output dir: {args.output_dir}")
        shutil.rmtree(args.output_dir)

    t0 = time.time()
    print(f"Memory at start: {mem_gb():.1f} GB")

    # --- Load base model ---
    print(f"\n[1/4] Loading base model from {args.base_model}")
    t1 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    print(f"  Base model loaded in {fmt_time(time.time() - t1)} | mem: {mem_gb():.1f} GB")

    # --- Load LoRA adapter ---
    print(f"\n[2/4] Loading LoRA adapter from {args.lora_dir}")
    t2 = time.time()
    model = PeftModel.from_pretrained(model, args.lora_dir)
    print(f"  LoRA loaded in {fmt_time(time.time() - t2)} | mem: {mem_gb():.1f} GB")

    # --- Merge ---
    print("\n[3/4] Merging LoRA into base model")
    t3 = time.time()
    model = model.merge_and_unload()
    gc.collect()
    torch.cuda.empty_cache() if torch.cuda.is_available() else None
    print(f"  Merged in {fmt_time(time.time() - t3)} | mem: {mem_gb():.1f} GB")

    # --- Save ---
    print(f"\n[4/4] Saving merged model to {args.output_dir}")
    t4 = time.time()
    os.makedirs(args.output_dir, exist_ok=True)
    model.save_pretrained(args.output_dir, safe_serialization=True)
    tokenizer.save_pretrained(args.output_dir)
    print(f"  Saved in {fmt_time(time.time() - t4)} | mem: {mem_gb():.1f} GB")

    # Check output size
    total_bytes = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fns in os.walk(args.output_dir)
        for f in fns
    )
    print(f"  Output size: {total_bytes / 1024**3:.1f} GB")

    elapsed = time.time() - t0
    print(f"\nMerge complete in {fmt_time(elapsed)}")

    # --- Optional GGUF conversion ---
    if args.gguf:
        print(f"\n[GGUF] Converting to {args.gguf_type}")
        t5 = time.time()

        # Find convert script — check common locations
        convert_script = None
        candidates = [
            "/opt/hiveai/project/llama.cpp/convert_hf_to_gguf.py",
            "/opt/llama.cpp/convert_hf_to_gguf.py",
            shutil.which("convert_hf_to_gguf.py") or "",
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                convert_script = c
                break

        if not convert_script:
            print("  ERROR: convert_hf_to_gguf.py not found. Tried:")
            for c in candidates:
                if c:
                    print(f"    {c}")
            print("  Skipping GGUF conversion. Merged safetensors are saved.")
            sys.exit(0)

        gguf_out = os.path.join(
            args.output_dir,
            f"v7-merged-{args.gguf_type.replace('_', '-')}.gguf",
        )
        cmd = [
            sys.executable, convert_script,
            args.output_dir,
            "--outfile", gguf_out,
            "--outtype", args.gguf_type,
        ]
        print(f"  Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            print(f"  ERROR: GGUF conversion failed (exit {result.returncode})")
            sys.exit(1)

        if os.path.isfile(gguf_out):
            size_gb = os.path.getsize(gguf_out) / 1024**3
            print(f"  GGUF saved: {gguf_out} ({size_gb:.1f} GB)")
        print(f"  GGUF conversion done in {fmt_time(time.time() - t5)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
