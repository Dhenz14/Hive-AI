"""Complete 'get smarter' orchestrator -- the master controller that ties all self-improvement subsystems together."""

PAIRS = [
    (
        "local-ai/get-smarter-orchestrator",
        "Show the complete 'get smarter' orchestrator: a single entry point that coordinates self-training, evaluation, LoRA training, GGUF export, and curriculum management for autonomous AI self-improvement on 15GB VRAM.",
        """Complete 'get smarter' orchestrator:

```python
import json
import os
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from datetime import datetime
from enum import Enum

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("get_smarter")


class Phase(Enum):
    EVALUATE = "evaluate"
    GENERATE_DATA = "generate_data"
    TRAIN = "train"
    MERGE_EXPORT = "merge_export"
    VALIDATE = "validate"


@dataclass
class SmartConfig:
    \"\"\"Master configuration for the self-improvement pipeline.\"\"\"
    # Model paths
    base_model_hf: str              # HuggingFace model for training
    current_gguf: str               # Current GGUF for inference
    llama_cpp_path: str = "llama.cpp"
    llama_server_url: str = "http://127.0.0.1:8080"

    # Training
    lora_output_dir: str = "training/lora"
    merged_output_dir: str = "training/merged"
    training_data_dir: str = "training/data"
    lora_rank: int = 16
    lora_alpha: int = 32
    learning_rate: float = 2e-4
    max_steps: int = 200
    batch_size: int = 4
    gradient_accumulation: int = 4

    # Quality thresholds
    min_pair_quality: float = 0.7
    min_improvement: float = 0.02   # Must improve by 2%+ to keep
    max_regression: float = 0.05    # Reject if regresses 5%+

    # Resource constraints
    vram_budget_gb: float = 15.0
    max_training_hours: float = 2.0
    max_pairs_per_cycle: int = 200

    # Cycle management
    state_file: str = "training/state.json"
    max_cycles: int = 100


@dataclass
class CycleState:
    \"\"\"Persistent state across improvement cycles.\"\"\"
    cycle_number: int = 0
    total_pairs_trained: int = 0
    current_benchmark_score: float = 0.0
    best_benchmark_score: float = 0.0
    best_gguf_path: str = ""
    skill_scores: dict = field(default_factory=dict)
    weakest_skills: list = field(default_factory=list)
    history: list = field(default_factory=list)

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(vars(self), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "CycleState":
        if os.path.exists(path):
            with open(path) as f:
                return cls(**json.load(f))
        return cls()


class GetSmarter:
    \"\"\"Master orchestrator for AI self-improvement.

    Usage:
        smarter = GetSmarter(config)
        smarter.run()  # Runs one full improvement cycle

    Or for continuous improvement:
        smarter.run_continuous(max_cycles=10)

    The pipeline per cycle:
    1. EVALUATE -- benchmark current model, find weaknesses
    2. GENERATE_DATA -- create training pairs targeting weaknesses
    3. TRAIN -- QLoRA fine-tune on new + replay data
    4. MERGE_EXPORT -- merge LoRA, export GGUF
    5. VALIDATE -- benchmark new model, accept or rollback
    \"\"\"

    def __init__(self, config: SmartConfig):
        self.config = config
        self.state = CycleState.load(config.state_file)

        # Initialize subsystems (from other p400-series modules)
        self._init_subsystems()

    def _init_subsystems(self):
        \"\"\"Initialize all self-improvement subsystems.\"\"\"
        # These reference classes from p400-p406 batch files
        # In production, import from the actual training modules

        self.benchmarks = {
            "python_basics": self._benchmark_python_basics,
            "algorithms": self._benchmark_algorithms,
            "system_design": self._benchmark_system_design,
            "debugging": self._benchmark_debugging,
            "code_generation": self._benchmark_code_generation,
            "self_knowledge": self._benchmark_self_knowledge,
        }

    def run(self) -> dict:
        \"\"\"Run one complete improvement cycle.\"\"\"
        self.state.cycle_number += 1
        cycle_num = self.state.cycle_number
        log.info(f"=== Improvement Cycle {cycle_num} ===")

        result = {"cycle": cycle_num, "phases": {}}

        # Phase 1: EVALUATE
        log.info(f"Phase 1/{5}: EVALUATE")
        eval_result = self._phase_evaluate()
        result["phases"]["evaluate"] = eval_result

        # Phase 2: GENERATE DATA
        log.info(f"Phase 2/{5}: GENERATE DATA")
        data_result = self._phase_generate_data(eval_result)
        result["phases"]["generate_data"] = data_result

        # Phase 3: TRAIN
        log.info(f"Phase 3/{5}: TRAIN")
        train_result = self._phase_train(data_result)
        result["phases"]["train"] = train_result

        # Phase 4: MERGE & EXPORT
        log.info(f"Phase 4/{5}: MERGE & EXPORT")
        export_result = self._phase_merge_export(train_result)
        result["phases"]["merge_export"] = export_result

        # Phase 5: VALIDATE
        log.info(f"Phase 5/{5}: VALIDATE")
        valid_result = self._phase_validate(export_result)
        result["phases"]["validate"] = valid_result

        # Save state
        self.state.save(self.config.state_file)
        self._log_cycle_summary(result)

        return result

    def run_continuous(self, max_cycles: Optional[int] = None):
        \"\"\"Run improvement cycles until convergence or max cycles.\"\"\"
        max_c = max_cycles or self.config.max_cycles
        plateau_count = 0

        for _ in range(max_c):
            result = self.run()
            improvement = result["phases"]["validate"].get("improvement", 0)

            if improvement < self.config.min_improvement:
                plateau_count += 1
                log.info(f"Plateau detected ({plateau_count}/3)")
                if plateau_count >= 3:
                    log.info("Converged: 3 cycles without improvement")
                    break
            else:
                plateau_count = 0

    # === Phase Implementations ===

    def _phase_evaluate(self) -> dict:
        \"\"\"Benchmark current model across all skill areas.\"\"\"
        scores = {}
        for skill_name, benchmark_fn in self.benchmarks.items():
            score = benchmark_fn()
            scores[skill_name] = score
            log.info(f"  {skill_name}: {score:.3f}")

        overall = sum(scores.values()) / max(1, len(scores))
        self.state.current_benchmark_score = overall
        self.state.skill_scores = scores

        # Find weakest skills (bottom 3 or below threshold)
        sorted_skills = sorted(scores.items(), key=lambda x: x[1])
        weakest = [name for name, score in sorted_skills
                     if score < 0.7 or sorted_skills.index((name, score)) < 3]
        self.state.weakest_skills = weakest

        return {
            "overall_score": overall,
            "skill_scores": scores,
            "weakest_skills": weakest,
            "best_so_far": self.state.best_benchmark_score,
        }

    def _phase_generate_data(self, eval_result: dict) -> dict:
        \"\"\"Generate training data targeting weaknesses.\"\"\"
        weakest = eval_result["weakest_skills"]
        pairs_per_skill = self.config.max_pairs_per_cycle // max(1, len(weakest))

        all_pairs = []
        for skill in weakest:
            pairs = self._generate_skill_pairs(skill, pairs_per_skill)
            all_pairs.extend(pairs)
            log.info(f"  Generated {len(pairs)} pairs for {skill}")

        # Add replay data (20% from previous best pairs)
        replay = self._get_replay_pairs(
            int(len(all_pairs) * 0.25)
        )
        all_pairs.extend(replay)
        log.info(f"  Added {len(replay)} replay pairs")

        # Save training data
        data_path = os.path.join(
            self.config.training_data_dir,
            f"cycle_{self.state.cycle_number:04d}.jsonl"
        )
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        with open(data_path, "w") as f:
            for pair in all_pairs:
                f.write(json.dumps(pair) + "\\n")

        return {
            "total_pairs": len(all_pairs),
            "new_pairs": len(all_pairs) - len(replay),
            "replay_pairs": len(replay),
            "data_path": data_path,
            "skills_covered": weakest,
        }

    def _phase_train(self, data_result: dict) -> dict:
        \"\"\"Run QLoRA training on generated data.\"\"\"
        lora_dir = os.path.join(
            self.config.lora_output_dir,
            f"cycle_{self.state.cycle_number:04d}"
        )

        # Training config optimized for 15GB VRAM
        train_config = {
            "model_path": self.config.base_model_hf,
            "data_path": data_result["data_path"],
            "output_dir": lora_dir,
            "lora_r": self.config.lora_rank,
            "lora_alpha": self.config.lora_alpha,
            "lr": self.config.learning_rate,
            "max_steps": self.config.max_steps,
            "per_device_batch_size": self.config.batch_size,
            "gradient_accumulation": self.config.gradient_accumulation,
            # 15GB VRAM optimizations
            "quantization": "nf4",
            "gradient_checkpointing": True,
            "optim": "paged_adamw_8bit",
            "bf16": True,
            "max_seq_length": 2048,
        }

        log.info(f"  Training LoRA: r={self.config.lora_rank}, "
                 f"steps={self.config.max_steps}, "
                 f"pairs={data_result['total_pairs']}")

        # Run training (delegates to QLoRA pipeline from p401)
        start = time.time()
        train_loss = self._run_qlora_training(train_config)
        elapsed = time.time() - start

        self.state.total_pairs_trained += data_result["total_pairs"]

        return {
            "lora_path": lora_dir,
            "final_loss": train_loss,
            "training_time_sec": elapsed,
            "pairs_trained": data_result["total_pairs"],
        }

    def _phase_merge_export(self, train_result: dict) -> dict:
        \"\"\"Merge LoRA into base model and export GGUF.\"\"\"
        merged_dir = os.path.join(
            self.config.merged_output_dir,
            f"cycle_{self.state.cycle_number:04d}"
        )
        gguf_path = os.path.join(merged_dir, "model-Q4_K_M.gguf")

        log.info(f"  Merging LoRA and exporting GGUF...")

        # Step 1: Merge LoRA with scaling to prevent forgetting
        merge_ratio = 0.85  # Conservative merge
        self._merge_lora(
            base_model=self.config.base_model_hf,
            lora_path=train_result["lora_path"],
            output_dir=merged_dir,
            merge_ratio=merge_ratio,
        )

        # Step 2: Convert to GGUF
        self._convert_to_gguf(merged_dir, gguf_path)

        # Step 3: Clean up intermediate files
        hf_dir = os.path.join(merged_dir, "merged_hf")
        fp16_path = os.path.join(merged_dir, "merged-f16.gguf")
        for path in [hf_dir, fp16_path]:
            if os.path.exists(path):
                import shutil
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.unlink(path)

        return {
            "gguf_path": gguf_path,
            "merge_ratio": merge_ratio,
        }

    def _phase_validate(self, export_result: dict) -> dict:
        \"\"\"Validate the new model against the old one.\"\"\"
        new_gguf = export_result["gguf_path"]

        # Swap to new model for benchmarking
        old_gguf = self.config.current_gguf
        self._swap_model(new_gguf)

        # Re-run benchmarks
        new_scores = {}
        for skill_name, benchmark_fn in self.benchmarks.items():
            new_scores[skill_name] = benchmark_fn()

        new_overall = sum(new_scores.values()) / max(1, len(new_scores))
        old_overall = self.state.current_benchmark_score
        improvement = new_overall - old_overall

        # Check for regression
        regressions = {
            skill: self.state.skill_scores.get(skill, 0) - new_scores[skill]
            for skill in new_scores
            if new_scores[skill] < self.state.skill_scores.get(skill, 0) - 0.01
        }

        # Decision: accept or rollback
        accept = (
            improvement >= self.config.min_improvement
            and all(r < self.config.max_regression for r in regressions.values())
        )

        if accept:
            log.info(f"  ACCEPTED: +{improvement:.3f} improvement")
            self.state.current_benchmark_score = new_overall
            self.state.skill_scores = new_scores
            self.config.current_gguf = new_gguf
            if new_overall > self.state.best_benchmark_score:
                self.state.best_benchmark_score = new_overall
                self.state.best_gguf_path = new_gguf
        else:
            log.info(f"  REJECTED: improvement={improvement:.3f}, "
                     f"regressions={regressions}")
            self._swap_model(old_gguf)  # Rollback

        self.state.history.append({
            "cycle": self.state.cycle_number,
            "old_score": old_overall,
            "new_score": new_overall,
            "improvement": improvement,
            "accepted": accept,
            "regressions": regressions,
            "timestamp": datetime.now().isoformat(),
        })

        return {
            "accepted": accept,
            "improvement": improvement,
            "new_score": new_overall,
            "old_score": old_overall,
            "regressions": regressions,
            "new_scores": new_scores,
        }

    # === Helper Methods (delegate to subsystems) ===

    def _generate_skill_pairs(self, skill: str, n: int) -> list[dict]:
        \"\"\"Generate training pairs for a specific skill.\"\"\"
        # Delegates to problem generators from p400, p405
        return [{"prompt": f"Practice {skill}", "response": "..."}] * n

    def _get_replay_pairs(self, n: int) -> list[dict]:
        \"\"\"Get replay pairs from previous cycles.\"\"\"
        # Load best pairs from previous cycles
        replay = []
        data_dir = Path(self.config.training_data_dir)
        for f in sorted(data_dir.glob("cycle_*.jsonl"), reverse=True):
            with open(f) as fh:
                for line in fh:
                    pair = json.loads(line)
                    if pair.get("quality", 0.5) >= 0.8:
                        replay.append(pair)
                    if len(replay) >= n:
                        return replay
        return replay

    def _run_qlora_training(self, config: dict) -> float:
        \"\"\"Run QLoRA training. Returns final loss.\"\"\"
        # Delegates to training pipeline from p401
        return 0.5  # Placeholder

    def _merge_lora(self, base_model: str, lora_path: str,
                     output_dir: str, merge_ratio: float):
        \"\"\"Merge LoRA adapter into base model.\"\"\"
        # Delegates to merge pipeline from p403
        pass

    def _convert_to_gguf(self, model_dir: str, gguf_path: str):
        \"\"\"Convert HF model to GGUF.\"\"\"
        # Delegates to GGUF converter from p403
        pass

    def _swap_model(self, gguf_path: str):
        \"\"\"Hot-swap the inference model.\"\"\"
        import requests
        # In production: restart llama-server with new model
        # Or use the model switching API if available
        log.info(f"  Swapping model to: {gguf_path}")

    def _benchmark_python_basics(self) -> float:
        return self._run_benchmark("python_basics")

    def _benchmark_algorithms(self) -> float:
        return self._run_benchmark("algorithms")

    def _benchmark_system_design(self) -> float:
        return self._run_benchmark("system_design")

    def _benchmark_debugging(self) -> float:
        return self._run_benchmark("debugging")

    def _benchmark_code_generation(self) -> float:
        return self._run_benchmark("code_generation")

    def _benchmark_self_knowledge(self) -> float:
        return self._run_benchmark("self_knowledge")

    def _run_benchmark(self, category: str) -> float:
        \"\"\"Run a benchmark category and return score 0-1.\"\"\"
        # Placeholder: real implementation generates test prompts,
        # runs inference, executes code, scores results
        return 0.5

    def _log_cycle_summary(self, result: dict):
        \"\"\"Log a human-readable cycle summary.\"\"\"
        v = result["phases"]["validate"]
        log.info(f"--- Cycle {result['cycle']} Summary ---")
        log.info(f"  Score: {v['old_score']:.3f} -> {v['new_score']:.3f} "
                 f"({'ACCEPTED' if v['accepted'] else 'REJECTED'})")
        log.info(f"  Improvement: {v['improvement']:+.3f}")
        log.info(f"  Total pairs trained: {self.state.total_pairs_trained}")
        log.info(f"  Best score ever: {self.state.best_benchmark_score:.3f}")


# === Entry Point: "Get Smarter" ===

def get_smarter(config_path: str = "training/config.json"):
    \"\"\"The single command to make the AI smarter.

    This is what gets called when the user says 'get smarter'.
    It loads config, runs one improvement cycle, and reports results.
    \"\"\"
    # Load or create config
    if os.path.exists(config_path):
        with open(config_path) as f:
            cfg_dict = json.load(f)
        config = SmartConfig(**cfg_dict)
    else:
        config = SmartConfig(
            base_model_hf="/opt/models/qwen3.5-7b",
            current_gguf="/opt/models/qwen3.5-7b-Q4_K_M.gguf",
        )

    orchestrator = GetSmarter(config)
    result = orchestrator.run()

    accepted = result["phases"]["validate"]["accepted"]
    improvement = result["phases"]["validate"]["improvement"]

    if accepted:
        print(f"Got smarter! Score improved by {improvement:+.3f}")
    else:
        print(f"Cycle complete but no improvement ({improvement:+.3f})")
        print("Will try different approach next cycle.")

    return result


# Call it:
# get_smarter()
```

Key patterns:
1. **5-phase pipeline** -- evaluate -> generate data -> train -> export -> validate; each phase independent
2. **Weakness targeting** -- benchmarks identify weakest skills; training data focuses on those areas
3. **Rollback safety** -- if new model regresses on any skill beyond threshold, reject and keep old model
4. **Replay buffer** -- mix 20-25% old high-quality pairs to prevent catastrophic forgetting
5. **Convergence detection** -- stop after 3 cycles without improvement; avoid wasting compute
6. **Single entry point** -- `get_smarter()` is all the user needs to call; everything else is automated"""
    ),
    (
        "local-ai/self-improvement-monitoring",
        "Show monitoring and dashboarding for AI self-improvement: track learning curves, detect plateaus, compare model versions, and visualize skill progression.",
        """Self-improvement monitoring and analytics:

```python
import json
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from collections import defaultdict


@dataclass
class ModelVersion:
    \"\"\"A snapshot of model performance at a point in time.\"\"\"
    version_id: str
    cycle_number: int
    gguf_path: str
    overall_score: float
    skill_scores: dict[str, float]
    training_pairs: int
    timestamp: str
    accepted: bool = True


class ImprovementTracker:
    \"\"\"Track and analyze self-improvement progress over time.\"\"\"

    def __init__(self, log_dir: str = "training/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.versions: list[ModelVersion] = []
        self._load_history()

    def _load_history(self):
        history_file = self.log_dir / "improvement_history.jsonl"
        if history_file.exists():
            with open(history_file) as f:
                for line in f:
                    data = json.loads(line)
                    self.versions.append(ModelVersion(**data))

    def record_version(self, version: ModelVersion):
        self.versions.append(version)
        with open(self.log_dir / "improvement_history.jsonl", "a") as f:
            f.write(json.dumps(vars(version)) + "\\n")

    def learning_curve(self) -> list[dict]:
        \"\"\"Overall learning curve across all cycles.\"\"\"
        return [
            {
                "cycle": v.cycle_number,
                "score": v.overall_score,
                "pairs_trained": v.training_pairs,
                "accepted": v.accepted,
            }
            for v in self.versions
        ]

    def skill_progression(self, skill_name: str) -> list[dict]:
        \"\"\"Track a specific skill's improvement over time.\"\"\"
        return [
            {
                "cycle": v.cycle_number,
                "score": v.skill_scores.get(skill_name, 0),
            }
            for v in self.versions
            if skill_name in v.skill_scores
        ]

    def detect_plateau(self, window: int = 5,
                        threshold: float = 0.01) -> dict:
        \"\"\"Detect if learning has plateaued.

        Returns analysis of recent improvement trend.
        \"\"\"
        if len(self.versions) < window:
            return {"plateau": False, "reason": "Not enough data"}

        recent = self.versions[-window:]
        scores = [v.overall_score for v in recent]
        trend = scores[-1] - scores[0]
        variance = max(scores) - min(scores)

        is_plateau = abs(trend) < threshold and variance < threshold * 2

        return {
            "plateau": is_plateau,
            "trend": trend,
            "variance": variance,
            "recent_scores": scores,
            "recommendation": self._plateau_recommendation(is_plateau, trend),
        }

    def _plateau_recommendation(self, is_plateau: bool, trend: float) -> str:
        if not is_plateau:
            if trend > 0:
                return "Learning actively. Continue current strategy."
            else:
                return "Regressing. Check data quality and merge ratio."

        return (
            "Plateau detected. Try:\\n"
            "1. Increase LoRA rank (more capacity)\\n"
            "2. Switch to harder problems (curriculum shift)\\n"
            "3. Add new data sources (broader knowledge)\\n"
            "4. Try different learning rate\\n"
            "5. Increase training steps per cycle"
        )

    def compare_versions(self, v1_idx: int, v2_idx: int) -> dict:
        \"\"\"Compare two model versions skill by skill.\"\"\"
        ver1 = self.versions[v1_idx]
        ver2 = self.versions[v2_idx]

        comparison = {
            "version_1": ver1.version_id,
            "version_2": ver2.version_id,
            "overall_delta": ver2.overall_score - ver1.overall_score,
            "skill_deltas": {},
            "improved_skills": [],
            "regressed_skills": [],
        }

        all_skills = set(ver1.skill_scores) | set(ver2.skill_scores)
        for skill in all_skills:
            s1 = ver1.skill_scores.get(skill, 0)
            s2 = ver2.skill_scores.get(skill, 0)
            delta = s2 - s1
            comparison["skill_deltas"][skill] = {
                "before": s1, "after": s2, "delta": delta,
            }
            if delta > 0.02:
                comparison["improved_skills"].append(skill)
            elif delta < -0.02:
                comparison["regressed_skills"].append(skill)

        return comparison

    def generate_report(self) -> str:
        \"\"\"Generate a human-readable improvement report.\"\"\"
        if not self.versions:
            return "No training history yet."

        latest = self.versions[-1]
        first = self.versions[0]

        lines = [
            "=== AI Self-Improvement Report ===",
            f"Total cycles: {len(self.versions)}",
            f"Starting score: {first.overall_score:.3f}",
            f"Current score: {latest.overall_score:.3f}",
            f"Total improvement: {latest.overall_score - first.overall_score:+.3f}",
            f"Total pairs trained: {sum(v.training_pairs for v in self.versions)}",
            "",
            "Skill Breakdown:",
        ]

        for skill, score in sorted(latest.skill_scores.items(),
                                      key=lambda x: x[1]):
            first_score = first.skill_scores.get(skill, 0)
            delta = score - first_score
            bar = "#" * int(score * 20)
            lines.append(f"  {skill:20s} {bar:20s} {score:.2f} ({delta:+.2f})")

        plateau = self.detect_plateau()
        lines.extend(["", f"Plateau status: {'YES' if plateau['plateau'] else 'No'}",
                       f"Recommendation: {plateau['recommendation']}"])

        return "\\n".join(lines)


# Usage
tracker = ImprovementTracker("training/logs")

# After each cycle, record the version
tracker.record_version(ModelVersion(
    version_id="v1", cycle_number=1,
    gguf_path="/opt/models/v1.gguf",
    overall_score=0.45,
    skill_scores={"python_basics": 0.6, "algorithms": 0.3, "debugging": 0.5},
    training_pairs=200, timestamp="2026-03-05T10:00:00",
))

print(tracker.generate_report())
print(tracker.detect_plateau())
```

Key patterns:
1. **Version tracking** -- every training cycle produces a versioned snapshot with full scores
2. **Learning curve** -- plot overall score vs cycles; detect diminishing returns
3. **Plateau detection** -- sliding window over recent scores; recommend strategy changes when stuck
4. **Skill-level comparison** -- compare any two versions to see which skills improved or regressed
5. **Actionable recommendations** -- when plateau detected, suggest concrete next steps (rank, LR, data)"""
    ),
]
