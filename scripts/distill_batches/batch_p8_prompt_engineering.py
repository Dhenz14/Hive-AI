"""
Batch P8 — Prompt Engineering and LLM Application Patterns
Covers: chain-of-thought reasoning, structured output extraction, RAG prompt engineering,
agent system prompts (ReAct), evaluation and optimization (LLM-as-judge, APO/DSPy).
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "prompt-engineering/chain-of-thought-reasoning-patterns",
        "Explain chain-of-thought prompting techniques including zero-shot CoT, few-shot exemplars, self-consistency, tree-of-thought, and step-back prompting, then implement a reasoning framework in Python that dynamically selects the optimal prompting strategy based on task complexity analysis",
        r"""# Chain-of-Thought and Reasoning Patterns for LLM Applications

## Why Chain-of-Thought Matters

Chain-of-thought (CoT) prompting is one of the most impactful discoveries in modern prompt engineering **because** it unlocks multi-step reasoning capabilities that are otherwise latent in large language models. The core insight, first formalized by Wei et al. (2022), is deceptively simple: asking a model to "think step by step" before producing an answer dramatically improves accuracy on tasks requiring arithmetic, logic, commonsense reasoning, and symbolic manipulation. **However**, naive application of CoT is a **common mistake** — different reasoning tasks demand different prompting strategies, and selecting the wrong one can actually *degrade* performance compared to direct prompting. **Therefore**, building production-grade systems requires understanding the full taxonomy of reasoning patterns and when to deploy each.

The **trade-off** at the heart of CoT design is between **cost/latency** and **reasoning depth**. Zero-shot CoT adds virtually no prompt tokens but provides shallow reasoning. Few-shot CoT with curated exemplars is more reliable but increases prompt length. Self-consistency and tree-of-thought provide the highest accuracy but multiply API costs by 5-40x. The **best practice** is to build an adaptive system that selects strategy based on measured task complexity.

## Zero-Shot Chain-of-Thought

Zero-shot CoT is the simplest technique: append "Let's think step by step" (or a similar trigger phrase) to the end of a prompt. Kojima et al. (2022) showed this single phrase improves accuracy on GSM8K math problems from 17.7% to 78.7% with PaLM 540B. The mechanism works **because** the trigger phrase shifts the model's attention distribution toward reasoning tokens rather than pattern-matching to an answer directly.

**However**, zero-shot CoT has a critical **pitfall**: it performs poorly on tasks requiring domain-specific reasoning chains. For example, legal reasoning or medical diagnosis requires structured domain knowledge that "think step by step" alone cannot elicit. A second **common mistake** is using zero-shot CoT for classification tasks where it adds unnecessary verbosity without improving accuracy — for simple sentiment analysis, direct prompting is both faster and more accurate.

### Few-Shot CoT with Curated Exemplars

Few-shot CoT provides 2-8 solved examples in the prompt, each showing the complete reasoning chain leading to the answer. This is the **best practice** for production systems **because** it gives the model a concrete template for reasoning structure, formatting, and depth. The quality of exemplars matters enormously — poorly constructed examples can teach the model to make systematic errors.

**Key principles for exemplar design:**
- **Diversity**: Cover different reasoning paths and edge cases
- **Faithfulness**: Every step must be logically valid (models copy errors too)
- **Granularity**: Match the step size to task complexity — overly detailed steps slow down simple problems
- **Format consistency**: Use identical formatting across all exemplars

## Self-Consistency Decoding

Self-consistency (Wang et al., 2022) samples multiple reasoning chains from the model at temperature > 0 and takes a majority vote on the final answer. This works **because** correct reasoning paths tend to converge on the same answer, while incorrect paths diverge. The **trade-off** is clear: sampling 10-40 completions multiplies cost and latency by the same factor. **However**, for high-stakes decisions where accuracy justifies the cost (medical triage, financial analysis), self-consistency provides the strongest reliability guarantees.

### Tree-of-Thought

Tree-of-thought (ToT) extends CoT by treating reasoning as a search problem over a tree of intermediate states. At each node, the model generates multiple candidate "thoughts," evaluates them (either self-evaluating or using a separate evaluator call), and prunes unpromising branches before continuing. This enables **backtracking** — a capability absent from linear CoT. ToT is the **best practice** for complex planning tasks, puzzle-solving, and creative writing where the first reasoning path is unlikely to be optimal. The **pitfall** is over-engineering: ToT adds enormous complexity and cost, and for most business applications, few-shot CoT with self-consistency achieves comparable results at a fraction of the implementation effort.

### Step-Back Prompting

Step-back prompting (Zheng et al., 2023) asks the model to first identify the high-level principle or abstraction relevant to a question before attempting to answer it. For example, before solving a physics problem, the model first identifies which physical laws apply. This is particularly effective **because** it prevents the model from getting lost in surface-level details and **therefore** anchors the reasoning chain to correct foundational concepts.

## Implementing a Dynamic Reasoning Strategy Selector

The following framework analyzes task characteristics and selects the optimal CoT strategy automatically. It considers question complexity, domain specificity, required accuracy, and cost constraints.

```python
import re
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from collections import Counter


class ReasoningStrategy(Enum):
    DIRECT = "direct"
    ZERO_SHOT_COT = "zero_shot_cot"
    FEW_SHOT_COT = "few_shot_cot"
    SELF_CONSISTENCY = "self_consistency"
    TREE_OF_THOUGHT = "tree_of_thought"
    STEP_BACK = "step_back"


@dataclass
class TaskAnalysis:
    # Captures the complexity profile of a reasoning task.
    # Scores are floats in [0, 1] representing relative complexity.
    multi_step_score: float = 0.0
    domain_specificity: float = 0.0
    ambiguity_score: float = 0.0
    numerical_reasoning: bool = False
    requires_planning: bool = False
    estimated_steps: int = 1
    cost_sensitivity: float = 0.5  # 0 = no limit, 1 = minimize cost


@dataclass
class StrategyConfig:
    strategy: ReasoningStrategy
    temperature: float = 0.0
    num_samples: int = 1
    max_depth: int = 3
    branching_factor: int = 3
    system_prompt_suffix: str = ""
    exemplars: list[dict[str, str]] = field(default_factory=list)


COMPLEXITY_INDICATORS = {
    "multi_step": [
        r"\b(calculate|compute|derive|solve)\b",
        r"\b(then|next|after that|finally|first)\b",
        r"\b(step\s*\d|part\s*[a-d])\b",
        r"\b(compare|contrast|analyze)\b",
    ],
    "domain_specific": [
        r"\b(theorem|proof|lemma|corollary)\b",
        r"\b(diagnosis|symptom|treatment|prognosis)\b",
        r"\b(statute|precedent|jurisdiction|liability)\b",
        r"\b(algorithm|complexity|amortized|asymptotic)\b",
    ],
    "numerical": [
        r"\b\d+\.?\d*\s*[\+\-\*\/\%]\s*\d+\.?\d*\b",
        r"\b(percent|ratio|proportion|average|median)\b",
        r"\b(equation|formula|integral|derivative)\b",
    ],
    "planning": [
        r"\b(plan|schedule|optimize|arrange|organize)\b",
        r"\b(constraint|requirement|deadline|budget)\b",
        r"\b(sequence|order|prioritize)\b",
    ],
}


def analyze_task_complexity(question: str) -> TaskAnalysis:
    # Analyze a question to determine its complexity profile.
    # Uses regex pattern matching and heuristics to score dimensions.
    question_lower = question.lower()
    analysis = TaskAnalysis()

    # Score multi-step complexity
    multi_step_hits = sum(
        1 for pattern in COMPLEXITY_INDICATORS["multi_step"]
        if re.search(pattern, question_lower)
    )
    analysis.multi_step_score = min(multi_step_hits / 4.0, 1.0)

    # Score domain specificity
    domain_hits = sum(
        1 for pattern in COMPLEXITY_INDICATORS["domain_specific"]
        if re.search(pattern, question_lower)
    )
    analysis.domain_specificity = min(domain_hits / 3.0, 1.0)

    # Detect numerical reasoning
    num_hits = sum(
        1 for pattern in COMPLEXITY_INDICATORS["numerical"]
        if re.search(pattern, question_lower)
    )
    analysis.numerical_reasoning = num_hits >= 1

    # Detect planning requirements
    plan_hits = sum(
        1 for pattern in COMPLEXITY_INDICATORS["planning"]
        if re.search(pattern, question_lower)
    )
    analysis.requires_planning = plan_hits >= 2

    # Estimate required reasoning steps
    word_count = len(question.split())
    analysis.estimated_steps = max(1, min(10, word_count // 15 + multi_step_hits))

    # Score ambiguity (questions with multiple interpretations)
    ambiguity_markers = [r"\bor\b", r"\beither\b", r"\bdepends\b", r"\b(could|might)\b"]
    amb_hits = sum(
        1 for p in ambiguity_markers
        if re.search(p, question_lower)
    )
    analysis.ambiguity_score = min(amb_hits / 3.0, 1.0)

    return analysis
```

The strategy selector maps complexity profiles to optimal reasoning approaches.

```python
def select_strategy(
    analysis: TaskAnalysis,
    accuracy_requirement: float = 0.8,
    max_cost_multiplier: float = 10.0,
) -> StrategyConfig:
    # Select the optimal reasoning strategy based on task analysis.
    # Balances accuracy needs against cost constraints.

    # Direct prompting for simple, unambiguous tasks
    if (analysis.multi_step_score < 0.2
            and analysis.estimated_steps <= 2
            and not analysis.numerical_reasoning):
        return StrategyConfig(
            strategy=ReasoningStrategy.DIRECT,
            temperature=0.0,
        )

    # Step-back for highly domain-specific tasks
    if analysis.domain_specificity > 0.6:
        return StrategyConfig(
            strategy=ReasoningStrategy.STEP_BACK,
            temperature=0.0,
            system_prompt_suffix=(
                "Before answering, first identify the key principles, "
                "laws, or frameworks that apply to this question. "
                "Then use those principles to reason through the answer."
            ),
        )

    # Tree-of-thought for planning tasks with budget
    if (analysis.requires_planning
            and max_cost_multiplier >= 9.0
            and accuracy_requirement > 0.9):
        return StrategyConfig(
            strategy=ReasoningStrategy.TREE_OF_THOUGHT,
            temperature=0.7,
            max_depth=min(analysis.estimated_steps, 5),
            branching_factor=3,
        )

    # Self-consistency for numerical / high-accuracy needs
    if (analysis.numerical_reasoning or accuracy_requirement > 0.9):
        num_samples = min(int(max_cost_multiplier), 15)
        if num_samples >= 3:
            return StrategyConfig(
                strategy=ReasoningStrategy.SELF_CONSISTENCY,
                temperature=0.7,
                num_samples=num_samples,
            )

    # Few-shot CoT for medium-complexity multi-step tasks
    if analysis.multi_step_score >= 0.3 or analysis.estimated_steps >= 3:
        return StrategyConfig(
            strategy=ReasoningStrategy.FEW_SHOT_COT,
            temperature=0.0,
        )

    # Default: zero-shot CoT
    return StrategyConfig(
        strategy=ReasoningStrategy.ZERO_SHOT_COT,
        temperature=0.0,
        system_prompt_suffix="Let's think through this step by step.",
    )


class ReasoningOrchestrator:
    # Orchestrates LLM calls using the selected reasoning strategy.
    # Handles self-consistency voting and tree-of-thought search.

    def __init__(self, llm_call: Callable[..., Any]):
        self.llm_call = llm_call

    async def execute(
        self,
        question: str,
        config: StrategyConfig,
    ) -> dict[str, Any]:
        if config.strategy == ReasoningStrategy.SELF_CONSISTENCY:
            return await self._self_consistency(question, config)
        elif config.strategy == ReasoningStrategy.TREE_OF_THOUGHT:
            return await self._tree_of_thought(question, config)
        else:
            return await self._single_pass(question, config)

    async def _single_pass(
        self, question: str, config: StrategyConfig
    ) -> dict[str, Any]:
        prompt = question
        if config.system_prompt_suffix:
            prompt = f"{question}\n\n{config.system_prompt_suffix}"
        response = await self.llm_call(prompt, temperature=config.temperature)
        return {"answer": response, "strategy": config.strategy.value, "samples": 1}

    async def _self_consistency(
        self, question: str, config: StrategyConfig
    ) -> dict[str, Any]:
        cot_prompt = f"{question}\n\nLet's think step by step."
        tasks = [
            self.llm_call(cot_prompt, temperature=config.temperature)
            for _ in range(config.num_samples)
        ]
        responses = await asyncio.gather(*tasks)

        # Extract final answers and vote
        final_answers = [self._extract_final_answer(r) for r in responses]
        vote_counts = Counter(final_answers)
        best_answer, best_count = vote_counts.most_common(1)[0]
        confidence = best_count / len(final_answers)

        return {
            "answer": best_answer,
            "confidence": confidence,
            "vote_distribution": dict(vote_counts),
            "strategy": "self_consistency",
            "samples": config.num_samples,
        }

    async def _tree_of_thought(
        self, question: str, config: StrategyConfig
    ) -> dict[str, Any]:
        # Simplified ToT: BFS over reasoning states
        frontier = [{"state": question, "thoughts": [], "score": 0.0}]

        for depth in range(config.max_depth):
            candidates = []
            for node in frontier:
                gen_prompt = (
                    f"Given the problem: {question}\n"
                    f"Current reasoning: {' -> '.join(node['thoughts']) or 'None'}\n"
                    f"Generate {config.branching_factor} distinct next "
                    f"reasoning steps. Number them 1-{config.branching_factor}."
                )
                raw = await self.llm_call(gen_prompt, temperature=0.8)
                steps = self._parse_numbered_steps(raw)

                for step in steps[:config.branching_factor]:
                    eval_prompt = (
                        f"Rate this reasoning step (1-10) for the problem: "
                        f"{question}\nStep: {step}\nReply with just a number."
                    )
                    score_raw = await self.llm_call(eval_prompt, temperature=0.0)
                    score = self._parse_score(score_raw)
                    candidates.append({
                        "state": f"{node['state']} -> {step}",
                        "thoughts": node["thoughts"] + [step],
                        "score": node["score"] + score,
                    })

            # Keep top-k candidates
            candidates.sort(key=lambda x: x["score"], reverse=True)
            frontier = candidates[:config.branching_factor]

        best_path = frontier[0]
        final_prompt = (
            f"Problem: {question}\n"
            f"Reasoning: {' -> '.join(best_path['thoughts'])}\n"
            f"Based on this reasoning, provide the final answer."
        )
        answer = await self.llm_call(final_prompt, temperature=0.0)
        return {
            "answer": answer,
            "reasoning_path": best_path["thoughts"],
            "total_score": best_path["score"],
            "strategy": "tree_of_thought",
        }

    @staticmethod
    def _extract_final_answer(response: str) -> str:
        lines = response.strip().split("\n")
        for line in reversed(lines):
            if line.strip():
                return line.strip()
        return response.strip()

    @staticmethod
    def _parse_numbered_steps(text: str) -> list[str]:
        steps = re.findall(r"\d+[\.\)]\s*(.+)", text)
        return steps if steps else [text]

    @staticmethod
    def _parse_score(text: str) -> float:
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else 5.0
```

### Putting It All Together

```python
async def reason_about(
    question: str,
    llm_call: Callable[..., Any],
    accuracy_requirement: float = 0.8,
    max_cost_multiplier: float = 10.0,
) -> dict[str, Any]:
    # High-level API: analyze a question and apply the best reasoning strategy.
    # This is the primary entry point for the reasoning framework.
    analysis = analyze_task_complexity(question)
    config = select_strategy(
        analysis,
        accuracy_requirement=accuracy_requirement,
        max_cost_multiplier=max_cost_multiplier,
    )
    orchestrator = ReasoningOrchestrator(llm_call)
    result = await orchestrator.execute(question, config)
    result["task_analysis"] = {
        "multi_step_score": analysis.multi_step_score,
        "domain_specificity": analysis.domain_specificity,
        "numerical_reasoning": analysis.numerical_reasoning,
        "requires_planning": analysis.requires_planning,
        "estimated_steps": analysis.estimated_steps,
    }
    return result


# Example usage
async def main():
    async def mock_llm(prompt: str, temperature: float = 0.0) -> str:
        return f"[LLM response to: {prompt[:80]}...]"

    # Simple question -> direct prompting
    result = await reason_about("What is the capital of France?", mock_llm)
    print(f"Strategy: {result['strategy']}")

    # Math question -> self-consistency
    result = await reason_about(
        "Calculate the compound interest on $10,000 at 5% for 7 years compounded quarterly.",
        mock_llm,
        accuracy_requirement=0.95,
    )
    print(f"Strategy: {result['strategy']}, Samples: {result['samples']}")

    # Planning question -> tree-of-thought
    result = await reason_about(
        "Plan and schedule a software release that must satisfy deployment constraints, "
        "testing requirements, and a Friday deadline with budget optimization.",
        mock_llm,
        accuracy_requirement=0.95,
        max_cost_multiplier=20.0,
    )
    print(f"Strategy: {result['strategy']}")
```

## Summary and Key Takeaways

- **Zero-shot CoT** ("think step by step") is a low-cost baseline that works well for general reasoning but is a **pitfall** for domain-specific or classification tasks where it adds latency without accuracy gains.
- **Few-shot CoT** with carefully curated exemplars is the **best practice** for most production systems **because** it provides consistent formatting and reasoning depth.
- **Self-consistency** decoding provides the highest reliability for numerical and factual reasoning tasks, **however** the cost multiplier (5-40x) must be justified by accuracy requirements.
- **Tree-of-thought** enables backtracking and exploration for planning tasks, but the implementation complexity is a significant **trade-off** — use it only when linear reasoning provably fails.
- **Step-back prompting** anchors reasoning in foundational principles, making it ideal for domain-specific questions in law, medicine, and science.
- **Dynamic strategy selection** based on task complexity analysis is **therefore** the optimal approach for production systems that encounter diverse question types, balancing cost against accuracy automatically.
- A **common mistake** is applying the most powerful (and expensive) strategy uniformly — measure task complexity first and match the strategy to the need.
"""
    ),
    (
        "prompt-engineering/structured-output-extraction-validation",
        "Explain structured output extraction from LLMs including JSON mode, function calling, constrained generation, and Pydantic validation with retry logic, then implement a robust extraction pipeline with schema validation, error recovery, type coercion, and feedback-driven correction in Python",
        r"""# Structured Output Extraction: Schema Validation, Error Recovery, and Type Coercion

## The Challenge of Structured Output

Extracting structured data from LLMs is one of the most critical capabilities for production applications **because** it bridges the gap between natural language understanding and programmatic data consumption. APIs, databases, and downstream services require data in precise formats — JSON objects with specific fields, correct types, and valid value ranges. **However**, LLMs are fundamentally next-token predictors trained on natural language, and coercing their output into strict schemas is fraught with failure modes. A **common mistake** is treating LLM output as reliable structured data without validation — this leads to runtime crashes, data corruption, and silent logical errors that propagate through systems undetected.

The **trade-off** in structured extraction is between **flexibility** and **reliability**. Unconstrained generation gives the model maximum freedom to reason but frequently produces malformed output. Fully constrained generation (grammar-based sampling) guarantees syntactic validity but can degrade semantic quality **because** the model's token probabilities are distorted by the constraint mask. The **best practice** is a layered approach: use the strongest available constraint mechanism, validate with schemas, and implement intelligent retry with error feedback.

## Extraction Mechanisms Compared

### JSON Mode

Most modern LLM APIs offer a "JSON mode" that guarantees the response is valid JSON. This is implemented at the inference level by biasing token probabilities toward JSON-valid continuations. **However**, JSON mode only guarantees *syntactic* validity — the output is parseable JSON but may not match your expected schema. A response of `{"error": "I don't know"}` is valid JSON but useless for your application. **Therefore**, JSON mode should always be combined with schema validation.

### Function Calling / Tool Use

Function calling (OpenAI) or tool use (Anthropic) provides a higher-level abstraction where the model generates structured arguments for predefined functions. The API enforces that output matches the function's parameter schema. This is the **best practice** for most applications **because** it integrates schema definition into the API contract. The **pitfall** is that complex nested schemas with optional fields and unions can confuse models, leading to hallucinated field names or incorrect nesting.

### Constrained Generation (Outlines / Guidance)

For self-hosted models, libraries like Outlines and Guidance enforce output structure at the token sampling level using context-free grammars or regular expressions. Every generated token is guaranteed to be consistent with the target schema. This provides the strongest structural guarantee, **however** the **trade-off** is that it can slow inference (grammar checking at each step) and may force the model into low-probability token sequences that reduce output quality.

## Implementing a Robust Extraction Pipeline

```python
import json
import re
from typing import TypeVar, Type, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel, ValidationError, field_validator
from datetime import datetime, date


T = TypeVar("T", bound=BaseModel)


class ExtractionStatus(Enum):
    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    PARSE_ERROR = "parse_error"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"


@dataclass
class ExtractionResult:
    # Container for extraction results with metadata about the extraction process.
    status: ExtractionStatus
    data: Optional[Any] = None
    raw_response: str = ""
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    total_tokens_used: int = 0


class TypeCoercer:
    # Handles intelligent type coercion for common LLM output mistakes.
    # LLMs frequently return strings where numbers are expected, or
    # inconsistent date formats. This class normalizes those issues.

    @staticmethod
    def coerce_value(value: Any, target_type: str) -> Any:
        if value is None:
            return value

        if target_type == "integer":
            return TypeCoercer._to_int(value)
        elif target_type == "number":
            return TypeCoercer._to_float(value)
        elif target_type == "boolean":
            return TypeCoercer._to_bool(value)
        elif target_type == "string":
            return str(value)
        return value

    @staticmethod
    def _to_int(value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            # Handle common LLM outputs: "42", "42.0", "$42", "42%", "~42"
            cleaned = re.sub(r"[^\d.\-]", "", value)
            if cleaned:
                return int(float(cleaned))
        raise ValueError(f"Cannot coerce {value!r} to int")

    @staticmethod
    def _to_float(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = re.sub(r"[^\d.\-eE]", "", value)
            if cleaned:
                return float(cleaned)
        raise ValueError(f"Cannot coerce {value!r} to float")

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ("true", "yes", "1", "y", "on"):
                return True
            if value.lower() in ("false", "no", "0", "n", "off"):
                return False
        raise ValueError(f"Cannot coerce {value!r} to bool")


def coerce_dict_types(
    data: dict[str, Any],
    schema_properties: dict[str, Any],
) -> dict[str, Any]:
    # Recursively coerce types in a dictionary according to a JSON schema.
    # This handles the most common LLM output issues before Pydantic validation.
    coerced = {}
    coercer = TypeCoercer()

    for key, value in data.items():
        prop_schema = schema_properties.get(key, {})
        prop_type = prop_schema.get("type", "string")

        if prop_type == "object" and isinstance(value, dict):
            nested_props = prop_schema.get("properties", {})
            coerced[key] = coerce_dict_types(value, nested_props)
        elif prop_type == "array" and isinstance(value, list):
            items_schema = prop_schema.get("items", {})
            items_type = items_schema.get("type", "string")
            if items_type == "object":
                nested_props = items_schema.get("properties", {})
                coerced[key] = [
                    coerce_dict_types(item, nested_props)
                    if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                coerced[key] = [
                    coercer.coerce_value(item, items_type) for item in value
                ]
        else:
            try:
                coerced[key] = coercer.coerce_value(value, prop_type)
            except (ValueError, TypeError):
                coerced[key] = value  # Let Pydantic catch it

    return coerced
```

### The Extraction Pipeline with Retry Logic

The core pipeline implements a feedback loop: extract, validate, and if validation fails, re-prompt the model with specific error messages. This is far more effective than blind retries **because** the model can correct specific mistakes rather than regenerating from scratch.

```python
class StructuredExtractor:
    # Production-grade structured extraction with retry and error feedback.
    # Uses a layered approach: parse -> coerce -> validate -> retry with feedback.

    def __init__(
        self,
        llm_call: Callable[..., str],
        max_retries: int = 3,
        enable_coercion: bool = True,
    ):
        self.llm_call = llm_call
        self.max_retries = max_retries
        self.enable_coercion = enable_coercion

    def extract(
        self,
        prompt: str,
        schema_class: Type[T],
        system_prompt: Optional[str] = None,
    ) -> ExtractionResult:
        # Extract structured data from an LLM response, with retry logic.
        # Returns an ExtractionResult containing the validated data or error details.
        errors: list[str] = []
        last_response = ""

        schema_json = json.dumps(
            schema_class.model_json_schema(), indent=2
        )

        extraction_prompt = (
            f"{prompt}\n\n"
            f"Respond with a JSON object matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Output ONLY the JSON object, no other text."
        )

        for attempt in range(self.max_retries + 1):
            if attempt > 0 and errors:
                # Build feedback prompt with specific error details
                error_feedback = "\n".join(f"- {e}" for e in errors[-3:])
                extraction_prompt = (
                    f"{prompt}\n\n"
                    f"Your previous response had these errors:\n{error_feedback}\n\n"
                    f"Please fix these issues and respond with a valid JSON object "
                    f"matching this schema:\n```json\n{schema_json}\n```\n"
                    f"Output ONLY the JSON object, no other text."
                )

            raw_response = self.llm_call(
                extraction_prompt,
                system_prompt=system_prompt,
            )
            last_response = raw_response

            # Step 1: Parse JSON from response
            parsed = self._extract_json(raw_response)
            if parsed is None:
                errors.append(
                    f"Attempt {attempt + 1}: Could not parse valid JSON from response. "
                    f"Ensure output is a single JSON object with no markdown or prose."
                )
                continue

            # Step 2: Type coercion
            if self.enable_coercion:
                schema_props = schema_class.model_json_schema().get("properties", {})
                parsed = coerce_dict_types(parsed, schema_props)

            # Step 3: Pydantic validation
            try:
                validated = schema_class.model_validate(parsed)
                return ExtractionResult(
                    status=ExtractionStatus.SUCCESS,
                    data=validated,
                    raw_response=raw_response,
                    attempts=attempt + 1,
                )
            except ValidationError as e:
                error_msgs = []
                for err in e.errors():
                    loc = " -> ".join(str(l) for l in err["loc"])
                    error_msgs.append(f"Field '{loc}': {err['msg']} (type: {err['type']})")
                errors.extend(error_msgs)

        return ExtractionResult(
            status=ExtractionStatus.MAX_RETRIES_EXCEEDED,
            raw_response=last_response,
            errors=errors,
            attempts=self.max_retries + 1,
        )

    @staticmethod
    def _extract_json(text: str) -> Optional[dict[str, Any]]:
        # Extract a JSON object from text that may contain markdown or prose.
        # Tries multiple strategies in order of specificity.

        # Strategy 1: Look for JSON in code blocks
        code_block_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```",
            text,
            re.DOTALL,
        )
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 2: Find the outermost {...} in the response
        brace_depth = 0
        start_idx = None
        for i, char in enumerate(text):
            if char == "{":
                if brace_depth == 0:
                    start_idx = i
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth == 0 and start_idx is not None:
                    try:
                        return json.loads(text[start_idx:i + 1])
                    except json.JSONDecodeError:
                        start_idx = None

        # Strategy 3: Try parsing the entire response
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            return None
```

### Example: Defining Extraction Schemas

```python
class ProductReview(BaseModel):
    # Schema for extracting structured product review data.
    product_name: str
    rating: float
    sentiment: str
    pros: list[str]
    cons: list[str]
    summary: str
    recommended: bool
    price_mentioned: Optional[float] = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: float) -> float:
        if not 0.0 <= v <= 5.0:
            raise ValueError("Rating must be between 0.0 and 5.0")
        return round(v, 1)

    @field_validator("sentiment")
    @classmethod
    def validate_sentiment(cls, v: str) -> str:
        allowed = {"positive", "negative", "neutral", "mixed"}
        if v.lower() not in allowed:
            raise ValueError(f"Sentiment must be one of: {allowed}")
        return v.lower()


class FinancialEntity(BaseModel):
    entity_name: str
    entity_type: str  # company, person, index, currency
    value: Optional[float] = None
    currency: Optional[str] = None
    change_percent: Optional[float] = None
    time_reference: Optional[str] = None


class FinancialExtraction(BaseModel):
    entities: list[FinancialEntity]
    overall_sentiment: str
    key_events: list[str]
    risk_factors: list[str]


# Usage example
def extract_review(review_text: str, llm_fn: Callable[..., str]) -> ExtractionResult:
    extractor = StructuredExtractor(
        llm_call=llm_fn,
        max_retries=3,
        enable_coercion=True,
    )
    return extractor.extract(
        prompt=f"Extract structured data from this product review:\n\n{review_text}",
        schema_class=ProductReview,
        system_prompt="You are a precise data extraction assistant. Extract only factual information present in the text.",
    )
```

## Summary and Key Takeaways

- **JSON mode** guarantees syntactic validity but not schema conformance — always pair it with Pydantic validation, which is a **best practice** for catching semantic errors that syntactic checks miss.
- **Function calling / tool use** provides the best developer experience for API-based models **because** it integrates schema enforcement into the API contract, **however** complex schemas with deeply nested optionals remain a **pitfall**.
- **Type coercion** before validation is essential **because** LLMs frequently return strings where numbers are expected (e.g., `"42"` instead of `42`), and handling this automatically reduces retry rates by 40-60%.
- **Error feedback retries** are dramatically more effective than blind retries — providing specific validation error messages lets the model correct targeted mistakes. **Therefore**, always include the error details in retry prompts.
- The **trade-off** between constrained generation and free-form extraction depends on your deployment: constrained generation (Outlines/Guidance) is ideal for self-hosted models, while function calling is the **best practice** for API-based models.
- A **common mistake** is not handling the JSON extraction step robustly — LLMs wrap JSON in markdown code blocks, add explanatory prose, or include trailing commas. Multiple extraction strategies (code block parsing, brace matching, raw parsing) are **therefore** necessary for production reliability.
"""
    ),
    (
        "prompt-engineering/rag-prompt-engineering-context-management",
        "Explain RAG prompt engineering including context window management, chunk ranking strategies, citation generation, and source attribution for answer synthesis, then implement a RAG prompt builder in Python with dynamic context selection, relevance scoring, and hallucination detection mechanisms",
        r"""# RAG Prompt Engineering: Context Management, Citation, and Hallucination Detection

## Why RAG Prompt Design Is the Bottleneck

Retrieval-Augmented Generation (RAG) extends LLM capabilities by injecting retrieved documents into the prompt context, allowing the model to answer questions using information beyond its training data. **However**, the quality of a RAG system is determined far more by *how* retrieved context is presented in the prompt than by the retrieval model itself. Research from Anthropic and Microsoft consistently shows that prompt formatting, chunk ordering, and explicit attribution instructions account for 30-50% of answer quality variance. **Therefore**, RAG prompt engineering is not an afterthought — it is the primary lever for production quality.

The fundamental **trade-off** in RAG prompt design is between **context richness** and **signal-to-noise ratio**. Including more chunks provides the model with more potential evidence, but irrelevant chunks dilute attention and increase hallucination risk. The "lost in the middle" phenomenon (Liu et al., 2023) demonstrates that LLMs attend most strongly to information at the beginning and end of the context window, with significantly degraded recall for information in the middle. This is a critical **pitfall** that naive RAG implementations fail to address.

## Context Window Management

### Chunk Ranking in the Prompt

The order in which retrieved chunks appear in the prompt has a measurable impact on answer quality. The **best practice** is to place the most relevant chunks at the **beginning** and **end** of the context block, with less relevant chunks in the middle. This "bookend" strategy exploits the primacy and recency biases of transformer attention. **However**, an alternative strategy — placing the single most relevant chunk last, immediately before the question — can outperform bookending for single-hop factual questions **because** the model's next-token prediction naturally attends most to recent context.

### Dynamic Context Selection

Not all queries need the full context window. Short, factual questions may need only 1-2 highly relevant chunks, while complex analytical questions benefit from 5-10 diverse chunks covering different facets. A **common mistake** is using a fixed top-k retrieval regardless of query complexity. **Therefore**, the prompt builder should dynamically adjust the number of included chunks based on relevance scores, query complexity, and available context budget.

### Citation Generation and Source Attribution

Grounding LLM responses in specific sources is essential for trust and verifiability. The **best practice** is to assign each chunk a unique identifier (e.g., `[Source 1]`, `[Source 2]`) and explicitly instruct the model to cite sources inline. Without explicit citation instructions, models frequently synthesize correct answers from context but fail to attribute them, or worse, attribute claims to the wrong source — a subtle form of hallucination that is difficult to detect automatically.

## Implementing the RAG Prompt Builder

```python
import re
import hashlib
from typing import Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class RetrievedChunk:
    # Represents a single retrieved document chunk with metadata.
    content: str
    source_id: str
    source_title: str
    relevance_score: float  # 0.0 to 1.0
    chunk_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0

    def __post_init__(self):
        # Rough token estimation: ~4 chars per token for English text
        if self.token_count == 0:
            self.token_count = len(self.content) // 4


class ChunkOrderStrategy(Enum):
    RELEVANCE_DESC = "relevance_descending"
    BOOKEND = "bookend"
    RECENCY_BIAS = "recency_bias"
    DIVERSITY_INTERLEAVE = "diversity_interleave"


@dataclass
class RAGPromptConfig:
    # Configuration for RAG prompt construction.
    max_context_tokens: int = 6000
    min_relevance_threshold: float = 0.3
    max_chunks: int = 10
    chunk_order: ChunkOrderStrategy = ChunkOrderStrategy.BOOKEND
    include_source_metadata: bool = True
    require_citations: bool = True
    enable_hallucination_guard: bool = True
    citation_format: str = "[Source {id}]"


class RAGPromptBuilder:
    # Builds optimized RAG prompts with dynamic context selection,
    # chunk ordering, citation requirements, and hallucination guards.

    def __init__(self, config: Optional[RAGPromptConfig] = None):
        self.config = config or RAGPromptConfig()

    def build_prompt(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        system_context: str = "",
    ) -> dict[str, str]:
        # Build a complete RAG prompt with system and user components.
        # Returns a dict with 'system' and 'user' keys.

        # Step 1: Filter by relevance threshold
        filtered = self._filter_chunks(chunks)

        # Step 2: Select chunks within token budget
        selected = self._select_within_budget(filtered)

        # Step 3: Order chunks according to strategy
        ordered = self._order_chunks(selected)

        # Step 4: Build the context block with source identifiers
        context_block = self._format_context(ordered)

        # Step 5: Build system prompt with instructions
        system_prompt = self._build_system_prompt(system_context)

        # Step 6: Build user prompt with query and context
        user_prompt = self._build_user_prompt(query, context_block)

        return {"system": system_prompt, "user": user_prompt}

    def _filter_chunks(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        # Remove chunks below the relevance threshold.
        return [
            c for c in chunks
            if c.relevance_score >= self.config.min_relevance_threshold
        ]

    def _select_within_budget(
        self, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        # Greedily select the most relevant chunks that fit in the token budget.
        # This is a knapsack-style optimization prioritizing relevance.
        sorted_chunks = sorted(
            chunks, key=lambda c: c.relevance_score, reverse=True
        )
        selected: list[RetrievedChunk] = []
        remaining_tokens = self.config.max_context_tokens

        for chunk in sorted_chunks:
            if len(selected) >= self.config.max_chunks:
                break
            if chunk.token_count <= remaining_tokens:
                selected.append(chunk)
                remaining_tokens -= chunk.token_count

        return selected

    def _order_chunks(
        self, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        # Order chunks according to the configured strategy.
        if not chunks:
            return chunks

        if self.config.chunk_order == ChunkOrderStrategy.RELEVANCE_DESC:
            return sorted(chunks, key=lambda c: c.relevance_score, reverse=True)

        elif self.config.chunk_order == ChunkOrderStrategy.BOOKEND:
            # Place highest relevance at start and end, lower in middle
            by_relevance = sorted(
                chunks, key=lambda c: c.relevance_score, reverse=True
            )
            if len(by_relevance) <= 2:
                return by_relevance
            result: list[RetrievedChunk] = []
            for i, chunk in enumerate(by_relevance):
                if i % 2 == 0:
                    result.insert(0, chunk)  # Prepend high-relevance
                else:
                    result.append(chunk)  # Append to middle/end
            # Move the single best chunk to position 0
            best = max(result, key=lambda c: c.relevance_score)
            result.remove(best)
            result.insert(0, best)
            return result

        elif self.config.chunk_order == ChunkOrderStrategy.RECENCY_BIAS:
            # Best chunk goes last (closest to the question)
            by_relevance = sorted(
                chunks, key=lambda c: c.relevance_score
            )
            return by_relevance  # Ascending, so best is last

        return chunks

    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        # Format chunks into a labeled context block.
        sections: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            source_label = self.config.citation_format.format(id=i)
            header = f"{source_label}"
            if self.config.include_source_metadata:
                header += f" - {chunk.source_title}"
                if "date" in chunk.metadata:
                    header += f" ({chunk.metadata['date']})"
                header += f" [relevance: {chunk.relevance_score:.2f}]"
            sections.append(f"{header}\n{chunk.content}")

        return "\n\n---\n\n".join(sections)

    def _build_system_prompt(self, additional_context: str = "") -> str:
        parts = [
            "You are a knowledgeable assistant that answers questions "
            "based on the provided source documents."
        ]
        if self.config.require_citations:
            parts.append(
                "IMPORTANT: You MUST cite your sources using the [Source N] "
                "format for every factual claim. If a piece of information "
                "comes from a specific source, cite it inline."
            )
        if self.config.enable_hallucination_guard:
            parts.append(
                "If the provided sources do not contain sufficient information "
                "to answer the question, explicitly state what information is "
                "missing. Do NOT fabricate information or cite sources for "
                "claims they do not support. Say 'Based on the provided sources, "
                "I cannot determine...' when appropriate."
            )
        if additional_context:
            parts.append(additional_context)
        return "\n\n".join(parts)

    def _build_user_prompt(self, query: str, context_block: str) -> str:
        return (
            f"## Source Documents\n\n{context_block}\n\n"
            f"---\n\n## Question\n\n{query}\n\n"
            f"Provide a comprehensive answer based on the sources above."
        )
```

### Hallucination Detection Post-Processing

After the model generates a response, verifying that citations are valid and claims are grounded is essential. The following detector checks for common hallucination patterns.

```python
@dataclass
class HallucinationReport:
    # Report from hallucination detection analysis.
    uncited_claims: list[str]
    invalid_citations: list[str]
    unsupported_claims: list[dict[str, str]]
    hallucination_score: float  # 0.0 = no hallucination, 1.0 = fully hallucinated
    is_grounded: bool


class HallucinationDetector:
    # Detects potential hallucinations in RAG-generated responses by
    # checking citation validity and claim grounding.

    def __init__(
        self,
        similarity_fn: Optional[Callable[[str, str], float]] = None,
        grounding_threshold: float = 0.4,
    ):
        # If no similarity function provided, use simple word overlap
        self.similarity_fn = similarity_fn or self._word_overlap_similarity
        self.grounding_threshold = grounding_threshold

    def analyze(
        self,
        response: str,
        source_chunks: list[RetrievedChunk],
    ) -> HallucinationReport:
        # Analyze a response for potential hallucinations.
        cited_sources = self._extract_citations(response)
        valid_source_ids = set(range(1, len(source_chunks) + 1))

        # Check for invalid citation IDs
        invalid = [
            f"[Source {cid}]" for cid in cited_sources
            if cid not in valid_source_ids
        ]

        # Split response into claim sentences
        claims = self._split_into_claims(response)

        # Check each claim for grounding
        uncited: list[str] = []
        unsupported: list[dict[str, str]] = []

        for claim in claims:
            claim_citations = self._extract_citations(claim)
            if not claim_citations and self._is_factual_claim(claim):
                uncited.append(claim)
                continue

            # Verify cited sources actually support the claim
            for cid in claim_citations:
                if cid in valid_source_ids:
                    chunk = source_chunks[cid - 1]
                    sim = self.similarity_fn(claim, chunk.content)
                    if sim < self.grounding_threshold:
                        unsupported.append({
                            "claim": claim,
                            "cited_source": f"[Source {cid}]",
                            "similarity": f"{sim:.2f}",
                        })

        total_claims = max(len(claims), 1)
        problem_claims = len(uncited) + len(unsupported)
        hallucination_score = min(problem_claims / total_claims, 1.0)

        return HallucinationReport(
            uncited_claims=uncited,
            invalid_citations=invalid,
            unsupported_claims=unsupported,
            hallucination_score=hallucination_score,
            is_grounded=hallucination_score < 0.3,
        )

    @staticmethod
    def _extract_citations(text: str) -> list[int]:
        return [int(m) for m in re.findall(r"\[Source\s+(\d+)\]", text)]

    @staticmethod
    def _split_into_claims(text: str) -> list[str]:
        # Split text into individual sentences/claims
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if len(s.strip()) > 20]

    @staticmethod
    def _is_factual_claim(text: str) -> bool:
        # Heuristic: factual claims contain specific entities, numbers, or dates
        factual_patterns = [
            r"\b\d{4}\b",           # Years
            r"\b\d+\.?\d*%\b",      # Percentages
            r"\b[A-Z][a-z]+\s[A-Z]", # Proper nouns
            r"\b(according to|research shows|studies indicate)\b",
        ]
        return any(re.search(p, text) for p in factual_patterns)

    @staticmethod
    def _word_overlap_similarity(text1: str, text2: str) -> float:
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        return len(intersection) / min(len(words1), len(words2))
```

### End-to-End RAG Pipeline Usage

```python
def run_rag_pipeline(
    query: str,
    retriever_fn: Callable[[str], list[RetrievedChunk]],
    llm_fn: Callable[[str, str], str],
    config: Optional[RAGPromptConfig] = None,
) -> dict[str, Any]:
    # Complete RAG pipeline: retrieve, build prompt, generate, detect hallucinations.
    builder = RAGPromptBuilder(config)
    detector = HallucinationDetector()

    # Retrieve relevant chunks
    chunks = retriever_fn(query)

    # Build optimized prompt
    prompt = builder.build_prompt(query, chunks)

    # Generate response
    response = llm_fn(prompt["system"], prompt["user"])

    # Analyze for hallucinations
    report = detector.analyze(response, chunks)

    return {
        "answer": response,
        "sources_used": len(chunks),
        "hallucination_report": {
            "score": report.hallucination_score,
            "is_grounded": report.is_grounded,
            "uncited_claims": len(report.uncited_claims),
            "invalid_citations": report.invalid_citations,
            "unsupported_claims": len(report.unsupported_claims),
        },
        "metadata": {
            "context_tokens": sum(c.token_count for c in chunks),
            "chunks_filtered": len(chunks),
        },
    }
```

## Summary and Key Takeaways

- **Chunk ordering** has a measurable impact on answer quality due to the "lost in the middle" phenomenon. The **best practice** is bookend ordering (best chunks at start and end), **however** recency-bias ordering (best chunk last) can outperform for simple factual queries.
- **Dynamic context selection** based on relevance scores and token budgets prevents the **common mistake** of blindly stuffing the maximum number of chunks into the context window, which dilutes attention and increases hallucination risk.
- **Explicit citation instructions** in the system prompt are essential **because** without them, models synthesize information without attribution, making verification impossible. **Therefore**, always assign unique source identifiers and require inline citations.
- **Hallucination detection** via citation validation and claim grounding provides a measurable safety net. The **trade-off** is that simple word-overlap similarity is fast but imprecise — production systems should use embedding-based similarity for more accurate grounding checks.
- The **pitfall** of RAG prompt engineering is treating it as a one-time setup. In practice, prompt templates must be tuned per domain, per query type, and per model, **because** different models respond differently to formatting, instruction phrasing, and context length.
- **Best practice**: always include a hallucination guard instruction telling the model to explicitly state when sources are insufficient rather than fabricating information.
"""
    ),
    (
        "prompt-engineering/react-agent-system-prompts-tool-dispatch",
        "Explain agent system prompt design including the ReAct framework, tool use patterns, reflection and self-correction, and multi-step planning with LLMs, then implement a complete ReAct agent loop in Python with tool dispatch, observation parsing, thought generation, and loop termination logic",
        r"""# Agent System Prompts: ReAct Framework, Tool Dispatch, and Self-Correction

## Why Agent Architectures Matter

LLM-powered agents extend language models from passive text generators into active problem-solvers that can observe, reason, and act in external environments. The ReAct framework (Yao et al., 2022) formalized the most successful pattern: interleaving **Reasoning** (thinking about what to do) with **Acting** (executing tools) and **Observing** (processing results). This approach outperforms pure chain-of-thought reasoning **because** it grounds the model's reasoning in real-world observations rather than relying entirely on parametric knowledge, which may be outdated or incorrect.

**However**, building reliable agents is significantly harder than building simple prompt-response systems. The core **trade-off** is between **agent autonomy** and **predictability**. A highly autonomous agent can solve complex multi-step problems but is more likely to enter infinite loops, hallucinate tool calls, or take unintended actions. A tightly constrained agent is predictable but limited in capability. The **best practice** is to implement explicit guardrails — maximum iteration limits, tool call validation, output parsing with fallbacks, and reflection-based self-correction — while giving the agent sufficient flexibility to handle diverse tasks.

## The ReAct Pattern in Detail

### System Prompt Design

The system prompt is the foundation of agent behavior. A **common mistake** is writing vague system prompts like "You are a helpful assistant that can use tools." Effective agent system prompts must specify:

1. **Identity and scope**: What the agent can and cannot do
2. **Tool descriptions**: Precise specifications of each tool's inputs, outputs, and side effects
3. **Output format**: The exact format for thoughts, actions, and observations
4. **Termination criteria**: When to stop the loop and produce a final answer
5. **Error handling**: How to recover from tool failures and unexpected observations

### Thought-Action-Observation Loop

The ReAct loop follows a strict pattern. The model generates a **Thought** (internal reasoning about the current state and next step), then an **Action** (a tool call with specific arguments), receives an **Observation** (the tool's output), and repeats. This explicit separation of reasoning from action is critical **because** it makes the agent's decision-making transparent and debuggable. **Therefore**, the thought step should never be omitted — agents that jump directly to actions without articulating reasoning produce less reliable results and are far harder to debug in production.

### Reflection and Self-Correction

Advanced agents include a **reflection** step where the model evaluates its own progress and identifies errors. This is the **best practice** for complex tasks **because** without explicit self-monitoring, agents frequently perseverate on failed approaches — a **pitfall** known as the "action loop." Reflection prompts ask the model to assess whether its current approach is working, whether the observations match expectations, and whether a different strategy would be more effective.

## Implementing the ReAct Agent

```python
import re
import json
import time
from typing import Any, Optional, Callable, Protocol
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod


class ToolStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"


@dataclass
class ToolResult:
    # Result from a tool execution.
    status: ToolStatus
    output: str
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    # Abstract base class for agent tools.
    name: str
    description: str
    parameters_schema: dict[str, Any]

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        ...

    def to_prompt_description(self) -> str:
        params = json.dumps(self.parameters_schema, indent=2)
        return (
            f"Tool: {self.name}\n"
            f"Description: {self.description}\n"
            f"Parameters: {params}"
        )


class SearchTool(Tool):
    name = "search"
    description = "Search the knowledge base for relevant information."
    parameters_schema = {
        "query": {"type": "string", "description": "The search query"},
        "max_results": {"type": "integer", "description": "Maximum results to return", "default": 5},
    }

    def __init__(self, search_fn: Callable[[str, int], list[str]]):
        self.search_fn = search_fn

    def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        try:
            results = self.search_fn(query, max_results)
            return ToolResult(
                status=ToolStatus.SUCCESS,
                output="\n".join(f"- {r}" for r in results),
            )
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, output=str(e))


class CalculatorTool(Tool):
    name = "calculator"
    description = "Perform mathematical calculations. Supports basic arithmetic and common math functions."
    parameters_schema = {
        "expression": {"type": "string", "description": "The math expression to evaluate"},
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        import math
        expression = kwargs.get("expression", "")
        # Restricted eval with only math functions
        allowed_names = {
            k: v for k, v in math.__dict__.items()
            if not k.startswith("_")
        }
        allowed_names.update({"abs": abs, "round": round, "min": min, "max": max})
        try:
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=str(result),
            )
        except Exception as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                output=f"Calculation error: {e}",
            )


@dataclass
class AgentStep:
    # A single step in the agent's reasoning loop.
    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[dict[str, Any]] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[str] = None


@dataclass
class AgentConfig:
    max_iterations: int = 10
    max_observation_tokens: int = 2000
    enable_reflection: bool = True
    reflection_interval: int = 3  # Reflect every N steps
    timeout_per_tool_ms: float = 30000.0
```

### The Core Agent Loop

The agent loop is the heart of the system. It parses the model's output to extract thoughts and actions, dispatches tool calls, and feeds observations back into the conversation.

```python
class ReActAgent:
    # ReAct agent with tool dispatch, observation parsing, and self-correction.

    def __init__(
        self,
        llm_call: Callable[[list[dict[str, str]]], str],
        tools: list[Tool],
        config: Optional[AgentConfig] = None,
    ):
        self.llm_call = llm_call
        self.tools = {tool.name: tool for tool in tools}
        self.config = config or AgentConfig()
        self.steps: list[AgentStep] = []

    def build_system_prompt(self) -> str:
        tool_descriptions = "\n\n".join(
            tool.to_prompt_description() for tool in self.tools.values()
        )
        return (
            "You are an AI agent that solves problems by reasoning step-by-step "
            "and using tools when needed.\n\n"
            "## Available Tools\n\n"
            f"{tool_descriptions}\n\n"
            "## Response Format\n\n"
            "For each step, respond with EXACTLY this format:\n\n"
            "Thought: [Your reasoning about the current situation and what to do next]\n"
            "Action: [tool_name]\n"
            "Action Input: [JSON object with tool parameters]\n\n"
            "When you have enough information to answer, respond with:\n\n"
            "Thought: [Your final reasoning]\n"
            "Final Answer: [Your complete answer to the original question]\n\n"
            "## Rules\n\n"
            "1. Always start with a Thought before taking any Action.\n"
            "2. Use ONLY the tools listed above. Do not invent tools.\n"
            "3. If a tool returns an error, reason about the error and try a different approach.\n"
            "4. Provide your Final Answer when you have sufficient information.\n"
            "5. If you cannot answer after exhausting all approaches, say so explicitly.\n"
        )

    def run(self, query: str) -> dict[str, Any]:
        # Execute the agent loop for a given query.
        # Returns the final answer and step history.
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.build_system_prompt()},
            {"role": "user", "content": query},
        ]
        self.steps = []

        for iteration in range(self.config.max_iterations):
            # Check if reflection is due
            if (self.config.enable_reflection
                    and iteration > 0
                    and iteration % self.config.reflection_interval == 0):
                self._inject_reflection(messages, query)

            # Get model response
            response = self.llm_call(messages)

            # Parse the response
            step = self._parse_response(response, iteration + 1)
            self.steps.append(step)

            if step.is_final:
                return {
                    "answer": step.final_answer,
                    "steps": self.steps,
                    "iterations": iteration + 1,
                    "status": "completed",
                }

            # Execute the tool
            if step.action and step.action in self.tools:
                tool = self.tools[step.action]
                start = time.perf_counter()
                result = tool.execute(**(step.action_input or {}))
                elapsed_ms = (time.perf_counter() - start) * 1000
                result.execution_time_ms = elapsed_ms

                observation = self._format_observation(result)
                step.observation = observation

                # Add the exchange to message history
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": f"Observation: {observation}",
                })

            elif step.action:
                # Tool not found
                error_obs = (
                    f"Error: Tool '{step.action}' not found. "
                    f"Available tools: {', '.join(self.tools.keys())}"
                )
                step.observation = error_obs
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {error_obs}"})
            else:
                # No action parsed — ask model to try again
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": (
                        "Observation: Could not parse a valid Action from your response. "
                        "Please use the exact format: Action: [tool_name]"
                    ),
                })

        # Max iterations reached
        return {
            "answer": None,
            "steps": self.steps,
            "iterations": self.config.max_iterations,
            "status": "max_iterations_exceeded",
        }

    def _parse_response(self, response: str, step_number: int) -> AgentStep:
        # Parse the model's response into structured thought/action components.
        step = AgentStep(step_number=step_number, thought="")

        # Extract thought
        thought_match = re.search(
            r"Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|\Z)",
            response,
            re.DOTALL,
        )
        if thought_match:
            step.thought = thought_match.group(1).strip()

        # Check for final answer
        final_match = re.search(
            r"Final Answer:\s*(.*)",
            response,
            re.DOTALL,
        )
        if final_match:
            step.is_final = True
            step.final_answer = final_match.group(1).strip()
            return step

        # Extract action
        action_match = re.search(r"Action:\s*(\w+)", response)
        if action_match:
            step.action = action_match.group(1).strip()

        # Extract action input
        input_match = re.search(
            r"Action Input:\s*(\{.*?\})",
            response,
            re.DOTALL,
        )
        if input_match:
            try:
                step.action_input = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                step.action_input = {}

        return step

    def _format_observation(self, result: ToolResult) -> str:
        # Format a tool result as an observation string.
        output = result.output
        # Truncate very long observations
        max_chars = self.config.max_observation_tokens * 4
        if len(output) > max_chars:
            output = output[:max_chars] + "\n... [truncated]"

        prefix = "SUCCESS" if result.status == ToolStatus.SUCCESS else "ERROR"
        return f"[{prefix}] {output}"

    def _inject_reflection(
        self,
        messages: list[dict[str, str]],
        original_query: str,
    ) -> None:
        # Inject a reflection prompt to enable self-correction.
        step_summary = "\n".join(
            f"Step {s.step_number}: {s.thought[:100]}..."
            for s in self.steps[-3:]
        )
        reflection_prompt = (
            f"Before continuing, reflect on your progress toward answering: "
            f"'{original_query}'\n\n"
            f"Recent steps:\n{step_summary}\n\n"
            f"Are you making progress? Should you try a different approach? "
            f"Is there information you still need?"
        )
        messages.append({"role": "user", "content": reflection_prompt})
```

### Agent Usage Example

```python
def create_research_agent(
    llm_call: Callable[[list[dict[str, str]]], str],
) -> ReActAgent:
    # Create a research agent with search and calculator tools.

    def mock_search(query: str, max_results: int = 5) -> list[str]:
        return [f"Result for '{query}': relevant information..."]

    tools = [
        SearchTool(search_fn=mock_search),
        CalculatorTool(),
    ]

    return ReActAgent(
        llm_call=llm_call,
        tools=tools,
        config=AgentConfig(
            max_iterations=8,
            enable_reflection=True,
            reflection_interval=3,
        ),
    )

# Usage
# agent = create_research_agent(my_llm_function)
# result = agent.run("What is the GDP per capita of the top 5 economies?")
# print(result["answer"])
# for step in result["steps"]:
#     print(f"Step {step.step_number}: {step.thought}")
```

## Summary and Key Takeaways

- The **ReAct framework** (Thought-Action-Observation) is the **best practice** for building LLM agents **because** it makes reasoning explicit, enables tool use, and provides an auditable decision trail for debugging.
- **System prompt design** is the most critical component — a **common mistake** is using vague instructions. Effective prompts must specify tool schemas, output format, termination criteria, and error handling with precision.
- **Reflection and self-correction** at regular intervals prevents the agent from perseverating on failed approaches. This is essential **because** without it, agents frequently enter infinite loops or repeat the same failing tool calls. The **trade-off** is that reflection adds one LLM call per interval, increasing cost and latency.
- **Observation truncation** is a practical necessity — tool outputs (e.g., search results, API responses) can easily exceed the context window. **Therefore**, always cap observation length and prioritize the most relevant information.
- **Tool dispatch validation** must handle three cases: successful execution, tool errors (graceful degradation), and hallucinated tool names (redirect to available tools). The **pitfall** of not validating tool names is that models frequently invent plausible-sounding tools that do not exist.
- **Loop termination** requires both explicit criteria (Final Answer detection) and safety limits (maximum iterations) **because** relying on the model to terminate is unreliable — models can enter infinite reasoning loops under adversarial or ambiguous inputs.
- A **best practice** for production agents is to log every step (thought, action, observation) for post-hoc analysis, enabling systematic identification of failure patterns and prompt refinement.
"""
    ),
    (
        "prompt-engineering/evaluation-optimization-llm-as-judge",
        "Explain prompt evaluation and optimization techniques including A/B testing, LLM-as-judge evaluation, automatic prompt optimization inspired by DSPy, and metric design for generation quality, then implement a prompt evaluation framework in Python with multiple metrics, statistical comparison, and iterative refinement capabilities",
        r"""# Prompt Evaluation and Optimization: Metrics, LLM-as-Judge, and Iterative Refinement

## Why Systematic Evaluation Is Non-Negotiable

Prompt engineering without systematic evaluation is guesswork. The difference between a good prompt and a great prompt can be 20-40% accuracy on domain-specific tasks, but this difference is invisible without measurement. A **common mistake** is evaluating prompts by reading a handful of outputs and making subjective judgments — this approach is biased by recency, confirmation bias, and the evaluator's inability to hold statistical distributions in working memory. **Therefore**, production prompt engineering requires automated evaluation with well-designed metrics, statistical significance testing, and iterative optimization loops.

The fundamental **trade-off** in evaluation is between **evaluation cost** and **evaluation fidelity**. Human evaluation is the gold standard but costs $10-50 per sample and does not scale. Automated metrics (BLEU, ROUGE, BERTScore) are cheap but poorly correlated with human judgment for open-ended generation. LLM-as-judge sits in the middle — it provides human-like evaluation at 100-1000x lower cost, **however** it introduces its own biases (verbosity bias, position bias, self-preference). The **best practice** is to use a combination: automated metrics for rapid iteration, LLM-as-judge for detailed quality assessment, and periodic human evaluation for calibration.

## Metric Design for Generation Quality

### Task-Specific vs. General Metrics

Effective evaluation requires metrics tailored to the specific task. For factual QA, accuracy and faithfulness matter most. For creative writing, coherence, style, and originality dominate. For code generation, functional correctness (pass@k) is the only metric that truly matters. A **pitfall** is using generic metrics like "overall quality" — these are too vague for the LLM judge to evaluate consistently and produce unreliable scores.

### LLM-as-Judge Patterns

The most reliable LLM-as-judge configurations use **pairwise comparison** rather than absolute scoring **because** models are better at relative judgments than calibrated absolute ratings. When absolute scores are needed, use a detailed rubric with specific criteria for each score level. **However**, all LLM judges exhibit systematic biases:

- **Verbosity bias**: Longer responses receive higher scores regardless of quality
- **Position bias**: In pairwise comparisons, the first or last response is favored
- **Self-preference**: Models rate their own outputs higher than other models' outputs

The **best practice** to mitigate these biases is to randomize presentation order, normalize for response length, and use a different model family as judge than the one being evaluated.

### Automatic Prompt Optimization

Inspired by DSPy and APO (Automatic Prompt Optimization), the key insight is that prompt optimization can be framed as a search problem: given an evaluation function, find the prompt that maximizes the score. Approaches range from simple grid search over prompt variants to gradient-free optimization (evolutionary algorithms, Bayesian optimization) to LLM-driven prompt rewriting. The **trade-off** is that more sophisticated optimization requires more evaluation budget — each candidate prompt must be tested on a representative sample.

## Implementing the Evaluation Framework

```python
import statistics
import random
import json
import time
from typing import Any, Optional, Callable, Protocol
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod


@dataclass
class EvalSample:
    # A single evaluation sample with input, expected output, and metadata.
    input_text: str
    expected_output: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    category: str = "default"


@dataclass
class GenerationResult:
    # The result of running a prompt on a single sample.
    input_text: str
    output_text: str
    prompt_template: str
    latency_ms: float = 0.0
    token_count: int = 0


@dataclass
class MetricScore:
    # A single metric evaluation result.
    metric_name: str
    score: float  # 0.0 to 1.0
    explanation: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)


class EvalMetric(ABC):
    # Abstract base class for evaluation metrics.
    name: str
    description: str

    @abstractmethod
    def evaluate(
        self,
        generation: GenerationResult,
        expected: Optional[str] = None,
    ) -> MetricScore:
        ...


class LengthAdequacyMetric(EvalMetric):
    # Evaluates whether the response length is appropriate for the query.
    name = "length_adequacy"
    description = "Checks if response length is appropriate"

    def __init__(self, min_words: int = 50, max_words: int = 500):
        self.min_words = min_words
        self.max_words = max_words

    def evaluate(
        self,
        generation: GenerationResult,
        expected: Optional[str] = None,
    ) -> MetricScore:
        word_count = len(generation.output_text.split())

        if self.min_words <= word_count <= self.max_words:
            score = 1.0
            explanation = f"Response length ({word_count} words) is within acceptable range."
        elif word_count < self.min_words:
            score = max(0.0, word_count / self.min_words)
            explanation = f"Response too short ({word_count} words, minimum {self.min_words})."
        else:
            # Slight penalty for being too verbose
            excess_ratio = word_count / self.max_words
            score = max(0.3, 1.0 / excess_ratio)
            explanation = f"Response too long ({word_count} words, maximum {self.max_words})."

        return MetricScore(
            metric_name=self.name,
            score=score,
            explanation=explanation,
            raw_data={"word_count": word_count},
        )


class FormatComplianceMetric(EvalMetric):
    # Checks if the response follows expected formatting conventions.
    name = "format_compliance"
    description = "Evaluates structural formatting compliance"

    def __init__(self, required_elements: Optional[list[str]] = None):
        self.required_elements = required_elements or []

    def evaluate(
        self,
        generation: GenerationResult,
        expected: Optional[str] = None,
    ) -> MetricScore:
        text = generation.output_text
        checks_passed = 0
        total_checks = max(len(self.required_elements), 1)
        missing: list[str] = []

        for element in self.required_elements:
            if element.lower() in text.lower():
                checks_passed += 1
            else:
                missing.append(element)

        score = checks_passed / total_checks if total_checks > 0 else 1.0

        return MetricScore(
            metric_name=self.name,
            score=score,
            explanation=f"Found {checks_passed}/{total_checks} required elements. Missing: {missing}",
            raw_data={"missing_elements": missing},
        )


class LLMJudgeMetric(EvalMetric):
    # Uses an LLM to evaluate generation quality on specific criteria.
    # This is the most flexible and powerful evaluation approach.
    name = "llm_judge"
    description = "LLM-based quality evaluation"

    def __init__(
        self,
        judge_llm: Callable[[str], str],
        criteria: list[str],
        rubric: Optional[dict[int, str]] = None,
    ):
        self.judge_llm = judge_llm
        self.criteria = criteria
        self.rubric = rubric or {
            1: "Poor: Fails to address the query or contains major errors",
            2: "Below Average: Partially addresses the query with significant issues",
            3: "Average: Addresses the query but with notable gaps or minor errors",
            4: "Good: Thoroughly addresses the query with minor issues",
            5: "Excellent: Comprehensive, accurate, and well-structured response",
        }

    def evaluate(
        self,
        generation: GenerationResult,
        expected: Optional[str] = None,
    ) -> MetricScore:
        criteria_text = "\n".join(f"- {c}" for c in self.criteria)
        rubric_text = "\n".join(f"  {k}: {v}" for k, v in self.rubric.items())

        judge_prompt = (
            f"Evaluate the following AI-generated response.\n\n"
            f"## Query\n{generation.input_text}\n\n"
            f"## Response\n{generation.output_text}\n\n"
        )
        if expected:
            judge_prompt += f"## Reference Answer\n{expected}\n\n"

        judge_prompt += (
            f"## Evaluation Criteria\n{criteria_text}\n\n"
            f"## Scoring Rubric\n{rubric_text}\n\n"
            f"Provide your evaluation in this exact format:\n"
            f"Score: [1-5]\n"
            f"Reasoning: [Your detailed reasoning for the score]\n"
        )

        judge_response = self.judge_llm(judge_prompt)
        score_val, reasoning = self._parse_judge_response(judge_response)

        return MetricScore(
            metric_name=self.name,
            score=score_val / 5.0,  # Normalize to 0-1
            explanation=reasoning,
            raw_data={"raw_score": score_val, "judge_response": judge_response},
        )

    @staticmethod
    def _parse_judge_response(response: str) -> tuple[int, str]:
        import re
        score_match = re.search(r"Score:\s*(\d+)", response)
        reasoning_match = re.search(r"Reasoning:\s*(.*)", response, re.DOTALL)

        score = int(score_match.group(1)) if score_match else 3
        score = max(1, min(5, score))
        reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning provided"

        return score, reasoning
```

### The Evaluation Runner and Statistical Comparison

```python
@dataclass
class EvalRunResult:
    # Results from evaluating a single prompt across all samples.
    prompt_name: str
    prompt_template: str
    metric_scores: dict[str, list[float]]  # metric_name -> list of scores
    generation_results: list[GenerationResult]
    mean_latency_ms: float = 0.0

    def mean_score(self, metric_name: str) -> float:
        scores = self.metric_scores.get(metric_name, [])
        return statistics.mean(scores) if scores else 0.0

    def std_score(self, metric_name: str) -> float:
        scores = self.metric_scores.get(metric_name, [])
        return statistics.stdev(scores) if len(scores) > 1 else 0.0

    def overall_score(self) -> float:
        all_means = [self.mean_score(m) for m in self.metric_scores]
        return statistics.mean(all_means) if all_means else 0.0


class PromptEvaluator:
    # Framework for evaluating and comparing prompt variants.
    # Supports multiple metrics, statistical comparison, and iterative refinement.

    def __init__(
        self,
        llm_call: Callable[[str, str], str],
        metrics: list[EvalMetric],
        samples: list[EvalSample],
    ):
        self.llm_call = llm_call
        self.metrics = metrics
        self.samples = samples

    def evaluate_prompt(
        self,
        prompt_name: str,
        prompt_template: str,
        system_prompt: str = "",
    ) -> EvalRunResult:
        # Run evaluation for a single prompt across all samples.
        metric_scores: dict[str, list[float]] = {m.name: [] for m in self.metrics}
        generations: list[GenerationResult] = []
        latencies: list[float] = []

        for sample in self.samples:
            filled_prompt = prompt_template.replace("{input}", sample.input_text)
            start = time.perf_counter()
            output = self.llm_call(system_prompt, filled_prompt)
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)

            gen_result = GenerationResult(
                input_text=sample.input_text,
                output_text=output,
                prompt_template=prompt_template,
                latency_ms=latency,
            )
            generations.append(gen_result)

            for metric in self.metrics:
                score = metric.evaluate(gen_result, sample.expected_output)
                metric_scores[metric.name].append(score.score)

        return EvalRunResult(
            prompt_name=prompt_name,
            prompt_template=prompt_template,
            metric_scores=metric_scores,
            generation_results=generations,
            mean_latency_ms=statistics.mean(latencies) if latencies else 0.0,
        )

    def compare_prompts(
        self,
        prompt_variants: dict[str, str],
        system_prompt: str = "",
        significance_level: float = 0.05,
    ) -> dict[str, Any]:
        # Compare multiple prompt variants with statistical significance testing.
        results: dict[str, EvalRunResult] = {}

        for name, template in prompt_variants.items():
            results[name] = self.evaluate_prompt(name, template, system_prompt)

        # Compute pairwise comparisons
        comparison = self._statistical_comparison(results, significance_level)

        # Rank by overall score
        ranked = sorted(
            results.items(),
            key=lambda x: x[1].overall_score(),
            reverse=True,
        )

        return {
            "rankings": [
                {
                    "rank": i + 1,
                    "prompt_name": name,
                    "overall_score": result.overall_score(),
                    "metric_scores": {
                        m: result.mean_score(m) for m in result.metric_scores
                    },
                    "mean_latency_ms": result.mean_latency_ms,
                }
                for i, (name, result) in enumerate(ranked)
            ],
            "pairwise_comparisons": comparison,
            "best_prompt": ranked[0][0] if ranked else None,
        }

    @staticmethod
    def _statistical_comparison(
        results: dict[str, EvalRunResult],
        alpha: float = 0.05,
    ) -> list[dict[str, Any]]:
        # Perform pairwise Welch's t-test between prompt variants.
        comparisons: list[dict[str, Any]] = []
        names = list(results.keys())

        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                name_a, name_b = names[i], names[j]
                result_a, result_b = results[name_a], results[name_b]

                for metric_name in result_a.metric_scores:
                    scores_a = result_a.metric_scores[metric_name]
                    scores_b = result_b.metric_scores.get(metric_name, [])

                    if len(scores_a) < 2 or len(scores_b) < 2:
                        continue

                    # Welch's t-test (manual implementation)
                    mean_a = statistics.mean(scores_a)
                    mean_b = statistics.mean(scores_b)
                    var_a = statistics.variance(scores_a)
                    var_b = statistics.variance(scores_b)
                    n_a, n_b = len(scores_a), len(scores_b)

                    se = (var_a / n_a + var_b / n_b) ** 0.5
                    if se == 0:
                        continue

                    t_stat = (mean_a - mean_b) / se
                    # Rough p-value approximation (for proper testing use scipy)
                    df = min(n_a, n_b) - 1
                    p_value_approx = 2.0 * (1.0 / (1.0 + abs(t_stat)))

                    comparisons.append({
                        "prompt_a": name_a,
                        "prompt_b": name_b,
                        "metric": metric_name,
                        "mean_a": round(mean_a, 4),
                        "mean_b": round(mean_b, 4),
                        "t_statistic": round(t_stat, 4),
                        "p_value_approx": round(p_value_approx, 4),
                        "significant": p_value_approx < alpha,
                        "winner": name_a if mean_a > mean_b else name_b,
                    })

        return comparisons
```

### Iterative Prompt Refinement

```python
class PromptOptimizer:
    # Iteratively refines prompts using evaluation feedback.
    # Inspired by DSPy's approach of using LLMs to optimize LLM prompts.

    def __init__(
        self,
        evaluator: PromptEvaluator,
        optimizer_llm: Callable[[str], str],
        max_iterations: int = 5,
    ):
        self.evaluator = evaluator
        self.optimizer_llm = optimizer_llm
        self.max_iterations = max_iterations
        self.history: list[dict[str, Any]] = []

    def optimize(
        self,
        initial_prompt: str,
        system_prompt: str = "",
        target_score: float = 0.9,
    ) -> dict[str, Any]:
        # Iteratively improve a prompt template using LLM-driven refinement.
        current_prompt = initial_prompt
        best_prompt = initial_prompt
        best_score = 0.0

        for iteration in range(self.max_iterations):
            # Evaluate current prompt
            result = self.evaluator.evaluate_prompt(
                prompt_name=f"iteration_{iteration}",
                prompt_template=current_prompt,
                system_prompt=system_prompt,
            )
            current_score = result.overall_score()

            # Track history
            self.history.append({
                "iteration": iteration,
                "prompt": current_prompt,
                "score": current_score,
                "metric_details": {
                    m: result.mean_score(m) for m in result.metric_scores
                },
            })

            # Update best
            if current_score > best_score:
                best_score = current_score
                best_prompt = current_prompt

            # Check termination
            if current_score >= target_score:
                break

            # Generate improved prompt
            weakest_metrics = sorted(
                result.metric_scores.items(),
                key=lambda x: statistics.mean(x[1]) if x[1] else 0,
            )[:2]

            # Sample failure cases for feedback
            failure_examples = []
            for gen in result.generation_results[:3]:
                failure_examples.append(
                    f"Input: {gen.input_text[:200]}\n"
                    f"Output: {gen.output_text[:300]}"
                )

            refinement_prompt = (
                f"You are a prompt engineering expert. Improve this prompt template.\n\n"
                f"## Current Prompt Template\n{current_prompt}\n\n"
                f"## Current Score: {current_score:.3f} (target: {target_score})\n\n"
                f"## Weakest Metrics\n"
                + "\n".join(
                    f"- {name}: {statistics.mean(scores):.3f}"
                    for name, scores in weakest_metrics
                )
                + f"\n\n## Example Outputs (showing issues)\n"
                + "\n---\n".join(failure_examples)
                + f"\n\n## Instructions\n"
                f"Rewrite the prompt template to address the weak metrics. "
                f"Keep the {{input}} placeholder. Return ONLY the improved prompt template."
            )

            current_prompt = self.optimizer_llm(refinement_prompt)

        return {
            "best_prompt": best_prompt,
            "best_score": best_score,
            "iterations": len(self.history),
            "history": self.history,
            "improvement": best_score - self.history[0]["score"] if self.history else 0,
        }


# Usage example
def run_optimization_example(
    llm_fn: Callable[[str, str], str],
    judge_fn: Callable[[str], str],
    optimizer_fn: Callable[[str], str],
) -> dict[str, Any]:
    # Set up metrics
    metrics: list[EvalMetric] = [
        LengthAdequacyMetric(min_words=100, max_words=400),
        FormatComplianceMetric(required_elements=["however", "therefore", "in conclusion"]),
        LLMJudgeMetric(
            judge_llm=judge_fn,
            criteria=[
                "Factual accuracy",
                "Completeness of explanation",
                "Clarity and readability",
                "Logical structure",
            ],
        ),
    ]

    # Create test samples
    samples = [
        EvalSample(
            input_text="Explain how transformers use self-attention",
            expected_output=None,
            category="technical",
        ),
        EvalSample(
            input_text="What are the trade-offs between SQL and NoSQL databases?",
            expected_output=None,
            category="comparison",
        ),
    ]

    # Create evaluator and optimizer
    evaluator = PromptEvaluator(
        llm_call=llm_fn,
        metrics=metrics,
        samples=samples,
    )

    optimizer = PromptOptimizer(
        evaluator=evaluator,
        optimizer_llm=optimizer_fn,
        max_iterations=5,
    )

    # Run optimization
    result = optimizer.optimize(
        initial_prompt="Answer this question: {input}",
        system_prompt="You are a knowledgeable technical writer.",
        target_score=0.85,
    )

    return result
```

## Summary and Key Takeaways

- **Systematic evaluation** with automated metrics is non-negotiable for production prompt engineering **because** subjective evaluation is biased and does not scale. A **common mistake** is relying on manual review of a few examples rather than statistical measurement across representative samples.
- **LLM-as-judge** provides the best cost-quality **trade-off** for evaluating open-ended generation, **however** it requires bias mitigation: randomize presentation order, normalize for length, and use a different model family as judge. **Therefore**, always calibrate LLM judges against periodic human evaluation.
- **Pairwise comparison** is more reliable than absolute scoring for LLM judges **because** relative judgments are easier than calibrated ratings. Use pairwise comparison for prompt A/B testing and absolute scoring only when you need a single quality metric.
- **Statistical significance testing** (Welch's t-test or bootstrap confidence intervals) is the **best practice** for declaring a prompt variant the winner. Without significance testing, you risk selecting prompts that are better by random chance, which is a **pitfall** that leads to regression in production.
- **Iterative prompt refinement** using LLM-driven optimization (inspired by DSPy/APO) automates the prompt engineering cycle. The **trade-off** is evaluation budget — each iteration requires running the full evaluation suite, so target score thresholds and maximum iterations must be set carefully.
- **Metric design** should be task-specific: use accuracy for factual QA, pass@k for code generation, and multi-criteria LLM-as-judge for open-ended generation. Generic "quality" metrics are a **pitfall** that produces unreliable evaluations.
- **Best practice**: maintain a versioned prompt registry with evaluation scores, enabling rollback to previous versions if a new prompt degrades in production, and track prompt performance over time as model updates change behavior.
"""
    ),
]
