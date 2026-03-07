# Long-Context & Recursive Decomposition Patterns

## Context Rot
When input grows large, LLM accuracy degrades even within the context window. Attention dilutes across too many tokens. The model isn't missing data — it's overwhelmed.

## RLM Pattern (Recursive Language Models)
Separate query from context. Context lives externally; model interacts through tools.

### Core Tools
- `peek(n)` — view first N chars to understand structure
- `grep(pattern)` — filter lines matching regex
- `partition(chunk_size)` — split into manageable chunks
- `recursive_call(sub_query, chunk)` — process each chunk independently

### Algorithm
```
1. Peek → understand format/structure
2. Grep → filter to relevant subset
3. If subset still too large → partition + recurse on each chunk
4. Aggregate sub-results → final answer
```

### When to Use
- Counting/classification over >1000 items
- Multi-hop reasoning across large documents
- Any task where answer requires scanning full context

### When NOT to Use
- Short contexts (<5K tokens) — overhead not worth it
- Math/proofs — needs holistic reasoning, not decomposition
- Real-time chat — recursive calls add latency

## Practical Context Management

### Budget context tokens
```python
MAX_CONTEXT_TOKENS = 4000  # leave room for system + response
sections.sort(key=lambda s: s["relevance"], reverse=True)
total = 0
selected = []
for s in sections:
    size = len(s["content"].split()) * 4 // 3  # rough token estimate
    if total + size > MAX_CONTEXT_TOKENS:
        break
    selected.append(s)
    total += size
```

### Query-focused filtering
Instead of including full sections, grep for query-relevant sentences:
```python
import re
query_words = [w for w in query.lower().split() if len(w) > 3]
relevant_lines = []
for line in section.splitlines():
    if any(w in line.lower() for w in query_words):
        relevant_lines.append(line)
```

## Comparison
| Approach | Scales | Best For |
|----------|--------|----------|
| RAG | Lookup speed | Factual Q&A |
| Agents | Task steps | Multi-step workflows |
| Chain-of-thought | Reasoning depth | Math, logic |
| RLM | Context breadth | Large doc analysis |
