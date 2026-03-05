"""Synthetic data generation — LLM-generated training data, data flywheel."""

PAIRS = [
    (
        "ai/synthetic-data-generation",
        "Show synthetic training data generation with LLMs: seed-based expansion, quality filtering, and diversity-aware sampling.",
        '''Synthetic data generation pipeline:

```python
import json
import hashlib
import random
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class SyntheticSample:
    instruction: str
    response: str
    seed_id: str
    quality_score: float = 0.0
    diversity_hash: str = ""
    metadata: dict = field(default_factory=dict)


class SyntheticDataPipeline:
    """Generate diverse training data from seed examples using LLMs."""

    def __init__(self, generator_fn: Callable, judge_fn: Callable):
        self.generator = generator_fn
        self.judge = judge_fn
        self.samples: list[SyntheticSample] = []
        self.seen_hashes: set = set()

    def expand_seed(self, seed_instruction: str, seed_response: str,
                     n_variants: int = 5) -> list[SyntheticSample]:
        """Generate diverse variants from a seed example."""
        prompt = f"""Generate {n_variants} diverse training examples similar to this seed.
Each should test the same skill but with different context/complexity.

Seed instruction: {seed_instruction}
Seed response: {seed_response}

Output JSON array: [{{"instruction": "...", "response": "..."}}]
Vary: domain, difficulty, length, edge cases, error scenarios."""

        raw = self.generator(prompt)
        variants = json.loads(raw)

        samples = []
        for v in variants:
            sample = SyntheticSample(
                instruction=v["instruction"],
                response=v["response"],
                seed_id=hashlib.md5(seed_instruction.encode()).hexdigest()[:8],
            )
            samples.append(sample)
        return samples

    def score_quality(self, sample: SyntheticSample) -> float:
        """Use LLM judge to score sample quality 1-5."""
        prompt = f"""Rate this training example quality (1-5):
- Accuracy: Is the response correct?
- Completeness: Does it fully answer the instruction?
- Clarity: Is it well-written and clear?

Instruction: {sample.instruction}
Response: {sample.response}

Output JSON: {{"score": <1-5>, "issues": ["..."]}}"""

        result = json.loads(self.judge(prompt))
        sample.quality_score = result["score"]
        return result["score"]

    def compute_diversity_hash(self, sample: SyntheticSample) -> str:
        """Hash key concepts for deduplication."""
        words = sample.instruction.lower().split()
        key_words = sorted(set(w for w in words if len(w) > 4))[:10]
        h = hashlib.md5(" ".join(key_words).encode()).hexdigest()[:12]
        sample.diversity_hash = h
        return h

    def filter_and_deduplicate(self, samples: list[SyntheticSample],
                                min_quality: float = 3.5) -> list[SyntheticSample]:
        """Keep high-quality, diverse samples."""
        filtered = []
        for s in samples:
            if s.quality_score < min_quality:
                continue
            div_hash = self.compute_diversity_hash(s)
            if div_hash in self.seen_hashes:
                continue
            self.seen_hashes.add(div_hash)
            filtered.append(s)
        return filtered

    def generate_dataset(self, seeds: list[dict], target_size: int = 1000,
                          variants_per_seed: int = 10) -> list[dict]:
        """Full pipeline: expand seeds → score → filter → export."""
        all_samples = []
        for seed in seeds:
            variants = self.expand_seed(seed["instruction"], seed["response"],
                                         n_variants=variants_per_seed)
            for v in variants:
                self.score_quality(v)
            all_samples.extend(variants)

            if len(all_samples) >= target_size * 2:
                break

        filtered = self.filter_and_deduplicate(all_samples)
        # Sample to target size maintaining seed diversity
        if len(filtered) > target_size:
            filtered = self._diverse_sample(filtered, target_size)

        return [{"instruction": s.instruction, "response": s.response,
                 "quality": s.quality_score} for s in filtered]

    def _diverse_sample(self, samples: list[SyntheticSample],
                         n: int) -> list[SyntheticSample]:
        """Sample maintaining diversity across seed sources."""
        by_seed = {}
        for s in samples:
            by_seed.setdefault(s.seed_id, []).append(s)

        result = []
        per_seed = max(1, n // len(by_seed))
        for seed_samples in by_seed.values():
            seed_samples.sort(key=lambda x: x.quality_score, reverse=True)
            result.extend(seed_samples[:per_seed])

        random.shuffle(result)
        return result[:n]
```

Key patterns:
1. **Seed expansion** — few high-quality seeds → many diverse variants via LLM generation
2. **LLM-as-judge scoring** — use strong model to rate generated sample quality
3. **Diversity hashing** — detect near-duplicates by hashing key concepts
4. **Quality filtering** — minimum score threshold removes low-quality generations
5. **Balanced sampling** — maintain representation across seed sources for diversity'''
    ),
    (
        "ai/data-flywheel",
        "Show the data flywheel pattern: collecting production data, human feedback, and iterative model improvement.",
        '''Data flywheel — continuous model improvement:

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict


class FeedbackType(Enum):
    THUMBS_UP = "positive"
    THUMBS_DOWN = "negative"
    EDIT = "correction"
    REGENERATE = "regenerate"


@dataclass
class ProductionSample:
    request_id: str
    input_text: str
    output_text: str
    model_version: str
    timestamp: str
    latency_ms: float
    feedback: FeedbackType | None = None
    corrected_output: str | None = None
    metadata: dict = field(default_factory=dict)


class DataFlywheel:
    """Collect production data → curate → retrain → deploy → repeat."""

    def __init__(self):
        self.samples: list[ProductionSample] = []
        self.training_sets: dict[str, list] = {}

    def log_interaction(self, sample: ProductionSample):
        self.samples.append(sample)

    def log_feedback(self, request_id: str, feedback: FeedbackType,
                      correction: str = None):
        for s in self.samples:
            if s.request_id == request_id:
                s.feedback = feedback
                if correction:
                    s.corrected_output = correction
                break

    def curate_training_set(self, version: str) -> list[dict]:
        """Build training set from production feedback."""
        training_data = []

        for s in self.samples:
            if s.feedback == FeedbackType.THUMBS_UP:
                training_data.append({
                    "instruction": s.input_text,
                    "response": s.output_text,
                    "source": "positive_feedback",
                    "weight": 1.0,
                })
            elif s.feedback == FeedbackType.EDIT and s.corrected_output:
                training_data.append({
                    "instruction": s.input_text,
                    "response": s.corrected_output,
                    "source": "human_correction",
                    "weight": 2.0,  # Corrections are high-value
                })
            elif s.feedback == FeedbackType.THUMBS_DOWN:
                # DPO pair: corrected > original
                if s.corrected_output:
                    training_data.append({
                        "instruction": s.input_text,
                        "chosen": s.corrected_output,
                        "rejected": s.output_text,
                        "source": "preference_pair",
                    })

        self.training_sets[version] = training_data
        return training_data

    def compute_metrics(self) -> dict:
        """Track flywheel health metrics."""
        total = len(self.samples)
        feedback_count = sum(1 for s in self.samples if s.feedback)
        positive = sum(1 for s in self.samples
                       if s.feedback == FeedbackType.THUMBS_UP)
        negative = sum(1 for s in self.samples
                       if s.feedback == FeedbackType.THUMBS_DOWN)
        corrections = sum(1 for s in self.samples
                          if s.feedback == FeedbackType.EDIT)

        by_version = defaultdict(lambda: {"total": 0, "positive": 0})
        for s in self.samples:
            by_version[s.model_version]["total"] += 1
            if s.feedback == FeedbackType.THUMBS_UP:
                by_version[s.model_version]["positive"] += 1

        return {
            "total_samples": total,
            "feedback_rate": feedback_count / max(total, 1),
            "satisfaction_rate": positive / max(feedback_count, 1),
            "correction_rate": corrections / max(feedback_count, 1),
            "by_version": dict(by_version),
        }
```

Key patterns:
1. **Production logging** — capture every interaction with model version and latency
2. **Multi-signal feedback** — thumbs up/down, edits, regenerations each signal different things
3. **Correction weighting** — human edits are highest-value training signal; weight 2x
4. **DPO pairs** — negative feedback + correction = preference pair for alignment training
5. **Version tracking** — compare satisfaction rates across model versions to measure progress'''
    ),
    (
        "ai/curriculum-learning",
        "Show curriculum learning: ordering training data by difficulty, multi-stage training, and adaptive scheduling.",
        '''Curriculum learning — training data ordering strategies:

```python
import torch
import numpy as np
from torch.utils.data import Dataset, Sampler


class CurriculumDataset(Dataset):
    """Dataset with difficulty scores for curriculum learning."""

    def __init__(self, samples: list[dict]):
        self.samples = samples
        self.difficulties = np.array([s["difficulty"] for s in samples])

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]

    @staticmethod
    def compute_difficulty(sample: dict) -> float:
        """Heuristic difficulty scoring."""
        score = 0.0
        text = sample.get("instruction", "") + sample.get("response", "")
        score += min(len(text) / 2000, 1.0) * 0.3  # Length
        score += min(text.count("\\n") / 50, 1.0) * 0.2  # Complexity
        code_blocks = text.count("```")
        score += min(code_blocks / 6, 1.0) * 0.3  # Code complexity
        score += min(len(set(text.split())) / 500, 1.0) * 0.2  # Vocabulary
        return score


class CurriculumSampler(Sampler):
    """Sampler that gradually introduces harder examples."""

    def __init__(self, dataset: CurriculumDataset, n_epochs: int = 10):
        self.dataset = dataset
        self.n_epochs = n_epochs
        self.current_epoch = 0
        self.sorted_indices = np.argsort(dataset.difficulties)

    def set_epoch(self, epoch: int):
        self.current_epoch = epoch

    def __iter__(self):
        # Fraction of data to include (grows each epoch)
        progress = min((self.current_epoch + 1) / self.n_epochs, 1.0)
        # Competence function: start with easy, add harder gradually
        competence = 0.3 + 0.7 * progress  # 30% → 100%
        n_available = int(len(self.dataset) * competence)
        available = self.sorted_indices[:n_available]
        np.random.shuffle(available)
        return iter(available.tolist())

    def __len__(self):
        progress = min((self.current_epoch + 1) / self.n_epochs, 1.0)
        competence = 0.3 + 0.7 * progress
        return int(len(self.dataset) * competence)


class MultiStageCurriculum:
    """Multi-stage training with different data mixtures."""

    def __init__(self):
        self.stages = []

    def add_stage(self, name: str, datasets: dict[str, float],
                   epochs: int, lr: float):
        """Add training stage with data mixture ratios."""
        self.stages.append({
            "name": name, "datasets": datasets,
            "epochs": epochs, "lr": lr,
        })

    def get_schedule(self) -> list[dict]:
        """Example multi-stage schedule for LLM training."""
        return [
            {"name": "foundation", "epochs": 3, "lr": 2e-5,
             "datasets": {"general": 0.7, "code": 0.2, "math": 0.1}},
            {"name": "specialization", "epochs": 2, "lr": 1e-5,
             "datasets": {"domain_specific": 0.6, "general": 0.3, "hard_examples": 0.1}},
            {"name": "alignment", "epochs": 1, "lr": 5e-6,
             "datasets": {"preference_pairs": 0.5, "safety": 0.3, "quality": 0.2}},
        ]
```

Key patterns:
1. **Difficulty scoring** — heuristic or model-based difficulty estimation per sample
2. **Competence function** — gradually increase fraction of hard examples during training
3. **Multi-stage** — different data mixtures at different training phases
4. **Easy-to-hard** — start with simple examples; complex ones later when model has foundations
5. **Adaptive pacing** — if loss is low, accelerate; if loss is high, slow down curriculum'''
    ),
]
