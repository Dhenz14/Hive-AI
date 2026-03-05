"""P3 Batch: AI alignment techniques -- Constitutional AI, SPIN, online DPO, reward modeling, synthetic data."""

PAIRS = [
    (
        "constitutional AI and RLAIF alignment technique",
        "Explain Constitutional AI (CAI) and RLAIF in depth -- how AI feedback replaces human labelers in the alignment pipeline, the critique-revision-ranking loop, and how to implement CAI programmatically in Python. Compare the costs and quality trade-offs between RLAIF and traditional RLHF approaches, including common pitfalls and best practices for production deployment.",
        '''## Constitutional AI and RLAIF: Aligning Models Without Human Labelers

### The Core Problem with RLHF

Reinforcement Learning from Human Feedback (RLHF) is the dominant alignment paradigm, but it has a critical bottleneck: **human labelers are expensive, slow, inconsistent, and difficult to scale**. A single round of preference labeling for a frontier model can cost $500K+ and take weeks. Worse, human annotators disagree with each other 20-30% of the time on subjective judgments, introducing noise into the reward signal.

Constitutional AI (CAI), introduced by Anthropic in 2022, addresses this by replacing human feedback with AI feedback -- a technique called **Reinforcement Learning from AI Feedback (RLAIF)**. The key insight is that a language model can critique and revise its own outputs against a set of written principles (the "constitution"), producing preference data without any human in the loop.

### How the Critique-Revision-Ranking Pipeline Works

The CAI pipeline has two distinct phases:

- **Phase 1 -- Supervised Learning (SL-CAI):** The model generates responses, then critiques and revises them according to constitutional principles. The revised outputs become the supervised fine-tuning data.
- **Phase 2 -- Reinforcement Learning (RL-CAI):** The model generates pairs of responses, an AI judge ranks them according to the constitution, and these AI-generated preferences train a reward model for PPO.

The constitution itself is a set of natural language principles like: "Choose the response that is most helpful while being harmless" or "Prefer the answer that does not encourage illegal activity." Each principle addresses a specific failure mode. The beauty is that **you can modify alignment behavior by editing text, not retraining from scratch**.

### Implementing CAI in Python

```python
import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from openai import AsyncOpenAI


@dataclass
class ConstitutionalPrinciple:
    """A single principle in the constitution."""
    name: str
    critique_prompt: str
    revision_prompt: str
    weight: float = 1.0  # How much this principle matters in ranking


@dataclass
class CAIConfig:
    """Configuration for a Constitutional AI pipeline."""
    principles: list[ConstitutionalPrinciple] = field(default_factory=list)
    num_revisions: int = 3         # Rounds of critique-revision
    temperature_critique: float = 0.3
    temperature_revision: float = 0.7
    temperature_generation: float = 1.0
    model_name: str = "gpt-4"

    def validate(self) -> None:
        if not self.principles:
            raise ValueError("Constitution must have at least one principle")
        if self.num_revisions < 1:
            raise ValueError("Need at least one revision round")


DEFAULT_CONSTITUTION = [
    ConstitutionalPrinciple(
        name="helpfulness",
        critique_prompt=(
            "Identify ways in which the assistant's response is not helpful, "
            "accurate, or relevant to the user's question."
        ),
        revision_prompt=(
            "Revise the response to be more helpful, accurate, and directly "
            "relevant. Fix any factual errors."
        ),
        weight=1.5,
    ),
    ConstitutionalPrinciple(
        name="harmlessness",
        critique_prompt=(
            "Identify any content in the response that could be harmful, "
            "dangerous, unethical, or that encourages illegal activity."
        ),
        revision_prompt=(
            "Revise the response to remove all harmful content while keeping "
            "the helpful information intact."
        ),
        weight=2.0,
    ),
    ConstitutionalPrinciple(
        name="honesty",
        critique_prompt=(
            "Identify places where the response is misleading, overconfident, "
            "or fails to acknowledge uncertainty."
        ),
        revision_prompt=(
            "Revise the response to be more honest. Add uncertainty qualifiers "
            "where appropriate and correct any misleading claims."
        ),
        weight=1.0,
    ),
]
```

This defines the constitution as structured data -- each principle has both a critique prompt and a revision prompt. The weights allow you to prioritize certain principles (e.g., harmlessness weighted higher than helpfulness). Now implement the critique-revision loop:

```python
class ConstitutionalAIPipeline:
    """Full CAI pipeline: generate -> critique -> revise -> rank."""

    def __init__(self, config: CAIConfig, client: Optional[AsyncOpenAI] = None):
        self.config = config
        self.config.validate()
        self.client = client or AsyncOpenAI()

    async def _call_model(self, messages: list[dict], temperature: float) -> str:
        """Call the language model with error handling and retry logic."""
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=2048,
            )
            return response.choices[0].message.content
        except Exception as e:
            # Log and return empty -- don't crash the pipeline
            print(f"[CAI] Model call failed: {e}")
            return ""

    async def critique_response(
        self, prompt: str, response: str, principle: ConstitutionalPrinciple
    ) -> str:
        """Generate a critique of the response using a constitutional principle."""
        messages = [
            {"role": "system", "content": "You are a careful AI safety reviewer."},
            {"role": "user", "content": (
                f"Human request: {prompt}\\n\\n"
                f"Assistant response: {response}\\n\\n"
                f"Critique task: {principle.critique_prompt}\\n\\n"
                "Provide a specific, actionable critique."
            )},
        ]
        return await self._call_model(messages, self.config.temperature_critique)

    async def revise_response(
        self, prompt: str, response: str, critique: str,
        principle: ConstitutionalPrinciple
    ) -> str:
        """Revise the response based on a critique."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant revising your response."},
            {"role": "user", "content": (
                f"Original request: {prompt}\\n\\n"
                f"Your previous response: {response}\\n\\n"
                f"Critique: {critique}\\n\\n"
                f"Revision task: {principle.revision_prompt}\\n\\n"
                "Write the complete revised response."
            )},
        ]
        return await self._call_model(messages, self.config.temperature_revision)

    async def full_critique_revision(self, prompt: str, initial_response: str) -> str:
        """Run the full critique-revision loop across all principles."""
        current_response = initial_response

        for round_idx in range(self.config.num_revisions):
            for principle in self.config.principles:
                critique = await self.critique_response(
                    prompt, current_response, principle
                )
                if critique:  # Only revise if critique was generated
                    revised = await self.revise_response(
                        prompt, current_response, critique, principle
                    )
                    if revised:
                        current_response = revised

        return current_response

    async def rank_pair(self, prompt: str, response_a: str, response_b: str) -> dict:
        """AI judge ranks two responses according to the constitution."""
        scores = {"a": 0.0, "b": 0.0}
        for principle in self.config.principles:
            messages = [
                {"role": "system", "content": "You are an impartial judge."},
                {"role": "user", "content": (
                    f"Question: {prompt}\\n\\n"
                    f"Response A: {response_a}\\n\\n"
                    f"Response B: {response_b}\\n\\n"
                    f"Evaluation criterion: {principle.critique_prompt}\\n\\n"
                    "Which response is better? Answer 'A' or 'B' with a brief reason."
                )},
            ]
            judgment = await self._call_model(messages, 0.1)
            if "A" in judgment[:10]:
                scores["a"] += principle.weight
            else:
                scores["b"] += principle.weight

        return {
            "preferred": "a" if scores["a"] >= scores["b"] else "b",
            "scores": scores,
            "margin": abs(scores["a"] - scores["b"]),
        }
```

### Generating Preference Data at Scale

```python
async def generate_preference_dataset(
    pipeline: ConstitutionalAIPipeline,
    prompts: list[str],
    pairs_per_prompt: int = 4,
    batch_size: int = 10,
) -> list[dict]:
    """
    Generate a full preference dataset using RLAIF.

    This is the production-critical function. Common mistake: generating
    too few pairs per prompt. You need diversity in the preference data,
    so generate at least 4 pairs per prompt and use high temperature.
    """
    dataset = []

    for batch_start in range(0, len(prompts), batch_size):
        batch = prompts[batch_start:batch_start + batch_size]
        tasks = []

        for prompt in batch:
            for _ in range(pairs_per_prompt):
                tasks.append(_generate_single_pair(pipeline, prompt))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, dict):
                dataset.append(result)
            # Skip exceptions -- log them but don't crash the pipeline

    return dataset


async def _generate_single_pair(
    pipeline: ConstitutionalAIPipeline, prompt: str
) -> dict:
    """Generate one preference pair: two responses + AI ranking."""
    response_a = await pipeline._call_model(
        [{"role": "user", "content": prompt}],
        pipeline.config.temperature_generation,
    )
    response_b = await pipeline._call_model(
        [{"role": "user", "content": prompt}],
        pipeline.config.temperature_generation,
    )

    # Revise both through the constitution
    revised_a = await pipeline.full_critique_revision(prompt, response_a)
    revised_b = await pipeline.full_critique_revision(prompt, response_b)

    # AI judge ranks them
    ranking = await pipeline.rank_pair(prompt, revised_a, revised_b)

    return {
        "prompt": prompt,
        "chosen": revised_a if ranking["preferred"] == "a" else revised_b,
        "rejected": revised_b if ranking["preferred"] == "a" else revised_a,
        "margin": ranking["margin"],
    }
```

### RLAIF vs. RLHF: Cost and Quality Comparison

The trade-offs between RLAIF and RLHF are nuanced:

- **Cost**: RLAIF is 10-20x cheaper per preference label. Human labeling costs $1-5 per comparison; API-based AI labeling costs $0.05-0.20. However, RLAIF requires a strong base model as judge, which has its own costs.
- **Speed**: RLAIF can generate 100K preference pairs in hours. Human labeling the same volume takes weeks to months, even with a large annotation team.
- **Consistency**: AI judges are deterministic at low temperature. Human annotators show 20-30% inter-annotator disagreement. Consequently, RLAIF produces cleaner reward model training signal.
- **Ceiling quality**: This is where RLHF still wins. Human experts catch subtle errors and cultural nuances that AI judges miss. For frontier model alignment, a hybrid approach works best -- AI feedback for bulk data, human feedback for hard cases.
- **Pitfall -- constitutional drift**: If your constitution is poorly written, the AI judge will consistently reward the wrong behaviors. Best practice: start with Anthropic's published principles and iterate based on failure analysis.
- **Pitfall -- self-reinforcing bias**: Because the same model family generates, critiques, and judges, biases can amplify. Although using a different model as judge helps, the fundamental limitation remains.

### Performance Considerations for Production

For production deployment, you need to think about throughput and latency. The critique-revision loop makes 2N API calls per response (N principles x 2 for critique+revision), multiplied by the number of revision rounds. With 3 principles and 3 rounds, that is 18 API calls per response. Batching, caching, and async concurrency are essential.

Another best practice is **margin-based filtering**: only keep preference pairs where the AI judge's confidence margin exceeds a threshold. Low-margin pairs are ambiguous and add noise to reward model training. A common threshold is keeping only the top 70% by margin.

### Key Takeaways

- **Constitutional AI replaces human labelers** with a set of written principles that an AI uses to critique, revise, and rank model outputs, dramatically reducing alignment cost
- **The critique-revision loop** iteratively improves responses across multiple principles, and the number of rounds directly trades off quality against API cost
- **RLAIF is 10-20x cheaper** than RLHF and far faster, but human feedback still provides higher ceiling quality for frontier models -- use a hybrid approach
- **Common mistakes include** poorly written constitutions, insufficient pair diversity, and ignoring confidence margins when filtering preference data
- **Production systems must** batch API calls, filter by ranking margin, and use different model families for generation vs. judging to avoid self-reinforcing bias
'''
    ),
    (
        "SPIN self-play fine-tuning for language models",
        "Explain SPIN (Self-Play Fine-Tuning) in detail -- how the model plays against itself to improve without human preference data, the discriminator-generator dynamic, convergence properties, and when to stop training. Provide a complete PyTorch implementation with training loop, loss functions, and practical guidance on hyperparameters and common pitfalls.",
        '''## SPIN: Self-Play Fine-Tuning for Language Model Alignment

### The Core Idea: Model as Both Player and Opponent

Self-Play Fine-Tuning (SPIN), introduced by Chen et al. (2024), is an elegant alignment method that requires **no human preference labels at all** -- only a dataset of high-quality demonstrations. The key insight is borrowed from game theory: a model can improve by playing against a previous version of itself, similar to how AlphaGo improved through self-play.

The setup works as follows. You have two players: a **generator** (the current model being trained) and a **discriminator** (the model from the previous iteration). The generator tries to produce text that the discriminator cannot distinguish from real human-written demonstrations. The discriminator tries to tell apart real demonstrations from generated text. Because both roles are played by the same model architecture, this creates a minimax game that converges when the generator perfectly matches the target data distribution.

### Why SPIN Works: The Game-Theoretic Foundation

The theoretical foundation is a two-player zero-sum game. Let p_data be the distribution of human demonstrations and p_theta be the model's distribution. SPIN defines:

- **Generator objective**: Produce completions that are indistinguishable from real data
- **Discriminator objective**: Maximize the log-probability gap between real and generated data

The loss function is derived from a separation objective: the model should assign higher probability to real demonstrations than to its own generations. Consequently, at the Nash equilibrium, p_theta = p_data -- the model's distribution perfectly matches the data distribution.

This is fundamentally different from DPO or RLHF because **there is no preference data**. You only need (prompt, good_response) pairs, not (prompt, chosen, rejected) triples. This makes SPIN applicable when you have expert demonstrations but no comparative judgments.

### PyTorch Implementation

```python
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Optional
from dataclasses import dataclass
from copy import deepcopy
import logging

logger = logging.getLogger(__name__)


@dataclass
class SPINConfig:
    """Configuration for SPIN training."""
    model_name: str = "meta-llama/Llama-2-7b-chat-hf"
    learning_rate: float = 5e-7       # Very low LR -- critical for stability
    beta: float = 0.1                  # Temperature for the logit difference
    lambda_reg: float = 0.1            # Regularization toward reference model
    max_iterations: int = 3            # Number of self-play iterations
    epochs_per_iteration: int = 2      # Epochs within each iteration
    batch_size: int = 4
    max_length: int = 1024
    gradient_accumulation_steps: int = 8
    convergence_threshold: float = 0.01  # Stop when loss change < this

    def effective_batch_size(self) -> int:
        return self.batch_size * self.gradient_accumulation_steps


class SPINDataset(Dataset):
    """Dataset that holds real demonstrations and generated responses."""

    def __init__(
        self,
        prompts: list[str],
        real_responses: list[str],
        generated_responses: list[str],
        tokenizer: AutoTokenizer,
        max_length: int = 1024,
    ):
        self.prompts = prompts
        self.real_responses = real_responses
        self.generated_responses = generated_responses
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.prompts)

    def __getitem__(self, idx: int) -> dict:
        prompt = self.prompts[idx]
        real = self.real_responses[idx]
        generated = self.generated_responses[idx]

        real_text = f"{prompt}\\n{real}"
        gen_text = f"{prompt}\\n{generated}"

        real_tokens = self.tokenizer(
            real_text, truncation=True, max_length=self.max_length,
            padding="max_length", return_tensors="pt"
        )
        gen_tokens = self.tokenizer(
            gen_text, truncation=True, max_length=self.max_length,
            padding="max_length", return_tensors="pt"
        )

        return {
            "real_input_ids": real_tokens["input_ids"].squeeze(0),
            "real_attention_mask": real_tokens["attention_mask"].squeeze(0),
            "gen_input_ids": gen_tokens["input_ids"].squeeze(0),
            "gen_attention_mask": gen_tokens["attention_mask"].squeeze(0),
            "prompt_length": len(self.tokenizer.encode(prompt)),
        }
```

Now implement the core SPIN loss function and the training loop:

```python
def compute_spin_loss(
    model: AutoModelForCausalLM,
    batch: dict,
    beta: float = 0.1,
    lambda_reg: float = 0.1,
    reference_model: Optional[AutoModelForCausalLM] = None,
) -> torch.Tensor:
    """
    Compute the SPIN loss: maximize log-prob gap between real and generated.

    The loss encourages the model to assign higher probability to real
    demonstrations than to its own previous generations. This is the
    core of the self-play dynamic.

    Common mistake: forgetting to mask the prompt tokens. You only want
    the loss computed on the response portion, not the prompt.
    """
    device = next(model.parameters()).device

    # Forward pass on real demonstrations
    real_outputs = model(
        input_ids=batch["real_input_ids"].to(device),
        attention_mask=batch["real_attention_mask"].to(device),
    )
    # Forward pass on generated responses
    gen_outputs = model(
        input_ids=batch["gen_input_ids"].to(device),
        attention_mask=batch["gen_attention_mask"].to(device),
    )

    # Compute per-token log probabilities (shift for autoregressive)
    real_logps = _compute_sequence_logprobs(
        real_outputs.logits, batch["real_input_ids"].to(device),
        batch["real_attention_mask"].to(device), batch["prompt_length"]
    )
    gen_logps = _compute_sequence_logprobs(
        gen_outputs.logits, batch["gen_input_ids"].to(device),
        batch["gen_attention_mask"].to(device), batch["prompt_length"]
    )

    # SPIN loss: logistic separation
    logit_diff = beta * (real_logps - gen_logps)
    spin_loss = -F.logsigmoid(logit_diff).mean()

    # Optional: KL regularization toward reference model
    if reference_model is not None:
        with torch.no_grad():
            ref_real = reference_model(
                input_ids=batch["real_input_ids"].to(device),
                attention_mask=batch["real_attention_mask"].to(device),
            )
        ref_logps = _compute_sequence_logprobs(
            ref_real.logits, batch["real_input_ids"].to(device),
            batch["real_attention_mask"].to(device), batch["prompt_length"]
        )
        kl_penalty = (real_logps - ref_logps).pow(2).mean()
        spin_loss = spin_loss + lambda_reg * kl_penalty

    return spin_loss


def _compute_sequence_logprobs(
    logits: torch.Tensor,
    labels: torch.Tensor,
    attention_mask: torch.Tensor,
    prompt_length: int,
) -> torch.Tensor:
    """Compute average log-prob of the response tokens only."""
    # Shift: logits[t] predicts labels[t+1]
    shift_logits = logits[:, :-1, :].contiguous()
    shift_labels = labels[:, 1:].contiguous()
    shift_mask = attention_mask[:, 1:].contiguous()

    # Mask out prompt tokens -- only score the response
    response_mask = shift_mask.clone()
    response_mask[:, :prompt_length] = 0

    log_probs = F.log_softmax(shift_logits, dim=-1)
    token_logps = log_probs.gather(2, shift_labels.unsqueeze(-1)).squeeze(-1)
    token_logps = token_logps * response_mask

    # Average over response tokens
    return token_logps.sum(dim=-1) / response_mask.sum(dim=-1).clamp(min=1)
```

The outer self-play loop that orchestrates the iterative training:

```python
class SPINTrainer:
    """Full SPIN training loop with self-play iterations."""

    def __init__(self, config: SPINConfig):
        self.config = config
        self.tokenizer = AutoTokenizer.from_pretrained(config.model_name)
        self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            config.model_name, torch_dtype=torch.bfloat16
        )
        self.reference_model = deepcopy(self.model)
        self.reference_model.eval()

    @torch.no_grad()
    def generate_responses(self, prompts: list[str]) -> list[str]:
        """Generate responses using the current model (opponent's turn)."""
        self.model.eval()
        responses = []
        for prompt in prompts:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(
                next(self.model.parameters()).device
            )
            try:
                output_ids = self.model.generate(
                    **inputs, max_new_tokens=512,
                    temperature=0.7, do_sample=True, top_p=0.9,
                )
                response = self.tokenizer.decode(
                    output_ids[0][inputs["input_ids"].shape[1]:],
                    skip_special_tokens=True,
                )
                responses.append(response)
            except RuntimeError as e:
                logger.warning(f"Generation failed for prompt: {e}")
                responses.append("")  # Fallback to empty
        self.model.train()
        return responses

    def train(
        self, prompts: list[str], real_responses: list[str]
    ) -> dict[str, list[float]]:
        """
        Run the full SPIN self-play training procedure.

        Best practice: monitor the logit gap between real and generated.
        When it stops increasing, the model has converged -- further
        iterations will not help and may cause overfitting.
        """
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(device)
        self.reference_model.to(device)
        history = {"loss": [], "logit_gap": []}

        for iteration in range(self.config.max_iterations):
            logger.info(f"SPIN iteration {iteration + 1}/{self.config.max_iterations}")

            # Step 1: Generate synthetic responses (opponent's move)
            generated = self.generate_responses(prompts)

            # Step 2: Build dataset with real vs generated pairs
            dataset = SPINDataset(
                prompts, real_responses, generated,
                self.tokenizer, self.config.max_length,
            )
            loader = DataLoader(
                dataset, batch_size=self.config.batch_size, shuffle=True
            )

            # Step 3: Train to distinguish real from generated
            optimizer = torch.optim.AdamW(
                self.model.parameters(), lr=self.config.learning_rate
            )
            epoch_losses = []

            for epoch in range(self.config.epochs_per_iteration):
                total_loss = 0.0
                optimizer.zero_grad()

                for step, batch in enumerate(loader):
                    loss = compute_spin_loss(
                        self.model, batch, self.config.beta,
                        self.config.lambda_reg, self.reference_model,
                    )
                    loss = loss / self.config.gradient_accumulation_steps
                    loss.backward()

                    if (step + 1) % self.config.gradient_accumulation_steps == 0:
                        torch.nn.utils.clip_grad_norm_(
                            self.model.parameters(), 1.0
                        )
                        optimizer.step()
                        optimizer.zero_grad()

                    total_loss += loss.item()

                avg_loss = total_loss / max(len(loader), 1)
                epoch_losses.append(avg_loss)
                logger.info(f"  Epoch {epoch+1} loss: {avg_loss:.4f}")

            history["loss"].extend(epoch_losses)

            # Convergence check: stop if loss barely changed
            if len(history["loss"]) >= 2:
                delta = abs(history["loss"][-1] - history["loss"][-2])
                if delta < self.config.convergence_threshold:
                    logger.info(f"Converged at iteration {iteration+1} (delta={delta:.5f})")
                    break

            # Update opponent: current model becomes next iteration's reference
            self.reference_model = deepcopy(self.model)
            self.reference_model.eval()

        return history
```

### Convergence Properties and When to Stop

SPIN has a provable fixed point: training converges when the model's distribution matches the target data distribution. In practice, this means:

- **Iteration 1** gives the largest improvement -- typically 60-70% of the total gain
- **Iteration 2** gives diminishing but meaningful returns
- **Iteration 3+** often shows minimal improvement, and continuing can cause overfitting

The convergence signal is the **logit gap** between real and generated data. When this gap stops increasing, the model can no longer distinguish its own outputs from the training data -- it has reached equilibrium. Although running more iterations is tempting, pushing past convergence degrades performance because the model starts memorizing training examples rather than learning the distribution.

### Trade-offs and Practical Guidance

- **Advantage over DPO/RLHF**: No preference labels needed -- only demonstrations. This makes SPIN ideal when you have expert outputs but no comparative judgments.
- **Learning rate is critical**: Use 5e-7 to 1e-6 -- much lower than standard SFT. Higher rates cause catastrophic forgetting because the self-play signal is subtle.
- **Batch size matters**: Larger effective batch sizes (32+) stabilize the logit gap estimation. Use gradient accumulation if GPU memory is limited.
- **Common pitfall -- data quality**: SPIN converges to match the training data distribution. If your demonstrations are noisy or inconsistent, the model will faithfully reproduce that noise. Therefore, invest heavily in data quality before running SPIN.
- **Common pitfall -- prompt masking**: Forgetting to mask prompt tokens in the loss computation causes the model to overfit on prompt patterns rather than learning response quality.

### Key Takeaways

- **SPIN uses self-play** to align models using only demonstration data -- no human preference labels required -- making it uniquely suited for domains where expert outputs exist but comparative judgments are expensive
- **The minimax game** between generator and discriminator has a provable Nash equilibrium at p_theta = p_data, providing theoretical convergence guarantees
- **Iteration 1 captures most gains** (60-70%), and training should stop when the logit gap between real and generated data plateaus -- typically after 2-3 iterations
- **Critical hyperparameters** are learning rate (5e-7 to 1e-6), beta (0.05-0.2), and effective batch size (32+) -- getting these wrong causes either divergence or overfitting
- **Data quality is paramount** because SPIN converges to match the training distribution exactly, amplifying any noise or inconsistency in the demonstrations
'''
    ),
    (
        "online DPO iterative alignment with rejection sampling",
        "Explain online DPO and iterative alignment in depth -- how online DPO differs from offline DPO, the process of generating new preference data during training, the exploration-exploitation tradeoff, rejection sampling strategies, and a complete implementation using the TRL library. Include practical advice on when to use online vs offline DPO and common pitfalls to avoid in production alignment pipelines.",
        '''## Online DPO and Iterative Alignment: Closing the Distribution Gap

### The Problem with Offline DPO

Standard Direct Preference Optimization (DPO) is an **offline** method: you collect a static dataset of (prompt, chosen, rejected) triples, train the model once, and ship it. This is simple but has a fundamental flaw -- **distribution shift**. The preference data was generated by a different model (the SFT model or a previous checkpoint), so the policy being trained never sees feedback on its own outputs.

Consequently, offline DPO often produces models that are well-calibrated on training prompts but behave unpredictably on out-of-distribution inputs. The model learns to avoid specific bad responses it saw during training, but it does not learn a general principle for what makes responses good. Research from Meta and Google has shown that online DPO closes this gap, producing models that generalize 15-25% better on held-out evaluations.

### How Online DPO Works

Online DPO adds an **iterative generation loop** to the standard DPO pipeline:

1. **Generate**: The current policy generates multiple candidate responses for each prompt
2. **Score**: A reward model (or AI judge) scores each candidate
3. **Select**: The best and worst responses become the new (chosen, rejected) pair
4. **Train**: One DPO update step using the freshly generated preference data
5. **Repeat**: Go to step 1 with the updated policy

The critical difference is that the preference data comes from **the current policy**, not a static dataset. This eliminates distribution shift because the model always trains on feedback about its own behavior. However, this introduces a new challenge: the **exploration-exploitation tradeoff**.

### Exploration vs. Exploitation in Online DPO

- **Exploitation**: Use low temperature to generate high-quality responses, maximizing immediate reward. The risk is that the model never explores novel response strategies and gets stuck in a local optimum.
- **Exploration**: Use high temperature to generate diverse responses, discovering new strategies. The risk is wasting compute on low-quality responses that provide weak training signal.

The best practice is a **decaying temperature schedule**: start with high temperature (1.0-1.2) in early iterations to explore broadly, then anneal to lower temperature (0.6-0.8) as the model improves. This mirrors the epsilon-greedy strategy from reinforcement learning.

### Rejection Sampling: The Quality Filter

Not all generated pairs are equally useful for training. **Rejection sampling** filters pairs to keep only high-quality training signal:

- **Best-of-N sampling**: Generate N responses per prompt, score all of them, keep the highest and lowest as the preference pair. Larger N gives better pairs but costs more compute.
- **Margin filtering**: Only keep pairs where the reward gap between chosen and rejected exceeds a threshold. Low-margin pairs are ambiguous and add noise.
- **Diversity filtering**: Avoid keeping pairs that are too similar -- if the chosen and rejected responses differ by only a few tokens, the training signal is too weak.

### Implementation with TRL

```python
import torch
from dataclasses import dataclass, field
from typing import Optional
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DPOTrainer, DPOConfig
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class OnlineDPOConfig:
    """Configuration for online iterative DPO training."""
    model_name: str = "meta-llama/Llama-2-7b-chat-hf"
    reward_model_name: str = "OpenAssistant/reward-model-deberta-v3-large"
    num_iterations: int = 5
    num_candidates: int = 8        # Best-of-N -- generate this many per prompt
    min_reward_margin: float = 0.5  # Reject pairs with smaller margin
    temperature_start: float = 1.0
    temperature_end: float = 0.7
    dpo_beta: float = 0.1           # KL penalty coefficient
    learning_rate: float = 5e-7
    batch_size: int = 4
    max_length: int = 1024
    max_prompt_length: int = 512

    def temperature_at_iteration(self, iteration: int) -> float:
        """Linear temperature decay schedule."""
        progress = iteration / max(self.num_iterations - 1, 1)
        return self.temperature_start + progress * (
            self.temperature_end - self.temperature_start
        )


class RewardScorer:
    """Score responses using a reward model for preference ranking."""

    def __init__(self, model_name: str, device: str = "cuda"):
        from transformers import pipeline
        try:
            self.pipe = pipeline(
                "text-classification", model=model_name, device=device,
                torch_dtype=torch.bfloat16,
            )
        except Exception as e:
            logger.error(f"Failed to load reward model: {e}")
            raise

    def score(self, prompt: str, response: str) -> float:
        """Score a single prompt-response pair."""
        try:
            text = f"Human: {prompt}\\nAssistant: {response}"
            result = self.pipe(text, truncation=True, max_length=1024)
            return result[0]["score"]
        except Exception as e:
            logger.warning(f"Scoring failed: {e}")
            return 0.0  # Neutral score on failure

    def score_batch(
        self, prompt: str, responses: list[str]
    ) -> list[float]:
        """Score multiple responses for the same prompt."""
        return [self.score(prompt, r) for r in responses]
```

Now implement the online generation and pair selection pipeline:

```python
class OnlineDPOPipeline:
    """
    Online DPO training with iterative preference data generation.

    The pipeline alternates between generating new preference pairs
    from the current policy and running DPO training updates. This
    eliminates distribution shift -- the most common pitfall of
    offline DPO.
    """

    def __init__(self, config: OnlineDPOConfig):
        self.config = config
        self.tokenizer = AutoTokenizer.from_pretrained(config.model_name)
        self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            config.model_name, torch_dtype=torch.bfloat16
        )
        self.ref_model = AutoModelForCausalLM.from_pretrained(
            config.model_name, torch_dtype=torch.bfloat16
        )
        self.scorer = RewardScorer(config.reward_model_name)

    @torch.no_grad()
    def generate_candidates(
        self, prompt: str, n: int, temperature: float
    ) -> list[str]:
        """Generate N candidate responses for rejection sampling."""
        self.model.eval()
        device = next(self.model.parameters()).device
        inputs = self.tokenizer(prompt, return_tensors="pt").to(device)
        candidates = []

        for _ in range(n):
            try:
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=512,
                    temperature=temperature,
                    do_sample=True,
                    top_p=0.95,
                    top_k=50,
                )
                response = self.tokenizer.decode(
                    output[0][inputs["input_ids"].shape[1]:],
                    skip_special_tokens=True,
                )
                candidates.append(response)
            except RuntimeError as e:
                logger.warning(f"Generation failed: {e}")
                continue

        self.model.train()
        return candidates

    def select_preference_pair(
        self, prompt: str, candidates: list[str], min_margin: float
    ) -> Optional[dict]:
        """
        Select best and worst response as preference pair.

        Best practice: use margin filtering to avoid noisy pairs.
        A common mistake is keeping all pairs regardless of reward
        gap -- this adds noise that degrades DPO training.
        """
        if len(candidates) < 2:
            return None

        scores = self.scorer.score_batch(prompt, candidates)
        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        best_response, best_score = scored[0]
        worst_response, worst_score = scored[-1]
        margin = best_score - worst_score

        # Reject pairs with insufficient margin
        if margin < min_margin:
            return None

        return {
            "prompt": prompt,
            "chosen": best_response,
            "rejected": worst_response,
            "chosen_score": best_score,
            "rejected_score": worst_score,
            "margin": margin,
        }

    def generate_preference_dataset(
        self, prompts: list[str], iteration: int
    ) -> Dataset:
        """Generate an entire preference dataset from current policy."""
        temperature = self.config.temperature_at_iteration(iteration)
        logger.info(
            f"Generating preference data: iteration={iteration}, "
            f"temp={temperature:.2f}, N={self.config.num_candidates}"
        )

        pairs = []
        for prompt in prompts:
            candidates = self.generate_candidates(
                prompt, self.config.num_candidates, temperature
            )
            pair = self.select_preference_pair(
                prompt, candidates, self.config.min_reward_margin
            )
            if pair is not None:
                pairs.append(pair)

        logger.info(
            f"Generated {len(pairs)} valid pairs from {len(prompts)} prompts "
            f"({len(pairs)/len(prompts)*100:.1f}% yield)"
        )

        return Dataset.from_list(pairs)

    def train(self, prompts: list[str]) -> dict[str, list]:
        """Run the full online DPO iterative training loop."""
        history = {"iteration_loss": [], "pair_yield": [], "avg_margin": []}

        for iteration in range(self.config.num_iterations):
            logger.info(f"=== Online DPO Iteration {iteration+1} ===")

            # Step 1: Generate preference data from current policy
            pref_dataset = self.generate_preference_dataset(prompts, iteration)

            if len(pref_dataset) < self.config.batch_size:
                logger.warning("Too few valid pairs -- skipping iteration")
                continue

            # Step 2: Run DPO training on the fresh data
            dpo_config = DPOConfig(
                output_dir=f"./checkpoints/online_dpo_iter{iteration}",
                per_device_train_batch_size=self.config.batch_size,
                learning_rate=self.config.learning_rate,
                beta=self.config.dpo_beta,
                max_length=self.config.max_length,
                max_prompt_length=self.config.max_prompt_length,
                num_train_epochs=1,  # Single epoch per iteration
                logging_steps=10,
                gradient_accumulation_steps=4,
                bf16=True,
                remove_unused_columns=False,
            )

            trainer = DPOTrainer(
                model=self.model,
                ref_model=self.ref_model,
                args=dpo_config,
                train_dataset=pref_dataset,
                processing_class=self.tokenizer,
            )

            try:
                train_result = trainer.train()
                history["iteration_loss"].append(train_result.training_loss)
            except Exception as e:
                logger.error(f"DPO training failed at iteration {iteration}: {e}")
                continue

            margins = [p["margin"] for p in pref_dataset]
            history["pair_yield"].append(len(pref_dataset) / len(prompts))
            history["avg_margin"].append(np.mean(margins))

        return history
```

### When to Use Online vs. Offline DPO

The choice depends on your constraints:

- **Use offline DPO** when you have a high-quality static preference dataset (e.g., from human annotators), limited compute budget, or need reproducible training. Offline DPO is simpler to debug because the data is fixed.
- **Use online DPO** when you need the model to generalize beyond the training distribution, have access to a reliable reward model, and can afford the extra compute. Online DPO is 3-5x more expensive per training run because of the generation overhead.
- **Hybrid approach**: Start with offline DPO on existing preference data, then run 2-3 online iterations to close the distribution gap. This gives you the best of both approaches.

### Common Pitfalls to Avoid

- **Reward model quality**: Online DPO is only as good as your reward model. If the reward model has blind spots, online DPO will exploit them -- this is a form of Goodhart's law. Best practice: use an ensemble of reward models.
- **KL divergence explosion**: Without proper beta tuning, the policy can drift too far from the reference model. Monitor KL divergence and increase beta if it exceeds 10-15 nats.
- **Temperature too low**: Setting temperature below 0.5 during generation produces near-identical candidates, making rejection sampling useless. Although low temperature gives higher individual quality, you need diversity for meaningful preference pairs.
- **Not refreshing the reference model**: In iterative online DPO, the reference model should be the initial SFT model, not the previous iteration. Using a moving reference creates a compounding drift.

### Key Takeaways

- **Online DPO eliminates distribution shift** by generating preference data from the current policy, producing models that generalize 15-25% better than offline DPO on out-of-distribution inputs
- **Rejection sampling with margin filtering** is essential for data quality -- keep only pairs where the reward gap exceeds a threshold (typically 0.3-0.5)
- **Temperature annealing** (1.0 to 0.7 over iterations) balances exploration and exploitation, avoiding both local optima and wasted compute
- **The hybrid approach** (offline DPO first, then online iterations) provides the best cost-quality tradeoff for most production scenarios
- **Monitor KL divergence** carefully and use reward model ensembles to prevent Goodhart's law exploitation in the online setting
'''
    ),
    (
        "reward model training from preference data alignment",
        "Explain how to train a reward model from human preference data for RLHF alignment -- covering the Bradley-Terry preference model, calibration techniques, over-optimization and Goodhart's law, ensemble reward models, and a complete code implementation in PyTorch. Include best practices for production reward model training, common pitfalls, and how to diagnose reward model failures.",
        '''## Reward Model Training: The Backbone of RLHF Alignment

### Why Reward Models Matter

The reward model (RM) is the most critical component in the RLHF pipeline, yet it receives the least attention. A flawed reward model does not just produce mediocre alignment -- it actively teaches the policy model to exploit weaknesses, producing outputs that score high on the reward signal but are actually worse by human judgment. This is **Goodhart's law** applied to AI alignment: "When a measure becomes a target, it ceases to be a good measure."

Training a robust reward model requires understanding the mathematical foundations, calibration challenges, and failure modes. Because every dollar spent on reward model quality multiplies through the entire alignment pipeline, getting this right is the highest-leverage investment in RLHF.

### The Bradley-Terry Preference Model

The standard framework for reward modeling is the **Bradley-Terry model**, which assumes human preference between two responses can be modeled as:

P(response_a > response_b) = sigmoid(r(a) - r(b))

Where r(x) is the scalar reward assigned to response x. This gives us a straightforward training objective: maximize the log-likelihood of the observed human preferences. The loss function is:

L = -E[log(sigmoid(r(chosen) - r(rejected)))]

This is mathematically equivalent to binary cross-entropy where the target is always 1 (the chosen response is always preferred). Although simple, this model has important assumptions: preferences are transitive, context-independent, and the reward is a scalar. All of these assumptions break in practice, which is why calibration and ensembling matter.

### PyTorch Implementation

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer, AutoConfig
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class RewardModelConfig:
    """Configuration for reward model training."""
    base_model: str = "meta-llama/Llama-2-7b-hf"
    learning_rate: float = 1e-5
    weight_decay: float = 0.01
    batch_size: int = 8
    num_epochs: int = 2
    max_length: int = 1024
    margin_target: float = 0.0     # Target margin for calibration
    label_smoothing: float = 0.0   # Smooth labels to handle annotator noise
    gradient_accumulation_steps: int = 4
    warmup_ratio: float = 0.1
    freeze_layers: int = 0         # Freeze bottom N transformer layers


class RewardModel(nn.Module):
    """
    Reward model: transformer backbone + scalar value head.

    Architecture: we take the last hidden state at the final token
    position and project it to a scalar reward. This is standard
    but has a subtle issue: the reward depends on which token is
    "last," so padding must be handled correctly.
    """

    def __init__(self, config: RewardModelConfig):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(
            config.base_model, torch_dtype=torch.bfloat16
        )
        hidden_size = self.backbone.config.hidden_size

        # Value head: project hidden states to scalar reward
        self.value_head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_size // 2, 1),
        )

        # Optionally freeze bottom layers for efficiency
        if config.freeze_layers > 0:
            self._freeze_bottom_layers(config.freeze_layers)

    def _freeze_bottom_layers(self, n: int) -> None:
        """Freeze the bottom N transformer layers."""
        for param in self.backbone.embed_tokens.parameters():
            param.requires_grad = False
        for i, layer in enumerate(self.backbone.layers):
            if i < n:
                for param in layer.parameters():
                    param.requires_grad = False

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """
        Compute scalar reward for each sequence in the batch.

        Common mistake: using the [CLS] token position instead of the
        last real token. For decoder-only models, there is no [CLS] --
        use the last non-padding token instead.
        """
        outputs = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )
        hidden_states = outputs.last_hidden_state

        # Find the last real token position (before padding)
        sequence_lengths = attention_mask.sum(dim=1) - 1
        batch_indices = torch.arange(
            hidden_states.size(0), device=hidden_states.device
        )
        last_hidden = hidden_states[batch_indices, sequence_lengths]

        rewards = self.value_head(last_hidden).squeeze(-1)
        return rewards
```

Now implement the training pipeline with calibration and diagnostics:

```python
class PreferenceDataset(Dataset):
    """Dataset of preference pairs for reward model training."""

    def __init__(
        self,
        prompts: list[str],
        chosen_responses: list[str],
        rejected_responses: list[str],
        tokenizer: AutoTokenizer,
        max_length: int = 1024,
    ):
        self.chosen_texts = [
            f"{p}\\n{c}" for p, c in zip(prompts, chosen_responses)
        ]
        self.rejected_texts = [
            f"{p}\\n{r}" for p, r in zip(prompts, rejected_responses)
        ]
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.chosen_texts)

    def __getitem__(self, idx: int) -> dict:
        chosen = self.tokenizer(
            self.chosen_texts[idx], truncation=True,
            max_length=self.max_length, padding="max_length",
            return_tensors="pt",
        )
        rejected = self.tokenizer(
            self.rejected_texts[idx], truncation=True,
            max_length=self.max_length, padding="max_length",
            return_tensors="pt",
        )
        return {
            "chosen_ids": chosen["input_ids"].squeeze(0),
            "chosen_mask": chosen["attention_mask"].squeeze(0),
            "rejected_ids": rejected["input_ids"].squeeze(0),
            "rejected_mask": rejected["attention_mask"].squeeze(0),
        }


def compute_reward_loss(
    model: RewardModel,
    batch: dict,
    label_smoothing: float = 0.0,
    margin_target: float = 0.0,
) -> dict[str, torch.Tensor]:
    """
    Bradley-Terry preference loss with optional calibration.

    The margin_target parameter adds a soft constraint that the reward
    difference between chosen and rejected should approximate a target
    value. This helps with calibration -- without it, rewards can drift
    to arbitrary scale, which causes instability in downstream PPO.
    """
    device = next(model.parameters()).device

    chosen_rewards = model(
        batch["chosen_ids"].to(device),
        batch["chosen_mask"].to(device),
    )
    rejected_rewards = model(
        batch["rejected_ids"].to(device),
        batch["rejected_mask"].to(device),
    )

    reward_diff = chosen_rewards - rejected_rewards

    # Bradley-Terry loss (with optional label smoothing)
    if label_smoothing > 0:
        # Smooth toward 50/50 -- handles noisy human labels
        target = torch.ones_like(reward_diff) * (1.0 - label_smoothing)
        bt_loss = F.binary_cross_entropy_with_logits(
            reward_diff, target
        )
    else:
        bt_loss = -F.logsigmoid(reward_diff).mean()

    # Calibration loss: push reward margin toward target
    cal_loss = (reward_diff - margin_target).pow(2).mean()

    # Reward magnitude regularization: prevent reward scale explosion
    mag_loss = (chosen_rewards.pow(2).mean() + rejected_rewards.pow(2).mean()) * 0.01

    total_loss = bt_loss + 0.1 * cal_loss + mag_loss

    return {
        "loss": total_loss,
        "bt_loss": bt_loss.detach(),
        "accuracy": (reward_diff > 0).float().mean().detach(),
        "avg_margin": reward_diff.mean().detach(),
        "chosen_mean": chosen_rewards.mean().detach(),
        "rejected_mean": rejected_rewards.mean().detach(),
    }
```

The full training loop with diagnostics for detecting reward model failures:

```python
class RewardModelTrainer:
    """Full reward model training with calibration and diagnostics."""

    def __init__(self, config: RewardModelConfig):
        self.config = config
        self.tokenizer = AutoTokenizer.from_pretrained(config.base_model)
        self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = RewardModel(config)

    def train(
        self,
        prompts: list[str],
        chosen: list[str],
        rejected: list[str],
        val_prompts: Optional[list[str]] = None,
        val_chosen: Optional[list[str]] = None,
        val_rejected: Optional[list[str]] = None,
    ) -> dict:
        """
        Train the reward model with comprehensive diagnostics.

        Best practice: always hold out 10-20% of preference data for
        validation. The most dangerous failure mode is a reward model
        that has high training accuracy but poor generalization -- this
        leads to severe over-optimization during PPO.
        """
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(device)

        dataset = PreferenceDataset(
            prompts, chosen, rejected, self.tokenizer, self.config.max_length
        )
        loader = DataLoader(
            dataset, batch_size=self.config.batch_size, shuffle=True
        )

        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        # Linear warmup schedule
        total_steps = len(loader) * self.config.num_epochs
        warmup_steps = int(total_steps * self.config.warmup_ratio)

        history = {
            "train_loss": [], "train_acc": [], "val_acc": [],
            "avg_margin": [], "reward_std": [],
        }

        for epoch in range(self.config.num_epochs):
            self.model.train()
            epoch_metrics = {"loss": 0, "acc": 0, "margin": 0, "steps": 0}
            optimizer.zero_grad()

            for step, batch in enumerate(loader):
                metrics = compute_reward_loss(
                    self.model, batch,
                    self.config.label_smoothing,
                    self.config.margin_target,
                )

                loss = metrics["loss"] / self.config.gradient_accumulation_steps
                loss.backward()

                if (step + 1) % self.config.gradient_accumulation_steps == 0:
                    torch.nn.utils.clip_grad_norm_(
                        self.model.parameters(), 1.0
                    )
                    optimizer.step()
                    optimizer.zero_grad()

                epoch_metrics["loss"] += metrics["loss"].item()
                epoch_metrics["acc"] += metrics["accuracy"].item()
                epoch_metrics["margin"] += metrics["avg_margin"].item()
                epoch_metrics["steps"] += 1

            n = max(epoch_metrics["steps"], 1)
            train_acc = epoch_metrics["acc"] / n
            history["train_loss"].append(epoch_metrics["loss"] / n)
            history["train_acc"].append(train_acc)
            history["avg_margin"].append(epoch_metrics["margin"] / n)

            # Validation
            if val_prompts is not None:
                val_acc = self._evaluate(val_prompts, val_chosen, val_rejected)
                history["val_acc"].append(val_acc)
                self._check_diagnostics(train_acc, val_acc, epoch)

            logger.info(
                f"Epoch {epoch+1}: loss={history['train_loss'][-1]:.4f}, "
                f"acc={train_acc:.3f}, margin={history['avg_margin'][-1]:.3f}"
            )

        return history

    @torch.no_grad()
    def _evaluate(
        self, prompts: list[str], chosen: list[str], rejected: list[str]
    ) -> float:
        """Evaluate reward model accuracy on held-out preferences."""
        self.model.eval()
        device = next(self.model.parameters()).device
        correct = 0

        for p, c, r in zip(prompts, chosen, rejected):
            c_tok = self.tokenizer(
                f"{p}\\n{c}", return_tensors="pt", truncation=True,
                max_length=self.config.max_length,
            )
            r_tok = self.tokenizer(
                f"{p}\\n{r}", return_tensors="pt", truncation=True,
                max_length=self.config.max_length,
            )
            c_reward = self.model(c_tok["input_ids"].to(device), c_tok["attention_mask"].to(device))
            r_reward = self.model(r_tok["input_ids"].to(device), r_tok["attention_mask"].to(device))
            if c_reward.item() > r_reward.item():
                correct += 1

        return correct / max(len(prompts), 1)

    def _check_diagnostics(
        self, train_acc: float, val_acc: float, epoch: int
    ) -> None:
        """Check for common reward model failure modes."""
        # Overfitting detection
        if train_acc - val_acc > 0.1:
            logger.warning(
                f"[DIAGNOSTIC] Overfitting detected at epoch {epoch+1}: "
                f"train_acc={train_acc:.3f}, val_acc={val_acc:.3f}. "
                "Consider more data, regularization, or early stopping."
            )
        # Underfitting detection
        if train_acc < 0.55:
            logger.warning(
                f"[DIAGNOSTIC] Underfitting at epoch {epoch+1}: "
                f"train_acc={train_acc:.3f}. Model may need higher LR "
                "or the preference data may be too noisy."
            )
        # Random performance
        if val_acc < 0.52:
            logger.warning(
                f"[DIAGNOSTIC] Near-random validation accuracy: {val_acc:.3f}. "
                "The reward model is not learning useful preferences."
            )
```

### Goodhart's Law and Over-Optimization

The most insidious problem in reward model training is **over-optimization**: the policy model learns to exploit reward model blind spots, producing outputs that score high but are actually low quality. This happens because:

- The reward model is a **proxy** for human judgment, not a perfect measure
- The policy optimizer (PPO) is powerful enough to find adversarial inputs that maximize the proxy while diverging from the true objective
- Longer training amplifies this divergence -- there is a sweet spot after which more RL training makes the model worse

Mitigation strategies include:

- **Ensemble reward models**: Train 3-5 reward models on different data splits and average their scores. Disagreement between ensemble members is a signal that the policy is in an adversarial region.
- **KL penalty**: Penalize divergence from the reference model during PPO. This limits how far the policy can exploit the reward model.
- **Reward model refresh**: Periodically retrain the reward model on data generated by the current policy. This closes the gap between the reward model's training distribution and the policy's behavior.
- **Conservative reward estimation**: Use the minimum of ensemble scores rather than the average. This penalizes outputs where any reward model is uncertain.

### Key Takeaways

- **The Bradley-Terry model** is the standard framework for reward modeling, converting pairwise preferences into scalar rewards through a logistic model with loss L = -log(sigmoid(r_chosen - r_rejected))
- **Calibration is critical** -- without magnitude regularization and margin targets, reward scores drift to arbitrary scales that destabilize downstream PPO training
- **Goodhart's law is the primary failure mode**: the policy will exploit any weakness in the reward model, so use ensembles, KL penalties, and conservative reward estimation to mitigate
- **Always hold out 10-20% of preference data** for validation, and monitor the train-val accuracy gap to detect overfitting early
- **Common pitfalls include** using the wrong token position for reward extraction, neglecting label smoothing for noisy annotations, and training too many epochs on small preference datasets
'''
    ),
    (
        "synthetic data generation alignment pipeline Evol-Instruct",
        "Explain synthetic data generation for AI alignment in depth -- covering Evol-Instruct, Self-Instruct, and WizardLM methodologies, quality filtering with LLM-as-judge, decontamination against benchmark leakage, and building a complete production-grade synthetic data pipeline. Include Python code implementations, practical advice on costs and scaling, and common pitfalls to avoid.",
        '''## Synthetic Data Generation for Alignment: Building Data Factories

### Why Synthetic Data Is the Future of Alignment

The alignment bottleneck is not algorithms -- it is data. Human-generated preference data costs $2-10 per example, takes weeks to collect, and is inconsistent across annotators. Meanwhile, models like GPT-4 and Claude can generate thousands of high-quality instruction-response pairs per hour at $0.01-0.10 each. The quality gap between synthetic and human data has narrowed dramatically, and for many domains, **synthetic data now matches or exceeds human-written data quality**.

Three methodologies dominate synthetic data generation for alignment: Self-Instruct (Wang et al., 2023), Evol-Instruct (Xu et al., 2023), and WizardLM's evolution framework. Each uses different strategies to generate diverse, high-quality instruction-following data. Understanding their trade-offs is essential for building production data pipelines.

### Self-Instruct: Bootstrap from Seed Examples

Self-Instruct starts with a small seed set of human-written (instruction, response) pairs (typically 175 examples) and uses a language model to generate new instructions, classify them, and produce responses. The pipeline has four stages:

1. **Instruction generation**: The model generates new instructions inspired by seed examples
2. **Classification**: Each instruction is tagged as classification or open-ended
3. **Instance generation**: The model produces input-output pairs for each instruction
4. **Filtering**: Rouge-L overlap removes near-duplicates

The key limitation is **diversity collapse** -- after several generations, the model produces increasingly similar instructions. Evol-Instruct addresses this directly.

### Evol-Instruct: Controlled Complexity Evolution

Evol-Instruct takes existing instructions and systematically evolves them along complexity dimensions:

- **Deepening**: Add constraints, edge cases, or requirements
- **Widening**: Broaden the scope or add related subtasks
- **Concretizing**: Make abstract instructions specific
- **Reasoning**: Add multi-step reasoning requirements
- **In-breadth**: Generate entirely new instructions at similar difficulty

Each evolution step is controlled by a prompt template that specifies the type of transformation. This produces a natural curriculum from simple to complex instructions.

### Implementation: The Core Pipeline

```python
import json
import hashlib
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum
from openai import AsyncOpenAI
import logging
import re

logger = logging.getLogger(__name__)


class EvolutionType(Enum):
    """Types of instruction evolution from Evol-Instruct."""
    DEEPEN = "deepen"
    WIDEN = "widen"
    CONCRETIZE = "concretize"
    REASONING = "reasoning"
    BREADTH = "in_breadth"


EVOLUTION_PROMPTS: dict[EvolutionType, str] = {
    EvolutionType.DEEPEN: (
        "Rewrite the following instruction to make it more complex by adding "
        "constraints, edge cases, or additional requirements. The evolved "
        "instruction should require deeper expertise to answer correctly.\\n\\n"
        "Original: {instruction}\\n\\nEvolved:"
    ),
    EvolutionType.WIDEN: (
        "Rewrite the following instruction to broaden its scope by combining "
        "it with a related subtask or asking for comparison across approaches.\\n\\n"
        "Original: {instruction}\\n\\nEvolved:"
    ),
    EvolutionType.CONCRETIZE: (
        "Rewrite the following instruction to make it more specific and "
        "concrete, with a realistic scenario, specific numbers, or named "
        "technologies.\\n\\n"
        "Original: {instruction}\\n\\nEvolved:"
    ),
    EvolutionType.REASONING: (
        "Rewrite the following instruction to require multi-step reasoning, "
        "analysis of trade-offs, or step-by-step problem solving.\\n\\n"
        "Original: {instruction}\\n\\nEvolved:"
    ),
    EvolutionType.BREADTH: (
        "Generate a completely new instruction that is at a similar difficulty "
        "level as the following but covers a different topic.\\n\\n"
        "Reference: {instruction}\\n\\nNew instruction:"
    ),
}


@dataclass
class SyntheticPair:
    """A single instruction-response pair with metadata."""
    instruction: str
    response: str
    source: str                     # Which method generated this
    evolution_depth: int = 0        # How many times the instruction was evolved
    quality_score: float = 0.0      # LLM judge score
    decontaminated: bool = False    # Whether decontamination check passed
    fingerprint: str = ""           # Hash for deduplication

    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = hashlib.md5(
                self.instruction.lower().encode()
            ).hexdigest()


@dataclass
class PipelineConfig:
    """Configuration for synthetic data generation pipeline."""
    model_name: str = "gpt-4"
    judge_model: str = "gpt-4"
    generation_temperature: float = 0.8
    judge_temperature: float = 0.1
    max_evolution_depth: int = 3
    evolutions_per_instruction: int = 2
    quality_threshold: float = 7.0     # Minimum LLM judge score (1-10)
    max_rouge_overlap: float = 0.7     # Deduplication threshold
    batch_size: int = 20
    max_concurrent: int = 10
```

Now implement the evolution engine and response generation:

```python
class EvolInstructEngine:
    """Core Evol-Instruct engine for instruction evolution."""

    def __init__(self, config: PipelineConfig, client: Optional[AsyncOpenAI] = None):
        self.config = config
        self.client = client or AsyncOpenAI()
        self.semaphore = asyncio.Semaphore(config.max_concurrent)

    async def _call_model(
        self, prompt: str, temperature: float, max_tokens: int = 2048
    ) -> str:
        """Rate-limited model call with error handling."""
        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model=self.config.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"Model call failed: {e}")
                return ""

    async def evolve_instruction(
        self, instruction: str, evolution_type: EvolutionType
    ) -> str:
        """Evolve an instruction using a specific evolution strategy."""
        prompt_template = EVOLUTION_PROMPTS[evolution_type]
        prompt = prompt_template.format(instruction=instruction)
        evolved = await self._call_model(
            prompt, self.config.generation_temperature, max_tokens=512
        )

        # Validate evolution: must be meaningfully different
        if not evolved or len(evolved) < 20:
            return ""
        if evolved.lower().strip() == instruction.lower().strip():
            return ""  # No actual evolution occurred

        return evolved

    async def generate_response(self, instruction: str) -> str:
        """Generate a high-quality response for an instruction."""
        system_prompt = (
            "You are a helpful, accurate, and thorough assistant. Provide "
            "detailed, well-structured responses with code examples where "
            "appropriate. Be honest about limitations and uncertainties."
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": instruction},
                ],
                temperature=self.config.generation_temperature,
                max_tokens=2048,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Response generation failed: {e}")
            return ""

    async def evolve_and_generate(
        self, seed_instruction: str, depth: int = 0
    ) -> list[SyntheticPair]:
        """Recursively evolve an instruction and generate responses."""
        pairs = []

        # Generate response for current instruction
        response = await self.generate_response(seed_instruction)
        if response:
            pairs.append(SyntheticPair(
                instruction=seed_instruction,
                response=response,
                source="evol_instruct",
                evolution_depth=depth,
            ))

        # Evolve if we haven't reached max depth
        if depth < self.config.max_evolution_depth:
            evolution_types = list(EvolutionType)
            selected = evolution_types[:self.config.evolutions_per_instruction]

            tasks = [
                self.evolve_instruction(seed_instruction, etype)
                for etype in selected
            ]
            evolved_instructions = await asyncio.gather(*tasks)

            for evolved in evolved_instructions:
                if evolved:
                    child_pairs = await self.evolve_and_generate(
                        evolved, depth + 1
                    )
                    pairs.extend(child_pairs)

        return pairs
```

### Quality Filtering with LLM-as-Judge

Raw synthetic data contains noise -- irrelevant responses, hallucinations, incomplete answers. **LLM-as-judge** filtering scores each pair and removes low-quality examples. This is the single most impactful step in the pipeline.

```python
class LLMJudge:
    """Quality filter using LLM-as-judge scoring."""

    JUDGE_PROMPT = """Rate the following instruction-response pair on a scale of 1-10.

Criteria:
- Helpfulness (1-3): Does the response fully address the instruction?
- Accuracy (1-3): Is the information correct and precise?
- Depth (1-2): Is the response thorough with good detail?
- Clarity (1-2): Is the response well-organized and clear?

Instruction: {instruction}

Response: {response}

Return ONLY a JSON object: {{"score": <number>, "reason": "<brief explanation>"}}"""

    def __init__(self, config: PipelineConfig, client: Optional[AsyncOpenAI] = None):
        self.config = config
        self.client = client or AsyncOpenAI()

    async def score_pair(self, pair: SyntheticPair) -> float:
        """Score a single instruction-response pair."""
        prompt = self.JUDGE_PROMPT.format(
            instruction=pair.instruction, response=pair.response
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.config.judge_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.judge_temperature,
                max_tokens=200,
            )
            result = json.loads(response.choices[0].message.content)
            return float(result.get("score", 0))
        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.warning(f"Judge scoring failed: {e}")
            return 0.0

    async def filter_dataset(
        self, pairs: list[SyntheticPair]
    ) -> list[SyntheticPair]:
        """Score and filter all pairs, keeping only high-quality ones."""
        tasks = [self.score_pair(pair) for pair in pairs]
        scores = await asyncio.gather(*tasks)

        filtered = []
        for pair, score in zip(pairs, scores):
            pair.quality_score = score
            if score >= self.config.quality_threshold:
                filtered.append(pair)

        logger.info(
            f"Quality filter: {len(filtered)}/{len(pairs)} pairs passed "
            f"(threshold={self.config.quality_threshold})"
        )
        return filtered
```

### Decontamination: Preventing Benchmark Leakage

A critical but often neglected step is **decontamination** -- ensuring your synthetic data does not contain examples from evaluation benchmarks. If training data overlaps with test sets (MMLU, HumanEval, GSM8K, etc.), your eval numbers are inflated and meaningless.

```python
class Decontaminator:
    """Remove synthetic examples that overlap with evaluation benchmarks."""

    def __init__(self, benchmark_texts: list[str], ngram_size: int = 10):
        self.ngram_size = ngram_size
        self.benchmark_ngrams: set[str] = set()

        for text in benchmark_texts:
            tokens = text.lower().split()
            for i in range(len(tokens) - ngram_size + 1):
                ngram = " ".join(tokens[i:i + ngram_size])
                self.benchmark_ngrams.add(ngram)

        logger.info(
            f"Decontaminator initialized with {len(self.benchmark_ngrams)} "
            f"{ngram_size}-grams from {len(benchmark_texts)} benchmark examples"
        )

    def is_contaminated(self, text: str, max_overlap: int = 3) -> bool:
        """
        Check if text contains too many benchmark n-gram matches.

        Common pitfall: using exact string matching instead of n-gram
        overlap. Exact matching misses paraphrased benchmark questions,
        which are the most dangerous form of contamination because they
        inflate scores without being detectable by naive checks.
        """
        tokens = text.lower().split()
        matches = 0
        for i in range(len(tokens) - self.ngram_size + 1):
            ngram = " ".join(tokens[i:i + self.ngram_size])
            if ngram in self.benchmark_ngrams:
                matches += 1
                if matches >= max_overlap:
                    return True
        return False

    def decontaminate(self, pairs: list[SyntheticPair]) -> list[SyntheticPair]:
        """Remove contaminated pairs from the dataset."""
        clean = []
        contaminated_count = 0
        for pair in pairs:
            combined = f"{pair.instruction} {pair.response}"
            if self.is_contaminated(combined):
                contaminated_count += 1
            else:
                pair.decontaminated = True
                clean.append(pair)

        logger.info(
            f"Decontamination: removed {contaminated_count}/{len(pairs)} pairs"
        )
        return clean
```

### The Complete Production Pipeline

```python
class SyntheticDataPipeline:
    """End-to-end synthetic data generation pipeline."""

    def __init__(
        self,
        config: PipelineConfig,
        benchmark_texts: Optional[list[str]] = None,
    ):
        self.config = config
        self.engine = EvolInstructEngine(config)
        self.judge = LLMJudge(config)
        self.decontaminator = (
            Decontaminator(benchmark_texts) if benchmark_texts else None
        )

    async def run(
        self, seed_instructions: list[str]
    ) -> list[SyntheticPair]:
        """
        Run the full pipeline: evolve -> generate -> judge -> decontaminate.

        Best practice: start with 500-1000 diverse seed instructions.
        The evolution process will expand this 5-10x, and after filtering,
        you typically retain 40-60% of generated pairs.
        """
        logger.info(f"Starting pipeline with {len(seed_instructions)} seeds")

        # Step 1: Evolve instructions and generate responses
        all_pairs: list[SyntheticPair] = []
        for batch_start in range(0, len(seed_instructions), self.config.batch_size):
            batch = seed_instructions[batch_start:batch_start + self.config.batch_size]
            tasks = [self.engine.evolve_and_generate(inst) for inst in batch]
            results = await asyncio.gather(*tasks)
            for pairs in results:
                all_pairs.extend(pairs)

        logger.info(f"Generated {len(all_pairs)} raw pairs")

        # Step 2: Deduplicate by fingerprint
        seen: set[str] = set()
        deduped = []
        for pair in all_pairs:
            if pair.fingerprint not in seen:
                seen.add(pair.fingerprint)
                deduped.append(pair)
        logger.info(f"After dedup: {len(deduped)} pairs")

        # Step 3: Quality filtering with LLM judge
        high_quality = await self.judge.filter_dataset(deduped)

        # Step 4: Decontamination
        if self.decontaminator:
            clean = self.decontaminator.decontaminate(high_quality)
        else:
            clean = high_quality

        logger.info(
            f"Pipeline complete: {len(seed_instructions)} seeds -> "
            f"{len(all_pairs)} raw -> {len(clean)} final pairs"
        )
        return clean

    def export_dataset(
        self, pairs: list[SyntheticPair], output_path: str
    ) -> None:
        """Export the dataset in standard format."""
        records = [
            {
                "instruction": p.instruction,
                "response": p.response,
                "source": p.source,
                "quality_score": p.quality_score,
                "evolution_depth": p.evolution_depth,
            }
            for p in pairs
        ]
        with open(output_path, "w") as f:
            json.dump(records, f, indent=2)
        logger.info(f"Exported {len(records)} pairs to {output_path}")
```

### Cost Analysis and Scaling Considerations

For production synthetic data generation, the cost breakdown per 10K final pairs is approximately:

- **Evolution**: ~30K API calls at $0.02 each = $600
- **Response generation**: ~20K API calls at $0.05 each = $1,000
- **Judge scoring**: ~20K API calls at $0.03 each = $600
- **Total**: ~$2,200 for 10K high-quality pairs

Compare this to human annotation at $5 per pair: $50,000 for the same volume. Synthetic data is **20x cheaper** even when accounting for the quality filtering loss. However, the trade-off is ceiling quality -- for safety-critical domains, human review of the filtered synthetic data is still a best practice.

For throughput, the bottleneck is API rate limits. With async concurrency of 10-20 requests and a rate limit of 500 RPM, you can generate approximately 1,000 final pairs per hour. Scaling beyond this requires multiple API keys or self-hosted models.

### Key Takeaways

- **Evol-Instruct systematically evolves** seed instructions along complexity dimensions (deepening, widening, concretizing, reasoning), producing a natural difficulty curriculum that Self-Instruct alone cannot achieve
- **LLM-as-judge filtering** is the single highest-impact step -- it typically removes 40-60% of generated pairs, and the quality threshold should be calibrated on a held-out human-evaluated set
- **Decontamination is non-negotiable** for any dataset used in evaluation-facing models; use n-gram overlap checking against all benchmarks you plan to evaluate on
- **Cost is approximately $0.20-0.25 per final high-quality pair** using GPT-4 class models, which is 20x cheaper than human annotation at comparable quality
- **Common pitfalls include** diversity collapse (mitigated by in-breadth evolution), benchmark contamination (mitigated by n-gram decontamination), and insufficient quality filtering (mitigated by setting the judge threshold above 7.0)
'''
    ),
]
