"""LLM caching and optimization — prompt caching, KV-cache reuse, semantic dedup."""

PAIRS = [
    (
        "ai/prompt-caching",
        "Show LLM prompt caching strategies: exact match caching, semantic caching, prefix caching, and KV-cache reuse.",
        '''LLM prompt caching for cost and latency reduction:

```python
import hashlib
import time
import json
import numpy as np
from dataclasses import dataclass, field
from collections import OrderedDict
from typing import Any


# === Exact Match Cache ===

class ExactMatchCache:
    """Cache LLM responses by exact prompt match.

    Simple but effective: many applications send identical prompts
    (system prompts, templates with same variables, repeated queries).
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600):
        self.cache: OrderedDict[str, dict] = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0

    def _key(self, prompt: str, model: str, temperature: float) -> str:
        """Deterministic cache key from request parameters."""
        key_data = json.dumps({
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
        }, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, prompt: str, model: str, temperature: float = 0.0) -> str | None:
        """Look up cached response. Only cache deterministic (temp=0) by default."""
        if temperature > 0:
            return None  # Non-deterministic responses shouldn't be cached

        key = self._key(prompt, model, temperature)
        entry = self.cache.get(key)

        if entry is None:
            self.misses += 1
            return None

        # Check TTL
        if time.time() - entry["timestamp"] > self.ttl:
            del self.cache[key]
            self.misses += 1
            return None

        self.hits += 1
        self.cache.move_to_end(key)  # LRU: move to most recent
        return entry["response"]

    def set(self, prompt: str, model: str, temperature: float,
            response: str):
        """Cache a response."""
        if temperature > 0:
            return

        key = self._key(prompt, model, temperature)
        self.cache[key] = {"response": response, "timestamp": time.time()}

        # Evict oldest if over capacity
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


# === Semantic Cache ===

class SemanticCache:
    """Cache based on meaning similarity, not exact match.

    "How do I sort a list in Python?" and
    "Python list sorting" should hit the same cache entry.
    """

    def __init__(self, similarity_threshold: float = 0.92, max_size: int = 5000):
        self.threshold = similarity_threshold
        self.max_size = max_size
        self.entries: list[dict] = []

    def _embed(self, text: str) -> np.ndarray:
        """Get embedding for text. In production: use sentence-transformers."""
        # Placeholder — use a real embedding model
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        vec = np.frombuffer(h, dtype=np.uint8).astype(np.float32)[:32]
        return vec / (np.linalg.norm(vec) + 1e-8)

    def get(self, prompt: str) -> str | None:
        """Find semantically similar cached prompt."""
        if not self.entries:
            return None

        query_emb = self._embed(prompt)
        best_sim = -1
        best_entry = None

        for entry in self.entries:
            sim = np.dot(query_emb, entry["embedding"])
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_sim >= self.threshold:
            best_entry["access_count"] += 1
            return best_entry["response"]
        return None

    def set(self, prompt: str, response: str):
        embedding = self._embed(prompt)
        self.entries.append({
            "prompt": prompt,
            "response": response,
            "embedding": embedding,
            "timestamp": time.time(),
            "access_count": 0,
        })
        if len(self.entries) > self.max_size:
            # Evict least accessed
            self.entries.sort(key=lambda e: e["access_count"])
            self.entries = self.entries[100:]  # Remove bottom 100


# === Prefix Caching (for shared system prompts) ===

class PrefixCache:
    """Cache KV states for shared prefixes (system prompts).

    Many requests share the same system prompt.
    Computing KV states for it once and reusing saves ~30-50% compute.
    """

    def __init__(self, max_prefixes: int = 100):
        self.kv_cache: dict[str, dict] = {}
        self.max_prefixes = max_prefixes

    def get_or_compute_prefix(
        self,
        prefix: str,
        model,
        tokenizer,
    ) -> dict:
        """Get cached KV state for prefix, or compute it."""
        prefix_key = hashlib.md5(prefix.encode()).hexdigest()

        if prefix_key in self.kv_cache:
            return self.kv_cache[prefix_key]

        # Compute KV state for prefix
        tokens = tokenizer(prefix, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model(**tokens, use_cache=True)

        kv_state = {
            "past_key_values": outputs.past_key_values,
            "prefix_length": tokens["input_ids"].shape[1],
        }

        self.kv_cache[prefix_key] = kv_state
        if len(self.kv_cache) > self.max_prefixes:
            oldest = next(iter(self.kv_cache))
            del self.kv_cache[oldest]

        return kv_state

    def generate_with_cached_prefix(
        self,
        prefix: str,
        continuation: str,
        model,
        tokenizer,
        max_new_tokens: int = 512,
    ) -> str:
        """Generate using cached prefix KV state."""
        import torch

        # Get or compute prefix KV state
        kv_state = self.get_or_compute_prefix(prefix, model, tokenizer)

        # Tokenize only the continuation (not the prefix)
        cont_tokens = tokenizer(continuation, return_tensors="pt", add_special_tokens=False)
        cont_ids = cont_tokens["input_ids"].to(model.device)

        # Generate with cached prefix
        with torch.no_grad():
            output = model.generate(
                input_ids=cont_ids,
                past_key_values=kv_state["past_key_values"],
                max_new_tokens=max_new_tokens,
            )

        return tokenizer.decode(output[0], skip_special_tokens=True)


# === Tiered Caching Strategy ===

class TieredLLMCache:
    """Multi-tier caching: exact → semantic → prefix.

    Check each tier in order of speed and specificity:
    1. Exact match (fastest, most specific)
    2. Semantic similarity (moderate speed)
    3. Prefix KV-cache (saves compute, not a full cache hit)
    """

    def __init__(self):
        self.exact = ExactMatchCache(max_size=10000, ttl_seconds=3600)
        self.semantic = SemanticCache(similarity_threshold=0.95, max_size=5000)
        self.stats = {"exact_hits": 0, "semantic_hits": 0, "misses": 0}

    def get(self, prompt: str, model: str, temperature: float = 0.0) -> str | None:
        # Tier 1: Exact match
        result = self.exact.get(prompt, model, temperature)
        if result:
            self.stats["exact_hits"] += 1
            return result

        # Tier 2: Semantic similarity
        result = self.semantic.get(prompt)
        if result:
            self.stats["semantic_hits"] += 1
            return result

        self.stats["misses"] += 1
        return None

    def set(self, prompt: str, model: str, temperature: float, response: str):
        self.exact.set(prompt, model, temperature, response)
        self.semantic.set(prompt, response)
```

Caching strategy comparison:

| Strategy | Hit rate | Latency | Cost savings | Freshness |
|----------|---------|---------|-------------|-----------|
| **Exact match** | 10-30% | < 1ms | Per-hit: 100% | TTL-based |
| **Semantic** | 20-50% | 5-10ms | Per-hit: 100% | Similarity threshold |
| **Prefix KV** | 80-95% | Compute savings | 30-50% per request | Always fresh |
| **Tiered** | 30-60% | 1-10ms | Highest overall | Mixed |

Key patterns:
1. **Temperature gating** — only cache deterministic (temp=0) responses; stochastic responses should vary
2. **Semantic threshold** — 0.92-0.95 similarity balances hit rate vs correctness; too low gives wrong answers
3. **Prefix caching** — shared system prompts compute KV state once; used by Claude, GPT-4 natively
4. **LRU eviction** — least-recently-used eviction keeps frequently accessed responses in cache
5. **Tiered approach** — exact → semantic → prefix; each tier catches different patterns'''
    ),
    (
        "ai/prompt-optimization",
        "Show prompt optimization techniques: few-shot selection, chain-of-thought, DSPy-style optimization, and automatic prompt tuning.",
        '''Prompt optimization for better LLM outputs:

```python
import random
import json
import numpy as np
from dataclasses import dataclass
from typing import Callable


# === Few-Shot Example Selection ===

class FewShotSelector:
    """Select the most relevant few-shot examples for each query.

    Random selection is suboptimal. Select examples that are
    semantically similar to the current query.
    """

    def __init__(self, examples: list[dict], embedding_fn: Callable):
        self.examples = examples
        self.embeddings = np.array([
            embedding_fn(ex["input"]) for ex in examples
        ])
        self.embedding_fn = embedding_fn

    def select(self, query: str, k: int = 3,
               strategy: str = "similarity") -> list[dict]:
        """Select K examples using the specified strategy."""
        if strategy == "similarity":
            return self._select_similar(query, k)
        elif strategy == "diverse":
            return self._select_diverse(query, k)
        elif strategy == "difficulty":
            return self._select_by_difficulty(query, k)
        return random.sample(self.examples, min(k, len(self.examples)))

    def _select_similar(self, query: str, k: int) -> list[dict]:
        """Select examples most similar to the query."""
        query_emb = self.embedding_fn(query)
        similarities = self.embeddings @ query_emb
        top_indices = np.argsort(-similarities)[:k]
        return [self.examples[i] for i in top_indices]

    def _select_diverse(self, query: str, k: int) -> list[dict]:
        """Select diverse examples (MMR-style)."""
        query_emb = self.embedding_fn(query)
        similarities = self.embeddings @ query_emb

        selected = []
        remaining = list(range(len(self.examples)))

        for _ in range(k):
            if not remaining:
                break

            best_idx = None
            best_score = float("-inf")

            for idx in remaining:
                relevance = similarities[idx]
                diversity = 0
                if selected:
                    max_sim = max(
                        self.embeddings[idx] @ self.embeddings[s]
                        for s in selected
                    )
                    diversity = -max_sim

                score = 0.7 * relevance + 0.3 * diversity
                if score > best_score:
                    best_score = score
                    best_idx = idx

            selected.append(best_idx)
            remaining.remove(best_idx)

        return [self.examples[i] for i in selected]

    def _select_by_difficulty(self, query: str, k: int) -> list[dict]:
        """Select examples ordered easy → hard (curriculum)."""
        query_emb = self.embedding_fn(query)
        similarities = self.embeddings @ query_emb
        sorted_indices = np.argsort(-similarities)

        # Take closest (easiest) first, then progressively harder
        candidates = sorted_indices[:k * 2]
        selected = list(candidates[:k])
        return [self.examples[i] for i in selected]


# === Chain-of-Thought Optimization ===

def build_cot_prompt(question: str, examples: list[dict] | None = None,
                      strategy: str = "zero-shot") -> str:
    """Build chain-of-thought prompts with different strategies."""

    if strategy == "zero-shot":
        return f"{question}\\n\\nLet's think step by step."

    elif strategy == "few-shot":
        prompt_parts = []
        for ex in (examples or []):
            prompt_parts.append(
                f"Q: {ex['question']}\\n"
                f"Reasoning: {ex['reasoning']}\\n"
                f"A: {ex['answer']}"
            )
        prompt_parts.append(
            f"Q: {question}\\n"
            f"Reasoning:"
        )
        return "\\n\\n".join(prompt_parts)

    elif strategy == "plan-and-solve":
        return (
            f"{question}\\n\\n"
            "Let's first understand the problem and devise a plan to solve it. "
            "Then, let's carry out the plan and solve the problem step by step."
        )

    elif strategy == "tree-of-thought":
        return (
            f"{question}\\n\\n"
            "Consider multiple approaches to this problem. "
            "For each approach, evaluate its merits and drawbacks. "
            "Select the best approach and execute it step by step."
        )


# === DSPy-style Prompt Optimization ===

@dataclass
class PromptTemplate:
    """Optimizable prompt template with slots."""
    instruction: str
    few_shot_examples: list[dict]
    output_format: str

    def render(self, query: str) -> str:
        parts = [self.instruction]
        for ex in self.few_shot_examples:
            parts.append(f"Input: {ex['input']}\\nOutput: {ex['output']}")
        parts.append(f"Input: {query}\\n{self.output_format}")
        return "\\n\\n".join(parts)


class PromptOptimizer:
    """Optimize prompts using evaluation feedback.

    Like DSPy: treat prompt components as parameters,
    optimize them against a metric on a dev set.
    """

    def __init__(self, candidate_instructions: list[str],
                 example_pool: list[dict], eval_fn: Callable,
                 llm_fn: Callable):
        self.instructions = candidate_instructions
        self.example_pool = example_pool
        self.eval_fn = eval_fn
        self.llm_fn = llm_fn

    def optimize(self, dev_set: list[dict], num_shots: int = 3,
                 num_trials: int = 20) -> PromptTemplate:
        """Find best instruction + examples combination."""
        best_score = -1
        best_template = None

        for trial in range(num_trials):
            # Sample instruction and examples
            instruction = random.choice(self.instructions)
            examples = random.sample(
                self.example_pool, min(num_shots, len(self.example_pool))
            )

            template = PromptTemplate(
                instruction=instruction,
                few_shot_examples=examples,
                output_format="Output:",
            )

            # Evaluate on dev set
            score = self._evaluate(template, dev_set)

            if score > best_score:
                best_score = score
                best_template = template
                print(f"Trial {trial}: new best score={score:.3f}")

        return best_template

    def _evaluate(self, template: PromptTemplate, dev_set: list[dict]) -> float:
        """Evaluate template on dev set."""
        scores = []
        for example in dev_set[:20]:  # Evaluate on subset for speed
            prompt = template.render(example["input"])
            response = self.llm_fn(prompt)
            score = self.eval_fn(response, example["expected_output"])
            scores.append(score)
        return np.mean(scores)
```

Prompt optimization techniques:

| Technique | Improvement | Cost | Automation |
|-----------|------------|------|-----------|
| **Few-shot selection** | 10-30% | Free (no extra calls) | Fully automatic |
| **Chain-of-thought** | 20-50% on reasoning | +tokens | Manual or auto |
| **DSPy optimization** | 15-40% | Dev set + trials | Fully automatic |
| **Prompt tuning** | 10-25% | Training compute | Automatic |
| **Auto-CoT** | 15-35% | Clustering cost | Automatic |

Key patterns:
1. **Similarity-based selection** — embed all examples, select nearest to query; 10-30% better than random
2. **Diverse selection (MMR)** — balance similarity to query with diversity among selected examples
3. **Zero-shot CoT** — "Let's think step by step" gives 20-50% improvement on reasoning tasks for free
4. **Prompt as parameters** — treat instruction text and examples as optimizable; search over candidates
5. **Curriculum ordering** — order few-shot examples easy → hard for better in-context learning'''
    ),
]
"""
