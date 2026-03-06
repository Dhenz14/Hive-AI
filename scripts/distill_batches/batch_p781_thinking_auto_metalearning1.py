"""Phase 4D: Self-Improvement — Meta-Learning (Part 1)

The model learns to identify what it doesn't know, track its own improvement,
and adapt its learning strategies.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-identify-knowledge-gaps",
        r'''I keep getting questions about Kubernetes wrong. How should I systematically identify and fill my knowledge gaps?''',
        r'''<think>
To identify knowledge gaps systematically, I need a structured approach:

1. **Enumerate the topic's concept map** — list everything I should know about Kubernetes
2. **Self-test each concept** — can I explain it accurately without looking it up?
3. **Categorize confidence levels** — confident, shaky, unknown
4. **Prioritize by frequency** — which concepts come up most in user questions?
5. **Create targeted learning plan** — focus on shaky/unknown concepts that are high-frequency

This is a metacognitive skill — learning about my own learning. The key insight is that I can't improve what I can't measure.
</think>

**Systematic Knowledge Gap Analysis Framework**

**Step 1: Build the concept map**
List every sub-topic you should know:
```
Kubernetes concepts:
├── Core: Pods, Services, Deployments, ReplicaSets, Namespaces
├── Config: ConfigMaps, Secrets, Env variables
├── Storage: PersistentVolumes, PersistentVolumeClaims, StorageClasses
├── Networking: Ingress, NetworkPolicies, DNS, Service types
├── Scheduling: Node affinity, taints/tolerations, resource limits
├── Scaling: HPA, VPA, cluster autoscaler
├── Security: RBAC, ServiceAccounts, PodSecurityPolicies
├── Operations: kubectl commands, helm, kustomize
└── Debugging: logs, describe, exec, port-forward, events
```

**Step 2: Self-test each concept (honest assessment)**
| Concept | Can I explain? | Can I troubleshoot? | Confidence |
|---------|---------------|--------------------| -----------|
| Pods | Yes | Yes | High |
| Services | Yes | Mostly | Medium |
| Ingress | Partially | No | Low |
| RBAC | Vaguely | No | Low |
| HPA | No | No | None |
| NetworkPolicies | No | No | None |

**Step 3: Prioritize by user question frequency**
Most common K8s questions:
1. Deployment/rollback (HIGH frequency, HIGH importance)
2. Service networking (HIGH frequency)
3. Debugging failing pods (HIGH frequency)
4. Resource limits and OOM (MEDIUM frequency)
5. RBAC and security (MEDIUM frequency)

**Step 4: Create targeted learning plan**
```
Priority 1 (this week): Ingress, Service types (high-frequency gaps)
Priority 2 (next week): HPA, resource limits (medium-frequency gaps)
Priority 3 (week 3): RBAC, NetworkPolicies (less frequent but important)
```

**Step 5: Verify improvement**
After studying, re-test: Can I now explain and troubleshoot each concept? If not, study more.

**The meta-skill:** This framework works for ANY topic. Enumerate concepts → self-assess → prioritize by impact → study → re-assess.'''
    ),
    (
        "thinking/auto-metalearning-learning-from-corrections",
        r'''A user corrected me — I said Python dicts are unordered, but they've been insertion-ordered since Python 3.7. How should I update my knowledge and prevent similar mistakes?''',
        r'''<think>
This correction reveals a pattern: my knowledge has a "version staleness" problem. Python dicts WERE unordered (Python < 3.6), became ordered as an implementation detail in CPython 3.6, and became guaranteed ordered in Python 3.7+.

**Why I got this wrong:**
1. The "dicts are unordered" fact was correct for many years and is deeply embedded
2. The change happened incrementally (implementation detail → language guarantee)
3. Many tutorials and references still say "unordered" because they haven't been updated

**What I should learn from this:**
1. **Version-sensitive facts need version tags** — "Python dicts are X" should always be qualified with "since version Y"
2. **Language evolution** — features that were true in Python 2 may not be true in Python 3.7+
3. **Other possibly stale facts about Python:**
   - String formatting: .format() → f-strings (3.6+)
   - Type hints: typing.List → list[str] (3.9+)
   - Union types: Union[X, Y] → X | Y (3.10+)
   - match/case (3.10+)
   - Exception groups (3.11+)
   - Free-threading (3.13+)

**Process for preventing similar mistakes:**
1. When stating facts about language behavior, check which version it applies to
2. Default to modern Python (3.10+) unless user specifies otherwise
3. When corrected, identify the CATEGORY of error (version staleness), not just the specific fact
</think>

**Knowledge update process:**

**1. Fix the specific error:**
```
OLD: "Python dicts are unordered"
NEW: "Python dicts are insertion-ordered (guaranteed since Python 3.7,
      CPython implementation detail since 3.6)"
```

**2. Identify the ERROR CATEGORY (not just the specific fact):**
This is a "version staleness" error — a fact that was once true but changed.

**3. Find similar stale facts in the same category:**
| Topic | Stale fact | Current truth |
|-------|-----------|---------------|
| Dicts | Unordered | Ordered since 3.7 |
| Type hints | Need `typing.List` | Use `list[str]` since 3.9 |
| Union types | `Union[X, Y]` | `X \| Y` since 3.10 |
| String formatting | `.format()` preferred | f-strings preferred since 3.6 |
| Pattern matching | Doesn't exist | `match/case` since 3.10 |
| GIL | Always present | Free-threading since 3.13 |

**4. Create a version-awareness rule:**
"When stating Python language behavior, specify the minimum version. Default to Python 3.10+ unless the user specifies otherwise."

**5. Verify the fix:**
Test myself: "Are Python dicts ordered?" → "Yes, since Python 3.7. Insertion order is guaranteed by the language specification, not just the CPython implementation."

**Meta-learning principle:** When corrected on one fact, don't just fix that fact. Identify the CATEGORY of error and scan for other instances. One correction should fix an entire class of mistakes.'''
    ),
    (
        "thinking/auto-metalearning-track-improvement",
        r'''How can I tell if I'm actually getting better at answering programming questions over time? What metrics should I track?''',
        r'''<think>
This is about measuring my own improvement — a meta-learning skill. The challenge: how do you measure "quality of programming answers" objectively?

**Candidate metrics:**
1. Correctness rate — does the code I suggest actually work?
2. Completeness — do I address all aspects of the question?
3. Self-correction rate — how often do I catch my own errors before presenting?
4. Edge case coverage — do I consider boundary conditions?
5. Security awareness — do I flag security issues?
6. Conciseness — am I answering the question asked, not writing a textbook?
7. User satisfaction — do users find the answer helpful?

**What to track for each answer:**
- Did I need corrections after presenting? (quality indicator)
- Did I proactively self-evaluate before presenting? (process indicator)
- How confident was I, and was that confidence justified? (calibration indicator)
</think>

**Self-Improvement Metrics Framework**

**Tier 1: Correctness metrics (most important)**
| Metric | How to measure | Target |
|--------|---------------|--------|
| Code correctness | Does suggested code run without bugs? | > 95% |
| Factual accuracy | Are stated facts verifiable? | > 98% |
| Version accuracy | Are version-specific claims correct? | > 95% |

**Tier 2: Quality metrics**
| Metric | How to measure | Target |
|--------|---------------|--------|
| Edge case coverage | Did I mention boundary conditions? | > 80% of relevant cases |
| Security awareness | Did I flag security issues when present? | > 90% |
| Completeness | Did I answer ALL parts of the question? | > 90% |
| Conciseness | Did I answer without scope creep? | < 20% excess content |

**Tier 3: Process metrics (meta-learning)**
| Metric | How to measure | Target |
|--------|---------------|--------|
| Self-correction rate | Did I catch errors before presenting? | > 50% of errors caught |
| Confidence calibration | Was my confidence justified by outcome? | Within 10% of actual accuracy |
| Knowledge gap identification | Did I flag when I was uncertain? | > 80% of uncertain areas flagged |

**Tracking process:**
```
After each significant answer, log:
1. Topic area (Python, databases, security, etc.)
2. Confidence level (low/medium/high)
3. Self-evaluation score (1-10)
4. Corrections needed (0/1/2+)
5. What I would do differently next time

Monthly review:
- Which topic areas have the most corrections?
- Is my confidence calibrated? (high confidence should correlate with low corrections)
- Am I catching more errors through self-evaluation?
```

**Improvement indicators:**
- Fewer corrections needed over time
- Better calibrated confidence (fewer "I was confident but wrong" cases)
- More proactive edge case coverage
- Faster identification of knowledge gaps

**The most important metric:** Confidence calibration. If I'm highly confident and correct, that's good. If I'm uncertain and flag it, that's also good. If I'm highly confident and wrong — that's the dangerous failure mode to minimize.'''
    ),
    (
        "thinking/auto-metalearning-transfer-learning",
        r'''I just learned a debugging technique for Python (systematic print debugging with binary search). Can I transfer this skill to other languages? What's the generalizable principle?''',
        r'''<think>
The specific technique: when a Python script produces wrong output, I narrow down the bug by adding print statements at the midpoint of the code, checking if the output is correct so far, then searching the half where the bug is. This is binary search applied to debugging.

**What's language-specific:**
- Python syntax for print: `print(f"DEBUG: {variable}")`
- Python's specific debugger: `breakpoint()` / pdb
- Python's specific error types and tracebacks

**What's generalizable (the PRINCIPLE):**
1. Binary search debugging works in ANY language — it's a strategy, not a tool
2. The idea: divide the problem space in half, determine which half contains the bug, repeat
3. Works for: wrong output, crashes, slow code, incorrect state

**Transfer to other contexts:**
- JavaScript: console.log() at midpoints
- C/C++: printf() or GDB breakpoints
- Database queries: EXPLAIN ANALYZE on subqueries
- System issues: check logs at different service boundaries
- CSS: comment out half the stylesheet, narrow down

**Even more general principle:** Any search for an unknown (bug, bottleneck, root cause) benefits from binary search over linear search. Don't check every line — check the middle first.
</think>

**Generalizable Principle: Binary Search Debugging**

**The technique in Python:**
```python
# Script produces wrong output. Add print at midpoint:
result_1 = step_1(data)      # ← print here to check
result_2 = step_2(result_1)
result_3 = step_3(result_2)  # ← if result_1 is correct, bug is below
final = step_4(result_3)
```

**The PRINCIPLE (language-independent):**
> When searching for a bug in a sequential process, check the middle first. If the state is correct at the midpoint, the bug is in the second half. If incorrect, it's in the first half. Repeat.

**Transfer to other languages:**
| Language | Tool | Same principle |
|----------|------|---------------|
| JavaScript | `console.log()` | Check state at midpoint |
| Java | `System.out.println()` or debugger breakpoints | Same binary search |
| SQL | Run subqueries independently | Check intermediate results |
| Shell scripts | `echo` + `set -x` | Check state between commands |
| CSS | Comment out half the rules | Narrow down which rule causes the issue |

**Transfer to other domains:**
| Domain | Application |
|--------|------------|
| System debugging | Check logs at each service boundary |
| Network issues | Ping intermediate hops (traceroute) |
| Performance | Profile midpoint: is first half or second half slow? |
| Data pipelines | Check data integrity at each transformation step |

**The meta-learning insight:** When you learn a technique, ask:
1. What is the SPECIFIC tool? (print in Python)
2. What is the GENERAL principle? (binary search for unknowns)
3. Where else does this principle apply? (any sequential process)

Extracting the general principle from a specific technique is how ONE learning experience improves performance across MANY situations.'''
    ),
    (
        "thinking/auto-metalearning-when-to-say-dont-know",
        r'''How do I decide when to attempt an answer versus when to say "I don't know"? I sometimes give wrong answers because I try to answer everything.''',
        r'''<think>
This is about knowing the boundary of my own knowledge — a critical meta-skill.

**The problem with always answering:**
- If I'm wrong, the user builds on a false foundation
- Wrong answers with high confidence are worse than "I don't know"
- Trust is damaged when errors are discovered later

**The problem with always saying "I don't know":**
- Users don't get help
- I might actually know enough to be useful, even if not 100% certain
- "I don't know" without alternatives isn't helpful

**The right framework:** Calibrated confidence with transparent uncertainty.

**Decision matrix:**
1. I'm confident (> 90% sure) → Answer directly
2. I'm mostly confident (70-90%) → Answer with caveats: "I believe X, but verify because..."
3. I'm uncertain (40-70%) → Share what I do know, flag uncertainty, suggest verification
4. I don't know (< 40%) → Say "I'm not sure" and suggest where to find the answer

**The key rule:** Never present uncertain information with confident framing.
</think>

**When to Answer vs "I Don't Know" — Decision Framework**

**The calibration spectrum:**

| Confidence | Action | Example framing |
|-----------|--------|-----------------|
| > 90% certain | Answer directly | "Here's how to do X..." |
| 70-90% | Answer with caveats | "I believe X, but I'd recommend verifying Y because..." |
| 40-70% | Share partial knowledge | "I'm not certain, but I think X. You should verify by checking..." |
| < 40% | Say don't know | "I'm not sure about X. The best resource would be..." |

**Red flags that I should say "I don't know":**
1. **I'm extrapolating** — I know how X works in language A, I'm guessing it works the same in language B
2. **The topic changes rapidly** — library versions, cloud service pricing, API endpoints
3. **I'm combining things I've seen** — "I think you can combine X and Y" but I've never seen them combined
4. **I feel the urge to hedge** — if I'm writing "I think" or "probably" or "should", I'm uncertain

**The right way to say "I don't know":**
```
# Bad:
"I don't know."

# Good:
"I'm not confident about the specifics of X.
What I do know: [share what you're confident about].
To get the right answer, I'd recommend: [specific resource/documentation]."
```

**Why this matters more than being right:**
A model that says "I'm not sure, check the docs" when uncertain is MORE trustworthy than a model that gives a confident wrong answer. Users calibrate their trust based on your worst mistakes, not your best answers.

**Self-check before answering:**
1. Can I cite where I learned this? (If yes → higher confidence)
2. Has this fact changed recently? (If yes → flag uncertainty)
3. Am I extrapolating or stating something I've verified? (If extrapolating → caveat)
4. What's the cost of being wrong here? (If high → lower confidence threshold for "I don't know")'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
