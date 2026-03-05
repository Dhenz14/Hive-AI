"""Advanced prompt engineering — structured output, multi-turn, tool use."""

PAIRS = [
    (
        "ai/structured-output",
        "Show structured output extraction from LLMs: JSON mode, schema enforcement, and parsing with retry logic.",
        '''Structured LLM output extraction:

```python
import json
import re
from dataclasses import dataclass
from typing import Any, TypeVar, Type
from pydantic import BaseModel, ValidationError


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str
    confidence: float
    attributes: dict[str, Any] = {}


class StructuredExtractor:
    """Extract structured data from LLM outputs with validation."""

    def __init__(self, llm_fn):
        self.llm = llm_fn
        self.max_retries = 3

    def extract_json(self, prompt: str, schema: dict = None) -> dict:
        """Extract JSON from LLM response with retry logic."""
        system = "You are a JSON extraction assistant. Always respond with valid JSON only."
        if schema:
            system += f"\\nFollow this schema: {json.dumps(schema)}"

        for attempt in range(self.max_retries):
            response = self.llm(prompt, system=system)
            parsed = self._parse_json(response)
            if parsed is not None:
                if schema and not self._validate_schema(parsed, schema):
                    prompt = f"Previous output didn't match schema. Fix: {response}"
                    continue
                return parsed

            # Retry with explicit instruction
            prompt = f"Your previous response was not valid JSON. Try again.\\n{prompt}"

        raise ValueError(f"Failed to extract JSON after {self.max_retries} attempts")

    def extract_typed(self, prompt: str, model_class: Type[BaseModel]) -> BaseModel:
        """Extract and validate against Pydantic model."""
        schema = model_class.model_json_schema()
        system = f"Respond with JSON matching this schema:\\n{json.dumps(schema, indent=2)}"

        for attempt in range(self.max_retries):
            response = self.llm(prompt, system=system)
            parsed = self._parse_json(response)
            if parsed is None:
                continue
            try:
                return model_class.model_validate(parsed)
            except ValidationError as e:
                prompt = f"Validation error: {e}. Fix the JSON.\\n{prompt}"

        raise ValueError("Failed to extract valid typed response")

    def _parse_json(self, text: str) -> dict | None:
        """Try multiple strategies to extract JSON."""
        # Strategy 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Strategy 2: extract from markdown code block
        match = re.search(r"```(?:json)?\\n(.*?)```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Strategy 3: find first { ... } or [ ... ]
        for start, end in [("{", "}"), ("[", "]")]:
            s = text.find(start)
            e = text.rfind(end)
            if s != -1 and e > s:
                try:
                    return json.loads(text[s:e+1])
                except json.JSONDecodeError:
                    pass
        return None

    def _validate_schema(self, data: dict, schema: dict) -> bool:
        required = schema.get("required", [])
        return all(k in data for k in required)


class ToolUsePrompt:
    """Build prompts for LLM tool use / function calling."""

    def __init__(self):
        self.tools: list[dict] = []

    def add_tool(self, name: str, description: str, parameters: dict):
        self.tools.append({
            "name": name, "description": description,
            "parameters": parameters,
        })

    def build_system_prompt(self) -> str:
        tools_desc = json.dumps(self.tools, indent=2)
        return f"""You have access to these tools:

{tools_desc}

To use a tool, respond with JSON:
{{"tool": "tool_name", "args": {{...}}}}

If no tool is needed, respond normally."""

    def parse_tool_call(self, response: str) -> dict | None:
        try:
            parsed = json.loads(response)
            if "tool" in parsed and "args" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return None
```

Key patterns:
1. **Multi-strategy JSON parsing** — try direct, code block, then brace extraction
2. **Retry with feedback** — include validation errors in retry prompt for self-correction
3. **Pydantic validation** — typed extraction with automatic schema generation
4. **Schema enforcement** — include JSON schema in system prompt for structured output
5. **Tool use format** — standardized JSON format for function calling'''
    ),
    (
        "ai/multi-turn-prompting",
        "Show multi-turn conversation patterns: context management, conversation memory, and turn-based prompt construction.",
        '''Multi-turn conversation management:

```python
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str
    metadata: dict = field(default_factory=dict)


class ConversationManager:
    """Manage multi-turn conversations with context windowing."""

    def __init__(self, system_prompt: str, max_tokens: int = 8000):
        self.system = Message(role="system", content=system_prompt)
        self.history: list[Message] = []
        self.max_tokens = max_tokens

    def add_user_message(self, content: str):
        self.history.append(Message(role="user", content=content))

    def add_assistant_message(self, content: str):
        self.history.append(Message(role="assistant", content=content))

    def get_context_window(self) -> list[dict]:
        """Build message list fitting within token budget."""
        messages = [{"role": "system", "content": self.system.content}]

        # Always include last N turns
        recent = self.history[-10:]
        # Estimate tokens (rough: 4 chars per token)
        token_est = len(self.system.content) // 4
        included = []

        for msg in reversed(recent):
            msg_tokens = len(msg.content) // 4
            if token_est + msg_tokens > self.max_tokens:
                break
            included.insert(0, msg)
            token_est += msg_tokens

        # If we truncated, add a summary of earlier context
        if len(included) < len(self.history):
            n_dropped = len(self.history) - len(included)
            summary = f"[{n_dropped} earlier messages summarized: conversation about "
            topics = self._extract_topics(self.history[:n_dropped])
            summary += ", ".join(topics[:3]) + "]"
            messages.append({"role": "system", "content": summary})

        for msg in included:
            messages.append({"role": msg.role, "content": msg.content})

        return messages

    def _extract_topics(self, messages: list[Message]) -> list[str]:
        """Simple topic extraction from messages."""
        words = {}
        for msg in messages:
            for word in msg.content.lower().split():
                if len(word) > 5:
                    words[word] = words.get(word, 0) + 1
        return [w for w, c in sorted(words.items(), key=lambda x: -x[1])[:5]]

    def branch(self, from_turn: int = -2) -> "ConversationManager":
        """Create a branch for exploring alternative conversation paths."""
        branched = ConversationManager(self.system.content, self.max_tokens)
        branched.history = self.history[:from_turn].copy()
        return branched

    def inject_context(self, context: str, position: str = "before_last"):
        """Inject retrieved context into conversation."""
        ctx_msg = Message(role="system",
                          content=f"Relevant context:\\n{context}")
        if position == "before_last" and self.history:
            self.history.insert(-1, ctx_msg)
        else:
            self.history.append(ctx_msg)
```

Key patterns:
1. **Context windowing** — fit conversation in token budget; truncate oldest turns first
2. **Summary injection** — summarize dropped messages so model retains context awareness
3. **Conversation branching** — explore alternative paths from a checkpoint
4. **Context injection** — insert RAG-retrieved context before the last user message
5. **Token estimation** — rough 4-chars-per-token for fast budget checking'''
    ),
    (
        "ai/few-shot-optimization",
        "Show few-shot prompt optimization: example selection, ordering effects, and dynamic prompt construction.",
        '''Few-shot prompt optimization:

```python
import numpy as np
from typing import Callable


class FewShotOptimizer:
    """Optimize few-shot example selection for best performance."""

    def __init__(self, example_pool: list[dict], embed_fn: Callable):
        self.pool = example_pool
        self.embed_fn = embed_fn
        self.embeddings = np.array([embed_fn(e["instruction"]) for e in example_pool])

    def select_similar(self, query: str, k: int = 3) -> list[dict]:
        """Select examples most similar to the query."""
        q_embed = np.array(self.embed_fn(query))
        similarities = self.embeddings @ q_embed / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q_embed) + 1e-8
        )
        top_k = np.argsort(similarities)[-k:][::-1]
        return [self.pool[i] for i in top_k]

    def select_diverse(self, k: int = 3) -> list[dict]:
        """Select maximally diverse examples (MMR-style)."""
        selected = [0]  # Start with first
        for _ in range(k - 1):
            best_idx, best_score = -1, -float("inf")
            for i in range(len(self.pool)):
                if i in selected:
                    continue
                # Max similarity to any selected example
                max_sim = max(
                    float(self.embeddings[i] @ self.embeddings[j])
                    for j in selected
                )
                # Diversity = negative max similarity
                if -max_sim > best_score:
                    best_score = -max_sim
                    best_idx = i
            selected.append(best_idx)
        return [self.pool[i] for i in selected]

    def build_prompt(self, query: str, examples: list[dict],
                      template: str = None) -> str:
        """Build few-shot prompt with selected examples."""
        if template is None:
            template = "Instruction: {instruction}\\nResponse: {response}"

        parts = []
        for ex in examples:
            parts.append(template.format(**ex))

        parts.append(f"Instruction: {query}\\nResponse:")
        return "\\n\\n".join(parts)

    def optimize_order(self, query: str, examples: list[dict],
                        eval_fn: Callable, n_trials: int = 10) -> list[dict]:
        """Find best example ordering by trying permutations."""
        import itertools
        if len(examples) <= 4:
            perms = list(itertools.permutations(examples))
        else:
            perms = [list(np.random.permutation(examples)) for _ in range(n_trials)]

        best_order, best_score = examples, 0
        for perm in perms:
            prompt = self.build_prompt(query, list(perm))
            score = eval_fn(prompt)
            if score > best_score:
                best_score = score
                best_order = list(perm)

        return best_order
```

Key patterns:
1. **Similarity selection** — pick examples closest to query in embedding space
2. **Diversity selection** — MMR-style maximal marginal relevance avoids redundant examples
3. **Order matters** — example ordering affects LLM performance; last example most influential
4. **Dynamic construction** — adapt examples per-query rather than static few-shot
5. **Prompt optimization** — try different orderings and pick best by evaluation metric'''
    ),
]
