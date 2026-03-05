"""
Batch P4 — LLM Training: LoRA, distributed training, mixed precision, data pipelines.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. LoRA and Parameter-Efficient Fine-Tuning ---
    (
        "lora_peft_deep_dive",
        "Explain LoRA (Low-Rank Adaptation) in depth — the mathematical foundation of low-rank "
        "decomposition, how to choose rank and alpha, which layers to target, QLoRA for 4-bit "
        "training, and how to merge LoRA weights back into the base model. Show complete training "
        "code with PyTorch and the PEFT library, including proper evaluation and export.",
        """\
# LoRA: Parameter-Efficient Fine-Tuning for Large Language Models

## Why LoRA Exists

Fine-tuning a 7B parameter model requires updating all 7 billion parameters, which needs:
- ~28GB of GPU memory just for weights (FP32) or ~14GB (BF16)
- ~56GB total with optimizer states (Adam stores momentum + variance)
- Multiple high-end GPUs for models >13B

LoRA solves this by **freezing the base model** and training small **low-rank adapter
matrices** that modify the model's behavior. A typical LoRA adds only 0.1-1% new parameters.

## Mathematical Foundation

```
Standard fine-tuning modifies weight matrix W directly:
  W_new = W_original + ΔW    (ΔW has same dimensions as W, e.g., 4096×4096)

LoRA decomposes ΔW into two smaller matrices:
  ΔW = B × A    where B is (d × r) and A is (r × d)
  B: "down-projection" — d dimensions → r dimensions
  A: "up-projection"  — r dimensions → d dimensions
  r << d (rank 8-64 is typical, d is 4096+)

For a 4096×4096 weight matrix:
  Full fine-tuning:  4096 × 4096 = 16.7M parameters
  LoRA rank 16:      4096 × 16 + 16 × 4096 = 131K parameters (128x fewer!)
  LoRA rank 64:      4096 × 64 + 64 × 4096 = 524K parameters (32x fewer)

Forward pass with LoRA:
  y = W_original × x + (B × A × x) × (α/r)

  α (alpha) is a scaling factor that controls adaptation strength:
  - α = r: scaling is 1.0 (like standard fine-tuning at that rank)
  - α = 2r: scaling is 2.0 (stronger adaptation, more divergence from base)
  - α = r/2: scaling is 0.5 (gentler adaptation, stays closer to base)

  The reason α exists: without it, changing rank changes the magnitude of updates.
  α/r normalizes this, so you can tune rank independently of update magnitude.
```

## Why Low-Rank Works

The key insight from the original LoRA paper: **pre-trained language models have a low
intrinsic dimensionality** — the weight updates during fine-tuning occupy a very low-rank
subspace. In other words, most of the 7 billion parameters don't need to change much for
a specific task. LoRA exploits this by constraining updates to a low-rank subspace.

This is why LoRA works well for domain adaptation (teaching a model about your codebase or
industry) but works less well for fundamentally changing the model's capabilities (e.g.,
adding a new language it's never seen). The trade-off is efficiency versus expressiveness.

## Complete Training Pipeline

```python
\"\"\"Production LoRA training pipeline with QLoRA support.\"\"\"
import torch
from torch.utils.data import DataLoader
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
from trl import SFTTrainer, DataCollatorForCompletionOnlyLM
from datasets import load_dataset
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class LoRATrainingConfig:
    \"\"\"Configuration for LoRA training — each parameter explained.\"\"\"
    # Model
    base_model: str = "meta-llama/Llama-3.1-8B"
    use_qlora: bool = True  # 4-bit quantization for memory efficiency

    # LoRA hyperparameters
    lora_r: int = 32         # Rank — higher = more expressive but more memory
    lora_alpha: int = 64     # Scaling — typically 2x rank for good results
    lora_dropout: float = 0.05  # Regularization — prevents overfitting to small datasets
    target_modules: List[str] = None  # Which layers to adapt

    # Training
    learning_rate: float = 2e-4     # LoRA-specific: higher than full fine-tuning
    num_epochs: int = 3
    per_device_batch_size: int = 4
    gradient_accumulation_steps: int = 4  # Effective batch = 4 * 4 = 16
    max_seq_length: int = 2048
    warmup_ratio: float = 0.03

    # Output
    output_dir: str = "./lora-output"

    def __post_init__(self):
        if self.target_modules is None:
            # Target attention + MLP layers for best results
            # q_proj, k_proj, v_proj: attention projections
            # o_proj: attention output
            # gate_proj, up_proj, down_proj: MLP layers
            # Targeting ALL these is better than just attention — the original
            # LoRA paper only did q/v, but later work showed MLP matters too
            self.target_modules = [
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ]


def setup_model(config: LoRATrainingConfig):
    \"\"\"
    Load base model and apply LoRA configuration.

    QLoRA (Quantized LoRA) loads the base model in 4-bit precision,
    then trains LoRA adapters in BF16. This reduces memory from ~16GB
    to ~6GB for a 7B model, making it trainable on a single consumer GPU.
    \"\"\"
    tokenizer = AutoTokenizer.from_pretrained(config.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if config.use_qlora:
        # 4-bit quantization config
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",       # NormalFloat4 — best for LLMs
            bnb_4bit_compute_dtype=torch.bfloat16,  # Compute in BF16
            bnb_4bit_use_double_quant=True,   # Quantize the quantization constants
        )
        model = AutoModelForCausalLM.from_pretrained(
            config.base_model,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",  # FA2 for speed
        )
        model = prepare_model_for_kbit_training(model)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            config.base_model,
            device_map="auto",
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        )

    # Apply LoRA configuration
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.target_modules,
        bias="none",        # Don't train biases — marginal benefit, adds params
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, lora_config)

    # Log trainable parameters
    trainable, total = model.get_nb_trainable_parameters()
    logger.info(
        f"Trainable parameters: {trainable:,} / {total:,} "
        f"({100 * trainable / total:.2f}%)"
    )

    return model, tokenizer


def format_training_data(
    example: Dict[str, str],
    tokenizer: AutoTokenizer,
) -> str:
    \"\"\"
    Format instruction-response pairs into the model's chat template.

    Using the model's native chat template is critical because it matches
    what the model learned during pre-training. Using a custom format
    degrades performance because the model doesn't recognize the structure.
    \"\"\"
    messages = [
        {"role": "system", "content": "You are a helpful coding assistant."},
        {"role": "user", "content": example["instruction"]},
        {"role": "assistant", "content": example["response"]},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False)


def train(config: LoRATrainingConfig, dataset_path: str) -> str:
    \"\"\"
    Train LoRA adapter and return the output path.
    \"\"\"
    model, tokenizer = setup_model(config)
    dataset = load_dataset("json", data_files=dataset_path, split="train")

    # Only compute loss on the assistant's response, not the instruction
    # This is crucial — training on the instruction teaches the model to
    # generate instructions, which is not what we want
    response_template = "<|start_header_id|>assistant<|end_header_id|>"
    collator = DataCollatorForCompletionOnlyLM(
        response_template=response_template,
        tokenizer=tokenizer,
    )

    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.per_device_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=config.warmup_ratio,
        bf16=True,                    # BF16 mixed precision
        logging_steps=10,
        save_strategy="epoch",
        optim="adamw_8bit",           # 8-bit Adam saves memory
        gradient_checkpointing=True,  # Trade compute for memory
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_grad_norm=1.0,
        report_to="wandb",
        seed=42,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=dataset,
        data_collator=collator,
        formatting_func=lambda ex: format_training_data(ex, tokenizer),
        max_seq_length=config.max_seq_length,
        packing=True,  # Pack short sequences together for efficiency
    )

    try:
        trainer.train()
        trainer.save_model(config.output_dir)
        tokenizer.save_pretrained(config.output_dir)
        logger.info(f"Training complete. Model saved to {config.output_dir}")
        return config.output_dir
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise
```

## Merging LoRA Back into Base Model

```python
def merge_lora_to_base(
    base_model_path: str,
    lora_adapter_path: str,
    output_path: str,
    push_to_hub: bool = False,
) -> None:
    \"\"\"
    Merge LoRA weights into the base model for inference without PEFT.

    After merging, the model runs at native speed (no adapter overhead)
    and can be quantized to GGUF/AWQ for deployment.

    The merge is mathematically exact:
    W_merged = W_base + (B × A × α/r)
    \"\"\"
    from peft import PeftModel

    logger.info(f"Loading base model: {base_model_path}")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_path,
        torch_dtype=torch.bfloat16,
        device_map="cpu",  # Merge on CPU to avoid GPU memory issues
    )

    logger.info(f"Loading LoRA adapter: {lora_adapter_path}")
    model = PeftModel.from_pretrained(base_model, lora_adapter_path)

    logger.info("Merging LoRA weights into base model...")
    merged_model = model.merge_and_unload()

    logger.info(f"Saving merged model to: {output_path}")
    merged_model.save_pretrained(output_path)

    tokenizer = AutoTokenizer.from_pretrained(lora_adapter_path)
    tokenizer.save_pretrained(output_path)

    if push_to_hub:
        merged_model.push_to_hub(output_path)
        tokenizer.push_to_hub(output_path)

    logger.info("Merge complete!")
```

## Choosing Hyperparameters

```
LoRA Rank (r):
  r=8:   Minimal adaptation, good for simple tasks (sentiment, classification)
  r=16:  Standard for most fine-tuning tasks
  r=32:  Good for complex domain adaptation (coding, medical, legal)
  r=64:  Maximum useful rank for most models
  r=128: Rarely needed, diminishing returns
  Rule: Start with r=32, reduce if overfitting, increase if underfitting

LoRA Alpha (α):
  α = r:   Balanced adaptation (1.0 scaling)
  α = 2r:  Standard recommendation (slightly stronger adaptation)
  α = r/2: Conservative (stays closer to base model behavior)
  Rule: Set α = 2 × r as default, tune if needed

Target Modules:
  Attention only (q_proj, v_proj):     Baseline, least parameters
  + k_proj, o_proj:                     Better, covers all attention
  + gate_proj, up_proj, down_proj:      Best, covers MLP too (recommended)
  + embed_tokens, lm_head:              Rarely needed, adds many params

Learning Rate:
  Full fine-tuning:  1e-5 to 5e-5
  LoRA:              1e-4 to 3e-4 (higher because fewer params)
  QLoRA:             2e-4 (standard recommendation)

Dataset Size:
  < 100 examples:    Risk of overfitting. Use r=8, more dropout (0.1)
  100-1000:          Sweet spot for LoRA. r=16-32
  1000-10000:        Can use higher rank. r=32-64
  > 10000:           Consider full fine-tuning if budget allows
```

## Testing LoRA Quality

```python
import pytest
from transformers import pipeline


def test_lora_generation_quality():
    \"\"\"Verify LoRA model generates coherent, on-topic responses.\"\"\"
    pipe = pipeline("text-generation", model="./lora-output", device_map="auto")

    test_prompts = [
        "Explain how Python's GIL affects multithreading performance.",
        "Write a function to implement binary search in Rust.",
        "What are the trade-offs between SQL and NoSQL databases?",
    ]

    for prompt in test_prompts:
        result = pipe(prompt, max_new_tokens=200, do_sample=False)
        text = result[0]["generated_text"]

        # Basic quality checks
        assert len(text) > len(prompt) + 50, f"Response too short for: {prompt[:50]}"
        assert text.count("\\n") < 50, "Excessive newlines (degenerate output)"

        # Check for repetition (common failure mode)
        words = text.split()
        if len(words) > 20:
            unique_ratio = len(set(words)) / len(words)
            assert unique_ratio > 0.3, f"Highly repetitive output (unique ratio: {unique_ratio})"


def test_lora_merge_preserves_quality():
    \"\"\"Merged model should produce same outputs as adapter model.\"\"\"
    adapter_pipe = pipeline("text-generation", model="./lora-output")
    merged_pipe = pipeline("text-generation", model="./merged-output")

    prompt = "What is the capital of France?"
    adapter_result = adapter_pipe(prompt, max_new_tokens=50, do_sample=False)
    merged_result = merged_pipe(prompt, max_new_tokens=50, do_sample=False)

    # Results should be identical (merge is mathematically exact)
    assert adapter_result[0]["generated_text"] == merged_result[0]["generated_text"]
```

## Key Takeaways

LoRA is the most practical approach to fine-tuning LLMs for most teams because it reduces
GPU memory requirements by 4-8x while preserving 95%+ of full fine-tuning quality. The
common mistake is using too high a rank (r=128) "just to be safe" — this wastes memory
and can cause overfitting on small datasets. Start with r=32, α=64, target all attention
and MLP layers, and adjust based on evaluation.

QLoRA makes fine-tuning a 7B model possible on a single 16GB GPU (RTX 4080/A4000), which
democratizes model adaptation. However, the trade-off is training speed — 4-bit quantization
adds ~20% overhead per step because of dequantization during the forward pass. For production
training at scale, BF16 full-precision LoRA on multiple GPUs is faster if you have the
hardware budget.
"""
    ),

    # --- 2. Distributed Training ---
    (
        "distributed_training_deepspeed_fsdp",
        "Explain distributed LLM training — data parallelism vs model parallelism vs pipeline "
        "parallelism, DeepSpeed ZeRO stages, FSDP (Fully Sharded Data Parallel), and how to "
        "train models that don't fit on a single GPU. Show a complete multi-GPU training setup "
        "with DeepSpeed ZeRO-3 and compare with FSDP. Include proper configuration, monitoring, "
        "and common failure modes with solutions.",
        """\
# Distributed LLM Training: From Single GPU to Multi-Node Clusters

## The Memory Problem

Training a 7B parameter model requires:
```
Component              FP32          BF16          Memory
Model parameters       28 GB         14 GB         Weights
Gradients              28 GB         14 GB         Same size as params
Optimizer states       56 GB         28 GB         Adam: 2x params (momentum + variance)
Activations            Variable      Variable      Depends on batch size + seq length
─────────────────────────────────────────────────────────
Total (no activation   112 GB        56 GB         Doesn't fit on any single GPU!
checkpointing)

With gradient checkpointing:
  Activations reduced by ~60-70%, but recomputed during backward pass
  Total: ~70 GB (BF16) — still needs multiple GPUs
```

## Parallelism Strategies

```
1. DATA PARALLELISM (DP)
   Each GPU has a full model copy, different data batches
   ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
   │GPU 0│ │GPU 1│ │GPU 2│ │GPU 3│
   │Full │ │Full │ │Full │ │Full │  ← Same model, different data
   │Model│ │Model│ │Model│ │Model│
   └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘
      └───────┴───┬───┴───────┘
                  │ AllReduce gradients
                  │ (synchronize updates)

   Pro: Simple, scales linearly
   Con: Each GPU must fit the full model + optimizer

2. MODEL PARALLELISM (Tensor Parallel)
   Model layers are split across GPUs
   ┌─────────────┐
   │   Layer N    │  ← Split across GPUs
   │ GPU0 | GPU1  │
   ├─────────────┤
   │   Layer N-1  │
   │ GPU0 | GPU1  │
   └─────────────┘

   Pro: Handles models too large for one GPU
   Con: Communication overhead between GPUs per layer

3. PIPELINE PARALLELISM
   Different layers on different GPUs
   ┌─────┐→┌─────┐→┌─────┐→┌─────┐
   │GPU 0│ │GPU 1│ │GPU 2│ │GPU 3│
   │L1-8 │ │L9-16│ │L17-24│ │L25-32│  ← Different layers
   └─────┘ └─────┘ └──────┘ └──────┘

   Pro: Simple to implement, good for deep models
   Con: Pipeline bubbles (GPUs idle while waiting)

4. ZERO (Zero Redundancy Optimizer) — DeepSpeed's innovation
   Shard optimizer states, gradients, AND parameters across GPUs
   No GPU has a full copy — they gather what they need on demand
```

## DeepSpeed ZeRO Configuration

```python
\"\"\"Multi-GPU training with DeepSpeed ZeRO-3.\"\"\"
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
)
from trl import SFTTrainer
from datasets import load_dataset
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# DeepSpeed ZeRO-3 configuration — explained
DEEPSPEED_CONFIG: Dict[str, Any] = {
    "bf16": {
        "enabled": True  # BF16 mixed precision — essential for LLM training
    },
    "zero_optimization": {
        "stage": 3,  # ZeRO Stage 3: shard params + gradients + optimizer

        # Stage 3 specifics
        "offload_optimizer": {
            "device": "cpu",     # Offload optimizer to CPU RAM (saves GPU memory)
            "pin_memory": True   # Pinned memory for faster CPU-GPU transfer
        },
        "offload_param": {
            "device": "none",    # Keep params on GPU (faster training)
            # Use "cpu" if you still run out of GPU memory
        },

        # Prefetching — overlap communication with computation
        "stage3_prefetch_bucket_size": 5e8,  # 500M params per prefetch
        "stage3_param_persistence_threshold": 1e6,  # Small params stay on all GPUs

        # Gathering parameters
        "stage3_max_live_parameters": 1e9,
        "stage3_max_reuse_distance": 1e9,
        "stage3_gather_16bit_weights_on_model_save": True,

        # Reduce buffer for gradient reduction
        "reduce_bucket_size": 5e8,

        # Contiguous memory optimization
        "contiguous_gradients": True,
        "overlap_comm": True,  # Overlap communication with backward pass
    },
    "gradient_accumulation_steps": "auto",  # Inherited from TrainingArguments
    "gradient_clipping": 1.0,
    "train_batch_size": "auto",
    "train_micro_batch_size_per_gpu": "auto",

    # Activation checkpointing — trade compute for memory
    "activation_checkpointing": {
        "partition_activations": True,
        "cpu_checkpointing": False,
        "contiguous_memory_optimization": True,
        "number_checkpoints": None,  # Checkpoint all layers
    },

    # Communication optimization
    "comms_config": {
        "fp16": {"enabled": False},
        "bf16": {"enabled": True},  # Use BF16 for AllReduce communication
    },
}


def train_distributed(
    model_name: str = "meta-llama/Llama-3.1-8B",
    dataset_path: str = "training_data.jsonl",
    output_dir: str = "./distributed-output",
    num_epochs: int = 3,
) -> None:
    \"\"\"
    Launch distributed training with DeepSpeed ZeRO-3.

    Run with: deepspeed --num_gpus=4 train.py
    Or with torchrun: torchrun --nproc_per_node=4 train.py
    \"\"\"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Model loaded with DeepSpeed — it handles sharding automatically
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
        use_cache=False,  # Must disable KV cache for training
    )

    dataset = load_dataset("json", data_files=dataset_path, split="train")

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,  # Effective batch size: 2 * 8 * 4 GPUs = 64
        learning_rate=2e-5,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        bf16=True,
        logging_steps=10,
        save_strategy="steps",
        save_steps=500,
        deepspeed=DEEPSPEED_CONFIG,  # Enable DeepSpeed
        gradient_checkpointing=True,
        report_to="wandb",
        seed=42,
        # Multi-node settings
        ddp_timeout=7200,  # 2 hours (large models take long to initialize)
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=dataset,
        max_seq_length=2048,
        packing=True,
    )

    try:
        trainer.train()
        trainer.save_model()
        logger.info(f"Training complete. Model saved to {output_dir}")
    except Exception as e:
        logger.error(f"Training failed: {e}")
        # Save checkpoint on failure for recovery
        trainer.save_model(f"{output_dir}/emergency-checkpoint")
        raise
```

## ZeRO Stages Comparison

```
                Stage 1         Stage 2         Stage 3
What's sharded: Optimizer       + Gradients     + Parameters
Memory per GPU: ~75% of naive   ~50%            ~25%
Communication:  Low             Medium          High
Speed:          Fastest         Medium          Slowest (but fits largest models)

Recommendation:
  Model fits on 1 GPU with optimizer? → Don't use DeepSpeed, waste of complexity
  Model fits but optimizer doesn't?   → ZeRO Stage 1
  Gradients + optimizer don't fit?    → ZeRO Stage 2
  Model itself doesn't fit?           → ZeRO Stage 3 (or FSDP)

Common mistake: Using Stage 3 when Stage 1 suffices.
Stage 3 adds significant communication overhead because parameters must be
gathered before each forward/backward pass. Only use it when necessary.
```

## FSDP vs DeepSpeed Comparison

```python
# PyTorch FSDP alternative — native PyTorch, no external library
# Use this when you want to avoid the DeepSpeed dependency

fsdp_config = {
    "fsdp": "full_shard auto_wrap",
    "fsdp_config": {
        "fsdp_auto_wrap_policy": "TRANSFORMER_BASED_WRAP",
        "fsdp_backward_prefetch": "BACKWARD_PRE",
        "fsdp_cpu_ram_efficient_loading": True,
        "fsdp_forward_prefetch": False,
        "fsdp_offload_params": False,
        "fsdp_sharding_strategy": "FULL_SHARD",  # Equivalent to ZeRO-3
        "fsdp_state_dict_type": "SHARDED_STATE_DICT",
        "fsdp_transformer_layer_cls_to_wrap": "LlamaDecoderLayer",
        "fsdp_use_orig_params": True,
    },
}

# TrainingArguments with FSDP
# training_args = TrainingArguments(
#     ...
#     fsdp="full_shard auto_wrap",
#     fsdp_config=fsdp_config["fsdp_config"],
# )

# DeepSpeed vs FSDP trade-offs:
#   DeepSpeed: More features (offloading, inference, compression), more config complexity
#   FSDP: Native PyTorch, simpler config, better for pure PyTorch workflows
#   Performance: Similar at Stage 3/full_shard. DeepSpeed slightly faster with offloading.
#   Ecosystem: DeepSpeed has better HuggingFace integration as of 2025.
```

## Monitoring and Common Failures

```python
def monitor_training_health(trainer) -> Dict[str, Any]:
    \"\"\"Check for common distributed training issues.\"\"\"
    metrics = {}

    # 1. GPU memory utilization — should be 85-95%
    for i in range(torch.cuda.device_count()):
        allocated = torch.cuda.memory_allocated(i) / 1e9
        total = torch.cuda.get_device_properties(i).total_mem / 1e9
        utilization = allocated / total
        metrics[f"gpu_{i}_mem_util"] = utilization

        if utilization > 0.98:
            logger.warning(f"GPU {i} near OOM: {utilization:.1%}")
        elif utilization < 0.70:
            logger.info(f"GPU {i} underutilized: {utilization:.1%} — consider larger batch")

    # 2. Loss divergence check
    if hasattr(trainer.state, 'log_history') and len(trainer.state.log_history) > 10:
        recent_losses = [
            h['loss'] for h in trainer.state.log_history[-10:]
            if 'loss' in h
        ]
        if recent_losses and recent_losses[-1] > 2 * min(recent_losses):
            logger.error("Loss diverging! Consider reducing learning rate.")

    return metrics
```

## Key Takeaways

Distributed training is necessary when your model doesn't fit on a single GPU, but it adds
significant complexity. The common mistake is jumping to multi-GPU training before optimizing
single-GPU performance — gradient checkpointing, mixed precision, and LoRA often eliminate
the need for distributed training entirely.

When distributed training is necessary, start with ZeRO Stage 2 (shards optimizer + gradients)
because it has the best speed/memory trade-off. Only use Stage 3 when the model parameters
themselves don't fit on a single GPU. The trade-off between DeepSpeed and FSDP is ecosystem
versus simplicity — DeepSpeed has more features and better HuggingFace integration, while
FSDP is native PyTorch with simpler configuration.

For production training, always monitor GPU memory utilization, gradient norms, and loss
trends. A sudden spike in loss usually indicates learning rate too high or data quality issues,
not a distributed training bug. Save checkpoints frequently because multi-GPU jobs are
expensive to restart.
"""
    ),
]
