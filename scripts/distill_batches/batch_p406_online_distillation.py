"""Online distillation -- iterative knowledge transfer, progressive training, and continuous self-improvement."""

PAIRS = [
    (
        "local-ai/online-distillation-loop",
        "Show online distillation for local AI: iteratively distill from stronger model outputs, filter quality, and progressively improve without catastrophic forgetting.",
        """Online distillation with progressive improvement:

```python
import json
import os
import random
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from datetime import datetime


@dataclass
class DistillationPair:
    \"\"\"A single distillation training pair.\"\"\"
    prompt: str
    teacher_response: str
    student_response: Optional[str] = None
    teacher_score: float = 0.0
    student_score: float = 0.0
    category: str = ""
    difficulty: float = 0.5
    pair_id: str = ""

    def __post_init__(self):
        if not self.pair_id:
            h = hashlib.md5(self.prompt.encode()).hexdigest()[:12]
            self.pair_id = f"dp_{h}"


@dataclass
class DistillationCycle:
    \"\"\"One cycle of the distillation loop.\"\"\"
    cycle_number: int
    pairs_generated: int = 0
    pairs_accepted: int = 0
    avg_quality: float = 0.0
    student_improvement: float = 0.0
    categories_covered: list[str] = field(default_factory=list)
    timestamp: str = ""


class OnlineDistiller:
    \"\"\"Continuous distillation from teacher model to student model.

    Pipeline per cycle:
    1. Generate diverse prompts (curriculum-aware)
    2. Get teacher responses (strong model or API)
    3. Get student responses (local model)
    4. Score both responses
    5. Filter: keep pairs where teacher >> student (learning signal)
    6. Train student on filtered pairs
    7. Evaluate improvement
    8. Repeat with harder prompts
    \"\"\"

    def __init__(self, teacher_endpoint: str, student_endpoint: str,
                 data_dir: str, quality_threshold: float = 0.7):
        self.teacher_url = teacher_endpoint
        self.student_url = student_endpoint
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.quality_threshold = quality_threshold
        self.cycles: list[DistillationCycle] = []
        self.all_pairs: list[DistillationPair] = []

    def run_cycle(self, n_prompts: int = 50,
                    categories: Optional[list[str]] = None) -> DistillationCycle:
        \"\"\"Run one distillation cycle.\"\"\"
        cycle = DistillationCycle(
            cycle_number=len(self.cycles) + 1,
            timestamp=datetime.now().isoformat(),
        )

        # Step 1: Generate prompts
        prompts = self._generate_prompts(n_prompts, categories)

        # Step 2-3: Get teacher and student responses
        pairs = []
        for prompt_data in prompts:
            pair = self._create_pair(prompt_data)
            if pair:
                pairs.append(pair)

        cycle.pairs_generated = len(pairs)

        # Step 4-5: Score and filter
        accepted = self._filter_pairs(pairs)
        cycle.pairs_accepted = len(accepted)
        cycle.avg_quality = (
            sum(p.teacher_score for p in accepted) / max(1, len(accepted))
        )

        # Step 6: Save accepted pairs for training
        self._save_pairs(accepted, cycle.cycle_number)
        self.all_pairs.extend(accepted)

        # Step 7: Record cycle
        cycle.categories_covered = list(set(p.category for p in accepted))
        self.cycles.append(cycle)

        print(f"Cycle {cycle.cycle_number}: "
              f"{cycle.pairs_accepted}/{cycle.pairs_generated} pairs accepted "
              f"(avg quality: {cycle.avg_quality:.2f})")

        return cycle

    def _generate_prompts(self, n: int,
                            categories: Optional[list[str]] = None) -> list[dict]:
        \"\"\"Generate diverse training prompts.

        Mix of:
        - Coding tasks (algorithms, data structures, patterns)
        - Reasoning tasks (logic, math, analysis)
        - Knowledge tasks (explain concepts, compare approaches)
        - Creative tasks (design systems, invent solutions)
        \"\"\"
        prompt_templates = {
            "coding": [
                "Write a Python function that {task}. Include type hints and handle edge cases.",
                "Implement {algorithm} in Python. Optimize for both time and space complexity.",
                "Refactor this code to be more {quality}: ```python\\n{code}\\n```",
            ],
            "reasoning": [
                "Explain step by step how to solve: {problem}",
                "What are the tradeoffs between {option_a} and {option_b} for {context}?",
                "Debug this code and explain the root cause: ```python\\n{code}\\n```",
            ],
            "knowledge": [
                "Explain {concept} with a practical code example.",
                "Compare {tech_a} vs {tech_b} for {use_case}. Show code for both.",
                "What are the best practices for {topic} in production?",
            ],
            "creative": [
                "Design a {system} that handles {requirements}. Show the key components in code.",
                "Invent a novel approach to solve {problem} that combines {technique_a} and {technique_b}.",
            ],
        }

        prompts = []
        target_categories = categories or list(prompt_templates.keys())

        for _ in range(n):
            cat = random.choice(target_categories)
            template = random.choice(prompt_templates[cat])
            prompts.append({
                "prompt": template,  # Would be filled with actual tasks
                "category": cat,
                "difficulty": self._next_difficulty(cat),
            })

        return prompts

    def _next_difficulty(self, category: str) -> float:
        \"\"\"Adaptive difficulty based on student performance.\"\"\"
        recent = [p for p in self.all_pairs[-100:] if p.category == category]
        if not recent:
            return 0.3  # Start easy

        avg_gap = sum(p.teacher_score - p.student_score for p in recent) / len(recent)
        # Large gap = too hard, small gap = too easy
        current_diff = recent[-1].difficulty
        if avg_gap > 0.4:
            return max(0.1, current_diff - 0.1)  # Easier
        elif avg_gap < 0.1:
            return min(1.0, current_diff + 0.1)  # Harder
        return current_diff  # Just right

    def _create_pair(self, prompt_data: dict) -> Optional[DistillationPair]:
        \"\"\"Get teacher and student responses for a prompt.\"\"\"
        import requests

        prompt = prompt_data["prompt"]

        # Get teacher response
        try:
            teacher_resp = requests.post(
                f"{self.teacher_url}/completion",
                json={"prompt": prompt, "n_predict": 512, "temperature": 0.3},
                timeout=60,
            ).json()
        except Exception:
            return None

        # Get student response
        try:
            student_resp = requests.post(
                f"{self.student_url}/completion",
                json={"prompt": prompt, "n_predict": 512, "temperature": 0.3},
                timeout=30,
            ).json()
        except Exception:
            return None

        pair = DistillationPair(
            prompt=prompt,
            teacher_response=teacher_resp.get("content", ""),
            student_response=student_resp.get("content", ""),
            category=prompt_data.get("category", ""),
            difficulty=prompt_data.get("difficulty", 0.5),
        )

        # Score both responses
        pair.teacher_score = self._score_response(prompt, pair.teacher_response)
        pair.student_score = self._score_response(prompt, pair.student_response)

        return pair

    def _score_response(self, prompt: str, response: str) -> float:
        \"\"\"Score a response on quality (0-1).

        Simple heuristic scoring (real system uses reward model from p402):
        - Has code blocks: +0.2
        - Code is syntactically valid: +0.2
        - Response length reasonable: +0.1
        - Contains explanation: +0.2
        - Not repetitive: +0.15
        - Addresses the prompt: +0.15
        \"\"\"
        score = 0.0

        if "```" in response:
            score += 0.2
            # Check syntax
            import re
            code_blocks = re.findall(r"```python\n(.*?)```", response, re.DOTALL)
            for code in code_blocks:
                try:
                    compile(code, "<test>", "exec")
                    score += 0.2
                    break
                except SyntaxError:
                    score += 0.05  # Partial credit for having code

        # Length check
        words = len(response.split())
        if 50 <= words <= 500:
            score += 0.1

        # Has explanation (not just code)
        non_code = re.sub(r"```.*?```", "", response, flags=re.DOTALL)
        if len(non_code.split()) > 20:
            score += 0.2

        # Not repetitive
        lines = response.split("\\n")
        unique_ratio = len(set(lines)) / max(1, len(lines))
        if unique_ratio > 0.7:
            score += 0.15

        # Addresses prompt (keyword overlap)
        prompt_words = set(prompt.lower().split())
        resp_words = set(response.lower().split())
        overlap = len(prompt_words & resp_words) / max(1, len(prompt_words))
        score += min(0.15, overlap * 0.3)

        return min(1.0, score)

    def _filter_pairs(self, pairs: list[DistillationPair]) -> list[DistillationPair]:
        \"\"\"Keep pairs where teacher quality is high and student has room to learn.\"\"\"
        accepted = []
        for pair in pairs:
            # Teacher must be good enough
            if pair.teacher_score < self.quality_threshold:
                continue
            # Student should have room to improve (learning signal)
            if pair.teacher_score - pair.student_score < 0.05:
                continue  # Student already knows this; no learning signal
            accepted.append(pair)
        return accepted

    def _save_pairs(self, pairs: list[DistillationPair], cycle: int):
        \"\"\"Save accepted pairs as training data.\"\"\"
        output_file = self.data_dir / f"cycle_{cycle:04d}.jsonl"
        with open(output_file, "w") as f:
            for pair in pairs:
                record = {
                    "prompt": pair.prompt,
                    "response": pair.teacher_response,
                    "category": pair.category,
                    "difficulty": pair.difficulty,
                    "teacher_score": pair.teacher_score,
                    "student_score": pair.student_score,
                    "gap": pair.teacher_score - pair.student_score,
                }
                f.write(json.dumps(record) + "\\n")

    def get_training_data(self, min_quality: float = 0.7,
                            max_pairs: int = 1000) -> list[dict]:
        \"\"\"Compile training dataset from all cycles.

        Mix strategy:
        - 70% recent cycle pairs (freshest learning signal)
        - 20% highest-quality pairs from all cycles
        - 10% random pairs from all cycles (diversity)
        \"\"\"
        all_good = [p for p in self.all_pairs if p.teacher_score >= min_quality]

        recent = all_good[-int(max_pairs * 0.7):]
        best = sorted(all_good, key=lambda p: p.teacher_score,
                        reverse=True)[:int(max_pairs * 0.2)]
        diverse = random.sample(all_good,
                                 min(int(max_pairs * 0.1), len(all_good)))

        combined = {p.pair_id: p for p in recent + best + diverse}
        return [
            {"prompt": p.prompt, "response": p.teacher_response}
            for p in combined.values()
        ][:max_pairs]
```

Key patterns:
1. **Quality filtering** -- only keep pairs where teacher is good AND student has room to learn
2. **Adaptive difficulty** -- track teacher-student gap; increase difficulty when gap shrinks
3. **Mixed replay** -- 70% recent + 20% best + 10% random prevents forgetting while learning new skills
4. **Cycle tracking** -- monitor improvement per cycle; detect plateaus and adjust strategy
5. **Scoring heuristics** -- syntax validity, explanation quality, relevance; layered quality checks"""
    ),
    (
        "local-ai/progressive-knowledge-building",
        "Show progressive knowledge building: how a local AI builds expertise layer by layer, from fundamentals to advanced topics, with dependency-aware training.",
        """Progressive knowledge building with dependency tracking:

```python
import json
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional


@dataclass
class KnowledgeNode:
    \"\"\"A single skill or knowledge area.\"\"\"
    name: str
    prerequisites: list[str] = field(default_factory=list)
    difficulty: float = 0.5
    mastery: float = 0.0   # 0.0 = unknown, 1.0 = mastered
    training_pairs: int = 0
    last_evaluated: str = ""


class KnowledgeGraph:
    \"\"\"Dependency graph of skills for structured learning.

    Ensures the model learns prerequisites before advanced topics.
    Example: learn 'loops' before 'recursion', learn 'recursion'
    before 'dynamic programming'.
    \"\"\"

    def __init__(self):
        self.nodes: dict[str, KnowledgeNode] = {}
        self.mastery_threshold = 0.7  # Consider mastered above this

    def add_skill(self, name: str, prerequisites: list[str] = None,
                    difficulty: float = 0.5):
        self.nodes[name] = KnowledgeNode(
            name=name,
            prerequisites=prerequisites or [],
            difficulty=difficulty,
        )

    def prerequisites_met(self, skill_name: str) -> bool:
        \"\"\"Check if all prerequisites are mastered.\"\"\"
        node = self.nodes.get(skill_name)
        if not node:
            return False
        return all(
            self.nodes.get(prereq, KnowledgeNode(name=prereq)).mastery
            >= self.mastery_threshold
            for prereq in node.prerequisites
        )

    def get_ready_skills(self) -> list[KnowledgeNode]:
        \"\"\"Get skills that are ready to learn (prerequisites met, not mastered).\"\"\"
        ready = []
        for node in self.nodes.values():
            if node.mastery < self.mastery_threshold and self.prerequisites_met(node.name):
                ready.append(node)
        # Sort by difficulty (learn easier things first)
        ready.sort(key=lambda n: n.difficulty)
        return ready

    def get_learning_path(self, target_skill: str) -> list[str]:
        \"\"\"Compute optimal learning path to reach a target skill.\"\"\"
        if target_skill not in self.nodes:
            return [target_skill]

        path = []
        visited = set()

        def dfs(skill: str):
            if skill in visited:
                return
            visited.add(skill)
            node = self.nodes.get(skill)
            if node:
                for prereq in node.prerequisites:
                    if self.nodes.get(prereq, KnowledgeNode(name=prereq)).mastery < self.mastery_threshold:
                        dfs(prereq)
            if node and node.mastery < self.mastery_threshold:
                path.append(skill)

        dfs(target_skill)
        return path

    def update_mastery(self, skill_name: str, score: float):
        \"\"\"Update mastery level using exponential moving average.\"\"\"
        if skill_name in self.nodes:
            node = self.nodes[skill_name]
            alpha = 0.3  # Weight of new observation
            node.mastery = alpha * score + (1 - alpha) * node.mastery


class ProgressiveTrainer:
    \"\"\"Train the model layer by layer through the knowledge graph.\"\"\"

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.graph = knowledge_graph
        self.training_log: list[dict] = []

    def plan_next_session(self, max_skills: int = 3,
                            max_pairs_per_skill: int = 20) -> list[dict]:
        \"\"\"Plan the next training session.

        Strategy:
        1. Find skills with prerequisites met
        2. Prioritize skills closest to mastery (almost there)
        3. Include 1 exploratory skill for breadth
        \"\"\"
        ready = self.graph.get_ready_skills()
        if not ready:
            return []

        plan = []

        # Priority 1: Almost-mastered skills (high ROI)
        almost = [n for n in ready if 0.4 <= n.mastery < self.graph.mastery_threshold]
        for node in almost[:max_skills - 1]:
            plan.append({
                "skill": node.name,
                "difficulty": node.difficulty,
                "current_mastery": node.mastery,
                "pairs_needed": max_pairs_per_skill,
                "rationale": "Close to mastery; high ROI",
            })

        # Priority 2: Lowest mastery ready skills
        remaining = max_skills - len(plan)
        weak = [n for n in ready if n not in almost]
        for node in weak[:remaining]:
            plan.append({
                "skill": node.name,
                "difficulty": node.difficulty,
                "current_mastery": node.mastery,
                "pairs_needed": max_pairs_per_skill,
                "rationale": "Weakest ready skill",
            })

        return plan

    def build_default_graph(self) -> KnowledgeGraph:
        \"\"\"Build a default knowledge dependency graph for coding skills.\"\"\"
        g = self.graph

        # Layer 0: Fundamentals
        g.add_skill("variables_types", difficulty=0.1)
        g.add_skill("control_flow", difficulty=0.1)
        g.add_skill("functions", prerequisites=["variables_types", "control_flow"], difficulty=0.2)

        # Layer 1: Core data structures
        g.add_skill("lists_arrays", prerequisites=["functions"], difficulty=0.2)
        g.add_skill("dicts_hashmaps", prerequisites=["functions"], difficulty=0.2)
        g.add_skill("strings", prerequisites=["functions"], difficulty=0.2)

        # Layer 2: Intermediate
        g.add_skill("recursion", prerequisites=["functions"], difficulty=0.4)
        g.add_skill("sorting", prerequisites=["lists_arrays"], difficulty=0.3)
        g.add_skill("classes_oop", prerequisites=["functions", "dicts_hashmaps"], difficulty=0.3)

        # Layer 3: Advanced data structures
        g.add_skill("trees", prerequisites=["recursion", "classes_oop"], difficulty=0.5)
        g.add_skill("graphs", prerequisites=["trees", "dicts_hashmaps"], difficulty=0.6)
        g.add_skill("heaps", prerequisites=["lists_arrays", "trees"], difficulty=0.5)

        # Layer 4: Advanced algorithms
        g.add_skill("dynamic_programming", prerequisites=["recursion", "dicts_hashmaps"], difficulty=0.7)
        g.add_skill("graph_algorithms", prerequisites=["graphs"], difficulty=0.7)
        g.add_skill("backtracking", prerequisites=["recursion", "trees"], difficulty=0.6)

        # Layer 5: System design
        g.add_skill("design_patterns", prerequisites=["classes_oop"], difficulty=0.5)
        g.add_skill("async_concurrency", prerequisites=["functions", "classes_oop"], difficulty=0.6)
        g.add_skill("system_design", prerequisites=["design_patterns", "async_concurrency"], difficulty=0.8)

        # Layer 6: AI/ML self-improvement specific
        g.add_skill("lora_training", prerequisites=["classes_oop"], difficulty=0.6)
        g.add_skill("gguf_quantization", prerequisites=["lora_training"], difficulty=0.5)
        g.add_skill("self_evaluation", prerequisites=["lora_training"], difficulty=0.7)
        g.add_skill("curriculum_learning", prerequisites=["self_evaluation"], difficulty=0.8)
        g.add_skill("autonomous_improvement",
                     prerequisites=["curriculum_learning", "gguf_quantization", "self_evaluation"],
                     difficulty=0.9)

        return g


# Usage
graph = KnowledgeGraph()
trainer = ProgressiveTrainer(graph)
trainer.build_default_graph()

# Get learning path to "autonomous_improvement"
path = graph.get_learning_path("autonomous_improvement")
print("Learning path:", " -> ".join(path))

# Plan next session
plan = trainer.plan_next_session()
for step in plan:
    print(f"  Train: {step['skill']} (mastery={step['current_mastery']:.2f})")
```

Key patterns:
1. **Dependency graph** -- skills have prerequisites; learn foundations before advanced topics
2. **Ready set** -- only train skills whose prerequisites are mastered; prevents confusion
3. **Mastery EMA** -- exponential moving average smooths noisy individual scores
4. **Learning path** -- DFS through dependency graph to find ordered path to any target skill
5. **Session planning** -- prioritize almost-mastered skills (high ROI) + weakest ready skills"""
    ),
]
