"""Systems knowledge training pairs: AI/ML engineering, software architecture, and quick references."""
PAIRS = [
    # ===================== AI/ML ENGINEERING (12 pairs) =====================

    (
        "sys_know1_01",
        r'''What is TIES merge and how do I use it to combine multiple LoRA adapters? I have several LoRAs trained on different subject areas and want to merge them into one.''',
        r'''<think>
The user wants to combine multiple LoRA adapters. TIES (TrIM, Elect Sign & Merge) is a smart merging method from the paper "Resolving Interference When Merging Models." It handles the problem of conflicting parameter updates across LoRAs by trimming low-magnitude changes, resolving sign conflicts, and then averaging. I should explain the algorithm steps, when it beats simple averaging, and show a peft code example.
</think>

## TIES Merge for Combining Multiple LoRA Adapters

TIES (TrIM, Elect Sign & Merge) is a model merging algorithm designed to combine multiple fine-tuned adapters while minimizing **interference** — the problem where contradictory parameter updates from different adapters cancel each other out during naive averaging.

### Why Not Simple Averaging?

When you average two LoRA adapters, parameters where one adapter pushed a weight *up* and another pushed it *down* can cancel to near-zero, destroying both learned behaviors. TIES addresses this with a three-step process.

### The TIES Algorithm

1. **Trim**: Remove parameter deltas with small magnitudes (below a density threshold). These are mostly noise and contribute little to the adapter's learned behavior. A typical density of 0.2 means keeping only the top 20% of parameter changes by magnitude.

2. **Elect Sign**: For each parameter position, conduct a "vote" across all adapters. The sign (positive or negative) that has the largest total magnitude wins. This resolves conflicts — if 3 adapters push a weight up and 1 pushes it down, the positive direction wins.

3. **Merge**: Average only the parameter deltas that agree with the elected sign. Deltas with the wrong sign are zeroed out before averaging.

### When to Use TIES

- You have **2+ LoRA adapters** trained on different domains/subjects
- Simple averaging (or linear merge) causes quality degradation
- You want to preserve the strengths of each individual adapter
- The adapters were trained on the **same base model** with the **same LoRA config** (rank, target modules)

### Code Example with PEFT

```python
from peft import PeftModel, PeftConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import copy

def ties_merge(
    base_model_path: str,
    adapter_paths: list[str],
    density: float = 0.2,
    weights: list[float] | None = None,
) -> dict[str, torch.Tensor]:
    """
    Merge multiple LoRA adapters using TIES algorithm.

    Args:
        base_model_path: Path to the base model
        adapter_paths: List of paths to LoRA adapter directories
        density: Fraction of parameters to keep (0.0-1.0). Lower = more aggressive trimming
        weights: Optional per-adapter weights. Defaults to equal weighting.

    Returns:
        Merged state dict for the combined adapter
    """
    if weights is None:
        weights = [1.0 / len(adapter_paths)] * len(adapter_paths)

    assert len(weights) == len(adapter_paths), "weights must match number of adapters"

    # Step 0: Load all adapter state dicts and compute deltas
    adapter_states = []
    for path in adapter_paths:
        config = PeftConfig.from_pretrained(path)
        state = torch.load(f"{path}/adapter_model.bin", map_location="cpu")
        adapter_states.append(state)

    param_keys = list(adapter_states[0].keys())

    # Step 1: TRIM — zero out low-magnitude deltas
    trimmed_states = []
    for state in adapter_states:
        trimmed = {}
        for key in param_keys:
            tensor = state[key].clone()
            # Keep only the top `density` fraction by magnitude
            threshold = torch.quantile(tensor.abs().float(), 1.0 - density)
            mask = tensor.abs() >= threshold
            trimmed[key] = tensor * mask
        trimmed_states.append(trimmed)

    # Step 2: ELECT SIGN — majority vote weighted by magnitude
    elected_signs = {}
    for key in param_keys:
        # Stack all adapter values for this parameter
        stacked = torch.stack([s[key] for s in trimmed_states])
        # Sum magnitudes by sign
        pos_mass = (stacked.clamp(min=0)).sum(dim=0)
        neg_mass = (stacked.clamp(max=0)).abs().sum(dim=0)
        elected_signs[key] = torch.where(pos_mass >= neg_mass,
                                          torch.ones_like(pos_mass),
                                          -torch.ones_like(pos_mass))

    # Step 3: MERGE — average only agreeing deltas
    merged = {}
    for key in param_keys:
        accumulator = torch.zeros_like(trimmed_states[0][key])
        count = torch.zeros_like(trimmed_states[0][key])
        for i, state in enumerate(trimmed_states):
            # Only include deltas that agree with elected sign
            agrees = (state[key].sign() == elected_signs[key]) | (state[key] == 0)
            contribution = state[key] * agrees * weights[i]
            accumulator += contribution
            count += agrees.float() * weights[i]

        # Avoid division by zero
        count = count.clamp(min=1e-8)
        merged[key] = accumulator / count * count.sum() / count.numel()

    return merged


# Usage:
# merged_state = ties_merge(
#     base_model_path="Qwen/Qwen2.5-Coder-14B-Instruct",
#     adapter_paths=["loras/python_v7", "loras/js_v7", "loras/go_v7"],
#     density=0.2,
#     weights=[0.4, 0.35, 0.25],  # weight Python higher
# )
# torch.save(merged_state, "loras/merged_ties/adapter_model.bin")
```

### PEFT Built-in Support (v0.7+)

Recent versions of PEFT have built-in TIES support:

```python
from peft import PeftModel

# Load base + first adapter
model = AutoModelForCausalLM.from_pretrained(base_path)
model = PeftModel.from_pretrained(model, "loras/python_v7", adapter_name="python")

# Load additional adapters
model.load_adapter("loras/js_v7", adapter_name="js")
model.load_adapter("loras/go_v7", adapter_name="go")

# TIES merge
model.add_weighted_adapter(
    adapters=["python", "js", "go"],
    weights=[0.4, 0.35, 0.25],
    adapter_name="merged",
    combination_type="ties",
    density=0.2,
)
model.set_adapter("merged")
```

### Key Parameters

| Parameter | Typical Range | Effect |
|-----------|--------------|--------|
| `density` | 0.1–0.5 | Lower = more aggressive trimming. 0.2 is a good starting point |
| `weights` | Sum to 1.0 | Higher weight = more influence from that adapter |

### When TIES Falls Short

TIES works best when adapters learned **complementary** skills (e.g., Python vs Go). If adapters learned **conflicting** behaviors on the **same** domain (two different coding styles for Python), TIES cannot fully resolve the conflict — you would need to retrain with combined data instead.'''
    ),

    (
        "sys_know1_02",
        r'''I'm training a coding LoRA on multiple categories (Python, JS, Go, etc.) and I'm worried that adding new categories degrades performance on existing ones. How should I test for this?''',
        r'''## Subject-by-Subject Training for Regression Testing

The gold standard approach is **subject-by-subject training**: train each category independently and validate that performance holds before combining. This catches regressions early and isolates which data causes problems.

### The Process

```
For each subject category:
  1. Train LoRA on ONLY that category's data
  2. Run eval on ALL categories (not just the trained one)
  3. Record scores per category
  4. Compare against baseline (base model or previous best)
  5. Flag any category that dropped >X% as a regression

Only after all subjects pass individually:
  6. Combine all data and train final merged LoRA
  7. Run full eval again to verify combined performance
```

### Implementation

```python
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass

@dataclass
class SubjectResult:
    subject: str
    trained_score: float  # score on the trained category
    baseline_scores: dict[str, float]  # scores on all other categories
    regression_detected: bool

def train_and_eval_subject(
    subject: str,
    data_path: str,
    base_model: str,
    eval_prompts: dict[str, list[str]],
    regression_threshold: float = 0.05,
) -> SubjectResult:
    """Train on one subject, eval on all subjects."""

    output_dir = f"loras/subject_trials/{subject}"

    # Train on just this subject's data
    subprocess.run([
        "python", "scripts/train_v5.py",
        "--data", data_path,
        "--output", output_dir,
        "--epochs", "2",
    ], check=True)

    # Eval on ALL categories
    scores = {}
    for category, prompts in eval_prompts.items():
        score = run_quick_eval(output_dir, prompts)
        scores[category] = score

    # Check for regressions: did any NON-trained category drop?
    baseline = load_baseline_scores()  # scores from base model
    regressions = {}
    for cat, score in scores.items():
        if cat == subject:
            continue
        drop = baseline.get(cat, 0) - score
        if drop > regression_threshold:
            regressions[cat] = drop

    return SubjectResult(
        subject=subject,
        trained_score=scores.get(subject, 0),
        baseline_scores=scores,
        regression_detected=len(regressions) > 0,
    )

# Run all subjects
subjects = ["python", "javascript", "go", "rust", "hive", "architecture"]
results = []
for subj in subjects:
    result = train_and_eval_subject(
        subject=subj,
        data_path=f"data/categories/{subj}.jsonl",
        base_model="Qwen/Qwen2.5-Coder-14B-Instruct",
        eval_prompts=load_eval_prompts(),
    )
    results.append(result)
    print(f"{subj}: trained={result.trained_score:.3f}, "
          f"regression={'YES' if result.regression_detected else 'no'}")
```

### Why This Works

- **Isolation**: If training on Go data degrades Python scores, you catch it immediately — before it gets mixed into a combined training set where the cause is harder to diagnose
- **Data quality signal**: A subject that passes on its own domain but causes regressions likely has conflicting patterns (e.g., different coding style expectations)
- **Merge confidence**: When all subjects pass individually, you have strong evidence that a combined training should work. If the combined training still regresses, the issue is likely data volume imbalance, not data quality

### What Counts as a Regression?

A 3-5% drop threshold is reasonable for quick eval metrics. Smaller drops may be noise from sampling variance. If you see consistent 2% drops across many categories from a single subject, that is still a signal worth investigating even if no individual drop crosses the threshold.'''
    ),

    (
        "sys_know1_03",
        r'''How do I build a multi-dimension eval scoring system using an LLM as judge? I want to evaluate code responses on multiple criteria, not just pass/fail.''',
        r'''<think>
The user wants LLM-as-judge evaluation with multiple dimensions. Key design decisions: what dimensions to score, how to prompt the judge LLM, the reasoning-before-scoring pattern (makes scores more reliable), and how to aggregate. I should give a concrete implementation with a structured prompt that forces the LLM to reason through each dimension before assigning a score.
</think>

## Multi-Dimension Eval Scoring with LLM-as-Judge

Single-dimension eval (pass/fail, single 1-10 score) misses important quality distinctions. A response can pass tests but have terrible explanations, or explain beautifully but contain bugs. Multi-dimension scoring captures this.

### The Four Dimensions

| Dimension | What it measures | Weight |
|-----------|-----------------|--------|
| `code_validity` | Does the code parse, run, and handle edge cases? | 0.35 |
| `test_passing` | Would the code pass reasonable unit tests? | 0.25 |
| `concept_coverage` | Does it address the core concept(s) in the question? | 0.25 |
| `explanation_quality` | Is the explanation clear, accurate, and helpful? | 0.15 |

### The Reasoning-Before-Scoring Pattern

The critical insight: if you ask an LLM to output scores first, it anchors on snap judgments. If you force it to **reason through each dimension first**, then assign scores, the results are significantly more consistent and calibrated.

### Implementation

```python
import json
import re
from dataclasses import dataclass
from openai import OpenAI

@dataclass
class EvalScore:
    code_validity: int      # 1-5
    test_passing: int       # 1-5
    concept_coverage: int   # 1-5
    explanation_quality: int # 1-5
    reasoning: str          # judge's reasoning
    weighted_total: float   # 0.0-5.0

    @classmethod
    def from_judge_output(cls, text: str) -> "EvalScore":
        """Parse structured judge output into scores."""
        scores = {}
        for dim in ["code_validity", "test_passing", "concept_coverage", "explanation_quality"]:
            match = re.search(rf"{dim}:\s*(\d)", text)
            if match:
                scores[dim] = min(5, max(1, int(match.group(1))))
            else:
                scores[dim] = 3  # default to middle if parse fails

        weights = {"code_validity": 0.35, "test_passing": 0.25,
                    "concept_coverage": 0.25, "explanation_quality": 0.15}
        weighted = sum(scores[d] * weights[d] for d in weights)

        return cls(**scores, reasoning=text, weighted_total=weighted)


JUDGE_PROMPT = """You are an expert code reviewer evaluating an AI assistant's response to a coding question.

## Question
{question}

## Response to Evaluate
{response}

## Instructions
Evaluate the response on four dimensions. For EACH dimension, first write 2-3 sentences of reasoning, then assign a score from 1-5.

**Scoring scale:**
- 1: Completely wrong or missing
- 2: Major issues, partially addresses the task
- 3: Acceptable but with notable gaps
- 4: Good, minor issues only
- 5: Excellent, comprehensive and accurate

## Required Output Format (follow exactly):

### Code Validity Analysis
[Your reasoning about whether the code is syntactically correct, would run, handles edge cases...]
code_validity: [1-5]

### Test Passing Analysis
[Your reasoning about whether the code would pass unit tests, produces correct output...]
test_passing: [1-5]

### Concept Coverage Analysis
[Your reasoning about whether core concepts from the question are addressed...]
concept_coverage: [1-5]

### Explanation Quality Analysis
[Your reasoning about clarity, accuracy, and helpfulness of explanations...]
explanation_quality: [1-5]"""


def judge_response(
    client: OpenAI,
    question: str,
    response: str,
    model: str = "gpt-4o",
) -> EvalScore:
    """Score a response using LLM-as-judge with reasoning-before-scoring."""
    result = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a rigorous but fair code review evaluator."},
            {"role": "user", "content": JUDGE_PROMPT.format(
                question=question, response=response
            )},
        ],
        temperature=0.1,  # low temp for consistency
        max_tokens=1500,
    )
    return EvalScore.from_judge_output(result.choices[0].message.content)


def run_eval_suite(
    client: OpenAI,
    eval_pairs: list[tuple[str, str, str]],  # (id, question, response)
) -> dict:
    """Run multi-dimension eval on a batch of responses."""
    results = {}
    for pair_id, question, response in eval_pairs:
        score = judge_response(client, question, response)
        results[pair_id] = {
            "weighted_total": score.weighted_total,
            "code_validity": score.code_validity,
            "test_passing": score.test_passing,
            "concept_coverage": score.concept_coverage,
            "explanation_quality": score.explanation_quality,
        }
        print(f"{pair_id}: {score.weighted_total:.2f} "
              f"(cv={score.code_validity} tp={score.test_passing} "
              f"cc={score.concept_coverage} eq={score.explanation_quality})")

    avg = sum(r["weighted_total"] for r in results.values()) / len(results)
    print(f"\nOverall weighted average: {avg:.2f}/5.0")
    return results
```

### Calibration Tips

1. **Run the same response through the judge 3 times** and average — LLM judges have variance even at low temperature
2. **Include 5-10 "anchor" responses** with known-good scores to detect judge drift
3. **Log the full reasoning**, not just scores — when a score seems wrong, the reasoning tells you whether the judge misunderstood the question or the response
4. **Use the strongest available judge model** — GPT-4o or Claude Opus as judge produces much more reliable scores than smaller models'''
    ),

    (
        "sys_know1_04",
        r'''Can you describe the architecture for a self-improving AI training loop? I want to automatically identify weaknesses in my model and generate targeted training data to fix them.''',
        r'''<think>
This is about a continuous improvement loop for AI training. The key stages are: run eval to find failures, categorize the failures to understand what's weak, generate targeted training data for those weaknesses, retrain, eval again as a quality gate, and deploy only if improved. I should emphasize the eval gate — without it you can make things worse. Also important: the failure mining step needs to be structured, not just "find bad outputs."
</think>

## Self-Improving AI Loop Architecture

The core idea is to close the loop between evaluation and training data generation, so the model automatically improves on its weaknesses over time. Here is the full architecture.

### The Six-Stage Loop

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐ │
│  │ 1. EVAL  │───▶│ 2. FAILURE   │───▶│ 3. TARGETED   │ │
│  │ (run     │    │    MINING &   │    │    DATA GEN   │ │
│  │  full    │    │  CATEGORIZE  │    │  (distill for │ │
│  │  suite)  │    │              │    │   weak areas) │ │
│  └──────────┘    └──────────────┘    └───────┬───────┘ │
│       ▲                                      │         │
│       │                                      ▼         │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐ │
│  │ 6.DEPLOY │◀───│ 5. EVAL GATE │◀───│ 4. RETRAIN    │ │
│  │ (if      │    │ (pass/fail   │    │  (incremental │ │
│  │  passed) │    │  threshold)  │    │   on new data)│ │
│  └──────────┘    └──────────────┘    └───────────────┘ │
│       │                                                 │
│       └──── loop back to stage 1 ──────────────────────┘
```

### Stage 1: Eval — Find What's Broken

Run a comprehensive eval suite that covers all target capabilities:

```python
def run_full_eval(model_path: str) -> dict[str, float]:
    """Run eval across all categories, return per-category scores."""
    categories = {
        "python": load_eval_prompts("python"),
        "javascript": load_eval_prompts("javascript"),
        "architecture": load_eval_prompts("architecture"),
        "debugging": load_eval_prompts("debugging"),
        "explanation": load_eval_prompts("explanation"),
    }
    scores = {}
    for cat, prompts in categories.items():
        scores[cat] = evaluate_category(model_path, prompts)
    return scores
```

### Stage 2: Failure Mining & Categorization

This is the most important stage. Don't just note "the model scored 0.6 on debugging" — analyze *why* it failed:

```python
from dataclasses import dataclass

@dataclass
class FailureCase:
    category: str
    prompt: str
    model_output: str
    expected_behavior: str
    failure_type: str  # "wrong_logic", "missing_edge_case", "wrong_api", etc.
    severity: int      # 1-3

def mine_failures(
    eval_results: list[dict],
    score_threshold: float = 0.6,
) -> list[FailureCase]:
    """Extract and categorize failures from eval results."""
    failures = []
    for result in eval_results:
        if result["score"] < score_threshold:
            # Use LLM to categorize the failure type
            failure_type = classify_failure(
                prompt=result["prompt"],
                output=result["model_output"],
                expected=result["expected"],
            )
            failures.append(FailureCase(
                category=result["category"],
                prompt=result["prompt"],
                model_output=result["model_output"],
                expected_behavior=result["expected"],
                failure_type=failure_type,
                severity=result.get("difficulty", 2),
            ))

    # Group by failure type for targeted data generation
    from collections import Counter
    type_counts = Counter(f.failure_type for f in failures)
    print("Failure distribution:")
    for ftype, count in type_counts.most_common():
        print(f"  {ftype}: {count}")

    return failures
```

### Stage 3: Targeted Data Generation

Generate training data specifically for the identified weaknesses:

```python
def generate_targeted_data(
    failures: list[FailureCase],
    teacher_model: str = "claude-opus-4-20250514",
    pairs_per_failure_type: int = 20,
) -> list[dict]:
    """Distill training pairs targeting identified weaknesses."""
    # Group failures by type
    from itertools import groupby
    grouped = {}
    for f in failures:
        grouped.setdefault(f.failure_type, []).append(f)

    new_pairs = []
    for failure_type, examples in grouped.items():
        # Build a meta-prompt showing the failure pattern
        prompt = f"""Generate {pairs_per_failure_type} training pairs that teach
a coding assistant to handle "{failure_type}" correctly.

Here are examples of questions where the model failed:
{[e.prompt for e in examples[:5]]}

Common mistakes the model made:
{[e.model_output[:200] for e in examples[:3]]}

Generate diverse questions that exercise this skill, with
high-quality answers that avoid the mistakes shown above."""

        pairs = call_teacher_model(teacher_model, prompt)
        new_pairs.extend(pairs)

    return new_pairs
```

### Stage 4: Retrain

Incrementally train on the new data **combined with a replay buffer** of existing good data (prevents catastrophic forgetting):

```python
def retrain_with_replay(
    new_data: list[dict],
    replay_buffer_path: str,
    replay_ratio: float = 0.3,
):
    """Train on new targeted data + replay buffer to prevent forgetting."""
    replay_data = load_jsonl(replay_buffer_path)

    # Sample replay_ratio of existing data to mix in
    import random
    replay_sample = random.sample(
        replay_data,
        min(len(replay_data), int(len(new_data) * replay_ratio / (1 - replay_ratio)))
    )

    combined = new_data + replay_sample
    random.shuffle(combined)
    save_jsonl(combined, "data/improvement_round.jsonl")

    # Train
    train(data_path="data/improvement_round.jsonl", output="loras/improvement_round")
```

### Stage 5: Eval Gate (Critical)

**Never deploy without passing the eval gate.** This prevents regressions:

```python
def eval_gate(
    new_model: str,
    previous_scores: dict[str, float],
    regression_tolerance: float = 0.03,
    improvement_required: float = 0.02,
) -> bool:
    """Gate deployment: must improve on weak areas without regressing on strong ones."""
    new_scores = run_full_eval(new_model)

    regressions = []
    improvements = []
    for cat, old_score in previous_scores.items():
        new_score = new_scores.get(cat, 0)
        delta = new_score - old_score
        if delta < -regression_tolerance:
            regressions.append((cat, delta))
        elif delta > improvement_required:
            improvements.append((cat, delta))

    if regressions:
        print(f"GATE FAILED — regressions: {regressions}")
        return False

    if not improvements:
        print("GATE FAILED — no meaningful improvements detected")
        return False

    print(f"GATE PASSED — improvements: {improvements}")
    return True
```

### Stage 6: Deploy & Loop

If the gate passes, deploy the new model and update the replay buffer with the new training data. Then loop back to Stage 1 for the next improvement cycle.

### Key Design Principles

1. **The eval gate is non-negotiable** — without it, you will eventually ship a regression
2. **Replay buffer prevents forgetting** — always mix old successful data with new targeted data
3. **Categorize failures, don't just count them** — "60% on debugging" is not actionable, but "fails on async debugging because it forgets to await" is
4. **Each loop iteration should be small** — 20-50 new pairs targeting specific weaknesses, not 500 pairs hoping something sticks
5. **Log everything** — every loop iteration's eval scores, failure categories, generated data, and gate decisions should be persisted for debugging'''
    ),

    (
        "sys_know1_05",
        r'''Explain the batch file pattern for managing training data: having many small Python files that get aggregated into a single JSONL for training. What are the advantages over just editing one big JSONL directly?''',
        r'''## Training Data Pipeline: The Batch File Pattern

The batch file pattern uses **many small Python files** (each containing a `PAIRS` list) that get aggregated by a build script into a single JSONL file for training. Here is how it works and why it is better than editing JSONL directly.

### The Structure

```
scripts/distill_batches/
├── batch_p0001_python_basics.py      # 25 pairs
├── batch_p0002_python_async.py       # 25 pairs
├── batch_p0003_js_fundamentals.py    # 25 pairs
├── ...
├── batch_p1200_hive_security.py      # 25 pairs
└── __init__.py

scripts/prepare_v5_data.py            # Aggregator: reads all batch files → v5.jsonl
loras/training_data/v5.jsonl          # Build artifact (gitignored)
```

Each batch file is a simple Python module:

```python
"""Python async/await training pairs."""
PAIRS = [
    (
        "py_async_01",
        "How do I run multiple HTTP requests concurrently in Python?",
        "Use asyncio.gather() with aiohttp...",
    ),
    (
        "py_async_02",
        "What's the difference between threading and asyncio?",
        "<think>\nThe user is asking about concurrency models...\n</think>\n\nThreading uses OS threads...",
    ),
    # ... more pairs
]
```

The aggregator script:

```python
import importlib
import json
from pathlib import Path
from typing import Iterator

def load_all_pairs(batch_dir: str = "scripts/distill_batches") -> Iterator[dict]:
    """Import all batch files and yield ChatML-formatted training pairs."""
    batch_path = Path(batch_dir)
    seen_ids = set()

    for py_file in sorted(batch_path.glob("batch_p*.py")):
        module_name = py_file.stem
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "PAIRS"):
            print(f"WARNING: {py_file.name} has no PAIRS list, skipping")
            continue

        for pair_id, question, answer in module.PAIRS:
            if pair_id in seen_ids:
                print(f"DUPLICATE ID: {pair_id} in {py_file.name}")
                continue
            seen_ids.add(pair_id)

            yield {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ]
            }

def export_jsonl(output_path: str = "loras/training_data/v5.jsonl"):
    pairs = list(load_all_pairs())
    with open(output_path, "w") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")
    print(f"Exported {len(pairs)} pairs to {output_path}")
```

### Advantages Over Editing JSONL Directly

**1. Git-friendly diffs**

A 50MB JSONL file is nearly impossible to review in a pull request. When you change one training pair, `git diff` shows the entire line (which might be 5KB of JSON). With batch files, each pair is clearly separated with readable Python strings, and diffs are clean.

**2. Parallel contribution**

Multiple team members can add batch files simultaneously without merge conflicts. Two people editing the same JSONL file will always conflict. With batch files, each person works on their own file.

**3. Category organization**

File names encode category metadata: `batch_p0350_hive_economics.py` tells you what is inside without opening it. You can count pairs per category with a simple glob, and selectively include/exclude categories by modifying the aggregator.

**4. Deduplication**

The aggregator can check for duplicate IDs across all batch files at build time. With raw JSONL, you need a separate dedup script.

**5. The JSONL is a build artifact**

The JSONL file is gitignored because it can be regenerated from batch files at any time. This keeps the repo smaller and ensures the batch files are the source of truth.

**6. Validation**

Because batch files are Python, you get syntax checking for free. You can also add validation in the aggregator: check that each pair has exactly 3 elements, IDs follow naming conventions, responses are not too long, etc.

### Disadvantage

The main cost is slightly more complex tooling — you need the aggregator script, and adding a pair requires creating/editing a Python file rather than appending a JSON line. For small projects (<100 pairs), a single JSONL may be simpler. The batch pattern pays off at scale (500+ pairs, multiple contributors).'''
    ),

    (
        "sys_know1_06",
        r'''I'm oversampling domain-specific data in my training set (2x for Hive blockchain pairs) but my eval scores haven't improved. What could be going wrong?''',
        r'''<think>
The user is oversampling domain-specific data but not seeing improvement. The most common pitfall is that naive oversampling creates exact duplicates, which the model memorizes rather than generalizes from. I need to explain why duplicates waste training budget, how to detect the issue, and what to do instead (paraphrasing, augmentation, or higher-quality unique pairs).
</think>

## Oversampling Pitfalls: Zero-Novelty Duplicates

The most likely problem is that your 2x oversampling is creating **exact duplicates** of existing pairs. When the model sees the same question-answer pair twice in an epoch, the second occurrence provides **zero novel gradient signal** — the model already learned to reproduce that exact output. You are spending training compute on data the model has already memorized.

### Why Duplicates Waste Training Budget

```
Normal training:
  Pair A (first seen) → large gradient update → model learns new pattern
  Pair B (first seen) → large gradient update → model learns new pattern

With 2x oversampling (naive duplication):
  Pair A (first seen)  → large gradient update → model learns pattern
  Pair A (duplicate)   → tiny gradient update  → model already knows this
  Pair B (first seen)  → large gradient update → model learns pattern
  Pair B (duplicate)   → tiny gradient update  → already knows this

Result: 2x the training time, ~1x the learning
```

Even worse, heavy duplication can cause **overfitting to the oversampled domain** at the expense of other categories. The model spends disproportionate capacity memorizing Hive-specific phrasings rather than learning generalizable coding patterns.

### How to Detect the Problem

```python
import json
from collections import Counter

def check_training_duplication(jsonl_path: str):
    """Detect exact and near-duplicate pairs in training data."""
    pairs = []
    with open(jsonl_path) as f:
        for line in f:
            msg = json.loads(line)
            user_msg = next(
                m["content"] for m in msg["messages"] if m["role"] == "user"
            )
            pairs.append(user_msg)

    # Exact duplicates
    counts = Counter(pairs)
    dupes = {q: c for q, c in counts.items() if c > 1}
    total_wasted = sum(c - 1 for c in dupes.values())

    print(f"Total pairs: {len(pairs)}")
    print(f"Unique pairs: {len(counts)}")
    print(f"Duplicated pairs: {len(dupes)}")
    print(f"Wasted training examples: {total_wasted}")

    if dupes:
        print("\nMost duplicated:")
        for q, c in sorted(dupes.items(), key=lambda x: -x[1])[:5]:
            print(f"  [{c}x] {q[:80]}...")

check_training_duplication("loras/training_data/v5.jsonl")
```

### Better Alternatives to Naive Oversampling

**1. Paraphrase augmentation** — Use an LLM to rephrase the same question in different ways:

```python
def augment_pair(question: str, answer: str, teacher_model) -> list[tuple[str, str]]:
    """Generate paraphrased versions of a training pair."""
    prompt = f"""Rephrase this coding question 3 different ways.
Keep the same technical intent but change the wording, context, or framing.

Original: {question}

Return exactly 3 rephrased versions, one per line."""

    rephrased = call_teacher(teacher_model, prompt)
    return [(q.strip(), answer) for q in rephrased.split("\n") if q.strip()]
```

**2. Scenario variation** — Same concept, different concrete scenario:

Instead of duplicating "How do I transfer HIVE tokens?", generate:
- "How do I send HIVE to another account using Python?"
- "Write a function that transfers HIVE and handles insufficient balance"
- "How do I batch multiple HIVE transfers in one transaction?"

Each teaches the same core concept but requires different code patterns.

**3. Weighted loss instead of oversampling** — Give domain pairs higher loss weight without duplicating them:

```python
# In your data collator or loss function
domain_weight = 2.0  # equivalent to 2x oversampling but no duplication
general_weight = 1.0

for batch in dataloader:
    loss = compute_loss(batch)
    if batch["domain"] == "hive":
        loss = loss * domain_weight
    loss.backward()
```

**4. Generate MORE unique pairs** — The best option. If you have 200 Hive pairs and want 2x representation, distill 200 more unique pairs instead of duplicating the existing 200. This gives the model 400 unique learning signals instead of 200 signals seen twice.

### Rule of Thumb

If your oversampled data has more than 5% exact duplicates, you are wasting training budget. Every duplicated pair should be replaced with a paraphrase or a new unique pair covering the same concept from a different angle.'''
    ),

    (
        "sys_know1_07",
        r'''What is NEFTune noise injection and should I use it for LoRA fine-tuning?''',
        r'''## NEFTune: Noisy Embedding Fine-Tuning

NEFTune adds **uniform random noise to token embeddings during training** (not during inference). The noise is added after the embedding layer but before the transformer blocks process the input.

### How It Works

```python
# Simplified NEFTune implementation
def neftune_forward(model, input_ids, noise_alpha=5.0):
    embeddings = model.get_input_embeddings()(input_ids)

    if model.training:
        # Add uniform noise scaled by alpha / sqrt(seq_len * embed_dim)
        seq_len, embed_dim = embeddings.shape[1], embeddings.shape[2]
        mag = noise_alpha / (seq_len * embed_dim) ** 0.5
        noise = torch.zeros_like(embeddings).uniform_(-1, 1) * mag
        embeddings = embeddings + noise

    return model(inputs_embeds=embeddings)
```

The noise acts as a **regularizer**: it forces the model to be robust to small perturbations in input representations, which discourages overfitting to exact token sequences in the training data.

### Typical Alpha Values

| Alpha | Effect | Use case |
|-------|--------|----------|
| 5 | Light noise, safe default | Most LoRA fine-tuning |
| 10 | Moderate noise | Small datasets (<500 pairs) prone to overfitting |
| 15 | Aggressive noise | Very small datasets or when you see severe overfitting |
| >15 | Usually too much | Degrades learning signal |

### When to Use It

**Good candidates for NEFTune:**
- Small training datasets (under 1000 pairs) where overfitting is a risk
- You see a big gap between training loss and validation loss
- Your model memorizes training examples instead of generalizing

**Skip NEFTune when:**
- Large dataset (5000+ pairs) — natural data diversity provides enough regularization
- You are already using other regularization (dropout, weight decay) and overfitting is not observed
- Training for very few steps (1 epoch) — not enough exposure for overfitting to occur

### Enabling in HuggingFace TRL

```python
from trl import SFTTrainer, SFTConfig

training_args = SFTConfig(
    output_dir="loras/my_lora",
    neftune_noise_alpha=5.0,  # that's it — TRL handles the rest
    num_train_epochs=2,
    # ... other args
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
)
```

NEFTune is lightweight (negligible compute cost) and easy to experiment with. If you are unsure, try alpha=5 and compare eval scores with and without — it often provides a small but consistent improvement on small to medium datasets.'''
    ),

    (
        "sys_know1_08",
        r'''How should I use a small fixed eval prompt set as a deployment gate? I want fast go/no-go decisions before running my expensive full evaluation.''',
        r'''## Quick Eval as a Deployment Gate

A quick eval is a **small fixed set of prompts** (typically 15-30) that you run against every model checkpoint for a fast pass/fail decision. It takes minutes instead of hours, and catches obvious regressions before you commit to expensive full evaluation.

### Design Principles

1. **Fixed prompts, never changed** — The prompts must stay identical across all evaluations so scores are comparable. If you change the prompts, you invalidate all historical comparisons.

2. **Cover critical capabilities** — Pick 2-3 prompts per core category. These should be "canary" prompts that detect category-level regressions.

3. **Include known-hard cases** — Include prompts the base model gets wrong but your fine-tuned model should get right. These validate that training added value.

4. **A/B comparison** — Always compare against a reference (base model or previous best), not against absolute scores. This eliminates variance from prompt difficulty.

### Implementation

```python
import json
import time
from pathlib import Path
from dataclasses import dataclass

@dataclass
class QuickEvalResult:
    passed: bool
    score: float
    reference_score: float
    per_category: dict[str, float]
    duration_seconds: float

# Fixed prompt set — NEVER modify these after establishing baseline
QUICK_EVAL_PROMPTS = {
    "python": [
        "Write a Python function that finds the longest common subsequence of two strings.",
        "How do I handle file uploads in FastAPI with size limits and type validation?",
        "Explain Python's GIL and how it affects multithreaded programs.",
    ],
    "javascript": [
        "Implement a debounce function in TypeScript with proper generics.",
        "How does the JavaScript event loop handle microtasks vs macrotasks?",
    ],
    "architecture": [
        "Design a rate limiter for an API that supports both per-user and global limits.",
        "What are the tradeoffs between microservices and a modular monolith?",
    ],
    "debugging": [
        "My Python async code deadlocks when I call asyncio.run() inside an existing event loop. How do I fix this?",
    ],
    # ... total: 15-30 prompts
}

def run_quick_eval(
    model_endpoint: str,
    reference_endpoint: str,
    pass_threshold: float = 0.45,  # must win >45% of A/B comparisons
) -> QuickEvalResult:
    """Fast go/no-go eval using fixed prompt set."""
    start = time.time()
    wins, losses, ties = 0, 0, 0
    category_scores = {}

    for category, prompts in QUICK_EVAL_PROMPTS.items():
        cat_wins = 0
        for prompt in prompts:
            # Get responses from both models
            candidate = query_model(model_endpoint, prompt)
            reference = query_model(reference_endpoint, prompt)

            # LLM-as-judge comparison (blind — randomize order)
            winner = judge_ab(prompt, candidate, reference)
            if winner == "A":
                wins += 1
                cat_wins += 1
            elif winner == "B":
                losses += 1
            else:
                ties += 1

        category_scores[category] = cat_wins / len(prompts)

    total = wins + losses + ties
    score = (wins + 0.5 * ties) / total
    ref_score = (losses + 0.5 * ties) / total

    passed = score >= pass_threshold
    duration = time.time() - start

    print(f"Quick eval: {'PASS' if passed else 'FAIL'} "
          f"({score:.1%} vs {ref_score:.1%}, {duration:.0f}s)")

    return QuickEvalResult(
        passed=passed,
        score=score,
        reference_score=ref_score,
        per_category=category_scores,
        duration_seconds=duration,
    )
```

### Decision Flow

```
New checkpoint ready
        │
        ▼
  Quick eval (5-10 min)
        │
    ┌───┴───┐
    │ FAIL  │ → Stop. Don't waste time on full eval.
    └───┬───┘   Investigate what regressed.
        │
    ┌───┴───┐
    │ PASS  │ → Proceed to full eval (1-2 hours).
    └───┬───┘
        │
        ▼
  Full eval confirms? → Deploy
```

### Key Metrics to Track

Log every quick eval result with timestamp, model version, and per-category breakdown. Over time, this gives you a trendline showing whether training iterations are moving in the right direction — even small improvements compound across iterations.'''
    ),

    (
        "sys_know1_09",
        r'''How do I format multi-turn conversations in ChatML format for SFT training? I want the model to learn from conversation history, not just single-turn Q&A.''',
        r'''<think>
The user wants to train on multi-turn conversations using ChatML format. I need to explain the token structure with <|im_start|>/<|im_end|>, how to handle system + multiple user/assistant turns, and the key consideration of masking loss on non-assistant turns. Multi-turn is trickier than single-turn because you need to mask the user turns and only compute loss on assistant responses.
</think>

## ChatML Multi-Turn Format for SFT Training

ChatML uses `<|im_start|>role\n` and `<|im_end|>` tokens to delimit each message in a conversation. For multi-turn SFT, you need to structure the full conversation in a single training example while only computing loss on the assistant turns.

### The Token Structure

```
<|im_start|>system
You are a helpful coding assistant.<|im_end|>
<|im_start|>user
How do I read a CSV file in Python?<|im_end|>
<|im_start|>assistant
Use pandas: `pd.read_csv("file.csv")`<|im_end|>
<|im_start|>user
What if the file has no header row?<|im_end|>
<|im_start|>assistant
Pass `header=None`: `pd.read_csv("file.csv", header=None)`<|im_end|>
```

### JSONL Format for Training

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful coding assistant."},
    {"role": "user", "content": "How do I read a CSV file in Python?"},
    {"role": "assistant", "content": "Use pandas: `pd.read_csv(\"file.csv\")`"},
    {"role": "user", "content": "What if the file has no header row?"},
    {"role": "assistant", "content": "Pass `header=None`: `pd.read_csv(\"file.csv\", header=None)`"}
  ]
}
```

### Loss Masking: Only Train on Assistant Turns

The critical detail for multi-turn SFT: you should only compute loss on the **assistant** tokens, not on the system prompt or user messages. The model should learn to *generate* good assistant responses given the conversation history, not to *generate* user messages.

```python
from trl import SFTTrainer, SFTConfig, DataCollatorForCompletionOnlyLM
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-Coder-14B-Instruct")

# The response template marks where assistant content begins
# For ChatML, the assistant turn starts with this token sequence
response_template = "<|im_start|>assistant\n"

# DataCollatorForCompletionOnlyLM masks loss on everything
# BEFORE each response_template occurrence
collator = DataCollatorForCompletionOnlyLM(
    response_template=response_template,
    tokenizer=tokenizer,
)

# This automatically handles multi-turn: it finds ALL occurrences
# of the response template and only computes loss on the tokens
# between each <|im_start|>assistant\n and the next <|im_end|>

trainer = SFTTrainer(
    model=model,
    args=SFTConfig(
        output_dir="loras/multi_turn",
        num_train_epochs=2,
        max_seq_length=4096,  # must fit the full conversation
    ),
    train_dataset=dataset,
    data_collator=collator,
    tokenizer=tokenizer,
)
```

### Key Considerations

**1. Sequence length**: Multi-turn conversations are longer than single-turn. A 3-turn conversation might use 2000+ tokens. Set `max_seq_length` high enough to avoid truncating conversations, but not so high that you waste memory.

**2. Truncation strategy**: If a conversation exceeds max length, truncate from the **beginning** (remove early turns), not the end. The most recent turns are usually the most important for learning the response pattern.

**3. Each assistant turn is a learning signal**: In a 3-turn conversation, the model learns from all 3 assistant responses, not just the last one. This means a single multi-turn example provides more training signal than a single-turn pair.

**4. Consistency across turns**: Ensure the assistant's responses within a multi-turn conversation are internally consistent. If the first turn establishes a coding approach, later turns should build on it, not contradict it.

### When to Use Multi-Turn Training

- Teaching the model to handle **follow-up questions** and **clarifications**
- Training **contextual awareness** — the model needs to remember what was discussed earlier
- Teaching **progressive problem-solving** — breaking complex tasks into conversation steps

For standalone coding questions that do not require conversation context, single-turn pairs are simpler and equally effective.'''
    ),

    (
        "sys_know1_10",
        r'''How do I fit a 14B parameter model for LoRA fine-tuning on a 16GB VRAM GPU? What techniques are needed?''',
        r'''## Fitting 14B Models on 16GB VRAM with QLoRA

A 14B parameter model in FP16 requires ~28GB VRAM just for the weights — far more than 16GB. The solution is to combine **4-bit quantization** (QLoRA), **gradient checkpointing**, and **8-bit optimizers** to reduce memory usage by approximately 4x.

### The Memory Stack

```
FP16 14B model:          ~28 GB  ← won't fit
4-bit quantized (QLoRA): ~7 GB   ← fits, but need room for:
  + LoRA adapters (FP16): ~0.3 GB
  + Gradients:            ~0.6 GB
  + Optimizer states:     ~1.2 GB (8-bit) or ~2.4 GB (FP32)
  + Activations:          ~4-8 GB (without gradient checkpointing)
                          ~1-2 GB (with gradient checkpointing)
─────────────────────────────────
Total with all tricks:    ~10-11 GB ← fits in 16 GB
```

### Implementation

```python
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# 1. Load model in 4-bit quantization
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",           # normalized float 4-bit
    bnb_4bit_compute_dtype=torch.bfloat16, # compute in bf16 for speed
    bnb_4bit_use_double_quant=True,       # quantize the quantization constants too
)

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-Coder-14B-Instruct",
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)

# 2. Prepare model for k-bit training (freezes base, enables gradient for LoRA)
model = prepare_model_for_kbit_training(model)

# 3. Enable gradient checkpointing (trades compute for memory)
model.gradient_checkpointing_enable()

# 4. Add LoRA adapters
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.1,
    bias="none",
    task_type="CAUSAL_LM",
    use_rslora=True,  # rank-stabilized LoRA
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# Trainable: ~25M params (0.18% of 14B)

# 5. Training args with 8-bit optimizer and memory optimizations
training_args = TrainingArguments(
    output_dir="loras/my_lora",
    num_train_epochs=2,
    per_device_train_batch_size=1,        # batch size 1 to save memory
    gradient_accumulation_steps=8,        # effective batch size = 8
    optim="adamw_8bit",                   # 8-bit Adam saves ~50% optimizer memory
    bf16=True,
    gradient_checkpointing=True,
    max_grad_norm=0.3,
    warmup_ratio=0.05,
    learning_rate=2e-4,
    logging_steps=10,
    save_strategy="epoch",
)
```

### What Each Technique Does

| Technique | Memory Saved | Trade-off |
|-----------|-------------|-----------|
| 4-bit quantization (NF4) | ~21 GB (28→7 GB for weights) | Slight quality loss vs FP16 (usually negligible for LoRA) |
| Gradient checkpointing | ~3-6 GB (recomputes activations during backward) | ~30% slower training (recomputation cost) |
| 8-bit Adam optimizer | ~1.2 GB (half the optimizer state) | Negligible quality impact |
| Batch size 1 + grad accum | ~2-4 GB (fewer simultaneous activations) | Same effective training, just slower per-step |
| Double quantization | ~0.4 GB (quantizes NF4 scaling factors) | No measurable quality impact |

### Monitoring VRAM During Training

```python
# Add to training loop or as a callback
def log_gpu_memory():
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
    print(f"GPU memory: {allocated:.1f} GB allocated, {reserved:.1f} GB reserved")
```

If you are still running out of memory after all these techniques, reduce `max_seq_length` (shorter sequences use less activation memory) or reduce LoRA rank from 16 to 8.'''
    ),

    (
        "sys_know1_11",
        r'''My model training sometimes gets stuck — the training step hangs for hours without producing output. How do I build a watchdog/heartbeat system to detect and handle hung training?''',
        r'''<think>
Training hangs are a real problem, especially with GPU workloads — they can be caused by GPU deadlocks, memory issues, data loading problems, or network issues (in distributed training). A watchdog needs to: monitor the training loop's progress, detect when steps stop advancing, and take action (alert, log, or kill/restart). I should show a practical implementation using a background thread.
</think>

## Training Heartbeat/Watchdog for Hung Step Detection

A training watchdog runs in a background thread, monitors the timestamp of the last completed training step, and triggers an alert or auto-kill if the gap exceeds a timeout.

### Implementation

```python
import threading
import time
import signal
import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from transformers import TrainerCallback

logger = logging.getLogger(__name__)

@dataclass
class TrainingWatchdog:
    """Monitors training progress and detects hung steps."""
    timeout_seconds: float = 600  # 10 minutes per step max
    check_interval: float = 30   # check every 30 seconds
    alert_callback: callable = None  # optional: send Slack/email alert
    auto_kill: bool = False      # kill training if hung

    _last_heartbeat: float = field(default_factory=time.time, init=False)
    _current_step: int = field(default=0, init=False)
    _running: bool = field(default=False, init=False)
    _thread: threading.Thread = field(default=None, init=False)

    def heartbeat(self, step: int):
        """Call this after each training step completes."""
        self._last_heartbeat = time.time()
        self._current_step = step

    def start(self):
        """Start the watchdog background thread."""
        self._running = True
        self._last_heartbeat = time.time()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"Watchdog started (timeout={self.timeout_seconds}s)")

    def stop(self):
        """Stop the watchdog."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _monitor_loop(self):
        while self._running:
            time.sleep(self.check_interval)
            elapsed = time.time() - self._last_heartbeat

            if elapsed > self.timeout_seconds:
                msg = (f"TRAINING HUNG: step {self._current_step} "
                       f"has not advanced in {elapsed:.0f}s "
                       f"(timeout={self.timeout_seconds}s)")
                logger.error(msg)

                # Save diagnostic info
                self._dump_diagnostics()

                if self.alert_callback:
                    self.alert_callback(msg)

                if self.auto_kill:
                    logger.error("Auto-killing training process")
                    os.kill(os.getpid(), signal.SIGTERM)
                    return
            elif elapsed > self.timeout_seconds * 0.5:
                # Warning at 50% of timeout
                logger.warning(
                    f"Step {self._current_step} running for {elapsed:.0f}s "
                    f"(warning threshold)")

    def _dump_diagnostics(self):
        """Save diagnostic information when a hang is detected."""
        diag_path = Path("logs/watchdog_dump.txt")
        diag_path.parent.mkdir(exist_ok=True)
        with open(diag_path, "a") as f:
            f.write(f"\n=== HUNG DETECTED: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write(f"Step: {self._current_step}\n")
            f.write(f"Seconds since last heartbeat: "
                    f"{time.time() - self._last_heartbeat:.0f}\n")
            try:
                import torch
                if torch.cuda.is_available():
                    f.write(f"GPU memory allocated: "
                            f"{torch.cuda.memory_allocated()/1024**3:.1f} GB\n")
                    f.write(f"GPU memory reserved: "
                            f"{torch.cuda.memory_reserved()/1024**3:.1f} GB\n")
            except Exception as e:
                f.write(f"GPU info unavailable: {e}\n")


class WatchdogCallback(TrainerCallback):
    """HuggingFace Trainer callback that sends heartbeats to the watchdog."""

    def __init__(self, watchdog: TrainingWatchdog):
        self.watchdog = watchdog

    def on_train_begin(self, args, state, control, **kwargs):
        self.watchdog.start()

    def on_step_end(self, args, state, control, **kwargs):
        self.watchdog.heartbeat(state.global_step)

    def on_train_end(self, args, state, control, **kwargs):
        self.watchdog.stop()


# Usage with HuggingFace Trainer:
watchdog = TrainingWatchdog(
    timeout_seconds=600,    # 10 min timeout per step
    auto_kill=True,         # kill if hung (for unattended runs)
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    callbacks=[WatchdogCallback(watchdog)],
)
trainer.train()
```

### Timeout Guidelines

| Model Size | Typical Step Time | Suggested Timeout |
|-----------|-------------------|-------------------|
| 7B QLoRA | 2-10s | 120s |
| 14B QLoRA | 5-30s | 300s |
| 14B QLoRA (long seq) | 30-120s | 600s |
| 70B QLoRA | 30-180s | 900s |

Set the timeout to roughly 5-10x your typical step time. This provides enough margin for occasional slow steps (garbage collection, checkpointing) without missing genuine hangs.

### Common Causes of Hung Training

1. **GPU memory fragmentation** — CUDA OOM that hangs instead of crashing. Fix: reduce batch size or sequence length
2. **Data loader deadlock** — `num_workers > 0` with certain datasets can deadlock. Fix: try `num_workers=0`
3. **Disk I/O stall** — Checkpointing to a slow/full disk. Fix: ensure output dir has space, use SSD
4. **NCCL timeout** (multi-GPU) — One GPU dies, others wait forever. Fix: set `NCCL_TIMEOUT` environment variable'''
    ),

    (
        "sys_know1_12",
        r'''I have thousands of training pairs and want to automatically prioritize which ones are most valuable. How do I score training data by importance?''',
        r'''## Importance Scoring for Training Data Curation

Not all training pairs contribute equally. A composite importance score helps you prioritize high-value pairs and cut low-value ones, making training more efficient.

### The Composite Score

```
importance = (difficulty × 0.4) + (novelty × 0.35) + (quality × 0.25)
```

Each component is scored 0.0–1.0:

- **Difficulty**: How hard is the question? Trivial questions (print "hello world") teach little. Complex multi-step problems with edge cases teach a lot.
- **Novelty**: How different is this pair from others in the dataset? Redundant pairs waste compute. Unique concepts add the most learning signal.
- **Quality**: How good is the answer? Clear, correct, well-structured answers are worth training on. Vague or wrong answers are harmful.

### Implementation

```python
import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
from openai import OpenAI

@dataclass
class ScoredPair:
    pair_id: str
    question: str
    answer: str
    difficulty: float
    novelty: float
    quality: float
    importance: float

def score_difficulty(client: OpenAI, question: str) -> float:
    """Score question difficulty using LLM."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # cheap model is fine for difficulty scoring
        messages=[{
            "role": "user",
            "content": f"""Rate the difficulty of this coding question from 0.0 to 1.0.
0.0 = trivial (print statement, basic syntax)
0.5 = moderate (standard algorithm, common pattern)
1.0 = expert (complex architecture, subtle edge cases)

Question: {question}

Respond with ONLY a decimal number."""
        }],
        temperature=0.0,
        max_tokens=10,
    )
    try:
        return float(response.choices[0].message.content.strip())
    except ValueError:
        return 0.5

def score_novelty(
    question: str,
    answer: str,
    existing_embeddings: list[list[float]],
    embed_fn,
) -> float:
    """Score novelty by distance from nearest existing pair."""
    import numpy as np

    pair_text = question + " " + answer[:500]
    embedding = embed_fn(pair_text)

    if not existing_embeddings:
        return 1.0

    # Cosine similarity with all existing pairs
    similarities = [
        np.dot(embedding, existing) /
        (np.linalg.norm(embedding) * np.linalg.norm(existing) + 1e-8)
        for existing in existing_embeddings
    ]
    max_similarity = max(similarities)

    # Convert similarity to novelty: high similarity = low novelty
    return max(0.0, 1.0 - max_similarity)

def score_quality(client: OpenAI, question: str, answer: str) -> float:
    """Score answer quality using LLM judge."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": f"""Rate the quality of this coding answer from 0.0 to 1.0.
Consider: correctness, clarity, completeness, code quality, explanation quality.
0.0 = wrong or harmful
0.5 = acceptable but has gaps
1.0 = excellent, comprehensive, production-quality

Question: {question}
Answer: {answer[:3000]}

Respond with ONLY a decimal number."""
        }],
        temperature=0.0,
        max_tokens=10,
    )
    try:
        return float(response.choices[0].message.content.strip())
    except ValueError:
        return 0.5

def score_dataset(
    jsonl_path: str,
    output_path: str,
    difficulty_weight: float = 0.4,
    novelty_weight: float = 0.35,
    quality_weight: float = 0.25,
) -> list[ScoredPair]:
    """Score all pairs in a dataset and write ranked output."""
    client = OpenAI()
    pairs = []

    with open(jsonl_path) as f:
        for line in f:
            data = json.loads(line)
            msgs = data["messages"]
            question = next(m["content"] for m in msgs if m["role"] == "user")
            answer = next(m["content"] for m in msgs if m["role"] == "assistant")
            pair_id = data.get("id", hashlib.md5(question.encode()).hexdigest()[:8])
            pairs.append((pair_id, question, answer))

    # Score all pairs
    embeddings = []
    scored = []
    for pair_id, question, answer in pairs:
        d = score_difficulty(client, question)
        n = score_novelty(question, answer, embeddings, get_embedding)
        q = score_quality(client, question, answer)
        importance = d * difficulty_weight + n * novelty_weight + q * quality_weight

        scored.append(ScoredPair(
            pair_id=pair_id, question=question, answer=answer,
            difficulty=d, novelty=n, quality=q, importance=importance,
        ))

        # Add embedding for future novelty comparisons
        embeddings.append(get_embedding(question + " " + answer[:500]))

    # Sort by importance (highest first)
    scored.sort(key=lambda s: s.importance, reverse=True)

    # Write ranked output
    with open(output_path, "w") as f:
        for s in scored:
            json.dump({
                "id": s.pair_id,
                "importance": round(s.importance, 3),
                "difficulty": round(s.difficulty, 2),
                "novelty": round(s.novelty, 2),
                "quality": round(s.quality, 2),
                "question": s.question[:100],
            }, f)
            f.write("\n")

    # Summary statistics
    top_20 = scored[:len(scored)//5]
    bottom_20 = scored[-len(scored)//5:]
    print(f"Top 20% avg importance: {sum(s.importance for s in top_20)/len(top_20):.3f}")
    print(f"Bottom 20% avg importance: {sum(s.importance for s in bottom_20)/len(bottom_20):.3f}")
    print(f"Recommendation: drop bottom {len(bottom_20)} pairs for faster training")

    return scored
```

### Practical Usage

After scoring, use the results to:

1. **Cut the bottom 10-20%** — Low-importance pairs are trivial, redundant, or low-quality. Removing them speeds up training with minimal quality loss.
2. **Oversample the top 10%** — High-importance pairs deserve extra emphasis. Use paraphrase augmentation (not exact duplication) to amplify their signal.
3. **Investigate medium-novelty, low-quality pairs** — These cover unique topics but have poor answers. Regenerating their answers with a stronger teacher model can be high-ROI.

### Cost Optimization

Scoring thousands of pairs with an LLM judge can be expensive. To reduce cost:
- Use `gpt-4o-mini` instead of `gpt-4o` for difficulty and quality scoring (good enough for 0-1 ratings)
- Batch the scoring calls using the OpenAI batch API (50% cost reduction)
- Cache scores in a SQLite database so you only score new pairs when your dataset changes'''
    ),

    # ===================== SOFTWARE ARCHITECTURE (8 pairs) =====================

    (
        "sys_know1_13",
        r'''How do I build a keyword-based routing system that matches user queries to relevant documentation and injects it into the system prompt at runtime?''',
        r'''<think>
The user wants a regex/keyword-based routing system for runtime context injection. This is the "skill injection" pattern — match user queries against keyword patterns, load relevant documentation, and inject it into the system prompt before the LLM processes the query. I should show a practical implementation with priority ordering (multiple matches get ranked) and a clean architecture.
</think>

## Regex-Based Routing for Runtime Context Injection

This pattern matches user queries against keyword patterns and injects relevant documentation into the system prompt before the LLM sees the query. It is a lightweight alternative to RAG that works well when you have a known set of topics.

### Architecture

```
User query: "How do I transfer HIVE tokens using Python?"
                    │
                    ▼
        ┌───────────────────┐
        │  Keyword Router   │  Match against pattern rules
        │  "hive" + "token" │  → hive_sdk skill (priority 1)
        │  "python"         │  → python_best skill (priority 2)
        └───────────────────┘
                    │
                    ▼
        ┌───────────────────┐
        │  Load top-N skill │  Read SKILL.md files for matches
        │  files by priority│  Inject into system prompt
        └───────────────────┘
                    │
                    ▼
        ┌───────────────────┐
        │ System prompt:    │
        │ [base prompt]     │
        │ [hive_sdk context]│  Injected skill content
        │ [python context]  │
        │                   │
        │ User: "How do I   │
        │ transfer HIVE..." │
        └───────────────────┘
```

### Implementation

```python
import re
import json
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class SkillRule:
    name: str
    patterns: list[str]           # regex patterns to match
    skill_file: str               # path to SKILL.md or context file
    priority: int = 10            # lower = higher priority
    max_inject_tokens: int = 800  # truncate if context is too long
    _compiled: list = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def matches(self, query: str) -> int:
        """Return number of pattern matches (0 = no match)."""
        return sum(1 for p in self._compiled if p.search(query))


class SkillRouter:
    """Keyword-based router that injects relevant context into system prompts."""

    def __init__(self, skills_dir: str = "skills"):
        self.rules: list[SkillRule] = []
        self.skills_dir = Path(skills_dir)
        self._load_skill_metadata()

    def _load_skill_metadata(self):
        """Load routing rules from skill_meta.json files."""
        for meta_path in self.skills_dir.glob("*/skill_meta.json"):
            meta = json.loads(meta_path.read_text())
            skill_dir = meta_path.parent

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            self.rules.append(SkillRule(
                name=meta["name"],
                patterns=meta.get("patterns", []),
                skill_file=str(skill_file),
                priority=meta.get("priority", 10),
                max_inject_tokens=meta.get("max_tokens", 800),
            ))

    def match(self, query: str, max_skills: int = 3) -> list[tuple[SkillRule, int]]:
        """Find matching skills for a query, sorted by relevance."""
        matches = []
        for rule in self.rules:
            hit_count = rule.matches(query)
            if hit_count > 0:
                matches.append((rule, hit_count))

        # Sort by: hit count (desc), then priority (asc)
        matches.sort(key=lambda x: (-x[1], x[0].priority))
        return matches[:max_skills]

    def build_system_prompt(
        self,
        base_prompt: str,
        query: str,
    ) -> str:
        """Build system prompt with injected skill context."""
        matches = self.match(query)

        if not matches:
            return base_prompt

        skill_sections = []
        for rule, hit_count in matches:
            content = Path(rule.skill_file).read_text(encoding="utf-8")
            # Rough token estimate: 1 token ≈ 4 chars
            max_chars = rule.max_inject_tokens * 4
            if len(content) > max_chars:
                content = content[:max_chars] + "\n[... truncated]"
            skill_sections.append(
                f"## Reference: {rule.name}\n{content}"
            )

        injected = "\n\n".join(skill_sections)
        return f"{base_prompt}\n\n---\n{injected}"


# Example skill_meta.json:
# {
#   "name": "Hive SDK",
#   "patterns": [
#     "\\bhive\\b", "\\bbeem\\b", "\\bhivesigner\\b",
#     "\\btransfer.*hive\\b", "\\bbroadcast.*operation\\b"
#   ],
#   "priority": 5,
#   "max_tokens": 600
# }

# Usage in a Flask app:
router = SkillRouter(skills_dir="skills")

@app.route("/chat", methods=["POST"])
def chat():
    query = request.json["message"]
    system_prompt = router.build_system_prompt(BASE_PROMPT, query)
    response = call_llm(system_prompt=system_prompt, user_message=query)
    return jsonify({"response": response})
```

### Priority Ordering

When multiple skills match, priority determines which ones get injected first (and thus are more likely to influence the response):

| Priority | When to use |
|----------|------------|
| 1-3 | Domain-critical skills (Hive blockchain, core product) |
| 4-6 | Language-specific skills (Python, TypeScript patterns) |
| 7-10 | General skills (architecture, best practices) |

### Advantages Over RAG

- **Deterministic**: Same query always gets the same skill injection. Easy to debug and test.
- **No vector database**: No embedding computation, no similarity search, no infrastructure.
- **Curated context**: SKILL.md files are hand-written to be concise and focused. RAG retrieval can pull in noisy, irrelevant chunks.
- **Fast**: Regex matching is sub-millisecond. No network calls to a vector store.

### When to Use RAG Instead

Use RAG when you have hundreds of documents, the topics cannot be enumerated in advance, or user queries are unpredictable. Keyword routing works for 5-50 known topics with clear keyword signals.'''
    ),

    (
        "sys_know1_14",
        r'''Our team project has hardcoded paths like C:\Users\dan\hiveai everywhere in the code. How do we make it portable so other team members can use it on their machines?''',
        r'''## Environment Portability: Replacing Hardcoded Paths

Hardcoded paths break whenever a different user or machine tries to run the code. The fix is a combination of **environment variables**, **sensible defaults**, and a **single config file** that resolves paths dynamically.

### Step 1: Replace Every Hardcoded Path with a Config Lookup

```python
# BAD — hardcoded, breaks on every other machine
MODEL_PATH = "C:/Users/dan/hiveai/Hive-AI/models/qwen2.5-coder-14b"
DATA_DIR = "/opt/hiveai/project/loras/training_data"

# GOOD — environment variable with sensible default
import os
from pathlib import Path

def get_project_root() -> Path:
    """Get project root from env var or auto-detect from this file's location."""
    env_root = os.environ.get("HIVEAI_ROOT")
    if env_root:
        return Path(env_root)
    # Auto-detect: assume this file is at <root>/hiveai/config.py
    return Path(__file__).resolve().parent.parent

PROJECT_ROOT = get_project_root()
MODEL_PATH = PROJECT_ROOT / "models" / "qwen2.5-coder-14b"
DATA_DIR = PROJECT_ROOT / "loras" / "training_data"
LOGS_DIR = PROJECT_ROOT / "logs"
```

### Step 2: Create a Config Module

Centralize all path resolution in one place:

```python
# hiveai/config.py
import os
from pathlib import Path

def _env_path(var: str, default: str) -> Path:
    """Read path from env var, fall back to default relative to project root."""
    val = os.environ.get(var)
    if val:
        return Path(val)
    return PROJECT_ROOT / default

PROJECT_ROOT = get_project_root()

# All configurable paths in one place
MODELS_DIR = _env_path("HIVEAI_MODELS", "models")
TRAINING_DATA = _env_path("HIVEAI_DATA", "loras/training_data")
SKILLS_DIR = _env_path("HIVEAI_SKILLS", "skills")
EVAL_CHALLENGES = _env_path("HIVEAI_EVAL", "scripts/eval_challenges.json")
LOG_DIR = _env_path("HIVEAI_LOGS", "logs")

# Server config (not paths, but also should not be hardcoded)
LLM_HOST = os.environ.get("HIVEAI_LLM_HOST", "127.0.0.1")
LLM_PORT = int(os.environ.get("HIVEAI_LLM_PORT", "8080"))
```

### Step 3: Use the Config Everywhere

```python
# In training scripts
from hiveai.config import TRAINING_DATA, MODELS_DIR

data_path = TRAINING_DATA / "v5.jsonl"
output_dir = MODELS_DIR / "lora_v5"

# In the Flask app
from hiveai.config import SKILLS_DIR, LLM_HOST, LLM_PORT

router = SkillRouter(skills_dir=SKILLS_DIR)
```

### Step 4: Document for Team Members

Create a `.env.example` file (committed to git) that shows what can be configured:

```bash
# .env.example — copy to .env and customize for your machine
# All paths are optional — defaults work if you keep the standard directory layout

# Project root (auto-detected if not set)
# HIVEAI_ROOT=C:/Users/yourname/hiveai/Hive-AI

# Override specific directories
# HIVEAI_MODELS=/mnt/fast_ssd/models
# HIVEAI_DATA=/mnt/fast_ssd/training_data

# Server config
# HIVEAI_LLM_HOST=127.0.0.1
# HIVEAI_LLM_PORT=8080
```

And add `.env` to `.gitignore` so personal configs do not get committed.

### Finding Hardcoded Paths in Your Codebase

```bash
# Search for hardcoded absolute paths (Windows)
grep -rn "C:\\\\Users\\|C:/Users/" scripts/ hiveai/ --include="*.py"

# Search for hardcoded absolute paths (Linux)
grep -rn "/home/\|/opt/hiveai" scripts/ hiveai/ --include="*.py"

# These should ALL be replaced with config lookups
```

### The Rule

The only place a machine-specific path should ever appear is in a `.env` file that is gitignored. Every Python file should use `hiveai.config` for path resolution. If a new team member clones the repo and runs the code without setting any environment variables, it should still work using sensible defaults.'''
    ),

    (
        "sys_know1_15",
        r'''How do I set up a Flask app with background workers for tasks like embedding warmup and periodic health checks?''',
        r'''<think>
The user wants a Flask app with background workers. Key aspects: non-blocking startup (don't delay the Flask server while warming up), periodic tasks (health checks, cache refresh), and proper thread management. I should show a practical pattern using threading for background workers with graceful shutdown.
</think>

## Flask App with Background Workers

Flask's WSGI server is synchronous by default, so long-running tasks (embedding warmup, periodic checks) need to run in background threads. Here is a clean pattern.

### Architecture

```
Flask Process
├── Main Thread (WSGI — handles HTTP requests)
├── Worker Thread 1: Embedding warmup (runs once at startup)
├── Worker Thread 2: Periodic health check (runs every 60s)
└── Worker Thread 3: Cache refresh (runs every 300s)
```

### Implementation

```python
import threading
import time
import logging
import signal
import sys
from flask import Flask, jsonify, request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class BackgroundWorker:
    """A periodic background task runner."""
    name: str
    target: callable
    interval_seconds: float  # 0 = run once then stop
    _thread: threading.Thread = field(default=None, init=False, repr=False)
    _stop_event: threading.Event = field(
        default_factory=threading.Event, init=False, repr=False
    )

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name=f"worker-{self.name}", daemon=True
        )
        self._thread.start()
        logger.info(f"Started background worker: {self.name}")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

    def _run(self):
        try:
            self.target()  # Run immediately on start
            if self.interval_seconds <= 0:
                logger.info(f"Worker {self.name} completed (one-shot)")
                return
            while not self._stop_event.is_set():
                self._stop_event.wait(self.interval_seconds)
                if not self._stop_event.is_set():
                    self.target()
        except Exception as e:
            logger.error(f"Worker {self.name} crashed: {e}", exc_info=True)


class AppState:
    """Shared application state, thread-safe."""
    def __init__(self):
        self._lock = threading.Lock()
        self.embeddings_ready = False
        self.health_status = {"llm": "unknown", "disk": "unknown"}
        self.skill_cache = {}

    def set_embeddings_ready(self):
        with self._lock:
            self.embeddings_ready = True

    def update_health(self, component: str, status: str):
        with self._lock:
            self.health_status[component] = status


def create_app() -> Flask:
    app = Flask(__name__)
    state = AppState()
    workers = []

    # === Background Tasks ===

    def warmup_embeddings():
        """Load embedding model into memory. Runs once at startup."""
        logger.info("Warming up embedding model...")
        # Simulate slow model loading
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        # Warm up with a dummy encode
        model.encode(["warmup"])
        state.set_embeddings_ready()
        logger.info("Embedding model ready")

    def health_check():
        """Periodic health check for dependencies."""
        import urllib.request
        # Check LLM server
        try:
            req = urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=5)
            state.update_health("llm", "healthy" if req.status == 200 else "degraded")
        except Exception:
            state.update_health("llm", "unreachable")

        # Check disk space
        import shutil
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024**3)
        state.update_health("disk", "healthy" if free_gb > 5 else "low")

    def refresh_skill_cache():
        """Reload skill files from disk periodically."""
        from pathlib import Path
        for skill_path in Path("skills").glob("*/SKILL.md"):
            state.skill_cache[skill_path.parent.name] = skill_path.read_text()
        logger.info(f"Refreshed {len(state.skill_cache)} skills")

    # === Register Workers ===
    workers.append(BackgroundWorker("embeddings", warmup_embeddings, interval_seconds=0))
    workers.append(BackgroundWorker("health", health_check, interval_seconds=60))
    workers.append(BackgroundWorker("skills", refresh_skill_cache, interval_seconds=300))

    # === Routes ===

    @app.route("/health")
    def health():
        return jsonify({
            "status": "ok",
            "embeddings_ready": state.embeddings_ready,
            "dependencies": state.health_status,
        })

    @app.route("/chat", methods=["POST"])
    def chat():
        if not state.embeddings_ready:
            return jsonify({"error": "Service warming up, try again shortly"}), 503
        query = request.json.get("message", "")
        # ... process query using state.skill_cache, embeddings, etc.
        return jsonify({"response": "..."})

    # === Lifecycle ===

    @app.before_request
    def _first_request_check():
        # Start workers on first request (avoids double-start with Flask reloader)
        if not hasattr(app, '_workers_started'):
            for w in workers:
                w.start()
            app._workers_started = True

    def shutdown():
        logger.info("Shutting down background workers...")
        for w in workers:
            w.stop()

    # Register shutdown for clean exit
    import atexit
    atexit.register(shutdown)

    return app

# Run: flask run, or gunicorn "app:create_app()"
app = create_app()
```

### Key Design Decisions

1. **Daemon threads**: Set `daemon=True` so workers die when the main process exits. No zombie threads.
2. **Stop event**: Use `threading.Event` for clean shutdown instead of killing threads.
3. **Shared state with locks**: `AppState` uses a lock for thread-safe updates. Flask request handlers run in the main thread (or WSGI worker threads), so they need synchronized access to state modified by background workers.
4. **503 during warmup**: Return HTTP 503 (Service Unavailable) while embeddings are loading instead of crashing or returning bad results.
5. **Interval=0 for one-shot tasks**: Embedding warmup runs once and stops. Health checks run on a loop.

### Production Note

For production, consider using Celery or APScheduler instead of raw threads. They provide retry logic, task queuing, and monitoring. The thread-based approach shown here is appropriate for lightweight background tasks in a single-process deployment.'''
    ),

    (
        "sys_know1_16",
        r'''When should I use RAG (vector retrieval) versus keyword-matched skill files for augmenting LLM responses? Can I combine both?''',
        r'''## RAG vs Skill Injection: When to Use Each

Both RAG and skill injection solve the same core problem — giving the LLM relevant context it was not trained on. They have different strengths and are complementary.

### Comparison

| Dimension | Keyword Skill Injection | RAG (Vector Retrieval) |
|-----------|------------------------|----------------------|
| **Setup complexity** | Low — regex patterns + markdown files | High — embedding model, vector DB, chunking pipeline |
| **Query matching** | Exact keyword/pattern match | Semantic similarity (catches paraphrases) |
| **Context quality** | High — hand-curated, concise | Variable — depends on chunking and retrieval quality |
| **Number of topics** | Best for 5-50 known topics | Scales to thousands of documents |
| **Latency** | Sub-millisecond | 50-200ms (embedding + search) |
| **Maintenance** | Manual — edit SKILL.md files | Semi-automatic — re-embed when docs change |
| **Failure mode** | Silent miss (no match = no context) | Noisy retrieval (wrong chunks injected) |

### Decision Framework

**Use keyword skill injection when:**
- You have a small, known set of topics (blockchain operations, language best practices)
- The topics have clear keyword signals ("hive", "transfer", "broadcast")
- You need deterministic, testable behavior
- Context must be high-quality and concise (<800 tokens per skill)
- Latency matters (real-time chat)

**Use RAG when:**
- You have a large document corpus (API docs, codebase, knowledge base)
- User queries are unpredictable and do not match clean keyword patterns
- Semantic understanding matters ("how to send money" should match "transfer tokens")
- Documents change frequently (RAG re-embedding is easier than rewriting skill files)

### The Hybrid Pattern

Use both — skill injection as the **first pass** (fast, precise, high-quality) and RAG as a **fallback** for queries that do not match any skill pattern.

```python
class HybridContextRouter:
    def __init__(self, skill_router, rag_engine):
        self.skill_router = skill_router
        self.rag_engine = rag_engine

    def get_context(self, query: str, max_tokens: int = 1500) -> str:
        """Get relevant context using skills first, RAG as fallback."""
        # Try skill injection first
        skill_matches = self.skill_router.match(query)

        if skill_matches:
            # Skill match found — use curated context
            contexts = []
            tokens_used = 0
            for rule, _ in skill_matches:
                content = load_skill(rule.skill_file)
                tokens_used += estimate_tokens(content)
                if tokens_used > max_tokens:
                    break
                contexts.append(content)
            return "\n\n".join(contexts)

        # No skill match — fall back to RAG
        chunks = self.rag_engine.retrieve(query, top_k=3)
        return "\n\n".join(c.text for c in chunks)

    def get_context_combined(self, query: str, max_tokens: int = 2000) -> str:
        """Use both skill injection AND RAG together."""
        parts = []
        tokens_remaining = max_tokens

        # Skills first (higher quality, higher priority)
        skill_matches = self.skill_router.match(query, max_skills=2)
        for rule, _ in skill_matches:
            content = load_skill(rule.skill_file)
            tokens = estimate_tokens(content)
            if tokens <= tokens_remaining:
                parts.append(f"## {rule.name}\n{content}")
                tokens_remaining -= tokens

        # Fill remaining budget with RAG
        if tokens_remaining > 200:
            chunks = self.rag_engine.retrieve(query, top_k=3)
            for chunk in chunks:
                tokens = estimate_tokens(chunk.text)
                if tokens <= tokens_remaining:
                    parts.append(chunk.text)
                    tokens_remaining -= tokens

        return "\n\n---\n\n".join(parts)
```

### Practical Recommendation

Start with skill injection. It is simpler, faster, and produces higher-quality context. Add RAG only when you outgrow what keyword matching can handle — typically when you have more than 30-50 distinct topics or when user queries are too diverse for keyword patterns to capture.'''
    ),

    (
        "sys_know1_17",
        r'''How should I design eval challenges for a code-generating LLM? I want to test across languages and difficulty levels with expected-keyword scoring.''',
        r'''<think>
The user wants to design an eval challenge set. Key considerations: multi-language coverage, difficulty tiers, keyword-based scoring (checking for expected patterns/functions in output), and making it extensible. I should show the data structure, scoring logic, and example challenges.
</think>

## Eval Challenge Design for Code-Generating LLMs

A good eval challenge set tests the model across languages, difficulty levels, and task types, using **expected keyword scoring** as a fast, deterministic quality signal.

### Challenge Data Structure

```json
{
  "id": "py_async_001",
  "category": "python",
  "difficulty": 2,
  "prompt": "Write a Python function that fetches multiple URLs concurrently using asyncio and aiohttp. Handle timeouts and return results as a dict mapping URL to response text or error message.",
  "expected_keywords": ["async def", "aiohttp", "asyncio.gather", "timeout", "ClientSession"],
  "expected_any": ["try:", "except"],
  "anti_keywords": ["requests.get"],
  "language": "python",
  "max_score": 5
}
```

### Field Definitions

| Field | Purpose |
|-------|---------|
| `expected_keywords` | ALL must appear in the response. Each present keyword scores points. |
| `expected_any` | At least ONE must appear. Tests that the concept is addressed without requiring exact syntax. |
| `anti_keywords` | If ANY appear, deduct points. Catches common mistakes (e.g., using sync `requests` for an async question). |
| `difficulty` | 1 = basic, 2 = intermediate, 3 = advanced. Weight scoring by difficulty. |
| `language` | For multi-language coverage tracking. |

### Scoring Implementation

```python
import json
import re
from dataclasses import dataclass

@dataclass
class ChallengeResult:
    challenge_id: str
    score: float        # 0.0 - 1.0
    max_score: float
    matched_keywords: list[str]
    missing_keywords: list[str]
    anti_matches: list[str]

def score_response(challenge: dict, response: str) -> ChallengeResult:
    """Score a model response against challenge criteria."""
    response_lower = response.lower()
    score = 0
    max_score = 0
    matched = []
    missing = []

    # Expected keywords: each one is worth 1 point
    for kw in challenge.get("expected_keywords", []):
        max_score += 1
        if kw.lower() in response_lower:
            score += 1
            matched.append(kw)
        else:
            missing.append(kw)

    # Expected any: worth 1 point if at least one matches
    any_keywords = challenge.get("expected_any", [])
    if any_keywords:
        max_score += 1
        if any(kw.lower() in response_lower for kw in any_keywords):
            score += 1
            matched.append(f"ANY({any_keywords})")
        else:
            missing.append(f"ANY({any_keywords})")

    # Anti-keywords: deduct 1 point per match
    anti_matches = []
    for kw in challenge.get("anti_keywords", []):
        if kw.lower() in response_lower:
            score -= 1
            anti_matches.append(kw)

    normalized = max(0.0, score / max_score) if max_score > 0 else 0.0

    return ChallengeResult(
        challenge_id=challenge["id"],
        score=normalized,
        max_score=max_score,
        matched_keywords=matched,
        missing_keywords=missing,
        anti_matches=anti_matches,
    )

def run_eval(
    challenges_path: str,
    model_fn,  # callable: prompt → response
) -> dict:
    """Run full eval suite and report per-category scores."""
    with open(challenges_path) as f:
        challenges = json.load(f)

    results_by_category = {}
    results_by_difficulty = {1: [], 2: [], 3: []}

    for ch in challenges:
        response = model_fn(ch["prompt"])
        result = score_response(ch, response)

        cat = ch.get("category", "unknown")
        results_by_category.setdefault(cat, []).append(result)
        results_by_difficulty[ch.get("difficulty", 2)].append(result)

    # Summary
    print("\n=== Per-Category Scores ===")
    for cat, results in sorted(results_by_category.items()):
        avg = sum(r.score for r in results) / len(results)
        print(f"  {cat}: {avg:.3f} ({len(results)} challenges)")

    print("\n=== Per-Difficulty Scores ===")
    for diff, results in sorted(results_by_difficulty.items()):
        if results:
            avg = sum(r.score for r in results) / len(results)
            print(f"  Difficulty {diff}: {avg:.3f} ({len(results)} challenges)")

    overall = sum(r.score for rs in results_by_category.values() for r in rs)
    total = sum(len(rs) for rs in results_by_category.values())
    print(f"\nOverall: {overall/total:.3f}")

    return results_by_category
```

### Example Challenges Across Languages

```json
[
  {
    "id": "py_basic_001",
    "category": "python",
    "difficulty": 1,
    "prompt": "Write a Python function that reverses a string without using slicing or built-in reverse.",
    "expected_keywords": ["def ", "return"],
    "expected_any": ["for ", "while "],
    "anti_keywords": ["[::-1]", ".reverse()"],
    "language": "python"
  },
  {
    "id": "js_mid_001",
    "category": "javascript",
    "difficulty": 2,
    "prompt": "Implement a TypeScript generic function that deep-merges two objects, with the second object's values taking precedence.",
    "expected_keywords": ["function", "typeof", "object"],
    "expected_any": ["<T", "generic", "Record<"],
    "anti_keywords": [],
    "language": "typescript"
  },
  {
    "id": "go_adv_001",
    "category": "go",
    "difficulty": 3,
    "prompt": "Write a Go function that implements a concurrent-safe LRU cache using sync.Mutex and a doubly-linked list.",
    "expected_keywords": ["sync.Mutex", "func ", "Lock()", "Unlock()"],
    "expected_any": ["container/list", "doubly"],
    "anti_keywords": [],
    "language": "go"
  }
]
```

### Design Tips

1. **Aim for 5-8 challenges per category** — enough to be statistically meaningful, few enough to run quickly
2. **Balance difficulty**: ~30% easy, ~50% medium, ~20% hard
3. **Keep keywords specific**: "async def" is better than "async" (too generic). "asyncio.gather" is better than "gather" (could appear in unrelated context)
4. **Test understanding too**: Not every challenge should be "write code." Include "explain why X happens" and "what's wrong with this code?" challenges
5. **Version your challenge file**: Never modify existing challenges (breaks score comparisons). Add new ones with new IDs.'''
    ),

    (
        "sys_know1_18",
        r'''What's a good git workflow for ML projects where the team has large JSONL training data files, frequent training experiments, and multiple people pushing to the same repo?''',
        r'''## Git Workflow for ML Projects

ML projects have unique git challenges: large data files, frequent experiments, and training artifacts that should not be committed. Here is a practical workflow.

### Gitignore Essentials

```gitignore
# Training data (build artifacts — regenerated from batch files)
loras/training_data/*.jsonl

# Model outputs and checkpoints
loras/*/checkpoint-*
loras/*/runs/
*.gguf
*.safetensors

# Training logs (keep summaries, ignore verbose logs)
logs/*.log
wandb/

# Caches
__pycache__/
.cache/
*.pyc

# Environment-specific
.env
*.vhdx

# OS junk
.DS_Store
Thumbs.db
```

### The Key Principle: Source vs Artifact

**Commit** (source of truth):
- Batch files (`scripts/distill_batches/batch_p*.py`) — small, diffable Python
- Training scripts and configs
- Eval challenge definitions
- Skill files

**Gitignore** (regenerable artifacts):
- `v5.jsonl` — built from batch files by `prepare_v5_data.py --export`
- Model checkpoints — rebuilt by training
- Eval result logs — rebuilt by running eval

This keeps the repo manageable (batch files are ~5KB each vs a 50MB JSONL).

### Branch Strategy

```
main ─────────────────────────────────────────────
  │          │                │
  │  feature/go-pairs    feature/hive-security
  │  (Alice adds Go      (Bob adds Hive
  │   training data)      security pairs)
  │          │                │
  │          └───── merge ────┘
  │                   │
  │           main ───┘
```

**Rules:**
1. **Always pull before starting work**: `git pull --rebase origin main`
2. **Feature branches for data additions**: `feature/go-training-data`, `feature/eval-v3`
3. **Rebase, don't merge** for linear history: `git pull --rebase` instead of merge commits
4. **Small, focused commits**: One batch file per commit, or one logical change per commit

### Avoiding Conflicts

The batch file pattern almost eliminates merge conflicts because each contributor works in a separate file:

```
Alice: scripts/distill_batches/batch_p1050_go_basics.py     # new file
Bob:   scripts/distill_batches/batch_p1051_hive_security.py  # new file
```

New files cannot conflict. The only shared files that might conflict are:
- Training scripts (rare changes)
- Eval challenges JSON (use append-only: add new challenges at the end)

### Handling Large Files

If you must track large files (pre-trained model weights, large datasets):

```bash
# Option 1: Git LFS (if your host supports it)
git lfs install
git lfs track "*.gguf"
git lfs track "loras/training_data/v5.jsonl"

# Option 2: Store outside git, document location
# Keep a MODELS.md with download links / shared drive paths
```

For this project's approach, the JSONL is gitignored and rebuilt from batch files, so LFS is not needed for training data.

### Team Coordination Checklist

```bash
# Before starting work:
git pull --rebase origin main

# After adding a batch file:
git add scripts/distill_batches/batch_p1050_new_topic.py
git commit -m "Add 25 Go concurrency training pairs"

# Before pushing:
git pull --rebase origin main   # get any changes from teammates
# Resolve conflicts if any (rare with batch file pattern)
git push origin main
```

### Numbering Convention

Use sequential numbering for batch files (`batch_p0001` through `batch_p9999`). Leave gaps for concurrent work — if Alice is working on p1050-p1055 and Bob on p1060-p1065, they will not collide. Communicate your number range on the team chat before starting a large batch of files.'''
    ),

    (
        "sys_know1_19",
        r'''How can I use SQLite to support a training data pipeline — specifically for dedup caching, training pair tracking, and quality score persistence?''',
        r'''<think>
The user wants to use SQLite as a lightweight database for training data management. Good use cases: dedup cache (check if a question/answer already exists), tracking metadata about each pair (when added, which batch, scores), and persisting quality scores from LLM judges. SQLite is perfect here because it's serverless, single-file, and handles concurrent reads well.
</think>

## Database-Backed Knowledge Mining with SQLite

SQLite is ideal for training data pipelines because it is serverless (just a file), supports concurrent reads, and persists between runs without any infrastructure.

### Schema Design

```python
import sqlite3
import hashlib
import json
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = "data/training_pipeline.db"

def init_db(db_path: str = DB_PATH):
    """Create tables for training data management."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        -- Training pairs with dedup support
        CREATE TABLE IF NOT EXISTS pairs (
            pair_id TEXT PRIMARY KEY,
            question_hash TEXT NOT NULL,
            answer_hash TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            source_batch TEXT,           -- e.g., "batch_p1050_go_basics"
            category TEXT,               -- e.g., "python", "go", "hive"
            has_thinking INTEGER DEFAULT 0,  -- 1 if answer has <think> tags
            char_count INTEGER,
            created_at REAL,
            UNIQUE(question_hash, answer_hash)  -- dedup constraint
        );

        -- Quality scores from LLM judges
        CREATE TABLE IF NOT EXISTS quality_scores (
            pair_id TEXT NOT NULL,
            scorer TEXT NOT NULL,         -- e.g., "gpt-4o", "manual"
            code_validity REAL,
            test_passing REAL,
            concept_coverage REAL,
            explanation_quality REAL,
            composite REAL,
            scored_at REAL,
            FOREIGN KEY (pair_id) REFERENCES pairs(pair_id),
            UNIQUE(pair_id, scorer)       -- one score per scorer per pair
        );

        -- Training run tracking
        CREATE TABLE IF NOT EXISTS training_runs (
            run_id TEXT PRIMARY KEY,
            started_at REAL,
            finished_at REAL,
            pairs_used INTEGER,
            epochs INTEGER,
            final_loss REAL,
            eval_score REAL,
            config_json TEXT,             -- full training config
            notes TEXT
        );

        -- Indexes for fast lookups
        CREATE INDEX IF NOT EXISTS idx_pairs_category ON pairs(category);
        CREATE INDEX IF NOT EXISTS idx_pairs_question_hash ON pairs(question_hash);
        CREATE INDEX IF NOT EXISTS idx_scores_composite ON quality_scores(composite);
    """)
    conn.close()

@contextmanager
def get_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
```

### Dedup Cache

```python
def content_hash(text: str) -> str:
    """Hash text content for dedup. Normalizes whitespace."""
    normalized = " ".join(text.split()).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]

def is_duplicate(conn: sqlite3.Connection, question: str, answer: str) -> bool:
    """Check if a question-answer pair already exists."""
    q_hash = content_hash(question)
    a_hash = content_hash(answer)
    row = conn.execute(
        "SELECT pair_id FROM pairs WHERE question_hash = ? AND answer_hash = ?",
        (q_hash, a_hash)
    ).fetchone()
    return row is not None

def is_question_duplicate(conn: sqlite3.Connection, question: str) -> bool:
    """Check if the QUESTION already exists (even with different answer)."""
    q_hash = content_hash(question)
    row = conn.execute(
        "SELECT pair_id FROM pairs WHERE question_hash = ?", (q_hash,)
    ).fetchone()
    return row is not None

def insert_pair(
    conn: sqlite3.Connection,
    pair_id: str,
    question: str,
    answer: str,
    source_batch: str,
    category: str = "unknown",
) -> bool:
    """Insert a pair, returning False if it's a duplicate."""
    q_hash = content_hash(question)
    a_hash = content_hash(answer)
    has_thinking = 1 if "<think>" in answer else 0

    try:
        conn.execute(
            """INSERT INTO pairs
               (pair_id, question_hash, answer_hash, question, answer,
                source_batch, category, has_thinking, char_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pair_id, q_hash, a_hash, question, answer,
             source_batch, category, has_thinking, len(answer), time.time())
        )
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate
```

### Quality Score Persistence

```python
def save_quality_score(
    conn: sqlite3.Connection,
    pair_id: str,
    scorer: str,
    scores: dict[str, float],
):
    """Save or update quality scores for a pair."""
    composite = (
        scores.get("code_validity", 0) * 0.35 +
        scores.get("test_passing", 0) * 0.25 +
        scores.get("concept_coverage", 0) * 0.25 +
        scores.get("explanation_quality", 0) * 0.15
    )
    conn.execute(
        """INSERT OR REPLACE INTO quality_scores
           (pair_id, scorer, code_validity, test_passing,
            concept_coverage, explanation_quality, composite, scored_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (pair_id, scorer,
         scores.get("code_validity"), scores.get("test_passing"),
         scores.get("concept_coverage"), scores.get("explanation_quality"),
         composite, time.time())
    )

def get_lowest_quality_pairs(
    conn: sqlite3.Connection,
    category: str = None,
    limit: int = 50,
) -> list[dict]:
    """Find pairs with lowest quality scores — candidates for replacement."""
    query = """
        SELECT p.pair_id, p.question, p.category, q.composite
        FROM pairs p
        JOIN quality_scores q ON p.pair_id = q.pair_id
    """
    params = []
    if category:
        query += " WHERE p.category = ?"
        params.append(category)
    query += " ORDER BY q.composite ASC LIMIT ?"
    params.append(limit)

    return [dict(row) for row in conn.execute(query, params).fetchall()]
```

### Pipeline Statistics

```python
def print_pipeline_stats(db_path: str = DB_PATH):
    """Print summary of the training data pipeline."""
    with get_db(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]
        by_cat = conn.execute(
            "SELECT category, COUNT(*) FROM pairs GROUP BY category ORDER BY COUNT(*) DESC"
        ).fetchall()
        thinking = conn.execute(
            "SELECT COUNT(*) FROM pairs WHERE has_thinking = 1"
        ).fetchone()[0]
        scored = conn.execute(
            "SELECT COUNT(DISTINCT pair_id) FROM quality_scores"
        ).fetchone()[0]
        avg_quality = conn.execute(
            "SELECT AVG(composite) FROM quality_scores"
        ).fetchone()[0]

        print(f"Total pairs: {total}")
        print(f"With <think> tags: {thinking} ({thinking/total*100:.0f}%)")
        print(f"Scored pairs: {scored}/{total}")
        if avg_quality:
            print(f"Average quality: {avg_quality:.2f}/5.0")
        print("\nPer-category:")
        for row in by_cat:
            print(f"  {row[0]}: {row[1]}")
```

### Why SQLite Over Files

- **Atomic dedup**: The `UNIQUE` constraint prevents duplicates at the database level — no race conditions
- **Fast lookups**: Hash-indexed dedup check takes microseconds vs scanning a JSONL file
- **Persistent scores**: Quality scores survive across pipeline runs without re-computing
- **SQL queries**: Finding "lowest quality Python pairs" or "all pairs from batch_p1050" is a one-liner
- **Single file**: Copy `training_pipeline.db` to another machine and you have the full state'''
    ),

    (
        "sys_know1_20",
        r'''How do I set up config-driven training where hyperparameters are externalized and training metadata is saved for reproducibility?''',
        r'''## Config-Driven Training for Reproducibility

Externalizing hyperparameters into config files and saving full training metadata makes every training run reproducible, comparable, and debuggable.

### Config File Structure (YAML)

```yaml
# configs/train_v8.yaml
model:
  base: "Qwen/Qwen2.5-Coder-14B-Instruct"
  load_in_4bit: true
  compute_dtype: "bfloat16"

lora:
  r: 16
  alpha: 32
  dropout: 0.1
  target_modules: ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
  use_rslora: true

training:
  epochs: 2
  batch_size: 1
  gradient_accumulation: 8
  learning_rate: 2e-4
  warmup_ratio: 0.05
  max_seq_length: 4096
  optimizer: "adamw_8bit"
  gradient_checkpointing: true
  max_grad_norm: 0.3

data:
  path: "loras/training_data/v8.jsonl"
  val_split: 0.05
  max_response_len: 15000
  hive_oversample: 2.0

regularization:
  kl_lambda: 0.3
  kl_temp: 1.0
  kl_seq_limit: 512
  neftune_alpha: 5.0

output:
  dir: "loras/v8_run1"
  save_strategy: "epoch"
```

### Loading Config in Training Script

```python
import yaml
import json
import time
import hashlib
import platform
from pathlib import Path
from dataclasses import dataclass, asdict

def load_config(config_path: str) -> dict:
    """Load training config from YAML file."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Validate required fields
    required = ["model.base", "lora.r", "training.epochs", "data.path"]
    for key in required:
        parts = key.split(".")
        obj = config
        for part in parts:
            if part not in obj:
                raise ValueError(f"Missing required config key: {key}")
            obj = obj[part]

    return config

def config_hash(config: dict) -> str:
    """Deterministic hash of config for tracking."""
    serialized = json.dumps(config, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:12]
```

### Saving Training Metadata

After every training run, save a `training_meta.json` alongside the model:

```python
import torch
import subprocess

def save_training_meta(
    config: dict,
    output_dir: str,
    train_dataset_size: int,
    val_dataset_size: int,
    final_train_loss: float,
    final_val_loss: float = None,
    eval_score: float = None,
    extra: dict = None,
):
    """Save complete training metadata for reproducibility."""
    meta = {
        "config": config,
        "config_hash": config_hash(config),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": {
            "train_size": train_dataset_size,
            "val_size": val_dataset_size,
            "path": config["data"]["path"],
        },
        "results": {
            "final_train_loss": final_train_loss,
            "final_val_loss": final_val_loss,
            "eval_score": eval_score,
        },
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda if torch.cuda.is_available() else None,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "gpu_memory_gb": round(
                torch.cuda.get_device_properties(0).total_mem / 1024**3, 1
            ) if torch.cuda.is_available() else None,
        },
        "git": {
            "commit": _git_commit_hash(),
            "branch": _git_branch(),
            "dirty": _git_is_dirty(),
        },
    }

    if extra:
        meta["extra"] = extra

    output_path = Path(output_dir) / "training_meta.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Training metadata saved to {output_path}")
    return meta

def _git_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"

def _git_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "branch", "--show-current"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"

def _git_is_dirty() -> bool:
    try:
        result = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
        ).decode().strip()
        return len(result) > 0
    except Exception:
        return True
```

### Using Config in the Training Script

```python
# scripts/train_v5.py
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument("--override", nargs="*", help="Override config: key=value")
    args = parser.parse_args()

    config = load_config(args.config)

    # Allow CLI overrides: --override training.epochs=3 lora.r=32
    if args.override:
        for item in args.override:
            key, value = item.split("=", 1)
            parts = key.split(".")
            obj = config
            for part in parts[:-1]:
                obj = obj[part]
            # Auto-cast types
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
            obj[parts[-1]] = value

    # Use config values
    model = load_model(
        config["model"]["base"],
        load_in_4bit=config["model"]["load_in_4bit"],
    )
    # ... rest of training setup using config dict

    # After training, save metadata
    save_training_meta(
        config=config,
        output_dir=config["output"]["dir"],
        train_dataset_size=len(train_dataset),
        val_dataset_size=len(val_dataset),
        final_train_loss=trainer.state.log_history[-1]["loss"],
    )

# Usage:
# python scripts/train_v5.py --config configs/train_v8.yaml
# python scripts/train_v5.py --config configs/train_v8.yaml --override training.epochs=3
```

### Why This Matters

When you come back to a training run three months later and ask "what exact config produced this model?", `training_meta.json` has the complete answer: config, dataset size, git commit, GPU type, library versions, and final metrics. Without this, reproducing or debugging old runs is nearly impossible.'''
    ),

    # ===================== CONCISE/QUICK ANSWERS (5 pairs, no think tags) =====================

    (
        "sys_know1_21",
        r'''What's the difference between LoRA merge and LoRA serving?''',
        r'''**LoRA merge** bakes the adapter weights into the base model permanently (`model.merge_and_unload()`). You get a single model file with zero inference overhead, but you cannot easily swap adapters.

**LoRA serving** keeps the adapter separate and applies it at runtime. This lets you hot-swap adapters (e.g., different LoRAs for different users) without reloading the base model, but adds ~1-3% inference latency from the adapter forward pass.

Use merge for production deployment with a single adapter. Use serving when you need to switch between multiple adapters dynamically.'''
    ),

    (
        "sys_know1_22",
        r'''How do I check if my training data has duplicates?''',
        r'''Quick check using question content hashing:

```python
import json
from collections import Counter

questions = []
with open("training_data.jsonl") as f:
    for line in f:
        msgs = json.loads(line)["messages"]
        q = next(m["content"] for m in msgs if m["role"] == "user")
        questions.append(q.strip().lower())

dupes = {q: n for q, n in Counter(questions).items() if n > 1}
print(f"{len(dupes)} duplicated questions out of {len(questions)} total")
for q, n in sorted(dupes.items(), key=lambda x: -x[1])[:10]:
    print(f"  [{n}x] {q[:80]}")
```

This catches exact duplicates. For near-duplicates (rephrased questions), compute embeddings and flag pairs with cosine similarity > 0.95.'''
    ),

    (
        "sys_know1_23",
        r'''What's a good warmup ratio for LoRA fine-tuning?''',
        r'''**0.03 to 0.10** is the typical range. A warmup ratio of 0.05 (5% of total steps) is a safe default for most LoRA fine-tuning jobs.

Warmup gradually increases the learning rate from 0 to prevent large, destabilizing gradient updates early in training when the model has not yet adapted to the new data distribution. Lower warmup (0.03) is fine for large datasets. Higher warmup (0.10) helps with small datasets or high learning rates where early instability is more likely.'''
    ),

    (
        "sys_know1_24",
        r'''How do I resume training from a checkpoint with HuggingFace Trainer?''',
        r'''Pass the checkpoint directory to `train()`:

```python
trainer.train(resume_from_checkpoint="output_dir/checkpoint-500")
```

Or to auto-detect the latest checkpoint in the output directory:

```python
trainer.train(resume_from_checkpoint=True)
```

This restores model weights, optimizer state, learning rate scheduler, and the RNG state. The training will continue from where it left off, including the correct step count and epoch number.'''
    ),

    (
        "sys_know1_25",
        r'''What's packing in SFT training?''',
        r'''Packing concatenates multiple short training examples into a single sequence (up to `max_seq_length`) separated by EOS tokens, instead of padding each example individually. This eliminates wasted compute on padding tokens and can speed up training 2-3x for datasets with many short examples.

**Do NOT use packing** when you use response-only loss masking (`DataCollatorForCompletionOnlyLM`), because the collator cannot correctly identify which parts of a packed sequence are prompts vs responses when multiple examples are concatenated. Use packing only with standard causal LM loss on the full sequence.'''
    ),
]
