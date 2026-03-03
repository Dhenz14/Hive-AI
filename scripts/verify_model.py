"""Verify rebuilt model: expert counts and gate alignment."""
import json
import glob
import sys
from collections import defaultdict
from safetensors import safe_open

model_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/hiveai/project/models/qwen3.5-35b-a3b-v3.5-fixed"

with open(f"{model_dir}/model.safetensors.index.json") as f:
    idx = json.load(f)

layer_counts = defaultdict(lambda: {"gate": 0, "up": 0, "down": 0, "max_idx": -1})
for key in idx["weight_map"]:
    for proj in ["gate_projs", "up_projs", "down_projs"]:
        if f".experts.{proj}." in key:
            layer = int(key.split("layers.")[1].split(".")[0])
            expert_idx = int(key.split(f"{proj}.")[1].split(".")[0])
            short = proj.replace("_projs", "")
            layer_counts[layer][short] += 1
            layer_counts[layer]["max_idx"] = max(layer_counts[layer]["max_idx"], expert_idx)

issues = []
for layer in sorted(layer_counts.keys()):
    c = layer_counts[layer]
    if c["gate"] != 128 or c["up"] != 128 or c["down"] != 128 or c["max_idx"] != 127:
        issues.append((layer, c))

if issues:
    print(f"ISSUES in {len(issues)} layers:")
    for layer, c in issues[:5]:
        print(f"  Layer {layer}: gate={c['gate']}, up={c['up']}, down={c['down']}, max_idx={c['max_idx']}")
else:
    print(f"ALL {len(layer_counts)} layers: 128 experts each, indices 0-127. PERFECT.")

# Check gate shape
for shard in sorted(glob.glob(f"{model_dir}/*.safetensors")):
    if "index" in shard:
        continue
    f = safe_open(shard, framework="pt")
    for key in f.keys():
        if "layers.0.mlp.gate.weight" in key:
            t = f.get_tensor(key)
            print(f"Gate layer 0 shape: {t.shape}")
            break
    else:
        continue
    break
