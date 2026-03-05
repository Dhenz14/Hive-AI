"""P2 Batch: AI training techniques — curriculum learning, synthetic data, model merging, quantization."""

PAIRS = [
    (
        "curriculum learning for language model training",
        "Explain curriculum learning for LLM fine-tuning — how ordering training data by difficulty improves convergence and final quality. Show practical implementations with difficulty scoring and scheduling strategies.",
        """## Curriculum Learning: Teaching Models Easy Things First

### Why Data Order Matters

Random shuffling is the default for training data. But humans don't learn by random exposure — we learn basics before advanced topics, simple examples before complex ones. Curriculum learning applies this insight to model training: **present easy examples first, then gradually increase difficulty**.

The evidence is strong: Bengio et al. (2009) showed curriculum learning improves convergence speed and generalization. For code models specifically, training on simple functions before complex systems produces 5-15% better eval scores than random ordering.

### Difficulty Scoring for Code Training Pairs

```python
import re
import ast
import math
from dataclasses import dataclass


@dataclass
class DifficultyScore:
    overall: float          # 0.0 (easiest) to 1.0 (hardest)
    code_complexity: float  # Cyclomatic complexity of code blocks
    concept_depth: float    # Number of advanced concepts referenced
    response_length: float  # Normalized length (longer = harder topic)
    reasoning_density: float # Ratio of reasoning markers to total words


def score_difficulty(instruction: str, response: str) -> DifficultyScore:
    \"\"\"
    Score the difficulty of a training pair for curriculum ordering.

    Why not just use response length? Because a long explanation of
    a simple concept (like 'what is a variable') is easy, while a
    short explanation of a hard concept (like 'explain the GIL') is
    hard. We need multiple signals.
    \"\"\"
    # 1. Code complexity: parse Python blocks and measure cyclomatic complexity
    code_blocks = re.findall(r'```python\\n(.*?)```', response, re.DOTALL)
    complexities = []
    for block in code_blocks:
        try:
            tree = ast.parse(block)
            complexity = 1
            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                     ast.With, ast.Assert, ast.BoolOp)):
                    complexity += 1
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    complexity += 2  # New scope = complexity jump
                if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                    complexity += 1
            complexities.append(complexity)
        except SyntaxError:
            complexities.append(5)  # Unparseable = probably complex

    avg_complexity = sum(complexities) / max(len(complexities), 1)
    code_complexity = min(avg_complexity / 20.0, 1.0)  # Normalize to 0-1

    # 2. Concept depth: count advanced programming concepts
    advanced_concepts = [
        r'\\bmetaclass\\b', r'\\bdescriptor\\b', r'\\bcoroutine\\b',
        r'\\bgenerator\\b', r'\\bdecorator\\b', r'\\bclosure\\b',
        r'\\bmonkey.?patch\\b', r'\\bGIL\\b', r'\\breference.?count\\b',
        r'\\bgarbage.?collect\\b', r'\\bweak.?ref\\b', r'\\b__dunder__\\b',
        r'\\basync\\b', r'\\bawait\\b', r'\\bthread.?safe\\b',
        r'\\block.?free\\b', r'\\batomic\\b', r'\\bmemory.?model\\b',
        r'\\bvirtual.?table\\b', r'\\bvtable\\b', r'\\bRTTI\\b',
        r'\\bSFINAE\\b', r'\\bconcept\\b', r'\\btemplate\\b',
        r'\\bownership\\b', r'\\bborrow\\b', r'\\blifetime\\b',
    ]
    combined = (instruction + " " + response).lower()
    concept_count = sum(1 for p in advanced_concepts if re.search(p, combined))
    concept_depth = min(concept_count / 10.0, 1.0)

    # 3. Response length (normalized)
    word_count = len(response.split())
    response_length = min(word_count / 2000.0, 1.0)

    # 4. Reasoning density: ratio of reasoning markers
    reasoning_markers = len(re.findall(
        r'\\b(because|therefore|however|trade-?off|the reason|this means|'
        r'the key insight|the problem is|notice that|importantly|'
        r'the difference|compared to|alternatively|in contrast)\\b',
        response, re.IGNORECASE
    ))
    total_words = max(word_count, 1)
    reasoning_density = min(reasoning_markers / (total_words / 100), 1.0)

    # Weighted combination
    overall = (
        0.35 * code_complexity +
        0.30 * concept_depth +
        0.20 * response_length +
        0.15 * reasoning_density
    )

    return DifficultyScore(
        overall=round(overall, 4),
        code_complexity=round(code_complexity, 4),
        concept_depth=round(concept_depth, 4),
        response_length=round(response_length, 4),
        reasoning_density=round(reasoning_density, 4),
    )
```

### Curriculum Scheduling Strategies

```python
import random
from typing import List, Tuple


def linear_curriculum(
    pairs: list[dict],
    num_epochs: int = 3,
) -> list[list[dict]]:
    \"\"\"
    Linear curriculum: easy → hard over the first epoch,
    then random for subsequent epochs.

    Why random after epoch 1? The curriculum helps the model
    build foundational representations. After that, random
    exposure helps generalization (prevents overfitting to
    the difficulty ordering).
    \"\"\"
    # Score all pairs
    scored = []
    for pair in pairs:
        diff = score_difficulty(pair["instruction"], pair.get("output", pair.get("response", "")))
        scored.append((diff.overall, pair))

    # Sort by difficulty for epoch 1
    scored.sort(key=lambda x: x[0])
    epoch_1 = [pair for _, pair in scored]

    # Random shuffle for remaining epochs
    epochs = [epoch_1]
    for _ in range(num_epochs - 1):
        shuffled = list(pairs)
        random.shuffle(shuffled)
        epochs.append(shuffled)

    return epochs


def competence_curriculum(
    pairs: list[dict],
    initial_competence: float = 0.2,
    growth_rate: float = 0.1,
) -> list[dict]:
    \"\"\"
    Competence-based curriculum (Platanios et al., 2019):
    the model's 'competence' grows over training steps,
    and only pairs below the competence threshold are eligible.

    This is more adaptive than linear curriculum because it
    naturally spends more time on easy examples early on.

    initial_competence: fraction of difficulty range available at start
    growth_rate: how fast competence grows (per 1000 steps)
    \"\"\"
    scored = []
    for pair in pairs:
        diff = score_difficulty(pair["instruction"], pair.get("output", pair.get("response", "")))
        scored.append((diff.overall, pair))

    scored.sort(key=lambda x: x[0])
    difficulties = [d for d, _ in scored]
    max_diff = max(difficulties) if difficulties else 1.0

    ordered = []
    competence = initial_competence
    step = 0

    while len(ordered) < len(pairs):
        # Find eligible pairs (difficulty < competence * max_difficulty)
        threshold = competence * max_diff
        eligible = [(d, p) for d, p in scored if d <= threshold and p not in ordered]

        if eligible:
            # Sample from eligible pairs (with replacement prevention)
            _, selected = random.choice(eligible)
            ordered.append(selected)
            scored = [(d, p) for d, p in scored if p != selected]
        else:
            # All remaining pairs are too hard — increase competence
            competence = min(competence + growth_rate, 1.0)
            continue

        step += 1
        if step % 1000 == 0:
            competence = min(competence + growth_rate, 1.0)

    return ordered


def anti_curriculum(pairs: list[dict]) -> list[dict]:
    \"\"\"
    Anti-curriculum: hard examples first, then easy.

    Surprisingly, this sometimes works better for fine-tuning
    (not pre-training). The theory: hard examples force the
    model to form robust representations early, and easy
    examples then 'polish' these representations.

    Use this when: fine-tuning a strong base model on a small
    dataset. The model already has basic capabilities — showing
    it hard examples first leverages its existing knowledge.
    \"\"\"
    scored = []
    for pair in pairs:
        diff = score_difficulty(pair["instruction"], pair.get("output", pair.get("response", "")))
        scored.append((diff.overall, pair))

    scored.sort(key=lambda x: -x[0])  # Descending: hard first
    return [pair for _, pair in scored]
```

### Practical Integration with HiveAI Training Pipeline

```python
def prepare_curriculum_dataset(
    jsonl_path: str,
    strategy: str = "competence",
    output_path: str = None,
) -> str:
    \"\"\"
    Reorder a training JSONL file using curriculum learning.

    Usage:
        python -c "from curriculum import prepare_curriculum_dataset; \\
                    prepare_curriculum_dataset('loras/training_data/v5.jsonl')"
    \"\"\"
    import json

    pairs = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            pairs.append(json.loads(line))

    print(f"Loaded {len(pairs)} pairs from {jsonl_path}")

    if strategy == "linear":
        epochs = linear_curriculum(pairs, num_epochs=3)
        ordered = []
        for epoch in epochs:
            ordered.extend(epoch)
    elif strategy == "competence":
        ordered = competence_curriculum(pairs)
    elif strategy == "anti":
        ordered = anti_curriculum(pairs)
    else:
        ordered = pairs

    # Score distribution report
    difficulties = [score_difficulty(p["instruction"], p.get("output", "")).overall for p in ordered[:100]]
    print(f"First 100 pairs avg difficulty: {sum(difficulties)/len(difficulties):.3f}")
    difficulties = [score_difficulty(p["instruction"], p.get("output", "")).overall for p in ordered[-100:]]
    print(f"Last 100 pairs avg difficulty: {sum(difficulties)/len(difficulties):.3f}")

    if output_path is None:
        output_path = jsonl_path.replace(".jsonl", f"_curriculum_{strategy}.jsonl")

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in ordered:
            f.write(json.dumps(pair, ensure_ascii=False) + "\\n")

    print(f"Wrote {len(ordered)} pairs to {output_path}")
    return output_path
```

The key takeaway: data ordering is a free lunch. It costs nothing extra to sort your training data by difficulty, and it consistently improves both convergence speed (10-20% fewer steps) and final quality (2-5% better eval scores). For the HiveAI pipeline, adding curriculum ordering to `prepare_v5_data.py` before training would be the simplest high-impact improvement.""",
    ),

    (
        "synthetic data generation for code models",
        "How do you generate high-quality synthetic training data for code models? Explain Evol-Instruct, self-instruct, persona-driven generation, and quality filtering. Show practical implementations.",
        """## Synthetic Data: Manufacturing Training Pairs at Scale

### Why Synthetic Data Works

Real-world coding data (Stack Overflow, GitHub) has problems: it's noisy (many answers are wrong), biased (overrepresents popular languages), and limited (niche topics have few examples). Synthetic data generation uses a strong model to create training data for a weaker model, with the advantage of controlling quality, diversity, and topic coverage.

The key finding (Alpaca, WizardCoder, Code Evol-Instruct): models trained on high-quality synthetic data consistently outperform models trained on larger amounts of noisy real data.

### Technique 1: Evol-Instruct (WizardLM)

```python
import random


def evol_instruct(llm_fn, seed_instruction: str, depth: int = 3) -> list[str]:
    \"\"\"
    Evol-Instruct: evolve a simple instruction into increasingly complex ones.

    The algorithm applies random mutations to instructions, creating
    a tree of progressively harder variants. Each mutation adds ONE
    new requirement or constraint.

    Why this works: it generates a natural difficulty curve AND creates
    diverse instructions from a single seed. One seed like 'sort a list'
    can evolve into 'sort a list of dicts by multiple keys with custom
    comparators, handling None values and maintaining stability'.
    \"\"\"
    evolution_prompts = {
        "add_constraint": (
            "Add a constraint or requirement to make this programming task harder. "
            "The constraint should be realistic (something a real project would need). "
            "Keep the original task but make it more challenging.\\n\\n"
            "Original: {instruction}\\n\\nEvolved:"
        ),
        "deepen": (
            "Make this programming task require deeper understanding. "
            "Add requirements for error handling, edge cases, or performance optimization.\\n\\n"
            "Original: {instruction}\\n\\nEvolved:"
        ),
        "concretize": (
            "Make this programming task more specific and concrete. "
            "Replace generic descriptions with specific data types, sizes, or scenarios.\\n\\n"
            "Original: {instruction}\\n\\nEvolved:"
        ),
        "compose": (
            "Combine this programming task with a related but different concept. "
            "The result should require understanding both topics.\\n\\n"
            "Original: {instruction}\\n\\nEvolved:"
        ),
        "widen": (
            "Broaden this task to cover more scenarios or use cases. "
            "Add requirements for multiple input types, formats, or platforms.\\n\\n"
            "Original: {instruction}\\n\\nEvolved:"
        ),
    }

    results = [seed_instruction]
    current = seed_instruction

    for d in range(depth):
        mutation = random.choice(list(evolution_prompts.keys()))
        prompt = evolution_prompts[mutation].format(instruction=current)
        evolved = llm_fn(prompt)

        if evolved and len(evolved) > len(current) * 0.5:
            results.append(evolved.strip())
            current = evolved.strip()

    return results


def batch_evol_instruct(llm_fn, seeds: list[str], depth: int = 3, width: int = 2) -> list[str]:
    \"\"\"
    Generate multiple evolution branches per seed for maximum diversity.

    width=2 means each seed produces 2 independent evolution chains.
    With 100 seeds, depth=3, width=2: 100 * 2 * 3 = 600 evolved instructions.
    \"\"\"
    all_evolved = []
    for seed in seeds:
        for _ in range(width):
            chain = evol_instruct(llm_fn, seed, depth=depth)
            all_evolved.extend(chain)
    return all_evolved
```

### Technique 2: Self-Instruct with Quality Filtering

```python
import json
import hashlib
from collections import defaultdict


class SelfInstructPipeline:
    \"\"\"
    Self-Instruct (Wang et al., 2023): the model generates its own
    instruction-response pairs from a small set of seed examples.

    The pipeline:
    1. Start with 10-20 seed pairs (human-written, high quality)
    2. Model generates new instructions inspired by seeds
    3. Model generates responses to new instructions
    4. Quality filter removes bad pairs
    5. Good pairs become new seeds for the next round
    \"\"\"

    def __init__(self, llm_fn, seed_pairs: list[dict]):
        self.llm = llm_fn
        self.seed_pairs = seed_pairs
        self.generated = []
        self.seen_instructions = set()
        # Dedup by instruction prefix
        for p in seed_pairs:
            self.seen_instructions.add(self._hash(p["instruction"]))

    def _hash(self, text: str) -> str:
        normalized = text.lower().strip()[:200]
        return hashlib.md5(normalized.encode()).hexdigest()

    def generate_round(self, n_pairs: int = 20) -> list[dict]:
        \"\"\"Generate n new instruction-response pairs.\"\"\"
        new_pairs = []

        # Sample 3 seed pairs as few-shot examples
        examples = random.sample(
            self.seed_pairs + self.generated[-50:],  # Recent good pairs too
            min(3, len(self.seed_pairs))
        )

        example_text = "\\n\\n".join(
            f"Instruction: {p['instruction']}\\nResponse: {p['response'][:200]}..."
            for p in examples
        )

        for _ in range(n_pairs * 2):  # Generate 2x, filter to n
            # Step 1: Generate instruction
            gen_prompt = (
                f"Here are some example coding instruction-response pairs:\\n\\n"
                f"{example_text}\\n\\n"
                f"Generate a NEW, different coding instruction. "
                f"It should test a different concept or skill. "
                f"Be specific and require code in the response.\\n\\n"
                f"New Instruction:"
            )
            instruction = self.llm(gen_prompt).strip()

            # Dedup check
            inst_hash = self._hash(instruction)
            if inst_hash in self.seen_instructions:
                continue
            if len(instruction) < 20 or len(instruction) > 500:
                continue

            # Step 2: Generate response
            response = self.llm(instruction)
            if not response or len(response) < 100:
                continue

            # Step 3: Quality filter
            quality = self._score_quality(instruction, response)
            if quality < 0.7:
                continue

            pair = {
                "instruction": instruction,
                "response": response,
                "quality": quality,
                "source": "self_instruct",
            }
            new_pairs.append(pair)
            self.seen_instructions.add(inst_hash)

            if len(new_pairs) >= n_pairs:
                break

        self.generated.extend(new_pairs)
        return new_pairs

    def _score_quality(self, instruction: str, response: str) -> float:
        \"\"\"Quick quality check without full scoring pipeline.\"\"\"
        score = 0.5  # Base

        # Has code blocks
        code_blocks = len(re.findall(r'```', response)) // 2
        if code_blocks >= 3:
            score += 0.2
        elif code_blocks >= 1:
            score += 0.1

        # Sufficient length
        words = len(response.split())
        if words >= 400:
            score += 0.15
        elif words >= 200:
            score += 0.1

        # Has explanation (not just code)
        non_code = re.sub(r'```.*?```', '', response, flags=re.DOTALL)
        explanation_words = len(non_code.split())
        if explanation_words >= 100:
            score += 0.1

        # Instruction-response relevance (basic keyword overlap)
        inst_words = set(instruction.lower().split())
        resp_words = set(response.lower().split())
        overlap = len(inst_words & resp_words) / max(len(inst_words), 1)
        score += min(overlap * 0.2, 0.1)

        return min(score, 1.0)
```

### Technique 3: Persona-Driven Generation

```python
PERSONAS = [
    {
        "name": "Senior Backend Engineer",
        "style": "Production-focused. Always considers error handling, "
                 "logging, monitoring, and deployment. Uses type hints and "
                 "writes comprehensive tests. Prefers boring technology.",
        "topics": ["API design", "database optimization", "microservices",
                   "caching strategies", "message queues"],
    },
    {
        "name": "Systems Programmer",
        "style": "Performance-obsessed. Thinks in terms of cache lines, "
                 "memory layout, and zero-copy. Uses profiling data to "
                 "justify every design decision. Writes C++ and Rust.",
        "topics": ["memory management", "concurrency", "SIMD",
                   "lock-free data structures", "kernel bypass"],
    },
    {
        "name": "ML Engineer",
        "style": "Research-oriented but practical. Implements papers, "
                 "understands training dynamics, and optimizes inference. "
                 "Uses PyTorch, thinks about GPU utilization.",
        "topics": ["model training", "inference optimization", "data pipelines",
                   "distributed training", "model evaluation"],
    },
    {
        "name": "Security Engineer",
        "style": "Adversarial mindset. Thinks about how every feature can "
                 "be exploited. Reviews code for OWASP top 10, supply chain "
                 "attacks, and privilege escalation. Writes exploit PoCs.",
        "topics": ["input validation", "authentication", "cryptography",
                   "supply chain security", "penetration testing"],
    },
    {
        "name": "Junior Developer Learning Fast",
        "style": "Asks 'why' for everything. Needs step-by-step explanations "
                 "with analogies. Appreciates when complex concepts are broken "
                 "down into simple building blocks.",
        "topics": ["fundamentals", "debugging", "git workflow",
                   "reading documentation", "code review"],
    },
]


def persona_generate(llm_fn, persona: dict, topic: str) -> dict:
    \"\"\"
    Generate a training pair from a specific persona's perspective.

    Why personas? They create DIVERSE responses to similar topics.
    A Senior Backend Engineer and a Systems Programmer will give
    very different answers to 'how to implement a cache' — and
    the model benefits from seeing both perspectives.
    \"\"\"
    instruction_prompt = (
        f"You are a {persona['name']}. Your style: {persona['style']}\\n\\n"
        f"Write a coding question about {topic} that someone with your "
        f"background and expertise level would ask. Be specific."
    )
    instruction = llm_fn(instruction_prompt)

    response_prompt = (
        f"You are a {persona['name']}. Your style: {persona['style']}\\n\\n"
        f"Answer this question with your characteristic approach:\\n{instruction}\\n\\n"
        f"Include working code examples, explain your reasoning, "
        f"and discuss tradeoffs from your perspective."
    )
    response = llm_fn(response_prompt)

    return {
        "instruction": instruction,
        "response": response,
        "source": f"persona_{persona['name'].lower().replace(' ', '_')}",
        "topic": topic,
    }
```

### Quality Filtering: The Most Important Step

The single most impactful technique in synthetic data is **aggressive filtering**. Generating 10,000 pairs and keeping the best 2,000 produces better models than training on all 10,000. This is because low-quality pairs actively harm training — they teach the model to produce bad output.

```python
def multi_stage_filter(pairs: list[dict], target_count: int) -> list[dict]:
    \"\"\"
    Three-stage filtering pipeline:
    1. Hard filters (remove obviously bad pairs)
    2. Quality scoring (rank by multi-dimensional quality)
    3. Diversity selection (maximize topic coverage in final set)
    \"\"\"
    # Stage 1: Hard filters
    filtered = []
    for p in pairs:
        response = p.get("response", p.get("output", ""))
        instruction = p.get("instruction", "")

        # Must have code
        if '```' not in response:
            continue
        # Must have substance
        if len(response.split()) < 150:
            continue
        # Must not be meta-commentary
        if response.lower().startswith(("sure", "certainly", "of course")):
            response = response.split("\\n", 1)[-1]  # Strip first line
            p["response"] = response
        # Must have explanation (not just code dump)
        non_code = re.sub(r'```.*?```', '', response, flags=re.DOTALL)
        if len(non_code.split()) < 50:
            continue

        filtered.append(p)

    # Stage 2: Quality scoring
    scored = [(score_difficulty(p["instruction"], p.get("response", p.get("output", ""))).overall, p)
              for p in filtered]

    # Stage 3: Diversity-aware selection
    # Greedy selection: pick highest quality, but penalize topics already covered
    topic_counts = defaultdict(int)
    selected = []

    scored.sort(key=lambda x: -x[0])  # Highest quality first
    for quality, pair in scored:
        topic = pair.get("topic", pair.get("input", "unknown"))
        # Penalize over-represented topics
        penalty = 0.1 * topic_counts.get(topic, 0)
        adjusted_quality = quality - penalty

        if adjusted_quality > 0.3:  # Minimum threshold
            selected.append(pair)
            topic_counts[topic] += 1

        if len(selected) >= target_count:
            break

    return selected
```

The practical recipe for HiveAI: generate 5x your target dataset size using a mix of Evol-Instruct (for difficulty diversity), Self-Instruct (for topic diversity), and persona-driven generation (for style diversity). Then filter down to the target size using quality scoring + diversity selection. This consistently outperforms generating exactly the right number of pairs.""",
    ),

    (
        "model merging techniques for combining LoRA adapters",
        "Explain model merging techniques — TIES, DARE, SLERP, and task arithmetic. How do you combine multiple LoRA adapters or fine-tuned models into a single better model? Show implementations and when to use each.",
        """## Model Merging: Combining Models Without Training

### Why Merging Works

Training is expensive. If you have a Python specialist model and a Rust specialist model, training a new model that's good at both requires all the training data and compute again. Model merging combines the weights of multiple models directly — no training needed. It works because fine-tuned models share a common base, and the differences (deltas) from the base model encode task-specific knowledge that can be composed.

### Technique 1: Task Arithmetic (Ilharco et al., 2023)

```python
import torch
import numpy as np
from pathlib import Path


def load_state_dict(path: str) -> dict[str, torch.Tensor]:
    return torch.load(path, map_location="cpu")


def task_arithmetic_merge(
    base_weights: dict[str, torch.Tensor],
    expert_weights: list[dict[str, torch.Tensor]],
    scaling_coefficients: list[float],
) -> dict[str, torch.Tensor]:
    \"\"\"
    Task arithmetic: merged = base + sum(λ_i * (expert_i - base))

    The insight: the difference (expert - base) is a 'task vector'
    that encodes what the model learned during fine-tuning. You can
    ADD task vectors to give a model new capabilities, or SUBTRACT
    them to remove capabilities (like removing toxic behavior).

    scaling_coefficients control how much of each expert to include.
    Typical range: 0.3-1.0. Higher = more of that expert, but
    risk of interference with other experts.
    \"\"\"
    merged = {}

    for key in base_weights:
        merged_tensor = base_weights[key].clone().float()

        for expert, coeff in zip(expert_weights, scaling_coefficients):
            if key in expert:
                task_vector = expert[key].float() - base_weights[key].float()
                merged_tensor += coeff * task_vector

        merged[key] = merged_tensor

    return merged


# Example: merge Python expert + Rust expert + Hive expert
# base = load_state_dict("models/qwen3-14b/base.pt")
# python_expert = load_state_dict("loras/python/merged.pt")
# rust_expert = load_state_dict("loras/rust/merged.pt")
# hive_expert = load_state_dict("loras/hive/merged.pt")
#
# merged = task_arithmetic_merge(
#     base, [python_expert, rust_expert, hive_expert],
#     scaling_coefficients=[0.7, 0.5, 0.8]  # Hive gets highest weight
# )
```

### Technique 2: TIES-Merging (Yadav et al., 2023)

```python
def ties_merge(
    base_weights: dict[str, torch.Tensor],
    expert_weights: list[dict[str, torch.Tensor]],
    density: float = 0.5,
    scaling: float = 1.0,
) -> dict[str, torch.Tensor]:
    \"\"\"
    TIES: Trim, Elect Sign, and Merge.

    The problem with simple task arithmetic: many parameter changes
    from fine-tuning are NOISE, not signal. Small changes and sign
    conflicts between experts cancel out useful information.

    TIES fixes this in three steps:
    1. TRIM: zero out small-magnitude changes (keep only top-k%)
    2. ELECT SIGN: for each parameter, take the majority sign
       across experts (resolves conflicts)
    3. MERGE: average the trimmed, sign-aligned deltas

    density=0.5 means keep only the top 50% of changes by magnitude.
    This dramatically improves merge quality.
    \"\"\"
    merged = {}

    for key in base_weights:
        base_param = base_weights[key].float()

        # Compute task vectors
        deltas = []
        for expert in expert_weights:
            if key in expert:
                delta = expert[key].float() - base_param
                deltas.append(delta)

        if not deltas:
            merged[key] = base_param
            continue

        stacked = torch.stack(deltas)  # [num_experts, *param_shape]

        # Step 1: TRIM — zero out small-magnitude changes
        for i in range(len(deltas)):
            flat = stacked[i].abs().flatten()
            threshold = torch.quantile(flat, 1.0 - density)
            mask = stacked[i].abs() >= threshold
            stacked[i] = stacked[i] * mask.float()

        # Step 2: ELECT SIGN — majority vote on sign
        sign_sum = torch.sign(stacked).sum(dim=0)
        elected_sign = torch.sign(sign_sum)
        # Zero out parameters where experts disagree on sign
        for i in range(len(deltas)):
            agreement = torch.sign(stacked[i]) == elected_sign
            stacked[i] = stacked[i] * agreement.float()

        # Step 3: MERGE — average surviving deltas
        # Only count non-zero contributions in the average
        non_zero_count = (stacked != 0).float().sum(dim=0).clamp(min=1)
        merged_delta = stacked.sum(dim=0) / non_zero_count

        merged[key] = base_param + scaling * merged_delta

    return merged
```

### Technique 3: SLERP (Spherical Linear Interpolation)

```python
def slerp_merge(
    weights_a: dict[str, torch.Tensor],
    weights_b: dict[str, torch.Tensor],
    t: float = 0.5,
) -> dict[str, torch.Tensor]:
    \"\"\"
    SLERP: interpolate between two models on the weight hypersphere.

    Why not linear interpolation? Linear interpolation (lerp) moves
    through the interior of the weight space, which can pass through
    low-quality regions. SLERP moves along the surface of the
    hypersphere, staying in the high-quality manifold.

    In practice: SLERP produces smoother merges with fewer quality
    drops, especially when t is far from 0 or 1.

    t=0.0: pure model A
    t=0.5: equal blend
    t=1.0: pure model B
    \"\"\"
    merged = {}

    for key in weights_a:
        if key not in weights_b:
            merged[key] = weights_a[key]
            continue

        a = weights_a[key].float().flatten()
        b = weights_b[key].float().flatten()

        # Normalize to unit vectors
        a_norm = torch.nn.functional.normalize(a, dim=0)
        b_norm = torch.nn.functional.normalize(b, dim=0)

        # Compute angle between vectors
        dot = torch.clamp(torch.dot(a_norm, b_norm), -1.0, 1.0)
        omega = torch.acos(dot)

        if omega.abs() < 1e-6:
            # Vectors are parallel — just lerp
            result = (1 - t) * a + t * b
        else:
            sin_omega = torch.sin(omega)
            result = (
                torch.sin((1 - t) * omega) / sin_omega * a +
                torch.sin(t * omega) / sin_omega * b
            )

        merged[key] = result.reshape(weights_a[key].shape)

    return merged
```

### Technique 4: DARE (Delta Are Randomly Eliminated)

```python
def dare_merge(
    base_weights: dict[str, torch.Tensor],
    expert_weights: list[dict[str, torch.Tensor]],
    drop_rate: float = 0.9,
    scaling: float = 1.0,
) -> dict[str, torch.Tensor]:
    \"\"\"
    DARE: randomly drop 90% of delta parameters, then rescale.

    The surprising finding: you can drop 90% of fine-tuning changes
    randomly and the model still works almost as well. This means
    fine-tuning is incredibly redundant — only ~10% of parameter
    changes actually matter.

    For merging: dropping random deltas from each expert BEFORE
    merging reduces interference between experts. Each expert
    contributes in different (random) parameter subsets.

    drop_rate=0.9 means keep only 10% of each expert's changes.
    \"\"\"
    merged = {}

    for key in base_weights:
        base_param = base_weights[key].float()

        total_delta = torch.zeros_like(base_param)

        for expert in expert_weights:
            if key not in expert:
                continue

            delta = expert[key].float() - base_param

            # Random binary mask: keep (1-drop_rate) fraction
            mask = torch.bernoulli(torch.full_like(delta, 1.0 - drop_rate))

            # Rescale surviving deltas to compensate for dropped ones
            # Without rescaling, the merged model would be weaker
            rescaled_delta = delta * mask / (1.0 - drop_rate)

            total_delta += rescaled_delta

        # Average across experts
        total_delta /= max(len(expert_weights), 1)
        merged[key] = base_param + scaling * total_delta

    return merged
```

### Decision Matrix

| Method | Best For | Pros | Cons |
|--------|----------|------|------|
| **Task Arithmetic** | Simple 2-3 model merges | Easy to implement, tunable coefficients | Sign conflicts reduce quality |
| **TIES** | Many experts (5+) | Handles conflicts well, robust | Slower (trim + sign election) |
| **SLERP** | Two models, smooth blend | Best quality for 2-model merges | Only works with 2 models |
| **DARE** | Many overlapping experts | Reduces interference, works with many models | Stochastic (results vary per run) |

For HiveAI's merge cycling pipeline: use **TIES** when merging domain-specialized LoRAs (Python + Rust + Hive) because it handles sign conflicts between many experts. Use **SLERP** when merging two cycle iterations (cycle N into cycle N+1) because it produces smoother progressive improvement.""",
    ),

    (
        "quantization techniques for LLM deployment",
        "Explain LLM quantization — GPTQ, AWQ, GGUF/llama.cpp quantization, and when to use each. Show how quantization reduces model size with minimal quality loss, and the practical tradeoffs.",
        """## LLM Quantization: 4× Smaller, Nearly Same Quality

### What Quantization Does

Neural network weights are stored as 16-bit floats (FP16/BF16) by default. Quantization converts them to lower precision: 8-bit (INT8), 4-bit (INT4), or even 2-bit. A 14B parameter model at FP16 is ~28GB; at 4-bit, it's ~7GB. This means models that require an 80GB GPU at full precision can run on a consumer GPU with 8GB VRAM.

The key insight: LLM weights are highly redundant. Most weights cluster around zero and don't need 16 bits of precision. Quantization exploits this redundancy.

### GPTQ: Post-Training Quantization via Calibration

```python
import torch
import numpy as np


def gptq_quantize_layer(
    weight: torch.Tensor,     # [out_features, in_features]
    calibration_data: torch.Tensor,  # [n_samples, in_features]
    bits: int = 4,
    group_size: int = 128,
) -> tuple[torch.Tensor, dict]:
    \"\"\"
    GPTQ (Frantar et al., 2023): quantize one layer at a time using
    calibration data to minimize the quantization error.

    The algorithm: process columns one at a time. For each column,
    find the optimal quantized value that minimizes the reconstruction
    error on the calibration data. Then update the remaining columns
    to compensate for the quantization error.

    Why calibration data matters: without it, quantization treats all
    weights equally. With calibration data, GPTQ knows which weights
    are more 'important' (higher activation) and preserves their
    precision more carefully.
    \"\"\"
    W = weight.float().clone()
    n_out, n_in = W.shape

    # Compute Hessian approximation from calibration data
    # H ≈ X^T X — tells us how much each weight impacts the output
    H = calibration_data.T @ calibration_data / calibration_data.shape[0]
    H += 1e-5 * torch.eye(n_in)  # Regularization for numerical stability

    # Cholesky decomposition for efficient column processing
    H_inv = torch.linalg.cholesky(torch.linalg.inv(H))

    quantized = torch.zeros_like(W)
    scales = {}
    zeros = {}

    # Process in groups for better precision
    for group_start in range(0, n_in, group_size):
        group_end = min(group_start + group_size, n_in)

        for col in range(group_start, group_end):
            w_col = W[:, col].clone()

            # Find optimal scale and zero point for this group
            w_min = w_col.min()
            w_max = w_col.max()
            n_levels = 2 ** bits
            scale = (w_max - w_min) / (n_levels - 1)
            zero_point = torch.round(-w_min / scale).clamp(0, n_levels - 1)

            # Quantize
            q_col = torch.round(w_col / scale + zero_point).clamp(0, n_levels - 1)
            # Dequantize
            w_hat = (q_col - zero_point) * scale

            quantized[:, col] = q_col

            # Compensate remaining columns for quantization error
            error = (w_col - w_hat).unsqueeze(1)
            if col + 1 < group_end:
                h_inv_col = H_inv[col, col]
                correction = error * H_inv[col, col + 1:group_end] / h_inv_col
                W[:, col + 1:group_end] += correction

        scales[group_start] = scale
        zeros[group_start] = zero_point

    return quantized.to(torch.uint8), {"scales": scales, "zeros": zeros, "bits": bits}
```

### AWQ: Activation-Aware Quantization

```python
def awq_find_salient_channels(
    weight: torch.Tensor,
    activations: torch.Tensor,
    top_percent: float = 0.01,
) -> torch.Tensor:
    \"\"\"
    AWQ (Lin et al., 2024): protect 'salient' weight channels.

    AWQ's key insight: not all weight channels are equally important.
    The channels that correspond to HIGH activations have outsized
    impact on model quality. Protecting just 1% of channels (keeping
    them at higher precision) preserves most of the model's quality.

    This is simpler and faster than GPTQ (no iterative column processing),
    while achieving similar quality.
    \"\"\"
    # Compute per-channel importance: |activation| * |weight|
    act_importance = activations.abs().mean(dim=0)   # [in_features]
    weight_importance = weight.abs().mean(dim=0)     # [in_features]
    importance = act_importance * weight_importance

    # Find top-k salient channels
    n_salient = max(1, int(weight.shape[1] * top_percent))
    _, salient_indices = importance.topk(n_salient)

    # Create scaling factors: salient channels get higher scale
    scales = torch.ones(weight.shape[1])
    scales[salient_indices] = 2.0  # Protect salient channels

    return scales


def awq_quantize(
    weight: torch.Tensor,
    activations: torch.Tensor,
    bits: int = 4,
    group_size: int = 128,
) -> tuple[torch.Tensor, dict]:
    \"\"\"
    AWQ quantization: scale salient channels before quantization,
    then quantize uniformly.
    \"\"\"
    # Find and apply channel scaling
    scales = awq_find_salient_channels(weight, activations)

    # Scale weights (salient channels get scaled UP before quantization,
    # so quantization preserves more of their precision)
    scaled_weight = weight * scales.unsqueeze(0)

    # Standard group quantization
    n_levels = 2 ** bits
    quantized_groups = []
    group_params = []

    for g_start in range(0, weight.shape[1], group_size):
        g_end = min(g_start + group_size, weight.shape[1])
        group = scaled_weight[:, g_start:g_end]

        g_min = group.min(dim=1, keepdim=True).values
        g_max = group.max(dim=1, keepdim=True).values
        scale = (g_max - g_min) / (n_levels - 1)
        zero = torch.round(-g_min / scale)

        q_group = torch.round(group / scale + zero).clamp(0, n_levels - 1)
        quantized_groups.append(q_group)
        group_params.append({"scale": scale, "zero": zero})

    return torch.cat(quantized_groups, dim=1).to(torch.uint8), {
        "channel_scales": scales,
        "group_params": group_params,
        "bits": bits,
    }
```

### GGUF: llama.cpp's Quantization Format

```python
def explain_gguf_quant_types():
    \"\"\"
    GGUF quantization types used by llama.cpp.

    The naming convention: Q{bits}_K_{size}
    - Q4_K_M: 4-bit quantization, K-quant method, Medium size
    - The K-quant method is llama.cpp-specific: it uses importance-
      weighted quantization similar to AWQ but computed differently.
    \"\"\"
    quant_types = {
        "Q2_K": {
            "bits": 2.5,   # Average bits per weight
            "size_ratio": 0.16,  # vs FP16
            "quality": "Very low — only for testing or extreme memory constraints",
            "perplexity_increase": "+2.0-5.0",
        },
        "Q3_K_M": {
            "bits": 3.5,
            "size_ratio": 0.22,
            "quality": "Usable for simple tasks, noticeable quality loss",
            "perplexity_increase": "+0.5-1.5",
        },
        "Q4_K_M": {
            "bits": 4.5,
            "size_ratio": 0.28,
            "quality": "Sweet spot — best quality/size ratio for most use cases",
            "perplexity_increase": "+0.1-0.3",
        },
        "Q5_K_M": {
            "bits": 5.5,
            "size_ratio": 0.35,
            "quality": "Near-lossless for most tasks",
            "perplexity_increase": "+0.05-0.1",
        },
        "Q6_K": {
            "bits": 6.5,
            "size_ratio": 0.40,
            "quality": "Effectively lossless",
            "perplexity_increase": "+0.01-0.03",
        },
        "Q8_0": {
            "bits": 8.0,
            "size_ratio": 0.50,
            "quality": "Lossless for all practical purposes",
            "perplexity_increase": "+0.00-0.01",
        },
    }

    # Decision guide
    recommendations = {
        "8GB VRAM (RTX 3060/4060)": "Q4_K_M for 7B models, Q3_K_M for 14B",
        "12GB VRAM (RTX 3060 12G/4070)": "Q4_K_M for 14B, Q5_K_M for 7B",
        "16GB VRAM (RTX 4070 Ti)": "Q5_K_M for 14B, Q4_K_M for 30B",
        "24GB VRAM (RTX 3090/4090)": "Q5_K_M for 30B, Q8_0 for 14B",
        "RAM only (CPU inference)": "Q4_K_M — speed matters more than precision",
    }

    return quant_types, recommendations
```

### When to Use Each Method

| Method | Speed | Quality | Best For |
|--------|-------|---------|----------|
| **GPTQ** | Slow to quantize, fast inference | Best at 4-bit | GPU inference, maximum quality |
| **AWQ** | Fast to quantize, fast inference | Near-GPTQ quality | GPU inference, quick iteration |
| **GGUF (K-quant)** | Moderate quantize, good inference | Good across all bit widths | CPU inference, llama.cpp, Ollama |
| **BitsAndBytes** | Instant (on-the-fly) | Good for 8-bit, okay for 4-bit | Training (QLoRA), prototyping |

For HiveAI specifically: GGUF Q4_K_M is the right choice for deployment via Ollama/llama-server. It's the sweet spot — a 14B model fits in 8GB VRAM at Q4_K_M with quality loss that's barely measurable on coding benchmarks.""",
    ),
]
