# Hive AI DBC Plan
## Decentralized Brain Collective

**Status:** COOKING — living document, evolving as we build
**Last updated:** 2026-02-28 (v3.7 — protocol hardening: epoch timeout, verification sybil defense, secrets scanner, RC management, challenge pinning, chain lib resilience, cold start bootstrap)

---

## Vision

A decentralized AI that gets smarter from worldwide community contributions.
Contributors mine knowledge. Trainers forge LoRA adapters. The collective brain
auto-updates across all nodes. Coordinated entirely through the Hive blockchain
and HivePoA network. No central server. Intelligence owned by no one, improved
by everyone.

---

## Core Insight

LoRA fine-tuning doesn't need distributed training. A single RTX 4070 trains
500 pairs in 2-4 hours. The bottleneck is data quality, not compute.

Two properties make this trustless without cryptographic proofs:

1. **Scoring is deterministic.** Pure Python math (AST, regex, heuristics). Same
   pair in → same score out on every machine. No LLM needed.
2. **Eval is deterministic.** Same adapter + same challenges + `seed=42, top_k=1,
   temp=0` = same scores. Any node can verify any claim.

These two facts eliminate shadow trainers, ZK proofs, and dedicated verifier roles.
The eval harness is the immune system — every attack that matters shows up as a
bad eval score.

**Design principle: derive, don't store.** If a value can be computed from data
already on-chain, don't put it on-chain. The training set is derived from a
block range (not a pair list). The flatten schedule is derived from the epoch
count (not a flag). File integrity is derived from the IPFS CID (not a separate
hash). Previous eval scores are derived from chain history (not a redundant
field). Every field earns its place or gets cut.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 HIVE BLOCKCHAIN                   │
│                                                   │
│  Training pairs    (on-chain, gzip+base64)       │
│  Epoch configs     (block range + seed)          │
│  Version records   (adapter CID + eval score)    │
│  Verification votes                               │
│                                                   │
│  All free. Resource Credits only.                 │
└──────────┬────────────────────────────────────────┘
           │
     ┌─────┴─────┐
     │           │
 ┌───▼──┐   ┌───▼────┐
 │ MINE │   │ TRAIN  │
 │      │   │        │
 │Anyone│   │Vouched │
 │      │   │(WoT)   │
 │Pairs │   │        │
 │on-   │   │Collect │
 │chain │   │Train   │
 │      │   │Eval    │
 │      │   │Publish │
 └──────┘   └───┬────┘
                │
                ▼
     ┌─────────────────┐
     │  HivePoA / IPFS  │
     │                   │
     │  Base model GGUF  │
     │  Adapter GGUF     │
     │  PoA storage      │
     │  P2P CDN          │
     │  HBD payments     │
     └─────────────────┘
```

Two roles. Three infrastructure layers. That's the whole system.

---

## Role 1: Miners — Anyone running HiveAI

**What they do:** Generate training pairs through normal usage.

**Flow:**
1. Chat with HiveAI → knowledge gap detected → auto-mine fills it
2. Distiller generates instruction/response pair
3. **Pre-chain intelligence gate** (6 gates, all must pass):
   - Gate 1: Quality scorer >= 0.85 (on-chain bar is higher than local 0.70)
   - Gate 2: Code execution — all code blocks run in sandbox, pass rate >= 0.5
   - Gate 3: Local dedup — not a duplicate of pairs in local DB
   - Gate 4: On-chain dedup — not a duplicate of pairs already on the blockchain
   - Gate 5: Coverage gap — topic not already saturated on-chain
   - Gate 6: Secrets scanner — regex scan for API keys, private keys, PII, local paths
4. If all gates pass AND user has opted in (`enable_dbc = true`):
   gzip + base64 encode → post to Hive as `custom_json`

**Privacy gate:** DBC contribution is opt-in, defaulting to OFF. Users chatting
about proprietary code must never have pairs auto-submitted. The setting is per-
instance. When enabled, a background agent handles submission automatically —
the user doesn't interact with it.

**On-chain pair format:**

```json
custom_json id: "hiveai"
{
  "type": "pair",
  "data": "<gzip+base64 encoded instruction+response>",
  "score": 0.87,
  "lang": "python",
  "topic": "concurrency",
  "scorer": "v5.2"
}
```

**Why on-chain, not IPFS:**
Hive `custom_json` max is 8,192 bytes. A 10 KB pair gzips to ~4 KB, base64 to
~5.3 KB — fits with room to spare. Zero cost (RC regenerates). Permanent.
Immutable. No pinning, no daemon, no "is my file still there?" questions.

**Requirements:** Any machine. Ollama or OpenRouter for LLM during mining.
No GPU needed.

---

## Role 2: Trainers — Vouched GPU nodes

**What they do:** Everything else. Collect pairs, verify quality, train,
evaluate, publish.

**Eligibility:** HivePoA Generic Trusted-Role Registry (`dbc_trainer` role).
A candidate needs 2+ vouches from top-150 Hive witnesses. Witnesses can vouch
for multiple candidates. Vouch auto-revokes if the witness drops below rank 150.
Eligibility is binary (eligible or not) — no HP weighting on the privileged path.
Hive-AI checks eligibility via `GET /api/trust/check/:username/dbc_trainer`.

**The epoch lifecycle:**

```
Trainer available + cooldown elapsed + >= 4h since last epoch
              │
              ▼
  Trainer claims epoch (publishes config to Hive)
  Epoch includes ALL unclaimed pairs since last epoch (auto-sized)
  Cooldown prevents same trainer doing consecutive epochs
              │
              ▼
  Collect pairs: replay chain from last epoch's end block to now
  Filter: score >= 0.75, scorer >= v5.2
  Re-score locally — reject any that don't match (±0.03)
  Dedup against ALL historical pairs (cumulative embedding index)
              │
              ▼
  Train with locked config (seed, LR, everything pinned)
  20% replay from previous epoch's data
              │
              ▼
  Run eval: 125 challenges, seed=42, top_k=1, temp=0
              │
              ▼
  Publish to Hive: adapter CID + eval score
  Upload adapter to HivePoA storage contract
              │
              ▼
  Nodes verify: download adapter, re-run eval
  Accept if eval within ±0.02 of claimed
              │
         ┌────┴────┐
         │         │
      ACCEPT    REJECT
      Nodes     Trainer
      update    flagged
```

**Why the trainer verifies pairs (no Checker role):**

The trainer has the strongest incentive to filter garbage — they're about to
spend 2-4 hours of GPU on this data. If a miner lied about a quality score,
the trainer catches it during re-scoring. Bad pairs in → bad adapter out →
fails eval → trainer's work is wasted. Self-interest aligns with quality.

**Epoch config (on-chain):**

```json
custom_json id: "hiveai"
{
  "type": "epoch",
  "v": "3.1",
  "base_cid": "Qm...",
  "blocks": [82000000, 82100000],
  "min_score": 0.75,
  "scorer": "v5.2",
  "seed": 31,
  "script": "a1b2c3",
  "dedup_cid": "Qm..."
}
```

**Key simplification:** No pair list on-chain. `blocks: [from, to]` defines
the range. Anyone replays the chain between those blocks, extracts all `hiveai`
custom_json with `type: "pair"` and `score >= 0.75`, and reconstructs the
exact same training set. Deterministic from on-chain data alone.

`script` is the git commit hash of `train_incremental.py`. All hyperparameters
live in the script, not on-chain. The script is open source. The hash pins it.

`dedup_cid` (optional) is the cumulative dedup embedding index. Next trainer
downloads it instead of rebuilding from chain replay (~10 MB per 1000 pairs).
It's a cache, not source of truth — chain replay is the deterministic fallback.

**Version announcement (on-chain):**

```json
custom_json id: "hiveai"
{
  "type": "version",
  "v": "3.1",
  "cid": "Qm...",
  "eval": 0.867
}
```

Two fields removed: `sha256` is redundant (IPFS CIDs ARE content hashes —
`Qm...` is `base58(SHA-256(content))`; downloading by CID guarantees
integrity). `prev_eval` is derivable (look up the `base_cid` epoch's version
record on-chain).

**Verification by any node (on-chain):**

```json
custom_json id: "hiveai"
{
  "type": "verify",
  "v": "3.1",
  "eval": 0.865,
  "accept": true
}
```

No dedicated Checker role. Verification is what nodes do before accepting an
update. The auto-updater runs eval before swapping adapters. If the score
matches the trainer's claim → update. If not → reject and post a `verify`
with `accept: false`. Trust emerges from self-interest: every node protects
itself.

**Requirements:** GPU (RTX 3060+ / 12GB+ VRAM). HivePoA Web of Trust vouch.

---

## How The Brain Gets Updated

**What the brain IS:** A file. A single GGUF file (~300 MB) containing neural
network weight adjustments. Not a running service. Not a database. Static
bytes, like a PDF. The "brain" = base model (12 GB, never changes) + adapter
(300 MB, this is what gets updated).

**Where it lives:** Everywhere. IPFS is content-addressed — the CID is a hash
of the file. Download by CID from any peer that has it. Every copy is provably
identical. No "main server." Trainer uploads → nodes download → now they're all
hosts. More hosts = faster downloads. HivePoA pays nodes to keep hosting.

**How updates work (the queue):**

```
1. PAIRS ACCUMULATE (parallel — many users at once)
   Users chat → pairs generated → 6-gate filter → on-chain
   Gate 4 prevents duplicates across users

2. TRAINER CLAIMS EPOCH (sequential — first-come-first-served)
   Posts epoch config to Hive → this IS the lock
   First claim in a block wins. Others must wait.

3. TRAINER TRAINS (solo — 2-4 hours)
   Downloads previous adapter from IPFS
   Replays chain for pairs in the block range
   Trains on top of previous adapter weights
   Output: new adapter file

4. TRAINER PUBLISHES (adapter → IPFS, metadata → Hive)
   Upload new adapter → get CID
   Post version announcement with CID + eval score

5. NODES VERIFY AND UPDATE (parallel — everyone at once)
   GPU nodes: download adapter, run eval, compare scores
   Match? Swap adapter. Post accept vote.
   Non-GPU nodes: wait for 3+ accept votes, then swap.

6. NEXT TRAINER CAN NOW CLAIM
   Their base_cid = the adapter that was just published
   Linear chain: v3.0 → v3.1 → v3.2 → ... → v4.0 (flatten)
```

**Hosting is parallel. Training is sequential.** Many nodes host the same
adapter file simultaneously. But only one trainer produces the next version,
because each version builds on the previous weights. The blockchain is the
queue manager — epoch claims are timestamped and immutable.

---

## The Version Chain

```
v3.0 (base)       ← full train, 2,385 pairs, ~16h
  └→ v3.1         ← +200 pairs, lr=4e-5, ~4h
      └→ v3.2     ← +300 pairs, ~5h
          └→ v3.3 ← +250 pairs, ~4h
              └→ v3.4 ← +200 pairs, ~4h
                  └→ v4.0 ← FLATTEN (full retrain on ALL pairs, ~16h)
                      └→ v4.1 ← +200 pairs
```

**Incremental training:**
- Resume from previous adapter
- Learning rate: 1/5th of base (4e-5 vs 2e-4)
- 20% replay from previous data (prevents catastrophic forgetting)
- 1 epoch only
- LoRA inherently resists forgetting (TMLR 2024)

**Flatten:** Derived from chain state: `count(type:"epoch" on-chain) % 5 == 0`.
No flag, no governance vote. The trainer counts epoch operations on-chain and
knows whether this is a flatten. Flatten epochs use full LR and `blocks: [0,
latest]` (all historical pairs). Everything else stays the same.

---

## Throughput & Scaling

**Per-epoch timing (RTX 4070 class):**

| Phase | 200 pairs | 500 pairs | 1000 pairs |
|-------|-----------|-----------|------------|
| Collect + re-score + dedup | ~5 min | ~10 min | ~15 min |
| Train (1 epoch, lr=4e-5) | ~1.5 hours | ~3 hours | ~5.5 hours |
| Eval (125 challenges) | ~30 min | ~30 min | ~30 min |
| Publish | ~2 min | ~2 min | ~2 min |
| **Total** | **~2 hours** | **~3.5 hours** | **~6 hours** |

**Capacity (1 trainer, 5 pairs/user/day):**

| Epoch size | Epochs/day | Pairs/day | Users served |
|------------|-----------|-----------|-------------|
| 200 | ~12 | 2,400 | ~500 |
| 500 | ~7 | 3,500 | ~700 |
| 1,000 | ~4 | 4,000 | ~800 |

**Auto-scaling:** Epoch size isn't fixed. The trainer claims all unclaimed pairs
since the last epoch. Low traffic → small fast epochs. High traffic → large
epochs, fewer versions but same throughput. No threshold to configure.

**Pipeline overlap with multiple trainers:**

```
Trainer A: [prep 5m][TRAIN v3.1    1.5h][EVAL 30m][pub]
Trainer B:                         [prep        ][TRAIN v3.2    1.5h][EVAL]
Trainer C:                                        [prep              ][TRAIN v3.3]
```

Training is sequential (each epoch builds on the previous adapter). But
preparation (collect, re-score, dedup, export JSONL) overlaps with the
previous trainer's GPU phase. With 3 rotating trainers, gap between epochs
shrinks from ~2 hours to ~1.5 hours.

**Cross-epoch dedup:** Trainers maintain a cumulative embedding index of ALL
historical training pairs (across all epochs). New pairs are compared against
this index before training. Prevents the same knowledge from being learned
twice across different epochs.

---

## Storage

**Layer 1 — Hive blockchain:** All training data and coordination. On-chain,
free, permanent.

| What | Size | Cost |
|------|------|------|
| Training pair | 2-6 KB | Free (RC) |
| Epoch config | ~200 bytes | Free (RC) |
| Version record | ~200 bytes | Free (RC) |
| Verification vote | ~100 bytes | Free (RC) |

**Layer 2 — GitHub Releases:** Base model distribution.

| What | Size | Cost |
|------|------|------|
| Base model GGUF (7 parts) | ~12 GB | Free |

Split into 2 GB release assets. GitHub CDN, global, always-on, resume-capable.
No bandwidth limit. Open-source model in an open-source home.

**Layer 3 — HivePoA:** Adapter storage + distribution.

| What | Size | Cost |
|------|------|------|
| LoRA adapter GGUF | 200-400 MB | ~$4 HBD/year |

HivePoA nodes pin adapters and earn HBD through Proof of Access challenges
(every 4 hours, 25s anti-cheat timing). Desktop agents auto-pin popular
adapters for P2P delivery via WebRTC.

**No HuggingFace. No external dependencies.** App, base model, and adapters
all come from the GitHub + Hive ecosystem.

---

## Auto-Update

Two paths depending on whether the node has a GPU:

**GPU nodes (verify themselves):**
```python
if data["type"] == "version":
    adapter = download_from_hivepoa(data["cid"])
    my_eval = run_eval(adapter, seed=42, top_k=1, temp=0)

    if abs(my_eval - data["eval"]) < 0.02 and my_eval > current_eval:
        swap_adapter(adapter)
        broadcast_verify(data["v"], my_eval, accept=True)  # free (RC)
    else:
        broadcast_verify(data["v"], my_eval, accept=False)
```

**Non-GPU nodes (trust consensus):**
```python
if data["type"] == "version":
    # Wait for verification votes from GPU nodes
    votes = get_on_chain_verifications(data["v"])
    accepts = [v for v in votes if v["accept"]]
    # HP-weighted consensus (see Protocol Hardening §2)
    if hp_weighted_consensus(votes):  # 5000 HP total, 3+ unique, 100 HP min each
        adapter = download_from_hivepoa(data["cid"])
        swap_adapter(adapter)
```

**Why verification is incentive-free:** GPU nodes verify for self-interest
(don't install a bad adapter). Posting the vote on-chain costs nothing (RC).
The incentive is inherent — no reward system needed. Non-GPU nodes free-ride
on GPU nodes' self-interested verification. Everyone benefits.

New adapters require a graceful llama-server restart (~5 seconds). Acceptable
for updates every few days. Users can pin a specific version and opt out.

---

## Security

**One principle:** The eval harness is the immune system.

| If someone tries to... | What happens |
|------------------------|-------------|
| Submit garbage pairs | Trainer re-scores before training. Fails ±0.03 check. Rejected. |
| Lie about pair quality | Trainer re-scores. Mismatch detected. Pair skipped. |
| Train a bad adapter | Eval score is low. Nodes reject. Trainer wastes GPU time. |
| Claim fake eval scores | GPU nodes re-run eval; non-GPU nodes require HP-weighted consensus (5000 HP total, 100 HP min/voter). |
| Swap adapter file | CID IS the hash. Download by CID = integrity guaranteed. No separate SHA-256 needed. |
| Poison an adapter | 125 eval challenges catch it. Poisoned model fails benchmarks. |
| Monopolize training | WoT limits trainers. Cooldown between epochs. |
| Deny storage | HivePoA PoA challenges verify files exist. Nodes earn for storing. |

**What isn't protected:** Majority witness collusion (same risk as Hive itself).
Base model vulnerabilities (out of scope). Eval overfitting (mitigated by
rotating challenge sets).

Deterministic computation is the foundation. Any claim — pair score, eval score,
training result — can be independently verified by anyone with Python and the
scorer. No trust required. Lies are provable.

---

## Pre-Chain Intelligence Gate

Nothing touches the blockchain unless it passes 6 gates. On-chain is permanent
and immutable — the chain must be a curated knowledge graph, not a dumping ground.

```
Pair  ──► G1: QUALITY ──► G2: EXECUTION ──► G3: LOCAL DEDUP
generated    >= 0.85         code runs         not in local DB
             code present    pass rate >= 0.5  tiered similarity
             valid syntax    self-refine       thresholds
                             if failures
                                │
                                ▼
          G4: ON-CHAIN DEDUP ──► G5: COVERAGE GAP ──► G6: SECRETS ──► POST TO CHAIN
             not on blockchain     topic not             no API keys      gzip + base64
             already               saturated             no private keys  custom_json
             sim > 0.85 = block    under-served          no PII/emails
             sim 0.70-0.85 =      topics get             no local paths
             only if +0.10        priority boost
             quality better
```

**Three quality thresholds, three purposes:**

| Threshold | Purpose | Why different |
|-----------|---------|---------------|
| 0.70 | Local training — kept in local DB | Experimental, private |
| 0.75 | Trainer acceptance — used in LoRA training | Verified by trainer |
| **0.85** | **On-chain submission — permanent, public** | **Must be rock solid** |

A 0.72 pair is "good enough for local experiments." A 0.85 pair is "this is
genuinely high-quality knowledge worth making permanent." The 0.85 bar means
only the top ~48% of generated pairs (based on current distribution) ever
touch the chain.

### Gate 4: On-Chain Dedup (new)

Every DBC-enabled node streams the blockchain. For every `type: "pair"` that
appears, the node decompresses it, embeds the instruction, and adds the
embedding to a local index. This builds naturally — no coordination needed.

Before posting a new pair, the node checks:

```python
max_similarity = max(cosine_similarity(new_embedding, on_chain_index))

if max_sim > 0.85:
    return BLOCK          # Already well-covered on-chain

if max_sim > 0.70:
    existing = on_chain_pairs[argmax(similarities)]
    if new_quality < existing.score + 0.10:
        return BLOCK      # Not enough improvement over existing
    return SUBMIT         # Better answer to a known question

return SUBMIT             # New knowledge — genuinely uncovered territory
```

**Race condition:** Two nodes might submit similar pairs before seeing each
other's. Acceptable — the trainer dedup catches it during collection. The goal
is to minimize on-chain waste, not achieve perfection. A few overlaps in a
3-second block window are harmless.

### Gate 5: Coverage Gap (new)

The node tracks topic distribution from on-chain pairs:

```python
coverage = count_on_chain_pairs_by(language, topic_category)
# {"python/data_structures": 45, "cpp/memory_management": 3, ...}
```

Topics with few on-chain pairs get a priority boost. Topics already saturated
face a higher quality bar. This creates a **self-balancing knowledge economy**:

- Early on, everything is a gap → pairs flow freely
- As coverage grows, the bar rises for well-covered topics
- Under-represented domains (C++, Hive SDK) get auto-prioritized
- The brain grows toward **maximum diversity per on-chain byte**

| On-chain pairs for topic | Quality bar to submit |
|--------------------------|----------------------|
| 0 (uncovered) | 0.85 (standard) |
| 1-10 (sparse) | 0.85 |
| 11-30 (moderate) | 0.88 |
| 31-50 (well-covered) | 0.92 |
| 50+ (saturated) | 0.95 (near-perfect only) |

The distiller can also be steered: "We have 45 Python data structure pairs
but only 3 C++ memory management pairs. If the user's question touches C++,
prioritize generating that pair." The mining becomes intelligent — every pair
fills a real gap.

### What already exists vs what's new

| Gate | Existing code | New code needed |
|------|--------------|-----------------|
| Quality (0.85) | `_score_quality()` in distiller.py | Raise threshold for on-chain path |
| Execution | `verify_response_code()` in sandbox.py | Wire into submission path |
| Local dedup | `is_duplicate()` in dedup.py | Already works |
| On-chain dedup | Embedding infra (bge-m3, 1024-dim) | `OnChainIndex` class, ~50 lines |
| Coverage gap | `topic` field on TrainingPair | Topic counting + priority, ~30 lines |

### Pair Size Overflow (Large Pairs)

Hive `custom_json` max is 8,192 bytes. Most pairs fit after gzip+base64
(~5.3 KB for a 10 KB pair). But complex code pairs with extensive
explanations can exceed 15-25 KB — gzip ratio varies with content.

**When a pair exceeds the limit, store the full pair on HivePoA and post
a lightweight CID reference on-chain:**

```python
encoded = base64.b64encode(gzip.compress(pair_json.encode())).decode()

if len(encoded) + 200 <= 7500:  # room for JSON wrapper
    # Standard path: inline data
    payload = {"type": "pair", "data": encoded, "score": 0.87, ...}
else:
    # Overflow path: CID reference
    cid = upload_to_hivepoa(pair_json)
    payload = {"type": "pair", "data_cid": cid, "score": 0.87,
               "size": len(pair_json), ...}
```

`data` and `data_cid` are mutually exclusive. Trainers check for `data_cid`
and download from HivePoA/IPFS instead of decoding inline. Old nodes that
don't understand `data_cid` skip those pairs (graceful degradation).

Cost: ~$0.001 per overflow pair on HivePoA. Negligible. Estimated <5% of
pairs will overflow — the quality gate already filters very long low-value
responses, and the best pairs tend to be concise.

---

## Genesis & Bootstrap

**v3.0 is the Big Bang.** We train it locally (happening now). We upload the
adapter to HivePoA, post the version announcement to Hive manually. This is
the one exception where the chain has no derivable history — it's the genesis.

The DBC protocol starts at v3.1. Every version after that has a full on-chain
lineage: epoch config → block range → pairs → training script → adapter CID.

**We are the genesis trainer.** We commit to running the first trainer node.
As the community grows, more trainers join. Natural incentive: trainers get
the latest brain FIRST (before verification propagates to other nodes).

**Bootstrap adapter distribution:** During early days, every adapter goes to
BOTH HivePoA AND GitHub Releases. Nodes try HivePoA first, fall back to
GitHub. As HivePoA gains nodes, the GitHub fallback becomes unnecessary.

```json
{"type": "version", "v": "3.1", "cid": "Qm...", "github": "v3.1", "eval": 0.867}
```

The `github` field is optional. When HivePoA is mature, stop including it.

**Testnet strategy:** Before mainnet launch, validate the full protocol on Hive's
public testnet (`https://testnet.openhive.network`). Testnet has free accounts,
free RC, and identical API behavior. Run at least 2 full epoch cycles (seed →
claim → train → publish → verify → update) end-to-end. This catches serialization
bugs, RC estimation errors, and timing issues without risking real chain state.
Alternatively, a local mock chain mode (in-memory dict mimicking `custom_json`
read/write) enables fast iteration during Phase 1 development.

---

## Eval Integrity

The eval harness is the immune system. If it can be gamed, nothing else matters.

**Problem:** 125 public challenges = a trainer could train specifically on them.

**Solution: Rotating subset from a growing pool.**

The challenge pool is public and open source (target 500+).
Each epoch uses a **random 125-challenge subset** determined by the epoch seed:

> **Pre-launch requirement:** The current eval harness has 115 challenges.
> Rotation requires a pool **strictly larger than 125** (ideally 200+) so that
> subsets are meaningfully different between epochs. Before DBC launch, expand
> the challenge pool to at least 200 challenges across all domains. Until then,
> rotation is disabled and all challenges are used for every epoch.

```python
random.seed(epoch_config["seed"])
subset = random.sample(all_challenges, 125)
```

No one knows which 125 will be used for a given epoch until the seed is
published in the epoch config. Training specifically on any 125 challenges
means ignoring the other 375 — the next epoch will likely pick a different
subset, tanking the score.

All nodes use the same seed for the same epoch → deterministic verification
still works. The challenge set version is pinned by the `script` hash.

New challenges are added via PR to the open-source repo. The growing pool
makes overfitting progressively harder. Community can contribute challenges.

---

## Distribution — Three Layers

**Layer 1: GitHub Pages** — the front door.

Static site at `hiveai.github.io` (or custom domain). No server. Contains:
- Landing page with one-click download
- Network dashboard (reads Hive blockchain for stats, epochs, leaderboard)
- Pair browser (browse submitted pairs, vote quality via Hive Keychain)
- Question submission (post coding questions on-chain — miners generate answers)
- Documentation

**Layer 2: GitHub Releases** — base model distribution.

The pruned base model (~12 GB) is split into 7 x 2 GB parts and uploaded as
GitHub Release assets. Free. No bandwidth limit. Global CDN. Full resume
support via HTTP Range requests. Always online — no dependency on any single
node. The `hiveai init` command downloads and reassembles automatically.

Why GitHub Releases over IPFS: public IPFS gateways are unreliable for 12 GB
files (frequent interruptions, 0.1-15 MB/s variable speed). GitHub CDN is
consistently fast and 100% uptime. Free. The model is open source — GitHub
is the natural home for open-source artifacts.

**Layer 3: HivePoA** — adapter distribution (decentralized).

Adapters (~300 MB each) live on HivePoA with PoA storage contracts. P2P CDN
via desktop agents. HBD micropayments incentivize pinning. As the network
grows, the base model migrates here too — more seeders = faster P2P than any
CDN. But GitHub Releases is the bootstrap until P2P density is sufficient.

---

## Onboarding — One Download, Zero Config

**Desktop app (recommended):**

```text
1. Download HiveAI installer from hiveai.github.io
2. Installer pulls base model from GitHub Releases (~12 GB, resume-capable)
3. App auto-fetches latest adapter from HivePoA (~300 MB, <1 min)
4. Working AI. No HuggingFace. No Ollama. No terminal.
```

**pip install (developers):**

```text
1. pip install hiveai
2. hiveai init       ← downloads base model from GitHub Releases (~12 GB)
3. hiveai run        ← fetches adapter from HivePoA, starts llama-server
```

**Web interface (no install):**

The GitHub Pages site lets anyone with Hive Keychain:
- Submit coding questions on-chain (miners pick them up and generate pairs)
- Browse and vote on training pairs
- View network stats: epoch history, adapter scores, contributor leaderboard
- No LLM needed — the social/coordination layer is fully browser-based

**Connect Hive account (optional):** Hive Keychain for on-chain submissions.
Only needed for DBC contribution. The AI works fully offline without it.

**Updates are tiny:** Only the adapter changes (~300 MB). The base model is a
one-time download. Flatten epochs download a new base in the background while
the old one keeps serving.

---

## What's Already Built

The entire local pipeline works:

- Mining (URL → crawl → chunk → triple → Golden Book)
- Quality scorer (deterministic, v5.2, 8 dimensions)
- Distillation (30 templates: Python, C++, explanation, Hive)
- Deduplication (tiered: exact/paraphrase/near)
- LoRA training (DoRA, r=32, monkey-patched MoE)
- Eval harness (125 challenges, 4 dimensions, execution-based)
- GGUF conversion + deployment (llama-server)
- Rollback system
- Knowledge gap detection (auto-learn loop)

---

## What We Build

7 components. 3 phases.

### Phase 1: Chain Protocol (CPU-only, buildable now)

| # | File | What it does |
|---|------|-------------|
| 1 | `hiveai/dbc/chain.py` | Hive interactions: encode pairs (gzip+base64), broadcast custom_json via beem, stream and filter incoming operations |
| 2 | `hiveai/dbc/hivepoa.py` | HivePoA client: create storage contracts, download adapters by CID, resume-capable |
| 3 | `hiveai/dbc/node.py` | The daemon: watch chain → verify new versions → download adapter → restart llama-server → post verification vote |

### Phase 2: Training Pipeline (requires GPU)

| # | File | What it does |
|---|------|-------------|
| 4 | `hiveai/dbc/trainer.py` | Epoch agent: claim epoch → replay chain for pairs → re-score → train → eval → publish to Hive + HivePoA |
| 5 | `scripts/train_incremental.py` | The training script itself: resume from checkpoint, locked hyperparameters, deterministic seed |
| 6 | `scripts/migrate_model.py` | Model migration: baseline new model → gap analysis → smart filter → re-distill → train migration adapter |

### Phase 3: Web Portal (static site, GitHub Pages)

| # | File | What it does |
|---|------|-------------|
| 7 | `site/` | Static site: landing page, download links (GitHub Releases), network dashboard, pair browser, question submission via Hive Keychain |

The site reads directly from the Hive blockchain (public API) — no backend.
Hive Keychain browser extension handles signing. All interactions are
`custom_json` operations: submit questions, vote on pairs, view stats.

**What HivePoA provides (we don't build):**
Storage contracts, Proof of Access, HBD payments, P2P CDN, Web of Trust,
desktop agent with bundled IPFS, reputation scoring. Six systems, zero code.

**What GitHub provides (we don't build):**
Release CDN (base model hosting), Pages hosting (static site), CI/CD
(automated release uploads). Free for open-source projects.

---

## Resilience: The Knowledge Ledger ("Megatron" Architecture)

**Design principle: The training data IS the brain. The adapter is just a lens.**

The most important architectural decision: knowledge is model-agnostic and
permanent. Adapters are model-specific and disposable. When you upgrade the
base model, you don't "port" the old adapter — you **re-derive** a new adapter
from the permanent knowledge layer. The adapter is a snap-on part, not the
chassis.

```
KNOWLEDGE LAYER (on-chain, permanent, MODEL-AGNOSTIC)
├── Instruction/response pairs (text — works with ANY model)
├── Quality scores (deterministic scorer — model-independent)
├── Topic/domain metadata
└── Grows forever, never obsolete

ADAPTER LAYER (derived, MODEL-SPECIFIC, ephemeral)
├── qwen3.5-35b-a3b/v3.0 → v3.1 → v3.2 → ... (current)
├── qwen4-70b/v5.0 → v5.1 → ... (future)
├── llama4-scout/v6.0 → v6.1 → ... (future)
└── Each base model has its own version branch

EVAL LAYER (model-agnostic, growing)
├── 500+ challenges (test the KNOWLEDGE, not the MODEL)
└── Same challenges work across all base models
```

### Model Migration: "Extract the Upgrades Only"

When a new base model arrives, the migration protocol runs 6 steps:

**Step 1 — Baseline the new model.** Run it (no adapter) through ALL eval
challenges. Get per-domain baseline scores:
```
python: 0.82 (strong — model already knows this)
cpp: 0.65 (decent)
hive: 0.15 (weak — Hive is niche, no model knows this)
system_design: 0.70
```

**Step 2 — Gap analysis.** Compare new baseline to current adapted scores:
```
python: 0.82 new vs 0.91 adapted → gap = 0.09 (small)
cpp: 0.65 new vs 0.78 adapted → gap = 0.13 (moderate)
hive: 0.15 new vs 0.85 adapted → gap = 0.70 (huge — adapter needed)
system_design: 0.70 new vs 0.83 adapted → gap = 0.13
```

**Step 3 — Smart filter.** For each on-chain pair, test if the new model
already handles it. Generate a response from the new base model (no adapter),
score it with the deterministic scorer.
- If `new_model_score >= 0.80` → **SKIP** (model already knows this)
- If `new_model_score < 0.80` → **KEEP** (adapter needs to teach this)
- Result: 5,000 total on-chain pairs → 1,200 needed (76% filtered out)

**Step 4 — Re-distill (optional).** For kept pairs, regenerate responses using
the better base model. Keep the original instruction (the question), generate a
new response (the answer), score both old and new, keep whichever is better.
The training data itself upgrades with each model generation.

**Step 5 — Train migration adapter.** Train LoRA on filtered pairs. Full LR
(2e-4) since this is a new genesis for this base model. Run eval. Publish.

**Step 6 — Announce migration.** Post migration epoch on-chain. Nodes running
the old model continue unchanged. Nodes wanting to upgrade download the new
adapter.

**On-chain migration epoch:**

```json
custom_json id: "hiveai"
{
  "type": "migration",
  "from_model": "qwen3.5-35b-a3b",
  "to_model": "qwen4-70b",
  "v": "5.0",
  "cid": "QmNewAdapter...",
  "baseline_eval": 0.72,
  "adapted_eval": 0.89,
  "pairs_total": 5000,
  "pairs_used": 1200,
  "pairs_skipped": 3800,
  "gap_report_cid": "QmGapReport...",
  "seed": 42,
  "script": "f1e2d3"
}
```

### Version Tree (replaces version chain)

The version chain becomes a tree — one branch per base model:

```
qwen3.5-35b-a3b (branch A):
  v3.0 → v3.1 → v3.2 → v3.3 → v4.0 (flatten) → v4.1

qwen4-70b (branch B, same on-chain knowledge):
  v5.0 (migration) → v5.1 → v5.2 → v6.0 (flatten)

llama4-scout (branch C):
  v7.0 (migration) → v7.1 → ...
```

All branches train from the SAME on-chain pair pool. The chain data has
permanent value regardless of which model is current. `base_model` is a new
optional field on version records — absent means the original model (backward
compatible). Nodes filter versions by their own `base_model` to find their
update chain.

### The Self-Upgrading Data Cycle

```
Generation 1 (Qwen3.5): adapter quality 0.85 avg
  ↓ train → generate pairs → on-chain

Generation 2 (Qwen4): better base model → better re-distilled responses
  ↓ quality: 0.90 avg (data itself improved)

Generation 3 (Qwen5): even better
  ↓ quality: 0.93 avg + 2 generations of accumulated knowledge
```

Each model generation doesn't just create a better adapter — it produces
better training data that makes the NEXT generation even better. The knowledge
ledger is a flywheel.

---

## Resilience: Overflow Sharding (Scalability)

**Problem:** Sequential training backs up permanently at scale (50K+ pairs/day).

**Solution:** Keep sequential training as default. Add overflow sharding that
activates ONLY when the queue exceeds 2,000 pending pairs.

```
Normal mode (< 2,000 pending):
  Single sequential queue. One adapter. Current design.

Overflow mode (≥ 2,000 pending):
  Split into domain shards:
  ├── core (cross-domain, always sequential)
  ├── python-specialist (parallel)
  ├── cpp-specialist (parallel)
  ├── hive-specialist (parallel)
  └── auto-created when domain > 200 pending pairs
```

Domain shards train independently on different GPUs. After training, shards
are **merged offline** into a single adapter before publishing.

### Why Merge, Not Stack

LoRA adapter stacking is mathematically additive. If two shards both modify
the same attention head projections (q/k/v/o — they always do), their weight
deltas interfere unpredictably at inference time. The `scale` parameter is a
blunt knob that doesn't know which dimensions conflict. Stacked adapter
behavior is an open research question.

**Merging is solved.** TIES-Merging (Yadav et al., 2023) resolves sign
conflicts between shards, trims small-magnitude weights, and produces a clean
combined adapter. The merge is deterministic — same inputs, same weights,
same output. Verifiable.

### Merge Protocol

```
1. Shards train independently:
   core-trainer  → core.gguf   (cross-domain pairs)
   python-trainer → python.gguf (pure Python pairs)
   cpp-trainer   → cpp.gguf    (pure C++ pairs)

2. Merge coordinator (any trainer) combines:
   merged.gguf = TIES_merge(core, python, cpp, weights)

   Merge weights derived from:
   - Pair count (more data = higher weight)
   - Eval delta (better improvement = higher weight)
   - Core shard minimum weight: 0.40 (backbone guarantee)

3. Publish ONE merged adapter (not multiple)
   Nodes see a single adapter — zero inference overhead
   No dependency on llama-server stacking API
```

### Cross-Domain Pair Assignment

A "Python Hive bot" pair touches both domains. Rule:

```python
def assign_shard(pair):
    primary = pair.topic.split("/")[0]
    domain_hits = count_domain_keywords(pair.instruction + pair.response)

    if len(domain_hits) >= 2:
        return "core"         # cross-domain → core shard
    if primary in active_shards:
        return primary        # pure domain → domain shard
    return "core"             # default → core
```

Core handles all cross-cutting concerns. Domain shards handle pure-domain
pairs. Clean separation, no ambiguity.

### Merge Epoch (on-chain)

```json
custom_json id: "hiveai"
{
  "type": "merge",
  "v": "3.6",
  "shards": [
    {"shard": "core", "epoch_v": "3.5a", "cid": "QmCore..."},
    {"shard": "python", "epoch_v": "3.5b", "cid": "QmPython..."},
    {"shard": "cpp", "epoch_v": "3.5c", "cid": "QmCpp..."}
  ],
  "merged_cid": "QmMerged...",
  "eval": 0.873,
  "merge_weights": {"core": 0.40, "python": 0.35, "cpp": 0.25},
  "seed": 42,
  "script": "d4e5f6"
}
```

Verifiers reproduce the exact merge from shard CIDs + weights. Deterministic.

On-chain: `"shard": "python"` added to epoch config (optional field). Absent =
full adapter (normal mode). Present = domain shard. Nodes auto-detect mode from
chain state. Shard epochs are consumed by a `merge` epoch — nodes update only
on merged adapters, never on individual shards.

At day-1 (100 users), this never activates. At 10K+ users, it activates
automatically. No configuration needed.

---

## Resilience: Trainer Incentives

**Problem:** Trainers spend GPU time + electricity for zero compensation.
Altruism doesn't scale.

**Solution:** Each completed epoch publishes a **Hive post** (not just
custom_json). The community upvotes it → trainer earns HBD/HP through Hive's
native reward system.

```
Epoch completes → auto-generate training report post:
  - Pairs trained, eval score, improvement delta
  - Per-domain breakdown
  - Before/after comparison
  - All claims independently verifiable

Beneficiaries: 90% trainer, 10% @hiveai community account
```

This uses existing Hive economics — no new token, no new system. `publisher.py`
already creates Hive post operations (currently set to 0 rewards — change to
real rewards for epoch posts). Even small rewards ($2-5 per post) cover
electricity costs. The @hiveai community account accumulates HP for future
operations.

---

## Resilience: Trust Decay + Pair Governance

**Problem:** Immutable chain means bad pairs can't be removed. Flatten epochs
amplify subtly poisoned data. Uniform age decay penalizes stable knowledge
(algorithms don't change) while under-penalizing volatile knowledge
(blockchain SDK APIs change every 6 months).

**Solution:** Can't delete from an immutable chain, but you can **weight** it.
Instead of binary include/exclude, pairs earn trust based on community signals
and domain-aware decay rates.

Every on-chain pair starts with `trust_weight = 1.0`. Three mechanisms adjust:

**1. Flag operation (immediate):**

```json
custom_json id: "hiveai"
{"type": "flag", "pair_tx": "abc123", "reason": "incorrect output"}
```

3+ flags from different trainers → `trust_weight = 0.0` (effectively removed
from training without chain mutation).

**2. Domain-aware age decay (gradual):**

Different knowledge domains decay at different rates. Algorithms and data
structures are nearly permanent. Blockchain SDK APIs become outdated quickly.

```python
DOMAIN_DECAY = {
    # domain: (grace_months, decay_per_month, floor)

    # Stable — barely decays
    "algorithms":       (24, 0.01, 0.30),
    "data_structures":  (24, 0.01, 0.30),
    "design_patterns":  (18, 0.01, 0.30),
    "testing":          (18, 0.02, 0.30),
    "systems":          (12, 0.02, 0.30),

    # Moderate — languages evolve slowly
    "python":           (12, 0.03, 0.30),
    "cpp":              (12, 0.02, 0.30),
    "javascript":       (12, 0.04, 0.30),
    "database":         (12, 0.03, 0.30),
    "web":              (12, 0.04, 0.30),
    "devops":           (12, 0.04, 0.30),
    "security":         (12, 0.03, 0.30),

    # Fast — blockchain APIs change frequently
    "hive_sdk":         (6,  0.06, 0.30),
    "hive_layer2":      (6,  0.06, 0.30),
    "hive_economics":   (9,  0.05, 0.30),
    "hive_architecture":(9,  0.04, 0.30),
    "hive_security":    (9,  0.05, 0.30),

    # Default for uncategorized
    "default":          (12, 0.03, 0.30),
}

def compute_trust_weight(pair, current_time):
    age_months = (current_time - pair.created_at).days / 30
    category = pair.topic.split("/")[0] if "/" in pair.topic else pair.topic
    grace, rate, floor = DOMAIN_DECAY.get(category, DOMAIN_DECAY["default"])

    if age_months <= grace:
        return 1.0  # no decay during grace period

    weight = max(floor, 1.0 - (age_months - grace) * rate)
    return weight
```

**Why domain-aware matters:**

| Domain | Grace | After 12 months | After 24 months |
|--------|-------|-----------------|-----------------|
| algorithms | 24mo | 1.00 (no decay) | 1.00 (just starting) |
| python | 12mo | 1.00 (just starting) | 0.64 |
| hive_sdk | 6mo | 0.64 | 0.30 (floor) |

A binary search pair stays relevant for years. A Hive Engine API pair
becomes unreliable after 6 months. The decay curve matches reality.

**3. Scorer version filter (automatic):**

When the scorer upgrades (v5.2 → v5.3), old scores may not reflect new
standards. The trainer re-scores during collection — pairs that drop below
`min_score` are excluded. The scorer IS the governance.

During training, `sample_weight = trust_weight * quality`. High-trust,
high-quality pairs dominate. Flagged pairs have weight 0 — effectively
removed. The chain is immutable but the interpretation is dynamic. Flatten
epochs use the same trust weights.

---

## Resilience: Eval Verification Protocol

**Problem:** The entire security model rests on eval determinism. But LLM
output is NOT deterministic across hardware — different GPUs, CUDA versions,
and quantization implementations produce different floating-point accumulation
orders. Even `temp=0, top_k=1` doesn't guarantee identical text across machines.

**Key insight:** The scorer IS deterministic. Same text in → same score out,
on every machine, every time. It's pure Python math (AST parsing, regex,
word counting). The non-deterministic part is the LLM generating the text.
So: **verify the scoring, not the generation.**

### Structural Verification Protocol

The trainer publishes their eval results with a new artifact: the raw LLM
outputs for all 125 challenges. Verifiers run three checks:

```
CHECK 1: SCORER INTEGRITY (weight = 0.50, deterministic)
  Download trainer's raw eval outputs (eval_outputs_cid)
  Re-run deterministic scorer on each output (NO LLM call needed)
  Per-challenge scores must match EXACTLY
  If mismatch → REJECT (trainer tampered with scores)
  Cost: ~10 seconds (just Python math)

CHECK 2: CODE EXECUTION (weight = 0.30, deterministic)
  Extract code blocks from trainer's outputs
  Re-run in sandbox, re-run test assertions
  Test pass/fail must match trainer's claims
  Same Python code → same execution result (bit-for-bit)
  Cost: ~2 minutes (sandbox execution)

CHECK 3: GENERATION SPOT-CHECK (weight = adaptive, non-deterministic)
  Generate OWN outputs for 25 random challenges (subset from epoch seed)
  Use STATISTICAL AGGREGATION (not per-challenge comparison):
    - Compute mean overall score across all 25 challenges
    - Compare mean to trainer's mean for the same 25 (within ±aggregate_tolerance)
    - Outlier gate: no single challenge delta > 3× aggregate_tolerance
    - Test pass agreement: ≥80% of challenges with test_code must agree pass/fail
  Catches adapter substitution without requiring exact text match
  Cost: ~8 minutes (25 LLM calls instead of 125)
```

**Why statistical aggregation instead of per-challenge tolerance:**

Per-challenge ±0.05 is fragile — if hardware variance on any ONE challenge
exceeds the tolerance, the entire check fails. With 25 challenges, even
moderate variance (±0.10 per challenge) would cause frequent false rejections.

Statistical aggregation exploits the Central Limit Theorem: even if individual
challenge variance is high (σ), the variance of the MEAN of 25 challenges
is σ/√25 = σ/5. So a per-challenge stdev of 0.10 becomes a mean stdev of
0.02 — tight enough for reliable verification. The outlier gate catches
catastrophic failures on individual challenges without being brittle.

**Adaptive Check 3 Weight (Confidence Tiers):**

The calibration script (`scripts/calibrate_eval.py`) measures actual hardware
variance and assigns a confidence tier:

```
HIGH_CONFIDENCE    (max_range ≤ 0.05):  Check 3 weight = 20%
  Per-challenge variance is within ±0.05. Standard protocol works.

MEDIUM_CONFIDENCE  (max_range ≤ 0.15):  Check 3 weight = 20%
  Per-challenge variance exceeds ±0.05 but aggregate mean is stable.
  Use statistical aggregation (mean ± aggregate_tolerance).

LOW_CONFIDENCE     (max_range ≤ 0.30):  Check 3 weight = 10%
  High per-challenge variance. Reduce Check 3 weight and switch to
  RELATIVE verification: adapter must score ≥ previous version's mean
  on the same 25 challenges, rather than matching trainer's claim.

UNRELIABLE         (max_range > 0.30):   Check 3 weight = 0%
  Extreme variance. Rely on Checks 1+2 (80→100% of total weight).
  Check 3 is logged but does not affect the verification score.
```

**Verification score formula:**

```python
def verify_epoch(trainer_outputs, trainer_scores, adapter, epoch_seed,
                 protocol_config):
    # Check 1: re-score trainer's outputs (deterministic)
    my_scores = [score_challenge(output) for output in trainer_outputs]
    scorer_match = all(abs(my - theirs) < 0.001
                       for my, theirs in zip(my_scores, trainer_scores))

    # Check 2: re-run code execution (deterministic)
    my_tests = [run_tests(output, challenge) for output, challenge
                in zip(trainer_outputs, challenges)]
    test_match = sum(my == theirs for my, theirs in zip(my_tests, trainer_tests))
    test_rate = test_match / len(challenges)

    # Check 3: spot-check generation (statistical, 25 challenges)
    spot_size = protocol_config.get("spot_check_size", 25)
    agg_tol = protocol_config.get("aggregate_tolerance", 0.03)
    check3_weight = protocol_config.get("check3_weight", 0.20)

    random.seed(epoch_seed)
    subset = random.sample(range(len(challenges)), spot_size)
    my_outputs = [generate(adapter, challenges[i]) for i in subset]
    my_spot = [score_challenge(my_outputs[j]) for j in range(spot_size)]
    trainer_spot = [trainer_scores[subset[j]] for j in range(spot_size)]

    my_mean = mean(my_spot)
    trainer_mean = mean(trainer_spot)

    # Statistical check: mean within aggregate tolerance
    mean_ok = abs(my_mean - trainer_mean) <= agg_tol
    # Outlier gate: no catastrophic per-challenge delta
    outlier_ok = all(abs(my_spot[j] - trainer_spot[j]) <= 3 * agg_tol
                     for j in range(spot_size))
    # Test agreement: ≥80% binary pass/fail match
    test_agree = (sum(1 for j in range(spot_size)
                      if my_tests_match(my_outputs[j], trainer_outputs[subset[j]]))
                  / spot_size) >= 0.80

    generation = 1.0 if (mean_ok and outlier_ok and test_agree) else 0.0

    # Adaptive weights (from calibration)
    w1 = 0.50 + (0.20 - check3_weight) * 0.6   # absorb unused Check 3 weight
    w2 = 0.30 + (0.20 - check3_weight) * 0.4
    w3 = check3_weight

    integrity = 1.0 if scorer_match else 0.0
    execution = test_rate

    final = w1 * integrity + w2 * execution + w3 * generation
    return final >= 0.85  # accept threshold
```

**On-chain additions:**

```json
custom_json id: "hiveai"
{
  "type": "version",
  "v": "3.7",
  "cid": "Qm...",
  "eval": 0.867,
  "eval_outputs_cid": "QmEvalOutputs..."
}
```

`eval_outputs_cid` points to a gzipped JSON file on HivePoA/IPFS containing
all 125 raw LLM responses (~250-600 KB compressed). Temporary — only needed
during the verification window. Can be unpinned after 3+ accept votes.

### Pre-Launch Calibration

**Script:** `scripts/calibrate_eval.py` — runs BEFORE DBC code is built.

The calibration protocol measures actual hardware variance empirically:

```
Phase 1: DETERMINISTIC (seed=42, temp=0, top_k=1)
  Run 25 challenges × 5 runs on the same machine.
  Measures: are outputs identical with deterministic settings?
  Expected: near-zero variance (validates llama-server determinism)

Phase 2: REALISTIC (temp=0.3, no seed)
  Run 25 challenges × 5 runs on the same machine.
  Measures: how much does score vary between non-deterministic runs?
  This is the ACTUAL variance Check 3 will face.

Phase 3: CROSS-MACHINE (run Phase 1+2 on a second GPU, then compare)
  Measures: how much does score vary ACROSS different hardware?
  This is the definitive answer for setting tolerance.
```

Results determine the confidence tier and on-chain protocol config:

```json
{"type": "protocol",
 "eval_tolerance": 0.05,
 "aggregate_tolerance": 0.03,
 "spot_check_size": 25,
 "check3_weight": 0.20,
 "confidence_tier": "MEDIUM_CONFIDENCE",
 "calibration_machines": 2,
 "calibration_runs": 5,
 "min_verification_score": 0.85}
```

**Graceful degradation:** If cross-machine variance is extreme, the protocol
automatically reduces Check 3 weight (or disables it entirely) rather than
producing false rejections. The system ADAPTS to empirical reality instead
of assuming a tolerance. Checks 1+2 (deterministic, 80% baseline weight)
always work regardless of hardware variance.

---

## Resilience: Cumulative Pair Index

**Problem:** At 1M on-chain pairs, chain replay takes 30+ hours.

**Solution:** Each epoch includes an optional `index_cid` — a pre-built
snapshot of all on-chain pairs up to the previous epoch.

```json
{
  "type": "epoch",
  "v": "3.5",
  "index_cid": "QmPairIndex...",
  "blocks": [82100000, 82200000],
  ...
}
```

The index file (hosted on IPFS/HivePoA, ~10-50 MB):

```json
{
  "format": "hiveai_pair_index_v1",
  "block_range": [0, 82100000],
  "total_pairs": 15432,
  "flagged_txs": ["abc123", "def456"],
  "pairs": [
    {"tx": "a1b2", "block": 82000100, "score": 0.87, "lang": "python",
     "topic": "concurrency", "size_bytes": 5120}
  ],
  "checksum": "sha256_of_sorted_tx_ids"
}
```

Trainers download the index, replay ONLY the new block range (typically a few
hours of blocks), merge new pairs, publish an updated `index_cid` with their
epoch. Full chain replay remains the deterministic fallback — the index is a
cache, not truth. If a trainer lies about the index, their adapter differs from
what a verifier gets via full replay, and the eval check catches it.

| On-chain pairs | Index size | Replay (with index) | Replay (without) |
|----------------|-----------|-------------------|-----------------|
| 10K | ~4 MB | seconds | ~20 min |
| 100K | ~40 MB | seconds | ~3 hours |
| 1M | ~400 MB | seconds | ~30 hours |

---

## Resilience: Self-Improving Intelligence Loop

**Problem:** Without active development, the system stagnates. Worse: naive
auto-generation amplifies the model's own blind spots — if the model is weak
at security because of a fundamental misunderstanding, auto-generating more
security pairs with the same blind model produces pairs that share that
misunderstanding. The scorer catches low-quality output but not
"confident-and-syntactically-valid-but-wrong" output.

**Solution:** Connect the eval harness to the distiller in a closed loop,
with two new safety stages that prevent diversity collapse.

```
              ┌──────────────────────────────────┐
              │         EVAL HARNESS              │
              │  Per-domain scores after epoch:   │
              │    python: 0.91 ✓                 │
              │    cpp: 0.65 ✗ (weak)             │
              │    hive: 0.82 ✓                   │
              │    security: 0.45 ✗ (critical)    │
              └──────────┬───────────────────────┘
                         │ identify gaps
                         ▼
              ┌──────────────────────────────────┐
              │       GAP MINING AGENT            │
              │  distill_batch() with domain-     │
              │  specific templates, targeting    │
              │  weak domains. More pairs for     │
              │  weaker domains.                  │
              │                                   │
              │  security: generate 50 pairs      │
              │  cpp: generate 30 pairs           │
              └──────────┬───────────────────────┘
                         │ 6-gate filter (existing)
                         ▼
              ┌──────────────────────────────────┐
              │    ANCHOR VALIDATION (NEW)        │
              │  Compare against hand-verified    │
              │  reference answers per domain.    │
              │  Catches "confident but wrong."   │
              └──────────┬───────────────────────┘
                         │ passes anchor check
                         ▼
              ┌──────────────────────────────────┐
              │    STAGING BUFFER (NEW)           │
              │  Pairs sit visible for 1 epoch    │
              │  cycle. Other miners can flag.    │
              │  Trainer can review before use.   │
              └──────────┬───────────────────────┘
                         │ unflagged after staging
                         ▼
              ┌──────────────────────────────────┐
              │         ON-CHAIN                  │
              │  New pairs accumulate             │
              │  Targeted at weak domains         │
              └──────────┬───────────────────────┘
                         │ next epoch trains
                         ▼
              ┌──────────────────────────────────┐
              │       NEXT EPOCH TRAINING         │
              │  security: 0.45 → 0.62           │
              │  cpp: 0.65 → 0.73                │
              └──────────┬───────────────────────┘
                         │ eval again
                         ▼
                    (cycle repeats)
```

### Anchor Validation — Catching "Confident But Wrong"

A small set of hand-verified **anchor pairs** per domain (10-20 each). Each
anchor defines `must_contain` and `must_not_contain` patterns for responses
to similar questions. Anchors are the ground truth that prevents drift.

```python
ANCHOR_PAIRS = {
    "security": [
        {
            "instruction": "How do you prevent SQL injection in Python?",
            "must_contain": ["parameterized", "placeholder"],
            "must_not_contain": ["f-string", ".format(", "% ("],
        },
    ],
    "hive_sdk": [
        {
            "instruction": "How do you broadcast a custom_json on Hive?",
            "must_contain": ["custom_json", "required_posting_auths"],
            "must_not_contain": ["active_key"],  # custom_json uses posting
        },
    ],
}

def validate_against_anchors(pair, domain):
    anchors = ANCHOR_PAIRS.get(domain, [])
    for anchor in anchors:
        sim = cosine_similarity(embed(pair.instruction), embed(anchor["instruction"]))
        if sim > 0.80:  # similar question
            for required in anchor["must_contain"]:
                if required.lower() not in pair.response.lower():
                    return False  # missing critical concept
            for forbidden in anchor["must_not_contain"]:
                if forbidden.lower() in pair.response.lower():
                    return False  # contains known-bad pattern
    return True
```

**Why anchors work against blind spots:** The model doesn't know what it
doesn't know. But anchors are human-curated facts: "SQL injection prevention
MUST mention parameterized queries." If the model generates a security pair
that recommends f-strings for SQL, the anchor catches it — even though the
scorer would score the code highly (syntactically valid, runs, has tests).

Anchor sets are versioned, community-contributed via PR, and small (~200
total across all domains). They're test fixtures, not training data. Growing
the anchor set is the single most impactful community contribution.

### Staging Buffer — Temporal Safety Net

Auto-mined pairs don't go directly on-chain. They enter a visible **staging
queue** for one epoch cycle (typically 4-8 hours).

```
During staging:
  - Staged pairs are visible to all DBC nodes (broadcast as custom_json)
  - Other miners can flag: {"type": "stage_flag", "pair_tx": "abc...", "reason": "..."}
  - 2+ stage flags from different accounts → pair rejected (never goes on-chain)
  - Trainer can pre-filter during collection (skip staged pairs still in window)
  - Unflagged pairs auto-promote to on-chain after the staging window expires
```

On-chain format (additive):

```json
custom_json id: "hiveai"
{
  "type": "pair",
  "data": "...",
  "score": 0.87,
  "lang": "python",
  "topic": "security",
  "scorer": "v5.2",
  "staged_block": 82000100,
  "anchor_validated": true
}
```

`staged_block` is optional (absent for legacy pairs). `anchor_validated`
tells trainers this pair was checked against domain anchors. Trainers can
prioritize anchor-validated pairs during collection (higher confidence).

### Quality Ratchet (unchanged)

Each model generation produces better training data naturally. Better model =
better responses = higher scorer quality. v3.0 adapter generates 0.85 avg
quality pairs. v3.4 adapter generates 0.88. After migration to a better base
model, 0.91. The training data itself improves with no human intervention.

### Eval Challenge Growth (unchanged)

The challenge pool must grow faster than any gaming strategy. Community
contributes challenges via PR. Target: 500 by v4.0, 1000 by v5.0.
Auto-generate challenge candidates from high-quality training pairs (extract
the instruction, add test_code, promote to eval challenge).

---

## Resilience: Protocol Hardening

Nine operational gaps identified through adversarial analysis. Each has a
concrete solution that integrates with existing infrastructure.

### 1. Epoch Timeout — Preventing Pipeline Stalls

**Problem:** A trainer claims an epoch then crashes/disappears. The epoch
claim is on-chain and immutable. Other trainers can't claim because the chain
shows an active epoch. The entire training pipeline freezes.

**Solution:** Derivable timeout. No new on-chain operation needed.

```python
EPOCH_TIMEOUT_HOURS = 24  # configurable via "protocol" operation

def is_epoch_stalled(epoch_claim, current_block):
    claim_time = get_block_time(epoch_claim["block_num"])
    elapsed = current_block_time - claim_time

    # Check if a matching version was published
    version_exists = any(
        v["v"] == epoch_claim["v"]
        for v in get_chain_versions_since(epoch_claim["block_num"])
    )

    if version_exists:
        return False  # epoch completed normally

    return elapsed > timedelta(hours=EPOCH_TIMEOUT_HOURS)

def can_claim_epoch(account, chain_state):
    latest_epoch = get_latest_epoch_claim(chain_state)
    if latest_epoch is None:
        return True  # no active epoch

    # Normal case: previous epoch completed
    if epoch_has_version(latest_epoch, chain_state):
        return not is_cooldown_active(account, chain_state)

    # Stalled case: previous epoch timed out
    if is_epoch_stalled(latest_epoch, chain_state):
        return True  # anyone can re-claim (no cooldown for recovery)

    return False  # epoch still active, wait
```

**Key properties:**
- Timeout is **derivable** — every node computes it from block timestamps,
  no governance vote needed
- The stalled epoch's config stays on-chain but is superseded by the re-claim
- The re-claiming trainer uses the SAME block range (they inherit the stalled
  epoch's unclaimed pairs, not just pairs since the stall)
- No cooldown for recovery claims — the system's liveness takes priority
- Default 24h is generous (normal epochs complete in 2-6h). Adjustable via
  `type: "protocol"` operation if needed

### 2. Verification Sybil — Weighted Vote Consensus

**Problem:** Non-GPU nodes accept an adapter after 3+ `accept` votes. Anyone
can post `type: "verify"` — no proof of GPU, no stake requirement. Three Sybil
accounts posting fake accepts → non-GPU nodes install a poisoned adapter.

**Solution:** HP-weighted consensus with WoT fast-track.

```python
MIN_HP_TO_VERIFY = 100           # minimum HP to post a valid verify vote
CONSENSUS_HP_THRESHOLD = 5000    # total HP needed for non-GPU acceptance
CONSENSUS_MIN_ACCOUNTS = 3       # minimum unique voters
WOT_FAST_TRACK = 3               # 3 WoT-vouched accepts = instant consensus

def evaluate_consensus(votes, wot_accounts):
    """Determine if enough valid accepts exist for non-GPU nodes."""
    valid_accepts = []
    for vote in votes:
        if not vote["accept"]:
            continue
        voter_hp = get_account_hp(vote["author"])
        if voter_hp < MIN_HP_TO_VERIFY:
            continue  # ignore low-HP accounts (Sybil resistance)
        valid_accepts.append({
            "author": vote["author"],
            "hp": voter_hp,
            "is_wot": vote["author"] in wot_accounts,
        })

    # Fast track: 3+ WoT-vouched accepts = trusted immediately
    wot_accepts = [v for v in valid_accepts if v["is_wot"]]
    if len(wot_accepts) >= WOT_FAST_TRACK:
        return True

    # Standard path: HP-weighted consensus
    total_hp = sum(v["hp"] for v in valid_accepts)
    unique_accounts = len(set(v["author"] for v in valid_accepts))

    return (total_hp >= CONSENSUS_HP_THRESHOLD and
            unique_accounts >= CONSENSUS_MIN_ACCOUNTS)
```

**Why HP-weighted works:**
- Creating 3 Sybil accounts with 100+ HP each requires ~$300+ in liquid HIVE
  (at current prices) — economically irrational for attacking a free adapter
- WoT-vouched trainers provide fast consensus (they already proved trustworthiness)
- HP threshold is adjustable via `type: "protocol"` operation
- Regular Hive users with legitimate stakes naturally contribute to consensus
- Reject votes from WoT-vouched accounts trigger immediate investigation:
  non-GPU nodes should NOT accept if ANY WoT account rejects

**On-chain verify format (unchanged):**

```json
{"type": "verify", "v": "3.1", "eval": 0.865, "accept": true}
```

The HP and WoT filtering happens client-side. The on-chain format doesn't
change — the INTERPRETATION is what changes. Nodes read the voter's HP from
the blockchain state (already public) and check WoT status from the witness
vouch list.

### 3. Epoch Claim Tiebreaker

**Problem:** Two trainers submit `type: "epoch"` in the same 3-second Hive
block. Both think they claimed first. Both start training. One wastes hours.

**Solution:** Deterministic tiebreaker from Hive's transaction ordering.

```python
def get_winning_epoch_claim(block):
    """Within a single block, first transaction wins."""
    epoch_claims = []
    for tx_index, tx in enumerate(block["transactions"]):
        for op in tx["operations"]:
            if is_hiveai_epoch_claim(op):
                epoch_claims.append({
                    "tx_index": tx_index,
                    "author": op["required_posting_auths"][0],
                    "config": op["json"],
                })

    if not epoch_claims:
        return None

    # Hive blocks have deterministic transaction ordering
    # All nodes see the same tx_index for the same transaction
    return min(epoch_claims, key=lambda c: c["tx_index"])
```

**Why this is deterministic:**
- Hive block producers (witnesses) order transactions within a block
- This ordering is part of the signed block — identical on all nodes
- `tx_index` is a position integer, not a timestamp — no ambiguity
- Losing claimants detect the conflict when they see the block and abort
  before wasting GPU time (epoch claim → observe block → if not winner,
  cancel immediately)

**Conflict notification:** When a node detects it lost a tiebreak, it logs a
warning and enters standby for the next epoch. No on-chain operation needed.

### 4. Scorer Gaming — Anchor Coverage Gate

**Problem:** The scorer is open-source and deterministic. A sophisticated
attacker can reverse-engineer it to craft pairs that score highly (correct
syntax, many code blocks, keyword-dense) but contain subtly wrong information.
Anchors catch this for covered domains — but new/niche domains start with
zero anchors.

**Solution:** Anchor coverage minimum for auto-mined pairs.

```python
MIN_ANCHORS_FOR_AUTO_MINE = 3  # domain needs ≥3 anchors for auto-mining

def can_auto_mine_domain(domain, anchor_stats):
    """Gate auto-gap-mining behind anchor coverage."""
    domain_anchors = anchor_stats.get("by_domain", {}).get(domain, 0)

    if domain_anchors >= MIN_ANCHORS_FOR_AUTO_MINE:
        return "allowed"      # full auto-mining

    if domain_anchors >= 1:
        return "extended_staging"  # auto-mine but 24h staging (not 4-8h)

    return "blocked"          # no auto-mining until anchors exist

# Human-generated pairs (from real user chat) are ALWAYS allowed
# This gate only affects the self-improvement loop's auto-gap-mining
```

**Why this works:**
- Auto-mining is the amplification vector — it generates many pairs fast
  from a potentially biased model. Without anchors, there's no ground truth
  to catch "confident but wrong" outputs.
- Human-generated pairs come from real user interactions — the user
  implicitly validates by using the response. Much lower amplification risk.
- This creates healthy pressure to grow the anchor set: want auto-mining
  for C++? Contribute 3+ C++ anchors first.
- The 1-2 anchor "extended staging" tier gives partial access while
  signaling "we need more anchors here."

**Current coverage (122 anchors, 16 domains):** Every eval domain already
has 5+ anchors. This gate is already satisfied for all current domains.
It protects against future domains added without anchor coverage.

### 5. Privacy — Pre-Submission Content Scanner

**Problem:** On-chain pairs are public and permanent. Even with opt-in, a
user might accidentally submit a pair containing API keys, passwords,
private keys, or personal data. The flag system zeros trust weight but the
raw data remains readable. This is a GDPR/legal risk.

**Solution:** Regex-based content scan runs locally before any broadcast.

```python
import re

SECRET_PATTERNS = [
    # API keys
    (r'(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}', "AWS access key"),
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI/Stripe secret key"),
    (r'ghp_[a-zA-Z0-9]{36}', "GitHub personal access token"),
    (r'xox[bpoas]-[0-9a-zA-Z-]+', "Slack token"),

    # Private keys / mnemonics
    (r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----', "Private key (PEM)"),
    (r'(?:^|\s)5[HJK][1-9A-HJ-NP-Za-km-z]{49}', "Hive/WIF private key"),
    (r'\b(?:[a-z]+ ){11,23}[a-z]+\b', "Possible mnemonic phrase (12-24 words)"),

    # Passwords / secrets in code
    (r'(?:password|passwd|secret|api_key)\s*[=:]\s*["\'][^"\']{8,}', "Hardcoded secret"),

    # PII
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', "Email address"),
    (r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b', "Possible SSN"),

    # File paths with usernames
    (r'(?:C:\\Users\\|/home/|/Users/)[a-zA-Z0-9._-]+', "Local file path with username"),
]

def scan_for_secrets(text: str) -> list[dict]:
    """Scan text for potential secrets/PII. Returns list of findings."""
    findings = []
    for pattern, description in SECRET_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            findings.append({
                "type": description,
                "position": match.start(),
                "snippet": text[max(0, match.start()-10):match.end()+10],
            })
    return findings

def pre_submission_check(pair: dict) -> tuple[bool, list]:
    """Gate: scan pair content before on-chain submission."""
    text = pair.get("instruction", "") + " " + pair.get("response", "")
    findings = scan_for_secrets(text)

    if findings:
        # BLOCK submission, warn user
        return False, findings
    return True, []
```

**UI integration:** When a pair is blocked:
```
⚠ Pair blocked from on-chain submission:
  Found: Hardcoded secret at position 245
  Found: Local file path with username at position 1023

  Submitted pairs are PUBLIC and PERMANENT on the Hive blockchain.
  Remove sensitive content and retry, or disable DBC for this pair.
```

**The mnemonic pattern** has intentional false positives (12+ lowercase words
in a row). Better to over-block than to leak a seed phrase. The user can
override with explicit confirmation for non-sensitive content.

### 6. Resource Credit Management

**Problem:** Hive Resource Credits regenerate over 5 days. At high mining
rates, a low-HP account exhausts RC and can't broadcast.

**Solution:** RC budget tracking with auto-throttle.

```python
RC_FLOOR_PERCENT = 20    # pause mining below 20% RC
RC_RESUME_PERCENT = 50   # resume mining above 50% RC
RC_PER_CUSTOM_JSON = 1.5e9  # approximate RC cost per custom_json

def estimate_daily_capacity(account_hp: float) -> int:
    """Estimate pairs/day based on HP."""
    max_rc = account_hp * 1e10  # approximate RC from HP
    daily_regeneration = max_rc * 0.20  # 20% regenerates per day
    return int(daily_regeneration / RC_PER_CUSTOM_JSON)

def should_submit(current_rc_percent: float, submission_paused: bool) -> bool:
    """Hysteresis-based throttle to prevent RC exhaustion."""
    if submission_paused:
        return current_rc_percent >= RC_RESUME_PERCENT
    return current_rc_percent >= RC_FLOOR_PERCENT

# Recommended HP for mining rates:
#   10 pairs/day  →  ~50 HP
#   50 pairs/day  →  ~250 HP
#  100 pairs/day  →  ~500 HP
```

**When throttled:** Pairs queue locally in the normal DB. When RC recovers,
the queue drains automatically in priority order (highest quality first).
No pairs are lost — just delayed.

**Dashboard integration:** Show RC status, estimated daily capacity, and
queue depth on the DBC status panel.

### 7. Eval Challenge Set Pinning

**Problem:** The challenge pool grows over time (125 → 500 → 1000). Two
verifiers with different challenge set versions compute different subsets
from the same epoch seed, producing incomparable results.

**Solution:** Pin the challenge set in the epoch config.

```json
custom_json id: "hiveai"
{
  "type": "epoch",
  "v": "3.1",
  "blocks": [82000000, 82100000],
  "seed": 31,
  "script": "a1b2c3",
  "eval_set": "d4e5f6",
  ...
}
```

`eval_set` is the SHA-256 hash of the sorted, concatenated challenge file
contents (or the CID of the challenge directory on IPFS). Every node
verifying this epoch MUST use the exact challenge set matching this hash.

```python
def verify_challenge_set(challenges_dir, expected_hash):
    """Verify local challenge set matches epoch's pinned version."""
    import hashlib
    h = hashlib.sha256()
    for path in sorted(Path(challenges_dir).glob("*.json")):
        h.update(path.read_bytes())
    actual = h.hexdigest()[:6]

    if actual != expected_hash:
        # Download the correct challenge set from IPFS/GitHub
        download_challenge_set(expected_hash)
    return actual == expected_hash
```

**Transition protocol:** When the challenge pool grows (e.g., 125 → 200),
the community publishes a `type: "protocol"` operation with the new
challenge set hash. Epochs after that block use the new set. Epochs before
it use the old one. Clean boundary, no ambiguity.

### 8. Chain Library Resilience

**Problem:** The chain protocol depends on `beem` (Python Hive library),
maintained by one person. If beem becomes unmaintained or breaks with a
Hive hard fork, the DBC protocol is blocked.

**Solution:** Abstraction layer with fallback.

The DBC chain operations are simple:
1. Broadcast `custom_json` (posting authority)
2. Stream blocks and filter operations
3. Read account data (HP, RC)

```python
# hiveai/dbc/chain.py — abstract interface
class ChainBackend:
    def broadcast_custom_json(self, id, json_data, posting_auths): ...
    def stream_blocks(self, start_block): ...
    def get_account(self, name): ...

class BeemBackend(ChainBackend):
    """Primary: beem library."""
    ...

class LighthiveBackend(ChainBackend):
    """Fallback: lighthive (minimal, HTTP-based)."""
    ...

class DirectRPCBackend(ChainBackend):
    """Emergency: raw HTTP JSON-RPC to any Hive API node."""
    ...
```

**All three backends exist in the codebase.** The node tries beem first,
falls back to lighthive, then to direct RPC. The direct RPC backend is
~100 lines of `requests.post()` calls — no external dependency beyond
Python's standard library + requests.

**Practical note:** beem is stable and actively maintained as of 2026.
This is insurance, not urgency. Build `BeemBackend` first, add fallbacks
when building Phase 1.

### 9. Cold Start Bootstrap — Chain Seeding

**Problem:** DBC needs pairs on-chain before the first epoch. Organic
mining from 5 users on day 1 produces a trickle. The flywheel needs a push.

**Solution:** Seed the chain from the existing vetted local DB.

```
Phase 0: CHAIN SEEDING (before DBC launch)

1. Select top 200 pairs from local DB (quality >= 0.85, diverse topics)
   Source: 2,385 existing pairs in v3.jsonl, already scored and deduplicated

2. Post to chain as type: "pair" from the genesis trainer account
   Rate: ~50/day (stay well within RC budget)
   Timeline: 4 days to seed 200 pairs

3. Post genesis epoch config:
   {"type": "epoch", "v": "3.0", "blocks": [0, genesis_block], "seed": 42,
    "script": "genesis", "note": "genesis_seed"}

4. Genesis version announcement (adapter already trained locally):
   {"type": "version", "v": "3.0", "cid": "QmGenesisAdapter...", "eval": 0.853}

5. DBC is now live. v3.1 epoch can be claimed by any vouched trainer.
   They'll collect the 200 seeded pairs + any new organic mining.
```

**Why 200 pairs:**
- Enough for a meaningful incremental epoch (~1.5 hours training)
- Small enough to seed in 4 days without RC exhaustion
- Diverse enough to cover major domains (Python, C++, Hive, algorithms, security)
- All pre-vetted — these are the same pairs that produced the v1 adapter
  with 0.853 eval score

**Ongoing bootstrap (first month):**
- Genesis trainer runs auto-mining aggressively (distill_batch on all gap domains)
- Target: 500+ on-chain pairs within 2 weeks
- First community epoch (v3.1) should have 200-300 new pairs to train on

---

## On-Chain Format Summary

All formats from v3.4 remain unchanged. New additions (all optional/additive):

| Operation | New Fields | Purpose |
|-----------|-----------|---------|
| `type: "version"` | `base_model`, `eval_outputs_cid` | Multi-model tree + structural verification |
| `type: "epoch"` | `shard` (optional) | Domain sharding overflow |
| `type: "epoch"` | `index_cid` (optional) | Cumulative pair index |
| `type: "pair"` | `data_cid` (alt to `data`) | Large pair overflow to HivePoA |
| `type: "pair"` | `staged_block`, `anchor_validated` | Staging buffer + anchor verification |
| `type: "migration"` | (new operation) | Model migration metadata |
| `type: "merge"` | (new operation) | Shard merge recipe + weights |
| `type: "flag"` | (new operation) | Pair governance |
| `type: "stage_flag"` | (new operation) | Pre-chain staging flags |
| `type: "protocol"` | (new operation) | Eval tolerance + verification config |
| `type: "epoch"` | `eval_set` (optional) | Challenge set version hash |

Old nodes that don't understand new fields simply ignore them.

---

## Resolved Questions

1. **Epoch threshold:** Auto-scaling. Trainer claims all unclaimed pairs since
   last epoch. No fixed threshold. Low traffic → small fast epochs. High traffic
   → large epochs. Self-regulating.

2. **Trainer selection:** First-come-first-served with cooldown. Trainer posts
   `type: "epoch"` to claim. Cooldown prevents same trainer doing consecutive
   epochs (derivable from chain — just check if their last epoch is the most
   recent one). No round-robin state to maintain.

3. **Multi-language adapters:** One combined adapter. Training data already mixes
   Python, C++, JavaScript, Hive SDK. Separate adapters per language would need
   coordination, stacking logic (`--lora-scaled`), and versioning for each — all
   complexity for marginal gain. The model handles multilingual naturally.

4. **Contract funding:** Trainer pays. ~$4 HBD/year per adapter is trivial
   relative to the GPU time already invested. No funding pool, no proportional
   splits, no governance. One entity, one payment.

5. **Emergency rollback:** Not needed. Nodes never auto-install a version that
   fails eval. GPU nodes verify before swapping. Non-GPU nodes wait for 3+
   consensus votes. A bad adapter simply isn't adopted — no rollback because
   nothing was rolled forward. The "emergency" is already handled by the normal
   update path.

6. **Stalled trainer:** 24-hour epoch timeout (derivable from block timestamps).
   If no version published within 24h of epoch claim, epoch is abandoned and
   any trainer can re-claim. No governance vote needed.

7. **Verification Sybil:** HP-weighted consensus (100 HP minimum to vote,
   5000 HP total for acceptance) + WoT fast-track (3 vouched accepts = instant).
   Makes Sybil attacks economically irrational.

8. **Epoch claim conflicts:** Deterministic tiebreaker — lowest transaction
   index within a Hive block wins. All nodes see the same ordering.

9. **Privacy of on-chain pairs:** Pre-submission content scanner blocks API keys,
   private keys, passwords, PII, and local file paths. Runs locally before
   broadcast. Override with explicit confirmation for false positives.

---

## Complexity Scorecard

| Metric | v1 | v2 | v3.7 (this) |
|--------|----|----|-------------|
| Roles | 4 | 3 | **2** |
| Components to build | 13 | 8 | **7** (+migrate_model.py) |
| On-chain payload for epoch | kilobytes (pair list) | kilobytes | **~200 bytes** (block range) |
| Governance decisions | 3+ | 1 | **0** (flatten + sharding + timeout automatic) |
| External dependencies | 3 | 1 | **2** (HivePoA + GitHub), fallback chain libs |
| Redundant GPU work | 100% | 0% | **0%** |
| User setup steps | 5+ | 3 | **1** (download → run) |
| External accounts needed | HuggingFace + Hive | HuggingFace + Hive | **0** (Hive optional) |
| Pre-chain quality gates | 0 | 1 | **6** (quality + exec + dedup x2 + coverage + secrets scan) |
| On-chain data redundancy | uncontrolled | filtered | **near-zero** (6-gate system) |
| Eval gaming protection | none | none | **rotating subset from 500+ pool** |
| Eval verification | full re-run | full re-run | **structural (80% deterministic + adaptive spot-check)** |
| Eval calibration | none | none | **empirical 3-phase protocol + confidence tiers** |
| Eval challenge pinning | none | none | **eval_set hash in epoch config** |
| Model lock-in | total | total | **zero** (Knowledge Ledger — any base model) |
| Poison resistance | none | none | **domain-aware trust decay + flagging + re-scoring** |
| Trainer incentives | none | none | **Hive post rewards** |
| Scalability ceiling | 1 trainer | 1 trainer | **overflow sharding + TIES merge** |
| Chain replay at 1M pairs | 30h | 30h | **seconds** (cumulative pair index) |
| Large pair support | drop | drop | **CID overflow to HivePoA** |
| Self-improvement | manual | manual | **auto-gap mining + anchor validation + staging** |
| Pipeline liveness | no protection | no protection | **24h epoch timeout + re-claim** |
| Verification Sybil | unprotected | unprotected | **HP-weighted + WoT fast-track** |
| Epoch conflicts | undefined | undefined | **deterministic tx_index tiebreaker** |
| Privacy protection | none | none | **pre-submission secrets scanner** |
| RC management | none | none | **auto-throttle + queue + budget calc** |
| Chain library | single dep | single dep | **abstraction layer + 3 backends** |
| Cold start | manual | manual | **200-pair chain seeding from vetted DB** |

---

## References

| Finding | Source |
|---------|--------|
| LoRA resists catastrophic forgetting vs full FT | "LoRA Learns Less and Forgets Less" (TMLR 2024) |
| 1/5th LR for incremental training | Lightning AI experiments |
| 20% data replay is the best anti-forgetting technique | Multiple sources |
| Hive custom_json: 8,192 bytes, free (RC only) | Hive developer docs |
| gzip+base64 fits 10 KB in 5.3 KB | hive-file-chunker project |
| temp=0 + top_k=1 + seed gives reproducible LLM output | LLM eval reproducibility research |
| CLT: mean of n samples has stdev σ/√n | Central Limit Theorem — variance reduction for aggregate scoring |
| TIES-Merging: Trim + Elect Sign + Disjoint Merge | Yadav et al., 2023 — deterministic adapter merging |
| HivePoA: storage contracts + PoA + WoT + P2P CDN | github.com/Dhenz14/HivePoA |
| beem blockchain streaming | beem.readthedocs.io |

---

*Living document. Update as decisions are made and components are built.*
