#!/usr/bin/env python3
"""Test Unsloth model loading for Qwen3.5-9B — validates we can skip 18GB download."""
import sys
import os

# Minimize VRAM usage for testing
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

print("=" * 60)
print("  Testing Unsloth Qwen3.5-9B Loading")
print("=" * 60)

try:
    from unsloth import FastLanguageModel
    print("[OK] Unsloth imported")
except ImportError:
    print("[FAIL] Unsloth not available")
    sys.exit(1)

print("\nDownloading + loading unsloth/Qwen3.5-9B-bnb-4bit...")
print("(This downloads ~5GB pre-quantized weights on first run)")
print()

try:
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="unsloth/Qwen3.5-9B-bnb-4bit",
        max_seq_length=4096,
        load_in_4bit=True,
        dtype=None,
    )
    print(f"\n[OK] Model loaded: {type(model).__name__}")
    print(f"[OK] Tokenizer loaded: {tokenizer.__class__.__name__}")

    # Check model size
    import torch
    mem = torch.cuda.memory_allocated() / 1024**3
    print(f"[OK] GPU memory used: {mem:.1f} GB")

    # Quick generation test
    print("\nTesting generation...")
    inputs = tokenizer("def fibonacci(n):", return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=50)
    text = tokenizer.decode(out[0], skip_special_tokens=True)
    print(f"[OK] Generated: {text[:100]}...")

    print("\n" + "=" * 60)
    print("  SUCCESS — Unsloth Qwen3.5-9B ready for training!")
    print("=" * 60)

except Exception as e:
    print(f"\n[FAIL] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
