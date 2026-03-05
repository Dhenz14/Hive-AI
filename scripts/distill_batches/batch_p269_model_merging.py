"""Model merging and composition — TIES, DARE, task arithmetic, SLERP."""

PAIRS = [
    (
        "ai/model-merging-techniques",
        "Show model merging techniques: task arithmetic, TIES merging, DARE, and spherical interpolation for combining fine-tuned models.",
        '''Model merging — combining fine-tuned models without retraining:

```python
import torch
import numpy as np
from typing import Optional


def task_arithmetic_merge(base: dict, models: list[dict],
                           weights: list[float]) -> dict:
    """Task arithmetic: merge by adding weighted task vectors.

    task_vector = fine_tuned - base
    merged = base + sum(weight_i * task_vector_i)
    """
    merged = {}
    for key in base:
        task_vectors = [w * (m[key].float() - base[key].float())
                        for m, w in zip(models, weights)]
        merged[key] = base[key].float() + sum(task_vectors)
    return merged


def ties_merge(base: dict, models: list[dict], weights: list[float],
               density: float = 0.5) -> dict:
    """TIES merging: Trim, Elect Sign, Disjoint Merge.

    1. Trim: zero out small-magnitude changes (keep top density%)
    2. Elect sign: majority vote on direction of change
    3. Disjoint merge: average only agreeing parameters
    """
    merged = {}
    for key in base:
        task_vectors = []
        for m, w in zip(models, weights):
            tv = w * (m[key].float() - base[key].float())
            # Step 1: Trim — keep only top density% by magnitude
            threshold = torch.quantile(tv.abs().float(),
                                        1.0 - density)
            tv[tv.abs() < threshold] = 0.0
            task_vectors.append(tv)

        stacked = torch.stack(task_vectors)

        # Step 2: Elect sign — majority vote
        signs = torch.sign(stacked)
        elected_sign = torch.sign(signs.sum(dim=0))

        # Step 3: Disjoint merge — average only matching signs
        mask = (signs == elected_sign.unsqueeze(0))
        masked = stacked * mask.float()
        counts = mask.float().sum(dim=0).clamp(min=1)
        merged_tv = masked.sum(dim=0) / counts

        merged[key] = base[key].float() + merged_tv
    return merged


def dare_merge(base: dict, models: list[dict], weights: list[float],
               drop_rate: float = 0.9) -> dict:
    """DARE merging: Drop And REscale.

    Randomly drop most delta parameters, rescale survivors.
    Surprisingly effective — most parameters don't matter.
    """
    merged = {}
    for key in base:
        task_vectors = []
        for m, w in zip(models, weights):
            tv = w * (m[key].float() - base[key].float())
            # Random binary mask
            mask = torch.bernoulli(torch.full_like(tv, 1.0 - drop_rate))
            # Rescale to preserve expected magnitude
            tv = tv * mask / (1.0 - drop_rate)
            task_vectors.append(tv)

        merged[key] = base[key].float() + sum(task_vectors)
    return merged


def slerp_merge(model_a: dict, model_b: dict, t: float = 0.5) -> dict:
    """Spherical linear interpolation between two models.

    Better than linear interpolation — preserves weight magnitude.
    SLERP(a, b, t) = sin((1-t)θ)/sin(θ) * a + sin(tθ)/sin(θ) * b
    """
    merged = {}
    for key in model_a:
        a = model_a[key].float().flatten()
        b = model_b[key].float().flatten()

        # Compute angle between vectors
        a_norm = a / (a.norm() + 1e-8)
        b_norm = b / (b.norm() + 1e-8)
        cos_theta = (a_norm * b_norm).sum().clamp(-1, 1)
        theta = torch.acos(cos_theta)

        if theta.abs() < 1e-6:
            # Vectors nearly parallel, use linear interp
            merged[key] = ((1 - t) * a + t * b).reshape(model_a[key].shape)
        else:
            sin_theta = torch.sin(theta)
            w_a = torch.sin((1 - t) * theta) / sin_theta
            w_b = torch.sin(t * theta) / sin_theta
            merged[key] = (w_a * a + w_b * b).reshape(model_a[key].shape)

    return merged


class MergeKit:
    """High-level model merging API."""

    @staticmethod
    def merge(base_path: str, model_paths: list[str],
              method: str = "ties", **kwargs) -> dict:
        base = torch.load(base_path, map_location="cpu", weights_only=True)
        models = [torch.load(p, map_location="cpu", weights_only=True)
                  for p in model_paths]
        weights = kwargs.get("weights", [1.0 / len(models)] * len(models))

        methods = {
            "task_arithmetic": task_arithmetic_merge,
            "ties": ties_merge,
            "dare": dare_merge,
        }
        if method == "slerp" and len(models) == 2:
            return slerp_merge(models[0], models[1], kwargs.get("t", 0.5))

        return methods[method](base, models, weights, **{
            k: v for k, v in kwargs.items() if k != "weights"
        })
```

Key patterns:
1. **Task vectors** — difference between fine-tuned and base weights; captures learned skills
2. **TIES trimming** — remove small deltas; most fine-tuning changes are noise
3. **Sign election** — resolve conflicts by majority vote on parameter direction
4. **DARE sparsity** — randomly drop 90% of deltas; rescale survivors to compensate
5. **SLERP** — spherical interpolation preserves weight norms better than linear lerp'''
    ),
    (
        "ai/model-evaluation-pipeline",
        "Show end-to-end model evaluation pipeline: loading merged models, running benchmarks, and comparing against baselines.",
        '''Model evaluation pipeline:

```python
import json
import time
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class EvalConfig:
    model_path: str
    model_name: str
    benchmarks: list[str]
    batch_size: int = 8
    max_samples: int = 500
    output_dir: str = "eval_results"


@dataclass
class BenchmarkResult:
    benchmark: str
    accuracy: float
    n_correct: int
    n_total: int
    avg_latency_ms: float
    details: list[dict] = field(default_factory=list)


class EvalPipeline:
    """End-to-end model evaluation."""

    def __init__(self, config: EvalConfig):
        self.config = config
        self.results: list[BenchmarkResult] = []

    def run_benchmark(self, name: str, tasks: list[dict],
                       model_fn) -> BenchmarkResult:
        correct = 0
        total = 0
        latencies = []
        details = []

        for task in tasks[:self.config.max_samples]:
            start = time.perf_counter()
            prediction = model_fn(task["prompt"])
            latency = (time.perf_counter() - start) * 1000

            is_correct = self._check_answer(prediction, task["expected"])
            correct += int(is_correct)
            total += 1
            latencies.append(latency)

            details.append({
                "prompt": task["prompt"][:200],
                "predicted": prediction[:200],
                "expected": task["expected"][:200],
                "correct": is_correct,
                "latency_ms": latency,
            })

        result = BenchmarkResult(
            benchmark=name,
            accuracy=correct / max(total, 1),
            n_correct=correct,
            n_total=total,
            avg_latency_ms=sum(latencies) / max(len(latencies), 1),
            details=details,
        )
        self.results.append(result)
        return result

    def compare_models(self, results_a: list[BenchmarkResult],
                        results_b: list[BenchmarkResult]) -> dict:
        """Compare two models across benchmarks."""
        comparison = {}
        a_by_name = {r.benchmark: r for r in results_a}
        b_by_name = {r.benchmark: r for r in results_b}

        for name in set(a_by_name) | set(b_by_name):
            a = a_by_name.get(name)
            b = b_by_name.get(name)
            if a and b:
                comparison[name] = {
                    "model_a_accuracy": a.accuracy,
                    "model_b_accuracy": b.accuracy,
                    "delta": b.accuracy - a.accuracy,
                    "speedup": a.avg_latency_ms / max(b.avg_latency_ms, 0.1),
                }
        return comparison

    def _check_answer(self, predicted: str, expected: str) -> bool:
        pred = predicted.strip().lower()
        exp = expected.strip().lower()
        return pred == exp or exp in pred

    def save_results(self):
        out = Path(self.config.output_dir)
        out.mkdir(exist_ok=True)
        report = {
            "model": self.config.model_name,
            "results": [
                {"benchmark": r.benchmark, "accuracy": r.accuracy,
                 "n_total": r.n_total, "avg_latency_ms": r.avg_latency_ms}
                for r in self.results
            ],
        }
        path = out / f"{self.config.model_name}_eval.json"
        path.write_text(json.dumps(report, indent=2))
        return str(path)
```

Key patterns:
1. **Configurable pipeline** — model path, benchmarks, batch size in single config
2. **Per-sample tracking** — record prediction, expected, correctness, latency for debugging
3. **Model comparison** — delta accuracy and speedup across benchmarks
4. **Flexible matching** — exact match and contains-match for answer checking
5. **Reproducible results** — save full results to JSON for later analysis'''
    ),
]
"""
