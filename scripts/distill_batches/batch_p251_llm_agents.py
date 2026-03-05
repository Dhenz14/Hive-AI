"""LLM agents and reasoning — chain-of-thought, ReAct, planning, tool orchestration."""

PAIRS = [
    (
        "ai/chain-of-thought",
        "Show chain-of-thought prompting patterns: zero-shot CoT, few-shot CoT, self-consistency, and tree-of-thought for complex reasoning.",
        '''Chain-of-thought reasoning patterns:

```python
from anthropic import Anthropic
from dataclasses import dataclass
import json
import re


@dataclass
class ReasoningResult:
    answer: str
    reasoning: str
    confidence: float


class ChainOfThought:
    """Chain-of-thought prompting for complex reasoning tasks."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic()
        self.model = model

    def zero_shot_cot(self, question: str) -> ReasoningResult:
        """Zero-shot CoT: just add 'think step by step'."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"{question}\\n\\nLet's think step by step.",
            }],
        )
        text = response.content[0].text
        # Extract final answer (usually after "Therefore" or "The answer is")
        answer = self._extract_answer(text)
        return ReasoningResult(answer=answer, reasoning=text, confidence=0.8)

    def few_shot_cot(self, question: str, examples: list[dict]) -> ReasoningResult:
        """Few-shot CoT: provide reasoning examples."""
        prompt = ""
        for ex in examples:
            prompt += f"Q: {ex['question']}\\n"
            prompt += f"A: Let me think through this step by step.\\n{ex['reasoning']}\\n"
            prompt += f"Therefore, the answer is {ex['answer']}.\\n\\n"

        prompt += f"Q: {question}\\nA: Let me think through this step by step.\\n"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        return ReasoningResult(
            answer=self._extract_answer(text),
            reasoning=text,
            confidence=0.85,
        )

    def self_consistency(self, question: str, n_samples: int = 5,
                         temperature: float = 0.7) -> ReasoningResult:
        """Self-consistency: sample multiple CoT paths, majority vote.

        Different reasoning paths may reach different answers.
        Take the most common answer (majority vote).
        """
        answers = []
        reasonings = []

        for _ in range(n_samples):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=temperature,
                messages=[{
                    "role": "user",
                    "content": f"{question}\\n\\nLet's think step by step. After reasoning, state your final answer clearly.",
                }],
            )
            text = response.content[0].text
            answer = self._extract_answer(text)
            answers.append(answer)
            reasonings.append(text)

        # Majority vote
        from collections import Counter
        vote = Counter(answers).most_common(1)[0]
        best_answer = vote[0]
        confidence = vote[1] / n_samples

        # Return reasoning from the path that matches majority
        best_idx = answers.index(best_answer)
        return ReasoningResult(
            answer=best_answer,
            reasoning=reasonings[best_idx],
            confidence=confidence,
        )

    def _extract_answer(self, text: str) -> str:
        patterns = [
            r"(?:the answer is|therefore|thus|so)[:\s]+(.+?)(?:\.|$)",
            r"(?:final answer)[:\s]+(.+?)(?:\.|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                return match.group(1).strip()
        # Fallback: last sentence
        sentences = text.strip().split(".")
        return sentences[-1].strip() if sentences else text


class TreeOfThought:
    """Tree-of-Thought: explore multiple reasoning branches."""

    def __init__(self, model: str = "claude-sonnet-4-6", beam_width: int = 3):
        self.client = Anthropic()
        self.model = model
        self.beam_width = beam_width

    def solve(self, problem: str, n_steps: int = 3) -> dict:
        """BFS-style tree search over reasoning steps."""
        # Start with initial thoughts
        current_paths = [{"steps": [], "problem": problem}]

        for step in range(n_steps):
            candidates = []
            for path in current_paths:
                # Generate possible next steps
                next_steps = self._generate_thoughts(path)
                for thought in next_steps:
                    new_path = {
                        "steps": path["steps"] + [thought],
                        "problem": problem,
                    }
                    score = self._evaluate_thought(new_path)
                    candidates.append((score, new_path))

            # Keep top-k paths (beam search)
            candidates.sort(key=lambda x: x[0], reverse=True)
            current_paths = [c[1] for c in candidates[:self.beam_width]]

        # Select best final path
        best = current_paths[0]
        return {
            "steps": best["steps"],
            "answer": self._extract_final(best),
        }

    def _generate_thoughts(self, path: dict) -> list[str]:
        """Generate possible next reasoning steps."""
        context = f"Problem: {path['problem']}\\n"
        if path["steps"]:
            context += "Steps so far:\\n" + "\\n".join(f"- {s}" for s in path["steps"])
        context += "\\n\\nGenerate 3 possible next reasoning steps. Output as JSON array."

        response = self.client.messages.create(
            model=self.model, max_tokens=512,
            messages=[{"role": "user", "content": context}],
        )
        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return [response.content[0].text]

    def _evaluate_thought(self, path: dict) -> float:
        """Score a reasoning path (0-1)."""
        context = f"Problem: {path['problem']}\\nReasoning:\\n"
        context += "\\n".join(f"{i+1}. {s}" for i, s in enumerate(path["steps"]))
        context += "\\n\\nRate this reasoning path from 0.0 to 1.0 for correctness and progress. Output just the number."

        response = self.client.messages.create(
            model=self.model, max_tokens=10,
            messages=[{"role": "user", "content": context}],
        )
        try:
            return float(response.content[0].text.strip())
        except ValueError:
            return 0.5

    def _extract_final(self, path: dict) -> str:
        return path["steps"][-1] if path["steps"] else ""
```

Reasoning comparison:

| Method | Accuracy boost | Cost | Use case |
|--------|---------------|------|----------|
| **Zero-shot CoT** | +10-15% | 1x | Simple reasoning |
| **Few-shot CoT** | +15-25% | 1x | Complex reasoning |
| **Self-consistency** | +5-10% over CoT | Nx | Math, logic |
| **Tree-of-Thought** | +10-20% over CoT | N²x | Planning, puzzles |

Key patterns:
1. **Zero-shot CoT** — "think step by step" elicits reasoning without examples
2. **Self-consistency** — multiple samples + majority vote; reduces reasoning errors
3. **Tree-of-Thought** — beam search over reasoning branches; explore alternatives
4. **Answer extraction** — regex patterns find final answer in reasoning trace
5. **Temperature sampling** — higher temperature for diversity in self-consistency'''
    ),
    (
        "ai/react-agents",
        "Show ReAct (Reasoning + Acting) agent pattern: interleaved thought-action-observation loops, tool selection, and error recovery.",
        '''ReAct agent — interleaved reasoning and action:

```python
import json
from dataclasses import dataclass
from typing import Any, Callable
from anthropic import Anthropic


@dataclass
class Thought:
    text: str

@dataclass
class Action:
    tool: str
    input: dict

@dataclass
class Observation:
    result: Any
    error: str | None = None


class ReActAgent:
    """ReAct: interleave Thought → Action → Observation.

    The key insight: explicit reasoning (Thought) before each Action
    improves tool selection and error recovery.
    """

    def __init__(self, tools: dict[str, Callable], model: str = "claude-sonnet-4-6",
                 max_steps: int = 10):
        self.tools = tools
        self.client = Anthropic()
        self.model = model
        self.max_steps = max_steps

    def run(self, task: str) -> str:
        """Execute ReAct loop until task is complete."""
        trace: list[Thought | Action | Observation] = []
        tool_descriptions = self._format_tools()

        for step in range(self.max_steps):
            # Get next thought + action from LLM
            prompt = self._build_prompt(task, trace, tool_descriptions)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system="You are a ReAct agent. For each step, output EXACTLY:\nThought: <your reasoning>\nAction: <tool_name>\nAction Input: <json input>\n\nOr if you have the final answer:\nThought: <reasoning>\nFinal Answer: <your answer>",
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text

            # Parse thought
            thought_match = self._extract("Thought:", text)
            if thought_match:
                trace.append(Thought(thought_match))

            # Check for final answer
            final = self._extract("Final Answer:", text)
            if final:
                return final

            # Parse action
            action_name = self._extract("Action:", text)
            action_input_str = self._extract("Action Input:", text)

            if not action_name:
                trace.append(Observation(result=None, error="No action specified"))
                continue

            # Execute action
            try:
                action_input = json.loads(action_input_str) if action_input_str else {}
                action = Action(tool=action_name.strip(), input=action_input)
                trace.append(action)

                if action.tool not in self.tools:
                    obs = Observation(result=None, error=f"Unknown tool: {action.tool}")
                else:
                    result = self.tools[action.tool](**action.input)
                    obs = Observation(result=result)

            except Exception as e:
                obs = Observation(result=None, error=str(e))

            trace.append(obs)

        return "Max steps reached without final answer."

    def _build_prompt(self, task: str, trace: list, tools: str) -> str:
        prompt = f"Task: {task}\\n\\nAvailable tools:\\n{tools}\\n\\n"

        for item in trace:
            if isinstance(item, Thought):
                prompt += f"Thought: {item.text}\\n"
            elif isinstance(item, Action):
                prompt += f"Action: {item.tool}\\nAction Input: {json.dumps(item.input)}\\n"
            elif isinstance(item, Observation):
                if item.error:
                    prompt += f"Observation: ERROR - {item.error}\\n"
                else:
                    result_str = json.dumps(item.result, default=str)[:2000]
                    prompt += f"Observation: {result_str}\\n"

        prompt += "\\nWhat is your next step?"
        return prompt

    def _format_tools(self) -> str:
        lines = []
        for name, fn in self.tools.items():
            doc = fn.__doc__ or "No description"
            lines.append(f"- {name}: {doc.strip().split(chr(10))[0]}")
        return "\\n".join(lines)

    def _extract(self, prefix: str, text: str) -> str | None:
        for line in text.split("\\n"):
            if line.strip().startswith(prefix):
                return line.strip()[len(prefix):].strip()
        return None
```

Key patterns:
1. **Thought-Action-Observation** — explicit reasoning before each tool call improves decisions
2. **Error recovery** — observations include errors; agent can reason about failures and retry
3. **Trace building** — full history in prompt enables multi-step reasoning about past results
4. **Final Answer signal** — explicit "Final Answer:" stops the loop; prevents infinite actions
5. **Tool description** — clear tool descriptions help the agent select the right tool'''
    ),
    (
        "ai/planning-agents",
        "Show LLM planning patterns: task decomposition, plan-and-execute, hierarchical planning, and plan refinement.",
        '''LLM planning and task decomposition:

```python
import json
from dataclasses import dataclass, field
from anthropic import Anthropic


@dataclass
class Step:
    id: int
    description: str
    dependencies: list[int] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    result: str = ""


@dataclass
class Plan:
    goal: str
    steps: list[Step]
    current_step: int = 0


class PlanAndExecuteAgent:
    """Plan-and-Execute: create full plan first, then execute step by step.

    Unlike ReAct (think-act each step), this creates a complete plan upfront.
    The plan can be revised based on execution results.
    """

    def __init__(self, executor_fn, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic()
        self.model = model
        self.executor = executor_fn

    def create_plan(self, goal: str) -> Plan:
        """Decompose goal into ordered steps with dependencies."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"""Break down this goal into concrete, executable steps:

Goal: {goal}

Output as JSON:
{{
    "steps": [
        {{"id": 1, "description": "...", "dependencies": []}},
        {{"id": 2, "description": "...", "dependencies": [1]}},
        ...
    ]
}}

Rules:
- Each step should be a single, concrete action
- Include dependencies (which steps must complete first)
- Order by dependency (steps with no deps first)
- Be specific enough that each step can be executed independently""",
            }],
        )

        try:
            data = json.loads(response.content[0].text)
            steps = [Step(id=s["id"], description=s["description"],
                         dependencies=s.get("dependencies", []))
                     for s in data["steps"]]
        except (json.JSONDecodeError, KeyError):
            steps = [Step(id=1, description=goal)]

        return Plan(goal=goal, steps=steps)

    def execute_plan(self, plan: Plan) -> dict:
        """Execute plan step by step, revising if needed."""
        results = {}

        while plan.current_step < len(plan.steps):
            step = plan.steps[plan.current_step]

            # Check dependencies
            deps_met = all(
                plan.steps[d - 1].status == "completed"
                for d in step.dependencies
                if d <= len(plan.steps)
            )

            if not deps_met:
                step.status = "failed"
                step.result = "Dependencies not met"
                plan.current_step += 1
                continue

            # Execute step
            step.status = "running"
            context = self._build_context(plan, step)

            try:
                result = self.executor(step.description, context)
                step.status = "completed"
                step.result = str(result)
                results[step.id] = result
            except Exception as e:
                step.status = "failed"
                step.result = str(e)

                # Revise plan on failure
                revised = self.revise_plan(plan, step, str(e))
                if revised:
                    plan = revised
                    continue

            plan.current_step += 1

        return {
            "goal": plan.goal,
            "results": results,
            "success": all(s.status == "completed" for s in plan.steps),
        }

    def revise_plan(self, plan: Plan, failed_step: Step, error: str) -> Plan | None:
        """Revise plan when a step fails."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"""A step in our plan failed. Revise the remaining steps.

Original goal: {plan.goal}

Completed steps:
{json.dumps([{"id": s.id, "desc": s.description, "result": s.result} for s in plan.steps if s.status == "completed"], indent=2)}

Failed step: {failed_step.description}
Error: {error}

Remaining steps:
{json.dumps([{"id": s.id, "desc": s.description} for s in plan.steps if s.status == "pending"], indent=2)}

Output revised remaining steps as JSON (same format). If the goal is impossible, output {{"impossible": true, "reason": "..."}}""",
            }],
        )

        try:
            data = json.loads(response.content[0].text)
            if data.get("impossible"):
                return None
            # Rebuild plan with completed steps + revised remaining
            completed = [s for s in plan.steps if s.status == "completed"]
            revised_steps = [Step(id=s["id"], description=s["description"],
                                 dependencies=s.get("dependencies", []))
                           for s in data.get("steps", [])]
            new_plan = Plan(goal=plan.goal, steps=completed + revised_steps,
                          current_step=len(completed))
            return new_plan
        except (json.JSONDecodeError, KeyError):
            return None

    def _build_context(self, plan: Plan, step: Step) -> str:
        completed = [s for s in plan.steps if s.status == "completed"]
        context = f"Goal: {plan.goal}\\n\\nCompleted:\\n"
        for s in completed:
            context += f"- Step {s.id}: {s.description} -> {s.result[:200]}\\n"
        context += f"\\nCurrent: {step.description}"
        return context
```

Planning comparison:

| Pattern | When to use | Overhead |
|---------|------------|---------|
| **ReAct** | Dynamic, uncertain tasks | Low (step-by-step) |
| **Plan-and-Execute** | Well-defined goals | Medium (upfront plan) |
| **Hierarchical** | Complex multi-phase projects | High |
| **Iterative refinement** | Research/exploration | Medium |

Key patterns:
1. **Upfront planning** — decompose goal into steps before execution; better for well-defined tasks
2. **Dependency graph** — steps specify which prior steps must complete; enables parallel execution
3. **Plan revision** — when a step fails, revise remaining steps instead of failing entirely
4. **Context passing** — each step receives results from prior steps for informed execution
5. **Goal decomposition** — LLM breaks complex goals into concrete, executable substeps'''
    ),
    (
        "ai/rag-advanced",
        "Show advanced RAG (Retrieval-Augmented Generation) patterns: hybrid search, reranking, query expansion, and contextual compression.",
        '''Advanced RAG patterns:

```python
import numpy as np
from dataclasses import dataclass
from typing import Optional
from anthropic import Anthropic


@dataclass
class Document:
    id: str
    content: str
    metadata: dict
    embedding: Optional[np.ndarray] = None
    score: float = 0.0


class HybridRetriever:
    """Combine dense (vector) and sparse (BM25) retrieval."""

    def __init__(self, embed_fn, alpha: float = 0.7):
        self.embed_fn = embed_fn
        self.alpha = alpha  # Weight for dense retrieval
        self.documents: list[Document] = []

    def add_documents(self, docs: list[Document]):
        for doc in docs:
            doc.embedding = self.embed_fn(doc.content)
            self.documents.append(doc)

    def search(self, query: str, top_k: int = 10) -> list[Document]:
        """Hybrid search: weighted combination of dense and sparse scores."""
        query_embedding = self.embed_fn(query)
        query_tokens = set(query.lower().split())

        scored = []
        for doc in self.documents:
            # Dense score: cosine similarity
            dense_score = np.dot(query_embedding, doc.embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(doc.embedding) + 1e-8
            )

            # Sparse score: simple BM25-like TF matching
            doc_tokens = doc.content.lower().split()
            overlap = sum(1 for t in doc_tokens if t in query_tokens)
            sparse_score = overlap / (len(doc_tokens) + 1)

            # Hybrid score
            doc.score = self.alpha * dense_score + (1 - self.alpha) * sparse_score
            scored.append(doc)

        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:top_k]


class QueryExpander:
    """Expand user query for better retrieval coverage."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic()
        self.model = model

    def expand(self, query: str, n_expansions: int = 3) -> list[str]:
        """Generate query variations to improve recall."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"Generate {n_expansions} alternative phrasings of this search query. "
                           f"Each should capture a different aspect or use different terminology.\\n\\n"
                           f"Query: {query}\\n\\nOutput as JSON array of strings.",
            }],
        )
        import json
        try:
            expansions = json.loads(response.content[0].text)
            return [query] + expansions
        except json.JSONDecodeError:
            return [query]


class Reranker:
    """Cross-encoder reranker for retrieved documents."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic()
        self.model = model

    def rerank(self, query: str, documents: list[Document], top_k: int = 5) -> list[Document]:
        """Rerank documents using LLM relevance scoring."""
        doc_list = "\\n".join(
            f"[{i}] {doc.content[:300]}" for i, doc in enumerate(documents)
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"Rate relevance of each document to the query (0-10).\\n\\n"
                           f"Query: {query}\\n\\nDocuments:\\n{doc_list}\\n\\n"
                           f"Output JSON: {{\"scores\": [score_0, score_1, ...]}}",
            }],
        )

        import json
        try:
            data = json.loads(response.content[0].text)
            scores = data["scores"]
            for i, doc in enumerate(documents):
                if i < len(scores):
                    doc.score = scores[i]
        except (json.JSONDecodeError, KeyError):
            pass

        documents.sort(key=lambda d: d.score, reverse=True)
        return documents[:top_k]


class ContextualCompressor:
    """Compress retrieved documents to only include relevant portions."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic()
        self.model = model

    def compress(self, query: str, documents: list[Document]) -> list[Document]:
        """Extract only query-relevant portions from each document."""
        compressed = []
        for doc in documents:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": f"Extract ONLY the portions relevant to the query. "
                               f"Remove irrelevant information.\\n\\n"
                               f"Query: {query}\\n\\nDocument: {doc.content[:1500]}\\n\\n"
                               f"Relevant extract:",
                }],
            )
            compressed_doc = Document(
                id=doc.id,
                content=response.content[0].text,
                metadata=doc.metadata,
                score=doc.score,
            )
            compressed.append(compressed_doc)
        return compressed


class AdvancedRAGPipeline:
    """Full advanced RAG pipeline."""

    def __init__(self, retriever, reranker=None, compressor=None, expander=None):
        self.retriever = retriever
        self.reranker = reranker
        self.expander = expander
        self.compressor = compressor
        self.client = Anthropic()

    def query(self, question: str) -> str:
        # Step 1: Query expansion
        queries = [question]
        if self.expander:
            queries = self.expander.expand(question)

        # Step 2: Retrieve (merge results from all query variants)
        all_docs = {}
        for q in queries:
            for doc in self.retriever.search(q, top_k=10):
                if doc.id not in all_docs or doc.score > all_docs[doc.id].score:
                    all_docs[doc.id] = doc
        docs = list(all_docs.values())

        # Step 3: Rerank
        if self.reranker:
            docs = self.reranker.rerank(question, docs, top_k=5)
        else:
            docs = sorted(docs, key=lambda d: d.score, reverse=True)[:5]

        # Step 4: Compress
        if self.compressor:
            docs = self.compressor.compress(question, docs)

        # Step 5: Generate
        context = "\\n\\n---\\n\\n".join(d.content for d in docs)
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"Answer based on the context below.\\n\\nContext:\\n{context}\\n\\nQuestion: {question}",
            }],
        )
        return response.content[0].text
```

RAG pipeline stages:

| Stage | Technique | Purpose |
|-------|-----------|---------|
| **Query expansion** | LLM generates variations | Improve recall |
| **Retrieval** | Hybrid (dense + sparse) | Find candidates |
| **Reranking** | Cross-encoder scoring | Improve precision |
| **Compression** | Extract relevant portions | Reduce noise |
| **Generation** | LLM with context | Final answer |

Key patterns:
1. **Hybrid search** — combine vector similarity and keyword matching; better recall than either alone
2. **Query expansion** — generate alternative phrasings to capture different terminology
3. **Reranking** — cross-encoder scores (query, doc) pairs; more accurate than bi-encoder
4. **Contextual compression** — remove irrelevant text from retrieved docs; reduces noise in generation
5. **Reciprocal rank fusion** — merge results from multiple queries using rank-based scoring'''
    ),
]
"""
