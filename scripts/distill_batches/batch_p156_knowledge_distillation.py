"""Knowledge Distillation — teacher-student training, feature distillation, and self-distillation."""

PAIRS = [
    (
        "ai/knowledge-distillation",
        "Show knowledge distillation patterns: teacher-student training, soft label transfer, feature-based distillation, and progressive distillation.",
        '''Knowledge distillation — compressing large models into smaller ones:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer


class DistillationLoss(nn.Module):
    """Combined distillation loss: soft labels + hard labels + feature matching.

    L = alpha * L_soft + (1-alpha) * L_hard + beta * L_feature
    """

    def __init__(self, temperature: float = 4.0, alpha: float = 0.7, beta: float = 0.1):
        super().__init__()
        self.temperature = temperature
        self.alpha = alpha
        self.beta = beta

    def forward(
        self,
        student_logits: torch.Tensor,
        teacher_logits: torch.Tensor,
        labels: torch.Tensor,
        student_hidden: torch.Tensor | None = None,
        teacher_hidden: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        # Soft label loss (KL divergence on softened probabilities)
        # Higher temperature -> softer probability distribution -> more knowledge transfer
        soft_student = F.log_softmax(student_logits / self.temperature, dim=-1)
        soft_teacher = F.softmax(teacher_logits / self.temperature, dim=-1)
        loss_soft = F.kl_div(soft_student, soft_teacher, reduction="batchmean")
        loss_soft = loss_soft * (self.temperature ** 2)  # Scale by T^2

        # Hard label loss (standard cross-entropy)
        loss_hard = F.cross_entropy(student_logits, labels)

        # Feature matching loss (optional)
        loss_feature = torch.tensor(0.0, device=student_logits.device)
        if student_hidden is not None and teacher_hidden is not None:
            # Project student hidden to teacher dimension if different
            loss_feature = F.mse_loss(student_hidden, teacher_hidden)

        total = self.alpha * loss_soft + (1 - self.alpha) * loss_hard + self.beta * loss_feature

        return {
            "loss": total,
            "loss_soft": loss_soft.detach(),
            "loss_hard": loss_hard.detach(),
            "loss_feature": loss_feature.detach(),
        }


class LLMDistiller:
    """Distill a large LLM into a smaller one.

    Teacher: large model (e.g., Qwen-72B, Llama-70B)
    Student: small model (e.g., Qwen-1.5B, Llama-3B)
    """

    def __init__(
        self,
        teacher_name: str,
        student_name: str,
        temperature: float = 4.0,
        alpha: float = 0.7,
    ):
        # Load teacher (frozen, inference-only)
        self.teacher = AutoModelForCausalLM.from_pretrained(
            teacher_name, torch_dtype=torch.bfloat16, device_map="auto"
        )
        self.teacher.eval()
        for param in self.teacher.parameters():
            param.requires_grad = False

        # Load student (trainable)
        self.student = AutoModelForCausalLM.from_pretrained(
            student_name, torch_dtype=torch.bfloat16, device_map="auto"
        )

        self.tokenizer = AutoTokenizer.from_pretrained(student_name)
        self.criterion = DistillationLoss(temperature=temperature, alpha=alpha)

    @torch.no_grad()
    def get_teacher_logits(self, input_ids: torch.Tensor) -> torch.Tensor:
        """Get teacher's probability distribution over vocabulary."""
        outputs = self.teacher(input_ids)
        return outputs.logits

    def train_step(self, batch: dict) -> dict:
        """Single training step."""
        input_ids = batch["input_ids"]
        labels = batch["labels"]

        # Teacher predictions (no gradient)
        teacher_logits = self.get_teacher_logits(input_ids)

        # Student predictions (with gradient)
        student_outputs = self.student(input_ids)
        student_logits = student_outputs.logits

        # Shift for next-token prediction
        shift_student = student_logits[:, :-1].contiguous()
        shift_teacher = teacher_logits[:, :-1].contiguous()
        shift_labels = labels[:, 1:].contiguous()

        # Flatten
        vocab_size = shift_student.shape[-1]
        losses = self.criterion(
            shift_student.view(-1, vocab_size),
            shift_teacher.view(-1, vocab_size),
            shift_labels.view(-1),
        )

        return losses


# === Progressive Distillation ===

class ProgressiveDistiller:
    """Multi-stage distillation: Teacher -> Medium -> Small.

    Distilling directly from very large to very small often fails.
    Progressive distillation uses intermediate models as bridges.
    """

    def __init__(self, model_chain: list[str]):
        """
        model_chain: ["Qwen-72B", "Qwen-14B", "Qwen-7B", "Qwen-1.5B"]
        """
        self.model_chain = model_chain

    def distill_chain(self, dataset, epochs_per_stage: int = 3):
        """Distill through the chain of models."""
        for i in range(len(self.model_chain) - 1):
            teacher_name = self.model_chain[i]
            student_name = self.model_chain[i + 1]

            print(f"Stage {i+1}: {teacher_name} -> {student_name}")

            distiller = LLMDistiller(
                teacher_name=teacher_name,
                student_name=student_name,
                temperature=max(2.0, 6.0 - i * 2),  # Decrease temp for later stages
                alpha=0.8 - i * 0.1,  # Shift toward hard labels for later stages
            )

            # Train this stage
            train_distillation_stage(distiller, dataset, epochs_per_stage)

            # Save intermediate student as next teacher
            distiller.student.save_pretrained(f"checkpoints/stage_{i+1}")
            self.model_chain[i + 1] = f"checkpoints/stage_{i+1}"


# === Online Distillation (self-distillation) ===

class SelfDistillation(nn.Module):
    """Self-distillation: deeper layers teach shallower layers.

    No separate teacher model needed — the model teaches itself.
    Attach auxiliary classifiers at intermediate layers.
    """

    def __init__(self, base_model: nn.Module, hidden_dim: int,
                 vocab_size: int, aux_layer_indices: list[int]):
        super().__init__()
        self.base_model = base_model
        self.aux_layer_indices = aux_layer_indices

        # Auxiliary classifiers at intermediate layers
        self.aux_heads = nn.ModuleDict({
            str(idx): nn.Linear(hidden_dim, vocab_size, bias=False)
            for idx in aux_layer_indices
        })

    def forward(self, input_ids: torch.Tensor, labels: torch.Tensor) -> dict:
        # Forward through all layers, collecting hidden states
        hidden_states = []
        x = self.base_model.embed_tokens(input_ids)

        for i, layer in enumerate(self.base_model.layers):
            x = layer(x)
            if i in self.aux_layer_indices:
                hidden_states.append((i, x))

        # Final output
        x = self.base_model.norm(x)
        final_logits = self.base_model.lm_head(x)

        # Main loss
        main_loss = F.cross_entropy(
            final_logits[:, :-1].reshape(-1, final_logits.shape[-1]),
            labels[:, 1:].reshape(-1),
        )

        # Self-distillation: intermediate layers learn from final layer
        aux_loss = torch.tensor(0.0, device=x.device)
        final_probs = F.softmax(final_logits[:, :-1] / 3.0, dim=-1).detach()

        for layer_idx, hidden in hidden_states:
            aux_logits = self.aux_heads[str(layer_idx)](hidden[:, :-1])
            aux_log_probs = F.log_softmax(aux_logits / 3.0, dim=-1)
            aux_loss += F.kl_div(aux_log_probs, final_probs, reduction="batchmean")

        aux_loss /= len(hidden_states)
        total_loss = main_loss + 0.5 * aux_loss

        return {"loss": total_loss, "main_loss": main_loss, "aux_loss": aux_loss}
```

Distillation strategies:

| Method | Teacher needed | Quality | Compute |
|--------|---------------|---------|---------|
| **Logit KD** | Yes (frozen) | Best | 2x inference |
| **Feature KD** | Yes (frozen) | Great | 2x + storage |
| **Progressive** | Chain of models | Better for large gaps | N stages |
| **Self-distillation** | No | Good | 1.2x |
| **Data-free KD** | Generator + teacher | Decent | High |

Key patterns:
1. **Temperature scaling** — higher T (4-8) produces softer distributions, revealing more knowledge about class relationships
2. **Alpha blending** — balance soft labels (teacher knowledge) and hard labels (ground truth); alpha=0.7 is a good start
3. **T² scaling** — multiply KL loss by T² to keep gradients in the right scale as temperature changes
4. **Progressive chain** — 72B → 14B → 7B → 1.5B works better than 72B → 1.5B direct distillation
5. **Self-distillation** — attach auxiliary heads at intermediate layers; deeper layers teach shallower ones'''
    ),
    (
        "ai/synthetic-data-generation",
        "Show synthetic data generation for LLM training: Evol-Instruct, self-instruct, rejection sampling, and quality filtering.",
        '''Synthetic data generation for LLM training:

```python
import json
import random
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from anthropic import AsyncAnthropic


# === Evol-Instruct: evolve instructions through complexity mutations ===

EVOLUTION_PROMPTS = {
    "add_constraints": (
        "Make this instruction more complex by adding constraints or conditions.\\n"
        "Original: {instruction}\\n"
        "Evolved (more constrained):"
    ),
    "deepen": (
        "Increase the depth and reasoning required by this instruction.\\n"
        "Original: {instruction}\\n"
        "Evolved (deeper reasoning):"
    ),
    "concretize": (
        "Make this instruction more specific and concrete with real-world context.\\n"
        "Original: {instruction}\\n"
        "Evolved (more concrete):"
    ),
    "increase_steps": (
        "Add more steps or sub-tasks to this instruction.\\n"
        "Original: {instruction}\\n"
        "Evolved (multi-step):"
    ),
    "cross_domain": (
        "Combine this instruction with concepts from a different domain.\\n"
        "Original: {instruction}\\n"
        "Evolved (cross-domain):"
    ),
}


class EvolInstruct:
    """Generate increasingly complex instructions via evolution."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = AsyncAnthropic()
        self.model = model

    async def evolve(self, instruction: str, generations: int = 3) -> list[str]:
        """Evolve an instruction through multiple generations."""
        current = instruction
        evolved = [current]

        for gen in range(generations):
            mutation = random.choice(list(EVOLUTION_PROMPTS.keys()))
            prompt = EVOLUTION_PROMPTS[mutation].format(instruction=current)

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            current = response.content[0].text.strip()
            evolved.append(current)

        return evolved

    async def generate_responses(self, instructions: list[str]) -> list[dict]:
        """Generate high-quality responses for evolved instructions."""
        pairs = []

        async def process_one(instruction: str) -> dict:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": instruction}],
            )
            return {"instruction": instruction, "response": response.content[0].text}

        tasks = [process_one(inst) for inst in instructions]
        pairs = await asyncio.gather(*tasks)
        return list(pairs)


# === Self-Instruct: model generates its own training data ===

class SelfInstruct:
    """Generate instruction-response pairs from seed examples."""

    def __init__(self, seeds: list[dict], model: str = "claude-sonnet-4-6"):
        self.seeds = seeds
        self.client = AsyncAnthropic()
        self.model = model

    async def generate_instructions(self, n: int = 100) -> list[str]:
        """Generate diverse instructions from seed examples."""
        instructions = []

        for _ in range(n):
            seed_sample = random.sample(self.seeds, min(3, len(self.seeds)))
            seed_text = "\\n".join(
                f"- {s['instruction']}" for s in seed_sample
            )

            prompt = (
                f"Here are some example coding instructions:\\n{seed_text}\\n\\n"
                "Generate 5 new, diverse coding instructions that are different "
                "from the examples. Each should require substantial code in the "
                "response. Format as a numbered list."
            )

            response = await self.client.messages.create(
                model=self.model, max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            for line in response.content[0].text.split("\\n"):
                line = line.strip()
                if line and line[0].isdigit():
                    inst = line.split(".", 1)[-1].strip()
                    if len(inst) > 20:
                        instructions.append(inst)

        return instructions


# === Rejection Sampling: generate many, keep best ===

@dataclass
class ScoredResponse:
    instruction: str
    response: str
    scores: dict[str, float]
    total_score: float


class RejectionSampler:
    """Generate N responses per prompt, keep top-K by quality."""

    def __init__(self, model: str = "claude-sonnet-4-6", n_samples: int = 4):
        self.client = AsyncAnthropic()
        self.model = model
        self.n_samples = n_samples

    async def sample_and_filter(
        self,
        instructions: list[str],
        top_k: int = 1,
        min_score: float = 0.7,
    ) -> list[ScoredResponse]:
        """Generate multiple responses, score, and keep best."""
        results = []

        for instruction in instructions:
            candidates = await self._generate_candidates(instruction)
            scored = [self._score(instruction, c) for c in candidates]
            scored.sort(key=lambda x: x.total_score, reverse=True)

            for s in scored[:top_k]:
                if s.total_score >= min_score:
                    results.append(s)

        return results

    async def _generate_candidates(self, instruction: str) -> list[str]:
        """Generate N diverse responses."""
        temps = [0.3, 0.7, 1.0, 1.3][:self.n_samples]
        tasks = []

        for temp in temps:
            tasks.append(self._generate_one(instruction, temp))

        return await asyncio.gather(*tasks)

    async def _generate_one(self, instruction: str, temperature: float) -> str:
        response = await self.client.messages.create(
            model=self.model, max_tokens=2048, temperature=temperature,
            messages=[{"role": "user", "content": instruction}],
        )
        return response.content[0].text

    def _score(self, instruction: str, response: str) -> ScoredResponse:
        """Multi-criteria quality scoring."""
        scores = {}

        # Length and substance
        scores["length"] = min(len(response) / 2000, 1.0)

        # Code blocks present
        code_blocks = response.count("```")
        scores["has_code"] = min(code_blocks / 4, 1.0)

        # Explanation depth
        headers = sum(1 for line in response.split("\\n") if line.startswith("#"))
        scores["structure"] = min(headers / 3, 1.0)

        # Not a refusal
        refusal_phrases = ["I cannot", "I'm sorry", "I can't help"]
        scores["not_refusal"] = 0.0 if any(p in response for p in refusal_phrases) else 1.0

        total = sum(scores.values()) / len(scores)
        return ScoredResponse(instruction, response, scores, total)


# === Quality Filtering Pipeline ===

def filter_dataset(
    pairs: list[dict],
    min_response_length: int = 200,
    min_code_blocks: int = 1,
    max_duplication_ratio: float = 0.3,
) -> list[dict]:
    """Filter training pairs for quality."""
    filtered = []
    seen_instructions = set()

    for pair in pairs:
        instruction = pair["instruction"]
        response = pair["response"]

        # Length check
        if len(response) < min_response_length:
            continue

        # Code block check
        if response.count("```") < min_code_blocks * 2:  # Opening + closing
            continue

        # Near-duplicate check (simple n-gram)
        inst_key = " ".join(instruction.lower().split()[:10])
        if inst_key in seen_instructions:
            continue
        seen_instructions.add(inst_key)

        # Refusal check
        if any(phrase in response[:200] for phrase in ["I cannot", "I'm unable"]):
            continue

        filtered.append(pair)

    return filtered
```

Synthetic data pipeline:
```
Seeds → Self-Instruct (generate instructions)
           ↓
         Evol-Instruct (increase complexity)
           ↓
         Rejection Sampling (N responses, keep best)
           ↓
         Quality Filtering (length, code, dedup)
           ↓
         Training Dataset
```

Key patterns:
1. **Evol-Instruct** — mutate instructions through 5 operators (constrain, deepen, concretize, multi-step, cross-domain)
2. **Self-Instruct** — few-shot prompt with seed examples generates diverse new instructions
3. **Rejection sampling** — generate N responses at different temperatures, score and keep top-K
4. **Quality filtering** — enforce minimums (length, code blocks, structure) and deduplicate
5. **Temperature diversity** — low temp (0.3) for accuracy, high temp (1.3) for creativity; best of N captures both'''
    ),
]
