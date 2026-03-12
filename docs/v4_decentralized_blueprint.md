# Hive-AI v4.0: Full Decentralized Blueprint

> **Status**: FUTURE PLAN — Not yet started. Requires v3.0 style protection stack to be validated first.
>
> **Goal**: Absorb Bittensor/Templar (SparseLoCo + Gauntlet + R2 + Incentives) while keeping zero-regression loss guarantees.

---

## Vision

Take everything good from Covenant-72B (arXiv 2603.08163) and Templar (Subnet 3) — SparseLoCo (146x bandwidth reduction, dynamic peers), Gauntlet (trustless anti-regression scoring), R2 storage, permissionless GPU sharing, TAO incentives — and fork + customize + absorb it into the existing Hive-AI stack.

The single-GPU v3.0 stack (conditional `<direct>`/`<agentic>` prefixes + mean-init tokens + CURLoRA + EWC lambda=0.5 + probe-aware masked KL + mid-layer 24 MSE + dynamic weight + pre-shift analysis + 25-40% SSR replay + DELLA + 60-probe 3% gate + consolidation) stays **100% intact** and runs inside every miner.

**Result**: Near-zero regression (<1-2% even at 70+ peers scale) + internet-scale compute.

## Why This Eliminates the Training Bottleneck Forever

- Anyone with a GPU (even 4070 Ti) can mine and earn TAO
- DBC/Golden Books become deterministic shards → replay enforced at 25%
- Gauntlet + our probes = on-chain 3% gate
- SparseLoCo sparsity + error feedback + mid-layer anchoring = extra regularization beyond EWC/CURLoRA

**Effort**: 2-4 weeks MVP (we already know Unsloth/TRL/PEFT).

---

## 1. SparseLoCo Class (Adapted for LoRA Setup)

Clone the real repo (open-source, matches the paper exactly):

```bash
git clone https://github.com/one-covenant/SparseLoCo.git
cd SparseLoCo
uv sync  # or pip install -e .
```

Adapted version (`hiveai/lora/sparseloco.py`) — drop-in replacement for AdamW on LoRA adapters. LoRA-specific chunking, integrated with CURLoRA/EWC, only the needed parts (no full FSDP needed for LoRA):

```python
# hiveai/lora/sparseloco.py
import torch
from torch.optim import SGD
from typing import Optional
# Import the real ChunkingTransform and TopKCompressor from the repo
from src.tplr.chunking import ChunkingTransform
from src.tplr.compressor import TopKCompressor

class HiveSparseLoCo(SGD):
    """Adapted SparseLoCo for Qwen 2.5 14B + CURLoRA + PEFT setup"""
    def __init__(self, params, lr=1e-5, error_decay=0.95, top_k=64, chunk_size=4096,
                 quant_bits=2, use_quantization=True, decoupled_weight_decay=0.0, **kwargs):
        super().__init__(params, lr=lr, momentum=0.0, weight_decay=0.0, **kwargs)
        self.error_decay = error_decay
        self.top_k = top_k
        self.chunk_size = chunk_size
        self.quant_bits = quant_bits
        self.decoupled_weight_decay = decoupled_weight_decay

        self.chunking = ChunkingTransform(self.param_groups, chunk_size)
        self.compressor = TopKCompressor(use_quantization=use_quantization, quantization_bins=2**quant_bits)

        for group in self.param_groups:
            for p in group["params"]:
                if p.requires_grad:
                    self.state[p]["error_buffer"] = torch.zeros_like(p, device=p.device)

    @torch.no_grad()
    def step(self, closure=None):
        if closure is not None:
            closure()

        for group in self.param_groups:
            lr = group["lr"]
            for p in group["params"]:
                if p.grad is None:
                    continue

                # Decoupled weight decay (keeps EWC/CURLoRA clean)
                if self.decoupled_weight_decay != 0:
                    p.data.mul_(1.0 - lr * self.decoupled_weight_decay)

                state = self.state[p]
                error_buffer = state["error_buffer"]

                # Error feedback accumulation (this is the magic that lets 1-3% sparsity work)
                error_buffer.mul_(self.error_decay)
                error_buffer.add_(p.grad, alpha=lr)

                # Chunk + compress (paper exact)
                tensor_to_compress = self.chunking.encode(error_buffer)
                indices, values, shape, quant_params = self.compressor.compress(
                    tensor_to_compress, k=self.top_k
                )

                # Local reconstruction + error update
                local_recon = self.compressor.decompress(indices, values, shape, quant_params)
                transmitted = self.chunking.decode(local_recon)
                error_buffer.sub_(transmitted)

                # Simulate distributed aggregation (in miner: upload compressed; validator aggregates)
                # For single-GPU test: use local recon as "aggregated"
                p.grad.copy_(transmitted)  # In full distributed: replace with downloaded aggregate

        super().step()  # Calls SGD step on the aggregated sparse grad
```

**Diff vs current trainer** (in `train_v5.py`):

```python
# OLD
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5)

# NEW (replace with CURLoRA params only)
optimizer = HiveSparseLoCo(
    model.parameters(),  # or peft_model.base_model.model.parameters() for LoRA only
    lr=1e-5,
    error_decay=0.95,   # paper default for stability
    top_k=64,           # tune to 1-3% of LoRA params
    chunk_size=4096,
    quant_bits=2
)
```

This gives 146x lower comms + natural regularization (error feedback prevents drift) on top of CURLoRA/EWC.

---

## 2. Full miner.py Skeleton (With v3.0 Pipeline Inside)

```python
# scripts/miner.py
import bittensor as bt
import torch
from hiveai.lora.sparseloco import HiveSparseLoCo
from unsloth import FastLanguageModel
from trl import SFTTrainer

class HiveMiner:
    def __init__(self):
        self.wallet = bt.wallet(...)
        self.subnet = bt.subtensor().subnet(999)  # our netuid
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(...)

    def run_training_window(self):
        # Bittensor window trigger
        shard_manifest = self.download_from_r2(self.subnet.get_shard(self.wallet.hotkey.uid))
        dataset = self.load_dbc_shard(shard_manifest)

        # v3.0 PIPELINE — fully preserved
        dataset = self.add_style_prefixes(dataset)  # <agentic> for new, <direct> for 25% replay
        replay = self.load_replay_buffer(fraction=0.25)  # Covenant-style + SSR
        mixed_dataset = self.mix_uniform(dataset, replay)

        # Probe-aware + mid-layer MSE trainer
        trainer = self.create_probe_aware_trainer(
            model=self.model,
            dataset=mixed_dataset,
            v4_reference=self.v4_model,  # for anchoring
            probe_weight=0.2
        )

        # SparseLoCo optimizer
        optimizer = HiveSparseLoCo(self.model.parameters(), lr=1e-5, top_k=64)

        # Train
        trainer.train()

        # Compute & compress delta
        delta = self.compute_pseudo_gradient(self.model)  # theta_old - theta_new
        compressed_delta = self.compress_for_r2(delta)  # top-k + 2-bit from SparseLoCo

        # Upload
        self.upload_delta_to_r2(compressed_delta, self.wallet.hotkey.uid)
        # Gauntlet will score it automatically

if __name__ == "__main__":
    miner = HiveMiner()
    while True:
        miner.run_training_window()  # triggered by Bittensor blocks
```

Run with: `python scripts/miner.py --netuid 999`

---

## 3. R2 Upload Script for Deltas

```python
# hiveai/storage/r2.py
import boto3
import torch
import os

s3 = boto3.client(
    's3',
    endpoint_url=os.getenv("R2_ENDPOINT"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
)

def upload_delta(compressed_delta: dict, peer_uid: int, window_id: int):
    key = f"gradients/peer_{peer_uid}_window_{window_id}.pt"
    torch.save(compressed_delta, "/tmp/delta.pt")
    s3.upload_file("/tmp/delta.pt", os.getenv("R2_BUCKET_NAME"), key)
    print(f"Uploaded delta for peer {peer_uid} — size ~few MB thanks to SparseLoCo")

def download_aggregate(window_id):
    # Validator aggregates top-scoring deltas
    ...
```

---

## 4. Subnet Registration Walkthrough

```bash
# 1. Install Bittensor
pip install bittensor

# 2. Create wallet
btcli wallet create --wallet.name default

# 3. Register subnet (you become owner)
btcli subnet create --netuid 999 --wallet.name default --wallet.hotkey default

# 4. Set custom rules (optional — enforce probe gate)
btcli subnet hyperparameters --netuid 999 --param ...

# Test locally first with --local
```

**Strategy**: Start on Templar SN3 (netuid 3) to piggyback existing miners, then move to own subnet.

---

## 5. Full v4.0 Layered Protection (v3.0 + Templar Upgrades)

| Layer | Source | Description |
|-------|--------|-------------|
| Replay 25% | Covenant annealing + SSR | Enforced in every miner |
| SparseLoCo | Templar | Sparsity + error feedback + mid-layer 24 MSE |
| Gauntlet | Templar | + our 60-probe 3% gate (LossScore = 0.7*loss_improvement + 0.3*(1-probe_drop)) |
| Style prefixes | v3.0 | Mean-init in every miner |
| CURLoRA/EWC | v3.0 | Inside SparseLoCo step |
| Pre-shift analysis | v3.0 | On every shard |

### Extra zero-loss techniques

- Gauntlet normalizes delta magnitude (prevents style dominance)
- Dynamic participation: peers join/leave, consolidation pass runs centrally after aggregation
- 25% replay + domain-balanced boost to 40% on weak domains

### Revenue & Scale

- Miners earn TAO proportional to Gauntlet score
- DBC nodes auto-mine for extra income
- Go from 1 GPU to 70+ overnight

---

## Immediate Next Steps (When Ready)

1. Clone SparseLoCo + Templar repos (5 min)
2. Add the `HiveSparseLoCo` class + test on v5 run (30 min)
3. Create R2 buckets + upload one test delta
4. Run `miner.py` in local mode with 2 processes

---

## Prerequisites (Must Complete First)

- [ ] v3.0 style protection stack validated on a successful training cycle
- [ ] v5-agentic re-run with v3.0 defenses passes regression eval
- [ ] Bittensor SDK familiarization
- [ ] R2/Cloudflare account setup
- [ ] SparseLoCo repo cloned and tested locally

---

## Open Considerations

- **Aggregation → golden chain**: Current merge-then-freeze assumes one LoRA at a time. With 70 peers, need clear aggregation → merge → consolidation → promote flow.
- **Data curation stays centralized**: Miners train on pre-built shards, NOT run full crawl pipeline. Quality control is our moat.

---

## Solved: Custom Tokenizer Sync in Distributed Training

Every miner must use the exact same tokenizer (same vocab, same special token IDs, same added tokens)
or the parameter deltas will be misaligned and training will corrupt.

### Solution: Canonical tokenizer on HF + hash validation

1. **Publish canonical tokenizer** as `Dhenz14/HiveAI-Tokenizer-v4` on Hugging Face
   - Push full tokenizer folder: `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`
   - Include `tokenizer_version.txt` with SHA256 hash of json files

2. **Miner startup bootstrap** (in `scripts/miner.py`):

```python
from transformers import AutoTokenizer
import hashlib

CANONICAL_TOKENIZER = "Dhenz14/HiveAI-Tokenizer-v4"
tokenizer = AutoTokenizer.from_pretrained(CANONICAL_TOKENIZER, trust_remote_code=True)
tokenizer.add_special_tokens({
    "additional_special_tokens": ["<direct>", "<agentic>"]
})

# Hash check prevents drift
expected_hash = "your-fixed-sha256-hash-here"
current_hash = hashlib.sha256(open(tokenizer.vocab_file, "rb").read()).hexdigest()
assert current_hash == expected_hash, "Tokenizer mismatch — aborting"
```

3. **R2 training-window manifest includes tokenizer reference**:

```json
{
  "window_id": 12345,
  "tokenizer_repo": "Dhenz14/HiveAI-Tokenizer-v4",
  "tokenizer_hash": "your-fixed-sha256-hash-here",
  "shard_manifest": [...]
}
```

4. **All data preprocessing uses canonical tokenizer** — never fall back to base model's tokenizer
5. **Final merged model ships with tokenizer** — downstream users get it automatically

---

## Phase 5.5: Basilica GPU Verification

Gauntlet catches bad *results*. Basilica catches bad *hardware claims* before they waste time.

Clone `github.com/one-covenant/basilica` (Subnet 39 — official decentralized GPU verifier).

In validator (`scripts/validator.py`), before running Gauntlet LossScore:

```python
from basilica import verify_hardware

proof = miner_hotkey.get_basilica_proof()  # miners run basilica daemon alongside
if not verify_hardware(proof, expected_min_vram=24_000, expected_compute=your_threshold):
    score = 0  # instantly zero-weight cheaters
```

Miners run the Basilica daemon (~50 MB RAM) — trustless benchmarks + cryptographic proofs on-chain.

## Open-Source Repos (All Apache 2.0)

| Component | Repo | Purpose |
|-----------|------|---------|
| Templar framework | github.com/one-covenant/templar | Full miner/validator code for GPU sharing |
| SparseLoCo optimizer | github.com/one-covenant/SparseLoCo | Low-bandwidth gradient compression |
| Gauntlet scoring | (integrated in templar repo) | Trustless reward scoring via TAO |
| Basilica | github.com/one-covenant/basilica | GPU hardware verification (anti-cheat) |
| Grail | github.com/one-covenant/grail | Post-training/RL on distributed compute |
| Bittensor SDK | github.com/opentensor/bittensor | Network interaction, hotkeys, weights |
| Subnet template | github.com/opentensor/bittensor-subnet-template | Base for custom subnet |
| Model weights | huggingface.co/1Covenant/Covenant-72B | Reference checkpoints |

## Gems from Grok Review (Filtered — Only Usable Parts)

### Tokenizer Utils (save as `hiveai/tokenizer_utils.py` when ready)

```python
import hashlib
from transformers import AutoTokenizer

CANONICAL_REPO = "Dhenz14/HiveAI-Tokenizer-v4"
EXPECTED_HASH = "compute-once-and-hardcode"

def load_canonical_tokenizer():
    tokenizer = AutoTokenizer.from_pretrained(CANONICAL_REPO, trust_remote_code=True)
    tokenizer.add_special_tokens({
        "additional_special_tokens": ["<direct>", "<agentic>"]
    })
    vocab_path = tokenizer.vocab_file or "tokenizer.json"
    with open(vocab_path, "rb") as f:
        computed = hashlib.sha256(f.read()).hexdigest()
    assert computed == EXPECTED_HASH, f"Tokenizer mismatch! Expected {EXPECTED_HASH}"
    return tokenizer
```

### Miner CLI Structure (bittensor arg pattern — reuse this skeleton)

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    bt.wallet.add_args(parser)
    bt.subtensor.add_args(parser)
    parser.add_argument("--netuid", type=int, default=999)
    config = bt.config(parser)
    miner = HiveMiner(config)
    miner.run()
```

### R2 Delta Upload (minimal boto3 pattern)

```python
import boto3, torch, os

s3 = boto3.client('s3',
    endpoint_url=os.getenv("R2_ENDPOINT"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
)

def upload_delta(compressed_delta: dict, peer_uid: int, window_id: int):
    key = f"gradients/peer_{peer_uid}_window_{window_id}.pt"
    torch.save(compressed_delta, "/tmp/delta.pt")
    s3.upload_file("/tmp/delta.pt", os.getenv("R2_BUCKET_NAME"), key)
```

### Validator Scoring Formula (Gauntlet + retention)

```python
# Core scoring logic for validator — weight miners by quality
loss_score = loss_before - loss_after  # held-out loss improvement from delta
retention_score = probe_before - probe_after  # positive = no forgetting (use our 60 probes)
hardware_ok = verify_basilica(uid)  # GPU attestation

final_score = (0.6 * loss_score + 0.3 * retention_score) if hardware_ok else 0.0
# Set on-chain: subtensor.set_weights(uids=[uid], weights=[final_score], netuid=...)
```

### R2 Window Manifest Schema

```json
{
  "window_id": 12345,
  "phase": "annealing",
  "tokenizer_repo": "Dhenz14/HiveAI-Tokenizer-v4",
  "tokenizer_hash": "sha256-here",
  "replay_ratio": 0.25,
  "shard_manifest": ["shards/12345/000000.jsonl", "..."],
  "probe_set": "probe_set.json"
}
```

### Replay Ratios (from Covenant paper)

- **Annealing phase**: 25% replay (paper default, matches our current pipeline)
- **SFT phase**: 20% replay
- Our `replay_sampler.py` SuRe NLL scoring is superior to Templar's uniform sampling — keep ours, just load from R2 instead of local JSONL in distributed mode

### Validator Block Timing

- Bittensor validators run every ~12s (block time) — score loop should match this cadence

### What NOT to Use from Grok's Code

- **miner.py `_train_step()`**: Naive `model(**inputs).loss` — ignores our 6-phase `compute_loss_with_kl()`. Must wrap our real trainer, not replace it.
- **`SparseLoCoOptimizer` import**: Doesn't exist as a pip package. Real repo exposes `ChunkingTransform` + `TopKCompressor` as building blocks.
- **`basilica-sdk==0.25.2`**: Fabricated pin. Basilica is Subnet 39 source code, not a pip package.
- **`sparse-loco @ git+https://...`**: Pin to commit hash, not main branch.
- **`from basilica import get_hardware_proof`**: Fabricated API. Clone the repo and import from source.
- **`ReplayBuffer` loading from R2**: Pattern is fine but our `replay_sampler.py` with SuRe NLL scoring is far more sophisticated — adapt ours for R2, don't replace it.
- **validator `_compute_loss_score` / `_compute_retention_score`**: Placeholder `return 0.85` — needs real forward pass logic against our probe library.

## Research References

- Covenant-72B (arXiv 2603.08163) — SparseLoCo, Gauntlet scoring
- Templar Subnet 3 — Bittensor decentralized training
- CURLoRA (2024) — github.com/MNoorFawi/curlora
- SAP (ICML 2025) — Safety-Aware Probing
- DistillLens (ACL 2025) — Intermediate layer KD
