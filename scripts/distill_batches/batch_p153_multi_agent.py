"""Multi-agent systems — orchestration, communication, and specialized agent patterns."""

PAIRS = [
    (
        "ai/multi-agent-orchestration",
        "Show multi-agent system patterns: orchestrator-worker architecture, agent communication, task decomposition, and consensus.",
        '''Multi-agent orchestration patterns:

```python
import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from anthropic import AsyncAnthropic


# === Agent Roles and Messages ===

class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"


@dataclass
class AgentMessage:
    """Message passed between agents."""
    sender: AgentRole
    receiver: AgentRole
    content: str
    metadata: dict = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)  # filename -> content


@dataclass
class Task:
    """A unit of work assigned to an agent."""
    id: str
    description: str
    assigned_to: AgentRole
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed, failed
    result: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)


# === Specialized Agents ===

class BaseAgent:
    """Base class for specialized agents."""

    def __init__(self, role: AgentRole, model: str = "claude-sonnet-4-6"):
        self.role = role
        self.model = model
        self.client = AsyncAnthropic()
        self.context: list[AgentMessage] = []

    async def process(self, task: Task, context: list[AgentMessage]) -> AgentMessage:
        """Process a task and return a message with results."""
        system_prompt = self._get_system_prompt()

        # Build conversation from context messages relevant to this agent
        messages = self._build_messages(task, context)

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )

        result_text = response.content[0].text
        artifacts = self._extract_artifacts(result_text)

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.ORCHESTRATOR,
            content=result_text,
            artifacts=artifacts,
        )

    def _get_system_prompt(self) -> str:
        prompts = {
            AgentRole.PLANNER: (
                "You are a software architect. Break down tasks into clear, "
                "actionable steps. Identify dependencies between steps. "
                "Output a numbered plan with file paths and descriptions."
            ),
            AgentRole.CODER: (
                "You are an expert programmer. Write clean, production-quality code. "
                "Include type hints, error handling, and follow best practices. "
                "Wrap code in ```filename.py\\n...``` blocks."
            ),
            AgentRole.REVIEWER: (
                "You are a senior code reviewer. Check for bugs, security issues, "
                "performance problems, and style violations. Be specific about "
                "line numbers and suggest concrete fixes."
            ),
            AgentRole.TESTER: (
                "You are a QA engineer. Write comprehensive tests covering "
                "happy paths, edge cases, and error conditions. Use pytest. "
                "Wrap tests in ```test_*.py\\n...``` blocks."
            ),
        }
        return prompts.get(self.role, "You are a helpful assistant.")

    def _build_messages(self, task: Task, context: list[AgentMessage]) -> list[dict]:
        relevant = [m for m in context if m.receiver == self.role or m.sender == self.role]

        messages = []
        for msg in relevant[-5:]:  # Last 5 relevant messages
            role = "assistant" if msg.sender == self.role else "user"
            content = msg.content
            if msg.artifacts:
                content += "\\n\\nArtifacts:\\n" + "\\n".join(
                    f"```{name}\\n{code}\\n```" for name, code in msg.artifacts.items()
                )
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": f"Task: {task.description}"})
        return messages

    def _extract_artifacts(self, text: str) -> dict[str, str]:
        """Extract code blocks tagged with filenames."""
        import re
        artifacts = {}
        pattern = r"```(\S+\.(?:py|ts|js|yaml|sql))\n(.*?)```"
        for match in re.finditer(pattern, text, re.DOTALL):
            artifacts[match.group(1)] = match.group(2).strip()
        return artifacts


# === Orchestrator ===

class Orchestrator:
    """Coordinates multiple agents to complete complex tasks.

    Flow:
    1. Planner decomposes task into subtasks
    2. Orchestrator assigns subtasks to specialists
    3. Agents execute in dependency order (parallel when possible)
    4. Reviewer validates outputs
    5. Loop if review finds issues
    """

    def __init__(self):
        self.agents: dict[AgentRole, BaseAgent] = {
            AgentRole.PLANNER: BaseAgent(AgentRole.PLANNER),
            AgentRole.CODER: BaseAgent(AgentRole.CODER),
            AgentRole.REVIEWER: BaseAgent(AgentRole.REVIEWER),
            AgentRole.TESTER: BaseAgent(AgentRole.TESTER),
        }
        self.message_log: list[AgentMessage] = []
        self.tasks: list[Task] = []

    async def execute(self, user_request: str, max_iterations: int = 3) -> dict:
        """Execute multi-agent workflow."""

        # Step 1: Plan
        plan_task = Task(
            id="plan",
            description=f"Create implementation plan for: {user_request}",
            assigned_to=AgentRole.PLANNER,
        )
        plan_result = await self._run_agent(AgentRole.PLANNER, plan_task)
        subtasks = self._parse_plan(plan_result.content)

        # Step 2: Execute subtasks (respect dependencies)
        all_artifacts = {}
        for iteration in range(max_iterations):
            # Run independent tasks in parallel
            pending = [t for t in subtasks if t.status == "pending"]
            ready = [t for t in pending if self._deps_met(t, subtasks)]

            if not ready:
                break

            results = await asyncio.gather(*[
                self._run_agent(t.assigned_to, t) for t in ready
            ])

            for task, result in zip(ready, results):
                task.status = "completed"
                task.result = result.content
                task.artifacts = result.artifacts
                all_artifacts.update(result.artifacts)

            # Step 3: Review completed code
            if all_artifacts:
                review_task = Task(
                    id=f"review_{iteration}",
                    description=(
                        f"Review this code for bugs, security issues, and quality:\\n\\n"
                        + "\\n\\n".join(
                            f"```{name}\\n{code}\\n```"
                            for name, code in all_artifacts.items()
                        )
                    ),
                    assigned_to=AgentRole.REVIEWER,
                )
                review = await self._run_agent(AgentRole.REVIEWER, review_task)

                # If review passes, break
                if "approve" in review.content.lower():
                    break

                # Otherwise, create fix tasks from review feedback
                fix_task = Task(
                    id=f"fix_{iteration}",
                    description=f"Fix issues found in review:\\n{review.content}",
                    assigned_to=AgentRole.CODER,
                )
                fix_result = await self._run_agent(AgentRole.CODER, fix_task)
                all_artifacts.update(fix_result.artifacts)

        # Step 4: Generate tests
        test_task = Task(
            id="tests",
            description=(
                "Write tests for:\\n\\n"
                + "\\n\\n".join(
                    f"```{name}\\n{code}\\n```"
                    for name, code in all_artifacts.items()
                )
            ),
            assigned_to=AgentRole.TESTER,
        )
        test_result = await self._run_agent(AgentRole.TESTER, test_task)
        all_artifacts.update(test_result.artifacts)

        return {
            "artifacts": all_artifacts,
            "messages": len(self.message_log),
            "iterations": iteration + 1,
        }

    async def _run_agent(self, role: AgentRole, task: Task) -> AgentMessage:
        """Run a specific agent on a task."""
        agent = self.agents[role]
        task.status = "in_progress"
        result = await agent.process(task, self.message_log)
        self.message_log.append(result)
        return result

    def _deps_met(self, task: Task, all_tasks: list[Task]) -> bool:
        """Check if all dependencies are completed."""
        for dep_id in task.dependencies:
            dep = next((t for t in all_tasks if t.id == dep_id), None)
            if dep and dep.status != "completed":
                return False
        return True

    def _parse_plan(self, plan_text: str) -> list[Task]:
        """Parse planner output into structured tasks."""
        tasks = []
        for i, line in enumerate(plan_text.split("\\n")):
            line = line.strip()
            if line and line[0].isdigit() and "." in line:
                desc = line.split(".", 1)[1].strip()
                # Assign role based on keywords
                role = AgentRole.CODER
                if any(w in desc.lower() for w in ["test", "spec", "assert"]):
                    role = AgentRole.TESTER
                tasks.append(Task(
                    id=f"task_{i}",
                    description=desc,
                    assigned_to=role,
                ))
        return tasks


# === Fan-out / Fan-in Pattern ===

async def parallel_analysis(code: str) -> dict:
    """Run multiple specialized agents in parallel on the same code.

    Fan-out: dispatch to N agents simultaneously
    Fan-in: aggregate results into unified report
    """
    agents = {
        "security": BaseAgent(AgentRole.REVIEWER),
        "performance": BaseAgent(AgentRole.REVIEWER),
        "testing": BaseAgent(AgentRole.TESTER),
    }

    tasks = {
        "security": Task(
            id="security", assigned_to=AgentRole.REVIEWER,
            description=f"Security audit this code. Find OWASP top 10 vulnerabilities:\\n{code}",
        ),
        "performance": Task(
            id="performance", assigned_to=AgentRole.REVIEWER,
            description=f"Performance review. Find N+1 queries, memory leaks, blocking calls:\\n{code}",
        ),
        "testing": Task(
            id="testing", assigned_to=AgentRole.TESTER,
            description=f"Generate comprehensive test suite for:\\n{code}",
        ),
    }

    # Fan-out: all agents run simultaneously
    results = await asyncio.gather(*[
        agents[name].process(task, [])
        for name, task in tasks.items()
    ])

    # Fan-in: aggregate into single report
    return {
        name: result.content
        for name, result in zip(tasks.keys(), results)
    }
```

Multi-agent architecture patterns:

| Pattern | Flow | Best for |
|---------|------|----------|
| **Orchestrator-Worker** | Central coordinator dispatches to specialists | Complex multi-step tasks |
| **Fan-out / Fan-in** | Parallel analysis, aggregate results | Independent analyses |
| **Pipeline** | Agent A → Agent B → Agent C | Sequential refinement |
| **Debate** | Agents argue, consensus emerges | Difficult decisions |
| **Hierarchical** | Manager → sub-managers → workers | Large-scale decomposition |

Key patterns:
1. **Role-specialized agents** — each agent has a focused system prompt and expertise; specialists outperform generalists
2. **Dependency-aware scheduling** — `asyncio.gather` for independent tasks; sequential for dependent steps
3. **Review-fix loop** — reviewer validates, coder fixes, repeat until approval; catches bugs iteratively
4. **Artifact passing** — code files extracted from agent responses and passed to downstream agents
5. **Context windowing** — each agent sees only relevant messages (last 5); prevents context overflow in long workflows'''
    ),
    (
        "ai/agent-memory-rag",
        "Show agent memory patterns: conversation memory, RAG for long-term knowledge, episodic memory, and tool-augmented retrieval.",
        '''Agent memory and RAG patterns:

```python
import hashlib
import time
import json
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path


# === Memory Types ===

@dataclass
class MemoryEntry:
    """A single memory with metadata."""
    id: str
    content: str
    memory_type: str        # "conversation", "episodic", "semantic", "procedural"
    timestamp: float
    importance: float = 0.5  # 0-1 relevance score
    access_count: int = 0
    last_accessed: float = 0
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None


class AgentMemory:
    """Multi-tier memory system for LLM agents.

    Tiers:
    1. Working memory: current conversation context (in-context)
    2. Short-term: recent interactions (sliding window)
    3. Long-term: persistent knowledge (vector store + SQLite)
    """

    def __init__(
        self,
        working_memory_limit: int = 10,     # Messages in context
        short_term_limit: int = 100,         # Recent memories
        embedding_model: str = "text-embedding-3-small",
    ):
        self.working_memory: list[dict] = []
        self.short_term: list[MemoryEntry] = []
        self.long_term: list[MemoryEntry] = []  # In production: vector DB
        self.working_memory_limit = working_memory_limit
        self.short_term_limit = short_term_limit

    def add_conversation(self, role: str, content: str):
        """Add to working memory with overflow to short-term."""
        self.working_memory.append({"role": role, "content": content})

        # Overflow: summarize and move to short-term
        if len(self.working_memory) > self.working_memory_limit:
            overflow = self.working_memory[:2]  # Oldest messages
            self.working_memory = self.working_memory[2:]

            summary = self._summarize(overflow)
            self.add_memory(summary, "conversation", importance=0.3)

    def add_memory(
        self,
        content: str,
        memory_type: str = "semantic",
        importance: float = 0.5,
        metadata: dict | None = None,
    ):
        """Add a memory to short-term store."""
        entry = MemoryEntry(
            id=hashlib.sha256(content.encode()).hexdigest()[:16],
            content=content,
            memory_type=memory_type,
            timestamp=time.time(),
            importance=importance,
            metadata=metadata or {},
        )

        self.short_term.append(entry)

        # Promote important memories to long-term
        if importance >= 0.7:
            self.long_term.append(entry)

        # Evict least important short-term memories
        if len(self.short_term) > self.short_term_limit:
            self.short_term.sort(key=lambda m: self._memory_score(m))
            self.short_term = self.short_term[10:]  # Remove bottom 10

    def recall(
        self,
        query: str,
        top_k: int = 5,
        memory_types: list[str] | None = None,
        recency_weight: float = 0.3,
    ) -> list[MemoryEntry]:
        """Retrieve relevant memories using hybrid scoring.

        Score = similarity * (1 - recency_weight) + recency * recency_weight + importance * 0.1
        """
        query_embedding = self._embed(query)
        candidates = self.short_term + self.long_term

        if memory_types:
            candidates = [m for m in candidates if m.memory_type in memory_types]

        scored = []
        now = time.time()
        for memory in candidates:
            mem_embedding = memory.embedding or self._embed(memory.content)
            memory.embedding = mem_embedding  # Cache

            # Cosine similarity
            similarity = np.dot(query_embedding, mem_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(mem_embedding) + 1e-8
            )

            # Recency: exponential decay (half-life = 1 hour)
            age_hours = (now - memory.timestamp) / 3600
            recency = np.exp(-0.693 * age_hours)  # Half-life decay

            # Combined score
            score = (
                similarity * (1 - recency_weight)
                + recency * recency_weight
                + memory.importance * 0.1
            )

            scored.append((score, memory))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Update access metadata
        results = []
        for score, memory in scored[:top_k]:
            memory.access_count += 1
            memory.last_accessed = now
            results.append(memory)

        return results

    def _memory_score(self, memory: MemoryEntry) -> float:
        """Score for eviction (lower = more likely to evict)."""
        now = time.time()
        age = (now - memory.timestamp) / 3600
        return memory.importance * 0.5 + memory.access_count * 0.3 - age * 0.2

    def _embed(self, text: str) -> list[float]:
        """Get embedding vector. In production, use API or local model."""
        # Placeholder — use sentence-transformers or OpenAI embeddings
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        return [float(b) / 255.0 for b in h[:64]]  # Fake 64-dim embedding

    def _summarize(self, messages: list[dict]) -> str:
        """Summarize messages for compression."""
        return f"Summary of {len(messages)} messages: " + "; ".join(
            m["content"][:100] for m in messages
        )

    def get_context_window(self, query: str) -> list[dict]:
        """Build optimal context window for LLM call.

        Combines: working memory + recalled long-term memories + system context
        """
        # Recall relevant long-term memories
        recalled = self.recall(query, top_k=3)
        memory_context = "\\n".join(
            f"[Memory: {m.memory_type}] {m.content}" for m in recalled
        )

        context = []
        if memory_context:
            context.append({
                "role": "user",
                "content": f"Relevant context from memory:\\n{memory_context}",
            })

        # Add working memory (recent conversation)
        context.extend(self.working_memory)

        return context


# === RAG (Retrieval-Augmented Generation) ===

class RAGPipeline:
    """Production RAG pipeline with chunking, retrieval, and generation."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.documents: list[dict] = []  # In production: vector DB

    def ingest(self, text: str, source: str, metadata: dict | None = None):
        """Chunk and index a document."""
        chunks = self._chunk_text(text)

        for i, chunk in enumerate(chunks):
            self.documents.append({
                "id": f"{source}:chunk_{i}",
                "content": chunk,
                "source": source,
                "embedding": self._embed(chunk),
                "metadata": {**(metadata or {}), "chunk_index": i},
            })

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = True,
    ) -> list[dict]:
        """Retrieve relevant chunks with optional reranking."""
        query_embedding = self._embed(query)

        # Stage 1: Vector similarity (fast, approximate)
        scored = []
        for doc in self.documents:
            similarity = np.dot(query_embedding, doc["embedding"]) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(doc["embedding"]) + 1e-8
            )
            scored.append((similarity, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = [doc for _, doc in scored[:top_k * 3]]  # Over-fetch for reranking

        if rerank and len(candidates) > top_k:
            # Stage 2: Cross-encoder reranking (slower, more accurate)
            candidates = self._rerank(query, candidates, top_k)

        return candidates[:top_k]

    def query(self, question: str, top_k: int = 5) -> str:
        """Full RAG pipeline: retrieve + generate."""
        chunks = self.retrieve(question, top_k)

        context = "\\n\\n---\\n\\n".join(
            f"[Source: {c['source']}]\\n{c['content']}" for c in chunks
        )

        prompt = f"""Answer based on the provided context. If the context doesn't contain
the answer, say so. Cite sources.

Context:
{context}

Question: {question}

Answer:"""

        # In production: call LLM API here
        return prompt  # Return prompt for demonstration

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks at sentence boundaries."""
        sentences = text.replace("\\n", " ").split(". ")
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence = sentence.strip() + "."
            if current_length + len(sentence) > self.chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                # Keep overlap
                overlap_sentences = current_chunk[-2:]  # Last 2 sentences
                current_chunk = overlap_sentences
                current_length = sum(len(s) for s in current_chunk)

            current_chunk.append(sentence)
            current_length += len(sentence)

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _embed(self, text: str) -> list[float]:
        """Placeholder embedding."""
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        return [float(b) / 255.0 for b in h[:64]]

    def _rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """Cross-encoder reranking for better precision."""
        # In production: use cross-encoder model (e.g., ms-marco-MiniLM)
        return candidates[:top_k]
```

Memory architecture:
```
Query → Working Memory (last 10 messages, in-context)
      → Short-term (last 100 entries, recency-weighted)
      → Long-term (vector store, importance-filtered)
      → RAG (external docs, chunked + embedded)
      → Combined context → LLM
```

Key patterns:
1. **Tiered memory** — working (in-context) → short-term (sliding window) → long-term (vector store) mirrors human memory
2. **Hybrid scoring** — combine semantic similarity + recency decay + importance for balanced recall
3. **Memory promotion** — high-importance short-term memories auto-promote to long-term storage
4. **Context window assembly** — recalled memories + working memory + system prompt fit within token limits
5. **Chunked RAG** — overlap chunks at sentence boundaries; over-fetch then rerank for better precision'''
    ),
]
