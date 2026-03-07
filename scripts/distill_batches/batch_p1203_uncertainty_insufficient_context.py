"""
Uncertainty and boundary-awareness training pairs - insufficient context
"""

pairs = [
    {
        "instruction": r'''Why is this function slow?

```python
def process(data):
    result = []
    for item in data:
        result.append(transform(item))
    return result
```''',
        "output": r'''<think>
They're asking why a function is slow but I can't see what `transform()` does, I don't know how large `data` is, and I don't know what the performance target is. The visible code is a simple loop with append -- that pattern itself is fine for most cases. The bottleneck is almost certainly inside `transform()`, which I can't see. I should point this out and give general optimization advice while being clear I'm guessing.
</think>

I can see the loop structure, but I can't tell you why it's slow because the bottleneck is almost certainly inside `transform()`, which I can't see.

The visible code itself -- iterating and appending -- is not typically a performance problem in Python unless `data` has millions of items. Here's what I'd need to actually diagnose this:

**Critical missing info:**
- What does `transform()` do? (database call? API request? heavy computation? file I/O?)
- How large is `data`? (100 items? 10 million?)
- How slow is "slow"? (1 second when you expect 100ms? 10 minutes?)

**If `transform()` does I/O (most likely culprit):**
```python
# If transform makes network/DB calls, use async or threading:
from concurrent.futures import ThreadPoolExecutor

def process(data):
    with ThreadPoolExecutor(max_workers=10) as pool:
        return list(pool.map(transform, data))
```

**If it's pure computation on a large dataset:**
```python
# List comprehension is slightly faster than append loop:
def process(data):
    return [transform(item) for item in data]

# Or if transform is vectorizable, use numpy/pandas
```

**To find the actual bottleneck:**
```python
import cProfile
cProfile.run('process(your_data)')
# Look at which function has the highest cumtime
```

Share what `transform()` does and how big `data` is, and I can give you a specific optimization instead of guessing.'''
    },
    {
        "instruction": r'''Fix this bug:

```
Traceback (most recent call last):
  File "main.py", line 42, in <module>
    result = process_data(config)
  ...
  File "utils.py", line 87, in validate
    raise ValueError("Invalid input")
ValueError: Invalid input
```''',
        "output": r'''<think>
This traceback is truncated -- the "..." hides the middle frames which would tell me the actual call chain. I can see that process_data(config) eventually calls validate() which raises ValueError("Invalid input"), but I don't know what config contains, what validate() checks, or what the intermediate functions do. The error message "Invalid input" is generic and unhelpful without seeing the validation logic. I need to be honest that I can't fix this with what I have.
</think>

I can't fix this bug from this traceback alone -- there's not enough information. Here's what I can see and what I'd need:

**What the traceback tells me:**
- `main.py:42` calls `process_data(config)`
- Somewhere in the call chain (hidden by `...`), `utils.py:87` in `validate()` raises `ValueError("Invalid input")`
- The error message is generic -- it doesn't say what was invalid or why

**What I'd need to actually fix this:**

1. **The full traceback** (without the `...`) -- the middle frames show exactly which functions called which, and often reveal what went wrong

2. **The code in `utils.py` around line 87** -- what does `validate()` actually check?
```python
# Something like:
def validate(data):
    if not data.get("required_field"):  # <-- what field? what check?
        raise ValueError("Invalid input")
```

3. **What's in `config`?** -- print it before the call:
```python
print(repr(config))  # see exactly what's being passed
result = process_data(config)
```

**Quick debugging approach:**
```python
# Add this before line 42 in main.py to see what's going in:
import json
print(json.dumps(config, indent=2, default=str))

# Or use pdb to inspect at the point of failure:
# python -m pdb main.py
# Then type 'c' to continue to the error, 'bt' for full traceback
```

Share the full traceback and the validate function code and I can likely spot the issue immediately.'''
    },
    {
        "instruction": r'''My API is returning 500 errors intermittently. How do I fix it?''',
        "output": r'''<think>
Intermittent 500 errors -- this could be caused by dozens of things: database connection pool exhaustion, race conditions, memory pressure, timeout issues, external service failures, unhandled exceptions in specific code paths, resource limits, etc. Without knowing the stack, the error logs, the frequency pattern, and what the API does, I genuinely cannot diagnose this. I should give a structured debugging approach rather than guess at causes.
</think>

Intermittent 500 errors are one of the hardest things to debug because the cause could be almost anything. I can't diagnose this without more context, but I can give you a systematic debugging approach:

**Step 1: Get the actual error (most important)**
Whatever framework you're using, you need the exception that triggers the 500:
- Check your application logs (not just access logs)
- If you don't have structured logging, that's the first thing to fix
- Look for the actual Python/Node/Java traceback behind the 500

**Step 2: Find the pattern**
- Does it correlate with traffic volume? (could be resource exhaustion)
- Does it happen on specific endpoints? (could be a code bug)
- Does it happen at specific times? (could be cron jobs or external dependencies)
- Does it happen after the service has been running a while? (could be memory leak)

**Step 3: Common causes of intermittent 500s**
- Database connection pool exhaustion (connections not being returned)
- External service timeouts (API calls to third parties failing)
- Race conditions under concurrent requests
- Memory pressure causing OOM kills
- File descriptor limits (`ulimit -n`)

**What I need to help you further:**
- What framework/language? (Flask, FastAPI, Express, Spring?)
- What do the error logs say? (the actual exception, not just "500")
- How intermittent? (1 in 100 requests? 1 per hour? random bursts?)
- What infrastructure? (single server, containers, serverless?)
- Any recent deployments before this started?

The actual error message/traceback from your logs will narrow this from "could be anything" to "here's your specific problem" in most cases.'''
    },
    {
        "instruction": r'''Review my code and tell me if it's production-ready:

```python
def get_user(user_id):
    db = get_connection()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return user.fetchone()
```''',
        "output": r'''<think>
They want to know if this is production-ready. I can see one function, but I have no context about the rest of the application -- the framework, how get_connection() works (connection pooling? new connection each time?), error handling elsewhere, whether there's authentication, etc. The function itself has some issues I can flag, but calling the whole thing "production-ready" or not requires way more context than one function.
</think>

I can flag issues with this specific function, but I can't tell you if your application is "production-ready" from one function -- that requires understanding your full architecture, error handling strategy, testing, deployment, and more.

**Issues I can see in this function:**

1. **No error handling** -- what happens if the DB is down or the query fails?
2. **Connection lifecycle unclear** -- does `get_connection()` return a pooled connection? Is it closed somewhere? This could leak connections
3. **`SELECT *` in production** -- fragile if columns change, fetches more data than needed
4. **No type hints or docstring**
5. **Returns None silently** if user doesn't exist -- callers might not handle this

**Improved version:**
```python
from typing import Optional

def get_user(user_id: int) -> Optional[dict]:
    """Fetch a user by ID. Returns None if not found."""
    try:
        db = get_connection()
        row = db.execute(
            "SELECT id, name, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    except DatabaseError:
        logger.exception("Failed to fetch user %s", user_id)
        raise
```

**Things I can't evaluate without more context:**
- Is `get_connection()` using connection pooling? (critical for production)
- Is there SQL injection risk elsewhere? (parameterized queries here are good)
- Is there authentication/authorization before this is called?
- Are there tests?
- Is there rate limiting, monitoring, logging?
- How is this deployed?

"Production-ready" is about the whole system, not individual functions. Share more of the architecture and I can give a more useful review.'''
    },
    {
        "instruction": r'''Why does my React component keep re-rendering?''',
        "output": r'''<think>
They're asking about re-rendering but haven't shown any component code. React re-rendering can be caused by many things: state changes, prop changes, context updates, parent re-renders, missing memoization, creating new objects/arrays/functions in render, etc. Without seeing the component and its parent, I'm just listing generic possibilities. I should ask for the code while still providing useful general guidance.
</think>

Without seeing your component code, I can only give you a general checklist -- the actual cause depends on your specific component tree and state management. Here are the most common causes:

**Most likely culprits:**

1. **Creating new objects/arrays/functions in render:**
```jsx
// BAD: new object every render -> child always re-renders
<Child style={{ color: 'red' }} />
<Child onClick={() => doSomething()} />

// GOOD: stable references
const style = useMemo(() => ({ color: 'red' }), []);
const handleClick = useCallback(() => doSomething(), []);
```

2. **Parent re-renders cascade down** -- every child re-renders when parent does, unless wrapped in `React.memo()`

3. **Context changes** -- if you're consuming a context that changes frequently, every consumer re-renders

4. **State updates that create new references:**
```jsx
// This triggers re-render even if data hasn't changed:
setItems([...items]);  // new array reference
```

**How to diagnose YOUR specific case:**

```jsx
// Add this to the component to see why it re-renders:
import { useRef, useEffect } from 'react';

function useWhyDidYouRender(name, props) {
    const prev = useRef(props);
    useEffect(() => {
        const changes = {};
        for (const key of Object.keys(props)) {
            if (prev.current[key] !== props[key]) {
                changes[key] = { from: prev.current[key], to: props[key] };
            }
        }
        if (Object.keys(changes).length) {
            console.log(`[${name}] changed:`, changes);
        }
        prev.current = props;
    });
}
```

**Or use React DevTools** -> Profiler -> "Why did this render?" (enable in settings)

Share your component code and I can point to the specific cause instead of this general list.'''
    },
]
