"""LLM evaluation and benchmarking — metrics, benchmarks, human eval."""

PAIRS = [
    (
        "ai/llm-benchmarks",
        "Show LLM evaluation benchmark patterns: automated scoring, multi-task evaluation, and benchmark suite implementation.",
        '''LLM benchmark evaluation framework:

```python
import json
import re
from dataclasses import dataclass, field
from typing import Callable
from collections import defaultdict


@dataclass
class BenchmarkTask:
    name: str
    prompt: str
    expected: str
    category: str
    difficulty: str = "medium"
    metadata: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    task: str
    score: float
    predicted: str
    expected: str
    category: str
    latency_ms: float = 0
    tokens_used: int = 0


class LLMBenchmark:
    """Multi-task LLM evaluation suite."""

    def __init__(self, model_fn: Callable):
        self.model_fn = model_fn
        self.tasks: list[BenchmarkTask] = []
        self.results: list[EvalResult] = []
        self.scorers: dict[str, Callable] = {
            "exact_match": self._exact_match,
            "contains": self._contains_match,
            "numeric": self._numeric_match,
            "code_exec": self._code_execution_match,
        }

    def add_tasks(self, tasks: list[BenchmarkTask]):
        self.tasks.extend(tasks)

    def run(self, scoring: str = "exact_match") -> dict:
        """Run all benchmark tasks and collect results."""
        scorer = self.scorers[scoring]

        for task in self.tasks:
            import time
            start = time.perf_counter()
            predicted = self.model_fn(task.prompt)
            latency = (time.perf_counter() - start) * 1000

            score = scorer(predicted, task.expected)
            self.results.append(EvalResult(
                task=task.name, score=score,
                predicted=predicted, expected=task.expected,
                category=task.category, latency_ms=latency,
            ))

        return self.aggregate()

    def aggregate(self) -> dict:
        """Aggregate results by category."""
        by_category = defaultdict(list)
        for r in self.results:
            by_category[r.category].append(r.score)

        return {
            "overall": sum(r.score for r in self.results) / len(self.results),
            "by_category": {
                cat: sum(scores) / len(scores)
                for cat, scores in by_category.items()
            },
            "n_tasks": len(self.results),
            "avg_latency_ms": sum(r.latency_ms for r in self.results) / len(self.results),
        }

    def _exact_match(self, predicted: str, expected: str) -> float:
        return 1.0 if predicted.strip().lower() == expected.strip().lower() else 0.0

    def _contains_match(self, predicted: str, expected: str) -> float:
        return 1.0 if expected.strip().lower() in predicted.lower() else 0.0

    def _numeric_match(self, predicted: str, expected: str) -> float:
        try:
            nums = re.findall(r"-?\\d+\\.?\\d*", predicted)
            expected_num = float(expected)
            for n in nums:
                if abs(float(n) - expected_num) < 1e-6:
                    return 1.0
        except ValueError:
            pass
        return 0.0

    def _code_execution_match(self, predicted: str, expected: str) -> float:
        """Execute predicted code and check output."""
        code_match = re.search(r"```python\\n(.*?)```", predicted, re.DOTALL)
        if not code_match:
            return 0.0
        try:
            local_vars = {}
            exec(code_match.group(1), {}, local_vars)
            result = str(local_vars.get("result", ""))
            return 1.0 if result.strip() == expected.strip() else 0.0
        except Exception:
            return 0.0


class LLMJudge:
    """Use a strong LLM to judge another LLM's outputs."""

    def __init__(self, judge_fn: Callable):
        self.judge_fn = judge_fn

    def pairwise_comparison(self, prompt: str, response_a: str,
                             response_b: str) -> dict:
        """Compare two responses; return winner."""
        judge_prompt = f"""Compare these two responses to the prompt.

Prompt: {prompt}

Response A: {response_a}

Response B: {response_b}

Which response is better? Consider accuracy, completeness, and clarity.
Output JSON: {{"winner": "A" or "B" or "tie", "reasoning": "..."}}"""

        result = self.judge_fn(judge_prompt)
        return json.loads(result)

    def rubric_scoring(self, prompt: str, response: str,
                        rubric: dict[str, str]) -> dict:
        """Score response on multiple dimensions."""
        scores = {}
        for dimension, criteria in rubric.items():
            judge_prompt = f"""Rate this response on {dimension} (1-5).

Criteria: {criteria}

Prompt: {prompt}
Response: {response}

Output JSON: {{"score": <1-5>, "reasoning": "..."}}"""

            result = json.loads(self.judge_fn(judge_prompt))
            scores[dimension] = result["score"]

        scores["overall"] = sum(scores.values()) / len(scores)
        return scores
```

Key patterns:
1. **Multi-scorer** — exact match, contains, numeric extraction, code execution for different task types
2. **Category aggregation** — break down scores by reasoning, coding, math, etc. for diagnostic view
3. **LLM-as-judge** — use strong model to evaluate weaker models; pairwise or rubric-based
4. **Latency tracking** — speed matters in production; track alongside accuracy
5. **Rubric scoring** — multi-dimensional evaluation (accuracy, clarity, safety) for nuanced assessment'''
    ),
    (
        "ai/model-comparison",
        "Show LLM model comparison patterns: A/B testing, Elo rating, and systematic evaluation across capabilities.",
        '''LLM model comparison and ranking:

```python
import math
import random
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class ModelProfile:
    name: str
    elo_rating: float = 1200.0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    cost_per_1k_tokens: float = 0.0


class EloRanking:
    """Elo rating system for comparing LLMs via pairwise battles."""

    def __init__(self, k_factor: float = 32.0):
        self.k = k_factor
        self.models: dict[str, ModelProfile] = {}
        self.history: list[dict] = []

    def register_model(self, name: str, **kwargs):
        self.models[name] = ModelProfile(name=name, **kwargs)

    def expected_score(self, rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def record_match(self, model_a: str, model_b: str,
                      winner: str = None):
        """Update Elo ratings based on match result."""
        a = self.models[model_a]
        b = self.models[model_b]

        expected_a = self.expected_score(a.elo_rating, b.elo_rating)

        if winner == model_a:
            actual_a = 1.0
            a.wins += 1
            b.losses += 1
        elif winner == model_b:
            actual_a = 0.0
            a.losses += 1
            b.wins += 1
        else:
            actual_a = 0.5
            a.draws += 1
            b.draws += 1

        a.elo_rating += self.k * (actual_a - expected_a)
        b.elo_rating += self.k * ((1 - actual_a) - (1 - expected_a))

        self.history.append({
            "model_a": model_a, "model_b": model_b,
            "winner": winner, "elo_a": a.elo_rating, "elo_b": b.elo_rating,
        })

    def leaderboard(self) -> list[dict]:
        """Return models ranked by Elo."""
        ranked = sorted(self.models.values(),
                        key=lambda m: m.elo_rating, reverse=True)
        return [
            {"rank": i+1, "model": m.name, "elo": round(m.elo_rating),
             "wins": m.wins, "losses": m.losses, "draws": m.draws,
             "win_rate": m.wins / max(m.wins + m.losses + m.draws, 1)}
            for i, m in enumerate(ranked)
        ]


class CapabilityMatrix:
    """Evaluate models across capability dimensions."""

    def __init__(self):
        self.capabilities = [
            "reasoning", "coding", "math", "instruction_following",
            "creativity", "factuality", "safety", "multilingual",
        ]
        self.scores: dict[str, dict[str, float]] = defaultdict(dict)

    def record_score(self, model: str, capability: str, score: float):
        self.scores[model][capability] = score

    def radar_chart_data(self, models: list[str]) -> dict:
        """Get data for radar/spider chart comparison."""
        return {
            "capabilities": self.capabilities,
            "models": {
                model: [self.scores[model].get(cap, 0) for cap in self.capabilities]
                for model in models
            },
        }

    def best_for(self, capability: str) -> str:
        """Find best model for a specific capability."""
        best_model = max(
            self.scores.keys(),
            key=lambda m: self.scores[m].get(capability, 0)
        )
        return best_model

    def cost_efficiency(self, cost_per_model: dict[str, float]) -> dict:
        """Score / cost ratio for each model."""
        results = {}
        for model, scores in self.scores.items():
            avg_score = sum(scores.values()) / len(scores) if scores else 0
            cost = cost_per_model.get(model, 1.0)
            results[model] = {"avg_score": avg_score, "cost": cost,
                              "efficiency": avg_score / cost}
        return dict(sorted(results.items(),
                           key=lambda x: x[1]["efficiency"], reverse=True))
```

Key patterns:
1. **Elo rating** — chess-style ranking from pairwise comparisons; converges with many matches
2. **Expected score** — probability of winning based on rating difference; logistic curve
3. **Capability matrix** — evaluate across dimensions; models have different strength profiles
4. **Cost efficiency** — score per dollar; the cheapest model that meets quality bar often wins
5. **Leaderboard** — rank by Elo with win/loss stats; transparent comparison methodology'''
    ),
    (
        "ai/eval-datasets",
        "Show how to create evaluation datasets: human annotation pipelines, inter-annotator agreement, and quality-controlled data collection.",
        '''Evaluation dataset creation and quality control:

```python
import hashlib
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AnnotationTask:
    id: str
    text: str
    category: str
    labels: list[str]  # Available label options
    metadata: dict = field(default_factory=dict)


@dataclass
class Annotation:
    task_id: str
    annotator_id: str
    label: str
    confidence: float = 1.0
    time_seconds: float = 0.0


class AnnotationPipeline:
    """Manage human annotation with quality control."""

    def __init__(self, n_annotators_per_task: int = 3):
        self.n_annotators = n_annotators_per_task
        self.tasks: dict[str, AnnotationTask] = {}
        self.annotations: list[Annotation] = []
        self.gold_standard: dict[str, str] = {}  # Calibration items

    def add_task(self, task: AnnotationTask):
        self.tasks[task.id] = task

    def add_calibration(self, task_id: str, gold_label: str):
        """Add known-answer items for annotator quality checks."""
        self.gold_standard[task_id] = gold_label

    def record_annotation(self, annotation: Annotation):
        self.annotations.append(annotation)

    def get_majority_vote(self, task_id: str) -> Optional[str]:
        """Resolve label by majority vote."""
        labels = [a.label for a in self.annotations if a.task_id == task_id]
        if not labels:
            return None
        counts = Counter(labels)
        top = counts.most_common(1)[0]
        # Require majority (>50%)
        if top[1] > len(labels) / 2:
            return top[0]
        return None  # No consensus

    def cohens_kappa(self, annotator_a: str, annotator_b: str) -> float:
        """Inter-annotator agreement (Cohen's kappa)."""
        a_labels = {a.task_id: a.label for a in self.annotations
                    if a.annotator_id == annotator_a}
        b_labels = {a.task_id: a.label for a in self.annotations
                    if a.annotator_id == annotator_b}

        shared = set(a_labels.keys()) & set(b_labels.keys())
        if not shared:
            return 0.0

        # Observed agreement
        agree = sum(1 for t in shared if a_labels[t] == b_labels[t])
        po = agree / len(shared)

        # Expected agreement by chance
        all_labels = list(set(list(a_labels.values()) + list(b_labels.values())))
        pe = sum(
            (sum(1 for t in shared if a_labels[t] == l) / len(shared)) *
            (sum(1 for t in shared if b_labels[t] == l) / len(shared))
            for l in all_labels
        )

        if pe == 1.0:
            return 1.0
        return (po - pe) / (1 - pe)

    def annotator_quality(self) -> dict[str, float]:
        """Check annotator accuracy on gold standard items."""
        scores = defaultdict(list)
        for ann in self.annotations:
            if ann.task_id in self.gold_standard:
                correct = ann.label == self.gold_standard[ann.task_id]
                scores[ann.annotator_id].append(correct)

        return {
            ann_id: sum(s) / len(s) if s else 0.0
            for ann_id, s in scores.items()
        }

    def export_dataset(self, min_agreement: float = 0.66) -> list[dict]:
        """Export high-quality annotated dataset."""
        dataset = []
        for task_id, task in self.tasks.items():
            labels = [a.label for a in self.annotations if a.task_id == task_id]
            if not labels:
                continue

            counts = Counter(labels)
            top_label, top_count = counts.most_common(1)[0]
            agreement = top_count / len(labels)

            if agreement >= min_agreement:
                dataset.append({
                    "id": task_id, "text": task.text,
                    "label": top_label, "agreement": agreement,
                    "n_annotations": len(labels),
                })

        return dataset
```

Key patterns:
1. **Multi-annotator** — 3+ annotations per item; majority vote resolves disagreements
2. **Gold standard** — known-answer items mixed in to detect low-quality annotators
3. **Cohen's kappa** — inter-annotator agreement beyond chance; κ > 0.8 is excellent
4. **Quality filtering** — only export items with sufficient agreement; skip ambiguous ones
5. **Calibration items** — track annotator accuracy on gold items to weight their votes'''
    ),
]
