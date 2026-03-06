"""Phase 4B: Self-Improvement — Self-Evaluation (Part 7)

Evaluating own explanations for clarity, accuracy, and accessibility.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-clarity-recursion-explanation",
        r'''I'm about to explain recursion to a beginner. Let me evaluate my explanation before presenting it:

My draft: "Recursion is when a function calls itself. The function must have a base case to terminate. Each recursive call pushes a new frame onto the call stack. The call stack unwinds when the base case is reached, returning values back up the chain."''',
        r'''<think>
Let me evaluate this explanation for a beginner:

**Jargon check:**
- "function calls itself" — OK, clear
- "base case" — introduces a term without defining it
- "terminate" — OK but could be simpler ("stop")
- "pushes a new frame onto the call stack" — way too technical for a beginner
- "call stack unwinds" — even more technical
- "returning values back up the chain" — vague without a visual

**What's missing:**
- No example (critical for recursion)
- No analogy to connect to something they already know
- No visual of how recursion works step by step
- Explains MECHANISM but not PURPOSE (why would you use this?)

**Accessibility score: 3/10**
This reads like a textbook definition. A beginner would understand the words but not grasp what recursion actually does or why they'd use it.

**A good recursion explanation should:**
1. Start with a relatable analogy
2. Show the simplest possible example
3. Trace through the example step by step
4. Explain the base case through the example (not abstractly)
5. Show when you'd use it in practice
</think>

**Self-evaluation: Too abstract, too technical, no example. Rating: 3/10 for a beginner audience.**

**Problems with my explanation:**
- "call stack," "stack frame," "unwinds" — computer science jargon
- No example — recursion MUST be shown, not just described
- Explains how it works mechanically, not what it does conceptually
- A beginner would nod along but not be able to write recursive code

**What I should say instead:**

"Recursion is when you solve a problem by breaking it into a smaller version of the same problem.

**Analogy:** Imagine you're in a line of people and you want to know how many people are in front of you. You could count them all yourself. Or you could ask the person in front: 'How many people are in front of YOU?' They ask the person in front of them, and so on. The person at the front says 'zero.' Each person adds 1 to the answer they got and passes it back. That's recursion.

**In code:**
```python
def count_people_ahead(person):
    if person.is_at_front():     # No one ahead? The answer is 0.
        return 0
    return 1 + count_people_ahead(person.next)  # Ask the next person + 1
```

**Step-by-step trace:**
```
count_people_ahead(Alice)     # Alice asks Bob
  count_people_ahead(Bob)     # Bob asks Charlie
    count_people_ahead(Charlie)  # Charlie is at the front!
    returns 0                    # 'Zero people ahead of me'
  returns 0 + 1 = 1             # Bob: '1 person ahead of me'
returns 1 + 1 = 2               # Alice: '2 people ahead of me'
```

The 'stopping point' (Charlie at the front returning 0) is called the **base case** — it prevents the question from going on forever."

**What I changed:**
- Replaced jargon with an analogy
- Added a concrete code example
- Traced through the example visually
- Introduced "base case" naturally through the example, not as a definition'''
    ),
    (
        "thinking/auto-selfeval-clarity-async-explanation",
        r'''I explained async/await to a developer who asked "what is async?" Let me evaluate my explanation:

My draft: "Async programming uses coroutines that yield control back to an event loop when they encounter an I/O operation. The event loop multiplexes multiple coroutines on a single thread using cooperative multitasking. When the I/O completes, the event loop resumes the coroutine from where it yielded. This is more efficient than threading because there's no context switching overhead and no need for locks."''',
        r'''<think>
Let me evaluate this for someone who asked "what is async?":

**Jargon density check:**
- "coroutines" — they don't know what this is yet
- "yield control" — confusing (yield has multiple meanings in programming)
- "event loop" — introduces a new concept without explaining it
- "multiplexes" — too technical
- "cooperative multitasking" — academic term
- "context switching overhead" — OS-level concept
- "locks" — concurrency concept they may not know

**Jargon count: 7 undefined terms in 3 sentences.** This would confuse even intermediate developers.

**What's wrong with the structure:**
- Immediately dives into implementation details
- Doesn't answer WHY you'd use async
- Doesn't show what async CODE looks like
- Compares to threading before they understand async itself
- No example of the problem async solves

**What a "what is async?" answer needs:**
1. The problem async solves (in plain language)
2. An analogy to everyday life
3. A simple before/after code example
4. THEN (optionally) how it works under the hood
</think>

**Self-evaluation: Way too technical for someone asking "what is async?" Rating: 2/10.**

**My explanation used 7 undefined jargon terms in 3 sentences.** Someone who asks "what is async?" doesn't know what coroutines, event loops, or cooperative multitasking are.

**What I should say instead:**

"**The problem:** Your code does a lot of waiting — waiting for API responses, database queries, file reads. Normally, your program just sits idle during that wait time.

**The analogy:** Imagine you're a chef cooking three dishes. Synchronous cooking: you put dish 1 in the oven, STAND THERE WAITING for 20 minutes, take it out, THEN start dish 2. Async cooking: you put dish 1 in the oven, immediately start prepping dish 2, put dish 2 on the stove, start prepping dish 3 — and check the oven when the timer dings. You're one chef doing three things by using wait time productively.

**In code:**
```python
# Synchronous (waiting one at a time):
data1 = fetch_from_api_1()   # Wait 200ms...
data2 = fetch_from_api_2()   # Wait 200ms...
data3 = fetch_from_api_3()   # Wait 200ms...
# Total: 600ms

# Async (waiting concurrently):
data1, data2, data3 = await asyncio.gather(
    fetch_from_api_1(),   # All three
    fetch_from_api_2(),   # start at
    fetch_from_api_3(),   # the same time
)
# Total: ~200ms (limited by the slowest one)
```

Async lets one thread do multiple things by using wait time to start other work — just like a chef who doesn't stand in front of the oven."

**What I changed:**
- Replaced ALL jargon with plain language
- Started with the PROBLEM, not the mechanism
- Used a relatable analogy (cooking)
- Showed a concrete before/after code comparison
- Saved implementation details (event loop, coroutines) for a follow-up question'''
    ),
    (
        "thinking/auto-selfeval-clarity-git-explanation",
        r'''A junior developer asked me to explain git branching. Let me evaluate my draft explanation:

My draft: "A branch is a pointer to a commit. When you create a branch, Git creates a new pointer. HEAD is a special pointer that points to the current branch. When you commit on a branch, the pointer moves forward. Merging combines the commits from two branches by creating a merge commit or fast-forwarding if possible."''',
        r'''<think>
Let me evaluate this for a junior developer:

**Accuracy:** Technically correct but heavily abstract.

**Clarity issues:**
1. "pointer to a commit" — what's a commit in their mental model?
2. "new pointer" — pointers are an abstract CS concept
3. "HEAD is a special pointer that points to the current branch" — too many abstract references chained together
4. "fast-forwarding" — introduces a concept without explaining it
5. No mention of WHY you'd use branches

**What's missing:**
- No practical workflow (create branch, make changes, merge back)
- No visual diagram showing branches diverging
- No commands (git branch, git checkout, git merge)
- No connection to their daily work (feature branches, pull requests)

**The fundamental problem:** This explanation describes what branches ARE (data structure), not what branches DO (workflow). A junior developer needs to understand the workflow, not the implementation.

**Assessment: 3/10 for a junior developer.**
</think>

**Self-evaluation: Technically correct but too abstract for a junior developer. Rating: 3/10.**

**My explanation describes what branches ARE (data structures), not what branches DO (enable parallel work). A junior developer needs workflow, not internals.**

**What I should say instead:**

"Branches let you work on something without affecting the main code. Think of it like making a copy of a document to try some edits — if the edits work out, you merge them back. If they don't, you throw away the copy without affecting the original.

**The workflow:**
```bash
# 1. You're on main (the 'official' code)
git checkout main

# 2. Create a branch for your feature
git checkout -b add-search-feature
# Now you're on a 'copy' — changes here don't affect main

# 3. Make changes and commit
git add search.py
git commit -m 'Add search functionality'
git commit -m 'Add search tests'
# These commits only exist on YOUR branch

# 4. When your feature is ready, merge it back
git checkout main
git merge add-search-feature
# Now main has your search feature!

# 5. Clean up
git branch -d add-search-feature
```

**Why this matters:**
- You can work on a feature for days without breaking the main code
- Multiple people can work on different features simultaneously
- If your feature doesn't work out, just delete the branch — main is untouched
- Code review happens on branches (pull requests) before merging to main

**Visual:**
```
main:     A---B---C---------G (merge)
                   \       /
feature:            D---E---F
```
Commits D, E, F happen on the feature branch. Main stays at C until you merge."

**What I changed:**
- Started with WHY (parallel work without risk)
- Used a relatable analogy (document copy)
- Showed the actual commands in a workflow
- Added a visual diagram of branch divergence
- Connected to their daily work (pull requests, code review)'''
    ),
    (
        "thinking/auto-selfeval-clarity-docker-volumes",
        r'''I explained Docker volumes to someone who asked "how do I persist data in Docker?" Let me check my answer:

My draft: "Use volumes. Mount a volume with -v flag: docker run -v mydata:/app/data myimage. Volumes persist data beyond container lifecycle. You can also use bind mounts with -v /host/path:/container/path. Named volumes are managed by Docker, bind mounts map to host filesystem paths."''',
        r'''<think>
Let me evaluate this explanation:

**What's good:**
- Shows the actual command syntax
- Mentions both volume types
- Technically correct

**What's wrong:**
1. Doesn't explain the PROBLEM first — why data disappears in Docker
2. "persist data beyond container lifecycle" — jargon-heavy way to say "keep data after container stops"
3. Introduces two concepts at once (volumes AND bind mounts) without clear distinction
4. No example showing the problem and solution
5. "Named volumes are managed by Docker, bind mounts map to host filesystem paths" — unclear what "managed by Docker" means practically

**What the user needs to understand first:**
- By default, when a Docker container is removed, all data inside it is gone
- This is like a computer that loses everything when you turn it off
- Volumes are like plugging in an external hard drive — the data survives

**Assessment: 5/10 — technically correct but doesn't explain the underlying problem or provide enough context.**
</think>

**Self-evaluation: Jumps to the solution without explaining the problem. Rating: 5/10.**

**What the user needs to understand first:** By default, data inside a Docker container disappears when the container is removed. This is surprising and confusing if you don't expect it.

**What I should say instead:**

"**The problem:** By default, Docker containers are disposable. When you remove a container, ALL data inside it is gone — including your database data, uploaded files, and logs. It's like a computer that erases its hard drive every time you turn it off.

**The solution: Volumes**

A volume is like an external hard drive that you plug into the container. The data on the volume survives even when the container is removed.

**Example — running PostgreSQL with persistent data:**
```bash
# WITHOUT a volume (data is lost when container is removed):
docker run --name my-db -e POSTGRES_PASSWORD=secret postgres
docker rm my-db  # All database data is GONE!

# WITH a volume (data persists):
docker run --name my-db \
  -v pgdata:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=secret \
  postgres

docker rm my-db   # Container is gone...
docker run --name my-db-2 \
  -v pgdata:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=secret \
  postgres
# ...but all your database tables and data are still there!
```

**Two types of volumes:**

| Type | Syntax | Use when |
|------|--------|----------|
| Named volume | `-v mydata:/container/path` | Database files, app data |
| Bind mount | `-v /my/local/folder:/container/path` | Development (edit code on host, run in container) |

**For development (bind mount):**
```bash
# Your local code changes are immediately visible inside the container:
docker run -v $(pwd):/app myimage
# Edit files on your machine → changes appear in the container instantly
```

**For production data (named volume):**
```bash
# Docker manages the storage location — just give it a name:
docker run -v uploads:/app/uploads myimage
```"

**What I changed:**
- Explained the PROBLEM first (data disappears)
- Added a concrete before/after example with PostgreSQL
- Clearly distinguished when to use each volume type
- Added the most common use cases (database persistence, development workflow)'''
    ),
    (
        "thinking/auto-selfeval-clarity-check-analogy-accuracy",
        r'''I used this analogy in my explanation: "An API is like a waiter in a restaurant. You (the client) tell the waiter what you want, the waiter goes to the kitchen (the server), and brings back your food (the response)." Let me verify this analogy is accurate and not misleading.''',
        r'''<think>
Let me evaluate this analogy for accuracy:

**What the analogy gets RIGHT:**
1. Client makes a request (ordering food) ✓
2. There's an intermediary (waiter/API) ✓
3. Server processes the request (kitchen prepares food) ✓
4. Response comes back (food is delivered) ✓
5. Client doesn't need to know how the kitchen works ✓

**What the analogy gets WRONG or oversimplifies:**
1. **A waiter is a person, not a contract.** An API is more like a MENU — it defines WHAT you can order and HOW to order it. The waiter is the transport mechanism (HTTP).
2. **APIs are standardized.** Every customer uses the same menu. A waiter can take free-form requests, but APIs require specific formats.
3. **Error handling.** If the kitchen is out of an item, there's a specific error response (404, 503). A waiter says "sorry, we're out." The analogy doesn't convey structured error handling.
4. **Authentication.** Some APIs require credentials. The analogy would need "the waiter checks your reservation before taking your order."
5. **Statelessness.** REST APIs don't remember your previous order. The waiter analogy implies memory ("the usual?").

**Is it misleading?** Slightly. The biggest issue is conflating the API (the contract/menu) with the transport (the waiter). But for a first introduction, it's close enough.

**Should I use it?** Yes, with a small clarification: the API is more like the MENU (what you can order and how) rather than the waiter (who carries the request).

**Rating: 7/10.** Good enough for a first introduction but could mislead if taken too literally.
</think>

**Self-evaluation: Good analogy but imprecise in one important way. Rating: 7/10.**

**What the analogy gets right:**
- Client sends a request, gets a response ✓
- Client doesn't need to know how the server works internally ✓
- There's a defined interface between client and server ✓

**What the analogy gets wrong:**

The API is more like the **menu** than the waiter. The menu defines:
- What you can order (available endpoints)
- How to order it (required parameters)
- What you'll get back (response format)
- What's not available (error responses)

The waiter is more like **HTTP** — the transport mechanism that carries your order back and forth.

**Improved analogy:**

"An API is like a restaurant's **menu and ordering system**. The menu lists what you can request (endpoints), what information you need to provide (parameters), and what you'll get back (response format).

You don't walk into the kitchen and cook your own food. You use the menu to place a structured order:

```
Order: GET /menu/appetizers          → List of appetizers
Order: POST /orders {item: 'pasta'}  → Your pasta order, with an order number
Order: GET /orders/42/status         → 'Being prepared' or 'Ready'
```

If you order something that doesn't exist, you get back '404 Not Found.' If the kitchen is overloaded, you get '503 Service Unavailable.'"

**When to use the waiter analogy:**
- First 30 seconds of explaining APIs to a complete beginner — it's a good starting point
- Then refine: "Actually, the API is more like the menu..."

**Self-evaluation lesson:** Analogies are powerful teaching tools, but verify they don't introduce wrong mental models. The best analogies are ones you can extend (menu → endpoints, prices → rate limits) without the analogy breaking down.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
