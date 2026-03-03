"""Quick utility to list all pruned model variants."""
import json, os
base = '/opt/hiveai/project/models'
for d in sorted(os.listdir(base)):
    if not d.startswith('qwen3.5-35b-a3b-v3.5'):
        continue
    full = os.path.join(base, d)
    meta_path = os.path.join(full, 'pruning_meta.json')
    if os.path.exists(meta_path):
        m = json.load(open(meta_path))
        aa = m.get('activation_aware', 'N/A')
        pr = m.get('prune_ratio', 'N/A')
        method = m.get('pruning_method', 'unknown')
        eb = m.get('total_experts_before', '?')
        ea = m.get('total_experts_after', '?')
        rc = m.get('routing_capacity_retained', 0)
        print("{}: act={}, ratio={}, experts={}->{}, capacity={:.1%}, method={}".format(
            d, aa, pr, eb, ea, rc, method))
    else:
        try:
            size = sum(os.path.getsize(os.path.join(full, f))
                      for f in os.listdir(full) if f.endswith('.safetensors')) / 1e9
        except:
            size = 0
        print("{}: no pruning_meta.json, safetensors={:.1f}GB".format(d, size))
