# Recursive Language Model (RLM) Patterns for Architecture Queries

## What Are RLMs?

Recursive Language Models treat complex queries as decomposition problems. Instead of
stuffing everything into one prompt, the model breaks a hard question into simpler
sub-questions, answers each independently, then synthesizes a final response. This is
the LLM equivalent of divide-and-conquer algorithms.

Key insight: a single LLM call with 8K tokens of marginally-relevant context performs
worse than three focused calls with 2K tokens of highly-relevant context each.

## When to Decompose vs Answer Directly

### Decompose when:
- Query requires information from 3+ distinct knowledge areas
- Query contains implicit sub-questions ("How does X work and how does it compare to Y?")
- Single retrieval returns low-relevance chunks (max similarity < 0.65)
- Query is multi-hop: answer to part A is needed to formulate part B
- Architecture questions spanning multiple layers (consensus + API + storage)

### Answer directly when:
- Query maps cleanly to a single knowledge section (similarity > 0.80)
- Query is factual lookup ("What port does hived use?")
- Context fits comfortably in budget with high relevance scores
- Decomposition would produce trivial sub-questions

### Complexity heuristics
```
complexity_signals = [
    len(query.split()) > 25,           # long queries tend to be compound
    query.count(" and ") >= 2,         # explicit conjunction
    query.count("?") > 1,             # multiple questions
    "compare" in query.lower(),        # comparison requires multiple retrievals
    "how does X affect Y" pattern,     # causal chain = multi-hop
    "design" in query.lower(),         # design questions span layers
]
if sum(complexity_signals) >= 2:
    use_decomposition()
```

## Multi-Hop Reasoning Pattern

### Step 1: Decompose the query
Break the original question into independent sub-questions that can each be answered
with a single retrieval pass.

Example query: "How would I build a custom Hive indexer that tracks token transfers
and serves them via a REST API?"

Sub-questions:
1. "What is the Hive HAF indexer architecture?"
2. "How do I filter Hive operations by type (transfers)?"
3. "What REST framework patterns does HiveAI recommend for Python APIs?"

### Step 2: Retrieve independently for each sub-question
Each sub-question gets its own retrieval call. This avoids the dilution problem where
one broad query returns chunks from all three topics but none with high relevance.

### Step 3: Answer each sub-question
Generate a focused answer for each sub-question using only its retrieved context.
Keep sub-answers concise (target 100-200 tokens each).

### Step 4: Synthesize
Combine sub-answers into a coherent final response. The synthesis prompt includes:
- The original query (for coherence)
- All sub-answers (as structured input)
- No raw retrieved chunks (already distilled into sub-answers)

## Token Budget Allocation

For an 8192-token context window, allocate:

| Segment       | Tokens | Percentage | Purpose                          |
|---------------|--------|------------|----------------------------------|
| System prompt | ~400   | 5%         | Role, instructions, skill data   |
| Context       | ~4900  | 60%        | Retrieved knowledge chunks       |
| Query + history | ~1600 | 20%       | User question + conversation     |
| Response      | ~1300  | 15%        | Generated answer headroom        |

### Context prioritization rules
1. Sort retrieved chunks by relevance score (descending)
2. Include chunks until 60% budget is reached
3. Drop chunks below 0.40 similarity regardless of budget remaining
4. For multi-hop: split the 60% evenly across sub-queries
5. Prefer fewer high-relevance chunks over many low-relevance ones

```python
def budget_context(chunks, max_tokens=4900):
    """Select highest-relevance chunks within token budget."""
    chunks.sort(key=lambda c: c["score"], reverse=True)
    selected, total = [], 0
    for chunk in chunks:
        if chunk["score"] < 0.40:
            break
        est_tokens = len(chunk["content"].split()) * 4 // 3
        if total + est_tokens > max_tokens:
            continue  # try smaller chunks
        selected.append(chunk)
        total += est_tokens
    return selected
```

## Context Window Management

### The relevance decay problem
Adding more context does not always help. After ~5 high-relevance chunks, each
additional chunk dilutes attention. Monitor the relevance curve:

```
Chunk 1: 0.92  <-- critical
Chunk 2: 0.87  <-- critical
Chunk 3: 0.74  <-- useful
Chunk 4: 0.61  <-- marginal
Chunk 5: 0.45  <-- consider dropping
Chunk 6: 0.38  <-- drop (below 0.40 threshold)
```

### Strategies for large result sets
- **Truncate**: Drop low-relevance chunks (simplest, usually sufficient)
- **Summarize**: Compress large chunks to key sentences before including
- **Partition + Recurse**: RLM pattern -- split into sub-queries, each gets focused context
- **Rerank**: Use a cross-encoder or LLM to rerank after initial vector search

## Practical Decomposition Examples

### Example 1: Architecture comparison
**Query**: "Compare Hive's DPoS with Ethereum's PoS for building decentralized apps"

Decomposition:
1. "How does Hive DPoS consensus work for dapp developers?" -> retrieve Hive docs
2. "How does Ethereum PoS affect dapp architecture?" -> retrieve Ethereum docs
3. Synthesize: compare both with focus on developer experience

### Example 2: Debugging across layers
**Query**: "My custom_json operation is being broadcast but not processed by my HAF indexer"

Decomposition:
1. "How are custom_json operations broadcast on Hive?" -> broadcast mechanics
2. "How does HAF receive and index operations?" -> HAF pipeline
3. "What are common reasons a HAF indexer misses operations?" -> debugging patterns
4. Synthesize: ordered troubleshooting checklist

### Example 3: Performance optimization
**Query**: "How do I optimize my Hive API server for high throughput with caching?"

Decomposition:
1. "What Hive API call patterns have highest latency?" -> API performance
2. "What caching strategies work for blockchain data?" -> caching patterns
3. "How do I measure and benchmark API throughput?" -> monitoring
4. Synthesize: optimization plan with priorities

## Integration with Existing RAG

RLM decomposition wraps the existing `search_knowledge_sections` flow:

```
Standard RAG:  query -> retrieve -> generate
RLM-enhanced:  query -> decompose -> [retrieve -> generate] x N -> synthesize
```

The decomposition step adds one LLM call overhead. For simple queries, skip it.
For complex queries, the improved relevance more than compensates for the extra call.
