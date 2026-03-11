#!/bin/bash
# v4-recovery: C++ recovery + knowledge distill
# Combines: cpp_recovery.jsonl (50) + cpp replay (268) + hive_knowledge_distill.jsonl (100)
# Total: ~418 pairs, focused on recovering C++ regression

set -e
source /opt/hiveai-env/bin/activate
cd /opt/hiveai/project
export HF_HUB_OFFLINE=1

echo "=== Building v4-recovery combined dataset ==="

# Combine C++ recovery + knowledge distill
python3 -c "
import json, random
random.seed(42)

pairs = []

# C++ recovery pairs (priority)
with open('datasets/cpp_recovery.jsonl') as f:
    for line in f:
        obj = json.loads(line)
        obj.pop('metadata', None)
        pairs.append(obj)
print(f'C++ recovery: {len(pairs)} pairs')

# Knowledge distill
count = 0
with open('datasets/hive_knowledge_distill.jsonl') as f:
    for line in f:
        obj = json.loads(line)
        obj.pop('metadata', None)
        pairs.append(obj)
        count += 1
print(f'Knowledge distill: {count} pairs')

random.shuffle(pairs)

with open('datasets/v4_recovery_combined.jsonl', 'w') as f:
    for p in pairs:
        f.write(json.dumps(p) + '\n')

print(f'Total: {len(pairs)} pairs -> datasets/v4_recovery_combined.jsonl')
"

echo "=== Launching v4-recovery cycle ==="
bash scripts/run_full_cycle.sh recovery datasets/v4_recovery_combined.jsonl v4-recovery v3-think
