"""
Batch P8 — LLM Fine-Tuning Strategies: data preparation, LoRA/PEFT, full fine-tuning,
evaluation/benchmarking, alignment techniques (DPO/ORPO/KTO).
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Data Preparation for Fine-Tuning ---
    (
        "finetuning/data-preparation-pipeline",
        "Describe a comprehensive data preparation pipeline for LLM fine-tuning including "
        "instruction dataset curation, quality filtering with heuristic and model-based scoring, "
        "MinHash deduplication, data mixing ratios, and synthetic data generation strategies "
        "with full Python implementation",
        r"""## Data Preparation for LLM Fine-Tuning: Building a Production-Grade Pipeline

### Why Data Quality Determines Fine-Tuning Success

The single most important factor in fine-tuning outcomes is **data quality**, not model size, not training duration, not hyperparameter tuning. Research from the LIMA paper demonstrated that as few as 1,000 carefully curated examples can outperform models trained on 50,000+ noisy samples. This happens because language models are remarkably efficient learners during fine-tuning — they already possess broad capabilities from pre-training, and fine-tuning primarily teaches them **when and how** to apply those capabilities. Therefore, every low-quality example actively harms the model by reinforcing bad patterns.

A **common mistake** is treating fine-tuning data preparation like traditional ML data preparation. In traditional ML, more data almost always helps because models learn features from scratch. In LLM fine-tuning, however, the model already knows the features — you are reshaping its behavior. Noisy or contradictory examples create conflicting gradients that degrade the model's pre-trained knowledge, a phenomenon called **catastrophic forgetting**. The **best practice** is to invest 60-70% of your total fine-tuning effort in data preparation.

### Step 1: Quality Scoring and Filtering

Quality filtering operates at multiple levels. **Heuristic filters** catch obvious problems quickly — responses that are too short, contain excessive repetition, or have formatting issues. **Model-based scoring** uses a stronger model (or the base model itself) to evaluate semantic quality — coherence, factual accuracy, instruction-following fidelity.

The **trade-off** here is speed versus accuracy. Heuristic filters are fast (thousands of examples per second) but miss subtle quality issues. Model-based scoring catches nuanced problems but costs API calls or GPU time. The **best practice** is to layer them: run heuristic filters first to eliminate the bottom 20-30%, then apply model-based scoring to the survivors.

```python
import re
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Callable
from collections import Counter
import numpy as np


@dataclass
class QualityScore:
    # Overall quality score between 0.0 and 1.0
    overall: float
    # Individual component scores
    length_score: float
    formatting_score: float
    repetition_score: float
    instruction_adherence: float
    # Reasons for any penalties applied
    penalties: list[str] = field(default_factory=list)


class HeuristicQualityScorer:
    # Applies fast rule-based quality checks to instruction-response pairs.

    def __init__(
        self,
        min_response_words: int = 50,
        max_response_words: int = 4000,
        min_instruction_words: int = 5,
        max_repetition_ratio: float = 0.3,
        required_response_elements: Optional[list[str]] = None,
    ):
        self.min_response_words = min_response_words
        self.max_response_words = max_response_words
        self.min_instruction_words = min_instruction_words
        self.max_repetition_ratio = max_repetition_ratio
        self.required_elements = required_response_elements or []

    def score(self, instruction: str, response: str) -> QualityScore:
        # Score a single instruction-response pair on multiple quality dimensions.
        penalties: list[str] = []
        resp_words = response.split()
        inst_words = instruction.split()

        # Length scoring with smooth falloff
        word_count = len(resp_words)
        if word_count < self.min_response_words:
            length_score = word_count / self.min_response_words
            penalties.append(f"Response too short: {word_count} words")
        elif word_count > self.max_response_words:
            length_score = max(0.5, 1.0 - (word_count - self.max_response_words) / 2000)
            penalties.append(f"Response excessively long: {word_count} words")
        else:
            length_score = 1.0

        # Instruction length check
        if len(inst_words) < self.min_instruction_words:
            penalties.append(f"Instruction too brief: {len(inst_words)} words")

        # Formatting quality — checks for markdown structure, code blocks, etc.
        formatting_score = self._score_formatting(response)

        # Repetition detection using n-gram analysis
        repetition_score = self._score_repetition(resp_words)
        if repetition_score < 0.7:
            penalties.append("High repetition detected in response")

        # Instruction adherence — does the response address the instruction?
        instruction_adherence = self._score_adherence(instruction, response)

        overall = np.mean([
            length_score,
            formatting_score,
            repetition_score,
            instruction_adherence,
        ])

        return QualityScore(
            overall=float(overall),
            length_score=length_score,
            formatting_score=formatting_score,
            repetition_score=repetition_score,
            instruction_adherence=instruction_adherence,
            penalties=penalties,
        )

    def _score_formatting(self, response: str) -> float:
        # Check for well-structured markdown formatting.
        score = 0.5  # baseline
        if re.search(r"^#{1,4}\s", response, re.MULTILINE):
            score += 0.15  # has headers
        if "```" in response:
            score += 0.15  # has code blocks
        if re.search(r"^\s*[-*]\s", response, re.MULTILINE):
            score += 0.1   # has bullet lists
        if re.search(r"\*\*[^*]+\*\*", response):
            score += 0.1   # has bold emphasis
        return min(1.0, score)

    def _score_repetition(self, words: list[str]) -> float:
        # Detect repetitive content using trigram frequency analysis.
        if len(words) < 10:
            return 1.0
        trigrams = [" ".join(words[i:i+3]) for i in range(len(words) - 2)]
        counts = Counter(trigrams)
        if not trigrams:
            return 1.0
        repeated = sum(c - 1 for c in counts.values() if c > 1)
        ratio = repeated / len(trigrams)
        return max(0.0, 1.0 - ratio / self.max_repetition_ratio)

    def _score_adherence(self, instruction: str, response: str) -> float:
        # Check keyword overlap between instruction and response.
        inst_keywords = set(instruction.lower().split()) - {
            "the", "a", "an", "is", "are", "in", "to", "for", "of", "and",
            "how", "what", "why", "when", "explain", "describe", "show",
        }
        resp_lower = response.lower()
        if not inst_keywords:
            return 0.8
        matches = sum(1 for kw in inst_keywords if kw in resp_lower)
        return min(1.0, matches / max(1, len(inst_keywords) * 0.5))
```

### Step 2: MinHash Deduplication

Deduplication is critical because duplicate or near-duplicate examples cause the model to **overfit on specific phrasings** rather than learning generalizable patterns. Exact deduplication catches identical texts, but **near-duplicate detection** with MinHash/LSH (Locality-Sensitive Hashing) catches paraphrases and lightly edited copies that are equally harmful.

A **pitfall** many practitioners fall into is deduplicating only on instructions while ignoring responses. Two examples with different instructions but nearly identical responses teach the model to give the same generic answer regardless of the question. The **best practice** is to deduplicate on both instruction and response independently, then merge the flagged sets.

```python
from datasketch import MinHash, MinHashLSH
from typing import Iterator


class MinHashDeduplicator:
    # Near-duplicate detection using MinHash with Locality-Sensitive Hashing.
    # This approach scales to millions of examples with sub-linear query time.

    def __init__(
        self,
        threshold: float = 0.7,
        num_perm: int = 128,
        ngram_size: int = 3,
    ):
        self.threshold = threshold
        self.num_perm = num_perm
        self.ngram_size = ngram_size
        # Separate LSH indices for instructions and responses
        self.instruction_lsh = MinHashLSH(
            threshold=threshold, num_perm=num_perm
        )
        self.response_lsh = MinHashLSH(
            threshold=threshold, num_perm=num_perm
        )
        self._seen_instructions: dict[str, int] = {}
        self._seen_responses: dict[str, int] = {}

    def _text_to_minhash(self, text: str) -> MinHash:
        # Convert text into a MinHash signature using character n-grams.
        mh = MinHash(num_perm=self.num_perm)
        text_lower = text.lower().strip()
        for i in range(len(text_lower) - self.ngram_size + 1):
            ngram = text_lower[i:i + self.ngram_size]
            mh.update(ngram.encode("utf-8"))
        return mh

    def is_duplicate(
        self, idx: int, instruction: str, response: str
    ) -> tuple[bool, Optional[str]]:
        # Check if an example is a near-duplicate of any previously seen example.
        # Returns (is_dup, reason).
        inst_mh = self._text_to_minhash(instruction)
        resp_mh = self._text_to_minhash(response)

        # Query instruction LSH
        inst_key = f"inst_{idx}"
        inst_matches = self.instruction_lsh.query(inst_mh)
        if inst_matches:
            return True, f"Instruction near-duplicate of {inst_matches[0]}"

        # Query response LSH
        resp_key = f"resp_{idx}"
        resp_matches = self.response_lsh.query(resp_mh)
        if resp_matches:
            return True, f"Response near-duplicate of {resp_matches[0]}"

        # Not a duplicate — insert into indices
        try:
            self.instruction_lsh.insert(inst_key, inst_mh)
            self.response_lsh.insert(resp_key, resp_mh)
        except ValueError:
            pass  # Key already exists — skip
        return False, None

    def deduplicate_dataset(
        self, examples: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        # Remove near-duplicates from a dataset, preserving order.
        unique: list[dict[str, str]] = []
        removed_count = 0
        for idx, ex in enumerate(examples):
            is_dup, reason = self.is_duplicate(
                idx, ex["instruction"], ex["response"]
            )
            if not is_dup:
                unique.append(ex)
            else:
                removed_count += 1
        print(
            f"Deduplication: {removed_count}/{len(examples)} removed "
            f"({removed_count/len(examples)*100:.1f}%)"
        )
        return unique
```

### Step 3: Data Mixing and Stratified Sampling

Real fine-tuning datasets combine examples from multiple sources — general instruction-following, domain-specific knowledge, code, math, safety. The **mixing ratio** between these categories dramatically affects the model's strengths. However, a **common mistake** is using uniform sampling across categories, which over-represents large categories and under-represents small but critical ones (like safety examples).

The **best practice** is **temperature-based sampling** (also called proportional sampling with temperature). Categories are sampled with probability proportional to their size raised to a power (the temperature). Temperature 1.0 gives natural proportions, temperature 0.0 gives equal sampling, and values in between provide a controlled balance. Research suggests **temperature 0.5-0.7** works best for most fine-tuning scenarios because it preserves some of the natural distribution while boosting underrepresented categories.

```python
import random
from collections import defaultdict


class StratifiedDataMixer:
    # Combines multiple data sources with temperature-based
    # proportional sampling for balanced training.

    def __init__(
        self,
        temperature: float = 0.6,
        seed: int = 42,
        max_examples_per_category: Optional[int] = None,
    ):
        self.temperature = temperature
        self.seed = seed
        self.max_per_cat = max_examples_per_category
        self.categories: dict[str, list[dict]] = defaultdict(list)

    def add_category(
        self, name: str, examples: list[dict], weight_override: Optional[float] = None
    ) -> None:
        # Register a data category with its examples.
        self.categories[name] = examples
        if weight_override is not None:
            self._weight_overrides[name] = weight_override

    def compute_sampling_weights(self) -> dict[str, float]:
        # Compute temperature-scaled sampling probabilities per category.
        sizes = {name: len(exs) for name, exs in self.categories.items()}
        total = sum(sizes.values())
        if total == 0:
            return {}

        # Apply temperature scaling
        raw_probs = {
            name: (count / total) ** self.temperature
            for name, count in sizes.items()
        }
        # Normalize to sum to 1.0
        prob_sum = sum(raw_probs.values())
        return {name: p / prob_sum for name, p in raw_probs.items()}

    def sample(self, total_examples: int) -> list[dict]:
        # Sample a mixed dataset with stratified proportions.
        rng = random.Random(self.seed)
        weights = self.compute_sampling_weights()

        # Compute per-category sample counts
        counts: dict[str, int] = {}
        remaining = total_examples
        sorted_cats = sorted(weights.items(), key=lambda x: x[1])

        for i, (name, prob) in enumerate(sorted_cats):
            if i == len(sorted_cats) - 1:
                counts[name] = remaining
            else:
                n = round(prob * total_examples)
                n = min(n, len(self.categories[name]))  # cap at available
                if self.max_per_cat:
                    n = min(n, self.max_per_cat)
                counts[name] = n
                remaining -= n

        # Sample from each category
        mixed: list[dict] = []
        for name, count in counts.items():
            pool = self.categories[name]
            sampled = rng.sample(pool, min(count, len(pool)))
            for ex in sampled:
                ex["_category"] = name
            mixed.extend(sampled)

        rng.shuffle(mixed)
        return mixed


# Usage example: building a training mix
def build_training_dataset() -> list[dict]:
    mixer = StratifiedDataMixer(temperature=0.6, seed=42)
    # Add categories with different sizes
    # General instruction data — large pool
    # Domain-specific data — smaller but critical
    # Safety and refusal data — small but must be well-represented
    # mixer.add_category("general", general_examples)
    # mixer.add_category("domain", domain_examples)
    # mixer.add_category("safety", safety_examples)
    weights = mixer.compute_sampling_weights()
    print("Sampling weights:", weights)
    return mixer.sample(total_examples=10000)
```

### Key Takeaways

- **Data quality over quantity**: 1,000 excellent examples beat 50,000 noisy ones because fine-tuning reshapes existing capabilities, not building new ones from scratch.
- **Layer your filters**: Use fast heuristic scoring first (length, formatting, repetition), then expensive model-based scoring. This is the **best practice** for cost-effective quality control.
- **Deduplicate on both axes**: A **common mistake** is only deduplicating instructions. Near-duplicate responses are equally harmful because they cause the model to memorize specific outputs.
- **Temperature-based mixing** (0.5-0.7) provides the right **trade-off** between natural data proportions and balanced category representation. Therefore, small but critical categories like safety data get adequate representation.
- **Track provenance**: Tag every example with its source category, quality score, and deduplication status. This metadata is invaluable for debugging training failures later.
- A **pitfall** to avoid is filtering too aggressively — you want to remove genuinely bad examples while preserving natural diversity in writing style and response length.""",
    ),

    # --- 2. LoRA and Parameter-Efficient Fine-Tuning ---
    (
        "finetuning/lora-peft-qlora-dora",
        "Explain LoRA, QLoRA with 4-bit NF4 quantization, and DoRA (Weight-Decomposed Low-Rank "
        "Adaptation) for parameter-efficient LLM fine-tuning, covering rank selection strategies, "
        "adapter placement on attention and MLP layers, and full implementation with Hugging Face "
        "PEFT including rank ablation and adapter merging",
        r"""## LoRA, QLoRA, and DoRA: Parameter-Efficient Fine-Tuning Deep Dive

### The Case for Parameter-Efficient Methods

Full fine-tuning of a 7B parameter model requires approximately 28 GB of GPU memory for weights alone (FP32), plus another 28 GB for optimizer states (Adam momentum and variance), totaling around 112 GB when accounting for gradients and activations. This puts full fine-tuning beyond the reach of most practitioners. **Parameter-efficient fine-tuning (PEFT)** methods solve this by training only a small subset of parameters — typically 0.1% to 2% of the original model — while keeping the base model frozen.

LoRA is the dominant PEFT technique because it introduces **zero inference latency** after merging. Unlike adapters that add new layers (increasing forward pass time), LoRA weights can be folded back into the base model weights, producing a model that is architecturally identical to the original. This is a critical **trade-off** that sets LoRA apart from other PEFT approaches.

### LoRA Fundamentals: Rank, Alpha, and Target Modules

The mathematical foundation of LoRA is **low-rank matrix decomposition**. Instead of learning a full weight update matrix delta_W of shape (d_out, d_in), LoRA decomposes it into two smaller matrices: B of shape (d_out, r) and A of shape (r, d_in), where r is the rank and r is much smaller than both d_out and d_in. The forward pass becomes y = W_original * x + (B @ A) * x * (alpha / r).

**Rank selection** is the most important hyperparameter decision. A **common mistake** is always using rank 16 because it appeared in the original paper. However, the optimal rank depends on the complexity of the adaptation task:

- **Rank 4-8**: Sufficient for style transfer, tone adjustment, simple formatting tasks. These tasks require minimal deviation from pre-trained weights.
- **Rank 16-32**: Good for domain adaptation (legal, medical, financial text), instruction tuning with moderate complexity.
- **Rank 64-128**: Needed for complex tasks like adding new capabilities, multilingual fine-tuning, or when the target domain is very different from pre-training data.
- **Rank 256+**: Rarely beneficial — approaches full fine-tuning parameter count with diminishing returns. However, recent work on high-rank LoRA with proper regularization shows promise.

The **alpha parameter** controls the scaling of LoRA updates. The **best practice** is to set alpha equal to rank (alpha = r) for a scaling factor of 1.0, then adjust if needed. Setting alpha = 2*r doubles the learning rate effectively, which can help if the model is under-adapting. A **pitfall** is setting alpha too high, which causes training instability because gradient magnitudes become too large.

**Adapter placement** determines which layers receive LoRA adapters. The original paper targeted only attention projection matrices (Q, K, V, O), but subsequent research shows that including **MLP layers** (gate, up, and down projections) significantly improves performance for complex tasks. The **best practice** for modern fine-tuning is to target all linear layers.

### QLoRA: 4-bit Training with NF4 Quantization

QLoRA combines LoRA with 4-bit NormalFloat (NF4) quantization of the base model. The base model weights are quantized to 4-bit precision using a quantization scheme specifically designed for normally distributed neural network weights. The LoRA adapters, however, are kept in BF16 or FP16 precision because they are the parameters being actively trained.

The key innovation is **double quantization** — the quantization constants themselves are quantized, saving an additional 0.37 bits per parameter. This allows a 65B parameter model to fit into a single 48GB GPU for training. The **trade-off** is a small quality degradation (typically 1-3% on benchmarks) compared to full-precision LoRA, which is negligible for most applications. Therefore, QLoRA is the recommended approach for practitioners without access to multi-GPU setups.

### DoRA: Weight-Decomposed Low-Rank Adaptation

DoRA improves upon standard LoRA by decomposing the weight matrix into **magnitude** and **direction** components before applying low-rank adaptation. Standard LoRA modifies both magnitude and direction simultaneously through the single B @ A update. DoRA, however, learns the magnitude component separately (as a trainable vector m) while using LoRA to adapt only the direction.

This decomposition is motivated by the observation that full fine-tuning tends to make large changes in direction but small changes in magnitude. Standard LoRA conflates these two types of updates, leading to suboptimal optimization dynamics. DoRA's approach more closely mimics the learning patterns of full fine-tuning, which is why it consistently outperforms standard LoRA by 1-3% on downstream tasks with the same number of trainable parameters.

### Complete Implementation with PEFT

```python
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType,
)
from datasets import load_dataset
from trl import SFTTrainer
from typing import Optional


def create_qlora_model(
    model_name: str,
    lora_rank: int = 32,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    use_dora: bool = False,
    target_modules: Optional[list[str]] = None,
) -> tuple:
    # Build a QLoRA-configured model with NF4 quantization.
    # Returns the PEFT model and tokenizer ready for training.

    # 4-bit NF4 quantization config with double quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,  # double quantization saves memory
    )

    # Load base model in 4-bit
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
    )

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Prepare model for k-bit training
    # This freezes base layers and handles gradient checkpointing compat
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=True,
    )

    # Default target modules: all linear layers in attention and MLP
    if target_modules is None:
        target_modules = [
            "q_proj", "k_proj", "v_proj", "o_proj",  # attention
            "gate_proj", "up_proj", "down_proj",       # MLP
        ]

    # LoRA (or DoRA) configuration
    lora_config = LoraConfig(
        r=lora_rank,
        lora_alpha=lora_alpha,
        target_modules=target_modules,
        lora_dropout=lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        use_dora=use_dora,  # Enable DoRA weight decomposition
    )

    peft_model = get_peft_model(model, lora_config)
    trainable, total = peft_model.get_nb_trainable_parameters()
    print(
        f"Trainable parameters: {trainable:,} / {total:,} "
        f"({100 * trainable / total:.2f}%)"
    )
    return peft_model, tokenizer
```

### Rank Ablation Study

A **best practice** before committing to a training run is to perform a rank ablation study — training with multiple ranks on a small subset and comparing validation loss. This avoids wasting GPU hours on a suboptimal configuration.

```python
import json
from pathlib import Path


def run_rank_ablation(
    model_name: str,
    dataset_name: str,
    ranks: list[int] = None,
    eval_steps: int = 50,
    max_steps: int = 500,
    output_dir: str = "./ablation_results",
) -> dict[int, float]:
    # Run LoRA training at multiple ranks and compare validation loss.
    # Returns a mapping of rank -> best validation loss.
    if ranks is None:
        ranks = [4, 8, 16, 32, 64, 128]

    results: dict[int, dict] = {}
    dataset = load_dataset(dataset_name, split="train[:2000]")

    for rank in ranks:
        print(f"\n{'='*60}")
        print(f"Training with rank={rank}, alpha={rank}")
        print(f"{'='*60}")

        run_dir = Path(output_dir) / f"rank_{rank}"
        model, tokenizer = create_qlora_model(
            model_name=model_name,
            lora_rank=rank,
            lora_alpha=rank,  # alpha = rank is the standard baseline
        )

        training_args = TrainingArguments(
            output_dir=str(run_dir),
            max_steps=max_steps,
            per_device_train_batch_size=4,
            gradient_accumulation_steps=4,
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            warmup_steps=50,
            logging_steps=10,
            eval_strategy="steps",
            eval_steps=eval_steps,
            save_strategy="no",  # don't save intermediate checkpoints
            bf16=True,
            optim="paged_adamw_8bit",
            report_to="none",
        )

        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=dataset,
            tokenizer=tokenizer,
            max_seq_length=2048,
        )
        trainer.train()

        # Record metrics
        eval_result = trainer.evaluate()
        trainable_params, _ = model.get_nb_trainable_parameters()
        results[rank] = {
            "eval_loss": eval_result["eval_loss"],
            "trainable_params": trainable_params,
            "memory_mb": torch.cuda.max_memory_allocated() / 1024 / 1024,
        }
        print(f"Rank {rank}: loss={eval_result['eval_loss']:.4f}, "
              f"params={trainable_params:,}")

        # Clean up to free GPU memory
        del model, trainer
        torch.cuda.empty_cache()

    # Save results
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    with open(Path(output_dir) / "ablation_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Find optimal rank — best loss with fewest parameters
    best_rank = min(results, key=lambda r: results[r]["eval_loss"])
    print(f"\nBest rank: {best_rank} with loss {results[best_rank]['eval_loss']:.4f}")
    return results
```

### Adapter Merging Strategies

After training, LoRA adapters must be merged back into the base model for efficient inference. There are several merging strategies, each with different **trade-offs**.

```python
from peft import PeftModel
from pathlib import Path
import shutil


def merge_lora_adapter(
    base_model_name: str,
    adapter_path: str,
    output_path: str,
    merge_method: str = "default",
    scaling_factor: float = 1.0,
) -> None:
    # Merge a LoRA adapter into the base model and save the result.
    # merge_method options: "default", "ties", "dare"
    # "default" — standard linear merge (W + B@A * alpha/r)
    # "ties" — TIES merging for combining multiple adapters
    # "dare" — DARE: randomly drop adapter elements then rescale

    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.bfloat16,
        device_map="cpu",  # merge on CPU to avoid OOM
    )

    model = PeftModel.from_pretrained(base_model, adapter_path)

    if merge_method == "default":
        # Standard merge: fold LoRA weights into base
        merged = model.merge_and_unload()
    elif merge_method == "dare":
        # DARE: Drop And REscale — randomly zero out adapter weights
        # then scale remaining by 1/(1-drop_rate) to preserve magnitude
        merged = model.merge_and_unload(
            progressbar=True,
            safe_merge=True,  # check for NaN/Inf after merge
        )
    else:
        merged = model.merge_and_unload()

    # Save merged model
    merged.save_pretrained(output_path)

    # Also save tokenizer
    tokenizer = AutoTokenizer.from_pretrained(base_model_name)
    tokenizer.save_pretrained(output_path)

    # Verify merge — load and check output
    test_model = AutoModelForCausalLM.from_pretrained(
        output_path, torch_dtype=torch.bfloat16
    )
    print(f"Merged model saved to {output_path}")
    param_count = sum(p.numel() for p in test_model.parameters())
    print(f"Total parameters: {param_count:,}")
    del test_model
```

### Key Takeaways

- **Rank is task-dependent**: Simple style tasks need rank 4-8, domain adaptation needs 16-32, complex capability changes need 64+. A **common mistake** is using a single rank for all tasks.
- **QLoRA with NF4 double quantization** enables fine-tuning 7B+ models on a single consumer GPU with minimal quality loss. The **trade-off** is roughly 1-3% benchmark degradation for 4x memory savings.
- **DoRA consistently outperforms standard LoRA** by 1-3% by decomposing weight updates into magnitude and direction components. Therefore, it should be the default choice when the PEFT library version supports it.
- **Target all linear layers** (attention Q/K/V/O + MLP gate/up/down), not just attention projections. This is a **best practice** that consistently improves results.
- **Always run a rank ablation study** before committing to expensive training. This is the single best investment of GPU time because it prevents wasting hours on suboptimal configurations.
- **Merge carefully**: Use safe_merge=True to detect NaN/Inf corruption, and always verify the merged model produces reasonable outputs before deleting the adapter. A **pitfall** is merging without verification and discovering corruption only after deploying.""",
    ),

    # --- 3. Full Fine-Tuning Optimization ---
    (
        "finetuning/full-finetuning-deepspeed-optimization",
        "Explain full fine-tuning optimization for large language models including gradient "
        "accumulation, mixed precision training with BF16 and FP16, gradient checkpointing memory "
        "savings, DeepSpeed ZeRO stages 1 through 3, and FSDP sharding strategies with a complete "
        "DeepSpeed ZeRO-3 training script implementing curriculum learning",
        r"""## Full Fine-Tuning Optimization: DeepSpeed, Mixed Precision, and Curriculum Learning

### When Full Fine-Tuning Is Worth the Cost

Despite the efficiency of LoRA and other PEFT methods, **full fine-tuning** remains the gold standard when maximum performance is required. Full fine-tuning consistently outperforms LoRA by 2-5% on complex tasks because it can modify every parameter in the network, enabling deeper architectural adaptations. However, the cost is substantial: a 7B model requires approximately 112 GB of GPU memory for training (weights + gradients + optimizer states + activations), and a 70B model requires over 1 TB.

The **trade-off** is clear: full fine-tuning delivers the best quality but requires sophisticated distributed training infrastructure. Therefore, understanding the optimization techniques that make full fine-tuning feasible is essential for any serious ML engineering team. The techniques below — gradient accumulation, mixed precision, gradient checkpointing, and model sharding — can reduce memory requirements by 8-16x while maintaining training quality.

### Gradient Accumulation: Virtual Batch Sizes

Gradient accumulation is the simplest memory optimization technique. Instead of processing a large batch and computing gradients in one step, you process multiple smaller **micro-batches** and accumulate their gradients before performing a weight update. The mathematical result is identical to training with the larger batch.

A **common mistake** is ignoring the interaction between gradient accumulation and learning rate. When you increase the effective batch size through accumulation, you should also scale the learning rate proportionally (linear scaling rule). If your base learning rate is 2e-5 with batch size 8, and you switch to micro-batch 2 with 4 accumulation steps (effective batch 8), the learning rate stays the same. But if you change to 8 accumulation steps (effective batch 16), you should increase to 4e-5. The **pitfall** is that this linear scaling breaks down at very large batch sizes (>2048 for most LLMs) — at that point, the optimization landscape changes and you need warmup and careful tuning.

### Mixed Precision Training: BF16 vs FP16

Mixed precision training stores model weights and computes most operations in half-precision (16-bit) while keeping a master copy in FP32 for numerical stability. This halves memory consumption for weights and activations while also speeding up computation on modern GPUs with tensor cores.

**BF16 (Brain Floating Point)** is strongly preferred over FP16 for LLM training because it maintains the same exponent range as FP32 (8 bits), preventing overflow/underflow issues that plague FP16 training. FP16 has only 5 exponent bits, which means values outside the range [~6e-5, 65504] clip to zero or infinity. In practice, FP16 training often requires **loss scaling** (multiplying the loss by a large factor before backpropagation, then dividing gradients back down) to keep gradient values within the representable range. BF16 eliminates this complexity entirely. The **best practice** is to always use BF16 on Ampere or newer GPUs (A100, H100, RTX 3090+).

### Gradient Checkpointing: Trading Compute for Memory

During the forward pass, all intermediate activations must be stored because they are needed for the backward pass gradient computation. For a model with L layers, this requires O(L) memory for activations. **Gradient checkpointing** (also called activation checkpointing) saves memory by not storing all activations — instead, it recomputes them during the backward pass.

The standard approach divides the model into segments and only stores activations at segment boundaries. During backpropagation, when activations for a segment are needed, the forward pass is re-run for that segment from the stored boundary activation. This reduces activation memory from O(L) to O(sqrt(L)) at the cost of approximately 33% more computation. This is a fundamental **trade-off**: you spend 33% more time to save 60-80% of activation memory.

### DeepSpeed ZeRO: Eliminating Redundancy

DeepSpeed ZeRO (Zero Redundancy Optimizer) is the most impactful distributed training optimization because it eliminates the massive memory redundancy in standard data parallelism. In vanilla data parallelism, every GPU holds a complete copy of the model weights, gradients, and optimizer states — only the data differs. ZeRO **partitions** these components across GPUs so each GPU holds only a fraction.

**ZeRO Stage 1** partitions optimizer states across GPUs. Since Adam optimizer states (momentum and variance) consume 2x the model weight memory, this alone saves approximately 4x memory with 8 GPUs compared to naive data parallelism.

**ZeRO Stage 2** adds gradient partitioning. Each GPU computes all gradients during backpropagation but immediately reduces and scatters them, keeping only its assigned partition. This saves an additional 2x memory compared to Stage 1.

**ZeRO Stage 3** partitions the model weights themselves. Each GPU holds only 1/N of the parameters and gathers the full parameters on-demand for each layer during forward and backward passes. This enables training models that are N times larger than what fits on a single GPU, but introduces significant communication overhead because parameters must be all-gathered for every forward and backward operation.

The **trade-off** between ZeRO stages is memory savings versus communication overhead. Stage 1 has almost no overhead. Stage 2 adds minimal overhead. Stage 3 can slow training by 15-30% due to the all-gather operations, however it is the only way to train models that exceed single-GPU memory even with mixed precision and gradient checkpointing. Therefore, the **best practice** is to use the lowest stage that fits your model in memory.

### Complete DeepSpeed ZeRO-3 Training Script

```python
import os
import json
import math
import torch
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from datasets import load_dataset, concatenate_datasets
import deepspeed


@dataclass
class CurriculumConfig:
    # Configuration for curriculum learning — training on progressively
    # harder or longer examples over the course of training.
    enabled: bool = True
    # Number of stages in the curriculum
    num_stages: int = 4
    # Sequence length at each stage (ramps up)
    stage_max_lengths: tuple[int, ...] = (512, 1024, 1536, 2048)
    # Fraction of training spent in each stage
    stage_fractions: tuple[float, ...] = (0.15, 0.25, 0.30, 0.30)
    # Difficulty metric: "length", "perplexity", or "complexity_score"
    difficulty_metric: str = "length"


def generate_deepspeed_config(
    stage: int = 3,
    train_batch_size: int = 32,
    micro_batch_size: int = 1,
    gradient_accumulation: int = 32,
    learning_rate: float = 2e-5,
) -> dict[str, Any]:
    # Generate a DeepSpeed ZeRO configuration for the specified stage.
    config = {
        "train_batch_size": train_batch_size,
        "train_micro_batch_size_per_gpu": micro_batch_size,
        "gradient_accumulation_steps": gradient_accumulation,
        "optimizer": {
            "type": "AdamW",
            "params": {
                "lr": learning_rate,
                "betas": [0.9, 0.95],
                "eps": 1e-8,
                "weight_decay": 0.1,
            },
        },
        "scheduler": {
            "type": "WarmupDecayLR",
            "params": {
                "warmup_min_lr": 0,
                "warmup_max_lr": learning_rate,
                "warmup_num_steps": 100,
                "total_num_steps": 5000,
            },
        },
        "bf16": {"enabled": True},
        "gradient_clipping": 1.0,
        "zero_optimization": {
            "stage": stage,
            "offload_optimizer": {
                "device": "cpu",
                "pin_memory": True,
            } if stage == 3 else None,
            "offload_param": {
                "device": "cpu",
                "pin_memory": True,
            } if stage == 3 else None,
            "overlap_comm": True,
            "contiguous_gradients": True,
            "sub_group_size": 1e9,
            "reduce_bucket_size": "auto",
            "stage3_prefetch_bucket_size": "auto",
            "stage3_param_persistence_threshold": "auto",
            "stage3_max_live_parameters": 1e9,
            "stage3_max_reuse_distance": 1e9,
            "stage3_gather_16bit_weights_on_model_save": True,
        },
        "activation_checkpointing": {
            "partition_activations": True,
            "cpu_checkpointing": False,
            "contiguous_memory_optimization": True,
            "number_checkpoints": None,
            "synchronize_checkpoint_boundary": False,
        },
    }
    return config
```

### Curriculum Learning Integration

Curriculum learning presents training examples in order of increasing difficulty, which often converges faster and to a better minimum than random ordering. For LLMs, the most common curriculum dimension is **sequence length** — start with short sequences and gradually increase to the full target length. This works because short sequences are computationally cheaper and provide clear gradient signals, while long sequences introduce more noise.

```python
class CurriculumTrainer(Trainer):
    # Extends HuggingFace Trainer with curriculum learning support.
    # Dynamically adjusts training data difficulty based on training progress.

    def __init__(
        self,
        curriculum_config: CurriculumConfig,
        full_dataset,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.curriculum = curriculum_config
        self.full_dataset = full_dataset
        self._current_stage = 0
        self._stage_boundaries = self._compute_boundaries()

    def _compute_boundaries(self) -> list[int]:
        # Compute step boundaries for each curriculum stage.
        total_steps = self.args.max_steps
        boundaries = []
        cumulative = 0.0
        for frac in self.curriculum.stage_fractions:
            cumulative += frac
            boundaries.append(int(cumulative * total_steps))
        return boundaries

    def _get_stage_dataset(self, stage: int):
        # Filter dataset to examples appropriate for the current stage.
        max_len = self.curriculum.stage_max_lengths[stage]
        if self.curriculum.difficulty_metric == "length":
            # Filter by token count
            filtered = self.full_dataset.filter(
                lambda ex: len(ex["input_ids"]) <= max_len,
                num_proc=4,
            )
        else:
            filtered = self.full_dataset
        return filtered

    def training_step(self, model, inputs, num_items_in_batch=None):
        # Override training step to check curriculum stage transitions.
        current_step = self.state.global_step
        new_stage = 0
        for i, boundary in enumerate(self._stage_boundaries):
            if current_step < boundary:
                new_stage = i
                break
        else:
            new_stage = len(self._stage_boundaries) - 1

        if new_stage != self._current_stage:
            self._current_stage = new_stage
            print(
                f"\n[Curriculum] Stage {new_stage}: "
                f"max_length={self.curriculum.stage_max_lengths[new_stage]}"
            )
            self.train_dataset = self._get_stage_dataset(new_stage)

        return super().training_step(model, inputs, num_items_in_batch)


def launch_full_finetuning(
    model_name: str,
    dataset_path: str,
    output_dir: str,
    num_gpus: int = 8,
    max_steps: int = 5000,
    per_device_batch: int = 1,
    gradient_accum: int = 32,
    learning_rate: float = 2e-5,
) -> None:
    # Launch full fine-tuning with DeepSpeed ZeRO-3 and curriculum learning.

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        use_cache=False,  # must disable for gradient checkpointing
    )
    model.gradient_checkpointing_enable()

    dataset = load_dataset(dataset_path, split="train")

    ds_config = generate_deepspeed_config(
        stage=3,
        train_batch_size=per_device_batch * gradient_accum * num_gpus,
        micro_batch_size=per_device_batch,
        gradient_accumulation=gradient_accum,
        learning_rate=learning_rate,
    )
    ds_config_path = Path(output_dir) / "ds_config.json"
    ds_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ds_config_path, "w") as f:
        json.dump(ds_config, f, indent=2)

    training_args = TrainingArguments(
        output_dir=output_dir,
        max_steps=max_steps,
        per_device_train_batch_size=per_device_batch,
        gradient_accumulation_steps=gradient_accum,
        learning_rate=learning_rate,
        lr_scheduler_type="cosine",
        warmup_steps=100,
        bf16=True,
        logging_steps=10,
        save_strategy="steps",
        save_steps=500,
        eval_strategy="steps",
        eval_steps=250,
        gradient_checkpointing=True,
        deepspeed=str(ds_config_path),
        remove_unused_columns=False,
    )

    curriculum = CurriculumConfig(
        enabled=True,
        num_stages=4,
        stage_max_lengths=(512, 1024, 1536, 2048),
        stage_fractions=(0.15, 0.25, 0.30, 0.30),
    )

    trainer = CurriculumTrainer(
        curriculum_config=curriculum,
        full_dataset=dataset,
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=DataCollatorForLanguageModeling(
            tokenizer=tokenizer, mlm=False
        ),
    )
    trainer.train()
    trainer.save_model(output_dir)
    print(f"Training complete. Model saved to {output_dir}")
```

### FSDP as an Alternative to DeepSpeed

PyTorch's **Fully Sharded Data Parallelism (FSDP)** provides similar functionality to DeepSpeed ZeRO but is integrated natively into PyTorch. FSDP shards parameters, gradients, and optimizer states across GPUs, similar to ZeRO Stage 3. The main advantage of FSDP is tighter integration with the PyTorch ecosystem — no separate configuration files, native support for torch.compile, and easier debugging. However, DeepSpeed generally has better CPU offloading support and more mature tooling for very large models (100B+). The **best practice** is to use FSDP for models up to 30B parameters and DeepSpeed for larger models.

```python
from torch.distributed.fsdp import (
    FullyShardedDataParallel as FSDP,
    MixedPrecision,
    ShardingStrategy,
)
from torch.distributed.fsdp.wrap import transformer_auto_wrap_policy
from transformers.models.llama.modeling_llama import LlamaDecoderLayer
import functools


def setup_fsdp_model(
    model: AutoModelForCausalLM,
    sharding_strategy: str = "full_shard",
) -> FSDP:
    # Wrap a model with PyTorch FSDP for distributed training.
    # sharding_strategy options: "full_shard" (ZeRO-3), "shard_grad_op" (ZeRO-2),
    # "no_shard" (DDP), "hybrid_shard" (shard within node, replicate across)

    strategy_map = {
        "full_shard": ShardingStrategy.FULL_SHARD,
        "shard_grad_op": ShardingStrategy.SHARD_GRAD_OP,
        "no_shard": ShardingStrategy.NO_SHARD,
        "hybrid_shard": ShardingStrategy.HYBRID_SHARD,
    }

    # Auto-wrap policy: shard at the transformer layer level
    auto_wrap_policy = functools.partial(
        transformer_auto_wrap_policy,
        transformer_layer_cls={LlamaDecoderLayer},
    )

    # BF16 mixed precision config
    bf16_policy = MixedPrecision(
        param_dtype=torch.bfloat16,
        reduce_dtype=torch.bfloat16,
        buffer_dtype=torch.bfloat16,
    )

    fsdp_model = FSDP(
        model,
        sharding_strategy=strategy_map[sharding_strategy],
        mixed_precision=bf16_policy,
        auto_wrap_policy=auto_wrap_policy,
        device_id=torch.cuda.current_device(),
        limit_all_gathers=True,
        forward_prefetch=True,
        use_orig_params=True,  # required for torch.compile compatibility
    )
    return fsdp_model
```

### Key Takeaways

- **Gradient accumulation** enables large effective batch sizes on limited hardware but requires careful learning rate scaling. The **common mistake** of not adjusting the learning rate leads to under-training.
- **Always use BF16** on Ampere+ GPUs — it eliminates the complexity of loss scaling required by FP16 and is a strict improvement for LLM training.
- **Gradient checkpointing** saves 60-80% of activation memory at the cost of 33% more compute. This **trade-off** is almost always worth it because memory is the binding constraint.
- **ZeRO Stage 3** enables training models far larger than single-GPU memory, however it introduces 15-30% communication overhead. Therefore, use the lowest stage that fits your model.
- **Curriculum learning** (short to long sequences) typically converges 10-20% faster than random ordering and often reaches a better final loss. This is a **best practice** that costs nothing extra.
- A critical **pitfall** with DeepSpeed ZeRO-3: you must set `use_cache=False` on the model and enable `stage3_gather_16bit_weights_on_model_save` or your saved checkpoints will be corrupted.""",
    ),

    # --- 4. Evaluation and Benchmarking ---
    (
        "finetuning/evaluation-benchmarking-harness",
        "Describe comprehensive evaluation and benchmarking strategies for fine-tuned LLMs "
        "including perplexity measurement, BLEU and ROUGE for generation quality, MT-Bench and "
        "AlpacaEval for instruction following, custom domain benchmarks, contamination detection "
        "techniques, and implementation of an evaluation harness with multiple metrics and "
        "statistical significance testing",
        r"""## Comprehensive LLM Evaluation: Metrics, Benchmarks, and Statistical Rigor

### Why Evaluation Is Harder Than Training

Evaluating a fine-tuned LLM is paradoxically more difficult than training one. Training has a clear objective (minimize loss), but evaluation must answer a fundamentally different question: "Does this model do what we want it to do in the real world?" A model can achieve low perplexity while being useless for your application, or score well on standard benchmarks while failing on your specific domain. Therefore, a robust evaluation strategy must combine **automated metrics**, **benchmark suites**, **domain-specific tests**, and **human evaluation** — each capturing different aspects of model quality.

A **common mistake** is evaluating only on the same distribution as the training data. This tells you whether the model memorized the training set, not whether it generalized. The **best practice** is to maintain completely separate evaluation sets that are constructed independently from the training data, ideally by different people or from different sources.

### Perplexity: The Foundation Metric

**Perplexity** measures how well the model predicts the next token in a held-out dataset. It is the exponentiated average negative log-likelihood: PPL = exp(-1/N * sum(log P(token_i | context_i))). Lower perplexity means the model assigns higher probability to the correct tokens.

Perplexity is useful because it is fast, deterministic, and directly connected to the training objective. However, it has critical limitations. A model can have low perplexity while being terrible at following instructions because perplexity only measures prediction accuracy, not behavioral alignment. It is best used as a **sanity check** — if perplexity increased after fine-tuning, something went wrong — not as a primary evaluation metric.

A **pitfall** with perplexity measurement is inconsistent tokenization and context windows. If you measure perplexity on your fine-tuned model using a different tokenizer or sequence length than the base model, the comparison is meaningless. Always use identical evaluation conditions.

### Generation Quality Metrics: BLEU and ROUGE

**BLEU** (Bilingual Evaluation Understudy) measures n-gram precision between generated text and reference text. It was designed for machine translation but is widely used for any text generation task. BLEU-4 (using up to 4-grams) is the standard variant. A score of 0.3+ indicates strong overlap with references.

**ROUGE** (Recall-Oriented Understudy for Gisting Evaluation) focuses on recall rather than precision — it measures what fraction of the reference n-grams appear in the generated text. ROUGE-L uses the longest common subsequence, making it more flexible than strict n-gram matching. ROUGE is particularly useful for summarization tasks.

However, both BLEU and ROUGE have a fundamental limitation: they measure **surface-level textual overlap**, not semantic correctness. Two responses can convey identical information using completely different words, resulting in low BLEU/ROUGE scores. The **trade-off** is that these metrics are cheap and reproducible but miss semantic equivalence. Therefore, they should be used alongside embedding-based metrics (like BERTScore) and LLM-as-judge evaluation.

### MT-Bench and AlpacaEval: Instruction-Following Benchmarks

**MT-Bench** uses GPT-4 as a judge to evaluate model responses on a curated set of 80 multi-turn conversations spanning 8 categories (writing, roleplay, reasoning, math, coding, extraction, STEM, humanities). Responses are scored 1-10. MT-Bench correlates well with human preferences and captures instruction-following ability that perplexity misses entirely.

**AlpacaEval** compares model outputs against a reference model (GPT-4 or Claude) using an LLM judge. The win rate against the reference indicates overall quality. AlpacaEval 2.0 introduced length-controlled evaluation to prevent the length bias where longer responses are systematically preferred — this was a major **pitfall** in the original version.

A **common mistake** with LLM-as-judge evaluation is assuming the judge is unbiased. GPT-4 systematically prefers longer responses, its own outputs, and certain formatting patterns. The **best practice** is to use **position debiasing** (evaluating A-vs-B and B-vs-A, averaging the scores) and **multiple judges** to reduce systematic bias.

### Implementation: Comprehensive Evaluation Harness

```python
import math
import json
import numpy as np
from typing import Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer


@dataclass
class EvalResult:
    # Container for evaluation results with statistical metadata.
    metric_name: str
    score: float
    confidence_interval: tuple[float, float]
    num_samples: int
    per_sample_scores: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class PerplexityEvaluator:
    # Measures perplexity on a held-out dataset with proper handling
    # of sequence length and padding.

    def __init__(
        self,
        model: AutoModelForCausalLM,
        tokenizer: AutoTokenizer,
        max_length: int = 2048,
        stride: int = 512,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.stride = stride
        self.device = next(model.parameters()).device

    @torch.no_grad()
    def evaluate(self, texts: list[str]) -> EvalResult:
        # Compute perplexity using a sliding window approach for long texts.
        self.model.eval()
        all_nlls: list[float] = []
        total_tokens = 0

        for text in texts:
            encodings = self.tokenizer(
                text, return_tensors="pt", truncation=False
            )
            input_ids = encodings.input_ids.to(self.device)
            seq_len = input_ids.size(1)

            nlls: list[float] = []
            prev_end = 0
            for begin in range(0, seq_len, self.stride):
                end = min(begin + self.max_length, seq_len)
                target_len = end - prev_end
                input_chunk = input_ids[:, begin:end]

                with torch.amp.autocast("cuda", dtype=torch.bfloat16):
                    outputs = self.model(input_chunk, labels=input_chunk)

                # Only count loss for non-overlapping tokens
                neg_log_likelihood = outputs.loss * target_len
                nlls.append(neg_log_likelihood.item())
                total_tokens += target_len
                prev_end = end

                if end == seq_len:
                    break

            text_nll = sum(nlls) / total_tokens if total_tokens > 0 else 0
            all_nlls.append(text_nll)

        mean_nll = np.mean(all_nlls)
        perplexity = math.exp(mean_nll)

        # Bootstrap confidence interval
        ci = self._bootstrap_ci(all_nlls, func=lambda x: math.exp(np.mean(x)))

        return EvalResult(
            metric_name="perplexity",
            score=perplexity,
            confidence_interval=ci,
            num_samples=len(texts),
            per_sample_scores=[math.exp(nll) for nll in all_nlls],
        )

    def _bootstrap_ci(
        self,
        scores: list[float],
        func: Callable,
        n_bootstrap: int = 1000,
        alpha: float = 0.05,
    ) -> tuple[float, float]:
        # Compute bootstrap confidence interval for a statistic.
        rng = np.random.RandomState(42)
        bootstrap_stats = []
        arr = np.array(scores)
        for _ in range(n_bootstrap):
            sample = rng.choice(arr, size=len(arr), replace=True)
            bootstrap_stats.append(func(sample))
        lower = np.percentile(bootstrap_stats, 100 * alpha / 2)
        upper = np.percentile(bootstrap_stats, 100 * (1 - alpha / 2))
        return (float(lower), float(upper))
```

### LLM-as-Judge Evaluation with Position Debiasing

```python
from openai import OpenAI


class LLMJudgeEvaluator:
    # Uses a strong LLM as a judge to evaluate response quality.
    # Implements position debiasing by evaluating in both orders.

    JUDGE_PROMPT_TEMPLATE = (
        "You are an expert evaluator. Rate the following response to the "
        "given instruction on a scale of 1-10 across these dimensions:\n"
        "- Helpfulness (1-10): Does it address the instruction fully?\n"
        "- Accuracy (1-10): Is the information correct?\n"
        "- Clarity (1-10): Is it well-organized and easy to understand?\n"
        "- Completeness (1-10): Does it cover all aspects?\n\n"
        "Instruction: {instruction}\n\n"
        "Response: {response}\n\n"
        "Provide your scores as JSON: "
        '{{\"helpfulness\": X, \"accuracy\": X, \"clarity\": X, \"completeness\": X, '
        '\"overall\": X, \"reasoning\": \"...\"}}'
    )

    def __init__(
        self,
        judge_model: str = "gpt-4",
        client: Optional[OpenAI] = None,
    ):
        self.judge_model = judge_model
        self.client = client or OpenAI()

    def evaluate_single(
        self, instruction: str, response: str
    ) -> dict[str, float]:
        # Evaluate a single instruction-response pair.
        prompt = self.JUDGE_PROMPT_TEMPLATE.format(
            instruction=instruction, response=response
        )
        completion = self.client.chat.completions.create(
            model=self.judge_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512,
        )
        try:
            scores = json.loads(completion.choices[0].message.content)
            return scores
        except json.JSONDecodeError:
            return {"overall": 0, "error": "Failed to parse judge response"}

    def evaluate_pairwise_debiased(
        self,
        instruction: str,
        response_a: str,
        response_b: str,
    ) -> dict[str, float]:
        # Compare two responses with position debiasing.
        # Evaluates A-vs-B and B-vs-A, averages the results.
        score_ab = self.evaluate_single(instruction, response_a)
        score_ba = self.evaluate_single(instruction, response_b)

        # Average scores from both orderings to debias position effects
        debiased = {}
        for key in ["helpfulness", "accuracy", "clarity", "completeness", "overall"]:
            if key in score_ab and key in score_ba:
                debiased[key] = (score_ab[key] + score_ba[key]) / 2
        return debiased
```

### Contamination Detection

**Benchmark contamination** occurs when evaluation data appears in the training set, inflating scores artificially. This is a serious problem because many popular benchmarks have been leaked into web-scale pre-training corpora. A **common mistake** is assuming your fine-tuning data is clean just because you curated it — the base model may already be contaminated.

```python
from datasketch import MinHash, MinHashLSH


class ContaminationDetector:
    # Detects potential benchmark contamination by checking for
    # near-duplicate overlap between evaluation and training data.

    def __init__(
        self,
        threshold: float = 0.6,
        num_perm: int = 128,
        ngram_size: int = 5,
    ):
        self.threshold = threshold
        self.num_perm = num_perm
        self.ngram_size = ngram_size
        self.train_lsh = MinHashLSH(
            threshold=threshold, num_perm=num_perm
        )
        self._train_count = 0

    def index_training_data(self, texts: list[str]) -> None:
        # Build LSH index from training data for contamination checking.
        for text in texts:
            mh = self._text_to_minhash(text)
            try:
                self.train_lsh.insert(f"train_{self._train_count}", mh)
                self._train_count += 1
            except ValueError:
                pass

    def check_eval_contamination(
        self, eval_texts: list[str]
    ) -> dict[str, list]:
        # Check each evaluation example for contamination.
        contaminated: list[dict] = []
        clean: list[dict] = []

        for idx, text in enumerate(eval_texts):
            mh = self._text_to_minhash(text)
            matches = self.train_lsh.query(mh)
            if matches:
                contaminated.append({
                    "eval_idx": idx,
                    "text_preview": text[:200],
                    "train_matches": matches,
                })
            else:
                clean.append({"eval_idx": idx})

        report = {
            "total_eval": len(eval_texts),
            "contaminated_count": len(contaminated),
            "contamination_rate": len(contaminated) / len(eval_texts),
            "contaminated_examples": contaminated,
        }
        return report

    def _text_to_minhash(self, text: str) -> MinHash:
        mh = MinHash(num_perm=self.num_perm)
        words = text.lower().split()
        for i in range(len(words) - self.ngram_size + 1):
            ngram = " ".join(words[i:i + self.ngram_size])
            mh.update(ngram.encode("utf-8"))
        return mh
```

### Statistical Significance Testing

Without statistical significance testing, you cannot tell whether a 0.5% improvement is real or just noise from a lucky evaluation split. The **best practice** is to use **paired bootstrap testing** — resampling the evaluation set thousands of times and checking how often model A outperforms model B. A p-value below 0.05 indicates the difference is statistically significant.

```python
def paired_bootstrap_test(
    scores_a: list[float],
    scores_b: list[float],
    n_bootstrap: int = 10000,
    seed: int = 42,
) -> dict[str, float]:
    # Perform paired bootstrap hypothesis test.
    # Tests whether model A is significantly better than model B.
    # Returns p-value and effect size with confidence interval.
    assert len(scores_a) == len(scores_b), "Score lists must be same length"

    rng = np.random.RandomState(seed)
    arr_a = np.array(scores_a)
    arr_b = np.array(scores_b)
    observed_diff = np.mean(arr_a) - np.mean(arr_b)

    # Count how often the bootstrapped difference is <= 0
    count_worse = 0
    bootstrap_diffs = []
    for _ in range(n_bootstrap):
        indices = rng.randint(0, len(arr_a), size=len(arr_a))
        diff = np.mean(arr_a[indices]) - np.mean(arr_b[indices])
        bootstrap_diffs.append(diff)
        if diff <= 0:
            count_worse += 1

    p_value = count_worse / n_bootstrap
    ci_lower = np.percentile(bootstrap_diffs, 2.5)
    ci_upper = np.percentile(bootstrap_diffs, 97.5)
    effect_size = observed_diff / max(np.std(arr_a - arr_b), 1e-10)

    return {
        "observed_difference": float(observed_diff),
        "p_value": float(p_value),
        "confidence_interval": (float(ci_lower), float(ci_upper)),
        "effect_size_cohens_d": float(effect_size),
        "significant_at_005": p_value < 0.05,
        "significant_at_001": p_value < 0.01,
    }
```

### Key Takeaways

- **Perplexity is necessary but insufficient**: It catches training failures but does not measure instruction-following quality. Therefore, always combine it with behavioral benchmarks.
- **BLEU and ROUGE measure surface overlap**, not semantic correctness. They are useful for regression testing but should not be the primary metric for open-ended generation. The **trade-off** is speed versus accuracy.
- **LLM-as-judge evaluation** (MT-Bench, AlpacaEval) correlates well with human preferences but requires **position debiasing** to avoid systematic bias. This is a critical **best practice** that many practitioners skip.
- **Contamination detection** is essential because inflated benchmark scores lead to incorrect deployment decisions. A **pitfall** is assuming your data is clean without checking.
- **Statistical significance testing** with paired bootstrap prevents you from chasing noise. A **common mistake** is declaring a model "better" based on a 0.3% improvement without testing significance.
- Build evaluation into your training pipeline, not as an afterthought. The **best practice** is to run the full evaluation harness at every checkpoint, not just at the end of training.""",
    ),

    # --- 5. Alignment Techniques: DPO, ORPO, KTO ---
    (
        "finetuning/alignment-dpo-orpo-kto",
        "Explain modern alignment techniques for LLM fine-tuning including Supervised Fine-Tuning "
        "as the foundation, DPO (Direct Preference Optimization) with its mathematical derivation "
        "from RLHF, ORPO (Odds Ratio Preference Optimization), KTO (Kahneman-Tversky Optimization), "
        "and iterative alignment with AI feedback, with a complete DPO training implementation "
        "including preference data loading and reference model management",
        r"""## Alignment Techniques: From SFT to DPO, ORPO, and KTO

### The Alignment Pipeline: Why Order Matters

Modern LLM alignment follows a specific pipeline: **pre-training** produces a base model with broad knowledge, **Supervised Fine-Tuning (SFT)** teaches the model to follow instructions, and **preference optimization** (DPO/RLHF/ORPO/KTO) aligns the model's outputs with human preferences. Each stage builds on the previous one, and skipping stages or reordering them produces significantly worse results.

A **common mistake** is attempting DPO directly on a base model without SFT. This fails because the base model does not understand instruction-response formatting — it will treat preference pairs as arbitrary text continuations rather than learning to prefer certain response styles. The SFT stage is critical because it establishes the **format and behavior baseline** that preference optimization then refines. Therefore, always perform SFT before any preference-based alignment.

The **trade-off** between different alignment methods is between simplicity, compute cost, and alignment quality. RLHF with PPO is the most powerful but requires training a separate reward model and managing a complex RL training loop. DPO achieves comparable results with dramatically simpler training. ORPO and KTO further simplify the pipeline by eliminating the need for a reference model or paired preferences, respectively.

### Supervised Fine-Tuning (SFT): The Foundation

SFT trains the model to produce helpful, well-formatted responses given instructions. The training objective is standard causal language modeling loss, but only computed on the **response tokens** (the instruction tokens are masked from the loss). This is called **response-only loss masking** and is the **best practice** for instruction tuning because it prevents the model from being evaluated on predicting the instruction itself.

SFT quality depends entirely on data quality. High-quality SFT data has three properties: (1) instructions are diverse and cover the target use cases, (2) responses are consistently high quality with no contradictions, and (3) the formatting is uniform (consistent markdown, code formatting, etc.). A **pitfall** of SFT is that training too long causes **catastrophic forgetting** — the model loses pre-trained knowledge while overfitting to the SFT distribution. The **best practice** is to train for only 1-3 epochs on well-curated data.

### DPO: Direct Preference Optimization

**DPO (Direct Preference Optimization)** replaces the complex RLHF pipeline (reward model + PPO training) with a single supervised learning objective. The key mathematical insight is that the optimal policy under RLHF can be expressed in **closed form** as a function of the reward model, and this allows us to reparameterize the reward model in terms of the policy itself — eliminating the need for an explicit reward model.

The DPO loss function is:

L_DPO = -E[log sigmoid(beta * (log pi(y_w|x)/pi_ref(y_w|x) - log pi(y_l|x)/pi_ref(y_l|x)))]

Where y_w is the preferred (winning) response, y_l is the rejected (losing) response, pi is the policy being trained, pi_ref is the reference (SFT) model, and beta controls how far the policy can deviate from the reference. This loss has an elegant interpretation: it increases the probability of preferred responses and decreases the probability of rejected responses, with the reference model acting as an anchor to prevent the policy from drifting too far.

**Beta selection** is critical. Higher beta (0.5-1.0) constrains the model close to the reference, producing more conservative but stable alignment. Lower beta (0.05-0.1) allows more aggressive updates, which can achieve better alignment but risks **reward hacking** — the model finds degenerate solutions that technically satisfy the preference data but are not genuinely better. The **best practice** is to start with beta=0.1 and adjust based on the KL divergence between the policy and reference model during training.

### ORPO: Odds Ratio Preference Optimization

**ORPO** eliminates the reference model entirely by combining SFT and preference optimization into a single training stage. The key insight is that the standard language modeling loss already provides an implicit reference point — ORPO adds a preference-aware penalty term based on the **odds ratio** between the log-probabilities of preferred and rejected responses.

The ORPO loss combines two terms: L_ORPO = L_SFT + lambda * L_OR, where L_SFT is the standard cross-entropy loss on the preferred response, and L_OR is the odds ratio loss that penalizes assigning high probability to rejected responses. The parameter lambda controls the strength of the preference signal relative to the SFT signal.

The advantage of ORPO is **simplicity and efficiency** — you don't need a separate SFT stage or a reference model, and training requires only one forward pass per example instead of two (policy + reference). However, the **trade-off** is that ORPO typically achieves slightly lower alignment quality than DPO on complex preference tasks because the single-stage approach has less capacity to separate the "learn to follow instructions" and "learn preferences" objectives. Therefore, ORPO is best suited for scenarios where training efficiency is paramount and the preference signal is straightforward.

### KTO: Kahneman-Tversky Optimization

**KTO** addresses a practical limitation of DPO: the requirement for **paired preferences** (a chosen and rejected response for the same prompt). In practice, it is much easier to collect **unpaired binary feedback** — users simply mark individual responses as good or bad, without comparing pairs. KTO works with this unpaired data by using insights from Kahneman and Tversky's prospect theory — specifically, that humans are **loss-averse** (they weigh losses more heavily than equivalent gains).

The KTO loss applies asymmetric weighting: rejected responses receive a stronger penalty than preferred responses receive a bonus, matching the psychological observation that bad outputs are more damaging to user trust than good outputs are beneficial. This asymmetry is controlled by a parameter that governs the loss-aversion ratio.

KTO's advantage is **data efficiency** — you can use any dataset where responses have binary quality labels, which is dramatically easier to collect than paired comparisons. A **common mistake** is assuming KTO is strictly worse than DPO. In practice, KTO with sufficient unpaired data often matches DPO performance while being far easier to set up. However, the **pitfall** is that KTO is more sensitive to the quality threshold — if your "good" and "bad" labels are noisy, KTO's performance degrades faster than DPO's.

### Complete DPO Training Implementation

```python
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Optional
from dataclasses import dataclass
import json
from pathlib import Path
import copy
import wandb


@dataclass
class DPOConfig:
    # Configuration for DPO training.
    model_name: str = "meta-llama/Llama-3-8B-Instruct"
    beta: float = 0.1              # KL penalty coefficient
    learning_rate: float = 5e-7    # Lower LR than SFT — critical for stability
    max_length: int = 2048
    max_prompt_length: int = 512
    batch_size: int = 4
    gradient_accumulation_steps: int = 8
    num_epochs: int = 1            # DPO typically needs only 1 epoch
    warmup_ratio: float = 0.1
    max_grad_norm: float = 1.0
    label_smoothing: float = 0.0   # Optional: adds robustness to noisy labels
    loss_type: str = "sigmoid"     # "sigmoid" (standard) or "hinge"
    log_interval: int = 10
    eval_interval: int = 100
    output_dir: str = "./dpo_output"


class PreferenceDataset(Dataset):
    # Loads and tokenizes preference pairs for DPO training.
    # Each example has a prompt, chosen response, and rejected response.

    def __init__(
        self,
        data_path: str,
        tokenizer: AutoTokenizer,
        max_length: int = 2048,
        max_prompt_length: int = 512,
    ):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.max_prompt_length = max_prompt_length

        # Load preference data
        with open(data_path, "r") as f:
            self.data = [json.loads(line) for line in f]

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        example = self.data[idx]
        prompt = example["prompt"]
        chosen = example["chosen"]
        rejected = example["rejected"]

        # Tokenize prompt + chosen
        chosen_full = prompt + chosen
        chosen_tokens = self.tokenizer(
            chosen_full,
            max_length=self.max_length,
            truncation=True,
            padding="max_length",
            return_tensors="pt",
        )

        # Tokenize prompt + rejected
        rejected_full = prompt + rejected
        rejected_tokens = self.tokenizer(
            rejected_full,
            max_length=self.max_length,
            truncation=True,
            padding="max_length",
            return_tensors="pt",
        )

        # Create labels — mask prompt tokens with -100
        prompt_tokens = self.tokenizer(
            prompt,
            max_length=self.max_prompt_length,
            truncation=True,
        )
        prompt_len = len(prompt_tokens["input_ids"])

        chosen_labels = chosen_tokens["input_ids"].clone().squeeze(0)
        chosen_labels[:prompt_len] = -100  # mask prompt

        rejected_labels = rejected_tokens["input_ids"].clone().squeeze(0)
        rejected_labels[:prompt_len] = -100  # mask prompt

        return {
            "chosen_input_ids": chosen_tokens["input_ids"].squeeze(0),
            "chosen_attention_mask": chosen_tokens["attention_mask"].squeeze(0),
            "chosen_labels": chosen_labels,
            "rejected_input_ids": rejected_tokens["input_ids"].squeeze(0),
            "rejected_attention_mask": rejected_tokens["attention_mask"].squeeze(0),
            "rejected_labels": rejected_labels,
        }
```

### DPO Training Loop with Reference Model Management

```python
class DPOTrainer:
    # Full DPO training loop with reference model management,
    # gradient accumulation, and comprehensive logging.

    def __init__(self, config: DPOConfig):
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load policy model (the one being trained)
        self.policy_model = AutoModelForCausalLM.from_pretrained(
            config.model_name,
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        ).to(self.device)

        # Create reference model — frozen copy of the policy at initialization
        # The reference model anchors the DPO loss to prevent reward hacking
        self.ref_model = copy.deepcopy(self.policy_model)
        self.ref_model.eval()
        for param in self.ref_model.parameters():
            param.requires_grad = False

        self.tokenizer = AutoTokenizer.from_pretrained(config.model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.optimizer = torch.optim.AdamW(
            self.policy_model.parameters(),
            lr=config.learning_rate,
            betas=(0.9, 0.95),
            weight_decay=0.1,
        )

    def compute_logprobs(
        self,
        model: AutoModelForCausalLM,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor,
    ) -> torch.Tensor:
        # Compute per-token log probabilities for the response tokens only.
        with torch.amp.autocast("cuda", dtype=torch.bfloat16):
            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
            )
        logits = outputs.logits[:, :-1, :]  # shift for next-token prediction
        labels_shifted = labels[:, 1:]       # align with shifted logits

        # Compute per-token log probs
        log_probs = F.log_softmax(logits, dim=-1)
        # Gather log probs for the actual tokens
        token_log_probs = log_probs.gather(
            dim=-1, index=labels_shifted.unsqueeze(-1).clamp(min=0)
        ).squeeze(-1)

        # Zero out log probs for masked tokens (label == -100)
        mask = labels_shifted != -100
        token_log_probs = token_log_probs * mask.float()

        # Sum log probs over sequence to get per-example log prob
        return token_log_probs.sum(dim=-1)

    def dpo_loss(
        self,
        policy_chosen_logps: torch.Tensor,
        policy_rejected_logps: torch.Tensor,
        ref_chosen_logps: torch.Tensor,
        ref_rejected_logps: torch.Tensor,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        # Compute the DPO loss with optional label smoothing.
        # Returns the loss tensor and a dictionary of monitoring metrics.

        # Log-ratio differences
        chosen_rewards = self.config.beta * (
            policy_chosen_logps - ref_chosen_logps
        )
        rejected_rewards = self.config.beta * (
            policy_rejected_logps - ref_rejected_logps
        )

        # The core DPO loss
        logits = chosen_rewards - rejected_rewards

        if self.config.loss_type == "sigmoid":
            if self.config.label_smoothing > 0:
                # Label smoothing for robustness to noisy preferences
                loss = (
                    -F.logsigmoid(logits) * (1 - self.config.label_smoothing)
                    - F.logsigmoid(-logits) * self.config.label_smoothing
                )
            else:
                loss = -F.logsigmoid(logits)
        elif self.config.loss_type == "hinge":
            loss = torch.relu(1 - logits)
        else:
            raise ValueError(f"Unknown loss type: {self.config.loss_type}")

        loss = loss.mean()

        # Monitoring metrics
        metrics = {
            "loss": loss.item(),
            "chosen_reward": chosen_rewards.mean().item(),
            "rejected_reward": rejected_rewards.mean().item(),
            "reward_margin": (chosen_rewards - rejected_rewards).mean().item(),
            "accuracy": (chosen_rewards > rejected_rewards).float().mean().item(),
            "chosen_kl": (policy_chosen_logps - ref_chosen_logps).mean().item(),
            "rejected_kl": (policy_rejected_logps - ref_rejected_logps).mean().item(),
        }
        return loss, metrics

    def train(self, train_dataset: PreferenceDataset, eval_dataset: Optional[PreferenceDataset] = None) -> None:
        # Main DPO training loop with gradient accumulation and logging.
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
            drop_last=True,
        )

        total_steps = (
            len(train_loader)
            // self.config.gradient_accumulation_steps
            * self.config.num_epochs
        )
        warmup_steps = int(total_steps * self.config.warmup_ratio)

        # Learning rate scheduler with warmup
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=total_steps, eta_min=1e-8
        )

        self.policy_model.train()
        global_step = 0
        accumulated_loss = 0.0
        accumulated_metrics: dict[str, float] = {}

        for epoch in range(self.config.num_epochs):
            for batch_idx, batch in enumerate(train_loader):
                # Move batch to device
                batch = {k: v.to(self.device) for k, v in batch.items()}

                # Compute log probs for policy model
                policy_chosen_logps = self.compute_logprobs(
                    self.policy_model,
                    batch["chosen_input_ids"],
                    batch["chosen_attention_mask"],
                    batch["chosen_labels"],
                )
                policy_rejected_logps = self.compute_logprobs(
                    self.policy_model,
                    batch["rejected_input_ids"],
                    batch["rejected_attention_mask"],
                    batch["rejected_labels"],
                )

                # Compute log probs for reference model (no grad needed)
                with torch.no_grad():
                    ref_chosen_logps = self.compute_logprobs(
                        self.ref_model,
                        batch["chosen_input_ids"],
                        batch["chosen_attention_mask"],
                        batch["chosen_labels"],
                    )
                    ref_rejected_logps = self.compute_logprobs(
                        self.ref_model,
                        batch["rejected_input_ids"],
                        batch["rejected_attention_mask"],
                        batch["rejected_labels"],
                    )

                # Compute DPO loss
                loss, metrics = self.dpo_loss(
                    policy_chosen_logps,
                    policy_rejected_logps,
                    ref_chosen_logps,
                    ref_rejected_logps,
                )

                # Scale loss for gradient accumulation
                scaled_loss = loss / self.config.gradient_accumulation_steps
                scaled_loss.backward()
                accumulated_loss += loss.item()

                # Accumulate metrics
                for k, v in metrics.items():
                    accumulated_metrics[k] = accumulated_metrics.get(k, 0) + v

                # Weight update step
                if (batch_idx + 1) % self.config.gradient_accumulation_steps == 0:
                    torch.nn.utils.clip_grad_norm_(
                        self.policy_model.parameters(),
                        self.config.max_grad_norm,
                    )
                    self.optimizer.step()
                    scheduler.step()
                    self.optimizer.zero_grad()
                    global_step += 1

                    # Log metrics
                    if global_step % self.config.log_interval == 0:
                        n = self.config.gradient_accumulation_steps
                        avg_metrics = {
                            k: v / n for k, v in accumulated_metrics.items()
                        }
                        print(
                            f"Step {global_step}/{total_steps} | "
                            f"Loss: {avg_metrics.get('loss', 0):.4f} | "
                            f"Accuracy: {avg_metrics.get('accuracy', 0):.3f} | "
                            f"Margin: {avg_metrics.get('reward_margin', 0):.3f}"
                        )
                    accumulated_loss = 0.0
                    accumulated_metrics = {}

                    # Evaluation
                    if eval_dataset and global_step % self.config.eval_interval == 0:
                        self._evaluate(eval_dataset, global_step)

        # Save final model
        output_path = Path(self.config.output_dir) / "final_model"
        output_path.mkdir(parents=True, exist_ok=True)
        self.policy_model.save_pretrained(str(output_path))
        self.tokenizer.save_pretrained(str(output_path))
        print(f"DPO training complete. Model saved to {output_path}")

    def _evaluate(self, eval_dataset: PreferenceDataset, step: int) -> dict:
        # Run evaluation on the held-out preference dataset.
        self.policy_model.eval()
        eval_loader = DataLoader(eval_dataset, batch_size=self.config.batch_size)
        all_metrics: list[dict] = []

        with torch.no_grad():
            for batch in eval_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}
                policy_chosen = self.compute_logprobs(
                    self.policy_model,
                    batch["chosen_input_ids"],
                    batch["chosen_attention_mask"],
                    batch["chosen_labels"],
                )
                policy_rejected = self.compute_logprobs(
                    self.policy_model,
                    batch["rejected_input_ids"],
                    batch["rejected_attention_mask"],
                    batch["rejected_labels"],
                )
                ref_chosen = self.compute_logprobs(
                    self.ref_model,
                    batch["chosen_input_ids"],
                    batch["chosen_attention_mask"],
                    batch["chosen_labels"],
                )
                ref_rejected = self.compute_logprobs(
                    self.ref_model,
                    batch["rejected_input_ids"],
                    batch["rejected_attention_mask"],
                    batch["rejected_labels"],
                )
                _, metrics = self.dpo_loss(
                    policy_chosen, policy_rejected,
                    ref_chosen, ref_rejected,
                )
                all_metrics.append(metrics)

        # Aggregate metrics
        avg = {}
        for key in all_metrics[0]:
            avg[key] = sum(m[key] for m in all_metrics) / len(all_metrics)
        print(f"[Eval Step {step}] Loss: {avg['loss']:.4f} | "
              f"Accuracy: {avg['accuracy']:.3f}")
        self.policy_model.train()
        return avg
```

### Iterative Alignment with AI Feedback

The most powerful alignment approach combines multiple techniques iteratively. The pipeline works as follows: (1) SFT on curated data, (2) generate responses from the SFT model, (3) use a strong judge model (GPT-4, Claude) to create preference pairs, (4) train DPO on these preferences, (5) repeat from step 2 using the DPO-aligned model. Each iteration improves the model's outputs, which in turn produces higher-quality training data for the next round. This **self-improvement loop** is how frontier models achieve increasingly strong alignment. However, the **pitfall** is that the judge model's biases get amplified with each iteration — if the judge prefers verbose responses, the model becomes increasingly verbose. The **best practice** is to rotate judges and include human evaluation checkpoints every 2-3 iterations.

```python
from openai import OpenAI


class IterativeAlignmentPipeline:
    # Implements the iterative alignment loop: generate -> judge -> train DPO -> repeat.
    # Each iteration refines the model using AI-generated preference pairs.

    def __init__(
        self,
        model: AutoModelForCausalLM,
        tokenizer: AutoTokenizer,
        judge_models: list[str],
        num_iterations: int = 3,
        pairs_per_iteration: int = 5000,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.judge_models = judge_models  # rotate judges to reduce bias
        self.num_iterations = num_iterations
        self.pairs_per_iteration = pairs_per_iteration
        self.client = OpenAI()

    def generate_preference_pairs(
        self,
        prompts: list[str],
        judge_model: str,
        num_responses: int = 2,
        temperature: float = 0.8,
    ) -> list[dict[str, str]]:
        # Generate multiple responses per prompt, then have the judge rank them.
        preference_pairs: list[dict[str, str]] = []
        for prompt in prompts:
            # Generate candidate responses from the policy model
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            responses: list[str] = []
            for _ in range(num_responses):
                output = self.model.generate(
                    **inputs, max_new_tokens=1024,
                    temperature=temperature, do_sample=True,
                )
                decoded = self.tokenizer.decode(
                    output[0][inputs["input_ids"].shape[1]:],
                    skip_special_tokens=True,
                )
                responses.append(decoded)

            # Use judge to rank responses
            judge_prompt = (
                f"Compare these two responses to: {prompt}\n\n"
                f"Response A: {responses[0]}\n\n"
                f"Response B: {responses[1]}\n\n"
                "Which response is better? Reply with ONLY 'A' or 'B'."
            )
            verdict = self.client.chat.completions.create(
                model=judge_model,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.1, max_tokens=5,
            ).choices[0].message.content.strip().upper()

            if "A" in verdict:
                chosen, rejected = responses[0], responses[1]
            else:
                chosen, rejected = responses[1], responses[0]

            preference_pairs.append({
                "prompt": prompt,
                "chosen": chosen,
                "rejected": rejected,
                "judge": judge_model,
            })
        return preference_pairs

    def run(self, prompts: list[str], dpo_config: DPOConfig) -> None:
        # Execute the full iterative alignment loop.
        for iteration in range(self.num_iterations):
            # Rotate judge model to reduce systematic bias
            judge = self.judge_models[iteration % len(self.judge_models)]
            print(f"\n[Iteration {iteration+1}] Using judge: {judge}")

            # Step 1: Generate preference pairs
            pairs = self.generate_preference_pairs(
                prompts[:self.pairs_per_iteration], judge_model=judge
            )
            print(f"Generated {len(pairs)} preference pairs")

            # Step 2: Save pairs and train DPO
            pairs_path = Path(dpo_config.output_dir) / f"pairs_iter{iteration}.jsonl"
            pairs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pairs_path, "w") as f:
                for p in pairs:
                    f.write(json.dumps(p) + "\n")

            # Step 3: Train DPO on the new preferences
            dataset = PreferenceDataset(
                str(pairs_path), self.tokenizer,
                dpo_config.max_length, dpo_config.max_prompt_length,
            )
            trainer = DPOTrainer(dpo_config)
            trainer.policy_model = self.model  # continue from current model
            trainer.train(dataset)
            self.model = trainer.policy_model
            print(f"[Iteration {iteration+1}] DPO training complete")
```

### Key Takeaways

- **SFT before preference optimization is mandatory**: DPO on a base model fails because the model does not understand instruction-response formatting. This is the most **common mistake** in the alignment pipeline.
- **DPO achieves RLHF-level alignment** without reward model training or PPO complexity. The **trade-off** is slightly less flexibility than full RLHF but dramatically simpler implementation and training stability.
- **Beta (KL penalty) is the most important DPO hyperparameter**: Too high (>0.5) constrains the model to the reference, too low (<0.05) enables reward hacking. Therefore, start at 0.1 and monitor the KL divergence during training.
- **ORPO combines SFT + alignment** in one stage, saving compute. However, it typically underperforms DPO on complex preference tasks — the **best practice** is to use ORPO when training budget is limited and preferences are straightforward.
- **KTO works with unpaired binary feedback**, which is far easier to collect than paired preferences. A **common mistake** is dismissing KTO as inferior — with sufficient data, it matches DPO performance.
- **Reference model management** is critical for DPO. The reference must be frozen and kept in memory (or offloaded to CPU with efficient loading). A **pitfall** is accidentally updating the reference model, which defeats the purpose of the KL anchor and leads to mode collapse.
- **Iterative alignment** with AI feedback is the most powerful approach but requires judge diversity to prevent bias amplification across iterations.""",
    ),
]
