#!/bin/bash
# prep_v5_batch.sh — Combine agentic datasets into v5 training batch
# Combines: agentic_capabilities.jsonl (50) + multi_turn_conversations.jsonl (50)
# Output: datasets/v5_agentic_combined.jsonl
# For the NEXT cycle after v4-recovery completes.

set -e
source /opt/hiveai-env/bin/activate
cd /opt/hiveai/project
export HF_HUB_OFFLINE=1

echo "=== Building v5-agentic combined dataset ==="

python3 -c "
import json, random
random.seed(42)

pairs = []

# Agentic capabilities
with open('datasets/agentic_capabilities.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        # Strip metadata fields
        obj.pop('metadata', None)
        obj.pop('source', None)
        obj.pop('category', None)
        obj.pop('difficulty', None)
        obj.pop('tags', None)
        pairs.append(obj)
print(f'Agentic capabilities: {len(pairs)} pairs')

# Multi-turn conversations
count_before = len(pairs)
with open('datasets/multi_turn_conversations.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        # Strip metadata fields
        obj.pop('metadata', None)
        obj.pop('source', None)
        obj.pop('category', None)
        obj.pop('difficulty', None)
        obj.pop('tags', None)
        pairs.append(obj)
count_multi = len(pairs) - count_before
print(f'Multi-turn conversations: {count_multi} pairs')

# Deterministic shuffle
random.shuffle(pairs)

with open('datasets/v5_agentic_combined.jsonl', 'w') as f:
    for p in pairs:
        f.write(json.dumps(p) + '\n')

print(f'')
print(f'Total: {len(pairs)} pairs -> datasets/v5_agentic_combined.jsonl')
print(f'Ready for: bash scripts/run_full_cycle.sh agentic datasets/v5_agentic_combined.jsonl v5-agentic v4-recovery')
"

echo "=== v5 batch ready ==="
