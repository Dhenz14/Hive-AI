"""Local LoRA training on 15GB VRAM — practical QLoRA pipeline for self-improvement."""

PAIRS = [
    (
        "self-improvement/qlora-15gb",
        "Show the complete QLoRA training pipeline that fits in 15GB VRAM: loading a model in 4-bit, configuring LoRA adapters, training on self-generated data, merging adapters, and exporting back to GGUF for inference.",
        """## QLoRA Training Pipeline for <=15GB VRAM

This is the practical training script that makes self-improvement possible
on consumer hardware. Every step is optimized for memory.

```python
import torch
import json
from pathlib import Path
from dataclasses import dataclass
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    BitsAndBytesConfig, TrainingArguments,
)
from peft import LoraConfig, get_peft_model, PeftModel
from trl import SFTTrainer, DataCollatorForCompletionOnlyLM
from datasets import Dataset


@dataclass
class LoRATrainConfig:
    \"\"\"Configuration for QLoRA training on consumer GPU.

    Memory budget for 7B model:
    - Base model (4-bit): ~4GB
    - LoRA adapters: ~100MB
    - Optimizer states: ~2GB
    - Activations (gradient checkpointing): ~2-4GB
    - Total: ~8-10GB (fits in 15GB with room for KV cache)
    \"\"\"
    model_name: str = "Qwen/Qwen2.5-7B"
    data_path: str = "self_training_data/latest.jsonl"
    output_dir: str = "lora_adapters/latest"

    # LoRA hyperparameters
    lora_r: int = 16              # Rank (8-64, higher = more capacity)
    lora_alpha: int = 32          # Scaling factor (usually 2*r)
    lora_dropout: float = 0.05   # Regularization
    target_modules: list = None   # Auto-detect if None

    # Training hyperparameters
    learning_rate: float = 2e-4
    num_epochs: int = 3
    batch_size: int = 1           # 1 for VRAM savings
    gradient_accumulation: int = 8  # Effective batch = 8
    max_seq_length: int = 2048
    warmup_ratio: float = 0.03

    # Memory optimizations
    use_4bit: bool = True
    gradient_checkpointing: bool = True
    use_flash_attention: bool = True
    bf16: bool = True


def load_model_for_training(config: LoRATrainConfig):
    \"\"\"Load model in 4-bit with LoRA adapters.\"\"\"
    # 4-bit quantization config
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",        # NormalFloat4 (best for LLMs)
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,    # Quantize the quantization constants
    )

    model = AutoModelForCausalLM.from_pretrained(
        config.model_name,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2" if config.use_flash_attention else "sdpa",
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Find target modules automatically
    target_modules = config.target_modules
    if target_modules is None:
        # Common patterns for different architectures
        target_modules = find_linear_modules(model)

    # Configure LoRA
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    # Output: trainable params: 13,107,200 || all params: 3,800,000,000
    # || trainable%: 0.3449

    if config.gradient_checkpointing:
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )

    return model, tokenizer


def find_linear_modules(model) -> list[str]:
    \"\"\"Auto-detect linear layers for LoRA targeting.\"\"\"
    linear_modules = set()
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            # Get the module name without the full path
            parts = name.split(".")
            linear_modules.add(parts[-1])

    # Remove output head (lm_head) — don't apply LoRA there
    linear_modules.discard("lm_head")
    return list(linear_modules)


def prepare_dataset(data_path: str, tokenizer,
                     max_length: int = 2048) -> Dataset:
    \"\"\"Load self-generated training data into HF Dataset.\"\"\"
    records = []
    with open(data_path) as f:
        for line in f:
            item = json.loads(line)
            # Format as instruction-following
            text = format_training_example(
                item["instruction"], item["output"],
                tokenizer,
            )
            records.append({"text": text})

    dataset = Dataset.from_list(records)
    return dataset


def format_training_example(instruction: str, output: str,
                              tokenizer) -> str:
    \"\"\"Format as chat template for training.\"\"\"
    messages = [
        {"role": "user", "content": instruction},
        {"role": "assistant", "content": output},
    ]
    # Use the model's native chat template
    return tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False
    )


def train(config: LoRATrainConfig):
    \"\"\"Run the full training pipeline.\"\"\"
    print(f"Loading model: {config.model_name}")
    model, tokenizer = load_model_for_training(config)

    print(f"Preparing dataset: {config.data_path}")
    dataset = prepare_dataset(config.data_path, tokenizer,
                                config.max_seq_length)

    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation,
        learning_rate=config.learning_rate,
        warmup_ratio=config.warmup_ratio,
        lr_scheduler_type="cosine",
        bf16=config.bf16,
        logging_steps=10,
        save_strategy="epoch",
        optim="paged_adamw_8bit",    # 8-bit optimizer saves ~1GB
        max_grad_norm=0.3,
        group_by_length=True,        # Batch similar lengths together
        report_to="none",
        gradient_checkpointing=config.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )

    # Response-only training: only compute loss on assistant tokens
    response_template = "<|im_start|>assistant"
    collator = DataCollatorForCompletionOnlyLM(
        response_template=response_template,
        tokenizer=tokenizer,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=collator,
        max_seq_length=config.max_seq_length,
        packing=True,   # Pack multiple short examples per sequence
    )

    print("Starting training...")
    trainer.train()
    trainer.save_model(config.output_dir)
    tokenizer.save_pretrained(config.output_dir)
    print(f"LoRA adapter saved to: {config.output_dir}")


def merge_and_export(base_model: str, lora_path: str,
                      output_path: str):
    \"\"\"Merge LoRA into base model and export for inference.\"\"\"
    print("Loading base model for merge...")
    model = AutoModelForCausalLM.from_pretrained(
        base_model, torch_dtype=torch.bfloat16, device_map="cpu",
    )
    model = PeftModel.from_pretrained(model, lora_path)

    print("Merging LoRA weights...")
    model = model.merge_and_unload()

    print(f"Saving merged model to {output_path}...")
    model.save_pretrained(output_path)
    AutoTokenizer.from_pretrained(base_model).save_pretrained(output_path)

    print("Converting to GGUF (run llama.cpp convert)...")
    print(f"  python convert_hf_to_gguf.py {output_path}")
    print(f"  llama-quantize {output_path}/model.gguf "
          f"{output_path}/model-Q4_K_M.gguf Q4_K_M")


# VRAM usage breakdown for 7B model:
# +---------------------------------+----------+
# | Component                       | VRAM     |
# +---------------------------------+----------+
# | Base model (NF4 quantized)      | ~3.5 GB  |
# | LoRA adapters (r=16)            | ~0.1 GB  |
# | Optimizer (paged AdamW 8-bit)   | ~1.5 GB  |
# | Gradients + activations (GC)    | ~3.0 GB  |
# | KV cache + overhead             | ~1.0 GB  |
# +---------------------------------+----------+
# | TOTAL                           | ~9.1 GB  |
# +---------------------------------+----------+
# Fits comfortably in 15GB with room for seq_len=2048


if __name__ == "__main__":
    config = LoRATrainConfig(
        model_name="Qwen/Qwen2.5-7B",
        data_path="self_training_data/latest.jsonl",
        output_dir="lora_adapters/cycle_1",
    )
    train(config)
```

### Memory Optimization Checklist

1. **4-bit quantization** (NF4) — 7B model fits in ~3.5GB instead of 14GB
2. **Gradient checkpointing** — trade compute for memory; ~60% memory reduction
3. **Paged AdamW 8-bit** — optimizer states in 8-bit; saves ~1GB
4. **Gradient accumulation** — batch_size=1 with accumulation=8; same as batch=8
5. **bf16 compute** — half-precision activations and gradients
6. **Response-only loss** — don't waste compute on instruction tokens
7. **Packing** — fit multiple short examples in one sequence; no wasted padding"""
    ),
    (
        "self-improvement/lora-merge-cycle",
        "Show the LoRA merge cycling strategy: train LoRA, merge into base, re-quantize, train new LoRA on improved base. How to avoid catastrophic forgetting while stacking improvements.",
        """## LoRA Merge Cycling: Stacking Improvements Without Forgetting

Each training cycle produces a LoRA adapter. To keep improving, you need
to merge it into the base model and start fresh. But naive merging can
cause catastrophic forgetting. Here's how to do it right.

```python
import json
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass
class MergeCycleState:
    cycle: int
    base_model_path: str
    current_gguf_path: str
    eval_scores: list[float]
    merged_adapters: list[str]


class LoRAMergeCycler:
    \"\"\"Safely merge LoRA adapters and cycle for continuous improvement.

    The cycle:
    1. Train LoRA on current base model
    2. Evaluate LoRA model vs base model
    3. If improved: merge LoRA into base
    4. Re-quantize to GGUF for inference
    5. Repeat with new base

    Anti-forgetting strategies:
    - Always include replay data from previous cycles
    - Evaluate on held-out benchmark before merging
    - Keep rollback checkpoints
    - Gradual merge with scaling factor
    \"\"\"

    def __init__(self, initial_base: str, workspace: str = "merge_workspace"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.state = MergeCycleState(
            cycle=0,
            base_model_path=initial_base,
            current_gguf_path="",
            eval_scores=[],
            merged_adapters=[],
        )
        self.replay_buffer_path = self.workspace / "replay_buffer.jsonl"

    def should_merge(self, base_score: float, lora_score: float,
                       min_improvement: float = 0.02) -> bool:
        \"\"\"Only merge if LoRA genuinely improves over base.\"\"\"
        improvement = lora_score - base_score
        print(f"  Base score: {base_score:.3f}")
        print(f"  LoRA score: {lora_score:.3f}")
        print(f"  Improvement: {improvement:+.3f}")

        if improvement < min_improvement:
            print("  SKIP: Improvement too small, keeping base")
            return False

        # Check for regression on previous capabilities
        if self.state.eval_scores:
            prev_best = max(self.state.eval_scores)
            if lora_score < prev_best * 0.95:
                print(f"  SKIP: Regression from previous best ({prev_best:.3f})")
                return False

        return True

    def merge_with_scaling(self, base_path: str, lora_path: str,
                             output_path: str, merge_ratio: float = 0.8):
        \"\"\"Merge LoRA with a scaling factor to reduce forgetting.

        merge_ratio < 1.0 means partial merge — keeps some of the
        base model's original weights, reducing catastrophic forgetting.
        \"\"\"
        import torch
        from transformers import AutoModelForCausalLM
        from peft import PeftModel

        model = AutoModelForCausalLM.from_pretrained(
            base_path, torch_dtype=torch.bfloat16, device_map="cpu"
        )
        peft_model = PeftModel.from_pretrained(model, lora_path)

        if merge_ratio < 1.0:
            # Scale LoRA weights before merging
            for name, param in peft_model.named_parameters():
                if "lora_" in name:
                    param.data *= merge_ratio

        merged = peft_model.merge_and_unload()
        merged.save_pretrained(output_path)
        print(f"  Merged with ratio {merge_ratio} -> {output_path}")

    def add_to_replay_buffer(self, training_data_path: str,
                                keep_ratio: float = 0.3):
        \"\"\"Keep a fraction of each cycle's training data for replay.

        Replay buffer prevents catastrophic forgetting by mixing
        old successful solutions into new training batches.
        \"\"\"
        new_data = []
        with open(training_data_path) as f:
            for line in f:
                new_data.append(json.loads(line))

        # Sample a subset for replay
        import random
        n_keep = max(1, int(len(new_data) * keep_ratio))
        # Keep highest-scoring pairs
        new_data.sort(key=lambda x: x.get("score", 0), reverse=True)
        replay_samples = new_data[:n_keep]

        # Append to replay buffer
        with open(self.replay_buffer_path, "a") as f:
            for sample in replay_samples:
                sample["source_cycle"] = self.state.cycle
                f.write(json.dumps(sample) + "\\n")

    def prepare_training_data(self, new_data_path: str,
                                output_path: str,
                                replay_ratio: float = 0.2):
        \"\"\"Mix new data with replay buffer for anti-forgetting.\"\"\"
        new_data = []
        with open(new_data_path) as f:
            new_data = [json.loads(line) for line in f]

        replay_data = []
        if self.replay_buffer_path.exists():
            with open(self.replay_buffer_path) as f:
                replay_data = [json.loads(line) for line in f]

        # Mix: 80% new, 20% replay
        import random
        n_replay = int(len(new_data) * replay_ratio)
        if replay_data and n_replay > 0:
            replay_sample = random.sample(
                replay_data, min(n_replay, len(replay_data))
            )
        else:
            replay_sample = []

        combined = new_data + replay_sample
        random.shuffle(combined)

        with open(output_path, "w") as f:
            for item in combined:
                f.write(json.dumps(item) + "\\n")

        print(f"  Training data: {len(new_data)} new + "
              f"{len(replay_sample)} replay = {len(combined)} total")

    def convert_to_gguf(self, model_path: str,
                          quant_type: str = "Q4_K_M") -> str:
        \"\"\"Convert merged model to GGUF for inference.\"\"\"
        gguf_path = f"{model_path}/model-{quant_type}.gguf"

        # Step 1: Convert HF to GGUF
        subprocess.run([
            "python3", "llama.cpp/convert_hf_to_gguf.py",
            model_path, "--outtype", "f16",
        ], check=True)

        # Step 2: Quantize
        subprocess.run([
            "llama.cpp/llama-quantize",
            f"{model_path}/model-f16.gguf",
            gguf_path, quant_type,
        ], check=True)

        # Cleanup F16 intermediate
        Path(f"{model_path}/model-f16.gguf").unlink(missing_ok=True)

        return gguf_path

    def run_cycle(self, training_data_path: str,
                    eval_fn, train_fn) -> bool:
        \"\"\"Execute one complete merge cycle.\"\"\"
        print(f"\\n=== Merge Cycle {self.state.cycle} ===")

        # Prepare mixed training data (new + replay)
        mixed_path = self.workspace / "mixed_training.jsonl"
        self.prepare_training_data(training_data_path, str(mixed_path))

        # Train LoRA
        lora_path = str(self.workspace / f"lora_cycle_{self.state.cycle}")
        train_fn(self.state.base_model_path, str(mixed_path), lora_path)

        # Evaluate
        base_score = eval_fn(self.state.base_model_path)
        lora_score = eval_fn(self.state.base_model_path, lora_path)

        if not self.should_merge(base_score, lora_score):
            return False

        # Merge with scaling
        merged_path = str(self.workspace / f"merged_cycle_{self.state.cycle}")
        self.merge_with_scaling(
            self.state.base_model_path, lora_path, merged_path,
            merge_ratio=0.85,
        )

        # Add to replay buffer
        self.add_to_replay_buffer(training_data_path)

        # Convert to GGUF
        gguf_path = self.convert_to_gguf(merged_path)

        # Update state
        self.state.base_model_path = merged_path
        self.state.current_gguf_path = gguf_path
        self.state.eval_scores.append(lora_score)
        self.state.merged_adapters.append(lora_path)
        self.state.cycle += 1

        # Save state for recovery
        state_path = self.workspace / "cycle_state.json"
        with open(state_path, "w") as f:
            json.dump(vars(self.state), f, indent=2)

        print(f"  Cycle complete. New GGUF: {gguf_path}")
        return True
```

### Anti-Forgetting Strategies

| Strategy | How It Works | Cost |
|----------|-------------|------|
| **Replay buffer** | Mix 20% old data in each cycle | +20% training time |
| **Merge scaling** | Merge at 85% instead of 100% | Slightly less improvement |
| **Eval gate** | Only merge if score improves | May skip cycles |
| **Regression check** | Block merge if below previous best | Conservative |
| **Gradual scaling** | 0.5 -> 0.7 -> 0.85 -> 1.0 over cycles | Slow start |

### The Improvement Curve

```
Score
 0.9 |                          ●
 0.8 |              ●     ●
 0.7 |        ●
 0.6 |  ●
 0.5 |●
     +--+--+--+--+--+--+--+---> Cycle
     0  1  2  3  4  5  6  7

Each cycle: practice -> filter quality -> train LoRA -> evaluate -> merge
```"""
    ),
    (
        "self-improvement/novel-code-generation",
        "Show how to train an AI to write novel code — not just reproduce known patterns, but create new algorithms, combine ideas creatively, and solve problems that have no standard solution.",
        """## Training for Novel Code Generation

Standard training teaches the model to reproduce patterns. To generate
truly novel code, we need to train on CREATIVE problem-solving:
combining known techniques in new ways, inventing new approaches,
and evaluating ideas the model has never seen.

```python
import random
import json
from dataclasses import dataclass


class NoveltyTrainer:
    \"\"\"Train the model to create new things, not just reproduce.\"\"\"

    def __init__(self, model_fn):
        self.model = model_fn
        self.known_solutions: dict[str, list[str]] = {}

    def generate_combination_problem(self) -> dict:
        \"\"\"Combine two unrelated concepts into a new problem.

        'What if we combined a binary search tree with a message queue?'
        'What if we used gradient descent to optimize a cache eviction policy?'
        \"\"\"
        concepts_a = [
            "binary search tree", "hash map", "priority queue",
            "bloom filter", "skip list", "trie", "B-tree",
            "ring buffer", "segment tree", "disjoint set",
        ]
        concepts_b = [
            "message queue", "rate limiter", "cache",
            "load balancer", "circuit breaker", "connection pool",
            "event loop", "scheduler", "state machine", "logger",
        ]

        a = random.choice(concepts_a)
        b = random.choice(concepts_b)

        prompt = f\"\"\"Create a novel data structure or algorithm that combines
the properties of a {a} with the functionality of a {b}.

Requirements:
1. Explain what problem this hybrid solves that neither alone can
2. Design the API (what methods does it expose?)
3. Implement it in Python with clear code
4. Show a usage example with a real scenario
5. Analyze the time/space complexity

Be creative — this combination may not exist yet. Think about what
properties of {a} would benefit {b} and vice versa.\"\"\"

        response = self.model(prompt)
        return {
            "instruction": prompt,
            "response": response,
            "type": "combination",
            "concepts": [a, b],
        }

    def generate_constraint_problem(self) -> dict:
        \"\"\"Add unusual constraints that force novel solutions.

        Standard algorithms break under weird constraints.
        The model must invent new approaches.
        \"\"\"
        base_problems = [
            "Sort an array",
            "Find the shortest path in a graph",
            "Implement a key-value store",
            "Build a task scheduler",
            "Create a text search engine",
        ]
        weird_constraints = [
            "using only O(1) extra memory and no recursion",
            "where the data changes while you're processing it",
            "that works correctly even if operations happen out of order",
            "that must be fully deterministic given the same seed",
            "where you can't use any built-in data structures",
            "that must handle adversarial input designed to cause worst-case behavior",
            "that works on a machine with only 1KB of RAM",
            "where operations must be reversible (undo-able)",
            "that must be lock-free and thread-safe",
            "where the answer must be approximate but computed in O(1)",
        ]

        problem = random.choice(base_problems)
        constraint = random.choice(weird_constraints)

        prompt = f\"\"\"Solve this with an unusual constraint:

Problem: {problem}
Constraint: {constraint}

The standard approach won't work here. You need to invent a new technique.
Think about:
- Why does the constraint break the normal approach?
- What properties does a solution need?
- Can you borrow ideas from other domains?

Show your full reasoning and implementation.\"\"\"

        response = self.model(prompt)
        return {
            "instruction": prompt,
            "response": response,
            "type": "constraint",
        }

    def generate_analogy_problem(self) -> dict:
        \"\"\"Apply an idea from one domain to another.

        'Apply natural selection to optimize database indexes'
        'Use fluid dynamics to model network traffic'
        \"\"\"
        domains = [
            ("biology/evolution", "natural selection, mutation, fitness"),
            ("physics/thermodynamics", "entropy, equilibrium, phase transitions"),
            ("economics/markets", "supply and demand, auctions, game theory"),
            ("music/harmony", "composition, rhythm, counterpoint"),
            ("architecture/buildings", "load bearing, foundations, ventilation"),
        ]
        targets = [
            "database query optimization",
            "network packet routing",
            "memory management",
            "task scheduling",
            "code refactoring",
        ]

        domain, desc = random.choice(domains)
        target = random.choice(targets)

        prompt = f\"\"\"Apply concepts from {domain} ({desc}) to solve a
problem in {target}.

This is a cross-domain innovation exercise:
1. Identify a principle from {domain} that maps onto {target}
2. Design the analogy carefully — what maps to what?
3. Implement the cross-domain solution in Python
4. Compare it to the standard approach — what's different?

Be genuinely creative. The best innovations come from unexpected connections.\"\"\"

        response = self.model(prompt)
        return {
            "instruction": prompt,
            "response": response,
            "type": "analogy",
        }

    def generate_invention_problem(self) -> dict:
        \"\"\"Ask the model to invent something that doesn't exist.\"\"\"
        prompts = [
            \"\"\"Invent a new sorting algorithm that's optimized for data
that's 'almost sorted but with a few elements very far from their
correct positions'. Standard algorithms handle this poorly.
Design, implement, and analyze your invention.\"\"\",

            \"\"\"Design a new caching strategy that learns from access patterns
and predicts what data will be needed next. It should adapt over time
and handle pattern changes. Implement it with real code.\"\"\",

            \"\"\"Create a new error handling pattern that's fundamentally
different from try/catch, Result types, or error codes. It should
make error handling easier and less error-prone. Design the API,
implement it in Python, and show examples.\"\"\",

            \"\"\"Invent a new concurrency primitive that makes it impossible
to create deadlocks by design. Not just detection — prevention by
construction. Implement it.\"\"\",

            \"\"\"Design a data structure that combines the best properties
of arrays (O(1) access) and linked lists (O(1) insert/delete) without
the downsides of either. Implement and benchmark it.\"\"\",
        ]

        prompt = random.choice(prompts)
        response = self.model(prompt)
        return {
            "instruction": prompt,
            "response": response,
            "type": "invention",
        }

    def score_novelty(self, solution: str, category: str) -> float:
        \"\"\"Score how novel a solution is compared to known approaches.\"\"\"
        if category not in self.known_solutions:
            self.known_solutions[category] = []
            return 1.0

        # Check structural similarity to known solutions
        import difflib
        max_similarity = 0
        for known in self.known_solutions[category]:
            similarity = difflib.SequenceMatcher(
                None, solution, known
            ).ratio()
            max_similarity = max(max_similarity, similarity)

        novelty = 1.0 - max_similarity
        # Add to known set for future comparisons
        self.known_solutions[category].append(solution)
        return novelty

    def generate_creative_batch(self, n: int = 20) -> list[dict]:
        \"\"\"Generate a batch of creative training pairs.\"\"\"
        generators = [
            (self.generate_combination_problem, 0.3),
            (self.generate_constraint_problem, 0.3),
            (self.generate_analogy_problem, 0.2),
            (self.generate_invention_problem, 0.2),
        ]

        pairs = []
        for _ in range(n):
            gen_fn = random.choices(
                [g for g, _ in generators],
                weights=[w for _, w in generators],
            )[0]
            pair = gen_fn()
            # Score novelty
            novelty = self.score_novelty(
                pair["response"], pair["type"]
            )
            pair["novelty_score"] = novelty
            if novelty > 0.3:  # Only keep genuinely novel solutions
                pairs.append(pair)

        return pairs
```

### The Creativity Spectrum

```
Level 0: REPRODUCE   "Implement quicksort"        (memorization)
Level 1: ADAPT       "Sort with memory limit"      (applying knowledge)
Level 2: COMBINE     "Merge BST + message queue"   (synthesis)
Level 3: ANALOGIZE   "Apply evolution to caching"   (cross-domain)
Level 4: INVENT      "Create a new concurrency primitive" (true innovation)
```

### Key Insight

Training on levels 2-4 teaches the model to think beyond its training data.
The model learns that novel solutions exist and that combining, analogizing,
and inventing are valid problem-solving strategies — not just pattern matching."""
    ),
]
