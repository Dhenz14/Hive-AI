"""Meta-learning and few-shot adaptation -- learning to learn faster on 15GB VRAM."""

PAIRS = [
    (
        "local-ai/meta-learning-few-shot",
        "Show meta-learning for local AI self-improvement: few-shot adaptation, task-specific LoRA banks, and rapid skill acquisition without full retraining.",
        """Meta-learning for rapid local AI adaptation:

```python
import json
import os
import hashlib
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class SkillProfile:
    \"\"\"Tracks a learned skill with its LoRA adapter.\"\"\"
    skill_name: str
    lora_path: str
    accuracy: float = 0.0
    examples_trained: int = 0
    categories: list[str] = field(default_factory=list)
    created_at: str = ""
    last_improved: str = ""


class LoRABank:
    \"\"\"Bank of task-specific LoRA adapters for rapid switching.

    Instead of one monolithic fine-tune, maintain a library of
    small LoRAs that can be hot-swapped or composed for new tasks.
    \"\"\"

    def __init__(self, bank_dir: str, max_loras: int = 50):
        self.bank_dir = Path(bank_dir)
        self.bank_dir.mkdir(parents=True, exist_ok=True)
        self.max_loras = max_loras
        self.skills: dict[str, SkillProfile] = {}
        self._load_index()

    def _load_index(self):
        index_path = self.bank_dir / "index.json"
        if index_path.exists():
            data = json.loads(index_path.read_text())
            for name, info in data.items():
                self.skills[name] = SkillProfile(**info)

    def _save_index(self):
        data = {name: vars(sp) for name, sp in self.skills.items()}
        (self.bank_dir / "index.json").write_text(json.dumps(data, indent=2))

    def register_skill(self, profile: SkillProfile):
        \"\"\"Add a new skill LoRA to the bank.\"\"\"
        if len(self.skills) >= self.max_loras:
            self._evict_weakest()
        self.skills[profile.skill_name] = profile
        self._save_index()

    def find_relevant_loras(self, task_description: str,
                             top_k: int = 3) -> list[SkillProfile]:
        \"\"\"Find most relevant existing LoRAs for a new task.

        Uses keyword overlap as a simple relevance heuristic.
        A real system would use embedding similarity.
        \"\"\"
        task_words = set(task_description.lower().split())
        scored = []
        for name, profile in self.skills.items():
            skill_words = set(name.lower().split())
            for cat in profile.categories:
                skill_words.update(cat.lower().split())
            overlap = len(task_words & skill_words)
            scored.append((overlap, profile))
        scored.sort(key=lambda x: (-x[0], -x[1].accuracy))
        return [s[1] for s in scored[:top_k]]

    def _evict_weakest(self):
        \"\"\"Remove lowest-accuracy skill to make room.\"\"\"
        if not self.skills:
            return
        weakest = min(self.skills.values(), key=lambda s: s.accuracy)
        lora_dir = Path(weakest.lora_path)
        if lora_dir.exists():
            import shutil
            shutil.rmtree(lora_dir)
        del self.skills[weakest.skill_name]


class FewShotAdapter:
    \"\"\"Rapidly adapt to new tasks using few examples.

    Strategy: instead of full fine-tuning on few examples (overfits),
    use existing LoRA bank as initialization + aggressive regularization.
    \"\"\"

    def __init__(self, bank: LoRABank, base_model_path: str):
        self.bank = bank
        self.base_model_path = base_model_path

    def adapt_to_task(self, task_name: str, examples: list[dict],
                       max_steps: int = 100) -> SkillProfile:
        \"\"\"Create a new skill from few examples.

        Steps:
        1. Find similar existing skills in bank
        2. Initialize LoRA from closest match (transfer learning)
        3. Train with high regularization for few steps
        4. Validate on held-out examples
        5. Register in bank if quality passes threshold
        \"\"\"
        # Find closest existing skill
        similar = self.bank.find_relevant_loras(task_name, top_k=1)
        init_from = similar[0].lora_path if similar else None

        # Split examples: 80% train, 20% validation
        split_idx = max(1, int(len(examples) * 0.8))
        train_examples = examples[:split_idx]
        val_examples = examples[split_idx:]

        # Configure aggressive regularization for few-shot
        train_config = {
            "lora_r": 8,              # Small rank for few examples
            "lora_alpha": 16,
            "learning_rate": 1e-4,    # Conservative LR
            "weight_decay": 0.1,      # Strong regularization
            "max_steps": min(max_steps, len(train_examples) * 3),
            "warmup_steps": 5,
            "gradient_accumulation": 2,
            "init_lora_path": init_from,  # Transfer from similar skill
        }

        # Train (calls into the QLoRA pipeline from p401)
        lora_path = self._train_few_shot(train_config, train_examples)

        # Validate
        accuracy = self._validate(lora_path, val_examples)

        profile = SkillProfile(
            skill_name=task_name,
            lora_path=lora_path,
            accuracy=accuracy,
            examples_trained=len(train_examples),
            categories=[task_name.split("/")[0]] if "/" in task_name else [],
        )

        if accuracy >= 0.6:  # Lower threshold for few-shot
            self.bank.register_skill(profile)
            print(f"Registered new skill: {task_name} (acc={accuracy:.2f})")
        else:
            print(f"Skill below threshold: {task_name} (acc={accuracy:.2f})")
            print("Need more examples or different approach")

        return profile

    def compose_loras(self, skill_names: list[str],
                       weights: Optional[list[float]] = None) -> str:
        \"\"\"Combine multiple LoRA skills for a complex task.

        Uses weighted LoRA merging: new_lora = w1*lora1 + w2*lora2 + ...
        \"\"\"
        if weights is None:
            weights = [1.0 / len(skill_names)] * len(skill_names)

        lora_paths = []
        for name in skill_names:
            if name in self.bank.skills:
                lora_paths.append(self.bank.skills[name].lora_path)

        # Merge LoRA weights (simplified)
        composed_path = str(
            self.bank.bank_dir / f"composed_{'_'.join(skill_names)}"
        )
        self._merge_lora_weights(lora_paths, weights, composed_path)
        return composed_path

    def _train_few_shot(self, config: dict, examples: list) -> str:
        \"\"\"Train a LoRA adapter on few examples. Delegates to QLoRA pipeline.\"\"\"
        # Placeholder: real implementation uses batch_p401 QLoRA training
        output_dir = str(self.bank.bank_dir / f"lora_{len(self.bank.skills)}")
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def _validate(self, lora_path: str, examples: list) -> float:
        \"\"\"Score LoRA on validation examples.\"\"\"
        if not examples:
            return 0.5  # No validation data; assume mediocre
        # Placeholder: real implementation runs inference + scoring
        return 0.75

    def _merge_lora_weights(self, paths: list, weights: list, output: str):
        \"\"\"Merge multiple LoRA adapters with weights.\"\"\"
        os.makedirs(output, exist_ok=True)
        # Placeholder: real implementation loads safetensors, weighted sum
```

Key patterns:
1. **LoRA bank** -- library of task-specific adapters; hot-swap instead of retrain from scratch
2. **Transfer initialization** -- start new LoRA from similar existing skill; faster convergence
3. **Few-shot regularization** -- small rank, high weight decay, limited steps; prevents overfitting
4. **LoRA composition** -- weighted merge of multiple skills for complex tasks
5. **Skill eviction** -- remove lowest-quality adapters when bank is full; bounded disk usage"""
    ),
    (
        "local-ai/curriculum-meta-learning",
        "Show curriculum-based meta-learning: how a local AI sequences its own training to maximize learning efficiency with limited compute.",
        """Curriculum meta-learning for efficient self-improvement:

```python
import json
import time
import random
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional


@dataclass
class TaskAttempt:
    \"\"\"Record of one training attempt on a task.\"\"\"
    task_id: str
    category: str
    difficulty: float  # 0.0-1.0
    success: bool
    score: float
    time_seconds: float
    attempt_number: int


@dataclass
class CategoryStats:
    \"\"\"Aggregated stats for a skill category.\"\"\"
    total_attempts: int = 0
    successes: int = 0
    avg_score: float = 0.0
    recent_scores: list[float] = field(default_factory=list)
    current_difficulty: float = 0.3  # Start at 30% difficulty
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    time_invested_sec: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / max(1, self.total_attempts)

    @property
    def learning_velocity(self) -> float:
        \"\"\"How fast scores are improving (positive = learning).\"\"\"
        if len(self.recent_scores) < 3:
            return 0.0
        recent = self.recent_scores[-5:]
        older = self.recent_scores[-10:-5] if len(self.recent_scores) >= 10 else self.recent_scores[:5]
        return (sum(recent) / len(recent)) - (sum(older) / len(older))

    @property
    def efficiency(self) -> float:
        \"\"\"Score per second of training invested.\"\"\"
        if self.time_invested_sec == 0:
            return 0
        return self.avg_score / self.time_invested_sec


class CurriculumScheduler:
    \"\"\"Sequences training tasks for maximum learning efficiency.

    Implements zone of proximal development: tasks should be
    challenging enough to learn from but not so hard they fail always.
    Target: 60-75% success rate per category.
    \"\"\"

    def __init__(self, categories: list[str]):
        self.stats: dict[str, CategoryStats] = {
            cat: CategoryStats() for cat in categories
        }
        self.history: list[TaskAttempt] = []
        self.target_success_rate = 0.65  # Zone of proximal development

    def record_attempt(self, attempt: TaskAttempt):
        \"\"\"Record a training attempt and update curriculum.\"\"\"
        self.history.append(attempt)
        stats = self.stats.setdefault(attempt.category, CategoryStats())

        stats.total_attempts += 1
        stats.time_invested_sec += attempt.time_seconds
        stats.recent_scores.append(attempt.score)
        if len(stats.recent_scores) > 20:
            stats.recent_scores = stats.recent_scores[-20:]

        stats.avg_score = sum(stats.recent_scores) / len(stats.recent_scores)

        if attempt.success:
            stats.successes += 1
            stats.consecutive_successes += 1
            stats.consecutive_failures = 0
        else:
            stats.consecutive_successes = 0
            stats.consecutive_failures += 1

        # Adjust difficulty based on performance
        self._adjust_difficulty(stats)

    def _adjust_difficulty(self, stats: CategoryStats):
        \"\"\"Move difficulty toward target success rate.\"\"\"
        if stats.total_attempts < 3:
            return  # Need minimum data

        if stats.success_rate > 0.80:
            # Too easy: increase difficulty
            stats.current_difficulty = min(1.0,
                stats.current_difficulty + 0.05)
        elif stats.success_rate < 0.50:
            # Too hard: decrease difficulty
            stats.current_difficulty = max(0.1,
                stats.current_difficulty - 0.05)

        # Fast-track: 5 consecutive successes = bigger jump
        if stats.consecutive_successes >= 5:
            stats.current_difficulty = min(1.0,
                stats.current_difficulty + 0.1)
            stats.consecutive_successes = 0

        # Rescue: 5 consecutive failures = bigger drop
        if stats.consecutive_failures >= 5:
            stats.current_difficulty = max(0.1,
                stats.current_difficulty - 0.1)
            stats.consecutive_failures = 0

    def select_next_category(self) -> str:
        \"\"\"Pick which category to train next.

        Priority order:
        1. Categories with high learning velocity (actively improving)
        2. Categories with low scores (weakest areas)
        3. Categories with least time invested (underexplored)
        \"\"\"
        scores = {}
        for cat, stats in self.stats.items():
            # Weighted score: high velocity + low score + low time
            velocity_score = max(0, stats.learning_velocity) * 3
            weakness_score = (1.0 - stats.avg_score) * 2
            explore_score = 1.0 / (1 + stats.total_attempts) * 1

            scores[cat] = velocity_score + weakness_score + explore_score

        # Softmax sampling (some randomness to avoid getting stuck)
        items = list(scores.items())
        weights = [s for _, s in items]
        total = sum(weights) or 1
        probs = [w / total for w in weights]

        chosen = random.choices([c for c, _ in items], weights=probs, k=1)[0]
        return chosen

    def get_training_plan(self, n_tasks: int = 10) -> list[dict]:
        \"\"\"Generate a training plan balancing exploitation and exploration.\"\"\"
        plan = []
        for _ in range(n_tasks):
            category = self.select_next_category()
            stats = self.stats[category]
            plan.append({
                "category": category,
                "target_difficulty": stats.current_difficulty,
                "current_score": stats.avg_score,
                "learning_velocity": stats.learning_velocity,
                "rationale": self._explain_choice(category),
            })
        return plan

    def _explain_choice(self, category: str) -> str:
        stats = self.stats[category]
        if stats.total_attempts < 3:
            return "Underexplored category; need baseline data"
        if stats.learning_velocity > 0.05:
            return f"Active learning (velocity={stats.learning_velocity:.3f})"
        if stats.avg_score < 0.5:
            return f"Weak area (score={stats.avg_score:.2f})"
        return f"Maintenance training (score={stats.avg_score:.2f})"

    def report(self) -> str:
        \"\"\"Summary report of curriculum progress.\"\"\"
        lines = ["=== Curriculum Progress ==="]
        for cat, stats in sorted(self.stats.items(),
                                   key=lambda x: x[1].avg_score):
            lines.append(
                f"  {cat}: score={stats.avg_score:.2f} "
                f"diff={stats.current_difficulty:.2f} "
                f"vel={stats.learning_velocity:+.3f} "
                f"n={stats.total_attempts}"
            )
        return "\\n".join(lines)
```

Key patterns:
1. **Zone of proximal development** -- target 60-75% success rate; too easy = no learning, too hard = frustration
2. **Adaptive difficulty** -- ratchet up on consecutive successes, drop on consecutive failures
3. **Category prioritization** -- focus on areas with active learning velocity or biggest weaknesses
4. **Exploration vs exploitation** -- softmax sampling ensures underexplored areas get attention
5. **Learning velocity** -- track score trends; prioritize categories where the model is actively improving"""
    ),
]
