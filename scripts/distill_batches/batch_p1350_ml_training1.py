"""ML training optimization pairs: LoRA strategies, data curation, loss masking, eval methodology."""
PAIRS = [
    # ===================== LoRA/PEFT TRAINING STRATEGIES (5 pairs) =====================

    (
        "ml_train1_01",
        r'''I'm fine-tuning a 14B parameter model with LoRA. Should I train everything in one go, or is there a better approach? I'm seeing the model lose its general capabilities after training on my domain data.''',
        r'''<think>
The user is experiencing catastrophic forgetting during LoRA fine-tuning. This is a classic problem. The two-stage training approach from the LLM4SVG paper is directly applicable here: Stage 1 does format alignment at a low learning rate (1 epoch, 1e-5), and Stage 2 does knowledge training at a higher rate (2 epochs, 2e-5). This prevents the model from abruptly shifting its weight distribution.

I should explain the two-stage strategy, give concrete hyperparameters, and show how to implement it with HuggingFace Trainer.
</think>

## Two-Stage LoRA Training to Prevent Catastrophic Forgetting

The problem you're hitting is well-known: a single training run at one learning rate forces the model to simultaneously learn output formatting AND domain knowledge, which destabilizes the base model's general capabilities. The solution is a **two-stage training strategy**.

### Stage 1: Format Alignment (Gentle)

- **Purpose**: Teach the model your output format/style without aggressive weight updates
- **Config**: 1 epoch, low LR (1e-5), high warmup ratio (0.1)
- **Data**: Your full dataset — the model sees the format but doesn't deeply memorize content

### Stage 2: Knowledge Training (Focused)

- **Purpose**: Train actual domain knowledge with the format already locked in
- **Config**: 2 epochs, higher LR (2e-5), standard warmup (0.05)
- **Data**: Same dataset, but the model now focuses on content since format is stable

### Implementation

```python
from transformers import TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model

def create_lora_model(base_model):
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.1,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_rslora=True,
        task_type="CAUSAL_LM",
    )
    return get_peft_model(base_model, lora_config)

# Stage 1: Format alignment
stage1_args = TrainingArguments(
    output_dir="./checkpoints/stage1",
    num_train_epochs=1,
    learning_rate=1e-5,
    warmup_ratio=0.1,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    bf16=True,
    lr_scheduler_type="cosine",
    save_strategy="epoch",
    logging_steps=10,
)

trainer_s1 = Trainer(
    model=model,
    args=stage1_args,
    train_dataset=dataset,
    data_collator=collator,
)
trainer_s1.train()

# Stage 2: Knowledge training — resume from stage 1 checkpoint
stage2_args = TrainingArguments(
    output_dir="./checkpoints/stage2",
    num_train_epochs=2,
    learning_rate=2e-5,       # Higher LR — format is stable
    warmup_ratio=0.05,        # Less warmup needed
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    bf16=True,
    lr_scheduler_type="cosine",
    save_strategy="epoch",
    logging_steps=10,
)

trainer_s2 = Trainer(
    model=model,              # Same model — LoRA weights carry over
    args=stage2_args,
    train_dataset=dataset,
    data_collator=collator,
)
trainer_s2.train()
```

### Why This Works

In Stage 1, the low learning rate makes small adjustments to LoRA weights — enough to recognize your template format (e.g., ChatML delimiters, markdown structure) but not enough to overwrite the base model's knowledge. By Stage 2, the model already "knows" how to format its output, so the higher learning rate can focus entirely on learning domain-specific patterns without fighting the format alignment simultaneously.

This is analogous to curriculum learning: teach the easy stuff first (format), then the hard stuff (knowledge). The result is better convergence and significantly less forgetting of general capabilities.'''
    ),

    (
        "ml_train1_02",
        r'''What LoRA rank should I use? I've seen people recommend r=4, r=16, r=64, and even r=256. How do I decide?''',
        r'''## LoRA Rank Selection Guide

The rank `r` controls the expressiveness of your LoRA adapter — how many independent "directions" of change it can apply to the base model's weights. Here's a practical framework:

### Rank Guidelines by Task

| Rank | Use Case | Example |
|------|----------|---------|
| r=4–8 | Style/format adaptation | "Write in markdown", tone changes |
| r=16 | Domain knowledge (sweet spot) | Coding assistant, domain QA |
| r=32–64 | Complex multi-domain training | Multi-task, multi-language |
| r=128–256 | Near full fine-tuning | Rarely needed with LoRA |

### Why r=16 is the Sweet Spot for Most Tasks

```python
from peft import LoraConfig

# Recommended config for domain fine-tuning
config = LoraConfig(
    r=16,
    lora_alpha=32,           # alpha = 2*r is a solid default
    lora_dropout=0.1,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    use_rslora=True,         # Rank-stabilized LoRA scales better
)
```

### Key Principles

1. **alpha/r ratio matters more than absolute values**: `lora_alpha=32` with `r=16` gives a scaling factor of 2.0. With RSLoRA enabled, this scaling is `alpha / sqrt(r)` instead of `alpha / r`, which makes higher ranks more stable.

2. **Diminishing returns**: Going from r=4 to r=16 gives a large quality jump. Going from r=16 to r=64 gives marginal improvement for 4x the parameters. Going from r=64 to r=256 rarely helps unless your task is extremely diverse.

3. **Trainable parameter count**:
   ```
   r=8  → ~0.1% of 14B params → ~14M trainable
   r=16 → ~0.2% of 14B params → ~28M trainable
   r=64 → ~0.8% of 14B params → ~112M trainable
   ```

4. **Higher rank ≠ always better**: Higher ranks increase risk of overfitting, especially on small datasets (<5K pairs). If you have <2K training pairs, r=8 may outperform r=16.

### Decision Checklist

- Dataset size <2K pairs → r=8, alpha=16
- Dataset 2K–10K pairs, single domain → r=16, alpha=32
- Dataset 10K+ pairs, multiple domains → r=32, alpha=64
- Always use RSLoRA (`use_rslora=True`) for ranks ≥16 — it prevents the scaling factor from dominating at higher ranks'''
    ),

    (
        "ml_train1_03",
        r'''How should I set the learning rate for LoRA fine-tuning? I keep getting either no learning or catastrophic forgetting.''',
        r'''## Learning Rate Selection for LoRA Fine-Tuning

The learning rate is the most impactful hyperparameter in LoRA training. Too low and the adapter learns nothing; too high and you destroy the base model's knowledge.

### Recommended Ranges

For LoRA (NOT full fine-tuning — full FT uses 10-100x lower rates):

| Model Size | Conservative | Standard | Aggressive |
|------------|-------------|----------|-----------|
| 7B | 1e-5 | 2e-5 | 5e-5 |
| 14B | 5e-6 | 1e-5 | 2e-5 |
| 70B | 2e-6 | 5e-6 | 1e-5 |

### Learning Rate Scheduling

```python
from transformers import TrainingArguments

args = TrainingArguments(
    learning_rate=2e-5,
    lr_scheduler_type="cosine",    # Smooth decay — best for LoRA
    warmup_ratio=0.05,             # 5% of steps for warmup
    num_train_epochs=2,
    # ...
)
```

**Why cosine > linear**: Cosine scheduling decays the LR smoothly to near-zero at the end, which gives the model a "settling" period where it can fine-tune details without large weight updates. Linear decay is more abrupt.

### Diagnosing LR Problems

**Too high** (catastrophic forgetting):
- Training loss drops very fast in the first 50 steps
- Eval loss starts rising after initial drop (classic overfitting/forgetting curve)
- Model outputs become repetitive or nonsensical on general tasks

**Too low** (underfitting):
- Training loss barely moves across epochs
- Model outputs are identical to base model — adapter has no effect

**Just right**:
- Training loss decreases steadily over the first epoch
- Eval loss tracks training loss (no divergence)
- Model handles both domain and general tasks

### Practical Tip: The LR Finder Approach

If unsure, run 3 short experiments (100-200 steps each) at 5e-6, 2e-5, and 5e-5. Compare the loss curves — pick the highest LR that doesn't cause eval loss divergence. This takes 15-20 minutes and saves hours of full training at the wrong rate.'''
    ),

    (
        "ml_train1_04",
        r'''What target modules should I apply LoRA to? I see some people only targeting q_proj/v_proj and others targeting all linear layers.''',
        r'''<think>
This is a common question. The original LoRA paper only adapted q_proj and v_proj, but modern practice targets all attention projections plus the MLP layers. I should explain the trade-offs and give a concrete recommendation.
</think>

## LoRA Target Module Selection

### The Evolution of Target Module Selection

The original LoRA paper (Hu et al., 2021) demonstrated results with only `q_proj` and `v_proj`. This was conservative — they proved the concept on minimal parameters. Modern practice has moved significantly:

### Module Groups and Their Effects

```python
# Minimal — original LoRA paper approach
target_modules = ["q_proj", "v_proj"]
# Pros: Fewest trainable params, fastest training
# Cons: Limited expressiveness, often undertrained

# Attention-only — common recommendation
target_modules = ["q_proj", "k_proj", "v_proj", "o_proj"]
# Pros: Good for style/format changes
# Cons: Misses MLP layers where factual knowledge is stored

# Full (recommended) — attention + MLP
target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                  "gate_proj", "up_proj", "down_proj"]
# Pros: Best quality, adapts both attention patterns AND knowledge
# Cons: ~3x more params than attention-only
```

### Why Include MLP Layers?

Research has shown that in transformer models:
- **Attention layers** control what information flows between tokens (patterns, relationships)
- **MLP layers** store factual knowledge and perform transformations

If you're training a domain-specific assistant (coding, medical, legal), the model needs to learn **new knowledge**, not just new attention patterns. Skipping MLP layers leaves the most important knowledge-storing parameters frozen.

### Practical Impact

For a 14B parameter model with r=16:

```
q_proj + v_proj only:     ~8M params  (0.06%)
All attention:            ~16M params (0.11%)
Attention + MLP:          ~28M params (0.20%)
```

The difference between 8M and 28M trainable parameters is negligible in terms of memory and speed — LoRA is already parameter-efficient. But the quality difference is significant: attention+MLP consistently outperforms attention-only on knowledge-intensive tasks.

### Recommendation

Always use the full set (`q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`) unless you have a specific reason not to. The marginal cost is tiny; the quality gain is real.'''
    ),

    (
        "ml_train1_05",
        r'''I trained a LoRA adapter and it works great on my domain but the model became worse at general tasks. How do I prevent this drift from the base model?''',
        r'''## Preventing Base Model Drift with KL Regularization

When a LoRA adapter drifts too far from the base model, general capabilities degrade. This is called **catastrophic forgetting**. The best defense is **KL divergence regularization** — it penalizes the fine-tuned model for diverging too much from the base model's output distribution.

### How KL Regularization Works

During training, you compute two forward passes:
1. Fine-tuned model's logits (with LoRA active)
2. Base model's logits (with LoRA disabled)

The KL divergence between these distributions is added to the training loss:

```
total_loss = task_loss + lambda * KL(fine_tuned || base)
```

### Implementation

```python
import torch
import torch.nn.functional as F
from transformers import Trainer

class KLRegularizedTrainer(Trainer):
    """Trainer with KL divergence regularization against base model."""

    def __init__(self, *args, kl_lambda=0.3, kl_temperature=1.0,
                 kl_seq_limit=512, **kwargs):
        super().__init__(*args, **kwargs)
        self.kl_lambda = kl_lambda
        self.kl_temperature = kl_temperature
        self.kl_seq_limit = kl_seq_limit

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        # Forward pass with LoRA (fine-tuned)
        outputs = model(**inputs)
        task_loss = outputs.loss

        # Forward pass without LoRA (base model)
        model.disable_adapter_layers()
        with torch.no_grad():
            base_outputs = model(**inputs)
        model.enable_adapter_layers()

        # Compute KL divergence on truncated sequences
        ft_logits = outputs.logits[:, :self.kl_seq_limit, :]
        base_logits = base_outputs.logits[:, :self.kl_seq_limit, :]

        ft_probs = F.log_softmax(ft_logits / self.kl_temperature, dim=-1)
        base_probs = F.softmax(base_logits / self.kl_temperature, dim=-1)

        kl_div = F.kl_div(ft_probs, base_probs, reduction="batchmean")
        total_loss = task_loss + self.kl_lambda * kl_div

        return (total_loss, outputs) if return_outputs else total_loss
```

### Hyperparameter Guidelines

| Parameter | Value | Effect |
|-----------|-------|--------|
| `kl_lambda` | 0.1–0.5 (default: 0.3) | Higher = stronger regularization, less domain learning |
| `kl_temperature` | 1.0 | Higher = softer distributions, smoother penalty |
| `kl_seq_limit` | 512 | Truncate for memory — KL on full sequences is expensive |

### Important Notes

- **Lambda tuning**: Start at 0.3. If the model still forgets general tasks, increase to 0.5. If it's not learning domain knowledge, decrease to 0.1.
- **Memory cost**: KL regularization requires two forward passes per step. With `kl_seq_limit=512`, the overhead is manageable (~30% more VRAM).
- **Combine with two-stage training**: Use KL regularization primarily in Stage 2 (knowledge training) where drift risk is highest. Stage 1 (format alignment) at low LR rarely causes significant drift.'''
    ),

    # ===================== TRAINING DATA CURATION (4 pairs) =====================

    (
        "ml_train1_06",
        r'''I have a dataset of 10K training pairs for fine-tuning. Some are duplicates from oversampling, and the quality varies. How can I score and filter the data to keep only the best pairs?''',
        r'''<think>
The user needs a data scoring and filtering pipeline. The key insight from our findings is that the scoring formula (0.35*difficulty + 0.35*novelty + 0.30*quality) works well, and that zero-novelty duplicates from oversampling are the main source of low-quality data. I should provide a practical implementation.
</think>

## Training Data Importance Scoring and Filtering

### Scoring Formula

Each training pair gets a composite score based on three factors:

```
score = 0.35 * difficulty + 0.35 * novelty + 0.30 * quality
```

- **Difficulty** (0–1): How challenging is the task? Simple Q&A scores low; multi-step reasoning scores high
- **Novelty** (0–1): How unique is this pair relative to the rest of the dataset? Exact duplicates score 0
- **Quality** (0–1): How well-written and correct is the response?

### Implementation

```python
import hashlib
from collections import Counter
from difflib import SequenceMatcher
from dataclasses import dataclass

@dataclass
class ScoredPair:
    id: str
    question: str
    answer: str
    difficulty: float
    novelty: float
    quality: float

    @property
    def score(self) -> float:
        return 0.35 * self.difficulty + 0.35 * self.novelty + 0.30 * self.quality


def compute_novelty(pairs: list[dict]) -> dict[str, float]:
    """Score novelty based on content hashing and similarity detection."""
    # Hash each pair's content for exact duplicate detection
    content_hashes = Counter()
    pair_hashes = {}

    for pair in pairs:
        content = f"{pair['question'].strip()}\n{pair['answer'].strip()}"
        h = hashlib.sha256(content.encode()).hexdigest()
        content_hashes[h] += 1
        pair_hashes[pair['id']] = h

    novelty_scores = {}
    for pair in pairs:
        h = pair_hashes[pair['id']]
        count = content_hashes[h]
        if count > 1:
            # Exact duplicate — zero novelty
            novelty_scores[pair['id']] = 0.0
        else:
            # Check near-duplicates via question similarity
            max_sim = 0.0
            for other in pairs:
                if other['id'] == pair['id']:
                    continue
                sim = SequenceMatcher(
                    None, pair['question'], other['question']
                ).ratio()
                max_sim = max(max_sim, sim)
            # High similarity to another pair = low novelty
            novelty_scores[pair['id']] = max(0.0, 1.0 - max_sim)

    return novelty_scores


def compute_difficulty(pair: dict) -> float:
    """Heuristic difficulty score based on response characteristics."""
    answer = pair['answer']
    score = 0.0

    # Longer responses suggest more complex tasks
    word_count = len(answer.split())
    if word_count > 500:
        score += 0.3
    elif word_count > 200:
        score += 0.2
    elif word_count > 100:
        score += 0.1

    # Code blocks suggest implementation tasks
    code_blocks = answer.count("```")
    if code_blocks >= 4:
        score += 0.3
    elif code_blocks >= 2:
        score += 0.2

    # Reasoning traces indicate complex problems
    if "<think>" in answer:
        score += 0.3

    # Multi-step indicators
    for marker in ["Step 1", "### ", "1.", "First,"]:
        if marker in answer:
            score += 0.1
            break

    return min(1.0, score)


def filter_dataset(pairs: list[dict], threshold: float = 0.3) -> list[dict]:
    """Score and filter training pairs.

    Use threshold=0.3 to remove only obvious junk (duplicates, trivial pairs).
    Avoid threshold>0.5 — it cuts useful training data.
    """
    novelty_scores = compute_novelty(pairs)

    scored = []
    for pair in pairs:
        sp = ScoredPair(
            id=pair['id'],
            question=pair['question'],
            answer=pair['answer'],
            difficulty=compute_difficulty(pair),
            novelty=novelty_scores[pair['id']],
            quality=compute_quality(pair),  # your quality scoring function
        )
        scored.append(sp)

    # Filter by threshold
    kept = [sp for sp in scored if sp.score >= threshold]

    print(f"Filtered: {len(pairs)} → {len(kept)} pairs "
          f"(removed {len(pairs) - len(kept)}, threshold={threshold})")

    # Log why pairs were removed
    removed = [sp for sp in scored if sp.score < threshold]
    zero_novelty = sum(1 for sp in removed if sp.novelty == 0.0)
    print(f"  Zero-novelty duplicates removed: {zero_novelty}")

    return [{"id": sp.id, "question": sp.question, "answer": sp.answer}
            for sp in kept]
```

### Threshold Guidelines

- **0.3** (recommended): Removes exact duplicates and trivially short/broken pairs. Safe default.
- **0.4**: Slightly more aggressive. Good if you have >10K pairs and want to trim.
- **0.5+**: Dangerous — cuts borderline but useful training data. Only use if you have >20K pairs and need to reduce training time.

### Key Insight: Oversampling Creates Zero-Novelty Duplicates

If you're oversampling domain-specific data (e.g., 2x for Hive blockchain pairs), you may be creating exact duplicates that score 0.0 novelty. These duplicates waste training budget without adding learning signal. Better approaches: rephrase duplicates slightly, or use loss weighting instead of data duplication.'''
    ),

    (
        "ml_train1_07",
        r'''What's the ideal balance between code generation and code understanding pairs in a training dataset for a coding assistant?''',
        r'''## Generation vs Understanding Balance in Training Data

### The Two Types of Coding Pairs

**Generation pairs** (implement, build, write, create):
```
Q: "Write a function that validates email addresses"
A: [Implementation code + explanation]
```

**Understanding pairs** (explain, debug, analyze, review):
```
Q: "Why does this async function have a race condition?"
A: [Analysis of the bug + fix explanation]
```

### Ideal Ratios

| Ratio (Gen/Understand) | Result |
|------------------------|--------|
| 80/20 | Model generates well but can't explain its reasoning |
| 60/40 | Good balance — strong generation with solid explanation ability |
| 50/50 | Best for assistants that need to teach/debug as much as build |
| 30/70 | Understanding-focused — good for code review tools, not builders |

**Recommended: 60/40 or 50/50** for general-purpose coding assistants.

### Why Understanding Pairs Matter

A model trained primarily on generation pairs develops a bias: when asked "why does this code fail?", it tends to just rewrite the code instead of explaining the problem. Understanding pairs teach the model to:

1. **Analyze** existing code without rewriting it
2. **Explain** concepts in plain language
3. **Debug** by identifying root causes, not just symptoms
4. **Review** code and suggest improvements with reasoning

### How to Audit Your Dataset

```python
import re

def classify_pair(question: str) -> str:
    """Classify a training pair as generation or understanding."""
    q = question.lower()

    generation_signals = [
        r'\b(write|implement|create|build|make|generate|code)\b',
        r'\b(add|develop|design|set up|scaffold)\b',
    ]
    understanding_signals = [
        r'\b(explain|why|how does|what does|analyze|debug)\b',
        r'\b(review|compare|difference|trade-?off|when to use)\b',
        r'\b(fix|broken|error|bug|wrong|issue)\b',
    ]

    gen_score = sum(1 for p in generation_signals if re.search(p, q))
    und_score = sum(1 for p in understanding_signals if re.search(p, q))

    return "generation" if gen_score > und_score else "understanding"


def audit_balance(pairs: list[dict]) -> dict:
    """Check generation/understanding ratio."""
    counts = {"generation": 0, "understanding": 0}
    for pair in pairs:
        category = classify_pair(pair["question"])
        counts[category] += 1

    total = len(pairs)
    print(f"Generation:    {counts['generation']:4d} ({counts['generation']/total:.0%})")
    print(f"Understanding: {counts['understanding']:4d} ({counts['understanding']/total:.0%})")

    return counts
```

### Rebalancing Strategies

If your dataset is generation-heavy (common because it's easier to write "implement X" pairs):

1. **Add debugging pairs**: Take existing code from generation answers, introduce realistic bugs, create "find the bug" pairs
2. **Add explanation pairs**: Ask "explain how this works" for complex implementations already in your dataset
3. **Add comparison pairs**: "When should I use X vs Y?" forces the model to reason about trade-offs
4. **Add code review pairs**: Present code with subtle issues and ask for review'''
    ),

    (
        "ml_train1_08",
        r'''How do I deduplicate training data for LLM fine-tuning? I'm worried about exact and near-duplicate pairs inflating my dataset.''',
        r'''## Training Data Deduplication for LLM Fine-Tuning

### Three Levels of Deduplication

1. **Exact duplicates**: Identical question+answer text
2. **Near-duplicates**: Same question with minor wording differences
3. **Semantic duplicates**: Different wording but same knowledge being taught

### Implementation

```python
import hashlib
from collections import defaultdict
from difflib import SequenceMatcher

def deduplicate_training_pairs(
    pairs: list[dict],
    similarity_threshold: float = 0.85,
) -> list[dict]:
    """Remove exact and near-duplicate training pairs.

    Args:
        pairs: List of dicts with 'id', 'question', 'answer' keys
        similarity_threshold: Pairs with question similarity above
                              this threshold are considered near-duplicates

    Returns:
        Deduplicated list, keeping the first occurrence
    """
    # Phase 1: Exact dedup via content hashing
    seen_hashes = {}
    phase1_kept = []

    for pair in pairs:
        content = pair["question"].strip() + "\n" + pair["answer"].strip()
        h = hashlib.sha256(content.encode()).hexdigest()
        if h not in seen_hashes:
            seen_hashes[h] = pair["id"]
            phase1_kept.append(pair)

    exact_removed = len(pairs) - len(phase1_kept)
    print(f"Phase 1 (exact): {len(pairs)} → {len(phase1_kept)} "
          f"(removed {exact_removed})")

    # Phase 2: Near-duplicate detection via question similarity
    phase2_kept = []
    removed_near = []

    for i, pair in enumerate(phase1_kept):
        is_duplicate = False
        for kept in phase2_kept:
            sim = SequenceMatcher(
                None,
                pair["question"].lower().strip(),
                kept["question"].lower().strip(),
            ).ratio()
            if sim > similarity_threshold:
                is_duplicate = True
                removed_near.append((pair["id"], kept["id"], sim))
                break

        if not is_duplicate:
            phase2_kept.append(pair)

    print(f"Phase 2 (near):  {len(phase1_kept)} → {len(phase2_kept)} "
          f"(removed {len(removed_near)})")

    # Report near-duplicates for review
    if removed_near:
        print("\nNear-duplicate pairs removed:")
        for removed_id, kept_id, sim in removed_near[:10]:
            print(f"  {removed_id} ≈ {kept_id} (similarity: {sim:.2f})")

    return phase2_kept
```

### Handling Oversampled Domain Data

If you intentionally oversampled domain-specific pairs (e.g., 2x for blockchain data), deduplication will correctly flag those as duplicates. Instead of exact duplication, use these alternatives:

```python
def weighted_sampling(pairs: list[dict], weights: dict[str, float]):
    """Use loss weighting instead of data duplication.

    weights: mapping from domain → weight multiplier
    e.g., {"hive": 2.0, "general": 1.0}
    """
    # Create a custom data collator that scales loss by domain weight
    pair_weights = []
    for pair in pairs:
        domain = pair.get("domain", "general")
        pair_weights.append(weights.get(domain, 1.0))

    return pair_weights
```

### Key Takeaway

Exact duplicates from oversampling are the #1 source of wasted training budget. They don't teach the model anything new — the model sees the exact same gradient twice. Use loss weighting or rephrasing instead of raw duplication.'''
    ),

    (
        "ml_train1_09",
        r'''I have training data from multiple domains (Python, JavaScript, Go, system design). How should I balance the mix for a general coding assistant?''',
        r'''## Multi-Domain Training Data Balancing

### The Problem

If your dataset is 70% Python, 15% JavaScript, 10% system design, and 5% Go, the model will become Python-biased. It'll try to solve Go problems with Python patterns and give superficial system design answers.

### Balancing Strategy

**Step 1: Categorize and count**

```python
from collections import Counter

def categorize_pairs(pairs: list[dict]) -> dict[str, list]:
    """Group pairs by domain category."""
    categories = {
        "python": [],
        "javascript": [],
        "go": [],
        "system_design": [],
        "general": [],
    }

    for pair in pairs:
        cat = detect_category(pair["question"], pair["answer"])
        categories.get(cat, categories["general"]).append(pair)

    for cat, cat_pairs in categories.items():
        print(f"  {cat}: {len(cat_pairs)} pairs")

    return categories
```

**Step 2: Define target distribution**

```python
# Target mix for a general coding assistant
TARGET_DISTRIBUTION = {
    "python":        0.30,   # Core language
    "javascript":    0.25,   # Web ecosystem
    "go":            0.10,   # Systems language
    "system_design": 0.15,   # Architecture skills
    "general":       0.20,   # Cross-cutting (debugging, testing, etc.)
}
```

**Step 3: Rebalance via undersampling the majority + generation for minority**

```python
import random

def rebalance_dataset(
    categories: dict[str, list],
    target_dist: dict[str, float],
    target_total: int = 8000,
) -> list[dict]:
    """Rebalance dataset to match target distribution.

    Uses undersampling for over-represented categories.
    Flags under-represented categories for data generation.
    """
    balanced = []

    for cat, target_frac in target_dist.items():
        target_count = int(target_total * target_frac)
        available = categories.get(cat, [])

        if len(available) >= target_count:
            # Undersample — randomly pick target_count pairs
            sampled = random.sample(available, target_count)
            balanced.extend(sampled)
            print(f"  {cat}: {len(available)} → {target_count} (undersampled)")
        else:
            # Use all available, flag deficit
            balanced.extend(available)
            deficit = target_count - len(available)
            print(f"  {cat}: {len(available)} → {len(available)} "
                  f"(NEED {deficit} MORE PAIRS)")

    random.shuffle(balanced)
    return balanced
```

### Important Considerations

1. **Don't oversample small categories via duplication** — this creates exact duplicates that waste training budget. Instead, generate new pairs or accept a smaller dataset.

2. **Within each domain, maintain the generation/understanding balance** (aim for 60/40).

3. **Difficulty curve**: Each category should have easy, medium, and hard pairs. Don't make all Go pairs trivial while Python pairs are complex — the model will learn that Go means simple.

4. **Cross-domain pairs are valuable**: "Port this Python REST API to Go" teaches both languages and transfer skills. Count these toward both categories or create a separate "cross-domain" category.'''
    ),

    # ===================== LOSS MASKING AND TRAINING EFFICIENCY (3 pairs) =====================

    (
        "ml_train1_10",
        r'''What is response-only loss masking in LLM fine-tuning and why should I use it?''',
        r'''## Response-Only Loss Masking

### The Problem with Standard Training

In standard causal language model fine-tuning, the model computes loss on **every token** in the training sequence — including the system prompt, user question, and all template tokens (`<|im_start|>`, `<|im_end|>`, etc.). This is wasteful because:

1. The model already knows how to reproduce prompt tokens (it's a pre-trained LLM)
2. You're wasting ~40-50% of your compute on tokens that don't teach anything new
3. The gradient signal is diluted — prompt token loss pulls weights in directions that don't improve response quality

### How Response-Only Masking Works

You mask the loss on all tokens except the assistant's response, effectively **doubling your effective training signal**:

```
<|im_start|>system
You are a helpful assistant.<|im_end|>     ← loss masked (-100)
<|im_start|>user
Write a sort function<|im_end|>            ← loss masked (-100)
<|im_start|>assistant
Here's a sort function:                    ← LOSS COMPUTED
```python
def sort(arr):                             ← LOSS COMPUTED
    return sorted(arr)                     ← LOSS COMPUTED
```<|im_end|>                              ← LOSS COMPUTED
```

### Implementation with HuggingFace TRL

```python
from trl import DataCollatorForCompletionOnlyLM

# Define the response template — tokens that mark start of assistant response
response_template = "<|im_start|>assistant\n"

collator = DataCollatorForCompletionOnlyLM(
    response_template=response_template,
    tokenizer=tokenizer,
    mlm=False,
)

# Use this collator with Trainer or SFTTrainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    data_collator=collator,
)
```

### What This Means Practically

For a dataset where prompts average 200 tokens and responses average 300 tokens:

| Metric | Standard | Response-Only |
|--------|----------|---------------|
| Tokens with loss | 500 | 300 |
| Effective training signal | 60% | 100% |
| Training quality | Baseline | ~2x better signal-to-noise |

### Important Caveat: Packing is Incompatible

Sequence packing (concatenating multiple examples into one sequence for efficiency) **breaks response-only masking**. The reason: the collator looks for the response template token sequence to know where to start computing loss. With packing, multiple examples are concatenated, and the template boundaries get confused.

If you use response-only masking, set `packing=False` in your training config. The slight efficiency loss from padding is more than compensated by the quality gain from proper loss masking.'''
    ),

    (
        "ml_train1_11",
        r'''How does KL divergence regularization work during LoRA training, and when should I increase or decrease the lambda value?''',
        r'''## KL Divergence Regularization in LoRA Training

### Core Concept

KL regularization adds a penalty term that measures how far your fine-tuned model's output distribution has drifted from the base model. The total training loss becomes:

```
L_total = L_task + λ * KL(P_finetuned || P_base)
```

Where:
- `L_task` is the standard cross-entropy loss on your training data
- `KL(P || Q)` measures the divergence between fine-tuned and base distributions
- `λ` (lambda) controls regularization strength

### How It Works Mechanically

At each training step:
1. Run forward pass with LoRA adapters **enabled** → get fine-tuned logits
2. Run forward pass with LoRA adapters **disabled** → get base model logits
3. Compute KL divergence between the two sets of logits
4. Add `λ * KL` to the task loss before backpropagation

The LoRA adapter weights are the only trainable parameters, so the gradient update adjusts them to balance between learning the task (low `L_task`) and staying close to the base model (low KL).

### Lambda Tuning Guide

```
λ = 0.0  →  No regularization (pure task learning, maximum forgetting risk)
λ = 0.1  →  Light regularization (domain-heavy training, tolerate some drift)
λ = 0.3  →  Standard (good default for most LoRA fine-tuning)
λ = 0.5  →  Strong regularization (when base capabilities are critical)
λ = 1.0  →  Very strong (model barely learns — usually too aggressive)
```

### When to Adjust Lambda

**Increase lambda (0.3 → 0.5)** when:
- Model loses general coding ability after training
- Base model's instruction following degrades
- Training data is very domain-specific (e.g., only blockchain code)

**Decrease lambda (0.3 → 0.1)** when:
- Model isn't learning domain knowledge well enough
- Training/eval loss plateaus early
- Your dataset is diverse enough to maintain general capabilities naturally

### Memory Optimization

KL computation requires two forward passes, which increases VRAM usage. To manage this:

```python
# Truncate KL computation to first N tokens
kl_seq_limit = 512  # Don't compute KL on full 4096-token sequences

ft_logits = outputs.logits[:, :kl_seq_limit, :]
base_logits = base_outputs.logits[:, :kl_seq_limit, :]
```

This reduces KL VRAM overhead from ~30% to ~10% with minimal impact on regularization quality, since the early tokens capture most of the distribution information.'''
    ),

    (
        "ml_train1_12",
        r'''I want to train a LoRA adapter but my dataset is too large to fit into GPU memory. What are my options for training efficiency?''',
        r'''## Training Efficiency Techniques for Large Datasets

### 1. Gradient Accumulation (First Thing to Try)

Instead of fitting a large batch into memory at once, accumulate gradients over multiple small batches:

```python
from transformers import TrainingArguments

args = TrainingArguments(
    per_device_train_batch_size=1,         # Tiny batch per step
    gradient_accumulation_steps=16,        # Effective batch = 1 * 16 = 16
    # ...
)
```

**Effect**: Simulates batch size 16 while only loading 1 example at a time. Training takes longer but uses minimal memory.

### 2. Mixed Precision Training (BF16)

Always use BF16 for modern GPUs (Ampere+). It halves memory usage for activations and is numerically stable:

```python
args = TrainingArguments(
    bf16=True,
    bf16_full_eval=True,
    # ...
)
```

**Effect**: ~40% VRAM reduction vs FP32 with no quality loss.

### 3. Gradient Checkpointing

Trade compute for memory — recompute activations during backward pass instead of storing them:

```python
model.gradient_checkpointing_enable()

args = TrainingArguments(
    gradient_checkpointing=True,
    # ...
)
```

**Effect**: ~60% reduction in activation memory at ~30% increase in training time.

### 4. 4-Bit Base Model Loading (QLoRA)

Load the base model in 4-bit quantization and only train LoRA adapters in full precision:

```python
from transformers import BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,     # Nested quantization
)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=bnb_config,
    device_map="auto",
)
```

**Effect**: 14B model fits in ~10GB VRAM instead of ~28GB (BF16).

### 5. Sequence Length Management

Long sequences dominate memory. Filter or truncate:

```python
MAX_RESPONSE_LEN = 15000  # chars, not tokens

def filter_verbose_pairs(pairs):
    """Remove excessively long responses that waste training budget."""
    kept = [p for p in pairs if len(p["answer"]) <= MAX_RESPONSE_LEN]
    print(f"Verbosity filter: {len(pairs)} → {len(kept)} pairs")
    return kept
```

### Recommended Stack for 24GB VRAM (RTX 3090/4090)

```python
# This stack fits a 14B model training on 24GB VRAM
bnb_config = BitsAndBytesConfig(load_in_4bit=True, ...)  # QLoRA
args = TrainingArguments(
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    bf16=True,
    gradient_checkpointing=True,
    max_grad_norm=1.0,
)
model.gradient_checkpointing_enable()
```

### Combined Memory Impact

| Technique | VRAM Savings | Speed Cost |
|-----------|-------------|-----------|
| BF16 | ~40% | None |
| 4-bit (QLoRA) | ~75% | ~5% slower |
| Gradient checkpointing | ~60% activations | ~30% slower |
| Gradient accumulation | Linear with batch | Linear with steps |
| Sequence truncation | Proportional | None |'''
    ),

    # ===================== DATA QUALITY PATTERNS (3 pairs) =====================

    (
        "ml_train1_13",
        r'''How do I control verbosity in my fine-tuned model? After training, it generates extremely long responses even for simple questions.''',
        r'''<think>
Verbose output is a common problem from training on verbose data. The fix is twofold: filter verbose pairs from training data AND add concise answer pairs that teach the model brevity is acceptable.
</think>

## Controlling Model Verbosity After Fine-Tuning

### Root Cause

If your model generates 500-word answers to "what does `len()` do?", the problem is in your training data — the model learned that **every** response should be long and detailed. This happens when:

1. Most training pairs have long responses (>1000 words)
2. No short/concise training pairs exist as counterexamples
3. Verbose pairs from reasoning distillation dominate the dataset

### Fix 1: Verbosity Filter on Training Data

```python
def apply_verbosity_filter(pairs: list[dict],
                           max_chars: int = 15000) -> list[dict]:
    """Remove excessively verbose training pairs.

    15000 chars ≈ 3000-4000 tokens. Responses longer than this
    are typically bloated with unnecessary repetition.
    """
    kept = []
    removed_count = 0

    for pair in pairs:
        if len(pair["answer"]) <= max_chars:
            kept.append(pair)
        else:
            removed_count += 1

    print(f"Verbosity filter: removed {removed_count} pairs "
          f"over {max_chars} chars")
    return kept
```

### Fix 2: Add Concise Answer Pairs

Explicitly train the model that short answers are appropriate for simple questions:

```python
CONCISE_PAIRS = [
    {
        "question": "What does the `zip()` function do in Python?",
        "answer": (
            "`zip()` takes multiple iterables and returns an iterator "
            "of tuples, pairing elements by position:\n\n"
            "```python\n"
            "names = ['Alice', 'Bob']\n"
            "ages = [30, 25]\n"
            "list(zip(names, ages))  # [('Alice', 30), ('Bob', 25)]\n"
            "```\n\n"
            "It stops at the shortest iterable. Use `itertools.zip_longest` "
            "to pad shorter iterables."
        ),
    },
    # Add 20-30 concise pairs like this covering basic concepts
]
```

### Fix 3: Response Length Distribution Audit

```python
def audit_response_lengths(pairs: list[dict]):
    """Check if your dataset is verbosity-biased."""
    lengths = [len(p["answer"]) for p in pairs]
    lengths.sort()

    short = sum(1 for l in lengths if l < 500)
    medium = sum(1 for l in lengths if 500 <= l < 2000)
    long = sum(1 for l in lengths if 2000 <= l < 5000)
    very_long = sum(1 for l in lengths if l >= 5000)

    total = len(lengths)
    print(f"Short  (<500 chars):   {short:4d} ({short/total:.0%})")
    print(f"Medium (500-2K):       {medium:4d} ({medium/total:.0%})")
    print(f"Long   (2K-5K):        {long:4d} ({long/total:.0%})")
    print(f"Very long (5K+):       {very_long:4d} ({very_long/total:.0%})")

    if short / total < 0.15:
        print("\n⚠ WARNING: Less than 15% short responses — model will "
              "be verbose. Add concise answer pairs.")
```

### Target Distribution

A well-balanced dataset should have approximately:
- **15-20%** short responses (<500 chars) — simple facts, quick answers
- **40-50%** medium responses (500-2000 chars) — standard explanations
- **25-30%** long responses (2000-5000 chars) — detailed implementations
- **<10%** very long responses (5000+ chars) — complex multi-part answers'''
    ),

    (
        "ml_train1_14",
        r'''What makes a good reasoning trace for training data? I'm adding <think> blocks to my fine-tuning dataset.''',
        r'''## Writing High-Quality Reasoning Traces for Training Data

### What a Reasoning Trace Should Do

A `<think>` block teaches the model **how to approach problems**, not just what the answer is. Good traces show the thinking process; bad traces just restate the question.

### Good vs Bad Traces

**Bad trace** (restates the question):
```
<think>
The user wants to implement a binary search. I will implement a binary search function.
</think>
```

**Good trace** (shows reasoning process):
```
<think>
The user wants binary search. Key decisions:
1. Iterative vs recursive — iterative is better for production (no stack overflow risk)
2. Edge cases: empty array, single element, target not found
3. Return type: index or -1? I'll return the index or -1, matching the convention
4. The array must be sorted — I should mention this precondition
</think>
```

### Principles for Quality Traces

1. **Show decision points**: "Should I use X or Y? X is better here because..."
2. **Identify edge cases**: "What happens when the input is empty/null/negative?"
3. **Acknowledge trade-offs**: "This approach is O(n²) but simpler. For the user's scale, it's fine."
4. **Plan the structure**: "I'll need three parts: validation, processing, error handling."
5. **Keep it concise**: 3-8 sentences. Longer traces don't improve quality.

### When to Include Traces (and When Not To)

**Include `<think>` for:**
- Multi-step problems (algorithms, architecture decisions)
- Debugging questions (reasoning about what could be wrong)
- Design trade-off questions (choosing between approaches)
- Complex implementations (planning the code structure)

**Skip `<think>` for:**
- Simple factual questions ("What does `map()` do?")
- Direct API usage ("How do I read a file in Python?")
- Concise answer pairs (these should be short by design)

### Target Mix in Dataset

```
~50% of pairs: No reasoning trace (direct answers)
~40% of pairs: Short trace (3-5 sentences)
~10% of pairs: Detailed trace (6-8 sentences, complex problems)
```

### Key Research Finding

Quality of reasoning traces matters far more than quantity. A dataset with ~4K high-quality reasoning pairs consistently outperforms larger datasets with noisy or shallow traces. A shallow trace ("I will answer the question") is worse than no trace at all — it teaches the model to produce meaningless preamble.'''
    ),

    (
        "ml_train1_15",
        r'''What is curriculum learning for LLM fine-tuning? Should I order my training data from easy to hard?''',
        r'''## Curriculum Learning for LLM Fine-Tuning

### The Concept

Curriculum learning presents training data in a structured order — typically easy examples first, then progressively harder ones — mimicking how humans learn. The idea is that mastering simple patterns provides a foundation for learning complex ones.

### Does It Work for LLM Fine-Tuning?

**Short answer**: The benefit is modest for LoRA fine-tuning compared to training from scratch. Here's why:

1. **Pre-trained LLMs already know the basics** — they don't need "easy" examples to learn fundamentals
2. **Standard shuffled training** works well because LoRA adapters converge quickly
3. **Two-stage training** (format alignment → knowledge training) captures the most important curriculum effect without explicit difficulty ordering

### When Curriculum Order Helps

The main scenario where ordering matters is **two-stage training**, which is a form of curriculum learning:

```python
# Stage 1: Format/style alignment (easy — just learn the template)
stage1_args = TrainingArguments(
    num_train_epochs=1,
    learning_rate=1e-5,  # Low LR — gentle alignment
)

# Stage 2: Domain knowledge (hard — learn new capabilities)
stage2_args = TrainingArguments(
    num_train_epochs=2,
    learning_rate=2e-5,  # Higher LR — active learning
)
```

This works because format alignment is genuinely easier and provides a stable foundation for knowledge learning.

### What Doesn't Help

Sorting individual pairs by difficulty within a stage typically doesn't help and can hurt:

```python
# DON'T DO THIS — it creates training distribution shift
dataset = sorted(dataset, key=lambda x: x["difficulty"])

# DO THIS INSTEAD — shuffle within each stage
random.shuffle(dataset)
```

**Why sorting hurts**: If easy examples come first, the model overfits to easy patterns early on. When hard examples arrive later, the model has to "unlearn" some of the overfit patterns. Shuffling ensures the model sees a representative mix at every point in training.

### Practical Recommendation

1. **Use two-stage training** (this is the highest-impact curriculum effect)
2. **Shuffle data within each stage** (don't sort by difficulty)
3. **Ensure difficulty diversity** in your dataset (don't make it all easy or all hard)
4. **If your dataset has clear tiers**, consider training in 2-3 subject batches rather than difficulty tiers — train Python pairs first, then JavaScript, then Go. This is a form of "subject curriculum" that can help with knowledge compartmentalization.'''
    ),

    # ===================== EVALUATION METHODOLOGY (3 pairs) =====================

    (
        "ml_train1_16",
        r'''How do I evaluate a fine-tuned LoRA model properly? I trained a coding assistant and need to know if it's actually better than the base model.''',
        r'''<think>
Evaluation methodology is critical and often done wrong. The user needs to know about A/B eval (quick_eval with blind comparison), the limitations of automated code execution eval, and how to combine both approaches. I should also mention the sandbox limitation where non-Python code always scores 0.
</think>

## Evaluating Fine-Tuned LoRA Models: A/B Testing Approach

### The Gold Standard: Blind A/B Evaluation

The most reliable way to evaluate a LoRA adapter is **side-by-side blind comparison** against the base model on the same prompts:

```python
import random

def run_ab_eval(
    base_url: str,          # llama-server endpoint (no LoRA)
    lora_url: str,          # llama-server endpoint (with LoRA)
    eval_prompts: list[str],
    judge_fn=None,          # Optional automated judge
) -> dict:
    """Run blind A/B evaluation between base and fine-tuned model."""
    results = {"base_wins": 0, "lora_wins": 0, "ties": 0}

    for prompt in eval_prompts:
        # Get responses from both models
        base_response = query_model(base_url, prompt)
        lora_response = query_model(lora_url, prompt)

        # Randomize order to prevent position bias
        if random.random() > 0.5:
            response_a, response_b = base_response, lora_response
            a_is_base = True
        else:
            response_a, response_b = lora_response, base_response
            a_is_base = False

        # Judge (human or automated)
        winner = judge_fn(prompt, response_a, response_b)

        if winner == "A":
            results["base_wins" if a_is_base else "lora_wins"] += 1
        elif winner == "B":
            results["lora_wins" if a_is_base else "base_wins"] += 1
        else:
            results["ties"] += 1

    total = len(eval_prompts)
    print(f"Base wins:  {results['base_wins']}/{total}")
    print(f"LoRA wins:  {results['lora_wins']}/{total}")
    print(f"Ties:       {results['ties']}/{total}")
    print(f"LoRA win rate: {results['lora_wins']/total:.1%}")

    return results
```

### Automated Code Execution Eval (with Caveats)

You can automatically evaluate coding responses by executing them in a sandbox:

```python
import subprocess
import tempfile

def eval_code_response(code: str, test_cases: list[dict]) -> float:
    """Execute code and run test cases. Returns pass rate 0.0-1.0."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                     delete=False) as f:
        f.write(code)
        f.write("\n\n# Test cases\n")
        for tc in test_cases:
            f.write(f"assert {tc['call']} == {tc['expected']}, "
                    f"'Failed: {tc[\"call\"]}'\n")
        f.write("print('ALL TESTS PASSED')\n")
        f.flush()

        result = subprocess.run(
            ["python", f.name],
            capture_output=True, text=True, timeout=10
        )

    return 1.0 if "ALL TESTS PASSED" in result.stdout else 0.0
```

### Critical Limitation: Sandbox Language Support

A common pitfall: if your eval sandbox **only executes Python**, then non-Python pairs (JavaScript, Go, Rust, C++) will always score 0.0 regardless of quality. This creates a false signal that your model degraded on those languages when the eval methodology is the actual problem.

**Solutions:**
1. Add execution sandboxes for each language (Node.js, Go compiler, etc.)
2. Use A/B eval (no execution needed) for non-Python languages
3. Don't trust automated execution scores for languages your sandbox doesn't support

### Recommended Eval Strategy

1. **Quick A/B eval** (20 prompts, 5 minutes): Fast sanity check — does the LoRA hurt anything?
2. **Execution eval** (Python only): Automated pass rate on coding tasks
3. **Domain-specific eval**: Test your specific domain knowledge (e.g., Hive blockchain API questions)
4. **Regression check**: Run 10 general coding prompts to verify base capabilities are intact'''
    ),

    (
        "ml_train1_17",
        r'''What is skill injection for LLMs and how does it differ from fine-tuning? Can I add new capabilities without training?''',
        r'''## Skill Injection: Zero-Training Knowledge Transfer

### The Concept

Skill injection adds new capabilities to an LLM **at inference time** by injecting relevant context into the system prompt — no training required. It's essentially retrieval-augmented generation (RAG) specialized for skill/knowledge files.

### How It Works

```python
# 1. Define skill files — concise knowledge documents (~500 tokens each)
# skills/hive_sdk/SKILL.md
SKILL_CONTENT = """
# Hive Blockchain SDK
## Key Functions
- `Client(nodes=['https://api.hive.blog'])` — connect to Hive
- `client.broadcast(op)` — broadcast a transaction
- `client.get_account(name)` — fetch account data
## Common Patterns
...
"""

# 2. Route queries to relevant skills via keyword matching
def load_skills_for_query(query: str) -> str:
    """Match query to relevant skill files."""
    skills = []
    for skill in ALL_SKILLS:
        if any(kw in query.lower() for kw in skill.keywords):
            skills.append(skill.content)
    return "\n\n".join(skills)

# 3. Inject into system prompt at inference time
def build_prompt(query: str, base_system_prompt: str) -> str:
    skill_context = load_skills_for_query(query)
    if skill_context:
        return f"{base_system_prompt}\n\n{skill_context}"
    return base_system_prompt
```

### Skill Injection vs Fine-Tuning

| Aspect | Skill Injection | Fine-Tuning |
|--------|----------------|-------------|
| Training required | No | Yes (hours/days) |
| Knowledge update | Edit a text file | Retrain the model |
| Context window cost | ~500 tokens per skill | Zero at inference |
| Knowledge depth | Surface-level (API refs) | Deep (patterns, reasoning) |
| Forgetting risk | None | Catastrophic forgetting possible |
| Best for | API references, facts | Reasoning patterns, style |

### When to Use Each

**Skill injection** (zero-training):
- API documentation and function signatures
- Domain-specific facts that change frequently
- Quick prototyping before committing to fine-tuning
- Supplementing fine-tuning with updateable references

**Fine-tuning** (training required):
- Teaching reasoning patterns and problem-solving approaches
- Changing the model's output style or format
- Deep domain expertise that requires multi-step reasoning
- When context window budget is too tight for skill injection

### The Hybrid Approach (Best of Both)

Use fine-tuning for reasoning patterns and skill injection for reference data:

```python
# Fine-tune: Teach the model HOW to work with Hive blockchain
# (reasoning patterns, common architectures, debugging approaches)
training_pairs = load_hive_reasoning_pairs()

# Skill inject: Give the model WHAT the current API looks like
# (function signatures, parameter names, return types)
skill_files = load_skill_files("hive_sdk")

# At inference: Fine-tuned model + skill context
response = model.generate(
    system_prompt=BASE_PROMPT + skill_context,
    user_message=query,
)
```

This way, the fine-tuned model knows how to reason about Hive development, and the skill files provide up-to-date API details that can change without retraining.'''
    ),

    (
        "ml_train1_18",
        r'''How do I write good eval prompts for testing a fine-tuned coding assistant? My current eval always shows 100% because the questions are too easy.''',
        r'''## Writing Effective Eval Prompts for Coding Assistants

### Why Your Eval Shows 100%

If every eval prompt gets a correct response, your prompts are testing capabilities the base model already has. Good eval prompts should test the **delta** — what did fine-tuning add?

### Eval Prompt Design Framework

**Tier 1: Baseline (should pass before and after training)**
```python
BASELINE_PROMPTS = [
    "Write a Python function to reverse a string",
    "Explain what a hash map is",
]
# Purpose: Regression detection — if these fail, fine-tuning broke something
```

**Tier 2: Domain-specific (should improve after training)**
```python
DOMAIN_PROMPTS = [
    "Write a Hive blockchain custom_json operation that votes on a post",
    "Debug this async WebSocket handler for Hive streaming API",
]
# Purpose: Measure domain knowledge gain from fine-tuning
```

**Tier 3: Reasoning (tests depth of understanding)**
```python
REASONING_PROMPTS = [
    "This Hive transaction broadcasts but the custom_json never appears "
    "on-chain. What are the possible causes and how would you debug it?",
    "Design a system that monitors Hive blockchain for specific operations "
    "and triggers webhooks. Consider reliability and backpressure.",
]
# Purpose: Tests multi-step reasoning, not just API knowledge
```

### Concrete Eval Prompt Template

```python
EVAL_SUITE = [
    # Format: (prompt, category, difficulty, eval_method)

    # Regression checks
    ("Write a binary search in Python", "general", "easy", "execution"),
    ("Explain the difference between threads and processes",
     "general", "medium", "quality"),

    # Domain knowledge
    ("How do you broadcast a transfer operation using beem?",
     "domain", "medium", "quality"),

    # Edge cases and debugging
    ("This code connects to Hive but gets 'too many requests'. "
     "What's wrong?\n```python\nfor i in range(10000):\n"
     "    client.get_account('alice')\n```",
     "domain", "medium", "quality"),

    # Architecture and design
    ("Design a caching layer for Hive API calls that handles "
     "node failover and rate limiting",
     "domain", "hard", "quality"),
]
```

### Scoring Methods

```python
def score_response(prompt: str, response: str,
                   eval_method: str) -> float:
    if eval_method == "execution":
        # Extract code, run it, check test cases
        return run_code_tests(response)
    elif eval_method == "quality":
        # Use A/B comparison against base model
        base_response = get_base_response(prompt)
        return ab_compare(prompt, response, base_response)
    elif eval_method == "checklist":
        # Check for required elements in response
        return checklist_score(response, required_elements)
```

### Key Principles

1. **Test the delta**: Include prompts that the base model struggles with but your fine-tuned model should handle
2. **Include regression prompts**: Make sure fine-tuning didn't break general capabilities
3. **Mix difficulties**: 30% easy, 40% medium, 30% hard
4. **Use multiple eval methods**: Don't rely solely on code execution (sandbox limitations) or solely on quality judgments
5. **20+ prompts minimum**: Fewer than 20 gives noisy results with high variance'''
    ),

    # ===================== MODEL SERVING (2 pairs) =====================

    (
        "ml_train1_19",
        r'''I've trained a LoRA adapter and want to serve it for inference. What are my options for quantization and deployment?''',
        r'''<think>
The user needs to go from a trained LoRA adapter to a deployable inference setup. The main options are: merge+quantize to GGUF for llama.cpp/llama-server, or serve with vLLM/TGI with dynamic LoRA loading. I should cover both paths with practical commands.
</think>

## Deploying a LoRA Adapter: Quantization and Serving Options

### Option 1: Merge + GGUF Quantization (llama.cpp)

Best for: Single-GPU inference, CPU inference, edge deployment

```bash
# Step 1: Merge LoRA into base model
python -c "
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = AutoModelForCausalLM.from_pretrained(
    'Qwen/Qwen2.5-Coder-14B-Instruct',
    torch_dtype='auto',
    device_map='cpu',  # Merge on CPU to avoid VRAM issues
)
model = PeftModel.from_pretrained(base, './my-lora-adapter')
merged = model.merge_and_unload()
merged.save_pretrained('./merged-model')

tokenizer = AutoTokenizer.from_pretrained('Qwen/Qwen2.5-Coder-14B-Instruct')
tokenizer.save_pretrained('./merged-model')
"

# Step 2: Convert to GGUF
python llama.cpp/convert_hf_to_gguf.py ./merged-model \
    --outfile ./model.gguf --outtype bf16

# Step 3: Quantize to desired precision
./llama.cpp/llama-quantize ./model.bf16.gguf ./model.Q4_K_M.gguf Q4_K_M
```

**Quantization levels:**

| Quant | Size (14B) | Quality | Speed |
|-------|-----------|---------|-------|
| Q8_0 | ~15GB | Near-lossless | Baseline |
| Q6_K | ~12GB | Excellent | ~10% faster |
| Q5_K_M | ~10GB | Very good | ~20% faster |
| Q4_K_M | ~8.5GB | Good (recommended) | ~30% faster |
| Q3_K_M | ~7GB | Acceptable | ~40% faster |
| Q2_K | ~5.5GB | Noticeable degradation | ~50% faster |

**Serving with llama-server:**
```bash
llama-server \
    --model ./model.Q4_K_M.gguf \
    --host 0.0.0.0 --port 8080 \
    --n-gpu-layers 99 \         # Offload all layers to GPU
    --ctx-size 8192 \
    --parallel 2                 # Concurrent request slots
```

### Option 2: Dynamic LoRA Loading (vLLM)

Best for: Multi-LoRA serving, A/B testing, production with multiple adapters

```bash
# Serve base model with LoRA adapter loaded dynamically
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-Coder-14B-Instruct \
    --enable-lora \
    --lora-modules my-adapter=./my-lora-adapter \
    --max-loras 4 \
    --dtype bfloat16

# Query with specific LoRA
curl http://localhost:8000/v1/chat/completions \
    -d '{"model": "my-adapter", "messages": [...]}'
```

### Recommendation

- **Single adapter, max performance**: Merge + GGUF Q4_K_M with llama-server
- **Multiple adapters or A/B testing**: vLLM with dynamic LoRA loading
- **CPU-only deployment**: Merge + GGUF Q4_K_M with llama.cpp (no GPU needed, slower)'''
    ),

    (
        "ml_train1_20",
        r'''What's the difference between llama.cpp quantization formats? When should I use Q4_K_M vs Q5_K_M vs Q8_0?''',
        r'''## GGUF Quantization Format Guide

### How Quantization Works

Quantization reduces model weights from 16-bit (BF16/FP16) to lower precision (2-8 bit). Each weight takes fewer bits to store, reducing both file size and memory usage. The trade-off is precision loss — lower bits mean more rounding error in weight values.

### The K-Quant System

The "K" in Q4_K_M stands for **k-means quantization** — weights are clustered and each cluster gets its own scale factor. The suffix (S/M/L) indicates how many bits are allocated to the scale factors:

- **S (Small)**: Fewer scale bits, smaller file, more quality loss
- **M (Medium)**: Balanced — recommended default
- **L (Large)**: More scale bits, larger file, less quality loss

### Format Comparison for a 14B Model

| Format | Bits/Weight | Size | Quality vs BF16 | Use Case |
|--------|------------|------|-----------------|----------|
| BF16 | 16 | ~28GB | Reference | Development only |
| Q8_0 | 8 | ~15GB | 99.5% | When VRAM permits, quality-critical |
| Q6_K | 6.5 | ~12GB | 99% | Good balance with ample VRAM |
| Q5_K_M | 5.5 | ~10GB | 98% | Great quality, fits 16GB GPUs |
| Q4_K_M | 4.5 | ~8.5GB | 96% | Best quality/size trade-off |
| Q4_K_S | 4.25 | ~8GB | 94% | Slightly smaller Q4 |
| Q3_K_M | 3.5 | ~7GB | 90% | Tight VRAM, acceptable quality |
| Q2_K | 2.5 | ~5.5GB | 80% | Extreme compression, noticeable degradation |
| IQ4_XS | 4.25 | ~7.8GB | 95% | Importance-matrix quant, needs imatrix |

### Decision Guide

```
Available VRAM ≥ 16GB?
  └─ Yes → Q8_0 (near-lossless quality)
  └─ No
     Available VRAM ≥ 12GB?
       └─ Yes → Q5_K_M (very good quality)
       └─ No
          Available VRAM ≥ 10GB?
            └─ Yes → Q4_K_M (recommended default)
            └─ No → Q3_K_M (last resort before quality drops noticeably)
```

### Practical Impact on Code Generation

For coding tasks specifically:
- **Q8_0 to Q5_K_M**: Virtually no difference in code correctness. Syntax, logic, and API usage remain accurate.
- **Q4_K_M**: Occasional minor differences in variable naming or comment quality. Core logic remains correct. This is the sweet spot for coding assistants.
- **Q3_K_M and below**: Starts affecting complex reasoning chains. The model may produce subtly incorrect logic in multi-step algorithms. Fine for simple tasks, risky for complex ones.

### IMatrix Quantization (Advanced)

For Q4 and below, **importance matrix (imatrix) quantization** can significantly improve quality by measuring which weights matter most:

```bash
# Generate importance matrix from calibration data
./llama-imatrix -m model.bf16.gguf -f calibration.txt -o imatrix.dat

# Quantize with importance matrix
./llama-quantize --imatrix imatrix.dat \
    model.bf16.gguf model.IQ4_XS.gguf IQ4_XS
```

This tells the quantizer to preserve precision for important weights and compress unimportant ones more aggressively. The result is measurably better quality at the same file size compared to standard K-quant.'''
    ),
]
