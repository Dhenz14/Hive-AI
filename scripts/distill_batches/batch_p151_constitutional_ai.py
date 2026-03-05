"""Constitutional AI, RLAIF, and DPO — alignment without human labels."""

PAIRS = [
    (
        "ai/constitutional-ai-rlaif",
        "Show Constitutional AI and RLAIF patterns: principle-based self-critique, AI-generated preference labels, and reward model training without human annotators.",
        '''Constitutional AI and RLAIF — self-supervised alignment:

```python
import torch
from dataclasses import dataclass, field
from transformers import AutoModelForCausalLM, AutoTokenizer


# === Constitutional AI Pipeline ===

@dataclass
class ConstitutionalPrinciple:
    """A principle for the AI to self-critique against."""
    name: str
    critique_prompt: str
    revision_prompt: str


# Define constitution — the rules the model evaluates itself against
CONSTITUTION = [
    ConstitutionalPrinciple(
        name="helpful",
        critique_prompt=(
            "Identify specific ways the response could be more helpful. "
            "Does it directly address the question? Does it provide actionable code?"
        ),
        revision_prompt=(
            "Rewrite the response to be maximally helpful. Include working code "
            "examples, explain key decisions, and anticipate follow-up questions."
        ),
    ),
    ConstitutionalPrinciple(
        name="harmless",
        critique_prompt=(
            "Does the response contain insecure code patterns (SQL injection, XSS, "
            "command injection, hardcoded secrets)? Does it encourage bad practices?"
        ),
        revision_prompt=(
            "Rewrite the response to follow security best practices. Use "
            "parameterized queries, input validation, and safe defaults."
        ),
    ),
    ConstitutionalPrinciple(
        name="honest",
        critique_prompt=(
            "Does the response make claims that might be incorrect? Does it "
            "acknowledge limitations or uncertainty where appropriate?"
        ),
        revision_prompt=(
            "Rewrite to be accurate and honest. Correct any errors, acknowledge "
            "trade-offs, and note when something is opinion vs established practice."
        ),
    ),
    ConstitutionalPrinciple(
        name="code_quality",
        critique_prompt=(
            "Review the code for: type safety, error handling at boundaries, "
            "proper resource cleanup, and following language idioms. "
            "Does it handle edge cases?"
        ),
        revision_prompt=(
            "Rewrite the code to be production-quality. Add proper error handling, "
            "use type hints, follow language conventions, and handle edge cases."
        ),
    ),
]


class ConstitutionalAI:
    """Generate improved responses via self-critique and revision."""

    def __init__(self, model_name: str = "meta-llama/Llama-3.1-8B-Instruct"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, torch_dtype=torch.bfloat16, device_map="auto"
        )

    def generate(self, prompt: str, max_tokens: int = 2048) -> str:
        """Generate a response from the model."""
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs, max_new_tokens=max_tokens,
                temperature=0.7, do_sample=True,
            )
        return self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

    def critique_and_revise(
        self,
        question: str,
        initial_response: str,
        principles: list[ConstitutionalPrinciple] | None = None,
        num_rounds: int = 1,
    ) -> dict:
        """Apply constitutional critique-revision loop.

        For each principle:
        1. Ask model to critique its own response
        2. Ask model to revise based on critique
        """
        principles = principles or CONSTITUTION
        current_response = initial_response
        history = []

        for round_num in range(num_rounds):
            for principle in principles:
                # Step 1: Critique
                critique_prompt = f"""Question: {question}

Response: {current_response}

Critique the above response based on this principle:
{principle.critique_prompt}

Provide specific, actionable feedback:"""

                critique = self.generate(critique_prompt)

                # Step 2: Revise
                revision_prompt = f"""Question: {question}

Original response: {current_response}

Critique ({principle.name}): {critique}

{principle.revision_prompt}

Improved response:"""

                revised = self.generate(revision_prompt)

                history.append({
                    "round": round_num,
                    "principle": principle.name,
                    "critique": critique,
                    "revision": revised,
                })

                current_response = revised

        return {
            "original": initial_response,
            "final": current_response,
            "history": history,
        }


# === RLAIF: AI-generated preference labels ===

class RLAIFLabeler:
    """Generate preference pairs using AI feedback instead of human annotators.

    Flow:
    1. Generate multiple responses to same prompt
    2. Use AI judge to rank responses
    3. Create preference pairs (chosen, rejected)
    4. Train reward model or use DPO directly
    """

    def __init__(self, model_name: str):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, torch_dtype=torch.bfloat16, device_map="auto"
        )

    def generate_candidates(
        self,
        prompt: str,
        n_candidates: int = 4,
        temperatures: list[float] | None = None,
    ) -> list[str]:
        """Generate diverse response candidates."""
        temperatures = temperatures or [0.3, 0.7, 1.0, 1.2]
        candidates = []

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        for temp in temperatures[:n_candidates]:
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs, max_new_tokens=1024,
                    temperature=temp, do_sample=True,
                    top_p=0.95,
                )
            response = self.tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True
            )
            candidates.append(response)

        return candidates

    def judge_pair(
        self,
        prompt: str,
        response_a: str,
        response_b: str,
    ) -> dict:
        """AI judge: compare two responses and select the better one.

        Uses chain-of-thought to improve judgment quality.
        """
        judge_prompt = f"""You are an expert judge evaluating AI responses about coding.

Question: {prompt}

Response A:
{response_a}

Response B:
{response_b}

Evaluate both responses on these criteria:
1. Correctness: Is the code correct and would it work?
2. Completeness: Does it fully address the question?
3. Best practices: Does it follow language idioms and security practices?
4. Clarity: Is the explanation clear and well-structured?

Think step by step, then state which response is better.
End with exactly one of: "WINNER: A" or "WINNER: B"

Evaluation:"""

        judgment = self.generate(judge_prompt, max_tokens=1024)

        winner = "A" if "WINNER: A" in judgment else "B"
        return {
            "winner": winner,
            "chosen": response_a if winner == "A" else response_b,
            "rejected": response_b if winner == "A" else response_a,
            "reasoning": judgment,
        }

    def create_preference_dataset(
        self,
        prompts: list[str],
        candidates_per_prompt: int = 4,
    ) -> list[dict]:
        """Generate full preference dataset from prompts.

        For each prompt:
        1. Generate N candidates
        2. Do pairwise comparisons
        3. Select best (chosen) and worst (rejected)
        """
        dataset = []

        for prompt in prompts:
            candidates = self.generate_candidates(prompt, candidates_per_prompt)

            # Round-robin pairwise judging
            scores = {i: 0 for i in range(len(candidates))}
            for i in range(len(candidates)):
                for j in range(i + 1, len(candidates)):
                    result = self.judge_pair(prompt, candidates[i], candidates[j])
                    if result["winner"] == "A":
                        scores[i] += 1
                    else:
                        scores[j] += 1

            # Best and worst by win count
            best_idx = max(scores, key=scores.get)
            worst_idx = min(scores, key=scores.get)

            dataset.append({
                "prompt": prompt,
                "chosen": candidates[best_idx],
                "rejected": candidates[worst_idx],
                "best_score": scores[best_idx],
                "worst_score": scores[worst_idx],
            })

        return dataset
```

Constitutional AI pipeline:
```
Prompt → Initial Response → Critique (per principle) → Revision → Improved Response
                                ↑                          |
                                └──────── repeat ──────────┘
```

RLAIF vs RLHF:

| Aspect | RLHF | RLAIF |
|--------|------|-------|
| **Labels** | Human annotators | AI judge |
| **Cost** | $$$$ (human labor) | $ (compute only) |
| **Scale** | Limited by annotators | Unlimited |
| **Consistency** | Inter-annotator variance | Deterministic (same temp) |
| **Quality** | Gold standard | Near-human on well-defined criteria |
| **Bias** | Human biases | Model biases (different) |

Key patterns:
1. **Constitution as code** — explicit principles (helpful, harmless, honest) that the model evaluates itself against
2. **Critique → Revise loop** — model identifies specific flaws, then rewrites to fix them; multiple rounds compound quality
3. **AI judge** — chain-of-thought evaluation of response pairs; pairwise comparison is more reliable than absolute scoring
4. **Temperature diversity** — generate candidates at different temperatures to get genuinely different responses
5. **DPO over PPO** — preference pairs from RLAIF feed directly into DPO training (simpler than reward model + PPO)'''
    ),
    (
        "ai/dpo-training",
        "Show DPO (Direct Preference Optimization) training: dataset preparation, loss function, and training loop with TRL.",
        '''DPO training — alignment without a reward model:

```python
import torch
import torch.nn.functional as F
from dataclasses import dataclass
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DPOTrainer, DPOConfig
from peft import LoraConfig


# === DPO Loss Function (from scratch) ===

def dpo_loss(
    policy_chosen_logps: torch.Tensor,    # log P(chosen | prompt) from trained model
    policy_rejected_logps: torch.Tensor,  # log P(rejected | prompt) from trained model
    ref_chosen_logps: torch.Tensor,       # log P(chosen | prompt) from reference model
    ref_rejected_logps: torch.Tensor,     # log P(rejected | prompt) from reference model
    beta: float = 0.1,                    # Temperature parameter
) -> torch.Tensor:
    """DPO loss: maximize margin between chosen and rejected.

    L_DPO = -log sigmoid(beta * (log(pi/ref)(chosen) - log(pi/ref)(rejected)))

    Intuition: increase probability of chosen response relative to reference,
    while decreasing probability of rejected response.
    """
    # Log-ratios: how much has the policy shifted from reference?
    chosen_logratios = policy_chosen_logps - ref_chosen_logps
    rejected_logratios = policy_rejected_logps - ref_rejected_logps

    # DPO objective: chosen should shift more than rejected
    logits = beta * (chosen_logratios - rejected_logratios)

    loss = -F.logsigmoid(logits).mean()

    # Metrics for monitoring
    chosen_rewards = beta * chosen_logratios.detach()
    rejected_rewards = beta * rejected_logratios.detach()
    reward_margin = (chosen_rewards - rejected_rewards).mean()

    return loss, chosen_rewards.mean(), rejected_rewards.mean(), reward_margin


# === Prepare DPO dataset ===

def prepare_dpo_dataset(preference_data: list[dict]) -> Dataset:
    """Convert preference pairs to DPO training format.

    Each example needs: prompt, chosen response, rejected response.
    """
    formatted = []
    for item in preference_data:
        formatted.append({
            "prompt": format_prompt(item["prompt"]),
            "chosen": item["chosen"],
            "rejected": item["rejected"],
        })

    dataset = Dataset.from_list(formatted)

    # Split train/eval
    split = dataset.train_test_split(test_size=0.05, seed=42)
    return split["train"], split["test"]


def format_prompt(question: str) -> str:
    """Format as chat template."""
    return f"""<|im_start|>system
You are a helpful coding assistant.<|im_end|>
<|im_start|>user
{question}<|im_end|>
<|im_start|>assistant
"""


# === DPO Training with TRL ===

def train_dpo(
    model_name: str = "Qwen/Qwen3.5-9B",
    train_data: list[dict] | None = None,
    output_dir: str = "loras/dpo-v1",
    beta: float = 0.1,
    num_epochs: int = 1,
):
    """Train DPO with LoRA using TRL."""

    # Model and tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="flash_attention_2",
    )

    # LoRA config (train adapter, not full model)
    peft_config = LoraConfig(
        r=32,
        lora_alpha=64,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        task_type="CAUSAL_LM",
        use_dora=True,
    )

    # DPO training config
    training_config = DPOConfig(
        output_dir=output_dir,
        beta=beta,                          # KL penalty coefficient
        loss_type="sigmoid",                # Standard DPO loss
        num_train_epochs=num_epochs,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=5e-5,                 # Lower LR than SFT
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        bf16=True,
        max_length=2048,
        max_prompt_length=512,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="steps",
        eval_steps=100,
        remove_unused_columns=False,
        gradient_checkpointing=True,
        report_to="none",
    )

    # Prepare dataset
    train_dataset, eval_dataset = prepare_dpo_dataset(train_data)

    # DPO trainer handles reference model automatically
    # (creates a frozen copy of the initial model)
    trainer = DPOTrainer(
        model=model,
        args=training_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    # Train
    trainer.train()

    # Save LoRA adapter
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Log final metrics
    metrics = trainer.evaluate()
    print(f"Final eval loss: {metrics['eval_loss']:.4f}")
    print(f"Reward margin: {metrics.get('eval_rewards/margins', 'N/A')}")

    return trainer


# === DPO variants ===

def compute_dpo_variant_loss(
    chosen_logratios: torch.Tensor,
    rejected_logratios: torch.Tensor,
    beta: float = 0.1,
    variant: str = "sigmoid",
) -> torch.Tensor:
    """Different DPO loss variants.

    - sigmoid: Standard DPO (Rafailov et al.)
    - hinge: Margin-based, less sensitive to outliers
    - ipo: Identity PO — linear loss, more stable
    - kto: Kahneman-Tversky Optimization — unpaired preferences
    """
    logits = beta * (chosen_logratios - rejected_logratios)

    if variant == "sigmoid":
        # Standard DPO
        return -F.logsigmoid(logits).mean()

    elif variant == "hinge":
        # SLiC-HF style hinge loss
        return torch.relu(1.0 - logits).mean()

    elif variant == "ipo":
        # IPO: (logits - 1/(2*beta))^2
        return ((logits - 1.0 / (2.0 * beta)) ** 2).mean()

    elif variant == "kto":
        # KTO: separate loss for chosen and rejected
        chosen_loss = 1.0 - F.sigmoid(beta * chosen_logratios)
        rejected_loss = F.sigmoid(beta * rejected_logratios)
        return (chosen_loss.mean() + rejected_loss.mean()) / 2

    raise ValueError(f"Unknown variant: {variant}")
```

DPO vs PPO comparison:

| Aspect | PPO (RLHF) | DPO |
|--------|-----------|-----|
| **Reward model** | Required (separate training) | Not needed |
| **Training stability** | Tricky (KL, clipping, GAE) | Stable (supervised-like) |
| **Memory** | 4 models (policy, ref, reward, value) | 2 models (policy, ref) |
| **Hyperparameters** | Many (clip, GAE lambda, etc.) | Few (beta, LR) |
| **Performance** | Slightly better ceiling | Comparable in practice |

Key patterns:
1. **DPO as classification** — reformulates RLHF as binary classification: chosen vs rejected, no reward model needed
2. **Beta parameter** — controls deviation from reference model; lower beta = more change, higher = more conservative
3. **Reference model** — frozen copy of initial weights; DPO loss is defined relative to it
4. **LoRA + DPO** — train only adapter weights for alignment; reference model shares base weights (memory efficient)
5. **IPO variant** — linear loss is more stable than sigmoid for small datasets; KTO works with unpaired preferences'''
    ),
]
"""
