"""Self-training loop — the complete 'get smarter' pipeline for local AI.

This is the master batch: how a local AI on <=15GB VRAM can autonomously
improve itself through iterative code practice, self-evaluation, and
targeted LoRA fine-tuning.
"""

PAIRS = [
    (
        "self-improvement/get-smarter-pipeline",
        "I want my local AI to be able to make itself smarter autonomously. Show the complete self-training loop: generate practice problems, attempt solutions, evaluate quality, extract training signal, do LoRA fine-tuning, and repeat. This should work on a single GPU with 15GB VRAM or less.",
        """## The Complete 'Get Smarter' Loop for Local AI

The core insight: **an AI can improve itself by practicing coding problems,
evaluating its own solutions against execution results, and fine-tuning on
its successes.** This is the same way humans learn — practice, get feedback,
internalize what works.

### Architecture

```
[Generate Challenge] -> [Attempt Solution] -> [Execute & Test]
        ^                                           |
        |                                    [Score Result]
        |                                           |
        |                                   [Extract Training Pair]
        |                                           |
        |                                    [Accumulate Batch]
        |                                           |
        +-------- [LoRA Fine-tune] <----------------+
```

### Full Implementation

```python
import subprocess
import json
import time
import random
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PracticeProblem:
    category: str          # "algorithms", "data_structures", "system_design"
    difficulty: str        # "easy", "medium", "hard"
    description: str       # Natural language problem statement
    test_code: str         # Python test cases to verify solution
    hints: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class SolutionAttempt:
    problem: PracticeProblem
    solution_code: str
    passed_tests: bool
    test_output: str
    execution_time_ms: float
    score: float           # 0.0 to 1.0
    reasoning: str         # Model's chain of thought


@dataclass
class TrainingPair:
    instruction: str
    response: str
    score: float
    source: str            # "self_practice", "self_correction", "synthesis"


class SelfTrainingLoop:
    \"\"\"The master self-improvement engine.

    Runs on a single GPU with <=15GB VRAM by:
    1. Using the GGUF model for inference (llama.cpp, ~4-8GB)
    2. Loading the base model for LoRA training (QLoRA 4-bit, ~6-10GB)
    3. Never running both simultaneously
    \"\"\"

    def __init__(self, model_path: str, base_model_path: str,
                 lora_output_dir: str = "lora_adapters",
                 training_data_dir: str = "self_training_data"):
        self.model_path = model_path          # GGUF for inference
        self.base_model_path = base_model_path  # HF model for training
        self.lora_dir = Path(lora_output_dir)
        self.data_dir = Path(training_data_dir)
        self.lora_dir.mkdir(exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)

        self.training_pairs: list[TrainingPair] = []
        self.iteration = 0
        self.improvement_log: list[dict] = []

    def run_improvement_cycle(self, n_problems: int = 50,
                                min_pairs_to_train: int = 30):
        \"\"\"One full cycle of self-improvement.\"\"\"
        print(f"=== Improvement Cycle {self.iteration} ===")

        # Phase 1: Generate diverse practice problems
        problems = self.generate_problems(n_problems)

        # Phase 2: Attempt solutions with chain-of-thought
        attempts = []
        for prob in problems:
            attempt = self.attempt_solution(prob)
            attempts.append(attempt)

        # Phase 3: Score and extract training signal
        good_pairs = []
        failed_problems = []
        for attempt in attempts:
            if attempt.score >= 0.8:
                # Successful solution -> training pair
                pair = TrainingPair(
                    instruction=attempt.problem.description,
                    response=attempt.solution_code,
                    score=attempt.score,
                    source="self_practice",
                )
                good_pairs.append(pair)
            else:
                failed_problems.append(attempt)

        # Phase 4: Self-correction on failures (2nd attempt)
        for failed in failed_problems:
            corrected = self.self_correct(failed)
            if corrected.score >= 0.7:
                pair = TrainingPair(
                    instruction=failed.problem.description,
                    response=corrected.solution_code,
                    score=corrected.score,
                    source="self_correction",
                )
                good_pairs.append(pair)

        # Phase 5: Generate synthesis problems (harder variants)
        if len(good_pairs) > 10:
            synthesis_pairs = self.generate_harder_variants(
                [p for p in good_pairs if p.score >= 0.9]
            )
            good_pairs.extend(synthesis_pairs)

        self.training_pairs.extend(good_pairs)
        print(f"  Generated {len(good_pairs)} training pairs "
              f"({len(self.training_pairs)} total)")

        # Phase 6: LoRA fine-tune if enough pairs
        if len(self.training_pairs) >= min_pairs_to_train:
            self.do_lora_finetune()
            self.training_pairs = []  # Reset for next cycle

        # Phase 7: Evaluate improvement
        score = self.evaluate_current_level()
        self.improvement_log.append({
            "iteration": self.iteration,
            "pairs_generated": len(good_pairs),
            "eval_score": score,
            "timestamp": time.time(),
        })
        self.iteration += 1
        return score

    def generate_problems(self, n: int) -> list[PracticeProblem]:
        \"\"\"Generate diverse coding challenges using the model itself.\"\"\"
        categories = [
            ("algorithms", "sorting, searching, graph traversal, dynamic programming"),
            ("data_structures", "trees, heaps, hash maps, linked lists, tries"),
            ("system_design", "caching, rate limiting, pub/sub, connection pools"),
            ("debugging", "find and fix bugs in given code"),
            ("optimization", "make slow code faster, reduce memory usage"),
            ("api_design", "design clean APIs, handle edge cases"),
        ]

        problems = []
        for _ in range(n):
            cat, desc = random.choice(categories)
            difficulty = random.choices(
                ["easy", "medium", "hard"],
                weights=[0.3, 0.5, 0.2]
            )[0]

            prompt = f\"\"\"Generate a coding problem.
Category: {cat} ({desc})
Difficulty: {difficulty}

Output JSON:
{{"description": "problem statement with examples",
  "test_code": "python code with assert statements to verify solution",
  "hints": ["hint1", "hint2"],
  "tags": ["tag1", "tag2"]}}\"\"\"

            response = self.inference(prompt)
            try:
                data = json.loads(response)
                problems.append(PracticeProblem(
                    category=cat, difficulty=difficulty,
                    description=data["description"],
                    test_code=data["test_code"],
                    hints=data.get("hints", []),
                    tags=data.get("tags", []),
                ))
            except (json.JSONDecodeError, KeyError):
                continue  # Skip malformed generations

        return problems

    def attempt_solution(self, problem: PracticeProblem) -> SolutionAttempt:
        \"\"\"Solve a problem with chain-of-thought reasoning.\"\"\"
        prompt = f\"\"\"Solve this coding problem step by step.

Problem: {problem.description}

Think through your approach:
1. Understand the problem
2. Consider edge cases
3. Choose an algorithm
4. Write clean, correct code

Respond with your reasoning followed by:
```python
# Your solution here
```\"\"\"

        response = self.inference(prompt)
        code = self.extract_code(response)

        # Execute and test
        passed, output, exec_time = self.execute_with_tests(
            code, problem.test_code
        )

        score = 1.0 if passed else 0.0
        # Partial credit for code that runs but fails some tests
        if not passed and "AssertionError" in output:
            # Count passing assertions
            total = problem.test_code.count("assert")
            failed = output.count("AssertionError")
            if total > 0:
                score = max(0, (total - failed) / total)

        return SolutionAttempt(
            problem=problem,
            solution_code=code,
            passed_tests=passed,
            test_output=output,
            execution_time_ms=exec_time,
            score=score,
            reasoning=response,
        )

    def self_correct(self, failed: SolutionAttempt) -> SolutionAttempt:
        \"\"\"Analyze failure and try again — learning from mistakes.\"\"\"
        prompt = f\"\"\"Your previous solution had errors. Learn from them.

Problem: {failed.problem.description}

Your previous attempt:
```python
{failed.solution_code}
```

Error output:
{failed.test_output[:500]}

Analyze what went wrong, then write a corrected solution.
Focus on the specific failure — don't start from scratch unless necessary.\"\"\"

        response = self.inference(prompt)
        code = self.extract_code(response)
        passed, output, exec_time = self.execute_with_tests(
            code, failed.problem.test_code
        )

        score = 1.0 if passed else 0.3  # Even failed corrections have value
        return SolutionAttempt(
            problem=failed.problem,
            solution_code=code,
            passed_tests=passed,
            test_output=output,
            execution_time_ms=exec_time,
            score=score,
            reasoning=response,
        )

    def generate_harder_variants(self, solved: list[TrainingPair],
                                   n_per: int = 2) -> list[TrainingPair]:
        \"\"\"Take problems you solved and make harder versions.

        This is evolution-based curriculum learning:
        easy problems -> harder variants -> even harder -> ...
        \"\"\"
        variants = []
        for pair in solved[:10]:  # Top 10 solutions
            prompt = f\"\"\"Take this solved coding problem and create a harder
variant that tests deeper understanding.

Original problem: {pair.instruction}
Original solution: {pair.response}

Make it harder by:
- Adding constraints (memory limit, time limit)
- Requiring handling of edge cases
- Making the input scale larger
- Adding a twist that requires a different algorithm

Output JSON:
{{"description": "harder problem", "test_code": "assert-based tests"}}\"\"\"

            response = self.inference(prompt)
            try:
                data = json.loads(response)
                harder = PracticeProblem(
                    category="synthesis", difficulty="hard",
                    description=data["description"],
                    test_code=data["test_code"],
                )
                attempt = self.attempt_solution(harder)
                if attempt.score >= 0.7:
                    variants.append(TrainingPair(
                        instruction=data["description"],
                        response=attempt.solution_code,
                        score=attempt.score,
                        source="synthesis",
                    ))
            except (json.JSONDecodeError, KeyError):
                continue

        return variants

    def do_lora_finetune(self):
        \"\"\"LoRA fine-tune on accumulated training pairs.

        Key: this runs AFTER inference is stopped.
        QLoRA 4-bit fits in ~10GB VRAM for 7B model.
        \"\"\"
        # Save training data
        data_path = self.data_dir / f"cycle_{self.iteration}.jsonl"
        with open(data_path, "w") as f:
            for pair in self.training_pairs:
                f.write(json.dumps({
                    "instruction": pair.instruction,
                    "output": pair.response,
                    "score": pair.score,
                    "source": pair.source,
                }) + "\\n")

        # LoRA training config for <=15GB VRAM
        config = {
            "model_name": self.base_model_path,
            "data_path": str(data_path),
            "output_dir": str(self.lora_dir / f"cycle_{self.iteration}"),
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "learning_rate": 2e-4,
            "num_epochs": 3,
            "batch_size": 1,
            "gradient_accumulation": 8,
            "max_seq_length": 2048,
            "quantization": "4bit",  # QLoRA for VRAM efficiency
            "gradient_checkpointing": True,
            "use_flash_attention": True,
        }

        print(f"  Training LoRA on {len(self.training_pairs)} pairs...")
        self.run_training(config)
        print(f"  LoRA saved to {config['output_dir']}")

    def evaluate_current_level(self) -> float:
        \"\"\"Benchmark current model on held-out problems.\"\"\"
        eval_problems = self.generate_problems(20)
        scores = []
        for prob in eval_problems:
            attempt = self.attempt_solution(prob)
            scores.append(attempt.score)
        avg = sum(scores) / max(len(scores), 1)
        print(f"  Eval score: {avg:.2f} ({sum(1 for s in scores if s >= 0.8)}/{len(scores)} passed)")
        return avg

    def execute_with_tests(self, code: str, tests: str) -> tuple:
        \"\"\"Safely execute code + tests in subprocess.\"\"\"
        full_code = code + "\\n\\n" + tests
        try:
            result = subprocess.run(
                ["python3", "-c", full_code],
                capture_output=True, text=True, timeout=10,
            )
            passed = result.returncode == 0
            output = result.stdout + result.stderr
            return passed, output, 0
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT: execution exceeded 10s", 10000

    def extract_code(self, response: str) -> str:
        \"\"\"Extract Python code from model response.\"\"\"
        import re
        match = re.search(r"```python\\n(.*?)```", response, re.DOTALL)
        return match.group(1).strip() if match else response.strip()

    def inference(self, prompt: str) -> str:
        \"\"\"Run inference via llama.cpp server or similar.\"\"\"
        import httpx
        resp = httpx.post("http://localhost:8080/completion", json={
            "prompt": prompt,
            "n_predict": 2048,
            "temperature": 0.7,
            "stop": ["<|end|>", "<|user|>"],
        }, timeout=120)
        return resp.json()["content"]

    def run_training(self, config: dict):
        \"\"\"Execute LoRA training (calls training script).\"\"\"
        config_path = self.data_dir / "train_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        subprocess.run(
            ["python3", "scripts/train_lora.py", "--config", str(config_path)],
            check=True,
        )


# === USAGE ===
# loop = SelfTrainingLoop(
#     model_path="models/qwen3.5-35b-a3b/Qwen3.5-35B-A3B-Q4_K_M.gguf",
#     base_model_path="models/qwen3.5-35b-a3b",
# )
#
# # Run 10 improvement cycles
# for i in range(10):
#     score = loop.run_improvement_cycle(n_problems=50)
#     print(f"Cycle {i}: score = {score:.2f}")
#     if score > 0.95:
#         print("Reached mastery!")
#         break
```

### Why This Works

1. **Practice makes perfect**: The model generates its own problems at increasing
   difficulty, just like a student doing progressively harder exercises.

2. **Execution-based feedback**: Unlike human evaluation, code either runs correctly
   or it doesn't. This gives a clean, objective training signal.

3. **Self-correction teaches debugging**: When a solution fails, the model analyzes
   the error and tries again. The corrected solution becomes training data for
   learning from mistakes.

4. **Evolutionary curriculum**: Solved problems spawn harder variants. The model
   always trains at the edge of its ability.

5. **Fits on consumer hardware**: Inference via GGUF (~8GB), training via QLoRA
   4-bit (~10GB). Never both at once. A 15GB GPU handles it.

### Key Design Decisions

- **Temperature 0.7** for problem generation (diverse) vs 0.2 for solutions (precise)
- **Score threshold 0.8** for training pairs — only learn from good solutions
- **Self-correction as 2nd chance** — lower threshold (0.7) because the debugging
  process itself is valuable training data
- **Synthesis problems** — the hardest, most valuable training signal comes from
  problems the model creates by extending what it already knows"""
    ),
    (
        "self-improvement/training-data-quality",
        "Show how to build a quality filter for self-generated training data: scoring solutions on correctness, efficiency, readability, and novelty. Only high-quality pairs should enter the training set.",
        """## Training Data Quality Filter for Self-Improvement

The model only gets smarter if it trains on GOOD data. Bad training data
makes it worse. Here's how to score and filter self-generated pairs.

```python
import ast
import re
import subprocess
import time
from dataclasses import dataclass


@dataclass
class QualityScore:
    correctness: float    # 0-1: does it pass tests?
    efficiency: float     # 0-1: time/space complexity
    readability: float    # 0-1: clean code practices
    novelty: float        # 0-1: different from existing training data
    overall: float        # weighted combination


class QualityFilter:
    \"\"\"Score training pair quality across multiple dimensions.\"\"\"

    def __init__(self, existing_solutions: list[str] = None):
        self.existing = existing_solutions or []
        self.min_overall = 0.7  # Minimum quality to enter training set

    def score(self, code: str, test_code: str,
              problem: str) -> QualityScore:
        correctness = self._score_correctness(code, test_code)
        efficiency = self._score_efficiency(code, test_code)
        readability = self._score_readability(code)
        novelty = self._score_novelty(code)

        # Weighted: correctness matters most
        overall = (
            correctness * 0.40 +
            efficiency * 0.20 +
            readability * 0.20 +
            novelty * 0.20
        )

        return QualityScore(
            correctness=correctness,
            efficiency=efficiency,
            readability=readability,
            novelty=novelty,
            overall=overall,
        )

    def _score_correctness(self, code: str, test_code: str) -> float:
        \"\"\"Run tests — binary pass/fail with partial credit.\"\"\"
        full = code + "\\n" + test_code
        try:
            result = subprocess.run(
                ["python3", "-c", full],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return 1.0
            # Partial credit: count passing vs failing asserts
            total = test_code.count("assert ")
            fails = result.stderr.count("AssertionError")
            return max(0, (total - fails) / total) if total else 0
        except subprocess.TimeoutExpired:
            return 0.1  # Ran but too slow

    def _score_efficiency(self, code: str, test_code: str) -> float:
        \"\"\"Time the solution and check for obvious inefficiencies.\"\"\"
        full = code + "\\n" + test_code
        try:
            start = time.perf_counter()
            subprocess.run(
                ["python3", "-c", full],
                capture_output=True, timeout=10,
            )
            elapsed = time.perf_counter() - start

            # Score based on execution time
            if elapsed < 0.1:
                return 1.0
            elif elapsed < 1.0:
                return 0.8
            elif elapsed < 5.0:
                return 0.5
            else:
                return 0.2
        except subprocess.TimeoutExpired:
            return 0.0

    def _score_readability(self, code: str) -> float:
        \"\"\"Score code quality heuristics.\"\"\"
        score = 1.0

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 0.0

        lines = code.split("\\n")

        # Deduct for very long functions (>50 lines)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_lines = node.end_lineno - node.lineno
                if func_lines > 50:
                    score -= 0.2

        # Deduct for no functions (just raw script)
        funcs = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not funcs and len(lines) > 15:
            score -= 0.2

        # Deduct for single-letter variables (except i, j, k, n, x, y)
        allowed_short = {"i", "j", "k", "n", "x", "y", "e", "f", "_"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and len(node.id) == 1:
                if node.id not in allowed_short:
                    score -= 0.05

        # Deduct for excessive nesting (>4 levels)
        max_depth = self._max_indent(lines)
        if max_depth > 4:
            score -= 0.1 * (max_depth - 4)

        # Bonus for docstrings
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant)):
                    score += 0.05

        return max(0, min(1, score))

    def _score_novelty(self, code: str) -> float:
        \"\"\"How different is this from existing training solutions?\"\"\"
        if not self.existing:
            return 1.0

        # Simple token overlap check
        code_tokens = set(re.findall(r'\\w+', code.lower()))
        max_overlap = 0
        for existing in self.existing:
            existing_tokens = set(re.findall(r'\\w+', existing.lower()))
            if not code_tokens or not existing_tokens:
                continue
            overlap = len(code_tokens & existing_tokens) / len(code_tokens)
            max_overlap = max(max_overlap, overlap)

        # Novelty = inverse of max overlap
        return max(0, 1 - max_overlap + 0.3)  # Bias toward acceptance

    def _max_indent(self, lines: list[str]) -> int:
        max_depth = 0
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                depth = (len(line) - len(stripped)) // 4
                max_depth = max(max_depth, depth)
        return max_depth

    def filter_batch(self, pairs: list[dict]) -> list[dict]:
        \"\"\"Filter a batch of training pairs to quality threshold.\"\"\"
        accepted = []
        rejected = []
        for pair in pairs:
            score = self.score(
                pair["response"], pair.get("test_code", ""),
                pair["instruction"],
            )
            if score.overall >= self.min_overall:
                pair["quality_score"] = score.overall
                accepted.append(pair)
            else:
                rejected.append((pair["instruction"][:50], score))

        print(f"Quality filter: {len(accepted)}/{len(pairs)} accepted "
              f"({len(accepted)/max(len(pairs),1)*100:.0f}%)")
        return accepted
```

### Quality Thresholds by Source

| Source | Min Score | Rationale |
|--------|----------|-----------|
| Self-practice (pass) | 0.8 | High bar — only train on clean solutions |
| Self-correction | 0.7 | Debugging process is valuable even if imperfect |
| Synthesis (harder) | 0.75 | Higher difficulty, slightly lower bar |
| External problems | 0.85 | Unknown quality — be strict |

### Key Insights

1. **Correctness dominates** (40% weight) — wrong code teaches wrong patterns
2. **Novelty prevents collapse** — without it, the model memorizes its own outputs
3. **AST-based readability** — doesn't rely on subjective judgment, uses structural metrics
4. **Batch filtering** — accept/reject entire pairs, not partial credit in training
5. **Existing solution tracking** — maintains set of seen solutions to promote diversity"""
    ),
    (
        "self-improvement/progressive-difficulty",
        "Show how a local AI can automatically generate progressively harder problems for itself, creating an adaptive curriculum that always trains at the edge of its abilities.",
        """## Adaptive Curriculum: Always Train at the Edge of Ability

The AI should never practice problems it already knows how to solve perfectly,
and never attempt problems so hard it learns nothing. The sweet spot is
problems where it succeeds ~60-70% of the time.

```python
import random
import json
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path


@dataclass
class DifficultyProfile:
    category: str
    current_level: float = 0.5     # 0-1 difficulty scale
    success_rate: float = 0.5      # Recent success rate
    attempts: int = 0
    successes: int = 0
    history: list[tuple] = field(default_factory=list)  # (difficulty, passed)


class AdaptiveCurriculum:
    \"\"\"Generate problems that adapt to the model's current ability.

    Core idea: track success rate per category, adjust difficulty
    to maintain ~65% success rate (optimal learning zone).
    \"\"\"

    TARGET_SUCCESS_RATE = 0.65   # Zone of proximal development
    ADJUSTMENT_RATE = 0.1       # How fast difficulty changes
    WINDOW_SIZE = 20            # Recent history for rate calculation

    def __init__(self):
        self.profiles: dict[str, DifficultyProfile] = {}
        self.problem_templates = self._load_templates()

    def get_next_problem(self, category: str = None) -> dict:
        \"\"\"Generate a problem at the right difficulty for current level.\"\"\"
        if category is None:
            # Pick category with lowest mastery
            category = self._weakest_category()

        profile = self._get_profile(category)
        difficulty = profile.current_level

        # Generate problem at target difficulty
        problem = self._generate_at_difficulty(category, difficulty)
        return problem

    def record_result(self, category: str, difficulty: float,
                       passed: bool):
        \"\"\"Update difficulty based on result.\"\"\"
        profile = self._get_profile(category)
        profile.attempts += 1
        if passed:
            profile.successes += 1
        profile.history.append((difficulty, passed))

        # Keep only recent history
        if len(profile.history) > self.WINDOW_SIZE:
            profile.history = profile.history[-self.WINDOW_SIZE:]

        # Calculate recent success rate
        recent = profile.history[-self.WINDOW_SIZE:]
        profile.success_rate = sum(1 for _, p in recent if p) / len(recent)

        # Adjust difficulty
        if profile.success_rate > self.TARGET_SUCCESS_RATE + 0.1:
            # Too easy — increase difficulty
            profile.current_level = min(1.0,
                profile.current_level + self.ADJUSTMENT_RATE)
        elif profile.success_rate < self.TARGET_SUCCESS_RATE - 0.1:
            # Too hard — decrease difficulty
            profile.current_level = max(0.1,
                profile.current_level - self.ADJUSTMENT_RATE)

    def _weakest_category(self) -> str:
        \"\"\"Find the category where the model needs most practice.\"\"\"
        if not self.profiles:
            return random.choice(list(self.problem_templates.keys()))

        # Weighted selection: lower mastery = higher weight
        categories = list(self.profiles.items())
        weights = [1.0 - p.success_rate + 0.1 for _, p in categories]
        return random.choices(
            [c for c, _ in categories], weights=weights, k=1
        )[0]

    def _generate_at_difficulty(self, category: str,
                                  difficulty: float) -> dict:
        \"\"\"Map difficulty float to concrete problem parameters.\"\"\"
        templates = self.problem_templates.get(category, [])
        if not templates:
            return self._fallback_problem(category, difficulty)

        # Scale parameters based on difficulty
        constraints = self._difficulty_to_constraints(difficulty)

        template = random.choice(templates)
        return {
            "category": category,
            "difficulty": difficulty,
            "description": template["base"].format(**constraints),
            "test_code": template["tests"].format(**constraints),
            "constraints": constraints,
        }

    def _difficulty_to_constraints(self, d: float) -> dict:
        \"\"\"Convert difficulty 0-1 to problem parameters.\"\"\"
        return {
            "n": int(10 + d * 990),            # Input size: 10 to 1000
            "time_limit": max(0.1, 2.0 - d * 1.8),  # Tighter time limits
            "edge_cases": int(d * 5),           # More edge cases at higher difficulty
            "num_constraints": int(1 + d * 4),  # More constraints
        }

    def get_mastery_report(self) -> dict:
        \"\"\"Report current mastery across all categories.\"\"\"
        return {
            cat: {
                "level": p.current_level,
                "success_rate": p.success_rate,
                "attempts": p.attempts,
                "mastered": p.success_rate > 0.85 and p.current_level > 0.7,
            }
            for cat, p in self.profiles.items()
        }

    def _get_profile(self, category: str) -> DifficultyProfile:
        if category not in self.profiles:
            self.profiles[category] = DifficultyProfile(category=category)
        return self.profiles[category]

    def _load_templates(self) -> dict:
        \"\"\"Problem templates by category with difficulty scaling.\"\"\"
        return {
            "algorithms": [
                {
                    "base": "Implement a function that finds the {num_constraints} "
                            "most frequent elements in a list of {n} integers. "
                            "Must run in O(n log k) time.",
                    "tests": "# Test with n={n} elements\\n"
                             "import random\\n"
                             "data = [random.randint(1,100) for _ in range({n})]\\n"
                             "result = solution(data, {num_constraints})\\n"
                             "assert len(result) == {num_constraints}\\n",
                },
            ],
            "data_structures": [
                {
                    "base": "Implement an LRU cache with capacity {n} that supports "
                            "get() and put() in O(1) time. Handle {edge_cases} edge cases.",
                    "tests": "cache = LRUCache({n})\\n"
                             "cache.put(1, 1)\\n"
                             "cache.put(2, 2)\\n"
                             "assert cache.get(1) == 1\\n",
                },
            ],
        }

    def _fallback_problem(self, category: str, difficulty: float) -> dict:
        return {
            "category": category,
            "difficulty": difficulty,
            "description": f"Write a {category} solution (difficulty: {difficulty:.1f})",
            "test_code": "assert True  # placeholder",
        }
```

### The Learning Zone Diagram

```
Success Rate
    1.0  |  ████████  Too Easy (boring, no learning)
         |  ████████
    0.8  |  --------  Upper bound
         |  ░░░░░░░░  OPTIMAL ZONE (0.55 - 0.75)
    0.65 |  ░░░░░░░░  Target: 65% success rate
         |  ░░░░░░░░
    0.5  |  --------  Lower bound
         |            Too Hard (frustrating, no learning)
    0.0  |
         +----------->  Difficulty
```

### Key Insights

1. **Zone of proximal development** — 65% success rate is where learning is maximized
2. **Per-category tracking** — model might be great at algorithms but weak at system design
3. **Automatic adjustment** — difficulty increases when model succeeds, decreases when it fails
4. **Weakest-first selection** — prioritize categories with lowest mastery for balanced growth
5. **Constraint scaling** — difficulty maps to concrete parameters (input size, time limits, edge cases)"""
    ),
    (
        "self-improvement/deep-thinking-training",
        "Show how to train a local AI to think more deeply: generating chain-of-thought reasoning, tree-of-thought exploration, and metacognitive self-reflection on its own problem-solving process.",
        """## Training Deep Thinking: From Shallow to Deep Reasoning

The difference between a mediocre AI and a great one is depth of reasoning.
Here's how to train your local model to think before it answers, explore
multiple approaches, and reflect on its own thinking.

```python
import json
import re
from dataclasses import dataclass, field


@dataclass
class ThoughtNode:
    thought: str
    confidence: float
    children: list = field(default_factory=list)
    evaluation: str = ""
    is_terminal: bool = False


class DeepThinkingTrainer:
    \"\"\"Generate training data that teaches deeper reasoning.\"\"\"

    def __init__(self, model_fn):
        self.model = model_fn

    def generate_cot_pair(self, problem: str) -> dict:
        \"\"\"Generate a chain-of-thought training pair.

        The model solves the problem step by step, then we extract
        the reasoning chain as training data.
        \"\"\"
        # Step 1: Get the model to think step by step
        response = self.model(f\"\"\"Solve this problem. Think carefully step by step.
For each step, explain WHY you're doing it, not just what.

Problem: {problem}

Format your thinking as:

## Step 1: [Understanding]
[What is the problem really asking?]

## Step 2: [Approach]
[What approaches could work? Why choose this one?]

## Step 3: [Edge Cases]
[What could go wrong? What are the tricky inputs?]

## Step 4: [Implementation]
[Write the solution with clear logic]

## Step 5: [Verification]
[Test your solution mentally with examples]

## Answer
[Final clean solution]
\"\"\")

        return {
            "instruction": problem,
            "response": response,
            "type": "chain_of_thought",
        }

    def generate_tot_pair(self, problem: str,
                            breadth: int = 3, depth: int = 3) -> dict:
        \"\"\"Generate tree-of-thought training pair.

        Explore multiple solution paths, evaluate each,
        then choose the best one.
        \"\"\"
        root = ThoughtNode(thought="Initial problem analysis", confidence=1.0)

        # Generate multiple initial approaches
        approaches_response = self.model(f\"\"\"For this problem, brainstorm
{breadth} completely different approaches. For each, briefly describe
the approach and rate your confidence (0-1) that it will work.

Problem: {problem}

Format:
Approach 1: [description] (confidence: X.X)
Approach 2: [description] (confidence: X.X)
Approach 3: [description] (confidence: X.X)
\"\"\")

        approaches = self._parse_approaches(approaches_response)

        best_path = None
        best_score = -1

        for approach in approaches:
            # Develop each approach further
            development = self.model(f\"\"\"Develop this approach to solve the problem.

Problem: {problem}
Approach: {approach['description']}

Write the full solution using this approach.
After writing it, evaluate: what are its strengths and weaknesses?
Rate the solution quality 0-10.
\"\"\")

            score = self._extract_score(development)
            if score > best_score:
                best_score = score
                best_path = {
                    "approach": approach["description"],
                    "development": development,
                    "score": score,
                }

        # Build the training response that shows the thinking process
        training_response = f\"\"\"Let me explore multiple approaches before solving this.

**Approach Analysis:**
{approaches_response}

**Best Approach: {best_path['approach']}**

**Detailed Solution:**
{best_path['development']}

**Why this approach won:** It scored {best_score}/10 compared to alternatives.
\"\"\"

        return {
            "instruction": problem,
            "response": training_response,
            "type": "tree_of_thought",
        }

    def generate_metacognition_pair(self, problem: str) -> dict:
        \"\"\"Generate self-reflection training pair.

        The model solves a problem, then reflects on its own
        problem-solving process. This teaches metacognition.
        \"\"\"
        # First, solve the problem
        solution = self.model(f"Solve this problem: {problem}")

        # Then, reflect on the solving process
        reflection = self.model(f\"\"\"You just solved this problem:

Problem: {problem}
Your solution: {solution}

Now reflect on your problem-solving process:

1. **What was my first instinct?** Was it correct or did I need to revise?
2. **Where did I get stuck?** What helped me get unstuck?
3. **What assumptions did I make?** Were they all valid?
4. **What would I do differently?** If I solved this again, what would I change?
5. **What general principle can I extract?** What lesson applies to future problems?
6. **How confident am I?** Rate 1-10 and explain why.
\"\"\")

        training_response = f\"\"\"Let me solve this and then reflect on my process.

**Solution:**
{solution}

**Self-Reflection:**
{reflection}
\"\"\"

        return {
            "instruction": problem,
            "response": training_response,
            "type": "metacognition",
        }

    def generate_debate_pair(self, problem: str) -> dict:
        \"\"\"Internal debate: argue for and against an approach.

        This teaches the model to consider counterarguments
        and strengthen its reasoning.
        \"\"\"
        # Generate a solution
        solution = self.model(f"Solve: {problem}")

        # Argue against it
        critique = self.model(f\"\"\"Critique this solution. Find EVERY flaw.
Be harsh and thorough. Look for:
- Logical errors
- Missing edge cases
- Performance issues
- Readability problems

Solution to critique:
{solution}
\"\"\")

        # Defend and improve
        defense = self.model(f\"\"\"Address each critique and improve the solution.

Original solution: {solution}
Critique: {critique}

For each criticism:
- If valid: fix the issue
- If invalid: explain why the original was correct
\"\"\")

        training_response = f\"\"\"I'll solve this using internal debate.

**Initial Solution:**
{solution}

**Self-Critique:**
{critique}

**Improved Solution (addressing critique):**
{defense}
\"\"\"

        return {
            "instruction": problem,
            "response": training_response,
            "type": "debate",
        }

    def _parse_approaches(self, text: str) -> list[dict]:
        approaches = []
        for match in re.finditer(
            r"Approach \\d+:\\s*(.+?)\\s*\\(confidence:\\s*(\\d\\.\\d)\\)",
            text
        ):
            approaches.append({
                "description": match.group(1).strip(),
                "confidence": float(match.group(2)),
            })
        return approaches or [{"description": text[:200], "confidence": 0.5}]

    def _extract_score(self, text: str) -> float:
        match = re.search(r"(\\d+)/10", text)
        return float(match.group(1)) if match else 5.0


class ThinkingStyleMixer:
    \"\"\"Mix different thinking styles in training data.\"\"\"

    def __init__(self, trainer: DeepThinkingTrainer):
        self.trainer = trainer

    def generate_batch(self, problems: list[str]) -> list[dict]:
        pairs = []
        for problem in problems:
            # Distribute thinking styles
            style = random.choice([
                "cot", "cot", "cot",    # 30% chain of thought
                "tot",                   # 10% tree of thought
                "meta",                  # 10% metacognition
                "debate",                # 10% debate
                "direct",               # 40% direct (for balance)
            ])

            if style == "cot":
                pairs.append(self.trainer.generate_cot_pair(problem))
            elif style == "tot":
                pairs.append(self.trainer.generate_tot_pair(problem))
            elif style == "meta":
                pairs.append(self.trainer.generate_metacognition_pair(problem))
            elif style == "debate":
                pairs.append(self.trainer.generate_debate_pair(problem))
            else:
                # Direct answer (prevents model from overthinking simple questions)
                pairs.append({
                    "instruction": problem,
                    "response": self.trainer.model(problem),
                    "type": "direct",
                })

        return pairs
```

### Why Mix Thinking Styles?

| Style | Teaches | Use When |
|-------|---------|----------|
| Chain of thought | Sequential reasoning | Standard problems |
| Tree of thought | Parallel exploration | Complex/ambiguous problems |
| Metacognition | Self-awareness | After failures, hard problems |
| Debate | Critical thinking | Design decisions, tradeoffs |
| Direct | Efficiency | Simple factual questions |

### The Deep Thinking Stack

```
Level 4: METACOGNITION  "Why did I think that way?"
Level 3: DEBATE         "What's wrong with my approach?"
Level 2: TREE-OF-THOUGHT "What are ALL the approaches?"
Level 1: CHAIN-OF-THOUGHT "Let me think step by step"
Level 0: DIRECT          "The answer is X"
```

Training on all levels produces a model that knows WHEN to think deeply
and when to just answer directly. This is the difference between a model
that wastes tokens on simple questions and one that activates deep reasoning
only when needed."""
    ),
]
