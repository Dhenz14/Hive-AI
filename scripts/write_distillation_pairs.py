#!/usr/bin/env python3
"""Append multi-provider distillation training pairs to v8_research_pairs.jsonl."""
import json, pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "loras" / "training_data" / "v8_research_pairs.jsonl"

PAIRS = [
    (
        "I want to build a training data pipeline that uses multiple free LLM APIs to generate coding training pairs. What architecture would you recommend?",
        """A multi-provider distillation architecture needs four layers:

**1. Provider Registry**
Define each provider with: base_url, API key env var, model list, rate limits (RPM + daily), and priority. Example providers: Gemini (free tier, 15 RPM), OpenRouter (27+ free models, 10 RPM), Groq (free tier, 30 RPM), Cerebras (free tier), DeepSeek, Mistral, HuggingFace Inference.

```python
@dataclass
class Provider:
    name: str
    base_url: str
    api_key_env: str
    models: list[str]
    rpm_limit: int
    daily_limit: int
    priority: int  # lower = tried first
```

**2. Intelligent Router**
Don't round-robin — route by difficulty. Small models (7-27B) handle straightforward prompts. Large models (70B-405B) handle complex multi-step reasoning. Track per-model quality scores from eval feedback and weight selection toward better performers.

**3. Rate Limit Manager**
Track per-provider request counts with sliding windows. When one provider is exhausted, automatically failover to the next. Reset daily counters at midnight. This lets you maximize throughput across all providers without hitting limits.

**4. Quality Filter**
Not all generated pairs are good. Score each output for: code validity (does it parse/compile?), completeness (does it address the prompt?), and novelty (is it too similar to existing pairs?). Only pairs above threshold enter the training set.

The key insight: diversity of models actually improves training data quality — different models have different strengths and failure modes, so you get broader coverage than using a single model."""
    ),
    (
        "How should I select which free models to use from OpenRouter for code generation training data? There are dozens available.",
        """Selection criteria, in priority order:

**1. Parameter count floor**: Skip anything under 24B for code generation. Below that, output quality drops sharply — you'll spend more time filtering bad pairs than you save on API costs. The free tier includes models up to 480B (Qwen3 Coder MoE).

**2. Coding specialization**: Prefer models explicitly trained for code: Qwen3 Coder (480B MoE, 262K context), Mistral Small 3.1 (24B, strong coding), Nemotron Nano (30B MoE). General-purpose models like Llama 3.3 70B still work but produce more boilerplate.

**3. Context window**: For generating training pairs with full context (system prompt + task + solution + tests + explanation), you need at least 8K tokens of output. Models with 128K+ context windows give headroom: Qwen3 Coder (262K), Llama 3.3 (128K), gpt-oss-120B (131K).

**4. Practical availability**: Some "free" models have aggressive rate limits or frequent downtime. Monitor actual success rates. A reliable 70B model beats an unreliable 405B model for throughput.

**Recommended shortlist** (as of early 2026):
- `nousresearch/hermes-3-llama-3.1-405b:free` — highest raw quality
- `qwen/qwen3-coder:free` — 480B MoE, best for code specifically
- `openai/gpt-oss-120b:free` — strong general + code
- `meta-llama/llama-3.3-70b-instruct:free` — reliable workhorse
- `mistralai/mistral-small-3.1-24b-instruct:free` — fast, good code quality

Re-audit quarterly — the free model landscape changes fast as providers rotate promotional offerings."""
    ),
    (
        "My distillation system generates training pairs from multiple AI providers, but quality varies wildly. How do I filter effectively?",
        """Multi-stage filtering pipeline:

**Stage 1: Structural validation (instant, no LLM needed)**
```python
def structural_filter(response: str) -> bool:
    # Must contain actual code blocks
    if '```' not in response:
        return False
    # Extract code blocks and verify they parse
    for block in extract_code_blocks(response):
        lang = detect_language(block)
        if lang == 'python':
            try:
                ast.parse(block)
            except SyntaxError:
                return False
        # For compiled langs, check structural markers
        elif lang in ('rust', 'go', 'cpp'):
            if not has_function_or_struct(block):
                return False
    return True
```

**Stage 2: Deduplication (embedding-based)**
Embed each pair with a lightweight model (bge-m3). Compare cosine similarity against existing training set. Reject pairs above 0.92 similarity — they're paraphrases that add training cost without new signal.

**Stage 3: Completeness scoring**
Check that the response actually addresses the prompt:
- Does it contain code that solves the stated problem?
- Does it include test cases or usage examples?
- Does it explain the approach (not just dump code)?
Score each dimension 0-1, reject below 0.6 average.

**Stage 4: Per-model quality tracking**
Log which model generated each pair. After eval, correlate training pair quality with source model. Over time, you'll discover which models excel at which categories — route future prompts accordingly.

The meta-insight: filtering is more important than generation. A 1000-pair dataset where every pair is excellent beats a 10000-pair dataset with 30% noise. Noise in training data doesn't average out — it actively teaches bad patterns."""
    ),
    (
        "How do I handle rate limits across multiple free AI API providers without getting blocked?",
        """Implement a token-bucket rate limiter per provider with automatic failover:

```python
import time
from dataclasses import dataclass, field

@dataclass
class RateBucket:
    rpm_limit: int
    daily_limit: int
    requests_this_minute: int = 0
    requests_today: int = 0
    minute_start: float = field(default_factory=time.time)
    day_start: float = field(default_factory=time.time)

    def can_request(self) -> bool:
        now = time.time()
        # Reset minute window
        if now - self.minute_start >= 60:
            self.requests_this_minute = 0
            self.minute_start = now
        # Reset daily window
        if now - self.day_start >= 86400:
            self.requests_today = 0
            self.day_start = now
        return (self.requests_this_minute < self.rpm_limit
                and self.requests_today < self.daily_limit)

    def record_request(self):
        self.requests_this_minute += 1
        self.requests_today += 1
```

**Key patterns:**

1. **Priority-ordered failover**: Sort providers by priority. Try the best available provider first. If rate-limited, fall to next. This maximizes quality while maintaining throughput.

2. **Backoff on 429s**: When you hit a rate limit response, mark that provider as unavailable for 60s (not just the next request). Some providers track limits server-side more strictly than documented.

3. **Stagger requests**: Don't burst 10 requests in the first second of each minute. Spread them evenly with `sleep(60 / rpm_limit)` between calls. Providers are more lenient with steady traffic.

4. **Daily budget awareness**: Log remaining daily quota. Alert when any provider drops below 20% of daily limit so you can redistribute load.

5. **Provider health tracking**: If a provider returns errors 3x consecutively, circuit-break it for 5 minutes. Don't waste rate limit budget on a provider experiencing outages."""
    ),
    (
        "What's the best way to generate diverse seed prompts for a coding training data pipeline?",
        """Seed prompt diversity is the bottleneck — if your prompts are repetitive, no amount of model diversity fixes the output. Four proven sources:

**1. Structured template expansion**
Define prompt templates with slots, fill combinatorially:
```python
TEMPLATES = [
    "Implement {data_structure} in {language} with {feature}",
    "Write a {language} function that {operation} on {input_type}",
    "Debug this {language} code that has a {bug_type}: {code_snippet}",
    "Refactor this {pattern} to use {better_pattern} in {language}",
]
# Expand with category-specific slot values
```
This gives you thousands of unique prompts from dozens of templates.

**2. Real-world question mining**
Stack Exchange API (free, 300 req/day, no key needed) has millions of real coding questions with quality signals (votes, accepted answers):
```
GET https://api.stackexchange.com/2.3/questions
    ?order=desc&sort=votes&tagged=python
    &site=stackoverflow&filter=withbody
```
Use the question body as a seed prompt. The answers tell you what quality looks like, but generate your own response — you want your model's voice, not Stack Overflow's.

**3. Curriculum-based generation**
Map out skills by difficulty tier. Generate prompts that form a learning progression:
- Tier 1: Single-function problems (fizzbuzz, string manipulation)
- Tier 2: Multi-function with data structures (linked lists, trees)
- Tier 3: System design (API servers, concurrent pipelines)
- Tier 4: Debugging and refactoring existing code

**4. Weakness-targeted generation**
After eval, identify categories where your model scores lowest. Generate 3x more prompts for those categories. Our experience: Go and C++ were underrepresented at 0.7-0.8% of training data — targeted generation brought meaningful improvement.

The ratio that works: 40% template expansion, 30% real-world mining, 20% curriculum, 10% weakness-targeted."""
    ),
]

with open(OUT, "a", encoding="utf-8") as f:
    for prompt, response in PAIRS:
        obj = {
            "conversations": [
                {"role": "system", "content": "You are a helpful AI coding assistant."},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.strip()},
            ]
        }
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

print(f"Appended {len(PAIRS)} multi-provider distillation pairs to {OUT}")
