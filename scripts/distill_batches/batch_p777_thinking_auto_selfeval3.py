"""Phase 4B: Self-Improvement — Self-Evaluation (Part 3)

The model evaluates outputs for edge cases, assumptions, and missed context.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-check-assumptions",
        r'''I was asked "How do I read a CSV file in Python?" and I'm about to send this answer:

```python
import pandas as pd
df = pd.read_csv('data.csv')
print(df.head())
```

Let me check my assumptions before sending.''',
        r'''<think>
Let me check what assumptions I'm making:

**Assumption 1: The user has pandas installed.**
Pandas is not part of the standard library. If they're a beginner, they might not have it. I should mention `pip install pandas` or offer a stdlib alternative with the `csv` module.

**Assumption 2: The user wants a DataFrame.**
Maybe they want a list of dicts, or a list of lists. Pandas is the heaviest possible tool for reading a CSV. The built-in `csv` module is simpler and doesn't require any installation.

**Assumption 3: The file is well-formed CSV.**
What if it has: encoding issues, mixed delimiters, missing headers, quoted fields with commas, BOM characters? I should mention common gotchas.

**Assumption 4: The file fits in memory.**
`pd.read_csv` loads the entire file. For GB-sized files, this might OOM. Should mention `chunksize` for large files.

**Assumption 5: They want to "read" it — but for what purpose?**
- Quick inspection → pandas is fine
- Processing row by row → csv.DictReader is better
- Data analysis → pandas is the right choice
- Just extracting one column → csv module is simpler

**Verdict:** I'm assuming intermediate-level Python user who wants data analysis. Should offer both the simple (csv module) and powerful (pandas) approach.
</think>

**Assumption check revealed 5 implicit assumptions:**

| Assumption | Risk | Fix |
|-----------|------|-----|
| User has pandas installed | Medium | Offer stdlib `csv` alternative |
| User wants a DataFrame | Medium | Ask about use case |
| CSV is well-formed | Medium | Mention encoding, delimiter |
| File fits in memory | Low | Mention chunksize for large files |
| Data analysis intent | Medium | Offer multiple approaches |

**Improved answer with fewer assumptions:**

"Two approaches depending on your needs:

**Simple (no dependencies):**
```python
import csv

with open('data.csv', newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        print(row)  # Each row is a dict: {'name': 'Alice', 'age': '30'}
```

**For data analysis (requires pandas):**
```python
import pandas as pd  # pip install pandas
df = pd.read_csv('data.csv')
print(df.head())
```

**Common gotchas:**
- Encoding: `open('data.csv', encoding='utf-8-sig')` for files with BOM
- Delimiter: `csv.reader(f, delimiter=';')` for semicolon-separated files
- Large files: `pd.read_csv('data.csv', chunksize=10000)` to process in chunks"'''
    ),
    (
        "thinking/auto-selfeval-rate-explanation-clarity",
        r'''Rate the clarity of my own explanation of database indexing:

"A database index is like a book's index — it lets you find data without scanning every row. Create an index on columns you filter or sort by. But indexes slow down writes because the index must be updated on every INSERT/UPDATE/DELETE. So don't index everything — only columns in WHERE, JOIN, and ORDER BY clauses."

Scale: 1 (confusing) to 10 (crystal clear).''',
        r'''<think>
Let me evaluate the clarity of my own explanation:

**Analogy quality:** Book index analogy is excellent — immediately understood by anyone. 5/5.

**Core concept:** "Find data without scanning every row" — correct and clear. Captures the essential purpose. 5/5.

**Actionability:** "Create an index on columns you filter or sort by" — good rule of thumb. Tells the user what to DO. 4/5.

**Tradeoff explanation:** "Indexes slow down writes" — correct and important. Most explanations skip this. 5/5.

**Guideline:** "Only columns in WHERE, JOIN, and ORDER BY" — good heuristic. 4/5.

**What's missing:**
- No example (a concrete CREATE INDEX statement would help)
- No mention of composite indexes (multi-column)
- No mention of how to tell if you NEED an index (EXPLAIN/query plan)
- No mention of index types (B-tree, hash, GIN)

**What's good:**
- Concise (4 sentences)
- Covers the most important tradeoff (read speed vs write speed)
- Gives actionable advice
- Accessible to beginners

**Overall clarity: 7/10.** Good for a quick overview. Missing concrete examples and next steps.
</think>

**Clarity: 7/10 — Good overview but missing examples.**

| Criterion | Score | Notes |
|-----------|-------|-------|
| Analogy | 5/5 | Book index analogy is perfect |
| Core concept | 5/5 | "Find without scanning" is clear |
| Tradeoff | 5/5 | Mentions write overhead |
| Actionability | 3/5 | No concrete example |
| Completeness | 3/5 | Missing composite indexes, EXPLAIN |

**To get to 9/10, add a concrete example:**

"A database index is like a book's index — it lets you find data without scanning every row.

```sql
-- Without index: scans all 10M rows (slow)
SELECT * FROM users WHERE email = 'alice@example.com';

-- Add index: jumps directly to the row (fast)
CREATE INDEX idx_users_email ON users(email);

-- Now the same query uses the index automatically
```

Create indexes on columns in WHERE, JOIN, and ORDER BY clauses. But indexes slow writes — every INSERT/UPDATE must also update the index. Don't index everything.

**How to check if you need an index:**
```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'alice@example.com';
-- Look for 'Seq Scan' (no index) vs 'Index Scan' (has index)
```"'''
    ),
    (
        "thinking/auto-selfeval-catch-outdated-info",
        r'''Let me evaluate whether my knowledge might be outdated before answering about Python type hints:

User asked: "What's the modern way to type hint a function that returns a list of strings?"

My draft: "Use typing.List:
```python
from typing import List

def get_names() -> List[str]:
    return ['Alice', 'Bob']
```"

Is this current best practice?''',
        r'''<think>
Let me check if my advice is up-to-date:

**What I know:**
- `typing.List` has been the standard way to annotate list types
- BUT Python 3.9+ allows built-in types as generics: `list[str]` instead of `List[str]`
- Python 3.10+ has `X | Y` union syntax instead of `Union[X, Y]`
- Python 3.12+ has improved type parameter syntax

**Is `typing.List` still best practice?**
NO. As of Python 3.9+ (released Oct 2020), you can use `list[str]` directly. `typing.List` is still supported but considered legacy. The `from __future__ import annotations` trick enables this even in 3.7+.

**Current best practice (Python 3.9+):**
```python
def get_names() -> list[str]:
    return ['Alice', 'Bob']
```

**Even more modern (Python 3.10+):**
```python
def get_names() -> list[str]:  # list[str] not List[str]
    ...

def get_value() -> str | None:  # str | None not Optional[str]
    ...
```

**My answer uses `typing.List` which is the OLD way.** Not wrong, but not current best practice. I should recommend the built-in syntax.

**Verdict:** My answer is technically correct but outdated. Update to use built-in generics.
</think>

**Self-evaluation: OUTDATED. My answer uses the old `typing.List` syntax.**

Since Python 3.9 (Oct 2020), `list[str]` works directly — no import needed.

| Syntax | Version | Status |
|--------|---------|--------|
| `typing.List[str]` | 3.5+ | Legacy (still works) |
| `list[str]` | 3.9+ | **Current best practice** |
| `from __future__ import annotations` | 3.7+ | Enables 3.9+ syntax early |

**Corrected answer:**
```python
# Modern Python (3.9+) — no import needed:
def get_names() -> list[str]:
    return ['Alice', 'Bob']

# Also modern (3.10+):
def find_user(name: str) -> dict[str, str] | None:
    ...

# If you need to support Python 3.7-3.8:
from __future__ import annotations
def get_names() -> list[str]:  # Works with the future import
    return ['Alice', 'Bob']
```

**Other updated type hints:**
```python
# Old → New
from typing import Dict → dict[str, int]
from typing import Tuple → tuple[str, int]
from typing import Set → set[str]
from typing import Optional[str] → str | None
from typing import Union[str, int] → str | int
```

**Self-evaluation lesson:** Always check if typing advice uses the current syntax. Python's type system has evolved significantly since 3.5.'''
    ),
    (
        "thinking/auto-selfeval-evaluate-tradeoff-analysis",
        r'''I'm evaluating my own tradeoff analysis before presenting it. User asked "Should we use MongoDB or PostgreSQL for our e-commerce platform?"

My draft analysis:
"MongoDB:
- Pros: Flexible schema, easy to scale horizontally, fast for reads
- Cons: No ACID transactions, eventual consistency, no joins

PostgreSQL:
- Pros: ACID compliant, strong consistency, supports joins
- Cons: Hard to scale, rigid schema, slower reads"

Is this analysis balanced and accurate?''',
        r'''<think>
Let me fact-check my own tradeoff analysis:

**MongoDB claims:**
- "Flexible schema" ✓ — True, document model allows varying structures
- "Easy to scale horizontally" ✓ — Built-in sharding, though it's complex in practice
- "Fast for reads" ⚠️ — Not inherently faster than PostgreSQL. Depends on schema design, indexing, and query patterns. This is a myth.
- "No ACID transactions" ❌ — WRONG since MongoDB 4.0 (2018). MongoDB supports multi-document ACID transactions.
- "Eventual consistency" ⚠️ — Misleading. Default is strong consistency for single-document reads. Eventual consistency only applies to replica reads with specific read concern settings.
- "No joins" ❌ — WRONG since MongoDB 3.2 (2015). `$lookup` provides join functionality. Not as performant as SQL joins, but they exist.

**PostgreSQL claims:**
- "ACID compliant" ✓ — True
- "Strong consistency" ✓ — True
- "Supports joins" ✓ — True
- "Hard to scale" ⚠️ — Misleading. PostgreSQL scales vertically very well (single server handling TB-scale data). Horizontal scaling is harder but possible with Citus, read replicas, or partitioning.
- "Rigid schema" ⚠️ — Misleading. PostgreSQL has JSONB columns for flexible data alongside relational tables. Best of both worlds.
- "Slower reads" ❌ — No evidence for this. With proper indexes, PostgreSQL reads are extremely fast.

**My analysis has significant inaccuracies.** I'm presenting outdated information about MongoDB and FUD about PostgreSQL.

**Also missing:** For e-commerce specifically, ACID transactions are critical (money, inventory, orders). This strongly favors PostgreSQL.

**Verdict:** My analysis is biased and contains factual errors. Needs major revision.
</think>

**Self-evaluation: Inaccurate and biased. Rating: 3/10.**

**Factual errors in my analysis:**
| Claim | Accurate? | Reality |
|-------|-----------|---------|
| MongoDB: "No ACID transactions" | ❌ Wrong | Has ACID since v4.0 (2018) |
| MongoDB: "No joins" | ❌ Wrong | Has $lookup since v3.2 |
| MongoDB: "Fast for reads" | ⚠️ Myth | Not inherently faster than PostgreSQL |
| PostgreSQL: "Hard to scale" | ⚠️ Misleading | Scales vertically to TB; Citus for horizontal |
| PostgreSQL: "Rigid schema" | ⚠️ Misleading | Has JSONB for flexible data |
| PostgreSQL: "Slower reads" | ❌ Wrong | No evidence for this |

**Corrected analysis for e-commerce:**

For an e-commerce platform, **PostgreSQL is the stronger choice** because:
- Orders, payments, and inventory need ACID transactions (money must be consistent)
- Relational data (users → orders → products → inventory) maps naturally to SQL
- JSONB gives you flexible fields when needed (product attributes vary by category)
- Battle-tested at scale (Shopify, GitLab, Instagram all use PostgreSQL)

MongoDB makes sense for specific parts (product catalog with varying schemas, session storage, analytics logs) but is not the best fit for the core transactional system.

**Self-evaluation lesson:** When comparing technologies, check claims against current versions, not outdated perceptions. MongoDB and PostgreSQL have both evolved significantly.'''
    ),
    (
        "thinking/auto-selfeval-evaluate-error-message",
        r'''I just generated an error message for our API. Let me evaluate it:

```python
return {"error": "An error occurred while processing your request. Please try again later. If the problem persists, contact support."}, 500
```

Is this a good error message?''',
        r'''<think>
Let me evaluate this error message on multiple dimensions:

**For the user/developer calling the API:**
- "An error occurred" — tells them nothing about WHAT went wrong
- "while processing your request" — vague, which request? which part?
- "Please try again later" — is it actually transient? Or will it always fail?
- "contact support" — with what information? They have nothing to report
- No error code for programmatic handling
- No request ID for correlation with server logs

**For our own debugging:**
- The 500 status code indicates a server error ✓
- But there's no way to correlate this response with server-side logs
- If a user reports this error, we have no way to find the relevant log entries

**What a good API error response looks like:**
- Machine-readable error code
- Human-readable message
- Request ID for correlation
- Specific enough to be actionable
- Doesn't leak internal details (stack traces, SQL queries, file paths)

**Verdict:** This is a bad error message. It's generic, unactionable, and impossible to debug. Score: 2/10.
</think>

**Self-evaluation: Generic and unhelpful. Rating: 2/10.**

| Criterion | Score | Issue |
|-----------|-------|-------|
| Specificity | 1/5 | "An error occurred" says nothing |
| Actionability | 1/5 | User can't do anything with this |
| Debuggability | 1/5 | No request ID, no error code |
| Safety | 4/5 | Doesn't leak internals (good) |
| Programmatic use | 1/5 | No error code for client handling |

**Improved error response:**
```python
import uuid

request_id = str(uuid.uuid4())
logger.error(f"Payment processing failed for order {order_id}",
             extra={"request_id": request_id, "error": str(e)})

return {
    "error": {
        "code": "payment_processing_failed",
        "message": "Unable to process payment. Your card was not charged.",
        "request_id": request_id,
        "retry": False
    }
}, 500
```

**What makes this better:**
- `code`: Machine-readable, clients can switch on it
- `message`: Specific (payment), reassuring (card not charged)
- `request_id`: User can report this, we can find the exact log entry
- `retry`: Tells the client whether retrying might help

**Error message checklist:**
1. Is it specific enough to be useful? (Not "an error occurred")
2. Does it include a request ID for debugging?
3. Does it have a machine-readable error code?
4. Does it avoid leaking internals? (No stack traces in responses)
5. Does it suggest what the user should do?'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
