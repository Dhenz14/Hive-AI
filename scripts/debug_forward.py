"""
Debug forward pass of full unpruned model to find NaN source.
Tests: single forward pass, check logits, try greedy decoding.
"""
import sys
import os
import time
import torch

try:
    import fla
    print(f"[OK] fla v{fla.__version__}")
except ImportError:
    print("[WARN] FLA not installed")

from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    "/opt/hiveai/project/models/qwen3.5-35b-a3b",
)
MAX_GPU = os.environ.get("MAX_GPU", "14GiB")

print(f"Model: {MODEL_PATH}")
print(f"Max GPU: {MAX_GPU}")

print("\n[1/5] Loading model (BF16, eager, no quantization)...")
t0 = time.time()
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    device_map="auto",
    max_memory={0: MAX_GPU, "cpu": "72GiB"},
    torch_dtype=torch.bfloat16,
    attn_implementation="eager",
)
model.eval()
print(f"  Loaded in {time.time()-t0:.1f}s")

# Check device map
try:
    dm = model.hf_device_map
    gpu = sum(1 for v in dm.values() if v == 0)
    cpu = sum(1 for v in dm.values() if v == "cpu")
    disk = sum(1 for v in dm.values() if v == "disk")
    print(f"  Modules: GPU={gpu}, CPU={cpu}, disk={disk}")
except:
    pass

allocated = torch.cuda.memory_allocated() / 1024**3
print(f"  VRAM: {allocated:.1f} GiB")

# [2/5] Simple tokenization test
print("\n[2/5] Tokenization test...")
text = "Hello, world!"
tokens = tokenizer(text, return_tensors="pt")
print(f"  Input: '{text}' → {tokens['input_ids'].shape}")

# [3/5] Single forward pass — check logits
print("\n[3/5] Single forward pass (checking for NaN)...")
prompt = "<|im_start|>user\nSay hello.<|im_end|>\n<|im_start|>assistant\n"
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
print(f"  Input shape: {inputs['input_ids'].shape}")

try:
    with torch.no_grad():
        outputs = model(**inputs)
    logits = outputs.logits
    print(f"  Logits shape: {logits.shape}")
    print(f"  Logits dtype: {logits.dtype}")
    print(f"  Has NaN: {torch.isnan(logits).any().item()}")
    print(f"  Has Inf: {torch.isinf(logits).any().item()}")
    print(f"  Min: {logits.min().item():.4f}")
    print(f"  Max: {logits.max().item():.4f}")
    print(f"  Mean: {logits.float().mean().item():.4f}")

    # Check last token logits (what would be sampled)
    last_logits = logits[0, -1, :]
    print(f"  Last token logits - NaN: {torch.isnan(last_logits).any().item()}, Inf: {torch.isinf(last_logits).any().item()}")

    if not torch.isnan(logits).any().item():
        # Try greedy decode for a few tokens
        top5 = torch.topk(last_logits, 5)
        for i, (val, idx) in enumerate(zip(top5.values, top5.indices)):
            tok = tokenizer.decode([idx.item()])
            print(f"  Top-{i+1}: {repr(tok)} (logit={val.item():.2f})")
except Exception as e:
    print(f"  ERROR in forward pass: {e}")
    import traceback
    traceback.print_exc()

# [4/5] Try greedy generation (no sampling)
print("\n[4/5] Greedy generation (do_sample=False)...")
try:
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=50,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    print(f"  Greedy response: {repr(response[:500])}")
except Exception as e:
    print(f"  ERROR: {e}")

# [5/5] Try sampled generation with temperature
print("\n[5/5] Sampled generation (temp=0.7, rep_penalty=1.5)...")
try:
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=50,
            temperature=0.7,
            top_p=0.95,
            top_k=20,
            do_sample=True,
            repetition_penalty=1.5,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    print(f"  Sampled response: {repr(response[:500])}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\nDone.")
