"""
Activation-Aware Expert Pruning via Proxy Hidden States.

Strategy: Load the 128-expert pruned model, run coding calibration prompts,
hook the gate layers to capture hidden_states BEFORE routing.
Then route those hidden states through the FULL 256-expert gate weights
to determine which of ALL 256 experts would have been activated.
Keep the top 128 by activation frequency.

This gives activation-aware selection without needing to load the full model.
"""
import json
import os
import re
import sys
import time

import torch
import torch.nn.functional as F
from collections import defaultdict

# Config
PRUNED_MODEL_PATH = os.environ.get(
    "PRUNED_MODEL_PATH",
    "/opt/hiveai/project/models/qwen3.5-35b-a3b-v3.5-correct",
)
ORIGINAL_MODEL_DIR = os.environ.get(
    "ORIGINAL_MODEL_DIR",
    "/opt/hiveai/project/models/qwen3.5-35b-a3b",
)
OUTPUT_PATH = os.environ.get(
    "OUTPUT_PATH",
    "/opt/hiveai/project/models/qwen3.5-35b-a3b-v3.5/pruning_meta_activation.json",
)
NUM_KEEP = 128
TOP_K = 8  # num_experts_per_tok

# Calibration prompts focused on coding
CALIBRATION_PROMPTS = [
    "Write a Python function to check if a number is prime.",
    "Implement a binary search algorithm in Python.",
    "Create a class for a linked list with insert and delete methods.",
    "Write a Python decorator that caches function results.",
    "Implement merge sort with type hints.",
    "Write a FastAPI endpoint that handles file uploads.",
    "Create a Python context manager for database connections.",
    "Implement a thread-safe singleton pattern in Python.",
    "Write unit tests for a calculator class using pytest.",
    "Implement a simple tokenizer for arithmetic expressions.",
    "Write a recursive fibonacci with memoization.",
    "Create an async HTTP client with retry logic.",
    "Implement a trie data structure for autocomplete.",
    "Write a Python generator for reading large CSV files.",
    "Implement the observer design pattern.",
    "Write a function to serialize a binary tree to JSON.",
]

SEP = "=" * 60


def main():
    from safetensors import safe_open

    print(SEP)
    print("Activation-Aware Expert Pruning via Proxy")
    print(SEP)

    # Step 1: Load full 256-expert gate weights from original model (tiny: ~42 MB)
    print("\n[1/4] Loading full 256-expert gate weights from original model...")

    LP = r"(?:model\.language_model\.layers|model\.layers)"
    gate_pattern = re.compile(LP + r"\.(\d+)\.mlp\.gate\.weight$")

    full_gate_weights = {}  # layer_idx -> (256, 2048) tensor
    shard_files = sorted(
        f for f in os.listdir(ORIGINAL_MODEL_DIR)
        if f.endswith(".safetensors") and "index" not in f
    )
    for sf in shard_files:
        path = os.path.join(ORIGINAL_MODEL_DIR, sf)
        f = safe_open(path, framework="pt")
        for key in f.keys():
            m = gate_pattern.search(key)
            if m:
                layer_idx = int(m.group(1))
                full_gate_weights[layer_idx] = f.get_tensor(key).float()  # (256, 2048)

    print(f"  Loaded gate weights for {len(full_gate_weights)} layers")
    assert len(full_gate_weights) == 40, f"Expected 40 layers, got {len(full_gate_weights)}"

    # Step 2: Load the pruned 128-expert model for generating hidden states
    print("\n[2/4] Loading 128-expert model for hidden state generation...")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from train_v3 import patch_experts_for_quantization
    patch_experts_for_quantization()

    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(PRUNED_MODEL_PATH)
    model = AutoModelForCausalLM.from_pretrained(
        PRUNED_MODEL_PATH,
        quantization_config=quant_config,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
        attn_implementation="eager",
    )
    model.eval()
    print("  Model loaded")

    # Step 3: Hook gate layers to capture hidden states
    print("\n[3/4] Running calibration prompts and capturing hidden states...")

    # Activation counter: layer_idx -> expert_idx -> count
    activation_counts = defaultdict(lambda: defaultdict(int))
    total_routing_decisions = defaultdict(int)

    def make_gate_hook(layer_idx):
        def hook_fn(module, input_args, output):
            hidden = input_args[0].detach().float()  # (batch, seq_len, 2048)

            # Route through FULL 256-expert gate weights
            gate_w = full_gate_weights[layer_idx].to(hidden.device)  # (256, 2048)
            scores = torch.matmul(hidden, gate_w.T)  # (batch, seq_len, 256)
            routing = torch.softmax(scores, dim=-1)
            topk_indices = torch.topk(routing, k=TOP_K, dim=-1).indices  # (batch, seq_len, 8)

            # Count activations
            for idx in topk_indices.reshape(-1).cpu().tolist():
                activation_counts[layer_idx][idx] += 1
            total_routing_decisions[layer_idx] += topk_indices.shape[0] * topk_indices.shape[1]

            del gate_w
        return hook_fn

    # Find and hook gate modules
    hooks = []
    text_model = model.model if hasattr(model, "model") else model
    if hasattr(text_model, "language_model"):
        text_model = text_model.language_model
    layers = text_model.layers

    for layer_idx in range(len(layers)):
        layer = layers[layer_idx]
        if hasattr(layer, "mlp") and hasattr(layer.mlp, "gate"):
            hook = layer.mlp.gate.register_forward_hook(make_gate_hook(layer_idx))
            hooks.append(hook)

    print(f"  Hooked {len(hooks)} gate layers")

    # Run calibration prompts
    t0 = time.time()
    for i, prompt in enumerate(CALIBRATION_PROMPTS):
        messages = [
            {"role": "system", "content": "You are a helpful coding assistant. Write clean, working Python code."},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(model.device)

        with torch.no_grad():
            try:
                _ = model(**inputs, use_cache=False)
            except Exception as e:
                print(f"  Warning: prompt {i} failed: {e}")
                continue

        if (i + 1) % 4 == 0:
            print(f"  Processed {i+1}/{len(CALIBRATION_PROMPTS)} prompts ({time.time()-t0:.1f}s)")

    # Remove hooks
    for h in hooks:
        h.remove()

    print(f"  Done! Captured routing for {len(activation_counts)} layers in {time.time()-t0:.1f}s")

    # Step 4: Select top-128 experts per layer by activation frequency
    print("\n[4/4] Selecting top-128 experts per layer by activation frequency...")

    prune_map_keep = {}

    for layer_idx in sorted(activation_counts.keys()):
        counts = activation_counts[layer_idx]
        total = total_routing_decisions[layer_idx]

        # Sort experts by activation count (descending)
        expert_counts = [(idx, counts.get(idx, 0)) for idx in range(256)]
        expert_counts.sort(key=lambda x: x[1], reverse=True)

        # Keep top NUM_KEEP
        kept = sorted([idx for idx, _ in expert_counts[:NUM_KEEP]])
        prune_map_keep[str(layer_idx)] = kept

        if layer_idx < 3 or layer_idx == 39:
            top5 = expert_counts[:5]
            bot5 = expert_counts[-5:]
            print(f"  Layer {layer_idx}: top5={top5[:3]}... bot5={bot5[-3:]}, total={total}")

    # Check overlap with L2 norm selection
    meta_path = os.path.join(os.path.dirname(OUTPUT_PATH), "pruning_meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            old_meta = json.load(f)
        old_prune = old_meta["prune_map"]  # experts TO PRUNE

        total_overlap = 0
        for layer_str in prune_map_keep:
            old_kept = set(range(256)) - set(old_prune.get(layer_str, []))
            new_kept = set(prune_map_keep[layer_str])
            overlap = len(old_kept & new_kept)
            total_overlap += overlap

        avg_overlap = total_overlap / 40
        overlap_pct = avg_overlap / 128 * 100
        print(f"\nOverlap with L2-norm selection: {avg_overlap:.0f}/128 per layer ({overlap_pct:.1f}%)")
    else:
        overlap_pct = -1

    # Save
    meta = {
        "source_model": "qwen3.5-35b-a3b",
        "pruning_method": "activation_proxy",
        "activation_aware": True,
        "proxy_model": "128-expert L2-norm pruned model",
        "calibration_prompts": len(CALIBRATION_PROMPTS),
        "prune_ratio": 0.5,
        "experts_per_layer_before": 256,
        "experts_per_layer_after": NUM_KEEP,
        "total_experts_before": 256 * 40,
        "total_experts_after": NUM_KEEP * 40,
        "prune_map": prune_map_keep,
        "l2_overlap_pct": overlap_pct,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nSaved activation-aware prune map to {OUTPUT_PATH}")
    print(f"Kept {NUM_KEEP} experts/layer ({NUM_KEEP * 40} total)")

    # Clean up model
    del model
    torch.cuda.empty_cache()
    print("Done!")


if __name__ == "__main__":
    main()
